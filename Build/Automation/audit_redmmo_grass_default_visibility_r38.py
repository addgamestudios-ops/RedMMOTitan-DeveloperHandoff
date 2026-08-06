"""Read-only R38 PIE comparison of default versus transiently forced grass visibility."""

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
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_GrassDefaultVisibility_R38_20260805T1440Z")
RESULT = DIAG / "result.json"


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


def distance(a, b):
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


def component_record(component, pawn_location):
    diag = unreal.RedPPGFoliageDiagnostics.inspect_component(component)
    bounds_origin = struct_field(diag, "bounds_origin")
    bounds_radius = float(struct_field(diag, "bounds_sphere_radius"))
    material = component.get_material(0)
    return {
        "component": component.get_path_name(),
        "mesh": asset_path(component.get_editor_property("static_mesh")),
        "visible": bool(component.get_editor_property("visible")),
        "hidden_in_game": bool(component.get_editor_property("hidden_in_game")),
        "num_instances": int(struct_field(diag, "num_instances")),
        "instance_data_ready": bool(struct_field(diag, "instance_data_ready")),
        "registered": bool(struct_field(diag, "registered")),
        "render_state_created": bool(struct_field(diag, "render_state_created")),
        "has_scene_proxy": bool(struct_field(diag, "has_scene_proxy")),
        "last_render_time_on_screen": float(struct_field(diag, "last_render_time_on_screen")),
        "min_draw_distance": float(struct_field(diag, "min_draw_distance")),
        "cached_max_draw_distance": float(struct_field(diag, "cached_max_draw_distance")),
        "pawn_distance_to_bounds_sphere_cm": max(0.0, distance(bounds_origin, pawn_location) - bounds_radius),
        "material": asset_path(material),
        "base_material": asset_path(material.get_base_material()) if material is not None else None,
    }


def summarize(records):
    materials = {}
    bases = {}
    for item in records:
        materials[item["material"]] = materials.get(item["material"], 0) + 1
        bases[item["base_material"]] = bases.get(item["base_material"], 0) + 1
    return {
        "components": len(records),
        "instances": sum(item["num_instances"] for item in records),
        "visible_true": sum(item["visible"] for item in records),
        "hidden_in_game_true": sum(item["hidden_in_game"] for item in records),
        "registered": sum(item["registered"] for item in records),
        "render_state_created": sum(item["render_state_created"] for item in records),
        "has_scene_proxy": sum(item["has_scene_proxy"] for item in records),
        "positive_last_render_time": sum(item["last_render_time_on_screen"] > 0.0 for item in records),
        "bounds_within_500m": sum(item["pawn_distance_to_bounds_sphere_cm"] <= 50000.0 for item in records),
        "materials": materials,
        "base_materials": bases,
        "nearest_24": sorted(records, key=lambda item: (item["pawn_distance_to_bounds_sphere_cm"], item["component"]))[:24],
    }


