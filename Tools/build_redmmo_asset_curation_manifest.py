"""Build a deterministic RED MMO art-library curation manifest.

The input is the candidate-only JSON emitted by
``export_redmmo_asset_registry_catalog.py``. Every decoded record is retained
exactly once and assigned a review disposition. No candidate is approved, no
license right is inferred, and no Unreal package or project Content file is
created, loaded, moved, renamed, or modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence

try:
    from Tools.export_redmmo_asset_registry_catalog import PRIORITY_LIBRARY_ROOTS
except ModuleNotFoundError as error:
    if error.name != "Tools":
        raise
    from export_redmmo_asset_registry_catalog import PRIORITY_LIBRARY_ROOTS


DEFAULT_DIAGNOSTICS_ROOT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics")
EXPECTED_AUDIT_ID = "redmmo-unreal-asset-registry-catalog-candidates"
EXPECTED_INPUT_STATUS = "candidate_only"

PROVENANCE_FILE_TERMS = {
    "copyright",
    "documentation",
    "eula",
    "licence",
    "license",
    "manifest",
    "readme",
    "version",
}
PROVENANCE_FILE_SUFFIXES = {".html", ".htm", ".json", ".md", ".pdf", ".txt", ".xml"}

PRIMARY_CLASS_POLICY = {
    "/Script/Engine.StaticMesh": ("primary_environment_asset", 100),
    "/Script/Foliage.FoliageType_InstancedStaticMesh": (
        "primary_foliage_definition",
        95,
    ),
    "/Script/Landscape.LandscapeGrassType": ("primary_grass_definition", 90),
    "/Script/Engine.MaterialInstanceConstant": ("primary_material_instance", 80),
}

SUPPORT_CLASS_POLICY = {
    "/Script/Engine.Material": ("support_master_material", 65),
    "/Script/Engine.MaterialFunction": ("support_material_function", 55),
    "/Script/Engine.Texture2D": ("support_texture", 50),
    "/Script/Engine.TextureCube": ("support_texture_cube", 50),
    "/Script/Engine.VolumeTexture": ("support_volume_texture", 50),
    "/Script/Engine.RuntimeVirtualTexture": ("support_runtime_virtual_texture", 45),
    "/Script/Landscape.LandscapeLayerInfoObject": (
        "support_landscape_layer",
        40,
    ),
    "/Script/Engine.MaterialParameterCollection": (
        "support_material_parameter_collection",
        40,
    ),
    "/Script/PhysicsCore.PhysicalMaterial": ("support_physical_material", 40),
    "/Script/Engine.CurveLinearColorAtlas": ("support_color_atlas", 35),
    "/Script/Engine.CurveLinearColor": ("support_color_curve", 30),
}

DEFERRED_CLASS_POLICY = {
    "/Script/Engine.AnimBlueprint": "deferred_animation_system",
    "/Script/Engine.AnimSequence": "deferred_animation_system",
    "/Script/Engine.BlendSpace1D": "deferred_animation_system",
    "/Script/Engine.Blueprint": "deferred_blueprint_or_demo_logic",
    "/Script/Engine.PhysicsAsset": "deferred_skeletal_system",
    "/Script/Engine.SkeletalMesh": "deferred_skeletal_system",
    "/Script/Engine.Skeleton": "deferred_skeletal_system",
    "/Script/Engine.SoundCue": "deferred_audio",
    "/Script/Engine.SoundWave": "deferred_audio",
    "/Script/Niagara.NiagaraEmitter": "deferred_vfx",
    "/Script/Niagara.NiagaraSystem": "deferred_vfx",
}

EXCLUDED_CLASS_POLICY = {
    "/Script/CoreUObject.ObjectRedirector": "exclude_redirector",
    "/Script/Engine.MapBuildDataRegistry": "exclude_map_build_data",
    "/Script/Engine.World": "exclude_reference_world",
    "/Script/EnhancedInput.InputAction": "exclude_demo_input",
    "/Script/EnhancedInput.InputMappingContext": "exclude_demo_input",
}

ROLE_PRIORITY_BONUS = {
    "Geology": 15,
    "Vegetation.Grass": 14,
    "Vegetation.Plant": 13,
    "Vegetation.Tree": 13,
    "Terrain.Surface": 12,
    "Water": 10,
    "Architecture": 8,
    "Prop": 6,
    "VFX": 3,
}

NAME_PREFIXES = {
    "bp",
    "ft",
    "m",
    "mf",
    "mi",
    "sk",
    "sm",
    "t",
}
VARIANT_TOKENS = {
    "a",
    "b",
    "bc",
    "c",
    "d",
    "e",
    "f",
    "mra",
    "n",
    "normal",
    "orm",
    "r",
    "roughness",
}


class CurationManifestError(RuntimeError):
    """Raised when the candidate input cannot produce a complete manifest."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def validate_diagnostics_path(
    path: Path,
    *,
    diagnostics_root: Path = DEFAULT_DIAGNOSTICS_ROOT,
    must_exist: bool,
) -> Path:
    resolved = path.resolve()
    resolved_root = diagnostics_root.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise CurationManifestError(
            f"path is restricted to diagnostics root {resolved_root}: {resolved}"
        ) from exc
    if resolved.suffix.casefold() != ".json":
        raise CurationManifestError(f"path must use a .json suffix: {resolved}")
    if must_exist and not resolved.is_file():
        raise CurationManifestError(f"candidate report is missing: {resolved}")
    if not must_exist and resolved.exists():
        raise CurationManifestError(f"refusing to overwrite output: {resolved}")
    return resolved


