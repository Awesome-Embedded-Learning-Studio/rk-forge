"""forge.fetch — generic source-fetching framework.

The three legacy fetch scripts (``fetch-deps.sh`` + the two WiFi driver drops)
share one shape: resolve a source (``<url> <ref>``) → ``git clone`` at that ref
(retried, shallow) → idempotency + a per-target post hook. This package factors
that shape into reusable primitives so each fetcher is a thin composition:

* :func:`read_source` — resolve ``<url> <ref>`` for ``name``: a board's own
  ``sources:`` (board.yaml) overrides the shared pool (``forge.yaml sources:``).
* :func:`clone_at_ref` — the source-tree clone: shallow ``--branch <ref>``
  (retried), falling back to a full clone + checkout when ``ref`` isn't a named
  ref (a bare SHA). Huge repos over flaky networks die mid-transfer; the retry +
  fallback are the rk-native fix.
* :func:`clone_shallow_sha` — the driver-drop clone: shallow ``--branch``, return
  the cloned HEAD sha (for the ``.forge-fetched`` marker).

§5.1: source refs live in YAML (``forge.yaml sources:`` shared pool +
``board.yaml sources:`` per-board), not ``pins/`` files. ``read_source`` resolves
board.sources[name] → project.sources[name].
"""
from __future__ import annotations

import time
from pathlib import Path

from forge.core.log import Log
from forge.core.proc import Proc


def read_source(board_sources: dict, project_sources: dict, name: str) -> tuple[str, str] | None:
    """Resolve ``<url> <ref>`` for ``name``: board sources override shared pool.

    Checks ``board_sources[name]`` first (per-board, board.yaml), then
    ``project_sources[name]`` (shared, forge.yaml). Each entry is
    ``{url: ..., ref: ...}``. Returns ``None`` when neither has it (caller
    decides whether that's skippable — e.g. openwrt absent on non-aes boards).
    """
    src = board_sources.get(name) or project_sources.get(name)
    if not src:
        return None
    return src["url"], src["ref"]


def _clone_retry(proc: Proc, argv: list[str], log: Log, *, tries: int = 3) -> bool:
    """Retry a ``git clone`` across transient network failures (linear backoff).

    Huge repos over flaky networks die mid-transfer (``curl 56 GnuTLS recv
    error`` / ``fetch-pack: unexpected disconnect``). Returns True on success.
    """
    for i in range(1, tries + 1):
        if proc.run(argv, check=False, quiet=True).returncode == 0:
            return True
        if i < tries:
            log.warn(f"git clone failed (attempt {i}/{tries}); retrying in {i * 3}s…")
            time.sleep(i * 3)
    return False


def clone_at_ref(proc: Proc, url: str, ref: str, target: Path,
                 log: Log) -> None:
    """Clone ``url`` at named ref/tag ``ref`` → ``target`` (shallow, retried).

    Falls back to a full clone + ``checkout <ref>`` when ``ref`` isn't a named
    ref (a bare SHA fails ``--branch``). No history needed — apply-series
    ``git am``s onto the resolved HEAD, which is present in a shallow clone.
    """
    target = Path(target)
    if _clone_retry(proc, ["git", "clone", "--depth", "1", "--branch", ref,
                           url, str(target)], log):
        return
    log.info(f"'{ref}' not a named ref (or shallow clone failed) — "
             "full clone + checkout (retried)")
    if not _clone_retry(proc, ["git", "clone", url, str(target)], log):
        log.die(f"git clone failed after retries ({url})")
    if proc.run(["git", "-C", str(target), "checkout", ref],
                check=False, quiet=True).returncode != 0:
        log.die(f"checkout {ref} failed (pin wrong?)")


def clone_shallow_sha(proc: Proc, url: str, ref: str, target: Path,
                      log: Log) -> str:
    """Shallow-clone ``url`` @ named ref ``ref`` → ``target``; return HEAD sha.

    Driver drops are working source only (history irrelevant); a one-shot
    shallow clone is enough. The returned sha is recorded in the drop's
    ``.forge-fetched`` marker.
    """
    target = Path(target)
    proc.run(["git", "clone", "-q", "--branch", ref, "--depth", "1", url, str(target)])
    cp = proc.run(["git", "-C", str(target), "rev-parse", "HEAD"], capture=True, quiet=True)
    return cp.stdout.strip()
