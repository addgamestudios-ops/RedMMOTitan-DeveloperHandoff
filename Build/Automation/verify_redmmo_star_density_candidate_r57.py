"""R57 no-save restrained analytic star-density candidate at the R56 camera."""

from __future__ import annotations

import hashlib
import time
import traceback
from pathlib import Path

import unreal


R56_SOURCE = Path(r"D:\RedMMOTitan\Build\Automation\verify_redmmo_star_density_r56.py")
R56_SHA256 = "A7E7D82BDC38719D5E6ABC1117580935F206795C9EE465E35B0E78C616214A08"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_StarDensityCandidate_R57_20260805T1938Z")
RESULT = DIAG / "result.json"
BASELINE = DIAG / "R57_star_density_0004.png"
CANDIDATE = DIAG / "R57_star_density_0080.png"


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


if file_sha256(R56_SOURCE) != R56_SHA256:
    raise RuntimeError("R56 harness dependency drift")

source = R56_SOURCE.read_text(encoding="utf-8")
marker = "\ntry:\n    _R56 = R56()"
if source.count(marker) != 1:
    raise RuntimeError("R56 bootstrap boundary drift")
namespace = {"__name__": "redmmo_r56_harness", "__file__": str(R56_SOURCE)}
exec(compile(source.split(marker, 1)[0], str(R56_SOURCE), "exec"), namespace)

namespace["DIAG"] = DIAG
namespace["RESULT"] = RESULT
namespace["BASELINE"] = BASELINE
namespace["OCCUPIED"] = CANDIDATE
namespace["base"]["DIAG"] = DIAG
namespace["base"]["RESULT"] = RESULT
namespace["base"]["BASELINE"] = BASELINE
namespace["base"]["CORRECTED"] = CANDIDATE

R56Harness = namespace["R56"]
require = namespace["require"]
now = namespace["now"]
sha256 = namespace["sha256"]
atomic_json = namespace["atomic_json"]
dirty_packages = namespace["dirty_packages"]
provider_gate = namespace["provider_gate"]
CHECKS = namespace["CHECKS"]


class R57(R56Harness):
    def __init__(self):
        super().__init__()
        self.target_density = 0.08
        self.report = {
            "schema": "redmmo.star-density-candidate.r57.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "evidence_class": "real_gpu_visual",
            "capture_api": "URedPPGFoliageDiagnostics::RequestViewportScreenshot -> FScreenshotRequest::RequestScreenshot",
            "mutation_scope": "PIE-world RedPlanetNightPresenter.StarDensity only; 0.004 restored before stop",
            "persistent_save": False,
            "r56_harness_dependency": {"path": str(R56_SOURCE), "sha256": R56_SHA256},
            "candidate_density": self.target_density,
        }

    def set_phase(self, value):
        self.phase = value
        self.phase_started = time.monotonic()
        unreal.log("REDMMO_R57_PHASE " + value)

    def finish(self):
        require(not self.level.is_in_play_in_editor(), "PIE did not stop")
        require(dirty_packages() == {"content": [], "maps": []}, "PIE dirtied packages")
        for path, expected in CHECKS.items():
            require(sha256(path) == expected, "post-PIE drift: " + str(path))
        for path in (BASELINE, CANDIDATE):
            require(path.is_file() and path.stat().st_size > 0, "capture missing: " + str(path))
        self.report.update({
            "status": "PASS_R57_STAR_DENSITY_008_CANDIDATE_PENDING_PIXEL_REVIEW",
            "completed_utc": now(),
            "captures": {
                "density_0_004": {"path": str(BASELINE), "bytes": BASELINE.stat().st_size, "sha256": sha256(BASELINE)},
                "density_0_08": {"path": str(CANDIDATE), "bytes": CANDIDATE.stat().st_size, "sha256": sha256(CANDIDATE)},
            },
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "save_called": False,
            "claim_limit": "Matched existing-viewport D3D12 art candidate pending independent review; no persistence or visual acceptance claim.",
        })
        atomic_json(RESULT, self.report)
        unreal.log("REDMMO_R57_PASS")
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
        unreal.log_error("REDMMO_R57_FAIL " + str(error))
        self.schedule_quit(2.0)


try:
    _R57 = R57()
    _R57.start()
except Exception as bootstrap_error:
    DIAG.mkdir(parents=True, exist_ok=True)
    atomic_json(RESULT, {"schema": "redmmo.star-density-candidate.r57.v1", "status": "FAIL",
                         "completed_utc": now(), "error": str(bootstrap_error),
                         "traceback": traceback.format_exc()})
    unreal.SystemLibrary.quit_editor()
