# 56 — RK3588 Ubuntu 桌面用户与 rootfs ownership 修复（2026-08-02）

## 现象与根因

GDM 已启动但没有可登录账户。检查 staged rootfs 的 `/etc/passwd`，只有 root 和系统账户，
没有 UID ≥ 1000 的普通用户。GDM 默认不提供 root 图形登录，因此不可能进入正常 GNOME
会话。

检查此前成品 `rootfs.ext4` 又发现更严重的打包问题：

```text
/etc/passwd  uid=1000 gid=1000
/bin/bash    uid=1000 gid=1000
/home        uid=1000 gid=1000
```

`ubuntu-rootfs.tar` 正确保存了 numeric root ownership，但 `stage-rootfs.sh` 由普通用户解包，
磁盘上的 staging tree 全部变成宿主用户 UID/GID 1000；随后 `mke2fs -d` 原样把错误 ownership
写入 ext4。若只新增 UID 1000 用户，该用户会拥有大量系统文件，不能接受。

## 修复

Ubuntu staging 和 ext4 pack 之间加入持久化 fakeroot ownership 数据库：

```text
board/rk3588-topeet/out/.rootfs.fakeroot
```

- staging 使用 `tar --numeric-owner --same-owner`；
- WSL2 下设置 `FAKEROOTDONTTRYCHOWN=1`，避免 tar chown 返回 `EINVAL`；
- `pack-emmc.sh` 加载同一 fakeroot state 后再运行 `mke2fs -d`；
- 全流程仍然不需要 sudo、mount 或 loop device。

用户同时固化到 clean rootfs build 和 cached-tar staging 两条路径：

```text
用户名：charliechen
密码：chen0303
UID/GID：1000/1000
主目录：/home/charliechen
Shell：/bin/bash
附加组：adm sudo audio video render input plugdev netdev
```

GDM 配置为开发阶段自动登录 `charliechen`。该密码属于明文公开的 bring-up 凭据，产品化
前必须关闭自动登录并更换或锁定密码。

## 成品 ext4 验证

通过只读 `debugfs` 直接检查 inode，而不是只看 staging tree：

```text
/etc/passwd                                  0:0 mode 0644
/bin/bash                                    0:0 mode 0755
/usr/lib                                     0:0 mode 0755
/home/charliechen                         1000:1000 mode 0750
/var/lib/AccountsService/users/charliechen   0:0 mode 0600
```

同时验证：

- passwd 中账户 UID/GID/home/shell 正确；
- 8 个附加组完整；
- shadow 中 `chen0303` 的 SHA-512 crypt 哈希匹配；
- `/etc/gdm3/custom.conf` 的自动登录目标为 `charliechen`。

## 构建产物

完整执行 stage-rootfs、pack-emmc、RKAF+RKFW assemble 和 round-trip 自检：

```text
rk3588-topeet.dtb  282e630c0303ed417985ca1f98c0d3b0a8f4bfab901a49c004e9d765565b95a5
boot.img           9b738b027129e39a39ea61de57902dd268744c7bb6631914b90c04d3d43e3c8c
rootfs.ext4        868a677739a65b867933f4f20724e504397cfc52e14aa4bd79680cff95fc0050
update.img         d100a898c426a014362b58a3a479a09902c380cabe1404621fdf9127f2b368c5
```

`update.img` 大小为 `3290329674` 字节。它保留 [55](55-2026-08-02-rk3588-gt911-landscape-axis-fix.md)
的最终无 swap 触摸 DT；`af26a389…` 内容上没有普通用户且 ownership 错误，不再使用。
