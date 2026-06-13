#!/usr/bin/env bash
# sdk-diff.sh — STUB (Week 7-8). The honesty core of rk-forge.
#
# Compares a vendor BSP (e.g. the 正点原子/ALIENTEK SDK cloned into
# third_party/vendor-sdk/) against our mainline port, per subsystem, and reports:
#   - what the vendor BSP ships
#   - whether mainline has it
#   - the gap, and whether the board can still boot
# Plus a headline "RK-SDK residue" metric: for mainline boot of RK3506, the only
# residue is rkbin (closed DDR blobs) + the board DT (which rk-forge writes).
# This is the proof of the "replace build.sh, not all of RK-SDK" thesis.
#
# Planned: bash `git diff`/tree-walk leaves first; migrate to Python CLI (iter 2).
set -euo pipefail
echo "sdk-diff.sh: STUB (planned Week 7-8). Compare third_party/vendor-sdk/ vs our mainline port." >&2
exit 1
