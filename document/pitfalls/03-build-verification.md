# 03 — 构建侧的两个方法论坑:增量重编卡 syncconfig + strings 看错层

前面几篇坑都在板上,这篇换个地方——构建和验证的方法论。两条坑都不是代码 bug,是"你看错了层":一条让增量重编莫名其妙卡在 syncconfig,另一条让你以为探针删干净了、上板却还在打。共同教训就一句:工具链路径要看绝对、产物取证要看对层。

环境跟前面一致,工具链是 vendor 那套 `gcc-arm-10.3` armhf,构建走 vendor 的 make.sh/build.sh 风格。

## 增量重编,syncconfig 莫名其妙找不到 gcc

事情是这样的:笔者改了一行驱动,想增量重编内核,结果 `scripts/kconfig/conf --syncconfig Kconfig` 这一阶段直接报错,说找不到 gcc,构建中断。第一反应是常规排查——是不是缺包了?工具链没装好?.config 损坏了?查一圈全没问题。

折腾半天才定位到,根子出在 `CROSS_COMPILE` 笔者给的是个**相对路径**,大概是 `arm-linux-gnueabihf-` 这种,或者 `../../vendor-sdk/.../arm-none-linux-gnueabihf-`。机制在于:syncconfig 这一步是 kconfig 在 worktree 根目录跑的,它会拿 `CROSS_COMPILE` 去拼 `gcc` 的路径;咱们给相对路径,它就按 worktree 根那个工作目录去解析,解析到的地方根本没 gcc,于是整条增量链断在这儿。这也解释了为什么 vendor 的 `make.sh`/build.sh 一律传绝对路径——不是他们啰嗦,是被坑过。

正解没有捷径:`CROSS_COMPILE` 必须是整段绝对路径。你去看 vendor 的构建日志,[build-uboot.log](../logs/build-uboot.log) 第 167 行就是这么干的:

```
+ ./make.sh CROSS_COMPILE=/home/charliechen/rk-forge/third_party/vendor-sdk/prebuilts/gcc/linux-x86/arm/gcc-arm-10.3-2021.07-x86_64-arm-none-linux-gnueabihf/bin/arm-none-linux-gnueabihf- alientek_rk3506 --spl-new
```

一长串绝对路径,内核构建日志 [build-kernel.log](../logs/build-kernel.log) 里也是同一个套路(行 99/182/2812/3237)。所以 forge 这边的脚本、文档、还有我自己的命令速记,统统把 CROSS_COMPILE 写死成绝对路径。

⚠️ 任何 kconfig-driven 的构建(内核、U-Boot)增量重编之前,先确认 `CROSS_COMPILE` 是绝对路径。相对路径能让你在 syncconfig 阶段卡半天还摸不着头脑——这条当时没存下报错原文(现存的 build log 都是成功的绝对路径构建),你要复现,拿 `CROSS_COMPILE=arm-linux-gnueabihf-` 跑一次增量重编就能抓到那句"找不到 gcc"。

## strings zImage 查探针,查了个寂寞

第二条更隐蔽。我在 instrumented 内核里加过 PROBE 打印(在 `drivers/mtd/nand/spi/core.c`、`winbond.c` 里塞 `dev_info`),调试完想确认探针删干净了,顺手 `strings zImage | grep PROBE`——啥都 grep 不到。我一度以为探针已经删干净了,结果上板一看,`PROBE ...` 还在 dmesg 里欢快地打。

这回我又看错层了。zImage 是 **XZ 压缩**的部署产物,内核文本早就被压成一坨不可读的字节流,`strings` 哪里扫得到 `PROBE`、`dev_info` 这种明文。要看探针在不在编译产物里,得查**没压缩的 `.o`**(或者 vmlinux)。

正解是对着 instrumented 那棵树,跑 `strings drivers/mtd/nand/spi/winbond.o | grep PROBE`(命中)对比 `strings zImage | grep PROBE`(空),一比就坐实。note10 里我验增量构建也是看 `.o` 级产物——`spi-rockchip-sfc.o`、`winbond.o`、`spi-nand core.o` 编进、zImage 出(12059136 字节)——看的从来不是 zImage。而板上那些 PROBE 文本,全来自运行时 dmesg,跟 strings 一点关系没有(参见 `archive/HANDOFF-LOADER-MARGINAL-WRITE.md` 里 instrumented 探针那段)。

⚠️ 验探针/字符串/符号在不在编译产物里,查未压缩的 `.o` 或 vmlinux,别查 zImage(XZ 压缩,strings 根本看不见)。清探针要三重确认:`git diff` 干净 + `.o` 重编 + 板侧 dmesg 不再打 PROBE。

接下来终于进最硬的那篇:SPI-NAND 读写 + loader 写弱 rootfs 的完整 saga——中间还判过一次"rkbin 通病、不可解"的死结论,差点就信了。
