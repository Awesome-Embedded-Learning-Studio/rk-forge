# Ch0 — forge：把整条构建链收成一个命令

> 前面四卷的活，咱们从 boot 到 sd-boot 都手敲过一遍了。这一卷干的是收尾的活：咱们把那些手敲的步骤收进一个叫 `forge` 的编排器（管步骤顺序与依赖的一道总控），让一条命令替咱们把顺序跑对，把没变的步骤也跳过。它在目录上挂在 RK3506B 教程的后面，讲的却是三块板共用的基建，aes、rk3568-atk、rk3588-topeet 走的都是同一个 forge，所以这一章也是全书的共享章。

## 前言：为什么需要编排器

跟着前面四卷走一遍就清楚了，从源码到一块能烧的 `update.img`，咱们要从拉源、编内核一路做到组装镜像，中间十来步的前后依赖断不得，顺序错一步产物就不全了。这样的活手敲两遍的话，咱们就想把它自动化。自动化的心思从 imx-forge 时代就带过来了，那边是咱们更早弄 i.MX 板子的构建项目。

原厂那套 `build.sh` 倒是有编排的，毛病就是每次的全量重编，咱们改一个板级 DT 的话，内核就得从头再编一遍了。所以 forge 一开始要解的，是让整条链的依赖顺序自动跑对，外加只重跑输入真正变了的步骤。后来 rk-forge 从一块板扩到了三块板，编排器肩上的活又多了一件，板与板的差异得收进配置文件里，而不是散落在脚本里的 if 分支，这件事咱们留到板配置的章节去讲。

## forge 现在住在哪：src/forge 的 Python 包

今天的 forge 已经不是脚本了，它是 [src/forge](../../../src/forge/) 下的一个 Python 包，命令的入口在 [cli.py](../../../src/forge/cli.py)。包里的分工，咱们照位置一层一层看：

| 位置 | 管什么 | 代表文件 |
|---|---|---|
| `cli.py` | 命令树与参数解析，子命令按 `_cmd_*` 方法分发 | [cli.py](../../../src/forge/cli.py) |
| `config/` | 配置加载，`Board` 读板配置、`Project` 读项目配置 | [board.py](../../../src/forge/config/board.py)、[project.py](../../../src/forge/config/project.py) |
| `core/` | 编排的地基，DAG、内容指纹、子进程、日志、防护 | [dag.py](../../../src/forge/core/dag.py)、[stage.py](../../../src/forge/core/stage.py)、[proc.py](../../../src/forge/core/proc.py) |
| `build/` | 各构建器，内核、U-Boot、三种 rootfs、initramfs | [linux.py](../../../src/forge/build/linux.py)、[uboot.py](../../../src/forge/build/uboot.py)、[rootfs.py](../../../src/forge/build/rootfs.py) |
| `pack/` | 各打包器，loader、FIT、UBIFS、ext4、组装 | [fit.py](../../../src/forge/pack/fit.py)、[assemble.py](../../../src/forge/pack/assemble.py) |
| `fetch/` | 拉源，pin 住的源码树与 WiFi 驱动 drop | [deps.py](../../../src/forge/fetch/deps.py)、[driver.py](../../../src/forge/fetch/driver.py) |
| `tools/` | 两个纯 Python 打包器，替原厂的闭源工具 | [fit_pack.py](../../../src/forge/tools/fit_pack.py)、[rkfw_pack.py](../../../src/forge/tools/rkfw_pack.py) |

调用它的时候咱们不需要装任何东西，`python3 src/forge/cli.py ...` 的形式直接就能跑，cli.py 的文档串把原因写得很直白：

```
Invoked either as an installed console script (``forge ...``) or directly by
path (``python3 src/forge/cli.py ...``); the latter needs no ``pip install``
because the path self-fix below puts ``src/`` on ``sys.path``.
```

图省事的话，走 `pip install -e .` 的路子也能装出 `forge` 命令，[pyproject.toml](../../../pyproject.toml) 里写的入口是 `forge = forge.cli:main`。后面的咱们统一用 `forge` 指代两种调法。子命令的总数是十五个，四段的主干之外，`doctor` 管环境体检、`fetch` 单独拉源、`status` 看指纹状态这些咱们用到再讲，`forge --help` 自己会列全的。

