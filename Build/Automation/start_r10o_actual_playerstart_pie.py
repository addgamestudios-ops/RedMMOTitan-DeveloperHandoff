"""Start, attest, and leave visible R10O PIE at the actual PlayerStart."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import socket
import struct
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
HOME_MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
HOME_FILE = PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
EXPECTED_HOME = "C489B6000B359A7B52FBE7FD50A72A76232020DBC9A015DFC61CA2FB1120C46F"
R10N = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N"
R10O = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10O"
TARGET_PLANET = R10O + "/DA_PPG_HomeWorld_StylizedBinding_R10O"
TARGET_GRASS_MESHES = {
    R10N + "/Meshes/SM_GrassChunk_DenseTall_A_R10N",
    R10N + "/Meshes/SM_GrassChunk_DenseTall_B_R10N",
}
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_HomePresentation_R10O_20260802_183909")
RESULT = DIAG / "start_r10o_actual_playerstart_pie_result.json"
PNG = DIAG / "RedMMO_Home_R10O_actual_PlayerStart_ground_view_PIE_1920x1080.png"
EXPECTED_LOG = DIAG / "start_r10o_actual_playerstart_pie.log"
VERIFY = DIAG / "verify_r10o_fresh_reload_result.json"
VERIFY_GUARD = DIAG / "run_r10o_verify_guard_result.json"
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
    path = value.get_path_name().split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def vec(value):
    return [float(value.x), float(value.y), float(value.z)]


def sub(a, b):
    return unreal.Vector(a.x - b.x, a.y - b.y, a.z - b.z)


def length(value):
    return math.sqrt(value.x * value.x + value.y * value.y + value.z * value.z)


def normalized(value):
    magnitude = length(value)
    require(magnitude > 1.0e-6, "Cannot normalize zero vector")
    return unreal.Vector(value.x / magnitude, value.y / magnitude, value.z / magnitude)


def dot(a, b):
    return a.x * b.x + a.y * b.y + a.z * b.z


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
        records.append({"port": port, "closed": code != 0})
    require(all(item["closed"] for item in records), "Provider listener active")
    return records


def command_log():
    command = str(unreal.SystemLibrary.get_command_line())
    match = re.search(r'(?i)-abslog=(?:"([^"]+)"|(\S+))', command)
    return Path((match.group(1) or match.group(2)) if match else EXPECTED_LOG)


def read_png_size(path):
    with Path(path).open("rb") as stream:
        header = stream.read(24)
    require(header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR", "Screenshot is not PNG")
    return list(struct.unpack(">II", header[16:24]))


def write_result(payload):
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with RESULT.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def player_view(controller, pawn):
    location = pawn.get_actor_location()
    rotation = pawn.get_actor_rotation()
    method = getattr(controller, "get_player_view_point", None)
    if callable(method):
        raw = method()
        if isinstance(raw, tuple):
            for item in raw:
                if isinstance(item, unreal.Vector):
                    location = item
                elif isinstance(item, unreal.Rotator):
                    rotation = item
    return location, rotation


class Session:
    def __init__(self):
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.handle = None
        self.state = "prepare"
        self.state_started = time.monotonic()
        self.frames = 0
        self.ready_frames = 0
        self.editor_direction = None
        self.log_path = None
        self.log_offset = 0
        self.pie_spawner = None
        self.pie_world = None
        self.pawn = None
        self.controller = None
        self.report = {
            "schema": "redmmo.ppg_home_presentation.r10o.actual_playerstart_pie.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "map": HOME_MAP,
            "home_map_sha256": EXPECTED_HOME,
            "evidence_class": "real_d3d12_pie_actual_playerstart_ground_facing",
            "pawn_moved_by_validation": False,
            "view_rotated_by_validation": True,
            "map_saved_by_validation": False,
            "human_visual_acceptance": False,
        }

    def start(self):
        self.handle = unreal.register_slate_post_tick_callback(self.tick)
        unreal.log("REDMMO_R10O_PLAYERSTART_VALIDATION_BOOTSTRAPPED")

    def stop_callback(self):
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None

    def phase(self, state):
        self.state = state
        self.state_started = time.monotonic()
        self.frames = 0
        self.ready_frames = 0
        unreal.log("REDMMO_R10O_PLAYERSTART_PHASE " + state)

    def editor_contract(self):
        require(HOME_FILE.is_file() and sha256(HOME_FILE) == EXPECTED_HOME, "R10O home hash drift")
        verify = json.loads(VERIFY.read_text(encoding="utf-8"))
        guard = json.loads(VERIFY_GUARD.read_text(encoding="utf-8"))
        require(verify.get("status") == "PASS_FRESH_RELOAD_AND_MAPCHECK_PENDING_ACTUAL_PLAYERSTART_PIE", "R10O reload evidence missing")
        require(guard.get("status") == "PASS_FRESH_RELOAD_MAPCHECK_ZERO_OVERFLOW_PENDING_ACTUAL_PLAYERSTART_PIE", "R10O zero-overflow reload gate missing")
        for path, expected in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected, "Protected drift: " + str(path))
        self.report["provider_gate"] = provider_gate()
        require(not dirty_packages(), "Editor started dirty")
        world = unreal.EditorLevelLibrary.get_editor_world()
        require(world is not None, "Editor world unavailable")
        world_path = world.get_path_name().split(":", 1)[0].split(".", 1)[0]
        require(world_path == HOME_MAP, "Wrong map open: " + world_path)
        require(self.editor.get_game_world() is None and not self.level.is_in_play_in_editor(), "PIE already active")
        actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
        spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        starts = [actor for actor in actors if actor.get_class().get_name() == "PlayerStart"]
        require(len(actors) == 12 and len(spawners) == 1 and len(starts) == 1, "Editor actor contract drift")
        require(asset_path(spawners[0].get_editor_property("planet_data")) == TARGET_PLANET, "R10O PlanetData is not bound")
        center = spawners[0].get_actor_location()
        start = starts[0].get_actor_location()
        self.editor_direction = normalized(sub(start, center))
        self.report["editor_contract"] = {
            "actor_count": len(actors),
            "planet_data": TARGET_PLANET,
            "player_start_location": vec(start),
            "planet_center": vec(center),
            "player_start_radial_direction": vec(self.editor_direction),
        }
        self.log_path = command_log()
        require(self.log_path.is_file(), "PIE log unavailable")
        self.log_offset = self.log_path.stat().st_size
        unreal.log("REDMMO_R10O_PLAYERSTART_PIE_BEGIN")
        self.level.editor_request_begin_play()
        self.phase("wait_pie_world")

    def find_pie_contract(self):
        world = self.editor.get_game_world()
        if world is None or not self.level.is_in_play_in_editor():
            return False
        actors = list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor))
        spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        starts = [actor for actor in actors if actor.get_class().get_name() == "PlayerStart"]
        if len(spawners) != 1 or len(starts) != 1:
            return False
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        controller = unreal.GameplayStatics.get_player_controller(world, 0)
        if pawn is None or controller is None:
            return False
        require(asset_path(spawners[0].get_editor_property("planet_data")) == TARGET_PLANET, "PIE PlanetData binding drift")
        center = spawners[0].get_actor_location()
        start_location = starts[0].get_actor_location()
        pawn_location = pawn.get_actor_location()
        start_direction = normalized(sub(start_location, center))
        pawn_direction = normalized(sub(pawn_location, center))
        start_dot = dot(start_direction, self.editor_direction)
        pawn_dot = dot(pawn_direction, self.editor_direction)
        pawn_to_start = length(sub(pawn_location, start_location))
        require(start_dot >= 0.999999 and pawn_dot >= 0.999999, "PIE pawn is not at the actual PlayerStart radial region")
        require(pawn_to_start <= 1000.0, "PIE pawn is more than 10 m from PlayerStart")
        view_location, view_rotation = player_view(controller, pawn)
        view_dot = dot(normalized(sub(view_location, center)), self.editor_direction)
        require(view_dot >= 0.999999, "PIE viewpoint is not at the actual PlayerStart radial region")
        self.pie_world = world
        self.pie_spawner = spawners[0]
        self.pawn = pawn
        self.controller = controller
        self.report["pie_playerstart_contract"] = {
            "pawn_class": pawn.get_class().get_name(),
            "pawn_location": vec(pawn_location),
            "pawn_distance_from_player_start_cm": pawn_to_start,
            "view_location": vec(view_location),
            "view_rotation_before_ground_view": [float(view_rotation.pitch), float(view_rotation.yaw), float(view_rotation.roll)],
            "editor_to_pie_start_direction_dot": start_dot,
            "editor_to_pawn_direction_dot": pawn_dot,
            "editor_to_view_direction_dot": view_dot,
        }
        self.phase("wait_generation")
        return True

    def generation_status(self):
        method = getattr(self.pie_spawner, "get_planet_generation_status", None)
        require(callable(method), "PIE planet generation status unavailable")
        status = method()
        phase = str(status.get_editor_property("phase"))
        generating = bool(status.get_editor_property("is_generating"))
        progress = float(status.get_editor_property("progress"))
        return {"phase": phase, "is_generating": generating, "progress": progress, "ready": "COMPLETE" in phase.upper() and not generating and progress >= 0.999}

    def collect_foliage_components(self):
        foliage_actor = self.pie_spawner.get_foliage_actor()
        require(foliage_actor is not None, "PIE PPG foliage actor unavailable")
        components = list(foliage_actor.get_components_by_class(unreal.StaticMeshComponent))
        seen_grass = set()
        for component in components:
            path = asset_path(component.get_editor_property("static_mesh"))
            if path in TARGET_GRASS_MESHES:
                seen_grass.add(path)
        require(seen_grass == TARGET_GRASS_MESHES, "Both R10N grass mesh components are not present in R10O PIE")
        self.report["pie_foliage"] = {
            "foliage_actor": foliage_actor.get_path_name(),
            "static_mesh_component_count": len(components),
            "grass_meshes_present": sorted(seen_grass),
            "instance_count_limit": "GPU foliage instance count is not exposed to Unreal Python",
        }

    def orient_ground_view(self):
        before_location = self.pawn.get_actor_location()
        _view_location, before_rotation = player_view(self.controller, self.pawn)
        setter = getattr(self.controller, "set_control_rotation", None)
        require(callable(setter), "PlayerController control rotation setter unavailable")
        requested = unreal.Rotator(-22.0, float(before_rotation.yaw), 0.0)
        setter(requested)
        after_location = self.pawn.get_actor_location()
        require(length(sub(after_location, before_location)) <= 1.0, "Ground-view rotation moved the pawn")
        self.report["ground_view"] = {
            "requested_control_rotation": [float(requested.pitch), float(requested.yaw), float(requested.roll)],
            "pawn_displacement_cm": length(sub(after_location, before_location)),
        }
        self.phase("settle_ground_view")

    def issue_screenshot(self):
        require(not PNG.exists(), "Screenshot no-clobber failed")
        view_location, view_rotation = player_view(self.controller, self.pawn)
        self.report["ground_view"]["actual_view_location"] = vec(view_location)
        self.report["ground_view"]["actual_view_rotation"] = [float(view_rotation.pitch), float(view_rotation.yaw), float(view_rotation.roll)]
        unreal.SystemLibrary.execute_console_command(
            self.pie_world,
            'HighResShot filename="{}" 1920x1080'.format(str(PNG).replace("\\", "/")),
        )
        unreal.log("REDMMO_R10O_PLAYERSTART_GROUND_SCREENSHOT_ISSUED")
        self.phase("wait_screenshot")

    def finish(self):
        require(PNG.is_file() and PNG.stat().st_size > 0, "PIE screenshot missing")
        require(read_png_size(PNG) == [1920, 1080], "Unexpected PIE screenshot dimensions")
        with self.log_path.open("rb") as stream:
            stream.seek(min(self.log_offset, self.log_path.stat().st_size))
            log_slice = stream.read().decode("utf-8", errors="replace")
        overflows = re.findall(r"PPG foliage output overflowed: generated (\d+) records, retained (\d+)", log_slice)
        generations = re.findall(r"Planet generation completed in ([0-9.]+) ms with ([0-9]+) chunks", log_slice)
        require(generations, "No actual-PIE PPG completion marker")
        require(not overflows, "Actual PlayerStart PIE still overflows the shared foliage pool")
        require(sha256(HOME_FILE) == EXPECTED_HOME and not dirty_packages(), "PIE changed or dirtied the home map")
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "PIE changed protected content: " + str(path))
        self.report.update({
            "status": "PASS_REAL_GPU_ACTUAL_PLAYERSTART_ZERO_OVERFLOW_PIE_READY_PENDING_HUMAN_REVIEW",
            "completed_utc": now(),
            "generation": {"time_ms": float(generations[-1][0]), "chunks": int(generations[-1][1]), "foliage_overflow_count": 0},
            "screenshot": {"path": str(PNG), "sha256": sha256(PNG), "bytes": PNG.stat().st_size, "dimensions": [1920, 1080]},
            "pie_left_open_for_user": True,
        })
        write_result(self.report)
        unreal.log("REDMMO_R10O_PLAYERSTART_PIE_READY")
        self.stop_callback()

    def fail(self, error):
        self.report.update({"status": "FAIL", "completed_utc": now(), "error": str(error), "traceback": traceback.format_exc()})
        if not RESULT.exists():
            write_result(self.report)
        unreal.log_error("REDMMO_R10O_PLAYERSTART_PIE_FAIL " + str(error))
        self.stop_callback()

    def tick(self, _delta):
        try:
            self.frames += 1
            if self.state == "prepare":
                self.editor_contract()
            elif self.state == "wait_pie_world":
                require(time.monotonic() - self.state_started <= 90.0, "PIE startup timeout")
                self.find_pie_contract()
            elif self.state == "wait_generation":
                require(time.monotonic() - self.state_started <= 180.0, "PIE generation timeout")
                status = self.generation_status()
                self.report["pie_generation_status"] = status
                if status["ready"]:
                    self.ready_frames += 1
                    if self.ready_frames >= 180:
                        self.collect_foliage_components()
                        self.orient_ground_view()
                else:
                    self.ready_frames = 0
            elif self.state == "settle_ground_view":
                require(time.monotonic() - self.state_started <= 30.0, "Ground-view settle timeout")
                if self.frames >= 180:
                    self.issue_screenshot()
            elif self.state == "wait_screenshot":
                require(time.monotonic() - self.state_started <= 60.0, "PIE screenshot timeout")
                if PNG.is_file() and PNG.stat().st_size > 0 and self.frames >= 30:
                    self.finish()
        except Exception as error:
            self.fail(error)


try:
    _SESSION = Session()
    _SESSION.start()
except Exception as bootstrap_error:
    payload = {
        "schema": "redmmo.ppg_home_presentation.r10o.actual_playerstart_pie.v1",
        "status": "FAIL",
        "started_utc": now(),
        "completed_utc": now(),
        "error": str(bootstrap_error),
        "traceback": traceback.format_exc(),
    }
    if not RESULT.exists():
        write_result(payload)
    unreal.log_error("REDMMO_R10O_PLAYERSTART_PIE_BOOTSTRAP_FAIL " + str(bootstrap_error))
