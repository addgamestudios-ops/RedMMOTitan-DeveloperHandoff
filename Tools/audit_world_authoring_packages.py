"""Read-only serialized-package marker inventory for RED world authoring.

This audit deliberately does not load Unreal or mutate any package. It scans the
project-owned ``Content/RedMMO`` package bytes (and split-package sidecars) for
exact ASCII and UTF-16LE names that would normally be present in Unreal name,
import, or export tables when PCG, WorldGen, palette approval, manual protection,
or procedural-dressing policy is serialized.

Absence of a marker is static evidence only. It cannot prove decoded property
values, actor enablement, runtime construction, editor-only state, or visual
placement behavior; those require Asset Registry/editor/runtime acceptance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTENT_ROOT = PROJECT_ROOT / "Content" / "RedMMO"
DEFAULT_EXTERNAL_ACTOR_ROOT = PROJECT_ROOT / "Content" / "__ExternalActors__" / "RedMMO"
DEFAULT_EXTERNAL_OBJECT_ROOT = PROJECT_ROOT / "Content" / "__ExternalObjects__" / "RedMMO"
DEFAULT_DIAGNOSTICS_ROOT = Path("D:/RedMMOTitanWindowsData/Diagnostics")
PACKAGE_EXTENSIONS = {".uasset", ".umap"}
SIDECAR_SUFFIXES = (".uexp", ".ubulk", ".uptnl", ".m.ubulk", ".upayload")
SCAN_CHUNK_BYTES = 4 * 1024 * 1024
PROTECTED_MAP_RELATIVE = Path("Maps") / "RedPlanetGen_50km_Test.umap"
PROTECTED_MAP_SHA256 = (
    "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D"
)

# Precise class/module/property names. Generic "PCG" or "WorldGen" substrings
# are intentionally excluded from strong results because category/display names
# can survive in a package without a serialized plugin actor or asset reference.
STRONG_MARKER_GROUPS: dict[str, tuple[str, ...]] = {
    "pcg_runtime_reference": (
        "/Script/PCG",
        "PCGComponent",
        "PCGGraph",
        "PCGVolume",
        "PCGWorldActor",
        "PCGDataAsset",
    ),
    "worldgen_runtime_reference": (
        "/Script/WorldGen",
        "WorldGenerator",
        "WorldStreamingManager",
        "WorldGenExclusionVolume",
        "WorldGenSpawnerAsset",
        "WorldGenSettlementAsset",
        "WorldGenRoadAsset",
        "WorldGenRiverAsset",
        "WorldGenGrassAsset",
        "BiomeFoliageAsset",
        "RiverNetwork",
        "RoadNetwork",
        "WorldChunk",
    ),
    "palette_pcg_policy_marker": (
        "/Script/RedMMO.RedWorldAssetPalette",
        "RedWorldAssetPalette",
        "bApprovedForPCG",
        "bHandPlacementOnly",
    ),
    "manual_protection_marker": (
        "RedManualPlacementProtectionComponent",
        "ManualPlacementProtection",
    ),
    "dressing_policy_marker": (
        "bSuppressProceduralSurfaceDressing",
        "bSuppressAllProceduralDressing",
    ),
}

WEAK_MARKER_GROUPS: dict[str, tuple[str, ...]] = {
    "worldgen_label_only": (
        "WorldGen|Noise",
        "EWorldGenNoiseType",
    ),
}


class AuditError(RuntimeError):
    """Raised when the audit cannot make a complete fail-closed inventory."""


def _encoded_markers(
    marker_groups: dict[str, tuple[str, ...]],
) -> tuple[tuple[str, str, str, bytes], ...]:
    encoded: list[tuple[str, str, str, bytes]] = []
    for group, markers in marker_groups.items():
        for marker in markers:
            encoded.append((group, marker, "ascii", marker.encode("ascii")))
            encoded.append((group, marker, "utf-16-le", marker.encode("utf-16-le")))
    return tuple(encoded)


STRONG_ENCODED_MARKERS = _encoded_markers(STRONG_MARKER_GROUPS)
WEAK_ENCODED_MARKERS = _encoded_markers(WEAK_MARKER_GROUPS)
ALL_ENCODED_MARKERS = STRONG_ENCODED_MARKERS + WEAK_ENCODED_MARKERS
MAX_ENCODED_MARKER_LENGTH = max(len(item[3]) for item in ALL_ENCODED_MARKERS)


def _is_identifier_byte(value: int) -> bool:
    return (
        value == ord("_")
        or ord("0") <= value <= ord("9")
        or ord("A") <= value <= ord("Z")
        or ord("a") <= value <= ord("z")
    )


def _contains_exact_marker(
    window: bytes,
    encoded: bytes,
    encoding: str,
    *,
    final_window: bool,
) -> bool:
    start = 0
    while True:
        index = window.find(encoded, start)
        if index < 0:
            return False
        end = index + len(encoded)
        if encoding == "ascii":
            if not final_window and end >= len(window):
                return False
            before_is_identifier = (
                _is_identifier_byte(encoded[0])
                and index > 0
                and _is_identifier_byte(window[index - 1])
            )
            after_is_identifier = (
                _is_identifier_byte(encoded[-1])
                and end < len(window)
                and _is_identifier_byte(window[end])
            )
        else:
            if not final_window and end + 1 >= len(window):
                return False
            before_is_identifier = (
                _is_identifier_byte(encoded[0])
                and index >= 2
                and window[index - 1] == 0
                and _is_identifier_byte(window[index - 2])
            )
            after_is_identifier = (
                _is_identifier_byte(encoded[-2])
                and end + 1 < len(window)
                and window[end + 1] == 0
                and _is_identifier_byte(window[end])
            )
        if not before_is_identifier and not after_is_identifier:
            return True
        start = index + 1


def _scan_file(path: Path) -> tuple[str, int, dict[str, set[str]], dict[str, set[str]]]:
    digest = hashlib.sha256()
    size_bytes = 0
    strong_hits: dict[str, set[str]] = {}
    weak_hits: dict[str, set[str]] = {}
    tail = b""
    try:
        with path.open("rb") as handle:
            chunk = handle.read(SCAN_CHUNK_BYTES)
            while chunk:
                next_chunk = handle.read(SCAN_CHUNK_BYTES)
                digest.update(chunk)
                size_bytes += len(chunk)
                window = tail + chunk
                final_window = not next_chunk
                for group, marker, encoding, encoded in STRONG_ENCODED_MARKERS:
                    if marker not in strong_hits.get(group, set()) and _contains_exact_marker(
                        window, encoded, encoding, final_window=final_window
                    ):
                        strong_hits.setdefault(group, set()).add(marker)
                for group, marker, encoding, encoded in WEAK_ENCODED_MARKERS:
                    if marker not in weak_hits.get(group, set()) and _contains_exact_marker(
                        window, encoded, encoding, final_window=final_window
                    ):
                        weak_hits.setdefault(group, set()).add(marker)
                tail = window[-(MAX_ENCODED_MARKER_LENGTH + 2) :]
                chunk = next_chunk
    except OSError as exc:
        raise AuditError(f"unable to read serialized package payload {path}: {exc}") from exc
    return digest.hexdigest().upper(), size_bytes, strong_hits, weak_hits


def _merge_hits(target: dict[str, set[str]], source: dict[str, set[str]]) -> None:
    for group, markers in source.items():
        target.setdefault(group, set()).update(markers)


def _payload_paths(package_path: Path) -> tuple[Path, ...]:
    payloads = [package_path]
    for suffix in SIDECAR_SUFFIXES:
        sidecar = package_path.with_suffix(suffix)
        if sidecar.exists():
            if not sidecar.is_file():
                raise AuditError(f"serialized package sidecar is not a file: {sidecar}")
            payloads.append(sidecar)
    return tuple(payloads)


def _sorted_hit_dict(hits: dict[str, set[str]]) -> dict[str, list[str]]:
    return {group: sorted(markers) for group, markers in sorted(hits.items())}


def _scan_package(package_path: Path, content_root: Path, root_label: str) -> dict[str, object]:
    strong_hits: dict[str, set[str]] = {}
    weak_hits: dict[str, set[str]] = {}
    payload_records: list[dict[str, object]] = []
    for payload_path in _payload_paths(package_path):
        sha256, size_bytes, payload_strong, payload_weak = _scan_file(payload_path)
        _merge_hits(strong_hits, payload_strong)
        _merge_hits(weak_hits, payload_weak)
        payload_records.append(
            {
                "relative_path": (
                    f"{root_label}/{payload_path.relative_to(content_root).as_posix()}"
                ),
                "sha256": sha256,
                "size_bytes": size_bytes,
            }
        )

    return {
        "package_path": f"{root_label}/{package_path.relative_to(content_root).as_posix()}",
        "source_root": root_label,
        "package_type": "map" if package_path.suffix.lower() == ".umap" else "asset",
        "payloads": payload_records,
        "strong_marker_groups": _sorted_hit_dict(strong_hits),
        "weak_marker_groups": _sorted_hit_dict(weak_hits),
    }


def _package_paths(content_root: Path, *, required: bool) -> list[Path]:
    if not content_root.exists() or not content_root.is_dir():
        if required:
            raise AuditError(
                f"content root does not exist or is not a directory: {content_root}"
            )
        return []
    packages = sorted(
        path
        for path in content_root.rglob("*")
        if path.is_file() and path.suffix.lower() in PACKAGE_EXTENSIONS
    )
    if not packages and required:
        raise AuditError(f"no .umap or .uasset packages found under {content_root}")
    return packages


def _collect_inventory(
    roots: tuple[tuple[str, Path, bool], ...],
) -> list[tuple[str, Path, Path]]:
    inventory: list[tuple[str, Path, Path]] = []
    for root_label, root_path, required in roots:
        inventory.extend(
            (root_label, root_path, package_path)
            for package_path in _package_paths(root_path, required=required)
        )
    return sorted(inventory, key=lambda item: (item[0], item[2].as_posix()))


def _inventory_snapshot(
    inventory: list[tuple[str, Path, Path]],
) -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    try:
        for root_label, root_path, package_path in inventory:
            for payload_path in _payload_paths(package_path):
                stat = payload_path.stat()
                key = f"{root_label}/{payload_path.relative_to(root_path).as_posix()}"
                snapshot[key] = (stat.st_size, stat.st_mtime_ns)
    except OSError as exc:
        raise AuditError(f"unable to snapshot serialized package tree: {exc}") from exc
    return snapshot


def _git_head() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    return result.stdout.strip()


def build_report(
    content_root: Path,
    *,
    additional_roots: Iterable[tuple[str, Path]] = (),
    protected_relative: Path | None = None,
    protected_sha256: str | None = None,
    protected_sidecar_sha256: dict[str, str] | None = None,
) -> dict[str, object]:
    content_root = content_root.resolve()
    roots: list[tuple[str, Path, bool]] = [
        ("project_content", content_root, True),
        *((label, path.resolve(), False) for label, path in additional_roots),
    ]
    labels = [label for label, _, _ in roots]
    if len(labels) != len(set(labels)):
        raise AuditError(f"scan-root labels must be unique: {labels}")

    root_tuple = tuple(roots)
    inventory_before = _collect_inventory(root_tuple)
    snapshot_before = _inventory_snapshot(inventory_before)
    packages = [
        _scan_package(package_path, root_path, root_label)
        for root_label, root_path, package_path in inventory_before
    ]
    inventory_after = _collect_inventory(root_tuple)
    snapshot_after = _inventory_snapshot(inventory_after)
    if snapshot_after != snapshot_before:
        raise AuditError(
            "serialized package tree changed while it was being scanned; retry when quiescent"
        )

    group_package_counts = {
        group: sum(group in package["strong_marker_groups"] for package in packages)
        for group in STRONG_MARKER_GROUPS
    }
    weak_group_package_counts = {
        group: sum(group in package["weak_marker_groups"] for package in packages)
        for group in WEAK_MARKER_GROUPS
    }
    payload_count = sum(len(package["payloads"]) for package in packages)
    bytes_scanned = sum(
        payload["size_bytes"]
        for package in packages
        for payload in package["payloads"]
    )

    protected_record: dict[str, object] | None = None
    if protected_relative is not None:
        protected_name = f"project_content/{protected_relative.as_posix()}"
        protected_package = next(
            (package for package in packages if package["package_path"] == protected_name),
            None,
        )
        if protected_package is None:
            raise AuditError(f"protected package is missing from inventory: {protected_name}")
        actual_payloads = {
            payload["relative_path"]: payload["sha256"]
            for payload in protected_package["payloads"]
        }
        expected_payloads: dict[str, str] = {}
        if protected_sha256:
            expected_payloads[protected_name] = protected_sha256.upper()
        for suffix, sha256 in (protected_sidecar_sha256 or {}).items():
            if suffix not in SIDECAR_SUFFIXES:
                raise AuditError(f"unsupported protected sidecar suffix: {suffix}")
            sidecar_name = Path(protected_name).with_suffix(suffix).as_posix()
            expected_payloads[sidecar_name] = sha256.upper()
        if expected_payloads and set(actual_payloads) != set(expected_payloads):
            raise AuditError(
                "protected package payload manifest drift: "
                f"expected {sorted(expected_payloads)} got {sorted(actual_payloads)}"
            )
        for payload_name, expected_sha256 in expected_payloads.items():
            if actual_payloads[payload_name] != expected_sha256:
                raise AuditError(
                    "protected package hash drift: "
                    f"{payload_name} expected {expected_sha256} "
                    f"got {actual_payloads[payload_name]}"
                )
        protected_record = {
            "package_path": protected_name,
            "payload_sha256": actual_payloads,
            "matches_expected_manifest": not expected_payloads
            or actual_payloads == expected_payloads,
        }

    root_records: list[dict[str, object]] = []
    for root_label, root_path, required in roots:
        try:
            reported_root = root_path.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            reported_root = root_path.as_posix()
        root_records.append(
            {
                "label": root_label,
                "path": reported_root,
                "required": required,
                "exists": root_path.is_dir(),
                "package_count": sum(
                    package["source_root"] == root_label for package in packages
                ),
            }
        )

    runtime_groups = {"pcg_runtime_reference", "worldgen_runtime_reference"}
    policy_groups = {
        "palette_pcg_policy_marker",
        "manual_protection_marker",
        "dressing_policy_marker",
    }
    runtime_reference_package_count = sum(
        bool(runtime_groups.intersection(package["strong_marker_groups"]))
        for package in packages
    )
    policy_marker_package_count = sum(
        bool(policy_groups.intersection(package["strong_marker_groups"]))
        for package in packages
    )

    return {
        "schema_version": 1,
        "audit_id": "redmmo-world-authoring-serialized-package-inventory",
        "evidence_class": "static",
        "provenance": {
            "scanner_path": "Tools/audit_world_authoring_packages.py",
            "scanner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest().upper(),
            "project_git_head": _git_head(),
            "invocation": "python Tools/audit_world_authoring_packages.py --output <diagnostics-report.json>",
        },
        "scope": {
            "roots": root_records,
            "package_extensions": sorted(PACKAGE_EXTENSIONS),
            "package_count": len(packages),
            "map_count": sum(package["package_type"] == "map" for package in packages),
            "asset_count": sum(package["package_type"] == "asset" for package in packages),
            "payload_count": payload_count,
            "sidecar_count": payload_count - len(packages),
            "bytes_scanned": bytes_scanned,
            "tree_quiescent_during_scan": True,
        },
        "method": {
            "ascii_and_utf16le_exact_marker_scan": True,
            "split_package_sidecars_included": list(SIDECAR_SUFFIXES),
            "mutates_serialized_packages": False,
            "limitations": [
                "Marker absence is not a decoded Unreal property-value audit.",
                "This scan cannot prove actor enabled state, runtime construction, editor-only state, or visual placement.",
                "Default-valued native properties may be absent from serialized bytes.",
                "Soft dependencies, renamed Blueprint types, Data Layers, and plugin-created runtime objects may not match selected markers.",
                "Asset Registry or editor/runtime evidence is required before enabling PCG, WorldGen, or surface dressing.",
            ],
        },
        "summary": {
            "strong_marker_package_counts": group_package_counts,
            "weak_marker_package_counts": weak_group_package_counts,
            "runtime_reference_package_count": runtime_reference_package_count,
            "policy_marker_package_count": policy_marker_package_count,
        },
        "protected_checkpoint": protected_record,
        "packages": packages,
    }


def report_bytes(report: dict[str, object]) -> bytes:
    return (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_report_atomic(output_path: Path, payload: bytes) -> None:
    output_path = output_path.resolve()
    if output_path.suffix.lower() != ".json":
        raise AuditError(f"audit report output must use a .json suffix: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=output_path.name + ".",
        suffix=".tmp",
        dir=output_path.parent,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, output_path)
    finally:
        temporary_path = Path(temporary_name)
        if temporary_path.exists():
            temporary_path.unlink()


def validate_diagnostics_report_path(
    report_path: Path,
    *,
    diagnostics_root: Path = DEFAULT_DIAGNOSTICS_ROOT,
) -> Path:
    resolved_path = report_path.resolve()
    resolved_root = diagnostics_root.resolve()
    if resolved_path.suffix.lower() != ".json":
        raise AuditError(f"audit report path must use a .json suffix: {resolved_path}")
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise AuditError(
            f"audit reports are restricted to diagnostics root {resolved_root}: {resolved_path}"
        ) from exc
    return resolved_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument("--output", type=Path, help="Atomically write the JSON report.")
    output_group.add_argument(
        "--check",
        type=Path,
        help="Require an existing JSON report to match the deterministic live scan.",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = build_report(
        DEFAULT_CONTENT_ROOT,
        additional_roots=(
            ("external_actors", DEFAULT_EXTERNAL_ACTOR_ROOT),
            ("external_objects", DEFAULT_EXTERNAL_OBJECT_ROOT),
        ),
        protected_relative=PROTECTED_MAP_RELATIVE,
        protected_sha256=PROTECTED_MAP_SHA256,
        protected_sidecar_sha256={},
    )
    payload = report_bytes(report)
    if args.check:
        check_path = validate_diagnostics_report_path(args.check)
        try:
            current = check_path.read_bytes()
        except OSError as exc:
            raise AuditError(f"unable to read report for --check: {check_path}: {exc}") from exc
        if current != payload:
            raise AuditError(f"serialized package audit report is stale: {check_path}")
    elif args.output:
        output_path = validate_diagnostics_report_path(args.output)
        write_report_atomic(output_path, payload)
    else:
        print(payload.decode("utf-8"), end="")

    summary = report["summary"]
    scope = report["scope"]
    print(
        "RED_WORLD_AUTHORING_PACKAGE_AUDIT_OK "
        f"packages={scope['package_count']} "
        f"runtime_refs={summary['runtime_reference_package_count']} "
        f"policy_markers={summary['policy_marker_package_count']}",
        file=os.sys.stderr if not (args.output or args.check) else os.sys.stdout,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AuditError as error:
        print(f"RED_WORLD_AUTHORING_PACKAGE_AUDIT_FAILED {error}", file=os.sys.stderr)
        raise SystemExit(2)
