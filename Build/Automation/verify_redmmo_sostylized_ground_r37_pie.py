"""Fresh reload, MapCheck, PIE grass-count and D3D12 capture verifier for R37."""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject")
HOME_MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
HOME_FILE = PROJECT.parent / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
HOME_SHA = "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3"
PROFILE_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
PROFILE_SHA = "D226215C7367808F4A2E3225A0C9CBD7F4F32E803ABEFD22CA39062CD5538970"
FOLIAGE_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_GrassEligible_R29.uasset"
FOLIAGE_SHA = "D1ACEE4F403D2082FF49CB57D52907AAADA0C20D06386576C435557CF49404D8"
SURFACE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/MI_PPG_ProfileV1_Surface"
SURFACE_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\MI_PPG_ProfileV1_Surface.uasset"
PARENT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/M_PPG_ProfileV1_SurfaceParent"
PARENT_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\M_PPG_ProfileV1_SurfaceParent.uasset"
PARENT_SHA = "5B433BA09CCBB50EFC71A9F2C9100BF264274249A1B4AC2BE5E95126F4644768"
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
BC = "/Game/SoStylized/Environment/Landscape/Textures/T_Grass1_BC"
ROUGHNESS = "/Game/SoStylized/Environment/Landscape/Textures/T_Grass1_R"
FLAT_NORMAL = "/Engine/EngineMaterials/DefaultNormal"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_SoStylizedGround_R37_20260805T1430Z")
APPLY_RESULT = DIAG / "apply_result.json"
RESULT = DIAG / "verify_result.json"
SCREENSHOT = DIAG / "player_scale_normal_lit_r37.png"


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
    data = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


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


def command_log():
    text = str(unreal.SystemLibrary.get_command_line())
    match = re.search(r'(?i)-abslog=(?:"([^"]+)"|(\S+))', text)
    return (match.group(1) or match.group(2)) if match else str(PROJECT.parent / "Saved/Logs/RedMMO.log")


def map_check(world):
    path = command_log()
    require(os.path.isfile(path), "verifier log missing")
    offset = os.path.getsize(path)
    unreal.SystemLibrary.execute_console_command(world, "MAP CHECKDEP NOCLEARLOG")
    pattern = re.compile(r"MapCheck: Map check complete: (\d+) Error\(s\), (\d+) Warning\(s\)")
    for _ in range(120):
        time.sleep(0.1)
        with open(path, "rb") as stream:
            stream.seek(min(offset, os.path.getsize(path)))
            matches = pattern.findall(stream.read().decode("utf-8", errors="replace"))
        if matches:
            errors, warnings = (int(value) for value in matches[-1])
            require(errors == 0 and warnings == 0, "MapCheck failed: {}/{}".format(errors, warnings))
            return {"errors": errors, "warnings": warnings, "log": path}
    raise RuntimeError("no fresh MapCheck marker")


def vec(value):
    return [float(value.x), float(value.y), float(value.z)]


