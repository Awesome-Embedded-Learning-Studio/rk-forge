# Ubuntu rootfs：从 ubuntu-base 到 GNOME，再打进 eMMC

> 上一章 [GPU 章](04_gpu.md) 咱们收掉了 Panthor 和固件内建，所以内核能给桌面递上 `renderD128`，LCD 出图和触摸坐标咱们也都验过了。但是 GNOME 桌面是另一层的东西，`systemd`、`GDM`、`mesa`、`gnome-shell` 这一大坨用户态全都得住进咱们要造的根文件系统里。这一章咱们就造这块根，咱们拿 Canonical 官方的 ubuntu-base 最小骨架当原料，在 chroot 里咱们把系统喂成 Ubuntu 26.04 GNOME，后面几节咱们再压成 ext4 镜像、打成 update.img 烧进 eMMC。路上咱们碰了两场事故，一场是 GDM 起来了咱们却登录不进去，另一场是咱们烧完才发现整个 rootfs 归了开发机的普通用户。uint32 的体积红线咱们后面细讲，咱们认为事故加红线一起，就是本章最值钱的部分。

## 选型：这块板走 Ubuntu，RK3506B 走 buildroot

rk-forge 咱们铺了两条 rootfs 路线，它们各教各的东西，下面咱们把两边的定位摆清楚。

RK3506B 那卷（[boot 教程的 roadmap](../boot/00_roadmap.md)）咱们走的是 buildroot，用户态咱们拿的就是 busybox，所以教学定位只有一条：把每一字节的决定权都留给咱们自己。rootfs 里有什么、init 怎么起、哪个库在哪个环节被谁链接，这些问题咱们全部摊开看。但是代价也摆在那里，每加一个功能咱们都得自己凑物料。

RK3588 这卷咱们瞄准的是 GNOME 桌面加一票主线外设，这个体量咱们再拿 buildroot 手凑就不现实了。GNOME 这一套其实是几百个互相咬合的包，mesa 用户态、D-Bus、AccountsService、network-manager 这些咱们都得伺候到，所以任何一个版本咬合不上，咱们就得花半天排查。咱们改走 Ubuntu 的 apt 生态，这些咬合关系就让发行版替咱们维护，咱们的精力可以全花在板级和打包上。所以两边是分工：buildroot 卷教咱们搭 rootfs 的骨头，这一卷教咱们把一块现代发行版 rootfs 造出来，咱们还得把它正确地塞进 Rockchip 的烧写格式。

其实两条路线共用同一套 stage/pack 框架，咱们在 [stage.py](../../../src/forge/stage.py) 里开出了 `buildroot`、`openwrt`、`ubuntu` 三个 profile。[board.yaml](../../../boards/rk3588-topeet/board.yaml) 里咱们还留着一行 `rk3588_topeet_defconfig`，注释说它是留给未来的 buildroot profile，`--rootfs=ubuntu` 下咱们用不到它。但是门没关死，咱们这一卷只是不走它而已。咱们收成一张对照表：

| | RK3506B 卷：buildroot | 本卷：Ubuntu |
|---|---|---|
| 用户态 | busybox，几十个命令 | systemd + GNOME，几百个包 |
| 物料来源 | buildroot 菜单配置，自己挑 | packages.list 列清单，apt 解依赖 |
| 教学点 | rootfs 的骨架怎么搭、init 时序 | 发行版 rootfs 怎么造、属主与打包 |
| 打包出口 | UBI（SPI-NAND） | ext4（eMMC） |

原料层面咱们选的起点是 **ubuntu-base**，其实它是 Canonical 官方发布的最小根文件系统压缩包 `ubuntu-base-26.04-base-arm64.tar.gz`，咱们从 cdimage.ubuntu.com 下载这个约 30MB 的包。至于它为什么算最小，咱们看内容就知道了，里面只有 dpkg、apt、systemd、glibc 这几样让 apt 自己能跑起来的骨架，其余的全靠咱们后面用 apt 拉。在咱们手里它就是一袋面粉，本章要做的就是把它烤成蛋糕。

选型上咱们还有一处要交代，咱们为什么用 ubuntu-base，debootstrap 咱们放在了一边。后者是 Ubuntu 官方的另一条造根路线，不过路子是从零 bootstrap 一套基础系统。但是 debootstrap 咱们没走，多轮 chroot 迭代咱们得跑，仿真环境里那一堆一阶段二阶段的脚本咱们也得跟着跑，咱们嫌它又慢又脆。ubuntu-base 其实把能跑 apt 的骨架这一步官方化了，咱们拿到手直接 `apt install`，不确定性就被咱们收窄到 chroot 一层。这个取舍咱们写在 [ubuntu_rootfs.py](../../../src/forge/build/ubuntu_rootfs.py) 的文档串开头，ubuntu-base 加 apt 咱们用，debootstrap 咱们不走。

至于为什么不直接刷官方桌面镜像，咱们也交代一句。官方 arm64 桌面镜像假定的是 UEFI 那套引导流，但是这块板走的是从 BootROM 到 idbloader 的 Rockchip 私有链，咱们在板上内核 log 里能看到 `efi: UEFI not found` 那行直白的回绝。所以 rootfs 咱们自己造、引导咱们自己排，每个环节都握在咱们手里，咱们认为这正是本仓库的立身之道。

## 构建链总览：四步，一处 sudo

咱们把整条链整体摆出来，后面咱们逐段拆：

