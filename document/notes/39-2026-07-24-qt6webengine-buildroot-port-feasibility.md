# Qt6 WebEngine 移植进 forge buildroot —— 可行性评估与路线

> 评估"自己 patch 一份 qt6webengine 塞进 board/rk3568-atk/buildroot-external/"的可行性 + 最佳起点 + 移植路线 + 工作量 + 风险。workflow: 8 agents / 468k tokens / 2026-07-24。工具链: /opt Arm GNU 15.3.Rel1 (gcc 15.3.1, glibc 2.42) / buildroot 2026.08-git / Qt 6.9.1。

## ⚠ critique 的关键修正（读 synthesis 正文前必看 — 风险图景被纠正）

synthesis verdict = **go-with-risk**（维持），但它的**风险排序画反了**。critique 独立取证后的净修正：

1. **头号阻塞不是 gcc15，是 host-python3 = 3.14.6**（实测 `package/python3/python3.mk`）。chromium 130 的 grit/torque/polymer 脚本在 Python 3.14（2025-10，移除更多 deprecated）下几乎必然崩，且**比 gcc15 链接问题早得多地崩**（host 侧 GN 生成阶段），**无现成 patch**（qt5 补丁只到 3.12）。6 份 research + synthesis 全员漏报。mitigation: backport 3.13/3.14 兼容补丁，或临时降 host-python3 到 3.11/3.12（牵动重建链）。
2. **gcc15 R_AARCH64_CALL26 不是"至今未解"**：openSUSE 1251922 是 RESOLVED→REOPENED 的回归性问题，且有 synthesis 漏提的缓解路径——OE-Core 的 binutils linker veneer 补丁、试 lld、查 Arm GNU 15.3 自带 binutils 是否已插 veneer。从"不可估/block"降为"有路径待验证"。（诚实：/opt 工具链的 ld 是否有 veneer 未在沙箱验证。）
3. **RFC recipe 不是"90% 现成"**：作者自标 5 处未闭合（system ICU "DEBUG THIS" / system ffmpeg / host-python-html5lib 漏 patch / libnss select 漏写 / sysroot patch）+ 13 个月零回复零成功构建 + hash 仅 15 行（vs qt5 的 1256 行 = license 合规缺口）。是"结构完整的草稿"，不是"编得通"。
4. **wpewebkit + cog 全树内（synthesis 事实错误）**：`package/wpewebkit/`（2.50.5）+ `package/cog/`（0.18.5）都在 forge buildroot 树内——零 recipe 编写的 kiosk 栈，defconfig 勾选即可（待 Phase 2 Wayland/GLES/EGL）。这是最强替代方案，比 synthesis 呈现的成熟得多。
5. **工作量低估**：GN 工具链翻译（bitbake Python→mk，~15 变量）易多轮迭代（现实 3-5 轮，单轮 2-4h = 2x）；"临时换 gcc14 工具链"不是廉价 side-task（0.5-1 人日且不推进 gcc15 认知）。
6. **LGPL/license-hash 永久税**：每次 chromium bump 重生成 ~1200 行 hash + RFC 孤儿状态（13 月无人 review）= 永久自维护。

**一句话**：synthesis 的结论（go）对，但风险图景画反了——把可缓解的晚期链接器风险当头号怪兽，却没看见门口（host-python3 3.14）那个真会第一时间咬人的。

---

## Synthesis 正文

# Qt6 WebEngine 移植进 forge buildroot —— 可行性评估与路线

## 1. Verdict: **go-with-risk**

配方层"几乎能直接抄",但工具链层(gcc 15 + aarch64 + chromium)有一例**已观测的硬链接失败**,必须分阶段、把"写配方"和"攻工具链"解耦。

