# 25 — RW/abort saga 两轮误诊复盘(DDR / SFC)+ 方法论

> 真根因见 [24](24-2026-06-19-sfc-abort-rootcause-reserved-memory-trust.md)。本条专门记**追错树**
> 的两轮 detour,作为"别再犯"素材。提炼版见
> [pitfalls/05](../pitfalls/05-secure-mem-reservation-imprecise-abort.md)。

## saga 的时间线(三段,前两段错)

1. **第一轮:SFC op-idle gate(0011)**——假设"控制器 BUSY 时往里塞 SFC_CMD/CTRL → AXI SLVERR → 0xc06"。
   板上加 0011 idle gate 后 buildroot 起来了(boot 路径修了),**但 dd 写压测仍 0xc06**,
   且 dmesg **从无 "not idle" 警告**→ 控制器 op 间是空闲的 → busy 假说对 dd-stress 不成立。
   (0011 保留为无害硬化,但不是这个 abort 的解。)
2. **第二轮:DDR 头号嫌疑 + stressapptest 计划**——交接记忆写"abort 地址是用户 RAM → 头号嫌 DDR,
   下个 AI 先判别 DDR vs SFC(stressapptest)"。**这条直接被用户的洞察推翻**(见下)。
3. **第三轮(本 session,对)**:tmpfs 判别 → reserved-memory 真根因 → 修 → 板验过。

## 误诊①:DDR 头号嫌疑 —— 为什么错

**当时的推理**:"abort 落在用户 RAM(dd buffer)→ 是 DDR/内存总线压载错 → 跑 stressapptest 判别 DDR vs SFC"。

**错在哪**:
- **imprecise abort 的 FAR 不可信**。0xc06 是异步冒泡,FAR(0x0053d004)是"abort 冒上来时
  CPU 正在干的那个地址",**不是真凶总线事务的地址**。把 FAR 当 DDR 缺陷定位 → 方向就错。
- **用户洞察一票否决**:"vendor_sdk 爆炸写都没事"→ 同 DDR 芯片、同 DDR blob(md5 验证
  公开 rk3506b_ddr = ATK rk3506b_ddr)、同板,vendor 不炸 → **不可能是 DDR 芯片/调谐**。
  stressapptest 那条计划整个没必要(幸亏没花时间 build)。
- **真因是 secure 内存访问**,不是 DDR defect:被分到 trust 物理页的访问被 secure world
  拒,表现为 external abort。和 DDR 物理可靠性两码事。

**教训**:imprecise abort 别按 FAR 找;"vendor 同硬件没事"几乎能否决一切硬件假说。

## 误诊②:SFC PIO/DMA + 把 0xc06 归到 SFC —— 为什么错

**当时的推理**(本 session 前半段我自己也掉进去了):
- vendor 走同路径(spi-nand+spi-rockchip-sfc)→ 差异在 SFC 驱动 / DT。
- DT 唯一差异 = 我们 `rockchip,sfc-no-dma`(forced PIO),vendor 用 DMA。
- → 假设"PIO 写路径在 writeback 压力下喂不动 TX FIFO → 控制器 FSM 报错 → async SLVERR → 0xc06"。

**错在哪**:
- **tmpfs 一发就否决**:dd 写 tmpfs(零 NAND、零 SFC)**照样 0x008 abort**。PIO 写路径
  根本没参与。→ abort 和 SFC/PIO/DMA 无关。
- `no-dma` 是**遗留 debug**(nand-ecc-debug 时的"排除 DMA/cache"手段),它的原始理由
  (主线无 DLL 调谐、80MHz 读 marginal)早就被后续 DLL 移植**作废**了,只是没人回收。
  notes/14 还专门证过"读损坏非 DMA/非速率"(24MHz 无 DLL 都爆 → 锁 ECC 处理)。所以
  "PIO 是问题"是把一个已作废的 debug 当成了真因。
- SFC 写代码和 vendor **逐字等价**,vendor 用同代码不炸 → 不可能是 SFC 写路径。

**教训**:
- **任何"是不是外设/驱动"先 tmpfs 一发**(免费、板上现跑)。本次 tmpfs 直接判了 SFC 无关,
  省得继续 diff 816 行 SFC 驱动。
- **排查前先确认"差异项还活着"**:`no-dma` 当时的理由已失效,它从"真因候选"降级成"历史包袱"。
  别拿历史包袱当现状。

## 误诊③(隐性):把 UBIFS 的 0xc06 当成"独立于 tmpfs 的二级 SFC 问题"

我当时还留了个口子:"如果 reserved-memory 修了 tmpfs 但 UBIFS 还炸,说明有个独立 SFC 问题"。
**板验结果:reserved-memory 一修,UBIFS 0xc06 也消失了**(flash_stress 50/50 过)。
→ 0xc06 和 0x008 **同源**(都是 trust 物理页,只是 precision/冒泡时机不同)。**没有独立 SFC 问题**。

**教训**:**别因为 fault type 不同(0xc06 vs 0x008)就假设两个根因**。同一个根因在不同并发
负载下可以呈现不同 precision。

## 方法论提炼(写进 pitfalls/05)

1. **imprecise external abort(0xc06)= async,FAR 不可信**;只有 precise(0x008)的 FAR 才指向
   真凶地址。遇到 imprecise,先想办法制造 precise 复现(换更纯的 workload,如 tmpfs)。
2. **tmpfs 压测 = 外设/内存的免费判别器**:`dd of=/tmp/s` 大循环。零重建、板上现跑。
   炸 → 内存侧;不炸 → 外设侧。
3. **"vendor 同硬件没事 → 我们的配置/软件"**:最强指引,但**先确认 vendor 走同路径**
   (本次交接记忆错把 vendor 当 rkflash,实际是 mainline spi-nand;路径搞错,对比就失效)。
4. **kernel boot log 的告警/异常行别略过**:`No reserved-memory node in the DT` 这种一行
   字就是命门,被两轮调查跳过了。
5. **历史 workaround 要回收**:`no-dma`、powergood 这种"当时加的 debug/缓解",理由失效后
   要么删要么注释清楚,否则下一个人(包括未来的自己)会拿它当真因。

## 没白费的副产物

- 把 vendor rk3506 全链路扒清了:**同路径 + DT flash 逐字等价 + DDR blob md5 相同 + SFC 写等价**
  → 这套"逐项排除"表本身就是资产,以后任何 RK3506 对照都省事。
- 0011 idle gate、powergood、DLL 调谐这些 SFC 侧硬化**保留**(对齐 vendor rkflash 契约,
  无害),只是不再是 abort 的解。
- `no-dma` 标记为遗留 debug,**后续可清**(对齐 vendor 用 DMA),但不是这次的事。

相关:[[production-grade-rootcause-required]](用户硬要求根治,这两轮 detour 正是该要求的反面教材)。
