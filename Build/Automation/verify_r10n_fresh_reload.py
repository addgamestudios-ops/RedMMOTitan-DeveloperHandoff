"""Fresh-reload, exact-binding, MapCheck verifier for RedMMO R10N."""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
HOME_MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
HOME_FILE = PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
EXPECTED_HOME = "A0F4FECBAAB38CCC40D5B667706D72E8402C2312EB523AAB28CD4C1F1A26C665"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_HomePresentation_R10N_20260802_181848")
BUILD = DIAG / "build_r10n_spawn_grass_ground_smoothing_result.json"
RESULT = DIAG / "verify_r10n_fresh_reload_result.json"
PROFILE = PROJECT / r"Config\RedMMO\PPGStylizedFoliageProfiles\HomeWorld_Presentation_R10N.json"

SOURCE_ROOT = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10M"
SOURCE_FOLIAGE = SOURCE_ROOT + "/Profiles/DA_PPG_HomeWorld_StylizedForest_R10M"
SOURCE_SURFACE_PARENT = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10L/Materials/M_PPG_Home_PaintedLeafGround_R10L"
ROOT = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N"
PLANET = ROOT + "/DA_PPG_HomeWorld_StylizedBinding_R10N"
FOLIAGE = ROOT + "/Profiles/DA_PPG_HomeWorld_StylizedForest_R10N"
SURFACE = ROOT + "/Materials/MI_PPG_Home_PaintedLeafGround_Scaled_R10N"
GENERATION = ROOT + "/Materials/M_PPG_Generation_SmoothSpawnGrass_R10N"
GRASS_MIS = [
    ROOT + "/Materials/MI_GrassChunks_DenseTall_A_R10N",
    ROOT + "/Materials/MI_GrassChunks_DenseTall_B_R10N",
]
GRASS_MESHES = [
    ROOT + "/Meshes/SM_GrassChunk_DenseTall_A_R10N",
    ROOT + "/Meshes/SM_GrassChunk_DenseTall_B_R10N",
]

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


def load(path, class_name=None):
    asset = unreal.EditorAssetLibrary.load_asset(path)
    require(asset is not None, "Missing asset: " + path)
    if class_name:
        require(asset.get_class().get_name() == class_name, "Class mismatch: " + path)
    return asset


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
        records.append({"port": port, "closed": code != 0})
    require(all(item["closed"] for item in records), "Provider listener active")
    return records


def command_log():
    text = str(unreal.SystemLibrary.get_command_line())
    match = re.search(r'(?i)-abslog=(?:"([^"]+)"|(\S+))', text)
    return (match.group(1) or match.group(2)) if match else str(PROJECT / "Saved/Logs/RedMMO.log")


def map_check(world):
    path = command_log()
    require(os.path.isfile(path), "Verifier log missing")
    offset = os.path.getsize(path)
    unreal.SystemLibrary.execute_console_command(world, "MAP CHECKDEP NOCLEARLOG")
    pattern = re.compile(r"MapCheck: Map check complete: (\d+) Error\(s\), (\d+) Warning\(s\)")
    matches = []
    for _ in range(120):
        time.sleep(0.1)
        with open(path, "rb") as stream:
            stream.seek(min(offset, os.path.getsize(path)))
            matches = pattern.findall(stream.read().decode("utf-8", errors="replace"))
        if matches:
            break
    require(matches, "No fresh MapCheck marker")
    errors, warnings = (int(value) for value in matches[-1])
    require(errors == 0 and warnings == 0, "MapCheck failed: {}/{}".format(errors, warnings))
    return {"errors": errors, "warnings": warnings, "log": path}


def expression_desc(node):
    try:
        return str(node.get_editor_property("desc"))
    except Exception:
        return ""


def input_names(node):
    return [str(value) for value in unreal.MaterialEditingLibrary.get_material_expression_input_names(node)]


def resolved_input(material, node, input_name):
    names = input_names(node)
    sources = list(unreal.MaterialEditingLibrary.get_inputs_for_material_expression(material, node))
    require(len(names) == len(sources), "Input/source drift on " + node.get_name())
    return sources[names.index(input_name)]


def scalar_default(material, parameter_name):
    matches = []
    for node in unreal.MaterialEditingLibrary.get_material_expressions(material):
        if node.get_class().get_name() != "MaterialExpressionScalarParameter":
            continue
        if str(node.get_editor_property("parameter_name")) == parameter_name:
            matches.append(node)
    require(len(matches) == 1, "Expected one scalar parameter: " + parameter_name)
    return float(matches[0].get_editor_property("default_value"))


def verify_generation_graph(material):
    nodes = list(unreal.MaterialEditingLibrary.get_material_expressions(material))
    sources = sorted(
        [node for node in nodes if expression_desc(node) == "R05 read original G density"],
        key=lambda item: item.get_name(),
    )
    destinations = sorted(
        [node for node in nodes if expression_desc(node) == "R05 BA: inverted-grass B, rock Outside A"],
        key=lambda item: item.get_name(),
    )
    require(len(sources) == 3 and len(destinations) == 3, "R10N generation graph signature drift")
    restored = []
    for destination in destinations:
        source = resolved_input(material, destination, "A")
        require(source in sources, "Spawn grass input is not restored OriginalG")
        restored.append({"destination": destination.get_name(), "source": source.get_name()})
    return restored


