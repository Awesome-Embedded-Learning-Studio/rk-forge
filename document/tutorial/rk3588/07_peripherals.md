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

WiFi 是桌面像不像一台电脑这件事的最后一步。你看 GNOME 桌面还拖着一根网线，看着总觉得差了点意思，而且这笔代价算过：改一行配置，就得重打 3GiB 的 ext4、再重传 eMMC。板上的无线网通了还不够，要的是通到烧录、上电、全程不碰串口、开发机上 ssh 直接进的程度，这样才算真的把桌面做到无线可用。

DVFS 的全名记作 `Dynamic Voltage and Frequency Scaling`，是异构 SoC 的基本素养，中文的叫法是动态电压频率调节。它的白话版是这样：CPU 空闲时把频率和电压一起降下来省电降温，忙了再一起拉上去。笔者连着说调频调压，是因为调压和调频必须成对——频率上去了电压跟不上，硅片在错误的时间采样，算出来的数就是错的。这块 RK3588 走的是 big.LITTLE：小簇 4×A55、大簇 4×A76，而大簇还要再分成两个簇。启动日志里 `Brought up 1 node, 8 CPUs` 那行现在能读懂了：CPU0-3 对上 A55，CPU4-7 对上的是 A76。三个簇三条 CPU 电源轨、外加一个共享的 L3 缓存域，调频调压在这里是一组联动的事、看不到哪个核能单干。

为什么这也要单开一章？因为本卷的主题在 DVFS 上演得最彻底：主线不是没有 cpufreq，通用的 `cpufreq-dt` 驱动谁都能伺候，可 RK3588 的原厂 BSP 偏偏在切一次频率这件事里塞了一整套事务语义，讲究的是哪路电动在前、哪路在后、要不要过桥、失败怎么滚回去。这些讲究主线通用品是一个都不做的，笔者只好亲手补上。而它和 rk860x 调压、VOP2 时钟交接是同一类病：驱动都在，差的就是接口和时机。

## 主戏一：板载 WiFi，从认错芯片开始

### 这颗模组到底是谁

故事的开头是一次自我纠错。点亮初调之前的仓库记录里，`board.yaml`、`kernel.config`、`packages.list` 三处都把板载 WiFi 记成 AP6xxx/brcmfmac——纯想当然，其实谁也没在板上验证过。真要做 WiFi 了，头一件事就是把芯片的身份查实，手里的证据有五条：

```text
原厂内核 .config        RK_WIFIBT_CHIP="RTL8723DU"、CONFIG_RTL8723DU=m
迅为手册                板载 RTL8723，WiFi/蓝牙共用一组 USB2.0
原厂 DT                 sdmmc/sdhci 全部 no-sdio、无 WiFi 节点（没走 SDIO）
原厂驱动 usb_intf.c     {USB_DEVICE_AND_INTERFACE_INFO(0x0bda, 0xD723, ...)}
板上 lsusb              0bda:d723（Bus 4，经 1a40:0101 Terminus hub）
```

判定它就是 Realtek 的 RTL8723DU。WiFi/BT combo 的这个身份说直白些，其实就是一颗硅片同时管 WiFi 和蓝牙，对外数得到的就是一个 USB 接口，这一点你拿 `lsusb` 就能验证。它的物理形态值得单独记一笔：这颗模组接在板载的 Terminus USB hub（`1a40:0101`）后面，并没有直连 SoC 的 USB 口，所以 `lsusb` 里它的路径是 `4-1.1`——总线 4、hub 的 1 口、模组的 1 口。调试 USB 设备问题时得看清自己在 hub 树的哪一层，不然得多走不少的弯路。这颗模组走的偏偏是 USB，这一点上还得了个便宜：连设备树节点都免了。USB 设备是会自己枚举上报身份的，设备树里没什么可声明的，原厂 DT 里没有 WiFi 节点倒是顺理成章。

一个批次差异的注记：2026-01 的厂商固件说明提到过适配 aic8800 模组，迅为的板子存在批次不同的可能。但本机的 `lsusb` 已经裁决为 RTL8723DU，所以咱们全篇按本机事实写。真遇到 AIC8800 的话，主线没有它的驱动，得走仓库的 OOT（树外驱动）路线（`board.yaml` 的 `wifi_driver` 字段就是干这个的）。

### 主线归属：rtl8xxxu 是错的，rtw88 才是归宿

Realtek 的 WiFi 在主线有两个驱动家族，咱们很容易站错队。第一次配置笔者就开了 `RTL8XXXU(+UNTESTED)`——惯性联想，因为 SDIO 版的 8723BS 一类归 rtl8xxxu。证伪的证据就在板上：rootfs 的 `/lib/firmware/rtlwifi/` 里，8723 家族 AU/BE/BS/BU/DE 各版的闭源固件 blob 全齐，唯独没有任何 `du` 的 WiFi 固件。因为 8723DU 的主线归宿是 rtw88 家族（Realtek 较新的统一驱动框架），咱们要准备的固件是 `rtw88/rtw8723d_fw.bin`，和 SDIO 版的 8723DS 共用同一颗。

`CONFIG_RTW88_8723DU` 在 6.2 就进了主线（Sascha Hauer 的系列），本板的 v7.1、v7.3.1 都在树内。固件的清单一起记下：WiFi 半边是 `rtw88/rtw8723d_fw.bin`，蓝牙半边记下来的有两个文件：`rtl_bt/rtl8723d_fw.bin` 和 `rtl_bt/rtl8723d_config.bin`（将来 btusb/btrtl 认领），这批固件全在根文件系统侧的 `linux-firmware` 包里，一颗都不用你自己找。最终落在 kernel.config 的配置块：

