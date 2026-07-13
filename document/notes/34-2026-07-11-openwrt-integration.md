# 34 — OpenWrt 移植进 rk-forge(--rootfs=openwrt profile)

**2026-07-11**。朋友委托:把 OpenWrt 移植进 rk-forge,目标板 aes(RK3506B SPI-NAND)。

## 架构决策:选项 A

OpenWrt **自建 kernel + rootfs**(保住 opkg/LuCI/kmod 完整体验,vermagic 天然匹配),rk-forge 负责 RK 专属打包(mainline U-Boot + rkbin + fit-pack.py + rkfw-pack.py,全部板验过、零 vendor-sdk)。buildroot profile **共存**(默认),`--rootfs=openwrt` 切换。rootfs 分两阶段:Phase 1 UBIFS 可写根(复用 pack-ubifs),Phase 2 squashfs-on-UBI。

外部仓库 `czz8888/rk-3506-openwrt-7.1@31d15c0` 已逐字搬了 rk-forge 的 16 个内核补丁(quilt patches-7.1/),内核侧活干了一半。

## 四个 seam

| seam | buildroot | openwrt |
|---|---|---|
| 源 | linux/uboot/buildroot fetched-clone + git-am | + openwrt fetched-clone(quilt 管 kernel 补丁,git-am 只管 Device/aes overlay) |
| kernel 产物 | `$LINUX_DIR` | `KERNEL_ARTIFACT_DIR` → OpenWrt build_dir(forge.sh stage_pack 解析) |
| rootfs 树 | 解 buildroot rootfs.tar | rsync OpenWrt TARGET_DIR(kmod 已在 lib/modules/) |
| 打包链 | fit-pack / pack-loader / pack-ubifs / rkfw-pack | **完全相同,零改动** |

## 实现(commit f3e09de)

**新增**:`pins/openwrt`、`patches/openwrt/{series,0001-...add-aes-nand-device.patch}`、`scripts/build-openwrt.sh`、`board/aes/openwrt/{aes-nand.config,README.md}`
**改**:`fetch-deps.sh`(加 openwrt target,`all` 不含它)、`forge.sh`(--rootfs flag + setup/build/pack 分流)、`lib/env.sh`(OPENWRT_DIR + KERNEL_ARTIFACT_DIR)、`forge.env`(OPENWRT_TREE)、`stage-rootfs.sh`(按 profile:rsync TARGET_DIR / 解 rootfs.tar)、`pack-fit.sh`(zImage+dtb 读 KERNEL_ARTIFACT_DIR,默认 LINUX_DIR)

## 关键坑(实现中踩的)

1. **patch hunk header 行数错** → device 块被 git-am 截断。手写 `@@ -55,4 +55,17 @@` 但实际 added 16 行(该 +55,20),git-am 按行数读,丢掉 `BOOT_FLOW/endef/TARGET_DEVICES += aes_nand` → aes_nand 不进 `.targetinfo` → defconfig 选 Default,device 全不注册。**修**:`git format-patch -1` 让 git 自己算行数。
2. **arg parser flag 在 subcommand 后失效** → `forge setup --rootfs=openwrt` 走 buildroot 分支。**修**:break 后加第二循环 re-scan flags。
3. **world -j14 跨阶段竞态** → `make world` 把 package/cleanup + target/linux/compile 并行,稳定 fail。**修**:build-openwrt.sh **分阶段 build**(每阶段 -j14,阶段间顺序)。
4. **LINUX_DIR env 污染** → build-openwrt.sh source lib/env.sh export LINUX_DIR=rk-forge patched 树;OpenWrt `LINUX_DIR ?=` 让 env 赢 → 在 rk-forge 已 patched 树上 quilt-apply patches-7.1 → 冲突。**修**:`env -u LINUX_DIR`(OpenWrt 用自己 build_dir/linux-7.1)。
5. **OpenWrt cmd() silent 假失败** → `make -s` + fd 重定向在 -jN 下误判 fail(kernel 实际编成功,产物在)。**修**:build_stage 全程 `V=s`(verbose → per-stage log)。
6. **stage 顺序** → target/linux/install 产 rootfs image 要 TARGET_DIR(package 建),不能在 kernel stage。**修**:stage 2 只 compile,install 移 stage 4(package 后)。
7. **子进程不继承 ROOTFS_PROFILE** → stage-rootfs.sh 是子进程,forge.sh 没 export → 默认 buildroot。**修**:forge.sh `export ROOTFS_PROFILE`。
8. **find 路径/名字** → OpenWrt kernel 在 `build_dir/target-*/linux-rockchip_rk3506/linux-7.1`(非 `build_dir/linux-rockchip_rk3506`);TARGET_DIR 是 `root-rockchip`(非 root-rk3506)。**修**:find 用正确路径/名字。
9. **PSCI 不预判挂死**:OpenWrt 上游 HEAD 挂死是它**自己的 uboot 加载 OP-TEE**;rk-forge 主线 uboot 不加载 OP-TEE,aes 单核。→ 首验**不改** PSCI config;`patches/openwrt/0002` 条件性备用。

## 验证状态

- ✅ buildroot profile pack + assemble 不回归(initramfs 1.2MB,boot.img 9.4MB,round-trip OK)
- ✅ openwrt setup/build 全链路(zImage 7.27MB + aes.dtb + musl rootfs 9.3MB)
- ✅ **NAND 板验通**(update-openwrt-fromsrc-20260712.img):ubiprog from-source(erase 全 mtd5 + 写 RAM image,wrote≈76 erased_tail≈1316)→ OpenWrt shell
- ✅ **OpenWrt on SD 板验通**(update-openwrt-sd-thumb2-20260712.img):`forge assemble --rootfs=openwrt --sd`(复用 pack-sd,零新代码)→ kmodloader 0 failed + procd + OpenWrt 24.10 shell
- ✅ **差异化 provisioning**(b8dea9e):openwrt from-source(内嵌 image)/ buildroot read-modify-write(rootfs 23MB 超 boot 16MB)

## 待办

- [x] 全量 build 产出 zImage + aes.dtb + TARGET_DIR → forge pack/assemble → update.img(27.9MB)
- [ ] **板验**(头号风险 PSCI):板启 OpenWrt shell + opkg + RW + wifi
- [ ] Phase 2:squashfs-on-UBI(pack-squashfs-ubi.sh + sysupgrade)
- [ ] fork czz8888 → Awesome-Embedded-Learning-Studio(pins/openwrt 改指 fork,稳定性)
- [ ] buildmeter openwrt parser(Phase 1 复用 kind=kernel)

## 用法

```bash
forge setup --rootfs=openwrt     # fetch openwrt + apply overlay
forge build --rootfs=openwrt     # OpenWrt kernel+rootfs + rk-forge uboot
forge assemble --rootfs=openwrt  # → board/aes/out/update.img
forge all --rootfs=openwrt       # 一条龙
```

关联:[[forge-remaining-work-roadmap]] [[kill-vendor-sdk-roadmap]]。详见 plan:把 OpenWrt 移植进 rk-forge。
