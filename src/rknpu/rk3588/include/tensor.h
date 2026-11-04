// SPDX-License-Identifier: MIT
#pragma once
#include <cstdint>
#include <span>

#include "model.h"
#include "rknn_api.h"

namespace rknn {
struct Context;
namespace detail {
struct TensorExtent {
    uint64_t logical_elements = 0;
    uint64_t storage_elements = 0;
};
int      tensor_extent(const TensorRef& tensor, TensorExtent& extent);
uint64_t tensor_offset(const TensorRef& tensor, uint64_t logical_index);
int      transform_tensor(const TensorRef& source, const TensorRef& destination,
                          std::span<const uint8_t> input, std::span<uint8_t> output,
                          std::span<const uint32_t> permutation = {});
int      copy_reshape_output(const TensorRef& source, const TensorRef& destination,
                             std::span<const uint8_t> input, std::span<uint8_t> output);
int      execute_cpu_op(Context& context, const OpRef& operation);
int      get_outputs(Context& context, std::span<rknn_output> outputs);
}
}
