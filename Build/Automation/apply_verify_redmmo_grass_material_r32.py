"""Rollback-backed R32 project-owned grass material correction and D3D12 proof."""

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
VENDOR_PARENT = "/Game/StylizedRocksPack_01/Common/GrassChunks/Materials/M_GrassChunks_Base"
VENDOR_PARENT_FILE = PROJECT.parent / r"Content\StylizedRocksPack_01\Common\GrassChunks\Materials\M_GrassChunks_Base.uasset"
VENDOR_PARENT_SHA = "B8FD57E1371DAEC8AAE33C9A4A4F15A9420F7BFD8A8F0F0138F36822355EEE10"
R32_PARENT_FOLDER = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R32/Materials"
R32_PARENT_NAME = "M_GrassChunks_PPGReadable_R32"
R32_PARENT = R32_PARENT_FOLDER + "/" + R32_PARENT_NAME
R32_PARENT_FILE = PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R32\Materials\M_GrassChunks_PPGReadable_R32.uasset"
GRASS_MATERIALS = [
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Materials/MI_GrassChunks_DenseTall_A_R10N",
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Materials/MI_GrassChunks_DenseTall_B_R10N",
]
GRASS_MATERIAL_FILES = [
    PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_A_R10N.uasset",
    PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_B_R10N.uasset",
]
GRASS_MATERIAL_SHAS = [
    "6B6410611A60F382B57BA92C35B585D4954F491434680F1B6E74080A578ECCA0",
    "FA3994C498C80335E2077AAF8EDD41AEF5A32C0B4E3EABA1BB02E1A10F63950B",
]
APPROVED_GRASS = {
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_A_R10N",
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_B_R10N",
}
ROLLBACK = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeGrassMaterial_R32_20260805T1318Z")
ROLLBACK_MANIFEST = ROLLBACK / "pre_mutation_manifest.json"
ROLLBACK_MANIFEST_SHA = "F18AF9BD2162D313FA7D93EE0F0DBB5013243BC944FA22F3694DA8DB180B2723"
PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_GrassMaterial_R32E_20260805T1350Z")
RESULT = DIAG / "result.json"
UNLIT = DIAG / "grass_only_unlit_r32.png"
NORMAL = DIAG / "player_scale_normal_lit_r32.png"