```text
forge build ubuntu-rootfs   # chroot 里 apt 装包 + 配置，产出 ubuntu-rootfs.tar（要 sudo）
forge stage                 # 解包 tar 到 out/rootfs/，注入运行时配置（fakeroot 下）
forge pack emmc             # mke2fs -d 把树压成 rootfs.ext4（fakeroot 下，免 sudo）
forge assemble --variant emmc    # RKAF/RKFW 打包出 update.img（纯 Python，免 sudo）
```

这四步咱们跑完之后，`out/rk3588-topeet/` 货架上咱们数出这五样东西，后面各节咱们逐个认脸：

```text
ubuntu-rootfs.tar    # build 的产物：整棵 rootfs 的归档（约 2.4GiB 内容）
rootfs/              # stage 铺出的目录树，pack 的输入
.rootfs.fakeroot     # 属主数据库，贯穿 stage 与 pack（下文的主角之一）
rootfs.ext4          # pack 的产物：3GiB 定容 ext4 镜像
update.img           # assemble 的产物：可整包烧写的 RKFW 容器
```

有个设计决定咱们要交代：咱们整条 forge 链全程不用 sudo，唯一的例外其实是第一步的 chroot。原因咱们写在 [ubuntu_rootfs.py](../../../src/forge/build/ubuntu_rootfs.py) 的文档串里。dpkg 的安全检查要求它的数据库目录真的归 root 所有，但是咱们把手头的非特权工具数一圈，文件属主真的是 root、有 `/dev`、能跑 arm64 二进制，这三件事咱们凑不齐。proot 只能替咱们伪装进程 uid、不改文件属主，所以 dpkg 当场拒绝。unshare 咱们用它连 `/dev` 都造不出来。但是 fakeroot 又和 qemu 合不来。所以 chroot 老老实实跑在真 root 下，咱们把它记作全仓库文档化的唯一 sudo 孤岛。tar 做好之后咱们还有指纹缓存，后面 stage/pack/assemble 咱们全都不需要特权，咱们跑 `forge all --rootfs=ubuntu` 时只有第一次要 sudo。

装包之外咱们在 chroot 里还有一段 post-config 要跑，板级身份咱们也要烙进 rootfs。`/etc/fstab` 咱们用它固定根分区与 `/proc`、`/tmp`、`/var/log` 的挂载，其中 /tmp 和 /var/log 咱们让它走 tmpfs，是为了省 eMMC 写入。`/etc/hostname` 咱们写成板名 `rk3588-topeet`，板上 log 里 systemd 那行 `Hostname set to <rk3588-topeet>` 就是它的回声，咱们首次启动就能对上。root 密码咱们置空，这是咱们 MVP（最小可用版本）阶段的开发姿势，所以 ssh 密码通道自动拒绝，咱们就只剩密钥和串口两条路进来，其实反而安全些。至于根设备谁说了算，咱们要分清。内核挂根这一步听 bootargs 的 `root=/dev/mmcblk0p3`，这个参数是 U-Boot 章的 boot.scr 给咱们写进去的，咱们能跟板上 log 里 `VFS: Mounted root (ext4 filesystem) on device 179:3` 这行对上。咱们把 179:3 分成两半看，它其实是 mmc 主设备号 179 加第三分区。fstab 是 systemd 起来之后咱们的第二份记录。这些配置进的是缓存的 tar，所以咱们改它们就要重走 sudo 构建岛，这一点由指纹缓存替咱们强制执行。

背景咱们再说一句。咱们这颗 Ubuntu rootfs 不只伺候真板，rk3588-lite 仿真线咱们也拿来当真根跑冒烟，细节咱们记在 [notes/67](../../notes/67-2026-08-26-rk3588-lite-heterogeneous-ubuntu.md)（QEMU 异构 8 核）。同一颗镜像咱们两头吃，板上出问题之前咱们拿仿真线过一遍，这就是咱们仿真线的用法，本卷咱们不展开。

## 第一段：从 ubuntu-base 到能登录

### chroot 里跑 apt：qemu 慢世界的两个提速

arm64 的 rootfs 咱们要在 x86 开发机上装配，靠的是 binfmt_misc 注册的 `qemu-aarch64-static`，这个机制咱们下面就说。binfmt_misc 是内核的一个机制，按文件头魔数给非本机架构的二进制自动选解释器这件事咱们交给它办，这里咱们选的就是 qemu 的静态版。流程咱们摆一下，咱们把 qemu 静态二进制拷进 chroot，咱们再 bind-mount `/proc` `/sys` `/dev`，resolv.conf 咱们也放一份，然后咱们跑下面的命令：

```text
chroot <work> /usr/bin/apt-get update
chroot <work> /usr/bin/apt-get install -y --no-install-recommends <packages.list 里的全部包>
chroot <work> /usr/bin/apt-get clean
```

chroot 里的 arm64 dpkg，咱们就在 qemu 翻译下跑起来了。`--no-install-recommends` 咱们开着也是在省钱，桌面元包的推荐依赖咱们见过，而它们动不动就把体积和安装时间吹大一圈，开发板 rootfs 咱们只装清单里列出的东西。装完咱们记得把 qemu 静态二进制从 rootfs 里删掉，它只是给开发机仿真用的，板上真 arm64 咱们用不着它。

qemu 翻译有多慢咱们领教过，装过 ubuntu-desktop 的都知道。这里咱们有两个实测有效的提速，都是咱们拿教训换来的：

