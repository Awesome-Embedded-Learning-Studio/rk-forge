// SPDX-License-Identifier: MIT
/* emitter: 指令包编码 + 槽布局 + NN_BG→六 GEM 装配 */
#pragma once
#include <cstdint>

namespace rknn {

struct Context;

// 8B 硬件包: reg | value<<16 | tag<<48(FUN_001a20e0 公式)
uint64_t encode_packet(uint16_t reg, uint32_t value);

// chunk 槽包数 = (amt+11)&~7(dsh-008 §2.2.5; 对 124/26/106 等于 align(amt,16))
uint32_t slot_packets(uint32_t amt);

// 内核 PC amount 公式(rknpu_job.c:352; RK3588 scale=2)
uint32_t pc_amount(uint32_t amt, uint32_t scale);

// 装配入口(shell 的 rknn_init 调用)
int emit_build(Context* ctx);

}  // namespace rknn
