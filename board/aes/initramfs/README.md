# initramfs(首启置备 ramdisk)

首启置备 initramfs:静态 busybox + `/init` + `ubiprog`,塞进 kernel FIT 当 ramdisk
节点。首启时 `/init` 用 ubiprog 经内核可靠写路径重写 SPI-NAND rootfs 分区(绕开 rkbin
loader 对部分擦除块的弱写),打 marker 后续启动直接 switch_root 到真正 buildroot
rootfs。详见 `init` 注释 + document/notes/26。

## 生成(真相源 = forge stage)

**不要再手敲。** `scripts/build-initramfs.sh` 是这个 cpio 的唯一生成器,`forge pack`
会作为 `build-initramfs` stage 自动跑(pack-fit 之前)。从 tracked/pinned 源全可复现:

- busybox ← `pins/busybox`(上游 1.36.1 tarball,sha256 锁),用 forge 工具链(gcc 15.2)静态编
- ubiprog ← `board/aes/rootfs/ubiprog.c`(tracked),静态编
- /init  ← `board/aes/initramfs/init`(tracked)

输出 `board/aes/fit/initramfs.cpio.gz`(pack-fit 读这个路径;.gitignore 正确忽略这个
**生成产物**)。单独跑:`bash scripts/build-initramfs.sh`。

下面的手敲食谱是**历史参考**(早先靠 vendor-sdk 的 busybox + ATK gcc 10.3 手搓),
现在被生成器取代——别照它做,它漏了 ubiprog 且依赖 gitignored 的 vendor-sdk。

## 构建 busybox(静态,armhf)——历史参考,勿用

源码用 vendor buildroot 自带的 `busybox-1.36.1.tar.bz2`(无需外部下载):

```bash
ROOT=/home/charliechen/rk-forge
TC=$ROOT/reference/vendor-sdk/prebuilts/gcc/linux-x86/arm/gcc-arm-10.3-2021.07-x86_64-arm-none-linux-gnueabihf/bin/arm-none-linux-gnueabihf-
mkdir -p /tmp/rk-initramfs && cd /tmp/rk-initramfs
cp $ROOT/reference/vendor-sdk/buildroot/dl/busybox/busybox-1.36.1.tar.bz2 .
tar xf busybox-1.36.1.tar.bz2 && cd busybox-1.36.1
make ARCH=arm CROSS_COMPILE=$TC defconfig
sed -i 's/^# CONFIG_STATIC is not set$/CONFIG_STATIC=y/' .config
make ARCH=arm CROSS_COMPILE=$TC -j"$(nproc)"
file busybox   # 应是 ELF 32-bit ARM EABI5, statically linked
```

## 组装 + 打 cpio.gz

```bash
cd /tmp/rk-initramfs
rm -rf rootfs && mkdir -p rootfs/{bin,sbin,proc,sys,dev,etc,usr/bin,usr/sbin,tmp,root}
cp busybox-1.36.1/busybox rootfs/bin/busybox && chmod +x rootfs/bin/busybox
for a in sh mount umount ls cat echo uname mkdir ps dmesg pwd vi; do ln -sf busybox rootfs/bin/$a; done
cp $ROOT/third_party/bringup/initramfs/init rootfs/init && chmod +x rootfs/init
( cd rootfs && find . | cpio -H newc -o | gzip > $ROOT/third_party/bringup/fit/initramfs.cpio.gz )
```

## 进 kernel FIT(ramdisk 节点)

`third_party/bringup/fit/rk3506-kernel.its` 已加 `ramdisk` image 节点
(`data=/incbin/("initramfs.cpio.gz")`, `type=ramdisk`, `compression=gzip`, `load=0x08000000`)
+ conf 引用 `ramdisk = "ramdisk"`。重打:

```bash
(cd $ROOT/third_party/bringup/fit && ../../vendor-sdk/u-boot/tools/mkimage -f rk3506-kernel.its -E -p 0x800 rk3506-kernel.itb)
cp $ROOT/third_party/bringup/fit/rk3506-kernel.itb /mnt/d/DownloadFromInternet/rk3506-kernel.itb
```

## 烧 + 跑

RKDevTool 重烧 **boot 分区** = 新 `rk3506-kernel.itb`(uboot 分区不动)。上电:
```
=> mtd read boot 0x04000000 0 0xc5e000     # 0xc5e000 = 新 FIT 实际大小(含 ramdisk),页对齐
=> setenv bootargs 'earlycon=uart8250,mmio32,0xff0a0000 console=ttyS0,1500000'
=> bootm 0x04000000
```
→ `Run /init` → banner → `~ #` 交互 shell。

## 备注

- 内核需 `CONFIG_BLK_DEV_INITRD=y` + `CONFIG_RD_GZIP=y`(multi_v7_defconfig 默认开)。
- `sh: can't access tty; job control turned off` 无害(无控制 tty);要 job control,/init 里 `setsid -c` 开 console。
- busybox defconfig 出 ~1.4MB 静态 ELF,cpio.gz ~970KB;FIT 总 12.3MiB(>12MiB,故 mtd read 用 0xc5e000 非 0xc00000)。
