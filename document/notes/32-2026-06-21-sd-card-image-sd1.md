# 32 — SD 卡启动镜像打包(SD-1:手动引导到 shell)

**日期**:2026-06-21  
**阶段**:SD 卡启动镜像打包里程碑 SD-1(并行于 NAND,非替代——开发/恢复第二条启动路径)

## 背景 / 为什么做

forge 此前只产 SPI-NAND 的 `update.img`(板子主路径,已全闭环板验)。用户指示开 SD 卡阶段。SD 是独立的第二条启动媒体。

## ★★ 重要修正(板验反馈,2026-06-21):本板 SD 必须用 RKFW,裸 dd 镜像 ROM 不认

用户实测:**RK3506B 板子的 ROM 只认经 Rockchip SD 工具(RKDevTool/SD Firmware Tool)写出的 SD 卡,裸 dd 的 `sd.img` 插上"不认"**。所以 SD 的真正交付件是 **RKFW 格式的 `update-sd.img`**(和 NAND `update.img`、vendor `rk3506b_update_sd.img` 同构),不是裸镜像。

证据链:
- vendor `third_party/rk3506b_update_sd.img` 开头魔数 = **`RKFW`**(Rockchip Firmware 统一更新容器),和我们 NAND `update.img`(rkfw-pack.py 产)**完全同格式**。RK 工具只认 RKFW → 我们的裸 `sd.img`(protective MBR 开头)被"打开失败"。
- 拆开 vendor update_sd.img(rkfw-pack.py unpack):parameter(GPT)+ loader + uboot/boot/rootfs 分区镜像。`vendor_sdcard_log.txt` 证明这种 RKFW 经 RK 工具写出的 SD **能直接启动到 Linux**(root 在 mmcblk0p6)。
- 结论:RK 工具把 RKFW 转成可启动 SD(写 idblock@0x40 + 各分区镜像到 GPT)。

→ **SD 交付件 = `update-sd.img`(RKFW),`forge assemble --sd` 产**。裸 `sd.img`(pack-sd.sh)降为次选/副产品(给能认裸镜像的板子 dd/Etcher 用;本板用不上,但 pack-sd 仍需跑——它产 RKFW 要的 `rootfs.ext4`)。

## SD 启动协议(关键发现,来自 vendor_sdcard_log.txt + 构建配置双证)

不是猜的——**两处独立证据**确认了协议:

1. **vendor SD 启动 log**(`document/logs/vendor_sdcard_log.txt`):板子从 SD 启动,SPL 打印 `Trying fit image at 0x2000 sector` → 从 SD **sector 0x2000(4MiB)** 读 uboot FIT(optee+uboot+fdt)。
2. **主线 U-Boot defconfig**(`third_party/src/uboot/configs/evb-rk3506_defconfig:16`):`CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_SECTOR=0x2000` —— **硬编码** SPL 从 MMC sector 0x2000 读 U-Boot。

启动链:BootROM 读 SD **sector 64(0x40)** 的 idblock → DDR init + SPL(rkbin blob,同 NAND 源)→ SPL 从 sector 0x2000 加载 uboot FIT → OP-TEE → U-Boot → U-Boot 加载 kernel FIT → Linux 挂 **ext4** rootfs(mmcblk0pN)。

## 重要纠正:旧记忆 "SD 用 idbloader(非 rkbin 拼装)" 对 RK3506 不成立

`sd-card-image-next-phase` 记忆原先设想 SD 用主线 `idbloader.img`(`mkimage -T rksd` 拼 TPL+SPL),不走 rkbin。**这对 RK3506 不可能**——DDR init 是 rkbin blob(无开源 TPL,见 BLOBS.md),SD idblock **必须**是同一 rkbin idblock(boot_merger 产,DDR+usbplug+SPL)。SD 与 NAND 用**完全相同的 idblock + uboot.img**。板验后回写记忆。

## 复用 map(SD 几乎全复用 NAND 产物,只换 layout)

| SD 组件 | 来源 | 改动 |
|---|---|---|
| idblock | `pack-loader.sh`(boot_merger 已产 `idblock.img`) | 新增捕获到 out/(原本只拷 MiniLoaderAll.bin) |
| uboot.img | `pack-fit.sh` Mode A | 直接复用 |
| kernel boot.img | `pack-fit.sh` Mode B | 直接复用(媒体无关) |
| rootfs | `stage-rootfs.sh` 的 `out/rootfs` 树 | 新增:做 ext4(非 UBIFS) |

