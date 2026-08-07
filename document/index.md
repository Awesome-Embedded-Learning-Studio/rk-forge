---
layout: home

hero:
  name: "RK-Forge"
  text: "每板全栈的 Rockchip Linux 教学 + 工程"
  tagline: 在一块 RK 板上从驱动 bring-up 起步、全栈通往 Qt / 媒体 / AI,不换板;主线优先、真板诚实,追全开源
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
    title: 每板全栈,不换板
    details: 三块板都是奔向全栈的车道——你这块板硬件能干的领域,都能在这块板上学完(目前已交付到 GPU 显示;Qt / 媒体 / AI 在推进),不用为了学新东西换板
    link: /tutorial/
  - icon: 🧭
    title: 追全开源
    details: 逐层消灭闭源 blob、走向全开源;主线优先、真板诚实是底色,blob 是靶子不是妥协
    link: /sdk-diff
  - icon: 📋
    title: 诚实的差距报告
    details: 逐子系统告诉你 vendor BSP 有什么 / 主线有什么 / 差什么 / 还能不能 boot,绝不藏着;每项能力挂真板证据,状态不刷绿
    link: /sdk-diff
  - icon: 🧩
    title: 有序补丁库
    details: quilt 风格 series,git am 落真实 commit、可 bisect、失败原子回滚——修掉"只打最后一个补丁"的老毛病
    link: /tutorial/boot/
  - icon: 🛠️
    title: forge 编排器
    details: 把 kernel / uboot / rootfs 一长串命令收成一个 setup→build→pack→assemble 编排器,DAG + 增量跳过
    link: /tutorial/forge/
  - icon: 📖
    title: 全栈教程
    details: 从 bring-up 起步的可复现路径(通往 Qt / 媒体 / AI,上层为 roadmap),每章配真实板上抓取,绝不合成;按"通用方法 + 每板证据页"两层写
    link: /tutorial/
  - icon: 🌐
    title: OpenWrt profile
    details: "--rootfs=openwrt 一键切到真 OpenWrt(opkg / LuCI / kmod),OpenWrt 自建 musl kernel+rootfs、vermagic 天然匹配,NAND + SD 双路板上验证"
    link: https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/blob/main/board/aes/openwrt/README.md
  - icon: 💾
    title: NAND + SD 双启动
    details: SPI-NAND(UBIFS)+ SD 卡(RKFW)两条启动路都板上验证通过,含 loader 弱写 saga 的根治解
    link: /tutorial/sd-boot/
---
