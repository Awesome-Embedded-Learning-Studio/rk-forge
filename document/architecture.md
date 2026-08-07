# rk-forge 架构决策记录

> 权威施工依据。[blueprint.md](./blueprint) = **为什么**(设计原则 + 旧仓教训),本文 = **定了什么 + 待定什么**。
> 就地重构,branch `upgrade/refactor_project`,bash → Python。每条带一行理由 + 状态:🔒 已锁定 / 🟡 待定(带推荐)。

## 1. 顶层目录(🔒)

```
rk-forge/
  forge.yaml                     项目级唯一配置(根):默认板、路径、共享源池
  pyproject.toml                 [project.scripts] forge = forge.cli:main
  forge/                         工具(Python 包):cli/config/core/build/pack/tools
  boards/<id>/                   一块板 = 一个自洽目录(加板 = 1 触点)
    board.yaml                     声明(身份/kernel/uboot/storage/rkbin/manifests/sources/profiles/ubuntu)
    patches/{linux,uboot}/         补丁(series + *.patch;上游向评审单元)
    kernel.config  fit/*.its  RKBOOT*.ini  parameter*  package-file*
    buildroot-external/  ubuntu/  rootfs/  firmware/  ...
  third_party/                   真实构建依赖(rkbin+buildmeter submodule;buildroot+src/<id>/ gitignored)
  out/                           全部产物(ls out/ → update-<board>.img 一眼可见;gitignored)
  document/  site/  reference/   不动
```

| 决策 | 理由(一行) |
|---|---|
| 🔒 砍掉 `config/` 目录 | 目录是"塞石"入口。项目配置=根 `forge.yaml`(单文件),板配置=`boards/<id>/board.yaml`;按板 id 约束的目录 + 单文件都没有堆砌入口。 |
| 🔒 合并 `patches/<id>/` → `boards/<id>/patches/` | 补丁本就 per-board(无跨板共享);合了"加板=1 触点"。保留 `patches/` named subdir 保"上游向评审单元"语义。 |
| 🔒 保留 `third_party/` 名字(不换 deps/) | "第三方 pin 住的代码"语义更强(对照 `reference/`=只看不用的非构建池);零迁移成本。 |
| 🔒 单一根 `out/`,update.img 一眼可见 | 今天 `board/<id>/out/` 把产物和中间件混埋;新版 finals 与 intermediates 分层。 |
| 🔒 源码树保持 per-board(`third_party/src/<id>/`) | 磁盘+config 已一致 per-board;两板不能共享打补丁的树。零磁盘改动,loader 显式算路径。 |
| 🔒 `board/` → `boards/` | 配合合并与单复数对称,一次 churn。 |

## 2. 配置:聚合 YAML,单一 reader(🔒)

- `forge/config/` 包内**一个 loader** 是唯一 reader:读根 `forge.yaml` + `boards/<id>/board.yaml`,解析路径、跨文件引用(wifi_driver id → forge.yaml 池)、跑校验。
- **加载时强校验**(蓝图 §4.4 四个"静默丢失"陷阱全封):
  1. `kernel.base == sources.linux.ref`(防漂移)
  2. `uboot.arch_override` / `rkbin.spl_source` **键必存在**(防 bash `:-` 默认泄漏;丢了 rk3588 会 bootloop)
  3. `storage.kind==emmc/sd` → `rootfs_mib` 必填且 <4096;`kind==nand` → `nand_geometry` 必填
  4. `--board/--rootfs` 能力组合**加载阶段 <1ms 拒掉**(如 `--board=3588 --rootfs=openwrt`),不再 fetch 中途死
  5. 零绝对路径(`CONFIG_EXTRA_FIRMWARE_DIR=/home/...` 这类结构性消失)
- **删除**:根 `board.env`(死占位 rk3506-evb,从不被 source)、`config/{forge.env,toolchain.conf,boards/*.env}`、`pins/`(11 文件,进 `sources:`)。

## 3. 工具:forge/ Python 包,bash 退役(🔒)

- 6 桶 `cli/config/core/build/pack/tools`;32 个脚本 1:1 映射(`lib/stage.sh` 内容哈希 → `core/stage.py`,`forge.sh` run_stage → `core/dag.py`)。
- **唯一 subprocess 入口** `core/proc.run(argv[])`:argv 显式,永不 `shell=True`,env 显式 dict(这是 Python 抓住"bash source 偷漏字段"的方式)。
- **危险操作 named guards**:`flash-sd` dd 防护链全保留;`pack-sd` 补"拒绝块设备"。
- **特权显式化**:删 3 处 `exec sudo/fakeroot` 自动重 exec → `sudo forge` / `fakeroot forge` 显式。
- **共享代码零 board-id 字面量**:原 8 处(`forge.sh:244/271`、`build-openwrt.sh:123/126/131`、`stage-rootfs.sh:54/99`、`build-ubuntu-rootfs.sh:132`)全变 Board dataclass 字段。
- CLI:`forge setup/build/pack/assemble/all/clean/status/doctor/pdf/flash`。

## 4. 迁移顺序:配置先走,脚本不动(🔒)

