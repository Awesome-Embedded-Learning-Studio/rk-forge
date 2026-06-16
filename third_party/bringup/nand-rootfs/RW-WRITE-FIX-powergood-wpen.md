# RW 写损坏 — 根因修正 + 修复(powergood + WPEN)

> 本文**推翻** [HANDOFF-LOADER-MARGINAL-WRITE.md](HANDOFF-LOADER-MARGINAL-WRITE.md) 的"rkbin loader 边际写、换版本无效、不可解"结论。
> 真正根因:**我们主线 SFC 驱动缺 vendor 的写侧两项配置(powergood 门 + WPEN 位)**,导致读写都不够稳。RW 完全可达。
> 配套:[SFC-WRITE-CORRUPTION-POSTMORTEM.md](SFC-WRITE-CORRUPTION-POSTMORTEM.md)、记忆 `sfc-dll-saga-and-writepath`。

## 为什么上一轮判错了

上一轮 saga 的两个盲点:

1. **自始至终只换 rkbin loader(黑盒),从没让 vendor 内核驱动上过板。** 所有"换 loader 验证"都是 loader 互换 + **我们自己的主线 kernel/SFC 驱动**不变。v7 探针说"PEB27 是 loader 存量"——但那是用**我们不可靠的读驱动**(无 powergood/WPEN)读出来的,**可能本就是读边际**,不是 loader 写坏。结论归因"rkbin 通病"时,vendor kernel fspi 驱动(带 powergood)**一次都没被测过**。

2. **"我们的栈写可靠"从未跨重启验证。** mtdbb 当场回读 CLEAN、U-Boot 当场 cmp 干净全是**同会话**;而 saga 自己的症状(`echo>/test.txt`(Linux commit erase+重写 3/4/26)→ reboot → 读炸 ECC)恰恰是"Linux 写 → 重启 → 读 = 坏"。两证直接冲突。HANDOFF 对兜底 B"确定有效"的信心建立在**没验证过的前提**上。

## 存在性证明(用户实测确认)

vendor ATK SDK **本来就为这块板出货 RW UBIFS**:
- `rk3506b-alientek-...-nand-ubi-ubifs.dts` bootargs:`root=ubi0:rootfs rw rootfstype=ubifs`。
- 日志 [logs/atk-standard-boot.txt](../../logs/atk-standard-boot.txt)(=`rk3506b_update_ubi_ubifs.img` 烧录)显示:`UBIFS recovery needed → recovery completed → mounted`,**UBIFS 能成功 replay 上次 boot 写的 journal**(journal 就是元数据 PEB,就是我们这边会坏的那种)。`media format: w4/r0 (latest w5/r0)` 写计数跨重启递增。**用户反复跨重启写多次,vendor 极稳定。**

→ 同一颗 W25N04KV、同一块板:**硬件没问题,RW 可达**。差的就是驱动配置。

## vendor 写、我们没写的三项(逐一坐实)

