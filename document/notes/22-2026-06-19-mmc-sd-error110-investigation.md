# 22 — MMC/SD `-110` 排查：以为是主线 dw_mmc 回归，结果是卡接触（2026-06-19）

> **✅ RESOLVED（2026-06-19 晚，板上定性翻案）**：`-110` **不是主线驱动 bug，是 SD 卡没插紧**（marginal contact）。带 RINTSTS 打印的 `update-mmc-debug.img`（`boot-sdl-202606191808.txt`）板上插卡后**枚举成功**：`mmc0: new high speed SDXC card` + `mmcblk0: ... 58.2 GiB` + **8 分区全出来**（`p1..p8`）。我那行 debug 打印抓到的 `pending=0x100`（RTO 位）全在 **CMD5/CMD52（SDIO 探测命令）**上——这是**正常**的：mmc core 拿 SDIO 命令探 SD 内存卡，卡不认 SDIO → 超时 → core 接着走 SD 内存初始化（CMD0/8/55/41）成功。**没有 cmd0 err**。所以之前几次 `-110`（`Card stuck being busy`）就是卡数据线接触不良，插紧就好了。
>
> **教训（这条比结论更值钱）**：我这条排查**两次判错**——先判"物理问题"（被 vendor 同板 log 翻案），再判"主线 dw_mmc 回归"（被板验翻案）。真因是最朴素的**接触不良**。两次错的共同点：**没在动手深挖驱动/clk 之前，先排除"卡没插好"这种最便宜的物理变量**（重插、换卡、热插 vs 开机在位各试一次）。下面那一长串"逐项排除 DT/clk/pinctrl/ops"的过程不是白做（它确实坐实了"forge 这侧 DT/驱动跟 vendor 等价，问题不在软件配置层"），但**代价是把一个 5 分钟能验的接触问题，绕成了一场几小时的驱动考古**。顺序应该是：先最便宜的物理 triage → 再软件层 diff。
>
> **现状**：MMC 正常（热插枚举 + 8 分区）。A1（Ethernet 双口 + SPI + MMC/SD）**全部跑通**。dw_mmc 的 debug 打印已撤（一次性 debug，不入 series）。

---

> 下面是排查**过程**（保留作方法论 + 翻案记录）。结论见顶部 RESOLVED 段。

> **状态（2026-06-19）**：`mmc0: error -110 whilst initialising SD card`（含 `Card stuck being busy! __mmc_poll_for_busy`），插卡后所有速率（400k→300k→200k→187.5k→50M）全超时。**硬件已证 100% 好**（vendor 镜像读同一张 64G 卡 OK，见 [21](21-2026-06-19-peripheral-bringup-a1-eth-mmc-spi.md)），**DT 节点 + pinctrl 引脚 + clk-rk3506 SDMMC 定义 + dw_mmc-rockchip ops/init 跟 vendor 逐字/功能等价**，问题缩到**主线 dw_mmc CORE 驱动 6.1→7.1 的回归**。已出带 RINTSTS 打印的 `update-mmc-debug.img` 等板上定性（RTO 位=卡无响应、RE 位=响应 CRC 错）。

## 先翻案：不是物理问题

第一次板验 `-110` 时，我把它跟 vendor SD 启动 SPL 的 `mmc_init: -95`（"Card did not respond to voltage select"）联想，判断成"卡/槽/控制器物理接触问题"——**这个判断是错的**。

翻案的证据是 vendor 跑在同一块板的两张 log：`boot-sdl-2026-06191732.txt`（vendor 从 SD 启动，line 390 `mmc0: new high speed SDXC card` + `mmcblk0: ... 58.2 GiB` + 8 分区）和 `vendor_sdk_ubifs.txt`（vendor 跑在同一 SPI-NAND，boot NAND 的同时**还把那张 SD 卡读出来了**，line 390-395）。两份都证明同一张卡、同一个 `ff480000.mmc` 控制器、同一块板，vendor 读得干干净净。SPL 那个 `-95` 只是"SD 上没 RK boot 镜像 → fall 到 NAND"的正常启动顺序（line 689 `mmc_init: -95` → line 691 `Trying to boot from MTD1`），**不是读卡失败**。

教训记下：判断嵌入式板子"硬件好不好"，**别只看自己这棵树的 log，把 vendor 镜像跑在同板同存储上对照**。vendor 能读 = 硬件好，自己读不出 = 自己软件问题。两个独立软件栈（vendor SPL/loader + mainline Linux）都读不出同一个东西才算物理问题；只一个读不出而另一个 OK，铁定是读不出的那侧的软件。

