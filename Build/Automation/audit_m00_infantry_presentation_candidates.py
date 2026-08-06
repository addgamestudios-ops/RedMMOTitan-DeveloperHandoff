"""Read-only UE Asset Registry audit for the bounded M00 rifle presentation roots.

Run through Unreal's PythonScriptPlugin. The audit loads only the two reviewed
assets after resolving their package closure, never saves, and writes one
no-clobber JSON report outside every Content tree.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path

import unreal


OUTPUT_ENV = "REDMMO_M00_PRESENTATION_AUDIT_OUTPUT"
EXPECTED_PROJECT_ENV = "REDMMO_M00_PRESENTATION_AUDIT_PROJECT"

ROOTS = (
    "/Game/RedMMO/Anims/Rifle/A_Rifle_Fire_Single",
    "/Game/ProjectilesVol1/Effects/P_Flash_17",
)

COMPARATOR = "/Game/ProjectilesVol1/Effects/P_Flash_4"


class AuditError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def dirty_packages() -> dict[str, list[str]]:
    return {
        "content": sorted(
            str(package.get_path_name())
            for package in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
        ),
        "maps": sorted(
            str(package.get_path_name())
            for package in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
        ),
    }


def dependency_options(*, hard: bool = False, soft: bool = False) -> object:
    return unreal.AssetRegistryDependencyOptions(
        include_soft_package_references=soft,
        include_hard_package_references=hard,
        include_searchable_names=False,
        include_soft_management_references=False,
        include_hard_management_references=False,
    )


def package_file(content_dir: Path, package_name: str) -> Path | None:
    if not package_name.startswith("/Game/"):
        return None
    relative = package_name[len("/Game/") :].replace("/", os.sep)
    for suffix in (".uasset", ".umap"):
        candidate = content_dir / f"{relative}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def asset_class(asset_data: object) -> str:
    class_path = getattr(asset_data, "asset_class_path", None)
    asset_name = str(getattr(class_path, "asset_name", "")).strip()
    return asset_name or str(class_path)


def object_path(package_name: str) -> str:
    asset_name = package_name.rsplit("/", 1)[-1]
    return f"{package_name}.{asset_name}"


def get_property_text(asset: object, name: str) -> str | None:
    try:
        value = asset.get_editor_property(name)
    except Exception:
        return None
    return None if value is None else str(value)


def inspect_animation(package_name: str) -> dict[str, object]:
    asset = unreal.load_asset(object_path(package_name))
    if not asset or not isinstance(asset, unreal.AnimSequence):
        raise AuditError(f"animation did not load as AnimSequence: {package_name}")
    sampled_keys = None
    for method_name in ("get_number_of_sampled_keys", "get_number_of_frames"):
        method = getattr(asset, method_name, None)
        if callable(method):
            try:
                sampled_keys = int(method())
                break
            except Exception:
                pass
    return {
        "object_path": asset.get_path_name(),
        "class": asset.get_class().get_name(),
        "play_length_seconds": float(asset.get_play_length()),
        "sampled_keys_or_frames": sampled_keys,
        "skeleton": get_property_text(asset, "skeleton"),
        "enable_root_motion": get_property_text(asset, "enable_root_motion"),
        "root_motion_root_lock": get_property_text(asset, "root_motion_root_lock"),
        "additive_anim_type": get_property_text(asset, "additive_anim_type"),
    }


def inspect_niagara(package_name: str) -> dict[str, object]:
    asset = unreal.load_asset(object_path(package_name))
    if not asset or not isinstance(asset, unreal.NiagaraSystem):
        raise AuditError(f"effect did not load as NiagaraSystem: {package_name}")
    return {
        "object_path": asset.get_path_name(),
        "class": asset.get_class().get_name(),
        "fixed_bounds": get_property_text(asset, "fixed_bounds"),
        "warmup_time": get_property_text(asset, "warmup_time"),
        "warmup_tick_delta": get_property_text(asset, "warmup_tick_delta"),
        "effect_type": get_property_text(asset, "effect_type"),
    }


def main() -> None:
    output_text = os.environ.get(OUTPUT_ENV, "").strip()
    expected_project_text = os.environ.get(EXPECTED_PROJECT_ENV, "").strip()
    if not output_text or not expected_project_text:
        raise AuditError(f"{OUTPUT_ENV} and {EXPECTED_PROJECT_ENV} are required")

    output = Path(output_text).resolve()
    expected_project = Path(expected_project_text).resolve()
    project_file = Path(
        unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())
    ).resolve()
    if project_file != expected_project:
        raise AuditError(f"unexpected project: {project_file}")

    content_dir = Path(
        unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir())
    ).resolve()
    if output == project_file or content_dir in output.parents:
        raise AuditError(f"output must remain outside the project Content tree: {output}")
    if output.exists():
        raise AuditError(f"refusing to overwrite report: {output}")

    dirty_before = dirty_packages()
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    registry.search_all_assets(True)

    missing = [
        package
        for package in (*ROOTS, COMPARATOR)
        if not list(registry.get_assets_by_package_name(unreal.Name(package)) or [])
    ]
    if missing:
        raise AuditError(f"reviewed packages missing from registry: {missing}")

    closure: set[str] = set()
    pending = list(ROOTS)
    edges: set[tuple[str, str, str]] = set()
    external_leaves: set[str] = set()
    unresolved_game: set[str] = set()
    while pending:
        package = pending.pop()
        if package in closure:
            continue
        asset_records = list(
            registry.get_assets_by_package_name(unreal.Name(package)) or []
        )
        disk_path = package_file(content_dir, package)
        if not asset_records or disk_path is None:
            unresolved_game.add(package)
            continue
        closure.add(package)
        for edge_kind, options in (
            ("hard_package", dependency_options(hard=True)),
            ("soft_package", dependency_options(soft=True)),
        ):
            for dependency in registry.get_dependencies(unreal.Name(package), options) or []:
                dep = str(dependency)
                edges.add((package, dep, edge_kind))
                if dep.startswith("/Game/"):
                    if dep not in closure:
                        pending.append(dep)
                else:
                    external_leaves.add(dep)

    packages = []
    for package in sorted(closure):
        disk_path = package_file(content_dir, package)
        if disk_path is None:
            unresolved_game.add(package)
            continue
        records = list(registry.get_assets_by_package_name(unreal.Name(package)) or [])
        packages.append(
            {
                "package_name": package,
                "relative_content_path": str(disk_path.relative_to(content_dir)).replace("\\", "/"),
                "bytes": disk_path.stat().st_size,
                "sha256": sha256(disk_path),
                "assets": [
                    {
                        "object_path": f"{record.package_name}.{record.asset_name}",
                        "class": asset_class(record),
                    }
                    for record in records
                ],
            }
        )

    inspections = {
        ROOTS[0]: inspect_animation(ROOTS[0]),
        ROOTS[1]: inspect_niagara(ROOTS[1]),
        COMPARATOR: inspect_niagara(COMPARATOR),
    }
    dirty_after = dirty_packages()
    if dirty_after != dirty_before:
        raise AuditError(
            f"dirty package state changed: before={dirty_before} after={dirty_after}"
        )
    if unresolved_game:
        raise AuditError(f"unresolved /Game packages: {sorted(unresolved_game)}")

    payload = {
        "schema_version": 1,
        "evidence_class": "static",
        "status": "pass_dependency_closed_candidate_audit",
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "project_file": str(project_file),
        "content_dir": str(content_dir),
        "roots": list(ROOTS),
        "rejected_comparator": COMPARATOR,
        "package_count": len(packages),
        "total_bytes": sum(int(record["bytes"]) for record in packages),
        "hard_edge_count": sum(1 for edge in edges if edge[2] == "hard_package"),
        "soft_edge_count": sum(1 for edge in edges if edge[2] == "soft_package"),
        "external_leaves": sorted(external_leaves),
        "packages": packages,
        "edges": [
            {"source": source, "dependency": dependency, "kind": kind}
            for source, dependency, kind in sorted(edges)
        ],
        "inspections": inspections,
        "dirty_before": dirty_before,
        "dirty_after": dirty_after,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    unreal.log(f"REDMMO_M00_PRESENTATION_AUDIT_OK {output}")


if __name__ == "__main__":
    main()
