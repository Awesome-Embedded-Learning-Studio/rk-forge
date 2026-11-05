# Ch3 — UBIFS 与 loader 弱写 saga：bringup 最深的一关

> Ch2 rootfs 挂上、shell 起来了，咱们还别急着庆祝。咱们这章要的是整个 bringup 里最深的一关：“写下去的东西，跨冷重启之后还在”。这个要求听着挺朴素的，做起来一写就崩了、一崩就是好几天，咱们中间还下过一次“rkbin 通病、不可解”的判死定论，差点就信了、差点转头去拆 rkbin。这场拉锯的完整还原见 [pitfalls/04](../../pitfalls/04-sfc-nand-saga.md)，这里咱们走主线、讲方法。

## 前言：为什么“持久 RW”这么难

boot 干的是把链路点亮的活，rootfs 挂上了算是能跑。这章要的却是另一档：咱们写了一个文件，断电凉透、再重新上了电之后，它还原封不动地在。跨冷重启的持久，逼着咱们和 SPI-NAND 的读写可靠性、UBIFS 的一致性，还有那个甩不掉的闭源 loader 写可靠性正面交锋。整场悲剧就出在了谁往 NAND 里写 rootfs 这件事上。

## 头一步治读路径：80MHz 不调谐，采样全是 marginal

咱们这个故事的起点其实是读而不是写。主线那两颗 SFC 驱动（linux 的 `spi-rockchip-sfc.c`、uboot 的 `rockchip_sfc.c`）明明定义了采样延迟线寄存器，却**从来不写它**——采样一直是没调谐过的。而原厂的同名驱动里有个 `rockchip_sfc_delay_lines_tuning`。80MHz 跑着、采样又不调谐的时候，采样点落在了 marginal 区，bit 翻不翻也就纯看脸了，“时好时坏”的毛病就是这么来的。

bringup 那会儿咱们图快，用一行 DT 降频到了 50MHz 当过渡。50MHz 以下的采样窗口大到不调谐也稳，读就干净了，但它是权宜的法子，真正的终局在后面。终局是把原厂的那套 DLL 调谐搬进主线驱动、把读速拿回 80MHz：咱们放到板上扫窗，扫窗的输出就在 [boot-sdl-202606160948](../../logs/boot-sdl-202606160948.txt) 里，咱们看了直呼内行：

```
rockchip_sfc: dll tuning target=50000000Hz real=100000000Hz cell_max=383 step=10 cs=0
rockchip_sfc:   dll window [0, 230] (230 cells)
rockchip_sfc: dll ok best=[0,230] -> cell 92
```

扫出 230-cell 的巨大采样窗口，读路径这才算根治了。所以现在的定型链是 80MHz + DLL 调谐（DT 侧 0003、驱动侧 0002），而不是 50MHz 的降频。后来咱们又试过 100MHz，DLL 扫出的窗口是 `[0,0]`，一个 cell 都不肯给了——80MHz 是这颗 DLL 在这颗 SoC 上能稳的最高档，再往上挑不动了。

## RW 必崩的现场

读稳了，咱们以为 RW 也该顺理成章。结果 `echo X > /file && sync && reboot -f`，下次 boot 就直接 panic 了：`ubi0` 报的是 `error -74 (ECC error) ... PEB 3:4096`、`PEB 4:4096`，retry 了三次后报的是 `-EBADMSG`，再往后报的就是 `Cannot open root device`、kernel panic。PEB 3/4 跨了好几轮重刷都坏，稳得让咱们绝望。

这一段是整场拉锯的核心。咱们顺着时间线把误判一层一层剥开来看。这场拉锯里最值钱的并不是某个修法，真正值钱的是那个**怎么会被判错一次**的方法学。

## 四层误判，一层比一层像真的

**误判的头一层：Linux 写把数据写坏了。** 咱们最自然的一种归因——`echo > /test.txt`、reboot，看上去就是 `Linux commit → erase+rewrite PEB 3/4 → 重启 → 读炸` 的标准剧本，而且同会话写完立刻读是干净的，崩的只在元数据 PEB 的 commit 上。证据看着是自洽的，判断却是错的。

