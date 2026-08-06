"""R60 current-home adapter for the immutable A01 Trooper/StarSparrow validator.

The historical validator remains byte-exact.  This adapter replaces only its
input-authentication step so the same runtime control sequence can be run
against the current ProfileV1 home-map provenance (R26) and the compiled R59
starter-ship parking implementation.  It never saves a package or config.
"""

from __future__ import annotations

import os
from pathlib import Path


BASE = Path(r"D:\RedMMOTitan\Build\Automation\validate_clean_redmmo_trooper_starsparrow_a01_pie.py")
R26_REPORT = Path(
    r"D:\RedMMOTitanWindowsData\Diagnostics"
    r"\RedMMO_PPG_ProfileV1R25LandPlayerStartReload_R26_20260805T1200Z\result.json"
)
R26_REPORT_SHA256 = "7A50363E6A398CE4CC3B1C07C064FC4C099C6F75AB191B124550009C0B9F4449"
R59_REPORT = Path(
    r"D:\RedMMOTitanWindowsData\Diagnostics"
    r"\RedMMO_StarterShipParking_R59_20260805T2002Z\CorrectedRunAttempt7\result.json"
)
R59_REPORT_SHA256 = "F4DF8BB3A51D7D30286A65DC1C1891737982DC10F427E15A218DF6C2155DA42E"
PROFILE_BIND_REPORT = Path(
    r"D:\RedMMOTitanWindowsData\Diagnostics"
    r"\RedMMO_PPG_ProfileV1HomeBinding_20260805_0627"
    r"\apply_redmmo_ppg_profile_v1_home_binding_result.json"
)
PROFILE_BIND_REPORT_SHA256 = "D1FDF4058DC08E4E7F4B96A39331A61E72AD69E347F422D98F4039B70442B33F"
EXPECTED_EDITOR_DLL = Path(
    r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Binaries\Win64\UnrealEditor-RedMMO.dll"
)
EXPECTED_EDITOR_DLL_SHA256 = "728992E6FEE98759114E26974337D2AC94B575CD6EC46E39FDECE5F8EE1AC71C"
PROFILE_FOLIAGE = (
    "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles/"
    "DA_PPG_ProfileV1_GrassEligible_R29"
)
PROFILE_FOLIAGE_FILE = Path(
    r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\WorldAuthoring"
    r"\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_GrassEligible_R29.uasset"
)
PROFILE_FOLIAGE_SHA256 = "D1ACEE4F403D2082FF49CB57D52907AAADA0C20D06386576C435557CF49404D8"


source = BASE.read_text(encoding="utf-8")
bootstrap_marker = "\ntry:\n    _REDMMO_A01_PIE_VALIDATION = A01PIEValidation()"
marker_at = source.rfind(bootstrap_marker)
if marker_at < 0:
    raise RuntimeError("Historical A01 validator bootstrap marker drift")

base_globals = {"__name__": "redmmo_a01_r60_base", "__file__": str(BASE)}
exec(compile(source[:marker_at], str(BASE), "exec"), base_globals)

# The saved R25/R26 home contains the added attached developer label actor.
base_globals["EXPECTED_EDITOR_ACTOR_COUNT"] = 12
# R29 is the current project-owned foliage successor used by the unchanged
# seeded biome slots; R10O remains only the historical validator default.
base_globals["PPG_FOLIAGE"] = PROFILE_FOLIAGE


