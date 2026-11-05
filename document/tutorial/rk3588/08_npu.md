# NPU 收官：原厂驱动进主线，自研运行时逐字节对拍

> [外设章](07_peripherals.md) 把 WiFi 和 DVFS 都收了尾，NPU 还躺在咱们的待办清单上，当时的口径是主线 Rocket 驱动在、CONFIG 未开。这一章咱们把它真正收进来，而且收的不只是内核里的一发驱动。整件事咱们看成一条链：一头是把原厂的 GPL 内核驱动移植进主线，另一头咱们用 C++ 自研 librknnrt 的兼容运行时，把原厂的闭源用户态换掉，最后咱们在板上拿九个模型跟原厂闭源库逐字节对拍。工程的时序咱们也照实交代：用户态的逆向 2026-10-31 就收了官，而内核驱动到 11-03 才动工，因为 qemu 里的假内核让咱们在板子不在手边的日子里，照样把闭源库翻了个透。

## 本章定位：最后一块大件，一头在内核一头在用户态

RK3588 的 NPU 咱们用白话交代：它是 SoC 里专门跑神经网络推理的加速器电路，全卷咱们念叨到现在它一直没出场，而它在 RK3588 上的规模是三个核。跑在它身上的软件栈，原厂给它起的名字叫 RKNN，咱们把整条链画在下面（[notes/rknn/001](../../notes/rknn/001-2026-10-31-rknn-闭源边界与逆向开工.md) 的原文就是这么记的）：

```text
训练模型 → ONNX → rknn-toolkit2(PC,闭源) → .rknn →
librknnrt.so(板端,闭源) → 内核驱动(GPL) → NPU 硬件
```

链条上的闭源边界，咱们在 reference 目录里逐件查过：

| 件 | 状态 | 咱们手里的位置 |
|---|---|---|
| librknnrt.so 1.5.0（4.8MB，2023-05-25 构建） | 闭源，librknn_api.so 只是它的软链 | reference 的 rknpu2 运行时目录 |
| rknn-toolkit2（PC 端编译器） | 闭源，仓库里只有 PDF 手册 | 无本地件 |
| 内核驱动 drivers/rknpu | GPL-2.0 全源码，写自 5.10.198 树 | reference 的 kernel/drivers/rknpu/ |
| rknn_api.h 与 rknpu_ioctl.h | 开放，逆向用户态的两本字典 | reference 的 rknpu2 运行时目录与 kernel/drivers/rknpu/ 两处 |

内核驱动咱们补一句白话：它其实不懂神经网络，管的只是内存、IOMMU、任务提交这些杂活，网络到 NPU 指令的编译在 PC 端就做完了。所以闭源的部分卡在两头，一头是板上的 librknnrt，另一头是 PC 上的 toolkit2。主线这边的情况咱们也摸过：社区的 rocket 驱动 6.18 就进了主线，咱们 7.1 的树里就有（这棵树后来 rebase 到了 7.3.1，外设章的 rebase 一节有交代），用户态配套的是 Mesa 的 Teflon，也就是 25.3 起可用的 TFLite delegate。它是 Collabora 的正向重写路线，绕开了 .rknn 生态、改吃 TFLite 模型，当下的能力有四条：

- 仅加速 INT8 per-tensor 卷积，其余算子落回 CPU
- 时钟被固定在 200MHz
- 单模型限用一个核
- reset 不可靠

咱们动手之前，把原厂移植路线的断点预判了一遍，出处是 [notes/rknn/001](../../notes/rknn/001-2026-10-31-rknn-闭源边界与逆向开工.md)：7.1 的树里 `gem_free_object_unlocked` 与 `gem_prime_export` 这类成员已经删了，得迁到 drm_gem_object_funcs 的接口上，DT 还得补原厂的单节点、跟主线的三节点冲突。

咱们面前的路线于是有了两条。一条是主线 rocket 加 Teflon 的组合，零闭源件、主线的 dtsi 节点现成、NPU 的供电轨 rk860x 内核章也早已移植，但 .rknn 模型一个都跑不了，加速的范围也窄。另一条是把原厂的生态整个搬进主线，内核驱动有 GPL 的源码可以移植，用户态的闭源 blob（二进制大块文件）咱们自己写一个兼容实现换掉它。咱们选了后一条，图的有两层：手里的 .rknn 模型与原厂工具链的产物，在这块主线的板上要原样能跑，而自研运行时还给了一套验证的办法，咱们拿原厂库当 oracle。oracle 咱们译作对照基准，同一边界上原厂闭源库的输出就是标准答案，咱们的实现逐项对上了才算数。本章反复出现的验收词 byte-exact，它的定义咱们留到主戏一里定门槛的地方再给。

时序上有一处咱们提前说明，免得读者按章序误会：用户态的逆向与自研引擎，2026-10-31 就在开发机上收了官（[notes/rknn/001](../../notes/rknn/001-2026-10-31-rknn-闭源边界与逆向开工.md) 到 [008](../../notes/rknn/008-2026-10-31-模型zoo实测与多输出收敛.md)），那时主线内核里还没有 NPU 的影子，咱们的实验场是 qemu 里的假内核。而内核驱动 11-03 才移植上主线，板上的验收链从那时开始（[009](../../notes/rknn/009-2026-11-03-legacy-GEM内存同步修正与板验.md) 到 [016](../../notes/rknn/016-2026-11-04-运行时CMake与现代C++整理.md)）。所以本章的主戏顺序也是用户态在前、内核在后，咱们按工程的实情走。本章的路线列成清单：

- 主戏一：逆向与自研运行时，qemu 里拿到逐字节一致（notes/rknn/001 到 008）
- 主戏二：驱动移植 0036 到 0038，legacy 设备表面与同步修正
- 主戏三：板级资源与多媒体核 0039 到 0042，八核实板验收
- 收官：九模型板验、假证据复盘与工程整理