**误判的第二层：加探针，头一次指向了 loader。** 笔者在写路径加了 dev_info 探针，发现所有的 WRITE/ERASE 都 `prog_fail=0`（写都算成了成功），但同会话读 PEB 27 的结果是 ECC 不可纠。要紧的是 PEB 27 这次 boot 从头到尾没被写过，坏数据是 loader 烧进去的存量。方向头一回算是指对了。

**误判的第三层：换原厂 loader 4762d6 就稳了。** 既然是 loader 写的存量，换颗靠谱的原厂 loader 不就行了？当时写下的判断是：咱们的 loader 写弱、原厂的写得可靠。咱们这个判断后来被 A/B 推翻了。

**误判的第四层最严重：认定 rkbin 通病，换什么版本都没用、一概不可解。** 笔者把三颗 loader 全轮了一遍，全崩了，写下的就是“loader 写不可靠是 rkbin 通病，与版本无关”，据此就把 loader 这一线暂停了、转头去拆 rkbin。这个判死的定论现在看是错的，但只错了一半。换 loader 无济于事、病是通病的那个判断，后来的板验站住了。错的是“不可解”，真凶藏在写路径的时序里，咱们后文见。

## 判死为什么错：一个方法学盲区

判死定论的根子，是验证方法里藏着的共同盲区：**全程咱们只换 rkbin 黑盒（loader），从没让原厂内核的 fspi 驱动放到板上跑过对比，而且每次说“咱们这套栈写可靠”，全都是同会话的当场回读，从没做过跨重启的验证**。

咱们想这个盲区会导出什么：症状呈现的是 `Linux 写 → reboot → 读 = 坏`，咱们却把所有变量都攥在 rkbin 这一环上换（loader 换了三颗），自然就把锅全扣给了 rkbin，得出的就是“换 loader 都救不了 = rkbin 通病”。而“咱们这套栈写可靠”的前提，又全是没跨重启的同会话回读。拿的是没跨重启验证过的前提，去否定一个跨重启才暴露的症状，在逻辑上就站不住了。

## 推翻它：一个干净到不能再干净的 A/B

同一颗 loader（4762d6）、同一个内核、同一个分区（mtd5）的条件下，**咱们只换 rootfs 的内容**：烧咱们自己的 rootfs，boot2 立刻报 PEB 3/4/30/32 的 `error -74`，然后就 panic 了（[boot-sdl-2026-06162015](../../logs/boot-sdl-2026-06162015.txt)）。烧原厂的 rootfs，boot2 就干干净净地 `recovery completed → mounted`，全文的 `error -74` 计数为 0（[boot-sdl-202606162146](../../logs/boot-sdl-202606162146-update-nand-OURkernel-VENDORrootfs.txt)）。

咱们把这一对照摆出来，定论就拿到了：咱们内核的读路径没问题（原厂 rootfs 在同内核下跨重启干干净净），**是同一颗 loader 写咱们的小 rootfs 时把 PEB 3/4/30/32 写弱了，写原厂 rootfs 时同位置写得稳稳的**。咱们的 4MB 小 rootfs 把 UBIFS 的 master/journal 集中在了那几个 PEB，正好命中 loader 的弱写块。原厂的大 rootfs 元数据分散、没踩中。所以不是内核、不是硬件，也不是 ECC 配置的问题、更不是 Linux 写坏了。**锅就是 loader 对咱们 rootfs 的写**。

后来咱们上了 trace v2 直接看 NAND 的 status register byte，rootfs PEB3/4 的 `pg=3,5 st=0x20`、`pg=4 st=0x10`，对照的是 W25N04KV datasheet §7.3.1：SR bit[5:4]=`10` 指的就是“>8 flip 不可纠”，mainline 的 `ecc_get_status` 把它正确报成 `STATUS_ECC_UNCOR_ERROR`。loader 写弱这件事从逻辑推断变成了看 SR 真值，板上定死了。

> 咱们别把所有写崩都扣给 rkbin。loader 写弱不弱要怎么验？做法是每次只动一个变量的 A/B：同 loader、同内核、同分区的条件下，只换 rootfs 的内容。只换 rkbin 黑盒、又不让原厂驱动放到板上对比的做法，咱们永远分不清是 loader 写弱还是咱们自己的读弱。

## 解法：别让 loader 写 rootfs，改由 Linux 自己写进 NAND

