# 118 — RK3588 GMAC fabric wedge 战役交接（2026-11-01 凌晨）

> 目标原本是 NFS root 迭代引擎；挖出并修掉了三颗雷之后，剩下的主病是：
> **eth0 open 后第一次 MDIO readl 楔死 AXI fabric**。三份修复（0024/0025/0027）各自
> 治好了各自的病，但主病仍在。本文是完整交接：实验矩阵、证据链、假说记分板、
> 资产坐标、下一手建议。接手者：用户本人。

## 0. 近因链（已钉死，不用再验）

```
eth0 open → stmmac_open: setup_dma_desc(RxQ 打印) → pm_runtime_resume_and_get(返回 0)
→ stmmac_init_phy → phy_attach_direct → 第一次 MDIO 事务
→ stmmac_mdio_wait() 的第一个 readl(MII_ADDR) → AXI 不返回 → 该 CPU hard lock
→ fabric 逐步饿死（vblank 超时、SPI2/RK806 -110、其他核陆续死）
```

**probe 阶段的同一 MDIO 事务全通**（8.txt @0.997s 二十笔 xfer done；多个 boot 复现）。
死活分界在 probe 与 open 之间——但 9-b（maxcpus=4）在 **probe 阶段第 9 笔**就死（时序漂移，
唯一离群点，未解）。

## 1. 实验矩阵总账（logs/rk3588/nfs/1-9b + 两次未编号）

| 轮 | 内核/变量 | 结果 |
|---|---|---|
| 1-2 | -00021(NFS,±pseudo_nmi) | 死@1.78s initcall 区（无 RxQ） |
| 3 | -00021+initcall_debug | RxQ 后死@5.98s |
| 4 | -00021+blacklist cpufreq×2 | RxQ 后死，26s panic CPU5（**当时 0025 未修，发明脚在场，此轮证据作废**） |
| E1/E4 | -00020/21 eMMC+sh 手动 ip link | open 即死（同上，发明脚/域断电年代，证据作废） |
| E5 | -00020 devmem A/B | 1.3s 活 / 6.3s 死 → 域断电读=楔死（0024 已治） |
| 7 | -00022(0024+0025) NFS | RxQ-0/1 后静默，2.2s 死，cpu4 首爬 1608MHz |
| 8 | -00023(+0026 探针) NFS | probe MDIO 全通 → open mdio_read reg=31 pre wait 后死 |
| 9-a | -00023+clk_ignore_unused | 同 8 死点 → **late-init 时钟清扫无罪** |
| 9-b | -00023+maxcpus=4 | **probe 第 9 笔 MDIO 死**（离群）；cpufreq 全程未起 → **maxcpus 场景 CPU 线无罪** |
| 65s 判别 | -00023 eMMC+sh | shell 空转 65s 全稳（VOP/DSI/GPU/cpufreq 全在跑）→ **idle 无事，ip link 即死** |
| 终局试 | -00024(+0027 CLK_IS_CRITICAL) NFS | **同 8 死点** → stmmac 门控时钟这条子线也存疑（或 critical 未生效，见 §5-3） |

## 2. 假说记分板（dsh-005 + 终局试后）

| 假说 | 置信度 | 状态 |
|---|---|---|
| GMAC 电源/时钟/恢复窗未保证（A 线） | 0.60 | 近因成立；具体机制三连败（autosuspend 门控论被 0027 弱化、清扫论被 9-a 杀、域断电论被 0024+E5 分流）→ 剩「恢复稳定窗/PD QoS/ACLK」细分，见 dsh-005 §7 |
| CPU/供电轨（B 线，用户提出） | 0.25 | 降级为共病：65s idle 稳 + maxcpus=4 仍死；但 9-b 离群 + 早期 UART 乱码 + 历病史（51/53）保它一线 |
| 第三线：NoC/QoS、SMMU、DSU/DDR、GPU 域 device-link | 0.15 | dsh-005 §8 有展开 |

## 3. 已修复落袋（三笔正式补丁 + 一笔临时）