- `sources.list` 写 `trusted=yes`。qemu 下 keyboxd（gpg key 守护进程）的 IPC 举止异常，合法密钥也验签失败。构建期的源是清华镜像加 ports.ubuntu.com 兜底，都是可信镜像，构建时跳过 GPG 验签，省掉一类纯属仿真副作用的失败。
- 删掉 `/etc/apt/apt.conf.d/70debconf`（关掉 preconfigure）。qemu 下 apt-extracttemplates 要提前把每个包的 debconf 配置脚本跑一遍，几十分钟的纯开销，而咱们全程 `DEBIAN_FRONTEND=noninteractive`，这些脚本跑了也白跑。删掉之后包在解包阶段直接配置。

apt 源本身咱们配的是清华 tuna 镜像主源、`ports.ubuntu.com` 官方源兜底，咱们给两边各配 `main/restricted/universe/multiverse` 四个组件和 `-updates/-security` 两个跟进源，完整的 sources.list 咱们放在 [ubuntu_rootfs.py](../../../src/forge/build/ubuntu_rootfs.py) 里。

装什么包咱们不在脚本里硬编码，说了算的是板目录下的 [ubuntu/packages.list](../../../boards/rk3588-topeet/ubuntu/packages.list) 清单。这个文件咱们认为是块活的教学材料，下面讲 GNOME 的时候咱们还会回来细读。

### 串口 getty：console 在哪，登录提示符就在哪

咱们要 rootfs 能登录，第一件事是让一个 getty 替咱们蹲在串口上。getty 这个名字咱们分开看就是 get tty 的缩写，它干的活就是在终端上打印登录提示符、把会话交给 login。这里咱们有个省心的机制。至于最后一个 console 对应的 serial-getty，systemd 会自动侦测 cmdline 里的 `console=` 把它拉起来，所以咱们一行配置都不用写。这个机制咱们在 rk3588-lite 仿真线上验证过（[notes/70](../../notes/70-2026-08-27-rk3588-systemd-ubuntu-login.md)），咱们看到同一颗 Ubuntu rootfs 在 QEMU 里被 systemd 259 拉到串口 login，三断言咱们全核过。但是仿真线在本卷只当冒烟预检用、不当证据链主干。其实板上 log 里它也如实发生，咱们翻 8 月 1 日的首启 log（[202608011826.txt](../../logs/rk3588/202608011826.txt)）能看到 `[  OK  ] Started serial-getty@ttyS2.service`，紧接着串口上咱们就能看到 `Ubuntu 26.04 LTS rk3588-topeet ttyS2` 和 `rk3588-topeet login:`。

但是咱们注意到 console 在那天晚上搬了家。内核章讲过的 fan53555 误领 rk860x 那场 I²C 卡死病，就发生在咱们把 console 搬到 ttyFIQ0 之后。这次搬家切的是原厂式的 ttyFIQ0，背书的是 FIQ 调试器。rootfs 侧咱们要跟上，现在的构建里 rk3588 板的 post-config 咱们写成显式启用 `serial-getty@ttyFIQ0.service`，同时咱们删掉 ttyS2 的 getty。咱们不删它，而 ttyS2 一旦留下就要和 ttyFIQ0 抢同一个 UART、在 FIQ 调试器背后重新打开串口，所以会制造出一类极难定位的串口怪象。搬家的收据咱们也留了，在当晚 21:17 的 log 里咱们能翻到，文件咱们用 [202608012117.txt](../../logs/rk3588/202608012117.txt)，咱们摘一段：

```text
Welcome to Ubuntu 26.04 LTS!
[    2.070627] systemd[1]: systemd 259.5-0ubuntu3 running in system mode (+PAM +AUDIT ...)
[    2.070658] systemd[1]: Detected architecture arm64.
[    2.074707] systemd[1]: Hostname set to <rk3588-topeet>.
[    2.315171] systemd[1]: Queued start job for default target graphical.target.
...
         Expecting device dev-ttyFIQ0.device - /dev/ttyFIQ0...
```

咱们看这段 log，systemd 259 在 ARM64 上以 system mode 起来了，hostname 读到的板名正是咱们烙进 rootfs 的那个，graphical.target 进了队列这件事咱们也确认过，getty 已经蹲到 ttyFIQ0 上等设备了。log 咱们截在 boot 早期，graphical.target 达成的收据咱们放到后文成功长这样一节看。

这块板级配置里咱们还固化了看门狗，咱们在 systemd 里定了 `RuntimeWatchdogSec=30s`，咱们喂的是板上那颗 DesignWare 看门狗。lockup 诊断 sysctl 咱们也固化了一整套，`panic_on_oops`、`hardlockup_panic` 这些开关咱们让它们检测到就 panic。那些是内核章的取证装备，咱们在内核章已经讲过道理，这里咱们只把它们落到 rootfs 的文件上、不再重讲。

### 用户与属主：两场事故

到这里咱们能让 rootfs 出登录提示符了，但是 GNOME 还起不来。GDM 咱们说全名是 `GNOME Display Manager`，它管的就是图形登录，它面前咱们一个可登录的用户都拿不出来。这是咱们本章的第一场事故，咱们顺着它往下挖，挖出来的是更深的一场。完整病历咱们记在 [notes/56](../../notes/56-2026-08-02-rk3588-ubuntu-user-rootfs-ownership.md)。

