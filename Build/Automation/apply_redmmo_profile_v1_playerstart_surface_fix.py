"""Move only the clean-RedMMO home PlayerStart onto the proven ProfileV1 surface.

The previous persisted PlayerStart is 3.208 km above the generated ProfileV1
surface. PPG chooses close foliage/detail LODs from the initial player position,
so the later GameMode surface snap occurs after the relevant generation pass.
This transaction preserves the PlayerStart radial direction and rotation, creates
an exact map rollback first, changes no other actor, and never calls generation.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject")
HOME_MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
HOME_FILE = PROJECT.parent / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
EXPECTED_HOME = "F2B3EC00BE7D858FE4F7CDC2C611D8E0C9741344CCE48D7A4293D5300FD7AF9D"
EXPECTED_START = (-199124123.19739443, 16609013.409565615, -523874079.53368956)
TARGET_START = (-198911217.22968367, 16591254.847640004, -523634710.60749865)
PLANET_CENTER = (0.0, 0.0, -300000000.0)

ROLLBACK = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeRedPPGProfileV1PlayerStartSurface_20260805T0658Z")
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1PlayerStartSurface_R03_20260805T0658Z")
RESULT = DIAG / "result.json"

PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
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


def write_json_exclusive(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def provider_gate():
    result = {}
    for port in (5353, 8000, 8765, 11111):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            result[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    require(all(result.values()), "Provider/MCP listener unexpectedly active: " + repr(result))
    return result


def asset_path(value):
    if value is None:
        return None
    path = value.get_path_name().split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def dirty_packages():
    content = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    maps = list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return {
        "content": sorted({asset_path(value) for value in content}),
        "maps": sorted({asset_path(value) for value in maps}),
    }


def vec(value):
    return [float(value.x), float(value.y), float(value.z)]


def close_vec(actual, expected, tolerance=0.5):
    return all(abs(float(actual[index]) - float(expected[index])) <= tolerance for index in range(3))


def actor_snapshot(actor):
    location = actor.get_actor_location()
    rotation = actor.get_actor_rotation()
    scale = actor.get_actor_scale3d()
    parent = actor.get_attach_parent_actor()
    root = actor.get_editor_property("root_component")
    relative_location = root.get_editor_property("relative_location") if root is not None else location
    relative_rotation = root.get_editor_property("relative_rotation") if root is not None else rotation
    relative_scale = root.get_editor_property("relative_scale3d") if root is not None else scale
    return {
        "path": actor.get_path_name(),
        "class": actor.get_class().get_name(),
        "location": vec(location),
        "rotation": [float(rotation.pitch), float(rotation.yaw), float(rotation.roll)],
        "scale": vec(scale),
        "attach_parent": parent.get_path_name() if parent is not None else None,
        "relative_location": vec(relative_location),
        "relative_rotation": [
            float(relative_rotation.pitch), float(relative_rotation.yaw), float(relative_rotation.roll)
        ],
        "relative_scale": vec(relative_scale),
    }


def radius(point):
    dx = point[0] - PLANET_CENTER[0]
    dy = point[1] - PLANET_CENTER[1]
    dz = point[2] - PLANET_CENTER[2]
    return (dx * dx + dy * dy + dz * dz) ** 0.5


_EXIT = {"handle": None}


def schedule_exit(delay=6.0):
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
        "schema": "redmmo.ppg_profile_v1.playerstart_surface_fix.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "automation",
    }
    try:
        active_project = os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path())))
        require(active_project == os.path.normcase(os.path.abspath(str(PROJECT))), "Wrong active project")
        require(not RESULT.exists(), "Result no-clobber failed")
        require(HOME_FILE.is_file() and sha256(HOME_FILE) == EXPECTED_HOME, "Home map preimage hash drift")
        require(dirty_packages() == {"content": [], "maps": []}, "Editor is not clean")
        report["provider_gate"] = provider_gate()
        for path, expected in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected, "Protected package hash drift: " + str(path))

        rollback_map = ROLLBACK / "RedMMO_PPG_HomeWorld.pre_playerstart_surface.umap"
        if not ROLLBACK.exists():
            ROLLBACK.mkdir(parents=True, exist_ok=False)
            shutil.copy2(HOME_FILE, rollback_map)
            require(sha256(rollback_map) == EXPECTED_HOME, "Rollback map copy mismatch")
            write_json_exclusive(ROLLBACK / "manifest.json", {
                "schema": "redmmo.ppg_profile_v1.playerstart_surface_fix.rollback.v1",
                "captured_utc": now(),
                "source": str(HOME_FILE),
                "sha256": EXPECTED_HOME,
                "rollback": str(rollback_map),
                "restore": "Close Unreal and copy the retained rollback umap over only the clean RedMMO home map.",
            })
        require(rollback_map.is_file() and sha256(rollback_map) == EXPECTED_HOME,
                "Retained rollback map mismatch")

        world = unreal.EditorLoadingAndSavingUtils.load_map(HOME_MAP)
        require(world is not None and dirty_packages() == {"content": [], "maps": []}, "Home map load failed or dirtied packages")
        actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
        starts = [actor for actor in actors if actor.get_class().get_name() == "PlayerStart"]
        require(len(starts) == 1, "Expected exactly one PlayerStart")
        starts[0].modify()
        before = vec(starts[0].get_actor_location())
        require(close_vec(before, EXPECTED_START), "PlayerStart preimage location drift: " + repr(before))
        rotation_before = actor_snapshot(starts[0])["rotation"]
        other_before = [actor_snapshot(actor) for actor in actors if actor != starts[0]]

        target = unreal.Vector(*TARGET_START)
        require(starts[0].set_actor_location(target, False, False) is not False, "PlayerStart relocation failed")
        after_transient = vec(starts[0].get_actor_location())
        require(close_vec(after_transient, TARGET_START), "PlayerStart transient readback mismatch")
        require(actor_snapshot(starts[0])["rotation"] == rotation_before, "PlayerStart rotation changed")
        other_after = [actor_snapshot(actor) for actor in actors if actor != starts[0]]
        non_playerstart_differences = [
            {"before": before_item, "after": after_item}
            for before_item, after_item in zip(other_before, other_after)
            if before_item != after_item
        ]
        report["non_playerstart_differences_before_save"] = non_playerstart_differences
        start_path = starts[0].get_path_name()
        require(all(
            item["before"]["class"] == "TextRenderActor"
            and item["before"]["attach_parent"] == start_path
            and item["after"]["attach_parent"] == start_path
            and item["before"]["relative_location"] == item["after"]["relative_location"]
            and item["before"]["relative_rotation"] == item["after"]["relative_rotation"]
            and item["before"]["relative_scale"] == item["after"]["relative_scale"]
            for item in non_playerstart_differences
        ), "Unexpected non-PlayerStart actor change")
        require(dirty_packages()["content"] == [] and dirty_packages()["maps"] == [HOME_MAP], "Unexpected dirty package set")
        require(unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level(), "Home map save failed")
        require(dirty_packages() == {"content": [], "maps": []}, "Dirty packages remained after save")

        after = vec(starts[0].get_actor_location())
        require(close_vec(after, TARGET_START), "Saved PlayerStart readback mismatch")
        new_hash = sha256(HOME_FILE)
        require(new_hash != EXPECTED_HOME, "Home map hash did not change")
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "Protected package changed: " + str(path))

        report.update({
            "status": "PASS_PLAYERSTART_ON_PROFILE_V1_SURFACE_PENDING_FRESH_PIE",
            "home_map": HOME_MAP,
            "home_map_sha256_before": EXPECTED_HOME,
            "home_map_sha256_after": new_hash,
            "playerstart_before": before,
            "playerstart_after": after,
            "radial_height_reduction_cm": radius(before) - radius(after),
            "playerstart_rotation_preserved": True,
            "non_playerstart_actors_preserved": len(other_before),
            "attached_playerstart_labels_moved_with_parent": len(non_playerstart_differences),
            "rollback": str(rollback_map),
            "generation_called": False,
            "pie_started": False,
            "dirty_packages_after": dirty_packages(),
            "next_safe_action": "Fresh reload/MapCheck and one real-D3D12 PIE run; require approved grass components and visible player-scale grass before acceptance.",
        })
    except Exception as error:
        report["status"] = "FAIL"
        report["error"] = str(error)
        report["traceback"] = traceback.format_exc()
        report["home_map_sha256_observed"] = sha256(HOME_FILE) if HOME_FILE.is_file() else None
    finally:
        report["completed_utc"] = now()
        write_json_exclusive(RESULT, report)
        unreal.log("REDMMO_PROFILE_V1_PLAYERSTART_SURFACE_FIX " + report["status"])
        schedule_exit()


main()
