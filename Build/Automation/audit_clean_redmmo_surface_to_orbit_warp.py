"""Deterministic offline audit of clean RedMMO flight, orbit, and warp capability.

This scanner reads a fixed project-owned source/config set and architecture records.
It never launches Unreal, loads a package, or changes project content.  Absence
claims are intentionally limited to the audited clean RedMMO source/config set.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(r"D:\RedMMOTitan")
PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")

AUDIT_FILES = (
    PROJECT / r"Source\RedMMO\Public\RedShip.h",
    PROJECT / r"Source\RedMMO\Private\RedShip.cpp",
    PROJECT / r"Source\RedMMO\Public\RedShipMovementComponent.h",
    PROJECT / r"Source\RedMMO\Private\RedShipMovementComponent.cpp",
    PROJECT / r"Source\RedMMO\Public\RedGravityBodies.h",
    PROJECT / r"Source\RedMMO\Private\RedGravityBodies.cpp",
    PROJECT / r"Source\RedMMO\Public\RedPPGSurfaceAuthority.h",
    PROJECT / r"Source\RedMMO\Private\RedPPGSurfaceAuthority.cpp",
    PROJECT / r"Source\RedMMO\Public\RedPlanetNightPresentation.h",
    PROJECT / r"Source\RedMMO\Private\RedPlanetNightPresentation.cpp",
    PROJECT / r"Source\RedMMO\Private\RedPPGGameplayGameMode.cpp",
    PROJECT / r"Config\DefaultEngine.ini",
    PROJECT / r"Config\DefaultGame.ini",
    REPO / r"ProjectKnowledge\decisions\ADR-0002-server-authoritative-warp-state-machine.md",
    REPO / r"ProjectKnowledge\systems\warp-route.red-mars-to-ring-01.yaml",
)

PROTECTED = {
    REPO / r"Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap":
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    REPO / r"Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap":
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}

IMPLEMENTED_CHECKS = {
    "ship_replicates": (r"bReplicates\s*=\s*true", r"SetReplicateMovement\s*\(\s*true\s*\)"),
    "server_flight_input_rpc": (r"UFUNCTION\s*\(\s*Server\s*,\s*Unreliable\s*\)", r"ServerSetFlightInput"),
    "server_exit_rpc": (r"UFUNCTION\s*\(\s*Server\s*,\s*Reliable\s*\)", r"ServerRequestExitShip"),
    "six_axis_local_flight": (r"GetForwardVector\(\)\s*\*\s*ClampedMove\.X", r"GetRightVector\(\)\s*\*\s*ClampedMove\.Y", r"GetUpVector\(\)\s*\*\s*ClampedMove\.Z"),
    "pitch_yaw_roll": (r"PitchRateDegrees", r"YawRateDegrees", r"RollRateDegrees"),
    "boost_multiplier": (r"BoostMultiplier", r"bBoost"),
    "altitude_measurement": (r"GetAltitudeAboveNominalSurface", r"CurrentNominalRadius"),
    "stable_body_frame": (r"CurrentBodyId", r"StableId", r"ResolveUniqueHomeBody"),
    "owned_surface_collision": (r"SweepOwnedTerrain", r"TranslationCollisionEnvelope"),
    "possession_and_exit": (r"Possess\s*\(\s*this\s*\)", r"Possess\s*\(\s*ExitingPilot\s*\)"),
    "night_space_calculation": (r"SpaceTransitionWeight", r"StarVisibilityWeight", r"AtmosphereOpticalDepthProxy"),
}

MISSING_RUNTIME_CHECKS = {
    "authoritative_warp_state_machine": r"\bERedWarp(?:State|Phase)\b|\bFRedWarp(?:State|Route)\b",
    "warp_request_rpc": r"Server(?:Request|Begin|Start)Warp|UFUNCTION\s*\([^)]*Server[^)]*\)[\s\S]{0,160}\bWarp",
    "destination_registry_runtime": r"(?:Celestial|Destination|Body)Registry|ResolveDestinationBody",
    "sector_streaming_runtime": r"LoadStreamLevel|UnloadStreamLevel|WorldPartitionSubsystem|StreamingSource|DataLayerSubsystem",
    "map_or_server_travel_runtime": r"ServerTravel|ClientTravel|OpenLevel|SeamlessTravel",
    "atmosphere_vacuum_flight_state": r"\b(?:Atmosphere|Vacuum|Orbit)(?:Flight)?State\b|bInVacuum|bInAtmosphere",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def rel(path: Path) -> str:
    try:
        return path.relative_to(PROJECT).as_posix()
    except ValueError:
        return path.relative_to(REPO).as_posix()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("refusing to clobber existing result: {}".format(args.output))

    missing = [str(path) for path in AUDIT_FILES if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing audited inputs: " + ", ".join(missing))

    texts = {rel(path): path.read_text(encoding="utf-8", errors="strict") for path in AUDIT_FILES}
    runtime_text = "\n".join(
        text for name, text in texts.items()
        if name.startswith("Source/") or name.startswith("Config/")
    )
    all_text = "\n".join(texts.values())

    implemented = {}
    for name, patterns in IMPLEMENTED_CHECKS.items():
        implemented[name] = {
            "passed": all(re.search(pattern, runtime_text, re.MULTILINE) is not None for pattern in patterns),
            "patterns": list(patterns),
        }

    absent = {}
    for name, pattern in MISSING_RUNTIME_CHECKS.items():
        matches = sorted(set(re.findall(pattern, runtime_text, re.IGNORECASE | re.MULTILINE)))
        absent[name] = {
            "not_found_in_audited_runtime_source": not bool(matches),
            "pattern": pattern,
            "matches": matches,
        }

    adr = texts["ProjectKnowledge/decisions/ADR-0002-server-authoritative-warp-state-machine.md"]
    route = texts["ProjectKnowledge/systems/warp-route.red-mars-to-ring-01.yaml"]
    architecture = {
        "adr_accepted_not_started": "Accepted as architecture; implementation not started." in adr,
        "server_authoritative_states_recorded": all(
            state in adr for state in (
                "target", "validate", "spool", "align", "preload", "transit",
                "decelerate", "gravity_capture", "cooldown",
            )
        ),
        "route_retired_not_started": "status: retired_not_started" in route,
        "route_legacy_destination_retired": "status: retired_with_legacy_destination" in route,
    }

    protected = {}
    for path, expected in PROTECTED.items():
        actual = sha256(path)
        protected[rel(path)] = {"sha256": actual, "expected": expected, "match": actual == expected}

    result = {
        "schema_version": 1,
        "audit": "clean_redmmo_surface_to_orbit_warp_capability",
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "fixed clean RedMMO project-owned source/config plus canonical warp architecture records",
        "evidence_class": "offline_static_source_audit",
        "inputs": [{"path": rel(path), "sha256": sha256(path), "bytes": path.stat().st_size} for path in AUDIT_FILES],
        "implemented": implemented,
        "runtime_capabilities_not_found": absent,
        "architecture": architecture,
        "protected": protected,
        "summary": {
            "local_replicated_ship_flight_source_present": all(item["passed"] for item in implemented.values() if item is not implemented["night_space_calculation"]),
            "pure_night_space_calculation_source_present": implemented["night_space_calculation"]["passed"],
            "authoritative_warp_or_sector_runtime_found": any(not item["not_found_in_audited_runtime_source"] for key, item in absent.items() if key != "atmosphere_vacuum_flight_state"),
            "claim_limit": "Static source presence/absence only; no compile, Unreal runtime, visual, standalone, travel, replication, or multiplayer claim.",
        },
    }

    if not all(item["passed"] for item in implemented.values()):
        raise RuntimeError("one or more expected implemented source contracts were not found")
    if not all(item["not_found_in_audited_runtime_source"] for item in absent.values()):
        raise RuntimeError("unexpected candidate warp/travel runtime symbol found; manual review required")
    if not all(architecture.values()):
        raise RuntimeError("canonical warp architecture status/state contract drifted")
    if not all(item["match"] for item in protected.values()):
        raise RuntimeError("protected checkpoint hash mismatch")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "result": "pass",
        "output": str(args.output),
        "output_sha256": sha256(args.output),
        "implemented_checks": len(implemented),
        "absent_runtime_checks": len(absent),
        "protected_checks": len(protected),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
