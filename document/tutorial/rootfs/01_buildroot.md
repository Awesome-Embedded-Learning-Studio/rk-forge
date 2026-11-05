# Ch1 — buildroot：出一份正规的最小 rootfs

> boot 系列后期咱们靠一个手搓的静态 busybox initramfs 凑合过，能拿到 shell 就算赢了。rootfs 这程要的是一份正规的、可维护的 rootfs，所以上 buildroot。这章踩的全是构建侧的雷：WSL 会把 Windows 的 PATH 互操作进来、外部工具链的语言检查连环绊咱们、glibc 还把 RPC 挪走了，踩完手里才有一份能烧能启的 busybox rootfs。

## 前言：为什么不再手搓

boot 系列拿 shell 的法子是一个手搓 initramfs：静态 busybox 加一个 `/init`，塞进了 kernel FIT 当 ramdisk。它确实跑通了，但那是为快速验证启动链的凑合，rootfs 的内容全靠手维护，加个工具就得咱们自己交叉编译、自己塞 overlay，这么搞是不可持续的。

rootfs 这程要的是正规流程，所以上 buildroot。buildroot 会从源码给你编一整个最小 Linux 根文件系统：busybox、glibc 运行时、init 配置、FHS 目录结构，一条 `make` 就出齐了。RK3506 的核是 Cortex-A7 / NEON-VFPv4，工具链就用咱们在 [boot Ch1](../boot/01_toolchain.md) 敲定的那套，`/opt` 下的那套 Arm GNU 15.2，和板上 boot+RW 验过的完全一致，咱们不另起炉灶。

## 材料：buildroot 本体 + 咱们的 BR2_EXTERNAL

buildroot 本体用 loose 检出的上游 2026.08-dev，仓库在 `third_party/buildroot/`、状态是 gitignored 的，和 uboot/linux 的 explore 模式一样。定制这一块咱们不直接改 buildroot，而是通过一棵 **BR2_EXTERNAL 树**注入：[`board/aes/buildroot-external/`](../../../boards/aes/buildroot-external/) 这棵树是 rk-forge 自有、进版本控制的，里面放着的是 `configs/rk3506_aes_defconfig`（板级 defconfig），overlay 管的是 `/etc` 配置和 init 脚本，树里的 post-build hook 也一起放着。调用的时候跑 `make BR2_EXTERNAL=.../buildroot-external rk3506_aes_defconfig`，buildroot 就会注册这棵外部树、读咱们的 defconfig。

本体 loose、定制走 BR2_EXTERNAL 的结构不是洁癖。它是踩过雷才定下来的。当年咱们 `git add -A` 把 buildroot 当 embedded git 仓（gitlink）加进去，结果 clone 根本拿不到内容。解法就是 buildroot 本体保持 gitignored 的状态，defconfig 和 overlay 就全挪进了 BR2_EXTERNAL，挪进这棵真正进版本控制的树。详细的决策记在 [notes/19](../../notes/19-2026-06-18-buildroot-minimal-rootfs-first-build.md)。

## defconfig 的几个关键决策

defconfig 里要紧的选择，咱们逐条过一下。架构选的是 `arm`、`cortex-a7`、`neon-vfpv4`，对应的是 RK3506 的核心。工具链用的是 external，指向 `/opt` 的 Arm GNU 15.2，而不是让 buildroot 自己编一个，这样 rootfs 用的工具链和 kernel/uboot 就是同一份。init 走的是 busybox 加 sysv init。输出格式选了两种：`cpio` 给 initramfs 用，`tar` 则是给 UBIFS staging 用的。

有一条是刻意没开的：`BR2_TARGET_ROOTFS_UBIFS`。咱们选的是 tar 交给现有 `pack-ubifs.sh` 打包的路子，为的是复用已经验证过的 NAND 打包管线，而不是在 buildroot 里再开一条 UBIFS 直出的路。少了一条路，也就少了一份维护。

## 翻车一：WSL 的 PATH 里带空格，buildroot 当场拒跑

翻车里死得最快的一场，咱们连工具链校验都没走到就倒下了。WSL 会把 Windows 的 PATH 互操作进来，于是 `PATH` 里赫然躺着 `/mnt/c/Program Files/...` 一类带空格的条目。buildroot 的 `dependencies.mk:27` 一看 PATH 里有空格，直接就甩了一句 `Your PATH contains spaces, TABs, and/or newline`，然后就 exit 1、连配置都不让咱们生成。

这个毛病其实不怪 buildroot、也不怪 defconfig，纯纯是环境的问题。修法是咱们在跑 buildroot 之前把 `PATH` 里所有 `/mnt/*` 和含空白字符的条目剥掉，再把工具链的 bin 目录前置进去。具体的写法见后面 canonical 调用里那一行 `tr` + `grep -vE`，就是干这个的。

## 翻车二：外部工具链的语言检查，C++/Fortran/OpenMP 连环绊

PATH 弄干净了、进到工具链校验，连环的雷就来了。Arm GNU 的工具链是全套，bin 里的 g++、gfortran 都在，gcc 的身上还有 OpenMP。buildroot 的 `check_cplusplus` / `check_fortran` / `check_openmp` 要求 defconfig 必须老老实实承认工具链实际带的每一种语言，哪一种少承认了，configure 阶段就直接 exit 1 了。它还连着绊咱们：等咱们补上 C++，下一个又卡在了 Fortran、再下一个是 OpenMP，一个接一个地来。

