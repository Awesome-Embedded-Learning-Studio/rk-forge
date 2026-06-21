# Ch3 — UBIFS 与 loader 弱写 saga：bringup 最深的一关

> Ch2 rootfs 挂上、shell 起来了，先别急着庆祝。这章是整个 bringup 最深的一关——"写下去的东西跨冷重启还在"。听起来朴素，做起来一写就崩、一崩好几天，中间还判过一次"rkbin 通病、不可解"的死结论，差点就信了、差点转头去拆 rkbin。这篇 saga 的完整还原见 [pitfalls/04](../../pitfalls/04-sfc-nand-saga.md)，这里走主线、讲方法。

## 前言：为什么"持久 RW"这么难

boot 是"把链路点亮"，rootfs 挂上是"能跑"，但这章要的是"我写了个文件，断电凉透、重新上电，它还在"。这种跨冷重启持久，逼着你和 SPI-NAND 的读写可靠性、UBIFS 的一致性、还有那个甩不掉的闭源 loader 写可靠性正面交锋。整场悲剧，就出在"谁往 NAND 里写 rootfs"这件事上。

## 先把读路径治了：80MHz 不调谐，采样全是 marginal

故事的起点其实是读，不是写。主线那两颗 SFC 驱动（linux 的 `spi-rockchip-sfc.c`、uboot 的 `rockchip_sfc.c`）明明定义了采样延迟线寄存器，却**从来不写它**——采样从没调谐过；而 vendor 同名驱动里有个 `rockchip_sfc_delay_lines_tuning`。80MHz 跑着、采样又不调谐，采样点落在 marginal 区，bit 翻不翻纯看脸，这就是"时好时坏"的来源。boot Ch3 里我们用 50MHz 降频绕过，这章我们把 vendor 的 DLL 调谐移植进主线驱动、上板扫窗。[boot-sdl-202606160948](../../logs/boot-sdl-202606160948.txt) 里这段输出看得人直呼内行：

```
rockchip_sfc: dll tuning target=50000000Hz real=100000000Hz cell_max=383 step=10 cs=0
rockchip_sfc:   dll window [0, 230] (230 cells)
rockchip_sfc: dll ok best=[0,230] -> cell 92
```

扫出 230-cell 的巨大采样窗口，读路径这才算根治。

## RW 必崩的现场

读稳了，我以为 RW 也该顺理成章——结果 `echo X > /file && sync && reboot -f`，下次 boot 直接 panic：`ubi0` 报 `error -74 (ECC error) ... PEB 3:4096`、`PEB 4:4096`，retry 三次后 -EBADMSG，`Cannot open root device`，kernel panic。PEB 3/4 跨好几轮重刷都坏，稳得让人绝望。

这一段就是 saga 的核心。我顺着时间线把误判一层层剥给你看——因为这条 saga 最值钱的不是某个修法，是那个**怎么会被判错一次**的方法学。

## 四层误判，一层比一层像真的

**第一层：Linux 写把数据写坏了。** 最自然的归因——`echo > /test.txt`、reboot，看上去就是"Linux commit → erase+rewrite PEB 3/4 → 重启 → 读炸"，而且同会话写完立刻读是干净的，崩的只在元数据 PEB 的 commit 上。证据看似自洽，结论却是错的。

**第二层：加探针，第一次指向 loader。** 我在写路径加了 dev_info 探针，发现所有 WRITE/ERASE 都 `prog_fail=0`（写都"成功"），但同会话读 PEB 27 却是 ECC 不可纠——关键是 PEB 27 这次 boot 从头到尾没被写过，坏数据是 loader 烧进去的存量。方向第一次算指对了。

**第三层：换 vendor loader 4762d6 就稳。** 既然是 loader 写的存量，换颗靠谱的 vendor loader 不就行了？当时写下的结论是：我们的 loader 写弱、vendor 的写可靠。这条后来被 A/B 推翻。

**第四层（最严重）：rkbin 通病，换版本无效，不可解。** 我把三颗 loader 全轮了一遍，全崩，于是写下"loader 写不可靠是 rkbin 通病，与版本无关"，据此暂停了这条线、转头去拆 rkbin。这个判死结论现在看是错的，但它当时合理到差点就认了。

## 判死为什么错：一个方法学盲区

判死结论的根子，是验证方法有个共同盲区：**全程只换 rkbin 黑盒（loader），从没让 vendor 内核的 fspi 驱动上过板对比；而且每次说"我们的栈写可靠"，全是同会话当场回读，从没跨重启验证过。**

你想这个盲区会导出什么：症状是"Linux 写 → reboot → 读 = 坏"，我却把所有变量都攥在 rkbin 这一环上换（loader 换了三颗），自然就把锅全扣给 rkbin，得出"换 loader 都救不了 = rkbin 通病"。而"我们的栈写可靠"这个前提，又全是没跨重启的同会话回读——拿一个没跨重启验证的前提，去否定一个跨重启才暴露的症状，逻辑上就站不住。

## 推翻它：一个干净到不能再干净的 A/B

同一颗 loader（4762d6）、同一个内核、同一个分区（mtd5），**我只换 rootfs 的内容**：烧我们自己的 rootfs，boot2 立刻 PEB 3/4/30/32 `error -74` → panic（[boot-sdl-2026-06162015](../../logs/boot-sdl-2026-06162015.txt)）；烧 vendor 的 rootfs，boot2 干干净净 `recovery completed → mounted`，全文 `error -74` 计数为 0（[boot-sdl-202606162146](../../logs/boot-sdl-202606162146-update-nand-OURkernel-VENDORrootfs.txt)）。

