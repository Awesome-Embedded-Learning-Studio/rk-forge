# 26 — ubiprog / loader 弱写现状(独立于 abort)+ 下一步 rkbin 配置线索

> abort 真根因(reserved-memory)见 [24](24-2026-06-19-sfc-abort-rootcause-reserved-memory-trust.md)。
> 本条专门回答:**abort 修了之后,ubiprog / loader 弱写 saga 还剩什么?为什么 ubiprog 是
> "兜底"不是"根治"?下一步要不要查 rkbin 配置对齐?**

## 现状:loader 弱写真、独立、ubiprog 照样必要 + 照样成功

abort(reserved-memory)修好后冷启(board-sdl-202606192323 boot2),ubiprog 首启置备:

```
peb=3   full-read uncorrectable → page recovery (5/64 pages unreadable → 0xFF, rest kept)
peb=4   full-read uncorrectable → page recovery (5/64 pages unreadable → 0xFF, rest kept)
peb=5   full-read uncorrectable → page recovery (2/64 ...)
peb=122 ... (2/64)   peb=124 ... (1/64)
ubiprog done: rewrote=207 recovered(page-level)=5 skipped(erased)=1180 failed=0
```

**三点结论**:

1. **loader 弱写真、和 abort 无关**:abort 已修,PEB 3/4/5/122/124 照样读出 **chip ECC -74
   (>8 flip 不可纠)**。这是 **NAND 芯片自己的 ECC 引擎报的**(W25N04KV 内部 ECC,host 只读
   feature 寄存器),OP-TEE 内存那套(host RAM 分配)碰不到它。→ **不是第三次误诊**。
2. **ubiprog 仍必要**:没它,loader 弱写的那几页会让 UBIFS 起不来/丢数据。
3. **ubiprog 这次也成功**(failed=0),rootfs 起来 + flash_stress 50/50 过。

## 为什么 ubiprog "还可能出问题"——它是 recovery,不是 cure

ubiprog 的 page recovery 语义:**把 loader 写得还能读的页,用 Linux 可靠路径重写一遍
(防日后劣化);读不回的页 → 填 0xFF**。命门在"读不回 → 0xFF":

- **那 ~15 页(5 个 PEB 各几页)的原始数据,loader 写坏了、ubiprog 读不回 → 永久丢了**。
  ubiprog 手里**没有第二份干净 rootfs**(boot.img 不含 rootfs,板上唯一副本就是 loader 写的
  那份),所以**无法恢复**,只能 0xFF。
- 若丢的页恰好落在某二进制/配置上 → **静默损坏**:boot + stress 跑不到就发现不了,哪天
  用到那个文件才炸。
- 现在没炸(50 圈过),是因为丢的页大概率落 UBIFS 空/非关键区,或 UBIFS 容忍了。
  **不是"没问题",是"还没碰到"。**

## 根因(loader 弱写)在 rkbin SPL blob 里 —— 动不了?

loader 的 SFC 写路径在 Boot1 blob(我们用**公开 rkbin** SPL v1.12 + DDR v1.06 + usbplug v1.03
+ tee v2.40)。sustained 写 rootfs 时 PEB 3/4 边际化(>8 flip)。blob 改不了。
vendor 没事,大概率是它的 loader(DT + loader blob 都对)。

