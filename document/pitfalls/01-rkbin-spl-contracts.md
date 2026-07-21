# 01 — 跟 rkbin SPL 死磕:三个绕不开的隐性契约(chip tag / optee hash / FIT 布局)

> **更新(2026-06-17,P1):坑 #2"tee 锁定 v2.10"是方案 B(借 vendor SPL)时期的规矩。当前默认链已是全公开 rkbin——SPL v1.12 + tee v2.40,板上验证启动([notes/13](../notes/13-2026-06-17-p1-rkbin-public-loader-conquest.md) + [blobs.md](../blobs.md))。"必须 v2.10"仅适用于继续走 vendor SPL 的链。坑 #3 的 vendor mkimage 也已由 [scripts/fit-pack.py](../../scripts/fit-pack.py) 消除(P4)。正文保持方案 B 时期原样(诚实历史)。**

说实话,把 RK3506B 从 MaskROM 一路拽到主线 Linux 的 UART 提示符,最难的真不是写代码——主线 pinctrl、clock、SFC 驱动、主线 U-Boot 这些开源件早就齐活了。真正折磨人的,是夹在中间那颗闭源的 rkbin SPL:它在咱们拿到控制权之前,先替咱们把规矩定好了,而且一条都不写在文档里。这篇就是笔者跟这三条隐性契约死磕的完整记录——chip tag、optee 的 hash、还有 FIT 的字节布局,一个比一个阴,每一个都让笔者在串口前多坐了半天。

先把环境摆清楚,方便咱们对照复现:板子是 RK3506B 的 aes 板,SPI-NAND 是 W25N04KV(4Gb、on-die ECC)挂在 SFC@0xff488000;U-Boot 跑主线 2026.07-rc4,内核主线 7.1;而那个甩不掉的 rkbin loader(MiniLoaderAll.bin)负责在 MaskROM 阶段把各分区写进 NAND。整条链子是 `ROM → rkbin → U-Boot → Linux`,rkbin 这一环闭源,后面所有别扭的根源都在它身上。

这三条坑看着各管各的(chip tag 是烧录工具的事、optee hash 是启动校验的事、FIT 布局是打包格式的事),根子却是同一个:rkbin SPL 闭源,它的 chip tag 表、verified boot 锁的 hash、它读 FIT 的字节布局,全是它单方面定的契约,我们只能对齐、改不了。主线侧能动的只有 kernel FIT(由主线 U-Boot 加载,不走 SPL verified boot)和 U-Boot 自身;真不能动的是 uboot FIT、chip tag、还有那颗 tee 的 hash。

## 第一步就翻车:连芯片都校验不过

事情从打包 update.img 开始。笔者用 afptool 把分区凑好、RKDevTool 选「升级固件」一把烧——结果工具直接甩笔者一脸「校验芯片失败,请使用工具生成」,烧都烧不下去。

一开始笔者是往镜像结构上怀疑的:是不是 parameter 表写错了?afptool 打包参数不对?又被旧日志里 vendor 残留 uboot 那个 `#alientek` banner 带偏,折腾了半天怀疑是 idblock 没烧进去。直到笔者老老实实把 vendor 的 update.img 解包、再去啃 vendor 的 `mk-updateimg.sh`,才发现 RKFW 头里藏着一个 chip tag,而 RKDevTool 烧录前会拿它跟 loader 的真实 `CHIP_NAME` 比对——对不上,直接拒。

这里的关键机制是这样的:RKFW 头的 chip tag 必须跟 loader 里写死的 CHIP_NAME 一致,而 RK3506B 这颗 loader 的 CHIP_NAME 实际是 `RK350F`(对,不是 RK3506),咱们要是手滑硬编一个 `-RK3506` 进去,tag 就跟 loader 对不上,工具当场翻脸。所以正解是**永远从 loader 动态读这个 tag**,别硬编:

