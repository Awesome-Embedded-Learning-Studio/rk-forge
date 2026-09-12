# Note 101 · panthor M2n 侦察：mutter 采样 FS 全链现身

日期：2026-09-06 · 战役七第二十篇 · 上一节：note 100（M2m 桌面会话定界）

## 0. 摘要

**mutter 桌面合成的采样 fragment shader 指令流全数到手**。正路是跟
SPD 指针（v10.xml "Shader Program"）：w0=Type/Stage/RegAlloc、
**Binary 在字节偏移 +8**（首版误读 +0x10——genxml start="2:0" 是
32-bit 字号，首版输出的"pre"其实就是 Binary）。桌面合成 = 每次
boot 数百个 **RUN_IDVS 4 顶点 quad 直绘**（非索引），97% 带采样
FS；note 100 的"RUN_IDVS=0、合成全走 RUN_FRAGMENT"判据作废
（读数口径错误），桌面黑的真正原因 = 采样 draw 的 FS 执行缺失。

## 1. 修正两个上节误判（证据链）

1. **RUN_IDVS 并非 0**：op_hist（`qom-get /machine op-run-idvs`，
   HMP qom-get 直读）5 分钟 587 次；584 次带 fragment SPD（r20≠0），
   仅 16 次无 FS（panfrost_fs_required=false 路径，pan_csf.c 显式
   载 0）。上节的"0"是仪器挂点+读数方法的假象。
2. **批池邻近扫描不是通用法**：M2l 的 ATEST 锚（op=0x7d dest=r60）
   是 glestriangle 编译巧合；mutter 的 ATEST dest 不同（尾声字
   `487dbc0200ea037c` 全 shader 恒定，可作 mutter 类新锚）。

## 2. SPD 正路（v10.xml 权威）

```
SPD（"Shader Program"，align 32）：
  w0[3:0]=Type(8=Shader)  w0[7:4]=Stage(2=Fragment,3=Vertex)
  w0[31:30]=RegAlloc(2=32/thread)
  Binary 64bit @ +8  ← 代码 PC（pan_cmdstream prepare_shader 填
                        state->bin.gpu；csf_emit_shader_regs → r20）
IDVS SR（v10.xml enum）实测全景（GPUFSX sr:）：
  r4=SRT_2(资源表) r12=FAU_2 r16=SPD_0 r20=SPD_2 r24=TSD
  r33=INDEX_COUNT(=4) r34=INSTANCE_COUNT(=1) r40=TILER_CTX
  r50=BLEND_DESC r52=ZSD r54=INDEX_BUFFER(=0 非索引) r57/58=DCD
SRT_2 → Resource 16B/项（addr56+contains-bit 0x100 @+0、Size @+8）：
  实测 4 项（0x40/0x20/0x20/0x20 @7ffffffd42xx）= 纹理/采样器描述符链
```

## 3. 采样 FS 形态（三大类，全字 dump 在 scmi-dbg.log）

| SPD | 次数 | 指令序列 |
|---|---|---|
| e5020 | 443 | LD_VAR_SPECIAL(0x56)+LD_VAR_BUF_IMM(0x5c) → **TEX_FETCH(0x125)** → FMA.f32(0xb2)×n → ATEST → BLEND |
| a9b80 | 113 | LD_VAR×4 → IADD_IMM+MOV → **TEX_SINGLE(0x128)×2** → FMA×n → ATEST → BLEND |
| a9ce0 | 1 | LD_VAR → IADD_IMM → MOV → **TEX_SINGLE** → ATEST → BLEND（最简，9 条） |

TEX_SINGLE 操作数（valhall.py 位段）：读 staging 基址=bits[45:40]
（r19:r20=64bit 纹理描述符指针——前导 IADD_IMM 就是算它：SRT 基址
+纹理索引偏移）、写 staging 基址=bits[21:16]（r0-r2=RGBA fp16 结果
直通 BLEND 通道）、sr_count=bits[35:33]。FMA.f32=采样值×颜色调制
（透明度/着色）。采样 FS 本体 ≤16 条——深水区比 note 76 预估的
"per-pixel shader"窄：**每像素 = 仿射 uv 插值 + 1-2 次采样 + FMA +
blend**。

