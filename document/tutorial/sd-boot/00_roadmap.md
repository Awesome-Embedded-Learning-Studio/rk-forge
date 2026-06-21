# Ch0 — 路线图：SD 卡，第二条启动路

> boot + rootfs + 外设走完，板子从 SPI-NAND 启动已经完整了——能联网、能插 U 盘、能出声。但 SD 卡是第二条启动媒体，独立的价值：开发刷机不用动板载 NAND、板子砖了能恢复、换卡换系统。这个系列就是把 SD 启动这条路走通。有个和很多板子不一样的现实先说在前面：**这块板的 ROM 只认 RKFW 格式的 SD，裸 dd 出来的镜像它不认。**

## 前言：为什么要单独搞 SD

SPI-NAND 是板子的主启动路径，前面的 boot/rootfs 系列都围绕它。但 NAND 有个先天限制——它在板子上焊死了，刷机要用 Rockchip 的下载工具走 USB，不能像 SD 卡那样拔下来换。SD 这第二条路，给的是"拔卡即换系统""砖了能救"的便利，是开发阶段和恢复场景的刚需。

## 一个反直觉的现实：本板 ROM 只认 RKFW

这是 SD 这条路第一个要认清的事实。我们一开始理所当然地以为，打个裸 `sd.img`、`dd` 进卡、插上就启动——很多板子确实这样。但这块 RK3506B 的 ROM **只认经 Rockchip SD 工具（RKDevTool / SD Firmware Tool）写出的 SD 卡**，裸 dd 的镜像插上"不认"。

证据很直接：vendor 那个 `rk3506b_update_sd.img` 开头魔数是 **`RKFW`**（Rockchip Firmware 统一更新容器），和我们 NAND 的 `update.img`（rkfw-pack.py 产）是同一种格式；而我们的裸 `sd.img` 开头是 protective MBR，RK 工具"打开失败"。所以 SD 这条路的真正交付件是 **RKFW 格式的 `update-sd.img`**，裸 `sd.img` 反而是副产品（给那些能认裸镜像的板子 dd 用，本板用不上）。

## SD 启动协议

SD 怎么启动，不是猜的，是两处独立证据对上的：vendor 的 SD 启动 log 里 SPL 打 `Trying fit image at 0x2000 sector`，主线 U-Boot defconfig 里硬编码 `CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_SECTOR=0x2000`。链是这样：

```
BootROM 读 SD sector 0x40 的 idblock → DDR init + SPL(rkbin)
→ SPL 从 sector 0x2000 读 uboot FIT → OP-TEE → U-Boot
→ U-Boot mmc read sector 0x4000 的 boot.img(kernel FIT) → Linux
→ kernel 挂 ext4 rootfs(mmcblk0p3)
```

注意一个关键点：SD 和 NAND 用**完全相同的 idblock + uboot.img**（rkbin 那套），SD 几乎全复用 NAND 的产物，只换 layout——rootfs 从 UBIFS 换成 ext4、分区表从 NAND 的 parameter 换成 SD 的 GPT。

## 这个系列怎么走

- **Ch1 SD-1：手动引导到 shell**——先验证 SD 启动机制本身。上电进 U-Boot 提示符，手敲三行 `mmc read` 把 kernel 拉起来。这章踩两个坑：U-Boot proper 的 DT 没 mmc 节点（要补 uboot patch 0004）、rootfs 分区 grow 导致 RK 工具不写 rootfs（panic）。
- **Ch2 SD-2：autoboot**——SD-1 要手敲三行太麻烦，SD-2 做成零输入：上电自动跑到 shell。办法是给 U-Boot 加第二份 defconfig（patch 0005），bootcmd 直接是 mmc read 那套，烧进去就不用手敲了。

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

kernel 和 rootfs 全从 SD 卡的 ext4 来，一次按键都不用敲。我们 [Ch1](01_sd1_manual.md) 见。
