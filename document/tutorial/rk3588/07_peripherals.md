# 外设收尾：WiFi 上桌，DVFS 落地

> [网络章](06_network.md) 把 GMAC0 点亮、tftp+nfs 的免烧录引擎架了起来，这块板的有线网络已经是开发基建。这一章咱们给全卷收尾，等着咱们的是两件事。咱们头一件把板载 WiFi 真正用起来，要的就是 GNOME 桌面摆脱网线：烧完镜像上电就能 ssh 进去。另一件把 CPU 的调频调压从原厂手里搬进主线，咱们要的是八个核按负载起伏，而不是定频裸跑。这两件事在咱们手里一头一尾：一个在用户态收官、另一个在内核电源管理里攻坚，咱们正好借它们合上这一卷。

## 本章定位：桌面齐了，还差两口气

咱们走到网络章这一步，这块板的主线桌面已经完整，咱们数下来是六样：

- 主线 SPL/U-Boot 引导
- 主线内核 v7.3.1
- LCD 与触摸
- Panthor GPU
- Ubuntu GNOME
- 有线网络加免烧录迭代引擎

剩下的 WiFi 和 DVFS 咱们各自开一场主戏、分量都不轻。

WiFi 是咱们眼里桌面像不像一台电脑这件事的最后一步。你看 GNOME 桌面还拖着一根网线，咱们看着总觉得差点意思，而且 rootfs 章结尾咱们算过这笔代价：改一行配置，咱们就得重打 3GiB 的 ext4、再重传 eMMC。板上的无线网通了还不够，咱们要的是通到烧录、上电、全程不碰串口、开发机上 ssh 直接进的程度，这样咱们才算把桌面做到真正无线可用。

DVFS 是异构 SoC 的基本素养，全名咱们记作 `Dynamic Voltage and Frequency Scaling`，咱们译作动态电压频率调节。它的白话版是这样：CPU 空闲时把频率和电压一起降下来省电降温，忙时咱们再一起拉上去。咱们连着说调频调压，是因为调压和调频必须成对——频率上去了电压跟不上，硅片在错误的时间采样，算出来的数就是错的。咱们拿到的 RK3588 走 big.LITTLE：小簇 4×A55、大簇 4×A76，咱们看到的大簇还要再分成两个簇。启动日志里 `Brought up 1 node, 8 CPUs` 那行咱们现在能读懂了。CPU0-3 咱们对上了 A55，CPU4-7 咱们对上了 A76。拓扑咱们在 [平台章](00_platform.md) 展开过。三个簇三条 CPU 电源轨、外加一个共享的 L3 缓存域，调频调压在这里是一组联动的事、咱们看不到哪个核能单干。

为什么这也要单开一章？因为本卷的主题在 DVFS 上演得最彻底：主线不是没有 cpufreq，通用的 `cpufreq-dt` 驱动谁都能伺候，可 RK3588 的原厂 BSP 偏偏在切一次频率这件事里塞了一整套事务语义，讲究的是哪路电动在前、哪路在后、要不要过桥、失败怎么滚回去。这些讲究主线通用品是一个都不做的，咱们只能亲手补。这和内核章的 rk860x、LCD 章的 VOP2 handoff 是同一类病：驱动都在，接口和时机咱们就是对不上。

## 主戏一：板载 WiFi，从认错芯片开始

### 这颗模组到底是谁

故事的开头是一次自我纠错。bringup（板子点亮初调）之前的仓库记录里，`board.yaml`、`kernel.config`、`packages.list` 三处都把板载 WiFi 记成 AP6xxx/brcmfmac——纯想当然，咱们谁也没在板上验证过。真要做 WiFi 了，咱们头一件事就是把芯片身份查实，咱们手里有五条证据（完整链在 [notes/58](../../notes/58-2026-08-15-rk3588-wifi-rtl8723du-rtw88-bringup.md)）：

```text
原厂内核 .config        RK_WIFIBT_CHIP="RTL8723DU"、CONFIG_RTL8723DU=m
迅为手册                板载 RTL8723，WiFi/蓝牙共用一组 USB2.0
原厂 DT                 sdmmc/sdhci 全部 no-sdio、无 WiFi 节点（没走 SDIO）
原厂驱动 usb_intf.c     {USB_DEVICE_AND_INTERFACE_INFO(0x0bda, 0xD723, ...)}
板上 lsusb              0bda:d723（Bus 4，经 1a40:0101 Terminus hub）
```

咱们判定它就是 Realtek 的 RTL8723DU。WiFi/BT combo 这个身份咱们也说直白些：一颗硅片同时管 WiFi 和蓝牙，对外咱们数到一个 USB 接口，这点咱们 `lsusb` 就能验证。它的物理形态值得单独记一笔：这颗模组接在板载的 Terminus USB hub（`1a40:0101`）后面，并没有直连 SoC 的 USB 口，所以 `lsusb` 里它的路径是 `4-1.1`——总线 4、hub 的 1 口、模组的 1 口。咱们调试 USB 设备问题时得看清自己在 hub 树的哪一层，不然咱们得多走不少弯路。这颗模组走的偏偏是 USB，这一点上咱们还得了个便宜：连设备树节点都免了。USB 设备是会自己枚举上报身份的，咱们在 DT 里没什么可声明的，原厂 DT 里没有 WiFi 节点倒是顺理成章。

一个批次差异的注记：2026-01 的厂商固件说明提到过适配 aic8800 模组，迅为的板子存在批次不同的可能。但本机的 `lsusb` 已经裁决为 RTL8723DU，所以咱们全篇按本机事实写。真遇到 AIC8800 的话，主线没有它的驱动，得走仓库的 OOT（树外驱动）路线（`board.yaml` 的 `wifi_driver` 字段就是干这个的）。

### 主线归属：rtl8xxxu 是错的，rtw88 才是归宿