核心理由:
1. **现成起点极佳**:上游 buildroot 邮件列表已有一份完整的 qt6webengine RFC recipe(Roy Kollen Svendsen, 2025-06-28, patchwork `20250628140550`),592 行/8 文件,锚定版本正是 forge 树内的 Qt 6.9.1(`third_party/buildroot/package/qt6/qt6.mk:7-8`),版本零适配。Config.in 全部架构前置(aarch64 / glibc / host=x86_64 / EGL / udev)RK3568 全绿。
2. **头号风险有实证**:openSUSE Bug 1251922 记录 qt6-webengine 6.10.0 在 aarch64 + gcc 15 下链接 `libQt6WebEngineCore.so` 时 `R_AARCH64_CALL26` 重定位溢出到 libgcc 的 `__aarch64_cas8_acq`,**关 LTO 也救不回来**(lists.opensuse.org/archives/list/bugs/.../TFCJU5NALTVNDBYD42EGYL3CS2XPMBDJ)。forge 的 gcc 15.3.1 比该 bug 更新、chromium 130 略旧,属同类链接期故障,小补丁难绕。
3. **clang 退路成本高**:chromium 上游 Clang-only(`is_clang=false` 无 CI),meta-browser README 明写 "requires clang, GCC is not supported";而 buildroot 树内**没有** host-clang/llvm 包(grep `package/clang* llvm*` no matches),走 clang+libc++ = 再做一个子项目。
4. **有零移植替代**:`wpewebkit 2.50.5` 已在树内(`third_party/buildroot/package/wpewebkit/`),aarch64 一等公民、原生 Wayland、RAM 约为 Chromium 的一半,只缺 defconfig 勾选 + Phase 2 GPU。kiosk/Dashboard 场景更务实。
5. **硬前置未就位**:`rk3568_atk_defconfig` 还没开 GPU/EGL/Wayland(Phase 2),所有 web 引擎的运行验证都被 gate 住——与选哪个引擎无关。

## 2. 最佳起点

**主起点 —— 上游 RFC recipe(Qt 6.9.1,与 forge 完全对齐)**
- patchwork 入口(含 mbox 下载): `https://patchwork.ozlabs.org/project/buildroot/cover/20250628140550.4030996-1-roykollensvendsen@gmail.com/`
- 邮件列表 HTML(完整 diff 正文): `https://lists.buildroot.org/pipermail/buildroot/2025-June/781821.html`
- 含 `package/qt6/qt6webengine/{Config.in(79行), qt6webengine.mk(417行), qt6webengine.hash(15行), 0001-fix-chromium-build-in-buildroot-caused-by-duplicated.patch(25行)}` + 同系列 patch 1/2 `qt6webchannel`(qt6 树里缺,**必须一起加**,781758.html)。

**辅助参考(不要从 qt5 改起)**
- 本地 `third_party/buildroot/package/qt5/qt5webengine/qt5webengine.mk` —— 仅借鉴 `host-python-wrapper.in` / `host-pkg-config.in` 两个 wrapper 模板 + feature-flag 哲学。qt5→qt6 有三处硬断层(qmake→cmake、三包→一包、`-webengine-*`→`-DFEATURE_webengine_*`),不能改名复用。
- meta-qt6 **6.9 分支**(Chromium 130-based): `github.com/YoeDistribution/meta-qt6` —— GN 工具链生成(`gn-utils.inc::write_toolchain_file` 行 67-135)和 aarch64 V8 qemu wrapper 是 buildroot 侧缺失的关键拼图。**务必 pin 6.9 分支**(`SRCREV_qtwebengine-chromium=73d9c662bedb2dabd634fb7f43c1aa72ab5c02cb`),不要跟 master(6.11/Chromium 140),否则 qtbase ABI 对不上。

## 3. 移植路线

