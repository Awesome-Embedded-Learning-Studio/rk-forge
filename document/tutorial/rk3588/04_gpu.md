# GPU：Panthor、那颗绕不开的固件，和 GNOME 的第一帧

> [上一章](03_lcd.md) 把显示链交清楚了：VOP2 扫出、DSI2 编码、TC358775 桥、面板、GT911 触摸，咱们看到像素一路走到了玻璃。显示链本章咱们一行不重讲，只从它跟 GPU 的那个接口切进去：**谁来生产像素**。上一章结尾埋的那句『桌面已经在屏上了，该让它有 GPU 加速了』，背后还藏着一段咱们没讲过的小黑历史：LCD 显示那关收官那天，GNOME 桌面亮起来之前的那一会儿，屏幕其实黑过一阵。黑的原因不在显示链，在 GPU 这头：Mali-G610 的驱动 probe 失败了，而失败的根源，是一颗 282 KB 的闭源固件没在正确的时机出现在正确的位置。所以这一章就讲这颗固件，讲它背后的 CSF 架构为什么把“加载固件”变成启动链里绕不开的一环。

版本口径沿用 [内核章](02_kernel.md)：本章的板验里程碑是咱们在 v7.1 栈上验出来的（[notes/48](../../notes/48-2026-08-01-rk3588-gpu-firmware-embedded-gnome-desktop.md)，log 里的版本串是 `7.1.0-00002-g6c8532e28925`）。内核章收官的 rebase 之后，这套 GPU 配置（Panthor + 内建固件）咱们在 v7.3.1 上原样沿用。

## Mali-G610：一颗必须喂固件才肯干的 GPU

咱们补一点架构背景打底，不然固件这个角色是没头没脑的。

Mali GPU 这几年换代的分水岭，是 Arm 在 Valhall 架构后期引入的 **CSF（Command Stream Frontend，命令流前端的意思）**，咱们后面就叫它 CSF。老一代 Mali 的内核驱动是直接跟硬件打交道的（RK3568 那颗 G52 就是 boot 系列装过的），驱动自己往 GPU 寄存器里写的是作业描述符、自己排的是调度，GPU 就是一堆可以被 CPU 直接编排的硬件单元，咱们在整个栈里见不着固件的影子。到了第九代 Mali 这一代，Arm 把这套编排逻辑搬进了 GPU 内部一颗小小的 **MCU（微控制器，GPU 里的小 CPU）**——这颗 MCU 出厂时是空白的，咱们得给它喂一份固件，它才肯替咱们调度整个 GPU。

命令的提交方式跟着全变了，咱们拿两种架构对比着看：老架构是 CPU 逐个写寄存器，CSF 架构是 CPU 把命令流写进内存里的队列，然后敲一下门铃（一个叫 doorbell 的寄存器），剩下的归固件管。咱们看固件这边：从队列里取命令、调度到各个队列组和 shader 核心、驱动硬件执行，完了再通过共享内存和中断把结果报回来。

所以咱们得心里有底：对 CSF 时代的 GPU 来说，固件是 GPU 能开始工作的前提——**没有固件，GPU 就是一块不应答的硅**。

咱们把架构分界落到主线驱动的选型上，看到的就是 Panfrost 和 Panthor 的分界：

- **Panfrost**：老一代（Utgard/Midgard/Bifrost，G31/G52/G76 这些）的主线驱动，直接写硬件，不需要固件。
- **Panthor**：CSF 时代（v9 及以后）的主线驱动，probe 的第一步就是加载固件，之后所有工作都通过固件间接完成。

Mali-G610 是第十代的 Valhall（架构号 arch 10.8），咱们一眼就能看出，它早越过了 Panfrost 的射程。所以 [kernel.config](../../../boards/rk3588-topeet/kernel.config) 里那行注释写得毫不客气：`NOT Panfrost (G31/G52/G76 only). Panthor is the mainline driver for v9+ Mali`。咱们不能指望像 RK3568 那样开个 Panfrost 就完事，这颗 GPU 有自己的一套要求等着咱们满足。

### 三层栈：各管什么

咱们把整个 GPU 软件栈分成三层来看，每层第一次露面时表格里都配了句白话：

| 层 | 组件 | 管什么 | 开源吗 |
|---|---|---|---|
| 内核态 | `drm/panthor` | 加载固件、管 GPU 的内存映射和电源、暴露 `/dev/dri/renderD128` 和一串 ioctl | 开源（主线自带） |
| 用户态 | Mesa | 把 OpenGL ES / Vulkan 的调用翻译成 GPU 命令流，经 ioctl 提交给内核 | 开源（Ubuntu 仓里有） |
| 固件 | `mali_csffw.bin` | 在 GPU 的 MCU 上跑，接命令、排调度、真正驱动硬件 | **闭源固件 blob**（Arm 发布，收进 linux-firmware） |

