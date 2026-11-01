# 119 — GMAC fabric wedge 反击轮：open 前重整装 + 新事实（2026-11-01）

> 接 118。用户拍板「既然钉死，直接尝试修复」。本轮产出：两张新补丁（0028 正式 +
> 0029 TEMP）、一次待跑板实验；以及三组改写认知的新事实。探针内核 `-00026`（26 张）。

## 1. 本轮新事实（改变假说格局的三组）

### 1.1 probe 段那 25 笔 MDIO 不是总线扫描，是 RTL8211F 的分页配置序列

8.txt 0.9979–1.0007s 的读写序列（read31 → write31 → write16 → … → write13/read14
×3 MMD 间接访问）是 realtek 驱动的分页访问（reg31=0x1f 是页寄存器，13/14 是 MMD
ADDR/DATA）。**open 段死掉的第一笔 read phy=1 reg=31 与 probe 段第一笔完全同源**
——同一个函数跑两次：probe 一次全过，open 第一次 readl 就楔。

### 1.2 9-b 的死点修正：不是「第 9 笔死」，是「某笔完成后、打印打到一半 fabric 死」

9-b 尾部（`9-b.txt:387-391`）：read reg29 的第二轮 wait **通过了**，`xfer done` 打印
输出到 "xfer " 被掐断——CPU 在 fabric 扩散性死亡期间死在控制台排水/下一笔
`readl(MII_DATA)` 途中。结论：**fabric 是逐步死的，GMAC 从口是第一张倒的多米诺，
但不是瞬间全 SoC 死**（与 dsh-005 §1.1 一致，且更精确了）。

### 1.3 9-b 的 UART 时间戳乱码落在 `rk_gmac_powerup()` 的时钟/GRF 写窗口

`9-b.txt:332`：`[    1.8ʢº²] ... init for RGMII_RXID` ——时间戳字节损坏，位置恰在
gmac_clk_enable(true)（bulk 时钟 + io_clksel GRF + rmii ungate + mdelay(5)）与
php_grf CON0/CLK_CON1 写之间。8.txt 同窗口干净。→ **GMAC 时钟/GRF 配置动作本身
会间歇性 glitch 板级信号**（电气线证据 +1，但仅在 4 核慢启动轮出现过一次）。

## 2. 排除的假说（本轮证伪/分流）

| 假说 | 判决 | 依据 |
|---|---|---|
| 主线 DT 时钟表缺项 | **死** | vendor rk3588.dtsi gmac0 时钟表与主线逐项一致（125M/50M/pclk/aclk/ptp_ref + SRST_A + PD_GMAC） |
| vendor 有 PHY reset 脚 | **死（0025 保住）** | vendor 板级 dts 的 `reset-gpios = <&gpio1 RK_PB2>` 属于 &pcie3x4（NVMe），gmac0 只有死的 `snps,reset-*` 属性（无 gpio phandle，不生效） |
| vendor CSU 安全门控是差异点 | **死（本板）** | vendor gmac_clk_enable 里有 `rockchip_csu_disable(csu_aclk/pclk)`（SIP SMC 进 EL3 配总线），但 vendor rk3588.dtsi **没有任何 `rockchip,csu` 引用** → 本板上 CSU 调用是死代码 |
| io_clksel 极性翻转 | **死** | 主线 rk_configure_io_clksel 对 rk3588 id0 得 cru=bit4 置位，与 vendor SELET_CRU 一致 |
| 「MDIO 闲置 N 毫秒后下次访问必楔」 | **死** | 9-b 以 ~200µs 节奏连续访问，无空档，照样死 |

## 3. 找到的真实主线-vs-vendor 差异（0028 的内容）

1. **延迟线使能**：vendor `DELAY_ENABLE_BY_ID` 条件式（delay 值非 0 才使能该线）；
   主线 rk3588 无条件双开。本板 rgmii-rxid + rx_delay=0 → vendor 关 RX 延迟线，
   主线开着（值 0）。已改为条件式。
2. **clks_config 未接线**：主线 dwmac-rk 的 bulk 时钟（aclk/pclk）只在 probe 时的
   gmac_clk_enable() 开一次；runtime/system PM 走 stmmac_bus_clks_config() 只管
   stmmac 核心两钟，`plat->clks_config == NULL`。已接线到 gmac_clk_enable()
   （dsh-005 §7.2 修复 A 的落点）。
