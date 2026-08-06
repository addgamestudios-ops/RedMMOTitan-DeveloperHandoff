"""Create the isolated M07 Tropical planetary-biome visual staging map.

This script is intentionally *not* a general environment importer.  Run it only
through Unreal Engine 5.8's PythonScript commandlet against a freshly copied,
D:-resident RedMMOTitan scratch clone.  The caller must bind the exact project
file and an external no-clobber audit path through:

    REDMMO_M07_TROPICAL_STAGE_PROJECT_FILE
    REDMMO_M07_TROPICAL_STAGE_AUDIT_OUTPUT

The commandlet duplicates the protected fused-prototype map inside the scratch
clone, references four reviewed Tropical static meshes, and creates a small
collision-free visual cluster at deterministic authoring region 15.  It does
not import, migrate, rename, resave, or modify vendor assets.  It does not apply
vendor water, landscape, atmosphere, sky, sun, fog, post-process, cloud, RVT,
or MM_Sun assets.  Sand and water textures are authenticated and recorded only.

All actors are deliberately staged above the maximum authored terrain height
and tagged ``PendingNativePlanetSnap``.  A later, separately reviewed editor
step must use RedMMO.SnapSelectedMeshesToPlanet; this script never guesses the
final terrain surface or invokes that command.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import re
import stat
import traceback
from pathlib import Path
from typing import Any

import unreal


PROJECT_FILE_ENV = "REDMMO_M07_TROPICAL_STAGE_PROJECT_FILE"
AUDIT_OUTPUT_ENV = "REDMMO_M07_TROPICAL_STAGE_AUDIT_OUTPUT"

SCRATCH_ROOT = Path(r"D:\RedMMOTitanWindowsData\Scratch")
DIAGNOSTICS_ROOT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics")

REQUIRED_DISABLED_PLUGINS = (
    "AndroidFileServer",
    "AIAssistant",
    "Nwiro",
    "NwiroIntegrationKit",
    "UnrealAIIntegrationPlatform",
    "ModelContextProtocol",
)

SOURCE_MAP = "/Game/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype"
DESTINATION_MAP = (
    "/Game/RedMMO/Maps/Tests/"
    "RedPlanetGen_50km_FusedPrototype_M07_TropicalBiomeStage_V1"
)
DESTINATION_MAP_RELATIVE = Path(
    "RedMMO",
    "Maps",
    "Tests",
    "RedPlanetGen_50km_FusedPrototype_M07_TropicalBiomeStage_V1.umap",
)

REGION_INDEX = 15
EXPECTED_REGION = {
    "seed": 3_354_735_782,
    "archetype": "CoralCanopyCoast",
    "unit_site": (
        0.13523942097797426,
        -0.9796746527362116,
        -0.14814814814814814,
    ),
    "suggested_hub_radius_cm": 39_802.096176,
    "suggested_flatten_core_radius_cm": 23_881.257706,
    "suggested_flatten_blend_radius_cm": 15_920.838471,
    "reservation_id": "R15_CoralCanopyCoast_MainHub",
    "stable_guid": "EE37C6F3-C688-5390-B27E-3FB177050588",
}

EXPECTED_PLANET_RADIUS_CM = 795_774.7154594767
PLANET_NORTH_AXIS = (0.0, 0.0, 1.0)
# The fused profile has a +30,000 cm authored maximum.  Keep all pilot props
# 40 m above that ceiling until the native terrain-snap review is performed.
PRE_SNAP_ALTITUDE_CM = 34_000.0
MANAGED_TAG = "RedMMO_M07_TropicalBiomeStage_V1"
ACTOR_FOLDER_ROOT = "RedMMO/Staging/M07/TropicalBiome/R15"

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

MESH_ROOTS = {
    "cliff": {
        "package": "/Game/Zenscape_Island/Model/Rocks/SM_Cliff_01",
        "bytes": 316_046,
        "sha256":
            "49A14C32F6F36AF8853337D9714754E318D6AAA7A312AC548090256F17E9EE1D",
        "required": True,
    },
    "coconut": {
        "package": "/Game/Zenscape_Island/Model/Tree/SM_CoconutTree_01",
        "bytes": 152_377,
        "sha256":
            "925C3DA342358836CEB7F6EAC0933D2B2742459C0F39CB1FFA8D5EA9E4FE82F9",
        "required": True,
    },
    "plant": {
        "package": "/Game/Zenscape_Island/Model/Plants/SM_Plant_01",
        "bytes": 56_344,
        "sha256":
            "B169632CBB5B73C27616143437B9FD046542260EC60E901E08326453CD46FD7E",
        "required": True,
    },
    "coral": {
        "package": "/Game/Zenscape_Island/Model/Plants/SM_Coral_01",
        "bytes": 23_931,
        "sha256":
            "D3889034815975E9819CF9439FB657E0D04E139A0EF95555EFA6DE9F8C877CEA",
        "required": False,
    },
}

# These exact files are present for a future project-owned material adapter.
# This authoring commandlet authenticates but never loads or applies them.
STAGED_UNAPPLIED_TEXTURES = {
    "/Game/Zenscape_Island/Texture/Landscape/T_Sand_Stylized_BaseColor": {
        "bytes": 4_915_934,
        "sha256":
            "912E9BFFC157BD7FD785520815300EBD08BFA64DA934322E91123DFA31E6D705",
        "intent": "future RedMMO-owned sand material adapter; not applied",
    },
    "/Game/Zenscape_Island/Texture/Landscape/"
    "T_Sand_Stylized_Normalsand_04_normal_dx_2k": {
        "bytes": 4_442_298,
        "sha256":
            "7EC9E59A8DE4599BFBC0CA8C14A203CFF15B62D29CEF6032688C8F1AF4B53581",
        "intent": "future RedMMO-owned sand material adapter; not applied",
    },
    "/Game/Zenscape_Island/Texture/Landscape/T_Sand_Stylized_Height": {
        "bytes": 5_191_408,
        "sha256":
            "AB49F8B8DE2F94A05B2169BA62C7A5F69AA335DD1B07944E8550B3C26641C146",
        "intent": "future RedMMO-owned sand material adapter; not applied",
    },
    "/Game/Zenscape_Island/Texture/Landscape/T_Sand_AO": {
        "bytes": 5_614_332,
        "sha256":
            "4FC402A81C84CC833E3B51D9CD7811EA0D44E3D7B49C90000163B5E0D8F9E5A5",
        "intent": "future RedMMO-owned sand material adapter; not applied",
    },
    "/Game/Zenscape_Island/Texture/Water/Water/T_DetailWater01_Normal": {
        "bytes": 166_301,
        "sha256":
            "EF46E4D6C3E7C64477FBCCEF86F40C72C20EF12F1811B871BA60BCB5D01403EC",
        "intent": "future RedMMO-owned local-water adapter; not applied",
    },
    "/Game/Zenscape_Island/Texture/Water/Water/T_StylizedWater_Ocean_DP": {
        "bytes": 1_140_452,
        "sha256":
            "9962892A7370EEEBF03E589321820A277DE8700465FD5598F2508CF7A344A565",
        "intent": "future RedMMO-owned local-water adapter; not applied",
    },
    "/Game/Zenscape_Island/Texture/Water/Water/T_StylizedWater_Ocean_N": {
        "bytes": 1_231_099,
        "sha256":
            "6AADF08B60B432594159A304695E3226E6537C152BD9CEB7C766DEE58C227D32",
        "intent": "future RedMMO-owned local-water adapter; not applied",
    },
}

# Fixed asymmetric offsets avoid the uniform rows that are unsuitable for an
# organic coastal landmark.  Every point remains inside region 15's protected
# hub radius.  Yaw is applied about the local radial up vector, not world Z.
PLACEMENTS = (
    ("CliffGate", "cliff", -11_600.0, 4_900.0, 17.0, (3.0, 2.4, 2.7)),
    ("CoconutA", "coconut", -7_400.0, -4_600.0, 31.0, (1.45, 1.45, 1.45)),
    ("CoconutB", "coconut", -2_100.0, 7_800.0, 113.0, (1.20, 1.20, 1.20)),
    ("CoconutC", "coconut", 4_300.0, 2_100.0, 206.0, (1.58, 1.58, 1.58)),
    ("CoconutD", "coconut", 9_600.0, -6_100.0, 287.0, (1.32, 1.32, 1.32)),
    ("CoconutE", "coconut", 11_100.0, 6_800.0, 342.0, (1.50, 1.50, 1.50)),
    ("PlantA", "plant", -8_900.0, 1_400.0, 62.0, (1.90, 1.90, 1.90)),
    ("PlantB", "plant", -5_500.0, 5_700.0, 151.0, (1.35, 1.35, 1.35)),
    ("PlantC", "plant", -3_900.0, -7_900.0, 239.0, (2.15, 2.15, 2.15)),
    ("PlantD", "plant", 500.0, -2_900.0, 326.0, (1.55, 1.55, 1.55)),
    ("PlantE", "plant", 2_200.0, 8_900.0, 44.0, (1.80, 1.80, 1.80)),
    ("PlantF", "plant", 6_100.0, -1_100.0, 132.0, (1.40, 1.40, 1.40)),
    ("PlantG", "plant", 7_800.0, 5_200.0, 221.0, (2.05, 2.05, 2.05)),
    ("PlantH", "plant", 12_700.0, 900.0, 309.0, (1.60, 1.60, 1.60)),
    ("CoralA", "coral", -14_000.0, -2_500.0, 28.0, (1.70, 1.70, 1.70)),
    ("CoralB", "coral", -11_900.0, -7_100.0, 164.0, (2.05, 2.05, 2.05)),
    ("CoralC", "coral", 14_300.0, -2_100.0, 296.0, (1.55, 1.55, 1.55)),
)

EXPLICITLY_EXCLUDED = (
    "vendor demo maps and BuiltData",
    "BP_WaterPlane and all vendor water actors/material masters",
    "vendor landscape masters and RVT landscape assignment",
    "MM_Sun and vendor directional-light setup",
    "vendor SkyAtmosphere, sky dome/skybox, fog, post-process, and exposure",
    "MI_VolumetricCloud_S and all vendor cloud material assignment",
    "vendor foliage actors, foliage-type assets, PCG, and automatic scattering",
    "underwater post-process, caustics, fish, swimming, and gameplay setup",
)


class StageError(RuntimeError):
    """Fail-closed staging contract violation."""


def _norm(path: Path) -> str:
    return os.path.normcase(os.path.realpath(os.fspath(path)))


def _is_under(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((_norm(path), _norm(root))) == _norm(root)
    except ValueError:
        return False


def _assert_no_reparse_points(path: Path) -> None:
    """Reject symlinks and Windows junctions in every existing path component."""

    current = Path(path.anchor)
    parts = path.parts[1:]
    for part in parts:
        current /= part
        if not current.exists():
            continue
        info = os.lstat(current)
        attributes = int(getattr(info, "st_file_attributes", 0))
        if current.is_symlink() or (
            attributes & int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
        ):
            raise StageError(f"reparse point is forbidden in staging path: {current}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _file_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _package_file(project_root: Path, package_name: str, suffix: str) -> Path:
    if not package_name.startswith("/Game/"):
        raise StageError(f"not a /Game package: {package_name}")
    relative = package_name[len("/Game/") :].replace("/", os.sep) + suffix
    return project_root / "Content" / relative


def _authenticate_file(
    path: Path, *, expected_bytes: int | None, expected_sha256: str, label: str
) -> dict[str, Any]:
    if not path.is_file():
        raise StageError(f"{label} is missing: {path}")
    actual_bytes = path.stat().st_size
    actual_sha256 = _sha256(path)
    if expected_bytes is not None and actual_bytes != expected_bytes:
        raise StageError(
            f"{label} length drifted: expected {expected_bytes}, got {actual_bytes}: {path}"
        )
    if actual_sha256 != expected_sha256:
        raise StageError(
            f"{label} hash drifted: expected {expected_sha256}, "
            f"got {actual_sha256}: {path}"
        )
    return {
        "path": str(path),
        "bytes": actual_bytes,
        "sha256": actual_sha256,
    }


def _validate_project_binding() -> tuple[Path, Path]:
    expected_text = os.environ.get(PROJECT_FILE_ENV, "").strip()
    if not expected_text:
        raise StageError(f"required environment variable is unset: {PROJECT_FILE_ENV}")
    expected_project = Path(expected_text)
    if not expected_project.is_absolute() or not expected_project.is_file():
        raise StageError(f"bound project file is not an existing absolute file: {expected_project}")

    actual_text = unreal.Paths.convert_relative_path_to_full(
        unreal.Paths.get_project_file_path()
    )
    actual_project = Path(actual_text)
    if not actual_project.is_file():
        raise StageError(f"Unreal reported a missing project file: {actual_project}")
    if _norm(actual_project) != _norm(expected_project):
        raise StageError(
            "project binding mismatch: "
            f"environment={expected_project} unreal={actual_project}"
        )

    project_root = actual_project.parent
    if not _is_under(project_root, SCRATCH_ROOT):
        raise StageError(
            f"project is outside the required D: scratch root: {project_root}"
        )
    if _norm(project_root) == _norm(SCRATCH_ROOT):
        raise StageError("scratch root itself cannot be used as the Unreal project")
    if _norm(project_root) == _norm(Path(r"D:\RedMMOTitan")):
        raise StageError("production RedMMOTitan is explicitly forbidden")
    if actual_project.name.lower() != "titan.uproject":
        raise StageError(
            f"expected the RedMMOTitan Titan.uproject clone, got: {actual_project.name}"
        )
    _assert_no_reparse_points(project_root)
    return actual_project, project_root


def _validate_audit_output(project_root: Path) -> Path:
    output_text = os.environ.get(AUDIT_OUTPUT_ENV, "").strip()
    if not output_text:
        raise StageError(f"required environment variable is unset: {AUDIT_OUTPUT_ENV}")
    output = Path(output_text)
    if not output.is_absolute() or output.suffix.lower() != ".json":
        raise StageError(f"audit output must be an absolute .json path: {output}")
    if output.exists():
        raise StageError(f"audit output is no-clobber and already exists: {output}")
    if not DIAGNOSTICS_ROOT.is_dir():
        raise StageError(f"diagnostics root is missing: {DIAGNOSTICS_ROOT}")
    if not _is_under(output, DIAGNOSTICS_ROOT):
        raise StageError(
            f"audit output must remain under {DIAGNOSTICS_ROOT}: {output}"
        )
    if _is_under(output, project_root):
        raise StageError(f"audit output must be external to the scratch project: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    _assert_no_reparse_points(output.parent)
    return output


def _validate_provider_off_command_line() -> dict[str, Any]:
    command_line = str(unreal.SystemLibrary.get_command_line())
    boundary = r"""[\s"']"""

    def option_values(name: str) -> list[str]:
        pattern = re.compile(
            rf"""(?:^|{boundary})-{re.escape(name)}="""
            rf"""(?:"([^"]*)"|'([^']*)'|([^"'\s]+))(?=$|{boundary})""",
            re.IGNORECASE,
        )
        return [
            next(group for group in match.groups() if group is not None)
            for match in pattern.finditer(command_line)
        ]

    disable_values = option_values("DisablePlugins")
    required_value = ",".join(REQUIRED_DISABLED_PLUGINS)
    if disable_values != [required_value]:
        raise StageError(
            "provider-off launch contract requires exactly one exact "
            f"-DisablePlugins={required_value} option; observed={disable_values}"
        )

    enable_all_pattern = re.compile(
        rf"""(?:^|{boundary})-EnableAllPlugins"""
        rf"""(?:=(?:"[^"]*"|'[^']*'|[^"'\s]+))?(?=$|{boundary})""",
        re.IGNORECASE,
    )
    if enable_all_pattern.search(command_line):
        raise StageError(
            "provider-off launch contract forbids -EnableAllPlugins"
        )

    required_names = {name.casefold() for name in REQUIRED_DISABLED_PLUGINS}
    conflicting_enable_values: list[str] = []
    for value in option_values("EnablePlugins"):
        enabled_names = {
            name.strip().casefold() for name in value.split(",") if name.strip()
        }
        if enabled_names & required_names:
            conflicting_enable_values.append(value)
    if conflicting_enable_values:
        raise StageError(
            "provider-off launch contract has conflicting -EnablePlugins "
            f"values: {conflicting_enable_values}"
        )

    return {
        "required_disable_option": f"-DisablePlugins={required_value}",
        "disabled_plugins": list(REQUIRED_DISABLED_PLUGINS),
        "command_line_verified": True,
        "conflicting_enable_plugins": [],
        "enable_all_plugins_present": False,
    }


def _write_no_clobber_json(path: Path, payload: dict[str, Any]) -> None:
    encoded = (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    ).encode("utf-8")
    descriptor = os.open(
        path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o600
    )
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)


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


