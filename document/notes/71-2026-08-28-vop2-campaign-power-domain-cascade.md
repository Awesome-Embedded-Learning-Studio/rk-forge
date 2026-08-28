# 71 — VOP2 战役（一）：电源域级联与 PrimeCell ID（2026-08-28）

> 用户裁定「做 VOP2，不做前人不做的事就没理由 rk-forge」。战役第一阶段收官：
> 显示管线的全部阻塞被逐环定位并解开两层，链条推进到 PL330 控制器寄存器——
> 离 fbcon 一脚之遥。本篇同时记录一次珍贵的「仿真器抓住真 bug」的误诊反转。

## 0. 结论

| 项 | 结果 |
|---|---|
| **电源域级联影子** | ✅ 26 条规则（pwr 掩码 → repair 位清零），pm-domain probe 从 -22 阵亡到全树构建成功 |
| **AMBA PrimeCell ID 影子** | ✅ 四块 pl330 dmac 的 PeriphID/PCellID 应答，dmac 从「无声拒绝」进到寄存器探测 |
| **VOP2 设备** | ✅ `fdd90000.vop: Adding to iommu group 5` —— 显示控制器首次被内核接纳 |
| **DSI** | 首次真正 probe（defer 在 LCD 稳压器，非自身） |
| 回归 | rk3568 linux/fit + rk3588 board 全绿 |
| 下一脚 | PL330 CR0-CR4 合理值（dmac probe 收尾）→ DMA → SPI → rk8xx PMIC → DSI → VOP2 |

## 1. 需求环链条全景（本次测绘的完整地图）

```
fbcon ← VOP2(fdd90000) ← DSI(fde20000)+panel ← vcc3v3-lcd-n(稳压器)
      ← dcdc-reg8 ← rk8xx SPI PMIC ← spi@feb20000 ← TX DMA 通道
      ← pl330 dmac(fea0/1/3, fed1) ← ① 电源域供应商 ② AMBA PeriphID ③ CRn 值
```

## 2. 两个模型的诞生

### 电源域级联（战役核心突破）

**现象**：`rockchip-pm-domain probe failed -22`，整树陪葬——VOP、DSI、六块
IOMMU、GPU、USB 全部 defer，显示管线连 probe 都不开始。

**排除法走了五步**（每步都有实锤）：modify_dtb 三件套逐个禁用/离线化→无辜；
纯主线 EVB dtb → 同样炸（排除 topeet 移植层）；DTB 落盘验尸 → reg 全对；
真板日志（#10 内核）→ 无此错。最后 `genpd_add_subdomain` 源码里挖出隐藏条款：

```c
if (!genpd_status_on(genpd) && genpd_status_on(subdomain))
    return -EINVAL;    /* 父 OFF 子 ON → 拒绝 */
```

**根因链**（PMU 读写探针全程实锤）：`need_regulator` 域（npu 等）在
`add_one_domain` 里**故意先下电**（regulator 状态未知，保守处理，源码注释
明写）→ 写 pwr BIT(1) → 真硅上父域断电**物理级联**到子域（nputop 的
repair@0x290 位真实清零）→ 我们的影子没有这个物理 → nputop 仍读 ON →
父 OFF 子 ON → -22。

**模型**：26 条级联规则——每个 repair 位对应一个 pwr 掩码（自己+全部祖先，
双亲域如 RKVDEC0 = VCODEC|VDPU 取并集），掩码任一置位则 repair 位清零。
规则表由 python 从 `pm-domains.c DOMAIN_RK3588 表 + dtsi 嵌套`自动生成
（栈快照法取祖先链；两次翻车：回扫取全顶层节点=掩码过宽、双亲漏并集）。

### AMBA PrimeCell ID

pl330 dmac 是 `arm,primecell` 设备——AMBA 总线靠 0xFD0-0xFFC 的
PeriphID/PCellID 认硬件，毯子回零 = 身份不合 = **无声拒绝**（"deferred,
reason unknown" 的真身）。影子应答 PL330 的 0x000413330（PID4=04/PID0=30/
PID1=33/PID2=13——首版把 PID1/PID2 写反了，AMBA 读探针一击定位）。

## 3. 教训沉淀

1. **genpd 的隐藏 -EINVAL**：`drivers/pmdomain/core.c` 里父子状态矛盾的
   拒绝条款，是任何电源域仿真的必修物理。
2. **排除法要走到底**：五步排除里最贵的是「DT 验尸」和「真板日志对质」——
   但没有它们就没有后来的源码定向。
3. **生成器也要验证**：拓扑表生成两次错（祖先链取法），靠「掩码值人工抽查」
   （NPUTOP 必须 0xa）抓住。
4. python heredoc 打补丁在长战役里成了负资产（一次 `\\n` 字面量、两次锚文本
   mismatch 各浪费一轮 build）——Edit 工具正路化，已在记忆里。

## 4. 复现

```bash
python3 boards/rk3588-topeet/sim/smoke.py board --check   # 电源域全树构建
grep "iommu group" <日志>                                  # VOP2 进组
```
