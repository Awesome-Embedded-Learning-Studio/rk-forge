# 04 — SPI-NAND 那场写崩 saga:从"rw 必崩"到 RW 达成,中间还判过一次死

前面几篇坑加起来,都不及这一篇折腾。RK3506B 这块板,boot 链通到 kernel、通到 init、眼看 rootfs 都挂上了,结果一做"写完重启还在不在"——RW 直接必崩,一崩就是好几天。最折磨人的还不是崩本身,是这条 saga 中间产生过一个"rkbin 通病、不可解"的判死结论,我差点就信了、差点转头去拆 rkbin;最后是被一个干净到不能再干净的 A/B 实验推翻的。这篇就是这段 saga 的完整还原,含走过的弯路、含被推翻的结论、含每一步的板上串口证据。

先把舞台搭清楚:RK3506B aes 板,NAND 是 W25N04KV(4Gb、on-die ECC),挂在 SFC@0xff488000(VER_5);软件侧是主线 Linux 7.1 + 主线 U-Boot 2026.07-rc4,而那个甩不掉的 vendor rkbin loader(MiniLoaderAll.bin)负责在 MaskROM 烧录阶段把各分区写进 NAND。整条 RW 的悲剧,就出在"谁往 NAND 里写 rootfs"这件事上。

## 这场 saga 为什么会判错一次

我想先把后面所有误判的根子讲在前面,因为它比单个坑更值钱。saga 一路下来,我的验证方法有个共同的盲区:**全程只换 rkbin 黑盒(loader),从没让 vendor 内核的 fspi 驱动上过板对比;而且每次说"我们的栈写可靠",全是同会话当场回读(mtdbb 写完立刻 cmp),从没跨重启验证过。**

