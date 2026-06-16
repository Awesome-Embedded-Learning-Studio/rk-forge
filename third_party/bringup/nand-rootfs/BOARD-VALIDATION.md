# 板上验证手册(每次上板照此跑)

> **用途**:RK3506B「aes」板每次烧录/改驱动后,按此从烧录 → 各启动阶段现象 → RW 持久化,逐项核对。
> 本文是"每次验证"的标准清单。当前验证目标:**主线 SFC 驱动移植 powergood + WPEN 后,RW UBIFS 能否跨冷重启持久**(详见 [RW-WRITE-FIX-powergood-wpen.md](RW-WRITE-FIX-powergood-wpen.md))。
> 抓到的 boot 日志存到 `third_party/logs/boot-sdl-<YYYYMMDDHHMM>.txt` 再发我判读。

---

## 0. 文件清单(本次烧录用)

| 角色 | 路径 | 说明 |
|---|---|---|
| **整包(推荐)** | `D:\DownloadFromInternet\update-nand-powergood-wpen-fix.img` | RKFW 整包 = loader + uboot + boot(新内核) + rootfs,升级固件一键烧 |
| 或 loader | `third_party/bringup/vendor-loader-fromSDK.bin` | rkbin loader(4762d6),下载镜像模式的 Loader 槽 |
| 或 parameter | `third_party/bringup/parameter-nand-aes.txt` | 分区表 |
| 或 uboot | `third_party/bringup/out/uboot.img` | 主线 U-Boot FIT |
| 或 boot | `third_party/bringup/out/boot-nand.img` | **新内核(含 powergood+WPEN),7.36MB** |
| 或 rootfs | `third_party/bringup/out/rootfs.ubi.img` | busybox UBIFS rootfs |

分区表(parameter)布局:`uboot@0x2000 / boot@0xBA00(16MB) / rootfs@0x13A00 / userdata(grow)`。

---

## 1. 进 MaskROM + 烧录

### 进 MaskROM(下载模式)
断电 → 按住板载 **VOL+/Recovery** 键(或短接 MaskROM 引脚)→ 插 USB 上电 → 松开。RKDevTool 底部应显示 **「发现一个 MASKROM 设备」**。
(已烧过 loader 的板,也可用「升级固件」自动 reboot 到 MaskROM。)

### 方式 A —— 升级固件(整包,推荐首测)
1. RKDevTool 切到 **「升级固件」** 页。
2. 勾选固件,浏览选 `update-nand-powergood-wpen-fix.img`。
3. 点 **「升级」**。流程:下载 loader → 烧各分区 → **「升级完成 DONE」**。
4. 断电、拔按住键、重新上电,从串口抓 boot 日志。

### 方式 B —— 下载镜像(分区,逐步/排查用)
切到 **「下载镜像」** 页,先烧 parameter 再勾分区(只勾要刷的):

| 槽位 | 文件 | 说明 |
|---|---|---|
| **Loader**(单独按钮「…」) | `vendor-loader-fromSDK.bin` | 点一次「下载」烧 loader |
| parameter(勾) | `parameter-nand-aes.txt` | 分区表 |
| uboot(勾) | `out/uboot.img` | |
| boot(勾) | `out/boot-nand.img` | 新内核 |
| rootfs(勾) | `out/rootfs.ubi.img` | |

> 只换内核排查时:Loader+parameter 不勾,**只勾 boot** 烧 `boot-nand.img` 即可(分区偏移不变)。
> 砖/改分区表恢复:全部勾 + 先「擦除 Flash」。

> Linux 烧(可选):`rkdeveloptool db vendor-loader-fromSDK.bin; rkdeveloptool uf update-nand-powergood-wpen-fix.img`。

---

## 2. 期望现象 —— 逐启动阶段(抓串口日志逐行核对)

