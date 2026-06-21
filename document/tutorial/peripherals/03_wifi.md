# Ch3 — WiFi（RTL8733BU）：把 out-of-tree 驱动搬进 7.1

> 本系列最硬的一章。板载这颗 RTL8733BU（USB `0bda:b733`，焊死，OTG1 经一个 CH334R hub），主线内核根本没驱动。我们的活是把一份 out-of-tree 的 Realtek 驱动（wirenboard 的 rtl8733bu，for 6.18）移植到主线 7.1，从 Kbuild 重写、API 漂移修复，到 rootfs 集成、板上联网验证，一整条链。完整记录见 [notes/30](../../notes/30-2026-06-20-wifi-rtl8733bu-port-complete.md)，坑的完整叙事见 [pitfalls/07](../../pitfalls/07-wifi-out-of-tree-port.md)。

## 前言：为什么这颗 WiFi 这么麻烦

Ch2 把 USB 点亮后，板载那颗 RTL8733BU 就枚举在总线上了（`usb 2-1.3`，就是 Ch2 结尾那行）。但"枚举出来"和"能联网"差着整个驱动——主线没有 RTL8733BU 的驱动，你得自己搞一份。Realtek 这类 WiFi 驱动向来是出了名的 out-of-tree：代码量大（两百多个源文件）、跟着内核 API 漂移、Kbuild 还是一套自己的多芯片怪物。所以这章不是"接个线"，是一场移植战役。

