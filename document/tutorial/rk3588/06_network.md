# 网络启动与免烧录迭代：TFTP+NFS 引擎，和一场显示杀死网卡的冤案

> [rootfs 章](05_rootfs.md) 结尾咱们数过一轮迭代的代价：改一行配置也要重走构建岛、重打 3GiB 的 ext4、Loader 模式重烧 eMMC，几十分钟就这么进去了。这一章咱们把内核和根文件系统一起搬上网络：TFTP 负责拉内核，根文件系统的挂载交给 NFS，改完源码咱们构建一把，板上重启一次拿到的就是新版，烧写从此退出了迭代环。不过这套引擎在咱们手上得过两关。头一关的事，咱们要把 RK3588 的 GMAC 网卡在主线内核里接起来。第二关说出来没人信：偏偏网卡会以一种最离奇的方式死掉——显示子系统一改频，网卡的 AXI 读就永不返回，整块 SoC 的总线访问跟着挨饿。这桩跨子系统的冤案是本卷继 LCD 章之后的第二场硬仗，你看，它的破案全程就靠本章要搭的免烧录引擎。

版本口径咱们沿用 [内核章](02_kernel.md) 的。引擎的搭建和 GMAC 战役都在 v7.1 栈上进行（log 里的版本串从 `-00021` 一路打到 `-00027`），v7.3.1 rebase 的板验倒是直接用同一套引擎一轮完成，收益咱们留在收官一节单独统计。

## 为什么网络是迭代引擎

咱们得交代两个术语。TFTP（Trivial File Transfer Protocol）是一个极简的 UDP 文件传输协议，它简单到 U-Boot 的 BOOTP/TFTP 实现，塞进了 bootloader 都毫无压力，所以咱们放心拿它当“内核配送员”。网卡通了，咱们用 U-Boot 就能把文件拉下来。NFS root 指的是内核挂根文件系统时不走 eMMC，开机咱们让 NFS（Network File System，网络文件系统）直接把 PC 上的一棵目录树挂成 `/`。你看，板上跑的每一个文件，本体都住在咱们 PC 的硬盘里。

咱们把两个术语合起来看，迭代的形状就从“重打镜像、烧写、上电”变成了这样：

| 改动 | eMMC 烧录轮（rootfs 章的姿势） | TFTP+NFS 轮（本章的姿势） |
|---|---|---|
| 内核 | 重编、重打 FIT、Loader 烧 boot 分区 | 重编，产物进 `tftpboot/`，板上重启 |
| rootfs | 重打 ext4（3GiB）、整分区烧写 | 直接改 PC 上的导出树，`sync` 即生效 |
| 一轮成本 | 几十分钟 | 一刻钟量级 |

rootfs 侧的收益最狠：板上正在运行的系统，它的 `/etc` 就是 PC 上那棵树里的 `/etc`，咱们在 PC 这边改完存盘，板上下次读文件拿到的就是新版，你看，连重启这一步都省了。内核侧的收益要等到本章后半场才真正兑现：GMAC 那场战役打了三十来轮，咱们每轮都是改内核、重编、tftp 拉起、看死法，一轮的耗时约一刻钟。这个频率要是放在烧 eMMC 的流程里，战役的物理时间表会直接翻几倍，很多原本还想再多试一轮的排查就不会发生。这套引擎带给咱们的不只是省时间，它改变的是咱们排查的胆量。

这套基建还有一个特点：咱们搭一次，往后处处复用（[notes/117](../../notes/117-2026-10-31-rk3588-nfs-root-direct-link-bringup.md) 里留下的清单）：

| 组件 | 落点 | 用途 |
|---|---|---|
| nfsd | 导出 `out/rk3588-topeet/rootfs` | NFS root 本体 |
| tftpd-hpa | 服务 `out/rk3588-topeet/tftpboot` | 内核配送 + 链路探针 |
| 直连静态段 | 板 .99 直连 PC .5 | 不依赖烧录通道的调试链路 |
| ICMP 防火墙规则 | 限 192.168.50.0/24 入站 | ping 探针放行 |

往后内核章的 v7.3.1 rebase 板验、本章的 GMAC 战役、以及以后任何“改内核就为看一行日志”的日子，咱们用的都是这一套。

## 让网卡站起来：GMAC、RGMII 和 RTL8211F

### 硬件与驱动族

RK3588 里管以太网的是两个 GMAC（Gigabit Media Access Controller、千兆 MAC 控制器）IP，底层都是 Synopsys 的 DWMAC。主线给这套 IP 配了一组驱动，咱们逐个看：`stmmac` 是核心，管的是 DMA、描述符、MDIO 总线这些 IP 公共部分。`dwmac-rk` 是 Rockchip 的胶水层，管的是时钟、GRF 寄存器、电源域这些板级差异。配置上咱们把 `CONFIG_STMMAC_ETH`、`CONFIG_STMMAC_PLATFORM`、`CONFIG_DWMAC_ROCKCHIP` 这几项打开。本板只布了 gmac0 一个网口，接的是 Realtek RTL8211F 千兆 PHY。

这里咱们补记一处记忆雷。RK3588 两个 GMAC 的基地址是 `gmac0=fe1b0000`、`gmac1=fe1c0000`，跟 RK3568 的直觉排序不一样，笔者当时按 RK3568 的记忆认定 fe1b0000 是 GMAC1，看日志起的是 gmac0 还怀疑 DT 写错了。咱们去查树内 `rk3588-extra.dtsi` 才把事实定下来：日志和 DT 完全一致，是记忆错了。你看，SoC 级的事实只认在树 dtsi，不认咱们脑子里的记忆。

### DT 侧要补什么

MAC 和 PHY 之间的连线方式叫 RGMII，它的全称是 `Reduced Gigabit Media Independent Interface`。千兆下数据和时钟走的都是双边沿，走线的长度差一点采样就会错位，所以两侧各留了一条可调的延迟线（delay line）来补偿。咱们看这块板的 DT 写法（[0002](../../../boards/rk3588-topeet/patches/linux/0002-arm64-dts-rk3588-topeet-panel.patch) 板级 dts 的以太段），有三个关键点是咱们要圈出来的：

```dts
&gmac0 {
	clock_in_out = "output";
	phy-handle = <&rgmii_phy0>;
	phy-mode = "rgmii-rxid";
	tx_delay = <0x44>;
	rx_delay = <0x00>;
	...
};

&mdio0 {
	rgmii_phy0: ethernet-phy@1 {
		compatible = "ethernet-phy-id001c.c916";
		reg = <0x1>;
	};
};
```

