"""No-save real-D3D12 test of PlayerStart-based gravity-relative camera framing.

The editor PlayerStart is rotated transiently toward the parked ship before PIE.
After the default player view is captured, PIE is stopped and the map is freshly
reloaded to discard the unsaved candidate transform.
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
EXPECTED_MAP_SHA = "0A7252E93F6F75FA7FAFAD856C7249E6964C27E34B9DD1386202080E2FD2D6CF"
EXPECTED_GAME_MODE = "/Game/RedMMO/Gameplay/Player/GM_RedPlanet_R11.GM_RedPlanet_R11_C"
EXPECTED_PAWN = "BP_RedPlanetCharacter_R11_C"
SHIP_LABEL = "RedMMO_R12_ParkedStarSparrow_VisualOnly"
ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_PlayerStartCamera_R13Candidate_20260802"
STATE = os.path.join(ROOT, "validate_redmmo_ppg_playerstart_camera_candidate_r13_state.json")
RESULT = os.path.join(ROOT, "validate_redmmo_ppg_playerstart_camera_candidate_r13_result.json")
SCREENSHOT = os.path.join(ROOT, "RedMMO_R13Candidate_default_playerstart_camera_PIE_1920x1080.png")
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


def require(value, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def atomic_json(path: str, value) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    os.replace(temporary, path)


def vec(value) -> list[float]:
    return [float(value.x), float(value.y), float(value.z)]


def sub(a, b):
    return unreal.Vector(a.x - b.x, a.y - b.y, a.z - b.z)


def mul(value, scalar: float):
    return unreal.Vector(value.x * scalar, value.y * scalar, value.z * scalar)


def dot(a, b) -> float:
    return float(a.x * b.x + a.y * b.y + a.z * b.z)


def length(value) -> float:
    return math.sqrt(dot(value, value))


def normalized(value):
    magnitude = length(value)
    require(magnitude > 1.0e-6, "Cannot normalize zero vector")
    return mul(value, 1.0 / magnitude)


def dirty_packages() -> list[str]:
    packages = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    packages += list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted({package.get_path_name() for package in packages})


def provider_gate() -> dict[str, bool]:
    result = {}
    for port in PROVIDER_PORTS:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            result[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    require(all(result.values()), "AI/MCP/provider port is listening")
    return result


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


class Candidate:
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
        self.center = None
        self.ship = None
        self.screenshot_requested = False
        self.report = {
            "schema": "redmmo.ppg_playerstart_camera.r13_candidate.real_pie.v1",
            "status": "RUNNING",
            "phase": self.phase,
            "map": MAP,
            "home_map_sha256": EXPECTED_MAP_SHA,
            "evidence_class": "real_d3d12_pie_default_camera_no_save_transient_playerstart_candidate",
            "map_saved": False,
        }

    def publish(self):
        self.report["phase"] = self.phase
        self.report["phase_elapsed_seconds"] = time.monotonic() - self.phase_started
        atomic_json(STATE, self.report)

    def set_phase(self, phase: str):
        self.phase = phase
        self.phase_started = time.monotonic()
        self.publish()
        unreal.log("REDMMO_R13_CAMERA_CANDIDATE_PHASE " + phase)

    def start(self):
        require(not os.path.exists(RESULT), "R13 candidate result no-clobber failed")
        if os.path.exists(STATE):
            os.remove(STATE)
        if os.path.exists(SCREENSHOT):
            os.remove(SCREENSHOT)
        self.handle = unreal.register_slate_post_tick_callback(self.tick)
        self.publish()

    def prepare(self):
        require(sha256(MAP_FILE) == EXPECTED_MAP_SHA, "Home-map hash drift")
        require(not dirty_packages(), f"Dirty editor before candidate: {dirty_packages()}")
        self.report["provider_ports_closed"] = provider_gate()
        require(not self.level.is_in_play_in_editor(), "PIE already active")
        editor_world = self.editor.get_editor_world()
        require(editor_world.get_path_name().split(":", 1)[0].split(".", 1)[0] == MAP, "Wrong editor map")
        actual_game_mode = editor_world.get_world_settings().get_editor_property("default_game_mode")
        require(actual_game_mode.get_path_name() == EXPECTED_GAME_MODE, f"Wrong GameMode: {actual_game_mode}")
        actors = list(unreal.EditorLevelLibrary.get_all_level_actors())
        starts = [value for value in actors if value.get_class().get_name() == "PlayerStart"]
        spawners = [value for value in actors if value.get_class().get_name() == "PlanetSpawnerBP_C"]
        ships = [value for value in actors if value.get_actor_label() == SHIP_LABEL]
        require(len(starts) == len(spawners) == len(ships) == 1, "Expected one PlayerStart, spawner, and ship")
        start, spawner, ship = starts[0], spawners[0], ships[0]
        radial_up = normalized(sub(start.get_actor_location(), spawner.get_actor_location()))
        to_ship = sub(ship.get_actor_location(), start.get_actor_location())
        tangent = sub(to_ship, mul(radial_up, dot(to_ship, radial_up)))
        tangent = normalized(tangent)
        before = start.get_actor_rotation()
        target = unreal.MathLibrary.make_rot_from_xz(tangent, radial_up)
        require(start.set_actor_rotation(target, False), "Transient PlayerStart rotation failed")
        self.report["transient_playerstart_candidate"] = {
            "before": str(before),
            "target": str(target),
            "radial_up": vec(radial_up),
            "tangent_to_ship": vec(tangent),
            "saved": False,
        }
        self.level.editor_request_begin_play()
        self.set_phase("WAIT_PIE")

    def bind(self) -> bool:
        world = self.editor.get_game_world()
        if world is None or not self.level.is_in_play_in_editor():
            return False
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        controller = unreal.GameplayStatics.get_player_controller(world, 0)
        if pawn is None or controller is None:
            return False
        require(pawn.get_class().get_name() == EXPECTED_PAWN, f"Wrong pawn: {pawn.get_class().get_name()}")
        actors = list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor))
        spawners = [value for value in actors if value.get_class().get_name() == "PlanetSpawnerBP_C"]
        ships = [value for value in actors if value.get_actor_label() == SHIP_LABEL]
        require(len(spawners) == len(ships) == 1, "PIE spawner/ship missing")
        self.world = world
        self.pawn = pawn
        self.controller = controller
        self.movement = pawn.get_editor_property("character_movement")
        self.center = spawners[0].get_actor_location()
        self.ship = ships[0]
        self.set_phase("WAIT_GENERATION")
        return True

    def generation_ready(self) -> bool:
        spawners = [
            value for value in unreal.GameplayStatics.get_all_actors_of_class(self.world, unreal.Actor)
            if value.get_class().get_name() == "PlanetSpawnerBP_C"
        ]
        status = spawners[0].get_planet_generation_status()
        phase = str(status.get_editor_property("phase"))
        progress = float(status.get_editor_property("progress"))
        generating = bool(status.get_editor_property("is_generating"))
        self.report["generation"] = {"phase": phase, "progress": progress, "is_generating": generating}
        return "COMPLETE" in phase.upper() and progress >= 0.999 and not generating

    def capture(self):
        camera_location, camera_rotation = player_view(self.controller, self.pawn)
        camera_forward = unreal.MathLibrary.get_forward_vector(camera_rotation)
        ship_direction = normalized(sub(self.ship.get_actor_location(), camera_location))
        radial_up = normalized(sub(self.pawn.get_actor_location(), self.center))
        gravity_direction = self.movement.get_gravity_direction()
        relative = unreal.GravityController.get_gravity_relative_rotation(
            self.controller.get_control_rotation(), gravity_direction
        )
        self.report["default_view"] = {
            "camera_location": vec(camera_location),
            "camera_rotation": str(camera_rotation),
            "camera_forward": vec(camera_forward),
            "camera_forward_dot_ship": dot(camera_forward, ship_direction),
            "camera_forward_dot_radial_up": dot(camera_forward, radial_up),
            "gravity_relative_control_rotation": str(relative),
            "pawn_location": vec(self.pawn.get_actor_location()),
            "ship_location": vec(self.ship.get_actor_location()),
        }
        unreal.SystemLibrary.execute_console_command(self.world, "r.SetRes 1920x1080w")
        unreal.SystemLibrary.execute_console_command(
            self.world, "HighResShot 1920x1080 filename=\"" + SCREENSHOT.replace("\\", "/") + "\""
        )
        self.screenshot_requested = True
        self.set_phase("WAIT_SCREENSHOT")

    def finish_after_reload(self):
        require(sha256(MAP_FILE) == EXPECTED_MAP_SHA, "Candidate changed home-map file")
        require(not dirty_packages(), f"Fresh reload left dirty packages: {dirty_packages()}")
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "Protected checkpoint drift: " + path)
        require(os.path.isfile(SCREENSHOT) and os.path.getsize(SCREENSHOT) > 10000, "Screenshot missing")
        view = self.report["default_view"]
        self.report["candidate_structural_gate"] = {
            "ship_in_front": view["camera_forward_dot_ship"] > 0.10,
            "not_skyward": view["camera_forward_dot_radial_up"] < 0.35,
        }
        self.report["status"] = "PASS_REAL_D3D12_NO_SAVE_PLAYERSTART_CANDIDATE_PENDING_HUMAN_VISUAL_REVIEW"
        self.report["screenshot"] = {
            "path": SCREENSHOT, "sha256": sha256(SCREENSHOT), "bytes": os.path.getsize(SCREENSHOT)
        }
        atomic_json(RESULT, self.report)
        self.publish()
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        unreal.log("REDMMO_R13_CAMERA_CANDIDATE PASS")

    def fail(self, error):
        self.report["status"] = "FAIL"
        self.report["error"] = str(error)
        self.report["traceback"] = traceback.format_exc()
        atomic_json(RESULT, self.report)
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        unreal.log_error("REDMMO_R13_CAMERA_CANDIDATE FAIL " + str(error))

    def tick(self, _delta):
        try:
            elapsed = time.monotonic() - self.phase_started
            if self.phase == "PREPARE":
                self.prepare()
            elif self.phase == "WAIT_PIE":
                require(elapsed <= 90.0, "PIE startup timeout")
                self.bind()
            elif self.phase == "WAIT_GENERATION":
                require(elapsed <= 180.0, "PPG generation timeout")
                if self.generation_ready() and elapsed >= 3.0:
                    self.capture()
            elif self.phase == "WAIT_SCREENSHOT":
                require(elapsed <= 60.0, "Screenshot timeout")
                if self.screenshot_requested and os.path.isfile(SCREENSHOT) and os.path.getsize(SCREENSHOT) > 10000:
                    self.level.editor_request_end_play()
                    self.set_phase("WAIT_PIE_END")
            elif self.phase == "WAIT_PIE_END":
                require(elapsed <= 90.0, "PIE shutdown timeout")
                if not self.level.is_in_play_in_editor() and self.editor.get_game_world() is None and elapsed >= 1.0:
                    require(unreal.EditorLoadingAndSavingUtils.load_map(MAP), "Unable to reload home map")
                    self.set_phase("WAIT_RELOAD")
            elif self.phase == "WAIT_RELOAD":
                require(elapsed <= 90.0, "Map reload timeout")
                world = self.editor.get_editor_world()
                if world is not None and world.get_path_name().split(":", 1)[0].split(".", 1)[0] == MAP and elapsed >= 1.0:
                    self.finish_after_reload()
            self.publish()
        except Exception as error:
            self.fail(error)


try:
    _REDMMO_R13_CAMERA_CANDIDATE = Candidate()
    _REDMMO_R13_CAMERA_CANDIDATE.start()
except Exception as bootstrap_error:
    atomic_json(RESULT, {
        "schema": "redmmo.ppg_playerstart_camera.r13_candidate.real_pie.v1",
        "status": "FAIL",
        "error": str(bootstrap_error),
        "traceback": traceback.format_exc(),
    })
    unreal.log_error("REDMMO_R13_CAMERA_CANDIDATE_BOOTSTRAP_FAIL " + str(bootstrap_error))
