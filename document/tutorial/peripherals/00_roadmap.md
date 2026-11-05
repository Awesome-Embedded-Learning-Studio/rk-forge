# Ch0 — 路线图：把板子从“能启动”变成“能用”

> 咱们把 boot 和 rootfs 走完，板子能持久地停在 `login:` 上了，但到这里通了的还只是“能开机”的核心部分，CPU、console、SPI-NAND、rootfs 这些核心的东西。一块板子要真正地能用，咱们还得把外设一个个点亮，网口、USB、WiFi、I2C/UART、音频咱们都得点亮。这个系列干的就是这件事，好消息是主线那边基本都有现成的驱动，而外设 bringup 多半是接线活。

## 核心通了，外设还白着

boot 把板子带到了 console，rootfs 让它持久地跑进了 shell。咱们走到这一步，手里有的只是一块“能开机、能登录、但啥也干不了”的板子，而网口没通、USB 不认、WiFi 没影。外设系列要做的，就是把这块能开机的砖变成能用的板。

外设的活听着多，但有个能让人松一口气的前提：RK3506 的这些外设，主线驱动基本都已经进了上游。以太网的 `dwmac-rk`、SD/eMMC 的 `dw_mmc-rockchip`、`spi-rockchip`、USB 的 `dwc2`、DMA 的 `pl330`、音频 codec 的 `ES8328`，这些驱动咱们一个都不缺。所以外设 bringup 的主体，是咱们把这些驱动用设备树接到板子的引脚上、在 config 里打开、再拿到板上验证，绝大多数咱们都不用写驱动。

不过有几件事咱们得提前点明，免得咱们读到一半发现“说好的接线活”变了味。咱们看 Ethernet、MMC、SPI、Audio 这几样，确实是纯 DT 加 config、零驱动 patch 的活。USB2PHY 缺一个 rk3506 的 of_match，得补上一小块驱动的代码。I2C/UART2 走的是 RK3506 特有的 RMIO 交叉开关，而主线 pinctrl 压根不认，也得咱们补驱动。至于 WiFi——板载的这颗 RTL8733BU 是 USB dongle，主线里没它的驱动，整章的活，是把一份 out-of-tree 的 Realtek 驱动，移植到了 7.1。所以这个系列里两种活都有，接线的和动代码的，而主体仍是前者。

## 三层验证：T1 / T2 / T3

外设是不是真的在工作，光看 dmesg 蹦出一行 probe 是不够的，咱们分三层逐级地验证。T1 是驱动 probe 的层，dmesg 里有了 probe 行，`/sys/bus/.../drivers/...` 绑上了节点。T2 是设备就绪的层，总线把设备枚举了出来，`/sys/class/net/eth0`、`/dev/mmcblk0`、`/dev/spidev0.*` 就是这样的例子。T3 才是真的功能 I/O：Ethernet 的验证是 carrier up 加 DHCP 加 ping，MMC 的验证是插卡读 MBR 加 mount，USB 的验证是把设备枚举出来。

T1 加 T2 的这两层不依赖任何外部硬件，在板内就能 100% 验证 DT 和驱动的正确性。T3 要网线、SD 卡、U 盘这些外部的东西，有就跑、没有咱们就诚实标 `needs <gear>`，咱们绝不装假通过。后面每一章咱们都守着同一条原则。

## 拿原厂同板对照

要判断这块板的硬件到底好不好，咱们别只盯着 forge 自己的 log。咱们把原厂镜像跑在同一块板、同一个 SPI-NAND 上做对照，原厂能读出来的东西，硬件就是好的，forge 读不出来的话，那就是 forge 的软件问题，咱们别轻易往物理或接触上归因。

咱们在 MMC 上栽过这个跟头（[Ch1](01_eth_spi_mmc.md) 细讲）：头一次板验 SD 卡吃到的是 `-110`，咱们一度以为是卡槽接触或主线 dw_mmc 回归，绕了一大圈，最后是靠原厂的同板 log 一眼翻的案，而原厂在同一块板、同一个 dwmmc 控制器上，把同一张卡干干净净地读了出来。其实硬件好得很，真凶是没插紧的 SD 卡。这个方法论后面每章咱们都会用到，判断硬件状态永远拿原厂的同板 log 当锚，软件排掉了再去考虑物理。

## 这个系列怎么走

咱们按 patch 量和难度递增来排：Ch1 三样纯 DT 的外设打头，干的是全套里最清爽的活，而越往后驱动 patch 越多，到 Ch3 移植 WiFi 就是最硬的一仗。

Ch1 讲的是 Ethernet、SPI 和 MMC/SD，打头的三样外设都属“纯 DT、零驱动 patch”。Ethernet 双口通网是这一章的亮点，板子上装了两个 RJ45，用户的网线插哪个口都能通，靠的就是咱们把 gmac0 和 gmac1 两个口的 DT 都补全。

Ch2 讲的是 USB（USB2PHY 加 DWC2）。主线 USB2PHY 驱动缺一个 rk3506 的 of_match，咱们要补上一小块驱动 patch，外加一颗踩了才知道的 DT 雷。USB 通了，Ch3 的 WiFi dongle 才有载体往上挂。

Ch3 讲的是 WiFi（RTL8733BU），也是全套里最硬的一章。板载的这颗 WiFi 是 USB dongle，主线里没它的驱动，咱们得把 Realtek 的一份 out-of-tree 驱动搬到 7.1 上，咱们再 patch 一根线，把它接进 forge 的设备树，走 fork、patch 0016、fetch 脚本的路子。

Ch4 讲的是 I2C/UART（RMIO 交叉开关）。RK3506 的 I2C0/1/2 和 UART2 走一个叫 RMIO 的交叉开关，引脚的 mux 值超出了 iomux 寄存器位宽，而主线 pinctrl 压根不支持，咱们要补一个约 50 行的驱动 patch，把原厂的 `rockchip_set_rmio` 搬进主线。

Ch5 讲的是 Audio（ES8388 加 SAI1）。音频是 codec 加数字音频接口加 DMA 的三件套，三段的主线驱动全都在，但 SAI 的 of_match 表里没 rk3506，DMA 又过一道主线不认的 GRF crossbar，两处接线断了，咱们得补 patch。数字链路点亮（aplay/mpg123 干净播完、声卡注册）是能验的，而真出声还要等耳机线。

Display（DRM 800×1280 DSI）的主线驱动也在，但咱们手头没 LCD，这一章咱们暂不写，等屏幕到位了咱们再补。板子的物理屏是 800×1280（不是常见的 720），原厂在 U-Boot、Linux DRM、weston 三处报的都是 `800x1280@61.4, 67.0 MHz`，而且没调过它就亮了，咱们点亮 800×1280 就能证明物理屏就是这规格。

## 成功长这样

外设点亮的尽头，咱们会在板子上看到这样一整页 dmesg，下面这些行从全链 [boot-sdl-2026-06211109](../../logs/boot-sdl-2026-06211109.txt) 里截的，每行对应一个点亮的外设：

```
rk_gmac-dwmac ff4c8000.ethernet: init for RMII                         ← Ethernet
dwc2 ff740000.usb: DWC OTG Controller                                   ← USB host
usb 2-1.3: new high-speed USB device number 3 using dwc2                ← WiFi dongle 枚举
es8328 0-0011: supply DVDD not found, using dummy regulator             ← Audio codec
rockchip-sai ff310000.sai: ...                                          ← 音频接口
ALSA device list:
  #0: rockchip-es8388                                                   ← 声卡注册
```

一屏 dmesg 里网、USB、WiFi、音频全见到了。咱们 [Ch1](01_eth_spi_mmc.md) 见。