Realtek 的 WiFi 在主线有两个驱动家族，咱们很容易站错队。第一次配置笔者就开了 `RTL8XXXU(+UNTESTED)`——惯性联想，因为 SDIO 版的 8723BS 一类归 rtl8xxxu。证伪的证据就在板上：rootfs 的 `/lib/firmware/rtlwifi/` 里，8723 家族 AU/BE/BS/BU/DE 各版的闭源固件 blob 全齐，唯独没有任何 `du` 的 WiFi 固件。因为 8723DU 的主线归宿是 rtw88 家族（Realtek 较新的统一驱动框架），咱们要准备的固件是 `rtw88/rtw8723d_fw.bin`，和 SDIO 版的 8723DS 共用同一颗。

`CONFIG_RTW88_8723DU` 在 6.2 就进了主线（Sascha Hauer 的系列），本板的 v7.1、v7.3.1 都在树内。固件清单咱们一起记下：WiFi 半边是 `rtw88/rtw8723d_fw.bin`，蓝牙半边咱们记作两个文件：`rtl_bt/rtl8723d_fw.bin` 和 `rtl_bt/rtl8723d_config.bin`（将来 btusb/btrtl 认领），这批固件咱们数过全在 rootfs 章的 `linux-firmware` 包里，一颗咱们都不用自己找。最终落在 [kernel.config](../../../boards/rk3588-topeet/kernel.config) 的配置块：

```text
CONFIG_WLAN_VENDOR_REALTEK=y
CONFIG_RTW88=y                           # menu 门，见下节
CONFIG_RTW88_CORE=y
CONFIG_RTW88_USB=y
CONFIG_RTW88_8723D=y
CONFIG_RTW88_8723DU=y
```

原厂的 standalone 驱动呢？留着当备胎。[board.yaml](../../../boards/rk3588-topeet/board.yaml) 的 `wifi_driver` 字段现在是空串，咱们看注释：rtw88 若在板上出幺蛾子，咱们就退回原厂驱动 `reference/.../rockchip_wlan/rtl8723du`，咱们走 aes 板用过的 OOT 注入路线就是。咱们默认走主线，但不把回退的路拆了。原厂与主线两边的完整对照（原厂走 `CONFIG_RTL8723DU=m` 的 standalone 驱动、主线走 rtw88、DT 全程无节点），咱们记在 [sdk-diff](../../sdk-diff-rk3588.md) 的 WiFi/BT 行。咱们猜一次、回一次原厂证据，家底咱们全收在那里。

### 两道配置暗雷，各吃掉一次烧录

**第一道：menuconfig 的门。** rtw88 的 Kconfig 是 `menuconfig RTW88` 包着 `if RTW88 … config RTW88_8723DU`。咱们只写四个子项 `=y`、不写门 `CONFIG_RTW88=y`，olddefconfig 偏偏会把子项整个静默丢弃。不可见符号在 `.config` 里连 `# not set` 的行都没有。`select` 的语义咱们也记下：它只向下拉依赖、不会向上开门。咱们在板上看到的症状：`.config` 里 `# CONFIG_RTW88 is not set`、四个子项无影无踪、镜像里根本没有驱动。

**咱们吃的第二道亏：固件加载器不认 .zst。** Ubuntu 26.04 的 linux-firmware 全部是 zstd 压缩，而 arm64 defconfig 不开 `FW_LOADER_COMPRESS`，于是 `request_firmware("rtw88/rtw8723d_fw.bin")` 只找裸名、看不见旁边的 `.bin.zst`。咱们在板上看到的症状：

```text
rtw88_8723du 4-1.1:1.2: Direct firmware load for rtw88/rtw8723d_fw.bin failed with error -2
... probe with driver rtw88_8723du failed with error -22
```

咱们补上 `CONFIG_FW_LOADER_COMPRESS=y` + `CONFIG_FW_LOADER_COMPRESS_ZSTD=y`。这一开顺带救了蓝牙要用的 `rtl_bt/*.zst`，对已有的裸文件查找零影响。GPU 章讲固件时咱们走的是内建 raw blob 路线，倒是绕开了这个问题，WiFi 这边文件多、走 rootfs 的 linux-firmware 生态更合适，咱们就正面把压缩支持打开了——这其实是同一个问题的两种解法，取舍咱们分别在不同章节交代过。

固化下来的纪律：改完 kernel.config、烧板之前，咱们拿 `grep -E "^CONFIG_XXX" .config` 把期望行数数一遍。两道暗雷都是靠数行数抓住的，一次多余的烧录都没花。

### 驱动通了只是上半场：连接侧连环翻车

咱们到了驱动 probe 成功、`ip link` 里出现无线接口这一步，离连上网咱们还差得远，中间咱们还隔着六次翻车。六次翻车的完整病历在 [notes/58](../../notes/58-2026-08-15-rk3588-wifi-rtl8723du-rtw88-bringup.md) §5，咱们把每一次的教训浓缩在这里：

1. **接口名不是 wlan0。** systemd 的可预测命名给无插槽信息的 USB WiFi 起名 `wlx<MAC>`（本机 `wlx145d346ca1f5`），配置里写 `wlan0` 就没人接管。
2. **netplan 的 networkd renderer 只生成 `.network`、不写 wpa conf。** `wpa_supplicant@<iface>` 因为读不到配置退出 255，得自己 `wpa_passphrase` 生成 conf 再 enable。
3. **`/run/wpa_supplicant/` 目录不存在。** 服务能跑，wpa_cli 连不上控制接口，tmpfiles 补一行。
4. **RTL8723DU 是 2.4G 单频芯片。** 目标 SSID 叫 `Chenchen-5G`——5GHz 专属的 SSID 物理上够不着，`no-carrier` 的真凶就藏在名字里。换 2.4G 的 SSID 立刻通了。
5. **DNS 全挂。** 裸 IP 能 ping，域名解析失败。这份 rootfs 连 `systemd-resolved` 都不存在，`/etc/resolv.conf` 是 chroot 构建期的残留，兜底一行 `nameserver 223.5.5.5` 永久管用。
6. **netplan 的 `match.name` 只收标量。** 烤入版首烧翻车：配置里写了列表，boot 时 netplan generator 报 `expected scalar` 退出，整个网络配置没人生成。

