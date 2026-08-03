# Contributing to rk-forge

rk-forge is mainline-first board-enablement for Rockchip RK3506B / RK3568 / RK3588. Before contributing:

## Setup
1. `./scripts/doctor.sh` — checks host deps + the cross toolchain (armhf for RK3506,
   aarch64 for RK3568/RK3588); prints the `sudo apt install ...` line if anything is missing.
2. `source scripts/env-setup.sh` — exports `ARCH` / `CROSS_COMPILE` (or just run
   `bash scripts/forge.sh ...`, which picks the toolchain from the selected board).

## Conventions
- **Patches**: quilt-style ordered `patches/<board>/<component>/series`, one patch per commit,
  generated with `git format-patch` (with `From`/`Subject`/
  `Signed-off-by`). Prefix `[mainline]` / `[uboot]`.
- **Bash leaves must stay Python-wrap-able**: clean stdin/stdout/exit codes, **no**
  interactive `/dev/tty` prompts (that's why `doctor.sh` just prints the apt command,
  and `merge_overlay`-style scripts must take a `--yes` flag when added).
- **Incremental builds**: use `lib/stage.sh` content-hash skipping — don't rebuild a
  stage whose inputs haven't changed.
- **Commits**: conventional `type(scope): subject`, signed-off (`git commit -s`).
- **C/C++ style**: `.clang-format` is authoritative.

## Scope

rk-forge 是 Rockchip RK3506B / RK3568 / RK3588 三块板的主线优先板级使能（board enablement）+ 教程，**不是**发行版镜像。当前范围内：三块板（RK3506B 完整支持、RK3568/RK3588 真机 boot 已验证，逐板进度见 [README.md](README.md)）、主线 Linux 7.1 + U-Boot 2026.07、有序补丁整合（integrator，不写原创内核驱动）、SPI-NAND(UBIFS) / eMMC / SD 卡多路启动、buildroot / OpenWrt / Ubuntu 三种 rootfs、VitePress 文档站。

明确不做：发行版镜像、原创内核驱动、blob 纯洁主义（`rkbin` 先用、文档化、追踪消除，见 [document/blobs.md](document/blobs.md)）。完整定位与已验证能力见 [README.md](README.md)。
