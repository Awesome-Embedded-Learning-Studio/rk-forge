# 19 — buildroot 最小 rootfs 首次构建成功（external toolchain /opt Arm GNU 15.2）

> 一页纸备忘。buildroot 这条线今天（2026-06-18）新开，目标是用手搓 busybox rootfs（`scripts/mk-rootfs.sh`，复用 initramfs 静态 busybox）之外的**正规 buildroot 流程**出一个可烧可启的最小 rootfs。详见 `document/logs/buildroot-build-202606181746.log`（成功那次）+ 前两次失败 log（同前缀）。

## 终局（2026-06-18）
buildroot 2026.08-dev（HEAD `67449130`）用外部工具链 `/opt` Arm GNU 15.2（gcc 15.2.1 / glibc 2.42 / headers 6.6.76）**成功编出最小 rootfs**：
- `output/images/rootfs.cpio` — 8.21 MB
- `output/images/rootfs.tar`  — 8.76 MB
- busybox = ARM EABI5 **hard-float**（`ld-linux-armhf.so.3`），动态链接，strip；`/sbin/init`→busybox 符号链接；`/etc/inittab|passwd|shadow` 齐；glibc 运行时 + libstdc++/libgfortran/libgomp 全在 `/lib`；FHS 结构完整。
- **板上还没验**（下一步接 UBIFS 打包 + 烧板）。这次只到「buildroot 端到端能出活的 rootfs」。

## defconfig
位置：`board/aes/buildroot-external/configs/rk3506_aes_defconfig`（**BR2_EXTERNAL 树**，rk-forge 自有、进版本控制）。buildroot 本体是 loose 上游检出（`third_party/buildroot/`，gitignored，同 explore/vendor-sdk 模式），其定制通过 BR2_EXTERNAL 注入：`make BR2_EXTERNAL=.../buildroot-external rk3506_aes_defconfig`（已验认，`BR2_DEFCONFIG` 指向新位置 + 外部树注册）。见 `buildroot-external/README.md`。当初踩过的结构坑：`git add -A` 把 buildroot 当 embedded git 仓（gitlink）加进去——clone 拿不到内容；解法 = gitignore buildroot + defconfig 挪进 BR2_EXTERNAL。

关键决策：arm cortex-a7 / neon-vfpv4；external toolchain = `/opt` Arm GNU 15.2（与板上 boot+RW 验过的 toolchain 一致，见记忆 `self-run-build-and-copy`）；busybox + sysv init；输出 cpio（initramfs 用）+ tar（UBIFS staging 用）。**还没加 `BR2_TARGET_ROOTFS_UBIFS`**——选了走 tar→现有 `pack-ubifs.sh` 的路子，先复用已验过的 NAND 打包管线。

## 三连坑（buildroot external-toolchain check_*，全在 `toolchain/helpers.mk` + `toolchain-external/pkg-toolchain-external.mk`）
按撞墙顺序：

