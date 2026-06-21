# notes/30 — 2026-06-20 — WiFi RTL8733BU 驱动移植完成(板上联网验证通过)

> 接 [notes/29](29-2026-06-20-wifi-rtl8733bu-driver-port-roadmap.md)(研究 + 5 阶段 roadmap)。
> 本篇记**执行全过程 + 板上结果 + 复现**。roadmap 是"打算怎么干",本篇是"实际怎么干成的、
> 踩了什么"。坑的完整叙事另见 [pitfalls/07](../pitfalls/07-wifi-out-of-tree-port.md)。

## TL;DR
板载 **RTL8733BU**(USB `0bda:b733`,焊死,OTG1 经 CH334R hub)主线无驱动 → 移植
`wirenboard/rtl8733bu`(`v5.15.12-264_for6.18`,测到 6.8)到我们的 **Linux 7.1**。
**板上全链路验证通过**:`8733bu.ko` 零错编通 → insmod → probe(`CHIP TYPE: RTL8733B`)
→ 固件下载成功 → wlan0/wlan1 创建 → ifup → scan 扫到 AP → **wpa_supplicant 连上网**。
"完全独立"目标(板载 WiFi 走纯主线 7.1 内核 + 移植驱动,不依赖 vendor BSP)达成。

板上证据:`document/logs/boot-sdl-202606201050.txt`。

## 执行全过程(Phase 1-5)

### Phase 1 — 稳住 in-tree build(Kbuild 重写)
1. **克隆**:`git clone -b v5.15.12-264_for6.18 https://github.com/wirenboard/rtl8733bu`
   → `third_party/explore/linux/drivers/net/wireless/realtek/rtl8733bu/`(去 `.git`,221 .c)。
2. **提取 187 个 .o 文件列表**(关键步,roadmap 的提取法有坑——见下):
   驱动原 Makefile 是 2803 行多芯片 Makefile,文件列表由 `$(MODULE_NAME)-y` 累积。
   **正确提取法**(避坑:必须给 `KERNELRELEASE` + `src=`,否则 `ifneq ($(KERNELRELEASE),)`
   门控进不去 + `include $(src)/rtl8733b.mk` 解析不到 → phydm/btc 文件丢失):
   ```
   make -p KSRC=/dev/null ARCH=arm KERNELRELEASE=7.1.0 CONFIG_RTL8733BU=m src=$(pwd) \
     2>/dev/null   # 进 KERNELRELEASE if 分支 + 解析所有 .mk include
   ```
   再用一个 dump.mk include 驱动 Makefile 打印**完全展开**的 `$(8733bu-y)`(187 个 .o)
   和 `$(EXTRA_CFLAGS)`。产物:rtk_core 62 + _HAL_INTFS_FILES 49 + _OS_INTFS_FILES 17
   + _PHYDM_FILES 54 + _BTC_FILES 3 + _PLATFORM_FILES 1 + rtw_mp 1 = **187**。逐个验证
   187 个 `.c` 都存在(0 missing)。
3. **生成 Kbuild Makefile**:`obj-$(CONFIG_RTL8733BU) += 8733bu.o` + `8733bu-y := <187>`
   + `ccflags-y += <展开的 EXTRA_CFLAGS>`(路径 `/tmp/...` → `$(src)/...`)。替换驱动原
   2803 行 Makefile。走稳定内核 `obj-$()` 路径(out-of-tree `M=` 在本 WSL segfault make,
   roadmap 已记)。
4. **修 Kconfig bug**:驱动自带 `depends on MMC`(USB 设备的复制粘贴错)→ `USB && CFG80211`。
5. **接线**:`realtek/Makefile` += `obj-$(CONFIG_RTL8733BU) += rtl8733bu/`;
   `realtek/Kconfig` += `source ".../rtl8733bu/Kconfig"`。
6. **kernel.config** += `CONFIG_CFG80211=y` / `CONFIG_WLAN_VENDOR_REALTEK=y` / `CONFIG_RTL8733BU=m`。

### Phase 1 坑 — kernel-trim 偷杀 WLAN(pitfalls/06 同类)
`kernel-trim.config` 有 `# CONFIG_WLAN is not set`。`menuconfig WLAN` → `if WLAN` →
source realtek → `if WLAN_VENDOR_REALTEK` → RTL8733BU。**不删这行,RTL8733BU 直接消失**。
grep **构建后**的 `.config` 确认(不是 grep fragment——merge 顺序 multi_v7→config→trim)。

### Phase 2 — API 移植(6.8 → 7.1),22 error → 0
首遍 `-k` 宽幅编译,22 个 error,分三类(全解):
- **9× `<command-line>: expected expression before '/' token`** + **2× hal_com.c
  "too few arguments"** = **11 个,同根因**:ccflags 的路径宏 `EFUSE_MAP_PATH`/`WIFIMAC_PATH`/
  `REALTEK_CONFIG_PATH` 引号在 make→shell→gcc 链中被剥 → 宏展开成 `/system/etc/...`(除号串)
  → 调用处解析崩。**修**:三个路径宏都用 `\"` 转义(`-DEFUSE_MAP_PATH=\"/system/...\"`)。