| 补丁 | 内容 | 状态 |
|---|---|---|
| 0024 | PD_GMAC GENPD_FLAG_ALWAYS_ON（E5 实证域断电读=楔死，此防真实有效） | 正式 |
| 0025 | 删发明的 PHY 复位脚 gpio0_B0（vendor 无此脚；瞬杀源） | 正式 |
| 0027 | GMAC 三钟 CLK_IS_CRITICAL（vendor clk_gate.always_on 的域内版） | 正式，但未治愈主病 |
| 0026 | TEMP 探针（stmmac_open 4 处 + mdio_access 3 处 netdev_info） | **临时，结案后删** |

series 现状：0001-0021 + 0024/0025/0026/0027（0022 SIM-DIAG 注释态），24 张 replay 验证过
（`8cd9520d → 1074ad16`）。**全部未 commit**（含 kernel.config 的 NFS 段、boot-emmc.cmd 的
NFS bootargs、本笔记、logs/nfs/1-9b、dyn/dsh-001..005）。

## 4. 资产坐标

- 探针内核 `-00024`：out/rk3588-topeet/{boot.img,tftpboot/boot.img}（cmp 一致）
- dsh 报告：dyn/dsh-001..005（005 是总判决 + §4 六实验矩阵 + §5 判定表，接手先读它）
- 历史病案：notes/51（RK860X/I²C 挂死）、53（hardlock+ramoops）、54（VOP2 handoff）、117（本战役上半场）
- NFS/TFTP 基建：nfsd 导出 out 树、tftpd@out/.../tftpboot、直连静态段 192.168.50.5/99
  （WSL mirrored、Windows arp -a 权威、ICMP-in-50 规则）；U-Boot 每次要 setenv ipaddr/serverip（无 saveenv）
- 构建咒语：`git -C third_party/src/rk3588-topeet/linux reset --hard 8cd9520d && PYTHONPATH=src python3 -m forge apply --board rk3588-topeet --component linux --worktree third_party/src/rk3588-topeet/linux && forge build linux / pack`；**pipefail 必开**（tail 吞退出码两次坑）、staged 必须 cmp、版本串必须 grep boot.img

## 5. 下一手建议（按信息量排序，接手自由取舍）

1. **读 dsh-005 §4 的 E7/E8**（它设计好的区分实验：A 线内部细分——PD/ACLK/恢复窗，含判定表）
2. **验 0027 是否真生效**：-00024 eMMC+sh 起来（若 idle 仍稳）→ `cat /sys/kernel/debug/clk/clk_summary | grep -i gmac`（prepare/enable 计数 + critical 标志位）。critical 生效仍死 → 门控论出局，A 线收敛到 PD/QoS/恢复窗
3. **9-b 离群点**：为什么 maxcpus=4 在 probe 第 9 笔死——它与主线死法的异同是最未被使用的线索
4. 早期 UART 乱码（9-b 1.204s `1.8ʢº²`）在死前就出现——电气/参考钟干扰角度（clock_in_out=output 下 SoC 外供 PHY 钟，GMAC 活动是否干扰板级信号）值得一次示波器/换板验证
5. vendor 5.10 stmmac 的 runtime PM 与 mdio 实现逐行 diff（reference/rk3588/kernel/.../stmmac/）——特别是它 mdio_access 有没有 pm_runtime 保护差异
6. 上游 lore 检索（dsh-004 §4 布置过）：stmmac rk3588 mdio hang / first-open hang 的 fix commit

## 6. 教训清单（本战役新增）

- 「stable 内核 + 新 bootargs」不等于受控实验：轮 4/E1/E4 的「GMAC 中心」证据全部被后来的 0025 翻案
- 每 15 分钟一轮的 tftp 免烧录循环 + ungated 探针 = 他isenbug 唯一可靠对抗手段
- 一病万症：fabric 楔死的外显（vblank 饿死/SPI -110/多核 lockup/console 半行）全是派生，别追症状
- dsh 的任务书锚点质量 = 产出质量；它的五单报告（001-005）是本战役最值钱的资产之二（另一个是 logs/nfs/）