第六条把咱们逼到了架构层面，整个 WiFi 栈咱们决定弃用 netplan。咱们弃用 netplan 的理由咱们写在第 2 条和第 6 条里：改名和凭据它是真的都想管，boot 时它偏偏不写 wpa conf（第 2 条），match 语法咱们又踩雷（第 6 条）。结果两头都想管、两头都漏。咱们终版选的是纯 systemd 三件套，咱们逐件看：

- `.link` 文件按内核名 `OriginalName=wlan*` 把名字定在 `wlan0`（rtw88 注册时用的就是 wlan0，咱们这个 `.link` 又排在 99-default.link 的 MAC 改名策略前面，`wlx` 那个名字从头就出不来）
- `.network` 给 wlan0 配 DHCP
- wpa conf 管凭据

还有一个连带动作容易漏：netplan 的 generator 原本顺手把 networkd 拉起来，弃用之后咱们必须自己 enable `systemd-networkd`——否则没人跑 DHCP，症状咱们看得清楚：IPv6 通、IPv4 没有。落成文件一共五个（也就是构建链往镜像里烤的那五件）：

```text
/etc/systemd/network/10-forge-wifi.link            OriginalName=wlan* → Name=wlan0
/etc/systemd/network/20-forge-wifi.network         Name=wlan0，DHCP=yes
/etc/wpa_supplicant/wpa_supplicant-wlan0.conf      凭据（PSK 按 WPA 规范 pbkdf2 现算）
/etc/.../wants/systemd-networkd.service → enable   弃用 netplan 后必须自己拉
/etc/tmpfiles.d/wpa_supplicant.conf                d /run/wpa_supplicant 0755 root root
```

### 烤进镜像：烧完上电即连

上面这些解法最终都固化进了构建链（[stage.py](../../../src/forge/stage.py) 的 `_provision_runtime_config`，与 rootfs 章讲的 stage/build 分工是同一套哲学：凭据这类必须避开 git 和缓存的东西，咱们交给 stage 注入）。stage-rootfs 解包后咱们直接往 staged 树里写五件套：

- `.link` 改名
- `.network` 配 DHCP
- wpa conf
- `systemctl enable` 等价的软链
- tmpfiles 的目录项

wpa conf 里的 PSK 咱们按 WPA 规范用 pbkdf2 现算，凭据咱们挡在 git 和缓存 tar 之外。DNS 咱们也在这时按 `network.yaml` 烤进 resolv.conf。

凭据从哪来：仓库根的 [user/ 凭据目录](../../../user/)咱们设了 gitignore，咱们只让 `*.example` 模板进 git。咱们复制 `wifi.yaml.example`、填上 SSID 和密码即可。一次性覆盖咱们留给环境变量 `FORGE_WIFI_SSID/PASS/DNS`，咱们让它压过一切文件配置。模板里那行注释咱们直接抄回来，因为它是第 4 条翻车的遗产：

```yaml
# 注意:模组若是单频 2.4G(如 RK3588 的 RTL8723DU),
# SSID 必须是 2.4G 那个 —— "-5G" 后缀的连不上(no-carrier 真凶)。
```

这一天的 WiFi 移植还顺带逼出了构建系统三处真 bug（[notes/58](../../notes/58-2026-08-15-rk3588-wifi-rtl8723du-rtw88-bringup.md) §4），因为咱们第一次全程以普通用户跑 `forge all`。这里的病根咱们看得清楚：fakeroot 重入用 `exec` 会把 forge 进程整个换掉，`all` 在 pack 之后静默断流（rootfs 章提过的那笔，这里修的根）。进程环境白名单漏了 `FAKEROOTKEY`，libfakeroot 挂在 mke2fs 上偏偏连不上 faked，errno 逐次浮动成了破案线索。还有上个 UID 留下的软链残留让 mke2fs 直接 EACCES。三修之后咱们用普通用户把 `forge all` 一键跑到底，后面那场 E2E 验收（烧完上电即连）咱们才能一口气跑完。

### 成功长这样

板上的收据咱们原样贴在这里，截自 2026-08-16 凌晨的 log（[202608160026.txt](../../logs/rk3588/202608160026.txt)，咱们一个字都没合成）：

```text
[    1.136659] usbcore: registered new interface driver rtw88_8723du
[    2.345884] rtw88_8723du 4-1.1:1.2: Firmware version 48.0.0, H2C version 0
...
[  OK  ] Started wpa_supplicant@wlan0.service - WPA supplicant daemon (for interface wlan0).
[  OK  ] Started systemd-networkd.service - Network Management.
```

第一行咱们看的是驱动注册，第二行 `4-1.1` 的路径正是 hub 后面的那颗模组、固件 48.0.0 加载成功，后两行是开机自动关联链在跑——注意服务名里的 `wlan0`，说明 `.link` 把名字定住了，咱们从头到尾没见过 `wlx`。

终验是 E2E 的一口气（当轮 update.img MD5 `0f3ce286`）：烧录、上电、全程不碰串口，咱们在开发机上 `ssh root@192.168.1.8` 免密直进——改名、关联、DHCP、公钥全部自动。板上咱们数下来单接口 `State: routable`，DHCP 咱们拿到 `192.168.1.8/24`，`iw scan` 咱们跑着正常，`ping baidu.com` 咱们量到 54ms。板验口径咱们照实记：**关联加 DHCP 通、2.4G 单频**。

