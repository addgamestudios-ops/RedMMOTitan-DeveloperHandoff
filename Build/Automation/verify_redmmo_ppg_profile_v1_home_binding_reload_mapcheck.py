"""Fresh-process no-save reload and MapCheck for the ProfileV1 home binding."""

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


PROJECT_FILE = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject")
HOME_MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
HOME_FILE = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap")
EXPECTED_HOME = "F2B3EC00BE7D858FE4F7CDC2C611D8E0C9741344CCE48D7A4293D5300FD7AF9D"
TARGET_ROOT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1"
TARGET_PLANET = TARGET_ROOT + "/DA_PPG_ProfileV1_PlanetData"
TARGET_GENERATION = TARGET_ROOT + "/M_PPG_ProfileV1_Generation"
TARGET_MASK = TARGET_ROOT + "/M_PPG_ProfileV1_BiomeMask"
TARGET_SURFACE = TARGET_ROOT + "/MI_PPG_ProfileV1_Surface"
EXPECTED_GAME_MODE = "/Game/RedMMO/Gameplay/Trooper/A01/Player/GM_RedTrooperPPG_A01"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1HomeBindingReload_20260805_0637")
RESULT = DIAG / "verify_redmmo_ppg_profile_v1_home_binding_reload_mapcheck_result.json"

EXPECTED_FILES = {
    Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\World\PPG\HomeWorld\SeededBiomeSurface\R17\DA_PPG_HomeWorld_SeededBiomeSurface_R17.uasset"):
        "ADFC9D79B509A9998C66229CF67E65C6E560E238141BE30F22C705075C3C6C55",
    Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"):
        "5C50D50A8955C1E5F4270BDD4E53D1214C941725157B76422CD72B748978B837",
    Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\WorldAuthoring\PPG\ProfileV1\M_PPG_ProfileV1_Generation.uasset"):
        "5165A27F0423735256EEE768739CE9547FEF7849BCA05540AAD63DF5BA1D96E3",
    Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\WorldAuthoring\PPG\ProfileV1\M_PPG_ProfileV1_BiomeMask.uasset"):
        "6A4EA303452559810E4FF805FE86AD7057D9807069B3585A8CC9489279BFA66D",
    Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\WorldAuthoring\PPG\ProfileV1\M_PPG_ProfileV1_SurfaceParent.uasset"):
        "5B433BA09CCBB50EFC71A9F2C9100BF264274249A1B4AC2BE5E95126F4644768",
    Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\WorldAuthoring\PPG\ProfileV1\MI_PPG_ProfileV1_Surface.uasset"):
        "FBB3A58782DEED69D93BB2369387873FA2DA7FEAA93F47CBA289FC61EBEFBD66",
}
PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap"):
        "211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7",
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
    path = value.get_path_name().split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    if "." in leaf:
        path = path.rsplit(".", 1)[0]
    return path[:-2] if path.endswith("_C") else path


