---
title: "卷四：显示、摄像头与媒体公共地基"
---

# 卷四：显示、摄像头与媒体公共地基

> RK3588 线 · 卷四 · 第 9–13 章 · [返回线总览](index.md)

### 第 9 章：DRM/KMS 与显示管线

一句话：先建 DRM/KMS 通用模型（所有 Linux SoC 一样，RK3588 只是具体 VOP/encoder 不同）——显示接口与屏幕确认后再进真板实验。

要点：

- 对象模型骨架：**plane → CRTC → encoder → connector**；VOP = CRTC + 多 plane
- 四条物理链路各有脾气：HDMI/DP（EDID/link training）、DSI（命令/视频模式）、eDP；D-PHY 物理层
- mode/pixel clock/同步时序：写错就是花屏或无信号；4K@60 约 594MHz 是链路硬约束
- format（FOURCC）/modifier（tiled 不匹配要 RGA 转 linear）/stride——与第 3 章同一套概念落到显示
- atomic modesetting 要么全成功要么全回滚；多 plane 硬件合成是 Android HWC 的核心思想（Android 方向第 4 章展开）；in/out-fence 显式同步

实践：
- `modetest` 枚举对象画拓扑图、点测试图、测多 plane
- 最小 libdrm 做 atomic page flip，ftrace 测提交到显示延迟
- 故意提交不支持的组合分析返回值

### 第 10 章：V4L2、Media Controller 与 ISP

一句话：sensor → CSI → ISP → V4L2 的通用模型——摄像头硬件待真板确认后进受控实验。

要点：

- 链条：sensor（RAW）→ MIPI CSI-2 → D-PHY → ISP（demosaic/3A/降噪/CSC）→ V4L2；元数据走独立节点
- **Media Controller 把链可视化**（`media-ctl -p`）：entity/pad/link，先 link 再 set_format 再 streaming
- buffer queue 三步 REQBUFS/QBUF/DQBUF；**现代零拷贝用 DMABUF 模式**（接第 5 章）
- RAW/YUV/颜色空间（BT.601/709/2020 标错发灰发紫）/stride 与下游协商
- 3A 与 IQ：rkisp 主线有 hook，**IQ 调参是厂商专属，rk-forge 不深入**——但要能识别 IQ 是否加载、3A 是否工作
- 时间戳对齐（与 audio/IMU/显示）是多传感器融合的基础

实践：
- `media-ctl -p` 画 media graph 标 pad 格式
- DMABUF 采集 100 帧落文件核对格式/stride/颜色空间
- 统计丢帧与时间戳分布；不同光照观察 3A 行为

### 第 11 章：MPP 硬件编解码

一句话：MPP 封装 VPU 的用户态库——codec 概念、buffer 模型、**用户态 MPP 与内核 VPU 驱动的边界**（决定 debug 看哪层日志）；支持矩阵以真板为准不预设。

要点：

- codec/profile/level 三件套：解码器必须支持该 profile+level；H.265 Main/Main10 不能同实例
- packet/frame/buffer 三层抽象：1 packet → 1+ frame（B 帧重排）、buffer 复用是性能关键
- 解码要点：**dma-buf 直接给下游不要拷**；码率控制（CBR/VBR/CQP）与 error resilience（IDR request）
- 边界：硬件问题（中断/firmware/IOMMU fault）看内核驱动，应用问题（packet/格式/码率）看 MPP；**MPP/驱动/firmware 三版本必须配对**

实践：
- 硬解受控素材记录格式/帧率/占用/码流统计
- CBR/VBR 对比编码；错误流观察恢复行为
- decoder 输出 dma-buf 直喂 DRM 验证零拷贝；记版本三元组当基线

### 第 12 章：RGA 图像处理

一句话：2D 加速器干「看起来简单但 CPU 做很亏」的活——缩放/裁剪/旋转/CSC；**能换 RGA 就换**。

