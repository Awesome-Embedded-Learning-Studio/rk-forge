# 37 — RK3568 Android SDK：构建流程解剖（ATK android13，.repo-only tgz）

**2026-07-23**。把 `E:\rk3568src\android13_sdk\android.tgz`（26.5 GB）解到 [reference/rk3568_android/](../../reference/rk3568_android/)，琢磨"RK3568 的安卓怎么编译"。结论：这是**正点原子(ATK) 重新打包的 Rockchip Android 13 多 SoC SDK**，含 RK3568——你这块 ATK-DLRK3568 板的产品配置齐全——但 tgz **只含 `.repo/`、不含工作树**，编译前还多一步 `repo sync -l`。与 [[36]]（RK3568 主线）是对立面：那边主线 kernel 7.1 + binman 自产 loader，这边 vendor kernel 5.10 + rkbin 闭源 blob + vendor u-boot 2017.09。**本次只解剖流程，不真跑构建**（用户选的范围）。关联记忆 `rk3568-migration-status`。

## 一句话定位

这套 SDK 是"vendor Android 世界"的完整自洽闭环——AOSP 源码 + Rockchip vendor kernel/u-boot + 闭源 blob，`repo` 管理。它**自成赛道**，塞不进 forge 的 `setup→build→pack→assemble`（那是主线 Linux 的编排），放 `reference/` 只当**提取池/对照锚**。

## 这是什么（实锤，从 manifest + 产品配置核对）

- **base**：Rockchip 官方 `android-13.0-mid-rkr6`，ATK 重打 tag（`android13-atk-r1*`）。ATK 的 `ATK-Android_SDK_Note.md` 标题写 RK3588 是因为他们旗舰板是 3588，但 SDK 是**多 SoC**：`.repo/projects/device/rockchip/` 下 common / rk3326 / rk3399 / rk3528 / rk3562 / rk356x / rk3588 全在。
- **RK3568 在内**：`device/rockchip/rk356x`（rk356x = RK3566+RK3568），且**你这台板的产品配置齐全**——`ATK_DLRK3568`（`PRODUCT_MODEL := ATK-DLRK3568`，Brand Alientek，eMMC `fe2b0000.dwmmc`，DynamicPartitions，tablet xhdpi density 320，API level 33）。
- **三件套版本**：kernel = **linux 5.10.157**（`kernel-5.10/`），u-boot = vendor **2017.09**（`u-boot/`），blob = `rkbin/`。
- **构建关键 project 的 manifest 修订**（`atk-android13_release.xml`，当前 `manifest.xml` include 它）：

| project (path) | upstream name | revision |
|---|---|---|
| device/rockchip/common | rk/device/rockchip/rksdk | android13-atk-r1.1 |
| device/rockchip/rk356x | rk/device/rockchip/rk3566 | android13-atk-r1 |
| kernel-5.10 | rk/kernel | android13-atk-r1.2 |
| u-boot | rk/u-boot | android13-atk-r1.1 |
| rkbin | rk/rkbin | android13-atk-r1.1 |

## 关键坑：tgz 只有 `.repo/`，没有工作树

解压完（26 G）顶层**只有 `.repo/`**，没有 `build/`、`device/`、`kernel-5.10/`——一个都没。即这个包是"repo 仓库快照"，不是可直接编译的源码树。要看实际文件 / 真编译，两条路：

- **手术式读单文件**（本次用的，零成本）：从 git 对象库直接取，如
  `git --git-dir=.repo/projects/device/rockchip/rk356x.git show android13-atk-r1:AndroidProducts.mk`。
  每个 project 的 ref 就是上表的 revision tag（注意 zsh 下 `${REV}:path` 要花括号，否则 `$REV:A` 被当成参数修饰符转绝对路径）。
- **检出完整工作树**（要编译必须这步）：`cd reference/rk3568_android && repo sync -l`（`-l` = local only，不走网络，对象已在 `.repo/`），再展开 ~60–80 GB。`repo` 工具这台机器有（depot_tools）。

## 怎么编译（两层，已对实物核对）

标准 Rockchip Android 三段式，**你这块板**：

```bash
# 0) 一次性：从本地 .repo 检出工作树（不走网络）
cd reference/rk3568_android
repo sync -l

# 1) AOSP 层：出 system/boot/vendor... 各分区镜像
source build/envsetup.sh
lunch ATK_DLRK3568-userdebug     # 你这台 ATK 板；通用参考板用 rk3568_t-userdebug
make -j$(nproc)

# 2) Rockchip 打包层：拼 loader + 出 update.img
./mkimage.sh                     # 实体在 device/rockchip/common/mkimage.sh，sync 后根目录有 symlink
```