```text
CONFIG_WLAN_VENDOR_REALTEK=y
CONFIG_RTW88=y                           # menu 门，见下节
CONFIG_RTW88_CORE=y
CONFIG_RTW88_USB=y
CONFIG_RTW88_8723D=y
CONFIG_RTW88_8723DU=y
```

原厂的 standalone 驱动呢？笔者留着当备胎。板级 `board.yaml` 的 `wifi_driver` 字段现在是空串，注释里写的是：rtw88 若在板上出幺蛾子，就退回原厂的那个驱动 `reference/.../rockchip_wlan/rtl8723du`，走小板用过的树外注入路线。默认走的是主线，但不把回退的路拆了。原厂与主线两边完整对照了一遍（原厂走 `CONFIG_RTL8723DU=m` 的 standalone 驱动、主线走 rtw88、设备树全程无节点），靠的就是这个口径。

### 两道配置暗雷，各吃掉一次烧录

**第一道：menuconfig 的门。** rtw88 的 Kconfig 是 `menuconfig RTW88` 包着 `if RTW88 … config RTW88_8723DU`。只写四个子项的 `=y`、不写门 `CONFIG_RTW88=y`，olddefconfig 偏偏会把子项整个静默丢弃。你在 `.config` 里连 `# not set` 的行都找不到。`select` 的语义也记下：它只向下拉依赖、不会向上开门。板上看到的症状：`.config` 里 `# CONFIG_RTW88 is not set`、四个子项无影无踪、镜像里根本没有驱动。

**吃的第二道亏：固件加载器不认 .zst。** Ubuntu 26.04 的 linux-firmware 全部是 zstd 压缩，而 arm64 defconfig 不开 `FW_LOADER_COMPRESS`，于是 `request_firmware("rtw88/rtw8723d_fw.bin")` 只找裸名、看不见旁边明明躺着的 `.bin.zst`。板上你看到的症状：

```text
rtw88_8723du 4-1.1:1.2: Direct firmware load for rtw88/rtw8723d_fw.bin failed with error -2
... probe with driver rtw88_8723du failed with error -22
```

补上的是 `CONFIG_FW_LOADER_COMPRESS=y` + `CONFIG_FW_LOADER_COMPRESS_ZSTD=y`。这一开顺带救了蓝牙要用的 `rtl_bt/*.zst`，对已有的裸文件查找零影响。GPU 那关的固件走的是内建 raw blob 路线，倒是绕开了这个问题。WiFi 这边的文件多，走根文件系统的 linux-firmware 生态更合适，你正面把压缩支持打开就行——同一个问题的两种解法，各有各的适用场景。

固化下来的纪律：改完 kernel.config、烧板之前，你拿 `grep -E "^CONFIG_XXX" .config` 把期望行数数一遍。两道暗雷都是靠数行数抓住的，一次多余的烧录都没花。

### 驱动通了只是上半场：连接侧连环翻车

到了驱动探测（probe）成功、`ip link` 里出现无线接口这一步，离连上网的路还差得远，中间隔着的翻车有六次。每一次的教训笔者浓缩在这里：

1. **接口名不是 wlan0。** systemd 的可预测命名给无插槽信息的 USB WiFi 起名 `wlx<MAC>`（本机 `wlx145d346ca1f5`），配置里写 `wlan0` 就没人接管。
2. **netplan 的 networkd renderer 只生成 `.network`、不写 wpa conf。** `wpa_supplicant@<iface>` 因为读不到配置退出 255，得自己 `wpa_passphrase` 生成 conf 再 enable。
3. **`/run/wpa_supplicant/` 目录不存在。** 服务能跑，wpa_cli 连不上控制接口，tmpfiles 补一行。
4. **RTL8723DU 是 2.4G 单频芯片。** 目标 SSID 叫 `Chenchen-5G`——5GHz 专属的 SSID 物理上够不着，`no-carrier` 的真凶就藏在名字里。换 2.4G 的 SSID 立刻通了。
5. **DNS 全挂。** 裸 IP 能 ping，域名解析失败。这份 rootfs 连 `systemd-resolved` 都不存在，`/etc/resolv.conf` 是 chroot 构建期的残留，兜底一行 `nameserver 223.5.5.5` 永久管用。
6. **netplan 的 `match.name` 只收标量。** 烤入版首烧翻车：配置里写了列表，boot 时 netplan generator 报 `expected scalar` 退出，整个网络配置没人生成。

第六条把人逼到了架构层面，整个 WiFi 栈就弃用了 netplan。弃用的理由就写在第 2 条和第 6 条里：改名和凭据它是真的都想管，boot 时它偏偏不写 wpa conf（第 2 条），match 语法又踩了雷（第 6 条），结果两头都想管、两头都漏。终版选的是纯 systemd 三件套，笔者逐件看：

- `.link` 文件按内核名 `OriginalName=wlan*` 把名字定在 `wlan0`（rtw88 注册时用的就是 wlan0，咱们这个 `.link` 又排在 99-default.link 的 MAC 改名策略前面，`wlx` 那个名字从头就出不来）
- `.network` 给 wlan0 配 DHCP
- wpa conf 管凭据

还有一个连带动作容易漏：netplan 的 generator 原本顺手把 networkd 拉起来，弃用之后就得你自己来 enable `systemd-networkd`——否则没人跑 DHCP，症状一眼就看清楚了：IPv6 通、IPv4 没有。落成文件一共五个（也就是构建链往镜像里烤的那五件）：

```text
/etc/systemd/network/10-forge-wifi.link            OriginalName=wlan* → Name=wlan0
/etc/systemd/network/20-forge-wifi.network         Name=wlan0，DHCP=yes
/etc/wpa_supplicant/wpa_supplicant-wlan0.conf      凭据（PSK 按 WPA 规范 pbkdf2 现算）
/etc/.../wants/systemd-networkd.service → enable   弃用 netplan 后必须自己拉
/etc/tmpfiles.d/wpa_supplicant.conf                d /run/wpa_supplicant 0755 root root
```

