# Build Progress Tool — 决策与分析

> 进度可视化工具（给 make-based 嵌入式 build 用）的设计决策记录。
> 状态：**分析完成；first-use 准度已实测定案（认 −6%）**。日期：2026-07-06（实测同日）。

## 1. 问题

给 **GNU Make-based 的嵌入式构建**（Linux kernel Kbuild / U-Boot / Buildroot）做进度可视化——build 进行中显示"已完成 X / 总共 Y，Z%"，解决"72 分钟 build 不知道是 10% 还是 90%"的痛点。

- **分子 X**（已完成）：好拿。解析 make stdout 数 CC 行，或数 build 树里出现的 `.o` 文件。
- **分母 Y**（总数）：**全部争论的焦点**。这是本文档分析的核心。

## 2. 约束（硬性）

1. **first-use**：第一次 build（空树、从未编过）必须有解——不能依赖缓存预热。
2. **分发友好**：工具要给别人/跨项目用，不能假设对方编过。
3. **make-based**：目标是 kernel/uboot/buildroot（GNU Make + Kbuild），不是 CMake/ninja。
4. **准确 + 便宜**：误差 <2%，预扫描 <几秒（理想）。

## 3. 根因：GNU Make 决定了"没银弹"

GNU Make 是**两阶段模型**（调研确认，源自 GNU make 手册 + 联网 AI 审查）：

1. **第一阶段**：读 Makefile、内化变量和规则。
2. **第二阶段**（update）：沿依赖图 + 时间戳 + 生成文件 + 递归 make，**才算出"实际要跑哪些动作"**。

也就是说，"要编译哪些 .o"**不是读完 Makefile 就稳定存在的静态列表**，而是 update 阶段动态算出来的。Kbuild 的递归下降（顶层 Makefile → 每个 subdir 的 Kbuild → 用 `.config` 构造目标列表）更坐实了这点——它不是一个平铺的全局 compile list。

**结论：没有"读完 Makefile 就准确知道编译总数"的静态方法。** 唯一能拿到"实际动作清单"的是 make 自己的 update 模拟（`make -n` dry-run）。

## 4. 分母（Y）方案逐条分析

| # | 方案 | first-use？ | 准？ | 快？ | 判定 | 证据 |
|---|---|---|---|---|---|---|
| 1 | **`make -n -k` dry-run**（顺序，build 前跑）| ✓ | ≈ **−6.18%**（vmlinux 断链，`-k` 修不了；post-link CC 全漏）| ❌ 慢（15s 解析，固定）| **唯一 first-use 准选项**（认 −6%） | 实测干净树 4875/4878 vs 真建 5196；根因 `No rule 'vmlinux.a'` → vmlinux_o abort → post-link（zImage 解压器/vdso/.vmlinux.export）不枚举 |
| 2 | dry-run + `-B`（--always-make）| ✓ | ❌ | ❌ | **失败** | 实测：kernel 已建树上 `-B -n -k` 只数出 28（宿主工具），**不枚举 cross-CC**（Kbuild 递归短路）|
| 3 | 并发 dry-run + 真建（隐藏 15s）| ✓ | ❌ | ✓ | **失败** | 无 `-B`：dry-run 看到真建进度→欠数；带 `-B`：见 #2，不枚举 |
| 4 | learned-total（缓存上次计数）| ❌ 第一次没 | ✓ 重复 | ✓ | **弃** | first-use 无用；**增量上错**（计数每次变）；用户否决缓存 |
| 5 | compile_commands.json | ❌ kernel 是 post-build | ✓ | — | **弃** | kernel 的从 `.cmd` 抽（`extract_compile_commands.py`），build 后才有；CMake 原生但目标项目不是 CMake |
| 6 | 静态分析库（pymake/Makefile::Parser/unmake）| ✓ | ❌ | ✓ | **弃** | 处理不了 Kbuild（`$(eval)`/`$(call)`/生成的 Makefile）；联网调研确认无成功案例 |
| 7 | `make -p`（print database）| ✓ | ❌ | ❌ | **弃** | 打印 read-in 后数据表，**不是 update 决策**；不比 `-n` 适合作分母；解析复杂 |
| 8 | Bear / intercept-build | ❌ 要真编 | ✓ | — | **弃** | 拦截 build 中的 exec 调用，必须真 build |
| 9 | indeterminate（无 %）| ✓ | N/A | ✓ | **不解决问题** | 用户明确要 %"我在哪"，indeterminate 不答 |