蓝牙半边的配置和固件都齐了（`rtl_bt/rtl8723d_*.zst`），板验咱们还没做，咱们把它留在待办清单上。另有一条小尾巴咱们也记下：`regulatory.db` 还是加载失败（-2），结果 cfg80211 回退 world 监管域，扫描和关联倒是不受影响，监管库的签名与加载时序咱们留到真需要时再收。`faux_driver regulatory: Direct firmware load for regulatory.db failed with error -2` 这行 log 咱们从内核章时代就见过，WiFi 通了之后它依旧是那副样子。

### 三发 backport（回迁上游修复的补丁）的生与死：被上游吃掉也是战果

WiFi 收完尾咱们还留着一个注脚：维护补丁到底是什么。series 在 v7.1 时代背过三发 rtw88 的 backport（[0015](../../../boards/rk3588-topeet/patches/linux/0015-wifi-rtw88-increase-tx-report-timeout-to-fix-race-condition.patch)–0017），都是上游 v7.2 的 race 修复，其中 0015 修的就是 RTL8723DU：固件在后台扫描时会离通道超过 500ms，TX 状态报告的清理定时器提前触发，skb 咱们看到被提前清掉，上层其实把丢状态当成了丢包，结果 TCP 窗口塌缩，iperf3 的实测数咱们看到从约 90Mbps 掉到接近零。结果两秒才缓回来。咱们把报告超时加到 2500ms，病就断了。0016、0017 的细节咱们下一段展开。

0016 修的是 USB 写失败时的内存泄漏：URB 提交失败（设备拔出、内存不足）时完成回调永远不来，依赖回调释放的 skb 和聚合控制块就漏了。0017 是给 RX 描述符补校验的。这三发在咱们手里都是 race 加固，咱们给它们的定性很直白：不修不至于致命、修了才踏实。bringup 一路走下来咱们没见它们拦过路。咱们背上它们那天起，板上跑的就是修好的 rtw88。

2026-11-01 的 v7.3.1 rebase（[notes/122](../../notes/122-2026-11-01-rk3588-kernel-v7.3.1-rebase.md)）里，这三发咱们清了，schedutil/OPP 两发（0013/0014）咱们也清了，五发咱们一起从 series 删掉。咱们去 v7.3.1 树内数过，上游其实全都有，这五发活咱们不用干了。补丁文件咱们留着当档案，series 的注释里写明来龙去脉和上游 commit 号。

这件事咱们想单独讲讲：它给维护补丁定了位，咱们背在 series 里的每一发都是替上游挡问题的资产。背 backport 的每一天，板上跑的都是修好的代码。而 rebase 那天，咱们五发一起清仓，series 咱们从 24 缩到 20，上游每吃掉一发咱们的 series 就短一发。判断一个补丁该不该背、背到什么时候，咱们只看上游有没有、不看它是不是自己写的。这也解释了本卷补丁栈的形态：0011/0012/0018/0019 这类原厂语义移植上游短期不会收，咱们就把它们当长期资产背着。race 加固类的 0013–0017 咱们清楚上游早晚会有，咱们就把它们当流动资产用。

## 主戏二：DVFS，把原厂的事务语义搬进主线

### 看清原厂在切频率时到底做了什么

主线通用的 `cpufreq-dt` 路径咱们都熟，咱们数下来动作就两步。按 OPP 表咱们设新电压和设新频率，电源咱们全程只走一路。Rockchip 的 5.10 SDK 在 RK3588 上不是这么干的，它在 `rockchip-cpufreq.c` 和原厂的 OPP helper 里执行一个完整事务（[notes/57](../../notes/57-2026-08-12-rk3588-vendor-cpufreq-dvfs-port.md) 从原厂源码逐条整理）：

1. 每个簇同时管逻辑上的 `cpu`、`mem` 两路 supply。
2. 升频顺序：过桥时钟 → mem 电压 → CPU 电压 → SRAM 读裕量 → 目标频率。
3. 降频顺序：过桥时钟 → 读裕量 → 目标频率 → CPU 电压 → mem 电压。
4. 任何一步失败，恢复旧频率、旧读裕量、两路旧电压。
5. 大簇到达 2208MHz 时临时禁掉簇的 deep-idle 档（CPU 的深度睡眠状态，进出各要一笔时间，高频运行时贸然进出会误事），降回来再恢复。

三个术语咱们挨个展开。**OPP**（`Operating Performance Point`）咱们译作运行性能点，咱们在设备树里翻得到一张频率-电压对照表，咱们要 1.8GHz 它就配 850mV。**SRAM 读裕量**（`read margin`）指的是 CPU 内部 SRAM 的采样窗口参数，这个窗口是随电压走低、频率走高一路收窄的，原厂是按当前电压档调它的。这个调整咱们追到 GRF 寄存器这一层，litcore、bigcore、DSU 三组咱们都数过，这一层咱们在主线里没见过。**过桥时钟**（`intermediate clock`）指的是切换途中的安全中转频率，咱们切频时把频率挂到过桥时钟上、改电压、再到目标频率，咱们靠它躲开高压高频同时出现的非法组合。架构上咱们还得记一层事实：RK3588 的 CPU 时钟归 SCMI 管，时钟请求是经 ATF 固件转发、不直接摸 CRU 寄存器的，过桥请求原厂是靠 rate 参数低位标志传给 SCMI 的。

随机挂死的方向咱们查明白了：主线 cpufreq 一开，咱们这块板就复现随机挂死。网络章 GMAC 冤案的案发名单上，1.198 秒首次换频的嫌疑人正是本章主角 cpufreq，当时咱们判它无辜，真凶是排在它后面的显示改频，欠它的正式交代咱们就在本章补上。挂死前的强信号咱们从内核章时代就在日志里见它晃，完整链条咱们写在 [notes/51](../../notes/51-2026-08-01-rk3588-ttyfiq-rk860x-i2c-hang-fix.md) 和 [notes/57](../../notes/57-2026-08-12-rk3588-vendor-cpufreq-dvfs-port.md) 里：

