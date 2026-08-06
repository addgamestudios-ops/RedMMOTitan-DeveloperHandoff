"""No-save PIE diagnostic for R27 grass rendering and black surface sky."""

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
PROFILE_SHA = "5C50D50A8955C1E5F4270BDD4E53D1214C941725157B76422CD72B748978B837"
PLANET_DATA = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
R27_RESULT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1R26LandSpawnGrassPIE_R27_20260805T1210Z\result.json")
R27_SHA = "4D4C9BC55880FCC6277DA8CEC0A998F70171E9FE9515E5108A968D7518F9C1A2"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_R27GrassSurfaceSkyAudit_R28B_20260805T1225Z")
RESULT = DIAG / "result.json"

APPROVED_GRASS = {
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_A_R10N",
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_B_R10N",
}
APPROVED_FILES = {
    PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_A_R10N.uasset":
        "6F215104F1374403194D8AB4DA79B3FF16CCBF86472746E5CD433E03118B2443",
    PROJECT.parent / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_B_R10N.uasset":
        "3C50C87B594CE012F680EF51BA306C2DF09FDAED10C06F7F60AFA4E62F678475",
}
PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
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
    temporary = path.with_suffix(".tmp")
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
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


def vec(value):
    return [float(value.x), float(value.y), float(value.z)]


def distance(a, b):
    dx = float(a.x - b.x)
    dy = float(a.y - b.y)
    dz = float(a.z - b.z)
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def normalized(value):
    magnitude = math.sqrt(float(value.x * value.x + value.y * value.y + value.z * value.z))
    require(magnitude > 1.0e-6, "zero vector")
    return unreal.Vector(value.x / magnitude, value.y / magnitude, value.z / magnitude)


def dot(a, b):
    return float(a.x * b.x + a.y * b.y + a.z * b.z)


def dirty_packages():
    content = [asset_path(item) for item in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]
    maps = [asset_path(item) for item in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
    return {"content": sorted(set(content)), "maps": sorted(set(maps))}


def provider_gate():
    result = {}
    for port in (11111, 5353, 8000, 8765):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.15)
        try:
            result[str(port)] = sock.connect_ex(("127.0.0.1", port)) != 0
        finally:
            sock.close()
    return result


def safe_prop(obj, name):
    try:
        return obj.get_editor_property(name)
    except Exception:
        return None


def safe_call(obj, name, default=None):
    try:
        method = getattr(obj, name, None)
        return method() if callable(method) else default
    except Exception:
        return default


def bounds_record(value):
    if value is None:
        return None
    try:
        return {
            "origin": vec(value.origin),
            "box_extent": vec(value.box_extent),
            "sphere_radius": float(value.sphere_radius),
        }
    except Exception:
        return str(value)


def material_record(material):
    if material is None:
        return None
    record = {"path": material.get_path_name()}
    base = safe_call(material, "get_base_material")
    if base is None and isinstance(material, unreal.Material):
        base = material
    if base is not None:
        record.update({
            "base_material": base.get_path_name(),
            "blend_mode": str(safe_prop(base, "blend_mode")),
            "shading_model": str(safe_prop(base, "shading_model")),
            "two_sided": safe_prop(base, "two_sided"),
            "is_sky": safe_prop(base, "is_sky"),
            "opacity_mask_clip_value": safe_prop(base, "opacity_mask_clip_value"),
        })
    parameters = {}
    for name in (
        "LocalScale_Multiply",
        "GrassLocalZ_ScaleMultiply",
        "GrassHighlights_Amount",
        "GrassHighlights_Density",
        "GrassHighlights_Gradient_Contrast",
        "Visibility",
        "Emission",
        "CellScale",
        "Density",
        "PointRadius",
    ):
        try:
            parameters[name] = float(
                unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(material, name)
            )
        except Exception:
            continue
    if parameters:
        record["scalar_parameters"] = parameters
    return record


def mesh_record(mesh):
    if mesh is None:
        return None
    record = {"path": asset_path(mesh)}
    try:
        bounds = mesh.get_bounds()
    except Exception:
        bounds = safe_prop(mesh, "extended_bounds")
    record["bounds"] = bounds_record(bounds)
    try:
        record["lod_count"] = int(unreal.EditorStaticMeshLibrary.get_lod_count(mesh))
    except Exception as error:
        record["lod_count_error"] = str(error)
    record["materials"] = [
        material_record(mesh.get_material(index))
        for index in range(len(list(safe_prop(mesh, "static_materials") or [])))
    ]
    nanite = safe_prop(mesh, "nanite_settings")
    if nanite is not None:
        try:
            record["nanite_enabled"] = bool(nanite.get_editor_property("enabled"))
        except Exception:
            pass
    return record


