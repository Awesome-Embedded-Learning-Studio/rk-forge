# 62 — 真板 DTS 直启：CRU/PMU 影子模型（2026-08-25）

> 60/61 号笔记同日第三役：`rk3568-atk-evb1-ddr4-v10.dtb`（真板全量设备树）
> 从「3752 万条日志死等 CRU」打到「三断言 PASS」。核心是两个影子模型、
> 一次全 1 的翻车、一个优先级教训。

## 0. 结论

| 项 | 结果 |
|---|---|
| 真 DTS 启动 | ✅ 三断言 PASS（`boot-smoke.sh rk3568-lite board`），guest ~90s |
| CRU/PMUCRU | RAM 后备影子：写存读回 + PLL 锁定位强制（`(offset&0x1f)==4 → BIT(10)`） |
| PMU 电源域 | 精确应答：ack@0x60 全置位、idle@0x68 全清零 |
| GRF/PMUGRF | yesman 全 1（SOC_STATUS0 的 PLL lock 位） |
| 外设毯子 | 0xf0000000/256MB unimp，显式 `priority -100` |
| 回归 | smoke（SMP=1/4）与 rootfs 模式全绿 |

## 1. 迭代链（每步有实锤）

1. **真 DTS 首启死点**：CRU+0x044 死轮询（37,521,569 次读/60s）——rk3036 型
   PLL 锁定位在 CON1 BIT(10)（`rockchip_rk3036_pll_wait_lock`）；另一条锁
   路径读 GRF SOC_STATUS0@0x580（clk-pll.c 源码定位）。
2. **第一版全 1 yesman 翻车两处**：
   - `dw-apb-uart: clock rate not defined`（EINVAL）——全 1 把分频算成垃圾。
     RAM 后备 + 读回 0 反而正确：mux 自动落在第一父时钟 xin24m（UART 得
     24MHz），div 0 被驱动当 1。ttyS2 成功注册（base_baud 75MHz 虽是垃圾
     但非零可用，波特率自洽）。
   - 电源域全判 idle：DOMAIN_RK3568 无 status_mask → `is_on = !is_idle`，
     全 1 → 全 idle → 每个域烧 ~9s 超时。
3. **PMU 精确应答**（偏移出自 pm-domains.c `rk3568_pmu`）：ack@0x60 置位 +
   idle@0x68 清零 → 每个域瞬间报告 "on"。全绿。
4. **毯子优先级教训**：同优先级重叠的胜负不可信——插入代码的推导与实验
   现象矛盾（串口字节被打进毯子，内核静默启动进 `cpu_do_idle`，addr2line
   定位）。显式 `add_subregion_overlap(-100)` 一锤定音。

## 2. 硬事实

| 事实 | 值 |
|---|---|
| rk3568_pmu 偏移 | pwr 0xa0 / status 0x98 / req 0x50 / **idle 0x68 / ack 0x60** |
| CRU PLL 锁定模式 | `(offset & 0x1f) == 4` → OR `BIT(10)` |
| 真 DTS 启动时长 | ~90 guest 秒：i2s/USB 等探测超时（下一批需求对象） |
| 调试日志风险 | 挂死状态 + `-d unimp` 全速写日志 = **3.2GB/150s**，排查完立刻删 |

## 3. 复现

```bash
QEMU=third_party/qemu/build/qemu-system-aarch64 \
  boards/rk3568-atk/sim/boot-smoke.sh rk3568-lite board
```

## 4. 下一步

90 秒慢启动的元凶清单（i2s "Could not register PCM"、USB 探测超时等）=
下一轮需求探测对象；U-Boot proper 线的 CRU 前置已就位，可并行开题。