## 逐项排除：把"是不是我 DT/驱动抄错了"一项项坐死

既然硬件好，那 `-110` 是 forge 这侧的软件。但 forge 的 MMC DT 是 verbatim 抄 vendor 的，所以第一反应是"我是不是抄漏/抄错了"。这个不能用猜的，得**抽 vendor 实际在用的 DTB（ground truth）跟 forge 编的 dtb 逐节 diff**——因为源码 .dts 可能跟实际烧进去的 DTB 有出入（不同的 board .dts、不同的 include 链）。

抽 vendor DTB 的办法：vendor 的 `rk3506b_update_sd.img` 里的 `boot.img` 是个 FIT（FDT 格式），里面 embed 了板级 DTB。FIT 自己开头是 FDT magic（`0xd00dfeed`），embed 的 DTB 也是 FDT magic——所以**扫 boot.img 里第二个 FDT magic，读它的 totalsize，切出来**就是 vendor 的板级 DTB，再 `dtc -I dtb -O dts` 反编译。Python 一小段搞定（见 [21] 的方法）。

然后逐项 diff：

**mmc 节点本体**——vendor 和 forge 的 `mmc@ff480000` 功能等价：compatible（rk3506/rk3288-dw-mshc）、reg、interrupts（GIC_SPI 86）、max-frequency（150M）、bus-width（4）、fifo-depth（0x100）全一样。clocks/resets 的数字看着不同（vendor `0xb4/0xb3`+reset `0x117` vs forge `0xa6/0xa5`+`0x7d`），但那只是 **vendor 和主线两边的 `<dt-bindings/clock/reset/rockchip,rk3506-cru.h>` 编号不一样**（vendor 把 SDMMC 时钟排在 179/180，主线排在 165/166），各自的 clk 驱动都正确映射到 SDMMC 时钟/reset，**功能等价**。

**pinctrl 引脚**——vendor 和 forge 的 sdmmc-bus4/clk/cmd 组**逐字相同**（bank3 PA0-PA5 func1），只有 pcfg 对象的 phandle 数字不同（0x6c vs 0x1c），那是 dtsi 里 phandle 分配顺序不同，指向的 `pcfg_pull_up`/`pcfg_pull_none` 是同一个。引脚没抄错。

**我移植时删的几个 slot 属性**（`supports-sd`/`no-mmc`/`no-sdio`/`cap-mmc-highspeed`）——grep 主线 `dw_mmc.c` + `dw_mmc-rockchip.c`：**主线根本不解析这几个**（empty grep）。所以删不删对主线无影响，不是 `-110` 的因。

**clk-rk3506 的 SDMMC 时钟定义**——这是我最先怀疑的（"分频器寄存器位写错 → 分频没生效 → 卡拿到父时钟而非 400k → init 太快 → -110"）。但 `diff` 主线和 vendor 的 `clk-rk3506.c`：`CCLK_SRC_SDMMC`（`COMPOSITE`，`RK3506_CLKSEL_CON(49)`，mux 13/2、divider 7/6、GATE `RK3506_CLKGATE_CON(17)` bit 6）+ `HCLK_SDMMC`（bit 7）**逐字相同**，两份文件总共差 120 行全在别的时钟（SAI/PLL/frac），SDMMC 段零差异。clk 不是因。

**dw_mmc-rockchip 的 ops**——vendor 的 `dw_mmc-rockchip.c` **根本没有 rk3506 专属条目**，它也是靠 DT 的 `rockchip,rk3288-dw-mshc` secondary 匹配 `rk3288_drv_data`（line 600-601）。所以 vendor 和主线用的是**同一套 ops**。`dw_mci_rockchip_init`（vendor 534 / 主线 498）也是功能等价：rk3288 分支都跑 `bus_hz /= RK3288_CLKGEN_DIV` + `freqs[]` 循环设 `minimum_speed`，rk3506 都命中这分支；vendor 那段 rk3568 专属的 `f_min=375000`（"RK356X only support 375KHz for ID mode"）rk3506 走 else（`f_min=100000`），主线干脆不设（用 `minimum_speed` 或 `DW_MCI_FREQ_MIN`）——但 forge log `actual 400000HZ div=0` 证明主机确实在跑 400k，f_min 没把它钳高频，所以 f_min 也不是因。