def authenticate_current_r60(self) -> None:
    b = base_globals
    actual_project = Path(
        b["unreal"].Paths.convert_relative_path_to_full(
            b["unreal"].Paths.get_project_file_path()
        )
    ).resolve(strict=True)
    b["require"](
        actual_project == b["PROJECT_FILE"].resolve(strict=True),
        f"Wrong active project: {actual_project}",
    )
    b["require"](
        b["PROJECT_FILE"].is_file()
        and b["sha256"](b["PROJECT_FILE"]) == b["PROJECT_SHA256"],
        "Project descriptor drift",
    )
    b["require"](
        b["HOME_FILE"].is_file()
        and b["sha256"](b["HOME_FILE"]) == b["HOME_SHA256"],
        "Current ProfileV1 home-map hash drift",
    )
    b["require"](
        b["sha256"](EXPECTED_EDITOR_DLL) == EXPECTED_EDITOR_DLL_SHA256,
        "Compiled R59 editor module drift",
    )

    bind = b["load_json"](
        PROFILE_BIND_REPORT, PROFILE_BIND_REPORT_SHA256, "ProfileV1 bind report"
    )
    b["require"](
        bind.get("schema") == "redmmo.ppg_profile_v1.home_binding.apply.v1",
        "ProfileV1 bind report schema drift",
    )
    b["require"](
        bind.get("status")
        == "PASS_PROFILE_V1_BOUND_TO_HOME_PENDING_FRESH_RELOAD_MAPCHECK_RUNTIME_VISUAL",
        "ProfileV1 bind report did not pass",
    )
    b["require"](
        bind.get("target_planet_data") == b["PPG_PLANET"],
        "ProfileV1 bind report PPG target drift",
    )
    b["require"](
        bool(bind.get("a01_game_mode_preserved")),
        "ProfileV1 bind report did not preserve A01 GameMode",
    )

    r26 = b["load_json"](R26_REPORT, R26_REPORT_SHA256, "R26 current-home reload report")
    b["require"](
        r26.get("schema")
        == "redmmo.ppg_profile_v1.r25_land_playerstart.reload_mapcheck.r26.v1",
        "R26 reload report schema drift",
    )
    b["require"](
        r26.get("status")
        == "PASS_R26_R25_LAND_PLAYERSTART_FRESH_RELOAD_MAPCHECK_NO_SAVE",
        "R26 current-home reload did not pass",
    )
    b["require"](
        r26.get("map_sha256_before_after") == b["HOME_SHA256"],
        "R26 report does not authenticate current home map",
    )
    b["require"](
        r26.get("planet_data") == b["PPG_PLANET"],
        "R26 report PPG binding drift",
    )
    expected_game_mode_asset = b["GAME_MODE_CLASS"].split(".", 1)[0]
    b["require"](
        r26.get("a01_game_mode") == expected_game_mode_asset,
        "R26 report GameMode drift",
    )
    b["require"](
        r26.get("actor_count") == b["EXPECTED_EDITOR_ACTOR_COUNT"],
        "R26 report actor-count drift",
    )
    b["require"](r26.get("generation_seed") == 1337, "R26 report seed drift")
    b["require"](
        r26.get("map_check", {}).get("errors") == 0
        and r26.get("map_check", {}).get("warnings") == 0,
        "R26 MapCheck gate did not pass",
    )
    b["require"](
        r26.get("dirty_packages_after") == {"content": [], "maps": []},
        "R26 report retained dirty packages",
    )
    b["require"](
        not r26.get("save_called") and not r26.get("pie_started"),
        "R26 report claim boundary drift",
    )

    r59 = b["load_json"](R59_REPORT, R59_REPORT_SHA256, "R59 ship-parking report")
    b["require"](
        r59.get("schema") == "redmmo.starter-ship-parking.r59.diagnostic.v1",
        "R59 report schema drift",
    )
    b["require"](
        r59.get("status") == "PASS_R59_STARTER_SHIP_PARKED_ON_AUTHENTIC_PPG_SURFACE",
        "R59 ship-parking runtime did not pass",
    )
    b["require"](r59.get("ship_count") == 1, "R59 did not prove exactly one starter ship")
    b["require"](
        r59.get("home_map_sha256_after") == b["HOME_SHA256"],
        "R59 report home-map preservation drift",
    )
    b["require"](
        not r59.get("save_called") and not r59.get("persistent_save"),
        "R59 report unexpectedly saved persistent content",
    )

    build = b["load_json"](b["BUILD_REPORT"], b["BUILD_REPORT_SHA256"], "A01 asset build report")
    fresh = b["load_json"](b["FRESH_REPORT"], b["FRESH_REPORT_SHA256"], "A01 fresh asset report")
    b["require"](
        build.get("status") == "pass_created_compiled_saved_same_process_readback",
        "A01 asset build did not pass",
    )
    b["require"](
        fresh.get("status") == "pass_fresh_process_serialized_readback",
        "A01 fresh asset readback did not pass",
    )
    b["require"](
        fresh.get("build_report", {}).get("sha256") == b["BUILD_REPORT_SHA256"],
        "Fresh report build provenance drift",
    )
    entries = fresh.get("files")
    b["require"](
        isinstance(entries, list) and len(entries) == 18,
        "Fresh A01 package record count drift",
    )
    self.tracked_hashes = {
        b["package_file"](str(item["package"])): str(item["sha256"]).upper()
        for item in entries
        if isinstance(item, dict)
    }
    b["require"](len(self.tracked_hashes) == 18, "Fresh A01 package set is malformed")
    for package, digest in b["TRACKED_PACKAGE_HASH_OVERRIDES"].items():
        package_path = b["package_file"](package)
        b["require"](
            package_path in self.tracked_hashes,
            f"Tracked-package override is outside A01: {package}",
        )
        b["require"](
            b["re"].fullmatch(r"[0-9A-F]{64}", digest) is not None,
            f"Malformed tracked-package override: {package}",
        )
        self.tracked_hashes[package_path] = digest
    self.tracked_hashes.update(
        {
            b["HOME_FILE"]: b["HOME_SHA256"],
            b["SOURCE_SHIP_FILE"]: b["SOURCE_SHIP_SHA256"],
            b["PPG_PLANET_FILE"]: b["PPG_PLANET_SHA256"],
            PROFILE_FOLIAGE_FILE: PROFILE_FOLIAGE_SHA256,
            EXPECTED_EDITOR_DLL: EXPECTED_EDITOR_DLL_SHA256,
            **b["APPROVED_GRASS_FILES"],
            **b["PROTECTED_FILES"],
        }
    )
    self.tracked_before = b["verify_hashes"](
        self.tracked_hashes, "Tracked gameplay/home/grass/protected file"
    )
    self.config_before = b["hash_tree"](b["PROJECT_ROOT"] / "Config")
    self.report["authenticated_inputs"] = {
        "active_project": str(actual_project),
        "profile_bind_report": {
            "path": str(PROFILE_BIND_REPORT),
            "sha256": PROFILE_BIND_REPORT_SHA256,
        },
        "r26_current_home_report": {
            "path": str(R26_REPORT),
            "sha256": R26_REPORT_SHA256,
        },
        "r59_ship_parking_report": {
            "path": str(R59_REPORT),
            "sha256": R59_REPORT_SHA256,
        },
        "build_report": {
            "path": str(b["BUILD_REPORT"]),
            "sha256": b["BUILD_REPORT_SHA256"],
        },
        "fresh_report": {
            "path": str(b["FRESH_REPORT"]),
            "sha256": b["FRESH_REPORT_SHA256"],
        },
        "home_map_sha256": b["HOME_SHA256"],
        "profile_v1_sha256": b["PPG_PLANET_SHA256"],
        "profile_v1_foliage": PROFILE_FOLIAGE,
        "profile_v1_foliage_sha256": PROFILE_FOLIAGE_SHA256,
        "compiled_editor_module_sha256": EXPECTED_EDITOR_DLL_SHA256,
        "tracked_file_count": len(self.tracked_hashes),
        "approved_grass": list(b["APPROVED_GRASS"]),
        "approved_grass_source": "/Game/StylizedRocksPack_01/Common/GrassChunks/Meshes/SM_GrassChunk_01",
        "tracked_package_hash_overrides": dict(b["TRACKED_PACKAGE_HASH_OVERRIDES"]),
    }


