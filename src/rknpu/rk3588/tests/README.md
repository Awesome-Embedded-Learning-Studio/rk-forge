# RK3588 RKNPU 与多媒体验证

> AI 生成：请注意，这个验证是 GPT 6.1 Sol 生成的E2E测试！请适度采纳！

## 入口

从仓库根目录执行基础回归：

```sh
python3 src/rknpu/rk3588/tests/run_host.py
```

先构建自研运行时，再运行完整主机回归（含 C++ ASan/UBSan、多媒体 mock、QEMU vendor 对照）：

```sh
cmake -S src/rknpu/rk3588 -B out/rk3588-topeet/rknpu-runtime/aarch64 -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE=cmake/aarch64-linux-gnu.cmake -DCMAKE_BUILD_TYPE=Release
cmake --build out/rk3588-topeet/rknpu-runtime/aarch64
~/tools/rknn-toolkit-venv/bin/python src/rknpu/rk3588/tests/run_host.py --suite all
```

有旧板验 MEM_SYNC 快照时，可额外运行真实缓冲区回归：

```sh
~/tools/rknn-toolkit-venv/bin/python src/rknpu/rk3588/tests/run_host.py \
  --suite all --sync-evidence /path/to/legacy-sync-evidence
```

支持 `--suite basic|native|media|oracle|all`。每次运行产生独立目录，
`verification.json` 记录每项退出码；主机回归通过不代表新一轮实板验收。
没有 `--sync-evidence` 时明确跳过该项快照测试，报告也记录未选择。

安装项目 pytest 开发依赖后，也可运行 `python3 -m pytest src/rknpu/rk3588/tests`。
缺少科学计算依赖时两项 media 测试显示 skip；vendor oracle 默认不参与 pytest，
需先构建 board bundle，再设置 `RKNN_RUN_VENDOR_ORACLE=1` 显式启用。
C++ 测试通过 `run_host.py --suite native` 调用 CMake/CTest 构建和执行，
也可在运行时 CMake 中设置 `RKNN_BUILD_TESTS=ON`。

## 测试内容与依赖

| 位置                         | 内容                                                    | 额外输入/工具                              |
| ---------------------------- | ------------------------------------------------------- | ------------------------------------------ |
| `host/test_board_runner.py`  | 模型/运行输出隔离、API/落盘失败返回                     | C 编译器、外部 SDK 头                      |
| `host/test_boot_check.py`    | 23 个驱动/IOMMU 绑定、PM 状态与错误日志                 | POSIX shell                                |
| `host/test_replay.py`        | 空证据、缺少提交、早期提交差异均拒绝                    | Python 标准库                              |
| `host/test_npu_evidence.py`  | 缺失、全零、NaN、字节差异均拒绝                         | Python 标准库                              |
| `host/test_corepool.py`      | 真实核心池 header、8000 次并发租用、probe/回收/错误路径 | C 编译器、ASan/UBSan、内核源码或 0041 补丁 |
| `native/execution_test.cpp`  | 真实模型分段执行、CPU 搬运、多输出、错误传播            | CMake、C++20、引擎源码、RKNN 模型          |
| `native/driver_test.cpp`     | mmap 失败回收、上下文析构、fence 就绪/超时/错误         | CMake、C++20、外部 SDK 头                  |
| `native/output_test.cpp`     | 真实板端快照、布局边界、负零、MEM_SYNC ABI              | 上述输入及 `--sync-evidence`               |
| `host/test_media_demo.py`    | 实际 demo 的正常/损坏/硬件错误、初始化顺序回归          | numpy、Pillow、本机及 AArch64 C 编译器     |
| `host/test_media_suite.py`   | 正常、核心空闲、错误计数增加及 JPEG 内容判定            | numpy、Pillow                              |
| `host/test_vendor_oracle.py` | 54 种提交序列、九模型全部首提交 GEM、三模型非零 CPU 缓冲区 | QEMU、rootfs、真实 own/vendor 库、九个模型 |
| `board/`                     | 板端 runner、harness、trace 与多媒体 demo 源码          | AArch64 构建；板端 BusyBox，无需 Python    |
| `fixtures/`                  | 模拟 V4L2/legacy ioctl 的 C 测试替身                    | 仅用于主机模拟                             |

