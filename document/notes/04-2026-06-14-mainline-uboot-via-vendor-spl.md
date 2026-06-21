# 2026-06-14 主线 U-Boot via vendor SPL — 排查与实施笔记

> **一句话**:借 vendor 能干净跑的 SPL,把主线 U-Boot `2026.07-rc4` 装进 vendor 格式的 FIT,在 ATK RK3506B(SPI NAND)真板上跑到**交互提示符 `=>`**。
>
> **诚实的边界**:这不是纯主线 boot——DDR、SPL、OP-TEE 三样都借的 vendor。我们这次真正的贡献是**板层(defconfig + DT)的修正** + 一个**关于 vendor FIT 的结构性发现**。纯主线 boot 要等方案 A(自己的 SPL)。
>
> 这是本次会话(2026-06-14,承接 SPL 崩阻塞)的完整排查记录,按工作实际发生的顺序写,含失败与修正,供审核。

---

## 背景与定位

承接 [02-2026-06-14-mainline-bringup-handoff.md](02-2026-06-14-mainline-bringup-handoff.md) 的状态:主线 U-Boot 能编、binman 出真镜像、DDR v1.06 在板子上跑起来,但**自己的 SPL 在 DDR 之后崩**(全波特率乱码,无 JTAG 难调)。

两条路摆面前:
- **A. 正经调自己的 SPL** —— 难(无 JTAG,靠迭代烧录),慢。
- **B. 借 vendor SPL,先把主线 U-Boot proper 跑起来** —— 快,拿里程碑,给后续兜底信心。

本次走 **B**。定位是"快速里程碑",不是最终形态。

---

## 阶段 0:接续——确认工作树状态

开干前先核实上次的产物/源码/工具都在(工作树可能因跨会话漂移):
- `third_party/explore/uboot/`:HEAD `5ca1a73c`(= 2026.07-rc4),板层 4 文件在,产物在(`u-boot-nodtb.bin`/`u-boot.dtb`/`idbloader.img`/`u-boot-rockchip.bin`)。
- `third_party/vendor-sdk/`:`boot_merger`、`RKBOOT/RK3506BMINIALL.ini`、`make_fit_optee.sh` 在;vendor 构建残留(`uboot.img`/`rk3506_spl_loader_v1.06.111.bin`)在。
- `third_party/explore/rkbin/bin/rk35/`:DDR/SPL/TEE blob 齐。

**结论**:材料齐,可直接进方案 B 的核心未知——vendor SPL 到底要什么样的 FIT。

---

## 阶段 1:摸清 vendor FIT 的真实结构(实证,非猜测)

### 问题
方案 B 的核心技术点:vendor SPL(2017.09)读不懂主线 binman 生成的 FIT。交接文档当时记的是"vendor SPL 不认 sha256 hash → Unsupported hash algorithm",**这是一个假设,没验证**。

### 方法:直接解 vendor 已知能跑的 FIT
不靠猜 vendor `make_fit_optee.sh`/`fit_nodes.sh` 生成什么(那要跑 vendor 构建链),而是直接 dump vendor 已经在板子上证明能加载的 `uboot.img`:

```bash
cd third_party/vendor-sdk/u-boot
./tools/dumpimage -l uboot.img
```

### 实证结构
```
Image 0 (uboot): Standalone Program, load=0x00200000, sha256
Image 1 (optee): Firmware,           load=0x00001000, sha256
Image 2 (fdt):   Flat Device Tree,   sha256
Configuration 0 (conf): firmware=optee, fdt=fdt, loadables=uboot
```

### 关键发现(推翻旧假设)
读 vendor 的 `fit_nodes.sh`:`gen_uboot_node`/`gen_fdt_node`/`gen_kfdt_node` **全都写 `hash { algo = "sha256"; }`**——**vendor 自己就用 sha256**。

所以 "Unsupported hash algorithm" 的真因**不是算法名**,而是**主线 binman 生成的 FIT 在节点结构/命名/conf 定义上,vendor SPL 不认**。

### 结论(决定性)
正解不是"换 hash 算法",而是**用 vendor 原生的 FIT 结构重新打包,只把 uboot 节点里那块二进制换成主线的**。结构 100% 复刻 vendor,只换内容。

