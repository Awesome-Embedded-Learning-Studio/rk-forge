# rk-forge — 方向交接文件

> 生成：2026-06-13　|　用途：进入 rk-forge 仓库开新会话时，先读这个文件接上下文
> 仓库现状：空（只有 `.gitkeep` 占位），greenfield，还没动工

---

## 一句话方向

**做 imx-forge 的 Rockchip 兄弟项目，专啃没人做的 RK3506，把最新主线 Linux 跑起来并诚实报告差距，先小后大地做。**

---

## 1. 这是什么

rk-forge = imx-forge（NXP i.MX6ULL）的同构兄弟，换到 Rockchip 平台。
- **imx-forge** 是用户自己的成熟项目（620 文件/132 提交），已验证打法：双轨内核（NXP BSP 6.12.3 + 主线 7.0rc）、Docker 即用、CI 多轨、0→1 教程、VitePress 文档站。
- **rk-forge** 镜像这套结构，但目标芯片换成 **RK3506**（用户手上有这块板），且采用 **mainline-first**（主线优先）。

为什么选 RK3506 而不是热门的 RK3588/RK3568：**好做的别人（Armbian/Buildroom/Collabora）都做了，做就是同质化。RK3506 是没人服务的真空，做深不做宽，避开红海。**

---

## 2. 关键事实（已研究核实，2026-06）