咱们逐行拆。`clock_in_out = "output"`：RGMII 是需要一颗参考时钟的，这块板的拓扑是 SoC 把 50MHz 参考钟供给 PHY，而不是 PHY 供 SoC。这个方向决定了一件事：SoC 侧要是把 GMAC 的 50M 时钟门控掉，PHY 的参考钟跟着就没，PHY 就聋了，你看，这个细节在后面的战役里会反复出场。`phy-mode = "rgmii-rxid"`：RX 方向的延迟由 PHY 自己加（rxid = RX internal delay），SoC 侧的 `rx_delay` 就该是 0，TX 方向倒是需要 SoC 延迟线来补 `0x44`。PHY 节点那边的写法，是 `ethernet-phy-id001c.c916` 直接写死 RTL8211F 的 PHY ID，挂在 `mdio0` 总线的地址 1 上。MDIO 是一对线的小总线（Management Data Input/Output），MAC 通过它读写 PHY 的寄存器（自协商状态、链路速率、分页配置）。战役的案发现场，就在这个总线的访问函数里。

咱们注意 PHY 节点没有 reset GPIO，这是 [0025](../../../boards/rk3588-topeet/patches/linux/0025-arm64-dts-rk3588-topeet-drop-invented-PHY-reset-GPIO.patch)（摘掉发明出来的 PHY reset）那发补丁的成果，也是战役里咱们交过学费的一笔，战役一节咱们再细说。

### 为什么网卡和 PHY 驱动必须 =y

NFS root 有个鸡生蛋、蛋生鸡式的循环依赖：根文件系统在网络另一头，而 `modprobe` 是用户态程序，偏偏就住在根文件系统里。内核起来的时候还没有任何用户态，网卡驱动和 PHY 驱动要是编成模块的话，结果就是永远没人加载。所以咱们把这两项一项不含糊地全写成内置（`=y`）。`kernel.config` 的 NFS 段（[kernel.config](../../../boards/rk3588-topeet/kernel.config) 尾部）把这串全链写成了显式声明：

```text
CONFIG_NFS_FS=y
CONFIG_NFS_V3=y
CONFIG_NFS_V4=y
CONFIG_ROOT_NFS=y
CONFIG_IP_PNP=y
CONFIG_IP_PNP_DHCP=y
CONFIG_STMMAC_ETH=y
CONFIG_STMMAC_PLATFORM=y
CONFIG_DWMAC_ROCKCHIP=y
CONFIG_REALTEK_PHY=y
```

这一串里咱们要认的头一个是总开关 `ROOT_NFS`，管的是内核把 NFS 当根挂这件事，`IP_PNP` 是内核自己配 IP 的机制（bootargs 的 `ip=` 参数靠它生效，不走用户态的 ip 命令）。全卷的“零模块纪律”，咱们在这套配置里又落了一面：咱们让 kernel.config 全 `=y`，rootfs 树内的 `/lib/modules` 是可以整个不要的，TFTP 拉什么内核板上就跑什么内核。你看，内核章的 v7.3.1 rebase 板验能免配对直接过，红利就是这里发的。

网卡驱动在板上站起来的样子，咱们从 R31 那轮 log（[vop/2.txt](../../logs/rk3588/vop/2.txt)，R31 是咱们打完修复仗之后验证的那一轮，三轮怎么划分的，咱们看本章后面的轮次表）里截两行来作收据：

```text
[    1.805731] rk_gmac-dwmac fe1b0000.ethernet eth0: registered PTP clock
[    1.805742] rk_gmac-dwmac fe1b0000.ethernet eth0: configuring for phy/rgmii-rxid link mode
```

`rk_gmac-dwmac` 是 dwmac-rk 胶水层注册的平台驱动，`fe1b0000.ethernet` 就是 gmac0 的基地址加设备名，`rgmii-rxid` 说明 DT 里的 phy-mode 传到了驱动。probe 走到了这一步，MAC 侧的活就干完了。能不能活到 `ip link up` 倒是另一回事，咱们接着往下看。

### bringup（板子点亮初调）路上赚到的四发正式补丁

咱们回头看，网卡能通到每轮都通的路，中间隔了一整场战役。战役期间留下了四发正式补丁（[0024](../../../boards/rk3588-topeet/patches/linux/0024-pmdomain-rockchip-keep-RK3588-PD_GMAC-always-on.patch)、[0025](../../../boards/rk3588-topeet/patches/linux/0025-arm64-dts-rk3588-topeet-drop-invented-PHY-reset-GPIO.patch)、[0027](../../../boards/rk3588-topeet/patches/linux/0027-clk-rockchip-rk3588-keep-GMAC-clocks-always-on.patch)、[0028](../../../boards/rk3588-topeet/patches/linux/0028-net-stmmac-dwmac-rk-wire-clks_config-and-conditional-RK3588-delay-lines.patch)），各自管各自的病：

- **0024**：`PD_GMAC` 电源域加 `GENPD_FLAG_ALWAYS_ON`。stmmac probe 完对电源域不持有 runtime-PM 引用，late-init 的 `genpd_power_off_unused()` 就把域关了，而这颗硅上"对断电的 GMAC 做访问"等于直接楔死总线。板上 A/B 实验实证过域断电读必死，这发防御是真实有效的。
- **0025**：删掉 bringup 时发明的 PHY reset GPIO。板上根本没把 RTL8211F 的复位脚布到任何 GPIO（原厂 DT 没有这根线，U-Boot 完全不做复位也自协商成功），发明的 gpio0_B0 复位序列实际是在拉一根用途不明的板级信号，拉下去的瞬间整块 SoC 的总线跟着楔死。这发是"删代码治大病"的典型。
- **0027**：GMAC 三钟（125M 核心、50M 参考、pclk）标 `CLK_IS_CRITICAL` 永不门控。原厂 BSP 的出厂 bootargs 里带着 `clk_gate.always_on=1`（什么都不许关），所以原厂从来不踩门控类的雷，这发是把同样的语义收窄到 GMAC 时钟域。
- **0028**：补上一处真实的主线与原厂 SDK 的差异，两件事。主线 dwmac-rk 的 bulk 时钟只在 probe 时开一次，runtime PM 的恢复路径没接线（`plat->clks_config` 是 NULL），把它接到 gmac_clk_enable() 上。同时把 RK3588 延迟线改成原厂同款的条件使能（delay 值非 0 才开该线），本板 rx_delay=0 就不该开 RX 延迟线。

