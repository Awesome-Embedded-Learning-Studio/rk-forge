# Ch3 — WiFi（RTL8733BU）：把 out-of-tree 驱动搬进 7.1

> Ch2 把 USB 点亮后，板载那颗 RTL8733BU（USB `0bda:b733`，焊死在 OTG1、挂在 CH334R hub 后面）就在总线上冒头了（`usb 2-1.3`，Ch2 结尾那行）。但枚举出来和能联网差着整个驱动——主线内核里压根没有 RTL8733BU 的驱动，这章就是把它从无到有搬进来，最后落成 patch-化的生产级可复现链路。完整执行过程见 [notes/30](../../notes/30-2026-06-20-wifi-rtl8733bu-port-complete.md)，研究/roadmap 见 [notes/29](../../notes/29-2026-06-20-wifi-rtl8733bu-driver-port-roadmap.md)，坑的全集叙事见 [pitfalls/07](../../pitfalls/07-wifi-out-of-tree-port.md)。

## 前言：为什么这颗 WiFi 这么麻烦

Realtek 这类 WiFi 驱动向来是出了名的 out-of-tree：代码量大（两百多个源文件）、跟着内核 API 漂移、Kbuild 还是一套一份 Makefile 同时管所有 RTL8xxx 芯片的多芯片怪物。我们这颗芯片的主线核查笔者做过一遍——不是 `grep` 假象：内核是 Linux 7.1.0，`drivers/net/wireless` 里搜 `8733` 是空的，`0bda:b733` 没有任何驱动 claim，rtw89 顶到 8851B/8852 系就停了，rtl8xxxu 也不覆盖这颗。所以没有"找个 backport 目标"这条路，只有搬一份 out-of-tree 驱动。