**Step 1 — 落配方骨架(用现成的)**
把 RFC 的 4 个文件 + patch 1/2 的 qt6webchannel 原样放进 `board/rk3568-atk/buildroot-external/package/qt6webengine/` 和 `qt6webchannel/`,在 `buildroot-external/Config.in` 加 `source`。`external.desc`/`external.mk` 已就绪,br2-external 原生支持,不动主树。版本变量 `QT6WEBENGINE_VERSION=$(QT6_VERSION)=6.9.1`、`SITE=$(QT6_SITE)`、`SOURCE=qtwebengine-$(QT6_SOURCE_TARBALL_PREFIX)-6.9.1.tar.xz` 全部复用 `qt6.mk` 定义,零改动。

**Step 2 — 补 RFC 作者自标的 TODO(自己写,局部补丁)**
RFC 正文里作者列了未完成项:① system ICU 被注释("DEBUG THIS");② system ffmpeg 待改;③ host-python-html5lib 漏发 patch —— 实际只需在 `third_party/buildroot/package/python-html5lib/python-html5lib.mk` 加一行 `$(eval $(host-python-package))`;④ libnss 必选未补 select;⑤ 唯一的 patch(注释掉 `target_sysroot`)想用 `-DCMAKE_SYSROOT=` 替代。都是几十行增量,不是重写。

**Step 3 — chromium 源与交叉编译 patch(用现成的 + 翻译一段)**
Qt6 的 chromium 已打包进 `src/3rdparty/chromium`(单 tarball, sha256 `787dfde2...`, `download.qt.io/archive/qt/6.9/6.9.1/submodules/qtwebengine-everywhere-src-6.9.1.tar.xz`)——qt5 那套三包 + catapult + cp hook **全部不需要**,这是 qt6 最大简化。交叉编译 patch 从 meta-qt6 6.9 分支取:① `0001-CMake-use-generated-yocto-toolchains.patch`(把 GN toolchain 指向 `//build/toolchain/yocto:yocto_{target,native}`);② `chromium/0001-v8-qemu-wrapper.patch`(aarch64 V8 snapshot 走 qemu,buildroot 有 qemu-user,直接复用);③ 把 `gn-utils.inc::write_toolchain_file()`(行 67-135,bitbake Python)**翻译成一段 mk hook**,生成 `BUILD.gn`,cc/cxx/ar 指向 `$(HOST_DIR)/opt/ext-toolchain/bin/aarch64-linux-gcc`。**这段是核心技术风险点**,错了表现为链接期找不到符号或软浮点 ABI 错。`chromium/0002-...clang` patch 是 meta-clang 专用,**先不要套**。

**Step 4 — host 工具依赖(用现成的)**
buildroot 树内已齐:`host-nodejs`(`package/nodejs`)、`host-ninja`、`host-python3`、`host-fontconfig`、`host-bison`/`flex`/`gperf` 全在;`python-html5lib` 加 host 变体(见 Step 2)。gn 不需要独立 host 包——RFC 用 `host-cmake-package` + `-DBUILD_ONLY_GN=ON` 自举编出 GN。官方要求 Node.js≥20.0、host gcc≥10(C++20),forge host(gcc 15, x86_64)满足,**但要确认 `host-nodejs` 当前版本≥20**。

**Step 5 — 工具链风险预案(分阶段,自己决策)**
- **Phase A**(低风险,必有产出):配方骨架先落地,用一个**降级到 gcc 14 或更早**的临时外部工具链验证整条 cmake→gn→ninja 构建链能通。隔离"配方对不对"和"gcc15 能不能编"两个问题。
- **Phase B**(高风险,可单独决策):攻 gcc-15-aarch64 链接问题。三选一:(a) 继续用 gcc 但补链接脚本/原子助手放置策略(SUSE/Gentoo 自己都没闭合,高风险);(b) 降级工具链到 gcc 13/14(最稳,但与 forge 锁定的 Arm GNU 15.3 冲突);(c) 引入 host-clang+libc++(buildroot 无现成包,工作量等于子项目)。**不要把 A 和 B 绑死**,否则会被工具链 bug 拖垮里程碑。

## 4. 工作量预估

