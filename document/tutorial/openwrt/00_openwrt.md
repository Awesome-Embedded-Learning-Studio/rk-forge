# OpenWrt：给 RK3506 装一套真能 opkg 的发行版

> rootfs 那一卷走完了，buildroot 出的 rootfs 已经能烧进 SPI-NAND、跨冷重启也持久了，还能一路跑进 `login:` 的那一行，连 loader 弱写那场拉锯也画上了句号（见 [rootfs Ch3](../rootfs/03_ubifs_loader_weakwrite.md)）。不过朋友拿到板子之后，要的东西其实超出了“一个 rootfs”，他想要的是“一套发行版”，也就是能在板子上 `opkg install` 现场装包的发行版，能开 LuCI 的网页来配网络，也能像路由器一样随时往系统里加新的 kmod。这样的东西 buildroot 给不了，只有 OpenWrt 给得了。这一篇咱们就把 OpenWrt 作为 `--rootfs=openwrt` profile 移植进 rk-forge，让它和 buildroot 并排成了两条路，NAND 和 SD 两条路都在板子上跑到了 `root@OpenWrt:~#`。

## 前言：buildroot 给得了 rootfs，给不了发行版

咱们得把 buildroot 和 OpenWrt 的差别讲明白，不然读到后面的每个决策都会觉得别扭。buildroot 的思路是**定做一个 rootfs**，你在 defconfig 里勾好要哪些包，它就从源码编一整个根文件系统给你，busybox、glibc 的运行时、init 脚本、FHS 目录，全都编了进去。想加个工具？那就改 defconfig、重编整个 rootfs、重新打包烧录。它走的路线是“出厂前就定好了”，咱们在板子上找不到包管理器，加东西的成本是一次完整重编。

OpenWrt 走的是另一套哲学：**它给你一套能现场生长的发行版**。rootfs 里自带着 `opkg` 包管理器和一整套 kmod 的内核模块体系，等板子跑了起来，`opkg install luci` 就能从软件源把包给装了，`opkg install kmod-usb-storage` 就能现场加载想要的内核模块，省去了重编 rootfs，也免了重新烧录。这样现场装包的能力，是路由器、网关这类产品安身立命的根本，也是 buildroot 的定做思路给不了的。

不过 OpenWrt 的代价也不小，它本身就是一整套的构建系统，要自己编 musl 的工具链、自己下 linux 内核源码打补丁，还得把 rootfs 和包也自己编了。好在咱们 rk-forge 这边，主线 U-Boot、rkbin 的 loader，以及 fit-pack.py、rkfw-pack.py 的脚本，这一整条 RK 专属打包链全都在板子上验过了，所以真正要解的就一个 seam 问题：**怎么让 OpenWrt 编出来的东西，接进 rk-forge 已经验过的打包链**，而不是把 rk-forge 的打包推倒重来。这一篇就是围绕这个 seam 展开的。

## 架构决策：让 OpenWrt 自建 kernel + rootfs，rk-forge 只管打包

头一个决策也是最要紧的决策：OpenWrt 的 kernel 和 rootfs，咱们让谁来编？

最省事的想法是借 rk-forge 已经编好的 kernel，毕竟咱们在 [boot Ch3](../boot/03_kernel.md) 里验过的那块板级设备树、那些补丁都靠得住，OpenWrt 只管出个 rootfs 不就完了？这个想法看上去省事，实际上会把 OpenWrt 最值钱的东西废掉：kmod。

底层机制是这样的。OpenWrt 的每个 kmod 包（`.ko`）都带着一段叫 **vermagic** 的版本魔法串，它其实就是“编这个模块时，那个内核 `.config` 的指纹”，内核打开了哪些选项、用的什么工具链、ABI 是 thumb2 还是 ARM，全都哈希进去了。内核加载 `.ko` 的时候，会拿运行内核自己的 vermagic 去比对模块里的，**对不上的就拒绝加载**，这是内核保护自己不被 ABI 不兼容的模块捅穿的一道防线。而 OpenWrt 的 opkg 软件源里那些 kmod 包，vermagic 全都来自 OpenWrt 自己编的那颗 kernel。如果咱们让 kernel 由 rk-forge 编、rootfs 由 OpenWrt 编，两边的 vermagic 就八竿子打不着了，板子上 `opkg install kmod-xxx` 装下来的模块一个都加载不了，kmod 体系也就当场作废了，OpenWrt 便退化成一个没有包管理的 busybox，那还移植它干嘛？