ASan/UBSan 测试使用 `detect_leaks=0`，不包含泄漏检测。QEMU 只验证软件执行
顺序及数据搬运，不执行 NPU 算术。模拟损坏输出、空闲核心或新增错误必须失败。

## 配置外部输入

默认沿用当前工作区输入，均可通过参数或环境变量更换：

| 参数             | 环境变量              | 默认位置                                                                    |
| ---------------- | --------------------- | --------------------------------------------------------------------------- |
| `--model-dir`    | `RKNN_MODEL_DIR`      | `.claude/rknn`，含 MobileNet 及 `zoo/`                                      |
| `--engine-dir`   | `RKNN_ENGINE_DIR`     | `src/rknpu/rk3588`                                                          |
| `--sdk-include`  | `RKNN_SDK_INCLUDE`    | vendor SDK 的 `include/`                                                   |
| `--own-lib-dir`  | `RKNN_OWN_LIB_DIR`    | `out/rk3588-topeet/rknpu-runtime/aarch64`                                    |
| `--kernel-dir`   | `RKNN_KERNEL_DIR`     | `third_party/src/rk3588-topeet/linux`                                       |
| `--vendor-dir`   | `RKNN_VENDOR_DIR`     | `reference/rk3588/external/rknpu2/runtime/RK3588/Linux/librknn_api/aarch64` |
| `--rootfs`       | `RKNN_TEST_ROOTFS`    | `out/rk3588-topeet/rootfs`                                                  |
| `--artifact-dir` | `RKNN_TEST_ARTIFACTS` | `out/rk3588-topeet/rknpu-tests`                                             |
| `--cross-cc`     | `RKNN_CROSS_CC`       | `CROSS_COMPILE`、PATH 或 `/opt` 下的 AArch64 GCC                            |

模型目录需含 `mobilenetv2_fp.rknn`、`mobilenetv2_i8.rknn` 和
`zoo/{dualout,googlenet,mbv3s,resnet18,resnet18_i8,shufflenet,squeezenet}.rknn`。
引擎目录含 `src/`、`include/`；oracle/部署读取 `RKNN_OWN_LIB_DIR/librknnrt.so`。
SDK 头和 vendor 库直接使用本地输入，不复制进版本控制。SDK 头由 `RKNN_SDK_INCLUDE` 指定。
ONNX 裁决工具另需 `mobilenetv2.onnx`、`zoo/resnet18.onnx` 与 onnxruntime。

## 构建、部署与板验

构建只写 `out/`，不连接板卡：

```sh
python3 src/rknpu/rk3588/tests/build_board.py
```

生成的 `out/rk3588-topeet/rknpu-tests/board/` 含 AArch64 二进制、脚本、源码和
自动生成的两路 H.264/NV12 夹具。`build-manifest.json` 记录编译器和文件摘要。

部署到指定 rootfs（原子替换文件，不重启或烧写）：

```sh
python3 src/rknpu/rk3588/tests/deploy_board.py --rootfs out/rk3588-topeet/rootfs
```

该入口先重新构建，随后复制测试 bundle、own/vendor 库和模型，检查 ELF 架构、
动态依赖与 shell 语法。板端操作保持为：

```sh
cd /opt/rknn-verify
sh ./run.sh                       # NPU 九模型字节对比
sh ./verify_legacy_sync.sh         # FP16 下溢与非零 ResNet 回归
sh ./multicore/run.sh              # 启动检查 + 各组逐核并发及内容检查
```

## 主机复核板端证据

```sh
python3 src/rknpu/rk3588/tests/host/verify_npu.py /path/to/npu-models.XXXXXX

~/tools/rknn-toolkit-venv/bin/python \
  src/rknpu/rk3588/tests/host/verify_media.py /path/to/media-multicore.XXXXXX

python3 src/rknpu/rk3588/tests/host/analyze_decode.py /path/to/media-multicore.XXXXXX

~/tools/rknn-toolkit-venv/bin/python \
  src/rknpu/rk3588/tests/host/analyze_sync.py /path/to/legacy-sync-evidence
```

`verify_npu.py` 严格校验九模型/十份输出、API 结果、大小、finite、非零门槛及
own/vendor 字节一致；`verify_media.py` 同时检查 JPEG 解码内容、RGA/NV12 像素、
逐核心提交/完成/错误/IRQ 增量和 worker 日志。`analyze_decode.py` 提供逐帧
差异与原始布局诊断，不能替代 `device-status` 或完整多媒体复核。
