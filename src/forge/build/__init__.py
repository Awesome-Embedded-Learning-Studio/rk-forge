"""forge.build — build stages as Proc-driven ``make`` wrappers.

Each leaf (kernel / u-boot / rootfs / …) is a class reading ``Board`` +
``Project``; every external command goes through :class:`forge.core.proc.Proc`
with an **explicit** env. The toolchain tuple (``ARCH`` / ``CROSS_COMPILE`` /
``PATH``) is passed explicitly via :func:`make_env` — never inherited — so the
bash ``source``-leak class of bug (a stale ``CROSS_COMPILE`` crossing a stage
boundary) is structurally impossible. Replaces ``scripts/build-*.sh``.

Shared here (used by every build leaf):

* :func:`make_env` — the ``env_extra`` every board ``make`` needs.
* :func:`check_toolchain` — die unless ``${CROSS_COMPILE}gcc`` + ``readelf``
  resolve (was ``lib/toolchain.sh``'s ``check_toolchain``).
"""
from __future__ import annotations

import os
import shutil

from forge.config.board import Board
from forge.core.log import Log


def make_env(board: Board, *, extra: dict | None = None) -> dict:
    """The ``env_extra`` every board ``make`` needs.

    ``ARCH`` + ``CROSS_COMPILE`` (from the board) + ``PATH`` with the board's
    toolchain ``bin_dir`` **prepended** to the host ``PATH``. Proc starts from
    its curated host allow-list (``PATH``/``HOME``/…) and overlays this, so the
    compiler resolves on ``PATH`` without ``os.environ`` ever crossing a stage
    boundary wholesale. Mirrors ``lib/toolchain.sh``
    (``CROSS_COMPILE=$TOOLCHAIN_PREFIX``; ``PATH=$TOOLCHAIN_BIN_DIR:$PATH``).
    """
    parts: list[str] = []
    if board.toolchain_bin_dir:
        parts.append(board.toolchain_bin_dir)
    parts.append(os.environ.get("PATH", ""))
    env: dict[str, str] = {
        "ARCH": board.arch,
        "CROSS_COMPILE": board.toolchain_prefix,
        "PATH": ":".join(p for p in parts if p),
    }
    if extra:
        env.update(extra)
    return env


def toolchain_resolves(board: Board) -> str | None:
    """Return the resolved ``${CROSS_COMPILE}gcc`` path if it + ``readelf`` are
    reachable, else ``None``. The lookup ``PATH`` includes the board's toolchain
    ``bin_dir`` (prepended, as :func:`make_env` does for the build itself).

    Non-fatal predicate — :func:`check_toolchain` dies on a ``None`` here;
    ``forge doctor`` reports it instead.
    """
    paths: list[str] = []
    if board.toolchain_bin_dir:
        paths.append(board.toolchain_bin_dir)
    paths.extend(os.environ.get("PATH", "").split(":"))
    search_path = ":".join(p for p in paths if p)
    gcc = shutil.which(f"{board.toolchain_prefix}gcc", path=search_path)
    readelf = shutil.which(f"{board.toolchain_prefix}readelf", path=search_path)
    return gcc if (gcc and readelf) else None


def check_toolchain(board: Board, log: Log) -> None:
    """Die unless ``${CROSS_COMPILE}gcc`` + ``${CROSS_COMPILE}readelf`` resolve.

    Was ``check_toolchain`` in ``lib/toolchain.sh``.
    """
    if toolchain_resolves(board) is None:
        log.die(
            f"toolchain not on PATH: {board.toolchain_prefix}gcc "
            f"(run: forge doctor --board {board.id})"
        )
