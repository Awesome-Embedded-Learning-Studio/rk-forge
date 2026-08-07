# rk-forge 项目蓝图与决策书

> **文档目的**:把 rk-forge 的**定位、工程架构、教学规划、待决事项**汇总成一份自包含文档,带到新仓按正确目录结构落地。
>
> **不绑定旧实现**:WSL 下的旧仓(`/home/charliechen/rk-forge`)已决定废弃。本文不引用它的具体文件路径作"修复项",只保留**决策 + 设计原则 + 旧仓教训**——这些是可移植的。旧仓里所有"修这个文件"的审计结论,在本文都转译成了"新仓的设计原则"。
>
> **如何用**:新仓若已有目录结构,把本文第 5 节的概念区映射过去即可;若是绿地,直接照第 5 节起步。

---

## 0. TL;DR

rk-forge = **每板全栈的 Rockchip Linux 教学 + 工程**项目。

- **主干**:每块板一条能学到底的全栈车道(驱动 bring-up → Qt / 媒体 / AI),**不换板**,学透 + 做出来。
- **三道亮色**:主线优先 · 真板诚实 · **追全开源(blob 消灭是北极星,不是核心动词)**。
- **工具**:全 Python(零 bash 逻辑),每板一份 YAML 配置 → Board dataclass,加板 ≈ 3 个触点。
- **三板**:RK3506B 驱动移植+bring-up / RK3568 框架+标准应用栈 / RK3588 异构全栈+全开源主战场。
- **出圈赌点**:V4L2 / 相机 / ISP 主线(P1)。

---

## 1. 定位

### 1.1 主干 vs 亮色(层级不能倒)

**主干(它是什么,每天交付什么)**:一套每板全栈的教学 + 工程项目。

**亮色(凭什么来 rk-forge)**:
1. **主线优先** —— 能用主线绝不碰 vendor;每块 SoC 的地基(pinctrl/clock、U-Boot SoC 支持、RK3588 的 GPU Panthor / NPU Rocket)都在主线。
2. **真板诚实** —— 每项能力挂真板证据,跑通说跑通、没通标没通,状态不刷绿。
3. **追全开源** —— 逐层消灭闭源 blob、走向全开源。**是亮色里最响的招牌 + 北极星,但只是招牌之一,不是项目定义。**

> 关键:别把没达到的远期目标(blob 全开源)当核心动词——会让定位虚。核心是每天是什么(教学/全栈/不换板)。

### 1.2 不是什么

不是发行版镜像 / 不是 Armbian·Yocto·厂商 BSP。不卷"成品饭",卖"菜谱 + 灶 + 带你做饭的书"。

### 1.3 北极星:全开源替代

当前绕不开的闭源:`rkbin`(DDR init / SPL / TEE)。态度:**先用,但当靶子,不当"先用着就行"的妥协**——每项文档化、追踪消除路径,随主线 U-Boot 推进按板攻(DDR init 最难啃;OP-TEE 上游可源码构建)。启动前段之外,kernel / U-Boot proper / 设备树全是开源主线。

> 独立身位:厂商 SDK 永不干掉自己的 blob,Armbian 不在乎,主线社区只管 driver 不管板级——"追 blob 到全开源"这条赛道没人占。

---

## 2. 三块板 = 三条全栈车道

### 2.1 车道(侧重/节奏,非域名割裂;每板都奔全栈)

| 板 | 车道定位 | 角色 |
|---|---|---|
| RK3506B(ARM32,A7×3) | 经典驱动移植 + bring-up + 存储可靠性 | 破圈招牌、入门板 |
| RK3568(AArch64,A55×4) | Linux 驱动框架 + 标准应用栈(Qt6/Wayland/Mesa) | 桥梁 |
| RK3588(AArch64,A76+A55) | 异构全栈(V4L2/VPU/NPU/GPU)+ 全开源主战场 | 全栈主角、blob 主战场 |

### 2.2 "不用换板"的诚实边界

原则:**你这块板硬件能干的领域,都能在这块板上学完。** 不是说 3506 上学 NPU(没那个硬件)——那是硬件现实,不是教程的锅。