COLORS = [
    unreal.LinearColor(0.055, 0.300, 0.025, 1.0),
    unreal.LinearColor(0.075, 0.360, 0.035, 1.0),
]
HIGHLIGHTS = [
    unreal.LinearColor(0.220, 0.520, 0.070, 1.0),
    unreal.LinearColor(0.280, 0.600, 0.090, 1.0),
]
SCALARS = {
    "GrassColor_Custom_Enable": 1.0,
    "GrassColor_Effects_Enable": 1.0,
    "GrassColor_FromLandscape_Amount": 0.0,
    "GrassColor_Intensity": 0.95,
    "GrassColor_Contrast": 1.05,
    "GrassColor_Saturation": 0.05,
    "GrassColor_MinValue": 0.75,
    "GrassColor_MaxValue": 1.08,
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


def color(value):
    return [float(value.r), float(value.g), float(value.b), float(value.a)]


def distance(a, b):
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


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


def set_toggle(instance, name, value, record):
    scalar_names = {str(item) for item in unreal.MaterialEditingLibrary.get_scalar_parameter_names(instance)}
    switch_names = {str(item) for item in unreal.MaterialEditingLibrary.get_static_switch_parameter_names(instance)}
    require(name in scalar_names or name in switch_names, "material toggle missing: " + name)
    if name in scalar_names:
        before = float(unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(instance, name))
        unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(instance, name, float(value))
        after = float(unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(instance, name))
        require(abs(after - float(value)) <= 0.0001, "scalar postcondition failed: " + name)
        record[name] = {"kind": "scalar", "before": before, "after": float(value)}
    else:
        before = bool(unreal.MaterialEditingLibrary.get_material_instance_static_switch_parameter_value(instance, name))
        unreal.MaterialEditingLibrary.set_material_instance_static_switch_parameter_value(instance, name, bool(value))
        after = bool(unreal.MaterialEditingLibrary.get_material_instance_static_switch_parameter_value(instance, name))
        require(after == bool(value), "switch postcondition failed: " + name)
        record[name] = {"kind": "static_switch", "before": before, "after": bool(value)}


class R32:
    def __init__(self):
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.handle = None
        self.phase = "PREPARE"
        self.started = time.monotonic()
        self.world = None
        self.pawn = None
        self.spawner = None
        self.controller = None
        self.visibility_states = []
        self.report = {
            "schema": "redmmo.grass_material.apply_verify.r32.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "evidence_class": "automation_plus_real_gpu_visual_pending_independent_review",
        }

    def set_phase(self, phase):
        self.phase = phase
        self.started = time.monotonic()
        self.report["phase"] = phase
        unreal.log("REDMMO_R32_PHASE " + phase)

    def authenticate(self):
        active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(active == PROJECT.resolve(strict=True), "wrong project")
        require(not RESULT.exists() and not UNLIT.exists() and not NORMAL.exists(), "R32 no-clobber failed")
        DIAG.mkdir(parents=True, exist_ok=True)
        for path, expected in (
            (PROJECT, PROJECT_SHA), (HOME_FILE, HOME_SHA), (PROFILE_FILE, PROFILE_SHA),
            (FOLIAGE_FILE, FOLIAGE_SHA), (VENDOR_PARENT_FILE, VENDOR_PARENT_SHA),
            (ROLLBACK_MANIFEST, ROLLBACK_MANIFEST_SHA),
        ):
            require(path.is_file() and sha256(path) == expected, "input drift: " + str(path))
        for path, expected in zip(GRASS_MATERIAL_FILES, GRASS_MATERIAL_SHAS):
            require(path.is_file() and sha256(path) == expected, "grass material drift: " + str(path))
        for index, expected in enumerate(GRASS_MATERIAL_SHAS):
            backup = ROLLBACK / GRASS_MATERIAL_FILES[index].name
            require(backup.is_file() and sha256(backup) == expected, "rollback drift: " + str(backup))
        for path, expected in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected, "protected drift: " + str(path))
        require(dirty_packages() == {"content": [], "maps": []}, "editor started dirty")
        require(not self.level.is_in_play_in_editor(), "PIE already active")
        command = str(unreal.SystemLibrary.get_command_line()).lower()
        require("-d3d12" in command and "-renderoffscreen" in command and "-nullrhi" not in command, "renderer gate failed")
        self.report["provider_gate_before"] = provider_gate()
        world = unreal.EditorLevelLibrary.get_editor_world()
        require(world is not None and world.get_path_name().split(":", 1)[0].split(".", 1)[0] == HOME_MAP, "wrong map")
        # Saving/recompiling a material can pump Slate. Move out of PREPARE before
        # the operation so the post-tick callback cannot re-enter authentication.
        self.set_phase("APPLYING")
        self.apply_material_correction()
        require(dirty_packages() == {"content": [], "maps": []}, "material save left dirty packages")
        self.level.editor_request_begin_play()
        self.set_phase("WAIT_PIE")

    def apply_material_correction(self):
        vendor = unreal.load_asset(VENDOR_PARENT)
        require(vendor is not None, "vendor parent missing")
        unreal.EditorAssetLibrary.make_directory(R32_PARENT_FOLDER)
        if R32_PARENT_FILE.exists() or unreal.EditorAssetLibrary.does_asset_exist(R32_PARENT):
            parent = unreal.load_asset(R32_PARENT)
            require(parent is not None and asset_path(parent) == R32_PARENT, "partial R32 parent adoption failed")
            require(sha256(R32_PARENT_FILE) == "2BD2B8DD41C611CF1250F1A39C40D3B4A7C47B5EB71ECD1497732546B80F0210", "partial R32 parent drift")
            self.report["adopted_partial_parent"] = True
        else:
            parent = unreal.AssetToolsHelpers.get_asset_tools().duplicate_asset(
                R32_PARENT_NAME, R32_PARENT_FOLDER, vendor
            )
            require(parent is not None and asset_path(parent) == R32_PARENT, "parent duplicate failed")
            self.report["adopted_partial_parent"] = False
        compile_errors = []
        if not self.report["adopted_partial_parent"]:
            parent.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
            parent.set_editor_property("opacity_mask_clip_value", 0.3333)
            parent.set_editor_property("two_sided", True)
            compile_result = unreal.MaterialEditingLibrary.recompile_material(parent)
            compile_errors = [str(item) for item in (compile_result or []) if str(item).strip()]
            require(not compile_errors, "R32 parent compile errors: " + repr(compile_errors))
            require(unreal.EditorAssetLibrary.save_loaded_asset(parent, only_if_is_dirty=False), "R32 parent save failed")
        require(parent.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_MASKED, "R32 parent blend-mode postcondition failed")
        require(abs(float(parent.get_editor_property("opacity_mask_clip_value")) - 0.3333) <= 0.0001, "R32 parent clip postcondition failed")
        require(bool(parent.get_editor_property("two_sided")), "R32 parent two-sided postcondition failed")

        changes = []
        for index, package in enumerate(GRASS_MATERIALS):
            instance = unreal.load_asset(package)
            require(instance is not None, "grass material missing: " + package)
            record = {"material": package, "before_sha256": GRASS_MATERIAL_SHAS[index], "parameters": {}}
            unreal.MaterialEditingLibrary.set_material_instance_parent(instance, parent)
            require(asset_path(instance.get_editor_property("parent")) == R32_PARENT, "parent postcondition failed: " + package)
            for name, value in SCALARS.items():
                set_toggle(instance, name, value, record["parameters"])
            vector_names = {str(item) for item in unreal.MaterialEditingLibrary.get_vector_parameter_names(instance)}
            require("GrassColor_01" in vector_names and "GrassHighlights_Color" in vector_names, "grass vector controls missing")
            before_color = unreal.MaterialEditingLibrary.get_material_instance_vector_parameter_value(instance, "GrassColor_01")
            before_highlight = unreal.MaterialEditingLibrary.get_material_instance_vector_parameter_value(instance, "GrassHighlights_Color")
            unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(instance, "GrassColor_01", COLORS[index])
            unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(instance, "GrassHighlights_Color", HIGHLIGHTS[index])
            after_color = unreal.MaterialEditingLibrary.get_material_instance_vector_parameter_value(instance, "GrassColor_01")
            after_highlight = unreal.MaterialEditingLibrary.get_material_instance_vector_parameter_value(instance, "GrassHighlights_Color")
            require(max(abs(a - b) for a, b in zip(color(after_color), color(COLORS[index]))) <= 0.0001, "grass color postcondition failed")
            require(max(abs(a - b) for a, b in zip(color(after_highlight), color(HIGHLIGHTS[index]))) <= 0.0001, "highlight color postcondition failed")
            record["vectors"] = {
                "GrassColor_01": {"before": color(before_color), "after": color(COLORS[index])},
                "GrassHighlights_Color": {"before": color(before_highlight), "after": color(HIGHLIGHTS[index])},
            }
            unreal.MaterialEditingLibrary.update_material_instance(instance)
            require(unreal.EditorAssetLibrary.save_loaded_asset(instance, only_if_is_dirty=False), "grass material save failed: " + package)
            record["after_sha256"] = sha256(GRASS_MATERIAL_FILES[index])
            require(record["after_sha256"] != record["before_sha256"], "grass material did not serialize: " + package)
            changes.append(record)
        self.report["material_correction"] = {
            "vendor_parent": VENDOR_PARENT,
            "vendor_parent_sha256": VENDOR_PARENT_SHA,
            "project_owned_parent": R32_PARENT,
            "project_owned_parent_sha256": sha256(R32_PARENT_FILE),
            "blend_mode": "BLEND_MASKED",
            "opacity_mask_clip_value": 0.3333,
            "two_sided": True,
            "compile_errors": compile_errors,
            "instances": changes,
        }

    def bind_pie(self):
        world = self.editor.get_game_world()
        if world is None or not self.level.is_in_play_in_editor():
            return False
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        spawners = [actor for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor) if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        if pawn is None or len(spawners) != 1:
            return False
        self.world = world
        self.pawn = pawn
        self.spawner = spawners[0]
        self.set_phase("WAIT_GENERATION")
        return True

    def generation_ready(self):
        status = self.spawner.get_planet_generation_status()
        record = {"phase": str(status.get_editor_property("phase")), "progress": float(status.get_editor_property("progress")), "is_generating": bool(status.get_editor_property("is_generating"))}
        self.report["generation"] = record
        return "COMPLETE" in record["phase"].upper() and record["progress"] >= 0.999 and not record["is_generating"]

    def isolate(self):
        self.controller, camera = camera_record(self.world)
        self.report["capture_camera"] = camera
        foliage_actor = self.spawner.get_foliage_actor()
        require(foliage_actor is not None, "foliage actor missing")
        approved = []
        total_instances = 0
        for component in list(foliage_actor.get_components_by_class(unreal.StaticMeshComponent)):
            if component.get_class().get_name() != "PPGGPUFoliageComponent":
                continue
            mesh = asset_path(component.get_editor_property("static_mesh"))
            if mesh in APPROVED_GRASS:
                approved.append(component)
                diag = unreal.RedPPGFoliageDiagnostics.inspect_component(component).to_dict()
                count = next(int(v) for k, v in diag.items() if str(k).replace("_", "").lower() == "numinstances")
                require(count > 0, "zero-instance approved component")
                total_instances += count
        require(len(approved) == 196, "approved grass component-count drift")

        hidden = 0
        for actor in unreal.GameplayStatics.get_all_actors_of_class(self.world, unreal.Actor):
            for component in list(actor.get_components_by_class(unreal.PrimitiveComponent)):
                visible = bool(component.get_editor_property("visible"))
                hidden_in_game = bool(component.get_editor_property("hidden_in_game"))
                self.visibility_states.append((component, visible, hidden_in_game))
                mesh = asset_path(component.get_editor_property("static_mesh")) if isinstance(component, unreal.StaticMeshComponent) else None
                if component.get_class().get_name() == "PPGGPUFoliageComponent" and mesh in APPROVED_GRASS:
                    component.set_visibility(True, True)
                    component.set_hidden_in_game(False)
                else:
                    component.set_visibility(False, True)
                    component.set_hidden_in_game(True)
                    hidden += 1
        self.report["runtime_grass"] = {"approved_components": len(approved), "total_instances": total_instances, "hidden_non_grass_primitives": hidden}
        unreal.SystemLibrary.execute_console_command(self.world, "DisableAllScreenMessages", self.controller)
        unreal.SystemLibrary.execute_console_command(self.world, "viewmode unlit", self.controller)
        self.set_phase("SETTLE_UNLIT")

    def restore_scene(self):
        restored = 0
        for component, visible, hidden_in_game in self.visibility_states:
            if component is None:
                continue
            component.set_visibility(visible, True)
            component.set_hidden_in_game(hidden_in_game)
            restored += 1
        self.report["runtime_grass"]["restored_primitive_components"] = restored
        unreal.SystemLibrary.execute_console_command(self.world, "viewmode lit", self.controller)
        self.set_phase("SETTLE_NORMAL")

    def request_capture(self, path):
        task = unreal.AutomationLibrary.take_high_res_screenshot(1280, 720, str(path))
        require(task is not None, "screenshot request failed: " + str(path))

    def finish_capture(self):
        require(UNLIT.is_file() and UNLIT.stat().st_size > 0, "unlit screenshot missing")
        require(NORMAL.is_file() and NORMAL.stat().st_size > 0, "normal screenshot missing")
        self.report["captures"] = {
            "grass_only_unlit": {"path": str(UNLIT), "bytes": UNLIT.stat().st_size, "sha256": sha256(UNLIT)},
            "player_scale_normal_lit": {"path": str(NORMAL), "bytes": NORMAL.stat().st_size, "sha256": sha256(NORMAL)},
        }
        self.level.editor_request_end_play()
        self.set_phase("WAIT_STOP")

    def finish(self):
        require(not self.level.is_in_play_in_editor(), "PIE did not stop")
        require(dirty_packages() == {"content": [], "maps": []}, "PIE left dirty packages")
        for path, expected in ((HOME_FILE, HOME_SHA), (PROFILE_FILE, PROFILE_SHA), (FOLIAGE_FILE, FOLIAGE_SHA), (VENDOR_PARENT_FILE, VENDOR_PARENT_SHA)):
            require(sha256(path) == expected, "post-PIE drift: " + str(path))
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "protected post-PIE drift: " + str(path))
        self.report.update({
            "status": "PASS_R32_GRASS_MATERIAL_SAVED_AND_D3D12_CAPTURED_PENDING_PIXEL_REVIEW",
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "home_sha256_before_after": HOME_SHA,
            "profile_sha256_before_after": PROFILE_SHA,
            "foliage_sha256_before_after": FOLIAGE_SHA,
            "vendor_parent_sha256_before_after": VENDOR_PARENT_SHA,
            "completed_utc": now(),
            "claim_limit": "Project-owned material serialization and real-D3D12 captures only; pixel acceptance remains independent and gameplay/package/multiplayer are not claimed.",
        })
        atomic_json(RESULT, self.report)
        unreal.log("REDMMO_R32_PASS")
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
                require(elapsed <= 30.0, "settle timeout")
                if elapsed >= 8.0:
                    self.isolate()
            elif self.phase == "SETTLE_UNLIT":
                require(elapsed <= 15.0, "unlit settle timeout")
                if elapsed >= 2.0:
                    self.request_capture(UNLIT)
                    self.set_phase("WAIT_UNLIT")
            elif self.phase == "WAIT_UNLIT":
                require(elapsed <= 25.0, "unlit screenshot timeout")
                if UNLIT.is_file() and UNLIT.stat().st_size > 0:
                    self.restore_scene()
            elif self.phase == "SETTLE_NORMAL":
                require(elapsed <= 15.0, "normal settle timeout")
                if elapsed >= 3.0:
                    self.request_capture(NORMAL)
                    self.set_phase("WAIT_NORMAL")
            elif self.phase == "WAIT_NORMAL":
                require(elapsed <= 25.0, "normal screenshot timeout")
                if NORMAL.is_file() and NORMAL.stat().st_size > 0:
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
    _R32 = R32()
    _R32.start()
except Exception as bootstrap_error:
    DIAG.mkdir(parents=True, exist_ok=True)
    atomic_json(RESULT, {"schema": "redmmo.grass_material.apply_verify.r32.v1", "status": "FAIL", "error": str(bootstrap_error), "traceback": traceback.format_exc(), "completed_utc": now()})
    unreal.SystemLibrary.quit_editor()