## 四段主干：setup → build → pack → assemble

编排的心脏是 [core/dag.py](../../../src/forge/core/dag.py) 里的 `Orchestrator` 类，它照着一张 DAG（步骤与依赖画成的有向无环图）替咱们调度整条链，模块的文档串把身世交代得很老实：

```
Orchestrator — the forge build DAG (replaces scripts/forge.sh).

Composes the leaf builders/packers (in-process — no ``cli.py`` subprocess) in the
right order, each behind :class:`forge.core.stage.Stage` content-hash skipping
(unless ``--force``/``--no-skip``). This is ``forge.sh``'s ``stage_setup /
stage_build / stage_pack / stage_pack_sd / stage_assemble / stage_status /
stage_clean`` + the ``all`` sequence, ported faithfully — same stage order, same
fingerprint inputs (so skip behaviour is byte-identical to the bash ``run_stage``).
```

`forge all` 干的就是四段的依次调用，`all()` 的身子一共五行，咱们一行不动地摆出来：

```python
def all(self, variant: str = "provision") -> None:
    self.setup()
    self.build()
    self.pack()
    self.assemble(variant)
    self.log.ok(f"all done → {self.out_dir}/update.img")
```

### setup：拉源与补丁

setup 阶段干的活，顺序是定的：要初始化 rkbin 的 submodule，要按板拉 pin 住的源码树，咱们还要把补丁序列应用进各源码树。拉的清单随 profile 分叉（profile 就是 rootfs 的路线，咱们用 `--rootfs` 旗标来选），buildroot 走的是 linux、uboot、buildroot 加 WiFi 驱动，openwrt 的清单换成 linux、uboot、openwrt 三样，ubuntu 的话只拉 linux 和 uboot 两样，它的 rootfs 来自 ubuntu-base 加 apt 的路线，就用不着 buildroot 了。

补丁的应用带了一道内容指纹的保险：序列文件、每一发的补丁、连同 pin 住的基点一起算出一个摘要，摘要没变的话就整段跳过。这道指纹是咱们在 2026 年 8 月 15 日的事故里换来的，那天 series 从 0011 长到了 0017，旧的判据只看 HEAD 有没有过基点，HEAD 没动的话，新补丁就被静默跳过了，咱们差点发出一份缺了 0013 到 0017 的镜像。现在的判据在 dag.py 的 `_apply_series` 文档串里写着：摘要对上之外，还要核对树确实过了基点，把指纹还在、树却被重拉干净的场合也一并兜住了。

### build：三个 profile 的编译

build 阶段是按 profile 选构建器的。buildroot 路线要编的件是内核、U-Boot 和 rootfs，其中的 rootfs 就由 buildroot 自己出。openwrt 的话，内核和 rootfs 都交给 OpenWrt 自己编了，咱们只补 U-Boot，为的是保住 kmod 的 vermagic 匹配（内核模块的版本指纹，对不上号的模块进不了内核），完整的论证在 [OpenWrt 卷](../openwrt/00_openwrt.md)里。ubuntu 的 rootfs 不靠编，走的是 ubuntu-base 加 apt 的 chroot 路线，细节归 [RK3588 卷的 rootfs 章](../rk3588/05_rootfs.md)讲。dag.py 的文档串把分叉一句话说完了：

```
Profile-driven (``rootfs_profile``): buildroot (default) / openwrt / ubuntu select
which build + stage + pack chain runs.
```

选的分叉落在 build、pack 两段，外加中间置备 rootfs 那一步的链上，咱们往下接着讲 pack。

### pack：随存储介质分叉

pack 阶段咱们要干的第一步是打 loader、置备 rootfs 树，然后按板的存储分叉，dag.py 文档串的原话：

```
Storage-driven (``board.storage_kind``): nand (ubifs + provisioning initramfs + full FIT set)
vs emmc/sd (ext4 + single no-ramdisk boot.img).
```

