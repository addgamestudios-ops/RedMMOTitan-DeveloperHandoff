"""Export catalog candidates for RED MMO's six priority art libraries.

Run this script through Unreal Engine 5.8's PythonScript commandlet. It reads
only Asset Registry metadata, never loads an asset UObject, and writes only one
JSON report below the external diagnostics root. The result is a curation input,
not an approval, license decision, package move, or visual/performance claim.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence


DEFAULT_DIAGNOSTICS_ROOT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics")
OUTPUT_ENVIRONMENT_VARIABLE = "REDMMO_ASSET_REGISTRY_OUTPUT"

PRIORITY_LIBRARY_ROOTS = (
    "/Game/SoStylized",
    "/Game/StylizedDesertOasis",
    "/Game/AlienJungle",
    "/Game/TropicalAlienWorld",
    "/Game/Alien_Grass_Pack",
    "/Game/Alien_Plants_Pack",
)

# These tags are useful when present and cheap to read from FAssetData. Their
# presence varies by class and engine version, so absence is never treated as
# evidence that a feature is disabled.
CURATION_TAGS = (
    "BlueprintType",
    "CollisionPrims",
    "Dimensions",
    "GeneratedClass",
    "HasNavigationData",
    "IsNaniteEnabled",
    "LODGroup",
    "MaterialDomain",
    "NativeParentClass",
    "NumLODs",
    "NumMaterials",
    "Parent",
    "Skeleton",
)

ROLE_TERMS = {
    "Vegetation.Grass": {"grass", "blade", "lawn", "meadow", "groundcover"},
    "Vegetation.Tree": {"tree", "trunk", "branch", "canopy", "palm", "root"},
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
    "Geology": {"rock", "stone", "pebble", "boulder", "cliff", "crystal", "ore"},
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
    "VFX": {"vfx", "fx", "niagara", "particle", "spark", "smoke", "mist", "dust"},
}


class CatalogExportError(RuntimeError):
    """Raised when a complete read-only Asset Registry export is impossible."""


def _tokens(value: str) -> set[str]:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return set(re.findall(r"[a-z0-9]+", separated.casefold()))


def infer_candidate_roles(package_name: str, asset_class_path: str) -> list[str]:
    """Return provisional roles from path/class tokens without claiming approval."""

    tokens = _tokens(package_name)
    roles = [
        role for role, terms in ROLE_TERMS.items() if tokens.intersection(terms)
    ]
    class_name = asset_class_path.rsplit(".", 1)[-1]
    if class_name in {"Material", "MaterialInstanceConstant", "Texture2D"}:
        roles.append("Art.Support")
    elif class_name in {"StaticMesh", "SkeletalMesh"} and not roles:
        roles.append("Uncategorized.Mesh")
    elif class_name in {"World", "Level"}:
        roles.append("Reference.Map")
    return sorted(set(roles))


def canonical_top_level_asset_path(value: object) -> str:
    """Serialize UE's FTopLevelAssetPath without debug-wrapper/pointer text."""

    if isinstance(value, str):
        if re.fullmatch(r"/[A-Za-z0-9_./-]+\.[A-Za-z0-9_]+", value):
            return value
        raise CatalogExportError(f"invalid asset class path string: {value!r}")
    package_name = str(getattr(value, "package_name", "")).strip()
    asset_name = str(getattr(value, "asset_name", "")).strip()
    canonical = f"{package_name}.{asset_name}"
    if not re.fullmatch(r"/[A-Za-z0-9_./-]+\.[A-Za-z0-9_]+", canonical):
        raise CatalogExportError(
            "FTopLevelAssetPath did not expose canonical package_name and asset_name"
        )
    return canonical


def _library_root_for_package(package_name: str) -> str:
    matches = [
        root
        for root in PRIORITY_LIBRARY_ROOTS
        if package_name == root or package_name.startswith(root + "/")
    ]
    if len(matches) != 1:
        raise CatalogExportError(
            f"package is outside the six priority roots: {package_name}"
        )
    return matches[0]