### 烤进镜像：烧完上电即连

上面这些解法最终都固化进了构建链（stage 阶段的 `_provision_runtime_config`：凭据这类必须避开 git 和缓存的东西，交给 stage 替你注入）。stage-rootfs 解包后直接往暂存树里写的就是这五件套：

- `.link` 改名
- `.network` 配 DHCP
- wpa conf
- `systemctl enable` 等价的软链
- tmpfiles 的目录项

wpa conf 里的 PSK，你按 WPA 规范用 pbkdf2 现算就好，凭据挡在 git 和缓存 tar 的外面。DNS 也在这时按 `network.yaml` 的内容烤进 resolv.conf。

凭据从哪来：仓库根的 user/ 凭据目录设了 gitignore，进 git 的只有 `*.example` 模板。你复制 `wifi.yaml.example`、填上 SSID 和密码即可。一次性覆盖留给了环境变量 `FORGE_WIFI_SSID/PASS/DNS`，它压过一切文件的配置。模板里那行注释笔者原样引在这里，因为它是第 4 条翻车的遗产：

```yaml
# 注意:模组若是单频 2.4G(如 RK3588 的 RTL8723DU),
# SSID 必须是 2.4G 那个 —— "-5G" 后缀的连不上(no-carrier 真凶)。
```

这一天的 WiFi 移植还顺带逼出了构建系统三处真 bug，因为笔者第一次全程以普通用户跑 `forge all`。病根你看得很清楚：fakeroot 重入用 `exec` 会把 forge 进程整个换掉，`all` 在 pack 之后就静默断流了，这次修的是根。进程环境白名单漏了 `FAKEROOTKEY`，libfakeroot 挂在 mke2fs 上偏偏连不上 faked，errno 逐次浮动成了破案线索。还有上个 UID 留下的软链残留让 mke2fs 直接 EACCES。三修之后你就能用普通用户把 `forge all` 一键跑到底，后面那场 E2E 的验收（烧完上电即连）才能一口气跑完。

### 成功长这样

板上的收据笔者原样贴在这里，截自 2026-08-16 凌晨的日志，一个字都不是合成的：

```text
[    1.136659] usbcore: registered new interface driver rtw88_8723du
[    2.345884] rtw88_8723du 4-1.1:1.2: Firmware version 48.0.0, H2C version 0
...
[  OK  ] Started wpa_supplicant@wlan0.service - WPA supplicant daemon (for interface wlan0).
[  OK  ] Started systemd-networkd.service - Network Management.
```

第一行看的是驱动注册，第二行 `4-1.1` 的路径正是 hub 后面的那颗模组、固件 48.0.0 加载成功，后两行是开机自动关联链在跑——你注意服务名里的 `wlan0`，说明 `.link` 把名字定住了，从头到尾没见过 `wlx` 的影子。

终验是 E2E 的一口气（当轮 update.img MD5 `0f3ce286`）：烧录、上电、全程不碰串口，开发机上你 `ssh root@192.168.1.8` 免密直进——改名、关联、DHCP、公钥全部自动。板上数下来单接口的状态是 `State: routable`，DHCP 拿到的是 `192.168.1.8/24`，`iw scan` 跑着是正常的，`ping baidu.com` 量到了 54ms。板验的口径照实记：**关联加 DHCP 通、2.4G 单频**。

蓝牙半边的配置和固件都齐了（`rtl_bt/rtl8723d_*.zst`），而板验还没做，就留在待办清单上了。另有一条小尾巴笔者也记下来了：`regulatory.db` 还是加载失败（-2），结果 cfg80211 回退 world 监管域，扫描和关联倒是不受影响，监管库的签名与加载时序留到真需要时再收。`faux_driver regulatory: Direct firmware load for regulatory.db failed with error -2` 这行日志从很早的时候就见过，WiFi 通了之后它依旧是那副样子。

### 三发回迁补丁的生与死：被上游吃掉也是战果

WiFi 收完尾还留着一个注脚：维护补丁到底是什么。主线补丁栈在 v7.1 时代背过三发 rtw88 的回迁补丁，都是上游 v7.2 的 race 修复，其中第一发修的就是 RTL8723DU：固件在后台扫描时会离通道超过 500ms，TX 状态报告的清理定时器提前触发，skb 被提前清掉了，上层把丢状态当成了丢包，结果 TCP 窗口塌缩，iperf3 的实测数从约 90Mbps 掉到接近零，隔了两秒才缓回来。报告的超时加到 2500ms，病就断了。另外两发的细节笔者下一段展开。

第二发修的是 USB 写失败时的内存泄漏：URB 提交失败（设备拔出、内存不足）时完成回调永远不来，依赖回调释放的 skb 和聚合控制块就漏了。第三发是给 RX 描述符补校验的。三发都是给 race 加固的，定性很直白：不修不至于致命、修了才踏实。点亮初调一路走下来笔者都没见它们拦过路。背上它们的那天起，板上跑的就是修好的 rtw88。

2026-11-01 的 v7.3.1 补丁重放里，这五发一起清掉了：笔者去 v7.3.1 树内数过，上游其实全都有，这五发活不用干了。补丁文件留着当了档案，来龙去脉写在档案的注释里。

这件事笔者想单独讲讲，它给维护补丁定了位——补丁栈里的每一发，都是替上游挡问题的资产。背回迁补丁的每一天，板上跑的都是修好的代码。补丁重放那天五发一起清了仓，栈就从 24 发缩到了 20 发，而上游每吃掉一发，栈就短了一发。判断一个补丁该不该背、背到什么时候，只看上游有没有、不看它是不是自己写的。这也解释了这套栈的形态：原厂语义移植类（FIQ、rk860x、DVFS 事务那一批）上游短期不会收，就当长期的资产背着。race 加固类上游早晚是会有的，就当流动的资产用。