## 主戏一：逆向开工，qemu 里拿到逐字节一致

### 弹药盘点：模型格式与社区的前茬

咱们动工之前，把社区的存量盘点了一遍（[notes/rknn/001](../../notes/rknn/001-2026-10-31-rknn-闭源边界与逆向开工.md) 的调研）。Netron 的 rknn.js 里有 .rknn 容器的完整规格，1.5.0 时代的文件是外层头、内嵌二进制段加一段明文 JSON 图段，容器解析几乎是白送的。phhusson 的逆向日记留下了观测，用的是 2023 年的板上 strace（系统调用跟踪），每个模型的六块设备内存缓冲，外加原生的 NC1HWC2 五维数据排布。NC1HWC2 咱们一个字母一个字母念：N 是批，C1 和 C2 是把通道数截成的两截，中间夹着的就是 H 高 W 宽。NPU 的数据通路按 4 个通道一组搬运，咱们把通道截成两截再拼起来，搬运也就对得齐了。mtx512 的项目更狠，作者绕开 librknnrt 自己写了命令流，把 llama2.c 跑上了 NPU，等于把开源引擎的可行性证明了。还有一件咱们本机就验过的宝：闭源 blob 认几个环境变量，`RKNN_DUMP_TXT_TENSOR` 能让它把每层的中间张量写成文件，天然就是逐层对拍的参考答案。

### 装置：假装有一颗 NPU

qemu 装置是整条逆向线的地基，构成咱们照 [notes/rknn/003](../../notes/rknn/003-2026-10-31-P1动态对账全绿.md) 里记的摆：qemu-aarch64-static 在 x86 开发机上直接跑 ARM64 程序，rootfs 当作咱们的 sysroot，libstdc++ 咱们从里面取。一个 LD_PRELOAD 桩库（LD_PRELOAD 是让动态链接器提前加载咱们的库的环境变量）拦下 open、ioctl、mmap 这些调用，假装 /dev/rknpu 是存在的，memfd 顶替了真内存。测试壳 harness 直链的是 librknn_api，从 rknn_init 一路跑到了 rknn_destroy，完整的生命周期咱们走一遍。模型是本机 venv 里 toolkit2 1.5.0 转出的 mobilenetv2_fp.rknn，7.7MB 的大小，权重是随机初始化的，版本是严格配对的。这个随机权重的伏笔，咱们到板验的段落再收。

假内核过了三道关，每一关咱们都捞到一个真发现。驱动版本关的门槛，咱们应答 GET_DRV_VERSION 得为 908（就是 0.9.8），而且大于 799 时运行时走新 ABI，40 字节的 MEM_CREATE 加 104 字节的 SUBMIT。硬件版本关：GET_HW_VERSION 的应答值就是平台枚举本身，RK3588 对应的值是 0x46495245，它的 ASCII 读法恰好是 FIRE。内存映射关：legacy 的 MEM_CREATE 返回的根本是 dma-buf fd，咱们读内核 rknpu_mem.c 才悟出来，桩改用了 memfd 加 ftruncate 来顶替，这一关咱们才过得去。

### P1 对拍：静态推演加动态普查

静态侧咱们靠 Ghidra 加一个分析 agent 把 blob 的调用链拆解，函数清单咱们清点出 4123 个（[notes/rknn/002](../../notes/rknn/002-2026-10-31-工具链落地与P1双产出.md)），导出符号 778 个里 rknn_ 前缀的有 28 个。它推演出的六个 ioctl 号，咱们拿本地 rknpu_ioctl.h 逐条核对全部对上，没有一条是编的。真正定量的一步在动态：假内核里把全生命周期的 ioctl 普查了一遍，与静态预测对上大半、也修正了三条（[notes/rknn/003](../../notes/rknn/003-2026-10-31-P1动态对账全绿.md)）。ioctl 咱们补一句白话，就是用户态程序向内核驱动发命令的系统调用。六个号咱们数得出，连成了一串：ACTION、SUBMIT、MEM_CREATE，再加上的就是 MEM_MAP、MEM_DESTROY、MEM_SYNC。普查表里咱们却只数出五行，因为版本查询两关走的都是 ACTION 的不同请求位，一并计进了 12 次探针里。剩下的 MEM_MAP，blob 是一个都没发的，咱们记下的次数是零。实测的结果如下：

| ioctl | 实测次数 | 与静态预测的对照 |
|---|---|---|
| ACTION 探针 | 12 | 吻合 |
| MEM_CREATE（40 字节） | 6 | 六次全部在 init 内，惰性创建的假设被推翻 |
| MEM_DESTROY | 6 | 与创建完美配对 |
| MEM_SYNC | 123 | 远超预期，权重刷写占了 110 次 |
| SUBMIT（104 字节） | 1 | run 时单发，吻合 |

MEM_SYNC 的 123 次咱们分开数，init 一头占了 117 次，run 一头只出了 6 次，init 那拨里有 110 次是逐权重张量的 TO_DEVICE 刷写。TO_DEVICE 是把 CPU 写好的缓存刷给设备，方向位的完整语义，咱们到主戏二讲同步病例时再展开。

咱们实测拿到六块 GEM，大小与标记的清单就在下面。GEM 是 DRM 内核子系统的内存对象机制，每块设备内存都配了自己的句柄，驱动和用户态的互相指认，靠的就是句柄。IOMMU 的活是给设备做地址翻译，让物理上散着的页在设备眼里连续：

```text
gem1  7543744B  flags 0x3   weight    权重
gem2   566144B  flags 0x5   regcmd    64 位宽的指令流
gem3    22440B  flags 0xb   task      任务表,561 行 × 40 字节
gem4  3411968B  flags 0x3   internal  工作内存
gem5   301056B  flags 0x3   input     1×3×224×224×fp16,精确吻合
gem6     2048B  flags 0x3   output    1000 类 × fp16
```

