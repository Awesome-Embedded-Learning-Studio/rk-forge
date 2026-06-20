# firmware/rtl8733bu/ — local fallback firmware blobs (NOT the runtime path)

The two files in this dir (`rtl8733bu_fw` + `rtl8733bu_config`) are copied once
from the ATK vendor-sdk overlay. They are **gitignored** (Realtek binary blobs,
redistribution status unverified — same stance as `third_party/rkbin-atk/`).

## These are UNUSED at runtime

The RTL8733BU driver loads its firmware from a **built-in C array** compiled
into `8733bu.ko` (board-verified: `document/logs/boot-sdl-202606201050.txt`
L613 — `rtl8733b_fw_dl Download Firmware from array success`, 126664 B v1.40).
The `/lib/firmware/rtl8733bu_fw` file (55236 B) is a **different, stale blob
that the driver never reads** — it ships only as a belt-and-suspenders fallback.

So: `scripts/stage-rootfs.sh` stages these into `/lib/firmware/` **best-effort**
(if this dir is populated); if the dir is empty (fresh checkout), it skips them
harmlessly. WiFi works either way.

## Why this dir exists

It decouples `stage-rootfs.sh` from the ATK vendor-sdk path (the kill-vendor-sdk
blocker) — the hard `third_party/vendor-sdk/...` dependency is gone, so
`third_party/vendor-sdk/` can be deleted. The blobs (if you want the unused
fallback) live here, local-only.

## Populating (optional)

```bash
# from the ATK reference clone, if you still have it:
cp third_party/vendor-sdk/buildroot/board/alientek/atk-dlrk3506/fs-overlay/usr/lib/firmware/rtl8733bu_{fw,config} \
   firmware/rtl8733bu/
```
