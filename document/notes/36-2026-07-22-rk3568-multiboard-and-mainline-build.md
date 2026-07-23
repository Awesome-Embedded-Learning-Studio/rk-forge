# 36 — RK3568 上板：多板框架 + 主线 kernel/uboot/binman 打通

**2026-07-22**（~23）。这篇记 RK3568 作为 rk-forge 第二块板的奠基：把单板硬编码重构成多板框架，然后验证 RK3568 在主线（linux v7.1 + 主线 U-Boot）下 kernel + uboot + loader 都能编出来、且 loader/uboot 由 **binman 自产、不靠 vendor 工具**。关联 [[35]]（OpenWrt rootfs 流，aes 的）；完整交接见记忆 `rk3568-migration-status` / `rk3568-mainline-driver-map` / `rk3568-build-gotchas`；计划在 `.claude/plans/concurrent-baking-dewdrop.md`。

## 一句话定位

RK3568 走**主线优先**（不是 vendor BSP）：SoC/GPU(Panfrost)/VPU(Hantro+rkvdec2)/RGA/camera 全主线，**只有 NPU 是例外**（主线 Rocket 只 RK3588，RK3568 要移植 vendor rknpu2 + 闭源 librknnrt，用户拍板的唯一不干净点）。这次把"框架能不能多板化、RK3568 主线能不能编、loader/uboot 能不能不靠 vendor 工具"三个最不确定的全验证了。

## 三个 commit（都验证过）

- **`d0e8724` 多板框架**：`config/boards/<board>.env` 板注册表 + `forge.sh --board=<id>` 选择层 + 8 个 build/pack 脚本参数化（rkbin/build-linux/build-uboot/build-rootfs/pack-loader/pack-fit/assemble-update/forge stage）+ patches/pins 每板一份（`patches/aes/`、`pins/aes/`，共享 pin 留扁平）。aes 回归门 `forge.sh --board=aes all` 通过（RK3506 没碰坏，update.img 自检过）。
- **`9d600e9` rk3568-atk 脚手架 + 框架补全**：源码树每板一份（`src/<board>/`）、toolchain/KERNEL_FRAGMENTS/WIFI_DRIVER 板驱动、u-boot `ARCH=arm`。主线 v7.1 kernel 编出 `Image` + `rk3568-evb1-v10.dtb`（主线本就有这颗 DDR4 V10 板的 dts，MVP 零 patch）。
- **`d783172` binman blob 接线**：RK3568 的 loader（`idbloader.img`）+ uboot（`u-boot.itb` 带 BL31/ATF）由主线 uboot binman 自产，**零 vendor 工具**（比 aes 干净——aes 还要 boot_merger）。

## 踩的坑（都在记忆 `rk3568-build-gotchas`）

- **u-boot `ARCH=arm`**：u-boot 用统一 `arch/arm/` 编 arm32 和 arm64（没有 `arch/arm64/`）。rk3568-atk 是 arm64 *内核*（`ARCH=arm64`）但 u-boot 要 `ARCH=arm`；arm64/armhf 的区分只在 `CROSS_COMPILE`。build-uboot.sh 强制 `ARCH=arm`。
- **binman 要 `BL31` + `ROCKCHIP_TPL`** 环境变量（从 rkbin），才把 ATF + DDR 嵌进 `u-boot.itb`/`idbloader.img`。**TEE/bl32 省略**：rkbin 的 bl32 是裸 `.bin`，binman 的 tee-os 要 ELF（magic 不符）；OP-TEE 启动非必需，binman 报 "missing optional blob: tee-os" 照样产出可用的 u-boot.itb（带 BL31）。
- **swig**：主线 uboot 编 pylibfdt 要 `apt install swig`，否则 "command 'swig' failed"。
- **WSL PATH 空格**：buildroot 拒绝 PATH 里的 `/mnt/c/Program Files/...`（`build-rootfs.sh` 用 `forge_clean_path`）。
- **flaky gitlab.denx.de**：u-boot 全 clone 超时；从已有 uboot 树本地 clone + checkout pin 秒级搞定。

## 主线驱动现状（2026-07，linux v7.1；详见记忆 `rk3568-mainline-driver-map`）

GPU=Panfrost（替 libmali）、VPU=Hantro+rkvdec2（含 HEVC，替 mpp）、RGA、RKCIF、SoC 外设+音频全主线。**唯一缺口 NPU**：主线 Rocket 只 RK3588，RK3568 的 NPU 是不同 IP → 移植 vendor GPL rknpu2 到主线 + 闭源 librknnrt.so（用户决策：NPU 是这块板存在的理由，接受这一处不干净）。

## 还差啥（MVP：可烧 eMMC update.img → 启动到 shell）

1. `boot.img`（kernel FIT）：pack-fit 建 arm64 的 `rk3568-kernel.its`，**且对 binman 板跳过 uboot 重打包**（RK3568 的 uboot 已是 binman 的 `u-boot.itb`，不能再 fit-pack 一遍）。
2. `rootfs.ext4`：buildroot `rk3568_atk_defconfig`（aarch64 + /opt 工具链 + busybox）+ pack-emmc（`mke2fs`）。
3. eMMC assemble：`assemble --emmc`（GPT + ext4，**不用** aes 的 NAND/ubiprog）+ `parameter-emmc-atk.txt` + `package-file-emmc.txt`。
4. `forge.sh --board=rk3568-atk all` → update.img（host 可验）；上板启动硬件 gated。

MVP 之后才叠：驱动 defconfig fragments、NPU 移植、buildroot 全包、`document/sdk-diff-rk3568.md`、openwrt profile。

## 一个判断

最难的不确定项（多板能不能抽象干净、RK3568 主线能不能编、loader/uboot 能不能甩开 vendor 工具）这次全过了。剩下的是机械活 + 一个 pack-fit/assemble 对 binman 流的适配，没有未知风险。