翻过来的意思其实就是 NAND 与 eMMC 两种形态。咱们落到 stage 清单上看（stage 就是链上带指纹的步骤单位），aes 这块 NAND 板要多出 `pack-ubifs`、`build-initramfs` 的两步，FIT 要打的是全集。rk3568-atk 与 rk3588-topeet 这两块 eMMC 板走的是 `pack-emmc`，FIT 只打一枚不带 ramdisk 的 `boot.img` 就够了。SD 启动是 aes 的第二条路，`pack-sd` 复用 NAND 的产物，再补 SD 专属的 U-Boot 变体与 FIT，完整的经过记在 [sd-boot 卷](../sd-boot/00_roadmap.md)里。

### assemble：组装 update.img

assemble 组装的是 RKFW 格式的 `update.img`，原料就是 pack 的产物，变体的清单有 provision、nand、rescue 的三种，外加 sd 和 emmc 的两种，默认的 provision 就是首启置备。eMMC 的板在这里会被自动路由到 assemble-emmc，咱们不用记。组装完之后还有一道往返的自检，`--no-verify` 的开关可以跳过它，不过咱们建议留着它。

## content-hash stage-skip：改了什么才重跑什么

这一手是咱们对付原厂 `build.sh` 全量重编的核心改进，完整的实现住在 [core/stage.py](../../../src/forge/core/stage.py) 里，文档串开头一句写的就是机制本身：

```
a stage reruns only when its INPUTS (sources + config + patches + DT) change,
not merely when an output artifact is absent
```

咱们翻个说法：stage 重不重跑看的是输入的变化，产物在不在反而是次要的。

指纹的算法其实没什么神秘，咱们一行行看：第一行是 stage 名、架构、工具链前缀拼的头部，换一套架构的话全部失效，再往后的每个输入按序归一化，目录用 `find` 抽出构建相关文件的路径、大小、修改时间，单个的文件用 `stat` 取一行，咱们把它们拼起来过一遍 sha1 就完事了。指纹文件落在 `out/<板>/.forge-stage/` 的目录里，下次一致的话就跳过。

有个移植的细节：Python 版特意沿用 `find` 和 `stat` 两个外部工具的做法来归一化输入，而不是用 Python 自己的 `os.stat` 重写，连目录输入用浮点时间、文件输入用整数时间的习惯都原样保留了。这么干其实就为一个理由：指纹与 bash 版逐字节一致，老用户升级的那天，已有的跳过状态直接就能用。结果就是咱们熟悉的开发循环：咱们改一个板级 DT，重跑的只有 `pack-fit` 和它下游的 `assemble` 两步，内核的编译纹丝不动。要强制重跑的话，`--force` 管单步的重跑，`--no-skip` 的话全部无条件跑，`forge status` 列出每个 stage 的指纹在不在。

stage 的输入清单里还有一类容易漏的东西。仓库根的 `user/` 目录下的 drop-in（WiFi 凭据、公钥、DNS 这些）会烤进置备好的 rootfs 树，它们必须进 stage-rootfs 的指纹，漏了的话，咱们会话中途改一次凭据，下一次的构建就还在用旧树。这也是 2026 年 8 月 15 日在板上抓出来的：`wifi.yaml` 已经带着真实的 SSID 了，镜像里烤的却是一开始猜的那个。

## 板配置：board.yaml 怎么被消费，三块板怎么共存

加一块板的触点只有一个：`boards/<id>/` 的目录。板的全部声明都在 [board.yaml](../../../boards/aes/board.yaml) 里，从身份、内核、U-Boot、存储到 rkbin 的 blob 与参数文件，咱们一份 YAML 就说全了。加载的入口是 [config/board.py](../../../src/forge/config/board.py) 的 `Board.from_yaml`，它文档串的第一行就定了性：

```
the single source of truth per board
```

咱们把它读作一板一文件的唯一真相源。

加载的时候不只是读，还有一道显式化的校验。bash 时代有些字段靠 `source` 的顺序和 `:-` 的默认值悄悄生效，丢了的话也不报错，RK3588 那次 SPL 与 BL31 的基址错配，出来的就是这么一场静默的 bootloop。现在的 `rkbin.spl_source`、`uboot.arch_override`、`storage.rootfs_mib` 这些键咱们必须写明白，board.py 文档串给的承诺：

