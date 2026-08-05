# Ch1 — 引导启动：bootloop 第 0 关 + 主线 SPL + autoboot

> 上一章交代了 RK3588 在阶梯里的位置。这一章动手，把板子从 BootROM 一路跑到 systemd 的 `graphical.target`。听起来和 RK3506B 那条启动链差不多，实际上 RK3588 的启动前段比 RK3506 多一级 ATF，而且咱们在这里栽进了一个全程看不见报错的 bootloop——这一章的主线，就是把这个 bootloop 的根因挖出来、绕过去，再把 baud、root 设备号、autoboot 三个板级细节对齐。完整记录见 [notes/49](../../notes/49-2026-07-27-rk3588-bootloop-mainline-spl.md)（bootloop）和 [notes/50](../../notes/50-2026-07-27-rk3588-first-boot-baud-root-dt.md)（首启）。

## 启动链长什么样：比 RK3506 多一级 ATF

先把 RK3588 的启动链画出来，看清每一段归谁管：

```
BootROM
  → @0x40 idblock         ← pack-loader 打的 loader 容器
      ├─ rkbin DDR init    ← 闭源 blob，点亮 DDR（绕不开）
      ├─ usbplug            ← 闭源 blob，Maskrom 下载用
      └─ SPL                ← 这一级是关键变量（vendor rk3588_spl 或主线 SPL）
  → BL31 / ATF             ← rkbin 闭源 blob（RK3506 没有这一级！）
  → U-Boot proper          ← 主线 2026.07-rc4
  → bootm FIT              ← kernel + 板级 DT
  → Linux 7.1              ← 主线
  → systemd → graphical.target
```

和 RK3506B 比，最大的结构差异是中间那级 BL31 / ATF——ARM Trusted Firmware 的运行时服务（PSCI 多核唤醒、SMC 调用都靠它）。RK3506 是 Cortex-A7 没有 ATF，RK3588 是 ARMv8-A 必须有。这一级多了，就多出一个「SPL 怎么把控制权交给 BL31」的契约，咱们踩的 bootloop 就埋在这条契约里。

idblock 这个 loader 容器由 [scripts/pack-loader.sh](../../../scripts/pack-loader.sh) 按 `board/rk3588-topeet/RKBOOT-RK3588-topeet.ini` 打包，里面三段 blob（DDR + usbplug + SPL）。前两段是 rkbin 闭源、绕不开；第三段 SPL 有两条来源可选，由板配置的 `SPL_SOURCE` 字段决定——这条字段就是这一章的主角。

## 坑之一：看不见报错的 bootloop

板子第一次上电，串口看到的是这样的循环：

```
BootROM → @0x40 idblock (rkbin DDR init + rk3588_spl v1.14)
  → U-Boot SPL 2017.09 ... → 验 atf/u-boot/fdt 全 sha256 OK
  → Jumping to U-Boot via ARM Trusted Firmware(0x00060000)
  → 【没出 banner】立即复位 → 回 DDR → 循环（观察 23+ 次）
```

SPL 验完三段镜像的 sha256 全 OK，说「我要跳给 ATF 了」，然后——没有 banner，直接复位，回到 DDR，再来一遍。没有报错，没有 panic，没有 oops，就是无限循环。这种 bootloop 最折磨人，因为它不告诉你哪儿错了。

完整 bootlog 和排除法分析见 [document/logs/rk3588/bootloop-analysis.md](../../logs/rk3588/bootloop-analysis.md)，这里讲咱们怎么一步步把真凶逼出来的。

第一个下意识的判断是：SPL 都验过 sha256 了，镜像肯定是好的，问题一定在后面——要么 U-Boot proper 崩，要么 DDR 不稳。这两个都是错的方向。U-Boot proper 根本没拿到控制权（banner 没出），DDR 也不稳的话连 SPL 都跑不到 sha256 那一步。

真正管用的诊断点，是 bootlog 里有没有这一行：

```
NOTICE:  BL31:
```

这是 BL31（ATF）进场时打的 banner。咱们的 bootloop 里，这一行从头到尾没出现。SPL 说「跳给 ATF」，ATF 却没进场——说明 SPL 跳去的地址，根本不是 BL31 真在的地方。