所以咱们把决策定得很清楚，OpenWrt 的文档里管它叫“选项 A”：**kernel 和 rootfs 的编译都交给 OpenWrt**，保住 vermagic 的天然匹配。rk-forge 这边复用它已经验过的主线 U-Boot + rkbin loader + 纯 Python 打包器，负责把 OpenWrt 编出来的东西装进 RK 的 update.img。两边各干自己擅长的事，seam 也就留在了最窄处。

具体谁负责什么，咱们用一张表说清：

| 环节 | 谁干的 | 说明 |
|---|---|---|
| kernel（zImage + aes.dtb） | **OpenWrt** | linux 7.1 + quilt 补丁，和 rk-forge 的内核补丁逐字节一致 |
| rootfs 树（busybox + procd + kmod） | **OpenWrt** | musl 工具链，kmod 已经在 `lib/modules/` 里 |
| U-Boot | **rk-forge** | 主线，板上验过，[build-uboot.sh](../../../scripts/build-uboot.sh) |
| loader（idbloader / MiniLoaderAll） | **rk-forge** | rkbin，[pack-loader.sh](../../../scripts/pack-loader.sh) |
| FIT（boot.img / uboot.img） | **rk-forge** | [fit-pack.py](../../../src/forge/tools/fit_pack.py)，板上验过的加载地址 |
| update.img | **rk-forge** | [rkfw-pack.py](../../../src/forge/tools/rkfw_pack.py) |

这里有个帮咱们省了不少活的意外之喜：OpenWrt 这边 pin 的上游树（[`pins/openwrt`](../../../pins/openwrt) 指向 `czz8888/rk-3506-openwrt-7.1@31d15c0`）已经把 rk-forge 那十六个内核补丁，用 quilt 的 `patches-7.1/series` 逐字节搬过去了。等于说内核侧那十六个补丁的活儿，人家已经干了一半，OpenWrt 构建的时候 quilt 自己会 apply。咱们 rk-forge 这边只需要补两块 overlay 就行：一块告诉 OpenWrt “aes 这块板子长什么样”，另一块补上它 config 里漏的几个开关。

## overlay 只补两块：Device/aes 和 config-7.1

咱们要补的 overlay 有两块，存放的位置就是 [`patches/openwrt/`](../../../boards/aes/patches/openwrt/)，和 linux/uboot 的补丁一个待遇，咱们同样走 `apply-series.sh --component openwrt` 用 `git am` 把它落进 OpenWrt 树。要注意的是，这里 `git am` 的只有 Device 和 config 这点 overlay，**并不包括内核侧的那十六个补丁**，那些是 quilt 在构建时自己 apply 的，咱们别重复打，重复打就冲突了。

第一块 [`0001`](../../../boards/aes/patches/openwrt/0001-openwrt-rk3506-add-aes-nand-device.patch) 干的是给 OpenWrt 注册一块 `Device/aes_nand`。OpenWrt 的 rockchip target 本来有一套自己的 `rk3506-img` BOOT_FLOW，走它自己那套 u-boot idbloader + u-boot.itb 的流程，但咱们压根不用 OpenWrt 的 u-boot，咱们用的是 rk-forge 的主线 U-Boot。所以这个 Device 把 `IMAGES` 和 `BOOT_FLOW` 都留了空，明确跳过 OpenWrt 自己的打包流程：