| 块 | 量级 | 说明 |
|---|---|---|
| buildroot 包封装 | **天级(1-3 人日)** | 抄 RFC + 补 qt6webchannel/host-python-html5lib + adapt 到 2026.08-git 基线(核对 `QT6_GL_SUPPORTS` 等 symbol 是否还在)。配方是抄,不是写。 |
| chromium 交叉编译调通 | **周级,高不确定(3-6 人日 + 1-2 轮 build)** | GN 工具链文件生成 + sysroot/`CMAKE_SYSROOT` 收敛 + ~25 个 PACKAGECONFIG 翻译。单轮 aarch64 build 2-4 小时,内存峰值 16-32GB,磁盘 30-50GB。 |
| gcc-15 链接问题(Phase B) | **不可估,可能 1-2 周或 block** | `R_AARCH64_CALL26` 是链接期硬故障,openSUSE 至今未解。这是决定 qt6webengine 能否真上产品的变量。 |

## 5. 风险表

| 风险 | 概率 | 影响 | mitigation |
|---|---|---|---|
| **gcc-15 aarch64 链接 `libQt6WebEngineCore.so` 的 `R_AARCH64_CALL26` 溢出**(openSUSE 1251922 实证,关 LTO 无效) | 高 | 致命(可能数小时编译后在最终链接步才崩) | Phase A 先用 gcc14 验配方;Phase B 三选一:降级工具链 / 攻链接补丁 / 引入 host-clang |
| gcc-15 编译期 `-Werror` 新警告(cstdint / template-id-cdtor / enum-int-mismatch) | 中 | 中 | `qt5webengine-chromium/0009` cstdint backport 可试;准备 `-Wno-error=*` |
| WSL2 OOM / 磁盘满 / `ulimit -n`(Qt 6.8.3 实测 "Too many open files") | 高 | 中(构建中断,不毁结果) | swap 32GB+,`NINJAFLAGS=-j2~-j4`,调高 `ulimit -n`,PATH 去空格(见 MEMORY rk3568-build-gotchas) |
| chromium Clang-only 无 CI,gcc-compat patch 随版本漂移 | 中 | 中(长期维护成本) | 锁 Qt 6.9.1 / chromium 130,不追新;接受"自维护" |
| 上游 RFC 未合入,作者自标 TODO(ICU/ffmpeg/sysroot/libnss) | 高(已知未完成) | 低-中(局部补丁) | 自己补完,见 Step 2 |
| GN 工具链文件生成(bitbake Python → mk hook 翻译) | 中 | 高(错则链接期符号/ABI 错) | 抄 meta-qt6 `gn-utils.inc`,逐变量对齐 `$(TARGET_CC)`/`$(TARGET_CXX)`/`$(HOST_DIR)`/`--sysroot` |
| Phase 2 GPU/EGL/Wayland 未开(defconfig 无 GPU) | 确定 | 运行期阻塞(编译过不代表能跑) | 并行推 Phase 2 Mesa/Panfrost+Wayland;先只验 compile |
| glibc 2.42 兼容 | 低 | 低 | chromium 130 对 glibc 是"最低版本"要求(~2.26-2.31),2.42 远高于下限;真正 header 风险在 kernel-headers 6.6.44 与 chromium 自带 `linux/` 头的 `statx` 字段,沿用 `qt5webengine-chromium/0001` sysroot 思路 |

## 6. 决策建议

**目的 A — 学习 / 填 buildroot 上游缺口:做。**
难得的练手 + 填补 buildroot qt6webengine 空白的机会。当前是**最佳窗口期**:forge 树 Qt 正好 6.9.1,与上游 RFC 精确对齐,版本零适配;一旦 buildroot 把 Qt 升到 6.10+,RFC recipe 就要 rebase,门槛抬高。建议 **Phase A 必做**(配方落地,用 gcc14 验证构建链通),Phase B 作为可选的硬骨头挑战。

