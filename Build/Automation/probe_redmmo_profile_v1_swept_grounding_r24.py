"""No-save swept Trooper grounding check at the R23 seeded land contact."""

from __future__ import annotations

import hashlib
import json
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
R23_RESULT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1CollisionFit_R23D_20260805T1130Z\result.json")
EXPECTED_R23_RESULT_SHA = "90DE04FA94048E90096F1A6204B2D2BF953228D1BF957F185BE8C35BB5AA61D6"
R20_HELPERS = Path(r"D:\RedMMOTitan\Build\Automation\apply_redmmo_profile_v1_seeded_land_start_r20.py")
EXPECTED_R20_HELPERS_SHA = "7707C56E13E9922A2F2D3ADBCE4CB7CCD917241B5F875EE631E347B5A70B83B7"
ROLLBACK = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeRedPPGProfileV1SweptGrounding_R24C_20260805T1145Z")
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1SweptGrounding_R24C_20260805T1145Z")
RESULT = DIAG / "result.json"
VIEW_ALTITUDE_CM = 100000.0
SETTLE_GENERATION_FRAMES = 180
SETTLE_GROUNDING_FRAMES = 240
CAPSULE_START_CLEARANCE_CM = 25.0
MAX_GROUND_CLEARANCE_ERROR_CM = 20.0
MAX_FINAL_SPEED_CM_S = 50.0
LOCAL_DIRECTION_DOT = 0.999999

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
require(sha256(R23_RESULT) == EXPECTED_R23_RESULT_SHA, "R23 result drift")
helper_source = R20_HELPERS.read_text(encoding="utf-8")
helper_prefix = helper_source.split("\nrequire(os.path.normcase", 1)[0]
helper_ns = {"__name__": "redmmo_r20_helpers", "__file__": str(R20_HELPERS)}
exec(compile(helper_prefix, str(R20_HELPERS), "exec"), helper_ns)

asset_path = helper_ns["asset_path"]
dirty_packages = helper_ns["dirty_packages"]
provider_gate = helper_ns["provider_gate"]
vec = helper_ns["vec"]
add = helper_ns["add"]
sub = helper_ns["sub"]
mul = helper_ns["mul"]
dot = helper_ns["dot"]
length = helper_ns["length"]
normalized = helper_ns["normalized"]
write_json_exclusive = helper_ns["write_json_exclusive"]

r23 = json.loads(R23_RESULT.read_text(encoding="utf-8"))
eligible = [item for item in r23["evaluated_preview"]
            if float(item.get("elevation_cm", -1.0e9)) >= 25000.0
            and float(item.get("surface_normal_radial_dot", -1.0)) >= 0.92]
require(eligible, "R23 exposes no contact/slope candidate")
eligible.sort(key=lambda item: -float(item["surface_normal_radial_dot"]))
R23_BEST = eligible[0]
SELECTED_DIRECTION = unreal.Vector(*R23_BEST["radial"])


