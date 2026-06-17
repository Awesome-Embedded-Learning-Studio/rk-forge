# pitfalls/ — 踩坑日记(多篇)

> P0 产出。note12 列的 12 条坑,按**故障域**分篇(非一坑一文件),每篇内部按时间线
> 还原该域的坑 + 走过的弯路 + 被推翻的结论 + 每步板上证据(log 行),如实叙事。
>
> 与其他层分工:[notes/](../notes/) = raw 按天流水(取证源);本目录 = 回溯提炼的完整叙事
> + canonical 结论;[tutorial/](../tutorial/) = 面向读者的成功路径;[archive/](../archive/) =
> 被本系列纠正的旧错结论(保留"走过的错路"痕迹,不误导)。

## 篇章划分

| 篇 | 故障域 | 坑号 | 状态 |
|---|---|---|---|
| [01-rkbin-spl-contracts.md](01-rkbin-spl-contracts.md) | rkbin SPL 三个隐性契约(chip tag / optee hash / FIT 布局) | #1 #2 #3 | ✅ |
| [02-busybox-init-devtmpfs.md](02-busybox-init-devtmpfs.md) | init 控制台 + devtmpfs 时序 | #4 #11 | ✅ |
| [03-build-verification.md](03-build-verification.md) | 构建验证方法论(增量重编 / 产物取证层级) | #9 #10 | ✅ |
| [04-sfc-nand-saga.md](04-sfc-nand-saga.md) | SPI-NAND / SFC 读写 + loader 弱写 saga(**最重一篇**) | #5 #6 #7 #8 #12 | ✅ |

## 一句话主线

RK3506B 这条 boot 链,**rkbin SPL(闭源)定了三个不可违背的契约**(篇 01);主线侧要补
**两个 init 时序约定**(篇 02);构建/验证有**两条方法论**(篇 03);最深的坑是
**SPI-NAND 读写 + loader 写弱 rootfs 的完整 saga**(篇 04,含"rkbin 通病不可解"误判如何被
一个干净的 A/B 实验推翻)。

## 取证承诺

每条坑的板上证据都引 [../logs/](../logs/) 的真实 UART 行(**绝不合成**);找不到独立 log 的
诚实标注「待补 log」+ 给出复现命令,不编造。被推翻的旧结论明确标记,指向 canonical。
