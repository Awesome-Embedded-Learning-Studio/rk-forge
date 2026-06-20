# pitfalls/07 — WiFi out-of-tree 驱动移植(RTL8733BU → Linux 7.1)

> 把主线无驱动的板载 WiFi 芯片靠移植 out-of-tree 驱动跑通的完整坑集。按**故障域**组织,
> 每条带板上证据(log 行号引 `document/logs/boot-sdl-202606201050.txt`)。完整执行过程见
> [notes/30](../notes/30-2026-06-20-wifi-rtl8733bu-port-complete.md),研究/roadmap 见
> [notes/29](../notes/29-2026-06-20-wifi-rtl8733bu-driver-port-roadmap.md)。

| 坑号 | 故障域 | 现象 | 根因/解 |
|---|---|---|---|
| #14 | make -p 文件列表提取 | `_PHYDM_FILES`/`_BTC_FILES` 为空,模块缺一半 | 必须给 `KERNELRELEASE=` + `src=` 才进 if 分支并解析 `include $(src)/*.mk` |
| #15 | Kbuild ccflags 路径宏引号 | 9× `<command-line>` '/' error + 2× hal_com "too few arguments" | 路径宏引号被 make→shell→gcc 剥,须 `\"` 转义 |
| #16 | kernel-trim 偷杀 WLAN | RTL8733BU 在 `.config` 里凭空消失 | `# CONFIG_WLAN is not set` 门控 WLAN_VENDOR_REALTEK,删之(pitfalls/06 同类) |
| #17 | cfg80211 ops wdev 漂移(6.14) | 11× ioctl_cfg80211.c incompatible pointer type | 7.1 把 9 个回调改 `wireless_dev*`,用 `_wdev` 转发器层 + `wdev_to_ndev` |
| #18 | buildroot PATH 含空格 | `make` 直接 Error 1(dependencies.mk PATH 检查) | WSL `/mnt/c` 路径剥掉,干净 PATH 再 make |
| #19 | 板测时序/命令 | `Network is down (-100)` / iw 打印 usage | ifup 在 scan 前;`iw dev wlan0 scan`(非 `iw wlan scan`) |

一句话主线:**Realtek 多芯片 Makefile 的两个隐性约定(KERNELRELEASE 门控 + `$(src)` include)
决定了文件列表提取法;ccflags 路径宏引号是 11 个编译错的的单点根因;cfg80211 在 6.14 把
9 个 ops 回调改成 wdev 是本次 API 移植的主体。** 板上全过。

---

## #14 — make -p 提取文件列表:必须给 KERNELRELEASE + src=

**背景**:驱动是 Realtek 经典 2803 行多芯片 Makefile,8733bu 的 187 个 `.o` 由
`$(MODULE_NAME)-y` 累积(`MODULE_NAME=8733bu`)。roadmap(notes/29)给的提取法是
`make -p KSRC=/dev/null ARCH=arm | grep ...`——**这法子有坑**。

**弯路**:
1. `make -p` 不带 `KERNELRELEASE` → 数据库只有 2015 行,无 `8733bu-y`。因为驱动 Makefile
   用经典 Kbuild 双分支:`ifneq ($(KERNELRELEASE),)`(L2572)门控整段 obj-/8733bu-y 构建
   块;直接 `make` 走 else 分支(standalone `modules:` 递归 `make -C $(KSRC) M=$(PWD)`)。
   → **必须传 `KERNELRELEASE=任意值`** 才进 if 分支。
2. 进了 if 分支后,`8733bu-y` 出现了,但 `_PHYDM_FILES`/`_BTC_FILES` 计数 = 0,`_HAL_INTFS_FILES`
   只有 15(应 49)。因为驱动 `include $(src)/rtl8733b.mk`(再 include `halmac-rs.mk`),
   而 standalone 时 `$(src)` 是空 → `include /rtl8733b.mk` 失败(被 `2>/dev/null` 吞)→
   8733b 专属 hal + phydm + btc 文件全丢。→ **必须传 `src=<驱动目录>`**。

**canonical 解**:
```
make -p KSRC=/dev/null ARCH=arm KERNELRELEASE=7.1.0 CONFIG_RTL8733BU=m src=$(pwd) 2>/dev/null
```
再用一个 `dump.mk`(`include` 驱动 Makefile,`dumpall:` 目标 `@echo "$(8733bu-y)"`)拿到
**完全展开**的 187 个 `.o` + `$(EXTRA_CFLAGS)`。逐个验证 187 个 `.c` 存在(0 missing)。

**教训**:Realtek Makefile 的两个隐性约定(KERNELRELEASE 门控 + `$(src)` 依赖)不在 roadmap
的提取法里,要自己撞出来。给全 `KERNELRELEASE` + `src` 才完整。

---

## #15 — Kbuild ccflags 路径宏引号:11 个编译错的的单点根因

**现象**:首遍编译 22 error 里 **11 个**是这引起:
- 9× `<command-line>: error: expected expression before '/' token`
- 2× `hal/hal_com.c: error: too few arguments to function 'rtw_read_efuse_from_file';
  expected 3, have 1`(以及 `rtw_read_macaddr_from_file`)

