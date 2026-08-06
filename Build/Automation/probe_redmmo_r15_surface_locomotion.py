"""No-save R15 spawn, surface, and forward-locomotion runtime probe.

The probe measures motion in the planet-relative frame so PPG world-origin
rebasing cannot masquerade as zero movement. It does not save assets or maps.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import socket
import time
import traceback

import unreal


PROJECT = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject"
MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
MAP_FILE = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
MAP_SHA = "7BA68701F4B1A96777407FC8C349D90878037917CD3212878164B9A28BB37059"
MOVE_ACTION = "/PPG/Example/Assets/Character/Input/Actions/IA_Move"
ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_R15_Playability_20260803"
RESULT = os.path.join(ROOT, "probe_redmmo_r15_surface_locomotion_result.json")
STATE = os.path.join(ROOT, "probe_redmmo_r15_surface_locomotion_state.json")
PROVIDER_PORTS = (5353, 8000, 8765)
GROUND_TIMEOUT_SECONDS = 90.0
FORWARD_TEST_SECONDS = 8.0
SAMPLE_SECONDS = (0.0, 1.0, 2.0, 4.0, 6.0, 8.0)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def atomic_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def vec(value):
    return [float(value.x), float(value.y), float(value.z)]


def dot(a, b):
    return float(a.x * b.x + a.y * b.y + a.z * b.z)


def sub(a, b):
    return unreal.Vector(a.x - b.x, a.y - b.y, a.z - b.z)


def mul(value, scalar):
    return unreal.Vector(value.x * scalar, value.y * scalar, value.z * scalar)


def add(a, b):
    return unreal.Vector(a.x + b.x, a.y + b.y, a.z + b.z)


def length(value):
    return math.sqrt(dot(value, value))


def normalized(value):
    magnitude = length(value)
    require(magnitude > 1.0e-6, "Cannot normalize zero vector")
    return mul(value, 1.0 / magnitude)


def project_tangent(value, up):
    projected = sub(value, mul(up, dot(value, up)))
    return normalized(projected)


def dirty_packages():
    values = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    values += list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted({value.get_path_name() for value in values})


def providers_closed():
    result = {}
    for port in PROVIDER_PORTS:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            result[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    return result


class Probe:
    def __init__(self):
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.phase = "PREPARE"
        self.phase_started = time.monotonic()
        self.handle = None
        self.world = self.pawn = self.controller = self.movement = None
        self.spawner = self.input_subsystem = self.move_action = None
        self.grounded_frames = 0
        self.test_started = None
        self.start_relative = self.start_direction = self.start_tangent = None
        self.sampled = set()
        self.report = {
            "schema": "redmmo.r15.surface_locomotion_probe.v1",
            "status": "RUNNING",
            "project": PROJECT,
            "map": MAP,
            "map_sha256": MAP_SHA,
            "evidence_class": "automation_real_pie_runtime_no_save",
            "write_contract": {
                "map_or_asset_save": False,
                "actor_transform_write": False,
                "input_injection": "IA_Move Y=1 only during bounded test",
            },
            "samples": [],
        }

    def publish_state(self):
        atomic_json(STATE, {
            "status": self.report.get("status"),
            "phase": self.phase,
            "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })

    def set_phase(self, value):
        self.phase = value
        self.phase_started = time.monotonic()
        self.publish_state()
        unreal.log("REDMMO_R15_LOCOMOTION_PHASE " + value)

    def start(self):
        require(not os.path.exists(RESULT), "Result no-clobber failed")
        self.handle = unreal.register_slate_post_tick_callback(self.tick)
        self.publish_state()

    def prepare(self):
        require(sha256(MAP_FILE) == MAP_SHA, "R15 home map hash drift")
        require(not dirty_packages(), f"Dirty packages before probe: {dirty_packages()}")
        gate = providers_closed()
        require(all(gate.values()), f"Provider/MCP listener active: {gate}")
        self.report["provider_ports_closed"] = gate
        require(not self.level.is_in_play_in_editor(), "PIE already active")
        world = self.editor.get_editor_world()
        current = world.get_path_name().split(":", 1)[0].split(".", 1)[0]
        require(current == MAP, f"Wrong editor map: {current}")
        self.level.editor_request_begin_play()
        self.set_phase("WAIT_PIE")

    def bind(self):
        world = self.editor.get_game_world()
        if world is None or not self.level.is_in_play_in_editor():
            return False
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        controller = unreal.GameplayStatics.get_player_controller(world, 0)
        if pawn is None or controller is None:
            return False
        actors = list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor))
        spawners = [a for a in actors if a.get_class().get_name() == "PlanetSpawnerBP_C"]
        require(len(spawners) == 1, f"Expected one PlanetSpawnerBP_C, found {len(spawners)}")
        movement = pawn.get_editor_property("character_movement")
        require(movement is not None, "CharacterMovement missing")
        subsystems = []
        for candidate in unreal.ObjectIterator(unreal.EnhancedInputLocalPlayerSubsystem):
            try:
                if candidate.get_world() == world:
                    subsystems.append(candidate)
            except Exception:
                pass
        require(len(subsystems) == 1, f"Expected one input subsystem, found {len(subsystems)}")
        move_action = unreal.load_asset(MOVE_ACTION)
        require(move_action is not None, "IA_Move missing")
        self.world, self.pawn, self.controller = world, pawn, controller
        self.spawner, self.movement = spawners[0], movement
        self.input_subsystem, self.move_action = subsystems[0], move_action
        mesh = pawn.get_editor_property("mesh")
        mesh_asset = mesh.get_editor_property("skeletal_mesh_asset")
        self.report["runtime_bind"] = {
            "pawn": pawn.get_path_name(),
            "pawn_class": pawn.get_class().get_path_name(),
            "mesh": mesh_asset.get_path_name() if mesh_asset else None,
            "spawner": self.spawner.get_path_name(),
            "initial_pawn_location": vec(pawn.get_actor_location()),
            "initial_spawner_location": vec(self.spawner.get_actor_location()),
            "max_walk_speed": float(movement.get_editor_property("max_walk_speed")),
            "max_fly_speed": float(movement.get_editor_property("max_fly_speed")),
        }
        self.set_phase("WAIT_GENERATION")
        return True

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

    def frame(self):
        pawn_location = self.pawn.get_actor_location()
        center = self.spawner.get_actor_location()
        relative = sub(pawn_location, center)
        radius = length(relative)
        direction = normalized(relative)
        velocity = self.pawn.get_velocity()
        actor_up = self.pawn.get_actor_up_vector()
        movement_mode = str(self.movement.get_editor_property("movement_mode"))
        grounded = bool(self.movement.is_moving_on_ground())
        value = {
            "pawn_location": vec(pawn_location),
            "spawner_location": vec(center),
            "relative_radius_cm": radius,
            "radial_direction": vec(direction),
            "actor_up_radial_dot": dot(normalized(actor_up), direction),
            "velocity_cm_s": vec(velocity),
            "speed_cm_s": length(velocity),
            "movement_mode": movement_mode,
            "grounded": grounded,
        }
        if self.start_direction is not None:
            cosine = max(-1.0, min(1.0, dot(self.start_direction, direction)))
            angular = math.acos(cosine)
            value["arc_displacement_cm"] = angular * radius
            value["radial_delta_cm"] = radius - length(self.start_relative)
            tangent_delta = sub(relative, self.start_relative)
            value["tangent_forward_displacement_cm"] = dot(tangent_delta, self.start_tangent)
        return value

    def begin_forward(self):
        current = self.frame()
        self.start_relative = sub(self.pawn.get_actor_location(), self.spawner.get_actor_location())
        self.start_direction = normalized(self.start_relative)
        camera_forward = unreal.MathLibrary.get_forward_vector(self.controller.get_control_rotation())
        try:
            self.start_tangent = project_tangent(camera_forward, self.start_direction)
        except Exception:
            self.start_tangent = project_tangent(self.pawn.get_actor_forward_vector(), self.start_direction)
        self.report["pre_forward"] = current
        self.report["forward_tangent"] = vec(self.start_tangent)
        self.test_started = time.monotonic()
        self.set_phase("FORWARD_TEST")

    def sample_forward(self):
        elapsed = time.monotonic() - self.test_started
        self.input_subsystem.inject_input_vector_for_action(
            self.move_action, unreal.Vector(0.0, 1.0, 0.0), [], []
        )
        for target in SAMPLE_SECONDS:
            if target not in self.sampled and elapsed >= target:
                value = self.frame()
                value["elapsed_seconds"] = elapsed
                self.report["samples"].append(value)
                self.sampled.add(target)
        if elapsed >= FORWARD_TEST_SECONDS:
            final = self.frame()
            require(len(self.report["samples"]) >= len(SAMPLE_SECONDS), "Missing timed samples")
            self.report["final"] = final
            self.report["diagnosis"] = {
                "remained_grounded": all(item["grounded"] for item in self.report["samples"]),
                "final_arc_displacement_cm": final.get("arc_displacement_cm", 0.0),
                "final_forward_displacement_cm": final.get("tangent_forward_displacement_cm", 0.0),
                "final_speed_cm_s": final["speed_cm_s"],
                "movement_decayed_to_near_zero": final["speed_cm_s"] < 25.0,
            }
            self.set_phase("REQUEST_END")

    def finish(self):
        require(sha256(MAP_FILE) == MAP_SHA, "Probe changed R15 map")
        require(not dirty_packages(), f"Probe dirtied packages: {dirty_packages()}")
        self.report["status"] = "PASS_DIAGNOSTIC_COMPLETE_NO_SAVE"
        self.report["map_sha256_after"] = sha256(MAP_FILE)
        atomic_json(RESULT, self.report)
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        atomic_json(STATE, {"status": self.report["status"], "phase": "DONE"})
        unreal.log("REDMMO_R15_LOCOMOTION_PROBE PASS")

    def fail(self, error):
        self.report.update({
            "status": "FAIL",
            "error": str(error),
            "traceback": traceback.format_exc(),
            "map_sha256_after": sha256(MAP_FILE) if os.path.isfile(MAP_FILE) else None,
        })
        atomic_json(RESULT, self.report)
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        atomic_json(STATE, {"status": "FAIL", "phase": self.phase, "error": str(error)})
        unreal.log_error("REDMMO_R15_LOCOMOTION_PROBE FAIL " + str(error))

    def tick(self, _delta):
        try:
            elapsed = time.monotonic() - self.phase_started
            if self.phase == "PREPARE":
                self.prepare()
            elif self.phase == "WAIT_PIE":
                require(elapsed <= 60.0, "Timed out waiting for PIE")
                self.bind()
            elif self.phase == "WAIT_GENERATION":
                require(elapsed <= 180.0, "Timed out waiting for PPG generation")
                if self.generation_ready():
                    self.set_phase("WAIT_GROUNDED")
            elif self.phase == "WAIT_GROUNDED":
                require(elapsed <= GROUND_TIMEOUT_SECONDS, "Timed out waiting for grounded pawn")
                current = self.frame()
                self.report["last_grounding_sample"] = current
                self.grounded_frames = self.grounded_frames + 1 if current["grounded"] else 0
                if self.grounded_frames >= 30:
                    self.begin_forward()
            elif self.phase == "FORWARD_TEST":
                self.sample_forward()
            elif self.phase == "REQUEST_END":
                self.level.editor_request_end_play()
                self.set_phase("WAIT_CLEAN_END")
            elif self.phase == "WAIT_CLEAN_END":
                require(elapsed <= 60.0, "Timed out waiting for clean PIE end")
                if not self.level.is_in_play_in_editor() and self.editor.get_game_world() is None:
                    self.finish()
            self.publish_state()
        except Exception as error:
            self.fail(error)


PROBE = Probe()
PROBE.start()
