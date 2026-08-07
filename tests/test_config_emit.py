#!/usr/bin/env python3
"""Parity test: for each board, config/boards/<id>.yaml (via Board.from_yaml +
Board.to_bash_env) must reproduce every KEY=VALUE the legacy config/boards/<id>.env
exported — nothing missing, nothing mismatched.

Run directly:  python3 tests/test_config_emit.py
With pytest:    pytest tests/test_config_emit.py   (after `pip install -e ".[dev]"`)

PR1 used strict parity (yaml == .env, no extras). PR2 deliberately makes the YAML
a superset (explicit-ization adds SPL_SOURCE on aes/rk3568, ROOTFS_MIB on rk3568,
matching the bash defaults the scripts already applied — so build behaviour is
unchanged). Those are reported as INFO extras, not failures. The regression guard
that matters — a legacy key going MISSING or changing value — stays a hard failure.
The legacy .env files are deleted in F4; until then they are this test's oracle.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from forge.config.board import Board  # noqa: E402  (sys.path tweak must precede)

_BOARDS = ["aes", "rk3568-atk", "rk3588-topeet"]
# A legacy .env assignment: optional `export`, an UPPER_KEY, =, then a value we de-quote.
_ASSIGN = re.compile(r"^\s*(?:export\s+)?([A-Z_][A-Z0-9_]*)=(.*)$")


class BoardEnvParity:
    """Compare a board's YAML-emitted env against its legacy .env."""

    # extras PR2 intentionally adds (declared in YAML, absent from legacy .env,
    # but identical to the bash default the scripts used) — silenced in reports.
    _EXPECTED_EXTRAS = {
        "aes": {"SPL_SOURCE"},
        "rk3568-atk": {"SPL_SOURCE", "ROOTFS_MIB"},
        "rk3588-topeet": set(),
    }

    def __init__(self, root: Path):
        self.root = root

    # ── parsers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _strip_quotes(value: str) -> str:
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            return value[1:-1]
        return value

    @classmethod
    def _parse_bash_assignments(cls, text: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for line in text.splitlines():
            line = line.split("#", 1)[0]  # values in these files never contain '#'
            m = _ASSIGN.match(line)
            if not m:
                continue
            out[m.group(1)] = cls._strip_quotes(m.group(2))
        return out

    def legacy_env(self, board_id: str) -> dict[str, str]:
        return self._parse_bash_assignments(
            (self.root / "config" / "boards" / f"{board_id}.env").read_text()
        )

    def emitted_env(self, board_id: str) -> dict[str, str]:
        board = Board.from_yaml(board_id, root=self.root)
        return self._parse_bash_assignments(board.to_bash_env())

    # ── check ─────────────────────────────────────────────────────────────────
    def check(self, board_id: str) -> tuple[list[str], list[str]]:
        """Return (problems, unexpected_extras). problems non-empty ⇒ regression."""
        legacy = self.legacy_env(board_id)
        emitted = self.emitted_env(board_id)
        problems: list[str] = []

        for key, value in legacy.items():
            if key not in emitted:
                problems.append(f"  MISSING  {key}  (legacy={value!r})")
            elif emitted[key] != value:
                problems.append(f"  MISMATCH {key}: legacy={value!r}  yaml={emitted[key]!r}")

        expected = self._EXPECTED_EXTRAS.get(board_id, set())
        unexpected_extras = sorted(set(emitted) - set(legacy) - expected)
        info_extras = sorted((set(emitted) - set(legacy)) & expected)
        return problems, unexpected_extras + ([f"(+ expected extras: {info_extras})"] if info_extras else [])

    def run(self, boards: list[str]) -> int:
        total_failures = 0
        for board in boards:
            problems, extras = self.check(board)
            n_legacy = len(self.legacy_env(board))
            if problems:
                total_failures += len(problems)
                print(f"[{board}] FAIL — {len(problems)} regression(s) vs legacy .env ({n_legacy} keys):")
                for p in problems:
                    print(p)
            else:
                print(f"[{board}] OK  ({n_legacy} legacy keys match)")
            if extras:
                print(f"          extras: {extras}")
        print("PARITY FAIL" if total_failures else "PARITY PASS")
        return 1 if total_failures else 0


# ── pytest surface (optional; needs pytest installed) ─────────────────────────
def _assert_board(board_id: str) -> None:
    problems, _ = BoardEnvParity(ROOT).check(board_id)
    assert not problems, f"[{board_id}] parity regressions:\n" + "\n".join(problems)


def test_aes_parity():
    _assert_board("aes")


def test_rk3568_atk_parity():
    _assert_board("rk3568-atk")


def test_rk3588_topeet_parity():
    _assert_board("rk3588-topeet")


if __name__ == "__main__":
    sys.exit(BoardEnvParity(ROOT).run(_BOARDS))
