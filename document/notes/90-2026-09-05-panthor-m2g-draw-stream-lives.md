# Note 90 · panthor M2g：draw 全指令流穿执行器——RUN_IDVS/RUN_FRAGMENT 活了

日期：2026-09-05 · 战役七第九篇 · 上一节：note 89（M2f bit19 brownout 根修）

## 0. 摘要

note 76 判 9-24 人月的 shader/tiler 深水区正式开题。本轮三刀落地：
①**CALL/JUMP 的 Length 是寄存器操作数**（旧解拿字段值=寄存器号 190，190/8
=23 条截断用户段——clear batch ≤23 条侥幸未露馅，draw batch 被砍在
RUN_IDVS 之前）；②**FBO 是 Tiled U-Interleaved**（bf=1，16×16 RGBA8 =
一个 1024B tile；RowStride 是 tile 行距 0x400；曾按线性 ×16 解码把 clear
铺进页表页 = Bad page map）；③**surfaceless context 必须 glViewport**
（默认 0×0 → `scissor_culls_everything` → draw 被 panfrost 静默剔除）。
修后：**全屏三角形 draw 的完整 CS（RUN_IDVS+RUN_FRAGMENT+FINISH_TILING+
FINISH_FRAGMENT，段长 456B=57 条）穿过执行器**；glClear 双路（bf=1 整 tile
铺 / bf=2 线性行铺）双机 PASS ×2、零页损坏。像素仍 [0,0,0,0]——shader
本体未执行，是诚实边界不是缺陷。

## 1. 弹药：glestriangle.py（sim/ 新资产）

全屏三角形（-1,-1 / 3,-1 / -1,3）+ 常量红 FS，16×16 RGBA8 FBO，VBO 顶点，
4×4 块逐像素验证。四个 client 侧坑（净机实测）：

| 坑 | 症状 | 修 |
|---|---|---|
| 3KB 单行 base64 | tty 截断（2004/2411B） | 分块 base64+md5（/tmp/send3.py 形态） |
| EGL 3 参 GBM 调用 BAD_PARAMETER(0x300c) | 净机必炸 | 照 glesclear 走 `eglGetDisplay(gd)` 单参兜底 |
| client-side 顶点数组 | GLES 不支持，mesa 静默不提交 draw | 真 VBO + glBufferData |
| 无 viewport | surfaceless 默认 0×0 → skip_rasterization | `glViewport(0,0,16,16)` |

`panfrost_batch_skip_rasterization`（pan_cmdstream.c:920）=
`rasterizer_discard || scissor_culls_everything || !rsd[VERTEX]`——
静默剔除无 GL error，是"job 里没有 RUN_*"的第三种来源（另两种见 §2/§3）。

## 2. CALL/JUMP Length = 寄存器操作数（M2g 主根修）

内核 wrapper（panthor_sched.c prepare_job_instrs）：
`MOV48 addr_reg,cs.start + MOV32 val_reg,cs.size + CALL addr_reg,val_reg`。
旧解释器拿 `(instr>>32)&0xff`（=val_reg 寄存器号 190）当字节数 → 23 条
截断。修：`len = regs[(instr>>32)&0xff]`，JUMP 同。实测 draw 段 456B/57
条，opcode 直方图首次出现 `6:1 7:1 9:1 11:1`（RUN_IDVS/RUN_FRAGMENT/
FINISH_TILING/FINISH_FRAGMENT）。

**为什么 M2c-M2e 全没露馅**：clear batch 用户段 ≤23 条，截断点在段尾
之后。M2f 的 67 发 WARN 也是它放行的畸形流。教训：**截断型缺陷的验收
必须有多段长样本**（draw 才是长段的最低门槛）。

## 3. FBO 是 U-tiled：RowStride 语义与 Bad page map

- v10.xml：RT Buffer{Base@+0x20, Row Stride@+0x28, Surface Stride@+0x2c}
  裸 uint 无修饰；Block Format@w1[11:8]（1=Tiled U-Interleaved, 2=Linear,
  12/13=AFBC）。
- 实测 16×16 RGBA8 FBO：bf=1、stride=0x400=**一个 16×16 RGBA8 tile**
  （1024B）——mesa 的 FBO 默认 U-tiled，RowStride 是 **tile 行距**不是
  线性行距（1024 宽桌面=64 tile=0x10000 自洽）。
- 曾两轮错解：裸当线性行距（16 行 ×0x400 溅 16KB）；×16（更离谱）。
  两次都在净机上把 clear word 铺进内核页表（`Bad page map, pte:
  ff0000ffff0000ff`=像素图案）——GDM 机上同 bug 溢进无人区所以从未暴露。
  **GPUFBG 落点打印（as/fbd VA→PA/bf/stride/clear word/AS1 表基）就是为
  此而生**。
- 修：bf=1 → 整 tile（1024B）铺 clear word，tile 网格 = ceil(w/16)×
  ceil(h/16)，行距=stride；bf=2 → 线性行铺；AFBC 跳过。边缘半 tile 不铺
  （partial tile 需 swizzle，诚实边界）。glClear 16×16（整 tile 恰好全
  覆盖）双机 PASS ×2、Bad page=0。

## 4. 连带修复：liveness 门不能拦 ACK

M2f 的 csg_live 门原版在 TERMINATE 时先标死再 `continue`——跳过了幂等
ACK 写（`c_out=req`），内核等 TERMINATE ack 超时（`CSG 0 update request
timedout`，净机实锤）。修：ACK 追平无条件执行，门只拦 ring 消费。

## 5. 取证装备（本轮沉淀）

- `GPUHIST=1`：每 job 打 opcode 直方图快照（差分=单 job 内容）
- `GPUSEG=1`：CALL 用户段前 16 条 opcode dump
- `GPUFBG`：clear 落点链（含 bf）
- mesa 权威源码就位：`/tmp/mesa`（gitlab.freedesktop.org 稀疏克隆——
  **Anubis 拦 HTTP 不拦 git 协议**，`git clone --filter=blob:none --sparse`
  即可；v10.xml 的 CS Opcode 枚举=指令表权威，pan_cmdstream.c=GL 驱动
  draw 路径，pan_fb.c/pan_desc.c=RT 描述符打包）
- guest 传输：/tmp/send3.py（240 字符分块 base64+md5 终验；串口在会话
  中断后要 \x03 预踢）

## 6. 边界与下一刀

- RUN_IDVS/RUN_FRAGMENT 仍是 fake-complete（解释器跳过）；readback=
  [0,0,0,0] 是未渲染 BO 原文。**桌面可见= shader 执行，note 76 判据不变**。
- M2h 候选切面（按性价比）：
  1. **RUN_IDVS 的 DCD 解析**（dump 顶点描述符/位置缓冲——先把
     `cs_run_idvs` 的 fbd/dcd 参数落点打通，像素仍可免责）
  2. RUN_FULLSCREEN(8)+最简 DCD 纯色 quad（blitter 路径，段 1926 行
     `cs_run_fullscreen(b, 0, dcd_pointer)`——readback blit 就走它）
  3. tiler 多边形列表堆（HEAP_SET/HEAP_OPERATION 已在流中可见）
- 挂账不变：真机 fixture 补采、PANTHORIOCTL 打点撤除、restore 多核
  （note 85）。
