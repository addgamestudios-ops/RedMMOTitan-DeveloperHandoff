"""Create ProfileV1-owned surface parent and tag only proven graph identities.

The transaction never loads or saves a map and does not alter any runtime
control value. It duplicates the existing project-owned R15 surface parent,
reparents the ProfileV1 material instance, and writes editor-only descriptions
onto exact existing nodes whose semantic identity is already proven.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
PROJECT_FILE = PROJECT / "RedMMO.uproject"
HOME_FILE = PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
EXPECTED_HOME = "0AB96B91A1F42042C878DC1822E3BB6D6C14DD0D5F3693D2FCD6492819D7EA75"

DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1GraphIdentity_20260805_0405")
RESULT = DIAG / "build_redmmo_ppg_profile_v1_graph_identity_result.json"
ROLLBACK = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeRedPPGProfileV1GraphIdentity_20260805T0405Z")

ROOT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1"
PLANET = ROOT + "/DA_PPG_ProfileV1_PlanetData"
GENERATION = ROOT + "/M_PPG_ProfileV1_Generation"
MASK = ROOT + "/M_PPG_ProfileV1_BiomeMask"
SURFACE_MI = ROOT + "/MI_PPG_ProfileV1_Surface"
SURFACE_PARENT = ROOT + "/M_PPG_ProfileV1_SurfaceParent"
SOURCE_SURFACE_PARENT = "/Game/RedMMO/World/PPG/HomeWorld/ContinentBiome/R15/Materials/M_PPG_Home_BiomeSurface_R15"

EXPECTED_HASHES = {
    PLANET: "5C50D50A8955C1E5F4270BDD4E53D1214C941725157B76422CD72B748978B837",
    GENERATION: "7414FB332551219CC51A3EA4B530E10AF0987252C3FFD2EB4FDBB8AF0BC0476E",
    MASK: "8AF61A4497705494BE42A7EAC3332A19FFC1661146145BC9BF2A9E15E7CFB49D",
    SURFACE_MI: "AD32E640D9A2EF73F58360914599AAD782C65B234795623EA67E9DCCD54E49D4",
    SOURCE_SURFACE_PARENT: "BAE8D5DFC16E342D6AB679475DDDDB6478A03DE0DC51C5DE587A3EBF17174227",
}

PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}

TAGS = {
    "generation_output": "RedProfile.ElevationOutput",
    "mask_output": "RedProfile.BiomeMaskOutput",
    "continental_noise": "RedProfile.ContinentalNoise",
    "surface_output": "RedProfile.PresentationRoles;Order=Craters,Mountains,Desert,Hills,Poles,Ocean",
    "OceanHeight": "RedProfile.Relief.Ocean.HeightScale",
    "OceanOffset": "RedProfile.Relief.Ocean.HeightBias",
    "PolesHeight": "RedProfile.Relief.Poles.HeightScale",
    "PolesOffset": "RedProfile.Relief.Poles.HeightBias",
    "HIllsHeight": "RedProfile.Relief.Hills.HeightScaleOnly",
    "MountainsHeight": "RedProfile.Relief.Mountains.HeightScaleOnly",
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


def asset_file(path):
    require(path.startswith("/Game/"), "Unexpected project path: " + path)
    return PROJECT / ("Content" + path.removeprefix("/Game").replace("/", os.sep) + ".uasset")


def dirty_packages():
    values = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    values += list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted({asset_path(value) for value in values})


def write_json_exclusive(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def provider_gate():
    records = []
    for port in (5353, 8000, 8765, 11111):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.25)
        try:
            code = sock.connect_ex(("127.0.0.1", port))
        finally:
            sock.close()
        records.append({"port": port, "closed": code != 0, "connect_ex": code})
    require(all(record["closed"] for record in records), "Provider/MCP listener active")
    return records


def load(path, expected_class=None):
    asset = unreal.EditorAssetLibrary.load_asset(path)
    require(asset is not None, "Missing asset: " + path)
    if expected_class:
        require(asset.get_class().get_name() == expected_class, "Class mismatch: " + path)
    return asset


def expression_map(material):
    return {
        node.get_name(): node
        for node in unreal.MaterialEditingLibrary.get_material_expressions(material)
    }


def unique_parameter(nodes, parameter_name):
    matches = [
        node for node in nodes.values()
        if node.get_class().get_name() == "MaterialExpressionScalarParameter"
        and str(node.get_editor_property("parameter_name")) == parameter_name
    ]
    require(len(matches) == 1, "Expected one scalar parameter: " + parameter_name)
    return matches[0]


def require_empty_desc(node, identity):
    current = str(node.get_editor_property("desc"))
    require(current in ("", identity), "Refusing to replace existing node description on " + node.get_name())


def set_tag(node, identity):
    require_empty_desc(node, identity)
    node.set_editor_property("desc", identity)
    require(str(node.get_editor_property("desc")) == identity, "Tag write failed: " + identity)


def snapshot_rollback():
    require(not ROLLBACK.exists(), "Rollback no-clobber failed")
    ROLLBACK.mkdir(parents=True, exist_ok=False)
    copies = []
    for asset, expected_hash in EXPECTED_HASHES.items():
        source = asset_file(asset)
        require(source.is_file() and sha256(source) == expected_hash, "Preimage hash drift: " + asset)
        destination = ROLLBACK / (asset.rsplit("/", 1)[-1] + ".uasset")
        shutil.copy2(source, destination)
        require(sha256(destination) == expected_hash, "Rollback copy mismatch: " + asset)
        copies.append({"asset": asset, "sha256": expected_hash, "rollback": str(destination)})
    manifest = {
        "schema": "redmmo.ppg_profile_v1.graph_identity.rollback.v1",
        "captured_utc": now(),
        "copied_preimages": copies,
        "new_surface_parent_existed_before": False,
        "restore": "Close Unreal; restore ProfileV1 generation, mask, and surface-instance preimages; delete M_PPG_ProfileV1_SurfaceParent. PlanetData and source R15 parent are unchanged.",
    }
    write_json_exclusive(ROLLBACK / "manifest.json", manifest)
    return manifest


_EXIT = {"handle": None}


def schedule_exit(delay=8.0):
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
        "schema": "redmmo.ppg_profile_v1.graph_identity.build.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "editor_automation_persisted_assets_no_map_change",
    }
    created = []
    try:
        active = os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path())))
        expected = os.path.normcase(os.path.abspath(str(PROJECT_FILE)))
        require(active == expected, "Active project mismatch")
        require(not RESULT.exists(), "Result no-clobber failed")
        require(HOME_FILE.is_file() and sha256(HOME_FILE) == EXPECTED_HOME, "Home map hash drift")
        require(not dirty_packages(), "Dirty packages before graph-identity build")
        report["provider_gate"] = provider_gate()
        for path, expected_hash in EXPECTED_HASHES.items():
            require(asset_file(path).is_file() and sha256(asset_file(path)) == expected_hash, "Asset hash drift: " + path)
        for path, expected_hash in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected_hash, "Protected hash drift: " + str(path))
        require(not unreal.EditorAssetLibrary.does_asset_exist(SURFACE_PARENT), "Target surface parent exists")
        require(not asset_file(SURFACE_PARENT).exists(), "Target surface parent file exists")
        report["rollback"] = snapshot_rollback()

        planet = load(PLANET, "PlanetData")
        generation = load(GENERATION, "Material")
        mask = load(MASK, "Material")
        surface_mi = load(SURFACE_MI, "MaterialInstanceConstant")
        source_parent = load(SOURCE_SURFACE_PARENT, "Material")
        require(asset_path(surface_mi.get_editor_property("parent")) == SOURCE_SURFACE_PARENT, "Surface MI parent drift")
        require(asset_path(planet.get_editor_property("planet_material")) == SURFACE_MI, "PlanetData surface binding drift")

        generation_nodes = expression_map(generation)
        mask_nodes = expression_map(mask)
        elevation = generation_nodes.get("MaterialExpressionPlanetElevationOutput_0")
        mask_output = mask_nodes.get("MaterialExpressionPlanetBiomeMaskOutput_0")
        continental = mask_nodes.get("MaterialExpressionPlanetNoise_3")
        require(elevation is not None and elevation.get_class().get_name() == "MaterialExpressionPlanetElevationOutput", "Elevation output signature drift")
        require(mask_output is not None and mask_output.get_class().get_name() == "MaterialExpressionPlanetBiomeMaskOutput", "Biome mask output signature drift")
        require(continental is not None and continental.get_class().get_name() == "MaterialExpressionPlanetNoise", "Continental noise signature drift")
        require(abs(float(continental.get_editor_property("base_frequency")) - 0.75) <= 0.0001, "Continental noise frequency drift")
        require(int(continental.get_editor_property("octaves")) == 3, "Continental noise octave drift")

        tagged = []
        for node, identity in (
            (elevation, TAGS["generation_output"]),
            (mask_output, TAGS["mask_output"]),
            (continental, TAGS["continental_noise"]),
        ):
            set_tag(node, identity)
            tagged.append({"asset": asset_path(node.get_outer()), "node": node.get_name(), "identity": identity})
        for parameter_name in ("OceanHeight", "OceanOffset", "PolesHeight", "PolesOffset", "HIllsHeight", "MountainsHeight"):
            node = unique_parameter(generation_nodes, parameter_name)
            set_tag(node, TAGS[parameter_name])
            tagged.append({"asset": GENERATION, "node": node.get_name(), "parameter": parameter_name, "identity": TAGS[parameter_name]})

        surface_parent = unreal.EditorAssetLibrary.duplicate_asset(SOURCE_SURFACE_PARENT, SURFACE_PARENT)
        require(surface_parent is not None and surface_parent.get_class().get_name() == "Material", "Surface parent duplicate failed")
        created.append(SURFACE_PARENT)
        surface_nodes = expression_map(surface_parent)
        surface_outputs = [
            node for node in surface_nodes.values()
            if node.get_class().get_name() == "MaterialExpressionPlanetBiomeMaterialOutput"
        ]
        require(len(surface_outputs) == 1, "Expected one surface biome output")
        surface_output = surface_outputs[0]
        surface_names = [str(value) for value in list(surface_output.get_editor_property("biome_names"))]
        require(surface_names == ["Craters", "Mountains", "Desert", "Hills", "Poles", "Ocean"], "Surface biome order drift")
        set_tag(surface_output, TAGS["surface_output"])
        tagged.append({"asset": SURFACE_PARENT, "node": surface_output.get_name(), "identity": TAGS["surface_output"], "biome_names": surface_names})

        unreal.MaterialEditingLibrary.set_material_instance_parent(surface_mi, surface_parent)
        require(asset_path(surface_mi.get_editor_property("parent")) == SURFACE_PARENT, "Surface MI reparent failed")

        for asset in (generation, mask, surface_parent, surface_mi):
            require(unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False), "Save failed: " + asset_path(asset))
        require(not dirty_packages(), "Dirty packages remain after graph-identity save")
        require(asset_path(planet.get_editor_property("planet_material")) == SURFACE_MI, "PlanetData surface binding changed")
        require(sha256(asset_file(PLANET)) == EXPECTED_HASHES[PLANET], "PlanetData package changed")
        require(sha256(asset_file(SOURCE_SURFACE_PARENT)) == EXPECTED_HASHES[SOURCE_SURFACE_PARENT], "Source surface parent changed")
        require(sha256(HOME_FILE) == EXPECTED_HOME, "Home map changed")
        for path, expected_hash in PROTECTED.items():
            require(sha256(path) == expected_hash, "Protected file changed: " + str(path))

        report.update({
            "status": "PASS_PROFILE_V1_OWNED_SURFACE_PARENT_AND_EXACT_TAGS_PERSISTED_UNBOUND",
            "created_packages": created,
            "modified_packages": [GENERATION, MASK, SURFACE_MI],
            "unchanged_packages": [PLANET, SOURCE_SURFACE_PARENT],
            "surface_instance_parent_before": SOURCE_SURFACE_PARENT,
            "surface_instance_parent_after": SURFACE_PARENT,
            "tagged_nodes": tagged,
            "target_hashes": {
                asset: sha256(asset_file(asset))
                for asset in (PLANET, GENERATION, MASK, SURFACE_MI, SURFACE_PARENT)
            },
            "home_map_sha256_before_after": EXPECTED_HOME,
            "home_map_loaded": False,
            "home_map_saved": False,
            "runtime_values_changed": False,
            "shader_connections_changed": False,
            "planet_data_binding_changed": False,
            "remaining_unresolved": [
                "DetailNoise exact graph target",
                "Craters HeightScale and HeightBias",
                "Hills HeightBias",
                "Mountains HeightBias",
                "Desert HeightScale and HeightBias",
                "ShorelineFlattenThreshold connected control",
                "per-role surface branch asset selection",
            ],
            "dirty_packages_after": dirty_packages(),
            "next_safe_action": "Fresh-process reload the five ProfileV1 packages and verify parent/tag persistence with zero dirty packages; do not bind or regenerate the home map.",
        })
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
        report["created_packages"] = created
        report["rollback_required"] = True
    finally:
        report["completed_utc"] = now()
        write_json_exclusive(RESULT, report)
        unreal.log("REDMMO_PPG_PROFILE_V1_GRAPH_IDENTITY " + report["status"])
        schedule_exit()


main()