咱们画一遍完整的调用，三层的接力就看清了：

```
应用程序   glDrawArrays(...)
              │
Mesa        把调用翻译成命令流，写进队列内存
              │ ioctl（有活来了）
内核        验证权限、管理缓冲、敲 doorbell 寄存器
              │ doorbell
固件(MCU)   取命令、排调度、分发到队列组和 shader 核心
              │
硬件        shader 核心执行，结果写回共享缓冲
```

咱们一句话把流程串完：应用程序说要画，然后 Mesa 翻译出怎么画，然后内核把画图的活递进去，然后固件定好谁去画的事，最后硬件真的画了。三层里少了任何一层，那链就断了：内核层缺席的话，设备节点就出不来了，Mesa 缺席的话，程序就只能走 CPU 软件渲染了，固件缺席的话，那内核 probe 直接失败（这正是本章的主线剧情）。

咱们对照一下原厂 SDK 那边，细节在 [sdk-diff](../../sdk-diff-rk3588.md) 的 GPU 段。迅为的 5.10 SDK，用的是 Arm 私有的 mali_kbase Bifrost/CSF 驱动开发包（DDK），其实代码就在 `drivers/gpu/arm/bifrost/`，DT compatible 写的是 `arm,mali-bifrost`。主线这边的话，咱们用的是 Panthor，所以从内核驱动到 DT 声明，其实是**两套各自独立的实现**。不过有个事实两边共通：CSF 架构的 GPU 都绕不开那颗闭源固件。

主线换掉了闭源内核驱动，不过闭源固件换不掉。其实这是走主线路线在这颗 GPU 上做成的一笔诚实的交易，换来的是可审计的内核栈和跟 Mesa 同步演进的用户态。代价其实也有，原厂 DDK 的命令流（command-stream）特性和调优，是未必都对得齐的（sdk-diff 的原话）。桌面场景咱们算下来这笔交易划算，极限性能场景那就要另说了。

还有一层配对关系咱们要心里有数：**固件和内核驱动是成对工作的**。CSF 的内核-固件之间有一套版本化的接口协议，成功 log 里 `CSF FW using interface v1.5.0` 的那一行就是协商结果。内核驱动和固件的版本要是错开太多，轻的话能力协商不上，重的话 probe 直接失败。所以 linux-firmware 的版本不宜跟内核版本长期各走各路。咱们把固件内建进内核镜像，正好把这两者的版本绑在了同一次构建里，之后就天生不会错位了。

### 板级 DT：三行供电

DT 这头反而是全章最省事的部分。主线 `rk3588.dtsi` 本来就带着 `gpu@fb000000` 节点（后面 log 里 probe 的就是它），咱们在板级 [dts 补丁 0002](../../../boards/rk3588-topeet/patches/linux/0002-arm64-dts-rk3588-topeet-panel.patch) 里只补了供电：

```dts
&pd_gpu {
	domain-supply = <&vdd_gpu_s0>;
};

&gpu {
	mali-supply = <&vdd_gpu_s0>;
	status = "okay";
};
```

其中 `vdd_gpu_s0` 是 rk806 PMIC 的 dcdc-reg1（550–950 mV），咱们也是在这个补丁里把它定义出来的。

咱们要让 probe 过关，内核得替 GPU 摆平四样东西：**供电**（`mali-supply` 指到 PMIC 的一轨）、**电源域**（`pd_gpu`，RK3588 的 GPU 有独立的上下电域）、**时钟**（dtsi 里声明好的，成功 log 第一行 `clock rate = 198000000` 就是它起来的证据）、**固件**。前两样咱们靠板级 DT 补线就行，第三样主线替咱们备好了，唯独固件这第四样是 DT 管不着的，它是启动链里一个全新的变量，也是本章真正的对手。DT 侧咱们就只写这三行，真正的难关全在后面那颗固件 blob 上。

## 症状：屏幕亮着，桌面黑着

时间回到 LCD 显示那关收官的那天，咱们把镜头切回来。当时显示链已经全通了，boot logo 是出了图的，咱们往 `/dev/fb0` 写噪点，屏上就花了一片，说明 VOP2 到面板的通路是好的。GDM 也起来了，`gnome-shell` 进程是活着的，咱们查到 PID 686。不过桌面黑的，咱们盯着它一动不动。

咱们从 GNOME 那头的 journalctl 里翻出来的，是这样反复刷屏的东西：

```
gnome-shell: Failed to lock front buffer on /dev/dri/card0: gbm_surface_lock_front_buffer failed
gnome-shell: Failed to query buffer age, got error 3003
```

咱们再看设备节点这边：