def _is_link_or_reparse(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise CurationManifestError(
            f"unable to inspect path metadata: {path}: {error}"
        ) from error
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(metadata, "st_file_attributes", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(
        reparse_flag and attributes & reparse_flag
    )


def discover_local_provenance_files(
    project_root: Path,
    library_roots: Sequence[str] = PRIORITY_LIBRARY_ROOTS,
) -> dict[str, list[dict[str, object]]]:
    """Find bounded local license/readme/version evidence without interpreting it."""

    project_root = project_root.resolve()
    content_root = project_root / "Content"
    if not content_root.is_dir() or _is_link_or_reparse(content_root):
        raise CurationManifestError(
            f"Content root is missing or linked: {content_root}"
        )

    def raise_walk_error(error: OSError) -> None:
        raise CurationManifestError(
            f"unable to scan provenance under {content_root}: {error}"
        ) from error

    result: dict[str, list[dict[str, object]]] = {}
    for library_root in library_roots:
        relative = library_root.removeprefix("/Game/").strip("/")
        disk_root = content_root / relative
        if not disk_root.is_dir() or _is_link_or_reparse(disk_root):
            raise CurationManifestError(
                f"priority library root is missing or linked: {disk_root}"
            )
        records: list[dict[str, object]] = []
        for raw_directory, directory_names, file_names in os.walk(
            disk_root,
            topdown=True,
            onerror=raise_walk_error,
            followlinks=False,
        ):
            directory = Path(raw_directory)
            safe_directories: list[str] = []
            for name in sorted(
                directory_names,
                key=lambda value: (value.casefold(), value),
            ):
                candidate = directory / name
                if _is_link_or_reparse(candidate):
                    raise CurationManifestError(
                        f"linked directory blocks complete provenance scan: {candidate}"
                    )
                safe_directories.append(name)
            directory_names[:] = safe_directories
            for name in sorted(
                file_names,
                key=lambda value: (value.casefold(), value),
            ):
                candidate = directory / name
                if _is_link_or_reparse(candidate):
                    raise CurationManifestError(
                        f"linked file blocks complete provenance scan: {candidate}"
                    )
                tokens = set(re.findall(r"[a-z0-9]+", candidate.stem.casefold()))
                if (
                    candidate.suffix.casefold() in PROVENANCE_FILE_SUFFIXES
                    and tokens.intersection(PROVENANCE_FILE_TERMS)
                ):
                    try:
                        records.append(
                            {
                                "path": candidate.relative_to(project_root).as_posix(),
                                "bytes": candidate.stat().st_size,
                                "sha256": sha256_file(candidate),
                            }
                        )
                    except OSError as error:
                        raise CurationManifestError(
                            f"unable to read provenance candidate {candidate}: {error}"
                        ) from error
        result[library_root] = records
    return result


def classify_asset_class(asset_class_path: str) -> tuple[str, str, int]:
    if asset_class_path in PRIMARY_CLASS_POLICY:
        reason, base_score = PRIMARY_CLASS_POLICY[asset_class_path]
        return "primary_environment_candidate", reason, base_score
    if asset_class_path in SUPPORT_CLASS_POLICY:
        reason, base_score = SUPPORT_CLASS_POLICY[asset_class_path]
        return "support_dependency_candidate", reason, base_score
    if asset_class_path in DEFERRED_CLASS_POLICY:
        return (
            "deferred_specialty_candidate",
            DEFERRED_CLASS_POLICY[asset_class_path],
            15,
        )
    if asset_class_path in EXCLUDED_CLASS_POLICY:
        return "excluded_technical_or_reference", EXCLUDED_CLASS_POLICY[asset_class_path], 0
    return "deferred_unknown_class", "deferred_unclassified_asset_class", 5


def _semantic_tokens(asset_name: str) -> list[str]:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", asset_name)
    raw = re.findall(r"[a-z0-9]+", separated.casefold())
    tokens = [
        token
        for token in raw
        if token not in NAME_PREFIXES
        and token not in VARIANT_TOKENS
        and not token.isdigit()
    ]
    return tokens or ["unnamed"]


def family_identity(library_root: str, asset_name: str) -> tuple[str, str]:
    semantic = "_".join(_semantic_tokens(asset_name)[:5])
    family_key = f"{library_root.removeprefix('/Game/').casefold()}/{semantic}"
    family_id = "RED-FAMILY-" + hashlib.sha256(family_key.encode("utf-8")).hexdigest()[
        :16
    ].upper()
    return family_id, family_key


def proposed_collections(
    library_root: str,
    candidate_roles: Sequence[str],
    disposition: str,
) -> list[str]:
    pack_name = library_root.removeprefix("/Game/")
    collections = [
        "RED MMO/Candidates/Needs License Review",
        f"RED MMO/Candidates/Source/{pack_name}",
        f"RED MMO/Candidates/Disposition/{disposition}",
    ]
    collections.extend(
        f"RED MMO/Candidates/Role/{role.replace('.', '/')}"
        for role in candidate_roles
        if role != "Art.Support"
    )
    return sorted(set(collections))


def _validate_raw_report(raw_report: Mapping[str, object]) -> list[Mapping[str, object]]:
    if raw_report.get("schema_version") != 1:
        raise CurationManifestError("candidate report schema_version must be integer 1")
    if raw_report.get("audit_id") != EXPECTED_AUDIT_ID:
        raise CurationManifestError("input is not the RED MMO Asset Registry report")
    if raw_report.get("status") != EXPECTED_INPUT_STATUS:
        raise CurationManifestError("input report must remain candidate_only")
    if raw_report.get("evidence_class") != "static":
        raise CurationManifestError("input report must be static evidence")
    scope = raw_report.get("scope")
    candidates = raw_report.get("candidates")
    if not isinstance(scope, dict) or not isinstance(candidates, list):
        raise CurationManifestError("input report scope/candidates shape is invalid")
    if scope.get("library_roots") != list(PRIORITY_LIBRARY_ROOTS):
        raise CurationManifestError("input report priority root ordering changed")
    if scope.get("candidate_count") != len(candidates):
        raise CurationManifestError("input report candidate count does not match payload")
    if any(not isinstance(candidate, dict) for candidate in candidates):
        raise CurationManifestError("every candidate must be a JSON object")
    return candidates


def _normalize_entry(
    raw: Mapping[str, object],
    provenance_files: Mapping[str, Sequence[Mapping[str, object]]],
) -> dict[str, object]:
    required = {
        "stable_candidate_id",
        "library_root",
        "package_name",
        "package_path",
        "asset_name",
        "object_path",
        "asset_class_path",
        "candidate_roles",
        "registry_tags",
        "source_policy",
        "review_status",
        "requires_license_review",
        "requires_visual_and_performance_review",
    }
    missing = sorted(required - set(raw))
    if missing:
        raise CurationManifestError(f"candidate is missing fields: {missing}")
    identity_fields = (
        "stable_candidate_id",
        "library_root",
        "package_name",
        "package_path",
        "asset_name",
        "object_path",
        "asset_class_path",
    )
    if any(
        not isinstance(raw[field], str) or not raw[field]
        for field in identity_fields
    ):
        raise CurationManifestError("candidate identity fields must be non-empty strings")
    if not isinstance(raw["candidate_roles"], list) or any(
        not isinstance(role, str) or not role for role in raw["candidate_roles"]
    ):
        raise CurationManifestError("candidate roles must be non-empty strings in a list")
    if not isinstance(raw["registry_tags"], dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in raw["registry_tags"].items()
    ):
        raise CurationManifestError("candidate registry tags must be a string mapping")

    library_root = raw["library_root"]
    if library_root not in PRIORITY_LIBRARY_ROOTS:
        raise CurationManifestError(f"candidate uses unknown root: {library_root}")
    package_name = raw["package_name"]
    matching_roots = [
        root
        for root in PRIORITY_LIBRARY_ROOTS
        if package_name == root or package_name.startswith(root + "/")
    ]
    if matching_roots != [library_root]:
        raise CurationManifestError(
            "candidate package path does not authenticate its claimed library root"
        )
    expected_package_path = package_name.rpartition("/")[0]
    if not expected_package_path or raw["package_path"] != expected_package_path:
        raise CurationManifestError(
            "candidate package_path does not match package_name"
        )
    expected_object_path = f"{package_name}.{raw['asset_name']}"
    if raw["object_path"] != expected_object_path:
        raise CurationManifestError(
            "candidate object_path does not match package_name and asset_name"
        )
    expected_candidate_id = hashlib.sha256(
        expected_object_path.encode("utf-8")
    ).hexdigest()[:24].upper()
    if raw["stable_candidate_id"] != expected_candidate_id:
        raise CurationManifestError(
            "candidate stable ID does not match its authenticated object path"
        )
    if raw["source_policy"] != "vendor_source_immutable":
        raise CurationManifestError("candidate source policy must remain immutable")
    if raw["review_status"] != "unreviewed_asset_registry_candidate":
        raise CurationManifestError("candidate was unexpectedly promoted before curation")
    if raw["requires_license_review"] is not True:
        raise CurationManifestError("candidate license review gate was removed")
    if raw["requires_visual_and_performance_review"] is not True:
        raise CurationManifestError("candidate visual/performance gate was removed")

    asset_class_path = raw["asset_class_path"]
    disposition, disposition_reason, base_score = classify_asset_class(
        asset_class_path
    )
    roles = sorted(set(raw["candidate_roles"]))
    role_bonus = max((ROLE_PRIORITY_BONUS.get(role, 0) for role in roles), default=0)
    review_priority_score = min(100, base_score + role_bonus)
    family_id, family_key = family_identity(library_root, str(raw["asset_name"]))
    local_provenance = list(provenance_files.get(library_root, ()))
    license_status = (
        "unverified_local_provenance_files_found_requires_human_review"
        if local_provenance
        else "unverified_no_local_license_record_found"
    )
    return {
        "stable_candidate_id": str(raw["stable_candidate_id"]),
        "object_path": str(raw["object_path"]),
        "package_name": str(raw["package_name"]),
        "package_path": str(raw["package_path"]),
        "asset_name": str(raw["asset_name"]),
        "asset_class_path": asset_class_path,
        "library_root": library_root,
        "source_pack_name": library_root.removeprefix("/Game/"),
        "source_version": "unknown_requires_vendor_record",
        "source_policy": "vendor_source_immutable",
        "local_provenance_files": local_provenance,
        "license_review_status": license_status,
        "license_approved": False,
        "asset_approved": False,
        "approved_roles": [],
        "candidate_roles": roles,
        "registry_tags": dict(raw["registry_tags"]),
        "curation_disposition": disposition,
        "curation_reason": disposition_reason,
        "review_priority_score": review_priority_score,
        "family_id": family_id,
        "family_key": family_key,
        "proposed_collections": proposed_collections(
            library_root,
            roles,
            disposition,
        ),
        "recommended_handling": (
            "project_owned_soft_reference_candidate"
            if disposition == "primary_environment_candidate"
            else "retain_as_source_or_dependency_without_palette_promotion"
        ),
        "requires_visual_and_performance_review": True,
    }


def build_manifest(
    raw_report: Mapping[str, object],
    *,
    input_path: Path,
    input_sha256: str,
    provenance_files: Mapping[str, Sequence[Mapping[str, object]]],
) -> dict[str, object]:
    candidates = _validate_raw_report(raw_report)
    entries = [_normalize_entry(raw, provenance_files) for raw in candidates]
    entries.sort(
        key=lambda entry: (
            -int(entry["review_priority_score"]),
            str(entry["library_root"]).casefold(),
            str(entry["object_path"]).casefold(),
        )
    )
    candidate_ids = [str(entry["stable_candidate_id"]) for entry in entries]
    object_paths = [str(entry["object_path"]) for entry in entries]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise CurationManifestError("duplicate stable candidate IDs in input")
    if len(object_paths) != len(set(object_paths)):
        raise CurationManifestError("duplicate object paths in input")

    disposition_counts = Counter(
        str(entry["curation_disposition"]) for entry in entries
    )
    class_counts = Counter(str(entry["asset_class_path"]) for entry in entries)
    root_counts = Counter(str(entry["library_root"]) for entry in entries)
    role_counts = Counter(
        str(role) for entry in entries for role in entry["candidate_roles"]
    )
    scope = raw_report["scope"]
    expected_root_counts = {
        root: root_counts[root] for root in PRIORITY_LIBRARY_ROOTS
    }
    if scope.get("root_candidate_counts") != expected_root_counts:
        raise CurationManifestError(
            "input report root_candidate_counts do not match authenticated candidates"
        )
    expected_class_counts = dict(sorted(class_counts.items()))
    if scope.get("asset_class_counts") != expected_class_counts:
        raise CurationManifestError(
            "input report asset_class_counts do not match authenticated candidates"
        )
    basename_counts = Counter(
        str(entry["asset_name"]).casefold() for entry in entries
    )
    expected_collision_count = sum(
        1 for count in basename_counts.values() if count > 1
    )
    if scope.get("duplicate_basename_group_count") != expected_collision_count:
        raise CurationManifestError(
            "input duplicate basename count does not match authenticated candidates"
        )

    families: dict[str, list[dict[str, object]]] = defaultdict(list)
    for entry in entries:
        if entry["curation_disposition"] in {
            "primary_environment_candidate",
            "support_dependency_candidate",
        }:
            families[str(entry["family_id"])].append(entry)
    review_batches = []
    for family_id, members in families.items():
        primary_members = [
            member
            for member in members
            if member["curation_disposition"] == "primary_environment_candidate"
        ]
        if not primary_members:
            continue
        support_members = [
            member
            for member in members
            if member["curation_disposition"] == "support_dependency_candidate"
        ]
        review_batches.append(
            {
                "family_id": family_id,
                "family_key": str(members[0]["family_key"]),
                "source_pack_name": str(members[0]["source_pack_name"]),
                "member_count": len(members),
                "primary_member_count": len(primary_members),
                "support_dependency_member_count": len(support_members),
                "max_review_priority_score": max(
                    int(member["review_priority_score"]) for member in members
                ),
                "candidate_roles": sorted(
                    {
                        str(role)
                        for member in members
                        for role in member["candidate_roles"]
                    }
                ),
                "member_ids": sorted(
                    str(member["stable_candidate_id"]) for member in members
                ),
                "primary_member_ids": sorted(
                    str(member["stable_candidate_id"])
                    for member in primary_members
                ),
                "support_dependency_member_ids": sorted(
                    str(member["stable_candidate_id"])
                    for member in support_members
                ),
                "review_status": "unreviewed_family_candidate",
                "approval_status": "not_approved",
            }
        )
    review_batches.sort(
        key=lambda batch: (
            -int(batch["max_review_priority_score"]),
            -int(batch["member_count"]),
            str(batch["family_key"]),
        )
    )

    manifest_signature = hashlib.sha256()
    for entry in sorted(entries, key=lambda item: str(item["stable_candidate_id"])):
        manifest_signature.update(
            (
                f"{entry['stable_candidate_id']}|{entry['object_path']}|"
                f"{entry['curation_disposition']}|{entry['family_id']}|"
                f"{entry['license_review_status']}\n"
            ).encode("utf-8")
        )

    return {
        "schema_version": 1,
        "manifest_id": "redmmo-art-library-curation-candidates",
        "evidence_class": "static",
        "status": "unreviewed_no_assets_approved",
        "input": {
            "path": input_path.as_posix(),
            "sha256": input_sha256,
            "audit_id": EXPECTED_AUDIT_ID,
            "candidate_count": len(entries),
        },
        "policy": {
            "vendor_packages_are_immutable": True,
            "every_input_candidate_retained_exactly_once": True,
            "license_approval_inferred": False,
            "asset_approval_inferred": False,
            "candidate_roles_are_approved_roles": False,
            "content_browser_collections_created": False,
            "unreal_packages_created_or_modified": False,
            "project_owned_palette_created": False,
        },
        "summary": {
            "entry_count": len(entries),
            "root_counts": {
                root: root_counts[root] for root in PRIORITY_LIBRARY_ROOTS
            },
            "disposition_counts": dict(sorted(disposition_counts.items())),
            "asset_class_counts": expected_class_counts,
            "candidate_role_counts": dict(sorted(role_counts.items())),
            "family_review_batch_count": len(review_batches),
            "local_provenance_file_count": sum(
                len(files) for files in provenance_files.values()
            ),
            "license_approved_count": 0,
            "asset_approved_count": 0,
            "manifest_signature_sha256": manifest_signature.hexdigest().upper(),
        },
        "source_packs": [
            {
                "library_root": root,
                "source_pack_name": root.removeprefix("/Game/"),
                "source_version": "unknown_requires_vendor_record",
                "source_policy": "vendor_source_immutable",
                "local_provenance_files": list(provenance_files.get(root, ())),
                "license_review_status": (
                    "unverified_local_provenance_files_found_requires_human_review"
                    if provenance_files.get(root)
                    else "unverified_no_local_license_record_found"
                ),
                "license_approved": False,
            }
            for root in PRIORITY_LIBRARY_ROOTS
        ],
        "review_batches": review_batches,
        "entries": entries,
        "claim_limit": (
            "This manifest classifies Asset Registry candidates for review only. "
            "Scores, roles, collections, and families are deterministic triage hints, "
            "not proof of license rights, PBR quality, appearance, performance, "
            "collision, LOD, Nanite, WPO, shadow, cull, or gameplay suitability."
        ),
    }


def manifest_bytes(manifest: Mapping[str, object]) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_manifest_atomic(output_path: Path, payload: bytes) -> None:
    if output_path.exists():
        raise CurationManifestError(f"refusing to overwrite output: {output_path}")
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
        os.rename(temporary_name, output_path)
    finally:
        temporary_path = Path(temporary_name)
        if temporary_path.exists():
            temporary_path.unlink()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    input_path = validate_diagnostics_path(args.input, must_exist=True)
    output_path = validate_diagnostics_path(args.output, must_exist=False)
    if input_path == output_path:
        raise CurationManifestError("input and output paths must differ")
    raw_bytes = input_path.read_bytes()
    raw_report = json.loads(raw_bytes.decode("utf-8"))
    project_root = args.project_root.resolve()
    expected_project = Path(__file__).resolve().parents[1]
    if project_root != expected_project:
        raise CurationManifestError(
            f"expected project root {expected_project}, observed {project_root}"
        )
    provenance_files = discover_local_provenance_files(project_root)
    manifest = build_manifest(
        raw_report,
        input_path=input_path,
        input_sha256=hashlib.sha256(raw_bytes).hexdigest().upper(),
        provenance_files=provenance_files,
    )
    write_manifest_atomic(output_path, manifest_bytes(manifest))
    print(
        "REDMMO_CURATION_MANIFEST_OK "
        f"entries={manifest['summary']['entry_count']} "
        f"primary={manifest['summary']['disposition_counts'].get('primary_environment_candidate', 0)} "
        f"support={manifest['summary']['disposition_counts'].get('support_dependency_candidate', 0)} "
        f"deferred={sum(count for key, count in manifest['summary']['disposition_counts'].items() if key.startswith('deferred_'))} "
        f"excluded={manifest['summary']['disposition_counts'].get('excluded_technical_or_reference', 0)} "
        f"output={output_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CurationManifestError, json.JSONDecodeError) as error:
        print(f"REDMMO_CURATION_MANIFEST_FAILED {error}", file=os.sys.stderr)
        raise SystemExit(2)
