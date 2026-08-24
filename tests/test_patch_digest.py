#!/usr/bin/env python3
"""PatchApplier.series_digest — the apply-skip fingerprint (2026-08-15 miss).

A HEAD-based "already patched" guard silently skipped freshly added patches:
the series grew 0011→0017 while the tree's HEAD never moved, so forge skipped
apply and nearly shipped an image without 0013-0017.  The digest must therefore
key on CONTENT — pinned base + series file + every listed patch, in order —
and tolerate (but flag, as MISSING) a listed-but-absent patch file.

Run directly:  python3 tests/test_patch_digest.py
With pytest:   pytest tests/test_patch_digest.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from forge.core.patch import PatchApplier  # noqa: E402  (sys.path tweak must precede)

SERIES = "0001-a.patch\n0002-b.patch\n"


def _mk_series(root: Path) -> Path:
    d = root / "patches"
    d.mkdir(parents=True, exist_ok=True)
    (d / "0001-a.patch").write_text("A body\n")
    (d / "0002-b.patch").write_text("B body\n")
    (d / "series").write_text(SERIES)
    return d / "series"


def test_series_digest_keys_on_content() -> None:
    with TemporaryDirectory() as t1, TemporaryDirectory() as t2:
        s1, s2 = _mk_series(Path(t1)), _mk_series(Path(t2))

        d1 = PatchApplier.series_digest(s1, "deadbeef")
        # same content at a different path → same digest (path-independent)
        assert d1 == PatchApplier.series_digest(s2, "deadbeef")
        # base pin change → digest change (re-pin must force a replay)
        assert d1 != PatchApplier.series_digest(s1, "cafef00d")
        # patch content change → digest change
        (s1.parent / "0001-a.patch").write_text("A body EDITED\n")
        assert d1 != PatchApplier.series_digest(s1, "deadbeef")
        # patch ADDED to the series → digest change (the 2026-08-15 miss)
        (s1.parent / "0001-a.patch").write_text("A body\n")
        (s1.parent / "0003-c.patch").write_text("C body\n")
        (s1).write_text(SERIES + "0003-c.patch\n")
        assert d1 != PatchApplier.series_digest(s1, "deadbeef")
        # series reorder → digest change (apply order is semantic)
        (s1).write_text("0002-b.patch\n0001-a.patch\n")
        assert d1 != PatchApplier.series_digest(s1, "deadbeef")
        # listed-but-missing patch must hash (as MISSING), not crash — the
        # applier then fails loudly with its normal rollback
        (s1).write_text("0001-a.patch\nnope.patch\n")
        PatchApplier.series_digest(s1, "deadbeef")


if __name__ == "__main__":
    test_series_digest_keys_on_content()
    print("test_patch_digest: OK")
