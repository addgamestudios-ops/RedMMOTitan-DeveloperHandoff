"""Real-D3D12 PIE telemetry gate for Red MMO R11 flight controls.

The script starts PIE, waits for the generated PPG home world, and exposes a
small phase protocol in an external JSON file.  The UE 5.8 Enhanced Input
subsystem injects the same IA_Fly and IA_Move action values used by the verified
R11 project-owned mapping context.  It records radial altitude and view-forward
displacement for ascent setup, camera-directed dive/climb, explicit ascent,
explicit descent, and the return-to-walking toggle.  No package is saved.
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


MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
MAP_FILE = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
EXPECTED_MAP_SHA = "3F98136280504222E5340DB7044F0F3564E8BFFD7221C4EC2F2DF655CE2FFAEC"
EXPECTED_PAWN = "BP_RedPlanetCharacter_R11_C"
EXPECTED_GAME_MODE = "/Game/RedMMO/Gameplay/Player/GM_RedPlanet_R11.GM_RedPlanet_R11_C"
MOVE_ACTION = "/PPG/Example/Assets/Character/Input/Actions/IA_Move"
FLY_ACTION = "/PPG/Example/Assets/Character/Input/Actions/IA_Fly"
ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_Flight_R11_20260802"
STATE = os.path.join(ROOT, "validate_redmmo_ppg_flight_r11_state.json")
RESULT = os.path.join(ROOT, "validate_redmmo_ppg_flight_r11_result.json")
SCREENSHOT = os.path.join(ROOT, "RedMMO_R11_flight_descent_PIE_1920x1080.png")
PROVIDER_PORTS = (5353, 8000, 8765)
PROTECTED = {
    r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap":
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap":
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
    r"D:\RedMMOTitan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap":
        "211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7",
    r"D:\RedMMOTitanWindowsData\Rollback\BeforeCoastDatum_20260714\RedPlanetGen_50km_FusedPrototype.umap":
        "A9C42C0D1B0429DD1018F00F0D2AB8A18F66C07291611964EFF5F9710F3B0C6A",
}
MIN_RADIAL_CHANGE_CM = 500.0
MIN_DIRECTION_DOT = 0.55


def require(value, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def atomic_json(path: str, value: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    for attempt in range(40):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 39:
                raise
            time.sleep(0.025)


def vec(value) -> list[float]:
    return [float(value.x), float(value.y), float(value.z)]


def sub(a, b):
    return unreal.Vector(a.x - b.x, a.y - b.y, a.z - b.z)


def length(value) -> float:
    return math.sqrt(value.x * value.x + value.y * value.y + value.z * value.z)


def normalized(value):
    magnitude = length(value)
    require(magnitude > 1.0e-6, "Cannot normalize zero vector")
    return unreal.Vector(value.x / magnitude, value.y / magnitude, value.z / magnitude)


def dot(a, b) -> float:
    return float(a.x * b.x + a.y * b.y + a.z * b.z)


def dirty_packages() -> list[str]:
    packages = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    packages += list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted({package.get_path_name() for package in packages})


def provider_gate() -> dict[str, bool]:
    output = {}
    for port in PROVIDER_PORTS:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            output[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    require(all(output.values()), "AI/MCP/provider port is listening")
    return output


def player_view(controller, pawn):
    location = pawn.get_actor_location()
    rotation = controller.get_control_rotation()
    getter = getattr(controller, "get_player_view_point", None)
    if callable(getter):
        raw = getter()
        if isinstance(raw, tuple):
            for item in raw:
                if isinstance(item, unreal.Vector):
                    location = item
                elif isinstance(item, unreal.Rotator):
                    rotation = item
    return location, rotation


class FlightValidation:
    def __init__(self):
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.handle = None
        self.phase = "PREPARE"
        self.phase_started = time.monotonic()
        self.world = None
        self.pawn = None
        self.controller = None
        self.movement = None
        self.input_subsystem = None
        self.move_action = None
        self.fly_action = None
        self.center = None
        self.phase_location = None
        self.phase_altitude = None
        self.phase_forward = None
        self.screenshot_issued = False
        self.report = {
            "schema": "redmmo.ppg_flight.r11.real_pie.v1",
            "status": "RUNNING",
            "phase": self.phase,
            "map": MAP,
            "home_map_sha256": EXPECTED_MAP_SHA,
            "evidence_class": "real_d3d12_pie_enhanced_input_action_injection_and_motion_telemetry",
            "input_provenance": {
                "mapping_context": "/Game/RedMMO/Gameplay/Input/IMC_RedPlanet_R11",
                "physical_key_bindings_static_verified": {
                    "toggle_flight": "F -> IA_Fly",
                    "forward": "W -> IA_Move Y+",
                    "ascend": "Space -> IA_Move Z+",
                    "descend": "LeftControl -> IA_Move Z- via SwizzleAxis+Negate",
                },
                "runtime_driver": "UE 5.8 EnhancedInputLocalPlayerSubsystem action injection",
            },
            "tests": {},
            "map_saved_by_validation": False,
        }

    def publish(self):
        self.report["phase"] = self.phase
        self.report["phase_elapsed_seconds"] = time.monotonic() - self.phase_started
        if self.pawn is not None and self.center is not None:
            location = self.pawn.get_actor_location()
            self.report["live"] = {
                "pawn_location": vec(location),
                "radial_altitude_proxy_cm": length(sub(location, self.center)),
                "is_flying": bool(self.movement.is_flying()) if self.movement else None,
                "control_rotation": str(self.controller.get_control_rotation()) if self.controller else None,
            }
        atomic_json(STATE, self.report)

    def set_phase(self, value: str):
        self.phase = value
        self.phase_started = time.monotonic()
        self.phase_location = self.pawn.get_actor_location() if self.pawn else None
        self.phase_altitude = length(sub(self.phase_location, self.center)) if self.pawn else None
        if self.controller and self.pawn:
            _view_location, rotation = player_view(self.controller, self.pawn)
            self.phase_forward = unreal.MathLibrary.get_forward_vector(rotation)
        self.publish()
        unreal.log("REDMMO_R11_FLIGHT_PHASE " + value)

    def phase_motion(self):
        location = self.pawn.get_actor_location()
        displacement = sub(location, self.phase_location)
        magnitude = length(displacement)
        radial = length(sub(location, self.center))
        direction_dot = dot(normalized(displacement), normalized(self.phase_forward)) if magnitude > 1.0 else 0.0
        return {
            "start_location": vec(self.phase_location),
            "end_location": vec(location),
            "displacement_cm": magnitude,
            "radial_start_cm": self.phase_altitude,
            "radial_end_cm": radial,
            "radial_delta_cm": radial - self.phase_altitude,
            "view_forward": vec(self.phase_forward),
            "movement_dot_view_forward": direction_dot,
        }

    def start(self):
        require(not os.path.exists(RESULT), "R11 PIE result no-clobber failed")
        if os.path.exists(STATE):
            os.remove(STATE)
        if os.path.exists(SCREENSHOT):
            os.remove(SCREENSHOT)
        self.handle = unreal.register_slate_post_tick_callback(self.tick)
        self.publish()
        unreal.log("REDMMO_R11_FLIGHT_VALIDATION_BOOTSTRAPPED")

    def prepare(self):
        require(sha256(MAP_FILE) == EXPECTED_MAP_SHA, "R11 home map hash drift")
        require(not dirty_packages(), f"Dirty editor before PIE: {dirty_packages()}")
        require(provider_gate(), "Provider gate failed")
        require(not self.level.is_in_play_in_editor(), "PIE already active")
        editor_world = unreal.EditorLevelLibrary.get_editor_world()
        require(editor_world.get_path_name().split(":", 1)[0].split(".", 1)[0] == MAP, "Wrong editor map")
        actual_game_mode = editor_world.get_world_settings().get_editor_property("default_game_mode")
        require(actual_game_mode.get_path_name() == EXPECTED_GAME_MODE, f"Wrong GameMode: {actual_game_mode}")
        self.report["provider_ports_closed"] = provider_gate()
        self.level.editor_request_begin_play()
        self.set_phase("WAIT_PIE_WORLD")

    def bind_pie(self) -> bool:
        world = self.editor.get_game_world()
        if world is None or not self.level.is_in_play_in_editor():
            return False
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        controller = unreal.GameplayStatics.get_player_controller(world, 0)
        if pawn is None or controller is None:
            return False
        spawners = [
            actor for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor)
            if actor.get_class().get_name() == "PlanetSpawnerBP_C"
        ]
        require(len(spawners) == 1, f"Expected one PPG spawner, found {len(spawners)}")
        require(pawn.get_class().get_name() == EXPECTED_PAWN, f"Wrong PIE pawn: {pawn.get_class().get_name()}")
        movement = pawn.get_editor_property("character_movement")
        require(movement is not None, "CharacterMovement missing")
        subsystem_candidates = []
        for candidate in unreal.ObjectIterator(unreal.EnhancedInputLocalPlayerSubsystem):
            try:
                if candidate.get_world() == world:
                    subsystem_candidates.append(candidate)
            except Exception:
                continue
        require(
            len(subsystem_candidates) == 1,
            "Expected exactly one PIE EnhancedInputLocalPlayerSubsystem; found "
            + str([item.get_path_name() for item in subsystem_candidates]),
        )
        subsystem = subsystem_candidates[0]
        required_methods = (
            "inject_input_vector_for_action",
            "start_continuous_input_injection_for_action",
            "stop_continuous_input_injection_for_action",
        )
        for method_name in required_methods:
            require(callable(getattr(subsystem, method_name, None)), "Missing Enhanced Input API: " + method_name)
        move_action = unreal.load_asset(MOVE_ACTION)
        fly_action = unreal.load_asset(FLY_ACTION)
        require(move_action is not None, "IA_Move missing")
        require(fly_action is not None, "IA_Fly missing")
        self.world = world
        self.pawn = pawn
        self.controller = controller
        self.movement = movement
        self.input_subsystem = subsystem
        self.move_action = move_action
        self.fly_action = fly_action
        self.center = spawners[0].get_actor_location()
        self.report["pie_contract"] = {
            "pawn_class": pawn.get_class().get_path_name(),
            "controller_class": controller.get_class().get_path_name(),
            "controller_has_input_key_api": "input_key" in dir(controller),
            "movement_component": movement.get_path_name(),
            "initial_location": vec(pawn.get_actor_location()),
            "initial_radial_altitude_proxy_cm": length(sub(pawn.get_actor_location(), self.center)),
            "enhanced_input_subsystem": subsystem.get_path_name(),
            "enhanced_input_subsystem_outer": (
                subsystem.get_outer().get_path_name() if subsystem.get_outer() else None
            ),
            "runtime_action_injection_methods": list(required_methods),
            "move_action": move_action.get_path_name(),
            "fly_action": fly_action.get_path_name(),
        }
        self.set_phase("WAIT_GENERATION")
        return True

    def generation_ready(self) -> bool:
        spawners = [
            actor for actor in unreal.GameplayStatics.get_all_actors_of_class(self.world, unreal.Actor)
            if actor.get_class().get_name() == "PlanetSpawnerBP_C"
        ]
        method = getattr(spawners[0], "get_planet_generation_status", None)
        require(callable(method), "PPG generation status API unavailable")
        status = method()
        phase = str(status.get_editor_property("phase"))
        progress = float(status.get_editor_property("progress"))
        generating = bool(status.get_editor_property("is_generating"))
        self.report["generation"] = {"phase": phase, "progress": progress, "is_generating": generating}
        return "COMPLETE" in phase.upper() and progress >= 0.999 and not generating

    def request_rotation(self, pitch: float):
        before = self.controller.get_control_rotation()
        gravity_direction = self.movement.get_gravity_direction()
        relative_before = unreal.GravityController.get_gravity_relative_rotation(
            before, gravity_direction
        )
        relative_target = unreal.Rotator(
            roll=0.0,
            pitch=float(pitch),
            yaw=float(relative_before.yaw),
        )
        world_target = unreal.GravityController.get_gravity_world_rotation(
            relative_target, gravity_direction
        )
        self.controller.set_control_rotation(world_target)
        actual = self.controller.get_control_rotation()
        actual_relative = unreal.GravityController.get_gravity_relative_rotation(
            actual, gravity_direction
        )
        require(
            abs(float(actual_relative.pitch) - float(pitch)) <= 1.0,
            "Gravity-relative pitch request failed: "
            f"requested={pitch}, actual_relative={actual_relative}, actual_world={actual}",
        )
        self.report.setdefault("requested_rotations", []).append(
            {
                "relative_pitch": pitch,
                "relative_yaw": float(relative_before.yaw),
                "gravity_direction": vec(gravity_direction),
                "actual_relative": str(actual_relative),
                "actual_world": str(actual),
            }
        )

    def inject_action(self, action, value):
        self.input_subsystem.inject_input_vector_for_action(action, value, [], [])

    def inject_move(self, x: float = 0.0, y: float = 0.0, z: float = 0.0):
        self.inject_action(self.move_action, unreal.Vector(x, y, z))

    def inject_fly_toggle(self):
        self.inject_action(self.fly_action, unreal.Vector(1.0, 0.0, 0.0))

    def finish(self):
        require(sha256(MAP_FILE) == EXPECTED_MAP_SHA, "PIE changed home map")
        require(not dirty_packages(), f"PIE dirtied packages: {dirty_packages()}")
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "Protected checkpoint drift: " + path)
        self.report["status"] = "PASS_REAL_D3D12_PIE_FLIGHT_CONTROLS"
        self.report["screenshot"] = {
            "path": SCREENSHOT,
            "sha256": sha256(SCREENSHOT),
            "bytes": os.path.getsize(SCREENSHOT),
        }
        atomic_json(RESULT, self.report)
        self.publish()
        self.level.editor_request_end_play()
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        unreal.log("REDMMO_R11_FLIGHT_VALIDATION_PASS")

    def fail(self, error):
        self.report["status"] = "FAIL"
        self.report["error"] = str(error)
        self.report["traceback"] = traceback.format_exc()
        atomic_json(RESULT, self.report)
        self.publish()
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        unreal.log_error("REDMMO_R11_FLIGHT_VALIDATION_FAIL " + str(error))

    def tick(self, _delta):
        try:
            elapsed = time.monotonic() - self.phase_started
            if self.phase == "PREPARE":
                self.prepare()
            elif self.phase == "WAIT_PIE_WORLD":
                require(elapsed <= 90.0, "PIE world startup timeout")
                self.bind_pie()
            elif self.phase == "WAIT_GENERATION":
                require(elapsed <= 180.0, "PPG generation timeout")
                if self.generation_ready() and elapsed >= 3.0:
                    self.inject_fly_toggle()
                    self.set_phase("WAIT_F_TOGGLE")
            elif self.phase == "WAIT_F_TOGGLE":
                require(elapsed <= 120.0, "F flight-toggle input timeout")
                if self.movement.is_flying():
                    self.set_phase("ASCEND_SETUP_SPACE")
            elif self.phase == "ASCEND_SETUP_SPACE":
                require(elapsed <= 120.0, "Space ascent-setup timeout")
                self.inject_move(z=1.0)
                motion = self.phase_motion()
                if motion["radial_delta_cm"] >= MIN_RADIAL_CHANGE_CM:
                    self.report["tests"]["space_ascent_setup"] = motion
                    self.request_rotation(-35.0)
                    self.set_phase("DIVE_W")
            elif self.phase == "DIVE_W":
                require(elapsed <= 120.0, "Camera-directed W dive timeout")
                self.inject_move(y=1.0)
                motion = self.phase_motion()
                if motion["radial_delta_cm"] <= -MIN_RADIAL_CHANGE_CM:
                    require(motion["movement_dot_view_forward"] >= MIN_DIRECTION_DOT, f"Dive did not follow camera: {motion}")
                    self.report["tests"]["camera_directed_dive_w"] = motion
                    self.request_rotation(35.0)
                    self.set_phase("CLIMB_W")
            elif self.phase == "CLIMB_W":
                require(elapsed <= 120.0, "Camera-directed W climb timeout")
                self.inject_move(y=1.0)
                motion = self.phase_motion()
                if motion["radial_delta_cm"] >= MIN_RADIAL_CHANGE_CM:
                    require(motion["movement_dot_view_forward"] >= MIN_DIRECTION_DOT, f"Climb did not follow camera: {motion}")
                    self.report["tests"]["camera_directed_climb_w"] = motion
                    self.request_rotation(0.0)
                    self.set_phase("ASCEND_SPACE")
            elif self.phase == "ASCEND_SPACE":
                require(elapsed <= 120.0, "Explicit Space ascent timeout")
                self.inject_move(z=1.0)
                motion = self.phase_motion()
                if motion["radial_delta_cm"] >= MIN_RADIAL_CHANGE_CM:
                    self.report["tests"]["explicit_space_ascent"] = motion
                    self.set_phase("DESCEND_LEFT_CONTROL")
            elif self.phase == "DESCEND_LEFT_CONTROL":
                require(elapsed <= 120.0, "Explicit LeftControl descent timeout")
                self.inject_move(z=-1.0)
                motion = self.phase_motion()
                if motion["radial_delta_cm"] <= -MIN_RADIAL_CHANGE_CM:
                    self.report["tests"]["explicit_left_control_descent"] = motion
                    unreal.SystemLibrary.execute_console_command(
                        self.world,
                        'HighResShot filename="{}" 1920x1080'.format(SCREENSHOT.replace("\\", "/")),
                    )
                    self.screenshot_issued = True
                    self.set_phase("WAIT_SCREENSHOT")
            elif self.phase == "WAIT_SCREENSHOT":
                require(elapsed <= 60.0, "Flight screenshot timeout")
                if os.path.isfile(SCREENSHOT) and os.path.getsize(SCREENSHOT) > 0:
                    self.inject_fly_toggle()
                    self.set_phase("WAIT_F_RETURN_WALKING")
            elif self.phase == "WAIT_F_RETURN_WALKING":
                require(elapsed <= 120.0, "F return-to-walking timeout")
                if not self.movement.is_flying():
                    self.report["tests"]["return_to_walking"] = {
                        "movement_mode": str(self.movement.get_editor_property("movement_mode")),
                        "location": vec(self.pawn.get_actor_location()),
                    }
                    self.finish()
            self.publish()
        except Exception as error:
            self.fail(error)


try:
    _REDMMO_R11_FLIGHT_VALIDATION = FlightValidation()
    _REDMMO_R11_FLIGHT_VALIDATION.start()
except Exception as bootstrap_error:
    atomic_json(RESULT, {
        "schema": "redmmo.ppg_flight.r11.real_pie.v1",
        "status": "FAIL",
        "error": str(bootstrap_error),
        "traceback": traceback.format_exc(),
    })
    unreal.log_error("REDMMO_R11_FLIGHT_VALIDATION_BOOTSTRAP_FAIL " + str(bootstrap_error))
