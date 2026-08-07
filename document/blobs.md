# 闭源固件清单（诚实、非纯洁主义）

rk-forge 主线优先、blob 最小化，但**不 blob 纯洁主义**：当前绕不开的闭源固件先用、在这里文档化、并追踪消除路径。本文件是 **RK3506B** 的闭源固件清单(当前最完整的一块);RK3568/RK3588 的板级 blob(BL31、mali_csffw 等)见各自 [sdk-diff](sdk-diff.md) 的残留表——完整图景三块合看。

## 为什么暂时纯洁不了

Rockchip 启动需要在任何开源代码跑起来之前先初始化 DDR。这段初始化藏在 Rockchip 闭源的 TPL/SPL blob（`rkbin`）里。截至 2026 年（FOSDEM 2026），RK3506 还没有完全开源的 DDR-init 替代，所以 `rkbin` 是**硬依赖**。

除此之外——Linux 内核、U-Boot proper、设备树——**全是开源主线**。

## 当前闭源 blob

| Blob | 来源 | 作用 | 可替代？ |
|---|---|---|---|
| RK3506 DDR bin（`bin/rk35/*ddr*`） | github.com/rockchip-linux/rkbin | U-Boot 之前初始化 DRAM | **否**（2026）——RK3506 尚无开源 DDR init |
| TPL/SPL loader 阶段 | rkbin | 早期引导，喂给 U-Boot proper | 部分——U-Boot proper 开源；pre-U-Boot 阶段不开源 |

## rk-forge 怎么管理它

- `third_party/rkbin/` 是公开仓 `github.com/rockchip-linux/rkbin` 的 **pinned 子模块**（commit `ecb4fcb`），是 loader（[scripts/pack-loader.sh](../scripts/pack-loader.sh)）和 uboot FIT 的 tee（[scripts/pack-fit.sh](../scripts/pack-fit.sh)）的**默认且唯一 blob 源**——一条全公开、内部自洽的 loader 链（DDR v1.06 + usbplug v1.03 + SPL v1.12 + tee v2.40），**零** vendor-sdk 依赖，已板上验证启动。
- [sdk-diff.md](sdk-diff.md) 把 `rkbin` 报告为 vendor BSP 与主线移植对比后的残留——即*还剩多少闭源固件*。
- 目标（远期）：追踪 / 贡献开源 DDR-init，让这张表缩水。更新先落到这里。
- **不要在 `pack-loader.sh` 与 `pack-fit.sh` 之间混用 blob 源**——SPL ↔ tee 由 hash 配对验证，混用（如 ATK SPL 配公开 tee）会触发 "optee Bad hash"。

## NAND 打包：闭源二进制（非 blob，但也不开源）

"源码 → 可烧 update.img" 的管线现在只调用**一个**精简的 Rockchip ELF（`boot_merger`，打 loader idblock）；另外两个已被 forge 的 Python 打包器取代：

| 工具 | 角色 | 可替代？ |
|---|---|---|
| `boot_merger` | 把 DDR+usbplug+SPL blob 包进 RK idblock（loader） | 部分——blob 是硬依赖；packer 在某些 rkbin 树里有开源重实现，但无干净 drop-in |
| ~~`afptool`~~ | ~~打 RKAF 容器~~ | **已取代**（2026-06-18）→ [scripts/rkfw-pack.py](../scripts/rkfw-pack.py)（格式从 vendor 产物逆向） |
| ~~`rkImageMaker`~~ | ~~包 RKFW 头 + loader~~ | **已取代**——`rkfw-pack.py` 一个工具同时打 RKAF + RKFW |

FIT 打包器 `mkimage` 是**开源主线**，forge 用 `third_party/src/uboot/tools/mkimage`（2026.07-rc4），不用 vendor 2017.09 那份。

### loader 字节差（诚实的边）

`pack-loader.sh` 用 `boot_merger` 从公开子模块复刻 loader（DDR v1.06 + usbplug v1.03 + SPL v1.12，281024 B）。它与 ATK 出厂的 `rk3506-vendor-loader.bin`（270784 B）**非字节一致**：`boot_merger` 内嵌构建时间戳、idblock 布局略有不同（~6 KB）。公开复刻 loader 的板上启动已验证；出厂 loader 留作回归基线。

## 许可

`rkbin` 内容是**不可再分发的专有 Rockchip 固件**。**不要**把 blob 文件拷进本仓库，仅通过 pinned 子模块引用。
