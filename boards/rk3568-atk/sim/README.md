# rk3568-atk sim 研究线

`rk3568-lite` 最小 QEMU 机器模型的配套资产。机器本体在 `third_party/qemu/`
（v11.1.0 浅克隆 fork，`hw/arm/rk3568-lite.c`）。完整叙事见
[notes/59](../../../document/notes/59-2026-08-24-rk3568-qemu-sim-m0-day0.md)～[65](../../../document/notes/65-2026-08-25-rk3568-sim-assets-python-port.md)。

**全部工具为纯 Python（仅标准库），Windows 原生可跑**（QEMU fork 需有对应
平台构建，Windows 侧待 MSYS2 编译，见笔记 65）。

| 文件 | 作用 |
|---|---|
| boot-smoke.py | 一键拉起，**双板**（`[rk3568-lite\|rk3588-lite] [模式] [--check]`） |
| build-initramfs.py | 纯 Python cpio 写 initramfs（不需要 fakeroot/cpio，确定性输出） |
| rk3568-lite.dts | 七节点最小 DTS，只描述已建模设备 |
| qemu-sim-machines.patch | rk3568-lite + rk3588-lite 双机器模型（对 QEMU v11.1.0 的补丁，构建前 `git apply`） |

`*.dtb` / `*.cpio.gz` 不入库（gitignore）：boot-smoke.py 启动时自动检查新鲜度并
重编（dtb 旧于 dts → cpp+dtc 重编；initramfs 旧于 rootfs → 重打），新克隆 +
`forge stage/build` 后即可直接拉起。

## 拉起（rk3568 线；rk3588 线见 ../rk3588-topeet/sim/）

```bash
python3 boards/rk3568-atk/sim/boot-smoke.py               # 交互直入 U-Boot（默认）
python3 boards/rk3568-atk/sim/boot-smoke.py linux         # 交互直入 Linux shell
python3 boards/rk3568-atk/sim/boot-smoke.py rootfs        # 交互（真根文件系统）
python3 boards/rk3568-atk/sim/boot-smoke.py <模式> --check # 冒烟断言（CI 形态）
```

| 模式 | 内容 |
|---|---|
| uboot（默认） | U-Boot shell；--check = booti 接力内核挂**整块 rootfs.ext4 真根**（四断言） |
| fit | **真板同款**：bootm 起 forge 的 FIT boot.img + 整块真根（四断言） |
| linux | initramfs Linux shell；--check = M0 三断言 |
| rootfs | virtio-blk 真根直启（无 U-Boot） |
| board | 真板 DTS（rk3568-atk-evb1-ddr4-v10）直启 |
| virt | Day-0 参考启动（QEMU 自带 virt 机器） |

fit 模式的 bootm 用三参形式 `bootm <FIT> - <sim DTB 地址>`：外部 sim DTB
覆盖 FIT 内置真板 DTB，因为 sim 的根盘是 virtio 替身（真板 DTB 无此节点，
rootwait 会永等）——FIT 文件与 bootm 命令与烧真板完全同款。

交互玩法（U-Boot → 整块 rootfs）：

```
python3 boards/rk3568-atk/sim/boot-smoke.py
（倒计时按任意键）
=> setenv bootargs 'console=ttyS2 root=/dev/vda rw rootwait init=/bin/sh panic=-1'
=> booti 0x02000000 - 0x0f000000
```
`Starting kernel ...` 后落在完整 rootfs 的 shell（全部用户态都在）。U-Boot 自己
看不见 virtio（真板 DTB 无此节点）——它只负责 booti，接力后的内核拿 sim DTB
里的 virtio 节点挂盘。

交互退出按 `Ctrl-A x`；`SMP=1` 降单核调试；`LOG=` 指定 --check 日志。
QEMU 自动发现：`third_party/qemu/build` 优先，PATH 兜底，`QEMU=` 可强制覆盖。

一次性构建（Linux/WSL）：

```bash
sudo apt install meson ninja-build libglib2.0-dev libpixman-1-dev device-tree-compiler
cd third_party/qemu
git clone --depth 1 --branch v11.1.0 https://github.com/qemu/qemu .   # 空目录时
git apply ../../boards/rk3568-atk/sim/qemu-sim-machines.patch         # 双机器模型
mkdir -p build && cd build && ../configure --target-list=aarch64-softmmu && ninja
```

U-Boot **零补丁**：DRAM 容量由机器模型扮演 TPL 预写 PMUGRF OS_REG（1 GiB
编码，`hw/arm/rk3568-lite.c` 注释有解码验算），U-Boot 按真板流程解码。注意
uboot 树里 baud/bootcmd 的 defconfig 改动是先于 sim 线的 working-tree 债
（与 linux series NOTE 同类，待 quilt 化）。弹药由 `forge build`/`forge stage` 产出。

调试惯例：QEMU 侧 `-d unimp,guest_errors` 是需求探测器（内核访问了哪些未建模
区域 = 下一个该做的设备）。未分配 MMIO **写**在 ARM TCG 下是 synchronous
external abort，不是静默忽略——哑铺图必须用 unimp。
