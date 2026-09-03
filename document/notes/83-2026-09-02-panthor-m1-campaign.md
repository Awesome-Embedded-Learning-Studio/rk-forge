# 83 — panthor 战役 M1：内核侧全通，mesa cs_builder 崩点攻坚（2026-09-02）

> 战役七续。目标：note 76 §3.4 的 M1 验收（eglinfo/renderer 无 llvmpipe）。
> 本文覆盖：内核侧剩余数据坑全补、mesa 用户态崩点的完整取证链、
> 未闭环的 csf_oom_handler_init 崩点分析。

## 0. 结果

| 项 | 结果 |
|---|---|
| **GROUP_CREATE 打通** | ✅ 根因：CSG control 的 suspend_size/protm_suspend_size 镜像初值 0，group_create 拿 0 alloc suspend buf 返 -ENOSPC（eglinfo 首个 GROUP_CREATE 即败）。修：假 MCU boot 时全 8 组补写 0x1000/0x800 |
| **cs_reg_count 0→256** | ✅ 根因：CS control（8 CSG × 8 流，共 64 槽）镜像无初值，features=0 → 内核 cs_reg_count=1 → mesa cs_builder 寄存器空间塌缩。修：假 MCU 全 64 槽写 features=0x000708ff（256 工作寄存器/8 记分板/C+F+T）+ input/output VA（shared 段内 0x04003400/0x04007400 + idx*0x10） |
| **取证工具链** | ✅ 内核 ftrace 未编 → 自建：fops ioctl/mmap/get_unmapped_area 打点包装 + `kernel/exception-trace`（用户态崩溃 PC/寄存器进 dmesg）+ ddebs 符号包 addr2line + `sim/elfnear.py`/guest 内 PT_LOAD dump（mini readelf） |
| **M1 验收** | ⛔ 未达：mesa 26.0.3 在 `csf_oom_handler_init → csf_init_context_v10 → cs_function_end`（cs_builder.h:2371）稳定段错误——写 `[x9+小imm]`、x9=NULL。内核侧 ioctl/mmap 全绿（GROUP/HEAP/VM/BO 全 ret=0），崩点纯用户态 |
| **fixture 欠账 +1** | CS features 真机值待采（现占位 0x000708ff）——note 76 §六.2 清单再添一项 |

## 1. 内核侧数据坑全补（QEMU 假 MCU）

固件镜像的 shared 段（64KB）**只有 124B 文件初值**（GLB+CSG0 control 的
部分字段）——真机上 suspend size、全部 CS control 都由 MCU 上电填写。假 MCU
mcu_boot 的完整动作（hw/arm/rk3588-lite.c）：

```
walk AS0 0x04000000（GLB control）
  → 写 version=0x01050000
walk 0x04001000（CSG control 区，stride 0xa0）
  → 8 组各写 suspend_size=0x1000 / protm_suspend_size=0x800
  → 64 个 CS 槽（+0x40+cs*0xc 每组内）各写
    features=0x000708ff / input_va / output_va
  → MCU_STATUS=ENABLED + JOB_INT_GLOBAL_IF
```

校验链（内核 panthor_fw.c）：组间 "Expecting identical CSG slots"（suspend
size 全同）、流间 "Expecting identical CS slots"（features 全同）——**只写
CSG0 会炸 CSG 校验、只写 CS0 会炸 CS 校验，必须全量**。

## 2. mesa 崩点取证链（方法论沉淀）

1. `/proc/sys/debug/exception-trace = 1` → 用户态 SIGSEGV 的
   `pc/lr/全部寄存器`进 dmesg（ESR 0x92000047 = level-3 写 fault）
2. launchpad `mesa_26.0.3.orig.tar.xz`（源码）+ `ddebs.ubuntu.com`
   `mesa-libgallium-dbgsym_26.0.3-1ubuntu1_arm64.ddeb`（符号）→ 宿主
   addr2line 直接出 inline 栈：
   `cs_function_end ← csf_init_context_v10 ← csf_oom_handler_init`