```text
cpu cpu4: _set_opp_voltage: failed to set voltage (...): -110
cpu cpu4: Failed to set regulator voltages: -110
cpufreq: __target_index: Failed to change cpu frequency: -110
```

-110 咱们查实是 `-ETIMEDOUT`，咱们把它翻成人话：切频率时去改电压，电压真的没有改成，超时了。内核章咱们修掉 rk860x 误领之后，这些报错咱们再没见过、随机挂死却并没有归零，咱们的读法是：驱动正确只是及格线、切频率这件事本身的语义还欠着。这组因果咱们拿无烧录的 A/B 定下来：

- `initcall_blacklist=panthor_init,cpufreq_dt_platdev_init`：稳定。
- 只拉黑 `cpufreq_dt_platdev_init`（Panthor 正常 probe，renderD128 在，桌面和登录稳定）：也稳定。
- cpufreq 放开：随机挂死复现。

GPU 咱们验下来不是必要条件。这次咱们要迁的是 CPUFreq/DVFS 路径。blacklist 只是隔离故障的工具，咱们不把它放进正式镜像。主线缺的咱们看下来是电源、频率、读裕量之间的事务语义，OPP 表倒是现成的（主线 DTS 有保守的固定表）。

移植的工程难点咱们碰到的是 API 断层：Linux 7.1 删掉了原厂 5.10 依赖的一体化 `set_opp` 接口，咱们没法把原厂代码逐行复制过来。新实现改用主线 `dev_pm_opp_config` 的 `config_regulators` 和 `config_clks` 两个回调，咱们把上面整套语义装进同一次 OPP 事务，再由新驱动自己注册 `cpufreq-dt` 的 platform device（`CPUFREQ_DT_PLATDEV` 关掉，通用和 Rockchip 两套并行注册路径在系统里是不存在的）。

### 0011：事务移植本体

[0011](../../../boards/rk3588-topeet/patches/linux/0011-cpufreq-rockchip-port-rk3588-vendor-dvfs-sequencing.patch)（2026-08-12）落了三块内容。`drivers/cpufreq/rockchip-cpufreq.c` 咱们数到约 640 行。咱们装进去的是双 supply 顺序、过桥时钟、读裕量更新、失败回滚，大簇到 2208MHz 的 cpuidle 协调咱们也一并装了。Kconfig 咱们加了 `CONFIG_ARM_ROCKCHIP_CPUFREQ`，kernel.config 里对应的三行立场（[kernel.config](../../../boards/rk3588-topeet/kernel.config)）：

```text
CONFIG_CPUFREQ_DT=y
CONFIG_ARM_ROCKCHIP_CPUFREQ=y
# CONFIG_CPUFREQ_DT_PLATDEV is not set
```

第三行是关键的一手：通用 platdev 注册路径显式关掉。装 OPP 回调的活咱们交给 Rockchip helper，`cpufreq-dt` 设备的注册咱们留给它亲自做，咱们要的就是系统里从头到尾只有一条注册路径。板级 DT 咱们补四个 GRF syscon，四个域的地址咱们列在下面：

- bigcore0：`fd590000`
- bigcore1：`fd592000`
- litcore：`fd594000`
- DSU：`fd598000`

三张 OPP 表咱们改成 cpu/mem 双 supply 写法，附上电压-读裕量对照表、`intermediate-threshold-freq = 1008000` 和大簇的 `rockchip,idle-threshold-freq = 2208000`。

双 supply 咱们照实说：它其实不是板上真有两颗稳压器。Topeet 板上每个簇的 `cpu-supply` 和 `mem-supply` 指向同一颗物理 RK860X，咱们与原厂板级 DT 核对过。咱们保住的是原厂 OPP 事务的接口和顺序，咱们并没有虚构第二颗芯片。原厂的大框架误读咱们也照实说：PVTM/binning/system-monitor 这一套咱们**有意不迁**，那套按芯片实测体质动态扩展超频 OPP 的机制，本次故障缺的咱们判定不是它，整包移入只会扩大故障面——这个后果咱们掂量过。主线 DTS 的保守固定表够用，这个取舍咱们留到 0018 再提——它到时候还会回来咬一口。

### 0012：8 毫秒定生死的 probe

0011 咱们烧进板子，DVFS 却压根没跑起来——而且不报错。病根藏在注册方式里：驱动用的裸 `module_init`，启动早期就要拿 SCMI 的 CPU 时钟和 I2C 上的 RK860X 调压器，驱动这边咱们读到的行为是谁还没就位就返回 `-EPROBE_DEFER`（-517），而 initcall 没有晚点再试的机制，一次 defer 在咱们板上就是永久放弃。板上 log 咱们看了，时机差是清清楚楚的：

```text
[    1.133390] failed to initialize RK3588 CPUFreq cluster for cpu0: -517
[    1.141205] arm-scmi arm-scmi.0.auto: Using scmi_smc_transport
```

驱动咱们看到死在 1.133 秒，SCMI 传输层 8 毫秒后的 1.141 秒才出现。这 8ms 之差咱们看得清楚，CPUFreq 从 0011 引入起咱们一次都没见它运行过。

