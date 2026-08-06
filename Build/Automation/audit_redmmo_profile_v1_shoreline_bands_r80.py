"""Fresh-reload/no-save real-D3D12 R80 exact seeded-coast audit."""

from pathlib import Path

import unreal


BASE = Path(r"D:\RedMMOTitan\Build\Automation\audit_redmmo_profile_v1_seeded_coast_water_r74.py")
source = BASE.read_text(encoding="utf-8")
prefix = source.rsplit("\nrequire(Path(unreal.Paths.convert_relative_path_to_full", 1)[0]
ns = {"__name__": "redmmo_r80_r74_base", "__file__": str(BASE)}
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
TARGET_PARENT_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\M_PPG_ProfileV1_ShorelineBands_R80.uasset"
TARGET_MI_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\MI_PPG_ProfileV1_ShorelineBands_R80.uasset"
WATER_PARENT_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\M_PPG_ProfileV1_OasisWater_R78.uasset"
WATER_MI_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\MI_PPG_ProfileV1_OasisWater_R78.uasset"
TARGET_PARENT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Materials/M_PPG_ProfileV1_ShorelineBands_R80"
TARGET_MI = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Materials/MI_PPG_ProfileV1_ShorelineBands_R80"
WATER_PARENT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Materials/M_PPG_ProfileV1_OasisWater_R78"
WATER_MI = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Materials/MI_PPG_ProfileV1_OasisWater_R78"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_ProfileV1ShorelineBands_R80_20260806T0150Z\Verify4")

expected = ns["EXPECTED"]
expected[PROFILE_FILE] = "D3F29BA1F3C2DBE5E6248787F4D0913E3D2B4D52E0DAB02E8B3329F5E343AD92"
expected[TARGET_PARENT_FILE] = "3815FE6D3822053E5540D77A253139BFFA290B1D5DA39E4F48C79D91D4463E87"
expected[TARGET_MI_FILE] = "61E1EC222F7360F1FB0EDDCC1BD908343FB2CC686E9963453EA27D9C2CECF16C"
expected[WATER_PARENT_FILE] = "B815972272713EDEC40A6CF33591E2FEF05F54D575C6049B29983330D23022F1"
expected[WATER_MI_FILE] = "2D3DFCC7583CABBCC551DD7D08A2CF5E33CC19465D14EAB5C4308DEC018DAE9A"

ns.update({
    "PROJECT": PROJECT,
    "HOME_FILE": HOME_FILE,
    "PROFILE_FILE": PROFILE_FILE,
    "NATIVE_WATER": WATER_MI,
    "EXPECTED": expected,
    "DIAG": DIAG,
    "CAPTURE_DIR": DIAG / "Capture",
    "RESULT": DIAG / "result.json",
    "LOG": DIAG / "verify.log",
    "ROLLBACK": Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeProfileV1ShorelineBandsAudit4_R80_20260806T0150Z"),
})

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
    "ROLLBACK": Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeProfileV1ShorelineBandsAudit4_R80_20260806T0150Z"),
})


def material_ancestry(material):
    result = []
    seen = set()
    current = material
    while current is not None and current.get_path_name() not in seen:
        seen.add(current.get_path_name())
        result.append(asset_path(current))
        try:
            current = current.get_editor_property("parent")
        except Exception:
            break
    return result


old_start = Audit.start


def start_r80(self):
    old_start(self)
    profile = unreal.EditorAssetLibrary.load_asset(ns["PROFILE"])
    require(profile is not None, "R80 ProfileV1 load failed")
    require(asset_path(profile.get_editor_property("planet_material")) == TARGET_MI, "R80 surface binding drift")
    require(asset_path(profile.get_editor_property("water_material")) == WATER_MI, "R78 water binding drift")
    instance = unreal.EditorAssetLibrary.load_asset(TARGET_MI)
    require(instance is not None and asset_path(instance.get_editor_property("parent")) == TARGET_PARENT, "R80 MI parent drift")
    editing = unreal.MaterialEditingLibrary
    scalar_names = {str(item) for item in editing.get_scalar_parameter_names(instance)}
    vector_names = {str(item) for item in editing.get_vector_parameter_names(instance)}
    texture_names = {str(item) for item in editing.get_texture_parameter_names(instance)}
    require({"R80_WetDepth", "R80_WetFeather"} <= scalar_names, "R80 scalar controls missing")
    require({"R80_WetSandTint", "R80_SubmergedSandTint"} <= vector_names, "R80 vector controls missing")
    require("BiomeMap" in texture_names, "R80 BiomeMap parameter missing")
    self.report.update({
        "schema": "redmmo.ppg.profile_v1_shoreline_bands.audit.r80.v1",
        "status": "RUNNING_R80",
        "evidence_class": "real_gpu_visual",
        "surface_successor": TARGET_MI,
        "water_successor_unchanged": WATER_MI,
        "persistent_map_or_asset_writes": False,
        "manual_plane_or_standin_created": False,
        "surface_controls": {
            "scalars": sorted(name for name in scalar_names if name.startswith("R80_")),
            "vectors": sorted(name for name in vector_names if name.startswith("R80_")),
            "runtime_texture": "BiomeMap",
        },
    })