六块的总数与 phhusson 2023 年板上 strace 的观测一致，咱们等于拿到了静态、动态、第三方三方的互证。SUBMIT 的 104 字节咱们也逐字段解了码，超时的公式实测修正为 `max(30×单 lane 任务数, 6000ms)`。lane 是挂在某个核上的任务通道，公式按一条 lane 的任务数算，不按三核的总数。run 传进来的 3000 在 RK3588 的 v2(FIRE)平台分支里直接被丢弃，这跟驱动版本大于 799 的新 ABI 分叉是两根轴。

### P2：NNBG 是 FlatBuffers，指令模板就在模型里

容器 dumper 咱们一发跑通后，架构级的发现就冒出来了（[notes/rknn/003](../../notes/rknn/003-2026-10-31-P1动态对账全绿.md)）：1.5.0 的 .rknn 是 JSON 元数据加一个名叫 NNBG 的节点，整张网络图离线编译成一段 7.5MB 的二进制塞在这个节点里。仓库的 README 把它写作 NN_BG，两种拼写指的是同一个东西，都是这段离线编译好的网络图二进制。librknnrt 的本质于是清楚了，它干的活就是加载器加提交器，真正的编译在 PC 端的 toolkit2 里早做完了。P2 的硬骨头就是把这段二进制的文法读出来，过程咱们记在 [notes/rknn/004](../../notes/rknn/004-2026-10-31-P2装配机制全解码.md) 与 [005](../../notes/rknn/005-2026-10-31-NNBG-schema定案.md)。

第一层发现：NNBG 段是 FlatBuffers（一种零拷贝的序列化格式），六张表 root、graph、tensor、op、edge、blob 把图描述完整撑起来了，字段咱们逐个拆到了有证据的深度。到了第二层，发现就更好玩了，咱们看到 task 表的 561 行其实是三套核数方案，内核按选核的结果取其中一段。表里的 mask 是逐位选核的位掩码，咱们选中几个 bit，内核就取几核的方案：

| 段 | 行数 | lane 分布 | 语义 | 选核实测 |
|---|---|---|---|---|
| A | 246 | 0/1/2 各 82 | 三核联动，AUTO 默认 | mask=0 提交整段 246 行 |
| B | 137 | 0:71 / 1:66 | 两核方案 | mask=3 从 246 行起取 132 行（66×2） |
| C | 178 | 0:64 / 1:57 / 2:57 | 三核非联动 | mask=7 从 383 行起取 171 行（57×3） |

取行数咱们按各 lane 的最小行数来，B 段 137 行里取的是 132，C 段 178 行里取的是 171，各 lane 行数不齐的尾巴就舍掉了。

第三层发现咱们直接说，指令模板的原文就在模型里。权重 GEM 的尾部连着一块模板池，池里的 395 个槽被 561 行任务复用，运行时干的活是模板拷贝加三类回填，lane 位、地址、槽尾的 4 包 PC trailer 各回各的。trailer 白话说就是每段任务末尾追加的接力包，4 个包里的头一个写下一段的地址，链到末尾一块的时候，写的 0 就表示终止。地址槽在模型里存的是符号 0，加载期才回填成真实的 IOVA，也就是 IOMMU 映射出来的总线地址。差异的量咱们两头量过：单抽一个 128 包的槽，模板与运行期包只有 12 处是不同的。全量盘下来的时候，395 个模板 blob 的差异一共也只有 5771 字节，这才是要复刻的完整靶面。最后还差两笔推算的公式，gem1 的打包按 64 字节对齐一路累加，行数咱们也验过，`561 = 82×3(A) + (68+68+1)(B) + (59×3+1)(C)`，解析器按公式重建 task 表做到了 561 行零失配。公式咱们按模板的生成序累加，一条边在一条 lane 上记的就是一行。上面表里的 lane 分布，则是 dump 实测的、每行落在哪条核通道上的计数。两套数的分组轴不同，而各段的总数是一样的，加起来都归到了 561。

### 引擎落地：从 .rknn 独立重建全部输出

有了文法规格，咱们就写引擎把它执行出来。从零写的 C++ 引擎起步时约 700 行、四个文件：

- 壳，对外的 C 接口
- loader，容器与图的解析
- emitter，装配
- driver，ioctl 的客户端

验收门槛咱们定成 byte-exact 重放。byte-exact 咱们译作逐字节一致，两边的输出按字节去比，差一个字节都不过关。它的比较面比只对拍最终推理输出更狠：从 .rknn 出发独立重建原厂库在 SUBMIT 时刻的全部输出，交给内核的每一块内存都纳入比较，逐字节一致了才算数。达成那天的收据（[notes/rknn/006](../../notes/rknn/006-2026-10-31-引擎byte-exact达成.md)）：

```text
gem1 7543744B / gem2 566144B / gem3 22440B
gem4 3411968B / gem5 301056B / gem6 2048B   六块全部逐字节一致
SUBMIT: flags=0x5 timeout=6000 task_number=246
        subcore=(0,82)(82,82)(164,82) core_mask=0 fence=-1
harness: init → query → inputs_set → run → outputs_get → destroy, exit=0
```

SUBMIT 的每个字段与原厂同装置的记录逐项一致。这个等价证明比输出张量对拍强：咱们连交给硬件的指令流都对上了，推理的结果若不同，嫌疑就落到硬件与驱动的头上了，用户态咱们就能排除。

### 用户表面与模型 zoo

