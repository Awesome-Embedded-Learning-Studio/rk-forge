# RK3568 rootfs: vendor SDK → forge mainline 等价对照

> 产出: 8 功能域 vendor→mainline buildroot 等价映射 + 分类(A 直接主线 / B 换主线实现 / C 必搬 vendor / D 丢弃) + MVP→完整功能 rootfs 路线 + 可落地的 defconfig fragment 草案。
> workflow: 10 agents / 495k tokens / 2026-07-24。数据源: reference/rk3568/buildroot (vendor 2021.11) ↔ third_party/buildroot (forge 2026.08-git)。

## ⚠ 评审修正摘要（critique 指出的 4 个主要点 — 读正文时请据此修正）

1. **buildroot 版本标签**: forge 树实际是 `2026.08-git`(Makefile:95 `BR2_VERSION := 2026.08-git`)，非 2026.05。2026.05 是最新*发布*版，树已进 2026.08 开发周期(git describe `2026.05-264-g67449130e9`)。所有 package 版本号本身准确；但若 checkout 2026.05 release tag 会得到比报告更旧的包。
2. **libcamera/ISP21 可能被低估**: 报告称主线 libcamera rkisp1 IPA 只覆盖 ISP1(RK3399/3288)、不支持 RK3568 的 ISP21。这对 libcamera **v0.7.1** 很可能不成立 — 上游 rkisp1 处理器覆盖 ISP v1/v2/ISP21(RK3566/68/62)；buildroot "Rockchip ISP1" 是遗留命名(内核驱动就叫 rkisp1)。libcamera 应视为 B 类真替代(非仅"未来方向")，rkaiq 降为 C 生产调优路径。需对 v0.7.1 IPA 版本矩阵做最终验证。
3. **NPU 未获域级分析**: npu2.config 由 ATK 引入(`BR2_PACKAGE_RKNPU2=y`)但 8 域均未单列，仅综合报告一行带过。应给域级处理(defconfig + 内核端 + S98rknn_server 依赖)。分类仍是 C(唯一无主线等价的 IP)。
4. **域 5 Panfrost defconfig 缺 `_LLVM`**: `BR2_PACKAGE_MESA3D_GALLIUM_DRIVER_PANFROST` depends on `BR2_PACKAGE_MESA3D_LLVM`(Config.in:209) 且 select `_NEEDS_PRECOMP_COMPILER`，漏了会静默失效。§7 草案已正确含 `BR2_PACKAGE_MESA3D_LLVM=y` — 以 §7 为准。

次要: QUECTEL_QCONNECTMANAGER 域间分类冲突(B vs C，建议统一 C，B 为替代); SOURCE_HAN_SANS_CN 分类分歧(B vs C); libmali "1.9.0" 是上游项目版本未在树内核对(ROCKCHIP_MALI_VERSION=master，但 bifrost-g52/g13p0 变体选择本身正确)。

---

所有核心版本和移除项均已针对 `third_party/buildroot` 完成验证。现在开始合成报告。

---

# RK3568 rootfs 功能组件迁移报告：vendor SDK → forge mainline buildroot 2026.05

> 板：ATK-DLRK3568 (RK3568)。锚：`reference/rk3568/buildroot`（vendor buildroot 2021.11，gitignored）。目标树：`third_party/buildroot`（forge buildroot 2026.05）。工具链：`/opt` gcc 15.3.1 / glibc 2.42 / kernel-headers 6.6.44。

## 1. 总览

**一句话结论**：vendor RK3568 rootfs 的功能组件里，绝大多数（A 类，~70%）在 forge buildroot 2026.05 直接开 `BR2_*` config 就能拿到、且版本普遍比 vendor(2021.11) 新一档；真正必须搬 vendor 的只有 RK3568 的硬件加速用户态栈（MPP/RGA/gstreamer-rockchip/camera-engine-rkaiq/rockchip-alsa-config）和 NPU(rknpu2)——这些主线只给内核驱动、不给 userspace 库。从 MVP busybox 走到完整功能 rootfs 的路径清晰：先抄 A 类 defconfig（纯 config，最快见效），再换 B 类主线实现（丢 Mali blob/chromium blob），最后搬 C 类 vendor 硬件栈。

**功能域 × 分类计数表**（计数按各域 agent 的 mainline_map 条目；跨域有少量重复条目，如 `LIBDRM_INSTALL_TESTS`/`IW`/`FONTCONFIG` 在多个域出现，故总数含重复）：

| 功能域 | A 直接主线 | B 换主线实现 | C 必搬 vendor | D 丢弃 | 小计 |
|---|---|---|---|---|---|
| 1. base + 芯片层 | 15 | 2 | 1 | 5 | 23 |
| 2. 文件系统 + 字体 | 10 | 3 | 0 | 1 | 14 |
| 3. GPU | 3 | 1 | 0 | 2 | 6 |
| 4. 多媒体 (audio/camera/Gst/MPP) | 9 | 0 | 5 | 1 | 15 |
| 5. 显示/UI (Weston/Qt/Chromium) | 9 | 2 | 3 | 2 | 16 |
| 6. 连接 (WiFi/BT/电源) | 10 | 2 | 1 | 1 | 14 |
| 7. ATK 网络工具杂项 (alientek.config) | 27 | 0 | 3 | 3 | 33 |
| 8. 开发期工具 (benchmark/debug) | 21 | 0 | 0 | 6 | 27 |
| **合计（含跨域重复）** | **104** | **10** | **13** | **21** | **148** |

> 独立组件去重后：A 类是绝对主体；C 类去重后实质 8 个 vendor 移植项（见 §5）。

---

## 2. 组件总表（按功能域分组）

表头：`vendor 组件` | `mainline 等价 / forge 包` | `forge 2026.05 版本` | `分类` | `defconfig 建议行`。版本均已对 `third_party/buildroot` 实测核对。

### 域 1：base + 芯片层

| vendor 组件 | mainline 等价 | forge 版本 | 类 | defconfig 建议 |
|---|---|---|---|---|
| `BR2_PACKAGE_BUSYBOX`(+`_SHOW_OTHERS`+fragment) | package/busybox | 1.38.0 (v 1.36.0) | A | `BR2_PACKAGE_BUSYBOX=y` / `_SHOW_OTHERS=y` / `_CONFIG_FRAGMENT_FILES="<forge>/busybox.fragment"` |
| `BR2_ROOTFS_DEVICE_CREATION_DYNAMIC_EUDEV` | system/Config.in:289 + package/eudev | eudev 3.2.14 (v 3.2.10) | A | `BR2_ROOTFS_DEVICE_CREATION_DYNAMIC_EUDEV=y` |
| `BR2_PACKAGE_E2FSPROGS`(+`_FSCK`,`_RESIZE2FS`) | package/e2fsprogs | 1.47.4 (v 1.46.5) | A | `BR2_PACKAGE_E2FSPROGS=y` + `_FSCK=y` + `_RESIZE2FS=y` |
| `BR2_PACKAGE_UTIL_LINUX_MOUNT` | package/util-linux 子选项 | util-linux 2.41 (v 2.39) | A | `BR2_PACKAGE_UTIL_LINUX=y` + `_MOUNT=y` |
| `BR2_PACKAGE_ANDROID_TOOLS` | package/android-tools | 4.2.2+git20130218 | A | `BR2_PACKAGE_ANDROID_TOOLS=y` |
| `BR2_PACKAGE_INPUT_EVENT_DAEMON` | package/input-event-daemon | 0.1.3 | A | `BR2_PACKAGE_INPUT_EVENT_DAEMON=y` |
| `BR2_PACKAGE_USBMOUNT` | package/usbmount | 0.0.22 | A | `BR2_PACKAGE_USBMOUNT=y` |
| `BR2_PACKAGE_HOST_QEMU`(+`_LINUX_USER_MODE`) | package/qemu (host) | 11.0.0 (v 6.1.0) | A | `BR2_PACKAGE_HOST_QEMU=y` + `_LINUX_USER_MODE=y` |
| `BR2_PACKAGE_HOST_PYTHON3`(+`_SSL`)/`HOST_E2FSPROGS`/`HOST_NTFS_3G` | host pkgs | python 3.14 (v 3.10) | A | `BR2_PACKAGE_HOST_PYTHON3=y` + `_SSL=y` 等 |
| rootfs 镜像 `EXT2`(+`_4`,`_SIZE`)/`CPIO`(+`_GZIP`)/`SQUASHFS` | fs/ext2,fs/cpio,fs/squashfs | 2026.05 infra | A | `BR2_TARGET_ROOTFS_EXT2=y` + `_4=y` + `_SIZE="auto"` |
| 通用系统 `BR2_aarch64`/`cortex_a55`/`MERGED_USR`/`ROOT_PASSWD`/`HOSTNAME`/`ISSUE` | system/ Kconfig | 2026.05 infra | A | `BR2_aarch64=y`/`BR2_cortex_a55=y`/`BR2_TARGET_GENERIC_HOSTNAME="forge-rk3568"` |
| `BR2_TOOLCHAIN_BUILDROOT_GLIBC`/`_CXX` | → 外部工具链 `BR2_TOOLCHAIN_EXTERNAL_CUSTOM_*` | gcc 15.3.1/glibc 2.42 | A | （MVP 已接，机制替换，非移植） |
| `BR2_LINUX_KERNEL_CUSTOM_LOCAL`(+`_LOCATION`) | linux infra | 2026.05 infra | A | `_LOCATION="<forge kernel path>"` |
| `BR2_CCACHE`/`PRIMARY_SITE`/`POST_BUILD_SCRIPT` | buildroot global | 2026.05 infra | A | `BR2_CCACHE=y`，post-build 重指 forge 路径 |
| `BR2_PACKAGE_GLIBC_GEN_LD_CACHE` | 选项已被上游删除（实测 `package/glibc/` 无此符号） | glibc 2.42 | **B** | post-build 钩子调 `<ldconfig> -r $(TARGET_DIR)`，或内部工具链下 `BR2_PACKAGE_GLIBC_UTILS=y` |
| `BR2_PACKAGE_RKSCRIPT` | 无单包；resize2fs + 自写 init/udev 规则重建 | — | **B** | `BR2_PACKAGE_E2FSPROGS_RESIZE2FS=y` + forge `S00resizefs` + `/etc/udev/rules.d/` |
| `BR2_PACKAGE_RKTOOLKIT` | 无（OTA `update`/`vendor_storage`；`io`→busybox devmem） | — | **C** | 需 RK OTA 时移植 `package/rockchip/rktoolkit` |
| `BR2_PACKAGE_PM_UTILS` | 上游已删（实测 `package/pm-utils` 不存在） | — | **D** | drop；`echo mem > /sys/power/state` |
| `BR2_PACKAGE_HOST_ENVIRONMENT_SETUP` | vendor SDK 便利脚本 | — | **D** | drop（仅发布 SDK 时再造） |
| `BR2_PACKAGE_ROCKCHIP` / `BR2_PACKAGE_RK3566_RK3568` | vendor config-only 菜单/SoC 选择器 | — | **D** | drop（forge per-board defconfig 即选择器） |
| `BR2_ROOTFS_OVERLAY`（vendor board 路径） | 重指 forge overlay | 2026.05 infra | **D** | `BR2_ROOTFS_OVERLAY="<forge>/overlay"`（内容审计 cherry-pick） |

