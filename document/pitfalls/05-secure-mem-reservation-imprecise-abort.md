# 05 — DT 没给 OP-TEE 留 reserved-memory,secure 物理页被分给用户态 → external abort

> 故障域:**DT 内存映射 / secure-memory(OP-TEE)预留**。这条坑藏在 SFC/NAND saga([04](04-sfc-nand-saga.md))
> 里两轮(DDR 嫌疑、SFC PIO/DMA)都没被识破,最后被一个**零重建的 tmpfs 判别实验**和一行被忽略
> 的 kernel 告警揪出来。raw 过程见 notes [24](../notes/24-2026-06-19-sfc-abort-rootcause-reserved-memory-trust.md)
> / [25](../notes/25-2026-06-19-sfc-abort-misdiagnosis-ddr-sfc-pitfalls.md)。

## canonical 结论(一句话)

**板跑 OP-TEE,DT 就必须有 `reserved-memory` 把 OP-TEE/trust 占的物理区 carve out;漏了,
内核就把那片当 free RAM 分给用户进程,访问到 secure 区 = external abort。** RK3506B 上
OP-TEE 在物理 `0x1000`、占 ~`0x60000`(rkbin `RKTRUST/RK3506TOS.ini` `ADDR=0x1000`),
要 reserve `[0x0, 0x62000)`(对齐 vendor `trust@0`)。

## 症状长什么样(迷惑性极强)

| workload | fault | 解读 |
|---|---|---|
| dd 写 UBIFS rootfs(`flash_stress_test`) | `imprecise external abort (0xc06)` @ dd user buffer | 异步,被两轮误判成 SFC/DDR |
| dd 写 **tmpfs**(`/tmp`,零 NAND) | `external abort on non-linefetch (0x008)` @ user buffer(pte→**phys 0x5000**) | 同步,精确,定位到 OP-TEE 区 |

**迷惑点**:fault 都在 `arm_copy_from_user` 读 dd 的 user buffer,看着像"内存/外设压力下
数据错"。第一反应往 DDR/SFC 找,**全错**。

## 为什么会判错两次(共性盲区)

1. **imprecise abort(0xc06)的 FAR 不可信**。异步冒泡,FAR 是"abort 冒上来时 CPU 正在干的
   那个地址",**不是真凶总线事务的地址**。按 FAR(0x0053d004)找 DDR 缺陷 → 方向错。
2. **第一轮(DDR)**:交接记忆写"abort 落用户 RAM → 头号嫌 DDR → 跑 stressapptest 判别"。
   被**用户一句"vendor_sdk 爆炸写都没事"**否决(同 DDR 芯片、同 DDR blob md5、同板)。
3. **第二轮(SFC PIO/DMA)**:发现我们 `rockchip,sfc-no-dma`(forced PIO)、vendor 用 DMA,
   假设 PIO 喂不动 FIFO。**没注意到 `no-dma` 是遗留 debug(理由已失效)**,也没先做最便宜
   的判别。

两个 detour 的共性:**没先确认"vendor 走的是不是同路径"** + **没先跑零成本判别器(tmpfs)**。

## 一发判干净:tmpfs 压测(零重建、板上现跑)

```sh
# 纯 RAM、零 NAND/SFC/UBI。和 abort 同一条 arm_copy_from_user 路径。
for i in $(seq 1 100); do dd if=/dev/urandom of=/tmp/s bs=1M count=30 2>/dev/null; md5sum /tmp/s >/dev/null; rm /tmp/s; done
```

- **炸 → 内存侧**(本次:0x008,pte→phys 0x5000 落 OP-TEE 区)。
- **不炸 → 外设侧**(SFC/NAND writeback 才触发)。

这一发直接判了"和 SFC 无关",省掉继续 diff 816 行 SFC 驱动。**以后任何"是不是外设"先 tmpfs**。

## 命门:一行被忽略的 kernel 告警 + 一段早就有的 boot 信息