**症状一：咱们没有可登录的用户。** 当时的 staged rootfs 咱们查下来，`/etc/passwd` 里咱们只数出 root 和系统用户，UID ≥ 1000 的普通用户咱们一个都数不出来。但是 GDM 默认不提供 root 图形登录，所以 GDM 起来了、greeter（登录欢迎界面）也亮了，咱们就是进不去。解法本身不复杂：构建时咱们在 chroot 里 `useradd` 一个 UID/GID 1000 的普通用户，附加组咱们给它挂 `adm sudo audio video render input plugdev netdev` 一共八个（GPU 渲染要进 render 组、桌面音频要进 audio 组，这些组关系咱们后面全用得上）。bringup（板子点亮初调）时期这个用户咱们定的是 `charliechen`，密码咱们明文公开，GDM 咱们给它配了自动登录，其实属于开发阶段的 bring-up 凭据。后来这坨东西咱们把它制度化：用户默认值咱们收敛成通用的 `rk-forge/rk-forge`，个人身份咱们走 `user/account.yaml` 覆盖，密码咱们在开发机上用 `openssl passwd -6` 哈希、再经 `chpasswd -e` 注入，明文咱们只让它活在开发机的 YAML 里，镜像里其实只有哈希。凭据咱们不放进镜像，这一课咱们认为是从 bringup 走向可发布时必须补的。

自动登录其实是两份文件配合的结果，`/etc/gdm3/custom.conf` 咱们写 `AutomaticLoginEnable = true` 加 `AutomaticLogin = <user>`，`/var/lib/AccountsService/users/<user>` 咱们写 `SystemAccount=false`，所以 AccountsService 认它是真人用户，greeter 才把它列出来给咱们看。板验的记录咱们同样落在 notes/56。shadow 的 `SHA-512` 哈希咱们对过与预期密码匹配，八附加组咱们数了齐全，custom.conf 的自动登录目标咱们核下来正确。开发阶段自动登录咱们用着很方便，产品化之前咱们要关掉它并换密码，这个边界咱们在 notes/56 里有原话记着。

**症状二：整个 rootfs 都归了开发机的普通用户。** 咱们在新增用户之前检查了一下此前的成品 `rootfs.ext4`，结果比没有用户严重得多：

```text
/etc/passwd  uid=1000 gid=1000
/bin/bash    uid=1000 gid=1000
/home        uid=1000 gid=1000
```

passwd、bash、整个 /home 咱们查下来，其实全是 uid 1000。一个 UID 1000 的新用户将把 passwd 和 bash 在内的一大票系统文件都据为己有，咱们认为这镜像不能用。

根因咱们定位在解包那一环。`ubuntu-rootfs.tar` 咱们验过本身是对的，tar 里存着的是数字属主 root:0。但是当时的 stage 脚本由普通用户执行，tar 解包时咱们 chown 不到 root，磁盘上的 staging 树全部落成了开发机用户的 UID/GID 1000，随后 `mke2fs -d` 忠实地把错误属主写进了 ext4。所以这是权限问题：全链路咱们设计的目标本来是不用 sudo，写属主的权力咱们却给不出来。

**解法：咱们用 fakeroot 数据库把属主信息背着走。** fakeroot 的原理是在进程外面拦一层，chown 调用它替咱们记进一个属主数据库，文件在磁盘上咱们看到的还是普通属主，但是在 fakeroot 会话的视图里它已经是 root。关键动作咱们认为是把数据库持久化：stage 阶段咱们用 `tar --numeric-owner --same-owner` 解包，整个 stage 咱们跑在 `fakeroot -s` 下把属主状态存进 `out/.rootfs.fakeroot`。pack 阶段咱们用 `fakeroot -i` 加载同一份数据库再跑 `mke2fs -d`，属主原样进了 ext4，咱们全程仍然不需要 sudo、mount 或 loop 设备。两个工程细节咱们记一下。一是 WSL2 下咱们要设 `FAKEROOTDONTTRYCHOWN=1`，咱们漏设的话 tar 的 chown 返回 EINVAL，所以构建当场就炸。二是 fakeroot 的重入咱们选了 fork+wait 而不是 exec，早期版本咱们用 exec 真的会把整个 forge 进程替换掉，`forge all` 就在 pack 之后悄无声息地断掉，而 assemble 永远轮不到跑。

修完咱们用只读 `debugfs` 直接查成品镜像的 inode、不看 staging 树自欺欺人（[notes/56](../../notes/56-2026-08-02-rk3588-ubuntu-user-rootfs-ownership.md) 的验证记录）：

```text
/etc/passwd                                  0:0 mode 0644
/bin/bash                                    0:0 mode 0755
/usr/lib                                     0:0 mode 0755
/home/charliechen                         1000:1000 mode 0750
/var/lib/AccountsService/users/charliechen   0:0 mode 0600
```

咱们验收的属主标准是系统文件归 root、家目录归用户、AccountsService 里的用户描述归 root，咱们才认它是一块能见人的 rootfs。

**回归：咱们在家目录属主上二次翻车。** 属主链咱们修好之后，咱们在 2026 年 8 月 15 日又在板上翻了一次同族的车。rootfs tar 咱们查出来是 `--owner=0 --group=0` 平铺打出来的，登录用户的家目录进了镜像就成了 root 属主，板上 gnome-shell、gvfs、dconf 咱们看着成片失败，localsearch 的崩溃循环咱们也抓到了。修法咱们进了 [stage.py](../../../src/forge/stage.py)，stage 那边咱们让它在 fakeroot 会话里对 `/home/<user>` 补一次 `chown 1000:1000`，属主落进了保存的数据库、最终也进了 rootfs.ext4。同一次 stage 咱们还注入了几样开发板刚需：

