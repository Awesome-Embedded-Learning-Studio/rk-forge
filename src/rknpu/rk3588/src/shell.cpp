// SPDX-License-Identifier: MIT
/* C ABI 壳: rknn_* 公开接口(drop-in librknnrt 替代)
 *
 * 生命周期契约实证于 dyn/ 装置(run3/run7):init 探针→6×MEM_CREATE→权重搬运
 * (110×MEM_SYNC)→装配→run 1×SUBMIT(A 方案 246 行)→destroy 6×MEM_DESTROY。
 *
 * dsh-011:补齐 rknn_query 全表面与 rknn_inputs_set/rknn_outputs_get 的
 * 用户格式变换。变换规则全部按 dyn/io_probe 对 vendor 1.5.0 的差分实测:
 *   - NHWC 输入: float32/float16/uint8 → (x-mean[c])/std[c]; int8 恒直拷,
 *     uint8 仅当张量带 f20(直接量化输入)时直拷, 否则按数值 normalize+quantize
 *   - int8 目标: 固定点乘子(16bit)+ shift; 分子 float 用 fma, 商在 double 里
 *     做 nearest-even, 再 clamp 到 [-128,127](0x28dbcc 的实测等价)
 *   - fp16 目标: IEEE binary16 round-to-nearest-even
 *   - 输入 GEM 是 NC1HWC2(带 C2 padding); C=3 时退化成 NHWC, 与 vendor dump 一致
 *   - 非 NHWC 的 in.fmt 对这两个模型 vendor 会报错但返回 0 且不写 GEM,
 *     这里同样不写(保持字节可比); 模型声明 NCHW 时才走 NCHW 变换
 *
 * dsh-012:多输出 query 表面。输出张量按 JSON norm_tensor 声明序选, 再按
 * NNBG tensor f5 名字匹配; q2/q11/q9 三种变体各自决定 fmt 与维度:
 *   q2  用户面 f13 layout; ndim<4 → UNDEFINED
 *   q11 NHWC; ndim==4 重排成 [N,H,W,C]
 *   q9  C1>1 报五维 native shape + f12 补齐字节; C1==1 塌缩成 q11
 * 输入 q1/q8/q10 仍为同一份用户面 NHWC 属性。
 */
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>

#include "emitter.h"
#include "execution.h"
#include "numeric.h"
#include "rknn_api.h"
#include "shell_ctx.h"
#include "tensor.h"


using rknn::Context;
using rknn::Model;
using rknn::TensorRef;
using namespace rknn::detail;

/* ---------------- 小工具: f32 <-> f16, 量化固定点 ---------------- */

struct QParam {
    int32_t  mult   = 0;
    uint32_t shift  = 0;
    int32_t  offset = 0;
};

/* vendor FUN_00317418: 把 f 表示成 mult / 2^shift, 目标 16bit 有符号 */
static QParam make_qparam(float inv, double inv_d, int32_t zp, float mean) {
    QParam q;
    q.offset = (int32_t)lrint((double)zp - inv_d * (double)mean);
    if (inv == 0.0f)
        return q;
    float    lg    = log2f(fabsf(inv));
    int      e     = (int)lg;  // vendor: (int)((int)log2 + 1.0)
    uint32_t shift = (uint32_t)((16 - 1) - (e + 1));
    long     m     = lrint((double)(1L << (shift & 0x3f)) * (double)inv);
    int32_t  mm    = (int32_t)m;
    if (mm == (1 << 15) || (long)mm < -(1L << 15)) {
        shift -= 1;
        mm >>= 1;
    }
    q.mult  = mm;
    q.shift = shift;
    return q;
}

static inline int32_t shl32(int32_t v, uint32_t s) {
    return (int32_t)((uint32_t)v << (s & 31));
}

