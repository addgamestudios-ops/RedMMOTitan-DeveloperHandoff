"""R41B fresh-reload proof: capture untouched Lit before any view-mode command."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject")
HOME_MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
HOME_FILE = PROJECT.parent / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
HEADER_FILE = PROJECT.parent / r"Source\RedMMO\Public\RedPPGGameplayGameMode.h"
SOURCE_FILE = PROJECT.parent / r"Source\RedMMO\Private\RedPPGGameplayGameMode.cpp"
BINARY_FILE = PROJECT.parent / r"Binaries\Win64\UnrealEditor-RedMMO.dll"
CHECKS = {
    PROJECT: "3BF3D8D1D1C7F892A2CD4873F7C0390EC1AF3CA8F77E60549169563D18DBF86F",
    HOME_FILE: "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3",
    HEADER_FILE: "904B46C063F74A01D7540E80844C2FA19D2A6CD5C1EF246D50B68201D06A5912",
    SOURCE_FILE: "706792C1DCA23B29A5B7B0D53C279494C888D69FD9373B6363579B9BB6203C1F",
    BINARY_FILE: "B6664A1E64D4213A74CD2EAC1B65462F14D27E99CC5B40B47270FDA417D23DC1",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"): "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"): "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}
GRASS_MESHES = {
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_A_R10N",
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_B_R10N",
}
EXPECTED_CAMERA = {
    "location": [191297894.99445367, 196950314.12190434, -421017759.8003976],
    "rotation": [20.41166676895961, -46.37008029227465, 111.80009049544566],
    "fov": 90.0,
}
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_GrassRenderRefresh_R41B_20260805T1530Z")
RESULT = DIAG / "result.json"
LIT = DIAG / "untouched_lit_first_after_refresh_r41b.png"


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
    result = {}
    for port in (11111, 5353, 8000, 8765):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.15)
        try:
            result[str(port)] = sock.connect_ex(("127.0.0.1", port)) != 0
        finally:
            sock.close()
    require(all(result.values()), "provider listener active: " + repr(result))
    return result


def normalized(value):
    return str(value).replace("_", "").replace(" ", "").lower()


def field(value, wanted):
    fields = value.to_dict()
    target = normalized(wanted)
    matches = [item for key, item in fields.items() if normalized(key) in (target, "b" + target)]
    require(len(matches) == 1, "missing reflected field " + wanted)
    return matches[0]


def inspect_grass(spawner):
    foliage = spawner.get_foliage_actor()
    require(foliage is not None, "foliage actor missing")
    components = [
        component for component in list(foliage.get_components_by_class(unreal.StaticMeshComponent))
        if component.get_class().get_name() == "PPGGPUFoliageComponent"
        and asset_path(component.get_editor_property("static_mesh")) in GRASS_MESHES
    ]
    records = []
    for component in components:
        diag = unreal.RedPPGFoliageDiagnostics.inspect_component(component)
        records.append({
            "instances": int(field(diag, "num_instances")),
            "visible": bool(component.get_editor_property("visible")),
            "hidden_in_game": bool(component.get_editor_property("hidden_in_game")),
            "registered": bool(field(diag, "registered")),
            "instance_data_ready": bool(field(diag, "instance_data_ready")),
            "scene_proxy": bool(field(diag, "has_scene_proxy")),
            "last_render": float(field(diag, "last_render_time_on_screen")),
        })
    summary = {
        "components": len(records),
        "instances": sum(item["instances"] for item in records),
        "visible_true": sum(item["visible"] for item in records),
        "hidden_in_game_true": sum(item["hidden_in_game"] for item in records),
        "registered": sum(item["registered"] for item in records),
        "instance_data_ready": sum(item["instance_data_ready"] for item in records),
        "scene_proxy": sum(item["scene_proxy"] for item in records),
        "positive_last_render": sum(item["last_render"] > 0.0 for item in records),
    }
    require(summary["components"] == 196 and summary["instances"] == 2218356, "grass census drift")
    require(summary["visible_true"] == 196 and summary["hidden_in_game_true"] == 0, "visibility drift")
    require(summary["registered"] == 196 and summary["instance_data_ready"] == 196 and summary["scene_proxy"] == 196, "runtime readiness drift")
    return summary


class R41B:
    def __init__(self):
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.handle = None
        self.phase = "PREPARE"
        self.started = time.monotonic()
        self.world = None
        self.spawner = None
        self.report = {
            "schema": "redmmo.grass_render_refresh.verify.r41b.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "evidence_class": "fresh_reload_pie_real_gpu_lit_first",
            "visibility_cycle_called": False,
            "view_mode_command_called_before_capture": False,
            "component_property_mutation_called": False,
            "save_called": False,
        }

    def set_phase(self, phase):
        self.phase = phase
        self.started = time.monotonic()
        self.report["phase"] = phase
        unreal.log("REDMMO_R41B_PHASE " + phase)

    def authenticate(self):
        active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(active == PROJECT.resolve(strict=True), "wrong project")
        require(not RESULT.exists() and not LIT.exists(), "R41B no-clobber failed")
        for path, expected in CHECKS.items():
            require(path.is_file() and sha256(path) == expected, "input drift: " + str(path))
        require(dirty_packages() == {"content": [], "maps": []}, "editor started dirty")
        require(not self.level.is_in_play_in_editor(), "PIE already active")
        command = str(unreal.SystemLibrary.get_command_line()).lower()
        require("-d3d12" in command and "-renderoffscreen" in command and "-nullrhi" not in command, "renderer gate failed")
        self.report["provider_gate_before"] = provider_gate()
        editor_world = unreal.EditorLevelLibrary.get_editor_world()
        require(editor_world is not None and editor_world.get_path_name().split(":", 1)[0].split(".", 1)[0] == HOME_MAP, "wrong map")
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

    def capture_lit_first(self):
        controller = unreal.GameplayStatics.get_player_controller(self.world, 0)
        manager = controller.get_editor_property("player_camera_manager")
        rotation = manager.get_camera_rotation()
        camera = {
            "location": [float(v) for v in (manager.get_camera_location().x, manager.get_camera_location().y, manager.get_camera_location().z)],
            "rotation": [float(rotation.pitch), float(rotation.yaw), float(rotation.roll)],
            "fov": float(manager.get_fov_angle()),
        }
        delta = {
            "location_cm_max_abs": max(abs(a - b) for a, b in zip(camera["location"], EXPECTED_CAMERA["location"])),
            "rotation_deg_max_abs": max(abs(a - b) for a, b in zip(camera["rotation"], EXPECTED_CAMERA["rotation"])),
            "fov_max_abs": abs(camera["fov"] - EXPECTED_CAMERA["fov"]),
        }
        require(delta["location_cm_max_abs"] <= 0.1 and delta["rotation_deg_max_abs"] <= 0.001 and delta["fov_max_abs"] <= 0.001, "camera drift: " + repr(delta))
        self.report["camera"] = camera
        self.report["camera_delta"] = delta
        self.report["state_before_first_capture"] = inspect_grass(self.spawner)
        task = unreal.AutomationLibrary.take_high_res_screenshot(1280, 720, str(LIT))
        require(task is not None, "lit-first screenshot request failed")
        self.set_phase("WAIT_LIT")

    def stop_pie(self):
        self.report["state_after_first_capture"] = inspect_grass(self.spawner)
        self.report["capture"] = {"path": str(LIT), "bytes": LIT.stat().st_size, "sha256": sha256(LIT)}
        self.level.editor_request_end_play()
        self.set_phase("WAIT_STOP")

    def finish(self):
        require(not self.level.is_in_play_in_editor(), "PIE did not stop")
        require(dirty_packages() == {"content": [], "maps": []}, "PIE dirtied packages")
        for path, expected in CHECKS.items():
            require(sha256(path) == expected, "post-PIE drift: " + str(path))
        self.report.update({
            "status": "PASS_R41B_UNTOUCHED_LIT_FIRST_CAPTURE_PENDING_VISUAL_REVIEW",
            "completed_utc": now(),
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "save_called": False,
            "visibility_cycle_called": False,
            "view_mode_command_called_before_capture": False,
            "component_property_mutation_called": False,
            "claim_limit": "Fresh-reload untouched Lit-first D3D12 PIE visual only; no map/content save, package, replication, multiplayer or user-acceptance claim.",
        })
        atomic_json(RESULT, self.report)
        unreal.log("REDMMO_R41B_PASS")
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
        unreal.log_error("REDMMO_R41B_FAIL " + str(error))
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
                    self.set_phase("SETTLE_REFRESH")
            elif self.phase == "SETTLE_REFRESH":
                require(elapsed <= 30.0, "refresh settle timeout")
                if elapsed >= 12.0:
                    self.capture_lit_first()
            elif self.phase == "WAIT_LIT":
                require(elapsed <= 25.0, "lit-first capture timeout")
                if LIT.is_file() and LIT.stat().st_size > 0:
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
    _R41B = R41B()
    _R41B.start()
except Exception as bootstrap_error:
    atomic_json(RESULT, {"schema": "redmmo.grass_render_refresh.verify.r41b.v1", "status": "FAIL", "completed_utc": now(), "error": str(bootstrap_error), "traceback": traceback.format_exc()})
    unreal.SystemLibrary.quit_editor()
