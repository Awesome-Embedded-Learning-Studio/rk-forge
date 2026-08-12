"""Proc — the SINGLE subprocess entry for the whole forge package.

Core invariant (the user's "no environment-variable leakage" rule): the child
env is ALWAYS an explicit dict — a curated host allow-list plus Board/Project-
derived extras. It is NEVER ``os.environ`` wholesale, so a build stage cannot
inherit or leak vars (the bash ``source``-leaked ``SPL_SOURCE``/``ROOTFS_MIB``
class of bug is structurally impossible). Callers pass what the tool needs;
nothing more.

``host_env`` defaults to a minimal allow-list (PATH/HOME/…) drawn from
``os.environ`` once, at construction — subprocess tools still resolve on PATH,
but no project var crosses a stage boundary implicitly.
"""
from __future__ import annotations

import os
import shlex
import subprocess
from typing import Mapping

from forge.core.log import Log

# Host vars a build tool's subprocesses legitimately need to resolve. Anything
# else (FORGE_*, ARCH, CROSS_COMPILE, board fields, …) must be passed explicitly
# via env_extra — never inherited. LD_PRELOAD / LD_LIBRARY_PATH are host-level
# linking vars (like PATH) and must propagate so tools that ride on them work
# through Proc — notably fakeroot (LD_PRELOAD intercepts chown for the ubuntu
# rootfs staging), which the no-leakage rule must not break.
_HOST_ALLOWLIST = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE",
                   "TZ", "TMPDIR", "LD_PRELOAD", "LD_LIBRARY_PATH", "GIT_CONFIG_PARAMETERS",
                   "GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0")


class Proc:
    """Runs external commands (make/mkfs/dd/git/…) with an explicit argv and env."""

    def __init__(self, log: Log | None = None, host_env: Mapping[str, str] | None = None):
        self.log = log or Log()
        self._host_env = (
            dict(host_env)
            if host_env is not None
            else {k: os.environ[k] for k in _HOST_ALLOWLIST if k in os.environ}
        )

    def env_for(self, env_extra: Mapping[str, str] | None = None) -> dict[str, str]:
        """The child env for ``run``: curated host allow-list + ``env_extra``.

        Exposed so a caller that drives its own subprocess pipeline (e.g. the
        buildmeter progress pipe in :mod:`forge.build.progress`) builds the SAME
        explicit env as :meth:`run` — one construction, no second copy that
        could drift from the no-leakage invariant.
        """
        env = dict(self._host_env)
        if env_extra:
            env.update(env_extra)
        return env

    def run(self, argv: list[str], *, cwd: str | None = None,
            env_extra: Mapping[str, str] | None = None, check: bool = True,
            capture: bool = False, quiet: bool = False) -> subprocess.CompletedProcess:
        """Run ``argv`` (a list, never a shell string).

        env = curated host allow-list + env_extra (Board/Project-derived).
        capture=True returns stdout/stderr on the result instead of streaming.
        """
        env = self.env_for(env_extra)

        if not quiet:
            self.log.debug("$ " + " ".join(shlex.quote(str(a)) for a in argv))

        result = subprocess.run(
            [str(a) for a in argv], cwd=cwd, env=env,
            capture_output=capture, text=True,
        )

        if check and result.returncode != 0:
            self.log.error(f"command failed ({result.returncode}): {' '.join(map(str, argv))}")
            if capture:
                if result.stdout:
                    self.log.error("stdout: " + result.stdout.strip())
                if result.stderr:
                    self.log.error("stderr: " + result.stderr.strip())
            raise SystemExit(result.returncode)

        return result
