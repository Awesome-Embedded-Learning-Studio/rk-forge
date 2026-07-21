# Ch2 — init 时序：从 switch_root 到 login 的两道暗门

> Ch1 把 rootfs 的内容弄出来了。但内核 handoff 到这份 rootfs、busybox init 把 shell 起起来，最后这两公里卡在 init 时序：一道是控制台被抢、输入字符当场劈半，一道是切到真根之后 `/dev` 是个空目录。两道都不在驱动层，根子全在 init 时序上。完整踩坑记录见 [pitfalls/02](../../pitfalls/02-busybox-init-devtmpfs.md)。

## 前言：最后两公里，坑不在驱动

boot 链好不容易通到 init。rkbin 放行、U-Boot 跑完、kernel 起来、switch_root 切进 rootfs，眼看着就要落到那个 `login:`。结果最后这两步，又摆了两道暗门。折磨人的是，笔者第一反应全是往驱动、波特率、接线上怀疑，真因却全在 init 的配置和时序。环境跟前面一致：RK3506B AES 板、主线 kernel 7.1、rootfs 是 busybox + UBIFS，console 走 ttyS0@1500000。init 这块用 busybox 的 initramfs（`/init`）做首启 provisioning，然后 switch_root 切到 UBIFS 真根。

首启 provisioning 的来龙去脉在 Ch3 那章细讲（loader 弱写 + ubiprog 那一程），这里只点一句：第一次 boot 时，initramfs 里的 [`/init`](../../../board/aes/initramfs/init) 会通过 ubiprog 把 rootfs 分区用内核自己的写路径重写一遍，盖一个 `.rkforge_provisioned` marker，之后再 `switch_root /mnt /sbin/init` 切到真根；往后每次启动，`/init` 看到 marker 就跳过重写、直接切。两道暗门就卡在这条 `/init → switch_root → /sbin/init` 的交接链上。

## 暗门一：控制台被抢，`ls` 变成 `s: not found`

第一道门来得猝不及防。busybox init 起来了，看着像大功告成，结果串口里提示符是 `~ # ~ #`，两个粘一块儿；手贱敲个 `ls`，终端回一句 `s: not found`。一开始整个人是懵的：`ls` 怎么就 not found 了？UART 波特率？接线？驱动？

折腾了一阵才反应过来。笔者敲的 `l` 和 `s` 被拆开了，一个 sh 收到 `l`、另一个 sh 收到 `s`，收到 `s` 的那个当然报 `s: not found`。罪魁是 inittab 笔者写了两行 respawn：

```
ttyS0::respawn:/bin/sh
console::respawn:/bin/sh   # ← 这行是祸根
```

机制在这里。我们的 bootargs 是 `console=ttyS0`，这种配置下 `/dev/console` 和 `/dev/ttyS0` 指向同一颗 UART。inittab 这两行 respawn 各起一个 sh，两个 sh 都 open 同一个 tty，于是咱们敲下去的字符被轮流分发到两个进程，`ls` 劈成 `l` 和 `s`。这跟波特率、接线、驱动一点关系都没有，纯属 init 配置。

正解简单粗暴：inittab 只留一行 `ttyS0::respawn:/bin/sh`。修复和原因都写进了 [`board/aes/rootfs/etc/inittab`](../../../board/aes/rootfs/etc/inittab) 的注释里，顺手把"两行会劈字符"这事儿原样记下，省得以后有人手贱又加回去。

⚠️ `console=ttyS0` 下，inittab 的控制台 respawn 只能有一行 `ttyS0::respawn:/bin/sh`，千万别图省事再加一行 `console::respawn:/bin/sh`，不然咱们会收获一个非常诡异的 `~ # ~ #` 加输入劈半。这一坑笔者当时没存现场 log，证据留在 inittab 的源码注释里，要复现就回放双 respawn 的 inittab。

## 暗门二：切完 rootfs，板上疯狂刷 `can't open /dev/ttyS0`

第一道门推开没多久，第二道又来了，而且更阴。首启 provisioning 跑完、`switch_root /mnt /sbin/init` 切过去，busybox init 起 inittab 那行 respawn，结果板上开始疯狂刷 `can't open /dev/ttyS0: No such file or directory`，一行接一行，根本进不了 shell。

这一坑笔者怀疑过一圈：inittab 是不是又写错了？busybox 是不是没编 `CONFIG_DEVTMPFS`？rootfs 里 /dev 目录是不是忘了建？全都不是。真正的机制是 devtmpfs 的挂载时机。我们的 kernel 配了 `CONFIG_DEVTMPFS_MOUNT=y`，但这玩意儿只自动挂到 initramfs 自己的 /dev 上；一旦 switch_root 切到真 rootfs（UBIFS），新根的 /dev 是个没人管的空目录——UBIFS rootfs 没预填设备节点，也没人给它挂 devtmpfs。于是 busybox init 那行 respawn 去 open `/dev/ttyS0`，扑了个空，死循环刷错。

板上串口把这个时序演得很清楚。失败那次的 [boot-sdl-202606162243](../../logs/boot-sdl-202606162243.txt)，provisioning 刚完切过去，紧接着就是刷屏：