### 2.3 状态:能力级诚实(尤其 RK3588)

状态不下沉到能力级就会被 RK3588 卡死——它有结构性绑 blob 的方向(VPU/MPP 要 firmware+闭源用户态;NPU Rocket 未成熟;Android 是 vendor 主场)。这些"主线 verified"物理上达不到。

→ **状态按能力/方向打标**,不按整板:boot 链 🟢 / 显示 DRM 🟡(VOP2 稳定性未闭环)/ GPU 🟡 / NPU 🔴(blocked on Rocket)/ VPU 🔴(blocked on blob)/ Android ⚪(planned,vendor 轨)。诚实地把 🔴 挂上 + 追消除路径,比"整板 supported"有公信力得多。

---

## 3. 教学架构

### 3.1 通用方法 + 每板证据页(两层)

- **方法层(资产,写一次)**:理论 / 调试方法 / 命令,三板共用。
- **证据层(每板附件)**:设备树、配置改动、真板 UART/日志。
- **加一块板 = 补一页证据,不是重写教程。**

### 3.2 推进节奏(按"能落到几块板"排优先级)

| 档 | 内容 | 板 |
|---|---|---|
| **P0 三板通吃** | bring-up / 基础外设 / Qt(最小→标准→产品) | 三板(兑现"不用换板") |
| **P1 差异化(出圈)** | DRM/显示+GPU、**V4L2/相机/ISP(下一个爆点)** | 3568 + 3588 |
| **P2 硬核** | NPU(Rocket)/ VPU(MPP)/ Android | 只 3588,绑 blob |

V4L2 赌点理由:需求大、别家烂、主线能做、**不绑 blob、风险低**。NPU 更性感但 Rocket 未成熟,放 P2 稳推。

### 3.3 证据链

真板日志 + 产物 + 配置齐备才能 `verified`;"跑通过一次" ≠ verified,"厂商 SDK 能跑" ≠ rk-forge verified。踩坑/失败 log 按故障域归档,是诚实承诺的底气,不删。

---

## 4. 工具架构(新仓,全 Python)

### 4.1 总则:单一语言,零 bash 逻辑

旧仓 bash 虽干净(零 /dev/tty、data→stdout、干净 exit),仍是维护/接缝负担;**config-as-bash 是迁移拦路虎**。新仓一刀切:**Python 是唯一构建逻辑语言**。外部工具(make/mkfs/dd/git/sgdisk)走 `subprocess`,不算"shell 逻辑"。

### 4.2 包结构(镜像 buildmeter 那套,它已是活样板)

- 顶层 `pyproject.toml`,可选 extras(weasyprint/pypandoc 等)。
- `forge/` 包,src/ layout,`[project.scripts] forge = forge.cli:main`。
- engine / cli / render 分离;带 `tests/`(pytest,从第一天起)。
- dual-mode 入口:既 `python -m forge`(已装),又 `python3 path/to/cli.py`(脚本式,免 PYTHONPATH)——方便集成。

### 4.3 配置:每板一份 YAML → Board dataclass(单一 reader)

**这是新仓最重要的一条。** 旧仓 config 散在 5+ 层(根 board.env / toolchain.conf / pins/<id>/ / 每板 .env / 8 个文件名间接字段),互覆、时序依赖、bash 语法 Python 读不了。新仓:**一份 `config/boards/<id>.yaml`,一个 Python `forge.config` loader 是唯一 reader。**

schema(结构化分区):
```
identity:   board / soc / arch / abi / cpu
kernel:     base_defconfig / fragments[] / img / dtb_name / base_ref
uboot:      defconfig / defconfig_sd / fit_source / arch_override='arm'  # 显式
storage:    nand|emmc + geometry(nand_min_io/peb/leb/max_leb) + rootfs_mib
rkbin:      blob_subdir / ddr/usbplug/spl/tee/bl31 patterns / tee_exclude / spl_source
toolchain:  prefix / bin_dir / sysroot
wifi_driver:
rootfs_profiles: []          # 能力声明,load 时强校验
sources:    {linux,uboot,openwrt,buildroot: {url, ref}}   # 吃掉 pins/
manifests:  {parameter,package,loader_ini,trust_ini} keyed by storage/profile   # 吃掉 8 个文件名字段
ubuntu:     hostname / username / packages_list / provisioning_hook   # 吃掉硬编码字面量
```
项目级(`config/forge.yaml`)只放板无关的路径 + 默认板。

