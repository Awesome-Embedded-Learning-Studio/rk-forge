# RK3506 主线 U-Boot 移植 — 交接 + 踩坑日志

> **给下一个会话**:从这里接上下文。本文是"克隆分身",自包含。
> 配套:`01-2026-06-14-vendor-uboot-build-flow.md`(vendor 构建链技术细节)、`../../PLAN.md`(项目方向)、memory(已核实前提)。
> 最后更新:2026-06-14。

---

## TL;DR(三行)

1. 主线 U-Boot `2026.07-rc4` **能编出来**;我们的 idblock 让板子 **DDR 起来了(v1.06,我们构建的)** ✅ —— 这是实打实的里程碑。
2. **SPL 阶段崩**(全波特率乱码,DT 完整无问题)❌ —— 当前阻塞,远程难调(无 JTAG)。
3. 下一步:**B(vendor SPL + 我们 U-Boot,拿主线 U-Boot banner 快速里程碑)→ A(正经调我们的 SPL)→ 内核**。

---

## 目标

rk-forge:把**主线 U-Boot + 主线内核**在 **ATK RK3506B(SPI NAND,32-bit Cortex-A7)** 上拉起来。当前在 Week 3-4 里程碑:**主线 U-Boot banner 出在 UART**。

工作树:`third_party/explore/uboot`(主线 denx u-boot,HEAD = 2026.07-rc4,全量检出)。参照系:`third_party/vendor-sdk`(ATK 厂商 BSP)。rkbin:`third_party/explore/rkbin`(上游)。

---

## 已达成(实打实的进展)

1. **主线 U-Boot 板层代码编过**。主线有 RK3506 的 SoC **驱动**(mach-rockchip/rk3506、clk_rk3506、pinctrl-rk3506、sdram_rk3506、ROCKCHIP_EXTERNAL_TPL),但**没板级**(无 defconfig/board/DT)。我们补了 4 个文件:
   - `third_party/explore/uboot/configs/evb-rk3506_defconfig`(仿 generic-rk3528,**无 board 目录、无 TARGET_**,靠 ROCKCHIP_COMMON_BOARD)
   - `arch/arm/dts/rk3506.dtsi`(从 vendor 移植的最小 SoC DT:cru/grf/grf_pmu/ioc_*/pinctrl+gpio0-4/uart0/gic/timer;**砍了 378KB 的 pinctrl-rmio**)
   - `arch/arm/dts/rk3506-u-boot.dtsi`(`#include rockchip-u-boot.dtsi` 拉进 binman + bootph 标签)
   - `arch/arm/dts/rk3506-evb.dts`(板级,model="Rockchip RK3506 Evaluation Board (ATK RK3506B)",console=&uart0)
   - **没改 `arch/arm/dts/Makefile`**(dtb 由 CONFIG_DEFAULT_DEVICE_TREE 经 scripts/Makefile.dts 自动编)
2. **binman 出了真镜像**:`u-boot-rockchip.bin`(8.7MB)+ `idbloader.img`(96KB,DDR v1.06 + 我们 SPL)+ `u-boot.itb`(FIT:U-Boot 2026.07-rc4 + op-tee + rk3506-evb dtb)。
3. **DDR + idblock 在板子上跑起来了**!日志首行 `DDR d27ac532c4 ... fwver: v1.06`(我们的 hash/版本,非出厂 v1.04)→ bootrom 加载了我们的 idblock。

---

## 当前阻塞:SPL 崩(乱码)

DDR 之后(SPL 该出 banner 处)输出 **`xDþ麃h` / `UNK:`** 乱码,**所有波特率(1500000/115200/921600/57600/38400)都不可读** → 不是波特率,是 **SPL 早期崩** 或 UART 配置彻底错。

**已排除**:
- DT:SPL 内嵌 DT(`spl/u-boot-spl.dtb`)完整(cru/pinctrl/uart/grf/dmc 全在,13 phandle)—— 不是 DT 问题。
- 加载地址:`SPL_TEXT_BASE=0x00000000` → RK 约定 load `0x03f00000`,与 vendor `.ini` 的 `LOAD_ADDR=0x3f00000` **一致**。

**未定嫌犯**:① SPL 的 debug UART 时钟假设(24MHz)与上电后实际 UART 时钟不符→非标波特;② boot_merger 打包我们 SPL 时校验和/格式错(DDR 段没事不代表 SPL 段没事);③ 早期崩。

**远程难调**:无 JTAG、输出全乱码。需要迭代构建+烧录(每次让用户重烧)。

**附带**:**我们的 SPL 缺 SPI NAND 驱动**(defconfig 只有 MMC_DW/SPL_MMC,板子从 SPI NAND 起)——即便 banner 出来,SPL 后面也读不了 NAND 上的 FIT。完整启动要补 SFC/MTD。

---