```makefile
define Device/aes_nand
  $(Device/rk3506)
  DEVICE_VENDOR := AES
  DEVICE_MODEL := RK3506B aes (SPI-NAND)
  DEVICE_DTS := rockchip/rk3506b-aes
  DEVICE_PACKAGES := kmod-usb2 kmod-usb-storage
  # rk-forge 用自己的 fit-pack.py + rkfw-pack.py + 主线 U-Boot 打包，
  # 不要走 OpenWrt 的 rk3506-img BOOT_FLOW（它依赖我们没用的 OpenWrt u-boot）
  IMAGES :=
  BOOT_FLOW :=
endef
TARGET_DEVICES += aes_nand
```

注册了这个 Device 之后，`make defconfig` 才会让咱们在 [`aes-nand.config`](../../../boards/aes/openwrt/aes-nand.config) 里选的 `CONFIG_TARGET_rockchip_rk3506_DEVICE_aes_nand=y` 生效。这块 patch 还有一个写补丁时犯过的错值得提一句：手写 unified diff 的时候，那个 `@@ -55,4 +55,17 @@` 的 hunk header 行数得算对，git-am 是按行数读的，算错了一行，它就把 `TARGET_DEVICES += aes_nand` 那行默默截掉了，device 也进不了 `.targetinfo`，defconfig 选了等于没选。这样的 silent fail 毫无提示，咱们当年 debug 了半天。后来老实地用 `git format-patch` 让 git 自己算行数，就再没出过事了。

第二块 [`0002`](../../../boards/aes/patches/openwrt/0002-openwrt-rk3506-config-essentials.patch) 补的是 config。czz8888 那棵树原本是给 HZHY MiniEVM 配的，咱们 aes 板在 rk-forge 主线 U-Boot 下还需要几个开关，这块 patch 补的就是这些漏掉的开关。咱们逐个说为什么。

头一个咱们要说的是 `CONFIG_ARCH_MESON=y`，它是最反直觉的一个，咱们明明是 Rockchip 的板子，开个 Meson（Amlogic）的 ARCH 干嘛？原因是它有个抬 `TEXT_OFFSET` 的副作用。而 RK3506B 跑着 OP-TEE，OP-TEE 占着物理内存最底下的 secure 区（`0x0` 起一段），如果内核的 zrel 清零区或页表落进了这片 secure RAM，`Starting kernel...` 之后等咱们的就是一个 data abort。开了 `ARCH_MESON`，内核加载偏移抬上去、避开了 secure 区，这个问题就没了。咱们 buildroot 那颗内核也用的同一个 trick。这件事其实和 [rootfs Ch3](../rootfs/03_ubifs_loader_weakwrite.md) 里那颗伪装成 SFC abort 的 reserved-memory 故障是同一片 secure 区的两种表现，一边炸在用户态的 dd 访问、一边炸在内核刚启动，根子都是 OP-TEE 占的那块物理内存没留出来。

然后是一组启动必需的开关：`RD_GZIP` 让内核能解压首启用的 gzip initramfs，`MTD_OF_PARTS` 把设备树里的固定分区实化成 `/dev/mtd0..6`，`DEVTMPFS` 加上 `DEVTMPFS_MOUNT` 的组合让内核自动 populate `/dev`。后面的两个尤其要紧，因为首启置备的 ubiprog 要 `open("/dev/mtd5")`，没有 devtmpfs 它连设备节点都开不了。`ATAGS` 加 `ARM_ATAG_DTB_COMPAT` 则是因为 rk-forge 的主线 U-Boot 用 ATAGS 传 bootargs（parameter 里 `ATAG: 0x00200800`），咱们得让内核兼容着把这些 ATAGS 转发进设备树。

压轴的开关是 `THUMB2_KERNEL`，它是这块补丁里唯一**故意不改**、留在 `y` 的，也是咱们真错过一回才定下的。OpenWrt 的 kmod 包全是 thumb2 编出来的，如果手贱把运行内核的 THUMB2 关成 ARM，vermagic 立刻就对不上了、kmodloader 拒绝加载，板子上就会出现一批加载失败的模块。这个错误在板上日志里抓到了真实现场，[openwrt_done.txt](../../logs/openwrt_done.txt) 这轮 NAND 启动的日志里，kmodloader 报了满屏的 vermagic 错位：

