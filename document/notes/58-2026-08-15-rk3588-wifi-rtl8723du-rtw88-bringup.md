# 58 — RK3588 WiFi：RTL8723DU → rtw88 主线移植全记录（2026-08-15）

> 一天之内从「板载 WiFi 是什么芯片都记错了」走到「真机关联 + DHCP 拿到地址」。
> 全程暴露并修掉了构建系统三个真 bug。update.img MD5 演进：`fa140cc5` → `93e3f7c8`
> → `8114f638`（终版，板验通过）。

## 0. 结论

| 项 | 结果 |
|---|---|
| 模组 | 板载 RTL8723DU WiFi/BT combo，**共用一组 USB2.0**（onboard Terminus hub 后） |
| 主线驱动 | `CONFIG_RTW88_8723DU`（6.2 进主线），非 rtl8xxxu |
| 固件 | `rtw88/rtw8723d_fw.bin.zst`（WiFi）+ `rtl_bt/rtl8723d_{fw,config}.bin.zst`（BT），linux-firmware 自带 |
| 板验 | ✅ **E2E 收官（2026-08-15，MD5 `0f3ce286`）**：烧录 → 上电 → 全程不碰串口 →
主机 `ssh root@192.168.1.8` 免密直进（改名/关联/DHCP/公钥全自动）；单接口
`State: routable`、DHCP `192.168.1.8/24`、`iw scan` 正常 |
| 遗留 | BT 半边未板验；nmcli/network-manager 与开发公钥待下次 rootfs 重建 |

## 1. 模组身份：四条证据闭环

起点是发现 `board.yaml`/`kernel.config`/`packages.list` 三处把 WiFi 记成
**AP6xxx/brcmfmac**——纯属想当然。真证据链：

```text
vendor kernel .config   RK_WIFIBT_CHIP="RTL8723DU"、CONFIG_RTL8723DU=m
迅为手册                「板载 RTL8723，WiFi/蓝牙共用一组 USB2.0」
vendor DT               sdmmc/sdhci 全部 no-sdio、无 WiFi 节点（旁证：没走 SDIO）
vendor 驱动 usb_intf.c  {USB_DEVICE_AND_INTERFACE_INFO(0x0bda, 0xD723, 0xff,0xff,0xff)}
                        = RTL8723D 1*1（U = USB 接口版；DS 才是 SDIO）
真机 lsusb              0bda:d723（Bus 4，经 1a40:0101 Terminus hub）
```

注意 2026-01 的厂商固件注记提到「适配 aic8800 模组」——批次差异存在，但本机
`lsusb` 已裁决为 RTL8723DU。若真遇 AIC8800：主线无驱动，走 aes/rk3568 式 OOT
（`board.yaml` 的 `wifi_driver` 字段就是干这个的）。

## 2. 主线驱动选型：rtl8xxxu 是错的，rtw88 才是归宿

第一次配置开了 `RTL8XXXU(+UNTESTED)`——惯性联想（8723BU 归 rtl8xxxu）。证伪证据
就在板上：`/lib/firmware/rtlwifi/` 里 8723 家族 AU/BE/BS/BU/DE 的 blob 全齐，
**唯独没有任何 `du` 的 WiFi 固件**——因为 8723DU 的主线归宿是 rtw88 家族，固件
在 `rtw88/rtw8723d_fw.bin`（与 SDIO 版 8723DS 共用）。

`CONFIG_RTW88_8723DU` 由 Sascha Hauer 系列于 6.2 进主线（本板 v7.1 在列），
Kconfig `select RTW88_CORE/RTW88_USB/RTW88_8723D`。最终配置块
（`boards/rk3588-topeet/kernel.config`）：

```text
CONFIG_WLAN_VENDOR_REALTEK=y
CONFIG_RTW88=y                           # ← menu 门,见 §3
CONFIG_RTW88_CORE=y
CONFIG_RTW88_USB=y
CONFIG_RTW88_8723D=y
CONFIG_RTW88_8723DU=y
```

## 3. 两个内核配置坑（各吃了一烧）

**坑一：menuconfig 门。** rtw88 的 Kconfig 是 `menuconfig RTW88` 包着
`if RTW88 … config RTW88_8723DU …`。只写四个子项 `=y` 不写门 `CONFIG_RTW88=y`，
olddefconfig 会把子项**整个静默丢弃**（不可见符号连 `# not set` 行都没有）。
`select` 只向下拉依赖、不会向上开门。症状：`.config` 里 `# CONFIG_RTW88 is not set`
而子项无影无踪。

**坑二：固件加载器不认 .zst。** Ubuntu 26.04 的 linux-firmware 全部 `.zst` 压缩，
arm64 defconfig 不开 `FW_LOADER_COMPRESS` → `request_firmware("rtw88/rtw8723d_fw.bin")`
只找裸名、看不见 `.zst`。真机症状：