上游社区有个 [wirenboard/rtl8733bu](https://github.com/wirenboard/rtl8733bu)（基于 Realtek `v5.15.12-264`，README 说测到 6.8），我们以它为底，往 7.1 上搬。主线内核"无驱动"这事实用户已授权松动——就这一颗——板载 WiFi 走纯主线 7.1 内核 + 移植驱动，不依赖 vendor BSP。集成方式是 in-tree `=m` 模块：放进内核树的 `drivers/net/wireless/realtek/rtl8733bu/`，编出 `8733bu.ko` 进 rootfs，switch_root 后 busybox `insmod`。为什么不是 `=y`？因为我们启动链是 initramfs → ubiprog → switch_root 到 UBIFS，`=y` 会在 initramfs 阶段 probe，那时 UBIFS 还没挂、固件不在、`request_firmware` 必失败；`=m` 推到 switch_root 之后加载，固件就在 `/lib/firmware/`。CFG80211 内建成 `=y`，保证模块依赖永远在。

## Phase 1：稳住 in-tree build（Kbuild 重写）

驱动原生的 2803 行多芯片 Makefile 直接拿来给主线内核用不行——它走 standalone 的 `make -C $(KSRC) M=$(PWD)` 递归，而这套路子在我们这台 WSL 上撞 `make` 自己 segfault（递归进那 2803 行 Makefile 时崩，跟内存/bc 都无关，可复现）。所以我们走主线稳定的 `obj-$(CONFIG)` 树内路径，把驱动的 Makefile 重写成 Kbuild 形态。

第一步是提取它到底要编哪 187 个 `.o`（8733b 配置下的全部源）。这一步有个不撞不知道的坑：roadmap 里给的 `make -p KSRC=/dev/null ARCH=arm` 法子提出来是**残的**——`_PHYDM_FILES`/`_BTC_FILES` 计数是 0，`_HAL_INTFS_FILES` 只有 15（应 49）。根因是 Realtek Makefile 用了经典 Kbuild 双分支：`ifneq ($(KERNELRELEASE),)`（L2572）门控整段 obj-/`8733bu-y` 构建块，不传 `KERNELRELEASE` 走 else 分支、根本进不去；进了分支，`include $(src)/rtl8733b.mk`（再 include `halmac-rs.mk`）这个语句的 `$(src)` standalone 时是空，`include /rtl8733b.mk` 失败被 `2>/dev/null` 吞掉，8733b 专属的 hal/phydm/btc 文件全丢。两道隐性约定，都得自己撞出来：

```
make -p KSRC=/dev/null ARCH=arm KERNELRELEASE=7.1.0 CONFIG_RTL8733BU=m src=$(pwd) 2>/dev/null
```

再写一个 `dump.mk` include 驱动 Makefile、`@echo "$(8733bu-y)"` 拿到完全展开的 187 个 `.o`（rtk_core 62 + _HAL_INTFS_FILES 49 + _OS_INTFS_FILES 17 + _PHYDM_FILES 54 + _BTC_FILES 3 + _PLATFORM_FILES 1 + rtw_mp 1）。逐个验证 187 个 `.c` 都在（0 missing）。然后生成 Kbuild Makefile：`obj-$(CONFIG_RTL8733BU) += 8733bu.o` + `8733bu-y := <187>` + `ccflags-y`（路径宏 `/tmp/...` 改成 `$(src)/...`），替换驱动原 2803 行 Makefile。

Kconfig 这边有个驱动自带的复制粘贴错：它写 `depends on MMC`——这明明是 USB 设备。改成 `depends on USB && CFG80211`，挂到内核树的 `drivers/net/wireless/realtek/Kconfig` 的 `if WLAN_VENDOR_REALTEK` 下。接线就是 patch [0016](../../../patches/linux/0016-wifi-rtl8733bu-wire-realtek.patch) 那 2 行：`realtek/Kconfig` 多一行 `source ".../rtl8733bu/Kconfig"`，`realtek/Makefile` 多一行 `obj-$(CONFIG_RTL8733BU) += rtl8733bu/`。

Phase 1 还有第二个 config 域的坑，跟 pitfalls/06 的 USB_SUPPORT 被偷杀是**完全同类**。`kernel-trim.config` 里有一行 `# CONFIG_WLAN is not set`，而 trim 在 merge 顺序最后（multi_v7 → kernel.config → kernel-trim → kernel-compress），它把 WLAN 整片关掉了——`menuconfig WLAN` → `if WLAN` → source realtek → `if WLAN_VENDOR_REALTEK` → RTL8733BU，WLAN 一关 realtek 树整片不参与配置，RTL8733BU 在 `.config` 里凭空消失。删那行，注释里标明"re-enabled for RTL8733BU"。这类坑的铁律：**grep 构建后的 `.config`**（`grep RTL8733BU .config`）确认，而不是 grep fragment——fragment 看着对、merge 顺序会骗你。

## Phase 2：API 移植 6.8 → 7.1（22 error → 0）

Kbuild 稳住，首遍 `-k` 宽幅编译 22 个 error。分三类，每一类都有真故事。

最大的一类（11 个 error）单点根因是 ccflags 路径宏引号丢失。驱动 ccflags 里有三个字符串宏：`-DEFUSE_MAP_PATH="/system/etc/wifi/wifi_efuse_8733bu.map"`、`-DWIFIMAC_PATH="/data/wifimac.txt"`、`-DREALTEK_CONFIG_PATH="/lib/firmware/"`。生成 Kbuild Makefile 时漏了反斜杠转义（写成 `"..."` 而非 `\"...\"`），make→shell→gcc 这条链一路把 `"` 剥掉，gcc 收到的就是 `-DEFUSE_MAP_PATH=/system/etc/...`，宏 `EFUSE_MAP_PATH` 展开成 `/system/etc/...` 这种裸除号串，代码里 `rtw_read_efuse_from_file(EFUSE_MAP_PATH, ...)` 就变成 `rtw_read_efuse_from_file(/system/etc/..., ...)`，解析直接崩。9 个表现为 `<command-line>: expected expression before '/' token`（错误定位 `<command-line>` 而非 `.c` 文件，就是宏定义本身坏的信号），2 个表现为 `hal/hal_com.c: too few arguments to function 'rtw_read_efse_from_file'`（解析器把 `/system/...` 吞成非法参数）。一行 sed 把三个宏全 `\"` 转义，11 个 error 一次消完，这是本次移植最高杠杆的单点修复。

第二类是 cfg80211 的 ops 签名漂移（也是 API 移植的真主体）。内核在 ~6.14（MLO/多链路重构）把 `cfg80211_ops` 里 9 个回调的第二个参数从 `struct net_device *` 改成 `struct wireless_dev *`，并给 key 系加了 `link_id`：`add_key`/`get_key`/`del_key`/`set_default_mgmt_key`/`add_station`/`del_station`/`change_station`/`get_station`/`dump_station`（`set_default_key`/`change_bss`/`start_ap` 系仍 netdev 不动）。wirenboard 那份 for6.18 已经带 `link_id`（6.1 加的），但没跟这次 wdev 转换，于是 11 处 `incompatible pointer type`。

笔者没去 in-place 改 9 个多行 `#if (LINUX_VERSION_CODE >= ...)` 签名 + body 插 `ndev = wdev_to_ndev(wdev)`——那种改法每个签名跨 4-6 行带多版本闸、body 还要插变量声明，风险太高。改法是写一组 wrapper 转发器：在 `ioctl_cfg80211.c` 的 `rtw_cfg80211_ops` struct 前插 9 个 `_wdev` 函数，签名逐字匹配内核 7.1 的 typedef（读 `include/net/cfg80211.h` 里 `struct cfg80211_ops` 拿权威签名，含 `link_id` 位置），body 一行转发，复用驱动已有的 helper `wdev_to_ndev(w)`（`((w)->netdev)`，`ioctl_cfg80211.h:271`）：

```c
static int cfg80211_rtw_add_key_wdev(struct wiphy *wiphy, struct wireless_dev *wdev,
        int link_id, u8 key_index, bool pairwise,
        const u8 *mac_addr, struct key_params *params)
{ return cfg80211_rtw_add_key(wiphy, wdev_to_ndev(wdev), link_id, key_index, pairwise, mac_addr, params); }
```

struct 那 9 处赋值改指向 wrapper（`.add_key = cfg80211_rtw_add_key_wdev,` …），2 个 caller（`cfg80211_new_sta`/`cfg80211_del_sta`）改成传 `ndev->ieee80211_ptr`（`net_device.ieee80211_ptr` 就是 wdev）。原函数体一行不动、零风险，wrapper 是 7.1 唯一内核、unconditional、加 `_wdev` 后缀 + 头注释说明是 6.14+ shim。教训：out-of-tree 驱动跨大版本，ops 签名漂移是常态，读**目标内核 header 的 typedef** 移植，别凭记忆。

第三类（`rtw_br_ext.c` 命中 `struct pppoe_tag` 无 `.tag_data`，7.x 移除 API）走预防性禁用：剥 `-DCONFIG_BR_EXT` 和 `-DCONFIG_BR_EXT_BRNAME`，这块桥接/NAT 是可选功能、不在 WiFi 数据路径上，没必要为它移植死代码（`rtw_br_ext.o` 仍编、`#ifdef` 出实际逻辑）。最终：零编译错误，零 modpost 错误。

## Phase 3-4：出 .ko，进 rootfs

`make modules`（树内，`RTL8733BU=m` 走 `obj-$()` 接线自动编）出 `8733bu.ko`。`modinfo` 验证：合法 ARM EABI5 模块，`name=8733bu`，`depends=` 空（CFG80211 内建、无依赖），vermagic 对得上我们这棵 7.1 树，**claim `0bda:b733`**——`usb_intf.c:316 USB_DEVICE_AND_INTERFACE_INFO(REALTEK, 0xB733, 0xff,0xff,0xff), .driver_info = RTL8733B`，insmod 必 bind 板上那颗芯片。

⚠️ 一个常被忘的步骤：`boot.img` 必须**用新 zImage 重打**。CFG80211 从 `m` 翻成 `=y` 进了 vmlinux，旧 boot.img 里那个 zImage 没有内建 cfg80211 符号，模块加载时符号对不上、直接挂。`pack-fit.sh` 重打完，再 `assemble-update.sh` 出 `update.img`。

rootfs 集成走 [`stage-rootfs.sh`](../../../scripts/stage-rootfs.sh)：`8733bu.ko` 注进 `lib/modules/`，固件 `rtl8733bu_fw` + `rtl8733bu_config` 进 `lib/firmware/`（这两个文件原在 ATK vendor-sdk overlay 里，forge 这边现在已经脱钩到本地 `firmware/rtl8733bu/`，跟 vendor-sdk 解绑），再放一个 [`S99wifi`](../../../board/aes/buildroot-external/overlay/etc/init.d/S99wifi) 开机脚本（busybox init 的 rcS 末尾 `insmod /lib/modules/8733bu.ko`，非致命、失败不挡启动）。buildroot defconfig 补 `wpa_supplicant`（带 NL80211）/`iw`/`wireless_tools`（libnl 自动跟上）。

buildroot 这步笔者撞了个 WSL 老坑：`make` 直接 `Your PATH contains spaces, TABs, and/or newline … Error 1`（`support/dependencies/dependencies.mk` 的 PATH 检查），原因是 WSL 默认 PATH 里漏进 `/mnt/c/Program Files/...` 这种带空格的项，buildroot 不接受。剥掉含 `/mnt` 或空格的 PATH 项再 make：

```
PATH=$(echo "$PATH" | tr ':' '\n' | grep -vE '^/mnt| ' | paste -sd:) make
```

`defconfig` 阶段不受影响，只在实编阶段需要这条。

## Phase 5：板上验证

烧 [`update-wifi-rtl8733bu.img`](../../logs/boot-sdl-202606201050.txt)（md5 `513800ae`，PROVISION-UBIPROG），全链路在 [boot-sdl-202606201050](../../logs/boot-sdl-202606201050.txt) 里逐行过：

```
S99wifi: loading RTL8733BU driver…
8733bu: loading out-of tree module taints kernel.        ← 模块加载成功
RTW: CHIP TYPE: RTL8733B                                  ← probe 进 HAL
RTW: VID = 0x0BDA, PID = 0xB733
RTW: rtl8733b_fw_dl Download Firmware from array success ← 固件从内建 array 下，v1.40 126664B
RTW: rtw_ndev_init(wlan0) / rtw_ndev_init(wlan1)         ← 并发模式双接口
S99wifi: 8733bu.ko loaded
```

`ip link` 实见 wlan0（MAC `4c:a3:8f:7b:45:99`）+ wlan1（`4e:a3:8f:7b:45:99`）。这里有个首测小插曲值得记——笔者第一次跑 `iw wlan scan`，iw 直接打印一整页 usage，看着像驱动没认；其实是命令笔误，`iw` 的 scan 是 `iw dev <devname> scan` 或简写 `iw <devname> scan`，`wlan` 不是有效接口名、iw 当无效命令处理。改 `iw dev wlan0 scan` 又撞 `command failed: Network is down (-100)`——`-100` 是 `ENETDOWN`，接口没 up。看 dmesg 里 `bup:0, hw_init_completed:0`：probe 阶段只做最小初始化，**完整 MAC/RF 上电（下固件、开射频、校准）在 `ip link set wlan0 up` 的 `ndo_open` 里才发生**。所以正确顺序是先 ifup 再 scan：

```bash
ip link set wlan0 up                                        # 触发 HAL 完整上电（dmesg 刷一堆 RTW: hw init）
iw dev wlan0 scan                                           # up 成功后才能扫
wpa_passphrase SSID PSK > /tmp/wpa.conf
wpa_supplicant -B -i wlan0 -c /tmp/wpa.conf
udhcpc -i wlan0
```

板上 up + scan 扫到 AP，wpa_supplicant + udhcpc 联网成功（用户确认）。

固件这边有个反直觉的发现：`/lib/firmware/rtl8733bu_fw` 这文件**没被用**——驱动的 HALMAC 走内建固件 array（`Download Firmware from array success`），文件在 rootfs 里只是兜底、留着无害。`regulatory.db failed to load` 那行也不是阻塞：cfg80211 的监管库文件没打进 rootfs，驱动有自带的 rtk regdb 兜底，alpha2 暂 `{255,255}` world，不挡 2.4G 扫描和连接；要完整信道支持，`iw reg set CN`（临时）或把 `regulatory.db` + `regulatory.db.p7s` 补进 `/lib/firmware/`（走 stage-rootfs 重出镜像）。

## 生产级收口：fork + fetch script

Phase 1-5 是"能跑"，但一个 untracked 的 221 文件 vendor drop 不算可复现——新机器 `git checkout` 不会有那坨东西。所以我们把它 patch-化了，把真相源收敛到**一处**。

驱动真相源 = forge fork [`Awesome-Embedded-Learning-Studio/rtl8733bu-linux-driver`](https://github.com/Awesome-Embedded-Learning-Studio/rtl8733bu-linux-driver)（branch `linux-7.1-port`，GPL-2.0-only）。整个 Realtek → wirenboard `v5.15.12-264_for6.18` → 7.1 移植链——静态 Kbuild Makefile（替换 2803 行原版）、USB && CFG80211 的 Kconfig、`ioctl_cfg80211.c` 的 9 个 wdev wrapper——全 bake 进 fork，fork 本身就是 ready-to-build 的驱动，clone 下来直接进内核树就能编。rk-forge 这边只留三件 tracked 的小东西：

- [patches/linux/0016](../../../patches/linux/0016-wifi-rtl8733bu-wire-realtek.patch)：那 2 行 realtek 接线（Kconfig source + Makefile obj-$）。它是真 git commit，树保持干净。
- [`scripts/fetch-rtl8733bu-driver.sh`](../../../scripts/fetch-rtl8733bu-driver.sh)：clone fork @ pin、strip `.git`、清构建产物、用 `.git/info/exclude`（不编辑 tracked `.gitignore`）把 `rtl8733bu/` 排除掉——`git status` 因此永远干净。幂等：`.forge-fetched` marker 记下 clone 的 commit SHA，重跑 no-op，`--force` 才刷新（fork 的 linux-7.1-port 推进后再用）。
- [`pins/rtl8733bu`](../../../pins/rtl8733bu)：tracked pin，格式 `<git-url> <ref>`，锁 fork 的 `linux-7.1-port` branch；想 bit-级 reproducible 就把 ref 换成 SHA 或 tag。

执行顺序是 `fetch-rtl8733bu-driver.sh` **先于** `apply-series.sh`——因为 patch 0016 要 source `rtl8733bu/Kconfig`，得 fetch 先把 Kconfig 落下来。验证：从 fork fetch 的树和板上的驱动源逐字相同（source identical），干净 v7.1 全 16-patch series apply 通过，`8733bu.ko` 从 fetched 树零错编出（4163516 B）。

固件这边同步脱钩：`stage-rootfs.sh` 不再硬依赖 ATK vendor-sdk 路径，固件落到 forge-local 的 `firmware/rtl8733bu/`（gitignored blobs，跟闭源 blob 同立场——不进仓、本地填）。运行时这俩文件其实没用（驱动走 array），best-effort 暂存。许可层面：fork 是 GPL-2.0-only（Realtek 头 + fork 根 LICENSE 都这么写），rk-forge 仓 MIT，fetch 引用不感染——这跟 Nixpkgs/Yocto 拉 GPL 源码而自身保持 MIT 是同一回事，我们不 relicense、也不能 relicense。

## 成功长这样

WiFi 全链路打通：驱动编通 → insmod → probe（`CHIP TYPE: RTL8733B`）→ 固件从 array 下 → wlan0/wlan1 创建 → ifup 触发完整上电 → scan 扫到 AP → wpa_supplicant + udhcpc 连上网。这颗主线没有的板载 WiFi，被我们用一份纯主线 7.1 内核 + 移植驱动点亮了，而且整套链路 fork + patch 化、新机器 clone + 一个脚本就能逐字重现。下一章换条路——RK3506 的 I2C/UART2 走一个主线 pinctrl 压根不认识的交叉开关，得补一个驱动 patch。我们 Ch4 见。
