"""R64 existing-viewport adapter over the proven R52 lifecycle capture."""

from pathlib import Path

import unreal


SOURCE = Path(r"D:\RedMMOTitan\Build\Automation\verify_redmmo_viewport_capture_lifecycle_r52.py")
scope = {"__name__": "redmmo_r64_capture"}
text = SOURCE.read_text(encoding="utf-8")
marker = "\ntry:\n    _R52 = R52()"
cut = text.find(marker)
if cut < 0:
    raise RuntimeError("R52 bootstrap shape changed")
exec(compile(text[:cut], str(SOURCE), "exec"), scope)

diag = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_GroundHueSeparation_R64_20260805T2124Z\Capture")
scope["DIAG"] = diag
scope["RESULT"] = diag / "capture_result.json"
scope["CAPTURE"] = diag / "R64_warm_olive_painted_ground_approved_dense_grass_existing_viewport.png"
scope["CHECKS"][scope["BINARY_FILE"]] = "728992E6FEE98759114E26974337D2AC94B575CD6EC46E39FDECE5F8EE1AC71C"

try:
    run = scope["R52"]()
    run.report["schema"] = "redmmo.ground_hue_separation_existing_viewport.r64.v1"
    run.report["slice"] = "R64 warm-olive SoStylized painted ground under unchanged approved dense grass"
    run.report["mutations"]["material_or_asset_write"] = False
    run.report["review_surface"] = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/MI_PPG_ProfileV1_Surface"
    run.start()
    unreal.log("REDMMO_R64_CAPTURE_STARTED")
except Exception as error:
    scope["atomic_json"](
        scope["RESULT"],
        {
            "schema": "redmmo.ground_hue_separation_existing_viewport.r64.v1",
            "status": "FAIL",
            "completed_utc": scope["now"](),
            "error": str(error),
            "traceback": scope["traceback"].format_exc(),
        },
    )
    unreal.SystemLibrary.quit_editor()
