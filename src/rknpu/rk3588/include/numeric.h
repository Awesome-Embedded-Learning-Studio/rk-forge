// SPDX-License-Identifier: MIT
#pragma once
#include <bit>
#include <cstdint>

#include "model.h"

namespace rknn::detail {
inline uint16_t f32_to_f16(float f) {
    const auto u    = std::bit_cast<uint32_t>(f);
    uint16_t   sign = (uint16_t)((u >> 16) & 0x8000);
    uint32_t   exp  = (u >> 23) & 0xff;
    uint32_t   man  = u & 0x7fffff;
    if (exp == 0xff)
        return (uint16_t)(sign | (man ? 0x7e00 : 0x7c00));
    int e = (int)exp - 127 + 15;
    if (e >= 0x1f)
        return (uint16_t)(sign | 0x7c00);
    if (e <= 0) {
        if (e < -10)
            return sign;
        uint32_t m     = man | 0x800000;
        uint32_t shift = (uint32_t)(1 - e + 13);
        uint32_t rem   = m & ((1u << shift) - 1);
        m >>= shift;
        uint32_t half = 1u << (shift - 1);
        if (rem > half || (rem == half && (m & 1)))
            m++;
        return (uint16_t)(sign | m);
    }
    uint32_t m   = man >> 13;
    uint32_t rem = man & 0x1fff;
    if (rem > 0x1000 || (rem == 0x1000 && (m & 1))) {
        m++;
        if (m == 0x400) {
            m = 0;
            e++;
        }
        if (e >= 0x1f)
            return (uint16_t)(sign | 0x7c00);
    }
    return (uint16_t)(sign | ((uint32_t)e << 10) | m);
}

inline float f16_to_f32(uint16_t h) {
    uint32_t sign = (uint32_t)(h & 0x8000) << 16;
    uint32_t exp  = (h >> 10) & 0x1f;
    uint32_t man  = h & 0x3ff;
    uint32_t u;
    if (exp == 0) {
        if (man == 0) {
            u = sign;
        } else {
            int e = -14;
            while (!(man & 0x400)) {
                man <<= 1;
                e--;
            }
            man &= 0x3ff;
            u = sign | ((uint32_t)(e + 127) << 23) | (man << 13);
        }
    } else if (exp == 0x1f) {
        u = sign | 0x7f800000 | (man << 13);
    } else {
        u = sign | ((exp - 15 + 127) << 23) | (man << 13);
    }
    return std::bit_cast<float>(u);
}

inline uint32_t dtype_bytes(int code) {
    return code == 3 ? 1 : 2;
}

inline uint32_t shape_elems(const TensorRef& t) {
    uint32_t n = 1;
    if (t.ndim == 0)
        return 0;
    for (uint32_t i = 0; i < t.ndim; i++)
        n *= t.dims[i];
    return n;
}

inline int io_tensor_index(const Model& m, uint32_t idx, bool input) {
    const std::vector<int>& map = input ? m.input_tensors : m.output_tensors;
    uint32_t                num = input ? m.input_num : m.output_num;
    if (!num)
        num = (uint32_t)map.size();
    if (idx >= num || idx >= map.size())
        return -1;
    int ti = map[idx];
    if (ti >= 0 && (size_t)ti < m.tensors.size())
        return ti;
    return -1;
}

}
