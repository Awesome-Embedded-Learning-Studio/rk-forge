# 27 — "loader 弱写"第三次翻案:U-Boot/Linux 同 flash 对比坐实 **Linux SFC 读 bug**(B);DMA 实验

> ⚠ **二次修正(读完 DMA 结果段再下结论)**:本条前半段我判"B = Linux 读 bug / loader 翻案",
> 被 DMA 实验(24MHz+DMA 仍 -74)+ U-Boot 源码核查(W25N04KV 条目确实查 ECC)推翻。
> **真因回到原 saga:loader 边际写(~8flip,读非确定),ubiprog 必要。** 详见文末"DMA 板验结果"。
> 本次 session 真·新收获是 abort 根因([24](24-2026-06-19-sfc-abort-rootcause-reserved-memory-trust.md) reserved-memory),不是这条。
>
> RW saga 终局:abort(reserved-memory)已修;loader 边际写由 ubiprog 兜(原 saga 对)。本条记绕圈过程 + 教训。

## 一句话结论

**U-Boot 把 rootfs PEB 3/4 读得干干净净(片内 ECC 无错),Linux 读同一片 NAND 同一份数据却报 -74(>8 flip 不可纠)→ 数据是好的,是 Linux 读错了。** "loader 弱写"是 saga 的**第三次误诊**(继 DDR、SFC PIO/DMA 之后),loader 洗清。ubiprog 兜的从来是 **Linux 的 SFC 读 bug**,修了它 ubiprog 就能退役。

## 决定性证据(boot-sdl-202606200014,同一次 fresh-flash、两个读者)

**① U-Boot 读 PEB 3/4 —— 干净**(line 81-88,U-Boot 提示符下):
```
=> mtd read spi-nand0 0x08000000 0x27a0000 0x20000     # PEB 3
Reading 131072 byte(s) (64 page(s)) at offset 0x027a0000   # 无 ECC 错
=> mtd read spi-nand0 0x08000000 0x27c0000 0x20000     # PEB 4
Reading 131072 byte(s) (64 page(s)) at offset 0x027c0000   # 无 ECC 错
```
U-Boot 的 `mtd read` 是 ECC-on(片内 on-die ECC),64 页全读、**零 -74** → 数据 ≤8 flip(被纠了)或零 flip。

**② Linux/ubiprog 读 PEB 3/4 —— -74**(line 458-489):
```
peb=3  full-read uncorrectable → page recovery (5/64 pages)
peb=4  full-read uncorrectable → page recovery (5/64 pages)
peb=5  ... (2/64)   peb=122 ... (2/64)
ubiprog done: rewrote=211 recovered(page-level)=4 skipped(erased)=1177 failed=0
```
Linux 认为这几页 >8 flip 不可纠。

**同片 NAND、同份数据,U-Boot ≤8flip / Linux >8flip → 必有一个读错。片内 ECC 是客观的,错的是 Linux 读路径。** 这正是 [note 14](14-2026-06-18-rootfs-peb34-readpath-bug.md) 那张矩阵(①U-Boot 干净 / ②Linux 爆)+ "反物理铁证"想要的判决,现在 abort 修干净后用**一次同-flash 对比**坐实了。

> 关键:**这次必须 `setenv bootargs console=ttyS0,1500000` 再 bootm**(runbook 手动引导 3 行之一)。
> 上次(boot-sdl-202606200000)我漏了这行,manual bootm 落到 DT chosen 的 `ubi.mtd=5` → 内核自动 attach → ubiprog 流程乱 → rescue shell。修正后(014)ubiprog 正常跑出 recovered=4。

## 机制分析:DLL/频率 还是 PIO/DMA?

### 嫌疑一:DLL 采样 cell / 频率(第一反应,后被否)
同 log 的 DLL 调谐对比(line 82-85 vs 300-303):

| | 实际频率 | DLL 窗口 | 选 cell |
|---|---|---|---|
| U-Boot(SPL) | **100MHz**(target 50M 但 RK3506 clk_set_rate 空操作) | **[0,230] = 230 cell(巨宽)** | 92 |
| Linux | 75MHz(target 80M) | [90,170] = 80 cell(窄) | 130 |

