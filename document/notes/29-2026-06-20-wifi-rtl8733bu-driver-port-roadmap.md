# notes/29 — 2026-06-20 — WiFi (RTL8733BU) driver-port ROADMAP (handoff for a fresh AI)

**This is a self-contained handoff. A new AI with clean context should read this +
the top memory handoff, then execute. Do NOT re-derive the research below — it's
already done and verified (incl. several dead-ends avoided).**

## TL;DR / decision
Board-mounted **Realtek RTL8733BU** WiFi+BT (USB id `0bda:b733`, **soldered on
the board**, not a dongle) has **no mainline driver**. User decision: **port the
out-of-tree driver** to get it working — forge goes "fully independent" using the
on-board chip. The mainline-only rule is **deliberately loosened for this one
driver** (user-authorized). Build it as an `=m` module shipped in the rootfs,
loaded via busybox `insmod` after switch_root, with ATK-provided firmware.

## Hardware facts (verified on board, log boot-sdl-202606200858)
- Chip **RTL8733BU**, USB **`0bda:b733`** (Realtek). USB descriptors read clean
  via sysfs: `0bda:b733 802.11n WLAN Adapter`.
- It sits on **OTG1** (`usb20_otg1` @ ff780000, bus 2) **behind a CH334R USB hub**
  (`1a86:8091`). So the DWC2 host + USB2PHY (Phase B, ✅done) already enumerate
  it — only a driver is missing. No DT work needed for WiFi itself.
- BT part of the combo shares the USB; out of scope for now (WiFi first).

## Research findings — DO NOT re-derive
1. **No mainline driver** (rigorously verified, not a grep artifact — used abs
   paths + multiple search terms): our kernel is **Linux 7.1.0** (VERSION=7
   PATCHLEVEL=1, 2025-vintage rtw89). `grep 8733 drivers/net/wireless` = empty;
   `0bda:b733` bound by NO driver. rtw89 tops out at **8851B/8852A/B/BT/C/8922A/D**.
   rtl8xxxu doesn't cover it. So: **no backport target exists**; only the
   out-of-tree driver works.
2. **Driver source**: `https://github.com/wirenboard/rtl8733bu`, branch
   **`v5.15.12-264_for6.18`** (newest; README says tested 5.10.x + 6.8.x — our 7.1
   is beyond their tested range, expect API fixes). ~221 .c files (core 69 /
   os_dep 20 / hal 120 / platform 12); only a subset compiles for the 8733b
   config. Classic Realtek **multi-chip Makefile** (2803 lines, one Makefile for
   all RTL8xxx chips, selected by `CONFIG_RTLxxxx`).
3. **Firmware exists** in the ATK overlay (no hunting needed):
   `third_party/vendor-sdk/buildroot/board/alientek/atk-dlrk3506/fs-overlay/usr/lib/firmware/`
   → `rtl8733bu_fw` (55236 B) + `rtl8733bu_config` (14 B). Copy both into the
   forge rootfs `/lib/firmware/`.
4. **Wireless stack present**: `.config` has `CONFIG_WIRELESS=y`, `CFG80211=m`,
   `MAC80211=m`. The Realtek fullmac-style driver uses **cfg80211** (likely NOT
   mac80211 — confirm when it links). `CFG80211_REQUIRE_SIGNED_REGDB=y` +
   `USE_KERNEL_REGDB_KEYS=y` (built-in regdb used; should be fine).
5. **First known compile error** (build got far before the env flaked):
   `core/rtw_br_ext.c:1237: 'struct pppoe_tag' has no member 'tag_data'` — kernel
   struct rename, in the OPTIONAL bridge-extension/NAT code. Representative of
   the error class: scattered, fixable API drift, NOT a rewrite.

## Integration architecture (decided)
- **Location**: in-tree at `third_party/explore/linux/drivers/net/wireless/realtek/rtl8733bu/`.
  Copy the wirenboard source there. Keeps it with the kernel build (stable) and
  is the natural `=m` home.
- **Why in-tree, not out-of-tree**: the driver's out-of-tree build (`make -C
  $(KSRC) M=$(PWD)`) **segfaults `make` itself in this WSL env** (make crashes
  during the M= recursion into the 2803-line Makefile, before/during compile —
  not memory, not bc; reproducible). The kernel's own `obj-$(CONFIG)` build path
  is far more robust. So: rewrite the driver's Makefile into Kbuild format.
- **Build mode**: **`=m` module** (8733bu.ko), NOT `=y`. Reason: the boot flow is
  provision-initramfs → ubiprog → switch_root to UBIFS. A `=y` driver probes
  during the initramfs stage, before the UBIFS rootfs (where firmware lives) is
  mounted → `request_firmware` fails. An `=m` loaded AFTER switch_root has
  firmware available. CFG80211 (and MAC80211 if needed) → `=y` built-in so the
  module's deps are always present.
- **Load**: busybox `insmod /lib/modules/8733bu.ko` from an rc script after
  switch_root. Minimal rootfs has no kmod/modprobe; busybox insmod suffices.
- **Connect**: buildroot `wpa_supplicant` + `iw`.

## Phased execution plan

### Phase 1 — stabilize the build (in-tree + Kbuild Makefile)
1. Clone: `git clone -b v5.15.12-264_for6.18 https://github.com/wirenboard/rtl8733bu`
   into `third_party/explore/linux/drivers/net/wireless/realtek/rtl8733bu/`.