> 这一步是本次最有价值的发现——把一个模糊的"hash 问题"收敛成了可操作的"结构复刻"。

---

## 阶段 2:抓出地址坑——TEXT_BASE 不匹配

复刻结构时立刻撞上一个致命点。

| | load 地址 |
|---|---|
| 主线 `u-boot-nodtb.bin` 的 `CONFIG_TEXT_BASE` | **`0x00800000`** |
| vendor FIT 里 uboot 节点的 load | **`0x00200000`** |

差 6MB。主线代码是按 `0x800000` 链接的,若 FIT 写 `load=0x200000`,SPL 把代码装错地址、绝对寻址全错 → 必崩。

### 解法
ITS 里把 uboot 节点的 `load` 改成 `0x00800000`(匹配我们编译),vendor 原来的 `0x200000` 不照搬。其余(optee load `0x1000`、conf 结构)不动。

### OP-TEE NS 跳转的自洽性论证(这是当时最大的不确定)
vendor 的链是 `SPL → optee(0x1000) → 降 NS → 跳 uboot`。optee 跑完后跳哪个地址?
- **若 optee 从 SPL 传入的 loadable 信息取**(标准做法)→ SPL 装我们 uboot 到 `0x800000`,optee 就跳 `0x800000`,自洽。✅
- **若 optee 硬编码跳 `0x200000`**(vendor 原 uboot 地址)→ 我们 `0x800000` 的代码跳空,崩。❌

vendor 的 `tee.bin` 是 rkbin 预编译 blob,源码不在手,**无法事先确定**。只能上板试。备选预案:若崩,把 uboot `load` 改回 `0x200000` + 重编主线 uboot(`TEXT_BASE=0x200000`)对齐 vendor。

> 阶段 4 会证实:**optee 走的是标准做法(从 loadable 取)**,`0x800000` 成立。这个悬而未决的担忧被实测打消了。

---

## 阶段 3:手写 ITS + 打包 + 验证

### ITS 设计
手写 `rk3506-mainline.its`,完全复刻 vendor 结构(阶段 1 实证),改动两处:
- `uboot` 节点:`data` 指向我们的 `u-boot-nodtb.bin`,`load = <0x00800000>`(阶段 2)。
- `fdt` 节点:`data` 指向我们的 `u-boot.dtb`(rk3506-evb)。
- `optee` 节点:`data` 指向 vendor `tee.bin`,`load/entry = <0x00001000>` 不动。

放新目录 `board/aes/fit/`,三个 blob 汇聚进去(uboot-nodtb.bin / u-boot.dtb / tee.bin),ITS 用相对文件名自包含。

### mkimage 选型
用 **vendor 的 `tools/mkimage`(2017.09)** 打包,而不是主线的。理由:与 vendor SPL 字节级兼容(同源工具),`-E` external data 模式是 RK SPL 的读取约定。

### 验证:dumpimage 对照
打出来的 `rk3506-mainline.itb`,`dumpimage -l` 逐项对照 vendor:

| 节点 | vendor | 我们 | 一致 |
|---|---|---|---|
| uboot type/arch | Standalone/ARM | Standalone/ARM | ✅ |
| uboot **load** | 0x200000 | **0x800000** | ✅ 故意改 |
| uboot hash | sha256 | sha256 | ✅ |
| optee type/load | Firmware/0x1000 | Firmware/0x1000 | ✅ |
| optee **hash 值** | `93603ca2...` | **`93603ca2...`** | ✅ 同一颗 tee.bin |
| conf firmware/fdt/loadables | optee/fdt/uboot | optee/fdt/uboot | ✅ |

optee 的 hash 与 vendor **逐字节相同**,证明用的就是 vendor 那颗 tee.bin,没换错。

---

## 阶段 4:第一次上板——banner 达成,但 hang 在 misc_init_r

### 烧板
RKDevTool "下载镜像"模式:Loader=`rk3506-vendor-loader.bin`(vendor 原装,恢复 vendor DDR+SPL 到 boot 区)+ 只勾 `uboot` 分区=`rk3506-uboot-mainline-vendor-fit.itb`,写到 NAND sector 0x2000。