def request_capture_r80(self):
    path = ns["CAPTURE_DIR"] / "R80_seeded_desert_coast_dry_wet_submerged_lit.png"
    require(not path.exists(), "R80 capture no-clobber failed")
    camera = unreal.GameplayStatics.get_player_camera_manager(self.world, 0)
    self.selected["capture_player_location"] = vec(self.pawn.get_actor_location())
    self.selected["capture_camera_location"] = vec(camera.get_actor_location()) if camera else None
    self.selected["capture_camera_rotation"] = str(camera.get_actor_rotation()) if camera else None
    self.selected["capture_path"] = str(path)
    surface_components = 0
    biome_map_bound = 0
    class_counts = {}
    for component in self.spawner.get_components_by_class(unreal.StaticMeshComponent):
        material = component.get_material(0)
        if material is None or TARGET_MI not in material_ancestry(material):
            continue
        surface_components += 1
        class_name = material.get_class().get_name()
        class_counts[class_name] = class_counts.get(class_name, 0) + 1
        getter = getattr(material, "get_texture_parameter_value", None)
        if callable(getter) and getter("BiomeMap") is not None:
            biome_map_bound += 1
    require(surface_components > 0, "R80 runtime surface components missing")
    require(biome_map_bound > 0, "R80 runtime BiomeMap texture not bound")
    self.r80_runtime_surface = {
        "component_count": surface_components,
        "biome_map_bound_count": biome_map_bound,
        "material_class_counts": class_counts,
    }
    require(unreal.RedPPGFoliageDiagnostics.request_viewport_screenshot(str(path)), "R80 viewport screenshot rejected")
    self.capture_requested = base_ns["time"].monotonic()
    self.set_phase("wait_capture")


def publish_r80(self):
    require(not self.level.is_in_play_in_editor() and self.editor.get_game_world() is None, "PIE still active")
    require(dirty_packages() == {"content": [], "maps": []}, "R80 audit dirtied packages")
    for path, expected_hash in expected.items():
        require(sha256(path) == expected_hash, "R80 post-run drift: " + str(path))
    require(len(self.records) == 1, "R80 coast capture missing")
    record = self.records[0]
    require(record["native_water_component_count"] > 0, "R80 native water components missing")
    require(record["native_water_visible_main_pass_count"] > 0, "R80 native water not in main pass")
    water_ancestry = [path for item in record["native_water_component_preview"] for path in item["material_ancestry"]]
    require(WATER_MI in water_ancestry and WATER_PARENT in water_ancestry, "R78 runtime water ancestry drift")
    runtime_surface = getattr(self, "r80_runtime_surface", None)
    require(runtime_surface is not None, "R80 live-PIE runtime surface evidence missing")
    capture = Path(record["capture_path"])
    require(capture.is_file() and capture.stat().st_size > 0, "R80 capture missing")
    self.report.update({
        "status": "PASS_R80_SHORELINE_BANDS_FRESH_RELOAD_LIT",
        "completed_utc": base_ns["now"](),
        "records": self.records,
        "runtime_surface": runtime_surface,
        "map_sha256_after": sha256(HOME_FILE),
        "profile_sha256_after": sha256(PROFILE_FILE),
        "target_parent_sha256_after": sha256(TARGET_PARENT_FILE),
        "target_mi_sha256_after": sha256(TARGET_MI_FILE),
        "water_parent_sha256_after": sha256(WATER_PARENT_FILE),
        "water_mi_sha256_after": sha256(WATER_MI_FILE),
        "capture_sha256": sha256(capture),
        "dirty_packages_after": dirty_packages(),
        "provider_gate_after": base_ns["provider_gate"](),
        "claim_limit": "One fresh-reload Lit D3D12 exact seeded Desert coast with runtime-bound R80 BiomeMap shoreline masks and unchanged R78 native water. This does not prove user art acceptance, every coastline, terrain smoothing, hands-on controls, packaging, replication or multiplayer.",
    })
    base_ns["write_json_exclusive"](ns["RESULT"], self.report)
    unreal.log_warning("REDMMO_R80_SHORELINE_BANDS_PASS " + str(record["capture_path"]))
    if self.handle is not None:
        unreal.unregister_slate_post_tick_callback(self.handle)
        self.handle = None
    unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), "QUIT_EDITOR")


Audit.start = start_r80
Audit.request_capture = request_capture_r80
Audit.publish = publish_r80

require(
    Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
    == PROJECT.resolve(strict=True),
    "wrong active project",
)
audit = Audit()
audit.handle = unreal.register_slate_post_tick_callback(audit.tick)
unreal.log("REDMMO_R80_SHORELINE_BANDS_STARTED")
