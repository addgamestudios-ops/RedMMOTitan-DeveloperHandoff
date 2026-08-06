"""Rollback-backed R34 painted-ground scale correction and D3D12 proof."""

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
SURFACE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/MI_PPG_ProfileV1_Surface"
SURFACE_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\MI_PPG_ProfileV1_Surface.uasset"
SURFACE_SHA = "FBB3A58782DEED69D93BB2369387873FA2DA7FEAA93F47CBA289FC61EBEFBD66"
SURFACE_PARENT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/M_PPG_ProfileV1_SurfaceParent"
SURFACE_PARENT_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\M_PPG_ProfileV1_SurfaceParent.uasset"
SURFACE_PARENT_SHA = "5B433BA09CCBB50EFC71A9F2C9100BF264274249A1B4AC2BE5E95126F4644768"
GRASS_MATERIAL_FILES = [
    PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_A_R10N.uasset",
    PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_B_R10N.uasset",
]
GRASS_MATERIAL_SHAS = [
    "91A0E7233A5922A921FB4CF8692B8631DBB7AEFE7D3D106FDB63C44DB412CE47",
    "19D1B594553977A6A7BA116271F103DCD4044F8F24C3E8B5CF8F596082A9F68E",
]
APPROVED_GRASS = {
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_A_R10N",
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_B_R10N",
}
ROLLBACK = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforePaintedGround_R34_20260805T1355Z")
ROLLBACK_ASSET = ROLLBACK / "MI_PPG_ProfileV1_Surface.uasset"
ROLLBACK_MANIFEST = ROLLBACK / "pre_mutation_manifest.json"
ROLLBACK_MANIFEST_SHA = "D0F17B88A609889CD849259EBC7E859F9162639E9E565C02817D4BE4ED0F3293"
PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}

DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PaintedGround_R34_20260805T1400Z")
RESULT = DIAG / "result.json"
NORMAL = DIAG / "player_scale_normal_lit_r34.png"
SURFACE_ONLY = DIAG / "painted_ground_lit_grass_hidden_r34.png"

TARGET_SCALARS = {
    "R10L_GroundUVScale": 24.0,
    "R10L_NormalAmount": 0.28,
}


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


