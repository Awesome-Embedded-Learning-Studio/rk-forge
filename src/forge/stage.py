"""StageRootfs — materialize the rootfs tree at ``out/rootfs/`` for packing.

Replaces ``scripts/stage-rootfs.sh``. Per architecture §5.3, this is **pure
materialization** — every customization (WiFi .ko, firmware, account, console,
watchdog, …) is baked by the base's NATIVE mechanism during ``forge build``
(buildroot post-build / openwrt package system / ubuntu chroot), so staging
just lays the tree down:

* buildroot — ``tar xf rootfs.tar``
* openwrt   — ``rsync TARGET_DIR/`` (kmod already in lib/modules)
* ubuntu    — ``tar xf ubuntu-rootfs.tar`` under fakeroot (preserves numeric
  root ownership across the stage→pack-emmc chain; the fakeroot state file is
  reloaded by pack-emmc before mke2fs)

The old stage-rootfs's post-extract provisioning (account re-creation, .ko drop,
firmware belt-and-suspenders, rk3588 console/watchdog) is GONE — moved into the
base builds (single-source, no build/stage drift). The fakeroot re-invocation
forks+waits a child (``fakeroot … forge stage``) — NOT ``os.execvpe``: exec
replaced the whole forge process, silently truncating ``forge all`` right after
this stage and never recording the stage-rootfs fingerprint.
"""
from __future__ import annotations

import os
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

from forge.config.board import Board
from forge.config.project import Project
from forge.core.log import Log
from forge.core.proc import Proc


