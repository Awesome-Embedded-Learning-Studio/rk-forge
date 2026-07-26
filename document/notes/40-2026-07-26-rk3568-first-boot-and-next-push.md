# RK3568 首次真机 boot 成功 (2026-07-26) + 下一步梭哈

## ✅ 成功:Linux 7.1.0 主线 boot 到 login

2026-07-26,RK3568 ATK 板真机 boot 成功 —— forge 主线 kernel **7.1.0** + u-boot **2026.07-rc4** + buildroot rootfs,从 BootROM 一路到 busybox **login prompt**。MVP 真机验证完成。

### boot 链(全链路真机确认)
```
BootROM → DDR init (vendor blob, 1560MHz, 4GiB)
  → idbloader @0x40 (binman, mainline)
  → SPL (vendor rk356x_spl v1.14, 2017.09 — rkbin blob, NOT mainline)
  → ATF BL31 (rkbin v1.46, v2.3-948)   [OPTEE 省略, 无害 warning]
  → U-Boot 2026.07-rc4+43 (主线, evb1-v10 DT)
  → bootm FIT (手动: mmc dev 0 + mmc read 0x08000000 + bootm)
  → Linux 7.1.0 (主线 v7.1, gcc 15.3.1, SMP PREEMPT, 4 CPU)
  → mmc1 HS200 eMMC (mmcblk1, C9A611 58.3GiB, p1/p2/p3)
  → EXT4 mount mmcblk1p3 → busybox init → login
```

### 关键产物版本
- **kernel**: Linux 7.1.0 (主线 v7.1 正式版 2026-06-14, `Linux version 7.1.0 ... #2 SMP PREEMPT`)
- **u-boot**: 2026.07-rc4-00043-g5ca1a73c7d30 (主线)
- **eMMC**: HS200 ES 1.8V, 58.3GiB, GPT p1(uboot)/p2(boot)/p3(rootfs 1GiB)
- **rootfs**: buildroot 2026.08-git ext4 (Phase 2a — 但当前是 Qt5 时期 buildroot, 见下)

