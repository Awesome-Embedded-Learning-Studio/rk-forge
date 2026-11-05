---
title: "卷七：工程交付与真板取证"
---

# 卷七：工程交付与真板取证

> RK3506B 线 · 卷七 · 第 16–17 章 · [返回线总览](index.md)

### 第 16 章：可复现构建与回归

一句话：「我机器上能编出来」不算交付——`forge` 把构建收成一条命令，让任何人 clone 后得到一样的镜像。

要点：

- 四阶段 `setup → build → pack → assemble`；一条 `forge all` 出 `out/aes/update.img`，取代 SDK `build.sh` 式全量重编
- **所有输入必须 pin**（源码 commit / 工具链 / rkbin release / series 版本），声明集中在 [forge.yaml](../../../forge.yaml) 与各板 board.yaml `sources:`；不 pin 三个月后必崩
- 增量构建靠内容哈希不是时间戳；三条纪律：算法稳定、输入集合完整、缓存可强制 invalidate——哈希算漏一个文件比全量重编危险
- 干净构建 vs 日常增量的使用时机：交付/发版/标 verified 必须干净构建一次
- 一项能力「已验证」= host / 构建 / 真板**三道检查都过**，互相不能替代
- 纯 Python 打包链替代 vendor 工具：[rkfw_pack.py](../../../src/forge/tools/rkfw_pack.py) 替 afptool/rkImageMaker、[fit_pack.py](../../../src/forge/tools/fit_pack.py) 字节级复刻 vendor 认的 FIT 布局——正文已在 [forge 卷](../../tutorial/forge/)兑现
- 去 vendor-sdk 的立身逻辑：仓库不携带厂商 SDK，主线源码 + 最小 rkbin blob 全部 pin 进 forge——正文同在 forge 卷

实践：
- 干净开发机全流程 clone → setup → build → assemble，不依赖本地未提交改动
- 两次构建（不同时间/host）产物哈希对比
- 故意改一个补丁观察增量只重做受影响阶段，再 `--clean` 对照
- 演练三道检查并记录每道输出

### 第 17 章：怎样证明一项能力已经完成

一句话：跑通一次不叫完成——把「我跑通了」变成「可由第二人复核的证据」，这是 partial 升 verified 的硬标准。

要点：

- 证据规范命名与存放（bootlog / 产物 / 测试记录各一套命名法），git 管理长期保留；本地没入库的「跑通了」不算证据
- 完整 bootlog 从上电第一行截到 `login:`，不合成不断段；**版本号主动与 pin 对账**，对不上证据效力归零
- 每个产物算 sha256，与源码 commit、series 版本一起记
- 测试记录四件事：前提、步骤、期望、实际——缺一不可复核
- 状态诚实铁律：跑通一次 ≠ verified；厂商 SDK 跑通 ≠ rk-forge verified；host 编过 ≠ 真板通过

最终产出：
- 可复现构建说明（forge + 三道检查清单）
- 可审查的真板日志组（logs 的 boot-sdl 系列）
- 已知限制与回归清单（blocked 项、卡点、消除路径）

## 素材与取证

| 资产 | 用途 |
|---|---|
| [sdk-diff.md](../../sdk-diff.md) | 残留度量表，「主线还差什么」的口径 |
| [notes/18（板级验证 playbook）](../../notes/18-2026-06-18-board-verification-playbook.md) | 三道检查的原始流程 |
| [notes/32](../../notes/32-2026-06-21-sd-card-image-sd1.md)、[33](../../notes/33-2026-06-21-sd-card-autoboot-sd2.md) | SD 卡镜像两篇 |
| [logs/](../../logs/) 的编号归档制度 | 第 17 章证据制度教材本身 |
| [src/forge/](../../../src/forge/)（`doctor`、`pack/assemble`）与 [forge.yaml](../../../forge.yaml) | 可复现构建的教学实物 |
| [tutorial/forge/](../../tutorial/forge/) | 第 16 章正文已兑现（forge/00：DAG + content-hash、八个子命令、去 vendor-sdk） |

## 缺口（待写）

- 第 16 章：pin 纪律专讲（forge.yaml / board.yaml `sources:`）、增量构建三纪律的算法细节、干净构建 vs 增量的使用时机、双构建哈希对比、三道检查演练未写。素材：[forge/00](../../tutorial/forge/00_forge.md)、[forge.yaml](../../../forge.yaml)、[notes/18（板级验证 playbook）](../../notes/18-2026-06-18-board-verification-playbook.md)。
- 第 17 章：整章待写（或裁决并入第 16 章收尾与站点「证据库」层）。素材散在：各教程章「成功长这样」小节、[logs/](../../logs/) 编号归档制度、[三板教学路线](../index.md)的四档口径。