## 主戏二：DVFS，把原厂的事务语义搬进主线

### 看清原厂在切频率时到底做了什么

主线通用的 `cpufreq-dt` 路径都熟，动作数下来就两步了：一步设的是新电压，一步设的是新频率，电源全程走的都是同一路。Rockchip 的 5.10 SDK 在 RK3588 上不是这么干的，它在 `rockchip-cpufreq.c` 和原厂的 OPP helper 里执行一个完整事务（笔者从原厂源码逐条整理如下）：

1. 每个簇同时管逻辑上的 `cpu`、`mem` 两路 supply。
2. 升频顺序：过桥时钟 → mem 电压 → CPU 电压 → SRAM 读裕量 → 目标频率。
3. 降频顺序：过桥时钟 → 读裕量 → 目标频率 → CPU 电压 → mem 电压。
4. 任何一步失败，恢复旧频率、旧读裕量、两路旧电压。
5. 大簇到达 2208MHz 时临时禁掉簇的 deep-idle 档（CPU 的深度睡眠状态，进出各要一笔时间，高频运行时贸然进出会误事），降回来再恢复。

三个术语笔者挨个展开。**OPP**（`Operating Performance Point`）中文的译名是运行性能点，设备树里翻得到一张频率-电压的对照表，要 1.8GHz 它配的就是 850mV。**SRAM 读裕量**（`read margin`）指的是 CPU 内部 SRAM 的采样窗口参数，这个窗口是随电压走低、频率走高一路收窄的，原厂是按当前电压档调它的。这个调整追到了 GRF 寄存器这一层，litcore、bigcore、DSU 三组笔者都数过，这一层在主线里是没有的。**过桥时钟**（`intermediate clock`）指的是切换途中的安全中转频率，它的用法是切频时把频率挂上过桥时钟、改电压、再到目标频率，靠它躲开高压高频同时出现的非法组合。架构上还得记一层事实：RK3588 的 CPU 时钟归 SCMI 管，时钟请求是经 ATF 固件转发、不直接摸 CRU 寄存器的，过桥请求原厂是靠 rate 参数低位标志传给 SCMI 的。

随机挂死的方向查明白了：主线 cpufreq 一开，这块板上就复现了随机挂死。之前查显示改频楔死网卡的那桩冤案时，案发名单上 1.198 秒首次换频的嫌疑人正是本章主角 cpufreq，当时判了它无辜，真凶是排在它后面的显示改频，欠它的正式交代笔者就在本章补上。挂死前的强信号在日志里早就在晃了，完整的链条是这三行：

```text
cpu cpu4: _set_opp_voltage: failed to set voltage (...): -110
cpu cpu4: Failed to set regulator voltages: -110
cpufreq: __target_index: Failed to change cpu frequency: -110
```

-110 的真身是 `-ETIMEDOUT`，给你翻成人话：切频率时去改电压，电压真的没有改成，超时了。rk860x 误领的问题修掉之后，这些报错笔者再没见过、随机挂死却并没有归零，读法是：驱动正确只是及格线、切频率这件事本身的语义还欠着。这组因果拿无烧录的 A/B 定下来：

- `initcall_blacklist=panthor_init,cpufreq_dt_platdev_init`：稳定。
- 只拉黑 `cpufreq_dt_platdev_init`（Panthor 正常 probe，renderD128 在，桌面和登录稳定）：也稳定。
- cpufreq 放开：随机挂死复现。

GPU 验下来不是必要的条件。这次笔者要迁的是 CPUFreq/DVFS 路径。blacklist 只是隔离故障的工具，不放进正式的镜像。主线缺的看下来是电源、频率、读裕量之间的事务语义，OPP 表倒是现成的（主线 DTS 有保守的固定表）。

移植的工程难点是 API 断层：Linux 7.1 删掉了原厂 5.10 依赖的一体化 `set_opp` 接口，笔者没法把原厂代码逐行复制过来。新实现改用主线 `dev_pm_opp_config` 的 `config_regulators` 和 `config_clks` 两个回调，把上面的整套语义装进同一次 OPP 事务，再由新驱动自己注册 `cpufreq-dt` 的 platform device（`CPUFREQ_DT_PLATDEV` 关掉，通用和 Rockchip 两套并行注册路径在系统里是不存在的）。

### 事务移植本体

这场移植（2026-08-12 落地）笔者装进去的是双 supply 顺序、过桥时钟、读裕量更新、失败回滚，大簇到 2208MHz 的 cpuidle 协调也一并装了，`drivers/cpufreq/rockchip-cpufreq.c` 数到约 640 行的体量。Kconfig 加了 `CONFIG_ARM_ROCKCHIP_CPUFREQ`，kernel.config 里对应的是三行：

```text
CONFIG_CPUFREQ_DT=y
CONFIG_ARM_ROCKCHIP_CPUFREQ=y
# CONFIG_CPUFREQ_DT_PLATDEV is not set
```

第三行是关键的一手：通用的 platdev 注册路径显式关掉。装 OPP 回调的活交给 Rockchip helper，`cpufreq-dt` 设备的注册留给它亲自做，要的就是系统里从头到尾只有一条注册路径。板级设备树补的是四个 GRF syscon，四个域的地址笔者列在下面：

- bigcore0：`fd590000`
- bigcore1：`fd592000`
- litcore：`fd594000`
- DSU：`fd598000`

这四个 syscon 节点的原文在板级设备树里长这样：

