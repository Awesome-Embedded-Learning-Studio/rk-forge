# reference/

Active reference material — **not** build inputs, **not** committed (all gitignored).
This is where rk-forge keeps sources it *extracts knowledge from*, kept separate from
the build-target trees under `third_party/`.

## vendor-sdk/ — the ATK-DLRK3506 BSP (extraction pool)

A local clone of the 正点原子/ALIENTEK RK3506 BSP (linux 6.1.118 + a vendor U-Boot 2017
fork), managed via the `repo` tool (it has a `.repo/`). It is **not built** and **not a
git submodule** — it exists solely as a knowledge source:

- **`scripts/sdk-diff.sh`** compares it subsystem-by-subsystem against the mainline port.
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

---

Moved here from `third_party/vendor-sdk/` on 2026-06-20 — topology honesty: reference
material belongs under `reference/`, not alongside the build-target submodules.
