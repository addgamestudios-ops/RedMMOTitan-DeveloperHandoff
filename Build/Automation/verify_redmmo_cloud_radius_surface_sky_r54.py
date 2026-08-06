"""R54 no-save cloud-radius discriminator at the saved full-night PPG view.

Uses the R52 existing-viewport screenshot bridge. The only PIE-world property
write is VolumetricCloudComponent.PlanetRadius, changed from its authenticated
6360 km preimage to the 3000 km PPG body radius and restored before PIE ends.
"""

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
HOME_MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
HOME_FILE = PROJECT.parent / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
DIAGNOSTICS_HEADER = PROJECT.parent / r"Source\RedMMO\Public\RedPPGFoliageDiagnostics.h"
DIAGNOSTICS_SOURCE = PROJECT.parent / r"Source\RedMMO\Private\RedPPGFoliageDiagnostics.cpp"
BINARY_FILE = PROJECT.parent / r"Binaries\Win64\UnrealEditor-RedMMO.dll"
PROFILE_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
R29_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_GrassEligible_R29.uasset"
R32_FILE = PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R32\Materials\M_GrassChunks_PPGReadable_R32.uasset"
INSTANCE_A_FILE = PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_A_R10N.uasset"
INSTANCE_B_FILE = PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_B_R10N.uasset"
PROTECTED_TEST = Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap")
PROTECTED_FUSED = Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap")

CHECKS = {
    PROJECT: "3BF3D8D1D1C7F892A2CD4873F7C0390EC1AF3CA8F77E60549169563D18DBF86F",
    HOME_FILE: "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3",
    DIAGNOSTICS_HEADER: "796EFD4BD6779FEB5D312C5A9B44BE097DEEF5C608F342D95B95651BB513AD94",
    DIAGNOSTICS_SOURCE: "9E95FAB31E7EEBB15551BE445E6481417304E7E43A44EF0C9D6ECE1722ABB18D",
    BINARY_FILE: "22C2AE57A79AA6FC8E5CBFB4865AB6915826C058FE7119E28D63A2F4576A1801",
    PROFILE_FILE: "D226215C7367808F4A2E3225A0C9CBD7F4F32E803ABEFD22CA39062CD5538970",
    R29_FILE: "D1ACEE4F403D2082FF49CB57D52907AAADA0C20D06386576C435557CF49404D8",
    R32_FILE: "2BD2B8DD41C611CF1250F1A39C40D3B4A7C47B5EB71ECD1497732546B80F0210",
    INSTANCE_A_FILE: "91A0E7233A5922A921FB4CF8692B8631DBB7AEFE7D3D106FDB63C44DB412CE47",
    INSTANCE_B_FILE: "19D1B594553977A6A7BA116271F103DCD4044F8F24C3E8B5CF8F596082A9F68E",
    PROTECTED_TEST: "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    PROTECTED_FUSED: "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}
GRASS_MESHES = {
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_A_R10N",
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_B_R10N",
}
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_CloudRadiusSurfaceSky_R54_20260805T1910Z")
RESULT = DIAG / "result.json"
BASELINE = DIAG / "R54_cloud_radius_6360km.png"
CORRECTED = DIAG / "R54_cloud_radius_3000km.png"


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
    temporary = path.with_suffix(".tmp")
    with temporary.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


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


def generation_record(spawner):
    status = spawner.get_planet_generation_status()
    return {
        "phase": str(status.get_editor_property("phase")),
        "progress": float(status.get_editor_property("progress")),
        "is_generating": bool(status.get_editor_property("is_generating")),
    }


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
            "identity": component.get_path_name(),
            "instances": int(field(diag, "num_instances")),
            "registered": bool(field(diag, "registered")),
            "instance_data_ready": bool(field(diag, "instance_data_ready")),
            "scene_proxy": bool(field(diag, "has_scene_proxy")),
        })
    identities = sorted(item["identity"] for item in records)
    return {
        "components": len(records),
        "instances": sum(item["instances"] for item in records),
        "registered": sum(item["registered"] for item in records),
        "instance_data_ready": sum(item["instance_data_ready"] for item in records),
        "scene_proxy": sum(item["scene_proxy"] for item in records),
        "identity_sha256": hashlib.sha256("\n".join(identities).encode("utf-8")).hexdigest().upper(),
    }


