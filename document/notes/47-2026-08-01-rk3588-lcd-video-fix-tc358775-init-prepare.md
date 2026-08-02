# 47 RK3588 LCD 视频空白根因 + TC358775 桥确认 + init→prepare 修复 (2026-08-01)

接 [46](46-2026-07-31-rk3588-lcd-dsi2-video-blocker-handoff.md)：DSI2 管线全 bind、panel 亮、VOP2 在扫描，但**屏无画面**。本篇记这一关的真凶 + 桥 IC 确认 + 修复。这是整个 LCD 移植最深的坑。

## 症状回顾

- DRM/VOP2/DSI2/PHY 全 bind，connector enabled/dpms On/mode 1024×600，dmesg 无报错。
- debugfs：`crtc video_port2 active=1`，mode 正确，connector 绑 vp2 → VOP2 在扫描。
- `head -c 2457600 /dev/urandom > /dev/fb0` → **屏空白**（像素没到 panel）。
- vendor BSP 同 mode 同 DSI 配置能正常使用屏。

## 深挖过程（排除法）

1. **subagent 逐行对照 mainline DSI2 core+glue+PHY vs BSP**：视频模式切换序列、IPI 配置、lane rate（10/9 burst overhead）、samsung-dcphy power_on、GRF 写——**全部功能等价，mainline 没漏寄存器**。排除了"驱动代码 bug"。
2. 剩下两嫌疑：VOP2→DSI2 IPI 路由 / 桥同步没锁。把问题凝练成自包含诊断文档（`document/logs/rk3588/dsi2-video-blank-diagnosis.md`）找大 AI。

## 大 AI 诊断 + 我的核实

- **桥 IC = Toshiba TC358775/774 家族**（大 AI 认出，我起初看错了）：init-seq 的 6 字节 payload 不是单字节寄存器，是 **`[addr_lo, addr_hi, data_le32]`**（小端 16-bit 寄存器 + 32-bit 数据）。解码我的序列：
  - `04 01 01 00 00 00` → addr **0x0104** (PPI_STARTPPI) = 1
  - `04 02 01 00 00 00` → addr **0x0204** (DSI_STARTDSI) = 1
  - `9C 04 31 04 00 00` → addr **0x049C** (LVCFG) = 0x431（LVDLINK=0 → single-link）
  - 主线有 `drivers/gpu/drm/bridge/tc358775.c`（备选：可直接用主线 bridge 驱动）。
- **真凶 = init 阶段**：vendor 在 `panel_simple_prepare()` 发 init；我的 OOT 驱动在 `.enable` 发。DSI2 host 在 panel `.enable` 前已切 video mode（atomic_enable，见 `dw-mipi-dsi2.c:847`），init 此时走 video-mode LP 注入（`host_transfer` 的 LPDT_DISPLAY_CMD_EN）——**但对 TC358775 桥不可靠**，桥没真正初始化 → 无视频。

## 修复

`panel-topeet-dsi.c` 把生命周期改成跟 vendor 一致：
- **init-sequence**：`.enable` → `.prepare`（供电+复位后、DSI2 切视频模式前，command mode 里发）。
- **exit-sequence**：`.disable` → `.unprepare`（断电前）。
- `.enable`/`.disable` 只留延时；init 失败时 regulator_disable 回滚。

## 真机结果

`update.img` MD5 `370c0597`：**boot logo（企鹅）正常显示 + fb0 灌噪点花屏**。LCD 视频管线全通。

## 教训

1. **DSI panel/bridge 的 init 一律放 `.prepare`，别放 `.enable`**——DSI2 控制器在 enable 前已切 video mode，video-mode LP 注入对桥不可靠。vendor panel-simple 也是 prepare 发。这是上游 RK3576 DSI2 也踩过的坑。
2. **payload 格式别想当然**：DSI generic long write的 payload 对不同桥含义不同。TC358775 是 `[addr_lo, addr_hi, data_le32]`，不是单字节寄存器。认桥 IC 要看 datasheet 寄存器表。
3. **"驱动代码等价"不等于"行为等价"**：subagent 证明 mainline 跟 BSP 寄存器级等价，但 bug 在 panel 驱动的调用阶段（上层），不在 DSI2 驱动（下层）。

## 关键文件

- `drivers/gpu/drm/panel/panel-topeet-dsi.c`：prepare 发 init、unprepare 发 exit（patch 0001 待 regen 纳入）。
- 诊断文档：`document/logs/rk3588/dsi2-video-blank-diagnosis.md`（给大 AI 的自包含交接）。
- 桥寄存器参考：主线 `drivers/gpu/drm/bridge/tc358775.c`（PPI_STARTPPI 0x0104 等）。