装配之外咱们也对齐了用户可见的表面（[notes/rknn/007](../../notes/rknn/007-2026-10-31-用户表面query与IO变换全对齐.md)）。rknn_query（运行时查模型信息的接口，输入维度、量化参数这些）的 16 条枚举应答与原厂 0 差异，唯一的时变量 run_duration 归一化后也一致。输入侧的格式变换，f32 到 fp16 与 f32 到 int8 的变换都做到了逐字节一致，其中 int8 走的是一条 16 位定点乘子管线，咱们记下的教训是：少一步、或把除法留在 f32 里做，xn.5 的地方就会差一个量化级，编译时咱们还得加 `-ffp-contract=off`，把浮点收缩的优化挡掉。MEM_DESTROY 的请求长度也在这里被纠了错，原厂用的是 16 字节，咱们误写了 32。

模型 zoo 把能跑什么从目测变成了实测，实测的记录在 [notes/rknn/008](../../notes/rknn/008-2026-10-31-模型zoo实测与多输出收敛.md) 里。zoo 的七个模型咱们全测了：

- `resnet18`、`squeezenet`、`shufflenet`、`googlenet` 这类单输出的常客
- `mbv3s`（hardswish 算子）与 `resnet18_i8`（int8 架构）这类目测二档的
- 双输出的 `dualout`

zoo 的七个模型，加上 qemu 装置里的 mobilenetv2_fp，再加上同一网络的 int8 版 mobilenetv2_i8，咱们手上的模型就凑齐了九个。收官板验说的九模型、十份输出（dualout 占两份），咱们从名单里就能数出来。装配层咱们一行没改，7/7 做到了逐字节一致。dualout 顺手抓出三个真 bug：输出选择得按容器里的声明序取、index 边界判错、输出格式规则漏了一种，修完之后九个模型的 query 逐行一致。还有一件结构发现咱们得说，多输出模型的每个输出各占一块 GEM，dualout 一共占了七块。已证的地盘是 conv 中心的 CNN 家族，fp16 与 int8 的静态图，单输出的或多输出的都算。没证的也有名有姓：

- encoder-decoder 的大内部内存路径
- 依赖 CPU fallback 的 Transformer 系
- 动态 shape（1.5.0 的 toolkit 造不出对照样本）
- 大于 1 的 batch

## 主戏二：驱动移植，让 /dev/rknpu 活在主线内核

### 0036：把 0.9.x 的驱动搬上 7.3.1

用户态收了官，内核这边还是空的：引擎与原厂 blob 说的都是 legacy ioctl 这门口径，内核里得真有 /dev/rknpu 的入口，它们的呼叫才有人应答。[0036](../../../boards/rk3588-topeet/patches/linux/0036-drivers-rknpu-port-vendor-driver-to-mainline.patch) 是 2026-11-03 落地的，它在内核里的提交是 71fa2f577d47，整个把原厂驱动搬上了主线，补丁咱们数下来 8038 行、26 个文件、7776 行插入。原厂驱动写在 5.10.198 的树上，跟主线 7.3.1 隔着几年的 API 变迁，漂移清单挑代表性的摆几条（补丁头注释里有全量）：

- drm_driver 的 .gem_prime_mmap 与 .date 成员，上游已经删了
- vm_insert_mixed 家族没了，fault 处理改用 vmf_insert_page
- iommu_map 与 iommu_map_sg 多出了一个 gfp_t 参数
- hrtimer_init 换成 hrtimer_setup，.remove 的返回值改成了 void
- rockchip_nvmem_cell_read_u8 得按 of_nvmem_cell_get 自己重新实现

devfreq（内核里设备调频的通用框架）的取舍单独说。原厂的 rockchip_opp_select、system_monitor、ipa 那套体质框架不随行，rknpu_devfreq.c 换成了 stub（空壳占位的实现），NPU 跑在配定的 200MHz。咱们当时的理由：byte-exact 的工作与频率无关，DVFS 咱们以后可以在 dev_pm_opp 上重建。这个取舍跟外设章的 DVFS 主戏正好一正一反，那边咱们把事务语义整包搬了，这边咱们暂时没搬。DT 侧咱们按原厂补了 rknpu@fdab0000 单节点、三个 64KB 的 reg 窗口，主线自带的 rknn-core 三节点（那是 rocket 驱动暴露给用户态的 uAPI）保持 disabled，两套并存的节点互不干扰。配置侧咱们开了 ROCKCHIP_RKNPU、DRM_GEM 与 DEBUG_FS，FENCE 与 SRAM 是关的，fence_fd 恒为 -1 的做法与逆向线的记录一致。

### 0037：legacy 设备表面挂上 DRM GEM

驱动搬过来了，legacy 的入口还缺一块。原厂内核只在自家的 DMA_HEAP 框架在场时才注册 legacy 的 misc 设备，主线没有那套 heap 的框架。而这个 misc 设备的 open 恰恰是 blob 选路径的开关：open 得到 /dev/rknpu，它走的就是 legacy 的 ioctl 面，open 不到的话它退到 DRM 路径上去了。咱们引擎学的只是 legacy 面，DRM 的那套它不说。于是有了 [0037](../../../boards/rk3588-topeet/patches/linux/0037-drivers-rknpu-legacy-dev-rknpu-surface-on-DRM-GEM.patch)，内核的提交号是 3cc062ad68d9，它新写了 rknpu_legacy.c，把约定接到了 GEM 的后端上，总共插入了 273 行。接线的方式：ACTION 与 SUBMIT 跟 DRM 路径共用同一套核心，MEM_CREATE 等于 GEM 的创建加 prime 导出，handle 字段携带的是 dma-buf fd，MEM_SYNC 复用 GEM 的同步入口，MEM_MAP 干脆返回了 -ENOTTY，因为 legacy 的 blob 从来不用它。

### 0038：同步方向写反的病例

