# Ubuntu 根文件系统：从 ubuntu-base 到 GNOME，再打进 eMMC

> 上一章 [GPU 章](04_gpu.md) 咱们收掉了 Panthor 和固件内建，所以内核能给桌面递上 `renderD128`，LCD 出图和触摸坐标咱们也都验过了。但是 GNOME 桌面是另一层的东西，`systemd`、`GDM`、`mesa`、`gnome-shell` 这一大坨用户态全都得住进咱们要造的根文件系统里。这一章咱们就造这块根，咱们拿 Canonical 官方的 ubuntu-base 最小骨架当原料，在 chroot 里咱们把系统喂成 Ubuntu 26.04 GNOME，后面几节咱们再压成 ext4 镜像、打成 update.img 烧进 eMMC。路上咱们碰了两场事故，一场是 GDM 起来了咱们却登录不进去，另一场是咱们烧完才发现整个 rootfs 归了开发机的普通用户。uint32 的体积红线咱们后面细讲，咱们认为事故加红线一起，就是本章最值钱的部分。

## 选型：这块板走 Ubuntu，RK3506B 走 buildroot

rk-forge 里铺了两条根文件系统路线，它们各教各的东西，下面咱们把两边的定位摆清楚。

仓库里另一块 RK3506B 小板走的是 buildroot，用户态拿的就是 busybox，所以教学定位只有一条：把每一字节的决定权都留给自己。根文件系统里有什么、init 怎么起、哪个库在哪个环节被谁链接，这些问题咱们就全部摊开来看。但是代价也摆在那里，每加一个功能咱们都得自己凑物料。

RK3588 这块板瞄准的是 GNOME 桌面加一票主线外设，这个体量再拿 buildroot 手凑就不现实了。GNOME 这一套其实是几百个互相咬合的包，mesa 的用户态、D-Bus、AccountsService、network-manager 这些都得伺候到，任何一个版本的包咬合不上，咱们就得花半天排查。所以改走 Ubuntu 的 apt 生态，这些咬合关系让发行版替咱们维护，咱们的精力可以全花在板级和打包上。两边是分工：buildroot 那边的路线教的是搭根文件系统的骨架，这一章教的是把一块现代发行版的根文件系统造出来，还得把它正确地塞进 Rockchip 的烧写格式。

其实两条路线共用同一套 stage/pack 框架，`src/forge/stage.py` 里开出了 `buildroot`、`openwrt`、`ubuntu` 三个 profile。板级的 `board.yaml` 里还留着一行 `rk3588_topeet_defconfig`，注释说它是留给未来的 buildroot profile，在 `--rootfs=ubuntu` 下是用不到它的。但是门没关死，本章只是不走它而已。咱们收成一张对照表：

| | RK3506B 板：buildroot | 本板：Ubuntu |
|---|---|---|
| 用户态 | busybox，几十个命令 | systemd + GNOME，几百个包 |
| 物料来源 | buildroot 菜单配置，自己挑 | packages.list 列清单，apt 解依赖 |
| 教学点 | rootfs 的骨架怎么搭、init 时序 | 发行版 rootfs 怎么造、属主与打包 |
| 打包出口 | UBI（SPI-NAND） | ext4（eMMC） |

原料层面选的起点是 **ubuntu-base**，它是 Canonical 官方发布的最小根文件系统压缩包 `ubuntu-base-26.04-base-arm64.tar.gz`，从 cdimage.ubuntu.com 下载这个约 30MB 的包。至于它为什么算最小，看内容就知道了，里面只有 dpkg、apt、systemd、glibc 这几样让 apt 自己能跑起来的骨架，其余的全靠后面用 apt 拉。在咱们手里它就是一袋面粉，本章要做的就是把它烤成蛋糕。

选型上还有一处要交代：为什么用 ubuntu-base，debootstrap 放在了一边。后者是 Ubuntu 官方的另一条造根路线，路子是从零 bootstrap 一套能起来的基础系统。但是 debootstrap 没走，因为多轮的 chroot 迭代要跑，仿真环境里那一堆一阶段二阶段的脚本也得跟着跑、它又慢又脆，咱们信不过它。ubuntu-base 其实把能跑 apt 的骨架这一步官方化了，拿到手咱们直接 `apt install`、不确定性就被收窄到 chroot 一层。这个取舍是定下来的：ubuntu-base 加 apt 用，debootstrap 咱们不走。

至于为什么不直接刷官方桌面镜像，咱们也交代一句。官方 arm64 桌面镜像假定的是 UEFI 那套引导流，但是这块板走的是从 BootROM 到 idbloader 的 Rockchip 私有链，板上内核日志里能看到 `efi: UEFI not found` 那行直白的回绝。所以根文件系统自己造、引导自己排，每个环节都握在自己的手里，这正是本仓库的立身之道。

## 构建链总览：四步，一处 sudo

咱们把整条链整体摆出来，随后逐段地拆：

