# document/ — rk-forge 文档体系

rk-forge 的文档分两半:**规划**([planning/](planning/),课纲)和**执行**(下面四层,教材 + 取证)。原始过程素材(raw 笔记 + 板上日志)全部保留作取证参考,和提炼后的结论分开摆;被推翻的旧结论则降级到 archive,免得误导后来人。

> 想看"整门课长什么样、三块板怎么排、哪块板已经能教",从 [planning/](planning/) 进——它是 ROADMAP(课纲)→ tutorial(教材)→ pitfalls/notes/logs(取证) 这条接力链的起点。

## 执行层:四层结构

| 层 | 目录 | 角色 |
|---|---|---|
| 教程 | [tutorial/](tutorial/) | 面向外部读者:结论性 how-to(成功路径)。每章"成功长这样"配真实 UART 抓取。 |
| 踩坑日记 | [pitfalls/](pitfalls/) | 按**故障域分篇**(4 篇),还原真实时间线 + 弯路 + 被推翻的结论 + 每步板上 log 佐证,覆盖 12 条坑。 |
| 过程笔记 | [notes/](notes/) | raw dated bringup 日记(含失败、噪音、半成品),honesty substrate,是踩坑日记的取证源。 |
| 归档 | `archive/` | 被证伪/取代的旧结论文档,带 superseded banner + canonical 指针,保留"走过的错路"但不误导。 |
| 参考 | [sdk-diff.md](sdk-diff.md) | vendor SDK vs 主线移植的逐外设差距对照(活文档)。 |

## 板上日志(取证素材)

[logs/](logs/) 是 47 个真实板上 UART 抓取 + 构建日志,是笔记和踩坑日记"绝不合成"承诺的底气。每个里程碑 log 对应佐证哪个坑,[logs/README.md](logs/README.md) 里有索引。

## 原则

原始素材(`notes/` + `logs/`)是取证链,不删。被推翻的旧结论进 `archive/` + superseded 标记,不当 first-class 参考。`notes/`(按天流水)和 `pitfalls/`(回溯叙事)内容必然有重叠,但分工不同——一个记现场、一个讲结论——不去重。

## 阅读入口

想看三门课的总纲和路线,从 [planning/](planning/) 进;想理解项目为什么这么做,从 [tutorial/boot/00_roadmap.md](tutorial/boot/00_roadmap.md) 进;想看踩过的坑,进 [pitfalls/](pitfalls/)(按故障域 4 篇);想看原始时间线,进 [notes/](notes/)(编号 01–12 dated)。