/* 返回已取整(nearest-even)并 clamp 的量化值 */
static int quant_i8(float x, const QParam& q, int32_t zp_unused) {
    (void)zp_unused;
    // 对齐 vendor 0x28dbcc: fmadd(s1=x, s3=mult, s0=offset<<shift) 得到 float 分子,
    // 然后转 double 除以 2^shift, frintx(double, nearest-even), 转回 float,
    // fminnm(127)/fmaxnm(-128), 最后 fcvtzs 截断。
    volatile float  off = (float)shl32(q.offset, q.shift);
    volatile float  m   = (float)q.mult;
    volatile float  num = __builtin_fmaf(m, x, off);
    volatile double den = (double)(int64_t)(1LL << (q.shift & 0x3f));
    double          qd  = (double)num / den;
    double          rd  = nearbyint(qd);
    float           rf  = (float)rd;
    rf                  = fminf(rf, 127.0f);
    rf                  = fmaxf(rf, -128.0f);
    return (int)rf;
}

static uint32_t type_bytes(rknn_tensor_type t) {
    switch (t) {
    case RKNN_TENSOR_FLOAT32:
        return 4;
    case RKNN_TENSOR_FLOAT16:
        return 2;
    case RKNN_TENSOR_INT8:
    case RKNN_TENSOR_UINT8:
        return 1;
    case RKNN_TENSOR_INT16:
    case RKNN_TENSOR_UINT16:
        return 2;
    case RKNN_TENSOR_INT32:
    case RKNN_TENSOR_UINT32:
        return 4;
    case RKNN_TENSOR_INT64:
        return 8;
    default:
        return 0;
    }
}

static const char* tensor_name(const Model& m, const TensorRef& t, uint32_t idx, bool input) {
    if (!t.name.empty())
        return t.name.c_str();
    size_t ji = input ? idx : (size_t)m.input_num + idx;
    if (ji < m.tensors_json.size() && !m.tensors_json[ji].name.empty())
        return m.tensors_json[ji].name.c_str();
    return input ? "input" : "output";
}

/* 输出属性按查询变体分流:
 *   q2  OUTPUT_ATTR          = 用户面 layout(f13); ndim<4 时 UNDEFINED
 *   q11 NATIVE_NHWC_OUTPUT   = NHWC; ndim==4 时逻辑序重排
 *   q9  NATIVE_NC1HWC2_OUTPUT= C1>1 报 5 维 native shape + f12 补齐字节;
 *                              C1==1 塌缩成 q11 形状; ndim<4 全部塌缩成 q2
 */
static int fill_attr(const Context* c, uint32_t idx, bool input, rknn_query_cmd cmd,
                     rknn_tensor_attr* a) {
    const Model& m  = c->model;
    int          ti = io_tensor_index(m, idx, input);
    if (ti < 0)
        return -5;
    const TensorRef& t       = m.tensors[ti];
    uint32_t         logical = shape_elems(t);
    if (!logical) {
        size_t ji = input ? idx : (size_t)m.input_num + idx;
        if (ji < m.tensors_json.size())
            logical = m.tensors_json[ji].n_elems;
    }
    uint32_t eb = dtype_bytes(t.dtype_code);

    a->type     = t.dtype_code == 3 ? RKNN_TENSOR_INT8 : RKNN_TENSOR_FLOAT16;
    a->qnt_type = RKNN_TENSOR_QNT_AFFINE_ASYMMETRIC;
    a->fl       = 0;
    a->zp       = t.zp;
    a->scale    = t.scale;
    a->n_elems  = logical;
    a->size     = logical * eb;
    a->n_dims   = t.ndim;
    for (uint32_t i = 0; i < RKNN_MAX_DIMS; i++)
        a->dims[i] = 0;
    for (uint32_t i = 0; i < t.ndim && i < RKNN_MAX_DIMS; i++)
        a->dims[i] = t.dims[i];
    snprintf(a->name, sizeof(a->name), "%s", tensor_name(m, t, idx, input));

    if (input) {
        a->fmt = (rknn_tensor_format)m.input_user_fmt;
        if (m.input_user_fmt == RKNN_TENSOR_NHWC && t.ndim == 4) {
            a->dims[0] = t.dims[0];
            a->dims[1] = t.dims[2];
            a->dims[2] = t.dims[3];
            a->dims[3] = t.dims[1];
        }
        return 0;
    }

    // 低维输出(如 [1,1000])三个变体都塌缩成 UNDEFINED + 逻辑 shape。
    if (t.ndim < 4) {
        a->fmt = RKNN_TENSOR_UNDEFINED;
        return 0;
    }

    if (cmd == RKNN_QUERY_OUTPUT_ATTR) {
        a->fmt = (rknn_tensor_format)m.output_user_fmt;
        return 0;
    }
    if (cmd == RKNN_QUERY_NATIVE_NHWC_OUTPUT_ATTR) {
        a->fmt = RKNN_TENSOR_NHWC;
        if (t.ndim == 4) {
            a->dims[0] = t.dims[0];
            a->dims[1] = t.dims[2];
            a->dims[2] = t.dims[3];
            a->dims[3] = t.dims[1];
        }
        return 0;
    }

    // NC1HWC2: C1>1 才是真的五维 native shape; C==C2(不拆)时塌缩成 NHWC。
    uint32_t c1 = t.native_ndim >= 5 ? t.native_dims[1] : 1;
    if (c1 > 1 && t.native_ndim >= 5) {
        a->fmt    = RKNN_TENSOR_NC1HWC2;
        a->n_dims = t.native_ndim;
        for (uint32_t i = 0; i < RKNN_MAX_DIMS; i++)
            a->dims[i] = 0;
        for (uint32_t i = 0; i < t.native_ndim && i < RKNN_MAX_DIMS; i++)
            a->dims[i] = t.native_dims[i];
        // vendor 报的是 f12 分配字节(含 C2 补齐), 不是逻辑连乘。
        a->size    = t.size;
        a->n_elems = eb ? t.size / eb : logical;
        return 0;
    }
    a->fmt = RKNN_TENSOR_NHWC;
    if (t.ndim == 4) {
        a->dims[0] = t.dims[0];
        a->dims[1] = t.dims[2];
        a->dims[2] = t.dims[3];
        a->dims[3] = t.dims[1];
    }
    return 0;
}

