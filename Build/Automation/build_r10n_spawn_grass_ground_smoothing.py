"""Build the rollback-backed R10N player-spawn grass and terrain smoothing successor."""

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


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
HOME_MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
HOME_FILE = PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
EXPECTED_HOME = "B19019D31369D0325896BA871EB083036DE64516EF51314CF89A74B30366DB10"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_HomePresentation_R10N_20260802_181848")
RESULT = DIAG / "build_r10n_spawn_grass_ground_smoothing_result.json"
PROFILE = PROJECT / r"Config\RedMMO\PPGStylizedFoliageProfiles\HomeWorld_Presentation_R10N.json"
ROLLBACK_MANIFEST = Path(r"D:\RedMMOTitanWindowsData\Rollback\RedMMO_PPG_HomePresentation_R10N_20260802_181848_A01\pre_r10n_manifest.json")

SOURCE_ROOT = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10M"
SOURCE_PLANET = SOURCE_ROOT + "/DA_PPG_HomeWorld_StylizedBinding_R10M"
SOURCE_FOLIAGE = SOURCE_ROOT + "/Profiles/DA_PPG_HomeWorld_StylizedForest_R10M"
SOURCE_SURFACE = SOURCE_ROOT + "/Materials/MI_PPG_Home_PaintedLeafGround_Natural_R10M"
SOURCE_GRASS_MIS = [
    SOURCE_ROOT + "/Materials/MI_GrassChunks_Natural_A_R10M",
    SOURCE_ROOT + "/Materials/MI_GrassChunks_Natural_B_R10M",
]
SOURCE_GRASS_MESHES = [
    SOURCE_ROOT + "/Meshes/SM_GrassChunk_Natural_A_R10M",
    SOURCE_ROOT + "/Meshes/SM_GrassChunk_Natural_B_R10M",
]
SOURCE_GENERATION = "/Game/RedMMO/World/PPG/HomeWorld/StylizedPilot/R05/Materials/M_PPG_Generation_CapFoliage_R05"

ROOT = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N"
TARGET_PLANET = ROOT + "/DA_PPG_HomeWorld_StylizedBinding_R10N"
TARGET_FOLIAGE = ROOT + "/Profiles/DA_PPG_HomeWorld_StylizedForest_R10N"
TARGET_SURFACE = ROOT + "/Materials/MI_PPG_Home_PaintedLeafGround_Scaled_R10N"
TARGET_GENERATION = ROOT + "/Materials/M_PPG_Generation_SmoothSpawnGrass_R10N"
GRASS_MIS = [
    ROOT + "/Materials/MI_GrassChunks_DenseTall_A_R10N",
    ROOT + "/Materials/MI_GrassChunks_DenseTall_B_R10N",
]
GRASS_MESHES = [
    ROOT + "/Meshes/SM_GrassChunk_DenseTall_A_R10N",
    ROOT + "/Meshes/SM_GrassChunk_DenseTall_B_R10N",
]

GROUND_UV_SCALE = 12.0
GROUND_MACRO_SCALE_A = 1.0
GROUND_MACRO_SCALE_B = 2.0
GROUND_NORMAL_AMOUNT = 0.20
GRASS_DENSITY = 180.0
GRASS_SCALE = (1.00, 1.55)
GRASS_MAX_SLOPE = 30.0
GRASS_LOCAL_SCALE = 1.30
GRASS_LOCAL_Z_SCALE = 1.45
GRASS_HIGHLIGHT_AMOUNT = 0.62
GRASS_HIGHLIGHT_DENSITY = 0.82
GRASS_HIGHLIGHT_GRADIENT_CONTRAST = 4.20
HILLS_DETAILS = 200.0
MOUNTAIN_DETAILS = 100.0

