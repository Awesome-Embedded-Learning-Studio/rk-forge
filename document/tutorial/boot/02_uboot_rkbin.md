# Ch2 — U-Boot 与 rkbin：在闭源 blob 的咽喉上拔河

> Ch1 把工具链敲定了，这一章咱们往地基上放第一块砖：主线 U-Boot。但 RK3506 的 U-Boot 不是编出来就能跑的，它前面卡着一颗闭源的 rkbin，方案 A 的自己写 SPL 那一路又崩在乱码里（Ch0 讲过）。所以这一章其实是咱们和那颗闭源 blob 在板子咽喉上拔河的全过程：三条它单方面定下的隐性约定，加上 bringup 路上四次把咱们按在地上摩擦的翻车。等咱们挺过去，串口里才能看到主线 U-Boot 的 banner。

## 前言：第一块砖，正好卡在闭源咽喉

工具链既然稳了，按计划的下一步，咱们要编的就是 U-Boot。主线 U-Boot 对 RK3506 这颗 SoC 是有驱动的（pinctrl、clock、甚至 sdram 初始化的框架都在），但它偏偏**没有板级**：没有这块具体板子的 defconfig，也没有对应的设备树。这恰恰是 rk-forge 要补的，[patches/uboot/0001](../../../boards/aes/patches/uboot/0001-rockchip-rk3506-add-AES-RK3506B-board-support-DT-def.patch) 那个补丁干的就是这件事。

编出来的产物是一回事，而跑得起来是另一回事。RK3506 的启动链里，U-Boot proper 是被 SPL 请出来的，而 SPL 这一环咱们自己的目前还写不出来（方案 A 崩了）。所以现阶段走的是方案 B：**借原厂的 DDR/SPL/OP-TEE blob 把链的前半段跑通，再把主线 U-Boot proper 装进原厂能认的 FIT 里**。诚实地讲，它其实还不是纯主线 boot，前半段还在借原厂的 blob。但它能让主线 U-Boot 在真正的板子上跑起来，后面塞内核才有了底座。

## 启动链前段长什么样：rkbin 内部

咱们要和 rkbin 拔河，就得看清它的招式。咱们看 RK3506 从上电到 U-Boot 出 banner 的前半段，是这样跑的：

```
ROM → idblock(DDR blob + usbplug + SPL) → SPL → FIT(optee@0x1000 + uboot@0x200000 + fdt) → OP-TEE → 降回 NS 世界 → U-Boot proper
```

咱们从 BootROM 看起，它会从存储的扇区 `0x40` 把 idblock 读进来。idblock 里塞了三段，DDR blob 负责的是把 DRAM 点亮，usbplug 是下载模式用的，还有的就是 SPL。SPL 起来之后去扇区 `0x2000` 找 uboot 的 FIT 镜像，按 FIT 里的 `conf` 把 optee 装到 `0x1000`、uboot 装到 `0x200000`、fdt 装好，然后跳进 OP-TEE 把安全世界搭了起来，再降回非安全的世界，把控制权交回到 U-Boot proper 的手里。

RK bootrom 和 SPL 单方面定死了一堆咱们只能对齐的约定。idblock 的位置在 `0x40`、uboot FIT 的位置在 `0x2000`，optee 的装入地址是 `0x1000`、uboot 的装入地址是 `0x200000`。原厂的那套打包层（`make.sh`、`boot_merger`、一堆 `.ini`、`make_fit_optee.sh`），在主线其实能塌缩成一次 binman 调用，对照表详见 [notes/01](../../notes/01-2026-06-14-vendor-uboot-build-flow.md) 的记录。但方案 B 阶段咱们还混着用：既然借了原厂的 SPL，就得喂它认的格式。接下来的那些翻车，大多就出在主线格式和原厂格式的接缝上。

## 翻车一：原厂 SPL 读不懂主线 FIT

