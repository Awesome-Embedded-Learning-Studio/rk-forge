// SPDX-License-Identifier: MIT
/* 引擎内部上下文(shell/emitter/planner 共享) */
#pragma once
#include <array>

#include "driver.h"
#include "model.h"

namespace rknn {

enum class BufferSlot : size_t {
    Weights,
    Commands,
    Tasks,
    Activations,
    Input,
    Output,
    Count
};

struct Context {
    ~Context() { release_buffers(); }
    void release_buffers() noexcept {
        for (auto& buffer : gem)
            if (buffer.fd >= 0)
                drv.mem_destroy(&buffer);
        for (auto& buffer : extra_out)
            if (buffer.fd >= 0)
                drv.mem_destroy(&buffer);
    }
    GemBuffer&       buffer(BufferSlot slot) noexcept { return gem[static_cast<size_t>(slot)]; }
    const GemBuffer& buffer(BufferSlot slot) const noexcept {
        return gem[static_cast<size_t>(slot)];
    }
    Model                                                         model;
    Driver                                                        drv;
    // 六块基础 GEM(创建顺序=run7 实测): 0=weight 1=regcmd 2=task 3=internal
    // 4=input 5=output[0]; 多输出模型第 2..N 块输出 GEM 按 JSON 声明序追加
    std::array<GemBuffer, static_cast<size_t>(BufferSlot::Count)> gem;
    std::vector<GemBuffer>                                        extra_out;
    uint64_t                                                      regcmd_size = 0;
    uint64_t                                                      task_size   = 0;
    uint32_t core_mask   = 0;  // rknn_set_core_mask 写入
    uint32_t iommu_en    = 0;
    uint32_t drv_version = 0;

    // 三套预构建调度(行区间): A=3lane 联动, B=2lane, C=3lane 非联动
    uint32_t                rows_a = 0, rows_b = 0, rows_c = 0;
    std::array<uint32_t, 3> seg_a{};  // 每 lane 行数
    std::array<uint32_t, 2> seg_b{};
    std::array<uint32_t, 3> seg_c{};
};

}  // namespace rknn
