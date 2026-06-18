# 15 — SFC/NAND saga 终章备忘（rootfs loader 弱写确认 + 80MHz 定型）

> 一页纸备忘。详细过程见 [notes/14](14-2026-06-18-rootfs-peb34-readpath-bug.md) + `document/logs/boot-sdl-20260618*`。记忆 `sfc-dll-saga-and-writepath` 顶部横幅是 canonical。

## 终局（2026-06-18，板上定死）
rootfs PEB3/4 的 `-74` ECC error **根因 = loader 写弱（>8 flip 不可纠）**，saga 原结论对，**不是** Linux 读 bug。
- **mainline `ecc_get_status` 正确**（`STATUS_ECC_UNCOR_ERROR=0x20` 对 W25N04KV 成立），不需要改 mainline。
- **ubiprog 首启 Linux 重写兜底**，RW UBIFS 跨冷重启持久化（板上多轮 + stress 验过）。
- **读速 80MHz 定型**（vendor EVB 对齐，DLL cell 130 / 窗口 [90,170]，+50% 读速）。

## saga 弧线（两次翻案，方向相反）
1. **boot `0x920000` "出厂坏块"** → 误诊（读截断 + 出厂垃圾）→ **翻案**（读全分区 + assemble 填满 16MB）✓ commit `028d6f7`
2. **rootfs PEB3/4 "loader 弱写"** → saga 原结论。复查想照 boot 翻案 → 验证矩阵①②③④推 "Linux 读 bug" → **trace 推翻**（SR=`0x20`=不可纠）→ **loader 弱写真，翻案作废**

> 两次都是"读侧"先入为主：boot 把好块读毛误诊成坏，rootfs 把弱写误诊成干净。根治都是看物理真值，不是看 host 读报不报错。

## 关键证据（铁证）
- **trace v2**（`spinand_read_page` 打 SR byte，只打 `st≠0x00`）：rootfs PEB3/4（全局 eb 317/318）`pg=3,5 st=0x20`、`pg=4 st=0x10`。log `boot-sdl-202606181427.txt`
- **W25N04KV datasheet §7.3.1**（mouser PDF）：SR bit[5:4] = `00`无错 / `01`(0x10)1-4纠 / **`10`(0x20)"NOT corrected" >8 flip 不可纠** / `11`(0x30)5-8 纠（超阈值）
- mainline `STATUS_ECC_UNCOR_ERROR=(2<<4)=0x20` ✓，`W25N04KV_STATUS_ECC_5_8_BITFLIPS=(3<<4)=0x30` ✓

## 教训（pitfalls 候选）
1. **单次 ECC 读不能判 loader 写稳定性**——loader 写**抖动**：同 loader 同数据，① 那次烧 ≤8 flip（on-die ECC 纠了，U-Boot 读无 `-74`），1427 那次烧 >8 flip（不可纠）。要看 SR 真值（trace），不能靠 `mtd read` 报不报错。
2. **翻案要 rigor**——`md.b` 头部 64 字节 ==源 ≠ 整块干净（那 3 页不在头部）；U-Boot `mtd read` 整块无 `-74` 也只代表"那次"loader 写 ≤8。
3. **诊断工具要对齐根因层**——host ECC 读报错（`-EBADMSG`）混合了"物理 flip"和"ECC 状态解析"，要直接看 SR byte（on-die ECC 真值）才能区分写弱 vs 读 bug。

## 当前可交付状态
- **patch**：`0001`(DT SFC+W25N04KV+RW rootfs) + `0002`(SFC DLL+powergood+WPEN) + `0003`(DT 80MHz)；`apply-series` 干净 v7.1 base 按序过（worktree 真重建验证代码一致）
- **commit**：rk-forge `d7e647d`；explore/linux `3afac7bb4`（80MHz DT）
- **镜像**：`update-nand-AUTO-PROVISION.img`（80MHz + ubiprog + 无 trace），板上 RW 验过（`boot-sdl-202606181545-ok`：80MHz DLL cell130、ubiprog peb=3/4 recovery、persist 冷重启存活、零 panic/ECC）

## 仍未解（不挡交付）
- **P5 loader 弱写根因**：trace 坐实了"写弱事实"（>8 flip），但**为什么** loader 写这几页弱（写侧配置/时序/io-domain）仍 open，需拆 rkbin loader。纯求知。
- **mkimage / afptool 仍 vendor**（P4）：pack-fit 的 uboot.img 还用 vendor mkimage 2017.09（vendor SPL 只认它的 `-E` external-data 布局）；assemble 用 vendor afptool/rkImageMaker。
