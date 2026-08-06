"""Fresh-reload, exact-binding, and MapCheck verifier for RedMMO R10O."""

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
EXPECTED_HOME = "C489B6000B359A7B52FBE7FD50A72A76232020DBC9A015DFC61CA2FB1120C46F"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_HomePresentation_R10O_20260802_183909")
BUILD = DIAG / "build_r10o_cap_safe_grass_density_result.json"
RESULT = DIAG / "verify_r10o_fresh_reload_result.json"
PROFILE = PROJECT / r"Config\RedMMO\PPGStylizedFoliageProfiles\HomeWorld_Presentation_R10O.json"

R10N = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N"
R10N_PLANET = R10N + "/DA_PPG_HomeWorld_StylizedBinding_R10N"
R10N_FOLIAGE = R10N + "/Profiles/DA_PPG_HomeWorld_StylizedForest_R10N"
GENERATION = R10N + "/Materials/M_PPG_Generation_SmoothSpawnGrass_R10N"
SURFACE = R10N + "/Materials/MI_PPG_Home_PaintedLeafGround_Scaled_R10N"
GRASS_MIS = [
    R10N + "/Materials/MI_GrassChunks_DenseTall_A_R10N",
    R10N + "/Materials/MI_GrassChunks_DenseTall_B_R10N",
]
GRASS_MESHES = [
    R10N + "/Meshes/SM_GrassChunk_DenseTall_A_R10N",
    R10N + "/Meshes/SM_GrassChunk_DenseTall_B_R10N",
]
R10O = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10O"
PLANET = R10O + "/DA_PPG_HomeWorld_StylizedBinding_R10O"
FOLIAGE = R10O + "/Profiles/DA_PPG_HomeWorld_StylizedForest_R10O"