首轮板验的现象咱们原样记（[notes/rknn/009](../../notes/rknn/009-2026-11-03-legacy-GEM内存同步修正与板验.md)）：双侧 harness 都 exit=0，两侧的输出却各是 0/1000 非零，两者之间还有 494 字节的差异，差异全落在零的符号位上，这一轮咱们判 FAIL。咱们的定位沿着两条线走。一条在内核侧：DRM 的同步 ioctl 要求创建标记带 CACHEABLE，legacy 的 heap 接口没有这个要求，regcmd 的创建标记是 0x5，也就是 NON_CONTIGUOUS 加 WRITE_COMBINE 的组合，DRM 的检查会把它拒掉。另一条在咱们引擎自己身上，而且更典型：mem_sync 传的是 obj_addr=0，方向位也写反了，返回值还被忽略了。方向位的原文咱们对照着列出来：

```text
引擎的写法:  2 = TO_DEVICE,  1 = FROM_DEVICE
内核的定义:  1 = TO_DEVICE,  2 = FROM_DEVICE
```

方向位咱们补一句白话：TO_DEVICE 是 CPU 写完把缓存刷给设备，FROM_DEVICE 是设备写完把 CPU 侧的缓存作废。方向反了，该刷出去的权重没刷，该作废的输出缓存还端着旧数据，缓存所有权就乱了。[0038](../../../boards/rk3588-topeet/patches/linux/0038-drivers-rknpu-fix-legacy-GEM-memory-sync.patch)（内核提交 0bcc4d771）的修法咱们觉得值得学：与其在内核里猜 obj_addr=0 指哪块内存，不如把门槛放到对的位置。抽出对象级的同步帮手，DRM 的 CACHEABLE 门槛留在它自己的 ioctl 里，legacy 的路径按会话查对象，把方向与范围都校验了，SUBMIT 之前咱们把整个会话交给设备，阻塞作业完成后咱们整个交还给 CPU，会话的 mutex 再把 ioctl 串行化。这样两侧的用户态运行时一行都不用改，代价是每次提交的缓存维护变多，当时咱们把正确性放在了第一位。

### 全零悬案：随机权重下溢与缺失的 CPU 搬运

咱们把 0038 烧进去，原厂库那句 failed to sync memory 的日志消失了，全零的输出却还在。板验目录里咱们把两份库分开放，`own` 是咱们的自研库，`vendor` 里放的是原厂库，下文的 own 侧与原厂侧说的就是它们。第二轮取证（[notes/rknn/010](../../notes/rknn/010-2026-11-03-随机权重下溢与CPU输出搬运修正.md)）把案子翻了个面：四次推理对应 core0 的 IRQ 计数从 0 涨到 4，dmesg 里没有 timeout、reset 与 IOMMU fault 的记录，六块 buffer 提交前后的 own 与原厂侧各自逐字节一致，internal 块从全零变成了 1073429 个非零字节，NPU 真的干了活。真相是：分类输出落在 internal 的 0xa00 偏移处，原厂库提交后会把它搬进用户的输出 buffer，咱们的引擎一直读着一块从没被写过的 output GEM，于是咱们读到的全是正零，那 494 字节差异是原厂结果里的负零符号位。

MobileNet 自己的全零也有数学底：模型是随机权重，咱们拿 ONNX 和同一输入在电脑上重算，FP32 输出的绝对值全部低于 2 的 -25 次方（约 2.98e-8），正好是 FP16 最近偶数舍入的归零阈值，转完的结果就是 0/1000 非零。所以全零不是病，0/1000 本来就是这个模型的正确答案。引擎的修正跟着真相走：解析 op 的类型与输入输出下标，成功提交后执行终端的 CPU Reshape，按图内张量索引定位 internal 区域、剥掉 NC1HWC2 的通道 padding，源偏移咱们从图里解析出来，MobileNet 的落在 0xa00，ResNet18 的落在 0x400，咱们不做硬编码。driver 侧的 obj_addr、方向位与 destroy 回填，咱们也一并改对。板验的收据在证据目录 legacy-sync-0038.jr4FZz 里，咱们复核过原始文件：

- MobileNetV2：双侧 0/1000 非零，全部有限，逐字节一致
- ResNet18：双侧 1000/1000 非零，全部有限，逐字节一致

这两轮板验咱们把验收门槛的哲学也立起来了：有限数咱们必查，NaN 与 Inf 之类的一律拒绝，全零在数学上成立时咱们放行，负零的符号位差异不许放行。咱们在烧板之前就得让板验脚本在电脑上过一遍样本测试，拒绝全零、NaN、字节差异的假样本，合法的样本才接受。整个驱动线的部署咱们全程走网络章架的 tftp+nfs 免烧录引擎，换内核咱们就换一份 Image 加 dtb，一次烧录咱们都没花。树上有一处咱们要交代：网络章的 nfsd 导出的是 rootfs 章那棵 Ubuntu 单源树，NPU 战役期间 nfsd 指向的却是一棵 BusyBox 最小树，两棵其实不是一棵。为什么换树，笔记里是没有记的，咱们不编，板上站得住的事实是那棵树没有 /lib/modules，结果模块装不上，后面主戏三的多媒体驱动因此全走了内建。

## 主戏三：板级资源与多媒体核，sync_state 的一课

### 0039：NPU 的窗口压住了 IOMMU

板验期间咱们见到启动日志里挂着一行 EBUSY，来历咱们查清了（[notes/rknn/011](../../notes/rknn/011-2026-11-03-NPU资源与多媒体电源域启动修正.md)）：0036 从原厂搬来的三块 64KB reg 窗口，core0 的 `fdab0000..fdabffff` 把独立注册的 IOMMU 寄存器（`fdab9000` 与 `fdaba000`）盖在了下面。devm_ioremap_resource 于是报了 EBUSY，驱动退到无独占申请的 devm_ioremap，初始化与推理倒是照样能跑，但资源描述本身是错的。[0039](../../../boards/rk3588-topeet/patches/linux/0039-arm64-dts-rk3588-topeet-fix-NPU-resource-overlap.patch) 的内核提交是 575708c54，它把三个窗口都收成了 `0x4000` 的范围，盖住的只有 PC、CNA（卷积神经网络加速器，NPU 里真正做卷积的单元）、CORE 三类控制 bank，与主线 rknn-core 节点分列的 bank 一致，IOMMU 资源归还它自己的设备。NPU 的命令流不走 CPU 的 ioremap 窗口，收窄了也没有副作用。四行插入的小补丁，修的其实是那 7776 行插入整包搬运带过来的惯性。