/* ---------------- C ABI ---------------- */

extern "C" int rknn_init(rknn_context* context, void* model, uint32_t size, uint32_t flag,
                         rknn_init_extend* ext) {
    (void)flag;
    (void)ext;
    if (!context || !model)
        return -1;
    auto c = std::make_unique<Context>();
    int  r = rknn::load_model(model, size, &c->model);
    if (r != 0)
        return r;
    if ((r = c->drv.open()) != 0)
        return r;
    uint32_t hardware_version = 0;
    if ((r = c->drv.get_hw_version(&hardware_version)) != 0)
        return r;
    if ((r = c->drv.get_drv_version(&c->drv_version)) != 0)
        return r;
    if ((r = c->drv.get_iommu_en(&c->iommu_en)) != 0)
        return r;
    if (c->drv_version < 0x2ba)
        return -6;
    if ((r = rknn::emit_build(c.get())) != 0)
        return r;
    *context = reinterpret_cast<rknn_context>(c.release());
    return 0;
}

extern "C" int rknn_destroy(rknn_context ctx) {
    Context* c = (Context*)ctx;
    if (!c)
        return -1;
    delete c;
    return 0;
}

extern "C" int rknn_query(rknn_context ctx, rknn_query_cmd cmd, void* info, uint32_t size) {
    Context* c = (Context*)ctx;
    if (!c || !info)
        return -1;
    switch (cmd) {
    case RKNN_QUERY_IN_OUT_NUM: {
        auto* io     = (rknn_input_output_num*)info;
        io->n_input  = c->model.input_num;
        io->n_output = c->model.output_num;
        return 0;
    }
    case RKNN_QUERY_INPUT_ATTR:
    case RKNN_QUERY_NATIVE_NC1HWC2_INPUT_ATTR:
    case RKNN_QUERY_NATIVE_NHWC_INPUT_ATTR: {
        auto* attr = (rknn_tensor_attr*)info;
        return fill_attr(c, attr->index, true, cmd, attr);
    }
    case RKNN_QUERY_OUTPUT_ATTR:
    case RKNN_QUERY_NATIVE_NC1HWC2_OUTPUT_ATTR:
    case RKNN_QUERY_NATIVE_NHWC_OUTPUT_ATTR: {
        auto* attr = (rknn_tensor_attr*)info;
        return fill_attr(c, attr->index, false, cmd, attr);
    }
    case RKNN_QUERY_PERF_DETAIL: {
        auto* pd = (rknn_perf_detail*)info;
        (void)size;
        pd->perf_data = nullptr;
        pd->data_len  = 0;
        return 0;
    }
    case RKNN_QUERY_PERF_RUN: {
        auto* pr = (rknn_perf_run*)info;
        (void)size;
        pr->run_duration = 0;
        return 0;
    }
    case RKNN_QUERY_SDK_VERSION: {
        auto* v = (rknn_sdk_version*)info;
        (void)size;
        snprintf(v->api_version, sizeof(v->api_version), "%s",
                 "1.5.0 (e6fe0c678@2023-05-25T08:09:20)");
        uint32_t d = c->drv_version;
        snprintf(v->drv_version, sizeof(v->drv_version), "%u.%u.%u", d / 10000, (d / 100) % 100,
                 d % 100);
        return 0;
    }
    case RKNN_QUERY_MEM_SIZE: {
        auto*    ms  = (rknn_mem_size*)info;
        uint64_t dma = 0;
        for (const auto& g : c->gem)
            dma += g.size;
        for (const auto& g : c->extra_out)
            dma += g.size;
        ms->total_weight_size =
            (uint32_t)(c->model.weight_size ? c->model.weight_size : c->model.gem1_size);
        ms->total_internal_size      = (uint32_t)c->model.internal_size;
        ms->total_dma_allocated_size = dma;
        ms->total_sram_size          = 0;
        ms->free_sram_size           = 0;
        memset(ms->reserved, 0, sizeof(ms->reserved));
        return 0;
    }
    case RKNN_QUERY_CUSTOM_STRING: {
        auto* cs = (rknn_custom_string*)info;
        memset(cs->string, 0, sizeof(cs->string));
        return 0;
    }
    case RKNN_QUERY_DEVICE_MEM_INFO:
        return -1;
    case RKNN_QUERY_INPUT_DYNAMIC_RANGE:
    case RKNN_QUERY_CURRENT_INPUT_ATTR:
    case RKNN_QUERY_CURRENT_OUTPUT_ATTR:
        return -6;  // 静态模型: vendor 返回 MODEL_INVALID
    default:
        return -1;
    }
}