```
a misconfiguration fails at load (in <1 ms), not mid-build
```

配置错的话，咱们在加载的毫秒级就把它拦下了，不会等到构建的半路。

三板共存还有项目级配置 [forge.yaml](../../../forge.yaml) 的一份功劳。板与板共享的上游源（buildroot、两颗 WiFi 驱动的 fork、busybox 的 tarball）在它的 sources 池里只存一份，各板的配置按名字去引用，板自己的源（linux、uboot 的 pin），才写进各自的 `board.yaml`。默认的板、输出的路径、ubuntu profile 的教学登录信息，也都在同一份的 forge.yaml 里。三块板咱们对着看：

| 板 | SoC 与架构 | 存储 | board.yaml 里的代表差异 |
|---|---|---|---|
| [aes](../../../boards/aes/board.yaml) | RK3506B，Cortex-A7，armhf | SPI-NAND，UBIFS 加首启置备 | NAND 的几何写死在 storage 段，WiFi 驱动是 rtl8733bu，SPL 用 rkbin 的 |
| [rk3568-atk](../../../boards/rk3568-atk/board.yaml) | RK3568，Cortex-A55，AArch64 | eMMC，ext4 | 多一份 RKTRUST 的清单（BL31 加 BL32），FIT 的来源是 binman，WiFi 驱动是 rtl8852bs |
| [rk3588-topeet](../../../boards/rk3588-topeet/board.yaml) | RK3588，A76 加 A55，AArch64 | eMMC，ext4 | `spl_source: mainline`，板头注释写明原厂 SPL 配不上新 BL31 会 bootloop，WiFi 走树内 rtw88 的路 |

咱们拿同一份 DAG 的代码读三份 board.yaml，就伺候了三块板，这就是加板等于一个触点的意思。profile 与存储的两个维度是正交的：`--rootfs` 选的是 rootfs 的路线，storage 段决定 pack 的形状，两边是互不牵扯的。

## 从 bash 到 Python：退役与继任

forge 的第一代是 bash 写的：单入口的编排器 `scripts/forge.sh` 有 444 行，每个 stage 都对应一个 `stage_xxx` 形式的函数，配上 `scripts/lib/` 下的 `stage.sh`、`env.sh`、`rkbin.sh` 一摞库脚本，再加 `build-linux.sh`、`pack-loader.sh` 这样的十几个叶子脚本。它如今已退役了，删除它的 commit 是 `cce9f63`。咱们想看旧模样的话，git 的历史里还有：`git show cce9f63^:scripts/forge.sh` 一条命令就能翻出来。它在咱们的演进史里不算失败品，四段的名字、stage 的命名、指纹的格式都是它定的，Python 版是照着它的行为逐字移植的。

退役的原因记在 [architecture.md](../../architecture.md) 的决策记录里，咱们拣最实的说。

头一个是环境变量的渗透。bash 靠 `source` 传配置的路子，一个变量漏了 export 或者被 `:-` 的默认值顶掉，症状要等到构建的半路才冒头，咱们之前看不到一点提示。Python 版的回应在全包只留 `Proc.run` 一个子进程的入口，[core/proc.py](../../../src/forge/core/proc.py) 文档串里的核心不变量：

```
Core invariant (the user's "no environment-variable leakage" rule): the child
env is ALWAYS an explicit dict — a curated host allow-list plus Board/Project-
derived extras. It is NEVER ``os.environ`` wholesale, so a build stage cannot
inherit or leak vars (the bash ``source``-leaked ``SPL_SOURCE``/``ROOTFS_MIB``
class of bug is structurally impossible).
```

咱们给子进程的环境永远拼一份显式的字典：一份白名单（PATH、HOME 这些跑构建必需的）加调用方显式传入的板字段，其余的什么都不继承。bash 靠 `source` 泄出去的那类字段，在这里是结构性不存在的。

