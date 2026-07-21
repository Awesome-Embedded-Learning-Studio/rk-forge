# Ch5 — Audio（ES8388 + SAI1）：点亮数字音频链路

> 外设系列最后一站。RK3506 这块板的音频是 ES8388 codec + SAI1 数字接口 + PL330 DMA 三件套，三样的主线驱动全在，但其中两样缺 RK3506 的接线：SAI 的 of_match 表里没 rk3506，PL330 的 DMA 请求又要过一个 GRF crossbar、主线那个单 cell 的 xlate 不认。这章把数字链路点亮，aplay/mpg123 能干净播完、声卡注册。真出声还得等耳机线——板上的耳机接口得接线——但数字链路这一关，板上过了。

## 链路长什么样：codec ↔ SAI1 ↔ PL330

音频这趟水从 codec 流到内存，中间过两道桥：`ES8388(codec) ↔ SAI1(数字音频接口) ↔ PL330(DMA)`。ES8388 这颗 codec 主线驱动就在（`everest,es8388`，走 I2C 控制，老牌的 ES8328 驱动 `SND_SOC_ES8328_I2C` 兼容它）；SAI1 是 RK 这边的 I2S 数字接口，主线 `rockchip_sai.c` 也在；最末段 DMA 用 ARM 的 PL330，主线 `pl330.c` 驱动也在。三段驱动全现成，听上去就是接线的事。

可两处接线断了。SAI 驱动的 of_match 表里压根没有 `rockchip,rk3506-sai`，probe 不到；DMA 这边更绕——RK3506 把外设的 DMA 请求过了一道 GRF crossbar（多路选择），主线 PL330 的 `of_dma_pl330_xlate` 只认单 cell 的 `dmas = <&dmac channel>`，不认 RK3506 这套 5-cell 编码。所以这一章的活儿就是 [0009](../../../patches/linux/0009-ASoC-dmaengine-rk3506-sai-pl330-dmamux.patch)（驱动侧：SAI of_match + PL330 5-cell dmamux）加 [0010](../../../patches/linux/0010-ARM-dts-rockchip-rk3506b-aes-ES8388-audio-sai1-dmac.patch)（DT 侧：sai1 + dmac0/dmac1 + es8388 + simple-card）。

## DMA 那道 crossbar：为什么是 5 个 cell

PL330 这段的弯绕值回票价，单独说。一般 SoC 的 DMA 请求是直连的——外设发请求、DMA 控制器接，DT 里 `dmas = <&dmac 5>` 一个 cell 搞定，那个 5 就是 channel 号。RK3506 偏不，它在外设和 DMAC 之间塞了一层 GRF crossbar，本质是个多路开关：同一个 channel 号，物理上能路由到不同外设的请求源。于是 DT 里 `dmas` 就得写成 5 个 cell：`<dmac channel mux_reg0 mux_val0 mux_reg1 mux_val1>`——channel 之后跟两对"寄存器地址 + 写入值"，DMA 拿到 channel 时按这两对去配 crossbar，把路由拨到对应外设。

主线 `of_dma_pl330_xlate` 当年只认 1 个 cell，撞见 5 个直接拒。我们的改法是把那个 `count != 1` 的拒收闸门放宽成 `count < 1`（拒掉 0 和负数，单 cell 用户原样不动），再在 `count == 5` 时多跑一段——把后面两对 mux reg/val 写进 GRF。这样单 cell 的所有其他 SoC 行为不变，RK3506 这套 5-cell 的也能跑。SAI1 实际用到的 DT 值待会儿贴。

## DT 接线

DT 侧的活儿在 SoC 级 `rk3506.dtsi` 和板级 `rk3506b-aes.dts` 各加一坨。SoC 级加两个 dmac 节点（`dmac0@ff000000`、`dmac1@ff008000`，都标 `#dma-cells = <5>`）和一个 sai1 节点；板级启用 sai1、在 i2c0 挂 es8388、再用 simple-audio-card 把它们缝成一张声卡。SoC 级 sai1 长这样（细节在 [0010](../../../patches/linux/0010-ARM-dts-rockchip-rk3506b-aes-ES8388-audio-sai1-dmac.patch)）：

```dts
sai1: sai@ff310000 {
    compatible = "rockchip,rk3506-sai", "rockchip,sai-v1";
    reg = <0xff310000 0x1000>;
    clocks = <&cru MCLK_SAI1>, <&cru HCLK_SAI1>;
    clock-names = "mclk", "hclk";
    /* 5-cell：<dmac chan mux_reg mux_val mux_reg mux_val>，GRF crossbar */
    dmas = <&dmac1 3  0xff2880a4 0x04000000 0x0 0x0>,   /* tx */
           <&dmac1 2  0xff2880a4 0x02000000 0x0 0x0>;   /* rx */
    dma-names = "tx", "rx";
    /* sdo0 only（stereo）；sdo1/2/3 会跟 i2c0 在 PB5/6/7 撞 */
    pinctrl-0 = <&sai1_mclk_pins &sai1_sclk_pins &sai1_lrck_pins
                 &sai1_sdi_pins &sai1_sdo0_pins>;
};
```