### 4.4 显式化清单(旧仓 4 个"静默丢失"陷阱 → 必须显式)

Python 显式 env dict 会丢掉靠 bash 同 shell source 才漏过去的字段。新仓 schema 必须显式列:
1. **`SPL_SOURCE`、`ROOTFS_MIB`** —— 旧仓不在 export 列表,靠 source 漏给 pack 阶段。丢了 → rk3588 BL31 bootloop / ext4 太小,不报错。
2. **`uboot.arch_override`** —— U-Boot arm32/arm64 都从 `arch/arm/` 出,要强制 `ARCH=arm`。旧仓是 build-uboot.sh 里的隐藏规则,看不见。
3. **`rootfs_profiles[]` 能力校验** —— 旧仓只校验语法,`--board=3588 --rootfs=openwrt` 会在 fetch 中途死。load 时强校验能力。
4. **无 `_bt_*` save/restore shim** —— toolchain 变 board 字段后,旧仓那个时序依赖 shim 自动消失。别保留。

### 4.5 加板 = ~3 触点

旧仓加板要 7-12 文件、跨 4 目录、还要改"共享"脚本里偷埋的 board-id 字面量。新仓目标:
1. 一份 `config/boards/<id>.yaml`(唯一真相源);
2. 一个 `boards/<id>/`(只放**不可声明**的工件:kernel.config 片段、DT 补丁、FIT/RKBOOT 模板若不生成、BR2_EXTERNAL);
3. 一个 `patches/<id>/`(series + 补丁,代码评审单元,独立)。

**零 board-id 字面量在共享代码里** —— 旧仓的 `forge.sh:244/271`、`build-openwrt.sh:123/126/131`、`stage-rootfs.sh:99/54`、`build-ubuntu-rootfs.sh:132` 全是 if-链里硬编码板 id。新仓这些全是 Board dataclass 字段,走数据,不走分支。

### 4.6 外部工具:subprocess + 危险操作结构化防护

- `make` / `mkfs.ubifs` / `mke2fs` / `sgdisk` / `dd` / `git` / `boot_merger` → `subprocess.run([...])`,argv 显式,无引号/分词坑。
- **危险操作必须有结构化防护 + 测试**:旧仓 `flash-sd.sh` 的 `sudo dd` 防护齐全(--device 必填、拒分区节点、拒挂载点、拒系统盘、大小校验、输设备名确认)——照搬;旧仓 `pack-sd.sh` 的 sgdisk --zap-all + 原始 dd 偏移**缺块设备拒绝逻辑**——补上。
- 提供非交互 `--yes` 路径(用于 CI);交互确认走 stdin,不是 /dev/tty。

### 4.7 特权:显式 sudo / fakeroot,无 auto re-exec

旧仓 `build-ubuntu-rootfs.sh` 用 `exec sudo -E "$0"` 自我重 exec 提权,`stage-rootfs.sh`/`pack-emmc.sh` 用 `exec fakeroot` 重 exec。新仓:**别自动提权**——让用户显式 `sudo forge ...` / `fakeroot forge ...`,或入口检测需要 root 时 `os.execv` 在 sudo 下重跑自己。比 bash 隐式 auto-sudo 更诚实(用户知道这步要 root),不丢能力。fakeroot:Python 跑在 fakeroot 下面,不从 Python 调 fakeroot。

### 4.8 源码树布局:选定一种且保持一致

旧仓的 P0 炸雷:配置声明按板路径 `src/<board>/linux`,磁盘却是扁平 `src/linux`,**多板根本没通**(连 aes 自己的配置路径都解析不到磁盘树)。新仓:**先定 per-board 还是 flat,然后配置 + 磁盘 + fetch 三处一致**。见第 7 节待决项 #1。