3. 先例确认：stmmac 核心 probe 时本来就脉冲 SRST_A_GMAC0（stmmac_main.c:7914
   区域），remove 时 assert 后**不复位**（:8183）——0029 在 open 前脉冲一次有先例、
   安全。

## 4. 本轮补丁（-00025 = 26 张）

- **0028（正式）** `net: stmmac: dwmac-rk: wire clks_config, make RK3588 delay
  lines conditional` —— 上述差异 1+2。
- **0029（TEMP，结案删）** open 入口战地补丁：canary readl(MII_ADDR)（就是凶器
  寄存器）+ pm 状态打印 + `clks_config(false) → SRST_A 脉冲 → clks_config(true)`
  全套重整装 + 每时钟 `__clk_is_enabled` dump + php_grf CON0/CLK_CON1 dump。
  目的：死不死都有判决性数据。

## 5. 板上轮次（-00026，tftp 免烧录）

NFS 轮为主判。判读表（含 canary 双读后的细分）：

| 现象 | 判定 | 下一手 |
|---|---|---|
| 全启动、eth0 up、可 ping | 主病被重整装压住（或延迟线差异就是根因） | down/up ×20 + 65s idle + 压测；然后瘦身 0029 找最小修复 |
| 死在 `DBG25 open-entry`：MII_ADDR 楔但 GMAC_CONFIG 前一行有值 | MDIO/PHY 时钟域挂（dsh-006 E2 判别式） | PHY refclk/电源测量；读 RTL8211F 侧 |
| 死在 `DBG25 open-entry`：两个 canary 都没打出来 | AXI/域层挂（状态在 probe→open 间劣化，非 PM 路径） | 重整装挪早（mdio_register 尾）；clk notifier 抓「谁关的钟」 |
| 死在重整装序列中间（re-arm 打印后、post-rearm 前） | clk cycle/复位脉冲本身触发 → 强指向 GRF/时钟写瞬态（7f864458e9a6 同族，电气线加重） | 示波器/换板；SRST 脉冲拆开 A/B |
| post-rearm 好的、init_phy 首笔 MDIO 仍楔 | 触发器在 MDIO 事务本身（PHY 侧/引脚域） | PHY 电源/refclk 测量；mdio 写方向单独打点 |

镜像坐标：`out/rk3588-topeet/{boot.img,tftpboot/boot.img}`（cmp 一致），
版本串 `7.1.0-00026-g3b258a84e951`，replay `8cd9520d → 3b258a84`（26 张全绿），
Image 内五条 DBG25 串齐全。canary 为 A/B 两行独立打印（MII_ADDR 与 GMAC_CONFIG
分开），楔哪个寄存器从日志直接可见。

## 5b. dsh-006（上游 lore 检索）判决摘要

- **我们是上游孤例**：dwmac-rk.c 全 commit 史（~90 条）+ linux-rockchip 归档 +
  bugzilla/GitHub 全搜，无「RK3588 first-open MDIO readl 永不返回」同款。
- **机理最近的证据链**（Synopsys databook 原文）：ef43e513/367f1854d442（6.15）
  「软件复位完成需要全部时钟在跑；PHY 掉电时可停其输出时钟」；36d18b5664ef
  「DMA reset depends on the RX clock, otherwise timeout」——RGMII 下 RXC 由
  RTL8211F 供。上游表现=超时，我们=总线不返回，深一层。
- **同族先例**：7f864458e9a6（RK3576：GMAC 时钟关后写 GRF 整机挂死，是否挂死取决
  于别的设备恰好开没开钟——纯时序耦合，与 maxcpus=4 漂移呼应）；Armbian
  linux-rockchip#547（RK3588 gmac1 MDIO 与 MAC soft reset 竞态写坏 PHY ANAR）。
- **vendor/主线驱动+DT 寄存器级全同**，无 QoS/NoC 私有防挂死代码。唯一系统性差异：
  **主线 rk3588 带 PSCI cluster 级 idle states（rk3588-base.dtsi:244），vendor
  6.1 没有**。注意：dsh-005 引 5.txt「cpuidle.off=1 仍挂」判死过 idle 线，但 5.txt
  是 -00020 发明脚年代的轮次，证据污染——**cpuidle.off=1 值得在 -00026 上重测**。