### 0040 与 0042：一对停用再恢复的教学补丁

另一类启动日志咱们也处理了，PM-domain 的 sync_state pending 挂了很久。机制咱们用白话说：fw_devlink 的 strict 策略要求消费者都绑定了驱动，供应商才允许释放固件交接时保留下来的状态，PM-domain 的 sync_state 负责收尾，具体释放的就是 stay-on 约束这一类。日志之所以挂着不散，其实是有些设备始终没人认领。没人认领的原因在驱动能力上：RGA（2D 图像加速器）、Hantro（VEPU121 JPEG 编码器的驱动）、RKVDEC（视频解码器）三家主线驱动，都明确拒绝同兼容串的第二个实例，返回了 ENODEV，因为它们没有多实例调度的支持。

配置侧还叠着一道暗雷：板级 fragment 写了 RGA=y，但父层的 MEDIA_SUPPORT 是 m，Kconfig 把 RGA 静默压回了 m，而咱们的 NFS rootfs 是 BusyBox 环境，没有 /lib/modules 的目录，咱们根本装不上模块。处理咱们分了两手。kernel.config 这边咱们补齐内建配置，media 父层是打底的，下面跟着的是 Hantro、RGA、RKVDEC 三家驱动本体，VSI 的 IOMMU 也一起开了。[0040](../../../boards/rk3588-topeet/patches/linux/0040-arm64-dts-rk3588-topeet-disable-secondary-media-cores.patch)（内核提交 a0c7eb0ac）在 DT 里停用了副核：RGA3 的第二核、VEPU121 的 1/2/3、RKVDEC 的第二核，连同各自的 IOMMU，保留的是主实例与 AV1 对（AV1 解码器连同它自己的 IOMMU）。思路咱们很认同：让描述的可用性去匹配驱动的真实能力，不动 fw_devlink 的策略，日志咱们也不压。[0042](../../../boards/rk3588-topeet/patches/linux/0042-arm64-dts-rk3588-topeet-enable-all-media-cores.patch)（内核提交 4fad778b0）当晚就把停用撤销了，它跟 0041 是同一晚成对提交的，因为多实例调度已经由 0041 补上了，RGA3 的双核、VEPU121 的四核、RKVDEC 的双核全部恢复。一停一启正好构成一对教学样本：缺能力时咱们改描述，能力补上咱们改回描述，两头的板级 DT 都跟驱动真实能力对齐。

### 0041：多核会话池

[0041](../../../boards/rk3588-topeet/patches/linux/0041-media-rockchip-enable-multicore-session-pools.patch) 的内核提交是 94b2c1897，补丁咱们量了 1118 行、409 处插入、187 处删除，它新增了 `include/media/v4l2-m2m-corepool.h`，外带 sysfs 的 ABI 文档，把三家驱动的单实例限制换成了共用的会话核心池。设计咱们按笔记复述（[notes/rknn/012](../../notes/rknn/012-2026-11-04-多媒体全部实例与并发核验.md)）：每类引擎保留一个 V4L2 frontend 当用户入口，其余的物理核作为后端进池。打开 frontend 的时候它选的是就绪且打开会话数最少的核心，会话数相同的就轮转。会话对核心的亲和保持到关闭，下面这些资源的归属从头到尾是同一个物理设备：

- DMA 映射与解码参考帧
- 寄存器与 IRQ
- watchdog 与 runtime PM

只有主实例注册 video 与 media 的节点，次实例等的是 frontend 就绪，device link 保证卸载的顺序，后端拆完了才轮到 frontend。要说清的是，这是会话级的并行，不做单帧的跨核拆分，也不能按核心的数量宣称单路速度翻倍。可观测性咱们也给足了，每个物理设备有四个只读的 sysfs 计数器：

```text
m2m_core_users        打开的会话数
m2m_core_submitted    提交数
m2m_core_completed    完成数
m2m_core_errors       错误数
```

### 八核实板验收

这轮验收咱们不是一遍过的。首轮的三项失败（[notes/rknn/015](../../notes/rknn/015-2026-11-04-多媒体初始化修正与八核实板验收.md)）翻下来，全在用户态的测试初始化上：

- 启动检查把驱动名写成了小写 rknpu，真实的 sysfs 名是 RKNPU
- JPEG 的 demo 把 OUTPUT 设在了 CAPTURE 前面，Hantro 的 CAPTURE 设置会重置 OUTPUT，于是返回了 EBUSY，得倒过来把 JPEG 侧的格式定在前面
- H.264 的 SPS/PPS 只塞在了 request 里，没赶在分配 buffer 之前设全局参数，解码的像素全错，咱们按 stateless 解码器的接口文档把顺序理对后才逐像素一致

修正之后咱们拿到了终局收据，每核都是 16 帧的并发：

```text
RGA3   fdb60000.rga          提交16 完成16 错误0 IRQ+16
RGA3   fdb70000.rga          提交16 完成16 错误0 IRQ+16
JPEG   fdba0000.video-codec  提交16 完成16 错误0 IRQ+16
JPEG   fdba4000.video-codec  提交16 完成16 错误0 IRQ+16
JPEG   fdba8000.video-codec  提交16 完成16 错误0 IRQ+16
JPEG   fdbac000.video-codec  提交16 完成16 错误0 IRQ+16
H.264  fdc38000.video-codec  提交16 完成16 错误0 IRQ+16
H.264  fdc40000.video-codec  提交16 完成16 错误0 IRQ+16
```

