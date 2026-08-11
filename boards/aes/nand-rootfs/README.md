# NAND 持久 rootfs(busybox + UBIFS)

把一个最小 busybox rootfs 持久化到 SPI-NAND 的 rootfs 分区,内核用
`root=ubi0:rootfs rootfstype=ubifs` 直接挂为根(**不走 initramfs**)。这是从
"initramfs 交互 shell"到"持久 rootfs boot"的一步,且:

- **不重编内核** —— UBI/UBIFS/SPI-NAND/MTD 全已在 multi_v7_defconfig
  (CONFIG_MTD_UBI=y, UBIFS_FS=y, MTD_SPI_NAND=y, DEVTMPFS_MOUNT=y)。
- **不重编 busybox** —— 复用 initramfs 里已验证的静态 busybox(defconfig,init
  applet 在)。

关键点:当前 boot.img 的 initramfs 带 `/init`,内核看到它就 exec 它(drop shell),
不会去 mount `root=`。所以切真根必须用一个**不带 ramdisk 节点**的 boot FIT
(`boot-nand.img`);原 `boot.img`(带 initramfs)保留作 rescue shell fallback。
DT 的 bootargs 加 `root=` 对两版都安全(有 ramdisk /init 时内核忽略 root=)。

## 构建链(一键)

```bash
cd ~/rk-forge
scripts/mk-rootfs.sh               # out/rootfs/(busybox+86 applet 链接+etc,1.5M)
scripts/pack-ubifs.sh              # out/rootfs.ubi.img(UBI image,3.4M,autoresize)
# (需重编 dtb 时:source scripts/env-setup.sh && scripts/build-linux.sh --just-dtb)
scripts/pack-fit.sh                # out/boot.img(initramfs fallback)+boot-nand.img
scripts/assemble-update.sh --nand  # out/update-nand.img(uboot+boot-nand+rootfs,一把烧)
```

## 产物(third_party/bringup/out/)

| 文件 | 大小 | 用途 |
|---|---|---|
| **update-nand.img** | 17M | RKDevTool 一把烧(uboot + boot-nand + rootfs) |
| rootfs.ubi.img | 3.4M | UBI image,烧 rootfs 分区(mtd5);autoresize 卷 |
| boot-nand.img | 12M | 无 ramdisk 的 boot FIT,kernel 挂 UBIFS 根 |
| boot.img | 13M | 带 initramfs 的 boot FIT(rescue shell fallback) |
| update.img | 14M | 不含 rootfs 的 update(initramfs rescue 变体,默认 assemble) |

## 烧录(Windows RKDevTool)

`update-nand.img` 内含 uboot + boot-nand + rootfs 三分区。RKDevTool 两种模式:

**方式 A:升级固件模式(推荐,一键)**
- 升级固件标签 → 固件选 `update-nand.img`(Loader 选 MiniLoaderAll.bin 或留空)
- 设备进 maskrom → 点"升级"
- 工具自动下载 loader + 解包 update-nand.img 逐分区烧(uboot/boot/rootfs,先擦后写)。
  即"一次烧一个 update.img"。misc/vnvm/recovery/userdata 不动。

**方式 B:下载镜像模式(逐分区,灵活)**
- 下载镜像标签 → 先点"下载"Loader(MiniLoaderAll.bin)使设备进 LOADER(= db)
- 勾选分区行(分区表由 parameter 自动加载),分别指定:
  - uboot → `uboot.img`
  - boot  → `boot-nand.img`
  - rootfs → `rootfs.ubi.img`
- 点"执行"(逐分区先擦后写)。rootfs 行之前没烧过(package-file-aes 省略),首次勾上即可。

> 注:`db`(download bootloader)是下载镜像模式的前置(手动让设备 maskrom→LOADER);
> 升级固件模式不用手动 db,工具内部自动发 loader。别把两者混用。

## U-Boot 引导

boot 分区现在是 boot-nand.img(无 ramdisk)。上电到 U-Boot 交互:

```
=> setenv bootargs 'earlycon=uart8250,mmio32,0xff0a0000 console=ttyS0,1500000 ubi.mtd=5 root=ubi0:rootfs rootfstype=ubifs rootwait'
=> saveenv                       # 持久(可选;不 save 则每次重设)
=> mtd read boot 0x04000000 0 0x1800000
=> bootm 0x04000000
```

> - `mtd read` 的 len `0x1800000` = boot 分区满 24MB(boot-nand ~12MB 居前,
>   bootm 解析 FIT header 自动取大小,多读无害)。0x04000000 是 FIT 暂存地址
>   (避 kernel load 0x02080000 重叠,见 sfc/bootm 笔记)。
> - bootargs 也可不 setenv(让内核用 DT /chosen 自带的 root=),但 U-Boot 若已
>   saveenv 过旧 bootargs 会覆盖 DT —— 显式 setenv 最稳。

## 板上验证清单

```
rk3506b-aes:/# cat /proc/mtd                  # mtd5 = rootfs
rk3506b-aes:/# cat /proc/mounts | grep ubi    # ubi0:rootfs on / type ubifs
rk3506b-aes:/# df -h /
rk3506b-aes:/# echo persist-test > /test.txt && reboot
# (重启后再 cat /test.txt 验证持久化)
```

预期启动序列:kernel banner → `UBI: attaching mtd5` → `UBIFS: mounted UBI
volume rootfs` → busybox init → 提示符 `rk3506b-aes:/#`(注意:不是 initramfs
的 `~ #`)。

## 几何(W25N04KV)

| 参数 | 值 | 说明 |
|---|---|---|
| page(min I/O) | 2048 | W25N04KV 2KB data page(+128B OOB) |
| erase block(PEB) | 128 KiB | 64 pages × 2KB |
| LEB | 124 KiB | PEB − 2×page(EC+VID header 各占一页) |
| rootfs 分区 | 174 MiB | DT partition@2740000 |
| -c(max LEB) | 1400 | < 1425 PEB,留 ~25 给 UBI 磨损均衡/坏块 |

pack-ubifs.sh: `-m 2048 -e 124KiB -c 1400`,ubinize `-p 128KiB`,
`vol_flags=autoresize`(UBI attach 时把唯一 rootfs 卷扩满分区)。

## 风险

- **SPI-NAND 写首次验证**:此前只修过*读* corrupt(50MHz PIO,spi-max-freq
  80→50MHz)。UBIFS 是写密集(日志/磨损均衡/首次 ubiattach 写 VID+EC 头)。读稳
  ≠ 写稳。若 ubiattach 或首次 mount 失败,优先怀疑 SFC 写路径。
  兜底:转 squashfs-on-ubi(只读根,只 UBI 元数据少量写,需开
  CONFIG_MTD_UBI_BLOCK 重编内核)。
- **autoresize**:UBI attach 时把唯一 rootfs 卷扩满分区。主线内核 UBI 支持。
- **fallback**:rootfs 若挂掉,改烧 `boot.img`(带 initramfs)回 rescue shell。