```text
rtw88_8723du 4-1.1:1.2: Direct firmware load for rtw88/rtw8723d_fw.bin failed with error -2
... probe with driver rtw88_8723du failed with error -22
```

补 `CONFIG_FW_LOADER_COMPRESS=y` + `CONFIG_FW_LOADER_COMPRESS_ZSTD=y`（顺带救了
后面 BT 要用的 `rtl_bt/*.zst`；对已有裸文件查找零影响）。

**固化纪律：改完 kernel.config、烧板之前，`grep -E "^CONFIG_XXX" .config` 预检
期望行数**——两次坑都是这一条抓的，一次烧录都没多花。

## 4. 构建系统三修（第一次全程非 sudo 跑全链路时暴露）

WiFi 移植顺带把 `forge all`（ubuntu profile）在普通用户下的三个真 bug 修掉了：

1. **`os.execvpe` 截断编排**（`src/forge/stage.py` / `src/forge/pack/emmc.py`）：
   fakeroot 重入用 exec 把 forge 进程整个换掉，`all` 在 stage-rootfs / pack-emmc
   之后静默结束（exit 0、无报错），assemble 永远不跑、阶段指纹永远记不上——
   `forge status` 里 stage-rootfs 常年 "not run yet" 就是它。改 `subprocess.run`
   fork+wait 后链路真正一键到底。
2. **Proc 环境白名单缺 `FAKEROOTKEY`**（`src/forge/core/proc.py`）：白名单里有
   `LD_PRELOAD` 没有 `FAKEROOTKEY` → fakeroot 子进程里 spawn 的 mke2fs 带着
   libfakeroot 却连不上 faked，`llistxattr` 返回垃圾 errno——**253/255 逐次浮动**
   是破案关键（真内核 errno 不会变）。补 `FAKEROOTKEY`/`FAKEROOTDONTTRYCHOWN`。
3. **nobody-old 残留软链**：`out/rk3588-topeet/rootfs.ext4` 是指向
   `.nobody-old-20260812/`（root 属主目录）的软链，mke2fs 顺链写入直接 EACCES。
   删链重建即好。

另：8/12 那次构建是 sudo 跑的，把两棵源码树污染成 root 属主（uboot 3594 + linux
5010 个文件），`sudo chown -R charliechen:charliechen third_party/src/rk3588-topeet`
修复。**纪律：forge 全程不 sudo**——fakeroot 的权限模拟构建内部自理，外层 sudo
只会把工作树污染成下次必炸的状态。

## 5. 板上连接五坑（一个 no-carrier 藏了四个，外加一个 DNS）

驱动侧通了之后，连接侧依次踩掉：

1. **接口名不是 wlan0**：systemd 可预测命名给无插槽信息的 USB WiFi 起
   `wlx<mac>`（本机 `wlx145d346ca1f5`）。netplan 配置写 `wlan0` → 无人接管。
2. **netplan(networkd renderer) 只生成 `.network`、不落 wpa conf**：
   `wpa_supplicant@<iface>` 因 `Failed to read or parse configuration` 退出 255。
   解法：`wpa_passphrase "SSID" "密码" > /etc/wpa_supplicant/wpa_supplicant-<iface>.conf`
   + `systemctl enable --now wpa_supplicant@<iface>`。
3. **`/run/wpa_supplicant/` 目录不存在**（包没建）：服务能跑，但 wpa_cli 连不上
   ctrl 接口。`mkdir -p /run/wpa_supplicant`。
4. **RTL8723DU 是 2.4G 单频芯片**：目标 SSID 叫 `Chenchen-5G`——5GHz 专属 SSID
   物理够不着，`no-carrier` 的真凶就藏在名字里。换 2.4G SSID 后立刻 routable。
5. **DNS 全挂**（`Temporary failure in name resolution`，裸 IP ping 正常）：
   本 rootfs **连 `systemd-resolved.service` 都不存在**（`Unit does not exist`），
   `/etc/resolv.conf` 是 chroot 构建期残留。兜底一行永久管用：
   `echo "nameserver 223.5.5.5" > /etc/resolv.conf`（阿里 DNS；家路由
   192.168.1.1 也行）。板验：`ping baidu.com` 54ms。
