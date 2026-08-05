# Ch4 — Ubuntu rootfs：从 ubuntu-base 到 GNOME 桌面

> RK3506B 那条 rootfs 路走的是 buildroot 出 busybox 最小系统；RK3588 这块板咱们直接上 Ubuntu 26.04 + GNOME 桌面。性质变了，坑也变了——这一章讲两个：GDM 起来却没账户登录、以及一个把整个 ext4 的文件 ownership 搞错的打包 bug。完整记录见 [notes/56](../../notes/56-2026-08-02-rk3588-ubuntu-user-rootfs-ownership.md)。buildroot 那条路（BR2_EXTERNAL、init 时序、外部工具链检查）在 [RK3568 的 rootfs 卷](../rootfs/) 讲过，这里不重复。

## Ubuntu rootfs 怎么出来的

先说这条 rootfs 不是 buildroot 出的，也不是 debootstrap。咱们用 `ubuntu-base` 的 arm64 tarball 起，借 `qemu-user-static` 在开发机上 chroot 进去 `apt install` 出一套完整系统——桌面、网络、固件都装齐，再 tar 出来交给 forge 打包。[scripts/build-ubuntu-rootfs.sh](../../../scripts/build-ubuntu-rootfs.sh) 干的就是这件事，包列表在 [board/rk3588-topeet/ubuntu/packages.list](../../../board/rk3588-topeet/ubuntu/packages.list)（systemd、netplan、openssh、linux-firmware、mesa、`ubuntu-desktop` 全套）。

出来的 `ubuntu-rootfs.tar` 交给 [stage-rootfs.sh](../../../scripts/stage-rootfs.sh) 解包、做板级定制（fstab 指 mmcblk1p3、hostname、ttyFIQ0 getty、用户、GDM 自动登录），再由 [pack-emmc.sh](../../../scripts/pack-emmc.sh) 用 `mke2fs -d` 打成 ext4。后面两个坑就埋在「解包→定制→打 ext4」这段链路里。

## 坑之一：GDM 起来了，却没有可登录账户

GPU 那关过了，桌面能渲染了，GDM 登录界面也出来了——可界面上没有账户，登不进去。检查 staged rootfs 的 `/etc/passwd`，里面只有 root 和一堆系统账户，没有 UID ≥ 1000 的普通用户。GDM 默认不提供 root 的图形登录，所以你面对的就是一个空荡荡的登录界面。

根因不复杂：`ubuntu-base` 的初始 tarball 不带普通用户，chroot 阶段忘了 `useradd` 创建桌面用户。修是在 stage-rootfs 的板级定制里固化一个开发用户（用户名、UID/GID、主目录、shell、附加组都写死），再配 GDM 自动登录这个用户。

## 坑之二：整个 ext4 的 ownership 是错的

给 rootfs 加了用户，正以为收工，回头一查此前成品的 `rootfs.ext4`——发现问题比「没用户」严重得多：

```
/etc/passwd    uid=1000 gid=1000
/bin/bash      uid=1000 gid=1000
/home          uid=1000 gid=1000
```

`/etc/passwd`、`/bin/bash` 这些本该属于 root 的系统文件，全变成了 uid=1000。如果只在这样的 rootfs 里补一个 UID 1000 的桌面用户，那个用户会「拥有」一大堆系统文件——这是绝对不能接受的。

根因在打包链的 ownership 传递上。`ubuntu-rootfs.tar` 本身是用 numeric ownership 存的（`/etc/passwd` 是 0:0），可 [stage-rootfs.sh](../../../scripts/stage-rootfs.sh) 是由普通用户（uid=1000）来解包的——解包时 tar 默认把 staging tree 的文件 owner 变成当前用户，于是磁盘上的 staging 目录里所有文件都变成了 uid=1000。接着 [pack-emmc.sh](../../../scripts/pack-emmc.sh) 的 `mke2fs -d` 原样把这个错误的 ownership 写进 ext4。tar 保存对了，坏在解包这一步。

## 正解：fakeroot ownership 数据库跨 stage 持久化

正解是在 staging 和 ext4 pack 之间，用 fakeroot 的 ownership 数据库把正确的属主信息持久化下来，让两个 stage 用同一份 state。落到这几处：

```bash
# staging 解包：保留 numeric ownership
tar --numeric-owner --same-owner -xf ubuntu-rootfs.tar
# WSL2 下 fakeroot 的 chown 会返回 EINVAL，要绕开
export FAKEROOTDONTTRYCHOWN=1
# pack-emmc 加载同一份 fakeroot state 再跑 mke2fs -d
fakeroot -i board/rk3588-topeet/out/.rootfs.fakeroot \
         -o board/rk3588-topeet/out/.rootfs.fakeroot \
         mke2fs -d staging/ ...
```

整条链路全程不需要 sudo、不需要 mount、不需要 loop device——这是 fakeroot 的好处，它在一个普通用户态的 ownership 虚拟层里就把「假装 root 操作」这件事办了，state 存进 `.rootfs.fakeroot` 文件跨脚本传递。

桌面用户固化在 clean rootfs build 和 cached-tar staging 两条路径里，写死成：

```
用户名：charliechen   UID/GID：1000/1000   主目录：/home/charliechen   Shell：/bin/bash
附加组：adm sudo audio video render input plugdev netdev
GDM：开发阶段自动登录 charliechen
```

## 成功长这样

ownership 修没修对，不能只看 staging tree（那是 fakeroot 虚拟层），要直接读 ext4 的 inode。用只读的 `debugfs` 查成品 `rootfs.ext4`：

```
/etc/passwd                                  0:0    mode 0644
/bin/bash                                    0:0    mode 0755
/usr/lib                                     0:0    mode 0755
/home/charliechen                         1000:1000 mode 0750
/var/lib/AccountsService/users/charliechen   0:0    mode 0600
```

系统文件回到 root，只有 `/home/charliechen` 属于 1000——这才对。这版 `update.img`（`d100a898…`，3.29 GB）就是带 GNOME 桌面、正确 ownership、桌面用户可登录的成品。

> ⚠️ 一条安全账，别带到产品里：开发阶段的 GDM 自动登录用的是明文密码（`charliechen / chen0303`），它是 bring-up 期间方便调试的公开凭据。产品化之前必须关掉自动登录、换掉或锁死这个密码——教程和 notes 里写这个密码，只是为了让你能复现 bring-up 环境，不是让你照着上生产线。
