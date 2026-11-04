// SPDX-License-Identifier: MIT
#include "execution.h"

#include <algorithm>
#include <cstring>
#include <limits>
#include <optional>
#include <span>

#include "shell_ctx.h"
#include "task.h"
#include "tensor.h"

namespace rknn::detail {
namespace {
constexpr uint32_t kPingPong   = 0x5;
constexpr uint32_t kPreload    = 0x1;
constexpr uint32_t kUnusedTask = std::numeric_limits<uint32_t>::max();

struct ChainSelection {
    uint32_t core_mask                               = 0;
    uint32_t pc_mode                                 = 0;
    bool     operator==(const ChainSelection&) const = default;
};
struct PendingSegment {
    uint32_t       first_operation;
    ChainSelection selection;
};
struct LanePlan {
    uint32_t                  first_task = 0;
    std::span<const uint32_t> counts;
};

std::optional<LanePlan> select_plan(const Context& context) {
    switch (context.core_mask) {
    case 3:
        return LanePlan{context.rows_a, context.seg_b};
    case 7:
        return LanePlan{context.rows_a + context.rows_b, context.seg_c};
    case 0:
    case 1:
    case 2:
    case 4:
        return LanePlan{0, context.seg_a};
    default:
        return std::nullopt;
    }
}

ChainSelection select_chain(const Context& context, const OpRef& operation) {
    if (context.core_mask != 3 && context.core_mask != 7)
        return {context.core_mask, 0};
    const auto& group = operation.groups[context.core_mask == 3 ? GRP_B0 : GRP_C0];
    // A-only ops have a reserved fallback row in the first B/C lane.
    if (group.empty())
        return {1, 0};
    const bool copy_chain = std::ranges::all_of(group, [&](uint16_t index) {
        const auto& edge = operation.edges[index];
        return edge.f2 == 4 || edge.enable_mask == 0x60;
    });
    return {context.core_mask, copy_chain ? 0u : context.core_mask == 3 ? 1u : 2u};
}

TaskRange find_operation_range(std::span<const uint8_t> task_bytes, uint32_t base, uint32_t count,
                               uint32_t first, uint32_t end) {
    TaskRange range{base, 0};
    for (uint32_t i = 0; i < count; ++i) {
        TaskRecord record;
        std::memcpy(&record, task_bytes.data() + static_cast<uint64_t>(base + i) * sizeof(record),
                    sizeof(record));
        if (record.operation_index < first) {
            ++range.start;
            continue;
        }
        if (record.operation_index >= end)
            break;
        ++range.count;
    }
    return range;
}

void populate_independent_ranges(SubmitArgs& arguments, uint32_t plan_mask) {
    if (arguments.core_mask != 3 && arguments.core_mask != 7)
        return;
    // The ABI duplicates lanes 0/1 in slots 2/3 for independent B/C plans.
    arguments.subcores[4] = plan_mask == 7 ? arguments.subcores[2] : TaskRange{kUnusedTask, 0};
    arguments.subcores[2] = arguments.subcores[0];
    arguments.subcores[3] = arguments.subcores[1];
}

int submit_range(Context& context, uint32_t first_operation, uint32_t end_operation, uint32_t flags,
                 uint32_t effective_mask, uint32_t& logical_start) {
    if (first_operation == end_operation)
        return 0;
    const auto plan  = select_plan(context);
    auto&      tasks = context.buffer(BufferSlot::Tasks);
    if (!plan || !tasks.map)
        return -5;
    const std::span task_bytes{static_cast<const uint8_t*>(tasks.map),
                               static_cast<size_t>(tasks.size)};
    SubmitArgs      arguments;
    arguments.flags         = flags;
    arguments.task_obj_addr = tasks.obj_addr;
    arguments.core_mask     = effective_mask;
    arguments.task_start    = logical_start;
    if (context.core_mask == 3)
        arguments.subcores[2].start = kUnusedTask;
    uint32_t base         = plan->first_task;
    uint32_t longest_lane = 0;
    for (size_t lane = 0; lane < plan->counts.size(); ++lane) {
        const uint32_t count = plan->counts[lane];
        if (static_cast<uint64_t>(base) + count > tasks.size / sizeof(TaskRecord))
            return -5;
        auto range = find_operation_range(task_bytes, base, count, first_operation, end_operation);
        if (effective_mask && !(effective_mask & (1u << lane)))
            range.count = 0;
        arguments.subcores[lane] = range;
        arguments.task_number += range.count;
        longest_lane = std::max(longest_lane, range.count);
        base += count;
    }
    if (!arguments.task_number)
        return 0;
    populate_independent_ranges(arguments, context.core_mask);
    arguments.timeout_ms = static_cast<uint32_t>(
        std::min<uint64_t>(kUnusedTask, std::max<uint64_t>(6000, 30ull * longest_lane)));
    const int result = context.drv.submit(arguments);
    if (!result)
        logical_start += context.core_mask == 0 ? longest_lane : arguments.task_number;
    return result;
}
}  // namespace

int execute_graph(Context& context) {
    uint32_t                      logical_start = context.core_mask == 3 ? context.rows_a
                                                  : context.core_mask == 7 ? context.rows_a + context.rows_b
                                                                           : 0;
    std::optional<PendingSegment> pending;
    for (uint32_t index = 0; index < context.model.ops.size(); ++index) {
        const auto& operation = context.model.ops[index];
        if (operation.type == "InputOperator" || operation.type == "OutputOperator")
            continue;
        const bool cpu_operation     = operation.edges.empty();
        const bool dedicated_preload = std::ranges::any_of(
            operation.edges, [](const EdgeRef& edge) { return edge.tensor2 != 0; });
        const auto selection = select_chain(context, operation);
        if (pending && (cpu_operation || dedicated_preload || selection != pending->selection)) {
            if (const int error = submit_range(context, pending->first_operation, index, kPingPong,
                                               pending->selection.core_mask, logical_start))
                return error;
            pending.reset();
        }
        if (cpu_operation) {
            if (const int error = execute_cpu_op(context, operation))
                return error;
        } else if (dedicated_preload) {
            if (const int error = submit_range(context, index, index + 1, kPreload,
                                               selection.core_mask, logical_start))
                return error;
        } else if (!pending) {
            pending = PendingSegment{index, selection};
        }
    }
    return pending ? submit_range(context, pending->first_operation,
                                  static_cast<uint32_t>(context.model.ops.size()), kPingPong,
                                  pending->selection.core_mask, logical_start)
                   : 0;
}
}  // namespace rknn::detail
