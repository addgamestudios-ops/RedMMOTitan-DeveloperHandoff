"""No-save D3D12 isolation of R18 surface occlusion and sun direction."""

from __future__ import annotations

import hashlib
import json
import math
import os
import socket
import struct
import time
import traceback
from pathlib import Path

import unreal


MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
MAP_FILE = Path("D:/RedMMOTitanWindowsData/Projects/RedMMO/Content/RedMMO/Maps/RedMMO_PPG_HomeWorld.umap")
EXPECTED_MAP_SHA = "6B45B423ED59BD8906A05CF35E7349C70282154DE2CE4723D41E0C16380F88D9"
PROFILE_FILE = Path("D:/RedMMOTitanWindowsData/Projects/RedMMO/Content/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData.uasset")
EXPECTED_PROFILE_SHA = "5C50D50A8955C1E5F4270BDD4E53D1214C941725157B76422CD72B748978B837"
DIAG = Path("D:/RedMMOTitanWindowsData/Diagnostics/RedMMO_R18_SurfaceOcclusion_R19_20260805T1028Z")
RESULT = DIAG / "result.json"
CAPTURES = {
    "night_dome_visible": DIAG / "R19_night_dome_visible_1280x720.png",
    "night_dome_hidden": DIAG / "R19_night_dome_hidden_1280x720.png",
    "sun_forward_inward": DIAG / "R19_sun_forward_inward_1280x720.png",
    "sun_forward_outward": DIAG / "R19_sun_forward_outward_1280x720.png",
}
PROTECTED = {
    Path("D:/RedMMOTitan/Content/RedMMO/Maps/RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path("D:/RedMMOTitan/Content/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}
PORTS = (11111, 5353, 8000, 8765)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def vec(value):
    return [float(value.x), float(value.y), float(value.z)]


def add(a, b):
    return unreal.Vector(a.x + b.x, a.y + b.y, a.z + b.z)


def sub(a, b):
    return unreal.Vector(a.x - b.x, a.y - b.y, a.z - b.z)


def mul(value, scalar):
    return unreal.Vector(value.x * scalar, value.y * scalar, value.z * scalar)


def dot(a, b):
    return float(a.x * b.x + a.y * b.y + a.z * b.z)


def length(value):
    return math.sqrt(dot(value, value))


def normalized(value):
    magnitude = length(value)
    require(magnitude > 0.001, "Cannot normalize zero vector")
    return mul(value, 1.0 / magnitude)


def cross(a, b):
    return unreal.Vector(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    )


def tangent_for(radial):
    axis = unreal.Vector(0.0, 0.0, 1.0)
    if abs(dot(radial, axis)) > 0.9:
        axis = unreal.Vector(0.0, 1.0, 0.0)
    return normalized(cross(radial, axis))


def asset_path(value):
    return value.get_path_name() if value is not None else None


def dirty_packages():
    content = [value.get_path_name() for value in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]
    maps = [value.get_path_name() for value in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
    return {"content": sorted(content), "maps": sorted(maps)}


def provider_gate():
    result = []
    for port in PORTS:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.2)
        try:
            closed = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
        result.append({"port": port, "closed": closed})
    require(all(item["closed"] for item in result), "Provider listener active")
    return result


def png_size(path):
    with Path(path).open("rb") as stream:
        header = stream.read(24)
    require(header[:8] == b"\x89PNG\r\n\x1a\n", "Not PNG: " + str(path))
    return list(struct.unpack(">II", header[16:24]))


def hit_value(hit, names, default=None):
    for name in names:
        try:
            return hit.get_editor_property(name)
        except Exception:
            continue
    return default


def trace_record(world, start, end, ignored):
    query = getattr(unreal.TraceTypeQuery, "TRACE_TYPE_QUERY1", None)
    require(query is not None, "Visibility TraceTypeQuery unavailable")
    hit = unreal.SystemLibrary.line_trace_single(
        world, start, end, query, True, ignored,
        unreal.DrawDebugTrace.NONE, True,
        unreal.LinearColor(1.0, 0.0, 0.0, 1.0),
        unreal.LinearColor(0.0, 1.0, 0.0, 1.0), 0.0,
    )
    if hit is None:
        return {"blocking_hit": False}
    actor = hit_value(hit, ("hit_actor", "actor"))
    component = hit_value(hit, ("hit_component", "component"))
    point = hit_value(hit, ("impact_point", "location"))
    normal = hit_value(hit, ("impact_normal", "normal"))
    return {
        "blocking_hit": bool(hit_value(hit, ("blocking_hit", "bBlockingHit"), False)),
        "actor": actor.get_path_name() if actor else None,
        "actor_label": actor.get_actor_label() if actor else None,
        "component": component.get_path_name() if component else None,
        "impact_point": vec(point) if point else None,
        "impact_normal": vec(normal) if normal else None,
    }


class Session:
    def __init__(self):
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.handle = None
        self.phase = "prepare"
        self.phase_started = time.monotonic()
        self.frames = 0
        self.world = None
        self.pawn = None
        self.spawner = None
        self.presenter = None
        self.sun = None
        self.star = None
        self.fill = None
        self.center = None
        self.radial = None
        self.radius = None
        self.original_sun_rotation = None
        self.report = {
            "status": "RUNNING",
            "map": MAP,
            "evidence_class": "real_gpu_visual_diagnostic",
            "no_save": True,
        }

    def set_phase(self, value):
        self.phase = value
        self.phase_started = time.monotonic()
        self.frames = 0
        unreal.log("REDMMO_R19_SURFACE_OCCLUSION_PHASE " + value)

    def prepare(self):
        # Level loading pumps Slate and can re-enter this callback. Advance first
        # so a progress tick cannot issue a second MAP LOAD command.
        self.set_phase("loading_map")
        require(not RESULT.exists(), "R19 result exists")
        require(all(not path.exists() for path in CAPTURES.values()), "R19 capture exists")
        require(sha256(MAP_FILE) == EXPECTED_MAP_SHA, "Home map hash drift")
        require(sha256(PROFILE_FILE) == EXPECTED_PROFILE_SHA, "ProfileV1 hash drift")
        self.report["provider_gate_before"] = provider_gate()
        require(dirty_packages() == {"content": [], "maps": []}, "Dirty before R19")
        require(self.level.load_level(MAP), "Unable to load exact home map")
        actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
        floor = [actor for actor in actors if actor.get_name() == "Floor_0"]
        require(len(floor) == 1, "Expected exact saved Floor_0")
        self.report["saved_floor"] = {
            "path": floor[0].get_path_name(),
            "label": floor[0].get_actor_label(),
            "location": vec(floor[0].get_actor_location()),
            "scale": vec(floor[0].get_actor_scale3d()),
        }
        self.level.editor_request_begin_play()
        self.set_phase("wait_pie")

    def acquire(self):
        world = self.editor.get_game_world()
        if world is None or not self.level.is_in_play_in_editor():
            return False
        actors = list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor))
        spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        presenters = [actor for actor in actors if actor.get_actor_label() == "RED_NightPresenter_R18"]
        suns = []
        for actor in actors:
            if isinstance(actor, unreal.DirectionalLight):
                components = list(actor.get_components_by_class(unreal.DirectionalLightComponent))
                if len(components) == 1 and bool(components[0].get_editor_property("atmosphere_sun_light")) \
                        and int(components[0].get_editor_property("atmosphere_sun_light_index")) == 0:
                    suns.append(actor)
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        if len(spawners) != 1 or len(presenters) != 1 or len(suns) != 1 or pawn is None:
            return False
        self.world, self.spawner, self.presenter, self.sun, self.pawn = world, spawners[0], presenters[0], suns[0], pawn
        stars = list(self.presenter.get_components_by_class(unreal.StaticMeshComponent))
        fills = list(self.presenter.get_components_by_class(unreal.DirectionalLightComponent))
        require(len(stars) == 1 and len(fills) == 1, "Presenter component contract drift")
        self.star, self.fill = stars[0], fills[0]
        mesh = self.star.get_editor_property("static_mesh")
        require(asset_path(mesh) == "/Engine/BasicShapes/Sphere.Sphere", "Unexpected star-dome mesh")
        self.center = self.spawner.get_actor_location()
        planet = self.spawner.get_editor_property("planet_data")
        self.radius = float(planet.get_editor_property("planet_radius"))
        self.radial = normalized(sub(self.pawn.get_actor_location(), self.center))
        self.original_sun_rotation = self.sun.get_actor_rotation()
        floor_location = unreal.Vector(*self.report["saved_floor"]["location"])
        self.report.update({
            "pawn": {"class": pawn.get_class().get_name(), "location": vec(pawn.get_actor_location())},
            "planet": {"center": vec(self.center), "radius": self.radius},
            "presenter": {
                "class": self.presenter.get_class().get_name(),
                "star_component": self.star.get_path_name(),
                "star_mesh": asset_path(mesh),
                "fill_component": self.fill.get_path_name(),
            },
            "floor_distance_from_planet_center_cm": length(sub(floor_location, self.center)),
            "floor_angular_dot_to_player": dot(normalized(sub(floor_location, self.center)), self.radial),
        })
        self.set_phase("wait_generation")
        return True

    def generation_ready(self):
        status = self.spawner.get_planet_generation_status()
        phase = str(status.get_editor_property("phase"))
        progress = float(status.get_editor_property("progress"))
        generating = bool(status.get_editor_property("is_generating"))
        self.report["generation"] = {"phase": phase, "progress": progress, "is_generating": generating}
        return "COMPLETE" in phase.upper() and progress >= 0.999 and not generating

    def set_sun_forward(self, forward):
        rotation = unreal.MathLibrary.make_rot_from_xz(forward, tangent_for(self.radial))
        require(self.sun.set_actor_rotation(rotation, True) is not False, "Transient sun rotation failed")

    def trace_surface(self):
        actors = list(unreal.GameplayStatics.get_all_actors_of_class(self.world, unreal.Actor))
        ignored = [actor for actor in actors if actor != self.spawner]
        pawn_location = self.pawn.get_actor_location()
        outward_end = add(self.center, mul(self.radial, self.radius + 2000000.0))
        shell_start = add(self.center, mul(self.radial, self.radius + 2000000.0))
        shell_end = add(self.center, mul(self.radial, self.radius - 2000000.0))
        self.report["traces"] = {
            "pawn_radially_outward": trace_record(self.world, add(pawn_location, mul(self.radial, 200.0)), outward_end, ignored),
            "outside_radially_inward": trace_record(self.world, shell_start, shell_end, ignored),
        }

    def capture(self, key):
        path = CAPTURES[key]
        unreal.SystemLibrary.execute_console_command(
            self.world, 'HighResShot filename="{}" 1280x720'.format(path.as_posix()))
        self.set_phase("wait_capture_" + key)

    def hide_star(self):
        self.presenter.set_actor_tick_enabled(False)
        self.star.set_visibility(False, True)
        self.star.set_hidden_in_game(True, True)

    def hide_presenter(self):
        self.hide_star()
        self.fill.set_visibility(False, True)
        self.fill.set_hidden_in_game(True, True)

    def restore_and_stop(self):
        self.sun.set_actor_rotation(self.original_sun_rotation, True)
        self.presenter.set_actor_tick_enabled(True)
        self.level.editor_request_end_play()
        self.set_phase("wait_end")

    def finish(self):
        for key, path in CAPTURES.items():
            require(path.is_file() and path.stat().st_size > 0, "Missing capture " + key)
            require(png_size(path) == [1280, 720], "Capture dimensions " + key)
            self.report.setdefault("captures", {})[key] = {
                "path": path.as_posix(), "sha256": sha256(path), "bytes": path.stat().st_size,
            }
        require(sha256(MAP_FILE) == EXPECTED_MAP_SHA, "PIE changed home map")
        require(sha256(PROFILE_FILE) == EXPECTED_PROFILE_SHA, "PIE changed ProfileV1")
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "Protected hash drift: " + str(path))
        require(dirty_packages() == {"content": [], "maps": []}, "R19 left dirty packages")
        self.report.update({
            "status": "PASS_R19_NO_SAVE_PIXELS_PENDING_VISUAL_CLASSIFICATION",
            "map_sha256_before_after": EXPECTED_MAP_SHA,
            "profile_sha256_before_after": EXPECTED_PROFILE_SHA,
            "protected_hashes": {str(path): sha256(path) for path in PROTECTED},
            "provider_gate_after": provider_gate(),
            "pie_stopped_cleanly": True,
        })
        DIAG.mkdir(parents=True, exist_ok=True)
        with RESULT.open("x", encoding="utf-8") as stream:
            json.dump(self.report, stream, indent=2)
            stream.write("\n")
        unreal.log_warning("REDMMO_R19_SURFACE_OCCLUSION_PASS " + json.dumps(self.report, sort_keys=True))
        unreal.unregister_slate_post_tick_callback(self.handle)
        self.handle = None
        unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), "QUIT_EDITOR")

    def fail(self, error):
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        unreal.log_error("REDMMO_R19_SURFACE_OCCLUSION_FAIL " + repr(error) + "\n" + traceback.format_exc())
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), "QUIT_EDITOR")

    def tick(self, _delta):
        try:
            self.frames += 1
            require(time.monotonic() - self.phase_started < 180.0, "R19 phase timeout: " + self.phase)
            if self.phase == "prepare":
                self.prepare()
            elif self.phase == "wait_pie":
                self.acquire()
            elif self.phase == "wait_generation":
                if self.generation_ready() and self.frames >= 120:
                    self.trace_surface()
                    self.set_sun_forward(self.radial)
                    self.set_phase("settle_night_visible")
            elif self.phase == "settle_night_visible" and self.frames >= 120:
                require(self.presenter.evaluate_and_apply_at(self.pawn.get_actor_location()), "Night presenter evaluation failed")
                self.capture("night_dome_visible")
            elif self.phase == "wait_capture_night_dome_visible" and self.frames >= 60:
                require(CAPTURES["night_dome_visible"].exists(), "Visible-dome capture timeout")
                self.hide_star()
                self.set_phase("settle_night_hidden")
            elif self.phase == "settle_night_hidden" and self.frames >= 120:
                self.capture("night_dome_hidden")
            elif self.phase == "wait_capture_night_dome_hidden" and self.frames >= 60:
                require(CAPTURES["night_dome_hidden"].exists(), "Hidden-dome capture timeout")
                self.hide_presenter()
                self.set_sun_forward(mul(self.radial, -1.0))
                self.set_phase("settle_sun_inward")
            elif self.phase == "settle_sun_inward" and self.frames >= 120:
                self.capture("sun_forward_inward")
            elif self.phase == "wait_capture_sun_forward_inward" and self.frames >= 60:
                require(CAPTURES["sun_forward_inward"].exists(), "Inward-sun capture timeout")
                self.set_sun_forward(self.radial)
                self.set_phase("settle_sun_outward")
            elif self.phase == "settle_sun_outward" and self.frames >= 120:
                self.capture("sun_forward_outward")
            elif self.phase == "wait_capture_sun_forward_outward" and self.frames >= 60:
                require(CAPTURES["sun_forward_outward"].exists(), "Outward-sun capture timeout")
                self.restore_and_stop()
            elif self.phase == "wait_end":
                if not self.level.is_in_play_in_editor() and self.editor.get_game_world() is None:
                    self.finish()
        except Exception as error:
            self.fail(error)


DIAG.mkdir(parents=True, exist_ok=True)
session = Session()
session.handle = unreal.register_slate_post_tick_callback(session.tick)
unreal.log("REDMMO_R19_SURFACE_OCCLUSION_STARTED")