解法是咱们在 defconfig 里把这几项全开。开 `BR2_TOOLCHAIN_EXTERNAL_CXX=y` 的效果是 select `BR2_INSTALL_LIBSTDCPP`、往 rootfs 装 libstdc++、也就几 MB，174MiB 的 UBIFS 装得下、无所谓。而 `BR2_TOOLCHAIN_EXTERNAL_FORTRAN=y` 和 `BR2_TOOLCHAIN_EXTERNAL_OPENMP=y` 只是能力上的声明、不装任何运行时。D 语言倒是不用管——这套工具链没带 gdc、check 自动过。

## 翻车三：glibc 2.42 把 RPC 挪走了

语言检查过了，接下来咱们又被 `check_glibc_rpc_feature` 绊住了，报的是 `RPC support not available in C library, please disable BR2_TOOLCHAIN_EXTERNAL_INET_RPC`。glibc 2.42 早就把 Sun RPC 从 libc 里挪走了（迁去了 libtirpc），sysroot 里压根没有 `rpc/rpc.h` 的影子。偏偏 `BR2_TOOLCHAIN_EXTERNAL_INET_RPC` 对 glibc 又是默认 y，所以你必须显式关掉它，写进 defconfig 的就是一行 `# BR2_TOOLCHAIN_EXTERNAL_INET_RPC is not set`。

三场翻车咱们都补完了，剩下的那些 check（kernel headers、gcc version、arm abi、MMU、SSP）一路绿灯，一路走完了 staging、busybox、rootfs，最后图就出来了。

## canonical 调用

咱们踩完雷之后定型的调用长这样：

```bash
cd third_party/buildroot
TC=/opt/arm-gnu-toolchain-15.2.rel1-x86_64-arm-none-linux-gnueabihf
export PATH="$TC/bin:$(printf '%s' "$PATH" | tr ':' '\n' | grep -vE '/mnt/|[[:space:]]' | paste -sd:)"
make rk3506_aes_defconfig   # 改了 defconfig 必须跑这个，olddefconfig 不重读 defconfig！
make
```

那一长串 `printf | tr | grep -vE | paste` 就是把 PATH 里的 `/mnt/*` 和带空格的条目滤掉，咱们再把工具链的 bin 前置进去——这就是翻车一的解法。

有两个易踩的点咱们得记下来。一是改了 `configs/*.defconfig` 之后要跑的是 `make <name>_defconfig`，**不是** `make olddefconfig`——后者只对已有的 `.config` 做比对、不重读 defconfig 文件，这次的语言标志头一回没生效，就栽在了这上面。二是咱们别画蛇添足传 `O=output`，buildroot 默认 `O=$(CURDIR)/output` 已经把 build 树放进 `output/` 了、`.config` 留 in-tree，这本来就是上游的设计、不是 hack（`git diff Makefile` 空）。

自动化的事咱们也顺带交代一句。当年这个调用咱们封进过 `scripts/build-rootfs.sh`，直接跑 `scripts/build-rootfs.sh [--reconfigure] [--clean]` 就可以了。脚本里 PATH 清洗走 `lib/host.sh` 的 `forge_clean_path`，工具链路径走 `lib/toolchain.sh` 从 `config/toolchain.conf` 推导出来的单一来源（commit a3f2936），所以工具链挪位置只动 `toolchain.conf` 一处，不用改 defconfig 里的硬编码，也不用咱们手改 PATH。这一套已随 cce9f63 退役了，继任的是 [src/forge/build/rootfs.py](../../../src/forge/build/rootfs.py)：PATH 清洗并进了 [src/forge/build/host.py](../../../src/forge/build/host.py) 的 `clean_path`，工具链的单一来源挪进了 [boards/aes/board.yaml](../../../boards/aes/board.yaml) 的 `toolchain:` 块，构建时从 `toolchain_bin_dir` 改写 defconfig 里硬编码的路径，单一来源的立场没变。

## 成功长这样

`make` 跑完了，`output/images/` 里就有了咱们要的东西：

```
rootfs.cpio   8.21 MB   ← 给 initramfs 用
rootfs.tar    8.76 MB   ← 给 UBIFS staging 用
```

咱们再看内容：busybox 是 ARM EABI5 **hard-float**（`ld-linux-armhf.so.3`）、动态链接，`/sbin/init` 是 busybox 的符号链接、`/etc/inittab|passwd|shadow` 齐全，glibc 的运行时加 libstdc++ 都在 `/lib`，FHS 的结构也是完整的。一份正规的、能烧能启的最小 rootfs，到手了。

rootfs 烧进板子跑起来的那一轮记录在 [boot-sdl-202606181919](../../logs/boot-sdl-202606181919.txt)，链路走的是主线 U-Boot 起 ubiprog 置备、switch_root 切根，打出 `Welcome to rk-forge buildroot` 的横幅，最后 root 登了进去。把 rootfs 打包进 NAND 用的 FIT packer 已经从早期的原厂 mkimage 换成了纯 Python 的 [`scripts/fit-pack.py`](../../../src/forge/tools/fit_pack.py)（字节级复现原厂 mkimage 的 SPL 兼容 -E 外部数据布局，见 [notes/20](../../notes/20-2026-06-19-mkimage-saga-handoff.md) 的记录），ubiprog 和持久化细节则是 Ch3 的事。这章咱们只要知道一条：buildroot 出的 rootfs，板上就能跑进 shell 了。

rootfs 的内容有了。但从内核 handoff 到 busybox init 把 shell 起起来的这一段，中间还卡着两道 init 时序的暗门：头一道是控制台被抢了，另一道是新根的 `/dev` 是空的。咱们 Ch2 见。