- RK3588 NoC/GMAC 勘误无公开文本（TRM 走 NDA）。
- 全文：`dyn/dsh-006-lore-search.md`（每条 URL 锚定）。

## 5c. Round 10（-00026）判决（2026-11-01 午）

**死点又搬家了：死在 probe 段第 6 笔**（`10.txt:351-355`）：read reg31 的 poll
完成后，`xfer done` 打印打到 `(uniniti` 被掐断（1.027352）——与 9-b 完全同型的
「打印中途 fabric 断流」死法。0029 的 open 入口机器根本没执行到。

**两个硬结论：**

1. **「probe→open 之间状态劣化」假说族全灭**。楔死不需要那个窗口——纯 probe 连发
   （~110µs/笔节奏）照样死。病是 MDIO 读轮询期间的**活竞争**：大量读通过、某一次
   点燃 fabric。
2. **并发子系统必要条件几乎清零**。round 10 死时 1.027s，系统里 eMMC（r8 是
   1.119）、cpufreq（1.153）、VOP 扫描（1.53）、GPU（1.6）、Goodix（1.73）
   **全都还没跑**。死亡时刻的不变常量只剩：MDIO 读轮询本身 + 其他 CPU 空闲
   （WFI/PSCI 深睡）+ FIQ 控制台。VOP/GPU/mmc/cpufreq 并发论出局。

**延迟线洗清**：U-Boot（已知良好，tftp 每轮在用）对 RGMII_RXID 传 rx=0 →
条件使能 → **同样关 RX 延迟线**（`dwc_eth_qos_rockchip.c:861-862` 的模式开关 +
DELAY_ENABLE 宏）。round 10 的 GRF 状态与 U-Boot 完全一致，probe 死亡不是 0028
引起。vendor 侧同判：powerup 对 RXID 也强制 rx=0。

**9-b 的 UART 时间戳乱码重估**：`1.8ʢº²` 是格式化时间戳的**内存字节损坏**而不只是
UART 信号毛刺——无 ECC DDR 位翻转 + AXI 楔死，两件事都指向一次**电源轨/物理层
扰动**。B 线（供电轨/共病）权重回升。

**probe 连发死亡的全部样本**：9-b（maxcpus=4，~#9-11 死）、10（8 核，#6 死）、
8/9-a/终局（8 核，25 笔全过）——按轮次漂移，非确定。

## 5d. Round 11/12 判决 + Round 13/14（2026-11-01 午后）

**Round 11（-00026 对照重跑）**：probe 段这次**全过**（round 10 的 probe 死不可
复现——按轮漂移），死在 open 入口：`post pm_runtime_resume` 打完，**canary A 都
没出来**——open 入口第一笔 readl(MII_ADDR) 就楔死。受害 CPU5（watchdog
"on cu 5"，NMI 发向 5）。楔后其他 CPU 又正常跑了 0.5s（Goodix/USB/rtw88 全打完）
——单核先楔、fabric 渐死的经典形状。

**Round 12（+cpuidle.off=1）**：多走一步——**canary A 成功**：
`open-entry A (MII_ADDR): rpm=0 val=0x00000104`（凶器寄存器当时是活的，busy=0），
然后死在 **canary B（GMAC_CONFIG @ +0x0，与 MDIO 无关的普通寄存器）**。受害 CPU4。

**判决：**
1. **cpuidle 深睡假说死亡**——禁掉深睡照样死在同一窗口。
2. **「每次读掷硬币」实锤**：同一从口、间隔 ~8µs 的两笔读，第一笔返回 0x104、
   第二笔永不返回。不是某个寄存器/某个时钟域坏了，是该从口的 AXI 读按概率楔。
3. 受害核全是大核（CPU5/CPU4），open 路径被调度到大核执行。
4. 0029 的重整装至今没得到执行机会（楔点总在它之前 1-2 笔读内）。

**Round 13/14（免编译，tftpboot 已备料）：**
- **R13**：-00026 + `maxcpus=1`——单核、无 SMP 并发（最接近 U-Boot 的单线程世界）。
  活 → 多核并发是必要条件；死 → 触发器单核可达。
