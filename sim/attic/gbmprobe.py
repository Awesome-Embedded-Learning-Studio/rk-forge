#!/usr/bin/env python3
"""GBM/EGL 交换链探针 v3（战役四诊断）。

guest 内跑：python3 gbmprobe.py
mutter 的 swap 死于 dri2_swap_buffers EGL_BAD_ALLOC，而 v2 的 plain/linear
探针全绿 —— 差异只能在它传给 gbm_surface 的参数组合里。v3 枚举全部候选：

  1. eglQueryDmaBufModifiers —— mutter 谈判的原料（软驱到底报告什么）
  2. AR24/plain、AR24/modifiers2[LINEAR]×(SCANOUT|RENDERING / 仅 SCANOUT)、
     AR24/modifiers2[内核 plane 全表: AFBC×9+LINEAR]、XR24 对照组

fmt: AR24=0x34325241 XR24=0x34325258；flags: SCANOUT=1 RENDERING=4；
modifier 位值取自内核 drm_fourcc.h（VENDOR_ARM=0x08<<56, 16x16=1,
YTR=0x10 SPLIT=0x20 SPARSE=0x40 CBR=0x80）。
"""
import ctypes
import os

os.environ.setdefault("EGL_LOG_LEVEL", "debug")
os.environ.setdefault("MESA_DEBUG", "1")

XR24, AR24 = 0x34325258, 0x34325241
SCANOUT, RENDERING = 1, 4
EGL_PLATFORM_GBM = 12749
W, H = 1024, 600
AFBC = [0x0800000000000001, 0x0800000000000041, 0x0800000000000011,
        0x0800000000000081, 0x0800000000000051, 0x08000000000000C1,
        0x0800000000000091, 0x08000000000000D1, 0x0800000000000071]

gbm = ctypes.CDLL("libgbm.so.1")
egl = ctypes.CDLL("libEGL.so.1")
gl = ctypes.CDLL("libGLESv2.so.2")
P, I, U = ctypes.c_void_p, ctypes.c_int, ctypes.c_uint


def fn(lib, name, res, args):
    f = getattr(lib, name)
    f.restype, f.argtypes = res, args
    return f


gbm_create_device = fn(gbm, "gbm_create_device", P, [I])
gbm_surface_create = fn(gbm, "gbm_surface_create", P, [P, U, U, U, U])
gbm_surface_create_with_modifiers2 = fn(gbm, "gbm_surface_create_with_modifiers2",
                                        P, [P, U, U, U, ctypes.POINTER(ctypes.c_uint64), U, U])
gbm_surface_lock_front_buffer = fn(gbm, "gbm_surface_lock_front_buffer", P, [P])
gbm_surface_destroy = fn(gbm, "gbm_surface_destroy", None, [P])
gbm_bo_get_modifier = fn(gbm, "gbm_bo_get_modifier", ctypes.c_uint64, [P])
gbm_bo_get_stride = fn(gbm, "gbm_bo_get_stride", U, [P])

eglGetError = fn(egl, "eglGetError", U, [])
eglGetPlatformDisplay = fn(egl, "eglGetPlatformDisplay", P, [U, P, P])
eglGetDisplay = fn(egl, "eglGetDisplay", P, [P])
eglInitialize = fn(egl, "eglInitialize", U, [P, ctypes.POINTER(I), ctypes.POINTER(I)])
eglQueryString = fn(egl, "eglQueryString", ctypes.c_char_p, [P, U])
eglBindAPI = fn(egl, "eglBindAPI", U, [U])
eglChooseConfig = fn(egl, "eglChooseConfig", U, [P, ctypes.POINTER(I),
                                                 ctypes.POINTER(P), I, ctypes.POINTER(I)])
eglGetConfigAttrib = fn(egl, "eglGetConfigAttrib", U, [P, P, I, ctypes.POINTER(I)])
try:
    eglCreatePlatformWindowSurface = fn(egl, "eglCreatePlatformWindowSurface", P, [P, P, P, P])
except AttributeError:
    eglCreatePlatformWindowSurface = fn(egl, "eglCreatePlatformWindowSurfaceEXT", P, [P, P, P, P])
eglCreateContext = fn(egl, "eglCreateContext", P, [P, P, P, P])
eglMakeCurrent = fn(egl, "eglMakeCurrent", U, [P, P, P, P])
eglSwapBuffers = fn(egl, "eglSwapBuffers", U, [P, P])
glGetString = fn(gl, "glGetString", ctypes.c_char_p, [U])
# libglvnd 不导出扩展符号，必须走 eglGetProcAddress
eglGetProcAddress = fn(egl, "eglGetProcAddress", P, [ctypes.c_char_p])
_qdm = eglGetProcAddress(b"eglQueryDmaBufModifiersEXT")
eglQueryDmaBufModifiers = ctypes.cast(_qdm, ctypes.CFUNCTYPE(
    U, P, I, I, ctypes.POINTER(ctypes.c_uint64),
    ctypes.POINTER(U), ctypes.POINTER(I))) if _qdm else None


def step(name, ok, detail=""):
    print(f"[{'OK' if ok else 'FAIL'}] {name}{'  ' + detail if detail else ''}", flush=True)
    return ok


def ecode():
    return f"egl=0x{eglGetError():x}"