第一斧就劈在了 FIT 上。咱们把主线 U-Boot 装进一个 FIT，指望的是原厂 SPL 来加载，结果 SPL 甩了一句 `Unsupported hash algorithm`、死活不认。

这报错是极具误导性的，笔者一开始真以为是 hash 算法的事。直到老老实实拿 `dumpimage` 把原厂那个已知能跑的 `uboot.img` 解开看结构：optee 的类型是 `Firmware`、地址在 `0x1000`，uboot 的类型是 `Standalone`、地址在 `0x200000`，fdt 的类型是 Flat DT，`conf` 里写的是 `firmware=optee, loadables=uboot, fdt=fdt`。再去翻原厂的 `fit_nodes.sh`，人家自己生成的节点里写的也是 `hash { algo = "sha256"; }`，**原厂自己用的就是 sha256**。所以根本不是算法的问题，真正的分歧在原厂 fork 的 FIT 节点结构、命名和 conf 定义上，它们和主线 binman 生成的那套对不上。

正解其实跟算法无关，要的是**结构复刻**：咱们手写一个 [`rk3506-mainline.its`](../../../boards/aes/fit/rk3506-mainline.its)，100% 照搬原厂已经跑通的 FIT 结构，只把 uboot 节点里那块二进制换成主线编出来的 `u-boot-nodtb.bin`。这一步把一个模糊的 hash 问题收敛成了可操作的复刻路线，是整个方案 B 最值钱的发现。

## 翻车二：TEXT_BASE 差了 6MB，还有 OP-TEE 到底跳哪里

结构上咱们照搬，但有一处是例外的，照搬了就崩。主线 `u-boot-nodtb.bin` 是按 `CONFIG_TEXT_BASE=0x00800000` 链接的，而原厂 FIT 里 uboot 的 load 写的是 `0x00200000`，差了整整 6MB。代码是按 `0x800000` 链接的，咱们却把它装到 `0x200000`，所有的绝对寻址全错，崩就成了必然。所以 ITS 里 uboot 的 `load` 得改成主线的 `0x800000`，不能盲抄原厂的 `0x200000`。

但这又引出一个让人睡不着觉的悬念。原厂的链是 `SPL → optee(0x1000) → 降 NS → 跳 uboot`，那 OP-TEE 跑完到底跳去哪个地址？如果它从 SPL 传进来的 loadable 信息里取地址（这是标准做法），那 SPL 把咱们的 uboot 装到 `0x800000`，OP-TEE 跳的就是 `0x800000`，链就自洽了。可如果 OP-TEE 把跳转地址硬编码成原厂 FIT 里那个 `0x200000`，那咱们 `0x800000` 的代码就跳空了、当场崩。问题在于 `tee.bin` 是 rkbin 预编译的 blob，源码根本不在咱们手里，这个跳转地址咱们事前没法确定，咱们只能在板子上试。

实测的结果让咱们松了口气：串口里清清楚楚打出的就是 `I/TC: Next entry point address: 0x00800000`，OP-TEE 走的是标准做法、从 loadable 取地址，而不是硬编码。这个悬在咱们头上好几天的最大风险，被一行 log 打消了。

## 翻车三：banner 出来了，却 hang 在 misc_init_r

咱们照上面改完、烧到板上，`U-Boot 2026.07-rc4` 的 banner 终于蹦出来了。咱们刚要庆祝，紧接着来的就是一盆冷水：`initcall misc_init_r() failed`，然后甩出的是 `### ERROR ### Please RESET the board ###`，死在了那里、进不了提示符。

banner 都出来了它还崩，这样的毛病最磨人。咱们顺着 `misc_init_r` 往里挖，根因链是这样的：`misc_init_r` 要调的 `rockchip_cpuid_from_efuse` 会去读 SoC ID，它内部的 `uclass_get_device_by_driver` 去找 OTP 设备。可咱们的最小 dtsi **根本没给 OTP 节点**，于是找不到设备、返回的是 `-ENODEV`，一路链式地失败下去，而 U-Boot 的 initcall 机制对返回非 0 的回调默认是 hang，直接卡死了。