### 4.9 测试 + CI 从第一天起

- 旧仓三个 Python 工具(fit-pack/rkfw-pack/build_pdf)**零单测**。新仓 pytest 从地基阶段就上,危险操作(dd/rm/patch rollback)有真测试。
- 旧仓 `build-pdf.sh` 被 CI(`pdf-export.yml`)verbatim 调用,迁移时漏改会断 CI。新仓 CI 入口跟 CLI 入口统一(`forge pdf`),别留两套。

---

## 5. 新仓目录结构建议(适配你已有的正确结构)

```
rk-forge/
  forge/                         # Python 包(src layout): cli / config(Board dataclass+loader) / core(stage DAG,内容哈希) / build,pack(subprocess) / tools(fit,rkfw,pdf)
  pyproject.toml                 # [project.scripts] forge=
  config/
    forge.yaml                   # 项目级(默认板、路径、共享 sources)
    boards/<id>.yaml             # 每板单一真相源
  boards/<id>/                   # 只放不可声明工件: kernel.config 片段 / DT 补丁 / FIT,RKBOOT 模板(若不生成) / BR2_EXTERNAL / ubuntu packages.list
  patches/<id>/{linux,uboot}/series   # 补丁(评审单元,独立;openwrt profile 仅相关板)
  third_party/                   # 构建依赖: rkbin(pinned submodule) + 源码树(per-board 或 flat,选定一种)
  reference/                     # vendor SDK 萃取池(非构建依赖)
  document/                      # tutorial / pitfalls / notes / logs / sdk-diff(每板一份) / planning
  tests/                         # pytest
  .github/workflows/             # CI: build/docs/pdf
```
> 若新仓已有结构,把上面的概念区(`forge/` 包 / `config/boards/<id>.yaml` / `boards/<id>/` 工件 / `patches/<id>/` / `third_party`/`reference` 分离)映射过去即可。核心约束:**每板一份 YAML + 一份工件目录 + 一份补丁目录**,其余全是这份数据派生。

---

## 6. 旧仓教训(审计结论 → 新仓原则)

| 旧仓反面教材 | 新仓原则 |
|---|---|
| config 散在 5+ 层(board.env/toolchain.conf/pins/每板 env/8 个文件名字段),互覆+时序依赖 | **每板一份 YAML,单一 reader** |
| config 是 bash 语法,Python 读不了(迁移拦路虎) | **YAML+dataclass 从第一天起** |
| SPL_SOURCE/ROOTFS_MIB 靠 source 漏过去;ARCH=arm 隐藏规则;ROOTFS_PROFILE 不校验能力 | **schema 显式列 + load 时强校验**(第 4.4) |
| 共享脚本里偷埋 board-id 字面量(8 处 if-链) | **板差异走 Board dataclass 字段,不走代码分支** |
| third_party/src 扁平 vs 配置按板,多板没通(P0 炸雷) | **源码树布局选定一种,配置+磁盘+fetch 三处一致** |
| Python 工具零单测 | **pytest 从地基阶段起,危险操作有测试** |
| build-pdf.sh 被 CI verbatim 调用,迁移漏改断 CI | **CI 入口 = CLI 入口,统一** |
| 源码硬编码凭证(charliechen + 预哈希密码 + 明文 chen0303) | **凭证走 env / 生成 secret,不入源** |
| rk3588 kernel.config 硬编码绝对 `CONFIG_EXTRA_FIRMWARE_DIR="/home/..."` 指向不存在目录 | **零绝对路径;firmware 路径相对项目根 + 缺失即报错** |
| 死/杂乱残留:根 board.env(误导新人)、空 rootfs/、1.5GB 重复克隆、孤儿 vendor defconfig、6 个数据行相同的 pin 文件(注释各带上下文) | **最小化,无死工件;pin 数据共享,差异才 per-board** |
| flash-sd dd 防护齐全,但 pack-sd 的 sgdisk+dd 没块设备拒绝 | **所有危险操作统一防护 + 测试** |

---

## 7. 待你拍板的事项(带到新仓定)