看着像"100MHz 有宽窗(稳)、75MHz 只有窄窗(marginal)"。**但 note 14 早测过:Linux 在 24MHz(无 DLL 调谐、采样裕度最大)读 PEB 3/4 照样 -74** → **读 bug 和频率/DLL 无关**。→ 100MHz 多半也救不了(频率无关)。DLL/频率非根因。

### 嫌疑二:PIO vs DMA(当前头号)
- 我们 DT 有 `rockchip,sfc-no-dma` → Linux **PIO** 读(`read_fifo`,CPU `ioread32_rep` 搬 SFC_DATA)。
- vendor/U-Boot 的 DT **没有** no-dma → **DMA** 读。
- note 14 验过 **ECC 状态处理正确**(0x20=UNCOR)→ 不是 ECC。
- 频率无关(note 14 24MHz)→ 不是采样。
- → **剩下唯一系统差异 = PIO vs DMA**。Linux PIO `read_fifo` 在某些页读出 >8 bit 错(搬运 bug/竞态)→ 片内 ECC 报 -74;U-Boot/vendor 走 DMA 干净。

而 `no-dma` 当初只是"排除 DMA/cache"的 **debug 手段**(见 nand-ecc-debug-handoff:"试 sfc-no-dma 排除 DMA/cache"),**"DMA reads corrupt"从没坐实**——很可能又是误诊(和 DDR/SFC/loader 同病)。

## DMA 实验(进行中,结果待回填)

**镜像**:`update-rwfix-dma.img`(md5 `f4e2dc07`)—— 去 `rockchip,sfc-no-dma` → Linux 走 DMA(对齐 vendor/U-Boot),其余不变(reserved-memory 保留、80MHz、public loader/tee)。
DT 改动:`rk3506.dtsi` sfc 节点删 `rockchip,sfc-no-dma;` 行(实验性 working-tree 改,确认后固化 patch 0013)。

**判据**(板验):
| ubiprog recovered | 结论 |
|---|---|
| **=0**(DMA 读干净) | **PIO read_fifo 是 bug** → DMA 是解 → ubiprog 可退役 + 清掉 no-dma 遗留。一箭双雕。 |
| **>0**(DMA 也 -74) | 不是 PIO/DMA,更深(读 op 序列?mainline vs vendor spi-nand?)。继续查。 |

> 顺带:abort(reserved-memory)已修,DMA 路径的 buffer 从 free pool 分(trust 区已 carve out)→ 不会再踩 OP-TEE 页。所以 DMA 实验不会把 abort 招回来。

## DMA 板验结果(boot-sdl-202606200028)= 否决 B,loader 边际写**回稳**(原 saga 对)

**recovered=5,且这次 DLL 直接 FAIL**(widest 70cell<80)→ fallback **24MHz** → **还是 -74**:
```
rockchip-sfc: dll FAIL: widest=[100,170] (70 cells < 80) @ real 75MHz, fall back to 24000000Hz
peb=3/4/5/122/124 full-read uncorrectable → page recovery
ubiprog done: recovered(page-level)=5
```
→ **频率/DLL/PIO/DMA 全排除**(最宽松 24MHz + DMA 仍炸)。我之前"头号嫌犯 PIO/DMA"作废。

**U-Boot 源码核查**(`uboot/drivers/mtd/nand/spi/winbond.c:483` W25N04KV 条目):用 `w25n02kv_ecc_get_status`(UNCOR→-EBADMSG)→ **U-Boot 确实查 ECC**。所以 U-Boot 读 PEB 3/4 "无错" = 片子告诉它 ≤8flip(不是 lenient 没查)。

→ **同片、同页、两边都查 ECC,U-Boot≤8 / Linux>8 → 唯一合理解释:那几页数据在 ECC 阈值(~8flip)附近,读非确定**(U-Boot 那次读到 ≤8,Linux 那次读到 >8)。

→ **loader 把那几页写边际了(~8flip)。原 saga"loader 弱写/抖动"结论正确。我前面判"B=Linux 读 bug / loader 翻案"是误判(第四次,这次是我)——把 U-Boot 运气读到 ≤8 当成"数据干净"。** 各次 recovered 数(200000=0 / 200014=4 / 200028=5)也印证:loader 写本身非确定,有时全干净、有时几页边际。