6. **netplan `match.name` 只收标量**（烤入版首烧翻车点）：生成
   `name: ["wlx*", "wlan*"]`（列表）→ boot 时 netplan generator `expected
   scalar` exit 1 → `/run/systemd/network/` 全没生成 → 没人改名没人配网，
   `wpa_supplicant@wlan0` 报 `No such device`（真名还是 wlx）。修法：标量
   `name: "wlan*"`——它 match 的是 udev 改名前的**内核名**（rtw88 注册即
   wlan0），且 netplan 的 .link 优先级压过 99-default.link 的 MAC 策略，
   连 wlx 改名一起拦掉。活板补修 = sed 改 yaml + `ip link set ... name
   wlan0` + `netplan apply`，无需重烧。教训：**配置类烤入的静态检查只能验
   「文件对不对」，「目标工具认不认」必须一次真机验收**。
   （坑六续，终局）标量过了又撞 `wifis: No access points defined`——此
   netplan 连凭据都想管(而它又不在 boot 时写 wpa conf,坑二)。**终版方案
   = 对 WiFi 整个弃用 netplan**，纯 systemd 三件套：`/etc/systemd/network/
   10-forge-wifi.link`（OriginalName=wlan* → Name=wlan0，压过 99-default.link
   的 wlx 改名）+ `20-forge-wifi.network`（Name=wlan0，DHCP=yes）+ wpa conf/
   enable 链/tmpfiles。**注意：netplan 的 generator 原本顺手拉起 networkd，
   弃用后必须自己 `enable systemd-networkd`**——否则没人跑 DHCP（IPv6 SLAAC
   能通、IPv4 没有，就是这个形态）。

终态：

```text
wlx145d346ca1f5: <BROADCAST,MULTICAST,UP,LOWER_UP> state UP
    inet 192.168.1.8/24 ... dynamic
State: routable (configured)
```

## 6. ssh 免密公式（DBG-11 现场版）

背景：root 账户无密码 → sshd 默认 `PermitEmptyPasswords no` +
`PermitRootLogin prohibit-password`，密码认证必拒（串口能进是因为 console 不走
sshd）。标准解法是公钥三步：

```bash
# ① 主机：拿公钥（没有就一路回车生成）
[ -f ~/.ssh/id_ed25519.pub ] || ssh-keygen -t ed25519 -N ""
cat ~/.ssh/id_ed25519.pub                # 复制整行

# ② 板（串口）：贴进 authorized_keys
mkdir -p /root/.ssh && chmod 700 /root/.ssh
echo "粘贴公钥行" >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys

# ③ 主机：免密落地（prohibit-password 允许 root 用钥匙，sshd 零改动）
ssh root@192.168.1.8
```

Plan B：rootfs 里已烤好的桌面账户密码登录（见
[note 56](56-2026-08-02-rk3588-ubuntu-user-rootfs-ownership)）；或板上
`passwd root` + `PermitRootLogin yes` + `systemctl restart ssh`（开发板不推荐）。

## 7. 遗留与教学回填

- **BT 板验**：`BT/BT_HCIBTUSB_RTL/BT_RTL` 配置全在、`rtl_bt/rtl8723d_*.zst`
  固件已核，大概率 `btusb` 自动绑定的事，待验。
- **下次 rootfs 重建**（`packages.list` 已改待生效）：`network-manager`（nmcli +
  GNOME WiFi 托盘，8/12 的 ubuntu-desktop 没拉全）；把开发公钥预烤进
  `/root/.ssh/authorized_keys`、`/etc/resolv.conf` 直接烤成
  `nameserver 223.5.5.5`（本 rootfs 无 systemd-resolved，见 §5 坑五）、给
  `wlx145d346ca1f5` 配路由器静态租约。
- **开机自动连 WiFi（已实现，`src/forge/stage.py` `_provision_runtime_config`）**：
  stage-rootfs 解包后直接把五件套写进 staged 树——netplan（`wlx*`/`wlan*` 通配
  match + `set-name: wlan0`，换模组不失效）、wpa conf（PSK 按 WPA 规范 pbkdf2
  现算，凭据不进 git/不进缓存 tar）、`systemctl enable` 等价软链、tmpfiles 目录、
  `resolv.conf`（`network.yaml` 的 dns，缺省 223.5.5.5）。凭据走 **`user/`
  drop-in 目录**（gitignored，仅 `*.example` 模板进 git；`forge.yaml` 保持提交态
  通用默认）：复制 `wifi.yaml.example → wifi.yaml` 填值即可；`FORGE_WIFI_SSID/
  PASS/DNS` 环境变量保留为最高优先级覆盖。`ssh.yaml` 把开发公钥烤进
  `/root/.ssh/authorized_keys`，`account.yaml` 可覆盖 `ubuntu.account`（触发 chroot
  全量重建）。——**烧完板上电即 WiFi 自动关联 + ssh 免密可达**。选 stage 注入而
  非 chroot 重建：免 sudo、改密码秒级重跑（指纹随 stage.py 自动失效）。
- **教学回填**：common-debug-infra 的 DBG-09（仅无线场景）现场版 + 新增 KP
  「单频 WiFi 模块连不上 XX-5G」；DBG-11 密钥登录；common-peripherals PERI-28~32
  （WiFi 子系统）以本板立真板证据。
- update.img MD5 `8114f638`（boot.img `13993dd1`），`forge all` 已可普通用户一键到底。
