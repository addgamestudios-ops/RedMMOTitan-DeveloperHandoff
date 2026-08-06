"""No-save R30 runtime audit of installed-PPG GPU grass dispatch/render facts."""

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
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1GrassDispatch_R30B_20260805T1300Z")
RESULT = DIAG / "result.json"


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


def material_record(component):
    material = component.get_material(0)
    return {
        "material": asset_path(material),
        "base_material": asset_path(material.get_base_material()) if material is not None else None,
        "material_count": int(component.get_num_materials()),
    }


def normalized_key(value):
    return str(value).replace("_", "").replace(" ", "").lower()


def struct_field(value, wanted):
    fields = value.to_dict()
    target = normalized_key(wanted)
    matches = [item for key, item in fields.items() if normalized_key(key) in (target, "b" + target)]
    require(len(matches) == 1, "expected one reflected field {} in {}".format(wanted, list(fields)))
    return matches[0]


def diagnostic_record(component, pawn_location):
    diag = unreal.RedPPGFoliageDiagnostics.inspect_component(component)
    require(bool(struct_field(diag, "is_ppg_gpu_foliage_component")), "diagnostic adapter rejected PPG component")
    origin = struct_field(diag, "world_location")
    bounds_origin = struct_field(diag, "bounds_origin")
    bounds_radius = float(struct_field(diag, "bounds_sphere_radius"))
    return {
        "component": component.get_path_name(),
        "mesh": asset_path(component.get_editor_property("static_mesh")),
        "num_instances": int(struct_field(diag, "num_instances")),
        "instance_data_ready": bool(struct_field(diag, "instance_data_ready")),
        "registered": bool(struct_field(diag, "registered")),
        "render_state_created": bool(struct_field(diag, "render_state_created")),
        "has_scene_proxy": bool(struct_field(diag, "has_scene_proxy")),
        "last_render_time_on_screen": float(struct_field(diag, "last_render_time_on_screen")),
        "min_draw_distance": float(struct_field(diag, "min_draw_distance")),
        "cached_max_draw_distance": float(struct_field(diag, "cached_max_draw_distance")),
        "world_location": vec(origin),
        "origin_distance_to_pawn_cm": distance(origin, pawn_location),
        "bounds_origin": vec(bounds_origin),
        "bounds_sphere_radius": bounds_radius,
        "pawn_distance_to_bounds_sphere_cm": max(0.0, distance(bounds_origin, pawn_location) - bounds_radius),
        **material_record(component),
    }


class R30:
    def __init__(self):
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.handle = None
        self.phase = "PREPARE"
        self.started = time.monotonic()
        self.world = None
        self.pawn = None
        self.spawner = None
        self.report = {
            "schema": "redmmo.ppg_profile_v1.grass_dispatch.audit.r30.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "evidence_class": "automation",
        }

    def set_phase(self, phase):
        self.phase = phase
        self.started = time.monotonic()
        self.report["phase"] = phase
        unreal.log("REDMMO_R30_PHASE " + phase)

    def authenticate(self):
        active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(active == PROJECT.resolve(strict=True), "wrong project")
        require(not RESULT.exists(), "R30 no-clobber failed")
        for path, expected in ((PROJECT, PROJECT_SHA), (HOME_FILE, HOME_SHA), (PROFILE_FILE, PROFILE_SHA), (FOLIAGE_FILE, FOLIAGE_SHA)):
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

    def inspect(self):
        actor = self.spawner.get_foliage_actor()
        require(actor is not None, "foliage actor missing")
        pawn_location = self.pawn.get_actor_location()
        records = []
        for component in list(actor.get_components_by_class(unreal.StaticMeshComponent)):
            if component.get_class().get_name() != "PPGGPUFoliageComponent":
                continue
            mesh = asset_path(component.get_editor_property("static_mesh"))
            if mesh in APPROVED_GRASS:
                records.append(diagnostic_record(component, pawn_location))
        require(records, "no approved grass components")
        positive = [item for item in records if item["num_instances"] > 0]
        renderable = [
            item for item in positive
            if item["instance_data_ready"] and item["registered"]
            and item["render_state_created"] and item["has_scene_proxy"]
        ]
        near_origin = [item for item in positive if item["origin_distance_to_pawn_cm"] <= 50000.0]
        near_bounds = [item for item in positive if item["pawn_distance_to_bounds_sphere_cm"] <= 50000.0]
        records.sort(key=lambda item: (item["origin_distance_to_pawn_cm"], item["component"]))
        self.report["grass_dispatch"] = {
            "approved_component_count": len(records),
            "positive_instance_component_count": len(positive),
            "total_instances": sum(item["num_instances"] for item in positive),
            "renderable_component_count": len(renderable),
            "positive_instance_origins_within_500m": len(near_origin),
            "positive_instance_bounds_within_500m": len(near_bounds),
            "nearest_24": records[:24],
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
            "status": "PASS_R30_NO_SAVE_PPG_GRASS_DISPATCH_DIAGNOSTIC",
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "home_sha256_before_after": HOME_SHA,
            "profile_sha256_before_after": PROFILE_SHA,
            "foliage_sha256_before_after": FOLIAGE_SHA,
            "save_called": False,
            "completed_utc": now(),
            "claim_limit": "C++ bridge plus runtime dispatch diagnostics only; no visual, gameplay, package or multiplayer acceptance.",
        })
        atomic_json(RESULT, self.report)
        unreal.log("REDMMO_R30_PASS")
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
                    self.inspect()
            elif self.phase == "WAIT_STOP":
                require(elapsed <= 15.0, "PIE stop timeout")
                if not self.level.is_in_play_in_editor():
                    self.finish()
        except Exception as error:
            self.fail(error)

    def start(self):
        self.handle = unreal.register_slate_post_tick_callback(self.tick)


try:
    _R30 = R30()
    _R30.start()
except Exception as bootstrap_error:
    DIAG.mkdir(parents=True, exist_ok=True)
    atomic_json(RESULT, {
        "schema": "redmmo.ppg_profile_v1.grass_dispatch.audit.r30.v1",
        "status": "FAIL",
        "error": str(bootstrap_error),
        "traceback": traceback.format_exc(),
        "completed_utc": now(),
    })
    unreal.SystemLibrary.quit_editor()