你想想这个盲区会导出什么:症状是"Linux 写 → reboot → 读 = 坏",而我把所有变量都攥在 rkbin 这一环上换(loader 换了三颗),自然就把锅全扣给 rkbin,得出"换 loader 都救不了 = rkbin 通病"。推翻这个结论,最后其实只需要一个把变量拆开的 A/B 实验(后面坑 #6 细讲):同一颗 loader、同一个内核、同一个分区,**只换 rootfs 的内容**,vendor rootfs 跨重启 0 ECC,我们 rootfs 跨重启炸 PEB 3/4。结论一下子翻转——问题压根不在 loader 版本,在 loader 对我们这份 rootfs 的写;解法也不是换 loader,而是干脆不让 loader 写 rootfs。三份旧文档([archive/](../archive/) 里那三个)分别记下了 saga 的三个错误阶段,文末有张演变表。

## 读路径先治:SFC 80MHz 不调谐,采样全是 marginal

故事的起点其实是读,不是写。主线 U-Boot 的 `mtd read`(非 raw)去读 kernel.itb,出来的字节是坏的——FIT magic 第三字节从 `fe` 翻成了 `de`,bootm 当场 `Wrong Image Type`;连着多读几次,还会退化到全 `0xee`(SFC 直接 latch-up)。`mtd read.raw` 更诡异,时好时坏,非确定性。

这种"时好时坏"最折磨人,我一开始是往 NAND 侧怀疑的,而且连换三个方向:先怀疑片内 on-die ECC 把 vendor 软件 ECC 的 page"纠正"错了,hack `spinand_ondie_ecc_prepare_io_req` 总关 ECC,仍 corrupt;再查 continuous read、rdesc_ecc,排除;又试 DMA(走 sfc-no-dma 的 PIO),还是 corrupt。三个方向全否,根因根本不在 NAND 侧。

真正的病根,是主线那两颗 SFC 驱动(linux 的 `spi-rockchip-sfc.c`、uboot 的 `rockchip_sfc.c`)**明明定义了 `SFC_DLL_CTRL0`(0x3C)和 `SCLK_SMP_DLL` bit,却从来不写它**——采样延迟线从没调谐过;而 vendor 同名驱动里有个 `rockchip_sfc_delay_lines_tuning`。80MHz 跑着、采样又不调谐,采样点就落在 marginal 区,bit 翻不翻纯看脸,这就是"时好时坏"的来源。当时的临时缓解是把 DT 里 `spi-max-frequency` 从 80MHz 降到 50MHz(50MHz 以下采样免调谐也稳)——这条"降频缓解"的旧结论后来标了过时,但"读路径真因是 DLL 没调谐"本身是对的。

真根治是把 vendor 的 `rockchip_sfc_delay_lines_tuning()` 移植进两颗主线驱动,DT 恢复 80MHz + `rockchip,max-dll=0x17F`,然后上板扫窗。[boot-sdl-202606160948.txt](../logs/boot-sdl-202606160948.txt) 里这段输出看得我直呼内行:

```
rockchip_sfc: dll tuning target=50000000Hz real=100000000Hz cell_max=383 step=10 cs=0
rockchip_sfc:   dll window [0, 230] (230 cells)
rockchip_sfc: dll ok best=[0,230] -> cell 92
```

扫出 230-cell 的巨大采样窗口,稳得一批,读路径这才算根治。(顺带一提,这日志里 target 50MHz、real 100MHz,是因为 U-Boot 的 `clk_set_rate` 在 RK3506 上是个空操作——这条 100MHz clk bug 是 saga 里独立挂着的一个"暂不修"项,读已经可靠了、不影响 boot,就先放着。)

⚠️ 主线 SFC 驱动的 DLL 调谐必须移植过来(照搬 vendor 的 delay_lines_tuning),不然 80MHz 下采样 marginal,读出来的字节时好时坏,能让你怀疑人生怀疑到 NAND 驱动上去。

## 事情到这里还没完,真正的坑在后面

读稳了,我以为 RW 也该顺理成章了——结果 `echo X > /file && sync && reboot -f`,下次 boot 直接 panic:`ubi0` 报 `ubi_io_read error -74 (ECC error) ... PEB 3:4096`、`PEB 4:4096`、`PEB 30:4096`,retry 三次后 -EBADMSG,`Cannot open root device`,kernel panic。PEB 3/4 跨好几轮重刷都坏,稳得让人绝望。

这一段就是 saga 的核心,我顺着时间线把误判一层层剥给你看。

**第一层误判:Linux 写把数据写坏了。** 这是最自然的归因——`echo > /test.txt`、reboot,看上去就是"Linux commit → erase+rewrite PEB 3/4 → 重启 → 读炸",而且同会话 `echo > /probe.txt;sync;cat` 回读是干净的,数据写路径明明通的,崩的只在元数据 PEB 的 commit 上。证据看似自洽,结论却是错的。

**第二层:加探针,第一次指向 loader。** 我在 `spinand_write_page`、`spinand_erase`、winbond 的 `STATUS_ECC_UNCOR` 上加了 dev_info 探针。板上跑下来,所有 WRITE/ERASE 都是 `prog_fail=0`(写都"成功"),但同会话读 PEB 27 却是 `ECC_UNCOR status=0x20`——关键是 **PEB 27 这次 boot 从头到尾没被写过**(PROBE WRITE 全落在 peb=1000+ 的高位 WL 块)。坏数据是 loader 烧进去的存量,这第一次算指对了方向。[boot-sdl-202606161120.txt](../logs/boot-sdl-202606161120.txt) 把这事儿记得很清楚,PROBE WRITE 的 PEB 全在 1000+,PEB 3/4/27/30/32 一次都没出现在写日志里。

**第三层(POSTMORTEM):换 vendor loader 4762d6 就稳。** 既然是 loader 写的存量,那换颗靠谱的 vendor loader 不就行了?当时写下的结论是:我们的 loader(6645685a)写弱,vendor 的(91a663/4762d6)写可靠,read 测试那次 PEB 3/4/5 全干净。这条结论后来被 A/B 实验直接推翻。

**第四层(HANDOFF):rkbin 通病,换版本无效,不可解——saga 最严重的判死。** 我把三颗 loader 全轮了一遍,结果全崩,于是写下"loader 写不可靠是 rkbin 通病,与版本无关",然后据此暂停了这条线、转头去拆 SDK/rkbin。这个判死结论现在看是错的,但它当时看着特别合理,合理到我差点就认了。

判死结论之所以错,根子就是开头讲的那个方法学盲区,展开就是两个具体的盲点:第一,**我只换 rkbin 黑盒 loader,从没让 vendor 内核的 fspi 驱动上过板**,所有"换 loader 验证"本质都是 loader 互换 + 我们自己的主线 SFC 驱动(那会儿还没加 powergood/WPEN)纹丝不动;第二,**"我们的栈写可靠"全是同会话当场回读,从没跨重启验证**,而 saga 的症状恰恰是"Linux 写 → 重启 → 读 = 坏",我拿一个没跨重启验证的前提,去否定一个跨重启才暴露的症状,逻辑上就站不住。

**推翻它,靠的是一个干净到不能再干净的 A/B 实验。** 同一颗 loader(4762d6)、同一个内核(已经加了 powergood/WPEN)、同一个分区(mtd5@39MB),我只换 rootfs 的内容:烧我们自己的 rootfs,boot2 立刻 PEB 3/4/30/32 `error -74` → panic;烧 vendor 的 rootfs,boot2 干干净净 `recovery completed → mounted`,全文 `error -74` 计数为 0。板上对照,我们 rootfs 那份在 [boot-sdl-2026-06162015.txt](../logs/boot-sdl-2026-06162015.txt)(PEB 3/4/30 连环炸):

```
ubi0 warning: ubi_io_read: error -74 (ECC error) while reading 126976 bytes from PEB 3:4096 ... retry
... (retry×3)
ubi0 error: ubi_io_read: error -74 ... PEB 3:4096
VFS: Cannot open root device "ubi0:rootfs" ... error -74
```

vendor rootfs 那份在 [boot-sdl-202606162146-update-nand-OURkernel-VENDORrootfs.txt](../logs/boot-sdl-202606162146-update-nand-OURkernel-VENDORrootfs.txt)(`grep -cE "error -74|ECC error" = 0`):

```
UBIFS (ubi0:0): recovery needed
UBIFS (ubi0:0): recovery completed
UBIFS (ubi0:0): UBIFS: mounted UBI device 0, volume 0, name "rootfs"
```

这一对照,结论彻底钉死:我们内核的读路径没问题(vendor rootfs 在同内核下跨重启干干净净),**是同一颗 loader 写我们这份小 rootfs 时把 PEB 3/4/30/32 写弱了,写 vendor rootfs 时同位置写得稳稳的**。我们这份 4MB 的小 rootfs 把 UBIFS 的 master/journal 集中在了 PEB 3/4/30/32,正好命中 loader 的弱写块;vendor 那份大 rootfs 元数据分散,没踩中。所以不是内核、不是硬件、不是 ECC 配置、更不是 Linux 写坏,**就是 loader 对我们这份 rootfs 的写**。

中间还有个小插曲值得提:powergood 门 + WPEN 这两项(主线 SFC 缺的、vendor 写侧有的两项)我移植过来之后,板上烧 `update-nand-powergood-wpen-fix.img` 实测,PEB 3/4/30/32 **照样炸**([boot-sdl-202606162143-update-nand-powergood-wpen-fix.txt](../logs/boot-sdl-202606162143-update-nand-powergood-wpen-fix.txt),18 处 ECC)。这说明 powergood/WPEN 不是没用——它们是 Linux 自己写可靠的前提——但它们救不了 loader 已经写下去的存量弱页。

⚠️ 别把所有写崩都扣给 rkbin。验证 loader 写弱不弱,要做的是拆开变量的 A/B:同 loader + 同内核 + 同分区,只换 rootfs 内容。只换 rkbin 黑盒、又不让 vendor 驱动上板对比,你永远分不清是 loader 写弱还是你自己的读弱。

## bootm 还顺手埋了两颗小雷:暂存地址和读长度

saga 主线之外,bootm 这边还埋了两颗独立的小雷,得单独说,因为它们会伪装成"写损坏"把你带沟里。

第一颗是 FIT 暂存地址。我手动 `mtd read boot ${kernel_addr_r} 0 0xc00000; bootm`,结果 `ERROR: new format image overwritten - must RESET the board to recover`,板子必须复位。`${kernel_addr_r}` 是 0x02080000,正好是 kernel 的 load 地址;我把 FIT 暂存在这儿,bootm 解 FIT 的时候要把 kernel 节点 load 出来,load 的目的地正好压在 FIT 自己头上,自覆写。改把 FIT 暂存到 `0x04000000` 就没事了。现场在 [boot-sdl-2026-0615955.txt](../logs/boot-sdl-2026-0615955.txt)。

第二颗是 `mtd read` 的长度。当前内核 FIT 有 7.36MB,你要是图省事读个 `0x600000`(6MB),FIT 被截断,bootm 解到一半 sha256 fail,kernel 损坏——而这个 sha256 fail 长得跟 SFC 读 corrupt 一模一样,极易被当成"写损坏 saga"的一部分。正解是读 `0x800000`(8MB)或干脆 `0x1000000`(16MB)读满分区。[BOARD-VALIDATION.md](../../third_party/bringup/nand-rootfs/BOARD-VALIDATION.md) 阶段③ 我把这事儿原样固化进验证手册了。

⚠️ `mtd read boot 0x04000000 0 0x1000000; bootm 0x04000000`——FIT 暂存躲开 kernel load(0x02080000),读长度盖过 FIT 实际大小(7.36MB → 至少 0x800000)。这俩错了会伪装成写损坏,别被骗。

## 另一颗伪装弹:内核太大,踩到出厂坏块

还有一颗伪装弹,跟 loader 写弱一点关系都没有,但 HANDOFF 当年把它俩混为一谈了,得拆开。`mtd read boot` 读到 boot-relative 0x920000(9.2MB)就 `error -74`,我一度以为是 retention 衰减或者物理写毛;后来读 vendor SPL 的坏块扫描日志才看明白,chip 0x2060000(也就是 boot-relative 0x920000)是**出厂坏块**:

```
sfc_nand_check_bad_block page= 40c0 ret= ffffffff spare= ffbf
w: LBA=10300 PBA=10300 is bad block skip0
```

PBA 10300 × 128KiB ≈ 0x920000,loader 老老实实 skip 了它,不是写毛。那为什么 vendor 的 boot.img(6MB)没事、我们的(12MB)踩雷?因为我们的内核太大——`multi_v7_defconfig` 默认砍不下来,我试过砍 DRM/MEDIA/ext4 这些,结果 EXT4/NFS/PERF 被 select 顶住,只省 0.5MB,杯水车薪。正解是不砍代码、换压缩:`multi_v7` + **XZ 压缩**,zImage 从 11.5MB(gzip)压到 7.1MB,稳稳落在出厂坏块 0x920000 之前。坏块证据在 [boot-sdl-202606161244.txt](../logs/boot-sdl-202606161244.txt),之后所有镜像 boot 分区都用 XZ,再没爆过 0x920000。

⚠️ boot 读不全有两个独立原因叠一起:出厂坏块(loader 会 skip,别当写毛)+ 内核太大跨过坏块。解法是 XZ 压缩、不是砍代码——砍不干净的。

## RW 的最终解法:不让 loader 写 rootfs,改由 Linux 落盘

绕了一大圈,结论收敛到一句:既然是 loader 写我们这份 rootfs 写弱,那就**别让 loader 写 rootfs**,改由 Linux 自己落盘。Linux 是可靠写者(读了 DLL 调谐、写了 powergood/WPEN,读写都稳),让它来 erase + 重写 rootfs 数据块,loader 只负责搬运。

具体落地是首启 initramfs 里跑一个 ubiprog:第一次 boot,initramfs 的 `/init` 发现没有置备 marker,就用 Linux 把 mtd5 的 rootfs 数据块擦了重写一遍,绕开 loader 的弱写,然后设上 marker;之后每次 boot 检到 marker 就跳过,直接 switch_root。但这里又冒出一个细节——PEB 3/4 是 loader 已经写弱的,整块读不可纠,如果 ubiprog 笨乎乎地整块读→整块写,会把 PEB 头部的 master 节点也一起读废,首启就挂不上。

第一版 ubiprog 是"整块读不可纠就跳过、留原样、赌 UBIFS 容忍"。这个版本其实 boot 通了、`/persist.log` 跨冷重启也存活,但它是"容忍"不是"修干净":dmesg 里那批 -74 还在,只是 UBIFS 容忍掉了;真要哪次重烧 loader 把 master 页(page0)也写废,页级恢复就 0xFF 不出来,首启照样挂。容忍态的现场在 [boot-sdl-202606162243.txt](../logs/boot-sdl-202606162243.txt):

```
[init] FIRST BOOT: ubiprog rewriting /dev/mtd5 (data blocks only)…
  peb=3 UNCORRECTABLE full-read — left as-is (UBIFS tolerates; master node at PEB head is ECC-recoverable)
  peb=4 UNCORRECTABLE full-read — left as-is ...
ubiprog done: rewrote=65 skipped(erased)=1325 skipped(uncorr,left)=2 failed=0
```

正解是**页级恢复**:对全块读不可纠的块,不整块跳过,而是逐页读(writesize 2KB),能纠的页(含 PEB 头部的 master 节点)保留、不可纠的页填 `0xFF`(对 master 区来说那是未用尾,本就该空),然后再擦、Linux 重写整块。这样 master 页保住了,UBIFS 首启干干净净挂上。[boot-sdl-202606162310.txt](../logs/boot-sdl-202606162310.txt) 是页级恢复版的现场:

```
  peb=3 full-read uncorrectable → page recovery (3/64 pages unreadable → 0xFF, rest kept)
  peb=4 full-read uncorrectable → page recovery (3/64 pages unreadable → 0xFF, rest kept)
ubiprog done: rewrote=65 recovered(page-level)=2 skipped(erased)=1325 failed=0
```

PEB 3/4 各 64 页,只有 3 页不可纠(填 0xFF),其余 61 页含 master 节点都保住了。改完之后,RW 才算真正稳:跨冷重启 UBIFS 能 replay(`recovery needed → recovery completed → mounted`),`/persist.log` 在 [boot-sdl-202606162254.txt](../logs/boot-sdl-202606162254.txt) 里三轮 stress 全在——c1-19.12、c2-300.87、c3-52.82,三次冷重启一个字没丢。

⚠️ 全块读不可纠的 PEB,别整块跳过赌容忍,要逐页恢复:不可纠页填 0xFF,能纠页(尤其 master 节点页)保留,再擦 + 重写。整块跳过是埋雷,master 页一旦哪次被 loader 写废就首启挂不上。

## 三份旧文档,就是 saga 的三个错误阶段

这场 saga 的弯路,原样留在了三份旧文档里,现在都归档在 [archive/](../archive/)、各带了一个 superseded banner。把它们摆成一张演变表,整条 saga 的认知推进就一目了然了:

| 文档 | 写于 | saga 阶段 | 核心结论 | 错在哪 / 被什么取代 |
|---|---|---|---|---|
| [SFC-WRITE-CORRUPTION-POSTMORTEM](../archive/SFC-WRITE-CORRUPTION-POSTMORTEM.md) | 06-16 中午 | 探针定位 loader 存量 | "坏数据是 loader 写的存量"(对)+"换 4762d6 就稳"(错) | "换版本就稳"被 A/B 推翻 |
| [HANDOFF-LOADER-MARGINAL-WRITE](../archive/HANDOFF-LOADER-MARGINAL-WRITE.md) | 06-16 下午 | 最严重判死 | "三颗 loader 全边际,rkbin 通病,与版本无关,不可解" | 两个方法学盲点,被 A/B 推翻 |
| [RW-WRITE-FIX-powergood-wpen](../archive/RW-WRITE-FIX-powergood-wpen.md) | 06-16 晚 | 推翻 HANDOFF | "真根因 = 缺 powergood+WPEN" | 不够(PEB 3/4 仍炸),被"Linux 落盘"收尾 |
| canonical(saga RW-SOLVED) | 06-16 深夜 | 最终态 | rootfs 由 Linux 落盘(ubiprog + 页级恢复),loader 还是同一颗 4762d6 | (当前真相) |

## saga 教训

整场 saga 最值钱的一句,不是某个具体的修法,而是那句方法学:**别只换 rkbin 黑盒、用 A/B 把变量拆开**。判死结论"rkbin 通病不可解"之所以产生,根子是验证盲区——只换 rkbin、从没让 vendor 驱动上板,"我们栈可靠"又全是同会话没跨重启。推翻它只需要一个干净 A/B:同 loader + 同内核 + 同分区,只换 rootfs,vendor rootfs 跨重启 0 ECC、我们 rootfs 炸 PEB 3/4。问题不在 loader 版本,在 loader 对我们这份 rootfs 的写;解法不是换 loader,是不让 loader 写。

这跟篇 01 恰好形成对照:篇 01 是"rkbin SPL 定的契约,我们老老实实对齐"(合理的让步);这一篇是"别把所有问题都归给 rkbin 黑盒、用实验隔离变量"(方法学)。两篇合起来,才是跟 rkbin 这层闭源打交道的完整姿态。还有个未解之谜留着(纯求知、不挡 RW):为什么同一颗 loader 写 vendor rootfs 稳、写我们 rootfs 弱?note12 里列了几个待查方向——loader 写侧的 SFC 配置、我们 rootfs 内容触发的 bit 模式、master 节点的 program-disturb——真要查得拆 rkbin loader 反汇编写初始化,留给以后。

到这里,RW 这条线总算大功告成,可以给板子拍张照了。主线 U-Boot + 主线 kernel + UBIFS rootfs + busybox,整条链子在 RK3506B 真板上 RW 跑通、跨冷重启数据还在,bringup 这程最难的一关,完结撒花。
