# 65 — sim 资产 Python 化：Windows 一等公民（2026-08-25）

> 用户对 `boot-smoke.sh` 的批评一针见血：仓库的历史就是 bash→Python 迁移
> （scripts/*.sh 被亲手删除），Discussion #7 又把 Windows 横向复现定为组织级
> 方向——在 sim 线上新造 shell 脚本是方向性错误。全部转 Python（纯标准库），
> shell 版删除。

## 0. 结论

| 项 | 结果 |
|---|---|
| build-initramfs.py | 纯 Python cpio(newc) 写出：**不再依赖 fakeroot/cpio**（设备节点直接写元数据，无权限问题），mtime=0 + 条目排序 = 确定性输出，Windows 原生可跑 |
| boot-smoke.py | 五模式（smoke/board/rootfs/uboot/virt）+ 断言全 Python；交互喂命令用 **stdin PIPE + 写线程**替代 fifo（fifo 也是 POSIX 专属） |
| 验证 | 五模式全 PASS；cpio 归档核对（`crw 5,1 dev/console` 真节点、`lib64→lib`、369 条目、8.3M） |

## 1. 纯 Python cpio 的关键点

newc 头 = `"070701"` + 13 个 8 位十六进制字段 + NUL 结尾文件名（4 字节对齐）
+ 数据（4 对齐）+ `TRAILER!!!`。设备节点只是元数据（S_IFCHR + rmaj/rmin），
根本不需要 root——fakeroot 那套（mknod 和 cpio 必须同一会话、stage 拷贝丢
设备节点）在 Python 版里整个问题类别消失。这同时是 [59 号笔记](59-2026-08-24-rk3568-qemu-sim-m0-day0.md)
里三个坑中两个的根治。

## 2. 教训（记入纪律）

- 本 session 被 shell 坑了四次（zsh 不做词切分、`set -u` 撞未初始化变量、
  `pkill -f` 自匹配、`tail -1` 吞编译错误）——每次都是「在 shell 里缝补」的
  姿势本身带来的。
- rk-forge 的纪律从此明确：**新工具一律 Python 纯标准库，跨平台优先；
  编辑文件用正经编辑工具，别用脚本打补丁。**

## 3. 复现

```bash
python3 boards/rk3568-atk/sim/boot-smoke.py              # 交互直入 U-Boot（零参数零环境变量）
python3 boards/rk3568-atk/sim/boot-smoke.py uboot --check  # 冒烟断言（CI 形态）
```

（同日按用户反馈二次反转 CLI：默认 = 交互直入，`--check` 才是断言形态；
QEMU 自动发现本地 build 优先、PATH 兜底——不再要求用户传 QEMU=。五模式重测全绿。）

用户首次交互实测又揪出两层 bug，同日修复：
1. `/init` 兜底行 `exec setsid cttyhack /bin/sh` 双重失效——buildroot 把 setsid
   放在 usr/bin（原打包未含），cttyhack 干脆没编。`--check` 从不触达此行
   （rk.smoke 提前 poweroff），是典型的「冒烟绿 ≠ 路径全通」。改裸 `exec /bin/sh`
   （rootfs 模式同款姿势，job control 警告无害）。
2. 修 1 时顺手整包 usr/bin+usr/sbin（20MB）引爆隐藏地雷：uboot 模式下内核只见
   190MB（U-Boot 的 192MB 改写），解包期内存压力 → `Initramfs unpacking failed:
   write error`（短写）；linux 模式看满 1G 同包无恙——差分定位。/init 不再需要
   usr 后整块撤除，回到 8.3M。遗留课题真解：让 U-Boot 知道真实 DRAM 大小。

补记（2026-08-26，rk3588 交互实测）：`clear: not found` 暴露同类缺口——busybox
的 clear/vi/top 等 applet 装在 usr/bin。零成本正解：**只摘指向 busybox 的符号
链接**（本体 /bin/busybox 已在包内，每个链接几十字节；当年膨胀是因为连真
二进制一起抄）。108 个链接 +1KB，guest 实测 `command -v clear vi top` 全中。
