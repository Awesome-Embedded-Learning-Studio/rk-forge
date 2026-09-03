# 87 — panthor M2c：首个真像素——glClear readback PASS（2026-09-04）

> 战役七加时赛。note 76 的执行器证据门（§3.6："4-6 周无正确像素则 No-Go"）
> 在第 3 天被推翻——**glClear readback 出正确颜色**。

## 0. 结果

| 项 | 结果 |
|---|---|
| **首个真像素** | ✅ `glClear(1,0,0,1)` → 16×16 RGBA8 FBO → `glReadPixels` 返回 **[255, 0, 0, 255]**，VERDICT PASS（干净二进制复验） |
| **执行器形态** | CS 解释器从"跳过用户段"升级为**进入 CALL 用户段执行**（共享寄存器文件，一层嵌套）+ RUN_FRAGMENT 的 clear-only 执行器 |
| 零 GL 错误 | ✅ glGetError 全程 0 |

## 1. 方法论：mesa genxml + 三轮 dump 实测

- **指令编码**：v10.xml（`PAN_MESA_DEBUG=trace` 在 Ubuntu mesa 未编 pandecode，
  trace 空——改从 QEMU 解释器内 dump）
- **用户段真容**（glClear 仅两个 job，~13 条指令）：job1 = fw init
  （HEAP_SET + SET_EXCEPTION_HANDLER）；job2 = MOVE×6 + **RUN_FRAGMENT(7)** +
  WAIT×2 + FLUSH + WAIT——**没有 shader、没有 tiler geometry**
- **FBD 布局三轮实测**（dump FBD+0x00..0x100）：
  - w8=宽高-1（0x000f000f = 16×16）✓ 与 XML 一致
  - **nrt 元数据不可信**（=1 但实际两个 RT 槽：RT0 空占位、真 RT 在槽 1）
  - RT 槽 0x40 步长：w1 bit0=WriteEnable、bits[7:3]=WritebackFormat
    （19=R8G8B8A8）、**RT Buffer（base@w8、RowStride@w10）**、
    **Clear Color0@w12**（ff0000ff = RGBA LE 直存，无定点 pack）

## 2. 实现（QEMU rk3588-lite.c）

- `cs_step`：单步解释（wrapper 与用户段共用）：MOVE48/32 装寄存器、
  SYNC_ADD32/64 真执行、**CALL(32) 进用户段**（walk 用户 VM 顺序执行
  len/8 条，寄存器文件共享——FBD 地址就是用户段 MOVE 装进 regs[40] 的）、
  **RUN_FRAGMENT(7) → run_fragment**
- `run_fragment`（clear-only）：walk FBD（regs[40]&~7）→ w/h → 扫全 8 个
  RT 槽（不按 nrt）→ wen && fmt==RGBA8 → **clear word 逐像素铺 w×h**
  （行距按 RowStride，经用户 VM walk 写物理内存）
- 取证 dump（SIMFBD/SIMCSCALL）三轮后全部撤除

## 3. 意义与边界

**意义**：note 76 的 No-Go 依据是"不存在能消费该流的软件后端"——clear
类被实证推翻。执行器路线从"1-3 人月预估"实测降到**半个工作日**
（含全部取证）。tile-based GPU 的 clear 走 FBD 描述符而非 shader 执行，
是这次捷径的本质。

**边界（诚实声明）**：
- 只有 **RGBA8 线性写回的 clear 路径**；AFBC/YUV/深度模板/MSAA 未实现
- **shader/tiling/纹理/混合全部没有**——三角形和 GNOME 仍是未开垦区
- clear color 的定点 pack 只验证了 R8G8B8A8 直存（blendable 分数位格式
  未验）
- readback 的 blit job（tiled→linear）**恰好**也走 clear/空路径过了——
  侥幸成分待 M2d 复核

## 4. M2d 展望（如果继续）

1. **readback blit 复核**：glReadPixels 的 tiled→linear blit job 是怎么
   过的（FBD 路径 or 侥幸）——若是 blit 描述符，补 blit 执行
2. **RUN_FULLSCREEN(8)**：mutter 桌面合成的主力路径（全屏 quad）——
   DCD 解析 + 定点光栅化（无 shader 的纯色 quad 就能出桌面底色）
3. 三角形：vertex fetch + 光栅 + fragment shader 调用——真正深水区
4. 执行器结构化：FBD/RT 解析抽成描述符表驱动，为多格式扩展铺路
