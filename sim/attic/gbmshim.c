/* GBM/EGL 调用窥探垫片（战役四诊断）。
 * LD_PRELOAD 进 mutter/gnome-shell：把 gbm_surface 创建参数（格式、flags、
 * 完整 modifier 列表）、swap/lock 结果打到 stderr（→ journal，grep GBMSHIM）。
 * 判决点：mutter 到底拿什么 modifier 列表要 buffer、llvmpipe 在哪一步说不。
 * 注意：垫片不调用 eglGetError（会吃掉错误标志，干扰 mutter 自身的错误读取）。
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>

#define P(...) do { fprintf(stderr, "GBMSHIM: " __VA_ARGS__); fputc('\n', stderr); } while (0)

typedef unsigned EGLBoolean;

static void log_mods(const uint64_t *m, unsigned n)
{
    fprintf(stderr, "GBMSHIM:   mods[%u]:", n);
    for (unsigned i = 0; i < n && i < 16; i++)
        fprintf(stderr, " 0x%016llx", (unsigned long long)m[i]);
    fputc('\n', stderr);
}

void *gbm_surface_create(void *dev, uint32_t w, uint32_t h, uint32_t f, uint32_t flags)
{
    static void *(*real)(void *, uint32_t, uint32_t, uint32_t, uint32_t);
    if (!real) real = dlsym(RTLD_NEXT, "gbm_surface_create");
    void *r = real(dev, w, h, f, flags);
    P("gbm_surface_create(%p, %ux%u, fmt 0x%08x, flags 0x%x) = %p", dev, w, h, f, flags, r);
    return r;
}

void *gbm_surface_create_with_modifiers(void *dev, uint32_t w, uint32_t h, uint32_t f,
                                        const uint64_t *m, unsigned n)
{
    static void *(*real)(void *, uint32_t, uint32_t, uint32_t, const uint64_t *, unsigned);
    if (!real) real = dlsym(RTLD_NEXT, "gbm_surface_create_with_modifiers");
    void *r = real(dev, w, h, f, m, n);
    P("gbm_surface_create_with_modifiers(%p, %ux%u, fmt 0x%08x) = %p", dev, w, h, f, r);
    log_mods(m, n);
    return r;
}

void *gbm_surface_create_with_modifiers2(void *dev, uint32_t w, uint32_t h, uint32_t f,
                                         const uint64_t *m, unsigned n, uint32_t flags)
{
    static void *(*real)(void *, uint32_t, uint32_t, uint32_t, const uint64_t *, unsigned, uint32_t);
    if (!real) real = dlsym(RTLD_NEXT, "gbm_surface_create_with_modifiers2");
    void *r = real(dev, w, h, f, m, n, flags);
    P("gbm_surface_create_with_modifiers2(%p, %ux%u, fmt 0x%08x, flags 0x%x) = %p",
      dev, w, h, f, flags, r);
    log_mods(m, n);
    return r;
}

void *gbm_bo_create_with_modifiers2(void *dev, uint32_t w, uint32_t h, uint32_t f,
                                    const uint64_t *m, unsigned n, uint32_t flags)
{
    static void *(*real)(void *, uint32_t, uint32_t, uint32_t, const uint64_t *, unsigned, uint32_t);
    if (!real) real = dlsym(RTLD_NEXT, "gbm_bo_create_with_modifiers2");
    void *r = real(dev, w, h, f, m, n, flags);
    P("gbm_bo_create_with_modifiers2(%p, %ux%u, fmt 0x%08x, flags 0x%x) = %p",
      dev, w, h, f, flags, r);
    log_mods(m, n);
    return r;
}

void *gbm_surface_lock_front_buffer(void *surf)
{
    static void *(*real)(void *);
    static uint64_t (*mod)(void *);
    static uint32_t (*stride)(void *);
    static uint32_t (*handle)(void *);
    static void *(*bomap)(void *, uint32_t, uint32_t, uint32_t, uint32_t,
                          uint32_t *, void **);
    static void (*bounmap)(void *);
    if (!real) real = dlsym(RTLD_NEXT, "gbm_surface_lock_front_buffer");
    if (!mod) mod = dlsym(RTLD_NEXT, "gbm_bo_get_modifier");
    if (!stride) stride = dlsym(RTLD_NEXT, "gbm_bo_get_stride");
    if (!handle) handle = dlsym(RTLD_NEXT, "gbm_bo_get_handle");
    if (!bomap) bomap = dlsym(RTLD_NEXT, "gbm_bo_map");
    if (!bounmap) bounmap = dlsym(RTLD_NEXT, "gbm_bo_unmap");
    void *bo = real(surf);
    if (bo) {
        /* 首像素透视：bo 里到底装没装画面（战役四：bo 内容 vs 地址对错） */
        uint32_t w = 0;
        void *map_data = NULL;
        void *px = bomap(bo, 0, 0, 4, 1, &w, &map_data);
        if (px) {
            unsigned char *p = px;
            P("lock_front(%p) bo %p mod 0x%016llx stride %u handle %u "
              "px %02x%02x%02x%02x %02x%02x%02x%02x %02x%02x%02x%02x %02x%02x%02x%02x",
              surf, bo, (unsigned long long)mod(bo), stride(bo), handle(bo),
              p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7],
              p[8], p[9], p[10], p[11], p[12], p[13], p[14], p[15]);
            bounmap(bo);
        } else {
            P("lock_front(%p) bo %p mod 0x%016llx stride %u handle %u (map失败)",
              surf, bo, (unsigned long long)mod(bo), stride(bo), handle(bo));
        }
    } else {
        P("lock_front(%p) = NULL", surf);
    }
    return bo;
}

void gbm_surface_release_buffer(void *surf, void *bo)
{
    static void (*real)(void *, void *);
    if (!real) real = dlsym(RTLD_NEXT, "gbm_surface_release_buffer");
    P("release_buffer(surf %p, bo %p)", surf, bo);
    real(surf, bo);
}

EGLBoolean eglSwapBuffers(void *dpy, void *surf)
{
    static EGLBoolean (*real)(void *, void *);
    if (!real) real = dlsym(RTLD_NEXT, "eglSwapBuffers");
    EGLBoolean r = real(dpy, surf);
    P("eglSwapBuffers(dpy %p, surf %p) = %u", dpy, surf, r);
    return r;
}

void *eglCreatePlatformWindowSurface(void *dpy, void *cfg, void *native, const int *attrs)
{
    static void *(*real)(void *, void *, void *, const int *);
    if (!real) real = dlsym(RTLD_NEXT, "eglCreatePlatformWindowSurface");
    void *r = real(dpy, cfg, native, attrs);
    P("eglCreatePlatformWindowSurface(dpy %p, cfg %p, native %p) = %p", dpy, cfg, native, r);
    return r;
}
