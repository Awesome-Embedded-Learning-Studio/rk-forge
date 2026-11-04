# RK3588 自研用户态运行时

本目录实现 RK3588 的 `librknnrt.so` 兼容运行时：解析 RKNN/NN_BG 模型，装配
寄存器命令与 task，管理 legacy `/dev/rknpu` GEM，按图顺序执行 NPU 段和
CPU Reshape/Transpose，并提供输入预处理、张量查询与多输出取回。
源码的许可见 [LICENSE](LICENSE)。内核移植及其 GPL 来源另见
[RKNPU 源码索引](../README.md)。

## 源码

| 文件              | 职责                                            |
| ----------------- | ----------------------------------------------- |
| `src/shell.cpp`   | RKNN C ABI、查询及输入格式/量化转换             |
| `src/execution.cpp` | 图顺序执行、选核、预载与 CPU 操作边界 |
| `src/tensor.cpp` | 张量布局、CPU Reshape/Transpose 与多输出取回 |
| `src/loader.cpp`  | RKNN 容器、NN_BG 图和 IO 元数据解析             |
| `src/emitter.cpp` | 权重/模板、地址回填、寄存器命令和 task 装配     |
| `src/driver.cpp`  | legacy ioctl、GEM 创建/同步/销毁与提交          |
| `include/`        | 模型、驱动接口、数值转换、task ABI 与 FD 所有权 |
| `CMakeLists.txt`   | 本机/交叉编译、安装、CTest 和格式检查 |
| `tests/`          | 主机回归、板端 demo 与证据复核 |

使用 C++20 的 `std::span` 表达缓冲区边界，`std::array` 表达固定 ABI 数组，
`std::bit_cast` 做浮点位表示转换。上下文和 FD 采用 RAII 回收，输出分配在
完整校验后移交给调用方。ioctl/task 使用具名结构及大小、偏移静态断言；
图执行和张量处理分别编译，测试直接链接生产对象。

## 外部 SDK 头

编译需要与目标 ABI 匹配的 `rknn_api.h`。原工作副本带有 Rockchip 的
proprietary/confidential 声明，因此作为外部 SDK 输入，不放入本目录。
当前工作区默认读取：

```text
reference/rk3588/external/rknpu2/runtime/RK3588/Linux/librknn_api/include/rknn_api.h
```

可用 CMake 参数 `-DRKNN_SDK_INCLUDE=/path/to/include` 或环境变量
`RKNN_SDK_INCLUDE` 指定其他安装位置。
构建本库不需要链接 vendor `librknnrt.so`；vendor 库仅用于独立对照测试。

## 构建

在仓库根目录执行：

```sh
# AArch64；使用 cmake/aarch64-linux-gnu.cmake 自动寻找交叉编译器
cmake -S src/rknpu/rk3588 -B out/rk3588-topeet/rknpu-runtime/aarch64 -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE=cmake/aarch64-linux-gnu.cmake \
  -DCMAKE_BUILD_TYPE=Release
cmake --build out/rk3588-topeet/rknpu-runtime/aarch64

# 本机测试库
cmake -S src/rknpu/rk3588 -B out/rk3588-topeet/rknpu-runtime/host -G Ninja \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo -DRKNN_BUILD_TESTS=ON \
  -DRKNN_ENABLE_SANITIZERS=ON
cmake --build out/rk3588-topeet/rknpu-runtime/host
ctest --test-dir out/rk3588-topeet/rknpu-runtime/host --output-on-failure
```

默认产物分别为：

```text
out/rk3588-topeet/rknpu-runtime/aarch64/librknnrt.so
out/rk3588-topeet/rknpu-runtime/host/librknnrt.so
```

需要 CMake 3.20+ 和支持 C++20 的编译器。交叉编译器可用 `RKNN_CROSS_CXX`
或 `CROSS_COMPILE` 指定；本机编译器用标准 `CXX`/`CMAKE_CXX_COMPILER` 配置。
构建参数包含 `-ffp-contract=off` 和 `-Wall -Wextra -Werror`。
可通过 `cmake --install <build-dir> --prefix <destination>` 安装库。
源码目录不保存生成的 `.so`。

本目录的 `.clang-format` 来自 Cinux，可使用全局 clang-format：

```sh
cmake --build out/rk3588-topeet/rknpu-runtime/host --target format
cmake --build out/rk3588-topeet/rknpu-runtime/host --target format-check
```

## 验证与支持范围

主机回归和板验工具统一位于
[src/rknpu/rk3588/tests](tests/README.md)：

```sh
python3 src/rknpu/rk3588/tests/run_host.py

~/tools/rknn-toolkit-venv/bin/python \
  src/rknpu/rk3588/tests/run_host.py --suite all
```

完整回归需要外部模型、SDK 头、vendor 库、QEMU 和对应 rootfs；详细配置见
测试目录 README。`RKNN_OWN_LIB_DIR` 可覆盖待对照库目录，默认使用上面的
AArch64 构建目录。

重构前的实板基线覆盖 RK3588、RKNPU 0.9.8 与固定图 FP16/int8 分类模型：
MobileNetV2 FP16/int8、ResNet18 FP16/int8、GoogLeNet、MobileNetV3 Small、
ShuffleNet、SqueezeNet、双输出模型。九模型十份原始输出均与 vendor
字节一致。当前 CMake 构建通过主机回归：九模型的六种选核方式完整提交序列、
九模型首提交全部 GEM，以及三模型的非零 CPU 搬运与输出对照。
重构后的库仍需新一轮实板验收。
这些结果不代表全部 RKNN 算子、动态 shape 或任意模型均已支持。

实板证据与执行路径说明见
[图顺序执行与多输出取回](../../../document/notes/rknn/014-2026-11-04-图顺序执行与多输出取回.md)。
