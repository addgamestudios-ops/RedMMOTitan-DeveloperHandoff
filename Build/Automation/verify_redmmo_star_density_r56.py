"""R56 no-save analytic star-density discriminator at the saved night view.

Reuses the hash-pinned R54 harness helpers. The sole PIE-world write changes
ARedPlanetNightPresenter.StarDensity from its authenticated 0.004 preimage to
1.0 so every analytic cell is occupied, then restores 0.004 before PIE ends.
"""

from __future__ import annotations

import hashlib
import time
import traceback
from pathlib import Path

import unreal


R54_SOURCE = Path(r"D:\RedMMOTitan\Build\Automation\verify_redmmo_cloud_radius_surface_sky_r54.py")
R54_SHA256 = "7B5961C137C476F4A963BDEE8231881F21DE71933EE8A289C2CB17349F373ADC"
STAR_MATERIAL_FILE = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Environment\M_RedAnalyticStarDome.uasset")
STAR_MATERIAL_SHA256 = "E7C36E9E030527AEF5236232296A3AF6E5ECC6D99A886775BB0FD6620D21DA52"
PRESENTER_SOURCE = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Source\RedMMO\Private\RedPlanetNightPresenter.cpp")
PRESENTER_SOURCE_SHA256 = "69487B6649E230906F2A3234D4CE19C505DA029B1950E4A78E7BB84514921112"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_StarDensity_R56_20260805T1929Z")
RESULT = DIAG / "result.json"
BASELINE = DIAG / "R56_star_density_0004.png"
OCCUPIED = DIAG / "R56_star_density_1000.png"


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


if file_sha256(R54_SOURCE) != R54_SHA256:
    raise RuntimeError("R54 harness dependency drift")
if file_sha256(STAR_MATERIAL_FILE) != STAR_MATERIAL_SHA256:
    raise RuntimeError("star material preimage drift")
if file_sha256(PRESENTER_SOURCE) != PRESENTER_SOURCE_SHA256:
    raise RuntimeError("night presenter source preimage drift")

source = R54_SOURCE.read_text(encoding="utf-8")
marker = "\ntry:\n    _R54 = R54()"
if source.count(marker) != 1:
    raise RuntimeError("R54 bootstrap boundary drift")
base = {"__name__": "redmmo_r54_harness", "__file__": str(R54_SOURCE)}
exec(compile(source.split(marker, 1)[0], str(R54_SOURCE), "exec"), base)
base["DIAG"] = DIAG
base["RESULT"] = RESULT
base["BASELINE"] = BASELINE
base["CORRECTED"] = OCCUPIED

R54Harness = base["R54"]
require = base["require"]
now = base["now"]
sha256 = base["sha256"]
atomic_json = base["atomic_json"]
dirty_packages = base["dirty_packages"]
provider_gate = base["provider_gate"]
vec = base["vec"]
rot = base["rot"]
distance = base["distance"]
rotation_delta = base["rotation_delta"]
CHECKS = dict(base["CHECKS"])
CHECKS[STAR_MATERIAL_FILE] = STAR_MATERIAL_SHA256
CHECKS[PRESENTER_SOURCE] = PRESENTER_SOURCE_SHA256