def _validate_protected_files(project_root: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for relative, expected_hash in PROTECTED_PROJECT_FILES.items():
        records[str(relative).replace("\\", "/")] = _authenticate_file(
            project_root / relative,
            expected_bytes=None,
            expected_sha256=expected_hash,
            label=f"protected scratch-clone source {relative}",
        )
    return records


def _struct_value(value: Any, property_name: str) -> Any:
    try:
        return value.get_editor_property(property_name)
    except Exception:
        return getattr(value, property_name)


def _xyz(value: Any) -> tuple[float, float, float]:
    return (float(value.x), float(value.y), float(value.z))


def _vector_distance(a: Any, b: Any) -> float:
    ax, ay, az = _xyz(a)
    bx, by, bz = _xyz(b)
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)


def _length(value: Any) -> float:
    x, y, z = _xyz(value)
    return math.sqrt(x * x + y * y + z * z)


def _normalize_tuple(value: tuple[float, float, float]) -> tuple[float, float, float]:
    magnitude = math.sqrt(sum(component * component for component in value))
    if magnitude <= 1.0e-12:
        raise StageError("cannot normalize a zero vector")
    return tuple(component / magnitude for component in value)


def _cross(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _surface_rotation(frame: Any, yaw_degrees: float) -> Any:
    up = _normalize_tuple(_xyz(_struct_value(frame, "unit_up")))
    east = _normalize_tuple(_xyz(_struct_value(frame, "unit_east")))
    north = _normalize_tuple(_xyz(_struct_value(frame, "unit_north")))
    yaw_radians = math.radians(yaw_degrees)
    forward = _normalize_tuple(
        tuple(
            (east[index] * math.cos(yaw_radians))
            + (north[index] * math.sin(yaw_radians))
            for index in range(3)
        )
    )
    right = _normalize_tuple(_cross(up, forward))

    math_library = getattr(unreal, "MathLibrary", None)
    if math_library is None:
        math_library = getattr(unreal, "KismetMathLibrary", None)
    make_rotation = (
        getattr(math_library, "make_rotation_from_axes", None)
        if math_library is not None
        else None
    )
    if make_rotation is None:
        raise StageError(
            "Unreal MathLibrary.make_rotation_from_axes is unavailable; "
            "refusing to create incorrectly oriented surface actors"
        )
    return make_rotation(
        unreal.Vector(*forward), unreal.Vector(*right), unreal.Vector(*up)
    )


def _validate_organic_layout() -> None:
    offsets = [(float(row[2]), float(row[3])) for row in PLACEMENTS]
    if len(offsets) != len(set(offsets)):
        raise StageError("organic cluster contains duplicate tangent offsets")
    if len({x for x, _ in offsets}) < 6 or len({y for _, y in offsets}) < 6:
        raise StageError("organic cluster does not have enough two-axis variation")
    maximum_radius = max(math.hypot(x, y) for x, y in offsets)
    if maximum_radius >= EXPECTED_REGION["suggested_flatten_core_radius_cm"]:
        raise StageError(
            "organic cluster exceeds region 15's protected/core staging radius: "
            f"{maximum_radius}"
        )
    # Explicitly reject a collinear layout using the first three distinct
    # landmark/tree points.
    ax, ay = offsets[0]
    bx, by = offsets[1]
    cx, cy = offsets[2]
    twice_area = abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax))
    if twice_area < 1_000_000.0:
        raise StageError("organic cluster's landmark basis is effectively collinear")


