# attic — 退役的取证/受控脚本

各战役的一次性工具，战役收官后移此归档（git 历史可溯，需要时移回
sim/ 即用）。现行工作面在 sim/：up/resboot/shot/smoke_monitor（启动
与观察）、serx/sendfile（串口）、verify_screen（内容判据）、
glestexture（受控回归守门员）、face/span/block_probe（note 114-115
staging 取证仪器）、snapshot+fbdump（战役六 vmstate 快照，9s 回桌面
=下役武器）、build-initramfs+initramfs（rk3568 线现役）。

| 脚本 | 出处 |
|---|---|
| glesclear/glesprobe/gbmprobe/gbmshim.c | M2c-M2e mesa 崩点/首像素取证 |
| glesblit/glesblitfb | M2h blit 受控 |
| glestriangle | M2l 常量色 FS 13/13（FSCOLOR） |
| elfnear | M2b 崩点 addr2line（mini readelf） |
| framehunt/klogdump | note 103-104 帧狩猎/内核日志环 |
| gdbfreezegrab | gdb 冻结抓取 |
| forensic_restore | note 85 多核 loadvm 锁死取证（已根修 f03d2bb） |
| sercmd | 串口客户端（被 serx.py 取代） |