```
# ls /dev/dri/
card0
```

咱们一看：**只有 card0，renderD128 是没有的**。

这里咱们得解释一下这对节点的分工，它是理解整个症状的钥匙。咱们在上一章讲 KMS 时提过 DRM 这个内核显示框架，它给咱们暴露两类设备节点：`card0` 是**显示节点**，modeset 和扫出这两件事都是它管的，上一章整章打交道的 VOP2、DSI、connector，全是挂在它上面的。咱们看 `renderD128`：它是**渲染节点**，GPU 计算本身是它唯一管的，显示是一概不碰的。咱们把渲染和显示拆成两个节点，是为了让没有桌面权限的程序也能安全地用 GPU 算东西，不用给它控制屏幕的权力。桌面合成器 mutter 是要 GPU 加速的，走的就是渲染节点。渲染节点要是缺了，mutter 就没有 GL/EGL 可用了，`gbm_surface_lock_front_buffer` 那串报错就是它拿不到缓冲时的挣扎。

这一点咱们来解释一下。为什么 boot logo 和 fbcon（内核的文字控制台）是好好的？因为它们根本不走 GPU——fbcon 是 CPU 直接往帧缓冲里写像素的，VOP2 负责后面的扫出，整条路上没有 Mali 什么事。**屏幕亮不亮看的是显示链、桌面动不动看的是 GPU**，两条链其实各自独立，直到后面讲的 dma-buf 才汇合。所以屏上有画面这件事，GPU 正常与否咱们是推不出来的，症状被显示链的胜利盖住了，排查时得有意识地把两件事分开问。

renderD128 为什么没出来？咱们到 dmesg 里找答案，答案是现成的：

```
panthor: *ERROR* Failed to load firmware image 'mali_csffw.bin'
```

Panthor probe 的第一步是 `request_firmware()` 要 `mali_csffw.bin`，咱们看到它拿不到，整个 probe 就地失败，渲染节点自然也就不创建了。

咱们回头盘点一下，这三步取证其实刚好各查一层，顺序也值得咱们在别的板上沿用：第一步咱们拿 `journalctl` 看**用户态**在喊什么疼（它只知道“拿不到缓冲”，不知道为什么），然后拿 `ls /dev/dri/` 看**内核给了什么设备**（缺节点直接把嫌疑指向驱动），最后拿 `dmesg` 看**内核侧的案发现场**（probe 失败的原话就在那里）。遇到桌面黑这样的症状，用户态的报错永远是二手的，根因是越靠底层露馅越早的，所以咱们从上往下剥比从下往上猜快得多。

## 根因：两个问题叠在一起

固件为什么拿不到？咱们排查下来是**两个独立的问题叠着**，单修任何一个都不够的。

**第一个是时机上的问题。** 咱们把 Panthor 配成了 `CONFIG_DRM_PANTHOR=y`（内建）。内建驱动的 probe 发生在内核启动的 initcall 阶段，是很早的一步。有多早？拿 11 月 eMMC 终验的 boot log（[finish/1.txt](../../logs/rk3588/finish/1.txt)）量一下，把同一次启动里跟本章有关的几个事件按时间摆开：

```
0.44 s   VOP2、DSI2 bind 进 display-subsystem     （上一章的显示链就位）
0.90 s   panthor probe：clock rate → Initialized   （固件请求发生在这段内部）
1.06 s   EXT4 挂载，VFS: Mounted root               （rootfs 第一次可见）
1.07 s   Run /sbin/init                             （交权给用户态）
   …     udev、systemd 起服务，各自按需加载
```

咱们把原文时间戳放在下面：

```
[    0.901460] panthor fb000000.gpu: [drm] clock rate = 198000000
...
[    1.062425] EXT4-fs (mmcblk0p3): mounted filesystem ... r/w with ordered data mode.
[    1.062444] VFS: Mounted root (ext4 filesystem) on device 179:3.
```

Panthor 在 0.90 s 就把 probe 跑完了，rootfs 是在 1.06 s 挂载的，咱们算一下：固件请求发生在 probe 内部，比 rootfs 的出现还要早约 160 ms。咱们看：`request_firmware()` 在那个时刻去找 `/usr/lib/firmware/arm/mali/arch10.8/mali_csffw.bin`，这个路径是还不存在的。固件明明是躺在 rootfs 里的，可 early probe（驱动的早期探测）其实就是够不着它。这是所有内建 GPU/VPU 驱动共同的时序处境，probe 在前、文件系统在后的局面下，咱们要喂的固件就卡在两者中间。