咱们绕了一大圈，最后的定论收敛到一句：既然是 loader 写咱们的 rootfs 写弱，那咱们就**别让 loader 写 rootfs**，写入的活改由 Linux 自己干。Linux 是可靠写者（读了 DLL 调谐、写了 powergood/WPEN、读写都稳），由它来 erase + 重写 rootfs 的数据块，loader 只干搬运的活。

具体的落地是首启 initramfs 里跑一个 **ubiprog**：头一次 boot 的时候，[`/init`](../../../boards/aes/initramfs/init) 会发现没有置备的 marker，咱们就用 Linux 把 mtd5 的 rootfs 数据块擦了重写一遍，绕开 loader 的弱写、然后设上 marker。之后的每次 boot 检到 marker 就跳过重写，直接就 switch_root 了。

但这里又冒出了一个细节——PEB 3/4 是 loader 已经写弱的，整块读是不可纠的。如果咱们让 ubiprog 笨乎乎地整块读了再整块写，会把 PEB 头部的 master 节点也一起读废，首启也就挂了。

## ubiprog 的两版：从“容忍”到“修干净”

第一版 ubiprog 的做法是“整块读不可纠就跳过”，留了原样、赌 UBIFS 容忍。这一版咱们其实 boot 通了、`/persist.log` 跨冷重启也存活（[boot-sdl-202606162243](../../logs/boot-sdl-202606162243.txt)），但这一版干的事是“容忍”，离修干净还差着关键的一步——dmesg 里的那批 -74 还在，只是 UBIFS 容忍掉了。万一哪次重烧把 master 页也写废了，页级恢复就变不出 0xFF 了，首启就照样挂掉了。

真正的正解是**页级恢复**：咱们对全块读不可纠的块不再整块跳过，而是逐页读（writesize 2KB），能纠的页（含 PEB 头部的 master 节点）保留、不可纠的页填 `0xFF`，然后 Linux 再擦了重写整块。页级恢复版的现场就是 [boot-sdl-202606162310](../../logs/boot-sdl-202606162310.txt)：

```
peb=3 full-read uncorrectable → page recovery (3/64 pages unreadable → 0xFF, rest kept)
peb=4 full-read uncorrectable → page recovery (3/64 pages unreadable → 0xFF, rest kept)
ubiprog done: rewrote=65 recovered(page-level)=2 skipped(erased)=1325 failed=0
```

PEB 3/4 的各 64 页里，只有 3 页是不可纠的（填 `0xFF`），其余 61 页含 master 节点都保住了。咱们改完了之后，RW 这才算真正稳了。

## 插曲：一颗伪装成 SFC 的 abort

咱们以为拉锯走到这儿、剩下的不过是几颗小雷扫扫尾。结果有颗 abort 把咱们带进了第二轮弯路，咱们专门把它拎出来写一段，因为它伪装得太像 SFC 写路径的锅了。

RW 收得差不多的那天晚上，板子突然报了 `imprecise external abort (0xc06)`，断点都落在 `arm_copy_from_user` 读 dd 的 user buffer 那一行，触发的 workload 是 `dd` 写 UBIFS rootfs 压测。看着像极了“SFC 写路径在压力下数据写错，abort 冒泡到用户态”——而彼时咱们刚把 SFC 这摊折腾完，第一反应自然是把锅扣回了 SFC。

第一轮的归因更激进：fault 落在了用户 RAM 上，头号嫌疑就是 DDR 的缺陷，咱们跑去跑 stressapptest。结果被一句“原厂 SDK 爆炸写都没事”给否决了。同样的 DDR 芯片、同样的 DDR blob、同一块板，凭啥咱们这栈就炸。第二轮又转回了 SFC，发现咱们用的 `rockchip,sfc-no-dma`（forced PIO）、原厂用 DMA，假设就变成了 PIO 喂不动 FIFO。两轮下来都挺合理、但两轮都错了。

真正的病根是 DT 里漏了东西，**OP-TEE 的 reserved-memory 压根没留**。RK3506B 这边跑的是 OP-TEE，OP-TEE 的物理位置在 `0x1000`、占用约 `0x60000`（rkbin `RKTRUST/RK3506TOS.ini` `ADDR=0x1000`），DT 漏了 carve-out，内核的 buddy allocator 就把这片当 free RAM 分给了 dd 的 user buffer，访问到 secure 区的那一刻 external abort 就来了。咱们两轮都找错了地方，是因为 imprecise abort（0xc06/async）的 FAR 不可信，它打的是“abort 冒上来时 CPU 正在干的那个地址”，跟真凶总线事务的地址完全不是一回事。按 FAR 找 DDR 当然找不到。