- **R14（分水岭）**：**vendor 5.10 内核 + vendor DTB** 走同一 U-Boot/BL31/tftp 链
  （`tftpboot/{vendor-Image,vendor-topeet.dtb}` 已就位，booti 启动）。同一块板、
  同一引导链、同一根网线，唯一变量=内核软件栈：
  - vendor 也楔 → 板/硅片/BL31 级问题，主线软件无罪，转示波器/换板/换 BL31；
  - vendor 活 → 病在主线软件栈，开始真刀真枪的主线-vs-vendor 内核二分
    （下一个低成本混合轮：主线 Image + vendor DTB）。

## 5e. R14/R16/R17 判决 + vendor-vs-mainline 状态 diff（2026-11-01 晚）

**R14（vendor 5.10 内核 + vendor DTB，同一 U-Boot/BL11/板）**：eth0=gmac1 正常起、
`devmem 0xfe1b0000` 返回 0x00000000 不楔；**30 万次裸读 gmac0 全活** →
板/硅片/BL31/U-Boot 全部无罪释放。

**R16（主线 -00026，eMMC+sh，idle ~10s 后）**：**第一发** `devmem 0xfe1b0000`
即 SoC 楔死 → 驱动序列论死刑（无驱动在场），「idle 后首读必楔」实锤。

**R17a（主线 idle 快照）**：gmac0 全部时钟 enable 计数 ≥1、域 on、设备 active
——账面全绿仍楔；顺带 `devmem 0xfe1c0000`（gated 的 gmac1）触发级联=预期行为。

**vendor-vs-mainline idle 状态 diff（本轮核心资产）：**

| 项 | vendor(活) | 主线(楔) | 判 |
|---|---|---|---|
| php_grf CON0 接口选择 | **0x208**（gmac0+gmac1 都=RGMII） | **0x000**（双双被清零！） | **主嫌疑** |
| php_grf CLK_CON1 | 0x210（CRU+DIV1，双 MAC） | 0x18（CRU+**DIV50**，div 从未按 vendor 设 DIV1） | 次嫌疑 |
| sys_grf CON7/CON8 延迟线 | TX@0x44 开/RX 关 | 同（0028 之功） | 一致 ✓ |
| mclk_gmac0_out | 0/0 | 0/0 | 红鲱鱼出局 |
| clk_gmac_50m | **enable=0**（RGMII 下 vendor 关着照样活） | enable=1（0027 critical 多余无害） | 出局 |
| 125M/pclk_gmac0/aclk_gmac0/ptp_ref | 计数同 | 计数同 | 一致 ✓ |
| genpd gmac 域 | on | on | 一致 ✓ |

**统一假说（当前最优）**：probe 时 CON0 是 RGMII（U-Boot 写的 + MAC 读回
"Active PHY interface: RGMII (1)"佐证），**之后 [1.03s,~3s] 之间被不明者清零**；
接口选择=000（GMII/MII 类模式）下 GMAC 的 io 岛时钟安排失效 → CSR 读跨域握手
悬挂 → AXI read 永不完成。时间窗与「1.74s NFS open 首读必死」「manual idle 首读
必死」「probe 连发偶发死（清除者竞态）」全部吻合。树内无第二家 php_grf 写者，
清零者待抓（候选：watchpoint/GRF 写跟踪探针内核）。

**R18 判决（盲修轮）**：①shell（~2.2s）时 CON0 **已经**是 0x00000000——清零
发生在 [1.03s, 2.2s]；②php_grf 读安全（返回 0）；③**`devmem 0xfd5b0008 32
0x00380008` 写入瞬间整机挂死**——坏状态下往 GMAC 接口选择位做 GRF 写=死，
与 RK3576 fix 7f864458e9a6（「GMAC 时钟状态不对时写 GRF → 整机挂死」）同族。
盲修路线不通：必须在进入坏状态**之前**阻止它。

**combphy 撞库假说（验尸）**：rk3588 naneng-combphy 只写自己节点内的
phy_grf/pipe_grf，共享 php_grf 的 php-grf 段仅存在于 rk3576 表（注释）。
rk3588 树内 php_grf 写者=仅 dwmac-rk 一次。**修正**：之前「树内无第二家写者」
的 grep 实际没跑成（zsh glob 错误），本轮已正确重验。

