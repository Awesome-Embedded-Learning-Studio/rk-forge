/* 只转发真实 syscall 的板验取证器；不改 ioctl 参数、不代做同步。
 * RKNN_TRACE_DIR 指定提交前后 mmap 快照目录，供主机离线对照。
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

struct create { uint32_t fd, flags; uint64_t size, obj, dma, sram; };
struct sync_args { uint32_t flags, reserved; uint64_t obj, offset, size; };
struct mapping { void *addr; size_t size; unsigned int id; int fd; };
static struct mapping maps[128];
static int fds[128], nfds;
static unsigned int next_id, submit_id;
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static int (*real_ioctl)(int, unsigned long, ...);
static void *(*real_mmap)(void *, size_t, int, int, int, off_t);
static void *(*real_mmap64)(void *, size_t, int, int, int, off64_t);
static int (*real_munmap)(void *, size_t);

__attribute__((constructor)) static void init_trace(void)
{
    real_ioctl = dlsym(RTLD_NEXT, "ioctl");
    real_mmap = dlsym(RTLD_NEXT, "mmap");
    real_mmap64 = dlsym(RTLD_NEXT, "mmap64");
    real_munmap = dlsym(RTLD_NEXT, "munmap");
    if (!real_ioctl || !real_mmap || !real_mmap64 || !real_munmap)
        _exit(125);
}

static int npu_fd(int fd)
{
    char path[64], target[128];
    snprintf(path, sizeof(path), "/proc/self/fd/%d", fd);
    ssize_t n = readlink(path, target, sizeof(target) - 1);
    if (n < 0) return 0;
    target[n] = 0;
    return !strcmp(target, "/dev/rknpu");
}

static void snapshot(const char *stage, unsigned int submit)
{
    const char *dir = getenv("RKNN_TRACE_DIR");
    for (size_t i = 0; i < sizeof(maps) / sizeof(maps[0]); i++) {
        struct mapping *m = &maps[i];
        if (!m->addr) continue;
        const unsigned char *p = m->addr;
        uint64_t hash = UINT64_C(1469598103934665603);
        size_t nonzero = 0;
        for (size_t j = 0; j < m->size; j++) {
            hash = (hash ^ p[j]) * UINT64_C(1099511628211);
            nonzero += p[j] != 0;
        }
        fprintf(stderr, "TRACE submit=%u %s buf=%u fd=%d size=%zu nz_bytes=%zu fnv=%016" PRIx64 " head=",
                submit, stage, m->id, m->fd, m->size, nonzero, hash);
        for (size_t j = 0; j < m->size && j < 16; j++) fprintf(stderr, "%02x", p[j]);
        fputc('\n', stderr);
        if (dir) {
            char path[4096];
            int n = snprintf(path, sizeof(path), "%s/submit%u-buf%u-%s.bin", dir, submit, m->id, stage);
            if (n < 0 || (size_t)n >= sizeof(path)) continue;
            FILE *f = fopen(path, "wb");
            if (f) {
                size_t written = fwrite(p, 1, m->size, f);
                int err = fclose(f);
                if (written != m->size || err)
                    fprintf(stderr, "TRACE snapshot write failed: %s\n", path);
            } else {
                fprintf(stderr, "TRACE snapshot open failed: %s errno=%d\n", path, errno);
            }
        }
    }
}

int ioctl(int fd, unsigned long cmd, ...)
{
    va_list ap;
    va_start(ap, cmd);
    void *arg = va_arg(ap, void *);
    va_end(ap);
    int saved_errno = errno;
    if (_IOC_TYPE(cmd) != 'r' || !npu_fd(fd)) {
        errno = saved_errno;
        return real_ioctl(fd, cmd, arg);
    }
    unsigned int nr = _IOC_NR(cmd), id = 0;
    pthread_mutex_lock(&lock);
    if (nr == 1 && arg && _IOC_SIZE(cmd) >= 64) {
        uint32_t *p = arg;
        uint64_t obj;
        memcpy(&obj, (char *)arg + 24, sizeof(obj));
        id = ++submit_id;
        fprintf(stderr, "TRACE SUBMIT #%u flags=%#x timeout=%u start=%u tasks=%u task_obj=%#" PRIx64 " core=%#x fence=%d\n",
                id, p[0], p[1], p[2], p[3], obj, p[14], (int32_t)p[15]);
        snapshot("pre", id);
    } else if (nr == 5 && arg && _IOC_SIZE(cmd) >= sizeof(struct sync_args)) {
        struct sync_args *s = arg;
        fprintf(stderr, "TRACE SYNC flags=%#x obj=%#" PRIx64 " off=%#" PRIx64 " size=%#" PRIx64 "\n",
                s->flags, s->obj, s->offset, s->size);
    }
    pthread_mutex_unlock(&lock);
    errno = saved_errno;
    int ret = real_ioctl(fd, cmd, arg);
    int out_errno = errno;
    pthread_mutex_lock(&lock);
    fprintf(stderr, "TRACE ioctl fd=%d nr=%u ret=%d errno=%d\n", fd, nr, ret, ret < 0 ? out_errno : 0);
    if (ret == 0 && nr == 2 && arg && _IOC_SIZE(cmd) >= sizeof(struct create)) {
        struct create *c = arg;
        if (nfds < (int)(sizeof(fds) / sizeof(fds[0]))) fds[nfds++] = c->fd;
        fprintf(stderr, "TRACE CREATE fd=%u flags=%#x size=%" PRIu64 " obj=%#" PRIx64 " dma=%#" PRIx64 "\n",
                c->fd, c->flags, c->size, c->obj, c->dma);
    }
    if (id && ret == 0) {
        uint32_t flags;
        memcpy(&flags, arg, sizeof(flags));
        if (!(flags & 2)) snapshot("post", id);
        else fprintf(stderr, "TRACE async submit: no post-completion snapshot\n");
    }
    pthread_mutex_unlock(&lock);
    errno = out_errno;
    return ret;
}

static void record_map(void *addr, size_t size, int fd, int prot)
{
    int saved_errno = errno;
    if (addr != MAP_FAILED && (prot & PROT_READ)) {
        pthread_mutex_lock(&lock);
        for (int i = 0; i < nfds; i++) {
            if (fds[i] != fd) continue;
            for (size_t j = 0; j < sizeof(maps) / sizeof(maps[0]); j++) {
                if (maps[j].addr) continue;
                maps[j] = (struct mapping){addr, size, ++next_id, fd};
                fprintf(stderr, "TRACE MMAP buf=%u fd=%d addr=%p size=%zu\n", next_id, fd, addr, size);
                break;
            }
            break;
        }
        pthread_mutex_unlock(&lock);
    }
    errno = saved_errno;
}

void *mmap(void *a, size_t n, int prot, int flags, int fd, off_t off)
{
    void *p = real_mmap(a, n, prot, flags, fd, off);
    record_map(p, n, fd, prot);
    return p;
}

void *mmap64(void *a, size_t n, int prot, int flags, int fd, off64_t off)
{
    void *p = real_mmap64(a, n, prot, flags, fd, off);
    record_map(p, n, fd, prot);
    return p;
}

int munmap(void *addr, size_t size)
{
    int saved_errno = errno;
    pthread_mutex_lock(&lock);
    errno = saved_errno;
    int ret = real_munmap(addr, size);
    int out_errno = errno;
    if (!ret) {
        uintptr_t start = (uintptr_t)addr, end = start + size;
        for (size_t i = 0; i < sizeof(maps) / sizeof(maps[0]); i++) {
            uintptr_t mstart = (uintptr_t)maps[i].addr;
            if (maps[i].addr && start < mstart + maps[i].size && end > mstart)
                maps[i].addr = NULL;
        }
    }
    pthread_mutex_unlock(&lock);
    errno = out_errno;
    return ret;
}