**第二个是压缩的问题。** Ubuntu 26.04 的 linux-firmware 包里，固件一律是 `.zst` 的压缩形态：`mali_csffw.bin.zst`。kernel.config 的注释里写着它的打包口径：`ships linux-firmware blobs as .zst ONLY`。而内核那会儿没开 `CONFIG_FW_LOADER_COMPRESS`，固件加载器是不认识压缩固件的。这个缺口不算咱们的过失，咱们得看清楚的是：arm64 的 defconfig 默认就不带压缩固件支持，这是发行版的打包形态和内核默认配置脱节的产物。但板子不管是谁的责任，读不到就是读不到的现实，咱们绕不过去。就算时机问题解决了（比如驱动改成模块、开机后再加载），文件名是对不上的，照样读不了。

两个问题一横一竖：时机挡住了“什么时候读”，压缩挡住了“读什么形态”。所以单把驱动改成模块不够，单开压缩支持也是不够的，咱们得有一个方案同时把这两道跨过去。

## 解法：把固件织进内核镜像

动手前咱们得回答一个问题：这颗固件从哪来。RK 平台的闭源 blob 有两个来源，咱们别搞混。启动链前段那些（DDR init、SPL、OP-TEE）走的是 **rkbin**，Rockchip 的私有发布仓，U-Boot 章折腾的就是它们。GPU 固件不在这个体系里——它是 **Arm 发布、收进 linux-firmware 仓的 `mali_csffw.bin`**，走的是正规发行版渠道，Ubuntu 的 `linux-firmware` 包里就有它（板侧 packages.list 装了这个包，一半是为了 WiFi/BT，咱们顺带也把 GPU 固件带上了）。所以 GPU 这关不需要去 rkbin 翻箱倒柜，rootfs 里是现成就有一颗的，咱们的问题只在于内核早期够不着它。

再比较三条让固件及时就位的路，然后说咱们走的哪条、为什么：

| 路线 | 时机上怎么解 | 代价 | 咱们的处境 |
|---|---|---|---|
| `=m` 模块 + 压缩固件 | udev 在 rootfs 挂载后加载模块，固件伸手可及，开 `FW_LOADER_COMPRESS_ZSTD` 直接读 `.zst` | 构建流程得做 `make modules_install` | forge 不装内核模块，为一个驱动破例不值 |
| initramfs 放固件 | 固件随 initramfs 早于 rootfs 就位 | 得先有 initramfs 这一环 | 这条启动链压根没有 initramfs（U-Boot 章） |
| `CONFIG_EXTRA_FIRMWARE` 内建 | 固件编进内核镜像，probe 时已在内存 | 镜像胖 282 KB | 几行配置，一次到位——**选了这条** |

咱们选中的路线，机制上是这样子的：编译内核时，把指定的固件文件塞进 `vmlinux` 里一块内置固件区，内核起来后这些固件已经躺在内存里了。`request_firmware()` 的查找顺序是内置区在前、文件系统在后，所以 early probe 一样拿得到，时机问题就整个消失了。

而塞进内核的是解压后的原始字节，`.zst` 那道也顺带绕开了，咱们一步就把两道全过了。

咱们拆成具体的四步来做：

1. **取货**。从 staged rootfs（linux-firmware 包）里拿 `arch10.10/mali_csffw.bin.zst`，解压成 raw，282 KB：

```sh
# 从 staged rootfs 的 /usr/lib/firmware 里取
zstd -d arch10.10/mali_csffw.bin.zst -o mali_csffw.bin
ls -l mali_csffw.bin      # 282 KB
```

2. **摆位**。放到 `boards/rk3588-topeet/firmware/arm/mali/arch10.8/mali_csffw.bin`。这个路径不是随便挑的：Panthor 驱动按 GPU 的架构号声明它要的固件（`panthor_fw.c` 里 `MODULE_FIRMWARE("arm/mali/arch10.8/mali_csffw.bin")`），G610 是 arch 10.8，请求路径就是 `arm/mali/arch10.8/`。而 linux-firmware 仓把这个 blob 归档在 `arch10.10/` 目录下——同一个 blob，要按**驱动要的路径**摆，不能拿源目录的名字直接用。这一步要是摆错了目录名，probe 时一样报 not found。
3. **配置**。kernel.config 里一行：

```
CONFIG_EXTRA_FIRMWARE="arm/mali/arch10.8/mali_csffw.bin"
```

   只有相对的固件名写死在 fragment 里。`CONFIG_EXTRA_FIRMWARE_DIR` 由构建器（`src/forge/build/linux.py` 的 `_inject_firmware_dir`）在构建时从板目录解析注入，不含任何机器相关的绝对路径——这是后来可移植化的定型形态，notes/48 最初版本里那个 `/home/...` 硬编码已经收掉了。咱们还有一道防御：设了 `CONFIG_EXTRA_FIRMWARE` 而板目录下没有 `firmware/` 的话，构建是会直接报错停下来的，不会让咱们编出一个“以为带了固件其实没带”的内核。
