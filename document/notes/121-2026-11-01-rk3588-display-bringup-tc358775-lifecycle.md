# 121 — RK3588 显示 bringup 收官:TC358775 桥生命周期 bug 与补丁栈整合(2026-11-01)

> 接 120。V0PLL 修复后系统全活但面板零像素,三轮排查(GPT 会诊 5/6)+
> 一次结构修复收官。终态:24 张正式补丁,显示/eth/NFS 三绿。

## 1. 症状与排查链(R32-R34)

症状:面板**从第一次 modeset 起只有背光、零像素**(早前「fbcon 有字」
的记忆是错的,已纠正)。逐项排除:

| 项 | 证据 | 判决 |
|---|---|---|
| 背光 | echo 64/0 有明暗变化,PWM enabled 78% | 无辜 |
| DT 状态 | 源/dtb/runtime 三重核验全 okay | 无辜 |
| gdm/会话 | autologin rk-forge(uid1000)完整桌面,DBus 全活 | 无辜 |
| GPU | egl-readback:Mali-G610(Panthor)GLES3.1 shader+读回 PASS | 无辜 |
| AFBC | noafbc 传导确认+modifier=0 仍黑 | 无辜 |
| CSC | 源码核 XR24+RGB 输出 y2r=r2y=0 | 无辜 |
| CPU 直扫 | 自写 kmsdraw(dumb buffer+SetCrtc)frame×12 全成功仍黑 | 无辜 |
| DSI 协议 | EOT/LPM/timing/极性/lanes 逐维对齐 vendor(含 EOT_PACKET 语义反转陷阱) | 无差异 |

工具沉淀:`dyn/kmsdraw.c`(零依赖 KMS 测试图,交叉编译进
`/var/tmp/`)、`dyn/egl-readback.c`(GPT 提供,surfaceless EGL 读回)。

## 2. 根因(GPT 会诊 6 定位,R34 板验)

**桥是 Toshiba TC358775**——blob 寄存器图与主线 `drivers/gpu/drm/bridge/
tc358775.c` 逐字吻合(PPI_LANEENABLE 0x0134/DSI_STARTDSI 0x0204/VFUEN
0x0464/LVCFG 0x049c);该家族**不支持 DCS short write**(vendor 四块 LVDS
桥屏 blob 全无 DCS 是系统性设计,不是漏写;「补 11/29」假设死亡)。

**生命周期 bug**:0001 把 init blob 放在 panel `.enable()` 发送,而 DRM
桥顺序里这发生在 `dw_mipi_dsi2_bridge_atomic_enable()` 已把 host 切到
VIDEO 模式**之后**——返回 0 只证明 host LP 插入命令走完 FIFO,不证明桥
锁存了配置。修复:init 搬到 `.prepare()`(此时 host 在 command 模式)+
`prepare_prev_first = true` 保证 host 先就绪;失败路径撤销上电/复位。
R34 上板:**屏幕点亮**,GNOME 桌面上屏。

附:vendor blob 的 HTIM/VTIM(hbp=160/hsync=20/hfp=160)与 host mode
(hbp=100/hsync=10/hfp=1580)不同是设计使然——桥从自身寄存器再生输出
时序,host 侧时序只是传输载体(这就是 82MHz/hfp=1580「怪 mode」的由来)。
上游先例:RK3588 Tiger SoM DSI0→TC358775→LVDS 在 v6.12 主线工作正常
(lkml 2024-11-20),架构组合本就可行。

## 3. 补丁栈整合(2026-11-01 结案)

- **0034(init-in-prepare)折叠进 0001**:面板驱动生而正确,无诊断残留
- **0033(V0PLL 重父)折叠进 0009**:含完整 rationale 注释
  (82MHz 除不尽 GPLL→SET_RATE_PARENT 传播重锁共享 PLL→php 岛楔死,
  见 118-120;Andy Yan lkml 2025-03-12 同族)
- 0030/0031/0032 全部注释退役(文件留档);0022/0026/0029 同前
- **终态 24 张**:0001-0006,0009-0021,0023-0025,0027,0028
- 终态镜像 `7.1.0-00024-ga7dad2806329`(8cd9520d→a7dad280,
  DBG30/32/34 零残留,dtb 显示全家 okay+parents=0 33 3)

## 4. 板侧清理(用户操作)

- `rm /run/systemd/user/org.gnome.Shell@.service.d/90-rk-black-debug.conf`
- `/etc/environment` 删 `PAN_MESA_DEBUG=noafbc` 行
- NFS 切换软链:`out/rk3588-topeet/nfsroot`(现指 ubuntu-rootfs.work;
  切回 buildroot:`ln -sfn rootfs nfsroot && sudo exportfs -ra`)

## 5. 待办

- R35:终态镜像验证轮(NFS,三绿确认)→ 按 118 §4 出烧录镜像
- eMMC 正式镜像=rootfs.ext4(buildroot);Ubuntu 桌面暂走 NFS
- 板上旧调试残留(见 §4)与镜像同轮清掉

## 6. 教训增量

- **DRM 生命周期**:panel init 必须在 host command 模式窗口内
  (prepare+prepare_prev_first);「返回 0」≠「远端锁存」
- DCS opcode 0x29 与传输类型 0x29(generic long write)是两回事;
  桥家族可能根本不支持 DCS short write——补丁前提要查芯片手册
- vendor flag 名不可信:MIPI_DSI_MODE_EOT_PACKET(vendor)与
  MIPI_DSI_MODE_NO_EOT_PACKET(主线)同 bit 同义——名字像、语义要核码
- debugfs/脚本的 `2>/dev/null || 兜底文案` 会把「文件没找到」伪装成
  「无属性=默认值」——假阴性输出比没有输出更危险
- Ubuntu minimized 的 /tmp 是 tmpfs,给板子放文件用导出树的 /var/tmp
- systemd 软渲染测试必须核对新 PID 的 environ(可能 shell 都没起来)

## 6b. eMMC 终验与打包(2026-11-01 晚,finish/1.txt)

update.img MD5 `10e6e29d…`(--00024 ga7dad280,bootargs 无拐棍,boot.scr=eMMC root),
烧录后:**0.81s 面板出画、login 可达、cpufreq -517→0.43s 重试成功、零 Oops**。
缺陷新账:①buildroot 最小 rootfs **无 rtw88 固件**→WiFi probe -22(回归:8 月
Ubuntu rootfs 有);②goodix_911_cfg.bin 缺(触摸降 OTP 配置待验);
③regulatory.db 缺。打包工序教训:④NFS-root 轮在 rootfs 树种 root 属主残留
(seedrng 700 目录),mke2fs -d 卡死——**pack-emmc 前必须 `find -user root` 清场**
(root 属主 700 目录 rm/mv 都不行,只能 sudo);⑤assemble 会拿 pack 失败的
半成品 rootfs.ext4 组出「自检 OK」的坏 update.img——roundtrip 仍只验封装,
内容级终验(grep 版本串/bootargs/DBG 计数)必须手工或固化成门禁。

## 7. 资产坐标

- 修复:0001(重构后)、0009(重构后);0033/0034 文件留档未删
- 会诊:dyn/gpt-consult-005/006(-review);工具:dyn/kmsdraw.c、
  dyn/egl-readback.c(+已编 binaries 于 ubuntu 树 /var/tmp)
- 日志:document/logs/rk3588/vop/{1,2,3}.txt;email.txt(Andy Yan 线程)
- 桥参考资料:主线 tc358775.c;TC358774/775 datasheet(firefly 存档)
