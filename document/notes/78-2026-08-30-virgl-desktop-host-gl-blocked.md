# 78 — virtio-gpu-gl 桌面加演：管线全通，宿主 GL 四路皆断（2026-08-30）

> note 77 定的同 DTB + cmdline virtio 路线，2D 档桌面已验证（GNOME 全彩落
> 在 virtio-gpu 控制台）。本役冲 GL 档（virgl 宿主渲染）：guest 侧全链谈成，
> **卡死在宿主 WSL 的 GL 供给**，四条路逐一验尸，根因定位到 Windows 侧 dxg
> 栈半瘫。解锁条件明确，代码零改动可复测。

## 0. 结论

| 项 | 结果 |
|---|---|
| 2D 桌面（virtio-gpu + llvmpipe 渲染） | ✅ 复验两次：`Virtual-1` connected、GNOME 全彩（screendump chroma 8/9），速度同 79s 地板（渲染仍 llvmpipe，符合预期） |
| GL 档 guest 侧 | ✅ `[drm] features: +virgl +edid`（内核与设备谈成）、mutter `Created gbm renderer for /dev/dri/card0`、gnome-shell 全程活着 |
| GL 档宿主侧 | ⛔ 四路全断（见 §2），根因 `dmesg: dxgk ioctls -22`——**Windows 侧 dxg 栈半瘫**，/dev/dri 永不出现 |
| QEMU 构建 | ✅ virglrenderer+opengl+sdl 全开（这步已永久落库，解锁后即用） |

## 1. guest 侧证据链（GL 档为什么说"管线通"）

```
[drm] features: +virgl +edid -resource_blob -host_visible   ← 设备能力谈成
gnome-shell[359]: Created gbm renderer for '/dev/dri/card0'  ← mutter 原生 KMS 渲染器
/sys/class/drm/card0-Virtual-1/status: disconnected          ← 但连接器断着
```

mutter 起了、shell 扩展全加载——不是崩溃是**无头模式**：virtio-gpu 的连接器
状态镜像宿主显示头，宿主 GL 窗口建废 → guest 视角"没插显示器"。

## 2. 宿主四路验尸（全是环境问题，非管线问题）

| 路线 | 死法 |
|---|---|
| `gtk,gl=on`（EGL on X11） | zink/dri2 全败无回落；`LIBGL_ALWAYS_SOFTWARE=1` 后无警告但 virtio-gpu 仍 disconnected（EGL 无 dri 节点支撑） |
| `egl-headless` | 硬性要求 `/dev/dri/renderD*`——本机根本没有（`egl: no drm render node available`） |
| `sdl,gl=on`（GLX） | ctypes 探针证明 legacy GLX 上下文可建（direct OK）；但 QEMU/SDL 走 glXChooseFBConfig/Attribs 路线 → epoxy 断言"no current GLX or EGL context" |
| `LIBGL_ALWAYS_INDIRECT=1` | XWayland GLX 拒 FBConfig 上下文：`X_GLXCreateContext BadValue` |

根因：`dmesg | grep dxg` → `dxgkio_is_feature_enabled/query_adapter_info:
Ioctl failed: -22`。dxg 设备在、ioctls 全废 → WSLg 系统侧起不了 GPU 集群 →
用户发行版永远没有 /dev/dri。

## 3. 解锁条件（Windows 侧，代码零改动）

1. `wsl --update`（PowerShell）+ 更新 Windows GPU 驱动，重启 WSL
2. 验收：用户发行版 `ls /dev/dri` 出现 `renderD128`
3. 直接跑 `python3 boards/rk3588-topeet/sim/smoke.py desktop`（默认 gl 设备，
   headless 自动 `egl-headless`）——若 WSLg X 有 GL 窗口也可
   `DISPLAY_BACKEND=sdl,gl=on GUI=1`

## 4. 工具增量

- smoke.py：GPU 设备 `id=gpu0`（screendump 点名）；GL 设备自动配 GL 显示后端
  （GUI→gtk,gl=on / headless→egl-headless），`DISPLAY_BACKEND` 环境变量可覆盖
- hvc0 交互技巧：`tail -f /tmp/hvc0-feed | … smoke.py desktop`，往文件追加
  字符即敲 guest console（后台任务的 stdio 也能做交互串口）
- PPM 判活：色度差采样（chroma ≥3/9）防文本屏误报

## 5. 待办

- 解锁后首跑：对比 79s 地板 + glmark2-es2 量化 virgl 收益
- 旧债未动：framehunt/snapshot 移植同 DTB 流、qemu-sim-machines.patch 重导、
  virtio_mmio.c 内核树提交
