"""Board config — the single source of truth per board (config/boards/<id>.yaml).

A ``Board`` owns both its data (the YAML fields) and the behaviours the build
needs from it today: loading (``from_yaml``, which also runs ``_validate``) and
emitting itself as the bash env the still-bash scripts read (``to_bash_env``).

PR2 adds load-time explicit-ization (``_validate``): the fields that previously
leaked via bash source-ordering / silent defaults — ``rkbin.spl_source``,
``uboot.arch_override``, ``storage.rootfs_mib`` / ``nand_geometry`` — must now be
present and self-consistent, so a misconfiguration fails at load (in <1 ms), not
mid-build. ``kernel.base == sources.linux.ref`` and ``rootfs_profiles`` capability
checks land later (those fields enter board.yaml when fetch / profiles port).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Board:
    # ── identity ─────────────────────────────────────────────────────────────
    id: str
    soc: str
    arch: str
    abi: str
    cpu: str

    # ── kernel ───────────────────────────────────────────────────────────────
    kernel_base: str
    dtb_name: str
    kern_img: str
    kernel_base_defconfig: str
    kernel_fragments: list = field(default_factory=list)

    # ── u-boot ───────────────────────────────────────────────────────────────
    uboot_defconfig: str = ""
    uboot_defconfig_sd: str = ""
    uboot_fit_source: str = ""
    uboot_arch_override: str = "arm"        # explicit (PR2): Rockchip u-boot ships under arch/arm/ even for arm64 SoCs

    # ── buildroot / wifi / storage ───────────────────────────────────────────
    buildroot_defconfig: str = ""
    wifi_driver: str = ""
    storage_kind: str = ""
    rootfs_mib: int | None = None            # required on emmc/sd (PR2); forbidden on nand
    nand_min_io: int | None = None
    nand_peb: str | None = None
    nand_leb: str | None = None
    nand_max_leb: int | None = None

    # ── workspace ────────────────────────────────────────────────────────────
    bringup_dir: str = ""
    board_cfg_dir: str = ""

    # ── rkbin ────────────────────────────────────────────────────────────────
    rkbin_blob_subdir: str = ""
    rkbin_ddr: str = ""
    rkbin_usbplug: str = ""
    rkbin_spl: str = ""
    rkbin_tee: str = ""
    rkbin_tee_exclude: str = ""
    rkbin_bl31: str | None = None            # None = no ATF stage (RK3506)
    rkbin_spl_source: str | None = None      # explicit (PR2): rkbin|mainline on every board

    # ── loader / manifests ───────────────────────────────────────────────────
    loader_ini: str = ""
    loader_trust_ini: str | None = None      # None = unset (aes / rk3588)
    parameter: dict = field(default_factory=dict)   # keyed by storage variant: nand/sd/emmc
    package: dict = field(default_factory=dict)     # keyed by image purpose: nand/rescue/sd/emmc

    # ── toolchain ────────────────────────────────────────────────────────────
    toolchain_prefix: str = ""
    toolchain_bin_dir: str = ""
    toolchain_sysroot: str = ""

    # ── convenience properties (read cleanly at call sites in later phases) ──
    @property
    def is_nand(self) -> bool:
        return self.storage_kind == "nand"

    @property
    def is_emmc(self) -> bool:
        return self.storage_kind == "emmc"

    @property
    def is_sd(self) -> bool:
        return self.storage_kind == "sd"

    @property
    def has_atf(self) -> bool:
        """BL31/ATF present (RK3568/RK3588); False on RK3506."""
        return self.rkbin_bl31 is not None

    # ── loading ──────────────────────────────────────────────────────────────
    @classmethod
    def from_yaml(cls, board_id: str, root) -> "Board":
        """Load ``config/boards/<board_id>.yaml`` → ``Board``, then validate."""
        path = Path(root) / "config" / "boards" / f"{board_id}.yaml"
        raw = yaml.safe_load(path.read_text())

        nand = (raw.get("storage") or {}).get("nand_geometry") or {}
        blobs = raw["rkbin"]["blobs"]
        manifests = raw["manifests"]

        board = cls(
            # identity
            id=raw["identity"]["board"],
            soc=raw["identity"]["soc"],
            arch=raw["identity"]["arch"],
            abi=raw["identity"]["abi"],
            cpu=raw["identity"]["cpu"],
            # kernel
            kernel_base=raw["kernel"]["base"],
            dtb_name=raw["kernel"]["dtb_name"],
            kern_img=raw["kernel"]["img"],
            kernel_base_defconfig=raw["kernel"]["base_defconfig"],
            kernel_fragments=list(raw["kernel"]["fragments"]),
            # u-boot
            uboot_defconfig=raw["uboot"]["defconfig"],
            uboot_defconfig_sd=raw["uboot"].get("defconfig_sd", ""),
            uboot_fit_source=raw["uboot"]["fit_source"],
            uboot_arch_override=raw["uboot"].get("arch_override", "arm"),
            # buildroot / wifi / storage
            buildroot_defconfig=(raw.get("buildroot") or {}).get("defconfig", ""),
            wifi_driver=raw.get("wifi_driver", ""),
            storage_kind=raw["storage"]["kind"],
            rootfs_mib=raw["storage"].get("rootfs_mib"),
            nand_min_io=nand.get("min_io"),
            nand_peb=nand.get("peb"),
            nand_leb=nand.get("leb"),
            nand_max_leb=nand.get("max_leb"),
            # workspace
            bringup_dir=raw["workspace"]["bringup_dir"],
            board_cfg_dir=raw["workspace"]["board_cfg_dir"],
            # rkbin
            rkbin_blob_subdir=raw["rkbin"]["blob_subdir"],
            rkbin_ddr=blobs["ddr"],
            rkbin_usbplug=blobs["usbplug"],
            rkbin_spl=blobs["spl"],
            rkbin_tee=blobs["tee"],
            rkbin_tee_exclude=blobs.get("tee_exclude", ""),
            rkbin_bl31=blobs.get("bl31"),
            rkbin_spl_source=raw["rkbin"].get("spl_source"),
            # loader / manifests
            loader_ini=manifests["loader_ini"],
            loader_trust_ini=manifests.get("trust_ini"),
            parameter=dict(manifests.get("parameter", {})),
            package=dict(manifests.get("package", {})),
            # toolchain
            toolchain_prefix=raw["toolchain"]["prefix"],
            toolchain_bin_dir=raw["toolchain"]["bin_dir"],
            toolchain_sysroot=raw["toolchain"].get("sysroot", ""),
        )
        board._validate()
        return board

    # ── validation (PR2 explicit-ization — fail at load, not mid-build) ──────
    def _validate(self) -> None:
        errors: list[str] = []

        if self.rkbin_spl_source is None:
            errors.append("rkbin.spl_source missing — must be explicit: rkbin | mainline")
        if not self.uboot_arch_override:
            errors.append("uboot.arch_override missing (Rockchip u-boot ships under arch/arm/; default 'arm')")

        if self.is_emmc or self.is_sd:
            if self.rootfs_mib is None:
                errors.append(f"storage.rootfs_mib required for storage.kind={self.storage_kind!r}")
            elif self.rootfs_mib >= 4096:
                errors.append(f"storage.rootfs_mib={self.rootfs_mib} must be < 4096 (RKAF entry size is uint32)")
            if self.nand_min_io is not None:
                errors.append(f"storage.nand_geometry must be absent for storage.kind={self.storage_kind!r}")
        elif self.is_nand:
            if self.rootfs_mib is not None:
                errors.append("storage.rootfs_mib must be absent for storage.kind='nand'")
            for name, value in (("min_io", self.nand_min_io), ("peb", self.nand_peb),
                                ("leb", self.nand_leb), ("max_leb", self.nand_max_leb)):
                if value is None:
                    errors.append(f"storage.nand_geometry.{name} required for storage.kind='nand'")

        if errors:
            raise ValueError(f"board {self.id!r} config invalid:\n  - " + "\n  - ".join(errors))

    # ── emitting (the PR1 bridge to the still-bash build scripts) ────────────
    def to_bash_env(self) -> str:
        """Emit this board as bash-sourceable ``export KEY="value"`` lines.

        The field→bash-var map mirrors the legacy .env exactly; ``None``
        fields are skipped (not emitted empty) so env.sh's downstream path
        resolution is unaffected. PR2's explicit fields (spl_source everywhere,
        rootfs_mib on rk3568) are now emitted too — they match the bash defaults
        the scripts already applied, so build behaviour is unchanged.
        """
        lines: list[str] = [
            f"# auto-generated by `forge config --board {self.id} --emit-env`"
            f" — source: config/boards/{self.id}.yaml. Do not edit."
        ]
        for name, value in self._bash_env_pairs():
            if value is None:
                continue
            lines.append(f"export {name}={self._bash_quote(value)}")
        return "\n".join(lines) + "\n"

    def _bash_env_pairs(self) -> list[tuple[str, object]]:
        """Field → bash-var-name pairs, in the legacy .env's order."""
        return [
            # identity
            ("BOARD", self.id), ("SOC", self.soc), ("ARCH", self.arch),
            ("ABI", self.abi), ("CPU", self.cpu), ("KERNEL_BASE", self.kernel_base),
            # kernel
            ("DT_NAME", self.dtb_name), ("KERN_IMG", self.kern_img),
            ("KERNEL_BASE_DEFCONFIG", self.kernel_base_defconfig),
            ("KERNEL_FRAGMENTS", " ".join(self.kernel_fragments)),
            # u-boot
            ("UBOOT_DEFCONFIG", self.uboot_defconfig),
            ("UBOOT_DEFCONFIG_SD", self.uboot_defconfig_sd),   # emit even when "" (matches .env)
            ("UBOOT_FIT_SOURCE", self.uboot_fit_source),
            # buildroot / wifi / storage
            ("BUILDROOT_DEFCONFIG", self.buildroot_defconfig),
            ("WIFI_DRIVER", self.wifi_driver),
            ("STORAGE", self.storage_kind),
            ("ROOTFS_MIB", self.rootfs_mib),
            ("NAND_MIN_IO", self.nand_min_io), ("NAND_PEB", self.nand_peb),
            ("NAND_LEB", self.nand_leb), ("NAND_MAX_LEB", self.nand_max_leb),
            # workspace
            ("BRINGUP_DIR", self.bringup_dir), ("BOARD_CFG_DIR", self.board_cfg_dir),
            # rkbin
            ("RKBIN_BLOB_SUBDIR", self.rkbin_blob_subdir),
            ("RKBIN_DDR_PAT", self.rkbin_ddr), ("RKBIN_USBPLUG_PAT", self.rkbin_usbplug),
            ("RKBIN_SPL_PAT", self.rkbin_spl), ("RKBIN_TEE_PAT", self.rkbin_tee),
            ("RKBIN_TEE_EXCLUDE", self.rkbin_tee_exclude),
            ("RKBIN_BL31_PAT", self.rkbin_bl31),        # None → skipped on aes
            ("SPL_SOURCE", self.rkbin_spl_source),      # explicit everywhere now (PR2)
            # loader / manifests
            ("LOADER_INI", self.loader_ini), ("LOADER_TRUST_INI", self.loader_trust_ini),
            *[(f"PARAMETER_{k.upper()}", v) for k, v in self.parameter.items()],
            *[(f"PKGFILE_{k.upper()}", v) for k, v in self.package.items()],
            # toolchain
            ("TOOLCHAIN_PREFIX", self.toolchain_prefix),
            ("TOOLCHAIN_BIN_DIR", self.toolchain_bin_dir),
            ("TOOLCHAIN_SYSROOT", self.toolchain_sysroot),
        ]

    @staticmethod
    def _bash_quote(value) -> str:
        """Bash-double-quote a value, escaping chars special inside ``"..."``."""
        s = str(value)
        for ch, esc in (("\\", "\\\\"), ('"', '\\"'), ("$", "\\$"), ("`", "\\`")):
            s = s.replace(ch, esc)
        return f'"{s}"'
