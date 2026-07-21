# 35 — OpenWrt rootfs 怎么造出来,怎么烧进板子

**2026-07-12**。这篇把 OpenWrt rootfs 从源码到上板的整条链路捋一遍。朋友拿到板子能照着复现,也能自己加包。关联 [[34]] [[ubiprog-from-source 根治]]。

## 一句话定位

OpenWrt 自己把 kernel 和 rootfs 都编出来(保住 opkg / kmod / LuCI 那一套),rk-forge 只管 RK 这边的打包——主线 U-Boot 把 kernel 载进去,rkbin loader 写 NAND,fit-pack.py / rkfw-pack.py 把分区凑成 update.img。两条 rootfs 链路:**NAND(UBIFS,带 ubiprog 首启置备)** 和 **SD(ext4,直接挂)**。

## 一键命令

```bash
forge setup  --rootfs=openwrt          # 拉源 + 打 overlay
forge build  --rootfs=openwrt          # 编 OpenWrt(kernel + rootfs + packages)
forge pack   --rootfs=openwrt          # 打 boot.img / rootfs.ubi.img
forge assemble --rootfs=openwrt        # → update.img(NAND)
forge assemble --rootfs=openwrt --sd   # → update-sd.img(SD)
```

懒人版:`forge all --rootfs=openwrt` 一条龙跑前四步。

## 七步链路

按 forge 内部 DAG 的顺序展开,每一步对应一个 stage。

### 1. 拉源 + 打 overlay(setup)

`pins/openwrt` 钉着 `czz8888/rk-3506-openwrt-7.1 @ 31d15c0`。这棵树已经把 rk-forge 的 16 个内核补丁(quilt patches-7.1/)逐字搬过去了,内核侧的活干了一半,所以 rk-forge 这边只补两块 overlay。

`patches/openwrt/0001` 给 `target/linux/rockchip/image/rk3506.mk` 加 `Device/aes_nand`——IMAGES 和 BOOT_FLOW 都留空,跳过 OpenWrt 自己的 rk3506-img 流程,因为我们用 fit-pack.py 打包。

`patches/openwrt/0002` 是 config-7.1 的补丁,补上 czz8888 那棵树漏掉的几样:`ARCH_MESON`(抬 textofs 避开 OP-TEE 的 secure RAM,不然 `Starting kernel...` 就 data abort)、`RD_GZIP`(解 initramfs)、`MTD_OF_PARTS`(出 `/dev/mtd0..6`)、`DEVTMPFS`(ubiprog 要开 `/dev/mtd5`)、`ATAGS`(主线 uboot 用 ATAGS 传 bootargs)。**THUMB2 留 y**——OpenWrt 的 kmod 都是 thumb2 编的,一关掉就 vermagic 错配,板上一堆模块加载失败,这个坑踩过一次。

### 2. 编 OpenWrt(build)

`scripts/build-openwrt.sh`。这里和 buildroot 走两条路:OpenWrt 自建 musl 工具链,不借 rk-forge 那个 glibc 外部工具链。这是有意的——kmod 的 vermagic 绑死在 kernel .config 上,工具链换了就对不上,opkg 装的 kmod 全废。

踩过的坑里三条值得记。第一,`make world -j14` 会把 package/cleanup 和 target/linux/compile 并行跑,稳定挂——拆成分阶段 build,每阶段内部还是 `-j14`,阶段之间走顺序。第二,`source lib/env.sh` 会把 rk-forge 那棵已经打过补丁的 `LINUX_DIR` 喷进环境,OpenWrt 的 `LINUX_DIR ?=` 反而吃了这个值,于是在已经 quilt-apply 过的树上再 apply 一遍 patches-7.1,全炸——`env -u LINUX_DIR` 隔离掉。第三,OpenWrt 的 `cmd()` 在 `-jN` 下有 silent 假失败(kernel 明明编出来了,make 报错),全程 `V=s` 解决。

最终产物在 `build_dir/target-*/linux-rockchip_rk3506/linux-7.1/` 下:`zImage`(7.27MB)、`rk3506b-aes.dtb`,以及 `build_dir/.../root-rockchip/` 这棵 TARGET_DIR——就是 rootfs 本体,musl 的 busybox + procd + kmod 全在里面,kmod 已经躺在 `lib/modules/` 了。

### 3. 暂存 rootfs 树(stage-rootfs)

`stage-rootfs.sh` 按 `ROOTFS_PROFILE` 分流。OpenWrt 这条直接 `rsync TARGET_DIR → out/rootfs/`,不走 tarball 中转——因为 OpenWrt 的 kmod 在 package/install 阶段已经装进 `lib/modules/`,不需要像 buildroot 那样手动拷 `.ko`。顺带塞一份 WiFi 固件(`lib/firmware/rtl8733bu/`)作 fallback,驱动其实是从内置数组加载固件的,板上线不需要,但留着无害。