[0012](../../../boards/rk3588-topeet/patches/linux/0012-cpufreq-rockchip-defer-safe-probe-and-panic-notifier.patch)（2026-08-15）把簇初始化从裸 initcall 挪进 platform driver 的 probe：initcall 只注册驱动和一个配对的 platform device，咱们读到的机制是：依赖之后返回 `-EPROBE_DEFER`，驱动核心会自动安排重试、咱们不用自己插手，SCMI 时钟和 RK860X 什么时候到齐什么时候继续。`cpufreq-dt` 设备的注册咱们仍然排在所有簇就绪之后，装好 OPP 回调、再起 `cpufreq-dt` 的顺序咱们不破。同一发里还移植了原厂的 panic notifier：panic 时把每个簇最后的频率和两路电压打出来，下次硬锁（hard lockup）捕获咱们靠 NMI 回溯加 ramoops，楔死瞬间的 DVFS 状态咱们就能记下来，后面两场戏咱们的主角都是它。

同轮还有一件配套动作咱们也记下：ramoops 的持久窗口从原厂位置的 `0x110000` 挪到了 `0x10000000`，因为主线 TPL/ddrbin 的启动链会清掉低地址那扇窗。取证装备和被取证的 DVFS 栈在同一发里各就各位，这个安排后面看很有远见——当时咱们只是按原厂语义顺手补的。

### 0018：2.208GHz 封顶，一个至今留着的诊断

0012 咱们修好注册，DVFS 真正跑起来的第一天，病情反而升级了：以前偶发的随机挂死，咱们看到它变成**每次启动都在 GNOME/GDM 加载时楔死**。现场咱们看到的是 CPU 全部静默，结果 IRQ 与 NMI 均无响应、最后 DW 看门狗复位。病情倒是从随机变成了确定，对排查反而是好事。

嫌疑犯咱们很快锁定到 2.4GHz 那档 OPP。原厂会用 PVTM/binning 把 2.4GHz 档限制在最高体质的芯片上，而 0011 有意没迁那套框架，咱们的表把 2.4GHz 无门槛地暴露在 1.0V。[0018](../../../boards/rk3588-topeet/patches/linux/0018-arm64-dts-rk3588-topeet-cap-big-2.208ghz-diagnostic.patch)（2026-08-15 深夜）咱们把它定位成教科书式的诊断补丁。咱们把两个大簇封顶在 2.208GHz@987.5mV，这个档位倒是原厂的高温钳位点，板上稳了就证实电源轨/体质理论，还楔咱们就往下排查（DSU 耦合、I2C 域）。补丁本身还有一个 DT 机制的细节值得学：OPP 阶梯节点住在被 include 的 `rk3588-opp.dtsi` 里，板级补丁干的是覆盖属性的活，所以只删板级的 2.4GHz 覆盖没用——底下还有单 supply 的基础版活着，必须用 `/delete-node/` 把引用表里的节点整个删掉。

现状咱们照实写：封顶补丁至今仍在 series 里，2.4GHz 的 bin-gating 咱们没有移植。也就是说这块板的大簇当前按 2.208GHz 封顶运行，给大簇配正经体质门的活咱们只排进待办清单，这件事咱们还没有闭合。

### 0019：DSU/L3 频率耦合，三级时钟域的联动

封顶之后咱们还遇上一场。2026-08-16 凌晨的捕获（[202608160026.txt](../../logs/rk3588/202608160026.txt)）记下了完整现场，楔死咱们数到发生在 boot 后 16 秒。i2c 超时、hard LOCKUP、Kernel panic 那几行的原文咱们本章不再重贴，出处咱们归到内核章的取证装备，本章要贴的是 panic notifier 记下的三个簇临终状态：

```text
[   18.122181] cpu cpu0: cur_freq: 1608000 Hz, volt_vdd: 850000 uV, volt_mem: 850000 uV
[   18.129910] cpu cpu4: cur_freq: 2208000 Hz, volt_vdd: 987500 uV, volt_mem: 987500 uV
[   18.137638] cpu cpu6: cur_freq: 1800000 Hz, volt_vdd: 850000 uV, volt_mem: 850000 uV
```

RK860X 所在的 `fd880000.i2c` 在事务中途超时，簇领队 CPU 咱们看到接连硬锁，楔死经 L3 扩散到全机、这一层咱们在 log 里看得到。`ipd: 0x1b, state: 2` 这行的可读性咱们顺路注意一下：IPD 是 RK3x I2C 控制器的中断挂起寄存器，主线驱动超时只报一句干巴巴的 timeout，内核章的 0004 咱们从原厂移植过 IPD/state 日志路径，寄存器值咱们才能打出来，这发咱们没背的话，卡在哪个状态咱们是无从知道的。

根因是 0011 留下的一条缝：它让每个簇独立切换，可这颗 SoC 的 DSU/L3 缓存是骑在小簇电源轨上的，咱们看到大簇狂奔时 L3 跟着小簇一起降频，缓存的供给被掐断，多簇并发的 DVFS 负载咱们看到就出事。boot 期的 udev coldplug 咱们见到的正是同一种负载。[0019](../../../boards/rk3588-topeet/patches/linux/0019-cpufreq-rockchip-port-dsu-l3-frequency-coupling.patch)（2026-08-16）移植原厂的护栏，护栏的机制咱们列在下面：

- 小簇 policy 创建时，每个大簇往它挂一个 `FREQ_QOS_MIN` 请求
- 大簇每次调频完成，地板更到 `rounddown(freq × 4/5, 100kHz)`
- 大核跑多快，咱们就保证 L3 至少跟着吃到八成、永远不许它塌下去

DT 侧咱们给小簇表打 `rockchip,opp-shared-dsu` 标记。

咱们展开一句 FREQ_QOS（`Frequency QoS`）：指的是频率服务质量约束。咱们把它读作内核里某一方对某个 CPU 频率区间提出约束的通用机制，散热、devfreq 咱们看到也在用它，约束会直接进 cpufreq 决策的有效区间。咱们看中它的地方是护栏不经过任何自定义协议。大簇调频的回调是直接更新挂在小簇 policy 上的约束请求的，小簇的下次决策自然就被托底了。

DVFS 链到这里咱们就算讲齐了，RK3588 的三级时钟域咱们也真正联动了起来。图咱们画在下面：