```text
forge build ubuntu-rootfs   # chroot 里 apt 装包 + 配置，产出 ubuntu-rootfs.tar（要 sudo）
forge stage                 # 解包 tar 到 out/rootfs/，注入运行时配置（fakeroot 下）
forge pack emmc             # mke2fs -d 把树压成 rootfs.ext4（fakeroot 下，免 sudo）
forge assemble --variant emmc    # RKAF/RKFW 打包出 update.img（纯 Python，免 sudo）
```

这四步跑完了之后，在 `out/rk3588-topeet/` 的货架上就有这五样东西，后面各节咱们逐个认脸：

```text
ubuntu-rootfs.tar    # build 的产物：整棵 rootfs 的归档（约 2.4GiB 内容）
rootfs/              # stage 铺出的目录树，pack 的输入
.rootfs.fakeroot     # 属主数据库，贯穿 stage 与 pack（下文的主角之一）
rootfs.ext4          # pack 的产物：3GiB 定容 ext4 镜像
update.img           # assemble 的产物：可整包烧写的 RKFW 容器
```

有个设计决定咱们要交代：整条 forge 链全程不用 sudo，唯一的例外其实是第一步的 chroot。dpkg 的安全检查要求它的数据库目录真的归 root 所有，但是把手头的非特权工具数一圈，文件属主真的是 root、有 `/dev`、能跑 arm64 二进制，这三件事是凑不齐的。proot 只能替咱们伪装进程 uid、不改文件属主，所以 dpkg 当场拒绝。unshare 是连 `/dev` 都造不出来的。fakeroot 则是和 qemu 合不来的。所以 chroot 老老实实跑在真 root 下，把它记作全仓库文档化的唯一 sudo 孤岛。tar 做好了之后还有指纹缓存，后面的 stage/pack/assemble 全都不需要特权，咱们跑 `forge all --rootfs=ubuntu` 时只有头一次要 sudo。

装包之外在 chroot 里咱们还有一段 post-config 要跑，板级的身份也要烙进根文件系统。`/etc/fstab` 固定根分区与 `/proc`、`/tmp`、`/var/log` 的挂载，其中 /tmp 和 /var/log 走的是 tmpfs，是为了省 eMMC 写入。`/etc/hostname` 写的是板名 `rk3588-topeet`，板上日志里 systemd 那行 `Hostname set to <rk3588-topeet>` 就是它的回声、首次启动就能对上。root 的密码置空，这是 MVP（最小可用版本）阶段的开发姿势，所以 ssh 密码通道自动拒绝、只剩密钥和串口两条路进来，反而安全些。至于根设备谁说了算，咱们要分清。内核挂根这一步听启动参数里的 `root=/dev/mmcblk0p3`，这个参数是启动脚本 boot.scr 写进去的，跟板上日志里 `VFS: Mounted root (ext4 filesystem) on device 179:3` 的那一行能对上。咱们把 179:3 分成两半看，它其实是 mmc 主设备号 179 加第三分区。fstab 是 systemd 起来之后的第二份记录。这些配置进的是缓存的 tar，所以改它们就要重走 sudo 构建岛，这一点由指纹缓存替咱们强制执行。

背景咱们再说一句。这颗 Ubuntu 根文件系统伺候的不只真板，rk3588-lite 的仿真线也拿它当真根，跑冒烟用的是 QEMU 异构 8 核仿真。同一颗镜像咱们两头吃，板上出问题之前咱们就拿仿真线过一遍，这是仿真线的用法，本章就不展开了。

## 第一段：从 ubuntu-base 到能登录

### chroot 里跑 apt：qemu 慢世界的两个提速

arm64 的根文件系统要在 x86 开发机上装配，靠的是 binfmt_misc 注册的 `qemu-aarch64-static`，这个机制的原理下面就说。binfmt_misc 是内核的一个机制，按文件头魔数给非本机架构的二进制自动选解释器这件事交给它办，这里选的就是 qemu 的静态版。流程咱们摆一下：把 qemu 静态二进制拷进 chroot、再 bind-mount `/proc` `/sys` `/dev`，resolv.conf 咱们也放一份，然后跑下面的命令：

```text
chroot <work> /usr/bin/apt-get update
chroot <work> /usr/bin/apt-get install -y --no-install-recommends <packages.list 里的全部包>
chroot <work> /usr/bin/apt-get clean
```

chroot 里的 arm64 dpkg，就在 qemu 翻译下跑起来了。`--no-install-recommends` 开着也是在省钱、桌面元包的推荐依赖见过，它们动不动就把体积和安装时间吹大了一圈，开发板的根文件系统只装清单里列出的东西。装完咱们记得把 qemu 静态二进制从根文件系统里删掉，它只是给开发机仿真用的，板上真 arm64 是用不着它的。

qemu 的翻译有多慢，装过 ubuntu-desktop 的咱们都知道。这里有两个实测有效的提速，都是拿教训换来的：

