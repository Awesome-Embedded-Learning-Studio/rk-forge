"""UbuntuRootfsBuilder — Ubuntu rootfs tarball for the ubuntu profile (rk3588).

Replaces ``scripts/build-ubuntu-rootfs.sh``. Strategy (ubuntu-base + apt over
debootstrap):

1. fetch ``ubuntu-base-<ver>-base-arm64.tar.gz`` from cdimage.ubuntu.com (cached)
2. extract to a work dir (as root)
3. chroot in via binfmt_misc qemu + apt install the package list
   (``<bringup>/ubuntu/packages.list``)
4. post-config: fstab, hostname, login account, serial console, autologin
5. tar up → ``<out>/ubuntu-rootfs.tar`` + ``.ubuntu-rootfs-built`` marker

**Needs root (``sudo forge build ubuntu-rootfs``).** dpkg's security check
requires a root-OWNED db dir, and no unprivileged tool satisfies that AND /dev
AND arm64 emulation together: proot fakes only the process uid (not file
ownership) → dpkg refuses; unshare can't create /dev; fakeroot doesn't compose
with qemu. So the chroot runs as REAL root (the documented exception — sudo-free
by design everywhere else). arm64 binaries run via the registered binfmt_misc
qemu-aarch64 handler; proot is NOT used (its path-resolver asserts on some
postinst symlinks).

Two qemu-emulation speedups applied: ``trusted=yes`` in sources.list (keyboxd's
gpg IPC misbehaves under qemu → signature check fails) + preconfigure disabled
(removing ``70debconf`` skips the apt-extracttemplates grind — tens of minutes
of running every debconf config script under emulation, for zero effect under
``DEBIAN_FRONTEND=noninteractive``).

Three locked architecture decisions applied (NOT a pure 1:1 translation):

* **§5.2 — credentials**: the login account comes from ``forge.yaml``'s
  ``ubuntu.account`` (generic teaching default ``rk-forge``/``rk-forge``), NOT a
  personal credential baked into the script. The password is hashed with
  ``openssl passwd -6`` and inserted via ``chpasswd -e`` — the plaintext lives
  only in YAML, the image carries just the hash.
* **§5.1 — hostname**: ``board.id`` (overridable via ``board.yaml
  ubuntu.hostname`` when that field lands), not a hardcode.

Needs ``qemu-user-static`` (binfmt registered) + network (cdimage +
ports.ubuntu.com). Run: ``sudo python3 src/forge/cli.py build --board <id> ubuntu-rootfs``.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from forge.config.board import Board
from forge.config.project import Project
from forge.core.log import Log
from forge.core.proc import Proc

_DEFAULT_GROUPS = ["adm", "sudo", "audio", "video", "render", "input", "plugdev", "netdev"]


class UbuntuRootfsBuilder:
    """Builds the Ubuntu aarch64 rootfs tarball (ubuntu profile). Needs root."""

    def __init__(self, board: Board, project: Project,
                 proc: Proc | None = None, log: Log | None = None):
        self.board = board
        self.project = project
        self.log = log or Log()
        self.proc = proc or Proc(log=self.log)
        self.bringup = project.root / board.bringup_dir
        self.pkg_list = self.bringup / "ubuntu" / "packages.list"

    def build(self, *, out_dir: Path, version: str = "26.04", clean: bool = False) -> None:
        out_dir = Path(out_dir)
        rootfs_tar = out_dir / "ubuntu-rootfs.tar"
        marker = out_dir / ".ubuntu-rootfs-built"
        # Already built (e.g. by a prior `sudo forge build ubuntu-rootfs`) + not
        # --clean → skip the root build entirely. ubuntu-rootfs is the only sudo
        # island (dpkg needs real root); this lets `forge all --rootfs ubuntu` run
        # UNPRIVILEGED for everything else (linux/uboot/pack/assemble) once the
        # tar exists.
        if not clean and rootfs_tar.is_file() and marker.is_file():
            self.log.info(f"ubuntu-rootfs already built → {rootfs_tar} (skip; --clean to rebuild)")
            return

        # Needs root (only reached when a build is actually required): dpkg's
        # security check requires a root-OWNED db dir; no unprivileged tool
        # satisfies that + /dev + arm64 emulation together.
        if os.geteuid() != 0:
            self.log.die(
                "ubuntu-rootfs build needs root (dpkg requires a root-owned db dir; "
                "no unprivileged chroot tool satisfies that + /dev + qemu together). "
                f"Re-run:\n  sudo python3 src/forge/cli.py build --board {self.board.id} ubuntu-rootfs"
            )
        if not shutil.which("qemu-aarch64-static"):
            self.log.die("missing host tool: qemu-aarch64-static (apt: qemu-user-static)")
        if not self.pkg_list.is_file():
            self.log.die(f"missing package list: {self.pkg_list}")

        dl_dir = out_dir / "dl"
        work_dir = out_dir / "ubuntu-rootfs.work"
        rootfs_tar = out_dir / "ubuntu-rootfs.tar"
        base_url = f"https://cdimage.ubuntu.com/ubuntu-base/releases/{version}/release"
        base_tgz = f"ubuntu-base-{version}-base-arm64.tar.gz"
        out_dir.mkdir(parents=True, exist_ok=True)

        # 1. clean. Also re-extract when running as root over a non-root-owned
        #    work dir (e.g. left by an earlier unprivileged attempt) — dpkg needs
        #    a root-OWNED db dir.
        if clean or (work_dir.is_dir() and work_dir.stat().st_uid != 0):
            if work_dir.is_dir():
                shutil.rmtree(work_dir)

        if work_dir.is_dir():
            self.log.info(f"reusing existing work dir ({work_dir}); use --clean to start fresh")
        else:
            dl_dir.mkdir(parents=True, exist_ok=True)
            if not (dl_dir / base_tgz).is_file():
                self.log.info(f"downloading {base_tgz} (~30MB)…")
                self.proc.run(["curl", "-fL", "-o", str(dl_dir / f"{base_tgz}.partial"),
                               f"{base_url}/{base_tgz}"])
                (dl_dir / f"{base_tgz}.partial").rename(dl_dir / base_tgz)
            self.log.ok(f"ubuntu-base cached: {dl_dir / base_tgz}")
            work_dir.mkdir(parents=True)
            self.log.info(f"extracting ubuntu-base → {work_dir}")
            self.proc.run(["tar", "xf", str(dl_dir / base_tgz), "-C", str(work_dir)])

        self._chroot_apt(work_dir)
        self._post_config(work_dir)

        # 2. tar up. Running as root, so --owner=0 --group=0 normalizes ownership
        #    (matches the bash predecessor; no fakeroot needed under root).
        self.log.info("packing ubuntu-rootfs.tar…")
        self.proc.run(["tar", "-C", str(work_dir), "--owner=0", "--group=0",
                       "-cf", str(rootfs_tar), "."])
        (out_dir / ".ubuntu-rootfs-built").touch()
        self.log.ok(f"Ubuntu rootfs → {rootfs_tar} ({rootfs_tar.stat().st_size} B)")
        self.log.info("next: forge pack (stage-rootfs → pack-emmc) assembles the ext4")

    # ── chroot + apt install (real root chroot; binfmt_misc runs arm64 via qemu) ─
    def _chroot_apt(self, work_dir: Path) -> None:
        # Rewrite sources.list to the arm64 ports archive (direct file write).
        codename = self._read_codename(work_dir)
        self.log.info(f"ubuntu codename: {codename}")
        (work_dir / "etc/apt/sources.list").unlink(missing_ok=True)
        (work_dir / "etc/apt/sources.list.d/ubuntu.sources").unlink(missing_ok=True)
        (work_dir / "etc/apt/sources.list").write_text(_sources_list(codename))
        # Disable preconfigure: under qemu, apt-extracttemplates running every
        # debconf config script upfront is a multi-tens-of-minutes grind with zero
        # effect under DEBIAN_FRONTEND=noninteractive. Removing 70debconf lets
        # packages configure during unpack instead.
        (work_dir / "etc/apt/apt.conf.d/70debconf").unlink(missing_ok=True)

        # Copy the qemu static into the chroot (binfmt looks it up by absolute
        # path inside the chroot's namespace). Bind-mount /proc /sys /dev +
        # resolv.conf for apt network.
        shutil.copy(shutil.which("qemu-aarch64-static"), work_dir / "usr" / "bin")
        self._bind_mount("/proc", work_dir / "proc")
        self._bind_mount("/sys", work_dir / "sys")
        self._bind_mount("/dev", work_dir / "dev")
        shutil.copy("/etc/resolv.conf", work_dir / "etc" / "resolv.conf")

        apt_env = {"DEBIAN_FRONTEND": "noninteractive", "DEBCONF_NONINTERACTIVE_SEEN": "true"}
        try:
            self.log.info("apt update + install packages (qemu chroot)…")
            self.proc.run(["chroot", str(work_dir), "/usr/bin/apt-get", "update"],
                          env_extra=apt_env)
            pkgs = self._package_args()
            self.proc.run(["chroot", str(work_dir), "/usr/bin/apt-get", "install", "-y",
                           "--no-install-recommends", *pkgs], env_extra=apt_env)
            self.proc.run(["chroot", str(work_dir), "/usr/bin/apt-get", "clean"],
                          env_extra=apt_env)
        finally:
            self._cleanup_mounts(work_dir)

    def _post_config(self, work_dir: Path) -> None:
        apt_env = {"DEBIAN_FRONTEND": "noninteractive"}
        # fstab: root on the 3rd partition of the eMMC device.
        (work_dir / "etc/fstab").write_text(_FSTAB)
        # §5.1: hostname = board.id.
        (work_dir / "etc/hostname").write_text(f"{self.board.id}\n")
        # root login with no password (MVP — set a real password before shipping).
        self.proc.run(["chroot", str(work_dir), "/usr/bin/passwd", "-d", "root"],
                      env_extra=apt_env, check=False, quiet=True)

        # §5.2: login account from forge.yaml ubuntu.account (generic default),
        # password hashed via openssl passwd -6 → chpasswd -e (plaintext stays in
        # YAML; only the hash enters the image).
        self._create_account(work_dir)

        # rk3588 console + lockup diagnostics (board-specific). §5.3: was
        # stage-rootfs's rk3588 provisioning — moved here so build owns ALL ubuntu
        # customization and `forge stage` is pure materialization.
        if self.board.id == "rk3588-topeet":
            self._rk3588_hardening(work_dir)

        # remove the qemu static from the final rootfs (not needed on real arm64).
        (work_dir / "usr/bin/qemu-aarch64-static").unlink(missing_ok=True)

    def _rk3588_hardening(self, work_dir: Path) -> None:
        wants = work_dir / "etc/systemd/system/getty.target.wants"
        wants.mkdir(parents=True, exist_ok=True)
        # ttyFIQ0 is the FIQ-backed console; remove the conflicting ttyS2 getty so
        # no ttyS2 getty can reopen the same UART behind the FIQ debugger.
        (wants / "serial-getty@ttyS2.service").unlink(missing_ok=True)
        (wants / "serial-getty@ttyFIQ0.service").symlink_to(
            "/lib/systemd/system/serial-getty@.service")
        # ttyFIQ0 can't diagnose a global IRQ/hard lockup. Keep the DesignWare
        # watchdog alive through systemd + make every detector panic.
        sysd = work_dir / "etc/systemd/system.conf.d"
        sysd.mkdir(parents=True, exist_ok=True)
        (sysd / "10-rk3588-lockup-diagnostics.conf").write_text(
            "[Manager]\nRuntimeWatchdogSec=30s\n")
        sysctl = work_dir / "etc/sysctl.d"
        sysctl.mkdir(parents=True, exist_ok=True)
        (sysctl / "90-rk3588-lockup-diagnostics.conf").write_text(_RK3588_SYSCTL)

    def _create_account(self, work_dir: Path) -> None:
        acct = self.project.ubuntu_account
        username = acct.get("username", "rk-forge")
        password = acct.get("password", "rk-forge")
        uid = acct.get("uid", 1000)
        gecos = acct.get("gecos", "rk-forge dev")
        groups = acct.get("groups") or _DEFAULT_GROUPS
        autologin = acct.get("autologin", True)

        id_cp = self.proc.run(["chroot", str(work_dir), "/usr/bin/id", "-u", username],
                              check=False, capture=True, quiet=True)
        if id_cp.returncode != 0:
            self.proc.run(["chroot", str(work_dir), "/usr/sbin/useradd", "-m", "-U",
                           "-u", str(uid), "-s", "/bin/bash", "-c", gecos,
                           "-G", ",".join(groups), username])
        # Hash the plaintext password on the HOST (openssl), then insert via
        # chpasswd -e inside the chroot — plaintext stays in YAML, only the hash
        # enters the image.
        hash_cp = self.proc.run(["openssl", "passwd", "-6", password],
                                capture=True, quiet=True)
        pw_hash = hash_cp.stdout.strip()
        import subprocess
        subprocess.run(["chroot", str(work_dir), "/usr/sbin/chpasswd", "-e"],
                       input=f"{username}:{pw_hash}\n", text=True,
                       env=self.proc.env_for(), check=True)

        if autologin:
            (work_dir / "var/lib/AccountsService/users").mkdir(parents=True, exist_ok=True)
            (work_dir / "etc/gdm3").mkdir(parents=True, exist_ok=True)
            (work_dir / "var/lib/AccountsService/users" / username).write_text(
                "[User]\nSystemAccount=false\n")
            (work_dir / "var/lib/AccountsService/users" / username).chmod(0o600)
            (work_dir / "etc/gdm3/custom.conf").write_text(
                "[daemon]\nAutomaticLoginEnable = true\n"
                f"AutomaticLogin = {username}\n\n[security]\n\n[debug]\n")

    # ── helpers ──────────────────────────────────────────────────────────────
    def _bind_mount(self, src: str, dst: Path) -> None:
        self.proc.run(["mount", "--bind", src, str(dst)])

    def _cleanup_mounts(self, work_dir: Path) -> None:
        for sub in ("proc", "sys", "dev"):
            self.proc.run(["umount", str(work_dir / sub)], check=False, quiet=True)

    def _read_codename(self, work_dir: Path) -> str:
        os_release = (work_dir / "etc/os-release").read_text(errors="replace")
        for line in os_release.splitlines():
            if line.startswith("VERSION_CODENAME="):
                return line.split("=", 1)[1].strip().strip('"')
        return "26.04"

    def _package_args(self) -> list[str]:
        pkgs: list[str] = []
        for line in self.pkg_list.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if line and line[0].isalnum():
                pkgs.append(line)
        return pkgs


def _sources_list(codename: str) -> str:
    # trusted=yes: under qemu the modern keyboxd (gpg key daemon) IPC misbehaves
    # → signature verification fails even for valid keys. The repos are trusted
    # mirrors (tuna + ports.ubuntu.com), so skip GPG at build time.
    return f"""\
