---
layout: home

hero:
  name: "RK-FORGE / FIELD MANUAL"
  text: "把一块 Rockchip 板，真正带到主线 Linux"
  tagline: 从上电、引导到驱动与用户空间。命令可复现，结果在真板上验证；成功和失败都留下记录。
  image:
    src: /Awesome-Embedded.png
    alt: RK-Forge Logo
  actions:
    - theme: brand
      text: 从上电开始
      link: /tutorial/boot/
    - theme: alt
      text: 教程目录
      link: /tutorial/
    - theme: alt
      text: GitHub
      link: https://github.com/Awesome-Embedded-Learning-Studio/rk-forge

features:
  - icon: "01"
    title: 每板全栈,不换板
    details: 三块板各自走完从 bring-up 到上层应用的路径。当前已推进到 GPU 显示，Qt、媒体与 AI 持续补齐。
    link: /tutorial/
  - icon: "02"
    title: 追全开源
    details: 主线优先，逐层替换闭源依赖。暂时绕不开的 blob 会被明确标出，而不是藏在脚本里。
    link: /sdk-diff
  - icon: "03"
    title: 诚实的差距报告
    details: 按子系统对照 vendor BSP 与主线：已有能力、缺口、启动状态，以及对应的真板证据。
    link: /sdk-diff
  - icon: "04"
    title: 有序补丁库
    details: quilt 风格 series，git am 落真实 commit；可 bisect，失败时原子回滚。
    link: /tutorial/boot/
  - icon: "05"
    title: forge 编排器
    details: 把 kernel、U-Boot、rootfs 收进 setup → build → pack → assemble 流程，支持 DAG 与增量跳过。
    link: /tutorial/forge/
  - icon: "06"
    title: 全栈教程
    details: 以“通用方法 + 每板证据”组织内容。每章都配真实板上抓取，不用合成日志冒充结果。
    link: /tutorial/
  - icon: "07"
    title: OpenWrt profile
    details: "--rootfs=openwrt 切换到完整 OpenWrt；自建 musl kernel + rootfs，NAND 与 SD 双路验证。"
    link: https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/blob/main/board/aes/openwrt/README.md
  - icon: "08"
    title: NAND + SD 双启动
    details: SPI-NAND（UBIFS）与 SD 卡（RKFW）均通过板上验证，并完整记录 loader 弱写问题的根治过程。
    link: /tutorial/sd-boot/
---
