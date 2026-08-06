"""Read-only R40 exact-camera default versus post-R33-cycle wireframe audit."""

from __future__ import annotations

import hashlib
import json
import math
import os
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
FOLIAGE_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_GrassEligible_R29.uasset"
FOLIAGE_SHA = "D1ACEE4F403D2082FF49CB57D52907AAADA0C20D06386576C435557CF49404D8"
SURFACE_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\MI_PPG_ProfileV1_Surface.uasset"
SURFACE_SHA = "FBB3A58782DEED69D93BB2369387873FA2DA7FEAA93F47CBA289FC61EBEFBD66"
PARENT_FILE = PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R32\Materials\M_GrassChunks_PPGReadable_R32.uasset"
PARENT_SHA = "2BD2B8DD41C611CF1250F1A39C40D3B4A7C47B5EB71ECD1497732546B80F0210"
GRASS_FILES = {
    PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_A_R10N.uasset": "91A0E7233A5922A921FB4CF8692B8631DBB7AEFE7D3D106FDB63C44DB412CE47",
    PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_B_R10N.uasset": "19D1B594553977A6A7BA116271F103DCD4044F8F24C3E8B5CF8F596082A9F68E",
}
GRASS_MESHES = {
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_A_R10N",
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_B_R10N",
}
PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"): "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"): "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}
R33_CAMERA = {
    "location": [191297894.99445367, 196950314.12190434, -421017759.8003976],
    "rotation": [20.41166676895961, -46.37008029227465, 111.80009049544566],
    "fov": 90.0,
}
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_GrassCaptureState_R40_20260805T1504Z")
RESULT = DIAG / "result.json"
DEFAULT_WIREFRAME = DIAG / "default_wireframe_r40.png"
POST_CYCLE_WIREFRAME = DIAG / "post_r33_cycle_wireframe_r40.png"


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
    require(all(state.values()), "provider listener active: " + repr(state))
    return state


def asset_path(value):
    if value is None:
        return None
    path = value.get_path_name().split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def dirty_packages():
    return {
        "content": sorted({asset_path(item) for item in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}),
        "maps": sorted({asset_path(item) for item in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()}),
    }


def normalized(value):
    return str(value).replace("_", "").replace(" ", "").lower()


def struct_field(value, wanted):
    fields = value.to_dict()
    target = normalized(wanted)
    matches = [item for key, item in fields.items() if normalized(key) in (target, "b" + target)]
    require(len(matches) == 1, "expected reflected field {} in {}".format(wanted, list(fields)))
    return matches[0]


def vec(value):
    return [float(value.x), float(value.y), float(value.z)]


def camera_record(world):
    controller = unreal.GameplayStatics.get_player_controller(world, 0)
    require(controller is not None, "player controller missing")
    manager = controller.get_editor_property("player_camera_manager")
    require(manager is not None, "camera manager missing")
    rotation = manager.get_camera_rotation()
    return controller, {
        "location": vec(manager.get_camera_location()),
        "rotation": [float(rotation.pitch), float(rotation.yaw), float(rotation.roll)],
        "fov": float(manager.get_fov_angle()),
    }


def camera_delta(actual):
    return {
        "location_cm_max_abs": max(abs(a - b) for a, b in zip(actual["location"], R33_CAMERA["location"])),
        "rotation_deg_max_abs": max(abs(a - b) for a, b in zip(actual["rotation"], R33_CAMERA["rotation"])),
        "fov_max_abs": abs(actual["fov"] - R33_CAMERA["fov"]),
    }


def component_summary(components):
    records = []
    for component in components:
        diag = unreal.RedPPGFoliageDiagnostics.inspect_component(component)
        records.append({
            "visible": bool(component.get_editor_property("visible")),
            "hidden_in_game": bool(component.get_editor_property("hidden_in_game")),
            "instances": int(struct_field(diag, "num_instances")),
            "registered": bool(struct_field(diag, "registered")),
            "render_state_created": bool(struct_field(diag, "render_state_created")),
            "scene_proxy": bool(struct_field(diag, "has_scene_proxy")),
            "last_render": float(struct_field(diag, "last_render_time_on_screen")),
        })
    return {
        "components": len(records),
        "instances": sum(item["instances"] for item in records),
        "visible_true": sum(item["visible"] for item in records),
        "hidden_in_game_true": sum(item["hidden_in_game"] for item in records),
        "registered": sum(item["registered"] for item in records),
        "render_state_created": sum(item["render_state_created"] for item in records),
        "scene_proxy": sum(item["scene_proxy"] for item in records),
        "positive_last_render": sum(item["last_render"] > 0.0 for item in records),
    }


