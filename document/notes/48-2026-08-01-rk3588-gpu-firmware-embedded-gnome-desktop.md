# 48 RK3588 GPU Panthor 固件内建 + GNOME 桌面 (2026-08-01)

接 [47](47-2026-08-01-rk3588-lcd-video-fix-tc358775-init-prepare.md)：LCD 视频通了（boot logo 出图），但 GNOME 桌面不显示。本篇记 GPU 固件这关。

## 症状

- LCD 视频正常（boot 企鹅 + fb0 噪点都显示）。
- GDM 起来了、gnome-shell 跑起来（PID 686），但**桌面黑**。
- `journalctl`: `gnome-shell: Failed to lock front buffer on /dev/dri/card0: gbm_surface_lock_front_buffer failed`（反复）+ `Failed to query buffer age, got error 3003`。
- `ls /dev/dri/` → **只有 card0，没有 renderD128**。

## 根因

- `renderD128` 是 GPU 渲染节点，Panthor（Mali-G610）probe 成功才创建。它缺 → mutter 没 GL/EGL → 拿不到 GBM front buffer → 桌面不渲染（fbcon/boot logo 不走 GPU 所以正常）。
- dmesg: `panthor: *ERROR* Failed to load firmware image 'mali_csffw.bin'`。
- 两个叠加坑：
  1. **时机**：Panthor `=y` 在 boot 早期 probe，那时 rootfs 还没挂 → `/usr/lib/firmware/arm/mali/arch10.8/mali_csffw.bin` 拿不到。
  2. **压缩**：rootfs 里是 `mali_csffw.bin.zst`，而 `CONFIG_FW_LOADER_COMPRESS` 没开 → 即使挂了也读不了 .zst。

## 修复：CONFIG_EXTRA_FIRMWARE 内建 raw 固件

forge 不做 `make modules_install`（只装 wifi .ko），所以 Panthor `=m` + 装模块的路子要加脚本步骤。**最省的是把 raw 固件内建进 kernel**：

1. 从 staged rootfs 取 `arch10.10/mali_csffw.bin.zst`（linux-firmware 包），`zstd -d` 解压成 raw（282 KB）。
2. 放 `board/rk3588-topeet/firmware/arm/mali/arch10.8/mali_csffw.bin`（Panthor 请求的路径，见 `panthor_fw.c:1510` `MODULE_FIRMWARE("arm/mali/arch10.8/mali_csffw.bin")`）。
3. kernel.config：
   ```
   CONFIG_EXTRA_FIRMWARE="arm/mali/arch10.8/mali_csffw.bin"
   CONFIG_EXTRA_FIRMWARE_DIR="/home/charliechen/rk-forge/board/rk3588-topeet/firmware"
   ```
   （绝对路径，dev 机专用；可移植化时改成 build 脚本 copy 进 kernel 源码树 + 相对路径。）
4. 验证：`strings Image | grep mali_csffw` 命中 → 固件进了 vmlinux。

## 真机结果

`update.img` MD5 `95da441d`：**`renderD128` 出现 + GNOME 桌面正常显示**。RK3588 LCD 全通（boot logo + 桌面）。

## 备选方案（没走）

- Panthor `=m` + `CONFIG_FW_LOADER_COMPRESS_ZSTD=y` + 给 rootfs 加 `make modules_install`：boot 后 udev 加载 panthor.ko，读 rootfs 的 .zst。更"正统"但要改 forge 脚本装模块。
- initramfs 放固件：要先生成 initramfs（当前无）。

## 教训

- early-probe 的固件（GPU/VPU）要么内建（CONFIG_EXTRA_FIRMWARE），要么走 initramfs/=m——放 rootfs 里 early probe 拿不到。
- `.zst` 固件要 `CONFIG_FW_LOADER_COMPRESS_ZSTD`（依赖 `FW_LOADER_COMPRESS`）；排查"firmware not found"先看是不是压缩 + 时机。

## 关键文件

- `board/rk3588-topeet/firmware/arm/mali/arch10.8/mali_csffw.bin`（raw blob，tracked）
- `board/rk3588-topeet/kernel.config`（CONFIG_EXTRA_FIRMWARE）
