# 24 — RW/abort saga 真根因:DT 缺 reserved-memory(OP-TEE/trust 物理页进了 free pool)

> 本条是 RW 写可靠性 saga 的**真根因笔记**。前两轮(DDR 头号嫌疑、SFC PIO/DMA)全追错树,
> 详见 [25-…-misdiagnosis](25-2026-06-19-sfc-abort-misdiagnosis-ddr-sfc-pitfalls.md)。
> ubiprog/loader-弱写的独立现状 + 下一步 rkbin 配置线索见
> [26-…-ubiprog-loader-weakwrite](26-2026-06-19-ubiprog-loader-weakwrite-status-and-rkbin-lead.md)。
> 板上验证 log:`document/logs/boot-sdl-202606192323.txt`(修前+修后两次冷启同 log)。

## 一句话结论

**写压测 abort(0xc06 UBIFS / 0x008 tmpfs)的真根因 = DT 没有 `reserved-memory` 节点 →
内核把 OP-TEE/trust 占着的低 DRAM 物理页([0x0, 0x62000))当 free pool → 分给用户进程 →
访问到 secure 区 → external abort。和 NAND/SFC/DDR 调谐全无关。**
修复:rk3506b-aes.dts 加 `reserved-memory { trust@0 { reg=<0x0 0x62000> } }`(对齐 vendor),
patch 0012。板上 50 圈 NAND 写压测 + 100 圈 tmpfs 全过。

## 症状(两种 abort,同一个根因)

| 场景 | fault | 地址 | 路径 | log |
|---|---|---|---|---|
| `flash_stress_test.sh 50`(dd 写 UBIFS) | **0xc06 imprecise**(异步) | user 0x0053d004 | `arm_copy_from_user ← generic_perform_write` | boot-sdl-202606192124-crash / 2208 |
| `dd if=/dev/urandom of=/tmp/s`(写 tmpfs,**零 NAND**) | **0x008 precise**(同步) | user 0xb6d7a000(pte→**phys 0x5000**) | `arm_copy_from_user ← generic_perform_write ← shmem_file_write_iter` | 同上 2208 |

两种都在 `arm_copy_from_user` 读 dd 的 user buffer 那一下。第二种是 **shmem(tmpfs)**——
**全程没有 NAND、没有 SFC、没有 UBI**。这一条直接判了"不是 SFC"。

## 决定性转折(两步)

### 转折①:用户洞察 —— "vendor_sdk 爆炸写都没事"
→ 不是硬件(DDR 芯片 / NAND / SFC 控制器),是我们的软件/配置。据此把 vendor rk3506
全链路扒了一遍,**推翻了交接记忆的前提**:

- vendor `rk3506_defconfig` / `alientek_rk3506_defconfig` 用的是
  `CONFIG_MTD_SPI_NAND=y` + `CONFIG_SPI_ROCKCHIP_SFC=y` + `CONFIG_UBIFS_FS=y`
  ——**和我们一模一样的 mainline 路径**,**不是** `CONFIG_RK_SFC_NAND`(私有 rkflash)。
  → 交接记忆"vendor 工作参考是 rkflash/sfc.c(带 idle 门)"**对 rk3506 是错的**。
- vendor ATK 板 `&fspi` 的 flash@0:`spi-nand / 80MHz / rx4 / tx1` —— 和我们**逐字等价**
  (80MHz 不是差异;之前看到 alientek.dtsi 的 50MHz 是 `&spi0` spidev,不是 SFC)。
- DDR blob:公开 `rkbin` 的 `rk3506b_ddr_750MHz_v1.06.bin` 和 ATK 的**md5 完全相同**
  (`6baff1cf…`)→ DDR 调谐不是差异(且我们 `pack-loader.sh:70` 本就装的是 rk3506**b** blob,没错)。
- SFC 写路径(`write_fifo`/`xfer_*`)和 vendor `spi-rockchip-sfc.c` **逐字等价**
  (816 行 diff 全是 API 改名 spi_master→spi_controller、DTR/octet 特性、powergood、DLL
  调谐算法差异;写 mechanic 一致)。

→ 排除了 DDR、NAND 芯片、SFC 控制器、SFC 驱动写路径。差异只剩:**我们 forced PIO
(`rockchip,sfc-no-dma`,遗留 debug)+ 无 `reserved-memory`**。但此时还没意识到后者才是命门。

### 转折②:dd-tmpfs(纯 RAM、零重建)也 abort —— 锁定内存
板上跑 100 圈 `dd of=/tmp/s`(tmpfs),照样 0x008 abort。`shmem_file_write_iter` = 写
内存,不碰任何外设。→ **abort 不需要 NAND writeback**,是**内存**问题。pte 解码:

```
[0xb6d7a000] *pgd=03297835, *pte=0000575f, *ppte=00005c7f
  → user 虚拟 0xb6d7a000 映射到物理 0x00005000
```

物理 **0x5000** 是极低地址(20KB 进 RAM)——不该是用户匿名页。而 boot log 里:

```
## Checking optee 0x00001000 ...
Jumping to U-Boot(0x00800000) via OP-TEE(0x00001000)
I/TC: OP-TEE memory size: TEEOS 0x5e000 TA 0x1000 SHM 0x1000
```

