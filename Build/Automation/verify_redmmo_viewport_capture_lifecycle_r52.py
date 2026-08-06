"""R52 existing-viewport capture lifecycle discriminator for approved PPG grass.

Uses the project-owned FScreenshotRequest bridge, never the high-resolution
automation path. It samples the exact approved components before, during, and
after file output without changing components, materials, seed, distribution,
surface, map, or packages.
"""

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
DIAGNOSTICS_HEADER = PROJECT.parent / r"Source\RedMMO\Public\RedPPGFoliageDiagnostics.h"
DIAGNOSTICS_SOURCE = PROJECT.parent / r"Source\RedMMO\Private\RedPPGFoliageDiagnostics.cpp"
BINARY_FILE = PROJECT.parent / r"Binaries\Win64\UnrealEditor-RedMMO.dll"
PROFILE_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
R29_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_GrassEligible_R29.uasset"
R32_FILE = PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R32\Materials\M_GrassChunks_PPGReadable_R32.uasset"
INSTANCE_A_FILE = PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_A_R10N.uasset"
INSTANCE_B_FILE = PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_B_R10N.uasset"
MESH_A_FILE = PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_A_R10N.uasset"
MESH_B_FILE = PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_B_R10N.uasset"
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
    MESH_A_FILE: "6F215104F1374403194D8AB4DA79B3FF16CCBF86472746E5CD433E03118B2443",
    MESH_B_FILE: "3C50C87B594CE012F680EF51BA306C2DF09FDAED10C06F7F60AFA4E62F678475",
    PROTECTED_TEST: "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    PROTECTED_FUSED: "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}
GRASS_MESHES = {
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_A_R10N",
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_B_R10N",
}
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_ViewportCaptureLifecycle_R52B_20260805T1846Z")
RESULT = DIAG / "result.json"
CAPTURE = DIAG / "R52_existing_viewport.png"


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


def generation_record(spawner):
    status = spawner.get_planet_generation_status()
    return {
        "phase": str(status.get_editor_property("phase")),
        "progress": float(status.get_editor_property("progress")),
        "is_generating": bool(status.get_editor_property("is_generating")),
    }


def inspect_grass(spawner):
    foliage = spawner.get_foliage_actor()
    if foliage is None:
        return {
            "components": 0,
            "instances": 0,
            "registered": 0,
            "instance_data_ready": 0,
            "scene_proxy": 0,
            "positive_last_render": 0,
            "identity_sha256": None,
        }
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
            "last_render": float(field(diag, "last_render_time_on_screen")),
        })
    identities = sorted(item["identity"] for item in records)
    identity_hash = hashlib.sha256("\n".join(identities).encode("utf-8")).hexdigest().upper()
    return {
        "components": len(records),
        "instances": sum(item["instances"] for item in records),
        "registered": sum(item["registered"] for item in records),
        "instance_data_ready": sum(item["instance_data_ready"] for item in records),
        "scene_proxy": sum(item["scene_proxy"] for item in records),
        "positive_last_render": sum(item["last_render"] > 0.0 for item in records),
        "identity_sha256": identity_hash,
    }