### 域 2：文件系统 + 字体

| vendor 组件 | mainline 等价 | forge 版本 | 类 | defconfig 建议 |
|---|---|---|---|---|
| `BR2_PACKAGE_DOSFSTOOLS`(+`_FATLABEL`/`_FSCK_FAT`/`_MKFS_FAT`) | package/dosfstools | 4.2 | A | `BR2_PACKAGE_DOSFSTOOLS=y` + 3 子选项 |
| `BR2_PACKAGE_NTFS_3G`(+`_NTFSPROGS`) | package/ntfs-3g | 2022.10.3 (v 2022.5.17) | A | `BR2_PACKAGE_NTFS_3G=y` + `_NTFSPROGS=y` |
| `BR2_PACKAGE_PARTED` | package/parted | 3.6 (v 3.3) | A | `BR2_PACKAGE_PARTED=y` |
| `BR2_PACKAGE_FONTCONFIG` | package/fontconfig | 2.17.1 (v 2.13.1) | A | `BR2_PACKAGE_FONTCONFIG=y` |
| `BR2_PACKAGE_DEJAVU`/`LIBERATION` | package/dejavu,liberation | 2.37 / 2.1.5 | A | `BR2_PACKAGE_DEJAVU=y` / `_LIBERATION=y` |
| `BR2_PACKAGE_FONT_AWESOME` | package/font-awesome | 7.2.0 (v 4.7.0，跨大版本) | A | `BR2_PACKAGE_FONT_AWESOME=y`（注意 4→7 图标 class breaking change） |
| `BR2_PACKAGE_EXFAT`/`EXFAT_UTILS`（legacy FUSE） | 切 exfatprogs + 内核 in-tree exfat（6.6 自带） | exfatprogs 1.2.9 | **B** | `BR2_PACKAGE_EXFATPROGS=y`（Config.in:12 明确要求内核 exfat 用 exfatprogs） |
| `BR2_PACKAGE_SOURCE_HAN_SANS_CN`（思源黑体） | forge 缺包；主线等价 wqy-zenhei，或移植 vendor 纯 OFL 数据包 | wqy-zenhei 0.9.45 | **B** | `BR2_PACKAGE_WQY_ZENHEI=y`；或 `cp -r reference/.../package/source-han-sans third_party/buildroot/package/` 后开原符号 |
| `BR2_PACKAGE_FATRESIZE` | forge 已移除（实测 `package/fatresize` 不存在） | — | **D** | drop；parted 替代 |

### 域 3：GPU

| vendor 组件 | mainline 等价 | forge 版本 | 类 | defconfig 建议 |
|---|---|---|---|---|
| `BR2_PACKAGE_ROCKCHIP_MALI`（libmali blob 1.9.0） | mesa3d Gallium **Panfrost**（Mali-G52 Bifrost，ES 3.1 conformant） | mesa3d 26.1.2 | **B** | `BR2_PACKAGE_MESA3D=y`/`_LLVM=y`/`_GALLIUM_DRIVER_PANFROST=y`/`_OPENGL_EGL=y`/`_OPENGL_ES=y`/`_GBM=y`（panfrost 选项见 `package/mesa3d/Config.in:206`） |
| `BR2_PACKAGE_LIBDRM`（mali 隐含） | package/libdrm（mesa3d 自动 select） | 2.4.134 | A | `BR2_PACKAGE_LIBDRM_ROCKCHIP=y` |
| libgbm / libEGL / libGLES（mali 提供 virtual） | mesa3d 提供 | mesa3d 26.1.2 | A | 由上面 mesa3d GBM/EGL/GLES 行覆盖 |
| libOpenCL（mali 默认开） | mesa3d RustiCL-on-G52（实验性） | 26.1.2 | **D** | OFF（RustiCL-on-G52 非生产就绪） |
| Vulkan（`_HAS_VULKAN`，vendor 默认关） | mesa3d panvk-on-G52（实验性） | 26.1.2 | **D** | OFF（与 vendor 默认一致） |

### 域 4：多媒体（audio / camera / GStreamer / MPP）

| vendor 组件 | mainline 等价 | forge 版本 | 类 | defconfig 建议 |
|---|---|---|---|---|
| `BR2_PACKAGE_ALSA_PLUGINS` | package/alsa-plugins | 1.2.12 | A | `BR2_PACKAGE_ALSA_PLUGINS=y` |
| `BR2_PACKAGE_ALSA_UTILS`(+`ALSACONF`/`AMIXER`/`APLAY`) | package/alsa-utils | 1.2.16 (v 1.2.7) | A | `BR2_PACKAGE_ALSA_UTILS=y` + 3 子选项 |
| `BR2_PACKAGE_LIBMAD` | package/libmad | 0.15.1b | A | `BR2_PACKAGE_LIBMAD=y` |
| `BR2_PACKAGE_PULSEAUDIO`(+`_DAEMON`) | package/pulseaudio | 17.0 (v 14.2) | A | `BR2_PACKAGE_PULSEAUDIO=y` + `_DAEMON=y` |
| `BR2_PACKAGE_LIBV4L`(+`_UTILS`) | package/libv4l | 1.32.0 (v 1.22.1) | A | `BR2_PACKAGE_LIBV4L=y` + `_UTILS=y` |
| `BR2_PACKAGE_GSTREAMER1` | package/gstreamer1 | 1.24.13 (v 1.22.2) | A | `BR2_PACKAGE_GSTREAMER1=y` |
| `BR2_PACKAGE_GST1_PLUGINS_BASE`(+子插件) | 同名 | 1.24.13 | A | `_INSTALL_TOOLS=y`/`_PLUGIN_ALSA/APP/.../VORBIS=y`；**改名** `_PLUGIN_VIDEOCONVERTSCALE=y`（原 `VIDEOCONVERT` 是死符号，实测真符号在 `gst1-plugins-base/Config.in:62`） |
| `BR2_PACKAGE_GST1_PLUGINS_GOOD`(+~20 子插件) | 同名 | 1.24.13 | A | `JPEG/PNG`(无 `_PLUGIN_` 中缀)/`RTP/RTPMANAGER/RTSP/UDP/V4L2/MATROSKA/...=y` |
| `BR2_PACKAGE_GST1_PLUGINS_BAD`(+~18 子插件) | 同名 | 1.24.13 | A | `KMS/FAAD/FLUIDSYNTH/MIDI/CAMERABIN2/MPEGTSMUX/HLS/RTMP/SDP/...=y` |
| `BR2_PACKAGE_GST1_PLUGINS_UGLY`(ASFDEMUX/.../MPEG2DEC) | 同名 | 1.24.13 | A | 4 子选项；建议另开 `BR2_PACKAGE_GST1_LIBAV=y`（codec 覆盖更全） |
| `BR2_PACKAGE_ROCKCHIP_MPP`(+`_ALLOCATOR_DRM`) | 无主线等价（内核 VPU Hantro/rkvdec2 全主线，userspace libmpp 是 RK 专有） | develop | **C** | 移植 `package/rockchip/rockchip-mpp` |
| `BR2_PACKAGE_ROCKCHIP_RGA` | 无（2D 加速 userspace） | master | **C** | 移植 `package/rockchip/rockchip-rga` |
| `BR2_PACKAGE_GSTREAMER1_ROCKCHIP` | 无（mppvideodec/mppvideoenc/rgaconvert 插件） | master | **C** | 移植 `package/rockchip/gstreamer1-rockchip`（可能需 X11-optional patch） |
| `BR2_PACKAGE_CAMERA_ENGINE`（→ rkaiq，ISP2/RK3568） | 无（libcamera v0.7.1 在 forge，但 rkisp1 IPA 只覆盖 ISP1/RK3399，**不支持 RK3568 ISP21**） | rkaiq 1.0 | **C** | 移植 `camera_engine_rkaiq`（依赖 rga） |
| `BR2_PACKAGE_ROCKCHIP_ALSA_CONFIG` | 无（板级 UCM/asound 路由） | 1.0 | **C** | 移植 `package/rockchip/rockchip-alsa-config` + `external/alsa-config` |
| `BR2_PACKAGE_ALSA_UCM_CONF` | forge 无此符号（实测 grep 空） | — | **D** | drop（RK3568 用 rockchip-alsa-config） |

### 域 5：显示 / UI（Weston / Qt5+Qt6 / Chromium / fonts）

