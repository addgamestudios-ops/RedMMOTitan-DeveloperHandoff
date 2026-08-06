"""No-save D3D12 PIE acceptance for R88 grounded footstep ownership.

The historical A01 Trooper/StarSparrow validator supplies the proven full
character-to-ship-to-character Enhanced Input sequence.  The R60 adapter adds
the current radial camera steering.  This adapter authenticates current R73
PPG inputs and proves that the new project-owned footstep producer emits audio
only during grounded tangent movement, including after ship exit.
"""

from __future__ import annotations

from pathlib import Path


R60 = Path(
    r"D:\RedMMOTitan\Build\Automation"
    r"\validate_clean_redmmo_trooper_starsparrow_a01_pie_r60.py"
)
PROJECT_ROOT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
PROJECT_FILE = PROJECT_ROOT / "RedMMO.uproject"
HOME_FILE = PROJECT_ROOT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
PROFILE_FILE = PROJECT_ROOT / (
    r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1"
    r"\DA_PPG_ProfileV1_PlanetData.uasset"
)
R66_FOLIAGE_FILE = PROJECT_ROOT / (
    r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles"
    r"\DA_PPG_ProfileV1_NoPalms_R66.uasset"
)
R73_ROCK_FILE = PROJECT_ROOT / (
    r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles"
    r"\DA_PPG_ProfileV1_RockOnly_R73.uasset"
)
PLAYER_FILE = PROJECT_ROOT / (
    r"Content\RedMMO\Gameplay\Trooper\A01\Player"
    r"\BP_RedTrooperPlayer_A01.uasset"
)
BOLT_FILE = PROJECT_ROOT / (
    r"Content\RedMMO\Gameplay\Trooper\A01\Combat"
    r"\BP_RedBolt_Trooper_A01.uasset"
)
SOUND_FILE = PROJECT_ROOT / r"Content\SoStylized\Sounds\Step\SC_Steps_Dirt.uasset"
EDITOR_DLL = PROJECT_ROOT / r"Binaries\Win64\UnrealEditor-RedMMO.dll"
HEADER_FILE = PROJECT_ROOT / r"Source\RedMMO\Public\RedPlayerCharacter.h"
SOURCE_FILE = PROJECT_ROOT / r"Source\RedMMO\Private\RedPlayerCharacter.cpp"

PPG_PLANET = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
R66_FOLIAGE = (
    "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles/"
    "DA_PPG_ProfileV1_NoPalms_R66"
)
R73_ROCK = (
    "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles/"
    "DA_PPG_ProfileV1_RockOnly_R73"
)
EXPECTED_SOUND = "/Game/SoStylized/Sounds/Step/SC_Steps_Dirt.SC_Steps_Dirt"

EXPECTED = {
    PROJECT_FILE: "3BF3D8D1D1C7F892A2CD4873F7C0390EC1AF3CA8F77E60549169563D18DBF86F",
    HOME_FILE: "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3",
    PROFILE_FILE: "D3F29BA1F3C2DBE5E6248787F4D0913E3D2B4D52E0DAB02E8B3329F5E343AD92",
    R66_FOLIAGE_FILE: "C0EE6CB0A2D9D679D1FB4D64747555D55A5AF18ABED4AEC2666A1D5BECDA97DC",
    R73_ROCK_FILE: "4499F76A4B541D92BB7CCF66EA4C8B55C2AA0AC0CEEA4D4AFB964D2807EE7A1D",
    PLAYER_FILE: "186C50AE14CEF7FA3E3A0C492B86DCB680D2898A75E04C6DEBAB4A507B9F2B08",
    BOLT_FILE: "29ED70E6EA2115E2C7FA48C4F5F13A79222C3EEA8F3518F65ED749BE7EA52EDF",
    SOUND_FILE: "EFC10D81407F39E8C0B340B37DBCE8E2F784AB16B65EF82A0F6A1FF3149F0F67",
    EDITOR_DLL: "BFBB0348E660EF6852A55FDC1F735C07C013E3A13BDD533B35DE8734A69B2426",
    HEADER_FILE: "4FEA8A173A1022966E959D852878CB65327434F33EBBF29F95624D5B63E815D5",
    SOURCE_FILE: "BCD11DF53C33CC57559CF3351FA876C1DC27987999D7AC5EFBDD2ACBAC8182CC",
}