**最终结论：first-use 准确 % 只有"顺序 dry-run（`make -n -k`）"这一条路，代价是 15s 预扫描阻塞。make-based 没银弹。**（联网 AI 独立审查得出相同结论。）

**2026-07-06 实测补刀**：dry-run 在干净 multi_v7 树欠 **6.18%**（预扫描 4875/4878 vs 真建 5196）。根因**不是** objtool 截断（`-k` 已修那部分，前 4875 个 CC 全靠它枚举出来），而是 **vmlinux 链接处断链**——`vmlinux.a` 是 recipe 产物、dry-run 不生成，make 报 `No rule to make target 'vmlinux.a', needed by 'vmlinux.o'` 后 vmlinux_o 子图 abort，post-link 的 ~263 个 CC（`arch/arm/boot/compressed/*` zImage 解压器 / `arch/arm/vdso/*` / `.vmlinux.export.o` / 依赖 asm-offsets 的 `mach-omap2` 等）整段不枚举。`-k` 无效（vmlinux.a 是硬前置，keep-going 绕不过）。**这是 dry-run 对"link-then-compile"型构建的固有缺陷，认了。** per-verb：AR 1029=1029 完全准、AS −9、LD −5、CC −263（缺口全在 CC）。

## 5. 增量 build 的特殊性（关键洞察）

增量 build（改几个文件、重编）暴露了 dry-run + learned-total 的共同硬伤：

- **dry-run 能数对**（只数要重建的几步），**但 15s 解析开销是固定的**（跟步骤数无关）→ 秒级增量 build（5s）被 15s 预扫描拖成 20s，**工具把 build 时间翻了 4 倍**。荒唐。
- **learned-total 在增量上是错的**——它存的是全量计数（5136），增量只做 5 步 → bar 显示 `5/5136 (0%)`，无用。learned-total 假设"同配置=同计数"，但增量每次改的不同、计数不同。
- **增量 build 短（秒级），本身不需要进度条。**

**判别 clean vs 增量**（毫秒级）：
```bash
find <tree> -name '*.o' -print -quit | grep -q . && echo "有 .o → 大概率增量" || echo "无 .o → clean 全编"
```

## 6. 决策矩阵（当前共识）

| 场景 | 分母来源 | UX | 开销 |
|---|---|---|---|
| **clean build**（无 `.o`）| `make -n -k`（15s 预扫描）| **准 ~94% + finalizing 尾部**（主体 0→100% 准；done 超 total 切 "finalizing post-link"，cap 不溢出 100%）| 15s 阻塞（分钟级 build 可接受）|
| **增量 build**（有 `.o`）| 无（跳过预扫描）| indeterminate（count + rate + 当前文件）| 0 开销、秒起 |
| **opt-in %**（增量也想要 %）| `--prescan` 显式开 | dry-run % | 用户自付 15s |

**进度条的甜区 = clean / 大改后的长 build**（无 .o 或大量 .o 过期）。那里 15s 预扫描值、% 最有用。**增量短 build 直接放行**（indeterminate），不收税。

## 7. 已弃方案汇总（别再走）

- **learned-total / 缓存**：first-use 无用 + 增量错 + 用户否决。
- **并发 dry-run**：`-B` 在 kernel 实测失败（28，不枚举 cross-CC）。
- **静态分析库**：处理不了 Kbuild。
- **compile_commands.json**：kernel first-use 无（post-build）。
- **indeterminate-default**：用户要 %，不解决"我在哪"。

## 8. 待验证（open items）

