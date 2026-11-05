# Ch1 — SD-1：手动引导 SD 卡到 shell

> NAND 那边的启动路径咱们已经在板上跑通了，这一章咱们开第二条媒体——SD 卡。SD-1 的目标很窄：把 SD 启动的机制本身跑通，上电进 U-Boot 的提示符，咱们手敲三行 `mmc read` 把 kernel 拉起来，挂上 SD 卡自己的 ext4 rootfs，落到了 shell。这一趟咱们会踩两颗雷，一颗是 U-Boot proper 的设备树压根没 mmc 节点（`mmc dev 0` 报 No MMC device），另一颗是 rootfs 分区写了 `grow` 把 RK 工具搞懵，最后 kernel 也 panic 了。完整的记录在 [notes/32](../../notes/32-2026-06-21-sd-card-image-sd1.md)。

## 交付件是 RKFW，不是裸镜像

Ch0 交代过这板一个别扭的事实：RK3506B 的 BootROM **只认 Rockchip 工具（RKDevTool / SD Firmware Tool）写出来的 SD 卡**，拿 `dd` 裸写的 `sd.img` 插上去，ROM 是不认的。这件事不是咱们瞎猜的——原厂的 `rk3506b_update_sd.img` 解开看，开头四个字节就是 `RKFW` 的魔数，和咱们 NAND 的 `update.img`（rkfw-pack.py 产）**完全同一种容器**。RK 工具吃的就是 RKFW，它把 RKFW 解开、转成 SD 上 ROM 认的布局（idblock 写到 sector 0x40、各分区镜像按 GPT 摆好），裸 `sd.img` 的开头是 protective MBR，RK 工具直接给的答复是“打开失败”。

所以 SD-1 真正的交付件是 `forge assemble --sd` 产出的 `update-sd.img`（RKFW 格式），咱们拿到 Windows 用 RK 工具写进 SD 卡。裸 `sd.img`（[pack-sd.sh](../../../scripts/pack-sd.sh) 产）在咱们这块板是用不上的。但 pack-sd 这一步 forge 还是要跑的，因为 RKFW 里 rootfs 分区装的 ext4 镜像，就是 pack-sd 用 `mke2fs -d` 从 buildroot 树填出来的。pack-sd 产的 `rootfs.ext4`，就是 RKFW 的上游原料。

## 启动协议：从两条独立证据对出来的

SD 的启动链看上去和 NAND 的差不多，idblock、SPL、U-Boot、kernel、rootfs 的接力顺序都一样，但 kernel FIT 放在 SD 卡的哪个 sector、U-Boot 怎么读到它，这事咱们不能瞎猜。咱们是从两处独立证据对出来的：一处是原厂 SD 启动 log（[vendor_sdcard_log](../../logs/vendor_sdcard_log.txt)）里 SPL 打印的 `Trying fit image at 0x2000 sector`，它从 SD 的 sector 0x2000 读 uboot FIT，也就是 4 MiB 偏移的地方。另一处是主线 U-Boot defconfig 里硬编码的那行 `CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_SECTOR=0x2000`。两处相互对上了，protocol 才算落定：BootROM 读 sector 0x40 的 idblock（DDR init + SPL），SPL 从 sector 0x2000 的位置读 uboot FIT，U-Boot 再用 `mmc read` 把 kernel FIT 裸读进了内存，读的正是 sector 0x4000 上的 boot-sd.img。

这里有个设计上的取舍咱们要交代清楚。evb-rk3506 的 defconfig 极简，它留下的是 `CONFIG_CMD_MMC` + `CONFIG_CMD_GPT` + `CONFIG_CMD_BOOTM`，但是**没有 ext4/FAT/load 这一套通用命令**，因为 NAND 走的 `mtd read` 是裸读、根本不需要文件系统。所以 kernel FIT 也是裸存于固定 sector 的，U-Boot 用 `mmc read` 裸读（和 NAND 的 `mtd read` 同一种哲学），而 ext4 rootfs 是 GPT 分区、由 **kernel** 自己挂（`root=/dev/mmcblk0p3`），U-Boot 全程也就不需要 ext4 的驱动。这套设计让咱们 SD-1 连一行 U-Boot 代码都不用动。

## 翻车一：`mmc dev 0` 报 No MMC device