class R52:
    def __init__(self):
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.handle = None
        self.phase = "PREPARE"
        self.phase_started = time.monotonic()
        self.audit_started = self.phase_started
        self.last_sample = -999.0
        self.world = None
        self.spawner = None
        self.capture_requested = None
        self.capture_ready = None
        self.timeline = []
        self.report = {
            "schema": "redmmo.viewport_capture_lifecycle.r52.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "evidence_class": "automation",
            "slice": "R52 existing-viewport FScreenshotRequest grass lifecycle discriminator",
            "capture_api": "URedPPGFoliageDiagnostics::RequestViewportScreenshot -> FScreenshotRequest::RequestScreenshot",
            "mutations": {
                "component_property_write": False,
                "visibility_cycle": False,
                "view_mode_command": False,
                "material_or_asset_write": False,
                "save": False,
                "viewport_resize_request": False,
            },
        }

    def set_phase(self, phase):
        self.phase = phase
        self.phase_started = time.monotonic()
        self.report["phase"] = phase
        unreal.log("REDMMO_R52_PHASE " + phase)

    def sample(self, force=False):
        elapsed = time.monotonic() - self.audit_started
        if not force and elapsed - self.last_sample < 0.05:
            return
        self.last_sample = elapsed
        self.timeline.append({
            "index": len(self.timeline),
            "utc": now(),
            "elapsed_seconds": round(elapsed, 6),
            "phase": self.phase,
            "phase_elapsed_seconds": round(time.monotonic() - self.phase_started, 6),
            "capture_requested": self.capture_requested is not None,
            "capture_file_ready": CAPTURE.is_file() and CAPTURE.stat().st_size > 0,
            "generation": generation_record(self.spawner),
            "grass": inspect_grass(self.spawner),
        })

    def authenticate(self):
        active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(active == PROJECT.resolve(strict=True), "wrong project")
        require(not RESULT.exists() and not CAPTURE.exists(), "R52 no-clobber failed")
        for path, expected in CHECKS.items():
            require(path.is_file() and sha256(path) == expected, "input drift: " + str(path))
        require(dirty_packages() == {"content": [], "maps": []}, "editor started dirty")
        require(not self.level.is_in_play_in_editor(), "PIE already active")
        command = str(unreal.SystemLibrary.get_command_line()).lower()
        require("-d3d12" in command and "-renderoffscreen" in command and "-nullrhi" not in command, "renderer gate failed")
        require("-resx=1280" in command and "-resy=720" in command and "-forceres" in command, "viewport size gate failed")
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
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        if len(spawners) != 1 or pawn is None:
            return False
        self.world = world
        self.spawner = spawners[0]
        camera = unreal.GameplayStatics.get_player_camera_manager(world, 0)
        self.report["player_pawn"] = pawn.get_class().get_path_name()
        self.report["camera_location"] = str(camera.get_actor_location()) if camera else None
        self.report["camera_rotation"] = str(camera.get_actor_rotation()) if camera else None
        self.set_phase("OBSERVE_GENERATION")
        self.sample(True)
        return True

    def generation_complete(self):
        record = generation_record(self.spawner)
        return "COMPLETE" in record["phase"].upper() and record["progress"] >= 0.999 and not record["is_generating"]

    def request_capture(self):
        state = inspect_grass(self.spawner)
        require(state["components"] == 196 and state["instances"] == 2218356, "pre-capture census drift")
        require(state["registered"] == 196 and state["instance_data_ready"] == 196 and state["scene_proxy"] == 196, "pre-capture readiness drift")
        self.report["pre_capture_state"] = state
        camera = unreal.GameplayStatics.get_player_camera_manager(self.world, 0)
        self.report["capture_camera_location"] = str(camera.get_actor_location()) if camera else None
        self.report["capture_camera_rotation"] = str(camera.get_actor_rotation()) if camera else None
        self.sample(True)
        accepted = unreal.RedPPGFoliageDiagnostics.request_viewport_screenshot(str(CAPTURE))
        require(accepted, "FScreenshotRequest bridge rejected request")
        self.capture_requested = time.monotonic()
        self.report["capture_requested_utc"] = now()
        self.set_phase("OBSERVE_POST_CAPTURE")
        self.sample(True)

    def analyze(self):
        post = [item for item in self.timeline if item["capture_requested"]]
        require(post, "no post-capture samples")
        grass = [item["grass"] for item in post]
        identity_hashes = sorted({item["identity_sha256"] for item in grass if item["identity_sha256"]})
        minima = {
            key: min(item[key] for item in grass)
            for key in ("components", "instances", "registered", "instance_data_ready", "scene_proxy")
        }
        stable = (
            minima == {
                "components": 196,
                "instances": 2218356,
                "registered": 196,
                "instance_data_ready": 196,
                "scene_proxy": 196,
            }
            and len(identity_hashes) == 1
            and identity_hashes[0] == self.report["pre_capture_state"]["identity_sha256"]
        )
        return {
            "sample_count": len(self.timeline),
            "post_capture_sample_count": len(post),
            "post_capture_minima": minima,
            "post_capture_identity_hashes": identity_hashes,
            "readiness_stable": stable,
        }

    def request_stop(self):
        self.report["lifecycle_analysis"] = self.analyze()
        self.report["timeline"] = self.timeline
        self.level.editor_request_end_play()
        self.set_phase("WAIT_STOP")

    def finish(self):
        require(not self.level.is_in_play_in_editor(), "PIE did not stop")
        require(dirty_packages() == {"content": [], "maps": []}, "PIE dirtied packages")
        for path, expected in CHECKS.items():
            require(sha256(path) == expected, "post-PIE drift: " + str(path))
        require(CAPTURE.is_file() and CAPTURE.stat().st_size > 0, "capture missing")
        stable = self.report["lifecycle_analysis"]["readiness_stable"]
        self.report.update({
            "status": "PASS_R52_NON_RESIZING_CAPTURE_LIFECYCLE_STABLE" if stable else "FAIL_R52_NON_RESIZING_CAPTURE_READINESS_DRIFT",
            "completed_utc": now(),
            "capture": {"path": str(CAPTURE), "bytes": CAPTURE.stat().st_size, "sha256": sha256(CAPTURE)},
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "claim_limit": "Fresh-process D3D12 existing-viewport lifecycle evidence; visual content remains independently unreviewed.",
        })
        atomic_json(RESULT, self.report)
        unreal.log("REDMMO_R52_" + ("PASS" if stable else "FAIL_READINESS"))
        self.phase = "DONE"
        self.schedule_quit(3.0)

    def fail(self, error):
        failed_phase = self.phase
        self.phase = "FAILED"
        self.report.update({"status": "FAIL", "failed_phase": failed_phase, "completed_utc": now(),
                            "error": str(error), "traceback": traceback.format_exc(), "timeline": self.timeline})
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        if not RESULT.exists():
            atomic_json(RESULT, self.report)
        unreal.log_error("REDMMO_R52_FAIL " + str(error))
        self.schedule_quit(2.0)

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
            unreal.SystemLibrary.quit_editor()

        self.handle = unreal.register_slate_post_tick_callback(quit_tick)

    def tick(self, _delta):
        try:
            elapsed = time.monotonic() - self.phase_started
            if self.phase == "PREPARE":
                self.authenticate()
            elif self.phase == "WAIT_PIE":
                require(elapsed <= 25.0, "PIE startup timeout")
                self.bind_pie()
            elif self.phase == "OBSERVE_GENERATION":
                require(elapsed <= 240.0, "generation timeout")
                self.sample()
                if self.generation_complete():
                    self.set_phase("OBSERVE_SETTLE")
                    self.sample(True)
            elif self.phase == "OBSERVE_SETTLE":
                require(elapsed <= 30.0, "settle timeout")
                self.sample()
                if elapsed >= 12.0:
                    self.request_capture()
            elif self.phase == "OBSERVE_POST_CAPTURE":
                require(elapsed <= 30.0, "post-capture timeout")
                self.sample()
                if CAPTURE.is_file() and CAPTURE.stat().st_size > 0 and self.capture_ready is None:
                    self.capture_ready = time.monotonic()
                    self.report["capture_file_ready_utc"] = now()
                    self.sample(True)
                if self.capture_ready is not None and time.monotonic() - self.capture_ready >= 10.0:
                    self.sample(True)
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
    _R52 = R52()
    _R52.start()
    unreal.log("REDMMO_R52_STARTED")
except Exception as bootstrap_error:
    atomic_json(RESULT, {"schema": "redmmo.viewport_capture_lifecycle.r52.v1", "status": "FAIL",
                         "completed_utc": now(), "error": str(bootstrap_error),
                         "traceback": traceback.format_exc()})
    unreal.SystemLibrary.quit_editor()
