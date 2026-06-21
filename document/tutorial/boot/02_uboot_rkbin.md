# Ch2 — U-Boot 与 rkbin：在闭源 blob 的咽喉上拔河

> Ch1 把工具链钉死了，这一章我们往地基上放第一块砖：主线 U-Boot。但 RK3506 的 U-Boot 不是"编出来就能跑"那么简单——它前面卡着一颗闭源的 rkbin，方案 A 自己写 SPL 又崩在乱码里（Ch0 讲过）。所以这章其实是笔者和那颗闭源 blob 在板子的咽喉上拔河的全过程：三个它单方面定的隐性契约，加上 bringup 路上四个把我们按在地上摩擦的坑。挺过去，你才能在串口里看到主线 U-Boot 的 banner。

## 前言：第一块砖，就撞上闭源咽喉

工具链既然稳了，按计划下一步就是编 U-Boot。主线 U-Boot 对 RK3506 这颗 SoC 是有驱动的——pinctrl、clock、甚至 sdram 初始化的框架都在——但它**没有板级**：没有这块具体板子的 defconfig，没有设备树。这恰恰是 rk-forge 要补的，[patches/uboot/0001](../../../patches/uboot/0001-rockchip-rk3506-add-AES-RK3506B-board-support-DT-def.patch) 那个补丁干的就是这件事。

编出来是一回事，跑起来是另一回事。RK3506 的启动链，U-Boot proper 是被 SPL 请出来的，而 SPL 这一环目前我们自己的写不出来（方案 A 崩了）。所以现阶段走的是方案 B：**借 vendor 的 DDR/SPL/OP-TEE blob 把链的前半段跑通，再把主线 U-Boot proper 装进 vendor 能认的 FIT 里**。诚实地讲，这不是纯主线 boot——前半段还在借厂商 blob。但它能让主线 U-Boot 在真板上真正跑起来，这是整条链的第一座里程碑，也是后面塞内核的前提。

## 这条链前段长什么样：rkbin 内部

要和 rkbin 拔河，得先看清它的招式。RK3506 从上电到 U-Boot 出 banner，前半段是这样跑的：

```
ROM → idblock(DDR blob + usbplug + SPL) → SPL → FIT(optee@0x1000 + uboot@0x200000 + fdt) → OP-TEE → 降回 NS 世界 → U-Boot proper
```

BootROM 先从存储的扇区 `0x40` 把 idblock 读进来。idblock 里塞着三段：DDR blob（把 DRAM 点亮）、usbplug（下载模式用的）、还有 SPL。SPL 起来之后，去扇区 `0x2000` 找 uboot 的 FIT 镜像，按 FIT 里的 `conf` 把 optee 装到 `0x1000`、uboot 装到 `0x200000`、fdt 装好，然后先跳进 OP-TEE 把安全世界搭起来，再降回非安全世界，把控制权交给 U-Boot proper。

这里有一堆 RK bootrom 和 SPL 单方面定死、我们只能对齐的契约：idblock 在 `0x40`、uboot FIT 在 `0x2000`、optee 装在 `0x1000`、uboot 装在 `0x200000`。vendor 那套打包层——`make.sh`、`boot_merger`、一堆 `.ini`、`make_fit_optee.sh`——在主线其实能塌缩成一次 binman 调用（详见 [notes/01](../../notes/01-2026-06-14-vendor-uboot-build-flow.md) 的对照表）。但方案 B 阶段我们还混着用：既然借了 vendor 的 SPL，就得喂它认的格式。接下来的坑，大多就出在"主线格式"和"vendor 格式"的接缝上。

## 坑之一：vendor SPL 读不懂主线 FIT

第一斧就劈在 FIT 上。我们把主线 U-Boot 装进一个 FIT，指望 vendor SPL 来加载——结果 SPL 甩一句 `Unsupported hash algorithm`，死活不认。

这报错极具误导性，笔者一开始真以为是 hash 算法的事。直到老老实实拿 `dumpimage` 把 vendor 那个已知能跑的 `uboot.img` 解开看结构：optee 是 `Firmware` 装在 `0x1000`、uboot 是 `Standalone` 装在 `0x200000`、fdt 是 Flat DT，`conf` 里 `firmware=optee, loadables=uboot, fdt=fdt`。再去翻 vendor 的 `fit_nodes.sh`，人家自己生成的节点里写的也是 `hash { algo = "sha256"; }`——**vendor 自己就用 sha256**。所以根本不是算法问题，是 vendor fork 的 FIT 节点结构、命名、conf 定义，和主线 binman 生成的那套对不上。

正解不是换算法，而是**结构复刻**：手写一个 [`rk3506-mainline.its`](../../../board/aes/fit/rk3506-mainline.its)，100% 照搬 vendor 已经跑通的 FIT 结构，只把 uboot 节点里那块二进制换成主线编出来的 `u-boot-nodtb.bin`。这一步是整个方案 B 最有价值的发现——把一个模糊的"hash 问题"收敛成了可操作的"照着抄结构"。

