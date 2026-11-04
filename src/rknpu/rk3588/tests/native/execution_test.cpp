// Production executor, actual models, deterministic fake kernel, failure injection.
#include <unistd.h>

#include <cassert>
#include <cerrno>
#include <cstdarg>
#include <cstring>
#include <fstream>
#include <iterator>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <vector>

#include "emitter.h"
#include "numeric.h"
#include "rknn_api.h"
#include "shell_ctx.h"
#include "tensor.h"
using rknn::Context;
using rknn::Model;
using rknn::TensorRef;
using namespace rknn::detail;

static std::vector<rknn::SubmitArgs> submissions;
static unsigned                      create_id, fail_submit_at;
static bool                          fail_sync;
extern "C" int                       ioctl(int, unsigned long cmd, ...) noexcept {
    va_list ap;
    va_start(ap, cmd);
    void* arg = va_arg(ap, void*);
    va_end(ap);
    switch (cmd & 0xff) {
    case 2: {
        struct Create {
            uint32_t fd, flags;
            uint64_t size, obj, dma, sram;
        };
        auto* p  = (Create*)arg;
        int   fd = (int)syscall(SYS_memfd_create, "rknn-test", 0);
        assert(fd >= 0 && ftruncate(fd, p->size) == 0);
        p->fd  = fd;
        p->obj = ++create_id;
        p->dma = 0x50000000ull + create_id * 0x100000;
        return 0;
    }
    case 4:
        return 0;
    case 5:
        if (fail_sync) {
            errno = EIO;
            return -1;
        }
        return 0;
    case 1: {
        const auto*      p = (const uint8_t*)arg;
        rknn::SubmitArgs a;
        memcpy(&a.flags, p, 4);
        memcpy(&a.timeout_ms, p + 4, 4);
        memcpy(&a.task_start, p + 8, 4);
        memcpy(&a.task_number, p + 12, 4);
        memcpy(&a.task_obj_addr, p + 24, 8);
        memcpy(&a.core_mask, p + 56, 4);
        memcpy(&a.fence_fd, p + 60, 4);
        memcpy(a.subcores.data(), p + 64, 40);
        submissions.push_back(a);
        if (fail_submit_at == submissions.size()) {
            errno = ETIMEDOUT;
            return -1;
        }
        return 0;
    }
    default:
        assert(false);
        return -1;
    }
}

static void load(Context* c, const char* name) {
    std::ifstream        f((std::string(std::getenv("RKNN_MODEL_DIR")) + "/zoo/") + name + ".rknn",
                           std::ios::binary);
    std::vector<uint8_t> raw{std::istreambuf_iterator<char>(f), {}};
    assert(!raw.empty() && !rknn::load_model(raw.data(), raw.size(), &c->model));
    c->iommu_en = 1;
    create_id   = 0;
    assert(!rknn::emit_build(c));
    submissions.clear();
}
static void unload(Context* c) {
    for (auto& g : c->gem)
        assert(!c->drv.mem_destroy(&g));
    for (auto& g : c->extra_out)
        assert(!c->drv.mem_destroy(&g));
}

static void output_test() {
    Context c;
    load(&c, "dualout");
    const auto&  t = c.model.tensors[c.model.output_tensors[0]];
    TensorExtent extent;
    assert(!tensor_extent(t, extent));
    const auto count = extent.logical_elements, storage = extent.storage_elements;
    assert(count == 7840);
    auto* native = (uint16_t*)c.gem[5].map;
    for (uint64_t i = 0; i < storage; i++)
        native[i] = 0xdead;
    for (uint64_t i = 0; i < count; i++)
        native[tensor_offset(t, i)] = (uint16_t)(0x1000 + i);
    auto* cls = (uint16_t*)c.extra_out[0].map;
    for (unsigned i = 0; i < 32; i++)
        cls[i] = (uint16_t)(0x3c00 + i);
    rknn_output out[2] = {};
    out[0].index       = 1;
    out[1].index       = 0;
    assert(!rknn_outputs_get((rknn_context)&c, 2, out, nullptr));
    assert(out[0].size == 64 && out[1].size == 15680);
    assert(!memcmp(out[0].buf, cls, 64));
    auto* flat = (uint16_t*)out[1].buf;
    for (uint64_t i = 0; i < count; i++)
        assert(flat[i] == 0x1000 + i);
    assert(!rknn_outputs_release((rknn_context)&c, 2, out));
    assert(!out[0].buf && !out[1].buf);
    out[0]            = {};
    out[0].index      = 1;
    out[0].want_float = 1;
    assert(!rknn_outputs_get((rknn_context)&c, 1, out, nullptr));
    assert(out[0].size == 128);
    for (unsigned i = 0; i < 32; i++)
        assert(((float*)out[0].buf)[i] == f16_to_f32(cls[i]));
    assert(!rknn_outputs_release((rknn_context)&c, 1, out));
    std::vector<uint8_t> pre(15684, 0xcc);
    out[0]             = {};
    out[0].index       = 0;
    out[0].is_prealloc = 1;
    out[0].buf         = pre.data();
    out[0].size        = 15680;
    out[1]             = {};
    out[1].index       = 1;
    out[1].is_prealloc = 1;
    out[1].buf         = pre.data();
    out[1].size        = 1;
    assert(rknn_outputs_get((rknn_context)&c, 2, out, nullptr) == -5);
    for (auto b : pre)
        assert(b == 0xcc);  // validation is atomic
    assert(!rknn_outputs_get((rknn_context)&c, 1, out, nullptr));
    for (unsigned i = 15680; i < pre.size(); i++)
        assert(pre[i] == 0xcc);
    out[1] = out[0];
    assert(rknn_outputs_get((rknn_context)&c, 2, out, nullptr) == -5);
    out[0].index = 2;
    assert(rknn_outputs_get((rknn_context)&c, 1, out, nullptr) == -5);
    out[0].index = 0;
    fail_sync    = true;
    assert(rknn_outputs_get((rknn_context)&c, 1, out, nullptr) == -EIO);
    fail_sync = false;
    unload(&c);
}

