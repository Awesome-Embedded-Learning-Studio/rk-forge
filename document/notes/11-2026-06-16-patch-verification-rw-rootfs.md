# 11 — patch 验证:RW rootfs 系列(linux 0001-0006 / uboot 0001-0004)真能用吗?

> 2026-06-16。RW UBIFS rootfs 在板上跑通 + PEB 3/4 页级恢复修好后,把全套
> patch 存档(linux 6 个、uboot 4 个)。本文记录"**这些 patch 到底对不对、能不
> 能从最干净的源码重新打起来**"的验证过程与结论,并说明现场如何保全(万一 patch
> 错了能重生)。

## 为什么要验证

patches/ 是 forge 的规范产物(explore/ 树 gitignore,不进主仓),主仓里 RW 这一
轮的全部改动只靠 patches/ + bringup/(ubiprog/init)承载。如果 patch 漏了/错了,
单看主仓无法发现 —— 必须把 patch 打到**最干净的上游**、重新构建,比对回 explore
原树,才能坐实"patch 完整、可用、可复现"。

## 现场保全(regeneration source of truth)

验证前先把"能重新生成 patch 的源头"锁死:

- explore 两树打 tag:`rkforge-rw-checkpoint`
  - `explore/linux`  → `34ae6be78`(base v7.1 = `8cd9520d3`)
  - `explore/uboot`  → `6b6be88c`(base rc4 = `5ca1a73c`)
- patches/ 由 `git format-patch <base>..HEAD` 从这两个 commit 生成;只要 tag 在,
  patch 永远能重生:`git -C third_party/explore/linux format-patch 8cd9520d3..rkforge-rw-checkpoint`。
- 主仓已提交 3 个 commit(`patches:` / `bringup:` / `logs:`),patches/ 进了 git
  历史。

→ **即便验证发现 patch 有问题,explore 树(tag)还在,重新 format-patch 即可。**

## 验证方法

对每个组件:**干净 worktree → 打全套 series → 逐字节比对源码 vs explore → 干净树构建 → 比对产物**。
全程不碰 explore 原树(用 `git worktree`)。

```bash
# linux
git -C third_party/explore/linux worktree add --detach /tmp/verify-linux 8cd9520d3
cd /tmp/verify-linux && /home/charliechen/rk-forge/scripts/apply-series.sh --component linux_mainline
# uboot 同理:worktree 5ca1a73c,--component uboot
```

## 结果

| 检查 | linux (0001-0006) | uboot (0001-0004) |
|---|---|---|
| 干净上游 | v7.1 `8cd9520d3` | rc4 `5ca1a73c` |
| `apply-series.sh` | **6/6 OK**,无冲突 → `fc576ff8e` | **4/4 OK**,无冲突 → `64d8b7b3` |
| 改动文件 vs explore(逐字节) | sfc.c / rk3506.dtsi / rk3506b-aes.dts **全部 IDENTICAL** | rockchip_sfc.c / rk3506-u-boot.dtsi **IDENTICAL** |
| 干净树构建 | zImage 7,356,928 B + dtb **成功** | (apply+源码已证;构建同 explore) |
| dtb vs explore | **`5b48b95e` 字节相同** ✓(dtc 确定性,无时间戳) | — |

**结论:patch 完整且可用。** 打在干净上游上的源码与 explore 原树**逐字节相同**;
干净树成功编出 zImage + dtb;dtb 与原树字节一致。

### 关于 zImage/vmlinux hash 不一致(不是 patch 问题)

干净树 zImage 与 explore 原 zImage **hash 不同,但大小相同**(7,356,928 B),vmlinux
各 section size 也相同(text/data/bss 全一致)。差异全在**非功能性元数据**:

- 内核版本 banner 的 git-describe:`00005-g453820219629-dirty`(explore,dirty 树编的)
  vs `00006-gfc576ff8ea68`(verify,干净 commit 编的)—— 两者源码相同,只是 commit 计数不同。
- 构建目录路径(嵌在 `__FILE__` / debug):`/tmp/verify-linux` vs `/home/.../explore/linux`。
- 构建时间戳。

这些不影响功能指令(同源码 → 同编译产物 → 同指令)。dtb 无这些元数据,故**字节完全
一致**。zImage(strip+XZ 压缩的部署产物)差异只在 banner 串;vmlinux(含 debug/符号)
差异更大但同样不部署、不影响功能。

要拿到**字节级可复现**的 zImage,需固定 `SOURCE_DATE_EPOCH` + 在相同路径下构建 —— 本
验证不需要(源码逐字节相同已是更强证明)。

## 怎么复现这次验证

```bash
cd /home/charliechen/rk-forge
# 1. 干净 worktree(不碰 explore 原树)
git -C third_party/explore/linux worktree add --detach /tmp/verify-linux 8cd9520d3
# 2. 打全套 patch
( cd /tmp/verify-linux && scripts/apply-series.sh --component linux_mainline )
# 3. 逐字节比对改动文件(应全 IDENTICAL)
for f in drivers/spi/spi-rockchip-sfc.c arch/arm/boot/dts/rockchip/rk3506.dtsi arch/arm/boot/dts/rockchip/rk3506b-aes.dts; do
  diff -q /tmp/verify-linux/$f third_party/explore/linux/$f && echo "OK $f"
done
# 4. 构建(用 explore 的 .config 保确定性)
cp third_party/explore/linux/.config /tmp/verify-linux/.config
TC=third_party/vendor-sdk/prebuilts/gcc/linux-x86/arm/gcc-arm-10.3-2021.07-x86_64-arm-none-linux-gnueabihf/bin/arm-none-linux-gnueabihf-
( cd /tmp/verify-linux && make ARCH=arm CROSS_COMPILE=$TC olddefconfig && make ARCH=arm CROSS_COMPILE=$TC -j$(nproc) zImage rockchip/rk3506b-aes.dtb )
# 5. 比对 dtb(应字节相同);zImage 比大小(应相同,hash 因时间戳不同)
# 6. 清理
git -C third_party/explore/linux worktree remove /tmp/verify-linux --force
```

uboot 同流程(`--component uboot`,base `5ca1a73c`)。

## 相关

- patches 主仓提交:`1b74109`(patches: regen) / `2d09be7`(bringup: ubiprog+init) / `6c924af`(logs)。
- 根因与修复全程:记忆 `sfc-dll-saga-and-writepath`(顶部 RW-SOLVED 段)、`bringup/nand-rootfs/RW-WRITE-FIX-powergood-wpen.md` + `BOARD-VALIDATION.md`。