**目的 B — 产品尽快上 web:先问"是否真需要 Chromium"。**
- 需要 V8 JIT 性能 / 复杂 SPA / WebGL2 / WebRTC / 站点 Blink 兼容性 / in-process QML webview+QWebChannel → **qt6webengine 必要**,但要接受 Phase B 的工具链风险,且产品交付前必须真机验通 gcc15 编译。
- 只是 HTML5/CSS/JS 的 kiosk/Dashboard、且在意 RAM → **wpewebkit 2.50.5**(已在树内,aarch64 一等公民,原生 Wayland,RAM 约一半)远比自 patch 一个未合入主线的重型 recipe 务实,只需 defconfig 勾选 + Phase 2。
- 只是静态 HTML / 极简 JS、且 framebuffer → **netsurf 3.10**(树内,SDL 前端可免 GPU)。
- UI 能用 Qt/QML 或 LVGL 直接画 → 根本不需要 web 引擎。

**qt5webengine 什么时候更务实?** 仅当:已有 Qt5 UI 遗留 + 短期产品 + 接受 Chromium 87 内核。注意三点:① qt5webengine 内嵌的是 **Chromium 87**(`third_party/buildroot/package/qt5/qt5webengine-chromium/qt5webengine-chromium.mk:6`, commit `85337c28...`),和你要避开的 vendor chromium 88 **几乎同代甚至更老**,换 Qt5 拿不到比 vendor 更新的内核;② Qt 5.15 LTS 开源 EOL 2026-09(KDE fork 续命),Chromium 87 是 EOL-era,安全仅靠 backport;③ 但 `qt5webengine-chromium` 已带 GCC 15 cstdint 补丁(`0009`)和 python3.13 补丁,**工具链层面零额外移植**——这是它唯一真正的优势。新设计不建议。

---

## 附: 完整对抗性评审原文 (critique)

验证完成。以下是我的对抗性评估。

---

# 对抗性复核 — qt6webengine 移植可行性评估

我做了独立取证(本地 grep + web)。总体判断先说:**verdict "go-with-risk" 站得住,且在用户最担心的 gcc15 问题上反而偏保守(并非过于乐观)**。但 synthesis 的**风险预算错配**:过度加权了一个其实有缓解方案的链接器问题,却完全漏掉了一个无缓解的 host-python 阻塞,并把一份未经验证的 RFC 当成"90% 现成"。此外对 wpewebkit 替代方案有事实性低估。下面逐条。

## Issues

### BLOCKER 1 — host-python3 = 3.14.6,chromium 130 的构建脚本几乎必然崩(全员漏报,含 synthesis)

- **证据**:`third_party/buildroot/package/python3/python3.mk` → `PYTHON3_VERSION = 3.14.6`(host-python3 即此版本)。qt5webengine-chromium 自带的 Python 兼容补丁只覆盖到 **3.11/3.12**(`0005-Fix-build-in-Python-3.11-invalid-mode-rU.patch`、`0004-...Python-3.12...patch`);0003 是泛化 py3 迁移。chromium 130 是 2024 年的代码,它的 grit/torque/polymer 脚本在 3.14(2025-10 发布,移除了更多 deprecated 模块、收紧了 `imp`/`ast` API)下出问题几乎是确定的——6 份 research 全部只说"Python 3.11/3.12 有已知 break",没人意识到本树 host-python 已经是 3.14。
- **影响**:这不是 target 侧、不是 gcc、不是链接器——是 host 侧 GN/工具链生成阶段。会在构建**极早期**就崩,比 R_AARCH64_CALL26 早得多。且没有现成 patch(qt5 树只到 3.12)。
- **建议修正**:synthesis 的"Step 4 host 工具依赖——已齐"是错的。必须新增一行风险:host-python3 3.14 vs chromium 130 脚本不兼容,需自行 backport Python 3.13/3.14 兼容补丁(或临时把 host-python3 降到 3.11/3.12,但那会牵动 host-nodejs/ninja 之外的重建链)。这条应进风险表,severity 不低于 gcc15。