class StageRootfs:
    """Materializes out/rootfs/ from the built rootfs source (profile-driven)."""

    def __init__(self, board: Board, project: Project,
                 proc: Proc | None = None, log: Log | None = None):
        self.board = board
        self.project = project
        self.log = log or Log()
        self.proc = proc or Proc(log=self.log)

    def stage(self, *, out_dir: Path, profile: str = "buildroot") -> None:
        out_dir = Path(out_dir)
        root = out_dir / "rootfs"
        # ubuntu: the rootfs tar stores root ownership; preserving it on extract
        # needs either root or fakeroot. Under root (the ubuntu build already
        # runs under sudo), extract directly. Unprivileged, re-exec under
        # fakeroot (the re-invocation carries RK_FORGE_STAGE_FAKEROOT=1).
        if (profile == "ubuntu" and os.geteuid() != 0
                and os.environ.get("RK_FORGE_STAGE_FAKEROOT") != "1"):
            self._rerun_under_fakeroot(out_dir, profile)
            return   # unreached — execvpe replaces the process

        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)

        if profile == "openwrt":
            self._stage_openwrt(root)
        elif profile == "ubuntu":
            self._stage_ubuntu(root)
        else:
            self._stage_buildroot(root)

        self.log.ok(f"rootfs staged → {root} ({_tree_size(root)})")

    # ── buildroot: extract rootfs.tar (post-build already baked .ko etc.) ──────
    def _stage_buildroot(self, root: Path) -> None:
        rootfs_tar = self.project.buildroot_dir / "output" / "images" / "rootfs.tar"
        if not rootfs_tar.is_file():
            self.log.die(
                f"missing buildroot rootfs.tar (build it first: forge build rootfs): {rootfs_tar}"
            )
        self.log.info(f"extracting buildroot rootfs.tar → {root}")
        self.proc.run(["tar", "xf", str(rootfs_tar), "-C", str(root)])
        self.log.info(f"next: forge pack (pack-ubifs → rootfs.ubi.img)")

    # ── openwrt: rsync TARGET_DIR (kmod packages already in lib/modules/) ─────
    def _stage_openwrt(self, root: Path) -> None:
        target_dir = self._find_openwrt_target_dir()
        if not (target_dir and (target_dir / "bin" / "busybox").is_file()):
            self.log.die(
                f"OpenWrt TARGET_DIR missing/incomplete: {target_dir or '<not found>'} "
                "(run: forge build openwrt)"
            )
        self.log.info(f"rsync OpenWrt TARGET_DIR → {root}")
        self.proc.run(["rsync", "-a", f"{target_dir}/", f"{root}/"])
        self.log.info("next: forge pack (pack-ubifs → rootfs.ubi.img)")

    # ── ubuntu: extract ubuntu-rootfs.tar (build already baked account/etc.) ──
    def _stage_ubuntu(self, root: Path) -> None:
        out_dir = root.parent
        tar = out_dir / "ubuntu-rootfs.tar"
        if not tar.is_file():
            self.log.die(
                f"missing ubuntu rootfs.tar (build it first: forge build ubuntu-rootfs): {tar}"
            )
        self.log.info(f"extracting ubuntu rootfs.tar → {root}")
        # --numeric-owner --same-owner: the tar stores numeric root ownership;
        # under fakeroot this preserves it for pack-emmc's mke2fs.
        self.proc.run(["tar", "--numeric-owner", "--same-owner", "-xf", str(tar),
                       "-C", str(root)])
        self._provision_runtime_config(root)
        self.log.info("next: forge pack (pack-emmc → rootfs.ext4)")

    def _provision_runtime_config(self, root: Path) -> None:
        """Bake boot-time runtime config into the staged tree (NOT the cached tar).

        Injected at stage time on purpose: unprivileged, hash-invalidated by any
        edit to this file, and credentials never enter the rootfs tar / git.
        Everything here is idempotent static-file writing — no chroot needed.

        Source of truth: ``user/`` drop-ins (see user/README.md
        and notes/58) — wifi.yaml (SSID/PSK/iface rename), ssh.yaml (pubkeys →
        /root/.ssh/authorized_keys; root has an empty password so ssh password
        auth refuses), network.yaml (DNS — this rootfs has no systemd-resolved).
        FORGE_WIFI_SSID/FORGE_WIFI_PASS/FORGE_DNS env vars override for one-offs.
        """
        u = self.project.user
        for w in u.perm_warnings:
            self.log.info(f"user-config: {w}")

        # The rootfs tar is built with --owner=0 --group=0 (flat numeric root
        # ownership), so the login account's home would ship root-owned.  Board-
        # caught 2026-08-15: root-owned ~/.config/~/.local made gnome-shell /
        # gvfs / dconf fail en masse and localsearch crash-loop.  Re-establish
        # it here — this runs inside the stage fakeroot session, so the chown
        # lands in the saved ownership metadata and thus in rootfs.ext4.
        acct = dict(self.project.ubuntu_account)
        ua = self.project.user.account
        if ua.username and ua.password:
            acct.update(username=ua.username, password=ua.password)
        username = acct.get("username", "rk-forge")
        uid = acct.get("uid", 1000)
        home = root / "home" / username
        if home.is_dir():
            self.proc.run(["chown", "-R", f"{uid}:{uid}", str(home)])
            self.log.ok(f"home ownership: /home/{username} → {uid}:{uid}")
        else:
            self.log.warn(f"no home to chown at {home} — account created at tar-build only")

        # Dev-board convenience: the login account is in the `sudo` group, but
        # that still prompts — and this rootfs has no usable root password to
        # fall back to. Research/bring-up flows (tracefs mounts, kprobes) run
        # unattended over serial; give the dev account passwordless sudo.
        sudoers = root / "etc" / "sudoers.d"
        sudoers.mkdir(parents=True, exist_ok=True)
        (sudoers / "010-dev-nopasswd").write_text(
            f"{username} ALL=(ALL) NOPASSWD: ALL\n")
        os.chmod(sudoers / "010-dev-nopasswd", 0o440)

        # DNS: chroot-era resolv.conf leftover resolves nothing.
        dns = u.dns or "223.5.5.5"
        (root / "etc").mkdir(exist_ok=True)
        (root / "etc/resolv.conf").write_text(f"nameserver {dns}\n")

        # Dev pubkeys (files + literals, deduped) → zero-touch ssh after reflash.
        keys: list[str] = []
        for kf in u.ssh.pubkey_files:
            p = Path(os.path.expanduser(kf))
            if p.is_file():
                keys.append(p.read_text().strip())
            else:
                self.log.info(f"ssh pubkey file not found (skipped): {p}")
        keys += [k.strip() for k in u.ssh.pubkeys]
        keys = [k for k in dict.fromkeys(k for k in keys if k)]
        if keys:
            ssh_dir = root / "root" / ".ssh"
            ssh_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            (ssh_dir / "authorized_keys").write_text("\n".join(keys) + "\n")
            os.chmod(ssh_dir / "authorized_keys", 0o600)

        # WiFi auto-connect: netplan only renames + DHCP; credentials live solely
        # in the wpa_supplicant conf (PSK computed per WPA spec — no host tools).
        ssid, passphrase, iface = u.wifi.ssid, u.wifi.psk, u.wifi.iface
        if not ssid or not passphrase:
            self.log.info("wifi provisioning skipped (fill user/wifi.yaml "
                          "— see wifi.yaml.example — to enable boot-time auto-connect)")
            return

        # Pure systemd (netplan dropped for wifi): this netplan wants match.name
        # as a SCALAR and wifis to define access-points — two generator rejections
        # on the board (notes/58 §5 坑六), and netplan never writes the boot-time
        # wpa conf anyway (坑二). The .link keys on the KERNEL name (rtw88
        # registers wlan0 before udev's predictable rename) and /etc outranks
        # 99-default.link's MAC policy → the wlx rename never happens; everything
        # downstream (network/wpa/unit) keys on the stable wlan0. MAC-independent.
        sd = root / "etc" / "systemd" / "network"
        sd.mkdir(parents=True, exist_ok=True)
        (sd / "10-forge-wifi.link").write_text(
            "[Match]\n"
            "OriginalName=wlan*\n"
            "\n"
            "[Link]\n"
            f"Name={iface}\n")
        (sd / "20-forge-wifi.network").write_text(
            "[Match]\n"
            f"Name={iface}\n"
            "\n"
            "[Network]\n"
            "DHCP=yes\n")
        # netplan's systemd-generator is what used to pull networkd up at boot
        # (it enables it in /run when a netplan config exists). We dropped netplan
        # → WE must enable networkd ourselves, or nothing runs DHCP (board-caught
        # 2026-08-15: "systemd-networkd is not running").
        (root / "etc/systemd/system/multi-user.target.wants").mkdir(parents=True,
                                                                    exist_ok=True)
        (root / "etc/systemd/system/multi-user.target.wants" /
         "systemd-networkd.service").symlink_to(
            "/usr/lib/systemd/system/systemd-networkd.service")

        psk = hashlib.pbkdf2_hmac("sha1", passphrase.encode(), ssid.encode(), 4096, 32).hex()
        wpa_dir = root / "etc" / "wpa_supplicant"
        wpa_dir.mkdir(parents=True, exist_ok=True)
        (wpa_dir / f"wpa_supplicant-{iface}.conf").write_text(
            "ctrl_interface=DIR=/run/wpa_supplicant GROUP=root\n"
            "network={\n"
            f'  ssid="{ssid}"\n'
            f"  psk={psk}\n"
            "  key_mgmt=WPA-PSK\n"
            "}\n")
        os.chmod(wpa_dir / f"wpa_supplicant-{iface}.conf", 0o600)

        # enable the unit without a chroot: the same symlink `systemctl enable`
        # would create (template instance for the renamed interface).
        wants = root / "etc/systemd/system/multi-user.target.wants"
        wants.mkdir(parents=True, exist_ok=True)
        (wants / f"wpa_supplicant@{iface}.service").symlink_to(
            "/usr/lib/systemd/system/wpa_supplicant@.service")

        # /run is tmpfs and this rootfs ships no tmpfiles entry for the ctrl dir.
        tmpd = root / "etc/tmpfiles.d"
        tmpd.mkdir(parents=True, exist_ok=True)
        (tmpd / "wpa_supplicant.conf").write_text("d /run/wpa_supplicant 0755 root root -\n")

        self.log.ok(f"wifi provisioned: {iface} auto-connects to {ssid!r} on boot")

    # ── fakeroot re-exec (ubuntu ownership preservation) ──────────────────────
    def _rerun_under_fakeroot(self, out_dir: Path, profile: str) -> None:
        if not shutil.which("fakeroot"):
            self.log.die("missing host tool: fakeroot (needed to preserve Ubuntu rootfs ownership)")
        state = out_dir / ".rootfs.fakeroot"
        state.unlink(missing_ok=True)
        self.log.info("staging Ubuntu rootfs under fakeroot (persistent ownership metadata)")
        env = dict(os.environ,
                   FAKEROOTDONTTRYCHOWN="1",
                   RK_FORGE_STAGE_FAKEROOT="1")
        cli = Path(__file__).resolve().parent / "cli.py"
        # fork+wait (NOT os.execvpe): exec replaced the whole forge process, so
        # `forge all` silently ended right here — pack-emmc/assemble never ran and
        # the stage-rootfs fingerprint was never recorded (the exec'd child runs
        # the bare `stage` leaf, outside StageRunner). Wait for the child instead;
        # control returns to the orchestrator, which marks the stage and continues.
        result = subprocess.run(
            ["fakeroot", "-s", str(state), "--",
             sys.executable, str(cli),
             "--root", str(self.project.root),   # global — must precede the subcommand
             "stage", "--board", self.board.id, "--profile", profile,
             "--out", str(out_dir)],
            env=env)
        if result.returncode != 0:
            self.log.die(f"fakeroot stage failed ({result.returncode})")

    def _find_openwrt_target_dir(self) -> Path | None:
        bd = self.project.src_dir / self.board.id / "openwrt" / "build_dir"
        if not bd.is_dir():
            return None
        for p in bd.rglob("root-rockchip"):
            if p.is_dir():
                return p
        return None


def _tree_size(root: Path) -> str:
    """Human-readable tree size (du -sh analogue)."""
    try:
        return subprocess.run(["du", "-sh", str(root)], capture_output=True,
                              text=True).stdout.split()[0]
    except Exception:
        return "?"