- `sources.list` 写 `trusted=yes`。qemu 下 keyboxd（gpg key 守护进程）的 IPC 举止异常，合法密钥也验签失败。构建期的源是清华镜像加 ports.ubuntu.com 兜底，都是可信镜像，构建时跳过 GPG 验签，省掉一类纯属仿真副作用的失败。
- 删掉 `/etc/apt/apt.conf.d/70debconf`（关掉 preconfigure）。qemu 下 apt-extracttemplates 要提前把每个包的 debconf 配置脚本跑一遍，几十分钟的纯开销，而全程 `DEBIAN_FRONTEND=noninteractive`，这些脚本跑了也白跑。删掉之后包在解包阶段直接配置。

apt 源本身配的是清华 tuna 镜像主源、`ports.ubuntu.com` 官方源兜底，两边各配的是 `main/restricted/universe/multiverse` 四个组件和 `-updates/-security` 两个跟进源，咱们把完整的 sources.list 放在构建器 `ubuntu_rootfs.py` 里。

装什么包不在脚本里硬编码，说了算的是板目录下的 `ubuntu/packages.list` 清单。这个文件是块活的教学材料，下面讲 GNOME 的时候咱们还会回来细读。

### 串口 getty：控制台在哪，登录提示符就在哪

咱们要根文件系统能登录，第一件事是让一个 getty 替咱们蹲在串口上。getty 这个名字分开看就是 get tty 的缩写，它干的活就是在终端上打印登录提示符、把会话交给 login。这里有个省心的机制：串口控制台对应的 serial-getty，systemd 会自动侦测内核命令行里 `console=` 的最后一个值、把对应的 serial-getty 拉起来，所以一行配置都不用写。这个机制咱们在 rk3588-lite 的仿真线上验证过，同一颗 Ubuntu 根文件系统在 QEMU 里被 systemd 259 拉到了串口 login，三条断言咱们全核过。但是仿真线在本章只当冒烟预检用、不当证据链主干。其实板上日志里它也如实发生，翻 8 月 1 日的首启日志能看到 `[  OK  ] Started serial-getty@ttyS2.service`，紧接着串口上就能看到 `Ubuntu 26.04 LTS rk3588-topeet ttyS2` 和 `rk3588-topeet login:` 的字样。

但是控制台在那晚搬了家。一场 fan53555 误领 rk860x 引发的 I²C 卡死病，就发生在控制台搬到了 ttyFIQ0 之后。这次搬家切的是原厂式的 ttyFIQ0，背书的是 FIQ 调试器。根文件系统侧的配置要跟上，现在的构建里 rk3588 板的 post-config 写成显式启用 `serial-getty@ttyFIQ0.service`，同时删掉 ttyS2 的 getty。不删是不行的：ttyS2 一旦留下就要和 ttyFIQ0 抢同一个 UART、在 FIQ 调试器背后重新打开串口，所以会制造出一类极难定位的串口怪象。搬家的收据也留了，当晚 21:17 的日志里翻得到，咱们摘一段：

```text
Welcome to Ubuntu 26.04 LTS!
[    2.070627] systemd[1]: systemd 259.5-0ubuntu3 running in system mode (+PAM +AUDIT ...)
[    2.070658] systemd[1]: Detected architecture arm64.
[    2.074707] systemd[1]: Hostname set to <rk3588-topeet>.
[    2.315171] systemd[1]: Queued start job for default target graphical.target.
...
         Expecting device dev-ttyFIQ0.device - /dev/ttyFIQ0...
```

咱们看这段日志，systemd 259 在 ARM64 上以 system mode 起来了，hostname 读到的板名正是烙进根文件系统的那个，graphical.target 进了队列这件事也确认过，getty 已经蹲到 ttyFIQ0 上等设备了。日志截在了启动早期，graphical.target 达成的收据放到后文成功长这样的一节里看。

这块板级配置里还固化了看门狗，systemd 里定了 `RuntimeWatchdogSec=30s`，喂的是板上那颗 DesignWare 看门狗。lockup 诊断 sysctl 也固化了一整套、`panic_on_oops`、`hardlockup_panic` 这些开关，检测到就把内核打进了恐慌停机的状态。道理在内核取证的那一侧，这里咱们只把它们落到根文件系统的文件上、不再重讲。

### 用户与属主：两场事故

到这里能让根文件系统出登录提示符了，但是 GNOME 还起不来。GDM 的全名是 `GNOME Display Manager`，它管的就是图形登录，它面前一个可登录的用户都拿不出来。这是本章的第一场事故，咱们顺着它往下挖，挖出来的是更深的一场。

**症状一：没有可登录的用户。** 当时暂存的根文件系统树（staging 树，解包出来待打包的目录）咱们查下来，`/etc/passwd` 里数得出来的只有 root 和系统用户，UID ≥ 1000 的普通用户一个都数不出来。但是 GDM 默认不提供 root 图形登录，所以 GDM 起来了、greeter（登录欢迎界面）也亮了、就是进不去。解法本身不复杂：构建时在 chroot 里 `useradd` 一个 UID/GID 1000 的普通用户，附加组给它挂的是 `adm sudo audio video render input plugdev netdev` 一共八个（GPU 渲染要进 render 组、桌面音频要进 audio 组，这些组关系后面咱们全用得上）。点亮初调时期这个用户定的是 `charliechen`，密码是明文公开的，GDM 给它配了自动登录，属于开发阶段的点亮初调凭据。后来这坨东西制度化：用户默认值收敛成通用的 `rk-forge/rk-forge`，个人的身份走 `user/account.yaml` 覆盖，密码在开发机上用 `openssl passwd -6` 哈希了、再经 `chpasswd -e` 注入进去，明文只让它活在开发机的 YAML 里，镜像里其实只有哈希。凭据是不放进镜像的，这一课是从点亮初调走向可发布时必须补的。