r60_source = R60.read_text(encoding="utf-8")
r60_bootstrap = (
    "\ntry:\n"
    "    base_globals[\"_REDMMO_A01_PIE_VALIDATION\"] = "
    "base_globals[\"A01PIEValidation\"]()"
)
r60_marker = r60_source.rfind(r60_bootstrap)
if r60_marker < 0:
    raise RuntimeError("R60 A01 adapter bootstrap marker drift")

r60_globals = {"__name__": "redmmo_r88_r60_adapter", "__file__": str(R60)}
exec(compile(r60_source[:r60_marker], str(R60), "exec"), r60_globals)

b = r60_globals["base_globals"]
unreal = b["unreal"]
require = b["require"]
asset_path = b["asset_path"]
vec = b["vec"]
A01PIEValidation = b["A01PIEValidation"]

b["HOME_SHA256"] = EXPECTED[HOME_FILE]
b["PPG_PLANET"] = PPG_PLANET
b["PPG_PLANET_FILE"] = PROFILE_FILE
b["PPG_PLANET_SHA256"] = EXPECTED[PROFILE_FILE]
b["EXPECTED_EDITOR_ACTOR_COUNT"] = 12
b["PPG_FOLIAGE"] = R66_FOLIAGE
b["ANIMATIONS"].update({
    "idle_animation": "/Game/Action_Male_and_Female/Animations/UE4TF/A_Tall_Female_Idle_Rifle",
    "walk_animation": "/Game/Action_Male_and_Female/Animations/UE4TF/A_Tall_Female_Sprint_Fwd_Rifle",
    "run_animation": "/Game/Action_Male_and_Female/Animations/UE4TF/A_Tall_Female_Sprint_Fwd_Rifle",
})


def footstep_counts(self):
    events = int(self.trooper.get_grounded_footstep_event_count())
    audio = int(self.trooper.get_grounded_footstep_audio_spawn_count())
    return {"events": events, "audio_spawns": audio}


def authenticate_r88(self) -> None:
    actual_project = Path(
        unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())
    ).resolve(strict=True)
    require(actual_project == PROJECT_FILE.resolve(strict=True), f"Wrong active project: {actual_project}")
    self.tracked_hashes = dict(EXPECTED)
    self.tracked_hashes.update(b["PROTECTED_FILES"])
    self.tracked_before = b["verify_hashes"](self.tracked_hashes, "R88 tracked input")
    self.config_before = b["hash_tree"](PROJECT_ROOT / "Config")
    self.report.update({
        "schema": "redmmo.r88.grounded-footsteps.real-d3d12-pie.v1",
        "claim_limit": (
            "One-player no-save D3D12 RenderOffscreen PIE using real A01 Enhanced Input. "
            "Grounded footstep event/audio telemetry, airborne silence, ship-flight silence, "
            "and post-exit grounded recovery only; physical-device feel, human audio/art review, "
            "package, replication, multiplayer, and standalone travel remain separate gates."
        ),
        "authenticated_inputs": {
            "active_project": str(actual_project),
            "tracked_hashes": self.tracked_before,
            "current_profile": PPG_PLANET,
            "approved_footstep_sound": EXPECTED_SOUND,
            "editor_module_sha256": EXPECTED[EDITOR_DLL],
            "source_header_sha256": EXPECTED[HEADER_FILE],
            "source_cpp_sha256": EXPECTED[SOURCE_FILE],
        },
    })


