# 78 — virtio-gpu-gl 桌面加演：从"宿主四路皆断"误诊到单显示形态点亮（2026-08-30）

> 本役完整弧线：GL 档 guest 侧全链谈成但黑屏 → 一度误诊为"宿主 WSL GL
> 全废（dxg 半瘫）"**（错误结论，见 §4 更正）** → 用户问责后补课调研 →
> 真根因是 QEMU 上游 #1727（virgl 给第二个显示设备建 GL 上下文撞断言，
> 我们的 VOP 控制台正是第二个）→ 机器加 `vop-console` 属性走单显示形态
> → **virgl 桌面点亮 + virtio 键鼠交互可用**。

## 0. 最终结论

| 项 | 结果 |
|---|---|
| **virgl 桌面（交互版）** | ✅ `sdl,gl=on`（GLX）+ `virtio-gpu-gl-device` + `-M rk3588-lite,vop-console=off`：GNOME 上 virgl，`QEMU Virtio Keyboard/Tablet` 枚举（/dev/input/event0/1），窗口内可点可敲 |
| 2D 桌面（对照） | ✅ `virtio-gpu-device` + 同显示后端照常（诊断用，GPU_BACKEND=2d） |
| guest 侧证据 | `[drm] features: +virgl +edid`、mutter `Created gbm renderer for card0` |
| QEMU 构建 | virglrenderer+opengl+sdl 全开（meson 重配一次到位） |
| 宿主 GL 实情 | **GLX 完全健康**：240 FBConfig、AttribsARB、direct ctx、GL 4.5 / Mesa 25.2.8 / llvmpipe（ctypes 探针逐项实证）——渲染落在宿主软件 GL（native x86），比 TCG 里的 guest llvmpipe 快一个量级级差 |

## 1. 真根因与修法（qemu GitLab #1727）

```
virtio-gpu-gl + 多显示设备（我们的 VOP QemuConsole 是第二个）
  → virgl 为第二显示设备建 GL 上下文 → epoxy 断言
    "Couldn't find current GLX or EGL context" → QEMU 秒退
```

社区同款经验：多图形设备才触发，单显示 + `display sdl` 可活。修法照抄：
机器加 `vop-console` bool 属性（`object_class_property_add_bool`，virt.c 同款），
默认 on（board 模式看 VOP 窗口）；desktop virgl 形态 `-M rk3588-lite,vop-console=off`
——VOP 影子照常跑，fb 寄存器照常 qom 导出（fbdump 不受影响），只有窗口推送
跳过（scanout 里 `!s->con` 早退）。

## 2. 输入三件套（交互欠账的补法）

- virtio-gpu 是纯显示设备，机器上原本没有任何输入通路 → 键鼠事件无处去
- 内核 `CONFIG_VIRTIO_INPUT=y`（kernel.config 同族休眠配置，真机无
  `virtio_mmio.device=` 参数不激活）
- 机器 virtio-mmio 槽位 4→6；smoke.py desktop/gpu-probe 自动挂
  `virtio-tablet-device`（绝对坐标，GNOME 直接吃）+ `virtio-keyboard-device`
- 踩坑：第一次验证时机器抢先吃到未编 input 驱动的旧 Image（后台编译未收工
  就启动）——`/sys/bus/virtio/drivers/` 无 `virtio_input` 即可判别；Image
  与 System.map 符号核对后才重启，事件设备即现

## 3. 宿主显示后端抉择（WSLg 实测矩阵）

| 后端 | 结果 |
|---|---|
| `gtk,gl=on`（EGL） | 无 /dev/dri 支撑，virtio-gpu 连接器报 disconnected（mutter 无头跑） |
| `egl-headless` | 硬要 `/dev/dri/renderD*`，本机无（启动即拒） |
| `sdl,gl=on`（GLX）★ | 单显示形态下全通——SDL 走 GLX，WSLg X11 的 GLX 链路健康 |

## 4. 误诊更正记录（保留示警）

初版笔记曾写"dxgk ioctls -22 → Windows dxg 栈半瘫 → /dev/dri 永远出不来 →
GL 无解，只能 wsl --update 解锁"。**错误**：
- `dxgk -22` 是 [microsoft/WSL#11293](https://github.com/microsoft/WSL/issues/11293)
  一族已知问题，影响 /dev/dxg 的**计算路径**（CUDA 类），不拦 X11/GLX——
  d3d12_dri.so 与 GLX 探针实证 GL 一直在；
- 两个 dmesg 错误行 ≠ 栈瘫；连"GLX 只支持 legacy visual"的补丁式猜测也是
  错的（240 个 FBConfig 打脸）。
教训入流程：**环境级"无解"结论必须有本地探针 + 外部信源双重实证**，
拿两行日志写"永远"是被用户当场抓包的武断。

## 5. 工具增量（本轮沉淀）

- smoke.py：GPU 设备 `id=gpu0`、GL 显示后端自动配 + `DISPLAY_BACKEND` 覆盖、
  virgl 自动 `vop-console=off`、键鼠设备、`VIRTIO_MMIO` 6 transport
- hvc0 交互技巧：`tail -f /tmp/hvc0-feed | … smoke.py desktop`，往文件追加
  字符即敲 guest console（后台任务的 stdio 也能做交互串口）
- PPM 判活：色度差采样（chroma ≥3/9）防文本屏误报

## 6. 冷启动计时成绩（用户肉眼停表，2026-08-30）

| 配置 | 开机→壁纸露脸 |
|---|---|
| llvmpipe（VOP2 旧流） | 79s（五轮自动实测地板） |
| virgl 宿主 GL | 50s |
| virgl + FAST（quiet loglevel=3 + fw_devlink=off，smoke.py FAST=1） | **45s** |

分解：QEMU 起 ~2s + 内核 ~6s + systemd→login ~16s + gdm→shell(JS×TCG)→上色 ~21s。
剩余大头是 TCG 啃 systemd/gnome-shell 的 CPU 模拟税——继续抠预期收益 ≤5s；
真正的下一档提速 = vmstate 快照战役（秒回桌面），冷启动 45s 定为本线当前地板。

## 6.1 待办（原）

- VOP2 影子在同 DTB 流下的回归验证（real DTB 的 vop 带 iommus，desktop 现在
  走 virtio-gpu，board 模式的 VOP 窗口是否还活需复测）
- 老债：framehunt/snapshot 移植同 DTB 流、qemu-sim-machines.patch 重导、
  virtio_mmio.c 内核树提交、旧 overlay 死文件清理
