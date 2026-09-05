#!/usr/bin/env python3
"""M2h 侦察：GPU blit 路径。64×64 U-tiled FBO clear 红 → glReadPixels。
大图 readback 无法走 CPU 快路（tiled→linear detile 必须 blitter），
预期 mesa 发 RUN_FULLSCREEN(8)+DCD。验收：4×4 采样块全红 =
blit 真数据搬运（非 clear 铺设）的第二个真像素里程碑。
"""
import ctypes
import os
import sys

os.environ.setdefault("EGL_PLATFORM", "gbm")
NODE = "/dev/dri/renderD128"
W = H = 64

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
                         (ctypes.c_int * 3)(0x3098, 2, 0x3038))
assert ctx
assert E.eglMakeCurrent(d, None, None, ctx)

tex = ctypes.c_uint()
G.glGenTextures(1, ctypes.byref(tex))
G.glBindTexture(0xDE1, tex)
G.glTexImage2D(0xDE1, 0, 0x1908, W, H, 0, 0x1908, 0x1401, None)
G.glTexParameteri(0xDE1, 0x2800, 0x2601)
G.glTexParameteri(0xDE1, 0x2801, 0x2601)
fbo = ctypes.c_uint()
G.glGenFramebuffers(1, ctypes.byref(fbo))
G.glBindFramebuffer(0x8D40, fbo)
G.glFramebufferTexture2D(0x8D40, 0x8CE0, 0xDE1, tex, 0)
assert G.glCheckFramebufferStatus(0x8D40) == 0x8CD5

G.glClearColor(ctypes.c_float(1.0), ctypes.c_float(0.0),
               ctypes.c_float(0.0), ctypes.c_float(1.0))
G.glClear(0x4000)
print("clear err =", hex(G.glGetError()))

buf = (ctypes.c_ubyte * (W * 4))()
G.glReadPixels(0, 0, W, 4, 0x1908, 0x1401, buf)
print("read err =", hex(G.glGetError()))
bad = []
for y in range(4):
    for x in range(0, W, 16):
        p = list(buf[(y * W + x) * 4:(y * W + x) * 4 + 4])
        if p != [255, 0, 0, 255]:
            bad.append((x, y, p))
print("采样坏点 =", len(bad), bad[:4])
print("VERDICT:", "PASS" if not bad else "FAIL")