咱们要诚实交代：这四发各自治好了各自的病，但主病（下一节的那桩冤案）它们谁也没治好。战役结案后的复核把它们重新定性，咱们把 0025 和 0028 定成真修复，0024 和 0027 在根因修掉之后其实属于“多余但无害的防御层”，咱们让它们留在 series 里暂不退役。

## 直连静态段：一根网线的 192.168.50.0/24

### 拓扑与地址规划

迭代引擎的网络不走家里路由器，而是 PC 的有线网口直连板子 eth0。咱们用的是一根网线直连，中间没有交换机这样的设备，也没有 DHCP 服务器这样的角色。地址咱们手动规划在 192.168.50.0/24 这段：

| 端 | 地址 | 配置方式 |
|---|---|---|
| PC（Windows 有线口） | 192.168.50.5 | Windows 网卡静态 IP |
| PC（WSL 侧） | 同 192.168.50.5 | mirrored 模式自动镜像进 WSL |
| 板 eth0 | 192.168.50.99 | bootargs `ip=` 静态指定 |

为什么直连而不走路由器，咱们把理由摆开：

- 路由器意味着 DHCP，也就意味着多一个不可控变量。排查链路问题时，你想让地址是恒定的、让二层只有两个端点。
- TFTP 和 NFS 的服务都在 PC 的 WSL 里，板子只要够得着 PC 就行，你看，根本不需要出这根线。
- 网线和烧录通道（USB 的 rockusb）物理上完全独立：烧录那边随便折腾，链路这边倒是一直在线，板子起不来的时候 U-Boot 的 tftp 还是活的，这就是一条烧板都不用停的调试通道。

咱们还要诚实记录一条边界：经路由器的 `ip=dhcp` 路径没在这块板上复验过，bootargs 的注释里留了两种形态，本章全部按直连的静态段写。

### WSL mirrored 模式的两条地方法则

宿主侧咱们在 WSL 里干活，网络跑的是 mirrored 模式，Windows 网卡的 IP 直接出现在 WSL 里。这个模式有两条实测出来的地方法则，咱们写下来省得读者再交学费。

**WSL 里的 `ip neigh` 不可信，Windows 侧的 `arp -a` 才是权威邻居表。**咱们要查板子的 MAC 有没有进 PC 的 ARP 表，就得用 Windows 里的 `arp -a`，笔者的实践里板子的动态条目（`66:50:1b:af:7e:d2`）就是在 Windows ARP 表里看到的，WSL 侧的邻居表在这个模式下对不上。

**Windows 防火墙把未识别的网络按“公用配置文件”的路子处理，默认拦掉入站的 ICMP，这是它的策略行为，跟咱们要查的故障无关。**咱们这里直连段没有 DHCP，Windows 有线口一度拿到 169.254.x.x 的 APIPA 自配地址（APIPA：链路本地自动地址，“找不到 DHCP 服务器”时自己给自己发的地址），就被 Windows 归为公用网络了。咱们放行探针用的 netsh 规则只对 50 段开门：

```text
netsh advfirewall firewall add rule name="ICMP-in-50" protocol=icmpv4:8,any dir=in action=allow remoteip=192.168.50.0/24
```

咱们注意它拦的只是 ICMP（ping 探针），实测不拦 TFTP 和 NFS 的业务端口。所以后面 NFS 起来之前，链路其实一直是通的，只是 ping 的探测包进不来，这个认知差很容易把咱们带偏。

## TFTP 侧：tftpd-hpa 和 tftpboot 货架

PC 侧的文件服务咱们用 tftpd-hpa，服务目录就是构建产物树里的 `out/rk3588-topeet/tftpboot/`。起服务时咱们带上 `--secure --verbose` 两个参数：secure 把服务锁在目录里，verbose 让每笔传输的记录都落进日志，排查的时候它们就是咱们的眼睛。

货架上的三件套咱们用 [notes/122](../../notes/122-2026-11-01-rk3588-kernel-v7.3.1-rebase.md) 定型的版本，全在 `out/rk3588-topeet/tftpboot/` 里：`Image` 是 `forge build linux` 出的裸内核镜像，`rk3588-topeet.dtb` 是板子的设备树，`boot-tftp.scr` 是 U-Boot 的引导脚本。

这里有个咱们刻意做的设计选择：TFTP 路线走**裸 Image + dtb + `booti`**，不做 FIT 的重打包。eMMC 那侧（内核章）的内核装在 FIT 里，咱们每次迭代都要 `mkimage` 一遍。TFTP 这边的 Image 就是编译器的直接产物，构建完咱们拷进货架就能用，迭代环里的“打包”这一步也就省了。引导逻辑是固化在 scr 里的，它的源文件是 [boot-tftp.cmd](../../../boards/rk3588-topeet/fit/boot-tftp.cmd)，咱们看它的本体就四行：

```text
setenv bootargs console=ttyFIQ0 root=/dev/nfs nfsroot=192.168.50.5:/home/charliechen/rk-forge/out/rk3588-topeet/rootfs,vers=3,tcp ip=192.168.50.99:192.168.50.5::255.255.255.0::eth0:off rw
tftpboot ${kernel_addr_r} Image
tftpboot ${fdt_addr_r} rk3588-topeet.dtb
booti ${kernel_addr_r} - ${fdt_addr_r}
```

加载地址咱们沿用 `rk3588_common.h` 的约定：`kernel_addr_r=0x02000000`、`fdt_addr_r=0x12000000`。货架上的 Image 和 dtb 咱们不需要手动维护，构建流程会把 `forge build linux` 的最新产物放进 tftpboot，货架上永远躺着最近一次成功构建的内核。你看，这本身就是一种防呆：忘了构建，拉下来的就是上一版，版本串会替咱们招供。改了 cmd 之后，咱们用 `mkimage -A arm64 -O linux -T script -C none -d boot-tftp.cmd .../tftpboot/boot-tftp.scr` 重生成 scr。

板侧的用法是咱们在串口打断 autoboot 之后敲四条命令（这块板的 U-Boot 没有 saveenv，`ipaddr`/`serverip` 每次都要咱们现场设）：