## 关键设计点:为什么 boot.img 是裸存而非 ext4 boot 分区

evb-rk3506 defconfig **极简**:有 `CONFIG_CMD_MMC` + `CONFIG_CMD_GPT` + `CONFIG_CMD_BOOTM`,但**无 ext4/FAT/load/fs 通用命令**(NAND 走 `mtd read` 裸读,不需要 FS)。所以:
- boot.img **裸存**于固定 sector,U-Boot 用 `mmc read` 裸读(同 NAND 的 `mtd read` 哲学)。
- rootfs 是 GPT 分区(ext4),由 **kernel** 挂(`root=/dev/mmcblk0p1`)——U-Boot 不需要 ext4 驱动。

→ SD-1 零 U-Boot 改动(用户选择"先手动引导")。

## SD layout(`pack-sd.sh`)

```
sector    0-33      GPT primary
sector    64 (0x40) idblock        (raw)
sector    8192 (0x2000) uboot.img  (raw; SPL 读此)
sector    16384 (0x4000) boot.img  (raw; U-Boot mmc read)
sector    65536 (0x10000) GPT p1 rootfs (ext4 256MiB)
[backup GPT @ tail]
```
- 32MiB 头区装 idblock+uboot+boot.img(~19MiB 用,留 headroom)。
- p1 固定 256MiB ext4;板上 `resize2fs /dev/mmcblk0p1` 可扩到卡满。
- **root-free 拼装**:不用 losetup/mount(免 sudo)——每分区用 `mke2fs -d` 从目录填充成独立 ext4,再 `dd` 进 sd.img 偏移;sgdisk 直接对镜像文件写 GPT。

## 纯 SD boot(boot-sd.img,无 ramdisk 变体)

板验 boot-sdl-202606210958 暴露:原 SD 用 `boot.img`(带 provisioning initramfs)→ kernel 优先跑 `/init` → attach NAND ubi0:rootfs → switch_root 到 **NAND** rootfs(cmdline 的 `root=/dev/mmcblk0p3` 被拦截)。SD ext4(mmcblk0p3)枚举了但没当根挂。= 混合启动(kernel 从 SD、rootfs 从 NAND)。

修:`boot-sd.img`——**无 ramdisk 的 kernel FIT**(zImage+dtb,类 boot-nand.img 但 SD 版)。无 `/init` 拦截 → kernel 按 `root=/dev/mmcblk0p3` 挂 SD ext4 rootfs。`assemble --sd` 现用 boot-sd.img(pack-fit.sh 加第 4 个 FIT `rk3506-kernel-sd.its`)。FIT 本身媒体无关(与 boot-nand.img 同结构:zImage+dtb 无 ramdisk),差别只在 U-Boot setenv 的 bootargs(NAND:ubi0:rootfs / SD:mmcblk0p3);独立一份只为命名诚实。

验证(mkimage -l):boot-sd.img 只有 kernel+fdt 无 ramdisk;update-sd.img 里的 boot 分区镜像 ramdisk 计数=0。新 update-sd.img md5 **7768cd4c**(`/mnt/d/.../update-sd-rkfw-puresd-20260621.img`)。**待板验**:kernel 该直接挂 mmcblk0p3 → SD ext4 rootfs。

## 板验进展 2(2026-06-21):rootfs panic → grow 分区根因 + 修

首测 boot-sd.img(boot-sdl-202606211014):kernel panic `VFS: Unable to mount root fs on "/dev/mmcblk0p3"` + `No filesystem could mount root, tried: ext3 ext2 ext4 squashfs vfat msdos ntfs` 全失败。mmcblk0p3 分区在(GPT 写了、UUID 对、58GB grow),但**上面没有任何文件系统**——RK 工具建了分区却没写 rootfs.ext4。

**根因**:parameter-sd-aes.txt 原用 `-@0x00010000(rootfs:grow)`(grow)。`rkfw-pack.py` 的 `parse_parameter` 正则 `(-?0x[0-9a-fA-F]+)@0x...` 要求 size 是 `0x..`;grow 的 size 是裸 `-`(无 `0x`)→ **正则不匹配** → `parts["rootfs"]` 没设 → 默认 `nand_addr=0xFFFFFFFF`。RK 工具按各分区的 nand_addr 写镜像:uboot/boot 有偏移(0x2000/0x4000)→ 写了;rootfs=0xFFFFFFFF → **不知道往哪写 → 跳过**(只建了空 GPT 分区)→ 内核挂不上 → panic。vendor 用固定 size(5GB)所以没这问题。

