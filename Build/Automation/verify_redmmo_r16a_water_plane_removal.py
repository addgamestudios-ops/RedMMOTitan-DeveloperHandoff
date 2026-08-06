"""Fresh-reload verification for the R16A exact water-plane deletion."""

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
HOME_MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
HOME_FILE = PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
EXPECTED_HOME = "1821ED915E924085A2D6B3E1A85984A0F207C116EFF32AC974E8F0B7CD217F87"
R06_LABEL = "RedMMO_StylizedPilot_OasisWater_R06"
EXPECTED_PLANET = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10O/DA_PPG_HomeWorld_StylizedBinding_R10O"
EXPECTED_NATIVE_WATER = "/PPG/Water/Materials/M_PlanetaryOceanWater"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_R16A_RemoveRejectedWaterPlane_20260803_003500")
RESULT = DIAG / "verify_redmmo_r16a_water_plane_removal_result.json"

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


def command_log():
    command = str(unreal.SystemLibrary.get_command_line())
    match = re.search(r'(?i)-abslog=(?:"([^"]+)"|(\S+))', command)
    return Path(match.group(1) or match.group(2)) if match else PROJECT / r"Saved\Logs\RedMMO.log"


def map_check(world):
    log_path = command_log()
    require(log_path.is_file(), "Verifier log missing")
    marker = "R16A_MAPCHECK_BEGIN_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    initial_size = log_path.stat().st_size
    unreal.log(marker)
    deadline = time.monotonic() + 10.0
    marker_end = None
    while time.monotonic() < deadline:
        time.sleep(0.05)
        with log_path.open("rb") as stream:
            stream.seek(min(initial_size, log_path.stat().st_size))
            tail = stream.read().decode("utf-8", errors="replace")
        index = tail.find(marker)
        if index >= 0:
            marker_end = initial_size + len(tail[: index + len(marker)].encode("utf-8"))
            break
    require(marker_end is not None, "MapCheck marker missing")
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
    require(matches, "MapCheck completion missing")
    errors, warnings = (int(value) for value in matches[-1])
    require(errors == 0 and warnings == 0, "MapCheck failed")
    return {"marker": marker, "errors": errors, "warnings": warnings, "log": str(log_path)}


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
        "schema": "redmmo.r16a.water_plane_removal.fresh_reload.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "automation",
    }
    try:
        require(not RESULT.exists(), "No-clobber result already exists")
        require(sha256(HOME_FILE) == EXPECTED_HOME, "R16A home-map hash drift")
        report["provider_gate"] = provider_gate()
        for path, expected in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected, "Protected hash drift")
        world = unreal.EditorLoadingAndSavingUtils.load_map(HOME_MAP)
        require(world is not None, "Fresh map load failed")
        require(not dirty_packages(), "Fresh map load dirtied packages")
        actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
        require(len(actors) == 12, "Fresh actor count drift: " + str(len(actors)))
        require(not any(actor.get_actor_label() == R06_LABEL for actor in actors), "Rejected R06 water actor persists")
        spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        require(len(spawners) == 1, "Expected one PPG spawner")
        spawner = spawners[0]
        planet = spawner.get_editor_property("planet_data")
        require(asset_path(planet) == EXPECTED_PLANET, "PPG PlanetData binding drift")
        require(bool(planet.get_editor_property("generate_water")), "Native PPG GenerateWater disabled")
        require(asset_path(planet.get_editor_property("water_material")) == EXPECTED_NATIVE_WATER, "Native PPG water material drift")
        report["map_check"] = map_check(world)
        require(not dirty_packages(), "Verifier dirtied packages")
        report.update({
            "status": "PASS_FRESH_RELOAD_MAPCHECK_NO_REJECTED_PLANE",
            "home_map_sha256": sha256(HOME_FILE),
            "actor_count": len(actors),
            "r06_actor_count": 0,
            "ppg_planet_data": asset_path(planet),
            "ppg_generate_water": True,
            "ppg_water_material": asset_path(planet.get_editor_property("water_material")),
            "map_saved_by_verifier": False,
            "dirty_packages": dirty_packages(),
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
        unreal.log("REDMMO_R16A_WATER_PLANE_VERIFY " + report["status"])
        schedule_exit()


main()
