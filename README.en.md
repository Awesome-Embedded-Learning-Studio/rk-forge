# rk-forge

<div align="center">

**A mainline-first development workspace for Rockchip RK3506**
Ordered patch library × Honest gap report × A build experience that replaces RK-SDK's `build.sh` × 0→1 tutorial

</div>

---

## What is this

rk-forge serves the **underserved RK3506**: bring up the latest mainline Linux, and **honestly report what's still missing**.

It is **not** yet another Armbian / Yocto / vendor BSP image. It does three things:

1. **Ordered patch library** — quilt-style `series`; `git am` lands real commits, bisectable, atomic rollback on failure (fixes the "only the last patch applies" disease).
2. **Honest gap report** (`sdk-diff.sh`) — per subsystem: what the vendor BSP has / what mainline has / what's missing / whether it still boots.
3. **0→1 tutorial** — a reproducible path from a blank machine to RK3506 mainline booting to UART.

**Core thesis (verified):** RK3506's SoC foundation (pinctrl+clk since Linux 6.19; U-Boot SoC support merged via Jonas Karlman's v2 series) is **entirely in mainline**. So for "mainline boot", the whole RK-SDK collapses into two things: ① `rkbin` (closed DDR-init blob, unavoidable); ② **a board device tree** (not upstream — rk-forge writes it). rk-forge's main contribution is that `.dts` + an honest path.

> Others sell cooked meals; rk-forge sells the recipe + the stove + a book that walks you through cooking — the dish nobody else makes.

## Quick start

```bash
./scripts/doctor.sh                       # check host deps + the armhf cross toolchain (prints the apt line if missing)
source scripts/env-setup.sh               # export ARCH=arm / CROSS_COMPILE=arm-linux-gnueabihf-
bash scripts/forge.sh all                 # setup → build → pack → assemble → board/aes/out/update.img
```

See [QUICK_START.md](QUICK_START.md) and [document/tutorial/boot/](document/tutorial/boot/).

> Your shell is zsh? Always invoke forge as `bash scripts/forge.sh ...` — the lib scripts use `BASH_SOURCE`, which is empty under zsh.

## Repository layout

```
config/toolchain.conf        declarative toolchain config (a future Python CLI reads it directly)
board.env                    board metadata (placeholder rk3506-evb)
board/                       aes/(build workspace: fit/rootfs/buildroot-external) · rk3506-evb/(board config)
patches/{linux,uboot}/series   ordered patch series
third_party/                 src/(linux·uboot source trees) · buildroot · rkbin(submodule)
reference/                   vendor-sdk(reference/extraction pool, NOT a build dependency)
scripts/
  lib/{log,toolchain,stage}.sh           shared libs; stage.sh = content-hash incremental skip
  env-setup.sh · doctor.sh               environment (source / standalone check)
  apply-series.sh                        ★ patch library (fixes imx-forge's #1 debt)
  build-uboot.sh · build-linux.sh · flash-sd.sh · sdk-diff.sh
BLOBS.md                     honest list of rkbin closed blobs + the path to eliminate them
document/tutorial/boot/      Ch0-3 tutorial (in-repo Markdown)
```

## Explicitly out of scope (v1)

Distro images, multi-SoC (v1 is RK3506 only), original kernel drivers (integrator only), Docker/CI multi-track, GUI/SaaS, blob purism (use first, document, target elimination). Python CLI is iteration 2 — the bash leaves are written to be Python-wrappable (clean stdin/stdout/exit; `doctor.sh` has no `/dev/tty` interaction).

## References

- Model (positional reference, not a copy): imx-forge (the NXP i.MX6ULL sibling project).
- Mainline facts in [PLAN.md](PLAN.md) and `document/`.

## License

MIT, see [LICENSE](LICENSE). Patches originating from GPL SDKs retain GPL-2.0 and are marked in the patch header. `rkbin` is Rockchip proprietary firmware, referenced as a pinned submodule only — not copied into this repo.