- sudoers.d 里的 `NOPASSWD`。用户在 sudo 组但仍要密码，root 又没密码可回退，串口上的无人值守流程就会卡死在密码提示上。
- 一份能用的 resolv.conf（chroot 时代的那份解析不了任何域名）
- 开发者的 ssh 公钥进 `/root/.ssh/authorized_keys`（重烧镜像后 ssh 免配置）

教训咱们浓缩成一句，属主问题咱们碰过就不止一次，往后它还会回来找咱们，但是 root 属主的树配上无特权工具链，这对矛盾就一直在咱们眼前，每个新环节进场咱们都要重新核对一遍属主。

这里咱们能看清 stage 与 build 的分工哲学（[stage.py](../../../src/forge/stage.py) 的文档串写着架构条目）。build 咱们让它拥有全部 rootfs 定制，用户、getty、看门狗咱们烙进 tar，sysctl 咱们也在 chroot 里定了。stage 咱们只让它做物化，把 tar 铺成目录树这件事咱们交给它，咱们外加少量必须避开缓存和 git 的运行时注入，凭据、DNS、属主修复咱们都算在这一类。定制咱们只有一份源头，build 与 stage 就不会跟咱们各说各话，咱们认为这是这套框架最省心的地方。

## 第二段：从能登录到 GNOME

### 包清单怎么读

[packages.list](../../../boards/rk3588-topeet/ubuntu/packages.list) 按用途分了段，咱们读它像读一份作战序列：

- init 与基础（systemd、dbus、udev、kmod）：ubuntu-base 已有 systemd，这段是显式确认。
- 网络（netplan.io、iproute2、openssh、wpasupplicant、network-manager）。
- 固件（linux-firmware）：WiFi/BT 固件全从这里来。
- GPU 用户态（mesa-utils、libgl1-mesa-dri）。
- 桌面本体（ubuntu-desktop）。
- 开发工具（vim-tiny、curl、htop、i2c-tools 这些）加诊断武器（strace、binutils、gdb、xz-utils）。

其中两个条目咱们要多说两句。`ubuntu-desktop` 其实是元包（meta package，自己不含文件、只靠依赖关系把一整套软件拉进来的空壳包），它拖进来的就是 gdm3、gnome-shell、mutter、wayland、xorg 加整个桌面栈，所以 GNOME 能一条清单就装齐，功劳咱们记在依赖关系这个大管家头上。诊断武器那四件（strace、binutils、gdb、xz-utils）是另一场战役的遗产：最小系统里咱们缺过它们，攻坚期咱们只能靠内核 printk 打点加手写工具绕行，所以清单注释给它们记了时间税太高的判词。板上崩 mesa 时咱们拿 gdb 直接在板上看反汇编，断点、变量、调用栈咱们当场就能看。隔着串口猜就只剩内核 printk 的回声，一条一条地等。

但是清单不是一次写好的。注释里咱们留了一条板验记录：咱们翻 8 月 12 日的记录，那颗 rootfs 里咱们没配 network-manager，所以板上 `nmcli` 报 command not found，当时的网络咱们靠 netplan 加 wpa_supplicant 手撑，network-manager 是咱们后来才补进清单的。所以 packages.list 也进了指纹，咱们改它一次，结果缓存的 rootfs tar 就判过期，sudo 构建岛咱们就得重走。不过纪律本身是 2026-08-15 那次事故换来的，当时咱们 sysctl 改了三天、镜像是旧的，这个教训同样记在 [ubuntu_rootfs.py](../../../src/forge/build/ubuntu_rootfs.py) 的缓存守卫注释里。

机制上咱们再看一眼，`.ubuntu-rootfs-built` 这个标记文件里存的其实是一份内容摘要，咱们对 packages.list 和构建器源码本身做哈希，结果就落成这个标记文件。缓存命中时咱们要比对摘要，摘要对不上咱们就重建，除此之外咱们不留第三条路。

### mesa 用户态：上一章内核侧的另一半

咱们把桌面落到 GPU 上，两侧咱们要同时到位。内核侧上一章讲完了，交的就是 Panthor 驱动加内建的 `mali_csffw.bin` 固件，所以 `renderD128` 出现了。rootfs 这一侧咱们给的是 mesa 用户态（mesa 24.x 起自带 Panthor 的 Gallium 驱动），`libgl1-mesa-dri` 咱们用它把整个 GL/DRI 栈拉进来。两侧咱们在 `/dev/dri/renderD128` 这个设备节点上碰头，mutter（GNOME 的窗口管理器兼显示服务器）通过 GBM 拿 GPU 的 buffer，渲染节点咱们缺了，结果就是上一章开头那场桌面黑屏、`gbm_surface_lock_front_buffer failed` 的病。内核的 DRM 驱动和用户态的 mesa 之间，是一整套共享的接口约定。哪一侧咱们对不上，咱们看到的都是黑屏。这两侧咱们分了两章讲，但是验收是合一的。

### graphical.target 链与体积红线

包装齐之后咱们再看开机链，它是 systemd 的标准上坡。graphical.target 是咱们这块板的默认目标，板上 log 那行 `Queued start job for default target graphical.target` 咱们可以当证据，它比 multi-user.target（getty、网络）多拉了一票图形服务，gdm.service 咱们数下来是其中之一。GDM 起来后咱们要跟它打交道的有两件事，图形会话的立起归它，自动登录或者弹 greeter 咱们怎么选，听的是 AccountsService 的配置。最终咱们看到 gnome-shell 作为用户会话跑起来，而 mutter 在里面兼任显示服务器，把窗口合成到 LCD 章点亮的那块 1024×600 屏上。板上实测的收据咱们放在下一节成功长这样里看。