**修**:
- `parameter-sd-aes.txt`:rootfs 改**固定 512MB** `0x00100000@0x00010000(rootfs)`(非 grow)→ 正则匹配 → nand_addr=0x10000。验:`rkfw-pack.py info` 显示 rootfs `nand_size=0x100000 nand_addr=0x10000`(was 0xFFFFFFFF)。
- **防再犯 ①**:`rkfw-pack.py` pack 时对 `nand_addr=0xFFFFFFFF` 的真实分区打 WARNING(grow/未映射 → RK 工具不会写 → 空分区 → 板 panic)。打包期抓,不放空分区出货。
- **防再犯 ②**:`assemble-update.sh --sd` 加 sanity check:rootfs.ext4 size ≤ rootfs 分区 size(防 `--rootfs-mib` 调大后静默溢出)。

新 update-sd.img md5 **dbc81910**(`/mnt/d/.../update-sd-rkfw-rootfsfix-20260621.img`)。**待板验**:kernel 该挂 `EXT4-fs (mmcblk0p3): mounted filesystem`(非 ubi0/UBIFS)。

## 板上手动引导序列(SD-1,板验用)

### 主路径:RKFW → RK 工具写 SD(本板唯一可用)
```
# 1. forge assemble --sd → board/aes/out/update-sd.img (RKFW,boot-sd.img 无 ramdisk)
# 2. Windows RK 工具打开 update-sd.img → 写到 SD 卡
# 3. 插卡上电 → SPL → U-Boot(2s 倒计时,按键进 => prompt)
=> mmc dev 0
=> mmc read 0x04000000 0x4000 0x5000     # boot-sd.img @ boot 分区(sector 0x4000)
=> setenv bootargs 'console=ttyS0,1500000 root=/dev/mmcblk0p3 rootwait rw'
=> bootm 0x04000000
# 4. kernel 起(无 initramfs 拦截)→ 按 root=/dev/mmcblk0p3 挂 SD ext4 → busybox shell
```
- **root=/dev/mmcblk0p3**:RKFW 的 GPT 有 3 分区(uboot=p1 @0x2000, boot=p2 @0x4000, rootfs=p3 @0x10000)。
- `mmc read 0x4000 0x5000`:从 sector 0x4000 读 20480 sect(10MiB)覆盖 kernel FIT。
- 进 prompt:CONFIG_BOOTCOMMAND 是 NAND 的 `mtd read boot`,会先跑;若板载 NAND 空则 mtd read 失败落 prompt,否则 2s 倒计时按键打断。

### 次选:裸 sd.img + dd/Etcher(本板 ROM 不认,仅作记录)
```
# forge pack-sd → sd.img → dd/balenaEtcher 写卡 → root=/dev/mmcblk0p1(单分区)
```
本板 ROM 不认裸镜像,此路径在本板不可用;留作其他能认裸镜像的板子。

## 板验进展(2026-06-21)

✅ **RKFW 路径板上验证通到 U-Boot**(首测 log):RK 工具写 update-sd.img → 上电 → DDR(v1.06)→ SPL(v1.12 公开 rkbin)`Trying fit image at 0x2000 sector` → verified-boot(optee v2.40 + uboot + fdt sha256 全 OK)→ **主线 U-Boot 2026.07-rc4 跑到 `=>` prompt**。整个 SD 启动机制 + 协议分析(SPL@0x2000、idblock@0x40、RKFW 转可启动 SD)**板上证实**。

❌ **但 `mmc dev 0` / `mmc list` 报 "No MMC device available"**——U-Boot proper 看不到 SD 卡。
- **根因**:主线 U-Boot 的 rk3506.dtsi(patch 0001)是极简 bring-up 版,**把 mmc 等所有外设 deferred 了**(只留 console/SFC)。mmc@ff480000 节点根本不存在。SPL 自带 SD 驱动能从 SD 读 uboot,但 U-Boot proper 走 driver-model(DM),DT 无节点 → dwmmc_rockchip 驱动不 probe → 无 MMC 设备。
- **修(patch 0004 `0004-uboot-dts-mmc-sd-controller.patch`)**:
  - rk3506.dtsi 加 `mmc@ff480000` 节点:`compatible = "rockchip,rk3506-dw-mshc","rockchip,rk3288-dw-mshc"`(驱动匹配 rk3288 fallback)+ clocks `<&cru HCLK_SDMMC>(166) <&cru CCLK_SRC_SDMMC>(165)` + reset `<&cru SRST_H_SDMMC>` + bus-width 4 + cap-sd-highspeed。
  - **坑**:dtsi 只 include 了 clock 头没 reset 头 → `SRST_H_SDMMC` 词法错(build-uboot 容错滤了错误,u-boot.dtb 没重建,sha256 没变还以为成了)。修=加 `#include <dt-bindings/reset/rockchip,rk3506-cru.h>`。
  - evb.dts `&mmc { broken-cd; status = "okay" }`:broken-cd = 卡肯定在(我们就是从它启动的)跳过 GPIO card-detect;**不加 pinctrl**——SPL 已配好 SD 引脚读 uboot,U-Boot 继承。
  - 验证:u-boot.dtb 新 sha256(c5bd3c40)+ fdtdump 确认 mmc 节点在(clocks 解析对、broken-cd 在)。
