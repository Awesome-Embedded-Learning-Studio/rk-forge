# Ch1 — SD-1：手动引导 SD 卡到 shell

> SD 系列第一章，先把 SD 启动的机制本身跑通：上电进 U-Boot 提示符，手敲三行 `mmc read` 把 kernel 拉起来、挂上 SD 卡的 ext4 rootfs、落到 shell。这章踩两个坑——U-Boot proper 的设备树没 mmc 节点（`mmc dev 0` 报 No MMC device）、rootfs 分区 grow 导致 RK 工具不写 rootfs（kernel panic）。完整记录见 [notes/32](../../notes/32-2026-06-21-sd-card-image-sd1.md)。

## 交付件是 RKFW，不是裸镜像

Ch0 说过，本板 ROM 只认 RKFW。所以 SD-1 的交付件是 `forge assemble --sd` 产出的 `update-sd.img`（RKFW 格式），拿到 Windows 用 RK 工具写进 SD 卡。裸 `sd.img`（[pack-sd.sh](../../../scripts/pack-sd.sh) 产）在本板用不上，但 pack-sd 这步还是要跑——它产 RKFW 要的 `rootfs.ext4`。

## 坑之一：`mmc dev 0` 报 No MMC device

镜像写好、上电，DDR + SPL + verified-boot + 主线 U-Boot 2026.07 一路跑到 `=>` 提示符，机制全通。但一敲 `mmc dev 0`，U-Boot 回我 `No MMC device available`——U-Boot proper 看不到 SD 卡。

根因是主线 U-Boot 的 rk3506.dtsi（patch 0001）是极简 bring-up 版，**把 mmc 等外设全 deferred 了**，只留 console 和 SFC。`mmc@ff480000` 节点根本不存在。SPL 自带 SD 驱动、能从 SD 读 uboot，但 U-Boot proper 走 driver model（DM），DT 没节点，dwmmc_rockchip 驱动就不 probe，自然没 MMC 设备。

修是 uboot patch [0004](../../../patches/uboot/0004-uboot-dts-mmc-sd-controller.patch)：给 rk3506.dtsi 加 `mmc@ff480000` 节点（`rockchip,rk3506-dw-mshc` + `rk3288-dw-mshc` fallback、clocks、reset、bus-width 4、cap-sd-highspeed），板级 `&mmc { broken-cd; status = "okay"; }`——`broken-cd` 告诉它卡肯定在（我们就是从它启动的），跳过 GPIO 卡检测。这里有个隐蔽坑：dtsi 只 include 了 clock 头、没 include reset 头，`SRST_H_SDMMC` 词法错，但 build-uboot 容错把错误滤了、u-boot.dtb 没重建、sha256 没变，让人以为成了——得加 `#include <dt-bindings/reset/rockchip,rk3506-cru.h>` 才真重建。

## 坑之二：rootfs panic——grow 分区的锅

mmc 修好，手敲引导能起 kernel 了，但 kernel panic：`Unable to mount root fs on /dev/mmcblk0p3`，试了 ext3/ext2/ext4/squashfs... 全失败。mmcblk0p3 分区在（GPT 写了、UUID 对），但**上面没有任何文件系统**——RK 工具建了分区、却没把 rootfs.ext4 写进去。

根因在打包参数。我们的 `parameter-sd-aes.txt` 原来 rootfs 用 `grow`（`-@0x10000(rootfs:grow)`），而 [rkfw-pack.py](../../../scripts/rkfw-pack.py) 解析分区的正则要求 size 是 `0x..` 这种；grow 的 size 是个裸 `-`，正则不匹配，于是 rootfs 的 `nand_addr` 没设、默认 `0xFFFFFFFF`。RK 工具按各分区的 nand_addr 写镜像：uboot/boot 有偏移就写了，rootfs 是 `0xFFFFFFFF`（不知道往哪写）就跳过——只建了个空 GPT 分区，kernel 自然挂不上。

修是 rootfs 改固定 512MB（`0x00100000@0x10000(rootfs)`），正则就匹配了。防再犯做了两手：rkfw-pack.py 打包时对 `nand_addr=0xFFFFFFFF` 的真实分区打 WARNING（打包期就抓，不放空分区出货）；assemble 加 sanity check 防 rootfs 溢出分区。

## 手动引导序列

两个坑填完，手动引导是这样的（在 U-Boot `=>` 提示符）：

```
=> mmc dev 0
=> mmc read 0x04000000 0x4000 0x5000     # boot.img @ sector 0x4000
=> setenv bootargs 'console=ttyS0,1500000 root=/dev/mmcblk0p3 rootwait rw'
=> bootm 0x04000000
```

`root=/dev/mmcblk0p3`：RKFW 的 GPT 有 3 分区（uboot=p1、boot=p2、rootfs=p3）。

## 成功长这样

手敲这三行，kernel 起来、挂上 SD 的 ext4 rootfs、落 shell——[boot-sdl-202606211028](../../logs/boot-sdl-202606211028.txt) 就是这一轮：

```
EXT4-fs (mmcblk0p3): mounted filesystem ... r/w
VFS: Mounted root (ext4 filesystem) on device 179:3.
Run /sbin/init as init process
```

kernel 和 rootfs 都从 SD 的 ext4 来，没有 ubi、没有 panic。SD 启动机制板上证实。但每 boot 都要手敲三行，太累——下一章我们做成 autoboot，上电零输入跑到 shell。我们 Ch2 见。
