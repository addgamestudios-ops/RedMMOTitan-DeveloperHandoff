"""Fresh-process, read-only verification for ProfileV1 graph identities.

This script loads only the five project-owned ProfileV1 packages. It verifies
their exact hashes, internal bindings, editor-only identity descriptions, and
clean package state. It never saves an asset or map and never regenerates PPG.
"""

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
PROJECT_FILE = PROJECT / "RedMMO.uproject"
HOME_FILE = PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
EXPECTED_HOME = "0AB96B91A1F42042C878DC1822E3BB6D6C14DD0D5F3693D2FCD6492819D7EA75"

DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1GraphIdentityReload_20260805_0416")
RESULT = DIAG / "verify_redmmo_ppg_profile_v1_graph_identity_reload_result.json"

ROOT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1"
PLANET = ROOT + "/DA_PPG_ProfileV1_PlanetData"
GENERATION = ROOT + "/M_PPG_ProfileV1_Generation"
MASK = ROOT + "/M_PPG_ProfileV1_BiomeMask"
SURFACE_MI = ROOT + "/MI_PPG_ProfileV1_Surface"
SURFACE_PARENT = ROOT + "/M_PPG_ProfileV1_SurfaceParent"
SOURCE_SURFACE_PARENT = "/Game/RedMMO/World/PPG/HomeWorld/ContinentBiome/R15/Materials/M_PPG_Home_BiomeSurface_R15"

EXPECTED_HASHES = {
    PLANET: "5C50D50A8955C1E5F4270BDD4E53D1214C941725157B76422CD72B748978B837",
    GENERATION: "5CD34E415CADD6B632B2896AE51461B8E7909FCC456027FC5E5CA8CC63EF541A",
    MASK: "6A4EA303452559810E4FF805FE86AD7057D9807069B3585A8CC9489279BFA66D",
    SURFACE_MI: "FBB3A58782DEED69D93BB2369387873FA2DA7FEAA93F47CBA289FC61EBEFBD66",
    SURFACE_PARENT: "5B433BA09CCBB50EFC71A9F2C9100BF264274249A1B4AC2BE5E95126F4644768",
    SOURCE_SURFACE_PARENT: "BAE8D5DFC16E342D6AB679475DDDDB6478A03DE0DC51C5DE587A3EBF17174227",
}

PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}