## 踩坑日志(按时间)

1. **vendor-sdk 是 bz2 非 gz**:`atk_dlrk3506_*.tar.gz` 实为 bzip2,用 `tar -xjf --strip-components=1`。
2. **repo 检出缺 python**:本机只有 python3,用 `python3 .repo/repo/repo sync -l -j8`(不 sudo 建软链)。
3. **vendor U-Boot(2017)构建缺 python2**:check-loader.sh 是软门(`if ! which python2`),用 pyenv 装 2.7.18(系统零污染,`pyenv shell 2.7.18`)。主线 U-Boot 不需要(python3-only)。
4. **主线 host 依赖比 vendor 多**:vendor build 不需要,主线编 pylibfdt/binman 要 `swig` + `python3-dev` + `python3-pyelftools`(evb-rk3308 基准构建在 `scripts/dtc/pylibfdt` 报 `swig: No such file`)。
5. **mkeficapsule 要 gnutls**:RK SD 启动用不到 EFI capsule,defconfig 加 `# CONFIG_TOOLS_MKEFICAPSULE is not set` 免装 libgnutls28-dev。
6. **工具链**:apt `gcc-arm-linux-gnueabihf` 未装(sudo 要密码);探索构建用 vendor 打包的 `arm-none-linux-gnueabihf-`(gcc 10.3,功能等价)。正式 forge 构建切回 apt。
7. **linux 子模块 URL**:PLAN 要 v7.0.12(在 `stable/linux.git`,**非 torvalds**——torvalds 只有 v7.0 大版本)。
8. **主线 U-Boot rk3506 缺板级**:有 SoC 驱动,没 defconfig/board/DT——这才是贡献点。**主线内核也缺 rk3506.dtsi**(SoC DT 都没有,不仅是 board DT)。
9. **FIT 偏移**:vendor `CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_USE_PARTITION=y`(按 GPT 分区查 uboot@0x2000);主线默认 `0x4000`。我们对齐改成 `0x2000`。
10. **板子 boot 顺序**:实测从 **SPI NAND** 起(不是 SD)。raw SD(无论 Rufus 还是 padded)bootrom 都不选,直接起 NAND vendor。
11. **idblock 格式**:我们 binman 的 idblock 头与 vendor boot_merger 的**字节级一致**(RKNS + 同段表)——格式有效。
12. **RKDevTool "Loader" 字段坑**:它一个字段干两件事——既做 db(要 usbplug),又往 boot 区写(要是我们的 idblock)。我们的 binman idbloader 没 usbplug→不能当 db loader。**vendor-loader 有 usbplug 但 SPL 是 vendor 的**。
13. **合并 loader 解法(关键)**:用 vendor 的 `boot_merger` + `RKBOOT/RK3506BMINIALL.ini`,把 `FlashBoot` 指向**我们的 SPL**,产出**两用 loader**(vendor usbplug + 我们的 SPL + DDR)。RKDevTool 单 Loader 字段就能 db + 写我们的 SPL。产物:`rk3506_spl_loader_mainline.bin`。验证:其 idblock 含 `U-Boot SPL 2026.07-rc4` 串。
14. **合并 loader 上板后**:DDR v1.06(我们的)起,但 SPL 乱码崩(见上"当前阻塞")。

---

## 下一步(优先级)

**先把板子恢复干净**(可选,若板子停在乱码):RKDevTool `Loader → rk3506-vendor-loader.bin`,uboot 留空 → 回出厂 vendor U-Boot。

**B. vendor SPL + 我们 U-Boot(快速里程碑,推荐先做)**:
- 用能干净跑的 vendor SPL,把我们的主线 U-Boot 装进** vendor 能解析的 FIT**(vendor SPL 不认我们 FIT 的 sha256 hash → "Unsupported hash algorithm";要去掉/换 hash,或用 vendor 的 `make_fit_optee.sh` + 我们的 u-boot-nodtb.bin 生成 vendor 格式 FIT)。
- 写到 0x2000。启动:vendor DDR+SPL → 加载我们的 U-Boot → `U-Boot 2026.07-rc4` banner。
- **不是纯主线 boot**(SPL 借 vendor),但主线 U-Boot 在板子上跑起来 = 里程碑。

### B 已落地:vendor 格式 FIT 已构建(2026-06-14,待上板)

**关键修正(推翻之前假设)**:vendor 的 `fit_nodes.sh` **自己也用 sha256**(`hash { algo = "sha256"; }`)——所以 "Unsupported hash algorithm" 的真因不是算法名,而是**主线 binman 生成的 FIT 结构/节点命名 vendor SPL 不认**。正解:**直接用 vendor 结构重新打包,只换 uboot 二进制**。

