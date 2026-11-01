---
title: "Android 方向（RK3588 线）"
---

# Android 方向

> RK3588 线 · Android 方向 · 方向内第 1–6 章（主题：Android 系统结构） · [返回线总览](index.md)
>
> 引用本方向章节时带方向名，如「Android 方向 · 第 3 章」。使用 Rockchip Android SDK 时，必须记录 SDK、内核、固件和板卡的准确版本，不照搬厂商文档。

### 第 1 章：AOSP、Rockchip SDK 与分区

一句话：Android 产品化最重的一块——AOSP 是什么、vendor BSP 干什么、分区怎么切；**AOSP 不是 Linux 发行版**。

要点：

- AOSP（上游）与 vendor BSP（下游适配）分层，版本严格匹配；把 Linux 习惯带到 Android 是常见错误
- 分区模型是第一道门槛：boot/vendor_boot/system/vendor/product/userdata 各角色；A/B 双分区是现代标配
- GKI（Android 12+）：通用内核与 vendor 模块解耦；版本三方对齐（AOSP ↔ GKI 内核 ↔ vendor module ABI）；具体版本立项时定，不预设
- 调试三件套 adb/fastboot/recovery，与 Linux 的 ssh+dmesg 根本不同
- Linux 与 Android 启动链根本差异：init 用 .rc、应用从 Zygote fork、binder IPC、SELinux 强制——**别把 Linux 假设照搬**

实践：
- 列全板分区并标注角色/大小/文件系统/A-B；getprop 出「系统身份卡」
- 跟踪一次启动画时间线；分析一次失败启动出诊断清单

### 第 2 章：init、SELinux、Zygote 与 System Server

一句话：Android 用户态怎么起来——**SELinux 是 Android 工程师最容易卡住的地方**，重点讲。

要点：

- init 是 PID 1，读 `.rc`（service/on/setprop/trigger）；与 systemd 的差异要重学
- property 系统是系统级 KV，服务启停常由 property 触发，改 property 是测试常用手段
- SELinux：permissive（开发）/enforcing（产品必须）；denial 日志读法 → 写 `.te` allow 规则
- Zygote 模板进程 → System Server（系统大脑）→ 应用进程；任何一环卡住看不到桌面
- bootanimation 与 `sys.bootcomplete`；三类卡黑屏典型场景

实践：
- 跟踪一个服务从 rc 到运行的全程
- 故意触发一次 denial 并写出 allow 规则修复
- 分析一次「bootanimation 后卡黑屏」反推卡点

### 第 3 章：从内核设备到 Android 服务

一句话：binder/HAL/AIDL 这套 IPC 与硬件抽象——**kernel → HAL → Framework → App 四层调用是 Android 系统工程师的基本功**。

要点：

- binder 一次拷贝、ServiceManager 服务发现；高频调用要批处理/异步
- HAL 形态演进（旧版 → HIDL → AIDL）；Treble 让 Framework 与 Vendor 可独立升级
- 实现一个 HAL 的五步：定义 `.aidl` → 生成桩 → 实现 → 注册 → getService
- 应用只能用公开 API；权限（Manifest）与 SELinux 是两层安全模型
- 一次「拍照」的完整四层链路；**bug 可能在任一层**——logcat/dumpsys/HAL 日志/dmesg 各看一层

实践：
- 把一个简单硬件能力（GPIO LED 或传感器）从内核驱动一路暴露到 App，保存每层证据
- 制造跨层错误建诊断清单；测量一次完整调用链的分层耗时

### 第 4 章：Android 人机交互链

一句话：SurfaceFlinger/HWC/Audio/Input 怎么把画面声音输入接到用户——底层就是 Linux 的 DRM/ALSA/Input，Android 加了一层 HAL。

要点：

- SurfaceFlinger 是 DRM 的用户态消费者；BufferQueue → 合成 → DRM atomic 提交
- **HWC 是流畅度关键**：硬件合成零 GPU/CPU 开销；每个 HW 合成 Surface 对应一个 DRM plane
- AudioFlinger + Audio HAL 封装 ALSA；产品级要处理路由切换
- InputReader/EventDispatcher/焦点窗口；多屏/旋转/触摸-显示映射/热插拔的产品场景
- 调试分界：底层硬件 bug 看 dmesg，Framework 问题看 logcat；**Linux DRM/ALSA/Input 知识依然适用**

实践：
- dumpsys 看 SurfaceFlinger/audio 状态；getevent 看输入
- ftrace/systrace 抓一次完整合成；多屏/旋转/热插拔测试
- 制造 HWC 失败（plane 不够）观察 GPU fallback 的性能差异

### 第 5 章：Camera HAL 与 MediaCodec

一句话：Android 怎么用摄像头与硬编硬解——Camera2 到 ISP、MediaCodec 到 MPP，底层还是公共必修那套。

要点：

- Camera2 API/CameraService/Camera HAL 三层；多流（预览+拍照+分析）；**IQ 调参厂商专属不深入**，但要能判断 IQ/3A 是否工作
- MediaCodec 是应用层标准 API，HAL 内部调 MPP；异步模式吞吐更高；**零拷贝路径走 Surface**
- 调试分界：MediaCodec 行为看 logcat，MPP/VPU 内部看厂商日志/dmesg
- 权限与 SELinux：CAMERA/RECORD_AUDIO 运行时请求；HAL 进程的 `.te` 同步写；Android 12+ 指示器要求

实践：
- 最小 Camera2 应用（预览+拍照）与 MediaCodec 硬解到 Surface
- 多流相机测试；制造错误观察回调路径；enforcing 下无 denial 验证

### 第 6 章：形成可维护 Android 产品

一句话：能跑的 Android → 可维护的产品——定制、A/B OTA、回滚、工厂恢复，本方向收口。

要点：

- Launcher/SystemUI 定制走 product 分区与 overlay，分层覆盖（AOSP → vendor → product → OEM）
- A/B OTA 全流程（UpdateEngine/bootctrl/双槽/失败回滚）；full vs incremental 推送策略
- 回滚：新槽启动失败 N 次自动回旧槽
- **升级路径必须测**：数据库 schema/接口废弃/SELinux 策略变更，很多 bug 只在升级路径出现
- 工厂恢复/诊断模式/adb bugreport 的产品化处理

方向产出：kernel—HAL—Framework—App 完整闭环、系统定制方案、升级与回滚方案、24 小时稳定性证据、恢复与诊断方案。

## 素材与取证

| 资产 | 用途 |
|---|---|
| books/RK3588 的 5.Android系统开发目录 | 厂方参考（`.claude/books/`，本地资料） |
| [卷一第 2 章（启动链与分区）](01-platform-boot.md) | Linux/Android 双路径的启动侧基础 |
| 独立调研方向 | 启动条件（SDK 版本、硬件配套）见线总览的「明确不讲或推迟」与硬件确认门 |
