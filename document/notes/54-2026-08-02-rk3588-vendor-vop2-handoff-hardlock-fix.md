# 54 RK3588 vendor VOP2 handoff 补全与 hard-lock 候选（2026-08-02）

接 [53](53-2026-08-02-rk3588-hard-lockup-ramoops-watchdog.md)。本轮目标不是回退
vendor 的旧 DDR/SPL/BL31/U-Boot，而是在继续使用新版启动链和 Linux 7.1 的前提下，
审计 TOPEET/Rockchip BSP 中没有迁入主线板级实现的硬件初始化语义。

## 新证据

完整 panic 最早保留下来的异常不是 watchdog 栈，而是 DRM 启动阶段连续三次：

```text
rockchip-drm display-subsystem: [CRTC:83:video_port2] vblank wait timed out
```

随后 CPU6 的 buddy hard-lock detector 在约 16 秒报告 CPU7 hard lock。panic 中的
CPU6 栈只是观察者，不能用来断言 CPU7 卡在 cpuidle。此前 `nomodeset` 或
`fbcon=disable` 能避开早期冻结，也把故障域指向 VOP/DSI modeset handoff。

逐项比较 vendor `rk3588s.dtsi` 和 VOP2 驱动后确认主线板级移植漏了三项相关语义：

- VOP ACLK 固定为 750 MHz；
- VP2 的 `DCLK_VOP2_SRC` 以 `PLL_V0PLL` 为父时钟；
- vendor 在视频口 timing/config commit 后脉冲对应 `dclk_vpN` reset，再开启 vblank。

主线基础 DTS 没有这六路 reset 描述，主线 VOP2 驱动也没有获取或脉冲
`dclk_vpN`，所以单纯把 `vp2 -> dsi0` graph 接通并不等价于 vendor 的硬件 handoff。

## 实现

新增：

- `0009-drm-rockchip-align-RK3588-VOP2-dclk-handoff-with-BSP.patch`
  - 板级 `&vop`：ACLK 750 MHz、AXI/AHB/VP0-3 DCLK resets；
  - 板级 `&vp2`：`DCLK_VOP2_SRC -> PLL_V0PLL`；
  - 主线 VOP2：按名字获取 optional `dclk_vpN` reset；
  - timing/interface commit 后 assert 10 us、deassert，与 vendor 时序对应。

新版 DDR/SPL/BL31、主线 U-Boot 和 Linux 7.1 均保持不变，没有替换为 vendor
`MiniLoaderAll.bin` 或 `uboot.img`。

## 明确未纳入

`0007` I²C v5 auto-stop 与 `0008` GT911 polling 仍从 `series` 排除。组合候选
`c670a208…` 已被真机否决，不能因为 vendor 源码中存在相似实现就重复烧录。
而且 reference 的正常默认屏配置实际是 MIPI1/FT5x06，并没有启用这块
LVDS 1024×600/GT911 路径；因此它不能作为 GT911 polling 已板验的证据。

本候选继续使用 GT911 的 pull-up + falling-edge 最小 IRQ 修复，先解决系统 hard lock，
触摸功能待系统稳定后单独继续。

## 可复现与二进制门禁

- 从 v7.1 空树依次 `git am` 0001–0006、0009：通过；
- DTS、VOP2、I²C、Goodix、RK860X、FIQ 七个关键文件与实际构建树逐字节一致；
- `Image + rk3588-topeet.dtb` 编译通过；
- 编译 DTB 反查确认 ACLK=750 MHz、六个 reset name、VP2/V0PLL parent；
- Image 中存在 VP DCLK reset 路径；
- Image/DTB 中不存在已否决的 I²C v5 auto-stop、GT911 polling 标记；
- `pack -> assemble` 通过，RKAF/RKFW round-trip 自检通过。

## 待烧候选

```text
update.img size:    3290329674 bytes
update.img SHA-256: 2846097b24e3293bdfb5366b74cadcfdb8d56fb36565b83b36ccf8fb5f63d9a3
boot.img SHA-256:   4b3f16779fea97383e5dd2393d2490c8d25e7d2b8ea7c964e7e1c234a1fa8346
Image SHA-256:      a6eee3c5f3459d93d2cb640187d180e420dc89d0ecb53362c7db9a35188c05df
DTB SHA-256:        8c9e6cf882cdc9e99435f2db96ed95331021d4e1b75afba0a0de96428a113e4e
```

该镜像是因果收敛后的候选，不得在真机连续冷/热启动和桌面运行验证前写成“稳定”。
首轮板验重点：

```sh
dmesg | grep -iE 'vblank|dclk reset|rk3x-i2c|timeout|cpufreq|voltage|Hard LOCKUP'
cat /proc/interrupts | grep -iE 'goodix|gt911'
```

通过标准是启动阶段不再出现 VP2 vblank timeout，连续多轮启动和桌面运行无 hard lock；
GT911 IRQ/事件另行记录，不与稳定性结论混写。
