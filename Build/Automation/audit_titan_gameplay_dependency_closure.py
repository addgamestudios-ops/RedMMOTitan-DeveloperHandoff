"""Provider-off, no-load Asset Registry closure audit for Titan gameplay roots.

Run only through Unreal's PythonScriptPlugin against the temporary module-free
TitanGameplayAudit.uproject beside the authoritative Content directory. The
script scans metadata, never loads an asset or map, never saves, and emits one
no-clobber JSON report outside every Content tree.
"""

from __future__ import annotations

import datetime as _datetime
import hashlib
import json
import os
from pathlib import Path

import unreal


OUTPUT_ENV = "REDMMO_TITAN_GAMEPLAY_CLOSURE_OUTPUT"
EXPECTED_PROJECT_ENV = "REDMMO_TITAN_GAMEPLAY_AUDIT_PROJECT"

ROOTS = (
    "/Game/RedMMO/Characters/BP_RedGameplayCharacter",
    "/Game/RedMMO/Characters/ABP_RedTrooperFemale",
    "/Game/RedMMO/Characters/CR_RedTrooperFocalAim",
    "/Game/RedMMO/Weapons/SK_RedTrooper_Rifle_A",
    "/Game/RedMMO/UI/BP_RedMultiplayerPlayerController",
    "/Game/RedMMO/UI/WBP_VibeMMOHUD",
    "/Game/RedMMO/Materials/M_BoltTracer",
    "/Game/RedMMO/Materials/MI_RedGrapplePlasma",
    "/Game/RedMMO/Anims/Rifle/A_Rifle_Aim_Idle",
    "/Game/RedMMO/Anims/Rifle/A_Rifle_Aim_Jump_End",
    "/Game/RedMMO/Anims/Rifle/A_Rifle_Aim_Jump_Start",
    "/Game/RedMMO/Anims/Rifle/A_Rifle_Fire_Single",
    "/Game/RedMMO/Anims/Rifle/A_Rifle_Jetpack_Aim_Air",
    "/Game/RedMMO/Anims/Rifle/A_Rifle_Jog_Aim_Fwd",
    "/Game/RedMMO/Anims/Rifle/A_Rifle_Relaxed_Idle",
    "/Game/Action_Trooper/Meshes/Trooper_UE4_Tall_Female/SK_TF_Trooper_Standalone_Covered",
    "/Game/Action_Trooper/Meshes/Trooper_UE4_Tall_Female/SK_TF_Trooper_Upper",
    "/Game/Action_Trooper/Meshes/Trooper_Accessories/SK_Trooper_Weapon_Rifle_B",
    "/Game/ProjectilesVol1/Effects/P_Flash_4",
    "/Game/ProjectilesVol1/Effects/P_Hit_3",
    "/Game/BeamsPack/VFX/Beams/NS_BeamOnly_02",
    "/Game/SoStylized/Sounds/Step/SC_Steps_Dirt",
)

EDGE_OPTIONS = {
    "hard_package": dict(include_hard_package_references=True),
    "soft_package": dict(include_soft_package_references=True),
}


class AuditError(RuntimeError):
    pass


def _dependency_options(enabled: dict[str, bool]) -> object:
    values = {
        "include_soft_package_references": False,
        "include_hard_package_references": False,
        "include_searchable_names": False,
        "include_soft_management_references": False,
        "include_hard_management_references": False,
    }
    values.update(enabled)
    return unreal.AssetRegistryDependencyOptions(**values)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _dirty_packages() -> dict[str, list[str]]:
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


def _asset_class(asset_data: object) -> str:
    class_path = getattr(asset_data, "asset_class_path", None)
    asset_name = str(getattr(class_path, "asset_name", "")).strip()
    return asset_name or str(class_path)


def _object_path(asset_data: object) -> str:
    return f"{asset_data.package_name}.{asset_data.asset_name}"