class VerifyR37:
    def __init__(self):
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.handle = None
        self.phase = "PREPARE"
        self.started = time.monotonic()
        self.world = None
        self.spawner = None
        self.controller = None
        self.report = {
            "schema": "redmmo.sostylized_ground.verify_pie.r37.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "evidence_class": "fresh_reload_mapcheck_plus_real_gpu_visual_pending_pixel_review",
        }

    def set_phase(self, phase):
        self.phase = phase
        self.started = time.monotonic()
        self.report["phase"] = phase
        unreal.log("REDMMO_R37_VERIFY_PHASE " + phase)

    def authenticate(self):
        active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(active == PROJECT.resolve(strict=True), "wrong project")
        require(not RESULT.exists() and not SCREENSHOT.exists(), "R37 verify no-clobber failed")
        apply = json.loads(APPLY_RESULT.read_text(encoding="utf-8"))
        require(apply.get("status") == "PASS_R37_SERIALIZED_PENDING_FRESH_RELOAD_MAPCHECK_AND_D3D12_VISUAL", "apply evidence failed")
        self.surface_sha = apply["surface_sha256_after"]
        for path, expected in ((HOME_FILE, HOME_SHA), (PROFILE_FILE, PROFILE_SHA), (FOLIAGE_FILE, FOLIAGE_SHA), (SURFACE_FILE, self.surface_sha), (PARENT_FILE, PARENT_SHA)):
            require(path.is_file() and sha256(path) == expected, "input drift: " + str(path))
        for path, expected in {**GRASS_FILES, **PROTECTED}.items():
            require(path.is_file() and sha256(path) == expected, "protected/grass drift: " + str(path))
        require(dirty_packages() == {"content": [], "maps": []}, "editor started dirty")
        command = str(unreal.SystemLibrary.get_command_line()).lower()
        require("-d3d12" in command and "-renderoffscreen" in command and "-nullrhi" not in command, "renderer gate failed")
        self.report["provider_gate_before"] = provider_gate()
        world = unreal.EditorLoadingAndSavingUtils.load_map(HOME_MAP)
        require(world is not None and dirty_packages() == {"content": [], "maps": []}, "fresh map load failed or dirtied packages")
        self.report["map_check"] = map_check(world)
        self.verify_surface()
        self.level.editor_request_begin_play()
        self.set_phase("WAIT_PIE")

    def verify_surface(self):
        instance = unreal.load_asset(SURFACE)
        require(instance is not None and asset_path(instance.get_editor_property("parent")) == PARENT, "surface/parent drift")
        editing = unreal.MaterialEditingLibrary
        expected_textures = {
            "R10L_StylizedGrass_BC": BC,
            "R10L_StylizedGrass_N": FLAT_NORMAL,
            "R10L_StylizedGrass_ORM": ROUGHNESS,
        }
        actual_textures = {}
        for name, expected in expected_textures.items():
            actual_textures[name] = asset_path(editing.get_material_instance_texture_parameter_value(instance, name))
            require(actual_textures[name] == expected, "texture binding drift: " + name)
        actual_scalars = {
            name: float(editing.get_material_instance_scalar_parameter_value(instance, name))
            for name in ("R10L_NormalAmount", "R10L_GroundSpecular", "R10L_GroundUVScale")
        }
        require(abs(actual_scalars["R10L_NormalAmount"] - 0.0) <= 0.0001, "normal amount drift")
        require(abs(actual_scalars["R10L_GroundSpecular"] - 0.02) <= 0.0001, "specular drift")
        require(abs(actual_scalars["R10L_GroundUVScale"] - 12.0) <= 0.0001, "UV scale drift")
        actual_vectors = {}
        for name in ("R10L_GroundTintA", "R10L_GroundTintB"):
            value = editing.get_material_instance_vector_parameter_value(instance, name)
            actual_vectors[name] = [float(value.r), float(value.g), float(value.b), float(value.a)]
            require(max(abs(item - 1.0) for item in actual_vectors[name]) <= 0.0001, "neutral tint drift: " + name)
        self.report["surface"] = {"textures": actual_textures, "scalars": actual_scalars, "vectors": actual_vectors, "sha256": self.surface_sha}

    def bind_pie(self):
        world = self.editor.get_game_world()
        if world is None or not self.level.is_in_play_in_editor():
            return False
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        spawners = [actor for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor) if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        if pawn is None or len(spawners) != 1:
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
        foliage_actor = self.spawner.get_foliage_actor()
        require(foliage_actor is not None, "foliage actor missing")
        components = 0
        instances = 0
        for component in list(foliage_actor.get_components_by_class(unreal.StaticMeshComponent)):
            if component.get_class().get_name() != "PPGGPUFoliageComponent":
                continue
            if asset_path(component.get_editor_property("static_mesh")) not in GRASS_MESHES:
                continue
            diag = unreal.RedPPGFoliageDiagnostics.inspect_component(component).to_dict()
            count = next(int(value) for key, value in diag.items() if str(key).replace("_", "").lower() == "numinstances")
            require(count > 0, "approved grass component has zero instances")
            components += 1
            instances += count
        require(components == 196, "approved grass component-count drift")
        require(instances == 2218356, "approved grass instance-count drift")
        self.report["runtime_grass"] = {"approved_components": components, "instances": instances}
        self.controller = unreal.GameplayStatics.get_player_controller(self.world, 0)
        require(self.controller is not None, "player controller missing")
        manager = self.controller.get_editor_property("player_camera_manager")
        require(manager is not None, "camera manager missing")
        rotation = manager.get_camera_rotation()
        self.report["capture_camera"] = {
            "location": vec(manager.get_camera_location()),
            "rotation": [float(rotation.pitch), float(rotation.yaw), float(rotation.roll)],
            "fov": float(manager.get_fov_angle()),
        }
        unreal.SystemLibrary.execute_console_command(self.world, "DisableAllScreenMessages", self.controller)
        unreal.SystemLibrary.execute_console_command(self.world, "viewmode lit", self.controller)
        self.set_phase("SETTLE_CAPTURE")

    def request_capture(self):
        task = unreal.AutomationLibrary.take_high_res_screenshot(1280, 720, str(SCREENSHOT))
        require(task is not None, "screenshot request failed")
        self.set_phase("WAIT_CAPTURE")

    def stop_pie(self):
        require(SCREENSHOT.is_file() and SCREENSHOT.stat().st_size > 0, "screenshot missing")
        self.report["capture"] = {"path": str(SCREENSHOT), "bytes": SCREENSHOT.stat().st_size, "sha256": sha256(SCREENSHOT)}
        self.level.editor_request_end_play()
        self.set_phase("WAIT_STOP")

    def finish(self):
        require(not self.level.is_in_play_in_editor(), "PIE did not stop")
        require(dirty_packages() == {"content": [], "maps": []}, "PIE left dirty packages")
        for path, expected in ((HOME_FILE, HOME_SHA), (PROFILE_FILE, PROFILE_SHA), (FOLIAGE_FILE, FOLIAGE_SHA), (SURFACE_FILE, self.surface_sha), (PARENT_FILE, PARENT_SHA)):
            require(sha256(path) == expected, "post-PIE drift: " + str(path))
        for path, expected in {**GRASS_FILES, **PROTECTED}.items():
            require(sha256(path) == expected, "protected/grass post-drift: " + str(path))
        self.report.update({
            "status": "PASS_R37_FRESH_RELOAD_MAPCHECK_AND_D3D12_CAPTURE_PENDING_PIXEL_REVIEW",
            "completed_utc": now(),
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "claim_limit": "Fresh reload, MapCheck, exact surface binding, runtime grass counts, and one real-D3D12 frame only; pixel acceptance, gameplay, package, replication, and multiplayer are not claimed.",
        })
        atomic_json(RESULT, self.report)
        unreal.log("REDMMO_R37_VERIFY_PASS")
        self.phase = "DONE"
        self.schedule_quit(3.0)

    def fail(self, error):
        failed_phase = self.phase
        self.phase = "FAILED"
        self.report.update({"status": "FAIL", "failed_phase": failed_phase, "completed_utc": now(), "error": str(error), "traceback": traceback.format_exc()})
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        if not RESULT.exists():
            atomic_json(RESULT, self.report)
        unreal.log_error("REDMMO_R37_VERIFY_FAIL " + str(error))
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
                    self.set_phase("SETTLE")
            elif self.phase == "SETTLE":
                require(elapsed <= 35.0, "generation settle timeout")
                if elapsed >= 15.0:
                    self.prepare_capture()
            elif self.phase == "SETTLE_CAPTURE":
                require(elapsed <= 15.0, "capture settle timeout")
                if elapsed >= 3.0:
                    self.request_capture()
            elif self.phase == "WAIT_CAPTURE":
                require(elapsed <= 25.0, "screenshot timeout")
                if SCREENSHOT.is_file() and SCREENSHOT.stat().st_size > 0:
                    self.stop_pie()
            elif self.phase == "WAIT_STOP":
                require(elapsed <= 15.0, "PIE stop timeout")
                if not self.level.is_in_play_in_editor():
                    self.finish()
        except Exception as error:
            self.fail(error)

    def start(self):
        self.handle = unreal.register_slate_post_tick_callback(self.tick)


try:
    _R37 = VerifyR37()
    _R37.start()
except Exception as bootstrap_error:
    atomic_json(RESULT, {"schema": "redmmo.sostylized_ground.verify_pie.r37.v1", "status": "FAIL", "completed_utc": now(), "error": str(bootstrap_error), "traceback": traceback.format_exc()})
    unreal.SystemLibrary.quit_editor()
