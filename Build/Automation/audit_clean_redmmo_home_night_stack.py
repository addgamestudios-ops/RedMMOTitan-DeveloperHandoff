"""Read-only inventory of the clean RedMMO home-world lighting and sky stack.

The audit loads the persisted home map in a fresh Unreal process, records only
lighting/atmosphere/post-process actors and components, verifies provider and
protected-package gates, and exits without saving.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
HOME_MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
HOME_FILE = PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
RESULT = Path(os.environ["REDMMO_NIGHT_AUDIT_RESULT"])
EXPECTED_HOME = os.environ.get("REDMMO_EXPECTED_HOME_SHA256", "").upper()
REVIEW_MAP = "/Game/RedMMO/Maps/Review/RedMMO_StarfieldTintReview"
STAR_ASSETS = (
    "/Game/RedMMO/Materials/Sky/StarfieldReview/M_Red_StarfieldTintable",
    "/Game/RedMMO/Materials/Sky/StarfieldReview/MI_Red_Starfield_Sparse_Original",
    "/Game/RedMMO/Materials/Sky/StarfieldReview/MI_Red_Starfield_Holo_Original",
    "/Game/SoStylized/Environment/Sky/Meshes/SM_StylizedSkyDome",
)

PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap"):
        "211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7",
}

KEYWORDS = (
    "sky", "sun", "moon", "star", "light", "atmosphere", "cloud",
    "fog", "postprocess", "exposure",
)

PROPERTIES = (
    "intensity", "light_color", "cast_shadows", "visible",
    "hidden_in_game", "atmosphere_sun_light",
    "atmosphere_sun_light_index", "indirect_lighting_intensity",
    "volumetric_scattering_intensity", "real_time_capture",
    "lower_hemisphere_is_solid_color", "sky_distance_threshold",
    "rayleigh_scattering_scale", "mie_scattering_scale",
    "multi_scattering_factor", "aerial_perspective_view_distance_scale",
    "transform_mode", "blend_weight", "priority", "unbound",
)


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def asset_path(value):
    getter = getattr(value, "get_path_name", None)
    return getter() if callable(getter) else str(value)


def stable(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [stable(item) for item in value]
    for method in ("to_tuple", "to_string"):
        call = getattr(value, method, None)
        if callable(call):
            try:
                return stable(call())
            except Exception:
                pass
    return asset_path(value)


def read_property(obj, name):
    try:
        return stable(obj.get_editor_property(name))
    except Exception:
        return None


def properties(obj):
    return {
        name: value for name in PROPERTIES
        if (value := read_property(obj, name)) is not None
    }


def dirty_packages():
    values = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    values += list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted({asset_path(value).split(":", 1)[0] for value in values})


def provider_gate():
    records = []
    for port in (5353, 8000, 8765):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.25)
        try:
            code = sock.connect_ex(("127.0.0.1", port))
        finally:
            sock.close()
        records.append({"port": port, "closed": code != 0})
    if not all(record["closed"] for record in records):
        raise RuntimeError("AI/provider listener active")
    return records


def actor_record(actor):
    record = {
        "label": actor.get_actor_label(),
        "class": actor.get_class().get_name(),
        "path": actor.get_path_name(),
        "location": stable(actor.get_actor_location()),
        "rotation": stable(actor.get_actor_rotation()),
        "hidden": bool(actor.is_hidden_ed()),
        "properties": properties(actor),
        "components": [],
    }
    for component in actor.get_components_by_class(unreal.ActorComponent):
        component_class = component.get_class().get_name()
        component_name = component.get_name()
        joined = (component_class + " " + component_name).lower()
        if any(keyword in joined for keyword in KEYWORDS):
            record["components"].append({
                "name": component_name,
                "class": component_class,
                "path": component.get_path_name(),
                "properties": properties(component),
            })
    return record


def material_parameters(material):
    result = {}
    library = unreal.MaterialEditingLibrary
    for kind in ("scalar", "vector", "texture", "static_switch"):
        call = getattr(library, "get_{}_parameter_names".format(kind), None)
        if not callable(call):
            continue
        try:
            result[kind] = [str(value) for value in call(material)]
        except Exception as exc:
            result[kind + "_error"] = str(exc)
    return result


def star_asset_record(path):
    asset = unreal.EditorAssetLibrary.load_asset(path)
    if asset is None:
        return {"path": path, "loaded": False}
    record = {
        "path": path,
        "loaded": True,
        "class": asset.get_class().get_name(),
        "properties": {},
    }
    for name in (
        "parent", "material_domain", "blend_mode", "two_sided", "is_sky",
        "shading_model", "allow_negative_emissive_color",
    ):
        value = read_property(asset, name)
        if value is not None:
            record["properties"][name] = value
    if isinstance(asset, unreal.MaterialInterface):
        record["parameters"] = material_parameters(asset)
    return record


def review_actor_record(actor):
    record = {
        "label": actor.get_actor_label(),
        "class": actor.get_class().get_name(),
        "location": stable(actor.get_actor_location()),
        "scale": stable(actor.get_actor_scale3d()),
        "mesh_components": [],
    }
    for component in actor.get_components_by_class(unreal.StaticMeshComponent):
        mesh = read_property(component, "static_mesh")
        materials = []
        try:
            materials = [asset_path(value) for value in component.get_materials()]
        except Exception:
            pass
        record["mesh_components"].append({
            "name": component.get_name(),
            "mesh": mesh,
            "materials": materials,
        })
    return record


_EXIT = {"handle": None}


def schedule_exit(delay=5.0):
    started = time.monotonic()

    def tick(_delta):
        if time.monotonic() - started < delay:
            return
        handle = _EXIT.get("handle")
        if handle is not None:
            unreal.unregister_slate_post_tick_callback(handle)
            _EXIT["handle"] = None
        unreal.SystemLibrary.quit_editor()

    _EXIT["handle"] = unreal.register_slate_post_tick_callback(tick)


def main():
    report = {
        "schema": "redmmo.home.night_stack.audit.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "static_runtime_read_only",
    }
    try:
        if RESULT.exists():
            raise RuntimeError("No-clobber result exists: " + str(RESULT))
        if EXPECTED_HOME and sha256(HOME_FILE) != EXPECTED_HOME:
            raise RuntimeError("Home-map hash drift")
        report["provider_gate"] = provider_gate()
        report["protected_hashes"] = {}
        for path, expected in PROTECTED.items():
            actual = sha256(path)
            if actual != expected:
                raise RuntimeError("Protected hash drift: " + str(path))
            report["protected_hashes"][str(path)] = actual
        world = unreal.EditorLoadingAndSavingUtils.load_map(HOME_MAP)
        if world is None:
            raise RuntimeError("Home map failed to load")
        if dirty_packages():
            raise RuntimeError("Fresh load dirtied packages")
        actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
        records = []
        for actor in actors:
            joined = (actor.get_actor_label() + " " + actor.get_class().get_name()).lower()
            record = actor_record(actor)
            if any(keyword in joined for keyword in KEYWORDS) or record["components"]:
                records.append(record)
        report.update({
            "status": "PASS_READ_ONLY_NIGHT_STACK_AUDIT",
            "home_map_sha256": sha256(HOME_FILE),
            "actor_count": len(actors),
            "night_stack_actor_count": len(records),
            "night_stack": records,
            "dirty_packages": dirty_packages(),
            "map_saved": False,
        })
        report["star_assets"] = [star_asset_record(path) for path in STAR_ASSETS]
        review_world = unreal.EditorLoadingAndSavingUtils.load_map(REVIEW_MAP)
        if review_world is None:
            raise RuntimeError("Starfield review map failed to load")
        review_actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
        report["starfield_review"] = {
            "map": REVIEW_MAP,
            "actor_count": len(review_actors),
            "actors": [review_actor_record(actor) for actor in review_actors],
        }
        if dirty_packages():
            raise RuntimeError("Starfield review audit dirtied packages")
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        report["completed_utc"] = now()
        RESULT.parent.mkdir(parents=True, exist_ok=True)
        with RESULT.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        unreal.log("REDMMO_NIGHT_STACK_AUDIT " + report["status"])
        schedule_exit()


main()
