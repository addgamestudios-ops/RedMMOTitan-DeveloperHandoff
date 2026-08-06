"""Prepare the isolated T02 So Stylized sparkle mask probe.

This script is intentionally fail-closed. It changes exactly one project-owned
diagnostic material instance and only when the explicit write flag is present.
It never saves vendor content, the production biome material, or a map.

Expected Unreal invocation (only after the host resource gate is safe):

    UnrealEditor-Cmd.exe D:/RedMMOTitan/Titan.uproject \
      -run=pythonscript \
      -script=D:/RedMMOTitan/Build/Automation/prepare_red_sand_sparkle_mask_probe.py \
      -RedSandSparkleMaskProbeWrite
"""

from __future__ import annotations

import hashlib
import json
import math
import pathlib
import shutil
from typing import Any, Dict, Mapping

try:
    import unreal  # type: ignore
except ModuleNotFoundError:  # Allows offline policy tests without Unreal.
    unreal = None


WRITE_FLAG = "-RedSandSparkleMaskProbeWrite"
TARGET_ASSET = (
    "/Game/RedMMO/Materials/DesertSparkleTest/"
    "MI_PlanetBiome_DesertSparkle_T02"
)
ALLOWED_PACKAGE_ROOT = "/Game/RedMMO/Materials/DesertSparkleTest/"
EXPECTED_PARENT = (
    "/Game/RedMMO/Materials/DesertSparkleTest/M_Planet_DesertSparkle_T02"
)
DIAGNOSTIC_BACKUP_ROOT = pathlib.Path(
    "D:/RedMMOTitanWindowsData/Diagnostics/SandSparkleMaskProbe/AssetBackups"
)

DESIRED_SWITCHES = {
    "SimpleSparkle?": True,
    "SparklShrinkNear?": False,  # Exact vendor spelling.
}
HELD_SWITCHES = {
    "DesertSandSparkle?": True,
    "SandRippleNormals?": True,
    "SparkleProject3D?": False,
    "SparkleIntensityVariance?": True,
    "SparkleDayAndWeather?": False,
    "NeedWorldRotation?": True,
}
HELD_SCALARS = {
    "Desert Sand Scale": 1024.0,
    "Desert Sand Normal Texture Scale": 2400.0,
    "Desert Sparkle Scale": 1600.0,
    "Desert Sparkle Brightness": 120.0,
    "Desert Sparkle Contrast": 8.0,
    "Desert Sparkle Tolerance": 0.75,
    "Desert Sparkle Speed": 1.0,
    "Desert Sparkle Fade Start": 1000.0,
    "Desert Sparkle Fade End": 5000.0,
    "Desert Sparkle Shrink Amount": 0.3,
    "Desert Sparkle Shrink Near Distance": 500.0,
    "Desert Sparkle Shrink Far Distance": 2500.0,
}
HELD_VECTOR = {
    "name": "Desert Sparkle  Color",  # Vendor parameter contains two spaces.
    "value": (1.0, 0.78, 0.35, 1.0),
}

PROTECTED_PACKAGES = (
    "/Game/SoStylized/Materials/MF_DesertSand",
    "/Game/SoStylized/Materials/MF_Sparkle",
    "/Game/RedMMO/Materials/DesertSparkleTest/MFI_DesertSandSparkle_T02",
    "/Game/RedMMO/Materials/DesertSparkleTest/M_Planet_DesertSparkle_T02",
    "/Game/RedMMO/Materials/MI_PlanetBiome_RED",
    "/Game/RedMMO/Maps/RedPlanetGen_50km_Test",
)


def _package_from_object_path(path: str) -> str:
    return str(path).split(".", 1)[0]


def _has_write_flag(command_line: str) -> bool:
    return WRITE_FLAG.lower() in str(command_line).lower().split()


def _close(actual: float, expected: float) -> bool:
    return math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=1e-5)


def validate_snapshot(snapshot: Mapping[str, Any], allow_probe_state: bool) -> None:
    """Validate every held parameter and reject partial probe permutations."""

    switches = snapshot["switches"]
    scalars = snapshot["scalars"]
    vector = snapshot["vector"]

    for name, expected in HELD_SWITCHES.items():
        entry = switches[name]
        if not entry["overridden"] or bool(entry["value"]) is not expected:
            raise RuntimeError(f"Held switch drift: {name}={entry}")

    for name, expected in HELD_SCALARS.items():
        entry = scalars[name]
        if not entry["overridden"] or not _close(entry["value"], expected):
            raise RuntimeError(f"Held scalar drift: {name}={entry}")

    if not vector["overridden"]:
        raise RuntimeError("Held sparkle color is not overridden")
    if any(
        not _close(actual, expected)
        for actual, expected in zip(vector["value"], HELD_VECTOR["value"])
    ):
        raise RuntimeError(f"Held sparkle color drift: {vector['value']}")

    pair = (
        bool(switches["SimpleSparkle?"]["value"]),
        bool(switches["SparklShrinkNear?"]["value"]),
    )
    pair_overridden = (
        bool(switches["SimpleSparkle?"]["overridden"]),
        bool(switches["SparklShrinkNear?"]["overridden"]),
    )
    allowed_pairs = {(False, True)}
    if allow_probe_state:
        allowed_pairs.add((True, False))
    if pair not in allowed_pairs or pair_overridden != (True, True):
        raise RuntimeError(
            "Unexpected or partial mask-probe state: "
            f"values={pair} overridden={pair_overridden}"
        )


