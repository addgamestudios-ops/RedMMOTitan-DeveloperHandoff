"""Authenticate PPG elevation aggregation and a safe ProfileV1 flatten design.

This is a filesystem-only audit. It reads installed PPG source plus retained
ProfileV1 automation results, writes one diagnostics JSON, and changes no
Unreal package, map, plugin, or configuration file.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path


PLUGIN = Path(r"D:\UE_5.8\Engine\Plugins\Marketplace\Procedur890d9e860517V2")
ELEVATION_HEADER = PLUGIN / r"Source\PPG\Public\MaterialExpressionPlanetElevationOutput.h"
ELEVATION_CPP = PLUGIN / r"Source\PPG\Private\MaterialExpressionPlanetElevationOutput.cpp"
PLANET_SHADER = PLUGIN / r"Shaders\Planet.usf"
FLATTEN_HEADER = PLUGIN / r"Source\PPG\Public\MaterialExpressionPlanetFlattenElevation.h"
FLATTEN_CPP = PLUGIN / r"Source\PPG\Private\MaterialExpressionPlanetFlattenElevation.cpp"
NOISE_SHADER = PLUGIN / r"Shaders\NoiseLib.usf"

RELIEF_RESULT = Path(
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1ReliefPartners_20260805_0447_R02\audit_redmmo_ppg_profile_v1_relief_partners_result.json"
)
FAILED_WRITE_RESULT = Path(
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1ShorelineFlatten_20260805_0518\apply_redmmo_ppg_profile_v1_shoreline_flatten_result.json"
)
DIAG = Path(
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ProfileV1ElevationAggregationContract_20260805_0531"
)
RESULT = DIAG / "audit_redmmo_ppg_profile_v1_elevation_aggregation_contract_result.json"

RED_PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
HOME = RED_PROJECT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
GENERATION = RED_PROJECT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\M_PPG_ProfileV1_Generation.uasset"
PROTECTED = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}
EXPECTED_HOME = "0AB96B91A1F42042C878DC1822E3BB6D6C14DD0D5F3693D2FCD6492819D7EA75"
EXPECTED_GENERATION = "5CD34E415CADD6B632B2896AE51461B8E7909FCC456027FC5E5CA8CC63EF541A"

EXPECTED_INPUT_HASHES = {
    ELEVATION_HEADER: "D4569CA1055B5C1EE9154F385D2ED38A431427FD790E8273C27359BA6F58A6A5",
    ELEVATION_CPP: "0EB9AF7E05974F7022CB1F45A513DA6B9E213436834816E1112F9AAC7EA2DE2F",
    PLANET_SHADER: "4A109146711F1D0B0EB565568BA012ABBFD62202B7EC05808140C84344538EA2",
    FLATTEN_HEADER: "371F09B0035803983821ED75EEBD8312FD20BCAC458CD79563917997065EC658",
    FLATTEN_CPP: "142CCABEEF9CFF1C46B629A234D6F3AEE8CCDC0D04707C972BDCCD6D1435A5E0",
    NOISE_SHADER: "358B2E37ABE6E5E8B8C32030E36717E6D2712DD7789F95C7236562B6554F8DD4",
    RELIEF_RESULT: "52E095553D110DF21A3FF474D68F725E116D88B134328CFBD5B6E1B699E0D7AE",
    FAILED_WRITE_RESULT: "49575DB3034244F46D6AF77C0ADF27C0FCDE6EC602CA9A39420403317697ECDF",
}

ROLE_ORDER = ["Craters", "Mountains", "Desert", "Hills", "Poles", "Ocean"]


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


def require_text(text, fragment, label):
    require(fragment in text, "Missing authenticated source fragment: " + label)


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


def write_json_exclusive(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def main():
    require(not RESULT.exists(), "Result no-clobber failed")
    for path, expected in EXPECTED_INPUT_HASHES.items():
        require(path.is_file() and sha256(path) == expected, "Input hash drift: " + str(path))
    require(HOME.is_file() and sha256(HOME) == EXPECTED_HOME, "Home map hash drift")
    require(GENERATION.is_file() and sha256(GENERATION) == EXPECTED_GENERATION, "ProfileV1 generation hash drift")
    for path, expected in PROTECTED.items():
        require(path.is_file() and sha256(path) == expected, "Protected hash drift: " + str(path))

    elevation_header = ELEVATION_HEADER.read_text(encoding="utf-8")
    elevation_cpp = ELEVATION_CPP.read_text(encoding="utf-8")
    planet_shader = PLANET_SHADER.read_text(encoding="utf-8")
    flatten_header = FLATTEN_HEADER.read_text(encoding="utf-8")
    flatten_cpp = FLATTEN_CPP.read_text(encoding="utf-8")
    noise_shader = NOISE_SHADER.read_text(encoding="utf-8")

    require_text(
        elevation_header,
        "It is not added to final elevation automatically.",
        "Global Height is shared context only",
    )
    require_text(
        elevation_cpp,
        "GlobalHeight.IsConnected() ? GlobalHeight.Compile(Compiler) : Compiler->Constant(0.0f)",
        "unconnected Global Height compiles to zero",
    )
    require_text(
        elevation_cpp,
        "BiomeHeights[BiomeIndex].IsConnected()",
        "biome outputs compile independently",
    )
    require_text(
        planet_shader,
        "PPGGlobalHeight = GetPlanetTerrain1(Parameters);",
        "Global Height evaluates once into shared context",
    )
    require_text(
        planet_shader,
        "heights[cellIndex] = EvaluatePlanetBiomeHeight(",
        "each contributing biome height evaluates separately",
    )
    require_text(
        planet_shader,
        "terrainData.finalElevation = dot(biomeHeights, top4CellStrengths);",
        "final elevation is shader-side weighted aggregation",
    )
    require_text(flatten_header, "float WaterLevel = 0.0f;", "flatten water default")
    require_text(flatten_header, "float Threshold = 0.005f;", "flatten threshold default")
    require_text(
        flatten_cpp,
        "return flattenElevation(Elev, Water, Thresh);",
        "native flatten call",
    )
    require_text(
        noise_shader,
        "return lerp(waterLevel, elevation, mask);",
        "native flatten result",
    )

    relief = json.loads(RELIEF_RESULT.read_text(encoding="utf-8"))
    failed_write = json.loads(FAILED_WRITE_RESULT.read_text(encoding="utf-8"))
    require(relief["status"].startswith("PASS"), "Relief topology result not passing")
    require(list(relief["roles"].keys()) == sorted(ROLE_ORDER), "Relief role key set drift")
    require(failed_write["status"] == "FAIL", "Retained global wrapper attempt status drift")
    require(failed_write["error"] == "Global Height is unconnected", "Retained blocker drift")
    require(failed_write["save_called"] is False, "Failed attempt unexpectedly called save")
    require(failed_write["rollback_required"] is False, "Failed attempt unexpectedly requires rollback")

    wrappers = []
    for role in ROLE_ORDER:
        record = relief["roles"][role]
        expected_input = role + " Height"
        require(record["output_input"] == expected_input, "Output input drift: " + role)
        require(bool(record["branch_root"]), "Missing branch root: " + role)
        wrappers.append({
            "role": role,
            "existing_source": record["branch_root"],
            "output_input": expected_input,
            "flatten_elevation_source": record["branch_root"],
            "flatten_threshold_source": "ShorelineFlattenThreshold",
            "flatten_water_level_input": "unconnected_default_0.0",
            "flatten_output_target": expected_input,
        })

    result = {
        "schema": "redmmo.ppg_profile_v1.elevation_aggregation_contract.read_only.v1",
        "status": "PASS_PER_BIOME_NATIVE_FLATTEN_DESIGN_AUTHENTICATED_NO_WRITE",
        "started_utc": now(),
        "completed_utc": now(),
        "evidence_class": "static",
        "provider_gate": provider_gate(),
        "authenticated_inputs": {
            str(path): expected for path, expected in EXPECTED_INPUT_HASHES.items()
        },
        "native_contract": {
            "global_height": "evaluated once as GetPlanetTerrain1 and exposed through PPGGlobalHeight; it is not added to final elevation",
            "unconnected_global_height": "compiles to 0.0",
            "biome_heights": "each active biome output evaluates independently as GetPlanetTerrain2 through GetPlanetTerrain17",
            "final_aggregation": "shader-side dot(biomeHeights, top4CellStrengths)",
            "material_graph_post_blend_hook": False,
        },
        "profile_v1_graph": {
            "global_height_connected": False,
            "connected_biome_height_count": 6,
            "role_order": ROLE_ORDER,
            "existing_role_roots": {
                role: relief["roles"][role]["branch_root"] for role in ROLE_ORDER
            },
        },
        "supported_unbound_design": {
            "shared_scalar": {
                "parameter_name": "ShorelineFlattenThreshold",
                "default": 0.005,
                "identity": "RedProfile.ShorelineFlattenThreshold",
            },
            "native_flatten_node_count": 6,
            "wrappers": wrappers,
            "global_height_action": "leave unconnected",
            "preserves": [
                "six biome names and order",
                "existing branch roots and upstream values",
                "default water level zero",
                "ProfileV1 unbound state",
            ],
        },
        "behavioral_boundary": {
            "supported_order": "blend(flatten(each biome height))",
            "unsupported_exact_post_blend_order": "flatten(blend(all biome heights))",
            "nonlinear_equivalence": False,
            "transition_note": "smoothstep flatten is nonlinear, so per-biome preblend flatten can differ from post-blend flatten in biome transitions",
            "exact_post_blend_requirement": "a separately approved project-owned PPG shader/plugin extension after the final dot product",
        },
        "write_performed": False,
        "save_called": False,
        "regeneration_called": False,
        "home_map_loaded": False,
        "home_map_saved": False,
        "hash_gates": {
            "home_map_before_after": EXPECTED_HOME,
            "profile_generation_before_after": EXPECTED_GENERATION,
            "protected": {str(path): expected for path, expected in PROTECTED.items()},
        },
        "next_safe_action": "Under the retained exact rollback or a fresh equivalent, persist one shared ShorelineFlattenThreshold scalar and six native per-biome flatten wrappers in unbound ProfileV1 generation, then fresh-reload the package. Do not bind, regenerate, save the home map, capture, or claim a visible shoreline change.",
    }
    write_json_exclusive(RESULT, result)


if __name__ == "__main__":
    main()