**实证 vendor FIT 结构**(直接 `dumpimage -l vendor uboot.img`):
```
Image 0 (uboot): Standalone, load=0x00200000, sha256
Image 1 (optee): Firmware,   load=0x00001000, sha256   ← 带 OP-TEE
Image 2 (fdt):   Flat DT,     sha256
conf: firmware=optee, fdt=fdt, loadables=uboot
```
boot 链:SPL → 装 optee(0x1000)+uboot(0x200000)+fdt → 跳 optee(安全世界)→ 降 NS → 跳 uboot。

**地址坑(关键)**:主线 `CONFIG_TEXT_BASE=0x00800000`,vendor FIT 里 uboot@0x00200000,差 6MB。我们代码按 0x800000 链接,装到 0x200000 会崩(绝对寻址错)。**解法:ITS 里 uboot `load=0x00800000`**(匹配我们编译),optee(0x1000)/tee 不动。SPL 装我们 uboot 到 0x800000,optee NS 跳转地址由 SPL 按 loadable 的 load 设置 → 自洽。

**产物**:`board/aes/fit/rk3506-mainline.its`(手写,复刻 vendor 结构)+ `rk3506-mainline.itb`(547KB,vendor 2017.09 mkimage `-E` 打包)。dumpimage 对照:optee hash 值与 vendor **逐字节相同**(同一颗 tee.bin),结构/conf 全对。Windows 副本:`D:\DownloadFromInternet\rk3506-uboot-mainline-vendor-fit.itb`。

**烧板(待用户操作,RKDevTool "下载镜像"模式)**:
1. Loader = `rk3506-vendor-loader.bin`(vendor 原装,恢复 vendor SPL 到 boot 区 + 进下载模式)
2. parameter = `parameter-nand.txt`
3. **只勾 uboot 分区** → `rk3506-uboot-mainline-vendor-fit.itb`,其余不勾(保留原 NAND)
4. 执行 + 重启。判据:`U-Boot 2026.07-rc4` banner。

**最大风险**:vendor `tee.bin` 是 rkbin 预编译,op-tee 跑完 NS 跳 uboot 的地址——若从 SPL 传的 loadable 取(标准),0x800000 OK;若硬编码 0x200000,跳空。崩了备选:ITS 改 uboot load=0x200000 + 重编主线 uboot TEXT_BASE=0x200000。

### B 上板成功:主线 U-Boot banner 达成 🎉(2026-06-14 20:37)

**所有判断命中**:① vendor SPL 顺利验了我们的 vendor 格式 FIT(optee/uboot/fdt 全 sha256 OK)——证明"结构不是算法问题";② uboot@0x800000 装对了;③ OP-TEE NS 跳转地址 = 0x800000(`I/TC: Next entry point address: 0x00800000`,**标准做法从 SPL loadable 取,非硬编码**——最大风险排除)。UART:`U-Boot 2026.07-rc4` + `Rockchip RK3506 Evaluation Board (ATK RK3506B)` + `DRAM: 512 MiB` + `32 devices, 14 uclasses`。

**唯一尾巴:banner 后 hang 在 misc_init_r**。`initcall_run_r(): initcall misc_init_r() failed` → `### ERROR ### Please RESET`。根因(board.c 的 misc_init_r → `rockchip_cpuid_from_efuse` → `uclass_get_device_by_driver(rockchip_otp)`):DT **无 OTP 节点** → 找不到 efuse device → 返回 -1 → initcal hang。**主线 OTP 驱动已认 `rockchip,rk3506-otp`(用 rk3568 read),vendor OTP 基地址 `0xff4f0000`**(从 `.alientek-rk3506.dtb.dts.tmp` 取)。

**修复(已重编,待上板验进提示符)**:`rk3506.dtsi` 加 `otp: otp@ff4f0000 { compatible = "rockchip,rk3506-otp"; reg = <0xff4f0000 0x4000>; }`,`rk3506-u-boot.dtsi` 加 `&otp { bootph-some-ram; }`。照主线 rk3528 最小版(无 clocks)。重编后新 FIT(optee hash 不变,uboot/fdt hash 变)。**备选**(若仍 hang = OTP probe 强制要 clocks):把 vendor 三行 `clocks=<&cru 210/209/208>` + `resets` 抄进 OTP 节点。判据:进 `=>` 提示符。

**上板验证彻底成功 🎉(2026-06-14 20:52)**:OTP **无需 clocks**(主线 rk3528 最小版够),`SoC: RK3506B` 打印成功 = `rockchip_cpuid_from_efuse` 读到 = misc_init_r 通过,33 devices/15 uclasses(比 hang 版多 1 OTP device),bootstd 正常扫描,autoboot 倒计时跑过,**停在 `=>` 交互提示符**。**主线 U-Boot 2026.07-rc4 在 ATK RK3506B 真板从上电一路跑到交互 shell** = 方案 B 里程碑彻底达成。剩余 UART 噪声(No bootdevs/Unknown uclass/EFI RNG)正常(没配内核启动目标、NO_NET),无害。