好消息是上游社区有个 [wirenboard/rtl8733bu](https://github.com/wirenboard/rtl8733bu)（基于 Realtek `v5.15.12-264`，测到 6.8），我们以它为底，往 7.1 上搬。

## Phase 1：稳住 in-tree build（Kbuild 重写）

驱动原生的 Makefile 是 2803 行的多芯片怪物，文件列表由 `$(MODULE_NAME)-y` 累积，直接拿来给主线内核用不行。第一步是提取它到底要编哪 187 个 `.o`。这里有个坑：提取时必须给 `KERNELRELEASE` + `src=`，否则驱动的 `ifneq ($(KERNELRELEASE),)` 门控进不去、`.mk` include 解析不到，phydm/btc 那批文件会丢。正确姿势是 `make -p ... KERNELRELEASE=7.1.0 src=$(pwd)`，再用一个 dump.mk 打印完全展开的 `$(8733bu-y)`，凑齐 187 个 `.o`。

然后用这 187 个文件生成一份干净的 Kbuild Makefile：`obj-$(CONFIG_RTL8733BU) += 8733bu.o` + `8733bu-y := <187个>` + `ccflags-y`。走主线稳定的 `obj-$()` 树内路径（out-of-tree 的 `M=` 在我们这台 WSL 上 make 会 segfault）。

这阶段还修了两个 bug：驱动自带 Kconfig 写了 `depends on MMC`（USB 设备的复制粘贴错），改成 `USB && CFG80211`；还有 `kernel-trim.config` 里一行 `# CONFIG_WLAN is not set`——它是 kernel.config 之后应用的，不删的话 RTL8733BU 直接消失（这种坑得 grep **构建后**的 `.config` 才看得出，grep fragment 看不出）。

## Phase 2：API 移植 6.8 → 7.1（22 error → 0）

Kbuild 稳住，首遍宽幅编译 22 个 error，分三类全解。最大的一类是 cfg80211 的 ops 签名漂移——7.1 把 `add_key/get_key/del_key/...` 一批回调从 `net_device*` 改成了 `wireless_dev*`（6.14 的 MLO wdev 转换），驱动还在用老签名。

我们没有笨乎乎地去 in-place 改 9 处多行 `#if`，而是写了一组 **wdev wrapper**：在 `rtw_cfg80211_ops` struct 前插 9 个 `_wdev` 转发器，签名匹配 7.1 的 typedef，body 一行 `return cfg80211_rtw_xxx(wiphy, wdev_to_ndev(wdev), ...);`（驱动本就有 `wdev_to_ndev` helper），struct 那 9 处赋值指向 wrapper。零风险、最小改动。剩下几类是 ccflags 路径宏（`EFUSE_MAP_PATH` 那几个）在 make→shell→gcc 链里引号被剥、展开成除号串，用 `\"` 转义修掉。

结果：零编译错误，零 modpost 错误。

## Phase 3-4：出 .ko，进 rootfs

`make modules` 出 `8733bu.ko`，合法 ARM EABI5 模块，`modinfo` 显示 `depends=` 空（cfg80211 内建）、vermagic 对、**claim `0bda:b733`**——insmod 必 bind 板上那颗芯片。

rootfs 集成靠 [`stage-rootfs.sh`](../../../scripts/stage-rootfs.sh)：把 `.ko` 注进 `lib/modules/`，固件文件进 `lib/firmware/`，再放一个 [`S99wifi`](../../../board/aes/buildroot-external/overlay/etc/init.d/S99wifi) 开机脚本（rcS 末尾 `insmod`，非致命）。buildroot defconfig 补 `wpa_supplicant`/`iw`/`wireless_tools`。别忘了 boot.img 要用新的 zImage（含 `CFG80211=y`）重打，否则板上跑旧内核、模块符号对不上。

## Phase 5：板上验证

烧 `update-wifi-rtl8733bu.img`，[boot-sdl-202606201050](../../logs/boot-sdl-202606201050.txt) 里这条链全通：

```
S99wifi: loading RTL8733BU driver…
8733bu: loading out-of-tree module taints kernel.        ← 加载成功
RTW: CHIP TYPE: RTL8733B
RTW: VID = 0x0BDA, PID = 0xB733
RTW: rtl8733b_fw_dl Download Firmware from array success  ← 固件走内建 array 下载
RTW: rtw_ndev_init(wlan0) / rtw_ndev_init(wlan1)          ← 双接口
```

`ip link` 实见 wlan0 + wlan1，`ip link set wlan0 up` → `iw dev wlan0 scan` 扫到 AP → `wpa_supplicant` + `udhcpc` 连上网。"板载 WiFi 走纯主线 7.1 内核 + 移植驱动、不依赖 vendor BSP"这个目标，板上达成。

## 生产级收口：fork + fetch script

Phase 1-5 是"能跑"，但要"生产级可复现"，光一个 untracked 的驱动 drop 不够。所以我们把它 patch-化了：驱动真相源 = forge fork [`Awesome-Embedded-Learning-Studio/rtl8733bu-linux-driver`](https://github.com/Awesome-Embedded-Learning-Studio/rtl8733bu-linux-driver)（branch `linux-7.1-port`，GPL-2.0-only）——Realtek → wirenboard → 7.1 移植（静态 Kbuild + Kconfig 修复 + wdev wrapper）全 bake 进 fork，fork 即 ready-to-build。rk-forge 这边只留 [0016](../../../patches/linux/0016-wifi-rtl8733bu-wire-realtek.patch) 那 2 行 realtek 接线 + [`fetch-rtl8733bu-driver.sh`](../../../scripts/fetch-rtl8733bu-driver.sh)（clone fork @ pin、strip .git、幂等）+ [`pins/rtl8733bu`](../../../pins/rtl8733bu)（tracked pin）。固件也从 ATK vendor-sdk 路径脱钩，落到 forge-local 的 `firmware/rtl8733bu/`。fork 是 GPL-2.0-only，rk-forge 仓 MIT，fetch 引用不感染。

> 一个小尾巴：[boot-sdl-202606201050](../../logs/boot-sdl-202606201050.txt) 里有 `regulatory.db failed to load`——cfg80211 的监管库文件没打进 rootfs。驱动自带 rtk regdb 兜底，alpha2 暂 `{255,255}` world，不挡 2.4G 扫描和连接；要完整信道支持，`iw reg set CN`（临时）或补 `regulatory.db` 进 rootfs。

## 成功长这样

WiFi 全链路打通：驱动编通 → insmod → probe → 固件下载 → wlan0/wlan1 → scan → 连网。RTL8733BU 这颗主线没有的 WiFi，被我们用一份纯主线 7.1 内核 + 移植驱动点亮了。下一章我们换条路——RK3506 的 I2C/UART2 走一个主线 pinctrl 压根不认识的交叉开关，得补一个驱动 patch。我们 Ch4 见。
