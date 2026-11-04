// SPDX-License-Identifier: MIT
/* emitter: NN_BG → task 表 + regcmd 指令流 + 六块 GEM(P2 核心)
 *
 * 机制(dsh-008/009 + dsh-010):
 *   gem1 = 563 个 blob 按 blob 下标 64B 对齐顺序拼接; 模板是模型里的
 *          8B 记录 {u16 rsvd, u16 reg, u32 value}, 加载期按 edge.f5 的
 *          (reg → tensor,offset) 回填地址, 首层再改 0x104c/0x1180,
 *          最后按 task 发射顺序回写 lane 位(0x1004/0x3004 的 bit28-29)。
 *   gem2 = 8 趟(A×3/B×2/C×3)逐 task 从 gem1 拷 amt 包并编码成硬件包,
 *          槽尾 4 包 0x0010(next chunk)/0x0014(pc_amount|mode<<16)/
 *          常量 0x0041.../0x0008(enable, tag 0x0081)。
 *   task = 每 task 40B, op/enable/int_mask/amt/regcfg_off/regcmd_addr。
 *
 * 关键实测偏差(详见 .claude/rknn/dsh-010-emitter.md):
 *   - 0x0014 的 pc_amount 取“同一 lane 内下一条 task”的 amt; lane 末条为 0。
 *   - 0x0010 在 lane 末条写 8B 零, 不是 reg=0 的编码包。
 *   - mode 不是趟号: A/特殊 A 模板、em=0x60 的 26 包模板、Concat 的 f2=4
 *     copy 模板用 0, B 用 1, C 用 2。
 *   - gem1 的 lane 位是“最后写者”。
 *
 * dsh-012 泛化(zoo 全模型):
 *   - B0/C0 的特殊 A 追加条件不是硬编码 op53, 而是“该 op 缺 B0/C0 组”;
 *     缺组时把 A 组(含 tensor2 预载行)按 lane0 补在 B/C 组之后。
 *   - edge.f1(tensor2) 非零时先发一块预载模板; mbv3s 的 HardSigmoid 用
 *     tensor2=1 的 kind6 常量, reloc 地址指向 regcmd GEM 而不是 activation。
 *   - 多输出按 JSON 声明序各占一块 output GEM(gem6, gem7, ...)。
 */
#include "emitter.h"

#include <cstring>
#include <vector>

#include "shell_ctx.h"
#include "task.h"