/* 用户 NHWC/NCHW/NC1HWC2 元素 → native NC1HWC2 元素 */
static size_t user_index_to_native(const TensorRef& t, const TensorRef& nt, rknn_tensor_format fmt,
                                   uint32_t n, uint32_t c, uint32_t h, uint32_t w) {
    uint32_t C = t.ndim > 1 ? t.dims[1] : 1;
    uint32_t H = t.ndim > 2 ? t.dims[2] : 1;
    uint32_t W = t.ndim > 3 ? t.dims[3] : 1;
    (void)C;
    (void)H;
    (void)W;
    if (fmt == RKNN_TENSOR_NHWC || fmt == RKNN_TENSOR_UNDEFINED) {
        // 先按 NHWC 读, 再打包成 NC1HWC2
        uint32_t C1 = nt.native_ndim >= 5 ? nt.native_dims[1] : 1;
        uint32_t C2 = nt.native_ndim >= 5 ? nt.native_dims[4] : (t.ndim > 1 ? t.dims[1] : 1);
        if (!C1)
            C1 = 1;
        if (!C2)
            C2 = t.ndim > 1 ? t.dims[1] : 1;
        uint32_t hh = t.ndim > 2 ? t.dims[2] : 1;
        uint32_t ww = t.ndim > 3 ? t.dims[3] : 1;
        (void)hh;
        (void)ww;
        size_t src = ((size_t)n * hh * ww + (size_t)h * ww + w) * C + c;
        size_t dst = ((((size_t)n * C1 + c / C2) * hh + h) * ww + w) * C2 + (c % C2);
        return (size_t)(uint32_t)src | ((size_t)(uint32_t)dst << 32);
    }
    if (fmt == RKNN_TENSOR_NCHW) {
        uint32_t C1 = nt.native_ndim >= 5 ? nt.native_dims[1] : 1;
        uint32_t C2 = nt.native_ndim >= 5 ? nt.native_dims[4] : (t.ndim > 1 ? t.dims[1] : 1);
        if (!C1)
            C1 = 1;
        if (!C2)
            C2 = t.ndim > 1 ? t.dims[1] : 1;
        uint32_t hh  = t.ndim > 2 ? t.dims[2] : 1;
        uint32_t ww  = t.ndim > 3 ? t.dims[3] : 1;
        size_t   src = (((size_t)n * C + c) * hh + h) * ww + w;
        size_t   dst = ((((size_t)n * C1 + c / C2) * hh + h) * ww + w) * C2 + (c % C2);
        return (size_t)(uint32_t)src | ((size_t)(uint32_t)dst << 32);
    }
    // NC1HWC2 源: 假设与 native 同布局
    uint32_t C1  = nt.native_ndim >= 5 ? nt.native_dims[1] : 1;
    uint32_t C2  = nt.native_ndim >= 5 ? nt.native_dims[4] : 1;
    uint32_t hh  = t.ndim > 2 ? t.dims[2] : 1;
    uint32_t ww  = t.ndim > 3 ? t.dims[3] : 1;
    size_t   idx = ((((size_t)n * C1 + c / C2) * hh + h) * ww + w) * C2 + (c % C2);
    return idx | (idx << 32);
}