## 最终结论(二次修正)

- **loader 边际写真、ubiprog 必要**(原 saga 对)。loader 偶发把 rootfs 某几页写到 ECC 阈值附近,读非确定 → 偶发 >8 → -74 → ubiprog 0xFF 兜底。
- **本次 session 真·新收获 = abort 根因(reserved-memory,[24](24-…))+ 修 + 板验**。这才是生产级的关键修复。
- **系统 work**:ubiprog failed=0 + flash_stress 50/50 过 + abort 修。**接受 ubiprog 当生产解**(loader 边际写是 rkbin blob 的固有抖动,动不了;ubiprog 兜得住,bounded)。
- **no-dma 实验镜像** `update-rwfix-dma.img` 板上也能跑(stress 过),但**没修 -74**(不是 PIO/DMA)。可保留 DMA(对齐 vendor)或回 PIO(原状),二选一都行——不影响生产。

## ATK loader 结果(build-sdl-202606200050)= 换 loader 也救不了,saga 终结

试了 ATK 原厂 loader(`rk3506_spl_loader_v1.06.111.bin` = SPL v1.11 + ATK tee v2.10,镜像 `update-rwfix-atkloader.img`):
**ATK chain 正常启动**(`#charliechen` SPL banner + OP-TEE v2.10 + reserved-memory 生效 + DMA kernel),但 ubiprog 照样:
```
peb=122 full-read uncorrectable → page recovery (2/64)
peb=124 full-read uncorrectable → page recovery (1/64)
```
**ATK loader(v1.11)和 public loader(v1.12)一样把 PEB 122/124 写边际了** → **不是 loader 版本问题,是 rkbin blob / 板+NAND 的通病**。换 loader 无效。

**→ ubiprog 是唯一解,定稿。** saga 终结:abort(reserved-memory)是本次真修;loader 边际写是 blob 通病,ubiprog 兜。候选 A(换 ATK loader)排除。

**别把"第二个读者读到干净"等同于"数据干净"**。当数据在 ECC 阈值附近时,读是非确定的——A 读者这次 ≤8、B 读者这次 >8 完全可能。要判"数据到底干不干净",得 RAW 读 + 逐字节比源(note 14 ① 那种),不能只看某个读者的 ECC 状态裁决。我这次就是吃了这个亏:U-Boot 读干净 → 我判 B → 实际是边际数据 + 读非确定。

## 三次误诊的统一教训(写进 pitfalls 更新)

| 轮次 | 假说 | 被谁推翻 |
|---|---|---|
| 1 | DDR 头号嫌 | 用户"vendor 爆炸写没事"(同 DDR blob/芯片) |
| 2 | SFC PIO/DMA 写路径 | dd-tmpfs 零 NAND 也炸(实际是 abort=reserved-memory) |
| 3 | **loader 弱写** | **U-Boot/Linux 同 flash 对比:U-Boot 干净 → 数据好 → Linux 读错** |

**共性**:**没让第二个独立读者(这次是 U-Boot)上板对比**。saga 全程只在 Linux 侧看 -74,自然把锅扣给"写者"(loader)。一旦拉 U-Boot 当第二个读者,立刻翻案。→ **canonical 方法论:可疑数据损坏,务必双读者(写者×读者矩阵)对比**,别只信一个读者就给写者定罪。

## 相关
- [[sfc-dll-saga-and-writepath]]:saga 主体。**其"loader 弱写/ubiprog 必要"段再次翻案**:loader 写干净,是 Linux 读 bug;ubiprog 兜的是 Linux 读。DMA 修了即可退役。
- [[rootfs-weakwrite-reexam]]:之前用 SR trace(st=0x20)否回"翻案",现在看 SR trace 那次要么是真弱写抖动(偶发)、要么本身被 Linux 读 bug 污染——**主因是 Linux 读**。
- [24](24-…-reserved-memory):abort 真根因(独立,已修)。
- [25](25-…-misdiagnosis):DDR/SFC 两轮误诊(本条是第三轮,同方法论)。
- [pitfalls/05](../pitfalls/05-secure-mem-reservation-imprecise-abort.md):需补"双读者矩阵"这条。
