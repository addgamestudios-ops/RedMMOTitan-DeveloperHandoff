"""No-save native component collision fit at the R22-selected PPG land direction.

This deliberately avoids the failed world/profile trace family. It streams only
the selected R22 direction, samples the live generated chunk BiomeMap, and asks
each local generated terrain component to trace its own collision body. A pass
requires above-sea elevation, foliage-eligible seeded biome, outward runnable
normal, and capsule-centre clearance. No PlayerStart or package is saved.
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
R22_RESULT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1BiomeAuthority_R22_20260805T1110Z\result.json")
EXPECTED_R22_RESULT_SHA = "1A92C984FA0F3826594B3CDA71C034B0B790DEDCF6B7F9456AA86D12D8AB06BB"
ROLLBACK = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeRedPPGProfileV1CollisionFit_R23D_20260805T1130Z")
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1CollisionFit_R23D_20260805T1130Z")
RESULT = DIAG / "result.json"
R20_HELPERS = Path(r"D:\RedMMOTitan\Build\Automation\apply_redmmo_profile_v1_seeded_land_start_r20.py")
EXPECTED_R20_HELPERS_SHA = "7707C56E13E9922A2F2D3ADBCE4CB7CCD917241B5F875EE631E347B5A70B83B7"
VIEW_ALTITUDE_CM = 100000.0
SETTLE_FRAMES = 180
MIN_ELEVATION_CM = 25000.0
MIN_NORMAL_DOT = 0.92
MIN_DOMINANT_STRENGTH = 0.90
LOCAL_DIRECTION_DOT = 0.999999
CAPSULE_EXTRA_CLEARANCE_CM = 25.0

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
require(sha256(R22_RESULT) == EXPECTED_R22_RESULT_SHA, "R22 authority result drift")
helper_source = R20_HELPERS.read_text(encoding="utf-8")
helper_prefix = helper_source.split("\nrequire(os.path.normcase", 1)[0]
helper_ns = {"__name__": "redmmo_r20_helpers", "__file__": str(R20_HELPERS)}
exec(compile(helper_prefix, str(R20_HELPERS), "exec"), helper_ns)

asset_path = helper_ns["asset_path"]
biome_records = helper_ns["biome_records"]
dirty_packages = helper_ns["dirty_packages"]
provider_gate = helper_ns["provider_gate"]
sample_component = helper_ns["sample_component"]
vec = helper_ns["vec"]
add = helper_ns["add"]
sub = helper_ns["sub"]
mul = helper_ns["mul"]
dot = helper_ns["dot"]
length = helper_ns["length"]
normalized = helper_ns["normalized"]
write_json_exclusive = helper_ns["write_json_exclusive"]

r22 = json.loads(R22_RESULT.read_text(encoding="utf-8"))
require(r22.get("status") == "PASS_R22_ABOVE_SEA_FOLIAGE_AUTHORITY_DIRECTION_FOUND_NO_SAVE",
        "R22 authority did not pass")
SELECTED_DIRECTION = unreal.Vector(*r22["selected_candidate"]["component_center_direction"])


def unpack_component_trace(value):
    require(isinstance(value, tuple), "Unexpected LineTraceComponent return type: " + repr(type(value)))
    require(len(value) >= 4, "Unexpected LineTraceComponent return length: " + repr(len(value)))
    booleans = [item for item in value if isinstance(item, bool)]
    vectors = [item for item in value if hasattr(item, "x") and hasattr(item, "y") and hasattr(item, "z")]
    names = [item for item in value if item.__class__.__name__ == "Name"]
    hit_results = [item for item in value if item.__class__.__name__ == "HitResult"]
    require(len(vectors) >= 2,
            "LineTraceComponent tuple lacks two vectors: " + repr([type(item).__name__ for item in value]))
    # UE 5.8 Python omits the native bool return for this K2 wrapper. The two
    # ordered output vectors remain HitLocation and HitNormal; a miss leaves the
    # normal zero, while a collision hit returns a unit normal.
    hit = booleans[0] if booleans else length(vectors[1]) > 0.5
    return hit, vectors[0], vectors[1], names[0] if names else None, hit_results[0] if hit_results else value


def unpack_closest_point(value):
    require(isinstance(value, tuple), "Unexpected GetClosestPointOnCollision return type: " + repr(type(value)))
    require(len(value) >= 2, "Unexpected GetClosestPointOnCollision return length: " + repr(len(value)))
    numbers = [item for item in value if isinstance(item, (int, float)) and not isinstance(item, bool)]
    vectors = [item for item in value if hasattr(item, "x") and hasattr(item, "y") and hasattr(item, "z")]
    require(numbers and vectors,
            "GetClosestPointOnCollision tuple lacks number/vector: " + repr([type(item).__name__ for item in value]))
    return float(numbers[0]), vectors[0]


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
        self.noise_height = None
        self.pawn = None
        self.report = {
            "schema": "redmmo.ppg_profile_v1.local_collision_fit.r23d.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "evidence_class": "automation",
            "map": MAP,
            "map_sha256_before": EXPECTED_MAP_SHA,
            "profile_sha256_before": EXPECTED_PROFILE_SHA,
            "r22_result_sha256": EXPECTED_R22_RESULT_SHA,
            "selected_direction": vec(SELECTED_DIRECTION),
            "seed_changed": False,
            "generation_called": False,
        }

    def set_phase(self, value):
        self.phase = value
        self.phase_started = time.monotonic()
        self.frames = 0
        self.ready_frames = 0
        unreal.log("REDMMO_R23_COLLISION_FIT_PHASE " + value)

    def start(self):
        require(not RESULT.exists(), "R23D result no-clobber failed")
        require(not ROLLBACK.exists(), "R23D rollback no-clobber failed")
        require(sha256(MAP_FILE) == EXPECTED_MAP_SHA, "Home map hash drift")
        require(sha256(PROFILE_FILE) == EXPECTED_PROFILE_SHA, "ProfileV1 hash drift")
        require(dirty_packages() == {"content": [], "maps": []}, "Editor started dirty")
        self.report["provider_gate_before"] = provider_gate()
        for path, expected in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected, "Protected hash drift: " + str(path))
        ROLLBACK.mkdir(parents=True, exist_ok=False)
        rollback_map = ROLLBACK / "RedMMO_PPG_HomeWorld.pre_r23d_collision_fit.umap"
        shutil.copy2(MAP_FILE, rollback_map)
        require(sha256(rollback_map) == EXPECTED_MAP_SHA, "Rollback byte mismatch")
        write_json_exclusive(ROLLBACK / "manifest.json", {
            "schema": "redmmo.ppg_profile_v1.local_collision_fit.r23d.rollback.v1",
            "captured_utc": now(),
            "source": str(MAP_FILE),
            "source_sha256": EXPECTED_MAP_SHA,
            "rollback": str(rollback_map),
                "restore": "No restore is expected because R23D is no-save; retain this exact preimage.",
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
        self.noise_height = abs(float(self.planet.get_editor_property("noise_height")))
        self.pawn = pawn
        seed = int(self.planet.get_editor_property("generation_seed"))
        require(seed == 1337, "PPG seed drift")
        capsules = list(pawn.get_components_by_class(unreal.CapsuleComponent))
        require(capsules, "PIE pawn exposes no capsule component")
        capsule = capsules[0]
        self.report["planet"] = {
            "center": vec(self.center),
            "radius_cm": self.radius,
            "noise_height_cm": self.noise_height,
            "seed": seed,
            "biomes": biome_records(self.planet),
        }
        self.report["pawn"] = {
            "class": pawn.get_class().get_name(),
            "capsule_radius_cm": float(capsule.get_scaled_capsule_radius()),
            "capsule_half_height_cm": float(capsule.get_scaled_capsule_half_height()),
        }
        target = add(self.center, mul(SELECTED_DIRECTION, self.radius + VIEW_ALTITUDE_CM))
        require(self.pawn.set_actor_location(target, False, True) is not False,
                "Transient view-pawn teleport failed")
        self.set_phase("settle_selected_direction")

    def generation_ready(self):
        status = self.spawner.get_planet_generation_status()
        phase = str(status.get_editor_property("phase"))
        progress = float(status.get_editor_property("progress"))
        generating = bool(status.get_editor_property("is_generating"))
        self.report["generation"] = {"phase": phase, "progress": progress, "is_generating": generating}
        return "COMPLETE" in phase.upper() and progress >= 0.999 and not generating

    def evaluate(self):
        components = list(self.spawner.get_components_by_class(unreal.StaticMeshComponent))
        terrain = [
            component for component in components
            if component.is_query_collision_enabled()
            and component.get_editor_property("static_mesh") is not None
            and not isinstance(component, unreal.InstancedStaticMeshComponent)
        ]
        by_index = {item["index"]: item for item in self.report["planet"]["biomes"]}
        local = []
        for component in terrain:
            location = component.get_world_location()
            delta = sub(location, self.center)
            if length(delta) < self.radius * 0.5:
                continue
            direction = normalized(delta)
            alignment = dot(direction, SELECTED_DIRECTION)
            if alignment < LOCAL_DIRECTION_DOT:
                continue
            authority_point = add(self.center, mul(direction, self.radius))
            try:
                sample = sample_component(self.world, component, authority_point, self.center, self.radius)
            except Exception:
                continue
            if sample is None:
                continue
            alpha = float(sample["raw_index_pixel"][3])
            dominant_index = int(sample["top3_biome_indices"][0])
            dominant_strength = float(sample["top3_biome_strengths"][0])
            dominant = by_index.get(dominant_index, {
                "index": dominant_index, "name": "UNKNOWN", "foliage": None})
            if alpha < 0.999 or not dominant.get("foliage") or dominant_strength < MIN_DOMINANT_STRENGTH:
                continue
            local.append({
                "component_object": component,
                "component": component.get_path_name(),
                "direction": direction,
                "alignment_to_r22": alignment,
                "authority_alpha": alpha,
                "dominant_biome": dominant,
                "dominant_strength": dominant_strength,
                "recursion_level": sample["recursion_level"],
                "chunk_size": sample["chunk_size"],
            })
        require(local, "No local above-sea foliage-eligible component around R22 direction")
        local.sort(key=lambda item: (-item["alignment_to_r22"], -item["recursion_level"], item["chunk_size"]))

        evaluated = []
        viable = []
        trace_extent = self.noise_height + 1000000.0
        for item in local[:64]:
            component = item.pop("component_object")
            direction = item["direction"]
            start = add(self.center, mul(direction, self.radius + trace_extent))
            end = add(self.center, mul(direction, self.radius - trace_extent))
            trace_attempts = []
            hit_location = None
            hit_normal = None
            for trace_complex in (False, True):
                try:
                    raw = component.line_trace_component(start, end, trace_complex, False, False)
                    hit, location, normal, bone_name, _hit_result = unpack_component_trace(raw)
                    trace_attempts.append({
                        "trace_complex": trace_complex,
                        "hit": hit,
                        "location": vec(location),
                        "normal": vec(normal),
                        "bone_name": str(bone_name),
                    })
                    if hit:
                        hit_location = location
                        hit_normal = normal
                        break
                except Exception as error:
                    trace_attempts.append({"trace_complex": trace_complex, "error": str(error)})
            record = {key: value for key, value in item.items() if key != "direction"}
            record["direction"] = vec(direction)
            record["trace_attempts"] = trace_attempts
            if hit_location is None:
                record["rejection"] = "component_direct_trace_missed"
                evaluated.append(record)
                continue
            radial = normalized(sub(hit_location, self.center))
            normal = normalized(hit_normal)
            elevation = length(sub(hit_location, self.center)) - self.radius
            normal_dot = dot(normal, radial)
            spawn_center = add(hit_location, mul(radial,
                self.report["pawn"]["capsule_half_height_cm"] + CAPSULE_EXTRA_CLEARANCE_CM))
            record.update({
                "hit_location": vec(hit_location),
                "hit_normal": vec(normal),
                "radial": vec(radial),
                "elevation_cm": elevation,
                "surface_normal_radial_dot": normal_dot,
                "capsule_center_target": vec(spawn_center),
            })
            if elevation < MIN_ELEVATION_CM:
                record["rejection"] = "below_minimum_elevation"
                evaluated.append(record)
                continue
            if normal_dot < MIN_NORMAL_DOT:
                record["rejection"] = "surface_too_steep"
                evaluated.append(record)
                continue
            clearance_checks = []
            for other in terrain:
                try:
                    distance, closest = unpack_closest_point(other.get_closest_point_on_collision(spawn_center))
                except Exception:
                    continue
                if distance < 0.0:
                    continue
                clearance_checks.append({
                    "component": other.get_path_name(),
                    "distance_cm": distance,
                    "closest_point": vec(closest),
                })
            clearance_checks.sort(key=lambda value: value["distance_cm"])
            record["capsule_clearance_checks"] = clearance_checks[:12]
            if not clearance_checks:
                record["rejection"] = "capsule_clearance_query_unavailable"
                evaluated.append(record)
                continue
            required = self.report["pawn"]["capsule_half_height_cm"] + 10.0
            record["required_surface_distance_cm"] = required
            record["minimum_surface_distance_cm"] = clearance_checks[0]["distance_cm"]
            if clearance_checks[0]["distance_cm"] < required:
                record["rejection"] = "capsule_clearance_insufficient"
                evaluated.append(record)
                continue
            record["collision_fit_pass"] = True
            viable.append(record)
            evaluated.append(record)

        viable.sort(key=lambda item: (
            -item["surface_normal_radial_dot"],
            abs(item["elevation_cm"] - 100000.0),
            -item["minimum_surface_distance_cm"],
        ))
        selected = viable[0] if viable else None
        status = "PASS_R23D_NATIVE_COLLISION_SLOPE_CLEARANCE_FIT_NO_SAVE" if selected else \
            "BLOCKED_R23D_NO_LOCAL_COMPONENT_PASSED_COLLISION_SLOPE_CLEARANCE"
        self.report.update({
            "status": status,
            "query_collision_component_count": len(terrain),
            "local_authority_component_count": len(local),
            "components_evaluated": len(evaluated),
            "viable_count": len(viable),
            "evaluated_preview": evaluated[:24],
            "selected_collision_fit": selected,
            "map_sha256_after": sha256(MAP_FILE),
            "profile_sha256_after": sha256(PROFILE_FILE),
            "dirty_packages_before_pie_stop": dirty_packages(),
            "completed_utc": now(),
            "claim_limit": (
                "No-save native collision-fit automation only. PlayerStart persistence, fresh reload, MapCheck, "
                "visible grass, surface day/night, gameplay and player acceptance remain pending."
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
        require(not self.level.is_in_play_in_editor(), "PIE still active during R23 publish")
        require(dirty_packages() == {"content": [], "maps": []}, "Editor dirty after R23 PIE stop")
        self.report["provider_gate_after"] = provider_gate()
        self.report["dirty_packages_after"] = dirty_packages()
        write_json_exclusive(RESULT, self.report)
        marker = "PASS" if self.report["status"].startswith("PASS") else "BLOCKED"
        unreal.log_warning("REDMMO_R23_COLLISION_FIT_" + marker + " " + json.dumps(
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
            "map_sha256_observed": sha256(MAP_FILE) if MAP_FILE.is_file() else None,
            "profile_sha256_observed": sha256(PROFILE_FILE) if PROFILE_FILE.is_file() else None,
            "completed_utc": now(),
        })
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        if not RESULT.exists():
            write_json_exclusive(RESULT, self.report)
        unreal.log_error("REDMMO_R23_COLLISION_FIT_FAIL " + repr(error) + "\n" + traceback.format_exc())
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), "QUIT_EDITOR")

    def tick(self, _delta):
        try:
            self.frames += 1
            require(time.monotonic() - self.started < 600.0, "R23 overall timeout")
            require(time.monotonic() - self.phase_started < 300.0, "R23 phase timeout: " + self.phase)
            if self.phase == "prepare":
                self.start()
            elif self.phase == "wait_pie":
                self.bind_pie()
            elif self.phase == "settle_selected_direction":
                target = add(self.center, mul(SELECTED_DIRECTION, self.radius + VIEW_ALTITUDE_CM))
                self.pawn.set_actor_location(target, False, True)
                if self.generation_ready():
                    self.ready_frames += 1
                    if self.ready_frames >= SETTLE_FRAMES:
                        self.set_phase("evaluate")
                else:
                    self.ready_frames = 0
            elif self.phase == "evaluate":
                self.evaluate()
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
unreal.log("REDMMO_R23_COLLISION_FIT_STARTED")