| 事实 | 状态 | 来源 |
|---|---|---|
| RK3506 pinctrl 主线支持 | **已合并进 Linux 6.19**（Linus Walleij pull，2025-12）。⚠ 6.19 已 EOL，**目标改为 7.0.x**（2026-06 最新稳定 7.0.12） | [LKML pin pull v6.19](https://lkml.org/lkml/2025/12/8/736) |
| RK3506 clock/reset 主线支持 | **已合并进 6.19**，`CONFIG_CLK_RK3506`（`drivers/clk/rockchip/clk-rk3506.c`） | [LKDBB](https://cateee.net/lkddb/web-lkddb/CLK_RK3506.html) |
| RK3506 U-Boot 主线 | **v2 12 补丁系列已合并进主线 U-Boot**（maintainer Kever Yang 确认，随 2026 版发布）。SoC 支持全在 upstream；**无上游板级 DT**——这正是 rk-forge 的贡献点 | [U-Boot patchwork v2 cover](https://patchwork.ozlabs.org/project/uboot/cover/20260310005326.606079-1-jonas@kwiboo.se/) |
| FOSDEM 2026 预测 | "RK3506 补丁开始涌现，预计 2026 年内能用主线 boot" | [slides](https://fosdem.org/2026/events/attachments/KLFW73-no-line-like-mainline-rockchip/slides/267550/no-line-l_vrjwxmj.pdf) · [Collabora 年度总结](https://www.collabora.com/news-and-blog/blog/2026/03/02/running-mainline-linux-u-boot-and-mesa-on-rockchip-a-year-in-review/) |
| QEMU 支持 | **主线 QEMU 无任何 RK SoC machine model**；只能用通用 `virt` 做架构近似，无法仿真 RK 外设 → QEMU 降为辅助，不当招牌 | (deep-research #1) |
| RK3506 架构 | **32-bit ARM Cortex-A7**（和 imx6ULL 同核，可迁移知识）；工具链 `arm-linux-gnueabihf`，`arch/arm/boot/dts/`，armhf rootfs | — |
| 启动离不开 rkbin | RK 启动需要 Rockchip 闭源 TPL/SPL（DDR 初始化），暂时绕不开 | — |

**最重要的结论（2026-06-13 已独立核实）**：RK3506 的 SoC 地基——pinctrl+clock（自 6.19）**和 U-Boot SoC 支持**（Jonas Karlman v2 已合并）——全在主线。所以**不是"从零拼补丁启动"，而是"在已合并的 SoC 支持上加板级 DT + 跑到用户空间 + 查清还差什么"**。rk-forge 的主要贡献 = **板级 `.dts`**（上游化目标）。比预想可行，难度低于 imx6ULL 那条路。

> **2026-06-13 新增决策**：① "取代 RK-SDK" = 只取代它的 `build.sh`（不碰全貌），sdk-diff 作证明器；② 先 bash、二期迁 Python CLI，bash leaves 留 seam（干净 stdin/stdout/exit、doctor 无 `/dev/tty`、config 走声明式 conf）；③ vendor SDK（如正点原子）作**参照系**拉进 `reference/vendor-sdk/`，构建目标仍是主线。详见仓库结构与 BLOBS.md。

---

## 3. 定位（反同质化）

**为什么不是 Armbian/Buildroom/Yocto-meta-rockchip/Collabora**：它们服务热门芯片、卖成品镜像。rk-forge 服务没人做的 RK3506，**不做镜像**，做三件事：

1. **打对补丁的库**（有序 `series`，修掉 imx-forge "只打最后一个补丁"的债）
2. **诚实的差距报告工具**（`sdk-diff`：逐子系统告诉你 BSP 有什么 / 主线有什么 / 差什么 / 能不能 boot）
3. **手把手 0→1 教程**

**比喻**：别人卖成品饭，rk-forge 卖菜谱 + 灶 + 带你做饭的书，专做没人做的那道菜。

**明确不做**：发行版、多 SoC（v1 只 RK3506）、内核驱动原创（只做整合者）、Buildroom/Yocto 替代、GUI/SaaS、blob 纯洁主义（先 blob，目标消除并文档化）。

**scope 护栏测试**：「这件事能让 RK3506 主线 boot 更可复现 / 更诚实追踪 / 更可教吗？不能就砍。」

---

## 4. imx-forge 范本（镜像它，别重造）

参考路径：`/home/charliechen/imx-forge`

**要镜像的**：
- `patches/{linux-imx, linux_mainline, uboot, uboot-imx}/` 按组件分 → rk 版 `patches/{linux-rk, linux_mainline, uboot}/`
- 补丁前缀 `[linux-imx]`/`[mainline]`/`[uboot]` → `[linux-rk]`/`[mainline]`/`[uboot]`
- `third_party/` 内核/U-Boot 源码子模块
- `release-all.sh` 一条命令出镜像（`--mainline`/`--bsp` track 开关）
- Docker 镜像 + WSL2 友好
- CI 多轨、VitePress 文档站、0→1 教程路径

**要修的债（rk-forge 从零做对的机会）**：
- `imx-forge/scripts/apply_patches.sh` 第 54-62 行：**只打最后一个补丁、坏了静默跳过**，没有真正的 series 顺序 → rk-forge 要做 quilt-style 有序 `series` + dry-run + 原子回滚 + 精确冲突报告
- `release-all.sh` 342 行单体 bash（rootfs 脚本 311-448 行）→ 不可读。rk-forge 要 readable：先 bash 模块化（每个 <100 行单一职责），未来按需引入 Python

---

## 5. 首迭代计划（8 周，先小后大）

**唯一硬里程碑：RK3506 用主线 Linux 启动到 UART 文字界面 + 一份诚实的 sdk-diff 报告。**

| 周 | 交付物 | 技术 |
|---|---|---|
| 1-2 | 仓库骨架 + `series` 文件（bash `apply-series.sh` + `git am`）+ `third_party/` 子模块 + `board.env` + `doctor` 脚本 + README | Bash + git submodule |
| 3-4 | U-Boot 构建：Jonas Karlman v3 系列 + rkbin 隔离子模块 + `BLOBS.md` + SD 烧录。**验证：U-Boot banner 出现在 UART** | Bash + binman |
| 5-6 | 内核构建：对 v6.19+（pinctrl+clk 已合并）+ 板卡 DT + defconfig。**验证：kernel 到 earlycon**。诚实 gap 报告 | Bash + merge_config.sh |
| 7-8 | `sdk-diff.sh`（主线 vs 我们 的差异 + 启动能力清单）+ 教程 Ch0-3 写成 repo 内 Markdown | Bash + git diff |

**退出标准**：板子 boot 主线到 UART console + 诚实 sdk-diff 报告存在。**失败就停**——在投资 Python CLI/VitePress 之前知道 thesis 对不对。

**有意排除（全部留第二迭代）**：Python CLI、VitePress 站点、lkml-registry 自动化、boot watch/analyze、composable profiles、Docker 镜像、CI 多轨、EN i18n、contributor 仪式、onboarding wizard、吉祥物。

---

## 6. 已定的关键决策

| 决策 | 结论 |
|---|---|
| 先 bash 后 Python | **先 bash**，但架构留 Python 口（bash leaves 走干净 stdin/stdout/exit 约定，未来 Python 无缝包裹） |
| mainline 先于 BSP | **是**，identity-first；BSP 是 Phase 4 安全网 |
| rkbin 态度 | **诚实非纯洁**：先用，`BLOBS.md` 文档化，sdk-diff 追踪，目标消除 |
| 编排语言 | bash 起步；CLI 框架等上 Python 时再选（Click/Typer） |
| 补丁应用 | `git am`（保 LKML 作者署名）+ `series` 有序 |
| 内核 config | 用内核原生 `merge_config.sh` 合并 fragment，不写自定义工具 |

---

## 7. 待用户最终确认的（进入仓库时可以再聊）

- 首迭代范围是否就这 8 周？（推荐：是）
- 板子具体型号 / 你手头 RK3506 是哪块开发板（影响板卡 DT）
- 是否接受"先 blob"的诚实策略

---

## 8. 参考资料

- **完整产品蓝图 + 批评**（含 15 个开放决策、12 章教程设计、VitePress 兄弟站点方案）：
  `/home/charliechen/orgorg/.orgorg/cache/ai_summaries/Awesome-Embedded-Learning-Studio_rk-forge.md`
  及原始工作流输出：`/tmp/claude-1000/-home-charliechen-orgorg/a6b2c8d7-5f18-47c3-a3e4-31cce5c0ef25/tasks/wry2q4w1e.output`
- **imx-forge 范本**：`/home/charliechen/imx-forge`
- **rk-forge 仓库**（空，待开工）：`/home/charliechen/orgorg/repos/rk-forge`
- **rk-forge roadmap 草稿**（用户之前写的 194 行规格）：`repos/rk-forge/roadmap.md`（基准板写的是 RK3588，已决定改为 RK3506）

---

*大方向四句话：做 RK 的 imx-forge 兄弟、专啃没人做的 RK3506、把最新 Linux 跑起来并诚实报告差距、先小后大地做。*