1. **✅ 已实测（2026-07-06）** `make -n -k` 在干净 multi_v7 树上的计数：dry-run **4875/4878**（两次，±3 = −j14 并发行合并噪声）vs 真建 **5196**，欠 **321 / 6.18%**。per-verb：**AR 1029=1029 完全准**、AS −9、LD −5、**CC −263**（缺口全在 CC）。根因**不是 objtool**（`-k` 已修，前 4875 个 CC 靠它枚举），而是 **vmlinux 链接断链**：dry-run 不生成 `vmlinux.a` → make 报 `No rule to make target 'vmlinux.a', needed by 'vmlinux.o'` → vmlinux_o 子图 abort → post-link 的 ~263 CC（`arch/arm/boot/compressed/*` / `arch/arm/vdso/*` / `.vmlinux.export.o` / asm-offsets 依赖的 `mach-omap2` 等）整段不枚举。`-k` 无效（硬前置）。**定性：dry-run 对"link-then-compile"构建的固有缺陷，非 forge bug，非 −k 能修。修法已定：cap 100% + finalizing 尾部（见 §10）。**
2. **增量检测（`find .o`）的假阳/假阴**——clean-ish 树（部分 .o）会被判"增量"→ 跳过预扫描。实际影响多大？
3. **uboot/buildroot 的 dry-run 行为**——kernel 踩的 objtool 坑，uboot/buildroot 有没有类似的？需各 profile 实测。

## 9. 产品形态（buildmeter，Python-first）

**为什么 Python-first**（用户决策）：跨平台（Win/Mac/Linux）+ 绕开这轮打的全部 bash 怪癖（pipefail/exit-code、stdbuf 缓冲、`$buf` 引号、`set -u`）。Python subprocess 结构上消灭它们。

```
buildmeter/
  runner.py     # ★ subprocess 编排：
                #   1. detect: find -name '*.o' → clean or 增量?
                #   2. clean → 后台 make -n -k 预扫描（分母）；增量 → 跳过
                #   3. Popen(make) 真建，逐行读 → 分子（数 CC/.o）→ 渲染 bar
                #   4. tee log + 错误捕获
  engine.py     # 渲染器 + ringbuffer（从 rk-forge progress.py 抽）
  profiles/     # kernel(kbuild) / uboot(kbuild+binman noise) / buildroot(>>> pkg)
  cli.py        # `python -m buildmeter run kernel -- make ...`
  tests/        # replay fixture assert 计数（回归网）
```

**分子（X）**：Python `Popen` 逐行 `readline()`（无需 stdbuf），数 CC 行 + 当前文件路径。
**分母（Y）**：clean 模式 → `make -n -k`（`{...|| true}` 吞非零退出）；**已知欠 ~6%（vmlinux 断链）→ bar 超 total 时切 "finalizing post-link"、cap 100%（progress.py `done > total` 分支已落地，replay 3 场景验证：欠数→finalizing / 准确→100% / 过大→正常 bar）**；增量模式 → 无（indeterminate）。
**rk-forge 关系**：rk-forge 现有 bash 版（forge-progress 分支，板上验证过）先不动；buildmeter 独立成长，成熟后 rk-forge 可切。

## 10. 决策清单（要拍的）

- [x] 认 make-based 没银弹，first-use 准 % = 顺序 dry-run（15s 税）。
- [x] 砍 learned-total（增量错 + 否决缓存）。
- [x] clean vs 增量 自动切（`find .o` 检测）。
- [x] Python-first（buildmeter）。
- [x] **`make -n -k` 在干净树欠数**：实测 **6.18%**（非 <2%），根因 vmlinux 断链（`-k` 修不了）。**认了。**
- [x] **clean 模式 6% 欠数处理**：cap 100% + done 超 total 切 "finalizing post-link" 尾部（progress.py `done > total` 分支已落地，replay 3 场景验证通过）。
- [x] **buildmeter @ AELS org**（github.com/Awesome-Embedded-Learning-Studio/buildmeter），名字+位置 2026-07-06 定。"meter" 比 "kit" 准（这是 build 进度计量仪，非工具包）。
- [ ] rk-forge 的 bash forge-progress：收尾合并，还是等 buildmeter 切换后弃？
