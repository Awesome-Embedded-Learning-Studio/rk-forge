# 进度笔记：busybox UBIFS rootfs + update.img 链路（2026-06-15）

## ✅ 完成

### 1. busybox UBIFS rootfs 打包链（不重编内核 / 不重编 busybox）
`mk-rootfs.sh` → `pack-ubifs.sh`（W25N04KV `-m 2048 -e 124KiB -c 1400` autoresize）→
`pack-fit.sh`（`boot-nand.img` 无 ramdisk）→ `assemble-update.sh --nand`
（`update-nand.img` = uboot + boot-nand + rootfs）。
- DT bootargs 加 `ubi.mtd=5 root=ubi0:rootfs rootfstype=ubifs rootwait`。
- ★坑：boot FIT 带 ramdisk `/init` → 内核 exec 它、`root=` 被忽略 → 用无 ramdisk 的
  `boot-nand.img` 走真根；`boot.img`（带 initramfs）留 rescue fallback。

### 2. update.img 升级固件"校验芯片失败"修复 ✅ 板上验证
- 根因：`rkImageMaker` chip tag 硬编码 `-RK3506`，但 RK3506B loader 真实标识是 **RK350F**
  （RKBOOT ini `CHIP_NAME=RK350F`）。tag ≠ loader → RKDevTool 校验失败。
- 正解：chip tag 从 loader offset 21 读 4B 反转（vendor `mk-updateimg.sh` 方法）。
  `assemble-update.sh` 改动态读 TAG。修后 RKDevTool 升级固件**烧成功 + idblock 也烧进 forge loader**。
- ★坑：`rockdev/rk3506-mkupdate.sh` 硬编码 `RK3506` 是简化/旧脚本（误导）；
  `device/rockchip/common/scripts/mk-updateimg.sh`（从 loader 读 tag）才是权威。

## 🟡 部分成功：forge loader 进 idblock + kernel 起来了，但 uboot 跑的是 vendor 的

新日志（`logs/boot-sdl-202606152121.txt`）**纠正了旧判断**（旧日志 #alientek 让我以为 idblock 没烧）：

- **idblock 烧进 forge loader 了**：DDR `fwver v1.06` + SPL `#lxh g1e54c433094 Jan 16 2025`
  = forge 的 rkbin SPL。chip tag RK350F 修好后 RKDevTool 确实烧了 idblock + 分区。
- **assemble 没打包错**：`out/uboot.img` = `U-Boot 2026.07-rc4-g66d619c72047 (Jun 15 2026)` + **tee v2.40**
  （源头 `explore/uboot/u-boot-nodtb.bin` 一致）。是 forge 主线，不是 vendor_sdk。
- **但加载的 U-Boot proper = vendor**：`2017.09-g26c8833 #alientek (Mar 26 2026)` + **tee v2.10**。

**根因：rkbin SPL（forge loader）verified boot 锁 vendor uboot+tee**
| rkbin SPL 试 | 内容 | 结果 |
|---|---|---|
| `0x2000 sector` | assemble 烧的 forge uboot（主线 + tee **v2.40**） | optee **Bad hash**（rkbin 内嵌 vendor tee **v2.10** 期望）→ 拒绝 |
| `0x3000 sector` | 残留 vendor uboot（tee v2.10） | hash OK → 加载 vendor U-Boot |

- forge uboot 只 595KB（1190 sector），从 0x2000 起够不到 0x3000，**残留 vendor uboot 没被覆盖**，rkbin SPL 回退捡到它。
- rkbin SPL 是 vendor 编译的，verified boot 内嵌 vendor uboot+tee(v2.10) hash；forge 主线 uboot(v2.40) 被拒。**这是 forge loader（用 rkbin SPL）的固有限制，不是 assemble 打包错。**

**但 boot/rootfs 是 forge 的，kernel 起来了**：
- `boot-nand.img`（forge kernel + fdt `RK3506B AES ... ubi.mtd=5 root=ubi0:rootfs`）✓
- vendor U-Boot autoboot 它 → `Starting kernel ...` ✓（日志 line 197，截断在此）
- 离持久 rootfs boot 只差 kernel 后续 mount UBIFS。

## ▶ 下一步

1. **抓 kernel 启动后续日志**（Starting kernel 之后），看 `ubi.mtd=5` / `root=ubi0:rootfs`
   是否 attach UBI + mount UBIFS → busybox init → shell。这是 rootfs 持久化的最终验证。
2. **uboot 全主线化（长期/可选）**：rkbin SPL verified boot 锁 vendor uboot，要用主线 U-Boot
   proper 需 idblock 换主线 U-Boot SPL（非 rkbin），或找到关闭 verified boot 的方式。
   当前可用配置：idblock=forge loader(rkbin SPL) + uboot=vendor + boot/rootfs=forge。

## 诊断方法备忘
- **区分 idblock 来源**：比 SPL banner（`#alientek` vs `#lxh`）+ git hash + 编译日期 + DDR fwver
  （v1.04=vendor 旧 / v1.06=forge）。`strings <loader> | grep -iE 'U-Boot SPL|alientek|lxh'`。
- **rkbin SPL verified boot**：会试多个 FIT sector，选 hash 匹配的；vendor uboot+tee(v2.10) 是
  它认的。forge uboot(主线)+tee(v2.40) hash 不匹配会被跳过。
- assemble 回程自检只验 parameter/uboot/boot/rootfs 在位 + 大小，**没验 uboot 实际是主线还是 vendor**（pack-fit 源头要对）。
