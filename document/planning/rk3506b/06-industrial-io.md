---
title: "卷六：工业接口与网络"
---

# 卷六：工业接口与网络

> RK3506B 线 · 卷六 · 第 13–15 章 · [返回线总览](index.md)

### 第 13 章：双网口、GMAC 与 PHY

一句话：两个 RJ45 是本板当网关/路由的命根子——讲清一个网口从硬件到协议栈的整条链，「网口不通」时先分层再查。

要点：

- 网口四件套：MAC（GMAC）/ PHY（YT8512×2）/ 中间接口（RMII）/ MDIO；**摸清拓扑是排查第一步**
- 链路 up/down 由 PHY 自协商决定；协商失败落低速半双工——「link up 却慢得像拨号」的真因
- bridge（L2）/ routing（L3）/ NAT 三种转发数据通路不同，分层排查：PHY → ARP → route → netfilter
- 故障四分类：MAC / PHY / 驱动 / 协议栈，各有排查工具链（ip link → ethtool → ethtool -S → ss/tcpdump → nft）
- 验收四硬指标：吞吐、丢包、重连、长跑；**双网口 IRQ 绑不同核**，否则一个核被打爆丢包

实践：
- 双口各自 iperf3 满速验证；做桥接或路由 + NAT 转发节点
- 保存 `ethtool -S` 快照与重连时序；长跑 24h 输出稳定性报告

### 第 14 章：I²C、SPI、UART 与 RMIO

一句话：工业接口三件套加 RMIO——接不上时先分清是控制器、pinmux 还是板级接线的问题。

要点：

- 三层分锅：控制器（SoC/驱动）/ pinmux（pad 停在 GPIO）/ 板级接线（地址/片选/电平）；现象各不同
- I²C：DT 枚举 + `i2c-tools` 排查；经典坑：上拉缺失、地址冲突、电平不匹配、CLK 拉伸
- SPI：mode（CPOL×CPHA）/频率/片选都在 DT 声明，**填错 mode 最常见**；spi-mem（命令式器件）与 `spi_transfer`（普通外设）两条路
- UART 三线最简单；RS-485 半双工**必须管方向**，`SER_RS485` 自动方向控制需硬件配合（RK3506 UART 支持，工业加分项）
- RMIO 落到接口上：布线受限时把控制器挪到空闲 pad；语义比 pinmux 多一层路由

实践（按真实硬件选做）：
- 接一个 I²C 传感器/触摸：扫到地址、probe 成功、读到数据
- 接一个 SPI ADC/Flash：验证 mode/频率/片选；接一个 RS-485 终端跑通方向控制
- GPIO 告警/控制接 input 子系统或 sysfs

### 第 15 章：USB、Wi-Fi 与音频选修

一句话：三样都板验过但都标选修——重点不在具体器件，在理解「**接 out-of-tree 驱动 = 接受长期维护成本**」这个权衡。

要点：

- USB 2.0 = USB2PHY + DWC2 双模；三大故障源：PHY 时钟没起、供电不足、OTG ID 引脚接错
- WiFi RTL8733BU out-of-tree：已搬到 7.1 且 STA/AP 双通，但每升内核都要重 patch——工业设备尽量选主线已支持硬件的理由
- 音频五层链 ALSA→ASoC→SAI→codec(ES8388)→DMA；数字链路已通（声卡注册、48k 干净播放），调音是另一层事
- 选修含义：毕业项目用到哪项深入哪项；但权衡判断每个 BSP 工程师都得会做

## 素材与取证

| 资产 | 用途 |
|---|---|
| [tutorial/peripherals/01–05](../../tutorial/peripherals/) | 第 13、14 章初稿 |
| [notes/21](../../notes/21-2026-06-19-peripheral-bringup-a1-eth-mmc-spi.md)、[22](../../notes/22-2026-06-19-mmc-sd-error110-investigation.md)、[23](../../notes/23-2026-06-19-peripheral-bringup-a2-rmio-i2c-uart2.md) | 外设三篇流水与 RMIO 案例 |
| [notes/28](../../notes/28-2026-06-20-usb-bringup-usb2phy-dwc2.md) + [pitfalls/06（USB2PHY 与 DWC2）](../../pitfalls/06-usb-bringup-usb2phy-dwc2.md) | USB 素材 |
| [notes/29](../../notes/29-2026-06-20-wifi-rtl8733bu-driver-port-roadmap.md)、[30](../../notes/30-2026-06-20-wifi-rtl8733bu-port-complete.md) + [pitfalls/07（RTL8733BU 移植全案）](../../pitfalls/07-wifi-out-of-tree-port.md) | Wi-Fi 招牌素材 |
| books/RK3506B 包的 CAN 入门与协议文档 | 工业接口参考（`.claude/books/`，本地资料） |
