# Ch2 — SD-2：autoboot，上电零输入到 shell

> SD-1 在 U-Boot 提示符手敲三行 `mmc read` 才能把 SD 卡上的 kernel 引起来，每 boot 一次敲一次，调试几轮下来手腕都酸。SD-2 要做的是把这套手敲序列 bake 进 uboot 二进制本身——上电、零输入、自动跑到 buildroot shell。完整记录见 [notes/33](../../notes/33-2026-06-21-sd-card-autoboot-sd2.md)。

## 为什么是第二份 defconfig，而不是改环境

U-Boot 跑的是 `CONFIG_BOOTCOMMAND` 那串命令，我们这套板子的 env 又是 `nowhere`——不向任何介质存环境，所以每次 boot 都跑编译进二进制的默认 bootcmd。而 NAND 那份 defconfig（[0003](../../../patches/uboot/0003-uboot-autoboot-mtd-bootm.patch)）的 bootcmd 是 `mtd read boot ...`，从 NAND 读 kernel；SD 这边要的是 `mmc read ...`，从 SD 卡的 GPT 第二分区读到 kernel FIT。两套 bootcmd 不兼容，硬塞进同一份 defconfig 不行。

可走的路有两条：改环境，或者做 sibling defconfig。env=nowhere 直接把第一条堵死——没有 env 介质就没法在运行时覆盖 bootcmd，能改的只剩编译进二进制那一份默认值。于是正解就是 [0005](../../../patches/uboot/0005-uboot-sd-autoboot-mmc-defconfig.patch)：新增 `configs/evb-rk3506_sd_defconfig`，跟 NAND 那份除了 bootcmd 完全一样，NAND 的 defconfig 一行不动、NAND 那条 update.img 的 mtd-read 路径保持原样。两份 defconfig 各出一份 uboot（`uboot.img` / `uboot-sd.img`），由 pack/assemble 的 `--variant sd` 选着用。

新 defconfig 的核心就这两行：

```
CONFIG_USE_BOOTCOMMAND=y
CONFIG_BOOTCOMMAND="setenv bootargs 'console=ttyS0,1500000 root=/dev/mmcblk0p3 rootwait rw'; \
mmc dev 0; mmc read 0x04000000 0x4000 0x5000; bootm 0x04000000"
```

bootargs 里 `root=/dev/mmcblk0p3` 对应 RKFW SD 卡的三分区 GPT 布局——uboot 在 p1、kernel FIT 在 p2、rootfs 在 p3——这是 [Ch1](01_sd1_manual.md) 那张卡烧完之后的固定拓扑，跟裸 dd 出来的整盘镜像不是一回事。`mmc read` 那行三个数也得对上 SD-1 手动验证过的序列：`mmc dev 0` 选卡、加载偏移 `0x4000`（扇区号，等于 SD 上 p2 内 kernel FIT 的位置）、读长 `0x5000`（扇区数，对齐我们 boot.img 的实际尺寸）。最后 `bootm 0x04000000` 把读进来的 FIT 从那个地址启动——`0x04000000` 这个暂存地址在内核那一章（[boot/03](../boot/03_kernel.md)）的"坑之二"里讲过为什么不能放 `0x02080000`，这里复用同一个避开 kernel load 区的暂存点。

## Kbuild 的 trap：out-of-tree 翻车，正解是 git worktree

编第二份 defconfig，第一反应是 out-of-tree build，干净利落：

```bash
make -C $UBOOT_DIR O=$OUT_DIR/build-uboot-sd evb-rk3506_sd_defconfig
make -C $UBOOT_DIR O=$OUT_DIR/build-uboot-sd ...
```

Kbuild 直接拒了，错误信息一字不漏贴出来：

```
*** The source tree is not clean, please run 'make ARCH=arm mrproper'
*** in .../third_party/src/uboot
```

理由很直白：源树里已经有 NAND 那一轮 in-tree build 的产物（`u-boot-nodtb.bin`、满地的 `.o`、`u-boot.cfg` 那些），Kbuild 不许在脏源树上做 out-of-tree 构建。它让咱们 `make mrproper` 清干净——可 `mrproper` 一跑，NAND 那一份产物全毁，紧接着的 NAND `pack-fit` 直接断链。这条死路咱们怎么走都破不了：要么 Kbuild 拒，要么毁 NAND。

⚠️ 这里千万别想着"那我先编 SD、再编 NAND 顺序来"——两个 defconfig 在同一棵源树里 in-tree build，后编的照样覆盖前一个的产物，pack-fit 拿到的是错的二进制。

解法是 `git worktree`。同一 HEAD 上开一份干净的工作树，源树在那份工作树里是 pristine 的（git 跟踪状态干净、没有任何 build artifact），in-tree build 在那棵新树里跑，NAND 那棵树一根毛都不动。命令序列精简成这样：

```bash
git -C $UBOOT_DIR worktree add --detach $WT_DIR HEAD
# 在 $WT_DIR 里 in-tree build evb-rk3506_sd_defconfig
# 把产物 u-boot-sd-nodtb.bin + u-boot-sd.dtb 拷到 $OUT_DIR
git -C $UBOOT_DIR worktree remove --force $WT_DIR   # trap on exit，无论成败都收
```

`--detach` 是为了脱离任何分支引用——我们就是想就地编一份 SD uboot，不想动当前 checkout 也不想要新分支。编完 `worktree remove --force` 把这棵临时树收掉，bash 这边记得用 trap，免得中途脚本挂了留下脏 worktree 把后续 git 操作搞糊涂。`tools/mkimage` 两份 defconfig 共用（差的就是 bootcmd 那一行，mkimage 调用方式不变）。

## 成功长这样

SD defconfig 编出来的 `uboot-sd.img` 烧进 `update-sd.img`、RK 工具把卡写好、上电——这次一个键都不用敲，[boot-sdl-2026-06211109](../../logs/boot-sdl-2026-06211109.txt) 就是 SD-2 的全自动 boot：

```
Hit any key to stop autoboot: 0          ← 倒计时归零，没人按键
mmc0 is current device
MMC read: dev # 0, block # 16384, count 20480 ... 20480 blocks read: OK
## Loading kernel from FIT Image at 04000000 ...
Starting kernel ...
EXT4-fs (mmcblk0p3): mounted filesystem ... r/w
VFS: Mounted root (ext4) on device 179:3
rk3506 login: root
```

`block # 16384` 就是 `0x4000`、`count 20480` 就是 `0x5000`——bootcmd 里那两个数原样落到串口上，编译进二进制的 mmc read 跑通了。autoboot 倒计时归零、`=>` 提示符一次都没出现，U-Boot 直接执行 baked-in 的 bootcmd：mmc 选卡、读 kernel FIT、bootm 跳过去、内核挂上 SD 卡 p3 那份 ext4 rootfs、`/sbin/init` 起来、落 login。零输入、全自动、跨冷重启可复现。SD 这条路（[Ch1](01_sd1_manual.md) 手动 + 这里自动）到此收口。
