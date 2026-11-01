---
title: "卷四：标准总线与真实设备"
---

# 卷四：标准总线与真实设备

> RK3568 线 · 卷四 · 第 11–13 章 · [返回线总览](index.md)

### 第 11 章：I²C 与 regmap

一句话：最常用总线的驱动框架 + regmap 把寄存器读写统一到一套 API。

要点：

- adapter/client/message 分层；DT 子节点 `compatible` + `reg`（7-bit 地址）
- `i2c-tools` 先扫地址再写驱动；经典坑：上拉缺失、地址冲突、电平不匹配、CLK 拉伸
- regmap 统一 I²C/SPI/MMIO 寄存器访问：可缓存、可调试（debugfs）、易适配多总线
- **优先接标准子系统**（hwmon/IIO/input），别什么都写私有字符设备
- 总线错误与恢复：NACK、超时、死锁（SCL 脉冲释放）

实践：
- 接一个传感器/监控芯片，regmap 读写寄存器
- 模拟总线错误（短路 SDA/SCL），分析恢复行为

### 第 12 章：SPI 驱动

一句话：SPI 框架与它的坑——mode 填错是最常见事故。

要点：

- controller/device/transfer/message 分层；mode（CPOL×CPHA）、bits-per-word、max_speed_hz、片选都在 DT 声明
- `spi_sync` 阻塞 vs `spi_async` 带回调；小数据同步、批量高吞吐异步
- spi-mem（命令式器件：NOR/NAND/EEPROM）与 `spi_transfer`（传感器/ADC）两条路的分界
- 大块传输的性能边界：DMA vs PIO；**逻辑分析仪对照波形是排查终极手段**

实践：
- 接 SPI ADC/传感器/显示，比较不同频率与传输长度
- 逻辑分析仪对照 SPI 事务，核对软件与波形

### 第 13 章：UART、RS-485 与协议边界

一句话：UART 最简单、RS-485 要管方向；内核管字节流，**协议帧归用户态**。

要点：

- tty/serial core/8250 分层；termios 配波特率/数据位/流控
- RS-485 半双工必须管方向（DE/RE）；`SER_RS485` 自动方向控制需硬件配合（RK3568 UART 支持）
- line discipline 是 tty 上的协议层；大多数工业协议（Modbus/自定义）**不该写内核 ldisc，放用户态**
- 内核（字节流）与用户态（协议帧、连接管理、状态机）的边界

实践：
- 验证串口与 RS-485；写用户态协议收发器（Modbus 或自定义）
- 测试超时、半包、错误帧、断线重连
- CAN 最小实践：ip link 配 up、candump 收发一帧（板验素材见 tutorial/rk3568/02）

## 素材与取证

| 资产 | 用途 |
|---|---|
| 协议仓互指 | I²C/SPI 机制在 U2、U3，RS-485 电气在 U1.1——本章只讲内核驱动侧 |
| [notes/63（PMU 状态机与 I²C NACK）](../../notes/63-2026-08-25-rk3568-pmu-state-machine-i2c-nack-3s8-boot.md) | I²C 总线真实故障现场 |
| [tutorial/rk3568/02_peripherals](../../tutorial/rk3568/02_peripherals.md) | Goodix 触摸（I²C 客户端驱动）板验素材 |
| books 的 RK3568 用户手册 | 总线控制器资源核对 |