### UART 关键行(document/logs/boot-sdl-202606142037.txt)
```
Trying fit image at 0x2000 sector
## Checking optee 0x00001000 ... sha256(93603ca22c...) + OK
## Checking uboot 0x00800000 ... sha256(0c7f161332...) + OK
## Checking fdt 0x00864f50 ... sha256(08a82c6d3e...) + OK
Jumping to U-Boot(0x00800000) via OP-TEE(0x00001000)
I/TC: Next entry point address: 0x00800000          ← 阶段2的担忧打消
I/TC: Primary CPU switching to normal world boot

U-Boot 2026.07-rc4-g5ca1a73c7d30 (Jun 14 2026 - 18:30:02 +0800)   ← banner 出来了!
Model: Rockchip RK3506 Evaluation Board (ATK RK3506B)
DRAM:  512 MiB
Core:  32 devices, 14 uclasses, devicetree: separate
...
initcall_run_r(): initcall misc_init_r() failed                    ← 失败!
### ERROR ### Please RESET the board ###                             ← hang
```

### 三个核心判断全部命中
1. ✅ "结构不是算法问题"——vendor SPL 顺利验了三个节点。
2. ✅ 地址坑解法对——`load=0x800000` 装对了。
3. ✅ OP-TEE NS 跳转走标准做法——`Next entry point address: 0x00800000`,从 SPL loadable 取,非硬编码。阶段 2 最大风险解除。

### 失败(诚实记录)
banner 之后 `misc_init_r() failed` → hang。没有进到提示符。

> 阶段 4 已经是"banner 里程碑"(主线 U-Boot 在真板跑起来),但还差一口气到"可交互"。这一口就是阶段 5-7。

---

## 阶段 5:诊断 misc_init_r 的根因

### 根因链(读主线 `arch/arm/mach-rockchip/board.c`)
```c
__weak int misc_init_r(void)
{
	...
	ret = rockchip_cpuid_from_efuse(cpuid_offset, cpuid_length, cpuid);
	if (ret) return ret;          // ← 失败点
	...
}
```
`rockchip_cpuid_from_efuse`(同文件)内部:
```c
ret = uclass_get_device_by_driver(UCLASS_MISC,
                                  DM_DRIVER_GET(rockchip_otp), &dev);
if (ret) { return -1; }          // ← 找不到 OTP device → 返回 -1
```
`initcall_run_r` 对返回非 0 的 initcall 默认 hang。

### 为什么找不到 OTP device
查主线 `drivers/misc/rockchip-otp.c` 的 `of_match`:**主线 OTP 驱动已认 `rockchip,rk3506-otp`**(用 `rk3568_data` 的 read 函数)。但我们的最小 `rk3506.dtsi` **没有 OTP 节点** → 没有绑定该驱动的 device → `uclass_get_device_by_driver` 返回 -ENODEV → 链式失败 → hang。

> 这正是 [01-2026-06-14-vendor-uboot-build-flow.md](01-2026-06-14-vendor-uboot-build-flow.md) 第 5 节"待核实"里**早就预警过**的点:"misc_init_r/OTP:是否解引用最小 DT 里没有的 OTP 节点导致 banner 后挂?"——完全命中。预警在先,诊断省力。

### 缺的最后一块拼图:rk3506 OTP 物理基地址
主线驱动认 compatible,但 `reg` 地址要照真实硬件。rk3528 是 `0xffce0000`、rk3568 是 `0xfe38c000`,rk3506 不一样。vendor `rk3502.dtsi` 里 grep 不到 otp(节点名可能不在该文件)。

**从 vendor dtb 预处理产物取**:`u-boot/arch/arm/dts/.alientek-rk3506.dtb.dts.tmp`(dtc 展开的完整 dts)里:
```
otp: otp@ff4f0000 {
    compatible = "rockchip,rk3506-otp";
    reg = <0xff4f0000 0x4000>;
    ...
    otp_id: id@a { reg = <0x0a 0x10>; };   ← cpuid 偏移 0x0a, 长 0x10(与 rk3568 一致)
}
```
**rk3506 OTP 基地址 = `0xff4f0000`,size `0x4000`,cpuid @ `0x0a`。**

---

## 阶段 6:加 OTP 节点 + 重编

