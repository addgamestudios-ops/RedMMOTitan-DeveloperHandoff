"""Offline no-clobber verifier for the clean RedMMO celestial registry port."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(r"D:\RedMMOTitan")
CLEAN = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
SOURCE = {
    REPO / r"Source\RedMMO\RedCelestialFrameRegistry.h":
        CLEAN / r"Source\RedMMO\Public\RedCelestialFrameRegistry.h",
    REPO / r"Source\RedMMO\RedCelestialFrameRegistry.cpp":
        CLEAN / r"Source\RedMMO\Private\RedCelestialFrameRegistry.cpp",
}
EXPECTED = {
    "header": "223593D0338ECE2D94804ECE56391B22BA707D5CFE875F6F0A7B07579F6669D7",
    "implementation": "1C72D20ED720C49AA948282F956504EE6E2BA69BB0184D17C7DEBC7FB67F44B0",
}
PROTECTED = {
    CLEAN / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap":
        "0AB96B91A1F42042C878DC1822E3BB6D6C14DD0D5F3693D2FCD6492819D7EA75",
    REPO / r"Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap":
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    REPO / r"Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap":
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("refusing to clobber existing report: {}".format(args.output))

    copies = []
    for source, target in SOURCE.items():
        if not source.is_file() or not target.is_file():
            raise FileNotFoundError(target)
        source_hash = sha256(source)
        target_hash = sha256(target)
        if source_hash != target_hash:
            raise RuntimeError("source/target mismatch: {}".format(target))
        copies.append({
            "source": str(source), "target": str(target),
            "source_sha256": source_hash, "target_sha256": target_hash,
            "bytes": target.stat().st_size,
        })
    if copies[0]["target_sha256"] != EXPECTED["header"]:
        raise RuntimeError("header identity drift")
    if copies[1]["target_sha256"] != EXPECTED["implementation"]:
        raise RuntimeError("implementation identity drift")

    clean_source_files = sorted(
        path for path in (CLEAN / "Source").rglob("*") if path.suffix in {".h", ".cpp"})
    producer_calls = []
    consumers = []
    for path in clean_source_files:
        if path in SOURCE.values():
            continue
        text = path.read_text(encoding="utf-8", errors="strict")
        if re.search(r"RedCelestialFrames::RegisterOrUpdate\s*\(", text):
            producer_calls.append(str(path))
        if re.search(r"RedCelestialFrames::ResolveExact\s*\(", text):
            consumers.append(str(path))
    if producer_calls or consumers:
        raise RuntimeError("source-only tranche unexpectedly wired registry")

    build_text = (CLEAN / r"Source\RedMMO\RedMMO.Build.cs").read_text(encoding="utf-8")
    if not all(name in build_text for name in ('"Core"', '"CoreUObject"', '"Engine"')):
        raise RuntimeError("clean module dependency drift")

    protected = []
    for path, expected in PROTECTED.items():
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError("protected hash mismatch: {}".format(path))
        protected.append({"path": str(path), "sha256": actual})

    result = {
        "schema_version": 1,
        "verification": "clean_redmmo_celestial_registry_exact_source_port",
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_class": "static",
        "result": "pass_exact_source_unwired",
        "copies": copies,
        "producer_callsites": producer_calls,
        "consumer_callsites": consumers,
        "module_dependencies_present": True,
        "protected": protected,
        "claim_limit": "Exact unwired source and protected-hash evidence only; no build or runtime claim.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "result": result["result"],
        "output": str(args.output),
        "output_sha256": sha256(args.output),
        "copy_count": len(copies),
        "producer_callsites": len(producer_calls),
        "consumer_callsites": len(consumers),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
