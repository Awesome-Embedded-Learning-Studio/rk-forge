# Note 97 · panthor M2l 侦察：常量色 FS——常量不在内存里

日期：2026-09-06 深夜 · 战役七第十六篇 · 上一节：note 96（M2k AFBC 基建）

## 0. 摘要

桌面可见最后判定 = 常量色 fragment shader 执行。两轮侦察的否定性结论
同样有价值：

1. **FAU 寄存器不是裸指针**：IDVS SR 的 FAU_0/2（regs 8/12）实测只装
   低 32 位 + 页选复合编码（kraid model.rs 的 FAUModel/user_page_idx
   佐证：FAU 是 GPU 内 RAM，按页索引）——`ptr|count<<56` 的
   hw_runner 形态是 compute 路径，不适用 draw。
2. **常量不在内存里**：批池区（SPD_2±0x8000）扫 fp32 RGBA quad
   （红=3f800000,0,0,3f800000）**零命中**——Valhall 编译器把
   0.0/1.0 类常量烤进**指令立即数 + FAU RAM 预置小常量表**
   （kraid small_constants.rs 的 SmallConstantTable）。
   ⇒ 常量色提取 = **Valhall 指令解码**，无数据旁路。
3. **SPD_2=regs[20] 不直指 Shader Program**：其 +0 首字非 Shader
   类型、+16 Binary=0——fragment 程序描述符经 SRT 的 0x40 载体再
   间接（note 93 载体 w5 指向批池深处）。

## 1. 资产（本轮仪器，随补丁落库）

- `GPUFAU=1`：常量 quad 锚点扫描（批池区 fp32 RGBA 模式匹配）
- `GPUSPD=1`：SPD 链 dump（regs[20]→+16 Binary→二进制 24 条）

## 2. M2l 主战役施工图（下一会话）

1. **宿主编译 Bifrost 反汇编器**：`/tmp/mesa/src/panfrost/compiler/
   bifrost/disassembler/`（ISA.xml 权威在 valhall/ISA.xml）——standalone
   编译或最小化抄核心；WSL 重启会清 /tmp/mesa（重新稀疏克隆，git 协议
   过 Anubis）。
2. **定位 FS 二进制真链**：0x40 载体（note 93）的字段考古 → 找
   Shader Program Descriptor 的真身 → Binary 指针 → dump。
3. **解码常量色模式**：常量 FS ≈ 2-4 条 Valhall（load imm/small-const
   → writeout）；识别该模式 → 提取 RGBA → 以 FS 语义铺 FBD
   （RUN_IDVS 的 coverage= 全屏三角形）。
4. **验收**：glestriangle 红 PASS + 蓝变体 PASS（证明色值来自 guest
   shader 数据流而非硬编码）——即 note 76 证据门的"真 shader 语义"。

## 3. 边界

- mutter 桌面（多窗口纹理合成）仍超出常量色范畴——M2l 达成后的下一程。
- WSL 重启清 /tmp：sercmd2/send3 已重建入库节奏（脚本在 sim 会话记忆
  里，重建按本文）；/tmp/mesa 克隆命令：`git clone --depth 1
  --filter=blob:none --sparse https://gitlab.freedesktop.org/mesa/mesa
  && git sparse-checkout set src/panfrost`。
