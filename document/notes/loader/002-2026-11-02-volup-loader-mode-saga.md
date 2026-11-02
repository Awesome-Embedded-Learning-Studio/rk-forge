# loader/002 — vol-up→LOADER 十补丁收官(2026-11-02 深夜板验通过)

> 目标:按住 vol-up+电源,咱们自己的主线 u-boot 直进 Loader 模式,RKDevTool 认成「LOADER设备」。
> 从 0007 到 0010 四发补丁、两轮 GPT 会诊(用户中转)、三轮板测,全链打通。
> 前史:notes/123(0004-0006 铺路)、notes/loader/001(ddrbin 逆向定谳:开关=BROM strap,按键之路只剩 ADC)。

## 0. 终局

| 层 | 机制 | 补丁 |
|---|---|---|
| 按键检测 | SARADC ch1 梯底档 vol-up(raw≤128 窗口;节点名 adc@fec10000 需 compatible 匹配) | 0007 |
| 执行开关 | **CONFIG_USE_PREBOOT**——不开则 main_loop 跳过 preboot,一切 env_set("preboot") 都是死信 | 0007 |
| 设备身份 | **PID 300a**(vendor usbplug 同款,350b=BROM maskrom 牌) | 0008 |
| 分类指纹 | **bcdUSB 0x0201**(Rockchip 工具按它分 maskrom/loader;vendor 注释原文) | 0009 |
| Windows 枚举 | 0x0201 义务应答 **BOS**;USB2 链路回 12B USB2-Extension cap(bmAttributes=0),否则 rockusb.sys 启动即 code 10/C000000E | 0010 |

## 1. 迭代史(每版一头栽在一个新层上)

- **v1/v2**(g0577da65377b):ADC 三件套齐,板测正常启动——根因 USE_PREBOOT 未开(GPT 会诊#1,本地三重坐实:.config:552/main.c:54/defconfig)。**连带翻案:reboot loader 在此链上从未真正工作过**(notes/123 §0 已改)
- **v3**(gf13c8057d41c,+USE_PREBOOT+CMD_ADC):板测命中——串口 `download key pressed, entering Loader mode (rockusb)` 后静默蹲守(rockusb 循环无声,勿当死机)。但 RKDevTool 标「MASKROM设备」
- **v4**(g09ecd1db,+0008 PID 300a):Windows 读到 300a、绑 rockusb.sys,但 **code 10/C000000E**(STATUS_NO_SUCH_DEVICE,驱动启动期 USB 请求失败)
- **v5**(gd4cbc225f4f9,+0009 bcdUSB 0201):仍 code 10——GPT 会诊#2 定位 BOS 缺口:0x0201 义务应答 BOS,而 mainline 只在 SuperSpeed 答;Windows 8+ 枚举即问,STALL 打死驱动(vendor composite.c 有同款 workaround 注释)
- **v6**(ged8485d0,+0010 USB2 BOS):**板验通过**——code 10 消失,RKDevTool 认 LOADER,收官

## 2. 0010 里比会诊模板多堵的坑

mainline `bos_desc()` 的超速 cap 组挂在 `gadget_is_superspeed()`——判的是**驱动能力**(dwc3 天生 SS-capable)非**链路速度**;直接开门会在 HS 链路上谎报 SS caps + LPM/BESL。0010 按链路速度分流,USB2 只回 bmAttributes=0 的干净 12B cap。

## 3. 工艺与协作账

- 会诊模式成形:我写自包含 prompt(背景/已验锚点/问题清单)→ 用户粘给 GPT → 其断言回来**本地验尸**(每条对着源码/二进制复跑)→ 修法落成补丁。两轮会诊三个根因(USE_PREBOOT/bcdUSB/BOS),全部本地坐实后才动刀
- 补丁工艺:真改树→commit→format-patch→reset→forge apply 从 pin 重放(规避手织 hunk);内容门禁:版本串+关键字节(objdump/strings/字节扫描)
- 工艺事故(已记 loader/001 §8):复合命令在仓库根误跑 `git reset --hard` 冲掉未提交 guard——**多仓操作 reset 必须 `git -C <tree>`**

## 4. 遗留(小)

- `reboot loader` 与按键同走 preboot,理论同修,未单独板验——下次顺手验
- f_rockusb 多条 vendor 命令未实现(READ_FLASH_INFO→cb_not_support 等);本次 GUI 认设备+流程未撞上,若日后升级动作卡住,按报错抓包补最小 CBW
- CMD_ADC 板面诊断命令随 0007 常驻(`adc single adc@fec10000 1` 实测梯子)

取证:.claude/loader/(GPT 两轮 reply、会诊 prompt、dsh-001、basic-forensics-001);series 0007-0010 含决策注释。
