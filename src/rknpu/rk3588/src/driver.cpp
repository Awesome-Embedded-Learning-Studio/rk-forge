// SPDX-License-Identifier: MIT
#include "driver.h"

#include <fcntl.h>
#include <poll.h>

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cstddef>
#include <limits>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <type_traits>

namespace rknn {
namespace {
constexpr unsigned long kAction        = 0xc0087200;
constexpr unsigned long kSubmit        = 0xc0687201;
constexpr unsigned long kCreateMemory  = 0xc0287202;
constexpr unsigned long kDestroyMemory = 0xc0107204;
constexpr unsigned long kSyncMemory    = 0xc0207205;
constexpr uint32_t      kDriverVersion = 1;
constexpr uint32_t      kIommuEnabled  = 18;
constexpr uint32_t      kNonblocking   = 1u << 1;

struct ActionRequest {
    uint32_t flags;
    uint32_t value;
};
struct CreateMemoryRequest {
    uint32_t handle{};
    uint32_t flags{};
    uint64_t size{};
    uint64_t object_address{};
    uint64_t dma_address{};
    uint64_t sram_size{};
};
struct SyncMemoryRequest {
    uint32_t flags;
    uint32_t reserved{};
    uint64_t object_address;
    uint64_t offset;
    uint64_t size;
};
struct DestroyMemoryRequest {
    uint32_t handle;
    uint32_t reserved{};
    uint64_t object_address;
};
// Explicit reserved fields keep the legacy kernel ABI independent of C++ helpers.
struct SubmitRequest {
    uint32_t                  flags;
    uint32_t                  timeout_ms;
    uint32_t                  task_start;
    uint32_t                  task_number;
    uint64_t                  reserved0{};
    uint64_t                  task_object;
    std::array<std::byte, 24> reserved1{};
    uint32_t                  core_mask;
    int32_t                   fence_fd;
    std::array<TaskRange, 5>  subcores;
};
static_assert(sizeof(ActionRequest) == 8);
static_assert(sizeof(CreateMemoryRequest) == 40);
static_assert(sizeof(SyncMemoryRequest) == 32);
static_assert(sizeof(DestroyMemoryRequest) == 16);
static_assert(sizeof(SubmitRequest) == 104);
static_assert(offsetof(SubmitRequest, task_object) == 0x18);
static_assert(offsetof(SubmitRequest, core_mask) == 0x38);
static_assert(offsetof(SubmitRequest, fence_fd) == 0x3c);
static_assert(offsetof(SubmitRequest, subcores) == 0x40);
static_assert(std::is_trivially_copyable_v<SubmitRequest>);

int wait_for_fence(int descriptor, uint32_t timeout_ms) {
    using Clock = std::chrono::steady_clock;
    UniqueFd   fence{descriptor};
    const auto deadline = Clock::now() + std::chrono::milliseconds{timeout_ms};
    pollfd     poll_descriptor{fence.get(), POLLIN, 0};
    for (;;) {
        const auto remaining =
            std::chrono::duration_cast<std::chrono::milliseconds>(deadline - Clock::now()).count();
        if (remaining <= 0)
            return -ETIMEDOUT;
        const int wait_ms =
            static_cast<int>(std::min<int64_t>(remaining, std::numeric_limits<int>::max()));
        const int result = ::poll(&poll_descriptor, 1, wait_ms);
        if (result < 0 && errno == EINTR)
            continue;
        if (result < 0)
            return -errno;
        if (result == 0)
            return -ETIMEDOUT;
        if (poll_descriptor.revents & (POLLERR | POLLHUP | POLLNVAL))
            return -EIO;
        if (poll_descriptor.revents & POLLIN)
            return 0;
    }
}
}  // namespace

int Driver::open() {
    if (fd_.valid())
        return 0;
    const int descriptor = ::open("/dev/rknpu", O_RDWR);
    if (descriptor < 0)
        return -errno;
    fd_.reset(descriptor);
    return 0;
}

int Driver::action(uint32_t flag, uint32_t input, uint32_t* output) {
    ActionRequest request{flag, input};
    if (::ioctl(fd_.get(), kAction, &request) < 0)
        return -errno;
    if (output)
        *output = request.value;
    return 0;
}
int Driver::get_hw_version(uint32_t* output) {
    return action(0, 0, output);
}
int Driver::get_drv_version(uint32_t* output) {
    return action(kDriverVersion, 0, output);
}
int Driver::get_iommu_en(uint32_t* output) {
    return action(kIommuEnabled, 0, output);
}

int Driver::mem_create(uint64_t size, uint32_t flags, GemBuffer* output) {
    CreateMemoryRequest request{.flags = flags, .size = size};
    if (::ioctl(fd_.get(), kCreateMemory, &request) < 0)
        return -errno;
    output->fd           = static_cast<int>(request.handle);
    output->handle       = request.handle;
    output->size         = size;
    output->dma_addr     = request.dma_address;
    output->obj_addr     = request.object_address;
    output->create_flags = flags;
    output->map          = ::mmap(nullptr, size, PROT_READ | PROT_WRITE, MAP_SHARED, output->fd, 0);
    if (output->map == MAP_FAILED) {
        const int error = errno;
        output->map     = nullptr;
        mem_destroy(output);
        return -error;
    }
    return 0;
}

int Driver::mem_sync(const GemBuffer& buffer, uint64_t offset, uint64_t size,
                     SyncDirection direction) {
    SyncMemoryRequest request{.flags          = static_cast<uint32_t>(direction),
                              .object_address = buffer.obj_addr,
                              .offset         = offset,
                              .size           = size};
    if (::ioctl(fd_.get(), kSyncMemory, &request) < 0)
        return -errno;
    return 0;
}

int Driver::mem_destroy(GemBuffer* buffer) {
    if (buffer->map) {
        ::munmap(buffer->map, buffer->size);
        buffer->map = nullptr;
    }
    UniqueFd descriptor{std::exchange(buffer->fd, -1)};
    // Release the dma-buf descriptor before destroying its legacy session handle.
    descriptor.reset();
    DestroyMemoryRequest request{.handle         = std::exchange(buffer->handle, 0),
                                 .object_address = buffer->obj_addr};
    if (::ioctl(fd_.get(), kDestroyMemory, &request) < 0)
        return -errno;
    return 0;
}

int Driver::submit(const SubmitArgs& args) {
    SubmitRequest request{.flags       = args.flags,
                          .timeout_ms  = args.timeout_ms,
                          .task_start  = args.task_start,
                          .task_number = args.task_number,
                          .task_object = args.task_obj_addr,
                          .core_mask   = args.core_mask,
                          .fence_fd    = args.fence_fd,
                          .subcores    = args.subcores};
    if (::ioctl(fd_.get(), kSubmit, &request) < 0)
        return -errno;
    if (request.fence_fd >= 0 && !(args.flags & kNonblocking))
        return wait_for_fence(request.fence_fd, args.timeout_ms);
    return 0;
}

int Driver::close() {
    fd_.reset();
    return 0;
}
}  // namespace rknn
