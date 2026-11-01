/* Headless GLES2 shader/readback smoke test. See gpt-consult-005-review.md. */
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <stdio.h>
#include <stdlib.h>

enum { W = 64, H = 64 };

static void egl_fail(const char *what)
{
    fprintf(stderr, "%s: EGL error 0x%x\n", what, eglGetError());
    exit(2);
}

static GLuint shader(GLenum type, const char *source)
{
    GLuint s = glCreateShader(type);
    GLint ok;
    glShaderSource(s, 1, &source, NULL);
    glCompileShader(s);
    glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        char log[4096];
        glGetShaderInfoLog(s, sizeof(log), NULL, log);
        fprintf(stderr, "shader compile: %s\n", log);
        exit(2);
    }
    return s;
}

int main(int argc, char **argv)
{
    if (argc > 2) {
        fprintf(stderr, "usage: %s [output.ppm]\n", argv[0]);
        return 2;
    }
    PFNEGLGETPLATFORMDISPLAYEXTPROC get_platform =
        (PFNEGLGETPLATFORMDISPLAYEXTPROC)eglGetProcAddress("eglGetPlatformDisplayEXT");
    if (!get_platform) {
        fprintf(stderr, "eglGetPlatformDisplayEXT unavailable\n");
        return 2;
    }
    EGLDisplay d = get_platform(EGL_PLATFORM_SURFACELESS_MESA,
                                EGL_DEFAULT_DISPLAY, NULL);
    EGLint major, minor, count;
    EGLConfig config;
    const EGLint attrs[] = {
        EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
        EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
        EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8,
        EGL_ALPHA_SIZE, 8, EGL_NONE
    };
    const EGLint pb_attrs[] = {EGL_WIDTH, W, EGL_HEIGHT, H, EGL_NONE};
    const EGLint ctx_attrs[] = {EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE};
    if (d == EGL_NO_DISPLAY || !eglInitialize(d, &major, &minor))
        egl_fail("eglInitialize(surfaceless)");
    if (!eglBindAPI(EGL_OPENGL_ES_API))
        egl_fail("eglBindAPI");
    if (!eglChooseConfig(d, attrs, &config, 1, &count) || count != 1)
        egl_fail("eglChooseConfig");
    EGLSurface surface = eglCreatePbufferSurface(d, config, pb_attrs);
    if (surface == EGL_NO_SURFACE)
        egl_fail("eglCreatePbufferSurface");
    EGLContext context = eglCreateContext(d, config, EGL_NO_CONTEXT, ctx_attrs);
    if (context == EGL_NO_CONTEXT)
        egl_fail("eglCreateContext");
    if (!eglMakeCurrent(d, surface, surface, context))
        egl_fail("eglMakeCurrent");

    printf("EGL %d.%d vendor=%s\n", major, minor, eglQueryString(d, EGL_VENDOR));
    printf("GL_VENDOR=%s\nGL_RENDERER=%s\nGL_VERSION=%s\n",
           glGetString(GL_VENDOR), glGetString(GL_RENDERER), glGetString(GL_VERSION));
    fflush(stdout);

    const char *vs = "attribute vec2 p; void main() { gl_Position=vec4(p,0.,1.); }";
    const char *fs =
        "precision mediump float; void main() {"
        "bool right=gl_FragCoord.x>=32.; bool top=gl_FragCoord.y>=32.;"
        "vec3 c=top ? (right ? vec3(1.,1.,1.) : vec3(0.,0.,1.))"
        "           : (right ? vec3(0.,1.,0.) : vec3(1.,0.,0.));"
        "gl_FragColor=vec4(c,1.); }";
    GLuint v = shader(GL_VERTEX_SHADER, vs), f = shader(GL_FRAGMENT_SHADER, fs);
    GLuint program = glCreateProgram();
    glAttachShader(program, v);
    glAttachShader(program, f);
    glBindAttribLocation(program, 0, "p");
    glLinkProgram(program);
    GLint ok;
    glGetProgramiv(program, GL_LINK_STATUS, &ok);
    if (!ok) {
        char log[4096];
        glGetProgramInfoLog(program, sizeof(log), NULL, log);
        fprintf(stderr, "program link: %s\n", log);
        return 2;
    }
    const GLfloat vertices[] = {-1.f, -1.f, 3.f, -1.f, -1.f, 3.f};
    GLuint buffer;
    glGenBuffers(1, &buffer);
    glBindBuffer(GL_ARRAY_BUFFER, buffer);
    glBufferData(GL_ARRAY_BUFFER, sizeof(vertices), vertices, GL_STATIC_DRAW);
    glViewport(0, 0, W, H);
    glDisable(GL_DITHER);
    glClearColor(1.f, 0.f, 1.f, 1.f);
    glClear(GL_COLOR_BUFFER_BIT);
    glUseProgram(program);
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, NULL);
    glEnableVertexAttribArray(0);
    glDrawArrays(GL_TRIANGLES, 0, 3);
    glFinish();
    GLubyte pixels[W * H * 4];
    glReadPixels(0, 0, W, H, GL_RGBA, GL_UNSIGNED_BYTE, pixels);
    GLenum err = glGetError();
    if (err != GL_NO_ERROR) {
        fprintf(stderr, "draw/readback: GL error 0x%x\n", err);
        return 2;
    }

    unsigned bad = 0;
    for (int y = 0; y < H; ++y) {
        for (int x = 0; x < W; ++x) {
            int right = x >= W / 2, top = y >= H / 2;
            unsigned expected[] = {
                (top ? right : !right) ? 255u : 0u,
                right ? 255u : 0u, top ? 255u : 0u, 255u
            };
            const GLubyte *p = pixels + (y * W + x) * 4;
            for (int c = 0; c < 4; ++c) {
                if (abs((int)p[c] - (int)expected[c]) > 2) {
                    if (bad == 0)
                        fprintf(stderr, "first mismatch (%d,%d): rgba=%u,%u,%u,%u\n",
                                x, y, p[0], p[1], p[2], p[3]);
                    ++bad;
                    break;
                }
            }
        }
    }
    if (argc == 2) {
        FILE *out = fopen(argv[1], "wb");
        if (!out) {
            perror(argv[1]);
            return 2;
        }
        fprintf(out, "P6\n%d %d\n255\n", W, H);
        for (int y = H - 1; y >= 0; --y)
            for (int x = 0; x < W; ++x)
                if (fwrite(pixels + (y * W + x) * 4, 1, 3, out) != 3) {
                    fprintf(stderr, "PPM write failed\n");
                    fclose(out);
                    return 2;
                }
        if (fclose(out) != 0) {
            perror("PPM close");
            return 2;
        }
    }
    printf("%s: %u/%d mismatched pixels\n", bad ? "FAIL" : "PASS", bad, W * H);
    glDeleteBuffers(1, &buffer);
    glDeleteProgram(program);
    glDeleteShader(v);
    glDeleteShader(f);
    eglMakeCurrent(d, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    eglDestroyContext(d, context);
    eglDestroySurface(d, surface);
    eglTerminate(d);
    return bad ? 1 : 0;
}
