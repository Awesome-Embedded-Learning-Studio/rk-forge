# Ch1 — 引导启动：主线 7.1 真机首启到 login

> 这一章把 RK3568 ATK 板从 BootROM 一路跑到 busybox 的 `login:`。和 RK3588 那条启动链比，RK3568 的前段简单一截——vendor 的 `rk356x_spl` 没有 RK3588 那个基址错配的 bootloop，不需要切主线 SPL，所以咱们这章不花篇幅在「让 BL31 进场」上，而是把力气花在 eMMC 启动这条路的几个板级细节上。完整记录见 [notes/40](../../notes/40-2026-07-26-rk3568-first-boot-and-next-push.md)。

> 先说清楚范围：这一章讲的是 MVP 首启——用主线自带的 `rk3568-evb1-v10.dtb`（主线 EVB1 的 DT，ATK 板是它的变体）跑通启动链。ATK 板级设备树那八个子系统（PMIC、双 GMAC、audio、触摸、LCD、CAN、RTC、WiFi）的移植是 [下一章](02_peripherals) 的事，本章不碰。

## 启动链长什么样

RK3568 的启动链画出来是这样：

```
BootROM
  → DDR init              ← rkbin 闭源 blob（1560 MHz, 4 GiB）
  → idbloader @0x40       ← binman 自产（主线），不再是 vendor 的 loader
  → SPL                   ← vendor rk356x_spl v1.14（rkbin blob，这条板能用）
  → ATF BL31              ← rkbin v1.46（OP-TEE 省略，无害 warning）
  → U-Boot 2026.07-rc4    ← 主线，evb1-v10 DT
  → bootm FIT             ← kernel + DTB
  → Linux 7.1.0           ← 主线 v7.1，SMP PREEMPT，4 × Cortex-A55
  → mmc1 HS200 eMMC       ← mmcblk1, p1/p2/p3
  → EXT4 → busybox init → login
```

和 RK3506B 比，RK3568 多了 ATF BL31 这一级（ARMv8-A 必需）；和 RK3588 比，RK3568 的 vendor SPL 跟 BL31 没有基址冲突，所以这一级可以继续借 vendor blob，不用像 [RK3588 启动章](../rk3588/01_boot) 那样切主线 SPL。

> 这一章值得记的一个工程进步是 idbloader 由 binman 自产——也就是说 loader 这段不再依赖 vendor 的打包工具，binman 直接从主线 U-Boot 的构建产物 + rkbin 的 DDR/usbplug blob 组出 idblock。这是 RK3568 移植一开始就立起来的「零 vendor 打包工具」基线，后面 RK3588 沿用了同一条路。

eMMC 这条启动路的分区是 GPT 三段：`p1` 放 u-boot、`p2` 是 boot 分区（放 boot.img / FIT）、`p3` 是 rootfs（ext4）。boot.scr 放在 rootfs 分区的 `/boot/` 下——这个位置选择是有讲究的，见下面第一个坑。

## 坑之一：bootflow 找不到 raw FIT，boot.scr 要放 rootfs

U-Boot 默认 `bootcmd=bootflow scan`，让它自己扫启动设备。可 RK3568 的 eMMC boot 分区（p2）是裸 FIT（raw，没有文件系统），bootflow 在一个没有文件系统的分区上找不到入口，就卡住了。

正解是把 boot.scr 放在 rootfs 分区（p3）的 `/boot/` 下。rootfs 是 ext4 有文件系统，U-Boot 的 SCRIPT bootmeth 能命中它、读出 boot.scr、`source` 执行。这相当于把「启动脚本入口」从 boot 分区挪到了 rootfs 分区，绕开 raw FIT 找不到入口的问题。

## 坑之二：FIT 读到 0x02000000 会和 kernel load 撞车

boot.scr 里要把 FIT 从 eMMC 读进内存。第一版的写法是：

```bash
mmc read ${kernel_addr_r} ...    # ${kernel_addr_r} = 0x02000000
```

`bootm` 报：

```
new format image overwritten
```

根因是 FIT 里描述的 kernel load address 也是 `0x02000000`。`bootm` 解 FIT 时要把 kernel 解压/搬到它自己声明的 load address（0x02000000），可咱们恰恰把整个 FIT 读到了 0x02000000——bootm 一搬，就把 FIT 自己覆盖了。

正解是把 FIT 读到不和 kernel/fdt load address 冲突的空闲 DRAM。RK3568 上 kernel load 在 0x02000000、fdt 在 0x12000000，咱们把 FIT 读到 0x08000000（两者之间的空闲区），bootm 再把 kernel 搬到 0x02000000 就不会覆盖 FIT 了：

```bash
mmc read 0x08000000 0x6000 0x20000    # FIT 读到 0x08000000
bootm 0x08000000                       # bootm 从这里解 FIT、把 kernel 搬到 0x02000000
```

> ⚠️ 这种「FIT 暂存地址 ≠ kernel load address」的坑很隐蔽——`bootm` 报的 `new format image overwritten` 不直接说「地址撞了」，得知道 FIT 的 load 机制才看得懂。RK3588 那边也踩了同一个坑、用的同一个 0x08000000 解法，两板独立验证过。

## 坑之三：rootfs 分区装不下，要 resize