class R38:
    def __init__(self):
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.handle = None
        self.phase = "PREPARE"
        self.started = time.monotonic()
        self.world = None
        self.pawn = None
        self.spawner = None
        self.components = []
        self.original = []
        self.report = {
            "schema": "redmmo.grass_default_visibility.audit.r38.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "evidence_class": "automation",
        }

    def set_phase(self, phase):
        self.phase = phase
        self.started = time.monotonic()
        self.report["phase"] = phase
        unreal.log("REDMMO_R38_PHASE " + phase)

    def authenticate(self):
        active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(active == PROJECT.resolve(strict=True), "wrong project")
        require(not RESULT.exists(), "R38 no-clobber failed")
        for path, expected in ((PROJECT, PROJECT_SHA), (HOME_FILE, HOME_SHA), (PROFILE_FILE, PROFILE_SHA), (FOLIAGE_FILE, FOLIAGE_SHA), (SURFACE_FILE, SURFACE_SHA)):
            require(path.is_file() and sha256(path) == expected, "input drift: " + str(path))
        for path, expected in {**GRASS_FILES, **PROTECTED}.items():
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
        record = {
            "phase": str(status.get_editor_property("phase")),
            "progress": float(status.get_editor_property("progress")),
            "is_generating": bool(status.get_editor_property("is_generating")),
        }
        self.report["generation"] = record
        return "COMPLETE" in record["phase"].upper() and record["progress"] >= 0.999 and not record["is_generating"]

    def collect_components(self):
        foliage_actor = self.spawner.get_foliage_actor()
        require(foliage_actor is not None, "foliage actor missing")
        self.components = [
            component for component in list(foliage_actor.get_components_by_class(unreal.StaticMeshComponent))
            if component.get_class().get_name() == "PPGGPUFoliageComponent"
            and asset_path(component.get_editor_property("static_mesh")) in GRASS_MESHES
        ]
        require(len(self.components) == 196, "approved component-count drift")
        self.original = [
            (component, bool(component.get_editor_property("visible")), bool(component.get_editor_property("hidden_in_game")))
            for component in self.components
        ]
        records = [component_record(component, self.pawn.get_actor_location()) for component in self.components]
        self.report["default_state"] = summarize(records)
        for component, _visible, _hidden in self.original:
            component.set_visibility(True, True)
            component.set_hidden_in_game(False)
        self.set_phase("SETTLE_FORCED")

    def collect_forced(self):
        records = [component_record(component, self.pawn.get_actor_location()) for component in self.components]
        self.report["forced_state"] = summarize(records)
        changed = sum((not visible) or hidden for _component, visible, hidden in self.original)
        self.report["transient_force"] = {
            "components_requiring_flag_change": changed,
            "set_visibility": True,
            "set_hidden_in_game": False,
            "saved": False,
        }
        for component, visible, hidden in self.original:
            component.set_visibility(visible, True)
            component.set_hidden_in_game(hidden)
        self.set_phase("SETTLE_RESTORE")

    def collect_restored(self):
        records = [component_record(component, self.pawn.get_actor_location()) for component in self.components]
        self.report["restored_state"] = summarize(records)
        for component, visible, hidden in self.original:
            require(bool(component.get_editor_property("visible")) == visible, "visible flag restore failed")
            require(bool(component.get_editor_property("hidden_in_game")) == hidden, "hidden flag restore failed")
        self.level.editor_request_end_play()
        self.set_phase("WAIT_STOP")

    def finish(self):
        require(not self.level.is_in_play_in_editor(), "PIE did not stop")
        require(dirty_packages() == {"content": [], "maps": []}, "PIE dirtied packages")
        for path, expected in ((HOME_FILE, HOME_SHA), (PROFILE_FILE, PROFILE_SHA), (FOLIAGE_FILE, FOLIAGE_SHA), (SURFACE_FILE, SURFACE_SHA)):
            require(sha256(path) == expected, "post-PIE drift: " + str(path))
        for path, expected in {**GRASS_FILES, **PROTECTED}.items():
            require(sha256(path) == expected, "grass/protected post-drift: " + str(path))
        default = self.report["default_state"]
        forced = self.report["forced_state"]
        self.report.update({
            "status": "PASS_R38_DEFAULT_VS_TRANSIENT_FORCED_GRASS_VISIBILITY_AUDIT",
            "completed_utc": now(),
            "diagnosis": {
                "default_flags_suppress_grass": default["visible_true"] < default["components"] or default["hidden_in_game_true"] > 0,
                "forced_flags_increase_last_render_count": forced["positive_last_render_time"] > default["positive_last_render_time"],
            },
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "save_called": False,
            "claim_limit": "Fresh D3D12 PIE component-state comparison only; no screenshot, save, visual acceptance, gameplay, package or multiplayer claim.",
        })
        atomic_json(RESULT, self.report)
        unreal.log("REDMMO_R38_PASS")
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
        unreal.log_error("REDMMO_R38_FAIL " + str(error))
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
                require(elapsed <= 25.0, "default-state settle timeout")
                if elapsed >= 8.0:
                    self.collect_components()
            elif self.phase == "SETTLE_FORCED":
                require(elapsed <= 15.0, "forced-state settle timeout")
                if elapsed >= 3.0:
                    self.collect_forced()
            elif self.phase == "SETTLE_RESTORE":
                require(elapsed <= 15.0, "restore-state settle timeout")
                if elapsed >= 2.0:
                    self.collect_restored()
            elif self.phase == "WAIT_STOP":
                require(elapsed <= 15.0, "PIE stop timeout")
                if not self.level.is_in_play_in_editor():
                    self.finish()
        except Exception as error:
            self.fail(error)

    def start(self):
        self.handle = unreal.register_slate_post_tick_callback(self.tick)


try:
    _R38 = R38()
    _R38.start()
except Exception as bootstrap_error:
    atomic_json(RESULT, {"schema": "redmmo.grass_default_visibility.audit.r38.v1", "status": "FAIL", "completed_utc": now(), "error": str(bootstrap_error), "traceback": traceback.format_exc()})
    unreal.SystemLibrary.quit_editor()