**当前主假说（v3）**：php_grf/GMAC0 io 岛随某个 php 族电源域断电而失电/隔离
——失电后 CON0 读回 0（复位态）、gmac0 CSR 读楔、GRF 域写楔。佐证：
vendor genpd 里 `sdmmc` 域 on（eMMC 在用），主线 `sdmmc` 域 off-0（主线 eMMC
节点没挂域，域被当 unused 关掉）——两侧 php 族域状态不同。待验：
php_grf 失电说与 CLK_CON1=0x18 相容 iff 0x18 是其复位默认值（TRM NDA 查不到）。


**R19 判决（pd_ignore_unused）**：shell ~17s 时 `devmem 0xfd5b0008`（php_grf 读，
默认参数下一直安全的操作）**也触发 fabric 级联死亡**——pd_ignore_unused 改变了
致死面而不是消除它。另见 11.9s 的 `sync_state() pending due to
fdb50000.video-codec …` ×9（video-codec/rga 无驱动未绑定，pm-domain 供应商
sync 一直悬置）。shell 考古信息增益递减，转仪器化。

**0030 探针内核（-00027）**：subsys_initcall 起、每 100ms 读 php_grf CON0/
CLK_CON1 + GMAC0 GMAC_CONFIG 并带 printk 时间戳打印，CON0 变值打 FLIP 横幅。
100ms 分辨率夹住「接口位丢失瞬间」和「第一笔楔死 GMAC 读瞬间」，与驱动 probe
日志对齐。R20（NFS 轮）出数。

**R20 判决（-00027 探针内核 v1，日志 13.txt）**：两个改写案情的事实：
1. **0.92s 时（dwmac probe 之前）CON0=0x0008、CLK_CON1=0x0010——U-Boot 写的良好
   值还在**。对照 R17a idle 读到的 CON0=0x0000、CLK_CON1=0x0018：php_grf 在
   1.03~2.2s 之间**整个寄存器堆被打回复位默认值**（0 与 0x18 即复位值）——
   不是「有人清了接口位」，是 **php_grf 块被复位/掉电**。R18 写接口位秒死 =
   往复位态的 GRF 写触发挂死（RK3576 同族）；读返回复位值正常。
2. 本轮死在 **1.009s**（史上最早，dwmac probe 之前、CON0 未翻），且 v1 轮询器
   每 100ms 读一次 GMAC_CFG——**这个读本身是污染变量**（其 0.925s 首读与
   85ms 后的死亡可能存在慢导火关联）。

**v2 探针（-00027 g6f0570a3）**：20ms 轮询、只读 php_grf CON0/CLK_CON1 +
PMU 电源域状态字 0x00-0x0c、变化打横幅、**不碰 GMAC**（NFS 轮自己的 open 当
致死探针）。目标：php_grf 掉回复位态的精确毫秒 + 是否伴随 PMU 域状态翻转，
与驱动 probe 日志对齐锁定案发时刻。

**R21 判决（-00027 v2 探针，日志 14.txt）**：**php_grf 全程稳在 U-Boot 良好值
（CON0=0x0008/CLK_CON1=0x0010）、PMU 0x00-0x0c 零变化，仍死于 open（1.8157s，
RxQ 打印都没出，受害 CPU2，NMI/stop 失败）**。结论：php_grf 复位像是 cleanup 后
的伴生状态（状态 B），非 NFS 轮凶手；真凶=状态 A（onset∈(0.925,1.815)）。

**GPT 二轮反馈核验（三条硬锚点全属实）**：
1. PMU 域状态真偏移在 0x110~0x290（域 on/off=+0x290 repair 位，GMAC=bit21），
   v2 采样的 0x00-0x0c 无效 → 「PMU 无变化」结论作废，需 v3 重取；
2. SRST 后有 udelay(10)（「无延时」表述收回）；RXC 条款只适用于 MAC/DMA 软复位
   而非 CRU SRST——SRST 假说保留但论证降档，A/B 才算数；
3. fc900000=mmu600_**pcie**（fcb00000 才是 php，默认 disabled）——「php SMMU」
   标注错误，SMMU 线降权为「共享互联间接影响」。