## 方案 B 结论(2026-06-14):里程碑达成,主线 U-Boot 在真板可交互

方案 B(借 vendor SPL/DDR/usbplug,主线 U-Boot proper 走 vendor 格式 FIT)已**完整跑通**。boot 链:`bootrom → vendor idblock(vendor DDR v1.06 + vendor SPL 2017) → 读 NAND uboot 分区(我们 FIT) → 装 optee(0x1000)+uboot(0x800000)+fdt → OP-TEE → NS 跳 0x800000 → 主线 U-Boot 2026.07-rc4 提示符`。

**关键产出(可复用)**:
- `board/aes/fit/rk3506-mainline.its` + `rk3506-mainline.itb`(vendor 格式 FIT 模板,uboot load=0x800000)
- `arch/arm/dts/rk3506.dtsi` 加 OTP 节点(ff4f0000)
- Windows:`D:\DownloadFromInternet\rk3506-uboot-mainline-vendor-fit.itb` + `rk3506-vendor-loader.bin`

**这不是纯主线 boot**(SPL/DDR/op-tee 都借 vendor)。纯主线要等方案 A。

**A. 正经调我们的 SPL**(B 之后):
- 出"调试版 SPL":改 debug UART 时钟假设 / 加早期 print / 试不用 boot_merger(但 RKDevTool 要 usbplug,只能合并 loader)。
- 补 SPI NAND 驱动(defconfig 加 SFC/MTC,SPL 能从 NAND 读 FIT)。
- 无 JTAG,靠迭代构建+烧录。

**之后:内核**。主线内核 v7.0.12 有 rk3506 clk/pinctrl/reset 驱动,但**无 rk3506.dtsi**(SoC DT)——要从 vendor `rk3502.dtsi` 移植(clock-ID 共享 `rockchip,rk3506-cru.h`,适配量小)。

---

## 关键文件 / 路径 / 命令

**主线 U-Boot 源(工作树)**:`third_party/explore/uboot/`
- 板层:`configs/evb-rk3506_defconfig`、`arch/arm/dts/{rk3506.dtsi,rk3506-u-boot.dtsi,rk3506-evb.dts}`
- 产物:`u-boot-rockchip.bin`、`idbloader.img`、`spl/u-boot-spl.bin`、`u-boot.itb`(从 u-boot-rockchip.bin 按 FIT magic 0x7f8000 抽)

**构建命令**:
```bash
cd third_party/explore/uboot
TC=third_party/vendor-sdk/prebuilts/gcc/linux-x86/arm/gcc-arm-10.3-2021.07-x86_64-arm-none-linux-gnueabihf/bin/arm-none-linux-gnueabihf-
RK=third_party/explore/rkbin/bin/rk35
make ARCH=arm CROSS_COMPILE=$TC evb-rk3506_defconfig
make ARCH=arm CROSS_COMPILE=$TC -j$(nproc) \
  ROCKCHIP_TPL=$RK/rk3506b_ddr_750MHz_v1.06.bin \
  TEE=$RK/rk3506_tee_v2.40.bin     # 无 BL31(arm32)
```

**合并 loader(vendor usbplug + 我们 SPL)**:
```bash
cd third_party/vendor-sdk/rkbin
cp ../../explore/uboot/spl/u-boot-spl.bin bin/rk35/rk3506_mainline_spl.bin
cp RKBOOT/RK3506BMINIALL.ini /tmp/m.ini
sed -i 's|^FlashBoot=.*|FlashBoot=bin/rk35/rk3506_mainline_spl.bin|' /tmp/m.ini
./tools/boot_merger /tmp/m.ini   # → rk3506_spl_loader_mainline.bin
```

**RKDevTool 映射**(Loader=合并 loader,uboot=我们 FIT,boot 留空)。判据:UART 首行 `DDR v1.06` + `U-Boot SPL 2026.07-rc4`。

**Windows 产物**:`D:\DownloadFromInternet\`(rk3506-merged-loader.bin、rk3506-uboot-ours.itb、rk3506-vendor-loader.bin、parameter-nand.txt)。

---

## 指针

- `01-2026-06-14-vendor-uboot-build-flow.md`(同目录):vendor 编 uboot 全流程 + 主线映射 + 各 Stage 实证(更细)。
- `../../PLAN.md`:项目方向(8 周首迭代,mainline-first)。
- memory(下个会话自动加载):[[vendor-sdk-atk-bsp]]、[[rk3506-mainline-premises]]、[[vendor-build-pipeline-for-forge]]、+ 本次新增的 bring-up 状态。
- 日志:`document/logs/build-uboot.log`(vendor)、`build-rk3506-stage2.log`(主线 Stage2)、`boot-sdl-*.log/.txt`(上板 UART 抓取)。