1. **PATH 含空格 → `dependencies.mk:27` 拒跑**（最先死，没到工具链校验）。WSL 把 Windows PATH 互操作进来，`/mnt/c/Program Files/...` 带空格，buildroot 直接 `Your PATH contains spaces, TABs, and/or newline` exit 1。**环境问题，非 buildroot/defconfig 问题。** 修法：跑 buildroot 时剥掉所有 `/mnt/*` + 含空白字符的 PATH 条目，再前置工具链 bin。
2. **`check_cplusplus`/`check_fortran`/`check_openmp` → "not selected but available"**。Arm GNU 工具链是全套（bin 里 g++ + gfortran + gcc 带 OpenMP，**无 gdc**），buildroot 的 check_* 要求 config 必须承认工具链实际带的每一种语言，否则 configure 阶段 exit 1。**连环**（C++→Fortran→OpenMP 顺序绊）。修法：defconfig 加 `BR2_TOOLCHAIN_EXTERNAL_CXX=y`（select `BR2_INSTALL_LIBSTDCPP`，会装 libstdc++ 进 rootfs，check_cplusplus 读的就是 `BR2_INSTALL_LIBSTDCPP`）+ `BR2_TOOLCHAIN_EXTERNAL_FORTRAN=y` + `BR2_TOOLCHAIN_EXTERNAL_OPENMP=y`。D 不用管（无 gdc，check 自动过）。Fortran/OpenMP 只是能力声明，不装运行时；C++ 会装 libstdc++（几 MB，174MiB UBIFS 无所谓）。
3. **`check_glibc_rpc_feature` → "RPC support not available in C library, please disable BR2_TOOLCHAIN_EXTERNAL_INET_RPC"**。glibc 2.42 早把 Sun RPC 从 libc 挪走（迁 libtirpc），sysroot 无 `rpc/rpc.h`；但 `BR2_TOOLCHAIN_EXTERNAL_INET_RPC` 对 glibc **默认 y**，所以必须**显式关**（defconfig 写 `# BR2_TOOLCHAIN_EXTERNAL_INET_RPC is not set`）。

修完三个，剩余 check（kernel headers / gcc version / arm abi / MMU / SSP）全过，进 staging→busybox→rootfs 出图。

## canonical 调用（踩坑后定型）
```bash
cd third_party/buildroot
TC=/opt/arm-gnu-toolchain-15.2.rel1-x86_64-arm-none-linux-gnueabihf
export PATH="$TC/bin:$(printf '%s' "$PATH" | tr ':' '\n' | grep -vE '/mnt/|[[:space:]]' | paste -sd:)"
make rk3506_aes_defconfig   # 从 defconfig 重新生成 .config（改了 defconfig 必须跑这个，olddefconfig 不重读 defconfig！）
make                        # 不带 O=：buildroot 默认 O=$(CURDIR)/output 当 build 树，.config 留 in-tree
```
**两个易踩点**：
- 改了 `configs/*.defconfig` 后要跑 `make <name>_defconfig`，**不是** `make olddefconfig`——后者只对账现有 `.config`，不重读 defconfig 文件（这次语言标志第一次没生效就是栽这）。
- `O=` 默认值设计很巧：`O` 没传 → `O=$(CURDIR)/output`（build 树进 `output/`）但 `CONFIG_DIR=$(CURDIR)`（**`.config` 留 in-tree**）。是上游设计不是 hack（`git diff Makefile` 空）。别画蛇添足传 `O=output`，会踩 ELSE 分支歧义。

## 下一步（接 NAND）
1. ✅ **结构已定**：BR2_EXTERNAL（`buildroot-external/`），buildroot 本体 gitignored loose 检出。`make BR2_EXTERNAL=.../buildroot-external rk3506_aes_defconfig` 验通。
2. 把 buildroot 的 `rootfs.tar` 解出来喂 `scripts/pack-ubifs.sh`（现管线吃 rootfs 树）——✅ 已做（2026-06-18，板上 boot 通，见下「板上验证」），或后续给 defconfig 加 `BR2_TARGET_ROOTFS_UBIFS` 直出 ubifs 省一步。
3. 现有手搓 rootfs 里的 `mtdrawdump`/`mtdbb` 取证工具 + `/etc` 配置，buildroot 最小 rootfs 没有；要保留就靠 BR2_EXTERNAL overlay（`BR2_ROOTFS_OVERLAY`）或 package 补。
4. ✅ 板上验证：烧 `update-provision-buildroot.img` → 主线 U-Boot → `console-only + mtd read 0x1000000 + bootm` → /init → ubiprog 置备（failed=0，PEB3/4 页级恢复）→ switch_root → `Welcome to rk-forge buildroot` → root 登录。log `boot-sdl-202606181919`。遗留非阻塞：rcS `tmpfs: Unknown parameter 'mode'`（/dev/shm /tmp /run 没挂 tmpfs）。
