# Ch1 — 工具链：arm-linux-gnueabihf

> 状态：草稿。RK3506 与 i.MX6ULL 同为 Cortex-A7 / armhf，工具链内容近乎一致。

## 前言

RK3506 是 32-bit ARM Cortex-A7（+ Cortex-M0），硬浮点。所以交叉工具链是
**`arm-linux-gnueabihf`**（`hf` = hard-float；Cortex-A7 有 VFPv4/NEON），`ARCH=arm`。

## 实验环境

| 项 | 值 |
|---|---|
| Host | WSL2 (Ubuntu) — `./scripts/doctor.sh` 会检测并提示 |
| 目标架构 | ARMv7-A, armhf (Cortex-A7) |
| 工具链包 | `gcc-arm-linux-gnueabihf` |

## 第一步：检查环境

```bash
./scripts/doctor.sh
```

缺包时它会把 `sudo apt install ...` 打到 stdout（**不自动装**，保持可被脚本/Python 调用）。

## 第二步：导出环境

```bash
source scripts/env-setup.sh
# ARCH=arm  CROSS_COMPILE=arm-linux-gnueabihf-
```

## 第三步：验证产物是 32-bit ARM

（构建后）用 `${CROSS_COMPILE}readelf -h <elf>` 看到 `Machine: ARM`。

## 踩坑记录

- WSL2 下 USB 烧录（rkdeveloptool）需要 Windows 侧 `usbipd-win`；SD 卡烧录可直接走。
- 别装成 soft-float 的 `gcc-arm-linux-gnueabi`（无 `hf`）——RK3506 要硬浮点。
