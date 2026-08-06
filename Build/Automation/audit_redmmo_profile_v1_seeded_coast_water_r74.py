"""R74 read-only/no-save native PPG coast-water audit for retained R73.

The audit uses a generated Desert region known to contain both above- and
below-sea chunks.  It proves the current public PPG water binding, finds the
closest live above/below-sea pair, places the existing Trooper on the land
chunk facing the submerged neighbor, inventories native water components and
captures one Lit D3D12 player view.  It creates no plane or persistent actor.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import unreal


BASE = Path(r"D:\RedMMOTitan\Build\Automation\audit_redmmo_profile_v1_multi_biome_views_r72.py")
source = BASE.read_text(encoding="utf-8")
prefix = source.split("\nrequire(os.path.normcase", 1)[0]
ns = {"__name__": "redmmo_r74_base", "__file__": str(BASE)}
exec(compile(prefix, str(BASE), "exec"), ns)

PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject")
CONTENT = PROJECT.parent / "Content"
HOME_FILE = CONTENT / r"RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
PROFILE_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
R66_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_NoPalms_R66.uasset"
R73_PARENT_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\M_PPG_ProfileV1_BiomePresentation_R73.uasset"
R73_MI_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\MI_PPG_ProfileV1_BiomePresentation_R73.uasset"
R73_FOLIAGE_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_RockOnly_R73.uasset"
GENERATION_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\M_PPG_ProfileV1_Generation.uasset"
PLUGIN = Path(r"D:\UE_5.8\Engine\Plugins\Marketplace\Procedur890d9e860517V2")
WATER_FILE = PLUGIN / r"Content\Water\Materials\M_PlanetaryOceanWater.uasset"
PLANET_DATA_H = PLUGIN / r"Source\PPG\Public\PlanetData.h"
CHUNK_CPP = PLUGIN / r"Source\PPG\Private\ChunkObject.cpp"
SPAWNER_CPP = PLUGIN / r"Source\PPG\Private\PlanetSpawner.cpp"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_ProfileV1SeededCoastWater_R74_20260806T0001Z")

PROFILE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
R66 = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles/DA_PPG_ProfileV1_NoPalms_R66"
R73_FOLIAGE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles/DA_PPG_ProfileV1_RockOnly_R73"
R73_PARENT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Materials/M_PPG_ProfileV1_BiomePresentation_R73"
R73_MI = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Materials/MI_PPG_ProfileV1_BiomePresentation_R73"
GENERATION = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/M_PPG_ProfileV1_Generation"
NATIVE_WATER = "/PPG/Water/Materials/M_PlanetaryOceanWater"

EXPECTED = {
    HOME_FILE: "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3",
    PROFILE_FILE: "E19F14597BA1B73C958F6022B92A41B0C1A5F61573390295D3EEBD7484DBC335",
    R66_FILE: "C0EE6CB0A2D9D679D1FB4D64747555D55A5AF18ABED4AEC2666A1D5BECDA97DC",
    R73_FOLIAGE_FILE: "4499F76A4B541D92BB7CCF66EA4C8B55C2AA0AC0CEEA4D4AFB964D2807EE7A1D",
    R73_PARENT_FILE: "8D33435C91E0FE4813D5077991EDC6990AD5257395F67D6F5FDACBCE4F260992",
    R73_MI_FILE: "17C83A43FCB0AB9B22AC7EF499D53A8B7B2435B3F709CA585374E64F48371E91",
    GENERATION_FILE: "5165A27F0423735256EEE768739CE9547FEF7849BCA05540AAD63DF5BA1D96E3",
    WATER_FILE: "9DBBB204894F64FAC06F2D6A37348892D65345DA16329F6F35E1D416743A4E84",
    PLANET_DATA_H: "99AD104C419E1ADA4DD36804E6D7E6BA2AC47D8F67C5152E83DAAA08A8BDEF41",
    CHUNK_CPP: "BAAAB0CD184A10800E71D30ACCE6C918FC280D4632E9EC718ED73F5BFF61FE2A",
    SPAWNER_CPP: "6C73A5BCA90629364CF60062713B72B6E85C14A4454FB04A3D4E1FD6B79291F8",
    Path(r"D:\RedMMOTitan\Build\Automation\apply_redmmo_profile_v1_seeded_land_start_r20.py"):
        "7707C56E13E9922A2F2D3ADBCE4CB7CCD917241B5F875EE631E347B5A70B83B7",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}

# Three proven R69 Desert directions containing both above- and below-sea
# chunks.  R74 chooses the most sunlit one at runtime without changing light.
DESERT_DIRECTIONS = [
    [0.04692456666828282, 0.84375, -0.5346812345154763],
    [-0.9947455851113557, -0.09375, 0.041135852993057866],
    [0.47511337085238026, -0.84375, 0.24970627212244495],
]

ns.update({
    "PROJECT": PROJECT,
    "MAP_FILE": HOME_FILE,
    "PROFILE_FILE": PROFILE_FILE,
    "R66_FILE": R66_FILE,
    "ROLE_PARENT_FILE": R73_PARENT_FILE,
    "ROLE_MI_FILE": R73_MI_FILE,
    "EXPECTED": EXPECTED,
    "PROFILE": PROFILE,
    "TARGETS": [{"label": "seeded_coast", "role": "Desert", "direction": DESERT_DIRECTIONS[0], "above_sea": True}],
    "ROLLBACK": Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeProfileV1SeededCoastWaterAudit_R74_20260806T0001Z"),
    "DIAG": DIAG,
    "CAPTURE_DIR": DIAG / "Capture",
    "RESULT": DIAG / "result.json",
    "LOG": DIAG / "verify.log",
})

Audit = ns["Audit"]
require = ns["require"]
asset_path = ns["asset_path"]
dirty_packages = ns["dirty_packages"]
sha256 = ns["sha256"]
add = ns["add"]
sub = ns["sub"]
mul = ns["mul"]
dot = ns["dot"]
length = ns["length"]
normalized = ns["normalized"]
vec = ns["vec"]
sample_component = ns["sample_component"]
component_trace = ns["component_trace"]


def material_ancestry(material):
    result = []
    seen = set()
    current = material
    while current is not None and current.get_path_name() not in seen:
        seen.add(current.get_path_name())
        result.append(asset_path(current))
        try:
            current = current.get_editor_property("parent")
        except Exception:
            break
    return result


def serialized_water_gate(self):
    profile = unreal.EditorAssetLibrary.load_asset(PROFILE)
    generation = unreal.EditorAssetLibrary.load_asset(GENERATION)
    require(profile is not None and generation is not None, "ProfileV1 water assets failed to load")
    require(bool(profile.get_editor_property("generate_water")), "native PPG water is disabled")
    water = asset_path(profile.get_editor_property("water_material"))
    require(water == NATIVE_WATER, "native PPG water binding drift: " + str(water))
    expressions = list(unreal.MaterialEditingLibrary.get_material_expressions(generation))
    thresholds = [item for item in expressions if item.get_class().get_name() == "MaterialExpressionScalarParameter" and str(item.get_editor_property("parameter_name")) == "ShorelineFlattenThreshold"]
    flatten = [item for item in expressions if item.get_class().get_name() == "MaterialExpressionPlanetFlattenElevation"]
    require(len(thresholds) == 1 and abs(float(thresholds[0].get_editor_property("default_value")) - 0.012) <= 1.0e-6, "shoreline threshold drift")
    require(len(flatten) == 6, "expected six per-role shoreline flatten nodes")
    self.report["serialized_water_gate"] = {
        "generate_water": True,
        "water_material": water,
        "far_water_material": asset_path(profile.get_editor_property("far_water_material")),
        "water_simulation_data": asset_path(profile.get_editor_property("water_simulation_data")),
        "planet_radius_cm": float(profile.get_editor_property("planet_radius")),
        "generation_material": asset_path(profile.get_editor_property("generation_material")),
        "shoreline_flatten_threshold": 0.012,
        "shoreline_flatten_node_count": 6,
        "public_native_contract": {
            "water_generation_condition": "PlanetData.generate_water and ChunkMinHeight < 0",
            "surface_radius": "PlanetData.planet_radius",
            "material_parameters": ["HeightMap", "PlanetRadius", "planet-surface transform parameters"],
            "collision": "native WaterChunk uses NoCollision",
            "biome_role_dependency": False,
        },
    }


original_start = Audit.start


def start_r74(self):
    self.report.update({
        "schema": "redmmo.ppg.profile_v1_seeded_coast_water.audit.r74.v1",
        "status": "RUNNING",
        "evidence_class": "real_gpu_visual",
        "persistent_map_or_asset_writes": False,
        "manual_plane_or_standin_created": False,
    })
    serialized_water_gate(self)
    original_start(self)


original_bind_pie = Audit.bind_pie


def bind_pie_r74(self):
    original_bind_pie(self)
    if self.world is None:
        return
    unreal.SystemLibrary.execute_console_command(self.world, "viewmode lit")
    unreal.SystemLibrary.execute_console_command(self.world, "r.EyeAdaptationQuality 0")
    lights = list(unreal.GameplayStatics.get_all_actors_of_class(self.world, unreal.DirectionalLight))
    light_dirs = []
    for actor in lights:
        component = actor.get_component_by_class(unreal.DirectionalLightComponent)
        if component is not None and component.is_visible():
            rays_to_surface = mul(actor.get_actor_forward_vector(), -1.0)
            light_dirs.append((float(component.get_editor_property("intensity")), normalized(rays_to_surface), actor.get_path_name()))
    require(light_dirs, "no visible directional light")
    light_dirs.sort(key=lambda item: item[0], reverse=True)
    sun = light_dirs[0]
    ranked = []
    for raw in DESERT_DIRECTIONS:
        direction = normalized(unreal.Vector(*raw))
        ranked.append((dot(direction, sun[1]), direction, raw))
    ranked.sort(key=lambda item: item[0], reverse=True)
    self.direction = ranked[0][1]
    self.report["sun_selection"] = {
        "actor": sun[2],
        "intensity": sun[0],
        "selected_direction": ranked[0][2],
        "selected_solar_dot": ranked[0][0],
        "all_candidate_solar_dots": [{"direction": raw, "solar_dot": score} for score, _direction, raw in ranked],
    }


def begin_next_target_r74(self):
    self.target_index += 1
    if self.target_index >= 1:
        self.level.editor_request_end_play()
        self.set_phase("wait_pie_stop")
        return
    self.target = {"label": "seeded_coast", "role": "Desert", "direction": vec(self.direction), "above_sea": True}
    self.selected = None
    self.capture_requested = None
    target = add(self.center, mul(self.direction, self.radius + ns["VIEW_ALTITUDE_CM"]))
    forward = ns["tangent_for"](self.direction)
    rotation = unreal.MathLibrary.make_rot_from_xz(forward, self.direction)
    require(self.pawn.set_actor_location(target, False, True) is not False, "coast stream teleport failed")
    self.pawn.set_actor_rotation(rotation, True)
    self.controller.set_control_rotation(rotation)
    self.set_phase("settle_stream")


def select_and_place_r74(self):
    terrain = []
    for component in self.spawner.get_components_by_class(unreal.StaticMeshComponent):
        if (not component.is_query_collision_enabled()
                or component.get_editor_property("static_mesh") is None
                or isinstance(component, unreal.InstancedStaticMeshComponent)):
            continue
        delta = sub(component.get_world_location(), self.center)
        if length(delta) < self.radius * 0.5:
            continue
        direction = normalized(delta)
        try:
            sample = sample_component(self.world, component, add(self.center, mul(direction, self.radius)), self.center, self.radius)
        except Exception:
            continue
        if sample is None:
            continue
        dominant = int(sample["top3_biome_indices"][0])
        role = self.by_index.get(dominant, {"name": "UNKNOWN"})["name"]
        if role != "Desert":
            continue
        above = float(sample["raw_index_pixel"][3]) >= 0.999
        terrain.append({"component": component, "direction": direction, "sample": sample, "above": above})
    land = [item for item in terrain if item["above"]]
    submerged = [item for item in terrain if not item["above"]]
    require(land and submerged, "selected Desert stream did not expose both sides of sea datum")
    pairs = [(dot(a["direction"], b["direction"]), a, b) for a in land for b in submerged]
    pairs.sort(key=lambda item: item[0], reverse=True)
    separation_dot, land_item, sea_item = pairs[0]
    hit_point, hit_normal = component_trace(land_item["component"], self.center, self.radius, land_item["direction"])
    if dot(hit_normal, land_item["direction"]) < 0.0:
        hit_normal = mul(hit_normal, -1.0)
    radial_up = normalized(sub(hit_point, self.center))
    sea_forward = sub(sea_item["direction"], mul(radial_up, dot(sea_item["direction"], radial_up)))
    require(length(sea_forward) > 1.0e-6, "coast tangent direction degenerate")
    self.sea_forward = normalized(sea_forward)
    rotation = unreal.MathLibrary.make_rot_from_xz(self.sea_forward, radial_up)
    location = add(hit_point, mul(radial_up, 220.0))
    require(self.pawn.set_actor_location(location, False, True) is not False, "coast ground placement failed")
    self.pawn.set_actor_rotation(rotation, True)
    self.controller.set_control_rotation(rotation)

    water_components = []
    for component in self.spawner.get_components_by_class(unreal.StaticMeshComponent):
        if component.is_query_collision_enabled() or isinstance(component, unreal.InstancedStaticMeshComponent):
            continue
        material = component.get_material(0)
        ancestry = material_ancestry(material) if material is not None else []
        if NATIVE_WATER in ancestry:
            water_components.append({
                "component": component.get_path_name(),
                "visible": bool(component.is_visible()),
                "hidden_in_game": bool(component.get_editor_property("hidden_in_game")),
                "collision_enabled": str(component.get_collision_enabled()),
                "render_in_main_pass": bool(component.get_editor_property("render_in_main_pass")),
                "material_ancestry": ancestry,
                "location": vec(component.get_world_location()),
            })
    require(water_components, "no native PPG water components use the bound water material")
    require(any(item["visible"] and not item["hidden_in_game"] and item["render_in_main_pass"] for item in water_components), "native water components are not render-visible")
    self.selected = {
        "label": "seeded_coast",
        "land_role": "Desert",
        "land_component": land_item["component"].get_path_name(),
        "land_direction": vec(land_item["direction"]),
        "land_sea_authority_alpha": float(land_item["sample"]["raw_index_pixel"][3]),
        "submerged_role": "Desert",
        "submerged_component": sea_item["component"].get_path_name(),
        "submerged_direction": vec(sea_item["direction"]),
        "submerged_sea_authority_alpha": float(sea_item["sample"]["raw_index_pixel"][3]),
        "pair_direction_dot": separation_dot,
        "pair_angular_separation_degrees": math.degrees(math.acos(max(-1.0, min(1.0, separation_dot)))),
        "native_water_component_count": len(water_components),
        "native_water_visible_main_pass_count": sum(1 for item in water_components if item["visible"] and not item["hidden_in_game"] and item["render_in_main_pass"]),
        "native_water_component_preview": water_components[:12],
        "trace_point": vec(hit_point),
        "trace_normal": vec(hit_normal),
        "player_location": vec(location),
        "sea_forward": vec(self.sea_forward),
    }
    self.set_phase("settle_ground")


def pin_orientation_r74(self):
    if not self.selected:
        return
    up = normalized(sub(self.pawn.get_actor_location(), self.center))
    forward = sub(self.sea_forward, mul(up, dot(self.sea_forward, up)))
    if length(forward) < 1.0e-6:
        forward = ns["tangent_for"](up)
    rotation = unreal.MathLibrary.make_rot_from_xz(normalized(forward), up)
    self.pawn.set_actor_rotation(rotation, True)
    self.controller.set_control_rotation(rotation)


def request_capture_r74(self):
    path = ns["CAPTURE_DIR"] / "R74_seeded_desert_coast_native_water_lit.png"
    require(not path.exists(), "capture no-clobber failed")
    camera = unreal.GameplayStatics.get_player_camera_manager(self.world, 0)
    self.selected["capture_player_location"] = vec(self.pawn.get_actor_location())
    self.selected["capture_camera_location"] = vec(camera.get_actor_location()) if camera else None
    self.selected["capture_camera_rotation"] = str(camera.get_actor_rotation()) if camera else None
    self.selected["capture_path"] = str(path)
    require(unreal.RedPPGFoliageDiagnostics.request_viewport_screenshot(str(path)), "viewport screenshot rejected")
    self.capture_requested = ns["time"].monotonic()
    self.set_phase("wait_capture")


def publish_r74(self):
    require(not self.level.is_in_play_in_editor() and self.editor.get_game_world() is None, "PIE still active")
    require(dirty_packages() == {"content": [], "maps": []}, "R74 dirtied packages")
    for path, expected in EXPECTED.items():
        require(sha256(path) == expected, "post-run drift: " + str(path))
    require(len(self.records) == 1, "coast capture missing")
    self.report.update({
        "status": "PASS_R74_NATIVE_PPG_SEEDED_COAST_WATER_LIT_NO_SAVE",
        "completed_utc": ns["now"](),
        "records": self.records,
        "map_sha256_after": sha256(HOME_FILE),
        "profile_sha256_after": sha256(PROFILE_FILE),
        "dirty_packages_after": dirty_packages(),
        "provider_gate_after": ns["provider_gate"](),
        "claim_limit": "One fresh Lit D3D12 native PPG Desert sea-datum boundary and water-component audit only. The native water hook is elevation-driven, not Ocean-biome-driven. This does not prove final shoreline art, beach bands, water acceptance, gameplay, packaging, replication, multiplayer or user acceptance.",
    })
    ns["write_json_exclusive"](ns["RESULT"], self.report)
    unreal.log_warning("REDMMO_R74_SEEDED_COAST_WATER_PASS " + json.dumps({"water_components": self.records[0]["native_water_component_count"], "capture": self.records[0]["capture_path"]}))
    if self.handle is not None:
        unreal.unregister_slate_post_tick_callback(self.handle)
        self.handle = None
    unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), "QUIT_EDITOR")


Audit.start = start_r74
Audit.bind_pie = bind_pie_r74
Audit.begin_next_target = begin_next_target_r74
Audit.select_and_place = select_and_place_r74
Audit.pin_orientation = pin_orientation_r74
Audit.request_capture = request_capture_r74
Audit.publish = publish_r74

require(Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True) == PROJECT.resolve(strict=True), "wrong active project")
audit = Audit()
audit.handle = unreal.register_slate_post_tick_callback(audit.tick)
unreal.log("REDMMO_R74_SEEDED_COAST_WATER_STARTED")
