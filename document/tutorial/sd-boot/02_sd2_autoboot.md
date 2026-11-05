# Ch2 — SD-2：autoboot，上电零输入到 shell

> SD-1 在 U-Boot 提示符手敲三行 `mmc read` 才能把 SD 卡上的 kernel 引起来，咱们每 boot 一次就得敲一次，几轮调试下来手腕都酸了。SD-2 要做的是把这套手敲序列 bake 进 uboot 二进制本身，做到上电零输入、自动跑进 buildroot 的 shell。完整的记录见 [notes/33](../../notes/33-2026-06-21-sd-card-autoboot-sd2.md)。

## 为什么是第二份 defconfig，而不是改环境

U-Boot 跑的是 `CONFIG_BOOTCOMMAND` 那串命令，咱们这套板子的 env 又是 `nowhere`，环境是哪儿都不存的，所以每次 boot 都跑编译进二进制的默认 bootcmd。而 NAND 那边 defconfig（[0003](../../../boards/aes/patches/uboot/0003-uboot-autoboot-mtd-bootm.patch)）的 bootcmd 是 `mtd read boot ...`，读的是 NAND 里的 kernel。SD 这边要的是 `mmc read ...`，从 SD 卡的 GPT 第二分区读 kernel FIT。两套 bootcmd 是不兼容的，硬塞进同一份 defconfig 是不行的。

咱们可走的路有两条：改环境，或者做 sibling 的 defconfig。env=nowhere 直接把头一条路堵死了。没有 env 介质的话就没法在运行时覆盖 bootcmd，能改的只剩编译进二进制的默认值。于是咱们的正解就是 [0005](../../../boards/aes/patches/uboot/0005-uboot-sd-autoboot-mmc-defconfig.patch)：新增的 `configs/evb-rk3506_sd_defconfig` 跟 NAND 那边除了 bootcmd 完全一样，NAND 的 defconfig 一行不动，NAND 那路 update.img 的 mtd-read 路径保持原样。两份 defconfig 出的 uboot 也就分成两份（`uboot.img` / `uboot-sd.img`），由 pack/assemble 的 `--variant sd` 选着用。

咱们要加的新 defconfig 核心就是这两行：

```
CONFIG_USE_BOOTCOMMAND=y
CONFIG_BOOTCOMMAND="setenv bootargs 'console=ttyS0,1500000 root=/dev/mmcblk0p3 rootwait rw'; \
mmc dev 0; mmc read 0x04000000 0x4000 0x5000; bootm 0x04000000"
```

bootargs 里 `root=/dev/mmcblk0p3` 对应的是 RKFW SD 卡的三分区 GPT 布局，uboot 占的是 p1、kernel FIT 占的是 p2、rootfs 占的是 p3，这是 [Ch1](01_sd1_manual.md) 里烧完卡之后固定的拓扑，跟裸 dd 出来的整盘镜像不是一回事。`mmc read` 那行三个数也得对上咱们在 SD-1 手动验证过的序列：`mmc dev 0` 负责选卡，`0x4000` 是加载的偏移（扇区号，也就是 SD 上 p2 内 kernel FIT 的位置），`0x5000` 是读的长度（扇区数，对齐的是咱们 boot.img 的实际尺寸）。最后 `bootm 0x04000000` 把读进来的 FIT 从那个地址启动。`0x04000000` 这个暂存地址在内核那一章（[boot/03](../boot/03_kernel.md)）的“翻车二”里讲过为什么不能放 `0x02080000`，这里复用的是同一个避开 kernel load 区的暂存点。

## Kbuild 的 trap：out-of-tree 翻车，正解是 git worktree

咱们编第二份 defconfig 的第一反应是 out-of-tree build，图的就是干净利落：

```bash
make -C $UBOOT_DIR O=$OUT_DIR/build-uboot-sd evb-rk3506_sd_defconfig
make -C $UBOOT_DIR O=$OUT_DIR/build-uboot-sd ...
```

Kbuild 直接拒了，错误信息咱们一字不漏地贴出来：

```
*** The source tree is not clean, please run 'make ARCH=arm mrproper'
*** in .../third_party/src/uboot
```

理由其实很直白：源树里已经有 NAND 那一轮 in-tree build 的产物（`u-boot-nodtb.bin`、满地的 `.o`、`u-boot.cfg` 那些），Kbuild 是不许在脏源树上做 out-of-tree 构建的。它让咱们 `make mrproper` 清干净。不过 `mrproper` 一跑，NAND 的产物全毁，紧接着的 NAND `pack-fit` 直接断链。这样的死路咱们怎么走都破不了：Kbuild 拒的是 out-of-tree，`mrproper` 毁的是 NAND 的产物。

⚠️ 咱们别想着用“编完 SD 再编 NAND”的顺序绕过去。两个 defconfig 在同一棵源树里做的 in-tree build，后编的照样会覆盖前一个的产物，pack-fit 拿到的是错的二进制。

咱们最后的解法是 `git worktree`。咱们在同一 HEAD 上开一份干净的工作树，源树在新的工作树里是 pristine 的（git 跟踪状态干净、没有任何 build artifact），in-tree build 在那棵新的树里跑，NAND 那棵树咱们一根毛都不动。命令序列咱们精简成了这样：

```bash
git -C $UBOOT_DIR worktree add --detach $WT_DIR HEAD
# 在 $WT_DIR 里 in-tree build evb-rk3506_sd_defconfig
# 把产物 u-boot-sd-nodtb.bin + u-boot-sd.dtb 拷到 $OUT_DIR
git -C $UBOOT_DIR worktree remove --force $WT_DIR   # trap on exit，无论成败都收
```

`--detach` 是为了脱离任何的分支引用——咱们就是想就地编一份 SD uboot，不想动当前的 checkout、也不想要新分支。编完了用 `worktree remove --force` 把这棵临时树收掉，bash 这边咱们记得用 trap，免得中途脚本挂了留下脏 worktree 把后续 git 操作搞糊涂。`tools/mkimage` 两份 defconfig 共用（差的就是 bootcmd 那一行，mkimage 的调用方式不变）。

## 成功长这样

SD defconfig 编出来的 `uboot-sd.img` 烧进 `update-sd.img`，RK 工具也把卡写好了，咱们一上电、一个键都不用敲，[boot-sdl-2026-06211109](../../logs/boot-sdl-2026-06211109.txt) 就是 SD-2 的全自动 boot：

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

`block # 16384` 就是 `0x4000`、`count 20480` 就是 `0x5000`——bootcmd 里的两个数原样落到了串口上，编译进二进制的 mmc read 也就跑通了。autoboot 的倒计时归零，`=>` 提示符是一回都没露过的，U-Boot 直接执行的是 baked-in 的 bootcmd：mmc 选卡、读 kernel FIT、bootm 跳过去，内核挂上 SD 卡 p3 的 ext4 rootfs，`/sbin/init` 也起来了、落到了 login。零输入、全自动的样子，跨冷重启咱们也复现过。SD 这一路（[Ch1](01_sd1_manual.md) 手动 + 这里自动）到这儿就走完了。