自动登录其实是两份文件配合的结果，`/etc/gdm3/custom.conf` 写的是 `AutomaticLoginEnable = true` 加 `AutomaticLogin = <user>`，`/var/lib/AccountsService/users/<user>` 写的是 `SystemAccount=false`，所以 AccountsService 认它是真人用户，greeter 才把它列出来给咱们看。shadow 的 `SHA-512` 哈希对过与预期密码匹配，八附加组数了齐全，custom.conf 的自动登录目标核下来正确。开发阶段自动登录用着是很方便的，产品化之前咱们必须关掉它并换密码，这道边界是明写着的。

**症状二：整个根文件系统都归了开发机的普通用户。** 在新增用户之前咱们检查了一下此前的成品 `rootfs.ext4`，结果比没有用户严重得多：

```text
/etc/passwd  uid=1000 gid=1000
/bin/bash    uid=1000 gid=1000
/home        uid=1000 gid=1000
```

passwd、bash、整个 /home 咱们查下来，看到的全是 uid 1000。一个 UID 1000 的新用户会把 passwd 和 bash 在内的一大票系统文件据为己有，这镜像就不能用了。

根因定位在了咱们解包的那一环。`ubuntu-rootfs.tar` 验过本身是对的，tar 里存着的是数字属主 root:0。但是当时的 stage 脚本由普通用户执行，tar 解包时 chown 不到 root、磁盘上的 staging 树全部落成了开发机用户的 UID/GID 1000，随后 `mke2fs -d` 忠实地把错误属主写进了 ext4。所以这是权限问题：全链路设计的目标本来是不用 sudo，写属主的权力却给不出来。

**解法：咱们用 fakeroot 数据库把属主信息背着走。** fakeroot 的原理是在进程外面拦一层，chown 调用它替咱们记进一个属主数据库，文件在磁盘上看到的还是普通属主，但是在 fakeroot 会话的视图里它已经是 root。关键动作是把数据库持久化：stage 阶段咱们用 `tar --numeric-owner --same-owner` 解包，整个 stage 是跑在 `fakeroot -s` 下的，把属主状态存进了 `out/.rootfs.fakeroot`。pack 阶段咱们用 `fakeroot -i` 加载同一份数据库再跑 `mke2fs -d`，属主原样进了 ext4，咱们全程仍然不需要 sudo、mount 或 loop 设备。两个工程细节咱们记一下。一是 WSL2 下咱们要设 `FAKEROOTDONTTRYCHOWN=1`，漏设的话 tar 的 chown 返回 EINVAL，构建当场就炸了。二是 fakeroot 的重入选了 fork+wait 而不是 exec，早期版本用 exec 真的会把整个 forge 进程替换掉，`forge all` 就在 pack 之后悄无声息地断掉，而 assemble 永远轮不到跑。

修完咱们用只读 `debugfs` 直接查成品镜像的 inode，不看 staging 树自欺欺人的那一套：

```text
/etc/passwd                                  0:0 mode 0644
/bin/bash                                    0:0 mode 0755
/usr/lib                                     0:0 mode 0755
/home/charliechen                         1000:1000 mode 0750
/var/lib/AccountsService/users/charliechen   0:0 mode 0600
```

验收的属主标准是系统文件归 root、家目录归用户、AccountsService 里的用户描述归 root，咱们认下这些才是一块能见人的根文件系统。

**回归：家目录属主上又翻了一次车。** 属主链修好了之后，2026 年 8 月 15 日咱们又在板上翻了一次同族的车。根文件系统的 tar 查出来是 `--owner=0 --group=0` 平铺打出来的，登录用户的家目录进了镜像就成了 root 属主，板上 gnome-shell、gvfs、dconf 成片地失败，localsearch 的崩溃循环也抓到了。修法进了 `stage.py`：stage 那边让它在 fakeroot 会话里对 `/home/<user>` 补一次 `chown 1000:1000`，属主落进了保存的数据库、最终也进了 rootfs.ext4。同一次 stage 还注入了几样开发板刚需：

- sudoers.d 里的 `NOPASSWD`。用户在 sudo 组但仍要密码，root 又没密码可回退，串口上的无人值守流程就会卡死在密码提示上。
- 一份能用的 resolv.conf（chroot 时代的那份解析不了任何域名）
- 开发者的 ssh 公钥进 `/root/.ssh/authorized_keys`（重烧镜像后 ssh 免配置）

教训浓缩成一句：属主问题咱们碰过就不止一次，往后它还会回来找咱们，root 属主的树配上无特权工具链，这对矛盾会一直在咱们眼前，每个新环节进场咱们都要重新核对一遍属主。

