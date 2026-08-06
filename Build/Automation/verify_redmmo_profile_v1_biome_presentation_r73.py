"""Fresh-reload, no-save D3D12 acceptance audit for R73.

The proven R72 four-role harness is reused after replacing only its immutable
inputs and its ground-placement selector.  The selector prefers a locally
flatter generated component for Desert so the third-person camera does not
intersect the surface; no generated data, actors, or packages are saved.
"""

from __future__ import annotations

import json
from pathlib import Path

import unreal


BASE = Path(r"D:\RedMMOTitan\Build\Automation\audit_redmmo_profile_v1_multi_biome_views_r72.py")
source = BASE.read_text(encoding="utf-8")
prefix = source.split("\nrequire(os.path.normcase", 1)[0]
ns = {"__name__": "redmmo_r73_verify_base", "__file__": str(BASE)}
exec(compile(prefix, str(BASE), "exec"), ns)

PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject")
CONTENT = PROJECT.parent / "Content"
HOME_FILE = CONTENT / r"RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
PROFILE_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
R66_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_NoPalms_R66.uasset"
R73_FOLIAGE_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_RockOnly_R73.uasset"
R73_PARENT_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\M_PPG_ProfileV1_BiomePresentation_R73.uasset"
R73_MI_FILE = CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\MI_PPG_ProfileV1_BiomePresentation_R73.uasset"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_ProfileV1BiomePresentation_R73_20260805T2343Z\Verify")

PROFILE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
R66 = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles/DA_PPG_ProfileV1_NoPalms_R66"
R73_FOLIAGE = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles/DA_PPG_ProfileV1_RockOnly_R73"
R73_PARENT = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Materials/M_PPG_ProfileV1_BiomePresentation_R73"
R73_MI = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Materials/MI_PPG_ProfileV1_BiomePresentation_R73"

EXPECTED = {
    HOME_FILE: "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3",
    PROFILE_FILE: "E19F14597BA1B73C958F6022B92A41B0C1A5F61573390295D3EEBD7484DBC335",
    R66_FILE: "C0EE6CB0A2D9D679D1FB4D64747555D55A5AF18ABED4AEC2666A1D5BECDA97DC",
    R73_FOLIAGE_FILE: "4499F76A4B541D92BB7CCF66EA4C8B55C2AA0AC0CEEA4D4AFB964D2807EE7A1D",
    R73_PARENT_FILE: "8D33435C91E0FE4813D5077991EDC6990AD5257395F67D6F5FDACBCE4F260992",
    R73_MI_FILE: "17C83A43FCB0AB9B22AC7EF499D53A8B7B2435B3F709CA585374E64F48371E91",
    Path(r"D:\RedMMOTitan\Build\Automation\apply_redmmo_profile_v1_seeded_land_start_r20.py"):
        "7707C56E13E9922A2F2D3ADBCE4CB7CCD917241B5F875EE631E347B5A70B83B7",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}

TARGETS = [
    {"label": "hills", "role": "Hills", "direction": [0.4212191481735607, -0.53125, 0.7350835780453403], "above_sea": True},
    {"label": "desert", "role": "Desert", "direction": [0.04692456666828282, 0.84375, -0.5346812345154763], "above_sea": True},
    {"label": "mountains", "role": "Mountains", "direction": [-0.20889049343814645, 0.59375, 0.7770622235388668], "above_sea": True},
    {"label": "ocean", "role": "Ocean", "direction": [0.3797986477904189, 0.78125, 0.4953800809848628], "above_sea": False},
]

# Replace the base harness inputs before constructing its Audit instance.
ns.update({
    "PROJECT": PROJECT,
    "MAP_FILE": HOME_FILE,
    "PROFILE_FILE": PROFILE_FILE,
    "R66_FILE": R66_FILE,
    "ROLE_PARENT_FILE": R73_PARENT_FILE,
    "ROLE_MI_FILE": R73_MI_FILE,
    "EXPECTED": EXPECTED,
    "PROFILE": PROFILE,
    "TARGETS": TARGETS,
    "ROLLBACK": Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeProfileV1BiomePresentationVerify_R73_20260805T2343Z"),
    "DIAG": DIAG,
    "CAPTURE_DIR": DIAG / "Capture",
    "RESULT": DIAG / "result.json",
    "LOG": DIAG / "verify.log",
})

Audit = ns["Audit"]
require = ns["require"]
asset_path = ns["asset_path"]
dirty_packages = ns["dirty_packages"]
sha256 = ns["sha256"]
add = ns["add"]
sub = ns["sub"]
mul = ns["mul"]
dot = ns["dot"]
length = ns["length"]
vec = ns["vec"]
sample_component = ns["sample_component"]
component_trace = ns["component_trace"]
tangent_for = ns["tangent_for"]


