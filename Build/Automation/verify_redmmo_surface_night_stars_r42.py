"""R42 no-save matched D3D12 surface-night star readability proof.

This deliberately reuses the proven R18 day/night/orbit transaction while
updating only the current immutable map/evidence paths and the stricter R42
surface-night control contract.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import unreal


BASE_PATH = Path("D:/RedMMOTitan/Build/Automation/verify_redmmo_night_presenter_r18_pie.py")
SPEC = importlib.util.spec_from_file_location("redmmo_r18_night_verify_base_for_r42", BASE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load proven R18 verifier")

base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)

base.EXPECTED_MAP_SHA = "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3"
base.DIAG = Path("D:/RedMMOTitanWindowsData/Diagnostics/RedMMO_SurfaceNightStars_R42B_20260805T1552Z")
base.RESULT = base.DIAG / "verify_result.json"
base.CAPTURES = {
    "surface_day": base.DIAG / "R42_surface_day_1280x720.png",
    "surface_night": base.DIAG / "R42_surface_night_1280x720.png",
    "orbit_night": base.DIAG / "R42_orbit_night_1280x720.png",
}

SOURCE_FILES = {
    "header": Path("D:/RedMMOTitanWindowsData/Projects/RedMMO/Source/RedMMO/Public/RedPlanetNightPresenter.h"),
    "implementation": Path("D:/RedMMOTitanWindowsData/Projects/RedMMO/Source/RedMMO/Private/RedPlanetNightPresenter.cpp"),
    "editor_binary": Path("D:/RedMMOTitanWindowsData/Projects/RedMMO/Binaries/Win64/UnrealEditor-RedMMO.dll"),
}


def prepare_r42(self):
    base.require(not base.RESULT.exists(), "R42 verify result already exists")
    base.require(all(not path.exists() for path in base.CAPTURES.values()), "R42 capture already exists")
    base.require(base.sha256(base.MAP_FILE) == base.EXPECTED_MAP_SHA, "R42 map hash drift")
    self.report["providers"] = base.provider_gate()
    for path, expected in base.PROTECTED.items():
        base.require(base.sha256(path) == expected, "Protected hash drift: " + str(path))
    base.require(not base.dirty_packages()["content"] and not base.dirty_packages()["maps"],
                 "Dirty before R42 verify")
    base.require(self.level.load_level(base.MAP), "Unable to fresh-reload R42 map")
    editor_world = self.editor.get_editor_world()
    actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
    presenters = [actor for actor in actors if actor.get_actor_label() == base.PRESENTER_LABEL]
    spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
    base.require(len(presenters) == 1 and len(spawners) == 1, "R42 serialized actor contract failed")
    unreal.SystemLibrary.execute_console_command(editor_world, "MAP CHECK")
    base.require(not base.dirty_packages()["content"] and not base.dirty_packages()["maps"],
                 "MapCheck dirtied R42")
    self.report["fresh_reload"] = {
        "actor_count": len(actors),
        "presenter_count": len(presenters),
        "spawner_count": len(spawners),
    }
    self.report["source_hashes"] = {name: base.sha256(path) for name, path in SOURCE_FILES.items()}
    self.level.editor_request_begin_play()
    self.phase("wait_pie")


def capture_r42(self, key):
    path = base.CAPTURES[key]
    view_location, view_rotation = base.player_view(self.controller, self.pawn)
    applied = self.presenter.evaluate_and_apply_at(view_location)
    base.require(bool(applied), "Presenter failed to resolve for " + key)
    surface_control = float(self.presenter.get_editor_property("surface_night_star_visibility"))
    values = {
        "view_location": base.vec(view_location),
        "view_rotation": [float(view_rotation.pitch), float(view_rotation.yaw), float(view_rotation.roll)],
        "altitude_cm": float(self.presenter.get_editor_property("last_altitude_cm")),
        "night_weight": float(self.presenter.get_editor_property("last_night_hemisphere_weight")),
        "star_weight": float(self.presenter.get_editor_property("last_star_visibility_weight")),
        "fill_weight": float(self.presenter.get_editor_property("last_night_fill_weight")),
        "surface_night_star_visibility_control": surface_control,
        "path": path.as_posix(),
    }
    base.require(abs(surface_control - 0.75) < 0.001, "Serialized R42B surface-night control is not 0.75")
    if key == "surface_day":
        base.require(values["night_weight"] < 0.01 and values["star_weight"] < 0.01,
                     "Day weights wrong")
    elif key == "surface_night":
        base.require(values["night_weight"] > 0.99 and 0.74 <= values["star_weight"] <= 0.76
                     and values["fill_weight"] >= 0.15, "Surface-night R42B weights wrong")
    else:
        base.require(values["star_weight"] > 0.99 and values["fill_weight"] < 0.01,
                     "Orbit weights wrong")
    self.report.setdefault("captures", {})[key] = values
    unreal.SystemLibrary.execute_console_command(
        self.world, 'HighResShot filename="{}" 1280x720'.format(path.as_posix()))
    self.phase("wait_" + key + "_capture")


def finish_r42(self):
    for key, path in base.CAPTURES.items():
        base.require(path.is_file() and path.stat().st_size > 0, "Missing capture: " + key)
        base.require(base.png_size(path) == [1280, 720], "Capture size mismatch: " + key)
        self.report["captures"][key].update({
            "sha256": base.sha256(path),
            "bytes": path.stat().st_size,
            "dimensions": [1280, 720],
        })
    base.require(base.sha256(base.MAP_FILE) == base.EXPECTED_MAP_SHA, "PIE changed R42 map")
    base.require(not base.dirty_packages()["content"] and not base.dirty_packages()["maps"],
                 "PIE dirtied R42 packages")
    for path, expected in base.PROTECTED.items():
        base.require(base.sha256(path) == expected, "PIE changed protected content")
    self.report.update({
        "status": "PASS_R42B_RUNTIME_WEIGHTS_AND_D3D12_CAPTURES_PENDING_INDEPENDENT_PIXEL_REVIEW",
        "map_sha256_after": base.sha256(base.MAP_FILE),
        "protected_hashes": {str(path): base.sha256(path) for path in base.PROTECTED},
        "pie_stopped_cleanly": True,
        "persistent_map_or_asset_saves": 0,
        "claim_limit": (
            "Runtime weights and fresh D3D12 pixels exist. Independent visual review is still required; "
            "no biome, grass, gameplay, standalone, replication, or multiplayer acceptance is claimed."
        ),
    })
    with base.RESULT.open("x", encoding="utf-8") as stream:
        json.dump(self.report, stream, indent=2)
        stream.write("\n")
    unreal.log_warning("REDMMO_SURFACE_NIGHT_STARS_R42_VERIFY_PASS "
                       + json.dumps(self.report, sort_keys=True))
    unreal.unregister_slate_post_tick_callback(self.handle)
    self.handle = None
    unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), "QUIT_EDITOR")


base.Session.prepare = prepare_r42
base.Session.capture = capture_r42
base.Session.finish = finish_r42
base.session.report.update({
    "slice": "R42B surface-night star readability",
    "surface_night_visibility_target": 0.75,
    "orbit_star_density_emission_policy": "unchanged from verified R18",
})
unreal.log("REDMMO_SURFACE_NIGHT_STARS_R42_VERIFY_STARTED")