### 阶段 ① SPL / loader(rkbin,DDR+SPL)
```
DDR d27ac532c4 ... fwver: v1.06        ← DDR v1.06
...
DDR3, 750MHz
BW=16 Col=10 Bk=8 CS0 Row=15 CS=1 Size=512MB
out
U-Boot SPL 2017.09-g26c8833 #alientek ...
sfc cmd=03H(6BH-x4)
SPI Nand ID ef aa 23                    ← W25N04KV id
...
## Checking optee 0x00001000 ... sha256(93603ca22c...) + OK   ← tee 必 v2.10
## Checking uboot 0x00800000 ... sha256(...) + OK
## Checking fdt ... sha256(...) + OK
Jumping to U-Boot(0x00800000) via OP-TEE(0x00001000)
```
**异常**:`optee Bad hash` → tee 版本错(必须 v2.10);`SPI Nand ID` 非 `ef aa 23` → SFC/flash 没认。

### 阶段 ② OP-TEE → U-Boot proper
```
I/TC: OP-TEE version: 3.13.0 ... fwver: v2.10
U-Boot 2026.07-rc4-gff4b08b5... (Jun 16 2026 ...)    ← 主线 U-Boot
Model: Rockchip RK3506 Evaluation Board (ATK RK3506B)
SoC:   RK3506B
DRAM:  512 MiB
...
Hit any key to stop autoboot: 0
Scanning for bootflows in all bootdevs ...
(0 bootflows, 0 valid)            ← 正常:bootflow 不认 MTD,落 => 提示符
=> 
```
**异常**:U-Boot banner 是 `2017.09 #alientek` 而非 `2026.07-rc4` → 烧错 uboot(残留 vendor)。

### 阶段 ③ 手动引导内核(关键!每次重启都要做)

> **U-Boot env 是 `nowhere`(无持久存储),`saveenv` 不存。每次冷重启后都会落到 `=>`,必须手动 boot。**
> **当前内核 FIT = 7.36MB,`mtd read` 必须读 0x800000(8MB);读 0x600000(6MB)会截断 FIT → kernel 损坏,会伪装成"写损坏"!**

在 `=>` 提示符**逐行粘贴**这 3 条:
```
setenv bootargs 'earlycon=uart8250,mmio32,0xff0a0000 console=ttyS0,1500000 ubi.mtd=5 root=ubi0:rootfs rootfstype=ubifs rootwait rw'
mtd read boot 0x04000000 0 0x800000
bootm 0x04000000
```
首次 `mtd read` 时会出现 DLL 调谐行(读稳的证据):
```
rockchip_sfc: dll tuning target=50000000Hz real=100000000Hz cell_max=383 step=10 cs=0
rockchip_sfc:   dll window [0, 230] (230 cells)
rockchip_sfc:   dll ok best=[0,230] -> cell 92 ...
Reading 8388608 byte(s) ...
```
然后:
```
## Loading kernel ... Verifying Hash Integrity ... sha256+ OK
## Loading fdt ... Verifying Hash Integrity ... sha256+ OK
Starting kernel ...
```
**异常**:`new format image overwritten` → FIT 暂存地址撞 kernel load(应 0x04000000,见上);sha256 失败 → mtd read 长度不够(检查是 0x800000)。

### 阶段 ④ 内核 → UBIFS → shell
```
[ ... ] Machine model: ... AES RK3506B ...           ← 板名 aes
[ 2.x ] spi-nand ...: Winbond SPI NAND was found.
[ 2.x ] ... 512 MiB, block size: 128 KiB, page size: 2048, OOB size: 128
[ 2.x ] ...Creating ... partitions ... on "spi-nand0"
[ 2.8 ] ubi0: attaching mtd5
[ 3.x ] ubi0: attached mtd5 (name "rootfs", size ...)
[ 3.x ] UBIFS (ubi0:0): Mounting in unauthenticated mode
[ 3.x ] UBIFS (ubi0:0): recovery needed          ← 不洁关机时会出(正常)
[ 3.x ] UBIFS (ubi0:0): recovery completed       ← ★ journal 跨重启可读 = RW 稳的核心证据
[ 3.x ] UBIFS (ubi0:0): mounted UBI device 0, volume 0, name "rootfs"
[ 3.x ] VFS: Mounted root (ubifs filesystem) ...
...
~ #                                            ← 拿到 busybox 交互 shell = 链路全通
```