class R40:
    def __init__(self):
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.handle = None
        self.phase = "PREPARE"
        self.started = time.monotonic()
        self.world = None
        self.controller = None
        self.spawner = None
        self.grass = []
        self.visibility_states = []
        self.report = {
            "schema": "redmmo.grass_capture_state.audit.r40.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "evidence_class": "automation_plus_diagnostic_gpu_buffers",
        }

    def set_phase(self, phase):
        self.phase = phase
        self.started = time.monotonic()
        self.report["phase"] = phase
        unreal.log("REDMMO_R40_PHASE " + phase)

    def authenticate(self):
        active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(active == PROJECT.resolve(strict=True), "wrong project")
        require(not RESULT.exists() and not DEFAULT_WIREFRAME.exists() and not POST_CYCLE_WIREFRAME.exists(), "R40 no-clobber failed")
        for path, expected in (
            (PROJECT, PROJECT_SHA), (HOME_FILE, HOME_SHA), (PROFILE_FILE, PROFILE_SHA),
            (FOLIAGE_FILE, FOLIAGE_SHA), (SURFACE_FILE, SURFACE_SHA), (PARENT_FILE, PARENT_SHA),
        ):
            require(path.is_file() and sha256(path) == expected, "input drift: " + str(path))
        for path, expected in list(GRASS_FILES.items()) + list(PROTECTED.items()):
            require(path.is_file() and sha256(path) == expected, "grass/protected drift: " + str(path))
        require(dirty_packages() == {"content": [], "maps": []}, "editor started dirty")
        require(not self.level.is_in_play_in_editor(), "PIE already active")
        command = str(unreal.SystemLibrary.get_command_line()).lower()
        require("-d3d12" in command and "-renderoffscreen" in command and "-nullrhi" not in command, "renderer gate failed")
        self.report["provider_gate_before"] = provider_gate()
        world = unreal.EditorLevelLibrary.get_editor_world()
        require(world is not None and world.get_path_name().split(":", 1)[0].split(".", 1)[0] == HOME_MAP, "wrong map")
        self.level.editor_request_begin_play()
        self.set_phase("WAIT_PIE")

    def bind_pie(self):
        world = self.editor.get_game_world()
        if world is None or not self.level.is_in_play_in_editor():
            return False
        spawners = [actor for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor) if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        if len(spawners) != 1 or unreal.GameplayStatics.get_player_pawn(world, 0) is None:
            return False
        self.world = world
        self.spawner = spawners[0]
        self.set_phase("WAIT_GENERATION")
        return True

    def generation_ready(self):
        status = self.spawner.get_planet_generation_status()
        record = {
            "phase": str(status.get_editor_property("phase")),
            "progress": float(status.get_editor_property("progress")),
            "is_generating": bool(status.get_editor_property("is_generating")),
        }
        self.report["generation"] = record
        return "COMPLETE" in record["phase"].upper() and record["progress"] >= 0.999 and not record["is_generating"]

    def prepare_default(self):
        self.controller, camera = camera_record(self.world)
        delta = camera_delta(camera)
        require(delta["location_cm_max_abs"] <= 0.1 and delta["rotation_deg_max_abs"] <= 0.001 and delta["fov_max_abs"] <= 0.001, "R33 camera drift: " + repr(delta))
        self.report["camera"] = camera
        self.report["camera_delta_from_r33"] = delta
        foliage_actor = self.spawner.get_foliage_actor()
        require(foliage_actor is not None, "foliage actor missing")
        self.grass = [
            component for component in list(foliage_actor.get_components_by_class(unreal.StaticMeshComponent))
            if component.get_class().get_name() == "PPGGPUFoliageComponent"
            and asset_path(component.get_editor_property("static_mesh")) in GRASS_MESHES
        ]
        require(len(self.grass) == 196, "approved component-count drift")
        self.report["default_state_before_wireframe"] = component_summary(self.grass)
        unreal.SystemLibrary.execute_console_command(self.world, "DisableAllScreenMessages", self.controller)
        unreal.SystemLibrary.execute_console_command(self.world, "viewmode wireframe", self.controller)
        self.set_phase("SETTLE_DEFAULT_WIREFRAME")

    def request_capture(self, path, next_phase):
        task = unreal.AutomationLibrary.take_high_res_screenshot(1280, 720, str(path))
        require(task is not None, "screenshot request failed: " + str(path))
        self.set_phase(next_phase)

    def begin_r33_cycle(self):
        hidden = 0
        forced_grass = 0
        for actor in unreal.GameplayStatics.get_all_actors_of_class(self.world, unreal.Actor):
            for component in list(actor.get_components_by_class(unreal.PrimitiveComponent)):
                visible = bool(component.get_editor_property("visible"))
                hidden_in_game = bool(component.get_editor_property("hidden_in_game"))
                self.visibility_states.append((component, visible, hidden_in_game))
                mesh = asset_path(component.get_editor_property("static_mesh")) if isinstance(component, unreal.StaticMeshComponent) else None
                if component.get_class().get_name() == "PPGGPUFoliageComponent" and mesh in GRASS_MESHES:
                    component.set_visibility(True, True)
                    component.set_hidden_in_game(False)
                    forced_grass += 1
                else:
                    component.set_visibility(False, True)
                    component.set_hidden_in_game(True)
                    hidden += 1
        self.report["r33_cycle"] = {
            "captured_primitive_states": len(self.visibility_states),
            "hidden_non_grass_primitives": hidden,
            "forced_grass_components": forced_grass,
            "saved": False,
        }
        unreal.SystemLibrary.execute_console_command(self.world, "viewmode unlit", self.controller)
        self.set_phase("SETTLE_R33_UNLIT")

    def restore_r33_cycle(self):
        for component, visible, hidden_in_game in self.visibility_states:
            if component is not None:
                component.set_visibility(visible, True)
                component.set_hidden_in_game(hidden_in_game)
        unreal.SystemLibrary.execute_console_command(self.world, "viewmode wireframe", self.controller)
        self.set_phase("SETTLE_POST_CYCLE_WIREFRAME")

    def finish_captures(self):
        require(DEFAULT_WIREFRAME.is_file() and POST_CYCLE_WIREFRAME.is_file(), "diagnostic capture missing")
        self.report["post_cycle_state"] = component_summary(self.grass)
        self.report["captures"] = {
            "default_wireframe": {"path": str(DEFAULT_WIREFRAME), "bytes": DEFAULT_WIREFRAME.stat().st_size, "sha256": sha256(DEFAULT_WIREFRAME)},
            "post_r33_cycle_wireframe": {"path": str(POST_CYCLE_WIREFRAME), "bytes": POST_CYCLE_WIREFRAME.stat().st_size, "sha256": sha256(POST_CYCLE_WIREFRAME)},
        }
        for component, visible, hidden_in_game in self.visibility_states:
            if component is not None:
                require(bool(component.get_editor_property("visible")) == visible, "visible restore failed")
                require(bool(component.get_editor_property("hidden_in_game")) == hidden_in_game, "hidden restore failed")
        self.level.editor_request_end_play()
        self.set_phase("WAIT_STOP")

    def finish(self):
        require(not self.level.is_in_play_in_editor(), "PIE did not stop")
        require(dirty_packages() == {"content": [], "maps": []}, "PIE dirtied packages")
        for path, expected in (
            (HOME_FILE, HOME_SHA), (PROFILE_FILE, PROFILE_SHA), (FOLIAGE_FILE, FOLIAGE_SHA),
            (SURFACE_FILE, SURFACE_SHA), (PARENT_FILE, PARENT_SHA),
        ):
            require(sha256(path) == expected, "post-PIE drift: " + str(path))
        for path, expected in list(GRASS_FILES.items()) + list(PROTECTED.items()):
            require(sha256(path) == expected, "grass/protected post-drift: " + str(path))
        self.report.update({
            "status": "PASS_R40_DEFAULT_VS_POST_R33_CYCLE_WIREFRAME_CAPTURED_PENDING_PIXEL_COMPARISON",
            "completed_utc": now(),
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "save_called": False,
            "normal_beauty_capture_called": False,
            "claim_limit": "Exact-camera wireframe diagnostic buffers only; no save, normal beauty frame, visual acceptance, gameplay, package or multiplayer claim.",
        })
        atomic_json(RESULT, self.report)
        unreal.log("REDMMO_R40_PASS")
        self.phase = "DONE"
        self.schedule_quit(3.0)

    def fail(self, error):
        failed_phase = self.phase
        self.phase = "FAILED"
        self.report.update({"status": "FAIL", "failed_phase": failed_phase, "completed_utc": now(), "error": str(error), "traceback": traceback.format_exc()})
        for component, visible, hidden_in_game in self.visibility_states:
            if component is not None:
                try:
                    component.set_visibility(visible, True)
                    component.set_hidden_in_game(hidden_in_game)
                except Exception:
                    pass
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        if not RESULT.exists():
            atomic_json(RESULT, self.report)
        unreal.log_error("REDMMO_R40_FAIL " + str(error))
        self.schedule_quit(2.0)

    def schedule_quit(self, delay):
        started = time.monotonic()
        old = self.handle
        if old is not None:
            try:
                unreal.unregister_slate_post_tick_callback(old)
            except Exception:
                pass

        def tick(_delta):
            if time.monotonic() - started < delay:
                return
            try:
                unreal.unregister_slate_post_tick_callback(self.handle)
            except Exception:
                pass
            unreal.SystemLibrary.quit_editor()

        self.handle = unreal.register_slate_post_tick_callback(tick)

    def tick(self, _delta):
        try:
            elapsed = time.monotonic() - self.started
            if self.phase == "PREPARE":
                self.authenticate()
            elif self.phase == "WAIT_PIE":
                require(elapsed <= 25.0, "PIE startup timeout")
                self.bind_pie()
            elif self.phase == "WAIT_GENERATION":
                require(elapsed <= 240.0, "generation timeout")
                if self.generation_ready():
                    self.set_phase("SETTLE_DEFAULT")
            elif self.phase == "SETTLE_DEFAULT":
                require(elapsed <= 30.0, "default settle timeout")
                if elapsed >= 10.0:
                    self.prepare_default()
            elif self.phase == "SETTLE_DEFAULT_WIREFRAME":
                require(elapsed <= 15.0, "default wireframe settle timeout")
                if elapsed >= 3.0:
                    self.request_capture(DEFAULT_WIREFRAME, "WAIT_DEFAULT_CAPTURE")
            elif self.phase == "WAIT_DEFAULT_CAPTURE":
                require(elapsed <= 25.0, "default wireframe capture timeout")
                if DEFAULT_WIREFRAME.is_file() and DEFAULT_WIREFRAME.stat().st_size > 0:
                    self.begin_r33_cycle()
            elif self.phase == "SETTLE_R33_UNLIT":
                require(elapsed <= 15.0, "R33 unlit-cycle settle timeout")
                if elapsed >= 3.0:
                    self.restore_r33_cycle()
            elif self.phase == "SETTLE_POST_CYCLE_WIREFRAME":
                require(elapsed <= 15.0, "post-cycle wireframe settle timeout")
                if elapsed >= 3.0:
                    self.request_capture(POST_CYCLE_WIREFRAME, "WAIT_POST_CAPTURE")
            elif self.phase == "WAIT_POST_CAPTURE":
                require(elapsed <= 25.0, "post-cycle wireframe capture timeout")
                if POST_CYCLE_WIREFRAME.is_file() and POST_CYCLE_WIREFRAME.stat().st_size > 0:
                    self.finish_captures()
            elif self.phase == "WAIT_STOP":
                require(elapsed <= 15.0, "PIE stop timeout")
                if not self.level.is_in_play_in_editor():
                    self.finish()
        except Exception as error:
            self.fail(error)

    def start(self):
        self.handle = unreal.register_slate_post_tick_callback(self.tick)


try:
    _R40 = R40()
    _R40.start()
except Exception as bootstrap_error:
    atomic_json(RESULT, {"schema": "redmmo.grass_capture_state.audit.r40.v1", "status": "FAIL", "completed_utc": now(), "error": str(bootstrap_error), "traceback": traceback.format_exc()})
    unreal.SystemLibrary.quit_editor()
