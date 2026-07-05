---
title: forge 编排器
---

<PageHeader icon="🛠️" title="forge 编排器" description="把一长串命令收成一个 setup → build → pack → assemble 编排器" />

前面四卷把每一步都手敲过一遍了：编内核、打 FIT、stage rootfs、assemble 出 update.img，十来个脚本按对的顺序跑。这一卷是 capstone——把这些命令收口成一个编排器 `forge`。它的核心就两件事：一是按 DAG 依赖自动跑对顺序，二是给每个 stage 算内容指纹，输入没变的步骤跳过，改了什么就只重跑什么。RK-SDK 那套 `build.sh` 每次全量重编，forge 对的就是这个。

<ChapterNav>
  <ChapterLink num="01" href="00_forge">forge：把一长串命令收成一个编排器</ChapterLink>
</ChapterNav>