**lunch 目标**（`device/rockchip/rk356x/AndroidProducts.mk` 的 `COMMON_LUNCH_CHOICES`，权威）：
`ATK_DLRK3568-{user,userdebug}`、`rk3568_t-{user,userdebug}`、`rk3566_t(-tgo)-{user,userdebug}`。

**`mkimage.sh` 干了啥**（读了头，不是猜）：它先 `. build/envsetup.sh && setpaths`（所以必须在 lunch 之后跑），用 `get_build_var` 读 `TARGET_PRODUCT` 等，把 `u-boot/uboot.img`、`trust_nand.img`(→`trust.img`)、kernel、`parameter.txt`、`config.cfg` 收进 `rockdev/Image-$TARGET_PRODUCT/`，fakeroot 打包，最终产出可烧的 `update.img`。默认 `TARGET=withoutkernel`（kernel 预编好拷进来）。

## 硬件门槛 + 你的机器够不够

| 要求 | 这台机器 |
|---|---|
| Ubuntu 20.04 | WSL2 Ubuntu ✓ |
| 16 GB RAM 起（全量构建推荐 64 G） | **30 G（偏紧，链接阶段可能 OOM，靠 8 G swap 顶）** |
| 250 GB 盘（源码 + 构建产物） | **898 G ext4 空闲 ✓** |
| 64-bit + Java/ninja 等 AOSP 依赖 | 待装（要编译再 `apt` 一堆） |

**⚠️ 别在 `/mnt/e`（drvfs）上构建 AOSP**——大小写敏感 + 9p 性能会要命。`reference/rk3568_android/` 在 ext4 上 ✓，但要给构建产物留 ~150 GB。

## 一个判断

这套东西**能编**（manifest / 产品配置 / mkimage.sh 都齐全且自洽），但跟你 RK3568 的主线活（[[36]]）是**两个平行宇宙**：主线用 kernel 7.1 + 主线 U-Boot + binman 自产 loader（零 vendor 工具）；Android 用 vendor kernel 5.10 + vendor u-boot + rkbin 闭源 blob。它不进 forge，只当**对照锚 / 提取池**——以后要挖 vendor 的 DT / io-domain / 分区表，或真要出一台 Android 成品，再回来。

## 续：工作树已检出 + 构建接线钉死

后续真把工作树检出了（`repo sync -l`，~105 GB），对着真树把构建流程核实到底：

- **`PRODUCT_KERNEL_VERSION := 5.10`** 在 `device/rockchip/rk356x/BoardConfig.mk`（覆盖 common 默认的 4.19，无版本错配）。板配置：`PRODUCT_UBOOT_CONFIG := rk3568`、`PRODUCT_KERNEL_DTS := rk3568-atk-evb1-ddr4-v10`（与主线 [[36]] 同一块 EVB1-DDR4-V10）。
- **vendor 预期入口是 `device/rockchip/common/build/rockchip/build.sh`**（不是手搓 envsetup/make/mkimage）。它自己 `source envsetup`，按序编 u-boot（`u-boot/make.sh rk3568`）→ kernel（`kernel-5.10/make.sh`，**5.10 强制 clang/LLVM**，用 `prebuilts/clang`）→ external wifi driver → `resource.img`（pack_resource）→ android（`make -jN`）→ 打包。flags：`-U`uboot/`-K`kernel/`-A`android/`-u`update.img/`-J`jobs(默认 16)/无参=默认全套。
- **host 依赖实况**（audit 结果）：make/gcc/g++/flex/bison/perl/ninja/cmake/libssl-dev/zlib1g-dev/libncurses-dev 都在；`zip` 缺（已 `apt download`+`dpkg -x` 免 sudo 解到 `.host-deps/extracted/usr/bin/`）；**python2 缺**（u-boot 2017.09 CFGCHK 要，已本地编译 2.7.18 到 `.host-deps/python2/bin/`，symlink 出 python2/python）；`gcc-aarch64-linux-gnu` 缺（u-boot 要，需 sudo 装）；JDK 走 `prebuilts/jdk17`，主机可不装。**android make 里的老 clang**（`prebuilts/clang/.../clang-3289846`，renderscript bitcode 用）要 `libncurses.so.5`/`libtinfo.so.5`（noble 只有 .6）。⚠️ **`LD_LIBRARY_PATH` 方案无效**——soong/ninja 起的构建动作环境被收口，shell 里 export 的 `LD_LIBRARY_PATH` 进不了 ninja 的子进程（`clang.real --version` 直接调能过，经 ninja 就挂）。**正解：系统级 symlink**（有 sudo，一次性）：`sudo ln -sf /usr/lib/x86_64-linux-gnu/lib{ncurses,tinfo}.so.6 /usr/lib/x86_64-linux-gnu/lib{ncurses,tinfo}.so.5 && sudo ldconfig`。动态链接器永远搜 `/usr/lib/x86_64-linux-gnu`，ncurses5/6 ABI 对 clang 够用。
- **build.sh 两个坑**：① 硬编码 `export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64`（Rockchip 遗留，AOSP 13 实际用 JDK 17）——若 java 步骤报错，注释掉 build.sh 这三行 JAVA_HOME/PATH/CLASSPATH 让 soong 用 prebuilt jdk17；② 默认 `-J 16`，30G 内存必 OOM，传 `-J 6`。

