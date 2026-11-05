# Ch1 — 工具链：arm-linux-gnueabihf

> 工具链是整条启动链的地基。地基要是选错了（soft-float 装成了 hard-float、前缀对不上、套的还是原厂的旧版本），而后面的 U-Boot、内核、rootfs 会一路错下去，而且错得很难看。所以这一章咱们不急着编译任何东西，得把工具链这件事敲定了再说。

## 目标架构：Cortex-A7 + 硬浮点 → armhf

咱们把 RK3506 的应用核看清，它是三核的 32-bit ARM Cortex-A7（外加一颗 M0 协处理器），VFPv4 和 NEON 也带上了，而且是硬浮点。这三样落到了工具链上，就成了三样配置：架构 `arm`、ABI `armhf`（hard-float），还有前缀后缀 `gnueabihf`（那个 `hf` 指的就是 hard-float）。

第一颗雷其实已经冒头了。Debian/Ubuntu 的仓库里同时摆着 `gcc-arm-linux-gnueabihf` 和 `gcc-arm-linux-gnueabi` 两兄弟，差别就在一个 `hf` 的有无上：前者硬浮点、后者软浮点。RK3506 必须用带 `hf` 的那个。装成了软浮点那一套，咱们不会立刻收到报错，编出来的东西甚至“能跑”，但只要走到任何浮点密集的路径上，行为就是不可预测的，非法指令会从最不起眼的地方甩咱们一脸。别问笔者是怎么知道的。

## forge 锁的工具链：Arm GNU 15.2，不是 apt 那套

接下来要说的这件事，是 forge 和大多数教程分叉的地方。咱们**不是**用 `apt` 装的那个 `gcc-arm-linux-gnueabihf`。forge 锁定的工具链是 **Arm GNU Toolchain**，版本定在了 **15.2.Rel1**（gcc 15.2.1），解压的位置在 `/opt` 下面，前缀用的是 `arm-none-linux-gnueabihf-`，注意中间的那个 `none`，apt 包是没有它的。

为什么不用 apt 那套、也不用 ATK 自带的？咱们想要的是用上最前沿的编译器，享受最现代的优化和软件支持，咱们还抱着一条明确的目标，就是把构建链上每一个借原厂的地方都换掉。早期咱们用的是 ATK BSP 里自带的 Linaro gcc 10.3，板上那套 U-Boot、内核、rootfs 都是它编出来、并逐字节板上验证过的，这是一条已知的、可靠的底线。后来咱们把它换成了上游的 Arm GNU 15.2，并在 2026-06-17 完成了板上复验：用 15.2 编出来的链，主线 boot 和 NAND 读写都过了。所以现在 15.2 是正式工具链，gcc 10.3 退到了 fallback 的位置，配置里留了注释，万一 15.2 哪天在板上翻了车，改一行 `TOOLCHAIN_BIN_DIR` 就能切回去了。buildroot 那一路后来也接了同一个外部工具链（详见 [notes/19](../../notes/19-2026-06-18-buildroot-minimal-rootfs-first-build.md)），glibc 2.42、headers 6.6.76 的组合在板上也起得来。

咱们要查“用哪个工具链”的真相，它全声明在一个地方：[`config/toolchain.conf`](../../../config/toolchain.conf)。它写明前缀（`TOOLCHAIN_PREFIX`）、`/opt` 下的 bin 目录（`TOOLCHAIN_BIN_DIR`），还有一句要紧的注释，写的是这个文件本身不 `export` 任何东西、只存配置，真正去读它、把环境导出来的是 [`scripts/lib/toolchain.sh`](../../../scripts/lib/toolchain.sh)。“配置和副作用分开”的写法并不是洁癖：等到将来上 Python CLI 的时候，配置文件是可以被直接读的，而不是非得去 source 一个 shell 脚本。最近的 refactor（commit `a3f2936`）把工具链路径彻底改成了从 `toolchain.conf` 派生，以前依赖的是 PATH 里碰巧有它，现在脚本显式拼的是 `${TOOLCHAIN_BIN_DIR}:${PATH}`，路径从哪来一目了然，调试和复现也都干净了。