4. 「已判死」收窄：R16 只排除 open/phylib 是**扳机**，不排除 probe 序列/DT 是
   **状态建立者**；vendor 的正常收发在 GMAC1，对 GMAC0 只证明 CSR 可访问。
5. R21 死点「纯 RAM 段」表述过强：RxQ 打印前有 page_pool/dma_alloc_coherent/
   调度/中断，受害上下文未定。

**v3 探针（-00027 g6fb57648）**：20ms 轮询 php_grf CON0/CLK_CON1 + PMU
{0x110,0x118,0x120,0x150,0x1f8,0x290}（变化打横幅）+ 每 200ms 金丝雀
（try 打印→readl→ok 打印，双括弧夹住首个不返回访问，受害者=已知上下文的
工作队列线程）。R22 出数。

**R22 判决（-00027 v3 探针，日志 15.txt）——翻转抓到现行**：
- 1.076→1.34：PMU1f8 低 8 位持续翻动（域表核对：bits 0-7 **不映射任何 genpd 域**，
  是 CPU/DSU 类内存岛的活动噪声，与 php 无关）
- **1.2207：GRF008 8→0、GRF070 10→18（php_grf 打回复位像）**；PMU150=0x11 稳
  （php bit5/gmac bit6 电源请求始终 0）、PMU290 php/gmac repair 位始终 on、
  0x1f8 的 php/gmac mem 位（29/30）始终 0（内存未门控）——**php_grf 复位不是
  任何 PMU 可见电源域动作**
- ~1.35：轮询器自身遇难（第三次 canary 的 try 都没打出——卡在前置 GRF/PMU 读，
  或 work 未再调度，不可区分）
- 5.567：open 照死（受害 CPU1=A55 小核！「大核专属」模式证伪）
- 翻转窗口案发名单（15.txt 原文）：1.198 cpufreq CPU6 首换频 → 1.203-1.207
  video-codec iommu group + **rockchip-drm 绑定 VOP/DSI** → [1.2207 翻转] →
  1.304 USB 新设备

**GPT 三轮修正（全部吸收）**：双状态模型作废（翻转在 open 前 4.3s 的驱动初始化期
就发生）；PMU 采样未见 php/gmac 掉电=「非持续掉电」证据增强；探针先于 open 遇难
且卡点未定；panic 栈是报告核（CPU0）的不是受害核的。偏移核实：rk3588 pwr 基址
0x14c+域 p_offset（php/gmac 在 0x150 ✓）、mem_status 0x1f8（bit=1=已门控）、
repair 0x290。**PHP 系软复位（SRST_P_PHPTOP_CRU 575 / SRST_P_PHP_BIU 288 /
SRST_A_MMU_PHP 306）树内无任何驱动/DT 消费者**——软件侧可查的行为者全部排除。

**v4 探针（-00027 g086cba84）**：CPU0 专属 kthread 1ms 轮询 CON0 + 20ms 全 PMU 组
（补 0x14c/0x1a4）+ 200ms 金丝雀；每次读前后写阶段日志簿（seq/stage），另一
上下文的冻结侦测器在日志簿停摆时广播 `JOURNAL FROZEN seq=N stage=S`——楔死
发生在哪一步读、哪个寄存器，即使受害核永不返回也能从日志得知。R23 出数。

**R26 判决（headless 轮，日志 17.txt）——案件告破到家族级**：0031 禁用显示全家
（VOP2+MMU+DSI2+DCPHY+面板）后：**php_grf 翻转横幅消失、金丝雀一路 ok、eth0
open 首次活着走过**（NFS 未挂上是新问题，见 §5f）。**凶手=显示上电路径**。
头号嫌疑（待家族内二分）：0009 给 &vop 加的 reset 组（SRST_A/H/D_VOP*——VOP2
enable 路径会 assert/deassert 它们，若其中有 ID 错位=乱复位）、0001 OOT 面板
驱动、DSI2/DCPHY 控制器上电序列。R22 已证翻转在 drm bind VOP+DSI 后 13ms。

## 5f. 新章：链路全通（R27 判决，2026-11-01 午后）

