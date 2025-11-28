from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_INDEX_URL = "https://raw.githubusercontent.com/EnjiMD/Continuum/main/docs/index.json"


def _app_data_dir(app_name: str = "Continuum") -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / app_name
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / app_name
    return Path.home() / ".local" / "share" / app_name


def _parse_version(v: str) -> tuple[int, int, int]:
    parts = (v or "0").strip().split(".")
    nums: list[int] = []
    for p in parts[:3]:
        try:
            digits = "".join([c for c in p if c.isdigit()])
            nums.append(int(digits or "0"))
        except Exception:
            nums.append(0)
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums)  # type: ignore


def _sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()


def _https_only(url: str) -> None:
    if not url.lower().startswith("https://"):
        raise ValueError(f"Refusing non-HTTPS URL: {url}")


def _fetch_bytes(url: str, timeout: int = 15) -> bytes:
    _https_only(url)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Continuum/1.0 (Guidelines updater)"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _fetch_json(url: str) -> Any:
    raw = _fetch_bytes(url)
    return json.loads(raw.decode("utf-8"))


@dataclass(frozen=True)
class PackInfo:
    id: str
    title: str
    version: str
    manifest_url: str
    rules_url: str
    sha256_manifest: str
    sha256_rules: str


@dataclass(frozen=True)
class PackUpdate:
    pack: PackInfo
    installed_version: str | None


class GuidelinesManager:
    def __init__(self) -> None:
        self.base_dir = _app_data_dir("Continuum")
        self.guidelines_dir = self.base_dir / "guidelines"
        self.guidelines_dir.mkdir(parents=True, exist_ok=True)

        self.builtin_dir = Path(__file__).resolve().parent / "guidelines_builtin"

    def ensure_builtin_installed(self) -> None:
        if not self.builtin_dir.exists():
            return
        builtin_index = self.builtin_dir / "index.json"
        if not builtin_index.exists():
            return
        packs_dir = self.builtin_dir / "packs"
        if not packs_dir.exists():
            return

        for pack_dir in packs_dir.iterdir():
            if not pack_dir.is_dir():
                continue
            dest = self.guidelines_dir / pack_dir.name
            if dest.exists():
                continue
            dest.mkdir(parents=True, exist_ok=True)
            for fname in ("manifest.json", "rules.json"):
                src = pack_dir / fname
                if src.exists():
                    (dest / fname).write_bytes(src.read_bytes())

    def list_installed(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for d in self.guidelines_dir.iterdir():
            if not d.is_dir():
                continue
            m = d / "manifest.json"
            if not m.exists():
                continue
            try:
                j = json.loads(m.read_text(encoding="utf-8"))
                out[d.name] = str(j.get("version", "0.0.0"))
            except Exception:
                continue
        return out

    def read_pack_rules(self, pack_id: str) -> list[dict[str, Any]]:
        rules_path = self.guidelines_dir / pack_id / "rules.json"
        if not rules_path.exists():
            return []
        return json.loads(rules_path.read_text(encoding="utf-8"))

    def fetch_index(self, index_url: str) -> list[PackInfo]:
        idx = _fetch_json(index_url)
        packs = idx.get("packs", [])
        out: list[PackInfo] = []
        for p in packs:
            out.append(
                PackInfo(
                    id=str(p["id"]),
                    title=str(p.get("title", p["id"])),
                    version=str(p.get("version", "0.0.0")),
                    manifest_url=str(p["manifest_url"]),
                    rules_url=str(p["rules_url"]),
                    sha256_manifest=str(p["sha256_manifest"]).lower(),
                    sha256_rules=str(p["sha256_rules"]).lower(),
                )
            )
        return out

    def check_updates(self, index_url: str) -> list[PackUpdate]:
        remote = self.fetch_index(index_url)
        installed = self.list_installed()

        updates: list[PackUpdate] = []
        for p in remote:
            local_v = installed.get(p.id)
            if local_v is None:
                updates.append(PackUpdate(pack=p, installed_version=None))
                continue
            if _parse_version(p.version) > _parse_version(local_v):
                updates.append(PackUpdate(pack=p, installed_version=local_v))
        return updates

    def install_pack(self, pack: PackInfo) -> None:
        manifest_bytes = _fetch_bytes(pack.manifest_url)
        rules_bytes = _fetch_bytes(pack.rules_url)

        if _sha256_bytes(manifest_bytes) != pack.sha256_manifest:
            raise ValueError(f"manifest SHA mismatch for {pack.id}")
        if _sha256_bytes(rules_bytes) != pack.sha256_rules:
            raise ValueError(f"rules SHA mismatch for {pack.id}")

        dest = self.guidelines_dir / pack.id
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "manifest.json").write_bytes(manifest_bytes)
        (dest / "rules.json").write_bytes(rules_bytes)
