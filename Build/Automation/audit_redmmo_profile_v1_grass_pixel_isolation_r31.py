"""No-save R31 grass-only unlit/wireframe pixel-isolation diagnostic."""

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
R30_RESULT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1GrassDispatch_R30B_20260805T1300Z\result.json")
R30_RESULT_SHA = "E6FA2EA76FC56C5FEC7AED63D222BF5DCD26E1DD7E03FF7C80CF6A4CCD04252B"
APPROVED_GRASS = {
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_A_R10N",
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_B_R10N",
}
PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1GrassPixelIsolation_R31C_20260805T1320Z")
RESULT = DIAG / "result.json"
UNLIT = DIAG / "grass_only_unlit.png"
WIREFRAME = DIAG / "grass_only_wireframe.png"


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


def distance(a, b):
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


def normalized_key(value):
    return str(value).replace("_", "").replace(" ", "").lower()


def struct_field(value, wanted):
    fields = value.to_dict()
    target = normalized_key(wanted)
    matches = [item for key, item in fields.items() if normalized_key(key) in (target, "b" + target)]
    require(len(matches) == 1, "expected one reflected field {} in {}".format(wanted, list(fields)))
    return matches[0]


def camera_record(world):
    controller = unreal.GameplayStatics.get_player_controller(world, 0)
    require(controller is not None, "player controller missing")
    manager = controller.get_editor_property("player_camera_manager")
    require(manager is not None, "player camera manager missing")
    rotation = manager.get_camera_rotation()
    return controller, {
        "location": vec(manager.get_camera_location()),
        "rotation": [float(rotation.pitch), float(rotation.yaw), float(rotation.roll)],
        "fov": float(manager.get_fov_angle()),
    }