```text
A76 big0（policy4，轨：RK8602）──┐
                                 ├─ FREQ_QOS_MIN 地板（freq × 4/5）─→ A55 小簇（policy0）＋ DSU/L3
A76 big1（policy6，轨：RK8603）──┘                                     ↑ 小簇的轨同时养着 L3
```

A76 大簇咱们数下来各自一条轨，A55 小簇咱们看到是一条轨外加养着 DSU/L3，频率策略上大簇咱们看到通过 QoS 地板托住小簇。上面的图咱们画的就是异构 SoC 的 DVFS 比单簇多出来的部分。

### 电压链的执行末端：rk860x，回到内核章

把 DVFS 的整条链摆直了看：cpufreq 收到调频请求，OPP 事务咱们看到按原厂顺序走，每次改电压咱们看到最终都落成 `fd880000.i2c` 上对 `RK8602`/`RK8603` 的一笔 I2C 写。**rk860x 调压器就是 DVFS 的执行末端**，8/16 那场 i2c 超时咱们见过，更早的 -110 调压失败咱们也见过，结果两场都透过它显形。

这正是内核章那场病的回声。当时主线 fan53555 咱们看到错误认领 RK860X，compatible fallback 倒是又让 RK8603 伪装成 RK8602，调频改压时 I2C 事务超时返回的其实就是 -110，咱们在内核章的 log 里见过它，外加主线 rk3x-i2c 超时后咱们看到它不做 SLV_HDSCL 检测、也不复位两个 reset domain，一次 SCL 咱们看到被拉住，结果控制器持续卡死。这个卡死咱们在内核章里排过。内核章的 [0004](../../../boards/rk3588-topeet/patches/linux/0004-regulator-rk860x-and-i2c-timeout-recovery.patch) 咱们拿来移植原厂的 rk860x 驱动和 I2C 恢复路径，fan53555 咱们关掉了，DVFS 能开工的前置条件咱们就此备齐。本章讲的是同一颗芯片在频率策略里的角色：它其实不只是被正确驱动。总线时序质量咱们看着它直接决定多簇并发调压的生死，咱们上 0019 的护栏，图的是减少多簇同时压一条 I2C 总线的场景烈度。

### 验收：DVFS 活着的证据长什么样

notes/57 给的验收清单咱们抓出来是三条：

- 启动参数里没有 `initcall_blacklist`
- 三组 policy 全部出现：policy0 管 A55 小簇、policy4 和 policy6 各管一个 A76 大簇
- 连续冷热启动和 GNOME 登录后，不再出现 `fd880000.i2c` 超时、调压失败和硬锁

第一遍体检咱们跑这个命令块：

```sh
cat /proc/cmdline
dmesg | grep -iE 'Rockchip RK3588 CPUFreq|cpufreq|rk3x-i2c|rk860|timeout|voltage|Hard LOCKUP'
find /sys/devices/system/cpu/cpufreq -maxdepth 1 -name 'policy*' -print
```

板子上咱们看 DVFS 活着，最直观的是 `stats/time_in_state`——每个频率档累计停留的毫秒数。8 月 15 日晚的会话（[202608152342.txt](../../logs/rk3588/202608152342.txt)）里，登录后 policy0（小簇）和 policy4（大簇之一）的记录是这样的：

```text
/sys/.../policy0/stats/time_in_state:1008000 3732
/sys/.../policy0/stats/time_in_state:1200000 82
/sys/.../policy0/stats/time_in_state:1416000 61
/sys/.../policy0/stats/time_in_state:1608000 65
/sys/.../policy0/stats/time_in_state:1800000 323
/sys/.../policy4/stats/time_in_state:1200000 3422
/sys/.../policy4/stats/time_in_state:1416000 111
/sys/.../policy4/stats/time_in_state:1608000 63
/sys/.../policy4/stats/time_in_state:1800000 45
/sys/.../policy4/stats/time_in_state:2016000 59
/sys/.../policy4/stats/time_in_state:2208000 560
```

小簇五档、大簇六档咱们看到全走过。2.4GHz 那档咱们用 0018 删掉了，表顶咱们收在 2208000。policy6 的记录咱们看到同构（同一个 log 咱们翻到 policy6 time_in_state 的 `2208000 398` 一行），光 2208 档咱们数到停了 398ms。调度器咱们看到真的在八个核上按负载搬频率。同一次会话里还跑了一个 DVFS hammer 压测脚本：8 核满载，每条 policy 一个 slammer 循环扫全档、随机跳档（顺带验了 governor 在 userspace、powersave、performance 之间来回切），dmesg 咱们实时过滤 I2C、调压、lockup 关键字。hammer 的终局咱们看到是一次 RCU stall panic。诊断咱们翻开看、8 核满载把 RCU 宽限期线程饿了七千多 jiffy，这个代价咱们算在压测姿势头上，但 panic 路径恰好让 0012 的 panic notifier 上了班：

```text
[  321.351523] cpu cpu0: cur_freq: 1008000 Hz, volt_vdd: 675000 uV, volt_mem: 675000 uV
[  321.359251] cpu cpu4: cur_freq: 2208000 Hz, volt_vdd: 987500 uV, volt_mem: 987500 uV
[  321.366987] cpu cpu6: cur_freq: 2016000 Hz, volt_vdd: 925000 uV, volt_mem: 925000 uV
```

楔死瞬间每个簇的频率和两路电压咱们一行不落地全拿到了。取证装备就在它该在的位置上等着，内核章那套方法论最直接的回报咱们在这看到了。

最终态的收据咱们贴 v7.1 线 eMMC 收官轮的 log（[finish/1.txt](../../logs/rk3588/finish/1.txt)，首行咱们核过是 `Linux version 7.1.0-00024`，根文件系统走的是 eMMC 的 `root=/dev/mmcblk0p3`）：

