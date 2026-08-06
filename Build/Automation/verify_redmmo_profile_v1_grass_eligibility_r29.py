"""Fresh reload/MapCheck/PIE gate for the R29 grass-eligibility successor."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import socket
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject")
PROJECT_SHA = "3BF3D8D1D1C7F892A2CD4873F7C0390EC1AF3CA8F77E60549169563D18DBF86F"
HOME_MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
HOME_FILE = PROJECT.parent / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
HOME_SHA = "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3"
PROFILE_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
PROFILE_SHA = "D226215C7367808F4A2E3225A0C9CBD7F4F32E803ABEFD22CA39062CD5538970"
R26_RESULT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1R25LandPlayerStartReload_R26_20260805T1200Z\result.json")
R26_SHA = "7A50363E6A398CE4CC3B1C07C064FC4C099C6F75AB191B124550009C0B9F4449"
R29_FOLIAGE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles/DA_PPG_ProfileV1_GrassEligible_R29"
R29_FOLIAGE_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_GrassEligible_R29.uasset"
R29_FOLIAGE_SHA = "D1ACEE4F403D2082FF49CB57D52907AAADA0C20D06386576C435557CF49404D8"

PLANET_DATA = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
PLAYER_CLASS = "/Game/RedMMO/Gameplay/Trooper/A01/Player/BP_RedTrooperPlayer_A01.BP_RedTrooperPlayer_A01_C"
GAME_MODE_CLASS = "/Game/RedMMO/Gameplay/Trooper/A01/Player/GM_RedTrooperPPG_A01.GM_RedTrooperPPG_A01_C"
MOVE_ACTION = "/Game/RedMMO/Gameplay/Trooper/A01/Input/IA_RedMove"
APPROVED_GRASS = {
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_A_R10N",
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_B_R10N",
}
APPROVED_GRASS_FILES = {
    PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_A_R10N.uasset":
        "6F215104F1374403194D8AB4DA79B3FF16CCBF86472746E5CD433E03118B2443",
    PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_B_R10N.uasset":
        "3C50C87B594CE012F680EF51BA306C2DF09FDAED10C06F7F60AFA4E62F678475",
}

DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1GrassEligibilityReloadPIE_R29C_20260805T1245Z")
RESULT = DIAG / "result.json"
SCREENSHOT = DIAG / "player_scale_grass_eligibility_r29c.png"

PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}

MIN_ELEVATION_CM = 25000.0
MIN_TANGENT_WALK_CM = 500.0
FOLIAGE_SETTLE_SECONDS = 8.0
MAX_ACTIVE_GRASS_ORIGIN_DISTANCE_CM = 50000.0


class GateError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise GateError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def provider_gate():
    state = {}
    for port in (11111, 5353, 8000, 8765):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            state[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    require(all(state.values()), "Provider/MCP listener unexpectedly active: " + repr(state))
    return state


def asset_path(value):
    if value is None:
        return None
    path = str(value.get_path_name()).split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    path = path.rsplit(".", 1)[0] if "." in leaf else path
    return path[:-2] if path.endswith("_C") else path


def class_path(value):
    return value.get_class().get_path_name() if value is not None else None


def dirty_packages():
    return {
        "content": sorted({asset_path(value) for value in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}),
        "maps": sorted({asset_path(value) for value in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()}),
    }


def vec(value):
    return [float(value.x), float(value.y), float(value.z)]


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
    require(magnitude > 1.0e-6, "Cannot normalize zero vector")
    return mul(value, 1.0 / magnitude)


def plane_project(value, normal):
    return sub(value, mul(normal, dot(value, normal)))


def input_subsystem_for_world(world):
    candidates = []
    for item in unreal.ObjectIterator(unreal.EnhancedInputLocalPlayerSubsystem):
        try:
            if item.get_world() == world:
                candidates.append(item)
        except Exception:
            continue
    require(len(candidates) == 1, "Expected one PIE EnhancedInputLocalPlayerSubsystem")
    return candidates[0]


def command_log():
    command = str(unreal.SystemLibrary.get_command_line())
    match = re.search(r'(?i)-abslog=(?:"([^"]+)"|(\S+))', command)
    require(match, "Dedicated -AbsLog argument missing")
    return match.group(1) or match.group(2)


def map_check(world):
    path = command_log()
    offset = os.path.getsize(path)
    unreal.SystemLibrary.execute_console_command(world, "MAP CHECKDEP NOCLEARLOG")
    pattern = re.compile(r"MapCheck: Map check complete: (\d+) Error\(s\), (\d+) Warning\(s\)")
    matches = []
    for _ in range(180):
        time.sleep(0.1)
        with open(path, "rb") as stream:
            stream.seek(min(offset, os.path.getsize(path)))
            matches = pattern.findall(stream.read().decode("utf-8", errors="replace"))
        if matches:
            break
    require(matches, "No fresh authoritative MapCheck completion marker")
    errors, warnings = (int(value) for value in matches[-1])
    require(errors == 0 and warnings == 0, "MapCheck failed: %d errors, %d warnings" % (errors, warnings))
    return {"errors": errors, "warnings": warnings, "log": path, "offset": offset}


def foliage_state(spawner, pawn):
    get_actor = getattr(spawner, "get_foliage_actor", None)
    require(callable(get_actor), "PPG foliage-actor API unavailable")
    actor = get_actor()
    records = []
    if actor is not None:
        for component in list(actor.get_components_by_class(unreal.StaticMeshComponent)):
            mesh = asset_path(component.get_editor_property("static_mesh"))
            origin = component.get_world_location()
            distance = length(sub(origin, pawn.get_actor_location()))
            registered_method = getattr(component, "is_registered", None)
            render_state_method = getattr(component, "is_render_state_created", None)
            registered = bool(registered_method()) if callable(registered_method) else None
            render_state = bool(render_state_method()) if callable(render_state_method) else None
            world_attached = component.get_world() == pawn.get_world()
            owner_attached = component.get_owner() == actor
            records.append({
                "component": component.get_path_name(),
                "class": component.get_class().get_name(),
                "mesh": mesh,
                "approved_grass": mesh in APPROVED_GRASS,
                "visible": bool(component.get_editor_property("visible")),
                "hidden_in_game": bool(component.get_editor_property("hidden_in_game")),
                "registered": registered,
                "render_state_created": render_state,
                "registration_api_exposed": callable(registered_method),
                "render_state_api_exposed": callable(render_state_method),
                "pie_world_attached": world_attached,
                "foliage_actor_owned": owner_attached,
                "origin": vec(origin),
                "origin_distance_to_player_cm": distance,
            })
    approved = [item for item in records if item["approved_grass"] and item["visible"] and not item["hidden_in_game"]]
    active_near = [
        item for item in approved
        if item["pie_world_attached"] and item["foliage_actor_owned"]
        and item["origin_distance_to_player_cm"] <= MAX_ACTIVE_GRASS_ORIGIN_DISTANCE_CM
    ]
    return {
        "foliage_actor": actor.get_path_name() if actor is not None else None,
        "static_mesh_component_count": len(records),
        "approved_visible_grass_component_count": len(approved),
        "approved_world_owned_grass_within_cull_range_count": len(active_near),
        "registration_render_state_api_available": any(
            item["registration_api_exposed"] and item["render_state_api_exposed"] for item in approved
        ),
        "nearest_approved_grass_origin_distance_cm": min(
            (item["origin_distance_to_player_cm"] for item in approved), default=None
        ),
        "components": records,
    }


class R29:
    def __init__(self):
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.handle = None
        self.phase = "PREPARE"
        self.phase_started = time.monotonic()
        self.world = None
        self.spawner = None
        self.center = None
        self.radius = None
        self.pawn = None
        self.movement = None
        self.input = None
        self.move_action = None
        self.grounded_frames = 0
        self.walk_start = None
        self.max_tangent_speed = 0.0
        self.screenshot_requested = False
        self.report = {
            "schema": "redmmo.ppg_profile_v1.grass_eligibility.reload_pie.r29.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "evidence_class": "automation_plus_real_gpu_capture_pending_pixel_review",
            "phase": self.phase,
        }

    def set_phase(self, phase):
        self.phase = phase
        self.phase_started = time.monotonic()
        self.report["phase"] = phase
        unreal.log("REDMMO_R29_PHASE " + phase)

    def authenticate(self):
        active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(active == PROJECT.resolve(strict=True), "Wrong active project")
        require(not RESULT.exists() and not SCREENSHOT.exists(), "R29 output no-clobber failed")
        require(sha256(PROJECT) == PROJECT_SHA, "Project descriptor drift")
        require(sha256(HOME_FILE) == HOME_SHA, "R26 home-map drift")
        require(sha256(PROFILE_FILE) == PROFILE_SHA, "ProfileV1 drift")
        require(R29_FOLIAGE_FILE.is_file() and sha256(R29_FOLIAGE_FILE) == R29_FOLIAGE_SHA, "R29 foliage drift")
        require(sha256(R26_RESULT) == R26_SHA, "R26 result drift")
        for path, expected in APPROVED_GRASS_FILES.items():
            require(path.is_file() and sha256(path) == expected, "Approved grass asset drift: " + str(path))
        for path, expected in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected, "Protected package drift: " + str(path))
        require(dirty_packages() == {"content": [], "maps": []}, "Editor started dirty")
        require(not self.level.is_in_play_in_editor(), "PIE already active")
        report = json.loads(R26_RESULT.read_text(encoding="utf-8"))
        require(report.get("status") == "PASS_R26_R25_LAND_PLAYERSTART_FRESH_RELOAD_MAPCHECK_NO_SAVE", "R26 did not pass")
        command = str(unreal.SystemLibrary.get_command_line()).lower()
        require("-d3d12" in command and "-renderoffscreen" in command and "-nullrhi" not in command, "R29 renderer gate failed")
        self.report["provider_gate_before"] = provider_gate()
        world = unreal.EditorLevelLibrary.get_editor_world()
        require(world is not None, "Editor world missing")
        path = world.get_path_name().split(":", 1)[0].split(".", 1)[0]
        require(path == HOME_MAP, "Wrong editor map: " + path)
        self.report["map_check"] = map_check(world)
        require(dirty_packages() == {"content": [], "maps": []}, "MapCheck dirtied packages")
        actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
        require(len(actors) == 12, "Editor actor count drift")
        starts = [actor for actor in actors if actor.get_class().get_name() == "PlayerStart"]
        require(len(starts) == 1, "Expected one PlayerStart")
        require(length(sub(starts[0].get_actor_location(), unreal.Vector(*report["playerstart_location"]))) <= 0.5, "PlayerStart drift")
        self.move_action = unreal.EditorAssetLibrary.load_asset(MOVE_ACTION)
        require(self.move_action is not None, "Move InputAction missing")
        profile = unreal.EditorAssetLibrary.load_asset(PLANET_DATA)
        require(profile is not None, "ProfileV1 missing")
        bindings = []
        for biome in list(profile.get_editor_property("biome_data")):
            bindings.append({
                "name": str(biome.get_editor_property("name")),
                "foliage": asset_path(biome.get_editor_property("foliage_data")),
            })
        require([item["foliage"] for item in bindings[:3]] == [R29_FOLIAGE] * 3, "R29 biome binding missing")
        self.report["fresh_reload_biome_bindings"] = bindings
        self.level.editor_request_begin_play()
        self.set_phase("WAIT_PIE")

    def bind_pie(self):
        world = self.editor.get_game_world()
        if world is None or not self.level.is_in_play_in_editor():
            return False
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        controller = unreal.GameplayStatics.get_player_controller(world, 0)
        if pawn is None or controller is None:
            return False
        spawners = [actor for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor) if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        require(len(spawners) == 1, "Expected one PIE PPG spawner")
        game_mode = unreal.GameplayStatics.get_game_mode(world)
        require(game_mode is not None and class_path(game_mode) == GAME_MODE_CLASS, "PIE GameMode drift")
        require(class_path(pawn) == PLAYER_CLASS, "PIE pawn class drift: " + str(class_path(pawn)))
        self.world = world
        self.pawn = pawn
        self.spawner = spawners[0]
        self.center = self.spawner.get_actor_location()
        planet = self.spawner.get_editor_property("planet_data")
        require(asset_path(planet) == PLANET_DATA, "PIE ProfileV1 binding drift")
        self.radius = float(planet.get_editor_property("planet_radius"))
        require(int(planet.get_editor_property("generation_seed")) == 1337, "PIE seed drift")
        self.movement = pawn.get_editor_property("character_movement")
        require(self.movement is not None, "CharacterMovement unavailable")
        self.input = input_subsystem_for_world(world)
        self.report["pie"] = {
            "world": world.get_path_name(),
            "pawn": pawn.get_path_name(),
            "pawn_class": class_path(pawn),
            "planet_center": vec(self.center),
            "planet_radius_cm": self.radius,
            "planet_data": PLANET_DATA,
        }
        self.set_phase("WAIT_GENERATION")
        return True

    def generation_ready(self):
        method = getattr(self.spawner, "get_planet_generation_status", None)
        require(callable(method), "PPG generation-status API unavailable")
        status = method()
        record = {
            "phase": str(status.get_editor_property("phase")),
            "progress": float(status.get_editor_property("progress")),
            "is_generating": bool(status.get_editor_property("is_generating")),
        }
        self.report["generation"] = record
        return "COMPLETE" in record["phase"].upper() and record["progress"] >= 0.999 and not record["is_generating"]

    def radial_state(self):
        location = self.pawn.get_actor_location()
        radial = normalized(sub(location, self.center))
        velocity = self.pawn.get_velocity()
        return location, radial, {
            "location": vec(location),
            "radial_elevation_above_sea_cm": length(sub(location, self.center)) - self.radius,
            "moving_on_ground": bool(self.movement.is_moving_on_ground()),
            "falling": bool(self.movement.is_falling()),
            "velocity": vec(velocity),
            "tangent_speed_cm_s": length(plane_project(velocity, radial)),
            "actor_up_dot_radial": dot(normalized(self.pawn.get_actor_up_vector()), radial),
        }

    def finalize(self):
        require(SCREENSHOT.is_file() and SCREENSHOT.stat().st_size > 0, "Real-GPU screenshot missing")
        self.level.editor_request_end_play()
        self.set_phase("WAIT_PIE_STOP")

    def finish_after_stop(self):
        require(not self.level.is_in_play_in_editor(), "PIE did not stop")
        require(dirty_packages() == {"content": [], "maps": []}, "PIE dirtied packages")
        require(sha256(HOME_FILE) == HOME_SHA, "PIE changed home map")
        require(sha256(PROFILE_FILE) == PROFILE_SHA, "PIE changed ProfileV1")
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "Protected package changed: " + str(path))
        self.report.update({
            "status": "PASS_R29C_FRESH_RELOAD_MAPCHECK_RUNTIME_NEAR_GRASS_PENDING_PIXEL_REVIEW",
            "screenshot": {"path": str(SCREENSHOT), "bytes": SCREENSHOT.stat().st_size, "sha256": sha256(SCREENSHOT)},
            "map_sha256_after": sha256(HOME_FILE),
            "profile_sha256_after": sha256(PROFILE_FILE),
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "save_called": False,
            "completed_utc": now(),
            "claim_limit": (
                "Fresh reload, MapCheck, runtime generation, saved-spawn grounding/radial movement and near-player PIE-world-owned approved grass identity only. "
                "PPGGPUFoliageComponent does not expose registration/render-state methods to Unreal Python; GPU pixels remain the visual authority. "
                "Grass pixel visibility requires independent screenshot review; day/night, broader gameplay, standalone, "
                "replication, multiplayer and player approval remain pending."
            ),
        })
        atomic_json(RESULT, self.report)
        unreal.log("REDMMO_R29_PASS")
        self.schedule_quit(4.0)

    def fail(self, error):
        self.report.update({
            "status": "FAIL",
            "error": str(error),
            "traceback": traceback.format_exc(),
            "failed_phase": self.phase,
            "home_map_sha256_observed": sha256(HOME_FILE) if HOME_FILE.is_file() else None,
            "profile_sha256_observed": sha256(PROFILE_FILE) if PROFILE_FILE.is_file() else None,
            "completed_utc": now(),
        })
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        if not RESULT.exists():
            atomic_json(RESULT, self.report)
        self.schedule_quit(4.0)

    def schedule_quit(self, delay):
        started = time.monotonic()
        old = self.handle
        if old is not None:
            try:
                unreal.unregister_slate_post_tick_callback(old)
            except Exception:
                pass
        def quit_tick(_delta):
            if time.monotonic() - started < delay:
                return
            try:
                unreal.unregister_slate_post_tick_callback(self.handle)
            except Exception:
                pass
            self.handle = None
            unreal.SystemLibrary.quit_editor()
        self.handle = unreal.register_slate_post_tick_callback(quit_tick)

    def tick(self, _delta):
        try:
            elapsed = time.monotonic() - self.phase_started
            if self.phase == "PREPARE":
                self.authenticate()
            elif self.phase == "WAIT_PIE":
                require(elapsed <= 20.0, "PIE startup timeout")
                self.bind_pie()
            elif self.phase == "WAIT_GENERATION":
                require(elapsed <= 240.0, "PPG generation timeout")
                if self.generation_ready():
                    self.set_phase("WAIT_GROUNDED")
            elif self.phase == "WAIT_GROUNDED":
                require(elapsed <= 90.0, "Trooper grounding timeout")
                _location, _radial, state = self.radial_state()
                if state["moving_on_ground"] and not state["falling"]:
                    self.grounded_frames += 1
                else:
                    self.grounded_frames = 0
                if self.grounded_frames >= 20:
                    require(state["radial_elevation_above_sea_cm"] >= MIN_ELEVATION_CM, "Saved spawn is not above native sea datum")
                    require(state["actor_up_dot_radial"] >= 0.98, "Trooper up is not radial")
                    self.report["grounded_spawn"] = state
                    up = normalized(sub(self.pawn.get_actor_location(), self.center))
                    forward = plane_project(self.pawn.get_actor_forward_vector(), up)
                    require(length(forward) >= 0.90, "Trooper forward is not tangent")
                    controller = unreal.GameplayStatics.get_player_controller(self.world, 0)
                    controller.set_control_rotation(unreal.MathLibrary.make_rot_from_xz(normalized(forward), up))
                    self.set_phase("WAIT_FOLIAGE")
            elif self.phase == "WAIT_FOLIAGE":
                require(elapsed <= FOLIAGE_SETTLE_SECONDS + 40.0, "Foliage settle timeout")
                if elapsed >= FOLIAGE_SETTLE_SECONDS:
                    state = foliage_state(self.spawner, self.pawn)
                    self.report["runtime_foliage"] = state
                    require(
                        state["approved_world_owned_grass_within_cull_range_count"] > 0,
                        "No PIE-world-owned approved grass component exists within cull range",
                    )
                    task = unreal.AutomationLibrary.take_high_res_screenshot(1280, 720, str(SCREENSHOT))
                    require(task is not None, "Screenshot request failed")
                    self.screenshot_requested = True
                    self.set_phase("WAIT_SCREENSHOT")
            elif self.phase == "WAIT_SCREENSHOT":
                require(elapsed <= 25.0, "Screenshot timeout")
                if SCREENSHOT.is_file() and SCREENSHOT.stat().st_size > 0:
                    self.walk_start = self.pawn.get_actor_location()
                    self.set_phase("WALK")
            elif self.phase == "WALK":
                require(elapsed <= 20.0, "Radial walk timeout")
                self.input.inject_input_vector_for_action(self.move_action, unreal.Vector(0.0, 1.0, 0.0), [], [])
                location, radial, state = self.radial_state()
                tangent_displacement = length(plane_project(sub(location, self.walk_start), radial))
                self.max_tangent_speed = max(self.max_tangent_speed, state["tangent_speed_cm_s"])
                if tangent_displacement >= MIN_TANGENT_WALK_CM:
                    self.input.inject_input_vector_for_action(self.move_action, unreal.Vector(), [], [])
                    self.report["radial_walk"] = {
                        "start": vec(self.walk_start),
                        "end": vec(location),
                        "tangent_displacement_cm": tangent_displacement,
                        "max_tangent_speed_cm_s": self.max_tangent_speed,
                        "radial_elevation_after_cm": state["radial_elevation_above_sea_cm"],
                        "actor_up_dot_radial": state["actor_up_dot_radial"],
                    }
                    require(state["radial_elevation_above_sea_cm"] >= MIN_ELEVATION_CM, "Trooper walked below sea datum")
                    self.finalize()
            elif self.phase == "WAIT_PIE_STOP":
                require(elapsed <= 15.0, "PIE stop timeout")
                if not self.level.is_in_play_in_editor():
                    self.finish_after_stop()
        except Exception as error:
            self.fail(error)

    def start(self):
        self.handle = unreal.register_slate_post_tick_callback(self.tick)


try:
    _R29 = R29()
    _R29.start()
except Exception as bootstrap_error:
    DIAG.mkdir(parents=True, exist_ok=True)
    atomic_json(RESULT, {
        "schema": "redmmo.ppg_profile_v1.grass_eligibility.reload_pie.r29.v1",
        "status": "FAIL",
        "error": str(bootstrap_error),
        "traceback": traceback.format_exc(),
        "completed_utc": now(),
    })
    unreal.SystemLibrary.quit_editor()