有意思的是，主线那个 OTP 驱动其实**已经认得** `rockchip,rk3506-otp`（它共用 rk3568 的读法），缺的只是 DT 里那个节点和它的物理地址。rk3506 的 OTP 基地址不在主线 dtsi 里，最后是从原厂 dtb 的预处理产物里抠出来的：`0xff4f0000`。于是咱们给 dtsi 补上 `otp@ff4f0000`，照主线 rk3528 的最小写法（不带 clocks、实测也不需要），重编了再烧到板上，这次 `SoC: RK3506B` 顺顺当当地打印了出来，意味着 OTP 读到了、`misc_init_r` 过了，板子稳稳地停在 `=>` 提示符。主线 U-Boot 从上电一路跑到了交互 shell。

## rkbin 的三条隐性约定：入门税

咱们把上面这些翻车连同打包烧录时踩的那些归拢起来，其实就是闭源 rkbin SPL 给咱们立下的三条约定，完整的记录详见 [pitfalls/01](../../pitfalls/01-rkbin-spl-contracts.md)，这里只浓缩地讲一遍。

**第一条约定管的是 chip tag**。打包出来的 `update.img` 头里有一个 chip tag，烧录前工具会拿它跟 loader 里写死的 `CHIP_NAME` 比对，对不上的话当场拒烧。麻烦在于 RK3506B 这颗 loader 的真实名字其实是 `RK350F`、真的不是 RK3506，咱们要是手滑硬编一个 `-RK3506`，tag 就对不上了，工具当场翻脸不认人（[`RKBOOT-RK3506B-aes.ini`](../../../boards/aes/RKBOOT-RK3506B-aes.ini) 第 13 行的 `NAME=RK350F`）。正解的做法是**永远从 loader 动态读这个 tag**：`RK$(dd if=loader bs=1 count=4 skip=21 | rev)`，咱们别图省事硬编。

**第二条约定管的是 OP-TEE 的 hash**。被 SPL 的 verified boot 拿 sha256 锁住的，只有 optee 节点的那颗 tee.bin，uboot 与 fdt 是不在校验范围的。方案 B 阶段咱们借的是原厂 SPL，它锁的 hash 对应 tee v2.10（`93603ca22c...`）。咱们要是把 tee 换成公开仓里的 v2.40，hash 算出来的就变成了 `616f8152...`，SPL 当场报出的就是 `optee Bad hash`，[boot-sdl-202606152121](../../logs/boot-sdl-202606152121.txt) 的记录里，整个翻车现场都在里面了。所以当时 tee 必须锁定在 v2.10。

> 这里咱们得诚实交代一句后续：后来咱们把整条 loader 都换成了公开 rkbin，也就是 SPL v1.12 加 tee v2.40 的组合，换出来的全公开链自洽、板上能跑。所以“必须 v2.10”是方案 B 借原厂 SPL 阶段的约定，而不是普适的真理。但那是打包纯化阶段的事了，方案 B 当时锁的就是 v2.10。

**第三条约定管的是 FIT 的字节布局**。就算咱们 tee 用对了 v2.10，只要这个 FIT 是用主线 `mkimage -E` 打的，optee 报的照样是 Bad hash，只不过这一次的 hash 变成了 `7b78fe4e...`，现场就是 [boot-sdl-202606152144](../../logs/boot-sdl-202606152144.txt) 的记录。原因其实很阴：主线 mkimage 和原厂 mkimage 的参数都叫 `-E`（external data），但两者的外部数据**字节布局不一样**，原厂 SPL 按它自己的那套布局硬读 optee 节点，读错位了，sha256 算的是错位的字节，当然不等于期望值。所以 uboot FIT 必须用原厂那颗 2017.09 的 mkimage 打。这是 rkbin SPL 收的一笔“隐性税”。

