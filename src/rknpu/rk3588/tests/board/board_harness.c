/* 板载取证 harness: 与 dyn/harness.c 同一生命周期,追加输出落盘+摘要+计时.
 * 用法: board_harness <model.rknn> <outdir> [core_mask]
 * 同一二进制经 LD_LIBRARY_PATH 切换 own/vendor librknnrt,输出逐字节对账.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "rknn_api.h"

#define MARK(tag) fprintf(stderr, "\n#### HARNESS: %s ####\n", tag)

static uint64_t fnv1a(const void* p, size_t n)
{
    uint64_t h = 1469598103934665603ULL;
    const unsigned char* b = p;
    for (size_t i = 0; i < n; i++) { h ^= b[i]; h *= 1099511628211ULL; }
    return h;
}

static double now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

int main(int argc, char** argv)
{
    if (argc < 3) {
        fprintf(stderr, "usage: board_harness <model.rknn> <outdir> [core_mask]\n");
        return 2;
    }

    FILE* f = fopen(argv[1], "rb");
    if (!f) { perror("fopen model"); return 2; }
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    if (sz <= 0 || (unsigned long)sz > UINT32_MAX || fseek(f, 0, SEEK_SET)) {
        fclose(f);
        return 2;
    }
    void* model = malloc(sz);
    if (!model || fread(model, 1, sz, f) != (size_t)sz) {
        fclose(f);
        free(model);
        return 2;
    }
    fclose(f);
    fprintf(stderr, "model %s: %ld bytes\n", argv[1], sz);

    rknn_context ctx = 0;
    MARK("rknn_init");
    double t0 = now_ms();
    int r = rknn_init(&ctx, model, (uint32_t)sz, 0, NULL);
    fprintf(stderr, "=> rknn_init ret=%d ctx=0x%llx (%.1f ms)\n",
            r, (unsigned long long)ctx, now_ms() - t0);
    if (r != 0) { free(model); return 1; }
    int status = 1;
    void *ibuf = NULL;

    if (argc >= 4) {
        rknn_core_mask mask = (rknn_core_mask)strtoul(argv[3], NULL, 0);
        MARK("rknn_set_core_mask");
        r = rknn_set_core_mask(ctx, mask);
        fprintf(stderr, "=> set_core_mask(0x%x) ret=%d\n", (unsigned)mask, r);
        if (r != 0) goto cleanup;
    }

    MARK("query IN_OUT_NUM");
    rknn_input_output_num io = {0, 0};
    r = rknn_query(ctx, RKNN_QUERY_IN_OUT_NUM, &io, sizeof(io));
    fprintf(stderr, "=> ret=%d n_input=%u n_output=%u\n", r, io.n_input, io.n_output);
    if (r != 0 || io.n_input != 1 || io.n_output == 0 || io.n_output > 16) {
        fprintf(stderr, "FAIL: query or unsupported harness IO count\n");
        goto cleanup;
    }

    rknn_tensor_attr attrs[16];
    memset(attrs, 0, sizeof(attrs));
    for (uint32_t i = 0; i < io.n_input && i < 16; i++) {
        attrs[i].index = i;
        r = rknn_query(ctx, RKNN_QUERY_INPUT_ATTR, &attrs[i], sizeof(attrs[i]));
        fprintf(stderr, "=> input[%u] ret=%d type=%d fmt=%d n_elems=%u size=%u\n",
                i, r, attrs[i].type, attrs[i].fmt, attrs[i].n_elems, attrs[i].size);
        if (r != 0 || !attrs[i].size) goto cleanup;
    }

    if (io.n_input > 0) {
        /* 输入模式与 dyn/harness.c 一致: 0x55 填充,双跑可比 */
        ibuf = malloc(attrs[0].size);
        if (!ibuf) goto cleanup;
        memset(ibuf, 0x55, attrs[0].size);
        rknn_input in;
        memset(&in, 0, sizeof(in));
        in.index = 0;
        in.buf = ibuf;
        in.size = attrs[0].size;
        in.type = attrs[0].type;
        in.fmt = attrs[0].fmt;
        MARK("rknn_inputs_set");
        r = rknn_inputs_set(ctx, 1, &in);
        fprintf(stderr, "=> ret=%d\n", r);
        if (r != 0) goto cleanup;
    }

    MARK("rknn_run");
    t0 = now_ms();
    r = rknn_run(ctx, NULL);
    fprintf(stderr, "=> rknn_run ret=%d (%.1f ms)\n", r, now_ms() - t0);
    if (r != 0) goto cleanup;

    if (io.n_output > 0 && io.n_output <= 16) {
        rknn_output outs[16];
        memset(outs, 0, sizeof(outs));
        for (uint32_t i = 0; i < io.n_output; i++) {
            outs[i].index = i;
            outs[i].want_float = 0;   /* 原始量化输出,与 replay 线一致 */
            outs[i].is_prealloc = 0;
        }
        MARK("rknn_outputs_get");
        t0 = now_ms();
        r = rknn_outputs_get(ctx, io.n_output, outs, NULL);
        fprintf(stderr, "=> ret=%d (%.1f ms)\n", r, now_ms() - t0);
        if (r != 0) goto cleanup;
        {
            int output_failed = 0;
            for (uint32_t i = 0; i < io.n_output; i++) {
                char path[512];
                int n = snprintf(path, sizeof(path), "%s/out%u.bin", argv[2], i);
                if (n < 0 || (size_t)n >= sizeof(path) || !outs[i].buf || !outs[i].size) {
                    output_failed = 1;
                    break;
                }
                FILE* o = fopen(path, "wb");
                if (!o) { perror("fopen output"); output_failed = 1; break; }
                size_t written = fwrite(outs[i].buf, 1, outs[i].size, o);
                int close_ret = fclose(o);
                if (written != outs[i].size || close_ret != 0) {
                    perror("write output");
                    output_failed = 1;
                    break;
                }
                fprintf(stderr, "=> out[%u] size=%u fnv1a=0x%016llx -> %s\n",
                        i, outs[i].size,
                        (unsigned long long)fnv1a(outs[i].buf, outs[i].size), path);
            }
            MARK("rknn_outputs_release");
            r = rknn_outputs_release(ctx, io.n_output, outs);
            fprintf(stderr, "=> ret=%d\n", r);
            if (r != 0 || output_failed) goto cleanup;
        }
    }
    status = 0;

cleanup:
    MARK("rknn_destroy");
    r = rknn_destroy(ctx);
    fprintf(stderr, "=> ret=%d\n", r);
    if (r != 0) status = 1;
    free(ibuf);
    free(model);
    MARK("done");
    return status;
}
