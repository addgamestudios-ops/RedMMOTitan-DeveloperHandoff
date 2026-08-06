"""Fresh-process, no-save verifier for the serialized RedMMO R15 home world."""

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


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
PROJECT_FILE = PROJECT / "RedMMO.uproject"
HOME_MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
HOME_FILE = PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ContinentBiome_R15_20260802_211912")
FINALIZER = DIAG / "finalize_r15_continent_biome_r05_result.json"
FINALIZER_GUARD = DIAG / "run_r15_finalizer_guard_r05_result.json"
RESULT = DIAG / "verify_r15_fresh_reload_r02_result.json"
PROFILE = PROJECT / r"Config\RedMMO\PPGContinentBiomeProfiles\HomeWorld_ContinentBiome_R15.json"
EXPECTED_HOME_POST = "7BA68701F4B1A96777407FC8C349D90878037917CD3212878164B9A28BB37059"
EXPECTED_FINALIZER_SHA256 = "DEF1A4D5F56DA6F0FB6296B553882EB68D0DF8AA04D81A83256A4241B0F1EE95"
EXPECTED_PROFILE_SHA256 = "FAAD649D96227DC03589E0E604762A533D3232DAC65B42EBEB895B49D03DF3CD"

SOURCE_PLANET = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10O/DA_PPG_HomeWorld_StylizedBinding_R10O"
SOURCE_FOLIAGE = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10O/Profiles/DA_PPG_HomeWorld_StylizedForest_R10O"
ROOT = "/Game/RedMMO/World/PPG/HomeWorld/ContinentBiome/R15"
TARGET_PLANET = ROOT + "/DA_PPG_HomeWorld_ContinentBiome_R15"
TARGET_GENERATION = ROOT + "/Materials/M_PPG_Generation_Continents_R15"
TARGET_MASK = ROOT + "/Materials/M_PPG_BiomeMask_Continents_R15"
TARGET_SURFACE_PARENT = ROOT + "/Materials/M_PPG_Home_BiomeSurface_R15"
TARGET_SURFACE_MI = ROOT + "/Materials/MI_PPG_Home_BiomeSurface_R15"
TARGET_CELL_MAP = ROOT + "/DA_PPG_HomeWorld_ContinentBiome_R15_PPG_BiomeCells"
TARGET_ASSETS = {
    TARGET_PLANET,
    TARGET_GENERATION,
    TARGET_MASK,
    TARGET_SURFACE_PARENT,
    TARGET_SURFACE_MI,
    TARGET_CELL_MAP,
}
EXPECTED_TARGET_HASHES = {
    TARGET_PLANET: "47924E95B2CF2A730065709E4BF7861A33B2C3D1A0872E8E9124AD8C500FD4D0",
    TARGET_CELL_MAP: "123F39A471D29FBDDB096E842F2620A4460FD77F43613DA1A045644F560E2162",
    TARGET_SURFACE_MI: "1A8568B6F37A63B82E974915511029B28360F0C8DD6D448B66B6708566766E43",
    TARGET_MASK: "D8A11945E6AD4EDFF7E1B17B489CF83FA12A0C96A8E63902EBB78295E37FBB72",
    TARGET_GENERATION: "433A6EB553B1FA46812297A8EBAB74829E8FCAC8C69197BEC06A527F6E0D9C04",
    TARGET_SURFACE_PARENT: "BAE8D5DFC16E342D6AB679475DDDDB6478A03DE0DC51C5DE587A3EBF17174227",
}

SOURCE_HASHES = {
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10O\DA_PPG_HomeWorld_StylizedBinding_R10O.uasset": "7C6835CA50EBB06B4C94AA6D1E8B0419B1E0ACF09A44D5CEA5B670FBD5865C5A",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10O\Profiles\DA_PPG_HomeWorld_StylizedForest_R10O.uasset": "4D7B577684CF74CBF56BCB6AF8A6867DAD130C8BACF022CF461D86A53833E18F",
}
PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"): "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"): "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap"): "211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7",
    Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeCoastDatum_20260714\RedPlanetGen_50km_FusedPrototype.umap"): "A9C42C0D1B0429DD1018F00F0D2AB8A18F66C07291611964EFF5F9710F3B0C6A",
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