一发判干净是零成本的判别器：咱们把同样的压测换到 tmpfs 上跑（纯 RAM、零 NAND/SFC/UBI），照样 abort 了，fault 类型从 0xc06 变成了同步的 0x008、pte 解出来正好落在 OP-TEE 区的物理 `0x5000`——同源、同根因，只是不同并发负载下的精度不同。这一发直接判了“和 SFC 无关”，把继续 diff 816 行 SFC 驱动的活都省了。真正的线索其实在 boot log 里一行早被忽略的告警：`OF: reserved mem: No reserved-memory node in the DT`——打一开始就待在那儿，两轮排查都从眼前溜过去了。

咱们用 patch 0012 解掉它，根节点补上的是一段对齐原厂的 `reserved-memory`：

```dts
reserved-memory {
    #address-cells = <1>;
    #size-cells = <1>;
    ranges;
    trust@0 { reg = <0x0 0x62000>; };   /* 罩住 OP-TEE [0x1000, 0x61000] */
};
```

咱们补上了之后 tmpfs 100 圈零 abort、flash_stress 50/50 全过，0xc06 和 0x008 一起消失了。没有独立的 SFC 二级问题。这个雷的完整还原见 [pitfalls/05](../../pitfalls/05-secure-mem-reservation-imprecise-abort.md)。值得记的不是“加一段 DT”的动作，值得记的是方法论：imprecise 的 FAR 不能信，要定位就得造出 precise 的复现，比如把 workload 换成 tmpfs 这样的纯 RAM。怀疑到外设头上的时候都拿 tmpfs 压一遍，就能零成本地决定还要不要去 diff 驱动。还有一条要说的：ubiprog 的 loader 弱写拉锯依然独立成立——abort 修了之后，首启照样读出 PEB 3/4 的 chip ECC -74，因为 loader 写弱是 NAND 侧 SR 报的，跟 host RAM 的分配无关，两件事是不挨着的。

## 几颗伪装弹，点到为止

拉锯的主线之外还有几颗会伪装成“写损坏”、把咱们带进沟里的雷，这里咱们点到、细节都在 [pitfalls/04](../../pitfalls/04-sfc-nand-saga.md) 里：`bootm` 把 kernel FIT 暂存到 `0x02080000`（这是 kernel load 的地址）会自覆盖，正确的暂存地址是 `0x04000000`。`mtd read` 读的长度太短会截断 FIT、sha256 fail，跟读 corrupt 的样子一模一样。内核太大（11.5MB gzip）会踩过 boot 分区里那块出厂就标坏的 `0x920000`，咱们的解法是换 XZ 压缩压到 7.1MB、而不是砍代码（这块 PEB 是 loader 老实 skip 的出厂坏块、不是写毛的，咱们别把它跟拉锯混为一谈）。

## 成功长这样

RW 真正稳了，咱们跨冷重启，UBIFS 的 replay 也跑得通，`/persist.log` 在 [boot-sdl-202606162254](../../logs/boot-sdl-202606162254.txt) 里的三轮 stress 全都在：

```
UBIFS (ubi0:0): recovery needed
UBIFS (ubi0:0): recovery completed
UBIFS (ubi0:0): UBIFS: mounted UBI device 0, volume 0, name "rootfs"
```

咱们冷重启三次，日志里的三个时间戳 `c1-19.12`、`c2-300.87`、`c3-52.82` 一个字都没丢——写下去的东西，跨过冷重启还稳稳地在。而走到全链的 [boot-sdl-2026-06211109](../../logs/boot-sdl-2026-06211109.txt)，就是整条路彻底走通的样子：`rk3506 login: root`。

bringup 最难的这一关，到这儿算是翻过去了。rootfs 系列走到了头，boot 那个 Ch3 的 panic 也彻底消掉了，从空机器一路走到了持久的 `login:`，整条链路也就此接通了。咱们给板子拍张照，不过分。

