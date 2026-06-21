# Ch2 — SD-2：autoboot，上电零输入到 shell

> SD-1 要在 U-Boot 提示符手敲三行 `mmc read`，每 boot 一次敲一次，太累。SD-2 把它做成 autoboot：上电、零输入、自动跑到 shell。办法是给 U-Boot 加第二份 defconfig，把 bootcmd 直接写成 mmc read 那套、烧进去。完整记录见 [notes/33](../../notes/33-2026-06-21-sd-card-autoboot-sd2.md)。

## 为什么是第二份 defconfig

U-Boot 跑的是 `CONFIG_BOOTCOMMAND` 里那串命令。我们 env 是 `nowhere`（不存环境），所以每次 boot 都跑编译进二进制的默认 bootcmd。而 NAND 那份 defconfig 的 bootcmd 是 `mtd read boot ...`（从 NAND 读 kernel），SD 要的是 `mmc read ...`（从 SD 读）——两套不兼容。

所以正解不是改环境，是**做一份 sibling defconfig**：bootcmd 写成 mmc read 那套，bake 进二进制。NAND 的 defconfig 不动，两份 defconfig 各出一份 uboot（`uboot.img` / `uboot-sd.img`），按变体选用。这就是 uboot patch [0005](../../../patches/uboot/0005-uboot-sd-autoboot-mmc-defconfig.patch)：新增 `evb-rk3506_sd_defconfig`，和 NAND 那份除了 bootcmd 完全一样：

```
CONFIG_BOOTCOMMAND="setenv bootargs 'console=ttyS0,1500000 root=/dev/mmcblk0p3 rootwait rw'; \
mmc dev 0; mmc read 0x04000000 0x4000 0x5000; bootm 0x04000000"
```

`root=/dev/mmcblk0p3` 对应 RKFW 的 SD 三分区布局，加载偏移 `0x4000` 和读长 `0x5000` 对齐 SD-1 验证过的手动序列。

## Kbuild 的 trap：为什么用 git worktree 而不是 make O=

编这份 SD defconfig，第一反应是 out-of-tree：`make -C uboot O=$OUT/build-uboot-sd`。Kbuild 直接拒了——`The source tree is not clean, please run make mrproper`。因为源树里已经有 NAND 的 in-tree 产物（u-boot-nodtb.bin、.o 那些），Kbuild 不许在脏源树上做 out-of-tree构建。可你要 `mrproper` 清掉它，就把 NAND 的产物毁了、NAND 的 pack-fit 也跟着崩。

解法是 **git worktree**：`worktree add --detach` 开一个同一 HEAD 的干净工作树，在那里 in-tree 编 SD defconfig，NAND 那棵树一根毛都不动，编完 `worktree remove --force` 收掉。为什么不用 `make O=`？因为 Kbuild 禁止脏源树 out-of-tree；为什么不清源树？因为会毁 NAND 产物。worktree 是唯一两全的路。`tools/mkimage` 两份 defconfig 共用（只差 bootcmd）。

## 成功长这样

SD defconfig 编出来的 `uboot-sd.img` 烧进 update-sd.img，上电——这次一个键都不用敲，[boot-sdl-2026-06211109](../../logs/boot-sdl-2026-06211109.txt) 就是 SD-2 的全自动 boot：

```
Hit any key to stop autoboot: 0          ← 没人按键
mmc0 is current device
MMC read: dev # 0, block # 16384, count 20480 ... 20480 blocks read: OK
## Loading kernel from FIT Image at 04000000 ...
Starting kernel ...
EXT4-fs (mmcblk0p3): mounted filesystem ... r/w
rk3506 login: root
```

`Hit any key to stop autoboot: 0` 那个倒计时归零、没人打断，U-Boot 就自动跑了编译进去的 mmc read bootcmd，kernel 起来、挂 SD ext4、落 login。零输入、全自动。SD 这条路（SD-1 手动 + SD-2 自动）到此走通。