这里咱们能看清 stage 与 build 的分工。build 拥有全部的根文件系统定制，用户、getty、看门狗都烙进了 tar，sysctl 也在 chroot 里定了。stage 只做物化的工作，把 tar 铺成目录树这件事是交给它的，外加少量必须避开缓存和 git 的运行时注入，凭据、DNS、属主修复都算进了这一类。定制的源头只有一份，build 与 stage 就不会各说各话、这是这套框架最省心的地方。

## 第二段：从能登录到 GNOME

### 包清单怎么读

`packages.list` 按用途分了段，咱们读它就像读一份作战序列：

- init 与基础（systemd、dbus、udev、kmod）：ubuntu-base 已有 systemd，这段是显式确认。
- 网络（netplan.io、iproute2、openssh、wpasupplicant、network-manager）。
- 固件（linux-firmware）：WiFi/BT 固件全从这里来。
- GPU 用户态（mesa-utils、libgl1-mesa-dri）。
- 桌面本体（ubuntu-desktop）。
- 开发工具（vim-tiny、curl、htop、i2c-tools 这些）加诊断武器（strace、binutils、gdb、xz-utils）。

其中两个条目咱们要多说两句。`ubuntu-desktop` 其实是元包（meta package，自己不含文件、只靠依赖关系把一整套软件拉进来的空壳包），它拖进来的就是 gdm3、gnome-shell、mutter、wayland、xorg 加整个桌面栈，所以 GNOME 能一条清单就装齐，功劳记在依赖关系这个大管家的头上。诊断武器那四件（strace、binutils、gdb、xz-utils）是另一场战役的遗产：最小系统里缺过它们，攻坚期咱们只能靠内核 printk 打点加手写工具绕行，所以清单注释给它们记了时间税太高的判词。板上崩 mesa 时咱们拿 gdb 直接在板上看反汇编，断点、变量、调用栈咱们当场就能看。隔着串口猜就只剩内核 printk 的回声，一条一条地等。

但是清单不是一次写好的。注释里留了一条板验记录：翻 8 月 12 日的记录，那颗根文件系统里缺了 network-manager，所以板上 `nmcli` 报 command not found，当时的网络靠 netplan 加 wpa_supplicant 手撑，network-manager 是后来才补进清单的。所以 packages.list 也进了指纹，咱们改它一次，结果缓存的根文件系统 tar 就判过期、sudo 构建岛就得重走。这道纪律本身是 2026-08-15 那次事故换来的：当时 sysctl 改了三天、镜像是旧的，缓存守卫就是那次教训立起来的。

机制上咱们再看一眼，`.ubuntu-rootfs-built` 这个标记文件里存的其实是一份内容摘要，对 packages.list 和构建器的源码本身做哈希，结果就落成了这个标记文件。缓存命中时咱们要比对摘要，摘要对不上咱们就重建，除此之外就不留第三条路了。

### mesa 用户态：内核侧的另一半

咱们把桌面落到 GPU 上，两侧是要同时到位的。内核侧交的是 Panthor 驱动加内建的 `mali_csffw.bin` 固件，所以 `renderD128` 出现了。根文件系统这一侧给的是 mesa 用户态（mesa 24.x 起自带 Panthor 的 Gallium 驱动），`libgl1-mesa-dri` 把整个 GL/DRI 栈都拉了进来。两侧是在 `/dev/dri/renderD128` 这个设备节点上碰头的，mutter（GNOME 的窗口管理器兼显示服务器）通过 GBM 拿 GPU 的 buffer，渲染节点要是缺了，结果就是桌面黑屏、`gbm_surface_lock_front_buffer failed` 反复刷的那场病。内核的 DRM 驱动和用户态的 mesa 之间，是一整套共享的接口约定，哪一侧的实现对不上，看到的都是黑屏。两侧咱们分开讲，验收是合一的。

### graphical.target 链与体积红线

包装齐了之后咱们再看开机链，它是 systemd 的标准上坡。graphical.target 是这块板的默认目标，板上日志的那行 `Queued start job for default target graphical.target` 可以当证据，它比 multi-user.target（getty、网络）多拉了一票图形服务，gdm.service 咱们数下来是其中之一。GDM 起来后要跟它打交道的有两件事：图形会话的立起归它，自动登录或者弹 greeter 怎么选，听的是 AccountsService 的配置。最终咱们看到 gnome-shell 作为用户会话跑起来，mutter 在里面是兼任显示服务器的，把窗口合成到那块 1024×600 的屏上。板上实测的收据放在下一节成功长这样里看。

体积咱们也要算一遍。GNOME 桌面加 mesa 加 linux-firmware 咱们装下来，根文件系统的体积量下来约 2.4GiB。ext4 镜像定的是 3072MiB，装下 2.4GiB 是还有余量的。最终成品咱们量过一轮：`update.img` 共 3290329674 字节（约 3.06GiB）。这 3GiB 不是随手拍的，下一节讲它头上的红线。

