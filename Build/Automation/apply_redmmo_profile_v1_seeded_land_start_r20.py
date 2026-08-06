"""Select and persist one seeded, above-sea, collision-fitted PPG land start.

The transaction uses the already generated ProfileV1 chunk set.  It does not
change the seed, PlanetData, generation graph, water, biome masks, or foliage
bindings.  Candidate points must come from the sole PPG spawner's query-
collision terrain, sit above native sea datum, and resolve to a biome whose
existing PlanetData entry already owns foliage.  Only PlayerStart is modified;
its attached label follows through the existing attachment relationship.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import socket
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject")
MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
MAP_FILE = PROJECT.parent / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
EXPECTED_MAP_SHA = "6B45B423ED59BD8906A05CF35E7349C70282154DE2CE4723D41E0C16380F88D9"
EXPECTED_PROFILE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
EXPECTED_START = (-198911217.22968367, 16591254.847640004, -523634710.60749865)
PROFILE_FILE = PROJECT.parent / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
EXPECTED_PROFILE_SHA = "5C50D50A8955C1E5F4270BDD4E53D1214C941725157B76422CD72B748978B837"
ROLLBACK = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeRedPPGProfileV1LandStart_R20D_20260805T1050Z")
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1LandStart_R20D_20260805T1050Z")
RESULT = DIAG / "result.json"
MIN_ELEVATION_CM = 25000.0
START_CLEARANCE_CM = 250.0
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


def write_json_exclusive(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def asset_path(value):
    if value is None:
        return None
    path = str(value.get_path_name()).split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def provider_gate():
    result = {}
    for port in (11111, 5353, 8000, 8765):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            result[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    require(all(result.values()), "Provider/MCP listener unexpectedly active: " + repr(result))
    return result


def dirty_packages():
    return {
        "content": sorted({asset_path(value) for value in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}),
        "maps": sorted({asset_path(value) for value in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()}),
    }


def vec(value):
    return [float(value.x), float(value.y), float(value.z)]


def add(a, b):
    return unreal.Vector(a.x + b.x, a.y + b.y, a.z + b.z)


def sub(a, b):
    return unreal.Vector(a.x - b.x, a.y - b.y, a.z - b.z)


def mul(value, scalar):
    return unreal.Vector(value.x * scalar, value.y * scalar, value.z * scalar)


def dot(a, b):
    return float(a.x * b.x + a.y * b.y + a.z * b.z)


def length(value):
    return math.sqrt(dot(value, value))


def normalized(value):
    magnitude = length(value)
    require(magnitude > 1.0e-6, "Cannot normalize zero vector")
    return mul(value, 1.0 / magnitude)


def close_vec(actual, expected, tolerance=0.5):
    return all(abs(float(actual[index]) - float(expected[index])) <= tolerance for index in range(3))


def struct_value(record, names):
    wanted = {str(name).replace("_", "").lower() for name in names}
    for key, value in record.to_dict().items():
        if str(key).replace("_", "").lower() in wanted:
            return value
    return None


def biome_records(planet):
    records = []
    for index, biome in enumerate(list(planet.get_editor_property("biome_data"))):
        records.append({
            "index": index,
            "name": str(struct_value(biome, ("name", "biome_name"))),
            "foliage": asset_path(struct_value(biome, ("foliage_data", "forest_foliage_data"))),
        })
    return records


def face_coordinates(planet_local, radius):
    direction_len = math.sqrt(sum(value * value for value in planet_local))
    require(direction_len > 0.0, "Candidate is at planet center")
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


def sample_component(world, component, point, center, radius):
    material = component.get_material(0)
    if material is None or material.get_class().get_name() != "MaterialInstanceDynamic":
        return None
    biome_map = material.get_texture_parameter_value("BiomeMap")
    if biome_map is None or biome_map.get_class().get_name() != "TextureRenderTarget2D":
        return None
    rotation_value = material.get_vector_parameter_value("PlanetSpaceRotation")
    rotation = (int(round(rotation_value.r)), int(round(rotation_value.g)), int(round(rotation_value.b)))
    local = vec(sub(point, center))
    player_face, player_u, player_v = face_coordinates(local, radius)
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
    width = int(biome_map.get_editor_property("size_x"))
    require(width > 1, "Invalid live BiomeMap width")
    quality = width - 1
    grid_x = max(0.0, min(float(quality), (player_u - origin_u) / size * quality))
    grid_y = max(0.0, min(float(quality), (player_v - origin_v) / size * quality))
    pixel_x = int(round(grid_x))
    pixel_y = int(round(grid_y))
    index_pixel = unreal.RenderingLibrary.read_render_target_raw_pixel(
        world, biome_map, pixel_x, pixel_y, False)
    strength_pixel = unreal.RenderingLibrary.read_render_target_raw_pixel(
        world, biome_map, pixel_x, pixel_y + width, False)
    return {
        "component": component.get_path_name(),
        "chunk_size": size,
        "recursion_level": int(round(material.get_scalar_parameter_value("recursionLevel"))),
        "sample_pixel": [pixel_x, pixel_y],
        "raw_index_pixel": color_record(index_pixel),
        "top3_biome_indices": [
            int(round(index_pixel.r * 255.0)),
            int(round(index_pixel.g * 255.0)),
            int(round(index_pixel.b * 255.0)),
        ],
        "top3_biome_strengths": [float(strength_pixel.r), float(strength_pixel.g), float(strength_pixel.b)],
    }


def sample_biome(world, components, point, center, radius, biomes):
    samples = []
    for component in components:
        try:
            sample = sample_component(world, component, point, center, radius)
            if sample is not None:
                samples.append(sample)
        except Exception:
            continue
    require(samples, "No generated BiomeMap contains collision candidate")
    samples.sort(key=lambda item: (item["chunk_size"], -item["recursion_level"]))
    sample = samples[0]
    by_index = {item["index"]: item for item in biomes}
    sample["top3_biomes"] = [
        {
            **by_index.get(index, {"index": index, "name": "UNKNOWN", "foliage": None}),
            "strength": sample["top3_biome_strengths"][slot],
        }
        for slot, index in enumerate(sample["top3_biome_indices"])
    ]
    return sample


def hit_value(hit, names, default=None):
    for name in names:
        try:
            return hit.get_editor_property(name)
        except Exception:
            continue
    return default


def trace_direction(world, spawner, terrain_paths, center, radius, direction, ignored):
    start = add(center, mul(direction, radius + 2000000.0))
    end = add(center, mul(direction, radius - 2000000.0))
    attempts = []
    for profile in ("Pawn", "BlockAll"):
        hit = unreal.SystemLibrary.line_trace_single_by_profile(
            world, start, end, unreal.Name(profile), True, ignored,
            unreal.DrawDebugTrace.NONE, True,
            unreal.LinearColor(1.0, 0.0, 0.0, 1.0),
            unreal.LinearColor(0.0, 1.0, 0.0, 1.0), 0.0)
        if hit is None:
            attempts.append({"profile": profile, "blocking_hit": False})
            continue
        actor = hit_value(hit, ("hit_actor", "actor"))
        component = hit_value(hit, ("hit_component", "component"))
        point = hit_value(hit, ("impact_point", "location"))
        normal = hit_value(hit, ("impact_normal", "normal"))
        blocking = bool(hit_value(hit, ("blocking_hit", "bBlockingHit"), False))
        accepted = bool(
            blocking and actor == spawner and component is not None
            and component.get_path_name() in terrain_paths and point is not None and normal is not None)
        record = {
            "profile": profile,
            "blocking_hit": blocking,
            "accepted": accepted,
            "actor": actor.get_path_name() if actor else None,
            "component": component.get_path_name() if component else None,
        }
        attempts.append(record)
        if accepted:
            return {
                "method": "line_trace_profile_" + profile,
                "component": component.get_path_name(),
                "point": point,
                "normal": normal,
                "attempts": attempts,
            }
    return None


def actor_snapshot(actor):
    location = actor.get_actor_location()
    rotation = actor.get_actor_rotation()
    scale = actor.get_actor_scale3d()
    parent = actor.get_attach_parent_actor()
    root = actor.get_editor_property("root_component")
    relative_location = root.get_editor_property("relative_location") if root else location
    relative_rotation = root.get_editor_property("relative_rotation") if root else rotation
    relative_scale = root.get_editor_property("relative_scale3d") if root else scale
    return {
        "path": actor.get_path_name(),
        "class": actor.get_class().get_name(),
        "location": vec(location),
        "rotation": [float(rotation.pitch), float(rotation.yaw), float(rotation.roll)],
        "scale": vec(scale),
        "attach_parent": parent.get_path_name() if parent else None,
        "relative_location": vec(relative_location),
        "relative_rotation": [float(relative_rotation.pitch), float(relative_rotation.yaw), float(relative_rotation.roll)],
        "relative_scale": vec(relative_scale),
    }


class Transaction:
    def __init__(self):
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.phase = "prepare"
        self.phase_started = time.monotonic()
        self.frames = 0
        self.ready_frames = 0
        self.handle = None
        self.world = None
        self.spawner = None
        self.planet = None
        self.center = None
        self.radius = None
        self.candidate = None
        self.report = {
            "schema": "redmmo.ppg_profile_v1.seeded_land_start.r20.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "evidence_class": "automation",
            "map": MAP,
            "map_sha256_before": EXPECTED_MAP_SHA,
            "profile_sha256_before": EXPECTED_PROFILE_SHA,
            "seed_changed": False,
            "generation_called": False,
        }

    def set_phase(self, phase):
        self.phase = phase
        self.phase_started = time.monotonic()
        self.frames = 0
        unreal.log("REDMMO_R20_LAND_START_PHASE " + phase)

    def start(self):
        # Unreal creates the parent of -AbsLog before this script executes.
        # The result artifact itself is the durable no-clobber transaction gate.
        require(not RESULT.exists(), "R20 result no-clobber failed")
        require(not ROLLBACK.exists(), "R20 rollback no-clobber failed")
        require(sha256(MAP_FILE) == EXPECTED_MAP_SHA, "Home map hash drift")
        require(sha256(PROFILE_FILE) == EXPECTED_PROFILE_SHA, "ProfileV1 hash drift")
        require(dirty_packages() == {"content": [], "maps": []}, "Editor started dirty")
        self.report["provider_gate_before"] = provider_gate()
        for path, expected in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected, "Protected hash drift: " + str(path))
        ROLLBACK.mkdir(parents=True, exist_ok=False)
        rollback_map = ROLLBACK / "RedMMO_PPG_HomeWorld.pre_r20_land_start.umap"
        shutil.copy2(MAP_FILE, rollback_map)
        require(sha256(rollback_map) == EXPECTED_MAP_SHA, "Rollback byte mismatch")
        write_json_exclusive(ROLLBACK / "manifest.json", {
            "schema": "redmmo.ppg_profile_v1.seeded_land_start.rollback.v1",
            "captured_utc": now(),
            "source": str(MAP_FILE),
            "source_sha256": EXPECTED_MAP_SHA,
            "rollback": str(rollback_map),
            "restore": "Close Unreal and copy this retained umap over only the clean RedMMO home map.",
        })
        self.report["rollback"] = str(rollback_map)
        self.set_phase("loading_map")
        require(self.level.load_level(MAP), "Unable to load exact home map")
        require(dirty_packages() == {"content": [], "maps": []}, "Map load dirtied packages")
        self.level.editor_request_begin_play()
        self.set_phase("wait_pie")

    def bind_pie(self):
        world = self.editor.get_game_world()
        if world is None or not self.level.is_in_play_in_editor():
            return False
        actors = list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor))
        spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        require(len(spawners) == 1, "Expected exactly one PPG spawner")
        self.world = world
        self.spawner = spawners[0]
        self.planet = self.spawner.get_editor_property("planet_data")
        require(asset_path(self.planet) == EXPECTED_PROFILE, "Unexpected PlanetData binding")
        self.center = self.spawner.get_actor_location()
        self.radius = float(self.planet.get_editor_property("planet_radius"))
        self.report["planet"] = {
            "center": vec(self.center),
            "radius_cm": self.radius,
            "seed": int(self.planet.get_editor_property("generation_seed")),
            "biomes": biome_records(self.planet),
        }
        require(self.report["planet"]["seed"] == 1337, "PPG seed drift")
        self.set_phase("wait_generation")
        return True

    def generation_ready(self):
        status = self.spawner.get_planet_generation_status()
        phase = str(status.get_editor_property("phase"))
        progress = float(status.get_editor_property("progress"))
        generating = bool(status.get_editor_property("is_generating"))
        self.report["generation"] = {"phase": phase, "progress": progress, "is_generating": generating}
        return "COMPLETE" in phase.upper() and progress >= 0.999 and not generating

    def select_candidate(self):
        components = list(self.spawner.get_components_by_class(unreal.StaticMeshComponent))
        terrain = [
            component for component in components
            if component.is_query_collision_enabled()
            and component.get_editor_property("static_mesh") is not None
            and not isinstance(component, unreal.InstancedStaticMeshComponent)
        ]
        require(terrain, "No query-collision PPG terrain components")
        terrain_paths = {component.get_path_name() for component in terrain}
        actors = list(unreal.GameplayStatics.get_all_actors_of_class(self.world, unreal.Actor))
        ignored = [actor for actor in actors if actor != self.spawner]
        directions = {}
        for component in terrain:
            location = component.get_world_location()
            delta = sub(location, self.center)
            if length(delta) < self.radius * 0.5:
                continue
            direction = normalized(delta)
            key = tuple(int(round(value * 10000.0)) for value in vec(direction))
            directions.setdefault(key, direction)
        require(directions, "Generated terrain component transforms expose no shell directions")

        collision_candidates = []
        for direction in directions.values():
            hit = trace_direction(
                self.world, self.spawner, terrain_paths, self.center, self.radius, direction, ignored)
            if hit is None:
                continue
            point = hit["point"]
            normal = normalized(hit["normal"])
            radial = normalized(sub(point, self.center))
            elevation = length(sub(point, self.center)) - self.radius
            normal_dot = dot(normal, radial)
            if elevation < MIN_ELEVATION_CM or normal_dot < 0.92:
                continue
            collision_candidates.append({
                "method": hit["method"],
                "component": hit["component"],
                "point": vec(point),
                "normal": vec(normal),
                "radial": vec(radial),
                "elevation_cm": elevation,
                "surface_normal_radial_dot": normal_dot,
                "trace_attempts": hit["attempts"],
            })
        collision_candidates.sort(key=lambda item: (-item["surface_normal_radial_dot"], item["elevation_cm"]))
        require(collision_candidates, "No above-sea collision candidate in completed generated chunk set")

        biomes = self.report["planet"]["biomes"]
        evaluated = []
        for item in collision_candidates[:96]:
            point = unreal.Vector(*item["point"])
            try:
                sample = sample_biome(
                    self.world, components, point, self.center, self.radius, biomes)
            except Exception as error:
                item["biome_sample_error"] = str(error)
                evaluated.append(item)
                continue
            item["biome_sample"] = sample
            dominant = sample["top3_biomes"][0]
            item["dominant_biome"] = dominant
            item["foliage_eligible"] = bool(dominant.get("foliage")) and float(dominant["strength"]) >= 0.90
            evaluated.append(item)
        viable = [item for item in evaluated if item.get("foliage_eligible")]
        require(viable, "Above-sea collision candidates exist but none resolves to a >=90% foliage-enabled biome")
        biome_rank = {"Hills": 0, "Craters": 1, "Mountains": 2}
        viable.sort(key=lambda item: (
            biome_rank.get(item["dominant_biome"]["name"], 9),
            -item["surface_normal_radial_dot"],
            abs(item["elevation_cm"] - 100000.0),
        ))
        chosen = viable[0]
        chosen_point = unreal.Vector(*chosen["point"])
        radial = normalized(sub(chosen_point, self.center))
        chosen["persisted_playerstart_target"] = vec(add(chosen_point, mul(radial, START_CLEARANCE_CM)))
        self.candidate = chosen
        self.report.update({
            "query_collision_component_count": len(terrain),
            "unique_generated_direction_count": len(directions),
            "above_sea_collision_candidate_count": len(collision_candidates),
            "evaluated_candidate_count": len(evaluated),
            "foliage_eligible_candidate_count": len(viable),
            "candidate_preview": evaluated[:12],
            "selected_candidate": chosen,
        })
        self.level.editor_request_end_play()
        self.set_phase("wait_pie_stop")

    def persist(self):
        world = self.editor.get_editor_world()
        require(world is not None, "Editor world unavailable after PIE")
        current = world.get_path_name().split(":", 1)[0].split(".", 1)[0]
        require(current == MAP, "Wrong editor map after PIE: " + current)
        require(dirty_packages() == {"content": [], "maps": []}, "Editor dirty before PlayerStart persist")
        actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
        starts = [actor for actor in actors if actor.get_class().get_name() == "PlayerStart"]
        require(len(starts) == 1, "Expected exactly one editor PlayerStart")
        start = starts[0]
        before = vec(start.get_actor_location())
        require(close_vec(before, EXPECTED_START), "PlayerStart preimage location drift: " + repr(before))
        rotation_before = actor_snapshot(start)["rotation"]
        other_before = [actor_snapshot(actor) for actor in actors if actor != start]
        start.modify()
        target = unreal.Vector(*self.candidate["persisted_playerstart_target"])
        require(start.set_actor_location(target, False, False) is not False, "PlayerStart relocation failed")
        require(close_vec(vec(start.get_actor_location()), self.candidate["persisted_playerstart_target"]),
                "Transient PlayerStart readback mismatch")
        require(actor_snapshot(start)["rotation"] == rotation_before, "PlayerStart rotation changed")
        other_after = [actor_snapshot(actor) for actor in actors if actor != start]
        differences = [
            {"before": before_item, "after": after_item}
            for before_item, after_item in zip(other_before, other_after)
            if before_item != after_item
        ]
        start_path = start.get_path_name()
        require(all(
            item["before"]["class"] == "TextRenderActor"
            and item["before"]["attach_parent"] == start_path
            and item["after"]["attach_parent"] == start_path
            and item["before"]["relative_location"] == item["after"]["relative_location"]
            and item["before"]["relative_rotation"] == item["after"]["relative_rotation"]
            and item["before"]["relative_scale"] == item["after"]["relative_scale"]
            for item in differences
        ), "Unexpected non-PlayerStart actor transform changed")
        require(dirty_packages()["content"] == [] and dirty_packages()["maps"] == [MAP],
                "Unexpected dirty package set before save: " + repr(dirty_packages()))
        require(self.level.save_current_level(), "Home map save failed")
        require(dirty_packages() == {"content": [], "maps": []}, "Dirty packages remained after save")
        new_hash = sha256(MAP_FILE)
        require(new_hash != EXPECTED_MAP_SHA, "Home map hash did not change")
        require(sha256(PROFILE_FILE) == EXPECTED_PROFILE_SHA, "ProfileV1 package changed")
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "Protected package changed: " + str(path))
        self.report.update({
            "status": "PASS_R20_SEEDED_ABOVE_SEA_LAND_START_SAVED_PENDING_FRESH_RELOAD",
            "playerstart_before": before,
            "playerstart_after": vec(start.get_actor_location()),
            "playerstart_rotation_preserved": True,
            "other_actor_count": len(other_before),
            "attached_label_count_moved_with_parent": len(differences),
            "map_sha256_after": new_hash,
            "profile_sha256_after": sha256(PROFILE_FILE),
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "protected_hashes_after": {str(path): sha256(path) for path in PROTECTED},
            "completed_utc": now(),
            "claim_limit": (
                "Saved PlayerStart transform and seeded runtime candidate evidence only. Fresh reload, MapCheck, "
                "spawn collision, approved grass pixels, day/night, gameplay and player acceptance remain pending."
            ),
            "next_safe_action": (
                "Fresh reload and MapCheck the exact saved map, then run one provider-off D3D12 PIE at the new "
                "start and require above-water player view, fitted collision, visible approved grass, and matched "
                "surface day/night before acceptance."
            ),
        })
        write_json_exclusive(RESULT, self.report)
        unreal.log_warning("REDMMO_R20_LAND_START_PASS " + json.dumps(self.report, sort_keys=True, default=str))
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), "QUIT_EDITOR")

    def fail(self, error):
        self.report.update({
            "status": "FAIL",
            "error": str(error),
            "traceback": traceback.format_exc(),
            "map_sha256_observed": sha256(MAP_FILE) if MAP_FILE.is_file() else None,
            "profile_sha256_observed": sha256(PROFILE_FILE) if PROFILE_FILE.is_file() else None,
            "completed_utc": now(),
        })
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        if not RESULT.exists():
            write_json_exclusive(RESULT, self.report)
        unreal.log_error("REDMMO_R20_LAND_START_FAIL " + repr(error) + "\n" + traceback.format_exc())
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), "QUIT_EDITOR")

    def tick(self, _delta):
        try:
            self.frames += 1
            require(time.monotonic() - self.phase_started < 300.0, "R20 phase timeout: " + self.phase)
            if self.phase == "prepare":
                self.start()
            elif self.phase == "wait_pie":
                self.bind_pie()
            elif self.phase == "wait_generation":
                if self.generation_ready():
                    self.ready_frames += 1
                    if self.ready_frames >= 180:
                        self.set_phase("select_candidate")
                else:
                    self.ready_frames = 0
            elif self.phase == "select_candidate":
                self.select_candidate()
            elif self.phase == "wait_pie_stop":
                if not self.level.is_in_play_in_editor() and self.editor.get_game_world() is None:
                    self.set_phase("persist")
            elif self.phase == "persist":
                self.persist()
        except Exception as error:
            self.fail(error)


require(os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path()))) ==
        os.path.normcase(os.path.abspath(str(PROJECT))), "Wrong active project")
transaction = Transaction()
transaction.handle = unreal.register_slate_post_tick_callback(transaction.tick)
unreal.log("REDMMO_R20_LAND_START_STARTED")
