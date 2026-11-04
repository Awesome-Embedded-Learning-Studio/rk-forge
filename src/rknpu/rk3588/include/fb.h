// SPDX-License-Identifier: MIT
/* 极简 FlatBuffers 只读访问器(schema 无关机制层)
 *
 * NN_BG 已实证是 FlatBuffers(dsh-008):标准 little-endian、vtable soffset 为负、
 * 根表定位非标准(见 loader)。这里只提供机制,字段语义由 schema 层给偏移。
 */
#pragma once
#include <cstdint>
#include <cstring>

namespace rknn {
namespace fb {

struct Table {
    const uint8_t* buf = nullptr;  // 整个 flatbuffer 基址
    uint64_t       pos = 0;        // 表起点(相对 buf)

    bool valid() const { return buf != nullptr; }

    // vtable 相对表起点:*(i32*)pos 为负偏移
    uint64_t vtable() const {
        int32_t soff;
        std::memcpy(&soff, buf + pos, 4);
        return pos - (uint64_t)soff;
    }
    // 字段在表内的偏移; 不存在返回 0
    uint64_t field_off(uint32_t slot) const {
        uint16_t vt_len;
        std::memcpy(&vt_len, buf + vtable(), 2);
        uint64_t idx = 4 + slot * 2;
        if (idx >= vt_len)
            return 0;
        uint16_t off;
        std::memcpy(&off, buf + vtable() + idx, 2);
        return off ? (uint64_t)off : 0;
    }

    template <typename T>
    bool get_scalar(uint32_t slot, T* out) const {
        uint64_t off = field_off(slot);
        if (!off)
            return false;
        std::memcpy(out, buf + pos + off, sizeof(T));
        return true;
    }

    // 间接字段:uoffset 相对字段存储位置(FlatBuffers 语义),非表起点
    bool get_table(uint32_t slot, Table* out) const {
        uint64_t off = field_off(slot);
        uint32_t uo;
        if (!off || !get_scalar(slot, &uo))
            return false;
        out->buf = buf;
        out->pos = pos + off + (uint64_t)uo;
        return true;
    }

    // string: 返回 {指针, 长度}
    bool get_str(uint32_t slot, const char** s, uint32_t* len) const {
        uint64_t off = field_off(slot);
        uint32_t uo;
        if (!off || !get_scalar(slot, &uo))
            return false;
        uint64_t sp = pos + off + (uint64_t)uo;
        std::memcpy(len, buf + sp, 4);
        *s = (const char*)(buf + sp + 4);
        return true;
    }

    // vector 起点(跳过长度 u32)与元素数
    bool get_vec(uint32_t slot, const uint8_t** data, uint32_t* n) const {
        uint64_t off = field_off(slot);
        uint32_t uo;
        if (!off || !get_scalar(slot, &uo))
            return false;
        uint64_t vp = pos + off + (uint64_t)uo;
        std::memcpy(n, buf + vp, 4);
        *data = buf + vp + 4;
        return true;
    }
};

}  // namespace fb
}  // namespace rknn
