"""Doctor — standalone environment checker.

Replaces ``scripts/doctor.sh``. Verifies the host build essentials forge actually
uses (``mkimage`` comes from the U-Boot tree, NOT the host; ``qemu-system-arm``
isn't used — both were over-cautious carryovers), the board's cross toolchain
(Arm GNU — NOT apt-installable), and ``pyelftools`` (kernel build helper).

No interactive ``/dev/tty`` apt-install (that was imx-forge env-init.sh's trap —
it made the script un-wrap-able). On missing deps this PRINTS the remediation
``sudo apt install …`` line to stdout (copy-pasteable / CI-capturable) and exits
1; exit 0 when everything is present. Diagnostics → stderr.
"""
from __future__ import annotations

import shutil
import sys

from forge.build import toolchain_resolves
from forge.config.board import Board
from forge.core.log import Log

# host build essentials forge actually uses (mkimage from U-Boot tree; no qemu).
_HOST_CMDS = ["git", "make", "gcc", "bc", "bison", "flex", "dtc",
              "cpio", "mkfs.ubifs", "ubinize", "sgdisk"]
# command → Debian/Ubuntu package (host deps only; cross toolchain is Arm GNU).
_PKG = {
    "dtc": "device-tree-compiler", "mkfs.ubifs": "mtd-utils", "ubinize": "mtd-utils",
    "sgdisk": "gdisk", "bison": "bison", "flex": "flex", "cpio": "cpio",
    "bc": "bc", "git": "git", "make": "make", "gcc": "gcc",
}
# libs the kernel/u-boot builds always want (appended to the apt line).
_APT_LIBS = ["libssl-dev", "libncurses-dev"]


class Doctor:
    """Checks host deps + the board's cross toolchain; prints remediation."""

    def __init__(self, board: Board, log: Log | None = None):
        self.board = board
        self.log = log or Log()

    def run(self) -> int:
        missing: list[str] = []
        self.log.info("== rk-forge doctor ==")

        for c in _HOST_CMDS:
            if shutil.which(c):
                self.log.ok(c)
            else:
                self.log.warn(f"missing: {c}")
                missing.append(c)

        # cross toolchain (Arm GNU — NOT apt; separate remediation).
        gcc = toolchain_resolves(self.board)
        if gcc:
            self.log.ok(f"toolchain: {self.board.toolchain_prefix}gcc")
        else:
            self.log.warn(f"missing cross toolchain: {self.board.toolchain_prefix}gcc (Arm GNU Toolchain — NOT apt)")
            self.log.warn(f"  install Arm GNU 15.x so toolchain.bin_dir ({self.board.toolchain_bin_dir}) exists")
            self.log.warn("  download: https://developer.arm.com/downloads  →  GNU Toolchain")

        # python helper for kernel build scripts.
        try:
            import elftools  # noqa: F401
            self.log.ok("python3-pyelftools")
        except ImportError:
            self.log.warn("missing: python3-pyelftools")
            missing.append("python3-pyelftools")

        # WSL2 advisory (not an error).
        try:
            with open("/proc/version") as f:
                if "microsoft" in f.read().lower():
                    self.log.info("WSL2 detected: USB flashing (rkdeveloptool) needs usbipd-win on Windows; SD-card flashing works directly.")
        except OSError:
            pass

        if not missing and gcc:
            self.log.ok("all dependencies present")
            return 0

        if missing:
            pkgs: list[str] = []
            for m in missing:
                pkg = _PKG.get(m, m)
                if pkg not in pkgs:
                    pkgs.append(pkg)
            for extra in _APT_LIBS:
                if extra not in pkgs:
                    pkgs.append(extra)
            self.log.warn("")  # blank line
            self.log.warn("Fix host deps with:")
            sys.stdout.write(f"sudo apt install {' '.join(pkgs)}\n")   # stdout — copy-pasteable
            sys.stdout.flush()
        if not gcc:
            self.log.warn("")  # blank line
            self.log.warn("(cross toolchain: see the Arm GNU note above, not apt)")
        return 1
