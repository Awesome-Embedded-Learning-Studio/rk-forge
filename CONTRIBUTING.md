# Contributing to rk-forge

rk-forge is mainline-first board-enablement for RK3506. Before contributing:

## Setup
1. `./scripts/doctor.sh` — checks host deps + the `arm-linux-gnueabihf` toolchain;
   prints the `sudo apt install ...` line if anything is missing.
2. `source scripts/env-setup.sh` — exports `ARCH` / `CROSS_COMPILE`.

## Conventions
- **Patches**: quilt-style ordered `patches/<component>/series`, one patch per commit,
  generated with `scripts/patch-maker.sh` (`git format-patch`, with `From`/`Subject`/
  `Signed-off-by`). Prefix `[mainline]` / `[uboot]`.
- **Bash leaves must stay Python-wrap-able**: clean stdin/stdout/exit codes, **no**
  interactive `/dev/tty` prompts (that's why `doctor.sh` just prints the apt command,
  and `merge_overlay`-style scripts must take a `--yes` flag when added).
- **Incremental builds**: use `lib/stage.sh` content-hash skipping — don't rebuild a
  stage whose inputs haven't changed.
- **Commits**: conventional `type(scope): subject`, signed-off (`git commit -s`).
- **C/C++ style**: `.clang-format` is authoritative.

## Out of scope (v1)
Distro images, multi-SoC, original kernel drivers, Docker/CI multi-track, GUI, VitePress
site, Python CLI (iteration 2). See [PLAN.md](PLAN.md).