## 打进 eMMC：ext4、parameter、RKAF

根文件系统在货架上还只是 `rootfs.ext4` 一个文件而已。最后一步咱们把它和 uboot、boot 一起装进容器，而且装的还得是 Rockchip 烧写工具生态认的格式。这一章从里到外过一遍：ext4 怎么打，体积为什么定 3GiB，分区表怎么读，容器怎么拼，最后怎么烧。

### mke2fs -d：不 mount 不 loop 的 ext4

咱们要把一棵目录树变成 ext4 镜像，常规的路子是 dd 一个空文件、losetup、mkfs、mount、拷树、umount，而且每一步都要 root。forge 走的是另一条路：拿 `mke2fs -d`（`pack/emmc.py`）让 mke2fs 直接从目录树填充文件系统，所以全程无特权、无 loop 设备。

```text
mke2fs -q -F -t ext4 -b 4096 -L rootfs
       -U 11111111-2222-3333-4444-555555555555
       -E hash_seed=66666666-7777-8888-9999-aaaaaaaaaaaa
       -d out/rootfs out/rootfs.ext4 3072M
```

两个写死的值有讲究：UUID 和 hash_seed 写死了，镜像的结构就能复现（superblock 写入时间仍会变，所以不是逐字节金标，但是结构稳定）。这个 UUID 不是写着玩的，板上日志里咱们翻到内核亲口报的那行 `EXT4-fs (mmcblk0p3): mounted filesystem 11111111-2222-3333-4444-555555555555 r/w`，看到这串数字就知道挂上的正是 forge 打的这块镜像。

咱们让 pack 把 boot.scr 烙进镜像：拿 mkimage 把 `boot-emmc.cmd` 裹成 U-Boot 的 script 格式，在 `/boot/boot.scr` 和分区根的 `/boot.scr` 各放一份。为什么是 rootfs 分区来扛引导脚本？因为 boot 分区是裸 FIT、没有文件系统，bootflow（U-Boot 的启动流程框架）里读脚本的 SCRIPT bootmeth 只能在 ext4 的根文件系统分区上找到它，找到了再由它裸读 boot 分区、bootm 交内核。引导入口是住在根文件系统里的，这是本板布局的一个容易想拧的点。

Ubuntu 的属主要求在这里兑现：pack 发现货架上躺着 `.rootfs.fakeroot`、就 fork 一个加载了属主数据库的 fakeroot 子进程把整个 pack 重跑一遍，`mke2fs -d` 拿到的就是 root 属主的系统文件，上一节那套机制到这里就走完了。pack 开工前咱们还有一道防御：把整棵 staging 树扫一遍，任何读不了的条目看着就拒打（典型来源是 NFS 时代留在树里的污染），免得打出一块带黑洞目录的镜像到板上才炸。

### 为什么镜像只有 3GiB：一条 uint32 的红线

板级 `board.yaml` 的 `rootfs_mib: 3072` 挂了一句注释，咱们把注释写成 `ext4 镜像大小，必须小于 4GiB，因为 RKAF 条目的 size 字段是 uint32`。

咱们展开说。update.img 的正文是一个 RKAF 容器（下一小节拆它），容器里的每个分区条目是 112 字节，尾部的五个字段数出来是 `nand_size、pos、nand_addr、padded、size`，写入全部走的是 `struct.pack('<IIIII', ...)`，所以每个都是无符号 32 位整数（uint32、最大到 4294967295），4GiB 的镜像一放就直接溢出。所以塞进 update.img 的 rootfs.ext4 必须守住 4GiB 的红线，取 3GiB 是给约 2.4GiB 的 GNOME 根文件系统留的增长空间。

有个数字对比帮着把三层约束分开记：这块板的 eMMC 是 116GiB（板上日志 `mmcblk0: mmc0:0001 METORA 116 GiB`），所以物理空间完全不缺。GPT 里 rootfs 分区切了 8GiB，这个规划是仓库自己定的。镜像定的是 3GiB，结果才是 RKAF 格式逼出来的硬上限。116GiB、8GiB、3GiB 咱们摆在一起看，它们分属的层级一层层数得清、别把它们混成一个问题。

那 GPT 分区表里的 rootfs 分区为什么敢写 8GiB？因为那是切在 eMMC 上、不走 RKAF 条目的分区，uint32 是管不着它的。两道天花板是两码事：分区 8GiB 是给根文件系统长大留的地，镜像 3GiB 是烧写格式给的框。assemble 时咱们还有第三道检查（`_check_rootfs_fits`）：镜像体积不得超过分区体积，超了直接报错拒打，报错里会提示要么缩 `--rootfs-mib` 要么改 parameter 扩分区。

### parameter-emmc-topeet.txt 逐行读

`parameter-emmc-topeet.txt` 是烧写工具读的分区表。头部是元数据的一段，字段数出来的是 `FIRMWARE_VER`、`MACHINE_MODEL: RK3588`、`MACHINE_ID: 007` 这几样。咱们单独看 `MAGIC: 0x5041524B`，四个字节正是 `PARK` 的 ASCII，这是 Rockchip 的小幽默。真正要读的是 CMDLINE 那行：

