<div align="center">

# rk-forge

**面向 Rockchip RK3506 的主线优先（mainline-first）嵌入式 Linux 开发工作空间**
有序补丁库 · 诚实差距报告 · forge 构建编排器 · 0→1 教程

[![License](https://img.shields.io/badge/License-MIT-orange?style=flat-square)](LICENSE)
[![Kernel](https://img.shields.io/badge/Kernel-mainline%207.1-blue?style=flat-square)](#-板上已验证)
[![U-Boot](https://img.shields.io/badge/U--Boot-mainline%202026.07-blue?style=flat-square)](#-板上已验证)
[![Mainline](https://img.shields.io/badge/Mainline-first%20%E2%9C%93-brightgreen?style=flat-square)](#-这是什么)
[![Board](https://img.shields.io/badge/board-RK3506B%20verified-brightgreen?style=flat-square)](#-板上已验证)
[![WSL2](https://img.shields.io/badge/WSL2-tested-brightgreen?style=flat-square)](QUICK_START.md)
[![Docs](https://img.shields.io/badge/docs-online%20%E2%86%92-blue?style=flat-square)](https://awesome-embedded-learning-studio.github.io/rk-forge/)
[![Deploy](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/actions/workflows/deploy.yml/badge.svg)](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/actions/workflows/deploy.yml)

[English](README.en.md) · 中文

</div>

---

## 这是什么

rk-forge 服务**没人服务的 RK3506**：把最新主线 Linux 跑起来，并**诚实报告还差什么**。

它**不是**又一个 Armbian / Yocto / 厂商 BSP 镜像，而是四件事：

1. **有序补丁库** —— quilt 风格 `series`，`git am` 落真实 commit、可 bisect、失败原子回滚（修掉"只打最后一个补丁、坏了静默跳过"的老毛病）。
2. **诚实的差距报告** —— [document/sdk-diff.md](document/sdk-diff.md) 逐子系统告诉你：vendor BSP 有什么 / 主线有什么 / 差什么 / 还能不能 boot。
3. **forge 构建编排器** —— 一条 `forge.sh all` 把 `setup → build → pack → assemble` 收口，DAG 依赖 + 内容哈希增量跳过，取代 RK-SDK `build.sh` 每次全量重编的体验。
4. **0→1 教程** —— 从空机器到 RK3506 主线启动到 UART 登录的完整可复现路径，每章配真实板上 UART 抓取，绝不合成。

**核心命题（已核实并板上验证）**：RK3506 的 SoC 地基——pinctrl + clock（自 Linux 6.19 起）、U-Boot SoC 支持（经 Jonas Karlman v2 系列已合并）——**全在主线**。所以对"主线启动"这件事，RK-SDK 整个坍缩成两样：① `rkbin`（DDR 初始化闭源 blob，绕不开，见 [诚实 blob 政策](#-诚实-blob-政策)）；② **一块板级设备树**（上游没有，rk-forge 来写）。rk-forge 的主要贡献就是这块 `.dts` + 一条诚实的路径。

> 别人卖成品饭；rk-forge 卖菜谱 + 灶 + 带你做饭的书，专做没人做的那道菜。

📖 **在线文档站**：<https://awesome-embedded-learning-studio.github.io/rk-forge/>

---

## ✅ 板上已验证

不是 PPT，是真板子（AES-RK3506B，RK3506B / Cortex-A7×3）上跑通的能力。完整取证日志见 [document/logs/](document/logs/)。

| 能力 | 状态 | 说明 |
|------|------|------|
| 主线 U-Boot 2026.07-rc4 引导 | ✅ 板上 | 过 SPL 到交互提示符 |
| 主线 Linux 7.1 SMP 启动 | ✅ 板上 | A7×3 全起来，ttyS0 console |
| UBIFS rootfs + RW 持久 | ✅ 板上 | `/persist.log` 跨冷重启存活，UBIFS recovery 通过 |
| SPI-NAND 读写（W25N04KV + SFC） | ✅ 板上 | DLL 调谐移植，80MHz 读稳，写侧加 powergood + WPEN |
| SD 卡启动（纯 SD，RKFW） | ✅ 板上 | kernel + rootfs 都从 SD ext4 启动到 buildroot shell |
| Ethernet 双口（gmac0 + gmac1） | ✅ 板上 | YT8512，RMII |
| SPI + MMC/SD | ✅ 板上 | 板载存储三件套 |
| I2C×3 + UART2（RMIO 交叉开关） | ✅ 板上 | RMIO mux 移植 |
| Audio（ES8388 + SAI1 + DMA） | ✅ 数字链路 | 声卡注册、aplay/mpg123 48k 干净播完 |
| WiFi（RTL8733BU，wlan0/wlan1） | ✅ 板上 probe | out-of-tree 驱动搬到 7.1，全链 probe |

启动前段（DDR / secure）仍借 `rkbin` blob——这是 RK 平台的硬现实，详见 [诚实 blob 政策](#-诚实-blob-政策)。

---

## 🚀 快速开始

```bash
./scripts/doctor.sh            # 检查 host 依赖 + armhf 交叉工具链（缺啥会给 apt 命令）
source scripts/env-setup.sh    # 导出 ARCH=arm / CROSS_COMPILE=arm-none-linux-gnueabihf-
bash scripts/forge.sh all      # setup → build → pack → assemble → board/aes/out/update.img
```

`forge` 是单一入口编排器，常用子命令：

```bash
bash scripts/forge.sh setup            # 拉源码树 + WiFi 驱动 + 应用补丁库
bash scripts/forge.sh status           # 看哪些 stage 是最新（增量跳过一目了然）
bash scripts/forge.sh assemble --sd    # 出 SD 卡镜像（RKFW，本板 ROM 只认 RK-tool 卡）
bash scripts/forge.sh clean --full     # 干净重建
```

> **zsh 用户**：始终用 `bash scripts/forge.sh ...` 调用——lib 脚本依赖 `BASH_SOURCE`，在 zsh 下为空。

烧录与上板引导见 [QUICK_START.md](QUICK_START.md) 与 [document/tutorial/boot/](document/tutorial/boot/)。

---

## 📖 学习路径

bring-up 弧线分五个阶段，按顺序读最顺：先把板子**启动**起来，再让它**持久登录**，接着点亮**外设**，然后补 **SD 卡**这条第二条启动路，最后用 **forge 编排器**收口。

| 阶段 | 主题 | 内容 | 状态 |
|------|------|------|------|
| 🚀 | [引导启动](document/tutorial/boot/) | 工具链 → U-Boot 与 rkbin → 板级设备树 | ✅ |
| 📦 | [根文件系统](document/tutorial/rootfs/) | buildroot → init 时序 → UBIFS 与 loader 弱写 saga | ✅ |
| 🔌 | [外设](document/tutorial/peripherals/) | Ethernet/SPI/MMC → USB → WiFi → I2C/UART → Audio | ✅ 持续扩展 |
| 💾 | [SD 卡启动](document/tutorial/sd-boot/) | SD-1 手动引导 → SD-2 autoboot | ✅ |
| 🛠️ | [forge 编排器](document/tutorial/forge/) | 一条命令收口整条构建链 | ✅ |

踩过的坑按故障域归档在 [document/pitfalls/](document/pitfalls/)，原始时间线在 [document/notes/](document/notes/)。

---

## 📦 仓库结构

```
scripts/
  forge.sh                     ★ 单一入口编排器（setup/build/pack/assemble/all/clean/status）
  lib/{env,log,stage,toolchain,host,rkbin}.sh   共享库；stage.sh = 内容哈希增量跳过
  apply-series.sh              有序补丁库（git am + 真干跑 --check + 原子回滚）
  fit-pack.py · rkfw-pack.py   纯 Python 打包器，取代 vendor mkimage / afptool / rkImageMaker
  build-{linux,uboot,rootfs}.sh · pack-{loader,fit,sd,ubifs}.sh · assemble-update.sh
  doctor.sh · env-setup.sh · fetch-deps.sh · flash-sd.sh
patches/{linux,uboot}/series   有序补丁序列（[mainline]/[uboot] 前缀）
board/                         aes/(构建工作区:fit/rootfs/buildroot-external) · rk3506-evb/(板 config)
third_party/                   rkbin(pinned submodule) · buildroot · src/(linux·uboot 源树,fetch-deps 管理)
reference/                     vendor-sdk(参照/萃取池,非构建依赖)
config/                        forge.env · toolchain.conf（声明式配置）
document/                      tutorial · pitfalls · notes · logs · sdk-diff
```

---

## 🎯 支持的开发板

| 板卡 | 芯片 | 状态 |
|------|------|------|
| AES-RK3506B | Rockchip RK3506B（Cortex-A7×3，32-bit armhf） | ✅ 完整支持 |

其他 RK3506 板卡欢迎提 PR 补板级设备树。

---

## 🧭 诚实 blob 政策

rk-forge 主线优先、blob 最小化，但**不 blob 纯洁主义**：当前绕不开的闭源固件（`rkbin` 的 DDR/SPL/TEE）——先用、文档化、追踪消除路径。启动前段之外，**Linux 内核、U-Boot proper、设备树全是开源主线**。完整清单与消除路径见 [document/blobs.md](document/blobs.md)。

---

## 🤝 贡献

欢迎补丁、板级 DT、教程、问题反馈。开始前先读 [CONTRIBUTING.md](CONTRIBUTING.md)。

- **补丁**：quilt 风格有序 `patches/<component>/series`，一个补丁一个 commit，`git format-patch` 生成并带 `Signed-off-by`，前缀 `[mainline]` / `[uboot]`。
- **bash leaves 须可被 Python 包裹**：干净 stdin/stdout/exit，**无** `/dev/tty` 交互（所以 `doctor.sh` 只打印 apt 命令、不自动装）。
- **增量构建**：用 `lib/stage.sh` 内容哈希跳过——别重编输入没变的 stage。
- 🐛 [报告 Bug](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/issues) · 🔧 [提交 PR](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/pulls)

---

## 📄 协议

MIT，详见 [LICENSE](LICENSE)。源自 GPL SDK 的补丁保留 GPL-2.0 并在补丁头标注。`rkbin` 为 Rockchip 专有固件，仅以 pinned 子模块引用，**不拷入本仓库**、不再分发。

---

<div align="center">

**做 RK 的 imx-forge 兄弟项目，专啃没人做的 RK3506，把最新 Linux 跑起来并诚实报告差距。**

[⭐ Star](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge) · [🍴 Fork](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/fork) · [📢 Issues](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/issues)

</div>
