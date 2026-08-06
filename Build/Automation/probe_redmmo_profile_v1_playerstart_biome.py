"""No-save live PPG biome/vertex-color sample at the persisted PlayerStart.

The probe waits for the startup home planet to finish generating, resolves the
finest ready chunk that geometrically contains PlayerStart, reads the chunk's
GPU BiomeMap at the corresponding terrain-grid coordinate, and attempts the
matching retained terrain vertex-color sample.  It never calls save, rebuild,
regenerate, PIE, or any provider.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import socket
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
PROJECT_FILE = PROJECT / "RedMMO.uproject"
HOME_MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
HOME_FILE = PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
EXPECTED_HOME = "83C78D0ACB599F01E8D3834FB62D58D6B6AA75466F6549F03BFEC4DF908E3336"
EXPECTED_PLANET = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
RESULT = Path(os.environ["REDMMO_PROFILE_V1_PLAYERSTART_BIOME_RESULT"])
PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def asset_path(value):
    if value is None:
        return None
    path = str(value.get_path_name()).split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def dirty_packages():
    content = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    maps = list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return {
        "content": sorted({asset_path(value) for value in content}),
        "maps": sorted({asset_path(value) for value in maps}),
    }


def provider_gate():
    result = {}
    for port in (5353, 8000, 8765, 11111):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            result[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    require(all(result.values()), "Provider/MCP listener unexpectedly active")
    return result


def atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=False)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True, default=str)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def vec(value):
    return [float(value.x), float(value.y), float(value.z)]


def prop(value, name, default=None):
    try:
        return value.get_editor_property(name)
    except Exception:
        return default


def struct_value(record, names):
    wanted = {str(name).replace("_", "").lower() for name in names}
    for key, value in record.to_dict().items():
        if str(key).replace("_", "").lower() in wanted:
            return value
    return None


def biome_names(planet):
    result = []
    for index, biome in enumerate(list(planet.get_editor_property("biome_data"))):
        result.append({
            "index": index,
            "name": str(struct_value(biome, ("name", "biome_name"))),
            "foliage": asset_path(struct_value(biome, ("foliage_data", "forest_foliage_data"))),
        })
    return result


def face_coordinates(planet_local, radius):
    """CPU equivalent of PPGDFInverseCubeSphereFaceCoordinates."""
    direction_len = math.sqrt(sum(value * value for value in planet_local))
    require(direction_len > 0.0, "PlayerStart is at planet center")
    direction = [value / direction_len for value in planet_local]
    axis = max(range(3), key=lambda index: abs(direction[index]))
    half_original = radius / math.sqrt(2.0)

    def inverse(non_dominant, dominant_abs):
        deformed_ratio = (non_dominant / dominant_abs) * 0.6681786199650447
        return math.atan(deformed_ratio) * 1.6976527287503789 * half_original

    x, y, z = planet_local
    if axis == 0 and direction[0] >= 0.0:
        return (1, 0, 0), inverse(-z, x), inverse(y, x)
    if axis == 0:
        return (-1, 0, 0), inverse(z, -x), inverse(y, -x)
    if axis == 1 and direction[1] >= 0.0:
        return (0, 1, 0), inverse(x, y), inverse(-z, y)
    if axis == 1:
        return (0, -1, 0), inverse(x, -y), inverse(z, -y)
    if direction[2] >= 0.0:
        return (0, 0, 1), inverse(x, z), inverse(y, z)
    return (0, 0, -1), inverse(-x, -z), inverse(y, -z)


def origin_coordinates(location, rotation):
    x, y, z = location
    if rotation == (0, -1, 0):
        return x, z
    if rotation == (0, 1, 0):
        return x, -z
    if rotation == (-1, 0, 0):
        return z, y
    if rotation == (0, 0, 1):
        return x, y
    if rotation == (0, 0, -1):
        return -x, y
    if rotation == (1, 0, 0):
        return -z, y
    raise RuntimeError("Unknown PPG face rotation: " + repr(rotation))


def color_record(value):
    return [float(value.r), float(value.g), float(value.b), float(value.a)]


def loaded_chunk_objects():
    chunk_type = getattr(unreal, "ChunkObject", None)
    require(chunk_type is not None, "PPG ChunkObject Python type missing")
    return list(unreal.ObjectIterator(chunk_type))


def sample_component(world, component, player_face, player_u, player_v):
    material = component.get_material(0)
    if material is None or material.get_class().get_name() != "MaterialInstanceDynamic":
        return None
    biome_map = material.get_texture_parameter_value("BiomeMap")
    if biome_map is None or biome_map.get_class().get_name() != "TextureRenderTarget2D":
        return None
    rotation_value = material.get_vector_parameter_value("PlanetSpaceRotation")
    rotation = (int(round(rotation_value.r)), int(round(rotation_value.g)), int(round(rotation_value.b)))
    if rotation != player_face:
        return None
    location_high = material.get_vector_parameter_value("ChunkLocationHigh")
    location_low = material.get_vector_parameter_value("ChunkLocationLow")
    location = (
        float(location_high.r + location_low.r),
        float(location_high.g + location_low.g),
        float(location_high.b + location_low.b),
    )
    origin_u, origin_v = origin_coordinates(location, rotation)
    size = float(material.get_scalar_parameter_value("ChunkSizeHigh")) + float(
        material.get_scalar_parameter_value("ChunkSizeLow"))
    if not (origin_u - 0.01 <= player_u <= origin_u + size + 0.01 and
            origin_v - 0.01 <= player_v <= origin_v + size + 0.01):
        return None
    vertices = int(biome_map.get_editor_property("size_x"))
    require(vertices > 1, "Invalid live BiomeMap width")
    quality = vertices - 1
    vertices = quality + 1
    grid_x = max(0.0, min(float(quality), (player_u - origin_u) / size * quality))
    grid_y = max(0.0, min(float(quality), (player_v - origin_v) / size * quality))
    pixel_x = int(round(grid_x))
    pixel_y = int(round(grid_y))
    index_pixel = unreal.RenderingLibrary.read_render_target_raw_pixel(
        world, biome_map, pixel_x, pixel_y, False)
    strength_pixel = unreal.RenderingLibrary.read_render_target_raw_pixel(
        world, biome_map, pixel_x, pixel_y + vertices, False)

    return {
        "component": component.get_path_name(),
        "material_instance": material.get_path_name(),
        "rotation": list(rotation),
        "planet_space_location": list(location),
        "origin_uv": [origin_u, origin_v],
        "chunk_size": size,
        "chunk_quality": quality,
        "recursion_level": int(round(material.get_scalar_parameter_value("recursionLevel"))),
        "grid_coordinate": [grid_x, grid_y],
        "sample_pixel": [pixel_x, pixel_y],
        "biome_map": biome_map.get_path_name(),
        "raw_index_pixel": color_record(index_pixel),
        "top3_biome_indices": [
            int(round(index_pixel.r * 255.0)),
            int(round(index_pixel.g * 255.0)),
            int(round(index_pixel.b * 255.0)),
        ],
        "top3_biome_strengths": [float(strength_pixel.r), float(strength_pixel.g), float(strength_pixel.b)],
        "terrain_vertex_color_rgba8": None,
        "terrain_vertex_color_read_error": (
            "Installed PPG 1.0 retains generated VertexColors as a private UChunkObject property; "
            "Unreal Python cannot read it without changing plugin code."
        ),
    }


class Probe:
    def __init__(self):
        self.started = time.monotonic()
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.pie_requested = False
        self.handle = unreal.register_slate_post_tick_callback(self.tick)
        self.finished = False
        self.report = {
            "schema": "redmmo.profile_v1.playerstart_biome_sample.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "evidence_class": "fresh_editor_live_generated_chunk_read_only",
        }

    def finish(self, status, **values):
        if self.finished:
            return
        self.finished = True
        self.report.update(values)
        self.report.update({"status": status, "completed_utc": now()})
        atomic_json(RESULT, self.report)
        unreal.log("REDMMO_PROFILE_V1_PLAYERSTART_BIOME " + status)
        try:
            unreal.unregister_slate_post_tick_callback(self.handle)
        except Exception:
            pass
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        unreal.SystemLibrary.quit_editor()

    def tick(self, _delta):
        try:
            if time.monotonic() - self.started > 240.0:
                raise RuntimeError("Timed out waiting for PPG generation")
            active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
            require(active == PROJECT.resolve(), "Wrong active project: " + str(active))

            if not self.pie_requested:
                editor_world = self.editor.get_editor_world()
                if editor_world is None:
                    return
                world_path = editor_world.get_path_name().split(":", 1)[0].split(".", 1)[0]
                require(world_path == HOME_MAP, "Wrong startup map: " + world_path)
                clean_state = dirty_packages()
                require(clean_state == {"content": [], "maps": []}, "Editor started dirty")
                self.report["dirty_packages_before_pie"] = clean_state
                self.report["provider_ports_closed_before_pie"] = provider_gate()
                require(not self.level.is_in_play_in_editor(), "PIE unexpectedly active")
                self.level.editor_request_begin_play()
                self.pie_requested = True
                return
            world = self.editor.get_game_world()
            if world is None or not self.level.is_in_play_in_editor():
                return

            actors = list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor))
            spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
            starts = [actor for actor in actors if actor.get_class().get_name() == "PlayerStart"]
            require(len(spawners) == 1 and len(starts) == 1, "Expected one spawner and one PlayerStart")
            spawner = spawners[0]
            status = spawner.get_planet_generation_status()
            phase = str(status.get_editor_property("phase"))
            progress = float(status.get_editor_property("progress"))
            generating = bool(status.get_editor_property("is_generating"))
            complete = "COMPLETE" in phase.upper() and progress >= 0.999 and not generating
            # PPG may immediately begin a second adaptive chunk pass after its
            # initial completion.  Give both passes a bounded settle window,
            # then sample only if the public status reports complete.
            if time.monotonic() - self.started < 12.0:
                return
            require(complete, f"PPG did not settle: phase={phase} progress={progress} generating={generating}")
            if not complete:
                return

            planet = spawner.get_editor_property("planet_data")
            require(asset_path(planet) == EXPECTED_PLANET, "Unexpected PlanetData binding")
            radius = float(planet.get_editor_property("planet_radius"))
            center = spawner.get_actor_location()
            start = starts[0].get_actor_location()
            local = [float(start.x - center.x), float(start.y - center.y), float(start.z - center.z)]
            player_face, player_u, player_v = face_coordinates(local, radius)

            components = list(spawner.get_components_by_class(unreal.StaticMeshComponent))
            active_components = []
            candidates = []
            property_errors = []
            for component in components:
                try:
                    record = sample_component(world, component, player_face, player_u, player_v)
                    if record is not None:
                        active_components.append(component)
                        candidates.append(record)
                except Exception as error:
                    property_errors.append({"component": component.get_path_name(), "error": str(error)})
            require(candidates, "No ready generated chunk contains PlayerStart: " + repr(property_errors[:5]))
            candidates.sort(key=lambda item: (item["chunk_size"], -item["recursion_level"]))
            sample = candidates[0]
            biomes = biome_names(planet)
            by_index = {item["index"]: item for item in biomes}
            sample["top3_biomes"] = [
                {
                    **by_index.get(index, {"index": index, "name": "UNKNOWN", "foliage": None}),
                    "strength": sample["top3_biome_strengths"][slot],
                }
                for slot, index in enumerate(sample["top3_biome_indices"])
            ]
            dominant = sample["top3_biomes"][0]
            require(sha256(HOME_FILE) == EXPECTED_HOME, "Probe changed home-map bytes")
            for path, expected in PROTECTED.items():
                require(path.is_file() and sha256(path) == expected, "Protected hash drift: " + str(path))
            self.finish(
                "PASS_PLAYERSTART_BIOME_SAMPLED_NO_SAVE",
                provider_ports_closed=provider_gate(),
                map=HOME_MAP,
                map_sha256_before_after=EXPECTED_HOME,
                playerstart={"path": starts[0].get_path_name(), "world_location": vec(start)},
                planet={"center": vec(center), "radius": radius, "biomes": biomes},
                player_face=list(player_face),
                player_face_uv=[player_u, player_v],
                static_mesh_component_count=len(components),
                containing_generated_component_count=len(active_components),
                containing_chunk_count=len(candidates),
                generation={"phase": phase, "progress": progress, "is_generating": generating},
                sample=sample,
                dominant_biome_has_foliage=bool(dominant.get("foliage")),
                no_save=True,
                no_regeneration=True,
                pie_used_for_live_runtime_chunk=True,
                pie_world_saved=False,
                dirty_packages_after_pie_not_queried=True,
                protected_hashes_after={str(path): sha256(path) for path in PROTECTED},
                next_safe_action=(
                    "If the dominant biome has null foliage, prepare one rollback-guarded ProfileV1 biome-to-foliage "
                    "assignment repair. Otherwise use the sampled vertex color to test BLUE-inverted density eligibility."
                ),
            )
        except Exception as error:
            self.finish("FAIL", error=str(error), traceback=traceback.format_exc(), no_save=True)


require(not RESULT.exists() and not RESULT.parent.exists(), "Result no-clobber failed")
require(HOME_FILE.is_file() and sha256(HOME_FILE) == EXPECTED_HOME, "Home-map preimage hash drift")
for protected_path, protected_hash in PROTECTED.items():
    require(protected_path.is_file() and sha256(protected_path) == protected_hash, "Protected preimage drift")
PROBE = Probe()
