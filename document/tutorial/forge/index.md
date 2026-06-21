---
title: forge 编排器
---

<PageHeader icon="🛠️" title="forge 编排器" description="把一长串命令收成一个 setup → build → pack → assemble 编排器" />

前面四卷把每一步都手敲过一遍了。forge 是把这些命令收口成一个编排器的 capstone：`setup` 拉源码、`build` 编 kernel/uboot/rootfs、`pack` 打 FIT/loader、`assemble` 出可烧镜像——DAG 依赖 + 内容哈希增量跳过，改了什么就只重跑什么。

<ChapterNav>
  <ChapterLink num="01" href="00_forge">forge：把一长串命令收成一个编排器</ChapterLink>
</ChapterNav>