## 让 doctor 替咱们检查环境

forge 给了一个独立的检查脚本 [`scripts/doctor.sh`](../../../scripts/doctor.sh)。咱们不用记要装哪些包，跑它就行了：

```bash
./scripts/doctor.sh
```

它会逐项检查 host 上构建需要的那几样：`git`、`make`、`gcc`、`bc`、`bison`、`flex`、`dtc`、`cpio`、`qemu-system-arm`、`mkimage`，再加交叉工具链和 `python3-pyelftools` 的检查。哪样齐了打勾，哪样缺了告诉你。缺包的时候它**不会**自作主张去 `sudo apt install`，这一点是故意的，老版本的 imx-forge 就是栽在这里，一个交互式的 apt，把脚本搞到了没法被上层（Python / CI）调用的地步。forge 的 doctor 只是把修复命令打到 stdout，咱们复制粘贴去执行，退出码 0 表示的是全齐、1 表示的是缺东西，整体是干净、可脚本化的。

如果咱们在 WSL2 里跑，doctor 还会多提醒咱们一句：USB 的烧录（`rkdeveloptool`）得在 Windows 侧装 `usbipd-win`，但 SD 卡的烧录可以直接走，不受它的影响。这件事咱们到 Ch2 烧录那一步再细讲。

> ⚠️ 这里有个要留意的细节：doctor 在发现交叉工具链缺失的时候，提示咱们装的是 apt 包 `gcc-arm-linux-gnueabihf`，那个装出来的前缀是 `arm-linux-gnueabihf-`（中间没有 `none`）。而 forge 配置锁的是 `arm-none-linux-gnueabihf-`，这俩其实不是同一个前缀，别图省事装了 apt 那套就当对齐了。doctor 的提示更多是“给你一个能快速起步的 armhf 编译器”。想和项目的正式工具链对齐，还是得把 `/opt` 下的 Arm GNU 15.2 装好、让 `arm-none-linux-gnueabihf-gcc` 进 PATH。

## 把环境导出来

工具链装好了，下一步咱们要 source 环境脚本：

```bash
source scripts/env-setup.sh
```

咱们要注意的是 `source`，而不是直接执行，直接跑的话，导出的变量出不了那个子进程。脚本做的事很简单：它去读 `toolchain.conf` 里的配置，把 `ARCH`、`CROSS_COMPILE`（也就是 `arm-none-linux-gnueabihf-`）、`PROJECT_ROOT` 给咱们导出来，并把 `/opt` 下的 bin 目录加到 `PATH` 的最前面（`toolchain.sh` 里那行 `export PATH="${TOOLCHAIN_BIN_DIR}:${PATH}"`）。跑完了它会打印一行确认，告诉你当前的 `ARCH`、`CROSS_COMPILE`、`PROJECT_ROOT` 是什么。

咱们还得提前说一下 shell 这边的一颗小雷。如果咱们的登录 shell 是 zsh（现在不少发行版默认就是它），脚本里用的是 `BASH_SOURCE` 定位自己，zsh 下这个变量是空的。`source` 环境变量的这一下通常没事，但跑 `forge.sh` 那样的编排脚本的时候，咱们要养成习惯一律用 `bash scripts/forge.sh ...` 来调，而不是直接 `./scripts/forge.sh`，省得咱们在 shell 兼容性上栽跟头。

### WSL2 那个 PATH 含空格的坎

WSL2 的用户还得过一个坎。Windows 默认是把整个 Windows PATH 互操作进来的，里面塞满了 `/mnt/c/Program Files/...`、`/mnt/c/Users/.../AppData/...` 这样带空格的路径条目。日常用倒是没事，但 buildroot 的 `support/dependencies/dependencies.mk` 只要见到 PATH 里任何一条带空格、TAB 或换行的条目，就直接给你 exit 1，出错的时候连工具链校验都还没跑到，打出来的错误信息是 `Your PATH contains spaces, TABs, and/or newline`。咱们头一回遇上它的时候，盯着 defconfig 排查了半天，根因其实在环境。