def vec(value):
    return [float(value.x), float(value.y), float(value.z)]


def rot(value):
    return [float(value.pitch), float(value.yaw), float(value.roll)]


def distance(a, b):
    return math.sqrt(float((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2))


def rotation_delta(a, b):
    return max(abs(float(a.pitch - b.pitch)), abs(float(a.yaw - b.yaw)), abs(float(a.roll - b.roll)))


class R54:
    def __init__(self):
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.handle = None
        self.phase = "PREPARE"
        self.phase_started = time.monotonic()
        self.world = None
        self.spawner = None
        self.cloud = None
        self.original_radius = None
        self.target_radius = None
        self.baseline_camera = None
        self.baseline_rotation = None
        self.report = {
            "schema": "redmmo.cloud-radius-surface-sky.r54.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "evidence_class": "real_gpu_visual",
            "capture_api": "URedPPGFoliageDiagnostics::RequestViewportScreenshot -> FScreenshotRequest::RequestScreenshot",
            "mutation_scope": "PIE-world VolumetricCloudComponent.PlanetRadius only; restored before stop",
            "persistent_save": False,
        }

    def set_phase(self, value):
        self.phase = value
        self.phase_started = time.monotonic()
        unreal.log("REDMMO_R54_PHASE " + value)

    def authenticate(self):
        active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(active == PROJECT.resolve(strict=True), "wrong project")
        require(not RESULT.exists() and not BASELINE.exists() and not CORRECTED.exists(), "R54 no-clobber failed")
        for path, expected in CHECKS.items():
            require(path.is_file() and sha256(path) == expected, "input drift: " + str(path))
        require(dirty_packages() == {"content": [], "maps": []}, "editor started dirty")
        require(not self.level.is_in_play_in_editor(), "PIE already active")
        command = str(unreal.SystemLibrary.get_command_line()).lower()
        require("-d3d12" in command and "-renderoffscreen" in command and "-nullrhi" not in command, "renderer gate failed")
        require("-resx=1280" in command and "-resy=720" in command and "-forceres" in command, "viewport gate failed")
        self.report["provider_gate_before"] = provider_gate()
        world = unreal.EditorLevelLibrary.get_editor_world()
        require(world is not None and world.get_path_name().split(":", 1)[0].split(".", 1)[0] == HOME_MAP, "wrong map")
        self.level.editor_request_begin_play()
        self.set_phase("WAIT_PIE")

    def bind_pie(self):
        world = self.editor.get_game_world()
        if world is None or not self.level.is_in_play_in_editor():
            return False
        actors = list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor))
        spawners = [a for a in actors if a.get_class().get_name() == "PlanetSpawnerBP_C"]
        clouds = [a for a in actors if isinstance(a, unreal.VolumetricCloud)]
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        if len(spawners) != 1 or len(clouds) != 1 or pawn is None:
            return False
        components = list(clouds[0].get_components_by_class(unreal.VolumetricCloudComponent))
        require(len(components) == 1, "expected one cloud component")
        self.world, self.spawner, self.cloud = world, spawners[0], components[0]
        planet = self.spawner.get_editor_property("planet_data")
        require(planet is not None, "PlanetData missing")
        self.original_radius = float(self.cloud.get_editor_property("planet_radius"))
        self.target_radius = float(planet.get_editor_property("planet_radius")) / 100000.0
        require(abs(self.original_radius - 6360.0) <= 0.01, "cloud-radius preimage drift")
        require(abs(self.target_radius - 3000.0) <= 0.01, "PPG radius drift")
        self.report["radius_km"] = {"before": self.original_radius, "target": self.target_radius}
        self.set_phase("WAIT_GENERATION")
        return True

    def generation_complete(self):
        record = generation_record(self.spawner)
        self.report["generation"] = record
        return "COMPLETE" in record["phase"].upper() and record["progress"] >= 0.999 and not record["is_generating"]

    def camera(self):
        manager = unreal.GameplayStatics.get_player_camera_manager(self.world, 0)
        require(manager is not None, "camera manager missing")
        return manager.get_actor_location(), manager.get_actor_rotation()

    def stable_grass(self, label):
        state = inspect_grass(self.spawner)
        require(state["components"] == 196 and state["instances"] == 2218356, label + " grass census drift")
        require(state["registered"] == 196 and state["instance_data_ready"] == 196 and state["scene_proxy"] == 196,
                label + " grass readiness drift")
        return state

    def request_baseline(self):
        self.baseline_camera, self.baseline_rotation = self.camera()
        self.report["baseline_request"] = {
            "utc": now(), "camera_location_cm": vec(self.baseline_camera),
            "camera_rotation_deg": rot(self.baseline_rotation),
            "cloud_radius_km": float(self.cloud.get_editor_property("planet_radius")),
            "grass": self.stable_grass("baseline"),
        }
        require(unreal.RedPPGFoliageDiagnostics.request_viewport_screenshot(str(BASELINE)), "baseline capture rejected")
        self.set_phase("WAIT_BASELINE")

    def apply_target(self):
        require(BASELINE.is_file() and BASELINE.stat().st_size > 0, "baseline capture missing")
        self.cloud.set_editor_property("planet_radius", self.target_radius)
        require(abs(float(self.cloud.get_editor_property("planet_radius")) - self.target_radius) <= 0.01,
                "cloud target radius did not apply")
        self.report["target_applied_utc"] = now()
        self.set_phase("SETTLE_TARGET")

    def request_corrected(self):
        location, rotation = self.camera()
        require(distance(location, self.baseline_camera) <= 1.0, "camera location drift")
        require(rotation_delta(rotation, self.baseline_rotation) <= 0.1, "camera rotation drift")
        self.report["corrected_request"] = {
            "utc": now(), "camera_location_cm": vec(location),
            "camera_rotation_deg": rot(rotation),
            "camera_location_delta_cm": distance(location, self.baseline_camera),
            "camera_rotation_max_delta_deg": rotation_delta(rotation, self.baseline_rotation),
            "cloud_radius_km": float(self.cloud.get_editor_property("planet_radius")),
            "grass": self.stable_grass("corrected"),
        }
        require(unreal.RedPPGFoliageDiagnostics.request_viewport_screenshot(str(CORRECTED)), "corrected capture rejected")
        self.set_phase("WAIT_CORRECTED")

    def restore(self):
        require(CORRECTED.is_file() and CORRECTED.stat().st_size > 0, "corrected capture missing")
        self.cloud.set_editor_property("planet_radius", self.original_radius)
        require(abs(float(self.cloud.get_editor_property("planet_radius")) - self.original_radius) <= 0.01,
                "cloud radius restoration failed")
        self.report["restored_utc"] = now()
        self.set_phase("SETTLE_RESTORE")

    def request_stop(self):
        location, rotation = self.camera()
        require(distance(location, self.baseline_camera) <= 1.0, "post-restore camera location drift")
        require(rotation_delta(rotation, self.baseline_rotation) <= 0.1, "post-restore camera rotation drift")
        self.report["restored_state"] = {
            "cloud_radius_km": float(self.cloud.get_editor_property("planet_radius")),
            "camera_location_delta_cm": distance(location, self.baseline_camera),
            "camera_rotation_max_delta_deg": rotation_delta(rotation, self.baseline_rotation),
            "grass": self.stable_grass("restored"),
        }
        self.level.editor_request_end_play()
        self.set_phase("WAIT_STOP")

    def finish(self):
        require(not self.level.is_in_play_in_editor(), "PIE did not stop")
        require(dirty_packages() == {"content": [], "maps": []}, "PIE dirtied packages")
        for path, expected in CHECKS.items():
            require(sha256(path) == expected, "post-PIE drift: " + str(path))
        for path in (BASELINE, CORRECTED):
            require(path.is_file() and path.stat().st_size > 0, "capture missing: " + str(path))
        self.report.update({
            "status": "PASS_R54_CLOUD_RADIUS_TRANSIENT_DISCRIMINATOR_PENDING_PIXEL_REVIEW",
            "completed_utc": now(),
            "captures": {
                "baseline_6360km": {"path": str(BASELINE), "bytes": BASELINE.stat().st_size, "sha256": sha256(BASELINE)},
                "corrected_3000km": {"path": str(CORRECTED), "bytes": CORRECTED.stat().st_size, "sha256": sha256(CORRECTED)},
            },
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "save_called": False,
            "claim_limit": "Matched existing-viewport D3D12 pixels pending independent review; no persistent correction or acceptance claim.",
        })
        atomic_json(RESULT, self.report)
        unreal.log("REDMMO_R54_PASS")
        self.schedule_quit(2.0)

    def fail(self, error):
        if self.cloud is not None and self.original_radius is not None:
            try:
                self.cloud.set_editor_property("planet_radius", self.original_radius)
            except Exception:
                pass
        self.report.update({"status": "FAIL", "failed_phase": self.phase, "completed_utc": now(),
                            "error": str(error), "traceback": traceback.format_exc()})
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        if not RESULT.exists():
            atomic_json(RESULT, self.report)
        unreal.log_error("REDMMO_R54_FAIL " + str(error))
        self.schedule_quit(2.0)

    def schedule_quit(self, delay):
        started = time.monotonic()
        if self.handle is not None:
            try:
                unreal.unregister_slate_post_tick_callback(self.handle)
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
                require(elapsed <= 30.0, "PIE startup timeout")
                self.bind_pie()
            elif self.phase == "WAIT_GENERATION":
                require(elapsed <= 240.0, "generation timeout")
                if self.generation_complete():
                    self.set_phase("SETTLE_BASELINE")
            elif self.phase == "SETTLE_BASELINE":
                require(elapsed <= 25.0, "baseline settle timeout")
                if elapsed >= 8.0:
                    self.request_baseline()
            elif self.phase == "WAIT_BASELINE":
                require(elapsed <= 30.0, "baseline capture timeout")
                if BASELINE.is_file() and BASELINE.stat().st_size > 0 and elapsed >= 2.0:
                    self.apply_target()
            elif self.phase == "SETTLE_TARGET":
                require(elapsed <= 20.0, "target settle timeout")
                if elapsed >= 5.0:
                    self.request_corrected()
            elif self.phase == "WAIT_CORRECTED":
                require(elapsed <= 30.0, "corrected capture timeout")
                if CORRECTED.is_file() and CORRECTED.stat().st_size > 0 and elapsed >= 2.0:
                    self.restore()
            elif self.phase == "SETTLE_RESTORE":
                require(elapsed <= 15.0, "restore settle timeout")
                if elapsed >= 3.0:
                    self.request_stop()
            elif self.phase == "WAIT_STOP":
                require(elapsed <= 15.0, "PIE stop timeout")
                if not self.level.is_in_play_in_editor():
                    self.finish()
        except Exception as error:
            self.fail(error)

    def start(self):
        self.handle = unreal.register_slate_post_tick_callback(self.tick)


try:
    _R54 = R54()
    _R54.start()
except Exception as bootstrap_error:
    atomic_json(RESULT, {"schema": "redmmo.cloud-radius-surface-sky.r54.v1", "status": "FAIL",
                         "completed_utc": now(), "error": str(bootstrap_error),
                         "traceback": traceback.format_exc()})
    unreal.SystemLibrary.quit_editor()
