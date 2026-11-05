# Ch0 — 路线图：从 panic 到 login，rootfs 这条最深的路

> boot 系列走完了，板子能到 `Starting kernel` 了。但 boot 那个 Ch3 结尾的 `panic: Unable to mount root fs` 还杵在那里——内核起来了，root 却没了落脚的地方。这个 rootfs 系列就是咱们来消掉这行 panic 的：把 rootfs 做出来、挂上去、跑进 `login:`，还要保证写下去的东西跨冷重启还在。说句心里话吧，这是整个 bringup 最深的一程，比 boot 难得多——难的不在挂个文件系统，难的是挂上、持久、还写不崩。

## 前言：为什么 rootfs 是最深的一程

boot 系列干的是把链路点亮的活：U-Boot 起来、内核起来、console 亮，每一步都有明确的里程碑，看到 banner 就知道成了。rootfs 这程就不一样了。它的成功标志不是某一行 banner。真正的验收是咱们真往板子上写一个文件，然后断电、拔掉电源、凉透了再重新上电，那个文件还原封不动地待在原处。持久的要求要跨过冷重启，就会把咱们逼进 NAND 读写、文件系统一致性，还有那个甩不掉的 loader 写可靠性里去。

这程还最容易冒出判死式的绝望时刻。咱们看着 `echo > /test.txt; sync; reboot`，回来发现 rootfs 炸了、panic 了，一崩就崩了好几天，咱们会怀疑是 NAND 坏了、是内核写坏了、是 rkbin 通病不可解。咱们在这程里真有过一个“rkbin 通病、换啥 loader 都没用、不可解”的判死定论，差点就信了、差点转头去拆 rkbin，最后被一个干净到不能再干净的 A/B 实验推翻了。这些弯路咱们都会在这程里如实再走一遍，踩过的雷咱们就不必再踩了。

## 两条路：initramfs 凑合，UBIFS 才算数

把 rootfs 弄到板上的路其实有两条，咱们得分清楚。

**initramfs** 走的是把 rootfs 打包进 kernel FIT 当 ramdisk 的路子，内核起来后的头一件事就是解到内存里跑。它的好处是简单——不依赖任何存储读写，boot 系列后期咱们就是靠它拿到 shell 的。但它有个致命的短板：rootfs 是待在内存里的，一断电就什么都没了，咱们写进去的任何东西重启后也不会在。它其实顶多算个凑合能用，离真能用还差着关键的一步。

**UBIFS** 才是咱们要的。rootfs 落进了 SPI-NAND，以 UBI 卷的形式持久存在，写下去的东西跨冷重启还在。这才是一块能用的板子该有的样子。但这就得和 SPI-NAND 的读写可靠性、UBIFS 的一致性，还有那个甩不掉的 loader 写可靠性正面交锋了。rootfs 系列的主线，走的就是 UBIFS 这一程。

## 这个系列怎么走

咱们把 rootfs 的路拆成三章来走，每一章啃下自己的一块。

Ch1 讲的是 buildroot 最小 rootfs，管的是 rootfs 的内容从哪儿来。咱们用 buildroot 走正规流程出一个 busybox rootfs，不再手搓了。这章踩的全是构建侧的雷：WSL 会把 Windows 的 PATH 互操作进来，那个带空格的 `/mnt/c/Program Files/...` 能让 buildroot 当场拒跑。外部工具链的语言检查也会连环绊咱们，C++、Fortran、OpenMP 一个接一个地来。

Ch2 讲的是 init 时序：从 `switch_root` 一路到 `login:`，rootfs 有了，这一段的卡点是怎么从内核 handoff 切进去，busybox init 又是怎么把 shell 起起来的。这一章的两道暗门都不在驱动层、全在 init 时序上：一道是控制台被两个 respawn 抢走了，输入的字符当场劈成两半。另一道是等咱们切到真 rootfs 之后，新根的 `/dev` 居然是个空目录。

**Ch3 UBIFS 与 loader 弱写**——本系列最深的一章。咱们要让 rootfs 落进 SPI-NAND 做持久 RW，结果一写就崩。咱们从读路径的 DLL 没调谐，一路查到了 loader 写弱咱们自己的 rootfs，中间判过一次死、又被 A/B 实验翻了案，最后的解法出人意料：rootfs 的写入别再交给 loader，而是让 Linux 自己写进存储。

还有一颗伪装弹得提前给咱们打个招呼：写到一半板子就 external abort 了，看着活脱脱就是 SFC 写路径的锅，真凶偏偏是 DT 没给 OP-TEE 留 reserved-memory，secure 物理页被分给了用户态进程，一访问就炸了。这颗雷在整场拉锯里藏了两轮都没被识破，咱们专门写在 [pitfalls/05](../../pitfalls/05-secure-mem-reservation-imprecise-abort.md)，Ch3 里咱们只点到、不展开。

## 成功长这样

这一程走到头了，板子上是这样的：rootfs 真正落进了 SPI-NAND，跨冷重启之后数据还是全的。下面这几行是从咱们 RW 达成的 milestone log（[boot-sdl-202606162254](../../logs/boot-sdl-202606162254.txt)）里截的：

```
UBIFS (ubi0:0): recovery needed
UBIFS (ubi0:0): recovery completed
UBIFS (ubi0:0): UBIFS: mounted UBI device 0, volume 0, name "rootfs"
```

跨冷重启之后 UBIFS 的 replay 跑得通（`recovery needed → recovery completed → mounted`），意味着写下去的东西结构完整、扛得住断电。咱们拿 `/persist.log` 做了三轮 stress 验证——冷重启三次，日志里的三个时间戳 `c1-19.12`、`c2-300.87`、`c3-52.82` 一个字都没丢。这就是持久 RW 实打实的证据。

等咱们走到 [login 提示符](../../logs/boot-sdl-2026-06211109.txt)，整条路才算有了真正的终点：

```
Welcome to rk-forge buildroot
rk3506 login: root
```

boot 系列遗留的那行 `panic: Unable to mount root fs`，到这儿就彻底消掉了。从空机器一路跑到了 `login:`，整条路也就通了。咱们 Ch1 见。