板名的硬编码是第二个。咱们翻旧脚本能数出八处写死板名的字面量，多板化之后每一处都成了雷。Python 版的回应是 `Board` 的 dataclass，八处字面量全变成了字段的读取。

第三个是校验的时机。shell 没办法替咱们在加载配置的毫秒级就拦下非法的组合，`--board` 与 `--rootfs` 打架的场合，要等 fetch 跑了一半才死。键这一层的校验已经在加载期做了，前面 board.py 那段说的就是它。组合这一层咱们还没等到，board.py 的文档串自己写着 `rootfs_profiles capability checks land later`，读到这里别把组合拦截当成已经交付的能力。

移植是分两步走的。`4d70e3d`（2026 年 8 月 8 日）落的是地基：配置进 YAML、`lib/env.sh` 桥接旧脚本、七枚叶子脚本头一批迁移（五个 `pack-*` 打包的，加组装的 `assemble-update` 与打补丁的 `apply-series`），同时立了 `tests/golden/` 的黄金网，三块板全量产物的 sha256 存了底，之后咱们每迁一步就跟旧的产物对哈希，保证的是零行为变更。`cce9f63`（2026 年 8 月 11 日）收的尾：剩下的构建叶子全迁完了，整个 `scripts/` 目录也删干净了，板配置也从 `config/boards/` 挪进了 `boards/<id>/board.yaml`。黄金网的存底今天还在，`tests/golden/` 下的三份 sha256 就是移植没走样的实证。

移植后的日子里也修过真 bug，有一轮记在 [notes/58](../../notes/58-2026-08-15-rk3588-wifi-rtl8723du-rtw88-bringup.md)：咱们第一次全程以普通用户跑 `forge all`，暴露了三处毛病。重入 fakeroot（靠 LD_PRELOAD 拦截属主操作、伪装 root 权限的工具）的 exec 会把 forge 进程整个换掉，`all` 在 `pack` 之后的静默结束还返回 0。环境白名单漏了 `FAKEROOTKEY`，mke2fs 报的错误码还逐次浮动。旧用户留下的属主残留让 mke2fs 直接 EACCES。三处修完了之后，普通用户的一键到底才算真的成立。

## 两个纯 Python 打包器：fit_pack.py 与 rkfw_pack.py

编排的活之外，forge 还替咱们干了另一件事，就是把构建链对原厂闭源打包工具的最后依赖切干净了。两个当事的文件如今住在 [src/forge/tools/](../../../src/forge/tools/) 里，以库的身份被 pack 阶段直接 import，不再走子进程的那一层。

[rkfw_pack.py](../../../src/forge/tools/rkfw_pack.py) 替掉的是原厂的 afptool 加 rkImageMaker，产的是 `update.img`。格式是两层套娃的结构：外层的 RKFW（`0x66` 头、loader、RKAF 归档、32 字节的 ASCII MD5），内层的 RKAF（`0x8c` 头、分区表、按 `0x800` 对齐的分区镜像）。逆向的评估记在 [notes/12](../../notes/12-2026-06-17-kill-vendor-sdk-assessment.md) 里。社区那头的参照咱们也拿去交叉核对过，afptool-rs 供的是重实现，rk_image_tool 供的是格式说明，出处都在 rkfw_pack.py 的头注释里。最反直觉的一处是 Rockchip 自家的 CRC32 不是 IEEE 的那个多项式，源码的注释里写着 `poly 0x04c10db7`，跟标准的 `0x04c11db7` 差了一位，咱们最早按 zlib 的算法算，尾部的校验怎么都对不上。

[fit_pack.py](../../../src/forge/tools/fit_pack.py) 替的是原厂的 mkimage `2017.09`，产的是 rkbin SPL 认的那一类 FIT `-E` 镜像。为什么不能用主线的 mkimage、为什么要逐字节复刻原厂的布局，这一场的完整记录咱们放在 [notes/20](../../notes/20-2026-06-19-mkimage-saga-handoff.md) 里。它的文档串给了验证的方式：

```
Proven byte-identical to vendor by `fit-pack.py selftest`
```