> 这里咱们同样诚实补一句。后来咱们用纯 Python 写了 [fit-pack.py](../../../src/forge/tools/fit_pack.py)，把原厂 mkimage 那套 SPL 兼容的字节布局复刻了出来，才算彻底摆脱了原厂的 mkimage。但方案 B 那会儿老老实实用原厂 mkimage 是最快的路。

咱们把三条约定看下来，它们的本质是同一件事：rkbin SPL 是闭源的，它的 chip tag 表、verified boot 锁的 hash、读 FIT 的字节布局，全是它单方面定下的约定，咱们只能对齐、改不动。主线侧真正自由的只有 kernel FIT，它是主线 U-Boot 加载的，根本不经 SPL 的 verified boot。想摆脱全部三条的话，唯一的办法是换掉 rkbin SPL，那是远期的事，这一章咱们交的正是那笔“入门税”。

## 把镜像凑出来，烧到板上

约定讲完了，咱们说说怎么把东西真的弄进板子。forge 现在的打包分几步：[pack-loader.sh](../../../scripts/pack-loader.sh) 用 Rockchip 的 `boot_merger` 从公开 rkbin 把 loader/idblock 打出来（DDR + usbplug + SPL），[pack-fit.sh](../../../scripts/pack-fit.sh) 打 uboot 的 FIT，最后 assemble 成一个完整的 `update.img`。诚实地讲，方案 B 那会儿咱们混着用的是原厂 mkimage、boot_merger 加手写 ITS，后来才一点点地纯化成了 fit-pack.py 加全公开 rkbin，纯化的过程是另一条弧线，这一章讲的是 bringup 过程，混着用是没有毛病的。

烧录的路有两条，走哪一条的依据是板子从哪儿启动。这块 RK3506B 实测是 **SPI-NAND 排在前头**启动的，依据是 [notes/01](../../notes/01-2026-06-14-vendor-uboot-build-flow.md) 的 Stage 3 验证。SD 卡咱们裸写一个镜像进去、bootrom 根本不选，转头就去起 NAND 里出厂烧进去的原厂系统。所以主线落地走的是 NAND，咱们用 RKDevTool 把 `update.img` 烧进板载的 SPI-NAND（chip tag 对得上的话才烧得下去，对应的是上面第一条约定）。SD 卡这一路咱们留作开发和恢复用的第二媒体，写卡用的是 [flash-sd.sh](../../../scripts/flash-sd.sh)，它用 `dd` 把 sd.img 写进了卡，这脚本是一堆安全检查裹出来的：拒绝写挂载着的设备、拒绝写系统盘、拒绝分区节点，写之前还非要咱们手敲一遍设备名确认，生怕咱们把宿主盘抹了。WSL2 的用户记得 SD 卡得提前走 `usbipd-win` 透传进来。

## 成功长这样

咱们交完三笔入门税、爬完四次翻车，板子上终于跑出了想要的那一行。下面这段是从方案 B 的里程碑 log（[boot-sdl-202606142052](../../logs/boot-sdl-202606142052.txt)）里截的，咱们一个字没合成：

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

每一行都值回了票价。`U-Boot 2026.07-rc4` 出的是主线的版本号，原厂那颗 2017 版的已经退场了。`SoC: RK3506B` 打印了出来，说明 OTP 读到了，`misc_init_r` 那个翻车已经填平了。`DRAM: 512 MiB` 是借来的原厂 DDR blob 点亮的内存。最后停在了 `=>`，意味着主线 U-Boot 从上电一路跑到了交互 shell。诚实的边界咱们还是要再强调一遍：它赖以运行的 DDR/SPL/OP-TEE 还是借的原厂 blob，它其实还不是纯主线 boot。但有了这块能跑的 U-Boot 当底座，下一章就能往上面塞内核了，看主线 Linux 认不认咱们亲手写的那块板级设备树、能不能一路跑到 `Starting kernel`。咱们 Ch3 见。