SOURCE_HASHES = {
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedPilot\R05\Materials\M_PPG_Generation_CapFoliage_R05.uasset": "F48D4CEE2078401FD31C1EEA989EE70CF9BB4444575C2B8A62091C7DACFA5594",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10M\DA_PPG_HomeWorld_StylizedBinding_R10M.uasset": "1CE35B5C690485E5183706469BAF40E693DBC436B722A8C6B1DF0F61E5841183",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10M\Profiles\DA_PPG_HomeWorld_StylizedForest_R10M.uasset": "59008A72B604A86AD02DBDE7BFA8B8A4946B78ECFB6C5E0FF624772A60AC7305",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10M\Materials\MI_PPG_Home_PaintedLeafGround_Natural_R10M.uasset": "8440FE7A388A733FF488539C65F7621E6791CCA8650CACCD1EE88FD9AED181DC",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10M\Materials\MI_GrassChunks_Natural_A_R10M.uasset": "5E73A8B5619C3D279A9E5FB71ABB51BA7B3CC64A2286172597C3D82CE4130878",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10M\Materials\MI_GrassChunks_Natural_B_R10M.uasset": "2D8744BD77272965437B88B2788985C6FA48AB3D6A1148C9D6A6B7AEE485BFE5",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10M\Meshes\SM_GrassChunk_Natural_A_R10M.uasset": "1A1B7724D00A7581545D1960773389AB040B49E973238A42668ADA082D894A85",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10M\Meshes\SM_GrassChunk_Natural_B_R10M.uasset": "250B32E289FE936C76E718969F07C96E002E8C73A1B4F4DF2DD0392D78D94C1A",
}
PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"): "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"): "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap"): "211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7",
    Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeCoastDatum_20260714\RedPlanetGen_50km_FusedPrototype.umap"): "A9C42C0D1B0429DD1018F00F0D2AB8A18F66C07291611964EFF5F9710F3B0C6A",
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


def asset_path(value):
    if value is None:
        return None
    path = value.get_path_name().split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def write_json_exclusive(path, payload):
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with Path(path).open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def dirty_packages():
    values = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    values += list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted(set(asset_path(item) for item in values))


def provider_gate():
    records = []
    for port in (5353, 8000, 8765):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.25)
        try:
            code = sock.connect_ex(("127.0.0.1", port))
        finally:
            sock.close()
        records.append({"port": port, "closed": code != 0, "connect_ex": code})
    require(all(item["closed"] for item in records), "Provider listener active")
    return records


def load(path, class_name=None):
    asset = unreal.EditorAssetLibrary.load_asset(path)
    require(asset is not None, "Missing asset: " + path)
    if class_name:
        require(asset.get_class().get_name() == class_name, "Class mismatch: " + path)
    return asset


def duplicate(source, target, created):
    require(not unreal.EditorAssetLibrary.does_asset_exist(target), "Refusing overwrite: " + target)
    asset = unreal.EditorAssetLibrary.duplicate_asset(source, target)
    require(asset is not None, "Duplicate failed: {} -> {}".format(source, target))
    created.append(target)
    return asset


def normalized_key(name):
    return str(name).replace("_", "").replace(" ", "").lower()


def find_key(values, wanted):
    wanted = normalized_key(wanted)
    matches = [key for key in values if normalized_key(key) == wanted]
    require(len(matches) == 1, "Expected one key {} in {}".format(wanted, list(values)))
    return matches[0]


def input_names(node):
    return [str(value) for value in unreal.MaterialEditingLibrary.get_material_expression_input_names(node)]


def output_names(node):
    return [str(value) for value in unreal.MaterialEditingLibrary.get_material_expression_output_names(node)]


def choose_output(source, requested=""):
    outputs = output_names(source)
    if requested in outputs:
        return requested
    if requested == "" and len(outputs) == 1:
        return outputs[0]
    if requested == "" and "RGB" in outputs:
        return "RGB"
    if "" in outputs:
        return ""
    raise RuntimeError("No usable output on {}: {}".format(source.get_name(), outputs))


def connect(source, destination, input_name, output_name=""):
    require(input_name in input_names(destination), "Missing input {} on {}".format(input_name, destination.get_name()))
    require(
        unreal.MaterialEditingLibrary.connect_material_expressions(
            source, choose_output(source, output_name), destination, input_name
        ),
        "Connection failed {} -> {}.{}".format(source.get_name(), destination.get_name(), input_name),
    )


