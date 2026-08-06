"""No-save D3D12 PIE acceptance for the clean RedMMO R86 rifle presentation.

The historical A01 harness supplies the proven ProfileV1 home-world bootstrap,
MapCheck, PPG readiness, exact Trooper/rifle discovery and Enhanced Input path.
This focused adapter walks the grounded Trooper, captures the pre-fire pose,
fires through IA_RedFire, verifies the exact runtime animation and Niagara
bindings plus the spawned Niagara component, captures the fire impulse, then
proves and captures deterministic locomotion restoration before clean teardown.
"""

from __future__ import annotations

import os
from pathlib import Path


BASE = Path(r"D:\RedMMOTitan\Build\Automation\validate_clean_redmmo_trooper_starsparrow_a01_pie.py")
PROJECT_ROOT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
PROJECT_FILE = PROJECT_ROOT / "RedMMO.uproject"
HOME_FILE = PROJECT_ROOT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
PROFILE_FILE = PROJECT_ROOT / r"Content\RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset"
PLAYER_FILE = PROJECT_ROOT / r"Content\RedMMO\Gameplay\Trooper\A01\Player\BP_RedTrooperPlayer_A01.uasset"
BOLT_FILE = PROJECT_ROOT / r"Content\RedMMO\Gameplay\Trooper\A01\Combat\BP_RedBolt_Trooper_A01.uasset"
FIRE_FILE = PROJECT_ROOT / r"Content\RedMMO\Anims\Rifle\A_Rifle_Fire_Single.uasset"
ABP_FILE = PROJECT_ROOT / r"Content\Action_Trooper\Animations\Tall_Female\ABP_ThirdPerson_Female_Tall.uasset"
MUZZLE_FILE = PROJECT_ROOT / r"Content\ProjectilesVol1\Effects\P_Flash_17.uasset"
MUZZLE_DEPENDENCIES = {
    PROJECT_ROOT / r"Content\ProjectilesVol1\Materials\MI_Flash26a.uasset":
        "F29008C271FDA7FF13E99590FC150E26CDAD9ED3A14B16EF82CB45D2EF7BA8C4",
    PROJECT_ROOT / r"Content\ProjectilesVol1\Materials\M_Circle41a.uasset":
        "691FA4E3054993D98699BA6C2C9900D3681841B8E51D7E7F93C0AA2CAECE0970",
    PROJECT_ROOT / r"Content\ProjectilesVol1\Textures\T_Circle41.uasset":
        "EE1AB2A5459699F07B03F29B19E19F387D03BA13D4453EB18943A07930EBAED6",
    PROJECT_ROOT / r"Content\ProjectilesVol1\Textures\T_Flash26.uasset":
        "69F0C7D7D86AE68CCB050EBF57B93B13DF6DAC097202AE856F3C56127D8A2310",
    PROJECT_ROOT / r"Content\ProjectilesVol1\Textures\T_Noise41.uasset":
        "8A7D828E71A9806E38073B848929A8B8C2A6BEBAACFA86E3E1711961CA1D7CA3",
}
EDITOR_DLL = PROJECT_ROOT / r"Binaries\Win64\UnrealEditor-RedMMO.dll"
SOURCE_CHARACTER_CPP = PROJECT_ROOT / r"Source\RedMMO\Private\RedPlayerCharacter.cpp"
SOURCE_CHARACTER_H = PROJECT_ROOT / r"Source\RedMMO\Public\RedPlayerCharacter.h"
SOURCE_BOLT = PROJECT_ROOT / r"Source\RedMMO\Private\RedBolt.cpp"
SOURCE_DIAGNOSTICS_CPP = PROJECT_ROOT / r"Source\RedMMO\Private\RedPPGFoliageDiagnostics.cpp"
SOURCE_DIAGNOSTICS_H = PROJECT_ROOT / r"Source\RedMMO\Public\RedPPGFoliageDiagnostics.h"