### ★ 修复生效的判据(全文搜索日志,这些必须**没有**)
```
ubi_io_read error -74 (ECC)         ← 读到不可纠 ECC
-EBADMSG                            ← 同上
UBIFS ... bad magic 0x... vs 0x...  ← 元数据位翻
powergood ... not asserted          ← powergood bit 没置位(本次先非致命,见判读表)
```
**只要阶段④ 走到 `~ #` 且上述错误一个都没有 → powergood+WPEN 生效、读写稳。**

---

## 3. RW 持久化验证(核心 —— 这就是 vendor 在做、saga 在崩的操作)

到 `~ #` 后,连做 **写 + 冷重启** 循环。**注意每次 reboot 后都要重做阶段③ 的 3 条手动 boot。**

```bash
# 第 1 次进 ~# 后:
echo "cycle-1 $(awk -F. '{print $1}' /proc/uptime)" >> /persist.log
sync
reboot -f                  # 冷重启 → 会落回 U-Boot =>

# (阶段③ 粘贴 3 条手动 boot → 再次到 ~#)
cat /persist.log           # 期望:有 cycle-1 这行(旧 saga 这里就崩/丢)
echo "cycle-2 $(awk -F. '{print $1}' /proc/uptime)" >> /persist.log
sync
reboot -f
# ... 重复到 cycle-3/4/5
```

**最少做 3 轮(写+重启+读);vendor 稳、saga 崩,所以哪怕 1 轮存活就是强信号,3~5 轮存活即定论。**

最后一轮到 `~#` 后,把这两条输出抓给我:
```bash
cat /persist.log
dmesg | grep -iE "ecc|ebadmsg|ubi_io_read|powergood|bad magic|recovery"
```

---

## 4. 判读表(结果 → 含义 → 下一步)

| 现象 | 含义 | 下一步 |
|---|---|---|
| `cat /persist.log` 有 cycle-1..N 全在 + `dmesg` 0 ECC 错 + `recovery completed` | **✅ RW 达成。powergood+WPEN 是根因解。** | 我把 powergood 非致命→致命(对齐 vendor)、重生 patches、清探针 |
| `/persist.log` 全在,但 dmesg 有 `powergood ... not asserted` 刷屏 | powergood bit 在本板不置位;靠 WPEN 单独保住读写 | powergood 不是机制,移除它只留 WPEN;或查 GRF_PMU+0x100 真实含义 |
| `/persist.log` 丢行 / `ubi_io_read -74` / `bad magic` | 写路径仍边际(powergood+WPEN 不够) | 下一步:U-Boot 100MHz clk 修到 50MHz + Linux 写后校验兜底;再不行查真电气 |
| 阶段④ 根本没到(`ubi0: attaching` 卡/挂) | loader 烧的 rootfs 初次读就炸 | 先确认阶段③ mtd read 是 0x800000;再考虑 rootfs 由 Linux 落盘(不让 loader 写) |
| 阶段③ sha256 fail / `image overwritten` | 引导命令错(不是写问题) | 核对 bootargs / 0x04000000 / 0x800000 三处 |

---

## 5. 抓日志约定(给我判读用)
- 串口全程抓到 `third_party/logs/boot-sdl-<YYYYMMDDHHMM>.txt`(从上电 SPL 到 `~#`)。
- RW 测试轮的 `cat /persist.log` + 那条 `dmesg|grep` 单独贴。
- 文件名带时间,别覆盖旧 log。

---

## 附:想要自动 boot(免去每次手动引导)
当前 env=nowhere,`saveenv` 不存。若要冷重启自动引导,二选一:
1. 重建 U-Boot 时 `CONFIG_USE_BOOTCOMMAND=y` + `CONFIG_BOOTCOMMAND="mtd read boot 0x04000000 0 0x800000; bootm 0x04000000"`(我可以加)。
2. 给 U-Boot 配 MTD env(`CONFIG_ENV_IS_IN_MTD`,rootfs 之外的扇区),`saveenv` 持久。
本次验证**不依赖**自动 boot,手动引导即可。