def resolved_input(material, node, input_name):
    names = input_names(node)
    sources = list(unreal.MaterialEditingLibrary.get_inputs_for_material_expression(material, node))
    require(len(names) == len(sources), "Input/source drift on " + node.get_name())
    return sources[names.index(input_name)]


def expression_desc(node):
    try:
        return str(node.get_editor_property("desc"))
    except Exception:
        return ""


def editor_y(node):
    for name in ("material_expression_editor_y", "editor_y"):
        try:
            return int(node.get_editor_property(name))
        except Exception:
            pass
    return 0


def configure_instanced(material):
    usage = None
    for name in ("INSTANCED_STATIC_MESHES", "MATUSAGE_INSTANCED_STATIC_MESHES", "MATUSAGE_InstancedStaticMeshes"):
        usage = getattr(unreal.MaterialUsage, name, None)
        if usage is not None:
            break
    require(usage is not None, "Instanced material usage enum missing")
    unreal.MaterialEditingLibrary.set_material_usage_override(material, usage, True, True)
    require(unreal.MaterialEditingLibrary.has_material_usage(material, usage), "Instanced usage failed: " + asset_path(material))


def build_generation(created):
    generation = duplicate(SOURCE_GENERATION, TARGET_GENERATION, created)
    nodes = list(unreal.MaterialEditingLibrary.get_material_expressions(generation))

    scalar_changes = {}
    for parameter_name, expected_before, after in (
        ("HillsDetails", 100.0, HILLS_DETAILS),
        ("MountainDetails", 50.0, MOUNTAIN_DETAILS),
    ):
        matches = []
        for node in nodes:
            if node.get_class().get_name() != "MaterialExpressionScalarParameter":
                continue
            if str(node.get_editor_property("parameter_name")) == parameter_name:
                matches.append(node)
        require(len(matches) == 1, "Expected one scalar parameter: " + parameter_name)
        node = matches[0]
        before = float(node.get_editor_property("default_value"))
        require(abs(before - expected_before) <= 1.0e-5, "{} default drift: {}".format(parameter_name, before))
        node.set_editor_property("default_value", after)
        scalar_changes[parameter_name] = {"before": before, "after": after, "node": node.get_name()}

    grass_sources = sorted(
        [node for node in nodes if expression_desc(node) == "R05 read original G density"],
        key=editor_y,
    )
    grass_destinations = sorted(
        [node for node in nodes if expression_desc(node) == "R05 BA: inverted-grass B, rock Outside A"],
        key=editor_y,
    )
    require(len(grass_sources) == 3 and len(grass_destinations) == 3, "R05 grass-cap graph signature drift")
    restored = []
    for source, destination in zip(grass_sources, grass_destinations):
        before = resolved_input(generation, destination, "A")
        require(before is not None and expression_desc(before) == "R05 B=1-((1-G)*Outside) for inverted grass", "Unexpected R05 B input")
        require(unreal.MaterialEditingLibrary.disconnect_material_expressions(destination, "A"), "Could not disconnect R05 grass suppression")
        connect(source, destination, "A")
        require(resolved_input(generation, destination, "A") == source, "Grass cap restore did not persist in memory")
        restored.append({"source": source.get_name(), "destination": destination.get_name(), "editor_y": editor_y(destination)})

    compile_result = unreal.MaterialEditingLibrary.recompile_material(generation)
    compile_errors = [str(value) for value in (compile_result or []) if str(value).strip()]
    require(not compile_errors, "R10N generation compile errors: {}".format(compile_errors))
    require(unreal.EditorAssetLibrary.save_loaded_asset(generation, only_if_is_dirty=False), "R10N generation save failed")
    return generation, {
        "asset": TARGET_GENERATION,
        "scalar_changes": scalar_changes,
        "restored_grass_channels": restored,
        "grass_inside_cap_truth": "B=OriginalG, so BLUE+invert yields 1-OriginalG at PlayerStart",
        "tree_and_rock_cap_preserved": True,
        "compile_errors": compile_errors,
    }


