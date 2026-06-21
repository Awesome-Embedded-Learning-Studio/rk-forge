# forge：把一长串命令收成一个编排器

> 前面所有系列——编内核、打 FIT、stage rootfs、assemble update.img——每一步都是手敲命令。这一章我们把它们收口成一个编排器 `forge`：一条命令按正确的顺序跑完整条链，输入没变的步骤自动跳过。这是 forge 对 RK-SDK 那套 `build.sh` 的核心改进。

## 前言：为什么需要 forge

你跟着前面那些章节走一遍就知道了：从源码到一块能烧的 `update.img`，要跑 fetch 源树、apply 补丁、编 kernel、编 uboot、buildroot 出 rootfs、打 loader、打 FIT、stage rootfs、打 ubifs、assemble——十来个脚本，顺序不能错，漏一步就产物不全。手敲两遍你就想骂人。

这正是 rk-forge 的头号易用性痛点，也是从 imx-forge 继承下来的债——没有编排器。RK-SDK 那套 `build.sh` 倒是有编排，但它是"每次全量重编"，你改一个 DT、它把 kernel 从头编一遍。所以 forge 要解决两件事：一是把这一长串按 DAG 自动跑对，二是只重跑真正需要的步骤。

## forge 的灵魂：DAG + content-hash stage-skip

forge 是个单入口编排器（[`scripts/forge.sh`](../../../scripts/forge.sh)），核心是两个设计。

第一是 **DAG**：它知道每个 stage 依赖哪些产物，按正确的拓扑序跑。setup → build → pack → assemble 是主干；pack 内部还有 pack-loader / pack-fit / stage-rootfs / pack-ubifs 四个子 stage；SD 变体（pack-sd / assemble --sd）在 NAND pack 的基础上再加 SD 专属的几步。`forge all` 就是 setup → build → pack → assemble 一条龙。

第二是 **content-hash stage-skip**——这是 forge 对 build.sh 全量重编的核心改进。每个 stage 跑之前，[`lib/stage.sh`](../../../scripts/lib/stage.sh) 把它的输入算一个内容指纹；指纹和上次一样，就 skip（`up-to-date`），不一样才重跑。你改一个板级 DT，只有 pack-fit 和它下游的 assemble 重跑，kernel 编译那步纹丝不动。要强制全跑，`--force` 或 `--no-skip`。

## 八个子命令

```
forge setup      fetch 源树 + WiFi 驱动 + apply 补丁 series
forge build      编 kernel + uboot + rootfs（全自动化）
forge pack       打 loader + FIT + stage/ubifs rootfs
forge pack-sd    打 SD 镜像（复用 NAND pack + SD layout）
forge assemble   组装 update.img（--provision/--nand/--rescue/--sd）
forge all        setup → build → pack → assemble（一键出镜像）
forge clean      清 out/（--full 连源树一起 mrproper）
forge status     看各 stage 是否 up-to-date
```

最常用的就是 `forge all`——一条命令，从零出到 `out/update.img`。要 SD 卡的镜像，`forge assemble --sd`。想看哪些 stage 已经跑过、哪些还没，`forge status`。

## 两个诚实的细节

forge 不假装一切都可复现，有两个细节如实交代。一是 U-Boot 的字节可复现：`build-uboot.sh` 用 `SOURCE_DATE_EPOCH` 固定时间戳，跑两次 uboot 二进制逐字一致。二是 rootfs 那个 ext4 **不是** byte-identical——`mke2fs -d` 的 superblock 写时间（s_wtime / s_mtime / journal seq）是 host 相关，跑两次 sha256 不同；但结构、layout、内容是确定性的（设了固定 UUID + hash_seed）。这是 buildroot rootfs 的已知限制，forge 标注了、没藏着。

## 一个 shell 上的提醒

forge 的 lib 脚本用 `BASH_SOURCE` 定位自己，zsh 下这变量是空的。所以**一律用 `bash scripts/forge.sh ...` 调**，别直接 `./scripts/forge.sh`（shebang 在正常情况下能兜住，但 `sh scripts/forge.sh` 这种就抓瞎了）。forge 自己也加了 guard：发现不是 bash 跑的，会 exec 重启自己到 bash 下。

## 成功长这样

`forge all` 跑完，结尾是这行：

```
all done → board/aes/out/update.img
```

从源树到一块能烧的 `update.img`，一条命令、按 DAG、只重跑该跑的步骤。前面那些系列里你手敲的每一行，forge 都替你串起来了。

到这里，整个教程走完了：boot 让板子启动到 console，rootfs 让它持久跑进 shell，peripherals 把外设一个个点亮，sd-boot 开出第二条启动路，build 用 forge 把这一切自动化。一块空板，到一块能联网、能持久、能一键出镜像的 RK3506 主线开发板——这就是 rk-forge 这本书带你走完的全程。给板子拍张照，完结撒花。