判定咱们不只看日志：

- RGA 的两路输出与各自图案逐像素一致
- H.264 两路 NV12 与真值逐字节一致，保存下来的 34 份帧快照（两路并发各 16 帧加单路基线两帧）咱们在电脑上全部复核过
- 四张 JPEG 用 Pillow 实际解码，PSNR（峰值信噪比，数值越高越像原图）咱们量到 42.127、41.977、41.738、41.926 dB，门槛咱们定在 28 dB，防的就是只有合法 JPEG 头或全黑图也被算成通过

启动侧的体检咱们也拿到了：23 个实例与 IOMMU 全部绑定（清单把每个功能核和它自己的 IOMMU 各算一件），PM-domain 的 state_synced 等于 1，EBUSY 与 sync_state pending 两类日志在本轮 dmesg 里消失了，MobileNet FP16 与 ResNet18 的 NPU 回归，前后也都通过了。测的是各组内部的并发，三组是按序执行的，咱们不宣称八个核同时满载或单路跨核加速，128×128 固定输入加每核 16 帧的功能验收，也不是性能上限或长时间稳定性的验收。

## 收官：九模型板验、假证据复盘与工程整理

### 一场假证据的复盘

九模型全量对比的第一轮输出是 6/9，咱们差点就拿去交差了，翻开之后咱们才认出了里面的假证据（[notes/rknn/013](../../notes/rknn/013-2026-11-04-NPU全模型脚本隔离与真实失败.md)）。病根在板端 runner 的第一版：所有模型的输出写进共用的 `results/own/out*.bin` 与 `results/vendor/out*.bin`。dualout 取第二个输出时返回了 -5，harness 却照样报了 exit=0。失败后的搬运命令只在单文件时有效，多文件时的目标不是目录，搬运失败还被忽略了，原厂侧的 out1.bin 就残在了原地。随后所有单输出模型都被它误判成缺少 own 侧的文件。更早的原厂侧 out0.bin 又被后续模型覆盖，这一轮的完整证据救不回来了。现存日志里的六个模型确实一致，咱们只把它记作日志证据，不升级成验收通过的判定。三项真实的失败没被残留文件解释，咱们逐一立案，dualout 取输出返回了 -5，mbv3s 运行报了 -110 超时，shufflenet 的两侧摘要不同。runner 重写成每次运行建独立的目录，own 与原厂侧的原始输出按模型分开保留，外加双向的检查，空的一律拒绝，harness 对 API 的失败一律返回非零。这个案例咱们要正面写：测试装置自己就会制造冤案，它跟故意造假的情形是两码事，所以板验的判定脚本本身得被测试。

### 图顺序执行：三个真失败

上面三项失败的修法，把引擎推到了正确的一层（[notes/rknn/014](../../notes/rknn/014-2026-11-04-图顺序执行与多输出取回.md)）。根因咱们认得很清楚：六块 GEM 的装配一致加 query 一致，却并不等于执行链的正确性。咱们引擎此前把整个 A/B/C 计划一口气提交，只在最后补了个终端 Reshape，而原厂是按 CPU 边界、按预载任务分段提交的。三个病例各修各的。dualout 的 rknn_outputs_get 硬编码只收一个输出，改成按输出 index 各取独立的 GEM，剥掉 padding 后返回逻辑的 NCHW。mbv3s 的 HardSigmoid 带常量与 LUT 的预载任务，原厂把 flags=0x1 的任务单独提交，普通段才用的是 0x5。咱们看 SUBMIT 的 flags，得跟 GEM 的创建标记分开。SUBMIT 的 flags 是提交结构里选执行路径的标记，0x1 标的是预载段，0x5 标的是普通指令段。GEM 那边的 0x5 是内存块的创建属性，数值上是相同的，却是两个结构里的两个东西。咱们连跑就进了错误的预载路径超时，改成了按图顺序的 57 次提交。shufflenet 图里的 16 次 CPU Transpose 此前被整个跳过，现在咱们解析 permutation，按它记录的置换把数据取回、转置、重新打包，7×7 的 blocked 特征面里 49 个有效位置向上取到 4 的倍数、排进 52 个物理位置，这正是 NC1HWC2 按 4 通道一组打包的对齐，padding 也清了零。执行时的同步纪律咱们立住了：CPU 操作前咱们等前一 NPU 段完成，源和目标都得做 FROM_DEVICE 的同步，CPU 写完了再对目标做 TO_DEVICE。

主机侧的 oracle 在 qemu 里同时加载真原厂库与 own 库两份跑对拍，咱们让九个模型各跑六种选核，凑出了 54 种完整提交序列。六种选核咱们列得出，AUTO 加上 mask 的显式值 1/2/3/4/7，凑齐的正好是六种。flags、timeout、task 范围的字段，连同 core_mask、fence 与全部 subcore 的字段，咱们逐项核对一致，只有内核对象地址做了归一化。三模型的 CPU 搬运逐段一致：

- mbv3s 的 57 段
- ShuffleNet 的 17 段
- dualout 的 2 段

板上的终局收据咱们存在证据目录 npu-models.Xu6DXb 里：9/9 模型、10 份输出的成绩，own 与原厂侧的输出字节一致，而且全部有限，dualout 的两份输出是 15680B 加 64B，mbv3s 也不再超时了，shufflenet 的输出也一致了。口径照录：验证用的是默认 AUTO 选核，六种显式选核组合的硬件数值验收不在本轮。

### 测试的四层与证据复核