R27（headless -00026 g8794a551，eMMC 手动轮）：`ip link up` 完整走通（RxQ/
PHY attach/PTP/configuring rgmii-rxid），**12.5s Link is Up 1Gbps/Full**，
ping PC 五发全中（稳态 0.4ms）。**主线内核以太网端到端首次全通。**

NFS 挂载失败的原因也随之清楚：**链路训练需 ~4s**（open 后 4.1s），NFS 轮的
ipconfig 在 1.7s 起跑等不到。R28=NFS 轮耐心等 2-3 分钟验证。

## 5g. 收尾路线图

1. R28：NFS 轮 + 耐心 → 若挂上=**原始目标（NFS root 迭代引擎）达成**
2. 显示家族二分恢复显示：逐个恢复 vop / vop_mmu / dsi0 / mipidcphy0 /
   面板，以 DBG30 CON0 翻转横幅+eth0 存活为判据；头号嫌疑=0009 的
   &vop reset 组（SRST_A/H/D_VOP*）与 0001 面板驱动
3. 找到元凶后做成正式修复（修元凶本身，而不是永久 headless），退役全部
   TEMP 补丁（0026/0029 已退役，0030/0031 待退役）

## 5h. R29 收官：NFS root 迭代引擎竣工（2026-11-01 傍晚）

**eth0+NFS root 全通**：Link Up 5.4s → IP-Config Complete → NFS 挂根 → buildroot
用户态全起 → login。原始战役目标（3568 卷一第 4 章那套引擎的 3588 侧）达成。
PC 侧三处修复：mountd 钉 20048（`/etc/nfs.conf.d/mountd-port.conf`，注意
`/etc/default/nfs-kernel-server` 里根本没有 RPCMOUNTDOPTS 行，sed 会空转）；
Windows 防火墙 NFS-TCP/UDP-in-50 两条规则（111/20048/2049，mirrored 模式入站
必加，当年 ICMP 同款）；bootargs nfsroot 加 `,nolock`（跳过锁管理器动态端口）。
注意：Windows `Test-NetConnection` 到自身 IP 的 hairpin 测试在 mirrored 模式下
不可靠（False 不代表外部不通，板子才是真裁判）。板侧网络脚本 `ip: RTNETLINK
answers: File exists` 是 buildroot 想重配内核已配好的 eth0，无害。

**战役总账**：29 轮 / 约 30 小时。从「open 首笔 MDIO readl 楔死 AXI」起，经
GPT 三轮外部会诊 + dsh-006 lore + v1-v6 探针迭代，终点：**凶手=显示上电家族
（headless 即痊愈）**，eth/NFS 全通。剩余收尾移交下一会话（见 §7 交接任务书）。

## 7. 移交下一会话：显示家族二分

任务书全文：`dyn/vop-handoff-session-prompt.md`。要点：按 vop → dsi0+panel →
mipidcphy0 顺序逐个恢复（判据=DBG30 CON0 翻转横幅 + NFS 轮能否挂上），找到
元凶（头号嫌疑 0009 的 &vop reset 组、0001 面板驱动）做成正式修复，退役
0030/0031。

## 6. 流水线教训（重申+新增）

- `forge build ... | tail` 会吞退出码（笔记 118 已记录，本轮**又踩一次**：tail -15
  连错误行本身都截掉了）。后台构建要 `> log 2>&1` 落盘再查 exit。
- `clk_is_enabled()` 不存在于消费者 API；用 `<linux/clk-provider.h>` 的
  `__clk_is_enabled()`（TEMP 补丁可接受）。

## 7. 资产坐标（本轮增量）

- 补丁：`boards/rk3588-topeet/patches/linux/00{28,29}-*.patch`，series 已加
- replay：`8cd9520d → 15c7b4f4`（26 张全绿）
- dsh-006（lore 检索）：`dyn/dsh-006-lore-search.md`（生成中）
- vendor 对照锚点：`reference/rk3588/kernel/drivers/net/ethernet/stmicro/stmmac/dwmac-rk.c`
  （gmac_clk_enable 的 CSU 死代码、DELAY_ENABLE_BY_ID）；`reference/rk3588/kernel/
  arch/arm64/boot/dts/rockchip/{rk3588.dtsi:690,topeet-rk3588-linux.dts:209,258}`
