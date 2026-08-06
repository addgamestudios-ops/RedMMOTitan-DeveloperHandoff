"""R63 matched-palette adapter over the proven non-resizing R52 capture."""

from pathlib import Path

import unreal


SOURCE = Path(r"D:\RedMMOTitan\Build\Automation\verify_redmmo_viewport_capture_lifecycle_r52.py")
scope = {"__name__": "redmmo_r63_capture"}
text = SOURCE.read_text(encoding="utf-8")
marker = "\ntry:\n    _R52 = R52()"
cut = text.find(marker)
if cut < 0:
    raise RuntimeError("R52 bootstrap shape changed")
exec(compile(text[:cut], str(SOURCE), "exec"), scope)

diag = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_MatchedPalette_R63_20260805T2112Z\CaptureB")
scope["DIAG"] = diag
scope["RESULT"] = diag / "capture_result.json"
scope["CAPTURE"] = diag / "R63_matched_sostylized_ground_and_dense_grass_existing_viewport.png"
scope["CHECKS"][scope["BINARY_FILE"]] = "728992E6FEE98759114E26974337D2AC94B575CD6EC46E39FDECE5F8EE1AC71C"
scope["CHECKS"].pop(scope["INSTANCE_A_FILE"])
scope["CHECKS"].pop(scope["INSTANCE_B_FILE"])

try:
    run = scope["R52"]()
    run.report["schema"] = "redmmo.matched_palette_existing_viewport.r63.v1"
    run.report["slice"] = "R63 matched SoStylized ground plus restrained approved dense grass palette"
    run.report["mutations"]["material_or_asset_write"] = False
    run.report["review_surface"] = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/MI_PPG_ProfileV1_Surface"
    run.report["grass_material_hash_gate"] = "authenticated by R63 apply result; temporary hashes retained for rollback verification"
    run.start()
    unreal.log("REDMMO_R63_CAPTURE_STARTED")
except Exception as error:
    scope["atomic_json"](
        scope["RESULT"],
        {
            "schema": "redmmo.matched_palette_existing_viewport.r63.v1",
            "status": "FAIL",
            "completed_utc": scope["now"](),
            "error": str(error),
            "traceback": scope["traceback"].format_exc(),
        },
    )
    unreal.SystemLibrary.quit_editor()