### 两处 dtsi 改动
1. `arch/arm/dts/rk3506.dtsi`(SoC 级,OTP 是 SoC 硬件)——在 `ioc_grf` 后加:
   ```dts
   otp: otp@ff4f0000 {
       compatible = "rockchip,rk3506-otp";
       reg = <0xff4f0000 0x4000>;
       #address-cells = <1>;
       #size-cells = <1>;
   };
   ```
   (用 2-cell `reg`,因为我们 dtsi 根节点 `#address-cells=<1>`,与 vendor 一致;非主线 rk3528 的 4-cell。)

2. `arch/arm/dts/rk3506-u-boot.dtsi`——加 bootph 标签(照主线 rk3528 惯例,u-boot proper 阶段启用):
   ```dts
   &otp {
       bootph-some-ram;
   };
   ```

### 一个判断:不带 clocks
vendor 的 OTP 节点带 `clocks=<&cru 210/209/208>`,但**主线 `rk3528-u-boot.dtsi` 的 OTP 节点不带 clocks**(`compatible = "rockchip,rk3528-otp"; reg = <...>;` 就这两行),而 rk3528 是主线正常工作的板。rk3506-otp 与 rk3528-otp 共用同一份 `rk3568_data`(同一 read/probe 路径)。

**推断**:OTP 驱动 probe 不强制 clocks。先不带(最小改动),不行再加。→ 阶段 7 证实**无需 clocks**,判断成立,省了一轮迭代。

### 重编 + 重打 + 验证
```bash
make ARCH=arm CROSS_COMPILE=$TC -j$(nproc) ROCKCHIP_TPL=... TEE=...
# DTC arch/arm/dts/rk3506-evb.dtb  ← dtb 重编(含新 OTP 节点)
# BINMAN .binman_stamp              ← 干净通过
```
验证新 `u-boot.dtb` 含 OTP:`dtc -I dtb -O dts u-boot.dtb` 显示 `otp@ff4f0000 { ... bootph-some-ram; }`。

重打 FIT(`mkimage -f rk3506-mainline.its -E`):uboot/fdt 的 hash 变(blob 更新),**optee hash 不变**(`93603ca2...`,tee.bin 没动)。Windows 副本覆盖同文件名(配置不动)。

---

## 阶段 7:第二次上板——进提示符,里程碑达成

### UART 关键行(document/logs/boot-sdl-202606142052.txt)
```
U-Boot 2026.07-rc4-g5ca1a73c7d30 (Jun 14 2026 - 20:47:09 +0800)
Model: Rockchip RK3506 Evaluation Board (ATK RK3506B)
SoC:   RK3506B                          ← 新!misc_init_r 成功,OTP 读到了
DRAM:  512 MiB
Core:  33 devices, 15 uclasses          ← 比 hang 版多 1 device(OTP)+ 1 uclass
...
Hit any key to stop autoboot: 0         ← bootstd 正常
Scanning for bootflows in all bootdevs
(0 bootflows, 0 valid)                  ← 没配内核,扫到 0 是预期
=>                                      ← 交互提示符!
```

### 成功的铁证
- **`SoC: RK3506B` 打印出来** = `rockchip_cpuid_from_efuse` 成功读到 SoC ID = OTP 节点 probe 成功 = misc_init_r 通过。OTP 修复完美命中,**且无需 clocks**(阶段 6 的判断成立)。
- **33 devices / 15 uclasses**(上版 32/14)——多出来的就是 OTP device,被 driver model 绑定。
- **停在 `=>`**——主线 U-Boot 从上电一路跑到交互 shell。

### UART 噪声(正常,非问题)
`No bootdevs for mmc0` / `Unknown uclass 'nvme'/'scsi'/...` / `Missing RNG device for EFI_RNG_PROTOCOL` ——这些都是因为没配内核启动目标、`CONFIG_NO_NET` 没网卡、没 EFI 用途。无害。嫌吵后续可在 defconfig 关 EFI/bootstd 相关项。

---

## 产出清单

### 改动的源文件(主线 U-Boot 工作树)
| 文件 | 改动 | 性质 |
|---|---|---|
| `arch/arm/dts/rk3506.dtsi` | 新增 `otp@ff4f0000` 节点 | **本次新增**(修 misc_init_r) |
| `arch/arm/dts/rk3506-u-boot.dtsi` | 新增 `&otp { bootph-some-ram; }` | **本次新增** |

(板层其他文件 `evb-rk3506_defconfig`/`rk3506.dtsi` 主体/`rk3506-evb.dts` 是之前会话建的,本次未改。)

