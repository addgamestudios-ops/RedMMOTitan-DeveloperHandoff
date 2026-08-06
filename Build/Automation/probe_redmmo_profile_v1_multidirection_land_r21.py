"""No-save global-direction PPG land-start probe for the clean RedMMO home map.

R20 proved that the query-collision components around the current underwater
start do not expose an above-sea candidate.  R21 moves only the transient PIE
view pawn through a deterministic Fibonacci sphere so PPG streams generated
surface chunks in other directions.  It never saves a package or calls planet
regeneration.  A candidate must be native PPG collision, above sea datum,
smooth enough to stand on, and dominated by an already foliage-enabled biome.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject")
MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
MAP_FILE = PROJECT.parent / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
PROFILE_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
EXPECTED_MAP_SHA = "6B45B423ED59BD8906A05CF35E7349C70282154DE2CE4723D41E0C16380F88D9"
EXPECTED_PROFILE_SHA = "5C50D50A8955C1E5F4270BDD4E53D1214C941725157B76422CD72B748978B837"
EXPECTED_PROFILE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
ROLLBACK = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeRedPPGProfileV1LandProbe_R21B_20260805T1100Z")
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1LandProbe_R21B_20260805T1100Z")
RESULT = DIAG / "result.json"
R20_HELPERS = Path(r"D:\RedMMOTitan\Build\Automation\apply_redmmo_profile_v1_seeded_land_start_r20.py")
EXPECTED_R20_HELPERS_SHA = "7707C56E13E9922A2F2D3ADBCE4CB7CCD917241B5F875EE631E347B5A70B83B7"
MIN_ELEVATION_CM = 25000.0
MIN_NORMAL_DOT = 0.92
VIEW_ALTITUDE_CM = 100000.0
SETTLE_FRAMES = 120
DIRECTION_COUNT = 32

PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def now():
    return datetime.now(timezone.utc).isoformat()


def require(value, message):
    if not value:
        raise RuntimeError(message)


require(sha256(R20_HELPERS) == EXPECTED_R20_HELPERS_SHA, "R20 helper source drift")
helper_source = R20_HELPERS.read_text(encoding="utf-8")
helper_prefix = helper_source.split("\nrequire(os.path.normcase", 1)[0]
helper_ns = {"__name__": "redmmo_r20_helpers", "__file__": str(R20_HELPERS)}
exec(compile(helper_prefix, str(R20_HELPERS), "exec"), helper_ns)

asset_path = helper_ns["asset_path"]
biome_records = helper_ns["biome_records"]
dirty_packages = helper_ns["dirty_packages"]
provider_gate = helper_ns["provider_gate"]
sample_biome = helper_ns["sample_biome"]
trace_direction = helper_ns["trace_direction"]
vec = helper_ns["vec"]
add = helper_ns["add"]
sub = helper_ns["sub"]
mul = helper_ns["mul"]
dot = helper_ns["dot"]
length = helper_ns["length"]
normalized = helper_ns["normalized"]
write_json_exclusive = helper_ns["write_json_exclusive"]


def fibonacci_directions(count):
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))
    values = []
    for index in range(count):
        y = 1.0 - (2.0 * (index + 0.5) / count)
        radius = math.sqrt(max(0.0, 1.0 - y * y))
        theta = golden_angle * index
        values.append(unreal.Vector(math.cos(theta) * radius, y, math.sin(theta) * radius))
    return values


class Probe:
    def __init__(self):
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.phase = "prepare"
        self.phase_started = time.monotonic()
        self.started = time.monotonic()
        self.frames = 0
        self.ready_frames = 0
        self.handle = None
        self.world = None
        self.spawner = None
        self.planet = None
        self.center = None
        self.radius = None
        self.pawn = None
        self.direction_index = -1
        self.direction = None
        self.directions = fibonacci_directions(DIRECTION_COUNT)
        self.attempts = []
        self.selected = None
        self.report = {
            "schema": "redmmo.ppg_profile_v1.multidirection_land_probe.r21.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "evidence_class": "automation",
            "map": MAP,
            "map_sha256_before": EXPECTED_MAP_SHA,
            "profile_sha256_before": EXPECTED_PROFILE_SHA,
            "seed_changed": False,
            "generation_called": False,
            "direction_count": DIRECTION_COUNT,
            "view_altitude_cm": VIEW_ALTITUDE_CM,
            "settle_frames_per_direction": SETTLE_FRAMES,
        }

    def set_phase(self, value):
        self.phase = value
        self.phase_started = time.monotonic()
        self.frames = 0
        self.ready_frames = 0
        unreal.log("REDMMO_R21_LAND_PROBE_PHASE " + value)

    def start(self):
        require(not RESULT.exists(), "R21 result no-clobber failed")
        require(not ROLLBACK.exists(), "R21 rollback no-clobber failed")
        require(sha256(MAP_FILE) == EXPECTED_MAP_SHA, "Home map hash drift")
        require(sha256(PROFILE_FILE) == EXPECTED_PROFILE_SHA, "ProfileV1 hash drift")
        require(dirty_packages() == {"content": [], "maps": []}, "Editor started dirty")
        self.report["provider_gate_before"] = provider_gate()
        for path, expected in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected, "Protected hash drift: " + str(path))
        ROLLBACK.mkdir(parents=True, exist_ok=False)
        rollback_map = ROLLBACK / "RedMMO_PPG_HomeWorld.pre_r21_land_probe.umap"
        shutil.copy2(MAP_FILE, rollback_map)
        require(sha256(rollback_map) == EXPECTED_MAP_SHA, "Rollback byte mismatch")
        write_json_exclusive(ROLLBACK / "manifest.json", {
            "schema": "redmmo.ppg_profile_v1.multidirection_land_probe.rollback.v1",
            "captured_utc": now(),
            "source": str(MAP_FILE),
            "source_sha256": EXPECTED_MAP_SHA,
            "rollback": str(rollback_map),
            "restore": "No restore is expected because R21 is no-save; retain this exact preimage.",
        })
        self.report["rollback"] = str(rollback_map)
        self.set_phase("loading_map")
        require(self.level.load_level(MAP), "Unable to load exact home map")
        require(dirty_packages() == {"content": [], "maps": []}, "Map load dirtied packages")
        self.level.editor_request_begin_play()
        self.set_phase("wait_pie")

    def bind_pie(self):
        world = self.editor.get_game_world()
        if world is None or not self.level.is_in_play_in_editor():
            return
        actors = list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor))
        spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        require(len(spawners) == 1, "Expected exactly one PPG spawner")
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        require(pawn is not None, "PIE player pawn unavailable")
        self.world = world
        self.spawner = spawners[0]
        self.planet = self.spawner.get_editor_property("planet_data")
        require(asset_path(self.planet) == EXPECTED_PROFILE, "Unexpected PlanetData binding")
        self.center = self.spawner.get_actor_location()
        self.radius = float(self.planet.get_editor_property("planet_radius"))
        self.pawn = pawn
        seed = int(self.planet.get_editor_property("generation_seed"))
        require(seed == 1337, "PPG seed drift")
        self.report["planet"] = {
            "center": vec(self.center),
            "radius_cm": self.radius,
            "seed": seed,
            "biomes": biome_records(self.planet),
        }
        self.report["transient_view_pawn_class"] = pawn.get_class().get_name()
        self.report["transient_view_pawn_initial_location"] = vec(pawn.get_actor_location())
        self.set_phase("wait_initial_generation")

    def generation_ready(self):
        status = self.spawner.get_planet_generation_status()
        phase = str(status.get_editor_property("phase"))
        progress = float(status.get_editor_property("progress"))
        generating = bool(status.get_editor_property("is_generating"))
        self.report["generation"] = {"phase": phase, "progress": progress, "is_generating": generating}
        return "COMPLETE" in phase.upper() and progress >= 0.999 and not generating

    def begin_next_direction(self):
        self.direction_index += 1
        if self.direction_index >= len(self.directions):
            self.finish("BLOCKED_NO_VIABLE_LAND_IN_R21_MULTIDIRECTION_SCAN")
            return
        self.direction = self.directions[self.direction_index]
        target = add(self.center, mul(self.direction, self.radius + VIEW_ALTITUDE_CM))
        require(self.pawn.set_actor_location(target, False, True) is not False,
                "Transient view-pawn teleport failed")
        self.set_phase("settle_direction")
        unreal.log("REDMMO_R21_LAND_PROBE_DIRECTION " + json.dumps({
            "index": self.direction_index,
            "direction": vec(self.direction),
            "view_target": vec(target),
        }, sort_keys=True))

    def terrain_components(self):
        components = list(self.spawner.get_components_by_class(unreal.StaticMeshComponent))
        terrain = [
            component for component in components
            if component.is_query_collision_enabled()
            and component.get_editor_property("static_mesh") is not None
            and not isinstance(component, unreal.InstancedStaticMeshComponent)
        ]
        return components, terrain

    def evaluate_direction(self):
        components, terrain = self.terrain_components()
        record = {
            "index": self.direction_index,
            "direction": vec(self.direction),
            "query_collision_component_count": len(terrain),
        }
        if not terrain:
            record["result"] = "no_query_collision_components"
            self.attempts.append(record)
            self.begin_next_direction()
            return
        terrain_paths = {component.get_path_name() for component in terrain}
        actors = list(unreal.GameplayStatics.get_all_actors_of_class(self.world, unreal.Actor))
        ignored = [actor for actor in actors if actor != self.spawner]
        hit = trace_direction(
            self.world, self.spawner, terrain_paths, self.center, self.radius, self.direction, ignored)
        if hit is None:
            record["result"] = "no_native_ppg_collision_hit"
            self.attempts.append(record)
            self.begin_next_direction()
            return
        point = hit["point"]
        radial = normalized(sub(point, self.center))
        normal = normalized(hit["normal"])
        elevation = length(sub(point, self.center)) - self.radius
        normal_dot = dot(normal, radial)
        record.update({
            "result": "collision_hit",
            "method": hit["method"],
            "component": hit["component"],
            "point": vec(point),
            "normal": vec(normal),
            "elevation_cm": elevation,
            "surface_normal_radial_dot": normal_dot,
            "trace_attempts": hit["attempts"],
        })
        if elevation < MIN_ELEVATION_CM:
            record["rejection"] = "below_minimum_elevation"
        elif normal_dot < MIN_NORMAL_DOT:
            record["rejection"] = "surface_too_steep"
        else:
            try:
                sample = sample_biome(
                    self.world, components, point, self.center, self.radius, self.report["planet"]["biomes"])
                record["biome_sample"] = sample
                dominant = sample["top3_biomes"][0]
                record["dominant_biome"] = dominant
                eligible = bool(dominant.get("foliage")) and float(dominant["strength"]) >= 0.90
                record["foliage_eligible"] = eligible
                if eligible:
                    record["persistable_playerstart_target"] = vec(add(point, mul(radial, 250.0)))
                    self.selected = record
                else:
                    record["rejection"] = "dominant_biome_not_foliage_eligible_at_90_percent"
            except Exception as error:
                record["rejection"] = "biome_sample_failed"
                record["biome_sample_error"] = str(error)
        self.attempts.append(record)
        if self.selected is not None:
            self.finish("PASS_R21_VIABLE_SEEDED_LAND_CANDIDATE_FOUND_NO_SAVE")
        else:
            self.begin_next_direction()

    def finish(self, status):
        self.report.update({
            "status": status,
            "attempts": self.attempts,
            "directions_evaluated": len(self.attempts),
            "selected_candidate": self.selected,
            "map_sha256_after": sha256(MAP_FILE),
            "profile_sha256_after": sha256(PROFILE_FILE),
            "dirty_packages_before_pie_stop": dirty_packages(),
            "completed_utc": now(),
            "claim_limit": (
                "No-save candidate-streaming evidence only. PlayerStart persistence, fresh reload, MapCheck, "
                "spawn collision, grass pixels, day/night, gameplay and player acceptance remain pending."
            ),
        })
        require(self.report["map_sha256_after"] == EXPECTED_MAP_SHA, "Home map changed during no-save probe")
        require(self.report["profile_sha256_after"] == EXPECTED_PROFILE_SHA, "ProfileV1 changed during no-save probe")
        require(dirty_packages() == {"content": [], "maps": []}, "No-save probe dirtied packages")
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "Protected package changed: " + str(path))
        self.level.editor_request_end_play()
        self.set_phase("wait_pie_stop")

    def publish(self):
        require(not self.level.is_in_play_in_editor(), "PIE still active during R21 publish")
        require(dirty_packages() == {"content": [], "maps": []}, "Editor dirty after R21 PIE stop")
        self.report["provider_gate_after"] = provider_gate()
        self.report["dirty_packages_after"] = dirty_packages()
        write_json_exclusive(RESULT, self.report)
        marker = "PASS" if self.report["status"].startswith("PASS") else "BLOCKED"
        unreal.log_warning("REDMMO_R21_LAND_PROBE_" + marker + " " + json.dumps(
            self.report, sort_keys=True, default=str))
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), "QUIT_EDITOR")

    def fail(self, error):
        self.report.update({
            "status": "FAIL",
            "error": str(error),
            "traceback": traceback.format_exc(),
            "attempts": self.attempts,
            "map_sha256_observed": sha256(MAP_FILE) if MAP_FILE.is_file() else None,
            "profile_sha256_observed": sha256(PROFILE_FILE) if PROFILE_FILE.is_file() else None,
            "completed_utc": now(),
        })
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        if not RESULT.exists():
            write_json_exclusive(RESULT, self.report)
        unreal.log_error("REDMMO_R21_LAND_PROBE_FAIL " + repr(error) + "\n" + traceback.format_exc())
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), "QUIT_EDITOR")

    def tick(self, _delta):
        try:
            self.frames += 1
            require(time.monotonic() - self.started < 900.0, "R21 overall timeout")
            require(time.monotonic() - self.phase_started < 300.0, "R21 phase timeout: " + self.phase)
            if self.phase == "prepare":
                self.start()
            elif self.phase == "wait_pie":
                self.bind_pie()
            elif self.phase == "wait_initial_generation":
                if self.generation_ready():
                    self.ready_frames += 1
                    if self.ready_frames >= 120:
                        self.begin_next_direction()
                else:
                    self.ready_frames = 0
            elif self.phase == "settle_direction":
                target = add(self.center, mul(self.direction, self.radius + VIEW_ALTITUDE_CM))
                self.pawn.set_actor_location(target, False, True)
                if self.generation_ready():
                    self.ready_frames += 1
                    if self.ready_frames >= SETTLE_FRAMES:
                        self.set_phase("evaluate_direction")
                else:
                    self.ready_frames = 0
            elif self.phase == "evaluate_direction":
                self.evaluate_direction()
            elif self.phase == "wait_pie_stop":
                if not self.level.is_in_play_in_editor() and self.editor.get_game_world() is None:
                    self.set_phase("publish")
            elif self.phase == "publish":
                self.publish()
        except Exception as error:
            self.fail(error)


require(os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path()))) ==
        os.path.normcase(os.path.abspath(str(PROJECT))), "Wrong active project")
probe = Probe()
probe.handle = unreal.register_slate_post_tick_callback(probe.tick)
unreal.log("REDMMO_R21_LAND_PROBE_STARTED")