```
[init] provisioning complete → switch_root
can't open /dev/ttyS0: No such file or directory
can't open /dev/ttyS0: No such file or directory
... (连续 20+ 行)
```

有意思的是，同一份日志靠前还有一行 `[    0.013236] devtmpfs: initialized`——说明 kernel 侧 devtmpfs 是活的，问题不在它起没起来，而在 switch_root 之后没人把它挂到新根上。`CONFIG_DEVTMPFS_MOUNT=y` 的语义比直觉窄：它只在内核 mount rootfs 那条路径上、给最初的那个 root（这里是 initramfs）挂一次 devtmpfs；switch_root 是用户态换根，内核根本不知道，更不会替新根补挂。inittab 注释里那句"devtmpfs is auto-mounted, so /dev is already populated"是站在 switch_root 之后的 busybox init 视角写的——前提是 `/init` 已经把 devtmpfs 挂到了新根的 `/dev`。这个前提不写进 `/init`，就是刷屏。

正解是在 initramfs 的 [`/init`](../../../board/aes/initramfs/init) 里、switch_root 之前，手动把 devtmpfs 挂到新根的 /dev。挂的位置很关键：得在真 rootfs 挂好之后、pivot 之前。`switch_to_rootfs()` 里那几行：

```sh
# Populate /dev on the real rootfs. CONFIG_DEVTMPFS_MOUNT only auto-mounts
# devtmpfs on the initramfs /dev; after switch_root the new root's /dev is
# empty, so busybox init's ttyS0::respawn:/bin/sh can't open /dev/ttyS0.
# Mount devtmpfs on the new root's /dev before pivoting (it survives
# switch_root and stays as /dev).
mkdir -p /mnt/dev
mount -t devtmpfs none /mnt/dev 2>/dev/null
```

为什么挂到 `/mnt/dev` 而不是别处？因为这时候真 rootfs 还挂在 `/mnt`，devtmpfs 挂到 `/mnt/dev`，等会儿 switch_root 把 `/mnt` 提成新根，这个 devtmpfs 自然就成了新根的 `/dev`，busybox init 的 respawn 就能 open 到 `/dev/ttyS0`。switch_root 不重建文件系统命名空间，它只是把进程的根目录和当前目录切到新根，已挂载的 vfs 树原样带过去——这正是为什么"在 pivot 前挂到 `/mnt/dev`"能落在 pivot 后的 `/dev`。改完上板，同一个流程，[boot-sdl-202606162254](../../logs/boot-sdl-202606162254.txt) 里 `switch_root` 之后再没有那句刷屏，干干净净落到 shell。

⚠️ initramfs 的 `/init` 在 switch_root 之前，一定记得 `mkdir -p /mnt/dev && mount -t devtmpfs none /mnt/dev`。别指望 `CONFIG_DEVTMPFS_MOUNT=y` 能帮咱们盖到真 rootfs，它只管 initramfs 自己那一亩三分地；新根的 /dev 要咱们自己挂。

## 顺带一坑：TMPFS 没显式锁住，`mount -t tmpfs` 静默退回 ramfs

inittab 里除了 respawn 那行，还有几行 sysinit 往 `/tmp`、`/run` 挂 tmpfs：

```
::sysinit:/bin/mount -t tmpfs   none /tmp
::sysinit:/bin/mount -t tmpfs   none /run
```

这几行看着无害，但踩过一个阴的。`multi_v7` defconfig 默认只开 `TMPFS_POSIX_ACL`、不开 `CONFIG_TMPFS`，TMPFS 本身是靠默认 y 跟着上去的；而我们裁体积那条链（`merge_config` + `olddefconfig`）能把 TMPFS 默默掉成 `# CONFIG_TMPFS is not set`，板上 `.config` 真就出现过这一行。TMPFS 关掉之后 `mount -t tmpfs` 不会报错，内核把它静默退回 ramfs，而 ramfs 不认 buildroot `/etc/fstab` 里的 `mode=` 选项，于是 `/tmp` 挂不上、报一句 `unknown parameter 'mode'`。所以 [`board/rk3506-evb/kernel-trim.config`](../../../board/rk3506-evb/kernel-trim.config) 里把 `CONFIG_TMPFS=y` 显式锁住了，配 KEEP 注释写明"别让 merge_config 把它掉成 n"。这一坑不算 init 时序本身，但它跟 inittab 那几行 sysinit 强绑定：TMPFS 不在，init 阶段就又会卡一道，所以一并记在这里。

## 成功长这样

两道暗门推开，内核 handoff 顺顺当当切进 rootfs、busybox init 把 shell 起起来。从 [boot-sdl-202606162254](../../logs/boot-sdl-202606162254.txt) 到全链 [boot-sdl-2026-06211109](../../logs/boot-sdl-2026-06211109.txt)，switch_root 之后是干干净净的：

```
Run /sbin/init as init process
...
Welcome to rk-forge buildroot
rk3506 login: root
```

shell 起来了，能登录了。但这会儿 rootfs 还只是"挂上来能用"，离"写下去跨冷重启还在"还差着整个 rootfs 系列最深的那一程——下一章我们就和 loader 弱写正面交锋，把 UBIFS 的持久 RW 啃下来。Ch3 见。
