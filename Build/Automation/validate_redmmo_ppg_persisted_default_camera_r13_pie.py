"""Fresh-process R13 default-camera proof followed by unchanged R11 flight telemetry.

The editor must already have the persisted home map open from process startup.
This validator never loads, reloads, saves, or transforms an editor actor.  It
records the untouched default gameplay camera before any input is injected,
then delegates the flight phases to the reviewed R11 validator unchanged.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import traceback

import unreal


BASE = r"D:\RedMMOTitan\Build\Automation\validate_redmmo_ppg_flight_r11_pie.py"
EXPECTED_BASE_SHA = "24562B5B2FB14BFE8F74F6D84059CEF7FD6FFD01E791F16C84599BCE097955C7"
EXPECTED_PERSISTED_MAP_SHA = "C9BE88085575E75E1790CB9306D564EB100F5ED2E75E012C1FD09EA110FDDFE0"
ROOT_R13 = (
    r"D:\RedMMOTitanWindowsData\Diagnostics"
    r"\RedMMO_PPG_PersistedDefaultCamera_R13V2_20260802"
)
DEFAULT_SCREENSHOT = os.path.join(
    ROOT_R13, "RedMMO_R13_persisted_default_camera_PIE_1920x1080.png"
)
EXPECTED_CHARACTER_MESH = "/Game/SoStylized/Demo/Pawn/Mannequin/Character/Mesh/SK_Mannequin"
EXPECTED_CHARACTER_ANIM = "/Game/SoStylized/Demo/Pawn/Mannequin/Animations/ThirdPerson_AnimBP"
EXPECTED_SHIP_MESH = "/Game/StarSparrow/Meshes/Examples/SM_StarSparrow01"
EXPECTED_SHIP_LABEL = "RedMMO_R12_ParkedStarSparrow_VisualOnly"
EXPECTED_RELATIVE_YAW = -5.282777
MAX_RELATIVE_PITCH_ROLL_DEG = 1.0
MAX_RELATIVE_YAW_ERROR_DEG = 1.0
MAX_RADIAL_DOT = 0.05
MIN_SHIP_DOT = 0.875


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _replace_exact(source: str, old: str, new: str, count: int = 1) -> str:
    actual = source.count(old)
    if actual != count:
        raise RuntimeError(
            f"Reviewed R11 validator marker drift: {old!r} count={actual}"
        )
    return source.replace(old, new)


if _sha256(BASE) != EXPECTED_BASE_SHA:
    raise RuntimeError("Reviewed R11 flight validator hash drift")
with open(BASE, "r", encoding="utf-8") as _handle:
    _source = _handle.read()
_source = _replace_exact(
    _source,
    'EXPECTED_MAP_SHA = "3F98136280504222E5340DB7044F0F3564E8BFFD7221C4EC2F2DF655CE2FFAEC"',
    f'EXPECTED_MAP_SHA = "{EXPECTED_PERSISTED_MAP_SHA}"',
)
_source = _replace_exact(
    _source,
    r'ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_Flight_R11_20260802"',
    r'ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_PersistedDefaultCamera_R13V2_20260802"',
)
_source = _replace_exact(
    _source,
    "validate_redmmo_ppg_flight_r11_state.json",
    "validate_redmmo_ppg_persisted_default_camera_r13_state.json",
)
_source = _replace_exact(
    _source,
    "validate_redmmo_ppg_flight_r11_result.json",
    "validate_redmmo_ppg_persisted_default_camera_r13_result.json",
)
_source = _replace_exact(
    _source,
    "RedMMO_R11_flight_descent_PIE_1920x1080.png",
    "RedMMO_R13_persisted_flight_descent_PIE_1920x1080.png",
)
_bootstrap = "\ntry:\n    _REDMMO_R11_FLIGHT_VALIDATION = FlightValidation()"
if _bootstrap not in _source:
    raise RuntimeError("Reviewed R11 validator bootstrap marker drift")
exec(compile(_source.split(_bootstrap, 1)[0], BASE, "exec"), globals(), globals())


def _asset_path(asset) -> str | None:
    if asset is None:
        return None
    path = str(asset.get_path_name()).split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    if "." in leaf:
        path = path.rsplit(".", 1)[0]
    if path.endswith("_C"):
        path = path[:-2]
    return path


def _rotation_record(value) -> dict[str, float]:
    return {
        "pitch": float(value.pitch),
        "yaw": float(value.yaw),
        "roll": float(value.roll),
    }


def _angle_error_degrees(actual: float, expected: float) -> float:
    return abs((float(actual) - float(expected) + 180.0) % 360.0 - 180.0)


def _d3d12_sm6_gate() -> dict[str, object]:
    command = str(unreal.SystemLibrary.get_command_line())
    match = re.search(r'(?i)-abslog=(?:"([^"]+)"|(\S+))', command)
    require(match, "Dedicated -abslog argument missing for RHI proof")
    log_path = match.group(1) or match.group(2)
    require(os.path.isfile(log_path), f"RHI proof log missing: {log_path}")
    with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
        log_text = handle.read()
    selected = bool(
        re.search(r"LogRHI: Using (?:Forced|Default) RHI: D3D12", log_text)
    )
    feature = "LogRHI: Using Highest Feature Level of D3D12: SM6" in log_text
    supported = (
        "LogRHI: RHI D3D12 with Feature Level SM6 is supported and will be used."
        in log_text
    )
    created = "Creating D3D12 RHI with Max Feature Level SM6" in log_text
    require(
        selected and feature and supported and created,
        "Fresh process is not proven D3D12/SM6",
    )
    return {
        "log": log_path,
        "selected_d3d12": selected,
        "feature_level_sm6": feature,
        "supported": supported,
        "created": created,
    }


def _bounds_record(actor) -> dict[str, list[float]]:
    origin, extent = actor.get_actor_bounds(False, False)
    return {"origin": vec(origin), "extent": vec(extent)}


def _recent_render_record(component) -> dict[str, object]:
    method = getattr(component, "was_recently_rendered", None)
    if not callable(method):
        return {"available": False, "reason": "UE Python method unavailable"}
    try:
        return {"available": True, "value": bool(method(1.0)), "tolerance_seconds": 1.0}
    except Exception as error:
        return {"available": False, "reason": str(error)}


class PersistedDefaultCameraValidation(FlightValidation):
    def __init__(self):
        super().__init__()
        self.ship = None
        self.character_mesh_component = None
        self.ship_mesh_component = None
        self.default_screenshot_issued = False
        self.clean_end_requested = False
        self.report.update(
            {
                "schema": "redmmo.ppg_persisted_default_camera.r13.real_pie.v1",
                "evidence_class": (
                    "real_d3d12_pie_persisted_default_camera_render_"
                    "and_unchanged_r11_flight_telemetry"
                ),
                "character_mesh_expected": EXPECTED_CHARACTER_MESH,
                "character_anim_expected": EXPECTED_CHARACTER_ANIM,
                "ship_mesh_expected": EXPECTED_SHIP_MESH,
                "ship_visual_only": True,
                "ship_grounding_accepted": False,
                "ship_grounding_next_gate": (
                    "normal-spawn runtime radial surface trace after PPG completion"
                ),
                "map_load_reload_called": False,
                "map_saved_by_validation": False,
                "default_view_rotation_writes": False,
                "playerstart_writes": False,
                "r11_flight_telemetry_inherited_unchanged": True,
                "visual_acceptance": {
                    "runtime_components_machine_gated": True,
                    "exact_full_character_and_ship_pixel_containment_machine_authoritative": False,
                    "human_screenshot_review_required": True,
                },
            }
        )

    def start(self):
        require(
            not os.path.exists(DEFAULT_SCREENSHOT),
            "R13 default screenshot no-clobber failed",
        )
        return super().start()

    def prepare(self):
        self.report["rhi"] = _d3d12_sm6_gate()
        editor_world = unreal.EditorLevelLibrary.get_editor_world()
        current = editor_world.get_path_name().split(":", 1)[0].split(".", 1)[0]
        require(current == MAP, f"Wrong editor map: {current}")
        starts = [
            actor
            for actor in unreal.EditorLevelLibrary.get_all_level_actors()
            if actor.get_class().get_name() == "PlayerStart"
        ]
        require(len(starts) == 1, f"Expected one persisted PlayerStart, found {len(starts)}")
        rotation = starts[0].get_actor_rotation()
        persisted = _rotation_record(rotation)
        require(abs(persisted["pitch"]) <= 0.05, f"Persisted PlayerStart pitch drift: {persisted}")
        require(abs(persisted["roll"]) <= 0.05, f"Persisted PlayerStart roll drift: {persisted}")
        require(
            _angle_error_degrees(persisted["yaw"], EXPECTED_RELATIVE_YAW) <= 0.05,
            f"Persisted PlayerStart yaw drift: {persisted}",
        )
        self.report["persisted_playerstart"] = {
            "path": starts[0].get_path_name(),
            "rotation": persisted,
            "read_only": True,
        }
        return super().prepare()

    def bind_pie(self) -> bool:
        if not super().bind_pie():
            return False
        mesh_components = [
            component
            for component in self.pawn.get_components_by_class(unreal.SkeletalMeshComponent)
            if component.get_skeletal_mesh_asset() is not None
        ]
        require(len(mesh_components) == 1, "Expected one runtime character mesh")
        character_mesh = mesh_components[0]
        require(
            _asset_path(character_mesh.get_skeletal_mesh_asset()) == EXPECTED_CHARACTER_MESH,
            "Runtime mannequin mesh mismatch",
        )
        require(
            _asset_path(character_mesh.get_editor_property("anim_class")) == EXPECTED_CHARACTER_ANIM,
            "Runtime mannequin AnimBP mismatch",
        )
        require(bool(character_mesh.get_editor_property("visible")), "Runtime mannequin is not visible")
        require(
            not bool(character_mesh.get_editor_property("hidden_in_game")),
            "Runtime mannequin is hidden in game",
        )
        actors = list(unreal.GameplayStatics.get_all_actors_of_class(self.world, unreal.Actor))
        ships = [actor for actor in actors if actor.get_actor_label() == EXPECTED_SHIP_LABEL]
        require(len(ships) == 1, "Expected one R12 visual ship reference in PIE")
        self.ship = ships[0]
        ship_components = [
            component
            for component in self.ship.get_components_by_class(unreal.StaticMeshComponent)
            if component.get_editor_property("static_mesh") is not None
        ]
        require(len(ship_components) == 1, "Expected one runtime ship mesh component")
        ship_mesh = ship_components[0]
        require(
            _asset_path(ship_mesh.get_editor_property("static_mesh")) == EXPECTED_SHIP_MESH,
            "Runtime StarSparrow mesh mismatch",
        )
        require(bool(ship_mesh.get_editor_property("visible")), "Runtime StarSparrow is not visible")
        require(
            not bool(ship_mesh.get_editor_property("hidden_in_game")),
            "Runtime StarSparrow is hidden in game",
        )
        require(not self.ship.get_actor_enable_collision(), "Visual-only ship collision is enabled")
        self.character_mesh_component = character_mesh
        self.ship_mesh_component = ship_mesh
        self.report["runtime_visual_contract"] = {
            "character_actor": self.pawn.get_path_name(),
            "character_mesh": EXPECTED_CHARACTER_MESH,
            "character_anim_blueprint": EXPECTED_CHARACTER_ANIM,
            "character_visible": True,
            "character_hidden_in_game": False,
            "ship_actor": self.ship.get_path_name(),
            "ship_mesh": EXPECTED_SHIP_MESH,
            "ship_visible": True,
            "ship_hidden_in_game": False,
            "ship_collision": "disabled",
            "ship_grounding_accepted": False,
            "character_bounds": _bounds_record(self.pawn),
            "ship_bounds": _bounds_record(self.ship),
        }
        return True

    def capture_default_view(self):
        camera_location, camera_rotation = player_view(self.controller, self.pawn)
        camera_forward = unreal.MathLibrary.get_forward_vector(camera_rotation)
        radial_up = normalized(sub(self.pawn.get_actor_location(), self.center))
        ship_direction = normalized(sub(self.ship.get_actor_location(), camera_location))
        gravity_direction = self.movement.get_gravity_direction()
        relative_camera = unreal.GravityController.get_gravity_relative_rotation(
            camera_rotation, gravity_direction
        )
        relative_control = unreal.GravityController.get_gravity_relative_rotation(
            self.controller.get_control_rotation(), gravity_direction
        )
        radial_dot = dot(camera_forward, radial_up)
        ship_dot = dot(camera_forward, ship_direction)
        yaw_error = _angle_error_degrees(relative_camera.yaw, EXPECTED_RELATIVE_YAW)
        character_recent = _recent_render_record(self.character_mesh_component)
        ship_recent = _recent_render_record(self.ship_mesh_component)
        self.report["default_view"] = {
            "camera_location": vec(camera_location),
            "camera_rotation": str(camera_rotation),
            "camera_forward": vec(camera_forward),
            "gravity_relative_camera_rotation": _rotation_record(relative_camera),
            "gravity_relative_control_rotation": _rotation_record(relative_control),
            "relative_yaw_error_degrees": yaw_error,
            "camera_forward_dot_radial_up": radial_dot,
            "camera_forward_dot_ship": ship_dot,
            "pawn_location": vec(self.pawn.get_actor_location()),
            "ship_location": vec(self.ship.get_actor_location()),
            "character_recent_render": character_recent,
            "ship_recent_render": ship_recent,
            "ship_center_within_broad_view_cone": ship_dot >= MIN_SHIP_DOT,
            "ship_grounding_accepted": False,
            "no_rotation_or_transform_write_before_capture": True,
        }
        require(
            abs(float(relative_camera.pitch)) <= MAX_RELATIVE_PITCH_ROLL_DEG,
            f"Default relative camera pitch failed: {relative_camera}",
        )
        require(
            abs(float(relative_camera.roll)) <= MAX_RELATIVE_PITCH_ROLL_DEG,
            f"Default relative camera roll failed: {relative_camera}",
        )
        require(
            yaw_error <= MAX_RELATIVE_YAW_ERROR_DEG,
            f"Default relative camera yaw failed: {relative_camera} error={yaw_error}",
        )
        require(abs(radial_dot) <= MAX_RADIAL_DOT, f"Default camera is not tangent: dot={radial_dot}")
        require(ship_dot >= MIN_SHIP_DOT, f"Ship reference is outside broad view cone: dot={ship_dot}")
        if ship_recent.get("available"):
            require(bool(ship_recent.get("value")), "Runtime ship reference was not rendered")
        unreal.SystemLibrary.execute_console_command(
            self.world,
            'HighResShot filename="{}" 1920x1080'.format(
                DEFAULT_SCREENSHOT.replace("\\", "/")
            ),
        )
        self.default_screenshot_issued = True
        self.set_phase("WAIT_DEFAULT_SCREENSHOT")

    def finish(self):
        require(
            os.path.isfile(DEFAULT_SCREENSHOT) and os.path.getsize(DEFAULT_SCREENSHOT) > 10000,
            "R13 default screenshot missing",
        )
        require(os.path.isfile(SCREENSHOT) and os.path.getsize(SCREENSHOT) > 10000,
                "R13 flight screenshot missing")
        require(sha256(MAP_FILE) == EXPECTED_MAP_SHA, "PIE changed persisted R13 home map")
        require(not dirty_packages(), f"PIE dirtied packages: {dirty_packages()}")
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "Protected checkpoint drift: " + path)
        self.report["default_screenshot"] = {
            "path": DEFAULT_SCREENSHOT,
            "sha256": sha256(DEFAULT_SCREENSHOT),
            "bytes": os.path.getsize(DEFAULT_SCREENSHOT),
            "resolution": [1920, 1080],
        }
        self.report["flight_screenshot"] = {
            "path": SCREENSHOT,
            "sha256": sha256(SCREENSHOT),
            "bytes": os.path.getsize(SCREENSHOT),
            "resolution": [1920, 1080],
        }
        self.report["status"] = "ENDING_PIE_AFTER_PASSING_CAMERA_AND_FLIGHT_GATES"
        self.set_phase("REQUEST_CLEAN_PIE_END")

    def finalize_after_clean_end(self):
        require(sha256(MAP_FILE) == EXPECTED_MAP_SHA, "Clean PIE end changed home map")
        require(not dirty_packages(), f"Clean PIE end left dirty packages: {dirty_packages()}")
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "Protected checkpoint drift after PIE: " + path)
        self.report["status"] = (
            "PASS_REAL_D3D12_PERSISTED_DEFAULT_CAMERA_AND_R11_FLIGHT_"
            "SHIP_VISIBILITY_ONLY_GROUNDING_UNRESOLVED"
        )
        self.report["cleanup"] = {
            "pie_end_requested": True,
            "pie_end_verified": True,
            "game_world_destroyed": True,
            "map_file_unchanged": True,
            "dirty_packages": [],
            "map_load_reload_called": False,
            "map_saved": False,
        }
        self.phase = "COMPLETE"
        self.report["phase"] = self.phase
        self.pawn = None
        self.controller = None
        self.movement = None
        self.world = None
        atomic_json(RESULT, self.report)
        atomic_json(STATE, self.report)
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        unreal.log("REDMMO_R13_PERSISTED_DEFAULT_CAMERA_AND_FLIGHT PASS")

    def fail(self, error):
        self.report["status"] = "FAIL"
        self.report["error"] = str(error)
        self.report["traceback"] = traceback.format_exc()
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        self.pawn = None
        self.controller = None
        self.movement = None
        self.world = None
        atomic_json(RESULT, self.report)
        atomic_json(STATE, self.report)
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        unreal.log_error("REDMMO_R13_PERSISTED_DEFAULT_CAMERA_AND_FLIGHT FAIL " + str(error))

    def tick(self, delta):
        try:
            elapsed = time.monotonic() - self.phase_started
            if self.phase == "WAIT_GENERATION":
                require(elapsed <= 180.0, "PPG generation timeout")
                if self.generation_ready() and elapsed >= 3.0:
                    unreal.SystemLibrary.execute_console_command(self.world, "r.SetRes 1920x1080w")
                    self.set_phase("SETTLE_UNTOUCHED_DEFAULT_VIEW")
                self.publish()
                return
            if self.phase == "SETTLE_UNTOUCHED_DEFAULT_VIEW":
                require(elapsed <= 30.0, "Default-view settle timeout")
                if elapsed >= 1.5:
                    self.capture_default_view()
                self.publish()
                return
            if self.phase == "WAIT_DEFAULT_SCREENSHOT":
                require(elapsed <= 60.0, "Default screenshot timeout")
                if os.path.isfile(DEFAULT_SCREENSHOT) and os.path.getsize(DEFAULT_SCREENSHOT) > 10000:
                    self.inject_fly_toggle()
                    self.set_phase("WAIT_F_TOGGLE")
                self.publish()
                return
            if self.phase == "REQUEST_CLEAN_PIE_END":
                require(not self.clean_end_requested, "Duplicate clean PIE end request")
                self.clean_end_requested = True
                self.set_phase("WAIT_CLEAN_PIE_END")
                self.level.editor_request_end_play()
                return
            if self.phase == "WAIT_CLEAN_PIE_END":
                require(elapsed <= 90.0, "Clean PIE shutdown timeout")
                if not self.level.is_in_play_in_editor() and self.editor.get_game_world() is None:
                    self.finalize_after_clean_end()
                return
            return super().tick(delta)
        except Exception as error:
            self.fail(error)


try:
    _REDMMO_R13_PERSISTED_DEFAULT_CAMERA_VALIDATION = PersistedDefaultCameraValidation()
    _REDMMO_R13_PERSISTED_DEFAULT_CAMERA_VALIDATION.start()
except Exception as _bootstrap_error:
    atomic_json(
        RESULT,
        {
            "schema": "redmmo.ppg_persisted_default_camera.r13.real_pie.v1",
            "status": "FAIL",
            "error": str(_bootstrap_error),
            "traceback": traceback.format_exc(),
        },
    )
    unreal.log_error(
        "REDMMO_R13_PERSISTED_DEFAULT_CAMERA_BOOTSTRAP_FAIL "
        + str(_bootstrap_error)
    )