deb [arch=arm64 trusted=yes] http://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports {codename} main restricted universe multiverse
deb [arch=arm64 trusted=yes] http://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports {codename}-updates main restricted universe multiverse
deb [arch=arm64 trusted=yes] http://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports {codename}-security main restricted universe multiverse
# 官方 ports 源兜底（万一镜像缺包）
deb [arch=arm64 trusted=yes] http://ports.ubuntu.com/ubuntu-ports {codename} main restricted universe multiverse
deb [arch=arm64 trusted=yes] http://ports.ubuntu.com/ubuntu-ports {codename}-updates main restricted universe multiverse
deb [arch=arm64 trusted=yes] http://ports.ubuntu.com/ubuntu-ports {codename}-security main restricted universe multiverse
"""


_FSTAB = """\
/dev/mmcblk1p3  /        ext4   defaults,noatime              0 1
proc            /proc    proc   defaults                      0 0
tmpfs           /tmp     tmpfs  defaults,nosuid,nodev         0 0
tmpfs           /var/log tmpfs  defaults,nosuid,nodev         0 0
"""

# rk3588 lockup diagnostics: every detector panics (→ watchdog warm reset into
# the ramoops window) instead of printing into an unreachable FIQ console.
_RK3588_SYSCTL = """\
kernel.panic = 10
kernel.panic_on_oops = 1
kernel.softlockup_panic = 1
kernel.hardlockup_panic = 1
kernel.hung_task_panic = 1
kernel.hung_task_timeout_secs = 60
kernel.panic_on_rcu_stall = 1
kernel.watchdog_thresh = 10
"""