def asset_file(path):
    require(path.startswith("/Game/"), "Unexpected project asset path: " + path)
    return PROJECT / ("Content" + path.removeprefix("/Game").replace("/", os.sep) + ".uasset")


def load(path, class_name=None):
    asset = unreal.EditorAssetLibrary.load_asset(path)
    require(asset is not None, "Missing asset: " + path)
    if class_name:
        require(asset.get_class().get_name() == class_name, "Class mismatch: " + path)
    return asset


def dirty_packages():
    values = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    values += list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted(set(asset_path(item) for item in values))


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


def command_log():
    command = str(unreal.SystemLibrary.get_command_line())
    match = re.search(r'(?i)-abslog=(?:"([^"]+)"|(\S+))', command)
    return Path(match.group(1) or match.group(2)) if match else PROJECT / r"Saved\Logs\RedMMO.log"


def map_check_after_marker(world):
    log_path = command_log()
    require(log_path.is_file(), "Verifier log missing: " + str(log_path))
    marker = "R15_FRESH_MAPCHECK_BEGIN_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    initial_size = log_path.stat().st_size
    unreal.log(marker)
    marker_end = None
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        time.sleep(0.05)
        with log_path.open("rb") as stream:
            stream.seek(min(initial_size, log_path.stat().st_size))
            tail = stream.read().decode("utf-8", errors="replace")
        index = tail.find(marker)
        if index >= 0:
            marker_end = initial_size + len(tail[: index + len(marker)].encode("utf-8"))
            break
    require(marker_end is not None, "Fresh MapCheck marker did not reach log")
    unreal.SystemLibrary.execute_console_command(world, "MAP CHECKDEP NOCLEARLOG")
    pattern = re.compile(r"MapCheck: Map check complete: (\d+) Error\(s\), (\d+) Warning\(s\)")
    matches = []
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        time.sleep(0.1)
        with log_path.open("rb") as stream:
            stream.seek(min(marker_end, log_path.stat().st_size))
            matches = pattern.findall(stream.read().decode("utf-8", errors="replace"))
        if matches:
            break
    require(matches, "No MapCheck completion after fresh marker")
    errors, warnings = (int(value) for value in matches[-1])
    require(errors == 0 and warnings == 0, "MapCheck failed: {}/{}".format(errors, warnings))
    return {"marker": marker, "errors": errors, "warnings": warnings, "log": str(log_path)}


