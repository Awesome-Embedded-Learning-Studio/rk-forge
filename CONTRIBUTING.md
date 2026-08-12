# Contributing to rk-forge

rk-forge is a per-board, full-stack Rockchip Linux teaching + engineering project (RK3506B / RK3568 / RK3588) — mainline-first, honest on hardware, chasing fully-open. Before contributing:

## Setup
1. `python3 src/forge/cli.py doctor --board aes` — checks host deps + the cross
   toolchain (armhf for RK3506, aarch64 for RK3568/RK3588); prints the
   `sudo apt install ...` line if anything is missing.
2. `forge` reads the toolchain from the selected board's `config/boards/<id>.yaml`
   (no env sourcing). Run any stage as `python3 src/forge/cli.py <cmd> --board <id>`
   (or `pip install -e .` for the short `forge` form).

## Conventions
- **Patches**: quilt-style ordered `patches/<board>/{linux,uboot}/series`, one patch per commit,
  generated with `git format-patch` (with `From`/`Subject`). **Should carry
  `Signed-off-by`** (some legacy patches are still being brought up to date).
- **Bash leaves must stay Python-wrap-able**: clean stdin/stdout/exit codes, **no**
  interactive `/dev/tty` prompts (that's why `doctor.sh` just prints the apt command,
  and `merge_overlay`-style scripts must take a `--yes` flag when added).
- **Incremental builds**: use `lib/stage.sh` content-hash skipping — don't rebuild a
  stage whose inputs haven't changed.
- **Commits**: conventional `type(scope): subject`, signed-off (`git commit -s`).
- **C/C++ style**: `.clang-format` is authoritative.

## Scope

rk-forge 是 Rockchip RK3506B / RK3568 / RK3588 的**每板全栈教学 + 工程**项目——每块板都是一条能学到底的全栈车道(驱动 bring-up → Qt / 媒体 / AI;前段已交付、上层应用在推进中),不换板;主线优先、真板诚实,追全开源。**不是**发行版镜像。

当前范围内:三块板(RK3506B 完整支持、RK3568/RK3588 真机 boot 已验证,逐板进度见 [README.md](README.md))、主线 Linux 7.1 + U-Boot 2026.07-rc4、有序补丁整合(集成者为主,但**主线缺、且堵在全开源路上的,自己写**——板级 DT、SPL/DDR 胶水、开源 TEE 接入)、SPI-NAND(UBIFS) / eMMC / SD 卡多路启动、buildroot / OpenWrt / Ubuntu 三种 rootfs、VitePress 文档站。

明确不做:发行版镜像。闭源 blob(`rkbin`)是**要消灭的靶子**而非"先用着就行"——先用、文档化、追踪到全开源(见 [document/blobs.md](document/blobs.md))。完整定位与已验证能力见 [README.md](README.md)。