static int inputs_set_one(Context* c, const rknn_input& in) {
    const Model& m  = c->model;
    int          ti = m.input_tensor;
    if (ti < 0 || (size_t)ti >= m.tensors.size())
        return -5;
    if (in.index != 0 || !in.buf)
        return -5;
    const TensorRef& t       = m.tensors[ti];
    uint32_t         n_elems = shape_elems(t);
    uint32_t         tb      = type_bytes(in.type);
    if (!n_elems || !tb)
        return -5;
    uint64_t expect = (uint64_t)n_elems * tb;
    if (in.size < expect)
        return -5;

    auto& g = c->buffer(rknn::BufferSlot::Input);
    if (!g.map)
        return -1;
    uint64_t native_size = (uint64_t)n_elems * dtype_bytes(t.dtype_code);

    if (in.pass_through) {
        uint64_t n = native_size < g.size ? native_size : g.size;
        memcpy(g.map, in.buf, n);
        c->drv.mem_sync(g, 0, g.size, rknn::SyncDirection::ToDevice);
        return 0;
    }

    // 这两个模型 vendor 只接受与输入 normalize 配置一致的 layout;
    // 不一致时打印错误但返回 0 且不写 GEM(实测 fmt=0/2/3 均如此)。
    if ((int)in.fmt != m.input_user_fmt)
        return 0;

    // 8bit -> int8: int8 直拷; uint8 仅在张量带 f20(直接量化输入)时直拷,
    // 否则和 float 一样走 normalize+quantize(实测 C=2/8/16 模型)
    if (t.dtype_code == 3 &&
        (in.type == RKNN_TENSOR_INT8 || (in.type == RKNN_TENSOR_UINT8 && t.has_f20))) {
        uint64_t n = native_size < g.size ? native_size : g.size;
        memcpy(g.map, in.buf, n);
        c->drv.mem_sync(g, 0, g.size, rknn::SyncDirection::ToDevice);
        return 0;
    }
    // int8 -> fp16 不支持: 同 vendor, 不写 GEM 返回 0
    if (t.dtype_code != 3 && in.type == RKNN_TENSOR_INT8)
        return 0;

    uint32_t            N = t.ndim > 0 ? t.dims[0] : 1;
    uint32_t            C = t.ndim > 1 ? t.dims[1] : 1;
    uint32_t            H = t.ndim > 2 ? t.dims[2] : 1;
    uint32_t            W = t.ndim > 3 ? t.dims[3] : 1;
    std::vector<QParam> qp(C);
    if (t.dtype_code == 3) {
        float scale = t.scale;
        if (scale == 0.0f) {
            float range = t.qmax - t.qmin;
            scale       = range != 0.0f ? range / 255.0f : 1.0f;
        }
        for (uint32_t k = 0; k < C; k++) {
            float  mean  = k < m.input_mean.size() ? m.input_mean[k] : 0.0f;
            float  std   = k < m.input_std.size() ? m.input_std[k] : 1.0f;
            double inv_d = (1.0 / (double)std) * (1.0 / (double)scale);
            qp[k]        = make_qparam((float)inv_d, inv_d, t.zp, mean);
        }
    }

    uint8_t* dst = (uint8_t*)g.map;
    uint8_t* src = (uint8_t*)in.buf;
    for (uint32_t n = 0; n < N; n++) {
        for (uint32_t h = 0; h < H; h++) {
            for (uint32_t w = 0; w < W; w++) {
                for (uint32_t ch = 0; ch < C; ch++) {
                    uint32_t cch    = ch;
                    size_t   packed = user_index_to_native(t, t, in.fmt, n, ch, h, w);
                    size_t   si     = (size_t)(uint32_t)packed;
                    size_t   di     = (size_t)(uint32_t)(packed >> 32);
                    float    x      = 0.0f;
                    switch (in.type) {
                    case RKNN_TENSOR_FLOAT32: {
                        float v;
                        memcpy(&v, src + si * 4, 4);
                        x = v;
                        break;
                    }
                    case RKNN_TENSOR_FLOAT16: {
                        uint16_t v;
                        memcpy(&v, src + si * 2, 2);
                        x = f16_to_f32(v);
                        break;
                    }
                    case RKNN_TENSOR_UINT8:
                        x = (float)src[si];
                        break;
                    default:
                        return -5;
                    }
                    float mean = cch < m.input_mean.size() ? m.input_mean[cch] : 0.0f;
                    float std  = cch < m.input_std.size() ? m.input_std[cch] : 1.0f;
                    if (t.dtype_code == 3) {
                        // vendor 固定点直接吃原始 x: mult/offset 已含 1/std 与 mean
                        dst[di] = (uint8_t)(int8_t)quant_i8(x, qp[cch], t.zp);
                    } else {
                        float    y     = (x - mean) / std;
                        uint16_t hbits = f32_to_f16(y);
                        memcpy(dst + di * 2, &hbits, 2);
                    }
                }
            }
        }
    }
    return c->drv.mem_sync(g, 0, g.size, rknn::SyncDirection::ToDevice);
}

