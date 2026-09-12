# 63 — 推干净战役：PMU 状态机 + i2c NACK 模型，真 DTS 启动 90s → 3.8s（2026-08-25）

> 62 号笔记拿下真 DTS 直启后，把 ~90 秒的探测超时税全部清零。两个新模型
> （PMU 有状态镜像、rk3x i2c NACK 最小模型）+ 一次极性翻车（195s）+ 一次
> fprintf 探针裁决。终态：3.8s、最大间隙 0.47s、四模式全绿。

## 0. 结论

| 项 | 结果 |
|---|---|
| 真 DTS 启动时长 | 90s → 7.6s（PMU）→ **3.8s（+i2c）**；最大间隙 0.47s |
| PMU 影子 v2 | 有状态：ack@0x60/idle@0x68 镜像 req@0x50，**status@0x98 同极性镜像 pwr@0xa0** |
| i2c 模型 | rk3x 最小版：事件即时回 IPD + 拉 IRQ，地址阶段一律 NACK → 客户端瞬间 -ENXIO |
| 回归 | smoke / rootfs / board / virt 四模式全绿 |

## 1. PMU：从无状态到状态机（三步翻车史）

1. 全 1（62 号）：上电瞬通，但挂起方向全超时——`is_on = !is_idle`，
   全 1 = 全 idle = 全断电。
2. req 镜像 v2：idle/ack 跟随 req 写值——「set idle」通了，「set domain off」
   还烧：`is_on` 实际读 **status@0x98**（DOMAIN_RK3568 的 status_mask=pwr 位，
   非零，之前判错）。
3. status 镜像 + 极性坑：v3 先写 `~pwr` → **195s 大翻车**（「set ON」全面
   失败）。fprintf 探针抓到驱动写 0x00800000（ON 写）后死轮询 0x98——回读
   源码，`rockchip_pmu_domain_is_on` 的注释写得明白：**"1'b0: power on,
   1'b1: power off"——status 位 1 = 断电**。同极性直镜像 `status = pwr`
   才对（pwr 位 1 = 下电，二者天然一致）。改完 → 7.6s。

教训：**极性靠猜必翻车，驱动源码注释就是 TRM**。四条镜像（req→ack、req→idle、
pwr→status、ack 握手）全部「跟随驱动自己的写」，任何方向都瞬通。

## 2. rk3x i2c NACK 最小模型（7.6s → 3.8s）

剩余燃烧全在 i2c：每次传输 1s 超时（rk8xx PMIC ×1、fan53555 ×1、Goodix ×2、
pcf8563 ×1）。模型（寄存器/位值出自 i2c-rk3x.c）：

- CON(0x00) 写：START 位(BIT3)→pend IPD.START(BIT4)；STOP(BIT4)→pend
  IPD.STOP(BIT5)
- MTXCNT(0x10)/MRXCNT(0x14) 写：pend IPD.NAKRCV(BIT6)——仿真总线上没有
  设备，地址阶段如实 NACK
- IPD(0x1c)：写 1 清除；每次写后 `irq = !!(ipd & IEN)`
- IRQ 接 GIC SPI 46/47/51（i2c0/1/5），gpio-in[n] 直接就是 SPI n

时序闭环依赖驱动自己的顺序（start 先写 IEN 再写 CON.START；handle_start 先
写 IEN=MBTF|NAKRCV 再写 MTXCNT；stop 先写 IEN=STOP 再写 CON.STOP）——模型
只做同步应答，全部命中。效果：i2c 客户端从 `-ETIMEDOUT`（1s）变 `-ENXIO`
（µs）。

## 3. 终态残留清单（29 条错误行全部瞬时且语义诚实）

| 类别 | 语义 | 处置 |
|---|---|---|
| i2c 客户端 ×4（-ENXIO） | 总线上无此设备 | ✅ 如实 |
| i2s ×N + pinctrl pin-42 | 音频链无 DMA/PIN 冲突 | 瞬时，未来音频课题再清 |
| USB ehci×2/ohci×2 | 控制器未建模 | 瞬时，未来 USB 课题 |
| rk_iommu / arm-scmi(~0.2s) / mmc1 note | 附属噪声 | 瞬时/可忽略 |
| regulatory.db | 真机也如此 | 正常 |

## 4. 复现

```bash
QEMU=third_party/qemu/build/qemu-system-aarch64 \
  boards/rk3568-atk/sim/boot-smoke.sh rk3568-lite board   # 3.8s 三断言 PASS
```

## 5. 下一步候选

真 SDHCI 模型（替换 virtio 替身，mmc1 顺手收编）/ SCMI 邮箱（再省 0.2s）/
U-Boot proper 线（CRU 影子已备好）。
