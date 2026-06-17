# 13 — P1 第一刀 rkbin:全公开 loader + 纠正"公开仓有 v2.10"的前提

> 2026-06-17。P1(源码层零 vendor_sdk)开干,第一刀 rkbin。**原计划基于 note 12
> 的前提("公开仓有 rk3506_tee_v2.10")——核实后前提错误**,本刀的实际做法与
> note 12 的预想不同,但目标(不再下笨重 SDK、用公开源灵活调整)反而更彻底达成。

## 前提纠错:公开仓从来就没有 v2.10 / v1.02 / v1.11

note 12 表格说"rkbin→公开仓 submodule,**已验版本对**:tee v2.10 都在"。**核实打脸**:
对 `third_party/explore/rkbin`(= `github.com/rockchip-linux/rkbin` clone)翻**全部 git 历史**:

```
$ git log --all -- 'bin/rk35/rk3506_tee_v2.10.bin'   → (空,从未存在)
$ 全历史 tee 版本:rk3506_tee_v2.40.  (只有 v2.40)
$ 全历史 usbplug:v1.03;  SPL:v1.12.   (没有 v1.02 / v1.11)
```

板子验证过的 loader 是 **ATK 快照**:DDR v1.06 + usbplug **v1.02** + SPL **v1.11** + tee **v2.10**。
其中 usbplug/SPL/tee 三个版本公开仓**从未有过**——是 ATK-BSP 专有快照,公开仓只有更新的
v1.03/v1.12/v2.40。DDR v1.06 两边一致。

## 纠正 sfc-dll-saga 的"v2.40 板致命"结论

saga 说"tee 用 v2.40 → 必 v2.10(vendor SPL 验 optee hash)"。这条结论**有条件**——它成立
的前提是**混搭**:ATK 的 SPL **v1.11**(内置 v2.10 的 hash)去验公开的 tee v2.40,当然 Bad hash。

**全公开链路不混**:公开 SPL **v1.12** 是 Rockchip 当年和 tee **v2.40** 一起发布的,内置的就是
v2.40 自己的 hash → 验 v2.40 匹配。SPL↔tee 是按 hash 配对的(SPL 内置期望 hash,tee 是 FIT 里的
loadable;uboot 也是 loadable 不 hash-lock,所以**唯一要跟 SPL 配对的就是 tee**)。

→ 真正该攻克的不是"换 tee 版本",而是"**整条 loader 链全公开、不混**"。

## 做法征服(全公开 loader,零 vendor-sdk)

| blob | 公开仓有 | 角色 |
|---|---|---|
| DDR `rk3506b_ddr_750MHz_v1.06.bin` | ✅(同版) | loader CODE471/FlashData |
| usbplug `v1.03` | ✅ | loader CODE472(MaskROM USB 烧录用,不影响 NAND 启动) |
| SPL `v1.12` | ✅ | loader FlashBoot(做 verified boot,验 tee hash) |
| tee `v2.40` | ✅ | 进 uboot FIT(pack-fit.sh),被 SPL v1.12 验 |

`third_party/rkbin` 从"假 submodule"(.gitkeep 占位,.gitmodules 声明但无 gitlink)做成**真
gitlink**,pinned `ecb4fcb`。`pack-loader.sh` / `pack-fit.sh` 默认指向它,boot_merger 也恒用公开
submodule 的(packer 版本无关)。**build 验证**:默认全公开 loader 一次拼出 →
`MiniLoaderAll.bin` 281024 B,全程零 vendor-sdk。

## ATK 保险绳(`third_party/rkbin-atk/`,committed 本地存档)

三个 ATK 快照 blob 没法从公开源 fetch(只在 SDK 源码分发里),所以**直接 commit 进
`third_party/rkbin-atk/`** 当本地存档(372K),而不是写 fetch 脚本(fetch 还得拴 vendor-sdk,没真脱钩)。
`FORGE_RKBIN_DIR=third_party/rkbin-atk` 一行回到 ATK 版本(DDR v1.06+usbplug v1.02+SPL v1.11+tee v2.10)。

**⛔ 不 push 到 origin**(redistribution 权属不明,见 BLOBS.md Licensing)。公开 loader 板验通过后
删掉这个目录,征服才算收尾。

两个 variant 的 SPL↔tee 配对已验自洽:
```
[public]  spl=rk3506_spl_v1.12.bin   tee=rk3506_tee_v2.40.bin   → 自洽
[atk]     spl=rk3506_spl_v1.11.bin   tee=rk3506_tee_v2.10.bin   → 自洽(已知能起)
```

## 还没验 / 残留

- **✅ 公开 loader 板上通过(2026-06-17)** —— log `document/logs/boot-sdl-202606171200.txt`:
  公开 SPL v1.12 + tee v2.40,optee `sha256(e2a712a533...) + OK` 两轮冷重启稳定;ubiprog 首启抓到
  PEB 3/4 `full-read uncorrectable`(loader 弱写实证)并页级恢复,`cat /persist.log`=`c1 44` 跨冷重启存活。
  → 征服终极确认 + ubiprog 解法对公开 loader 同样成立(loader 版本无关)。详见 [[sfc-dll-saga-and-writepath]]。
- **rkbin 这刀的 build 路径已零 vendor-sdk**(grep 确认:pack-loader/pack-fit 里除 P4 vendor mkimage 外无 vendor-sdk rkbin 引用)。
- **P1 另两刀 deferred**(用户指示):toolchain 后续拉**更高版本编译器**再做(现在 vendor gcc 10.3 能编出能跑的,白下 10.3 没意义);busybox 随 toolchain 一起换 upstream。
- **残留 vendor-sdk build 依赖**(预期,各属后续阶段):P4 vendor mkimage(pack-fit.sh:35)、
  P2 afptool/rkImageMaker(assemble-update.sh:38)、deferred toolchain(mk-rootfs.sh:81 + toolchain.conf + initramfs/README.md)、纯参考 sdk-diff。

## 相关

note 12(评估 + 路线图,本文纠正其 rkbin 行)、`BLOBS.md`(闭源 blob 单一真相,rkbin 段已更新)、
`third_party/rkbin-atk/README.md`、[[sfc-dll-saga-and-writepath]](其"v2.40 致命"结论本文加条件)。