镜像写好了、上电，DDR、SPL、verified-boot 都过了，主线 U-Boot 2026.07 一路跑到了 `=>` 提示符，机制是全通的。咱们一敲 `mmc dev 0`，U-Boot 回笔者的就是 `No MMC device available`，U-Boot proper 是看不到 SD 卡的。

根因要回到主线 U-Boot 的 rk3506.dtsi。咱们在 [boot/03](../boot/03_kernel.md) 里说过同一件事的内核版，主线对 RK3506 是有驱动的骨架、缺的是设备树。U-Boot 这边也是同样的毛病，patch 0001 的 bring-up dtsi 是极简版，**把 mmc 等外设全 deferred 了**，只留下了 console 和 SFC，`mmc@ff480000` 节点是根本不存在的。这里有个反直觉的点咱们容易绕进去：SPL 明明是能从 SD 读 uboot 的，怎么到了 proper 反而看不到卡？因为 SPL 自带一份精简的 SD 读驱动（够它把 uboot FIT 拽出来就行），而 U-Boot proper 走 driver model（DM），DT 里没节点所以 `dwmmc_rockchip` 驱动不 probe，自然也就没 MMC 设备了。SPL 和 proper 是两套不同的路径。

咱们修它靠的是 uboot patch [0004](../../../boards/aes/patches/uboot/0004-uboot-dts-mmc-sd-controller.patch)，给 dtsi 加的 mmc 节点如下：

```dts
mmc: mmc@ff480000 {
    compatible = "rockchip,rk3506-dw-mshc", "rockchip,rk3288-dw-mshc";
    reg = <0xff480000 0x4000>;
    interrupts = <GIC_SPI 86 IRQ_TYPE_LEVEL_HIGH>;
    clocks = <&cru HCLK_SDMMC>, <&cru CCLK_SRC_SDMMC>;
    clock-names = "biu", "ciu";
    bus-width = <4>;
    cap-sd-highspeed;
    max-frequency = <150000000>;
    fifo-depth = <0x100>;
    resets = <&cru SRST_H_SDMMC>;
    reset-names = "reset";
    status = "disabled";
};
```

compatible 写 `rk3506-dw-mshc` 主线驱动本来是不认的，所以咱们挂了个 `rk3288-dw-mshc` 做 fallback。dwmmc 这套 IP 是兼容的，rk3288 的匹配能把它带起来。板级 `&mmc { broken-cd; status = "okay"; }` 里 `broken-cd` 是关键：它告诉驱动卡肯定在（咱们就是从它启动的），跳过了 GPIO card-detect。板子上卡槽的 CD 脚没接，不加这个的代价，就是驱动会一直等一张永远不来的卡。**pinctrl 是不用加的**，因为 SPL 已经把 SD 的 pad 配好读 uboot 了，U-Boot 继承过来就行了。

这颗雷里还藏了个更阴的，差点让咱们白忙一场。dtsi 原来**只 include 了 clock 头、没 include reset 头**，`resets = <&cru SRST_H_SDMMC>` 里那个 `SRST_H_SDMMC` 是个未定义的词、DTC 词法报错。可 `build-uboot` 那个阶段的日志过滤把错误吞了，u-boot.dtb 是压根没重建的，sha256 跟之前的一模一样。笔者看着 sha256 没变还以为改对了，烧上去 `mmc dev 0` 回的仍是 `No MMC device`，笔者回头才反应过来。正解是给 dtsi 顶部补的一行 `#include <dt-bindings/reset/rockchip,rk3506-cru.h>`，DTC 这才真重建了一次，u-boot.dtb 的 sha256 变了、fdtdump 里能看到 mmc 节点的 clocks/resets 都解析对了，这事才算完了。

⚠️ 咱们改完 DT 之后，一定确认 u-boot.dtb 的 sha256 真的变了再往板子上烧，否则烧的就是一个根本没重建的 dtb。

## 翻车二：rootfs panic——grow 分区的锅

mmc 修好了，咱们手敲引导能起 kernel 了，但 kernel 给的 panic 是 `Unable to mount root fs on /dev/mmcblk0p3`，试了 ext3/ext2/ext4/squashfs/vfat... 全都失败。`mmcblk0p3` 分区是在的（GPT 写了、UUID 对、58GB grow），但它上面**是没有任何文件系统的**，RK 工具建了分区、却没把 rootfs.ext4 写进去。