### 新产出物
| 路径 | 内容 |
|---|---|
| `board/aes/fit/rk3506-mainline.its` | 手写的 vendor 格式 FIT 源(可复用模板) |
| `board/aes/fit/rk3506-mainline.itb` | 打包好的 vendor 格式 FIT(547 KB) |
| `board/aes/fit/{uboot-nodtb.bin,u-boot.dtb,tee.bin}` | 三方汇聚的 blob |

### Windows 侧(给 RKDevTool 烧板用,`D:\DownloadFromInternet\`)
| 文件 | 角色 |
|---|---|
| `rk3506-uboot-mainline-vendor-fit.itb` | 方案 B 的 FIT(本次,进提示符版) |
| `rk3506-vendor-loader.bin` | vendor 原装 loader(vendor DDR+SPL+usbplug) |
| `parameter-nand.txt` | NAND 分区表(uboot @ sector 0x2000) |

### 日志
- `document/logs/boot-sdl-202606142037.txt` —— 第一次上板(banner + hang)
- `document/logs/boot-sdl-202606142052.txt` —— 第二次上板(进提示符,里程碑)

---

## 可复用知识沉淀(本次的 takeaway)

1. **vendor SPL 读不懂主线 FIT,是结构问题不是 hash 算法问题**。vendor 自己也用 sha256;正解是复刻 vendor 的 FIT 节点结构,只换 uboot 二进制。验证手段:`dumpimage -l` 直接解 vendor 已知能跑的 FIT。
2. **OP-TEE 的 NS 跳转地址走标准做法**(从 SPL 传入的 loadable 取),不是硬编码。所以 uboot 的 `load` 可以对齐自己的 `TEXT_BASE`(这里是 `0x800000`),不必复刻 vendor 的 `0x200000`。实测 `I/TC: Next entry point address: 0x00800000` 证实。
3. **主线 OTP 驱动已认 `rockchip,rk3506-otp`**(共用 `rk3568_data`)。rk3506 OTP 基地址 `0xff4f0000`,cpuid @ offset `0x0a`。**probe 不需要 clocks**(主线 rk3528 最小节点即工作)。
4. **RK 的 `misc_init_r` 失败会 hang**(initcall 默认行为),不要指望它容错——DT 缺 efuse/OTP 节点就直接卡死 banner 之后。
5. **RKDevTool "下载镜像"模式可以一次同时**:Loader 字段写 boot 区(恢复/换 idblock)+ 逐分区写(只勾要换的)。方案 B 用 vendor loader 恢复 vendor SPL + 只写 uboot 分区,一步到位。
6. **dumpimage / dtc 是最可靠的结构取证工具**,优于读生成脚本猜行为。这次两次靠它拍板(vendor FIT 结构、OTP 节点地址)。

---

## 边界与诚实声明

- **这不是纯主线 boot**。boot 链前半段(`bootrom → DDR → SPL → OP-TEE`)全部是 vendor 的;我们只换了后半段的 U-Boot proper(主线 `2026.07-rc4`)。
- **主线 U-Boot 的运行依赖 vendor SPL 准备的环境**(DDR 活、进 NS 世界)。这与纯主线(自己的 SPL 从 SRAM 起自己初始化 DDR)是两回事。
- **自己的 SPL 崩(全波特率乱码)的坑仍在**,本次没有碰。那是方案 A 的事。
- 本次只是**里程碑**:证明"主线 U-Boot proper 在 RK3506B 真硬件上能完整启动到交互 shell"。下一步要么走方案 A(纯主线 boot),要么借这个能跑的 U-Boot 直接推内核(主线内核缺 `rk3506.dtsi`,要从 vendor 移植)。

---

## 指针

- [02-2026-06-14-mainline-bringup-handoff.md](02-2026-06-14-mainline-bringup-handoff.md) —— 活的交接文档(本次成果已同步进去)。
- [01-2026-06-14-vendor-uboot-build-flow.md](01-2026-06-14-vendor-uboot-build-flow.md) —— vendor 构建链技术参照(第 5 节"待核实"的 misc_init_r 预警,本次应验)。
- memory:`mainline-uboot-bringup-state`(状态)、`vendor-build-pipeline-for-forge`、`rk3506-mainline-premises`。
