/* 假内核桩(dump 版): 在 fakekern_sync 基础上注册表跟踪 MEM_CREATE 的 memfd,
 * SUBMIT 时把全部 GEM buffer 原始内容落盘(P2 对拍金标准)+ 解码 task 表头几项。
 * 落盘目录 = env RKNN_DUMP_DIR(默认 dumps/)。 */
#define _GNU_SOURCE
#include <stdio.h>
#include <dlfcn.h>
#include <stdarg.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <sys/mman.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <poll.h>

#define FAKE_FD_BASE 1024
#define LOG(...) fprintf(stderr, "##STUB## " __VA_ARGS__)

static int (*real_open)(const char*, int, ...);
static int (*real_ioctl)(int, unsigned long, ...);
static void* (*real_mmap)(void*, size_t, int, int, int, off_t);
static int (*real_close)(int);

static void init_real(void)
{
    if (!real_open) real_open = dlsym(RTLD_NEXT, "open");
    if (!real_ioctl) real_ioctl = dlsym(RTLD_NEXT, "ioctl");
    if (!real_mmap) real_mmap = dlsym(RTLD_NEXT, "mmap");
    if (!real_close) real_close = dlsym(RTLD_NEXT, "close");
}

static int is_fake_fd(int fd) { return fd >= FAKE_FD_BASE; }

static void hexdump(const void* p, size_t n)
{
    const unsigned char* b = p;
    for (size_t i = 0; i < n; i += 16) {
        fprintf(stderr, "##STUB##   %04zx:", i);
        for (size_t j = 0; j < 16 && i + j < n; j++) fprintf(stderr, " %02x", b[i + j]);
        fprintf(stderr, "\n");
    }
}

static const char* ioc_name(unsigned long req)
{
    unsigned type = (req >> 8) & 0xff, nr = req & 0xff;
    if (type == 'r') {
        switch (nr) {
        case 0: return "ACTION";
        case 1: return "SUBMIT";
        case 2: return "MEM_CREATE";
        case 3: return "MEM_MAP";
        case 4: return "MEM_DESTROY";
        case 5: return "MEM_SYNC";
        }
    }
    return "?";
}

static uint32_t handle_ctr;

/* ---- memfd 注册表: MEM_CREATE 返回的真 fd -> 元数据 ---- */
#define MAX_GEM 16
struct gem {
    int fd;
    uint32_t handle, flags;
    uint64_t size, dma_addr;
    int dead;
};
static struct gem gems[MAX_GEM];

static struct gem* gem_new(int fd, uint32_t h, uint32_t fl, uint64_t sz, uint64_t dma)
{
    for (int i = 0; i < MAX_GEM; i++) {
        if (gems[i].fd && gems[i].fd == fd) { gems[i].dead = 0; return &gems[i]; }
    }
    for (int i = 0; i < MAX_GEM; i++) {
        if (!gems[i].fd || gems[i].dead) {
            gems[i] = (struct gem){ fd, h, fl, sz, dma, 0 };
            return &gems[i];
        }
    }
    return NULL;
}

static struct gem* gem_by_fd(int fd)
{
    for (int i = 0; i < MAX_GEM; i++)
        if (gems[i].fd == fd && !gems[i].dead) return &gems[i];
    return NULL;
}

/* rknpu_task(内核 ABI, 40B packed): dump 时刻 blob 已装填完,就是 P2 金标准 */
struct rknpu_task_dump {
    uint32_t flags, op_idx, enable_mask, int_mask, int_clear, int_status;
    uint32_t regcfg_amount, regcfg_offset;
    uint64_t regcmd_addr;
} __attribute__((packed));

