# Ch0 — 路线图：把板子从"能启动"变成"能用"

> boot + rootfs 走完，板子能持久 `login:` 了。但这只是"核心活"——CPU、console、SPI-NAND、rootfs。一块板子要真正"能用"，还得把外设一个个点亮：网口、USB、WiFi、I2C/UART、音频。这个系列就是干这个的。好消息是，主线驱动基本都在，外设 bringup 多半是"接线活"。

## 核心通了，外设还白着

boot 让板子启动到 console，rootfs 让它持久跑进 shell。到这一步，我们手里是一块"能开机、能登录、但啥也干不了"的板子——网口没通、USB 不认、WiFi 没影。外设系列就是把这块"能开机的砖"变成"能用的板"。

听起来工作量不小，但有个让人松一口气的前提：RK3506 这些外设的主线驱动，基本都已经在上游了。dwmac-rk（以太网）、dw_mmc-rockchip（SD/eMMC）、spi-rockchip、dwc2（USB）、pl330（DMA）、ES8328（音频 codec）……一个都不缺。所以外设 bringup 的主体是把这些驱动用设备树接到板子的引脚上、在 config 里打开、再上板验证——绝大多数不用写驱动。

不过有几点先点明，免得读到一半发现"这不是说好的接线活吗"。Ethernet、MMC、SPI、Audio 这几样确实是纯 DT 加 config，零驱动 patch；USB2PHY 缺一个 rk3506 的 of_match，得补一小块驱动代码；I2C/UART2 走的是 RK3506 特有的 RMIO 交叉开关，主线 pinctrl 压根不认，也要补驱动；至于 WiFi——板载这颗 RTL8733BU 是 USB dongle，主线没驱动，整章是把它从一份 out-of-tree 的 Realtek 驱动移植到 7.1。所以这个系列里"接线活"和"动代码"两种活都有，主体仍是前者。

## 三层验证：T1 / T2 / T3

外设"确实在工作"不能只看 dmesg 蹦一行 probe，我们分三层逐级坐实。T1 是驱动 probe——dmesg 有 probe 行，`/sys/bus/.../drivers/...` 绑了节点。T2 是设备就绪——总线把设备枚举出来，比如 `/sys/class/net/eth0`、`/dev/mmcblk0`、`/dev/spidev0.*`。T3 才是真功能 I/O：Ethernet 要看 carrier up + DHCP + ping，MMC 要插卡读 MBR + mount，USB 要枚举到设备。

T1 加 T2 不依赖任何外部硬件就能 100% 坐实"DT 和驱动正确"——这两层完全在板内闭环。T3 要网线、SD 卡、U 盘这些外部东西，有就跑、没有就诚实标 `needs <gear>`，绝不装假通过。这条原则后面每章都守。

## 拿 vendor 同板对照

判断"这块板的硬件到底好不好"，别只盯 forge 自己的 log。把 vendor 镜像跑在同一块板、同一个 SPI-NAND 上对照——vendor 能读出来的东西，硬件就是好的；forge 读不出，那就是 forge 软件问题，别轻易往"物理/接触"上归因。

我们在 MMC 上栽过这个跟头（[Ch1](01_eth_spi_mmc.md) 细讲）：第一次板验 SD 卡 `-110`，一度以为是卡槽接触或主线 dw_mmc 回归，绕了一大圈，最后靠 vendor 同板 log 一眼翻案——同一块板、同一个 dwmmc 控制器，vendor 把同一张卡读得干干净净。硬件好得很，是 SD 卡没插紧。这条方法论后面每章都会用到，**判断硬件状态永远优先用 vendor 同板 log 作锚**，先排除软件再考虑物理。

## 这个系列怎么走

按 patch 量和难度递增排：Ch1 三样纯 DT 的外设打头，是整套里最清爽的一档；越往后驱动 patch 越多，到 Ch3 移植 WiFi 是最硬的一仗。

Ch1 是 Ethernet + SPI + MMC/SD，三个"纯 DT、零驱动 patch"的外设打头。Ethernet 双口通网是这一章的亮点——这板子有两个 RJ45，用户网线插哪个口都能通，靠的就是把 gmac0 和 gmac1 两个口的 DT 都补全。

Ch2 是 USB（USB2PHY + DWC2）。主线 USB2PHY 驱动缺一个 rk3506 的 of_match，要补一小块驱动 patch；外加一个踩了才知道的 DT 坑。USB 一通，Ch3 的 WiFi dongle 才有载体往上挂。

Ch3 是 WiFi（RTL8733BU），本系列最硬的一章。板载这颗 WiFi 是 USB dongle，主线没驱动，得把一份 out-of-tree 的 Realtek 驱动移植到 7.1，再 patch 一根线把它接进 forge 的设备树（fork + patch 0016 + fetch 脚本）。

Ch4 是 I2C/UART（RMIO 交叉开关）。RK3506 的 I2C0/1/2 和 UART2 走一个叫 RMIO 的交叉开关，引脚 mux 值超出 iomux 寄存器位宽，主线 pinctrl 压根不支持，要补一个驱动 patch（约 50 行）把 vendor 的 `rockchip_set_rmio` 搬进主线。

Ch5 是 Audio（ES8388 + SAI1）。音频是 codec + 数字音频接口 + DMA 三件套，主线驱动全在，但 SAI 的 of_match 表里没 rk3506、DMA 又过一道 GRF crossbar 主线不认——两处接线断，得补 patch。数字链路点亮（aplay/mpg123 干净播完、声卡注册），真出声还要等耳机线。

Display（DRM 800×1280 DSI）主线驱动也在，但作者手头没 LCD，这章暂不写，等屏幕到位再补。板子的物理屏是 800×1280（不是常见的 720），vendor 在 U-Boot、Linux DRM、weston 三处都报 `800x1280@61.4, 67.0 MHz`，且"没调就亮"——驱动点亮 800×1280 即证物理屏就是这规格。

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