extern "C" int rknn_inputs_set(rknn_context ctx, uint32_t n_inputs, rknn_input inputs[]) {
    Context* c = (Context*)ctx;
    if (!c || !inputs)
        return -1;
    if (n_inputs != 1)
        return -5;
    return inputs_set_one(c, inputs[0]);
}

extern "C" int rknn_run(rknn_context ctx, rknn_run_extend* extend) {
    (void)extend;
    auto* context = reinterpret_cast<Context*>(ctx);
    return context ? rknn::detail::execute_graph(*context) : -1;
}

extern "C" int rknn_outputs_get(rknn_context ctx, uint32_t count, rknn_output outputs[],
                                rknn_output_extend* extend) {
    (void)extend;
    auto* context = reinterpret_cast<Context*>(ctx);
    if (!context || !outputs)
        return -1;
    return rknn::detail::get_outputs(*context, std::span{outputs, count});
}

extern "C" int rknn_set_core_mask(rknn_context ctx, rknn_core_mask mask) {
    Context* c = (Context*)ctx;
    if (!c)
        return -1;
    if (mask > 7 || mask == 5 || mask == 6)
        return -1;
    c->core_mask = (uint32_t)mask;
    return 0;
}

extern "C" int rknn_outputs_release(rknn_context ctx, uint32_t n_outputs, rknn_output outputs[]) {
    Context* c = (Context*)ctx;
    if (!c)
        return -1;
    for (uint32_t i = 0; i < n_outputs; i++)
        if (!outputs[i].is_prealloc && outputs[i].buf) {
            free(outputs[i].buf);
            outputs[i].buf = nullptr;
        }
    return 0;
}