首启用的 buildroot rootfs 是 Phase 2a 的全功能栈（Qt6/Mesa/GStreamer 那一套），展开 451 MB。可板配置里的 rootfs 分区只给了 512 MiB（parameter 的 `0x00100000` 扇区），扣掉文件系统开销装不下。

正解是把 rootfs 分区扩到 1 GiB，两处一起改：

```
# board/rk3568-atk/parameter-emmc-atk.txt
0x00100000 → 0x00200000     # rootfs 分区 512 MiB → 1 GiB

# scripts/pack-emmc.sh（RK3568 路径）
ROOTFS_MIB 256 → 1024       # ext4 镜像大小
```

## 坑之四：eMMC 是 dev 0，SD 才是 dev 1

U-Boot 里 `mmc dev` 选设备，这个编号容易搞反。RK3568 上 `mmc@fe2b0000`（sdmmc0，SD 卡槽）是 dev 1，`mmc@fe310000`（sdhci，eMMC）是 dev 0——eMMC 是 dev 0，不是 dev 1。咱们中途一度搞反，照着「SD 是 0」的惯性写 `mmc dev 1`，结果读的是 SD 卡不是 eMMC。判据是 `rk3568.dtsi` 里的控制器地址：`sdmmc0 = dwmmc@fe2b0000`、`sdhci = sdhci@fe310000`，U-Boot 的 dev 号按探测顺序给，eMMC（sdhci）先拿到 dev 0。

## 坑之五：bootflow 不扫 eMMC 分区，目前还是手动 boot

上面四个坑过了，板子能在 U-Boot 提示符下手动 boot 到 login——敲这一串就行：

```bash
mmc dev 0
mmc read 0x08000000 0x6000 0x20000
setenv bootargs console=ttyS2,115200 root=/dev/mmcblk1p3 rw rootwait
bootm 0x08000000
```

注意 root 是 `mmcblk1p3`——RK3568 ATK 的 eMMC 在 kernel 里是 `mmcblk1`（RK3588 topeet 是 `mmcblk0`，两板不一样，照搬必踩 `Waiting for root device`）。

可一松手让它 autoboot，它又不动。根因和 RK3588 一样：U-Boot 的 `bootflow scan` 对 eMMC（dev 0）不扫分区，手动 `mmc dev 0` 它认，bootflow 偏不扫。RK3588 那边用 `CONFIG_BOOTCOMMAND` 写死成「直接 `load mmc 0:3 boot.scr; source`」绕开了（见 [RK3588 autoboot 节](../rk3588/01_boot#autoboot-bootflow-不扫-emmc-分区-就绕开它)）；RK3568 这条自动化当时没收尾——上电还得在 U-Boot 里手动敲上面那串。这是已知尾巴，落 `CONFIG_BOOTCOMMAND` 的 patch 是后续。

## 成功长这样

五个坑都过了，update.img 烧 eMMC，上电手动 boot，串口 115200 看到：

```
...（DDR / BL31 / U-Boot banner，115200 干净）
U-Boot 2026.07-rc4-00043 (evb1-v10 DT)
=> mmc dev 0
=> mmc read 0x08000000 0x6000 0x20000
=> setenv bootargs console=ttyS2,115200 root=/dev/mmcblk1p3 rw rootwait
=> bootm 0x08000000
...（Linux 7.1.0 SMP PREEMPT，4 × Cortex-A55）
mmc1: mmcblk1: p1 p2 p3           # eMMC HS200，注意是 mmcblk1
EXT4-fs (mmcblk1p3): mounted ...
...（busybox init）
rk3568 login:                     # 到 login，首启完成
```

这一段从 [notes/40](../../notes/40-2026-07-26-rk3568-first-boot-and-next-push.md) 的真机记录里来的。到这一步，RK3568 主线启动链通了。

> 这里得区分「首启当时」和「交接时」两个状态，别把首启的临时毛病当成 RK3568 的最终能力。首启那天（[notes/40](../../notes/40-2026-07-26-rk3568-first-boot-and-next-push.md)）确实一堆问题：网络只有 lo（`STMMAC_ETH` 编成模块、rootfs 没装没 modprobe）、Qt6 没进 rootfs（tar 还是 Qt5 时期）、LCD 不亮（evb1-v10 DT 用 `raydium,rm67200`，ATK 屏要另移植 panel）、GPU/VPU/USB3 deferred probe。可这些都是首启当天的快照——随后一轮大重 build（[notes/41–42](../../notes/)）把绝大多数都修通并板验了：`STMMAC_ETH` 等改 `=y` 后 eth0/eth1 双口通（2× RTL8211F RGMII）、ATK panel 驱动移植后 LCD 点亮（`card0-DSI-1 connected`）、Panfrost Mali-G52 起来（card1）、Goodix GT928 触摸、CAN1、RTC pcf8563 全部板上验证通过。到交接时（[notes/42](../../notes/42-2026-07-26-rk3568-mainline-handoff-rtl8852bs-next.md)）真正没收尾的只剩两个：音频 RK809（hp-det GPIO 抢了 i2s1 mclk、声卡没 probe，只有 BT SCO）和 WiFi rtl8852bs（SDIO 总线通、主线无驱动，待搬 vendor 851 文件驱动）。这些后续移植的板级 DT 当前还是 working-tree delta，等 patch 化（P4）落定后课程化成 [下一章](02_peripherals) 及之后的章节。
