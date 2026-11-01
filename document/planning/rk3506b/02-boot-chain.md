---
title: "卷二：掌控 Rockchip 启动链"
---

# 卷二：掌控 Rockchip 启动链

> RK3506B 线 · 卷二 · 第 3–4 章 · [返回线总览](index.md)

### 第 3 章：rkbin、DDR 与闭源边界

一句话：启动链的咽喉——回答「为什么 DDR 初始化绕不开那颗闭源 blob」，并诚实地把「做不到」写出来。

要点：

- DDR init 跑在整条链最前段：无 RAM、无 C 运行时，纯汇编裸 poke PHY + 私有 training；主线 sdram 框架有架子，RK3506 的 training 参数不开源
- rk-forge 自研 DDR init（方案 A）现状：DDR 能点亮（串口出 `DDR d27ac532c4`）但自研 SPL 紧接着崩成乱码；**板没引 JTAG，崩在 SPL 里连打印都抓不到**
- rkbin 三段（TPL/SPL/可选 OP-TEE）**配对使用不能拆换**：FIT 节点结构、hash、偏移互相约束；vendor 2017 fork 的 FIT 与主线 binman 不对齐（`Unsupported hash algorithm` 的真因）
- 别混用不同来源的 blob：DDR 容量/PHY 参数 ↔ SPL 的 RAM 布局、TEE reserved-memory ↔ 内核 DT 的 hole
- **主线优先 ≠ 纯主线 boot**：前者是现状（借 blob 但诚实记录消除路径），后者是目标（卡在 rkbin）；维护闭源清单见 blobs.md

实践：
- `binman`/`dumpimage` 拆 loader，列每段来源与版本，说明每个不可替代 blob 做了什么
- 分析一组 SPL/TEE 不匹配的失败日志
- 对照厂商与主线启动链，差异写进 [sdk-diff.md](../../sdk-diff.md)

### 第 4 章：U-Boot、FIT 与启动策略

一句话：rkbin 之后全是主线开源代码——U-Boot 怎么加载内核、FIT 怎么打包、启动链怎么设计成可恢复的。

要点：

- U-Boot 设备模型（DM）与内核 device model 同构：uclass/driver/device，DT 触发 probe；RK3506 SoC 级 DM 驱动已在主线
- `bootcmd`/`bootargs` 分工；环境变量存哪、**改完必验回退路径**（一次写错就变砖）
- NAND 与 SD 两条路读取方式不同：NAND 按硬约定偏移，SD 可走 GPT、适合置备/救援
- FIT 多组件 + hash 校验；vendor FIT 节点结构与主线不对齐的坑延续自第 3 章；rk-forge 用纯 Python [fit-pack.py](../../../src/forge/tools/fit_pack.py) 字节级复刻 vendor 认的布局
- 启动链预留三种互不破坏的用途：**正常 / 置备 / 救援**；三条规矩：置备不写救援分区、救援不覆盖正常分区、环境变量可回退

实践：
- 手动 `fatload`/`mmc read`/`ubi read` 读 FIT 并 `bootm`，对照 `printenv` 走一遍 bootcmd
- 改一个可观察内核参数并验证生效；`dumpimage -l` 查 FIT 组成与 hash
- 设计「正常启动失败 → 自动回退救援」环境变量脚本并测幂等性

阶段产出：启动失败决策树、可解释且可恢复的启动方案（三入口）。

## 素材与取证

| 资产 | 用途 |
|---|---|
| [pitfalls/01（rkbin SPL 的三条隐性约定）](../../pitfalls/01-rkbin-spl-contracts.md) | 第 3 章正文骨架 |
| [blobs.md](../../blobs.md) | 闭源清单单一真相源，第 3 章的现成正文 |
| [notes/01](../../notes/01-2026-06-14-vendor-uboot-build-flow.md)、[03](../../notes/03-2026-06-14-maskrom-brick-recovery.md)、[13](../../notes/13-2026-06-17-p1-rkbin-public-loader-conquest.md) | 取证链 |
| [tutorial/boot/01–03](../../tutorial/boot/) | 第 3、4 章初稿底子 |
| [notes/20（mkimage saga）](../../notes/20-2026-06-19-mkimage-saga-handoff.md) | FIT 打包教训 |
| [src/forge/tools/fit_pack.py](../../../src/forge/tools/fit_pack.py) 与 [rkfw_pack.py](../../../src/forge/tools/rkfw_pack.py) | 打包器教学实物 |
| [sdk-diff.md](../../sdk-diff.md) | 厂商 vs 主线启动链对照 |