def foliage_profile_record(planet):
    records = []
    for biome in list(planet.get_editor_property("biome_data")):
        name = str(biome.get_editor_property("name"))
        foliage = safe_prop(biome, "foliage_data")
        if foliage is None:
            foliage = safe_prop(biome, "forest_foliage_data")
        if foliage is None:
            continue
        for index, entry in enumerate(list(foliage.get_editor_property("foliage_list"))):
            meshes = []
            for variant in list(safe_prop(entry, "meshes") or []):
                mesh = safe_prop(variant, "mesh")
                if mesh is not None:
                    meshes.append(asset_path(mesh))
            legacy = safe_prop(entry, "foliage_mesh")
            if legacy is not None:
                meshes.append(asset_path(legacy))
            if not APPROVED_GRASS.intersection(meshes):
                continue
            scale = safe_prop(entry, "scale")
            records.append({
                "biome": name,
                "foliage_data": asset_path(foliage),
                "entry_index": index,
                "meshes": meshes,
                "density": float(safe_prop(entry, "foliage_density")),
                "scale_min": float(scale.get_editor_property("min")) if scale is not None else None,
                "scale_max": float(scale.get_editor_property("max")) if scale is not None else None,
                "spawn_distance": safe_prop(entry, "spawn_distance"),
                "culling_distance": safe_prop(entry, "culling_distance"),
                "min_slope": safe_prop(entry, "min_slope"),
                "max_slope": safe_prop(entry, "max_slope"),
                "depth_offset": safe_prop(entry, "depth_offset"),
                "align_to_terrain": safe_prop(entry, "align_to_terrain"),
                "uniform_scale": safe_prop(entry, "uniform_scale"),
                "force_cpu_ismc": safe_prop(entry, "force_cpu_ismc"),
                "lod_count": len(list(safe_prop(entry, "lods") or [])),
            })
    return records


def component_record(component, pawn_location):
    mesh = safe_prop(component, "static_mesh")
    location = component.get_world_location()
    transform = component.get_world_transform()
    bounds = safe_prop(component, "bounds")
    record = {
        "component": component.get_path_name(),
        "mesh": asset_path(mesh),
        "distance_to_pawn_cm": distance(location, pawn_location),
        "world_location": vec(location),
        "world_scale": vec(transform.scale3d),
        "bounds": bounds_record(bounds),
        "visible": bool(safe_prop(component, "visible")),
        "hidden_in_game": bool(safe_prop(component, "hidden_in_game")),
        "registered": bool(safe_call(component, "is_registered", False)),
        "render_state_created": bool(safe_call(component, "is_render_state_created", False)),
        "min_draw_distance": safe_prop(component, "min_draw_distance"),
        "cached_max_draw_distance": safe_prop(component, "cached_max_draw_distance"),
        "wpo_disable_distance": safe_prop(component, "world_position_offset_disable_distance"),
        "evaluate_wpo": safe_prop(component, "evaluate_world_position_offset"),
        "component_material": material_record(component.get_material(0)),
    }
    if isinstance(bounds, unreal.BoxSphereBounds):
        delta = distance(bounds.origin, pawn_location)
        record["pawn_distance_to_bounds_sphere_cm"] = max(0.0, delta - float(bounds.sphere_radius))
    return record


def light_records(actors):
    records = []
    for actor in actors:
        class_name = actor.get_class().get_name()
        if "DirectionalLight" not in class_name:
            continue
        components = list(actor.get_components_by_class(unreal.DirectionalLightComponent))
        component = components[0] if components else None
        records.append({
            "actor": actor.get_path_name(),
            "label": actor.get_actor_label(),
            "class": class_name,
            "hidden": safe_prop(actor, "hidden"),
            "forward": vec(actor.get_actor_forward_vector()),
            "rotation": [float(actor.get_actor_rotation().pitch), float(actor.get_actor_rotation().yaw), float(actor.get_actor_rotation().roll)],
            "component": component.get_path_name() if component else None,
            "visible": safe_prop(component, "visible") if component else None,
            "intensity": safe_prop(component, "intensity") if component else None,
            "atmosphere_sun_light": safe_prop(component, "atmosphere_sun_light") if component else None,
            "atmosphere_sun_light_index": safe_prop(component, "atmosphere_sun_light_index") if component else None,
            "cast_shadows": safe_prop(component, "cast_shadows") if component else None,
        })
    return records