```
# assemble-update.sh —— chip tag 从 loader 的 offset 21 读 4 字节、反转
TAG="RK$(dd if="$LOADER" bs=1 count=4 skip=21 status=none | rev)"
```

这写法是照搬 vendor `mk-updateimg.sh` 的权威做法。loader 的真实名记在 [RKBOOT-RK3506B-aes.ini](../../board/aes/RKBOOT-RK3506B-aes.ini) 里,第 13 行 `NAME=RK350F` 就是铁证;而 vendor 自己那个 `rockdev/rk3506-mkupdate.sh` 把 RK3506 写死,只是图省事的简化脚本,千万别拿它当参考。

⚠️ 这一步千万别偷懒硬编 `-RK3506`:chip tag 永远动态读,认准 `RK$(dd if=loader bs=1 count=4 skip=21 | rev)`。改好之后 RKDevTool 不光校验过了,连 idblock 也一并烧进了我们的 loader,分区这才齐活。

## 镜像烧进去了,结果 optee Bad hash

chip tag 修好、镜像总算烧下去了,笔者以为能松口气——结果上板一看,rkbin SPL 在 verified boot 阶段直接报 `optee Bad hash`,拒绝我们的 FIT,然后它居然回退去捡 NAND 里残留的 vendor uboot(那颗 uboot 配的是 tee v2.10),vendor uboot 又引不动主线 kernel,整板挂死。

这一坑笔者一开始是怪错对象的。早期(note01/04)我一直用 explore/rkbin 的 `rk3506_tee_v2.40.bin` 打 uboot FIT,因为 vendor SDK 默认 ini `RK3506TOS.ini` 里 `TOSTA` 就指向 v2.40,打包脚本照搬嘛。方案 B 阶段我还一度误判成「vendor SPL 不认主线 FIT 的 hash 结构」,后来才想明白一个关键区别:

> uboot 节点是 loadable、不被 hash 锁;**唯一被 SPL verified-boot 锁的,就是 optee 节点那颗 tee.bin 的 sha256。**

换句话说,咱们换 v2.40,等于直接撞 SPL 的 hash 锁。板上串口把这个过程记得清清楚楚,[boot-sdl-202606152121.txt](../logs/boot-sdl-202606152121.txt) 第 26 行:

```
Trying fit image at 0x2000 sector
## Verified-boot: 0
## Checking optee 0x00001000 ... sha256 Bad hash: 616f8152e41d6b245d6cd9a818c9b8a59d7612af6145f3071822dccb09a01c10
 error!
Bad hash value for 'hash' hash node in 'optee' image node
Trying fit image at 0x3000 sector
## Verified-boot: 0
## Checking optee 0x00001000 ... sha256(93603ca22c...) + OK
## Checking uboot 0x00200000 ... sha256(9d237e6721...) + OK
```

你看,先试 0x2000 那个 fit(我们打的、配 tee v2.40),optee hash 算出来是 `616f8152...`,SPL 不认,`error!`;接着它去试 0x3000 那个(残留的、配 tee v2.10),optee hash 是 `93603ca22c...`,这回 `+ OK`,uboot 也跟着过了。这个 `93603ca22c...` 正是 v2.10 的 sha256,也是 SPL 唯一认的值。所以正解很干脆——uboot FIT 的 tee 节点固定用 vendor-sdk 的 `rk3506_tee_v2.10.bin`(125904 字节,sha256=`93603ca22c...`)。

⚠️ tee 千万别"升级"到 v2.40。[pack-fit.sh](../../scripts/pack-fit.sh) 里我专门留了注释 `# tee MUST be vendor v2.10 … Do NOT "upgrade" to v2.40.`,就是怕后来人手贱。记住:uboot 是 loadable 不被锁,**唯一要匹配 SPL verified boot 的就是这颗 tee**;kernel FIT 由主线 U-Boot 加载、根本不经 SPL verified boot,不受这条约束。

## tee 对了还是 Bad hash——这次是 mkimage 的锅