3. guest 内无 binutils/gdb/strace/ftrace（最小系统+无网）→ `sim/elfnear.py`
   （纯 stdlib mini readelf）+ guest 内 PT_LOAD dump 指令字节
4. 内核打点：panthor fops 的 ioctl/mmap/get_unmapped_area 三层包装
   （PANTHORIOCTL/SIMMMAP/SIMMUA 前缀，**战役后撤**）

### 崩点现状

- pc=libgallium+0x13bf218：`str x8, [x9, #imm]`，x9=NULL（x24/x25 同 0）
- cs_reg_count=256 修复后**崩点 PC 不变**——非寄存器数不足所致
- 候选二选一（未定）：
  a. `cs_function_end` 栈数组 `masks/ranges[SAVE_RESTORE_MAX_OPS]` 越界
     （dirty 位图异常展开）
  b. python 主线程 8MB 栈被 cs_builder 宏展开的大函数族吃穿（guard page）
- 剪枝记录：cs_bo/reg_save_bo 的 ptr.cpu 必非 NULL（bo_create mmap 失败
  早退）；bo_cache 命中保留映射；flush_id mmap(1<<56) 未复现失败
  （先前手工 mmap EINVAL 是 ctypes 未设 argtypes 的 32 位截断，**假线索**）

## 3. 下一步（M1 续）

1. **反汇编定位 x9 来源**：拉 Ubuntu arm64 二进制 deb（ports pool 路径待
   找对）或 guest 内拖 xz 压缩的 .so 出来做宿主 objdump
2. **csif A/B**：真机 CS features fixture 采集（一次性 debug dump，note 76
   §六.2）——work regs 真值可能是 0xbf+1=192 而非 256；顺带 unpreserved
3. 若 a/b 都排除 → 栈深问题：改用 C 程序（非 python ctypes）跑同 EGL 序列
   复测，绕开 python 栈布局差异
4. restore 迟发锁死二分（note 82 §5 挂账不变）

## 4. 落库清单

- `third_party/qemu` hw/arm/rk3588-lite.c：假 MCU 补写 CSG suspend/protm +
  64 CS control（M1 内核侧全通）
- `sim/glesprobe.py`（GBM 平台 GLES context 探针，v4：config+surfaceless
  context）+ `sim/elfnear.py`（mini readelf）
- 内核树诊断打点（PANTHORIOCTL/SIMGRP/SIMGLB/SIMCSREG/SIMMMAP/SIMMUA）：
  **M1 期间保留，收役统一撤**

## 7. 研究机装备升级（2026-09-03，用户提议）

M1 攻坚暴露最小 rootfs 的诊断真空（无 strace/gdb/binutils/ftrace，ioctl 靠
printk 打点、符号靠手写 mini-readelf、崩点只能 exception-trace）。一次补齐：

- **rootfs**（packages.list +5）：strace / binutils / gdb / xz-utils / sudo。
  sudoers NOPASSWD 由 stage 注入（`_provision_runtime_config` 写
  /etc/sudoers.d/010-dev-nopasswd——凭据不进 tar 的设计不变）。
- **内核**（kernel.config）：FTRACE + KPROBES + KPROBE_EVENTS +
  FUNCTION_TRACER + DYNAMIC_FTRACE + DEBUG_FS。
- **工具**：`sim/resboot.py`（研究机冷启：panthor 在、GDM mask、串口 4446）。
- 重建链踩两坑记 gotchas：WSL binfmt（§9，含 O-flag 二刷）、fakeroot
  stale-inode（§10，state 按 inode 索引，stage 重铺后须重跑 stage 重存 state）。
- 验证：sudo -n 免密 ✓、strace 6.19/gdb/readelf/xz 在位 ✓、panthor M0
  不回退（`Initialized panthor 1.8.0 on minor 1` + renderD128）✓。
- 登录变化：root 不再免密——用 rk-forge/rk-forge（forge.yaml §5.2 教学默认），
  sercmd 探测需适配 `$` 提示符。
