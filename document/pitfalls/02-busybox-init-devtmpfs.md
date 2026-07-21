# 02 — busybox init 的两道暗门:控制台被抢 + 新根 /dev 是空的

boot 链好不容易通到 init 了——rkbin 放行、U-Boot 跑完、kernel 起来、switch_root 切进 rootfs,眼看着就要落到那个 `~ #` 提示符。结果最后这两步,又给我摆了两道暗门:一道是控制台被两个 sh 抢着用、输入字符当场劈半;另一道是切到真 rootfs 之后,新根的 /dev 居然是个空目录,busybox 连 /dev/ttyS0 都打不开。这两坑都不在驱动层,根子全在 init 的时序上,这篇就是怎么把它们一扇扇推开的记录。

环境跟前一篇一样:RK3506B aes 板、主线 kernel 7.1、rootfs 是 busybox + UBIFS,console 走 ttyS0@1500000。init 这块用 busybox 的 initramfs(`/init`)做首启 provisioning,然后 switch_root 切到 UBIFS 真根。

## 提示符变成 `~ # ~ #`,键盘敲 ls 收到个 `s: not found`

第一道门来得猝不及防。busybox init 起来了,笔者以为大功告成,结果串口里提示符是 `~ # ~ #`——两个粘一块儿的;笔者手贱敲个 `ls`,终端回笔者一句 `s: not found`。一开始笔者整个人是懵的:ls 怎么就 not found 了?UART 波特率?接线?驱动?

折腾了一阵才反应过来——笔者敲的 `l` 和 `s` 被拆开了,一个 sh 收到 `l`、另一个 sh 收到 `s`,收到 `s` 的那个当然报 `s: not found`。罪魁是 inittab 笔者写了两行 respawn:

```
ttyS0::respawn:/bin/sh
console::respawn:/bin/sh   # ← 这行是祸根
```

机制在这里:我们的 bootargs 是 `console=ttyS0`,在这种配置下 `/dev/console` 和 `/dev/ttyS0` 指向的是**同一颗 UART**。inittab 里这两行 respawn 各起一个 sh,两个 sh 都 open 同一个 tty,于是咱们敲下去的字符就被轮流分发到两个进程里——`ls` 劈成 `l` 和 `s`。这跟波特率、接线、驱动一点关系都没有,纯属 init 配置。

正解简单粗暴:inittab 只留一行。我把修复和原因都写进了 [inittab](../../board/aes/rootfs/etc/inittab) 的注释里,就那一行 `ttyS0::respawn:/bin/sh`,顺手把"两行会劈字符"这事儿原样记下,省得以后有人手贱又加回去。

⚠️ `console=ttyS0` 下,inittab 的控制台 respawn 只能有一行 `ttyS0::respawn:/bin/sh`,千万别图省事再加一行 `console::respawn:/bin/sh`,不然你会收获一个非常诡异的 `~ # ~ #` 加输入劈半。

## 切完 rootfs,板上疯狂刷 `can't open /dev/ttyS0`

第一道门推开没多久,第二道又来了——而且更阴。首启 ubiprog 把 rootfs provisioning 跑完、`switch_root /mnt /sbin/init` 切过去,busybox init 起 inittab 那行 respawn,结果板上开始疯狂刷 `can't open /dev/ttyS0: No such file or directory`,一行接一行,根本进不了 shell。

这一坑我怀疑过一圈:inittab 是不是又写错了?busybox 是不是没编 `CONFIG_DEVTMPFS`?rootfs 里 /dev 目录是不是忘了建?全都不是。真正的机制是 devtmpfs 的挂载时机:我们的 kernel 配了 `CONFIG_DEVTMPFS_MOUNT=y`,但这玩意儿**只自动挂到 initramfs 自己的 /dev 上**;一旦 switch_root 切到真 rootfs(UBIFS),新根的 /dev 是个没人管的空目录(UBIFS rootfs 没预填设备节点,也没人给它挂 devtmpfs),于是 busybox init 那行 `ttyS0::respawn` 去 open `/dev/ttyS0`,扑了个空,死循环刷错。

板上串口把这个时序演得很清楚。失败那次的 [boot-sdl-202606162243.txt](../logs/boot-sdl-202606162243.txt),provisioning 刚完就切过去,紧接着就是刷屏:

```
[init] provisioning complete → switch_root
can't open /dev/ttyS0: No such file or directory
can't open /dev/ttyS0: No such file or directory
... (连续 20+ 行)
```

有意思的是,同一份日志靠前还有一行 `[ 0.013236] devtmpfs: initialized`——说明 kernel 侧 devtmpfs 是活的,问题不在它起没起来,而在 switch_root 之后没人把它挂到新根上。

正解是在 initramfs 的 `/init` 里、switch_root 之前,手动把 devtmpfs 挂到新根的 /dev。挂的位置很关键:得在真 rootfs 挂好之后、pivot 之前。我在 [initramfs/init](../../board/aes/initramfs/init) 的 `switch_to_rootfs()` 里加了这几行:

```
# Populate /dev on the real rootfs. CONFIG_DEVTMPFS_MOUNT only auto-mounts
# devtmpfs on the initramfs /dev; after switch_root the new root's /dev is
# empty, so busybox init's ttyS0::respawn:/bin/sh can't open /dev/ttyS0.
# Mount devtmpfs on the new root's /dev before pivoting.
mkdir -p /mnt/dev
mount -t devtmpfs none /mnt/dev 2>/dev/null
```

为什么挂到 `/mnt/dev` 而不是别处?因为这时候真 rootfs 还挂在 `/mnt`,devtmpfs 挂到 `/mnt/dev`,等会儿 switch_root 把 `/mnt` 提成新根,这个 devtmpfs 自然就成了新根的 `/dev`,busybox init 的 respawn 就能 open 到 `/dev/ttyS0` 了。改完上板,同一个流程,[boot-sdl-202606162254.txt](../logs/boot-sdl-202606162254.txt) 里 `switch_root` 之后再没有那句刷屏,干干净净落到 shell。

⚠️ initramfs 的 `/init` 在 switch_root 之前,一定记得 `mkdir -p /mnt/dev && mount -t devtmpfs none /mnt/dev`。别指望 `CONFIG_DEVTMPFS_MOUNT=y` 能帮你盖到真 rootfs,它只管 initramfs 自己那一亩三分地;新根的 /dev 要你自己挂。

劈字符那现场当时没存 log,要复现就回放双 respawn 的 inittab;`/dev/ttyS0` 那条倒是有完整的失败→成功对照([boot-sdl-202606162243](../logs/boot-sdl-202606162243.txt) 刷屏 → [boot-sdl-202606162254](../logs/boot-sdl-202606162254.txt) 干净落到 shell)。下一篇换个地方——构建侧的两个方法论坑:syncconfig 卡相对路径、strings 查 zImage 查错层。