def build_surface(created):
    surface = duplicate(SOURCE_SURFACE, TARGET_SURFACE, created)
    for name, value in {
        "R10L_GroundUVScale": GROUND_UV_SCALE,
        "R10L_MacroUVScaleA": GROUND_MACRO_SCALE_A,
        "R10L_MacroUVScaleB": GROUND_MACRO_SCALE_B,
        "R10L_NormalAmount": GROUND_NORMAL_AMOUNT,
    }.items():
        unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(surface, name, value)
    unreal.MaterialEditingLibrary.update_material_instance(surface)
    require(unreal.EditorAssetLibrary.save_loaded_asset(surface, only_if_is_dirty=False), "R10N surface save failed")
    return surface


def build_grass(created):
    materials = []
    meshes = []
    for source, target in zip(SOURCE_GRASS_MIS, GRASS_MIS):
        instance = duplicate(source, target, created)
        for name, value in {
            "LocalScale_Multiply": GRASS_LOCAL_SCALE,
            "GrassLocalZ_ScaleMultiply": GRASS_LOCAL_Z_SCALE,
            "GrassHighlights_Amount": GRASS_HIGHLIGHT_AMOUNT,
            "GrassHighlights_Density": GRASS_HIGHLIGHT_DENSITY,
            "GrassHighlights_Gradient_Contrast": GRASS_HIGHLIGHT_GRADIENT_CONTRAST,
        }.items():
            unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(instance, name, value)
        unreal.MaterialEditingLibrary.update_material_instance(instance)
        configure_instanced(instance)
        require(unreal.EditorAssetLibrary.save_loaded_asset(instance, only_if_is_dirty=False), "R10N grass MI save failed")
        materials.append(instance)
    for source, target, material in zip(SOURCE_GRASS_MESHES, GRASS_MESHES, materials):
        mesh = duplicate(source, target, created)
        require(len(list(mesh.get_editor_property("static_materials"))) == 1, "Grass slot count drift")
        mesh.set_material(0, material)
        require(unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False), "R10N grass mesh save failed")
        meshes.append(mesh)
    return materials, meshes


def rebuild_grass_entry(source_entry, target_meshes):
    values = source_entry.to_dict()
    mesh_key = find_key(values, "meshes")
    lod_key = find_key(values, "lods")
    density_key = find_key(values, "foliage_density")
    max_slope_key = find_key(values, "max_slope")
    scale_key = find_key(values, "scale")

    require(abs(float(values[density_key]) - GRASS_DENSITY) <= 1.0e-5, "R10M grass density drift")
    values[density_key] = GRASS_DENSITY
    values[max_slope_key] = GRASS_MAX_SLOPE
    scale = values[scale_key]
    scale.set_editor_property("min", GRASS_SCALE[0])
    scale.set_editor_property("max", GRASS_SCALE[1])
    values[scale_key] = scale

    old_variants = list(source_entry.get_editor_property("meshes"))
    require(len(old_variants) == len(target_meshes), "Foliage mesh cardinality drift")
    values[mesh_key] = [
        unreal.FoliageMeshVariant(
            mesh=mesh,
            probability_weight=float(old.get_editor_property("probability_weight")),
        )
        for old, mesh in zip(old_variants, target_meshes)
    ]
    lods = []
    for lod in list(source_entry.get_editor_property("lods")):
        lod_values = lod.to_dict()
        lod_mesh_key = find_key(lod_values, "meshes")
        lod_values[lod_mesh_key] = list(target_meshes)
        lods.append(unreal.FoliageLOD(**lod_values))
    values[lod_key] = lods
    return unreal.FoliageList(**values)