def component_trace(component, start, end):
    for trace_complex in (False, True):
        raw = component.line_trace_component(start, end, trace_complex, False, False)
        if raw is None:
            continue
        require(isinstance(raw, tuple), "Unexpected component trace return: " + repr(type(raw)))
        vectors = [item for item in raw if hasattr(item, "x") and hasattr(item, "y") and hasattr(item, "z")]
        if len(vectors) >= 2 and length(vectors[1]) > 0.5:
            return {"location": vectors[0], "normal": normalized(vectors[1]), "trace_complex": trace_complex}
    return None


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
        self.capsule = None
        self.movement = None
        self.terrain = []
        self.initial_target = None
        self.contact = None
        self.report = {
            "schema": "redmmo.ppg_profile_v1.swept_grounding.r24c.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "evidence_class": "automation",
            "map": MAP,
            "map_sha256_before": EXPECTED_MAP_SHA,
            "profile_sha256_before": EXPECTED_PROFILE_SHA,
            "r23_result_sha256": EXPECTED_R23_RESULT_SHA,
            "selected_direction": vec(SELECTED_DIRECTION),
            "seed_changed": False,
            "generation_called": False,
        }

    def set_phase(self, value):
        self.phase = value
        self.phase_started = time.monotonic()
        self.frames = 0
        self.ready_frames = 0
        unreal.log("REDMMO_R24_SWEPT_GROUNDING_PHASE " + value)

    def start(self):
        require(not RESULT.exists(), "R24C result no-clobber failed")
        require(not ROLLBACK.exists(), "R24C rollback no-clobber failed")
        require(sha256(MAP_FILE) == EXPECTED_MAP_SHA, "Home map hash drift")
        require(sha256(PROFILE_FILE) == EXPECTED_PROFILE_SHA, "ProfileV1 hash drift")
        require(dirty_packages() == {"content": [], "maps": []}, "Editor started dirty")
        self.report["provider_gate_before"] = provider_gate()
        for path, expected in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected, "Protected hash drift: " + str(path))
        ROLLBACK.mkdir(parents=True, exist_ok=False)
        rollback_map = ROLLBACK / "RedMMO_PPG_HomeWorld.pre_r24c_swept_grounding.umap"
        shutil.copy2(MAP_FILE, rollback_map)
        require(sha256(rollback_map) == EXPECTED_MAP_SHA, "Rollback byte mismatch")
        write_json_exclusive(ROLLBACK / "manifest.json", {
            "schema": "redmmo.ppg_profile_v1.swept_grounding.r24c.rollback.v1",
            "captured_utc": now(),
            "source": str(MAP_FILE),
            "source_sha256": EXPECTED_MAP_SHA,
            "rollback": str(rollback_map),
            "restore": "No restore is expected because R24C is no-save; retain this exact preimage.",
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
        capsules = list(pawn.get_components_by_class(unreal.CapsuleComponent))
        movements = list(pawn.get_components_by_class(unreal.CharacterMovementComponent))
        require(capsules and movements, "PIE pawn lacks capsule or character movement")
        self.capsule = capsules[0]
        self.movement = movements[0]
        require(int(self.planet.get_editor_property("generation_seed")) == 1337, "PPG seed drift")
        self.report["pawn"] = {
            "class": pawn.get_class().get_name(),
            "capsule_radius_cm": float(self.capsule.get_scaled_capsule_radius()),
            "capsule_half_height_cm": float(self.capsule.get_scaled_capsule_half_height()),
        }
        view = add(self.center, mul(SELECTED_DIRECTION, self.radius + VIEW_ALTITUDE_CM))
        require(self.pawn.set_actor_location(view, False, True) is not False, "Transient view teleport failed")
        self.set_phase("settle_generation")

    def generation_ready(self):
        status = self.spawner.get_planet_generation_status()
        phase = str(status.get_editor_property("phase"))
        progress = float(status.get_editor_property("progress"))
        generating = bool(status.get_editor_property("is_generating"))
        self.report["generation"] = {"phase": phase, "progress": progress, "is_generating": generating}
        return "COMPLETE" in phase.upper() and progress >= 0.999 and not generating

    def place_swept(self):
        components = list(self.spawner.get_components_by_class(unreal.StaticMeshComponent))
        self.terrain = [component for component in components
                        if component.is_query_collision_enabled()
                        and component.get_editor_property("static_mesh") is not None
                        and not isinstance(component, unreal.InstancedStaticMeshComponent)]
        extent = self.noise_height + 1000000.0
        hits = []
        for component in self.terrain:
            delta = sub(component.get_world_location(), self.center)
            if length(delta) < self.radius * 0.5:
                continue
            direction = normalized(delta)
            if dot(direction, SELECTED_DIRECTION) < LOCAL_DIRECTION_DOT:
                continue
            start = add(self.center, mul(direction, self.radius + extent))
            end = add(self.center, mul(direction, self.radius - extent))
            hit = component_trace(component, start, end)
            if hit is None:
                continue
            radial = normalized(sub(hit["location"], self.center))
            normal_dot = dot(hit["normal"], radial)
            elevation = length(sub(hit["location"], self.center)) - self.radius
            if elevation >= 25000.0 and normal_dot >= 0.92:
                hits.append({
                    "component_object": component,
                    "component": component.get_path_name(),
                    "location": hit["location"],
                    "normal": hit["normal"],
                    "radial": radial,
                    "normal_dot": normal_dot,
                    "elevation_cm": elevation,
                    "trace_complex": hit["trace_complex"],
                })
        require(hits, "No native local contact survived R24 revalidation")
        hits.sort(key=lambda item: (-item["normal_dot"], abs(item["elevation_cm"] - R23_BEST["elevation_cm"])))
        self.contact = hits[0]
        half_height = self.report["pawn"]["capsule_half_height_cm"]
        self.initial_target = add(self.contact["location"], mul(
            self.contact["radial"], half_height + CAPSULE_START_CLEARANCE_CM))
        high = add(self.contact["location"], mul(self.contact["radial"], VIEW_ALTITUDE_CM))
        require(self.pawn.set_actor_location(high, False, True) is not False, "High placement failed")
        swept_return = self.pawn.set_actor_location(self.initial_target, True, False)
        actual = self.pawn.get_actor_location()
        self.report["swept_placement"] = {
            "set_actor_location_return": bool(swept_return),
            "requested_center": vec(self.initial_target),
            "actual_center_immediate": vec(actual),
            "request_error_cm": length(sub(actual, self.initial_target)),
            "contact": {
                "component": self.contact["component"],
                "location": vec(self.contact["location"]),
                "normal": vec(self.contact["normal"]),
                "radial": vec(self.contact["radial"]),
                "elevation_cm": self.contact["elevation_cm"],
                "surface_normal_radial_dot": self.contact["normal_dot"],
            },
        }
        require(length(sub(actual, self.initial_target)) <= 5.0, "Swept placement did not reach clear target")
        self.set_phase("settle_grounding")

    def evaluate_grounding(self):
        final_location = self.pawn.get_actor_location()
        final_radial = normalized(sub(final_location, self.center))
        contact_delta = sub(final_location, self.contact["location"])
        clearance = dot(contact_delta, self.contact["radial"])
        tangential_delta = sub(contact_delta, mul(self.contact["radial"], clearance))
        tangential_drift = length(tangential_delta)
        half_height = self.report["pawn"]["capsule_half_height_cm"]
        overlaps = []
        for component in self.terrain:
            try:
                if self.capsule.is_overlapping_component(component):
                    overlaps.append(component.get_path_name())
            except Exception:
                continue
        velocity = self.movement.get_editor_property("velocity")
        speed = length(velocity)
        moving_on_ground = bool(self.movement.is_moving_on_ground())
        clearance_error = abs(clearance - half_height)
        self.report["grounding"] = {
            "settle_frames": SETTLE_GROUNDING_FRAMES,
            "final_center": vec(final_location),
            "final_velocity": vec(velocity),
            "final_speed_cm_s": speed,
            "moving_on_ground": moving_on_ground,
            "ground_component": self.contact["component"],
            "ground_location": vec(self.contact["location"]),
            "ground_normal": vec(self.contact["normal"]),
            "radial_clearance_cm": clearance,
            "capsule_half_height_cm": half_height,
            "clearance_error_cm": clearance_error,
            "tangential_drift_cm": tangential_drift,
            "overlapping_terrain_components": overlaps,
            "target_to_final_cm": length(sub(final_location, self.initial_target)),
        }
        passed = moving_on_ground and speed <= MAX_FINAL_SPEED_CM_S and not overlaps and \
            clearance_error <= MAX_GROUND_CLEARANCE_ERROR_CM and tangential_drift <= 20.0
        self.report.update({
            "status": "PASS_R24C_SWEPT_CAPSULE_CLEARANCE_AND_GROUNDING_NO_SAVE" if passed else
                      "BLOCKED_R24C_SWEPT_GROUNDING_ACCEPTANCE_FAILED",
            "map_sha256_after": sha256(MAP_FILE),
            "profile_sha256_after": sha256(PROFILE_FILE),
            "dirty_packages_before_pie_stop": dirty_packages(),
            "completed_utc": now(),
            "claim_limit": (
                "No-save swept-grounding automation only. PlayerStart persistence, fresh reload, MapCheck, "
                "visible grass, day/night, broader gameplay and player acceptance remain pending."
            ),
        })
        require(self.report["map_sha256_after"] == EXPECTED_MAP_SHA, "Home map changed during R24")
        require(self.report["profile_sha256_after"] == EXPECTED_PROFILE_SHA, "ProfileV1 changed during R24")
        require(dirty_packages() == {"content": [], "maps": []}, "R24 dirtied packages")
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "Protected package changed: " + str(path))
        self.level.editor_request_end_play()
        self.set_phase("wait_pie_stop")

    def publish(self):
        require(not self.level.is_in_play_in_editor(), "PIE still active during publish")
        require(dirty_packages() == {"content": [], "maps": []}, "Editor dirty after PIE stop")
        self.report["provider_gate_after"] = provider_gate()
        self.report["dirty_packages_after"] = dirty_packages()
        write_json_exclusive(RESULT, self.report)
        marker = "PASS" if self.report["status"].startswith("PASS") else "BLOCKED"
        unreal.log_warning("REDMMO_R24_SWEPT_GROUNDING_" + marker + " " + json.dumps(
            self.report, sort_keys=True, default=str))
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), "QUIT_EDITOR")

    def fail(self, error):
        self.report.update({"status": "FAIL", "error": str(error), "traceback": traceback.format_exc(),
                            "completed_utc": now()})
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        if not RESULT.exists():
            write_json_exclusive(RESULT, self.report)
        unreal.log_error("REDMMO_R24_SWEPT_GROUNDING_FAIL " + repr(error) + "\n" + traceback.format_exc())
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), "QUIT_EDITOR")

    def tick(self, _delta):
        try:
            self.frames += 1
            require(time.monotonic() - self.started < 600.0, "R24 overall timeout")
            require(time.monotonic() - self.phase_started < 300.0, "R24 phase timeout: " + self.phase)
            if self.phase == "prepare":
                self.start()
            elif self.phase == "wait_pie":
                self.bind_pie()
            elif self.phase == "settle_generation":
                view = add(self.center, mul(SELECTED_DIRECTION, self.radius + VIEW_ALTITUDE_CM))
                self.pawn.set_actor_location(view, False, True)
                if self.generation_ready():
                    self.ready_frames += 1
                    if self.ready_frames >= SETTLE_GENERATION_FRAMES:
                        self.set_phase("place_swept")
                else:
                    self.ready_frames = 0
            elif self.phase == "place_swept":
                self.place_swept()
            elif self.phase == "settle_grounding":
                if self.frames >= SETTLE_GROUNDING_FRAMES:
                    self.set_phase("evaluate_grounding")
            elif self.phase == "evaluate_grounding":
                self.evaluate_grounding()
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
unreal.log("REDMMO_R24_SWEPT_GROUNDING_STARTED")
