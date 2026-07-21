# forge：把一长串命令收成一个编排器，顺手干掉 vendor-sdk

> boot 系列让板子启动到 console，rootfs 系列让它持久跑进 shell，peripherals 把外设一个个点亮，sd-boot 开出第二条启动路。这一章是收口：把前面手敲的十来个脚本串成一个编排器 `forge`，顺手把这套构建链对 ATK vendor-sdk 的最后依赖也切干净——这是 rk-forge 这本书的立身所在。

## 前言：为什么需要 forge

跟着前面那些章节走一遍就清楚了：从源码到一块能烧的 `update.img`，要 fetch 源树、apply 补丁、编 kernel、编 uboot、buildroot 出 rootfs、打 loader、打 FIT、stage rootfs、打 ubifs、assemble——十来个脚本，顺序不能错，漏一步就产物不全。手敲两遍就想骂人。这是 rk-forge 的头号易用性痛点，也是从 imx-forge 继承下来的债：没有编排器。

RK-SDK 那套 `build.sh` 倒是有编排，但它每次全量重编——改一个板级 DT，kernel 从头编一遍。所以 forge 要解决两件事：把这一长串按 DAG 自动跑对，以及只重跑真正需要的步骤。还有第三件事，比前两件更重——把构建链对 vendor-sdk 的依赖切干净，否则别人一句"我有 SDK 为啥用你的"就能把仓库的立身废了。

## forge 的两个设计：DAG + content-hash stage-skip

[`scripts/forge.sh`](../../../scripts/forge.sh) 是个单入口编排器，核心是两个设计。

第一个是 DAG。它知道每个 stage 依赖哪些产物，按拓扑序跑：setup → build → pack → assemble 是主干，`forge all` 就是这一条龙。pack 内部还展开成 pack-loader / pack-fit / stage-rootfs / pack-ubifs 四个子 stage；SD 变体（pack-sd / assemble --sd）在 NAND pack 的基础上再加 SD 专属几步。每个 stage 在 [forge.sh](../../../scripts/forge.sh) 里就是一个 `stage_xxx` 函数，顺序读下来就是 DAG 的拓扑序。

第二个是 content-hash stage-skip，这是对 build.sh 全量重编的核心改进。每个 stage 跑之前，[`lib/stage.sh`](../../../scripts/lib/stage.sh) 把它的输入算一个内容指纹——`stage_fingerprint` 把传入的每个文件（或目录下的 `*.c/*.h/*.dts/*.config/series/*.patch` 这类构建相关文件）的路径、大小、mtime 拼起来过一遍 sha1。指纹和上次一样就 skip（`up-to-date`），不一样才重跑。改一个板级 DT，只有 pack-fit 和它下游的 assemble 重跑，kernel 编译那步纹丝不动。要强制全跑，`--force` 重跑单步、`--no-skip` 跑全部。

`run_stage` 那段逻辑就几行，但正是 forge 区别于 build.sh 的关键——一个 stage 是否重跑，取决于输入是否变化，而不是产物在不在。后面所有"开发循环里改了 X，只重编 X"的体验都来自这里。

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

最常用就是 `forge all`——一条命令从零出到 `out/update.img`。要 SD 卡镜像，`forge pack-sd` 或 `forge assemble --sd`。想看哪些 stage 跑过、哪些没跑，`forge status` 列出每个 stage 的 fingerprint 是否落盘。

## 去 vendor-sdk：这才是 forge 的立身

forge 的编排价值是易用性，去 vendor-sdk 才是仓库的立身。vendor-sdk 是正点原子的 ATK-DLRK3506 BSP（linux 6.1.118，repo 管理，gitignored），它在我们这出过两个力：一个是工具与二进制提供者（rkbin loader/tee、toolchain、busybox 源、`mkimage`、`afptool`/`rkImageMaker`），一个是板级 DT 和外设 config 的参考源。两边都消掉，vendor-sdk 才能从构建链里彻底拿走。完整评估见 [notes/12](../../notes/12-2026-06-17-kill-vendor-sdk-assessment.md)。

第一边消得比较顺。rkbin 改成 `third_party/rkbin` 公开 submodule（pin `ecb4fcb`，loader/DDR/tee/usbplug 全用公开仓的版本，板上验证过）；toolchain 换 ArmGNU 15.2，路径写死在 `config/toolchain.conf`（commit `a3f2936`，不再靠 PATH 里碰运气）；busybox 源切 upstream；rootfs 交给 buildroot 自建。这些做完，源码层就零 vendor-sdk 了，只剩打包工具。