咱们把修法放在了 [`scripts/lib/host.sh`](../../../scripts/lib/host.sh) 里。干活的函数是 `forge_clean_path`，它把 PATH 按 `:` 的分隔切开，剥掉所有以 `/mnt/` 开头的条目和任何含空白字符的条目、再 paste 回去：

```bash
forge_clean_path() {
  printf '%s' "${PATH:-}" | tr ':' '\n' | grep -vE '^/mnt/|[[:space:]]' | paste -sd:
}
```

在 buildroot 之前咱们调一句 `PATH=$(forge_clean_path) make ...` 就能跑通。forge 编排器会在构建开始的时候调一次 `forge_warn_windows_path`，PATH 脏了就给你一行警告，这是 host.sh 顶上注释里写明的约定：编排器负责提醒一次，真正需要干净 PATH 的那个 build（buildroot），调 `forge_clean_path` 的活归它自己。kernel 和 U-Boot 这边对 PATH 空格的敏感性没这么高，咱们不强制剥。这是环境的问题，而不是 buildroot 或 defconfig 的问题，这一点咱们记下了，能省很多误诊的时间。

## 验证编出来的东西真的是 32-bit ARM

装完了、导完了，最后一步是验证这套工具链产出的二进制确实是对的。咱们编一个最简单的 C，或者直接拿后面会编出来的 U-Boot / 内核产物，用 `readelf` 看它的头：

```bash
${CROSS_COMPILE}readelf -h <某个.elf>
```

`toolchain.conf` 里记录了咱们本机实测的验证值，拿来一对就知道对不对了：`Machine: ARM`、`Flags: 0x5000400`（hard-float ABI 的标志）、`Tag_CPU_arch: v7`、`Tag_FP_arch: VFPv3`，这一组正好匹配的是 Cortex-A7 / armhf。看到 `Machine: ARM` 而不是 `AArch64`，看到 hard-float 而不是 soft，工具链这一关就算过了。buildroot 那一路出来的 busybox 是 ARM EABI5 hard-float（`ld-linux-armhf.so.3`），跟主线编出来的内核是同一个 ABI，也就能摆在一起用了。

## 几个回头查起来方便的雷

soft-float 对 hard-float 的选择最致命。RK3506 的核是 Cortex-A7、带硬浮点，工具链的后缀必须是 `gnueabihf`，装成 `gnueabi`（无 `hf`）的那套就是埋雷，编译倒是能过、内核也能起，然后在某个浮点路径上甩你一条非法指令。再就是前缀里的那个 `none`：apt 的 `gcc-arm-linux-gnueabihf` 前缀是 `arm-linux-gnueabihf-`，forge 配置锁的是 `arm-none-linux-gnueabihf-`，俩其实不是一回事，咱们别混着用。host 依赖的这一块，原厂 BSP 在 Ubuntu 24.04 上要装四十来个包（见 [host-deps-ubuntu24](../../logs/host-deps-ubuntu24.txt) 的实测对照），主线这边 doctor 只查了十几样，轻了一个量级。但主线要编的还有 binman / pylibfdt，得额外装的还有 `swig`、`python3-dev`、`python3-pyelftools`，这几个其实 doctor 也会查。WSL2 的读者最后还要记一条，PATH 含空格的毛病会卡 buildroot，咱们调 `forge_clean_path` 就行。USB 的烧录要 `usbipd-win`，SD 卡的烧录不用它。

## 成功长这样

咱们到这一步，环境应该长这样：`./scripts/doctor.sh` 检查项全部打勾、退出码回到了 0。环境脚本 source 完了之后，`echo $CROSS_COMPILE` 能打出的是 `arm-none-linux-gnueabihf-`。随便编个东西 `readelf` 看到的是 `Machine: ARM` + hard-float。

工具链敲定了，地基也稳了，下一章咱们就要往这块地基上放第一块砖了：和那个绕不开的闭源 rkbin 正面交锋，咱们把主线 U-Boot 打包出来、烧到板上，亲眼看它的 banner 从串口里蹦出来。咱们 Ch2 见。