## 4. 资源链全解（受控测试 gtx + 全链 dump）

受控测试 `sim/glestexture.py`（2×2 四色纹理 + NEAREST + 全屏
TRIANGLE_STRIP quad，顶点形态与 mutter 同构 r33=4）——当前 FAIL
全零（预期：采样未实现），其 draw 的全链 dump 补齐最后拼图：

```
SRT 下标 = 表号（pan_context.h）：0=UBO 1=ATTRIBUTE 2=ATTR_BUF
  3=SAMPLER 4=TEXTURE 5=IMAGE 6=SSBO；表项 16B {addr56|contains@56,size@+8}
Buffer（表项指向的数组元素，32B，v10.xml）：
  Type@w0[3:0]  Size@w1  **Address@w2（+0x10）**  Stride/Packet@w4
gtx 实测（fragment SRT_2）：
  t1[ATTRIBUTE]（32B ATTRIBUTE 描述符：Type=5、offset=0x400/0x410
    ——pan 源码 1024 基实锤、Format@w0[31:10]）
  t3[SAMPLER] 32B 描述符（NEAREST/CLAMP 默认形态）
  t4[TEXTURE] Buffer[0]={Size=0x1688, Addr=0x7fffffeaa080}
    ——纹理描述符在批池，待接 M2i plane 解析
FS 受控形态（单采样最小版，9 条）：
  LD_VAR(uv) → IADD_IMM(texdesc=SRT 基+索引) → MOV →
  TEX_SINGLE(1128009453c02042：读基址 r19:r20、写 r0-r2) →
  MOV → ATEST(487dbc0200ea427c) → BLEND → IADD_IMM → 尾跳(0x2f)
```

## 5. M2n 实现路径（下轮工程）

RUN_IDVS 挂点（非 RUN_FRAGMENT）：SRT_0（r0）→ t1/t2 → 顶点属性
Buffer → 4 顶点（pos+uv，FORMAT 按 ATTRIBUTE desc 解）；SRT_2 →
t4 → Buffer.Addr → 纹理描述符 → plane（M2i）→ texel 读三形态
（M2j）；光栅化 quad 到 FBO（仿射 uv + nearest 采样 + FMA×1.0 +
BLEND）。全部由 guest 描述符数据驱动，固定功能形态但真数据路径。
验收 = gtx 四象限色 + gt（常量色回归）+ mutter 桌面 screendump 主色。

## 6. 资产与验收形态

- `GPUFSX`（新）：SPD_2/SPD_0 跟指针全字 dump + IDVS SR 全景 +
  SRT 七表全链跟读（表项→Buffer 数组→首描述符 32B，PA 翻译走
  va_pa_user 非 PA 线性猜测）
- `GPUFCS`：原 RUN_FRAGMENT 批池扫描（CS 流上有 tex 族假阳性，
  已知局限：9-bit 扫描分不清 CS 指令与 shader 指令）
- `sim/glestexture.py`：受控采样测试（FAIL 基线已立）
- glestriangle 同机对照：FSCOLOR 蓝 PASS 无回归（M2l 路径完好）

## 7. 工作流坑（本轮新增）

- **pkill/pgrep -f 自杀**：模式串出现在自己工具命令文本里 → 匹配
  wrapper shell → exit 144 且后续命令不执行；kill 与启动必须拆成
  两次工具调用，kill 用 `res[b]oot.py` 括号技巧 + `pkill qemu-system`
  （comm 15 字截断），判活用 `ss -tln | grep 4446` 别用 pgrep -f
- resboot.py 会堆积僵尸进程（各自 sleep DUR 后 p.kill）——重启前
  清理；`open(/tmp/scmi-dbg.log,"w")` 每次启动截断日志（历史 dump
  要及时摘走）
- HMP qom-get 可直读 op_hist 计数（`qom-get /machine op-run-idvs`），
  免 GPUHIST 重启——回显有终端转义污染，正则剥 `x1b[[KD]`