class R31:
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
        self.report = {
            "schema": "redmmo.ppg_profile_v1.grass_pixel_isolation.r31.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "evidence_class": "automation_plus_real_gpu_visual_pending_independent_review",
        }

    def set_phase(self, phase):
        self.phase = phase
        self.started = time.monotonic()
        self.report["phase"] = phase
        unreal.log("REDMMO_R31_PHASE " + phase)

    def authenticate(self):
        active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(active == PROJECT.resolve(strict=True), "wrong project")
        require(not RESULT.exists() and not UNLIT.exists() and not WIREFRAME.exists(), "R31 no-clobber failed")
        DIAG.mkdir(parents=True, exist_ok=True)
        for path, expected in (
            (PROJECT, PROJECT_SHA), (HOME_FILE, HOME_SHA), (PROFILE_FILE, PROFILE_SHA),
            (FOLIAGE_FILE, FOLIAGE_SHA), (R30_RESULT, R30_RESULT_SHA),
        ):
            require(path.is_file() and sha256(path) == expected, "input drift: " + str(path))
        for path, expected in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected, "protected drift: " + str(path))
        require(dirty_packages() == {"content": [], "maps": []}, "editor started dirty")
        require(not self.level.is_in_play_in_editor(), "PIE already active")
        command = str(unreal.SystemLibrary.get_command_line()).lower()
        require("-d3d12" in command and "-renderoffscreen" in command and "-nullrhi" not in command, "renderer gate failed")
        self.report["provider_gate_before"] = provider_gate()
        world = unreal.EditorLevelLibrary.get_editor_world()
        require(world is not None, "editor world missing")
        require(world.get_path_name().split(":", 1)[0].split(".", 1)[0] == HOME_MAP, "wrong map")
        self.level.editor_request_begin_play()
        self.set_phase("WAIT_PIE")

    def bind_pie(self):
        world = self.editor.get_game_world()
        if world is None or not self.level.is_in_play_in_editor():
            return False
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        spawners = [
            actor for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor)
            if actor.get_class().get_name() == "PlanetSpawnerBP_C"
        ]
        if pawn is None or len(spawners) != 1:
            return False
        self.world = world
        self.pawn = pawn
        self.spawner = spawners[0]
        self.controller, self.report["camera_before_isolation"] = camera_record(world)
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

    def isolate(self):
        foliage_actor = self.spawner.get_foliage_actor()
        require(foliage_actor is not None, "foliage actor missing")
        pawn_location = self.pawn.get_actor_location()
        approved_components = []
        positive_components = []
        for component in list(foliage_actor.get_components_by_class(unreal.StaticMeshComponent)):
            if component.get_class().get_name() != "PPGGPUFoliageComponent":
                continue
            mesh = asset_path(component.get_editor_property("static_mesh"))
            if mesh not in APPROVED_GRASS:
                continue
            approved_components.append(component)
            diag = unreal.RedPPGFoliageDiagnostics.inspect_component(component)
            count = int(struct_field(diag, "num_instances"))
            if count > 0:
                positive_components.append((component, count, distance(component.get_world_location(), pawn_location)))
        require(len(approved_components) == 196, "approved component-count drift")
        require(len(positive_components) == 196, "positive component-count drift")

        hidden_components = 0
        kept_components = 0
        for actor in unreal.GameplayStatics.get_all_actors_of_class(self.world, unreal.Actor):
            for component in list(actor.get_components_by_class(unreal.PrimitiveComponent)):
                mesh = None
                if isinstance(component, unreal.StaticMeshComponent):
                    mesh = asset_path(component.get_editor_property("static_mesh"))
                if component.get_class().get_name() == "PPGGPUFoliageComponent" and mesh in APPROVED_GRASS:
                    component.set_visibility(True, True)
                    component.set_hidden_in_game(False)
                    kept_components += 1
                else:
                    component.set_visibility(False, True)
                    component.set_hidden_in_game(True)
                    hidden_components += 1

        self.controller, camera_after = camera_record(self.world)
        self.report["isolation"] = {
            "approved_components": len(approved_components),
            "positive_components": len(positive_components),
            "total_instances": sum(item[1] for item in positive_components),
            "nearest_component_origin_cm": min(item[2] for item in positive_components),
            "kept_primitive_components": kept_components,
            "hidden_non_grass_primitive_components": hidden_components,
            "camera_after_isolation": camera_after,
            "camera_transform_preserved": camera_after == self.report["camera_before_isolation"],
            "transient_only": True,
        }
        unreal.SystemLibrary.execute_console_command(self.world, "DisableAllScreenMessages", self.controller)
        unreal.SystemLibrary.execute_console_command(self.world, "viewmode unlit", self.controller)
        self.set_phase("SETTLE_UNLIT")

    def request_capture(self, path):
        task = unreal.AutomationLibrary.take_high_res_screenshot(1280, 720, str(path))
        require(task is not None, "screenshot request failed: " + str(path))

    def finish_capture(self):
        require(UNLIT.is_file() and UNLIT.stat().st_size > 0, "unlit screenshot missing")
        require(WIREFRAME.is_file() and WIREFRAME.stat().st_size > 0, "wireframe screenshot missing")
        self.report["captures"] = {
            "unlit": {"path": str(UNLIT), "bytes": UNLIT.stat().st_size, "sha256": sha256(UNLIT)},
            "wireframe": {"path": str(WIREFRAME), "bytes": WIREFRAME.stat().st_size, "sha256": sha256(WIREFRAME)},
        }
        self.level.editor_request_end_play()
        self.set_phase("WAIT_STOP")

    def finish(self):
        require(not self.level.is_in_play_in_editor(), "PIE did not stop")
        require(dirty_packages() == {"content": [], "maps": []}, "PIE dirtied packages")
        for path, expected in ((HOME_FILE, HOME_SHA), (PROFILE_FILE, PROFILE_SHA), (FOLIAGE_FILE, FOLIAGE_SHA)):
            require(sha256(path) == expected, "post-PIE drift: " + str(path))
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "protected post-PIE drift: " + str(path))
        self.report.update({
            "status": "PASS_R31_NO_SAVE_GRASS_ONLY_UNLIT_WIREFRAME_CAPTURE",
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "home_sha256_before_after": HOME_SHA,
            "profile_sha256_before_after": PROFILE_SHA,
            "foliage_sha256_before_after": FOLIAGE_SHA,
            "save_called": False,
            "completed_utc": now(),
            "claim_limit": "Transient grass-only real-D3D12 captures plus runtime identity/count checks; pixel interpretation remains independent and no gameplay/package/multiplayer acceptance is claimed.",
        })
        atomic_json(RESULT, self.report)
        unreal.log("REDMMO_R31_PASS")
        self.schedule_quit(3.0)

    def fail(self, error):
        self.report.update({
            "status": "FAIL",
            "error": str(error),
            "traceback": traceback.format_exc(),
            "failed_phase": self.phase,
            "completed_utc": now(),
        })
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
                    unreal.SystemLibrary.execute_console_command(self.world, "viewmode wireframe", self.controller)
                    self.set_phase("SETTLE_WIREFRAME")
            elif self.phase == "SETTLE_WIREFRAME":
                require(elapsed <= 15.0, "wireframe settle timeout")
                if elapsed >= 2.0:
                    self.request_capture(WIREFRAME)
                    self.set_phase("WAIT_WIREFRAME")
            elif self.phase == "WAIT_WIREFRAME":
                require(elapsed <= 25.0, "wireframe screenshot timeout")
                if WIREFRAME.is_file() and WIREFRAME.stat().st_size > 0:
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
    _R31 = R31()
    _R31.start()
except Exception as bootstrap_error:
    DIAG.mkdir(parents=True, exist_ok=True)
    atomic_json(RESULT, {
        "schema": "redmmo.ppg_profile_v1.grass_pixel_isolation.r31.v1",
        "status": "FAIL",
        "error": str(bootstrap_error),
        "traceback": traceback.format_exc(),
        "completed_utc": now(),
    })
    unreal.SystemLibrary.quit_editor()
