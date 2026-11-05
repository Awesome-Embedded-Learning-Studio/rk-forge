---
title: forge 编排器
---

<PageHeader icon="🛠️" title="forge 编排器" description="把一长串命令收成一个 setup → build → pack → assemble 编排器" />

前面四卷的活，咱们从编内核、打 FIT、置备 rootfs 到组装 `update.img` 都手敲过一遍了，十来步的顺序断不得。这一卷是收官的 capstone，咱们把那些手敲的步骤收进一个编排器 `forge`，如今它是 src/forge 的 Python 包。它的核心就两件事：一是按 DAG 的依赖自动跑对顺序，二是给每个 stage 算出内容的指纹，输入没变的步骤跳过，改了什么就只重跑什么。RK-SDK 那套 `build.sh` 的每次全量重编，forge 对的就是这个。

<ChapterNav>
  <ChapterLink num="01" href="00_forge">forge：把整条构建链收成一个命令</ChapterLink>
</ChapterNav>
