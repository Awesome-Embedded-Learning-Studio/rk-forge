# RK-Forge 路线图

> 最后更新：2026-03  
> 原则：**每个 Phase 结束时，仓库必须处于可用状态**，不留永远"施工中"的半成品。

---

## 总体阶段规划

```
Phase 1 ──► Phase 2 ──► Phase 3（长期愿景）
BSP 5.10     BSP 6.1      任意 upstream mainline
单板验证     多板扩展      快速 patch 出可烧录镜像
工具链就绪   CI 完整       发行版框架成熟
```

## 🗂️ 仓库结构

```
rk-forge/
├── boards/                    # 板卡配方（每块板一个目录）
│   └── rk3588-evb/
│       ├── board.yaml         # 板卡元信息（SoC、内存、Flash 类型等）
│       ├── kernel.config      # defconfig 覆盖片段
│       └── patches/           # 板卡专属补丁（优先级高于通用补丁）
│
├── patches/                   # 通用补丁库（跨板复用）
│   ├── kernel/
│   │   ├── 5.10/              # 当前主力版本
│   │   │   ├── series         # quilt-style 应用序列
│   │   │   └── 0001-xxx.patch
│   │   └── 6.1/               # Phase 2 目标版本
│   └── uboot/
│
├── drivers/                   # 自研驱动参考实现
│   └── <driver-name>/
│       ├── METADATA.yaml      # 兼容性、依赖、License 声明
│       ├── Kconfig
│       └── *.c / *.h
│
├── rootfs/                    # Rootfs 部署配方
│   ├── profiles/              # minimal / standard / full 三档
│   │   ├── minimal.yaml
│   │   ├── standard.yaml
│   │   └── full.yaml
│   ├── base/                  # 所有 profile 共享的基础包声明
│   └── overlays/              # 板卡或发行版专属覆盖层
│
├── scripts/                   # 脚本库（核心入口）
│   ├── apply-patches.sh       # 按 series 文件应用补丁
│   ├── build-kernel.sh        # 交叉编译内核
│   ├── build-rootfs.sh        # 构建/打包 ext4 rootfs 镜像
│   ├── flash.sh               # 调用 rkdeveloptool 烧录
│   ├── sdk-diff.py            # 私有 SDK vs upstream 差异分析
│   └── env-setup.sh           # 初始化交叉编译环境
│
├── sim/                       # PC 端模拟环境（QEMU + Docker）
│   ├── run-qemu.sh            # 启动 ARM64 QEMU 冠烟测试
│   └── docker/                # 轻量级驱动单元测试容器
│
├── examples/                  # Hello World 级应用示例
│   ├── rga-hello/
│   ├── npu-hello/
│   └── qt-hello/
│
├── docs/                      # 知识配方文档
│   ├── quickstart.md
│   ├── patch-workflow.md      # 补丁工作流完整说明
│   ├── sdk-diff-guide.md      # 如何使用 sdk-diff.py
│   ├── rootfs-deploy.md       # 任意发行版 Rootfs 部署指南
│   └── roadmap.md
│
├── meta/
│   └── stats.json             # CI Badge 统计数据
│
└── .github/
    ├── workflows/
    │   ├── patch-validate.yml # 补丁可应用性 + 内核编译
    │   └── rootfs-build.yml   # Rootfs 镜像构建
    └── hooks/
        └── pre-commit         # 本地提交前检查脚本
```


---

## ✅ Phase 1 —— 地基（当前阶段）

**目标：** 以一块 RK3588 开发板为基准，把整个工作流跑通，每个模块都有最小可用实现。

**内核版本：** Rockchip BSP kernel 5.10  
**Rootfs：** Buildroot（极简验证）+ Debian（主力部署）

### 1.1 脚本库基础建设

- [ ] `env-setup.sh` —— 交叉编译工具链一键初始化（aarch64-linux-gnu）
- [ ] `apply-patches.sh` —— 按 `series` 文件顺序应用补丁，支持 dry-run 模式
- [ ] `build-kernel.sh` —— 交叉编译内核，输出 `Image` + `dtb`
- [ ] `build-rootfs.sh` —— 构建 ext4 rootfs 镜像（Buildroot & Debian 两路）
- [ ] `flash.sh` —— 封装 `rkdeveloptool`，支持分区烧录

### 1.2 补丁体系