def _package_file(content_dir: Path, package_name: str) -> Path | None:
    if not package_name.startswith("/Game/"):
        return None
    relative = package_name[len("/Game/") :].replace("/", os.sep)
    for suffix in (".uasset", ".umap"):
        candidate = content_dir / f"{relative}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def _write_no_clobber(output: Path, payload: dict[str, object]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


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
        raise AuditError(f"unexpected audit project: {project_file}")
    if project_file.name != "TitanGameplayAudit.uproject":
        raise AuditError(f"unexpected audit descriptor name: {project_file.name}")

    content_dir = Path(
        unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir())
    ).resolve()
    if content_dir != project_file.parent / "Content":
        raise AuditError(f"audit project does not mount adjacent Content: {content_dir}")
    if output == project_file or content_dir in output.parents:
        raise AuditError(f"output must remain outside Content and descriptor: {output}")

    dirty_before = _dirty_packages()
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    registry.search_all_assets(True)

    missing_roots = []
    for root in ROOTS:
        if not list(registry.get_assets_by_package_name(unreal.Name(root)) or []):
            missing_roots.append(root)
    if missing_roots:
        raise AuditError(f"reviewed roots absent from current registry: {missing_roots}")

    closure: set[str] = set()
    pending = list(ROOTS)
    edges: set[tuple[str, str, str]] = set()
    external_leaves: set[str] = set()
    unresolved_game: set[str] = set()
    package_assets: dict[str, list[object]] = {}

    while pending:
        package_name = pending.pop()
        if package_name in closure:
            continue
        asset_records = list(
            registry.get_assets_by_package_name(unreal.Name(package_name)) or []
        )
        package_path = _package_file(content_dir, package_name)
        if not asset_records or package_path is None:
            unresolved_game.add(package_name)
            continue
        closure.add(package_name)
        package_assets[package_name] = asset_records

        for edge_kind, enabled in EDGE_OPTIONS.items():
            options = _dependency_options(enabled)
            dependencies = registry.get_dependencies(
                unreal.Name(package_name), options
            ) or []
            for dependency in dependencies:
                dependency_name = str(dependency)
                edges.add((package_name, dependency_name, edge_kind))
                if dependency_name.startswith("/Game/"):
                    if dependency_name not in closure:
                        pending.append(dependency_name)
                else:
                    external_leaves.add(dependency_name)

    package_records = []
    for package_name in sorted(closure):
        package_path = _package_file(content_dir, package_name)
        if package_path is None:
            unresolved_game.add(package_name)
            continue
        assets = sorted(package_assets[package_name], key=_object_path)
        stat = package_path.stat()
        package_records.append(
            {
                "package_name": package_name,
                "relative_content_path": str(package_path.relative_to(content_dir)).replace("\\", "/"),
                "bytes": stat.st_size,
                "last_write_utc": _datetime.datetime.fromtimestamp(
                    stat.st_mtime, tz=_datetime.timezone.utc
                ).isoformat(),
                "sha256": _sha256(package_path),
                "assets": [
                    {"object_path": _object_path(asset), "class": _asset_class(asset)}
                    for asset in assets
                ],
            }
        )

    dirty_after = _dirty_packages()
    if dirty_after != dirty_before:
        raise AuditError(
            f"dirty package state changed: before={dirty_before} after={dirty_after}"
        )

    result = "pass_current_registry_closure" if not unresolved_game else "fail_unresolved_game_packages"
    payload = {
        "schema_version": 1,
        "captured_utc": _datetime.datetime.now(_datetime.timezone.utc).isoformat(),
        "result": result,
        "evidence_class": "static_current_asset_registry",
        "project_file": str(project_file),
        "content_dir": str(content_dir),
        "engine_version": unreal.SystemLibrary.get_engine_version(),
        "roots": list(ROOTS),
        "root_count": len(ROOTS),
        "closure_count": len(closure),
        "edge_count": len(edges),
        "package_records": package_records,
        "edges": [
            {"source": source, "dependency": dependency, "kind": kind}
            for source, dependency, kind in sorted(edges)
        ],
        "external_leaves": sorted(external_leaves),
        "script_leaves": sorted(x for x in external_leaves if x.startswith("/Script/")),
        "plugin_mount_leaves": sorted(
            x
            for x in external_leaves
            if x.startswith("/")
            and not x.startswith(("/Game/", "/Engine/", "/Script/"))
        ),
        "unresolved_game_packages": sorted(unresolved_game),
        "non_package_dependency_policy": (
            "The UE Python get_dependencies wrapper does not reliably separate searchable-name "
            "or management categories when both package-reference flags are false. This report "
            "therefore claims only hard/soft package closure; the historical UE detailed dump "
            "is retained separately for non-package category review."
        ),
        "dirty_before": dirty_before,
        "dirty_after": dirty_after,
        "claim_limit": (
            "Registry metadata and current source-file hashes only. No asset/map was loaded, "
            "compiled, copied, saved, bound, run, or visually accepted."
        ),
    }
    _write_no_clobber(output, payload)
    unreal.log(f"RED_TITAN_GAMEPLAY_CLOSURE_RESULT={result}")
    unreal.log(f"RED_TITAN_GAMEPLAY_CLOSURE_PACKAGES={len(closure)}")
    unreal.log(f"RED_TITAN_GAMEPLAY_CLOSURE_EDGES={len(edges)}")
    unreal.log(f"RED_TITAN_GAMEPLAY_CLOSURE_OUTPUT={output}")
    if unresolved_game:
        raise AuditError(f"unresolved /Game packages: {sorted(unresolved_game)}")


if __name__ == "__main__":
    main()