static void reshape_transpose_test() {
    Context c;
    load(&c, "shufflenet");
    const auto& op = c.model.ops[116];
    assert(op.permutation == std::vector<uint32_t>({1, 0, 2, 3}));
    const auto&  src = c.model.tensors[op.inputs[0]];
    auto*        raw = (uint16_t*)((uint8_t*)c.gem[3].map + src.internal_off);
    TensorExtent extent;
    assert(!tensor_extent(src, extent));
    const auto count = extent.logical_elements, storage = extent.storage_elements;
    assert(storage == 9984 && count == 9408);
    for (uint64_t i = 0; i < storage; i++)
        raw[i] = 0xffff;
    // Source: N=2,C=96,H=W=7. Distinct value per logical element.
    for (uint64_t i = 0; i < count; i++)
        raw[tensor_offset(src, i)] = (uint16_t)(0x1000 + i);
    assert(!execute_cpu_op(c, op));
    assert(!execute_cpu_op(c, c.model.ops[117]));
    const auto& dst = c.model.tensors[c.model.ops[117].outputs[0]];
    auto*       out = (uint16_t*)((uint8_t*)c.gem[3].map + dst.internal_off);
    for (uint64_t ch = 0; ch < 192; ch++)
        for (uint64_t pos = 0; pos < 49; pos++) {
            uint64_t source = ((ch % 2) * 96 + ch / 2) * 49 + pos;
            assert(out[(ch / 8 * 52 + pos) * 8 + ch % 8] == 0x1000 + source);
        }
    for (unsigned block = 0; block < 24; block++)
        for (unsigned pos = 49; pos < 52; pos++)
            for (unsigned ch = 0; ch < 8; ch++)
                assert(out[(block * 52 + pos) * 8 + ch] == 0);
    auto invalid        = op;
    invalid.permutation = {0, 0, 2, 3};
    assert(execute_cpu_op(c, invalid) == -6);
    invalid           = op;
    invalid.inputs[0] = UINT32_MAX;
    assert(execute_cpu_op(c, invalid) == -5);
    invalid      = op;
    invalid.type = "MissingCPUOp";
    assert(execute_cpu_op(c, invalid) == -6);
    unload(&c);
}

static void quantized_output_test() {
    Context   c;
    TensorRef t;
    t.kind          = 2;
    t.dtype_code    = 3;
    t.scale         = 0.25f;
    t.zp            = -2;
    t.ndim          = 4;
    t.native_ndim   = 5;
    t.size          = 32;
    uint32_t dims[] = {1, 3, 2, 2}, native[] = {1, 1, 2, 2, 8};
    memcpy(t.dims, dims, sizeof(dims));
    memcpy(t.native_dims, native, sizeof(native));
    c.model.tensors        = {t};
    c.model.output_num     = 1;
    c.model.output_tensors = {0};
    std::vector<int8_t> packed(32, 99);
    c.gem[5].map  = packed.data();
    c.gem[5].size = packed.size();
    for (unsigned i = 0; i < 12; i++)
        packed[tensor_offset(t, i)] = (int8_t)((int)i - 6);
    rknn_output out = {};
    out.want_float  = 1;
    assert(!rknn_outputs_get((rknn_context)&c, 1, &out, nullptr));
    assert(out.size == 48);
    for (unsigned i = 0; i < 12; i++)
        assert(((float*)out.buf)[i] == ((int)i - 4) * 0.25f);
    assert(!rknn_outputs_release((rknn_context)&c, 1, &out));
    out = {};
    assert(!rknn_outputs_get((rknn_context)&c, 1, &out, nullptr));
    assert(out.size == 12);
    for (unsigned i = 0; i < 12; i++)
        assert(((int8_t*)out.buf)[i] == (int)i - 6);
    assert(!rknn_outputs_release((rknn_context)&c, 1, &out));
}

static void execution_test(const char* name, unsigned expected) {
    Context c;
    load(&c, name);
    assert(!rknn_run((rknn_context)&c, nullptr));
    assert(submissions.size() == expected);
    unsigned preload = 0, total = 0;
    for (const auto& a : submissions) {
        total += a.task_number;
        if (a.flags == 1) {
            preload++;
            assert(a.task_number == 6);
        } else
            assert(a.flags == 5);
    }
    assert(total == c.rows_a);
    assert(preload == (std::string(name) == "mbv3s" ? 28 : 0));
    if (expected > 1) {
        submissions.clear();
        fail_submit_at = 2;
        assert(rknn_run((rknn_context)&c, nullptr) == -ETIMEDOUT);
        assert(submissions.size() == 2);
        fail_submit_at = 0;
        submissions.clear();
        fail_sync = true;
        assert(rknn_run((rknn_context)&c, nullptr) == -EIO);
        fail_sync = false;
    }
    unload(&c);
}
int main() {
    output_test();
    reshape_transpose_test();
    quantized_output_test();
    execution_test("mbv3s", 57);
    execution_test("shufflenet", 17);
    execution_test("dualout", 2);
    execution_test("resnet18", 1);
    puts(
        "PASS: real-model segments, CPU transpose/reshape + spatial padding, multi-output "
        "raw/float/index/prealloc, error propagation");
}
