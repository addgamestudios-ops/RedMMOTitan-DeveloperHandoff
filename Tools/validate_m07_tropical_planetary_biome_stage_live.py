"""Live-editor validation for the isolated M07 Tropical planetary-biome stage.

This is a deliberately narrow, asynchronous live-editor script.  It must run
only in the exact UE 5.8 D3D12 scratch project/map produced by
``create_m07_tropical_planetary_biome_stage.py``.  It:

* authenticates the authoring audit, pre-snap map, protected maps/assets, and
  the reviewed Tropical root assets;
* creates one external, no-clobber, byte-for-byte backup of the staging map;
* waits for PlanetGen near region 15 by ticking the editor rather than sleeping;
* selects exactly the 17 managed static-mesh actors;
* invokes only
  RedMMOEditorTools.snap_selected_static_mesh_actors_to_planet_surface(0.0);
* proves only those transforms changed, with scale/collision contracts intact;
* saves only the isolated staging map; and
* sequences three reversible viewport cameras and explicit HighResShot requests.

The script never enters PIE and never applies vendor water, cloud, sky,
atmosphere, sun, fog, post-process, landscape, RVT, or MM_Sun assets.  Each
HighResShot must produce its exact external, non-empty output and remain
size-stable for several ticks before the viewport can move.  Pixel quality is
still intentionally left pending external inspection.

Required environment variables:

    REDMMO_M07_TROPICAL_LIVE_PROJECT_FILE
    REDMMO_M07_TROPICAL_STAGE_AUDIT_PATH
    REDMMO_M07_TROPICAL_LIVE_DIAGNOSTICS_DIR
    REDMMO_M07_TROPICAL_LIVE_AUDIT_OUTPUT
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import re
import stat
import time
import traceback
from pathlib import Path
from typing import Any

import unreal


PROJECT_FILE_ENV = "REDMMO_M07_TROPICAL_LIVE_PROJECT_FILE"
STAGE_AUDIT_ENV = "REDMMO_M07_TROPICAL_STAGE_AUDIT_PATH"
DIAGNOSTICS_DIR_ENV = "REDMMO_M07_TROPICAL_LIVE_DIAGNOSTICS_DIR"
LIVE_AUDIT_ENV = "REDMMO_M07_TROPICAL_LIVE_AUDIT_OUTPUT"

SCRATCH_ROOT = Path(r"D:\RedMMOTitanWindowsData\Scratch")
DIAGNOSTICS_ROOT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics")

DESTINATION_MAP = (
    "/Game/RedMMO/Maps/Tests/"
    "RedPlanetGen_50km_FusedPrototype_M07_TropicalBiomeStage_V1"
)
DESTINATION_MAP_RELATIVE = Path(
    "Content",
    "RedMMO",
    "Maps",
    "Tests",
    "RedPlanetGen_50km_FusedPrototype_M07_TropicalBiomeStage_V1.umap",
)

EXPECTED_STAGE_AUDIT_SHA256 = (
    "1A1A0A98030D1A7BC6AE1F2617805E9E1080D367051266BFCFF04335CA446ADA"
)
EXPECTED_PRE_SNAP_MAP_SHA256 = (
    "FBB0EED0191099B99833CA829834BA08DB5786204ED27A04BA38F053B4F1B491"
)
EXPECTED_PRE_SNAP_MAP_BYTES = 12_497_095
EXPECTED_MANAGED_ACTOR_COUNT = 17

REGION_INDEX = 15
EXPECTED_REGION_SEED = 3_354_735_782
EXPECTED_REGION_ARCHETYPE = "CoralCanopyCoast"
EXPECTED_REGION_SITE = (
    0.13523942097797426,
    -0.9796746527362116,
    -0.14814814814814814,
)
EXPECTED_PLANET_RADIUS_CM = 795_774.7154594767
MAX_AUTHORED_HEIGHT_CM = 30_000.0
MANAGED_TAG = "RedMMO_M07_TropicalBiomeStage_V1"
PENDING_SNAP_TAG = "PendingNativePlanetSnap"
COMPLETE_SNAP_TAG = "NativePlanetSnapComplete"
CANONICAL_PROJECT_ROOT = Path("D:/RedMMOTitan")

REQUIRED_DISABLED_PLUGINS = (
    "AndroidFileServer",
    "AIAssistant",
    "EditorTelemetry",
    "ModelContextProtocol",
    "Nwiro",
    "NwiroIntegrationKit",
    "OnlineSubsystemSteam",
    "SteamIntegrationKit",
    "SteamSockets",
    "UnrealAIIntegrationPlatform",
)

EXPECTED_ACTOR_LABELS = {
    "M07_Tropical_CliffGate",
    "M07_Tropical_CoconutA",
    "M07_Tropical_CoconutB",
    "M07_Tropical_CoconutC",
    "M07_Tropical_CoconutD",
    "M07_Tropical_CoconutE",
    "M07_Tropical_PlantA",
    "M07_Tropical_PlantB",
    "M07_Tropical_PlantC",
    "M07_Tropical_PlantD",
    "M07_Tropical_PlantE",
    "M07_Tropical_PlantF",
    "M07_Tropical_PlantG",
    "M07_Tropical_PlantH",
    "M07_Tropical_CoralA",
    "M07_Tropical_CoralB",
    "M07_Tropical_CoralC",
}

PROTECTED_PROJECT_FILES = {
    Path("Content/RedMMO/Maps/RedPlanetGen.umap"):
        "1DF9E6ED913A267875F1EF452F6ED51DAF337DBBAAE4C6EC3379EA6299346724",
    Path("Content/RedMMO/Maps/RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path("Content/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
    Path("Content/RedMMO/Environment/DA_RED_Planet50Km_FusedHeightfield.uasset"):
        "412E26B75DAD95CE0EF4FA63BFF21CCA0EDB755B5D08BA1A4CFA3EEFEC06E562",
}

VENDOR_ROOT_FILES = {
    Path("Content/Zenscape_Island/Model/Rocks/SM_Cliff_01.uasset"):
        (316_046, "49A14C32F6F36AF8853337D9714754E318D6AAA7A312AC548090256F17E9EE1D"),
    Path("Content/Zenscape_Island/Model/Tree/SM_CoconutTree_01.uasset"):
        (152_377, "925C3DA342358836CEB7F6EAC0933D2B2742459C0F39CB1FFA8D5EA9E4FE82F9"),
    Path("Content/Zenscape_Island/Model/Plants/SM_Plant_01.uasset"):
        (56_344, "B169632CBB5B73C27616143437B9FD046542260EC60E901E08326453CD46FD7E"),
    Path("Content/Zenscape_Island/Model/Plants/SM_Coral_01.uasset"):
        (23_931, "D3889034815975E9819CF9439FB657E0D04E139A0EF95555EFA6DE9F8C877CEA"),
    Path("Content/Zenscape_Island/Texture/Landscape/T_Sand_Stylized_BaseColor.uasset"):
        (4_915_934, "912E9BFFC157BD7FD785520815300EBD08BFA64DA934322E91123DFA31E6D705"),
    Path(
        "Content/Zenscape_Island/Texture/Landscape/"
        "T_Sand_Stylized_Normalsand_04_normal_dx_2k.uasset"
    ):
        (4_442_298, "7EC9E59A8DE4599BFBC0CA8C14A203CFF15B62D29CEF6032688C8F1AF4B53581"),
    Path("Content/Zenscape_Island/Texture/Landscape/T_Sand_Stylized_Height.uasset"):
        (5_191_408, "AB49F8B8DE2F94A05B2169BA62C7A5F69AA335DD1B07944E8550B3C26641C146"),
    Path("Content/Zenscape_Island/Texture/Landscape/T_Sand_AO.uasset"):
        (5_614_332, "4FC402A81C84CC833E3B51D9CD7811EA0D44E3D7B49C90000163B5E0D8F9E5A5"),
    Path("Content/Zenscape_Island/Texture/Water/Water/T_DetailWater01_Normal.uasset"):
        (166_301, "EF46E4D6C3E7C64477FBCCEF86F40C72C20EF12F1811B871BA60BCB5D01403EC"),
    Path("Content/Zenscape_Island/Texture/Water/Water/T_StylizedWater_Ocean_DP.uasset"):
        (1_140_452, "9962892A7370EEEBF03E589321820A277DE8700465FD5598F2508CF7A344A565"),
    Path("Content/Zenscape_Island/Texture/Water/Water/T_StylizedWater_Ocean_N.uasset"):
        (1_231_099, "6AADF08B60B432594159A304695E3226E6537C152BD9CEB7C766DEE58C227D32"),
}

MIN_SNAP_SETTLE_SECONDS = 12.0
MIN_SNAP_SETTLE_FRAMES = 240
MAX_SNAP_SETTLE_SECONDS = 45.0
MIN_CAMERA_SETTLE_SECONDS = 2.0
MIN_CAMERA_SETTLE_FRAMES = 45
MAX_SCREENSHOT_WAIT_SECONDS = 60.0
SCREENSHOT_STABLE_TICKS = 5
SCREENSHOT_RESOLUTION = "1920x1080"

BACKUP_FILENAME = (
    "pre_snap_RedPlanetGen_50km_FusedPrototype_"
    "M07_TropicalBiomeStage_V1_FBB0EED0191099B99.umap"
)
SCREENSHOT_FILENAMES = (
    "M07_TropicalBiomeStage_ground.png",
    "M07_TropicalBiomeStage_curvature.png",
    "M07_TropicalBiomeStage_horizon.png",
)


class LiveValidationError(RuntimeError):
    """Fail-closed live validation contract violation."""


_ACTIVE_SESSION: "LiveValidationSession | None" = None


def _norm(path: Path) -> str:
    return os.path.normcase(os.path.realpath(os.fspath(path)))


def _is_under(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((_norm(path), _norm(root))) == _norm(root)
    except ValueError:
        return False


def _assert_no_reparse_points(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if not current.exists():
            continue
        info = os.lstat(current)
        attributes = int(getattr(info, "st_file_attributes", 0))
        if current.is_symlink() or (
            attributes & int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
        ):
            raise LiveValidationError(
                f"reparse point is forbidden in live validation path: {current}"
            )


def _assert_single_link_regular_file(path: Path, *, label: str) -> os.stat_result:
    """Reject symlinks, reparse descendants, devices, and hard-linked inputs."""

    _assert_no_reparse_points(path)
    try:
        info = os.lstat(path)
    except FileNotFoundError as exc:
        raise LiveValidationError(f"{label} is missing: {path}") from exc
    attributes = int(getattr(info, "st_file_attributes", 0))
    if (
        not stat.S_ISREG(info.st_mode)
        or path.is_symlink()
        or attributes
        & int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    ):
        raise LiveValidationError(
            f"{label} must be a regular non-reparse file: {path}"
        )
    if int(info.st_nlink) != 1:
        raise LiveValidationError(
            f"{label} must have exactly one hard link; "
            f"observed st_nlink={info.st_nlink}: {path}"
        )
    return info


def _sha256(path: Path) -> str:
    _assert_single_link_regular_file(path, label="SHA-256 input")
    digest = hashlib.sha256()
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_BINARY", 0)
    )
    try:
        opened_before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_before.st_mode)
            or int(opened_before.st_nlink) != 1
        ):
            raise LiveValidationError(
                f"SHA-256 descriptor is not a single-link regular file: {path}"
            )
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        opened_after = os.fstat(descriptor)
        if (
            int(opened_before.st_size) != int(opened_after.st_size)
            or int(opened_before.st_mtime_ns) != int(opened_after.st_mtime_ns)
            or int(opened_before.st_ino) != int(opened_after.st_ino)
            or int(opened_after.st_nlink) != 1
        ):
            raise LiveValidationError(
                f"SHA-256 input changed through its open descriptor: {path}"
            )
    finally:
        os.close(descriptor)
    path_after = _assert_single_link_regular_file(path, label="SHA-256 input")
    if (
        int(opened_after.st_size) != int(path_after.st_size)
        or int(opened_after.st_mtime_ns) != int(path_after.st_mtime_ns)
        or int(opened_after.st_ino) != int(path_after.st_ino)
    ):
        raise LiveValidationError(
            f"SHA-256 input path identity changed during hashing: {path}"
        )
    return digest.hexdigest().upper()


def _file_record(path: Path) -> dict[str, Any]:
    before = _assert_single_link_regular_file(path, label="authenticated file")
    digest = _sha256(path)
    after = _assert_single_link_regular_file(path, label="authenticated file")
    if (
        int(before.st_size) != int(after.st_size)
        or int(before.st_mtime_ns) != int(after.st_mtime_ns)
        or int(before.st_ino) != int(after.st_ino)
    ):
        raise LiveValidationError(f"file changed while authenticating: {path}")
    return {
        "path": str(path),
        "bytes": int(after.st_size),
        "sha256": digest,
        "st_nlink": int(after.st_nlink),
    }


def _authenticate_file(
    path: Path, *, expected_bytes: int | None, expected_sha256: str, label: str
) -> dict[str, Any]:
    before = _assert_single_link_regular_file(path, label=label)
    actual_bytes = int(before.st_size)
    actual_sha256 = _sha256(path)
    after = _assert_single_link_regular_file(path, label=label)
    if (
        actual_bytes != int(after.st_size)
        or int(before.st_mtime_ns) != int(after.st_mtime_ns)
        or int(before.st_ino) != int(after.st_ino)
    ):
        raise LiveValidationError(f"{label} changed while authenticating: {path}")
    if expected_bytes is not None and actual_bytes != expected_bytes:
        raise LiveValidationError(
            f"{label} length drifted: expected {expected_bytes}, "
            f"got {actual_bytes}: {path}"
        )
    if actual_sha256 != expected_sha256:
        raise LiveValidationError(
            f"{label} hash drifted: expected {expected_sha256}, "
            f"got {actual_sha256}: {path}"
        )
    return {
        "path": str(path),
        "bytes": actual_bytes,
        "sha256": actual_sha256,
        "st_nlink": int(after.st_nlink),
    }


def _write_no_clobber_json(path: Path, payload: dict[str, Any]) -> None:
    _assert_no_reparse_points(path.parent)
    if path.exists() or path.is_symlink():
        raise LiveValidationError(f"no-clobber JSON output already exists: {path}")
    encoded = (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    ).encode("utf-8")
    descriptor = os.open(
        path,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)
    _assert_single_link_regular_file(path, label="no-clobber JSON output")


def _copy_no_clobber(source: Path, destination: Path) -> dict[str, Any]:
    """Copy one file without overwrite and authenticate source stability."""

    _assert_single_link_regular_file(source, label="pre-snap backup source")
    _assert_no_reparse_points(destination.parent)
    if destination.exists() or destination.is_symlink():
        raise LiveValidationError(
            f"pre-snap backup destination is not no-clobber: {destination}"
        )
    source_before = _file_record(source)
    source_descriptor = os.open(
        source, os.O_RDONLY | getattr(os, "O_BINARY", 0)
    )
    source_open_info = os.fstat(source_descriptor)
    if (
        not stat.S_ISREG(source_open_info.st_mode)
        or int(source_open_info.st_nlink) != 1
    ):
        os.close(source_descriptor)
        raise LiveValidationError(
            f"pre-snap backup source descriptor is unsafe: {source}"
        )
    try:
        descriptor = os.open(
            destination,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
            0o600,
        )
    except Exception:
        os.close(source_descriptor)
        raise
    try:
        with (
            os.fdopen(source_descriptor, "rb", closefd=False) as source_handle,
            os.fdopen(descriptor, "wb", closefd=False) as output,
        ):
            for block in iter(lambda: source_handle.read(1024 * 1024), b""):
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
    finally:
        os.close(source_descriptor)
        os.close(descriptor)
    _assert_single_link_regular_file(
        destination, label="pre-snap backup destination"
    )
    source_after = _file_record(source)
    backup = _file_record(destination)
    if source_before != source_after:
        raise LiveValidationError(
            f"staging map changed during pre-snap backup: {source}"
        )
    if (
        backup["bytes"] != source_before["bytes"]
        or backup["sha256"] != source_before["sha256"]
    ):
        raise LiveValidationError(
            f"pre-snap map backup is not byte-identical: {destination}"
        )
    return {
        "source_before": source_before,
        "source_after": source_after,
        "backup": backup,
        "byte_identical": True,
        "no_clobber": True,
    }


def _dirty_packages() -> dict[str, list[str]]:
    def names(packages: Any) -> list[str]:
        return sorted(
            str(package.get_path_name()).split(".", 1)[0] for package in packages
        )

    return {
        "content": names(
            unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
        ),
        "maps": names(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()),
    }


def _xyz(value: Any) -> tuple[float, float, float]:
    return (float(value.x), float(value.y), float(value.z))


def _struct_value(value: Any, property_name: str) -> Any:
    try:
        return value.get_editor_property(property_name)
    except Exception:
        return getattr(value, property_name)


def _vector(value: tuple[float, float, float]) -> Any:
    return unreal.Vector(value[0], value[1], value[2])


def _add(
    *vectors: tuple[float, float, float]
) -> tuple[float, float, float]:
    return tuple(sum(vector[index] for vector in vectors) for index in range(3))


def _subtract(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> tuple[float, float, float]:
    return tuple(a[index] - b[index] for index in range(3))


def _multiply(
    value: tuple[float, float, float], scalar: float
) -> tuple[float, float, float]:
    return tuple(component * scalar for component in value)


def _length(value: tuple[float, float, float]) -> float:
    return math.sqrt(sum(component * component for component in value))


def _normalize(
    value: tuple[float, float, float]
) -> tuple[float, float, float]:
    magnitude = _length(value)
    if magnitude <= 1.0e-12:
        raise LiveValidationError("cannot normalize a zero vector")
    return tuple(component / magnitude for component in value)


def _dot(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> float:
    return sum(a[index] * b[index] for index in range(3))


def _distance(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> float:
    return _length(_subtract(a, b))


def _rotation_delta_degrees(a: list[float], b: list[float]) -> float:
    def axis_delta(left: float, right: float) -> float:
        return abs(((left - right + 180.0) % 360.0) - 180.0)

    return max(axis_delta(a[index], b[index]) for index in range(3))


def _actor_transform_record(actor: Any) -> dict[str, Any]:
    location = actor.get_actor_location()
    rotation = actor.get_actor_rotation()
    scale = actor.get_actor_scale3d()
    record = {
        "actor_path": str(actor.get_path_name()),
        "label": actor.get_actor_label(),
        "class": actor.get_class().get_name(),
        "location_cm": list(_xyz(location)),
        "rotation_degrees": [
            float(rotation.pitch),
            float(rotation.yaw),
            float(rotation.roll),
        ],
        "scale": list(_xyz(scale)),
        "forward": list(_xyz(actor.get_actor_forward_vector())),
        "right": list(_xyz(actor.get_actor_right_vector())),
        "up": list(_xyz(actor.get_actor_up_vector())),
        "tags": sorted(
            str(tag) for tag in actor.get_editor_property("tags")
        ),
        "actor_collision_enabled": bool(actor.get_actor_enable_collision()),
    }
    component = getattr(actor, "static_mesh_component", None)
    if component is None:
        try:
            component = actor.get_editor_property("static_mesh_component")
        except Exception:
            component = None
    if component is not None:
        mesh = component.get_editor_property("static_mesh")
        record.update(
            {
                "static_mesh_path": (
                    str(mesh.get_path_name()) if mesh is not None else None
                ),
                "component_collision_enabled": str(
                    component.get_collision_enabled()
                ),
                "generate_overlap_events": bool(
                    component.get_editor_property("generate_overlap_events")
                ),
            }
        )
    else:
        record.update(
            {
                "static_mesh_path": None,
                "component_collision_enabled": None,
                "generate_overlap_events": None,
            }
        )
    return record


def _transform_changed(
    before: dict[str, Any], after: dict[str, Any], *, tolerance: float
) -> bool:
    return (
        _distance(tuple(before["location_cm"]), tuple(after["location_cm"]))
        > tolerance
        or _distance(tuple(before["scale"]), tuple(after["scale"])) > tolerance
        or _rotation_delta_degrees(
            list(before["rotation_degrees"]), list(after["rotation_degrees"])
        )
        > tolerance
    )


def _current_world() -> Any:
    world = unreal.get_editor_subsystem(
        unreal.UnrealEditorSubsystem
    ).get_editor_world()
    if world is None:
        raise LiveValidationError("Unreal has no current editor world")
    return world


def _current_world_package() -> str:
    return str(_current_world().get_path_name()).split(".", 1)[0]


def _assert_no_pie() -> None:
    pie_worlds = list(
        unreal.EditorLevelLibrary.get_pie_worlds(
            include_dedicated_server=False
        )
    )
    if pie_worlds:
        raise LiveValidationError(
            "PIE/simulate worlds are forbidden during live validation: "
            f"{[str(world.get_path_name()) for world in pie_worlds]}"
        )


def _validate_project_binding() -> tuple[Path, Path]:
    expected_text = os.environ.get(PROJECT_FILE_ENV, "").strip()
    if not expected_text:
        raise LiveValidationError(
            f"required environment variable is unset: {PROJECT_FILE_ENV}"
        )
    expected_project = Path(expected_text)
    if not expected_project.is_absolute() or not expected_project.is_file():
        raise LiveValidationError(
            f"bound project file is not an existing absolute file: {expected_project}"
        )
    _assert_single_link_regular_file(
        expected_project, label="bound scratch project file"
    )
    actual_project = Path(
        unreal.Paths.convert_relative_path_to_full(
            unreal.Paths.get_project_file_path()
        )
    )
    if not actual_project.is_file() or _norm(actual_project) != _norm(expected_project):
        raise LiveValidationError(
            "project binding mismatch: "
            f"environment={expected_project} unreal={actual_project}"
        )
    _assert_single_link_regular_file(
        actual_project, label="active Unreal scratch project file"
    )
    project_root = actual_project.parent
    if not _is_under(project_root, SCRATCH_ROOT):
        raise LiveValidationError(
            f"project is outside the required D: scratch root: {project_root}"
        )
    if _norm(project_root) in {
        _norm(SCRATCH_ROOT),
        _norm(Path(r"D:\RedMMOTitan")),
    }:
        raise LiveValidationError(
            f"scratch project root is forbidden or insufficiently isolated: {project_root}"
        )
    if actual_project.name.casefold() != "titan.uproject":
        raise LiveValidationError(
            f"expected the Titan.uproject clone, got: {actual_project.name}"
        )
    _assert_no_reparse_points(project_root)
    return actual_project, project_root


def _validate_diagnostics(project_root: Path) -> tuple[Path, Path]:
    directory_text = os.environ.get(DIAGNOSTICS_DIR_ENV, "").strip()
    audit_text = os.environ.get(LIVE_AUDIT_ENV, "").strip()
    if not directory_text or not audit_text:
        raise LiveValidationError(
            f"{DIAGNOSTICS_DIR_ENV} and {LIVE_AUDIT_ENV} are required"
        )
    directory = Path(directory_text)
    audit = Path(audit_text)
    if not directory.is_absolute() or not directory.is_dir():
        raise LiveValidationError(
            f"live diagnostics directory must already exist: {directory}"
        )
    if not _is_under(directory, DIAGNOSTICS_ROOT):
        raise LiveValidationError(
            f"live diagnostics directory must be under {DIAGNOSTICS_ROOT}: {directory}"
        )
    if _norm(directory) == _norm(DIAGNOSTICS_ROOT):
        raise LiveValidationError(
            "the shared diagnostics root is not a fresh per-run diagnostics directory"
        )
    if _is_under(directory, project_root):
        raise LiveValidationError(
            f"live diagnostics must be external to scratch project: {directory}"
        )
    if not audit.is_absolute() or audit.parent != directory:
        raise LiveValidationError(
            f"live audit must be an immediate child of {directory}: {audit}"
        )
    if audit.name != "live_validation_audit.json":
        raise LiveValidationError(
            f"live audit must use the exact filename live_validation_audit.json: {audit}"
        )
    _assert_no_reparse_points(directory)
    expected_outputs = [
        audit,
        directory / BACKUP_FILENAME,
        *(directory / name for name in SCREENSHOT_FILENAMES),
    ]
    existing = [str(path) for path in expected_outputs if path.exists()]
    if existing:
        raise LiveValidationError(
            f"live diagnostics targets are no-clobber but already exist: {existing}"
        )
    return directory, audit


def _option_values(command_line: str, name: str) -> list[str]:
    boundary = r"""[\s"']"""
    pattern = re.compile(
        rf"""(?:^|{boundary})-{re.escape(name)}="""
        rf"""(?:"([^"]*)"|'([^']*)'|([^"'\s]+))(?=$|{boundary})""",
        re.IGNORECASE,
    )
    return [
        next(group for group in match.groups() if group is not None)
        for match in pattern.finditer(command_line)
    ]


def _flag_count(command_line: str, flag: str) -> int:
    boundary = r"""[\s"']"""
    return len(
        re.findall(
            rf"""(?:^|{boundary})-{re.escape(flag)}(?=$|{boundary})""",
            command_line,
            flags=re.IGNORECASE,
        )
    )


def _exact_token_count(command_line: str, token: str) -> int:
    normalized = command_line.replace("\\", "/")
    normalized_token = token.replace("\\", "/")
    boundary = r"""[\s"']"""
    return len(
        re.findall(
            rf"""(?:^|{boundary}){re.escape(normalized_token)}(?=$|{boundary})""",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def _validate_live_command_line(project_file: Path) -> dict[str, Any]:
    command_line = str(unreal.SystemLibrary.get_command_line())
    required_disable = ",".join(REQUIRED_DISABLED_PLUGINS)
    disable_values = _option_values(command_line, "DisablePlugins")
    if disable_values != [required_disable]:
        raise LiveValidationError(
            "provider-off launch requires exactly one exact "
            f"-DisablePlugins={required_disable}; observed={disable_values}"
        )
    if "AIAssistant" not in required_disable:
        raise LiveValidationError("AIAssistant must be in the provider-off allowlist")

    if _flag_count(command_line, "d3d12") != 1:
        raise LiveValidationError(
            "live validation requires exactly one explicit -d3d12 flag"
        )
    if _flag_count(command_line, "sm6") != 1:
        raise LiveValidationError(
            "live validation requires exactly one explicit -sm6 flag"
        )
    forbidden_flags = (
        "nullrhi",
        "d3d11",
        "dx11",
        "vulkan",
        "opengl",
        "game",
        "server",
        "unattended",
    )
    observed_forbidden = [
        flag for flag in forbidden_flags if _flag_count(command_line, flag)
    ]
    if observed_forbidden:
        raise LiveValidationError(
            f"live validation command line has forbidden flags: {observed_forbidden}"
        )
    if re.search(r"(?:^|\s)-run=", command_line, flags=re.IGNORECASE):
        raise LiveValidationError(
            "live validation must run in a normal editor, not a commandlet"
        )
    if re.search(
        r"""(?:^|[\s"'])-EnableAllPlugins(?:=|$|[\s"'])""",
        command_line,
        flags=re.IGNORECASE,
    ):
        raise LiveValidationError("-EnableAllPlugins is forbidden")
    required_names = {name.casefold() for name in REQUIRED_DISABLED_PLUGINS}
    conflicts = []
    for value in _option_values(command_line, "EnablePlugins"):
        enabled = {
            item.strip().casefold() for item in value.split(",") if item.strip()
        }
        if enabled & required_names:
            conflicts.append(value)
    if conflicts:
        raise LiveValidationError(
            f"provider-off launch has conflicting -EnablePlugins: {conflicts}"
        )

    normalized_project = str(project_file).replace("\\", "/")
    project_tokens = [
        token.replace("\\", "/")
        for token in re.findall(
            r"""(?:^|[\s"'])([^\s"']+\.uproject)(?=$|[\s"'])""",
            command_line,
            flags=re.IGNORECASE,
        )
    ]
    if len(project_tokens) > 1 or any(
        token.casefold() != normalized_project.casefold()
        for token in project_tokens
    ):
        raise LiveValidationError(
            "in-process command line contains an unexpected or duplicate "
            f".uproject token: {project_tokens}"
        )
    if _exact_token_count(command_line, DESTINATION_MAP) != 1:
        raise LiveValidationError(
            "command line must contain the exact M07 staging map package once"
        )
    if _current_world_package() != DESTINATION_MAP:
        raise LiveValidationError(
            f"current editor map is not the exact staging map: {_current_world_package()}"
        )
    _assert_no_pie()
    return {
        "command_line": command_line,
        "project_binding": {
            "path": str(project_file),
            "authority": "unreal.Paths.get_project_file_path",
            "in_process_command_line_project_tokens": project_tokens,
            "note": (
                "UE may strip the launch-time .uproject token from its "
                "in-process command-line view."
            ),
        },
        "exact_map_token": DESTINATION_MAP,
        "d3d12_flag_count": 1,
        "sm6_flag_count": 1,
        "nullrhi_present": False,
        "required_disable_option": f"-DisablePlugins={required_disable}",
        "disabled_plugins": list(REQUIRED_DISABLED_PLUGINS),
        "AIAssistant_disabled": True,
        "PIE_active": False,
        "rhi_claim": "D3D12 launch contract verified; real pixels require screenshot postflight",
    }


def _validate_stage_audit(
    project_file: Path, project_root: Path
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    text = os.environ.get(STAGE_AUDIT_ENV, "").strip()
    if not text:
        raise LiveValidationError(
            f"required environment variable is unset: {STAGE_AUDIT_ENV}"
        )
    path = Path(text)
    if not path.is_absolute() or not _is_under(path, DIAGNOSTICS_ROOT):
        raise LiveValidationError(
            f"authoring audit must be an absolute external diagnostics path: {path}"
        )
    _assert_no_reparse_points(path)
    record = _authenticate_file(
        path,
        expected_bytes=38_421,
        expected_sha256=EXPECTED_STAGE_AUDIT_SHA256,
        label="M07 authoring audit",
    )
    if _is_under(path, project_root):
        raise LiveValidationError("authoring audit must be external to the scratch project")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("result") != "passed"
        or payload.get("operation")
        != "tropical_planetary_biome_scratch_stage_v1"
    ):
        raise LiveValidationError("authoring audit is not the exact successful stage record")
    if _norm(Path(str(payload.get("project_file", "")))) != _norm(project_file):
        raise LiveValidationError("authoring audit project binding drifted")
    stage = payload.get("stage", {})
    if stage.get("destination_map") != DESTINATION_MAP:
        raise LiveValidationError("authoring audit destination map drifted")
    map_record = stage.get("destination_map_file", {})
    if (
        int(map_record.get("bytes", -1)) != EXPECTED_PRE_SNAP_MAP_BYTES
        or str(map_record.get("sha256", "")).upper()
        != EXPECTED_PRE_SNAP_MAP_SHA256
    ):
        raise LiveValidationError("authoring audit pre-snap map identity drifted")
    if int(stage.get("cluster", {}).get("actor_count", -1)) != 17:
        raise LiveValidationError("authoring audit does not contain exactly 17 actors")
    claims = stage.get("claims", {})
    if (
        claims.get("native_terrain_snap_complete") is not False
        or claims.get("water_integrated") is not False
        or claims.get("cloud_integrated") is not False
    ):
        raise LiveValidationError("authoring audit claim boundary drifted")
    return path, payload, record


def _validate_protected_and_vendor(
    project_root: Path,
) -> dict[str, dict[str, dict[str, Any]]]:
    protected: dict[str, dict[str, Any]] = {}
    for relative, expected_hash in PROTECTED_PROJECT_FILES.items():
        protected[str(relative).replace("\\", "/")] = _authenticate_file(
            project_root / relative,
            expected_bytes=None,
            expected_sha256=expected_hash,
            label=f"protected scratch-clone source {relative}",
        )
    canonical_protected: dict[str, dict[str, Any]] = {}
    for relative, expected_hash in PROTECTED_PROJECT_FILES.items():
        canonical_protected[str(relative).replace("\\", "/")] = (
            _authenticate_file(
                CANONICAL_PROJECT_ROOT / relative,
                expected_bytes=None,
                expected_sha256=expected_hash,
                label=f"canonical protected production source {relative}",
            )
        )
    vendor: dict[str, dict[str, Any]] = {}
    for relative, (expected_bytes, expected_hash) in VENDOR_ROOT_FILES.items():
        vendor[str(relative).replace("\\", "/")] = _authenticate_file(
            project_root / relative,
            expected_bytes=expected_bytes,
            expected_sha256=expected_hash,
            label=f"reviewed Tropical root {relative}",
        )
    return {
        "protected": protected,
        "canonical_protected": canonical_protected,
        "vendor": vendor,
    }


def _validate_stage_audit_against_live_files(
    payload: dict[str, Any],
    project_root: Path,
    authenticated: dict[str, dict[str, dict[str, Any]]],
) -> None:
    stage = payload["stage"]
    for relative, expected_hash in PROTECTED_PROJECT_FILES.items():
        key = str(relative).replace("\\", "/")
        before = stage["protected_files_before"][key]
        after = stage["protected_files_after"][key]
        if (
            str(before["sha256"]).upper() != expected_hash
            or str(after["sha256"]).upper() != expected_hash
            or authenticated["protected"][key]["sha256"] != expected_hash
        ):
            raise LiveValidationError(
                f"authoring audit/live protected identity mismatch: {key}"
            )

    audited_vendor_paths: set[str] = set()
    for record in stage["reviewed_mesh_roots"].values():
        if record.get("available"):
            audited_vendor_paths.add(_norm(Path(record["path"])))
    for record in stage["staged_unapplied_textures"].values():
        audited_vendor_paths.add(_norm(Path(record["path"])))
        if record.get("loaded_by_script") or record.get("applied_by_script"):
            raise LiveValidationError(
                f"authoring audit unexpectedly applied a staged texture: {record}"
            )
    expected_paths = {
        _norm(project_root / relative) for relative in VENDOR_ROOT_FILES
    }
    if audited_vendor_paths != expected_paths:
        raise LiveValidationError(
            "authoring audit vendor root set does not match the live allowlist"
        )


def _validate_loaded_scene(
    stage_payload: dict[str, Any],
) -> tuple[Any, Any, list[Any], Any]:
    if _current_world_package() != DESTINATION_MAP:
        raise LiveValidationError(
            f"wrong current map: {_current_world_package()}"
        )
    _assert_no_pie()
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = list(actor_subsystem.get_all_level_actors())

    planet_class = getattr(unreal, "CLMPlanet", None)
    anchor_class = getattr(unreal, "RedPlanetRegionAnchor", None)
    if planet_class is None or anchor_class is None:
        raise LiveValidationError(
            "required CLMPlanet/RedPlanetRegionAnchor reflected types are unavailable"
        )
    planets = [actor for actor in actors if isinstance(actor, planet_class)]
    if len(planets) != 1:
        raise LiveValidationError(
            f"expected one CLMPlanet, found {len(planets)}"
        )
    planet = planets[0]
    if abs(
        float(planet.get_editor_property("planet_radius"))
        - EXPECTED_PLANET_RADIUS_CM
    ) > 1.0:
        raise LiveValidationError("loaded scratch planet radius drifted")

    anchors = [
        actor
        for actor in actors
        if isinstance(actor, anchor_class)
        and int(actor.get_editor_property("region_index")) == REGION_INDEX
    ]
    if len(anchors) != 1:
        raise LiveValidationError(
            f"expected one exact region-15 anchor, found {len(anchors)}"
        )
    anchor = anchors[0]
    if (
        int(anchor.get_editor_property("seed")) != EXPECTED_REGION_SEED
        or str(anchor.get_editor_property("archetype_tag"))
        != EXPECTED_REGION_ARCHETYPE
        or _distance(
            _xyz(anchor.get_editor_property("unit_site")),
            EXPECTED_REGION_SITE,
        )
        > 1.0e-9
    ):
        raise LiveValidationError("loaded region-15 anchor metadata drifted")

    managed = [
        actor
        for actor in actors
        if MANAGED_TAG
        in {str(tag) for tag in actor.get_editor_property("tags")}
    ]
    if len(managed) != EXPECTED_MANAGED_ACTOR_COUNT:
        raise LiveValidationError(
            f"expected exactly 17 managed actors, found {len(managed)}"
        )
    if any(not isinstance(actor, unreal.StaticMeshActor) for actor in managed):
        raise LiveValidationError("managed actor set contains a non-StaticMeshActor")
    labels = {actor.get_actor_label() for actor in managed}
    if labels != EXPECTED_ACTOR_LABELS:
        raise LiveValidationError(
            f"managed actor labels drifted: {sorted(labels)}"
        )

    audited_actors = stage_payload["stage"]["cluster"]["actors"]
    audited_paths = {str(record["actor_path"]) for record in audited_actors}
    live_paths = {str(actor.get_path_name()) for actor in managed}
    if live_paths != audited_paths:
        raise LiveValidationError(
            "managed actor path set does not match authenticated authoring audit"
        )
    audit_by_path = {
        str(record["actor_path"]): record for record in audited_actors
    }
    for actor in managed:
        path = str(actor.get_path_name())
        expected = audit_by_path[path]
        actual = _actor_transform_record(actor)
        if _distance(
            tuple(actual["location_cm"]), tuple(expected["location_cm"])
        ) > 0.1:
            raise LiveValidationError(
                f"pre-snap actor location drifted from authoring audit: {path}"
            )
        if _distance(tuple(actual["scale"]), tuple(expected["scale"])) > 1.0e-6:
            raise LiveValidationError(
                f"pre-snap actor scale drifted from authoring audit: {path}"
            )
        component = actor.get_editor_property("static_mesh_component")
        if (
            component is None
            or component.get_editor_property("static_mesh") is None
            or actor.get_actor_enable_collision()
            or component.get_collision_enabled()
            != unreal.CollisionEnabled.NO_COLLISION
            or bool(component.get_editor_property("generate_overlap_events"))
        ):
            raise LiveValidationError(
                f"managed actor collision/mesh contract drifted: {path}"
            )
        tags = {str(tag) for tag in actor.get_editor_property("tags")}
        if PENDING_SNAP_TAG not in tags:
            raise LiveValidationError(
                f"managed actor is missing pending-snap tag: {path}"
            )
        if COMPLETE_SNAP_TAG in tags:
            raise LiveValidationError(
                f"managed actor already has complete-snap tag: {path}"
            )

    pending_paths = {
        str(actor.get_path_name())
        for actor in actors
        if PENDING_SNAP_TAG
        in {str(tag) for tag in actor.get_editor_property("tags")}
    }
    complete_paths = {
        str(actor.get_path_name())
        for actor in actors
        if COMPLETE_SNAP_TAG
        in {str(tag) for tag in actor.get_editor_property("tags")}
    }
    if pending_paths != live_paths or complete_paths:
        raise LiveValidationError(
            "pre-snap tag scope is not exact: "
            f"pending={sorted(pending_paths)} complete={sorted(complete_paths)}"
        )

    return planet, anchor, sorted(managed, key=lambda actor: actor.get_actor_label()), actor_subsystem


def _viewport_setter() -> Any:
    subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    method = getattr(subsystem, "set_level_viewport_camera_info", None)
    if method is not None:
        return method
    method = getattr(
        unreal.EditorLevelLibrary, "set_level_viewport_camera_info", None
    )
    if method is None:
        raise LiveValidationError(
            "no supported level-viewport camera setter is available"
        )
    return method


def _look_at_rotation(location: Any, target: Any) -> Any:
    math_library = getattr(unreal, "MathLibrary", None)
    if math_library is None:
        math_library = getattr(unreal, "KismetMathLibrary", None)
    method = (
        getattr(math_library, "find_look_at_rotation", None)
        if math_library is not None
        else None
    )
    if method is None:
        raise LiveValidationError(
            "MathLibrary.find_look_at_rotation is unavailable"
        )
    return method(location, target)


def _set_viewport_camera(
    setter: Any,
    location: tuple[float, float, float],
    target: tuple[float, float, float],
) -> dict[str, Any]:
    location_vector = _vector(location)
    target_vector = _vector(target)
    rotation = _look_at_rotation(location_vector, target_vector)
    setter(location_vector, rotation)
    return {
        "location_cm": list(location),
        "target_cm": list(target),
        "rotation_degrees": [
            float(rotation.pitch),
            float(rotation.yaw),
            float(rotation.roll),
        ],
    }


class LiveValidationSession:
    def __init__(
        self,
        *,
        project_file: Path,
        project_root: Path,
        diagnostics_dir: Path,
        audit_output: Path,
        command_line_record: dict[str, Any],
        stage_audit_path: Path,
        stage_payload: dict[str, Any],
        stage_audit_record: dict[str, Any],
        authenticated_files: dict[str, dict[str, dict[str, Any]]],
    ) -> None:
        self.project_file = project_file
        self.project_root = project_root
        self.diagnostics_dir = diagnostics_dir
        self.audit_output = audit_output
        self.stage_audit_path = stage_audit_path
        self.stage_payload = stage_payload
        self.actor_subsystem: Any = None
        self.planet: Any = None
        self.anchor: Any = None
        self.managed: list[Any] = []
        self.viewport_setter = _viewport_setter()
        self.callback_handle: Any = None
        self.terminal = False
        self.state = "preflight"
        self.state_started = time.monotonic()
        self.state_frames = 0
        self.snap_before_all: dict[str, dict[str, Any]] | None = None
        self.snap_applied = False
        self.map_saved = False
        self.camera_index = 0
        self.cameras: list[dict[str, Any]] = []
        self.screenshot_last_size: int | None = None
        self.screenshot_stable_ticks = 0
        self.audit: dict[str, Any] = {
            "schema_version": 1,
            "module": "M07",
            "operation": "tropical_planetary_biome_live_snap_visual_validation_v1",
            "evidence_class": "automation",
            "requested_evidence_class":
                "real_gpu_visual_pending_external_pixel_inspection",
            "captured_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "project_file": str(project_file),
            "project_root": str(project_root),
            "map": DESTINATION_MAP,
            "scratch_only": True,
            "PIE_started": False,
            "providers_used": False,
            "water_or_cloud_assets_applied": False,
            "command_line": command_line_record,
            "authoring_audit": {
                **stage_audit_record,
                "authenticated_operation":
                    stage_payload["operation"],
                "authenticated_result": stage_payload["result"],
            },
            "files_before": authenticated_files,
            "result": "running",
            "claim_limit": (
                "Live editor snap and exact stable screenshot-file evidence only. "
                "Screenshot pixels, gameplay, water, collision feel, performance, "
                "surface-to-orbit transition, and production integration remain unaccepted."
            ),
        }

    def prepare(self) -> None:
        _assert_no_pie()
        dirty = _dirty_packages()
        if dirty != {"content": [], "maps": []}:
            raise LiveValidationError(
                f"live scratch map starts dirty: {dirty}"
            )
        map_path = self.project_root / DESTINATION_MAP_RELATIVE
        self.audit["pre_snap_map"] = _authenticate_file(
            map_path,
            expected_bytes=EXPECTED_PRE_SNAP_MAP_BYTES,
            expected_sha256=EXPECTED_PRE_SNAP_MAP_SHA256,
            label="pre-snap M07 staging map",
        )
        backup_path = self.diagnostics_dir / BACKUP_FILENAME
        self.audit["pre_snap_backup"] = _copy_no_clobber(
            map_path, backup_path
        )
        if (
            self.audit["pre_snap_backup"]["backup"]["sha256"]
            != EXPECTED_PRE_SNAP_MAP_SHA256
        ):
            raise LiveValidationError(
                "pre-snap backup did not authenticate to the pinned FBB0EED map"
            )

        self.planet, self.anchor, self.managed, self.actor_subsystem = (
            _validate_loaded_scene(self.stage_payload)
        )
        self.audit["managed_preflight"] = [
            _actor_transform_record(actor) for actor in self.managed
        ]

        center = _xyz(self.planet.get_actor_location())
        target = tuple(
            sum(actor.get_actor_location().__getattribute__(axis) for actor in self.managed)
            / len(self.managed)
            for axis in ("x", "y", "z")
        )
        up = _normalize(_subtract(target, center))
        region_library = getattr(
            unreal, "RedPlanetRegionBlueprintLibrary", None
        )
        if region_library is None:
            raise LiveValidationError(
                "RedPlanetRegionBlueprintLibrary is unavailable"
            )
        frame = region_library.make_planet_tangent_frame(
            self.anchor.get_editor_property("unit_site"),
            unreal.Vector(0.0, 0.0, 1.0),
        )
        north = _normalize(_xyz(_struct_value(frame, "unit_north")))
        east = _normalize(_xyz(_struct_value(frame, "unit_east")))
        load_camera = _add(
            target,
            _multiply(up, 70_000.0),
            _multiply(north, -30_000.0),
        )
        self.audit["planet_streaming_warmup_view"] = _set_viewport_camera(
            self.viewport_setter, load_camera, target
        )
        self.audit["planet_streaming_warmup_view"]["purpose"] = (
            "drive PlanetGen chunk generation near region 15 before native snap"
        )
        self.audit["camera_basis"] = {
            "center_cm": list(center),
            "target_cm": list(target),
            "unit_up": list(up),
            "unit_north": list(north),
            "unit_east": list(east),
        }
        self._set_state("settle_for_planetgen")

    def start(self) -> None:
        if self.callback_handle is not None:
            raise LiveValidationError("live validation callback is already registered")
        handle = unreal.register_slate_pre_tick_callback(self._on_tick)
        if handle is None:
            raise LiveValidationError(
                "register_slate_pre_tick_callback returned no handle"
            )
        self.callback_handle = handle
        try:
            unreal.log(
                "RED_M07_TROPICAL_LIVE_VALIDATION_STARTED "
                f"map={DESTINATION_MAP} actors={len(self.managed)} "
                f"backup={self.audit['pre_snap_backup']['backup']['path']} "
                "pie=false providers=false"
            )
        except Exception:
            self._unregister()
            raise

    def _set_state(self, state: str) -> None:
        self.state = state
        self.state_started = time.monotonic()
        self.state_frames = 0
        unreal.log(f"RED_M07_TROPICAL_LIVE_STATE state={state}")

    def _elapsed(self) -> float:
        return time.monotonic() - self.state_started

    def _on_tick(self, _delta_seconds: float) -> None:
        if self.terminal:
            if self.callback_handle is not None:
                try:
                    self._unregister()
                    self._release_active_session()
                except Exception:
                    pass
            return
        self.state_frames += 1
        try:
            _assert_no_pie()
            if _current_world_package() != DESTINATION_MAP:
                raise LiveValidationError(
                    f"editor changed away from staging map: {_current_world_package()}"
                )
            if self.state == "settle_for_planetgen":
                if self._elapsed() > MAX_SNAP_SETTLE_SECONDS:
                    raise LiveValidationError(
                        "PlanetGen warmup exceeded the bounded 45-second window"
                    )
                if (
                    self._elapsed() >= MIN_SNAP_SETTLE_SECONDS
                    and self.state_frames >= MIN_SNAP_SETTLE_FRAMES
                ):
                    self._snap_validate_and_save()
                    self._clear_selection_for_visual_capture()
                    self._begin_camera(0)
            elif self.state == "settle_camera":
                if (
                    self._elapsed() >= MIN_CAMERA_SETTLE_SECONDS
                    and self.state_frames >= MIN_CAMERA_SETTLE_FRAMES
                ):
                    self._issue_high_res_shot()
            elif self.state == "wait_for_screenshot":
                self._poll_screenshot_completion()
        except Exception as exc:
            self._finish_failure(exc)

    def _snapshot_all_level_actors(self) -> dict[str, dict[str, Any]]:
        return {
            str(actor.get_path_name()): _actor_transform_record(actor)
            for actor in self.actor_subsystem.get_all_level_actors()
        }

    def _select_exact_managed_set(self) -> None:
        self.actor_subsystem.clear_actor_selection_set()
        self.actor_subsystem.set_selected_level_actors(self.managed)
        selected = list(self.actor_subsystem.get_selected_level_actors())
        selected_paths = {str(actor.get_path_name()) for actor in selected}
        managed_paths = {str(actor.get_path_name()) for actor in self.managed}
        if selected_paths != managed_paths or len(selected) != 17:
            raise LiveValidationError(
                "editor selection is not exactly the 17 managed staging actors"
            )

    def _clear_selection_for_visual_capture(self) -> None:
        self.actor_subsystem.clear_actor_selection_set()
        selected = list(self.actor_subsystem.get_selected_level_actors())
        if selected:
            raise LiveValidationError(
                "visual capture selection clear failed; orange outlines would remain: "
                f"{[str(actor.get_path_name()) for actor in selected]}"
            )
        dirty = _dirty_packages()
        if dirty != {"content": [], "maps": []}:
            raise LiveValidationError(
                f"selection clear changed dirty-package state: {dirty}"
            )
        self.audit["visual_capture_selection"] = {
            "cleared": True,
            "selected_actor_count": 0,
            "orange_selection_outlines_expected": False,
            "dirty_packages": dirty,
        }

    def _managed_tag_scope(
        self, snapshot: dict[str, dict[str, Any]] | None = None
    ) -> dict[str, list[str]]:
        records = snapshot or self._snapshot_all_level_actors()
        return {
            "pending_paths": sorted(
                path
                for path, record in records.items()
                if PENDING_SNAP_TAG in set(record["tags"])
            ),
            "complete_paths": sorted(
                path
                for path, record in records.items()
                if COMPLETE_SNAP_TAG in set(record["tags"])
            ),
        }

    def _restoration_status(
        self, current: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        if self.snap_before_all is None:
            raise LiveValidationError("pre-snap actor snapshot is unavailable")
        before_paths = set(self.snap_before_all)
        current_paths = set(current)
        transform_mismatches = sorted(
            path
            for path in before_paths & current_paths
            if _transform_changed(
                self.snap_before_all[path], current[path], tolerance=0.01
            )
        )
        managed_paths = {str(actor.get_path_name()) for actor in self.managed}
        managed_tag_mismatches = sorted(
            path
            for path in managed_paths & before_paths & current_paths
            if current[path]["tags"] != self.snap_before_all[path]["tags"]
        )
        dirty = _dirty_packages()
        return {
            "actor_set_equal": before_paths == current_paths,
            "missing_actor_paths": sorted(before_paths - current_paths),
            "unexpected_actor_paths": sorted(current_paths - before_paths),
            "transform_mismatches": transform_mismatches,
            "managed_tag_mismatches": managed_tag_mismatches,
            "tag_scope": self._managed_tag_scope(current),
            "dirty_packages": dirty,
            "restored": (
                before_paths == current_paths
                and not transform_mismatches
                and not managed_tag_mismatches
                and dirty == {"content": [], "maps": []}
            ),
        }

    def _attempt_undo(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "attempted": False,
            "methods": [],
            "attempt_count": 0,
            "restored": False,
        }
        if self.snap_before_all is None or self.map_saved:
            return result
        current = self._snapshot_all_level_actors()
        status = self._restoration_status(current)
        result["before_undo"] = status
        if status["restored"]:
            result["restored"] = True
            result["reason"] = (
                "full actor set, every actor transform, managed tags, and "
                "pre-snap empty dirty scope were already restored"
            )
            return result

        result["attempted"] = True
        undo = getattr(unreal.EditorLevelLibrary, "editor_undo", None)
        for _index in range(4):
            if undo is not None:
                method = "EditorLevelLibrary.editor_undo"
                undo()
            else:
                method = "TRANSACTION UNDO console fallback"
                unreal.SystemLibrary.execute_console_command(
                    _current_world(), "TRANSACTION UNDO"
                )
            result["methods"].append(method)
            result["attempt_count"] += 1
            after = self._snapshot_all_level_actors()
            status = self._restoration_status(after)
            result["after_undo"] = status
            if status["restored"]:
                result["restored"] = True
                break
            # Do not walk past our transaction once all transforms and managed
            # tags are restored; a remaining dirty package is a hard failure.
            if (
                status["actor_set_equal"]
                and not status["transform_mismatches"]
                and not status["managed_tag_mismatches"]
            ):
                break
        return result

    def _transition_snap_tags(self) -> dict[str, Any]:
        if self.snap_before_all is None:
            raise LiveValidationError("cannot transition tags without pre-snap state")
        managed_paths = {str(actor.get_path_name()) for actor in self.managed}
        before = self._snapshot_all_level_actors()
        scope_before = self._managed_tag_scope(before)
        if (
            set(scope_before["pending_paths"]) != managed_paths
            or scope_before["complete_paths"]
        ):
            raise LiveValidationError(
                f"pre-transition snap-tag scope drifted: {scope_before}"
            )

        transaction_class = getattr(unreal, "ScopedEditorTransaction", None)
        if transaction_class is None:
            raise LiveValidationError(
                "ScopedEditorTransaction is required for reversible tag transition"
            )
        with transaction_class("M07 Tropical Native Planet Snap Completion"):
            for actor in self.managed:
                tags = [
                    str(tag) for tag in actor.get_editor_property("tags")
                ]
                if (
                    tags.count(PENDING_SNAP_TAG) != 1
                    or COMPLETE_SNAP_TAG in tags
                ):
                    raise LiveValidationError(
                        "managed actor tag state drifted during transition: "
                        f"{actor.get_path_name()} tags={tags}"
                    )
                transitioned = [
                    COMPLETE_SNAP_TAG if tag == PENDING_SNAP_TAG else tag
                    for tag in tags
                ]
                actor.set_editor_property(
                    "tags", [unreal.Name(tag) for tag in transitioned]
                )

        after = self._snapshot_all_level_actors()
        scope_after = self._managed_tag_scope(after)
        if (
            scope_after["pending_paths"]
            or set(scope_after["complete_paths"]) != managed_paths
        ):
            raise LiveValidationError(
                f"post-transition snap-tag scope is not exact: {scope_after}"
            )
        nonmanaged_tag_changes = sorted(
            path
            for path in set(before) - managed_paths
            if before[path]["tags"] != after[path]["tags"]
        )
        if nonmanaged_tag_changes:
            raise LiveValidationError(
                "tag transition changed non-managed actors: "
                f"{nonmanaged_tag_changes}"
            )
        for path in managed_paths:
            expected_tags = sorted(
                COMPLETE_SNAP_TAG if tag == PENDING_SNAP_TAG else tag
                for tag in before[path]["tags"]
            )
            if after[path]["tags"] != expected_tags:
                raise LiveValidationError(
                    f"managed tag transition was not exact: {path}"
                )
        return {
            "transaction": "M07 Tropical Native Planet Snap Completion",
            "before": scope_before,
            "after": scope_after,
            "pending_removed": True,
            "complete_added_to_exact_managed_set": True,
            "nonmanaged_tag_changes": [],
        }

    def _snap_validate_and_save(self) -> None:
        _assert_no_pie()
        if _dirty_packages() != {"content": [], "maps": []}:
            raise LiveValidationError(
                f"packages became dirty before snap: {_dirty_packages()}"
            )
        map_path = self.project_root / DESTINATION_MAP_RELATIVE
        _authenticate_file(
            map_path,
            expected_bytes=EXPECTED_PRE_SNAP_MAP_BYTES,
            expected_sha256=EXPECTED_PRE_SNAP_MAP_SHA256,
            label="immediate pre-snap staging map",
        )
        self._select_exact_managed_set()
        self.snap_before_all = self._snapshot_all_level_actors()
        managed_paths = {str(actor.get_path_name()) for actor in self.managed}

        tools_class = getattr(unreal, "RedMMOEditorTools", None)
        method = (
            getattr(
                tools_class,
                "snap_selected_static_mesh_actors_to_planet_surface",
                None,
            )
            if tools_class is not None
            else None
        )
        if method is None:
            raise LiveValidationError(
                "RedMMOEditorTools native snap function is unavailable"
            )
        snap_result = str(method(0.0))
        self.snap_applied = snap_result.startswith("OK:")
        self.audit["native_snap_result"] = snap_result
        expected_result = (
            "OK: snapped=17 offset=0.00cm "
            "skipped(notStaticMesh=0 attached=0 noTerrainHit=0) "
            f"world={DESTINATION_MAP}"
        )
        if snap_result != expected_result:
            recovery = self._attempt_undo()
            self.audit["snap_failure_recovery"] = recovery
            raise LiveValidationError(
                f"native snap result was not exact: {snap_result}; "
                f"recovery={recovery}"
            )

        after_all = self._snapshot_all_level_actors()
        if set(after_all) != set(self.snap_before_all):
            recovery = self._attempt_undo()
            self.audit["snap_failure_recovery"] = recovery
            raise LiveValidationError(
                "actor population changed during the synchronous native snap"
            )
        unexpected_changes = [
            path
            for path, before in self.snap_before_all.items()
            if path not in managed_paths
            and _transform_changed(before, after_all[path], tolerance=0.001)
        ]
        if unexpected_changes:
            recovery = self._attempt_undo()
            self.audit["snap_failure_recovery"] = recovery
            raise LiveValidationError(
                "non-managed actor transforms changed during native snap: "
                f"{unexpected_changes}"
            )

        planet_center = _xyz(self.planet.get_actor_location())
        planet_radius = float(self.planet.get_editor_property("planet_radius"))
        managed_after: list[dict[str, Any]] = []
        for actor in self.managed:
            path = str(actor.get_path_name())
            before = self.snap_before_all[path]
            after = after_all[path]
            location_delta = _distance(
                tuple(before["location_cm"]), tuple(after["location_cm"])
            )
            scale_delta = _distance(
                tuple(before["scale"]), tuple(after["scale"])
            )
            radial = _normalize(
                _subtract(tuple(after["location_cm"]), planet_center)
            )
            radial_distance = _distance(
                tuple(after["location_cm"]), planet_center
            )
            up_dot = _dot(_normalize(tuple(after["up"])), radial)
            forward_radial = abs(_dot(_normalize(tuple(after["forward"])), radial))
            right_radial = abs(_dot(_normalize(tuple(after["right"])), radial))
            component = actor.get_editor_property("static_mesh_component")
            if location_delta <= 100.0:
                recovery = self._attempt_undo()
                self.audit["snap_failure_recovery"] = recovery
                raise LiveValidationError(
                    f"managed actor did not move meaningfully during snap: {path}"
                )
            if scale_delta > 1.0e-6:
                recovery = self._attempt_undo()
                self.audit["snap_failure_recovery"] = recovery
                raise LiveValidationError(
                    f"native snap changed managed actor scale: {path}"
                )
            if (
                up_dot < 0.9999
                or forward_radial > 0.001
                or right_radial > 0.001
            ):
                recovery = self._attempt_undo()
                self.audit["snap_failure_recovery"] = recovery
                raise LiveValidationError(
                    f"managed actor radial/tangent orientation failed: {path}"
                )
            if not (
                planet_radius - MAX_AUTHORED_HEIGHT_CM - 100.0
                <= radial_distance
                <= planet_radius + MAX_AUTHORED_HEIGHT_CM + 100.0
            ):
                recovery = self._attempt_undo()
                self.audit["snap_failure_recovery"] = recovery
                raise LiveValidationError(
                    f"managed actor snapped outside authored terrain shell: {path}"
                )
            if (
                actor.get_actor_enable_collision()
                or component.get_collision_enabled()
                != unreal.CollisionEnabled.NO_COLLISION
                or bool(component.get_editor_property("generate_overlap_events"))
            ):
                recovery = self._attempt_undo()
                self.audit["snap_failure_recovery"] = recovery
                raise LiveValidationError(
                    f"managed actor collision changed during native snap: {path}"
                )
            managed_after.append(
                {
                    **after,
                    "location_delta_cm": location_delta,
                    "scale_delta": scale_delta,
                    "radial_distance_cm": radial_distance,
                    "up_dot_radial": up_dot,
                    "forward_dot_radial_abs": forward_radial,
                    "right_dot_radial_abs": right_radial,
                    "collision": "disabled",
                }
            )

        tag_transition = self._transition_snap_tags()
        final_all = self._snapshot_all_level_actors()
        if set(final_all) != set(after_all):
            recovery = self._attempt_undo()
            self.audit["snap_failure_recovery"] = recovery
            raise LiveValidationError(
                "actor population changed during completion-tag transition"
            )
        tag_transform_changes = sorted(
            path
            for path in after_all
            if _transform_changed(
                after_all[path], final_all[path], tolerance=0.001
            )
        )
        if tag_transform_changes:
            recovery = self._attempt_undo()
            self.audit["snap_failure_recovery"] = recovery
            raise LiveValidationError(
                "completion-tag transition changed transforms: "
                f"{tag_transform_changes}"
            )

        captured_invariant_fields = (
            "actor_path",
            "label",
            "class",
            "scale",
            "actor_collision_enabled",
            "static_mesh_path",
            "component_collision_enabled",
            "generate_overlap_events",
        )
        invariant_mismatches: list[dict[str, Any]] = []
        for path in sorted(managed_paths):
            before = self.snap_before_all[path]
            final = final_all[path]
            for field in captured_invariant_fields:
                if before[field] != final[field]:
                    invariant_mismatches.append(
                        {
                            "actor_path": path,
                            "field": field,
                            "before": before[field],
                            "after": final[field],
                        }
                    )
            expected_tags = sorted(
                COMPLETE_SNAP_TAG if tag == PENDING_SNAP_TAG else tag
                for tag in before["tags"]
            )
            if final["tags"] != expected_tags:
                invariant_mismatches.append(
                    {
                        "actor_path": path,
                        "field": "tags",
                        "before": before["tags"],
                        "expected": expected_tags,
                        "after": final["tags"],
                    }
                )
        if invariant_mismatches:
            recovery = self._attempt_undo()
            self.audit["snap_failure_recovery"] = recovery
            raise LiveValidationError(
                "captured managed state delta exceeded transform snap plus "
                f"completion-tag replacement: {invariant_mismatches}"
            )
        managed_after = [
            {
                **record,
                "tags": final_all[record["actor_path"]]["tags"],
            }
            for record in managed_after
        ]

        dirty_before_save = _dirty_packages()
        if dirty_before_save != {
            "content": [],
            "maps": [DESTINATION_MAP],
        }:
            recovery = self._attempt_undo()
            self.audit["snap_failure_recovery"] = recovery
            raise LiveValidationError(
                f"dirty-package scope after snap is not destination-only: "
                f"{dirty_before_save}"
            )
        # The map file itself must still be the authenticated pre-snap version
        # until this one explicit save gate.
        _authenticate_file(
            map_path,
            expected_bytes=EXPECTED_PRE_SNAP_MAP_BYTES,
            expected_sha256=EXPECTED_PRE_SNAP_MAP_SHA256,
            label="unsaved pre-save staging map",
        )
        if not unreal.get_editor_subsystem(
            unreal.LevelEditorSubsystem
        ).save_current_level():
            recovery = self._attempt_undo()
            self.audit["snap_failure_recovery"] = recovery
            raise LiveValidationError(
                f"save_current_level failed for {DESTINATION_MAP}"
            )
        self.map_saved = True
        dirty_after_save = _dirty_packages()
        if dirty_after_save != {"content": [], "maps": []}:
            raise LiveValidationError(
                f"destination save left dirty packages: {dirty_after_save}"
            )
        post_map = _file_record(map_path)
        if post_map["sha256"] == EXPECTED_PRE_SNAP_MAP_SHA256:
            raise LiveValidationError(
                "saved staging map hash did not change after 17 verified snaps"
            )
        backup_path = self.diagnostics_dir / BACKUP_FILENAME
        _authenticate_file(
            backup_path,
            expected_bytes=EXPECTED_PRE_SNAP_MAP_BYTES,
            expected_sha256=EXPECTED_PRE_SNAP_MAP_SHA256,
            label="retained pre-snap rollback map",
        )
        files_after = _validate_protected_and_vendor(self.project_root)
        if files_after != self.audit["files_before"]:
            raise LiveValidationError(
                "protected/vendor identities changed during live snap validation"
            )

        self.audit["snap"] = {
            "managed_actor_count": len(managed_after),
            "managed_before": [
                self.snap_before_all[path] for path in sorted(managed_paths)
            ],
            "managed_after": sorted(
                managed_after, key=lambda record: record["label"]
            ),
            "tag_transition": tag_transition,
            "nonmanaged_transform_changes": [],
            "tag_transition_transform_changes": [],
            "captured_managed_state_invariants": list(
                captured_invariant_fields
            ),
            "captured_managed_state_delta_exact": True,
            "captured_managed_state_delta": (
                "native location/rotation snap plus exact "
                "PendingNativePlanetSnap-to-NativePlanetSnapComplete replacement"
            ),
            "scales_unchanged": True,
            "radial_up_and_tangent_orientation_verified": True,
            "collision_disabled": True,
            "dirty_before_save": dirty_before_save,
            "dirty_after_save": dirty_after_save,
            "save_scope": "LevelEditorSubsystem.save_current_level only",
            "post_save_map": post_map,
        }
        self.audit["files_after"] = files_after
        unreal.log(
            "RED_M07_TROPICAL_NATIVE_SNAP_VERIFIED "
            f"actors={len(managed_after)} map={DESTINATION_MAP} "
            f"post_sha256={post_map['sha256']} collision=disabled"
        )

    def _camera_definitions(self) -> list[dict[str, Any]]:
        basis = self.audit["camera_basis"]
        center = tuple(basis["center_cm"])
        target = tuple(
            sum(actor.get_actor_location().__getattribute__(axis) for actor in self.managed)
            / len(self.managed)
            for axis in ("x", "y", "z")
        )
        up = _normalize(_subtract(target, center))
        north = tuple(basis["unit_north"])
        east = tuple(basis["unit_east"])
        return [
            {
                "name": "ground",
                "location": _add(
                    target,
                    _multiply(up, 3_500.0),
                    _multiply(north, -12_000.0),
                    _multiply(east, -3_000.0),
                ),
                "target": _add(target, _multiply(up, 1_500.0)),
                "purpose": "surface-scale organic cluster and material-language review",
            },
            {
                "name": "curvature",
                "location": _add(
                    target,
                    _multiply(up, 80_000.0),
                    _multiply(north, -60_000.0),
                ),
                "target": target,
                "purpose": "local biome fit against visible spherical curvature",
            },
            {
                "name": "horizon",
                "location": _add(
                    target,
                    _multiply(up, 180_000.0),
                    _multiply(east, -100_000.0),
                ),
                "target": target,
                "purpose": "planet-owned atmosphere/horizon transition context",
            },
        ]

    def _begin_camera(self, index: int) -> None:
        _assert_no_pie()
        definitions = self._camera_definitions()
        definition = definitions[index]
        screenshot_path = self.diagnostics_dir / SCREENSHOT_FILENAMES[index]
        if screenshot_path.exists():
            raise LiveValidationError(
                f"screenshot output is no-clobber: {screenshot_path}"
            )
        camera = _set_viewport_camera(
            self.viewport_setter,
            tuple(definition["location"]),
            tuple(definition["target"]),
        )
        camera.update(
            {
                "name": definition["name"],
                "purpose": definition["purpose"],
                "expected_screenshot_path": str(screenshot_path),
                "screenshot_existence": "unverified_pending_postflight",
                "high_res_shot_issued": False,
            }
        )
        if index < len(self.cameras):
            self.cameras[index] = camera
        else:
            self.cameras.append(camera)
        self.camera_index = index
        self.screenshot_last_size = None
        self.screenshot_stable_ticks = 0
        self._set_state("settle_camera")

    def _issue_high_res_shot(self) -> None:
        _assert_no_pie()
        screenshot_path = Path(
            self.cameras[self.camera_index]["expected_screenshot_path"]
        )
        if screenshot_path.exists():
            raise LiveValidationError(
                f"HighResShot would overwrite an existing file: {screenshot_path}"
            )
        command_path = str(screenshot_path).replace("\\", "/")
        if any(character in command_path for character in ('"', "\r", "\n")):
            raise LiveValidationError(
                f"unsafe HighResShot output path: {command_path}"
            )
        command = (
            f'HighResShot filename="{command_path}" '
            f"{SCREENSHOT_RESOLUTION}"
        )
        unreal.SystemLibrary.execute_console_command(_current_world(), command)
        self.cameras[self.camera_index].update(
            {
                "high_res_shot_command": command,
                "high_res_shot_issued": True,
                "issued_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "screenshot_existence": "pending_exact_file_stability_check",
                "screenshot_pixels_inspected": False,
            }
        )
        unreal.log(
            "RED_M07_TROPICAL_HIGHRESSHOT_ISSUED "
            f"view={self.cameras[self.camera_index]['name']} "
            f"expected={screenshot_path} verification=pending_file_stability"
        )
        self._set_state("wait_for_screenshot")

    def _poll_screenshot_completion(self) -> None:
        screenshot_path = Path(
            self.cameras[self.camera_index]["expected_screenshot_path"]
        )
        if self._elapsed() > MAX_SCREENSHOT_WAIT_SECONDS:
            raise LiveValidationError(
                "HighResShot output did not become a stable non-empty exact "
                f"file within {MAX_SCREENSHOT_WAIT_SECONDS:.0f}s: {screenshot_path}"
            )
        if not screenshot_path.exists():
            self.screenshot_last_size = None
            self.screenshot_stable_ticks = 0
            return
        info = _assert_single_link_regular_file(
            screenshot_path,
            label=(
                f"{self.cameras[self.camera_index]['name']} HighResShot output"
            ),
        )
        size = int(info.st_size)
        if size <= 0:
            self.screenshot_last_size = size
            self.screenshot_stable_ticks = 0
            return
        if size == self.screenshot_last_size:
            self.screenshot_stable_ticks += 1
        else:
            self.screenshot_last_size = size
            self.screenshot_stable_ticks = 1
        self.cameras[self.camera_index].update(
            {
                "observed_bytes": size,
                "stable_tick_count": self.screenshot_stable_ticks,
            }
        )
        if self.screenshot_stable_ticks < SCREENSHOT_STABLE_TICKS:
            return

        file_record = _file_record(screenshot_path)
        if file_record["bytes"] != size:
            self.screenshot_last_size = int(file_record["bytes"])
            self.screenshot_stable_ticks = 1
            return
        self.cameras[self.camera_index].update(
            {
                "screenshot_existence": "verified_exact_nonempty_stable_file",
                "screenshot_file": file_record,
                "stability_required_ticks": SCREENSHOT_STABLE_TICKS,
                "stable_tick_count": self.screenshot_stable_ticks,
                "screenshot_pixels_inspected": False,
                "pixel_review": "pending_external_inspection",
                "file_verified_utc": dt.datetime.now(
                    dt.timezone.utc
                ).isoformat(),
            }
        )
        unreal.log(
            "RED_M07_TROPICAL_HIGHRESSHOT_FILE_VERIFIED "
            f"view={self.cameras[self.camera_index]['name']} "
            f"bytes={file_record['bytes']} sha256={file_record['sha256']} "
            "pixels=pending_external_inspection"
        )
        next_index = self.camera_index + 1
        if next_index >= len(SCREENSHOT_FILENAMES):
            self._finish_success()
        else:
            self._begin_camera(next_index)

    def _unregister(self) -> None:
        if self.callback_handle is None:
            return
        handle = self.callback_handle
        unreal.unregister_slate_pre_tick_callback(handle)
        self.callback_handle = None

    def _release_active_session(self) -> None:
        global _ACTIVE_SESSION
        if _ACTIVE_SESSION is self and self.callback_handle is None:
            _ACTIVE_SESSION = None

    def _finish_success(self) -> None:
        self._unregister()
        self._release_active_session()
        self.terminal = True
        self.audit["viewport_captures"] = self.cameras
        self.audit["result"] = "passed_pending_screenshot_pixel_inspection"
        self.audit["completed_utc"] = dt.datetime.now(
            dt.timezone.utc
        ).isoformat()
        self.audit["claims"] = {
            "scratch_map_native_snap_saved": True,
            "managed_actors_snapped": 17,
            "captured_managed_state_delta_exact": True,
            "managed_state_delta": (
                "native transform snap plus exact pending-to-complete tag transition"
            ),
            "collision_accepted": False,
            "screenshot_commands_issued": len(self.cameras),
            "screenshot_files_verified": True,
            "screenshot_pixels_inspected": False,
            "real_gpu_pixels_verified": False,
            "PIE_or_gameplay_accepted": False,
            "water_integrated": False,
            "cloud_integrated": False,
            "performance_accepted": False,
            "surface_to_orbit_accepted": False,
            "production_integration_accepted": False,
        }
        _write_no_clobber_json(self.audit_output, self.audit)
        unreal.log(
            "RED_M07_TROPICAL_LIVE_VALIDATION_READY "
            f"map={DESTINATION_MAP} actors=17 saved=true "
            f"screenshot_files={len(self.cameras)} "
            "screenshot_files_verified=true pixel_review=pending "
            "pie=false editor_kept_open=true "
            f"audit={self.audit_output}"
        )

    def _finish_failure(self, exc: Exception) -> None:
        self.terminal = True
        unregister_error: Exception | None = None
        try:
            self._unregister()
        except Exception as callback_exc:
            unregister_error = callback_exc
        self._release_active_session()
        if self.snap_applied and not self.map_saved:
            try:
                self.audit["failure_recovery"] = self._attempt_undo()
            except Exception as recovery_exc:
                self.audit["failure_recovery"] = {
                    "attempted": True,
                    "restored": False,
                    "error": str(recovery_exc),
                    "map_left_unsaved": True,
                }
        if unregister_error is not None:
            self.audit["callback_cleanup"] = {
                "unregistered": False,
                "handle_retained": self.callback_handle is not None,
                "error": str(unregister_error),
            }
        else:
            self.audit["callback_cleanup"] = {
                "unregistered": True,
                "handle_retained": False,
            }
        self.audit["result"] = "failed"
        self.audit["failure"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
            "map_saved": self.map_saved,
            "snap_applied": self.snap_applied,
            "editor_kept_open": True,
        }
        self.audit["viewport_captures"] = self.cameras
        try:
            _write_no_clobber_json(self.audit_output, self.audit)
        except Exception as audit_exc:
            unreal.log_error(
                "RED_M07_TROPICAL_LIVE_AUDIT_WRITE_FAILED "
                f"path={self.audit_output} error={audit_exc}"
            )
        unreal.log_error(
            "RED_M07_TROPICAL_LIVE_VALIDATION_FAILED "
            f"state={self.state} map_saved={self.map_saved} "
            f"editor_kept_open=true error={exc}"
        )


def main() -> None:
    global _ACTIVE_SESSION
    if _ACTIVE_SESSION is not None:
        raise LiveValidationError(
            "an M07 Tropical live validation session is already active"
        )

    project_file, project_root = _validate_project_binding()
    diagnostics_dir, audit_output = _validate_diagnostics(project_root)
    base_failure: dict[str, Any] = {
        "schema_version": 1,
        "module": "M07",
        "operation": "tropical_planetary_biome_live_snap_visual_validation_v1",
        "captured_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "project_file": str(project_file),
        "project_root": str(project_root),
        "map": DESTINATION_MAP,
        "result": "failed",
        "editor_kept_open": True,
    }
    session: LiveValidationSession | None = None
    try:
        command_line_record = _validate_live_command_line(project_file)
        stage_audit_path, stage_payload, stage_audit_record = (
            _validate_stage_audit(project_file, project_root)
        )
        authenticated_files = _validate_protected_and_vendor(project_root)
        _validate_stage_audit_against_live_files(
            stage_payload, project_root, authenticated_files
        )
        session = LiveValidationSession(
            project_file=project_file,
            project_root=project_root,
            diagnostics_dir=diagnostics_dir,
            audit_output=audit_output,
            command_line_record=command_line_record,
            stage_audit_path=stage_audit_path,
            stage_payload=stage_payload,
            stage_audit_record=stage_audit_record,
            authenticated_files=authenticated_files,
        )
        session.prepare()
        _ACTIVE_SESSION = session
        try:
            session.start()
        except Exception:
            if session.callback_handle is not None:
                session._unregister()
            session._release_active_session()
            raise
    except Exception as exc:
        callback_cleanup: dict[str, Any] | None = None
        if session is not None and session.callback_handle is not None:
            try:
                session._unregister()
                session._release_active_session()
                callback_cleanup = {
                    "unregistered": True,
                    "active_session_cleared": _ACTIVE_SESSION is None,
                }
            except Exception as cleanup_exc:
                callback_cleanup = {
                    "unregistered": False,
                    "active_session_cleared": False,
                    "error": str(cleanup_exc),
                }
        elif session is not None:
            session._release_active_session()
            callback_cleanup = {
                "unregistered": True,
                "active_session_cleared": _ACTIVE_SESSION is None,
            }
        base_failure["failure"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        if callback_cleanup is not None:
            base_failure["callback_cleanup"] = callback_cleanup
        try:
            _write_no_clobber_json(audit_output, base_failure)
        except Exception as audit_exc:
            unreal.log_error(
                "RED_M07_TROPICAL_LIVE_PREFLIGHT_AUDIT_WRITE_FAILED "
                f"path={audit_output} error={audit_exc}"
            )
        unreal.log_error(
            "RED_M07_TROPICAL_LIVE_PREFLIGHT_FAILED "
            f"editor_kept_open=true error={exc}"
        )
        raise


if __name__ == "__main__":
    main()