def verify_editor_contract_r88(self, world) -> None:
    require(b["current_map"](world) == b["HOME_MAP"], f"Wrong editor map: {b['current_map'](world)}")
    settings = world.get_world_settings()
    game_mode = settings.get_editor_property("default_game_mode") if settings else None
    require(game_mode is not None and game_mode.get_path_name() == b["GAME_MODE_CLASS"], "Current home GameMode drift")
    actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
    require(len(actors) == 12, f"Current editor actor count drift: {len(actors)}")
    require(not any(actor.get_actor_label() == b["OLD_VISUAL_LABEL"] for actor in actors), "Rejected visual-only ship returned")
    spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
    require(len(spawners) == 1, f"Expected one PPG spawner, found {len(spawners)}")
    planet = spawners[0].get_editor_property("planet_data")
    require(asset_path(planet) == PPG_PLANET, f"Current ProfileV1 binding drift: {asset_path(planet)}")
    require(int(planet.get_editor_property("generation_seed")) == 1337, "PPG seed drift")
    require(bool(planet.get_editor_property("generate_water")), "Seeded native water disabled")
    foliage_bindings = []
    for biome in list(planet.get_editor_property("biome_data")):
        for key, value in biome.to_dict().items():
            if str(key).replace("_", "").lower() in ("foliagedata", "forestfoliagedata"):
                foliage_bindings.append(asset_path(value))
    require(foliage_bindings.count(R66_FOLIAGE) == 1, f"R66 Hills foliage binding drift: {foliage_bindings}")
    require(foliage_bindings.count(R73_ROCK) == 2, f"R73 rock-only bindings drift: {foliage_bindings}")
    r66 = b["load_asset_exact"](R66_FOLIAGE)
    entries = list(r66.get_editor_property("foliage_list"))
    require(len(entries) == 3, "R66 foliage list cardinality drift")
    grass = [asset_path(item.get_editor_property("mesh")) for item in entries[1].get_editor_property("meshes")]
    require(grass == list(b["APPROVED_GRASS"]), f"Approved grass binding drift: {grass}")
    self.report["editor_contract"] = {
        "map": b["HOME_MAP"],
        "game_mode": b["GAME_MODE_CLASS"],
        "actor_count": len(actors),
        "planet_data": PPG_PLANET,
        "generation_seed": 1337,
        "native_water_enabled": True,
        "foliage_bindings": foliage_bindings,
        "approved_grass_bindings": grass,
        "palms_excluded_by_exact_r66_r73_hashes": True,
    }


old_tick = A01PIEValidation.tick
old_request_stop = A01PIEValidation.request_stop
old_finalize = A01PIEValidation.finalize_pass


def request_stop_r88(self) -> None:
    if not getattr(self, "r88_post_ship_verified", False):
        require(self.phase == "WAIT_TROOPER_REPOSSESSION", f"Premature R88 stop request in {self.phase}")
        require(footstep_counts(self) == self.r88_ship_baseline, "Footsteps fired during ship possession/flight")
        self.r88_post_ship_grounded_frames = 0
        self.set_phase("R88_WAIT_POST_SHIP_GROUNDED", reset_motion=False)
        return
    old_request_stop(self)