def normalize_record(
    *,
    package_name: str,
    package_path: str,
    asset_name: str,
    asset_class_path: str,
    registry_tags: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Normalize one FAssetData-like record into the candidate schema."""

    if not package_name.startswith("/Game/"):
        raise CatalogExportError(f"unexpected non-project package: {package_name}")
    library_root = _library_root_for_package(package_name)
    tags = {
        str(key): str(value)
        for key, value in sorted((registry_tags or {}).items())
        if str(value)
    }
    return {
        "stable_candidate_id": hashlib.sha256(
            f"{package_name}.{asset_name}".encode("utf-8")
        ).hexdigest()[:24].upper(),
        "library_root": library_root,
        "package_name": package_name,
        "package_path": package_path,
        "asset_name": asset_name,
        "object_path": f"{package_name}.{asset_name}",
        "asset_class_path": asset_class_path,
        "registry_tags": tags,
        "candidate_roles": infer_candidate_roles(package_name, asset_class_path),
        "source_policy": "vendor_source_immutable",
        "review_status": "unreviewed_asset_registry_candidate",
        "requires_license_review": True,
        "requires_visual_and_performance_review": True,
    }


def build_report(
    records: Iterable[Mapping[str, object]],
    *,
    engine_version: str,
    project_file: str,
) -> dict[str, object]:
    """Build a deterministic report from normalized candidate records."""

    normalized = [dict(record) for record in records]
    normalized.sort(
        key=lambda record: (
            str(record["package_name"]).casefold(),
            str(record["asset_name"]).casefold(),
        )
    )
    object_paths = [str(record["object_path"]) for record in normalized]
    if len(object_paths) != len(set(object_paths)):
        raise CatalogExportError("duplicate object paths returned by Asset Registry")

    root_counts = Counter(str(record["library_root"]) for record in normalized)
    missing_roots = [
        root for root in PRIORITY_LIBRARY_ROOTS if root_counts.get(root, 0) == 0
    ]
    if missing_roots:
        raise CatalogExportError(
            "Asset Registry returned no candidates for: " + ", ".join(missing_roots)
        )

    class_counts = Counter(str(record["asset_class_path"]) for record in normalized)
    basenames: dict[str, list[str]] = defaultdict(list)
    for record in normalized:
        basenames[str(record["asset_name"]).casefold()].append(
            str(record["object_path"])
        )
    collisions = [
        {
            "normalized_asset_name": name,
            "object_paths": sorted(paths),
            "candidate_count": len(paths),
        }
        for name, paths in basenames.items()
        if len(paths) > 1
    ]
    collisions.sort(
        key=lambda collision: (
            -int(collision["candidate_count"]),
            str(collision["normalized_asset_name"]),
        )
    )

    return {
        "schema_version": 1,
        "audit_id": "redmmo-unreal-asset-registry-catalog-candidates",
        "evidence_class": "static",
        "status": "candidate_only",
        "engine": {
            "version": engine_version,
            "project_file": project_file.replace("\\", "/"),
        },
        "scope": {
            "library_roots": list(PRIORITY_LIBRARY_ROOTS),
            "candidate_count": len(normalized),
            "root_candidate_counts": {
                root: root_counts[root] for root in PRIORITY_LIBRARY_ROOTS
            },
            "asset_class_counts": dict(sorted(class_counts.items())),
            "duplicate_basename_group_count": len(collisions),
        },
        "method": {
            "source": "Unreal Engine 5.8 Asset Registry FAssetData",
            "recursive": True,
            "include_only_on_disk_assets": True,
            "loads_asset_uobjects": False,
            "mutates_unreal_packages": False,
            "moves_or_renames_packages": False,
            "writes_project_content": False,
            "writes_external_diagnostics_only": True,
        },
        "limitations": [
            "Candidates are not approved assets or proof of redistribution rights.",
            "Asset Registry tags vary by asset class and do not replace visual review.",
            "No package is loaded, so geometry bounds, material graphs, texture pixels, collision quality, and runtime cost are not proven.",
            "PBR quality, LOD, Nanite, overdraw, shadows, WPO, streaming, and gameplay fit require isolated Unreal review and real-GPU evidence.",
            "Vendor packages remain immutable; project-owned catalogs, palettes, collections, and material adapters must reference them.",
        ],
        "duplicate_basenames": collisions,
        "candidates": normalized,
    }


def validate_output_path(
    output_path: Path,
    *,
    diagnostics_root: Path = DEFAULT_DIAGNOSTICS_ROOT,
) -> Path:
    resolved_output = output_path.resolve()
    resolved_root = diagnostics_root.resolve()
    if resolved_output.suffix.casefold() != ".json":
        raise CatalogExportError(f"output must use a .json suffix: {resolved_output}")
    try:
        resolved_output.relative_to(resolved_root)
    except ValueError as exc:
        raise CatalogExportError(
            f"output is restricted to diagnostics root {resolved_root}: "
            f"{resolved_output}"
        ) from exc
    return resolved_output


def report_bytes(report: Mapping[str, object]) -> bytes:
    return (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_report_atomic(output_path: Path, payload: bytes) -> None:
    if output_path.exists():
        raise CatalogExportError(f"refusing to overwrite existing report: {output_path}")
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
        # On Windows os.rename is an atomic same-volume move that fails when the
        # destination exists. Unlike os.replace, it preserves the no-overwrite
        # contract if another continuation races this writer.
        os.rename(temporary_name, output_path)
    finally:
        temporary_path = Path(temporary_name)
        if temporary_path.exists():
            temporary_path.unlink()


def _tag_value(
    asset_data: object,
    unreal_module: object,
    tag_name: str,
    asset_identity: str,
) -> str:
    """Handle UE Python's version-dependent out-parameter tuple shape."""

    try:
        result = asset_data.get_tag_value(unreal_module.Name(tag_name))
    except Exception as exc:
        raise CatalogExportError(
            f"Asset Registry tag read failed for {asset_identity} tag {tag_name}: {exc}"
        ) from exc
    if isinstance(result, tuple):
        if len(result) >= 2 and bool(result[0]):
            return str(result[1])
        return ""
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    raise CatalogExportError(
        f"unexpected Asset Registry tag result for {asset_identity} "
        f"tag {tag_name}: {type(result).__name__}"
    )


def collect_unreal_registry_records(unreal_module: object) -> Sequence[dict[str, object]]:
    """Read the six mounted roots from Unreal without loading package UObjects."""

    registry = unreal_module.AssetRegistryHelpers.get_asset_registry()
    registry.wait_for_completion()
    records: list[dict[str, object]] = []
    for root in PRIORITY_LIBRARY_ROOTS:
        asset_data_items = registry.get_assets_by_path(
            unreal_module.Name(root),
            True,
            True,
        )
        for asset_data in asset_data_items or ():
            package_name = str(asset_data.package_name)
            if package_name != root and not package_name.startswith(root + "/"):
                raise CatalogExportError(
                    f"Asset Registry query for {root} leaked {package_name}"
                )
            tags = {
                tag_name: value
                for tag_name in CURATION_TAGS
                if (
                    value := _tag_value(
                        asset_data,
                        unreal_module,
                        tag_name,
                        f"{package_name}.{asset_data.asset_name}",
                    )
                )
            }
            records.append(
                normalize_record(
                    package_name=package_name,
                    package_path=str(asset_data.package_path),
                    asset_name=str(asset_data.asset_name),
                    asset_class_path=canonical_top_level_asset_path(
                        asset_data.asset_class_path
                    ),
                    registry_tags=tags,
                )
            )
    return records


def _required_output_from_environment() -> Path:
    raw_output = os.environ.get(OUTPUT_ENVIRONMENT_VARIABLE, "").strip()
    if not raw_output:
        raise CatalogExportError(
            f"{OUTPUT_ENVIRONMENT_VARIABLE} must name a new diagnostics JSON path"
        )
    return validate_output_path(Path(raw_output))


def validate_unreal_identity(engine_version: str, project_file: str) -> None:
    if not engine_version.startswith("5.8"):
        raise CatalogExportError(
            f"expected Unreal Engine 5.8, observed {engine_version!r}"
        )
    expected_project = (Path(__file__).resolve().parents[1] / "Titan.uproject").resolve()
    observed_project = Path(project_file).resolve()
    if observed_project != expected_project:
        raise CatalogExportError(
            f"expected project {expected_project}, observed {observed_project}"
        )


def main() -> int:
    # Unreal is intentionally imported only inside the commandlet entry point so
    # all schema/path helpers remain unit-testable with ordinary CPython.
    import unreal

    output_path = _required_output_from_environment()
    engine_version = str(unreal.SystemLibrary.get_engine_version())
    project_file = str(unreal.Paths.get_project_file_path())
    validate_unreal_identity(engine_version, project_file)
    records = collect_unreal_registry_records(unreal)
    report = build_report(
        records,
        engine_version=engine_version,
        project_file=project_file,
    )
    write_report_atomic(output_path, report_bytes(report))
    unreal.log_warning(
        "REDMMO_ASSET_REGISTRY_CATALOG_READY "
        f"candidates={report['scope']['candidate_count']} output={output_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CatalogExportError as error:
        print(f"REDMMO_ASSET_REGISTRY_CATALOG_FAILED {error}", file=os.sys.stderr)
        raise SystemExit(2)