EXPECTED = {
    PROJECT_FILE: "3BF3D8D1D1C7F892A2CD4873F7C0390EC1AF3CA8F77E60549169563D18DBF86F",
    HOME_FILE: "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3",
    PROFILE_FILE: "D3F29BA1F3C2DBE5E6248787F4D0913E3D2B4D52E0DAB02E8B3329F5E343AD92",
    PLAYER_FILE: "186C50AE14CEF7FA3E3A0C492B86DCB680D2898A75E04C6DEBAB4A507B9F2B08",
    BOLT_FILE: "29ED70E6EA2115E2C7FA48C4F5F13A79222C3EEA8F3518F65ED749BE7EA52EDF",
    FIRE_FILE: "D8C17253D07F23A86F3B4835353A78E9FB3B2B7B19DB35938563F850CE11AF3B",
    ABP_FILE: "3F4DBD956EFCD7128B47F53C0592F2E896F42336B5426CBCEEEE84C153EAABE2",
    MUZZLE_FILE: "03D6E1A968858D2512A3210614D29354268D855B4E183257EC1CA5FC472421D8",
    EDITOR_DLL: "2A1FA34A76E3A7BAAFAE78C3A9F9BD31B9D2AA2AB633AE0368AA9103F84577F7",
    SOURCE_CHARACTER_CPP: "48910C2BBA6A9BEE27A919B5B266C826B4AA7CC8B46F687CB5E20B8C2250677D",
    SOURCE_CHARACTER_H: "F07B9521FE29D8C574DC0E909E1473BEA2146C2A2E783027BCA3F916E622592C",
    SOURCE_BOLT: "74214A105BF180D72D9EAA469216FB61082ADB70FE191AF47463A9E4C05ED05E",
    SOURCE_DIAGNOSTICS_CPP: "B03382DF71EA03E00C4E26E02BCDFC8D37C51DD2AE62DBF09ED276D1F02162F9",
    SOURCE_DIAGNOSTICS_H: "852EC7EFA3DC14C19140183395E49E507ACB09E816E0A31A9E4C094C1F2A56F3",
    **MUZZLE_DEPENDENCIES,
}

PPG_PLANET = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
EXPECTED_MUZZLE = "/Game/ProjectilesVol1/Effects/P_Flash_17"
REJECTED_MUZZLE = "/Game/ProjectilesVol1/Effects/P_Flash_4"
EXPECTED_FIRE = "/Game/RedMMO/Anims/Rifle/A_Rifle_Fire_Single"
EXPECTED_RIFLE_LOCOMOTION = "/Game/Action_Male_and_Female/Animations/UE4TF/A_Tall_Female_Sprint_Fwd_Rifle"
EXPECTED_ABP_CLASS = "/Game/Action_Trooper/Animations/Tall_Female/ABP_ThirdPerson_Female_Tall.ABP_ThirdPerson_Female_Tall_C"
CAPTURE_ENVS = {
    "before": "REDMMO_R86_BEFORE_CAPTURE",
    "fire": "REDMMO_R86_FIRE_CAPTURE",
    "restored": "REDMMO_R86_RESTORED_CAPTURE",
}

# R86 deliberately replaces the generic Action Trooper walk/run slots with the
# authenticated rifle-ready locomotion clips.  Select that already-supported
# base-harness profile before the historical source is compiled.
os.environ["REDMMO_A01_RIFLE_READY_PROFILE"] = "1"


source = BASE.read_text(encoding="utf-8")
bootstrap_marker = "\ntry:\n    _REDMMO_A01_PIE_VALIDATION = A01PIEValidation()"
marker_at = source.rfind(bootstrap_marker)
if marker_at < 0:
    raise RuntimeError("Historical A01 validator bootstrap marker drift")

ns = {"__name__": "redmmo_r86_presentation_base", "__file__": str(BASE)}
exec(compile(source[:marker_at], str(BASE), "exec"), ns)

unreal = ns["unreal"]
require = ns["require"]
sha256 = ns["sha256"]
asset_path = ns["asset_path"]
vec = ns["vec"]
length = ns["length"]
plane_project = ns["plane_project"]
distance = ns["distance"]
atomic_replace_json = ns["atomic_replace_json"]
A01PIEValidation = ns["A01PIEValidation"]

ns["HOME_SHA256"] = EXPECTED[HOME_FILE]
ns["PPG_PLANET"] = PPG_PLANET
ns["PPG_PLANET_FILE"] = PROFILE_FILE
ns["PPG_PLANET_SHA256"] = EXPECTED[PROFILE_FILE]
ns["EXPECTED_EDITOR_ACTOR_COUNT"] = 12