R10N_HASHES = {
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\DA_PPG_HomeWorld_StylizedBinding_R10N.uasset": "C6544BF727A7F8865618C18220747F20150341139677688DB1AC7F902BE9D1EF",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Profiles\DA_PPG_HomeWorld_StylizedForest_R10N.uasset": "B05F83E98247ED2387E6BADEB5BBBF59484EFE0C512DBE9420ED8063ABFDBCD9",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\M_PPG_Generation_SmoothSpawnGrass_R10N.uasset": "43EA98C552B42A28C90C588A588E6B30C9C63ABE02E1E99D744D02E6D65A1FD0",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_PPG_Home_PaintedLeafGround_Scaled_R10N.uasset": "A6ED14A2C495A1F7527F9AA79CA3C317E7E0101E155C4926015CCCE5927E95DB",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_A_R10N.uasset": "6B6410611A60F382B57BA92C35B585D4954F491434680F1B6E74080A578ECCA0",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_GrassChunks_DenseTall_B_R10N.uasset": "FA3994C498C80335E2077AAF8EDD41AEF5A32C0B4E3EABA1BB02E1A10F63950B",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_A_R10N.uasset": "6F215104F1374403194D8AB4DA79B3FF16CCBF86472746E5CD433E03118B2443",
    PROJECT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_B_R10N.uasset": "3C50C87B594CE012F680EF51BA306C2DF09FDAED10C06F7F60AFA4E62F678475",
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


def scalar_default(material, parameter_name):
    matches = []
    for node in unreal.MaterialEditingLibrary.get_material_expressions(material):
        if node.get_class().get_name() == "MaterialExpressionScalarParameter" and str(node.get_editor_property("parameter_name")) == parameter_name:
            matches.append(node)
    require(len(matches) == 1, "Expected one scalar parameter: " + parameter_name)
    return float(matches[0].get_editor_property("default_value"))


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
        "schema": "redmmo.ppg_home_presentation.r10o.reload_verify.v1",
        "status": "RUNNING",
        "started_utc": now(),
    }
    ok = False
    try:
        require(HOME_FILE.is_file() and sha256(HOME_FILE) == EXPECTED_HOME, "R10O home hash drift")
        build = json.loads(BUILD.read_text(encoding="utf-8"))
        require(
            build.get("status") == "PASS_STATIC_SERIALIZATION_PENDING_FRESH_RELOAD_MAPCHECK_AND_ACTUAL_PLAYERSTART_PIE"
            and build.get("home_map_sha256_after") == EXPECTED_HOME,
            "R10O build evidence drift",
        )
        require(len(build.get("created_assets", [])) == 2, "R10O created-asset count drift")
        for path, expected in R10N_HASHES.items():
            require(path.is_file() and sha256(path) == expected, "R10N source drift: " + str(path))
        for path, expected in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected, "Protected drift: " + str(path))
        for asset, expected in build.get("project_owned_hashes", {}).items():
            file_path = PROJECT / ("Content" + asset.removeprefix("/Game").replace("/", os.sep) + ".uasset")
            require(file_path.is_file() and sha256(file_path) == expected, "R10O asset hash drift: " + asset)
        require(PROFILE.is_file() and sha256(PROFILE) == build.get("profile_sha256"), "R10O profile drift")
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
        starts = [actor for actor in actors if actor.get_class().get_name() == "PlayerStart"]
        require(len(starts) == 1, "Expected one PlayerStart")
        start = starts[0].get_actor_location()

        planet = load(PLANET, "PlanetData")
        require(int(planet.get_editor_property("generation_seed")) == 1337, "Seed drift")
        require(abs(float(planet.get_editor_property("planet_radius")) - 300000000.0) <= 0.01, "Radius drift")
        require(asset_path(planet.get_editor_property("generation_material")) == GENERATION, "Generation binding drift")
        require(asset_path(planet.get_editor_property("planet_material")) == SURFACE, "Surface binding drift")
        biome_foliage = []
        for biome in list(planet.get_editor_property("biome_data")):
            for key, value in biome.to_dict().items():
                if str(key).replace("_", "").lower() in ("foliagedata", "forestfoliagedata"):
                    biome_foliage.append(asset_path(value))
        require(biome_foliage.count(FOLIAGE) == 3, "R10O foliage is not bound to all three biomes")

        foliage = load(FOLIAGE, "FoliageData")
        source_foliage = load(R10N_FOLIAGE, "FoliageData")
        entries = list(foliage.get_editor_property("foliage_list"))
        source_entries = list(source_foliage.get_editor_property("foliage_list"))
        require(len(entries) == 3 and len(source_entries) == 3, "Foliage structure drift")
        grass = entries[1]
        scale = grass.get_editor_property("scale")
        grass_state = {
            "density": float(grass.get_editor_property("foliage_density")),
            "scale": [float(scale.get_editor_property("min")), float(scale.get_editor_property("max"))],
            "max_slope_degrees": int(grass.get_editor_property("max_slope")),
            "density_channel": str(grass.get_editor_property("density_vertex_color_channel")),
            "invert_density_mask": bool(grass.get_editor_property("invert_density_vertex_color_mask")),
            "bindings": [asset_path(item.get_editor_property("mesh")) for item in grass.get_editor_property("meshes")],
        }
        require(abs(grass_state["density"] - 90.0) <= 1.0e-5, "Grass density drift")
        require(
            abs(grass_state["scale"][0] - 1.0) <= 1.0e-5
            and abs(grass_state["scale"][1] - 1.55) <= 1.0e-5,
            "Grass scale drift",
        )
        require(grass_state["max_slope_degrees"] == 30, "Grass slope drift")
        require("blue" in grass_state["density_channel"].lower() and grass_state["invert_density_mask"], "Grass density mask drift")
        require(grass_state["bindings"] == GRASS_MESHES, "Grass bindings drift")
        for index in (0, 2):
            current = [asset_path(item.get_editor_property("mesh")) for item in entries[index].get_editor_property("meshes")]
            source = [asset_path(item.get_editor_property("mesh")) for item in source_entries[index].get_editor_property("meshes")]
            require(current == source, "Non-grass foliage binding changed")

        generation = load(GENERATION, "Material")
        terrain_controls = {
            "HillsDetails": scalar_default(generation, "HillsDetails"),
            "MountainDetails": scalar_default(generation, "MountainDetails"),
        }
        require(
            abs(terrain_controls["HillsDetails"] - 200.0) <= 1.0e-5
            and abs(terrain_controls["MountainDetails"] - 100.0) <= 1.0e-5,
            "Terrain smoothing control drift",
        )

        editing = unreal.MaterialEditingLibrary
        surface = load(SURFACE, "MaterialInstanceConstant")
        ground = {
            name: float(editing.get_material_instance_scalar_parameter_value(surface, name))
            for name in ("R10L_GroundUVScale", "R10L_MacroUVScaleA", "R10L_MacroUVScaleB", "R10L_NormalAmount")
        }
        expected_ground = {"R10L_GroundUVScale": 12.0, "R10L_MacroUVScaleA": 1.0, "R10L_MacroUVScaleB": 2.0, "R10L_NormalAmount": 0.2}
        require(all(abs(ground[key] - value) <= 1.0e-5 for key, value in expected_ground.items()), "Ground scale drift")
        grass_materials = []
        for path in GRASS_MIS:
            instance = load(path, "MaterialInstanceConstant")
            values = {
                "asset": path,
                "local_scale": float(editing.get_material_instance_scalar_parameter_value(instance, "LocalScale_Multiply")),
                "local_z_scale": float(editing.get_material_instance_scalar_parameter_value(instance, "GrassLocalZ_ScaleMultiply")),
                "highlight_amount": float(editing.get_material_instance_scalar_parameter_value(instance, "GrassHighlights_Amount")),
                "highlight_density": float(editing.get_material_instance_scalar_parameter_value(instance, "GrassHighlights_Density")),
                "highlight_contrast": float(editing.get_material_instance_scalar_parameter_value(instance, "GrassHighlights_Gradient_Contrast")),
            }
            require(abs(values["local_scale"] - 1.3) <= 1.0e-5 and abs(values["local_z_scale"] - 1.45) <= 1.0e-5, "Grass height drift")
            require(
                abs(values["highlight_amount"] - 0.62) <= 1.0e-5
                and abs(values["highlight_density"] - 0.82) <= 1.0e-5
                and abs(values["highlight_contrast"] - 4.2) <= 1.0e-5,
                "Grass highlight drift",
            )
            grass_materials.append(values)

        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        require(profile.get("revision") == "R10O_cap_headroom_candidate_dense_tall_actual_spawn_grass", "R10O profile revision drift")
        check = map_check(world)
        require(not dirty_packages() and sha256(HOME_FILE) == EXPECTED_HOME, "Verifier changed project state")
        report.update({
            "status": "PASS_FRESH_RELOAD_AND_MAPCHECK_PENDING_ACTUAL_PLAYERSTART_PIE",
            "completed_utc": now(),
            "home_map_sha256": EXPECTED_HOME,
            "actor_labels": labels,
            "player_start_location": [start.x, start.y, start.z],
            "terrain_identity": {"seed": 1337, "radius_cm": 300000000.0},
            "terrain_controls": terrain_controls,
            "grass": grass_state,
            "grass_materials": grass_materials,
            "ground_scalars": ground,
            "map_check": check,
            "real_gpu_verified": False,
        })
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
        schedule_exit(15.0 if ok else 2.0)


main()
