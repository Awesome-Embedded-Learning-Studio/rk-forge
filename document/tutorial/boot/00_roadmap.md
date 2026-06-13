# Ch0 — 路线图：为什么是 RK3506，为什么 mainline-first

> 状态：草稿。板型/SDK 拉取后补"实验环境"块与具体版本。

## 前言

rk-forge 不是又一个 Rockchip 镜像发行版。它服务**没人服务的 RK3506**，目标只有一个：
**用主线 Linux 把 RK3506 启动到 UART，并诚实报告还差什么。**

## RK3506 启动链

```
ROM → rkbin(TPL/SPL, 闭源, DDR 初始化) → U-Boot(开源, 主线) → Linux(开源, 主线) → rootfs → init
```

关键事实（2026-06 已核实）：
- **pinctrl + clock** 自 Linux 6.19 起在主线（目标 **7.0.x**，6.19 已 EOL）。
- **U-Boot SoC 支持**（Jonas Karlman v2）已合并进主线 U-Boot。
- **唯一绕不开的闭源** = `rkbin`（DDR 初始化）；**唯一上游没有的** = 板级设备树。

## 为什么是 RK3506

好做的别人都做了（Armbian/Buildroom/Collabora 把 RK3588/RK3568 做烂了）。RK3506 是
真空。做深不做宽，避开红海。

## 为什么 mainline-first

主线 = 可持续、可上游、可教。BSP 是 Phase 4 的安全网，不是主线。

## 本教程的四个章节

- **Ch1** 工具链（armhf，与 i.MX6ULL 同 Cortex-A7）
- **Ch2** U-Boot + rkbin：为什么 blob 绕不开，binman 打包，烧录，UART 见 banner
- **Ch3** 内核到 console：在已合并的 SoC 支持上**加板级 DT**，解码 bootlog 到 earlycon

每章结尾："成功长这样"——**真实 UART 抓取**，绝不合成。
