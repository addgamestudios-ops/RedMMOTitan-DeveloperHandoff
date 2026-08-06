"""Remove only the rejected R06 square water carrier from clean RedMMO.

This transaction deliberately does not add replacement water. A seeded PPG
water/basin binding may be added only after its public capability is proven.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
HOME_MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
HOME_FILE = PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
EXPECTED_HOME = "C9BE88085575E75E1790CB9306D564EB100F5ED2E75E012C1FD09EA110FDDFE0"
R06_LABEL = "RedMMO_StylizedPilot_OasisWater_R06"
EXPECTED_MESH = "/Engine/BasicShapes/Plane"
EXPECTED_MATERIAL = "/Game/StylizedDesertOasis/Materials/Instances/Environment/MI_Water"
EXPECTED_SCALE = (90.0, 60.0, 1.0)

DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_R16A_RemoveRejectedWaterPlane_20260803_003500")
RESULT = DIAG / "remove_redmmo_r06_water_plane_r16a_result.json"
CHECKPOINT = Path(r"D:\RedMMOTitanWindowsData\Rollback\RedMMO_R16_SeededWaterAudioVehicle_20260803_003500_A01\manifest.json")

PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"): "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"): "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap"): "211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7",
    Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeCoastDatum_20260714\RedPlanetGen_50km_FusedPrototype.umap"): "A9C42C0D1B0429DD1018F00F0D2AB8A18F66C07291611964EFF5F9710F3B0C6A",
}

UNCHANGED_PROJECT_ASSETS = {
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10O\DA_PPG_HomeWorld_StylizedBinding_R10O.uasset": "7C6835CA50EBB06B4C94AA6D1E8B0419B1E0ACF09A44D5CEA5B670FBD5865C5A",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10O\Profiles\DA_PPG_HomeWorld_StylizedForest_R10O.uasset": "4D7B577684CF74CBF56BCB6AF8A6867DAD130C8BACF022CF461D86A53833E18F",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\M_PPG_Generation_SmoothSpawnGrass_R10N.uasset": "43EA98C552B42A28C90C588A588E6B30C9C63ABE02E1E99D744D02E6D65A1FD0",
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def asset_path(value):
    if value is None:
        return None
    getter = getattr(value, "get_path_name", None)
    if not callable(getter):
        return str(value)
    path = getter().split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def dirty_packages():
    values = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    values += list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted(set(asset_path(value) for value in values))


def provider_gate():
    records = []
    for port in (5353, 8000, 8765):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.25)
        try:
            code = sock.connect_ex(("127.0.0.1", port))
        finally:
            sock.close()
        records.append({"port": port, "closed": code != 0, "connect_ex": code})
    require(all(item["closed"] for item in records), "AI/provider listener active")
    return records


def actor_signature(actor):
    return (actor.get_actor_label(), actor.get_class().get_name())


def verify_checkpoint():
    require(CHECKPOINT.is_file(), "Checkpoint manifest missing")
    manifest = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    expected = next(item for item in manifest["files"] if item["path"].endswith("RedMMO_PPG_HomeWorld.umap"))
    copy_path = CHECKPOINT.parent / expected["path"]
    require(copy_path.is_file(), "Checkpoint map copy missing")
    require(sha256(copy_path) == EXPECTED_HOME == expected["sha256"], "Checkpoint map hash mismatch")
    return str(CHECKPOINT)


_EXIT = {"handle": None}


def schedule_exit(delay=8.0):
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
        "schema": "redmmo.r16a.remove_rejected_water_plane.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "direct_interface": "single guarded Unreal Python editor transaction",
        "strict_scope": {
            "removed_actor_only": R06_LABEL,
            "replacement_water_added": False,
            "manual_placement_added": False,
            "ppg_seed_or_markers_changed": False,
        },
    }
    try:
        require(not RESULT.exists(), "No-clobber result already exists")
        require(sha256(HOME_FILE) == EXPECTED_HOME, "Home map preimage drift")
        report["checkpoint"] = verify_checkpoint()
        report["provider_gate"] = provider_gate()
        for path, expected in {**PROTECTED, **UNCHANGED_PROJECT_ASSETS}.items():
            require(path.is_file() and sha256(path) == expected, "Protected/source hash drift: " + str(path))

        world = unreal.EditorLoadingAndSavingUtils.load_map(HOME_MAP)
        require(world is not None, "Home map load failed")
        require(not dirty_packages(), "Map load dirtied packages")
        subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actors_before = list(subsystem.get_all_level_actors())
        signatures_before = Counter(actor_signature(actor) for actor in actors_before)
        matches = [actor for actor in actors_before if actor.get_actor_label() == R06_LABEL]
        require(len(matches) == 1, "Expected exactly one R06 water actor")
        actor = matches[0]
        require(actor.get_class().get_name() == "StaticMeshActor", "R06 actor class drift")
        component = actor.get_component_by_class(unreal.StaticMeshComponent)
        require(component is not None, "R06 StaticMeshComponent missing")
        require(asset_path(component.get_editor_property("static_mesh")) == EXPECTED_MESH, "R06 mesh drift")
        require(asset_path(component.get_material(0)) == EXPECTED_MATERIAL, "R06 material drift")
        scale = actor.get_actor_scale3d()
        scale_tuple = (float(scale.x), float(scale.y), float(scale.z))
        require(all(abs(a - b) <= 0.001 for a, b in zip(scale_tuple, EXPECTED_SCALE)), "R06 scale drift")
        require(not actor.get_actor_enable_collision(), "R06 actor collision unexpectedly enabled")
        removed_signature = actor_signature(actor)

        removed_record = {
            "label": R06_LABEL,
            "class": actor.get_class().get_name(),
            "mesh": EXPECTED_MESH,
            "material": EXPECTED_MATERIAL,
            "scale": list(scale_tuple),
        }
        require(subsystem.destroy_actor(actor), "Could not destroy exact R06 water actor")
        require(set(dirty_packages()).issubset({HOME_MAP}), "Unexpected dirty package before save: " + str(dirty_packages()))
        require(unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level(), "Home-map save failed")
        require(not dirty_packages(), "Dirty packages remain after save")

        actors_after = list(subsystem.get_all_level_actors())
        signatures_after = Counter(actor_signature(item) for item in actors_after)
        expected_after = signatures_before.copy()
        expected_after.subtract([removed_signature])
        expected_after += Counter()
        require(signatures_after == expected_after, "Actor signature drift beyond exact R06 removal")
        require(not any(item.get_actor_label() == R06_LABEL for item in actors_after), "R06 actor persisted")
        require(len(actors_after) == len(actors_before) - 1, "Actor count changed by more than one")

        for path, expected in {**PROTECTED, **UNCHANGED_PROJECT_ASSETS}.items():
            require(sha256(path) == expected, "Protected/source changed: " + str(path))
        post_hash = sha256(HOME_FILE)
        require(post_hash != EXPECTED_HOME, "Map did not serialize exact removal")
        report.update({
            "status": "PASS_REMOVED_REJECTED_PLANE_PENDING_FRESH_RELOAD_MAPCHECK",
            "home_map_sha256_before": EXPECTED_HOME,
            "home_map_sha256_after": post_hash,
            "actor_count_before": len(actors_before),
            "actor_count_after": len(actors_after),
            "removed_actor": removed_record,
            "replacement_water_added": False,
            "dirty_packages_after": dirty_packages(),
        })
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        report["completed_utc"] = now()
        DIAG.mkdir(parents=True, exist_ok=True)
        with RESULT.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        unreal.log("REDMMO_R16A_WATER_PLANE_REMOVAL " + report["status"])
        schedule_exit()


main()
