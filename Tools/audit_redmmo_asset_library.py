"""Build a deterministic, read-only inventory of RED MMO Unreal content.

This scanner intentionally does not parse or modify Unreal packages. It records
package paths, sizes, naming signals, source ownership, basename collisions, and
candidate art-library categories. Every classification is explicitly provisional
until the package is decoded through Unreal's Asset Registry and reviewed by an
artist or technical artist.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTENT_ROOT = PROJECT_ROOT / "Content"
DEFAULT_PLUGINS_ROOT = PROJECT_ROOT / "Plugins"
DEFAULT_DIAGNOSTICS_ROOT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics")

PACKAGE_EXTENSIONS = frozenset({".uasset", ".umap"})
PROJECT_CONTENT_LABEL = "project_content"

REVIEW_PACK_NAMES = (
    "SoStylized",
    "StylizedDesertOasis",
    "AlienJungle",
    "TropicalAlienWorld",
    "Alien_Grass_Pack",
    "Alien_Plants_Pack",
)

ASSET_PREFIXES = (
    ("SKEL_", "Skeleton"),
    ("WBP_", "WidgetBlueprint"),
    ("ABP_", "AnimationBlueprint"),
    ("FXS_", "NiagaraSystem"),
    ("FXE_", "NiagaraEmitter"),
    ("FXF_", "NiagaraFunction"),
    ("PHYS_", "PhysicsAsset"),
    ("PPM_", "PostProcessMaterial"),
    ("HDR_", "HDRI"),
    ("RIG_", "Rig"),
    ("SNAP_", "LevelSnapshot"),
    ("MI_", "MaterialInstance"),
    ("SM_", "StaticMesh"),
    ("SK_", "SkeletalMesh"),
    ("BP_", "Blueprint"),
    ("FT_", "FoliageType"),
    ("PM_", "PhysicsMaterial"),
    ("M_", "Material"),
    ("T_", "Texture"),
    ("DA_", "DataAsset"),
    ("DT_", "DataTable"),
    ("CT_", "CurveTable"),
    ("E_", "Enum"),
)

CATEGORY_TERMS = {
    "Vegetation.Grass": {
        "grass",
        "blade",
        "lawn",
        "meadow",
        "groundcover",
        "ground",
    },
    "Vegetation.Tree": {
        "tree",
        "trunk",
        "branch",
        "canopy",
        "palm",
        "root",
    },
    "Vegetation.Plant": {
        "plant",
        "flower",
        "fern",
        "bush",
        "shrub",
        "reed",
        "cactus",
        "vine",
        "leaf",
        "leaves",
        "moss",
        "fungus",
        "mushroom",
    },
    "Geology": {
        "rock",
        "stone",
        "pebble",
        "boulder",
        "cliff",
        "cave",
        "crystal",
        "ore",
    },
    "Terrain.Surface": {
        "terrain",
        "landscape",
        "sand",
        "desert",
        "dirt",
        "soil",
        "mud",
        "snow",
    },
    "Water": {
        "water",
        "river",
        "lake",
        "ocean",
        "waterfall",
        "foam",
        "shore",
        "beach",
        "wet",
    },
    "Architecture": {
        "architecture",
        "building",
        "wall",
        "floor",
        "bridge",
        "door",
        "window",
        "column",
        "pillar",
        "platform",
    },
    "Prop": {
        "prop",
        "crate",
        "barrel",
        "furniture",
        "debris",
        "rubble",
        "fence",
        "sign",
    },
    "VFX": {
        "vfx",
        "fx",
        "niagara",
        "particle",
        "spark",
        "smoke",
        "mist",
        "dust",
        "fire",
    },
}


class AuditError(RuntimeError):
    """Raised when a complete, quiescent inventory cannot be produced."""


def _tokenize(value: str) -> set[str]:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return set(re.findall(r"[a-z0-9]+", separated.casefold()))


def infer_asset_type(asset_name: str, extension: str) -> tuple[str, str]:
    if extension.casefold() == ".umap":
        return "Map", ""
    upper_name = asset_name.upper()
    for prefix, asset_type in ASSET_PREFIXES:
        if upper_name.startswith(prefix):
            return asset_type, prefix
    return "Unknown", ""


def infer_candidate_categories(relative_path: Path, asset_type: str) -> list[str]:
    tokens: set[str] = set()
    for part in relative_path.parts:
        tokens.update(_tokenize(part))

    categories = [
        category
        for category, terms in CATEGORY_TERMS.items()
        if tokens.intersection(terms)
    ]
    if not categories:
        if asset_type in {"Material", "MaterialInstance", "Texture"}:
            categories.append("Art.Support")
        elif asset_type not in {"Map", "Unknown"}:
            categories.append("Uncategorized")
    return sorted(categories)


def _project_source_kind(top_level_root: str) -> str:
    if top_level_root == "RedMMO":
        return "project_owned"
    if top_level_root in {"__ExternalActors__", "__ExternalObjects__"}:
        return "world_partition_external"
    if top_level_root == "Developers":
        return "developer_sandbox"
    if top_level_root == "Collections":
        return "content_browser_metadata"
    return "vendor_or_sample"


def _package_paths(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if not root.is_dir():
        raise AuditError(f"content root is not a directory: {root}")
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.casefold() in PACKAGE_EXTENSIONS
    )


def _discover_sources(
    content_root: Path,
    plugins_root: Path,
) -> list[tuple[str, Path, str, str | None]]:
    sources: list[tuple[str, Path, str, str | None]] = [
        (PROJECT_CONTENT_LABEL, content_root, "/Game", None)
    ]
    if plugins_root.exists():
        if not plugins_root.is_dir():
            raise AuditError(f"plugins root is not a directory: {plugins_root}")
        for plugin_dir in sorted(
            (path for path in plugins_root.iterdir() if path.is_dir()),
            key=lambda path: path.name.casefold(),
        ):
            plugin_content = plugin_dir / "Content"
            if plugin_content.is_dir():
                sources.append(
                    (
                        f"plugin:{plugin_dir.name}",
                        plugin_content,
                        f"/{plugin_dir.name}",
                        plugin_dir.name,
                    )
                )
    return sources


def _inventory_paths(
    sources: Iterable[tuple[str, Path, str, str | None]],
) -> list[tuple[str, Path, str, str | None, Path]]:
    inventory: list[tuple[str, Path, str, str | None, Path]] = []
    for label, root, mount, plugin_name in sources:
        inventory.extend(
            (label, root, mount, plugin_name, path)
            for path in _package_paths(root)
        )
    return sorted(
        inventory,
        key=lambda item: (item[0].casefold(), item[4].as_posix().casefold()),
    )


def _snapshot(
    inventory: Iterable[tuple[str, Path, str, str | None, Path]],
) -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    try:
        for label, root, _, _, path in inventory:
            stat = path.stat()
            key = f"{label}/{path.relative_to(root).as_posix()}"
            snapshot[key] = (stat.st_size, stat.st_mtime_ns)
    except OSError as exc:
        raise AuditError(f"unable to snapshot package inventory: {exc}") from exc
    return snapshot


def _record_for_package(
    label: str,
    root: Path,
    mount: str,
    plugin_name: str | None,
    path: Path,
) -> dict[str, object]:
    relative = path.relative_to(root)
    relative_no_suffix = relative.with_suffix("")
    package_path = f"{mount.rstrip('/')}/{relative_no_suffix.as_posix()}"
    asset_name = path.stem
    asset_type, prefix = infer_asset_type(asset_name, path.suffix)

    if label == PROJECT_CONTENT_LABEL:
        top_level_root = relative.parts[0]
        source_kind = _project_source_kind(top_level_root)
        library_root = top_level_root
    else:
        top_level_root = plugin_name or label
        source_kind = "plugin_content"
        library_root = top_level_root

    return {
        "package_path": package_path,
        "disk_relative_path": (
            f"Content/{relative.as_posix()}"
            if label == PROJECT_CONTENT_LABEL
            else f"Plugins/{plugin_name}/Content/{relative.as_posix()}"
        ),
        "source_label": label,
        "source_kind": source_kind,
        "library_root": library_root,
        "asset_name": asset_name,
        "package_type": "map" if path.suffix.casefold() == ".umap" else "asset",
        "inferred_asset_type": asset_type,
        "recognized_prefix": prefix,
        "candidate_categories": infer_candidate_categories(relative, asset_type),
        "size_bytes": path.stat().st_size,
        "review_status": "unreviewed_inventory_candidate",
        "requires_unreal_asset_registry_decode": True,
    }


def _root_summaries(records: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for record in records:
        key = (
            str(record["source_label"]),
            str(record["library_root"]),
            str(record["source_kind"]),
        )
        grouped[key].append(record)

    summaries: list[dict[str, object]] = []
    for (source_label, library_root, source_kind), members in sorted(
        grouped.items(),
        key=lambda item: (item[0][0].casefold(), item[0][1].casefold()),
    ):
        assets = [member for member in members if member["package_type"] == "asset"]
        summaries.append(
            {
                "source_label": source_label,
                "library_root": library_root,
                "source_kind": source_kind,
                "package_count": len(members),
                "asset_count": len(assets),
                "map_count": len(members) - len(assets),
                "size_bytes": sum(int(member["size_bytes"]) for member in members),
                "recognized_prefix_asset_count": sum(
                    bool(member["recognized_prefix"]) for member in assets
                ),
                "unknown_type_asset_count": sum(
                    member["inferred_asset_type"] == "Unknown" for member in assets
                ),
            }
        )
    return summaries


def _collision_groups(records: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in records:
        if record["package_type"] == "asset":
            grouped[str(record["asset_name"]).casefold()].append(record)

    collisions: list[dict[str, object]] = []
    for normalized_name, members in grouped.items():
        package_paths = sorted(str(member["package_path"]) for member in members)
        if len(package_paths) > 1:
            collisions.append(
                {
                    "normalized_asset_name": normalized_name,
                    "package_count": len(package_paths),
                    "library_roots": sorted(
                        {str(member["library_root"]) for member in members}
                    ),
                    "package_paths": package_paths,
                }
            )
    return sorted(
        collisions,
        key=lambda collision: (
            -int(collision["package_count"]),
            str(collision["normalized_asset_name"]),
        ),
    )


def build_report(
    content_root: Path = DEFAULT_CONTENT_ROOT,
    plugins_root: Path = DEFAULT_PLUGINS_ROOT,
) -> dict[str, object]:
    content_root = content_root.resolve()
    plugins_root = plugins_root.resolve()
    if not content_root.is_dir():
        raise AuditError(f"project Content root is missing: {content_root}")

    sources = _discover_sources(content_root, plugins_root)
    inventory_before = _inventory_paths(sources)
    if not inventory_before:
        raise AuditError("no Unreal packages were found")
    snapshot_before = _snapshot(inventory_before)
    records = [
        _record_for_package(label, root, mount, plugin_name, path)
        for label, root, mount, plugin_name, path in inventory_before
    ]
    inventory_after = _inventory_paths(sources)
    snapshot_after = _snapshot(inventory_after)
    if snapshot_before != snapshot_after:
        raise AuditError(
            "the Unreal package tree changed during the inventory; retry when quiescent"
        )

    collisions = _collision_groups(records)
    root_summaries = _root_summaries(records)
    summary_by_root = {
        str(summary["library_root"]): summary
        for summary in root_summaries
        if summary["source_label"] == PROJECT_CONTENT_LABEL
    }
    selected_pack_summary = []
    for pack_name in REVIEW_PACK_NAMES:
        summary = summary_by_root.get(pack_name)
        selected_pack_summary.append(
            {
                "library_root": pack_name,
                "present": summary is not None,
                "package_count": int(summary["package_count"]) if summary else 0,
                "size_bytes": int(summary["size_bytes"]) if summary else 0,
            }
        )

    signature = hashlib.sha256()
    for record in sorted(records, key=lambda item: str(item["package_path"]).casefold()):
        signature.update(
            (
                f"{record['package_path']}|{record['size_bytes']}|"
                f"{record['package_type']}\n"
            ).encode("utf-8")
        )

    asset_records = [
        record for record in records if record["package_type"] == "asset"
    ]
    type_counts = Counter(
        str(record["inferred_asset_type"]) for record in asset_records
    )
    source_kind_counts = Counter(str(record["source_kind"]) for record in records)
    collision_member_count = sum(
        int(collision["package_count"]) for collision in collisions
    )

    return {
        "schema_version": 1,
        "audit_id": "redmmo-asset-library-inventory",
        "evidence_class": "static",
        "provenance": {
            "scanner_path": "Tools/audit_redmmo_asset_library.py",
            "scanner_sha256": hashlib.sha256(Path(__file__).read_bytes())
            .hexdigest()
            .upper(),
            "inventory_signature_kind": "sorted-package-path-size-type",
            "inventory_signature_sha256": signature.hexdigest().upper(),
        },
        "scope": {
            "content_root": content_root.as_posix(),
            "plugins_root": plugins_root.as_posix(),
            "package_extensions": sorted(PACKAGE_EXTENSIONS),
            "package_count": len(records),
            "asset_count": len(asset_records),
            "map_count": len(records) - len(asset_records),
            "bytes_inventoried": sum(int(record["size_bytes"]) for record in records),
            "tree_quiescent_during_scan": True,
            "source_kind_package_counts": dict(sorted(source_kind_counts.items())),
            "inferred_asset_type_counts": dict(sorted(type_counts.items())),
            "recognized_prefix_asset_count": sum(
                bool(record["recognized_prefix"]) for record in asset_records
            ),
            "unknown_type_asset_count": sum(
                record["inferred_asset_type"] == "Unknown"
                for record in asset_records
            ),
            "basename_collision_group_count": len(collisions),
            "basename_collision_package_count": collision_member_count,
        },
        "method": {
            "mutates_unreal_packages": False,
            "classification_status": "candidate_only",
            "limitations": [
                "Package payloads are not decoded and package contents are not hashed.",
                "Filename prefixes and path tokens cannot prove Unreal asset class or intended use.",
                "Vendor ownership and license rights are not inferred from folder names.",
                "Approval, PBR readiness, LOD, Nanite, collision, shader, and runtime cost require Unreal review.",
                "Physical moves and renames must be performed through Unreal with dependency and redirector validation.",
            ],
        },
        "selected_art_pack_summary": selected_pack_summary,
        "library_roots": root_summaries,
        "basename_collisions": collisions,
        "packages": records,
    }


def report_bytes(report: dict[str, object]) -> bytes:
    return (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")


def validate_output_path(
    output_path: Path,
    *,
    diagnostics_root: Path = DEFAULT_DIAGNOSTICS_ROOT,
) -> Path:
    resolved_output = output_path.resolve()
    resolved_root = diagnostics_root.resolve()
    if resolved_output.suffix.casefold() != ".json":
        raise AuditError(f"output must use a .json suffix: {resolved_output}")
    try:
        resolved_output.relative_to(resolved_root)
    except ValueError as exc:
        raise AuditError(
            f"output is restricted to diagnostics root {resolved_root}: "
            f"{resolved_output}"
        ) from exc
    return resolved_output


def write_report_atomic(output_path: Path, payload: bytes) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f"{output_path.name}.",
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Write the deterministic JSON report under the diagnostics root.",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output_path = validate_output_path(args.output)
    report = build_report()
    write_report_atomic(output_path, report_bytes(report))
    scope = report["scope"]
    print(
        "REDMMO_ASSET_LIBRARY_AUDIT_OK "
        f"packages={scope['package_count']} "
        f"assets={scope['asset_count']} "
        f"maps={scope['map_count']} "
        f"collision_groups={scope['basename_collision_group_count']} "
        f"report={output_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AuditError as error:
        print(f"REDMMO_ASSET_LIBRARY_AUDIT_FAILED {error}", file=os.sys.stderr)
        raise SystemExit(2)