```text
[    0.283506] rockchip-rk3588-cpufreq rockchip-rk3588-cpufreq: failed to initialize RK3588 CPUFreq cluster for cpu0: -517
[    0.406284] cpufreq: cpufreq_policy_online: CPU0: Running at unlisted initial frequency: 816000 kHz, changing to: 1008000 kHz
[    0.415826] cpufreq: cpufreq_policy_online: CPU4: Running at unlisted initial frequency: 816000 kHz, changing to: 1200000 kHz
[    0.425903] cpufreq: cpufreq_policy_online: CPU6: Running at unlisted initial frequency: 816000 kHz, changing to: 1200000 kHz
[    0.426954] rockchip-rk3588-cpufreq rockchip-rk3588-cpufreq: Rockchip RK3588 CPUFreq transition helper initialized
```

第一行的 -517 其实是 0012 设计好的剧情，时序咱们分开看：

- 依赖没到齐，defer
- 143 毫秒后重试成功，三组 policy 上线
- 起机进 login

这些收据咱们收到这里，同一天深夜咱们还跑了 v7.3.1 rebase 的板验，走的是 TFTP+NFS 免烧录（验收记录在 [notes/122](../../notes/122-2026-11-01-rk3588-kernel-v7.3.1-rebase.md)），`0011`/`0012`/`0018`/`0019` 四发咱们看到零改动落在 v7.3.1 上。内核咱们换成新的一代，tftp 货架上咱们换一份 Image 加 dtb，免烧录咱们就直接复验 DVFS 这类内核侧行为，烧写一次咱们都不用。

诚实的边界咱们照例交代：0018 的封顶咱们还在，2.4GHz 的体质门咱们没做，口径咱们以仓库记录为准，这块咱们不外推。

## 卷尾：一块主线化的 RK3588 长什么样

八章咱们走完了，成果单咱们摊开，每条咱们都在板上验过：

- **平台与启动链**：认清这块板在主线生态里的位置——RK3588 是 Collabora 的旗舰，驱动齐全，真正的仗在板级 DT 和原厂语义的接缝上。
- **U-Boot 章**：主线 SPL + BL31 v1.54 + 主线 U-Boot 的链立起来，bootloop 的 blob 版本配对问题解开，rockusb Loader 模式点亮，烧写不再进 MaskROM。
- **内核章**：原厂板级 dts 译成主线的 `rk3588-topeet`，fan53555 误领 rk860x 的 I2C 卡死病治好，硬锁取证装备（ramoops、看门狗、buddy detector）就位，收官完成 v7.3.1 rebase。
- **LCD 章**：TC358775 桥的 init 序列 saga 走通，GT911 触摸出坐标，1024×600 出图进桌面。
- **GPU 章**：Panthor 加内建固件，renderD128 出现，GNOME 真渲染。
- **rootfs 章**：ubuntu-base 长成 Ubuntu 26.04 GNOME，属主与缓存两条纪律立起来，3GiB 镜像打进 eMMC。
- **网络章**：GMAC0 通，tftp+nfs 免烧录引擎把烧写从迭代环里拿掉。
- **外设章**：WiFi 烧完上电即连，DVFS 三簇联动按需调频调压。

合起来咱们数一遍这块板的家底。板子咱们用的是迅为 iTOP-RK3588，链路咱们从 BootROM 走到 GNOME 桌面：引导咱们用主线的 U-Boot，内核咱们用主线 v7.3.1。原厂语义补丁咱们只留薄薄一层，每一发咱们都写得出处，用户态咱们交给发行版原生的 Ubuntu。补丁栈咱们也过了一遍筛选：v7.3.1 rebase 之后 series 咱们停在了 20 发，上游已经收走的那五发清了仓，咱们数下来一半是原厂语义移植（FIQ、rk860x、DVFS 四发），另一半咱们看到是主线确实还没有的板级适配（面板、GT911、GMAC），series 注释里咱们逐发写着来历和去留理由。闭源残留咱们数过，都集中在链条最前端的 DDR init 和 BL31。公开生态的边界咱们看到就停在这里，本卷也一样越不过去。

还没做的咱们按 [平台章](00_platform.md) 的盘点（这块板现在到哪一步了）照写一遍：

- 蓝牙：配置固件已齐，板验待做
- NPU：主线 Rocket 驱动在，CONFIG 未开
- VPU/MPP：Hantro/rkvdec2 在，DT 未接
- RGA：主线无驱动，上游缺
- 摄像头：rkisp1 在，pipeline 未做
- PCIe/NVMe、USB3/Type-C、SD 卡、gmac1、RTC、音频

规律咱们读出来是：剩下的多半是把 DT 接上、把用户态配齐的活。这个深度咱们走到了，铺路的活咱们干起来越来越顺。真正的例外咱们只数出 RGA 这类上游确实没有的。RGA 其实要的是另一场上游化的仗，那套做法本卷已经示范过很多遍了。

写完这一卷咱们回头看，咱们最值得带走的是反复出现的那套方法论：主线都有驱动的时候咱们换问法，咱们不问“有没有”，咱们问“接口和时机对不对”。rk860x 咱们按这个思路理顺过，VOP2 handoff 咱们也走的是同一条路，DVFS 咱们更是把这套问答跑了一遍，连 WiFi 的 menuconfig 门和 .zst 固件咱们也没跳出这个问法。咱们把原厂 BSP 在这场移植里的角色也重新看一眼。它是咱们手里唯一完整的语义说明书，四个章节的解法咱们干下来是同一件事。说明书里对的那部分咱们逐章翻译成了主线的语言，说明书里错的部分（比如 fan53555 的误领）咱们指出来扔掉。RK3588 的主线化咱们看着还在路上，这块板的故事咱们讲到收线。下一块板咱们板上见。