4. **验证**。编完内核用一行命令确认固件真的进了镜像：

```sh
$ strings Image | grep mali_csffw
```

   咱们要的是能命中，一旦命中了，就说明固件的登记信息进了内核镜像（notes/48 里就是这么验的）。这一步别省——`CONFIG_EXTRA_FIRMWARE` 的值拼错一个字符、或固件文件没摆到 `EXTRA_FIRMWARE_DIR` 指的目录，内核编译时是会报错停下来的。咱们做 strings 这一眼，为的是把“编进去了”的事变成板上事实，这是最后一道便宜的检查。

这儿有个后续值得一提的，咱们交代一下：那阵子 WiFi bringup（板子点亮初调，外设章的故事）遇到的是同一个压缩问题，rtw88 从 rootfs 读 `.zst` 固件是失败的，于是 `CONFIG_FW_LOADER_COMPRESS` + `CONFIG_FW_LOADER_COMPRESS_ZSTD` 后来还是打开了。

不过两套机制的分工没有变：**GPU 固件靠内建**，解的是 early probe 的时机问题，**WiFi/BT 固件靠的是压缩加载**，因为它们本来就是 rootfs 挂好之后才 probe 的，时机是天生安全的。同一个 kernel.config 里两套是并存的，各管各的时机，咱们读配置时别把这两行想成互相替代的。

咱们可以把这个经验一般化，以后碰到任何 early probe 的固件型驱动（GPU、VPU 都算）都适用：固件要么内建进内核（`CONFIG_EXTRA_FIRMWARE`），要么随 initramfs 早于驱动就位，要么把驱动改成模块让它晚点来——**放在 rootfs 里指望 early probe 去拿，是三条路里唯一走不通的**。

咱们排查任何“firmware not found”的时候，得问驱动什么时候 probe、那时固件在不在它看得见的地方，形态是不是压缩是紧跟着的第二个问题。

## 成功长这样

固件内建进内核、重新打包烧录（那次的里程碑镜像 `update.img` MD5 前 8 位 `95da441d`），咱们把板再启一次，dmesg 里就有了这段，log 咱们截自 [202608011826](../../logs/rk3588/202608011826.txt)，一个字咱们都没有合成：

```
[    2.931388] panthor fb000000.gpu: [drm] clock rate = 198000000
[    2.938749] panthor fb000000.gpu: EM: created perf domain
[    2.945384] panthor fb000000.gpu: [drm] Mali-G610 id 0xa867 major 0x0 minor 0x0 status 0x5
[    2.954622] panthor fb000000.gpu: [drm] Features: L2:0x7120306 Tiler:0x809 Mem:0x301 MMU:0x2830 AS:0xff
[    2.965129] panthor fb000000.gpu: [drm] shader_present=0x50005 l2_present=0x1 tiler_present=0x1
[    2.985663] panthor fb000000.gpu: [drm] Firmware protected mode entry is not supported, ignoring
[    2.995611] panthor fb000000.gpu: [drm] Firmware git sha: 95a25d71030715381f33105394285e1dcc860a65
[    3.005932] panthor fb000000.gpu: [drm] CSF FW using interface v1.5.0, Features 0x0 Instrumentation features 0x71
[    3.017850] panthor fb000000.gpu: [drm] Using Transparent Hugepage
[    3.025289] [drm] Initialized panthor 1.8.0 for fb000000.gpu on minor 1
```

咱们逐行读一遍，每行都是有信息量的：

- `clock rate = 198000000`：GPU 时钟起来了，供电链（板级 DT 那三行）生效。
- `EM: created perf domain`：GPU 的功耗模型（Energy Model）建好了，调度器据此知道这颗 GPU 什么负载费多少电，供任务摆放决策用。
- `Mali-G610 id 0xa867`：GPU 核心被认出来了，ID 寄存器读到了。这一行只有固件跑起来、MCU 开始应答之后才可能打印——空白的 MCU 不回话，probe 早就死在前一步了。
- `Features:` 和 `shader_present=0x50005`：固件报告了这颗 GPU 的家底——哪些 shader 核心在位（0x50005 这张位图）、L2/tiler/MMU 的配置如何。这些是 MCU 上电自查的结果，同样是有固件才有的输出。
- `Firmware protected mode entry is not supported, ignoring`：固件上报了自己支持的安全特性清单，protected mode 这项这颗实现没有，内核记一句继续走。固件还掌管一部分安全机制，这行就是证据。
- `Firmware git sha: 95a25d71…`：内核把固件的版本指纹打出来了。282 KB 的闭源 blob 也有版本可查，将来对不上问题时，这行就是核对固件版本的凭据。
- `CSF FW using interface v1.5.0`：内核驱动和固件协商出了命令流接口版本。CSF 时代内核与固件之间有一套版本化的共享内存协议，这行说明两边对上了话。
- `Using Transparent Hugepage`：内核给 GPU 的内存映射启用了透明大页，GPU 一次映射一大片，省 MMU 的 TLB 条目，算内核侧给 GPU 的一点顺手优化。
- `Initialized panthor 1.8.0 ... on minor 1`：probe 完成，DRM 设备注册，渲染节点随之创建。