根因在打包的参数里。咱们原来在 `parameter-sd-aes.txt` 里给 rootfs 用的是 `grow`（`-@0x10000(rootfs:grow)`），它的意思是“剩下的扇区都给 rootfs”，听上去是合理的。但 [rkfw_pack.py](../../../src/forge/tools/rkfw_pack.py) 解析分区的正则要求 size 是 `0x..` 这样的十六进制，grow 的 size 字段是个裸 `-`（无 `0x` 前缀），正则是不认的，于是 rootfs 的 `nand_addr` 没设、默认兜底成了 `0xFFFFFFFF`。RK 工具按各分区的 nand_addr 写镜像：uboot/boot 有偏移（0x2000 / 0x4000）就写了，rootfs 拿到的却是 `0xFFFFFFFF`——RK 工具不知道这玩意往哪写、索性跳过了，结果只建了个空 GPT 分区，kernel 自然就挂不上了。

修法是 rootfs 改成固定的 512MB（`0x00100000@0x10000(rootfs)`），正则匹配上了，`nand_addr=0x10000`，RK 工具也就正常地写进了卡里。512MB 对咱们的 buildroot rootfs 绰绰有余（实际只用了 ~9MB），后续咱们真要扩容，在板上跑一下 `resize2fs /dev/mmcblk0p3`、rootfs 就能长满整张卡了。

防再犯咱们做了两手。一手是 rkfw-pack.py 打包时对 `nand_addr=0xFFFFFFFF` 的真实分区打 WARNING，打包期就把它抓了，不让空的分区出货。另一手是 `assemble` 加了 sanity check，rootfs.ext4 的 size 不能超过 rootfs 分区的 size，防的是 `--rootfs-mib` 调大后的静默溢出。两个检查都是便宜的保险，比到时候对着 panic log 倒推强多了。

## 手动引导序列

两颗雷都填完了，咱们手动引导在 U-Boot `=>` 提示符下敲的是这三行：

```
=> mmc dev 0
=> mmc read 0x04000000 0x4000 0x5000     # boot-sd.img @ sector 0x4000
=> setenv bootargs 'console=ttyS0,1500000 root=/dev/mmcblk0p3 rootwait rw'
=> bootm 0x04000000
```

`mmc read 0x4000 0x5000` 是从 sector 0x4000 读出的 0x5000 个 sector（20480 sect = 10 MiB），把 boot-sd.img 完整地覆盖进内存。`0x04000000` 这个暂存点咱们在 [boot/03](../boot/03_kernel.md) 里见过。它是避开 kernel 自加载区的暂存地址，`bootm` 解压时是不会自己覆盖自己的。`root=/dev/mmcblk0p3` 对应的是 RKFW GPT 的三分区，uboot 的 p1 在 @0x2000，boot 的 p2 在 @0x4000，rootfs 的 p3 在 @0x10000。注意 SD 这边用的是 `boot-sd.img`——一份**没有 initramfs** 的 kernel FIT（zImage+dtb），就是为了避免 kernel 起来后的 `/init` 拦截，attach NAND 的 ubi0:rootfs，然后 switch_root 到 NAND 而不是 SD 的岔路。SD 启动要的就是 kernel 直接挂 `mmcblk0p3`，所以 ramdisk 必须拿掉。

## 成功长这样

咱们手敲这三行，kernel 就起来了，挂上了 SD 的 ext4 rootfs，落到了 shell。[boot-sdl-202606211028](../../logs/boot-sdl-202606211028.txt) 就是这一轮的串口 log：

```
EXT4-fs (mmcblk0p3): mounted filesystem ... r/w
VFS: Mounted root (ext4 filesystem) on device 179:3.
Run /sbin/init as init process
```

`mmcblk0p3` 而不是 `ubi0:rootfs`，`ext4` 而不是 `ubifs`——kernel 和 rootfs 都是从 SD 的 ext4 上来的，没有 ubi、panic 也没了。咱们把 SD 的启动机制在板上证实了。

不过每次上电都要手敲这三行，是真的累。下一章咱们把它做成 autoboot，做的是第二份 uboot defconfig、把这套引导序列直接写进 `CONFIG_BOOTCOMMAND`，上电零输入就跑到了 shell。咱们 Ch2 见。
