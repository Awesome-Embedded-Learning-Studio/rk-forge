# 68 — RK3588 真板 DTS 完全平移（2026-08-26）

> 用户终目标达成：`rk3588-topeet.dtb`（真板全量设备树）在 rk3588-lite 上完整
> 启动到 shell，三断言 PASS（`boot-smoke.py rk3588-lite board --check`）。
> rk3568 的影子方法论平移成功，途中四个新坑各有实锤。

## 0. 结论

| 项 | 结果 |
|---|---|
| 真板 DTS 直启 | ✅ `Machine model: Topeet RK3588 Board` → ttyS2 注册 → shell 三断言 |
| 影子套件平移 | CRU(0xfd7c0000/0x5c000) + sys_grf/pmu1grf yesman + PMU(0xfd8d8000/0x400) 四镜像 |
| ttyFIQ0 解法 | modify_dtb：nop 掉 fiq-debugger 节点 + uart2 status 还给 "okay"（8250 路线） |
| 回归 | 两板八模式全绿 |
| 遗留 | cpuidle 深睡在 TCG 异构下 hard lockup（`cpuidle.off=1` 规避，根因待查）；rk3588 U-Boot 卡 SCMI-over-SMCCC（见 §3） |

## 1. 四个新坑（RK3588 与 RK3568 的差异清单）

1. **PLL 锁定位不同**：rk3588 是 **PLLCON6 BIT(15)**（`(offset&0x1f)==0x18`），
   不是 rk3568 的 CON1 BIT10。第一版照抄 rk3568 → `rockchip_rk3588_pll_wait_lock`
   死转（addr2line 定位）。
2. **PLL 率预写要点名**：rk3588 的 PLL 分散在 CON{0,8,16,88,96,104,112,120}
   （b0/b1/l/v0/au/c/g/n，ppll 在 PMU 区），**CON(112) 的 gpll 在盲写范围外**。
   按驱动源码精确点位预写 m=100/p=2/s=1（=600MHz）。
3. **set_rate 半写自愈**：驱动重编程 gpll 后 CON1 只剩 hiword 残留（p=0）→
   率算 0 → `clock rate not defined` EINVAL。devmem 实锤寄存器状态后，影子
   读时补规则：PLL CON1 的 p 位为 0 → 回填 p=2。修完 ttyS2 注册
   （base_baud 37125000，分频自洽）。
4. **分频器 0 值**：clk_uart2_src 的 CLKSEL_CON(43)[2:6] 分频器读 0 → 整链
   EINVAL，预写 1。

另：PMU 影子补 status@0x180 同极性镜像 pwr（rkvdec0 域走此路），
rk3568 的极性教训直接复用；`cpuidle.off=1` 规避 A76 簇深睡在 TCG 的
watchdog hard lockup（根因未深究，诚实记录）。

## 2. 硬事实（沉淀给后续课题）

| 事实 | 值 |
|---|---|
| rk3588 PLL 分布 | CON{0,8,16,88,96,104,112,120} + ppll@PMU_PLL_CON(128)；锁 = CON6 BIT15 |
| uart 时钟链 | clk_uart2 mux{src,frac,xin24m} ← src mux{gpll,cpll} div@CLKSEL_CON43[2:6] |
| ttyFIQ0 | topeet dts 把 uart2 的 8250 绑定 disabled + fiq-debugger 节点独占 |
| rk3588 pm-domains | pwr 0x14c/status 0x180/req 0x10c/ack 0x118/idle 0x120/repair 0x290 |

## 3. 下一课题：SCMI 仿真（rk3588 U-Boot 的钥匙）

rk3588 U-Boot `initf_dm` 即死于 `scmi-over-smccc`（它靠 BL31 的 SCMI 服务管
时钟/复位/电源，仿真无 BL31）。正解是在 rk3588-lite 里**拦截 SMCCC 的 SCMI
函数号做固件接口仿真**——和 PSCI 拦截同一机制，是「仿真器扮演固件」系列
（TPL→OS_REG 之后的第二课）的招牌题目。

## 4. SOAK 存活浸泡与一次误诊（同日，用户问责推动）

用户质问「断言过就是过了？开机后立马挂找你算账」——完全成立：原断言只覆盖
「到 shell + 立即关机」，而 cpuidle 硬锁死那类故障在 30s+ 才发作，恰在断言
窗口外。补 **SOAK 机制**（`SOAK=秒数`）：去掉自动关机，shell 每 5s 一拍
`BEAT-n` 心跳回显，全到齐后手动关机——「跑通」升级为「活着」。

**一次诚实的误诊记录**：首版 SOAK 两板都在 ~45s 掉拍，我诊断成「MTTCG 异构
竞态」并上了 `-accel tcg,thread=single`（用户当场质疑：多线程的 bug 不测
了？）。复查发现掉拍位置两板一致、且手动测试全过——真凶是**喂拍代码自身**：
`(8+n*5)` 被当作逐拍 sleep 累加，节拍越来越稀，末拍落在超时之外。修为固定
节奏 + 撤掉单线程后，MTTCG 全过：

| 浸泡 | 结果 |
|---|---|
| rk3588-lite board（真板 DTS，8 核异构，MTTCG） | 60s 12/12、**120s 24/24** |
| rk3568-lite board（真板 DTS，MTTCG） | 60s 12/12 |
| 全模式回归 | 两板八模式 PASS |

结论：MTTCG 无此问题；唯一真实的规避仍是 `cpuidle.off=1`（那次锁死有
watchdog panic 实锤，根因仍在册）。教训两条：①「断言绿」≠「系统稳」，存活
浸泡必须是一等公民；②给基础设施下结论前，先排除测试自身的 bug——两板同位
置掉拍就是测试代码的指纹。

## 5. 复现

```bash
python3 boards/rk3568-atk/sim/boot-smoke.py rk3588-lite board --check
SOAK=120 python3 boards/rk3568-atk/sim/boot-smoke.py rk3588-lite board --check  # 存活浸泡
```
