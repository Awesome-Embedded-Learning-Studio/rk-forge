// SPDX-License-Identifier: MIT
#include "tensor.h"

#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <memory>

#include "numeric.h"
#include "shell_ctx.h"

namespace rknn::detail {
static uint64_t tensor_plane(const TensorRef& t) {
    uint64_t hw = (uint64_t)t.dims[2] * t.dims[3];
    // Spatial feature planes use four-point alignment; 1x1 classifier tensors
    // are packed directly. Vendor CPU oracle includes the 7x7 -> 52 case.
    return hw == 1 ? hw : (hw + 3) & ~uint64_t(3);
}

int tensor_extent(const TensorRef& t, TensorExtent& extent) {
    if (!t.ndim || t.ndim > 8 || (t.dtype_code != 3 && t.dtype_code != 10))
        return -6;
    uint64_t n = 1;
    for (uint32_t i = 0; i < t.ndim; i++) {
        if (!t.dims[i] || n > UINT32_MAX / t.dims[i])
            return -5;
        n *= t.dims[i];
    }
    extent.logical_elements = extent.storage_elements = n;
    if (t.native_ndim == 5 && t.ndim == 4) {
        const auto* d = t.native_dims;
        if (d[0] != t.dims[0] || d[2] != t.dims[2] || d[3] != t.dims[3] || !d[1] || !d[4] ||
            (uint64_t)d[1] * d[4] < t.dims[1])
            return -6;
        n = tensor_plane(t);
        for (uint32_t dim : {d[0], d[1], d[4]}) {
            if (!dim || n > UINT32_MAX / dim)
                return -5;
            n *= dim;
        }
        extent.storage_elements = n;
    } else if (t.native_ndim) {
        if (t.native_ndim != t.ndim)
            return -6;
        for (uint32_t i = 0; i < t.ndim; i++)
            if (t.native_dims[i] != t.dims[i])
                return -6;
    }
    return 0;
}

uint64_t tensor_offset(const TensorRef& t, uint64_t logical) {
    if (t.ndim != 4 || t.native_ndim != 5)
        return logical;
    uint64_t w = logical % t.dims[3];
    logical /= t.dims[3];
    uint64_t h = logical % t.dims[2];
    logical /= t.dims[2];
    uint64_t c = logical % t.dims[1], n = logical / t.dims[1];
    uint64_t c1 = t.native_dims[1], c2 = t.native_dims[4];
    return (((n * c1 + c / c2) * tensor_plane(t) + h * t.dims[3] + w) * c2 + c % c2);
}

// Gather first: source and destination can alias the same activation allocation.
int transform_tensor(const TensorRef& src, const TensorRef& dst, std::span<const uint8_t> input,
                     std::span<uint8_t> output, std::span<const uint32_t> permutation) {
    if (input.empty() || output.empty() || src.dtype_code != dst.dtype_code)
        return -6;
    TensorExtent source_extent, destination_extent;
    int          ret = tensor_extent(src, source_extent);
    if (ret)
        return ret;
    ret = tensor_extent(dst, destination_extent);
    if (ret)
        return ret;
    uint64_t   bytes       = dtype_bytes(src.dtype_code);
    const auto count       = source_extent.logical_elements;
    const auto in_storage  = source_extent.storage_elements;
    const auto out_storage = destination_extent.storage_elements;
    if (count != destination_extent.logical_elements)
        return -6;
    if (in_storage > input.size() / bytes || out_storage > output.size() / bytes)
        return -5;
    if (!permutation.empty()) {
        if (permutation.size() != src.ndim || dst.ndim != src.ndim)
            return -6;
        uint32_t used = 0;
        for (uint32_t i = 0; i < src.ndim; i++) {
            uint32_t axis = permutation[i];
            if (axis >= src.ndim || (used & (1u << axis)) || dst.dims[i] != src.dims[axis])
                return -6;
            used |= 1u << axis;
        }
    }
    std::vector<uint8_t> gathered(count * bytes);
    for (uint64_t i = 0; i < count; i++) {
        uint64_t si = i;
        if (!permutation.empty()) {
            uint64_t at = i, coords[8] = {};
            for (uint32_t j = dst.ndim; j-- > 0;) {
                coords[permutation[j]] = at % dst.dims[j];
                at /= dst.dims[j];
            }
            si = 0;
            for (uint32_t j = 0; j < src.ndim; j++)
                si = si * src.dims[j] + coords[j];
        }
        memcpy(gathered.data() + i * bytes, input.data() + tensor_offset(src, si) * bytes, bytes);
    }
    if (dst.ndim == 4 && dst.native_ndim == 5)
        memset(output.data(), 0, out_storage * bytes);
    for (uint64_t i = 0; i < count; i++)
        memcpy(output.data() + tensor_offset(dst, i) * bytes, gathered.data() + i * bytes, bytes);
    return 0;
}

int copy_reshape_output(const TensorRef& source, const TensorRef& destination,
                        std::span<const uint8_t> input, std::span<uint8_t> output) {
    return transform_tensor(source, destination, input, output);
}

namespace {
struct TensorMapping {
    GemBuffer*         buffer = nullptr;
    uint64_t           offset = 0;
    std::span<uint8_t> bytes;
};

int map_tensor(Context& context, uint32_t index, TensorMapping& mapping) {
    const auto& model = context.model;
    if (index >= model.tensors.size())
        return -5;
    const auto& tensor = model.tensors[index];
    if (tensor.kind == 3) {
        mapping.buffer = &context.buffer(rknn::BufferSlot::Activations);
        mapping.offset = tensor.internal_off;
    } else if (tensor.kind == 2) {
        const auto it = std::ranges::find(model.output_tensors, static_cast<int>(index));
        if (it == model.output_tensors.end())
            return -5;
        const auto output_index = static_cast<size_t>(it - model.output_tensors.begin());
        if (output_index && output_index - 1 >= context.extra_out.size())
            return -5;
        mapping.buffer = output_index ? &context.extra_out[output_index - 1]
                                      : &context.buffer(rknn::BufferSlot::Output);
    } else {
        return -6;
    }
    auto& buffer = *mapping.buffer;
    if (!buffer.map || mapping.offset > buffer.size || tensor.size > buffer.size - mapping.offset)
        return -5;
    mapping.bytes = {static_cast<uint8_t*>(buffer.map) + mapping.offset, tensor.size};
    return 0;
}

int sync_mapping(Context& context, const TensorMapping& mapping, SyncDirection direction) {
    return context.drv.mem_sync(*mapping.buffer, mapping.offset, mapping.bytes.size(), direction);
}

using OwnedAllocation = std::unique_ptr<void, decltype(&std::free)>;
struct PreparedOutput {
    std::vector<uint8_t> data;
    OwnedAllocation      allocation{nullptr, &std::free};
};

int prepare_output(Context& context, const rknn_output& output, PreparedOutput& prepared) {
    const int index = io_tensor_index(context.model, output.index, false);
    if (index < 0)
        return -5;
    const auto&  tensor = context.model.tensors[index];
    TensorExtent extent;
    if (const int error = tensor_extent(tensor, extent))
        return error;
    const auto count = extent.logical_elements;
    const auto bytes = count * (output.want_float ? sizeof(float) : dtype_bytes(tensor.dtype_code));
    if (bytes > UINT32_MAX || (output.is_prealloc && (!output.buf || output.size < bytes)))
        return -5;
    TensorMapping mapping;
    if (const int error = map_tensor(context, index, mapping))
        return error;
    if (const int error = sync_mapping(context, mapping, SyncDirection::FromDevice))
        return error;

    auto logical        = tensor;
    logical.native_ndim = 0;
    std::vector<uint8_t> raw(count * dtype_bytes(tensor.dtype_code));
    if (const int error = transform_tensor(tensor, logical, mapping.bytes, raw))
        return error;
    if (!output.want_float) {
        prepared.data = std::move(raw);
        return 0;
    }
    prepared.data.resize(bytes);
    float scale = tensor.scale;
    if (scale == 0.0f) {
        const float range = tensor.qmax - tensor.qmin;
        scale             = range != 0.0f ? range / 255.0f : 1.0f;
    }
    for (uint64_t i = 0; i < count; ++i) {
        float value;
        if (tensor.dtype_code == 3) {
            value = (static_cast<int8_t>(raw[i]) - tensor.zp) * scale;
        } else {
            uint16_t half;
            std::memcpy(&half, raw.data() + i * sizeof(half), sizeof(half));
            value = f16_to_f32(half);
        }
        std::memcpy(prepared.data.data() + i * sizeof(value), &value, sizeof(value));
    }
    return 0;
}
}  // namespace

int execute_cpu_op(Context& context, const OpRef& operation) {
    if (operation.type == "InputOperator" || operation.type == "OutputOperator")
        return 0;
    if ((operation.type != "Reshape" && operation.type != "Transpose") ||
        operation.inputs.empty() || operation.outputs.size() != 1)
        return -6;
    if (operation.type == "Transpose" && operation.permutation.empty())
        return -6;
    TensorMapping source, destination;
    if (const int error = map_tensor(context, operation.inputs.front(), source))
        return error;
    if (const int error = map_tensor(context, operation.outputs.front(), destination))
        return error;
    if (const int error = sync_mapping(context, source, SyncDirection::FromDevice))
        return error;
    // Preserve device-written padding and neighboring activations before CPU writes.
    if (const int error = sync_mapping(context, destination, SyncDirection::FromDevice))
        return error;
    const auto& input       = context.model.tensors[operation.inputs.front()];
    const auto& output      = context.model.tensors[operation.outputs.front()];
    const auto  permutation = operation.type == "Transpose"
                                  ? std::span<const uint32_t>{operation.permutation}
                                  : std::span<const uint32_t>{};
    if (const int error =
            transform_tensor(input, output, source.bytes, destination.bytes, permutation))
        return error;
    return sync_mapping(context, destination, SyncDirection::ToDevice);
}

int get_outputs(Context& context, std::span<rknn_output> outputs) {
    if (outputs.empty() || outputs.size() > context.model.output_tensors.size())
        return -5;
    std::vector<PreparedOutput> prepared(outputs.size());
    std::vector<bool>           selected(context.model.output_tensors.size(), false);
    for (size_t i = 0; i < outputs.size(); ++i) {
        const auto& output = outputs[i];
        if (output.index >= selected.size() || selected[output.index])
            return -5;
        selected[output.index] = true;
        if (const int error = prepare_output(context, output, prepared[i]))
            return error;
    }
    // Allocation remains owned here until every result is ready. Failure leaves
    // caller buffers unchanged and releases all allocations automatically.
    for (size_t i = 0; i < outputs.size(); ++i) {
        if (outputs[i].is_prealloc)
            continue;
        prepared[i].allocation.reset(std::malloc(prepared[i].data.size()));
        if (!prepared[i].allocation)
            return -1;
    }
    for (size_t i = 0; i < outputs.size(); ++i) {
        if (!outputs[i].is_prealloc)
            outputs[i].buf = prepared[i].allocation.release();
        std::memcpy(outputs[i].buf, prepared[i].data.data(), prepared[i].data.size());
        outputs[i].size = static_cast<uint32_t>(prepared[i].data.size());
    }
    return 0;
}
}  // namespace rknn::detail