def output_paths(result_path: Path) -> dict[str, Path]:
    root = ns["DIAGNOSTICS_ROOT"].resolve(strict=True)
    resolved: dict[str, Path] = {}
    for label, env_name in CAPTURE_ENVS.items():
        raw = os.environ.get(env_name, "").strip()
        require(bool(raw), f"{env_name} is required")
        path = Path(raw).resolve(strict=False)
        require(os.path.commonpath([str(path), str(root)]) == str(root), f"Unsafe R86 {label} capture path")
        require(path.parent == result_path.parent, f"R86 {label} capture must share the report directory")
        require(path.suffix.lower() == ".png", f"R86 {label} capture must be PNG")
        require(not os.path.lexists(path), f"R86 {label} capture no-clobber failed: {path}")
        resolved[label] = path
    return resolved


def current_single_node_animation(component) -> str:
    # PlayAnimation/SetAnimation update the transient AnimSingleNodeInstance;
    # AnimationData is the serialized construction-time fallback and remains
    # null for this runtime-driven component.
    instance = component.get_anim_instance()
    instance_getter = getattr(instance, "get_animation_asset", None)
    animation = instance_getter() if callable(instance_getter) else None
    if animation is None:
        data = component.get_editor_property("animation_data")
        getter = getattr(data, "get_editor_property", None)
        require(callable(getter), "Single-node animation_data reflection is unavailable")
        animation = getter("anim_to_play")
    path = asset_path(animation)
    require(bool(path), "Single-node anim_to_play is null")
    return path


def live_animation_owner(component) -> dict:
    instance = component.get_anim_instance()
    instance_class = instance.get_class().get_path_name() if instance is not None else ""
    return {
        "mode": str(component.get_animation_mode()),
        "instance": instance.get_path_name() if instance is not None else "",
        "instance_class": instance_class,
    }


def active_muzzle_components(world, muzzle_location) -> list[dict]:
    records = []
    for component in unreal.ObjectIterator(unreal.NiagaraComponent):
        try:
            if not unreal.SystemLibrary.is_valid(component):
                continue
            asset = component.get_editor_property("asset")
            if asset_path(asset) != EXPECTED_MUZZLE:
                continue
            component_world = component.get_world()
            if component_world != world:
                continue
            location = component.get_world_location()
            active_getter = getattr(component, "is_active", None)
            active = bool(active_getter()) if callable(active_getter) else True
            records.append({
                "component": component.get_path_name(),
                "asset": asset_path(asset),
                "location": vec(location),
                "distance_to_rifle_muzzle_cm": distance(location, muzzle_location),
                "active": active,
                "visible": bool(component.get_editor_property("visible")),
                "hidden_in_game": bool(component.get_editor_property("hidden_in_game")),
            })
        except Exception:
            continue
    return sorted(records, key=lambda item: item["distance_to_rifle_muzzle_cm"])


def request_capture(self, label: str) -> None:
    path = self.r86_capture_paths[label]
    accepted = unreal.RedPPGFoliageDiagnostics.capture_game_viewport_screenshot(str(path))
    require(bool(accepted), f"R86 {label} exact game-viewport screenshot rejected")
    self.r86_capture_requested_at = ns["time"].monotonic()
    self.r86_capture_label = label


def record_capture(self, label: str, subject: str) -> None:
    path = self.r86_capture_paths[label]
    require(path.is_file() and path.stat().st_size > 0, f"R86 {label} capture missing")
    self.report.setdefault("captures", {})[label] = {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "capture_route": "synchronous exact GEngine GameViewport readback through project-owned diagnostics bridge",
        "subject": subject,
    }


def tangent_displacement(self) -> float:
    current = self.trooper.get_actor_location()
    up = self.radial_up(self.r86_walk_start)
    return length(plane_project(current - self.r86_walk_start, up))


