"""Project-level config (forge.yaml) — board-agnostic.

Minimal for PR1: the emit-env path only needs ``Board``; ``Project`` is wired in
now (used from PR2 onward for path resolution and the shared source pool) so the
shape is settled early.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Project:
    root: Path
    default_board: str
    src_dir: Path
    buildroot_dir: Path
    rkbin_dir: Path
    assets_dir: Path
    out_root: Path
    sources: dict = field(default_factory=dict)
    ubuntu_account: dict = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, root) -> "Project":
        """Load ``<root>/forge.yaml`` → ``Project``.

        Root is resolved to absolute so every derived path (src_dir, rkbin_dir,
        out_root, …) is cwd-independent — subprocess calls that ``cd`` into a
        temp workdir still resolve tools/blobs by absolute path.
        """
        root = Path(root).resolve()
        raw = yaml.safe_load((root / "forge.yaml").read_text())
        paths = raw.get("paths", {})
        return cls(
            root=root,
            default_board=raw.get("project", {}).get("default_board", "aes"),
            src_dir=root / paths.get("src_dir", "third_party/src"),
            buildroot_dir=root / paths.get("buildroot_dir", "third_party/buildroot"),
            rkbin_dir=root / paths.get("rkbin_dir", "third_party/rkbin"),
            assets_dir=root / paths.get("assets_dir", "assets"),
            out_root=root / paths.get("out_root", "out"),
            sources=dict(raw.get("sources", {})),
            ubuntu_account=dict(raw.get("ubuntu", {}).get("account", {})),
        )
