# 31 — mk-rootfs.sh + patch-maker.sh 移除（合 main 前清理，2026-06-20）

合 main 前删两个弃用脚本。价值已内敛到迁移目标 / 本笔记，脚本本身删，别处不再提。

## mk-rootfs.sh（legacy static-busybox rootfs handcraft）

- P2.5 标 LEGACY —— 不在 forge DAG（forge 用 `stage-rootfs.sh` + buildroot）。
- 它的逻辑**已全部 port** 到 buildroot post-build（`board/aes/buildroot-external/board/rk3506_aes/post-build.sh`）：
  - **mtdrawdump + mtdbb** 静态编译 —— SFC/NAND 写路径 forensics 工具，post-build 用 `$HOST_DIR gcc -O2 -static` 编（见 notes/13、notes/19）。
  - **applet 符号链接** —— buildroot busybox defconfig 自带全套 applet，不用手动 ln。
- **audio tooling**（aplay/mpg123 + glibc runtime）—— buildroot 包（alsa-utils + mpg123）直接提供，不再手动 cp（Phase E 数字链路通，见 [[phase-e-audio-state]]）。
- busybox 来源：从 buildroot（不再是 initramfs 的 static binary）。
- 删除前确认无残留：`pack-ubifs.sh` / `assemble-update.sh` 的 "run mk-rootfs first" 引用 P2.5 已改指向 stage-rootfs；本笔记轮再清剩余注释。

## patch-maker.sh（生成 numbered patch 的工具，弃用）

- 用途：从 component branch 的 commit 生成 quilt 风格 numbered patches（`git format-patch`）。
- [notes/17](17-2026-06-18-patch-solidification-sop.md) 记：它的 `../../scripts` 对 `src/linux` 二级目录算错（找不到脚本），**bug 弃用**，patches 改手动生成。
- 现状：patches 是 hand-authored/fixed（16 个 linux + 3 个 uboot，quilt `series`），不靠工具生成。
- 删除：README.md / CONTRIBUTING.md 的引用本笔记轮清。

## 关联
- [[sfc-dll-saga-and-writepath]] —— mtdrawdump/mtdbb forensics 工具的来源与用途
- notes/13、notes/19 —— mtdrawdump/mtdbb port 到 buildroot post-build
- notes/17 —— patch-maker bug