要点：

- 职责：缩放、裁剪 blit、旋转镜像、CSC（这步每秒吃几 MiB 带宽常被忽视）
- 格式与限制以真板 RGA 版本为准；stride/alignment 不满足就报错或错位；不支持的格式会 fallback CPU 性能塌陷
- RGA vs CPU 软处理：固定功能零 CPU 占用微秒级延迟 vs 任意算法灵活；RGA 不支持的算法重新设计而不是堆 CPU
- **dma-buf 输入输出是正确用法**：「V4L2 → RGA → NPU/DRM」流水线关键一环

实践：
- 组合操作（CSC+缩放+旋转）单次 vs 串行调用对比
- libyuv vs RGA 同任务对比吞吐/CPU/带宽
- RGA 输出直送 DRM 与 MPP 跑双路；写格式支持矩阵模板

### 第 13 章：第一条端到端硬件流水线

一句话：把卷一至卷四前四章的零件拼成最小可跑流水线（建议 `文件或摄像头 → MPP/V4L2 → RGA → DRM`）。

要点：

- buffer ownership：任一时刻只有一个 owner；fd 引用计数管理；**还在 pipeline 里就释放 = fault**，用 fence 显式同步才能安全释放
- backpressure：下游满了上游必须停（有限 queue 深度 + 同步 QBUF/DQBUF）
- queue 深度是 trade-off：交互式浅（1-2）、流媒体深（3-5+），按场景测
- 时间戳同步：统一时钟基准，V4L2/MPP PTS/audio/vsync 可换算——多传感器融合的基础
- 错误传播与资源回收是健壮性硬指标：单帧错误不杀 pipeline、设备错误优雅停止、重启干净恢复（bufinfo 验证无残留）

实践：
- 端到端 pipeline 稳跑 30 分钟并每秒记录六项指标
- 模拟输入中断验证优雅停止与干净恢复
- 调 queue 深度画 trade-off 曲线；写「错误传播矩阵」

完成公共必修（卷一至卷四）后才能进入专业方向。

## 素材与取证

| 资产 | 用途 |
|---|---|
| [tutorial/rk3588/03_lcd](../../tutorial/rk3588/03_lcd.md) | 第 9 章强锚点：DSI→LVDS（TC358775）真板出图全程 |
| LCD 笔记：[44](../../notes/44-2026-07-31-rk3588-lcd-dsi-panel-port.md)、[45](../../notes/45-2026-07-31-rk3588-lcd-bringup-blockers.md)、[46](../../notes/46-2026-07-31-rk3588-lcd-dsi2-video-blocker-handoff.md)、[47](../../notes/47-2026-08-01-rk3588-lcd-video-fix-tc358775-init-prepare.md) | DSI/面板移植取证（五坑） |
| VOP2 战役：[71](../../notes/71-2026-08-28-vop2-campaign-power-domain-cascade.md)、[72](../../notes/72-2026-08-28-vop2-campaign2-drm-initialized.md)、[73](../../notes/73-2026-08-28-vop2-campaign3-kms-userspace.md)、[74](../../notes/74-2026-08-29-vop2-campaign4-desktop-lights.md)、[54（hardlock 修复）](../../notes/54-2026-08-02-rk3588-vendor-vop2-handoff-hardlock-fix.md) | 第 9 章 DRM/VOP2 取证；hardlock 未闭环现状见线总览 |
| 触摸笔记：[52](../../notes/52-2026-08-02-rk3588-gt911-vendor-polling-i2c-v5.md)、[55](../../notes/55-2026-08-02-rk3588-gt911-landscape-axis-fix.md) | input/触摸素材 |
| eai 仓互指 | V4L2/ISP 管线应用侧在 eai A2.6，内核侧在此 |
| books/RK3588 的 9.多媒体开发、12.多屏显示目录 | 厂方媒体/显示参考（`.claude/books/`，本地资料） |
