# rk-forge 交接提示词（交给任何 AI/新会话用）

把下面整段作为新对话的开场 prompt 交给接手者即可。仓库内此文件为权威版。

---

我在 `~/rk-forge` 继续 RK3588 QEMU 仿真研究线（战役七 panthor）的工作。开始前先读记忆（`~/.claude/projects/-home-charliechen-rk-forge/memory/` 下 MEMORY.md 及各条目）和 `document/notes/101-113`，这里只给当前落点：

## 总成果（M2n 全线，分支 feat/sim_rk3568，绝不 push）

**显示接管基建落成**（notes 109-111）：帧节拍重绘（VOP 60fps 重铺+console 缓存失效）+屏级快照+AS 捕获自证门+五点标记取证（坐标链路零误差定谳）。现行形态 `FSQUAD_REPAINT=1 GPUDBG=1 FSQUAD=1 FSQUAD_REALIMG=1 FSQUAD_BGFULLRES=1 GDM=1 + resboot`。

**屏幕内容现状（note 112-113 诚实定量，verify_screen.py 判决）**：壁纸背景色系+低频光芒在，浣熊未成形——final3（线性快照时代）bg_p90=22.4/st_p50=62（FAIL）；til2（tiled 快照）bg_p90=92 更糟。此前"背景像素级吻合/脸局部成形"宣称=角落采样幸存者偏差+MCP 幻觉，均已翻案。**staging 脸区（偏移 12-18MB）悬案**：与任何壁纸变体、任何读法（线性/tiled/位移±24）都不匹配——内容本质未知。

里程碑链（notes 101-113）：采样 FS 侦察 → 受控矩阵 → 异步分片 → 双病分流 → 界内全证 → 壁纸作业门 → 显示点亮 → 内容工程 → 毒根修（缝合写）→ 屏幕垃圾根修 → 细节五连修 → 显示接管基建+坐标定谳 → staging 读路径实验 → **校验武器化（verify_screen.py）** → 余=脸区悬案。

## 三层残局（notes 108-113）

1. ~~迟发毒~~ **已根修**（note 108 缝合写；note 110 读侧缝合补齐）
2. ~~屏幕竖条纹垃圾~~ **已根修**（note 109 条带门+页表自画像门）
3. ~~坐标错位~~ **已定谳零误差**（note 111 五点标记精确落位）
4. **浣熊脸区（open，最高优先）**：staging 脸区 6MB 内容本质未知（全变体/全读法不匹配）。**刀口（note 112 §6）**：QEMU 里加 STGDUMPFACE 把脸区原始字节 dump 出来 → `verify_screen.py --classify` 分类（image/pagetable/text/mixed？）→ 按分类结果定读法；辅以 STGSTRIPS 1:1 条带（已埋点，上轮 boot 被杀未取到）+ gems-gpuvas 对账
5. **UI 层合成/字形位姿（FAU）/vt1-nudge**：照旧 open

**内容验收仪器（note 113，权威）**：`sim/verify_screen.py` 确定性数值判决——
- 全屏对照：`python3 sim/verify_screen.py 屏.ppm --ref out/rk3588-topeet/ubuntu-rootfs.work/usr/share/backgrounds/cnusr25-Simple_Raccoon_Dark.png` → 背景域 p90≤20 且结构域 p50≤40=PASS（自动估 greeter 调光恒偏 ~[-11,-9,-10]）
- 1:1 条带：`--strips --strip-rows 100,500,990,1500,2000`（STGSTRIPS dump 后逐行定谳；16px 位移注入已验证判别力）
- 原始页分类：`--classify`（熵/零/排版字符/LPAE 指针特征→image/pagetable/text/mixed）
- **MCP 读图永不作判据**（两次把差 94 读成"完美浣熊"）——只可作 diff-heat.ppm 的旁白；人眼复核也只看热图
- **验收协议（用户令，note 113 后生效）**：数值 PASS ≠ 达成——每轮改动用 verify_screen.py 判决；只有当判决 PASS 后，**必须邀请用户现场把关**（拷 PNG 到 Windows 桌面+用户亲眼看屏/图确认）才可宣称"可见/达成"。note 76 证据门的两段式：机器判据→人眼终审
- QEMU 取证 dump 必须全分辨率（稀疏降采样会制造碎片伪影）；extract 快照寻址开关：默认线性（量化较优），FSQUAD_STGTILED=1 切瓦片

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

**绝不 push**；commit 禁 Co-Authored-By；一课题一编号笔记（下一号 114）；诚实边界（note 76 证据门——未验证的"可见"不宣称）；/tmp 只放可丢的临时物。