selftest 把原厂 `uboot.img` 的三个 blob 抠出来重打一遍，比的是树、哈希、偏移，离线的电脑上就能验。Mode A 伺服的是原厂 SPL 用的 `uboot.img`，Mode B 伺服的是主线 U-Boot bootm 用的 `boot.img`，两种布局的差异在源码的注释里各自标着。布局之外还有一条 SPL 侧的硬约束：根节点的 `/totalsize` 必须等于整个文件的大小，Rockchip 的 SPL 按 `ceil(/totalsize / bl_len) * bl_len` 算加载量（`spl_boot_image.c:293`），写小了，排在文件后半截的 external 数据就落在加载量之外。咱们在板上的验证也过了：Mode A 的 `uboot.img` 过 SPL 启动到了内核，Mode B 的 `boot.img` 过主线 bootm 也起来了。

## 用法实例：三块板各来一段

命令以仓库里的实物为准，咱们一块板给一段。

aes 板是 forge.yaml 里的默认板，咱们手头最短的路径就四条命令：

```bash
forge doctor --board aes                 # 查环境，缺啥会打印 sudo apt 的命令
forge all --board aes                    # 四段一条龙，产物在 out/aes/update.img
forge assemble --board aes --variant sd  # SD 卡的 RKFW 镜像（本板 ROM 只认 RK-tool 卡）
forge all --board aes --rootfs openwrt   # OpenWrt profile 的同一条龙
```

产物落在 out/aes/update.img 的位置，咱们把烧录的路子记在 [QUICK_START](../../../QUICK_START.md) 里，本板 ROM 只认 RK-tool 卡的细节也有完整的交代。

rk3568-atk 那边最近的一次真用 forge 是补丁化的规划：[RK3568 外设章](../rk3568/02_peripherals.md)写的做法是 `forge setup --board=rk3568-atk` 拉一份干净的、带 `.git` 的 `v7.1` 源树，然后把 working-tree 里的板级改动，各自做成 quilt 的补丁进 series。这板眼下的工程债咱们看得清楚，在册的补丁还没齐，第二个人 clone 下来之后就复现不了板上的八个子系统了，所以 setup 的这一步就是还债的起点。

rk3588-topeet 用的是 ubuntu 的 profile，rootfs 章的原话咱们照录：“咱们跑 `forge all --rootfs=ubuntu` 时只有第一次要 sudo”，写全的命令是：

```bash
forge all --board rk3588-topeet --rootfs ubuntu   # 首跑的 chroot 要 sudo，之后全程是普通用户
```

咱们最近的日用节奏更碎，[notes/123](../../notes/123-2026-11-01-rk3588-uboot-rockusb-loader-mode.md) 记了 U-Boot 实验的回合：`forge build uboot --board rk3588-topeet` 编完的产物留在树内，`forge pack fit --board rk3588-topeet` 负责的活是把它取进 out/ 再重包 `boot.img`，验完了再按需跑 `forge assemble --board rk3588-topeet`。咱们在 [notes/117](../../notes/117-2026-10-31-rk3588-nfs-root-direct-link-bringup.md) 那边也用同一个节奏跑着 NFS root 的循环，改树、`forge pack --board rk3588-topeet` 出镜像的循环里，板上跑的永远是同一份内容。单件的重跑不必带上整链，这是 stage 化的直接收益。

## 两个诚实的细节

forge 不假装一切都是可复现的，有两个细节咱们照实交代。

U-Boot 的那侧真能做到字节级：[build/uboot.py](../../../src/forge/build/uboot.py) 把 `SOURCE_DATE_EPOCH` 定在源树 HEAD 的提交日期上，咱们跑两次的二进制逐字一致，fit_pack.py 的默认时间戳也是零，所以 uboot.img 整条链是可复现的。

rootfs 侧的 ext4 其实就做不到。`mke2fs -d` 写进 superblock 的时间是跟跑构建的电脑相关的，跑两次的 sha256 就不同了，但结构、布局、内容是定的，靠的就是固定 UUID 加 hash_seed。板子能不能跑看的是内容，superblock 的时间倒不用看，这不挡咱们的交付，只是咱们不宣称全链的 byte-reproducible。UBIFS 的情况也一样，元数据的时间戳会差，但分区的内容是定的。

