#!/usr/bin/env python3
"""M1 探针 v3：GBM 平台 + gbm_surface + 带 config 的 GLES context
（gbmprobe v3 验证过的老路径），打 renderer。guest：python3 glesprobe.py"""
import ctypes
import os
import sys

NODE = sys.argv[1] if len(sys.argv) > 1 else "/dev/dri/renderD128"
W, H = 64, 64
AR24, RENDERING = 0x34325241, 4
EGL_PLATFORM_GBM = 0x31D6

libc = ctypes.CDLL("libc.so.6", use_errno=True)
E = ctypes.CDLL("libEGL.so.1")
G = ctypes.CDLL("libGLESv2.so.2")
gbm = ctypes.CDLL("libgbm.so.1")
E.eglGetPlatformDisplay.restype = ctypes.c_void_p
E.eglCreateContext.restype = ctypes.c_void_p
E.eglCreatePlatformWindowSurface.restype = ctypes.c_void_p
gbm.gbm_create_device.restype = ctypes.c_void_p
gbm.gbm_surface_create.restype = ctypes.c_void_p

fd = libc.open(NODE.encode(), 2)
if fd < 0:
    print("open FAIL", fd)
    sys.exit(1)
gd = gbm.gbm_create_device(fd)
print("gbm device:", hex(gd or 0))
if not gd:
    sys.exit(1)

d = E.eglGetPlatformDisplay(EGL_PLATFORM_GBM, gd, None)
if not d:
    os.environ["EGL_PLATFORM"] = "gbm"
    d = E.eglGetDisplay(gd)
print("display:", hex(d or 0))
major, minor = ctypes.c_long(), ctypes.c_long()
if not E.eglInitialize(d, ctypes.byref(major), ctypes.byref(minor)):
    print("eglInitialize FAIL", hex(E.eglGetError()))
    sys.exit(1)
print("EGL", major.value, minor.value)

E.eglBindAPI(0x30A)  # EGL_OPENGL_ES_API
cfg, n = ctypes.c_void_p(), ctypes.c_long()
E.eglChooseConfig(d, (ctypes.c_int * 11)(
                      0x3024, 8,  # RED
                      0x3023, 8,  # GREEN
                      0x3022, 8,  # BLUE
                      0x3025, 8,  # ALPHA
                      0x3033, 4,  # SURFACE_TYPE WINDOW
                      0x3038),
                  ctypes.byref(cfg), 1, ctypes.byref(n))
print("config:", hex(cfg.value or 0), "n:", n.value)
if not n.value:
    sys.exit(1)

surf = None  # surfaceless context（EGL_KHR_surfaceless_context）

ctx = E.eglCreateContext(d, cfg, None,
                         (ctypes.c_int * 3)(0x3098, 2, 0x3038))  
print("context:", hex(ctx or 0), "err", hex(E.eglGetError()))
if not ctx:
    sys.exit(1)
if not E.eglMakeCurrent(d, surf, surf, ctx):  # draw/read = EGL_NO_SURFACE
    print("makeCurrent FAIL", hex(E.eglGetError()))
    sys.exit(1)

G.glGetString.restype = ctypes.c_char_p
for name, label in ((0x1F00, "vendor"), (0x1F01, "renderer"),
                    (0x1F02, "version")):
    print(label, "=", G.glGetString(name).decode())