```
crc32c_cryptoapi: version magic '7.1 SMP preempt mod_unload ARMv7 thumb2 p2v8 '
                  should be '7.1 SMP preempt mod_unload ARMv7 p2v8 '
kmodloader: 8 modules could not be probed
```

咱们注意看这两行 vermagic 的差别，模块那边多了个 `thumb2`，而运行内核这边没有。这意味着那一轮镜像的运行内核被编成了 ARM 模式，而 opkg 仓库里的 kmod 还是 thumb2，crc32c、ehci、scsi、usb-storage 就全跪了。系统倒是照样能起来（核心功能不依赖这些 kmod），但 kmod 体系已经形同虚设了。咱们对照着看 [openwrt_sd.txt](../../logs/openwrt_sd.txt) 那轮 SD 启动，kmodloader 老老实实地 `done loading kernel modules`，咱们一个 failed 都没等到，那才是 THUMB2 留 `y` 之后该有的样子。所以咱们在补丁头里把话写死了：**THUMB2 必须留 `y`**，咱们别因为它“看起来和 RK3506 无关”就想当然地关掉省事，一关就是 vermagic 的错配。

## 构建：OpenWrt 自建 musl 工具链，分阶段 build

架构定下来了，咱们进构建。[`scripts/build-openwrt.sh`](../../../scripts/build-openwrt.sh) 是 openwrt profile 的构建脚本，但它干的第一件事就和咱们 buildroot 的老路分道扬镳了：OpenWrt **自己编一套 musl 工具链**，也不借 rk-forge 那个 glibc 的外部工具链。

这又是 vermagic 逼的。kmod 的 vermagic 不光看内核 `.config`，还看编它用的 gcc，工具链换了，vermagic 就跟着变了。rk-forge 的外部工具链是 Arm GNU 15.2，glibc 系的，而 OpenWrt 的 userspace 是 musl 的。要是硬把 glibc 的工具链塞给 OpenWrt，不光 musl 的 userspace 跑不起来，连 kmod 的 vermagic 都会和 opkg 仓库对不上。所以这块是有意的分叉：让 OpenWrt 用它自己的 musl 工具链编 kernel 和 kmod，vermagic 才能和它的 opkg 仓库天然对齐。这和咱们在 [rootfs Ch1](../rootfs/01_buildroot.md) 里 buildroot 借 glibc 外部工具链是相反的选择，但两边的道理都成立，buildroot 那边根本不关心 kmod 的 vermagic（它压根没 kmod 体系），OpenWrt 这边的命根子却就在 kmod 上。

构建这一步咱们犯的错最多，挑三个最值得记的。

第一个是 `make world -j14` 的跨阶段竞态。OpenWrt 的 `make world` 会把 `package/cleanup` 和 `target/linux/compile` 当成两个并行的 make[2] 作业一起跑，结果 `package/cleanup` 在重新生成 `tmp/.packageinfo` 的时候，而 `target/linux` 那边正读着同一份文件，于是它就稳定地挂，报的还是那句不带细节的 `target/linux failed to build`，看着像 flaky 其实是必现的竞态。所以咱们干脆不用 `make world`，改成**分阶段的 build**，每个阶段的内部还是 `-j$(nproc)`，但阶段之间走严格的顺序，按 world 的依赖链 `tools/install → toolchain/install → target/linux/compile → package/compile → package/install → target/linux/install`。这样既保住了阶段内的并行，又避开了跨阶段读写同一个文件。

