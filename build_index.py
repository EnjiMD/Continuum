#!/usr/bin/env python3
import json, hashlib
from pathlib import Path
from datetime import datetime, timezone

REPO = "EnjiMD/Continuum"
BRANCH = "main"
DOCS = Path("docs")
PACKS = DOCS / "packs"
BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/docs"

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()

def main():
    if not PACKS.exists():
        raise SystemExit("Missing docs/packs. Create packs under docs/packs/<pack_id>/ first.")

    packs_out = []
    for pack_dir in sorted([d for d in PACKS.iterdir() if d.is_dir()]):
        manifest = pack_dir / "manifest.json"
        rules = pack_dir / "rules.json"
        if not (manifest.exists() and rules.exists()):
            print(f"Skipping {pack_dir.name}: missing manifest.json or rules.json")
            continue

        m = json.loads(manifest.read_text(encoding="utf-8"))
        pid = m.get("id", pack_dir.name)
        title = m.get("title", pid)
        version = m.get("version", "0.0.0")

        packs_out.append({
            "id": pid,
            "title": title,
            "version": version,
            "manifest_url": f"{BASE}/packs/{pack_dir.name}/manifest.json",
            "rules_url": f"{BASE}/packs/{pack_dir.name}/rules.json",
            "sha256_manifest": sha256_file(manifest),
            "sha256_rules": sha256_file(rules),
        })

    idx = {
        "schema_version": 1,
        "updated_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "packs": packs_out
    }

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "index.json").write_text(json.dumps(idx, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote docs/index.json with {len(packs_out)} pack(s).")

if __name__ == "__main__":
    main()