base_globals["A01PIEValidation"].authenticate_inputs = authenticate_current_r60


def face_tangent_toward_current_r60(self, target):
    """Steer the current radial orbit camera through the real IA_RedLook path.

    RedPlayerCharacter movement is relative to its private
    CameraTangentForward, not controller rotation.  The historical harness
    therefore could not steer this newer camera implementation.  Course
    correction remains real gameplay input: IA_RedLook updates the camera
    heading, followed by IA_RedMove/IA_RedSprint in the inherited phase.
    """

    b = base_globals
    location = self.trooper.get_actor_location()
    up = self.radial_up(location)
    forward = b["plane_project"](b["sub"](target, location), up)
    b["require"](
        b["length"](forward) > 1.0,
        "Target has no tangent direction from Trooper",
    )
    forward = b["normalized"](forward)
    current = b["plane_project"](self.trooper.get_actor_forward_vector(), up)
    b["require"](
        b["length"](current) > 1.0e-4,
        "Trooper has no current tangent heading",
    )
    current = b["normalized"](current)
    cross = b["unreal"].Vector(
        current.y * forward.z - current.z * forward.y,
        current.z * forward.x - current.x * forward.z,
        current.x * forward.y - current.y * forward.x,
    )
    sine = b["dot"](cross, up)
    cosine = max(-1.0, min(1.0, b["dot"](current, forward)))
    signed_degrees = b["math"].degrees(b["math"].atan2(sine, cosine))
    look_x = max(-8.0, min(8.0, signed_degrees / 2.5))
    if abs(look_x) > 0.01:
        self.inject("look", x=look_x)
    return {
        "forward": b["vec"](forward),
        "up": b["vec"](up),
        "current": b["vec"](current),
        "signed_degrees": signed_degrees,
        "injected_look_x": look_x,
        "r60_real_look_action_steering": True,
    }


base_globals["A01PIEValidation"].face_tangent_toward = face_tangent_toward_current_r60

try:
    base_globals["_REDMMO_A01_PIE_VALIDATION"] = base_globals["A01PIEValidation"]()
    base_globals["_REDMMO_A01_PIE_VALIDATION"].start()
except Exception as bootstrap_error:
    base_globals["unreal"].log_error(
        "REDMMO_A01_R60_PIE_VALIDATION_BOOTSTRAP_FAIL " + str(bootstrap_error)
    )
    try:
        base_globals["unreal"].SystemLibrary.quit_editor()
    except Exception:
        pass
