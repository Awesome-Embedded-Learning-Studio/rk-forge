# 20 — mkimage saga：去 vendor mkimage 的探索 + 交接（2026-06-19）

> **✅ SOLVED（2026-06-19，方向 b 落地）**：`scripts/fit-pack.py` 纯 Python 手搓 FIT `-E`
> packer，**复现 vendor mkimage 2017.09（uboot，Mode A）+ 主线 mkimage -p 0x800（kernel，Mode B）
> 的两种外部布局**，绕开 mkimage/dtc/U-Boot build 整套（D 模式，同 `rkfw-pack.py` 替
> afptool/rkImageMaker）。`pack-fit.sh` **三个 FIT 全切 fit-pack.py**（uboot Mode A + boot/boot-nand
> Mode B），打包器统一，**vendor-sdk mkimage 依赖彻底去掉（P4 收官）+ 主线 mkimage 打包耦合也去（Phase 2）**。
>
> **逆向出的格式契约**（写进 fit-pack.py，是 SPL 兼容的硬约束）：
> - 文件 = FDT blob（`fdt_totalsize`=1220）+ `[1220, 0x600)` 残留 gap + external data @`FIT_ALIGN(fdt_totalsize)`=0x600 + 末尾。
> - external 每 blob 占 `FIT_ALIGN(len)`（FIT_ALIGN=0x200，源 `image.h:958`，`IMAGE_ALIGN_SIZE`=0x200），data-offset 累计 buf_ptr（`fit_image.c:524` `buf_ptr += FIT_ALIGN(len)`）。
> - **根 `/totalsize` prop** = mkimage 的 host 簿记值（inline-FIT 大小，`fit_image.c:103` `fit_set_totalsize(ptr,0,sbuf.st_size)`）；**Rockchip SPL 用它算加载量** `ceil(/totalsize/bl_len)*bl_len`（`spl_boot_image.c:293` `spl_load_fit`）→ 必须 ≥ 文件让全量加载。fit-pack.py 设 `/totalsize`=file_size（任何 bl_len 都加载全文件）。
> - `/timestamp`、`/totalsize` 值 + `[0x4c4,0x600)` 残留 gap（fdt_pack 前 FDT 残骸，`ftruncate` 不清零）= **SPL 不读的 host 产物**。
>
> **验证**（离线，不需板）：① `fit-pack.py selftest` 对比 vendor out/uboot.img——FDT 树（除 `/timestamp`+`/totalsize` 值）+ external blobs（同 offset 同 sha256）全等 → **PASS**；raw diff 仅 128B，全在 SPL-irrelevant 区。② `mkimage -l` 解析通过。③ 三 blob hash 与 vendor 逐字一致（uboot `54d12cbf…`、optee `e2a712a5…`、fdt `8e3f2ac7…`），且 public rkbin tee v2.40=124360B == vendor optee blob（公开链自洽）。**✅板上通过（2026-06-19）**：烧 update-p4-fitpack.img，fit-pack.py Mode A uboot.img 过 SPL 启动到 kernel。
>
> **非 byte-identical 的诚实说明**：vendor 的残留 gap + host 时间戳/totalsize 无法在不模拟 libfdt `fdt_pack` 的前提下复现；但这些 SPL 都不读，零功能影响。fit-pack.py 输出**结构+哈希全等**、布局语义全等。
>
> **Phase 2 ✅（2026-06-19，板上 uboot 通过后即做）**：boot.img/boot-nand.img 也迁到 fit-pack.py。
> 逆向主线 mkimage `-p 0x800`（= `external_offset`，`fit_image.c:735`）→ **Mode B**：`data-position`
> （绝对）+ 连续 blob（`buf_ptr += len`，无 FIT_ALIGN）+ external @ 绝对 `external_offset`(0x800) +
> root 仅 `/timestamp`（version/totalsize 是 ATK 私有，主线不加）。fit-pack.py 加 `--external-offset`
> 形参分支；selftest 对两 kernel FIT 全等 PASS（raw diff 仅 timestamp+trailing pad，mainline U-Boot
> bootm 不读）。pack-fit.sh 三 FIT 全归 fit-pack.py，主线 mkimage 仅留 `mkimage -l` 解析校验。
> **✅板上通过（2026-06-19）**：烧 `update-p2-unified-fitpack.img`，fit-pack.py Mode B 的 boot.img
> 过主线 U-Boot bootm，kernel 顺利启动。**Phase 2 闭环；fit-pack.py 全 FIT 唯一打包器，离线+板上双证。**

