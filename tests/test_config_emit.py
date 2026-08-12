#!/usr/bin/env python3
"""Board-config load + emit smoke test (post-F4).

F4 deleted the legacy ``config/boards/<id>.env`` files, so the old YAML↔.env
parity test (whose oracle was those .env files) is retired — the migration it
guarded is complete (YAML is now the sole source). This replaces it with a
forward-looking smoke test: every board's ``boards/<id>/board.yaml`` LOADS via
``Board.from_yaml`` (no exception) and ``to_bash_env`` emits the essential keys
(BOARD/SOC/ARCH + the workspace/toolchain dirs that every build reads).

Run directly:  python3 tests/test_config_emit.py
With pytest:   pytest tests/test_config_emit.py   (after `pip install -e ".[dev]"`)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from forge.config.board import Board  # noqa: E402  (sys.path tweak must precede)

_BOARDS = ["aes", "rk3568-atk", "rk3588-topeet"]
# Keys every board's emitted env must contain (the identity + path fields each
# build stage reads). Workspace paths now point under boards/<id>/ (F4).
_ESSENTIAL_KEYS = ("BOARD", "SOC", "ARCH", "BRINGUP_DIR", "BOARD_CFG_DIR",
                   "TOOLCHAIN_PREFIX", "TOOLCHAIN_BIN_DIR")


def _check(board_id: str) -> list[str]:
    """Return a list of problems (empty ⇒ board loads + emits cleanly)."""
    problems: list[str] = []
    try:
        board = Board.from_yaml(board_id, root=ROOT)
    except Exception as e:  # noqa: BLE001 — any load failure is a regression
        return [f"Board.from_yaml raised {type(e).__name__}: {e}"]

    env: dict[str, str] = {}
    for line in board.to_bash_env().splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" in line and not line.startswith("export"):
            # the emitted lines are `export KEY="v"` — strip to KEY
            continue
        if line.startswith("export "):
            kv = line[len("export "):]
            if "=" in kv:
                k, v = kv.split("=", 1)
                env[k] = v.strip().strip('"')
    for key in _ESSENTIAL_KEYS:
        val = env.get(key)
        if not val:
            problems.append(f"  MISSING/EMPTY  {key}")
    # F4: workspace paths must resolve under boards/<id>/ (or be absolute there).
    bringup = env.get("BRINGUP_DIR", "")
    if bringup and board_id not in bringup:
        problems.append(f"  BRINGUP_DIR={bringup!r} doesn't contain board id {board_id!r}")
    return problems


def run(boards: list[str]) -> int:
    failures = 0
    for board in boards:
        problems = _check(board)
        if problems:
            failures += len(problems)
            print(f"[{board}] FAIL:")
            for p in problems:
                print(p)
        else:
            print(f"[{board}] OK  (loads + emits {len(_ESSENTIAL_KEYS)} essential keys)")
    print("FAIL" if failures else "PASS")
    return 1 if failures else 0


# ── pytest surface (optional; needs pytest installed) ─────────────────────────
def test_aes_loads():
    assert not _check("aes")


def test_rk3568_atk_loads():
    assert not _check("rk3568-atk")


def test_rk3588_topeet_loads():
    assert not _check("rk3588-topeet")


if __name__ == "__main__":
    sys.exit(run(_BOARDS))
