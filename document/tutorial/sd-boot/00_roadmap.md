# Ch0 — 路线图：SD 卡，第二条启动路

> boot + rootfs + 外设都走完，板子从 SPI-NAND 启动已经完整——能联网、能插 U 盘、能出声。SD 这条路是给开发阶段和救板用的：刷机不用动板载 NAND，板子砖了能恢复，换卡换系统。这个系列把 SD 启动走通。但有个反直觉的事实先说在前面，**这块板的 ROM 只认 RKFW 格式的 SD，裸 dd 出来的镜像它不认**——后面我们会专门花一节讲为什么。

## 为什么要单独搞 SD

SPI-NAND 是主启动路径，前面的 boot / rootfs 系列都围着它转，而 NAND 有个先天限制是焊死在板上的，刷机得用 Rockchip 的下载工具走 USB，不能像 SD 卡那样拔下来换。SD 这第二条路换的就是"拔卡即换系统""砖了能救"这件事，开发阶段反复刷实验镜像、烧坏了想恢复出厂，都靠它。

但这一卷花的篇幅，不全是把 NAND 那套原样照搬一份换到 SD 上。SD 启动有它自己的协议（BootROM 怎么从卡上找 loader）、自己的 ROM 限制（只认 RKFW）、自己的坑（U-Boot 的 DT 里压根没 mmc 节点、rootfs 分区 grow 会让 RK 工具静默不写）。下面这几节按出现顺序交代。

## 一个反直觉的现实：本板 ROM 只认 RKFW

SD 这条路第一个要认清的事实，就是我们一开始理所当然地以为打个裸 `sd.img`、`dd` 进卡、插上就能启动——很多板子确实这样。但 RK3506B 这块的 ROM **只认经 Rockchip SD 工具（RKDevTool / SD Firmware Tool）写出的 SD 卡**，裸 dd 出来的镜像插上"不认"，连 BootROM 都不进。

证据很直接。vendor 那个 `rk3506b_update_sd.img` 开头四个字节是 `RKFW`，也就是 Rockchip Firmware 的统一更新容器，跟我们 NAND 那边 `update.img`（`scripts/rkfw-pack.py` 产）是同一种格式；而我们 `pack-sd.sh` 出的裸 `sd.img` 开头是 protective MBR，RK 工具"打开失败"。把 vendor update_sd.img 拆开看（`rkfw-pack.py info`），里面是 parameter（GPT）+ loader + uboot/boot/rootfs 分区镜像，RK 工具拿到这种 RKFW 后，会把它转成可启动 SD：在 sector 0x40 写 idblock，再把各分区镜像按 GPT 摆好位置写下去。

所以 SD 这条路真正交付的不是裸 `sd.img`，而是 RKFW 格式的 `update-sd.img`，由 `forge assemble --sd` 产。裸 `sd.img` 反而是副产品——它能给那些 ROM 能认裸镜像的板子 dd 用，本板用不上。但 `pack-sd.sh` 还是要跑，因为 RKFW 里塞的那份 `rootfs.ext4` 是它产出的。

## SD 启动协议：不是猜的，是两处证据对上的

SD 怎么启动，不是凭感觉。一处证据是 vendor 的 SD 启动 log（`document/logs/vendor_sdcard_log.txt`），板子从 SD 启动时 SPL 打印 `Trying fit image at 0x2000 sector`，也就是从 SD 的 sector 0x2000（4MiB 偏移）读 uboot FIT。另一处是主线 U-Boot 的 defconfig（`evb-rk3506_defconfig`）里硬编码了一行 `CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_SECTOR=0x2000`，这正是 SPL 从 MMC 读 U-Boot 的 sector 地址。两处独立对上，链就是这样的：

```
BootROM 读 SD sector 0x40 的 idblock → DDR init + SPL(rkbin)
→ SPL 从 sector 0x2000 读 uboot FIT → OP-TEE → U-Boot
→ U-Boot mmc read sector 0x4000 的 boot.img(kernel FIT) → Linux
→ kernel 挂 ext4 rootfs(mmcblk0p3)
```

这里有个能省不少事的关键点：SD 和 NAND 用的是**同一份 idblock 和同一份 uboot.img**，都是 rkbin 那套。SD 几乎全复用 NAND 的产物，只换 layout——rootfs 从 UBIFS 换成 ext4、分区表从 NAND 的 parameter 换成 SD 的 GPT。换句话说，SD 这条路我们没动 loader、没动 U-Boot 镜像本身（autoboot 那章加第二份 defconfig 是后面的事），动的只是怎么把这些镜像摆到 SD 卡上、怎么让 kernel 从 ext4 而不是 UBI 挂根。