---

> **立身**：forge 的价值 = 不依赖 ATK vendor-sdk（gitignored 正点原子 BSP）。`pack-fit.sh` 用 vendor-sdk 预编译的 mkimage 打 uboot.img——只要它还靠 vendor-sdk，别人一句"我有 SDK 为啥用你的"就把仓库立身废了。**mkimage 必须自己解决**（不依赖 vendor-sdk）。这是 P4 的硬约束。

## 背景
P4 = 去 vendor mkimage。vendor mkimage（`vendor-sdk/u-boot/tools/mkimage`，2017.09 ATK fork `g26c8833`）打 uboot.img（FIT `-E` external-data），rkbin SPL 只认它的 `-E` 布局（mainline mkimage `-E` 被 SPL 拒，optee Bad hash，2026-06-18 实测）。

## 探索全貌（按时间）
1. **vendor mkimage 能编 + SPL 兼容**：vendor-sdk/u-boot（ATK fork）`make sandbox_defconfig && make olddefconfig && touch include/config/auto.conf && make tools-only` 编出 mkimage（211208 B），md5 `e57dfce5...` == vendor 预编译。打的 uboot.img 609280 B，和 vendor 预编译只差 3 字节 FIT timestamp。SPL 接受（板上跑过无数遍的 vendor 版同 `-E` 布局 + 同 hash）。
2. **公开 release mkimage `/incbin/` fail**：`rockchip-linux/u-boot` release branch（`g524f26463d`，公开 2017.09）编的 mkimage，打 rk3506 ITS 时 `FATAL ERROR: Couldn't open "uboot-nodtb.bin"`——blob 明明在 cwd/ITS 同目录。
3. **mainline mkimage**（2026.07）：`/incbin/` 同样 fail + `-E` 被 SPL 拒。
4. **`/incbin/` 矛盾（核心未解）**：vendor + release mkimage **都** `system("dtc -I dts -O dtb -p 500 datafile")`，同一个系统 dtc 1.7.0，同 cmd——但 vendor 成功、release fail。差异只在 mkimage binary（`g26c8833` vs `g524f26463d`）。dtc 直接（cd W + ITS + blobs 同目录）跑最小 `/incbin/`（`test.bin`）**工作**，但 rk3506 ITS（嵌套 images/uboot + hash）`/incbin/` **fail**——然而 vendor mkimage（system dtc）打 rk3506 ITS 成功。根因未定位。
5. **`/incbin/` fix 没定位**：dtc-lexer.l（删 `YYLTYPE yylloc`）/ livetree.c（phandle `1`→`0x10000000`）/ source.c（无 diff）/ fit_image.c（加 `fdt_shrink_to_minimum` + `fit_set_totalsize/version`）的 ATK diff 都**不是** `/incbin/` fix。
6. **手动 gcc 编 mkimage（拷源）= 依赖地狱**：拷 ~50 .c + include + scripts/dtc/libfdt + arch/arm/include 进 forge，gcc 编。fit_image.c `MKIMAGE_DTC undeclared` → 拷 generated `autoconf.h`（`CONFIG_MKIMAGE_DTC_PATH "dtc"`）→ mkimage.c `fdt_support.h` 更多依赖 → … 整条 U-Boot build 依赖链。**重造 U-Boot build 系统，不实际**。
7. **track vendor-sdk/u-boot 全树 = 220M**（含 build artifacts + `.repo` git），太大 + ATK 内网来源。
8. **ATK fork 非公开**：vendor-sdk manifest 是 `http://192.168.1.71/RockchipSDK/rk3506_linux6.1_v1.2/manifests`（正点原子内网 IP）。ATK fork `g26c8833` 不在任何公开仓。

