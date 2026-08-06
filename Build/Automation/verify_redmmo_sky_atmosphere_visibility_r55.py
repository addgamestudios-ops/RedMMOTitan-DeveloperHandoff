"""R55 no-save SkyAtmosphere visibility discriminator at the saved night view.

Reuses the hash-pinned R54 harness helpers, but changes only the PIE-world
SkyAtmosphereComponent visibility for the second existing-viewport frame and
restores the exact preimage before PIE ends.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import traceback
from pathlib import Path

import unreal


R54_SOURCE = Path(r"D:\RedMMOTitan\Build\Automation\verify_redmmo_cloud_radius_surface_sky_r54.py")
R54_SHA256 = "7B5961C137C476F4A963BDEE8231881F21DE71933EE8A289C2CB17349F373ADC"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_SkyAtmosphereVisibility_R55_20260805T1918Z")
RESULT = DIAG / "result.json"
BASELINE = DIAG / "R55_sky_atmosphere_visible.png"
DISABLED = DIAG / "R55_sky_atmosphere_hidden.png"


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


if file_sha256(R54_SOURCE) != R54_SHA256:
    raise RuntimeError("R54 harness dependency drift")

source = R54_SOURCE.read_text(encoding="utf-8")
marker = "\ntry:\n    _R54 = R54()"
if source.count(marker) != 1:
    raise RuntimeError("R54 bootstrap boundary drift")
base = {"__name__": "redmmo_r54_harness", "__file__": str(R54_SOURCE)}
exec(compile(source.split(marker, 1)[0], str(R54_SOURCE), "exec"), base)

# Redirect inherited helper globals to this no-clobber R55 evidence set.
base["DIAG"] = DIAG
base["RESULT"] = RESULT
base["BASELINE"] = BASELINE
base["CORRECTED"] = DISABLED

R54Harness = base["R54"]
require = base["require"]
now = base["now"]
sha256 = base["sha256"]
atomic_json = base["atomic_json"]
dirty_packages = base["dirty_packages"]
provider_gate = base["provider_gate"]
inspect_grass = base["inspect_grass"]
generation_record = base["generation_record"]
vec = base["vec"]
rot = base["rot"]
distance = base["distance"]
rotation_delta = base["rotation_delta"]
CHECKS = base["CHECKS"]
PROJECT = base["PROJECT"]
HOME_MAP = base["HOME_MAP"]


def actor_class_name(actor):
    return actor.get_class().get_name()


class R55(R54Harness):
    def __init__(self):
        super().__init__()
        self.atmosphere = None
        self.atmosphere_actor = None
        self.original_visible = None
        self.original_hidden_in_game = None
        self.cloud_radius = None
        self.presenter = None
        self.report = {
            "schema": "redmmo.sky-atmosphere-visibility.r55.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "evidence_class": "real_gpu_visual",
            "capture_api": "URedPPGFoliageDiagnostics::RequestViewportScreenshot -> FScreenshotRequest::RequestScreenshot",
            "mutation_scope": "PIE-world SkyAtmosphereComponent visibility only; exact preimage restored before stop",
            "persistent_save": False,
            "r54_harness_dependency": {"path": str(R54_SOURCE), "sha256": R54_SHA256},
        }

    def set_phase(self, value):
        self.phase = value
        self.phase_started = time.monotonic()
        unreal.log("REDMMO_R55_PHASE " + value)

    def bind_pie(self):
        world = self.editor.get_game_world()
        if world is None or not self.level.is_in_play_in_editor():
            return False
        actors = list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor))
        spawners = [actor for actor in actors if actor_class_name(actor) == "PlanetSpawnerBP_C"]
        atmospheres = [actor for actor in actors if isinstance(actor, unreal.SkyAtmosphere)]
        clouds = [actor for actor in actors if isinstance(actor, unreal.VolumetricCloud)]
        presenters = [actor for actor in actors if actor_class_name(actor) == "RedPlanetNightPresenter"]
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        if len(spawners) != 1 or len(atmospheres) != 1 or len(clouds) != 1 or len(presenters) != 1 or pawn is None:
            return False
        atmosphere_components = list(atmospheres[0].get_components_by_class(unreal.SkyAtmosphereComponent))
        cloud_components = list(clouds[0].get_components_by_class(unreal.VolumetricCloudComponent))
        require(len(atmosphere_components) == 1, "expected one SkyAtmosphere component")
        require(len(cloud_components) == 1, "expected one VolumetricCloud component")
        self.world = world
        self.spawner = spawners[0]
        self.atmosphere_actor = atmospheres[0]
        self.atmosphere = atmosphere_components[0]
        self.presenter = presenters[0]
        self.original_visible = bool(self.atmosphere.get_editor_property("visible"))
        self.original_hidden_in_game = bool(self.atmosphere.get_editor_property("hidden_in_game"))
        self.cloud_radius = float(cloud_components[0].get_editor_property("planet_radius"))
        require(self.original_visible, "SkyAtmosphere visible preimage drift")
        require(not self.original_hidden_in_game, "SkyAtmosphere hidden-in-game preimage drift")
        require(abs(self.cloud_radius - 6360.0) <= 0.01, "cloud radius changed outside R55 scope")
        self.report["atmosphere_preimage"] = {
            "actor": self.atmosphere_actor.get_path_name(),
            "component": self.atmosphere.get_path_name(),
            "visible": self.original_visible,
            "hidden_in_game": self.original_hidden_in_game,
            "cloud_radius_km_unchanged": self.cloud_radius,
        }
        self.set_phase("WAIT_GENERATION")
        return True

    def presentation_state(self):
        return {
            "atmosphere_visible": bool(self.atmosphere.get_editor_property("visible")),
            "atmosphere_hidden_in_game": bool(self.atmosphere.get_editor_property("hidden_in_game")),
            "star_visibility_weight": float(self.presenter.get_editor_property("last_star_visibility_weight")),
            "night_fill_weight": float(self.presenter.get_editor_property("last_night_fill_weight")),
            "night_hemisphere_weight": float(self.presenter.get_editor_property("last_night_hemisphere_weight")),
            "cloud_radius_km": self.cloud_radius,
        }

    def request_baseline(self):
        self.baseline_camera, self.baseline_rotation = self.camera()
        self.report["baseline_request"] = {
            "utc": now(),
            "camera_location_cm": vec(self.baseline_camera),
            "camera_rotation_deg": rot(self.baseline_rotation),
            "presentation": self.presentation_state(),
            "grass": self.stable_grass("baseline"),
        }
        require(unreal.RedPPGFoliageDiagnostics.request_viewport_screenshot(str(BASELINE)), "baseline capture rejected")
        self.set_phase("WAIT_BASELINE")

    def apply_target(self):
        require(BASELINE.is_file() and BASELINE.stat().st_size > 0, "baseline capture missing")
        self.atmosphere.set_visibility(False, True)
        require(not bool(self.atmosphere.get_editor_property("visible")), "SkyAtmosphere visibility did not disable")
        require(not bool(self.atmosphere.get_editor_property("hidden_in_game")), "hidden-in-game changed outside R55 scope")
        self.report["target_applied_utc"] = now()
        self.set_phase("SETTLE_TARGET")

    def request_corrected(self):
        location, rotation = self.camera()
        require(distance(location, self.baseline_camera) <= 1.0, "camera location drift")
        require(rotation_delta(rotation, self.baseline_rotation) <= 0.1, "camera rotation drift")
        self.report["disabled_request"] = {
            "utc": now(),
            "camera_location_cm": vec(location),
            "camera_rotation_deg": rot(rotation),
            "camera_location_delta_cm": distance(location, self.baseline_camera),
            "camera_rotation_max_delta_deg": rotation_delta(rotation, self.baseline_rotation),
            "presentation": self.presentation_state(),
            "grass": self.stable_grass("disabled"),
        }
        require(unreal.RedPPGFoliageDiagnostics.request_viewport_screenshot(str(DISABLED)), "disabled capture rejected")
        self.set_phase("WAIT_CORRECTED")

    def restore(self):
        require(DISABLED.is_file() and DISABLED.stat().st_size > 0, "disabled capture missing")
        self.atmosphere.set_visibility(self.original_visible, True)
        require(bool(self.atmosphere.get_editor_property("visible")) == self.original_visible,
                "SkyAtmosphere visibility restoration failed")
        require(bool(self.atmosphere.get_editor_property("hidden_in_game")) == self.original_hidden_in_game,
                "SkyAtmosphere hidden-in-game preimage drift")
        self.report["restored_utc"] = now()
        self.set_phase("SETTLE_RESTORE")

    def request_stop(self):
        location, rotation = self.camera()
        require(distance(location, self.baseline_camera) <= 1.0, "post-restore camera location drift")
        require(rotation_delta(rotation, self.baseline_rotation) <= 0.1, "post-restore camera rotation drift")
        self.report["restored_state"] = {
            "camera_location_delta_cm": distance(location, self.baseline_camera),
            "camera_rotation_max_delta_deg": rotation_delta(rotation, self.baseline_rotation),
            "presentation": self.presentation_state(),
            "grass": self.stable_grass("restored"),
        }
        self.level.editor_request_end_play()
        self.set_phase("WAIT_STOP")

    def finish(self):
        require(not self.level.is_in_play_in_editor(), "PIE did not stop")
        require(dirty_packages() == {"content": [], "maps": []}, "PIE dirtied packages")
        for path, expected in CHECKS.items():
            require(sha256(path) == expected, "post-PIE drift: " + str(path))
        for path in (BASELINE, DISABLED):
            require(path.is_file() and path.stat().st_size > 0, "capture missing: " + str(path))
        self.report.update({
            "status": "PASS_R55_SKY_ATMOSPHERE_VISIBILITY_DISCRIMINATOR_PENDING_PIXEL_REVIEW",
            "completed_utc": now(),
            "captures": {
                "atmosphere_visible": {"path": str(BASELINE), "bytes": BASELINE.stat().st_size, "sha256": sha256(BASELINE)},
                "atmosphere_hidden": {"path": str(DISABLED), "bytes": DISABLED.stat().st_size, "sha256": sha256(DISABLED)},
            },
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "save_called": False,
            "claim_limit": "Matched existing-viewport D3D12 pixels pending independent review; no persistent correction or acceptance claim.",
        })
        atomic_json(RESULT, self.report)
        unreal.log("REDMMO_R55_PASS")
        self.schedule_quit(2.0)

    def fail(self, error):
        if self.atmosphere is not None and self.original_visible is not None:
            try:
                self.atmosphere.set_visibility(self.original_visible, True)
            except Exception:
                pass
        self.report.update({
            "status": "FAIL",
            "failed_phase": self.phase,
            "completed_utc": now(),
            "error": str(error),
            "traceback": traceback.format_exc(),
        })
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        if not RESULT.exists():
            atomic_json(RESULT, self.report)
        unreal.log_error("REDMMO_R55_FAIL " + str(error))
        self.schedule_quit(2.0)


try:
    _R55 = R55()
    _R55.start()
except Exception as bootstrap_error:
    DIAG.mkdir(parents=True, exist_ok=True)
    atomic_json(RESULT, {
        "schema": "redmmo.sky-atmosphere-visibility.r55.v1",
        "status": "FAIL",
        "completed_utc": now(),
        "error": str(bootstrap_error),
        "traceback": traceback.format_exc(),
    })
    unreal.SystemLibrary.quit_editor()
