# 117 — RK3588 NFS root：直连静态段 bring-up 全记录（2026-10-31）

> 目标：把「改 rootfs 秒级生效、重启即新版」的 NFS root 迭代引擎架到 rk3588 上。
> 一天里搭好内核/宿主/板侧三层基建，踩掉两颗构建雷、一颗记忆雷，用分层排查法把
> 「串口半行截断」拆成「console 瞎 + 直连无 DHCP」两件事。镜像已产出（MD5
> `6b118094`），真板 NFS root 起机验证待下一轮烧录。

## 0. 结论

| 项 | 结果 |
|---|---|
| 内核 | `kernel.config` fragment 补 NFS 全链：`ROOT_NFS/IP_PNP_DHCP/NFS_FS/NFS_V3/V4` + 网卡强制 `=y`（`DWMAC_ROCKCHIP`、`REALTEK_PHY`）——NFS root 无用户态，modprobe 不存在，**内置是硬要求** |
| 网络拓扑 | 板 eth0 **直连** PC 有线口（无 DHCP）；静态 `192.168.50.0/24`：PC=192.168.50.5（Windows 静态，mirrored 进 WSL eth1），板=192.168.50.99 |
| 导出 | **单源导出 `out/rk3588-topeet/rootfs`**（forge 打包源树本体）——NFS 视角 = `rootfs.ext4` 内容，busybox md5 双侧一致（`f8bf5254`）实证零漂移 |
| 链路验证 | 分层全通：PHY 自协商 ✅ → ARP 双向 ✅（Windows ARP 表实锤板 MAC `66:50:1b:af:7e:d2`）→ TFTP ✅（8 字节 `TFTP-OK`）→ ICMP 放行后 ✅ |
| bootargs | `root=/dev/nfs nfsroot=192.168.50.5:<out树>,vers=3,tcp ip=192.168.50.99:192.168.50.5::255.255.255.0::eth0:off rw`（直连无网关，gw 留空） |
| 镜像 | `update-nfsroot-static-20261031.img`（`6b118094`），已落 C 盘烧录位；**真板 `VFS: Mounted root (nfs filesystem)` 待验** |
| 基建复利 | nfsd（rootfs 导出）+ tftpd-hpa（`out/.../tftpboot`）+ 直连静态段——后续 U-Boot `tftp + bootm` 免烧录换内核 |

## 1. 架构决策：为什么导出 out 树而不是 /srv/nfs

第一版方案是教科书式 `/srv/nfs/rk3588-scratch`，被自己推翻：要多一个 root 目录（sudo）、
和 forge 打包源树形成**双宿主**（NFS 视角和烧录内容迟早漂移）。改为直接导出
`out/rk3588-topeet/rootfs`——它就是 `rootfs.ext4`/`update.img` 的打包源树：

```text
同一棵树 ──mke2fs──→ rootfs.ext4 ──→ update.img ──烧录──→ 板上 /
   └────────────────nfsd 导出────────────────→ 板上 NFS root
```

「合并校验」当场实证：`md5sum out/.../rootfs/bin/busybox` = `debugfs -R 'cat
/bin/busybox' rootfs.ext4 | md5sum` = `f8bf5254`。开发改树、`forge pack` 出镜像、
NFS 板上跑的，永远是同一份内容。

## 2. 两颗构建雷（差点烧了旧内核）

**雷 1：series 尾部补丁是裸 diff。** `0023-virtio-mmio-*`（sim 线遗产）缺
format-patch 邮件头，`git apply --check` 能过（它不挑头）、`git am` 直接
"Patch format detection failed"——21/21 处失败整树回滚。更阴的是 `forge all`
退出码仍是 0：**内核没编，out 里的 boot.img 还是旧的**。全链静态自检
（合并 .config、ext4 内 boot.scr、产物时间戳）拦住了「拿旧内核当新的烧」。
修法：补上与邻居一致的 `From/Date/Subject` 头。

**雷 2：RK3588 gmac 地址记反。** 按 RK3568 直觉认定 fe1b0000=GMAC1，看日志
「怎么起的是 gmac1？」怀疑 DT 错——查树内 `rk3588-extra.dtsi` 才钉死：
**RK3588 gmac0=fe1b0000、gmac1=fe1c0000**，日志和 DT 完全一致，虚惊一场。
教训：SoC 级事实只认在树 dtsi，不认记忆。