OP-TEE 装在物理 **0x1000**,占 `0x5e000+0x1000+0x1000 ≈ 0x60000` → 区间 [0x1000, ~0x61000]。
物理 0x5000 **正中靶心**。再看 kernel log 第一行:

```
OF: reserved mem: Reserved memory: No reserved-memory node in the DT
```

**三段拼齐 = 根因**:OP-TEE 占着低 DRAM,DT 没 carve out → 内核把那片当 free RAM →
buddy allocator 分给 dd 的 user buffer → 读它 = 踩 secure 区 → 精确 external abort 0x008。
vendor 编译 DT 里正好有 `reserved_memory { trust@0 { reg=<0x0 0x62000> } }` 罩住这片 →
vendor 不分到 → vendor 没事。完美闭环。

> 为什么 UBIFS 那个是 0xc06(imprecise)而 tmpfs 是 0x008(precise)?同一个根因(分到
> trust 物理页),precision 差异来自并发负载下的 async 冒泡时机——UBIFS writeback 时
> dd buffer + page cache 都可能分到 trust 页,abort 归到正在跑的 memcpy 就是 imprecise。
> **修 reserved-memory 后两个都消失**,证明同源。

## 修复(patch 0012,对齐 vendor)

`rk3506b-aes.dts` 根节点(紧挨 `memory@0`)加:

```dts
reserved-memory {
    #address-cells = <1>;
    #size-cells = <1>;
    ranges;
    trust@0 {
        reg = <0x0 0x62000>;
    };
};
```

- `0x62000` = 392 KiB,罩住 OP-TEE [0x1000, 0x61000] + 余量,**逐字对齐 vendor**。
- 不加 `no-map`:vendor 没加(编译 DT 实测),且 reserved-memory 框架无论是否 no-map 都
  会把这片从 buddy allocator 摘掉(用户页分配问题就这么解的)。先 match vendor,稳。
- `RKTRUST/RK3506TOS.ini` 实锤 `ADDR=0x1000`(OP-TEE 装载地址)→ 区域算得对。

patch:`patches/linux_mainline/0012-ARM-dts-rockchip-rk3506b-aes-reserve-OP-TEE-trust-memory.patch`
(explore/linux commit `eb9339d2b`),series 已 append。

## 板上验证(boot-sdl-202606192323.txt,修后冷启)

```
[    0.000000] OF: reserved mem: 0x00000000..0x00061fff (392 KiB) map non-reusable trust@0   ← 生效!
[    0.013787] Memory: 486744K/524288K available ...   ← 比修前 487140K 少 396K(=0x62000),trust 已 carve out
...
# dd if=/dev/urandom of=/tmp/s ... (100 圈)
TMPFS-DONE                                            ← 零 abort
# flash_stress_test.sh 50
[stress] loop 0/50: OK ... loop 49/50: OK
[stress] ===== PASS: 50 loops, no md5 mismatch =====   ← 50/50 全过
```

**两个原复现都干净** → 根因板上坐实。

## 关键文件 / commit / 镜像

- **patch**:`patches/linux_mainline/0012-…-reserve-OP-TEE-trust-memory.patch`;series append。
- **explore/linux commit**:`eb9339d2b ARM: dts: rockchip: rk3506b-aes: reserve OP-TEE/trust memory`。
- **DT 源**:`third_party/explore/linux/arch/arm/boot/dts/rockchip/rk3506b-aes.dts`(根节点 reserved-memory)。
- **vendor 参考**:`third_party/vendor-sdk/kernel-6.1/.../.rk3506b-alientek-…-nand-ubi-squashfs.dtb.dts.tmp:446`(trust@0)。
- **OP-TEE 区域来源**:`third_party/rkbin/RKTRUST/RK3506TOS.ini`(ADDR=0x1000);boot log OP-TEE size。
- **镜像**:`/mnt/d/DownloadFromInternet/update-rwfix-reservedmem.img`(md5 `35e1724e`,PROVISION-UBIPROG)。
- **板上 log**:`document/logs/boot-sdl-202606192323.txt`(修前 boot1 + 修后 boot2 同文件)。

## 教训(详见 笔记 25 提炼)

1. **imprecise external abort 的 FAR 不可信**(异步,归到任意后续指令)。别按 FAR 地址
   找原因——0x0053d004 是 dd user buffer,真凶是并发 trust 页访问,跟那个地址无关。
2. **纯 RAM(tmpfs)压测是免费判别器**:零重建、板上现跑,一锤定音"NAND/SFC 无关 vs 内存"。
   以后任何"是不是外设"先 tmpfs 一发。
3. **"vendor 同硬件没事 → 是我们的配置/软件"** 是最强指引;但前提是确认 vendor 走**同路径**
   (本次:vendor 也用 mainline spi-nand+spi-rockchip-sfc,不是 rkflash;交接记忆这步错了)。
4. **kernel boot log 的告警行别略过**:`No reserved-memory node in the DT` 一直在那,
   被两轮调查忽略了。
5. **imprecise(0xc06)和 precise(0x008)可能同源**:别因为 fault type 不同就分头查;
   tmpfs 复现给出 precise 版,反而更好定位。

相关:[[sfc-dll-saga-and-writepath]](待更新:abort 段改判 reserved-memory)
`handoff-rw-sfc-abort-open`（已作废,见记忆更正）、
[pitfalls/05](../pitfalls/05-secure-mem-reservation-imprecise-abort.md)。
