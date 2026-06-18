# buildroot-external — rk-forge's BR2_EXTERNAL tree

rk-forge customizes upstream **buildroot** via a BR2_EXTERNAL tree (the buildroot-native
extension point; see buildroot `docs/manual/customize-outsideroot.txt`). This keeps
forge's board config **version-controlled in this repo** while the upstream buildroot
checkout itself stays a local clone (gitignored at `third_party/buildroot/`, same
pattern as `third_party/explore/`).

## Layout
- `configs/rk3506_aes_defconfig` — the board defconfig (minimal rootfs: busybox + sysv
  init, cpio+tar output, external `/opt` Arm GNU 15.2 toolchain).
- `external.desc` / `external.mk` / `Config.in` — required BR2_EXTERNAL scaffolding
  (no custom packages yet; add per-board packages/overlays/post-build hooks here as the
  line grows).

## One-time: checkout upstream buildroot
```bash
git clone https://github.com/buildroot/buildroot.git third_party/buildroot
# pinned near 2026.08-dev (HEAD 67449130 as of 2026-06-18); any recent master works.
```
`third_party/buildroot/` is gitignored — it is NOT a submodule. Re-clone on a new machine.

## Build (canonical — see note 19 for the 3 pitfalls this encodes)
```bash
cd third_party/buildroot
TC=/opt/arm-gnu-toolchain-15.2.rel1-x86_64-arm-none-linux-gnueabihf
# WSL: strip /mnt/* + whitespace PATH entries (buildroot dependencies.mk:27 rejects them)
export PATH="$TC/bin:$(printf '%s' "$PATH" | tr ':' '\n' | grep -vE '/mnt/|[[:space:]]' | paste -sd:)"
export BR2_EXTERNAL="$PWD/../bringup/buildroot-external"   # this tree
make rk3506_aes_defconfig   # regen .config from the defconfig (run this, NOT olddefconfig, after editing the defconfig)
make                        # artifacts → output/images/{rootfs.cpio,rootfs.tar}
```
Do **not** pass `O=`: buildroot's default puts build artifacts in `output/` but keeps
`.config` in-tree (upstream design, not a hack).

## Wire the rootfs into NAND packaging
`output/images/rootfs.tar` → extract to `third_party/bringup/out/rootfs` →
`scripts/pack-ubifs.sh` → `scripts/assemble-update.sh --provision` (boot.img/initramfs/
ubiprog reused; only rootfs.ubi.img changes). See note 19 §下一步.

## Pitfalls (full detail in `document/notes/19-…`)
1. WSL PATH whitespace → `dependencies.mk:27` rejects. (fix: strip above)
2. Arm GNU toolchain ships full languages (g++/gfortran/openmp, no gdc) → buildroot
   `check_*` requires `BR2_TOOLCHAIN_EXTERNAL_CXX/FORTRAN/OPENMP=y` (CXX selects
   `BR2_INSTALL_LIBSTDCPP`, the flag `check_cplusplus` reads — installs libstdc++).
3. glibc 2.42 dropped Sun RPC → must explicitly `# BR2_TOOLCHAIN_EXTERNAL_INET_RPC is not set`.