class R28:
    def __init__(self):
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.phase = "PREPARE"
        self.phase_started = time.monotonic()
        self.handle = None
        self.world = None
        self.spawner = None
        self.pawn = None
        self.planet = None
        self.report = {
            "schema": "redmmo.ppg.r27_grass_surface_sky.audit.r28.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "evidence_class": "automation",
        }

    def set_phase(self, phase):
        self.phase = phase
        self.phase_started = time.monotonic()
        self.report["phase"] = phase
        unreal.log("REDMMO_R28_PHASE " + phase)

    def authenticate(self):
        active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(active == PROJECT.resolve(strict=True), "wrong project")
        require(not RESULT.exists(), "R28 output exists")
        require(sha256(PROJECT) == PROJECT_SHA, "project descriptor drift")
        require(sha256(HOME_FILE) == HOME_SHA, "home map drift")
        require(sha256(PROFILE_FILE) == PROFILE_SHA, "ProfileV1 drift")
        require(sha256(R27_RESULT) == R27_SHA, "R27 result drift")
        for path, expected in APPROVED_FILES.items():
            require(path.is_file() and sha256(path) == expected, "grass asset drift: " + str(path))
        for path, expected in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected, "protected package drift: " + str(path))
        require(dirty_packages() == {"content": [], "maps": []}, "editor started dirty")
        require(not self.level.is_in_play_in_editor(), "PIE already active")
        command = str(unreal.SystemLibrary.get_command_line()).lower()
        require("-d3d12" in command and "-renderoffscreen" in command and "-nullrhi" not in command, "renderer gate failed")
        require(all(provider_gate().values()), "provider listener active")
        world = unreal.EditorLevelLibrary.get_editor_world()
        require(world is not None, "editor world missing")
        world_path = world.get_path_name().split(":", 1)[0].split(".", 1)[0]
        require(world_path == HOME_MAP, "wrong map: " + world_path)
        self.report["provider_gate_before"] = provider_gate()
        self.level.editor_request_begin_play()
        self.set_phase("WAIT_PIE")

    def bind_pie(self):
        world = self.editor.get_game_world()
        if world is None or not self.level.is_in_play_in_editor():
            return False
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        if pawn is None:
            return False
        actors = list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor))
        spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        require(len(spawners) == 1, "expected one PPG spawner")
        self.world = world
        self.pawn = pawn
        self.spawner = spawners[0]
        self.planet = self.spawner.get_editor_property("planet_data")
        require(asset_path(self.planet) == PLANET_DATA, "ProfileV1 binding drift")
        require(int(self.planet.get_editor_property("generation_seed")) == 1337, "seed drift")
        self.report["foliage_profile"] = foliage_profile_record(self.planet)
        self.report["approved_mesh_assets"] = [
            mesh_record(unreal.load_asset(path)) for path in sorted(APPROVED_GRASS)
        ]
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
        pawn_location = self.pawn.get_actor_location()
        get_actor = getattr(self.spawner, "get_foliage_actor", None)
        require(callable(get_actor), "foliage actor API unavailable")
        foliage_actor = get_actor()
        require(foliage_actor is not None, "foliage actor missing")
        approved = []
        total = 0
        for component in list(foliage_actor.get_components_by_class(unreal.StaticMeshComponent)):
            total += 1
            if asset_path(safe_prop(component, "static_mesh")) in APPROVED_GRASS:
                approved.append(component_record(component, pawn_location))
        require(approved, "no approved grass runtime components")
        approved.sort(key=lambda item: item["distance_to_pawn_cm"])
        nearest = approved[:24]
        within_100m = sum(1 for item in approved if item["distance_to_pawn_cm"] <= 10000.0)
        within_500m = sum(1 for item in approved if item["distance_to_pawn_cm"] <= 50000.0)
        bounds_near = sum(
            1 for item in approved
            if item.get("pawn_distance_to_bounds_sphere_cm") is not None
            and item["pawn_distance_to_bounds_sphere_cm"] <= 500.0
        )
        actors = list(unreal.GameplayStatics.get_all_actors_of_class(self.world, unreal.Actor))
        presenters = [actor for actor in actors if actor.get_class().get_name() == "RedPlanetNightPresenter"]
        require(len(presenters) == 1, "expected one night presenter")
        presenter = presenters[0]
        star_components = [
            component for component in presenter.get_components_by_class(unreal.StaticMeshComponent)
            if "StarDome" in component.get_name()
        ]
        require(len(star_components) == 1, "expected one star dome")
        star = star_components[0]
        lights = light_records(actors)
        atmosphere_suns = [item for item in lights if item.get("atmosphere_sun_light")]
        solar_dot = None
        if len(atmosphere_suns) == 1:
            forward = unreal.Vector(*atmosphere_suns[0]["forward"])
            sun_direction = unreal.Vector(-forward.x, -forward.y, -forward.z)
            radial = normalized(pawn_location - self.spawner.get_actor_location())
            solar_dot = dot(radial, normalized(sun_direction))
        sky_actors = [
            {
                "actor": actor.get_path_name(),
                "label": actor.get_actor_label(),
                "class": actor.get_class().get_name(),
                "hidden": safe_prop(actor, "hidden"),
            }
            for actor in actors
            if "SkyAtmosphere" in actor.get_class().get_name() or "SkyLight" in actor.get_class().get_name()
        ]
        self.report.update({
            "pawn": {
                "class": self.pawn.get_class().get_path_name(),
                "location": vec(pawn_location),
                "radial_elevation_above_sea_cm": distance(pawn_location, self.spawner.get_actor_location()) - float(self.planet.get_editor_property("planet_radius")),
            },
            "runtime_grass": {
                "foliage_static_mesh_component_count": total,
                "approved_component_count": len(approved),
                "approved_component_origins_within_100m": within_100m,
                "approved_component_origins_within_500m": within_500m,
                "approved_component_bounds_within_5m_of_pawn": bounds_near,
                "nearest_components": nearest,
            },
            "surface_sky": {
                "presenter": presenter.get_path_name(),
                "last_frame_resolved": safe_prop(presenter, "last_frame_resolved"),
                "last_altitude_cm": safe_prop(presenter, "last_altitude_cm"),
                "last_night_hemisphere_weight": safe_prop(presenter, "last_night_hemisphere_weight"),
                "last_star_visibility_weight": safe_prop(presenter, "last_star_visibility_weight"),
                "last_night_fill_weight": safe_prop(presenter, "last_night_fill_weight"),
                "solar_dot_recomputed": solar_dot,
                "star_dome": {
                    "visible": safe_prop(star, "visible"),
                    "hidden_in_game": safe_prop(star, "hidden_in_game"),
                    "world_scale": vec(star.get_world_transform().scale3d),
                    "material": material_record(star.get_material(0)),
                },
                "directional_lights": lights,
                "sky_actors": sky_actors,
            },
        })
        self.level.editor_request_end_play()
        self.set_phase("WAIT_STOP")

    def finish(self):
        require(not self.level.is_in_play_in_editor(), "PIE did not stop")
        require(dirty_packages() == {"content": [], "maps": []}, "PIE dirtied packages")
        require(sha256(HOME_FILE) == HOME_SHA, "home map changed")
        require(sha256(PROFILE_FILE) == PROFILE_SHA, "ProfileV1 changed")
        for path, expected in APPROVED_FILES.items():
            require(sha256(path) == expected, "grass asset changed: " + str(path))
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "protected package changed: " + str(path))
        self.report.update({
            "status": "PASS_R28_NO_SAVE_GRASS_SURFACE_SKY_DIAGNOSTIC",
            "map_sha256_after": sha256(HOME_FILE),
            "profile_sha256_after": sha256(PROFILE_FILE),
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "save_called": False,
            "completed_utc": now(),
            "claim_limit": "Read-only runtime diagnostic only; no visual correction or acceptance is claimed.",
        })
        atomic_json(RESULT, self.report)
        unreal.log("REDMMO_R28_PASS")
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
                require(elapsed <= 20.0, "PIE startup timeout")
                self.bind_pie()
            elif self.phase == "WAIT_GENERATION":
                require(elapsed <= 240.0, "generation timeout")
                if self.generation_ready():
                    self.set_phase("SETTLE")
            elif self.phase == "SETTLE":
                require(elapsed <= 30.0, "settle timeout")
                if elapsed >= 8.0:
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
    _R28 = R28()
    _R28.start()
except Exception as bootstrap_error:
    DIAG.mkdir(parents=True, exist_ok=True)
    atomic_json(RESULT, {
        "schema": "redmmo.ppg.r27_grass_surface_sky.audit.r28.v1",
        "status": "FAIL",
        "error": str(bootstrap_error),
        "traceback": traceback.format_exc(),
        "completed_utc": now(),
    })
    unreal.SystemLibrary.quit_editor()