```text
CMDLINE:mtdparts=:0x00002000@0x00004000(uboot),0x00020000@0x00006000(boot),0x01000000@0x00026000(rootfs)
```

每段咱们按 `大小@偏移(名字)` 的格式读，单位是 512 字节的扇区：

| 分区 | 扇区数 | 换算 | 起始偏移 | 装什么 |
|---|---|---|---|---|
| uboot | 0x2000 | 4MiB | 0x4000 | u-boot.itb（binman 产物，约 1MiB） |
| boot | 0x20000 | 64MiB | 0x6000 | boot.img（kernel FIT，填充到整分区） |
| rootfs | 0x1000000 | 8GiB | 0x26000 | rootfs.ext4（Ubuntu GNOME） |

头部其余字段也各有归处：`FIRMWARE_VER:8.1` 进 RKAF 头的版本字段，`MACHINE_MODEL`/`MACHINE_ID` 进 RKAF 头的 SoC 标识，`TYPE: GPT` 是用来声明分区表风格的，末尾的 `uuid:rootfs=614e0000-...` 拿来给 rootfs 分区定 GPT UUID。三个分区的数字和启动链其他环节是咬合的。SPL 从 0x4000 找的是 u-boot.itb，扇区是由 `CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_SECTOR=0x4000` 定下来的。boot.scr 则是从 0x6000 裸读 0x20000 个扇区的。还有一个不在表里的要交代：idbloader 裸放在 0x40，GPT 表里根本没有它的位置，烧写工具的 loader 阶段单独写它。对照原厂的 parameter.txt，咱们砍掉了 misc/recovery/backup 一票分区，MVP 只需要 uboot/boot/rootfs 三个而已。另外一个实现细节记在这里：rootfs 的 8GiB 写成写死的定值而不是 `-` 这样的增长记号，因为 rkfw-pack 的解析正则不认增长记号、遇到它就只能按空分区处理，结果当场炸掉，注释里记了原因。

### package-file 清单与 RKAF/RKFW 结构

`package-file-emmc.txt` 是 RKAF 容器的装货单，咱们数下来是六行：

```text
package-file    package-file
bootloader      Image/MiniLoaderAll.bin
parameter       Image/parameter.txt
uboot           Image/u-boot.itb
boot            Image/boot.img
rootfs          Image/rootfs.img
```

咱们把单子读作名字到路径的映射，再加一个 MiniLoaderAll（boot_merger 从公开 rkbin 拼出来的下载 loader，只在烧写时让它进 DRAM 跑一次而已）。

按单子把容器拼起来的活，交给仓库自己的纯 Python 编码器 `rkfw_pack.py`，它替代原厂的 afptool 加 rkImageMaker。它的格式知识是咱们逆向来的：对着原厂工具的产物逐字节比对，再拿社区的 rk_image_tool 规范，跟 afptool-rs 的开源实现做了交叉验证。后者揭示了 Rockchip 自家的 CRC32 变体，它的多项式是 0x04c10db7、不是 IEEE 的 0x04c11db7，拿它复算原厂 afptool 的校验码能逐字节对上（校验 body 得 `0xa93e7e20`、parameter 得 `0xb3aaf39c`，与原厂产物是对到完全一致的），所以格式敢说吃透了。RKAF 容器尾部缀一个 4 字节的 rkcrc32，parameter 还要裹一层 `PARM 头 + 长度 + 数据 + rkcrc32` 的壳再进容器，这些细节错了一个字节，结果烧写工具就翻脸。成品的层次结构摆在这里：

```text
update.img = RKFW 容器
             ├─ 0x66 头（版本、大小）
             ├─ MiniLoaderAll.bin（下载 loader）
             ├─ RKAF 容器
             │   ├─ 0x8C 头（FIRMWARE_VER、MACHINE_MODEL 等，来自 parameter）
             │   ├─ 分区表（每条 112 字节：名字、大小、偏移、uint32 的 size）
             │   └─ 分区镜像（按 0x800 对齐依次摆放）
             └─ 32 字节 ASCII MD5
```

分区表的 112 字节咱们数下来，里面只有条目名和前面提过的五个 uint32、它们各管一件事：

| 字段 | 含义 |
|---|---|
| `nand_size` | 分区在闪存里的大小（扇区计，来自 parameter 的 mtdparts） |
| `pos` | 该镜像数据在 update.img 文件内的偏移 |
| `nand_addr` | 分区在闪存里的起始扇区 |
| `padded` | 镜像数据按 0x800 对齐后的长度 |
| `size` | 镜像的真实字节数——就是被 4GiB 卡脖子的那个 |

烧写工具是拿 `nand_addr` 定位分区、拿 `size`（或 `padded`）定长写入的，五个字段咱们错一个，结果不是拒烧就是写飞。