class R34:
    def __init__(self):
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.handle = None
        self.phase = "PREPARE"
        self.started = time.monotonic()
        self.world = None
        self.spawner = None
        self.controller = None
        self.grass_visibility = []
        self.report = {
            "schema": "redmmo.painted_ground.apply_verify.r34.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "evidence_class": "automation_plus_real_gpu_visual_pending_independent_review",
        }

    def set_phase(self, phase):
        self.phase = phase
        self.started = time.monotonic()
        self.report["phase"] = phase
        unreal.log("REDMMO_R34_PHASE " + phase)

    def authenticate(self):
        active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(active == PROJECT.resolve(strict=True), "wrong project")
        require(not RESULT.exists() and not NORMAL.exists() and not SURFACE_ONLY.exists(), "R34 no-clobber failed")
        DIAG.mkdir(parents=True, exist_ok=True)
        for path, expected in (
            (PROJECT, PROJECT_SHA), (HOME_FILE, HOME_SHA), (PROFILE_FILE, PROFILE_SHA),
            (FOLIAGE_FILE, FOLIAGE_SHA), (SURFACE_FILE, SURFACE_SHA),
            (SURFACE_PARENT_FILE, SURFACE_PARENT_SHA), (ROLLBACK_ASSET, SURFACE_SHA),
            (ROLLBACK_MANIFEST, ROLLBACK_MANIFEST_SHA),
        ):
            require(path.is_file() and sha256(path) == expected, "input drift: " + str(path))
        for path, expected in zip(GRASS_MATERIAL_FILES, GRASS_MATERIAL_SHAS):
            require(path.is_file() and sha256(path) == expected, "approved grass drift: " + str(path))
        for path, expected in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected, "protected drift: " + str(path))
        require(dirty_packages() == {"content": [], "maps": []}, "editor started dirty")
        require(not self.level.is_in_play_in_editor(), "PIE already active")
        command = str(unreal.SystemLibrary.get_command_line()).lower()
        require("-d3d12" in command and "-renderoffscreen" in command and "-nullrhi" not in command, "renderer gate failed")
        self.report["provider_gate_before"] = provider_gate()
        world = unreal.EditorLevelLibrary.get_editor_world()
        require(world is not None and world.get_path_name().split(":", 1)[0].split(".", 1)[0] == HOME_MAP, "wrong map")
        self.set_phase("APPLYING")
        self.apply_surface_correction()
        require(dirty_packages() == {"content": [], "maps": []}, "surface save left dirty packages")
        self.level.editor_request_begin_play()
        self.set_phase("WAIT_PIE")

    def apply_surface_correction(self):
        instance = unreal.load_asset(SURFACE)
        require(instance is not None, "ProfileV1 surface missing")
        require(asset_path(instance.get_editor_property("parent")) == SURFACE_PARENT, "surface parent drift")
        editing = unreal.MaterialEditingLibrary
        names = {str(item) for item in editing.get_scalar_parameter_names(instance)}
        require(set(TARGET_SCALARS).issubset(names), "painted-ground controls missing")
        changes = {}
        for name, target in TARGET_SCALARS.items():
            before = float(editing.get_material_instance_scalar_parameter_value(instance, name))
            require(name != "R10L_GroundUVScale" or abs(before - 12.0) <= 0.0001, "unexpected UV baseline")
            require(name != "R10L_NormalAmount" or abs(before - 0.2) <= 0.0001, "unexpected normal baseline")
            editing.set_material_instance_scalar_parameter_value(instance, name, float(target))
            after = float(editing.get_material_instance_scalar_parameter_value(instance, name))
            require(abs(after - target) <= 0.0001, "surface scalar postcondition failed: " + name)
            changes[name] = {"before": before, "after": after}
        editing.update_material_instance(instance)
        require(unreal.EditorAssetLibrary.save_loaded_asset(instance, only_if_is_dirty=False), "surface save failed")
        after_hash = sha256(SURFACE_FILE)
        require(after_hash != SURFACE_SHA, "surface serialized hash did not change")
        self.report["surface_correction"] = {
            "material_instance": SURFACE,
            "parent": SURFACE_PARENT,
            "texture_set": {
                "base_color": "/Game/StylizedRocksPack_01/Common/TilingTextures/T_StylizedGrass_01_BC",
                "normal": "/Game/StylizedRocksPack_01/Common/TilingTextures/T_StylizedGrass_01_N",
                "orm": "/Game/StylizedRocksPack_01/Common/TilingTextures/T_StylizedGrass_01_ORM",
            },
            "parameters": changes,
            "before_sha256": SURFACE_SHA,
            "after_sha256": after_hash,
            "rollback": str(ROLLBACK),
        }

    def bind_pie(self):
        world = self.editor.get_game_world()
        if world is None or not self.level.is_in_play_in_editor():
            return False
        spawners = [actor for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor) if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        if unreal.GameplayStatics.get_player_pawn(world, 0) is None or len(spawners) != 1:
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

    def prepare_capture(self):
        self.controller, camera = camera_record(self.world)
        self.report["capture_camera"] = camera
        foliage_actor = self.spawner.get_foliage_actor()
        require(foliage_actor is not None, "foliage actor missing")
        components = []
        total_instances = 0
        for component in list(foliage_actor.get_components_by_class(unreal.StaticMeshComponent)):
            if component.get_class().get_name() != "PPGGPUFoliageComponent":
                continue
            mesh = asset_path(component.get_editor_property("static_mesh"))
            if mesh not in APPROVED_GRASS:
                continue
            diag = unreal.RedPPGFoliageDiagnostics.inspect_component(component).to_dict()
            count = next(int(value) for key, value in diag.items() if str(key).replace("_", "").lower() == "numinstances")
            require(count > 0, "approved grass component has zero instances")
            total_instances += count
            components.append(component)
        require(len(components) == 196, "approved grass component-count drift")
        require(total_instances == 2218356, "approved grass instance-count drift")
        self.report["runtime_grass_preserved"] = {
            "components": len(components),
            "instances": total_instances,
            "materials_sha256": {str(path): sha256(path) for path in GRASS_MATERIAL_FILES},
        }
        self.grass_visibility = [
            (component, bool(component.get_editor_property("visible")), bool(component.get_editor_property("hidden_in_game")))
            for component in components
        ]
        unreal.SystemLibrary.execute_console_command(self.world, "DisableAllScreenMessages", self.controller)
        unreal.SystemLibrary.execute_console_command(self.world, "viewmode lit", self.controller)
        self.set_phase("SETTLE_NORMAL")

    def hide_grass(self):
        for component, _visible, _hidden in self.grass_visibility:
            component.set_visibility(False, True)
            component.set_hidden_in_game(True)
        self.set_phase("SETTLE_SURFACE")

    def restore_grass(self):
        for component, visible, hidden in self.grass_visibility:
            component.set_visibility(visible, True)
            component.set_hidden_in_game(hidden)
        self.report["runtime_grass_preserved"]["restored_components"] = len(self.grass_visibility)

    def request_capture(self, path):
        task = unreal.AutomationLibrary.take_high_res_screenshot(1280, 720, str(path))
        require(task is not None, "screenshot request failed: " + str(path))

    def finish_capture(self):
        self.restore_grass()
        require(NORMAL.is_file() and NORMAL.stat().st_size > 0, "normal screenshot missing")
        require(SURFACE_ONLY.is_file() and SURFACE_ONLY.stat().st_size > 0, "surface screenshot missing")
        self.report["captures"] = {
            "player_scale_normal_lit": {"path": str(NORMAL), "bytes": NORMAL.stat().st_size, "sha256": sha256(NORMAL)},
            "painted_ground_lit_grass_hidden": {"path": str(SURFACE_ONLY), "bytes": SURFACE_ONLY.stat().st_size, "sha256": sha256(SURFACE_ONLY)},
        }
        self.level.editor_request_end_play()
        self.set_phase("WAIT_STOP")

    def finish(self):
        require(not self.level.is_in_play_in_editor(), "PIE did not stop")
        require(dirty_packages() == {"content": [], "maps": []}, "PIE left dirty packages")
        for path, expected in ((HOME_FILE, HOME_SHA), (PROFILE_FILE, PROFILE_SHA), (FOLIAGE_FILE, FOLIAGE_SHA), (SURFACE_PARENT_FILE, SURFACE_PARENT_SHA)):
            require(sha256(path) == expected, "post-PIE drift: " + str(path))
        for path, expected in zip(GRASS_MATERIAL_FILES, GRASS_MATERIAL_SHAS):
            require(sha256(path) == expected, "approved grass changed: " + str(path))
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "protected post-PIE drift: " + str(path))
        self.report.update({
            "status": "PASS_R34_PAINTED_GROUND_SAVED_AND_D3D12_CAPTURED_PENDING_PIXEL_REVIEW",
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "home_sha256_before_after": HOME_SHA,
            "profile_sha256_before_after": PROFILE_SHA,
            "foliage_sha256_before_after": FOLIAGE_SHA,
            "surface_parent_sha256_before_after": SURFACE_PARENT_SHA,
            "surface_sha256_after": sha256(SURFACE_FILE),
            "completed_utc": now(),
            "claim_limit": "Project-owned surface MI correction and D3D12 captures only; terrain, topology, water, grass placement, gameplay, package, replication, and multiplayer are not claimed.",
        })
        atomic_json(RESULT, self.report)
        unreal.log("REDMMO_R34_PASS")
        self.phase = "DONE"
        self.schedule_quit(3.0)

    def fail(self, error):
        failed_phase = self.phase
        self.phase = "FAILED"
        self.report.update({"status": "FAIL", "error": str(error), "traceback": traceback.format_exc(), "failed_phase": failed_phase, "completed_utc": now()})
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        if not RESULT.exists():
            atomic_json(RESULT, self.report)
        self.schedule_quit(3.0)

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
                require(elapsed <= 20.0, "PIE startup timeout")
                self.bind_pie()
            elif self.phase == "WAIT_GENERATION":
                require(elapsed <= 240.0, "generation timeout")
                if self.generation_ready():
                    self.set_phase("SETTLE")
            elif self.phase == "SETTLE":
                require(elapsed <= 35.0, "settle timeout")
                if elapsed >= 15.0:
                    self.prepare_capture()
            elif self.phase == "SETTLE_NORMAL":
                require(elapsed <= 15.0, "normal settle timeout")
                if elapsed >= 3.0:
                    self.request_capture(NORMAL)
                    self.set_phase("WAIT_NORMAL")
            elif self.phase == "WAIT_NORMAL":
                require(elapsed <= 25.0, "normal screenshot timeout")
                if NORMAL.is_file() and NORMAL.stat().st_size > 0:
                    self.hide_grass()
            elif self.phase == "SETTLE_SURFACE":
                require(elapsed <= 15.0, "surface settle timeout")
                if elapsed >= 3.0:
                    self.request_capture(SURFACE_ONLY)
                    self.set_phase("WAIT_SURFACE")
            elif self.phase == "WAIT_SURFACE":
                require(elapsed <= 25.0, "surface screenshot timeout")
                if SURFACE_ONLY.is_file() and SURFACE_ONLY.stat().st_size > 0:
                    self.finish_capture()
            elif self.phase == "WAIT_STOP":
                require(elapsed <= 15.0, "PIE stop timeout")
                if not self.level.is_in_play_in_editor():
                    self.finish()
        except Exception as error:
            self.fail(error)

    def start(self):
        self.handle = unreal.register_slate_post_tick_callback(self.tick)


try:
    _R34 = R34()
    _R34.start()
except Exception as bootstrap_error:
    DIAG.mkdir(parents=True, exist_ok=True)
    atomic_json(RESULT, {"schema": "redmmo.painted_ground.apply_verify.r34.v1", "status": "FAIL", "error": str(bootstrap_error), "traceback": traceback.format_exc(), "completed_utc": now()})
    unreal.SystemLibrary.quit_editor()
