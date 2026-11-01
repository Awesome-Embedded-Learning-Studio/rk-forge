# 120 — V0PLL 重父修复结案:GMAC wedge 战役显示线全胜(2026-11-01 晚)

> 接 118/119。任务书 dyn/vop-handoff-session-prompt.md 的收官章节。
> 三轮(R30 复现仪器化 → R31 修复轮 → R32 正式确认)闭环,根因与修复
> 均为机制级证据,非单轮存活。

## 1. 根因(最终定论)

**0009 把 DCLK_VOP2_SRC←V0PLL 的重父写在了 &vp2(port 子节点)上——
port 不是设备,of_clk_set_defaults 永远不跑,重父从未生效。** DCLK_VOP2_SRC
于是一直挂在默认父 GPLL 上(R30 基线 CLKSEL_CON112 mux=0 直接坐实;Andy Yan
2025-03-12 lkml 原话同判)。主线 vop2_crtc_atomic_enable 的
`clk_set_rate(vp->dclk, 82MHz)`:82MHz 从 GPLL 除不尽,请求经
DCLK_VOP2/DCLK_VOP2_SRC 双层 CLK_SET_RATE_PARENT|NO_REPARENT 传播进共享
GPLL 触发重锁;GPLL 同时是 clk_gmac_125m/50m 与 aclk_php_root 的父——
php 岛时钟世界被显示改频打翻,GMAC0 从口 AXI 读永不返回,伴生 php_grf
复位像(CON0 8→0/CLK_CON1 10→18,R21 证明翻转非死亡必要条件)。

这与 vendor 5.10 同板全活自洽:vendor 把 dclk 源配在 V0PLL 上。

## 2. 修复(0033,正式补丁,已在 series)

`boards/rk3588-topeet/patches/linux/0033-dts-rk3588-topeet-parent-DCLK_VOP2_SRC-from-V0PLL.patch`
:重父挪到 &vop 设备节点,与 ACLK 750M 合并(`<0>` 占位),删 &vp2 死代码。
dtb 验证:assigned-clock-parents = `0 33 3`(cru/PLL_V0PLL)。

## 3. 三轮账

| 轮 | 镜像 | 判决 |
|---|---|---|
| R30(vop/1.txt) | -00026 g2ab357d16d89:显示全开+0030v7(CRU 监视)+0032v1 | 死在 `[drm] Initialized`(1.2119)后、一切 modeset 标记前,console 即刻阵亡。基线坐实 dclk 源=GPLL。兼 R11 参照(全开必死) |
| **R31(vop/2.txt)** | -00027 gf01819b0e8bd:**+0033 修复**+0032v2(死区加密标记) | **全绿**:标记链全打完;set_rate 12M→**82,000,000 精确命中**(GPLL 整数分频给不出,反证源已换);1.245 **V0PLL 重锁(0xc6→0x148)、GPLL/CPLL/AUPLL 全程零横幅**;php_grf 零翻转;1.587 fbcon 接管(LCD 出画面);5.918 eth0 Link Up 1Gbps;5.964 NFS 挂根;login/shell |
| R32(待跑) | -00025 g35eeb9c8550f:正式镜像(0030/0032 退役注释,文件留档) | 预期=无拐棍(bootargs 摘 buff)三绿;然后按 118 §4 烧 eMMC |

## 4. 判据链(R31 为什么是机制级闭环)

GPLL 零变更 + V0PLL 精确重锁 + dclk 精确 82MHz + php_grf 稳定 + eth/NFS/显示
三者并存——修复的设计预期(「82MHz 改频落进专用 PLL,共享 PLL 不被碰」)
被逐项观察证实,不是撞大运的单轮存活。R30(同栈无修复)同晚必死作对照。

## 5. 收尾状态

- TEMP 全退役:0022/0026/0029/0030/0031/0032 均注释(series 留案),
  patch 文件保留作证据
- 诊断 bootargs 可摘(均为辅助,无一掩盖病):`irqchip.gicv3_pseudo_nmi=1`
  (楔死期 console 韧性)、`rcupdate.rcu_expedited=1`(迭代提速)、
  `rcu_nocbs=all`(调试稳态);`earlycon`+`console=ttyFIQ0` 是设计(0003)保留;
  `nolock` 是 PC 防火墙配套必须留
- 可选后续卫生轮:0024(PD_GMAC always-on)/0027(GMAC 时钟 always-on)
  属「根因修复后多余但无害」的防御层,留去自便,建议先留着
- LCD 上真出画面(128x37 fbcon)但「VOP2 hardlock 未闭环」的旧线
  (rk3588-lite-sim 战役遗留)与本战役无关,显示压力测试另开课题

## 6. 教训增量

- **port 子节点不是设备**:assigned-clock-* 写在 port 上=静默死代码
  (dtc 不报错)。设备级重查应成条件反射
- 0030 v7 的 SEL110/SEL112 偏移算错 4 字节(实读 CON111/CON113)——
  本轮判决靠 PLL 横幅+标记链+结果三重证据未受影响;off-by-one 要用
  宏算,别手算 16 进制
- `git reset --hard HEAD~1` 重做补丁层会连工作区编辑一起抹掉(踩过:
  0032-v1 只剩 include 行,靠 grep patch 文件行数抓回)
- printk 异步:死点瞬间阵亡时,标记可能未冲出 UART——标记「没出现」
  不能直接等于「没执行」,判读要留这个口子(R30 教训)
- 复用资产:0030v7 的 CRU 监视组模板(4×PLL_CON0-3+MODE0+CLKSEL 组)
  可作 RK3588 时钟类问题的通用仪器

## 7. 资产坐标

- 修复补丁:0033(见上);正式镜像 `out/rk3588-topeet/boot.img`
  (7.1.0-00025-g35eeb9c8550f,8cd9520d→35eeb9c8,25 张)
- 日志:vop/1.txt(R30)、vop/2.txt(R31)
- 会诊:dyn/gpt-consult-004-display-bisect.md + dyn/gpt-consult-004-review.md
- 先例存档:document/logs/rk3588/vop/email.txt(Andy Yan 2025-03-12)
- 轮次卡:dyn/r30-run-card.md、dyn/r31-run-card.md
