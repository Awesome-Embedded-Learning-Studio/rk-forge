# document/notes — dated bringup log

This tier holds **honest, dated bringup notes** — what worked, what didn't, the exact
UART output, the brick scares. It's the project's honesty substrate (on-brand:
rk-forge's identity is "report the gap truthfully").

## 命名约定

`NN-YYYY-MM-DD-<slug>.md` — **序号 + 日期 + slug**:

- **序号 `NN`** = 推荐阅读顺序(理解项目的递进阶段),主导排序。
- **日期 `YYYY-MM-DD`** = 笔记对应的工作日期。
- **slug** = 内容一句话描述。

跨阶段持续更新的"活文档"用其主工作日期。Don't sanitize failures — they're the
most useful part.

## 阅读顺序(按阶段递进)

| 序号 | 文件 | 阶段 |
|---|---|---|
| 01 | [01-2026-06-14-vendor-uboot-build-flow.md](01-2026-06-14-vendor-uboot-build-flow.md) | 先懂 vendor 怎么编 U-Boot(主线迁移的参照基准) |
| 02 | [02-2026-06-14-mainline-bringup-handoff.md](02-2026-06-14-mainline-bringup-handoff.md) | 主线 U-Boot bring-up 状态总览(活文档,跨阶段) |
| 03 | [03-2026-06-14-maskrom-brick-recovery.md](03-2026-06-14-maskrom-brick-recovery.md) | 救砖插曲:固件写坏 → MaskROM 恢复 |
| 04 | [04-2026-06-14-mainline-uboot-via-vendor-spl.md](04-2026-06-14-mainline-uboot-via-vendor-spl.md) | 方案 B:借 vendor SPL 跑主线 U-Boot,真板进提示符(里程碑) |

## 待补

- `NN-2026-06-13-restructure.md` — repo 重构 + 前提验证(对应 commit `325a3bf`,目前无独立笔记)。
- vendor-sdk 总体调研(当前散在 01 里,可抽独立笔记)。
