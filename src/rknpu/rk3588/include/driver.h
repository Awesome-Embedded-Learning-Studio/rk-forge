// SPDX-License-Identifier: MIT
/* 开源 librknnrt 替代引擎 — driver client 层
 *
 * 契约全部实证于 dsh-001/005 + dyn/ qemu 装置(与 reference/rk3588 内核驱动配对):
 *   open("/dev/rknpu") 成功 → legacy 'r' ioctl 路径
 *   ACTION 'r'/00: flags=0 HW_VERSION(答 RK3588 target 0x46495245 由驱动填,用户态只读)
 *              flags=1 DRV_VERSION(>=0x2ba 走 104B 新 ABI)
 *   MEM_CREATE 'r'/02 40B: 返回真 dma-buf fd(+0) 与 dma_addr(+0x18); obj_addr(+0x10)=内核对象指针
 *   MEM_SYNC 'r'/05 32B / MEM_DESTROY 'r'/04
 *   SUBMIT 'r'/01 104B: flags/timeout/task_start/task_number/task_obj_addr/core_mask/
 *              fence_fd/subcore_task[5]; 等待 = fence poll(默认同步)
 */
#pragma once
#include <array>
#include <cstdint>

#include "unique_fd.h"

namespace rknn {

struct GemBuffer {
    int      fd           = -1;  // dma-buf fd(legacy MEM_CREATE 直接返回)
    uint32_t handle       = 0;
    uint64_t size         = 0;
    uint64_t dma_addr     = 0;        // IOVA
    uint64_t obj_addr     = 0;        // 内核对象指针(SUBMIT.task_obj_addr)
    void*    map          = nullptr;  // mmap 基址
    uint32_t create_flags = 0;
};

enum class SyncDirection : uint32_t {
    ToDevice   = 1,
    FromDevice = 2
};
struct TaskRange {
    uint32_t start = 0;
    uint32_t count = 0;
};
static_assert(sizeof(TaskRange) == 8);

struct SubmitArgs {
    uint32_t                 flags         = 0x5;
    uint32_t                 timeout_ms    = 6000;
    uint32_t                 task_start    = 0;
    uint32_t                 task_number   = 0;
    uint64_t                 task_obj_addr = 0;
    uint32_t                 core_mask     = 0;  // 0=AUTO
    int32_t                  fence_fd      = -1;
    std::array<TaskRange, 5> subcores{};
};

class Driver {
public:
    Driver()                         = default;
    Driver(const Driver&)            = delete;
    Driver& operator=(const Driver&) = delete;
    int     open();  // /dev/rknpu legacy interface
    int     get_hw_version(uint32_t* out);
    int     get_drv_version(uint32_t* out);
    int     get_iommu_en(uint32_t* out);
    int     mem_create(uint64_t size, uint32_t flags, GemBuffer* out);
    int     mem_sync(const GemBuffer& b, uint64_t off, uint64_t len, SyncDirection direction);
    int     mem_destroy(GemBuffer* b);
    int     submit(const SubmitArgs& a);
    int     close();
    bool    is_open() const { return fd_.valid(); }

private:
    int      action(uint32_t flag, uint32_t in_val, uint32_t* out);
    UniqueFd fd_;
};

}  // namespace rknn
