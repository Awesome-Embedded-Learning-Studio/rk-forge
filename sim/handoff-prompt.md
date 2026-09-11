# rk-forge 交接提示词（交给任何 AI/新会话用）

把下面整段作为新对话的开场 prompt 交给接手者即可。仓库内此文件为权威版。

---

我在 `~/rk-forge` 继续 RK3588 QEMU 仿真研究线（战役七 panthor）的工作。开始前先读记忆（`~/.claude/projects/-home-charliechen-rk-forge/memory/` 下 MEMORY.md 及各条目）和 `document/notes/101-107`，这里只给当前落点：

## 总成果（M2n 全线，分支 feat/sim_rk3568，绝不 push）

**GPU 仿真桌面已可见**：screendump 1024×600 最高 100% 非黑；真壁纸色全屏视图 98.7%/42 种真实色（Ubuntu 壁纸图案的块状采样）。证据 PPM 在 `sim/logs/`（m2n-visible-desktop=纯色蓝 98.67% / m2n-real-desktop=真色条带 6% / m2n-fullscreen-desktop=100% 全屏 / m2n-realimage-fullview=42 色真图）。

里程碑链（notes 101-107，七天）：采样 FS 侦察 → 受控矩阵 11/11 → 异步分片 → 双病分流 → 界内全证 → 壁纸作业门 → 显示点亮 → bg-fallback/solid/realimg/背景槽/scanout 镜像/全分辨率 fullres。

## 三层残局（毒已根修，note 108；屏幕垃圾已根修，note 109）

1. ~~迟发毒~~ **已根修**：VA 映射散射+线性写=毒（全部写路径已逐页缝合）；shell 全会话存活、340s+ 稳
2. ~~屏幕竖条纹垃圾~~ **已根修（note 109）**：bg-fallback 双维门（≥1024×256）杀条带误全屏 + tex_read_px 垃圾头门（64 对齐/<64MB）杀页表自画像。现状：**253 独立色真壁纸结构化上屏**（65%/55% 翻页波动）。残余：sb 级周期空洞、覆盖率翻页波动
3. **显示接管确定性**：好轮 VOPSCAN=9-14+内容可见，差轮=4+全黑；c1 会话激活（console=hvc0 下 VT1 不前台）→vt1-nudge.service 设计好但装机屡被死机打断。刀口：boot 极早期（<60s）串口注入服务，或改 bootargs
4. **字形位姿**：VS 语义 draw 的 actor 屏幕位置需要 FAU 仿射——r8=0xfffd4240 是页选复合编码（M2l 旧坑），需要 FAU RAM 模型（panthor fau 区）

**内容验收仪器（note 109）**：MCP 读图（zai analyze_image，本地路径直传）= 标准——像素直方图只证颜色不证布局（本轮翻案教训）；run-length+周期检测区分图像 vs 元数据（同低字节变高字节 run=指针）。

## 核心机制地图（全在 hw/arm/rk3588-lite.c，经 qemu patch 落库）

- **CS 解释器**：wrapper+用户段、192 寄存器文件、RUN_IDVS/FRAGMENT、BRANCH/JUMP/CALL、deferred SYNC_ADD（fence 对齐 raster-done）
- **采样执行器**（FSQUAD=1 门控）：RUN_IDVS 提取（SPD→Binary→TEX 族扫描；SRT t4→Texture→Surfaces→Plane；t2 顶点四形态解析）→BH 异步分片光栅化（128 行/片）→按 RT bf 提交（1=U-tile/2=线性/12=AFBC 头/13=AFBC Tiled 头，`rk3588_afbc_hdr()`）
- **大图策略**：>4M px 或 REALIMG≥256² = solid/realimg 模式（逐 sb 头写零 body）；背景槽（≥1024×768 常驻）；空 layer 回退（8 点探针全黑→改采背景）；scanout 镜像（fallback job 把 BG 缩放全分辨率写进全部近期扫描缓冲 scan_pbs[4]）
- **安全门**：VA 域（0x7fff*）+尺寸≤4096+span 界内+全 AS 一致性写翻译+BH 每片映射重验

## 现行操作形态

| 用途 | 命令 |
|---|---|
| 稳定桌面演示 | `GPUDBG=1 FSQUAD=1 FSQUAD_SOLIDBLUE=1 GDM=1 setsid nohup python3 sim/resboot.py 7200 > sim/logs/resboot.out 2>&1 &`（~5min 后 monitor screendump → 98.67% 壁纸蓝） |
| 真图冲刺 | 同上把 SOLIDBLUE 换 `FSQUAD_REALIMG=1`（boot 间方差；好轮=42 色真图） |
| 受控回归（净机） | `FSQUAD=1` 无 GDM；`sim/sendfile.py sim/glestexture.py /tmp/gtx.py` 后 `python3 /tmp/gtx.py`（11/11 基线） |
| 串口会话 | `CMD_TIMEOUT=60 python3 sim/serx.py 4446 "命令"`（rk-forge/rk-forge 自动登录） |
| 文件进 guest | `CMD_TIMEOUT=90 python3 sim/sendfile.py <本地> <远端>` |
| BO 真值 | guest: `sudo mount -t debugfs none /sys/kernel/debug; sudo cat /sys/kernel/debug/dri/1/gems`（per-BO 大小+modifier）；gpuvas=VA↔BO 映射 |
| 崩溃取证 | `grep -B2 -A6 'Unable to handle' sim/logs/scmi-serial.log`；monitor 4449 `\x03` 清行后 `pmemsave 0 0x80000000 "<路径>"`（~4min）→离线搜内核日志环（`MESSAGE=` 正则可读 journald 明文，需镜像内 journald Compress=no 已设） |
| QEMU 重编/落库 | `ninja -C third_party/qemu/build qemu-system-aarch64`；qemu 树 `git diff > sim/qemu-sim-machines.patch` →主仓 commit |
| 重启机器 | kill 与启动**拆两次工具调用**（pkill -f 模式串会匹配自己 wrapper=exit 144 自杀）；判活 `ss -tln | grep 4446` |

## 关键坑（血泪速查）

- pkill/pgrep -f 自杀；/tmp 大清洗（杀 qemu+删文件——工具/日志/提示词只用 sim/ 落库版）；resboot 僵尸堆积
- 串口短行蒸发（ZZB/ZZE 标记夹取）；monitor 需 \x03 清行+引号路径；两串口任务互踩
- bf=13="AFBC Tiled" 非 AFRC（历史误标已翻案）；mutter r57/58 是编码值非指针
- 扫描窗口算术机器算（十六进制位数坑 ×2）；guest /tmp 重启即清
- 环境开关族：GPUDBG（主）/FSQUAD/FSQUAD_NOWRITE/FSQUAD_SYNC/FSQUAD_SOLIDBLUE/FSQUAD_REALIMG/GPUFSX/GPUWRITELOG/LOGLEVEL

## 其余欠账

真机 fixture 补采（CS features 占位 0x000708bf）、PANTHORIOCTL 打点待撤、restore 多核 loadvm（note 85）、真机 BT/audio/RTC/NPU/VPU 板验、LINEAR 采样/blend/旋转（受控边界外）、ubuntu-dock 已在镜像禁用+core 陷阱+journald 持久化（均在 rootfs 非 git）。

## 纪律

**绝不 push**；commit 禁 Co-Authored-By；一课题一编号笔记（下一号 108）；诚实边界（note 76 证据门——未验证的"可见"不宣称）；/tmp 只放可丢的临时物。
