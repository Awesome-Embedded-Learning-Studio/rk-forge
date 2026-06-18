# 17 — forge patch 固化 SOP（explore 树 → patches/）

> 代码定型后固化成可复现 patch 的标准流程。80MHz 定型（commit `3afac7bb4` → patch 0003）走的就是这套。

## 0. 前提
- `third_party/explore/{linux,uboot}` 是独立 git 仓库（rk-forge `.gitignore` 行 31，不 track）
- base = mainline tag：linux `v7.1 = 8cd9520d3`、uboot `v2026.07-rc4`
- `patches/<component>/` 是 rk-forge canonical —— `apply-series` 在干净 base 重建出 explore 树

## 1. commit 改动（explore 树，一个逻辑改动一个 commit）
```bash
git -C third_party/explore/linux add <files>
git -C third_party/explore/linux commit -m "<subsystem>: <what> (<why>)"
```
- 英文 message，`area: description` 风格，**不带 Co-Authored**（用户要求，记忆 [[no-coauthored-trailer]]）
- 多行 body 说 why（板验证据 / datasheet / 反例）

## 2. format-patch 生成
```bash
git -C third_party/explore/linux format-patch --signoff \
    --output-directory patches/linux_mainline/ 8cd9520d3..HEAD
```
- 生成 `0001/0002/...`（覆盖同 commit 旧 patch + 新增）
- ⚠ 重生会改前序 patch 的编号（`PATCH 1/2`→`1/3`）+ 加 `Signed-off-by`，`git diff` 看 M 是这些（**非内容**）。别被吓到。

## 3. series 更新（patch-maker 有 bug，手动）
`patch-maker.sh` 的 `../../scripts` 对 `explore/linux` 二级目录算错（找不到脚本）。手动 append：
```bash
printf '\n# <说明>\n%s\n' "$(basename patches/linux_mainline/0003-*.patch)" >> patches/linux_mainline/series
```

## 4. apply-series --check 验证（干净 base 真重建）
```bash
git -C third_party/explore/linux worktree add --detach /tmp/verify 8cd9520d3
( cd /tmp/verify && <repo>/scripts/apply-series.sh --component linux_mainline --check )
git -C third_party/explore/linux worktree remove /tmp/verify --force
```
- 干跑（apply 全 series + revert），验按序 apply；或去 `--check` 真重建后 `diff` 主树确认代码一致
- 这是"patch 端到端正确"的证明（patch → 干净树 → 代码 == explore commit）

## 5. rk-forge commit
```bash
git add patches/linux_mainline/ document/logs/*.txt document/notes/*.md
git commit -m "<area>: <summary>"
```
- patches/ + logs + notes 进 rk-forge；explore 树 commit 留子仓库（rk-forge 靠 patches/ 引用，不 track explore）
- 分支 `bringup/*`（非 main）

## 流程图
```
explore 树改 → commit → format-patch → patches/ + series
                                       ↓
                          apply-series --check 验证 → rk-forge commit
```

## 相关
[18](18-2026-06-18-board-verification-playbook.md)（板上验证）/ 记忆 [[self-run-build-and-copy]]
