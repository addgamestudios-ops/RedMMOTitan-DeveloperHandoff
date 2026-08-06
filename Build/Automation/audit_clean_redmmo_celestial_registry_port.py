"""Offline gate for porting the proven celestial-frame registry into clean RedMMO.

The audit is read-only apart from its no-clobber JSON report. It authenticates
the legacy source, limits dependencies, checks clean-module compatibility, and
records the still-unwired producer/client boundaries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(r"D:\RedMMOTitan")
CLEAN = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
LEGACY_H = REPO / r"Source\RedMMO\RedCelestialFrameRegistry.h"
LEGACY_CPP = REPO / r"Source\RedMMO\RedCelestialFrameRegistry.cpp"
CLEAN_BUILD = CLEAN / r"Source\RedMMO\RedMMO.Build.cs"
CLEAN_PPG_H = CLEAN / r"Source\RedMMO\Public\RedPPGSurfaceAuthority.h"
CLEAN_PPG_CPP = CLEAN / r"Source\RedMMO\Private\RedPPGSurfaceAuthority.cpp"
ADR = REPO / r"ProjectKnowledge\decisions\ADR-0001-celestial-registry-and-gravity.md"

EXPECTED = {
    LEGACY_H: "223593D0338ECE2D94804ECE56391B22BA707D5CFE875F6F0A7B07579F6669D7",
    LEGACY_CPP: "1C72D20ED720C49AA948282F956504EE6E2BA69BB0184D17C7DEBC7FB67F44B0",
}

PROTECTED = {
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


def relative(path: Path) -> str:
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return "clean-redmmo/" + path.relative_to(CLEAN).as_posix()


def require(text: str, pattern: str, label: str) -> dict:
    found = re.search(pattern, text, re.MULTILINE | re.DOTALL) is not None
    if not found:
        raise RuntimeError("missing required contract: " + label)
    return {"label": label, "pattern": pattern, "present": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("refusing to clobber existing result: {}".format(args.output))

    inputs = (LEGACY_H, LEGACY_CPP, CLEAN_BUILD, CLEAN_PPG_H, CLEAN_PPG_CPP, ADR)
    for path in inputs:
        if not path.is_file():
            raise FileNotFoundError(path)
    for path, expected in EXPECTED.items():
        if sha256(path) != expected:
            raise RuntimeError("authenticated legacy registry changed: {}".format(path))

    header = LEGACY_H.read_text(encoding="utf-8")
    impl = LEGACY_CPP.read_text(encoding="utf-8")
    build = CLEAN_BUILD.read_text(encoding="utf-8")
    ppg_h = CLEAN_PPG_H.read_text(encoding="utf-8")
    ppg_cpp = CLEAN_PPG_CPP.read_text(encoding="utf-8")
    adr = ADR.read_text(encoding="utf-8")
    combined = header + "\n" + impl

    includes = sorted(set(re.findall(r'^#include\s+[<\"]([^>\"]+)[>\"]', combined, re.MULTILINE)))
    allowed_includes = {
        "CoreMinimal.h", "RedCelestialFrameRegistry.h",
        "Engine/World.h", "GameFramework/Actor.h",
    }
    unexpected_includes = sorted(set(includes) - allowed_includes)
    if unexpected_includes:
        raise RuntimeError("unexpected registry dependency: " + ", ".join(unexpected_includes))

    contracts = [
        require(combined, r"RegisterOrUpdate", "registration API"),
        require(combined, r"Unregister", "revision-bound unregister API"),
        require(combined, r"ResolveExact", "exact stable-ID resolver"),
        require(combined, r"RemoveWorld", "world cleanup API"),
        require(combined, r"World->GetNetMode\(\)\s*!=\s*NM_Client", "server or standalone registration"),
        require(combined, r"Authority->HasAuthority\(\)", "authority-owned registration"),
        require(combined, r"IsNextRevision", "sequential revision rule"),
        require(combined, r"HighWaterRevision", "retained high-water state"),
        require(combined, r"bConflict", "sticky duplicate-authority conflict"),
        require(header, r"struct\s+REDMMO_API\s+FFrameSnapshot[\s\S]*?FName\s+StableId[\s\S]*?FVector\s+Center[\s\S]*?double\s+NominalRadiusCm[\s\S]*?uint64\s+Revision", "pointer-free frame snapshot"),
    ]

    module_compatible = all(name in build for name in ('"Core"', '"CoreUObject"', '"Engine"'))
    if not module_compatible:
        raise RuntimeError("clean module lacks registry dependencies")

    clean_source = "\n".join(
        path.read_text(encoding="utf-8", errors="strict")
        for path in sorted((CLEAN / "Source").rglob("*")) if path.suffix in {".h", ".cpp"}
    )
    clean_registry_absent = not re.search(
        r"RedCelestialFrames::|FFrameRegistration|FFrameSnapshot", clean_source)
    if not clean_registry_absent:
        raise RuntimeError("clean registry symbols already exist; no-copy gate requires review")

    home_frame = {
        "stable_id_declared": 'StableId = TEXT("planet.red.mars")' in ppg_h,
        "owner_declared": "TWeakObjectPtr<APlanetSpawner> Owner" in ppg_h,
        "center_declared": "FVector Center" in ppg_h,
        "nominal_radius_declared": "double NominalRadius" in ppg_h,
        "unique_spawner_resolver": (
            "ResolveUniqueHomeBody" in ppg_cpp
            and "++SpawnerCount" in ppg_cpp
            and "return EBodyResolveResult::AmbiguousBody" in ppg_cpp
            and "if (!ResolvedSpawner)" in ppg_cpp
        ),
    }
    if not all(home_frame.values()):
        raise RuntimeError("clean PPG body-frame contract incomplete")

    production_registration_absent = not re.search(r"RegisterOrUpdate\s*\(", clean_source)
    client_snapshot_absent = not re.search(
        r"Replicated.*(?:Celestial|Body).*Snapshot|OnRep_.*(?:Celestial|Body)", clean_source,
        re.IGNORECASE | re.DOTALL)

    protected = {}
    for path, expected in PROTECTED.items():
        actual = sha256(path)
        protected[relative(path)] = {"sha256": actual, "expected": expected, "match": actual == expected}
    if not all(item["match"] for item in protected.values()):
        raise RuntimeError("protected hash mismatch")

    result = {
        "schema_version": 1,
        "audit": "clean_redmmo_celestial_registry_port_gate",
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_class": "offline_static_source_audit",
        "inputs": [{"path": relative(path), "sha256": sha256(path), "bytes": path.stat().st_size} for path in inputs],
        "authenticated_legacy_source": True,
        "legacy_registry_contracts": contracts,
        "includes": includes,
        "unexpected_includes": unexpected_includes,
        "clean_module_has_required_dependencies": module_compatible,
        "clean_registry_symbols_absent": clean_registry_absent,
        "clean_ppg_home_frame": home_frame,
        "production_registration_absent": production_registration_absent,
        "client_replicated_snapshot_absent": client_snapshot_absent,
        "adr_contract": {
            "accepted": "Status: Accepted" in adr,
            "server_owns_registry": "server owns" in adr.lower() and "registry bindings and lifecycle" in adr,
            "client_cannot_choose_authority": "cannot choose the authoritative body" in adr,
        },
        "protected": protected,
        "result": "source_dependency_prunable_port_ready_but_unwired",
        "claim_limit": "Portability and source-contract evidence only; no copy, compile, producer, client replication, runtime, warp, visual, standalone or multiplayer proof.",
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "result": result["result"],
        "output": str(args.output),
        "output_sha256": sha256(args.output),
        "contracts": len(contracts),
        "includes": includes,
        "producer_absent": production_registration_absent,
        "client_snapshot_absent": client_snapshot_absent,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