class R56(R54Harness):
    def __init__(self):
        super().__init__()
        self.presenter = None
        self.star_dome = None
        self.original_density = None
        self.target_density = 1.0
        self.cloud_radius = None
        self.atmosphere_visible = None
        self.report = {
            "schema": "redmmo.star-density.r56.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "evidence_class": "real_gpu_visual",
            "capture_api": "URedPPGFoliageDiagnostics::RequestViewportScreenshot -> FScreenshotRequest::RequestScreenshot",
            "mutation_scope": "PIE-world RedPlanetNightPresenter.StarDensity only; exact preimage restored before stop",
            "persistent_save": False,
            "r54_harness_dependency": {"path": str(R54_SOURCE), "sha256": R54_SHA256},
        }

    def set_phase(self, value):
        self.phase = value
        self.phase_started = time.monotonic()
        unreal.log("REDMMO_R56_PHASE " + value)

    def bind_pie(self):
        world = self.editor.get_game_world()
        if world is None or not self.level.is_in_play_in_editor():
            return False
        actors = list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor))
        spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        presenters = [actor for actor in actors if actor.get_class().get_name() == "RedPlanetNightPresenter"]
        clouds = [actor for actor in actors if isinstance(actor, unreal.VolumetricCloud)]
        atmospheres = [actor for actor in actors if isinstance(actor, unreal.SkyAtmosphere)]
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        if len(spawners) != 1 or len(presenters) != 1 or len(clouds) != 1 or len(atmospheres) != 1 or pawn is None:
            return False
        star_components = [
            component for component in presenters[0].get_components_by_class(unreal.StaticMeshComponent)
            if component.get_name() == "StarDome"
        ]
        cloud_components = list(clouds[0].get_components_by_class(unreal.VolumetricCloudComponent))
        atmosphere_components = list(atmospheres[0].get_components_by_class(unreal.SkyAtmosphereComponent))
        require(len(star_components) == 1, "expected one StarDome component")
        require(len(cloud_components) == 1, "expected one VolumetricCloud component")
        require(len(atmosphere_components) == 1, "expected one SkyAtmosphere component")
        self.world = world
        self.spawner = spawners[0]
        self.presenter = presenters[0]
        self.star_dome = star_components[0]
        self.original_density = float(self.presenter.get_editor_property("star_density"))
        self.cloud_radius = float(cloud_components[0].get_editor_property("planet_radius"))
        self.atmosphere_visible = bool(atmosphere_components[0].get_editor_property("visible"))
        require(abs(self.original_density - 0.004) <= 0.00001, "star-density preimage drift")
        require(abs(self.cloud_radius - 6360.0) <= 0.01, "cloud radius changed outside R56 scope")
        require(self.atmosphere_visible, "SkyAtmosphere changed outside R56 scope")
        require(self.star_dome.get_material(0) is not None, "StarDome material missing")
        self.report["preimage"] = self.presentation_state()
        self.set_phase("WAIT_GENERATION")
        return True

    def presentation_state(self):
        material = self.star_dome.get_material(0)
        return {
            "star_density": float(self.presenter.get_editor_property("star_density")),
            "star_cell_scale": float(self.presenter.get_editor_property("star_cell_scale")),
            "star_point_radius": float(self.presenter.get_editor_property("star_point_radius")),
            "star_emission": float(self.presenter.get_editor_property("star_emission")),
            "star_visibility_weight": float(self.presenter.get_editor_property("last_star_visibility_weight")),
            "night_fill_weight": float(self.presenter.get_editor_property("last_night_fill_weight")),
            "night_hemisphere_weight": float(self.presenter.get_editor_property("last_night_hemisphere_weight")),
            "last_frame_resolved": bool(self.presenter.get_editor_property("last_frame_resolved")),
            "star_dome_visible": bool(self.star_dome.get_editor_property("visible")),
            "star_dome_hidden_in_game": bool(self.star_dome.get_editor_property("hidden_in_game")),
            "star_dome_material": material.get_path_name(),
            "star_dome_scale": vec(self.star_dome.get_world_scale()),
            "cloud_radius_km": self.cloud_radius,
            "atmosphere_visible": self.atmosphere_visible,
        }

    def request_baseline(self):
        self.baseline_camera, self.baseline_rotation = self.camera()
        self.report["baseline_request"] = {
            "utc": now(), "camera_location_cm": vec(self.baseline_camera),
            "camera_rotation_deg": rot(self.baseline_rotation),
            "presentation": self.presentation_state(),
            "grass": self.stable_grass("baseline"),
        }
        require(unreal.RedPPGFoliageDiagnostics.request_viewport_screenshot(str(BASELINE)), "baseline capture rejected")
        self.set_phase("WAIT_BASELINE")

    def apply_target(self):
        require(BASELINE.is_file() and BASELINE.stat().st_size > 0, "baseline capture missing")
        self.presenter.set_editor_property("star_density", self.target_density)
        require(abs(float(self.presenter.get_editor_property("star_density")) - self.target_density) <= 0.00001,
                "star-density target did not apply")
        self.report["target_applied_utc"] = now()
        self.set_phase("SETTLE_TARGET")

    def request_corrected(self):
        location, rotation = self.camera()
        require(distance(location, self.baseline_camera) <= 1.0, "camera location drift")
        require(rotation_delta(rotation, self.baseline_rotation) <= 0.1, "camera rotation drift")
        state = self.presentation_state()
        require(abs(state["star_density"] - self.target_density) <= 0.00001, "density drift before capture")
        require(state["last_frame_resolved"] and state["star_dome_visible"], "star presenter not resolved/visible")
        self.report["occupied_request"] = {
            "utc": now(), "camera_location_cm": vec(location),
            "camera_rotation_deg": rot(rotation),
            "camera_location_delta_cm": distance(location, self.baseline_camera),
            "camera_rotation_max_delta_deg": rotation_delta(rotation, self.baseline_rotation),
            "presentation": state,
            "grass": self.stable_grass("occupied"),
        }
        require(unreal.RedPPGFoliageDiagnostics.request_viewport_screenshot(str(OCCUPIED)), "occupied capture rejected")
        self.set_phase("WAIT_CORRECTED")

    def restore(self):
        require(OCCUPIED.is_file() and OCCUPIED.stat().st_size > 0, "occupied capture missing")
        self.presenter.set_editor_property("star_density", self.original_density)
        require(abs(float(self.presenter.get_editor_property("star_density")) - self.original_density) <= 0.00001,
                "star-density restoration failed")
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
        for path in (BASELINE, OCCUPIED):
            require(path.is_file() and path.stat().st_size > 0, "capture missing: " + str(path))
        self.report.update({
            "status": "PASS_R56_STAR_DENSITY_TRANSIENT_DISCRIMINATOR_PENDING_PIXEL_REVIEW",
            "completed_utc": now(),
            "captures": {
                "density_0_004": {"path": str(BASELINE), "bytes": BASELINE.stat().st_size, "sha256": sha256(BASELINE)},
                "density_1_0": {"path": str(OCCUPIED), "bytes": OCCUPIED.stat().st_size, "sha256": sha256(OCCUPIED)},
            },
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "save_called": False,
            "claim_limit": "Matched existing-viewport D3D12 pixels pending independent review; no persistent correction or art acceptance claim.",
        })
        atomic_json(RESULT, self.report)
        unreal.log("REDMMO_R56_PASS")
        self.schedule_quit(2.0)

    def fail(self, error):
        if self.presenter is not None and self.original_density is not None:
            try:
                self.presenter.set_editor_property("star_density", self.original_density)
            except Exception:
                pass
        self.report.update({"status": "FAIL", "failed_phase": self.phase, "completed_utc": now(),
                            "error": str(error), "traceback": traceback.format_exc()})
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        if not RESULT.exists():
            atomic_json(RESULT, self.report)
        unreal.log_error("REDMMO_R56_FAIL " + str(error))
        self.schedule_quit(2.0)


try:
    _R56 = R56()
    _R56.start()
except Exception as bootstrap_error:
    DIAG.mkdir(parents=True, exist_ok=True)
    atomic_json(RESULT, {"schema": "redmmo.star-density.r56.v1", "status": "FAIL",
                         "completed_utc": now(), "error": str(bootstrap_error),
                         "traceback": traceback.format_exc()})
    unreal.SystemLibrary.quit_editor()