def field(value, wanted):
    values = value.to_dict()
    keynorm = lambda item: str(item).replace("_", "").replace(" ", "").lower()
    target = keynorm(wanted)
    matches = [key for key in values if keynorm(key) in (target, "b" + target)]
    require(len(matches) == 1, "missing reflected key " + wanted)
    return values[matches[0]]


def serialized_gate(self):
    profile = unreal.EditorAssetLibrary.load_asset(PROFILE)
    r66 = unreal.EditorAssetLibrary.load_asset(R66)
    rock_only = unreal.EditorAssetLibrary.load_asset(R73_FOLIAGE)
    parent = unreal.EditorAssetLibrary.load_asset(R73_PARENT)
    instance = unreal.EditorAssetLibrary.load_asset(R73_MI)
    require(all(item is not None for item in (profile, r66, rock_only, parent, instance)), "R73 serialized asset load failed")
    require(int(profile.get_editor_property("generation_seed")) == 1337, "R73 seed drift")
    require(asset_path(profile.get_editor_property("planet_material")) == R73_MI, "R73 material binding drift")
    bindings = {str(field(item, "name")): asset_path(field(item, "foliage_data")) for item in profile.get_editor_property("biome_data")}
    require(bindings.get("Hills") == R66, "Hills no longer uses dense R66 foliage")
    require(bindings.get("Mountains") == R73_FOLIAGE and bindings.get("Craters") == R73_FOLIAGE, "mountain/crater split drift")
    require(all(bindings.get(name) is None for name in ("Desert", "Ocean", "Poles")), "unexpected non-hill foliage binding")
    dense = list(r66.get_editor_property("foliage_list"))
    sparse = list(rock_only.get_editor_property("foliage_list"))
    require(len(dense) == 3 and len(sparse) == 3, "foliage list count drift")
    dense_values = [float(item.get_editor_property("foliage_density")) for item in dense]
    sparse_values = [float(item.get_editor_property("foliage_density")) for item in sparse]
    require(abs(dense_values[0]) <= 1.0e-6 and dense_values[1] > 0.0 and dense_values[2] > 0.0, "R66 density contract drift")
    require(abs(sparse_values[0]) <= 1.0e-6 and abs(sparse_values[1]) <= 1.0e-6 and sparse_values[2] > 0.0, "R73 rock-only density contract drift")
    require(asset_path(instance.get_editor_property("parent")) == R73_PARENT, "R73 MI parent drift")
    self.report["serialized_gate"] = {
        "bindings": bindings,
        "r66_density": dense_values,
        "r73_rock_only_density": sparse_values,
        "planet_material": R73_MI,
        "material_parent": R73_PARENT,
        "seed": 1337,
        "palm_density": dense_values[0],
    }


original_start = Audit.start


def start_r73(self):
    self.report.update({
        "schema": "redmmo.ppg.profile_v1_biome_presentation.verify.r73.v1",
        "status": "RUNNING",
        "r73_scope": "serialized foliage split plus four fresh real-GPU role views",
    })
    serialized_gate(self)
    original_start(self)