static void dump_one_gem(struct gem* g, int submit_no)
{
    static unsigned char buf[65536];
    char path[256];
    const char* dir = getenv("RKNN_DUMP_DIR");
    if (!dir || !*dir) dir = "dumps";
    syscall(SYS_mkdirat, AT_FDCWD, dir, 0777); /* EEXIST 无害 */
    snprintf(path, sizeof(path), "%s/s%d_gem%u_f0x%x_%lluB_dma0x%llx.bin",
             dir, submit_no, g->handle, g->flags,
             (unsigned long long)g->size, (unsigned long long)g->dma_addr);
    int out = (int)syscall(SYS_openat, AT_FDCWD, path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (out < 0) { LOG("dump %s 失败: %s\n", path, strerror(errno)); return; }
    uint64_t done = 0;
    while (done < g->size) {
        size_t chunk = g->size - done > sizeof(buf) ? sizeof(buf) : (size_t)(g->size - done);
        ssize_t r = pread(g->fd, buf, chunk, (off_t)done);
        if (r <= 0) break;
        ssize_t w = 0;
        while (w < r) {
            ssize_t k = write(out, buf + w, (size_t)(r - w));
            if (k <= 0) break;
            w += k;
        }
        done += (uint64_t)r;
        if (r < (ssize_t)chunk) break;
    }
    syscall(SYS_close, out);
    LOG("dump %s (%llu/%llu bytes)\n", path, (unsigned long long)done,
        (unsigned long long)g->size);

    /* task 表(flags 含 bit1|bit3,即 0xb 之类): 解码头 4 项 + 尾 1 项 */
    if (g->flags & 0xa) {
        static unsigned char tbuf[40 * 8];
        ssize_t r = pread(g->fd, tbuf, sizeof(tbuf), 0);
        size_t n = (size_t)r / 40;
        if (n > 4) n = 4;
        for (size_t i = 0; i < n; i++) {
            struct rknpu_task_dump* t = (struct rknpu_task_dump*)(tbuf + i * 40);
            LOG("  task[%zu] flags=0x%x op_idx=%u en_mask=0x%x int_mask=0x%x int_clear=0x%x "
                "int_status=0x%x regcfg_amt=%u regcfg_off=0x%x regcmd_addr=0x%llx\n",
                i, t->flags, t->op_idx, t->enable_mask, t->int_mask, t->int_clear,
                t->int_status, t->regcfg_amount, t->regcfg_offset,
                (unsigned long long)t->regcmd_addr);
        }
        if (g->size >= 40) {
            ssize_t r2 = pread(g->fd, tbuf, 40, (off_t)(g->size - 40));
            if (r2 == 40) {
                struct rknpu_task_dump* t = (struct rknpu_task_dump*)tbuf;
                LOG("  task[last] flags=0x%x op_idx=%u int_mask=0x%x regcfg_amt=%u "
                    "regcfg_off=0x%x regcmd_addr=0x%llx\n",
                    t->flags, t->op_idx, t->int_mask, t->regcfg_amount,
                    t->regcfg_offset, (unsigned long long)t->regcmd_addr);
            }
        }
    }
    /* regcmd 流(flags 含 bit1 无 bit3,如 0x5): 头 64B 节奏 */
    if ((g->flags & 0xb) == 0x5 || (g->flags & 0xb) == 0x4) {
        static unsigned char rbuf[64];
        pread(g->fd, rbuf, sizeof(rbuf), 0);
        LOG("  regcmd 头 64B:\n");
        hexdump(rbuf, sizeof(rbuf));
    }
}

static int dump_all(int submit_no)
{
    int n = 0;
    for (int i = 0; i < MAX_GEM; i++)
        if (gems[i].fd && !gems[i].dead) { dump_one_gem(&gems[i], submit_no); n++; }
    return n;
}

int open(const char* path, int flags, ...)
{
    init_real();
    mode_t mode = 0;
    va_list ap; va_start(ap, flags); mode = va_arg(ap, int); va_end(ap);
    if (strstr(path, "rknpu")) {
        LOG("open(\"%s\", 0x%x) -> FAKE_FD %d [legacy 路径]\n", path, flags, FAKE_FD_BASE);
        return FAKE_FD_BASE;
    }
    return real_open(path, flags, mode);
}

int openat(int dirfd, const char* path, int flags, ...)
{
    init_real();
    static int (*real)(int, const char*, int, ...);
    if (!real) real = dlsym(RTLD_NEXT, "openat");
    mode_t mode = 0;
    va_list ap; va_start(ap, flags); mode = va_arg(ap, int); va_end(ap);
    if (strstr(path, "rknpu")) {
        LOG("openat(\"%s\") -> FAKE_FD %d\n", path, FAKE_FD_BASE + 1);
        return FAKE_FD_BASE + 1;
    }
    return real(dirfd, path, flags, mode);
}

int ioctl(int fd, unsigned long req, ...)
{
    init_real();
    void* arg;
    va_list ap; va_start(ap, req); arg = va_arg(ap, void*); va_end(ap);
    if (!is_fake_fd(fd)) return real_ioctl(fd, req, arg);

    unsigned type = (req >> 8) & 0xff, nr = req & 0xff;
    size_t sz = (req >> 16) & 0x3fff;
    LOG("ioctl(fd=%d, 0x%lx '%c'/%02x sz=%zu %s)\n", fd, req, type, nr, sz, ioc_name(req));

    if (type == 'r' && nr == 2) { /* MEM_CREATE 40B: +0x10 obj_addr(内核对象指针,桩不填)
                                     +0x18 dma_addr(IOVA)。返回真 memfd fd 供直接 mmap */
        uint32_t* p = arg;
        uint64_t size = *(uint64_t*)((char*)arg + 8);
        uint32_t flags_in = p[1];
        int mfd = syscall(SYS_memfd_create, "rknpu_gem", 0);
        uint64_t dma = 0;
        if (mfd >= 0) {
            ftruncate(mfd, (off_t)((size + 0xfff) & ~0xfffull));
            dma = 0x50000000ull + (++handle_ctr) * 0x100000ull;
        }
        p[0] = (uint32_t)(mfd >= 0 ? mfd : (int)++handle_ctr);
        if (sz >= 40) *(uint64_t*)((char*)arg + 24) = dma;
        if (mfd >= 0) gem_new(mfd, handle_ctr, flags_in, size, dma);
        LOG("  MEM_CREATE handle=%u flags=0x%x size=%llu -> memfd=%d dma=0x%llx\n",
            handle_ctr, flags_in, (unsigned long long)size, mfd, (unsigned long long)dma);
        return 0;
    }
    if (type == 'r' && nr == 4) { /* MEM_DESTROY: 32B {handle,res,obj_addr} */
        uint32_t h = *(uint32_t*)arg;
        for (int i = 0; i < MAX_GEM; i++)
            if (gems[i].fd && gems[i].handle == h) gems[i].dead = 1;
        LOG("  MEM_DESTROY handle=%u\n", h);
        return 0;
    }
    if (type == 'r' && nr == 5) { /* MEM_SYNC: 计数即可,细节 run6 已采 */
        static unsigned long nsync;
        nsync++;
        uint64_t soff = *(uint64_t*)((char*)arg + 16);
        uint64_t ssize = *(uint64_t*)((char*)arg + 24);
        if (nsync <= 3 || nsync % 40 == 0)
            LOG("  MEM_SYNC #%lu off=0x%llx size=0x%llx\n", nsync,
                (unsigned long long)soff, (unsigned long long)ssize);
        return 0;
    }
    if (type == 'r' && nr == 1) { /* SUBMIT: 全量 dump + 结构解码 */
        static int submit_no;
        submit_no++;
        uint32_t* s = arg;
        uint32_t flags = s[0], timeout = s[1], tstart = s[2], tnum = s[3];
        uint64_t tobj = *(uint64_t*)((char*)arg + 0x18);
        uint32_t cmask = *(uint32_t*)((char*)arg + 0x38);
        int32_t fence = *(int32_t*)((char*)arg + 0x3c);
        LOG("  SUBMIT#%d flags=0x%x timeout=%u task_start=%u task_number=%u "
            "task_obj_addr=0x%llx core_mask=0x%x fence=%d\n",
            submit_no, flags, timeout, tstart, tnum, (unsigned long long)tobj, cmask, fence);
        for (int i = 0; i < 5; i++) {
            uint32_t a = *(uint32_t*)((char*)arg + 0x40 + i * 8);
            uint32_t b = *(uint32_t*)((char*)arg + 0x44 + i * 8);
            if (a | b) LOG("  subcore_task[%d]=(start=%u, number=%u)\n", i, a, b);
        }
        int n = dump_all(submit_no);
        LOG("  dump 完成: %d 块 GEM -> %s\n", n, getenv("RKNN_DUMP_DIR") ? getenv("RKNN_DUMP_DIR") : "dumps");
        return 0;
    }
    if (type == 'r' && nr == 0) { /* ACTION */
        uint32_t* p = arg;
        switch (p[0]) {
        case 0:  p[1] = 0x46495245; break;   /* GET_HW_VERSION = RK3588 target 枚举 */
        case 1:  p[1] = 908; break;          /* GET_DRV_VERSION = 0.9.8 -> 新 ABI */
        case 2:  p[1] = 600000000; break;    /* GET_FREQ 600MHz */
        case 18: p[1] = 1; break;            /* GET_IOMMU_EN */
        default: p[1] = 0; break;
        }
        LOG("  ACTION flags=%u -> out=0x%x\n", p[0], p[1]);
        return 0;
    }
    return 0;
}

void* mmap(void* addr, size_t len, int prot, int flags, int fd, off_t off)
{
    init_real();
    if (is_fake_fd(fd)) {
        LOG("mmap(len=%zu, fd=%d fake, off=0x%llx) -> anon\n", len, fd, (unsigned long long)off);
        return real_mmap(NULL, len, prot, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    }
    return real_mmap(addr, len, prot, flags, fd, off);
}

int close(int fd)
{
    init_real();
    if (is_fake_fd(fd)) { LOG("close(%d fake)\n", fd); return 0; }
    return real_close(fd);
}

int poll(struct pollfd* fds, nfds_t n, int timeout)
{
    init_real();
    static int (*real)(struct pollfd*, nfds_t, int);
    if (!real) real = dlsym(RTLD_NEXT, "poll");
    int any_fake = 0;
    for (nfds_t i = 0; i < n; i++)
        if (is_fake_fd(fds[i].fd)) { fds[i].revents = POLLIN; any_fake = 1; }
    if (any_fake) { LOG("poll(%zu fds, fake) -> ready\n", (size_t)n); return (int)n; }
    return real(fds, n, timeout);
}