```text
setenv ipaddr 192.168.50.99
setenv serverip 192.168.50.5
tftp ${scriptaddr} boot-tftp.scr
source ${scriptaddr}
```

往后的每一轮内核迭代，咱们在板上重复的就只有这四行。

## NFS root：导出同一棵树（主戏一）

### 架构决策：单源导出 out 树

搭 NFS 导出的时候，教科书式的做法是建一个 `/srv/nfs/rk3588-scratch` 目录再往里拷文件，咱们的第一版方案就是这么写的，后来被咱们自己推翻了。咱们的理由是**双宿主**。NFS 导出的目录和 forge 打包 rootfs.ext4 的源树成了两棵树，今天看着是一致的，下周就不一定了。板上 NFS 跑的内容和烧进 eMMC 的内容迟早漂移，而且漂移是静默的，咱们不会收到任何报错。

咱们定的正解是直接导出打包源树本体（[notes/117](../../notes/117-2026-10-31-rk3588-nfs-root-direct-link-bringup.md) 的架构决策）。咱们就守着同一棵源树：一条路用 mke2fs 打成 rootfs.ext4，再打包成 update.img 烧进板上的 eMMC，成为板上的 `/`。另一条路是咱们用 nfsd 把这棵树直接导出给板上当 NFS root。

咱们开发时改树、`forge pack` 出镜像、NFS 板上跑的，永远是咱们手里的同一份内容，这就是咱们要的单源、零漂移。这个合并校验咱们当场实证过一次：源树里的 busybox 算 md5，再从打包出的 rootfs.ext4 里把同一路径抠出来算 md5，两侧算出来的都是 `f8bf5254`。你看，板上跑的和将来烧的，连字节级都是一致的。

导出的配置落在 `/etc/exports`，咱们用一行把源树交给网段里的板子：

```text
/home/charliechen/rk-forge/out/rk3588-topeet/rootfs *(rw,sync,no_root_squash,insecure)
```

选项里有两个关键项是咱们要分开看的：`no_root_squash`（板上 root 写文件不被降权成匿名用户，否则 rootfs 里的所有权全乱，rootfs 章那棵 Ubuntu 树的用户/组所有权就是经不起咱们折腾的）、`insecure`（允许客户端从非特权端口挂载，内核的 NFS 客户端不保证走 2049 以下端口）。两项都是 bring-up 记录里明确写下的，`rw` 和 `sync` 是配它们的常规写法。改完咱们用 `exportfs -ra` 重读一遍。

### PC 侧的三处修复

NFS 的挂载真正跑通之前，咱们在 PC 侧还有三处雷要排，收尾记录见 [notes/119](../../notes/119-2026-11-01-gmac-wedge-open-rearm-counterattack.md) 的 §5h。

**mountd 的端口固定在 20048。**NFS 的挂载得问 rpcbind/mountd，mountd 默认用的是随机端口，Windows 防火墙拦下来就是莫名的挂载超时，所以咱们把端口固定下来，落点放在了 `/etc/nfs.conf.d/mountd-port.conf`。咱们提醒一句：想当然去 `/etc/default/nfs-kernel-server` 里改 `RPCMOUNTDOPTS` 会空转，咱们要找的那行配置在那个文件里根本不存在。

**Windows 防火墙给 NFS 加了两条入站规则**（TCP 和 UDP 各一，放行的端口是 111、20048、2049 三个，只限 192.168.50.0/24 的网段）。这是当年 ICMP 规则的同款操作，咱们已经懂这个理了：mirrored 模式下入站流量过 Windows 防火墙，每类服务都要咱们单独放行。

**bootargs 的 nfsroot 加 `nolock`。**NFS 的锁管理器（NLM）也是动态端口，咱们跳过它，就少一个被防火墙卡脖子的环节，对单客户端的迭代 rootfs 没有代价。这里咱们把出处交代清楚：这半个参数是咱们收官那轮（R29）现场手敲进 bootargs 的，咱们仓库的 [boot-tftp.cmd](../../../boards/rk3588-topeet/fit/boot-tftp.cmd) 文件里并没有它，当年的记录咱们留在 [notes/119](../../notes/119-2026-11-01-gmac-wedge-open-rearm-counterattack.md) 的 §5h。这个参数咱们不替仓库补，补不补是作者拍板的，教程的引文是照仓库文件原文写的。

咱们再补一条判定经验：Windows 上用 `Test-NetConnection` 测本机 NFS 端口，在 mirrored 模式下这个 hairpin 测试是不可靠的。显示 False 并不代表外部的链路不通，板子那边的实测才是真裁判。

### 构建侧排掉的两颗雷

搭 NFS 镜像那天咱们还排掉两颗雷，都值得咱们记。第一颗在补丁序列里：series 尾部的 0023（sim 线的 virtio 遗产）是个裸 diff，缺 format-patch 的邮件头。`git apply --check` 倒是不挑头、能过，`git am` 结果直接报 “Patch format detection failed”，21 发全回滚了。更阴的是 `forge all` 的退出码仍然是 0，内核是根本没编的，out 里的 boot.img 还是旧的。要是咱们没发现，下一轮烧到板上的就是旧内核挂新名，排查直接建立在假地基上。拦住它的是全链静态自检：合并 .config、检查 ext4 里的 boot.scr、核对产物时间戳，“拿旧内核当新的烧”这类事故进不了板。修法本身很简单（补上和邻居一致的 `From/Date/Subject` 头），教训倒是通用的：**构建系统退出码为 0，只说明它跑完了，不说明它干了咱们要的事**。

第二颗是咱们交过手的记忆雷（gmac0/gmac1 地址记反虚惊一场，咱们前面 GMAC 一节讲过），这里只补一句它的通用形态：bringup 期咱们看的日志多了，脑子里会堆起各种各样的“应该如此”，而 SoC 级的事实每隔几颗芯片就翻新一次。所以每个带着记忆下的判断，咱们都值得去在树 dtsi 里核一遍再信。

### bootargs 逐字段拆解

`ip=` 的静态语法是七个冒号分隔的字段，咱们在直连段里每个字段都有讲究：

```text
ip=192.168.50.99:192.168.50.5::255.255.255.0::eth0:off
   └─ client-ip   └─ server-ip └gw└─ netmask   └host└dev └autoconf
```

