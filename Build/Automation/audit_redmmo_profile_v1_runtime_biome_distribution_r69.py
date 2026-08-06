"""Read-only runtime census of the current seeded PPG biome distribution.

This deliberately does not alter PlanetData, seed, terrain, foliage, water,
materials, map actors, or packages. It streams the existing planet from a
deterministic set of directions and samples each generated chunk's live PPG
BiomeMap. The result distinguishes a presentation-layer failure (biomes are
emitted but look alike) from a generation/mask failure (biomes are absent).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import time
import traceback
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject")
MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
MAP_FILE = PROJECT.parent / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
PROFILE_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
EXPECTED_MAP_SHA = "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3"
EXPECTED_PROFILE_SHA = "56EA5F830A8F581C1844B956EBABA556B45E200C397443F37BA921766862FC1A"
EXPECTED_PROFILE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
EXPECTED_SEED = 1337
ROLLBACK = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeRuntimeBiomeDistribution_R69B_20260805T2234Z")
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_RuntimeBiomeDistribution_R69B_20260805T2234Z")
RESULT = DIAG / "result.json"
HELPERS = Path(r"D:\RedMMOTitan\Build\Automation\apply_redmmo_profile_v1_seeded_land_start_r20.py")
EXPECTED_HELPERS_SHA = "7707C56E13E9922A2F2D3ADBCE4CB7CCD917241B5F875EE631E347B5A70B83B7"

DIRECTION_COUNT = 32
SETTLE_FRAMES = 45
VIEW_ALTITUDE_CM = 100000.0
ABOVE_SEA_ALPHA = 0.999
PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


require(sha256(HELPERS) == EXPECTED_HELPERS_SHA, "R20 helper source drift")
helper_source = HELPERS.read_text(encoding="utf-8")
helper_prefix = helper_source.split("\nrequire(os.path.normcase", 1)[0]
helper_ns = {"__name__": "redmmo_r69_helpers", "__file__": str(HELPERS)}
exec(compile(helper_prefix, str(HELPERS), "exec"), helper_ns)

asset_path = helper_ns["asset_path"]
biome_records = helper_ns["biome_records"]
dirty_packages = helper_ns["dirty_packages"]
provider_gate = helper_ns["provider_gate"]
sample_component = helper_ns["sample_component"]
vec = helper_ns["vec"]
add = helper_ns["add"]
sub = helper_ns["sub"]
mul = helper_ns["mul"]
length = helper_ns["length"]
normalized = helper_ns["normalized"]
write_json_exclusive = helper_ns["write_json_exclusive"]


def fibonacci_directions(count):
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))
    values = []
    for index in range(count):
        y = 1.0 - (2.0 * (index + 0.5) / count)
        ring = math.sqrt(max(0.0, 1.0 - y * y))
        theta = golden_angle * index
        values.append(unreal.Vector(math.cos(theta) * ring, y, math.sin(theta) * ring))
    return values


def component_sample_key(component, sample):
    location = component.get_world_location()
    return "|".join((
        component.get_path_name(),
        str(int(round(location.x / 10.0))),
        str(int(round(location.y / 10.0))),
        str(int(round(location.z / 10.0))),
        str(sample["recursion_level"]),
        str(int(round(sample["chunk_size"] / 10.0))),
    ))


class Audit:
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
        self.directions = fibonacci_directions(DIRECTION_COUNT)
        self.direction_index = -1
        self.direction = None
        self.biomes = []
        self.by_index = {}
        self.seen = set()
        self.samples = []
        self.direction_records = []
        self.errors = []
        self.report = {
            "schema": "redmmo.ppg.runtime_biome_distribution.r69.v1",
            "status": "RUNNING",
            "evidence_class": "automation",
            "started_utc": now(),
            "map": MAP,
            "seed_changed": False,
            "generation_called": False,
            "persistent_writes": False,
            "direction_count": DIRECTION_COUNT,
            "settle_frames_per_direction": SETTLE_FRAMES,
            "view_altitude_cm": VIEW_ALTITUDE_CM,
        }

    def set_phase(self, value):
        self.phase = value
        self.phase_started = time.monotonic()
        self.frames = 0
        self.ready_frames = 0
        unreal.log("REDMMO_R69_BIOME_DISTRIBUTION_PHASE " + value)

    def start(self):
        require(not RESULT.exists(), "R69 result no-clobber failed")
        require(not ROLLBACK.exists(), "R69 rollback no-clobber failed")
        require(sha256(MAP_FILE) == EXPECTED_MAP_SHA, "Home map hash drift")
        require(sha256(PROFILE_FILE) == EXPECTED_PROFILE_SHA, "ProfileV1 hash drift")
        require(dirty_packages() == {"content": [], "maps": []}, "Editor started dirty")
        self.report["provider_gate_before"] = provider_gate()
        for path, expected in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected, "Protected hash drift: " + str(path))

        ROLLBACK.mkdir(parents=True, exist_ok=False)
        rollback_map = ROLLBACK / "RedMMO_PPG_HomeWorld.pre_r69_no_save.umap"
        shutil.copy2(MAP_FILE, rollback_map)
        require(sha256(rollback_map) == EXPECTED_MAP_SHA, "Rollback byte mismatch")
        write_json_exclusive(ROLLBACK / "manifest.json", {
            "schema": "redmmo.ppg.runtime_biome_distribution.rollback.v1",
            "captured_utc": now(),
            "source": str(MAP_FILE),
            "source_sha256": EXPECTED_MAP_SHA,
            "rollback": str(rollback_map),
            "restore": "No restore is expected because R69 is read-only/no-save.",
        })
        self.report["rollback"] = str(rollback_map)
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
        require(seed == EXPECTED_SEED, "PPG seed drift")
        self.biomes = biome_records(self.planet)
        self.by_index = {item["index"]: item for item in self.biomes}
        self.report["planet"] = {
            "center": vec(self.center),
            "radius_cm": self.radius,
            "seed": seed,
            "biomes": self.biomes,
        }
        self.report["transient_view_pawn_class"] = pawn.get_class().get_name()
        self.set_phase("wait_initial_generation")

    def generation_ready(self):
        status = self.spawner.get_planet_generation_status()
        phase = str(status.get_editor_property("phase"))
        progress = float(status.get_editor_property("progress"))
        generating = bool(status.get_editor_property("is_generating"))
        self.report["generation"] = {
            "phase": phase,
            "progress": progress,
            "is_generating": generating,
        }
        return "COMPLETE" in phase.upper() and progress >= 0.999 and not generating

    def begin_next_direction(self):
        self.direction_index += 1
        if self.direction_index >= len(self.directions):
            self.finish_scan()
            return
        self.direction = self.directions[self.direction_index]
        target = add(self.center, mul(self.direction, self.radius + VIEW_ALTITUDE_CM))
        require(self.pawn.set_actor_location(target, False, True) is not False,
                "Transient view-pawn teleport failed")
        self.set_phase("settle_direction")

    def evaluate_direction(self):
        components = list(self.spawner.get_components_by_class(unreal.StaticMeshComponent))
        terrain = [
            component for component in components
            if component.is_query_collision_enabled()
            and component.get_editor_property("static_mesh") is not None
            and not isinstance(component, unreal.InstancedStaticMeshComponent)
        ]
        record = {
            "index": self.direction_index,
            "direction": vec(self.direction),
            "query_collision_component_count": len(terrain),
            "new_samples": 0,
            "dominant_counts": {},
            "above_sea": 0,
            "below_sea": 0,
            "sample_errors": [],
        }
        counts = Counter()
        for component in terrain:
            location = component.get_world_location()
            delta = sub(location, self.center)
            if length(delta) < self.radius * 0.5:
                continue
            direction = normalized(delta)
            point = add(self.center, mul(direction, self.radius))
            try:
                sample = sample_component(self.world, component, point, self.center, self.radius)
            except Exception as error:
                if len(record["sample_errors"]) < 8:
                    record["sample_errors"].append({
                        "component": component.get_path_name(), "error": str(error)})
                continue
            if sample is None:
                continue
            key = component_sample_key(component, sample)
            if key in self.seen:
                continue
            self.seen.add(key)
            dominant_index = int(sample["top3_biome_indices"][0])
            dominant = self.by_index.get(dominant_index, {
                "index": dominant_index, "name": "UNKNOWN", "foliage": None})
            alpha = float(sample["raw_index_pixel"][3])
            above_sea = alpha >= ABOVE_SEA_ALPHA
            counts[dominant["name"]] += 1
            record["new_samples"] += 1
            record["above_sea" if above_sea else "below_sea"] += 1
            self.samples.append({
                "stream_direction_index": self.direction_index,
                "component": component.get_path_name(),
                "component_world_location": vec(location),
                "component_center_direction": vec(direction),
                "recursion_level": sample["recursion_level"],
                "chunk_size": sample["chunk_size"],
                "sea_authority_alpha": alpha,
                "at_or_above_sea": above_sea,
                "dominant_biome_index": dominant_index,
                "dominant_biome_name": dominant["name"],
                "dominant_strength": float(sample["top3_biome_strengths"][0]),
                "top3_biome_indices": sample["top3_biome_indices"],
                "top3_biome_strengths": sample["top3_biome_strengths"],
            })
        record["dominant_counts"] = dict(sorted(counts.items()))
        self.direction_records.append(record)
        self.begin_next_direction()

    def finish_scan(self):
        counts = Counter(sample["dominant_biome_name"] for sample in self.samples)
        above_counts = Counter(
            sample["dominant_biome_name"] for sample in self.samples if sample["at_or_above_sea"])
        below_counts = Counter(
            sample["dominant_biome_name"] for sample in self.samples if not sample["at_or_above_sea"])
        strength_sum = defaultdict(float)
        strength_count = Counter()
        for sample in self.samples:
            name = sample["dominant_biome_name"]
            strength_sum[name] += sample["dominant_strength"]
            strength_count[name] += 1
        expected_names = [item["name"] for item in self.biomes]
        emitted = [name for name in expected_names if counts[name] > 0]
        missing = [name for name in expected_names if counts[name] == 0]
        sample_count = len(self.samples)
        distribution = {}
        for name in expected_names:
            distribution[name] = {
                "samples": counts[name],
                "percent": (100.0 * counts[name] / sample_count) if sample_count else 0.0,
                "above_sea_samples": above_counts[name],
                "below_sea_samples": below_counts[name],
                "mean_dominant_strength": (
                    strength_sum[name] / strength_count[name] if strength_count[name] else 0.0),
            }
        status = (
            "PASS_R69_ALL_PROFILE_BIOMES_EMITTED_NO_SAVE"
            if not missing else "PARTIAL_R69_PROFILE_BIOMES_MISSING_FROM_RUNTIME_SAMPLE_NO_SAVE"
        )
        self.report.update({
            "status": status,
            "directions_evaluated": len(self.direction_records),
            "unique_runtime_chunk_samples": sample_count,
            "direction_records": self.direction_records,
            "biome_distribution": distribution,
            "emitted_biomes": emitted,
            "missing_biomes": missing,
            "above_sea_sample_count": sum(above_counts.values()),
            "below_sea_sample_count": sum(below_counts.values()),
            "sample_preview": self.samples[:96],
            "map_sha256_after": sha256(MAP_FILE),
            "profile_sha256_after": sha256(PROFILE_FILE),
            "dirty_packages_before_pie_stop": dirty_packages(),
            "completed_utc": now(),
            "claim_limit": (
                "Live seeded chunk-distribution evidence only. This does not prove accepted biome art, "
                "shoreline rendering, continent silhouettes, paths, gameplay, packaging, replication, "
                "multiplayer, or player acceptance."),
        })
        require(sample_count >= 100, "Insufficient live biome samples")
        require(self.report["map_sha256_after"] == EXPECTED_MAP_SHA, "Home map changed")
        require(self.report["profile_sha256_after"] == EXPECTED_PROFILE_SHA, "ProfileV1 changed")
        require(dirty_packages() == {"content": [], "maps": []}, "R69 dirtied packages")
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "Protected package changed: " + str(path))
        self.level.editor_request_end_play()
        self.set_phase("wait_pie_stop")

    def publish(self):
        require(not self.level.is_in_play_in_editor(), "PIE still active during R69 publish")
        require(dirty_packages() == {"content": [], "maps": []}, "Editor dirty after R69")
        self.report["provider_gate_after"] = provider_gate()
        self.report["dirty_packages_after"] = dirty_packages()
        write_json_exclusive(RESULT, self.report)
        unreal.log_warning("REDMMO_R69_BIOME_DISTRIBUTION " + json.dumps(
            {"status": self.report["status"],
             "samples": self.report["unique_runtime_chunk_samples"],
             "emitted": self.report["emitted_biomes"],
             "missing": self.report["missing_biomes"]}, sort_keys=True))
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), "QUIT_EDITOR")

    def fail(self, error):
        self.report.update({
            "status": "FAIL",
            "error": str(error),
            "traceback": traceback.format_exc(),
            "directions_evaluated": len(self.direction_records),
            "sample_count": len(self.samples),
            "map_sha256_observed": sha256(MAP_FILE) if MAP_FILE.is_file() else None,
            "profile_sha256_observed": sha256(PROFILE_FILE) if PROFILE_FILE.is_file() else None,
            "completed_utc": now(),
        })
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        if not RESULT.exists():
            write_json_exclusive(RESULT, self.report)
        unreal.log_error("REDMMO_R69_BIOME_DISTRIBUTION_FAIL " + repr(error) + "\n" + traceback.format_exc())
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), "QUIT_EDITOR")

    def tick(self, _delta):
        try:
            self.frames += 1
            require(time.monotonic() - self.started < 900.0, "R69 overall timeout")
            require(time.monotonic() - self.phase_started < 300.0, "R69 phase timeout: " + self.phase)
            if self.phase == "prepare":
                self.start()
            elif self.phase == "wait_pie":
                self.bind_pie()
            elif self.phase == "wait_initial_generation":
                if self.generation_ready():
                    self.ready_frames += 1
                    if self.ready_frames >= 90:
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
audit = Audit()
audit.handle = unreal.register_slate_post_tick_callback(audit.tick)
unreal.log("REDMMO_R69_BIOME_DISTRIBUTION_STARTED")
