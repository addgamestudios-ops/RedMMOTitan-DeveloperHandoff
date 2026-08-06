"""R53 no-save runtime diagnosis for the black PPG surface sky.

Records the saved valid-land player view, PPG body frame, atmosphere sun,
SkyAtmosphere geometry, skylight/fog/cloud state, and the project-owned night
presenter without changing or saving any actor, package, seed, foliage, or map.
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
PROFILE_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
R29_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_GrassEligible_R29.uasset"
R32_FILE = PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R32\Materials\M_GrassChunks_PPGReadable_R32.uasset"
INSTANCE_A_FILE = PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_A_R10N.uasset"
INSTANCE_B_FILE = PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_B_R10N.uasset"
PROTECTED_TEST = Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap")
PROTECTED_FUSED = Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap")
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_SurfaceSky_R53B_20260805T1858Z")
RESULT = DIAG / "result.json"

CHECKS = {
    PROJECT: "3BF3D8D1D1C7F892A2CD4873F7C0390EC1AF3CA8F77E60549169563D18DBF86F",
    HOME_FILE: "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3",
    PROFILE_FILE: "D226215C7367808F4A2E3225A0C9CBD7F4F32E803ABEFD22CA39062CD5538970",
    R29_FILE: "D1ACEE4F403D2082FF49CB57D52907AAADA0C20D06386576C435557CF49404D8",
    R32_FILE: "2BD2B8DD41C611CF1250F1A39C40D3B4A7C47B5EB71ECD1497732546B80F0210",
    INSTANCE_A_FILE: "91A0E7233A5922A921FB4CF8692B8631DBB7AEFE7D3D106FDB63C44DB412CE47",
    INSTANCE_B_FILE: "19D1B594553977A6A7BA116271F103DCD4044F8F24C3E8B5CF8F596082A9F68E",
    PROTECTED_TEST: "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    PROTECTED_FUSED: "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}


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


def vec(value):
    return [float(value.x), float(value.y), float(value.z)]


def rot(value):
    return [float(value.pitch), float(value.yaw), float(value.roll)]


def length(value):
    return math.sqrt(float(value.x * value.x + value.y * value.y + value.z * value.z))


def normalized(value):
    magnitude = length(value)
    require(magnitude > 1.0e-6, "zero vector")
    return unreal.Vector(value.x / magnitude, value.y / magnitude, value.z / magnitude)


def dot(a, b):
    return float(a.x * b.x + a.y * b.y + a.z * b.z)


def safe_prop(obj, name):
    try:
        value = obj.get_editor_property(name)
        if isinstance(value, unreal.Vector):
            return vec(value)
        if isinstance(value, unreal.Rotator):
            return rot(value)
        if isinstance(value, unreal.LinearColor):
            return [float(value.r), float(value.g), float(value.b), float(value.a)]
        if hasattr(value, "get_path_name"):
            return value.get_path_name()
        return value
    except Exception as error:
        return {"unavailable": str(error).split("\n", 1)[0]}


def props(obj, names):
    return {name: safe_prop(obj, name) for name in names}


def actor_base(actor):
    return {
        "path": actor.get_path_name(),
        "label": actor.get_actor_label(),
        "class": actor.get_class().get_path_name(),
        "location_cm": vec(actor.get_actor_location()),
        "rotation_deg": rot(actor.get_actor_rotation()),
        "forward": vec(actor.get_actor_forward_vector()),
        "hidden": safe_prop(actor, "hidden"),
    }


def first_component(actor, cls):
    values = list(actor.get_components_by_class(cls))
    return values[0] if len(values) == 1 else None


def material_record(material):
    if material is None:
        return None
    record = {"path": material.get_path_name(), "class": material.get_class().get_path_name()}
    base = None
    try:
        base = material.get_base_material()
    except Exception:
        if isinstance(material, unreal.Material):
            base = material
    if base is not None:
        record["base"] = base.get_path_name()
        record["base_properties"] = props(base, [
            "material_domain", "blend_mode", "shading_model", "two_sided",
            "disable_depth_test", "is_sky", "used_with_static_lighting",
        ])
    return record


class R53:
    def __init__(self):
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.handle = None
        self.phase = "PREPARE"
        self.phase_started = time.monotonic()
        self.report = {
            "schema": "redmmo.surface-sky.r53.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "map": HOME_MAP,
            "renderer": "D3D12_RenderOffscreen",
            "mutation_policy": "read_only_no_save",
        }
        self.world = None
        self.spawner = None
        self.pawn = None

    def set_phase(self, value):
        self.phase = value
        self.phase_started = time.monotonic()
        unreal.log("REDMMO_R53_PHASE " + value)

    def prepare(self):
        active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(active == PROJECT.resolve(strict=True), "wrong project")
        require(not RESULT.exists(), "R53 result exists")
        for path, expected in CHECKS.items():
            require(sha256(path) == expected, "hash drift: " + str(path))
        require(dirty_packages() == {"content": [], "maps": []}, "dirty packages before R53")
        self.report["provider_gate_before"] = provider_gate()
        require(self.level.load_level(HOME_MAP), "unable to load home map")
        require(dirty_packages() == {"content": [], "maps": []}, "load dirtied packages")
        world_path = unreal.EditorLevelLibrary.get_editor_world().get_path_name().split(":", 1)[0].split(".", 1)[0]
        require(world_path == HOME_MAP, "wrong map: " + world_path)
        self.level.editor_request_begin_play()
        self.set_phase("WAIT_PIE")

    def bind(self):
        world = self.editor.get_game_world()
        if world is None or not self.level.is_in_play_in_editor():
            return False
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        if pawn is None:
            return False
        actors = list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor))
        spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        require(len(spawners) == 1, "expected one PlanetSpawnerBP")
        self.world, self.spawner, self.pawn = world, spawners[0], pawn
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

    def collect(self):
        actors = list(unreal.GameplayStatics.get_all_actors_of_class(self.world, unreal.Actor))
        presenters = [a for a in actors if a.get_class().get_name() == "RedPlanetNightPresenter"]
        require(len(presenters) == 1, "expected one RedPlanetNightPresenter")
        presenter = presenters[0]
        controller = unreal.GameplayStatics.get_player_controller(self.world, 0)
        require(controller is not None, "player controller missing")
        camera_location = self.pawn.get_actor_location()
        camera_rotation = self.pawn.get_actor_rotation()
        try:
            view = controller.get_player_view_point()
            for item in view if isinstance(view, tuple) else []:
                if isinstance(item, unreal.Vector):
                    camera_location = item
                elif isinstance(item, unreal.Rotator):
                    camera_rotation = item
        except Exception:
            pass

        center = self.spawner.get_actor_location()
        planet = self.spawner.get_editor_property("planet_data")
        require(planet is not None, "bound PlanetData missing")
        planet_radius_cm = float(planet.get_editor_property("planet_radius"))
        radial_up = normalized(camera_location - center)

        directional = []
        atmosphere_suns = []
        for actor in actors:
            if not isinstance(actor, unreal.DirectionalLight):
                continue
            component = first_component(actor, unreal.DirectionalLightComponent)
            record = actor_base(actor)
            if component is not None:
                record["component"] = props(component, [
                    "visible", "hidden_in_game", "intensity", "light_color",
                    "atmosphere_sun_light", "atmosphere_sun_light_index",
                    "cast_shadows", "cast_cloud_shadows", "affects_world",
                ])
                if safe_prop(component, "atmosphere_sun_light") is True and safe_prop(component, "atmosphere_sun_light_index") == 0:
                    atmosphere_suns.append((actor, record))
            directional.append(record)
        require(len(atmosphere_suns) == 1, "expected one atmosphere sun index 0")
        sun_actor, sun_record = atmosphere_suns[0]
        sun_direction = normalized(-sun_actor.get_actor_forward_vector())
        solar_dot = dot(radial_up, sun_direction)

        sky_atmospheres = []
        atmosphere_geometry = []
        for actor in actors:
            if not isinstance(actor, unreal.SkyAtmosphere):
                continue
            component = first_component(actor, unreal.SkyAtmosphereComponent)
            record = actor_base(actor)
            if component is not None:
                record["component"] = props(component, [
                    "visible", "hidden_in_game", "transform_mode", "bottom_radius",
                    "atmosphere_height", "ground_albedo", "multi_scattering_factor",
                    "rayleigh_scattering_scale", "mie_scattering_scale",
                    "aerial_perspective_view_distance_scale", "trace_sample_count_scale",
                ])
                bottom = safe_prop(component, "bottom_radius")
                mode = str(safe_prop(component, "transform_mode"))
                if isinstance(bottom, (int, float)):
                    bottom_cm = float(bottom) * 100000.0
                    upper = mode.upper()
                    if "CENTER" in upper:
                        atmosphere_center = actor.get_actor_location()
                    else:
                        top = unreal.Vector(0.0, 0.0, 0.0) if "ABSOLUTE" in upper else actor.get_actor_location()
                        atmosphere_center = top - unreal.Vector(0.0, 0.0, bottom_cm)
                    camera_radius_km = length(camera_location - atmosphere_center) / 100000.0
                    atmosphere_geometry.append({
                        "actor": actor.get_path_name(),
                        "transform_mode": mode,
                        "bottom_radius_km": float(bottom),
                        "implied_center_cm": vec(atmosphere_center),
                        "ppg_center_offset_km": length(center - atmosphere_center) / 100000.0,
                        "camera_radius_from_atmosphere_center_km": camera_radius_km,
                        "camera_altitude_from_atmosphere_bottom_km": camera_radius_km - float(bottom),
                    })
            sky_atmospheres.append(record)

        skylights = []
        fogs = []
        clouds = []
        for actor in actors:
            if isinstance(actor, unreal.SkyLight):
                component = first_component(actor, unreal.SkyLightComponent)
                record = actor_base(actor)
                if component is not None:
                    record["component"] = props(component, [
                        "visible", "hidden_in_game", "intensity", "light_color",
                        "source_type", "real_time_capture", "lower_hemisphere_is_black",
                        "sky_distance_threshold", "volumetric_scattering_intensity",
                    ])
                skylights.append(record)
            elif isinstance(actor, unreal.ExponentialHeightFog):
                component = first_component(actor, unreal.ExponentialHeightFogComponent)
                record = actor_base(actor)
                if component is not None:
                    record["component"] = props(component, [
                        "visible", "hidden_in_game", "fog_density", "fog_height_falloff",
                        "fog_max_opacity", "start_distance", "volumetric_fog",
                    ])
                fogs.append(record)
            elif isinstance(actor, unreal.VolumetricCloud):
                component = first_component(actor, unreal.VolumetricCloudComponent)
                record = actor_base(actor)
                if component is not None:
                    record["component"] = props(component, [
                        "visible", "hidden_in_game", "layer_bottom_altitude", "layer_height",
                        "planet_radius", "material",
                    ])
                clouds.append(record)

        star_components = [c for c in presenter.get_components_by_class(unreal.StaticMeshComponent) if "StarDome" in c.get_name()]
        require(len(star_components) == 1, "expected one star dome")
        star = star_components[0]
        presenter_record = actor_base(presenter)
        presenter_record["runtime"] = props(presenter, [
            "required_body_id", "star_material", "star_dome_radius_cm", "star_emission",
            "star_cell_scale", "star_density", "star_point_radius", "night_fill_lux_per_weight",
            "atmosphere_fade_start_altitude_cm", "atmosphere_fade_end_altitude_cm",
            "last_frame_resolved", "last_altitude_cm", "last_night_hemisphere_weight",
            "last_star_visibility_weight", "last_night_fill_weight",
        ])
        presenter_record["star_dome"] = {
            "path": star.get_path_name(),
            "visible": safe_prop(star, "visible"),
            "hidden_in_game": safe_prop(star, "hidden_in_game"),
            "world_location_cm": vec(star.get_world_location()),
            "world_scale": vec(star.get_world_transform().scale3d),
            "bounds": str(star.get_local_bounds()),
            "static_mesh": safe_prop(star, "static_mesh"),
            "material": material_record(star.get_material(0)),
        }

        self.report.update({
            "status": "PASS_R53_READ_ONLY_SURFACE_SKY_RUNTIME_DIAGNOSIS",
            "player_view": {
                "pawn_class": self.pawn.get_class().get_path_name(),
                "camera_location_cm": vec(camera_location),
                "camera_rotation_deg": rot(camera_rotation),
                "ppg_center_cm": vec(center),
                "ppg_planet_radius_cm": planet_radius_cm,
                "ppg_planet_radius_km": planet_radius_cm / 100000.0,
                "camera_radius_from_ppg_center_km": length(camera_location - center) / 100000.0,
                "camera_altitude_from_ppg_nominal_km": (length(camera_location - center) - planet_radius_cm) / 100000.0,
                "radial_up": vec(radial_up),
            },
            "solar": {
                "solar_dot": solar_dot,
                "classification": "day" if solar_dot >= 0.10 else ("full_night" if solar_dot <= -0.25 else "terminator"),
                "sun_direction_from_body": vec(sun_direction),
                "atmosphere_sun": sun_record,
            },
            "sky_atmospheres": sky_atmospheres,
            "atmosphere_geometry": atmosphere_geometry,
            "skylights": skylights,
            "height_fogs": fogs,
            "volumetric_clouds": clouds,
            "night_presenter": presenter_record,
            "directional_lights": directional,
            "actor_class_counts": {
                name: sum(1 for actor in actors if actor.get_class().get_name() == name)
                for name in sorted({actor.get_class().get_name() for actor in actors})
                if any(token in name for token in ("Sky", "Atmosphere", "Fog", "Cloud", "Light", "Night"))
            },
        })
        self.level.editor_request_end_play()
        self.set_phase("WAIT_STOP")

    def finish(self):
        require(not self.level.is_in_play_in_editor(), "PIE did not stop")
        require(dirty_packages() == {"content": [], "maps": []}, "R53 dirtied packages")
        for path, expected in CHECKS.items():
            require(sha256(path) == expected, "post hash drift: " + str(path))
        self.report.update({
            "completed_utc": now(),
            "provider_gate_after": provider_gate(),
            "dirty_packages_after": dirty_packages(),
            "hashes_after": {str(path): sha256(path) for path in CHECKS},
            "save_called": False,
            "claim_limit": "Runtime state diagnosis only; no sky correction, visual acceptance, gameplay, standalone, replication, or multiplayer claim.",
        })
        atomic_json(RESULT, self.report)
        unreal.log("REDMMO_R53_PASS")
        self.schedule_quit(2.0)

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
                self.prepare()
            elif self.phase == "WAIT_PIE":
                require(elapsed <= 30.0, "PIE startup timeout")
                self.bind()
            elif self.phase == "WAIT_GENERATION":
                require(elapsed <= 240.0, "generation timeout")
                if self.generation_ready():
                    self.set_phase("SETTLE")
            elif self.phase == "SETTLE":
                require(elapsed <= 20.0, "settle timeout")
                if elapsed >= 5.0:
                    self.collect()
            elif self.phase == "WAIT_STOP":
                require(elapsed <= 15.0, "PIE stop timeout")
                if not self.level.is_in_play_in_editor():
                    self.finish()
        except Exception as error:
            self.fail(error)

    def start(self):
        self.handle = unreal.register_slate_post_tick_callback(self.tick)


try:
    _R53 = R53()
    _R53.start()
except Exception as bootstrap_error:
    atomic_json(RESULT, {
        "schema": "redmmo.surface-sky.r53.v1",
        "status": "FAIL",
        "error": str(bootstrap_error),
        "traceback": traceback.format_exc(),
        "completed_utc": now(),
    })
    unreal.SystemLibrary.quit_editor()