def authenticate_r86(self) -> None:
    actual_project = Path(
        unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())
    ).resolve(strict=True)
    require(actual_project == PROJECT_FILE.resolve(strict=True), f"Wrong active project: {actual_project}")
    self.tracked_hashes = dict(EXPECTED)
    self.tracked_hashes.update(ns["PROTECTED_FILES"])
    self.tracked_before = ns["verify_hashes"](self.tracked_hashes, "R86 tracked input")
    self.config_before = ns["hash_tree"](PROJECT_ROOT / "Config")
    self.r86_capture_paths = output_paths(self.result_path)
    self.report.update({
        "schema": "redmmo.r86.infantry-presentation.real-d3d12-pie.v1",
        "evidence_class": "real_gpu_visual",
        "claim_limit": (
            "One-player no-save D3D12 RenderOffscreen PIE using the real A01 fire InputAction. "
            "Exact runtime binding/component/animation telemetry and three player-scale frames only; "
            "physical input, package, replication, multiplayer and human acceptance remain separate gates."
        ),
        "authenticated_inputs": {
            "active_project": str(actual_project),
            "tracked_hashes": self.tracked_before,
            "current_profile": PPG_PLANET,
            "current_editor_module_sha256": EXPECTED[EDITOR_DLL],
            "current_character_cpp_sha256": EXPECTED[SOURCE_CHARACTER_CPP],
            "current_character_h_sha256": EXPECTED[SOURCE_CHARACTER_H],
        },
    })


def verify_editor_contract_r86(self, world) -> None:
    require(ns["current_map"](world) == ns["HOME_MAP"], f"Wrong editor map: {ns['current_map'](world)}")
    settings = world.get_world_settings()
    game_mode = settings.get_editor_property("default_game_mode") if settings else None
    require(game_mode is not None and game_mode.get_path_name() == ns["GAME_MODE_CLASS"], "Current home GameMode drift")
    actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
    require(len(actors) == 12, f"Current editor actor count drift: {len(actors)}")
    spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
    require(len(spawners) == 1, f"Expected one PPG spawner, found {len(spawners)}")
    planet = spawners[0].get_editor_property("planet_data")
    require(asset_path(planet) == PPG_PLANET, f"Current ProfileV1 binding drift: {asset_path(planet)}")
    require(int(planet.get_editor_property("generation_seed")) == 1337, "PPG seed drift")
    require(bool(planet.get_editor_property("generate_water")), "Seeded native water disabled")
    self.report["editor_contract"] = {
        "map": ns["HOME_MAP"],
        "game_mode": ns["GAME_MODE_CLASS"],
        "actor_count": len(actors),
        "planet_data": PPG_PLANET,
        "generation_seed": 1337,
        "native_water_enabled": True,
    }


old_tick = A01PIEValidation.tick
old_finalize = A01PIEValidation.finalize_pass