### 4. 打 UBIFS(pack-ubifs)

`pack-ubifs.sh` 标准 two-step:`mkfs.ubifs`(out/rootfs → rootfs.ubifs,约 9.3MB)+ `ubinize`(裹成 rootfs.ubi.img,autoresize,烧进 mtd5 后 UBI 自己把卷撑满 174MB 分区)。W25N04KV 的几何参数(page 2KB / erase block 128KB / LEB 124KB)写在脚本里,和板上 spi-nand driver 探测的一致。

### 5. 造 provisioning initramfs(build-initramfs)

这一步是 OpenWrt 走 from-source 的关键。静态编 busybox + ubiprog.c + /init,再把 rootfs.ubi.img **gzip 后塞进 cpio**(9.5MB → 3.34MB,压缩率 35%)。这个 ramdisk 会跟 kernel 一起进 boot.img,首启时 /init 把它解出来,ubiprog 拿着这份 RAM 里的确定 image,**擦掉整个 mtd5 再写**,不读 NAND 现有数据。

为什么这么搞?loader 写 rootfs 有时候会留下跨镜像的残留——先烧 buildroot 再烧 OpenWrt,后面那块 NAND 没被覆盖,UBIFS 挂上去就是"新 index + 旧残骸"的混合体,直接挂死。从 RAM 写确定的 image,残留、弱写、page-recovery 三个问题一起解决。详见 [[ubiprog-from-source 根治]]。

这里有个分流:buildroot profile **不**塞这个 image——buildroot rootfs 23MB(glibc),gzip 后 boot.img 会撑爆 16MB 的 boot 分区。buildroot 走的是 ubiprog 的老 read-modify-write 路径,已经板验过。分流逻辑在 `build-initramfs.sh` 里按 `ROOTFS_PROFILE` 切。

### 6. 打 boot FIT(pack-fit)

`pack-fit.sh` 把 OpenWrt 的 zImage + initramfs + aes.dtb 用 fit-pack.py 凑成 FIT(Mode A,vendor SPL 兼容的 `-E` 布局)。同时产一个 `boot-sd.img`,没 ramdisk 的版本,给 SD 用——SD 直接挂 ext4,不需要 provisioning。

### 7. 装进 update.img(assemble)

`assemble-update.sh` + `rkfw-pack.py`。NAND 这条:update.img = loader + parameter(boot 分区 16MB,vendorlayout)+ uboot + boot.img(含 from-source initramfs)+ rootfs.ubi.img。首启链路是 SPL → OP-TEE → 主线 U-Boot → `mtd read boot` → kernel → /init → ubiprog erase+write mtd5 → mount UBIFS → switch_root → OpenWrt shell。

SD 那条:`forge assemble --rootfs=openwrt --sd` 复用 pack-sd,零新代码——out/rootfs 喂给 `mke2fs -d` 产 rootfs.ext4,boot-sd.img 当 kernel,update-sd.img 是个 RKFW(板子 ROM 只认 RKFW,不认裸 dd)。kernel `root=/dev/mmcblk0p3` 挂上 ext4,procd 起来就是 OpenWrt shell。

## rootfs 里有什么,能多大

OpenWrt musl rootfs:busybox + procd + opkg + kmod(`lib/modules/`)+ 你选的包。当前 9.3MB。

加 LuCI、加常用包到 15-18MB 还在 boot 16MB 的内嵌上限里(gzip 35% 反算大约 20MB)。再大就要么扩 boot 分区,要么换 xz 压缩,要么直接上 SD——from-source 在 NAND 上的物理天花板大约 343MB(两份 image + 512MB NAND),500MB+ 的完整发行版只有 SD/eMMC 这一条。

## 加包 / 改 rootfs

入口是 `board/aes/openwrt/aes-nand.config`。想加 LuCI 就加一行 `CONFIG_PACKAGE_luci=y`,想加别的包同理(包名查 `make menuconfig`)。改完跑 `forge build --rootfs=openwrt --reconfigure`(让 OpenWrt 从 seed 重新展开 .config)+ `forge pack` + `forge assemble`,链路自己往下走。

## 还没干的

- fork czz8888 → 工作室 org(`pins/openwrt` 改指 fork,免得依赖个人仓)
- Phase 2 squashfs-on-UBI(OpenWrt 标准 NAND 方案,带 sysupgrade / 恢复出厂)
- buildmeter 加 openwrt parser(build 进度可视化,Phase 1 复用 kind=kernel)
- 逆向 vendor sdk:vendor 那套烧 rootfs 为什么没有弱写问题——下一程的活,单独开

---

关联 [[34-OpenWrt 移植]] [[ubiprog-from-source 根治]] [[sfc-dll-saga]]。
