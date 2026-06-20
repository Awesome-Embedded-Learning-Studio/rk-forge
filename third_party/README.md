# third_party/

External source trees. Three are git **submodules** (build targets).

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

> The vendor SDK reference clone used to live here (`third_party/vendor-sdk/`). On
> 2026-06-20 it moved to **[`reference/vendor-sdk/`](../reference/README.md)** — it is
> reference material (an extraction pool for sdk-diff + board-DT/config), not a build
> input, so it belongs under `reference/`, not alongside the build-target submodules.