这一对照，结论彻底钉死：我们内核的读路径没问题（vendor rootfs 在同内核下跨重启干干净净），**是同一颗 loader 写我们这份小 rootfs 时把 PEB 3/4/30/32 写弱了，写 vendor rootfs 时同位置写得稳稳的**。我们这份 4MB 的小 rootfs 把 UBIFS 的 master/journal 集中在了那几个 PEB，正好命中 loader 的弱写块；vendor 那份大 rootfs 元数据分散，没踩中。所以不是内核、不是硬件、不是 ECC 配置、更不是 Linux 写坏——**就是 loader 对我们这份 rootfs 的写**。

> 别把所有写崩都扣给 rkbin。验证 loader 写弱不弱，要做的是拆开变量的 A/B：同 loader + 同内核 + 同分区，只换 rootfs 内容。只换 rkbin 黑盒、又不让 vendor 驱动上板对比，你永远分不清是 loader 写弱还是你自己的读弱。

## 解法：别让 loader 写 rootfs，改由 Linux 落盘

绕了一大圈，结论收敛到一句：既然是 loader 写我们这份 rootfs 写弱，那就**别让 loader 写 rootfs**，改由 Linux 自己落盘。Linux 是可靠写者（读了 DLL 调谐、写了 powergood/WPEN，读写都稳），让它来 erase + 重写 rootfs 数据块，loader 只负责搬运。

具体落地是首启 initramfs 里跑一个 **ubiprog**：第一次 boot，[`/init`](../../../board/aes/initramfs/init) 发现没有置备 marker，就用 Linux 把 mtd5 的 rootfs 数据块擦了重写一遍，绕开 loader 的弱写，然后设上 marker；之后每次 boot 检到 marker 就跳过，直接 switch_root。

但这里又冒出一个细节——PEB 3/4 是 loader 已经写弱的，整块读不可纠。如果 ubiprog 笨乎乎地整块读→整块写，会把 PEB 头部的 master 节点也一起读废，首启就挂不上。

## ubiprog 的两版：从"容忍"到"修干净"

第一版 ubiprog 是"整块读不可纠就跳过、留原样、赌 UBIFS 容忍"。这个版本其实 boot 通了、`/persist.log` 跨冷重启也存活（[boot-sdl-202606162243](../../logs/boot-sdl-202606162243.txt)），但它是"容忍"不是"修干净"——dmesg 里那批 -74 还在，只是 UBIFS 容忍掉了；真要哪次重烧把 master 页也写废，页级恢复就 0xFF 不出来，首启照样挂。

正解是**页级恢复**：对全块读不可纠的块，不整块跳过，而是逐页读（writesize 2KB），能纠的页（含 PEB 头部的 master 节点）保留、不可纠的页填 `0xFF`，然后再擦、Linux 重写整块。[boot-sdl-202606162310](../../logs/boot-sdl-202606162310.txt) 是页级恢复版的现场：

```
peb=3 full-read uncorrectable → page recovery (3/64 pages unreadable → 0xFF, rest kept)
peb=4 full-read uncorrectable → page recovery (3/64 pages unreadable → 0xFF, rest kept)
ubiprog done: rewrote=65 recovered(page-level)=2 skipped(erased)=1325 failed=0
```

PEB 3/4 各 64 页，只有 3 页不可纠（填 0xFF），其余 61 页含 master 节点都保住了。改完之后，RW 才算真正稳。

## 几颗伪装弹，点到为止

saga 主线之外还有几颗会伪装成"写损坏"把你带沟里的雷，这里点到、细节都在 pitfalls/04：`bootm` 把 kernel FIT 暂存到 `0x02080000`（kernel load 地址）会自覆盖，得暂存到 `0x04000000`；`mtd read` 读太短会截断 FIT、sha256 fail，长得跟读 corrupt 一模一样；内核太大（11.5MB gzip）会踩过出厂坏块 `0x920000`，解法是换 XZ 压缩压到 7.1MB，不是砍代码。还有一颗更阴的——写到一半板子 external abort，看着活脱脱 SFC 写路径的锅，真因却是 DT 没给 OP-TEE 留 reserved-memory，详见 [pitfalls/05](../../pitfalls/05-secure-mem-reservation-imprecise-abort.md)。

## 这场 saga 教会我们什么

整场 saga 最值钱的一句，不是某个具体修法，而是那句方法学：**别只换 rkbin 黑盒、用 A/B 把变量拆开**。这跟 [pitfalls/01](../../pitfalls/01-rkbin-spl-contracts.md) 恰好形成对照——那一篇是"rkbin SPL 定的契约，我们老老实实对齐"（合理的让步），这一篇是"别把所有问题都归给 rkbin 黑盒、用实验隔离变量"（方法学）。两篇合起来，才是跟 rkbin 这层闭源打交道的完整姿态。

## 成功长这样

RW 真正稳了，跨冷重启 UBIFS 能 replay，`/persist.log` 在 [boot-sdl-202606162254](../../logs/boot-sdl-202606162254.txt) 里三轮 stress 全在：

```
UBIFS (ubi0:0): recovery needed
UBIFS (ubi0:0): recovery completed
UBIFS (ubi0:0): UBIFS: mounted UBI device 0, volume 0, name "rootfs"
```

冷重启三次，日志里 `c1-19.12`、`c2-300.87`、`c3-52.82` 三个时间戳一个字没丢——写下去的东西，跨冷重启，真在。而走到全链的 [boot-sdl-2026-06211109](../../logs/boot-sdl-2026-06211109.txt)，就是这条路彻底走通的样子：`rk3506 login: root`。

bringup 最难的这关，完结撒花。rootfs 系列到这儿，boot 那个 Ch3 的 panic 彻底消掉，空机器 → 持久 `login:` 的完整闭环，合龙。给板子拍张照，不过分。
