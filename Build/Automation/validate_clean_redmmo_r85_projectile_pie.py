"""Focused no-save D3D12 PIE acceptance for the clean RedMMO R85 tracer.

The historical A01 validator supplies the proven home-world PIE bootstrap and
real Enhanced Input fire path.  This adapter stops after the first authoritative
bolt, verifies the native mesh/material contract, parks that actual fired bolt
transiently in the player camera for one existing-viewport capture, tears PIE
down, and exits without saving content, maps, or config.
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
EDITOR_DLL = PROJECT_ROOT / r"Binaries\Win64\UnrealEditor-RedMMO.dll"
SOURCE_BOLT = PROJECT_ROOT / r"Source\RedMMO\Private\RedBolt.cpp"

EXPECTED = {
    PROJECT_FILE: "3BF3D8D1D1C7F892A2CD4873F7C0390EC1AF3CA8F77E60549169563D18DBF86F",
    HOME_FILE: "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3",
    PROFILE_FILE: "D3F29BA1F3C2DBE5E6248787F4D0913E3D2B4D52E0DAB02E8B3329F5E343AD92",
    PLAYER_FILE: "186C50AE14CEF7FA3E3A0C492B86DCB680D2898A75E04C6DEBAB4A507B9F2B08",
    BOLT_FILE: "29ED70E6EA2115E2C7FA48C4F5F13A79222C3EEA8F3518F65ED749BE7EA52EDF",
    EDITOR_DLL: "55B98B7AF5765CE14D5B82247EECF3913022CD8530A04ED07B63C1B037D1E008",
    SOURCE_BOLT: "74214A105BF180D72D9EAA469216FB61082ADB70FE191AF47463A9E4C05ED05E",
}

PPG_PLANET = "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/DA_PPG_ProfileV1_PlanetData"
EXPECTED_MESH = "/Engine/BasicShapes/Sphere.Sphere"
REJECTED_MESH_FRAGMENT = "/Game/ProjectilesVol1/Models/SM_Conus"
EXPECTED_MATERIAL = "/Game/RedMMO/Materials/M_BoltTracer.M_BoltTracer"
CAPTURE_ENV = "REDMMO_R85_PROJECTILE_CAPTURE"


source = BASE.read_text(encoding="utf-8")
bootstrap_marker = "\ntry:\n    _REDMMO_A01_PIE_VALIDATION = A01PIEValidation()"
marker_at = source.rfind(bootstrap_marker)
if marker_at < 0:
    raise RuntimeError("Historical A01 validator bootstrap marker drift")

ns = {"__name__": "redmmo_r85_projectile_base", "__file__": str(BASE)}
exec(compile(source[:marker_at], str(BASE), "exec"), ns)

unreal = ns["unreal"]
require = ns["require"]
sha256 = ns["sha256"]
asset_path = ns["asset_path"]
vec = ns["vec"]
atomic_replace_json = ns["atomic_replace_json"]
A01PIEValidation = ns["A01PIEValidation"]

# Bind the inherited runtime checks to the current saved clean-RedMMO home.
ns["HOME_SHA256"] = EXPECTED[HOME_FILE]
ns["PPG_PLANET"] = PPG_PLANET
ns["PPG_PLANET_FILE"] = PROFILE_FILE
ns["PPG_PLANET_SHA256"] = EXPECTED[PROFILE_FILE]
ns["EXPECTED_EDITOR_ACTOR_COUNT"] = 12


def capture_path(result_path: Path) -> Path:
    raw = os.environ.get(CAPTURE_ENV, "")
    require(bool(raw), f"{CAPTURE_ENV} is required")
    path = Path(raw).resolve(strict=False)
    root = ns["DIAGNOSTICS_ROOT"].resolve(strict=True)
    require(os.path.commonpath([str(path), str(root)]) == str(root), "Unsafe R85 capture path")
    require(path.parent == result_path.parent, "R85 capture must share the report directory")
    require(path.suffix.lower() == ".png", "R85 capture must be PNG")
    require(not os.path.lexists(path), f"R85 capture no-clobber failed: {path}")
    return path


def authenticate_r85(self) -> None:
    actual_project = Path(
        unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())
    ).resolve(strict=True)
    require(actual_project == PROJECT_FILE.resolve(strict=True), f"Wrong active project: {actual_project}")
    self.tracked_hashes = dict(EXPECTED)
    self.tracked_hashes.update(ns["PROTECTED_FILES"])
    self.tracked_before = ns["verify_hashes"](self.tracked_hashes, "R85 tracked input")
    self.config_before = ns["hash_tree"](PROJECT_ROOT / "Config")
    self.r85_capture_path = capture_path(self.result_path)
    self.report.update({
        "schema": "redmmo.r85.native-infantry-bolt.real-d3d12-pie.v1",
        "claim_limit": (
            "One-player no-save D3D12 RenderOffscreen PIE using the real A01 fire InputAction. "
            "Runtime mesh/material identity and one deliberately parked fired-bolt frame only; "
            "muzzle art, recoil animation, physical input, package, replication, multiplayer and "
            "human visual acceptance remain separate gates."
        ),
        "authenticated_inputs": {
            "active_project": str(actual_project),
            "tracked_hashes": self.tracked_before,
            "current_profile": PPG_PLANET,
            "current_profile_sha256": EXPECTED[PROFILE_FILE],
            "current_editor_module_sha256": EXPECTED[EDITOR_DLL],
            "current_bolt_source_sha256": EXPECTED[SOURCE_BOLT],
        },
    })


def verify_editor_contract_r85(self, world) -> None:
    require(ns["current_map"](world) == ns["HOME_MAP"], f"Wrong editor map: {ns['current_map'](world)}")
    settings = world.get_world_settings()
    game_mode = settings.get_editor_property("default_game_mode") if settings else None
    require(game_mode is not None and game_mode.get_path_name() == ns["GAME_MODE_CLASS"], "Current home GameMode drift")
    actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
    require(len(actors) == 12, f"Current editor actor count drift: {len(actors)}")
    require(not any(actor.get_actor_label() == ns["OLD_VISUAL_LABEL"] for actor in actors), "Rejected visual-only ship returned")
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
        "old_visual_ship_absent": True,
    }


def inspect_and_park_r85(self) -> None:
    bolt = self.new_bolt
    require(bolt is not None and unreal.SystemLibrary.is_valid(bolt), "Fired R85 bolt is no longer valid")
    meshes = list(bolt.get_components_by_class(unreal.StaticMeshComponent))
    require(len(meshes) == 1, f"Expected one RedBolt static mesh component, found {len(meshes)}")
    mesh_component = meshes[0]
    mesh = mesh_component.get_editor_property("static_mesh")
    material = mesh_component.get_material(0)
    mesh_path = mesh.get_path_name() if mesh is not None else ""
    material_path = material.get_path_name() if material is not None else ""
    scale = mesh_component.get_editor_property("relative_scale3d")
    require(mesh_path == EXPECTED_MESH, f"R85 bolt mesh drift: {mesh_path}")
    require(REJECTED_MESH_FRAGMENT not in mesh_path, f"Rejected SM_Conus remains active: {mesh_path}")
    require(material_path == EXPECTED_MATERIAL, f"R85 bolt material drift: {material_path}")
    require(abs(float(scale.x) - 1.6) <= 0.001, f"R85 bolt X scale drift: {scale.x}")
    require(abs(float(scale.y) - 0.07) <= 0.001, f"R85 bolt Y scale drift: {scale.y}")
    require(abs(float(scale.z) - 0.07) <= 0.001, f"R85 bolt Z scale drift: {scale.z}")
    require(bool(mesh_component.get_editor_property("visible")), "R85 bolt mesh is not visible")
    require(not bool(mesh_component.get_editor_property("hidden_in_game")), "R85 bolt mesh is hidden in game")

    movement = list(bolt.get_components_by_class(unreal.ProjectileMovementComponent))
    require(len(movement) == 1, f"Expected one projectile movement component, found {len(movement)}")
    movement[0].stop_movement_immediately()
    movement[0].deactivate()
    bolt.set_life_span(60.0)
    self.r85_mesh_component = mesh_component
    self.r85_runtime_identity = {
        "actor": bolt.get_path_name(),
        "static_mesh": mesh_path,
        "rejected_sm_conus_active": False,
        "material": material_path,
        "relative_scale": vec(scale),
        "visible": True,
        "hidden_in_game": False,
        "movement_deactivated_for_capture_only": True,
        "actual_fired_actor_reused_for_capture": True,
    }
    self.report["tests"]["r85_native_tracer_identity"] = self.r85_runtime_identity


def pin_bolt_r85(self) -> None:
    require(self.new_bolt is not None and unreal.SystemLibrary.is_valid(self.new_bolt), "R85 bolt expired before capture")
    manager = unreal.GameplayStatics.get_player_camera_manager(self.world, 0)
    require(manager is not None, "Player camera manager unavailable")
    location = manager.get_camera_location()
    rotation = manager.get_camera_rotation()
    forward = unreal.MathLibrary.get_forward_vector(rotation)
    up = unreal.MathLibrary.get_up_vector(rotation)
    target = location + forward * 350.0 + up * 12.0
    self.new_bolt.set_actor_location(target, False, False)
    self.new_bolt.set_actor_rotation(unreal.MathLibrary.make_rot_from_x(forward), False)
    self.r85_runtime_identity["capture_camera_location"] = vec(location)
    self.r85_runtime_identity["capture_camera_rotation"] = str(rotation)
    self.r85_runtime_identity["capture_actor_location"] = vec(target)
    self.r85_runtime_identity["capture_distance_cm"] = 350.0


old_tick = A01PIEValidation.tick
old_finalize = A01PIEValidation.finalize_pass


def tick_r85(self, delta_seconds: float) -> None:
    if self.phase == "R85_CAPTURE_SETTLE":
        try:
            self.phase_frames += 1
            require(ns["time"].monotonic() - self.phase_started <= 20.0, "R85 capture settle timeout")
            pin_bolt_r85(self)
            if self.phase_frames >= 20:
                accepted = unreal.RedPPGFoliageDiagnostics.request_viewport_screenshot(str(self.r85_capture_path))
                require(bool(accepted), "R85 existing-viewport screenshot request rejected")
                self.r85_capture_requested = ns["time"].monotonic()
                self.set_phase("R85_WAIT_CAPTURE", reset_motion=False)
            self.publish_state()
        except Exception as error:
            self.begin_failure(error)
        return
    if self.phase == "R85_WAIT_CAPTURE":
        try:
            self.phase_frames += 1
            pin_bolt_r85(self)
            elapsed = ns["time"].monotonic() - self.r85_capture_requested
            require(elapsed <= 30.0, "R85 projectile capture timeout")
            if self.r85_capture_path.is_file() and self.r85_capture_path.stat().st_size > 0 and elapsed >= 0.25:
                self.report["projectile_player_scale_capture"] = {
                    "path": str(self.r85_capture_path),
                    "bytes": self.r85_capture_path.stat().st_size,
                    "sha256": sha256(self.r85_capture_path),
                    "capture_route": "existing game viewport through project-owned read-only diagnostics bridge",
                    "capture_subject": "actual authoritative bolt created by IA_RedFire",
                    "capture_staging": "movement stopped and fired actor held 350 cm from the active player camera; runtime scale unchanged",
                }
                self.request_stop()
            else:
                self.publish_state()
        except Exception as error:
            self.begin_failure(error)
        return

    before = self.phase
    old_tick(self, delta_seconds)
    if before == "WAIT_GROUNDED" and self.phase in ("WALK", "WAIT_FOLIAGE_SETTLE"):
        # This focused slice requires a stable grounded spawn, then fires directly.
        self.set_phase("FIRE_PULSE")
    elif before == "WAIT_BOLT" and self.phase == "APPROACH_SHIP" and self.new_bolt is not None:
        try:
            inspect_and_park_r85(self)
            pin_bolt_r85(self)
            self.set_phase("R85_CAPTURE_SETTLE", reset_motion=False)
        except Exception as error:
            self.begin_failure(error)


def finalize_r85(self) -> None:
    old_finalize(self)
    require("projectile_player_scale_capture" in self.report, "R85 projectile capture record missing")
    self.report.update({
        "status": "PASS_R85_NATIVE_INFANTRY_TRACER_REAL_D3D12_PIE",
        "evidence_class": "real_gpu_visual",
        "r85_runtime_gate": {
            "real_enhanced_input_fire": True,
            "authoritative_spawn": True,
            "native_sphere_active": True,
            "rejected_sm_conus_absent": True,
            "project_owned_tracer_material_active": True,
            "player_scale_pixels_captured": True,
        },
    })
    atomic_replace_json(self.result_path, self.report)


A01PIEValidation.authenticate_inputs = authenticate_r85
A01PIEValidation.verify_editor_contract = verify_editor_contract_r85
A01PIEValidation.tick = tick_r85
A01PIEValidation.finalize_pass = finalize_r85

try:
    ns["_REDMMO_R85_PROJECTILE_VALIDATION"] = A01PIEValidation()
    ns["_REDMMO_R85_PROJECTILE_VALIDATION"].start()
except Exception as bootstrap_error:
    unreal.log_error("REDMMO_R85_PROJECTILE_BOOTSTRAP_FAIL " + str(bootstrap_error))
    try:
        unreal.SystemLibrary.quit_editor()
    except Exception:
        pass