def _require_unreal() -> None:
    if unreal is None:
        raise RuntimeError("This write script must run inside Unreal Editor")


def _parameter_name_map(names: Any) -> Dict[str, Any]:
    return {str(name): name for name in names}


def _capture_snapshot(instance: Any) -> Dict[str, Any]:
    editing = unreal.MaterialEditingLibrary
    switch_names = _parameter_name_map(editing.get_static_switch_parameter_names(instance))
    scalar_names = _parameter_name_map(editing.get_scalar_parameter_names(instance))
    vector_names = _parameter_name_map(editing.get_vector_parameter_names(instance))

    required_switches = set(HELD_SWITCHES) | set(DESIRED_SWITCHES)
    missing_switches = sorted(required_switches - set(switch_names))
    missing_scalars = sorted(set(HELD_SCALARS) - set(scalar_names))
    if missing_switches or missing_scalars or HELD_VECTOR["name"] not in vector_names:
        raise RuntimeError(
            "T02 parameter interface drift: "
            f"missing_switches={missing_switches} "
            f"missing_scalars={missing_scalars} "
            f"missing_vector={HELD_VECTOR['name'] not in vector_names}"
        )

    switches: Dict[str, Any] = {}
    for text in sorted(required_switches):
        name = switch_names[text]
        switches[text] = {
            "value": bool(
                editing.get_material_instance_static_switch_parameter_value(instance, name)
            ),
            "overridden": bool(
                editing.is_material_instance_parameter_overridden(instance, name)
            ),
        }

    scalars: Dict[str, Any] = {}
    for text in sorted(HELD_SCALARS):
        name = scalar_names[text]
        scalars[text] = {
            "value": float(
                editing.get_material_instance_scalar_parameter_value(instance, name)
            ),
            "overridden": bool(
                editing.is_material_instance_parameter_overridden(instance, name)
            ),
        }

    color_name = vector_names[HELD_VECTOR["name"]]
    color = editing.get_material_instance_vector_parameter_value(instance, color_name)
    vector = {
        "value": (float(color.r), float(color.g), float(color.b), float(color.a)),
        "overridden": bool(
            editing.is_material_instance_parameter_overridden(instance, color_name)
        ),
    }
    return {"switches": switches, "scalars": scalars, "vector": vector}


