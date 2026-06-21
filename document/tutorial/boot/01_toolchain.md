# Ch1 — 工具链：arm-linux-gnueabihf

> 工具链是整条启动链的地基。地基选错——soft-float 装成了 hard-float、前缀对不上、套了厂商的旧版本——后面的 U-Boot、内核、rootfs 会一路错下去，而且错得很难看。所以这一章我们不急着编译任何东西，先把工具链这件事彻底钉死。

## 前言：为什么工具链要单开一章

很多人觉得工具链嘛，`apt install` 一下就完了，有什么好讲的。在 RK3506 这条路上，这个想法会让你在后面踩一串莫名其妙的坑。交叉工具链决定了你在 host 上编出来的每一个二进制，是不是真的能在那颗 32-bit ARM Cortex-A7 上跑、是不是真的吃到了它的硬浮点。选错 ABI，链接能过、内核能起，然后某个浮点路径上突然甩你一个非法指令——这种 bug 排起来能让人掉头发。

所以这一章我们把工具链从"为什么是它"讲到"怎么装、怎么验证"：为什么后缀是 `gnueabihf`、forge 到底用的是哪一套、它和厂商自带的那套什么关系、怎么确认你装对了。

## 目标架构：Cortex-A7 + 硬浮点 → armhf

先把目标搞准。RK3506 的应用核是 32-bit ARM Cortex-A7（三核，外加一个 M0 协处理器），带 VFPv4 和 NEON，硬浮点。映射到工具链上就是三件事：架构是 `arm`，ABI 是 `armhf`（hard-float），所以工具链前缀的后缀是 `gnueabihf`（`hf` = hard-float）。

这里第一个坑就已经冒头了。Debian/Ubuntu 仓库里同时有 `gcc-arm-linux-gnueabihf` 和 `gcc-arm-linux-gnueabi` 两兄弟，前者硬浮点、后者软浮点。RK3506 必须用带 `hf` 的那个。装成软浮点那套，你不会立刻收到报错，编出来的东西甚至"能跑"，但只要走到任何浮点密集的路径上，行为就是不可预测的。别问我是怎么知道的。

## forge 真正用的工具链：Arm GNU 15.2

接下来这件事很重要，也是 forge 和大多数教程不一样的地方：我们**不是**用 `apt` 装的那个 `gcc-arm-linux-gnueabihf`。forge 锁定的工具链是 **Arm GNU Toolchain 15.2.Rel1**（gcc 15.2.1），解压在 `/opt` 下，前缀是 `arm-none-linux-gnueabihf-`。

为什么不用 apt 那套、也不用厂商自带的？因为笔者希望的是用上最前沿的编译器——这也就意味着您可以享受任何最现代的软件（至少，支持好，优化强），目标之一就是把构建链上每一个借厂商的地方都换掉。早期我们用的是 ATK BSP 里自带的 Linaro gcc 10.3，板上的 U-Boot、内核、rootfs 都是它编出来、并逐字节板上验证过的——这是一条已知的、可靠的底线。后来我们把它换成了上游的 Arm GNU 15.2，并在 2026-06-17 完成了板上复验：用 15.2 编出来的链，主线 boot 和 NAND 读写都过了。所以现在 15.2 是正式工具链，gcc 10.3 退居为 fallback——配置里留着注释，万一 15.2 哪天在板上翻车，改一行 `TOOLCHAIN_BIN_DIR` 就能切回去。

这套"用哪个工具链"的真相，全部声明在一个地方：[`config/toolchain.conf`](../../../config/toolchain.conf)。它写明前缀、`/opt` 下的 bin 目录，还有一句要紧的声明——这个文件不 `export` 任何东西，只存配置；真正去读它、把环境导出来的是 [`scripts/lib/toolchain.sh`](../../../scripts/lib/toolchain.sh)。这种"配置和副作用分开"的写法不是洁癖，是为了将来上 Python CLI 时，配置文件能被直接读，而不是非得去 source 一个 shell 脚本。

## 第一步：让 doctor 替你检查环境

forge 给了一个独立的检查脚本，[`scripts/doctor.sh`](../../../scripts/doctor.sh)。你不用记要装哪些包，跑它就行：

```bash
./scripts/doctor.sh
```

它会逐项检查 host 上构建需要的那几样——`git`、`make`、`gcc`、`bc`、`bison`、`flex`、`dtc`、`cpio`、`qemu-system-arm`、`mkimage`，外加交叉工具链和 `python3-pyelftools`。哪样齐了打勾，哪样缺了告诉你。缺包的时候，它**不会**自作主张去 `sudo apt install`——这点是故意的，老版本的 imx-forge 就是栽在这里：一个交互式 apt 把脚本搞得没法被上层（Python / CI）调用。forge 的 doctor 只是把修复命令打到 stdout，你复制粘贴去执行，退出码 0 表示全齐、1 表示缺东西。干净、可脚本化。