- **PR0 黄金网**:跑全 3 板 `forge all`,产物 sha256 存 `tests/golden/`(零行为变更)。
- **PR1 最小首 PR**:`forge/` 包(loader + env emitter)+ 3 个 `boards/<id>/board.yaml`(1:1 忠实翻译)+ `lib/env.sh` 一行桥接(source 生成的 env)+ 字段对等测试。**配置先到 YAML,bash 照跑。**
- **PR2 显式化校验** + 删 `_bt_*` shim。
- **PR3..N 叶子逐个迁**(每个独立 golden diff):`build-* → forge build`、`pack-* → forge pack`、`assemble → forge assemble`。
- **F3 编排器**(最险):`forge.sh → cli.py`,并行跑 legacy vs 新,全 `out/` 内容哈希 diff。
- **F4 目录清理 + out/ 聚合**:删 board.env/pins/.env、`board/→boards/`、CI 入口统一 `forge pdf`。
- **out/ 聚合**放 PR1(让所有迁移从一开始指向新路径)或 F4 —— 见 §5。

## 5. 待定决策 → 已锁定(🔒)

### 5.1 机械/共识项(默认采纳,已锁)
| 决策 | 落定 |
|---|---|
| 🔒 `out/` 内部分层 | `out/dist/<board>/`(finals)+ `out/build/<board>/`(intermediates+cache)+ 根 `out/update-<board>.img` 符号链接 + `MANIFEST.md`。`forge clean` 只清 build/,保留昂贵的 deps/(ubuntu-rootfs.tar)。 |
| 🔒 WiFi 驱动池位置 | `forge.yaml` 共享池,板按 id 引用(同一 fork 多板复用,URL/ref 只存一处)。 |
| 🔒 U-Boot `ARCH=arm` | 板字段 `uboot.arch_override`,默认 `arm`(可见、未来 arm64 一处翻)。 |
| 🔒 `apply-series --reverse` | 不实现,失败用 `git reset --hard + clean` 原子回滚(除非真出现 rebase 场景)。 |
| 🔒 `pack-sd` CLI | 折进 `forge pack --media sd`(少一个子命令;SD uboot 子构建作内部 stage,不动 NAND 产物)。 |
| 🔒 `forge flash` | 保留为一等子命令(承载 §3 的 guard 设计;唯一写卡路径)。 |
| 🔒 manifests(parameter/package/RKBOOT) | 暂作 tracked text 放 `boards/<id>/`(低风险;以后再考虑从 YAML 生成)。 |

### 5.2 三项判断题(已拍板)
1. 🔒 **ubuntu hostname = 默认板 id**。board.yaml 的 `ubuntu.hostname`,缺省取板 id;需要时板可覆盖。
2. 🔒 **凭证:明文进 YAML,不走 env**。账户默认放 **`forge.yaml` 的 `ubuntu.account`**:`{username: rk-forge, password: rk-forge, uid: 1000, groups: [...], autologin: true}`(全板一致,板可在 board.yaml 覆盖)。**构建时把明文 `openssl passwd -6` 哈希写进 /etc/shadow**——YAML 只存明文,镜像里只有哈希。
   > 与蓝图 §6"硬编码凭证"教训**不冲突**:§6 批的是**个人凭证**(charliechen / chen0303,真人名 + 疑似真人密码)烤进构建脚本 = 泄漏;现在是**通用、刻意公开的教学默认**(`rk-forge`/`rk-forge`,等同 Ubuntu live 镜像文档化的默认登录),写在配置、无密可保。判据 = "有没有敏感信息"。
3. 🔒 **rk3588 firmware:现在就建模** `kernel.firmware` 块(loader 解析项目相对路径 + 缺失即报错,结构性防 `/home/...` 绝对路径坑);先空着,`mali_csffw.bin` 落到 `boards/rk3588-topeet/firmware/`。

> §1–5 至此全部 🔒。架构方案定稿,可进施工(P0 黄金网 → P1 loader+board.yaml)。

## 6. 关联:定位文案(已落地)
定位文案两件事已应用:

- **README 枢纽化**:README 不讲故事,只说"干什么"+ 现状简表 + 「去哪找什么」导览;定位论述/比喻/细节搬到二级文档([blueprint](./blueprint) / document)。诚实化结构性达成(无叙事 = 无过度宣称空间)。原则见记忆 `readme-no-story-hub`。
- **6 条事实修复**(下表):均已 grep 核验并应用;上栈 Qt/媒体/AI 一律按"方向 / roadmap"表述,不写成已交付。
- README 称补丁带 `[mainline]/[uboot]` 前缀——实际 36 个补丁全无此前缀;
- README 称补丁带 `Signed-off-by`——不齐(aes/uboot 5 个、rk3568-atk/linux 0002 缺);
- U-Boot 徽标 `2026.07` vs 实际 `v2026.07-rc4+43`;
- `blobs.md` 自称"唯一真相源"却只覆盖 aes(3568 BL31 / 3588 DDR+BL31+mali_csffw 零提及);
- `planning/index.md` RK3506B 行"🟢 partial"图标与文字打架;
- README RK3588"出图"欠 VOP2 稳定性未闭环的限定(内部文档有,口号层欠)。

详见上轮 7 维审计结论。

---

*本文为活文档;决策落定后 🟡 → 🔒。*