## layout：boot.img 裸存，rootfs 走 GPT 分区

SD layout（`scripts/pack-sd.sh` 按 `board/aes/parameter-sd-aes.txt` 摆）是这样的：

```
sector    0-33       GPT primary
sector    64 (0x40)  idblock        (raw)
sector    8192 (0x2000)  uboot.img  (raw; SPL 读此)
sector    16384 (0x4000) boot.img   (raw; U-Boot mmc read)
sector    65536 (0x10000) GPT p3 rootfs (ext4 512MiB)
[backup GPT @ tail]
```

这里有一个反常规的设计点值得说，因为它解释了后面 SD-1 为什么是手敲 `mmc read` 而不是 `load mmc`：boot.img 是**裸存**在固定 sector 上的，U-Boot 用 `mmc read` 裸读，跟 NAND 那边 `mtd read` 是同一种哲学。原因是主线 evb-rk3506 那份 defconfig 极简，有 `CONFIG_CMD_MMC`、`CONFIG_CMD_GPT`、`CONFIG_CMD_BOOTM`，但**没有 ext4/FAT/load 这套文件系统命令**——NAND 走 `mtd read` 裸读不需要 FS，主线就把那些命令全省了。所以 U-Boot 看不见 boot 分区里的文件，只能按 sector 偏移硬读；rootfs 那一份 ext4 分区是给 kernel 挂的（`root=/dev/mmcblk0p3`），U-Boot 不需要 ext4 驱动。

## 这个系列怎么走

SD-1 先验证 SD 启动机制本身：上电进 U-Boot 提示符，手敲三行 `mmc read` 把 kernel 拉起来。这一步会撞两个坑。一个是 U-Boot proper 的 DT 里没有 mmc 节点——主线 rk3506.dtsi 是 bring-up 极简版，把 mmc 等外设全 deferred 了，只有 SPL 自带 SD 驱动所以能读 uboot，但 U-Boot proper 走 driver-model，DT 里没节点 dwmmc 驱动就不 probe，板上 `mmc dev 0` 直接报 "No MMC device available"。解法是补一份 [patches/uboot/0004-uboot-dts-mmc-sd-controller.patch](../../../patches/uboot/0004-uboot-dts-mmc-sd-controller.patch)，给 rk3506.dtsi 加 `mmc@ff480000` 节点，驱动匹配 `rockchip,rk3288-dw-mshc` fallback。另一个坑在 rootfs 分区：parameter 里写 `-@0x10000(rootfs:grow)` 用 grow 看着没问题，但 `rkfw-pack.py` 的正则要求 size 是 `0x..` 这种十六进制，grow 的 size 是个裸 `-` 不匹配，于是 rootfs 分区的 `nand_addr` 默认成 `0xFFFFFFFF`，RK 工具拿到这种地址不知道往哪写就静默跳过——只建了空 GPT 分区，kernel 挂 ext4 时 panic `VFS: Unable to mount root fs`。修法是 rootfs 写**固定 512MiB** `0x00100000@0x00010000(rootfs)`，正则匹配上才有正确的偏移。这两坑的细节都在 [Ch1](01_sd1_manual.md) 展开。

SD-2 做成零输入的 autoboot，因为 SD-1 每次上电手敲三行太烦。办法是给 U-Boot 加第二份 defconfig（[patches/uboot/0005-uboot-sd-autoboot-mmc-defconfig.patch](../../../patches/uboot/0005-uboot-sd-autoboot-mmc-defconfig.patch)），`CONFIG_BOOTCOMMAND` 直接就是 `mmc dev 0; mmc read ...; setenv bootargs root=/dev/mmcblk0p3; bootm` 这套，烧进去上电就自动跑到 shell。

## 成功长这样

SD-2 autoboot 的尽头，板子上电零输入就跑到这里——从 [boot-sdl-2026-06211109](../../logs/boot-sdl-2026-06211109.txt) 截的：

```
Hit any key to stop autoboot: 0          ← 没按键
MMC read: dev # 0, block # 16384, count 20480 ... 20480 blocks read: OK
## Loading kernel from FIT Image at 04000000 ...
Starting kernel ...
EXT4-fs (mmcblk0p3): mounted filesystem ... r/w
rk3506 login: root
```

kernel 和 rootfs 全从 SD 卡的 ext4 来，一次按键都不用敲，kernel 起来按 `root=/dev/mmcblk0p3` 直接挂 SD ext4 rootfs，没有 ubi、没有 panic。我们 [Ch1](01_sd1_manual.md) 见。
