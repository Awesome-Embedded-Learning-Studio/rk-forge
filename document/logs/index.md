---
title: 板上日志
---

<PageHeader icon="📟" title="板上日志" description="真实 UART 抓取 + 构建日志——笔记与踩坑日记「绝不合成」承诺的底气" />

这里（`document/logs/`）是近百个真实的板上 UART 抓取 + 构建日志，是笔记和踩坑日记"绝不合成"承诺的底气。每个里程碑 log 对应佐证哪个坑，完整索引见 [logs/README](./README)。

> 这些 `.txt` 是原始串口 / 构建输出，站点上点开会在 GitHub 上查看（原样保留，不渲染）。

### 里程碑 log（近 → 远）

- [boot-sdl-202606211028.txt](boot-sdl-202606211028.txt) — SD 卡纯 ext4 启动收官（kernel + rootfs 都从 SD 起，无 ubi/panic）
- [boot-sdl-202606201050.txt](boot-sdl-202606201050.txt) — WiFi RTL8733BU 板上全链验证
- [boot-sdl-2026-06211109.txt](boot-sdl-2026-06211109.txt) — 全链主线启动到 `rk3506 login:`
- [boot-sdl-202606182049.txt](boot-sdl-202606182049.txt) — buildroot 最小 rootfs 首启到 login