看 dmas 那行就是上一节说的 5-cell：tx 是 channel 3、rx 是 channel 2，后面 `0xff2880a4` 是那颗 GRF crossbar 的寄存器，`0x04000000`/`0x02000000` 是写给 tx/rx 各自的路由选择位，最后一对 `0x0 0x0` 是占位（sai1 只用一组 mux）。pinctrl 这行也交代一个细节：SAI1 的数据线 sdo0/1/2/3 跟 i2c0 的 rm_io13/14 在 bank0 的 PB5/6/7 上物理冲突，所以 SAI1 只引 sdo0（stereo 单线够用），把 sdo1/2/3 让掉，pad 落在 PB0-PB4。

板级那坨是 codec 和声卡：

```dts
&i2c0 {
    es8388: es8388@11 {
        compatible = "everest,es8388";
        reg = <0x11>;
        clocks = <&cru MCLK_OUT_SAI1>;
        clock-names = "mclk";
        assigned-clocks = <&cru MCLK_SAI1>;
        assigned-clock-rates = <12288000>;
    };
};

/ {
    sound {
        compatible = "simple-audio-card";
        simple-audio-card,name = "rockchip-es8388";
        simple-audio-card,format = "i2s";
        simple-audio-card,mclk-fs = <256>;
        simple-audio-card,cpu  { sound-dai = <&sai1>; };
        simple-audio-card,codec { sound-dai = <&es8388>; };
    };
};
```

声卡我们用了主线的 `simple-audio-card`，vendor 那套是用私有的 `rockchip,multicodecs-card` 机器驱动——主线能干的事就不背 vendor 的包袱。

## 几个坑

链路跑通踩了几颗雷，按出现顺序记一下。

ES8328 的 I2C 驱动 `SND_SOC_ES8328_I2C` 是个**隐藏 tristate**——它在 menuconfig 里平时根本看不见，得它依赖的 `SOUND`、`SND_SOC` 都先开起来才会冒出来。笔者第一次满世界 `.config` 搜它搜不到，以为是 patch 漏了，其实只是 menuconfig 把它折叠起来了。

codec 的 `set_sysclk` 只认 **11.2896 / 12.288 / 22.5792 / 24.576 MHz** 这四档（或 0），喂别的频率 HAL 直接 `-EINVAL`、声卡 probe 失败。我们选 12.288 MHz——它等于 256 × 48000，正好是 48kHz 播放的经典 MCLK。落 DT 就是上面 es8388 节点里那行 `assigned-clock-rates = <12288000>`，把 sai1 的 mclk composite 固定住，否则 codec 拿到默认 mclk 就翻脸。`mclk-fs = <256>` 那行也是配套的，声卡侧按这个比算 mclk。

SAI1 的 pinctrl 跟 i2c0 在 bank0 的 PB5/6/7 上物理冲突——SAI 的 sdo1/2/3 和 i2c0 的 rm_io13/14 抢同一组 pad。解法是 SAI1 只用 sdo0（stereo 单线就够），把 sdo1/2/3 让给 i2c0。所以 DT 里 sai1 pinctrl 只引 mclk/sclk/lrck/sdi/sdo0，落在 PB0-PB4。

板子默认是 mute 的。`aplay` 跑完没报错但就是没声，先别怀疑链路，进 `alsamixer` 把通路 unmute、音量推上去。这步听着废话，但笔者在"数字链路全通、就是没声"上耗过半小时。

还有一条 config 的坑：`kernel-trim.config` 曾经把 `SOUND` 砍掉省体积，后来发现是误诊，省的那点体积不值得。音频这块要保证 `SOUND=y` + `SND_SOC_ES8328_I2C=y` + `SND_SIMPLE_CARD=y`。

## 成功长这样

数字链路点亮、声卡注册。下面这些行从全链 [boot-sdl-2026-06211109](../../logs/boot-sdl-2026-06211109.txt) 里截的：

```
es8328 0-0011: supply DVDD not found, using dummy regulator     ← codec 上线
rockchip-sai ff310000.sai: ...                                   ← 数字接口 probe
ALSA device list:
  #0: rockchip-es8388                                            ← 声卡注册
```

ES8388 codec 上线、SAI1 数字接口 probe、ALSA 注册了 `rockchip-es8388` 这张声卡。板上验证：

```bash
aplay /path/to/test.wav              # 干净播完，无 XRUN
mpg123 -r 48000 /path/to/test.mp3    # 同样干净
```

数字链路这一关板上过了；模拟输出要等耳机线接上才能验证真出声（板上耳机接口得接线）。

## 还没解的几颗雷

链路通了不代表没尾巴，记下几条 follow-up，不挡交付但值得知道。一是 **44.1kHz 的 cru 时钟**——现在 48kHz 干净，44.1k 那档 cru 配置还没细调，播 44.1k 的源可能 XRUN。二是 **XRUN 的容忍**——重负载下偶发 XRUN，没深查是 DMA 调度还是时钟抖动。三是 **音量持久化**——`alsamixer` 设的音量重启后丢，得存 `alsactl store` + 开机 restore。四是 **clk-out**——现在 mclk 走的是 cru 的 `MCLK_OUT_SAI1` gate，板上能跑就没动它；万一哪天 mclk 没到 codec（主线缺 vendor 那个 `rockchip,clk-out` 的 GRF to-IO gate 节点），得补个 clk-out 驱动。