**至此源码层全排除**。mmc 节点、引脚、clk、ops、init、slot 属性——跟 vendor 全等价或主线忽略。剩下的差异只有一个：**主线 dw_mmc CORE 驱动（`drivers/mmc/host/dw_mmc.c`）是 7.1，vendor 是 6.1**。回归在这里，但源码对比定位不到具体哪行（6.1→7.1 dw_mmc 重构不少，盲 diff 没意义）。

## 一个有用的中间观察：irq 号不同但应该不是因

vendor mmc `irq 70`，forge `irq 39`（同一 DT 节点 GIC_SPI 86）。虚中断号不同是两个内核 irq 域分配顺序不同，正常；只要 gic 把 SPI 86 正确路由到各自注册的 virq 就行。控制台 UART（GIC_SPI 34）在 forge 工作正常 → gic 路由没问题 → mmc 的 SPI 86 也该正常路由。所以 irq 大概率不是因（但如果后面 RINTSTS 显示"中断根本没来"，要回头查这个）。

## 定性手段：dw_mmc 的 RINTSTS

`-110` 是 mmc core 的命令超时（CMD0 发下去没拿到响应）。dw_mmc 的中断处理（`dw_mci_interrupt`）读 `pending = MINTSTS`，命令失败走 `DW_MCI_CMD_ERROR_FLAGS` 分支（`host->cmd_status = pending`）。这个 `pending` 的位含义直接定性失败模式：

- **RTO（Response Timeout）位** = 控制器发了 CMD、等了若干 bus clock 没等到响应 = **卡没响应**（时钟没到卡 / 没供电 / CMD-DAT 信号没到卡）。
- **RE（Response Error）位** = 响应来了但 CRC 错 = **相位/信号完整性**问题。
- 别的位 = 别的故事。

主线这版 `dw_mmc.c` **没有 `dumpregs`/`CONFIG_MMC_DEBUG` 的寄存器 dump 机制**（grep 空），所以不能光靠 config，得手动加。我在 `DW_MCI_CMD_ERROR_FLAGS` 分支加一行 `dev_info`（直接改 `dw_mmc.c`，一次性 debug，不入正式 series）：

```c
host->cmd_status = pending;
/* TEMP DEBUG: RTO bit = card no-response (clk/power/pins),
 * RE bit = response CRC err (phase). Pinpoints mmc0 -110. */
dev_info(host->dev, "DBG cmd%u err: pending=0x%x STATUS=0x%x\n",
         host->cmd ? host->cmd->opcode : 0xffffffff, pending,
         mci_readl(host, STATUS));
```

出 `update-mmc-debug.img`（带这行打印 + A1 全部外设）。板上插卡后看 `DBG cmd0 err: pending=0x... STATUS=0x...` 那行：

- `pending` 里 RTO 位置位 → 卡没响应 → 问题在"时钟/供电/CMD-DAT 到没到卡"。但 clk 定义对、pinctrl 引脚对、供电 regulator 对（都跟 vendor 等价已证），那就得查 **CIU 时钟是不是真在物理引脚上跳**（clk_set_rate 报 400k 但硬件分频器没真写下去？要 `devmem` 读 cru `CLKSEL_CON(49)` 验）或 **主线 U-Boot 有没有像 vendor U-Boot 那样预 mux SD 引脚/预配 pad**（vendor mmc 节点 "No normal pinctrl state" 但能跑，疑似靠 bootloader 留的态；主线 U-Boot 可能没留 → Linux 的 pinctrl-0 理论上该补上，但也许没补全/时机不对）。
- RE 位置位 → 响应 CRC 错 → 相位问题，dw_mmc-rockchip 的采样相位调参方向。
- 完全没这行 → 中断根本没来（连 timeout 中断都没），那是 irq/控制器没真正跑起来，回头查 irq 路由 + clk gate。

## 待办

- 板验 `update-mmc-debug.img`，抓 `DBG cmd err` 那行 → 定 RTO/RE/无中断。
- RTO → `devmem` 读 `0xff9a01c4`（cru CLKSEL_CON(49)，cru@ff9a0000 + 0x100 + 4*49）看 SDMMC 分频器位（bit7-12）是不是真写进去了；并查主线 U-Boot 有没有预 mux SD pad。
- RE → dw_mmc-rockchip 相位/采样调参。
- 这条查清再回头看 mmc 要不要单独驱动 patch（比如给 dw_mmc-rockchip 补个 rk3506 专属 init，或主线 dw_mmc 的某处 quirk）。
