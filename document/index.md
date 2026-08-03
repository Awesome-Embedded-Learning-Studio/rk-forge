---
layout: home

hero:
  name: "RK-Forge"
  text: "Rockchip 三板主线开发工作空间"
  tagline: 面向 Rockchip RK3506B / RK3568 / RK3588，从工具链到 rootfs、外设、显示/GPU 的完整主线学习路径——别人卖成品镜像，我们卖菜谱 + 灶 + 带你做饭的书
  image:
    src: /Awesome-Embedded.png
    alt: RK-Forge Logo
  actions:
    - theme: brand
      text: 快速开始
      link: /tutorial/boot/
    - theme: alt
      text: 教程目录
      link: /tutorial/
    - theme: alt
      text: GitHub
      link: https://github.com/Awesome-Embedded-Learning-Studio/rk-forge

features:
  - icon: 🚀
    title: 主线优先
    details: 主线 Linux 7.1 + U-Boot 2026.07-rc4，紧跟上游；每块板都坍缩成 rkbin + 一块板级设备树
    link: /tutorial/boot/
  - icon: 🧩
    title: 有序补丁库
    details: quilt 风格 series，git am 落真实 commit、可 bisect、失败原子回滚——修掉"只打最后一个补丁"的老毛病
    link: /tutorial/boot/
  - icon: 📋
    title: 诚实的差距报告
    details: 逐子系统告诉你 vendor BSP 有什么 / 主线有什么 / 差什么 / 还能不能 boot，绝不藏着
    link: /sdk-diff
  - icon: 📖
    title: 0→1 教程
    details: 从空机器到 RK3506B 主线启动到 UART 登录的可复现路径，每章配真实板上抓取，绝不合成；RK3568/RK3588 教程建设中
    link: /tutorial/
  - icon: 🛠️
    title: forge 编排器
    details: 把 kernel / uboot / rootfs 一长串命令收成一个 setup→build→pack→assemble 编排器，DAG + 增量跳过
    link: /tutorial/forge/
  - icon: 🌐
    title: OpenWrt profile
    details: "--rootfs=openwrt 一键切到真 OpenWrt（opkg / LuCI / kmod），OpenWrt 自建 musl kernel+rootfs、vermagic 天然匹配，NAND + SD 双路板上验证"
    link: https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/blob/main/board/aes/openwrt/README.md
  - icon: 💾
    title: 双启动路径
    details: SPI-NAND（UBIFS）+ SD 卡（RKFW）两条启动路都板上验证通过，含 loader 弱写 saga 的根治解
    link: /tutorial/sd-boot/
---
