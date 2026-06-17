# Vendor U-Boot 构建链笔记(ATK-DLRK3506)

> **活账本**。这份笔记记录 ATK-DLRK3506 vendor SDK 怎么把 U-Boot 编出来,**作为主线迁移的参照基准**。迁移过程中一旦发现现实与本文不符,先改这里,再改动作。
> 来源:`./build.sh lunch`(选 #19)+ `./build.sh uboot` 的实跑 + 脚本精读。
> 配套日志:`document/logs/build-uboot.log`、`document/logs/lunch.txt`。

---

## TL;DR(三句话)

1. `build.sh uboot` 派发到 `mk-loader.sh`(钩子 `build-hooks/70-loader.sh`),后者调 vendor `u-boot/make.sh`,**一次 `make all` 出 u-boot+SPL+TPL,再两次打包**(FIT + idblock)。
2. **三个产物**:`rk3506_idblock_v1.06.111.img`(DDR blob + SPL,boot_merger 从 `RKBOOT/RK3506BMINIALL.ini` 打)、`uboot.img`(FIT:u-boot+OP-TEE+dtb,`make_fit_optee.sh` 生)、`MiniLoaderAll.bin`(完整 loader)。
3. **vendor 的整套打包层(make.sh / boot_merger / .ini / make_fit_optee.sh)在主线全塌缩成一个 `binman` 调用**;而 blob 集、SD 布局、bootrom 链、加载地址**完全通用、原样复用**。

---

## 1. 端到端流程

### ① `./build.sh lunch`(选 19)→ 解析 `RK_*` 环境
- `build.sh` 列 `device/rockchip/.chips/rk3506/` 下 42 个 `NN_*_defconfig`,选 19 → 经 kconfig 写 `output/.config` + `output/final.env`(软链 `output/final.env`)。
- **#19 这个 SDK defconfig 是薄 Kconfig 壳**:只命名 `RK_UBOOT_CFG="alientek_rk3506"` + 分区/DT/存储提示。真正的 U-Boot Kconfig 是 `u-boot/configs/alientek_rk3506_defconfig`。
- 该 defconfig 里关键项:`CONFIG_LOADER_INI="RK3506BMINIALL.ini"`(**B silicon 选择**)、`CONFIG_SPL_FIT_GENERATOR="arch/arm/mach-rockchip/make_fit_optee.sh"`、`CONFIG_ROCKCHIP_FIT_IMAGE_PACK=y`、`CONFIG_ROCKCHIP_NEW_IDB=y`。

### ② `./build.sh uboot` → 派发到 hook
- "uboot" 是 build 命令(`*.parsed_cmds` 聚合各 `mk-*.sh` 的 `*_CMDS`)→ 匹配 `mk-loader.sh`。
- 钩子排序 = 文件名数字:`build-hooks/NN-*.sh` 是指向 `scripts/mk-*.sh` 的软链,`70-loader.sh -> ../scripts/mk-loader.sh`。"70" 纯排序键。
- `mk-loader.sh` 的 `BUILD_CMDS="loader uboot u-boot"`,三个别名都进同一个 `build_uboot()`。
- 钩子经 `build-helper` 用**全量导出的 `RK_*` 环境**跑,所以 `mk-loader.sh` 能直接引用 `$RK_UBOOT_CFG` 等。

### ③ `mk-loader.sh`(loader 阶段编排)
- `get_toolchain U-Boot arm` → `prebuilts/gcc/.../arm-none-linux-gnueabihf-`(覆盖 make.sh 里硬编的 linaro)。
- 组命令:`./make.sh CROSS_COMPILE=<tc> alientek_rk3506 --spl-new`(`--spl-new` 因 `RK_UBOOT_SPL=y`)。
- 完事后把 `u-boot/*_loader_*.bin` 软链 `output/firmware/MiniLoaderAll.bin`、`u-boot/uboot.img` → `output/firmware/uboot.img`。
- **`build_uboot()` 一次调 make.sh 同时出 uboot.img 和 loader**,没有独立 build_loader。

### ④ vendor `u-boot/make.sh`(心脏,810 行)
调为 `./make.sh CROSS_COMPILE=... alientek_rk3506 --spl-new`,主序列(`make.sh:797-810`):
`process_args → prepare → select_toolchain → select_chip_info → select_ini_file → make all → pack_images → finish`

- **defconfig**:`make alientek_rk3506_defconfig -j28`。
- **PLAT_TYPE 检测**:`.config` 有 `CONFIG_ROCKCHIP_FIT_IMAGE_PACK=y` → `PLAT_TYPE="FIT"` → 走 `pack_fit_image`(而非 legacy 三件套)。
- **ini 解析**:`select_ini_file()`——`CONFIG_LOADER_INI="RK3506BMINIALL.ini"` 覆盖默认 → `RKBOOT/RK3506BMINIALL.ini`;arm32 无 ATF → `RKTRUST/RK3506TOS.ini`。
- **`make all`** 一把编三样:**u-boot proper**(`LD u-boot` / `OBJCOPY u-boot-nodtb.bin` / `DTC alientek-rk3506.dtb` / `MKIMAGE u-boot.img`)、**SPL**(`spl/u-boot-spl`)、**TPL**(`tpl/u-boot-tpl`,DDR-init 阶段)。
- **FIT(uboot.img)**:`make_fit_optee.sh`(18 行,调 `fit_nodes.sh` 的 gen_*)生成 `u-boot.its` → `mkimage -f u-boot.its -E u-boot.itb`。FIT 装 `uboot`(u-boot-nodtb.bin @ **0x200000**)+ `optee`(tee.bin @ **0x1000**)+ `fdt`(u-boot.dtb)。`conf { firmware=optee; loadables=uboot; fdt=fdt }`。tee.bin 从 `RKTRUST/RK3506TOS.ini` 的 `TOSTA=bin/rk35/rk3506_tee_v2.40.bin` 取,`ADDR=0x1000`。
- **idblock**:`pack_fit_image → fit.sh → pack_spl_loader_image`——把 .ini 拷到 tmp,`sed` 把 `FlashBoot=` 改指向刚编的 `spl/u-boot-spl.bin`,再 `./tools/boot_merger tmp/MINIALL.ini`。出 `rk3506_idblock_v1.06.111.img` + `rk3506_spl_loader_v1.06.111.bin`。
- **arm32 无独立 trust.img**——OP-TEE 嵌在 FIT 里(`optee` 节点)。

---

## 2. 产物 + bootrom 链(心智模型)

### 三个产物

| 产物 | 大小 | 内容 | 谁打的 |
|---|---|---|---|
| `rk3506_idblock_v1.06.111.img` | 198 KB | **DDR blob(rkbin)+ SPL** | boot_merger 从 `RKBOOT/RK3506BMINIALL.ini` |
| `uboot.img` | 4 MB | FIT: u-boot + OP-TEE + dtb | mkimage 从 make_fit_optee.sh |
| `rk3506_spl_loader_v1.06.111.bin` → `MiniLoaderAll.bin` | 270 KB | 完整 loader(idb+下载元数据) | boot_merger |

### `RKBOOT/RK3506BMINIALL.ini` 的 idblock 布局

```
[CODE471_OPTION] Path1=bin/rk35/rk3506b_ddr_750MHz_v1.06.bin   ← DDR init(rkbin blob)
[CODE472_OPTION] Path1=bin/rk35/rk3506_usbplug_v1.03.bin       ← USB 下载助手
[LOADER_OPTION]
  FlashData=bin/rk35/rk3506b_ddr_750MHz_v1.06.bin   ← 槽1(TPL/DDR)
  FlashBoot =<刚编的 spl/u-boot-spl.bin>            ← 槽2(SPL,sed 动态替换)
[OUTPUT] PATH=rk3506_spl_loader_*.bin  IDB_PATH=rk3506_idblock_*.img
[SYSTEM] NEWIDB=true
[FLAG]   471_RC4_OFF=true  RC4_OFF=true  CREATE_IDB=true
```

### bootrom 执行顺序(SD 启动)

1. **RK3506 bootrom**(掩膜 ROM)读 SD 扇区 **0x40** → 找到 idblock 头。
2. bootrom 解析 idblock → 取 **FlashData(DDR blob)**,在内部 SRAM 跑 → **DRAM 活**。
3. bootrom 取 **FlashBoot(SPL)**,拷进 DRAM,跳过去。
4. **SPL** 初始化 clk/MMU/UART,定位 SD 偏移 **0x2000** 的 `uboot.img`,解析 FIT。
5. SPL 按 `conf` 装:**optee(0x1000)** 先(firmware),再 **uboot(0x200000)**(loadable),再 **fdt**。
6. SPL 跳 OP-TEE(0x1000)→ 安全世界就绪 → 降回 NS 世界。
7. **U-Boot proper** 在 0x200000 带 DTB 跑起来 → 提示符(`CONFIG_BOOTDELAY=0`,不按键就直接引内核)。

> **DDR-init 重复**:vendor 从源码编了 `tpl/u-boot-tpl.bin`(含 `sdram_rk3506.c`),但 idblock 实际用 **rkbin 预编译的 DDR blob**——vendor policy,认 Rockchip 认证的二进制。这跟主线"DDR 走 `ROCKCHIP_EXTERNAL_TPL` rkbin blob"是同一个事实。

---

## 3. vendor-ism vs 通用 RK(迁移判别表)

| 环节 | vendor 机制 | 性质 |
|---|---|---|
| 配置选择 | `build.sh lunch` + SDK defconfig 壳 + `RK_UBOOT_CFG` 两层 | **vendor-ism**(主线塌成单 defconfig) |
| 构建 | `u-boot/make.sh`(810 行) | **vendor-ism**(主线 `make`,无 make.sh) |
| 钩子系统 | `build-hooks/NN-*.sh` + `mk-*.sh` + `build-helper` | **vendor-ism**(主线无) |
| FIT 生成 | `make_fit_optee.sh` + `fit_nodes.sh` → `mkimage` | **vendor-ism**(主线 binman 从 dtsi 生) |
| idblock 打包 | `boot_merger` + `RKBOOT/*MINIALL.ini` | **vendor-ism**(主线 binman,无 .ini) |
| OP-TEE 嵌入 | `pack_uboot_itb_image` + `RKTRUST/*TOS.ini` | **vendor-ism**(主线 binman `tee-os` entry) |
| blob 集 | DDR / SPL / TPL / OP-TEE / U-Boot / DTB | **通用 RK**(原样) |
| SD 布局 | idblock@0x40, uboot@0x2000 | **通用 RK**(bootrom 硬编) |
| bootrom 链 | bootrom→DDR→SPL→FIT(optee+uboot+fdt) | **通用 RK** |
| 加载地址 | uboot@0x200000, TEE@0x1000 | **通用 RK** |
| B-silicon | 选 `rk3506b_ddr` blob | **通用 RK** |
| 工具链 | arm-none-linux-gnueabihf 10.3 | 通用(主线同样接受) |

---

## 4. vendor → 主线 binman 映射(迁移速查)

| vendor 步骤 | vendor 机制 | 主线等价 |
|---|---|---|
| 选配置 | `build.sh lunch` → SDK defconfig → `RK_UBOOT_CFG` | `make evb-rk3506_defconfig`(单 defconfig,无壳) |
| 编 U-Boot | `make.sh ... alientek_rk3506 --spl-new` | `make CROSS_COMPILE=arm-linux-gnueabihf-` |
| DDR+SPL → idblock | `boot_merger RK3506BMINIALL.ini` | **binman**(`simple-bin > mkimage` 节点,`rockchip-tpl` + `u-boot-spl`),blob 路径由 `ROCKCHIP_TPL=` env 给 |
| FIT(uboot+optee+dtb) | `make_fit_optee.sh` → `mkimage -f u-boot.its` | **binman** `fit` 节点(arm32 走 `rockchip-u-boot.dtsi` 的 `op-tee` 分支),TEE 路径由 `TEE=` env 给 |
| 定位 rkbin blob | `RKBOOT/*.ini` + `RKTRUST/*.ini` | env:`ROCKCHIP_TPL=.../rk3506b_ddr_750MHz_v1.06.bin`、`TEE=.../rk3506_tee_v2.40.bin`(无 BL31,arm32) |
| 产物落 firmware/ | `mk-loader.sh` 软链 | `make` 直接出 `idbloader.img` + `u-boot.itb` + `u-boot-rockchip.bin` |

**核心**:vendor 的 `make.sh + boot_merger + .ini + make_fit_optee.sh` 是一套内聚的打包层;主线全塌缩成**一个由 board `u-boot.dtsi` 里 binman 节点驱动的 binman 调用**。blob 本身(DDR、OP-TEE)和 SD/bootrom 契约一致。

---

## 5. 待核实(迁移中要验的坑)

- [ ] **pinctrl bank 完整性**:`pinctrl-rk3506.c:400` 静态 `rk3506_pin_banks[]`(`.nr_banks=ARRAY_SIZE`)——probe 是否要求 DT 给齐所有 bank?最小 dtsi 只 gpio0 行不行?
- [ ] **波特率**:vendor 默认 1500000,ATK 板载 USB-UART 芯片是否改 115200?
- [ ] **dmc 节点 / DRAM size 读回**:`sdram_rk3506.c` 从 PMUGRF+0x208 读,验证 B silicon 偏移对不对。
- [ ] **`misc_init_r`/OTP**:SoC Kconfig imply `MISC_INIT_R`,是否解引用最小 DT 里没有的 OTP 节点导致 banner 后挂?
- [ ] **binman arm32 op-tee 节点**:`rockchip-u-boot.dtsi` 的 `#else` 分支 op-tee load 0x8400000(SDRAM_BASE=0 → 实为 0x8400000),与 vendor 的 0x1000 不同——主线是否另有 TEE_OFFSET 配置?迁移时核对。

---

## 6. 主机依赖差异(Stage 0 实证,2026-06-14)

主线 U-Boot 比 vendor build **多要** host 依赖(vendor 2017 uboot 不编 pylibfdt,绕过了)。实跑 evb-rk3308 基准构建在 `scripts/dtc/pylibfdt` 阶段报 `swig: No such file or directory`。

**缺的(需补)**:`swig`、`python3-dev`、`python3-pyelftools`(`python3 -c "import libfdt/elftools"` 都失败)。
**已在**:bc / bison / flex / libssl-dev / device-tree-compiler / build-essential / cpio / python3-setuptools。

```bash
sudo apt install swig python3-dev python3-pyelftools
```

**又一项(免装)**:`tools/mkeficapsule`(EFI capsule 签名工具)要 `libgnutls28-dev`。RK SD 启动用不到 EFI capsule → defconfig 加 `# CONFIG_TOOLS_MKEFICAPSULE is not set` 关掉(门控符号 `CONFIG_TOOLS_MKEFICAPSULE`,`tools/Makefile:273`),省装 gnutls、构建更干净。

## 7. Stage 1 构建结果(2026-06-14)

**通过的部分**(板层代码 sound):
- `spl/u-boot-spl.bin`(72 KB)编出来 → 交叉编译 OK,defconfig/Kconfig/dtsi 全对。
- `arch/arm/dts/rk3506-evb.dtb` 编出来 → **手刻最小 dtsi DTC 干净通过**:gpio0-4、`pcfg_pull_up/none`(标准 `bias-*` binding)、`uart0_xfer_pins`(`<0 RK_PC7 1 &pcfg_pull_up>` 等)、cru clock-ID(`SCLK_UART0`/`PCLK_GPIO0`/`DBCLK_GPIO0`…)全解析成功。**bank 完整性风险解除**(给了 5 个 bank)。

**fake-blob 模式的真相**:`--fake-ext-blobs --allow-missing` 对 `rockchip-tpl` 仍报错(binman exit 103:"missing external blobs: rockchip-tpl, non-functional")——fake 只占位不放过。所以 **Stage 1 的通过标准 = "SPL + dtb 能编"**(已达成),不必强求 fake-blob 出整镜像。直接进 Stage 2 喂真 rkbin blob。

## 8. Stage 2 构建结果(2026-06-14)✅ 镜像可烧

喂真 rkbin blob(`ROCKCHIP_TPL=rk3506b_ddr_750MHz_v1.06.bin` + `TEE=rk3506_tee_v2.40.bin`)后 binman 干净通过,出真镜像:

| 产物 | 大小 | 内容(已核实) |
|---|---|---|
| `u-boot-rockchip.bin` | 8.7 MB | idbloader + FIT;FIT magic `d00dfeed` ×7;含 `U-Boot 2026.07-rc4` + `Rockchip RK3506 Evaluation Board (ATK RK3506B)` banner 串 |
| `idbloader.img` | 96 KB | rkbin DDR `fwver: v1.06`(`d27ac532c4`, LPDDR2/3/4)+ U-Boot SPL |
| `spl/u-boot-spl.bin` | 72 KB | SPL(proper) |

**SPL 能读 SD**:`CONFIG_SPL_MMC=y` + `CONFIG_SPL_DM_MMC=y`(Kconfig 隐式 imply),`SPL_PAYLOAD="u-boot.bin"` → SPL 能从 SD 偏移 0x2000 读 FIT。

**烧录**:`sudo dd if=u-boot-rockchip.bin of=/dev/sdX bs=512 seek=64 conv=fsync && sync`(seek=64 = sector 64 = RK bootrom idblock 加载点)。详见 Stage 3。

## 9. Stage 3 上板结果(2026-06-14)⚠ 板子跑了 SPI NAND 的 vendor,没跑我们的 SD

**UART 输出显示**(关键行):
```
DDR ... fwver: v1.04                          ← 我们的 DDR 是 v1.06,这是 v1.04 → 不是我们
U-Boot SPL 2017.09-g0481582-dirty #charliechen ← vendor 2017 BSP,非我们 2026.07-rc4
Model: Rockchip RK3506 EVB Board              ← vendor model 串
Trying to boot from MMC1 ... Invalid GPT ... spl: partition error
Trying fit image at 0x4000 sector ... crc32 error / Unsupported hash algorithm
Trying to boot from MTD1 (SPI NAND) ... 找到 vendor FIT → Jumping to U-Boot via OP-TEE
DRAM: 512 MiB
```

**已排除的嫌疑(镜像/烧录都没错)**:
- 我们 `idbloader.img` 头与 vendor `rk3506_idblock` **字节级一致**(`RKNS 0000 0000 8001 0200...`)→ idblock 格式对,bootrom 该认。
- `CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_SECTOR=0x4000` → SPL 在扇区 0x4000 找 FIT;vendor SPL 日志"Trying fit at 0x4000"**找到了我们的 FIT**(只是 2017 SPL 读不懂 2026 FIT 的 hash 节点)→ **Rufus 裸写正确**(从扇区 0 写,32KB 垫零让 idblock 落扇区 64、FIT 落 0x4000)。
- UART/波特率(1500000)/接线全对(输出干净),板子活,DDR 512MB。

**真因**:bootrom **没从 SD 加载我们的 idblock**,直接从 SPI NAND 起了 vendor。板子出厂 boot 顺序大概率 **SPI NAND 优先**,SD 在后或需强制。

**已验证(里程碑侧面达成)**:主线 U-Boot 镜像**能正确生成 + 写入 + 被 SPL 识别**(FIT 在 0x4000 被找到)。差的只是让 bootrom 选 SD。

**下一步选项**:
1. 查 ATK 板子有无 SD 启动按键/跳线(boot-mode strap),强制 SD 优先。
2. 抹掉 SPI NAND 的 idblock(maskrom + rkdeveloptool),让 bootrom 回退到 SD。
3. 直接把镜像写进 SPI NAND(maskrom + rkdeveloptool)。

**待用户确认**:板子的 boot 顺序怎么选 SD?ATK 文档怎么说 SD 启动?

## 10. FIT 偏移不匹配(2026-06-14,深挖 parameter + vendor defconfig)

**vendor**:`alientek_rk3506_defconfig` 有 `CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_USE_PARTITION=y` → SPL 按 **GPT 分区表**找 `uboot` 分区加载 FIT,不读固定扇区。parameter(NAND 和 SD 都是):`0x00002000@0x00002000(uboot)` → uboot 分区在 **sector 0x2000**(byte 4MB)。

**我们主线**:`CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_SECTOR=0x4000`(sector 0x4000 = byte 8MB)→ 固定扇区。

**错位 4MB**。若 SDDiskTool 按 parameter 把 uboot.img 写进 `uboot` 分区(sector 0x2000),我们 SPL(找 0x4000)读不到。

**修正(二选一)**:
- (简)defconfig 加 `CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_SECTOR=0x2000`,SPL 改从 sector 0x2000 读。
- (干净)若主线支持,加 `CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_USE_PARTITION=y`,跟 vendor 一样按分区查。

(这也解释了 vendor SPL 先报 GPT 错再回退试 0x4000/0x5000——分区查找挂了才走 raw 兜底。)

## 11. SDDiskTool / update.img 路径(2026-06-14)

板子/ATK 强制走 SDDiskTool,需**完整 update.img**(RK 打包格式,非裸 idblock+FIT)。vendor 流水线:
- `mk-firmware.sh` 装 `rockdev/`(loader=MiniLoaderAll.bin + parameter + 分区镜像)
- `mk-updateimg.sh`:`afptool -pack` → `rkImageMaker -RKxxxx MiniLoaderAll.bin update.raw.img update.img`
- `package-file` = `bootloader→MiniLoaderAll.bin` + `parameter` + 各分区镜像(`gen_package_file` **只打包存在的镜像**,所以可不出 rootfs)

**换点**:rockdev 里 `MiniLoaderAll.bin` ← 我们的 loader(idbloader);`uboot.img` ← 我们的 `u-boot.itb`。再 `./build.sh updateimg` 打包。

**两条路**(取决于板子能否 SD 启动):
- **A. SD via SDDiskTool**:修偏移(0x2000)+ 换 uboot 进 update.img + SDDiskTool 烧 SD。不碰板载 NAND,但需板子真能 SD 启动。
- **B. 写 SPI NAND**:maskrom + rkdeveloptool/RKDevTool,把我们 uboot 直接写进板载 NAND(替换 vendor)。**板子确定从 NAND 起**(已验证),所以这条路最稳,但覆盖出厂 vendor。

## 12. idblock 对比 + 0x2000 重编(2026-06-14)

**idblock 结构对比**(我们 `idbloader.img` 96KB vs vendor `rk3506_idblock` 194KB):
- **头 128 字节字节级一致**(`RKNS 0000 0000 8001 0200 … 0400 2800 ffff ffff`)——段表、RC4 标志、版本全同。**我们 idblock 格式有效,bootrom 该认。**
- 两边都含 DDR v1.06(`d27ac532c4`)→ 板载 NAND 是更老的出厂 **v1.04**(没更新过),与我们无关。
- 大小差是 vendor SPL 更大(驱动多),结构同。

**0x2000 重编**:defconfig 加 `CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_SECTOR=0x2000`,重编成功(idbloader 新鲜)。**但**——日志 DDR v1.04 已证 bootrom 没加载我们 idblock(直接起 NAND vendor),FIT 扇区是下游事,**改 0x2000 改变不了板子选 NAND**。再 raw 烧一次只是确认判断。

**真因二选一**(待定):① boot 顺序 NAND 优先(任何 SD 都不启→只能写 NAND);② SD 优先但拒了 raw SD(没 GPT?→ update.img 带 GPT 能起)。

**工具链**:apt `gcc-arm-linux-gnueabihf` 未装(sudo 要密码);探索构建暂用 vendor 打包的 `arm-none-linux-gnueabihf-`(gcc 10.3.1,功能等价)。正式 forge 构建切回 apt。

**附带发现的 forge gap**(待修):
- `scripts/doctor.sh` 漏查 `swig`(只查了 python3-pyelftools)——应加 swig 探测。
- `QUICK_START.md` 的 apt 行也漏 `swig` / `python3-dev`。
- 基准板选错:rk3308 在主线是 **arm64**(`ROCKCHIP_RK3506 select ARM64`),不是 arm32。arm32 基准应选 `evb-rk3288`。但对 rk3506(arm32)迁移非必需——装完依赖可直接编 rk3506 本身。

---

## 变更记录

- 2026-06-14:初版。据 `build-uboot.log` 实跑 + 脚本精读建立。`待核实` 项随迁移推进修正。
- 2026-06-14:**Stage 0 修正**——主线 host 依赖比 vendor 多 `swig`/`python3-dev`/`python3-pyelftools`(evb-rk3308 基准构建实证);工具链暂用 bundled;doctor.sh/QUICK_START 漏 swig(待补);rk3308 是 arm64 非 arm32。
