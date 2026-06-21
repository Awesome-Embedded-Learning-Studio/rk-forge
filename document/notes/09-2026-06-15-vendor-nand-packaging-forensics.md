# 现状调查:vendor 怎么产一个能 boot 的 NAND(取证 + 可替代性裁决)

> 承 [08](08-2026-06-15-replace-sdk-nand-packaging.md) 的"建议第一步"。**本篇是取证结论,不是实现**。
> 方法:把 vendor 真实镜像 `rk3506b_update_ubi_squashfs.img` 用 vendor 自带工具逐层 unpack,对照 vendor build.sh 的 `mk-*.sh` 钩子,逐块标注"vendor 工具 / 我们的输入 / 可替代性"。
> 一句话:**从源码到 update.img 的链路,真正卡我们的只有 3 个 vendor 工具——mkimage(已有主线替代)、boot_merger(打包 rkbin blob,留)、afptool+rkImageMaker(产 update.img,待裁决)**。

---

## 一、方法论(可复现)

```bash
# vendor 镜像逐层剥开(实证,非推测)
TOOLS=third_party/vendor-sdk/tools/linux/Linux_Pack_Firmware/rockdev
IMG=/mnt/d/DownloadFromInternet/rk3506b_update_ubi_squashfs.img
$TOOLS/rkImageMaker -unpack "$IMG" out/        # 脱 RKFW 外壳 → boot.bin(loader) + firmware.img(RKAF)
$TOOLS/afptool      -unpack out/firmware.img out/   # 脱 RKAF → package-file + 各分区 .img
```
对照读取:`mk-loader.sh` `mk-fitimage.sh` `mk-image.sh` `mk-firmware.sh` `mk-updateimg.sh` + `rkbin/RKBOOT/RK3506BMINIALL.ini` + `rockdev/rk3506-{package-file,mkupdate.sh}`。

---

## 二、完整打包管线(补全 [08] 的表)

vendor 的 NAND 镜像由 **5 个阶段** 产出。下表把每块"当前怎么来 / 工具 / 我们的输入 / 可替代性"全标清:

| 阶段 | vendor 钩子 | vendor 工具 | 我们的输入 | 产物 | 可替代性裁决 |
|---|---|---|---|---|---|
| **① loader / idblock** | `mk-loader.sh`(→`u-boot/make.sh --idblock`) | `rkbin/tools/boot_merger` + `RKBOOT/RK3506BMINIALL.ini` | **rkbin blob**(DDR `rk3506b_ddr_750MHz_v1.06.bin` + usbplug `rk3506_usbplug_v1.02.bin` + vendor SPL `rk3506_spl_v1.11.bin`) | `MiniLoaderAll.bin`(= loader, 270784 B) | **留**(boot_merger 只是 blob 打包器,blob 是硬依赖,见 [[mainline-uboot-bringup-state]] 方案 A/B)。forge 脚本直接调 boot_merger 复现,**无需人工** |
| **② uboot FIT** | (loader 阶段内) | `rkbin/tools/mkimage -E` | u-boot-nodtb + tee + dtb | `uboot.img`(FIT, 4MB 分区) | **换主线 mkimage**(`third_party/explore/uboot/tools/mkimage`,已编)。格式级兼容已证(见 §五) |
| **③ boot FIT** | `mk-fitimage.sh` | `rkbin/tools/mkimage -E -p 0x800` | zImage + dtb + ramdisk(+ resource) | `boot.img`(FIT) | **换主线 mkimage**(同上,`-E -p 0x800` 主线全支持) |
| **④ rootfs** | `mk-rootfs.sh` → `mk-image.sh` | `mkfs.ubifs` + `ubinize`(mtd-utils)/ `mksquashfs`(squashfs-tools) | buildroot rootfs 目录 | `rootfs.img`(UBI+squashfs, ~101.6MB) | **装开源工具**(mtd-utils + squashfs-tools 全开源,系统现无)。这是真 rootfs 阶段的事 |
| **⑤ 组装** | `mk-firmware.sh` | bash(symlink + 大小校验) | parameter.txt + ①②③④ 各 .img | `rockdev/`(目录) | **forge bash 脚本**(trivial,照搬校验逻辑) |
| **⑥ update.img** | `mk-updateimg.sh` | `afptool -pack` + `rkImageMaker` | rockdev/ 全部 | `update.img`(RKFW, 144MB) | **裁决点**(见 §七):留 vendor packer 产 update.img,或弃 update.img 改 rkdeveloptool 直写 |