体积咱们也要算一遍。GNOME 桌面加 mesa 加 linux-firmware 咱们装下来，rootfs 咱们量下来落在约 2.4GiB。ext4 镜像咱们定的是 3072MiB，装下 2.4GiB 咱们还有余量。最终成品咱们在 [notes/56](../../notes/56-2026-08-02-rk3588-ubuntu-user-rootfs-ownership.md) 那一轮构建里量过，`update.img` 咱们量出来共 3290329674 字节（约 3.06GiB）。这 3GiB 咱们不是随手拍的，下一节咱们讲它头上的红线。

## 打进 eMMC：ext4、parameter、RKAF

rootfs 咱们看它在货架上还只是 `rootfs.ext4` 一个文件。最后一步咱们把它和 uboot、boot 一起装进容器，而且装的还得是 Rockchip 烧写工具生态认的格式。这一章咱们从里到外过一遍，ext4 咱们怎么打，体积为什么定 3GiB，分区表咱们怎么读，容器咱们怎么拼，最后咱们怎么烧。

### mke2fs -d：不 mount 不 loop 的 ext4

咱们要把一棵目录树变成 ext4 镜像，常规的路子是 dd 一个空文件、losetup、mkfs、mount、拷树、umount，而且每一步都要 root。forge 走的是另一条路：咱们拿 `mke2fs -d`（[pack/emmc.py](../../../src/forge/pack/emmc.py)）让 mke2fs 直接从目录树填充文件系统，所以全程无特权、无 loop 设备。

```text
mke2fs -q -F -t ext4 -b 4096 -L rootfs
       -U 11111111-2222-3333-4444-555555555555
       -E hash_seed=66666666-7777-8888-9999-aaaaaaaaaaaa
       -d out/rootfs out/rootfs.ext4 3072M
```

两个写死的值咱们有讲究，UUID 和 hash_seed 咱们写死了，镜像结构咱们就能复现（superblock 写入时间仍会变，所以不是逐字节金标，但是结构稳定）。这个 UUID 咱们不是写着玩的，板上 log 里咱们翻到内核亲口报的那行 `EXT4-fs (mmcblk0p3): mounted filesystem 11111111-2222-3333-4444-555555555555 r/w`（[202608012117.txt](../../logs/rk3588/202608012117.txt)），所以看到这串数字就知道挂上的正是 forge 打的这块镜像。

pack 咱们还让它把 boot.scr 烙进镜像：咱们拿 mkimage 把 [boot-emmc.cmd](../../../boards/rk3588-topeet/fit/boot-emmc.cmd) 裹成 U-Boot script 格式，在 `/boot/boot.scr` 和分区根的 `/boot.scr` 咱们各放一份。为什么是 rootfs 分区来扛引导脚本？因为 boot 分区是裸 FIT 没有文件系统（U-Boot 章反复强调的那个设计），bootflow 的 SCRIPT bootmeth 只能在 ext4 的 rootfs 分区上找到它，找到了再由它裸读 boot 分区、bootm 交内核。引导入口咱们说它住在 rootfs 里，这是本板布局的一个容易想拧的点。

Ubuntu 的属主要求咱们在这里兑现：pack 发现货架上躺着 `.rootfs.fakeroot`，咱们再 fork 一个加载了属主数据库的 fakeroot 子进程把整个 pack 重跑一遍，`mke2fs -d` 拿到的就是 root 属主的系统文件，上一节那套机制咱们看它到这里走完。pack 开工前咱们还有一道防御，咱们把整棵 staging 树扫一遍，任何读不了的条目咱们看着就拒打（典型来源是 NFS 时代留在树里的污染），免得咱们打出一块带黑洞目录的镜像到板上才炸。

### 为什么镜像只有 3GiB：一条 uint32 的红线

[board.yaml](../../../boards/rk3588-topeet/board.yaml) 的 `rootfs_mib: 3072` 咱们给它挂了一句注释，注释咱们写成 `ext4 镜像大小，必须小于 4GiB，因为 RKAF 条目的 size 字段是 uint32`。

咱们展开说。update.img 的正文是一个 RKAF 容器（下一小节拆它），容器里每个分区条目咱们数它是 112 字节，尾部的五个字段咱们数出来是 `nand_size、pos、nand_addr、padded、size`，写入咱们全部走 `struct.pack('<IIIII', ...)`，所以每个都是无符号 32 位整数、最大到 4294967295，4GiB 的镜像咱们一放就直接溢出。所以塞进 update.img 的 rootfs.ext4 必须守住 4GiB 的红线，取 3GiB 是咱们给约 2.4GiB 的 GNOME rootfs 留的增长空间。

有个数字对比咱们拿来帮着把三层约束分开记：咱们这块板的 eMMC 是 116GiB（板上 log `mmcblk0: mmc0:0001 METORA 116 GiB`），所以物理空间咱们完全不缺。GPT 里 rootfs 分区咱们切了 8GiB，这个规划其实是咱们仓库自己定的。镜像咱们定 3GiB，结果才是 RKAF 格式逼出来的硬上限。咱们把 116GiB、8GiB、3GiB 摆在一起，它们分属的层级咱们一层层数得清，咱们别把它们混成一个问题。

