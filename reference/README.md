# reference/

Active reference material — **not** build inputs, **not** committed (all gitignored).
This is where rk-forge keeps sources it *extracts knowledge from*, kept separate from
the build-target trees under `third_party/`.

## vendor-sdk/ — the ATK-DLRK3506 BSP (extraction pool)

A local clone of the 正点原子/ALIENTEK RK3506 BSP (linux 6.1.118 + a vendor U-Boot 2017
fork), managed via the `repo` tool (it has a `.repo/`). It is **not built** and **not a
git submodule** — it exists solely as a knowledge source:

- **[`document/sdk-diff.md`](../document/sdk-diff.md)** compares it subsystem-by-subsystem against the mainline port.
- **Board-DT / defconfig / io-domain extraction**: forge's board tree is built by reading
  what the vendor did here and porting the relevant bits to mainline. It is an *active
  extraction pool*, not a frozen snapshot — as forge grows (more peripherals, more
  config), more gets distilled out of here.

> **It is NOT deleted.** The "kill vendor-sdk" roadmap was about removing it as a **build
> dependency** (toolchain / mkimage / rkbin / loader / rootfs-firmware all decoupled —
> done). As a *reference* it stays indefinitely; it is the comparison anchor for sdk-diff
> and the source of truth for board-level config that forge has not yet distilled.

### Setup (optional — only if you want to run sdk-diff or extract)

The source tarball lives alongside as `reference/verdor-sdk.gz` (`[sic]` typo is original,
a rename is a separate tiny task). Or re-clone via the vendor `repo` manifest if you have
access. The clone is large (~14 GB) and fully gitignored — its absence is harmless to
every forge build/pack path.

## rk3568/ — the Rockchip RK3568 Linux BSP (extraction pool)

The Rockchip RK3568 **Linux** SDK (the `linux5.10_sdk` family: buildroot + kernel 5.10 +
vendor U-Boot + rkbin + `device/rockchip/` + debian/yocto), `repo`-managed (has a `.repo/`).
Same deal as vendor-sdk: **not built, not a submodule, gitignored** — a knowledge source
for the RK3568 *mainline* port (see [notes/36](../document/notes/36-2026-07-22-rk3568-multiboard-and-mainline-build.md)):
board-DT / io-domain / defconfig / vendor packaging flow get distilled out of here into
forge's mainline board tree.

## rk3568_android/ — the Rockchip RK3568 Android 13 BSP (extraction pool)

The Rockchip RK3568 **Android 13** SDK (AOSP + vendor kernel 5.10 + proprietary HALs +
rkbin), `repo`-managed, extracted from `android.tgz` (~26.5 GB → ~100 GB). Again **not
built, not committed, gitignored.** This is deliberately a *reference/comparison* track,
**separate from rk-forge's mainline-first identity**: Android here is the vendor Android
world (kernel 5.10 + blobs), the opposite pole from the mainline Linux port. It is kept to
understand the Rockchip Android packaging flow and to mine DTs/configs — see
[notes/37](../document/notes/37-2026-07-23-rk3568-android-sdk-build-flow.md) for the
build-flow analysis. Note Android's `envsetup/lunch/m` + `mkimage.sh` flow does **not** fit
forge's `setup→build→pack→assemble` orchestrator; it is its own track.

## rk3588/ — the Rockchip RK3588 Linux BSP (extraction pool)

The Rockchip RK3588 **Linux** SDK (`rk3588-linux_20251229.tar.xz`, ~13 GB) — the vendor
buildroot + kernel + U-Boot + rkbin bundle for the iTOP-RK3588 board. Same extraction-pool
role as rk3568/: a knowledge source for the RK3588 port (mainline-first, mirroring the
rk3568 approach), **not built, not a submodule, gitignored.** Currently placed **as a
tarball only** — extraction into a `repo`-managed tree is a follow-up step once the
migration kicks off.

## rk3588_android/ — the Rockchip RK3588 Android 13 BSP (extraction pool)

The Rockchip RK3588 **Android 13** SDK (`3588-android13-full-20251206.tar.xz`, ~28 GB;
shipped alongside `MD5.txt` + `readme.txt` in the iTOP `07_iTOP-RK3588开发板Android13源码`
folder). Same deal as rk3568_android/: the vendor Android world (kernel + blobs), kept as a
*reference/comparison* track separate from the mainline-first Linux port — **not built, not
committed, gitignored.** Also placed **as a tarball only** for now.

---

Moved here from `third_party/vendor-sdk/` on 2026-06-20 — topology honesty: reference
material belongs under `reference/`, not alongside the build-target submodules.