| vendor 组件 | mainline 等价 | forge 版本 | 类 | defconfig 建议 |
|---|---|---|---|---|
| `BR2_PACKAGE_WESTON`(+`_DRM`,`_DEMO_CLIENTS`) | package/weston（符号名不变） | 15.0.1 (v 12.0.1) | A | `BR2_PACKAGE_WESTON=y`/`_DRM=y`/`_DEMO_CLIENTS=y` |
| `BR2_PACKAGE_WAYLAND`(+utils) | package/wayland + wayland-protocols + wayland-utils | wayland 1.24.0 (v 1.22.0) | A | `BR2_PACKAGE_WAYLAND=y`/`_UTILS=y` |
| `BR2_PACKAGE_QT5`(+qt5base 子选项) | package/qt5/qt5base | 5.15.18 (qt5base commit bebdfd54) | A | `_GUI/_WIDGETS/_FONTCONFIG/_JPEG/_PNG/_GIF/_HARFBUZZ/_SQL/_SQLITE_QT=y`（v 5.15.8） |
| `BR2_PACKAGE_QT5WAYLAND`（vendor 隐含） | package/qt5/qt5wayland | 5.15 LTS | A | 显式 `BR2_PACKAGE_QT5WAYLAND=y`（Qt 跑在 Weston 下必备） |
| Qt5 应用模块（QUICKCONTROLS2/GRAPHICALEFFECTS/SVG/MULTIMEDIA/DECLARATIVE/...） | package/qt5/*（39/40 在 forge） | 5.15.18 | A | 按应用挑：`_QT5DECLARATIVE=y`/`_QUICKCONTROLS2=y`/... |
| `BR2_PACKAGE_CAIRO`/`PANGO`/`AT_SPI2_CORE`/`FONTCONFIG`/`JPEG_TURBO` | 各同名包 | cairo 1.18.4/pango 1.56.4/at-spi2-core 2.58.2/jpeg-turbo 3.1.4.1 | A | 多被 qt5base/webengine 自动 pull |
| 拉丁/图标字体（DEJAVU/FONT_AWESOME/LIBERATION/...） | 各同名包 | 同版本 | A | 按应用引用挑 |
| `BR2_PACKAGE_SDL2`(+Wayland/GLES/...) | package/sdl2 + 子包 | sdl2 2.32.10 (v 2.0.22) | A | `BR2_PACKAGE_SDL2=y`/`_WAYLAND=y`/`_OPENGLES=y` |
| `BR2_PACKAGE_LIBDRM_INSTALL_TESTS`/`WAYLAND_UTILS` | 子选项/包 | 2026.05 infra | A | 调显示管线必备（modetest/wayland-info） |
| `BR2_PACKAGE_ROCKCHIP_MALI`（同域 3） | → mesa3d Panfrost | 26.1.2 | **B** | 见域 3 |
| `BR2_PACKAGE_CHROMIUM_WAYLAND`（独立 Chromium 88） | 独立 chromium 已从 buildroot 删除；主线等价 qt5webengine（内嵌 chromium） | qt5webengine 5.15.18（qt6webengine 实测 ABSENT） | **B** | `BR2_PACKAGE_QT5WEBENGINE=y`(+`_PROPRIETARY_CODECS`/`_ALSA` 如需) |
| `BR2_PACKAGE_QT5QUICK3D` | forge 无 qt5quick3d（实测 ABSENT）；主线是 qt6quick3d | qt6 6.9.1 | **C** | drop 或迁 Qt6：`BR2_PACKAGE_QT6QUICK3D=y` |
| `BR2_PACKAGE_SOURCE_HAN_SANS_CN`/`NOTO_SANS_SC` | forge 缺；纯字体数据包 | — | **C** | 拷 vendor package/ 到 forge 或走 overlay；stopgap `BR2_PACKAGE_WQY_ZENHEI=y` |
| `BR2_PACKAGE_LIBV4L_RKMPP` | 域 4 rkmpp 的 V4L2 桥 | — | **C** | 归多媒体域（WebEngine 零拷贝 HW 解码才需） |
| `BR2_PACKAGE_QT5ENGINIO`/`QT5BASE_MYSQL`/`_EXAMPLES`/`_TOOLS_LINGUIST_TOOLS` | forge 仍在但产品镜像不需要 | enginio 1.6.3(deprecated) | **D** | omit |
| `BR2_PACKAGE_JPEG_TURBO_JPEG6` | 子选项已删 | — | **D** | omit |

### 域 6：连接（WiFi / BT / 电源）

| vendor 组件 | mainline 等价 | forge 版本 | 类 | defconfig 建议 |
|---|---|---|---|---|
| `BR2_PACKAGE_BLUEZ5_UTILS`(+`_CLIENT`/`_TOOLS`/`_DEPRECATED`) | package/bluez5_utils | 5.79 (v 5.62) | A | `BR2_PACKAGE_BLUEZ5_UTILS=y` + 3 子选项 |
| `BR2_PACKAGE_BLUEZ_ALSA`(+`_HCITOP`/`_RFCOMM`) | package/bluez-alsa | 4.3.1 (v 4.0.0) | A | `BR2_PACKAGE_BLUEZ_ALSA=y` + 子选项 |
| `BR2_PACKAGE_WPA_SUPPLICANT`(+AP/EAP/CLI/WPA_CLIENT_SO/PASSPHRASE) | package/wpa_supplicant | 2.11 (v 2.9) | A | 6 子选项全在；`AUTOSCAN` 留 OFF（alientek.config:45） |
| `BR2_PACKAGE_HOSTAPD` | package/hostapd | 2.11 (v 2.9) | A | `BR2_PACKAGE_HOSTAPD=y` |
| `BR2_PACKAGE_DNSMASQ` | package/dnsmasq | 2.93 (v 2.85) | A | `BR2_PACKAGE_DNSMASQ=y` |
| `BR2_PACKAGE_NTP` | package/ntp | 4.2.x | A | `BR2_PACKAGE_NTP=y` |
| `BR2_PACKAGE_GESFTPSERVER` | package/gesftpserver | 2 (v 1) | A | `BR2_PACKAGE_GESFTPSERVER=y` |
| `BR2_PACKAGE_DHCPCD`（vendor 注释掉） | package/dhcpcd | 10.2.4 | A | 可选（connman 内建 DHCP） |
| `BR2_PACKAGE_CONNMAN`(+`_WIFI`/`_LOOPBACK`/`_CLIENT`) | package/connman | 2.0 (v 1.40) | A | ATK 板的 netmgr，4 子选项 |
| `BR2_PACKAGE_IW` | package/iw | 6.17 (v 5.9) | A | `BR2_PACKAGE_IW=y` |
| `BR2_PACKAGE_UTIL_LINUX_RFKILL` | util-linux 子选项 | infra | A | `BR2_PACKAGE_UTIL_LINUX_RFKILL=y` |
| `BR2_PACKAGE_RKWIFIBT` | 无直接等价；forge 已用 `scripts/stage-rootfs.sh:38 stage_wifi_firmware()` + `S99wifi` 走主线 `request_firmware()` 替代其功能（rtl8733bu 内建 FW 不需要它） | — | **C** | 仅当 ATK wifi 芯片需 vendor nvram/MAC（Broadcom AP6256 系）才移植；硬件门控 |
| `BR2_PACKAGE_QUECTEL_QCONNECTMANAGER` | 主线 ofono(2.18)+ModemManager；或移植 vendor（单文件 C） | — | **B** | 有 4G 模组：`BR2_PACKAGE_OFONO=y` 或移植 quectel-CM；无模组：drop |
| `BR2_PACKAGE_PM_UTILS` | 上游已删（实测 ABSENT） | — | **B** | drop；`echo mem > /sys/power/state` |
| `BR2_PACKAGE_BLUEZ_UTILS_TOOLS`（legacy bluez4） | 死符号（vendor/forge 均无包目录） | — | **D** | drop；bluez5_utils_tools 替代 |

### 域 7：ATK 网络工具杂项（alientek.config）

> 本域是 ATK 板 rootfs 功能清单，A 类密集。仅列关键行与 C/D 项，其余网络工具版本对比见 §3。

| vendor 组件 | mainline 等价 | forge 版本 | 类 | defconfig 建议 |
|---|---|---|---|---|
| `CONNMAN`(同域 6)/`IW`/`UTIL_LINUX_RFKILL` | — | — | A | 见域 6 |
| `BR2_PACKAGE_IPERF3`/`IPROUTE2`/`RSYNC`/`ETHTOOL`/`PPPD` | 各同名包 | iperf3 3.21/iproute2 7.0.0/rsync 3.4.4/ethtool 7.0/pppd 2.5.2 | A | 直接开 |
| `BR2_PACKAGE_OPENSSH`(+`_CLIENT`/`_SERVER`) | package/openssh | 10.3p1 (v 8.8p1) | A | 3 行 |
| `BR2_PACKAGE_NGINX`(+`_RTMP`) | package/nginx 1.30.2；`_RTMP` 子选项需在 forge Config.in 复核（grep 未命中，疑 vendor patch） | 1.30.2 (v 1.20.1) | A | `BR2_PACKAGE_NGINX=y`；RTMP 缓 |
| `BR2_PACKAGE_NFS_UTILS`/`VSFTPD`/`SAMBA4` | 各同名包 | nfs 2.9.1/samba 4.24.3 | A | 按需 |
| `BR2_PACKAGE_LIBSOCKETCAN`/`CAN_UTILS`/`MMC_UTILS` | 各同名包 | can-utils 2025.01/mmc-utils git | A | 直接开 |
| `BR2_PACKAGE_FILE`/`EVTEST`/`COREUTILS`(+`_INDIVIDUAL_BINARIES`)/`KMOD_TOOLS`/`MINICOM` | 各同名包 | file 5.47/evtest 1.36/coreutils 9.10/kmod 34.2/minicom 2.11.1 | A | 直接开 |
| `BR2_PACKAGE_DOSFSTOOLS`(+子) | 同域 2 | 4.2 | A | 见域 2 |
| `BR2_PACKAGE_GLIBC_UTILS` | glibc 子选项 | 随 glibc 2.42 | A | `BR2_PACKAGE_GLIBC_UTILS=y` |
| `BR2_PACKAGE_VALGRIND`/`GDB`(+`_SERVER`/`_DEBUGGER`/`_TUI`/`HOST_GDB*`) | 各包 | valgrind 3.26.0 | A | 调试套件 |
| `BR2_TARGET_LOCALTIME="Asia/Shanghai"`/`BR2_GENERATE_LOCALE`/`_ENABLE_NLS`/`ROOT_PASSWD`/`HOSTNAME` | system/ global | infra | A | 直接抄（hostname 建议小写） |
| `BR2_PACKAGE_NETSTAT_NAT` | forge 已删（实测 ABSENT） | — | **D** | drop；用 `BR2_PACKAGE_CONNTRACK_TOOLS=y` |
| `CONFIG_UDHCPD=y` | 无效行（`CONFIG_` 非 `BR2_`，Kconfig 忽略） | — | **D** | 删；需 DHCP server 用 dnsmasq 或 busybox applet |
| `BR2_PACKAGE_QUECTEL_QCONNECTMANAGER` | 见域 6 | — | **C** | 同域 6（有 4G 才搬） |
| `BR2_PACKAGE_ATK_INSTALLS` | 无等价（板级资产：ES8388/RK809 asound.state + `S98rknn_server`(NPU) + `S01alactl`(ALSA) init + QML 插件 + wifi/bt 脚本） | — | **C** | 抽进 forge rootfs overlay + init，不照搬 package；NPU init 依赖 rknpu2 移植 |
| `BR2_PACKAGE_ALIENTEK` | vendor umbrella 菜单（仅包 ATK_INSTALLS+SYSTEMUI） | — | **C** | drop umbrella；子资产按上条处理 |
| `BR2_PACKAGE_SYSTEMUI` | ATK Qt5 演示 UI（依赖重） | — | **D** | MVP 跳过；后续基于 forge qt5/qt6 重写 |

### 域 8：开发期工具（benchmark / debug / test）

> 建议**不进主 board defconfig**，单独成 `configs/fragments/debug.config` + `benchmark.config`，开发期 `#include`，发布关掉瘦 rootfs。

| vendor 组件 | mainline 等价 | forge 版本 | 类 | defconfig 建议 |
|---|---|---|---|---|
| `STRACE`/`I2C_TOOLS`/`EVTEST`/`PROCPS_NG`/`LRZSZ`/`COREUTILS`/`IPUTILS`/`IW`/`WIRELESS_TOOLS` | 各包 | strace 7.1(6.2)/i2c-tools 4.4/evtest 1.36/procps-ng 4.0.6/lrzsz 0.12.21rc/coreutils 9.10/iputils 20250605/iw 6.17 | A | 硬件 bring-up 高价值保留 |
| `LIBDRM_INSTALL_TESTS` | libdrm 子选项 | infra | A | `BR2_PACKAGE_LIBDRM_INSTALL_TESTS=y`（modetest） |
| `LINUX_TOOLS_PERF` | linux-tools | infra | A | `BR2_PACKAGE_LINUX_TOOLS_PERF=y` |
| `GLMARK2` | package/glmark2 + FLAVOR | 2023.01 | A | `_FLAVOR_WAYLAND_GLESV2=y`（配 mesa3d GLESv2） |
| `LMBENCH`/`STRESS_NG`/`RT_TESTS`/`MEMTESTER`/`WHETSTONE`/`DHRYSTONE`/`IPERF` | 各包 | stress-ng 0.21.02/rt-tests 2.8/memtester 4.7.1/lmbench git | A | 基准套件 |
| `GST1_PLUGINS_BAD_PLUGIN_DEBUGUTILS` | gst-bad 子选项 | 1.24.13 | A | 仅 gst 栈开时 |
| `UNIXBENCH`/`PROCRANK_LINUX`/`STRESSAPPTEST` | forge 无（实测全 ABSENT） | — | **D** | drop；procps-ng pmap / stress-ng 替代 |
| `ROCKCHIP_TEST`/`ROCKCHIP_MPP_TESTS`/`CAMERA_ENGINE_RKAIQ_RKISP_DEMO` | vendor 专属；无主线等价 | — | **D** | drop；仅移植对应 vendor 包时才有意义 |

---

## 3. A 类：直接更新到最新（"统一更新"主战场）

这些是"开 config 就能拿、且 forge 版本比 vendor 新"的组件——把 vendor 的 `BR2_*` 行抄过来即可，零移植成本，且顺手吃到 4 年的安全/特性更新。版本对比（已对 `third_party/buildroot` 核对）：

**系统基础 / 镜像 / 工具链**
- busybox 1.36.0 → **1.38.0**（`package/busybox/busybox.mk`）
- util-linux 2.39 → **2.41**（含 `_MOUNT`/`_RFKILL`）
- e2fsprogs 1.46.5 → **1.47.4**（`_FSCK`/`_RESIZE2FS`）
- host qemu 6.1.0 → **11.0.0**（`_LINUX_USER_MODE`）
- host python3 3.10 → **3.14**（`_SSL`）
- eudev 3.2.10 → **3.2.14**（`BR2_ROOTFS_DEVICE_CREATION_DYNAMIC_EUDEV`）

**网络 / 连接**
- wpa_supplicant / hostapd 2.9 → **2.11**
- bluez5_utils 5.62 → **5.79**（`_CLIENT`/`_TOOLS`/`_DEPRECATED`）
- bluez-alsa 4.0.0 → **4.3.1**（`_HCITOP`/`_RFCOMM`）
- connman 1.40 → **2.0**（`_WIFI`/`_LOOPBACK`/`_CLIENT`，API 兼容）
- dnsmasq 2.85 → **2.93**；openssh 8.8p1 → **10.3p1**；iperf3 3.10.1 → **3.21**；iproute2 5.14 → **7.0.0**；ethtool 5.12 → **7.0**；iw 5.9 → **6.17**；pppd 2.4.8 → **2.5.2**；kmod 29 → **34.2**；file 5.38 → **5.47**；coreutils 9.0 → **9.10**

**多媒体**
- GStreamer 全家 1.22.2 → **1.24.13**（base/good/bad/ugly 全部，子选项齐）
- alsa-utils 1.2.7 → **1.2.16**（`ALSACONF`/`AMIXER`/`APLAY`）；alsa-plugins → **1.2.12**；pulseaudio 14.2 → **17.0**；libv4l 1.22.1 → **1.32.0**

**显示 / UI**
- weston 12.0.1 → **15.0.1**（`_DRM`/`_DEMO_CLIENTS` 符号不变，`package/weston/weston.mk`）
- wayland 1.22.0 → **1.24.0**
- Qt5 5.15.8 → **5.15.18**（`QT5_VERSION_MAJOR=5.15`，qt5base commit `bebdfd54`，`package/qt5/qt5base/qt5base.mk`）
- mesa3d/libdrm/libgbm → **mesa3d 26.1.2 / libdrm 2.4.134**（自动 pull）
- cairo 1.16 → **1.18.4**；pango 1.48 → **1.56.4**；fontconfig 2.13.1 → **2.17.1**；jpeg-turbo 2.1 → **3.1.4.1**；sdl2 2.0.22 → **2.32.10**
- font-awesome 4.7.0 → **7.2.0**（注意 4→7 图标 class breaking change）

**文件系统**
- ntfs-3g 2022.5.17 → **2022.10.3**；parted 3.3 → **3.6**；dosfstools 4.2 同版（子选项齐）

**调试 / 基准**
- strace 6.2 → **7.1**；procps-ng 3.3.17 → **4.0.6**；stress-ng 0.13.01 → **0.21.02**；rt-tests 2.2 → **2.8**；memtester 4.5.0 → **4.7.1**；iperf2 2.1.4 → **2.2.1**；valgrind 3.21 → **3.26.0**

**注意点（虽是 A 但有坑）**
- `GST1_PLUGINS_BASE_PLUGIN_VIDEOCONVERT` 在 vendor 是死符号，真符号是 **`VIDEOCONVERTSCALE`**（`package/gstreamer1/gst1-plugins-base/Config.in:62`），抄时要改名。
- Qt5 vs Qt6 取舍：若需要 **Qt WebEngine**，必须留 Qt5（实测 `qt6webengine` ABSENT）；否则 Qt6 6.9.1 是现代路径。
- Qt5 子模块 39/40 在 forge，**仅 `qt5quick3d` 缺**（实测 ABSENT）。

---

## 4. B 类：换主线实现（丢 vendor blob）

| 换什么 | vendor blob | 主线实现 | 取舍说明 |
|---|---|---|---|
| **GPU 驱动** | `BR2_PACKAGE_ROCKCHIP_MALI`（ARM libmali 1.9.0 blob，bifrost-g52 g13p0，License=ARM） | **mesa3d 26.1.2 + Gallium Panfrost**（`package/mesa3d/Config.in:206`） | Mali-G52 是 Bifrost v8，Panfrost 自 Mesa 21.2 起 OpenGL ES 3.1 conformant（~99.9% dEQP）。完全开源、丢 blob。代价：buildroot 的 Panfrost 现在拉 LLVM（Mesa 26 precomp 编译器，`mesa3d.mk` 走 host-mesa3d+spirv-llvm-translator），构建重但 gcc 15.3.1/glibc 2.42 下可编。除非有闭源 app 硬链 `libmali.so` 符号，否则是干净 drop-in。 |
| **Web 引擎** | `BR2_PACKAGE_CHROMIUM_WAYLAND`（独立 Chromium 88.0.4324.150，2021 老栈） | **qt5webengine**（内嵌 chromium，`package/qt5/qt5webengine`，`QT5WEBENGINE_VERSION=$(QT5_VERSION)`） | 独立 chromium 已从 buildroot 删除（实测 forge 无 `package/chromium*`）。buildroot 2026.05 里 web 引擎的唯一路径是 qt5webengine（重，但与 Qt/Wayland 集成）。**qt6webengine 实测 ABSENT**，所以选 webengine 就绑 Qt5。 |
| **exFAT** | `BR2_PACKAGE_EXFAT`/`EXFAT_UTILS`（legacy relan/exfat FUSE） | **exfatprogs 1.2.9 + 内核 in-tree exfat**（6.6.44 自带） | forge `package/exfat-utils/Config.in:12` 原文要求：内核 exfat 必须用 exfatprogs。FUSE 路径过时且性能差。 |
| **摄像头（未来方向）** | `BR2_PACKAGE_CAMERA_ENGINE`（rkaiq，C 类必搬） | **libcamera v0.7.1**（forge 有） | **注意：libcamera 的 rkisp1 IPA 目前只覆盖 ISP1（RK3399/RK3288），不支持 RK3568 的 ISP21**。所以 RK3568 现阶段必须用 rkaiq（C），libcamera 是未来 B 方向而非 drop-in。 |
| **4G 拨号** | `BR2_PACKAGE_QUECTEL_QCONNECTMANAGER`（vendor 1.0） | **ofono 2.18 + ModemManager** | vendor quectel-CM 是轻量单文件 C（源码开放）；ofono/MM 更通用但配置复杂。有 Quectel 模组：可选移植 quectel-CM（C）或上 ofono（B）；无模组：drop。 |
| **系统电源** | `BR2_PACKAGE_PM_UTILS`（1.4.1） | 内核 sysfs：`echo mem > /sys/power/state` | pm-utils 已从 buildroot 删除（实测 `package/pm-utils` ABSENT）。sysvinit 下直接写 sysfs，或 3 行 init helper。 |
| **ld.so 缓存** | `BR2_PACKAGE_GLIBC_GEN_LD_CACHE`（选项上游删除，实测 ABSENT） | post-build 钩子 `<ldconfig> -r $(TARGET_DIR)`，或内部工具链下 `BR2_PACKAGE_GLIBC_UTILS=y` | forge 外部 glibc 工具链下 `_GEN_LD_CACHE` 没了，改走 post-build 调外部 ldconfig。 |
| **RK init/udev 胶水** | `BR2_PACKAGE_RKSCRIPT`（resizeall/usbdevice/mountall/async-commit/bootanim + udev 规则） | 用 buildroot 原生重建：`resize2fs`+`S00resizefs`、自写 udev 规则、busybox devmem 替 `io` | 不是单包，逐功能用主线等价重建。iodomain notice 是纯提示（内核/BL31 处理），无需移植。 |
| **中文字体（主线替代）** | `SOURCE_HAN_SANS_CN`（思源黑体，forge 缺包） | **wqy-zenhei 0.9.45**（forge 自带，`package/wqy-zenhei`） | 主线走 wqy-zenhei 即可覆盖 CJK；要思源观感则原样拷 vendor 纯 OFL 数据包（归 C，成本极低）。 |

---

## 5. C 类：必搬 vendor（标注移植工作量）

这是"主线只给内核驱动、不给 userspace 库"的部分——RK3568 的硬件加速用户态栈全在这里。按移植工作量排序：

| 必搬项 | vendor 路径 | 工作量 | 说明 / 依赖 |
|---|---|---|---|
| **rockchip-alsa-config** | `package/rockchip/rockchip-alsa-config` + `external/alsa-config`（v1.0） | **小** | 纯板级 ALSA UCM/asound 路由数据（HDMI/HP/mic），无编译风险。不搬则音频路由默认错误。 |
| **rknpu2 + librknnrt**（NPU） | vendor NPU 栈 | **大** | RK3568 NPU 是**唯一无主线等价**的 IP（主线优先原则下的例外，见项目 memory）。需移植 vendor rknpu2 内核驱动 + librknnrt userspace。`ATK_INSTALLS` 的 `S98rknn_server` init 依赖它完成。 |
| **RKTOOLKIT**（可选） | `package/rockchip/rktoolkit`（master，`external/rktoolkit`） | **小-中** | 3 个 RK target 二进制：`update`(OTA recv)、`vendor_storage`(vendor 分区 r/w)、`io`(寄存器 r/w，可由 busybox devmem 替代)。基础功能 rootfs 可选。 |
| **QUECTEL_QConnectManager**（可选硬件） | `package/rockchip/quectel_QConnectManager`（1.0） | **小** | 单文件 C 程序（quectel-CM），仅板子接了移远 4G 模组才需要。 |
| **RKWIFIBT**（硬件门控） | `package/rockchip/rkwifibt`（1.0.0，meson） | **中** | wifi/bt firmware+nvram 加载。**forge 已用 `scripts/stage-rootfs.sh:38 stage_wifi_firmware()` + `S99wifi` 走主线 `request_firmware()` 替代其功能**。仅当 ATK wifi 芯片需 vendor nvram/MAC 逻辑（Broadcom AP6256 系）才搬；rtl8733bu 内建 FW 不需要。门控在 `rk3568-atk.env` 的 `WIFI_DRIVER`（当前空）。 |
| **rockchip-rga** | `package/rockchip/rockchip-rga`（master，`external/linux-rga`） | **中** | RGA 2D 加速 userspace（scale/rotate/csc/blend）。依赖 libdrm（forge 有）。被 gstreamer-rockchip 与 camera_engine_rkaiq 消费。 |
| **gstreamer1-rockchip** | `package/rockchip/gstreamer1-rockchip`（master，`external/gstreamer-rockchip`） | **中-大** | HW 加速 GStreamer 插件（mppvideodec/mppvideoenc/rgaconvert）。不搬则 GStreamer 退回软解（gst1-libav/ffmpeg 烧 CPU）。依赖 gst1-plugins-base + rockchip-mpp + rockchip-rga + libdrm，**可能需 patch 把 xlib_libX11 改为可选**。 |
| **camera-engine-rkaiq** | `camera_engine_rkaiq`（1.0，`external/camera_engine_rkaiq`） | **大** | RK3568 ISP2 用户态栈。主线 libcamera(rkisp1 IPA) 不覆盖 ISP21，故现阶段必搬。依赖 rockchip-rga。 |
| **rockchip-mpp** | `package/rockchip/rockchip-mpp`（develop，`external/mpp`） | **大** | 核心硬件编解码 userspace（H.264/H.265/VP9 解码 + H.264/H.265 编码）。`_ALLOCATOR_DRM` 选 DMA-BUF/DRM 后端（配 Panfrost/libdrm）。gstreamer-rockchip 与 camera_engine_rkaiq 的硬依赖。内核 VPU（Hantro/rkvdec2）全主线，但 libmpp 是 RK 专有。 |
| **板级资产 (ATK_INSTALLS)** | `package/alientek/atk_installs/` | **小-中** | 不照搬 package，而是抽进 forge rootfs overlay：ES8388/RK809 `asound.state` → `/var/lib/alsa/`；`S98rknn_server` → `/etc/init.d/`（依赖 rknpu2）；`S01alactl` → `/etc/init.d/`；wifi/bt 脚本 → connman dispatcher 或 init。 |
| **CJK 字体 (思源/Noto)**（可选，纯数据） | `package/source-han-sans/`、`package/noto/` | **极小** | 纯 OFL 字体数据包，无原生编译。拷 package/ 目录到 forge 即可，或直接 overlay `.otf`。wqy-zenhei 可作 stopgap。 |

> 去重后的实质 C 类：**8 个 vendor 移植项**（alsa-config / rknpu2 / rktoolkit / quectel / rkwifibt / rga / gst-rockchip / rkaiq / mpp）+ 板级资产 overlay。其中真正阻塞"完整功能 rootfs"的是多媒体 HW 栈（mpp+rga+gst-rockchip+rkaiq+alsa-config）和 NPU（rknpu2）。

---

## 6. 从 MVP busybox 到完整功能 rootfs 的路线

分三阶段，每阶段都是可交付的里程碑（前一阶段不依赖后一阶段）。

### Phase 2a — 纯 config 扩展（A 类，最快见效）
把 §3 的 A 类 defconfig 行批量抄进 forge board fragment。**零移植、零换实现**，只开 buildroot 原生包。

做完后 rootfs 能干：
- 完整 shell 工具链（coreutils/util-linux/procps-ng）、USB 自动挂载（usbmount+eudev）、ext4 在线扩容（resize2fs）
- 网络：connman 管 WiFi/Ethernet、wpa_supplicant/hostapd、ssh(sopenssh 10.3)、samba/nginx/nfs、iperf3
- 蓝牙：bluez5 + bluez-alsa（A2DP/HFP）
- 文件系统：ntfs-3g/dosfstools/parted 全套
- 调试：strace/gdb/perf/i2c-tools/evtest/modetest/lrzsz
- 基础图形：Weston 15.0.1 DRM compositor + Wayland 1.24 + mesa3d 26.1.2 **Panfrost**（GPU 已上主线）+ 拉丁字体
- 音频软栈：ALSA utils + pulseaudio 17.0（路由配置待 C 类 alsa-config）
- Qt5 5.15.18 应用（纯 Qt，无 webengine）

### Phase 2b — 换主线实现（B 类，丢 vendor blob）
- 丢 `ROCKCHIP_MALI` libmali blob，切 mesa3d Panfrost（GPU 仍工作，且开源）
- 丢独立 chromium，切 qt5webengine（拿到 web 引擎，绑 Qt5）
- exFAT 切 exfatprogs + 内核 in-tree exfat
- RKSCRIPT 胶水用 resize2fs + 自写 init/udev 规则重建
- post-build ldconfig 替代 `_GEN_LD_CACHE`

做完后 rootfs 能干：
- GPU 走全开源 Panfrost，EGL/GLES2/3.1 drop-in
- Qt 应用内嵌 chromium web 视图
- exFAT U 盘原生 r/w（内核驱动，性能优于 FUSE）
- 自动 resize / udev 权限规则用主线机制

### Phase 2c — 搬 vendor 硬件栈（C 类，拿回硬件加速能力）
按工作量从小到大：alsa-config（音频路由正）→ rktoolkit（如需 OTA）→ rga → mpp → gst-rockchip → rkaiq（摄像头）→ rknpu2（NPU）。板级资产（asound.state / init 脚本）抽进 overlay。

做完后 rootfs 能干：
- **硬件编解码**：GStreamer mppvideodec/mppvideoenc（H.264/H.265/VP9 硬解硬编，CPU 不再跑软解）、RGA 2D 加速
- **摄像头 ISP**：rkaiq ISP2 pipeline（主线 libcamera 暂不支持 ISP21）
- **音频路由正确**：HDMI/耳机/MIC 按板实际切换
- **NPU 推理**：rknpu2 + librknnrt（若产品用得到）
- 可选：4G 拨号（quectel-CM）、wifi/bt vendor 固件加载（如芯片需要）

> Phase 2a 结束即已是"可用的通用 Linux 板"；2b 是"开源合规 + 现代 web/GPU"；2c 才是"RK3568 硬件能力全开"。

---

## 7. forge board defconfig fragment 草案

放 `board/rk3568-atk/buildroot-external/` 下，主 defconfig 用 `#include` 引入。下面是 A 类汇总草稿，注释标 B/C 类 TODO。

```kconfig
# =============================================================================
# board/rk3568-atk/buildroot-external/fragments/rootfs-full.config
# RK3568 ATK — 完整功能 rootfs (Phase 2a, 纯 A 类)
# 原则: 只开 forge buildroot 2026.05 原生包; B/C 类另见 TODO 注释
# =============================================================================

# ---- 通用系统 / 工具链 (MVP 已接外部工具链, 此处仅系统设置) ----
BR2_aarch64=y
BR2_cortex_a55=y
BR2_ROOTFS_MERGED_USR=y
BR2_TARGET_GENERIC_HOSTNAME="forge-rk3568"
BR2_TARGET_GENERIC_ISSUE="Welcome to forge RK3568"
# BR2_TARGET_GENERIC_ROOT_PASSWD="<per-product-policy>"   # 不要硬编 "rockchip"
BR2_TARGET_LOCALTIME="Asia/Shanghai"
BR2_GENERATE_LOCALE="en_US zh_CN"
BR2_SYSTEM_ENABLE_NLS=y
BR2_CCACHE=y

# ---- /dev 与 init ----
BR2_ROOTFS_DEVICE_CREATION_DYNAMIC_EUDEV=y
BR2_PACKAGE_BUSYBOX=y
BR2_PACKAGE_BUSYBOX_SHOW_OTHERS=y
BR2_PACKAGE_BUSYBOX_CONFIG_FRAGMENT_FILES="board/rk3568-atk/buildroot-external/busybox.fragment"

# ---- 文件系统 / 分区 ----
BR2_TARGET_ROOTFS_EXT2=y
BR2_TARGET_ROOTFS_EXT2_4=y
BR2_TARGET_ROOTFS_EXT2_SIZE="auto"
BR2_PACKAGE_E2FSPROGS=y
BR2_PACKAGE_E2FSPROGS_FSCK=y
BR2_PACKAGE_E2FSPROGS_RESIZE2FS=y
BR2_PACKAGE_UTIL_LINUX=y
BR2_PACKAGE_UTIL_LINUX_MOUNT=y
BR2_PACKAGE_UTIL_LINUX_RFKILL=y
BR2_PACKAGE_DOSFSTOOLS=y
BR2_PACKAGE_DOSFSTOOLS_FATLABEL=y
BR2_PACKAGE_DOSFSTOOLS_FSCK_FAT=y
BR2_PACKAGE_DOSFSTOOLS_MKFS_FAT=y
BR2_PACKAGE_NTFS_3G=y
BR2_PACKAGE_NTFS_3G_NTFSPROGS=y
BR2_PACKAGE_PARTED=y
# [B] exFAT: 弃 legacy FUSE, 用内核 in-tree exfat + exfatprogs (内核侧 CONFIG_EXFAT_FS=y)
BR2_PACKAGE_EXFATPROGS=y
# [D] fatresize / pm-utils / netstat-nat / CONFIG_UDHCPD: 不开

# ---- USB / 输入 / 便捷 ----
BR2_PACKAGE_USBMOUNT=y
BR2_PACKAGE_INPUT_EVENT_DAEMON=y
BR2_PACKAGE_ANDROID_TOOLS=y

# ---- 网络: 连接管理 + WiFi + BT ----
BR2_PACKAGE_CONNMAN=y
BR2_PACKAGE_CONNMAN_WIFI=y
BR2_PACKAGE_CONNMAN_LOOPBACK=y
BR2_PACKAGE_CONNMAN_CLIENT=y
BR2_PACKAGE_WPA_SUPPLICANT=y
BR2_PACKAGE_WPA_SUPPLICANT_AP_SUPPORT=y
BR2_PACKAGE_WPA_SUPPLICANT_EAP=y
BR2_PACKAGE_WPA_SUPPLICANT_CLI=y
BR2_PACKAGE_WPA_SUPPLICANT_WPA_CLIENT_SO=y
BR2_PACKAGE_WPA_SUPPLICANT_PASSPHRASE=y
# BR2_PACKAGE_WPA_SUPPLICANT_AUTOSCAN is not set   # alientek.config:45 关省电
BR2_PACKAGE_HOSTAPD=y
BR2_PACKAGE_DNSMASQ=y
BR2_PACKAGE_IW=y
BR2_PACKAGE_BLUEZ5_UTILS=y
BR2_PACKAGE_BLUEZ5_UTILS_CLIENT=y
BR2_PACKAGE_BLUEZ5_UTILS_TOOLS=y
BR2_PACKAGE_BLUEZ5_UTILS_DEPRECATED=y
BR2_PACKAGE_BLUEZ_ALSA=y
BR2_PACKAGE_BLUEZ_ALSA_HCITOP=y
BR2_PACKAGE_BLUEZ_ALSA_RFCOMM=y
BR2_PACKAGE_OPENSSH=y
BR2_PACKAGE_OPENSSH_CLIENT=y
BR2_PACKAGE_OPENSSH_SERVER=y
BR2_PACKAGE_IPROUTE2=y
BR2_PACKAGE_IPERF3=y
BR2_PACKAGE_ETHTOOL=y
BR2_PACKAGE_IPUTILS=y
# [B/C] RKWIFIBT: 仅当 ATK wifi 芯片需 vendor nvram/MAC 才移植; 否则用 scripts/stage-rootfs.sh + S99wifi
# [B/C] QUECTEL_QCONNECTMANAGER: 仅当接了 4G 模组

# ---- CAN / eMMC ----
BR2_PACKAGE_LIBSOCKETCAN=y
BR2_PACKAGE_CAN_UTILS=y
BR2_PACKAGE_MMC_UTILS=y

# ---- 系统 observability / 模块 ----
BR2_PACKAGE_KMOD=y
BR2_PACKAGE_KMOD_TOOLS=y
BR2_PACKAGE_PROCPS_NG=y
BR2_PACKAGE_COREUTILS=y
BR2_PACKAGE_FILE=y
BR2_PACKAGE_GLIBC_UTILS=y
# [B] GLIBC_GEN_LD_CACHE: forge 无此符号; 改 post-build: <ldconfig> -r $(TARGET_DIR)

# ---- GPU: 主线 Panfrost (丢 libmali blob) ----
BR2_PACKAGE_MESA3D=y
BR2_PACKAGE_MESA3D_LLVM=y
BR2_PACKAGE_MESA3D_GALLIUM_DRIVER_PANFROST=y
BR2_PACKAGE_MESA3D_OPENGL_EGL=y
BR2_PACKAGE_MESA3D_OPENGL_ES=y
BR2_PACKAGE_MESA3D_GBM=y
BR2_PACKAGE_LIBDRM=y
BR2_PACKAGE_LIBDRM_ROCKCHIP=y
# OpenCL(RustiCL-on-G52 实验)/Vulkan(panvk-on-G52 实验): 默认 OFF, 与 vendor 一致

# ---- 显示 / Wayland ----
BR2_PACKAGE_WAYLAND=y
BR2_PACKAGE_WAYLAND_UTILS=y
BR2_PACKAGE_WESTON=y
BR2_PACKAGE_WESTON_DRM=y
BR2_PACKAGE_WESTON_DEMO_CLIENTS=y
BR2_PACKAGE_LIBDRM_INSTALL_TESTS=y

# ---- Qt5 (选 webengine 则绑 Qt5; 否则可迁 Qt6) ----
BR2_PACKAGE_QT5=y
BR2_PACKAGE_QT5BASE_GUI=y
BR2_PACKAGE_QT5BASE_WIDGETS=y
BR2_PACKAGE_QT5BASE_FONTCONFIG=y
BR2_PACKAGE_QT5BASE_JPEG=y
BR2_PACKAGE_QT5BASE_PNG=y
BR2_PACKAGE_QT5BASE_GIF=y
BR2_PACKAGE_QT5BASE_HARFBUZZ=y
BR2_PACKAGE_QT5BASE_SQL=y
BR2_PACKAGE_QT5BASE_SQLITE_QT=y
BR2_PACKAGE_QT5WAYLAND=y
BR2_PACKAGE_QT5DECLARATIVE=y
BR2_PACKAGE_QT5QUICKCONTROLS2=y
BR2_PACKAGE_QT5GRAPHICALEFFECTS=y
BR2_PACKAGE_QT5SVG=y
# [B] Web 引擎: 弃独立 chromium-wayland, 用 qt5webengine (内嵌 chromium)
BR2_PACKAGE_QT5WEBENGINE=y
BR2_PACKAGE_QT5WEBENGINE_ALSA=y
# BR2_PACKAGE_QT5WEBENGINE_PROPRIETARY_CODECS=y   # 如需 H.264/AAC
# [C] qt5quick3d: forge 无; 需 3D 则迁 Qt6 BR2_PACKAGE_QT6QUICK3D=y

# ---- 字体 ----
BR2_PACKAGE_FONTCONFIG=y
BR2_PACKAGE_DEJAVU=y
BR2_PACKAGE_LIBERATION=y
BR2_PACKAGE_FONT_AWESOME=y
# [B] CJK 主线替代:
BR2_PACKAGE_WQY_ZENHEI=y
# [C] 要思源黑体/思源宋体: 拷 reference/.../package/source-han-sans + noto 到 forge 后:
# BR2_PACKAGE_SOURCE_HAN_SANS_CN=y
# BR2_PACKAGE_NOTO_SANS_SC=y

# ---- 音频 (软栈; 路由配置待 C 类 rockchip-alsa-config) ----
BR2_PACKAGE_ALSA_PLUGINS=y
BR2_PACKAGE_ALSA_UTILS=y
BR2_PACKAGE_ALSA_UTILS_ALSACONF=y
BR2_PACKAGE_ALSA_UTILS_AMIXER=y
BR2_PACKAGE_ALSA_UTILS_APLAY=y
BR2_PACKAGE_LIBMAD=y
BR2_PACKAGE_PULSEAUDIO=y
BR2_PACKAGE_PULSEAUDIO_DAEMON=y
# [D] ALSA_UCM_CONF: forge 无, RK3568 用 rockchip-alsa-config

# ---- 多媒体: GStreamer 全家 (软解; HW 加速待 C 类 gst-rockchip) ----
BR2_PACKAGE_GSTREAMER1=y
BR2_PACKAGE_GST1_PLUGINS_BASE=y
BR2_PACKAGE_GST1_PLUGINS_BASE_INSTALL_TOOLS=y
BR2_PACKAGE_GST1_PLUGINS_BASE_PLUGIN_ALSA=y
BR2_PACKAGE_GST1_PLUGINS_BASE_PLUGIN_APP=y
BR2_PACKAGE_GST1_PLUGINS_BASE_PLUGIN_AUDIORATE=y
BR2_PACKAGE_GST1_PLUGINS_BASE_PLUGIN_AUDIOTESTSRC=y
BR2_PACKAGE_GST1_PLUGINS_BASE_PLUGIN_ENCODING=y
BR2_PACKAGE_GST1_PLUGINS_BASE_PLUGIN_OGG=y
BR2_PACKAGE_GST1_PLUGINS_BASE_PLUGIN_TCP=y
BR2_PACKAGE_GST1_PLUGINS_BASE_PLUGIN_THEORA=y
BR2_PACKAGE_GST1_PLUGINS_BASE_PLUGIN_VIDEOCONVERTSCALE=y   # 改名! 原 VIDEOCONVERT 是死符号
BR2_PACKAGE_GST1_PLUGINS_BASE_PLUGIN_VIDEORATE=y
BR2_PACKAGE_GST1_PLUGINS_BASE_PLUGIN_VIDEOTESTSRC=y
BR2_PACKAGE_GST1_PLUGINS_BASE_PLUGIN_VORBIS=y
BR2_PACKAGE_GST1_PLUGINS_GOOD=y
BR2_PACKAGE_GST1_PLUGINS_GOOD_JPEG=y
BR2_PACKAGE_GST1_PLUGINS_GOOD_PNG=y
BR2_PACKAGE_GST1_PLUGINS_GOOD_PLUGIN_AUDIOPARSERS=y
BR2_PACKAGE_GST1_PLUGINS_GOOD_PLUGIN_AUTODETECT=y
BR2_PACKAGE_GST1_PLUGINS_GOOD_PLUGIN_FLV=y
BR2_PACKAGE_GST1_PLUGINS_GOOD_PLUGIN_GDKPIXBUF=y
BR2_PACKAGE_GST1_PLUGINS_GOOD_PLUGIN_ID3DEMUX=y
BR2_PACKAGE_GST1_PLUGINS_GOOD_PLUGIN_MATROSKA=y
BR2_PACKAGE_GST1_PLUGINS_GOOD_PLUGIN_MULTIFILE=y
BR2_PACKAGE_GST1_PLUGINS_GOOD_PLUGIN_MPG123=y
BR2_PACKAGE_GST1_PLUGINS_GOOD_PLUGIN_PULSE=y
BR2_PACKAGE_GST1_PLUGINS_GOOD_PLUGIN_RTP=y
BR2_PACKAGE_GST1_PLUGINS_GOOD_PLUGIN_RTPMANAGER=y
BR2_PACKAGE_GST1_PLUGINS_GOOD_PLUGIN_RTSP=y
BR2_PACKAGE_GST1_PLUGINS_GOOD_PLUGIN_UDP=y
BR2_PACKAGE_GST1_PLUGINS_GOOD_PLUGIN_V4L2=y
BR2_PACKAGE_GST1_PLUGINS_GOOD_PLUGIN_VIDEOBOX=y
BR2_PACKAGE_GST1_PLUGINS_GOOD_PLUGIN_VIDEOCROP=y
BR2_PACKAGE_GST1_PLUGINS_GOOD_PLUGIN_VIDEOFILTER=y
BR2_PACKAGE_GST1_PLUGINS_GOOD_PLUGIN_VIDEOMIXER=y
BR2_PACKAGE_GST1_PLUGINS_BAD=y
BR2_PACKAGE_GST1_PLUGINS_BAD_PLUGIN_CAMERABIN2=y
BR2_PACKAGE_GST1_PLUGINS_BAD_PLUGIN_FAAD=y
BR2_PACKAGE_GST1_PLUGINS_BAD_PLUGIN_HLS=y
BR2_PACKAGE_GST1_PLUGINS_BAD_PLUGIN_KMS=y
BR2_PACKAGE_GST1_PLUGINS_BAD_PLUGIN_MIDI=y
BR2_PACKAGE_GST1_PLUGINS_BAD_PLUGIN_MPEGTSDEMUX=y
BR2_PACKAGE_GST1_PLUGINS_BAD_PLUGIN_MPEGTSMUX=y
BR2_PACKAGE_GST1_PLUGINS_BAD_PLUGIN_MPEGPSMUX=y
BR2_PACKAGE_GST1_PLUGINS_BAD_PLUGIN_ONVIF=y
BR2_PACKAGE_GST1_PLUGINS_BAD_PLUGIN_RTMP=y
BR2_PACKAGE_GST1_PLUGINS_BAD_PLUGIN_SDP=y
BR2_PACKAGE_GST1_PLUGINS_BAD_PLUGIN_VIDEOPARSERS=y
BR2_PACKAGE_GST1_PLUGINS_UGLY=y
BR2_PACKAGE_GST1_PLUGINS_UGLY_PLUGIN_ASFDEMUX=y
BR2_PACKAGE_GST1_PLUGINS_UGLY_PLUGIN_MPEG2DEC=y
BR2_PACKAGE_GST1_LIBAV=y                     # 建议补: codec 覆盖比 ugly 更全
BR2_PACKAGE_GST1_PLUGINS_BAD_PLUGIN_DEBUGUTILS=y
BR2_PACKAGE_LIBV4L=y
BR2_PACKAGE_LIBV4L_UTILS=y
# [C] HW 加速 (Phase 2c, 需先移植 vendor 包):
#   BR2_PACKAGE_ROCKCHIP_MPP=y + _ALLOCATOR_DRM=y
#   BR2_PACKAGE_ROCKCHIP_RGA=y
#   BR2_PACKAGE_GSTREAMER1_ROCKCHIP=y   (可能需 X11-optional patch)
#   BR2_PACKAGE_CAMERA_ENGINE=y         (camera_engine_rkaiq, ISP2/RK3568; libcamera 暂不支持 ISP21)
#   BR2_PACKAGE_ROCKCHIP_ALSA_CONFIG=y  (板级音频路由)

# ---- overlay / hooks (repoint 到 forge 自有目录) ----
BR2_ROOTFS_OVERLAY="board/rk3568-atk/buildroot-external/overlay"
BR2_ROOTFS_POST_BUILD_SCRIPT="board/rk3568-atk/buildroot-external/post-build.sh"
# [B] post-build.sh 里调: <external-ldconfig> -r $(TARGET_DIR)  (替 GEN_LD_CACHE)
# [C] overlay 放: asound.state, S00resizefs, S01alactl, udev rules, (S98rknn_server 待 rknpu2)
```

另建议拆 `configs/fragments/debug.config` + `benchmark.config`（§域 8 的 strace/gdb/perf/i2c-tools/glmark2/stress-ng 等），开发期 `#include`、发布关闭以瘦镜像。

---

### 附：关键判断速查
- **不原样搬 vendor 的**：`ROCKCHIP_MALI`(→Panfrost)、`CHROMIUM_WAYLAND`(→qt5webengine)、`RKSCRIPT`(→主线重建)、`EXFAT/EXFAT_UTILS`(→exfatprogs+内核)、`PM_UTILS`/`GLIBC_GEN_LD_CACHE`/`ALSA_UCM_CONF`/`NETSTAT_NAT`/`FATRESIZE`/`UNIXBENCH`(上游已删，drop)、`BLUEZ_UTILS_TOOLS`(死符号)、`CONFIG_UDHCPD`(无效行)、`ROCKCHIP`/`RK3566_RK3568` umbrella(config-only)。
- **必须搬 vendor 的（8 项）**：rockchip-mpp / rockchip-rga / gstreamer1-rockchip / camera-engine-rkaiq / rockchip-alsa-config / rknpu2(NPU) / rktoolkit(可选) / rkwifibt(硬件门控) + ATK 板级资产(overlay)。
- **版本统一更新**：凡 A 类都是 forge 2026.05 ≥ vendor 2021.11，无版本回退风险；gcc 15.3.1 / glibc 2.42 / headers 6.6.44 无阻断项（Panfrost 拉 LLVM 较重但可编）。

---

## 附: 完整对抗性评审原文 (critique)

验证完成。以下是我的对抗性评审意见。

## 评审报告 — 发现的问题 (按严重程度排序)

### 主要问题 1 — NPU (`npu2.config`) 虽然由 ATK 引入，但**未被任何领域**分析 (存在缺失)
ATK 的 `rootfs defconfig` 包含了 `npu2.config` (位于 `/home/charliechen/rk-forge/reference/rk3568/buildroot/configs/rockchip_atk_dlrk3568_defconfig:20` → `configs/rockchip/npu2.config:1` = `BR2_PACKAGE_RKNPU2=y`)，但在 8 个领域中均未对其进行列举。综合报告 §5 的 C 类表仅在提及时一笔带过。根据项目本身的记忆，NPU **是唯一没有主线等效物的 IP** — 它值得获得领域级的处理（包含 `defconfig` + 内核端说明 + 对 `S98rknn_server` / `ATK_INSTALLS` 的依赖），而不仅仅是综合报告中的一个表格行。证据: `package/rockchip/rknpu2/rknpu2.mk` (`RKNPU2_VERSION=1.0.0`, `SITE=external/rknpu2`, `local`)。**修复**: 添加第 9 个领域 (NPU) 或扩展基础领域，通过 `mainline_map` 条目枚举 `RKNPU2`+`librknnrt` (C 类，无主线等效物)。

### 主要问题 2 — libcamera/ISP21 的声明可能已过时/错误 (误分类风险，对应检查点 #4)
领域 4 和综合报告 §4 均声称: “主线 libcamera 的 `rkisp1 IPA` 针对的是 ISP1 (RK3399/RK3288)，**尚未覆盖 RK3568 的 ISP21**。” 这对于 libcamera **v0.7.1** 很可能是不成立的：上游 `rkisp1` 流水线处理程序涵盖了 ISP v1 和 v2/ISP21 (RK3566/RK3568/RK3562)；buildroot 中的 "Rockchip ISP1" 帮助文本是传统的命名（内核驱动本身命名为 `rkisp1`）。证据: forge 中包含 libcamera **v0.7.1** (`third_party/buildroot/package/libcamera/libcamera.mk`) 以及 `BR2_PACKAGE_LIBCAMERA_PIPELINE_RKISP1` (`Config.in:57`)；厂商甚至提供了包含完整流水线选项的 `configs/rockchip/libcamera.config`。报告**低估**了主线路径。**修复**: 将 libcamera `rkisp1` 提升为 RK3568 (B 类) 的真正替代方案（需针对 v0.7.1 IPA 的 ISP 版本矩阵进行验证）；将 `rkaiq` 保留为生产调优的 C 类路径，而非唯一选择。

### 主要问题 3 — forge buildroot 版本标签错误；树版本是 **2026.08-git**，而非 2026.05
`third_party/buildroot/Makefile:95` 中定义为 `export BR2_VERSION := 2026.08-git`。`CHANGES` 确认 2026.05 是最新 *发布* 版本 (2026 年 6 月 8 日)，该树处于 2026.08 开发周期。任务框架、8 个领域中的 7 个以及综合报告都写着 "2026.05"；只有 fs/font 领域正确标注为 "2026.08-git"。我验证的每一个软件包版本都与开发树匹配，因此任何检出 2026.05 *发布标签* 的人得到的软件包都会比报告所述的**更旧** —— 这存在可重复性问题。**修复**: 全文重新标记为 "2026.08-git (2026.05 后的开发版本)"；注意所有引用的版本都对应此开发树。(版本号本身均准确。)

### 主要问题 4 — 领域 5 的 Panfrost `defconfig` 缺少 `_LLVM` → 导致静默失效
领域 5 (display/UI) 中 `ROCKCHIP_MALI`→Panfrost 的 `defconfig_lines` 省略了 `BR2_PACKAGE_MESA3D_LLVM=y`。但是 `BR2_PACKAGE_MESA3D_GALLIUM_DRIVER_PANFROST` 是 `depends on BR2_PACKAGE_MESA3D_LLVM` (`third_party/buildroot/package/mesa3d/Config.in:209`)，且 `select BR2_PACKAGE_MESA3D_NEEDS_PRECOMP_COMPILER` (第 211 行)。如果没有 `_LLVM`，Panfrost 是不可选的 —— 这一行会静默地什么都不做。领域 3 和综合报告 §7 正确包含了 `_LLVM`。**修复**: 领域 5 的 `defconfig` 必须添加 `BR2_PACKAGE_MESA3D_LLVM=y` (并注意 LLVM 在工具链中的 `LLVM_ARCH_SUPPORTS` 依赖)。

### 次要问题 5 — `QUECTEL_QCONNECTMANAGER` 领域间分类冲突
领域 6 将其标记为 **B** (主线不同实现 = ofono+ModemManager)；领域 7 将其标记为 **C** (必须移植厂商)。综合报告 §5 列出它为 C。同一个软件包，却有两个不同的分类。**修复**: 统一确定一个主要分类（建议设为 C，并将 B 作为替代方案，因为厂商的 quectel-CM 是已验证良好的 QMI 流程，而 ofono/MM 更重）。

### 次要问题 6 — `SOURCE_HAN_SANS_CN` 分类分歧
领域 2 = B (wqy-zenhei 主线替代)；领域 5 = C。两者都承认 wqy-zenhei 作为权宜之计，但主要分类不同。**修复**: 声明一个统一的判定标准 (wqy-zenhei 足够 → B；产品需要确切的 Source Han 观感 → C)。

### 次要问题 7 — "libmali 1.9.0" 版本未验证
`ROCKCHIP_MALI_VERSION=master` 已验证 (`package/rockchip/rockchip-mali/rockchip-mali.mk`)；"1.9.0" 是上游 libmali 项目版本，未能在树内确认。影响较小（该 blob 正被弃用）。RK3568 的变体选择 `bifrost-g52/g13p0` 本身是**正确**的 (`rockchip-mali.mk:62-63`)。**修复**: 验证 `reference/rk3568/external/libmeli`，或修改为 "libmali (upstream ~1.9, ROCKCHIP_MALI_VERSION=master)"。

---

## 已正确处理的内容 (无问题)
- **所有抽检的 forge 版本均准确**: mesa3d 26.1.2, libdrm 2.4.134, weston 15.0.1, wayland 1.24.0, qt5base commit bebdfd54, gstreamer1 + all plugins 1.24.13, bluez5_utils 5.79, bluez-alsa 4.3.1, wpa_supplicant/hostapd 2.11, connman 2.0, pulseaudio 17.0, alsa-utils 1.2.16, alsa-plugins 1.2.12, libv4l 1.32.0, ntfs-3g 2022.10.3, parted 3.6, dosfstools 4.2, exfatprogs 1.2.9, font-awesome 7.2.0, fontconfig 2.17.1, sdl2 2.32.10, pipewire 1.6.6, ofono 2.18, libcamera v0.7.1。
- **所有“缺失/已弃用”的声明均经核实无误**: pm-utils, fatresize, netstat-nat, unixbench, procrank_linux, stressapptest, bluez-utils, ALSA_UCM_CONF, GLIBC_GEN_LD_CACHE (符号已移除), GLIBC_UTILS 依然存在 (`Config.in:71`)。
- **无厂商用户态软件包被误标为 A 类** (即任务所警告的错误): rockchip-mpp / rockchip-rga / gstreamer1-rockchip / camera-engine-rkaiq / rockchip-alsa-config / libv4l-rkmpp / rkwifibt / rktoolkit 均正确标记为 `forge_present:false`，且未在 forge `package/` 中发现。
- **bluez5_utils** 正确识别为存在 (scout 的“未命中”是 find 产生的伪影；已确认位于 `package/bluez5_utils/`)。
- **GStreamer 符号的细微之处均准确**: `VIDEOCONVERTSCALE` 是实际符号 (`gst1-plugins-base/Config.in:62`，原 VIDEOCONVERT 已弃用)；GOOD_JPEG/GOOD_PNG 缺少 `_PLUGIN_` 中缀 (第 15/21 行)，而 GOOD_PLUGIN_MPG123/_PULSE 则有 (第 272/370 行)。
- **qt5webengine 存在，qt6webengine 缺失，qt5quick3d 缺失，qt6quick3d 存在** — 均已确认 (验证了跨域 Qt5/Qt6 调用)。
- **connman 2.0 子选项** WIFI/LOOPBACK/CLIENT/ETHERNET 均存在。
- **Mali-G52 → Panfrost** 的核心技术声明是准确的：Panfrost 确实是 `depends on MESA3D_LLVM` (`Config.in:209`) 并选择了 precomp 编译器 → host-mesa3d + spirv-llvm-translator + spirv-tools (`mesa3d.mk:181-184`)。领域 3 的 GPU 分析是报告中最好的部分。

---

## 总体判断
**在版本/缺失调用和厂商软件包分类方面，该报告基本是可信的** (实质性内容验证无误)，但在发布前有四个真正的修复点：NPU 领域缺失 (主要)，libcamera/ISP21 的声明可能错误并驱动了错误分类 (主要)，"2026.05" 与 2026.08-git 的版本标签错误重复出现并影响可重复性 (主要)，以及领域 5 的 Panfrost `defconfig` 缺少 `_LLVM` 导致其静默失效 (主要)。解决这四个问题以及两个次要的分类协调后，报告即可作为工程行动的依据。