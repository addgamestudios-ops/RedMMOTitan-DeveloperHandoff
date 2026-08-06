"""R58 provider-off D3D12 verification of persisted StarDensity 0.08.

The source default is already changed and compiled before this harness runs.
This driver performs no editor-property mutation and saves no package. It
reloads the exact home map, verifies the live presenter inherits 0.08, and
captures two same-camera existing-viewport frames around a no-op settle phase.
"""

from __future__ import annotations

import hashlib
import time
import traceback
from pathlib import Path

import unreal


R57_SOURCE = Path(r"D:\RedMMOTitan\Build\Automation\verify_redmmo_star_density_candidate_r57.py")
R57_SHA256 = "D9ABBC9826C289015A0D8CB5E86E7AEE8E80BDCAB60469D3C089011044DC7DA8"
PROJECT_ROOT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
HEADER = PROJECT_ROOT / r"Source\RedMMO\Public\RedPlanetNightPresenter.h"
HEADER_SHA256 = "A4DEAF8C45A3318699F6D2B0367B6F61C7F17115C6681E07CBAA9882F4FB2B77"
BINARY = PROJECT_ROOT / r"Binaries\Win64\UnrealEditor-RedMMO.dll"
BINARY_SHA256 = "8D2276822AE6BA26329BD33E43E48B0C69297CE97BE7A206B18737BBE84978B2"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_StarDensityPersistence_R58_20260805T1947Z\RuntimeAttempt3")
RESULT = DIAG / "result.json"
PERSISTED = DIAG / "R58_persisted_density_0080.png"
CONFIRM = DIAG / "R58_persisted_density_0080_confirm.png"


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


if file_sha256(R57_SOURCE) != R57_SHA256:
    raise RuntimeError("R57 harness dependency drift")
if file_sha256(HEADER) != HEADER_SHA256:
    raise RuntimeError("persisted header drift")
if file_sha256(BINARY) != BINARY_SHA256:
    raise RuntimeError("built RedMMOEditor binary drift")

source = R57_SOURCE.read_text(encoding="utf-8")
marker = "\ntry:\n    _R57 = R57()"
if source.count(marker) != 1:
    raise RuntimeError("R57 bootstrap boundary drift")
namespace = {"__name__": "redmmo_r57_harness", "__file__": str(R57_SOURCE)}
exec(compile(source.split(marker, 1)[0], str(R57_SOURCE), "exec"), namespace)

namespace["DIAG"] = DIAG
namespace["RESULT"] = RESULT
namespace["BASELINE"] = PERSISTED
namespace["CANDIDATE"] = CONFIRM
namespace["OCCUPIED"] = CONFIRM
r56_namespace = namespace["namespace"]
r56_namespace["DIAG"] = DIAG
r56_namespace["RESULT"] = RESULT
r56_namespace["BASELINE"] = PERSISTED
r56_namespace["OCCUPIED"] = CONFIRM
r56_namespace["base"]["DIAG"] = DIAG
r56_namespace["base"]["RESULT"] = RESULT
r56_namespace["base"]["BASELINE"] = PERSISTED
r56_namespace["base"]["CORRECTED"] = CONFIRM

R57Harness = namespace["R57"]
require = namespace["require"]
now = namespace["now"]
sha256 = namespace["sha256"]
atomic_json = namespace["atomic_json"]
dirty_packages = namespace["dirty_packages"]
provider_gate = namespace["provider_gate"]
CHECKS = namespace["CHECKS"]
CHECKS[HEADER] = HEADER_SHA256
for checked_path in list(CHECKS):
    if checked_path.name == BINARY.name:
        CHECKS[checked_path] = BINARY_SHA256
r54_checks = r56_namespace["base"]["CHECKS"]
r54_checks[HEADER] = HEADER_SHA256
for checked_path in list(r54_checks):
    if checked_path.name == BINARY.name:
        r54_checks[checked_path] = BINARY_SHA256