- `client-ip` 192.168.50.99：板子自己。
- `server-ip` 192.168.50.5：TFTP 和 NFS 都在它身上。
- 第三字段 gateway 留空：直连段没有网关，出这根线的流量本来就不存在。
- `netmask` 255.255.255.0。
- 第五字段 host 留空（用不上主机名）。
- `eth0`：设备名，IP-Config 就配它。
- `off`：autoconf 关——这条链上没有 DHCP，别浪费等待。

nfsroot 那半边的写法：`nfsroot=192.168.50.5:<out树路径>,vers=3,tcp`，也就是服务器地址加导出路径。`vers=3` 锁 NFS 协议版本（内核 NFS root 对 v3 的路径最熟）。`tcp` 咱们选 TCP 传输，UDP 在直连上千兆是没问题的，但 TCP 的重传语义让大数据量传输不用咱们自己操心丢包。`nolock` 是上面 PC 侧第三处修复的配套，收官那轮是咱们手敲进 bootargs 的，仓库的 cmd 文件里是没有这个参数的（出处见前文 PC 侧修复一节）。最后咱们挂个 `rw`，迭代引擎要是只读就没意义了，板上改文件、咱们在 PC 上直接能看到。

### 链路分层验证法

内核侧的 NFS root 还没起来之前，咱们在 U-Boot 层就把物理链路一层层剥开验证。这套方法是 [notes/117](../../notes/117-2026-10-31-rk3588-nfs-root-direct-link-bringup.md) 里最有复用价值的一段，五层各用各的命令取证：

```text
U-Boot dhcp    → PHY 自协商 done、BOOTP 七连无应答  → 物理层通，DHCP 服务器不存在
Windows ipconfig → 有线口 169.254.95.17 (APIPA)      → 直连段在线，但无 DHCP 分配
静态 50 段     → ping 192.168.50.5 失败、无 ARP retry → ARP 已通，ICMP 被防火墙拦
Windows arp -a → 板 MAC 66:50:1b:af:7e:d2 动态条目   → 二层双向，铁的证据
tftpd + tftp   → 8 字节 "TFTP-OK" 文件落内存         → UDP 数据面全通
```

这套剥法的精髓在**每层只证明自己那层**：`dhcp` 能走到 BOOTP 超时，说明 U-Boot 的 MAC 驱动、PHY 自协商都过了，它连发出去了七次请求。ARP 表有板子的 MAC，说明线是通的、板子在应答，ping 不通在咱们这里就只能归到策略问题上。tftp 探针是画龙点睛的一笔：往货架里放一个 8 字节的 `TFTP-OK` 文本文件，咱们用 U-Boot `tftp` 拉进内存、`md.b` 看一眼，UDP 数据面通了，NFS 的把握就有九成九。咱们分层走到顶，每一层的判定都有独立证据，就不用赌了。

### 然后卡住了

咱们基建全通、镜像在手，结果真板第一轮 NFS 起机就死在 1.79 秒，串口最后一行打了一半就没了下文（全程取证：[nfs/1.txt](../../logs/rk3588/nfs/1.txt)）。三个证据（NMI 处理器安装失败的报错、更早的乱码行、死在半行字上）指向一件事：console 自己瞎了，内核倒是未必死。console 瞎了不等于内核死，这个判断咱们在内核章讲过，但这次它彻底瞎了，PHY、链路、DHCP 的日志全落在死区里，咱们只能进入盲飞排查。

盲飞咱们就得换手段。接下来的战役每一轮，都是靠本章已经架好的东西来打的：U-Boot 的 tftp 每轮都在用（它同时是链路健康的活证据），咱们把内核镜像一轮一轮经 tftp 烧到板上，一共打了 29 轮、约 30 个小时。这就是咱们的主戏二。

## GMAC fabric wedge：显示杀死网卡（主戏二）

### 症状与近因链

咱们多轮打点之后，死法被收敛成一条清晰的近因链（[notes/118](../../notes/118-2026-11-01-rk3588-gmac-fabric-wedge-handoff.md)）：

```text
eth0 open → stmmac_open → setup_dma_desc（RxQ 打印）→ pm_runtime_resume（返回 0）
→ stmmac_init_phy → 第一次 MDIO 事务
→ stmmac_mdio_wait() 的第一个 readl(MII_ADDR) → AXI 总线不返回 → 该 CPU hard lock
→ fabric 逐步饿死：vblank 超时、SPI2/RK806 报 -110、其他核陆续死
```

咱们翻译成白话：内核打开网卡，去读 PHY 的寄存器，这个读请求发进 SoC 的 AXI 总线 fabric（片内互联，CPU 访外设都要过它）之后就**永不完成**了。发起读的那个 CPU 死等，紧接着咱们看到整片互联挨饿，显示的 vblank 中断超时、PMIC 的 SPI 传输报 -110、别的核也陆续停摆，最后连 console 都断流了。一病万症：楔死的外显五花八门（vblank、SPI、多核 lockup、串口半行），在咱们看来全是派生症状，追着症状跑是追不完的。

还有一个贯穿全程的“健康对照组”，咱们叫它 U-Boot。战役每一轮都要靠 U-Boot 的 tftp 送内核，用的是同一颗 GMAC、同一个 PHY、同一根网线，U-Boot 其实从来没楔过。U-Boot 的世界是单线程的，没有 runtime PM 的概念，也没有时钟框架的动态调度，更没有别的子系统的并发改频。同一个硬件在两种软件的世界里一活一死，你看，这个对比是咱们手里“病在软件栈”最早的一份侧证，虽然当时咱们还读不出凶手藏在哪个差别里。

最吊诡的证据咱们单说。**probe 阶段跑的同一串 MDIO 事务全过**。dwmac probe 时 realtek 驱动会对 PHY 做一整串的分页配置（reg31 换页、MMD 间接读写），二十多笔事务全部都成功了，然后 `ip link up` 触发了 open，open 里的第一笔读就死。同一个函数咱们跑两次，结果却是第一次全过、第二次必死。

排查中期（notes/118 交接时的状态）的假说记分板咱们照录在这里，咱们给三个方向各挂了一个置信度：

| 假说线 | 内容 | 当时置信度 |
|---|---|---|
| A 线 | GMAC 自己的电源/时钟/恢复窗没保证 | 0.60 |
| B 线 | CPU 或供电轨的共病 | 0.25 |
| C 线 | NoC/QoS、SMMU、DSU 等共享互联 | 0.15 |