```dts
	/* RK3588 CPU/DSU SRAM read-margin GRFs used by vendor CPU DVFS. */
	bigcore0_grf: syscon@fd590000 {
		compatible = "rockchip,rk3588-bigcore0-grf", "syscon";
		reg = <0x0 0xfd590000 0x0 0x100>;
	};

	bigcore1_grf: syscon@fd592000 {
		compatible = "rockchip,rk3588-bigcore1-grf", "syscon";
		reg = <0x0 0xfd592000 0x0 0x100>;
	};

	litcore_grf: syscon@fd594000 {
		compatible = "rockchip,rk3588-litcore-grf", "syscon";
		reg = <0x0 0xfd594000 0x0 0x100>;
	};

	dsu_grf: syscon@fd598000 {
		compatible = "rockchip,rk3588-dsu-grf", "syscon";
		reg = <0x0 0xfd598000 0x0 0x100>;
	};
```

GRF 是 Rockchip 的"通用寄存器文件"（General Register File），syscon 是内核里"把一块寄存器区当纯读写口"的通用节点写法。这四个节点各自圈出一小块寄存器区：bigcore0/bigcore1 对两个 A76 大簇，litcore 对 A55 小簇，DSU 对共享的 L3 缓存域。名字里 `syscon@fd590000` 的 `fd590000` 就是这块寄存器区在总线上的起始地址，后面驱动调 SRAM 读裕量（采样窗口参数）就是透过这四个节点的地址去写对应寄存器。

三张 OPP 表咱们改成 cpu/mem 双 supply 写法，设备树里三张表各有代号：`cluster0_opp_table` 管 A55 小簇，`cluster1_opp_table` 和 `cluster2_opp_table` 各管一个 A76 大簇。每张表咱们都附上电压-读裕量对照表、`intermediate-threshold-freq = 1008000`，大簇的两张再补 `rockchip,idle-threshold-freq = 2208000`。大簇的 `cluster1_opp_table` 摘出来看（板级覆盖之后的样子）：

```dts
&cluster1_opp_table {
	rockchip,grf = <&bigcore0_grf>;
	volt-mem-read-margin = <
		855000 1
		765000 2
		675000 3
		495000 4
	>;
	low-volt-mem-read-margin = <4>;
	intermediate-threshold-freq = <1008000>;
	rockchip,idle-threshold-freq = <2208000>;

	opp-1200000000 {
		opp-microvolt = <675000 675000 1000000>,
				<675000 675000 1000000>;
	};

	...（其余频率档同款，末尾另有一处 /delete-node/，封顶那节单独说）
};
```

`opp-microvolt` 那行就是双 supply 的关键：基础版（住在 `rk3588-opp.dtsi`）里每个频率档只有一组三元组 `<目标 最低 最高>`，板级覆盖把它翻成两组——第一组是 cpu 轨、第二组是 mem 轨，两组数值一样，因为 Topeet 板上这两条轨接到的是同一颗稳压器。`volt-mem-read-margin` 是电压-读裕量对照表，左列是电压（微伏）、右列是读裕量档位，切到哪个电压就用哪一档的采样窗口。

双 supply 照实说：它其实不是板上真有两颗稳压器。Topeet 板上每个簇的 `cpu-supply` 和 `mem-supply` 指向同一颗稳压器（大簇是 RK8602/RK8603，小簇是 PMIC 的 dcdc-reg2），和原厂的板级设备树核对过。这段引用咱们摘大核小核各一颗来看：

```dts
&cpu_b0 {
	cpu-supply = <&vdd_cpu_big0_s0>;
	mem-supply = <&vdd_cpu_big0_mem_s0>;
};

&cpu_l0 {
	cpu-supply = <&vdd_cpu_lit_s0>;
	mem-supply = <&vdd_cpu_lit_mem_s0>;
};
```

`&cpu_b0` 是第一颗 A76 大核、`&cpu_l0` 是第一颗 A55 小核，这两个代号的本体都定义在 `rk3588-base.dtsi` 的 cpus 段。`cpu_b0` 里的 `vdd_cpu_big0_s0` 和 `vdd_cpu_big0_mem_s0` 是两个标签、落在同一颗 RK8602 上——板级 i2c0 下那个 `regulator@42` 节点挂的就是这双重标签。小簇（cpu_l0 到 cpu_l3）也是同一套写法，两路指到 PMIC 的 dcdc-reg2 小簇轨。cpu-supply 和 mem-supply 写的是两路、指到的是同一颗稳压器，这就是双 supply 不虚构第二颗芯片的根据。保住的是原厂 OPP 事务的接口和顺序，并没有虚构第二颗芯片这样的事。原厂的大框架误读也照实说：PVTM/binning（芯片出厂实测体质分档）这一套**有意不迁**，那套按体质动态扩展超频 OPP 的机制，本次故障缺的不是它，整包移入只会扩大故障面——这个后果笔者掂量过。主线 DTS 的保守固定表够用，这个取舍留到后面封顶的地方再提，它到时候还会回来咬一口的。

### 8 毫秒定生死的探测

事务移植烧进了板子，DVFS 却压根没跑起来——而且不报错。病根藏在注册方式里：驱动用的裸 `module_init`，启动早期就要拿 SCMI 的 CPU 时钟和 I2C 上的 RK860X 调压器，驱动这边读到的行为是谁还没就位就返回 `-EPROBE_DEFER`（-517），而 initcall 没有晚点再试的机制，一次 defer 在这块板上就是永久的放弃。板上日志笔者看了，时机差就清清楚楚了：

```text
[    1.133390] failed to initialize RK3588 CPUFreq cluster for cpu0: -517
[    1.141205] arm-scmi arm-scmi.0.auto: Using scmi_smc_transport
```

驱动死在了 1.133 秒，SCMI 传输层 8 毫秒后的 1.141 秒才出现。这 8ms 的差距看得清楚，CPUFreq 从引入起笔者就一次都没见它运行过。

