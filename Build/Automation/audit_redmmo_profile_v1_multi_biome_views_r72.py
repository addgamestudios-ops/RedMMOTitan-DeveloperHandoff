"""R72 no-save D3D12 representative-view audit for the R71 role surface.

This streams four deterministic R69 directions, selects a live generated PPG
chunk for the requested role, traces that chunk's own collision, transiently
places the PIE player at player height, and captures the real viewport in
Unlit view mode so day/night does not hide the role material. Nothing is saved.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
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
R66_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_NoPalms_R66.uasset"
ROLE_PARENT_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\M_PPG_ProfileV1_RoleSurface_R71.uasset"
ROLE_MI_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\MI_PPG_ProfileV1_RoleSurface_R71.uasset"
HELPERS = Path(r"D:\RedMMOTitan\Build\Automation\apply_redmmo_profile_v1_seeded_land_start_r20.py")
ROLLBACK = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeMultiBiomeViews_R72B_20260805T2326Z")
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_ProfileV1MultiBiomeViews_R72B_20260805T2326Z")
CAPTURE_DIR = DIAG / "Capture"
RESULT = DIAG / "result.json"
LOG = DIAG / "verify.log"

EXPECTED = {
    MAP_FILE: "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3",
    PROFILE_FILE: "BD5E46F3132A6A8947C1258AB18C0F152DD4836755A414B9CC876E3BD0D6CB0D",
    R66_FILE: "C0EE6CB0A2D9D679D1FB4D64747555D55A5AF18ABED4AEC2666A1D5BECDA97DC",
    ROLE_PARENT_FILE: "EA3A5704BDA1706C7720CDFB51F39CE370CCD844E6FECEDEB53CF3ACC4F555DE",
    ROLE_MI_FILE: "D4D222CF92769F99631B649198DD8C38032BD67B7853CD7B0A288E1657301253",
    HELPERS: "7707C56E13E9922A2F2D3ADBCE4CB7CCD917241B5F875EE631E347B5A70B83B7",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}

PROFILE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
EXPECTED_SEED = 1337
VIEW_ALTITUDE_CM = 100000.0
STREAM_SETTLE_FRAMES = 55
GROUND_SETTLE_FRAMES = 90
SCREENSHOT_SETTLE_SECONDS = 2.0

# Exact deterministic Fibonacci directions already proven by R69. Ocean is a
# true Ocean-role sample; it may be below the native sea datum.
TARGETS = [
    {"label": "hills", "role": "Hills", "direction": [0.4212191481735607, -0.53125, 0.7350835780453403], "above_sea": True},
    {"label": "desert", "role": "Desert", "direction": [0.04692456666828282, 0.84375, -0.5346812345154763], "above_sea": True},
    {"label": "mountains", "role": "Mountains", "direction": [-0.20889049343814645, 0.59375, 0.7770622235388668], "above_sea": True},
    {"label": "ocean", "role": "Ocean", "direction": [0.3797986477904189, 0.78125, 0.4953800809848628], "above_sea": False},
]


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


helper_source = HELPERS.read_text(encoding="utf-8")
helper_prefix = helper_source.split("\nrequire(os.path.normcase", 1)[0]
helper_ns = {"__name__": "redmmo_r72_helpers", "__file__": str(HELPERS)}
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
dot = helper_ns["dot"]
length = helper_ns["length"]
normalized = helper_ns["normalized"]
write_json_exclusive = helper_ns["write_json_exclusive"]


def cross(a, b):
    return unreal.Vector(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    )


def command_log():
    command = str(unreal.SystemLibrary.get_command_line())
    match = re.search(r'(?i)-abslog=(?:"([^"]+)"|(\S+))', command)
    return Path(match.group(1) or match.group(2)) if match else LOG


def map_check(world):
    path = command_log()
    require(path.is_file(), "verifier log missing")
    offset = path.stat().st_size
    unreal.SystemLibrary.execute_console_command(world, "MAP CHECKDEP NOCLEARLOG")
    pattern = re.compile(r"MapCheck: Map check complete: (\d+) Error\(s\), (\d+) Warning\(s\)")
    for _ in range(120):
        time.sleep(0.1)
        with path.open("rb") as stream:
            stream.seek(min(offset, path.stat().st_size))
            matches = pattern.findall(stream.read().decode("utf-8", errors="replace"))
        if matches:
            errors, warnings = (int(value) for value in matches[-1])
            require(errors == 0 and warnings == 0, "MapCheck failed: {}/{}".format(errors, warnings))
            return {"errors": errors, "warnings": warnings, "log": str(path)}
    raise RuntimeError("no fresh MapCheck marker")


def component_trace(component, center, radius, direction):
    start = add(center, mul(direction, radius + 2000000.0))
    end = add(center, mul(direction, radius - 2000000.0))
    raw = component.line_trace_component(start, end, True, False, False)
    require(isinstance(raw, tuple), "unexpected component trace type")
    vectors = [item for item in raw if hasattr(item, "x") and hasattr(item, "y") and hasattr(item, "z")]
    booleans = [item for item in raw if isinstance(item, bool)]
    require(len(vectors) >= 2, "component trace returned no point/normal")
    hit = booleans[0] if booleans else length(vectors[1]) > 0.5
    require(hit, "selected PPG component trace missed")
    return vectors[0], normalized(vectors[1])


def tangent_for(up):
    candidate = cross(unreal.Vector(0.0, 0.0, 1.0), up)
    if length(candidate) < 0.1:
        candidate = cross(unreal.Vector(0.0, 1.0, 0.0), up)
    return normalized(candidate)


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
        self.controller = None
        self.biomes = []
        self.by_index = {}
        self.target_index = -1
        self.target = None
        self.direction = None
        self.selected = None
        self.capture_requested = None
        self.records = []
        self.report = {
            "schema": "redmmo.ppg.profile_v1_multi_biome_views.r72.v1",
            "status": "RUNNING",
            "evidence_class": "real_gpu_visual",
            "started_utc": now(),
            "map": MAP,
            "seed_changed": False,
            "generation_called": False,
            "persistent_map_or_asset_writes": False,
            "capture_view_mode": "Unlit",
            "targets": TARGETS,
        }

    def set_phase(self, value):
        self.phase = value
        self.phase_started = time.monotonic()
        self.frames = 0
        self.ready_frames = 0
        unreal.log("REDMMO_R72_MULTI_BIOME_PHASE " + value)

    def generation_ready(self):
        status = self.spawner.get_planet_generation_status()
        phase = str(status.get_editor_property("phase"))
        progress = float(status.get_editor_property("progress"))
        generating = bool(status.get_editor_property("is_generating"))
        return "COMPLETE" in phase.upper() and progress >= 0.999 and not generating

    def start(self):
        active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(active == PROJECT.resolve(strict=True), "wrong active project")
        require(not RESULT.exists() and not ROLLBACK.exists(), "R72 no-clobber failed")
        for path, expected in EXPECTED.items():
            require(path.is_file() and sha256(path) == expected, "input drift: " + str(path))
        require(dirty_packages() == {"content": [], "maps": []}, "editor started dirty")
        require(not self.level.is_in_play_in_editor(), "PIE already active")
        command = str(unreal.SystemLibrary.get_command_line()).lower()
        require("-d3d12" in command and "-renderoffscreen" in command and "-nullrhi" not in command, "renderer gate failed")
        self.report["provider_gate_before"] = provider_gate()
        ROLLBACK.mkdir(parents=True, exist_ok=False)
        rollback_map = ROLLBACK / "RedMMO_PPG_HomeWorld.pre_r72_no_save.umap"
        shutil.copy2(MAP_FILE, rollback_map)
        require(sha256(rollback_map) == EXPECTED[MAP_FILE], "rollback byte mismatch")
        write_json_exclusive(ROLLBACK / "manifest.json", {
            "schema": "redmmo.ppg.multi_biome_views.rollback.r72.v1",
            "captured_utc": now(),
            "source": str(MAP_FILE),
            "source_sha256": EXPECTED[MAP_FILE],
            "rollback": str(rollback_map),
            "restore": "No restore expected: R72 is read-only/no-save.",
        })
        CAPTURE_DIR.mkdir(parents=True, exist_ok=False)
        require(self.level.load_level(MAP), "unable to load exact home map")
        require(dirty_packages() == {"content": [], "maps": []}, "map load dirtied packages")
        editor_world = self.editor.get_editor_world()
        self.report["map_check"] = map_check(editor_world)
        self.level.editor_request_begin_play()
        self.set_phase("wait_pie")

    def bind_pie(self):
        world = self.editor.get_game_world()
        if world is None or not self.level.is_in_play_in_editor():
            return
        actors = list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor))
        spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        require(len(spawners) == 1, "expected exactly one PPG spawner")
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        controller = unreal.GameplayStatics.get_player_controller(world, 0)
        require(pawn is not None and controller is not None, "PIE player/controller unavailable")
        self.world = world
        self.spawner = spawners[0]
        self.planet = self.spawner.get_editor_property("planet_data")
        require(asset_path(self.planet) == PROFILE, "unexpected PlanetData binding")
        self.center = self.spawner.get_actor_location()
        self.radius = float(self.planet.get_editor_property("planet_radius"))
        require(int(self.planet.get_editor_property("generation_seed")) == EXPECTED_SEED, "PPG seed drift")
        self.pawn = pawn
        self.controller = controller
        self.biomes = biome_records(self.planet)
        self.by_index = {item["index"]: item for item in self.biomes}
        self.report["runtime"] = {
            "world": world.get_path_name(),
            "spawner": self.spawner.get_path_name(),
            "pawn_class": pawn.get_class().get_name(),
            "center": vec(self.center),
            "radius_cm": self.radius,
            "seed": EXPECTED_SEED,
            "biomes": self.biomes,
        }
        unreal.SystemLibrary.execute_console_command(world, "DISABLEALLSCREENMESSAGES")
        unreal.SystemLibrary.execute_console_command(world, "viewmode unlit")
        self.set_phase("wait_initial_generation")

    def begin_next_target(self):
        self.target_index += 1
        if self.target_index >= len(TARGETS):
            self.level.editor_request_end_play()
            self.set_phase("wait_pie_stop")
            return
        self.target = TARGETS[self.target_index]
        self.direction = normalized(unreal.Vector(*self.target["direction"]))
        self.selected = None
        self.capture_requested = None
        target = add(self.center, mul(self.direction, self.radius + VIEW_ALTITUDE_CM))
        forward = tangent_for(self.direction)
        rotation = unreal.MathLibrary.make_rot_from_xz(forward, self.direction)
        require(self.pawn.set_actor_location(target, False, True) is not False, "transient stream teleport failed")
        self.pawn.set_actor_rotation(rotation, True)
        self.controller.set_control_rotation(rotation)
        self.set_phase("settle_stream")

    def pin_stream(self):
        target = add(self.center, mul(self.direction, self.radius + VIEW_ALTITUDE_CM))
        rotation = unreal.MathLibrary.make_rot_from_xz(tangent_for(self.direction), self.direction)
        self.pawn.set_actor_location(target, False, True)
        self.pawn.set_actor_rotation(rotation, True)
        self.controller.set_control_rotation(rotation)

    def select_and_place(self):
        components = list(self.spawner.get_components_by_class(unreal.StaticMeshComponent))
        candidates = []
        for component in components:
            if (not component.is_query_collision_enabled()
                    or component.get_editor_property("static_mesh") is None
                    or isinstance(component, unreal.InstancedStaticMeshComponent)):
                continue
            location = component.get_world_location()
            delta = sub(location, self.center)
            if length(delta) < self.radius * 0.5:
                continue
            direction = normalized(delta)
            point = add(self.center, mul(direction, self.radius))
            try:
                sample = sample_component(self.world, component, point, self.center, self.radius)
            except Exception:
                continue
            if sample is None:
                continue
            dominant_index = int(sample["top3_biome_indices"][0])
            role = self.by_index.get(dominant_index, {"name": "UNKNOWN"})["name"]
            above = float(sample["raw_index_pixel"][3]) >= 0.999
            if role != self.target["role"] or above != self.target["above_sea"]:
                continue
            candidates.append((dot(direction, self.direction), float(sample["top3_biome_strengths"][0]), component, direction, sample))
        require(candidates, "no live generated candidate for " + self.target["role"])
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        angular_dot, strength, component, direction, sample = candidates[0]
        hit_point, hit_normal = component_trace(component, self.center, self.radius, direction)
        forward = tangent_for(hit_normal)
        rotation = unreal.MathLibrary.make_rot_from_xz(forward, hit_normal)
        location = add(hit_point, mul(hit_normal, 175.0))
        require(self.pawn.set_actor_location(location, False, True) is not False, "ground placement failed")
        self.pawn.set_actor_rotation(rotation, True)
        self.controller.set_control_rotation(rotation)
        self.selected = {
            "label": self.target["label"],
            "role": self.target["role"],
            "component": component.get_path_name(),
            "component_direction": vec(direction),
            "stream_direction_dot": angular_dot,
            "dominant_strength": strength,
            "sea_authority_alpha": float(sample["raw_index_pixel"][3]),
            "at_or_above_sea": self.target["above_sea"],
            "trace_point": vec(hit_point),
            "trace_normal": vec(hit_normal),
            "initial_player_location": vec(location),
            "rotation": [rotation.pitch, rotation.yaw, rotation.roll],
        }
        self.set_phase("settle_ground")

    def pin_orientation(self):
        if not self.selected:
            return
        up = normalized(sub(self.pawn.get_actor_location(), self.center))
        rotation = unreal.MathLibrary.make_rot_from_xz(tangent_for(up), up)
        self.pawn.set_actor_rotation(rotation, True)
        self.controller.set_control_rotation(rotation)

    def request_capture(self):
        label = self.target["label"]
        path = CAPTURE_DIR / ("R72_{}_player_surface_unlit.png".format(label))
        require(not path.exists(), "capture no-clobber failed: " + str(path))
        camera = unreal.GameplayStatics.get_player_camera_manager(self.world, 0)
        self.selected["capture_player_location"] = vec(self.pawn.get_actor_location())
        self.selected["capture_camera_location"] = vec(camera.get_actor_location()) if camera else None
        self.selected["capture_camera_rotation"] = str(camera.get_actor_rotation()) if camera else None
        self.selected["capture_path"] = str(path)
        accepted = unreal.RedPPGFoliageDiagnostics.request_viewport_screenshot(str(path))
        require(accepted, "viewport screenshot request rejected")
        self.capture_requested = time.monotonic()
        self.set_phase("wait_capture")

    def complete_capture(self):
        path = Path(self.selected["capture_path"])
        require(path.is_file() and path.stat().st_size > 0, "capture missing")
        self.selected["capture_bytes"] = path.stat().st_size
        self.selected["capture_sha256"] = sha256(path)
        self.records.append(self.selected)
        self.begin_next_target()

    def publish(self):
        require(not self.level.is_in_play_in_editor() and self.editor.get_game_world() is None, "PIE still active")
        require(dirty_packages() == {"content": [], "maps": []}, "R72 dirtied packages")
        for path, expected in EXPECTED.items():
            require(sha256(path) == expected, "post-run drift: " + str(path))
        require(len(self.records) == len(TARGETS), "incomplete capture set")
        hashes = [item["capture_sha256"] for item in self.records]
        require(len(set(hashes)) == len(hashes), "representative captures are byte-identical")
        self.report.update({
            "status": "PASS_R72_FOUR_ROLE_PLAYER_SURFACE_D3D12_NO_SAVE",
            "completed_utc": now(),
            "records": self.records,
            "capture_sha256_distinct": True,
            "map_sha256_after": sha256(MAP_FILE),
            "profile_sha256_after": sha256(PROFILE_FILE),
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "claim_limit": "Four fresh Unlit D3D12 player-viewport role samples only. This does not prove final lit art, coast-water behavior, terrain smoothness, gameplay, packaging, replication, multiplayer, or player acceptance.",
        })
        write_json_exclusive(RESULT, self.report)
        unreal.log_warning("REDMMO_R72_MULTI_BIOME_PASS " + json.dumps({"captures": len(self.records), "roles": [item["role"] for item in self.records]}))
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), "QUIT_EDITOR")

    def fail(self, error):
        self.report.update({
            "status": "FAIL",
            "error": str(error),
            "traceback": traceback.format_exc(),
            "phase": self.phase,
            "records": self.records,
            "map_sha256_observed": sha256(MAP_FILE) if MAP_FILE.is_file() else None,
            "profile_sha256_observed": sha256(PROFILE_FILE) if PROFILE_FILE.is_file() else None,
            "completed_utc": now(),
        })
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        if not RESULT.exists():
            DIAG.mkdir(parents=True, exist_ok=True)
            write_json_exclusive(RESULT, self.report)
        unreal.log_error("REDMMO_R72_MULTI_BIOME_FAIL " + repr(error) + "\n" + traceback.format_exc())
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), "QUIT_EDITOR")

    def tick(self, _delta):
        try:
            self.frames += 1
            require(time.monotonic() - self.started < 1200.0, "R72 overall timeout")
            require(time.monotonic() - self.phase_started < 300.0, "R72 phase timeout: " + self.phase)
            if self.phase == "prepare":
                self.start()
            elif self.phase == "wait_pie":
                self.bind_pie()
            elif self.phase == "wait_initial_generation":
                if self.generation_ready():
                    self.ready_frames += 1
                    if self.ready_frames >= 90:
                        self.begin_next_target()
                else:
                    self.ready_frames = 0
            elif self.phase == "settle_stream":
                self.pin_stream()
                if self.generation_ready():
                    self.ready_frames += 1
                    if self.ready_frames >= STREAM_SETTLE_FRAMES:
                        self.select_and_place()
                else:
                    self.ready_frames = 0
            elif self.phase == "settle_ground":
                self.pin_orientation()
                if self.generation_ready():
                    self.ready_frames += 1
                    if self.ready_frames >= GROUND_SETTLE_FRAMES:
                        self.request_capture()
                else:
                    self.ready_frames = 0
            elif self.phase == "wait_capture":
                self.pin_orientation()
                path = Path(self.selected["capture_path"])
                if (path.is_file() and path.stat().st_size > 0
                        and time.monotonic() - self.phase_started >= SCREENSHOT_SETTLE_SECONDS):
                    self.complete_capture()
            elif self.phase == "wait_pie_stop":
                if not self.level.is_in_play_in_editor() and self.editor.get_game_world() is None:
                    self.set_phase("publish")
            elif self.phase == "publish":
                self.publish()
        except Exception as error:
            self.fail(error)


require(os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path()))) ==
        os.path.normcase(os.path.abspath(str(PROJECT))), "wrong active project")
audit = Audit()
audit.handle = unreal.register_slate_post_tick_callback(audit.tick)
unreal.log("REDMMO_R72_MULTI_BIOME_STARTED")