**根因**(单点):驱动 ccflags 里有路径宏
`-DEFUSE_MAP_PATH="/system/etc/wifi/wifi_efuse_8733bu.map"`、`-DWIFIMAC_PATH="/data/wifimac.txt"`、
`-DREALTEK_CONFIG_PATH="/lib/firmware/"`。生成 Kbuild Makefile 时**丢了反斜杠转义**(写成
`-DEFUSE_MAP_PATH="..."` 而非 `\"...\"`)。make→shell→gcc 链中 `"` 被剥 → gcc 收到
`-DEFUSE_MAP_PATH=/system/...` → 宏 `EFUSE_MAP_PATH` 展开成 `/system/etc/...`(裸的除号串)
→ 代码里 `rtw_read_efuse_from_file(EFUSE_MAP_PATH, ...)` 变成
`rtw_read_efuse_from_file(/system/etc/..., ...)` → 解析崩(`<command-line>` 错,因宏来自
命令行 -D;hal_com 的 "too few arguments" 是因为 `/system/...` 被解析器吞成非法参数)。

**canonical 解**:三个路径宏都 `\"` 转义,匹配驱动原 Makefile 的写法:
```
-DEFUSE_MAP_PATH=\"/system/etc/wifi/wifi_efuse_8733bu.map\"
-DWIFIMAC_PATH=\"/data/wifimac.txt\"
-DREALTEK_CONFIG_PATH=\"/lib/firmware/\"
```
一行 sed 修完 3 个,11 个 error 全消。**这是本次移植最高杠杆的单点修复**——9+2=11 个错同根因。

**教训**:Kbuild `ccflags-y` 里的字符串宏(`-DNAME="value"`)必须 `\"` 转义,否则引号在
make→shell→gcc 链丢失。诊断线索:错误定位在 `<command-line>` 而非 `.c` 文件 = 宏定义本身坏。

---

## #16 — kernel-trim 偷杀 WLAN(pitfalls/06 同类再现)

**现象**:kernel.config 加了 `CONFIG_RTL8733BU=m` + `CONFIG_WLAN_VENDOR_REALTEK=y`,但 olddefconfig
后 `.config` 里 RTL8733BU 凭空消失(构建时找不到驱动)。

**根因**:`kernel-trim.config` 有 `# CONFIG_WLAN is not set`,且 trim 在 merge 顺序最后
(multi_v7 → kernel.config → **kernel-trim** → kernel-compress),override 掉了。
`menuconfig WLAN`(drivers/net/wireless/Kconfig)→ `if WLAN` → source realtek →
`if WLAN_VENDOR_REALTEK` → RTL8733BU。**WLAN=off 整个 realtek 树不参与配置**。

这是 pitfalls/06(USB_SUPPORT 被 trim 偷杀)的**完全同类**——trim fragment 会静默杀子系统。

**canonical 解**:删 `kernel-trim.config` 里的 `# CONFIG_WLAN is not set`(注释里标明
"re-enabled for RTL8733BU")。**必须 grep 构建后的 `.config`**(`grep RTL8733BU .config`)
而非只看 fragment——pitfalls/06 的铁律:merge 顺序会骗你。

---

## #17 — cfg80211 ops wdev 漂移(6.14 MLO):API 移植主体

**现象**:11× `os_dep/linux/ioctl_cfg80211.c: error: ... from incompatible pointer type
'struct net_device *' ... expected 'struct wireless_dev *'`。

**根因**:内核 cfg80211 在 ~6.14(MLO/多链路重构)把 9 个 `cfg80211_ops` 回调的第二个参数从
`struct net_device *` 改成 `struct wireless_dev *`,并给 key 系加了 `link_id`。驱动(for6.18)
已有 `link_id`(6.1 加的),但**没跟 wdev 转换**。受影响:
`add_key`/`get_key`/`del_key`/`set_default_mgmt_key`/`add_station`/`del_station`/
`change_station`/`get_station`/`dump_station`。**不变**:`set_default_key`、`change_bss`、
`start_ap` 系(仍 netdev)。另 2 个 caller(`cfg80211_new_sta`/`cfg80211_del_sta`)也改 wdev。

**弯路(否决的方案)**:in-place 改 9 个多行 `#if (LINUX_VERSION_CODE >= ...)` 签名 + body 加
`ndev = wdev_to_ndev(wdev)`。风险高(每个签名跨 4-6 行带多个 `#if` 版本闸,body 要插变量声明)。

**canonical 解:wrapper 转发器层**(零风险,不动原函数)。在 `rtw_cfg80211_ops` struct 前插 9 个
`_wdev` 转发器,签名精确匹配内核 7.1 typedef,body 一行转发,用驱动已有的 helper:
```c
static int cfg80211_rtw_add_key_wdev(struct wiphy *wiphy, struct wireless_dev *wdev,
        int link_id, u8 key_index, bool pairwise,
        const u8 *mac_addr, struct key_params *params)
{ return cfg80211_rtw_add_key(wiphy, wdev_to_ndev(wdev), link_id, key_index, pairwise, mac_addr, params); }
```
(`wdev_to_ndev(w)` = `((w)->netdev)`,驱动 ioctl_cfg80211.h:271 已定义)
struct 9 处赋值改指向 wrapper(`.add_key = cfg80211_rtw_add_key_wdev,` …)。
caller 改 `cfg80211_new_sta(ndev->ieee80211_ptr, ...)`(`net_device.ieee80211_ptr` 是 wdev)。