到这里事情还没完,真正的坑在后面。笔者把 tee 换成 v2.10 了,满以为 optee 能过——结果上板,optee 还是 `Bad hash`,只不过这次 hash 值变了,变成了 `7b78fe4e...`。同一颗对的 tee,怎么还能 Bad hash?

这条是上一条的姊妹坑,极易混淆,笔者又绕了一圈才搞明白:问题不在 tee,在**打包它的 mkimage**。我之前用的是主线 `tools/mkimage -E` 打 uboot FIT,而主线 mkimage 的 `-E` external-data 布局,跟 vendor mkimage 的 `-E` 布局不一样;vendor SPL 是按它自己那套布局硬去读 optee 节点的,布局错了就读错位,sha256 算的是错位的字节(`7b78fe4e...`),当然不等于期望的 `93603ca22c`。所以即便 tee 用对了 v2.10,只要 FIT 是主线 mkimage 打的,optee 照样 Bad hash。

板上证据在 [boot-sdl-202606152144.txt](../logs/boot-sdl-202606152144.txt) 第 26 行,和上一条几乎一模一样的剧情,只是 hash 值换成了 `7b78fe4e`:

```
## Checking optee 0x00001000 ... sha256 Bad hash: 7b78fe4ee6db98cd7ebd662e4c9dd8182c6f7a01007c6ff961bc8c4b82775269
 error!
Bad hash value for 'hash' hash node in 'optee' image node
...
## Checking optee 0x00001000 ... sha256(93603ca22c...) + OK
```

这个 `7b78fe4e` 笔者在 [pack-fit.sh:77](../../scripts/pack-fit.sh) 的注释里也原样记了下来,就是主线 mkimage 错位读到的值。最后正解是:uboot FIT **永远用 vendor-sdk 的 `u-boot/tools/mkimage`(2017.09) `-E` 打**,结构跟 vendor SPL 字节级对齐;[rk3506-mainline.its](../../board/aes/fit/rk3506-mainline.its) 里 optee/fdt 节点的 load 和结构都照搬 vendor 已经跑通的布局,只把 uboot 的 load 改成主线的 `0x00800000`(TEXT_BASE)。打完上板,[boot-sdl-202606142037.txt](../logs/boot-sdl-202606142037.txt) 里三个节点(optee/uboot/fdt)全是 `+ OK`,FIT 这才被 SPL 放行。

⚠️ uboot FIT 别用主线 mkimage,认准 vendor-sdk 那颗 2017.09 的;kernel FIT(boot.img)才是由主线 U-Boot 加载,主线 mkimage 随便用。这条本质是 rkbin SPL 收的隐性税,不是 FIT 标准的锅,所以中途 note08/note09 我一度以为"主线 mkimage 格式级兼容、能替代"——双向 `mkimage -l` 解析都 OK 嘛——结果一上板就翻车,格式兼容不等于 SPL 认。真要彻底摆脱,得换掉 rkbin SPL、用主线 U-Boot 自己的 SPL 再关掉 verified boot,那是后话了。

## 三个契约,统一说一句

回头看这三条,其实就是闭源 SPL 给我们立的三个规矩:chip tag 得是 `RK350F`(#1,从 loader 动态读)、optee 的 hash 得是 v2.10 那个 `93603ca22c...`(#2,tee 锁定 v2.10)、FIT 的字节布局得是 vendor mkimage 2017.09 那套(#3,uboot FIT 用 vendor mkimage 打)。主线侧唯一自由的只有 kernel FIT。这三条都是我们对 rkbin 这层黑盒的让步,暂时照办;等哪天真要干净掉(note12 的 P4),换掉 rkbin SPL 才算数。

完结撒花,这篇算是把 boot 链的"入门税"交清楚了。下一篇我们去啃最硬的那块骨头——SPI-NAND 的读写和 loader 写弱 rootfs 的完整 saga,那才是真正让我血压拉满的一段。