## 根因定性
vendor mkimage 的 SPL 兼容靠两样**非公开/重系统**的东西：① ATK fork 的 mkimage/fit_image 私改（正点原子内网）；② U-Boot 完整 build 系统（解 generated autoconf.h 依赖链，手动 gcc 重造不实际）。公开仓 mkimage 既无 ATK 私改、`/incbin/` 又不工作。

**对比 D**（afptool/rkImageMaker → `rkfw-pack.py`）能干净去掉，是因为它们是**纯格式工具、零 build 系统依赖、零闭源验证**。vendor mkimage 和 boot_merger 一样撞 Rockchip/ATK 闭源墙 + 重 build 系统依赖。

## 下一步三方向（用户提的）
- **a. 死磕 patch release**：定位 `/incbin/` fix（dtc 深处，strace vendor vs release mkimage 的 `system(dtc)` 实际差异）+ 提取 ATK `mkimage.c`（`rockchip_copy_image`）/ `fit_image.c`（`fdt_shrink`, `fit_set_totalsize/version`）改动，apply 到公开 release submodule。复杂 + SPL 板验。
- **b. trace + 手搓 Python FIT packer（推荐，D 模式）**：strace vendor mkimage 实际编译（`system(dtc)` cmd + cwd + ITS 预处理），然后 Python 自己实现 FIT `-E` 打包——绕开 mkimage/dtc/U-Boot build 整套。复现 vendor uboot.img 字节（SPL 接受）。像 `rkfw-pack.py`（D）一样，避开 build 系统地狱。FIT = fdt header + external data + per-image sha256 hash，格式可控。
- **c. 对比差异**：strace vendor vs release mkimage 的 `system(dtc)` 调用（cmd/cwd/env）+ binary 字节 diff，定位 `/incbin/` + SPL 差异根因。是 a/b 的前置侦察。

**推荐 b**：a 撞 `/incbin/` 深坑（dtc 内部，未定位）；b 绕开 mkimage/dtc/build 整套（D 模式证明可行），Python 直接生成 FIT `-E`，逆 vendor uboot.img 字节复现。c 是 a/b 的侦察前置。

## 当前可用（✅ 已被 fit-pack.py 取代，见顶部 SOLVED）
~~`scripts/build-vendor-mkimage.sh` 在 vendor-sdk/u-boot 树 `make tools-only` 编 mkimage-2017~~
（脚本已删——其编译配方见上方"探索全貌①"；vendor-sdk 依赖本身就不满足立身）。`pack-fit.sh`
现用 `scripts/fit-pack.py pack` 打 uboot.img，零 vendor-sdk 依赖。

## 关键产物 / 参考
- **`scripts/fit-pack.py`**（✅ 本次产出：纯 Python FIT `-E` packer，替 vendor mkimage。ITS 解析器 + mkimage-faithful DTB 编码器 + selftest）。
- `scripts/pack-fit.sh` uboot.img 段（`python3 "$FIT_PACK" pack …`，已切）。
- `scripts/rkfw-pack.py`（D 模式范本 = 手搓 FIT packer 的设计参考）。
- `third_party/bringup/out/uboot.img`（609280 B；**历史基准** = 逆它的字节定位了 SPL 兼容布局。现已是 fit-pack.py 产出，selftest 对它跑=确定性检查）。
- `third_party/bringup/fit/rk3506-mainline.its`（FIT 源：uboot/optee/fdt + sha256 hash）。

## 手搓 FIT packer 的入门（b 方向）
FIT `-E` = fdt（FIT structure：images{uboot,optee,fdt}+hash + configurations）+ external data（三段 blob，fdt 的 data property 指向 external offset/size）+ per-image sha256。SPL 验 optee 的 sha256（读 fdt hash + external optee data 算 sha256 比对）。Python 复现：① 构 fdt（可用 `libfdt` Python binding 或手写 fdt encoder）；② 拼 external data；③ 写 data property = offset/size；④ 算 sha256 填 hash。逆 `out/uboot.img` 字节对齐验证（像 rkfw-pack.py 对 update.img）。