def tick_r88(self, delta_seconds: float) -> None:
    if self.phase == "R88_WAIT_POST_SHIP_GROUNDED":
        try:
            self.phase_frames += 1
            require(b["time"].monotonic() - self.phase_started <= 30.0, "Post-ship Trooper did not land")
            require(footstep_counts(self) == self.r88_ship_baseline, "Footsteps fired before post-ship landing")
            if not self.movement.is_falling():
                self.r88_post_ship_grounded_frames += 1
            else:
                self.r88_post_ship_grounded_frames = 0
            if self.r88_post_ship_grounded_frames >= 20:
                self.r88_post_ship_baseline = footstep_counts(self)
                self.set_phase("R88_POST_SHIP_GROUNDED_MOVE")
            self.publish_state()
        except Exception as error:
            self.begin_failure(error)
        return
    if self.phase == "R88_POST_SHIP_GROUNDED_MOVE":
        try:
            self.phase_frames += 1
            require(b["time"].monotonic() - self.phase_started <= 20.0, "Post-ship grounded footstep timeout")
            require(not self.movement.is_falling(), "Trooper became airborne during post-ship footstep proof")
            self.inject("move", y=1.0)
            motion = self.tangent_motion(self.trooper, self.phase_start_location)
            counts = footstep_counts(self)
            if motion["tangent_displacement_cm"] >= 300.0 and counts["events"] > self.r88_post_ship_baseline["events"]:
                require(counts["audio_spawns"] > self.r88_post_ship_baseline["audio_spawns"], "Post-ship step emitted no audio")
                self.report["tests"]["grounded_footsteps_after_ship_exit"] = {
                    "before": self.r88_post_ship_baseline,
                    "after": counts,
                    "motion": motion,
                    "sound": self.trooper.get_grounded_footstep_sound_path(),
                }
                self.r88_post_ship_verified = True
                old_request_stop(self)
            else:
                self.publish_state()
        except Exception as error:
            self.begin_failure(error)
        return

    before = self.phase
    old_tick(self, delta_seconds)
    try:
        after = self.phase
        if before in ("WAIT_GROUNDED", "WAIT_FOLIAGE_SETTLE") and after == "WALK":
            self.r88_walk_baseline = footstep_counts(self)
            require(self.trooper.get_grounded_footstep_sound_path() == EXPECTED_SOUND, "Runtime footstep sound drift")
        elif before == "WALK" and after == "WALK_SETTLE":
            counts = footstep_counts(self)
            require(counts["events"] > self.r88_walk_baseline["events"], "Walk emitted no grounded footsteps")
            require(counts["audio_spawns"] > self.r88_walk_baseline["audio_spawns"], "Walk emitted no footstep audio")
            self.report["tests"]["grounded_footsteps_walk"] = {"before": self.r88_walk_baseline, "after": counts, "sound": EXPECTED_SOUND}
        elif before == "WALK_SETTLE" and after == "SPRINT":
            self.r88_sprint_baseline = footstep_counts(self)
        elif before == "SPRINT" and after == "SPRINT_SETTLE":
            counts = footstep_counts(self)
            require(counts["events"] > self.r88_sprint_baseline["events"], "Sprint emitted no grounded footsteps")
            require(counts["audio_spawns"] > self.r88_sprint_baseline["audio_spawns"], "Sprint emitted no footstep audio")
            self.report["tests"]["grounded_footsteps_sprint"] = {"before": self.r88_sprint_baseline, "after": counts}
        elif before == "SPRINT_SETTLE" and after == "JUMP_PULSE":
            self.r88_jump_baseline = footstep_counts(self)
        if after in ("WAIT_AIRBORNE", "WAIT_LAND"):
            require(footstep_counts(self) == self.r88_jump_baseline, "Footstep fired during jump/fall")
        if before == "WAIT_LAND" and after == "FIRE_PULSE":
            require(footstep_counts(self) == self.r88_jump_baseline, "Jump landing changed footstep counters")
            self.report["tests"]["grounded_footsteps_airborne_silence"] = {"before_after": self.r88_jump_baseline}
        if before == "WAIT_SHIP_POSSESSION" and after == "SHIP_ASCEND":
            self.r88_ship_baseline = footstep_counts(self)
        if (after.startswith("SHIP_") or after == "WAIT_TROOPER_REPOSSESSION") and hasattr(self, "r88_ship_baseline"):
            require(footstep_counts(self) == self.r88_ship_baseline, "Footstep fired during ship possession/flight")
    except Exception as error:
        self.begin_failure(error)


def finalize_r88(self) -> None:
    old_finalize(self)
    for key in (
        "grounded_footsteps_walk",
        "grounded_footsteps_sprint",
        "grounded_footsteps_airborne_silence",
        "grounded_footsteps_after_ship_exit",
    ):
        require(key in self.report["tests"], f"Missing R88 runtime gate: {key}")
    self.report.update({
        "status": "PASS_R88_GROUNDED_FOOTSTEPS_A01_TROOPER_STARSPARROW_REAL_D3D12_PIE",
        "evidence_class": "automation",
        "r88_runtime_gate": {
            "walk_audio": True,
            "sprint_audio": True,
            "airborne_silent": True,
            "ship_flight_silent": True,
            "post_exit_grounded_audio": True,
            "approved_sound_exact": EXPECTED_SOUND,
        },
    })
    b["atomic_replace_json"](self.result_path, self.report)


A01PIEValidation.authenticate_inputs = authenticate_r88
A01PIEValidation.verify_editor_contract = verify_editor_contract_r88
A01PIEValidation.request_stop = request_stop_r88
A01PIEValidation.tick = tick_r88
A01PIEValidation.finalize_pass = finalize_r88

try:
    b["_REDMMO_R88_FOOTSTEP_VALIDATION"] = A01PIEValidation()
    b["_REDMMO_R88_FOOTSTEP_VALIDATION"].start()
except Exception as bootstrap_error:
    unreal.log_error("REDMMO_R88_FOOTSTEP_BOOTSTRAP_FAIL " + str(bootstrap_error))
    try:
        unreal.SystemLibrary.quit_editor()
    except Exception:
        pass
