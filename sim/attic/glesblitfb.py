#!/usr/bin/env python3
"""M2h 验收 v2：显式 GPU blit。FBO A（tiled，clear 红=tile 已铺）→
glBlitFramebuffer → FBO B（tiled）→ readback B（CPU detile 可用）。
blit 必须走 GPU（RUN_IDVS blit job）——执行器把 A 的内容搬进 B 就是
真数据搬运。验收：B 的采样全红。
"""
import ctypes
import os
import sys

os.environ.setdefault("EGL_PLATFORM", "gbm")
NODE = "/dev/dri/renderD128"
W = H = 16

libc = ctypes.CDLL("libc.so.6", use_errno=True)
E = ctypes.CDLL("libEGL.so.1")
G = ctypes.CDLL("libGLESv2.so.2")
gbm = ctypes.CDLL("libgbm.so.1")
E.eglGetPlatformDisplay.restype = ctypes.c_void_p
E.eglCreateContext.restype = ctypes.c_void_p
E.eglGetDisplay.restype = ctypes.c_void_p
gbm.gbm_create_device.restype = ctypes.c_void_p

fd = libc.open(NODE.encode(), 2)
gd = gbm.gbm_create_device(fd)
assert gd
d = E.eglGetPlatformDisplay(0x31D6, gd, None)
if not d:
    os.environ["EGL_PLATFORM"] = "gbm"
    d = E.eglGetDisplay(gd)
assert d
major, minor = ctypes.c_long(), ctypes.c_long()
assert E.eglInitialize(d, ctypes.byref(major), ctypes.byref(minor)), hex(
    E.eglGetError())
E.eglBindAPI(0x30A0)
cfg, n = ctypes.c_void_p(), ctypes.c_long()
E.eglChooseConfig(d, (ctypes.c_int * 1)(0x3038), ctypes.byref(cfg), 1,
                  ctypes.byref(n))
assert n.value
ctx = E.eglCreateContext(d, cfg, None,
                         (ctypes.c_int * 3)(0x3098, 3, 0x3038))  # GLES3
assert ctx, hex(E.eglGetError())
assert E.eglMakeCurrent(d, None, None, ctx)


def make_fbo():
    tex = ctypes.c_uint()
    G.glGenTextures(1, ctypes.byref(tex))
    G.glBindTexture(0xDE1, tex)
    G.glTexImage2D(0xDE1, 0, 0x1908, W, H, 0, 0x1908, 0x1401, None)
    G.glTexParameteri(0xDE1, 0x2800, 0x2601)
    G.glTexParameteri(0xDE1, 0x2801, 0x2601)
    G.glTexParameteri(0xDE1, 0x2802, 0x812F)   # CLAMP_TO_EDGE
    G.glTexParameteri(0xDE1, 0x2803, 0x812F)
    fbo = ctypes.c_uint()
    G.glGenFramebuffers(1, ctypes.byref(fbo))
    G.glBindFramebuffer(0x8D40, fbo)
    G.glFramebufferTexture2D(0x8D40, 0x8CE0, 0xDE1, tex, 0)
    assert G.glCheckFramebufferStatus(0x8D40) == 0x8CD5
    return fbo


fboA = make_fbo()
G.glClearColor(ctypes.c_float(1.0), ctypes.c_float(0.0),
               ctypes.c_float(0.0), ctypes.c_float(1.0))
G.glClear(0x4000)
print("clear A err =", hex(G.glGetError()), flush=True)

fboB = make_fbo()
G.glBindFramebuffer(0x8D40, fboA)               # READ_FRAMEBUFFER
G.glBindFramebuffer(0x8D46 if False else 0x8D40, fboB)  # 占位，下一行读绑
# GLES3：glBindFramebuffer(target, fb)；READ=0x8CA8 DRAW=0x8CA9
G.glBindFramebuffer(0x8CA8, fboA)
G.glBindFramebuffer(0x8CA9, fboB)
G.glBlitFramebuffer(0, 0, W, H, 0, 0, W, H, 0x4000, 0x2600)  # COLOR,NEAREST
print("blit err =", hex(G.glGetError()), flush=True)

G.glBindFramebuffer(0x8CA8, fboB)
G.glBindFramebuffer(0x8CA9, fboB)
G.glBindFramebuffer(0x8D40, fboB)
buf = (ctypes.c_ubyte * (W * H * 4))()
G.glReadPixels(0, 0, W, H, 0x1908, 0x1401, buf)
print("read err =", hex(G.glGetError()), flush=True)
bad = []
for y in range(H):
    for x in range(W):
        p = list(buf[(y * W + x) * 4:(y * W + x) * 4 + 4])
        if p != [255, 0, 0, 255]:
            bad.append((x, y, p))
print("坏点 =", len(bad), bad[:4], flush=True)
print("VERDICT:", "PASS" if not bad else "FAIL", flush=True)