def tick_r86(self, _delta_seconds: float) -> None:
    try:
        if self.phase == "R86_WALK_BEFORE":
            self.phase_frames += 1
            elapsed = ns["time"].monotonic() - self.phase_started
            require(elapsed <= 20.0, "R86 pre-fire walk timeout")
            self.inject("move", y=1.0)
            state = self.animation_state()
            owner = live_animation_owner(self.body) if self.phase_frames >= 20 else {}
            if (self.phase_frames >= 20 and "WALK" in state
                    and "ANIMATION_BLUEPRINT" in owner.get("mode", "").upper()
                    and owner.get("instance_class") == EXPECTED_ABP_CLASS):
                self.r86_before = {
                    "animation_state": state,
                    "animation_owner": owner,
                    "tangent_displacement_cm": tangent_displacement(self),
                    "location": vec(self.trooper.get_actor_location()),
                }
                request_capture(self, "before")
                self.set_phase("R86_WAIT_BEFORE_CAPTURE", reset_motion=False)
            self.publish_state()
            return

        if self.phase == "R86_WAIT_BEFORE_CAPTURE":
            self.phase_frames += 1
            self.inject("move", y=1.0)
            elapsed = ns["time"].monotonic() - self.r86_capture_requested_at
            require(elapsed <= 15.0, "R86 pre-fire capture timeout")
            path = self.r86_capture_paths["before"]
            if path.is_file() and path.stat().st_size > 0 and elapsed >= 0.15:
                record_capture(self, "before", "Trooper walking under exact ABP_ThirdPerson_Female_Tall before fire")
                self.bolts_before = {actor.get_path_name() for actor in self.bolt_actors()}
                self.muzzle_at_fire = self.weapon.get_socket_location(unreal.Name("Muzzle"))
                self.inject("fire", x=1.0)
                self.r86_fire_injected_at = ns["time"].monotonic()
                self.set_phase("R86_WAIT_FIRE_RUNTIME", reset_motion=False)
            else:
                self.publish_state()
            return

        if self.phase == "R86_WAIT_FIRE_RUNTIME":
            self.phase_frames += 1
            self.inject("move", y=1.0)
            self.inject("fire")
            elapsed = ns["time"].monotonic() - self.r86_fire_injected_at
            require(elapsed <= 4.0, "R86 fire did not produce complete presentation telemetry")
            candidates = [actor for actor in self.bolt_actors() if actor.get_path_name() not in self.bolts_before]
            if candidates:
                require(len(candidates) == 1, f"R86 fire created unexpected bolt count: {len(candidates)}")
                bolt = candidates[0]
                fire_animation = asset_path(self.trooper.get_editor_property("fire_animation"))
                muzzle_vfx = asset_path(self.trooper.get_editor_property("muzzle_vfx"))
                active_animation = current_single_node_animation(self.body)
                muzzle_components = active_muzzle_components(self.world, self.muzzle_at_fire)
                require(fire_animation == EXPECTED_FIRE, f"R86 fire animation binding drift: {fire_animation}")
                require(muzzle_vfx == EXPECTED_MUZZLE, f"R86 muzzle binding drift: {muzzle_vfx}")
                require(muzzle_vfx != REJECTED_MUZZLE, "Rejected P_Flash_4 is active")
                require(active_animation == EXPECTED_FIRE, f"R86 fire sequence did not become active: {active_animation}")
                require(muzzle_components, "Exact P_Flash_17 Niagara component was not observed after IA_RedFire")
                require(muzzle_components[0]["distance_to_rifle_muzzle_cm"] <= 10.0,
                        f"P_Flash_17 is not aligned to the rifle muzzle: {muzzle_components[0]}")
                require(muzzle_components[0]["visible"], "Observed P_Flash_17 component is not visible")
                require(not muzzle_components[0]["hidden_in_game"], "Observed P_Flash_17 component is hidden in game")
                self.new_bolt = bolt
                self.r86_fire = {
                    "fire_input_action": ns["ACTIONS"]["fire"],
                    "bolt": bolt.get_path_name(),
                    "fire_animation_binding": fire_animation,
                    "active_single_node_animation": active_animation,
                    "animation_owner_during_fire": live_animation_owner(self.body),
                    "muzzle_vfx_binding": muzzle_vfx,
                    "rejected_p_flash_4_active": False,
                    "rifle_muzzle_location": vec(self.muzzle_at_fire),
                    "muzzle_components": muzzle_components,
                    "muzzle_component_active_at_followup_poll": muzzle_components[0]["active"],
                    "tangent_displacement_cm": tangent_displacement(self),
                }
                # Read only the live game viewport. This tick follows the
                # injected fire frame, so its back buffer contains the bounded
                # fire pose/VFX without allowing an editor viewport to consume
                # or overwrite the request.
                request_capture(self, "fire")
                self.set_phase("R86_WAIT_FIRE_CAPTURE", reset_motion=False)
            self.publish_state()
            return

        if self.phase == "R86_WAIT_FIRE_CAPTURE":
            self.phase_frames += 1
            self.inject("move", y=1.0)
            self.inject("fire")
            elapsed = ns["time"].monotonic() - self.r86_capture_requested_at
            require(elapsed <= 15.0, "R86 fire capture timeout")
            path = self.r86_capture_paths["fire"]
            if path.is_file() and path.stat().st_size > 0 and elapsed >= 0.10:
                record_capture(self, "fire", "Actual IA_RedFire frame with exact P_Flash_17 and A_Rifle_Fire_Single active")
                self.r86_restore_started = ns["time"].monotonic()
                self.r86_restore_start_displacement = tangent_displacement(self)
                self.set_phase("R86_WAIT_RESTORE", reset_motion=False)
            else:
                self.publish_state()
            return

        if self.phase == "R86_WAIT_RESTORE":
            self.phase_frames += 1
            self.inject("move", y=1.0)
            self.inject("fire")
            elapsed = ns["time"].monotonic() - self.r86_restore_started
            require(elapsed <= 10.0, "R86 locomotion restoration timeout")
            if elapsed >= 0.40:
                state = self.animation_state()
                owner = live_animation_owner(self.body)
                displacement = tangent_displacement(self)
                require("WALK" in state or "RUN" in state, f"R86 locomotion state did not restore: {state}")
                require("ANIMATION_BLUEPRINT" in owner["mode"].upper(), f"R86 AnimBlueprint mode did not restore: {owner}")
                require(owner["instance_class"] == EXPECTED_ABP_CLASS, f"R86 exact AnimBlueprint did not restore: {owner}")
                require(displacement - self.r86_restore_start_displacement >= 20.0,
                        "R86 forward locomotion did not continue after the fire impulse")
                self.r86_restored = {
                    "animation_state": state,
                    "animation_owner": owner,
                    "tangent_displacement_cm": displacement,
                    "post_fire_displacement_cm": displacement - self.r86_restore_start_displacement,
                    "location": vec(self.trooper.get_actor_location()),
                }
                request_capture(self, "restored")
                self.set_phase("R86_WAIT_RESTORED_CAPTURE", reset_motion=False)
            self.publish_state()
            return

        if self.phase == "R86_WAIT_RESTORED_CAPTURE":
            self.phase_frames += 1
            self.inject("move", y=1.0)
            elapsed = ns["time"].monotonic() - self.r86_capture_requested_at
            require(elapsed <= 15.0, "R86 restored-locomotion capture timeout")
            path = self.r86_capture_paths["restored"]
            if path.is_file() and path.stat().st_size > 0 and elapsed >= 0.15:
                record_capture(self, "restored", "Trooper walking after deterministic fire-animation restoration")
                self.report["tests"]["r86_infantry_presentation"] = {
                    "before": self.r86_before,
                    "fire": self.r86_fire,
                    "restored": self.r86_restored,
                }
                self.request_stop()
            else:
                self.publish_state()
            return

        before = self.phase
        old_tick(self, _delta_seconds)
        if before == "WAIT_GROUNDED" and self.phase in ("WALK", "WAIT_FOLIAGE_SETTLE"):
            self.r86_walk_start = self.trooper.get_actor_location()
            self.set_phase("R86_WALK_BEFORE")
    except Exception as error:
        self.begin_failure(error)


