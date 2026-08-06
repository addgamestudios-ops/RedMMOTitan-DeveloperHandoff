"""Persist only the R24-proven seeded land PlayerStart in clean RedMMO.

R24C proved that the existing Trooper capsule can be swept to the selected
native generated-terrain contact and settle grounded without terrain overlap.
This transaction does not run PIE or regenerate PPG. It retains an exact map
preimage, moves only the unique PlayerStart, lets its existing attached label
follow without changing its relative transform, and saves only the home map.
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
PROFILE_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
R24_RESULT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1SweptGrounding_R24C_20260805T1145Z\result.json")

EXPECTED_HOME_SHA = "6B45B423ED59BD8906A05CF35E7349C70282154DE2CE4723D41E0C16380F88D9"
EXPECTED_PROFILE_SHA = "5C50D50A8955C1E5F4270BDD4E53D1214C941725157B76422CD72B748978B837"
EXPECTED_R24_SHA = "B1B4B00C5F177B9EF4020172BD88FA1C794D762597DE44603F0F10F63F806B32"
EXPECTED_START = (-198911217.22968367, 16591254.847640004, -523634710.60749865)
EXPECTED_TARGET = (191298068.8732862, 196950130.75085244, -421017596.52606624)

ROLLBACK = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeRedPPGProfileV1R24LandPlayerStart_R25_20260805T1150Z")
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1R24LandPlayerStart_R25_20260805T1150Z")
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
    data = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def provider_gate():
    result = {}
    for port in (11111, 5353, 8000, 8765):
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
    return {
        "content": sorted({asset_path(value) for value in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}),
        "maps": sorted({asset_path(value) for value in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()}),
    }


def vec(value):
    return [float(value.x), float(value.y), float(value.z)]


def rot(value):
    return [float(value.pitch), float(value.yaw), float(value.roll)]


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
        "rotation": rot(rotation),
        "scale": vec(scale),
        "attach_parent": parent.get_path_name() if parent is not None else None,
        "relative_location": vec(relative_location),
        "relative_rotation": rot(relative_rotation),
        "relative_scale": vec(relative_scale),
    }


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
        "schema": "redmmo.ppg_profile_v1.r24_land_playerstart.r25.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "automation",
    }
    try:
        active_project = os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path())))
        require(active_project == os.path.normcase(os.path.abspath(str(PROJECT))), "Wrong active project")
        require(not RESULT.exists(), "R25 result no-clobber failed")
        require(not ROLLBACK.exists(), "R25 rollback no-clobber failed")
        require(HOME_FILE.is_file() and sha256(HOME_FILE) == EXPECTED_HOME_SHA, "Home map preimage drift")
        require(PROFILE_FILE.is_file() and sha256(PROFILE_FILE) == EXPECTED_PROFILE_SHA, "ProfileV1 drift")
        require(R24_RESULT.is_file() and sha256(R24_RESULT) == EXPECTED_R24_SHA, "R24 result drift")
        require(dirty_packages() == {"content": [], "maps": []}, "Editor is dirty before R25")
        report["provider_gate_before"] = provider_gate()
        for path, expected in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected, "Protected package drift: " + str(path))

        r24 = json.loads(R24_RESULT.read_text(encoding="utf-8"))
        require(r24.get("status") == "PASS_R24C_SWEPT_CAPSULE_CLEARANCE_AND_GROUNDING_NO_SAVE", "R24 did not pass")
        require(close_vec(r24["swept_placement"]["requested_center"], EXPECTED_TARGET, 0.001), "R24 target drift")
        require(r24["grounding"]["moving_on_ground"] is True, "R24 was not grounded")
        require(not r24["grounding"]["overlapping_terrain_components"], "R24 terrain overlap was nonempty")

        ROLLBACK.mkdir(parents=True, exist_ok=False)
        rollback_map = ROLLBACK / "RedMMO_PPG_HomeWorld.pre_r25_r24_land_playerstart.umap"
        shutil.copy2(HOME_FILE, rollback_map)
        require(sha256(rollback_map) == EXPECTED_HOME_SHA, "Rollback map copy mismatch")
        write_json_exclusive(ROLLBACK / "manifest.json", {
            "schema": "redmmo.ppg_profile_v1.r24_land_playerstart.r25.rollback.v1",
            "captured_utc": now(),
            "source": str(HOME_FILE),
            "sha256": EXPECTED_HOME_SHA,
            "rollback": str(rollback_map),
            "restore": "Close Unreal and copy this retained umap over only the clean RedMMO home map.",
        })

        world = unreal.EditorLoadingAndSavingUtils.load_map(HOME_MAP)
        require(world is not None, "Home map load failed")
        require(dirty_packages() == {"content": [], "maps": []}, "Home map load dirtied packages")
        actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
        starts = [actor for actor in actors if actor.get_class().get_name() == "PlayerStart"]
        require(len(starts) == 1, "Expected exactly one PlayerStart")
        start = starts[0]
        start_path = start.get_path_name()
        before_start = actor_snapshot(start)
        require(close_vec(before_start["location"], EXPECTED_START), "PlayerStart preimage drift: " + repr(before_start["location"]))
        other_before = {actor.get_path_name(): actor_snapshot(actor) for actor in actors if actor != start}

        start.modify()
        target = unreal.Vector(*EXPECTED_TARGET)
        require(start.set_actor_location(target, False, False) is not False, "PlayerStart relocation failed")
        after_transient = actor_snapshot(start)
        require(close_vec(after_transient["location"], EXPECTED_TARGET), "PlayerStart transient readback mismatch")
        require(after_transient["rotation"] == before_start["rotation"], "PlayerStart rotation changed")
        require(after_transient["scale"] == before_start["scale"], "PlayerStart scale changed")

        other_after = {actor.get_path_name(): actor_snapshot(actor) for actor in actors if actor != start}
        require(set(other_before) == set(other_after), "Non-PlayerStart actor identity set changed")
        differences = [
            {"before": other_before[path], "after": other_after[path]}
            for path in sorted(other_before)
            if other_before[path] != other_after[path]
        ]
        require(len(differences) == 1, "Expected exactly one attached PlayerStart label to follow: " + repr(differences))
        label_change = differences[0]
        require(
            label_change["before"]["class"] == "TextRenderActor"
            and label_change["before"]["attach_parent"] == start_path
            and label_change["after"]["attach_parent"] == start_path
            and label_change["before"]["relative_location"] == label_change["after"]["relative_location"]
            and label_change["before"]["relative_rotation"] == label_change["after"]["relative_rotation"]
            and label_change["before"]["relative_scale"] == label_change["after"]["relative_scale"],
            "Attached label relationship or relative transform changed",
        )
        require(dirty_packages() == {"content": [], "maps": [HOME_MAP]}, "Unexpected dirty package set before save")
        require(unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level(), "Home map save failed")
        require(dirty_packages() == {"content": [], "maps": []}, "Dirty packages remained after save")

        new_hash = sha256(HOME_FILE)
        require(new_hash != EXPECTED_HOME_SHA, "Home map hash did not change")
        require(sha256(PROFILE_FILE) == EXPECTED_PROFILE_SHA, "ProfileV1 changed during R25")
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "Protected package changed: " + str(path))

        report.update({
            "status": "PASS_R25_R24_LAND_PLAYERSTART_SAVED_PENDING_FRESH_RELOAD_MAPCHECK",
            "home_map": HOME_MAP,
            "home_map_sha256_before": EXPECTED_HOME_SHA,
            "home_map_sha256_after": new_hash,
            "profile_sha256_after": sha256(PROFILE_FILE),
            "r24_result_sha256": sha256(R24_RESULT),
            "playerstart_before": before_start,
            "playerstart_after": actor_snapshot(start),
            "attached_label_change": label_change,
            "other_actor_count_preserved": len(other_before),
            "rollback": str(rollback_map),
            "generation_called": False,
            "pie_started": False,
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "completed_utc": now(),
            "claim_limit": (
                "Saved PlayerStart plus attached-label transform only. Fresh reload, MapCheck, spawn grounding, "
                "visible approved grass, day/night, broader gameplay and player acceptance remain pending."
            ),
            "next_safe_action": (
                "In one separate fresh process, reload the exact saved home map and run MapCheck without save or PIE. "
                "Only after that passes may a provider-off D3D12 PIE prove the saved surface start."
            ),
        })
    except Exception as error:
        report.update({
            "status": "FAIL",
            "error": str(error),
            "traceback": traceback.format_exc(),
            "home_map_sha256_observed": sha256(HOME_FILE) if HOME_FILE.is_file() else None,
            "profile_sha256_observed": sha256(PROFILE_FILE) if PROFILE_FILE.is_file() else None,
            "completed_utc": now(),
        })
    finally:
        if "completed_utc" not in report:
            report["completed_utc"] = now()
        write_json_exclusive(RESULT, report)
        unreal.log("REDMMO_R25_R24_LAND_PLAYERSTART " + report["status"])
        schedule_exit()


main()
