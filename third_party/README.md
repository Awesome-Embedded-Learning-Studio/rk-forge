# third_party/

External source trees. `rkbin/` is a git **submodule**; `src/` and `buildroot/`
are local fetched clones (gitignored, managed by `scripts/fetch-deps.sh` against
`pins/`).

## src/ — kernel + U-Boot source trees (fetched-clone)

| tree | source | role |
|---|---|---|
| `src/linux/` | torvalds/linux @ v7.1 (pin: `pins/linux`) | build kernel; `patches/linux` series applied |
| `src/uboot/` | denx/u-boot @ pinned commit (pin: `pins/uboot`) | build U-Boot; `patches/uboot` series applied |

These are NOT submodules — they carry our patch series (`git am`'d by
`scripts/apply-series.sh`), so a gitlink would drift. `fetch-deps.sh` clones them
gitignored; the patch series + board tree are what's actually version-controlled.

## buildroot/ — rootfs build system (fetched-clone)

Upstream buildroot clone (gitignored). forge's board customization (defconfig +
overlay + post-build) lives in the BR2_EXTERNAL tree at
`board/aes/buildroot-external/`. See its README for the checkout + build invocation.

## rkbin/ — closed Rockchip blobs (submodule)

github.com/rockchip-linux/rkbin — DDR/TPL/SPL/tee blobs (see ../BLOBS.md). The
only real submodule here; pinned at a known-good commit.

> The vendor SDK reference clone used to live here (`third_party/vendor-sdk/`).
> On 2026-06-20 it moved to [`reference/vendor-sdk/`](../reference/README.md).