再往后咱们在同一份 log 里还能看到：

```
Starting gdm.service - GNOME Display Manager...
[  OK  ] Started gdm.service - GNOME Display Manager.
```

GDM 起来了，gnome-shell 在渲染节点上是拿到 EGL 的，GNOME 桌面亮在上一章那块 1024×600 的屏上。验收三件事齐了：probe log、`/dev/dri/renderD128` 出现、桌面显示。后来上一章讲 VOP2 硬锁（hard lockup）排查的时候，GPU 还被咱们当成无辜嫌疑人单独验过一次。那是一个 surfaceless EGL 的 GLES 3.1 shader 读回测试（`egl-readback`，见上一章的排查表），咱们看到它在板上 PASS。这个测试的做法是不开窗口、直接渲染到离屏缓冲，然后把读回 CPU 的像素跟期望值比对，它证明的是比“桌面在动”硬得多的东西：GPU 确实执行了那段 shader，输出的每个像素都验过。

咱们把上面的验收浓缩成可以在任何一块 Panthor 板上重放的清单：三条命令加一条人工检查，咱们从内核到桌面各查一层：

```sh
dmesg | grep panthor        # 内核层：probe 成功、固件版本、GPU 家底
ls /dev/dri/                # 设备层：card0 之外要有 renderD128
journalctl -b -u gdm        # 服务层：GDM 起来后没有 GBM/EGL 报错刷屏
# 桌面层：登录进 GNOME，动一动窗口——合成流畅、无花屏
```

这套配置也经受住了后面的折腾。8 月中的多次重启验证、11 月 eMMC 终验的 24 补丁正式镜像（`7.1.0-00024-ga7dad2806329`），固件内建一次配好之后就没再要人管了，咱们在终验 log（[finish/1.txt](../../logs/rk3588/finish/1.txt)）里看到同一个 panthor 段落原样复现，固件的 git sha 还是 `95a25d71…`。固件是跟着内核镜像走的，内核升版了它也跟着走，这正是内建方案在维护性上的回报：不存在“内核新了固件没跟上”的错位。

## 从 renderD128 到桌面：GPU 与显示怎么接

固件这关过了，咱们退一步，把整条渲染到显示的通路串起来，这正是本章开头说的、跟上一章的接缝。

**用户态这一层咱们从认节点说起。** mutter（GNOME 的 Wayland 合成器，负责把所有窗口合成到屏幕上的那个进程）通过 Mesa 使用 GPU。Mesa 是开源的 OpenGL/Vulkan 实现，也就是把画图 API 翻译成 GPU 命令的那一层。Ubuntu 26.04 仓库里的 Mesa 已带 Panthor 支持，板侧 [packages.list](../../../boards/rk3588-topeet/ubuntu/packages.list) 装的是 `mesa-utils` + `libgl1-mesa-dri`，咱们这一路**不需要任何闭源用户态库**，这在原厂 SDK 上是不可想象的，那边用户态同样吊在 Arm 的闭源 blob 上。桌面那一侧的话，`ubuntu-desktop` 咱们装上，就把 `gdm3`、`gnome-shell`、`mutter`、`wayland` 全都拉了进来。而且这一层没有任何配置文件要写：Mesa 装上就认渲染节点，包列表之外是没有 mesa 配置物料的，这是开源栈装上即用的福利。

**然后是一帧的旅程。** 咱们看 mutter 每帧大致走这样一条流水线（Wayland 会话下走的是 GBM 的路子）：

```
mutter（合成器）
   │ EGL/GBM：在 renderD128 上拿一块离屏缓冲
   ▼
Mali-G610 把各窗口内容合成进这块缓冲          ← 本章的地盘
   │ dma-buf：同一块内存换个身份，零拷贝
   ▼
VOP2 plane 扫出 → DSI2 → TC358775 → 面板      ← 上一章的地盘
```

第一步走 EGL（OpenGL 和窗口系统之间的桥）初始化 GL 上下文，然后走 GBM（用户态在 DRM 设备上分配图形缓冲的接口）在渲染节点上拿到几块离屏缓冲，咱们轮流用。每一帧的活儿是这样的：GPU 把所有窗口的内容合成进当前缓冲，然后 mutter 走 KMS 的 atomic 接口，把这块缓冲提交给 VOP2 的 plane 扫出，提交完缓冲就归 GPU 复用了，周而复始。症状开头咱们在 journalctl 里看到的 `gbm_surface_lock_front_buffer` 报错，正是流水线上取缓冲的那一步，渲染节点不在的情况下，整条流水线的第一站就断了。