1. **源码树布局**:per-board(`src/<board>/linux`)还是 flat(`src/linux`)?选定一种,三处一致。(旧仓这个没定清楚是多板不通的根因。)
2. **凭证策略**:硬编码用户名/密码清成 env / 生成 secret?(公开教学仓的安全味道)
3. **ubuntu hostname 策略**:默认 = 板 id?per-board 字段?通用 `rkforge`?(决定 schema 里 `ubuntu.hostname` 形状)
4. **apply-series --reverse**:需要逆应用补丁吗(用于 rebase),还是失败时 git reset--hard+clean 原子回滚够用?(决定 Python patch 工具要不要 reverse 模式)
5. **reference 萃取池范围**:旧仓 README 写了 5 个池只 1 个在盘上。新仓要哪几个(vendor-sdk / rk3568 / rk3568_android / rk3588 / rk3588_android)?
6. **rk3588 firmware**:旧仓那个不存在的 `firmware/` 是 TODO(以后 stage Panthor mali_csffw.bin)还是构建一直静默跳过?(决定 `kernel.fragments` 怎么写 GPU 固件内嵌)
7. **U-Boot ARCH=arm 是否普适**:所有 Rockchip U-Boot 都从 `arch/arm/` 出,还是未来 RK3588 主线 U-Boot 可能要 `ARCH=arm64`?(决定 `uboot.arch_override` 是板字段还是项目常量)

---

## 8. 推进计划(新仓,绿地顺序)

> 绿地比旧仓迁移简单:无需过渡 bash env,直接 Python 起步。

| 阶段 | 内容 | 产出 |
|---|---|---|
| **F0 地基** | `forge/` 包 + pyproject + dual-mode 入口 + tests/ 骨架 + Board dataclass/loader(吃前 3 块板的 yaml) | `forge` 可装可跑空命令;配置可加载 |
| **F1 config** | 三块板的 `config/boards/*.yaml` 落地(按第 7 节决策);loader 强校验 + 显式化清单 | 每板配置单一真相源,加板 = 一份 yaml |
| **F2 核心** | stage DAG + 内容哈希跳过(Python);rkbin 解析;log/host 工具 | `forge status` / 增量构建可用 |
| **F3 构建/打包** | build-{linux,uboot,rootfs,openwrt} + pack-{loader,fit,ubifs,emmc,sd} → subprocess;fit-pack/rkfw-pack 并入包 | `forge build/pack/assemble` 全链 |
| **F4 编排收口** | `forge setup/build/pack/assemble/all/clean/status` CLI;doctor;progress(buildmeter 集成) | 单一入口闭环;**零 bash 逻辑** |
| **F5 内容(并行起步)** | 立"通用方法+每板证据页"模板 → P0 三板通收尾(bring-up/外设/Qt) → P1 V4L2/相机出圈 → P1 DRM/GPU → P2 NPU/VPU/Android | 教学使命兑现 |

F0-F4 是工程地基;F5 是教学使命,可在 F2 后并行(有了稳定 CLI,写教程有干净底座)。

---

## 9. 北极星看板(blob 消除,活文档)

挂文档站一处可见,随主线推进更新:

| 板 | DDR init | SPL | TEE | 现状 |
|---|---|---|---|---|
| RK3506B | 闭源(rkbin,最难) | 主线尝试中(旧仓自研 SPL 在 DDR 后崩) | rkbin tee;上游 OP-TEE 可源码构建 | 起步 |
| RK3568 | 闭源 | 主线 U-Boot 有 DRAM init 进展 | 同上 | 跟进 |
| RK3588 | 闭源 | 主线 SPL(旧仓规避 vendor SPL/BL31 基址错配) | 同上 | 主战场 |

消除路径:TEE → 源码构建(最易);SPL → 跟主线 U-Boot;DDR init → 最难,跟主线 DRAM init 上游化进度。

---

*本文是 rk-forge 的可移植蓝图。新仓落地时,以本文第 4(工具架构)+ 第 5(目录结构)+ 第 7(待决项)为施工依据;定位(第 1-3)已定,不重议。*