随后的修复（2026-08-15）把簇初始化从裸 initcall 挪进 platform driver 的探测：initcall 只注册驱动和一个配对的 platform device，它的机制是依赖没到齐就返回 `-EPROBE_DEFER`，驱动核心会自动安排重试、不用你插手，SCMI 时钟和 RK860X 什么时候到齐什么时候继续。`cpufreq-dt` 设备的注册仍然排在所有簇就绪之后，装好 OPP 回调、再起 `cpufreq-dt` 的顺序不破。同一轮里还移植了原厂的 panic notifier：内核恐慌时把每个簇最后的频率和两路电压打出来，下次硬锁（hard lockup）的捕获靠 NMI 回溯加 ramoops，楔死瞬间的 DVFS 状态就能记下来，后面两场戏的主角都是它。

同轮还有一件配套动作笔者记下：ramoops 的持久窗口从原厂位置的 `0x110000` 挪到了 `0x10000000`，因为主线启动链的 TPL/ddrbin（DDR 初始化那一段固件），会清掉低地址的那扇窗。取证装备和被取证的 DVFS 栈在同一轮里各就各位，这个安排后面看是很有远见的——当时只是按原厂语义顺手补的。

### 封顶在 2.208GHz，一个至今留着的诊断

注册修好、DVFS 真正跑起来的第一天，病情反而升级了：以前偶发的随机挂死，变成了**每次启动都在 GNOME/GDM 加载时楔死**。现场你看：CPU 全部静默，IRQ 与 NMI 是均无响应的，最后 DW 看门狗复了位。病情从随机变成了确定，对排查反而是好事。

嫌疑犯很快锁定到了 2.4GHz 那档 OPP。原厂会用 PVTM/binning 把 2.4GHz 档限制在最高体质的芯片上，而事务移植有意没迁那套框架，表把 2.4GHz 无门槛地暴露在 1.0V。随后的诊断改动（2026-08-15 深夜）把它定位成教科书式的一手，做法是把两个大簇封到了 2.208GHz@987.5mV，这个档位是原厂的高温钳位点，板上稳了就证实电源轨/体质理论，还楔你就往下排查（DSU 耦合、I2C 域）。这一手还有一个设备树机制的细节值得学：OPP 阶梯节点住在被 include 的 `rk3588-opp.dtsi` 里，板级改动干的是覆盖属性的活，所以只删板级的 2.4GHz 覆盖没用——底下还有单 supply 的基础版活着，必须用 `/delete-node/` 把引用表里的节点整个删掉。基础版里 2.4GHz 这一档长这样（`rk3588-opp.dtsi` 的 cluster1 表）：

```dts
		opp-2400000000 {
			opp-hz = /bits/ 64 <2400000000>;
			opp-microvolt = <1000000 1000000 1000000>;
			clock-latency-ns = <40000>;
		};
```

板级 `rk3588-topeet.dts` 里，cluster1 和 cluster2 两张表的覆盖块末尾各来一行：

```dts
	/delete-node/ opp-2400000000;
```

`/delete-node/` 是设备树里删子节点的语法，只能整个节点删、不能只删单个属性。`opp-2400000000` 是这张 OPP 表里的一个子节点，板级只覆盖它的属性没用——基础版的频率、时延这些属性都还在，内核照样会把 2.4GHz 当可用档；只有 `/delete-node/` 才能把这一档从最终合成的设备树里整个抹掉。

现状笔者照实写：封顶至今仍在，2.4GHz 的 bin-gating（按体质分档解锁高频档）没有移植。这块板的大簇当前按 2.208GHz 封顶运行，给大簇配正经体质门的活排进了待办清单、这件事还没有闭合。

### DSU/L3 频率耦合，三级时钟域的联动

封顶之后笔者还遇上了一场。2026-08-16 凌晨的捕获记下了完整现场，楔死发生在 boot 后的第 16 秒。i2c 超时、hard LOCKUP、Kernel panic 那几行的原文本章不再重贴，出处归在内核侧的取证装备，本章要贴的是 panic notifier 记下的三个簇临终状态：

```text
[   18.122181] cpu cpu0: cur_freq: 1608000 Hz, volt_vdd: 850000 uV, volt_mem: 850000 uV
[   18.129910] cpu cpu4: cur_freq: 2208000 Hz, volt_vdd: 987500 uV, volt_mem: 987500 uV
[   18.137638] cpu cpu6: cur_freq: 1800000 Hz, volt_vdd: 850000 uV, volt_mem: 850000 uV
```

RK860X 所在的 `fd880000.i2c` 在事务中途超时，簇领队 CPU 接连硬锁了，楔死经 L3 扩散到了全机，这一层在日志里是看得到的。`ipd: 0x1b, state: 2` 这行的可读性顺路注意一下：IPD 是 RK3x I2C 控制器的中断挂起寄存器，主线驱动超时只报一句干巴巴的 timeout，好在笔者往 I2C 驱动里移植过原厂的 IPD/state 日志路径，寄存器的值才能打出来。没这一发的话，卡在哪个状态是无从知道的。

根因是事务移植留下的一条缝：它让每个簇独立切换，可这颗 SoC 的 DSU/L3 缓存是骑在小簇电源轨上的，大簇狂奔时 L3 跟着小簇一起降了频，缓存的供给被掐断，多簇并发的 DVFS 负载一出就出事。boot 期的 udev coldplug 正是同一种负载。随后的修复（2026-08-16）笔者移植了原厂的护栏，护栏的机制列在下面：

- 小簇 policy 创建时，每个大簇往它挂一个 `FREQ_QOS_MIN` 请求
- 大簇每次调频完成，地板更到 `rounddown(freq × 4/5, 100kHz)`
- 大核跑多快，就保证 L3 至少跟着吃到八成、永远不许它塌下去

