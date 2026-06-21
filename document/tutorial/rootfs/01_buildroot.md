# Ch1 — buildroot：出一份正规的最小 rootfs

> rootfs 这程的第一步，是把 rootfs 的"内容"弄出来。boot 系列后期我们靠一个手搓的静态 busybox initramfs 凑合过，能拿到 shell 就行；但这程要的是一份正规的、可维护的 rootfs，所以上 buildroot。这章踩的全是构建侧的坑：WSL 把 Windows 的 PATH 互操作进来、外部工具链的语言检查连环绊、glibc 把 RPC 挪走了。踩完，你手里就有一份能烧能启的 busybox rootfs。

## 前言：为什么不再手搓

boot 系列里我们先拿到 shell，靠的是一个手搓的 initramfs——静态 busybox 加一个 `/init`，塞进 kernel FIT 当 ramdisk。能跑，但那是"为了快速验证启动链"的凑合：rootfs 内容全靠手维护，加个工具要自己交叉编译、自己塞 overlay，不可持续。

rootfs 这程要的是正规流程，所以上 buildroot。buildroot 会从源码给你编一整个最小 Linux 根文件系统——busybox、glibc 运行时、init 配置、FHS 目录结构，一条 `make` 出齐。RK3506 是 Cortex-A7 / NEON-VFPv4，工具链就用我们在 [boot Ch1](../boot/01_toolchain.md) 钉死的那套：`/opt` 下的 Arm GNU 15.2，和板上 boot+RW 验过的完全一致，不另起炉灶。

## 材料：buildroot 本体 + 我们的 BR2_EXTERNAL

buildroot 本体我们用 loose 检出的上游 2026.08-dev（`third_party/buildroot/`，gitignored，和 uboot/linux 的 explore 模式一样）。我们的定制不直接改 buildroot，而是通过一个 **BR2_EXTERNAL 树**注入——[`board/aes/buildroot-external/`](../../../board/aes/buildroot-external/)，这是 rk-forge 自有、进版本控制的：里面放着 `configs/rk3506_aes_defconfig`（板级 defconfig）、overlay（`/etc` 配置、init 脚本）、post-build hook。调用时 `make BR2_EXTERNAL=.../buildroot-external rk3506_aes_defconfig`，buildroot 就会注册这棵外部树、读我们的 defconfig。

这种"本体 loose + 定制走 BR2_EXTERNAL"的结构不是洁癖，是踩过坑才定的。当年 `git add -A` 把 buildroot 当 embedded git 仓（gitlink）加进去，结果 clone 根本拿不到内容；解法就是 buildroot 本体 gitignored，defconfig 和 overlay 全挪进 BR2_EXTERNAL 这棵真正进版本控制的树。详细决策记在 [notes/19](../../notes/19-2026-06-18-buildroot-minimal-rootfs-first-build.md)。

## defconfig 的几个关键决策

defconfig 里几个要紧的选择：架构 `arm`、`cortex-a7`、`neon-vfpv4`；工具链用 external（指向 `/opt` Arm GNU 15.2，不靠 buildroot 自己编一个）；init 走 busybox + sysv init；输出格式选了 `cpio`（给 initramfs 用）加 `tar`（给 UBIFS staging 用）。注意我们**没开** `BR2_TARGET_ROOTFS_UBIFS`——选了走 tar → 现有 `pack-ubifs.sh` 的路子，先复用已经验证过的 NAND 打包管线，而不是在 buildroot 里再开一条 UBIFS 直出的路。

## 坑之一：WSL 的 PATH 里带空格，buildroot 当场拒跑

第一个坑死得最快，都没走到工具链校验。WSL 会把 Windows 的 PATH 互操作进来，于是你的 `PATH` 里赫然躺着 `/mnt/c/Program Files/...` 这种带空格的条目。buildroot 的 `dependencies.mk:27` 一看 PATH 里有空格，直接甩一句 `Your PATH contains spaces, TABs, and/or newline` 然后 exit 1，连配置都不让你生成。

这是个纯环境问题，跟 buildroot、跟 defconfig 都没关系。修法是在跑 buildroot 之前，把 PATH 里所有 `/mnt/*` 和含空白字符的条目剥掉，再把工具链 bin 目录前置进去。具体写法见后面 canonical 调用里那一行 `tr` + `grep -vE`，就是干这个的。

## 坑之二：外部工具链的语言检查，C++/Fortran/OpenMP 连环绊

