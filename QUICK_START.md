# 快速开始

最短路径：把 RK3506 主线系统从源码构建到可烧 `update.img`。完整学习路径见 [document/tutorial/](document/tutorial/)，在线文档见 <https://awesome-embedded-learning-studio.github.io/rk-forge/>。

## 1. 检查 host

```bash
./scripts/doctor.sh
```

探测 host 构建依赖 + 交叉工具链（`arm-none-linux-gnueabihf`，即 Arm GNU Toolchain）、检测 WSL2，缺什么就打印精确的 `sudo apt install ...`。**绝不自动安装**（保持脚本可被 Python 包裹）。

> **交叉工具链不是 apt 包装的**：本项目的交叉编译器是 **Arm GNU Toolchain 15.2.Rel1**（前缀 `arm-none-linux-gnueabihf-`），手动装到 `/opt`（路径以 [config/toolchain.conf](config/toolchain.conf) 为准，从 <https://developer.arm.com/downloads> 下载）。Debian 的 `gcc-arm-linux-gnueabihf` 是**另一把**工具链（前缀不同、gcc 版本不同），装了也不满足。下面的 apt 行只管 **host** 构建依赖。

全新 WSL2 环境通常需要（**仅 host 依赖**）：

```bash
sudo apt install device-tree-compiler bison flex cpio libssl-dev libncurses-dev \
  python3-pyelftools mtd-utils gdisk
# mtd-utils → pack-ubifs 的 mkfs.ubifs/ubinize；gdisk → pack-sd 的 sgdisk
```

> 本项目深度 WSL2 友好（Mirrored 网络模式可直通开发板，USB 设备直通用于烧录/串口）。

## 2. 导出工具链环境（每个 shell）

```bash
source scripts/env-setup.sh    # 设置 ARCH=arm, CROSS_COMPILE=arm-none-linux-gnueabihf-
```

## 3. 一条命令构建

```bash
bash scripts/forge.sh all      # setup → build → pack → assemble（默认 NAND，带首启置备）
```

`forge` 是单一入口编排器，按 DAG 跑各 stage，输入没变的 stage 用内容哈希跳过。常用子命令：

```bash
bash scripts/forge.sh setup            # 初始化 rkbin submodule + 拉源码树 + WiFi 驱动 + 应用补丁库（git am）
bash scripts/forge.sh build            # 编 kernel（uboot / buildroot 单独触发，会打印命令）
bash scripts/forge.sh pack             # 打 loader + FIT + stage/ubifs rootfs
bash scripts/forge.sh pack-sd          # 打可启动 SD 卡镜像（复用 NAND pack 产物）
bash scripts/forge.sh assemble --sd    # 组 RKFW SD 卡 update.img（本板 ROM 只认 RK-tool 卡）
bash scripts/forge.sh assemble --nand  # 组 NAND update.img
bash scripts/forge.sh status           # 哪些 stage 是最新
bash scripts/forge.sh clean --full     # 干净重建
```

> **zsh 用户**：始终用 `bash scripts/forge.sh ...` 调用——lib 脚本依赖 `BASH_SOURCE`，在 zsh 下为空。

产物落在 `board/aes/out/update.img`。

## OpenWrt rootfs profile（可选）

上面默认走 buildroot rootfs。想要 OpenWrt（opkg / LuCI / kmod 完整体验），同一条 `forge` 加 `--rootfs=openwrt` 即可——OpenWrt 自建 kernel + musl rootfs（kmod vermagic 天然匹配），rk-forge 照样负责 RK 专属打包，NAND 和 SD 两条路都板上验证过：

```bash
bash scripts/forge.sh all --rootfs=openwrt             # → update.img（NAND，首启从 RAM 置备 UBIFS）
bash scripts/forge.sh assemble --rootfs=openwrt --sd   # → SD 卡镜像（ext4 rootfs）
```

buildroot 仍是默认 profile，不加 flag 完全不受影响；两个 profile 共享 `out/`，切换前若指纹混淆用 `forge clean` 清一下。想读懂整条移植链路（vermagic 为什么钉死 kernel 自建、from-source 首启置备怎么杀三个坑），读 [OpenWrt 教程](document/tutorial/openwrt/00_openwrt.md)；架构取舍与加包的速查参考见 [board/aes/openwrt/README.md](board/aes/openwrt/README.md)。

## 4. 烧录 & 上板

- **SD 卡**：`forge assemble --sd` 出的镜像用 Rockchip SD 卡工具写入（本板 ROM 只从 RK-tool 卡启动，裸 `dd` 的 SD 不认）。
- **NAND**：Windows 用 RKDevTool，或 Linux 用 `rkdeveloptool`（Maskrom 模式）。

烧录、上电引导、UART 抓 log 的逐步操作见 [document/tutorial/boot/](document/tutorial/boot/) 与 [document/tutorial/sd-boot/](document/tutorial/sd-boot/)。