设备树侧你给小簇的表打上 `rockchip,opp-shared-dsu` 标记。小簇的 `cluster0_opp_table` 在板级设备树里的覆盖块开头是这几行：

```dts
&cluster0_opp_table {
	rockchip,grf = <&litcore_grf>;
	rockchip,dsu-grf = <&dsu_grf>;
	/* DSU/L3 rides the little rail: big clusters floor little at freq*4/5. */
	rockchip,opp-shared-dsu;
	volt-mem-read-margin = <
		855000 1
		765000 2
		675000 3
		495000 4
	>;
	low-volt-mem-read-margin = <4>;
	intermediate-threshold-freq = <1008000>;

	...（后面的频率档是 cluster1 那种双 supply 写法）
};
```

`rockchip,opp-shared-dsu` 这一行就是护栏在设备树侧的那一刀：它声明这张小簇的频率表和 DSU/L3 共享时钟域，驱动读到它，就知道大簇每调一次频，得顺带把小簇的频率地板一起抬住，不让 L3 跟着小簇塌下去。上面那行英文注释 `DSU/L3 rides the little rail` 说的正是 L3 骑在小簇电源轨上这回事。

笔者展开一句 FREQ_QOS（`Frequency QoS`）：指的是频率服务质量约束。把它读作内核里某一方对某个 CPU 频率区间提出约束的通用机制，散热、devfreq 用的也是它，约束会直接进 cpufreq 决策的有效区间。看中它的地方是护栏不经过任何的自定义协议。大簇调频的回调是直接更新挂在小簇 policy 上的约束请求的，小簇的下次决策自然就被托底了。

DVFS 链到这里就算讲齐了，RK3588 的三级时钟域也真正联动了起来。图给你画在下面：

```text
A76 big0（policy4，轨：RK8602）──┐
                                 ├─ FREQ_QOS_MIN 地板（freq × 4/5）─→ A55 小簇（policy0）＋ DSU/L3
A76 big1（policy6，轨：RK8603）──┘                                     ↑ 小簇的轨同时养着 L3
```

A76 的大簇笔者数下来各自一条轨，A55 的小簇是一条轨外加养着 DSU/L3，频率策略上大簇通过 QoS 地板托住小簇。上面的图画的就是异构 SoC 的 DVFS 比单簇多出来的部分。

### 电压链的执行末端：rk860x

把 DVFS 的整条链摆直了看：cpufreq 收到调频请求，OPP 事务按原厂的顺序走，每次改电压最终都落成 `fd880000.i2c` 上对 `RK8602`/`RK8603` 的一笔 I2C 写。**rk860x 调压器就是 DVFS 的执行末端**，8/16 那场 i2c 超时笔者见过，更早的 -110 调压失败也见过，两场都是透过它显形的。

这正是当年那场调压卡死病的回声。主线 fan53555 错误认领了 RK860X，compatible fallback（兜底兼容名）又让 RK8603 伪装成了 RK8602，调频改压时 I2C 事务超时返回的就是 -110。主线的 rk3x-i2c 超时后不做 SLV_HDSCL 检测、也不复位两个 reset domain，SCL 被拉住了，控制器持续地卡死。那一场已经排过：笔者移植了原厂的 rk860x 驱动和 I2C 恢复路径，fan53555 关掉了，DVFS 能开工的前置条件就此备齐。本章讲的是同一颗芯片在频率策略里的角色：它不只是被正确驱动，总线时序质量直接决定多簇并发调压的生死，上耦合护栏图的就是减少多簇同时压一条 I2C 总线的场景烈度。

### 验收：DVFS 活着的证据长什么样

验收的清单笔者抓出来是三条：

- 启动参数里没有 `initcall_blacklist`
- 三组 policy 全部出现：policy0 管 A55 小簇、policy4 和 policy6 各管一个 A76 大簇
- 连续冷热启动和 GNOME 登录后，不再出现 `fd880000.i2c` 超时、调压失败和硬锁

第一遍体检咱们跑这个命令块：

```sh
cat /proc/cmdline
dmesg | grep -iE 'Rockchip RK3588 CPUFreq|cpufreq|rk3x-i2c|rk860|timeout|voltage|Hard LOCKUP'
find /sys/devices/system/cpu/cpufreq -maxdepth 1 -name 'policy*' -print
```

板子上你想看 DVFS 活着没有，最直观的是 `stats/time_in_state`——每个频率档累计停留的毫秒数。8 月 15 日晚的会话里，登录后 policy0（小簇）和 policy4（大簇之一）的记录是这样的：

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

小簇五档、大簇六档全走过了。2.4GHz 那档已经删掉了，表顶收在 2208000 了。policy6 的记录同构（同一次会话翻到 policy6 的 `2208000 398` 一行），光 2208 档就停了 398ms。调度器是真的在八个核上按负载搬频率。同一次会话里笔者还跑了一个 DVFS hammer 压测脚本：8 核满载，每条 policy 一个 slammer 循环扫全档、随机跳档（顺带验了 governor 在 userspace、powersave、performance 之间来回切），dmesg 实时过滤的是 I2C、调压、lockup 关键字。hammer 的终局是一次 RCU stall panic。诊断翻开看过了，8 核满载把 RCU 宽限期线程饿了七千多 jiffy，这个代价算在压测姿势的头上，但 panic 路径恰好让 panic notifier 上了班：

```text
[  321.351523] cpu cpu0: cur_freq: 1008000 Hz, volt_vdd: 675000 uV, volt_mem: 675000 uV
[  321.359251] cpu cpu4: cur_freq: 2208000 Hz, volt_vdd: 987500 uV, volt_mem: 987500 uV
[  321.366987] cpu cpu6: cur_freq: 2016000 Hz, volt_vdd: 925000 uV, volt_mem: 925000 uV
```