EXPECTED_TAGS = {
    GENERATION: {
        "MaterialExpressionPlanetElevationOutput_0": "RedProfile.ElevationOutput",
        "OceanHeight": "RedProfile.Relief.Ocean.HeightScale",
        "OceanOffset": "RedProfile.Relief.Ocean.HeightBias",
        "PolesHeight": "RedProfile.Relief.Poles.HeightScale",
        "PolesOffset": "RedProfile.Relief.Poles.HeightBias",
        "HIllsHeight": "RedProfile.Relief.Hills.HeightScaleOnly",
        "MountainsHeight": "RedProfile.Relief.Mountains.HeightScaleOnly",
    },
    MASK: {
        "MaterialExpressionPlanetBiomeMaskOutput_0": "RedProfile.BiomeMaskOutput",
        "MaterialExpressionPlanetNoise_3": "RedProfile.ContinentalNoise",
    },
    SURFACE_PARENT: {
        "MaterialExpressionPlanetBiomeMaterialOutput_1":
            "RedProfile.PresentationRoles;Order=Craters,Mountains,Desert,Hills,Poles,Ocean",
    },
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


def load(path, expected_class):
    asset = unreal.EditorAssetLibrary.load_asset(path)
    require(asset is not None, "Missing asset: " + path)
    require(asset.get_class().get_name() == expected_class, "Class mismatch: " + path)
    return asset


def expression_map(material):
    return {
        node.get_name(): node
        for node in unreal.MaterialEditingLibrary.get_material_expressions(material)
    }


def find_parameter(nodes, parameter_name):
    matches = [
        node for node in nodes.values()
        if node.get_class().get_name() == "MaterialExpressionScalarParameter"
        and str(node.get_editor_property("parameter_name")) == parameter_name
    ]
    require(len(matches) == 1, "Expected one scalar parameter: " + parameter_name)
    return matches[0]


def verify_tag(node, identity):
    actual = str(node.get_editor_property("desc"))
    require(actual == identity, "Identity mismatch on " + node.get_name() + ": " + actual)
    return {"node": node.get_name(), "identity": actual}


_EXIT = {"handle": None}


def schedule_exit(delay=6.0):
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
        "schema": "redmmo.ppg_profile_v1.graph_identity.reload.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "editor_automation_read_only_fresh_reload",
    }
    try:
        active = os.path.normcase(os.path.abspath(str(unreal.Paths.get_project_file_path())))
        expected = os.path.normcase(os.path.abspath(str(PROJECT_FILE)))
        require(active == expected, "Active project mismatch")
        require(not RESULT.exists(), "Result no-clobber failed")
        require(HOME_FILE.is_file() and sha256(HOME_FILE) == EXPECTED_HOME, "Home map hash drift")
        require(not dirty_packages(), "Dirty packages before reload verification")
        report["provider_gate"] = provider_gate()

        for path, expected_hash in EXPECTED_HASHES.items():
            require(asset_file(path).is_file(), "Missing package: " + path)
            require(sha256(asset_file(path)) == expected_hash, "Package hash drift: " + path)
        for path, expected_hash in PROTECTED.items():
            require(path.is_file() and sha256(path) == expected_hash, "Protected hash drift: " + str(path))

        planet = load(PLANET, "PlanetData")
        generation = load(GENERATION, "Material")
        mask = load(MASK, "Material")
        surface_parent = load(SURFACE_PARENT, "Material")
        surface_mi = load(SURFACE_MI, "MaterialInstanceConstant")

        bindings = {
            "generation_material": asset_path(planet.get_editor_property("generation_material")),
            "biome_mask_material": asset_path(planet.get_editor_property("biome_mask_material")),
            "surface_material": asset_path(planet.get_editor_property("planet_material")),
            "surface_instance_parent": asset_path(surface_mi.get_editor_property("parent")),
        }
        require(bindings["generation_material"] == GENERATION, "PlanetData generation binding drift")
        require(bindings["biome_mask_material"] == MASK, "PlanetData mask binding drift")
        require(bindings["surface_material"] == SURFACE_MI, "PlanetData surface binding drift")
        require(bindings["surface_instance_parent"] == SURFACE_PARENT, "Surface parent persistence failed")

        generation_nodes = expression_map(generation)
        mask_nodes = expression_map(mask)
        surface_nodes = expression_map(surface_parent)
        verified_tags = []

        elevation = generation_nodes.get("MaterialExpressionPlanetElevationOutput_0")
        require(elevation is not None and elevation.get_class().get_name() == "MaterialExpressionPlanetElevationOutput", "Elevation output signature drift")
        verified_tags.append({"asset": GENERATION, **verify_tag(elevation, EXPECTED_TAGS[GENERATION][elevation.get_name()])})

        for parameter_name in ("OceanHeight", "OceanOffset", "PolesHeight", "PolesOffset", "HIllsHeight", "MountainsHeight"):
            node = find_parameter(generation_nodes, parameter_name)
            verified_tags.append({"asset": GENERATION, "parameter": parameter_name, **verify_tag(node, EXPECTED_TAGS[GENERATION][parameter_name])})

        mask_output = mask_nodes.get("MaterialExpressionPlanetBiomeMaskOutput_0")
        continental = mask_nodes.get("MaterialExpressionPlanetNoise_3")
        require(mask_output is not None and mask_output.get_class().get_name() == "MaterialExpressionPlanetBiomeMaskOutput", "Biome mask output signature drift")
        require(continental is not None and continental.get_class().get_name() == "MaterialExpressionPlanetNoise", "Continental noise signature drift")
        require(abs(float(continental.get_editor_property("base_frequency")) - 0.75) <= 0.0001, "Continental noise frequency drift")
        require(int(continental.get_editor_property("octaves")) == 3, "Continental noise octave drift")
        verified_tags.append({"asset": MASK, **verify_tag(mask_output, EXPECTED_TAGS[MASK][mask_output.get_name()])})
        verified_tags.append({"asset": MASK, **verify_tag(continental, EXPECTED_TAGS[MASK][continental.get_name()])})

        surface_output = surface_nodes.get("MaterialExpressionPlanetBiomeMaterialOutput_1")
        require(surface_output is not None and surface_output.get_class().get_name() == "MaterialExpressionPlanetBiomeMaterialOutput", "Surface output signature drift")
        biome_names = [str(value) for value in list(surface_output.get_editor_property("biome_names"))]
        require(biome_names == ["Craters", "Mountains", "Desert", "Hills", "Poles", "Ocean"], "Surface biome order drift")
        verified_tags.append({"asset": SURFACE_PARENT, "biome_names": biome_names, **verify_tag(surface_output, EXPECTED_TAGS[SURFACE_PARENT][surface_output.get_name()])})
        require(len(verified_tags) == 10, "Exact identity cardinality drift")

        require(not dirty_packages(), "Packages became dirty during read-only reload verification")
        require(sha256(HOME_FILE) == EXPECTED_HOME, "Home map changed")
        for path, expected_hash in EXPECTED_HASHES.items():
            require(sha256(asset_file(path)) == expected_hash, "Package changed during verification: " + path)
        for path, expected_hash in PROTECTED.items():
            require(sha256(path) == expected_hash, "Protected file changed: " + str(path))

        report.update({
            "status": "PASS_PROFILE_V1_GRAPH_IDENTITIES_FRESH_RELOAD_UNBOUND",
            "loaded_packages": [PLANET, GENERATION, MASK, SURFACE_PARENT, SURFACE_MI],
            "bindings": bindings,
            "verified_tags": verified_tags,
            "verified_tag_count": len(verified_tags),
            "package_hashes_before_after": EXPECTED_HASHES,
            "home_map_sha256_before_after": EXPECTED_HOME,
            "home_map_saved": False,
            "save_called": False,
            "regeneration_called": False,
            "planet_data_bound_to_home_map": False,
            "dirty_packages_after": dirty_packages(),
            "remaining_unresolved": [
                "DetailNoise exact graph target",
                "Craters HeightScale and HeightBias",
                "Hills HeightBias",
                "Mountains HeightBias",
                "Desert HeightScale and HeightBias",
                "ShorelineFlattenThreshold connected control",
                "per-role surface branch asset selection",
            ],
            "next_safe_action": "Under a fresh rollback, resolve one remaining exact control group without binding or regenerating the home map; prefer per-role project-owned surface branch selection because it is independent of missing relief parameters.",
        })
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        report["completed_utc"] = now()
        write_json_exclusive(RESULT, report)
        unreal.log("REDMMO_PPG_PROFILE_V1_GRAPH_IDENTITY_RELOAD " + report["status"])
        schedule_exit()


main()
