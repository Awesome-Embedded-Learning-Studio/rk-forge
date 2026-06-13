# third_party/

External source trees. Three are git **submodules** (build targets); one is a local
**reference clone** (not a submodule).

## Build targets (submodules — initialized in Week 3+)

| dir | url | role |
|---|---|---|
| `linux_mainline/` | git.kernel.org/.../torvalds/linux.git | build kernel from **v7.0.x** (RK3506 pinctrl+clk present; 6.19 is EOL) |
| `uboot/` | gitlab.denx.de/u-boot/u-boot.git | build U-Boot — RK3506 SoC support already upstream |
| `rkbin/` | github.com/rockchip-linux/rkbin.git | closed DDR/TPL/SPL blobs (see ../BLOBS.md) |

Initialize (later):
```bash
git submodule update --init --depth 1 third_party/<name>
```

## Reference clone (NOT a submodule — gitignored)

`vendor-sdk/` — a local clone of a **vendor SDK used only as a knowledge source**
for `scripts/sdk-diff.sh` and board-DT extraction. It is **not** built; it is the
"other end" of the mainline-vs-BSP comparison.

```bash
# example: pull a vendor SDK into the reference slot
git clone <vendor-sdk-url> third_party/vendor-sdk
```

> **Confirm it targets RK3506** (and note its kernel version) on first pull. If the
> vendor SDK is a BSP kernel (e.g. 5.10/6.1 + vendor patches), that's fine as a
> *reference* — but our build target stays mainline. See ../PLAN.md.