def stable(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [stable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): stable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return stable(to_dict())
    path = asset_path(value)
    return path if path is not None else str(value)


def without_key(mapping, key_name):
    return {
        str(key): stable(value)
        for key, value in mapping.items()
        if str(key).replace("_", "").lower() != key_name.replace("_", "").lower()
    }


def biome_snapshot(planet):
    records = []
    structs = list(planet.get_editor_property("biome_data"))
    for biome in structs:
        data = biome.to_dict()
        records.append({
            "name": str(biome.get_editor_property("name")),
            "foliage_data": asset_path(biome.get_editor_property("foliage_data")),
            "non_foliage_fields": without_key(data, "foliage_data"),
        })
    return records


def foliage_snapshot(foliage):
    entries = list(foliage.get_editor_property("foliage_list"))
    records = []
    for entry in entries:
        data = entry.to_dict()
        records.append({
            "non_mesh_fields": without_key(data, "meshes"),
            "mesh_refs": [asset_path(item.get_editor_property("mesh")) for item in entry.get_editor_property("meshes")],
        })
    return records


def read_evidence_anchor():
    require(FINALIZER.is_file(), "R15 finalizer evidence missing")
    require(FINALIZER_GUARD.is_file(), "R15 finalizer guard evidence missing")
    finalizer = json.loads(FINALIZER.read_text(encoding="utf-8-sig"))
    guard = json.loads(FINALIZER_GUARD.read_text(encoding="utf-8-sig"))
    require(finalizer.get("status") == "PASS_SERIALIZED_PENDING_FRESH_RELOAD_MAPCHECK_AND_REAL_GPU", "R15 finalizer did not pass")
    require(guard.get("status") == "PASS_SERIALIZED_PENDING_FRESH_RELOAD_MAPCHECK_AND_REAL_GPU", "R15 finalizer guard did not pass")
    require(guard.get("result_sha256") == sha256(FINALIZER), "R15 finalizer evidence hash is not guard-anchored")
    require(sha256(FINALIZER) == EXPECTED_FINALIZER_SHA256, "R15 finalizer evidence hash drift")
    expected_home = str(finalizer.get("home_map_sha256_after", "")).upper()
    require(re.fullmatch(r"[0-9A-F]{64}", expected_home) is not None, "Invalid post-R15 home hash")
    require(expected_home != "C9BE88085575E75E1790CB9306D564EB100F5ED2E75E012C1FD09EA110FDDFE0", "R15 home map did not change")
    require(expected_home == EXPECTED_HOME_POST, "Unexpected serialized post-R15 home hash")
    project_hashes = {str(key): str(value).upper() for key, value in finalizer.get("project_owned_hashes", {}).items()}
    require(set(project_hashes) == TARGET_ASSETS, "R15 target-asset evidence set drift")
    require(all(re.fullmatch(r"[0-9A-F]{64}", value) for value in project_hashes.values()), "Invalid R15 target hash")
    require(project_hashes == EXPECTED_TARGET_HASHES, "Serialized R15 target hashes drift")
    profile_hash = str(finalizer.get("profile_sha256", "")).upper()
    require(re.fullmatch(r"[0-9A-F]{64}", profile_hash) is not None, "Invalid R15 profile hash")
    require(profile_hash == EXPECTED_PROFILE_SHA256, "Serialized R15 profile hash drift")
    return finalizer, expected_home, project_hashes, profile_hash


def tracked_files(expected_home, project_hashes, profile_hash):
    tracked = {"home_map": (HOME_FILE, expected_home), "profile": (PROFILE, profile_hash)}
    for asset, expected in sorted(project_hashes.items()):
        tracked["target:" + asset] = (asset_file(asset), expected)
    for path, expected in SOURCE_HASHES.items():
        tracked["source:" + str(path)] = (path, expected)
    for path, expected in PROTECTED.items():
        tracked["protected:" + str(path)] = (path, expected)
    return tracked


def snapshot_hashes(tracked):
    result = {}
    for label, (path, expected) in tracked.items():
        require(path.is_file(), "Tracked file missing: " + str(path))
        actual = sha256(path)
        require(actual == expected, "Tracked hash drift for {}: actual={} expected={}".format(label, actual, expected))
        result[label] = actual
    return result


_EXIT = {"handle": None}


def schedule_exit(delay):
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
        "schema": "redmmo.ppg_home_continent_biome.r15.fresh_reload_verify.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "saved_project_state": False,
    }
    ok = False
    try:
        active_project = os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path())))
        require(active_project == os.path.normcase(os.path.abspath(str(PROJECT_FILE))), "Active project mismatch")
        require(not RESULT.exists(), "R15 fresh-reload result already exists")
        finalizer, expected_home, target_hashes, profile_hash = read_evidence_anchor()
        tracked = tracked_files(expected_home, target_hashes, profile_hash)
        report["expected_home_map_sha256"] = expected_home
        report["finalizer_result_sha256"] = sha256(FINALIZER)
        report["provider_gate"] = provider_gate()
        require(not dirty_packages(), "Fresh verifier started with dirty packages")
        report["hashes_before"] = snapshot_hashes(tracked)

        world = unreal.EditorLoadingAndSavingUtils.load_map(HOME_MAP)
        require(world is not None, "Fresh home-map load failed")
        require(not dirty_packages(), "Fresh home-map load dirtied packages")
        actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
        labels = sorted(actor.get_actor_label() for actor in actors)
        require(len(actors) == 12, "Expected 12 actors, found " + str(len(actors)))
        require("RedMMO_StylizedPilot_OasisWater_R06" not in labels, "Rejected R06 OasisWater actor persists")
        spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        require(len(spawners) == 1, "Expected exactly one PlanetSpawnerBP_C")
        spawner = spawners[0]
        require(asset_path(spawner.get_editor_property("planet_data")) == TARGET_PLANET, "Spawner R15 binding drift")

        planet = load(TARGET_PLANET, "PlanetData")
        source_planet = load(SOURCE_PLANET, "PlanetData")
        require(int(planet.get_editor_property("generation_seed")) == 1337, "Seed drift")
        require(abs(float(planet.get_editor_property("planet_radius")) - 300000000.0) <= 0.01, "Radius drift")
        require(abs(float(planet.get_editor_property("noise_height")) - 600000.0) <= 0.01, "Noise-height drift")
        require(asset_path(planet.get_editor_property("generation_material")) == TARGET_GENERATION, "Generation binding drift")
        require(asset_path(planet.get_editor_property("biome_mask_material")) == TARGET_MASK, "Biome-mask binding drift")
        require(asset_path(planet.get_editor_property("planet_material")) == TARGET_SURFACE_MI, "Surface binding drift")
        require(asset_path(planet.get_editor_property("biome_cell_map")) == TARGET_CELL_MAP, "Biome-cell binding drift")
        require(bool(planet.get_editor_property("generate_water")), "Native spherical water disabled")
        require(asset_path(planet.get_editor_property("water_material")) == "/PPG/Water/Materials/M_PlanetaryOceanWater", "Native spherical water material drift")

        cell_map = load(TARGET_CELL_MAP, "Texture2D")
        cell_dimensions = [int(cell_map.blueprint_get_size_x()), int(cell_map.blueprint_get_size_y())]
        require(cell_dimensions == [192, 32], "Biome-cell dimensions drift: " + str(cell_dimensions))

        source_biomes = biome_snapshot(source_planet)
        target_biomes = biome_snapshot(planet)
        require(len(source_biomes) == len(target_biomes) == 6, "Biome cardinality drift")
        require([item["name"] for item in target_biomes] == ["Craters", "Hills", "Mountains", "Desert", "Ocean", "Poles"], "Biome order drift")
        require(target_biomes == source_biomes, "Biome order, references, or non-foliage fields changed")
        require([item["foliage_data"] for item in target_biomes[:3]] == [SOURCE_FOLIAGE] * 3, "First-three foliage references/order drift")

        foliage = load(SOURCE_FOLIAGE, "FoliageData")
        foliage_entries = foliage_snapshot(foliage)
        require(len(foliage_entries) == 3, "Foliage-list cardinality drift")
        require(all(item["non_mesh_fields"] for item in foliage_entries), "Foliage non-mesh field capture is empty")

        report["map_check"] = map_check_after_marker(world)
        require(not dirty_packages(), "Fresh verification dirtied packages")
        report["hashes_after"] = snapshot_hashes(tracked)
        require(report["hashes_after"] == report["hashes_before"], "Tracked files changed during no-save verification")
        require(sha256(HOME_FILE) == expected_home, "Post-R15 home hash changed during verification")
        report.update({
            "status": "PASS_FRESH_RELOAD_MAPCHECK_ZERO_DIRTY_PENDING_REAL_GPU",
            "completed_utc": now(),
            "home_map_sha256": expected_home,
            "actor_count": len(actors),
            "actor_labels": labels,
            "spawner": {
                "label": spawner.get_actor_label(),
                "planet_data": TARGET_PLANET,
                "max_foliage_instances_per_chunk": int(spawner.get_editor_property("max_foliage_instances_per_chunk")),
            },
            "terrain_identity": {"seed": 1337, "radius_cm": 300000000.0, "noise_height_cm": 600000.0},
            "bindings": {
                "generation": TARGET_GENERATION,
                "biome_mask": TARGET_MASK,
                "surface": TARGET_SURFACE_MI,
                "biome_cell_map": TARGET_CELL_MAP,
                "water": "/PPG/Water/Materials/M_PlanetaryOceanWater",
            },
            "biome_cell_dimensions": cell_dimensions,
            "biomes": target_biomes,
            "foliage": {
                "asset": SOURCE_FOLIAGE,
                "entry_count": len(foliage_entries),
                "entries": foliage_entries,
                "source_file_sha256": SOURCE_HASHES[PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10O\Profiles\DA_PPG_HomeWorld_StylizedForest_R10O.uasset"],
            },
            "dirty_packages_before_exit": [],
            "saved_project_state": False,
            "real_gpu_verified": False,
        })
        with RESULT.open("xb") as stream:
            stream.write((json.dumps(report, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        ok = True
    except Exception as exc:
        report.update({"status": "FAIL", "completed_utc": now(), "error": str(exc), "traceback": traceback.format_exc()})
        if not RESULT.exists():
            with RESULT.open("xb") as stream:
                stream.write((json.dumps(report, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
        raise
    finally:
        schedule_exit(10.0 if ok else 2.0)


main()