**交接靠的是 dma-buf。** dma-buf 是内核里跨设备共享缓冲的机制：一块内存同时被 GPU（当渲染目标）和显示控制器（当扫描源）映射，GPU 画完了直接扫，这是一条**零拷贝**的通路，像素是从 GPU 出来直接进面板的，全程不落回 CPU 的手里。上一章的 KMS 链（CRTC、encoder、connector），咱们看到它在另一端把扫出接了手。两条链到这儿就汇合了，这也是本章和上一章的分界线：上一章管的是缓冲怎么上屏，本章管的是缓冲里的像素从哪来。

交接里还藏着一个容易忽视的要点：**同步**。GPU 渲染是异步的，mutter 把一帧画图的提交交出去，函数返回时 GPU 多半是还没画完的。那 mutter 怎么知道一块缓冲可以复用了？靠的是内核里的 fence（围栏，内核实现叫 dma_fence/drm_syncobj）：提交渲染的时候附一个 fence，GPU 画完了内核把它标记为完成，谁想复用这块缓冲就得等它的 fence 标记完成。不等 fence 就复用的话，CPU 或 GPU 一边写一边读的是同一块内存，这就是所谓的数据竞争，屏上出了花屏还查不出报错。这类机制日常是被 Mesa 和 mutter 包办的，咱们一行代码都不用写，不过这一层咱们排查显示异常时得知道，提交完和渲染完中间是隔着一个 fence 的。

这个接口上还有一处容易栽的细节，上一章已经遇到过并修好了，咱们这里从 GPU 侧看一眼。缓冲交接之前两边得对上格式×布局的暗号：扫描侧通过内核广播一张 IN_FORMATS 表，声明自己支持哪些像素格式配哪些内存布局（比如线性、压缩 tiled 这样的 modifier），渲染侧是照表选的，选了表外的组合，present 就失败了。

上一章的 [补丁 0020](../../../boards/rk3588-topeet/patches/linux/0020-drm-rockchip-vop2-advertise-linear-modifier-on-rk3588-cluster-windows.patch) 补登了漏掉的 LINEAR 布局，[补丁 0021](../../../boards/rk3588-topeet/patches/linux/0021-drm-rockchip-vop2-drop-afbc-only-10bpc-formats-from-rk3588-cluster-windows.patch) 摘掉了混登的两个只支持 AFBC 压缩组合的 10bpc 格式，修的就是上面说的格式广播表。mutter 信了广播，选中了混登的 10bpc 格式，每条 present 路径都是失败的，桌面就永远亮不了。**广播的能力错了，照着广播办事的客户端是无辜的**，这类问题的阴险之处在于内核一句报错都没有，咱们全靠读代码对表才发现。它同时提醒咱们：GPU 这关过了不等于桌面能亮，交接处的协商机制一样能卡死人。

还有一桩 Mesa 的命名陷阱，咱们提前说一下，省得查资料时绕晕：内核侧的驱动叫 **Panthor**，但 Mesa 侧覆盖 CSF 硬件的 Gallium 驱动，族谱名字仍叫 **panfrost** 的原因，是这个 Mesa 驱动既对接老的 Panfrost 内核驱动，也对接的是新的 Panthor 内核驱动。所以用户态工具报的 renderer 字符串里出现“Panfrost”字样（模拟器研究线里实测报的是 `Mali-G610 MC4 (Panfrost)`），咱们别慌，Mesa 的家谱就是这么排的，不代表内核驱动选错了。

## 本章的误判清单

这一章和它牵着的上一章，一路上中过的招，咱们归拢成一张表，以后带别的板过 GPU 这关时逐条对一遍，这比重新踩一遍要便宜多了：

