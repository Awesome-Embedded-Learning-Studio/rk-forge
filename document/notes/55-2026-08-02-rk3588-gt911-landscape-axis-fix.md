# 55 — RK3588 TOPEET GT911 坐标范围修复（2026-08-02）

## 最终结论

触摸链路、IRQ 和触点生命周期均正常。错位的根因是 DTS 用 LCD 尺寸覆盖了 GT911 的
原生输入范围：

```dts
touchscreen-size-x = <1024>;
touchscreen-size-y = <600>;
```

GT911 配置寄存器 `0x8047` 实际返回：

```text
60 58 02 00 04 05 8d 00
```

- 配置版本：`0x60`；
- 原生 X 范围：`0x0258 = 600`；
- 原生 Y 范围：`0x0400 = 1024`。

这里的 600×1024 是控制器两个物理轴的数值分辨率，不代表触摸玻璃是竖屏安装。输入消费
端会分别归一化 X/Y 到 1024×600 显示区域，DTS 不能只改轴范围而不缩放事件值。

## 触点事件证据

原始 `/dev/input/event0` 记录包含完整的：

```text
ABS_MT_TRACKING_ID >= 0  → 按下
ABS_MT_POSITION_X/Y      → 坐标
SYN_REPORT               → 帧结束
ABS_MT_TRACKING_ID = -1  → 抬起
```

因此不是 IRQ 丢失、触点未释放或 `goodix_911_cfg.bin` 缺失。

## 被五点板验否定的第一次修复

候选 `2fa62f8f…` 删除尺寸覆盖后错误加入了 `touchscreen-swapped-x-y`。它的内核轴范围为
X `0..1023`、Y `0..599`，五点实测如下：

| 物理点击位置 | 事件 X | 事件 Y | 实际映射位置 |
|---|---:|---:|---|
| 左上 | 38 | 12 | 左上 |
| 右上 | 32 | 592 | 左下 |
| 右下 | 1015 | 591 | 右下 |
| 左下 | 1011 | 14 | 右上 |
| 中心 | 558 | 317 | 中心 |

这正是沿对角线转置的结果，证明 swap 生效但不应该存在。把上述坐标反交换即可还原芯片
原始数据：物理左右对应原生 X `0..599`，物理上下对应原生 Y `0..1023`，轴方向本来就是
正确的。此前仅凭键盘区域的一组事件断言“X 对应纵轴”是错误结论。

## 最终修复

GT911 节点既不覆盖尺寸，也不添加交换或反转属性：

```dts
reset-gpios = <&gpio3 RK_PC1 GPIO_ACTIVE_HIGH>;
status = "okay";
```

由主线 `goodix_read_config()` 发布真实的 X `0..599`、Y `0..1023` 范围，桌面输入栈再按
显示尺寸归一化。对应持久化补丁：

```text
patches/rk3588-topeet/linux/0010-arm64-dts-rk3588-topeet-fix-GT911-axis-mapping.patch
```

## Vendor 对照

Vendor `tp-size = <911>` 分支没有启用 X/Y 交换或反转。虽然 vendor 驱动编译时开启
`GTP_DRIVER_SEND_CFG`，但当前配置版本 `0x60`（96）大于等于 fixed-config 阈值 90，实际
保留芯片配置，不下发 `gtp_dat_gt11`。最终方案与该行为一致：不上传配置，不交换轴，只
删除主线 DTS 中不正确的范围覆盖。

## 上板验收

修复后内核报告的原生范围应为：

```text
kernel X range: (0, 599)
kernel Y range: (0, 1023)
```

五点物理点击的原始值应近似为：

```text
左上  (0, 0)
右上  (599, 0)
右下  (599, 1023)
左下  (0, 1023)
中心  (300, 512)
```

最终还要直接验证 GNOME 虚拟键盘、拖动和多点触控，不能只凭 input 设备注册成功宣称完成。

## 构建产物

最终无 swap 候选已完成 kernel、FIT、RKAF+RKFW assemble 和 round-trip 自检：

```text
rk3588-topeet.dtb  282e630c0303ed417985ca1f98c0d3b0a8f4bfab901a49c004e9d765565b95a5
boot.img           9b738b027129e39a39ea61de57902dd268744c7bb6631914b90c04d3d43e3c8c
update.img         af26a389b66496cf3f216a65134d2194df618f1a43f69030f4ede20ba26fcba6
```

`update.img` 大小为 `3290329674` 字节。DTB 反编译确认 GT911 节点不存在
`touchscreen-size-*`、`touchscreen-swapped-x-y` 或 `touchscreen-inverted-*`。

`2fa62f8f…` 是已被五点数据否决的 swap 候选，不得继续烧录。

后续 [56](56-2026-08-02-rk3588-ubuntu-user-rootfs-ownership.md) 修复了桌面用户和 ext4
ownership；其 `d100a898…` 镜像保持本章相同的无 swap DT，并取代缺用户的 `af26a389…`。