真因在 rkbin 的版本配套上。咱们用的 vendor `rk3588_spl_v1.14`（U-Boot SPL 2017.09 那一代）早于 BL31 v1.54。而 BL31 v1.54 干了一件事：把 `bl31_base` 从旧地址迁到了 `0x60000`。旧 SPL v1.14 不知道这次迁移，还按旧基址跳过去——那里没有 BL31，自然没人接，板子就复位了。bootlog 里 `Jumping to U-Boot via ARM Trusted Firmware(0x00060000)` 这行其实是 SPL 的「意图」，不是 ATF 真在那。

⚠️ 这里有个要记住的契约：SPL 和 BL31 必须同代。rkbin 的 rk3588_spl 老于 bl31 时，就会踩这种基址迁移的坑。诊断靠的就是 `NOTICE: BL31:` 这一行有没有——没有就是 SPL→BL31 这条链断了。

正解不是去翻 rkbin 找一个和老 SPL 配套的老 BL31（那是往回走），而是把 SPL 也换成主线的。[config/boards/rk3588-topeet.env](../../../config/boards/rk3588-topeet.env) 里设：

```bash
SPL_SOURCE="mainline"
```

这样 [pack-loader.sh](../../../scripts/pack-loader.sh) 打 idblock 时，第三段 SPL 不取 vendor 的 `rk3588_spl_v1.14`，改取 [build-uboot.sh](../../../scripts/build-uboot.sh) 编出来的 `u-boot-spl.bin`——主线 SPL，跟 BL31 v1.54 同代，知道 `bl31_base` 在 0x60000。这本来就是 U-Boot 官方的 RK3588 流程：rkbin DDR 作 TPL + 主线 SPL + binman。改完再 boot，`NOTICE: BL31:` 就出来了，后面 U-Boot banner、bootm 一路顺下去。

> 别照搬 RK3568 那条「vendor SPL + 主线 U-Boot」的路子。RK3568 的 `rk356x_spl` 没有这次基址迁移，用 vendor SPL 没事；RK3588 的 rk3588_spl 有这个坑，必须主线 SPL。每块板的 rkbin 配套契约不一样，这正是「三板不共享固件」纪律的现实理由。

## 坑之二：串口乱码——baud 得全链路改

bootloop 过了，U-Boot banner 出来了，可串口里全是乱码。这是波特率没对齐：vendor 默认 1500000，咱们的串口工具按 115200 接，自然花屏。

要命的不是 U-Boot 这一段，而是 baud 得全链路改，少一段都会乱。RK3588 上涉及 baud 的有四处，从最早的一段开始。

第一段是 DDR blob。rkbin 的 DDR init 在 BL31 和 U-Boot 之前就跑了，它初始化串口时用的 baud 写死在 blob 里。改它得用 rkbin 自带的 `ddrbin_tool`：

```bash
# 在 rkbin 子模块里，改 DDR blob 的串口波特率（只支持 115200 / 1500000）
python3 tools/ddrbin_tool.py rk3588 \
  -- uart baudrate=115200 \
  bin/rk35/rk3588_ddr_lp4_2112MHz_lp5_2400MHz_v1.*.bin
```

⚠️ 这一步目前是直接改 rkbin 的 working tree，`forge setup` 重新 fetch 会丢——集成进 setup 是待办，现在你得手动跑一次。

后面三段在配置里：U-Boot 的 `CONFIG_BAUDRATE=115200`、kernel DT 的 `stdout-path = "serial2:115200n8"`、bootargs 的 `console=ttyS2,115200`。这四处全对上，串口从 DDR init 到 systemd 登录全程可读。

## 坑之三：`Waiting for root device`——eMMC 是 mmcblk0

U-Boot 起来了、kernel 起来了，然后卡在：

```
Waiting for root device /dev/mmcblk1p3 ...
```

这是照搬 RK3568 的 bootargs 写的 root 设备号。RK3568-atk 的 eMMC 是 `mmcblk1`，可 RK3588 topeet 的 eMMC 是 `mmcblk0`——同一个 SoC 不同板的设备号都可能不一样，照搬必踩。