打包工具是难的那块，因为撞 Rockchip/ATK 的闭源墙。`afptool` + `rkImageMaker`（打 `update.img`）和 vendor `mkimage` 2017.09（打 uboot FIT）都是二进制，前者还触发过 issue #8（boot_merger）那类净室审计。我们的解法不是找替代品，而是直接手搓——见下面两节。

## rkfw-pack.py：替掉 afptool + rkImageMaker

`update.img` 的格式是两层套娃：外层 RKFW（`0x66` 头 + loader + RKAF archive + 32 字节 ASCII MD5），内层 RKAF（`0x8c` 头 + 分区表 + 分区镜像）。`scripts/rkfw-pack.py` 把这两层都自己实现：解析 package-file + parameter、读 loader 的 chip tag（loader 偏移 21 处那 4 字节反转回来，所以 chip tag 是 RK350F 不是硬编 RK3506——这个坑在前面 assemble 章节里也提过）、按 `0x800` 对齐铺分区、最后算 Rockchip 自家那个 CRC32。

⚠️ 这里有个反直觉的坑：Rockchip 用的 CRC32 不是 IEEE 那个 `0x04c11db7`，而是 MSB-first 的 `0x04c10db7`——多项式常数不一样。我们一开始按 zlib 的 CRC32 算，结果 trailing checksum 和 vendor afptool 对不上，对了好久才发现 poly 差一位。`rkfw-pack.py` 里那张 256 项的 `RKCRC32_TABLE` 是从社区 `afptool-rs` 抄来、再用 vendor 输出逐字节对过的。

rkfw-pack.py 还顺手把 SD 卡镜像那个坑也兜了：parameter 里写 `-0x<addr>` 的 grow 分区正则匹配不上，`nand_addr` 会落到 `0xFFFFFFFF`，RK 工具不写镜像，板子一启动就 root-mount panic。现在 pack 阶段对这种 grow 项直接告警，不让空分区出仓。

## fit-pack.py：替掉 vendor mkimage 2017.09

mkimage 这块比 rkfw-pack 难，故事也长（完整 saga 见 [notes/20](../../notes/20-2026-06-19-mkimage-saga-handoff.md)）。简短地说：uboot.img 是一个 FIT `-E` external-data 镜像，rkbin SPL 只认 vendor mkimage 2017.09 那种 `-E` 布局；主线 mkimage 的 `-E` 把 optee 数据摆在不同 offset，SPL 读到错位的字节，炸 `optee Bad hash`。能编出兼容布局的那个 ATK fork 又是非公开的（正点原子内网 manifest），手搓 mkimage 又会拖进整条 U-Boot build 依赖链（generated autoconfh 一路反解到地狱）。

解法和 rkfw-pack.py 一个路子：逆向 vendor `uboot.img` 的字节布局，纯 Python 自己拼 FIT。这就是 [`scripts/fit-pack.py`](../../../scripts/fit-pack.py)，关键就三件事。

一是 FIT `-E` 文件长这样：FDT blob（header + struct + strings）后面跟一段 external data，每个 image 的 blob 按 `FIT_ALIGN=0x200`（即 `image.h:958` 里的 `IMAGE_ALIGN_SIZE`）对齐排在 external 里，image 节点的 `data-offset`/`data-size` 指向它的位置和长度，hash 节点存那段 blob 的 sha256。二是 FDT 的 string table 顺序有讲究——它得忠实地复现 mkimage 的三阶段构建（ITS 原序 DFS 入串表 → root 自动 props → external 转换新加 props），否则字节对不上。三是一个踩出来的硬约束：根节点上那个 `/totalsize` 属性，得设成整个文件的大小，因为 Rockchip SPL 是按 `ceil(/totalsize / bl_len) * bl_len` 算加载量的（`spl_boot_image.c:293`），小于文件大小就只加载前半截、external 漏掉。

这套布局还有 Mode A / Mode B 之分。Mode A 给 vendor SPL 用（uboot.img），external 起始是 `FIT_ALIGN(fdt_totalsize)`，data-offset 是相对值，root 上 version+totalsize+timestamp 都有；Mode B 给主线 U-Boot bootm 用（boot.img/boot-nand.img），external 起始是 `mkimage -p N` 那个绝对 offset（0x800），data-position 是绝对值，blob 连续排（无 FIT_ALIGN gap），root 只有 timestamp。这两个模式 fit-pack.py 都支持，`--external-offset 0` 走 A、`>0` 走 B，pack-fit.sh 的三个 FIT（uboot/boot/boot-nand）现在全归它打。