def finalize_r86(self) -> None:
    old_finalize(self)
    require(set(self.report.get("captures", {})) == set(CAPTURE_ENVS), "R86 capture record incomplete")
    require("r86_infantry_presentation" in self.report.get("tests", {}), "R86 runtime presentation record missing")
    self.report.update({
        "status": "PASS_R86_INFANTRY_PRESENTATION_REAL_D3D12_PIE_PENDING_PIXEL_REVIEW",
        "evidence_class": "real_gpu_visual",
        "r86_runtime_gate": {
            "real_enhanced_input_fire": True,
            "exact_p_flash_17_runtime_binding": True,
            "p_flash_17_component_observed_at_rifle_muzzle": True,
            "rejected_p_flash_4_absent": True,
            "exact_a_rifle_fire_single_active": True,
            "exact_trooper_anim_blueprint_restored": True,
            "forward_locomotion_continued": True,
            "three_player_scale_frames_captured": True,
            "pixel_review_pending": True,
        },
    })
    atomic_replace_json(self.result_path, self.report)


A01PIEValidation.authenticate_inputs = authenticate_r86
A01PIEValidation.verify_editor_contract = verify_editor_contract_r86
A01PIEValidation.tick = tick_r86
A01PIEValidation.finalize_pass = finalize_r86

try:
    ns["_REDMMO_R86_PRESENTATION_VALIDATION"] = A01PIEValidation()
    ns["_REDMMO_R86_PRESENTATION_VALIDATION"].start()
except Exception as bootstrap_error:
    unreal.log_error("REDMMO_R86_PRESENTATION_BOOTSTRAP_FAIL " + str(bootstrap_error))
    try:
        unreal.SystemLibrary.quit_editor()
    except Exception:
        pass
