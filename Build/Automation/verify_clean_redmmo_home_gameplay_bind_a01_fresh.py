"""Fail-closed fresh-process readback for the A01 RedMMO home gameplay bind.

Required environment variables:

``REDMMO_HOME_BIND_A01_REPORT`` names the successful bind transaction report
below ``D:\\RedMMOTitanWindowsData\\Diagnostics``.

``REDMMO_HOME_BIND_A01_FRESH_REPORT`` names a new JSON result file below that
same Diagnostics root.  Publication is atomic and no-clobber.

This script must start on ``/Engine/Maps/Entry``.  It then loads only the real
RedMMO PPG home map, performs serialized readback plus MapCheck, and saves
nothing.  It does not run PIE and cannot establish controls, animation,
collision, ship-operation, visual, package, or multiplayer acceptance.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import unreal


PROJECT_ROOT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
PROJECT_FILE = PROJECT_ROOT / "RedMMO.uproject"
PROJECT_SHA256 = "54E664A24FA5E9129C022740EE624F84389F1825AA9A4AE07D5E99DD783F382E"
HOME_MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
HOME_FILE = PROJECT_ROOT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
HOME_SHA256_BEFORE = "1821ED915E924085A2D6B3E1A85984A0F207C116EFF32AC974E8F0B7CD217F87"
HOME_SHA256_AFTER = "1310D92641AC25DAEA4DF289A8B2C16A46F3F0D4AECB7FB9F4616FE5CEAD5209"
BIND_REPORT_SHA256 = "79CFB186136A107C7869EE5E437FBAF367698E64F3F56DDC5DA6007DA254B4AC"

BUILD_REPORT = Path(
    r"D:\RedMMOTitanWindowsData\Diagnostics"
    r"\RedMMO_TrooperAssets_A01_20260803T044000Z\build_report.json"
)
BUILD_REPORT_SHA256 = "21E20052DDAF86EA419AD0A00C9BEB3BB11EC2A34F3517608633E1D6202D19F1"
ASSET_FRESH_REPORT = Path(
    r"D:\RedMMOTitanWindowsData\Diagnostics"
    r"\RedMMO_TrooperAssets_A01_Fresh_20260803T044200Z\fresh_report.json"
)
ASSET_FRESH_REPORT_SHA256 = "18346B265845444825332E9A946BFE0AF57E3115D4A86E35499B10D01DDFD571"

SOURCE_SHIP = PROJECT_ROOT / r"Content\RedMMO\Ships\BP_RedModularStarSparrow.uasset"
SOURCE_SHIP_SHA256 = "A8A6E128C2A08AE95A745B3A70C47A372339F314C67C6CE37539A25B67DC78C9"
OLD_VISUAL_BP = PROJECT_ROOT / r"Content\RedMMO\Gameplay\World\BP_RedParkedStarSparrow_R12.uasset"
OLD_VISUAL_BP_SHA256 = "C9FDCF7D0FE89DACE39D418B79A7951C37C699C1FEA7E485C85670B2AB864BD6"
OLD_GAME_MODE_FILE = PROJECT_ROOT / r"Content\RedMMO\Gameplay\Player\GM_RedPlanet_R11.uasset"
OLD_GAME_MODE_SHA256 = "0696DE6039A5389BF0F872DB84D970E981C69184CD3AEA0279D89001B98BBEBD"
PPG_PLANET_FILE = PROJECT_ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10O\DA_PPG_HomeWorld_StylizedBinding_R10O.uasset"
PPG_PLANET_SHA256 = "7C6835CA50EBB06B4C94AA6D1E8B0419B1E0ACF09A44D5CEA5B670FBD5865C5A"
PPG_FOLIAGE_FILE = PROJECT_ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10O\Profiles\DA_PPG_HomeWorld_StylizedForest_R10O.uasset"
PPG_FOLIAGE_SHA256 = "4D7B577684CF74CBF56BCB6AF8A6867DAD130C8BACF022CF461D86A53833E18F"

PROTECTED_FILES = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen.umap"):
        "1DF9E6ED913A267875F1EF452F6ED51DAF337DBBAAE4C6EC3379EA6299346724",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Environment\DA_RED_Planet50Km_FusedHeightfield.uasset"):
        "412E26B75DAD95CE0EF4FA63BFF21CCA0EDB755B5D08BA1A4CFA3EEFEC06E562",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap"):
        "211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7",
    Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeCoastDatum_20260714\RedPlanetGen_50km_FusedPrototype.umap"):
        "A9C42C0D1B0429DD1018F00F0D2AB8A18F66C07291611964EFF5F9710F3B0C6A",
}

TRACKED_FILES = {
    SOURCE_SHIP: SOURCE_SHIP_SHA256,
    OLD_VISUAL_BP: OLD_VISUAL_BP_SHA256,
    OLD_GAME_MODE_FILE: OLD_GAME_MODE_SHA256,
    PPG_PLANET_FILE: PPG_PLANET_SHA256,
    **PROTECTED_FILES,
}

GRASS_ASSETS = {
    "/Game/StylizedRocksPack_01/Common/GrassChunks/Meshes/SM_GrassChunk_01": {
        "file": PROJECT_ROOT / r"Content\StylizedRocksPack_01\Common\GrassChunks\Meshes\SM_GrassChunk_01.uasset",
        "sha256": "294B5C257FFD2D31F192665E5A97F93E0B97E6B4D19C93D89782A338DD6AE699",
    },
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_A_R10N": {
        "file": PROJECT_ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_A_R10N.uasset",
        "sha256": "6F215104F1374403194D8AB4DA79B3FF16CCBF86472746E5CD433E03118B2443",
    },
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_B_R10N": {
        "file": PROJECT_ROOT / r"Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Meshes\SM_GrassChunk_DenseTall_B_R10N.uasset",
        "sha256": "3C50C87B594CE012F680EF51BA306C2DF09FDAED10C06F7F60AFA4E62F678475",
    },
}

ROOT = "/Game/RedMMO/Gameplay/Trooper/A01"
EXPECTED_PACKAGES = (
    ROOT + "/Input/IA_RedMove",
    ROOT + "/Input/IA_RedLook",
    ROOT + "/Input/IA_RedJump",
    ROOT + "/Input/IA_RedSprint",
    ROOT + "/Input/IA_RedFire",
    ROOT + "/Input/IA_RedADS",
    ROOT + "/Input/IA_RedInteract",
    ROOT + "/Input/IMC_RedTrooper_A01",
    ROOT + "/Input/IA_RedShipMove",
    ROOT + "/Input/IA_RedShipLook",
    ROOT + "/Input/IA_RedShipRoll",
    ROOT + "/Input/IA_RedShipBoost",
    ROOT + "/Input/IA_RedShipExit",
    ROOT + "/Input/IMC_RedShip_A01",
    ROOT + "/Combat/BP_RedBolt_Trooper_A01",
    ROOT + "/Player/BP_RedTrooperPlayer_A01",
    ROOT + "/Ship/BP_RedModularStarSparrow_Trooper_A01",
    ROOT + "/Player/GM_RedTrooperPPG_A01",
)

GAME_MODE_CLASS = ROOT + "/Player/GM_RedTrooperPPG_A01.GM_RedTrooperPPG_A01_C"
EXPECTED_OLD_GAME_MODE_CLASS = "/Game/RedMMO/Gameplay/Player/GM_RedPlanet_R11.GM_RedPlanet_R11_C"
OLD_VISUAL_LABEL = "RedMMO_R12_ParkedStarSparrow_VisualOnly"
OLD_VISUAL_CLASS = "/Game/RedMMO/Gameplay/World/BP_RedParkedStarSparrow_R12.BP_RedParkedStarSparrow_R12_C"
EXPECTED_ACTOR_COUNT = 11
PPG_SPAWNER_CLASS = "PlanetSpawnerBP_C"
PPG_PLANET = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10O/DA_PPG_HomeWorld_StylizedBinding_R10O"
PPG_FOLIAGE = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10O/Profiles/DA_PPG_HomeWorld_StylizedForest_R10O"
PPG_WATER = "/PPG/Water/Materials/M_PlanetaryOceanWater"
PPG_GRASS_BINDINGS = [
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_A_R10N",
    "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Meshes/SM_GrassChunk_DenseTall_B_R10N",
]

DIAGNOSTICS_ROOT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics")
ROLLBACK_ROOT = Path(r"D:\RedMMOTitanWindowsData\Rollback")
BIND_REPORT_ENV = "REDMMO_HOME_BIND_A01_REPORT"
FRESH_REPORT_ENV = "REDMMO_HOME_BIND_A01_FRESH_REPORT"
BIND_HOST_EXIT_ENV = "REDMMO_HOME_BIND_A01_HOST_EXIT_CODE"
PROVIDER_PORTS = (5353, 8000, 8765)
ALLOWED_WARNING = (
    "Floor_0 Large actor receives a pre-shadow and will cause an extreme "
    "performance hit unless bCastDynamicShadow is set to false."
)


class VerifyError(RuntimeError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise VerifyError(message)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def canonical_under(value: str, root: Path, must_exist: bool) -> Path:
    require(bool(value), "Required path environment variable is missing")
    path = Path(value).resolve(strict=must_exist)
    resolved_root = root.resolve(strict=True)
    require(
        os.path.commonpath([str(path), str(resolved_root)]) == str(resolved_root),
        f"Unsafe path outside {resolved_root}: {path}",
    )
    return path


def bind_report_path() -> Path:
    path = canonical_under(os.environ.get(BIND_REPORT_ENV, ""), DIAGNOSTICS_ROOT, must_exist=True)
    require(path.is_file() and path.suffix.lower() == ".json", "Bind report must be an existing JSON file")
    return path


def fresh_report_path() -> Path:
    path = canonical_under(os.environ.get(FRESH_REPORT_ENV, ""), DIAGNOSTICS_ROOT, must_exist=False)
    require(path.suffix.lower() == ".json", "Fresh report must be JSON")
    require(not os.path.lexists(path), f"Fresh report no-clobber failed: {path}")
    return path


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / ("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, default=str)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.rename(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def read_json(path: Path, label: str) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    require(isinstance(value, dict), f"{label} is not a JSON object")
    return value


def load_fixed_report(path: Path, expected_hash: str, label: str) -> dict[str, Any]:
    require(path.is_file() and sha256(path) == expected_hash, f"{label} is missing or has drifted")
    return read_json(path, label)


def asset_path(value: Any) -> str | None:
    if value is None:
        return None
    getter = getattr(value, "get_path_name", None)
    path = getter() if callable(getter) else str(value)
    return str(path).split(":", 1)[0]


def package_path(value: Any) -> str | None:
    path = asset_path(value)
    if not path:
        return None
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def package_file(package: str) -> Path:
    require(package.startswith("/Game/"), f"Unsafe package path: {package}")
    relative = package[len("/Game/") :].replace("/", os.sep) + ".uasset"
    result = (PROJECT_ROOT / "Content" / relative).resolve(strict=False)
    content = (PROJECT_ROOT / "Content").resolve(strict=True)
    require(
        os.path.commonpath([str(result), str(content)]) == str(content),
        f"Package escaped project Content: {package}",
    )
    return result


def dirty_packages() -> dict[str, list[str]]:
    content = sorted(
        value
        for value in {
            package_path(item)
            for item in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
        }
        if value
    )
    maps = sorted(
        value
        for value in {
            package_path(item)
            for item in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
        }
        if value
    )
    return {"content": content, "maps": maps}


def require_clean(label: str) -> dict[str, list[str]]:
    value = dirty_packages()
    require(value == {"content": [], "maps": []}, f"{label}: {value}")
    return value


def pie_gate() -> dict[str, Any]:
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    worlds = list(unreal.EditorLevelLibrary.get_pie_worlds(include_dedicated_server=False))
    output = {
        "is_in_play_in_editor": bool(level.is_in_play_in_editor()),
        "pie_world_count": len(worlds),
    }
    require(not output["is_in_play_in_editor"] and output["pie_world_count"] == 0, "PIE is active")
    return output


def provider_gate() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for port in PROVIDER_PORTS:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.25)
        try:
            code = probe.connect_ex(("127.0.0.1", port))
        finally:
            probe.close()
        records.append({"port": port, "closed": code != 0, "connect_ex": code})
    require(all(item["closed"] for item in records), "AI/MCP/provider listener is active")
    return records


def renderer_gate() -> dict[str, Any]:
    command_line = str(unreal.SystemLibrary.get_command_line())
    require(re.search(r"(?i)(?:^|\s)-d3d12(?:\s|$)", command_line) is not None, "Fresh verifier requires -d3d12")
    require(re.search(r"(?i)(?:^|\s)-renderoffscreen(?:\s|$)", command_line) is not None, "Fresh verifier requires -RenderOffscreen")
    require(re.search(r"(?i)(?:^|\s)-nullrhi(?:\s|$)", command_line) is None, "NullRHI is forbidden for the PPG home fresh verifier")
    return {
        "requested_rhi": "D3D12",
        "render_offscreen": True,
        "null_rhi": False,
        "command_line": command_line,
    }


def prior_bind_host_exit() -> dict[str, Any]:
    raw = os.environ.get(BIND_HOST_EXIT_ENV, "")
    require(raw == "3", f"{BIND_HOST_EXIT_ENV} must record the observed post-report host exit code 3")
    return {
        "exit_code": 3,
        "timing": "after_atomic_bind_report_publication",
        "failure_site": "PPG WarmupGenerationPipeline under NullRHI / FallbackMaterialProxy assertion",
        "disposition": "recorded_separately_durable_serialized_bind_still_requires_fresh_d3d12_verification",
    }


def verify_hashes(records: dict[Path, str], label: str) -> dict[str, str]:
    output: dict[str, str] = {}
    for path, expected in records.items():
        require(path.is_file(), f"{label} is missing: {path}")
        actual = sha256(path)
        require(actual == expected, f"{label} hash drift: {path} expected={expected} actual={actual}")
        output[str(path)] = actual
    return output


def expected_asset_records() -> list[dict[str, Any]]:
    build = load_fixed_report(BUILD_REPORT, BUILD_REPORT_SHA256, "A01 build report")
    fresh = load_fixed_report(ASSET_FRESH_REPORT, ASSET_FRESH_REPORT_SHA256, "A01 asset fresh report")
    expected = set(EXPECTED_PACKAGES)
    require(build.get("status") == "pass_created_compiled_saved_same_process_readback", "A01 build did not pass")
    require(build.get("target_count") == 18, "A01 build target count drift")
    require(set(build.get("created_assets", [])) == expected, "A01 build package set drift")
    saved_entries = build.get("saved_assets")
    require(isinstance(saved_entries, list) and len(saved_entries) == 18, "A01 saved-asset record count drift")
    require(all(isinstance(item, dict) for item in saved_entries), "Malformed A01 saved-asset record")
    require({item.get("package") for item in saved_entries} == expected, "A01 saved package set drift")
    saved_by_package = {item["package"]: item for item in saved_entries}
    require(build.get("map_saved") is False and build.get("config_saved") is False, "A01 build scope drift")
    require(fresh.get("status") == "pass_fresh_process_serialized_readback", "A01 asset fresh verifier did not pass")
    require(fresh.get("build_report", {}).get("sha256") == BUILD_REPORT_SHA256, "A01 fresh/build provenance drift")
    require(fresh.get("map_saved") is False and fresh.get("assets_saved") is False, "A01 fresh verifier wrote content")
    require(fresh.get("pie_active") is False and fresh.get("pie_world_count") == 0, "A01 fresh verifier PIE drift")
    entries = fresh.get("files")
    require(isinstance(entries, list) and len(entries) == 18, "A01 fresh package count drift")
    require({item.get("package") for item in entries if isinstance(item, dict)} == expected, "A01 fresh package set drift")
    output: list[dict[str, Any]] = []
    for item in entries:
        require(isinstance(item, dict), "Malformed A01 asset record")
        package = str(item.get("package", ""))
        path = package_file(package)
        expected_hash = str(item.get("sha256", "")).upper()
        require(len(expected_hash) == 64, f"Malformed A01 asset hash: {package}")
        require(Path(str(item.get("file", ""))).resolve(strict=False) == path, f"A01 file path drift: {package}")
        require(path.is_file() and sha256(path) == expected_hash, f"A01 asset hash drift: {package}")
        saved = saved_by_package[package]
        require(Path(str(saved.get("file", ""))).resolve(strict=False) == path, f"A01 build saved-file path drift: {package}")
        require(str(saved.get("sha256", "")).upper() == expected_hash, f"A01 build/fresh hash mismatch: {package}")
        require(int(saved.get("bytes", -1)) == path.stat().st_size, f"A01 build saved-byte count mismatch: {package}")
        output.append({"package": package, "file": str(path), "bytes": path.stat().st_size, "sha256": expected_hash})
    return sorted(output, key=lambda item: item["package"])


def verify_checkpoint_from_bind(bind: dict[str, Any], assets: list[dict[str, Any]]) -> dict[str, Any]:
    record = bind.get("checkpoint")
    require(isinstance(record, dict), "Bind checkpoint record is missing")
    path = canonical_under(str(record.get("manifest", "")), ROLLBACK_ROOT, must_exist=True)
    require(path.name == "manifest.json", "Unexpected checkpoint manifest name")
    expected_hash = str(record.get("manifest_sha256", "")).upper()
    require(len(expected_hash) == 64 and sha256(path) == expected_hash, "Bind checkpoint manifest hash drift")
    manifest = read_json(path, "A01 bind checkpoint")
    require(manifest.get("schema") == "redmmo.home_gameplay_bind.a01.rollback.v1", "Checkpoint schema drift")
    require(manifest.get("status") == "PASS_READY_FOR_MAP_BIND", "Checkpoint did not pass")
    require(manifest.get("home_map") == str(HOME_FILE), "Checkpoint home path drift")
    require(manifest.get("home_map_sha256") == HOME_SHA256_BEFORE, "Checkpoint home preimage drift")
    require(manifest.get("a01_assets") == assets, "Checkpoint A01 asset record drift")
    require(
        manifest.get("evidence", {}).get("build_report") == {"path": str(BUILD_REPORT), "sha256": BUILD_REPORT_SHA256},
        "Checkpoint build evidence drift",
    )
    require(
        manifest.get("evidence", {}).get("fresh_report") == {"path": str(ASSET_FRESH_REPORT), "sha256": ASSET_FRESH_REPORT_SHA256},
        "Checkpoint asset-fresh evidence drift",
    )
    require(manifest.get("source_ship") == {"path": str(SOURCE_SHIP), "sha256": SOURCE_SHIP_SHA256}, "Checkpoint source ship drift")
    require(manifest.get("protected_hashes") == {str(path): value for path, value in PROTECTED_FILES.items()}, "Checkpoint protected set drift")
    copy_path = Path(str(manifest.get("rollback_map_copy", ""))).resolve(strict=True)
    require(copy_path.parent == path.parent, "Checkpoint map copy escaped its checkpoint directory")
    require(copy_path.name == "RedMMO_PPG_HomeWorld.umap.pre_bind_a01", "Checkpoint map copy name drift")
    require(copy_path.is_file() and sha256(copy_path) == HOME_SHA256_BEFORE, "Checkpoint map copy hash drift")
    require(record.get("map_copy") == str(copy_path), "Bind report checkpoint copy path drift")
    require(record.get("map_copy_sha256") == HOME_SHA256_BEFORE, "Bind report checkpoint copy hash drift")
    return {
        "manifest": str(path),
        "manifest_sha256": expected_hash,
        "map_copy": str(copy_path),
        "map_copy_sha256": HOME_SHA256_BEFORE,
    }


def authenticate_bind_report(path: Path, assets: list[dict[str, Any]]) -> tuple[dict[str, Any], str, str]:
    report_hash = sha256(path)
    require(report_hash == BIND_REPORT_SHA256, "A01 home-bind report hash drift")
    bind = read_json(path, "A01 home bind report")
    require(bind.get("schema") == "redmmo.home_gameplay_bind.a01.transaction.v1", "Bind report schema drift")
    require(bind.get("status") == "PASS_MAP_BOUND_PENDING_FRESH_RELOAD_MAPCHECK_PIE", "Bind transaction did not pass")
    require(bind.get("home_map") == HOME_MAP and bind.get("home_map_file") == str(HOME_FILE), "Bind target drift")
    require(bind.get("home_map_sha256_before") == HOME_SHA256_BEFORE, "Bind preimage hash drift")
    post_hash = str(bind.get("home_map_sha256_after", "")).upper()
    require(re.fullmatch(r"[0-9A-F]{64}", post_hash) is not None, "Bind post-map hash is malformed")
    require(post_hash == HOME_SHA256_AFTER, "Bind post-map hash differs from the durable A01 transaction result")
    require(post_hash != HOME_SHA256_BEFORE, "Bind report did not serialize a new home-map image")
    require(HOME_FILE.is_file() and sha256(HOME_FILE) == post_hash, "Current home map does not match bind post-map hash")
    require(bind.get("actor_count_before") == 12 and bind.get("actor_count_after") == EXPECTED_ACTOR_COUNT, "Bind actor-count contract drift")
    removed = bind.get("removed_actor")
    require(isinstance(removed, dict), "Bind removed-actor record missing")
    require(removed.get("label") == OLD_VISUAL_LABEL and removed.get("class") == OLD_VISUAL_CLASS, "Bind removed the wrong actor")
    settings = bind.get("world_settings")
    require(isinstance(settings, dict), "Bind WorldSettings record missing")
    require(settings.get("default_game_mode_before") == EXPECTED_OLD_GAME_MODE_CLASS, "Bind prior GameMode drift")
    require(settings.get("default_game_mode_after") == GAME_MODE_CLASS, "Bind target GameMode drift")
    require(bind.get("ppg_before") == bind.get("ppg_after"), "Bind changed the PPG record")
    preserved = bind.get("preserved_actor_records")
    require(isinstance(preserved, list) and len(preserved) == EXPECTED_ACTOR_COUNT, "Bind preserved-actor record drift")
    require(bind.get("dirty_packages_after") == {"content": [], "maps": []}, "Bind left dirty packages")
    require(bind.get("map_saved") is True, "Bind did not save the exact home map")
    require(bind.get("config_saved") is False and bind.get("content_assets_saved") is False, "Bind scope drift")
    require(bind.get("a01_asset_count") == 18, "Bind A01 asset count drift")
    require(bind.get("fresh_reload_mapcheck_required") is True and bind.get("pie_required") is True, "Bind acceptance-gate drift")
    expected_tracked = {str(path): value for path, value in TRACKED_FILES.items()}
    require(bind.get("tracked_hashes_unchanged") == expected_tracked, "Bind tracked-file evidence drift")
    verify_checkpoint_from_bind(bind, assets)
    return bind, report_hash, post_hash


def actor_record(actor: Any) -> dict[str, Any]:
    location = actor.get_actor_location()
    rotation = actor.get_actor_rotation()
    scale = actor.get_actor_scale3d()
    return {
        "name": actor.get_name(),
        "label": actor.get_actor_label(),
        "class": actor.get_class().get_path_name(),
        "location": [float(location.x), float(location.y), float(location.z)],
        "rotation": [float(rotation.pitch), float(rotation.yaw), float(rotation.roll)],
        "scale": [float(scale.x), float(scale.y), float(scale.z)],
    }


def actor_records(actors: list[Any]) -> list[dict[str, Any]]:
    return sorted((actor_record(actor) for actor in actors), key=lambda item: (item["name"], item["label"], item["class"]))


def verify_grass(planet: Any) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for package, record in GRASS_ASSETS.items():
        path = record["file"]
        expected = str(record["sha256"])
        require(path.is_file() and sha256(path) == expected, f"Approved grass hash drift: {package}")
        asset = unreal.EditorAssetLibrary.load_asset(package)
        require(asset is not None and asset.get_class().get_name() == "StaticMesh", f"Approved grass failed to load: {package}")
        files.append({"package": package, "file": str(path), "sha256": expected})

    biome_foliage: list[str | None] = []
    for biome in list(planet.get_editor_property("biome_data")):
        for key, value in biome.to_dict().items():
            normalized = str(key).replace("_", "").lower()
            if normalized in ("foliagedata", "forestfoliagedata"):
                biome_foliage.append(package_path(value))
    require(biome_foliage.count(PPG_FOLIAGE) == 3, "R10O foliage is not bound to all three PPG biomes")
    foliage = unreal.EditorAssetLibrary.load_asset(PPG_FOLIAGE)
    require(foliage is not None and foliage.get_class().get_name() == "FoliageData", "R10O FoliageData failed to load")
    entries = list(foliage.get_editor_property("foliage_list"))
    require(len(entries) == 3, "R10O FoliageList cardinality drift")
    bindings = [package_path(item.get_editor_property("mesh")) for item in entries[1].get_editor_property("meshes")]
    require(bindings == PPG_GRASS_BINDINGS, "Approved R10N grass aliases are no longer the PPG grass bindings")
    return {
        "files": sorted(files, key=lambda item: item["package"]),
        "biome_foliage_bindings": biome_foliage,
        "grass_slot_index": 1,
        "grass_mesh_bindings": bindings,
    }


def verify_ppg(actors: list[Any]) -> tuple[dict[str, Any], Any]:
    spawners = [actor for actor in actors if actor.get_class().get_name() == PPG_SPAWNER_CLASS]
    require(len(spawners) == 1, f"Expected one PlanetSpawnerBP_C, found {len(spawners)}")
    spawner = spawners[0]
    planet = spawner.get_editor_property("planet_data")
    require(package_path(planet) == PPG_PLANET, "PPG PlanetData binding drift")
    require(bool(planet.get_editor_property("generate_water")), "PPG GenerateWater is disabled")
    water = package_path(planet.get_editor_property("water_material"))
    require(water == PPG_WATER, "PPG native water material drift")
    return (
        {
            "actor": actor_record(spawner),
            "planet_data": package_path(planet),
            "generate_water": True,
            "water_material": water,
        },
        planet,
    )


def current_map() -> str:
    world = unreal.EditorLevelLibrary.get_editor_world()
    require(world is not None, "Editor world is unavailable")
    value = world.get_path_name().split(":", 1)[0]
    return value.rsplit(".", 1)[0]


def command_log() -> Path:
    text = str(unreal.SystemLibrary.get_command_line())
    match = re.search(r'(?i)-abslog=(?:"([^"]+)"|(\S+))', text)
    value = (match.group(1) or match.group(2)) if match else str(PROJECT_ROOT / r"Saved\Logs\RedMMO.log")
    path = Path(value)
    require(path.is_file(), f"Verifier log is missing: {path}")
    return path


def normalized_warning(value: str) -> str:
    return " ".join(value.split()).casefold()


def map_check(world: Any) -> dict[str, Any]:
    log = command_log()
    offset = log.stat().st_size
    marker = "REDMMO_HOME_GAMEPLAY_BIND_A01_FRESH_MAPCHECK_" + uuid.uuid4().hex.upper()
    unreal.log(marker)
    unreal.SystemLibrary.execute_console_command(world, "MAP CHECKDEP NOCLEARLOG")
    summary_pattern = re.compile(r"MapCheck: Map check complete: (\d+) Error\(s\), (\d+) Warning\(s\)")
    segment = ""
    matches: list[tuple[str, str]] = []
    for _ in range(200):
        time.sleep(0.1)
        size = log.stat().st_size
        with log.open("rb") as stream:
            stream.seek(min(offset, size))
            segment = stream.read().decode("utf-8", errors="replace")
        if marker in segment:
            after_marker = segment.split(marker, 1)[1]
            matches = summary_pattern.findall(after_marker)
            if matches:
                segment = after_marker
                break
    require(matches, "No fresh authoritative MapCheck completion marker")
    errors, warnings = (int(item) for item in matches[-1])
    summary_match = list(summary_pattern.finditer(segment))[-1]
    checked_segment = segment[: summary_match.end()]
    warning_lines = re.findall(r"(?m)^.*?MapCheck: Warning: (.*?)\s*$", checked_segment)
    require(errors == 0, f"MapCheck reported {errors} error(s)")
    require(len(warning_lines) == warnings, f"MapCheck warning parse mismatch: summary={warnings} parsed={len(warning_lines)}")
    if warnings == 0:
        pass
    elif warnings == 1:
        require(normalized_warning(warning_lines[0]) == normalized_warning(ALLOWED_WARNING), "Unexpected MapCheck warning: " + warning_lines[0])
    else:
        raise VerifyError(f"MapCheck reported {warnings} warnings; at most the known Floor_0 warning is allowed")
    return {
        "errors": errors,
        "warnings": warnings,
        "warning_lines": warning_lines,
        "allowed_warning": ALLOWED_WARNING if warnings == 1 else None,
        "log": str(log),
        "marker": marker,
    }


_EXIT = {"handle": None}


def schedule_exit(delay: float) -> None:
    started = time.monotonic()

    def tick(_delta: float) -> None:
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


def main() -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema": "redmmo.home_gameplay_bind.a01.fresh_reload_mapcheck.v1",
        "status": "RUNNING",
        "started_utc": now(),
        "evidence_class": "automation",
        "claim_limit": (
            "Fresh-process serialized reload and MapCheck only. This is not runtime, PIE, controls, "
            "animation-in-motion, ship-operation, collision, audio, real-GPU visual, package, or multiplayer evidence."
        ),
        "save_calls": 0,
        "map_saved": False,
        "assets_saved": False,
        "config_saved": False,
    }
    target: Path | None = None
    try:
        target = fresh_report_path()
        bind_path = bind_report_path()
        require(target != bind_path, "Fresh output path aliases the bind input report")
        actual_project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(actual_project == PROJECT_FILE.resolve(strict=True), f"Wrong Unreal project: {actual_project}")
        require(PROJECT_FILE.is_file() and sha256(PROJECT_FILE) == PROJECT_SHA256, "Project descriptor drift")
        require_clean("Dirty packages before fresh verification")
        report["renderer_gate"] = renderer_gate()
        report["prior_bind_host"] = prior_bind_host_exit()
        report["pie_gate_before"] = pie_gate()
        report["provider_gate_before"] = provider_gate()
        require(current_map() == "/Engine/Maps/Entry", f"Fresh verifier must start on /Engine/Maps/Entry, found {current_map()}")

        assets = expected_asset_records()
        bind, bind_hash, post_hash = authenticate_bind_report(bind_path, assets)
        tracked_before = verify_hashes(TRACKED_FILES, "tracked source/protected file")
        grass_file_records_before = verify_hashes(
            {Path(record["file"]): str(record["sha256"]) for record in GRASS_ASSETS.values()},
            "approved grass file",
        )
        require(PPG_FOLIAGE_FILE.is_file() and sha256(PPG_FOLIAGE_FILE) == PPG_FOLIAGE_SHA256, "R10O FoliageData hash drift")

        world = unreal.EditorLoadingAndSavingUtils.load_map(HOME_MAP)
        require(world is not None and current_map() == HOME_MAP, "Exact home-map fresh load failed")
        require_clean("Fresh home-map load dirtied packages")
        report["pie_gate_after_load"] = pie_gate()
        report["provider_gate_after_load"] = provider_gate()
        require(sha256(HOME_FILE) == post_hash, "Home-map bytes changed during fresh load")

        subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actors = list(subsystem.get_all_level_actors())
        require(len(actors) == EXPECTED_ACTOR_COUNT, f"Fresh actor count drift: {len(actors)}")
        require(not any(actor.get_actor_label() == OLD_VISUAL_LABEL for actor in actors), "Removed visual-only ship label persists")
        records = actor_records(actors)
        require(records == bind.get("preserved_actor_records"), "Fresh actor records differ from authenticated bind report")

        settings = world.get_world_settings()
        require(settings is not None, "WorldSettings is unavailable")
        game_mode = asset_path(settings.get_editor_property("default_game_mode"))
        require(game_mode == GAME_MODE_CLASS, f"Fresh GameMode binding drift: {game_mode}")

        ppg, planet = verify_ppg(actors)
        require(ppg == bind.get("ppg_after"), "Fresh PPG record differs from authenticated bind report")
        grass = verify_grass(planet)

        check = map_check(world)
        require_clean("MapCheck dirtied packages")
        report["pie_gate_after_mapcheck"] = pie_gate()
        report["provider_gate_after_mapcheck"] = provider_gate()
        require(sha256(HOME_FILE) == post_hash, "MapCheck changed the bound home-map bytes")
        require(sha256(bind_path) == bind_hash, "Bind report changed during fresh verification")
        require(expected_asset_records() == assets, "A01 gameplay asset hashes changed during fresh verification")
        require(verify_hashes(TRACKED_FILES, "post-MapCheck tracked source/protected file") == tracked_before, "Tracked file record drift")
        require(
            verify_hashes(
                {Path(record["file"]): str(record["sha256"]) for record in GRASS_ASSETS.values()},
                "post-MapCheck approved grass file",
            ) == grass_file_records_before,
            "Approved grass record drift",
        )
        require(sha256(PPG_FOLIAGE_FILE) == PPG_FOLIAGE_SHA256, "MapCheck changed R10O FoliageData")

        report.update(
            {
                "status": "PASS_FRESH_SERIALIZED_RELOAD_MAPCHECK_PENDING_PIE",
                "completed_utc": now(),
                "project": str(PROJECT_FILE),
                "maps_loaded_by_verifier": [HOME_MAP],
                "home_map": HOME_MAP,
                "home_map_file": str(HOME_FILE),
                "home_map_sha256_derived_from_bind": post_hash,
                "home_map_sha256_after_mapcheck": sha256(HOME_FILE),
                "bind_report": {"path": str(bind_path), "sha256": bind_hash},
                "actor_count": len(actors),
                "actor_records": records,
                "removed_visual_only_label_count": 0,
                "world_settings": {"path": settings.get_path_name(), "default_game_mode": game_mode},
                "ppg": ppg,
                "approved_grass": grass,
                "a01_assets": assets,
                "a01_asset_count": len(assets),
                "protected_hashes": {str(path): value for path, value in PROTECTED_FILES.items()},
                "tracked_hashes": tracked_before,
                "map_check": check,
                "dirty_packages_after": dirty_packages(),
                "pie_started": False,
                "runtime_verified": False,
                "real_gpu_visual_verified": False,
            }
        )
    except Exception as exc:
        report.update(
            {
                "status": "FAIL",
                "completed_utc": now(),
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "dirty_packages_at_failure": dirty_packages(),
            }
        )
    finally:
        try:
            if target is not None:
                atomic_json(target, report)
        finally:
            if report.get("status", "").startswith("PASS"):
                unreal.log("REDMMO_HOME_GAMEPLAY_BIND_A01_FRESH " + report["status"])
            else:
                unreal.log_error("REDMMO_HOME_GAMEPLAY_BIND_A01_FRESH " + report.get("status", "FAIL") + " " + report.get("error", ""))
            schedule_exit(8.0 if report.get("status", "").startswith("PASS") else 2.0)
    return report


main()