那 GPT 分区表里的 rootfs 分区为什么敢写 8GiB？因为那是咱们切在 eMMC 上、不走 RKAF 条目的分区，uint32 咱们看它管不着它。两道天花板咱们说它们是两码事：分区 8GiB 咱们是给 rootfs 长大留的地，镜像 3GiB 是烧写格式给的框。assemble 时咱们还有第三道检查（`_check_rootfs_fits`），镜像体积咱们要求不得超过分区体积，超了咱们直接报错拒打，报错里咱们会提示要么缩 `--rootfs-mib` 要么改 parameter 扩分区。

### parameter-emmc-topeet.txt 逐行读

[parameter-emmc-topeet.txt](../../../boards/rk3588-topeet/parameter-emmc-topeet.txt) 是烧写工具读的分区表。头部咱们看它是一段元数据，字段咱们数出 `FIRMWARE_VER`、`MACHINE_MODEL: RK3588`、`MACHINE_ID: 007` 这几样。`MAGIC: 0x5041524B` 咱们单独看，四个字节正是 `PARK` 的 ASCII，咱们说这是 Rockchip 的小幽默。咱们真正要读的是 CMDLINE 那行：

```text
CMDLINE:mtdparts=:0x00002000@0x00004000(uboot),0x00020000@0x00006000(boot),0x01000000@0x00026000(rootfs)
```

每段咱们按 `大小@偏移(名字)` 的格式读，单位咱们知道是 512 字节扇区：

| 分区 | 扇区数 | 换算 | 起始偏移 | 装什么 |
|---|---|---|---|---|
| uboot | 0x2000 | 4MiB | 0x4000 | u-boot.itb（binman 产物，约 1MiB） |
| boot | 0x20000 | 64MiB | 0x6000 | boot.img（kernel FIT，填充到整分区） |
| rootfs | 0x1000000 | 8GiB | 0x26000 | rootfs.ext4（Ubuntu GNOME） |

头部其余字段咱们也各有归处：`FIRMWARE_VER:8.1` 进 RKAF 头的版本字段，`MACHINE_MODEL`/`MACHINE_ID` 进 RKAF 头的 SoC 标识，`TYPE: GPT` 咱们用它声明分区表风格，末尾的 `uuid:rootfs=614e0000-...` 咱们拿来给 rootfs 分区定 GPT UUID。三个分区数字咱们跟 U-Boot 章对得上。SPL 咱们看它从 0x4000 找 u-boot.itb，扇区由 `CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_SECTOR=0x4000` 帮咱们定下来。而 boot.scr 从 0x6000 裸读 0x20000 个扇区。还有一个不在表里的咱们要交代：idbloader 咱们把它裸放在 0x40、GPT 表里根本没有它的位置，烧写工具的 loader 阶段单独写它。对照原厂的 parameter.txt，咱们砍掉了 misc/recovery/backup 一票分区，MVP 咱们只需要 uboot/boot/rootfs 三个。另外一个实现细节咱们记在这里：rootfs 的 8GiB 咱们写成写死的定值而不是 `-` 这样的增长记号，因为 rkfw-pack 的解析正则不认增长记号，咱们遇到它就只能按空分区处理，结果当场炸掉，注释里咱们记了原因。

### package-file 清单与 RKAF/RKFW 结构

[package-file-emmc.txt](../../../boards/rk3588-topeet/package-file-emmc.txt) 是 RKAF 容器的装货单，咱们数下来六行：

```text
package-file    package-file
bootloader      Image/MiniLoaderAll.bin
parameter       Image/parameter.txt
uboot           Image/u-boot.itb
boot            Image/boot.img
rootfs          Image/rootfs.img
```

咱们把单子读作名字到路径的映射，再加一个 MiniLoaderAll（U-Boot 章咱们讲过，boot_merger 从公开 rkbin 拼的下载 loader，咱们只在烧写时让它进 DRAM 跑一次）。

按单子把容器拼起来的活，咱们交给仓库自己的纯 Python 编码器 [rkfw_pack.py](../../../src/forge/tools/rkfw_pack.py)，它替代原厂的 afptool 加 rkImageMaker。它的格式知识咱们是逆向来的：咱们对着原厂工具的产物逐字节比对，再拿社区的 rk_image_tool 规范和 afptool-rs 的开源实现，咱们做了交叉验证。后者给咱们揭示了 Rockchip 自家的 CRC32 变体，它的多项式是 0x04c10db7、不是 IEEE 的 0x04c11db7，咱们拿它复算原厂 afptool 的校验码能逐字节对上（校验 body 得 `0xa93e7e20`、parameter 得 `0xb3aaf39c`，与原厂产物咱们对到完全一致），所以格式咱们敢说吃透了。RKAF 容器尾部咱们缀一个 4 字节的 rkcrc32，parameter 咱们也要裹一层 `PARM 头 + 长度 + 数据 + rkcrc32` 再进容器，这些细节咱们错一个字节，结果烧写工具就翻脸。成品的层次结构咱们摆在这里：

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

分区表的 112 字节咱们数下来，里面只有条目名和前面提过的五个 uint32，咱们看它们各管一件事：

| 字段 | 含义 |
|---|---|
| `nand_size` | 分区在闪存里的大小（扇区计，来自 parameter 的 mtdparts） |
| `pos` | 该镜像数据在 update.img 文件内的偏移 |
| `nand_addr` | 分区在闪存里的起始扇区 |
| `padded` | 镜像数据按 0x800 对齐后的长度 |
| `size` | 镜像的真实字节数——就是被 4GiB 卡脖子的那个 |