诚实交代一句：fit-pack.py 的输出**不是** vendor mkimage 的逐字复现。vendor 那个 FDT→external 之间有一段 mkimage `fdt_pack` 留下的残留 gap，加上 host 时间戳和 inline-FIT 时代的 totalsize，这些不模拟 libfdt 内部是复现不出来的。但 selftest 证明它们对消费者（SPL 或 bootm）零影响——FDT 树除 `/timestamp`、`/totalsize` 这俩 host 簿记值外逐节点全等，三个 blob 的 sha256 和 vendor 逐字一致、offset 也一致。`fit-pack.py selftest` 就是干这个的：把 vendor `uboot.img` 的三个 blob 抠出来重新打一遍，比树、比 blob、比 offset，离线就能验，不用上板。

> 板上验证（2026-06-19）：烧 `update-p4-fitpack.img`，fit-pack.py Mode A 的 uboot.img 过 SPL 启动到 kernel；烧 `update-p2-unified-fitpack.img`，Mode B 的 boot.img 过主线 U-Boot bootm，kernel 顺利启动。fit-pack.py 是全 FIT 唯一打包器，主线 mkimage 只剩 `mkimage -l` 解析校验那一个用途。

## 两个诚实的细节

forge 不假装一切都可复现，有两个细节如实交代。

U-Boot 那边是真能做到字节级：[`build-uboot.sh`](../../../scripts/build-uboot.sh) 设了 `SOURCE_DATE_EPOCH` 固定时间戳，跑两次 uboot 二进制逐字一致。FIT 那层 fit-pack.py 也支持 `--timestamp 0`（默认就是 0），所以 uboot.img 整条链可复现。

rootfs 那个 ext4 **不是** byte-identical——`mke2fs -d` 的 superblock 写时间（`s_wtime` / `s_mtime` / journal seq）是 host 相关，跑两次 sha256 不同；但结构、layout、内容是确定性的（设了固定 UUID + hash_seed）。这是 buildroot rootfs 的已知限制，forge 标注了、没藏着。UBIFS 那边类似，metadata 时间戳跑两次会差，但分区内容是定的。板子能不能跑看的是内容，不看 superblock 时间，所以这不挡交付，只是不能宣称"全链 byte-reproducible"。

## 一个 shell 上的提醒

forge 的 lib 脚本用 `BASH_SOURCE` 定位自己，bash 数组也用了一堆，zsh 下这些不可靠。所以**一律用 `bash scripts/forge.sh ...` 调**，别直接 `./scripts/forge.sh`（shebang 在正常情况下能兜住，但 `sh scripts/forge.sh` 这种就抓瞎了）。forge 自己也加了 guard：发现不是 bash 跑的，会 `exec` 重启自己到 bash 下——这是兜底，不是让咱们随便用 sh 调。

## 成功长这样

`forge all` 跑完，tail 是这几行（截自一次净室构建的实测输出）：

```
[setup]   applying linux patch series
[setup]   applying uboot patch series
setup complete
[build]   kernel (build-linux.sh — make is internally incremental)
[build]   U-Boot (build-uboot.sh — SOURCE_DATE_EPOCH → byte-reproducible)
[build]   rootfs (build-rootfs.sh — buildroot + WSL clean PATH)
build complete (kernel + U-Boot + rootfs all automated)
pack-loader: done
pack-fit: done
stage-rootfs: done
pack-ubifs: done
assemble: done
all done → board/aes/out/update.img
```

从源树到一块能烧的 `update.img`，一条命令、按 DAG、只重跑该跑的步骤，构建链对 vendor-sdk 零依赖。前面那些系列里手敲的每一行——fetch、apply、build、pack-loader、pack-fit、stage-rootfs、pack-ubifs、assemble——forge 都替咱们串起来了；afptool、rkImageMaker、vendor mkimage 这三个 ATK 闭源工具，被 rkfw-pack.py 和 fit-pack.py 换成了仓库里的两个 Python 文件。

到这里，整个教程走完了：boot 让板子启动到 console，rootfs 让它持久跑进 shell，peripherals 把外设一个个点亮，sd-boot 开出第二条启动路，本篇用 forge 把这一切自动化、并把 ATK 那套闭源工具链彻底干掉。一块空板，到一块能联网、能持久、能一键出镜像、构建链全公开的 RK3506 主线开发板——这就是 rk-forge 这本书带咱们走完的全程。给板子拍张照，完结撒花。