### 点火 recipe（交给用户在本机点 fire）

> **推荐用 `./build-android.sh`**（脚本封装了下述全部：PATH + 预检 + lunch + build.sh）。**根因**：build.sh 用 `get_build_var` 读当前 shell 的 lunch 状态，fresh shell 没 lunch → KERNEL_VERSION/CROSS_COMPILE 全空 → u-boot 拿主机 x86 gcc 编 ARM（cc1 报 `x18`/`armv8-a+nosimd` 不认识）。脚本每次自己 lunch，根治。

```bash
cd /home/charliechen/rk-forge/reference/rk3568_android
sudo apt install -y gcc-aarch64-linux-gnu          # u-boot 要（一次性，你来 sudo）
export PATH="$PWD/.host-deps/python2/bin:$PWD/.host-deps/extracted/usr/bin:$PATH"  # 免 sudo 的 python2(u-boot)+zip
source build/envsetup.sh && lunch ATK_DLRK3568-userdebug
./build.sh -A -K -U -u -J 6     # uboot+kernel(5.10/clang)+android+update.img；-J6 防 OOM
```

盯 `free -g`，链接阶段 OOM 就降 `-J 4` 重来（make 增量）。首编 2–5h，产物 ~150G 写 ext4。产出 `rockdev/Image-ATK_DLRK3568/update.img`。

## ✅ 完成（2026-07-24）：编译成功，产物已验证合法

用 `./build-android.sh` 一键跑通，产出全套镜像并验过 magic bytes（不是空壳/损坏）：

- **`update.img`** 1.8 G，头部 `RKFW`（Rockchip Firmware 整包）——**可烧的最终交付**，RKDevTool / `upgrade_tool` 直接吃。
- `boot.img` 35 M，`ANDROID!` 魔数（Android bootimg，kernel@0x10008000，cmdline `console=ttyFIQ0 ...`）。
- `uboot.img` 4.0 M，`d00dfeed`（FIT/FDT，u-boot.itb，与主线 [[36]] binman 同形态）。
- `super.img` 1.7 G，Android sparse v1.0（system+vendor+product 动态分区，~796672 个 4K 块）。
- `MiniLoaderAll.bin` 465 K（loader）、`recovery.img` 46 M、`resource.img`、`vbmeta.img`、`dtbo.img`、`baseparameter.img` 齐全。
- `parameter.txt`：GPT，`MACHINE_MODEL: ATK-DLRK3568` / `MANUFACTURER: Alientek`，分区 security/uboot/trust/misc/dtbo/vbmeta/boot/recovery/backup/cache/metadata/frp/baseparameter/super/userdata(grow) 正确。

**踩坑链**（构建侧，全在脚本/host-deps 里根治了）：u-boot 2017.09 要 python2（本地编 2.7.18）→ 老 clang 要 libncurses.so.5（系统 symlink .so.5→.so.6，注意 `LD_LIBRARY_PATH` 因 soong 环境收口而**无效**）→ build.sh 必须在已 lunch 的 shell 跑（否则 CROSS_COMPILE 空，主机 x86 gcc 编 ARM，cc1 报 `x18`/`armv8-a`）→ 一律不用 sudo（sudo 重置 env → 回落 aosp_arm）。封装成 `build-android.sh`（PATH+预检+lunch+build.sh）一劳永逸。

**下一关：上板烧写** `update.img` 到 eMMC（RKDevTool Windows / `upgrade_tool` Linux），硬件 gated——与主线 [[36]] MVP 的 boot 验证同性质。构建侧到此全绿。