```
[    0.000000] OF: reserved mem: Reserved memory: No reserved-memory node in the DT   ← 命门,两轮都略过
...
## Checking optee 0x00001000 ...
Jumping to U-Boot(0x00800000) via OP-TEE(0x00001000)
I/TC: OP-TEE memory size: TEEOS 0x5e000 TA 0x1000 SHM 0x1000                 ← OP-TEE 区早写在 log 里
```

OP-TEE 在物理 `0x1000`、占 `~0x60000` → 区间 `[0x1000, 0x61000]`。abort 的 phys `0x5000`
**正中靶心**。三段拼齐就是根因。

## 解法(对齐 vendor,patch 0012)

`rk3506b-aes.dts` 根节点加:

```dts
reserved-memory {
    #address-cells = <1>;
    #size-cells = <1>;
    ranges;
    trust@0 { reg = <0x0 0x62000>; };   /* [0x0, 0x62000) 罩住 OP-TEE [0x1000, 0x61000] */
};
```

- `0x62000`(392 KiB)对齐 vendor 编译 DT 的 `trust@0`(`.rk3506b-alientek-…-nand-ubi-squashfs.dtb.dts.tmp:446`)。
- 不加 `no-map`:vendor 没加;reserved-memory 框架无论 no-map 都会把这片从 buddy allocator 摘掉,
  用户页分配问题就解了。先 match vendor。
- 区域算法:`RKTRUST/RK3506TOS.ini` 的 `ADDR=0x1000` + boot log 的 OP-TEE size → `0x62000`。

## 板上验证(boot-sdl-202606192323.txt)

```
[    0.000000] OF: reserved mem: 0x00000000..0x00061fff (392 KiB) map non-reusable trust@0
[    0.013787] Memory: 486744K/524288K available   ← 比修前 487140K 少 396K(=0x62000),已 carve out
TMPFS-DONE                                  ← dd-tmpfs 100 圈零 abort
[stress] ===== PASS: 50 loops, no md5 mismatch =====   ← flash_stress 50/50 过
```

**0xc06(UBIFS)和 0x008(tmpfs)同源**,reserved-memory 一修两个都消失 → 没有独立 SFC 二级问题。

## 方法论(canonical)

1. **imprecise(0xc06/async)的 FAR 不可信;要定位就造 precise(0x008/sync)复现**(换更纯的
   workload,如 tmpfs)。
2. **tmpfs 压测 = 外设/内存的免费判别器**(零重建、板上现跑)。先 tmpfs,再 diff 驱动。
3. **"vendor 同硬件没事 → 我们的配置/软件"**;但**先确认 vendor 走同路径**(本次交接记忆错把
   vendor 当 rkflash,实际是 mainline spi-nand;路径错,对比失效)。
4. **kernel boot log 的告警行别略过**:`No reserved-memory node in the DT` 这种一行字就是命门。
5. **历史 workaround 要回收**:`no-dma`/powergood 这种"当时加的 debug",理由失效后要删或注释,
   否则会被当真因(本次第二轮 detour 就是吃了这个)。
6. **fault type 不同(0xc06 vs 0x008)不等于两个根因**;同根因在不同并发负载下精度不同。

## 与 [04 SFC/NAND saga](04-sfc-nand-saga.md) 的关系

- [04] 的 loader 弱写 saga **依然成立、独立**(见 notes [26](../notes/26-…-ubiprog-loader-weakwrite)):
  abort 修了,ubiprog 首启照样读出 PEB 3/4/5/122/124 chip ECC -74。loader 弱写是 chip ECC 报的,
  和 host RAM 分配(OP-TEE)无关。
- 本篇纠正的是:**RW saga 里"写 abort / code 损坏"那一支,真根因是 reserved-memory,不是 SFC
  写路径**。0011 idle-gate、powergood、DLL 调谐都保留(无害硬化),但都不是 abort 的解。
- [04] 里某些"init prefetch abort / UBIFS LPT CRC 坏"症状,可能也有的是这条坑(OP-TEE 页)
  而非 loader 弱写 —— abort 修了之后,干净复测才能区分(notes [26] 待办)。
