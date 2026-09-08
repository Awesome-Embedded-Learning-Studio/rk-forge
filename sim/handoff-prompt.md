# rk-forge 交接提示词（新会话用）

把下面整段作为新对话的开场 prompt 交给 Claude 即可。（此文件在仓库
sim/handoff-prompt.md；/tmp 的副本可能被清洗，以仓库版为准。）

---

我在 `~/rk-forge` 继续 RK3588 QEMU 仿真研究线（战役七 panthor）的工作。开始前先读记忆（MEMORY.md 索引已有全部状态）和 `document/notes/101-105`，这里只给当前落点：

## 已完成（M2n 全线，均未 push，分支 feat/sim_rk3568）

- **受控矩阵 11/11 PASS**（note 102/104）：采样 draw 真执行
  - bf=13="AFBC Tiled"（非 AFRC，旧标签翻案；sim TEXTURE_FEATURES_0=0→mesa 根本不选 AFRC）
  - `rk3588_afbc_hdr()` 线性/tiled 双寻址贯穿 raster/blit 写/clear/纹理读/blit 读；**紧式 body_base**（4K 对齐头区）
  - 4 种顶点形态解析（16B 交错/8B 分离×2/32B 步长=pos@0+uv@16 像素坐标）→ mutter draw 全配对零弃权
  - clear 合并（mesa 把 glClear 并进 draw job FBD，RT bit31）→staging 预铺 clear word
  - TEX_FETCH(0x125) 像素 uv 模式；纹理读四形态（U-tiled/线性/AFBC solid/body）
- **异步分片 raster**（BH 128 行/片）+ completion 保序挂起（fence 对齐）+ `va_pa_write()` 全 AS 一致性写翻译 + BH 每片 base_va 映射重验
- **合成链结构打通**：raster-LRU（8 槽）blit 回退、壁纸链全程测绘到 VOP
- **双病分流**（note 105）：病一号=ubuntu-dock gjs 断言 SIGABRT（已在镜像禁用→NOWRITE 轮 shell 全活）；病二号=崩溃考古（四论证伪：NMI/body 越界/UAF/AS 歧义）
- **界内全证**（note 105 §7）：gems 真值（图集 BO=1,073,152B、壁纸 BO=45MB 含 11 级 mip）+ 2GB 转储对账=全部写界内、崩溃轮唯一写手 rjob 全审计界内——**越界论证伪**；PID1 死因重开（NULL+0x40 逻辑解引用 vs 早轮像素伪指针=多机制并存）

## 现行操作形态（已验证可用）

| 用途 | 命令 |
|---|---|
| 研究机冷启 | `GPUDBG=1 setsid nohup python3 sim/resboot.py 7200 > sim/logs/resboot.out 2>&1 &`（串口 4446/监视 4449；**日志在 sim/logs/ 免 /tmp 清洗**） |
| 采样验收（净机） | 加 `FSQUAD=1`；GDM 加 `GDM=1`；安全研究=GDM+`FSQUAD_NOWRITE=1` |
| 采样矩阵 | `sim/sendfile.py sim/glestexture.py /tmp/gtx.py` 后 `python3 /tmp/gtx.py`（TEXSIZE/QUAD/TEXGRAD 参数化） |
| 串口会话 | `CMD_TIMEOUT=60 python3 sim/serx.py 4446 "命令"`（rk-forge 自动登录，已落库） |
| 文件进 guest | `CMD_TIMEOUT=90 python3 sim/sendfile.py <本地> <远端>`（分块 base64+md5，已落库） |
| BO 真值测量 | guest：`sudo mount -t debugfs none /sys/kernel/debug; sudo cat /sys/kernel/debug/dri/1/gems`（per-BO 大小+modifier）；gpuvas 表=VA↔BO 映射 |
| 崩溃转储 | monitor（4449）：`\x03` 清行后 `pmemsave 0 0x80000000 "<路径>"`（~4 分钟）；离线搜内核日志环 |
| QEMU 重编 | `ninja -C third_party/qemu/build qemu-system-aarch64`（重启机器才生效） |
| QEMU 改动落库 | qemu 树 `git diff > sim/qemu-sim-machines.patch` → 主仓 commit |
| **重启机器** | kill 与启动**拆两次工具调用**（pkill -f 自杀坑）；判活 `ss -tln \| grep 4446` |
| WSL 重启恢复 | /tmp 全丢（会大清洗）；mesa 重克隆见 note 97 §3 + sparse-checkout add gallium 驱动 |

## 下一步（M2n-visible 收官）

1. **PID1 NULL 机制定谳**：journalctl 看 systemd 死前最后动作、NULL 提供者（panthor uevent/设备管理路径？）；对照早轮像素伪指针形态=多机制还是两病。崩溃日志现在在 sim/logs/（持久）
2. 图集内容偏 0x2000（真 body 起点 0x6000 非我的 0x4000）——gems+转储法可精确定真实头区公式
3. 根因闭环→writes-on 轮 shell 活→screendump 非黑=M2n-visible 收官

## 关键坑（速查）

- **pkill/pgrep -f 自杀**：kill/启动拆两次、`res[b]oot.py` 括号技巧、ss 判活
- **/tmp 大清洗**（会杀 qemu 进程+删文件）：工具/日志/提示词只用 sim/ 落库版
- resboot.py 僵尸堆积；串口短行蒸发（用 ZZB/ZZE 标记夹取）；monitor 需 \x03 清行
- mutter draw 的 r57/58（DCD）是编码值非指针；扫描窗口算术机器算
- 崩溃现场取证：`grep -B2 -A6 'Unable to handle' sim/logs/scmi-serial.log` + `tail sim/logs/scmi-dbg.log`

## 其余欠账（别忘）

真机 fixture 补采（CS features 占位 0x000708bf）、PANTHORIOCTL 打点待撤（journal 里还在刷）、restore 多核 loadvm（note 85）、真机 BT/audio/RTC/NPU/VPU 板验、LINEAR 采样/blend/旋转（受控边界外）

## 纪律

**绝不 push**；commit 禁 Co-Authored-By；一课题一编号笔记（下一号 106）；诚实边界（note 76 证据门——未验证的"可见"不宣称）。