→ **但这正是用户提的下一步方向**:rkbin 是**可配置**的(RKBOOT/*.ini 选 DDR/SPL/usbplug/tee
版本 + 各自 addr/load)。**会不会是我们 rkbin 配置没对齐 vendor,导致 loader 写 marginal?**
这和 reserved-memory 是同一类问题(配置没对齐 vendor)——值得查。见下节。

## 风险评级 + 可选根治路径

| 项 | 现状 |
|---|---|
| ubiprog 当前 | 工作(failed=0),rootfs 起、stress 过 |
| 残余风险 | 每次全新烧录**静默丢 ~15 页** rootfs 数据;bounded(稳定这 5 个 PEB)、低概率、非零 |
| 根因(loader 弱写) | rkbin SPL blob,不可改源 |
| **根治候选 A** | 换 ATK loader(rkbin-atk SPL v1.11)→ 若它写 rootfs 可靠 → 干掉弱写 → ubiprog 可退役。**代价:重引入 vendor blob 依赖(违 P1 公开链目标)** |
| **根治候选 B** | 复测 loader 弱写到底多严重(abort 已除,数据干净了)→ 若确认丢的页是非关键区,ubiprog 当保险绳定稿 |
| **根治候选 C(本次主线)** | 查 **rkbin 配置是否对齐 vendor**(RKBOOT .ini + 各 blob 版本/addr)→ 可能像 reserved-memory 一样,是个配置项没对齐 |

## 下一步:rkbin 配置对齐调查(候选 C,先查)

用户原话:"rkbin 我记得可以配置,是不是配置没有完全对齐导致的呢?"

**要查的对照项**(我们 vs vendor/ATK):

1. **RKBOOT .ini**(loader 组装单):
   - 我们:`third_party/bringup/RKBOOT-RK3506B-aes.ini`(pack-loader.sh 的模板)+ 公开
     `third_party/rkbin/RKBOOT/RK3506BMINIALL.ini`。
   - vendor/ATK:rkbin-atk 里对应的 .ini(若有)+ vendor SDK 的 loader 组装。
   - 对照:DDR/SPL/usbplug/tee 各自的**版本**、**FlashData/FlashBoot/LOAD_ADDR/PATH**。
2. **各 blob 版本**(已知差异,要核实是否相关):
   - 我们(公开链):DDR v1.06、SPL v1.12、usbplug v1.03、tee **v2.40**。
   - ATK(rkbin-atk):DDR v1.06、SPL **v1.11**、usbplug **v1.02**、tee **v2.10**。
   - loader 弱写是 **SPL** 的 SFC 写路径 → **SPL v1.12(公开) vs v1.11(ATK)** 的差异最可疑。
     (记忆 [[kill-vendor-sdk-roadmap]] 记过:公开仓全历史只有 SPL v1.12;板验的 v1.11 是
     ATK 专有。→ 我们被迫用 v1.12,vendor 用 v1.11。)
3. **SFC 写相关配置**:loader 的 SFC 时钟/驱动强度/powergood —— 这些在 blob 内部,.ini 暴露不了,
   只能靠换 blob(候选 A)或确认版本对齐(候选 C 的边界)。

**判断点**:
- 若 .ini 里 SPL 版本/addr 有可对齐项 → 像 reserved-memory 一样一改就好。
- 若差异只在 blob 二进制(SPL v1.12 vs v1.11,且 v1.11 是 ATK 专有)→ 候选 C 走不通,
  只能 A(换 ATK loader)或 B(接受 ubiprog 保险绳)。

**调查动作**(下个 session / 本 session 续):
- diff 我们 vs vendor 的 RKBOOT .ini(版本 + addr + load 字段)。
- 确认 SPL v1.12(公开)写 rootfs 是否就是比 v1.11(ATK)弱 —— 这个难直接证(blob 黑盒),
  间接证:若 ATK loader 写 rootfs 干净(可板测:用 rkbin-atk loader 打一个 update,首启看
  ubiprog 还报不报 PEB 3/4 uncorrectable)。
- 看 loader 弱写丢的那 ~15 页**到底是哪些 LEB/文件**(ubiprog 加日志报 PEB+page → LEB →
  UBIFS 区段),判断是不是关键数据(决定 B 是否成立)。

## 相关

- [[sfc-dll-saga-and-writepath]]:saga 主体,P5 闭环(loader 弱写位置无关证 + ubiprog 加固)。
- [[rootfs-weakwrite-reexam]]:loader 弱写曾想翻案,被 trace v2 + datasheet §7.3.1 否回(>8 flip 不可纠)。
- [[kill-vendor-sdk-roadmap]]:公开 rkbin vs rkbin-atk 的版本差异(SPL v1.12 vs v1.11 等)。
- [24](24-…-reserved-memory):abort 真根因(reserved-memory),和本条独立。
