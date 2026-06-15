# RK3506B 固件写坏后的救砖记录：从 Loader 失效到 MaskROM 恢复

今天在给 RK3506B 板子做固件烧录和冒烟测试时，遇到了一个比较典型的 Rockchip 平台救砖场景：固件被写坏后，按住 Recovery 键已经无法让 RKDevTool 进入 Loader 模式。最开始看起来像是板子“砖了”，但最后确认并不是硬件损坏，而是启动链前段被破坏，导致普通 Loader 模式无法进入。

## 现象

正常情况下，RK3506B 板子连接 Windows 电脑，按住 Recovery 键再上电或者复位，RKDevTool 应该能识别到 Loader 设备，例如：

```text
Found One LOADER Device
```

但这次刷坏之后，重复按 Recovery 没有反应，RKDevTool 无法进入 Loader 模式。这个状态很容易让人误判为板子彻底坏了。

后来确认，Recovery 进入 Loader 通常依赖板子上的 bootloader / loader 仍然能正常工作。如果前面的 loader、parameter、uboot 或存储起始区域被写坏，Recovery 键就可能不再有效。

## 核心判断

Rockchip 平台还有一个更底层的救援模式：MaskROM。

Loader 模式可以理解为“板子上的启动程序还能跑起来”；而 MaskROM 模式则更底层，是芯片内部 BootROM 提供的 USB 下载模式。即使外部 NAND / eMMC / SPI-NAND 上的启动内容损坏，只要芯片本身和 USB 下载链路正常，通常仍然可以通过 MaskROM 重新刷回完整镜像。

所以这次的关键不是继续反复按 Recovery，而是让板子进入 MaskROM。

## 进入 MaskROM

不同 RK3506B 板子的进入方式可能不同。有些板子提供独立的 MaskROM / Boot 按键；有些板子需要短接启动存储相关测试点，让芯片启动时读不到外部存储，从而退回 MaskROM。

这次成功进入后，RKDevTool 显示：

```text
Found One MASKROM Device
```

看到这个提示基本就可以放心了：这不是死砖，而是已经进到了 Rockchip 的底层救砖入口。

## 恢复流程

进入 MaskROM 后，不建议继续单独刷 `boot.img`。救砖阶段应该优先使用板厂提供的完整固件包，也就是完整的 `update.img`，把 loader、uboot、parameter、boot、rootfs 等关键分区整体恢复回来。

实际操作思路如下：

```text
1. RKDevTool 识别到 Found One MASKROM Device
2. 选择 RK3506B 对应板子的完整 update.img
3. 如果工具要求加载 Loader，则选择对应的 MiniLoaderAll.bin
4. 先执行 EraseFlash / 擦除 Flash
5. 再执行 Upgrade / 升级
6. 等待烧录完成，断电重启
```

恢复完成后，板子重新正常启动，说明这次问题只是固件启动链写坏，并不是硬件损坏。

## 这次踩到的坑

这次最大的坑是把 Recovery 和 MaskROM 混在了一起。Recovery 进不了 Loader，并不代表板子彻底没救；它只说明当前存储中的启动程序可能已经无法正确执行。

真正的救援入口是 MaskROM。只要能进 MaskROM，通常就可以通过 RKDevTool 重新下发 loader，并把完整镜像刷回去。

另一个教训是，冒烟测试阶段不要轻易只刷局部镜像，尤其是在不确定分区布局、parameter、loader 和启动介质类型是否完全匹配时。比如只拿 `boot.img` 或不完整镜像乱刷，很容易把启动链搞坏。后续更稳妥的流程应该是：

```text
先用官方完整 update.img 确认板子可恢复
再备份当前可启动固件
最后再逐步替换 boot.img / kernel / rootfs 做验证
```

## 总结

这次 RK3506B 救砖的结论很简单：

```text
Recovery 进不去 Loader，不一定是死砖。
能进 MaskROM，就基本还有救。
救砖阶段优先刷完整 update.img，不要继续单刷 boot.img。
```

对于 Rockchip 平台来说，MaskROM 是非常关键的底层逃生通道。只要电脑还能识别到 MASKROM 设备，就应该先冷静下来，使用板厂匹配的 MiniLoader 和完整固件包恢复整机，再继续后续的内核、rootfs 或应用层调试。
