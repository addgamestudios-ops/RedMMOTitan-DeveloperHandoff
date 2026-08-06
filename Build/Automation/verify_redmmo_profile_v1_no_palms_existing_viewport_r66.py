"""Fresh-reload D3D12 proof for the project-owned R66 no-palms PPG binding.

Reuses the proven R52 non-resizing viewport lifecycle harness, while adding a
fresh MapCheck, serialized ProfileV1/R66 inspection, and a runtime census that
requires the disabled seeded palm mesh to have zero generated components.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import unreal


BASE_PATH = Path(r"D:\RedMMOTitan\Build\Automation\verify_redmmo_viewport_capture_lifecycle_r52.py")
R66_FILE = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_NoPalms_R66.uasset")
R66_ASSET = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles/DA_PPG_ProfileV1_NoPalms_R66"
PALM = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R09/Meshes/SM_Tree_OasisPalm01_R09"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_ProfileV1NoPalms_R66_20260805T2144Z\Capture")
RESULT = DIAG / "result.json"
CAPTURE = DIAG / "R66_no_repeated_palms_existing_viewport.png"


source = BASE_PATH.read_text(encoding="utf-8")
bootstrap = "\ntry:\n    _R52 = R52()"
if bootstrap not in source:
    raise RuntimeError("R52 bootstrap boundary missing")
namespace = {"__name__": "redmmo_r52_base_for_r66", "__file__": str(BASE_PATH)}
exec(compile(source.split(bootstrap, 1)[0], str(BASE_PATH), "exec"), namespace)

PROJECT = namespace["PROJECT"]
HOME_MAP = namespace["HOME_MAP"]
HOME_FILE = namespace["HOME_FILE"]
PROFILE_FILE = namespace["PROFILE_FILE"]
BINARY_FILE = namespace["BINARY_FILE"]
CHECKS = dict(namespace["CHECKS"])
CHECKS[BINARY_FILE] = "728992E6FEE98759114E26974337D2AC94B575CD6EC46E39FDECE5F8EE1AC71C"
CHECKS[PROFILE_FILE] = "4D22E5BD8DC106061BC3EF086BB95FA85AA570A4BAD66325E002135E1C7AC96F"
CHECKS[R66_FILE] = "C0EE6CB0A2D9D679D1FB4D64747555D55A5AF18ABED4AEC2666A1D5BECDA97DC"
namespace["CHECKS"] = CHECKS
namespace["DIAG"] = DIAG
namespace["RESULT"] = RESULT
namespace["CAPTURE"] = CAPTURE

Base = namespace["R52"]
require = namespace["require"]
now = namespace["now"]
sha256 = namespace["sha256"]
atomic_json = namespace["atomic_json"]
asset_path = namespace["asset_path"]
dirty_packages = namespace["dirty_packages"]
provider_gate = namespace["provider_gate"]
field = namespace["field"]
inspect_grass = namespace["inspect_grass"]


def command_log():
    command = str(unreal.SystemLibrary.get_command_line())
    match = re.search(r'(?i)-abslog=(?:"([^"]+)"|(\S+))', command)
    return (match.group(1) or match.group(2)) if match else str(PROJECT.parent / "Saved/Logs/RedMMO.log")


def map_check(world):
    log_path = Path(command_log())
    require(log_path.is_file(), "verifier log missing")
    offset = log_path.stat().st_size
    unreal.SystemLibrary.execute_console_command(world, "MAP CHECKDEP NOCLEARLOG")
    pattern = re.compile(r"MapCheck: Map check complete: (\d+) Error\(s\), (\d+) Warning\(s\)")
    for _ in range(120):
        time.sleep(0.1)
        with log_path.open("rb") as stream:
            stream.seek(min(offset, log_path.stat().st_size))
            matches = pattern.findall(stream.read().decode("utf-8", errors="replace"))
        if matches:
            errors, warnings = (int(value) for value in matches[-1])
            require(errors == 0 and warnings == 0, "MapCheck failed: {}/{}".format(errors, warnings))
            return {"errors": errors, "warnings": warnings, "log": str(log_path)}
    raise RuntimeError("no fresh MapCheck marker")


def inspect_palm(spawner):
    foliage = spawner.get_foliage_actor()
    if foliage is None:
        return {"components": 0, "instances": 0, "meshes": []}
    components = [
        component for component in list(foliage.get_components_by_class(unreal.StaticMeshComponent))
        if component.get_class().get_name() == "PPGGPUFoliageComponent"
        and asset_path(component.get_editor_property("static_mesh")) == PALM
    ]
    instances = 0
    for component in components:
        diag = unreal.RedPPGFoliageDiagnostics.inspect_component(component)
        instances += int(field(diag, "num_instances"))
    return {"components": len(components), "instances": instances, "meshes": [PALM] if components else []}


def verify_serialized_binding():
    profile = unreal.EditorAssetLibrary.load_asset(
        "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
    )
    foliage = unreal.EditorAssetLibrary.load_asset(R66_ASSET)
    require(profile is not None and profile.get_class().get_name() == "PlanetData", "ProfileV1 load failed")
    require(foliage is not None and foliage.get_class().get_name() == "FoliageData", "R66 load failed")
    require(int(profile.get_editor_property("generation_seed")) == 1337, "ProfileV1 seed drift")
    bindings = []
    for biome in list(profile.get_editor_property("biome_data")):
        bindings.append({"name": str(field(biome, "name")), "foliage_data": asset_path(field(biome, "foliage_data"))})
    require(
        [item["name"] for item in bindings if item["foliage_data"] == R66_ASSET] == ["Craters", "Hills", "Mountains"],
        "ProfileV1 R66 binding drift",
    )
    entries = list(foliage.get_editor_property("foliage_list"))
    require(len(entries) == 3, "R66 foliage entry count drift")
    require(abs(float(entries[0].get_editor_property("foliage_density"))) <= 1.0e-6, "R66 palm density is not zero")
    meshes = [asset_path(item.get_editor_property("mesh")) for item in list(entries[0].get_editor_property("meshes"))]
    require(meshes == [PALM], "R66 palm slot identity drift")
    return {"seed": 1337, "bindings": bindings, "tree_density": 0.0, "tree_mesh": PALM}


class R66(Base):
    def __init__(self):
        super().__init__()
        self.report.update({
            "schema": "redmmo.profile_v1_no_palms.verify.r66.v1",
            "evidence_class": "real_gpu_visual",
            "slice": "R66 fresh-reload no-palms seeded PPG proof",
        })

    def authenticate(self):
        active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(active == PROJECT.resolve(strict=True), "wrong project")
        require(not RESULT.exists() and not CAPTURE.exists(), "R66 verify no-clobber failed")
        for path, expected in CHECKS.items():
            require(path.is_file() and sha256(path) == expected, "input drift: " + str(path))
        require(dirty_packages() == {"content": [], "maps": []}, "editor started dirty")
        require(not self.level.is_in_play_in_editor(), "PIE already active")
        command = str(unreal.SystemLibrary.get_command_line()).lower()
        require("-d3d12" in command and "-renderoffscreen" in command and "-nullrhi" not in command, "renderer gate failed")
        require("-resx=1280" in command and "-resy=720" in command and "-forceres" in command, "viewport size gate failed")
        self.report["provider_gate_before"] = provider_gate()
        editor_world = unreal.EditorLevelLibrary.get_editor_world()
        require(editor_world is not None and editor_world.get_path_name().split(":", 1)[0].split(".", 1)[0] == HOME_MAP, "wrong map")
        self.report["serialized_binding"] = verify_serialized_binding()
        self.report["map_check"] = map_check(editor_world)
        self.level.editor_request_begin_play()
        self.set_phase("WAIT_PIE")

    def sample(self, force=False):
        before = len(self.timeline)
        super().sample(force)
        if len(self.timeline) > before and self.spawner is not None:
            self.timeline[-1]["palm"] = inspect_palm(self.spawner)

    def request_capture(self):
        grass = inspect_grass(self.spawner)
        palm = inspect_palm(self.spawner)
        require(grass["components"] == 196 and grass["instances"] == 2218356, "pre-capture grass census drift")
        require(grass["registered"] == 196 and grass["instance_data_ready"] == 196 and grass["scene_proxy"] == 196, "pre-capture grass readiness drift")
        require(palm["components"] == 0 and palm["instances"] == 0, "seeded palm component remains")
        self.report["pre_capture_state"] = grass
        self.report["pre_capture_palm_state"] = palm
        camera = unreal.GameplayStatics.get_player_camera_manager(self.world, 0)
        self.report["capture_camera_location"] = str(camera.get_actor_location()) if camera else None
        self.report["capture_camera_rotation"] = str(camera.get_actor_rotation()) if camera else None
        self.sample(True)
        accepted = unreal.RedPPGFoliageDiagnostics.request_viewport_screenshot(str(CAPTURE))
        require(accepted, "FScreenshotRequest bridge rejected request")
        self.capture_requested = time.monotonic()
        self.report["capture_requested_utc"] = now()
        self.set_phase("OBSERVE_POST_CAPTURE")
        self.sample(True)

    def analyze(self):
        analysis = super().analyze()
        palm_samples = [item["palm"] for item in self.timeline if item.get("palm") is not None]
        analysis["palm_sample_count"] = len(palm_samples)
        analysis["palm_zero_throughout"] = bool(palm_samples) and all(
            item["components"] == 0 and item["instances"] == 0 for item in palm_samples
        )
        require(analysis["palm_zero_throughout"], "palm census became nonzero")
        return analysis

    def finish(self):
        require(not self.level.is_in_play_in_editor(), "PIE did not stop")
        require(dirty_packages() == {"content": [], "maps": []}, "PIE dirtied packages")
        for path, expected in CHECKS.items():
            require(sha256(path) == expected, "post-PIE drift: " + str(path))
        require(CAPTURE.is_file() and CAPTURE.stat().st_size > 0, "capture missing")
        stable = self.report["lifecycle_analysis"]["readiness_stable"] and self.report["lifecycle_analysis"]["palm_zero_throughout"]
        self.report.update({
            "status": "PASS_R66_NO_PALMS_FRESH_RELOAD_MAPCHECK_D3D12" if stable else "FAIL_R66_RUNTIME_DRIFT",
            "completed_utc": now(),
            "capture": {"path": str(CAPTURE), "bytes": CAPTURE.stat().st_size, "sha256": sha256(CAPTURE)},
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "claim_limit": "Fresh-reload MapCheck, runtime palm/grass census and D3D12 pixels only; full planet visual acceptance and packaged-build readiness are not claimed.",
        })
        atomic_json(RESULT, self.report)
        unreal.log("REDMMO_R66_VERIFY_" + ("PASS" if stable else "FAIL"))
        self.phase = "DONE"
        self.schedule_quit(3.0)


try:
    _R66 = R66()
    _R66.start()
    unreal.log("REDMMO_R66_VERIFY_STARTED")
except Exception as bootstrap_error:
    atomic_json(RESULT, {
        "schema": "redmmo.profile_v1_no_palms.verify.r66.v1",
        "status": "FAIL",
        "completed_utc": now(),
        "error": str(bootstrap_error),
    })
    unreal.SystemLibrary.quit_editor()
