# 66 — bootm + FIT：真板同款文件与命令的最后一接力（2026-08-26）

> 用户定了提交闸门：「bootm + 仿真必须走通才提交」。走通了——U-Boot 用
> `bootm` 起 forge 打包的 `out/rk3568-atk/boot.img`（烧真板的同一份 FIT），
> 内核挂整块 rootfs，四断言 PASS，六模式全绿。

## 0. 结论

| 项 | 结果 |
|---|---|
| bootm + FIT | ✅ 四断言：U-Boot 横幅 / autoboot / VFS Mounted root / FIT sentinel |
| 命令形态 | `bootm 0x20000000 - 0x0f000000`（FIT + 外部 DTB 三参形式） |
| 六模式回归 | linux / board / rootfs / uboot / fit / virt 全 PASS |
| 顺带清账 | U-Boot 192MB 遗留课题一并解决（见 §1） |

## 1. 两个坑

1. **U-Boot 只认 192MB（遗留账）**：真板由 TPL 把 DRAM 信息写进 OS_REG，
   仿真里没人写 → 尺寸解码落到兜底值 192MB → 内核也只见 190MB，真板 DTB
   的全量设备探测在 190MB 里 13 秒后冻结。修：`mach-rockchip/sdram.c` 的
   `dram_init()` 加 sim 分支直接报 1 GiB（QEMU 机器事实）——U-Boot 显示
   `DRAM: 1 GiB`，内核 `Memory: 938736K/1046528K`。集成正道是把该补丁
   进 `boards/rk3568-atk/patches/uboot/`（后续课题，勿忘）。
2. **rootwait 永等（假冻结）**：修完内存后内核仍在 13s「冻结」——时间戳
   停走但串口回显还活着。真相：FIT 内置的是真板 DTB，**没有 virtio 节点**，
   `root=/dev/vda rootwait` 永远等不到盘；board 模式从未暴露此坑是因为它
   3.5s 就 poweroff 了，根本走不到 rootwait。修：bootm 三参形式用外部
   sim DTB 覆盖 FIT 内置 DTB——FIT 与 bootm 仍是真板同款，DTB 差异是
   sim 的 virtio 替身所致，诚实声明。

## 2. booti vs bootm（本线的知识点收口）

- `booti` = 裸 arm64 Image + 裸 DTB + 地址（uboot/linux 模式用的最简形态）
- `bootm` = 容器（uImage/**FIT**）——真板 bootcmd 的标准姿势
- 现在 sim 里两种都通：同一台 rk3568-lite，从裸 Image 到 FIT 全覆盖

## 3. 复现与交互

```bash
python3 boards/rk3568-atk/sim/boot-smoke.py fit --check
# 交互：boot-smoke.py 进 U-Boot 后手敲
#   => setenv bootargs 'console=ttyS2 root=/dev/vda rw rootwait init=/bin/sh panic=-1'
#   => bootm 0x20000000 - 0x0f000000
```

## 4. 提交闸门状态

六模式全绿（2026-08-26），bootm+FIT 闸门达成，可以提交。

## 5. 交差完善（同日，含一次方案纠正）

git status 审计发现两类缺口，均已补；期间用户指出 U-Boot 补丁方案会干扰
真板（无条件 `return 0` 把真板内存也钉死 1GiB）——**方案作废重做**：

1. ~~U-Boot 补丁~~ → **机器模型扮演 TPL**：PMUGRF 从全 1 应声虫升级为 RAM
   影子，预写 OS_REG2=0x60C0/OS_REG3=0（sdram.c 解码验算：1ch/1rank/DDR3/
   16row/9col/8bank/32bit = 1<<(16+9+3+0+2-20) MB = 1024MB）。U-Boot 零补丁、
   按真板流程解码出 `DRAM: 1 GiB`，真板零风险。uboot/fit 双 --check 重验绿。
2. QEMU 机器模型导出为 `sim/qemu-rk3568-lite.patch`（含 PMUGRF 影子），
   README 记录 clone+apply+build 流程。
3. **生成物自动重建**：dtb/cpio.gz 不入库，boot-smoke.py 自检新鲜度并自愈。
   删除两产物实测全绿。