assemble 阶段咱们还有两道自保的手段。boot.img 是用 0 填充到整 64MiB 的，因为 loader 烧 boot 分区时是整分区擦写的，不填满的话新镜像尾部会留出厂垃圾。update.img 打好后还要做回读自检：用自己的解码器把刚打出来的镜像解开，逐个比对 uboot/boot/rootfs 的体积，对不上的话当场报警。自己打包的镜像自己验，而且不依赖任何原厂工具当裁判。这套编码器还带了 info 和 unpack 子命令，任何一块 update.img（包括原厂出的）都能开箱列条目、解出来看，逆向来的格式知识反过来成了最好的验货工具。assemble 的全貌也交代一句：它支持 provision/nand/rescue/sd/emmc 五个变体，NAND 板的首次引导、救援 shell 各走各的清单，本板 eMMC 走的就是本章的 emmc 变体。

其中一轮收工构建留了完整的产物指纹，咱们可以拿它当整条链产出过什么的凭证看：

```text
rk3588-topeet.dtb  SHA-256 282e630c…
boot.img           SHA-256 9b738b02…
rootfs.ext4        SHA-256 868a6777…
update.img         SHA-256 d100a898…（3290329674 字节）
```

从 dtb 到整包咱们看下来，四个产物是各有指纹的、任何一环被谁动过，咱们都能对出来。可复现性是这套纯 Python 打包链的底色：build_time 写死、UUID 固定、hash_seed 固定，同一份输入两次构建的 update.img 结构一致。

### 烧写：LOADER 模式

镜像齐了，看怎么进板。咱们按住音量上键上电（或在板上 `reboot loader`），板子就蹲成 rockusb 的 LOADER 设备，PC 侧一次烧的也只是一个分区。根文件系统一轮迭代就一条命令的事：

```text
rkdeveloptool wlx rootfs out/rk3588-topeet/rootfs.ext4
```

`wlx` 是按分区名写的，偏移是从 parameter 拿的。整包的 update.img 则走 `RKDevTool` 或 `upgrade_tool`、都能一步到位。RKDevTool 能把板认成 LOADER 设备、靠的是 USB 描述符上的三处身份修正（PID 300a、bcdUSB 0x0201、USB2 BOS），咱们一个都不能缺。比起 MaskROM 少了一步：不用每次都 `db` 灌下载 loader，LOADER 模式是插上线就能写的。但是再快的烧写也架不住频率：3GiB 的根文件系统镜像改一行配置也要重打 ext4、重传 eMMC，这个痛咱们到收尾处再说。

## 成功长这样

板测收据咱们交出来，截的是 8 月 1 日 GNOME 首启的日志，一个字也不是合成的：

```text
[  OK  ] Started wpa_supplicant.service - WPA supplicant.
...
         Starting gdm.service - GNOME Display Manager...
[  OK  ] Started serial-getty@ttyS2.s…vice - Serial Getty on ttyS2.
[  OK  ] Reached target getty.target - Login Prompts.
[  OK  ] Reached target multi-user.target - Multi-User System.
[  OK  ] Started gdm.service - GNOME Display Manager.
[  OK  ] Reached target graphical.target - Graphical Interface.

Ubuntu 26.04 LTS rk3588-topeet ttyS2

rk3588-topeet login:
```

咱们逐行核对：multi-user.target 到位（串口 getty 还蹲在 ttyS2 上、是控制台搬家前的时代印记），gdm.service 起来了，graphical.target 这个图形界面目标也达成了。串口上看到 `Ubuntu 26.04 LTS` 打了出来，这块 ubuntu-base 出身的根文件系统在真板上自报了家门。

再往下一层是桌面的收据。GDM 起来了只是登录管理器活着，桌面显示还要 gnome-shell 真的跑起来，GPU 也要它真的渲染起来。咱们板验下来：gnome-shell 跑起来了（PID 686），固件一内建 `renderD128` 就出现了，GNOME 桌面正常显示在 1024×600 的屏上。那之前的病（桌面黑、`gbm_surface_lock_front_buffer failed` 反复刷）根因在 GPU 侧的固件，这里只确认根文件系统侧的 mesa 用户态在最终链路上尽了职。

诚实的边界咱们照例交代两笔。头一笔是版本：本章的板验记录落在点亮初调当时的 7.1 补丁栈镜像上，不过根文件系统本身与内核版本无关，内核补丁后来整体重放到 v7.3.1 也不动这一章的任何定论。再一笔是稳定性：GNOME 桌面的点亮与稳定是两件事，显示那一侧的 VOP2 硬锁（hard lockup）稳定性保留意见还挂着，就靠本章固化的看门狗和内核侧的取证配置盯着。

最后把开头的承诺收个尾。这一章的迭代姿势摆出来：改 packages.list 或配置，sudo 构建岛咱们就得重走一趟（qemu 装包以几十分钟计），而后 ext4 重打，3GiB 的镜像经 LOADER 模式重烧。镜像和根文件系统其实都可以搬到网络上：tftp 拉内核、NFS 挂根，改完的文件 sync 一下就生效，烧写就从迭代环里彻底消失了。这套免烧录的路子加上撑起它的 GMAC 网卡点亮初调，留到网络章的正题里讲。咱们网络章见。