def _current_world_package() -> str:
    world = unreal.get_editor_subsystem(
        unreal.UnrealEditorSubsystem
    ).get_editor_world()
    if world is None:
        raise StageError("Unreal has no current editor world")
    return str(world.get_path_name()).split(".", 1)[0]


def _run_stage(project_root: Path) -> dict[str, Any]:
    _validate_organic_layout()
    dirty_before = _dirty_packages()
    if dirty_before != {"content": [], "maps": []}:
        raise StageError(
            f"scratch commandlet started with dirty packages: {dirty_before}"
        )

    protected_before = _validate_protected_files(project_root)
    destination_file = project_root / "Content" / DESTINATION_MAP_RELATIVE
    if destination_file.exists():
        raise StageError(
            "destination map is no-clobber and already exists: "
            f"{destination_file}"
        )

    mesh_file_records: dict[str, dict[str, Any]] = {}
    loaded_meshes: dict[str, Any] = {}
    for key, spec in MESH_ROOTS.items():
        package = str(spec["package"])
        path = _package_file(project_root, package, ".uasset")
        if not path.is_file() and not bool(spec["required"]):
            mesh_file_records[key] = {
                "package": package,
                "available": False,
                "required": False,
            }
            continue
        record = _authenticate_file(
            path,
            expected_bytes=int(spec["bytes"]),
            expected_sha256=str(spec["sha256"]),
            label=f"reviewed Tropical {key} mesh",
        )
        mesh = unreal.load_asset(package)
        if mesh is None or mesh.get_class().get_name() != "StaticMesh":
            raise StageError(
                f"reviewed Tropical root did not load as StaticMesh: {package}"
            )
        if not str(mesh.get_path_name()).startswith(package + "."):
            raise StageError(
                f"loaded Tropical mesh object escaped its exact package: "
                f"{mesh.get_path_name()}"
            )
        record.update(
            {
                "package": package,
                "object_path": str(mesh.get_path_name()),
                "class": mesh.get_class().get_name(),
                "available": True,
                "required": bool(spec["required"]),
            }
        )
        mesh_file_records[key] = record
        loaded_meshes[key] = mesh

    staged_texture_records: dict[str, dict[str, Any]] = {}
    for package, spec in STAGED_UNAPPLIED_TEXTURES.items():
        path = _package_file(project_root, package, ".uasset")
        record = _authenticate_file(
            path,
            expected_bytes=int(spec["bytes"]),
            expected_sha256=str(spec["sha256"]),
            label=f"staged-but-unapplied Tropical texture {package}",
        )
        record.update(
            {
                "package": package,
                "loaded_by_script": False,
                "applied_by_script": False,
                "intent": str(spec["intent"]),
            }
        )
        staged_texture_records[package] = record

    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not level_subsystem.new_level_from_template(DESTINATION_MAP, SOURCE_MAP):
        raise StageError(
            f"failed to create {DESTINATION_MAP} from protected template {SOURCE_MAP}"
        )
    if _current_world_package() != DESTINATION_MAP:
        raise StageError(
            "templated world is not the expected destination: "
            f"{_current_world_package()}"
        )

    # Templating must not rewrite any protected rollback source.
    protected_after_template = _validate_protected_files(project_root)
    if protected_after_template != protected_before:
        raise StageError("protected scratch-clone hashes changed during map templating")

    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actor_paths = [
        str(actor.get_path_name()) for actor in actor_subsystem.get_all_level_actors()
    ]
    escaped_actors = [
        path for path in actor_paths if not path.startswith(DESTINATION_MAP + ".")
    ]
    if escaped_actors:
        raise StageError(
            f"templated world exposes actors outside the destination map: {escaped_actors}"
        )

    planet_class = getattr(unreal, "CLMPlanet", None)
    anchor_class = getattr(unreal, "RedPlanetRegionAnchor", None)
    region_library = getattr(unreal, "RedPlanetRegionBlueprintLibrary", None)
    if planet_class is None or anchor_class is None or region_library is None:
        raise StageError(
            "required compiled RedMMO/PlanetGen reflected types are unavailable: "
            f"CLMPlanet={planet_class} RedPlanetRegionAnchor={anchor_class} "
            f"RedPlanetRegionBlueprintLibrary={region_library}"
        )

    planets = [
        actor
        for actor in actor_subsystem.get_all_level_actors()
        if isinstance(actor, planet_class)
    ]
    if len(planets) != 1:
        raise StageError(
            f"expected exactly one CLMPlanet in scratch stage, found {len(planets)}"
        )
    planet = planets[0]
    planet_radius_cm = float(planet.get_editor_property("planet_radius"))
    if abs(planet_radius_cm - EXPECTED_PLANET_RADIUS_CM) > 1.0:
        raise StageError(
            f"scratch template planet radius drifted: {planet_radius_cm}"
        )
    planet_center = planet.get_actor_location()

    anchors = [
        actor
        for actor in actor_subsystem.get_all_level_actors()
        if isinstance(actor, anchor_class)
        and int(actor.get_editor_property("region_index")) == REGION_INDEX
    ]
    if len(anchors) != 1:
        raise StageError(
            f"expected exactly one inherited region-15 anchor, found {len(anchors)}"
        )
    anchor = anchors[0]
    if not str(anchor.get_path_name()).startswith(DESTINATION_MAP + "."):
        raise StageError(
            f"region-15 anchor escaped destination map: {anchor.get_path_name()}"
        )

    anchor_seed = int(anchor.get_editor_property("seed"))
    anchor_archetype = str(anchor.get_editor_property("archetype_tag"))
    anchor_site = anchor.get_editor_property("unit_site")
    if anchor_seed != EXPECTED_REGION["seed"]:
        raise StageError(
            f"region-15 seed drifted: expected {EXPECTED_REGION['seed']}, "
            f"got {anchor_seed}"
        )
    if anchor_archetype != EXPECTED_REGION["archetype"]:
        raise StageError(
            f"region-15 archetype drifted: expected {EXPECTED_REGION['archetype']}, "
            f"got {anchor_archetype}"
        )
    expected_site = unreal.Vector(*EXPECTED_REGION["unit_site"])
    if _vector_distance(anchor_site, expected_site) > 1.0e-9:
        raise StageError(
            f"region-15 unit site drifted: expected {EXPECTED_REGION['unit_site']}, "
            f"got {_xyz(anchor_site)}"
        )
    if _vector_distance(
        anchor.get_editor_property("planet_center"), planet_center
    ) > 0.01:
        raise StageError("region-15 anchor and CLMPlanet centers disagree")
    if (
        abs(
            float(anchor.get_editor_property("planet_radius_cm"))
            - planet_radius_cm
        )
        > 1.0
    ):
        raise StageError("region-15 anchor and CLMPlanet radii disagree")

    for property_name, expected in (
        ("suggested_hub_radius_cm", EXPECTED_REGION["suggested_hub_radius_cm"]),
        (
            "suggested_flatten_core_radius_cm",
            EXPECTED_REGION["suggested_flatten_core_radius_cm"],
        ),
        (
            "suggested_flatten_blend_radius_cm",
            EXPECTED_REGION["suggested_flatten_blend_radius_cm"],
        ),
    ):
        actual = float(anchor.get_editor_property(property_name))
        if abs(actual - float(expected)) > 0.01:
            raise StageError(
                f"region-15 {property_name} drifted: expected {expected}, got {actual}"
            )

    native_regions = list(region_library.get_all_planet_regions())
    native_region = next(
        (
            region
            for region in native_regions
            if int(_struct_value(region, "region_index")) == REGION_INDEX
        ),
        None,
    )
    if native_region is None:
        raise StageError("native region service did not return region 15")
    if int(_struct_value(native_region, "seed")) != anchor_seed:
        raise StageError("native region service and inherited anchor seeds disagree")
    if _vector_distance(
        _struct_value(native_region, "unit_site"), anchor_site
    ) > 1.0e-9:
        raise StageError(
            "native region service and inherited region-15 anchor sites disagree"
        )

    north_axis = unreal.Vector(*PLANET_NORTH_AXIS)
    anchor_frame = region_library.make_planet_tangent_frame(
        anchor_site, north_axis
    )
    actor_records: list[dict[str, Any]] = []
    for label, mesh_key, offset_x, offset_y, yaw, scale in PLACEMENTS:
        mesh = loaded_meshes.get(mesh_key)
        if mesh is None:
            if mesh_key == "coral" and not MESH_ROOTS["coral"]["required"]:
                continue
            raise StageError(f"required staged mesh was not loaded: {mesh_key}")

        local_offset = unreal.Vector2D(float(offset_x), float(offset_y))
        location = region_library.planet_tangent_offset_to_position(
            planet_center,
            anchor_site,
            local_offset,
            PRE_SNAP_ALTITUDE_CM,
            planet_radius_cm,
            north_axis,
        )
        local_direction = region_library.planet_tangent_offset_to_direction(
            anchor_site, local_offset, planet_radius_cm, north_axis
        )
        local_frame = region_library.make_planet_tangent_frame(
            local_direction, north_axis
        )
        rotation = _surface_rotation(local_frame, float(yaw))
        radial_distance = _vector_distance(location, planet_center)
        expected_radial_distance = planet_radius_cm + PRE_SNAP_ALTITUDE_CM
        if abs(radial_distance - expected_radial_distance) > 1.0:
            raise StageError(
                f"native exponential-map placement radius drifted for {label}: "
                f"expected {expected_radial_distance}, got {radial_distance}"
            )

        actor = actor_subsystem.spawn_actor_from_class(
            unreal.StaticMeshActor, location, rotation
        )
        if actor is None or not isinstance(actor, unreal.StaticMeshActor):
            raise StageError(f"failed to spawn native StaticMeshActor for {label}")
        if not str(actor.get_path_name()).startswith(DESTINATION_MAP + "."):
            raise StageError(
                f"spawned actor escaped the scratch destination: {actor.get_path_name()}"
            )
        component = actor.get_editor_property("static_mesh_component")
        if component is None:
            raise StageError(f"spawned StaticMeshActor has no mesh component: {label}")
        component.set_static_mesh(mesh)
        actor.set_actor_scale3d(unreal.Vector(*scale))
        actor.set_actor_enable_collision(False)
        component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        component.set_editor_property("generate_overlap_events", False)
        actor.set_actor_label(f"M07_Tropical_{label}")
        actor.set_folder_path(
            unreal.Name(f"{ACTOR_FOLDER_ROOT}/{mesh_key.capitalize()}")
        )
        actor.set_editor_property(
            "tags",
            [
                unreal.Name(MANAGED_TAG),
                unreal.Name("RedMMO_TropicalIslandBiome"),
                unreal.Name("RedRegion_15"),
                unreal.Name("VisualStagingOnly"),
                unreal.Name("PendingNativePlanetSnap"),
                unreal.Name("NoCollision"),
            ],
        )

        assigned_mesh = component.get_editor_property("static_mesh")
        if (
            assigned_mesh is None
            or str(assigned_mesh.get_path_name()) != str(mesh.get_path_name())
        ):
            raise StageError(f"mesh assignment failed for {label}")
        if actor.get_actor_enable_collision():
            raise StageError(f"actor collision remained enabled for {label}")
        if component.get_collision_enabled() != unreal.CollisionEnabled.NO_COLLISION:
            raise StageError(f"component collision remained enabled for {label}")
        if bool(component.get_editor_property("generate_overlap_events")):
            raise StageError(f"component overlap generation remained enabled for {label}")

        actor_records.append(
            {
                "label": actor.get_actor_label(),
                "actor_path": str(actor.get_path_name()),
                "actor_class": actor.get_class().get_name(),
                "mesh_key": mesh_key,
                "mesh_object_path": str(mesh.get_path_name()),
                "tangent_offset_cm": [float(offset_x), float(offset_y)],
                "pre_snap_altitude_cm": PRE_SNAP_ALTITUDE_CM,
                "intended_local_yaw_degrees": float(yaw),
                "location_cm": list(_xyz(actor.get_actor_location())),
                "surface_direction": list(_xyz(local_direction)),
                "scale": [float(value) for value in scale],
                "collision": "disabled",
                "native_planet_snap": "pending_separate_editor_step",
                "folder": f"{ACTOR_FOLDER_ROOT}/{mesh_key.capitalize()}",
                "tags": sorted(
                    str(tag) for tag in actor.get_editor_property("tags")
                ),
            }
        )

    if len(actor_records) < 14:
        raise StageError(
            f"visual cluster is unexpectedly incomplete: {len(actor_records)} actors"
        )
    if not any(record["mesh_key"] == "cliff" for record in actor_records):
        raise StageError("visual cluster is missing its cliff landmark")
    if not any(record["mesh_key"] == "coconut" for record in actor_records):
        raise StageError("visual cluster is missing coconut-tree dressing")
    if not any(record["mesh_key"] == "plant" for record in actor_records):
        raise StageError("visual cluster is missing plant dressing")

    dirty_before_save = _dirty_packages()
    if dirty_before_save["content"]:
        raise StageError(
            "vendor/project content became dirty before map save: "
            f"{dirty_before_save['content']}"
        )
    unexpected_dirty_maps = [
        package
        for package in dirty_before_save["maps"]
        if package != DESTINATION_MAP
    ]
    if unexpected_dirty_maps:
        raise StageError(
            f"maps outside the scratch destination became dirty: {unexpected_dirty_maps}"
        )
    if not level_subsystem.save_current_level():
        raise StageError(f"failed to save scratch destination map: {DESTINATION_MAP}")
    if not destination_file.is_file():
        raise StageError(f"saved scratch destination map is missing: {destination_file}")

    dirty_after_save = _dirty_packages()
    if dirty_after_save != {"content": [], "maps": []}:
        raise StageError(
            f"scratch map save left dirty packages behind: {dirty_after_save}"
        )
    protected_after_save = _validate_protected_files(project_root)
    if protected_after_save != protected_before:
        raise StageError("protected scratch-clone sources changed after destination save")

    # Re-authenticate every selected root after the save.  Saving the map must
    # not forward-save or rewrite any referenced vendor package.
    mesh_hashes_after: dict[str, str] = {}
    for key, spec in MESH_ROOTS.items():
        path = _package_file(project_root, str(spec["package"]), ".uasset")
        if not path.is_file() and not bool(spec["required"]):
            continue
        mesh_hashes_after[key] = _authenticate_file(
            path,
            expected_bytes=int(spec["bytes"]),
            expected_sha256=str(spec["sha256"]),
            label=f"post-save Tropical {key} mesh",
        )["sha256"]
    texture_hashes_after: dict[str, str] = {}
    for package, spec in STAGED_UNAPPLIED_TEXTURES.items():
        texture_hashes_after[package] = _authenticate_file(
            _package_file(project_root, package, ".uasset"),
            expected_bytes=int(spec["bytes"]),
            expected_sha256=str(spec["sha256"]),
            label=f"post-save staged texture {package}",
        )["sha256"]

    anchor_frame_record = {
        "unit_up": list(_xyz(_struct_value(anchor_frame, "unit_up"))),
        "unit_east": list(_xyz(_struct_value(anchor_frame, "unit_east"))),
        "unit_north": list(_xyz(_struct_value(anchor_frame, "unit_north"))),
    }
    return {
        "source_map": SOURCE_MAP,
        "destination_map": DESTINATION_MAP,
        "destination_map_file": _file_record(destination_file),
        "save_scope": "save_current_level_only",
        "protected_files_before": protected_before,
        "protected_files_after": protected_after_save,
        "reviewed_mesh_roots": mesh_file_records,
        "mesh_hashes_after_save": mesh_hashes_after,
        "staged_unapplied_textures": staged_texture_records,
        "staged_texture_hashes_after_save": texture_hashes_after,
        "region": {
            "region_index": REGION_INDEX,
            "seed": anchor_seed,
            "archetype": anchor_archetype,
            "unit_site": list(_xyz(anchor_site)),
            "reservation_id": EXPECTED_REGION["reservation_id"],
            "stable_guid": EXPECTED_REGION["stable_guid"],
            "suggested_hub_radius_cm": float(
                anchor.get_editor_property("suggested_hub_radius_cm")
            ),
            "suggested_flatten_core_radius_cm": float(
                anchor.get_editor_property("suggested_flatten_core_radius_cm")
            ),
            "suggested_flatten_blend_radius_cm": float(
                anchor.get_editor_property("suggested_flatten_blend_radius_cm")
            ),
            "native_service_anchor_match": True,
            "tangent_frame": anchor_frame_record,
        },
        "planet": {
            "center_cm": list(_xyz(planet_center)),
            "radius_cm": planet_radius_cm,
            "planetgen_actor": str(planet.get_path_name()),
            "redmmo_owned_terrain_water_atmosphere_authority_preserved": True,
        },
        "cluster": {
            "algorithm": (
                "fixed asymmetric tangent offsets with native exponential-map "
                "positions and per-site radial frames"
            ),
            "actor_count": len(actor_records),
            "actors": actor_records,
            "pre_snap_altitude_cm": PRE_SNAP_ALTITUDE_CM,
            "collision": "disabled",
            "native_planet_snap": (
                "not_run; requires separately reviewed "
                "RedMMO.SnapSelectedMeshesToPlanet editor step"
            ),
        },
        "dirty_packages": {
            "before": dirty_before,
            "before_save": dirty_before_save,
            "after_save": dirty_after_save,
        },
        "explicitly_excluded": list(EXPLICITLY_EXCLUDED),
        "claims": {
            "scratch_map_created": True,
            "visual_staging_cluster_created": True,
            "vendor_assets_resaved": False,
            "production_content_modified": False,
            "native_terrain_snap_complete": False,
            "water_integrated": False,
            "cloud_integrated": False,
            "collision_accepted": False,
            "gameplay_accepted": False,
            "performance_accepted": False,
            "surface_to_orbit_accepted": False,
            "real_gpu_visual_accepted": False,
        },
    }


