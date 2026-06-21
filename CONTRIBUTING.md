# Contributing to rk-forge

rk-forge is mainline-first board-enablement for RK3506. Before contributing:

## Setup
1. `./scripts/doctor.sh` — checks host deps + the `arm-linux-gnueabihf` toolchain;
   prints the `sudo apt install ...` line if anything is missing.
2. `source scripts/env-setup.sh` — exports `ARCH` / `CROSS_COMPILE`.

## Conventions
- **Patches**: quilt-style ordered `patches/<component>/series`, one patch per commit,
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

rk-forge 是 RK3506 的主线优先板级使能（board enablement）+ 教程，**不是**发行版镜像。当前范围内：RK3506B（单 SoC）、主线 Linux + U-Boot、有序补丁整合（integrator，不写原创内核驱动）、SPI-NAND（UBIFS）与 SD 卡双启动、buildroot 最小 rootfs、VitePress 文档站。

明确不做：发行版镜像、多 SoC、原创内核驱动、blob 纯洁主义（`rkbin` 先用、文档化、追踪消除，见 [document/blobs.md](document/blobs.md)）。完整定位与已验证能力见 [README.md](README.md)。
