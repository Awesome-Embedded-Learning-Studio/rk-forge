// SPDX-License-Identifier: MIT
#pragma once
#include <cstddef>
#include <cstdint>
#include <type_traits>

namespace rknn {
// Kernel task-table ABI. Copy this object to/from GEM memory; do not alias it.
struct TaskRecord {
    uint32_t flags            = 0;
    uint32_t operation_index  = 0;
    uint32_t enable_mask      = 0;
    uint32_t interrupt_mask   = 0;
    uint32_t interrupt_clear  = 0;
    uint32_t interrupt_status = 0;
    uint32_t register_count   = 0;
    uint32_t register_offset  = 0;
    uint64_t command_address  = 0;
};
static_assert(sizeof(TaskRecord) == 40);
static_assert(offsetof(TaskRecord, command_address) == 32);
static_assert(std::is_trivially_copyable_v<TaskRecord>);
}