- **11× `os_dep/linux/ioctl_cfg80211.c`**:cfg80211 ops 签名漂移(7.1 把 add_key/get_key/
  del_key/set_default_mgmt_key/add_station/del_station/change_station/get_station/dump_station
  改成 `wireless_dev*`——6.14 MLO wdev 转换;`set_default_key`/`change_bss` 仍 netdev 不动)
  + 2 个 caller(cfg80211_new_sta/del_sta)。**修**:见下"cfg80211 wdev wrapper"。
- **BR_EXT**:首遍没报(已预防性禁用)。`rtw_br_ext.c` 命中 7.x 移除 API(`struct pppoe_tag`
  无 `.tag_data`)。剥 `-DCONFIG_BR_EXT` + `-DCONFIG_BR_EXT_BRNAME`(rtw_br_ext.o 仍编,代码
  `#ifdef` 出)。

**cfg80211 wdev wrapper**(替代 in-place 改 9 个多行 `#if` 签名,零风险):在
`ioctl_cfg80211.c` 的 `rtw_cfg80211_ops` struct 前插 9 个 `_wdev` 转发器,签名匹配内核 7.1
typedef,body 一行 `return cfg80211_rtw_xxx(wiphy, wdev_to_ndev(wdev), ...);`(驱动已有
`wdev_to_ndev(w)` = `((w)->netdev)` helper);struct 9 处赋值指向 wrapper。2 个 caller
`cfg80211_new_sta(ndev,...)` / `cfg80211_del_sta(ndev,...)` 改 `ndev->ieee80211_ptr`。

结果:**零编译错误,零 modpost 错误**。

### Phase 3 — 出 8733bu.ko
`make zImage` 生成 vmlinux 但**不生成 Module.symvers**(那是 `make modules` 的 modpost 产物,
且 vmlinux 必须含 CFG80211=y 才有 cfg80211 符号)。`make modules`(树内,RTL8733BU=m 走
`obj-$()` 接线自动编)→ **8733bu.ko 产出**。
- 验证:合法 ARM EABI5 模块;`modinfo` name=8733bu、**`depends=`(空,cfg80211 内建无依赖)**、
  vermagic `7.1.0-00015-gb2e98a648b7e-dirty`;
- **claim `0bda:b733`**(`usb_intf.c:316 USB_DEVICE_AND_INTERFACE_INFO(REALTEK, 0xB733,
  0xff,0xff,0xff), .driver_info = RTL8733B`)→ insmod 必 bind 板上芯片。

### Phase 4 — rootfs 集成
- **stage-rootfs.sh** 注入:`8733bu.ko` → `lib/modules/`;ATK overlay 的 `rtl8733bu_fw` +
  `rtl8733bu_config` → `lib/firmware/`(源:`vendor-sdk/buildroot/board/alientek/atk-dlrk3506/
  fs-overlay/usr/lib/firmware/`)。
- **S99wifi**(overlay `etc/init.d/`,0755):开机 `insmod /lib/modules/8733bu.ko`,非致命。
  busybox init 的 rcS 跑 `S??*` 数值序,S99 在最后。
- **buildroot defconfig** += `wpa_supplicant`(+ `NL80211`)/`iw`/`wireless_tools`(libnl 自动)。
- **boot.img 必须重打包**用新 zImage(含 CFG80211=y),否则板上跑旧内核模块符号不匹配。
  `pack-fit.sh` → `assemble-update.sh --provision` → `update.img`。

buildroot PATH 坑:`make` 拒编,因 WSL `/mnt/c/...` 路径含空格。
`PATH=$(echo $PATH|tr : \\n|grep -vE '/mnt| '|paste -sd:) make`。

### Phase 5 — 板上验证(log boot-sdl-202606201050)
烧 `update-wifi-rtl8733bu.img`(md5 `513800ae`)。关键行:
- L524 `S99wifi: loading RTL8733BU driver…`
- L525 `8733bu: loading out-of-tree module taints kernel.` ← 模块加载成功
- L572 `CHIP TYPE: RTL8733B`;L604 `VID = 0x0BDA, PID = 0xB733`
- L613 `rtl8733b_fw_dl Download Firmware from array success`(FW 126664B,v1.40)
  ← 固件走驱动**内建 array**(`/lib/firmware/rtl8733bu_fw` 没被用,留着兜底无害)
- L679 `rtw_ndev_init(wlan0)`;L683 `rtw_ndev_init(wlan1)` ← 并发模式双接口
- L688 `S99wifi: 8733bu.ko loaded`
- L699-702 `ip link` 实见 **wlan0 + wlan1**(MAC `4c:a3:8f:7b:45:99` / `4e:a3:8f:7b:45:99`)
- 之后 `ip link set wlan0 up`(ifup 触发完整 HAL/RF 上电)→ `iw dev wlan0 scan` 扫到 AP
  → `wpa_supplicant` + `udhcpc` **连上网**(用户确认)。

**首测小插曲**:`iw wlan scan` 笔误(`iw` 当无效命令打印 usage)→ 正确是 `iw dev wlan0 scan`;
scan 前忘了 `ip link set wlan0 up` → `Network is down (-100)`(ENETDOWN)。

