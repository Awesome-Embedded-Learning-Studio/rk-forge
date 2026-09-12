# 75 — virtio-gpu 提速探路与撤退：研究线纪律定音（2026-08-29）

> **后续裁决（同日）**：用户重新允许 virtio 路线，但增加不可妥协的边界：真机
> 与仿真必须使用同一份 DTB，禁止 sim overlay 和 QEMU 外设节点注入。本文保留
> 为当时决策的历史记录；现行实现与隔离原则见笔记 77。

> 战役四收官后追问 79s 冷启动地板的出路，提议并搭好了 virtio-gpu 提速实验
> （宿主 GPU 代劳渲染），开工 20 分钟被用户叫停：「咱们不走 virtio 这条路，
> 因为我们要做前人没做过的事情」。本笔记记录这次探路拿到的信息、撤场清单、
> 和定音的纪律——防止未来重复探这条岔路。

## 0. 裁决

**rk3588-lite 模拟线不引入 virtio-gpu / 半假设备来"解决"问题。** 这条线做的是
真 SoC（VOP2/DSI/PMU/iommu）的 QEMU 建模，本身就是没人做过的事；virtio-gpu
是 VM 世界的熟路，一换就绕开被研究对象，实验失去意义。llvmpipe×TCG 的 79s
冷启动地板是真 SoC 路线的结构性代价，**认了**。sim 内提速只许走「把真硬件
行为建得更对」：下一役 = 四影子 vmstate → 快照秒回桌面（见笔记 74 欠账 1）。

## 1. 探路 20 分钟拿到的信息（撤了也值钱）

- **机器侧零成本可用**：rk3588-lite 有 4 个 virtio-mmio 槽（0xfea00000+i×0x200，
  SPI 160+i），且 DTB 缺节点时机器自动嫁接（`rk3588_lite_fdt_add_virtio()`，
  四中断 cell 的坑它都处理了）——`-device virtio-gpu-device` 落第二槽即插即用。
  这机制未来若做 virtio-9p（宿主目录挂进 sim 换文件）现成可用。
- **内核侧**：`CONFIG_DRM_VIRTIO_GPU` 默认关，`scripts/config -e` + 老三样重编
  即可（Image 46,643,712 → 46,713,344，差 70KB 就是这个驱动）。
- **QEMU 侧是硬门槛**：本仓 QEMU 没编 virgl（config-host 无 epoxy/virglrenderer），
  要宿主 GPU 得 `libvirglrenderer-dev`+`libgbm-dev`（要 sudo）+ meson 重配重编；
  没装 virtio-gpu-gl 的话 guest 渲染仍是 llvmpipe，提速实验无意义。
- **判活小技巧**（写了个 PPM 色度差判据）：screendump 出的 PPM 按采样点
  max(R,G,B)-min(R,G,B)>40 计数 ≥3 判"桌面彩色"——QEMU 黑屏与文本控制台都是
  消色差的，不会误报。已随 framehunt GPU 模式一起撤掉，思路留档。

## 2. 撤场清单（全部归位，树净）

实验机杀掉；`rk3588-topeet-gpu.dts/.dtb` 删除；framehunt.py checkout 回提交版；
内核 `-d DRM_VIRTIO_GPU` 重编回 46,643,712 字节（战役四终态逐字节同尺寸）；
`git status` 无残留。工作树停在 commit 9cc0606。

## 3. 为什么当时的提议是错的（复盘）

提议时把问题框成了「怎么让 sim 桌面快」——但这条线的问题从来是「怎么把真
RK3588 建对」。virtio-gpu 能赢的是前者，输掉的是后者：换设备 = 研究对象消失。
类似的岔路以后还可能出现（假 IOMMU 直通、假中断兜底、跳过未建模外设），判据
统一：**改动是否让模型更接近真硬件行为**。是，干；不是，哪怕再快也不干。