板配置里的判据：U-Boot 下 `ls mmc 0:3 /boot` 能看到 boot.scr，说明 eMMC 在 U-Boot 里是 `mmc 0`；kernel 起来后 `mmcblk0: p1 p2 p3`。所以 boot.cmd 里 root 写：

```
root=/dev/mmcblk0p3 rw rootwait
```

## autoboot：bootflow 不扫 eMMC 分区，就绕开它

上面三个坑过了，板子能手动 boot 到 systemd——在 U-Boot 提示符下敲 `mmc dev 0; mmc read 0x08000000 0x6000 0x20000; bootm` 是好的。可你一松手让它自己 boot，它又不动了。

根因在 U-Boot 的 `bootflow scan`：对 eMMC 这个设备（dev 0），主线 bootdev 有个 quirk，不扫分区，所以 bootflow 找不到放在 rootfs 分区 `/boot/` 里的 boot.scr。手动 `mmc dev 0` 它就认，bootflow 偏不认——这种「手动行、自动不行」的坑最磨人。

正解是绕开 bootflow，把 bootcmd 写死成「直接读 boot.scr 然后 source」。这落在三个 U-Boot patch 里（[patches/rk3588-topeet/uboot/](../../../patches/rk3588-topeet/uboot/)）：`0001` 把 `BOOT_TARGETS` 砍到只剩 `mmc0`、`0002` 设 `CONFIG_BAUDRATE=115200`、`0003` 把 `CONFIG_BOOTCOMMAND` 写成 `load mmc 0:3 ${scriptaddr} /boot/boot.scr; source`。

> ⚠️ 这三个 defconfig 改动一定要落成 patch。咱们中途踩过一个回归坑：defconfig 改了没提交，一次 `git reset --hard` 把 dirty 冲掉，baud 又回到 1500000，串口重新满屏乱码——绕了一大圈才发现是自己的 reset 把改动冲了。改过的 defconfig 不进 patch series，等于没改。

## canonical：启动相关的几处配置

把这一章涉及的关键配置集中放这儿，方便对账：

```
# config/boards/rk3588-topeet.env
SPL_SOURCE="mainline"                    # 坑之一：主线 SPL 配 BL31 v1.54
RKBIN_BL31_PAT="rk3588_bl31_v*.elf"      # ATF blob
RKBIN_DDR_PAT="rk3588_ddr_lp4_2112MHz_lp5_2400MHz_v1.*.bin"

# board/rk3588-topeet/fit/boot-emmc.cmd（boot.scr 模板）
mmc dev 0
mmc read 0x08000000 0x6000 0x20000
setenv bootargs console=ttyS2,115200 root=/dev/mmcblk0p3 rw rootwait
bootm 0x08000000
```

板级 DT（PMIC rk806 + rk8602/rk8603 CPU 供电）这一版只接了启动必需的部分，照 `rk3588-fet3588-c.dtsi` 的模板；显示管线是下一章的事。

## 成功长这样

四个坑都过了之后，update.img（MD5 `1d972c21`）烧 eMMC，上电——串口 115200 全程可读，boot 到 systemd 的 `graphical.target`：

```
...（DDR init / NOTICE: BL31 / U-Boot banner，一路 115200 干净）
...（bootm → Linux 7.1.0 SMP PREEMPT）
rockchip-pmics ... rk806 ...                # PMIC
rk8602 / rk8603 ...                          # CPU 供电
mmc0: mmcblk0: p1 p2 p3                     # eMMC HS400，注意是 mmcblk0
rk3568... gmac0 ... RGMII ...               # 以太网
panthor ... Mali-G610 ... renderD128        # GPU（下一章细讲固件）
...
rk3588-topeet login:                        # systemd 到 graphical.target
```

这一段从 [document/logs/rk3588/](../../logs/rk3588/) 里的真机抓取截的，一个字没合成。bootloop 那一段的完整排除法在 [bootloop-analysis.md](../../logs/rk3588/bootloop-analysis.md)。

到这里，RK3588 已经能自己 boot 到 systemd 了。下一章咱们点亮那块 1024×600 的屏——那条路比 boot 难走得多，拖了整整四个镜像才出图。
