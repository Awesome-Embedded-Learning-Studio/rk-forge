# document/logs/ — 板上取证日志

这里近百个文件,全是 RK3506B 真板上电实跑的原始 UART 抓取加构建日志,没有一个是合成的。它们是 [pitfalls/](../pitfalls/) 和 [notes/](../notes/) 里那些"成功长这样""失败长那样"的底气——每个结论背后都能翻出一行对应的串口原文。

## 命名约定

`boot-sdl-YYYYMMDDHHMM.txt` 是板上 UART 抓取(SDL = Serial Debug Log),文件名时间戳就是抓的那一轮。有几个带后缀,标的是那一轮烧的镜像内容:`-kernel-7.1` / `-with-kernel` 是带 kernel 的某轮,`-powergood-wpen-fix` 是 powergood+WPEN 修复镜像,`-OURkernel-VENDORrootfs` 是那场决定性 A/B 实验(我们内核 + vendor rootfs)。构建类另算:`build-*.log` 是内核/uboot/stage 构建,还有 `lunch.txt`、`problem1.txt`、`uboot-debug.txt`、`host-deps-ubuntu24.txt`。

## 里程碑 / 证据级(被 pitfalls、notes 引用)

下面这些是真正被踩坑日记和笔记引用的"证据 log",按佐证哪个坑标了出来。表里的 ecc 是 `error -74/ECC error` 出现次数、rec 是 `recovery completed` 次数、bad 是 `Bad hash` 次数,扫出来供参考。

| 日志 | 关键标志 | 佐证 |
|---|---|---|
| boot-sdl-202606142037.txt | optee `93603ca22c` + OK,fwver v2.10 | 坑 #2/#3 成功侧(tee v2.10 + vendor mkimage 被接受) |
| boot-sdl-202606152121.txt | optee Bad hash `616f8152` → 换 fit 后 OK | 坑 #2 失败侧(tee v2.40 撞锁) |
| boot-sdl-202606152144.txt | optee Bad hash `7b78fe4e` → 换 fit 后 OK | 坑 #3 失败侧(主线 mkimage 错位) |
| boot-sdl-202606142052.txt | U-Boot 2026.07-rc4 进提示符 | note04 第二次进提示符里程碑 |
| boot-sdl-stage-end-of-kernel-uboot-202606151100.txt | 7.0.12 到 shell | note07/sdk-diff 内核+uboot 定型 |
| boot-sdl-2026-06151834.txt | 7.1.0,DT 7 分区全见 | note10 / 坑 #7 正确 boot 姿势(0x04000000) |
| boot-sdl-2026-0615955.txt | `image overwritten` RESET | 坑 #7 失败侧(FIT 暂存撞 kernel load) |
| boot-sdl-202606150723.txt | mtd read corrupt | note05 / 坑 #5 段1 读 corrupt 现场 |
| boot-sdl-202606160948.txt | dll window [0,230] | 坑 #5 读路径 DLL 移植首次证据 |
| boot-sdl-202606161244.txt | PBA=10300 bad block skip | 坑 #8 出厂坏块铁证 |
| boot-sdl-2026-06162015.txt | PEB 3/4/30 error -74 → panic | 坑 #5 段5 / #6 saga 核心失败现场 |
| boot-sdl-202606161120.txt | PROBE WRITE 全 peb=1000+ | 坑 #6 坏数据是 loader 存量 |
| boot-sdl-202606162146-...VENDORrootfs.txt | 0 ECC,recovery completed | **坑 #6 A/B 决定性证据**(vendor rootfs 跨重启干净) |
| boot-sdl-202606162143-powergood-wpen-fix.txt | 18 ECC,PEB 仍炸 | 坑 #5 段5(powergood+WPEN 不够) |
| boot-sdl-202606162243.txt | ubiprog skipped(uncorr)=2,devtmpfs 刷错 | 坑 #12 容忍态 + 坑 #11 失败侧 |
| boot-sdl-202606162254.txt | recovery ×2,/persist.log c1/c2 | 坑 #11 修复后 + 坑 #12 RW 达成 |
| boot-sdl-202606162310.txt | recovered(page-level)=2,5× recovery | 坑 #12 页级恢复版(修干净) |
| atk-standard-boot.txt | 6.1.118,recovery completed | vendor 标准 RW UBIFS 稳的存在性证明(坑 #6 对照) |

## saga 调试轮(ECC 错密集的失败中间态)

boot-sdl-202606152246 / 202606160139 / 202606160838 / 202606161033(单轮 145 处 ECC)——这些是 saga 期间 RW 写崩的各轮失败调试,ECC 错密集,中间态居多(其中 202606160948 同时是 DLL 首证,见上)。

## 早期探索轮

boot-sdl-202606141908/1933(vendor uboot 2017.09 早期)、202606142336、202606151001-with-kernel/1016/1234(7.0.12 内核早期)、2026-06151312-kernel-7.1 / 52219(7.1 早期)、202606160044/0101、202606161212/1812/2118/2221,以及 boot-sdl-hash-check-at202606161133(chip-tag / hash 调试轮)。

## 构建 / 主机日志

build-kernel.log、build-uboot.log、build-rk3506-stage1{,b,2}.log、build-rk3308-baseline.log 是构建日志(vendor 全绝对路径 CROSS_COMPILE 的正面参照,坑 #9);lunch.txt、problem1.txt、uboot-debug.txt(U-Boot dump)、host-deps-ubuntu24.txt(主机依赖)是杂项。
