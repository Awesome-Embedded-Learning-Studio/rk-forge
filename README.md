# rk-forge

<div align="center">

**面向 Rockchip RK3506 的主线优先（mainline-first）开发工作空间**　
有序补丁库 × 诚实差距报告 × 取代 RK-SDK `build.sh` 的构建体验 × 0→1 教程

</div>

---

## 这是什么

rk-forge 服务**没人服务的 RK3506**：把最新主线 Linux 跑起来，并**诚实报告还差什么**。

它**不是**又一个 Armbian / Yocto / 厂商 BSP 镜像。它做三件事：

1. **有序补丁库**——quilt 风格 `series`，`git am` 落真实 commit、可 bisect、失败原子回滚（修掉"只打最后一个补丁"的老毛病）。
2. **诚实的差距报告**（[`document/sdk-diff.md`](document/sdk-diff.md)）——逐子系统告诉你：vendor BSP 有什么 / 主线有什么 / 差什么 / 还能不能 boot。
3. **0→1 教程**——从空机器到 RK3506 主线启动到 UART 的可复现路径。

**核心命题（已核实）**：RK3506 的 SoC 地基（pinctrl+clk 自 Linux 6.19 起、U-Boot SoC 支持经 Jonas Karlman v2 已合并）**全在主线**。所以对"主线启动"这件事，RK-SDK 整个坍缩成两样东西：① `rkbin`（DDR 初始化闭源 blob，绕不开）；② **一块板级设备树**（上游没有，rk-forge 来写）。rk-forge 的主要贡献就是这块 `.dts` + 一条诚实的路径。

> 别人卖成品饭；rk-forge 卖菜谱 + 灶 + 带你做饭的书，专做没人做的那道菜。

## 快速开始

```bash
./scripts/doctor.sh                       # 检查 host 依赖 + armhf 交叉工具链（缺啥会给 apt 命令）
source scripts/env-setup.sh               # 导出 ARCH=arm / CROSS_COMPILE=arm-linux-gnueabihf-
# (Week 3+) cd third_party/uboot && ../../scripts/apply-series.sh --component uboot
```

详见 [QUICK_START.md](QUICK_START.md) 与 [document/tutorial/boot/](document/tutorial/boot/)。

## 仓库结构

```
config/toolchain.conf        声明式工具链配置（未来 Python CLI 直接读）
board.env                    板卡元信息（占位 rk3506-evb）
board/                       aes/(构建工作区:fit/rootfs/buildroot-external) · rk3506-evb/(板 config)
patches/{linux,uboot}/series   有序补丁序列
third_party/                 src/(linux·uboot 源树) · buildroot · rkbin(submodule)
reference/                   vendor-sdk(参照/萃取池,非构建依赖)
scripts/
  lib/{log,toolchain,stage}.sh           共享库；stage.sh = 内容哈希增量跳过
  env-setup.sh · doctor.sh               环境（source 用 / 独立检查）
  apply-series.sh                   ★ 补丁库（修 imx 的头号债）
  build-uboot.sh · build-linux.sh · flash-sd.sh   （Week 3-8 逐步落地）
BLOBS.md                     rkbin 闭源 blob 的诚实清单 + 消除路径
document/tutorial/boot/      Ch0-3 教程（in-repo Markdown）
```

## 明确不做（v1）

发行版镜像、多 SoC（v1 只 RK3506）、内核驱动原创（只做整合者）、Docker/CI 多轨、GUI/SaaS、blob 纯洁主义（先用、文档化、目标消除）。Python CLI 留二期——bash leaves 已按"可被 Python 包裹"的约定写（干净 stdin/stdout/exit、`doctor.sh` 无 `/dev/tty` 交互）。

## 参考

- 范本（定位参考，非照搬）：imx-forge（NXP i.MX6ULL 同构兄弟项目）。
- 主线事实见 [PLAN.md](PLAN.md) 与 `document/`。

## 协议

MIT，详见 [LICENSE](LICENSE)。源自 GPL SDK 的补丁保留 GPL-2.0 并在补丁头标注。`rkbin` 为 Rockchip 专有固件，仅以 pinned 子模块引用，不拷入本仓库。
