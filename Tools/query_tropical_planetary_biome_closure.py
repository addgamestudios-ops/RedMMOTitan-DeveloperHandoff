"""Authoritative UE 5.8 dependency probe for the Tropical planetary-biome pilot.

Run this script only through the Unreal PythonScript commandlet against the
isolated Tropical review project. It:

* authenticates an exact seed allowlist,
* computes fixed-point Asset Registry closures,
* bounded-loads every project package in each closure,
* proves that no content or map package became dirty, and
* writes one no-clobber JSON diagnostic outside every Unreal Content tree.

It never saves, migrates, renames, duplicates, places, or modifies an asset.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import unreal


OUTPUT_ENV = "REDMMO_TROPICAL_CLOSURE_OUTPUT"
EXPECTED_PROJECT_ROOT_ENV = "REDMMO_TROPICAL_EXPECTED_PROJECT_ROOT"
PACK_ROOT = "/Game/Zenscape_Island"

GROUPS = {
    "core": (
        "/Game/Zenscape_Island/Texture/Landscape/T_Sand_Stylized_BaseColor",
        "/Game/Zenscape_Island/Texture/Landscape/T_Sand_Stylized_Normalsand_04_normal_dx_2k",
        "/Game/Zenscape_Island/Texture/Landscape/T_Sand_Stylized_Height",
        "/Game/Zenscape_Island/Texture/Landscape/T_Sand_AO",
        "/Game/Zenscape_Island/Model/Rocks/SM_Cliff_01",
        "/Game/Zenscape_Island/Model/Tree/SM_CoconutTree_01",
        "/Game/Zenscape_Island/Model/Plants/SM_Plant_01",
        "/Game/Zenscape_Island/Texture/Water/Water/T_DetailWater01_Normal",
        "/Game/Zenscape_Island/Texture/Water/Water/T_StylizedWater_Ocean_DP",
        "/Game/Zenscape_Island/Texture/Water/Water/T_StylizedWater_Ocean_N",
    ),
    "coral_optional": (
        "/Game/Zenscape_Island/Model/Plants/SM_Coral_01",
    ),
    "cloud_conditional": (
        "/Game/Zenscape_Island/Material/Clouds/MI_VolumetricCloud_S",
        "/Game/Zenscape_Island/Material/Clouds/MM_StylizedVolumetricClouds",
        "/Game/Zenscape_Island/Texture/Clouds/Greyscale/MT_Greyscale_01",
        "/Game/Zenscape_Island/Texture/Clouds/Greyscale/MT_LowBlurredNoise",
        "/Game/Zenscape_Island/Texture/Clouds/VolumeTextures/VT_Voronoi",
    ),
}

EXPECTED_SEEDS = {
    "/Game/Zenscape_Island/Texture/Landscape/T_Sand_Stylized_BaseColor": (
        "Texture2D",
        4_915_934,
        "912E9BFFC157BD7FD785520815300EBD08BFA64DA934322E91123DFA31E6D705",
    ),
    "/Game/Zenscape_Island/Texture/Landscape/T_Sand_Stylized_Normalsand_04_normal_dx_2k": (
        "Texture2D",
        4_442_298,
        "7EC9E59A8DE4599BFBC0CA8C14A203CFF15B62D29CEF6032688C8F1AF4B53581",
    ),
    "/Game/Zenscape_Island/Texture/Landscape/T_Sand_Stylized_Height": (
        "Texture2D",
        5_191_408,
        "AB49F8B8DE2F94A05B2169BA62C7A5F69AA335DD1B07944E8550B3C26641C146",
    ),
    "/Game/Zenscape_Island/Texture/Landscape/T_Sand_AO": (
        "Texture2D",
        5_614_332,
        "4FC402A81C84CC833E3B51D9CD7811EA0D44E3D7B49C90000163B5E0D8F9E5A5",
    ),
    "/Game/Zenscape_Island/Model/Rocks/SM_Cliff_01": (
        "StaticMesh",
        316_046,
        "49A14C32F6F36AF8853337D9714754E318D6AAA7A312AC548090256F17E9EE1D",
    ),
    "/Game/Zenscape_Island/Model/Tree/SM_CoconutTree_01": (
        "StaticMesh",
        152_377,
        "925C3DA342358836CEB7F6EAC0933D2B2742459C0F39CB1FFA8D5EA9E4FE82F9",
    ),
    "/Game/Zenscape_Island/Model/Plants/SM_Plant_01": (
        "StaticMesh",
        56_344,
        "B169632CBB5B73C27616143437B9FD046542260EC60E901E08326453CD46FD7E",
    ),
    "/Game/Zenscape_Island/Texture/Water/Water/T_DetailWater01_Normal": (
        "Texture2D",
        166_301,
        "EF46E4D6C3E7C64477FBCCEF86F40C72C20EF12F1811B871BA60BCB5D01403EC",
    ),
    "/Game/Zenscape_Island/Texture/Water/Water/T_StylizedWater_Ocean_DP": (
        "Texture2D",
        1_140_452,
        "9962892A7370EEEBF03E589321820A277DE8700465FD5598F2508CF7A344A565",
    ),
    "/Game/Zenscape_Island/Texture/Water/Water/T_StylizedWater_Ocean_N": (
        "Texture2D",
        1_231_099,
        "6AADF08B60B432594159A304695E3226E6537C152BD9CEB7C766DEE58C227D32",
    ),
    "/Game/Zenscape_Island/Model/Plants/SM_Coral_01": (
        "StaticMesh",
        23_931,
        "D3889034815975E9819CF9439FB657E0D04E139A0EF95555EFA6DE9F8C877CEA",
    ),
    "/Game/Zenscape_Island/Material/Clouds/MI_VolumetricCloud_S": (
        "MaterialInstanceConstant",
        12_525,
        "AD043D1172E61CC23B5D91EAB9FA20BB1BBA5066026081F0AFB2CF97F428C651",
    ),
    "/Game/Zenscape_Island/Material/Clouds/MM_StylizedVolumetricClouds": (
        "Material",
        55_031,
        "6902D73F37027CEDC7F5F70FF51C40A34191B2A6BC1F754776AE63C63A620BA5",
    ),
    "/Game/Zenscape_Island/Texture/Clouds/Greyscale/MT_Greyscale_01": (
        "Texture2D",
        10_850,
        "6BFA1722E9FECD2C0494D9ACF973F3A86B1B4EB4C3E74A611D58F846F1750245",
    ),
    "/Game/Zenscape_Island/Texture/Clouds/Greyscale/MT_LowBlurredNoise": (
        "Texture2D",
        8_411,
        "D6DD9D76AA945397E71D5191E18A79B268A8AFABCBA8909A42C33679C865818C",
    ),
    "/Game/Zenscape_Island/Texture/Clouds/VolumeTextures/VT_Voronoi": (
        "VolumeTexture",
        15_117_356,
        "FEA4E994E8D8C3E1B9503B9339ED566952E0F8265A6609142AC955E700DF606F",
    ),
}


class ProbeError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _project_file_for_package(package_name: str) -> Path | None:
    if not package_name.startswith("/Game/"):
        return None
    relative = package_name[len("/Game/") :].replace("/", os.sep)
    content = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir()))
    for suffix in (".uasset", ".umap"):
        candidate = content / (relative + suffix)
        if candidate.is_file():
            return candidate
    return None


def _class_name(asset_data: object) -> str:
    value = getattr(asset_data, "asset_class_path", "")
    asset_name = str(getattr(value, "asset_name", "")).strip()
    if asset_name:
        return asset_name
    text = str(value)
    return text.rsplit(".", 1)[-1].rstrip("')")


def _object_path(asset_data: object) -> str:
    package = str(asset_data.package_name)
    asset = str(asset_data.asset_name)
    return f"{package}.{asset}"


def _dirty_package_names() -> dict[str, list[str]]:
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


def _package_records(registry: object, package_names: set[str]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for package_name in sorted(package_names):
        file_path = _project_file_for_package(package_name)
        if file_path is None:
            raise ProbeError(f"closure package has no local project file: {package_name}")
        assets = list(registry.get_assets_by_package_name(unreal.Name(package_name)) or [])
        if not assets:
            raise ProbeError(f"closure package has no Asset Registry records: {package_name}")
        records.append(
            {
                "package_name": package_name,
                "relative_content_path": str(
                    file_path.relative_to(
                        Path(
                            unreal.Paths.convert_relative_path_to_full(
                                unreal.Paths.project_content_dir()
                            )
                        )
                    )
                ).replace("\\", "/"),
                "bytes": file_path.stat().st_size,
                "sha256": _sha256(file_path),
                "assets": [
                    {
                        "object_path": _object_path(asset_data),
                        "class": _class_name(asset_data),
                    }
                    for asset_data in sorted(assets, key=_object_path)
                ],
            }
        )
    return records


def _query_group(registry: object, group_name: str, seeds: tuple[str, ...]) -> dict[str, object]:
    options = unreal.AssetRegistryDependencyOptions(
        include_soft_package_references=True,
        include_hard_package_references=True,
        include_searchable_names=False,
        include_soft_management_references=True,
        include_hard_management_references=True,
    )
    pending = list(seeds)
    closure: set[str] = set()
    edges: set[tuple[str, str]] = set()
    leaves: set[str] = set()

    while pending:
        package_name = pending.pop()
        if package_name in closure:
            continue
        closure.add(package_name)
        for dependency in registry.get_dependencies(
            unreal.Name(package_name), options
        ) or []:
            dependency_name = str(dependency)
            edges.add((package_name, dependency_name))
            if dependency_name.startswith(PACK_ROOT + "/"):
                if dependency_name not in closure:
                    pending.append(dependency_name)
            else:
                leaves.add(dependency_name)

    missing_game_leaves = sorted(
        dependency
        for dependency in leaves
        if dependency.startswith("/Game/")
        and not unreal.EditorAssetLibrary.does_asset_exist(dependency)
    )
    existing_game_leaves = sorted(
        dependency
        for dependency in leaves
        if dependency.startswith("/Game/")
        and unreal.EditorAssetLibrary.does_asset_exist(dependency)
    )

    loaded_objects: list[dict[str, str]] = []
    for package_name in sorted(closure):
        asset_records = list(
            registry.get_assets_by_package_name(unreal.Name(package_name)) or []
        )
        if not asset_records:
            raise ProbeError(f"no assets to load for {package_name}")
        for asset_data in sorted(asset_records, key=_object_path):
            loaded = asset_data.get_asset()
            if loaded is None:
                raise ProbeError(f"bounded load failed: {_object_path(asset_data)}")
            loaded_objects.append(
                {
                    "object_path": loaded.get_path_name(),
                    "class": loaded.get_class().get_name(),
                }
            )

    return {
        "group": group_name,
        "seeds": list(seeds),
        "closure_packages": _package_records(registry, closure),
        "closure_count": len(closure),
        "edges": [
            {"source": source, "dependency": dependency}
            for source, dependency in sorted(edges)
        ],
        "edge_count": len(edges),
        "external_leaves": sorted(leaves),
        "existing_external_game_leaves": existing_game_leaves,
        "missing_external_game_leaves": missing_game_leaves,
        "script_leaves": sorted(
            dependency for dependency in leaves if dependency.startswith("/Script/")
        ),
        "engine_leaves": sorted(
            dependency for dependency in leaves if dependency.startswith("/Engine/")
        ),
        "loaded_objects": loaded_objects,
        "load_count": len(loaded_objects),
        "eligible_for_staging": not missing_game_leaves,
    }


def main() -> None:
    output_text = os.environ.get(OUTPUT_ENV, "").strip()
    expected_root_text = os.environ.get(EXPECTED_PROJECT_ROOT_ENV, "").strip()
    if not output_text or not expected_root_text:
        raise ProbeError(f"{OUTPUT_ENV} and {EXPECTED_PROJECT_ROOT_ENV} are required")

    output = Path(output_text).resolve()
    expected_root = Path(expected_root_text).resolve()
    project_file = Path(
        unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())
    ).resolve()
    if project_file.parent != expected_root:
        raise ProbeError(
            f"wrong project root: expected {expected_root}, got {project_file.parent}"
        )
    if output.exists():
        raise ProbeError(f"refusing to overwrite output: {output}")
    if expected_root in output.parents or output == expected_root:
        raise ProbeError("diagnostic output must be outside the Unreal project")

    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    registry.search_all_assets(True)

    seed_records: list[dict[str, object]] = []
    for package_name, (expected_class, expected_bytes, expected_sha256) in sorted(
        EXPECTED_SEEDS.items()
    ):
        if not unreal.EditorAssetLibrary.does_asset_exist(package_name):
            raise ProbeError(f"seed asset missing: {package_name}")
        file_path = _project_file_for_package(package_name)
        if file_path is None:
            raise ProbeError(f"seed file missing: {package_name}")
        actual_bytes = file_path.stat().st_size
        actual_sha256 = _sha256(file_path)
        assets = list(
            registry.get_assets_by_package_name(unreal.Name(package_name)) or []
        )
        if len(assets) != 1:
            raise ProbeError(
                f"seed package must contain exactly one registry asset: {package_name}"
            )
        actual_class = _class_name(assets[0])
        if (
            actual_bytes != expected_bytes
            or actual_sha256 != expected_sha256
            or actual_class != expected_class
        ):
            raise ProbeError(
                "seed identity mismatch: "
                f"{package_name} class={actual_class} bytes={actual_bytes} "
                f"sha256={actual_sha256}"
            )
        seed_records.append(
            {
                "package_name": package_name,
                "class": actual_class,
                "bytes": actual_bytes,
                "sha256": actual_sha256,
            }
        )

    dirty_before = _dirty_package_names()
    if dirty_before != {"content": [], "maps": []}:
        raise ProbeError(f"project was dirty before read-only probe: {dirty_before}")

    groups = [
        _query_group(registry, group_name, seeds)
        for group_name, seeds in GROUPS.items()
    ]

    dirty_after = _dirty_package_names()
    if dirty_after != dirty_before:
        raise ProbeError(
            f"dirty package state changed during read-only probe: "
            f"before={dirty_before} after={dirty_after}"
        )

    report = {
        "schema_version": 1,
        "probe": "tropical_planetary_biome_ue58_asset_registry_closure",
        "engine_version": unreal.SystemLibrary.get_engine_version(),
        "project_file": str(project_file).replace("\\", "/"),
        "pack_root": PACK_ROOT,
        "dependency_options": {
            "soft_package_references": True,
            "hard_package_references": True,
            "searchable_names": False,
            "soft_management_references": True,
            "hard_management_references": True,
        },
        "seed_records": seed_records,
        "groups": groups,
        "dirty_before": dirty_before,
        "dirty_after": dirty_after,
        "saved_packages": 0,
        "mutation_calls": 0,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    unreal.log_warning(
        "RED_TROPICAL_CLOSURE_READY "
        f"groups={len(groups)} output={str(output).replace(os.sep, '/')}"
    )


main()
