# 任务书：RK3588 仿真线的 Mali-G610 GPU 建模预研（战役六可行性探索）

> 这是一份交给外部研究员（你，GPT）的任务书。我们的目标：搞清楚**如何在
> QEMU 里模拟 Arm Mali-G610（CSF 架构）GPU**，让我们基于 RK3588 的全系统
> 仿真线打通 GPU 这最后一环。你负责探索与论证，我们负责实现。请大胆假设、
> 小心求证，输出一份可以直接指导开工的预研报告。

## 1. 我们是谁、干到了哪

仓库 rk-forge：RK3568/RK3588 板卡的 Linux 移植工程台（内核/u-boot/rootfs/
烧录镜像全链），附带一条**QEMU 全系统仿真研究线**——自研机器模型
`rk3588-lite`（QEMU 11.1 fork，`hw/arm/rk3588-lite.c`，约千行）。

已达成（四个战役，一脉相承）：
- 真 RK3588 DTB + Ubuntu 26.04 完整 rootfs 在仿真里启动到串口登录；
- 电源域级联（PMU mem-chain）、DCPHY、VOP2 显示管线、DSI 面板逐影子建模；
- **GNOME 桌面（mutter 50.1 Wayland）已在仿真里点亮**——但走的是 llvmpipe
  软件渲染（guest 没有 GPU render node），冷启动到首帧 79s（TCG 地板）。

方法论叫**需求驱动的行为影子**（demand-driven behavior shadow）：不精确建模
硬件，只在 guest 驱动真正读写的寄存器上"撒最小的谎"（如 DCPHY 的 PLL_LOCK
位、PMU 状态字的位翻译、vop_mmu 的 FORCE_RESET 语义），让真驱动真协议栈
活下来。整套打法见仓库 document/notes/71-75 号笔记。

## 2. 宪法（先读这个，别的都好说）

**这条线只做"真 SoC 建模"，绝不引入假设备绕路。** guest 侧栈必须 100% 真：
真的 panthor 内核驱动、真的 Mesa、真的 GNOME。昨天的提议"换 virtio-gpu 让
宿主 GPU 代劳"已被否决——那是 VM 世界的熟路，换设备 = 研究对象消失。
但注意：在 **QEMU 侧**穿 Mali 的衣服做行为翻译（如把 CSF 命令流在宿主侧
执行），与我们的 VOP2 影子同族，是**合规**的建模手段。判据一句话：
**改动是否让 guest 看到的机器更接近真硬件。**

## 3. 已钉死的事实（省你考古，直接引用）

**目标硬件**：RK3588 SoC，Mali-G610（Valhall 架构、CSF 固件接口、
arch10.8）。

**guest 设备树里 GPU 节点已存在**（真板 DTS 带入，sim 未动它）：
```
gpu@fb000000 {
    compatible = "rockchip,rk3588-mali", "arm,mali-valhall-csf";
    reg = <0x0 0xfb000000 0x0 0x200000>;      /* 2MB MMIO，sim 里目前全零毯区 */
    interrupts = <GIC_SPI 92 LEVEL> /* job */, <93> /* mmu */, <94> /* gpu */;
    clocks = <&cru CLK_GPU>, <CLK_GPU_COREGROUP>, <CLK_GPU_STACKS>;
    assigned-clocks = <&scmi_clk SCMI_CLK_GPU>;  /* 注意：SCMI 走 secure 固件 */
    power-domains = <&power RK3588_PD_GPU>;      /* sim 的 PMU 影子已覆盖该域 */
};
```

**内核**：主线 v7.1 + 我们的移植补丁（编号 patch series，forge 流水线管理）。
`CONFIG_DRM_PANTHOR=y`（内建），`CONFIG_DRM_PANFROST=m`（本板不用）。
CSF 固件 `mali_csffw.bin`（arch10.8，282KB，闭源）经
`CONFIG_EXTRA_FIRMWARE` **内嵌进内核**，真板已用它点亮 GPU 加速桌面。

**真板参照系**：真机 RK3588 上 panthor + Mesa + GNOME 桌面**已验证通过**
（我们有串口日志可对照）。

**sim 现状**：panthor 内建 + DT 节点在，但 0xfb000000 无任何模型（读回全零）。
最近一次启动日志里 panthor **一个字都没打印**——它大概率在时钟/电源域/ID
校验的某一步静默 defer 了。这是第一个要侦察的点。