## 成功长这样

`forge all --board aes` 跑完的尾巴长下面这样。每一行都出自 dag.py 与 stage.py 里的日志语句，顺序就是 `all()` 的调用序，咱们一行都没合成，取的都是原文，只是把每行的 `[INFO]`、`[ OK ]` 前缀剥了，builder 与 fetch 的中间输出也省了：

```
[setup] init git submodules (third_party/rkbin — boot_merger + blob source)
[setup] fetching (buildroot profile: linux + uboot + buildroot + wifi driver)
[setup] applying linux series (no fingerprint yet)
[setup] applying uboot series (no fingerprint yet)
setup complete (profile=buildroot)
[build] kernel (make is internally incremental)
[build] U-Boot (SOURCE_DATE_EPOCH → byte-reproducible)
[build] rootfs (buildroot + WSL clean PATH)
build complete (profile=buildroot)
pack-loader: running
pack-loader: done
stage-rootfs: done
pack-ubifs: done
build-initramfs: done
pack-fit: done
assemble: done
all done → out/aes/update.img
```

咱们再跑一遍同一命令的话，中间那些 stage 会换成 up-to-date 的跳过行，只有指纹变了的 stage 才重跑。

## 档案与证据：本章的版本指纹

咱们引的每个实件都在下面的表里，你复核的时候对着核：

| 件 | 内容 | 出处 |
|---|---|---|
| forge 包 | `0.1.0`，入口 `forge = forge.cli:main` | [pyproject.toml](../../../pyproject.toml) |
| 命令树 | 十五个子命令，`_register_*` 逐个挂上 | [cli.py](../../../src/forge/cli.py) |
| 编排器 | 四段的主干与 stage 的清单，profile 与存储的双分叉 | [core/dag.py](../../../src/forge/core/dag.py) |
| 内容指纹 | sha1 的头部加逐输入的归一化，与 bash 版逐字节一致 | [core/stage.py](../../../src/forge/core/stage.py) |
| 子进程纪律 | 显式的环境字典，白名单加显式传入 | [core/proc.py](../../../src/forge/core/proc.py) |
| 板配置 | 三份 board.yaml，加载期的显式化校验 | [aes](../../../boards/aes/board.yaml)、[rk3568-atk](../../../boards/rk3568-atk/board.yaml)、[rk3588-topeet](../../../boards/rk3588-topeet/board.yaml) |
| 项目配置 | 默认的板、共享的源池、ubuntu 的登录默认 | [forge.yaml](../../../forge.yaml) |
| 黄金网 | 三板产物的 sha256 存底 | `tests/golden/` |
| 地基 commit | `4d70e3d`，配置进 YAML、七枚叶子与黄金网（2026 年 8 月 8 日） | git 历史 |
| 退役 commit | `cce9f63`，scripts 的整批删除（2026 年 8 月 11 日） | git 历史 |
| 移植决策 | 目录、配置、迁移顺序的完整记录 | [architecture.md](../../architecture.md) |
| 打包器逆向 | 去 SDK 的评估、mkimage 的长记录 | [notes/12](../../notes/12-2026-06-17-kill-vendor-sdk-assessment.md)、[notes/20](../../notes/20-2026-06-19-mkimage-saga-handoff.md) |
| 移植后修 bug | 普通用户全链的三修 | [notes/58](../../notes/58-2026-08-15-rk3588-wifi-rtl8723du-rtw88-bringup.md) |
| 日用的实例 | pack fit 与 assemble 的碎节奏 | [notes/117](../../notes/117-2026-10-31-rk3588-nfs-root-direct-link-bringup.md)、[notes/123](../../notes/123-2026-11-01-rk3588-uboot-rockusb-loader-mode.md) |

旧日的 `scripts/forge.sh` 与它的 lib 库在仓库里已无实体，它是演进的一页，四段的名字就是它留下来的。这本书的构建侧到这里收拢完成：boot、rootfs、peripherals、sd-boot 四卷手敲过的每一步，如今都住在 src/forge 的一个 Python 包里，咱们三块板共用的是它，一条命令也就够了。
