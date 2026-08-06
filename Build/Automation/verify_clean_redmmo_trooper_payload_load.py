"""No-save UE 5.8 load verification for the A12+A13 clean Trooper payload."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path

import unreal


A12_MANIFEST = Path(
    r"D:/RedMMOTitanWindowsData/Rollback/RedMMO_TitanStrictPayload_A12_20260803_060715/strict_payload_manifest_post.json"
)
A13_MANIFEST = Path(
    r"D:/RedMMOTitanWindowsData/Rollback/RedMMO_TitanLocomotionPayload_A13_20260803_061035/locomotion_payload_manifest_post.json"
)
EXPECTED_MANIFEST_HASHES = {
    A12_MANIFEST: "5A1FE625098BC233EE4B8D5BB995FDC103705B41BC894AD64A3C92C333C80AEA",
    A13_MANIFEST: "8E8D40724FEA5BB27DE21F3ABA92E6E11A14F67D72A8A1F488488A3346E929CD",
}
EXPECTED_PROJECT = Path(r"D:/RedMMOTitanWindowsData/Projects/RedMMO/RedMMO.uproject")
OUTPUT_ENV = "REDMMO_TROOPER_LOAD_REPORT"
FORBIDDEN_PACKAGE_FRAGMENTS = (
    "/Game/Action_Male_and_Female/",
    "/Game/RedMMO/Characters/BP_RedGameplayCharacter",
    "/Game/RedMMO/UI/BP_RedMultiplayerPlayerController",
    "/Game/RedMMO/Characters/ABP_RedTrooperFemale",
    "/Game/RedMMO/Characters/CR_RedTrooperFocalAim",
    "/Maps/",
)


class VerificationError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def read_json(path: Path) -> dict:
    if not path.is_file():
        raise VerificationError(f"missing manifest: {path}")
    expected = EXPECTED_MANIFEST_HASHES[path]
    actual = sha256(path)
    if actual != expected:
        raise VerificationError(f"manifest hash drift: {path} {actual} != {expected}")
    return json.loads(path.read_text(encoding="utf-8"))


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


def class_path(asset_data: object) -> str:
    return str(getattr(asset_data, "asset_class_path", ""))


def main() -> None:
    output_text = os.environ.get(OUTPUT_ENV, "").strip()
    if not output_text:
        raise VerificationError(f"{OUTPUT_ENV} is required")
    output = Path(output_text)
    if output.exists():
        raise VerificationError(f"refusing to overwrite report: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path()))
    if project.resolve() != EXPECTED_PROJECT.resolve():
        raise VerificationError(f"wrong project: {project}")

    manifests = [read_json(A12_MANIFEST), read_json(A13_MANIFEST)]
    entries: dict[str, dict] = {}
    for manifest in manifests:
        for item in manifest.get("files", []):
            package_name = str(item.get("package_name", ""))
            if not package_name.startswith("/Game/"):
                raise VerificationError(f"invalid package name: {package_name}")
            if any(fragment in package_name for fragment in FORBIDDEN_PACKAGE_FRAGMENTS):
                raise VerificationError(f"forbidden package in payload: {package_name}")
            if str(item.get("relative_content_path", "")).lower().endswith(".umap"):
                raise VerificationError(f"map package in payload: {package_name}")
            prior = entries.get(package_name)
            if prior is not None and prior.get("sha256") != item.get("sha256"):
                raise VerificationError(f"conflicting duplicate package: {package_name}")
            entries[package_name] = item

    if len(entries) != 135:
        raise VerificationError(f"expected 135 unique packages, found {len(entries)}")

    content_root = EXPECTED_PROJECT.parent / "Content"
    for package_name, item in entries.items():
        relative_path = Path(str(item["relative_content_path"]))
        destination = content_root / relative_path
        if not destination.is_file():
            raise VerificationError(f"missing destination file: {destination}")
        actual_hash = sha256(destination)
        if actual_hash != str(item["sha256"]):
            raise VerificationError(
                f"destination hash drift: {package_name} {actual_hash} != {item['sha256']}"
            )

    before = dirty_packages()
    if before != {"content": [], "maps": []}:
        raise VerificationError(f"pre-existing dirty packages: {before}")

    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    registry.wait_for_completion()
    loaded = []
    for package_name in sorted(entries):
        asset_data_items = list(registry.get_assets_by_package_name(unreal.Name(package_name)) or [])
        if not asset_data_items:
            raise VerificationError(f"package absent from Asset Registry: {package_name}")
        classes = []
        object_paths = []
        for asset_data in asset_data_items:
            cls = class_path(asset_data)
            if "FocalRig" in cls:
                raise VerificationError(f"FocalRig class in accepted payload: {package_name} {cls}")
            asset = asset_data.get_asset()
            if asset is None:
                raise VerificationError(
                    f"asset load returned None: {package_name}.{asset_data.asset_name}"
                )
            classes.append(cls)
            object_paths.append(str(asset.get_path_name()))
        loaded.append(
            {
                "package_name": package_name,
                "asset_count": len(asset_data_items),
                "classes": sorted(set(classes)),
                "object_paths": sorted(object_paths),
            }
        )

    after = dirty_packages()
    if after != before:
        raise VerificationError(f"dirty package drift: before={before} after={after}")

    payload = {
        "schema_version": 1,
        "captured_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "result": "pass_all_135_packages_loaded_no_dirty_state",
        "evidence_class": "automation",
        "project": str(project).replace("\\", "/"),
        "entry_map": "/Engine/Maps/Entry",
        "manifests": [
            {"path": str(path).replace("\\", "/"), "sha256": EXPECTED_MANIFEST_HASHES[path]}
            for path in (A12_MANIFEST, A13_MANIFEST)
        ],
        "package_count": len(entries),
        "loaded_asset_count": sum(item["asset_count"] for item in loaded),
        "packages": loaded,
        "dirty_before": before,
        "dirty_after": after,
        "forbidden_payloads_absent": True,
        "claim_limit": (
            "Package load and no-dirty automation only. This does not compile a Blueprint, "
            "bind a pawn/GameMode/map, run PIE, render visuals, or prove gameplay, audio, "
            "replication, multiplayer, cook, package, or standalone behavior."
        ),
    }
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    unreal.log("REDMMO_TROOPER_PAYLOAD_LOAD_RESULT=PASS")
    unreal.log(f"REDMMO_TROOPER_PAYLOAD_LOAD_PACKAGES={len(entries)}")
    unreal.log(f"REDMMO_TROOPER_PAYLOAD_LOAD_REPORT={output}")


try:
    main()
except Exception as exc:
    unreal.log_error(f"REDMMO_TROOPER_PAYLOAD_LOAD_RESULT=FAIL {exc}")
    raise