第二个是关于 `LINUX_DIR` 的环境变量污染，它是这里面最阴的一个。build-openwrt.sh 的开头 `source lib/env.sh`，而 env.sh 里 `export LINUX_DIR` 指向的，是 rk-forge 那棵**已经打过补丁**的 linux 树。偏偏 OpenWrt 的 `include/kernel.mk` 里写的是 `LINUX_DIR ?= $(KERNEL_BUILD_DIR)/linux-$(LINUX_VERSION)`，那个 `?=` 的意思是“没设才设”，环境变量已经设了它就不设了，于是 OpenWrt 拿着 rk-forge 那棵已经 quilt-apply 过的树，再去 apply 一遍它自己的 `patches-7.1/`，两套补丁就叠在了一起，0014/0016 报了一片 reject。咱们干脆在 build 的那行加 `env -u LINUX_DIR`，把设了的环境变量摘掉，让 OpenWrt 自己把 `dl/linux-7.1.tar.gz` 解到它自己的 `build_dir/linux-7.1` 里再打补丁。

咱们碰到的第三个错误是 OpenWrt `cmd()` 的 silent 假失败。OpenWrt 的 makefile 里有个 `cmd()` 宏，默认走的是 `make -s`、还会重定向文件描述符，在 `-jN` 高并发下会把明明编成功的目标误判成失败，kernel 其实编出来了、产物也在，make 却报了 error。咱们的解法是全程 `V=s`，绕开 cmd 的静默逻辑，完整的 verbose 输出落到 per-stage 日志，失败了就 tail 最后 30 行。三个错误都补完了，build 也就稳了。

咱们要的产物在 `build_dir/target-*/linux-rockchip_rk3506/linux-7.1/` 的下面：`zImage`（约 7.27 MB）、`rk3506b-aes.dtb`，还有 `build_dir/.../root-rockchip/` 里的这棵 TARGET_DIR，它就是 rootfs 的本体，musl 的 busybox + procd + kmod 全在里面，kmod 已经躺在 `lib/modules/` 了。后面 rk-forge 的 stage-rootfs 会把这棵树 rsync 到 `out/rootfs/`，和 buildroot 那边解 rootfs.tar 的路在此处分了流。

## 首启置备：从 read-modify-write 升级到 from-source

构建完了，咱们进全篇我觉得最有意思的一段，也就是首启怎么把 rootfs 写进 NAND。它和 [rootfs Ch3](../rootfs/03_ubifs_loader_weakwrite.md) 里那场 loader 弱写拉锯是一脉相承的，建议你把 Ch3 和这一篇对着看。

咱们回忆一下 Ch3 拿到的定论：rkbin loader 写咱们的小 rootfs 的时候，会把其中某些 erase block（PEB 3/4 那几个）写弱了，首启读得出来的东西，断电凉透再启就 ECC 不可纠、UBIFS 挂不上了。Ch3 的解法是首启 initramfs 里跑一个 `ubiprog`，在 loader 写完、数据还新鲜的第一次 boot 时，用 Linux 自己可靠的写路径把这些块重写一遍，绕开 loader 的弱写。那个 ubiprog 用的是 **read-modify-write** 模式，也就是读出每个块、擦掉、再写回去的老流程，遇到整块 ECC 不可纠的就做页级恢复（逐页读，能纠的页保留、不能纠的填 `0xFF`）。

而 OpenWrt 这一路，其实还能比 read-modify-write 更狠一档，咱们管它叫 **from-source**。

咱们这一路的思路是这样的。read-modify-write 不管怎么优化，它的本质还是“从 NAND 读出 loader 写的（可能已经弱的）数据再写回去”，它信任的是 NAND 上的存量。但 OpenWrt 的 rootfs 小（musl，9 MB 的量级），小到可以整个 gzip 之后塞进首启的 initramfs，再跟着 kernel 一起进了 boot.img。这样首启的时候，ubiprog 手里就攥着一份**从 host 打包出来的、确定的** rootfs image（在 RAM 里），它就不需要再信任 NAND 上读出来的任何东西了，把整个 mtd5 里的东西擦干净，从 RAM 里的确定 image 一笔一笔写下去。