def main() -> None:
    actual_project, project_root = _validate_project_binding()
    provider_off = _validate_provider_off_command_line()
    audit_output = _validate_audit_output(project_root)
    audit: dict[str, Any] = {
        "schema_version": 1,
        "module": "M07",
        "operation": "tropical_planetary_biome_scratch_stage_v1",
        "evidence_class": "automation",
        "captured_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "project_file": str(actual_project),
        "project_root": str(project_root),
        "scratch_only": True,
        "providers_used": False,
        "provider_off": provider_off,
        "result": "failed",
    }
    try:
        audit["stage"] = _run_stage(project_root)
        audit["result"] = "passed"
    except Exception as exc:
        audit["failure"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        _write_no_clobber_json(audit_output, audit)
        unreal.log_error(
            "RED_M07_TROPICAL_PLANETARY_BIOME_STAGE_FAILED "
            f"audit={audit_output} error={exc}"
        )
        raise

    _write_no_clobber_json(audit_output, audit)
    unreal.log(
        "RED_M07_TROPICAL_PLANETARY_BIOME_STAGE_READY "
        f"map={DESTINATION_MAP} "
        f"actors={audit['stage']['cluster']['actor_count']} "
        f"region={REGION_INDEX} "
        "collision=disabled snap=pending water=unapplied clouds=unapplied "
        f"audit={audit_output}"
    )


if __name__ == "__main__":
    main()
