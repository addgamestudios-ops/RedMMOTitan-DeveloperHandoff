"""Fresh-process no-save reload and MapCheck for the R25 land PlayerStart."""

from __future__ import annotations

import hashlib
import json
import os
import re
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
R25_RESULT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1R24LandPlayerStart_R25_20260805T1150Z\result.json")

EXPECTED_HOME_SHA = "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3"
EXPECTED_PROFILE_SHA = "5C50D50A8955C1E5F4270BDD4E53D1214C941725157B76422CD72B748978B837"
EXPECTED_R25_SHA = "FD2FC0FBCCE02BCF4CFF7236835BCD330A85E2A44B641E36E6FDB5E8747CEBAF"
EXPECTED_START = (191298068.87328622, 196950130.75085244, -421017596.52606624)
EXPECTED_START_ROTATION = (0.0, -5.282776832580566, 0.0)
EXPECTED_LABEL_RELATIVE_LOCATION = (-176.14661082754293, 194.88393431659483, 23.27325318406838)
EXPECTED_LABEL_RELATIVE_ROTATION = (-27.99034882719883, -29.396086596022894, 4.179246447900821)
EXPECTED_LABEL_RELATIVE_SCALE = (1.0, 1.0, 1.0)
EXPECTED_PLANET_DATA = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
EXPECTED_GAME_MODE = "/Game/RedMMO/Gameplay/Trooper/A01/Player/GM_RedTrooperPPG_A01"

DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1R25LandPlayerStartReload_R26_20260805T1200Z")
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
    state = {}
    for port in (11111, 5353, 8000, 8765):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            state[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    require(all(state.values()), "Provider/MCP listener unexpectedly active: " + repr(state))
    return state


def asset_path(value):
    if value is None:
        return None
    path = str(value.get_path_name()).split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    path = path.rsplit(".", 1)[0] if "." in leaf else path
    return path[:-2] if path.endswith("_C") else path


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


def command_log():
    command = str(unreal.SystemLibrary.get_command_line())
    match = re.search(r'(?i)-abslog=(?:"([^"]+)"|(\S+))', command)
    require(match, "Dedicated -AbsLog argument missing")
    return match.group(1) or match.group(2)


def map_check(world):
    path = command_log()
    require(os.path.isfile(path), "MapCheck log missing")
    offset = os.path.getsize(path)
    unreal.SystemLibrary.execute_console_command(world, "MAP CHECKDEP NOCLEARLOG")
    pattern = re.compile(r"MapCheck: Map check complete: (\d+) Error\(s\), (\d+) Warning\(s\)")
    matches = []
    for _ in range(180):
        time.sleep(0.1)
        with open(path, "rb") as stream:
            stream.seek(min(offset, os.path.getsize(path)))
            matches = pattern.findall(stream.read().decode("utf-8", errors="replace"))
        if matches:
            break
    require(matches, "No fresh authoritative MapCheck completion marker")
    errors, warnings = (int(value) for value in matches[-1])
    require(errors == 0 and warnings == 0, "MapCheck failed: %d errors, %d warnings" % (errors, warnings))
    return {"errors": errors, "warnings": warnings, "log": path, "offset": offset}


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
        "schema": "redmmo.ppg_profile_v1.r25_land_playerstart.reload_mapcheck.r26.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "automation",
    }
    try:
        active = os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path())))
        require(active == os.path.normcase(os.path.abspath(str(PROJECT))), "Wrong active project")
        require(not RESULT.exists(), "R26 result no-clobber failed")
        require(HOME_FILE.is_file() and sha256(HOME_FILE) == EXPECTED_HOME_SHA, "R25 home-map hash drift")
        require(PROFILE_FILE.is_file() and sha256(PROFILE_FILE) == EXPECTED_PROFILE_SHA, "ProfileV1 drift")
        require(R25_RESULT.is_file() and sha256(R25_RESULT) == EXPECTED_R25_SHA, "R25 result drift")
        require(dirty_packages() == {"content": [], "maps": []}, "Fresh process started dirty")
        report["provider_gate_before"] = provider_gate()
        for path, expected in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected, "Protected package drift: " + str(path))

        level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        require(not level.is_in_play_in_editor(), "PIE is active")
        world = unreal.EditorLevelLibrary.get_editor_world()
        require(world is not None, "Editor world missing")
        world_path = world.get_path_name().split(":", 1)[0].split(".", 1)[0]
        require(world_path == HOME_MAP, "Wrong fresh map: " + world_path)

        actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
        starts = [actor for actor in actors if actor.get_class().get_name() == "PlayerStart"]
        spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        require(len(actors) == 12, "Home actor count drift: " + str(len(actors)))
        require(len(starts) == 1 and len(spawners) == 1, "Expected one PlayerStart and one PPG spawner")
        start = starts[0]
        require(close_vec(vec(start.get_actor_location()), EXPECTED_START), "Persisted PlayerStart location drift")
        require(close_vec(rot(start.get_actor_rotation()), EXPECTED_START_ROTATION, 0.001), "PlayerStart rotation drift")
        require(close_vec(vec(start.get_actor_scale3d()), (1.0, 1.0, 1.0), 0.001), "PlayerStart scale drift")

        attached = [actor for actor in actors if actor.get_attach_parent_actor() == start]
        require(len(attached) == 1 and attached[0].get_class().get_name() == "TextRenderActor", "Attached label identity drift")
        label_root = attached[0].get_editor_property("root_component")
        require(label_root is not None, "Attached label root missing")
        require(close_vec(vec(label_root.get_editor_property("relative_location")), EXPECTED_LABEL_RELATIVE_LOCATION), "Label relative location drift")
        require(close_vec(rot(label_root.get_editor_property("relative_rotation")), EXPECTED_LABEL_RELATIVE_ROTATION, 0.001), "Label relative rotation drift")
        require(close_vec(vec(label_root.get_editor_property("relative_scale3d")), EXPECTED_LABEL_RELATIVE_SCALE, 0.001), "Label relative scale drift")

        spawner = spawners[0]
        require(asset_path(spawner.get_editor_property("planet_data")) == EXPECTED_PLANET_DATA, "ProfileV1 map binding drift")
        require(int(spawner.get_editor_property("max_foliage_instances_per_chunk")) == 100000, "Foliage cap drift")
        require(asset_path(world.get_world_settings().get_editor_property("default_game_mode")) == EXPECTED_GAME_MODE, "A01 GameMode drift")
        planet = unreal.EditorAssetLibrary.load_asset(EXPECTED_PLANET_DATA)
        require(planet is not None and planet.get_class().get_name() == "PlanetData", "ProfileV1 PlanetData missing")
        require(int(planet.get_editor_property("generation_seed")) == 1337, "ProfileV1 seed drift")
        require(abs(float(planet.get_editor_property("planet_radius")) - 300000000.0) <= 0.01, "Planet radius drift")
        require(bool(planet.get_editor_property("generate_water")), "Native PPG water disabled")

        check = map_check(world)
        require(dirty_packages() == {"content": [], "maps": []}, "MapCheck dirtied packages")
        require(sha256(HOME_FILE) == EXPECTED_HOME_SHA, "Fresh reload/MapCheck changed home-map bytes")
        require(sha256(PROFILE_FILE) == EXPECTED_PROFILE_SHA, "Fresh reload/MapCheck changed ProfileV1")
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "Protected package changed: " + str(path))

        report.update({
            "status": "PASS_R26_R25_LAND_PLAYERSTART_FRESH_RELOAD_MAPCHECK_NO_SAVE",
            "map": HOME_MAP,
            "map_sha256_before_after": EXPECTED_HOME_SHA,
            "actor_count": len(actors),
            "actor_inventory": sorted(
                ({"path": actor.get_path_name(), "class": actor.get_class().get_name()} for actor in actors),
                key=lambda item: item["path"],
            ),
            "playerstart_location": vec(start.get_actor_location()),
            "playerstart_rotation": rot(start.get_actor_rotation()),
            "attached_label": attached[0].get_path_name(),
            "attached_label_relative_location": vec(label_root.get_editor_property("relative_location")),
            "attached_label_relative_rotation": rot(label_root.get_editor_property("relative_rotation")),
            "attached_label_relative_scale": vec(label_root.get_editor_property("relative_scale3d")),
            "planet_data": EXPECTED_PLANET_DATA,
            "generation_seed": 1337,
            "planet_radius_cm": 300000000.0,
            "max_foliage_instances_per_chunk": 100000,
            "native_water_preserved": True,
            "a01_game_mode": EXPECTED_GAME_MODE,
            "map_check": check,
            "dirty_packages_after": dirty_packages(),
            "save_called": False,
            "pie_started": False,
            "explicit_regeneration_called": False,
            "provider_gate_after": provider_gate(),
            "completed_utc": now(),
            "claim_limit": (
                "Fresh reload and MapCheck only. Runtime spawn grounding, visible grass, surface day/night, "
                "broader gameplay, standalone, replication, multiplayer and player approval remain pending."
            ),
            "next_safe_action": (
                "Run one bounded provider-off real-D3D12 PIE at the exact verified saved start. Require generation "
                "complete, grounded Trooper movement, above-water player view and visible approved grass before "
                "separate matched surface-day/night visual review."
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
        unreal.log("REDMMO_R26_R25_LAND_PLAYERSTART_RELOAD " + report["status"])
        schedule_exit()


main()