如果你在 WSL2 里跑，doctor 还会多提醒你一句：USB 烧录（`rkdeveloptool`）需要在 Windows 侧装 `usbipd-win`，但 SD 卡烧录可以直接走，不受影响。这个我们到 Ch2 烧录那步再细讲。

> 这里有个要留意的细节：doctor 在发现交叉工具链缺失时，提示你装的是 apt 包 `gcc-arm-linux-gnueabihf`，那个装出来的前缀是 `arm-linux-gnueabihf-`（中间没有 `none`）。而 forge 配置锁的是 `arm-none-linux-gnueabihf-`，这俩不是同一个前缀。doctor 的提示更多是"给你一个能快速起步的 armhf 编译器"；要和项目正式工具链对齐，还是得把 `/opt` 下的 Arm GNU 15.2 装好，让 `arm-none-linux-gnueabihf-gcc` 进 PATH。

## 第二步：把环境导出来

工具链装好之后，下一步是 source 环境脚本：

```bash
source scripts/env-setup.sh
```

注意是 `source`，不是直接执行——直接跑它，导出的变量出不了那个子进程。这个脚本做的事很简单：读 `toolchain.conf`，把 `ARCH`、`CROSS_COMPILE`（也就是 `arm-none-linux-gnueabihf-`）、`PROJECT_ROOT` 导出来，并把 `/opt` 那个 bin 目录加到 `PATH` 最前面。跑完它会打印一行确认，告诉你当前的 `ARCH`、`CROSS_COMPILE`、`PROJECT_ROOT` 是什么。

有个 shell 上的小坑提前说一下。如果你的登录 shell 是 zsh（现在不少发行版默认就是它），脚本里用 `BASH_SOURCE` 定位自己，zsh 下这个变量是空的。`source` 环境变量这一下通常没事，但跑 `forge.sh` 那种编排脚本时，养成习惯一律用 `bash scripts/forge.sh ...` 来调，别直接 `./scripts/forge.sh`，省得在 shell 兼容性上栽跟头。

## 第三步：验证编出来的东西真的是 32-bit ARM

装完、导完，最后一步是验证这套工具链产出的二进制确实是对的。编一个最简单的 C，或者直接拿后面会编出来的 U-Boot / 内核产物，用 `readelf` 看它的头：

```bash
${CROSS_COMPILE}readelf -h <某个.elf>
```

`toolchain.conf` 里记录了我们本机实测的验证值，拿来对一下就知道对不对：`Machine: ARM`，`Flags: 0x5000400`（hard-float ABI），`Tag_CPU_arch: v7`，`Tag_FP_arch: VFPv3`——这一组正好匹配 Cortex-A7 / armhf。看到 `Machine: ARM` 而不是 `AArch64`，看到 hard-float 而不是 soft，工具链这一关就算过了。

## 踩坑小结

把这一章的坑集中摆一下，你后面回头查也方便。

最致命的是 soft-float vs hard-float。RK3506 是 Cortex-A7、带硬浮点，工具链后缀必须是 `gnueabihf`，装成 `gnueabi`（无 `hf`）那套就是埋雷。然后是前缀里的那个 `none`：apt 的 `gcc-arm-linux-gnueabihf` 前缀是 `arm-linux-gnueabihf-`，forge 配置锁的是 `arm-none-linux-gnueabihf-`，别混着用。再就是 host 依赖的轻重——厂商那套 BSP 在 Ubuntu 24.04 上要装四十来个包（见 [host-deps-ubuntu24](../../logs/host-deps-ubuntu24.txt) 的实测对照），主线这边 doctor 只查十几样，轻得多；但主线要编 binman / pylibfdt，得额外有 `swig`、`python3-dev`、`python3-pyelftools`，这几个 doctor 也会查。最后，WSL2 用户记住 USB 烧录要 `usbipd-win`，SD 卡烧录不用。

## 成功长这样

到这一步，你的环境应该长这样：`./scripts/doctor.sh` 全绿、退出 0；`source scripts/env-setup.sh` 之后 `echo $CROSS_COMPILE` 能打出 `arm-none-linux-gnueabihf-`；随便编个东西 `readelf` 看到的是 `Machine: ARM` + hard-float。

工具链钉死了，地基稳了，下一章我们就要往这块地基上放第一块砖——和那个绕不开的闭源 rkbin 正面交锋，把主线 U-Boot 打包出来、烧到板上，亲眼看它的 banner 从串口里蹦出来。我们 Ch2 见。
