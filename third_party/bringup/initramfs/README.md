# initramfs(主线 Linux 交互 shell 用)

最小 initramfs:静态 busybox + /init,塞进 kernel FIT 当 ramdisk 节点。主线 Linux
7.0.12 在 RK3506B 上跑 `/init` 进交互 shell(见 logs/boot-sdl-202606151234.txt,
结尾 `~ #`)。无 rootfs/mmc/nand 依赖,纯 ramdisk。

## 构建 busybox(静态,armhf)

源码用 vendor buildroot 自带的 `busybox-1.36.1.tar.bz2`(无需外部下载):

```bash
ROOT=/home/charliechen/rk-forge
TC=$ROOT/third_party/vendor-sdk/prebuilts/gcc/linux-x86/arm/gcc-arm-10.3-2021.07-x86_64-arm-none-linux-gnueabihf/bin/arm-none-linux-gnueabihf-
mkdir -p /tmp/rk-initramfs && cd /tmp/rk-initramfs
cp $ROOT/third_party/vendor-sdk/buildroot/dl/busybox/busybox-1.36.1.tar.bz2 .
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
