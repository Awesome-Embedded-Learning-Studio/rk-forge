// SPDX-License-Identifier: MIT
/* loader: .rknn 1.5.0 容器层 + NN_BG schema 解析
 *
 * 容器地图(实证 notes/rknn/001/004 + dsh-009):
 *   0x00 "RKNN" + u64 version + u64 data_size
 *   version>=2 → NN_BG(FlatBuffers) 起点 = 0x40; root = base + u32(base)
 *   尾部明文 JSON(前置 u64 长度): io 张量数/尺寸,单 NNBG 节点
 * NN_BG 的字段号语义按 dsh-009 固定, 全部落成 Model 里的值类型对象,
 * emitter 不再直接摸 FlatBuffers。
 */
#ifndef _GNU_SOURCE
#    define _GNU_SOURCE
#endif
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "fb.h"
#include "model.h"

namespace rknn {

namespace {

bool find_json(const uint8_t* d, size_t n, uint64_t* off) {
    // JSON 段以 "{\"" 开头直到文件尾;从后向前找合法起点(与 rknn_dump.py 同法)
    for (size_t i = n - 2; i > 0; i--) {
        if (d[i] == '{' && d[i + 1] == '"') {
            if (i >= 8) {
                uint64_t len;
                std::memcpy(&len, d + i - 8, 8);
                if (len > 0 && len <= n - i) {
                    *off = i;
                    return true;
                }
            }
        }
    }
    return false;
}

// 最小 JSON 字段抽取: 只拿 input_num/output_num 与 norm_tensor 的 size[]/url
void scan_json(const char* j, size_t n, Model* m) {
    auto find_key = [&](const char* key) -> const char* {
        char pat[48];
        snprintf(pat, sizeof(pat), "\"%s\"", key);
        return (const char*)memmem(j, n, pat, strlen(pat));
    };
    const char* p;
    if ((p = find_key("input_num")))
        sscanf(p, "%*[^:]: %u", &m->input_num);
    if ((p = find_key("output_num")))
        sscanf(p, "%*[^:]: %u", &m->output_num);
    const char* nt = find_key("norm_tensor");
    if (!nt)
        return;
    const char* end = j + n;
    const char* q   = nt;
    while ((q = (const char*)memmem(q, end - q, "\"size\":", 7)) != nullptr) {
        TensorAttr  t{};
        const char* lb = strchr(q + 7, '[');
        const char* rb = lb ? strchr(lb, ']') : nullptr;
        if (!lb || !rb)
            break;
        uint32_t v      = 0;
        bool     in_num = false;
        for (const char* r = lb + 1; r <= rb; r++) {
            if (*r >= '0' && *r <= '9') {
                v      = v * 10 + (*r - '0');
                in_num = true;
                continue;
            }
            if (in_num && t.ndim < 16) {
                t.dims[t.ndim++] = v;
                v                = 0;
                in_num           = false;
            }
        }
        t.n_elems = 1;
        for (uint32_t i = 0; i < t.ndim; i++)
            t.n_elems *= t.dims[i];
        const char* u = (const char*)memmem(rb, end - rb > 256 ? 256 : end - rb, "\"url\":", 6);
        if (u) {
            char name[64] = {0};
            sscanf(u + 6, " \"%63[^\"]", name);
            t.name = name;
        }
        m->tensors_json.push_back(t);
        q = rb;
    }
}

// FlatBuffers vector<Table>: 每个元素是相对自身的 uoffset
bool table_vec(const fb::Table& t, uint32_t slot, std::vector<fb::Table>* out) {
    const uint8_t* p = nullptr;
    uint32_t       n = 0;
    if (!t.get_vec(slot, &p, &n))
        return false;
    uint64_t base = (uint64_t)(p - t.buf);
    out->reserve(n);
    for (uint32_t i = 0; i < n; i++) {
        uint32_t uo;
        std::memcpy(&uo, p + i * 4, 4);
        out->push_back({t.buf, base + (uint64_t)i * 4 + uo});
    }
    return true;
}

template <typename T>
bool scalar_or(const fb::Table& t, uint32_t slot, T* out) {
    T v{};
    if (!t.get_scalar(slot, &v))
        return false;
    *out = v;
    return true;
}

// f8/f9/f10 是 vector<int>, 元素 bit pattern 即 f32(量化 min/max/scale)
bool vec_first_f32(const fb::Table& t, uint32_t slot, float* out) {
    const uint8_t* p = nullptr;
    uint32_t       n = 0;
    if (!t.get_vec(slot, &p, &n) || n == 0)
        return false;
    uint32_t bits = 0;
    std::memcpy(&bits, p, 4);
    std::memcpy(out, &bits, 4);
    return true;
}

int parse_layout(const std::string& cfg) {
    size_t p = cfg.find("\"layout\"");
    if (p == std::string::npos)
        return -1;
    p = cfg.find(':', p);
    if (p == std::string::npos)
        return -1;
    p = cfg.find('"', p);
    if (p == std::string::npos)
        return -1;
    size_t q = cfg.find('"', p + 1);
    if (q == std::string::npos)
        return -1;
    std::string v = cfg.substr(p + 1, q - p - 1);
    if (v == "NHWC")
        return 1;
    if (v == "NCHW")
        return 0;
    if (v == "NC1HWC2")
        return 2;
    return -1;
}

// 从 py-dict 风格的 attrs JSON 里抠 mean/std 数组(长度随 C)
bool parse_floats(const std::string& s, const char* key, std::vector<float>* out) {
    size_t p = s.find(std::string("'") + key + "'");
    if (p == std::string::npos)
        p = s.find(std::string("\"") + key + "\"");
    if (p == std::string::npos)
        return false;
    p = s.find('[', p);
    if (p == std::string::npos)
        return false;
    size_t q = s.find(']', p);
    if (q == std::string::npos)
        return false;
    std::string body = s.substr(p + 1, q - p - 1);
    const char* c    = body.c_str();
    out->clear();
    while (*c) {
        char*  end = nullptr;
        double v   = std::strtod(c, &end);
        if (end == c)
            break;
        out->push_back((float)v);
        c = end;
        while (*c == ',' || *c == ' ' || *c == '\t')
            c++;
    }
    return !out->empty();
}

void parse_blobs(const Model& m, const fb::Table& root, Model* out) {
    std::vector<fb::Table> tabs;
    table_vec(root, 4, &tabs);
    out->blobs.reserve(tabs.size());
    for (const auto& bt : tabs) {
        BlobRef        b;
        const uint8_t* p = nullptr;
        uint32_t       n = 0;
        if (bt.get_vec(0, &p, &n)) {
            b.data_off = (uint64_t)(p - m.raw.data());
            b.size     = n;
        }
        out->blobs.push_back(b);
    }
    uint64_t cur = 0;
    for (auto& b : out->blobs) {
        b.pack_off = cur;
        cur        = (cur + b.size + 0x3f) & ~(uint64_t)0x3f;
    }
    out->gem1_size = cur;
}

void parse_tensors(const Model& m, const fb::Table& graph, Model* out) {
    std::vector<fb::Table> tabs;
    table_vec(graph, 0, &tabs);
    out->tensors.reserve(tabs.size());
    for (const auto& tt : tabs) {
        TensorRef r;
        scalar_or(tt, 2, &r.kind);
        scalar_or(tt, 0, &r.dtype_code);
        scalar_or(tt, 12, &r.size);
        scalar_or(tt, 13, &r.internal_off);
        r.has_f20 = tt.field_off(20) != 0;
        {
            const char* ns = nullptr;
            uint32_t    nl = 0;
            if (tt.get_str(5, &ns, &nl) && nl)
                r.name.assign(ns, nl);
        }
        {
            const uint8_t* dp = nullptr;
            uint32_t       dn = 0;
            if (tt.get_vec(4, &dp, &dn)) {
                r.ndim = dn > 8 ? 8 : dn;
                for (uint32_t k = 0; k < r.ndim; k++)
                    std::memcpy(&r.dims[k], dp + k * 4, 4);
            }
            if (tt.get_vec(3, &dp, &dn)) {
                r.native_ndim = dn > 8 ? 8 : dn;
                for (uint32_t k = 0; k < r.native_ndim; k++)
                    std::memcpy(&r.native_dims[k], dp + k * 4, 4);
            }
        }
        const uint8_t* qv = nullptr;
        uint32_t       qn = 0;
        if (tt.get_vec(11, &qv, &qn) && qn >= 1)
            std::memcpy(&r.zp, qv, 4);  // f11[0] = zero_point
        vec_first_f32(tt, 8, &r.qmin);
        vec_first_f32(tt, 9, &r.qmax);
        vec_first_f32(tt, 10, &r.scale);
        uint32_t bi = 0;
        if (scalar_or(tt, 18, &bi) && bi < out->blobs.size()) {
            r.blob     = (int32_t)bi;
            r.gem1_off = out->blobs[bi].pack_off;
        }
        if (r.kind == 1 && !out->input_tensor)
            out->input_tensor = (int)out->tensors.size();
        if (r.kind == 2 && !out->output_tensor)
            out->output_tensor = (int)out->tensors.size();
        out->tensors.push_back(r);
    }
    (void)m;
}

void build_io_maps(Model* out) {
    std::vector<int> in_kind, out_kind;
    for (size_t i = 0; i < out->tensors.size(); i++) {
        if (out->tensors[i].kind == 1)
            in_kind.push_back((int)i);
        if (out->tensors[i].kind == 2)
            out_kind.push_back((int)i);
    }
    auto by_name = [&](uint8_t kind, const std::string& name) -> int {
        if (name.empty())
            return -1;
        for (size_t i = 0; i < out->tensors.size(); i++)
            if (out->tensors[i].kind == kind && out->tensors[i].name == name)
                return (int)i;
        return -1;
    };
    for (uint32_t i = 0; i < out->input_num; i++) {
        int ti = -1;
        if (i < out->tensors_json.size())
            ti = by_name(1, out->tensors_json[i].name);
        if (ti < 0 && i < in_kind.size())
            ti = in_kind[i];
        if (ti >= 0)
            out->input_tensors.push_back(ti);
    }
    for (uint32_t i = 0; i < out->output_num; i++) {
        size_t ji = (size_t)out->input_num + i;
        int    ti = -1;
        if (ji < out->tensors_json.size())
            ti = by_name(2, out->tensors_json[ji].name);
        if (ti < 0 && i < out_kind.size())
            ti = out_kind[i];
        if (ti >= 0)
            out->output_tensors.push_back(ti);
    }
    if (!out->input_tensors.empty())
        out->input_tensor = out->input_tensors[0];
    else if (!in_kind.empty())
        out->input_tensor = in_kind[0];
    if (!out->output_tensors.empty())
        out->output_tensor = out->output_tensors[0];
    else if (!out_kind.empty())
        out->output_tensor = out_kind[0];
}

void parse_ops(const Model& m, const fb::Table& graph, Model* out) {
    std::vector<fb::Table> tabs;
    table_vec(graph, 1, &tabs);
    out->ops.reserve(tabs.size());
    const uint8_t* raw   = m.raw.data();
    const uint64_t raw_n = m.raw.size();
    for (const auto& ot : tabs) {
        OpRef       op;
        const char* type     = nullptr;
        uint32_t    type_len = 0;
        if (ot.get_str(1, &type, &type_len))
            op.type.assign(type, type_len);
        auto tensor_ids = [&](uint32_t field, std::vector<uint32_t>* ids) {
            const uint8_t* vp = nullptr;
            uint32_t       vn = 0;
            if (!ot.get_vec(field, &vp, &vn))
                return;
            for (uint32_t i = 0; i < vn; i++) {
                uint32_t id;
                std::memcpy(&id, vp + i * 4, 4);
                ids->push_back(id);
            }
        };
        tensor_ids(4, &op.inputs);
        tensor_ids(5, &op.outputs);
        if (op.type == "Transpose") {
            fb::Table      attrs;
            const uint8_t* vp = nullptr;
            uint32_t       vn = 0;
            if (ot.get_table(8, &attrs) && attrs.get_vec(0, &vp, &vn) && vn <= 8)
                for (uint32_t i = 0; i < vn; i++) {
                    uint32_t axis;
                    std::memcpy(&axis, vp + i * 4, 4);
                    op.permutation.push_back(axis);
                }
        }
        const uint8_t* ep = nullptr;
        uint32_t       en = 0;
        if (ot.get_vec(6, &ep, &en)) {
            uint64_t ebase = (uint64_t)(ep - raw);
            for (uint32_t j = 0; j < en; j++) {
                uint32_t uo;
                std::memcpy(&uo, ep + j * 4, 4);
                uint64_t pos = ebase + (uint64_t)j * 4 + uo;
                if (pos + 4 > raw_n)
                    continue;
                fb::Table et{raw, pos};
                EdgeRef   e;
                scalar_or(et, 0, &e.tensor);
                scalar_or(et, 1, &e.tensor2);
                scalar_or(et, 2, &e.f2);
                scalar_or(et, 3, &e.enable_mask);
                scalar_or(et, 4, &e.int_mask_raw);
                scalar_or(et, 6, &e.core_index);
                scalar_or(et, 8, &e.core_num);

                const uint8_t* rp = nullptr;
                uint32_t       rn = 0;
                if (et.get_vec(5, &rp, &rn)) {
                    // 元素是 24B 记录(reg, tensor, u64 offset, 12B 保留)
                    uint64_t rbase = (uint64_t)(rp - raw);
                    if (rbase + (uint64_t)rn * 24 <= raw_n) {
                        for (uint32_t k = 0; k < rn; k++) {
                            const uint8_t* q = rp + (uint64_t)k * 24;
                            Reloc          rl;
                            std::memcpy(&rl.reg, q, 4);
                            std::memcpy(&rl.tensor, q + 4, 4);
                            std::memcpy(&rl.offset, q + 8, 8);
                            e.relocs.push_back(rl);
                        }
                    }
                }

                uint32_t  cn = e.core_num;
                uint32_t  ci = e.core_index;
                EdgeGroup g;
                if (cn <= 1)
                    g = GRP_A;
                else if (cn == 2)
                    g = ci == 0 ? GRP_B0 : GRP_B1;
                else if (cn == 3)
                    g = ci == 0 ? GRP_C0 : (ci == 1 ? GRP_C1 : GRP_C2);
                else
                    continue;
                op.groups[g].push_back((uint16_t)op.edges.size());
                op.edges.push_back(std::move(e));
            }
        }
        out->ops.push_back(std::move(op));
    }
    out->op_count = (uint32_t)out->ops.size();
}

}  // namespace

int load_model(const void* data, size_t size, Model* out) {
    if (size < 0x18 || std::memcmp(data, "RKNN", 4) != 0)
        return -1;
    const uint8_t* d = (const uint8_t*)data;
    std::memcpy(&out->version, d + 8, 8);
    std::memcpy(&out->data_size, d + 0x10, 8);

    // dsh-009 §1.1: version>=2 时 NN_BG 起点 = model+0x40; 标准 GetRoot
    out->fb_base = out->version >= 2 ? 0x40 : 0x18;
    if (out->fb_base + 4 > size)
        return -2;
    uint32_t root_u = 0;
    std::memcpy(&root_u, d + out->fb_base, 4);
    out->root_off = out->fb_base + root_u;
    if (out->root_off + 4 > size)
        return -2;
    out->nnbg_off      = out->fb_base;
    out->nnbg_root_off = root_u;

    uint64_t joff = 0;
    if (find_json(d, size, &joff)) {
        out->json_off  = joff;
        out->nnbg_size = joff - 8 - out->fb_base;
        scan_json((const char*)(d + joff), size - joff, out);
    } else {
        out->nnbg_size = size - out->fb_base;
    }
    out->raw.assign(d, d + size);

    fb::Table   root{out->raw.data(), out->root_off};
    const char* s;
    uint32_t    slen;
    if (root.get_str(1, &s, &slen) && slen >= 8)
        out->target.assign(s, slen);

    // 根表 f12/f13: 用户面 dtype/layout; f3: attrs(mean/std/rgb2bgr)
    if (root.get_str(12, &s, &slen))
        out->input_cfg_json.assign(s, slen);
    if (root.get_str(13, &s, &slen))
        out->output_cfg_json.assign(s, slen);
    if (root.get_str(3, &s, &slen))
        out->attrs_json.assign(s, slen);
    int lf = parse_layout(out->input_cfg_json);
    if (lf >= 0)
        out->input_user_fmt = lf;
    lf = parse_layout(out->output_cfg_json);
    if (lf >= 0)
        out->output_user_fmt = lf;
    parse_floats(out->attrs_json, "mean", &out->input_mean);
    parse_floats(out->attrs_json, "std", &out->input_std);
    for (auto& v : out->input_std)
        if (v == 0.0f)
            v = 1.0f;
    {
        size_t p = out->attrs_json.find("rgb2bgr");
        if (p != std::string::npos) {
            size_t q = out->attrs_json.find(':', p);
            if (q != std::string::npos) {
                size_t t = out->attrs_json.find_first_not_of(" \t", q + 1);
                if (t != std::string::npos)
                    out->rgb2bgr = out->attrs_json.compare(t, 4, "True") == 0;
            }
        }
    }

    // 根表 f19: {模板池起点(纯权重), internal 尺寸, 0}
    fb::Table f19;
    if (root.get_table(19, &f19)) {
        uint64_t v = 0;
        if (f19.get_scalar(0, &v))
            out->weight_size = v;
        if (f19.get_scalar(1, &v))
            out->internal_size = v;
    }

    std::vector<fb::Table> graphs;
    if (!table_vec(root, 2, &graphs) || graphs.empty())
        return -3;
    const fb::Table graph = graphs[0];

    parse_blobs(*out, root, out);
    parse_tensors(*out, graph, out);
    build_io_maps(out);
    parse_ops(*out, graph, out);
    return 0;
}

}  // namespace rknn
