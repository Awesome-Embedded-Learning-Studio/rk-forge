# 33 — SD-2: SD-card autoboot (separate uboot defconfig, no manual mmc read)

> 2026-06-21. SD-1 (hand-typed `mmc read` at the `=>` prompt) → SD-2 (autoboot:
> the SD card boots to a shell with zero input). Implementation only — board-verify
> pending. Continuation of [32](32-2026-06-21-sd-card-image-sd1.md).

## Why a second defconfig

SD-1 needed three hand-typed lines every boot because the single uboot defconfig's
`CONFIG_BOOTCOMMAND` was the NAND `mtd read` sequence. env=nowhere runs the
compiled-default bootcmd every boot, so the fix is a **sibling defconfig** whose
bootcmd is the `mmc read` sequence — baked in, no prompt interaction.

The NAND defconfig is **unchanged**; the two defconfigs produce two uboot images
(`uboot.img` / `uboot-sd.img`), selected by the build/pack/assemble variant.

## What changed (5 places, NAND path untouched)

- **patch 0005** (`patches/uboot/0005-uboot-sd-autoboot-mmc-defconfig.patch`): new
  `configs/evb-rk3506_sd_defconfig`, identical to `evb-rk3506_defconfig` EXCEPT the
  bootcmd:
  ```
  CONFIG_BOOTCOMMAND="setenv bootargs 'console=ttyS0,1500000 root=/dev/mmcblk0p3 rootwait rw'; mmc dev 0; mmc read 0x04000000 0x4000 0x5000; bootm 0x04000000"
  ```
  `root=/dev/mmcblk0p3` — the RKFW SD layout is 3 GPT partitions: uboot=p1 /
  boot=p2 / rootfs=p3 (NOT p1 like the raw dd image). Load offset 0x4000 + read
  length 0x5000 match the verified SD-1 manual sequence (boot-sdl-202606211028).
- **build-uboot.sh `--variant sd`**: builds the SD defconfig in a throwaway **git
  worktree** at the same HEAD (which already has the sd defconfig from 0005), so
  the SD in-tree build never touches the NAND artifacts in `$UBOOT_DIR`. Output
  `u-boot-sd-nodtb.bin` + `u-boot-sd.dtb` → `$OUT_DIR`. `tools/mkimage` is shared
  with the NAND build (the defconfigs differ only in bootcmd).
- **pack-fit.sh `--variant sd`**: packs ONLY `uboot-sd.img` — same fit-pack.py
  Mode A layout as `uboot.img`, just a different `u-boot-nodtb.bin` payload. The
  `boot*.img` are reused from the default NAND run (media-agnostic).
- **assemble-update.sh `--sd`**: uses `uboot-sd.img` (was `uboot.img`).
- **forge `stage_pack_sd`**: wires `build-uboot-sd` + `pack-fit-sd` + `pack-sd` +
  `assemble-sd`; `stage_status` lists the two new stages.

## The Kbuild trap — why a worktree, not `make O=`

First attempt was out-of-tree `make -C uboot O=$OUT_DIR/build-uboot-sd`. Kbuild
refused:
```
*** The source tree is not clean, please run 'make ARCH=arm mrproper'
*** in .../third_party/src/uboot
```
The source tree already has in-tree NAND artifacts (`u-boot-nodtb.bin`, `.o`, … from
the NAND build), and Kbuild forbids an out-of-tree build over a dirty source tree.
`mrproper`'ing it would destroy the NAND artifacts → break the NAND `pack-fit`. A
**git worktree** is a pristine separate working tree at the same HEAD → in-tree
build works there, and the NAND tree is never touched. (`worktree add --detach` at
HEAD; `worktree remove --force` in the trap on exit.)

## Host verification
- `strings`: sd uboot bootcmd = `mmc read 0x04000000 0x4000 0x5000` + `root=/dev/mmcblk0p3`;
  nand uboot = `mtd read boot …` (unchanged — NAND path confirmed untouched).
- `uboot-sd.img` 608256 B (fit-pack.py Mode A; uboot loadable sha256 `90347127…`,
  fdt `c5bd3c40` — same DT as NAND, only the nodtb payload differs).
- `update-sd.img` 294779466 B (RKFW, chip RK350F, 6 parts, round-trip self-check OK).
- md5 `bc572ca0…` → `/mnt/d/DownloadFromInternet/update-sd-rkfw-autoboot-20260621.img`.

## Board-verify (2026-06-21, log boot-sdl-2026-06211109) ✅ PASSED — SD-2 closed
RK tool wrote `update-sd.img` → power on → `Hit any key to stop autoboot: 0`
(**no keypress**) → U-Boot `2026.07-rc4-g7e23760a` ran the compiled bootcmd →
`## Loading kernel from FIT Image at 04000000` + `## Loading fdt` → `Starting
kernel` → `EXT4-fs (mmcblk0p3): mounted ... r/w` + `VFS: Mounted root (ext4) on
device 179:3` → `Run /sbin/init` → `Welcome to rk-forge buildroot` / `rk3506
login: root`. No `=>` prompt interaction, no UBI — a fully unattended SD boot to a
shell. SD-2 closed; the SD path (SD-1 manual + SD-2 auto) is **done**.