### MAJOR 2 — R_AARCH64_CALL26 被定性为"至今未解 / 可能 block",实为 FIXED-then-REOPENED,且缓解方案未被调研(偏悲观,但导致 Phase B 被高估为"不可估")

- **证据**:openSUSE Bug 1251922 的状态是 **RESOLVED→FIXED 之后又 REOPENED**(web 检索命中两个 thread:`.../2JDK2HL4.../` 标 RESOLVED|REOPENED,`.../TFCJU5NAL.../` 是"disabling LTO is not enough anymore"的回归)。即:曾修过,因 chromium/gcc 滚动而复发——是**回归性**问题,不是"从未解决"。而且存在 synthesis 完全没提的缓解路径:OE-Core 有专门修 chromium/ffmpeg aarch64 `R_AARCH64_CALL26` 的 **binutils linker veneer 补丁**(lists.openembedded.org/g/openembedded-core/topic/patch_binutils_fix_linker/78426389);根因是 binutils ld.bfd 对超大 DSO 不插 veneer(binutils ld/18668),不是纯 gcc 问题。
- **影响**:synthesis 把 Phase B 写成"三选一:降级工具链 / 攻补丁 / 引入 host-clang",漏掉了最便宜的第四条:**核查 Arm GNU 15.3.Rel1 自带的 binutils 是否已插 veneer / 试 lld / 试 OE 的 binutils patch**。这让 Phase B 显得比实际更 open-ended。
- **注意(诚实)**:我无法验证 `/opt/arm-gnu-toolchain-15.3.rel1-...-aarch64-none-linux-gnu` 自带的 ld 版本是否有 veneer 修复(沙箱里跑不了它的 ld);buildroot 内部 binutils 是 `arc-2024.12-release`(较新,可能有),但项目用**外部**工具链,所以 buildroot 的 binutils 版本不相关。这条仍是"未验证",不是"已解决"。
- **建议修正**:风险表该行 mitigation 增加"先查外部工具链 binutils 的 aarch64 long-branch veneer 支持 / 试 OE binutils patch / 评估 lld";把"不可估"改为"有已知缓解路径但需验证工具链 binutils"。

### MAJOR 3 — "RFC recipe 90% 完成 / 几乎可直接落地"被夸大

