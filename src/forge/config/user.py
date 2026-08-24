"""Per-developer drop-in config: ``user/*.yaml`` (gitignored).

``forge.yaml`` is the COMMITTED project config — generic teaching defaults
(§5.2: account ``rk-forge``/``rk-forge``, …). Everything personal lives in
``<repo>/user/``: WiFi credentials, dev ssh pubkeys, DNS, account
override. The directory is gitignored wholesale except ``*.example`` templates
and ``README.md`` — copy a template, strip the suffix, fill in.

Semantics (systemd-drop-in style):

* ``*.yaml`` files sorted by name, deep-merged in order (later files win);
* one domain per file (wifi / ssh / account / network) — a file's presence
  enables its feature, absence skips it;
* env overrides beat files (``FORGE_WIFI_SSID`` / ``FORGE_WIFI_PASS`` /
  ``FORGE_DNS``) for scripted one-offs;
* missing directory → all defaults (WiFi provisioning off).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DROPIN_DIR = "user"


@dataclass
class WifiCfg:
    ssid: str = ""
    psk: str = ""
    iface: str = "wlan0"


@dataclass
class SshCfg:
    pubkey_files: list[str] = field(default_factory=list)
    pubkeys: list[str] = field(default_factory=list)


@dataclass
class AccountCfg:
    username: str = ""
    password: str = ""


@dataclass
class UserConfig:
    wifi: WifiCfg = field(default_factory=WifiCfg)
    ssh: SshCfg = field(default_factory=SshCfg)
    account: AccountCfg = field(default_factory=AccountCfg)
    dns: str = ""
    perm_warnings: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, root: Path) -> "UserConfig":
        """Merge ``<root>/user/*.yaml`` (name-sorted) + env overrides."""
        d = Path(root) / DROPIN_DIR
        merged: dict[str, Any] = {}
        warns: list[str] = []
        if d.is_dir():
            if d.stat().st_mode & 0o077:
                warns.append(f"{d} is group/other-accessible — chmod 700 (it holds credentials)")
            for f in sorted(d.glob("*.yaml")):
                if f.stat().st_mode & 0o077:
                    warns.append(f"{f} is group/other-readable — chmod 600")
                _deep_merge(merged, yaml.safe_load(f.read_text()) or {})

        cfg = cls(perm_warnings=warns)
        wifi = merged.get("wifi") or {}
        cfg.wifi = WifiCfg(
            ssid=str(wifi.get("ssid") or ""),
            psk=str(wifi.get("psk") or ""),
            iface=str(wifi.get("iface") or "wlan0"))
        ssh = merged.get("ssh") or {}
        cfg.ssh = SshCfg(
            pubkey_files=[str(x) for x in ssh.get("pubkey_files") or []],
            pubkeys=[str(x) for x in ssh.get("pubkeys") or []])
        acct = merged.get("account") or {}
        cfg.account = AccountCfg(
            username=str(acct.get("username") or ""),
            password=str(acct.get("password") or ""))
        network = merged.get("network") or {}
        cfg.dns = str(network.get("dns") or "")

        # env overrides — scripted one-offs beat the files
        if os.environ.get("FORGE_WIFI_SSID"):
            cfg.wifi.ssid = os.environ["FORGE_WIFI_SSID"]
        if os.environ.get("FORGE_WIFI_PASS"):
            cfg.wifi.psk = os.environ["FORGE_WIFI_PASS"]
        if os.environ.get("FORGE_DNS"):
            cfg.dns = os.environ["FORGE_DNS"]
        return cfg


def _deep_merge(dst: dict[str, Any], src: dict[str, Any]) -> None:
    for k, v in (src or {}).items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v
