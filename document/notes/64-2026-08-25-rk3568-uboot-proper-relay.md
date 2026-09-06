# 64 — U-Boot proper 拉起 + booti 接力内核（2026-08-25）

> 启动链的中间层进仿真：u-boot.bin 以 `-bios` 直载（合法跳过 BROM/TPL/SPL/
> BL31 闭源段），U-Boot 走完 autoboot 进 shell，`booti` 把内核拉到 shell。
> 五个坑各有实锤，最后一个（U-Boot 堆踩预载 initrd）最有教学味。

## 0. 结论

| 项 | 结果 |
|---|---|
| U-Boot 拉起 | ✅ 2026.07-rc4 全流程：banner → SoC/DRAM 探测 → 设备枚举（606 devices）→ env → autoboot 倒计时 → `=>` shell |
| booti 接力 | ✅ 内核/initrd/DTB 预载 RAM，shell 里 `setenv bootargs` + `booti` → 内核到 shell → sentinel → 关机，三断言 PASS（`boot-smoke.py rk3568-lite uboot`） |
| 新模型 | OTP 最小模型（INT_STATUS done 位自置）；机器固件加载（ELF→raw 回退 + boot_info 接线）；has_el3 关闭 |
| 巧思 | U-Boot 吃**真板 DTB**，接力给内核的是**七节点 sim DTB**——bootloader 与内核各得其所 |

## 1. 五个坑

1. **`-bios` 没被加载**：arm_load_kernel 不管固件，加载是机器自己的责任
   （CPU 在地址 0 执行 DTB 魔数 `d00dfeed` 一眼定位）。
2. **firmware 路径不用 ELF 入口**：boot.c 注释明写「从地址 0 开始，
   env->boot_info 留 NULL」——机器载入 ELF 后需自己把 `boot_info` 接回去，
   `do_cpu_reset` 才会设 PC。
3. **OF_SEPARATE 的 DTB 不在 ELF 里**：U-Boot 找 `TEXT_BASE+0xb6438` 处的
   追加 DTB，只有 `u-boot.bin`（raw 拼接）有——ELF 失败回退 raw 裸载。
4. **EL3 与 SMC conduit 的隐藏规则**：内核在 `__primary_switched` 对着
   SMC #0 崩——QEMU 规则「SMC conduit 且固件入口在 EL3 → conduit 禁用」
   （boot.c 显式条款），且现代 U-Boot 已无 EL3→EL2 切换（`ARMV8_SWITCH_TO_EL2`
   Kconfig 已删除，真板这活 BL31 干）。**关 has_el3**：固件/内核都进 EL2
   （virt 同款姿势），SMC conduit 保留，全通。
5. **U-Boot 堆踩预载 initrd**：U-Boot 只看得见 192MB（无 TPL 告知 DRAM 大
   小，用了默认值），initrd 预载在 0x0a000000（视野内）被堆踩成垃圾——
   `Freeing initrd memory` 有、解包为空。搬到 0x20000000（视野外，和 DTB
   一样的待遇）后接力成功。

## 2. 附带收获

- OTP 最小模型（rockchip-otp.c 偏移）：SBPI@0x20 启动→INT_STATUS@0x304
  置 DONE 位，数据读零（`SoC: RK0000` 如实暴露「没烧 cpuid」）；不做这个
  `misc_init_r()` 等着超时。
- U-Boot 自己的探测把机器模型又考了一遍：CRU 影子让它过了时钟初始化
  （`rk3568_clk_set_rate gpll=0` 警告=影子如实回答垃圾速率，无害）。

## 3. 复现

```bash
QEMU=third_party/qemu/build/qemu-system-aarch64 \
  python3 boards/rk3568-atk/sim/boot-smoke.py rk3568-lite uboot
```

## 4. 升级：接力挂整块 rootfs（同日）

用户问「能不能挂整个 rootfs」——能，而且架构上就差一层窗户纸：U-Boot 看不见
virtio（真板 DTB 无节点），但接力后的内核吃 sim DTB（有 virtio 节点）。uboot
模式改为 `booti 0x02000000 - 0x0f000000`（无 initrd）+ `root=/dev/vda rw
rootwait`，内核接过接力棒直接挂**完整 459MB rootfs.ext4**——整板开机体验闭环：
U-Boot → booti → 内核 → 真根文件系统全量用户态。四断言 PASS。

## 5. 遗留

U-Boot 只认 192MB DRAM（无 TPL 传参，用了 evb 默认）→ 内核也只见 190MB，
够用但不体面；正解是给 U-Boot 传 sim 专用 DTB 的 memory 节点或调
CFG_SYS_SDRAM_SIZE。后续课题。
