# 18 — forge 板上验证 playbook（构建→烧→引导→读/trace/RW）

> 每次代码改动上板验证的标准流程。Claude 跑本地（构建/打包/拷贝），用户跑 Windows 物理侧（烧录/UART）。

## 1. 构建（Claude 自己 Bash，见 [[self-run-build-and-copy]]）
```bash
scripts/build-linux.sh                    # 重编内核（慢，分钟级）
scripts/pack-fit.sh                       # 重打 boot.img（FIT: zImage+dtb+initramfs）
scripts/assemble-update.sh --provision    # 打 update.img（loader+uboot+boot+rootfs）
cp board/aes/out/update.img /mnt/d/DownloadFromInternet/<name>.img
```
- 只改 DT：`build-linux.sh --just-dtb`（快，不重编内核）+ pack-fit + assemble
- 只改 core.c/驱动：`build-linux.sh`（重编 .o）
- assemble 变体：`--provision`（ubiprog 首启，标准 RW）/ `--nand`（直挂，对照会炸 ECC）/ `--rescue`（initramfs shell）
- `--loader <path>` 覆盖 loader（默认 `out/MiniLoaderAll.bin`）

## 2. 烧录（Windows RKDevTool，用户）
- **maskrom 模式**烧 update.img —— 确保 idb 区被写成镜像里的公开 loader
- ⚠ 升级固件模式可能只刷分区、不写 idb（idb 残留旧 loader → 启动行为错乱，见 notes/14 alientek loader 教训）。出怪先怀疑 idb 没刷。

## 3. 引导（env nowhere，每次手动 3 行）
U-Boot 倒计时按回车停 `=>`：
```
=> setenv bootargs 'console=ttyS0,1500000'
=> mtd read boot 0x04000000 0 0x1000000
=> bootm 0x04000000
```
- 别带 `root=/ubi.mtd=`（否则内核自己挂 rootfs，/init 不跑，ubiprog 不首启）
- console **必须带波特率** `1500000`（RK DW 8250 通病，不带会"看似卡死"实则波特率不对）

## 4. U-Boot 读 NAND（验证 loader 写 / ECC / RAW）
```
=> mtd list                                                  # 确认 master spi-nand0 + boot 分区
=> mtd read spi-nand0 0x04100000 <chip_offset> 0x20000       # ECC 读（chip 绝对偏移）
=> md.b 0x04100000 0x40
=> mtd read.raw spi-nand0 0x04200000 <chip_offset> 0x20000   # RAW 读（绕 on-die ECC，看物理 flip）
=> md.b 0x04200000 0x40
```
- rootfs PEB 偏移 = `rootfs偏移(0x2740000) + PEB×0x20000`：PEB3=`0x27A0000`、PEB4=`0x27C0000`
- mtdparts 只有 boot 分区，用 master `spi-nand0` + chip 绝对偏移读 rootfs（U-Boot `mtd read` 支持 master 设备 + 绝对偏移）
- RAM 缓冲 `0x04100000`/`0x04200000`（避开 kernel load `0x04000000`）

## 5. RW 跨冷重启验证（provision 后）
busybox 里：
```
echo "<marker>" >> /persist.log; sync; reboot -f
```
reboot 再引导 → `cat /persist.log`（应含 marker，跨冷重启存活）+ dmesg 看 `[init] already provisioned → switch_root`（marker 门控，ubiprog 只首启一次）+ `UBIFS recovery completed`

## 6. trace 上板（SPI-NAND ECC 诊断）
见 [16](16-2026-06-18-spinand-ecc-diagnosis-playbook.md)。加 trace → build-linux + pack-fit + assemble + cp + 烧 + 引导，串口/dmesg 看 `spinand_rd eb=X pg=Y st=0xZZ`。

## 7. 判读速查
| 看哪 | 期望（正常）| 异常含义 |
|---|---|---|
| SPL banner `#lxh v1.12`（公开 loader）| 公开 | `#alientek` = idb 没刷（maskrom 重烧）|
| `dll ok best=[90,170] -> cell 130`（80MHz）| DLL 成功 | `dll FAIL wid=[0,0]` = 该频率 PLL tap 不行 |
| ubiprog `peb=3/4 ... recovery` | loader 弱写兜底（预期）| 别当 bug |
| `[init] already provisioned → switch_root` | marker 跨重启 | 每次都 FIRST BOOT = marker 没持久 |
| `UBIFS recovery completed` | rootfs 跨重启正常 | panic = rootfs 坏 |

## 相关
[16](16-2026-06-18-spinand-ecc-diagnosis-playbook.md)（ECC 诊断）/ [17](17-2026-06-18-patch-solidification-sop.md)（patch 固化）/ 记忆 [[flash-and-verify-runbook]]（canonical）/ [[self-run-build-and-copy]]
