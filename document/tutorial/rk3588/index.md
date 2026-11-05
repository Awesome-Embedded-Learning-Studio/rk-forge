---
title: RK3588 教程
---

<PageHeader icon="🦾" title="RK3588 主线移植" description="iTOP-RK3588 / topeet 板：从无声 bootloop（板子无限重启）一路移植到 Ubuntu GNOME 桌面与 TFTP+NFS 免烧录迭代" />

RK3588 是咱们整条移植阶梯里最重的一块板——八核 big.LITTLE 大小核、Mali-G610 GPU、NPU 神经网络加速器、VPU 视频编解码单元，Rockchip 把这些全挤进了一颗硅里。它的主线支持很成熟（Collabora 的旗舰），所以咱们在这块板上要对付的不是主线缺驱动这件事，原厂 SDK（芯片原厂 Rockchip 的整套开发包）主线里早就给咱们备好了，真正的考验是咱们把原厂 SDK 整套拔掉、换上主线重新走一遍时，哪些接缝和时机咱们没对齐、板子就起不来。本卷十章咱们按移植顺序啃这些硬骨头，前八章咱们走的是板上主线，最后两章咱们收全卷的尾：

- 原厂 SPL 与 BL31 两级闭源固件基址错配的那场无声 bootloop
- LCD 拖了四版镜像才出图的排查
- GPU 固件必须抢在驱动早期探测（probe）之前就位的时序
- 显示 modeset（切换显示模式）反手楔死网卡的跨子系统冤案
- NPU 与多媒体核：原厂驱动进主线加自研运行时的逐字节对拍
- GPU 用户态：QEMU 里的采样合成研究线，从满负载黑屏到真壁纸上屏

> 诚实地说：咱们已经把这块板 boot 到了 Ubuntu 26.04 GNOME 桌面，GPU、LCD、触摸、WiFi、DVFS 咱们也都在板上点亮过，v7.3.1 内核咱们也靠 TFTP+NFS 免烧录在板上验过一轮。NPU 与多媒体核（RGA3、JPEG、H.264）咱们也验到了逐核并发，NPU 的九个模型跟原厂闭源库对到了逐字节一致。但 LCD 的 VOP2 彻底卡死（hard-lock）修复虽然已经板上收敛，连续冷热启动的稳定性咱们还没验证完，所以涉及显示的章节咱们会标清楚“出图，但不宣称稳定”。最后一章的 GPU 用户态战役跑在 QEMU 模拟机里，产出的是理解材料而非板上的点亮，口径咱们在章内分开写。蓝牙、摄像头这些咱们还留在规划里，等板上数据齐了再补。

<ChapterNav>
  <ChapterLink num="00" href="00_platform">平台与启动链：RK3588，以及拔掉原厂 SDK 之后会断在哪里</ChapterLink>
  <ChapterLink num="01" href="01_uboot">U-Boot 移植：无声 bootloop 与 rockusb Loader 模式</ChapterLink>
  <ChapterLink num="02" href="02_kernel">Linux 内核移植：把原厂 SDK 的设备树翻译成主线语法，一路追到 v7.3.1</ChapterLink>
  <ChapterLink num="03" href="03_lcd">LCD 显示：一块没有主线驱动的屏，和三场连环硬仗</ChapterLink>
  <ChapterLink num="04" href="04_gpu">GPU：Panthor、那颗绕不开的固件，和 GNOME 的第一帧</ChapterLink>
  <ChapterLink num="05" href="05_rootfs">Ubuntu rootfs：从 ubuntu-base 到 GNOME，再打进 eMMC</ChapterLink>
  <ChapterLink num="06" href="06_network">网络启动与免烧录迭代：TFTP+NFS 引擎，和一场显示杀死网卡的冤案</ChapterLink>
  <ChapterLink num="07" href="07_peripherals">外设收尾：WiFi 上桌，DVFS 落地</ChapterLink>
  <ChapterLink num="08" href="08_npu">NPU 收官：原厂驱动进主线，自研运行时逐字节对拍</ChapterLink>
  <ChapterLink num="09" href="09_gpu_userspace">GPU 用户态收官：QEMU 里的采样合成战役</ChapterLink>
</ChapterNav>
