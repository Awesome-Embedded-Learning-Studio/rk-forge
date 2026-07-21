# Ch0 — 路线图：从 panic 到 login，rootfs 这条最深的路

> boot 系列走完，板子能到 `Starting kernel` 了。但 boot 那个 Ch3 结尾的 `panic: Unable to mount root fs` 还杵在那儿——内核起来了，没地方落根。这个 rootfs 系列就是来消掉这行 panic 的：把 rootfs 做出来、挂上去、跑进 `login:`，还要保证写下去的东西跨冷重启还在。说句心里话，这是整个 bringup 最深的一程，比 boot 难得多——难不在"挂个文件系统"，难在"挂上、持久、还写不崩"。

## 前言：为什么 rootfs 是最深的一程

boot 系列是"把链路点亮"——U-Boot 起来、内核起来、console 亮，每一步都有明确的里程碑，看到 banner 就知道成了。rootfs 这程不一样。它的成功标志不是某一行 banner，而是"我往板子上写了个文件，断电、拔掉、凉透、重新上电，那个文件还在"。这种"跨冷重启持久"的要求，会把咱们逼进 NAND 读写、文件系统一致性、还有那个甩不掉的 loader 写可靠性里去。

这程还最容易冒出"判死"的绝望时刻。咱们看着 `echo > /test.txt; sync; reboot`，回来发现 rootfs 炸了、panic 了，一崩好几天，咱们会怀疑是 NAND 坏了、是内核写坏了、是 rkbin 通病不可解。我们在这程里真有过一个"rkbin 通病、换啥 loader 都没用、不可解"的判死结论，差点就信了、差点转头去拆 rkbin——最后被一个干净到不能再干净的 A/B 实验推翻。这些弯路，我们都会在这程里如实走给咱们看，踩过的雷咱们就不必再踩。

## 两条路：initramfs 凑合，UBIFS 才算数

把 rootfs 弄上板，其实有两条路，先分清楚。

**initramfs** 是把 rootfs 打包进 kernel FIT 当 ramdisk，内核起来直接解到内存里跑。它的好处是简单——不依赖任何存储读写，boot 系列后期我们就是靠它先拿到 shell 的。但它有个致命伤：rootfs 在内存里，断电即逝，咱们写的任何东西重启就没了。它是"凑合能用"，不是"真能用"。

**UBIFS** 才是我们要的——rootfs 落进 SPI-NAND，以 UBI 卷的形式持久存在，写下去的东西跨冷重启还在。这才是"一块能用的板子"该有的样子。但这就要和 SPI-NAND 的读写可靠性、UBIFS 的一致性、还有那个甩不掉的 loader 写可靠性正面交锋了。rootfs 系列的主线，就是走通这条 UBIFS 路。

## 这个系列怎么走

把这条路拆成三章，每章啃一块。

**Ch1 buildroot 最小 rootfs**——rootfs 的"内容"从哪来。我们用 buildroot 走正规流程出一个 busybox rootfs，不再手搓。这章踩的是构建侧的坑：WSL 把 Windows PATH 互操作进来，那个带空格的 `/mnt/c/Program Files/...` 能让 buildroot 当场拒跑；外部工具链的语言检查还会 C++/Fortran/OpenMP 连环绊咱们。

**Ch2 init 时序：从 switch_root 到 login**——rootfs 有了，怎么从内核 handoff 切进去、busybox init 怎么把 shell 起起来。这章两道暗门都不在驱动层、全在 init 时序：控制台被两个 respawn 抢着用、输入字符当场劈成两半；切到真 rootfs 之后，新根的 `/dev` 居然是个空目录。

**Ch3 UBIFS 与 loader 弱写 saga**——本系列最深的一章。rootfs 落进 SPI-NAND 要持久 RW，结果一写就崩。我们从"读路径 DLL 没调谐"一路查到"loader 写弱我们这份 rootfs"，中间判过一次死、被 A/B 实验翻案，最后的解法出人意料——别让 loader 写 rootfs，改由 Linux 自己落盘。

还有一颗伪装弹得提前打个招呼：写到一半板子会 external abort，看着活脱脱就是 SFC 写路径的锅，真因却是 DT 没给 OP-TEE 留 reserved-memory——secure 物理页被分给了用户态进程，一访问就炸。这条坑藏在 saga 里两轮都没被识破，我们专门写在 [pitfalls/05](../../pitfalls/05-secure-mem-reservation-imprecise-abort.md)，Ch3 里会点到、不展开。

## 成功长这样

这一程走到头，板子上是这样的——rootfs 真正落进 SPI-NAND、跨冷重启数据还在。下面几行，从我们 RW 达成的 milestone log（[boot-sdl-202606162254](../../logs/boot-sdl-202606162254.txt)）里截的：

```
UBIFS (ubi0:0): recovery needed
UBIFS (ubi0:0): recovery completed
UBIFS (ubi0:0): UBIFS: mounted UBI device 0, volume 0, name "rootfs"
```

跨冷重启 UBIFS 能 replay（`recovery needed → recovery completed → mounted`），意味着写下去的东西结构完整、扛得住断电。我们拿 `/persist.log` 做了三轮 stress 验证——冷重启三次，日志里 `c1-19.12`、`c2-300.87`、`c3-52.82` 三个时间戳一个字没丢。这就是"持久 RW"的铁证。

走到 [login 提示符](../../logs/boot-sdl-2026-06211109.txt)，是这条路真正的终点：

```
Welcome to rk-forge buildroot
rk3506 login: root
```

boot 系列那个 `panic: Unable to mount root fs`，到这儿彻底消掉。空机器到 `login:`，闭环。我们 Ch1 见。