def _dirty_package_paths() -> set[str]:
    dirty = []
    dirty.extend(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    dirty.extend(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    return {_package_from_object_path(package.get_path_name()) for package in dirty}


def _project_root() -> pathlib.Path:
    return pathlib.Path(
        unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
    ).resolve()


def _resolve_package_file(project_root: pathlib.Path, package: str) -> pathlib.Path:
    if not package.startswith("/Game/"):
        raise RuntimeError(f"Not a project package: {package}")
    base = project_root / "Content" / package[len("/Game/") :]
    candidates = [pathlib.Path(str(base) + extension) for extension in (".uasset", ".umap")]
    existing = [candidate for candidate in candidates if candidate.is_file()]
    if len(existing) != 1:
        raise RuntimeError(
            "Expected exactly one .uasset/.umap for project package "
            f"{package}; found={existing}"
        )
    return existing[0]


def _package_file(package: str) -> pathlib.Path:
    return _resolve_package_file(_project_root(), package)


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _protected_hashes() -> Dict[str, str]:
    result: Dict[str, str] = {}
    for package in PROTECTED_PACKAGES:
        path = _package_file(package)
        if not path.is_file():
            raise RuntimeError(f"Protected asset is missing: {path}")
        result[package] = _sha256(path)
    return result


def _backup_target(source: pathlib.Path) -> pathlib.Path:
    digest = _sha256(source)
    DIAGNOSTIC_BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    destination = DIAGNOSTIC_BACKUP_ROOT / f"{source.stem}_{digest}.uasset"
    if not destination.exists():
        shutil.copy2(source, destination)
    if _sha256(destination) != digest:
        raise RuntimeError(f"Probe rollback backup hash mismatch: {destination}")
    return destination


def _restore_target_file(source_backup: pathlib.Path, target: pathlib.Path) -> None:
    expected = _sha256(source_backup)
    shutil.copy2(source_backup, target)
    actual = _sha256(target)
    if actual != expected:
        raise RuntimeError(
            f"Rollback restore hash mismatch: expected={expected} actual={actual}"
        )


def _validate_dirty_after_edit(dirty: set[str], already_prepared: bool) -> None:
    expected = set() if already_prepared else {TARGET_ASSET}
    if dirty != expected:
        raise RuntimeError(
            f"Unexpected dirty packages: expected={expected} actual={dirty}"
        )


def main() -> None:
    _require_unreal()
    command_line = str(unreal.SystemLibrary.get_command_line())
    if not _has_write_flag(command_line):
        raise RuntimeError(f"Refusing write without explicit {WRITE_FLAG} flag")
    if TARGET_ASSET != ALLOWED_PACKAGE_ROOT + "MI_PlanetBiome_DesertSparkle_T02":
        raise RuntimeError(f"Probe target escaped its exact allowlist: {TARGET_ASSET}")

    dirty_before = _dirty_package_paths()
    if dirty_before:
        raise RuntimeError(f"Refusing to run with pre-existing dirty packages: {dirty_before}")

    target = unreal.load_asset(TARGET_ASSET)
    if target is None or target.get_class().get_name() != "MaterialInstanceConstant":
        raise RuntimeError(f"Missing or wrong-class probe target: {TARGET_ASSET}")
    parent = target.get_editor_property("parent")
    parent_package = _package_from_object_path(parent.get_path_name() if parent else "")
    if parent_package != EXPECTED_PARENT:
        raise RuntimeError(
            f"T02 parent drift: expected={EXPECTED_PARENT} actual={parent_package}"
        )

    before = _capture_snapshot(target)
    validate_snapshot(before, allow_probe_state=True)
    already_prepared = all(
        bool(before["switches"][name]["value"]) is desired
        and bool(before["switches"][name]["overridden"])
        for name, desired in DESIRED_SWITCHES.items()
    )
    protected_before = _protected_hashes()
    target_file = _package_file(TARGET_ASSET)
    target_hash_before = _sha256(target_file)
    backup = _backup_target(target_file) if not already_prepared else None

    editing = unreal.MaterialEditingLibrary
    try:
        if not already_prepared:
            # UE 5.8's setter currently returns false even after a successful write;
            # batch both writes with updates disabled, then compile one permutation.
            association = unreal.MaterialParameterAssociation.GLOBAL_PARAMETER
            editing.set_material_instance_static_switch_parameter_value(
                target, "SimpleSparkle?", True, association, False
            )
            editing.set_material_instance_static_switch_parameter_value(
                target, "SparklShrinkNear?", False, association, False
            )
            editing.update_material_instance(target)

        after = _capture_snapshot(target)
        validate_snapshot(after, allow_probe_state=True)
        for name, desired in DESIRED_SWITCHES.items():
            entry = after["switches"][name]
            if bool(entry["value"]) is not desired or not entry["overridden"]:
                raise RuntimeError(
                    f"Mask-probe write did not become effective: {name}={entry}"
                )

        _validate_dirty_after_edit(_dirty_package_paths(), already_prepared)
        if not already_prepared:
            if not unreal.EditorAssetLibrary.save_asset(
                TARGET_ASSET, only_if_is_dirty=False
            ):
                raise RuntimeError(f"Failed to save exact probe target: {TARGET_ASSET}")

        dirty_after_save = _dirty_package_paths()
        if dirty_after_save:
            raise RuntimeError(f"Dirty packages remain after exact save: {dirty_after_save}")
        protected_after = _protected_hashes()
        if protected_after != protected_before:
            changed = sorted(
                package
                for package in PROTECTED_PACKAGES
                if protected_before[package] != protected_after[package]
            )
            raise RuntimeError(f"Protected package hash changed: {changed}")
    except Exception as exc:
        rollback_message = "target file unchanged"
        if backup is not None and target_file.is_file():
            if _sha256(target_file) != target_hash_before:
                _restore_target_file(backup, target_file)
                rollback_message = f"target file restored from {backup}"
        raise RuntimeError(f"Mask-probe preparation failed; {rollback_message}: {exc}") from exc

    target_hash_after = _sha256(target_file)
    unreal.log(
        "RED_SAND_MASK_PROBE_PREPARED "
        + json.dumps(
            {
                "target": TARGET_ASSET,
                "target_hash_before": target_hash_before,
                "target_hash_after": target_hash_after,
                "rollback_backup": str(backup) if backup is not None else None,
                "desired_switches": DESIRED_SWITCHES,
                "changed": not already_prepared,
                "protected_hash_count": len(protected_after),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
