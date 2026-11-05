# Ch0 — 路线图：SD 卡，第二条启动路

> boot、rootfs、外设咱们都走完了，从 SPI-NAND 启动的板子已经完整了，联网、U 盘、声音全都齐了。SD 这一路是给开发阶段和救板用的：刷机不用动板载的 NAND，板子砖了能恢复，换卡换系统的活也归它。这个系列咱们把 SD 启动走通。但有个反直觉的事实咱们得摆在前面，**这块板的 ROM 只认 RKFW 格式的 SD，裸 `dd` 出来的镜像它不认**——后面咱们会专门花一节讲为什么。

## 为什么要单独搞 SD

咱们的主启动路径是 SPI-NAND，咱们前面的 boot / rootfs 系列都围着它转，而 NAND 有个天生的限制：芯片是直接焊在板上的，刷机得用 Rockchip 的下载工具走 USB，板载的它拔不下来、也换不了。SD 这第二条路换来的就是“拔卡即换系统”“砖了能救”。开发阶段咱们反复刷实验镜像、烧坏了想恢复出厂，用的都是它。

但这一卷要写的不只是把 NAND 那套照搬到 SD 上。SD 启动有它自己的协议（BootROM 怎么从卡上找 loader）、自己的 ROM 限制（只认 RKFW），还有自己要躲的雷：比如 U-Boot 的 DT 里压根没 mmc 节点，rootfs 分区的 grow 会让 RK 工具静默不写。这几节咱们按出现的顺序来交代。

## 一个反直觉的现实：本板 ROM 只认 RKFW

SD 这一路第一个要认清的事实，就是咱们一开始理所当然地以为，打个裸 `sd.img`、`dd` 进卡、插上就能启动了。其实很多板子也确实这样。但 RK3506B 这块的 ROM **只认经 Rockchip SD 工具（RKDevTool / SD Firmware Tool）写出的 SD 卡**，裸 dd 出来的镜像插上“不认”，连 BootROM 这一关都到不了。

证据咱们直接摆出来。原厂的 `rk3506b_update_sd.img` 开头四个字节是 `RKFW`，也就是 Rockchip Firmware 的统一更新容器，跟咱们 NAND 那边 `update.img`（`scripts/rkfw-pack.py` 产）是同一种格式。而咱们 `pack-sd.sh` 出的裸 `sd.img` 开头是 protective MBR，RK 工具的答复是“打开失败”。拿 `rkfw-pack.py info` 把原厂的 update_sd.img 解开看，里面装的是 parameter（GPT），再加 loader 和 uboot/boot/rootfs 的分区镜像。RK 工具拿到后会把它转成能启动的 SD：在 sector 0x40 的位置写 idblock，再把各分区的镜像按 GPT 摆好位置写下去。

所以 SD 这一路真正交付的是 RKFW 格式的 `update-sd.img`（`forge assemble --sd` 产），裸 `sd.img` 反而是副产品——它能给那些 ROM 能认裸镜像的板子 dd 用，咱们这块板是用不上的。但 `pack-sd.sh` 这一步咱们还是要跑，因为 RKFW 里塞进去的 `rootfs.ext4` 正是它产的。

## SD 启动协议：不是猜的，是两处证据对上的

SD 怎么启动，咱们不凭感觉。一处证据是原厂的 SD 启动 log（`document/logs/vendor_sdcard_log.txt`），板子从 SD 启动的时候 SPL 打印了 `Trying fit image at 0x2000 sector`，意思是从 SD 的 sector 0x2000 读 uboot FIT，那个 sector 也就是 4MiB 偏移的地方。另一处是主线 U-Boot 的 defconfig（`evb-rk3506_defconfig`）里硬编码了一行 `CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_SECTOR=0x2000`，这正是 SPL 从 MMC 读 U-Boot 的 sector 地址。两处独立地对上了，链就是这样的：

```
BootROM 读 SD sector 0x40 的 idblock → DDR init + SPL(rkbin)
→ SPL 从 sector 0x2000 读 uboot FIT → OP-TEE → U-Boot
→ U-Boot mmc read sector 0x4000 的 boot.img(kernel FIT) → Linux
→ kernel 挂 ext4 rootfs(mmcblk0p3)
```

这里有个能省不少事的关键点：SD 和 NAND 用的**idblock 是同一份，uboot.img 也用的同一份**，都是 rkbin 的那套。SD 几乎全复用 NAND 的产物，要换的只有 layout：rootfs 从 UBIFS 换成 ext4，分区表从 NAND 的 parameter 换成 SD 的 GPT。SD 这一路咱们没动 loader、没动 U-Boot 镜像本身（autoboot 那章加第二份 defconfig 是后面的事），动的只是怎么把这些镜像摆到 SD 卡上，怎么让 kernel 从 ext4 而不是 UBI 挂根。