def select_and_place_r73(self):
    components = list(self.spawner.get_components_by_class(unreal.StaticMeshComponent))
    candidates = []
    for component in components:
        if (not component.is_query_collision_enabled()
                or component.get_editor_property("static_mesh") is None
                or isinstance(component, unreal.InstancedStaticMeshComponent)):
            continue
        location = component.get_world_location()
        delta = sub(location, self.center)
        if length(delta) < self.radius * 0.5:
            continue
        direction = ns["normalized"](delta)
        point = add(self.center, mul(direction, self.radius))
        try:
            sample = sample_component(self.world, component, point, self.center, self.radius)
        except Exception:
            continue
        if sample is None:
            continue
        dominant_index = int(sample["top3_biome_indices"][0])
        role = self.by_index.get(dominant_index, {"name": "UNKNOWN"})["name"]
        above = float(sample["raw_index_pixel"][3]) >= 0.999
        if role != self.target["role"] or above != self.target["above_sea"]:
            continue
        candidates.append((dot(direction, self.direction), float(sample["top3_biome_strengths"][0]), component, direction, sample))
    require(candidates, "no live generated candidate for " + self.target["role"])
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    traced = []
    for angular_dot, strength, component, direction, sample in candidates[:32]:
        try:
            hit_point, hit_normal = component_trace(component, self.center, self.radius, direction)
        except Exception:
            continue
        if dot(hit_normal, direction) < 0.0:
            hit_normal = mul(hit_normal, -1.0)
        flatness = abs(dot(hit_normal, direction))
        traced.append((flatness, angular_dot, strength, component, direction, sample, hit_point, hit_normal))
    require(traced, "no traceable candidate for " + self.target["role"])
    # Desert needs the flattest nearby patch to avoid the earlier camera/terrain
    # intersection. Other roles preserve nearest-direction priority.
    if self.target["role"] == "Desert":
        chosen = max(traced, key=lambda item: (item[0], item[1], item[2]))
    else:
        chosen = max(traced, key=lambda item: (item[1], item[2], item[0]))
    flatness, angular_dot, strength, component, direction, sample, hit_point, hit_normal = chosen
    radial_up = ns["normalized"](sub(hit_point, self.center))
    rotation = unreal.MathLibrary.make_rot_from_xz(tangent_for(radial_up), radial_up)
    location = add(hit_point, mul(radial_up, 220.0))
    require(self.pawn.set_actor_location(location, False, True) is not False, "ground placement failed")
    self.pawn.set_actor_rotation(rotation, True)
    self.controller.set_control_rotation(rotation)
    self.selected = {
        "label": self.target["label"],
        "role": self.target["role"],
        "component": component.get_path_name(),
        "component_direction": vec(direction),
        "stream_direction_dot": angular_dot,
        "dominant_strength": strength,
        "sea_authority_alpha": float(sample["raw_index_pixel"][3]),
        "at_or_above_sea": self.target["above_sea"],
        "trace_point": vec(hit_point),
        "trace_normal": vec(hit_normal),
        "radial_up": vec(radial_up),
        "local_flatness": flatness,
        "initial_player_location": vec(location),
        "rotation": [rotation.pitch, rotation.yaw, rotation.roll],
    }
    self.set_phase("settle_ground")


def request_capture_r73(self):
    path = ns["CAPTURE_DIR"] / ("R73_{}_player_surface_unlit.png".format(self.target["label"]))
    require(not path.exists(), "capture no-clobber failed: " + str(path))
    camera = unreal.GameplayStatics.get_player_camera_manager(self.world, 0)
    self.selected["capture_player_location"] = vec(self.pawn.get_actor_location())
    self.selected["capture_camera_location"] = vec(camera.get_actor_location()) if camera else None
    self.selected["capture_camera_rotation"] = str(camera.get_actor_rotation()) if camera else None
    self.selected["capture_path"] = str(path)
    accepted = unreal.RedPPGFoliageDiagnostics.request_viewport_screenshot(str(path))
    require(accepted, "viewport screenshot request rejected")
    self.capture_requested = ns["time"].monotonic()
    self.set_phase("wait_capture")


def publish_r73(self):
    require(not self.level.is_in_play_in_editor() and self.editor.get_game_world() is None, "PIE still active")
    require(dirty_packages() == {"content": [], "maps": []}, "R73 verify dirtied packages")
    for path, expected in EXPECTED.items():
        require(sha256(path) == expected, "post-run drift: " + str(path))
    require(len(self.records) == len(TARGETS), "incomplete capture set")
    hashes = [item["capture_sha256"] for item in self.records]
    require(len(set(hashes)) == len(hashes), "representative captures are byte-identical")
    self.report.update({
        "status": "PASS_R73_FRESH_RELOAD_MAPCHECK_FOUR_ROLE_D3D12_NO_SAVE",
        "completed_utc": ns["now"](),
        "records": self.records,
        "capture_sha256_distinct": True,
        "map_sha256_after": sha256(HOME_FILE),
        "profile_sha256_after": sha256(PROFILE_FILE),
        "dirty_packages_after": dirty_packages(),
        "provider_gate_after": ns["provider_gate"](),
        "claim_limit": "Fresh reload, MapCheck, serialized foliage split, and four Unlit D3D12 player views only; not final lit-art, coast-water, gameplay, packaging, replication, multiplayer, or user acceptance proof.",
    })
    ns["write_json_exclusive"](ns["RESULT"], self.report)
    unreal.log_warning("REDMMO_R73_VERIFY_PASS " + json.dumps({"captures": len(self.records), "roles": [item["role"] for item in self.records]}))
    if self.handle is not None:
        unreal.unregister_slate_post_tick_callback(self.handle)
        self.handle = None
    unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), "QUIT_EDITOR")


Audit.start = start_r73
Audit.select_and_place = select_and_place_r73
Audit.request_capture = request_capture_r73
Audit.publish = publish_r73

require(Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True) == PROJECT.resolve(strict=True), "wrong active project")
audit = Audit()
audit.handle = unreal.register_slate_post_tick_callback(audit.tick)
unreal.log("REDMMO_R73_VERIFY_STARTED")