- **证据**:6 份 report 自己就列了作者 inline 标注的 **5 处未完成**:system ICU("DEBUG THIS",被注释→回退 bundled ICU,又把 ICU 的 gcc15 编译风险拉回来)、system ffmpeg("I have to modify system ffmpeg to make this work")、host-python-html5lib("I forgot to send the patches")、libnss select 漏写、sysroot patch 作者自己说想换 `-DCMAKE_SYSROOT=`。更硬的事实:**13 个月零回复、零成功构建报告**——"纸面 90%"≠"编得通"。另外 RFC 的 `qt6webengine.hash` 只有 **15 行**(顶层 LICENSES/*),对照 qt5webengine-chromium.hash **1256 行**——这是 license 合规缺口,不是"完整 recipe"。
- **影响**:Step 2 把这 5 项轻描淡写成"几十行增量"。其中 system ffmpeg 改造 + ICU 回退后的 gcc15 编译,都不是几十行。
- **建议修正**:把 RFC 定位从"现成骨架(90%)"下调为"结构完整但关键开关未闭合的草稿,system ICU/ffmpeg/sysroot 三处需实写";工作量表"buildroot 包封装 1-3 人日"应只覆盖"原样落地+小包",不含把 ICU/ffmpeg 真正打通。

### MAJOR 4(对替代方案不公)— cog 已在 buildroot 树内,synthesis 却说它在 OE、要"参考移植"

- **证据**:`third_party/buildroot/package/cog/cog.mk` → `COG_VERSION = 0.18.5`、`COG_DEPENDENCIES = dbus wpewebkit wpebackend-fdo wayland weston`。Config.in 也在。即 **wpewebkit + cog 是完全树内、零 recipe 编写的 kiosk 栈**。synthesis 原文:"配套的 cog 启动器(kiosk 单窗口)在 OpenEmbedded 有现成 recipe(layers.openembedded.org/layerindex/recipe/164324)可参考移植"——这是事实错误。
- **影响**:这恰恰**加强**了 wpewebkit 替代方案的成熟度。synthesis 的决策建议虽然也推荐了 wpewebkit,但把它呈现得比实际更费事,属于对替代方案不公(prompt 第 5 点)。
- **建议修正**:决策建议里 wpewebkit 一行改为"wpewebkit 2.50.5 + cog 0.18.5 **均已在 buildroot 树内**,defconfig 勾选即可(待 Phase 2 Wayland/GLES/EGL)"。

### MAJOR 5 — 工作量低估两处:GN 工具链翻译 + "临时换 gcc14 工具链"被当成廉价操作

- **证据(GN 翻译)**:meta-qt6 `write_toolchain_file()`(gn-utils.inc)是 bitbake Python,读 ~15 个 bitbake 变量(${CC}/${CXX}/${AR}/${CFLAGS}/${LDFLAGS}/--sysroot/${TARGET_ARCH}...)生成两段 `gcc_toolchain()` 的 BUILD.gn。researcher #2 自己定性"核心技术风险点"。一次 ABI/march/sysroot 透传错误只在**链接期**暴露,而一次 aarch64 全量 build 是 2-4 小时。"3-6 人日 + 1-2 轮 build"按 1-2 次迭代算,现实首移植常烧 3-5 轮——容易 2x。
- **证据(换工具链)**:Step 5 Phase A 说"用一个降级到 gcc 14 或更早的临时外部工具链验证"。但项目锁定外部 Arm GNU 15.3.Rel1;另起一套 gcc14 外部工具链=重新下载/配置 buildroot `BR2_TOOLCHAIN_EXTERNAL`/重建 qt6base + 全部依赖。这不是"廉价 side-task",本身是半天到一天的事,且会掩盖"真实工具链到底行不行"——Phase A 用 gcc14 跑通后,对 gcc15 仍一无所知。
- **建议修正**:工作量表"chromium 交叉编译调通"注明"GN 翻译易多次迭代";Phase A 的 gcc14 降级单独列为"额外 toolchain 搭建成本 ~0.5-1 人日,且不推进 Phase B 认知"。

### MAJOR 6 — LGPL/license-hash 维护成本被当成一次性子弹,实为永久税(且配方是孤儿)

- **证据**:qt5webengine-chromium.hash = **1256 行**、chromium-latest.inc = **1257 行**,每次 chromium bump 整体重生成(qt5 树顶部还专门留了 `find ... -iname 'license*' | sort | sed` 重生成命令)。RFC 的 hash 仅 15 行——合规级分发不够。而上游 RFC **13 个月无人 review**,意味着这税永远自己交。
- **影响**:synthesis 风险表把"LGPL 分发可行但有义务"放在 research 里、风险表只一行"维护成本长期化",没给量级,也没强调这是**每次 Qt 升级都重来**(prompt 第 4 点:维护成本)。
- **建议修正**:风险表新增"license hash 重生成(~1200 行级,每次 chromium bump)+ 上游孤儿状态=永久自维护"一行,severity 中。

### MINOR 7 — Chromium 版本(130 vs 132)在 6 份 report 内部就不一致,synthesis 默认取 130 未核实

- **证据**:researcher #1/#3/#4/#5 说 Qt 6.9.1→Chromium **130.0.6723.192**;researcher #6 说 Qt 6.9→Chromium **132**。synthesis 静默取 130 并据此给"锁 meta-qt6 6.9 分支 = chromium 130"的 pin 建议。wiki.qt.io 直取被本环境拦截,我无法 100% 裁决。
- **影响**:若实际是 132,meta-qt6 分支/SRCREV pin 建议要偏移。低影响于 verdict,但这是 load-bearing 事实未核实。
- **建议修正**:落地前 `curl` 一下 qtwebengine-6.9.1 tarball 里的 `src/3rdparty/chromium/chrome/VERSION` 确认,别只信 report。

### MINOR 8 — Node.js≥20 已确认(22.22.0),synthesis 的"要确认"可收口

- **证据**:`package/nodejs/nodejs.mk` → `NODEJS_COMMON_VERSION = 22.22.0`。synthesis hedge"但要确认 host-nodejs 当前版本≥20"——现在确认 ≥20。
- **建议**:改成已确认,无需动作。

### MINOR 9 — QT6_GL_SUPPORTS symbol 漂移担忧可解除

- **证据**:`package/qt6/Config.in:15` 确有 `config BR2_PACKAGE_QT6_GL_SUPPORTS`。researcher #5 担心的"symbol 在 2026.08 可能漂移"——至少这个关键 symbol 还在。
- **建议**:Step 1 该顾虑可下调。

## 总体判断

**Verdict 站得住,且方向正确。** 在用户最担心的"gcc 15.3 + 老 chromium 能不能编"这一**核心**问题上,synthesis **不是过于乐观,反而略偏悲观**:它把一个"曾被修复、有 binutils veneer/lld/-mcmodel 等多条缓解路径"的链接问题,定性成"至今未解/可能 block"。真正的乐观不在 gcc15,而在别处:

1. **把未经验证的 RFC 当 90% 现成**(实际 5 处未闭合 + 无人构建成功 + license hash 缺口);
2. **完全漏掉 host-python3 = 3.14.6 这个无缓解的早期阻塞**(全员漏报,这是本次复核最重的发现);
3. **低估 GN 工具链翻译迭代次数 + 把"临时换 gcc14 工具链"当廉价操作**;
4. **对 wpewebkit 替代方案有事实性错误**(cog 已在树内),反而压低了最强替代的成熟度;
5. **LGPL/license-hash 永久维护税**没给量级,且孤儿配方的长期成本被淡化。

**给用户的净修正**:verdict 维持"go-with-risk",但风险表要重排——把 **host-python3 3.14** 提到与 gcc15 同级(它更早崩、无现成 patch);把 R_AARCH64_CALL26 的 mitigation 扩到"先查外部工具链 binutils veneer / 试 OE patch / 评估 lld"并从"不可估"降为"有路径待验证";决策建议里 wpewebkit+cog 改为"全树内、零 recipe";并在工作量里显式加上"GN 翻译多轮迭代"和"license hash 永久维护"两项。

**一句话**:synthesis 的结论(go)对,但它的风险图景画反了——把一个可缓解的晚期链接器风险当成头号怪兽,却没看见门口(host-python3 3.14)那个真会第一时间咬人的。

来源(本次独立取证用到的):
- 本地:`third_party/buildroot/package/python3/python3.mk`(3.14.6)、`package/nodejs/nodejs.mk`(22.22.0)、`package/qt6/qt6.mk`(6.9.1)、`package/qt6/Config.in:15`(QT6_GL_SUPPORTS 在)、`package/qt5/qt5webengine-chromium/0009-...patch`(gcc15 cstdint,Arnout 2025-05-18)、`package/qt5/qt5webengine-chromium/qt5webengine-chromium.hash`(1256 行)、`package/cog/cog.mk`(0.18.5 在树内)、`package/wpewebkit/`(2.50.5)、`board/rk3568-atk/buildroot-external/configs/rk3568_atk_defconfig`(无 GPU)、`/opt/arm-gnu-toolchain-15.3.rel1-...`
- web:openSUSE Bug 1251922 双 thread(RESOLVED|REOPENED + LTO 不够回归)、OE-Core binutils chromium/ffmpeg aarch64 补丁、binutils ld/18668(veneer 根因)、GCC bug 94236(-mcmodel=large caveat)、maskray AArch64 linker notes