- [ ] 建立 `patches/kernel/5.10/series` 基础结构
- [ ] 整理至少 3 条真实 RK3588 必要补丁（作为格式示例）
- [ ] 编写 `docs/patch-workflow.md`（补丁命名规范、提交流程）
- [ ] 配置 `.github/hooks/pre-commit`（本地 lint + patch 格式检查）

### 1.3 SDK 差异对比工具（`sdk-diff.py`）

- [ ] 接受用户传入私有 SDK 路径
- [ ] 自动识别 kernel / U-Boot 版本，clone 对应 upstream tag
- [ ] 输出差异摘要报告（修改文件列表 + 新增文件 + 删除文件）
- [ ] 支持过滤：只看 `drivers/` 或只看 `arch/arm64/` 等子目录

### 1.4 Rootfs 配方框架

- [ ] 定义 `profiles/minimal.yaml` 和 `profiles/standard.yaml` 格式规范
- [ ] 实现 `base/` 基础包声明（与发行版无关的抽象层）
- [ ] 实现第一个 `overlays/rk3588-evb/`
- [ ] 编写 `docs/rootfs-deploy.md`

### 1.5 第一个驱动参考实现

- [ ] 选取 SPI 或 I2C 外设驱动作为模板驱动
- [ ] 附带完整 `METADATA.yaml`（见 `docs/metadata-schema.md`）
- [ ] 附带注释充分的代码，面向初学者可读

### 1.6 PC 端模拟环境（最小可用）

- [ ] `sim/run-qemu.sh` —— 启动 QEMU ARM64，加载编译好的 kernel + rootfs
- [ ] 记录在 x86 Ubuntu 上的完整环境搭建步骤到 `docs/qemu-sim.md`

### 1.7 CI（GitHub Actions）

- [ ] `patch-validate.yml`：PR 时自动跑 patch apply + 内核交叉编译
- [ ] `rootfs-build.yml`：验证 Buildroot rootfs 可构建
- [ ] lint 检查：shell 脚本 `shellcheck`，Python `ruff`

### 1.8 板卡配方

- [ ] 完成第一块 RK3588 板卡的 `boards/<board-name>/board.yaml`
- [ ] 补全 `boards/<board-name>/kernel.config` defconfig 片段

---

## 📋 Phase 2 —— 扩展（BSP 6.1 + 多板）

> 预计在 Phase 1 全部完成且运行稳定后启动。

- [ ] 支持 BSP kernel 6.1，`patches/kernel/6.1/` 补丁库建立
- [ ] 扩展至 RK3568 开发板支持
- [ ] Rootfs 支持扩展：Alpine、OpenWrt
- [ ] QEMU boot 冠烟测试接入 CI 流水线（非阻塞，PR 时触发）
- [ ] `sdk-diff.py` 扩展支持 Buildroot 组件对比
- [ ] 驱动参考实现扩展：Camera/ISP、NPU/RGA Hello World 示例

---

## 🔭 Phase 3 —— 长期愿景（upstream mainline）

> 这是最终目标，不设固定时间表。

**核心命题：** 给定任意 upstream mainline kernel 版本 + 目标板卡，能够快速 patch 出可烧录镜像。

实现路径设想：

- 维护一份「最小必要补丁集」per SoC（与内核版本解耦，按需适配）
- `sdk-diff.py` 升级为能自动推荐哪些 BSP 补丁仍有必要 backport
- Rootfs 部署框架支持任意发行版一键部署（标准化 ext4 镜像接口）
- 完整的 QEMU 端到端验证流水线（patch → build → boot → 基础功能测试）

---

## 🚫 明确不做的事

以下内容**不在 RK-Forge 范围内**，避免范围蔓延：

- 发布预构建二进制镜像（`.img` 下载）
- 支持非 Rockchip 平台
- 替代厂商 SDK 的完整 BSP 实现
- GUI 工具或 Web 界面

---

## 📌 贡献优先级引导

如果你想贡献但不知道从哪里入手，优先级参考：

1. **补丁**：格式正确、附带 `series` 条目、CI 通过
2. **驱动**：附带完整 `METADATA.yaml`、有实际硬件验证记录
3. **板卡配方**：完整的 `board.yaml` + `kernel.config` 片段
4. **脚本**：新增脚本需通过 `shellcheck`，附带使用文档
5. **文档**：欢迎任何改善可读性的 PR