def build_foliage_and_planet(generation, surface, grass_meshes, created):
    source_foliage = load(SOURCE_FOLIAGE, "FoliageData")
    source_entries = list(source_foliage.get_editor_property("foliage_list"))
    require(len(source_entries) == 3, "Foliage entry count drift")
    foliage = duplicate(SOURCE_FOLIAGE, TARGET_FOLIAGE, created)
    entries = list(foliage.get_editor_property("foliage_list"))
    entries[1] = rebuild_grass_entry(source_entries[1], grass_meshes)
    foliage.set_editor_property("foliage_list", entries)
    require(unreal.EditorAssetLibrary.save_loaded_asset(foliage, only_if_is_dirty=False), "R10N foliage save failed")

    planet = duplicate(SOURCE_PLANET, TARGET_PLANET, created)
    before_seed = int(planet.get_editor_property("generation_seed"))
    before_radius = float(planet.get_editor_property("planet_radius"))
    require(before_seed == 1337, "Generation seed drift")
    planet.set_editor_property("generation_material", generation)
    planet.set_editor_property("planet_material", surface)
    biomes = list(planet.get_editor_property("biome_data"))
    changed = []
    for index, biome in enumerate(biomes):
        values = biome.to_dict()
        touched = False
        for key in list(values):
            if normalized_key(key) in ("foliagedata", "forestfoliagedata") and asset_path(values[key]) == SOURCE_FOLIAGE:
                values[key] = foliage
                touched = True
        if touched:
            biomes[index] = unreal.BiomeData(**values)
            changed.append(str(biome.get_editor_property("name")))
    require(changed, "No R10M foliage reference replaced")
    planet.set_editor_property("biome_data", biomes)
    require(int(planet.get_editor_property("generation_seed")) == before_seed, "Seed changed")
    require(abs(float(planet.get_editor_property("planet_radius")) - before_radius) <= 1.0e-3, "Radius changed")
    require(unreal.EditorAssetLibrary.save_loaded_asset(planet, only_if_is_dirty=False), "R10N PlanetData save failed")
    return foliage, planet, changed, {"seed": before_seed, "radius_cm": before_radius}


def bind_map(planet):
    world = unreal.EditorLoadingAndSavingUtils.load_map(HOME_MAP)
    require(world is not None and not dirty_packages(), "Home map load failed/dirtied packages")
    actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
    require(len(actors) == 12, "Home actor count drift")
    spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
    require(len(spawners) == 1, "Expected one PPG spawner")
    spawner = spawners[0]
    require(asset_path(spawner.get_editor_property("planet_data")) == SOURCE_PLANET, "Source PlanetData binding drift")
    cap_before = int(spawner.get_editor_property("max_foliage_instances_per_chunk"))
    require(cap_before == 100000, "Spawner foliage cap drift")
    spawner.set_editor_property("planet_data", planet)
    require(callable(getattr(spawner, "regenerate_planet", None)), "Regenerate unavailable")
    spawner.regenerate_planet()
    require(int(spawner.get_editor_property("max_foliage_instances_per_chunk")) == cap_before, "Foliage cap changed")
    require(set(dirty_packages()).issubset({HOME_MAP}), "Unexpected dirty package before save")
    require(unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level(), "Home save failed")
    require(not dirty_packages(), "Dirty packages remain")
    player_starts = [actor for actor in actors if actor.get_class().get_name() == "PlayerStart"]
    require(len(player_starts) == 1, "Expected one PlayerStart")
    start = player_starts[0].get_actor_location()
    return {
        "actor_labels": sorted(actor.get_actor_label() for actor in actors),
        "spawner_max_foliage_instances_per_chunk": cap_before,
        "player_start_location": [start.x, start.y, start.z],
    }


def write_profile():
    require(not PROFILE.exists(), "R10N profile no-clobber failed")
    payload = {
        "schema": "redmmo.ppg_home_presentation_profile.r10n.v1",
        "revision": "R10N_actual_spawn_grass_scaled_painted_ground_smoothed_fine_relief",
        "source_revision": "R10M",
        "ground": {
            "material": TARGET_SURFACE,
            "uv_scale": GROUND_UV_SCALE,
            "macro_uv_scales": [GROUND_MACRO_SCALE_A, GROUND_MACRO_SCALE_B],
            "normal_amount": GROUND_NORMAL_AMOUNT,
        },
        "grass": {
            "density": GRASS_DENSITY,
            "scale": list(GRASS_SCALE),
            "max_slope_degrees": GRASS_MAX_SLOPE,
            "local_scale": GRASS_LOCAL_SCALE,
            "local_z_scale": GRASS_LOCAL_Z_SCALE,
            "highlight_amount": GRASS_HIGHLIGHT_AMOUNT,
            "highlight_density": GRASS_HIGHLIGHT_DENSITY,
            "highlight_gradient_contrast": GRASS_HIGHLIGHT_GRADIENT_CONTRAST,
            "spawn_cap_grass_suppression_removed": True,
            "tree_and_rock_cap_preserved": True,
            "materials": GRASS_MIS,
            "meshes": GRASS_MESHES,
        },
        "terrain": {
            "generation_material": TARGET_GENERATION,
            "seed": 1337,
            "hills_details_divisor": HILLS_DETAILS,
            "mountain_details_divisor": MOUNTAIN_DETAILS,
            "broad_shape_controls_changed": False,
        },
        "vendor_assets_modified": False,
        "human_accepted": False,
    }
    PROFILE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return payload