fd = os.open("/dev/dri/card0", os.O_RDWR | os.O_CLOEXEC)
dev = gbm_create_device(fd)
step("gbm_create_device", bool(dev))
dpy = eglGetPlatformDisplay(EGL_PLATFORM_GBM, dev, None) or eglGetDisplay(dev)
maj, mnr, n = I(), I(), I()
if not eglInitialize(dpy, ctypes.byref(maj), ctypes.byref(mnr)):
    step("eglInitialize", False, ecode())
    raise SystemExit(1)
step("eglInitialize", True, f"EGL {maj.value}.{mnr.value}")
eglBindAPI(0x30A0)                       # EGL_OPENGL_ES_API

# ① mutter 谈判原料：渲染器报告可 dmabuf 的 modifier
for fmt, tag in ((AR24, "AR24"), (XR24, "XR24")):
    mods = (ctypes.c_uint64 * 16)()
    cnt = I()
    if eglQueryDmaBufModifiers and eglQueryDmaBufModifiers(dpy, fmt, 16, mods, None, ctypes.byref(cnt)):
        print(f"dmabuf modifiers[{tag}] ({cnt.value}):",
              " ".join(f"0x{mods[i]:016x}" for i in range(cnt.value)) or "(空)")
    else:
        print(f"dmabuf modifiers[{tag}]: 不可用")


def cf(cfg, attrib):
    v = I()
    eglGetConfigAttrib(dpy, cfg, attrib, ctypes.byref(v))
    return v.value


# SURFACE_TYPE=WINDOW / RENDERABLE_TYPE=ES2；位数不预设，按 native visual 配
attr = (I * 5)(0x3033, 0x4, 0x3040, 0x4, 0x3038)
cfgs = (P * 64)()
if not eglChooseConfig(dpy, attr, cfgs, 64, ctypes.byref(n)):
    step("eglChooseConfig", False, ecode())
    raise SystemExit(1)
byvis = {}
rgba_fb = {}
for c in cfgs[:min(n.value, 64)]:
    vis = cf(c, 0x302C)                  # EGL_NATIVE_VISUAL_ID
    if vis not in byvis:
        byvis[vis] = c
    rgba = (cf(c, 0x3024), cf(c, 0x3023), cf(c, 0x3022), cf(c, 0x3021))
    rgba_fb.setdefault(rgba, c)


def pick_cfg(fmt):
    """按 surface 格式配 config（v1 教训：错配 → EGL_BAD_MATCH 假阳性）"""
    want_alpha = fmt == AR24
    c = byvis.get(fmt) or rgba_fb.get((8, 8, 8, 8 if want_alpha else 0))
    step(f"config for {fmt:#x}", bool(c), f"native match: {fmt in byvis}")
    return c


def swapchain(tag, surface, fmt):
    """窗口→上下文→swap→lock，mutter 断链现场复刻"""
    step(f"{tag}: gbm_surface", bool(surface), "" if surface else ecode())
    if not surface:
        return
    cfg = pick_cfg(fmt)
    if not cfg:
        gbm_surface_destroy(surface)
        return
    win = eglCreatePlatformWindowSurface(dpy, cfg, surface, None)
    if not step(f"{tag}: window surface", bool(win), "" if win else ecode()):
        gbm_surface_destroy(surface)
        return
    cattr = (I * 3)(0x3098, 2, 0x3038)   # CONTEXT_CLIENT_VERSION=2
    ctx = eglCreateContext(dpy, cfg, None, cattr)
    if not step(f"{tag}: context", bool(ctx), "" if ctx else ecode()):
        gbm_surface_destroy(surface)
        return
    eglMakeCurrent(dpy, win, win, ctx)
    ok = eglSwapBuffers(dpy, win)
    step(f"{tag}: eglSwapBuffers", bool(ok), "" if ok else ecode())
    front = gbm_surface_lock_front_buffer(surface)
    detail = (f"modifier 0x{gbm_bo_get_modifier(front):016x} "
              f"stride {gbm_bo_get_stride(front)}") if front else ecode()
    step(f"{tag}: lock_front", bool(front), detail)
    gbm_surface_destroy(surface)


swapchain("XR24-plain-SR", gbm_surface_create(dev, W, H, XR24, SCANOUT | RENDERING), XR24)
swapchain("AR24-plain-SR", gbm_surface_create(dev, W, H, AR24, SCANOUT | RENDERING), AR24)

lin = (ctypes.c_uint64 * 1)(0)           # DRM_FORMAT_MOD_LINEAR
swapchain("AR24-mods2[LINEAR]-SR",
          gbm_surface_create_with_modifiers2(dev, W, H, AR24, lin, 1, SCANOUT | RENDERING), AR24)
swapchain("AR24-mods2[LINEAR]-S",
          gbm_surface_create_with_modifiers2(dev, W, H, AR24, lin, 1, SCANOUT), AR24)

# 内核 plane 全表（vop2 rk3588 cluster 广告：AFBC×9 + LINEAR 兜底）
plane = (ctypes.c_uint64 * 10)(*AFBC, 0)
swapchain("AR24-mods2[plane]-SR",
          gbm_surface_create_with_modifiers2(dev, W, H, AR24, plane, 10, SCANOUT | RENDERING), AR24)
print("probe done")