class R58(R57Harness):
    def __init__(self):
        super().__init__()
        self.report = {
            "schema": "redmmo.star-density-persistence.r58.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "evidence_class": "real_gpu_visual",
            "capture_api": "URedPPGFoliageDiagnostics::RequestViewportScreenshot -> FScreenshotRequest::RequestScreenshot",
            "mutation_scope": "none; persisted source default and compiled binary read-only verification",
            "persistent_save": False,
            "expected_persisted_density": 0.08,
            "r57_harness_dependency": {"path": str(R57_SOURCE), "sha256": R57_SHA256},
            "header": {"path": str(HEADER), "sha256": HEADER_SHA256},
            "binary": {"path": str(BINARY), "sha256": BINARY_SHA256},
        }

    def set_phase(self, value):
        self.phase = value
        self.phase_started = time.monotonic()
        unreal.log("REDMMO_R58_PHASE " + value)

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
        self.target_density = self.original_density
        self.cloud_radius = float(cloud_components[0].get_editor_property("planet_radius"))
        self.atmosphere_visible = bool(atmosphere_components[0].get_editor_property("visible"))
        require(abs(self.original_density - 0.08) <= 0.00001, "persisted star-density is not 0.08")
        require(abs(self.cloud_radius - 6360.0) <= 0.01, "cloud radius changed outside R58 scope")
        require(self.atmosphere_visible, "SkyAtmosphere changed outside R58 scope")
        require(self.star_dome.get_material(0) is not None, "StarDome material missing")
        self.report["persisted_preimage"] = self.presentation_state()
        self.set_phase("WAIT_GENERATION")
        return True

    def apply_target(self):
        require(PERSISTED.is_file() and PERSISTED.stat().st_size > 0, "persisted capture missing")
        require(abs(float(self.presenter.get_editor_property("star_density")) - 0.08) <= 0.00001,
                "persisted density drift after first capture")
        self.report["read_only_settle_utc"] = now()
        self.set_phase("SETTLE_TARGET")

    def restore(self):
        require(CONFIRM.is_file() and CONFIRM.stat().st_size > 0, "confirmation capture missing")
        require(abs(float(self.presenter.get_editor_property("star_density")) - 0.08) <= 0.00001,
                "persisted density drift after confirmation")
        self.report["read_only_confirmed_utc"] = now()
        self.set_phase("SETTLE_RESTORE")

    def finish(self):
        require(not self.level.is_in_play_in_editor(), "PIE did not stop")
        require(dirty_packages() == {"content": [], "maps": []}, "PIE dirtied packages")
        for path, expected in CHECKS.items():
            require(sha256(path) == expected, "post-PIE drift: " + str(path))
        for path in (PERSISTED, CONFIRM):
            require(path.is_file() and path.stat().st_size > 0, "capture missing: " + str(path))
        self.report.update({
            "status": "PASS_R58_PERSISTED_DENSITY_008_RUNTIME_PENDING_PIXEL_REVIEW",
            "completed_utc": now(),
            "captures": {
                "persisted": {"path": str(PERSISTED), "bytes": PERSISTED.stat().st_size, "sha256": sha256(PERSISTED)},
                "confirmation": {"path": str(CONFIRM), "bytes": CONFIRM.stat().st_size, "sha256": sha256(CONFIRM)},
            },
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "save_called": False,
            "claim_limit": "Persisted-value runtime proof pending independent pixel review; not full night-sky, gameplay or player acceptance.",
        })
        atomic_json(RESULT, self.report)
        unreal.log("REDMMO_R58_PASS")
        self.schedule_quit(2.0)

    def fail(self, error):
        self.report.update({"status": "FAIL", "failed_phase": self.phase, "completed_utc": now(),
                            "error": str(error), "traceback": traceback.format_exc()})
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        if not RESULT.exists():
            atomic_json(RESULT, self.report)
        unreal.log_error("REDMMO_R58_FAIL " + str(error))
        self.schedule_quit(2.0)


try:
    _R58 = R58()
    _R58.start()
except Exception as bootstrap_error:
    DIAG.mkdir(parents=True, exist_ok=True)
    atomic_json(RESULT, {"schema": "redmmo.star-density-persistence.r58.v1", "status": "FAIL",
                         "completed_utc": now(), "error": str(bootstrap_error),
                         "traceback": traceback.format_exc()})
    unreal.SystemLibrary.quit_editor()
