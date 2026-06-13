# QUICK_START

Fast path. For the full learning path see [document/tutorial/boot/](document/tutorial/boot/).

## 1. Check your host

```bash
./scripts/doctor.sh
```

It probes the cross toolchain (`arm-linux-gnueabihf`) and build deps, detects WSL2,
and — if anything's missing — prints the exact `sudo apt install ...` line to stdout.
**We never auto-install** (keeps the script Python-wrap-able).

On a fresh WSL2 box you'll typically need:
```bash
sudo apt install gcc-arm-linux-gnueabihf device-tree-compiler bison flex cpio \
  qemu-system-arm u-boot-tools libssl-dev libncurses-dev python3-pyelftools
```

## 2. Export the toolchain env (per shell)

```bash
source scripts/env-setup.sh    # sets ARCH=arm, CROSS_COMPILE=arm-linux-gnueabihf-
```

## 3. (Week 3+) Fetch sources & apply patches

```bash
git submodule update --init --depth 1 third_party/uboot
cd third_party/uboot && ../../scripts/apply-series.sh --component uboot --check
```

`--check` is a true dry-run (applies then reverts), so it verifies the **whole
ordered series** applies cleanly before you build.

## 4. Build & flash — see the tutorial

U-Boot → kernel → SD flash is walked step-by-step in
`document/tutorial/boot/{02_uboot_rkbin,03_kernel_to_console}.md` (drafted as the
board DT lands).