- 新 update-sd.img md5 **b5b77f25**(`/mnt/d/.../update-sd-rkfw-mmcfix-20260621.img`,前版 2de9884c)。
- **待重测**:RK 工具写新 update-sd.img → `mmc dev 0` 应枚举 SD → 手敲 mmc read + root=/dev/mmcblk0p3 + bootm。

## host 验证(已完成,board-independent)

- `forge pack-sd` → `out/sd.img` 296MiB。
- `sgdisk -p`:GPT p1 rootfs @ sector 65536,256MiB。✓
- 三个 blob(idblock/uboot/boot.img)sha256 偏移校验全过。✓
- rootfs 分区 ext4 魔数 0x53EF @ 分区偏移确认。✓
- `debugfs` 列文件:`/etc/issue`="Welcome to rk-forge buildroot"、`/sbin/init` symlink、`/lib/modules/8733bu.ko` 全在。✓
- 增量:`forge pack-sd` 二跑全 skip(content-hash)。✓

## 诚实边缘

- **非 byte-identical**:sd.img 跑两次 sha256 不同——根因 `mke2fs -d` 的 ext4 superblock 写时间(s_wtime/s_mtime/journal seq)host 相关。**结构/layout/内容确定性**(同 buildroot rootfs 的已知限制,见记忆 P2.4e)。已设固定 UUID + hash_seed 稳定结构;若需逐字复现,后续可 debugfs 清时间戳(类 buildroot byte-compare,非阻塞)。
- **唯一运行时假设**:公开 rkbin SPL 在 MMC 从 sector 0x2000 读 FIT——已被**构建配置**(`SYS_MMCSD_RAW_MODE_U_BOOT_SECTOR=0x2000`)+ vendor log 双证,板验为最终确认。
- **idblock.img 独立可用**:boot_merger 产干净独立 idblock(208896 B,比 MiniLoaderAll 281024 B 小——是前段无下载协议尾),已验证。

## SD-2(后续,不在本里程碑)

- SD autoboot:第二份 uboot defconfig(`CONFIG_BOOTCOMMAND` = `mmc dev 0; mmc read ...; setenv bootargs root=/dev/mmcblk0p1; bootm`),出自包含、无需手敲的可启动 SD。需 uboot 重建。
- 可选:rootfs 扩容(板上 resize2fs 或镜像 grow 分区)、byte-repro(debugfs 清时间戳)。

## 文件

- 改:`scripts/pack-loader.sh`(+idblock.img 捕获)、`scripts/forge.sh`(pack-sd 子命令 + assemble --sd + stage + status)、`scripts/assemble-update.sh`(+ `--sd` 变体:RKFW + ext4 rootfs + SD parameter)
- 新:`scripts/pack-sd.sh`(裸镜像 + rootfs.ext4 构建)、`scripts/flash-sd.sh`(stub→实装 dd 写卡器 + 安全检查)、`board/aes/parameter-sd-aes.txt`(SD GPT)、`board/aes/package-file-sd.txt`(SD RKAF manifest)、本 notes
- **交付件**:`board/aes/out/update-sd.img`(RKFW,`forge assemble --sd`)→ cp `/mnt/d/DownloadFromInternet/update-sd-rkfw-<date>.img`(md5 2de9884c)。次选裸 `sd.img`(md5 ab7de19e)本板用不上。

## 关联记忆
[[sd-card-image-next-phase]]、[[handoff-current-state-next-usb]]、[[flash-and-verify-runbook]]、[[packaging-change-stage-update-img]]、[[mainline-uboot-bringup-state]]