_EXIT = {"handle": None}


def schedule_exit(delay):
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
        "schema": "redmmo.ppg_home_presentation.r10n.reload_verify.v1",
        "status": "RUNNING",
        "started_utc": now(),
    }
    ok = False
    try:
        require(HOME_FILE.is_file() and sha256(HOME_FILE) == EXPECTED_HOME, "R10N home hash drift")
        build = json.loads(BUILD.read_text(encoding="utf-8"))
        require(
            build.get("status") == "PASS_STATIC_SERIALIZATION_PENDING_FRESH_RELOAD_MAPCHECK_AND_REAL_PIE"
            and build.get("home_map_sha256_after") == EXPECTED_HOME,
            "R10N build evidence drift",
        )
        require(len(build.get("created_assets", [])) == 8, "R10N created-asset count drift")
        for path, expected in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected, "Protected drift: " + str(path))
        for path, expected in SOURCE_HASHES.items():
            require(path.is_file() and sha256(path) == expected, "Source drift: " + str(path))
        report["provider_gate"] = provider_gate()
        require(not dirty_packages(), "Verifier started dirty")

        world = unreal.EditorLoadingAndSavingUtils.load_map(HOME_MAP)
        require(world is not None and not dirty_packages(), "Fresh map load failed/dirtied packages")
        actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
        labels = sorted(actor.get_actor_label() for actor in actors)
        require(labels == build["map"]["actor_labels"], "Actor inventory drift")
        spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        require(len(spawners) == 1, "Expected one PlanetSpawnerBP_C")
        spawner = spawners[0]
        require(asset_path(spawner.get_editor_property("planet_data")) == PLANET, "Planet binding drift")
        require(int(spawner.get_editor_property("max_foliage_instances_per_chunk")) == 100000, "Foliage cap drift")
        player_starts = [actor for actor in actors if actor.get_class().get_name() == "PlayerStart"]
        require(len(player_starts) == 1, "Expected one PlayerStart")
        player_start = player_starts[0].get_actor_location()
        expected_start = build["map"]["player_start_location"]
        actual_start = [player_start.x, player_start.y, player_start.z]
        require(
            all(abs(float(actual_start[index]) - float(expected_start[index])) <= 0.01 for index in range(3)),
            "PlayerStart location drift",
        )

        planet = load(PLANET, "PlanetData")
        require(int(planet.get_editor_property("generation_seed")) == 1337, "Seed drift")
        require(abs(float(planet.get_editor_property("planet_radius")) - 300000000.0) <= 0.01, "Radius drift")
        require(abs(float(planet.get_editor_property("noise_height")) - 600000.0) <= 0.01, "Noise height drift")
        require(asset_path(planet.get_editor_property("generation_material")) == GENERATION, "Generation binding drift")
        require(asset_path(planet.get_editor_property("planet_material")) == SURFACE, "Surface binding drift")
        biome_foliage = []
        for biome in list(planet.get_editor_property("biome_data")):
            for key, value in biome.to_dict().items():
                if str(key).replace("_", "").lower() in ("foliagedata", "forestfoliagedata"):
                    biome_foliage.append(asset_path(value))
        require(biome_foliage.count(FOLIAGE) == 3, "R10N foliage is not bound to all three biomes")

        generation = load(GENERATION, "Material")
        terrain_controls = {
            "HillsDetails": scalar_default(generation, "HillsDetails"),
            "MountainDetails": scalar_default(generation, "MountainDetails"),
        }
        require(abs(terrain_controls["HillsDetails"] - 200.0) <= 1e-5, "HillsDetails drift")
        require(abs(terrain_controls["MountainDetails"] - 100.0) <= 1e-5, "MountainDetails drift")
        restored_graph = verify_generation_graph(generation)

        foliage = load(FOLIAGE, "FoliageData")
        source_foliage = load(SOURCE_FOLIAGE, "FoliageData")
        entries = list(foliage.get_editor_property("foliage_list"))
        source_entries = list(source_foliage.get_editor_property("foliage_list"))
        require(len(entries) == 3 and len(source_entries) == 3, "Foliage structure drift")
        grass = entries[1]
        grass_bindings = [asset_path(item.get_editor_property("mesh")) for item in grass.get_editor_property("meshes")]
        require(grass_bindings == GRASS_MESHES, "Grass mesh binding drift")
        for index in (0, 2):
            current = [asset_path(item.get_editor_property("mesh")) for item in entries[index].get_editor_property("meshes")]
            source = [asset_path(item.get_editor_property("mesh")) for item in source_entries[index].get_editor_property("meshes")]
            require(current == source, "Non-grass foliage changed")
        scale = grass.get_editor_property("scale")
        grass_state = {
            "density": float(grass.get_editor_property("foliage_density")),
            "scale": [float(scale.get_editor_property("min")), float(scale.get_editor_property("max"))],
            "max_slope_degrees": float(grass.get_editor_property("max_slope")),
            "bindings": grass_bindings,
        }
        require(abs(grass_state["density"] - 180.0) <= 1e-5, "Grass density drift")
        require(abs(grass_state["scale"][0] - 1.0) <= 1e-5 and abs(grass_state["scale"][1] - 1.55) <= 1e-5, "Grass scale drift")
        require(abs(grass_state["max_slope_degrees"] - 30.0) <= 1e-5, "Grass slope drift")

        editing = unreal.MaterialEditingLibrary
        grass_materials = []
        for mesh_path, material_path in zip(GRASS_MESHES, GRASS_MIS):
            mesh = load(mesh_path, "StaticMesh")
            require(asset_path(mesh.get_material(0)) == material_path, "Grass material binding drift")
            instance = load(material_path, "MaterialInstanceConstant")
            values = {
                "asset": material_path,
                "local_scale": float(editing.get_material_instance_scalar_parameter_value(instance, "LocalScale_Multiply")),
                "local_z_scale": float(editing.get_material_instance_scalar_parameter_value(instance, "GrassLocalZ_ScaleMultiply")),
                "highlight_amount": float(editing.get_material_instance_scalar_parameter_value(instance, "GrassHighlights_Amount")),
                "highlight_density": float(editing.get_material_instance_scalar_parameter_value(instance, "GrassHighlights_Density")),
                "highlight_gradient_contrast": float(editing.get_material_instance_scalar_parameter_value(instance, "GrassHighlights_Gradient_Contrast")),
            }
            require(abs(values["local_scale"] - 1.30) <= 1e-5, "Grass LocalScale drift")
            require(abs(values["local_z_scale"] - 1.45) <= 1e-5, "Grass LocalZ drift")
            require(abs(values["highlight_amount"] - 0.62) <= 1e-5, "Grass highlight amount drift")
            require(abs(values["highlight_density"] - 0.82) <= 1e-5, "Grass highlight density drift")
            require(abs(values["highlight_gradient_contrast"] - 4.20) <= 1e-5, "Grass highlight contrast drift")
            grass_materials.append(values)

        surface = load(SURFACE, "MaterialInstanceConstant")
        require(asset_path(surface.get_editor_property("parent")) == SOURCE_SURFACE_PARENT, "Surface parent drift")
        ground = {
            name: float(editing.get_material_instance_scalar_parameter_value(surface, name))
            for name in ("R10L_GroundUVScale", "R10L_MacroUVScaleA", "R10L_MacroUVScaleB", "R10L_NormalAmount")
        }
        require(abs(ground["R10L_GroundUVScale"] - 12.0) <= 1e-5, "Ground UV drift")
        require(abs(ground["R10L_MacroUVScaleA"] - 1.0) <= 1e-5, "Ground macro A drift")
        require(abs(ground["R10L_MacroUVScaleB"] - 2.0) <= 1e-5, "Ground macro B drift")
        require(abs(ground["R10L_NormalAmount"] - 0.20) <= 1e-5, "Ground normal drift")

        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        require(
            profile.get("revision") == "R10N_actual_spawn_grass_scaled_painted_ground_smoothed_fine_relief"
            and profile.get("terrain", {}).get("broad_shape_controls_changed") is False,
            "R10N profile drift",
        )
        check = map_check(world)
        require(not dirty_packages() and sha256(HOME_FILE) == EXPECTED_HOME, "Verifier changed project state")
        for asset, expected in build.get("project_owned_hashes", {}).items():
            file_path = PROJECT / ("Content" + asset.removeprefix("/Game").replace("/", os.sep) + ".uasset")
            require(file_path.is_file() and sha256(file_path) == expected, "R10N asset hash drift: " + asset)
        for path, expected in SOURCE_HASHES.items():
            require(sha256(path) == expected, "Verifier changed source: " + str(path))
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "Verifier changed protected: " + str(path))

        report.update(
            {
                "status": "PASS_FRESH_RELOAD_AND_MAPCHECK_PENDING_ACTUAL_PLAYERSTART_REAL_PIE",
                "completed_utc": now(),
                "home_map_sha256": EXPECTED_HOME,
                "actor_labels": labels,
                "player_start_location": actual_start,
                "terrain_identity": {"seed": 1337, "radius_cm": 300000000.0},
                "terrain_controls": terrain_controls,
                "spawn_grass_graph": restored_graph,
                "grass": grass_state,
                "grass_materials": grass_materials,
                "ground_scalars": ground,
                "map_check": check,
                "profile_sha256": sha256(PROFILE),
                "real_gpu_verified": False,
            }
        )
        with RESULT.open("xb") as stream:
            stream.write((json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        ok = True
    except Exception as exc:
        report.update({"status": "FAIL", "completed_utc": now(), "error": str(exc), "traceback": traceback.format_exc()})
        if not RESULT.exists():
            with RESULT.open("xb") as stream:
                stream.write((json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
        raise
    finally:
        schedule_exit(10.0 if ok else 2.0)


main()
