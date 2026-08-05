# Ch3 — GPU 固件：Panthor early probe 与内建 raw 固件

> 上一章把屏点亮了——可点亮的只是 boot logo 和 fbcon（内核帧缓冲控制台），GNOME 桌面还是黑的。这一章短得多，但它藏着一个 RK3588 上很有代表性的坑：early-probe 设备的固件时机。完整记录见 [notes/48](../../notes/48-2026-08-01-rk3588-gpu-firmware-embedded-gnome-desktop.md)。

## 症状：GDM 起来了，桌面是黑的

LCD 视频通了之后，systemd 把 GDM 拉起来，gnome-shell 也跑起来了（能看到它的 PID），可屏幕上桌面是黑的。`journalctl` 里 gnome-shell 在反复报：

```
gnome-shell: Failed to lock front buffer on /dev/dri/card0: gbm_surface_lock_front_buffer failed
gnome-shell: Failed to query buffer age, got error 3003
```

`ls /dev/dri/` 一看——只有 `card0`，没有 `renderD128`。

## 机制：renderD128 是 GPU 渲染节点

`card0` 是 DRM 主节点（显示），`renderD128` 才是 GPU 的渲染节点——它得 Panthor（Mali-G610 的主线开源驱动）probe 成功才会被创建。`renderD128` 缺席，意味着 mutter 拿不到 GL/EGL，于是拿不到 GBM 的 front buffer，桌面就没法渲染。boot logo 和 fbcon 不走 GPU（它们走 display 控制器的 scanout），所以屏能亮、桌面黑——这个分裂的症状就是 GPU 没 probe 的特征。

dmesg 把根因说得很直白：

```
panthor: *ERROR* Failed to load firmware image 'mali_csffw.bin'
```

Panthor 驱动 probe 时要加载 `mali_csffw.bin` 这颗固件，没拿到，probe 失败，`renderD128` 不创建。

## 坑：early probe 的固件，放 rootfs 里拿不到

这关是两个坑叠在一起，单看 dmesg 那行会以为是「固件没装」，其实装了也拿不到。

第一个坑是时机。Panthor 咱们编成 `=y`（built-in），它在 boot 早期就 probe——可那时候 rootfs 还没挂载，`/usr/lib/firmware/arm/mali/arch10.8/mali_csffw.bin` 根本还没出现在文件系统里。early-probe 的设备去 rootfs 里找固件，注定找不到。

第二个坑是压缩。就算 rootfs 挂上了，linux-firmware 包里给的是 `mali_csffw.bin.zst`（zstd 压缩），而咱们的 kernel 没开 `CONFIG_FW_LOADER_COMPRESS_ZSTD`——固件加载器读不了 `.zst`。所以哪怕时机对了，压缩这一层也读不出来。

## 正解：把 raw 固件内建进 kernel

forge 不跑 `make modules_install`（只单独装 WiFi 的 `.ko`），所以「Panthor 编 `=m` + 装模块 + udev 加载」这条正统路要额外加脚本步骤。最省事的是把解压后的 raw 固件直接内建进 kernel image：

```bash
# 1. 从 staged rootfs 取 .zst，解压成 raw（282 KB）
zstd -d mali_csffw.bin.zst -o mali_csffw.bin

# 2. 放到 Panthor 请求的路径（见 panthor_fw.c 的 MODULE_FIRMWARE）
#    board/rk3588-topeet/firmware/arm/mali/arch10.8/mali_csffw.bin
```

然后在 kernel.config 里告诉构建系统把这颗固件塞进 vmlinux：

```
CONFIG_EXTRA_FIRMWARE="arm/mali/arch10.8/mali_csffw.bin"
CONFIG_EXTRA_FIRMWARE_DIR="board/rk3588-topeet/firmware"
```

验证固件确实进了 kernel image：

```bash
strings Image | grep mali_csffw    # 命中 = 固件已内建
```

这颗 raw blob 是 tracked 的（[board/rk3588-topeet/firmware/arm/mali/arch10.8/mali_csffw.bin](../../../board/rk3588-topeet/firmware/arm/mali/arch10.8/mali_csffw.bin)），不依赖 rootfs 挂载、不依赖压缩支持，boot 早期 probe 时直接从内核里取。

## 成功长这样

`update.img`（MD5 `95da441d`）烧 eMMC，`renderD128` 出现，GNOME 桌面正常显示。到这一步，RK3588 的 LCD 全通——boot logo、fbcon、GNOME 桌面都亮。

> 教训记一下：early-probe 设备（GPU/VPU）的固件，要么内建（`CONFIG_EXTRA_FIRMWARE`），要么走 initramfs 或编 `=m` 让它延后 probe——放 rootfs 里、early probe 阶段是拿不到的。排查任何 `firmware not found`，先看两件事：固件是不是压缩的（`.zst` 要 `FW_LOADER_COMPRESS_ZSTD`），以及 probe 时机是不是早于 rootfs 挂载。

> 备选方案（咱们没走）：Panthor `=m` + `CONFIG_FW_LOADER_COMPRESS_ZSTD=y` + 给 rootfs 加 `make modules_install`，boot 后 udev 加载 `panthor.ko`、读 rootfs 里的 `.zst`。这条路更「正统」，但要改 forge 脚本去装模块。内建更省事，代价是 kernel image 大 ~280 KB，对 eMMC 启动的 RK3588 无所谓。