## 坑之二：TEXT_BASE 差了 6MB，还有 OP-TEE 到底跳哪里

结构照抄，但有一处不能照抄，一照抄就崩。主线 `u-boot-nodtb.bin` 是按 `CONFIG_TEXT_BASE=0x00800000` 链接的，而 vendor FIT 里 uboot 的 load 写的是 `0x00200000`——差了整整 6MB。代码按 `0x800000` 链接，你却把它装到 `0x200000`，所有绝对寻址全错，必崩。所以 ITS 里 uboot 的 `load` 得改成主线的 `0x800000`，不能盲抄 vendor 的 `0x200000`。

但这又引出一个让人睡不着觉的悬念。vendor 的链是 `SPL → optee(0x1000) → 降 NS → 跳 uboot`，那 OP-TEE 跑完到底跳去哪个地址？如果它从 SPL 传进来的 loadable 信息里取地址（这是标准做法），那 SPL 把我们的 uboot 装到 `0x800000`，OP-TEE 就跳 `0x800000`，自洽；可如果 OP-TEE 把跳转地址硬编码成 vendor 原来的 `0x200000`，那我们 `0x800000` 的代码就跳空了，崩。问题是——`tee.bin` 是 rkbin 预编译的 blob，源码根本不在我们手里，这个跳转地址事先没法确定，只能上板试。

实测的结果让人松了口气：串口里清清楚楚打着 `I/TC: Next entry point address: 0x00800000`——OP-TEE 走的是标准做法，从 loadable 取地址，不是硬编码。这个悬在头上好几天的最大风险，被一行 log 打消了。

## 坑之三：banner 出来了，却 hang 在 misc_init_r

照上面改完，上板——`U-Boot 2026.07-rc4` 的 banner 终于蹦出来了。笔者刚要庆祝，紧接着就是一盆冷水：`initcall misc_init_r() failed`，然后 `### ERROR ### Please RESET the board ###`，死在那里，进不了提示符。

banner 都出来了还崩，这种最磨人。顺着 `misc_init_r` 往里挖，根因链是这样：`misc_init_r` 要调 `rockchip_cpuid_from_efuse` 读 SoC ID，它内部 `uclass_get_device_by_driver` 去找 OTP 设备；可我们那份最小 dtsi **根本没给 OTP 节点**，于是找不到设备、返回 `-ENODEV`，一路链式失败，而 U-Boot 的 initcall 机制对返回非 0 的回调默认是 hang——直接卡死。

有意思的是，主线那个 OTP 驱动其实**已经认得** `rockchip,rk3506-otp`（它共用 rk3568 的读法），缺的只是 DT 里那个节点和它的物理地址。rk3506 的 OTP 基地址不在主线 dtsi 里，最后是从 vendor dtb 的预处理产物里抠出来的：`0xff4f0000`。于是给 dtsi 补上 `otp@ff4f0000`，照主线 rk3528 的最小写法（不带 clocks，实测也不需要），重编上板——这次 `SoC: RK3506B` 顺顺当当打印出来，意味着 OTP 读到了、`misc_init_r` 过了，板子稳稳停在 `=>` 提示符。主线 U-Boot，从上电一路跑到了交互 shell。

## rkbin 的三个隐性契约：入门税

把上面这些加上打包烧录时踩的，归拢一下，其实就是闭源 rkbin SPL 给我们立的三个规矩——详见 [pitfalls/01](../../pitfalls/01-rkbin-spl-contracts.md)，这里浓缩讲。

**第一个规矩是 chip tag**。打包出来的 `update.img` 头里有一个 chip tag，烧录前工具会拿它跟 loader 里写死的 `CHIP_NAME` 比对，对不上当场拒烧。坑在于：RK3506B 这颗 loader 的真实名字其实是 `RK350F`，对，不是 RK3506——你要是手滑硬编一个 `-RK3506`，tag 就对不上，工具翻脸不认人（[`RKBOOT-RK3506B-aes.ini`](../../../board/aes/RKBOOT-RK3506B-aes.ini) 第 13 行 `NAME=RK350F` 就是铁证）。正解是**永远从 loader 动态读这个 tag**：`RK$(dd if=loader bs=1 count=4 skip=21 | rev)`，别图省事硬编。

**第二个规矩是 OP-TEE 的 hash**。整条 FIT 里，uboot 是 loadable、不被校验；fdt 也不被锁；**唯一被 SPL verified-boot 拿 sha256 锁死的，就是 optee 节点那颗 tee.bin**。方案 B 阶段我们借的是 vendor SPL，它锁的 hash 对应 tee v2.10（`93603ca22c...`）。你要是把 tee 换成公开仓里的 v2.40，hash 算出来变成 `616f8152...`，SPL 当场报 `optee Bad hash`——[boot-sdl-202606152121](../../logs/boot-sdl-202606152121.txt) 里这个过程记得一清二楚。所以当时 tee 必须钉死 v2.10。