把记分板放这里是想说一件诚实的事：**记分板上的三条假说线最后全灭了**，真凶是第四条谁都没押的——显示子系统的时钟改频。排查的过程，就是咱们一边跑判决实验一边把记分板上的线一条条划掉，划到最后剩下的那个（哪怕再不合直觉）才是答案。

### 排除法长征

这场战役的排查史，是咱们一路“自信地提出假说、再用判决实验杀掉它”杀出来的历史。咱们挑改变案情节奏的轮次来讲，完整的实验矩阵在 notes/118 和 notes/119。

**TEMP 探针补丁群是咱们的武器库。** 咱们交代完工具再讲战果。战役期间写了五发 TEMP（临时取证）补丁：[0026](../../../boards/rk3588-topeet/patches/linux/0026-TEMP-stmmac-open-mdio-debug-probes.patch) 在 stmmac_open 和 MDIO 访问路径上撒 netdev_info 打点，把楔点定位到具体的两个调用之间。[0029](../../../boards/rk3588-topeet/patches/linux/0029-TEMP-stmmac-open-entry-rearm-and-state-snapshot.patch) 在 open 的入口放“金丝雀”读（canary read：直接 readl 一下已知会楔的寄存器，活着就证明总线是还没坏的），外加一轮时钟全断电的重整装。[0030](../../../boards/rk3588-topeet/patches/linux/0030-TEMP-poll-php_grf-and-gmac0-csr.patch) 是个每 20ms 轮询 php_grf、PMU 电源域状态和 CRU 时钟寄存器的看门狗 watcher，值一变就给咱们打横幅，它的 v7 版把 GPLL/CPLL/V0PLL/AUPLL 四颗 PLL 的配置寄存器，也都圈进了监视组。[0031](../../../boards/rk3588-topeet/patches/linux/0031-TEMP-headless-disable-display-pipeline.patch) 这一发专门做判别：把显示全家（VOP2、MMU、DSI2、DCPHY、面板）全禁掉了再跑，跑的是 headless（无显示）模式。[0032](../../../boards/rk3588-topeet/patches/linux/0032-TEMP-display-phase-markers.patch) 在显示的上电路径埋相位标记。这五发在咱们手里的定位就是**仪器**，它们的使命是产出判决性数据，结案后咱们让它们全部退役（series 里注释掉、文件留档），绝不让临时打点污染了正式内核。

**死点是会搬家的，而且每笔读像掷硬币。** Round 10 里死点从 open 搬进了 probe 段第 6 笔，咱们由此看到，“probe 和 open 之间状态劣化”这一类的假说全灭，纯 probe 连发的照样死。Round 12 里 cpuidle 深睡假说也被杀掉了，而且咱们拿到了全场最传神的一份证据：open 入口的两笔金丝雀读，咱们量下来的间隔是约 8µs，第一笔成功返回了 `MII_ADDR: val=0x00000104`，第二笔倒是永不返回。同一个从口、相邻的两笔读，结果一活一死，可见是这个从口的 AXI 读在按概率楔，跟哪个寄存器、哪个时钟域是都没关系的。

**分水岭实验：原厂内核当咱们的对照组。** Round 14 咱们把原厂 5.10 内核加原厂 DTB 放上同一块板、同一条 U-Boot/BL31 引导链、同一根网线，而且就是用 tftp 货架送上去的（`tftpboot/{vendor-Image,vendor-topeet.dtb}` 加 booti，引擎自己客串了法医）。判决出来了：原厂内核的 eth0 正常起，`devmem 0xfe1b0000` 读 GMAC 的寄存器不楔，**30 万次裸读 gmac0 都活了下来**。你看，板、硅片、BL31、U-Boot 的嫌疑全部洗清，病是在主线软件栈里的。

**外围假说咱们逐个杀。** 在死点搬家之前的那几轮，咱们还碰上一类围着“内核谁把 GMAC 弄坏了”转的假说，也各安排了一轮判决实验：加 `clk_ignore_unused` 跑 Round 9-a（late-init 时钟清扫无罪，死点倒是不变），65 秒 shell 空转的判别轮（VOP、GPU、cpufreq 全在跑，倒是稳如泰山，idle 是无事的，咱们一敲 `ip link up` 板子即死），`pd_ignore_unused` 的 Round 19（改变了致死面而不是消除它，还带出了 pm-domain sync_state 悬置，牵涉 video-codec 这类无驱动的设备）。这些轮次的价值，咱们数下来是把搜索空间一块块烧掉：到最后，“GMAC 自己的电源、时钟、驱动序列”范围内的候选几乎清零，病被逼到了 GMAC 之外。

**idle 其实也能死，驱动序列论也就出局了。** Round 16 更绝：主线内核起进 eMMC shell 什么都不干，idle 十秒后第一发 `devmem 0xfe1b0000` 就把整块 SoC 打死了。没有任何网卡驱动的活动在场，“open 序列触发”论就此判了死刑，idle 后首读必楔拿到了最直接的证据。同时 Round 17a 拍了两侧 idle 状态的快照做 diff：主线这边 GMAC 时钟 enable 计数全部正常、电源域 on、各项指标看着都没问题，结果照样楔。咱们找到的唯一的系统性差异在 php_grf（PHP：SoC 里挂网卡等外设的那个岛）的 CON0 寄存器上，原厂内核的 CON0 是 RGMII 模式（0x208），主线被清成了 0。R18 试图盲修（把好值直接写了回去），写入的瞬间整块 SoC 就挂死了。坏状态下往这个 GRF 写是自杀式的动作，盲修的路走不通，咱们必须在进入坏状态**之前**拦住它。

**php_grf 的复位像是伴生现象。** 0030 探针的前几版把 php_grf 的 CON0 翻转当头号嫌疑追了很久，R20 还发现 php_grf 在 1.03 到 2.2 秒之间整个寄存器堆被打回了复位默认值，看着就像有人把 php 岛复位了一样。但 R21 的 v2 探针轮给出了反证：那一轮 php_grf 全程稳在 U-Boot 写的良好值，是一次都没翻的，eth0 照样死在了 open。咱们判定：复位是翻车之后的伴生状态，死亡是另有原因的。这轮的反证很贵，它逼着排查放弃了眼看要收网的“抓复位者”的老路线，结果又回到“翻转之前到底发生了什么”的问题上。顺带一个仪器化的教训也记在这里：R20 用的 v1 探针每 100ms 还额外读一次 GMAC 寄存器，这个读本身成了污染变量，探针自己把死亡提前了。**仪器是会扰动被测系统的**，后来 v2 的设计原则就是只读 php_grf 和 PMU、绝不碰 GMAC，让 NFS 轮自己的 open 当致死探针。