[`board/aes/rootfs/ubiprog.c`](../../../boards/aes/rootfs/ubiprog.c) 里的两个模式是靠参数分流的：咱们传一个 image 文件路径就是 from-source，不传的话就是 legacy read-modify-write。from-source 的循环逻辑清晰得像它干的事一样，头一步做的是擦整个分区，image 覆盖到的 PEB 从 RAM 文件读出来写下去，image 之外的尾巴全擦成 `0xFF`：

```c
if (image_file) {
    /* FROM-SOURCE: image 来自 RAM（塞在首启 initramfs 里），绝不回读 NAND。
     * 擦整个分区，再过 kernel 的可靠写路径把 image 写下去；
     * image 之外的 PEB 一律擦成 0xFF。一刀杀掉三种故障：
     *   (1) 跨镜像残留——先烧 buildroot 再烧 OpenWrt，NAND 尾巴里还留着
     *       上一个更大 rootfs 的残骸，UBIFS 挂上去就是"新 index + 旧残骸"
     *       的混合体，recovery 失败、挂死；
     *   (2) loader 的弱写——我们不再信任任何从 NAND 读回的数据；
     *   (3) 页级 0xFF 恢复的 lossy——它会把落在不可纠 PEB 上的 UBIFS
     *       index znode 也填成 0xFF，损坏索引。*/
```

咱们为什么要比 read-modify-write 更狠？因为 OpenWrt 这一路 profile，多了一个 read-modify-write 没有的麻烦，说的就是**跨镜像残留**。OpenWrt 的 rootfs 小（9 MB），buildroot 的 rootfs 大（glibc，23 MB 的块头），buildroot 的那个 UBIFS 带 autoresize，首启就会把 174 MiB 的分区撑满、写满所有 1392 个 PEB。要是头一回烧的是 buildroot、接着再烧 OpenWrt，OpenWrt 覆盖的只是前面几十个 PEB，后面一千多个 PEB 还留着 buildroot 的残骸，UBIFS 下次挂上去读到的就是“新 index 指向的 + 旧残骸”的混合体，recovery 跑不完、直接挂死了。from-source 把整个分区擦干净了再写，残留、弱写、lossy 恢复三个问题就一起解决了。

那 buildroot 为什么不也用 from-source？因为它用不了。buildroot 的 rootfs 有 23 MB，咱们把它 gzip 之后塞进 initramfs，boot.img 就会撑爆 16 MB 的 boot 分区。所以 buildroot 这边还是走 Ch3 那套 read-modify-write（已经在板子上验过），用得起 from-source 的也只有 OpenWrt 那边。这个分流的实现就在 [`scripts/build-initramfs.sh`](../../../scripts/build-initramfs.sh) 里，按 `ROOTFS_PROFILE` 的取值切：

```bash
if [[ "${ROOTFS_PROFILE:-}" == "openwrt" ]]; then
    ROOTFS_UBI="${OUT_DIR}/rootfs.ubi.img"
    log_info "embedding rootfs.ubi.img → rootfs.ubi.img.gz (openwrt from-source)"
    gzip -c "$ROOTFS_UBI" > "$root/rootfs.ubi.img.gz"
else
    log_info "buildroot profile — NOT embedding image (ubiprog read-modify-write)"
fi
```

OpenWrt 这边把 `rootfs.ubi.img` gzip 之后塞进了 cpio（9.5 MB 压到 3.34 MB，压缩率 35% 的水平），buildroot 那边咱们一个字节都不塞，还是走老的 read-modify-write。同一个 ubiprog、同一份首启的 initramfs 脚手架，靠有没有内嵌的 image 自动分流到两条置备路径，这是我觉得整个移植里最干净的一处设计。

## 板验：NAND from-source + SD ext4，两条都通

说了这么多设计，咱们把镜像烧到板子上看真东西。走 NAND 的时候，烧进去首启的那一次，[`/init`](../../../boards/aes/initramfs/init) 发现没有置备的 marker，就调 ubiprog 用 from-source 的方式重写 mtd5。现场就落在 [openwrt_done.txt](../../logs/openwrt_done.txt) 的日志里：