## layout：boot.img 裸存，rootfs 走 GPT 分区

SD 的 layout 咱们让 `scripts/pack-sd.sh` 按 `board/aes/parameter-sd-aes.txt` 来摆，摆出来是这样的：

```
sector    0-33       GPT primary
sector    64 (0x40)  idblock        (raw)
sector    8192 (0x2000)  uboot.img  (raw; SPL 读此)
sector    16384 (0x4000) boot.img   (raw; U-Boot mmc read)
sector    65536 (0x10000) GPT p3 rootfs (ext4 512MiB)
[backup GPT @ tail]
```

这里有一个反常规的设计点值得咱们说一说，因为它解释了后面 SD-1 为什么是手敲 `mmc read` 而不是 `load mmc`：boot.img 是**裸存**在固定 sector 上的，U-Boot 这边用的是 `mmc read` 裸读，跟 NAND 那边的 `mtd read` 是同一种哲学。原因是主线 evb-rk3506 的 defconfig 极简，它留了 `CONFIG_CMD_MMC`、`CONFIG_CMD_GPT`、`CONFIG_CMD_BOOTM` 几条，但是**没有 ext4/FAT/load 这套文件系统命令**。NAND 走的是 `mtd read` 裸读、压根不需要 FS，主线就把那些命令全省了。所以 U-Boot 看不见 boot 分区里的文件，只能按 sector 的偏移硬读。rootfs 的 ext4 分区是给 kernel 挂的（`root=/dev/mmcblk0p3`），U-Boot 压根不需要 ext4 的驱动。

## 这个系列怎么走

SD-1 头一个验证的是 SD 启动机制本身：上电落到 U-Boot 的提示符，咱们手敲三行 `mmc read` 把 kernel 拉起来。这一步咱们会遇上两颗雷。头一颗在 U-Boot proper 的 DT 里没有 mmc 节点。主线 rk3506.dtsi 是 bring-up 的极简版，把 mmc 等外设全 deferred 了，只有 SPL 自带 SD 驱动所以能读 uboot，但 U-Boot proper 走的是 driver-model，DT 里没节点所以 dwmmc 驱动不 probe，咱们在板上敲 `mmc dev 0`，回来的就是 “No MMC device available”。咱们补 [0004](../../../boards/aes/patches/uboot/0004-uboot-dts-mmc-sd-controller.patch) 解掉它：给 rk3506.dtsi 补的节点是 `mmc@ff480000`，驱动匹配的是 `rockchip,rk3288-dw-mshc` fallback。另一颗雷出在 rootfs 的分区上：parameter 里写的 `-@0x10000(rootfs:grow)` 用 grow 看着没问题，但 `rkfw-pack.py` 的正则要求 size 是 `0x..` 这样的十六进制，grow 的 size 是个裸 `-` 不匹配，于是 rootfs 分区的 `nand_addr` 默认成 `0xFFFFFFFF`，RK 工具拿到了却不知道往哪写，索性静默地跳过——只建了空 GPT 分区，kernel 挂 ext4 时给出的 panic 是 `VFS: Unable to mount root fs`。修法是 rootfs 写**固定 512MiB** 的 `0x00100000@0x00010000(rootfs)`，正则匹配上才有正确的偏移。这两颗雷的细节都在 [Ch1](01_sd1_manual.md) 展开。

SD-1 每次上电手敲的都是那三行，咱们是真敲烦了，所以 SD-2 做成零输入的 autoboot。咱们的办法是给 U-Boot 加第二份 defconfig（[0005](../../../boards/aes/patches/uboot/0005-uboot-sd-autoboot-mmc-defconfig.patch)），`CONFIG_BOOTCOMMAND` 直接写的就是 `mmc dev 0; mmc read ...; setenv bootargs root=/dev/mmcblk0p3; bootm` 这一套，烧进卡之后上电就自动跑到了 shell。

## 成功长这样

SD-2 autoboot 的尽头长这样，板子上电零输入就跑到了这儿——咱们从 [boot-sdl-2026-06211109](../../logs/boot-sdl-2026-06211109.txt) 截的：

```
Hit any key to stop autoboot: 0          ← 没按键
MMC read: dev # 0, block # 16384, count 20480 ... 20480 blocks read: OK
## Loading kernel from FIT Image at 04000000 ...
Starting kernel ...
EXT4-fs (mmcblk0p3): mounted filesystem ... r/w
rk3506 login: root
```

kernel 和 rootfs 全从 SD 卡的 ext4 来，咱们一次按键都不用敲，kernel 起来按 `root=/dev/mmcblk0p3` 直接挂的就是 SD 的 ext4 rootfs，ubi 和 panic 全都没了。咱们 [Ch1](01_sd1_manual.md) 见。
