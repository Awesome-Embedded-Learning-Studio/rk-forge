# Ch0 — 路线图：把板子从"能启动"变成"能用"

> boot + rootfs 走完，板子能持久 `login:` 了。但这只是"核心活"——CPU、console、SPI-NAND、rootfs。一块板子要真正"能用"，还得把外设一个个点亮：网口、USB、WiFi、I2C/UART、音频。这个系列就是干这个的。好消息是，主线驱动基本都在，外设 bringup 多半是"接线活"。

## 前言：核心通了，外设还白着

boot 让板子启动到 console，rootfs 让它持久跑进 shell。到这一步，你手里是一块"能开机、能登录、但啥也干不了"的板子——网口没通、USB 不认、WiFi 没影。外设系列就是把这块"能开机的砖"变成"能用的板"。

听起来工作量不小，但有个让人松一口气的前提：**RK3506 这些外设的主线驱动，基本都已经在上游了**。dwmac-rk（以太网）、dw_mmc-rockchip（SD/eMMC）、spi-rockchip、dwc2（USB）、pl330（DMA）、ES8328（音频 codec）……一个都不缺。所以外设 bringup 的主体是"接线活"——把这些驱动用设备树接到板子的引脚上、在 config 里打开、再上板验证。绝大多数不用写驱动。

## 三层验证：T1 / T2 / T3

外设"确实在工作"不能只看 dmesg 蹦一行 probe，我们分三层逐级坐实，每层都有硬证据：

- **T1 驱动 probe**——dmesg 有 probe 行，`/sys/bus/.../drivers/...` 绑了节点。
- **T2 设备就绪**——总线枚举到：`/sys/class/net/eth0`、`/dev/mmcblk0`、`/dev/spidev0.*`。
- **T3 功能**——真 I/O：Ethernet 的 carrier + DHCP + ping，MMC 插卡读 MBR + mount，USB 枚举设备。

T1+T2 不依赖外部硬件就能 100% 坐实"DT + 驱动正确"；T3 要网线/卡/U盘，有就验、没有就诚实标 `needs <gear>`，不装假通过。

## 一个值钱的方法论：拿 vendor 同板对照

判断"这块板的硬件到底好不好"，别只盯 forge 自己的 log——**把 vendor 镜像跑在同一块板、同一个 SPI-NAND 上**对照。vendor 能读出来的东西，硬件就是好的；forge 读不出，那就是 forge 软件问题，**别轻易往"物理/接触"上归因**。我们在 MMC 上栽过这个跟头（[Ch1](01_eth_spi_mmc.md) 细讲），后来靠 vendor 同板 log 一眼翻案。这条方法论后面每章都会用到。

## 这个系列怎么走

主线驱动都在，但有几处缺的不是接线、是要动代码，先点明、好让你心里有数：

- **Ch1 Ethernet + SPI + MMC/SD**——三个"纯 DT、零驱动 patch"的外设。Ethernet 双口通网是亮点。
- **Ch2 USB（USB2PHY + DWC2）**——主线 USB2PHY 驱动缺一个 rk3506 的 of_match，要补一小块驱动 patch，外加一个踩了才知道的 DT 坑。
- **Ch3 WiFi（RTL8733BU）**——本系列最硬的一章。板载这颗 WiFi 主线没驱动，是把一份 out-of-tree 的 Realtek 驱动移植到 7.1。
- **Ch4 I2C/UART（RMIO 交叉开关）**——RK3506 的 I2C/UART2 走一个叫 RMIO 的交叉开关，主线 pinctrl 压根不支持，要补一个驱动 patch。
- **Ch5 Audio（ES8388 + SAI1）**——音频 codec + 数字音频接口 + DMA，数字链路点亮（真出声还要等耳机）。

Display（DRM 800×1280 DSI）主线驱动也在，但作者手头没 LCD，这章暂不写，等屏幕到位再补。

## 成功长这样

外设点亮的尽头，板子是这样一整页 dmesg——下面这些行从全链 [boot-sdl-2026-06211109](../../logs/boot-sdl-2026-06211109.txt) 里截的，每行对应一个点亮的外设：

```
rk_gmac-dwmac ff4c8000.ethernet: init for RMII                         ← Ethernet
dwc2 ff740000.usb: DWC OTG Controller                                   ← USB host
usb 2-1.3: new high-speed USB device number 3 using dwc2                ← WiFi dongle 枚举
es8328 0-0011: supply DVDD not found, using dummy regulator             ← Audio codec
rockchip-sai ff310000.sai: ...                                          ← 音频接口
ALSA device list:
  #0: rockchip-es8388                                                   ← 声卡注册
```

网、USB、WiFi、音频，一屏 dmesg 全见。我们 [Ch1](01_eth_spi_mmc.md) 见。