**翻转抓到了现行。** 0030 的 v3 探针，20ms 的轮询加横幅，在 Round 22 抓到了案发瞬间：1.2207 秒，php_grf 的 CON0 从 0x8 翻成 0x0、CLK_CON1 从 0x10 翻成 0x18，整块 php_grf 寄存器堆被打回了复位默认值。而 PMU 侧的电源域状态全程没有翻转，说明这背后没有任何可见的电源域动作。咱们看翻转前的案发名单：1.198 cpufreq 首次换频（距翻转约 23ms），1.203-1.207 rockchip-drm 绑定了 VOP 和 DSI，最后 13ms（1.207 到 1.2207）的窗口就落在显示 bind 的尾上，接着翻转就来了，再往后 1.304 USB 新设备上线了。

**headless 的判决。** 咱们顺着名单做 Round 26：0031 把显示全家禁掉再跑。php_grf 翻转横幅消失了，金丝雀一路都是 ok 的，**eth0 open 第一次活着走完了**。凶手就此锁定在显示的上电路径。教学上这里值得咱们停一拍：这个案子从网卡必死走到凶手在显示，中间隔着的是二十几轮实验、五版探针、一次原厂内核对照。跨子系统的 bug 不会在案发现场留下自家名片，得靠判别实验把案发现场一步步挪到真凶的门口。

### 链路首通与 NFS 竣工

显示禁掉了之后，咱们看到网卡的世界立刻豁然开朗。Round 27（eMMC 手动轮）里 `ip link up` 完整走通了，12.5 秒后打出了 `Link is Up - 1Gbps/Full`，咱们 ping PC 五发全中、稳态 0.4ms，主线内核的以太网端到端首次全通。

NFS 的挂载还差一口气：链路训练要约 4 秒（open 之后），而 NFS 轮的 IP-Config 在 1.7 秒就起跑了，等不到链路就放弃了。Round 28/29 咱们让 IP-Config 耐心等，再加上 PC 侧的三处修复（mountd 固定 20048、防火墙放行 NFS 端口、nolock），到 Round 29 全链就竣工了：Link Up、IP-Config Complete、NFS 挂根，用户态全部起来了，login 提示符出来了。notes/117 开头写的那个目标，“改 rootfs 秒级生效、重启即新版”，29 轮之后就兑现了。

### 根因与修复：GPLL 重锁

凶手是圈定到显示家族了，咱们还要二分到具体是谁。答案揭晓时很有喜剧感：**凶手是 LCD 章已经立案的那个时钟问题**，跟显示侧的哪个驱动都没关系。根因的全链在 [notes/120](../../notes/120-2026-11-01-rk3588-vop0pll-fix-closes-gmac-wedge.md)，LCD 章的显示侧判定在这里合龙：

LCD 章的 0009 补丁本想把 `DCLK_VOP2_SRC`（VOP2 的像素时钟源）重父到专用 V0PLL，意图却写在了 `&vp2` 上。port 子节点是算不上设备的，`of_clk_set_defaults` 是永远不会在它身上跑的，重父的动作就从未生效，dtc 偏偏也不报错。于是像素时钟源一直挂在默认的父 GPLL 上。主线 VOP2 驱动 modeset 时调了 `clk_set_rate(vp->dclk, 82MHz)`，82MHz 从 GPLL 是除不尽的，改频请求经 `CLK_SET_RATE_PARENT` 一路传了上去，结果触发了 **GPLL 重锁**。而 GPLL 同时是 `clk_gmac_125m`、`clk_gmac_50m` 和 `aclk_php_root` 的父，显示改一次频的功夫，php 岛的整个时钟世界跟着翻船，GMAC 从口的 AXI 读从此永不返回。你看，php_grf 被打回了复位像，只是翻车的伴生状态（R21 证明翻转不是死亡的必要条件）。原厂 5.10 同板全活也就自洽了，原厂本来就把 dclk 的源配在 V0PLL 上。

修复是 [0033](../../../boards/rk3588-topeet/patches/linux/0033-dts-rk3588-topeet-parent-DCLK_VOP2_SRC-from-V0PLL.patch)：咱们把重父挪到 `&vop` 设备节点上（与 ACLK 750M 合并声明），删掉 port 上的死代码。结案后它已折叠进 0009 的现行形态（series 留有注释），这发独立补丁文件咱们留档作证据。

显示家族内部的二分和修复验证一共三轮，咱们把记录（[notes/120](../../notes/120-2026-11-01-rk3588-vop0pll-fix-closes-gmac-wedge.md)）摆在这里：

| 轮 | 镜像变量 | 判决 |
|---|---|---|
| R30 | 显示全开 + 0030v7 CRU 监视 + 0032v1 标记 | 基线证实 dclk 源=GPLL，死在 modeset 标记之前（对照轮） |
| R31 | **+0033 修复** + 0032v2 死区加密标记 | 全绿：82MHz 精确命中、V0PLL 重锁、GPLL 零横幅、eth/NFS/显示三者并存 |
| R32 | 正式镜像（TEMP 全退役、bootargs 摘拐棍） | 无仪器三绿，正式收工 |

修复轮 R31 的收据是机制级的，咱们从 [vop/2.txt](../../logs/rk3588/vop/2.txt) 截的，一个字都不是咱们合成的：

```text
[    5.937325] IP-Config: Complete:
[    5.937337]      device=eth0, hwaddr=66:50:1b:af:7e:d2, ipaddr=192.168.50.99, mask=255.255.255.0, gw=255.255.255.255
[    5.964233] VFS: Mounted root (nfs filesystem) on device 0:27.
```