### 本次 debug 的关键修复
1. **boot.scr 入口**: u-boot `bootcmd=bootflow scan`,但 eMMC boot 分区是 **raw FIT**(非文件系统),bootflow 找不到入口 → 补 boot.scr 放 **rootfs /boot/**(SCRIPT bootmeth 命中 rootfs 分区)。
2. **FIT 地址重叠** ⚠: boot.scr 最初 `mmc read ${kernel_addr_r}`(0x02000000),但 FIT 的 kernel load address 也是 0x02000000 → bootm 报 `new format image overwritten`。改 FIT 读到 **0x08000000**(空闲 DRAM, 避开 kernel load 0x02000000 + fdt 0x12000000),bootm 把 kernel 搬到 0x02000000 不覆盖 FIT。
3. **eMMC 分区 resize**: Phase 2a rootfs 451M 装不下原 256M/512MiB。`parameter-emmc-atk.txt` rootfs `0x00100000→0x00200000`(512MiB→1GiB) + `pack-emmc.sh` `ROOTFS_MIB 256→1024`。
4. **eMMC dev 号**: u-boot `mmc@fe2b0000`=dev 1(sdmmc0, SD), `mmc@fe310000`=dev 0(**sdhci = eMMC**)。eMMC 是 dev 0!(曾一度搞反, `rk3568.dtsi` sdmmc0=dwmmc@fe2b0000 / sdhci=sdhci@fe310000)。
5. **当前手动 boot**(bootflow dev 0 不扫 partition, 见下): `mmc dev 0; mmc read 0x08000000 0x6000 0x20000; setenv bootargs console=ttyS2,115200 root=/dev/mmcblk1p3 rw rootwait; bootm 0x08000000`。

## ⚠ 当前剩余问题(2026-07-26 板上实测)

| 问题 | 根因 | 修复方向 |
|---|---|---|
| **网络只有 lo**(无 eth0/eth1) | `CONFIG_STMMAC_ETH=m` `CONFIG_DWMAC_ROCKCHIP=m`(**模块**, rootfs 没装/没 modprobe) → dmesg 一行 eth 都没有 | kernel.config 改 `=y`(built-in) 重编 kernel |
| **Qt6 没进 rootfs** | 当前 rootfs.tar 是 07-25 buildroot(Qt5 时期), 后来改 Qt6 defconfig **没重跑 buildroot** | 重跑 build-rootfs.sh --reconfigure |
| **bootflow 自动 boot 不通** | u-boot bootflow 对 dev 0(eMMC)**不扫 partition**(主线 bootdev quirk: `mmc dev 0` 手动 OK, bootflow 偏不扫) → 找不到 boot.scr | 改 u-boot `BOOTCOMMAND` 直接 `mmc dev 0; mmc read; bootm`(绕 bootflow) |
| **波特率 1500000** | u-boot CONFIG_BAUDRATE + kernel DT stdout 都 1500000(当前 boot.img 旧 dtb) | 改 115200(u-boot defconfig + kernel DT, 已改待重编) |
| **LCD 不亮** | evb1-v10 用 `raydium,rm67200`(dsi0); ATK 10.1寸 800x1280 MIPI 用 **dsi1 + vendor `panel-init-sequence`**(主线无该 panel driver) | 移植 ATK panel(Phase 2+, 搬 vendor panel driver) |
| **sshd FAIL** | `/var/empty` 权限 | rootfs overlay 修 |
| **GPU/VPU/USB3 deferred probe** | power-domain sync_state pending / dwc3 init fail | 后续(Panfrost/Hantro/dwc3) |

## 下一步:梭哈(一次移植通过)

目标: 一次大重 build(kernel + buildroot + u-boot)+ 重 pack, 出**插电自动 boot → login + 有 eth0 + 有 Qt6 + 115200** 的最终 update.img。

### 改动清单
1. **网络 =y**: `board/rk3568-atk/kernel.config` `STMMAC_ETH/DWMAC_ROCKCHIP/DWC_ETH_QOS` 从 `=m` 改 `=y` + ATK PHY DT(`phy-mode=rgmii` + `rgmii_phy0`, 对照 vendor)
2. **Qt6 真正进 rootfs**: 重跑 `FORGE_BOARD=rk3568-atk scripts/build-rootfs.sh --reconfigure`(Qt6 defconfig 已改, 需确认 host-qt6base 编通)
3. **u-boot 自动 boot + 115200**: `evb-rk3568_defconfig` `CONFIG_BOOTCOMMAND` 改直接 mmc boot(绕 bootflow) + `CONFIG_BAUDRATE=115200`(已改)
4. **kernel DT stdout 115200**(已改 evb1-v10.dts) + **boot.scr 0x08000000**(已改 boot-emmc.cmd)
5. **sshd /var/empty**: rootfs overlay(`/var/empty` root:root 0755)

### 梭哈不含(Phase 2+ 后续)
- **LCD** ATK 10.1寸 800x1280 MIPI: 要移植 vendor `panel-init-sequence` driver(dsi1_panel + rk3568-lcds.dtsi 屏库), 中-大工作量。
- **GPU Panfrost / VPU Hantro / USB3 dwc3**: deferred probe, 后续调。

### 期望结果
烧最终 update.img → 插电 → u-boot 自动 boot(115200 串口看 log) → kernel 7.1 → eth0 up → login(Qt6 库在 rootfs)。LCD/触摸/GPU 加速是再下一轮。

---
参见 [notes/38](38-2026-07-24-rk3568-rootfs-mainline-equivalence.md)(rootfs 等价对照)、[notes/39](39-2026-07-24-qt6webengine-buildroot-port-feasibility.md)(qt6webengine)、MEMORY rk3568-migration-status / rk3568-build-gotchas。
