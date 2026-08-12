# OpenWrt profile (`--rootfs=openwrt`)

OpenWrt is integrated into rk-forge as a **rootfs profile** alongside buildroot.
It builds a real OpenWrt (opkg / LuCI / kmod package management) on the aes
board (RK3506B, SPI-NAND), reusing rk-forge's board-verified RK packing chain
(mainline U-Boot + rkbin loader + fit-pack.py + rkfw-pack.py).

## Architecture (option A)

OpenWrt builds **both** the kernel and the rootfs; rk-forge does the RK-specific
packing. This keeps `opkg`/kmod fully functional — kmod packages pin to the
kernel's vermagic, and since OpenWrt builds both, they match by construction.

| concern | owner |
|---|---|
| kernel (zImage + aes.dtb) | **OpenWrt** (linux 7.1 + quilt patches-7.1/, byte-identical to rk-forge's patches/linux/) |
| rootfs tree (busybox+procd+kmod) | **OpenWrt** (musl, TARGET_DIR) |
| U-Boot | **rk-forge** (mainline, board-verified — `build-uboot.sh`, reused) |
| loader (idbloader/MiniLoaderAll) | **rk-forge** (rkbin, `pack-loader.sh`) |
| FIT images (boot.img/uboot.img) | **rk-forge** (`fit-pack.py`, board-verified load addrs) |
| update.img | **rk-forge** (`rkfw-pack.py`) |

The seam: `stage-rootfs.sh` rsyncs OpenWrt's `TARGET_DIR` → `out/rootfs/` (the
rootfs-format-agnostic tree that `pack-ubifs.sh` consumes); `pack-fit.sh` reads
zImage+aes.dtb from `KERNEL_ARTIFACT_DIR` (pointed at OpenWrt's build dir by
`forge.sh stage_pack`).

## Differences from the buildroot profile

- **Toolchain**: OpenWrt builds its own musl toolchain (NOT the rk-forge external
  glibc toolchain). Forcing glibc would break the musl userspace + kmod vermagic.
- **Kernel source**: OpenWrt downloads linux-7.1 itself and applies the quilt
  patches-7.1/ at build time. rk-forge does NOT `git am` the kernel patches for
  OpenWrt (unlike linux/uboot) — only a small Device/aes + config overlay is
  `git am`'d via `patches/openwrt/`.
- **WiFi**: goes through OpenWrt's kmod package system (not the
  `fetch-rtl8733bu-driver.sh` drop). The firmware fallback blobs are still staged
  from `firmware/rtl8733bu/` by `stage-rootfs.sh`.

## PSCI / OP-TEE

OpenWrt's upstream HEAD (`czz8888@31d15c0`) hangs at "Starting kernel..." because
that commit loads OP-TEE in its own U-Boot image flow + enables PSCI firmware.
rk-forge reuses its **mainline U-Boot (no OP-TEE)**, and rk-forge's own kernel
boots fine with `CONFIG_ARM_PSCI=y` (PSCI SMC gets no response → graceful
degrade; aes is single-core so the enable-method="psci" path is never taken).

→ **First board-verify WITHOUT touching PSCI config.** Only if it still hangs,
enable `patches/openwrt/0002-openwrt-rk3506-config-disable-psci.patch` (flip
`CONFIG_ARM_PSCI`/`ARM_PSCI_FW` off in `config-7.1`). See that patch's header.

## Usage

```bash
# one-time: fetch openwrt + uboot, apply the Device/aes overlay
bash scripts/forge.sh setup --rootfs=openwrt

# build OpenWrt kernel+rootfs + rk-forge U-Boot (~30-90min first time)
bash scripts/forge.sh build --rootfs=openwrt

# pack + assemble → board/aes/out/update.img
bash scripts/forge.sh assemble --rootfs=openwrt
# or the whole pipeline:
bash scripts/forge.sh all --rootfs=openwrt
```

The buildroot profile is untouched: `bash scripts/forge.sh build` (no `--rootfs`)
still builds the buildroot rootfs. The two profiles share `out/` — clean between
switches if fingerprints get confused (`forge clean`).

## Customizing the rootfs

Edit `aes-nand.config` (this dir), then `forge build --rootfs=openwrt
--reconfigure` (or `build-openwrt.sh --reconfigure`). After `make menuconfig` in
the openwrt tree, regenerate the seed with `./scripts/diffconfig.sh >
board/aes/openwrt/aes-nand.config`.

## Phase 2 (not yet): squashfs-on-UBI

Phase 1 ships a UBIFS writable root (reuses `pack-ubifs.sh`, fastest path to a
booting board). Phase 2 will add `pack-squashfs-ubi.sh` (OpenWrt's standard NAND
scheme: read-only squashfs root + overlay writable volume + sysupgrade) — see
the plan file.
