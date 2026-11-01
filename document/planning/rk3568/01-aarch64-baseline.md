---
title: "卷一：AArch64 与 RK3568 系统基线"
---

# 卷一：AArch64 与 RK3568 系统基线

> RK3568 线 · 卷一 · 第 1–4 章 · [返回线总览](index.md)

### 第 1 章：RK3568 硬件和启动全景

一句话：建整张图的直觉——SoC 拓扑、启动链、BSP 与 mainline 的版本边界；冻结一份「已知良好」真板基线当全卷参照原点。

要点：

- 四核 A55（ARMv8.2-A）共享 L2；接口齐全 + 主线支持成熟 + 外设覆盖广，**学到的驱动框架知识迁移到任何 AArch64 SoC 都通用**
- 启动链与所有 AArch64 Rockchip 一致：`BootROM → SPL/TPL → ATF(BL31) → 可选 OP-TEE → U-Boot → Linux → init`；闭源/开源分界同样画在 rkbin 之后
- 启动存储 eMMC/SD，分区角色（boot/rootfs/vendor）与 RK3588 一致，镜像落固定偏移
- 主线对 RK3568 支持已成熟（pinctrl/clk/GMAC/USB/PCIe 皆在主线），mainline-first 比 RK3506B 好走；差距口径见 [sdk-diff-rk3568.md](../../sdk-diff-rk3568.md)
- 真板基线已建立（ATK 真机 boot 到 login、多外设板验），证据见 tutorial/rk3568 与 logs

实践：
- 完整启动日志逐行标注阶段；版本号映射回源码 pin
- 形成板卡硬件事实表（CPU/内存/存储/DT/内核版本）

### 第 2 章：AArch64 工具链、LP64 与 ELF64

一句话：64 位工具链与 ARM32 的关键差异——专治从 ARM32 过来的人。

要点：

- X0-X30 寄存器与 AAPCS64（X0-X7 传参、X29 帧指针/X30 返回地址）；**与 ARM32 不能共用汇编**
- LP64 陷阱：`long`/指针变宽导致结构体布局变化；定宽类型是解药，**永远别假设 long 是 32 位**
- ELF64/动态链接/sysroot：sysroot 不一致是经典坑（host 编过、target 跑不起来）
- ARM32/ARM64 产物绝对不能混：两套工具链、两个 sysroot、两份 rootfs；错误架构 `.ko`/程序的典型报错要认得

实践：
- 同一份 C 源码双架构编译，对比 ELF 头与 `sizeof`
- 反汇编一个调用对比 X0/R0；故意加载错误架构 `.ko` 分析 dmesg

### 第 3 章：EL0–EL3、ATF 与 PSCI

一句话：32 位平台没有的概念——异常级、ATF、PSCI 怎么管多核；对照 RK3506B 的 ARMv7 模型看清两代差异。

要点：

- EL0 用户态 / EL1 内核 / EL2 hypervisor / EL3 secure monitor；Linux 跑 EL1 的理由
- ATF 启动阶段 BL1/BL2/BL31/BL32/BL33；**BL31 是常驻 runtime firmware**，内核经 SMC 陷进去要 secure 服务
- PSCI（CPU_ON/OFF/SUSPEND）释放次级核；cpuidle/cpufreq 也走它
- OP-TEE 可选（S-EL1 跑 TA），按产品需求决定
- earlycon 出现之前的黑盒段：解压、页表、栈——只能靠 ATF/U-Boot 早期打印
- 硬边界：三块板的启动链与 blob 不共用

实践：
- 从 bootlog 识别各固件阶段、CPU 上线时序
- 分析一组 PSCI/CPU_ON 失败日志；与 RK3506B 的 ARMv7 启动模型做对照表

### 第 4 章：U-Boot、设备树与开发 rootfs

一句话：U-Boot 怎么加载内核、DT 怎么交接、Buildroot 出最小 rootfs——**NFS root 对驱动开发的价值是本章最该记住的一句**。

要点：

- eMMC/SD 启动与 bootcmd/bootargs；改环境变量必验回退路径
- FIT 与 extlinux 两种启动方案取舍；纯 Python 打包 FIT 见 tutorial/forge
- DT 交接：U-Boot 改 `/chosen` 传 bootargs，dtb 与内核版本绑定；`fdt` 命令调试
- Buildroot 最小开发系统：`BR2_EXTERNAL`、overlay、post-build、注入构建身份
- **NFS root 把驱动迭代从分钟级烧录降到秒级重启**——没有 NFS root 等于裸奔；开工核查门：各板主线 defconfig 是否含 `CONFIG_ROOT_NFS`（未确认前本章 NFS 实践标 partial）

实践：
- 建本地 rootfs 与可选 NFS root；U-Boot 下改一个安全参数验证
- 保留可恢复启动入口；验证内核/DTB/rootfs/模块版本一致

## 素材与取证

| 资产 | 用途 |
|---|---|
| [tutorial/rk3568/01_boot](../../tutorial/rk3568/01_boot.md) | 真机首启强锚点（主线 7.1 + binman 自产 loader） |
| [notes/36](../../notes/36-2026-07-22-rk3568-multiboard-and-mainline-build.md)、[40](../../notes/40-2026-07-26-rk3568-first-boot-and-next-push.md)、[41](../../notes/41-2026-07-26-rk3568-atk-mainline-dt-port-plan.md) | 取证链 |
| books 的 ARMv8 编程手册 | 第 2、3 章直接素材（`.claude/books/`，本地资料） |
| books 的 RK3568 用户手册 | 平台参考 |
| 正点原子 RK3568 开发笔记 06/07（vendor U-Boot 启动流源码级走读，本地资料 `.claude/books/`，不入站） | 第 4 章深读素材——厂商 fork 的启动流逐函数分析，主线对照用；注意其中 ATAGS 篇属 32 位遗留，对 AArch64 板适用性需甄别 |
| [RK3506B 线卷二](../rk3506b/02-boot-chain.md) | 32 位启动链对照引入 |
| [sdk-diff-rk3568.md](../../sdk-diff-rk3568.md) | BSP 与主线差距口径 |
