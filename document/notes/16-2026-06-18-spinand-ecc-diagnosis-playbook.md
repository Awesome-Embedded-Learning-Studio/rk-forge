# 16 — SPI-NAND ECC 诊断 playbook（读/写 bug 定位）

> 从 rootfs PEB3/4 复查（notes/14/15）提炼的可复用 playbook。下次 SPI-NAND 报 `-EBADMSG`/`-74` 直接套。

## 1. 写者 × 读者验证矩阵（先定方向：读 bug 还是写 bug）

NAND ECC 报错，先填这张二维表，四格全测，按行列干净/爆的格局定根因方向：

| # | 写者 | 读者 | 怎么测 |
|---|---|---|---|
| ① | loader | U-Boot | 烧 update.img → 停 U-Boot → `mtd read`（ECC）+ `mtd read.raw` |
| ② | loader | Linux | 烧 → boot Linux → ubiprog/mtdrawdump 读 |
| ③ | Linux | U-Boot | boot Linux 写(echo+sync/ubiprog) → reboot → 停 U-Boot `mtd read` |
| ④ | Linux | Linux | saga 已知（写后 reboot 读）|

**格局判读**：
- 某读者列全干净（写者A+读者X干净，写者B+读者X也干净）→ 该读者 OK
- 写者A+读者X干净、写者A+读者Y爆 → **读者 Y bug（读侧）**
- 写者A+读者X爆、写者B+读者X干净 → **写者 A bug（写侧）**

⚠ **大坑**：单次 ECC 读"报不报 `-74`" **不能**判写者稳定性——**写者会抖动**。这次 loader 写 PEB3/4：① 那次烧 ≤8 flip（ECC 纠了，U-Boot 无 `-74`），另一次烧 >8 flip（不可纠）。**必须看 SR 真值**（§2），不能靠 `-74` 报不报。

## 2. spinand_read_page SR trace（on-die ECC 真值）

host 的 ECC 读会混合"物理 flip"和"ECC 状态解析"，要看 **flash 自己报的 SR byte**。在 `drivers/mtd/nand/spi/core.c` 的 `spinand_read_page`，`spinand_ondie_ecc_save_status(nand, status)` 之后加：

```c
spinand_ondie_ecc_save_status(nand, status);
if (status & STATUS_ECC_MASK)
    pr_info("spinand_rd eb=%u pg=%u st=0x%02x ecc=0x%02x\n",
            req->pos.eraseblock, req->pos.page, status, status & STATUS_ECC_MASK);
```

要点：
- **只打 `st≠0x00`**（有 flip 的页）。全打 = 64 页 × 1392 PEB ≈ 几万行，串口 log 抓不全（这次 trace v1 全打，10245 行，FIRST BOOT 段被截断丢关键）。
- `eb` 是 **全局 eraseblock**（不是分区内 index）= `分区偏移/erasesize + 分区内 PEB`。例：rootfs 偏移 `0x2740000` / `0x20000` = 314，rootfs PEB3 = **eb 317**、PEB4 = eb 318。grep trace 时算对 eb，别 grep `eb=3`。
- `ecc=` 字段用 `%02x` 别用 `%x`（`STATUS_ECC_MASK` 是 `GENMASK` 返回 long，`%x` 编译 warning；小值运行时无碍但不干净）。

## 3. SR 含义（W25N04KV，查 datasheet 核对）

W25N04KV datasheet §7.3.1，SR bit[5:4]（ECC-1,ECC-0）：

| bit5,bit4 | 值 | 含义 |
|---|---|---|
| 0,0 | 0x00 | 无错 |
| 0,1 | 0x10 | 1-4 flip **已纠**（未超阈值）|
| 1,0 | **0x20** | **"NOT corrected" >8 flip 不可纠** |
| 1,1 | 0x30 | 5-8 flip **已纠**（超阈值，建议刷新）|

mainline `STATUS_ECC_UNCOR_ERROR=(2<<4)=0x20`（通用 SPI NAND 标准，W25N04KV 成立）；`W25N04KV_STATUS_ECC_5_8_BITFLIPS=(3<<4)=0x30`。**别假设 0x20/0x30 哪个是 uncor，查 datasheet**（不同 flash 编码不同）。

**联网查 datasheet（免 MCP 额度）**：
```bash
curl -s "https://r.jina.ai/https://lite.duckduckgo.com/lite/?q=W25N04KV+datasheet+ECC+status"   # DDG lite 搜
# 找到 PDF URL 后 r.jina.ai 读
curl -s "https://r.jina.ai/https://www.mouser.com/pdfdocs/w25n04kv_ds.pdf" | grep -iE "ecc|correct|not corrected"
```
（智谱 MCP web-search 满额度会 429；curl/r.jina.ai 只烧模型 token，见记忆 [[web-access-via-curl]]）

## 4. 诊断流程（一图）

```
NAND 报 -74/-EBADMSG
   │
   ├─ §1 填 写者×读者矩阵 → 定方向（读 bug / 写 bug）
   │     └─ 注意写者抖动：矩阵只看一次不够，关键页要 §2 看 SR 真值
   │
   ├─ §2 spinand_read_page 加 SR trace（只打 flip）→ 重编 → 上板抓 st=0xZZ
   │     └─ 算对 eb（全局 = 分区偏移/erasesize + PEB）
   │
   ├─ §3 datasheet 核对 SR 含义 → 定 root cause
   │     └─ curl r.jina.ai 查 datasheet
   │
   └─ 结论：物理 flip 数（SR）+ 矩阵 → 读 bug / 写弱写 / ECC 解析 bug
```

## 5. 这次（rootfs PEB3/4）的实例
- 矩阵①②③④推 "Linux 读 bug"（①U-Boot 干净、②Linux 爆）→ 但单次读判不稳
- SR trace 抓 `eb=317 pg=3,5 st=0x20`（=NOT corrected，>8 flip）→ **loader 写这几页 >8 flip 不可纠**
- datasheet §7.3.1 确认 0x20=uncor → **loader 弱写真**，翻案作废
- 教训：①那次 U-Boot 无 `-74` 是 loader 写 ≤8（ECC 纠了），loader 写抖动，单次不能判稳定

## 相关
[14](14-2026-06-18-rootfs-peb34-readpath-bug.md)（详细过程）/ [15](15-2026-06-18-sfc-nand-saga-finale-memo.md)（终章备忘）/ 记忆 `sfc-dll-saga-and-writepath`