运行时连同测试统一进了仓库（[src/rknpu/rk3588](../../../src/rknpu/rk3588/README.md)），测试咱们分成四层，层名是从测试目录（host/native/board）与套件名（oracle）里蒸馏出来的：

- host 的 mock 层：板端 runner 的隔离逻辑、启动检查、核心池 8000 次并发租用，都在电脑上拿模拟对象测
- native 层：C++ 测试直链生产代码，ASan 与 UBSan（内存错误与未定义行为的两类运行时检测器）开着跑
- oracle 层：qemu 里真原厂库与 own 库同场对拍，提交序列、首提交 GEM、CPU 搬运逐段比
- board 层：板端 demo 与 runner，BusyBox 环境不需要装 Python

板端的操作入口，咱们照 [tests 的 README](../../../src/rknpu/rk3588/tests/README.md) 记的原文贴在下面：

```sh
cd /opt/rknn-verify
sh ./run.sh                       # NPU 九模型字节对比
sh ./verify_legacy_sync.sh         # FP16 下溢与非零 ResNet 回归
sh ./multicore/run.sh              # 启动检查 + 各组逐核并发及内容检查
```

三个入口对应的是本章三条验收线，九模型的逐字节对拍、下溢与非零的回归、多媒体的逐核并发。板子跑的是 BusyBox 环境，三个脚本咱们都没让它依赖 Python，产物也都落在独立的证据目录里，等的就是主机的复核。

证据复核的入口都在咱们主机这一侧：

- verify_npu.py 校验九模型十份输出的 API 结果、大小、有限、非零门槛与字节一致
- verify_media.py 复核 JPEG 的解码内容、RGA 与 NV12 像素、逐核计数增量
- analyze_sync.py 读 legacy-sync 证据目录的原始快照，是下溢回归那条线的主机入口

板端日志说了不算，咱们要让主机读原始文件重新判一遍。这里还有一句自述咱们照录（运行时仓库自述，原文在 tests README 的开头）：

```text
AI 生成：请注意，这个验证是 GPT 6.1 Sol 生成的E2E测试！请适度采纳！
```

咱们把它留在明面上：E2E 测试（端到端测试，从接口入口一路把整条链跑完）的骨架由 agent 生成，判定门槛与复核入口是咱们逐轮收紧的，自述的原文照挂在 README 开头，读者自己掂量采纳的程度。

### 工程整理与诚实的边界

收官前咱们把运行时整理了一遍（[notes/rknn/016](../../notes/rknn/016-2026-11-04-运行时CMake与现代C++整理.md)），构建咱们换成了 CMake 3.20+ 与 C++20，源码按职责分家（[运行时 README](../../../src/rknpu/rk3588/README.md) 的源码表）：

- shell.cpp 管对外 C 接口与量化转换
- execution.cpp 管图顺序执行与选核
- tensor.cpp 管张量布局与 CPU 算子
- loader.cpp、emitter.cpp、driver.cpp 分别管解析、装配、驱动交互
- include/ 放模型与接口定义，加 CMakeLists 与 tests，清单凑齐九件

现代 C++ 的落点也具体，咱们一件件数：

- span 给缓冲区的边界画线
- array 表达固定大小的 ABI 数组
- bit_cast 做浮点位表示的转换
- 上下文与 fd 的回收交给 RAII（资源获取即初始化，回收绑在对象的生命周期上）
- 具名的 BufferSlot、TaskRecord 与 ioctl 结构替代手工的字节拼接
- 静态断言卡住 legacy ABI 的大小与偏移

许可咱们分得清楚：自研的源码用 MIT，原厂的 SDK 头带着 proprietary 声明只作外部输入不进仓，内核补丁保留各自的 GPL 标识。主机回归咱们全跑过了：

- 54/54 的提交序列与 9/9 的首提交 GEM
- 三模型的 CPU oracle 与 mock 套件
- Cinux 风格的格式检查

诚实的边界咱们按仓库口径照写：重构后的库仍需新一轮实板验收，九模型的实板 PASS 属于重构前的构建。六种显式选核的硬件数值、动态 shape、Transformer 系、性能上限与长时间稳定性，都还在没测的清单上。

## 尾声：这块板的 NPU 站在哪了

咱们把整条链摆直了看，这块板的 NPU 现在是完整的。主线 7.3.1 内核里跑着咱们移植来的原厂 GPL 驱动，0036 到 0038 三发把整包搬运、legacy 设备表面与同步修正做齐了，资源窗口的修正 0039 也跟在后面落定。多媒体这边咱们点亮的是 RGA3、JPEG、H.264 八个功能核连同会话池（0040 到 0042），AV1 对咱们也启用着，只是它的功能验收不在本轮。用户态是一个 MIT 许可的自研运行时，九个模型在板上跟原厂闭源库对到了逐字节一致。板上的应用一行不用改，把 librknnrt.so 换成咱们的库就完事（九模型 PASS 出自重构前的构建，重构后的库还欠一轮实板复验），.rknn 的生态照原样能跑。

方法论上咱们最想带走的是那套对闭源件的办法：闭源其实不等于黑箱。容器规格社区有现成的，接口的字典就躺在开放的头文件里。行为对拍咱们靠 qemu 假内核加 `RKNN_DUMP_TXT_TENSOR` 这个环境变量金标准，每层的中间张量它都会写成文件。等价性咱们用 byte-exact 重放证明。板验收就交给独立的证据目录加主机复核。这套办法咱们换一家芯片也能用。社区那边的 rocket 加 Teflon 线咱们也看好，它往 TFLite 的方向走，咱们这边的线保 .rknn 生态，内核侧的两套节点本来就并存，谁成熟了咱们就用谁。外设章待办清单上的那一行现在可以划掉了。当时咱们记的口径是 NPU 那一行，主线 Rocket 驱动在、CONFIG 未开的处境，如今这一页咱们翻过去了。
