// SPDX-License-Identifier: MIT
/* 开源 librknnrt 替代引擎 — 模型/容器层
 *
 * .rknn 1.5.0 容器布局(实证见 document/notes/rknn/001-004 与 scripts/rknn_dump.py):
 *   0x00  外层头: "RKNN" magic + u64 version + u64 data_size (共 0x18)
 *   0x18  (version&0xFF)>1 时再跳 40B 嵌套头
 *   0x40  NN_BG 起点(version>=2; FlatBuffers, schema 见 dsh-009)
 *   尾部  明文 JSON 段(前面 8B 是长度), 元数据: io 张量/单 NNBG 节点
 */
#pragma once
#include <cstdint>
#include <string>
#include <vector>

namespace rknn {

struct TensorAttr {
    std::string name;
    uint32_t    dims[16] = {0};
    uint32_t    ndim     = 0;
    uint32_t    size     = 0;  // 字节
    uint32_t    n_elems  = 0;
    int         type     = 1;  // rknn_tensor_type, 1=FLOAT16(本模型类)
    int         fmt      = 1;  // rknn_tensor_format, 1=NHWC
};

/* ---- NN_BG schema 对象(dsh-009; 字段号到语义的映射只在这里出现) ---- */

enum EdgeGroup {
    GRP_A = 0,
    GRP_B0,
    GRP_B1,
    GRP_C0,
    GRP_C1,
    GRP_C2,
    GRP_COUNT,
};

struct BlobRef {
    uint64_t data_off = 0;  // raw 内偏移; size=0 表示空 blob
    uint32_t size     = 0;
    uint64_t pack_off = 0;  // gem1 内偏移(按 blob 下标顺序 64B 对齐)
};

struct TensorRef {
    std::string name;                // f5: NNBG 张量名(JSON url 按名匹配用)
    uint8_t     kind           = 0;  // f2: 1=input 2=output 3=activation 4=weight 7=模板
    uint8_t     dtype_code     = 0;  // f0: 10=float16 3=int8(实测; 0x104c 回填值由此查表)
    int32_t     zp             = 0;  // f11[0]: 量化 zero_point(不对称 int8; fp 模型缺省 0)
    float       scale          = 0.0f;  // f10[0][0]: 量化 scale(f32 位型)
    float       qmin           = 0.0f;  // f8[0][0]: 量化 min
    float       qmax           = 0.0f;  // f9[0][0]: 量化 max
    uint32_t    size           = 0;     // f12 分配字节数
    uint32_t    internal_off   = 0;     // f13: kind=3 在 internal GEM 内的偏移
    uint32_t    ndim           = 0;     // f4 逻辑 shape 维数(NCHW)
    uint32_t    dims[8]        = {0};   // f4 逻辑 shape
    uint32_t    native_ndim    = 0;     // f3 内部 shape 维数(NC1HWC2)
    uint32_t    native_dims[8] = {0};
    bool        has_f20  = false;  // f20 在场: 8bit 用户输入走原始字节域(vendor 实测)
    int32_t     blob     = -1;     // f18: root.f4 下标
    uint64_t    gem1_off = 0;      // 由 blob 反推, 省去每次再查
};

/* edge.f5 的 24B 记录: {reg, tensor, u64 offset, ...} */
struct Reloc {
    uint32_t reg    = 0;
    uint32_t tensor = 0;
    uint64_t offset = 0;
};

struct EdgeRef {
    uint32_t           tensor       = 0;  // f0 主模板 tensor
    uint32_t           tensor2      = 0;  // f1 次模板(0=无; mbv3s 的 HardSigmoid 常量)
    uint32_t           f2           = 0;  // f2 模板类别(4=Concat copy, 32768=weight/CBUF)
    uint32_t           enable_mask  = 0;  // f3
    uint32_t           int_mask_raw = 0;  // f4
    uint32_t           core_index   = 0;  // f6
    uint32_t           core_num     = 0;  // f8
    std::vector<Reloc> relocs;            // f5
};

struct OpRef {
    std::string           type;               // f1: 区分 CPU Reshape 与 NPU 模板
    std::vector<uint32_t> inputs, outputs;    // f4/f5: 张量下标,不是模板下标
    std::vector<uint32_t> permutation;        // Transpose: f8 属性表的 f0
    std::vector<EdgeRef>  edges;              // f6 顺序
    std::vector<uint16_t> groups[GRP_COUNT];  // 按 f8/f6 路由后的 edge 下标
};

struct Model {
    // 容器
    std::vector<uint8_t> raw;
    uint64_t             version = 0, data_size = 0;
    uint64_t             nnbg_off = 0, nnbg_size = 0;  // nnbg_off = FlatBuffers 基址(0x40)
    uint64_t             json_off = 0;
    std::string          target;  // 根表 f1, 如 "RKNPU v2"

    // NN_BG 根定位(dsh-009: data+0x40 的 u32 uoffset)
    uint64_t fb_base       = 0;
    uint64_t root_off      = 0;
    uint64_t nnbg_vt_off   = 0;
    uint64_t nnbg_root_off = 0;

    // JSON 元数据(最小解析)
    uint32_t                input_num = 0, output_num = 0;
    std::vector<TensorAttr> tensors_json;

    // 根表 f3/f12/f13: 用户面 IO 配置(与 NN_BG 图内张量互相印证)
    std::string attrs_json;           // f3: attrs/quant_tab/py-dict 文本
    std::string input_cfg_json;       // f12: {"input": {"dtype": "...", "layout": "..."}}
    std::string output_cfg_json;      // f13: {"output": {...}}
    int         input_user_fmt  = 1;  // 用户面 layout, 1=NHWC / 0=NCHW
    int         output_user_fmt = 3;  // 根表 f13 layout(0=NCHW/1=NHWC); 无 f13 时旧默认 3
    std::vector<float> input_mean;    // attrs.input.mean, 长度 = C
    std::vector<float> input_std;     // attrs.input.std
    bool               rgb2bgr = false;

    // NN_BG 图(schema 层填充)
    uint32_t op_count = 0;
    int input_tensor = 0, output_tensor = 0;  // kind=1/2 的首个张量下标(兼容旧路径)
    // JSON 声明序 -> NNBG 张量下标: 输入[i]=tensors_json[i],
    // 输出[i]=tensors_json[input_num+i]; 名字(JSON url == tensor f5)优先,
    // 名字缺失时退回图内 kind 顺序。
    std::vector<int>       input_tensors;
    std::vector<int>       output_tensors;
    uint64_t               internal_size = 0;  // 根表 f19[1]
    uint64_t               weight_size   = 0;  // 根表 f19[0]: gem1 模板池起点(纯权重)
    uint64_t               gem1_size     = 0;  // 563 blob 顺序打包总长
    std::vector<BlobRef>   blobs;
    std::vector<TensorRef> tensors;
    std::vector<OpRef>     ops;
};

// 解析容器 + NN_BG; 成功返回 0
int load_model(const void* data, size_t size, Model* out);

}  // namespace rknn
