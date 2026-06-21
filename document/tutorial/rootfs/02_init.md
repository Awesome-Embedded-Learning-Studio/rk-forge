# Ch2 — init 时序：从 switch_root 到 login 的两道暗门

> Ch1 把 rootfs 的内容弄出来了。但内核 handoff 到这份 rootfs、busybox init 把 shell 起起来，最后这两公里卡在 init 时序——两道暗门：一道是控制台被抢、输入字符当场劈半，一道是切到真根之后 `/dev` 是个空目录。两道都不在驱动层、根子全在 init 时序上。这章把它们一扇扇推开。完整踩坑记录见 [pitfalls/02](../../pitfalls/02-busybox-init-devtmpfs.md)。

## 前言：最后两公里，坑不在驱动

boot 链好不容易通到 init——rkbin 放行、U-Boot 跑完、kernel 起来、switch_root 切进 rootfs，眼看着就要落到那个 `login:`。结果最后这两步，又摆了两道暗门。折磨人的是，你第一反应全是往驱动、波特率、接线上怀疑，真因却全在 init 的配置和时序。环境跟前面一致：RK3506B AES 板、主线 kernel 7.1、rootfs 是 busybox + UBIFS，console 走 ttyS0@1500000。init 这块用 busybox 的 initramfs（`/init`）做首启 provisioning，然后 switch_root 切到 UBIFS 真根。

## 暗门一：控制台被抢，`ls` 变成 `s: not found`

第一道门来得猝不及防。busybox init 起来了，我以为大功告成，结果串口里提示符是 `~ # ~ #`——两个粘一块儿；手贱敲个 `ls`，终端回我一句 `s: not found`。一开始整个人是懵的：ls 怎么就 not found 了？UART 波特率？接线？驱动？

折腾了一阵才反应过来——我敲的 `l` 和 `s` 被拆开了，一个 sh 收到 `l`、另一个 sh 收到 `s`，收到 `s` 的那个当然报 `s: not found`。罪魁是 inittab 我写了两行 respawn：

```
ttyS0::respawn:/bin/sh
console::respawn:/bin/sh   # ← 这行是祸根
```

机制在这里：我们的 bootargs 是 `console=ttyS0`，这种配置下 `/dev/console` 和 `/dev/ttyS0` 指向**同一颗 UART**。inittab 这两行 respawn 各起一个 sh，两个 sh 都 open 同一个 tty，于是你敲下去的字符被轮流分发到两个进程——`ls` 劈成 `l` 和 `s`。这跟波特率、接线、驱动一点关系都没有，纯属 init 配置。

正解简单粗暴：inittab 只留一行 `ttyS0::respawn:/bin/sh`。别图省事再加一行 `console::respawn`，不然你就会收获那个非常诡异的 `~ # ~ #` 加输入劈半。

## 暗门二：切完 rootfs，板上疯狂刷 `can't open /dev/ttyS0`

第一道门推开没多久，第二道又来了，而且更阴。首启 provisioning 跑完、`switch_root /mnt /sbin/init` 切过去，busybox init 起 inittab 那行 respawn，结果板上开始疯狂刷 `can't open /dev/ttyS0: No such file or directory`，一行接一行，根本进不了 shell。

这一坑我怀疑过一圈：inittab 是不是又写错了？busybox 是不是没编 `CONFIG_DEVTMPFS`？rootfs 里 /dev 目录是不是忘了建？全都不是。真正的机制是 **devtmpfs 的挂载时机**。我们的 kernel 配了 `CONFIG_DEVTMPFS_MOUNT=y`，但这玩意儿**只自动挂到 initramfs 自己的 /dev 上**；一旦 switch_root 切到真 rootfs（UBIFS），新根的 /dev 是个没人管的空目录——UBIFS rootfs 没预填设备节点，也没人给它挂 devtmpfs。于是 busybox init 那行 respawn 去 open `/dev/ttyS0`，扑了个空，死循环刷错。

板上串口把这个时序演得很清楚。失败那次的 [boot-sdl-202606162243](../../logs/boot-sdl-202606162243.txt)，provisioning 刚完切过去，紧接着就是刷屏：

```
[init] provisioning complete → switch_root
can't open /dev/ttyS0: No such file or directory
can't open /dev/ttyS0: No such file or directory
... (连续 20+ 行)
```

有意思的是，同一份日志靠前还有一行 `devtmpfs: initialized`——说明 kernel 侧 devtmpfs 是活的，问题不在它起没起来，而在 switch_root 之后没人把它挂到新根上。

正解是在 initramfs 的 [`/init`](../../../board/aes/initramfs/init) 里、switch_root 之前，手动把 devtmpfs 挂到新根的 /dev。挂的位置很关键：得在真 rootfs 挂好之后、pivot 之前。

```
# switch_root 之前：给新根的 /dev 挂上 devtmpfs
mkdir -p /mnt/dev
mount -t devtmpfs none /mnt/dev 2>/dev/null
```

为什么挂到 `/mnt/dev`？因为这时候真 rootfs 还挂在 `/mnt`，devtmpfs 挂到 `/mnt/dev`，等会儿 switch_root 把 `/mnt` 提成新根，这个 devtmpfs 自然就成了新根的 `/dev`，busybox init 的 respawn 就能 open 到 `/dev/ttyS0`。改完上板，同一个流程，[boot-sdl-202606162254](../../logs/boot-sdl-202606162254.txt) 里 `switch_root` 之后再没有那句刷屏，干干净净落到 shell。

## 这两道门的共性

一道是控制台归属（两个 respawn 抢同一颗 tty），一道是新根 /dev 填充（devtmpfs 的挂载时机），看着不搭界，其实是同一类问题——bringup 阶段拿到 shell 的最后两公里，坑全在 init 时序上，跟驱动没关系。

## 成功长这样

两道暗门推开，内核 handoff 顺顺当当切进 rootfs、busybox init 把 shell 起起来。从 [boot-sdl-202606162254](../../logs/boot-sdl-202606162254.txt) 到全链的 [boot-sdl-2026-06211109](../../logs/boot-sdl-2026-06211109.txt)，switch_root 之后是干干净净的：

```
Run /sbin/init as init process
...
Welcome to rk-forge buildroot
rk3506 login: root
```

shell 起来了，能登录了。但你别急着庆祝——这时候 rootfs 还只是"挂上来能用"，离"写下去跨冷重启还在"还差着整个 rootfs 系列最深的那一程。下一章我们就要和 loader 弱写正面交锋，把 UBIFS 的持久 RW 啃下来。我们 Ch3 见。
