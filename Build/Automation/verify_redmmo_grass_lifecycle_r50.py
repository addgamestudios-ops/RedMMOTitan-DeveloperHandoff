"""R50 read-only PPG approved-grass lifecycle timing audit.

Samples the exact approved PPG grass components from PIE startup through
generation COMPLETE, one untouched high-resolution capture, and the known
post-capture readiness window. This script never changes component properties,
materials, foliage data, seed, distribution, surface, map, or packages.
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
HEADER_FILE = PROJECT.parent / r"Source\RedMMO\Public\RedPPGGameplayGameMode.h"
SOURCE_FILE = PROJECT.parent / r"Source\RedMMO\Private\RedPPGGameplayGameMode.cpp"
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
    HEADER_FILE: "94BEB7B37448C5CEC49F1F38B927B9AA153AAC7671F78B42EC78B46D24AE1639",
    SOURCE_FILE: "022C2B422D9BA20270B6CFA88BF1DB6B51D967AB2E88A7E6C34898CB1E4CD893",
    BINARY_FILE: "21081D7DA8239FD6606868808BB48234117B81C9A27ACBC7E25CA7F5D713FA30",
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
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_GrassLifecycle_R50_20260805T1814Z")
RESULT = DIAG / "result.json"
CAPTURE = DIAG / "R50_lifecycle_event_capture.png"


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


def inspect_grass_relaxed(spawner):
    foliage = spawner.get_foliage_actor()
    if foliage is None:
        return {"foliage_actor": None, "components": 0, "instances": 0, "visible_true": 0,
                "hidden_in_game_true": 0, "registered": 0, "instance_data_ready": 0,
                "scene_proxy": 0, "positive_last_render": 0, "identity_sha256": None,
                "not_registered": [], "not_instance_data_ready": [], "no_scene_proxy": [],
                "inspection_errors": ["foliage actor missing"]}
    components = [
        component for component in list(foliage.get_components_by_class(unreal.StaticMeshComponent))
        if component.get_class().get_name() == "PPGGPUFoliageComponent"
        and asset_path(component.get_editor_property("static_mesh")) in GRASS_MESHES
    ]
    records = []
    errors = []
    for component in components:
        identity = component.get_path_name()
        try:
            diag = unreal.RedPPGFoliageDiagnostics.inspect_component(component)
            records.append({
                "identity": identity,
                "instances": int(field(diag, "num_instances")),
                "visible": bool(component.get_editor_property("visible")),
                "hidden_in_game": bool(component.get_editor_property("hidden_in_game")),
                "registered": bool(field(diag, "registered")),
                "instance_data_ready": bool(field(diag, "instance_data_ready")),
                "scene_proxy": bool(field(diag, "has_scene_proxy")),
                "last_render": float(field(diag, "last_render_time_on_screen")),
            })
        except Exception as error:
            errors.append(identity + ": " + str(error))
    identities = sorted(item["identity"] for item in records)
    identity_hash = hashlib.sha256("\n".join(identities).encode("utf-8")).hexdigest().upper() if identities else None
    return {
        "foliage_actor": foliage.get_path_name(),
        "components": len(records),
        "instances": sum(item["instances"] for item in records),
        "visible_true": sum(item["visible"] for item in records),
        "hidden_in_game_true": sum(item["hidden_in_game"] for item in records),
        "registered": sum(item["registered"] for item in records),
        "instance_data_ready": sum(item["instance_data_ready"] for item in records),
        "scene_proxy": sum(item["scene_proxy"] for item in records),
        "positive_last_render": sum(item["last_render"] > 0.0 for item in records),
        "identity_sha256": identity_hash,
        "not_registered": sorted(item["identity"] for item in records if not item["registered"]),
        "not_instance_data_ready": sorted(item["identity"] for item in records if not item["instance_data_ready"]),
        "no_scene_proxy": sorted(item["identity"] for item in records if not item["scene_proxy"]),
        "inspection_errors": errors,
    }


class R50:
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
        self.capture_requested_monotonic = None
        self.capture_ready_monotonic = None
        self.timeline = []
        self.report = {
            "schema": "redmmo.grass_lifecycle.r50.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "evidence_class": "automation",
            "slice": "R50 read-only PPG approved-grass lifecycle timing audit",
            "mutations": {
                "component_property_write": False,
                "visibility_cycle": False,
                "view_mode_command": False,
                "material_or_asset_write": False,
                "save": False,
            },
        }

    def set_phase(self, phase):
        self.phase = phase
        self.phase_started = time.monotonic()
        self.report["phase"] = phase
        unreal.log("REDMMO_R50_PHASE " + phase)

    def sample(self, force=False):
        elapsed = time.monotonic() - self.audit_started
        if not force and elapsed - self.last_sample < 0.25:
            return
        self.last_sample = elapsed
        record = {
            "index": len(self.timeline),
            "utc": now(),
            "elapsed_seconds": round(elapsed, 6),
            "phase": self.phase,
            "phase_elapsed_seconds": round(time.monotonic() - self.phase_started, 6),
            "capture_requested": self.capture_requested_monotonic is not None,
            "capture_file_ready": CAPTURE.is_file() and CAPTURE.stat().st_size > 0,
            "generation": generation_record(self.spawner),
            "grass": inspect_grass_relaxed(self.spawner),
        }
        self.timeline.append(record)

    def authenticate(self):
        active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(active == PROJECT.resolve(strict=True), "wrong project")
        require(not RESULT.exists() and not CAPTURE.exists(), "R50 no-clobber failed")
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
        self.set_phase("OBSERVE_GENERATION")
        self.sample(True)
        return True

    def generation_complete(self):
        record = generation_record(self.spawner)
        return "COMPLETE" in record["phase"].upper() and record["progress"] >= 0.999 and not record["is_generating"]

    def request_capture(self):
        state = inspect_grass_relaxed(self.spawner)
        require(state["components"] == 196 and state["instances"] == 2218356, "pre-capture census drift")
        require(state["registered"] == 196 and state["instance_data_ready"] == 196 and state["scene_proxy"] == 196, "pre-capture readiness drift")
        self.report["pre_capture_state"] = state
        task = unreal.AutomationLibrary.take_high_res_screenshot(1280, 720, str(CAPTURE))
        require(task is not None, "R50 capture request failed")
        self.capture_requested_monotonic = time.monotonic()
        self.report["capture_requested_utc"] = now()
        self.set_phase("OBSERVE_POST_CAPTURE")
        self.sample(True)

    def analyze(self):
        post = [item for item in self.timeline if item["capture_requested"]]
        require(post, "no post-capture samples")
        grass = [item["grass"] for item in post]
        identities = sorted({item["identity_sha256"] for item in grass if item["identity_sha256"]})
        transitions = []
        previous = None
        for item in self.timeline:
            state = item["grass"]
            signature = (
                state["components"], state["instances"], state["registered"],
                state["instance_data_ready"], state["scene_proxy"], state["identity_sha256"],
            )
            if signature != previous:
                transitions.append({"index": item["index"], "elapsed_seconds": item["elapsed_seconds"],
                                    "phase": item["phase"], "capture_file_ready": item["capture_file_ready"],
                                    "signature": list(signature)})
                previous = signature
        return {
            "sample_count": len(self.timeline),
            "post_capture_sample_count": len(post),
            "post_capture_min_components": min(item["components"] for item in grass),
            "post_capture_min_instances": min(item["instances"] for item in grass),
            "post_capture_min_registered": min(item["registered"] for item in grass),
            "post_capture_min_instance_data_ready": min(item["instance_data_ready"] for item in grass),
            "post_capture_min_scene_proxy": min(item["scene_proxy"] for item in grass),
            "post_capture_identity_hashes": identities,
            "post_capture_drift_observed": any(
                item["components"] != 196 or item["instances"] != 2218356 or
                item["registered"] != 196 or item["instance_data_ready"] != 196 or item["scene_proxy"] != 196
                for item in grass
            ),
            "state_transitions": transitions,
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
        self.report.update({
            "status": "PASS_R50_READ_ONLY_LIFECYCLE_TIMELINE_CAPTURED",
            "completed_utc": now(),
            "capture": {"path": str(CAPTURE), "bytes": CAPTURE.stat().st_size, "sha256": sha256(CAPTURE)},
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "claim_limit": "Read-only fresh-process D3D12 PIE lifecycle timing evidence; no material, component, map, asset, seed, distribution, surface or package mutation and no visual-acceptance claim.",
        })
        atomic_json(RESULT, self.report)
        unreal.log("REDMMO_R50_PASS")
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
        unreal.log_error("REDMMO_R50_FAIL " + str(error))
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
                if CAPTURE.is_file() and CAPTURE.stat().st_size > 0 and self.capture_ready_monotonic is None:
                    self.capture_ready_monotonic = time.monotonic()
                    self.report["capture_file_ready_utc"] = now()
                    self.sample(True)
                if self.capture_ready_monotonic is not None and time.monotonic() - self.capture_ready_monotonic >= 10.0:
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
    _R50 = R50()
    _R50.start()
    unreal.log("REDMMO_R50_STARTED")
except Exception as bootstrap_error:
    atomic_json(RESULT, {"schema": "redmmo.grass_lifecycle.r50.v1", "status": "FAIL",
                         "completed_utc": now(), "error": str(bootstrap_error),
                         "traceback": traceback.format_exc()})
    unreal.SystemLibrary.quit_editor()