PATH 弄干净，进到工具链校验，连环坑来了。Arm GNU 工具链是全套——bin 里 g++、gfortran 都有，gcc 还带 OpenMP。buildroot 的 `check_cplusplus` / `check_fortran` / `check_openmp` 要求你的 defconfig 必须老老实实承认工具链实际带的每一种语言，少承认一种，configure 阶段就 exit 1。而且它还连着绊：你补上 C++，下一个又卡 Fortran，再下一个 OpenMP，一个接一个。

解法是 defconfig 里把这几项全开：`BR2_TOOLCHAIN_EXTERNAL_CXX=y`（它会 select `BR2_INSTALL_LIBSTDCPP`，往 rootfs 装 libstdc++，几 MB，174MiB 的 UBIFS 无所谓）、`BR2_TOOLCHAIN_EXTERNAL_FORTRAN=y`、`BR2_TOOLCHAIN_EXTERNAL_OPENMP=y`。D 语言不用管——这套工具链没 gdc，check 自动过。Fortran 和 OpenMP 只是能力声明、不装运行时，C++ 会装 libstdc++。

## 坑之三：glibc 2.42 把 RPC 挪走了

语言检查过完，又撞上 `check_glibc_rpc_feature` 报 `RPC support not available in C library, please disable BR2_TOOLCHAIN_EXTERNAL_INET_RPC`。原因是 glibc 2.42 早就把 Sun RPC 从 libc 里挪走了（迁去了 libtirpc），sysroot 里根本没有 `rpc/rpc.h`；可 `BR2_TOOLCHAIN_EXTERNAL_INET_RPC` 对 glibc 又是默认 y，所以你必须**显式关掉**它——defconfig 里写一行 `# BR2_TOOLCHAIN_EXTERNAL_INET_RPC is not set`。

这三个坑补完，剩下的 check（kernel headers、gcc version、arm abi、MMU、SSP）一路绿灯，进 staging → busybox → rootfs，出图。

## canonical 调用

踩完坑定型的调用长这样：

```bash
cd third_party/buildroot
TC=/opt/arm-gnu-toolchain-15.2.rel1-x86_64-arm-none-linux-gnueabihf
export PATH="$TC/bin:$(printf '%s' "$PATH" | tr ':' '\n' | grep -vE '/mnt/|[[:space:]]' | paste -sd:)"
make rk3506_aes_defconfig   # 改了 defconfig 必须跑这个，olddefconfig 不重读 defconfig！
make
```

那一长串 `printf | tr | grep -vE | paste` 就是把 PATH 里的 `/mnt/*` 和带空格的条目滤掉，再前置工具链 bin——坑一的解法。下面两个易踩点要记牢：一是**改了 `configs/*.defconfig` 之后要跑 `make <name>_defconfig`，不是 `make olddefconfig`**——后者只对账现有 `.config`、不重读 defconfig 文件（这次语言标志第一次没生效就是栽在这）；二是别画蛇添足传 `O=output`，buildroot 默认 `O=$(CURDIR)/output` 已经把 build 树放进 `output/` 了、`.config` 留 in-tree，是上游设计不是 hack。

## 成功长这样

`make` 跑完，`output/images/` 里就有了我们要的东西：

```
rootfs.cpio   8.21 MB   ← 给 initramfs 用
rootfs.tar    8.76 MB   ← 给 UBIFS staging 用
```

里面的 busybox 是 ARM EABI5 **hard-float**（`ld-linux-armhf.so.3`），动态链接，`/sbin/init` 是 busybox 的符号链接，`/etc/inittab|passwd|shadow` 齐全，glibc 运行时加 libstdc++ 都在 `/lib`，FHS 结构完整。一份正规的、能烧能启的最小 rootfs，到手。

这份 rootfs 烧进板子跑起来，是 [boot-sdl-202606181919](../../logs/boot-sdl-202606181919.txt) 那轮——主线 U-Boot → ubiprog 置备 → switch_root → `Welcome to rk-forge buildroot` → root 登录。不过那一轮里的 ubiprog 和持久化细节，是 Ch3 的事；这章你只要知道，buildroot 出的这份 rootfs，板上能跑进 shell。

rootfs 的内容有了。但内核 handoff 到这份 rootfs、busybox init 把 shell 起起来，中间还卡着两道 init 时序的暗门——一道是控制台被抢、一道是新根的 `/dev` 是空的。我们 Ch2 见。
