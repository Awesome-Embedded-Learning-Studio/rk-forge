# Ch5 — Audio（ES8388 + SAI1）：点亮数字音频链路

> 外设系列最后一章。RK3506 这块板的音频是 ES8388 codec + SAI1 数字接口 + PL330 DMA 三件套。三样主线驱动都在，但两样缺 RK3506 的接线：SAI 缺 of_match、PL330 的 DMA 请求要过一个 GRF crossbar（主线那个单 cell 的 xlate 不认）。这章把数字链路点亮——aplay/mpg123 能干净播完、声卡注册。真出声还得等耳机线（板上的耳机接口得接线），但数字链路这一关，板上过了。

## 三个件，两处缺接线

音频链路是 `ES8388(codec) ↔ SAI1(数字接口) ↔ PL330(DMA)`。ES8328 这个 codec 主线驱动在（`SND_SOC_ES8328_I2C`）；SAI 主线 `rockchip_sai.c` 也在，但 **of_match 里没有 rk3506**；DMA 这边，RK3506 的 DMA 请求要过一个 GRF 的 crossbar，而主线 `of_dma_pl330_xlate` 是单 cell 的，**不认 RK3506 那个 5-cell 的编码**（`dmas = <dmac chan mux_reg val …>`）。所以这一章是 [0009](../../../patches/linux/0009-ASoC-dmaengine-rk3506-sai-pl330-dmamux.patch)（驱动：SAI of_match + PL330 5-cell dmamux）加 [0010](../../../patches/linux/0010-ARM-dts-rockchip-rk3506b-aes-ES8388-audio-sai1-dmac.patch)（DT：sai1 + dmac0/dmac1 + es8388 + simple-card）。

## 几个 gotcha

跑通这条链踩了几个坑，记一下。一是 ES8328 的 I2C 驱动 `SND_SOC_ES8328_I2C` 是个**隐藏 tristate**，得它依赖的 `SOUND`/`SND_SOC` 都开了才会出现在 menuconfig，别满世界找它找不到。二是 codec 的 `set_sysclk` 要喂 **12288000**（不是随便一个频率），时钟不对 HAL 起不来。三是 SAI1 的 pinctrl 跟 i2c0 在 PB5/PB6 上**冲突**，所以 sai1 只用 sdo0（stereo），避开 i2c0。四是板子默认 mute，aplay 不出声先别慌，`alsamixer` 把通路 unmute。还有 config：`SOUND=y` + `SND_SOC_ES8328_I2C=y` + `SND_SIMPLE_CARD=y`，而且 `kernel-trim.config` 不能再砍 `SOUND`（之前一度误判为省体积砍过，其实是误诊）。

## 成功长这样

数字链路点亮，声卡注册。这些行从全链 [boot-sdl-2026-06211109](../../logs/boot-sdl-2026-06211109.txt) 里截的：

```
es8328 0-0011: supply DVDD not found, using dummy regulator     ← codec 上线
rockchip-sai ff310000.sai: ...                                   ← 数字接口
ALSA device list:
  #0: rockchip-es8388                                            ← 声卡注册
```

ES8388 codec 上线、SAI1 数字接口 probe、ALSA 注册了 `rockchip-es8388` 这张声卡。`aplay` 和 `mpg123 -r 48000` 在板上能把一首曲子干净播完（数字链路这一关过了）；模拟输出要等耳机线接上才能验证真出声。

## 外设系列走完

到这里，Ethernet（双口通网）、SPI、MMC/SD、USB（双 host）、WiFi（RTL8733BU 联网）、I2C/UART（RMIO）、Audio（数字链路）全部点亮。一块"能开机的砖"，现在是一块能联网、能插 U 盘、能连 WiFi、能出声的板子了。Display（屏幕）等 LCD 到位再补。给板子拍张照，外设系列完结撒花。
