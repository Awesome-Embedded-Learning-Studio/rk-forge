#!/usr/bin/env python3
"""M2g 侦察：全屏三角形 + 常量色 fragment shader 的真 draw 路径。
区别于 glesclear（clear 走 FBD 描述符）：这里 mesa 必须发 RUN_IDVS/
RUN_TILING+RUN_FRAGMENT 类 job（vertex/fragment 真负载）。验收：
readback 三角形覆盖区 = 常量色（本例：三角形铺满 FBO → 全红）。
"""
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
    E.eglGetDisplay.restype = ctypes.c_void_p
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

# FBO + texture（16×16 RGBA8）
tex = ctypes.c_uint()
G.glGenTextures(1, ctypes.byref(tex))
G.glBindTexture(0xDE1, tex)
G.glTexImage2D(0xDE1, 0, 0x1908, 16, 16, 0, 0x1908, 0x1401, None)
G.glTexParameteri(0xDE1, 0x2800, 0x2601)
G.glTexParameteri(0xDE1, 0x2801, 0x2601)
fbo = ctypes.c_uint()
G.glGenFramebuffers(1, ctypes.byref(fbo))
G.glBindFramebuffer(0x8D40, fbo)
G.glFramebufferTexture2D(0x8D40, 0x8CE0, 0xDE1, tex, 0)
assert G.glCheckFramebufferStatus(0x8D40) == 0x8CD5, hex(
    G.glCheckFramebufferStatus(0x8D40))
assert E.eglMakeCurrent(d, None, None, ctx)

VS = """
attribute vec2 a_pos;
void main() { gl_Position = vec4(a_pos, 0.0, 1.0); }
"""
FS = """
precision mediump float;
void main() { gl_FragColor = vec4(1.0, 0.0, 0.0, 1.0); }
"""


def shader(kind, src):
    s = G.glCreateShader(kind)
    src_c = ctypes.c_char_p(src.encode())
    G.glShaderSource(s, 1, ctypes.byref(src_c), None)
    G.glCompileShader(s)
    ok = ctypes.c_int()
    G.glGetShaderiv(s, 0x8B81, ctypes.byref(ok))
    if not ok.value:
        log = ctypes.create_string_buffer(4096)
        G.glGetShaderInfoLog(s, 4096, None, log)
        print("compile fail:", log.value)
        sys.exit(1)
    return s


prog = G.glCreateProgram()
G.glAttachShader(prog, shader(0x8B31, VS))   # VERTEX
G.glAttachShader(prog, shader(0x8B30, FS))   # FRAGMENT
G.glLinkProgram(prog)
ok = ctypes.c_int()
G.glGetProgramiv(prog, 0x8B82, ctypes.byref(ok))
if not ok.value:
    log = ctypes.create_string_buffer(4096)
    G.glGetProgramInfoLog(prog, 4096, None, log)
    print("link fail:", log.value)
    sys.exit(1)
G.glUseProgram(prog)

# 全屏三角形（一个顶点带出整屏覆盖）。GLES 无 client-side 顶点数组——
# CPU 指针版 mesa 静默不提交（draw 无 job），必须真 VBO。
verts = (ctypes.c_float * 6)(-1.0, -1.0, 3.0, -1.0, -1.0, 3.0)
vbo = ctypes.c_uint()
G.glGenBuffers(1, ctypes.byref(vbo))
G.glBindBuffer(0x8892, vbo)                           # ARRAY_BUFFER
G.glBufferData(0x8892, ctypes.sizeof(verts), verts, 0x88E4)  # STATIC_DRAW
G.glEnableVertexAttribArray(0)
G.glVertexAttribPointer(0, 2, 0x1406, 0, 0, None)     # FLOAT, VBO 偏移 0
# surfaceless context 默认 viewport=0×0 → scissor_culls_everything
# → draw 被 panfrost 静默剔除（job 无 RUN_*）。必须显式设。
G.glViewport(0, 0, 16, 16)
G.glDrawArrays(0x0004, 0, 3)                          # TRIANGLES
print("glGetError after draw =", hex(G.glGetError()))
G.glFinish()

buf = (ctypes.c_ubyte * 64)()
G.glReadPixels(0, 0, 4, 4, 0x1908, 0x1401, buf)
print("glGetError after read =", hex(G.glGetError()))
# 全屏三角形：4×4 块 16 像素全应为红。逐行验证 = 行距解码（×16 假设）
# 的实证判据——若 stride 错，非 0 行露馅。
bad = []
for y in range(4):
    for x in range(4):
        p = list(buf[(y * 4 + x) * 4:(y * 4 + x) * 4 + 4])
        if p != [255, 0, 0, 255]:
            bad.append((x, y, p))
print("坏点数 =", len(bad), bad[:4])
px = list(buf[:4])
print("pixel(0,0) =", px, "(期望 [255, 0, 0, 255])")
print("VERDICT:", "PASS" if not bad else "FAIL")