def verify_preconditions():
    require(
        os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path())))
        == os.path.normcase(os.path.abspath(str(PROJECT / "RedMMO.uproject"))),
        "Active project mismatch",
    )
    require(HOME_FILE.is_file() and sha256(HOME_FILE) == EXPECTED_HOME, "Home map hash drift")
    require(ROLLBACK_MANIFEST.is_file(), "Rollback manifest missing")
    manifest = json.loads(ROLLBACK_MANIFEST.read_text(encoding="utf-8-sig"))
    require(
        manifest.get("schema") == "redmmo.ppg_home_presentation.r10n.rollback.v1"
        and manifest.get("source_home_sha256") == EXPECTED_HOME,
        "Rollback manifest drift",
    )
    require(not unreal.EditorAssetLibrary.does_directory_exist(ROOT), "R10N content root exists")
    require(not PROFILE.exists() and not RESULT.exists(), "R10N output exists")
    require(not dirty_packages(), "Editor dirty before R10N")
    for path, expected in SOURCE_HASHES.items():
        require(path.is_file() and sha256(path) == expected, "Source hash drift: " + str(path))
    for path, expected in PROTECTED.items():
        require(path.is_file() and sha256(path) == expected, "Protected hash drift: " + str(path))


_EXIT = {"handle": None}


def schedule_exit(delay=7.0):
    started = time.monotonic()

    def tick(_delta):
        if time.monotonic() - started < delay:
            return
        handle = _EXIT.get("handle")
        if handle is not None:
            try:
                unreal.unregister_slate_post_tick_callback(handle)
            except Exception:
                pass
            _EXIT["handle"] = None
        unreal.SystemLibrary.quit_editor()

    _EXIT["handle"] = unreal.register_slate_post_tick_callback(tick)


def main():
    report = {
        "schema": "redmmo.ppg_home_presentation.r10n.build.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "created_assets": [],
    }
    try:
        verify_preconditions()
        report["provider_gate"] = provider_gate()
        generation, report["generation"] = build_generation(report["created_assets"])
        surface = build_surface(report["created_assets"])
        materials, meshes = build_grass(report["created_assets"])
        foliage, planet, changed, terrain_identity = build_foliage_and_planet(
            generation, surface, meshes, report["created_assets"]
        )
        report["map"] = bind_map(planet)
        report["profile"] = write_profile()
        report["changed_biomes"] = changed
        report["terrain_identity"] = terrain_identity
        report["home_map_sha256_before"] = EXPECTED_HOME
        report["home_map_sha256_after"] = sha256(HOME_FILE)
        require(report["home_map_sha256_after"] != EXPECTED_HOME, "Home binding did not serialize")
        report["project_owned_hashes"] = {}
        for asset in report["created_assets"]:
            file_path = PROJECT / ("Content" + asset.removeprefix("/Game").replace("/", os.sep) + ".uasset")
            if file_path.is_file():
                report["project_owned_hashes"][asset] = sha256(file_path)
        report["profile_sha256"] = sha256(PROFILE)
        for path, expected in SOURCE_HASHES.items():
            require(sha256(path) == expected, "Source modified: " + str(path))
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "Protected modified: " + str(path))
        require(not dirty_packages(), "Dirty packages remain")
        report["status"] = "PASS_STATIC_SERIALIZATION_PENDING_FRESH_RELOAD_MAPCHECK_AND_REAL_PIE"
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        report["completed_utc"] = now()
        write_json_exclusive(RESULT, report)
        schedule_exit()


main()