> 注:`mk-image.sh` 是通用文件系统镜像工具(ext4/vfat/ntfs/btrfs/f2fs/**ubi/ubifs/squashfs/erofs/jffs2**),UBI 路径 = `mkfs.ubifs`(造 ubifs)→ `ubinize`(包成 UBI 镜像),页大小 2KB / 块大小 128KB(`RK_UBI_PAGE_SIZE`/`RK_UBI_BLOCK_SIZE` 可配)。

---

## 三、update.img 实证结构图(剥出来的真实布局)

```
update.img  (144 880 202 B,  magic "RKFW" @0x0)
│
├── RKFW 头           ← rkImageMaker 套的外壳(chip-tag "RK3506", -os_type:androidos)
├── boot.bin          ← = MiniLoaderAll.bin(270 784 B),rkImageMaker 抽出
│                       DDR + usbplug + vendor SPL,写 NAND 的 0x0~boot 区
└── firmware.img      ← afptool 容器(magic "RKAF", 144 609 284 B)
    │   (RKAF 内部按 0x800 对齐排列,package-file 是清单)
    ├── package-file     @0x800     清单(221 B)
    ├── parameter.txt    @0x1000    分区表(453 B)
    ├── MiniLoaderAll.bin@0x1800    loader 副本(270 784 B)
    ├── uboot.img        @0x44000   (4 194 304 B = 4MB)        ← FIT
    ├── misc.img         @0x444000  (49 152 B)
    ├── recovery.img     @0x450000  (14 368 768 B ≈ 13.7MB)   ← FIT(ramboot)
    ├── boot.img         @0x1204000 (6 179 328 B ≈ 5.9MB)     ← FIT(kernel)
    ├── rootfs.img       @0x17E9000 (106 430 464 B ≈ 101.6MB) ← UBI+squashfs
    └── userdata.img     @0x7D69000 (13 107 200 B ≈ 12.5MB)
```

**关键:产 update.img 就两步**(见 `rockdev/rk3506-mkupdate.sh`):
```bash
afptool    -pack ./ Image/update.img                         # ./ = rockdev/,产 RKAF(firmware.img)
rkImageMaker -RK3506 Image/MiniLoaderAll.bin Image/update.img update.img -os_type:androidos
```
`afptool` 与 `rkImageMaker` 均为 **stripped 静态 x86-64 ELF,vendor 只给二进制无源码**(源只在 windows 的 `RKImageMaker_20230109.zip`,afptool 无开源对应)。

---

## 四、RK parameter 格式(扇区约定)

`parameter-nand-aes.txt` 的 `CMDLINE:mtdparts=` 就是分区表,**单位 = 512B 扇区**(RK 约定):
```
mtdparts=:
  0x00002000@0x00002000(uboot)        ← size@offset;  0x2000扇=4MB @ 4MB
  0x00000800@0x00004000(misc)         ← 1MB @ 8MB
  0x00000200@0x00004800(vnvm)         ← 256KB
  0x00007000@0x00004A00(recovery)     ← 14MB
  0x00008000@0x0000BA00(boot)         ← 16MB @ ~24MB   (我们改大的,见下)
  0x00057000@0x00013A00(rootfs)       ← ~172MB
  -@0x0006AA00(userdata:grow)         ← 剩余全给 userdata
```
- **0x0~0x2000(前 4MB)**:不属于任何分区 = idblock(loader)+ parameter 的存放区(RKDevTool "Loader"+parameter 字段写的)。
- `TYPE: GPT`、`MAGIC: 0x5041524B`("PARK")、`CHECK_MASK: 0x80` 是 RK parameter 头固定字段。
- **我们 vs vendor 的差异(已验证合理)**:vendor 原始是 `boot=0x5000(10MB)@0xBA00, rootfs=0x5A000@0x10A00`;我们改成 `boot=0x8000(16MB)@0xBA00, rootfs=0x57000@0x13A00`。原因:主线 kernel.itb(**12.4MB**)比 vendor boot.img(5.9MB)大,放不进 10MB → 扩 boot 到 16MB,rootfs offset 顺移。**这是 forge 有意改的,非照搬**。

---

## 五、关键发现(影响设计)

1. **主线 mkimage 可直接替代 vendor mkimage**(格式级已证):
   - 主线 `mkimage 2026.07-rc4` 同时支持 `-E`(external data)与 `-p addr`(align),与 vendor `mk-fitimage.sh` 用法完全一致。
   - **双向兼容**:主线 mkimage 能完美 `mkimage -l` 解析 vendor 的 `uboot.img`/`boot.img`(节点结构、hash、config 全读出)→ FIT 格式标准化(libfdt),vendor SPL 的 FIT 解析器吃标准 FIT。
   - 我们的 `rk3506-mainline.its` 节点结构 = vendor uboot.img 的字节级复刻(uboot@0x800000 / optee@0x1000 / fdt / conf),唯一改动是 uboot load 改 0x800000(主线 CONFIG_TEXT_BASE)。
   - ⚠ **待板级验证**:主线 mkimage 打出的 FIT,bootrom→vendor SPL→主线 U-Boot 这条链是否字节级可 boot(目前我们的 itb 是用 vendor mkimage 打的)。风险低,需实板回归。

2. **loader 验签默认不强制**:vendor `boot.img` 带 `sha256,rsa2048:dev` 签名,但我们**未签名**的 boot.img 照样 boot 到 shell → loader 默认不验签。`mk-fitimage.sh` 也只在 `RK_SECURITY` 时才签名(且会删 `uboot-ignore` 节点)。→ **forge 不开 RK_SECURITY,签名链整条免掉**。

3. **vendor boot.img 多一个 `resource` 节点**(RK 多文件镜像,logo/开机图),我们的 kernel.its 没有,仍能 boot → **非必需**,后续要开机图再补。

4. **loader 是纯 rkbin blob 拼装**(`RK3506BMINIALL.ini` 证实):boot_merger 只是把 DDR+usbplug+SPL 三块 blob 按 IDB 格式包起来。**forge 复现 loader = 调 boot_merger + 同 ini + 同 blob**,零人工、零改 blob。短期不可消除(DDR 自研是远期,见 sdk-diff residue)。

---

## 六、工具盘点(vendor vs 主线)

| 工具 | 来源 | 性质 | forge 裁决 |
|---|---|---|---|
| `mkimage` | vendor `rkbin/tools` & `u-boot/tools`(2017.09);主线 `explore/uboot/tools/mkimage`(2026.07) | 打 FIT | **主线**(已编,兼容已证) |
| `boot_merger` | vendor `rkbin/tools` | 打 idblock(包 blob) | **留 vendor**(blob 硬依赖,记 BLOBS.md) |
| `afptool` | vendor `tools/linux/Linux_Pack_Firmware/rockdev`(stripped,无源码) | 打 RKAF(产 update.img 内层) | **裁决点** |
| `rkImageMaker` | 同上(stripped) | 套 RKFW 头(产 update.img 外层) | **裁决点** |
| `mkfs.ubifs`/`ubinize` | mtd-utils(开源) | UBI rootfs | **装**(系统现无) |
| `mksquashfs` | squashfs-tools(开源) | squashfs rootfs | **装** |
| `dtc` | 系统 `/usr/bin/dtc` | 编 DT | **已有** |
| `rkdeveloptool` | Rockchip 开源(GitHub) | Linux USB 烧写(替代 Windows RKDevTool) | **装 + 板级验证**(见 §七) |

---

## 七、设计抉择:update.img / 烧录层怎么夺回主线(待用户定夺)

"摆脱 Windows RKDevTool + 手动 cp"有两条路,**核心未知 = rkdeveloptool 能不能烧 RK3506B 的 SPI-NAND**(理论上能:rkdeveloptool 的 `db MiniLoaderAll.bin` 把 loader 下进 RAM,后续 NAND 读写**全由 loader blob 干**,与 RKDevTool 同协议;但需实板验证)。

### 方案 A(推荐,最低风险):vendor packer 产 update.img + rkdeveloptool Linux 烧
- 产 update.img 仍用 vendor `afptool`+`rkImageMaker`(它们是"打包器",与 boot_merger 同性质,非 blob);
- 烧写改 Linux `rkdeveloptool uf update.img`(或 RKDevTool 兜底),彻底去 Windows + 手动 cp;
- **板无关可验证里程碑**:forge 脚本能从干净源码产一个**结构合法**的 update.img(用 rkImageMaker -unpack + afptool -unpack 回程自检),无需板子。

### 方案 B(最 mainline):弃 update.img,rkdeveloptool 直写各分区
- `rkdeveloptool db loader.bin` 下 loader → 逐分区 `rkdeveloptool wl <扇区> <part.img>`,完全不碰 afptool/rkImageMaker;
- 彻底去 vendor 打包工具,但**无单一可烧产物**(每次烧 = 板子进 maskrom + 跑脚本),且 rkdeveloptool NAND 支持需板级验证。

### 方案 C(远期):找/编 afptool + rkImageMaker 的开源重实现
- 有社区 reimplement(rkflashtool 系),但 yak-shave,低优先。

**我的推荐**:**先 A,后 B**。A 用最低风险立刻干掉 Windows + 手动 cp 并拿到可复现产物;B 作为"去最后一个 vendor 打包器"的收尾,待 rkdeveloptool NAND 板级验证通过再上。loader(blob)、boot_merger 短期都留,只文档化进 BLOBS.md——与 [[next-phase-nand-packaging-and-buildroot]] 的"取代 = 取代除 loader blob 外的一切"一致。

---

## 八、板无关的第一里程碑(无需硬件即可推进 + 验证)

把"主线 mkimage + boot_merger 产 loader + forge 脚本组装"做成可复现,产物落 `third_party/bringup/out/`,并**回程自检**:
1. `scripts/` 加 bash:`pack-loader.sh`(调 boot_merger + RK3506BMINIALL.ini)、`pack-fit.sh`(主线 mkimage 打 uboot/boot FIT)、`assemble-update.sh`(afptool+rkImageMaker 产 update.img);
2. 产物用 `rkImageMaker -unpack` + `afptool -unpack` 回剥,确认结构合法、各分区在位;
3. 与 vendor 镜像对照(同结构、我们内容)→ **管线 owned 的板无关证据**。

板级回归(主线 mkimage 打的 FIT 是否实 boot、rkdeveloptool 是否能烧 NAND)作为第二步,由用户在板上验。

---

## 相关

[[next-phase-nand-packaging-and-buildroot]] [[kernel-port-state]] [[vendor-build-pipeline-for-forge]] [[uboot-build-flash-commands]] [08](08-2026-06-15-replace-sdk-nand-packaging.md) [07](07-2026-06-15-milestone-mainline-linux-boots.md) [01](01-2026-06-14-vendor-uboot-build-flow.md) [04](04-2026-06-14-mainline-uboot-via-vendor-spl.md)
