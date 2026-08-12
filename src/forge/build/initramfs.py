"""InitramfsBuilder — generate the first-boot provisioning initramfs.cpio.gz
from tracked/pinned sources (the in-forge generator).

Replaces ``scripts/build-initramfs.sh``. The provisioning initramfs is what
``boot.img``'s ramdisk node carries: a static busybox shell + ``/init`` +
``ubiprog``. On FIRST boot ``/init`` rewrites the SPI-NAND rootfs partition
through the kernel's reliable write path (ubiprog), working around the rkbin
loader's weak programming of some erase blocks. A marker file makes later boots
skip the rewrite and ``switch_root`` to the real rootfs.

Reproducibility: everything builds from source under the forge toolchain — NO
ATK vendor-sdk dependency:

* busybox ← forge.yaml ``sources.busybox`` (upstream 1.36.1 tarball, sha256-pinned) — static
* ubiprog  ← ``<bringup>/rootfs/ubiprog.c`` (tracked) — static
* /init    ← ``<bringup>/initramfs/init`` (tracked)

``SOURCE_DATE_EPOCH=0`` (busybox embeds a build date; gcc respects it) +
``gzip -n`` (drops the gzip header mtime) → two builds converge on SIZE. The
embedded ``rootfs.ubi.img.gz`` (ubiprog re-writes mtd5 from this RAM copy on
first boot) requires this stage to run AFTER pack-ubifs (DAG order in forge.sh).

Output: ``<bringup>/fit/initramfs.cpio.gz`` (the path pack-fit incbin's).
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from forge.build import check_toolchain, make_env
from forge.build.progress import run_with_progress
from forge.config.board import Board
from forge.config.project import Project
from forge.core.log import Log
from forge.core.proc import Proc

_BB_VER = "busybox-1.36.1"   # matches the pinned tarball's top-level dir
# minimal pre-created applet symlinks (/init calls the rest via /bin/busybox).
_APPLETS = ("sh", "mount", "umount", "ls", "cat", "echo", "uname",
            "mkdir", "ps", "dmesg", "pwd", "vi")


class InitramfsBuilder:
    """Builds the provisioning initramfs (static busybox + ubiprog + /init + rootfs.ubi.img.gz)."""

    def __init__(self, board: Board, project: Project,
                 proc: Proc | None = None, log: Log | None = None):
        self.board = board
        self.project = project
        self.log = log or Log()
        self.proc = proc or Proc(log=self.log)
        self.bringup = project.root / board.bringup_dir
        self.bb_src = project.src_dir / _BB_VER
        self.ubiprog_src = self.bringup / "rootfs" / "ubiprog.c"
        self.init_src = self.bringup / "initramfs" / "init"

    def build(self, *, out_dir: Path, out_cpio: Path | None = None,
              clean: bool = False) -> None:
        b = self.board
        check_toolchain(b, self.log)
        out_cpio = Path(out_cpio) if out_cpio else (self.bringup / "fit" / "initramfs.cpio.gz")
        rootfs_ubi = Path(out_dir) / "rootfs.ubi.img"

        bb_url, bb_sha256 = self._read_busybox_pin()
        for f in (self.ubiprog_src, self.init_src):
            if not f.is_file():
                self.log.die(f"initramfs source missing: {f}")

        # Reproducibility: pin the build timestamp (busybox embeds a build date;
        # gcc respects SOURCE_DATE_EPOCH). gzip -n below drops the gzip mtime.
        env = make_env(b, extra={"SOURCE_DATE_EPOCH": os.environ.get("SOURCE_DATE_EPOCH", "0")})

        self._ensure_busybox_source(bb_url, bb_sha256)
        self._build_busybox(env, clean=clean)
        self._pack_cpio(env, out_cpio, rootfs_ubi)
        self.log.info("next: forge pack (pack-fit incbin's it into boot.img)")

    # ── busybox source: download + sha256-verify + extract (idempotent) ────────
    def _read_busybox_pin(self) -> tuple[str, str]:
        """busybox tarball url + sha256, from forge.yaml sources (§5.1; was pins/busybox)."""
        bb = self.project.sources.get("busybox")
        if not bb or "url" not in bb or "sha256" not in bb:
            self.log.die("busybox source missing in forge.yaml sources (want {url, sha256})")
        return bb["url"], bb["sha256"]

    def _ensure_busybox_source(self, url: str, sha256: str) -> None:
        if self.bb_src.is_dir():
            return
        tarball = self.bb_src.with_suffix(".tar.bz2")
        self.bb_src.parent.mkdir(parents=True, exist_ok=True)
        self.log.info(f"downloading {_BB_VER} ({url})")
        # forge standard: curl first, wget fallback.
        if not _download(self.proc, url, tarball):
            self.log.die(f"failed to download {url}")
        self.log.info(f"verifying sha256 ({sha256})")
        import hashlib
        if hashlib.sha256(tarball.read_bytes()).hexdigest() != sha256:
            tarball.unlink(missing_ok=True)
            self.log.die(f"busybox tarball sha256 mismatch ({url}). pin may be wrong.")
        self.log.info("extracting")
        self.proc.run(["tar", "xf", str(tarball), "-C", str(self.bb_src.parent)])
        tarball.unlink(missing_ok=True)
        if not self.bb_src.is_dir():
            self.log.die(f"busybox extract did not create {self.bb_src}")

    # ── static busybox (in-tree; incremental) ─────────────────────────────────
    def _build_busybox(self, env: dict, *, clean: bool) -> None:
        b = self.board
        bb = self.bb_src / "busybox"
        if clean:
            bb.unlink(missing_ok=True)
            (self.bb_src / ".config").unlink(missing_ok=True)
        if bb.exists() and os.access(bb, os.X_OK):
            return
        cc_argv = ["make", f"ARCH={b.arch}", f"CROSS_COMPILE={b.toolchain_prefix}"]
        if not (self.bb_src / ".config").is_file():
            self.proc.run(cc_argv + ["defconfig"], cwd=str(self.bb_src), env_extra=env, quiet=True)
        # static link (no libc in the ramdisk). The sed is idempotent.
        cfg = self.bb_src / ".config"
        text = cfg.read_text()
        text = text.replace("# CONFIG_STATIC is not set", "CONFIG_STATIC=y")
        if "CONFIG_STATIC=y" not in text:
            text += "CONFIG_STATIC=y\n"
        cfg.write_text(text)
        self.log.info("building static busybox (gcc 15.2)…")
        run_with_progress("kernel", cc_argv + ["-j", str(os.cpu_count() or 1)],
                          project=self.project, proc=self.proc, log=self.log,
                          cwd=str(self.bb_src), env_extra=env)
        if not (bb.exists() and os.access(bb, os.X_OK)):
            self.log.die(f"busybox build produced no binary ({self.bb_src})")
        cp = self.proc.run(["file", str(bb)], capture=True, quiet=True)
        if "statically linked" not in (cp.stdout or ""):
            self.log.die("busybox is NOT static (CONFIG_STATIC=y?)")

    # ── assemble the ramdisk tree + pack cpio.gz ──────────────────────────────
    def _pack_cpio(self, env: dict, out_cpio: Path, rootfs_ubi: Path) -> None:
        b = self.board
        cc = f"{b.toolchain_prefix}gcc"
        root = Path(tempfile.mkdtemp(prefix="initramfs-"))
        try:
            for d in ("bin", "sbin", "proc", "sys", "dev", "etc",
                      "usr/bin", "usr/sbin", "tmp", "root"):
                (root / d).mkdir(parents=True, exist_ok=True)
            shutil.copy(self.bb_src / "busybox", root / "bin" / "busybox")
            (root / "bin" / "busybox").chmod(0o755)
            self.log.info("building static ubiprog (ubiprog.c)…")
            self.proc.run([cc, "-static", "-O2", "-s", str(self.ubiprog_src),
                           "-o", str(root / "bin" / "ubiprog")], env_extra=env)
            for a in _APPLETS:
                (root / "bin" / a).symlink_to("busybox")
            shutil.copy(self.init_src, root / "init")
            (root / "init").chmod(0o755)

            # FROM-SOURCE rootfs image: embed rootfs.ubi.img (gzipped) for ALL
            # profiles. ubiprog re-writes mtd5 from this RAM copy on first boot
            # (kills cross-image residue + the loader's weak write). Requires
            # build-initramfs to run AFTER pack-ubifs (DAG order in forge.sh).
            if not rootfs_ubi.is_file():
                self.log.die(
                    f"missing {rootfs_ubi} (build-initramfs runs after pack-ubifs; "
                    "run: forge pack)"
                )
            self.log.info(
                f"embedding {rootfs_ubi.name} → rootfs.ubi.img.gz "
                f"(from-source ubiprog)"
            )
            self._gzip_to(rootfs_ubi, root / "rootfs.ubi.img.gz")

            out_cpio.parent.mkdir(parents=True, exist_ok=True)
            self.log.info(f"packing cpio.gz → {out_cpio}")
            # find . | cpio -o -H newc | gzip -9 -n  → deterministic-ish (gzip -n
            # drops the header mtime; cpio newc records each file's mtime, so two
            # runs differ only by the embedded mtimes — size-equivalent, matches
            # the bash generator exactly).
            self._mk_cpio_gz(root, out_cpio)
            self.log.ok(f"initramfs.cpio.gz → {out_cpio} ({out_cpio.stat().st_size} B)")
            self.log.ok(
                f"  busybox={(root/'bin'/'busybox').stat().st_size} B  "
                f"ubiprog={(root/'bin'/'ubiprog').stat().st_size} B"
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def _gzip_to(self, src: Path, dst: Path) -> None:
        """gzip src → dst (``gzip -9 -n -c``; -n drops the header mtime).

        Direct file→file via subprocess (gzip output is BINARY — cannot route
        through ``Proc.run``, which decodes stdout as text).
        """
        import subprocess
        with open(dst, "wb") as out:
            r = subprocess.run(["gzip", "-9", "-n", "-c", str(src)],
                               stdout=out, env=self.proc.env_for())
        if r.returncode != 0:
            self.log.die(f"gzip failed for {src} (rc={r.returncode})")

    def _mk_cpio_gz(self, root: Path, out_cpio: Path) -> None:
        """find . | cpio -o -H newc | gzip -9 -n → out_cpio (Popen pipeline)."""
        import subprocess
        env = self.proc.env_for()
        find = subprocess.Popen(["find", "."], cwd=str(root), stdout=subprocess.PIPE, env=env)
        cpio = subprocess.Popen(["cpio", "-o", "-H", "newc", "--quiet"],
                                cwd=str(root), stdin=find.stdout,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
        assert find.stdout is not None
        find.stdout.close()
        gz = subprocess.Popen(["gzip", "-9", "-n"], stdin=cpio.stdout,
                              stdout=open(out_cpio, "wb"), env=env)
        assert cpio.stdout is not None
        cpio.stdout.close()
        rc = gz.wait()
        find.wait(); cpio.wait()
        if rc != 0:
            self.log.die(f"cpio.gz pipeline failed (rc={rc})")


def _download(proc: Proc, url: str, dest: Path) -> bool:
    """curl first (forge standard), wget fallback. True on success."""
    if proc.run(["curl", "-fL", "--retry", "3", "--connect-timeout", "30",
                 "-o", str(dest), url], check=False, quiet=True).returncode == 0:
        return True
    return proc.run(["wget", "-q", "--tries=3", "--timeout=30",
                     "-O", str(dest), url], check=False, quiet=True).returncode == 0
