# 70 — systemd 上机：仿真里的 Ubuntu 26.04 完整开机（2026-08-27）

> 用户在真板 DTS + Ubuntu 合体 shell 里问「systemd 呢」——此前 `init=/bin/sh`
> 是冒烟的确定性捷径，systemd 从未被尝试。本篇让它真正开机：systemd 259 在
> rk3588-lite 上把 Ubuntu 26.04 拉到串口 login 提示符，三断言 PASS。

## 0. 结论

| 项 | 结果 |
|---|---|
| systemd 开机 | ✅ `boot-smoke.py rk3588-lite systemd --check` 三断言：running in system mode / Welcome to Ubuntu 26 / login: |
| 时间 | TCG 下约 4-5 分钟到登录提示符（8 vCPU；interactive 模式建议耐心） |
| 亮点 | 真板 DTB 的 DW 看门狗被 systemd 认领并喂养；hostname 正确 rk3588-topeet；graphical.target 正常排队（GNOME 起不来=无 GPU，符合预期） |
| 边界 | `init=/bin/sh`（rootfs 模式）保留为快速确定性路径——冒烟与全量开机两形态各司其职 |

## 1. 细节

- cmdline：`init=/sbin/init` + 其余与 rootfs 合体模式一致（真板 DTB + virtio
  真根 + cpuidle.off=1）。
- systemd 自动侦测 `console=ttyS2` 拉起 serial-getty → 串口直接出 login 提示
  （无需配置）。
- 首跑被镜像写锁咬了一口：前一个 --check 的 QEMU 残留攥着 rootfs.ext4——
  `ps` 清场即好（flock 随进程死释放，残影是竞态窗口）。
- 断言正则教训：别把版本号长度写死（`.{0,3}` 撞上 `259.5-0ubuntu3.4`），
  用短而稳的短语。

## 2. 复现

```bash
python3 boards/rk3568-atk/sim/boot-smoke.py rk3588-lite systemd --check   # 断言
python3 boards/rk3568-atk/sim/boot-smoke.py rk3588-lite systemd           # 交互看全程，login 等提示符
```
