"""buildmeter progress pipe — faithful port of ``lib/progress.sh``'s
``forge_progress_run`` (plus the U-Boot tolerant-build variant).

When interactive, pipes a long ``make`` through ``third_party/buildmeter`` so a
72-minute build shows a live progress bar instead of an endless CC/LD scroll.
Falls through to a plain :meth:`Proc.run` (no pipe) when **any** of these holds
(matching the bash fall-through exactly):

* stdout isn't a TTY (CI, log redirect, stage capture);
* ``FORGE_PROGRESS=0`` is set in the environment;
* the buildmeter entry or ``python3`` is missing.

Pre-scan (``FORGE_PROGRESS_PRESCAN=1``, default): runs ``make -k -n`` once to
count the build units (the bar's denominator), then pipes the real make through
``tee <log>`` and buildmeter. The bar is best-effort and never changes the
build's exit code.

Two call modes (the bash had two helpers — ``forge_progress_run`` and U-Boot's
inline block):

* ``check=True`` (default — kernel / buildroot): the make **streams** to the
  console and a non-zero exit raises ``SystemExit`` (Proc semantics).
* ``check=False`` (U-Boot): binman's combined-image step fails with "Error 103 /
  missing external blobs" even on a good build, so the make is **captured** to
  ``log_file`` (full output for the real-error gate), ``ignore_errors`` lines are
  filtered out of what's shown, and the rc is RETURNED (the caller post-scans
  the log for genuine ``error:`` / ``undefined reference`` and dies there).

Implemented as an explicit ``Popen`` pipeline (``make → tee → buildmeter``),
never ``shell=True`` — the same invariant :class:`Proc` upholds.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from forge.config.project import Project
from forge.core.log import Log
from forge.core.proc import Proc

# buildmeter cli.py's `kind` choices.
_KINDS = ("kernel", "uboot", "buildroot")


def _progress_py(project: Project) -> Path:
    """Path to buildmeter's script-style CLI entry (same one progress.sh used)."""
    return project.root / "third_party" / "buildmeter" / "src" / "buildmeter" / "cli.py"


def bar_enabled(project: Project) -> bool:
    """True iff the live bar should run (interactive + enabled + tooling present)."""
    return (
        os.environ.get("FORGE_PROGRESS", "1") == "1"
        and sys.stdout.isatty()
        and _progress_py(project).is_file()
        and shutil.which("python3") is not None
    )


def run_with_progress(kind: str, argv: list[str], *, project: Project,
                      proc: Proc, log: Log, cwd: str | None = None,
                      env_extra: dict | None = None, check: bool = True,
                      ignore_errors: str = "", log_file: str | Path | None = None) -> int:
    """Run a ``make`` ``argv``; pipe through buildmeter when interactive.

    ``check=True`` (default): streams the make; raises ``SystemExit(rc)`` on
    failure (kernel / buildroot). ``check=False``: captures the make to
    ``log_file`` (full text for a caller-side error gate), filters
    ``ignore_errors`` lines from what's shown, and RETURNS the rc — for U-Boot,
    where binman's "Error 103" is tolerated but real dts/compile/link errors are
    fatal (the caller scans the log).

    ``argv`` is the full make invocation (``["make", "ARCH=…", …]``); ``stdbuf
    -oL`` is prepended when available so make line-buffers through the pipe (a
    responsive bar), matching progress.sh's ``$buf`` prefix. Returns the make rc
    (0 in the ``check=True`` success path that doesn't return early).
    """
    if kind not in _KINDS:
        raise ValueError(f"buildmeter kind must be {list(_KINDS)}, got {kind!r}")

    want_bar = bar_enabled(project)
    logf = Path(log_file) if log_file else Path("/tmp") / f"forge-{kind}-{os.getpid()}.log"

    if not want_bar:
        return _run_plain(argv, proc=proc, log=log, cwd=cwd, env_extra=env_extra,
                          check=check, ignore_errors=ignore_errors, logf=logf)

    progress_py = _progress_py(project)
    env = proc.env_for(env_extra)
    make_argv = (["stdbuf", "-oL"] + argv) if shutil.which("stdbuf") else argv

    # Pre-scan: `{make -k -n || true} | buildmeter --count-only kind` → total.
    # DEFAULT OFF: `make -k -n` can corrupt the kernel tree's auto.conf (make's
    # include-remake rule fires even under -n), causing the subsequent real build
    # to fail. Opt in with FORGE_PROGRESS_PRESCAN=1 (the bar then has a %, else
    # indeterminate). The count + rate + ETA still work without it.
    total = 0
    if os.environ.get("FORGE_PROGRESS_PRESCAN", "0") == "1":
        log.info("counting build units (make -n)…")
        dry = subprocess.run(make_argv + ["-k", "-n"], cwd=cwd, env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        cnt = subprocess.run([sys.executable, str(progress_py), "--count-only", kind],
                             input=dry.stdout, stdout=subprocess.PIPE, text=True)
        try:
            total = int((cnt.stdout or "").strip())
        except ValueError:
            total = 0
        if total <= 0:
            log.info("pre-scan returned 0 — running indeterminate (no % bar)")

    log.info(f"full build log → {logf}")

    # Pipeline: make 2>&1 → tee logf → buildmeter (kind --total N --log logf
    # [--ignore-errors NOISE]). tee owns the log write + forward; buildmeter
    # renders the bar on its stderr (the TTY).
    make_p = subprocess.Popen(make_argv, cwd=cwd, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    tee_p = subprocess.Popen(["tee", str(logf)], stdin=make_p.stdout,
                             stdout=subprocess.PIPE, text=True)
    bm_argv = [sys.executable, str(progress_py), kind, "--log", str(logf)]
    if total > 0:
        bm_argv += ["--total", str(total)]
    if ignore_errors:
        bm_argv += ["--ignore-errors", ignore_errors]
    bm_p = subprocess.Popen(bm_argv, stdin=tee_p.stdout, text=True)
    assert make_p.stdout is not None
    make_p.stdout.close()
    assert tee_p.stdout is not None
    tee_p.stdout.close()

    make_rc = make_p.wait()
    try:
        tee_p.wait()
        bm_p.wait()
    except Exception:
        pass   # buildmeter/tee are best-effort; make's exit is authoritative

    if check and make_rc != 0:
        log.error(f"command failed ({make_rc}): {' '.join(map(str, make_argv))}")
        raise SystemExit(make_rc)
    return make_rc


def _run_plain(argv: list[str], *, proc: Proc, log: Log, cwd: str | None,
               env_extra: dict | None, check: bool, ignore_errors: str,
               logf: Path) -> int:
    """Non-interactive path. check=True → stream + raise (kernel). check=False →
    capture to ``logf``, show non-``ignore_errors`` lines, return rc (U-Boot)."""
    if check:
        proc.run(argv, cwd=cwd, env_extra=env_extra)   # streams; raises on failure
        return 0

    cp = proc.run(argv, cwd=cwd, env_extra=env_extra, check=False, capture=True)
    text = (cp.stdout or "") + (cp.stderr or "")
    logf.write_text(text)
    noise = re.compile(ignore_errors) if ignore_errors else None
    for line in text.splitlines():
        if noise and noise.search(line):
            continue
        sys.stdout.write(line + "\n")
    sys.stdout.flush()
    return cp.returncode