> 这里笔者得诚实交代一句后续：后来我们把整条 loader 都换成公开 rkbin（SPL v1.12 + tee v2.40），那条全公开的链自洽、板上能跑——所以"必须 v2.10"是方案 B 那条借 vendor SPL 的链的规矩，不是普适真理。但那是打包纯化阶段的事了，方案 B 当时锁的就是 v2.10。

**第三个规矩是 FIT 的字节布局**。就算你 tee 用对了 v2.10，只要这个 FIT 是用主线 `mkimage -E` 打的，optee 照样 Bad hash——只不过这次 hash 变成 `7b78fe4e...`（[boot-sdl-202606152144](../../logs/boot-sdl-202606152144.txt)）。原因很阴：主线 mkimage 和 vendor mkimage 都叫 `-E`（external data），但两者的外部数据**字节布局不一样**，vendor SPL 按它自己那套布局硬读 optee 节点，读错位了，sha256 算的是错位的字节，当然不等于期望值。所以 uboot FIT 必须用 vendor 那颗 2017.09 的 mkimage 打。这是 rkbin SPL 收的一笔"隐性税"。

> 同样诚实一句：后来我们用纯 Python 写了 [fit-pack.py](../../../scripts/fit-pack.py)，把 vendor mkimage 那套 SPL 兼容布局字节级复刻了出来，才算彻底摆脱了 vendor mkimage。但方案 B 那会儿，老老实实用 vendor mkimage 是最快的路。

三条规矩看下来，本质是同一件事：rkbin SPL 闭源，它的 chip tag 表、verified boot 锁的 hash、读 FIT 的字节布局，全是它单方面定的契约，我们只能对齐、改不动。主线侧真正自由的只有 kernel FIT（那是主线 U-Boot 加载的，根本不经 SPL verified boot）。要干净掉这三条，唯一的办法是换掉 rkbin SPL——那是远期的事，这章我们先交了"入门税"。

## 把镜像凑出来，烧到板上

讲完规矩，说说怎么把东西真的弄进板子。forge 现在的打包分几步：[pack-loader.sh](../../../scripts/pack-loader.sh) 用 Rockchip 的 `boot_merger` 从公开 rkbin 把 loader/idblock 打出来（DDR + usbplug + SPL），[pack-fit.sh](../../../scripts/pack-fit.sh) 打 uboot 的 FIT，最后 assemble 成一个完整的 `update.img`。诚实地讲，方案 B 那会儿是 vendor mkimage + boot_merger + 手写 ITS 混着上的，后来才一点点纯化成 fit-pack.py + 全公开 rkbin——纯化是另一条弧线，这章讲的是 bringup 过程，混着用没毛病。

烧录有两条路，走哪条取决于板子从哪儿启动。这块 RK3506B 实测是 **SPI-NAND 优先**启动的（[notes/01](../../notes/01-2026-06-14-vendor-uboot-build-flow.md) Stage 3 验证过）——SD 卡你裸写一个镜像进去，bootrom 根本不选，转头就去起 NAND 里的出厂 vendor。所以主线落地走的是 NAND：用 RKDevTool 把 `update.img` 烧进板载 SPI-NAND（chip tag 对了才烧得下去，这就是上面第一个规矩）。SD 卡这条呢，是作为开发和恢复用的第二媒体，[flash-sd.sh](../../../scripts/flash-sd.sh) 用 `dd` 把 sd.img 写进卡——这脚本是一堆安全检查裹出来的：拒绝写挂载着的设备、拒绝写系统盘、拒绝分区节点、写之前还非要你手敲一遍设备名确认，生怕你把宿主盘抹了。WSL2 用户记得 SD 卡得先走 `usbipd-win` 透传进来。

## 成功长这样

交完三笔入门税、爬完四个坑，板子上终于跑出了我们想要的那行。下面这段是从方案 B 的里程碑 log（[boot-sdl-202606142052](../../logs/boot-sdl-202606142052.txt)）里截的，一个字没合成：

```
U-Boot 2026.07-rc4-g5ca1a73c7d30 (Jun 14 2026 - 20:47:09 +0800)
Model: Rockchip RK3506 Evaluation Board (ATK RK3506B)
SoC:   RK3506B
DRAM:  512 MiB
Core:  33 devices, 15 uclasses, devicetree: separate
...
Hit any key to stop autoboot: 0
=>
```

每一行都值回票价：`U-Boot 2026.07-rc4` 是主线版本，不是 vendor 的 2017；`SoC: RK3506B` 打印出来，说明 OTP 读到了、`misc_init_r` 那个坑已经填平；`DRAM: 512 MiB` 是借来的 vendor DDR blob 点亮的内存；最后停在 `=>`，意味着主线 U-Boot 从上电一路跑到了交互 shell。

方案 B 的里程碑，到此达成。主线 U-Boot 在 RK3506B 真板上活了。诚实的边界还是要再强调一遍：它赖以运行的 DDR/SPL/OP-TEE 还是借的 vendor blob，这不是纯主线 boot。但有了这块能跑的 U-Boot 当底座，下一章我们就能往上面塞内核——看主线 Linux 认不认我们亲手写的那块板级设备树，能不能一路跑到 `Starting kernel`。我们 Ch3 见。