namespace rknn {

namespace {

constexpr uint32_t kOpExtra = 4;  // 槽尾 4 个 PC 包

struct Row {
    uint32_t       op     = 0;
    EdgeGroup      group  = GRP_A;
    const EdgeRef* edge   = nullptr;
    uint32_t       tensor = 0;  // 本行搬运的实际 blob(tensor2 预载行时 != edge->tensor)
    uint32_t       lane   = 0;
    uint32_t       amt    = 0;
    uint64_t       chunk_off = 0;
    bool           pass_last = false;
};

uint64_t encode_packet_raw(uint16_t reg, uint32_t value, uint16_t tag) {
    return (uint64_t)reg | ((uint64_t)value << 16) | ((uint64_t)tag << 48);
}

uint32_t encode_int_mask(uint32_t raw) {
    return (raw & 0xc00u) ? 0xc00u : 0x300u;
}

// 模板内 8B 记录: reg@+2, value@+4
uint16_t rec_reg(const uint8_t* p) {
    uint16_t v;
    std::memcpy(&v, p + 2, 2);
    return v;
}
uint32_t rec_val(const uint8_t* p) {
    uint32_t v;
    std::memcpy(&v, p + 4, 4);
    return v;
}
void rec_set_val(uint8_t* p, uint32_t v) {
    std::memcpy(p + 4, &v, 4);
}

uint64_t output_base(const Context& c, uint32_t ti) {
    const Model& m = c.model;
    for (size_t i = 0; i < m.output_tensors.size(); i++) {
        if ((uint32_t)m.output_tensors[i] != ti)
            continue;
        if (i == 0)
            return c.buffer(rknn::BufferSlot::Output).dma_addr;
        return i - 1 < c.extra_out.size() ? c.extra_out[i - 1].dma_addr : 0;
    }
    return c.buffer(rknn::BufferSlot::Output).dma_addr;
}

uint64_t tensor_base(const Context& c, uint32_t ti) {
    const Model& m = c.model;
    if (ti >= m.tensors.size())
        return 0;
    const TensorRef& t = m.tensors[ti];
    switch (t.kind) {
    case 1:
        return c.buffer(rknn::BufferSlot::Input).dma_addr;  // graph input
    case 2:
        return output_base(c, ti);  // graph output[i]
    case 3:
        return c.buffer(rknn::BufferSlot::Activations).dma_addr +
               t.internal_off;  // f13 即 internal 偏移
    case 4:
        return c.buffer(rknn::BufferSlot::Weights).dma_addr + t.gem1_off;  // 权重按 blob 打包
    case 0: {
        // 空表 kind=0 是隐式 alias: blob 下标 = tensor 下标 + 1(实测 105/106/107/165/166)
        uint32_t bi = ti + 1;
        if (bi < m.blobs.size())
            return c.buffer(rknn::BufferSlot::Weights).dma_addr + m.blobs[bi].pack_off;
        break;
    }
    default:
        break;
    }
    return 0;
}

int build_plan(const Model& m, std::vector<Row>* rows, Context* ctx) {
    auto add_row = [&](uint32_t oi, EdgeGroup g, const EdgeRef& e, uint32_t lane,
                       uint32_t tensor) -> bool {
        if (tensor >= m.tensors.size())
            return false;
        int32_t bi = m.tensors[tensor].blob;
        if (bi < 0 || (uint32_t)bi >= m.blobs.size())
            return false;
        if (m.blobs[bi].size % 8)
            return false;
        Row r;
        r.op     = oi;
        r.group  = g;
        r.edge   = &e;
        r.tensor = tensor;
        r.lane   = lane;
        r.amt    = m.blobs[bi].size / 8;
        rows->push_back(r);
        return true;
    };
    // edge.f1(tensor2) 非零时先发一块附加模板(HardSigmoid 的共享常量),
    // 再发主模板; 两条都是同一 lane/group 的独立 task。
    auto add_edge = [&](uint32_t oi, EdgeGroup g, const EdgeRef& e, uint32_t lane) -> bool {
        if (e.tensor2 && e.tensor2 < m.tensors.size()) {
            if (!add_row(oi, g, e, lane, e.tensor2))
                return false;
        }
        return add_row(oi, g, e, lane, e.tensor);
    };

    // 每趟(lane)是 regcmd 里独立的一段: lane 末条的 0x0010/0x0014 归零
    for (uint32_t lane = 0; lane < 3; lane++) {
        uint32_t start = (uint32_t)rows->size();
        for (uint32_t oi = 0; oi < m.ops.size(); oi++)
            for (uint16_t ei : m.ops[oi].groups[GRP_A])
                if (!add_edge(oi, GRP_A, m.ops[oi].edges[ei], lane))
                    return -4;
        if (!rows->empty() && rows->size() > start)
            rows->back().pass_last = true;
        ctx->seg_a[lane] = (uint32_t)rows->size() - start;
    }
    for (uint32_t lane = 0; lane < 2; lane++) {
        uint32_t  start = (uint32_t)rows->size();
        EdgeGroup g     = lane == 0 ? GRP_B0 : GRP_B1;
        for (uint32_t oi = 0; oi < m.ops.size(); oi++) {
            for (uint16_t ei : m.ops[oi].groups[g])
                if (!add_edge(oi, g, m.ops[oi].edges[ei], lane))
                    return -4;
            // B0 缺组时把该 op 的 A 模板补在 lane0(可含 tensor2 预载行)
            if (lane == 0 && m.ops[oi].groups[GRP_B0].empty())
                for (uint16_t ei : m.ops[oi].groups[GRP_A])
                    if (!add_edge(oi, GRP_A, m.ops[oi].edges[ei], 0))
                        return -4;
        }
        if (rows->size() > start)
            rows->back().pass_last = true;
        ctx->seg_b[lane] = (uint32_t)rows->size() - start;
    }
    for (uint32_t lane = 0; lane < 3; lane++) {
        uint32_t  start = (uint32_t)rows->size();
        EdgeGroup g     = lane == 0 ? GRP_C0 : (lane == 1 ? GRP_C1 : GRP_C2);
        for (uint32_t oi = 0; oi < m.ops.size(); oi++) {
            for (uint16_t ei : m.ops[oi].groups[g])
                if (!add_edge(oi, g, m.ops[oi].edges[ei], lane))
                    return -4;
            // C0 缺组时同理补 A 模板(op38 这类只有 B 组的 op 也会命中)
            if (lane == 0 && m.ops[oi].groups[GRP_C0].empty())
                for (uint16_t ei : m.ops[oi].groups[GRP_A])
                    if (!add_edge(oi, GRP_A, m.ops[oi].edges[ei], 0))
                        return -4;
        }
        if (rows->size() > start)
            rows->back().pass_last = true;
        ctx->seg_c[lane] = (uint32_t)rows->size() - start;
    }
    ctx->rows_a = ctx->seg_a[0] + ctx->seg_a[1] + ctx->seg_a[2];
    ctx->rows_b = ctx->seg_b[0] + ctx->seg_b[1];
    ctx->rows_c = ctx->seg_c[0] + ctx->seg_c[1] + ctx->seg_c[2];
    return 0;
}

// 加载期: 权重搬运 + edge.f5 地址回填 + 首层常数 + lane 位(最后写者)
int fill_weights(const Context& ctx, const std::vector<Row>& rows) {
    const Model& m = ctx.model;
    uint8_t*     w = (uint8_t*)ctx.buffer(rknn::BufferSlot::Weights).map;
    std::memset(w, 0, (size_t)ctx.buffer(rknn::BufferSlot::Weights).size);
    for (size_t i = 0; i < m.blobs.size(); i++) {
        const BlobRef& b = m.blobs[i];
        if (b.size)
            std::memcpy(w + b.pack_off, m.raw.data() + b.data_off, b.size);
    }

    for (const Row& r : rows) {
        const TensorRef& tt = m.tensors[r.tensor];
        int32_t          bi = tt.blob;
        if (bi < 0 || (uint32_t)bi >= m.blobs.size())
            return -5;
        uint8_t* base            = w + m.blobs[bi].pack_off;
        uint32_t amt             = r.amt;
        bool     first           = false;
        // kind=6 是常量/regcmd 预载模板: 它的 0x4020/0x5018 指向 regcmd GEM,
        // 不是 reloc 目标 activation 的 internal 地址(mbv3s HardSigmoid 实测)。
        bool     regcmd_template = tt.kind == 6;
        for (const Reloc& rl : r.edge->relocs) {
            uint64_t tb  = regcmd_template ? ctx.buffer(rknn::BufferSlot::Commands).dma_addr
                                           : tensor_base(ctx, rl.tensor);
            uint32_t v32 = (uint32_t)(tb + rl.offset);
            for (uint32_t p = 0; p < amt; p++) {
                uint8_t* rec = base + (uint64_t)p * 8;
                if (rec_reg(rec) == rl.reg)
                    rec_set_val(rec, v32);
            }
            if (rl.tensor < m.tensors.size() && m.tensors[rl.tensor].kind == 1)
                first = true;
        }
        if (first) {
            // 0x104c(CVT_CON0) 回填值按输入张量 dtype_code: 10(float16)→1, 3(int8)→9
            uint32_t cvt = m.tensors[m.input_tensor].dtype_code == 3 ? 9 : 1;
            for (uint32_t p = 0; p < amt; p++) {
                uint8_t* rec = base + (uint64_t)p * 8;
                uint16_t reg = rec_reg(rec);
                if (reg == 0x104c)
                    rec_set_val(rec, cvt);
                else if (reg == 0x1180)
                    rec_set_val(rec, 0xfff);
            }
        }
        for (uint32_t p = 0; p < amt; p++) {
            uint8_t* rec = base + (uint64_t)p * 8;
            uint16_t reg = rec_reg(rec);
            if (reg == 0x1004 || reg == 0x3004) {
                uint32_t v = rec_val(rec);
                v          = (v & ~0x30000000u) | (r.lane << 28);
                rec_set_val(rec, v);
            }
        }
    }
    return 0;
}

uint32_t row_mode(const Row& r) {
    if (r.group == GRP_A)
        return 0;  // A 与 B0*/C0* 的特殊 A 模板
    if (r.edge->enable_mask == 0x60)
        return 0;  // 26 包 weight/CBUF 载入模板
    if (r.edge->f2 == 4)
        return 0;  // Concat 的 copy 模板(f2=4)也是 mode0
    if (r.group == GRP_B0 || r.group == GRP_B1)
        return 1;
    return 2;
}

int fill_regcmd_task(const Context& ctx, const std::vector<Row>& rows) {
    const Model& m  = ctx.model;
    uint8_t*     rg = (uint8_t*)ctx.buffer(rknn::BufferSlot::Commands).map;
    uint8_t*     tk = (uint8_t*)ctx.buffer(rknn::BufferSlot::Tasks).map;
    uint8_t*     w  = (uint8_t*)ctx.buffer(rknn::BufferSlot::Weights).map;
    std::memset(rg, 0, (size_t)ctx.buffer(rknn::BufferSlot::Commands).size);
    std::memset(tk, 0, (size_t)ctx.buffer(rknn::BufferSlot::Tasks).size);

    for (size_t i = 0; i < rows.size(); i++) {
        const Row&       r  = rows[i];
        const TensorRef& tt = m.tensors[r.tensor];
        int32_t          bi = tt.blob;
        if (bi < 0 || (uint32_t)bi >= m.blobs.size())
            return -5;
        const uint8_t* src = w + m.blobs[bi].pack_off;
        uint8_t*       dst = rg + r.chunk_off;

        for (uint32_t p = 0; p < r.amt; p++) {
            uint16_t reg = rec_reg(src + (uint64_t)p * 8);
            uint32_t val = rec_val(src + (uint64_t)p * 8);
            if (reg == 0x1004 || reg == 0x3004)
                val = (val & ~0x30000000u) | (r.lane << 28);
            uint64_t pkt = encode_packet(reg, val);
            std::memcpy(dst + (uint64_t)p * 8, &pkt, 8);
        }

        uint8_t* tr = dst + (uint64_t)r.amt * 8;
        if (r.pass_last) {
            std::memset(tr, 0, 8);  // PC 链终止: 裸 8B 零, 不是 reg=0 编码包
        } else {
            uint64_t next = ctx.buffer(rknn::BufferSlot::Commands).dma_addr + rows[i + 1].chunk_off;
            uint64_t p    = encode_packet(0x0010, (uint32_t)next);
            std::memcpy(tr, &p, 8);
        }
        uint32_t pc  = r.pass_last ? 0 : pc_amount(rows[i + 1].amt, 2);
        uint64_t p14 = encode_packet(0x0014, pc | (row_mode(r) << 16));
        std::memcpy(tr + 8, &p14, 8);
        uint64_t konst = 0x0041000000000000ULL;
        std::memcpy(tr + 16, &konst, 8);
        uint64_t pen = encode_packet_raw(0x0008, r.edge->enable_mask, 0x0081);
        std::memcpy(tr + 24, &pen, 8);

        const TaskRecord record{
            .operation_index = r.op,
            .enable_mask     = r.edge->enable_mask,
            .interrupt_mask  = encode_int_mask(r.edge->int_mask_raw),
            .interrupt_clear = 0x1ffff,
            .register_count  = r.amt,
            .register_offset = static_cast<uint32_t>(m.blobs[bi].pack_off >> 3),
            .command_address = ctx.buffer(BufferSlot::Commands).dma_addr + r.chunk_off,
        };
        std::memcpy(tk + i * sizeof(record), &record, sizeof(record));
    }
    return 0;
}

}  // namespace

uint64_t encode_packet(uint16_t reg, uint32_t value) {
    uint32_t bank = reg >> 12;
    uint16_t tag;
    if (bank < 8)
        tag = (uint16_t)((1u << (bank + 8)) | 1u);
    else if (bank == 8)
        tag = 0x0401;
    else if (bank == 0xf)
        tag = 0x0008;
    else
        tag = 0x0001;
    return (uint64_t)reg | ((uint64_t)value << 16) | ((uint64_t)tag << 48);
}

uint32_t slot_packets(uint32_t amt) {
    return (amt + 11) & ~7u;
}

uint32_t pc_amount(uint32_t amt, uint32_t scale) {
    return (amt + kOpExtra + scale - 1) / scale - 1;
}

int emit_build(Context* ctx) {
    if (!ctx)
        return -1;
    Model& m = ctx->model;
    if (m.blobs.empty() || m.tensors.empty() || m.ops.empty())
        return -2;

    std::vector<Row> rows;
    int              rc = build_plan(m, &rows, ctx);
    if (rc)
        return rc;
    if (rows.empty())
        return -3;

    uint64_t regcmd_size = 0;
    for (Row& r : rows) {
        r.chunk_off = regcmd_size;
        regcmd_size += (uint64_t)slot_packets(r.amt) * 8;
    }

    uint64_t weight_size = m.gem1_size;
    uint64_t task_size   = (uint64_t)rows.size() * 40;

    uint64_t internal_size = m.internal_size;
    if (!internal_size) {
        for (const TensorRef& t : m.tensors)
            if (t.kind == 3 && (uint64_t)t.internal_off + t.size > internal_size)
                internal_size = (uint64_t)t.internal_off + t.size;
        internal_size = (internal_size + 0xfff) & ~(uint64_t)0xfff;
    }
    uint64_t input_size = 0, output_size = 0;
    auto     alloc_size = [&](int ti) -> uint64_t {
        const TensorRef& t = m.tensors[ti];
        if (t.size)
            return t.size;
        uint64_t n = 1;
        for (uint32_t i = 0; i < t.ndim; i++)
            n *= t.dims[i];
        return n * (t.dtype_code == 3 ? 1 : 2);
    };
    if (!m.input_tensors.empty())
        input_size = alloc_size(m.input_tensors[0]);
    else
        for (const TensorRef& t : m.tensors)
            if (t.kind == 1 && !input_size)
                input_size = t.size;

    // 输出 GEM 按 JSON 声明序: output[0] 占 gem[5], 其余追加到 extra_out。
    std::vector<int> outs = m.output_tensors;
    if (outs.empty())
        for (size_t i = 0; i < m.tensors.size(); i++)
            if (m.tensors[i].kind == 2)
                outs.push_back((int)i);
    if (!outs.empty())
        output_size = alloc_size(outs[0]);
    if (!weight_size || !regcmd_size || !task_size || !internal_size || !input_size ||
        !output_size || outs.empty())
        return -6;

    const uint64_t sizes[6]      = {weight_size,   regcmd_size, task_size,
                                    internal_size, input_size,  output_size};
    // 无 IOMMU 位时的基础 flags: weight 2 / regcmd 4 / task 0xa / 其余 2
    const uint32_t base_flags[6] = {0x2, 0x4, 0xa, 0x2, 0x2, 0x2};

    auto destroy_all = [&]() {
        ctx->release_buffers();
        ctx->extra_out.clear();
    };
    for (int i = 0; i < 6; i++) {
        uint32_t fl = base_flags[i] | (ctx->iommu_en ? 1u : 0u);
        int      r  = ctx->drv.mem_create(sizes[i], fl, &ctx->gem[i]);
        if (r) {
            destroy_all();
            return r;
        }
    }
    ctx->extra_out.clear();
    for (size_t i = 1; i < outs.size(); i++) {
        GemBuffer g;
        uint32_t  fl = 0x2 | (ctx->iommu_en ? 1u : 0u);
        int       r  = ctx->drv.mem_create(alloc_size(outs[i]), fl, &g);
        if (r) {
            if (g.fd >= 0)
                ctx->drv.mem_destroy(&g);
            destroy_all();
            return r;
        }
        ctx->extra_out.push_back(g);
    }
    ctx->regcmd_size = regcmd_size;
    ctx->task_size   = task_size;

    rc = fill_weights(*ctx, rows);
    if (rc) {
        destroy_all();
        return rc;
    }
    rc = fill_regcmd_task(*ctx, rows);
    if (rc) {
        destroy_all();
        return rc;
    }

    // Every generated buffer must reach the device before the first submit.
    for (const auto slot :
         {BufferSlot::Weights, BufferSlot::Commands, BufferSlot::Tasks, BufferSlot::Activations}) {
        const auto& buffer = ctx->buffer(slot);
        if (buffer.map) {
            const int error = ctx->drv.mem_sync(buffer, 0, buffer.size, SyncDirection::ToDevice);
            if (error) {
                destroy_all();
                return error;
            }
        }
    }
    return 0;
}

}  // namespace rknn
