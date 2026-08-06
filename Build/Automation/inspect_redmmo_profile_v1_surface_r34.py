"""Read-only R34 inspection of the active ProfileV1 surface material instance."""

from __future__ import annotations

import hashlib
import json
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
PROJECT_FILE = PROJECT / "RedMMO.uproject"
HOME_FILE = PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
PROFILE_FILE = PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
SURFACE_FILE = PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\MI_PPG_ProfileV1_Surface.uasset"
PARENT_FILE = PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\M_PPG_ProfileV1_SurfaceParent.uasset"

EXPECTED = {
    HOME_FILE: "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3",
    PROFILE_FILE: "D226215C7367808F4A2E3225A0C9CBD7F4F32E803ABEFD22CA39062CD5538970",
    SURFACE_FILE: "FBB3A58782DEED69D93BB2369387873FA2DA7FEAA93F47CBA289FC61EBEFBD66",
    PARENT_FILE: "5B433BA09CCBB50EFC71A9F2C9100BF264274249A1B4AC2BE5E95126F4644768",
}

ROOT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1"
PLANET = ROOT + "/DA_PPG_ProfileV1_PlanetData"
SURFACE = ROOT + "/MI_PPG_ProfileV1_Surface"
PARENT = ROOT + "/M_PPG_ProfileV1_SurfaceParent"

OUT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_ProfileSurface_R34_20260805T1350Z\surface_parameters.json")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def asset_path(value):
    if value is None:
        return None
    path = value.get_path_name().split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def dirty_packages():
    values = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    values += list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted({asset_path(value) for value in values})


def now():
    return datetime.now(timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def write_once(payload):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    with OUT.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


_EXIT = {"handle": None}


def schedule_exit(delay=2.0):
    started = time.monotonic()

    def tick(_delta):
        if time.monotonic() - started < delay:
            return
        handle = _EXIT.get("handle")
        if handle is not None:
            try:
                unreal.unregister_slate_post_tick_callback(handle)
            except Exception:
                pass
            _EXIT["handle"] = None
        unreal.SystemLibrary.quit_editor()

    _EXIT["handle"] = unreal.register_slate_post_tick_callback(tick)


def main():
    report = {
        "schema": "redmmo.profile_v1.surface_parameters.read_only.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "editor_automation_read_only",
    }
    try:
        active = os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path())))
        expected_project = os.path.normcase(os.path.abspath(str(PROJECT_FILE)))
        require(active == expected_project, "Active project mismatch")
        require(not OUT.exists(), "Output no-clobber failed")
        require(not dirty_packages(), "Dirty packages before inspection")
        for path, expected_hash in EXPECTED.items():
            require(path.is_file() and sha256(path) == expected_hash, "Package hash drift: " + str(path))

        planet = unreal.EditorAssetLibrary.load_asset(PLANET)
        surface = unreal.EditorAssetLibrary.load_asset(SURFACE)
        parent = unreal.EditorAssetLibrary.load_asset(PARENT)
        require(planet is not None and surface is not None and parent is not None, "Profile surface closure missing")
        require(asset_path(planet.get_editor_property("planet_material")) == SURFACE, "PlanetData surface binding drift")
        require(asset_path(surface.get_editor_property("parent")) == PARENT, "Surface parent drift")

        editing = unreal.MaterialEditingLibrary
        scalars = {}
        for raw_name in sorted(editing.get_scalar_parameter_names(surface), key=str):
            name = str(raw_name)
            scalars[name] = {
                "value": float(editing.get_material_instance_scalar_parameter_value(surface, raw_name)),
                "overridden": bool(editing.is_material_instance_parameter_overridden(surface, raw_name)),
            }
        vectors = {}
        for raw_name in sorted(editing.get_vector_parameter_names(surface), key=str):
            name = str(raw_name)
            value = editing.get_material_instance_vector_parameter_value(surface, raw_name)
            vectors[name] = {
                "value": [float(value.r), float(value.g), float(value.b), float(value.a)],
                "overridden": bool(editing.is_material_instance_parameter_overridden(surface, raw_name)),
            }
        textures = {}
        for raw_name in sorted(editing.get_texture_parameter_names(surface), key=str):
            name = str(raw_name)
            value = editing.get_material_instance_texture_parameter_value(surface, raw_name)
            textures[name] = {
                "value": asset_path(value),
                "overridden": bool(editing.is_material_instance_parameter_overridden(surface, raw_name)),
            }
        switches = {}
        for raw_name in sorted(editing.get_static_switch_parameter_names(surface), key=str):
            name = str(raw_name)
            switches[name] = {
                "value": bool(editing.get_material_instance_static_switch_parameter_value(surface, raw_name)),
                "overridden": bool(editing.is_material_instance_parameter_overridden(surface, raw_name)),
            }

        report.update({
            "status": "PASS_READ_ONLY",
            "planet_material": asset_path(planet.get_editor_property("planet_material")),
            "surface_parent": asset_path(surface.get_editor_property("parent")),
            "scalars": scalars,
            "vectors": vectors,
            "textures": textures,
            "switches": switches,
            "dirty_packages_after": dirty_packages(),
            "save_called": False,
            "hashes_before_after": {str(path): sha256(path) for path in EXPECTED},
        })
        require(not report["dirty_packages_after"], "Inspection dirtied packages")
        for path, expected_hash in EXPECTED.items():
            require(sha256(path) == expected_hash, "Inspection changed package: " + str(path))
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        report["completed_utc"] = now()
        write_once(report)
        unreal.log("REDMMO_PROFILE_SURFACE_R34 " + report["status"])
        schedule_exit()


main()