```
[init] FIRST BOOT: ubiprog from-source rewriting /dev/mtd5 (9961472 B)…
ubiprog: FROM-SOURCE /tmp/rootfs.ubi.img (9961472 B); erasing whole partition (1392 PEBs)
  ... 76 img PEBs written + 1316 tail erased
ubiprog done (from-source): wrote=76 erased_tail=1316 failed=0 (of 1392 PEBs; image 9961472 B)
```

`wrote=76 erased_tail=1316` 这一行值得咱们细看：9.5 MB 的 image 只占了 76 个 PEB，剩下 1316 个 PEB 全被擦成了 `0xFF`，这就是 from-source 杀跨镜像残留的现场，buildroot 当年撑满的那一千多个 PEB，一个不留全擦掉了。写完了重新 attach，UBIFS 干干净净挂上了：

```
ubi0: attached mtd5 (name "rootfs", size 174 MiB)
ubi0: good PEBs: 1392, bad PEBs: 0, corrupted PEBs: 0
UBIFS (ubi0:0): UBIFS: mounted UBI device 0, volume 0, name "rootfs"
[init] provisioning complete → switch_root
```

`bad PEBs: 0`、UBIFS 一次 mount 就成功了、没有 recovery。咱们对照 Ch3 那场动不动 `error -74`、recovery 半天、页级恢复的拉锯，这里倒是安静得不像同一个 NAND。switch_root 之后 procd 的三段起来，落进了 OpenWrt 的 shell：

```
procd: - early -
procd: - ubus -
procd: - init -
  _______                     ________        __
 |       |.-----.-----.-----.|  |  |  |.----.|  |_
 |   -   ||  _  |  -__|     ||  |  |  ||   _||   _|
 |_______||   __|_____|__|__||________||__|  |____|
          |__| W I R E L E S S   F R E E D O M
 -----------------------------------------------------
 OpenWrt 24.10-SNAPSHOT, r0-31d15c0
root@OpenWrt:~#
```

到这里 OpenWrt userspace 就起来了，busybox 换成了它自己的 musl 版（`v1.36.1 ... built-in shell (ash)`），buildroot 的那个没有跟过来。NAND 路那轮日志里的那批 vermagic 错位（前面 config 小节里贴过），就是 THUMB2 配错那一轮的现场，它是 openwrt profile 调通过程里咱们真实犯过的错，而不是合成出来的演示。

SD 这一路更值得咱们夸一句，它几乎没写新的代码。`forge assemble --rootfs=openwrt --variant sd` 直接复用 buildroot 那边已经验过的 SD 打包，把 OpenWrt 的 TARGET_DIR 喂给 `mke2fs -d` 出一份 ext4 rootfs，boot-sd.img 当 kernel、组一个 RKFW 的 update-sd.img（本板 ROM 只认 RK-tool 的卡、不认裸 dd）。kernel 拿着 `root=/dev/mmcblk0p3` 的参数挂上 ext4，procd 起来就是 OpenWrt 的 shell，咱们去看 [openwrt_sd.txt](../../logs/openwrt_sd.txt) 的日志：

```
mmcblk0: mmc0:b36a SDABC 58.2 GiB
 mmcblk0: p1 p2 p3
EXT4-fs (mmcblk0p3): mounted filesystem ... r/w with ordered data mode.
VFS: Mounted root (ext4 filesystem) on device 179:3.
VFS: Pivoted into new rootfs
procd: - early -
procd: - init -
kmodloader: done loading kernel modules from /etc/modules.d/*
OpenWrt 24.10-SNAPSHOT, r0-31d15c0
```

SD 这一路的 kmodloader 全程 `done loading`，咱们没等到一个 could not be probed，这就是 THUMB2 留 `y` 之后该有的样子。两条路、两份板上日志都拿到了，“OpenWrt 真的能在 RK3506 上跑起来”，这件事就有了实打实的证据。

## 加包、改 rootfs，还有 WiFi 得说实话

