// 实际生产输出函数 + 已采集真板 internal 数据,不需要 NPU。
#include <cassert>
#include <cstdarg>
#include <cstring>
#include <fstream>
#include <iterator>
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

struct SyncSeen {
    uint32_t flags, reserved;
    uint64_t obj, offset, size;
};
static std::vector<SyncSeen> seen;
static int                   sync_errno;
static uint64_t              destroyed;
extern "C" int               ioctl(int, unsigned long cmd, ...) noexcept {
    va_list ap;
    va_start(ap, cmd);
    void* arg = va_arg(ap, void*);
    va_end(ap);
    if ((cmd & 0xff) == 5) {
        seen.push_back(*(SyncSeen*)arg);
        if (sync_errno) {
            errno = sync_errno;
            return -1;
        }
    } else if ((cmd & 0xff) == 4) {
        memcpy(&destroyed, (uint8_t*)arg + 8, 8);
    } else {
        assert(false);
    }
    return 0;
}
static std::vector<uint8_t> read_file(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    assert(f.good());
    return {std::istreambuf_iterator<char>(f), {}};
}
static Model model_file(const char* path) {
    auto  b = read_file(path);
    Model m;
    assert(rknn::load_model(b.data(), b.size(), &m) == 0);
    return m;
}
static int materialize_outputs(Context* c) {
    for (const auto& op : c->model.ops)
        if (op.type == "Reshape" && op.edges.empty()) {
            int ret = execute_cpu_op(*c, op);
            if (ret)
                return ret;
        }
    return 0;
}
static void packed_copy_test(uint8_t dtype) {
    TensorRef s, d;
    s.dtype_code = d.dtype_code = dtype;
    s.ndim                      = 4;
    s.native_ndim               = 5;
    d.ndim                      = 2;
    const uint32_t dims[] = {2, 3, 2, 2}, native[] = {2, 1, 2, 2, 8};
    memcpy(s.dims, dims, sizeof(dims));
    memcpy(s.native_dims, native, sizeof(native));
    d.dims[0]                  = 2;
    d.dims[1]                  = 12;
    size_t               width = dtype_bytes(dtype);
    std::vector<uint8_t> in(64 * width, 0xcc), out(24 * width + 8, 0xdd), expected(24 * width);
    for (size_t n = 0; n < 2; n++)
        for (size_t c = 0; c < 3; c++)
            for (size_t h = 0; h < 2; h++)
                for (size_t w = 0; w < 2; w++) {
                    size_t   si = ((n * 2 + h) * 2 + w) * 8 + c;
                    size_t   di = ((n * 3 + c) * 2 + h) * 2 + w;
                    uint16_t v  = di == 0 ? 0x8000 : (uint16_t)(di + 1);
                    memcpy(in.data() + si * width, &v, width);
                    memcpy(expected.data() + di * width, &v, width);
                }
    assert(!copy_reshape_output(s, d, in, out));
    assert(!memcmp(out.data(), expected.data(), expected.size()));
    for (size_t i = expected.size(); i < out.size(); i++)
        assert(out[i] == 0xdd);
    assert(copy_reshape_output(s, d, std::span{in}.first(in.size() - 1), out) == -5);
    assert(copy_reshape_output(s, d, in, std::span{out}.first(expected.size() - 1)) == -5);
    d.dtype_code = 13;
    assert(copy_reshape_output(s, d, in, out) == -6);
}
int main(int argc, char** argv) {
    assert(argc == 2);
    packed_copy_test(10);
    packed_copy_test(3);
    Model m =
        model_file((std::string(std::getenv("RKNN_MODEL_DIR")) + "/mobilenetv2_fp.rknn").c_str());
    auto    native = read_file(std::string(argv[1]) + "/vendor/submit1-buf4-post.bin");
    auto    vendor = read_file(std::string(argv[1]) + "/vendor/out0.bin");
    Context c;
    c.model = std::move(m);
    std::vector<uint8_t> output(2048, 0);
    c.gem[3].map      = native.data();
    c.gem[3].size     = native.size();
    c.gem[3].obj_addr = 0x1234;
    c.gem[5].map      = output.data();
    c.gem[5].size     = output.size();
    c.gem[5].obj_addr = 0x5678;
    seen.clear();
    assert(!materialize_outputs(&c));
    assert(seen.size() == 3 && seen[0].obj == 0x1234 && seen[0].offset == 0xa00 &&
           seen[0].size == 2016 && seen[0].flags == 2);
    assert(seen[1].obj == 0x5678 && seen[1].flags == 2);
    assert(seen[2].obj == 0x5678 && seen[2].flags == 1);
    assert(!memcmp(output.data(), vendor.data(), vendor.size()));
    sync_errno = EIO;
    assert(materialize_outputs(&c) == -EIO);
    sync_errno = 0;
    assert(!c.drv.mem_sync(c.gem[5], 3, 7, rknn::SyncDirection::ToDevice));
    assert(seen.back().flags == 1 && seen.back().obj == 0x5678 && seen.back().offset == 3 &&
           seen.back().size == 7);
    rknn::GemBuffer destroy;
    destroy.obj_addr = 0x1234;
    assert(!c.drv.mem_destroy(&destroy));
    assert(destroyed == 0x1234);
    c.model =
        model_file((std::string(std::getenv("RKNN_MODEL_DIR")) + "/zoo/resnet18.rknn").c_str());
    std::fill(native.begin(), native.end(), 0);
    std::fill(output.begin(), output.end(), 0);
    for (size_t i = 0; i < 1000; i++) {
        uint16_t v = (uint16_t)(0x3c00 + i);
        memcpy(native.data() + 0x400 + 2 * i, &v, 2);
    }
    seen.clear();
    assert(!materialize_outputs(&c));
    assert(seen[0].offset == 0x400);
    assert(!memcmp(output.data(), native.data() + 0x400, 2000));
    puts(
        "OK: fp16/int8 padded layout, negative zero, buffer bounds, sync errors/ABI, real "
        "MobileNet board output byte-exact, ResNet graph-derived offset");
}
