#!/usr/bin/env python3
"""M2n 受控测试：纹理采样 draw（TEX_SINGLE 语义的最小已知明文）。
2×2 已知纹理（四象限四色）+ NEAREST + 全屏 quad（4 顶点 TRIANGLE_STRIP
——与 mutter 合成 draw 同形态：r33=4 非索引）。验收：readback 四象限
= 对应 texel 色（uv 插值 + 采样 + blend 全链）。
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

# FBO 16×16 RGBA8
fbotex = ctypes.c_uint()
G.glGenTextures(1, ctypes.byref(fbotex))
G.glBindTexture(0xDE1, fbotex)
G.glTexImage2D(0xDE1, 0, 0x1908, 16, 16, 0, 0x1908, 0x1401, None)
G.glTexParameteri(0xDE1, 0x2800, 0x2601)
G.glTexParameteri(0xDE1, 0x2801, 0x2601)
fbo = ctypes.c_uint()
G.glGenFramebuffers(1, ctypes.byref(fbo))
G.glBindFramebuffer(0x8D40, fbo)
G.glFramebufferTexture2D(0x8D40, 0x8CE0, 0xDE1, fbotex, 0)
assert G.glCheckFramebufferStatus(0x8D40) == 0x8CD5

# 采样纹理：2×2 四色（通道分离，抓住 R/B 交换）
#   (0,0)=红 (1,0)=绿 (0,1)=蓝 (1,1)=黄
quads = bytes([255, 0, 0, 255, 0, 255, 0, 255,
              0, 0, 255, 255, 255, 255, 0, 255])
tex = ctypes.c_uint()
G.glGenTextures(1, ctypes.byref(tex))
G.glBindTexture(0xDE1, tex)
G.glTexImage2D(0xDE1, 0, 0x1908, 2, 2, 0, 0x1908, 0x1401,
               (ctypes.c_ubyte * 16).from_buffer_copy(quads))
G.glTexParameteri(0xDE1, 0x2800, 0x2600)   # MIN NEAREST
G.glTexParameteri(0xDE1, 0x2801, 0x2600)   # MAG NEAREST
G.glTexParameteri(0xDE1, 0x2802, 0x812F)   # WRAP_S CLAMP
G.glTexParameteri(0xDE1, 0x2803, 0x812F)   # WRAP_T CLAMP

VS = """
attribute vec2 a_pos;
attribute vec2 a_uv;
varying vec2 v_uv;
void main() { v_uv = a_uv; gl_Position = vec4(a_pos, 0.0, 1.0); }
"""
FS = """
precision mediump float;
varying vec2 v_uv;
uniform sampler2D u_tex;
void main() { gl_FragColor = texture2D(u_tex, v_uv); }
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
G.glAttachShader(prog, shader(0x8B31, VS))
G.glAttachShader(prog, shader(0x8B30, FS))
G.glLinkProgram(prog)
ok = ctypes.c_int()
G.glGetProgramiv(prog, 0x8B82, ctypes.byref(ok))
if not ok.value:
    log = ctypes.create_string_buffer(4096)
    G.glGetProgramInfoLog(prog, 4096, None, log)
    print("link fail:", log.value)
    sys.exit(1)
G.glUseProgram(prog)
G.glUniform1i(G.glGetUniformLocation(prog, b"u_tex"), 0)

# 4 顶点 quad：pos(x,y) + uv(u,v) 交错，TRIANGLE_STRIP（mutter 同形态）
verts = (ctypes.c_float * 16)(
    -1.0, -1.0, 0.0, 0.0,
    1.0, -1.0, 1.0, 0.0,
    -1.0, 1.0, 0.0, 1.0,
    1.0, 1.0, 1.0, 1.0)
vbo = ctypes.c_uint()
G.glGenBuffers(1, ctypes.byref(vbo))
G.glBindBuffer(0x8892, vbo)
G.glBufferData(0x8892, ctypes.sizeof(verts), verts, 0x88E4)
G.glEnableVertexAttribArray(0)
G.glVertexAttribPointer(0, 2, 0x1406, 0, 16, None)
G.glEnableVertexAttribArray(1)
G.glVertexAttribPointer(1, 2, 0x1406, 0, 16, ctypes.c_void_p(8))
G.glViewport(0, 0, 16, 16)
G.glDrawArrays(0x0005, 0, 4)                          # TRIANGLE_STRIP
print("glGetError after draw =", hex(G.glGetError()))
G.glFinish()

buf = (ctypes.c_ubyte * 1024)()
G.glReadPixels(0, 0, 16, 16, 0x1908, 0x1401, buf)
print("glGetError after read =", hex(G.glGetError()))
# 16×16 全读：每像素按象限映射 texel。x∈[0,8)→texel0（像素中心不过界）
bad = []
for y in range(16):
    ty = 1 if y >= 8 else 0
    for x in range(16):
        tx = 1 if x >= 8 else 0
        exp = quads[(ty * 2 + tx) * 4:(ty * 2 + tx) * 4 + 4]
        p = bytes(buf[(y * 16 + x) * 4:(y * 16 + x) * 4 + 4])
        if p != exp:
            bad.append((x, y, list(p), list(exp)))
print("坏点数 =", len(bad), bad[:6])
print("pixel(2,2) =", list(buf[8 * 4 + 2 * 4:8 * 4 + 2 * 4 + 4]),
      "(期望 [255,0,0,255])")
print("pixel(10,10) =", list(buf[(10 * 16 + 10) * 4:(10 * 16 + 10) * 4 + 4]),
      "(期望 [255,255,0,255])")
print("VERDICT:", "PASS" if not bad else "FAIL")
