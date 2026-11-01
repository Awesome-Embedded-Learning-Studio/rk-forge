---
title: "卷六：显示与 HMI 选修"
---

# 卷六：显示与 HMI 选修

> RK3568 线 · 卷六 · 第 18 章 · [返回线总览](index.md)

### 第 18 章：DRM/KMS 入门

一句话：先建 DRM/KMS 通用模型（所有 Linux SoC 通用）——显示接口与屏幕确认后才能形成真板实验。

要点：

- fbdev 已淘汰，现代显示走 DRM/KMS；`/dev/dri/card0` 与 render node
- 四个核心对象及拓扑：**plane → CRTC → encoder → connector**；Rockchip VOP = CRTC + 多 plane
- mode/pixel clock 的时序含义与来源（EDID 自动协商 vs DSI/eDP 面板写 DT）
- pixel format（FOURCC）、modifier（tiled/linear，不匹配要 RGA 转）、stride
- atomic modesetting 一次提交要么全成功要么全回滚；page flip 在 vsync 边界避免撕裂

**panel 移植实战要点组**（板验素材已在，作为本章的实作纵深）：

- MIPI-DSI 面板点亮全程：ILI9881C 时序、初始化序列、供电时序与 gotcha 清单（panel IC 型号在两篇笔记里两说——HX8394 vs ILI9881C，写真板教程前必须在板上核对）
- HDMI：EDID 解码、HPD 热插拔 uevent、1080p60 点亮
- 三屏同显/异显/异触：多 connector 在线 + 双触摸各自有效（硬件门：接口与配套屏待确认）
- dclk 带宽限制：underflow 降配验证；显示调试方法论（stride 花屏、HPD 无信号各一次定位实录）

实践：
- `modetest` 枚举对象并点测试图
- 最小 libdrm 程序做 atomic page flip；ftrace 抓提交到显示的延迟
- 故意提交不支持的组合，分析 atomic 返回值

## 素材与取证

| 资产 | 用途 |
|---|---|
| [tutorial/rk3568/02_peripherals](../../tutorial/rk3568/02_peripherals.md) | LCD（ILI9881C）与触摸板验素材；panel IC 型号两说（HX8394 vs ILI9881C）写真板教程前须核对 |
| [RK3588 线 · 卷四（媒体公共地基）](../rk3588/04-media-foundation.md) | DRM/VOP2 深入在那边，互指不重复 |
| eai 仓互指 | V4L2/视频流管线应用侧在 eai A2.6，内核 DRM 侧在此 |