| 看到的 | 直觉说 | 真相是 |
|---|---|---|
| 屏上有 boot logo、fbcon 有字 | 显示正常，GPU 应该也没问题 | fbcon 是 CPU 直写帧缓冲，不走 GPU，两条链独立到 dma-buf 才汇合 |
| gnome-shell 进程活着（PID 都查得到） | 桌面在跑，快亮了 | 没有 renderD128 就没有 EGL，进程可以活着，桌面照样黑 |
| rootfs 里明明有 mali_csffw.bin.zst | 固件在，驱动自己会找到 | early probe 时 rootfs 还没挂，而且 `.zst` 要开 `FW_LOADER_COMPRESS_ZSTD` 才认 |
| dmesg 报 `Failed to load firmware image` | 固件没装，得去找固件 | 固件大概率就在 rootfs 里，先查时机（probe 早于挂载吗）再查形态（raw 还是 .zst），最后才怀疑缺失 |
| 固件文件从 linux-firmware 拷过来了 | 照源目录 arch10.10 摆就行 | 驱动按架构号要 `arm/mali/arch10.8/`，得按 `MODULE_FIRMWARE` 声明的路径摆 |
| dmesg 里 `Initialized panthor`，probe 全绿 | 桌面必然亮 | 扫出侧的格式×modifier 广播错了照样黑屏（上一章补丁 0020/0021 的故事） |
| 用户态报 renderer "…(Panfrost)" | 内核驱动选错了 | Mesa 的驱动族谱就叫 panfrost，它同时对接 Panfrost 和 Panthor 两个内核驱动 |

表里的前五条是本章的主角，第六条是上一章替咱们交的学费，第七条是查资料时的名字混淆。每一条的直觉都挺合理，真相都要咱们跨一层才看得到。

## 旁线：模拟器上的 CSF 研究线

章末交代一条平行的研究线，它不在真板移植的主线上，但产出了对 CSF 机制的理解材料。8 月底到 9 月咱们在 QEMU 里搭了一台 RK3588 lite 模拟机（`boards/rk3588-topeet/sim/`），专门研究 Panthor 和 CSF 固件的交互协议：咱们让 QEMU 机器兼任 BL31（应答 SCMI 时钟和 SMCCC 调用）、再给 GPU 造一片寄存器的影子，然后用一个假 MCU 复刻固件上电后会做的初始化动作。研究线一路打到了两个里程碑，渲染节点在模拟机里出现了（[notes/82](../../notes/82-2026-08-31-panthor-m0-scmi-agent.md)），Mesa 用户态全链也跑通了（[notes/83](../../notes/83-2026-09-02-panthor-m1-campaign.md)），中途还把命令队列组建立、寄存器窗口分配这些协议细节逐个啃了下去。

研究线的价值在于把闭源固件的行为逼到了明处。比如固件镜像里那段 64 KB 的共享内存区，文件里只有 124 字节的初值，其余全是 MCU 上电后自己填的，真板上这些动作是闭源固件一手包办的，咱们只看得到结果，模拟器里造假 MCU 的时候，咱们每写一个字段都得知道真固件会写什么，这等于咱们被迫逐字节搞懂了启动协议。咱们攒下的理解反过来撑着本章的每一句话：固件是什么、它什么时候就位，咱们说起来都有底气。

边界也要说死：仿真证明的是软件控制流和协议交互，证明不了时钟、电源、DDR 时序这些硬件行为，所以研究线交出的判断，咱们在仓库里都标注“仿真取证”，真板主线（就是本章这颗内建固件）才是验收的依据。咱们给两条线各定一个位置，主线负责的是验收，研究线负责的是理解材料。研究线的这些成果，后来整理成了教学侧的 GPU 选修材料（[planning/gpu.md](../../planning/rk3588/gpu.md)），咱们本章不展开它的战役过程。

## 收官

咱们盘点这一关实际改动的东西，清单是短得出奇的：

- **内核驱动补丁：零张。** 24 张正式补丁里没有一张是给 GPU 驱动写的——Panthor 是主线自带的，驱动代码一行没改。
- **板级 DT：三行供电**，搭在 dts 补丁 0002 里（跟 PMIC、显示那些各占一角）。
- **kernel.config：两处**。`CONFIG_DRM_PANTHOR=y` 开驱动，`CONFIG_EXTRA_FIRMWARE` 内建固件（后来的 `FW_LOADER_COMPRESS*` 是 WiFi 那关的，不算本章）。
- **新增物料：一个文件**。282 KB 的 `mali_csffw.bin`，从 linux-firmware 解压摆位。
- **rootfs 侧：三个包**。`mesa-utils`、`libgl1-mesa-dri`、`ubuntu-desktop`，全走 apt，没有一行闭源用户态。

这大概是走主线路线在 RK3588 上最划算的一次收获：全章唯一的难点落在理解上，一个架构变化（CSF）带来的时序约束，咱们必须让固件早于 early probe 就位。咱们理解到位之后，解法就只是几行配置的事。咱们验下来，GNOME 桌面是有 GPU 加速的，egl-readback 也验过了渲染，dma-buf 那头接的是上一章修好的 VOP2 扫出链。下一章（[rootfs 章](05_rootfs.md)）讲 rootfs：这套 Ubuntu 桌面是怎么从 ubuntu-base 一步步装出来的，Mesa 和固件这些物料是怎么进镜像的，整块 rootfs 又是怎么打包进 eMMC 的。