2. **Extract the 8733b `.o` file list** from the multi-chip Makefile (this is the
   key step). The list is assembled from chip-specific blocks + common vars.
   `MODULE_NAME = 8733bu` (Makefile:815, inside `ifeq (CONFIG_RTL8733B y)` @812);
   a second 8733b block @2601; `obj-$(CONFIG_RTL8733BU) := $(MODULE_NAME).o` @2697.
   **Technique**: dump the resolved file list WITHOUT the kernel recursion (which
   segfaults) — e.g. `cd rtl8733bu && make -p KSRC=/dev/null ARCH=arm 2>/dev/null |
   grep -E '8733bu-y|^rtk_core|\.o$'` (plain variable eval doesn't recurse → no
   segfault). Capture the full `.o` list.
3. Write a **Kbuild Makefile** replacing the driver's: `obj-$(CONFIG_RTL8733BU) +=
   8733bu.o` + `8733bu-y := <the extracted list>` + carry over the `ccflags-y`
   (`-I$(src)/include`, `-DCONFIG_RTL8733B`, the `-Wno-*`, etc. from EXTRA_CFLAGS).
   Drop the driver's `modules:`/`install:`/KSRC machinery (the kernel build owns that).
4. **Fix the driver's Kconfig bug**: it says `depends on MMC` (copy-paste error —
   it's USB). Change to `depends on USB && CFG80211` (drop it into the kernel
   tree's `drivers/net/wireless/realtek/Kconfig` under `if WLAN_VENDOR_REALTEK`,
   or keep a local Kconfig sourced from there).
5. Wire: `drivers/net/wireless/realtek/Makefile` += `obj-$(CONFIG_RTL8733BU) +=
   rtl8733bu/`; `realtek/Kconfig` += `source ".../rtl8733bu/Kconfig"`.
6. `board/rk3506-evb/kernel.config` += `CONFIG_RTL8733BU=m`, `CONFIG_CFG80211=y`
   (flip from m). Build → now the error list comes from the STABLE in-tree path.

### Phase 2 — API port (6.8.x → our 7.1)
- Enumerate errors from the in-tree build (`make ... modules` or the full
  `build-linux.sh`). Fix iteratively. **Strategy**: for OPTIONAL features that
  hit removed APIs, DISABLE the feature (set its `CONFIG_RTW_* = n`) rather than
  port dead code — e.g. `CONFIG_RTW_BR_EXT` skips rtw_br_ext.c (the pppoe_tag
  error). Only port code on the actual WiFi data path.
- **Expected error categories** (classic 5.x/6.x → 7.x churn — pre-warn yourself):
  `setup_timer`→`timer_setup`; `getnstimeofday`→ktime/time64;
  `proc_create` signature; `net_device_ops`/ndo changes; `usb_alloc_urb`/URB API;
  `cfg80211` ops signature drift; `wireless_dev`; `asm/uaccess.h`→`linux/uaccess.h`;
  `ioremap_nocache`→`ioremap`; `get_user_pages` signature; `eth_hw_addr_set`
  (replaces ether_setup random addr in newer kernels). Plus the confirmed
  `pppoe_tag.tag_data`.
- Goal: `8733bu.ko` links clean.

### Phase 3 — config + produce the .ko
- Confirm `.config`: `RTL8733BU=m`, `CFG80211=y` (+ `MAC80211=y` if the link
  demands it), `WLAN_VENDOR_REALTEK=y`. Build produces `8733bu.ko`.

### Phase 4 — rootfs integration
- `8733bu.ko` → forge rootfs `/lib/modules/8733bu.ko` (via the buildroot overlay
  / post-build hook — see how mtdrawdump/mtdbb got in, notes/19).
- Firmware: copy `rtl8733bu_fw` + `rtl8733bu_config` (from the ATK overlay path
  above) → rootfs `/lib/firmware/`.
- Load: add `insmod /lib/modules/8733bu.ko` to an rc script (rc.local / an
  Sxx init script) that runs AFTER switch_root (rootfs is mounted).
- buildroot: enable `wpa_supplicant` + `iw` packages (rebuild rootfs).

### Phase 5 — board test
`insmod` → `wlan0` appears (`ip link`) → `iw wlan0 scan` (see APs) →
`wpa_supplicant` + `udhcpc` connect. Provision-variant image, bootargs
`console=ttyS0,1500000`.

## Gotchas / environment
- **WSL make segfaults on out-of-tree `M=` recursion** with this Makefile → build
  IN-TREE (Phase 1). Don't waste time on out-of-tree.
- **kernel-trim.config is applied AFTER kernel.config** (merge order) and can
  silently kill subsystems (it bit USB — pitfalls/06). After any config change,
  grep the BUILT `.config`, not just the fragment, to confirm flags survived.
- **Firmware timing**: load the module AFTER switch_root (UBIFS mounted), else
  `request_firmware` fails. (This is why `=m`, not `=y`.)
- **`request_firmware` needs the file in `/lib/firmware/`** on the mounted rootfs
  (or the initramfs if loading early). Buildroot's `BR2_ROOTFS_OVERLAY` or a
  post-build hook is the way.
- **Don't re-prove "no mainline driver"** — done (item 1). Don't re-argue the
  approach — user authorized the out-of-tree port + loosened mainline-only.
- Standard forge rules: **production-grade / root-cause (no band-aid)**, **commit
  messages NEVER carry Co-Authored-By**, board name `aes` (never `atk`), **local
  build/cp/grep Claude runs itself** (only Windows RKDevTool flash + UART capture
  go to the user), **after any pack change re-run assemble-update.sh + cp the
  update.img to `/mnt/d/DownloadFromInternet/`**.

## References
- Driver repo: `wirenboard/rtl8733bu` branch `v5.15.12-264_for6.18`.
- Our kernel tree: `third_party/explore/linux/` (Linux 7.1.0). Build:
  `source scripts/env-setup.sh; scripts/build-linux.sh` (config fragment merge
  order: multi_v7 → kernel.config → kernel-trim → kernel-compress).
- Firmware src: `third_party/vendor-sdk/buildroot/board/alientek/atk-dlrk3506/fs-overlay/usr/lib/firmware/rtl8733bu_{fw,config}`.
- Related: notes/28 (B-USB, the USB2PHY+DWC2 work that gets the chip enumerated),
  pitfalls/06 (USB saga), memory `handoff-current-state-next-usb`.
- Full-assembled `.o` list for 8733b is the one non-obvious artifact — extract it
  first (Phase 1 step 2) and the rest is mechanical compile-fixing.

## Status when this was written
B-USB ✅ done (USB host works, the chip enumerates as 0bda:b733). WiFi driver
port NOT started — this roadmap is the entry point. No code written yet for WiFi.

---

## UPDATE 2026-06-20 (later) — Phase 1-4 DONE, Phase 5 board-test pending
All 5 phases executed through Phase 4. **8733bu.ko compiles clean on 7.1** (zero
errors, zero modpost errors; valid ARM module, `depends=` empty, claims
`0bda:b733`). Board image staged at
`/mnt/d/DownloadFromInternet/update-wifi-rtl8733bu.img` (md5 `513800ae`,
PROVISION-UBIPROG, new zImage with CFG80211=y + rootfs with .ko/firmware/S99wifi/
wpa_supplicant/iw). **Phase 5 = user flashes + insmod/scan/connect test.**

Key porting decisions (full detail in memory `wifi-rtl8733bu-port-state`, NOT
re-derived here):
- Kbuild Makefile rewritten from the 2803-line upstream Makefile via
  `make -p ... src=<dir> KERNELRELEASE=x CONFIG_RTL8733BU=m` extraction of the
  fully-expanded 187-file `8733bu-y` list + ccflags. Stable kernel obj-$() path.
- Path macros (`EFUSE_MAP_PATH`/`WIFIMAC_PATH`/`REALTEK_CONFIG_PATH`) MUST use
  `\"`-escaped quotes in ccflags-y, else make→shell→gcc strips them →
  `<command-line>` '/'-token errors + hal_com.c "too few arguments".
- `CONFIG_BR_EXT` disabled (optional; rtw_br_ext.c hits a removed 7.x API).
- cfg80211 wdev-ops conversion (add_key/.../dump_station changed to
  `wireless_dev*` in 6.14+) handled via 9 `_wdev` forwarder wrappers in
  ioctl_cfg80211.c (uses existing `wdev_to_ndev`), struct points at wrappers;
  2 callers (cfg80211_new_sta/del_sta) pass `ndev->ieee80211_ptr`.
- `# CONFIG_WLAN is not set` removed from kernel-trim.config (gates
  WLAN_VENDOR_REALTEK). CFG80211=y built-in, MAC80211 left =m.
- buildroot needs a clean PATH (WSL /mnt paths with spaces break it).

Phase 5 first-boot commands: `ip link` (wlan0?) → `iw wlan0 scan` →
wpa_supplicant. If firmware-not-found, check dmesg for the requested name and
symlink/rename in /lib/firmware/ or pass `rtw_fw_file_path=` module param.