def dirty_packages():
    content = [asset_path(value) for value in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]
    maps = [asset_path(value) for value in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
    return {"content": sorted(set(content)), "maps": sorted(set(maps))}


def provider_gate():
    state = {}
    for port in (5353, 8000, 8765, 11111):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.2)
        try:
            state[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    require(all(state.values()), "Provider/MCP listener unexpectedly open")
    return state


def verify_hashes(records, label):
    actual = {}
    for path, expected in records.items():
        require(path.is_file(), label + " missing: " + str(path))
        actual[str(path)] = sha256(path)
        require(actual[str(path)] == expected, label + " drift: " + str(path))
    return actual


def command_log():
    command = str(unreal.SystemLibrary.get_command_line())
    match = re.search(r'(?i)-abslog=(?:"([^"]+)"|(\S+))', command)
    require(match, "Dedicated -abslog argument missing")
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
    require(errors == 0 and warnings == 0, f"MapCheck failed: {errors}/{warnings}")
    return {"errors": errors, "warnings": warnings, "log": path, "offset": offset}


def write_json_exclusive(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


_EXIT = {"handle": None}


def schedule_exit(delay=7.0):
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
        "schema": "redmmo.ppg_profile_v1.home_binding.reload_mapcheck.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "automation",
    }
    try:
        require(not RESULT.exists(), "Verifier result no-clobber failed")
        active = os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path())))
        expected = os.path.normcase(os.path.abspath(str(PROJECT_FILE)))
        require(active == expected, "Active project mismatch")
        level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        require(not level.is_in_play_in_editor(), "PIE is active")
        require(dirty_packages() == {"content": [], "maps": []}, "Fresh process started dirty")
        require(HOME_FILE.is_file() and sha256(HOME_FILE) == EXPECTED_HOME, "Home-map hash drift")
        tracked_before = verify_hashes(EXPECTED_FILES, "authenticated input")
        protected_before = verify_hashes(PROTECTED, "protected checkpoint")
        report["provider_ports_closed"] = provider_gate()

        world = unreal.EditorLevelLibrary.get_editor_world()
        require(world is not None, "Editor world missing")
        world_path = world.get_path_name().split(":", 1)[0].split(".", 1)[0]
        require(world_path == HOME_MAP, "Wrong startup map: " + world_path)
        actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
        require(len(actors) == 11, "Home actor count drift")
        spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        require(len(spawners) == 1, "Expected exactly one PlanetSpawnerBP_C")
        spawner = spawners[0]
        require(asset_path(spawner.get_editor_property("planet_data")) == TARGET_PLANET,
                "ProfileV1 home binding did not persist")
        require(int(spawner.get_editor_property("max_foliage_instances_per_chunk")) == 100000,
                "Foliage cap drift")
        require(asset_path(world.get_world_settings().get_editor_property("default_game_mode")) == EXPECTED_GAME_MODE,
                "A01 GameMode drift")

        target = unreal.EditorAssetLibrary.load_asset(TARGET_PLANET)
        require(target is not None and target.get_class().get_name() == "PlanetData", "ProfileV1 PlanetData missing")
        require(int(target.get_editor_property("generation_seed")) == 1337, "ProfileV1 seed drift")
        require(abs(float(target.get_editor_property("planet_radius")) - 300000000.0) <= 0.01,
                "ProfileV1 radius drift")
        require(asset_path(target.get_editor_property("generation_material")) == TARGET_GENERATION,
                "ProfileV1 generation binding drift")
        require(asset_path(target.get_editor_property("biome_mask_material")) == TARGET_MASK,
                "ProfileV1 mask binding drift")
        require(asset_path(target.get_editor_property("planet_material")) == TARGET_SURFACE,
                "ProfileV1 surface binding drift")
        require(bool(target.get_editor_property("generate_water")), "ProfileV1 native water disabled")

        check = map_check(world)
        require(dirty_packages() == {"content": [], "maps": []}, "MapCheck dirtied packages")
        require(sha256(HOME_FILE) == EXPECTED_HOME, "MapCheck changed home-map bytes")
        require(verify_hashes(EXPECTED_FILES, "post-MapCheck input") == tracked_before,
                "Authenticated input set changed")
        require(verify_hashes(PROTECTED, "post-MapCheck protected checkpoint") == protected_before,
                "Protected checkpoint set changed")

        report.update({
            "status": "PASS_PROFILE_V1_HOME_BINDING_FRESH_RELOAD_MAPCHECK_PENDING_RUNTIME_VISUAL",
            "map": HOME_MAP,
            "map_sha256_before_after": EXPECTED_HOME,
            "actor_count": len(actors),
            "planet_data": TARGET_PLANET,
            "generation_seed": 1337,
            "planet_radius_cm": 300000000.0,
            "max_foliage_instances_per_chunk": 100000,
            "a01_game_mode": EXPECTED_GAME_MODE,
            "native_water_preserved": True,
            "map_check": check,
            "dirty_packages_after": dirty_packages(),
            "save_called": False,
            "pie_started": False,
            "explicit_regeneration_called": False,
            "next_safe_action": "Run one bounded provider-off real-D3D12 PIE generation/gameplay/visual acceptance against the exact verified map; retain rollback and reject on movement, biome, grass, shoreline or visual failure.",
        })
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        report["completed_utc"] = now()
        write_json_exclusive(RESULT, report)
        unreal.log("REDMMO_PPG_PROFILE_V1_HOME_BINDING_RELOAD " + report["status"])
        schedule_exit()


main()
