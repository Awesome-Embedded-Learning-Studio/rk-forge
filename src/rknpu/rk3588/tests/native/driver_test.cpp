// SPDX-License-Identifier: MIT
// Exercise resource ownership and fence deadlines through the real driver client.
#include <fcntl.h>
#include <unistd.h>

#include <cassert>
#include <cerrno>
#include <chrono>
#include <cstdarg>
#include <cstring>
#include <sys/syscall.h>

#include "shell_ctx.h"

namespace {
unsigned destroyed      = 0;
int      created_fd     = -1;
int      returned_fence = -1;
}

extern "C" int ioctl(int, unsigned long command, ...) noexcept {
    va_list arguments;
    va_start(arguments, command);
    auto* data = va_arg(arguments, void*);
    va_end(arguments);
    switch (command & 0xff) {
    case 2: {
        uint64_t size = 0;
        std::memcpy(&size, static_cast<char*>(data) + 8, sizeof(size));
        created_fd = static_cast<int>(::syscall(SYS_memfd_create, "driver-test", 0));
        assert(created_fd >= 0 && ::ftruncate(created_fd, size) == 0);
        const auto handle = static_cast<uint32_t>(created_fd);
        std::memcpy(data, &handle, sizeof(handle));
        return 0;
    }
    case 4:
        ++destroyed;
        return 0;
    case 1:
        std::memcpy(static_cast<char*>(data) + 60, &returned_fence, sizeof(returned_fence));
        return 0;
    default:
        assert(false);
        return -1;
    }
}

static bool is_closed(int descriptor) {
    errno = 0;
    return ::fcntl(descriptor, F_GETFD) == -1 && errno == EBADF;
}

static void memory_ownership_test() {
    rknn::Driver    driver;
    rknn::GemBuffer buffer;
    // Zero length makes the real mmap fail after the mocked device creates a GEM.
    assert(driver.mem_create(0, 0, &buffer) == -EINVAL);
    assert(destroyed == 1 && buffer.fd == -1 && !buffer.map && is_closed(created_fd));
    int input_fd, output_fd;
    {
        rknn::Context context;
        auto&         input = context.buffer(rknn::BufferSlot::Input);
        assert(context.drv.mem_create(4096, 0, &input) == 0);
        input_fd = input.fd;
        context.extra_out.emplace_back();
        assert(context.drv.mem_create(4096, 0, &context.extra_out.back()) == 0);
        output_fd = context.extra_out.back().fd;
    }
    assert(destroyed == 3 && is_closed(input_fd) && is_closed(output_fd));
}

static void fence_test() {
    rknn::Driver     driver;
    rknn::SubmitArgs arguments;
    arguments.timeout_ms = 20;
    int descriptors[2];
    assert(::pipe(descriptors) == 0);
    rknn::UniqueFd writer{descriptors[1]};
    returned_fence   = descriptors[0];
    const auto start = std::chrono::steady_clock::now();
    assert(driver.submit(arguments) == -ETIMEDOUT);
    assert(std::chrono::steady_clock::now() - start < std::chrono::seconds{2});
    assert(is_closed(returned_fence));

    assert(::pipe(descriptors) == 0);
    writer.reset(descriptors[1]);
    returned_fence = descriptors[0];
    assert(::write(writer.get(), "x", 1) == 1);
    assert(driver.submit(arguments) == 0 && is_closed(returned_fence));

    assert(::pipe(descriptors) == 0);
    writer.reset(descriptors[1]);
    returned_fence = descriptors[0];
    writer.reset();
    assert(driver.submit(arguments) == -EIO && is_closed(returned_fence));
}

int main() {
    memory_ownership_test();
    fence_test();
}