**QEMU 侧**：机器是 A55×4+A76×4、GICv3、2GB RAM、TCG（无 KVM，x86 宿主），
WLS2 环境。已有影子设备的代码模式可以照抄（MemoryRegionOps + 状态结构体 +
读撒谎/写记录）。

## 4. 技术分层：哪里下刀

guest 视角的栈（自上而下）：
```
GNOME/mutter → EGL/GL
  → Mesa panfrost 驱动（用户态，支持 CSF/panthor KMD；Ubuntu 26.04 自带）
    → /dev/panthor.*（panthor KMD 的 uapi：组/队列/提交/同步）
      → panthor 内核驱动（drivers/gpu/drm/panthor/，开源 = 接口的活文档）
        → CSF 固件接口（MCU 启动、固件加载、全局接口/门铃/队列协议）
          → mali_csffw.bin 跑在 GPU 内置 MCU 上（闭源）
            → Valhall shader cores / L2 / MMU（真硬件）
```

模拟的可下刀点（越往下越真、越往上越像作弊）：
- **刀口 A（寄存器级）**：模拟 CSF MMIO + MCU，让真固件跑起来——等于要模拟
  到微控制器级，闭源固件吃真硬件，基本不可行（但请论证，别只听我的）；
- **刀口 B（固件接口级）**★我们押这里：QEMU 设备实现 CSF 接口的**行为**
  ——MCU"假装"启动、固件"假装"加载完成、全局接口的组/队列管理命令按语义
  实现，job 提交翻译到宿主执行（宿主 GPU 或 CPU 软件执行）。guest 全栈无感。
  方法论亲戚：virgl 的翻译层（只借方法论，不借设备）、Renode 的 GPU 模型、
  Android 模拟器的 guest GPU 翻译；
- **刀口 C（KMD 之上）**：= virtio 路线，违宪，禁止。

## 5. 要你回答的问题（按优先级）

1. **先例考古**：QEMU 社区/学术界有没有人模拟过 Mali（任何代）？Renode 的
   Mali 模型（如 Mali-470/200）做到什么深度、怎么处理作业执行？Asahi Linux
   逆向 Apple GPU 固件接口的方法论有无可借鉴（同为固件调度型 GPU）？
   Android emulator / virgl / venus 的"guest 侧真驱动 + 宿主侧翻译"各自的
   刀口在哪、代价是什么？
2. **接口考古**：以 v7.1 的 drivers/gpu/drm/panthor/ 源码为规格书，梳出
   probe→固件加载→全局接口→队列创建→job 提交→同步/中断 的完整握手序列，
   落成一份"影子实现寄存器清单"：每步读哪些 MMIO、期待什么值、写什么触发
   什么、三个 IRQ（job/mmu/gpu）各在什么语义下拉高。这是报告的核心交付物。
3. **可行性裁决**：刀口 B 的分层实现路线——
   M0 = panthor probe 通过、`/dev/dri/renderD*` 出现；
   M1 = Mesa 枚举成功（EGL/GL context 建立）；
   M2 = 第一个不落 llvmpipe 的合成帧（GNOME 或 glmark）；
   M3 = 性能可用（对比 79s 地板）。
   每级的工作量量级、风险、以及"M0/M1 甚至不需要执行 shader"是否成立
   （即：CSF 接口能假装到多晚才需要真正执行 GPU 作业）。
4. **宿主执行后端**：翻译后的作业在宿主侧怎么跑最合理——复用 Mesa 自身
   （同一份 panfrost 驱动在宿主以软件/其他后端跑）？llvmpipe 当软件后端？
   还是有"离线执行 CSF 命令流"的现成工具（pandecode 家族？）？
5. **坑预警**：SCMI 时钟（GPU assigned-clock 走 secure 固件通道，我们 sim
   没有 TF-A）会不会在 M0 之前就卡死 probe？devfreq/冷却设备这些旁支要在
   影子里怎么应付？

## 6. 我们能配合提供的

- panthor 驱动源码任一文件（v7.1）、真板成功路径的 dmesg、sim 当前
  devices_deferred 列表、机器模型源码、71-75 号笔记全文。
- 你的报告被采纳后，实现由我们按 forge 纪律落地（编号补丁、一课题一笔记）。

## 7. 交付格式

一份 Markdown 预研报告：先例考古 → 接口规格（寄存器表 + 握手序列图）→
刀口裁决与里程碑计划（M0-M3，各含验收命令）→ 风险与坑清单 → 开放问题。
请明确区分"我从源码/文档确证的"与"我推断的"，推断要给出可证伪的验证法。