**关键**:wrapper 签名必须**逐字匹配内核 7.1 typedef**(读 `include/net/cfg80211.h` 的
`struct cfg80211_ops` 拿权威签名,含 `link_id` 位置)。逐个核对原函数 7.1 下解析出的签名与
转发调用参数位置一致(del_station 的 `station_del_parameters`、get_key 的 callback 类型等)。
wrapper 用 `_wdev` 后缀 + 头注释说明是 6.14+ shim;本树唯一内核是 7.1,unconditional。

**教训**:out-of-tree 驱动跨大版本,ops 签名漂移是常态。读**目标内核 header 的 typedef** 移植,
别凭记忆。wrapper 层比 in-place 改多行 #if 签名更稳(原函数体零风险)。

---

## #18 — buildroot PATH 含空格:WSL 老坑再现

**现象**:`cd third_party/buildroot && make` 直接
`Your PATH contains spaces, TABs, and/or newline … make: *** Error 1`
(support/dependencies/dependencies.mk 的 PATH 检查)。

**根因**:WSL 默认 PATH 含 `/mnt/c/Program Files/...`(空格)。buildroot 拒绝含空格的 PATH。
kernel.config 阶段没碰这(notes/19 建最小 rootfs 时已撞过同类)。

**canonical 解**:剥掉含 `/mnt` 或空格的 PATH 项再 make:
```
PATH=$(echo "$PATH" | tr ':' '\n' | grep -vE '^/mnt| ' | paste -sd:) make
```
defconfig 用 `make rk3506_aes_defconfig`(不受影响);`make`(实际编译)用干净 PATH。

---

## #19 — 板测时序/命令:ifup 在 scan 前,iw 用 dev 子命令

**现象**(用户首测):
1. `iw wlan scan` → `iw` 打印一整页 usage(不是驱动问题)。
2. `iw wlan0 scan` / `iw dev wlan0 scan` → `command failed: Network is down (-100)`。

**根因**:
1. 命令笔误:`iw` 的 scan 是 `dev <devname> scan` 或简写 `<devname> scan`;`iw wlan scan`
   里 `wlan` 不是有效接口名 → iw 当无效命令打印 usage。正确:`iw dev wlan0 scan` 或 `iw wlan0 scan`。
2. `-100` = `ENETDOWN`,**接口没 up**。dmesg 里 `bup:0, hw_init_completed:0`(L660)——probe
   只做最小初始化,**完整 MAC/RF 上电(下固件、开射频、校准)在 `ip link set wlan0 up` 时才发生**。

**canonical 解**:
```
ip link set wlan0 up      # 触发 ndo_open → HAL 完整上电(dmesg 刷一堆 RTW: hw init)
iw dev wlan0 scan         # up 成功后扫
wpa_passphrase SSID PSK > /tmp/wpa.conf && wpa_supplicant -B -i wlan0 -c /tmp/wpa.conf
udhcpc -i wlan0
```
板上证据:用户 up + scan 后扫到 AP,wpa_supplicant + udhcpc 连上网(确认)。

**附带**:`regulatory.db failed to load`(L396)非阻塞——驱动有 rtk regdb 兜底,alpha2 暂
world;`iw reg set CN` 设国别或补 `regulatory.db`+`.p7s` 到 `/lib/firmware/`。

---

## patch-化方案(生产级可复现,板测已确认可做)

rtl8733bu/ 是 untracked 221 文件 vendor drop,新机器 checkout 不会有。做可复现:
1. **realtek 接线 2 行** → 小 patch 进 `patches/linux_mainline/`(像 patch 0001-0013 那样)。
2. **rtl8733bu/ vendor drop** → 写 `scripts/fetch-rtl8733bu-driver.sh`:
   - `git clone -b v5.15.12-264_for6.18 --depth=1 https://github.com/wirenboard/rtl8733bu`
     → 拷进内核树(去 `.git`)。
   - 拷 tracked 的 Kbuild Makefile 副本(放 `boards/` 或 `patches/` 下)覆盖驱动原 Makefile。
   - apply tracked 的 wdev-wrapper patch(对 `os_dep/linux/ioctl_cfg80211.c`)。
   - 写 `Kconfig`(`depends on USB && CFG80211`)。
   - 清 `.o`/`.cmd`/`.ko` 构建产物。
   不进 git 当 blob(对齐 forge "不 vendor blob" 原则);脚本幂等,可重跑。
3. Kbuild Makefile + wdev patch 作为 tracked 文件(脚本的输入),驱动源由脚本拉。

## 取证承诺
板上证据全引 `document/logs/boot-sdl-202606201050.txt` 真实行号;编译错引
`/tmp/wifi-work/build-pass1.log` 实际 error 分类(9+2+11)。无合成。
