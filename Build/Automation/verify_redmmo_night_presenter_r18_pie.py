"""Fresh-reload, MapCheck, and matched D3D12 PIE proof for R18."""

from __future__ import annotations

import hashlib
import json
import socket
import struct
import time
import traceback
from pathlib import Path

import unreal


MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
MAP_FILE = Path("D:/RedMMOTitanWindowsData/Projects/RedMMO/Content/RedMMO/Maps/RedMMO_PPG_HomeWorld.umap")
EXPECTED_MAP_SHA = "6B45B423ED59BD8906A05CF35E7349C70282154DE2CE4723D41E0C16380F88D9"
DIAG = Path("D:/RedMMOTitanWindowsData/Diagnostics/RedMMO_NightPresenter_R18_20260805T0940Z")
RESULT = DIAG / "verify_result_r02.json"
CAPTURES = {
    "surface_day": DIAG / "R18_R02_surface_day_1280x720.png",
    "surface_night": DIAG / "R18_R02_surface_night_1280x720.png",
    "orbit_night": DIAG / "R18_R02_orbit_night_1280x720.png",
}
PRESENTER_LABEL = "RED_NightPresenter_R18"
PROTECTED = {
    Path("D:/RedMMOTitan/Content/RedMMO/Maps/RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path("D:/RedMMOTitan/Content/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}
PORTS = (11111, 5353, 8000, 8765)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def vec(value):
    return [float(value.x), float(value.y), float(value.z)]


def sub(a, b):
    return unreal.Vector(a.x - b.x, a.y - b.y, a.z - b.z)


def add(a, b):
    return unreal.Vector(a.x + b.x, a.y + b.y, a.z + b.z)


def mul(a, scale):
    return unreal.Vector(a.x * scale, a.y * scale, a.z * scale)


def length(value):
    return (value.x * value.x + value.y * value.y + value.z * value.z) ** 0.5


def normalized(value):
    magnitude = length(value)
    require(magnitude > 0.001, "Zero vector")
    return mul(value, 1.0 / magnitude)


def dot(a, b):
    return a.x * b.x + a.y * b.y + a.z * b.z


def cross(a, b):
    return unreal.Vector(a.y * b.z - a.z * b.y,
                         a.z * b.x - a.x * b.z,
                         a.x * b.y - a.y * b.x)


def tangent_for(radial):
    axis = unreal.Vector(0.0, 0.0, 1.0)
    if abs(dot(radial, axis)) > 0.9:
        axis = unreal.Vector(0.0, 1.0, 0.0)
    return normalized(cross(radial, axis))


def package_path(value):
    if value is None:
        return ""
    path = value.get_path_name()
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def dirty_packages():
    content = sorted(package_path(value) for value in
                     unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    maps = sorted(package_path(value) for value in
                  unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return {"content": [value for value in content if value],
            "maps": [value for value in maps if value]}


def provider_gate():
    records = []
    for port in PORTS:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.2)
        try:
            code = probe.connect_ex(("127.0.0.1", port))
        finally:
            probe.close()
        records.append({"port": port, "closed": code != 0})
    require(all(record["closed"] for record in records), "Provider listener active")
    return records


def png_size(path):
    with Path(path).open("rb") as stream:
        header = stream.read(24)
    require(header[:8] == b"\x89PNG\r\n\x1a\n", "Not PNG: " + str(path))
    return list(struct.unpack(">II", header[16:24]))


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
        self.phase_name = "prepare"
        self.phase_started = time.monotonic()
        self.frames = 0
        self.report = {"status": "RUNNING", "map": MAP, "rhi": "D3D12"}
        self.world = None
        self.pawn = None
        self.controller = None
        self.spawner = None
        self.presenter = None
        self.sun = None
        self.center = None
        self.radial = None
        self.original_sun_rotation = None
        self.original_pawn_location = None
        self.original_pawn_rotation = None

    def phase(self, value):
        self.phase_name = value
        self.phase_started = time.monotonic()
        self.frames = 0
        unreal.log("REDMMO_R18_VERIFY_PHASE " + value)

    def prepare(self):
        require(not RESULT.exists(), "R18 verify result already exists")
        require(all(not path.exists() for path in CAPTURES.values()), "R18 capture already exists")
        require(sha256(MAP_FILE) == EXPECTED_MAP_SHA, "R18 map hash drift")
        self.report["providers"] = provider_gate()
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "Protected hash drift: " + str(path))
        require(not dirty_packages()["content"] and not dirty_packages()["maps"], "Dirty before R18 verify")
        require(self.level.load_level(MAP), "Unable to fresh-reload R18 map")
        editor_world = self.editor.get_editor_world()
        actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
        presenters = [actor for actor in actors if actor.get_actor_label() == PRESENTER_LABEL]
        require(len(actors) == 12 and len(presenters) == 1, "R18 serialized actor contract failed")
        unreal.SystemLibrary.execute_console_command(editor_world, "MAP CHECK")
        require(not dirty_packages()["content"] and not dirty_packages()["maps"], "MapCheck dirtied R18")
        self.report["fresh_reload"] = {"actor_count": len(actors), "presenter_count": len(presenters)}
        self.level.editor_request_begin_play()
        self.phase("wait_pie")

    def acquire_pie(self):
        world = self.editor.get_game_world()
        if world is None or not self.level.is_in_play_in_editor():
            return False
        actors = list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor))
        presenters = [actor for actor in actors if actor.get_actor_label() == PRESENTER_LABEL]
        spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        suns = []
        for actor in actors:
            if isinstance(actor, unreal.DirectionalLight):
                components = list(actor.get_components_by_class(unreal.DirectionalLightComponent))
                if len(components) == 1 and bool(components[0].get_editor_property("atmosphere_sun_light")) \
                        and int(components[0].get_editor_property("atmosphere_sun_light_index")) == 0:
                    suns.append(actor)
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        controller = unreal.GameplayStatics.get_player_controller(world, 0)
        if len(presenters) != 1 or len(spawners) != 1 or len(suns) != 1 or pawn is None or controller is None:
            return False
        self.world, self.presenter, self.spawner, self.sun = world, presenters[0], spawners[0], suns[0]
        self.pawn, self.controller = pawn, controller
        self.center = self.spawner.get_actor_location()
        self.original_pawn_location = pawn.get_actor_location()
        self.original_pawn_rotation = pawn.get_actor_rotation()
        self.radial = normalized(sub(self.original_pawn_location, self.center))
        self.original_sun_rotation = self.sun.get_actor_rotation()
        self.report["pie_contract"] = {
            "pawn_class": pawn.get_class().get_name(),
            "presenter_class": self.presenter.get_class().get_name(),
            "presenter_label": self.presenter.get_actor_label(),
            "sun_label": self.sun.get_actor_label(),
            "start_location": vec(self.original_pawn_location),
            "radial_up": vec(self.radial),
        }
        self.phase("wait_generation")
        return True

    def generation_ready(self):
        method = getattr(self.spawner, "get_planet_generation_status", None)
        if not callable(method):
            return False
        status = method()
        phase = str(status.get_editor_property("phase"))
        generating = bool(status.get_editor_property("is_generating"))
        progress = float(status.get_editor_property("progress"))
        self.report["generation"] = {"phase": phase, "is_generating": generating, "progress": progress}
        return "COMPLETE" in phase.upper() and not generating and progress >= 0.999

    def set_sun(self, day):
        forward = mul(self.radial, -1.0 if day else 1.0)
        rotation = unreal.MathLibrary.make_rot_from_xz(forward, tangent_for(self.radial))
        require(self.sun.set_actor_rotation(rotation, True) is not False, "Unable to rotate transient sun")

    def capture(self, key):
        path = CAPTURES[key]
        view_location, view_rotation = player_view(self.controller, self.pawn)
        applied = self.presenter.evaluate_and_apply_at(view_location)
        require(bool(applied), "Presenter failed to resolve for " + key)
        values = {
            "view_location": vec(view_location),
            "view_rotation": [float(view_rotation.pitch), float(view_rotation.yaw), float(view_rotation.roll)],
            "altitude_cm": float(self.presenter.get_editor_property("last_altitude_cm")),
            "night_weight": float(self.presenter.get_editor_property("last_night_hemisphere_weight")),
            "star_weight": float(self.presenter.get_editor_property("last_star_visibility_weight")),
            "fill_weight": float(self.presenter.get_editor_property("last_night_fill_weight")),
            "path": path.as_posix(),
        }
        if key == "surface_day":
            require(values["night_weight"] < 0.01 and values["star_weight"] < 0.01, "Day weights wrong")
        elif key == "surface_night":
            require(values["night_weight"] > 0.99 and values["star_weight"] >= 0.17 and values["fill_weight"] >= 0.15,
                    "Surface-night weights wrong")
        else:
            require(values["star_weight"] > 0.99 and values["fill_weight"] < 0.01, "Orbit weights wrong")
        self.report.setdefault("captures", {})[key] = values
        unreal.SystemLibrary.execute_console_command(
            self.world, 'HighResShot filename="{}" 1280x720'.format(path.as_posix()))
        self.phase("wait_" + key + "_capture")

    def restore_and_stop(self):
        self.sun.set_actor_rotation(self.original_sun_rotation, True)
        self.pawn.set_actor_location(self.original_pawn_location, False, False)
        self.pawn.set_actor_rotation(self.original_pawn_rotation, True)
        self.level.editor_request_end_play()
        self.phase("wait_end")

    def finish(self):
        for key, path in CAPTURES.items():
            require(path.is_file() and path.stat().st_size > 0, "Missing capture: " + key)
            require(png_size(path) == [1280, 720], "Capture size mismatch: " + key)
            self.report["captures"][key].update({"sha256": sha256(path), "bytes": path.stat().st_size,
                                                   "dimensions": [1280, 720]})
        require(sha256(MAP_FILE) == EXPECTED_MAP_SHA, "PIE changed R18 map")
        require(not dirty_packages()["content"] and not dirty_packages()["maps"], "PIE dirtied R18 packages")
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "PIE changed protected content")
        self.report.update({
            "status": "PASS_R18_R02_SPARSE_STARS_RUNTIME_WEIGHTS_AND_D3D12_CAPTURES_PENDING_HUMAN_VISUAL_REVIEW",
            "map_sha256_after": sha256(MAP_FILE),
            "protected_hashes": {str(path): sha256(path) for path in PROTECTED},
            "pie_stopped_cleanly": True,
            "claim_limit": "Fresh D3D12 pixels and runtime weights exist, but human review is still required and no gameplay/standalone/multiplayer acceptance is claimed.",
        })
        with RESULT.open("x", encoding="utf-8") as stream:
            json.dump(self.report, stream, indent=2)
            stream.write("\n")
        unreal.log_warning("REDMMO_NIGHT_PRESENTER_R18_VERIFY_PASS " + json.dumps(self.report, sort_keys=True))
        unreal.unregister_slate_post_tick_callback(self.handle)
        self.handle = None
        unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), "QUIT_EDITOR")

    def fail(self, error):
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        unreal.log_error("REDMMO_NIGHT_PRESENTER_R18_VERIFY_FAIL " + repr(error) + "\n" + traceback.format_exc())
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), "QUIT_EDITOR")

    def tick(self, _delta):
        try:
            self.frames += 1
            if self.phase_name == "prepare":
                self.prepare()
            elif self.phase_name == "wait_pie":
                require(time.monotonic() - self.phase_started < 90.0, "PIE startup timeout")
                self.acquire_pie()
            elif self.phase_name == "wait_generation":
                require(time.monotonic() - self.phase_started < 180.0, "PPG generation timeout")
                if self.generation_ready() and self.frames >= 120:
                    self.set_sun(True)
                    self.phase("settle_day")
            elif self.phase_name == "settle_day" and self.frames >= 120:
                self.capture("surface_day")
            elif self.phase_name == "wait_surface_day_capture" and self.frames >= 60:
                require(CAPTURES["surface_day"].exists(), "Day capture timeout")
                self.set_sun(False)
                self.phase("settle_night")
            elif self.phase_name == "settle_night" and self.frames >= 120:
                self.capture("surface_night")
            elif self.phase_name == "wait_surface_night_capture" and self.frames >= 60:
                require(CAPTURES["surface_night"].exists(), "Night capture timeout")
                orbit = add(self.center, mul(self.radial, 310200000.0))
                self.pawn.set_actor_enable_collision(False)
                require(self.pawn.set_actor_location(orbit, False, True) is not False, "Orbit move failed")
                self.controller.set_control_rotation(unreal.MathLibrary.make_rot_from_xz(mul(self.radial, -1.0), tangent_for(self.radial)))
                self.phase("settle_orbit")
            elif self.phase_name == "settle_orbit":
                orbit = add(self.center, mul(self.radial, 310200000.0))
                self.pawn.set_actor_location(orbit, False, True)
                if self.frames >= 120:
                    self.capture("orbit_night")
            elif self.phase_name == "wait_orbit_night_capture" and self.frames >= 60:
                require(CAPTURES["orbit_night"].exists(), "Orbit capture timeout")
                self.restore_and_stop()
            elif self.phase_name == "wait_end":
                require(time.monotonic() - self.phase_started < 60.0, "PIE end timeout")
                if not self.level.is_in_play_in_editor() and self.editor.get_game_world() is None:
                    self.finish()
        except Exception as error:
            self.fail(error)


session = Session()
session.handle = unreal.register_slate_post_tick_callback(session.tick)
unreal.log("REDMMO_NIGHT_PRESENTER_R18_VERIFY_STARTED")