| # | 项 | vendor | 我们主线(修复前) | 影响 |
|---|---|---|---|---|
| 1 | **`SFC_CTRL_WPEN`(BIT29)** | 每个 op `ctrl\|=SFC_CTRL_WPEN`([vendor:462](../../vendor-sdk/kernel-6.1/drivers/spi/spi-rockchip-sfc.c#L462)) | 没定义、没设 | 控制器对 WP#/IO2 引脚驱动;缺则 quad 数据相位边际。**最贴时间线**(影响每次中途 commit 写) |
| 2 | **powergood 门** | 每次 op 前轮询 `GRF_PMU+0x100 bit0`([vendor:479-486](../../vendor-sdk/kernel-6.1/drivers/spi/spi-rockchip-sfc.c#L479-L486)),DT `rockchip,grf=<&grf_pmu>` | 完全没有 | 写前不确认 flash IO 域电压就绪 |
| 3 | U-Boot SFC 实跑 100MHz | (vendor U-Boot 也无 powergood) | `clk_set_rate` ENOENT → real=100MHz | 任何 U-Boot 写必边际(兜底 B 不修即空中楼阁;读已证可靠) |

(其余:FIFO mask、write_fifo、xfer_done、DIR 位、ECC 配置——逐行相同,两 agent 双盲收敛。)

## 本次修复(已改,编译通过)

**Linux 主线** [`drivers/spi/spi-rockchip-sfc.c`](../../explore/linux/drivers/spi/spi-rockchip-sfc.c):
- 加 `SFC_CTRL_WPEN BIT(29)`,`xfer_setup` 里 `ctrl |= SFC_CTRL_PHASE_SEL_NEGETIVE | SFC_CTRL_WPEN`。
- 加 `struct rockchip_sfc_powergood` + `struct rockchip_sfc_data` + `rk3506_fspi_data`(.powergood.valid, grf_offset=0x100, BIT(0))。
- `struct rockchip_sfc` 加 `grf`/`data` 字段;probe 里 `device_get_match_data` + `syscon_regmap_lookup_by_phandle("rockchip,grf")`。
- `xfer_setup` 写 ctrl 前轮询 powergood(**先非致命**:超时 `dev_warn_ratelimited` + 继续,避免 bit 不置位变砖;板上确认 bit 置位后可改回 vendor 的 `-EIO`)。
- `dt_ids` 加 `{ .compatible = "rockchip,rk3506-fspi", .data = &rk3506_fspi_data }`。

**Linux DT** [`rk3506.dtsi`](../../explore/linux/arch/arm/boot/dts/rockchip/rk3506.dtsi) sfc 节点:
- `compatible = "rockchip,rk3506-fspi", "rockchip,sfc";`
- `rockchip,grf = <&grf_pmu>;`

**U-Boot 主线** [`drivers/spi/rockchip_sfc.c`](../../explore/uboot/drivers/spi/rockchip_sfc.c):加 `SFC_CTRL_WPEN BIT(29)` + `xfer_setup` 设它(powergood 不加 —— vendor U-Boot 本就没有;U-Boot 只读 kernel,100MHz 读已证可靠)。

> 编译验证:Linux `spi-rockchip-sfc.o` ✓、`rk3506b-aes.dtb` ✓、U-Boot `rockchip_sfc.o` ✓;`CONFIG_MFD_SYSCON=y`(syscon 链接无虞)。

## 烧板 + 跨重启写验证协议(决定性)

核心:RW 的判据就是 vendor 在做的——**写文件 → 冷重启 → 还在**,连多轮。这正是 saga 会坏、vendor 不会坏的操作。

```bash
# 烧修复镜像后,boot 到 RW UBIFS shell(~ #),执行:
for i in 1 2 3 4 5; do
  echo "cycle-$i uptime=$(cat /proc/uptime | cut -d. -f1)" >> /persist.log
  sync
  reboot -f          # 硬复位(等同冷重启,SFC/DLL 全部重初始化)
done
# 第 6 次 boot 后:
cat /persist.log                       # 期望:5 行全在,cycle-1..5
dmesg | grep -iE "ecc|ebadmsg|ubi_io_read|powergood|bad magic"  # 期望:无 ECC 错;powergood 无 warning
```

**判读:**
- **5 行全在 + 0 ECC 错** → RW 达成,powergood+WPEN 是根因解。收尾:把 powergood 非致命改回 `-EIO`(对齐 vendor),`git format-patch` 重生 patches。
- **`powergood (GRF_PMU+0x100) not asserted` warning 刷屏** → bit 不置位 → powergood 不是机制,靠 WPEN。查 dmesg 写是否仍稳;稳则 WPEN 单独够。
- **仍爆 ECC / `/persist.log` 丢** → 写路径还有别的边际(U-Boot 100MHz?真电气?)→ 下一步:把 U-Boot clk 修到 50MHz + 给 Linux 写后校验 / 降写时钟兜底。

> 辅助取证(可选,用 rootfs 里已有的 mtdbb/mtdrawdump):对固定块做 `mtdbb test /dev/mtd5 0x60000` → `mtdrawdump -r ...` 记 md5 → `reboot` → 再 `mtdrawdump -r` 比对,看单块跨重启稳不稳。

## 仍待办

- 板验通过后:powergood 非致命→致命(对齐 vendor);重生 patches/0003(linux)+ uboot;清理 core.c/winbond.c 的 PROBE 探针代码。
- U-Boot 100MHz clk bug:若走"U-Boot 写 rootfs"(兜底 B)才必修;当前 Linux 写 rootfs 路径不依赖它。
- 长期 retention:多轮 reboot stress 后再确认(Linux 强写是否长期不衰)。
