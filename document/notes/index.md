---
title: 工程笔记
---

<PageHeader icon="🗒️" title="工程笔记" description="raw、按天的 bring-up 流水——what worked, what didn't，原样保留" />

这一层是 rk-forge 的**诚实底层**：73 篇带日期的 bring-up 流水，原样保留——成功的、失败的、brick 时的慌乱、半成品、噪音，一个不删、不去重。它是踩坑日记（[pitfalls/](../pitfalls/)）和教程（[tutorial/](../tutorial/)）的取证源：后两者是提炼后的结论，这里是现场。

> 命名约定 `NN-YYYY-MM-DD-<slug>.md`：**序号** = 推荐阅读顺序（理解项目的递进阶段），**日期** = 工作日期，**slug** = 一句话描述。序号主导排序。

完整 73 篇按阶段递进的阅读顺序，见左侧栏或 [notes/README](./README) 的阶段表。下面挑几个里程碑入口：

<ChapterNav>
  <ChapterLink num="07" href="07-2026-06-15-milestone-mainline-linux-boots">里程碑：主线 Linux 首次启动</ChapterLink>
  <ChapterLink num="13" href="13-2026-06-17-p1-rkbin-public-loader-conquest">P1：公开 rkbin loader 攻克</ChapterLink>
  <ChapterLink num="20" href="20-2026-06-19-mkimage-saga-handoff">mkimage saga 交接</ChapterLink>
  <ChapterLink num="30" href="30-2026-06-20-wifi-rtl8733bu-port-complete">WiFi RTL8733BU 移植完成</ChapterLink>
  <ChapterLink num="32" href="32-2026-06-21-sd-card-image-sd1">SD 卡镜像 SD-1</ChapterLink>
  <ChapterLink num="36" href="36-2026-07-22-rk3568-multiboard-and-mainline-build">RK3568：多板框架 + 主线 boot</ChapterLink>
  <ChapterLink num="50" href="50-2026-07-27-rk3588-first-boot-baud-root-dt">RK3588：首次 boot 到 systemd</ChapterLink>
  <ChapterLink num="48" href="48-2026-08-01-rk3588-gpu-firmware-embedded-gnome-desktop">RK3588：GPU 固件 + GNOME 桌面</ChapterLink>
  <ChapterLink num="57" href="57-2026-08-12-rk3588-vendor-cpufreq-dvfs-port">RK3588：vendor CPUFreq/DVFS 事务移植</ChapterLink>
  <ChapterLink num="58" href="58-2026-08-15-rk3588-wifi-rtl8723du-rtw88-bringup">RK3588：WiFi RTL8723DU→rtw88 移植全记录</ChapterLink>
  <ChapterLink num="59" href="59-2026-08-24-rk3568-qemu-sim-m0-day0">RK3568：QEMU 模拟研究线立项 + M0 Day 0 绿灯</ChapterLink>
  <ChapterLink num="60" href="60-2026-08-25-rk3568-lite-qemu-machine-first-boot">RK3568：rk3568-lite 机器首启，4 核跑到 shell</ChapterLink>
  <ChapterLink num="61" href="61-2026-08-25-rk3568-lite-virtio-rootfs-direct-boot">RK3568：virtio 存储 + rootfs 直启</ChapterLink>
  <ChapterLink num="62" href="62-2026-08-25-rk3568-real-dtb-cru-pmu-shadow">RK3568：真板 DTS 直启，CRU/PMU 影子模型</ChapterLink>
  <ChapterLink num="63" href="63-2026-08-25-rk3568-pmu-state-machine-i2c-nack-3s8-boot">RK3568：推干净战役，真 DTS 启动 90s→3.8s</ChapterLink>
  <ChapterLink num="64" href="64-2026-08-25-rk3568-uboot-proper-relay">RK3568：U-Boot 拉起 + booti 接力内核</ChapterLink>
  <ChapterLink num="65" href="65-2026-08-25-rk3568-sim-assets-python-port">RK3568：sim 资产 Python 化，Windows 一等公民</ChapterLink>
  <ChapterLink num="66" href="66-2026-08-26-rk3568-bootm-fit-relay">RK3568：bootm 起 forge FIT，真板同款最后一接力</ChapterLink>
  <ChapterLink num="67" href="67-2026-08-26-rk3588-lite-heterogeneous-ubuntu">RK3588：首台异构仿真机 + Ubuntu 真根直启</ChapterLink>
  <ChapterLink num="68" href="68-2026-08-26-rk3588-real-dtb-full-port">RK3588：真板 DTS 完全平移</ChapterLink>
  <ChapterLink num="69" href="69-2026-08-27-rk3588-real-dtb-ubuntu-merge">RK3588：真板 DTS + Ubuntu 真根合体</ChapterLink>
  <ChapterLink num="70" href="70-2026-08-27-rk3588-systemd-ubuntu-login">RK3588：systemd 上机，仿真里 Ubuntu 完整开机</ChapterLink>
  <ChapterLink num="71" href="71-2026-08-28-vop2-campaign-power-domain-cascade">RK3588：VOP2 战役一，电源域级联 + PrimeCell ID</ChapterLink>
  <ChapterLink num="72" href="72-2026-08-28-vop2-campaign2-drm-initialized">RK3588：VOP2 战役二，DRM 管线在仿真里成立</ChapterLink>
  <ChapterLink num="73" href="73-2026-08-28-vop2-campaign3-kms-userspace">RK3588：VOP2 战役三，KMS 用户态解放 + gdm 上机</ChapterLink>
  <ChapterLink num="74" href="74-2026-08-29-vop2-campaign4-desktop-lights">RK3588：VOP2 战役四，GNOME 桌面点亮 + 冷启动地板</ChapterLink>
  <ChapterLink num="75" href="75-2026-08-29-virtio-gpu-retreat-discipline">RK3588：virtio-gpu 探路撤退 + 研究线纪律定音</ChapterLink>
  <ChapterLink num="76" href="76-2026-08-29-mali-csf-emulation-feasibility">RK3588：Mali CSF 仿真预研（外部报告）</ChapterLink>
  <ChapterLink num="77" href="77-2026-08-29-same-dtb-cmdline-virtio-desktop">RK3588：同 DTB 的 cmdline virtio 桌面路径</ChapterLink>
  <ChapterLink num="78" href="78-2026-08-30-virgl-desktop-host-gl-blocked">RK3588：virgl 桌面加演，宿主 GL 四路验尸 + dxg 根因</ChapterLink>
  <ChapterLink num="79" href="79-2026-08-30-gt911-touch-i2c-campaign">RK3588：GT911 触摸真路径战役，i2c/gpio 影子成军</ChapterLink>
  <ChapterLink num="80" href="80-2026-08-30-real-panel-desktop">RK3588：真面板桌面，VOP2→DSI 全真管线贯通</ChapterLink>
  <ChapterLink num="81" href="81-2026-08-30-vmstate-snapshot">RK3588：vmstate 快照，9.2s 回桌面 + 迟发 hardlockup 挂账</ChapterLink>
  <ChapterLink num="82" href="82-2026-08-31-panthor-m0-scmi-agent">RK3588：panthor 战役，SCMI agent + SMCCC 根因 + GPU 影子假 MCU 直取 M0</ChapterLink>
  <ChapterLink num="83" href="83-2026-09-02-panthor-m1-campaign">RK3588：panthor M1，内核侧全通（CSG/CS fixture），mesa cs_builder 崩点取证</ChapterLink>
</ChapterNav>