## 板上发现(非阻塞)
1. **固件从 array 加载**,非 `/lib/firmware/` 文件(驱动的 HALMAC 走内建固件数组)。/lib/firmware
   的两文件是兜底,无害。
2. **`regulatory.db failed to load`**(L396):cfg80211 监管库文件没在 rootfs;驱动有 rtk regdb
   兜底,alpha2 暂 `{255,255}` world。要完整信道:`iw reg set CN`(临时)或补
   `regulatory.db`+`regulatory.db.p7s` 到 `/lib/firmware/`(走 stage-rootfs 重出镜像)。不挡 2.4G 扫描/连接。
3. PEB 3/4/5/173 的 ECC 弱写是已知 RW saga 行为,ubiprog 兜底(`failed=0`,L498),正常。

## 复现(rebuild)
```
source scripts/env-setup.sh
# 1. 内核 + 模块(CFG80211=y,RTL8733BU=m)
scripts/build-linux.sh                              # zImage + dtb(生成 vmlinux)
make -C third_party/explore/linux ARCH=arm CROSS_COMPILE=$CROSS_COMPILE modules   # Module.symvers + 8733bu.ko
# 2. boot.img 用新 zImage
scripts/pack-fit.sh
# 3. rootfs(buildroot 需干净 PATH)
cd third_party/buildroot && export BR2_EXTERNAL=$PWD/../bringup/buildroot-external \
  && make rk3506_aes_defconfig && PATH=$(echo $PATH|tr : \\n|grep -vE '/mnt| '|paste -sd:) make && cd -
bash scripts/stage-rootfs.sh                        # 注入 .ko + 固件 + S99wifi
bash scripts/pack-ubifs.sh
bash scripts/assemble-update.sh --provision
cp board/aes/out/update.img /mnt/d/DownloadFromInternet/update-wifi-rtl8733bu.img
```

## 改动清单(未 commit)
- **rk-forge 仓(tracked)**:[kernel.config](../../board/rk3506-evb/kernel.config) +
  [kernel-trim.config](../../board/rk3506-evb/kernel-trim.config) +
  [buildroot defconfig](../../board/aes/buildroot-external/configs/rk3506_aes_defconfig) +
  [stage-rootfs.sh](../../scripts/stage-rootfs.sh) + 新建
  [S99wifi](../../board/aes/buildroot-external/overlay/etc/init.d/S99wifi)。
- **explore/linux 内嵌 git**:`realtek/{Kconfig,Makefile}` 接线(2 行);`rtl8733bu/` 是
  **untracked vendor drop**(Kbuild Makefile + Kconfig 修复 + ioctl_cfg80211.c wdev wrapper 在里面)。
- 还原了被 `make O=.` 污染成 7 行 wrapper 的内核顶层 `Makefile`(`git checkout -- Makefile`)。

## 待办
- **✅ patch-化 DONE(2026-06-20,P1)+ fork 收口**:生产级可复现。**驱动真相源 = forge fork**
  `Awesome-Embedded-Learning-Studio/rtl8733bu-linux-driver`(branch `linux-7.1-port`,**GPL-2.0-only**):
  Realtek → wirenboard `v5.15.12-264_for6.18` → 7.1 移植(静态 Kbuild + USB&&CFG80211 Kconfig +
  cfg80211 wdev-ops wrapper)全 bake 进 fork,fork 即 ready-to-build 驱动。rk-forge 这边:
  - `patches/linux_mainline/0016-wifi-rtl8733bu-wire-realtek.patch` = realtek 接线 2 行(quilt,跟 0001-0015 同工艺)。
  - `scripts/fetch-rtl8733bu-driver.sh` = **简化版**:clone fork @ pin → strip .git → 清产物 → `.git/info/exclude` 忽略(无 overlay 步骤,移植已在 fork 里)。
  - `pins/rtl8733bu` = `<fork-url> linux-7.1-port`(tracked pin;SHA/tag 可锁发布)。
  - `drivers/rtl8733bu/` overlay **已从 rk-forge 删除**(搬进 fork,避免双源真相)。
  - **验证**:fetch 从 fork 逐字重现板上树(source identical)+ 幂等(SHA marker)+ 干净 v7.1 全 16-patch series apply + 8733bu.ko 从 fetched 树零错编出(4163516 B)。
  - **固件脱钩**:`stage-rootfs.sh` 不再硬依赖 ATK vendor-sdk 路径(原 line 60)→ forge-local
    `firmware/rtl8733bu/`(gitignored blobs,blob 同 rkbin-atk 立场)。kill-vendor-sdk WiFi 段闭环。
    固件运行时不用(驱动走内建 array),best-effort 暂存。
  - **许可**:fork GPL-2.0-only(Realtek 头 + fork 根 LICENSE);rk-forge 仓 MIT,fetch 引用不感染(类 Nixpkgs/Yocto)。不 relicense。
  - 详见 pitfalls/07 §patch-化方案 + fork 仓 README。
- **补 `regulatory.db`**(可选)。
- commit 整批改动(P1)。
