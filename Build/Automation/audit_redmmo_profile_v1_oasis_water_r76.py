"""Fresh-reload/no-save real-D3D12 R76 PPG Oasis-water shoreline audit."""

from pathlib import Path

import unreal


BASE = Path(r"D:\RedMMOTitan\Build\Automation\audit_redmmo_profile_v1_seeded_coast_water_r74.py")
source = BASE.read_text(encoding="utf-8")
prefix = source.rsplit(
    "\nrequire(Path(unreal.Paths.convert_relative_path_to_full", 1
)[0]
ns = {"__name__": "redmmo_r76_r74_base", "__file__": str(BASE)}
exec(compile(prefix, str(BASE), "exec"), ns)

Audit = ns["Audit"]
require = ns["require"]
sha256 = ns["sha256"]
dirty_packages = ns["dirty_packages"]
asset_path = ns["asset_path"]
vec = ns["vec"]

PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject")
CONTENT = PROJECT.parent / "Content"
HOME_FILE = CONTENT / r"RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
PROFILE_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
TARGET_PARENT_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\M_PPG_ProfileV1_OasisWater_R76.uasset"
TARGET_MI_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\MI_PPG_ProfileV1_OasisWater_R76.uasset"
TARGET_PARENT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Materials/M_PPG_ProfileV1_OasisWater_R76"
TARGET_MI = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Materials/MI_PPG_ProfileV1_OasisWater_R76"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_ProfileV1OasisWater_R76_20260806T0026Z\Verify2")

expected = ns["EXPECTED"]
expected[PROFILE_FILE] = "F733E34812872D5E0986DB9DAB6B7D61EA06E2FDCBC31DF99AC592BC2ED37F5B"
expected[TARGET_PARENT_FILE] = "62A00B4FF41BDB9C88907126C76D54C05595E17841355FFDF804C8B5AB7E4250"
expected[TARGET_MI_FILE] = "3B0AAFB59A2DD7DD65709958F7ACDE6A27C73A0CBEA1991B8EE04B992A2A3687"

ns.update({
    "PROJECT": PROJECT,
    "HOME_FILE": HOME_FILE,
    "PROFILE_FILE": PROFILE_FILE,
    "NATIVE_WATER": TARGET_MI,
    "EXPECTED": expected,
    "DIAG": DIAG,
    "CAPTURE_DIR": DIAG / "Capture",
    "RESULT": DIAG / "result.json",
    "LOG": DIAG / "verify.log",
    "ROLLBACK": Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeProfileV1OasisWaterAudit_R76_20260806T0043Z"),
})

# R74 wraps the R72 audit in its own namespace.  The state machine methods
# inherited from R72 retain that inner global dictionary, so route both
# namespaces to this fresh R76 evidence transaction.
base_ns = ns["ns"]
base_ns.update({
    "PROJECT": PROJECT,
    "MAP_FILE": HOME_FILE,
    "PROFILE_FILE": PROFILE_FILE,
    "EXPECTED": expected,
    "DIAG": DIAG,
    "CAPTURE_DIR": DIAG / "Capture",
    "RESULT": DIAG / "result.json",
    "LOG": DIAG / "verify.log",
    "ROLLBACK": Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeProfileV1OasisWaterAudit_R76_20260806T0043Z"),
})


old_start = Audit.start


def start_r76(self):
    old_start(self)
    self.report.update({
        "schema": "redmmo.ppg.profile_v1_oasis_water.audit.r76.v1",
        "status": "RUNNING_R76",
        "evidence_class": "real_gpu_visual",
        "water_successor": TARGET_MI,
        "persistent_map_or_asset_writes": False,
        "manual_plane_or_standin_created": False,
    })


def request_capture_r76(self):
    path = ns["CAPTURE_DIR"] / "R76_seeded_desert_coast_oasis_ppg_water_lit.png"
    require(not path.exists(), "R76 capture no-clobber failed")
    camera = unreal.GameplayStatics.get_player_camera_manager(self.world, 0)
    self.selected["capture_player_location"] = vec(self.pawn.get_actor_location())
    self.selected["capture_camera_location"] = vec(camera.get_actor_location()) if camera else None
    self.selected["capture_camera_rotation"] = str(camera.get_actor_rotation()) if camera else None
    self.selected["capture_path"] = str(path)
    require(unreal.RedPPGFoliageDiagnostics.request_viewport_screenshot(str(path)), "R76 viewport screenshot rejected")
    self.capture_requested = base_ns["time"].monotonic()
    self.set_phase("wait_capture")


def publish_r76(self):
    require(not self.level.is_in_play_in_editor() and self.editor.get_game_world() is None, "PIE still active")
    require(dirty_packages() == {"content": [], "maps": []}, "R76 audit dirtied packages")
    for path, expected_hash in expected.items():
        require(sha256(path) == expected_hash, "R76 post-run drift: " + str(path))
    require(len(self.records) == 1, "R76 coast capture missing")
    record = self.records[0]
    require(record["native_water_component_count"] > 0, "R76 native water components missing")
    require(record["native_water_visible_main_pass_count"] > 0, "R76 native water not in main pass")
    ancestry = [
        path
        for item in record["native_water_component_preview"]
        for path in item["material_ancestry"]
    ]
    require(TARGET_MI in ancestry and TARGET_PARENT in ancestry, "R76 runtime material ancestry drift")
    self.report.update({
        "status": "PASS_R76_PROJECT_OWNED_PPG_OASIS_WATER_FRESH_RELOAD_LIT",
        "completed_utc": ns["now"](),
        "records": self.records,
        "map_sha256_after": sha256(HOME_FILE),
        "profile_sha256_after": sha256(PROFILE_FILE),
        "target_parent_sha256_after": sha256(TARGET_PARENT_FILE),
        "target_mi_sha256_after": sha256(TARGET_MI_FILE),
        "dirty_packages_after": dirty_packages(),
        "provider_gate_after": ns["provider_gate"](),
        "claim_limit": "One fresh-reload Lit D3D12 seed-derived Desert shoreline and project-owned PPG-compatible Oasis-normal water-material audit. This does not prove final shoreline art, water gameplay, packaging, replication, multiplayer or user acceptance.",
    })
    ns["write_json_exclusive"](ns["RESULT"], self.report)
    unreal.log_warning("REDMMO_R76_OASIS_PPG_WATER_PASS " + str(record["capture_path"]))
    if self.handle is not None:
        unreal.unregister_slate_post_tick_callback(self.handle)
        self.handle = None
    unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), "QUIT_EDITOR")


Audit.start = start_r76
Audit.request_capture = request_capture_r76
Audit.publish = publish_r76

require(
    Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
    == PROJECT.resolve(strict=True),
    "wrong active project",
)
audit = Audit()
audit.handle = unreal.register_slate_post_tick_callback(audit.tick)
unreal.log("REDMMO_R76_OASIS_PPG_WATER_STARTED")
