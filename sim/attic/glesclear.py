#!/usr/bin/env python3
"""M2c 探针：glClear → FBO readback 校验（note 76 §3.6 的执行器验收程序）。
guest：python3 glesclear.py"""
import ctypes
import os
import sys

os.environ.setdefault("EGL_PLATFORM", "gbm")
NODE = "/dev/dri/renderD128"

libc = ctypes.CDLL("libc.so.6", use_errno=True)
E = ctypes.CDLL("libEGL.so.1")
G = ctypes.CDLL("libGLESv2.so.2")
gbm = ctypes.CDLL("libgbm.so.1")
E.eglGetPlatformDisplay.restype = ctypes.c_void_p
E.eglCreateContext.restype = ctypes.c_void_p
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
assert E.eglInitialize(d, ctypes.byref(major), ctypes.byref(minor)), hex(E.eglGetError())
E.eglBindAPI(0x30A)
cfg, n = ctypes.c_void_p(), ctypes.c_long()
E.eglChooseConfig(d, (ctypes.c_int * 1)(0x3038,), ctypes.byref(cfg), 1,
                  ctypes.byref(n))
assert n.value
ctx = E.eglCreateContext(d, cfg, None,
                         (ctypes.c_int * 3)(0x3098, 2, 0x3038))
assert ctx
assert E.eglMakeCurrent(d, None, None, ctx)

# FBO + texture
tex = ctypes.c_uint()
G.glGenTextures(1, ctypes.byref(tex))
G.glBindTexture(0xDE1, tex)                     # GL_TEXTURE_2D
G.glTexImage2D(0xDE1, 0, 0x1908, 16, 16, 0, 0x1908, 0x1401, None)  # RGBA/UBYTE
G.glTexParameteri(0xDE1, 0x2800, 0x2601)        # MIN nearest
G.glTexParameteri(0xDE1, 0x2801, 0x2601)        # MAG nearest
fbo = ctypes.c_uint()
G.glGenFramebuffers(1, ctypes.byref(fbo))
G.glBindFramebuffer(0x8D40, fbo)                # GL_FRAMEBUFFER
G.glFramebufferTexture2D(0x8D40, 0x8CE0, 0xDE1, tex, 0)  # COLOR_ATTACHMENT0
assert G.glCheckFramebufferStatus(0x8D40) == 0x8CD5, hex(
    G.glCheckFramebufferStatus(0x8D40))

# clear 红 + readback
G.glClearColor(ctypes.c_float(1.0), ctypes.c_float(0.0),
                 ctypes.c_float(0.0), ctypes.c_float(1.0))
G.glClear(0x4000)                               # GL_COLOR_BUFFER_BIT
print("glGetError =", hex(G.glGetError()))
buf = (ctypes.c_ubyte * 64)()
G.glReadPixels(0, 0, 4, 4, 0x1908, 0x1401, buf)
print("glGetError after read =", hex(G.glGetError()))
px = list(buf[:4])
print("pixel(0,0) =", px, "(期望 [255, 0, 0, 255])")
print("VERDICT:", "PASS" if px == [255, 0, 0, 255] else "FAIL")