## 3. 第一次烧录卡死：console 瞎 ≠ 内核死

烧 DHCP 版镜像，串口停在 1.79s 且**半行截断**（`counters` 后无下文）。三个证据
指向 ttyFIQ0 console 自己夭折、内核可能还活着：`could not install nmi irq
handler`（278 行）、更早就有乱码行（362 行）、死在半行字上。PHY/链路/DHCP 的日志
全落在死区里——**盲飞状态，换手段**。

## 4. U-Boot 分层排查法（本次最有复用价值的一段）

不碰内核，纯 bootloader 层把链路一层层剥开：

```text
U-Boot dhcp   → PHY 自协商 done、BOOTP 7 连无应答   → 物理层✅，DHCP❌
ipconfig      → PC 有线口 169.254.95.17 (APIPA)     → 直连！链路通但无 DHCP 服务器
静态 50 段    → ping .50.5 仍失败，但无 ARP retry    → ARP 已通、ICMP 被拦
Windows arp -a→ 板 MAC 66:50:1b:af:7e:d2 动态条目    → L2 双向实锤
tftpd + tftp  → 8 字节 TFTP-OK 落内存               → UDP 数据面全通，NFS 把握 99%
```

两条环境事实顺手钉死：**mirrored 模式下 WSL 的 `ip neigh` 不可信，Windows 侧
`arp -a` 才是权威邻居表**；**Windows 把未识别网络（APIPA）归为公用配置文件，
默认拦入站 ICMP——这是策略不是故障**（且不拦 TFTP/NFS 业务端口，实测为证）。
放行探针：`netsh advfirewall firewall add rule name="ICMP-in-50"
protocol=icmpv4:8,any dir=in action=allow remoteip=192.168.50.0/24`。

## 5. 修法与产物

直连段没有 DHCP 就不用 DHCP：bootargs 换 `ip=` 静态七段语法
（`<client>:<server>:<gw>:<mask>:<host>:<dev>:<autoconf>`，直连无网关 gw 空、
autoconf=off），`nfsroot` 指向 192.168.50.5。`forge pack + assemble` 重打——
kernel.config 没变，内容哈希正确跳过内核重编，只重生 rootfs.ext4 里的
boot.scr（pack-emmc 每次 pack 都从 `fit/boot-emmc.cmd` 重生，改源即生效）。

## 6. 基建沉淀（全部在位，后续复用）

| 组件 | 落点 | 用途 |
|---|---|---|
| nfsd | 导出 `out/rk3588-topeet/rootfs`（no_root_squash,insecure） | NFS root 本体 |
| tftpd-hpa | `out/rk3588-topeet/tftpboot`（`--secure --verbose`） | 外围链路探针 + 未来免烧录换内核 |
| 直连静态段 | 板 .99 ↔ PC .5（Windows 静止 IP + mirrored） | 烧板都不用的调试通道 |
| ICMP 规则 | `ICMP-in-50`（限 50.0/24） | ping 探针放行 |

未来免烧录内核迭代（待写进 boot.scr 的 tftpboot 分支）：
`tftp 0x08000000 192.168.50.5:boot.img && bootm 0x08000000`。

## 7. 遗留

- 真板 NFS root 起机验证（`VFS: Mounted root (nfs filesystem)`）——镜像在手待烧
- console 半行截断未根治：若下轮仍盲，bootargs 加 `keep_bootcon` 保住 8250
  earlycon 兜底；FIQ debugger 的 NMI 安装失败值得单独开课题
- `ip=dhcp` 路径（经路由器）未在本板复验——bootargs 注释里留了两种形态
- 教学挂接：本课题即 3568 卷一第 4 章「NFS root 迭代引擎」的 3588 侧实操首验，
  素材挂 `document/planning/rk3588/01-platform-boot.md` 时机待课程化

取证：[logs/rk3588/nfs/1.txt](../logs/rk3588/nfs/1.txt)（DHCP 版卡死全程串口）、
U-Boot 排查输出（本文 §4 转录）。