板子跑起来了，OpenWrt 的意义才算发挥出来，说的就是现场加包的能力。加包的入口是 [`board/aes/openwrt/aes-nand.config`](../../../boards/aes/openwrt/aes-nand.config)，它是给 OpenWrt `make defconfig` 用的 seed。咱们想加 LuCI，加一行 `CONFIG_PACKAGE_luci=y` 就够了，想加别的包同理，包名在 OpenWrt 的树里用 `make menuconfig` 查。改完了跑 `forge build --rootfs=openwrt --reconfigure`（那个 `--reconfigure` 会把 OpenWrt 的 `.config` 从 seed 重新展开，别忘了加，否则它还用老的），咱们再跑 `forge pack` + `forge assemble`，链路自己就往下走了。

这里有个 WiFi 的事得如实交代，咱们不能藏着。现在这版 seed 里 `DEVICE_PACKAGES` 只选了 `kmod-usb2 kmod-usb-storage`，**没选 RTL8733BU 的 kmod**，所以在 openwrt profile 上，WiFi 栈目前只走到了 cfg80211 子系统的这一层，芯片驱动级的支持还没进来。板上日志里能看到的 WiFi 相关输出只有这么一行：

```
cfg80211: failed to load regulatory.db
```

它说明的是无线监管数据库没打进 rootfs，这行倒是不挡 boot，但也说明了这一轮镜像里 WiFi 没真正接起来。咱们要真想在 OpenWrt 上用 RTL8733BU，得把它的 kmod 包选进 `aes-nand.config`（OpenWrt 走 kmod 包体系，不走 buildroot 那个 `fetch-rtl8733bu-driver.sh` 的 drop）。WiFi 在 buildroot profile 上是板上 probe 验过的（见 [peripherals Ch3](../peripherals/03_wifi.md)），OpenWrt 这边还是个没做的待办，咱们把话说明白放这儿。

## 还没干的，诚实交代

openwrt profile 还有几样没收尾的活，咱们列在这儿，免得给读者一个“全齐了”的错觉。

头一样的事是源码归属。现在 `pins/openwrt` 还指着 `czz8888` 的个人仓，靠个人仓库做构建总归是不稳妥的。咱们计划 fork 一份到工作室 org（和 `pins/rtl8733bu` 一个模式），fork 出来的是 verbatim 镜像、不做仓内改动，改的只是 `pins/openwrt` 的指向。

第二样是 NAND rootfs 的形态。现在 Phase 1 的是 UBIFS 可写根，直接复用的还是 pack-ubifs，图的是最快跑通。OpenWrt 在 NAND 上的标准方案其实是 **squashfs-on-UBI**，也就是只读的 squashfs 根，加一个可写的 overlay 卷，sysupgrade 的恢复出厂也配上了。那一套得咱们新写一个 `pack-squashfs-ubi.sh`，是 Phase 2 的活。

第三样是 buildmeter 的进度可视化还没加 openwrt parser（[forge Ch](../forge/00_forge.md) 那套构建进度条），现在 OpenWrt 的 build 阶段还是裸输出。Phase 1 能复用 buildmeter 的 kind=kernel 解析，咱们不急。

## 成功长这样

咱们把整条路走通之后，NAND 那一路的首启从 ubiprog 重写 mtd5，到 OpenWrt shell 落地，就是上面贴的那段：`wrote=76 erased_tail=1316 failed=0`，UBIFS 一次就挂上、procd 起来、落进了 `root@OpenWrt:~#`。SD 那一路复用现成的 pack-sd，ext4 挂上、pivot root 也都走完了，同样落进了 OpenWrt shell。

buildroot profile 咱们没动一丝一毫，不加 `--rootfs` 还是走 buildroot 验过的老路。OpenWrt 是和它并排多出来的一条 profile，`forge all --rootfs=openwrt` 一条命令就把源码编到了 update.img。RK3506 上能跑一套真能 opkg、能现场加 kmod 的发行版了。把上游社区树、内核补丁与 forge 打包链整合成一条命令的活，咱们干了，在咱们之前还没人干过。咱们给板子拍张照，不过分。