烧写工具咱们看它拿 `nand_addr` 定位分区、拿 `size`（或 `padded`）定长写入，五个字段咱们错一个，结果不是拒烧就是写飞。

assemble 阶段咱们还有两道自保。boot.img 咱们用 0 填充到整 64MiB，因为 loader 咱们看它烧 boot 分区是整分区擦写，咱们不填满的话新镜像尾部会留出厂垃圾。update.img 咱们打好后还要做 round-trip 自检，咱们用自己的解码器把刚打出来的镜像解开，咱们逐个比对 uboot/boot/rootfs 的体积，对不上咱们当场报警。自己打包咱们自己验，而且不依赖任何原厂工具当裁判。这套编码器咱们还给它带了 info 和 unpack 子命令，任何一块 update.img（包括原厂出的）咱们都能开箱列条目、解出来看，逆向来的格式知识反过来成了最好的验货工具。assemble 的全貌咱们也交代一句：它支持 provision/nand/rescue/sd/emmc 五个变体，NAND 板的首次引导、救援 shell 各走各的清单，本板 eMMC 走的就是本章的 emmc 变体。

notes/56 那轮收工构建咱们留了完整的产物指纹，咱们可以拿它当整条链产出过什么的凭证看：

```text
rk3588-topeet.dtb  SHA-256 282e630c…
boot.img           SHA-256 9b738b02…
rootfs.ext4        SHA-256 868a6777…
update.img         SHA-256 d100a898…（3290329674 字节）
```

咱们从 dtb 到整包看下来，四个产物咱们各有指纹，任何一环被谁动过咱们都能对出来。可复现性咱们说是这套纯 Python 打包链的底色，build_time 咱们写死、UUID 固定、hash_seed 固定，这些都定了下来，同一份输入咱们两次构建的 update.img 结构一致。

### 烧写：回到 U-Boot 章的 Loader 模式

镜像齐了，咱们看怎么进板。U-Boot 章咱们把 rockusb Loader 模式点亮，等的就是烧写根文件系统的日子：咱们按住音量上键上电（或在板上 `reboot loader`），板子咱们看它蹲成 LOADER 设备，PC 侧咱们就只烧一个分区。rootfs 咱们一轮迭代就一条命令：

```text
rkdeveloptool wlx rootfs out/rk3588-topeet/rootfs.ext4
```

`wlx` 咱们按分区名写，偏移咱们从 parameter 拿。整包 update.img 咱们则走 `RKDevTool` 或 `upgrade_tool`，反正咱们都能一步到位。RKDevTool 咱们看它能把板认成 LOADER 设备，靠的是 U-Boot 章那三发身份补丁（PID 300a、bcdUSB 0x0201、USB2 BOS），咱们说一个都不能缺。咱们比起 MaskROM 少了一步，咱们不用每次都 `db` 灌下载 loader，Loader 模式咱们插上线就能写。但是再快的烧写也架不住频率：3GiB 的 rootfs 镜像咱们改一行配置也要重打 ext4、重传 eMMC，这个痛咱们到收尾处再说。

## 成功长这样

咱们把板测收据交出来，咱们截的是 8 月 1 日的 GNOME 首启 log，文件咱们放在 [202608011826.txt](../../logs/rk3588/202608011826.txt)，咱们保证一个字没合成：

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

咱们逐行核对：multi-user.target 到位（串口 getty 还蹲在 ttyS2 上、是 console 搬家前的时代印记），gdm.service 起来了，graphical.target 这个图形界面目标也达成了。串口上咱们看到 `Ubuntu 26.04 LTS` 打了出来，这块 ubuntu-base 出身的 rootfs 在真板上自报了家门。

再往下一层是桌面的收据。GDM 起来咱们看只是登录管理器活着，桌面显示咱们还要 gnome-shell 真跑起来，GPU 咱们也要它真渲染。这两项的板验记录在 [notes/48](../../notes/48-2026-08-01-rk3588-gpu-firmware-embedded-gnome-desktop.md)：gnome-shell 跑起来了（PID 686），固件一内建 `renderD128` 就出现了，GNOME 桌面正常显示在 1024×600 的屏上。那之前的病（桌面黑、`gbm_surface_lock_front_buffer failed` 反复刷）是上一章的主戏，这里咱们只确认 rootfs 侧的 mesa 用户态在最终链路上尽了职。

诚实的边界咱们照例交代两笔。头一笔咱们交代版本，本章的板验记录落在 bringup 当时的 7.1 补丁栈镜像上，不过 rootfs 本身与内核版本无关，所以 v7.3.1 的 rebase（内核章）不动这一章的任何定论。再一笔咱们交代稳定性，GNOME 桌面的点亮与稳定是两件事，LCD 章末尾挂着的 VOP2 硬锁（hard lockup）稳定性保留意见，就靠内核章的取证装备和本章固化的看门狗盯着。

最后咱们把开头的承诺收个尾。这一章的迭代姿势咱们摆出来：咱们改 packages.list 或配置，sudo 构建岛咱们重走（qemu 装包以几十分钟计），ext4 咱们重打，3GiB 镜像咱们经 Loader 模式重烧。内核章那边已经用上了 tftp 拉内核、NFS 挂根的免烧录路子，rootfs 咱们同样可以整个搬到网络上，改完文件咱们 sync 一下就生效，咱们让烧写从迭代环里彻底消失。这套免烧录的路子加上撑起它的 GMAC 网卡 bring-up，咱们留到网络章正题里讲。咱们网络章见。