楔死瞬间每个簇的频率和两路电压一行不落地全拿到了。取证装备就在它该在的位置上等着，取证方法论最直接的回报，笔者在这看到了。

最终态的收据笔者贴的是 v7.1 线 eMMC 收官轮的日志（首行核过是 `Linux version 7.1.0-00024`，根文件系统走的是 eMMC 的 `root=/dev/mmcblk0p3`）：

```text
[    0.283506] rockchip-rk3588-cpufreq rockchip-rk3588-cpufreq: failed to initialize RK3588 CPUFreq cluster for cpu0: -517
[    0.406284] cpufreq: cpufreq_policy_online: CPU0: Running at unlisted initial frequency: 816000 kHz, changing to: 1008000 kHz
[    0.415826] cpufreq: cpufreq_policy_online: CPU4: Running at unlisted initial frequency: 816000 kHz, changing to: 1200000 kHz
[    0.425903] cpufreq: cpufreq_policy_online: CPU6: Running at unlisted initial frequency: 816000 kHz, changing to: 1200000 kHz
[    0.426954] rockchip-rk3588-cpufreq rockchip-rk3588-cpufreq: Rockchip RK3588 CPUFreq transition helper initialized
```

第一行的 -517 其实是那次探测修复设计好的剧情，时序给你分开看：

- 依赖没到齐，defer
- 143 毫秒后重试成功，三组 policy 上线
- 起机进 login

这些收据收到这里了。同一天深夜笔者还跑了 v7.3.1 补丁重放的板验，走的是 TFTP+NFS 免烧录，DVFS 的四处改动零修改落在 v7.3.1 上。内核换成新的一代，tftp 货架上换一份新的 Image 加 dtb，免烧录就直接复验 DVFS 这类内核侧的行为，而烧写一次都不用。

诚实的边界笔者照例交代：2.208GHz 的封顶还在，2.4GHz 的体质门没做，口径以当时的板验记录为准而不外推。

## 阶段收官：一块主线化的 RK3588 长什么样

到本章为止的板上线走完了，成果单给你摊开，每条都在板上验过了：

- **平台与启动链**：认清这块板在主线生态里的位置——RK3588 是 Collabora 的旗舰，驱动齐全，真正的仗在板级设备树和原厂语义的接缝上。
- **引导**：主线 SPL + BL31 v1.54 + 主线 U-Boot 的链立起来，bootloop 的 blob 版本配对问题解开，rockusb LOADER 模式点亮，烧写不再进 MaskROM。
- **内核**：原厂板级 dts 译成主线的 `rk3588-topeet`，fan53555 误领 rk860x 的 I2C 卡死病治好，硬锁取证装备（ramoops、看门狗、buddy detector）就位，收官完成 v7.3.1 补丁重放。
- **显示**：TC358775 桥的 init 序列这程走通，GT911 触摸出坐标，1024×600 出图进桌面。
- **GPU**：Panthor 加内建固件，renderD128 出现，GNOME 真渲染。
- **根文件系统**：ubuntu-base 长成 Ubuntu 26.04 GNOME，属主与缓存两条纪律立起来，3GiB 镜像打进 eMMC。
- **网络**：GMAC0 通，tftp+nfs 免烧录引擎把烧写从迭代环里拿掉。
- **外设**：WiFi 烧完上电即连，DVFS 三簇联动按需调频调压。

合起来数一遍这块板的家底。板子用的是迅为 iTOP-RK3588，链路从 BootROM 走到 GNOME 桌面：引导用主线的 U-Boot，内核用的是主线 v7.3.1。原厂语义的补丁只留薄薄一层，每一发都写得出它的出处，用户态交给发行版原生的 Ubuntu。补丁栈也过了一遍筛选：v7.3.1 补丁重放之后停在了 20 发，上游已经收走的那五发清了仓，数下来一半是原厂语义的移植（FIQ、rk860x、DVFS 那批），另一半是主线确实还没有的板级适配（面板、GT911、GMAC），每一发的来历和去留理由都有注释记着。闭源残留笔者数过，都集中在链条最前端的 DDR init 和 BL31。公开生态的边界就停在这里，本卷也越不过去。

还没做的活，笔者盘点如下：

- 蓝牙：配置固件已齐，板验待做
- NPU：主线 Rocket 驱动在，CONFIG 未开
- VPU/MPP：Hantro/rkvdec2 在，DT 未接
- RGA：主线无驱动，上游缺
- 摄像头：rkisp1 在，pipeline 未做
- PCIe/NVMe、USB3/Type-C、SD 卡、gmac1、RTC、音频

规律读出来是：剩下的多半是把设备树接上、把用户态配齐的活。这个深度走到了，铺路的活干起来就越来越顺了。真正的例外只数出 RGA 这类上游确实没有的。RGA 其实要的是另一场上游化的仗，那套做法本卷已经示范过很多遍了。笔者补一句后见：清单里记的是本章当时的口径，后面两章的进展不少，NPU 与多媒体核的实况下一章就有，RGA 的驱动在 7.3.1 匹配表里其实找得到，当初的判断过期了。

写到这一章笔者回头看，最值得带走的是反复出现的那套方法论：主线都有驱动的时候换问法，不问有没有、而问接口和时机对不对。rk860x 按这个思路理顺过了，VOP2 时钟交接走的也是同一条路，DVFS 更是把这套问答跑了一遍，连 WiFi 的 menuconfig 门和 .zst 固件也没跳出这个问法。原厂 BSP 在这场移植里的角色也重新看一眼：它是手里唯一完整的语义说明书，四个章节的解法干下来是同一件事——说明书里对的那部分逐章翻译成了主线的语言，说明书里错的部分（比如 fan53555 的误领）指出来扔掉。RK3588 的主线化还在路上，板上的主线走到这里告一段落，NPU 的事就留给下一章收进来。
