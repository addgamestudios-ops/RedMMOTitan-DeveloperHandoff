"""Read-only R79 audit of the active PPG sea-datum material capability.

This slice proves whether the installed PPG implementation already binds a
deterministic, seed-derived sea datum to generated terrain materials and
whether the current project-owned R73 surface graph exposes it.  It changes
no asset, map, seed, topology, placement rule, or vendor source file.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject")
CONTENT = PROJECT.parent / "Content"
HOME_FILE = CONTENT / r"RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
PROFILE_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
GENERATION_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\M_PPG_ProfileV1_Generation.uasset"
SURFACE_PARENT_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\M_PPG_ProfileV1_BiomePresentation_R73.uasset"
SURFACE_MI_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\MI_PPG_ProfileV1_BiomePresentation_R73.uasset"
WATER_PARENT_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\M_PPG_ProfileV1_OasisWater_R78.uasset"
WATER_MI_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\MI_PPG_ProfileV1_OasisWater_R78.uasset"
PROTECTED_TEST = Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap")
PROTECTED_FUSED = Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap")

PLUGIN = Path(r"D:\UE_5.8\Engine\Plugins\Marketplace\Procedur890d9e860517V2")
GENERATION_USF = PLUGIN / r"Shaders\GenerationUtilities.usf"
CHUNK_CPP = PLUGIN / r"Source\PPG\Private\ChunkObject.cpp"
SAMPLE_CPP = PLUGIN / r"Source\PPG\Private\MaterialExpressionPlanetBiomeMapSample.cpp"
SAMPLE_H = PLUGIN / r"Source\PPG\Public\MaterialExpressionPlanetBiomeMapSample.h"
OUTPUT_CPP = PLUGIN / r"Source\PPG\Private\MaterialExpressionPlanetBiomeMaterialOutput.cpp"

DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_ProfileV1SeaDatum_R79_20260806T0147Z")
RESULT = DIAG / "result.json"

ROOT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1"
PROFILE = ROOT + "/DA_PPG_ProfileV1_PlanetData"
GENERATION = ROOT + "/M_PPG_ProfileV1_Generation"
SURFACE_PARENT = ROOT + "/Materials/M_PPG_ProfileV1_BiomePresentation_R73"
SURFACE_MI = ROOT + "/Materials/MI_PPG_ProfileV1_BiomePresentation_R73"
WATER_MI = ROOT + "/Materials/MI_PPG_ProfileV1_OasisWater_R78"

EXPECTED = {
    PROJECT: "3BF3D8D1D1C7F892A2CD4873F7C0390EC1AF3CA8F77E60549169563D18DBF86F",
    HOME_FILE: "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3",
    PROFILE_FILE: "AA3B15F4538145C6B51B589D6B8F3E40899ACC136F573101E86C5790783E22C2",
    GENERATION_FILE: "5165A27F0423735256EEE768739CE9547FEF7849BCA05540AAD63DF5BA1D96E3",
    SURFACE_PARENT_FILE: "8D33435C91E0FE4813D5077991EDC6990AD5257395F67D6F5FDACBCE4F260992",
    SURFACE_MI_FILE: "17C83A43FCB0AB9B22AC7EF499D53A8B7B2435B3F709CA585374E64F48371E91",
    WATER_PARENT_FILE: "B815972272713EDEC40A6CF33591E2FEF05F54D575C6049B29983330D23022F1",
    WATER_MI_FILE: "2D3DFCC7583CABBCC551DD7D08A2CF5E33CC19465D14EAB5C4308DEC018DAE9A",
    PROTECTED_TEST: "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    PROTECTED_FUSED: "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
    GENERATION_USF: "95A81B360982B54EAA48DC0E1828B2915DC03142BF5BD5284C3BE4061AE87171",
    CHUNK_CPP: "BAAAB0CD184A10800E71D30ACCE6C918FC280D4632E9EC718ED73F5BFF61FE2A",
    SAMPLE_CPP: "126DAE8111F7B1BC72654DF858E984393650DF87EFCC60B34199437008345FED",
    SAMPLE_H: "39BDC3E5ABE02D96BD11930C619D5D4CC9E7B1F26F1CB12D7D0D85BFA36DF35C",
    OUTPUT_CPP: "CE95922DC0E55DE14A2BDEED83B63D74D70CCE62D3A79DEE4D00E001D5A9832F",
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def write_json_exclusive(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def asset_path(value):
    if value is None:
        return None
    getter = getattr(value, "get_path_name", None)
    if not callable(getter):
        return str(value)
    path = getter().split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def dirty_packages():
    values = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    values += list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted({asset_path(value) for value in values})


def provider_gate():
    records = []
    for port in (11111, 5353, 8000, 8765):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.2)
        try:
            code = probe.connect_ex(("127.0.0.1", port))
        finally:
            probe.close()
        records.append({"port": port, "closed": code != 0, "connect_ex": code})
    require(all(item["closed"] for item in records), "provider listener active")
    return records


def load(path, class_name):
    value = unreal.EditorAssetLibrary.load_asset(path)
    require(value is not None and value.get_class().get_name() == class_name, "load failed: " + path)
    return value


def safe_property(obj, name):
    try:
        value = obj.get_editor_property(name)
    except Exception:
        return None
    if hasattr(value, "get_path_name"):
        return asset_path(value)
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def input_sources(material, node):
    editing = unreal.MaterialEditingLibrary
    names = [str(item) for item in editing.get_material_expression_input_names(node)]
    sources = list(editing.get_inputs_for_material_expression(material, node))
    require(len(names) == len(sources), "input reflection mismatch: " + node.get_name())
    return {name: (source.get_name() if source is not None else None) for name, source in zip(names, sources)}


def source_probe(path, needles):
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    matches = []
    for label, needle in needles:
        found = [index + 1 for index, line in enumerate(lines) if needle in line]
        require(found, "source token missing: {} in {}".format(label, path))
        matches.append({"label": label, "line": found[0], "text": lines[found[0] - 1].strip()})
    return {"path": str(path), "sha256": sha256(path), "matches": matches}


_EXIT = {"handle": None}


def schedule_exit(delay=5.0):
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
        "schema": "redmmo.ppg.profile_v1.sea_datum.audit.r79.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "automation_read_only_d3d12_entry",
        "map_saved": False,
        "generation_called": False,
    }
    try:
        active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(active == PROJECT.resolve(strict=True), "wrong project")
        require(not RESULT.exists(), "R79 result no-clobber failed")
        for path, expected in EXPECTED.items():
            require(path.is_file() and sha256(path) == expected, "input drift: " + str(path))
        require(not dirty_packages(), "editor started dirty")
        command = str(unreal.SystemLibrary.get_command_line()).lower()
        require("-d3d12" in command and "-renderoffscreen" in command and "-nullrhi" not in command, "renderer gate failed")
        report["provider_gate_before"] = provider_gate()

        profile = load(PROFILE, "PlanetData")
        generation = load(GENERATION, "Material")
        parent = load(SURFACE_PARENT, "Material")
        instance = load(SURFACE_MI, "MaterialInstanceConstant")
        water = load(WATER_MI, "MaterialInstanceConstant")
        require(int(profile.get_editor_property("generation_seed")) == 1337, "ProfileV1 seed drift")
        require(asset_path(profile.get_editor_property("generation_material")) == GENERATION, "generation binding drift")
        require(asset_path(profile.get_editor_property("planet_material")) == SURFACE_MI, "surface binding drift")
        require(asset_path(profile.get_editor_property("water_material")) == WATER_MI, "water binding drift")
        require(asset_path(instance.get_editor_property("parent")) == SURFACE_PARENT, "R73 MI parent drift")

        editing = unreal.MaterialEditingLibrary
        nodes = list(editing.get_material_expressions(parent))
        counts = dict(sorted(Counter(node.get_class().get_name() for node in nodes).items()))
        samples = [node for node in nodes if node.get_class().get_name() == "MaterialExpressionPlanetBiomeMapSample"]
        outputs = [node for node in nodes if node.get_class().get_name() == "MaterialExpressionPlanetBiomeMaterialOutput"]
        require(len(samples) == 1, "R73 BiomeMap sampler count drift")
        require(len(outputs) == 1, "R73 biome output count drift")
        sample = samples[0]
        output_names = [str(item) for item in editing.get_material_expression_output_names(sample)]
        require(output_names == ["Biome IDs", "Strengths"], "public BiomeMap output contract drift: " + repr(output_names))
        # The plugin expression's fixed ParameterName is intentionally not a
        # reflected UPROPERTY in Unreal Python.  The installed source probe
        # below is therefore the authoritative name check; graph reflection
        # still proves the exact custom expression class and output contract.
        parameter_name = "BiomeMap"

        described = []
        for node in nodes:
            desc = safe_property(node, "desc")
            if desc:
                described.append({"name": node.get_name(), "class": node.get_class().get_name(), "desc": desc})
        ocean_lerps = [item for item in described if item["desc"] == "R73.Ocean.SandToAqua"]
        ocean_aqua = [item for item in described if item["desc"] == "R73.Ocean.AquaColor"]
        ocean_blend = [item for item in described if item["desc"] == "R73.Ocean.AquaBlend"]
        require(len(ocean_lerps) == len(ocean_aqua) == len(ocean_blend) == 1, "R73 ocean presentation nodes drift")
        lerp_node = next(node for node in nodes if node.get_name() == ocean_lerps[0]["name"])
        lerp_inputs = input_sources(parent, lerp_node)
        require(lerp_inputs.get("Alpha") == ocean_blend[0]["name"], "R73 ocean blend is not constant parameter driven")

        scalar_names = sorted(str(item) for item in editing.get_scalar_parameter_names(instance))
        vector_names = sorted(str(item) for item in editing.get_vector_parameter_names(instance))
        texture_names = sorted(str(item) for item in editing.get_texture_parameter_names(instance))
        sea_keywords = ("shore", "beach", "wet", "submerged", "depth", "elevation", "waterline")
        named_sea_candidates = sorted(name for name in scalar_names + vector_names + texture_names if any(key in name.lower() for key in sea_keywords))

        static_sources = [
            source_probe(GENERATION_USF, [
                ("underwater_alpha_write", "clamp(terrainData.finalElevation, -1.0, 0.0) + 1.0"),
                ("biome_strength_bottom_half", "terrainData.top3BiomeStrengths,"),
            ]),
            source_probe(CHUNK_CPP, [
                ("surface_biome_map_binding", 'SetTextureParameterValue("BiomeMap", BiomeMap)'),
                ("water_height_map_binding", 'SetTextureParameterValue("HeightMap", BiomeMap)'),
                ("water_below_sea_gate", "ChunkMinHeight < 0"),
            ]),
            source_probe(SAMPLE_CPP, [
                ("fixed_biome_map_parameter", 'ParameterName = TEXT("BiomeMap")'),
                ("sample_top_half", "BiomeMap.Load(int3(int2(Coordinate), 0)).rgb"),
                ("public_biome_ids_output", 'Outputs.Add(FExpressionOutput(TEXT("Biome IDs"'),
                ("public_strengths_output", 'Outputs.Add(FExpressionOutput(TEXT("Strengths"'),
            ]),
            source_probe(SAMPLE_H, [
                ("public_expression_class", "UMaterialExpressionPlanetBiomeMapSample"),
            ]),
            source_probe(OUTPUT_CPP, [
                ("runtime_entry_map_0", 'TEXT("PPG_SurfaceBiomeEntryMap0")'),
            ]),
        ]

        report.update({
            "status": "PASS_R79_EXACT_BIOMEMAP_SEA_DATUM_AVAILABLE_ADAPTER_REQUIRED",
            "completed_utc": now(),
            "profile": PROFILE,
            "seed": 1337,
            "bindings": {"generation": GENERATION, "surface": SURFACE_MI, "water": WATER_MI},
            "hashes": {str(path): sha256(path) for path in EXPECTED},
            "surface_graph": {
                "parent": SURFACE_PARENT,
                "expression_count": len(nodes),
                "class_counts": counts,
                "biome_map_sampler": {
                    "name": sample.get_name(),
                    "parameter_name": parameter_name,
                    "parameter_name_proof": "installed_plugin_source",
                    "output_names": output_names,
                    "alpha_or_depth_output_exposed": False,
                },
                "biome_material_output": {
                    "name": outputs[0].get_name(),
                    "input_sources": input_sources(parent, outputs[0]),
                },
                "ocean_base_color": {
                    "node": ocean_lerps[0],
                    "inputs": lerp_inputs,
                    "alpha_driver": "R73_OceanAquaBlend scalar parameter",
                    "sea_datum_driven": False,
                },
                "scalar_parameters": scalar_names,
                "vector_parameters": vector_names,
                "texture_parameters": texture_names,
                "named_sea_or_beach_candidates": named_sea_candidates,
                "sea_datum_driven_controls": [],
                "candidate_classification": "Named presentation controls may affect a biome role, but none receives BiomeMap alpha because the only public sampler outputs are Biome IDs and Strengths.",
            },
            "installed_ppg_sources": static_sources,
            "capability": {
                "deterministic_sea_datum_source": "BiomeMap top-half alpha",
                "encoding": "alpha = 1.0 at/above sea; alpha = clamp(finalElevation,-1,0)+1 below sea",
                "bound_to_each_surface_mid": True,
                "existing_public_surface_output_exposes_alpha": False,
                "vendor_edit_required": False,
                "safe_project_owned_route": "Create a successor surface material with a project-owned triangle-consistent BiomeMap-alpha sampler, then derive dry/wet/submerged sand masks without changing PPG seed, topology, water geometry, foliage, or vendor assets.",
            },
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "claim_limit": "Read-only D3D12 Entry reflection plus installed-source proof only; no map/material mutation, generation, gameplay, visual acceptance, or package evidence.",
        })
        require(report["dirty_packages_after"] == [], "audit dirtied packages")
        for path, expected in EXPECTED.items():
            require(sha256(path) == expected, "post-audit drift: " + str(path))
        write_json_exclusive(RESULT, report)
        unreal.log("REDMMO_R79_SEA_DATUM_AUDIT_PASS")
    except Exception as error:
        report.update({
            "status": "FAIL_READ_ONLY",
            "completed_utc": now(),
            "error": str(error),
            "traceback": traceback.format_exc(),
            "dirty_packages_after": dirty_packages(),
        })
        if not RESULT.exists():
            write_json_exclusive(RESULT, report)
        unreal.log_error("REDMMO_R79_SEA_DATUM_AUDIT_FAIL: " + str(error))
    finally:
        schedule_exit()


main()