时钟侧的三行收据，咱们把引文和逐行判读都放在 LCD 章，这里只报判读结果：dclk 从 12MHz 拉到 82MHz、ret=0 精确命中是咱们看到的，V0PLL 从 0xc6 重锁到 0x148 也是咱们看到的，GPLL/CPLL/AUPLL 是全程零横幅的，两边的口径是一致的，共享 PLL 是真没被碰的。网络侧的收据是 IP-Config 报了 Complete、eth0 拿到对的地址和掩码、NFS 挂根成功，显示、网卡、NFS 是同时在线的。修复的设计预期（“82MHz 落进专用 PLL，共享 PLL 不再被碰”）被咱们逐项观察证实，这是机制级的验证，绝不是碰巧活了一轮，同栈无修复的对照轮 R30 同晚必死。R32 换了正式镜像（探针全退役、bootargs 摘掉辅助拐棍）复验，同样三项全过了，那轮的 log（[vop/3.txt](../../logs/rk3588/vop/3.txt)）里 NFS 挂出来的已经是 Ubuntu rootfs，systemd 起到了 graphical.target。rootfs 章打包的那棵树，现在整棵是住在咱们 PC 里的，板上咱们随取随用。

这场战役的教学价值，咱们单独归纳成三条：

- 跨子系统时钟耦合的 bug 长这样：症状在网卡（AXI 读不返回），凶手在显示（GPLL 重锁），中间隔着一条隐性连线，GPLL 是两边共同的父时钟。案发子系统永远不是问题的发源地。
- 一病万症，咱们别追派生症状，fabric 楔死之后 vblank、SPI、多核 lockup 全是回声。
- 判别实验高于一切：原厂内核对照（R14）、idle 裸读（R16）、headless（R26），每个都一刀切开一类假说。而这些实验每轮都要换内核，没有这台 15 分钟一轮的免烧录引擎，这套做法在物理上就不成立。

## 收官：v7.3.1 一轮过，引擎的回报

引擎搭成之后接的第一单大活，就是内核章收官的 v7.3.1 rebase 板验。咱们做完 20 发补丁重放、构建、关键符号审计之后，板侧用的就是本章那四行 U-Boot 命令，2026 年 11 月 1 日深夜一轮通过：串口打出了 `Linux version 7.3.1-00020-g8a8c79486a31`，`VFS: Mounted root (nfs filesystem)`，shell 里 `uname -r` 对上了，显示管线也回归了，`reboot loader` 进了 rockusb。rebase 的故事在 [内核章](02_kernel.md) 讲过了，这里咱们只统计引擎自己的收益。

引擎的回报咱们从两个方向算。省钱的方向：战役 29 轮加上显示二分 3 轮，每轮的内核都不同，全部走的是 tftp 免烧录。按 rootfs 章结尾数过的代价（一轮 eMMC 迭代几十分钟）粗算，30 多轮省下的烧写时间以十小时计，引擎的建设成本（一个下午的基建）第一周就赚回来了。赚钱的方向更值钱：引擎不只是省了烧写，它还解锁了原本做不了的实验。原厂内核经 tftp 烧到板上当对照组（R14）、TEMP 探针内核每 15 分钟一轮的快速迭代、headless 判别轮（R26），这些轮次要靠烧 eMMC 的话，战役的节奏和深度都会是另一个样子。

最后咱们交一下现状。eMMC 里烧着 v7.3.1 的正式镜像（内核章的 fit 已重包），板上的日常就从 eMMC 起 Ubuntu GNOME，迭代引擎不是每次都要用的。两条引导路径咱们刻意保持着各管各的：eMMC 的 boot.scr（[boot-emmc.cmd](../../../boards/rk3588-topeet/fit/boot-emmc.cmd)）现在揣的是干净的本地 bootargs（战役年代加过的诊断参数全部摘掉，因为病已经修在补丁栈里了），NFS 的迭代则完全走 U-Boot 交互加 boot-tftp.scr，两边倒是互不掺和。引擎本体在 out 树的 tftpboot 货架和 nfsd 导出里待命，要改内核或 rootfs 的日子，咱们 `forge build` 完打断 autoboot 敲四行命令，就回到了免烧录世界。

## 本章资产索引

本章牵扯的补丁，咱们按去留归拢一遍（[series 文件](../../../boards/rk3588-topeet/patches/linux/series)里每发都有决策注释）：

| 补丁 | 内容 | 去留 |
|---|---|---|
| [0002](../../../boards/rk3588-topeet/patches/linux/0002-arm64-dts-rk3588-topeet-panel.patch) 的以太段 | gmac0 RGMII + RTL8211F PHY 描述 | 正式，板级 DT 的一部分 |
| [0024](../../../boards/rk3588-topeet/patches/linux/0024-pmdomain-rockchip-keep-RK3588-PD_GMAC-always-on.patch) | PD_GMAC always-on | 正式，结案后属防御层 |
| [0025](../../../boards/rk3588-topeet/patches/linux/0025-arm64-dts-rk3588-topeet-drop-invented-PHY-reset-GPIO.patch) | 删发明的 PHY reset GPIO | 正式，真修复 |
| [0027](../../../boards/rk3588-topeet/patches/linux/0027-clk-rockchip-rk3588-keep-GMAC-clocks-always-on.patch) | GMAC 三钟 CLK_IS_CRITICAL | 正式，结案后属防御层 |
| [0028](../../../boards/rk3588-topeet/patches/linux/0028-net-stmmac-dwmac-rk-wire-clks_config-and-conditional-RK3588-delay-lines.patch) | clks_config 接线 + 条件延迟线 | 正式，真修复 |
| [0026](../../../boards/rk3588-topeet/patches/linux/0026-TEMP-stmmac-open-mdio-debug-probes.patch) 等 TEMP 五发 | 取证仪器（打点/金丝雀/监视器/headless/标记） | 全部退役，series 注释、文件留档 |
| [0033](../../../boards/rk3588-topeet/patches/linux/0033-dts-rk3588-topeet-parent-DCLK_VOP2_SRC-from-V0PLL.patch) | V0PLL 重父（根因修复） | 结案后折叠进 0009 现行形态 |

板外的资产咱们也归拢一下：直连静态段 192.168.50.0/24（PC .5 / 板 .99）、nfsd 对 out 树的单源导出、tftpd-hpa 货架，外加两条咱们配的防火墙规则（ICMP-in-50 与 NFS 端口）。这些东西是不出现在任何 commit 里的，但它们是这场战役真正的生产资料。换一台 PC 干活的时候，咱们要重新架的就是上面列的全套东西。

下一章咱们要搞 WiFi（rtw88）和 CPU 调频（DVFS）。那里会用到本章一个熟悉的角色。cpufreq 在 GMAC 战役的案发名单上挂过名（1.198 秒首次换频），翻转是 23ms 之后才来的，最后的结果证明它是无辜路人，外设章给它一个正式的交代。咱们外设章见。
