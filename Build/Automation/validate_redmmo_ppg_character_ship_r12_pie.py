"""Extend the proven R11 flight gate with R12 character/ship real-GPU proof."""

from __future__ import annotations

import hashlib
import os
import traceback

import unreal


BASE = r"D:\RedMMOTitan\Build\Automation\validate_redmmo_ppg_flight_r11_pie.py"
EXPECTED_BASE_SHA = "24562B5B2FB14BFE8F74F6D84059CEF7FD6FFD01E791F16C84599BCE097955C7"
R12_ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_CharacterShip_R12_20260802"
GROUND_SCREENSHOT = os.path.join(R12_ROOT, "RedMMO_R12_character_ship_ground_PIE_1920x1080.png")
EXPECTED_CHARACTER_MESH = "/Game/SoStylized/Demo/Pawn/Mannequin/Character/Mesh/SK_Mannequin"
EXPECTED_CHARACTER_ANIM = "/Game/SoStylized/Demo/Pawn/Mannequin/Animations/ThirdPerson_AnimBP"
EXPECTED_SHIP_MESH = "/Game/StarSparrow/Meshes/Examples/SM_StarSparrow01"
EXPECTED_SHIP_LABEL = "RedMMO_R12_ParkedStarSparrow_VisualOnly"


def _sha(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


if _sha(BASE) != EXPECTED_BASE_SHA:
    raise RuntimeError("Reviewed R11 flight validator hash drift")

with open(BASE, "r", encoding="utf-8") as _handle:
    _source = _handle.read()

_source = _source.replace(
    'EXPECTED_MAP_SHA = "3F98136280504222E5340DB7044F0F3564E8BFFD7221C4EC2F2DF655CE2FFAEC"',
    'EXPECTED_MAP_SHA = "B66CE7E24465CB8ADA8F53D5F31B480289415D1641726BA7C276B0907BF20133"',
)
_source = _source.replace(
    r'ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_Flight_R11_20260802"',
    r'ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_CharacterShip_R12_20260802"',
)
_source = _source.replace(
    'validate_redmmo_ppg_flight_r11_state.json',
    'validate_redmmo_ppg_character_ship_r12_state.json',
).replace(
    'validate_redmmo_ppg_flight_r11_result.json',
    'validate_redmmo_ppg_character_ship_r12_result.json',
).replace(
    'RedMMO_R11_flight_descent_PIE_1920x1080.png',
    'RedMMO_R12_flight_descent_PIE_1920x1080.png',
)
_bootstrap = "\ntry:\n    _REDMMO_R11_FLIGHT_VALIDATION = FlightValidation()"
if _bootstrap not in _source:
    raise RuntimeError("Reviewed R11 validator bootstrap marker drift")
_prefix = _source.split(_bootstrap, 1)[0]
exec(compile(_prefix, BASE, "exec"), globals(), globals())


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


class CharacterShipValidation(FlightValidation):
    def __init__(self):
        super().__init__()
        self.ship = None
        self.ground_view_issued = False
        self.report.update({
            "schema": "redmmo.ppg_character_ship.r12.real_pie.v1",
            "evidence_class": "real_d3d12_pie_character_ship_render_and_retained_flight_telemetry",
            "character_mesh_expected": EXPECTED_CHARACTER_MESH,
            "character_anim_expected": EXPECTED_CHARACTER_ANIM,
            "ship_mesh_expected": EXPECTED_SHIP_MESH,
            "ship_visual_only": True,
            "ship_ground_contact_requires_image_review": True,
        })

    def start(self):
        require(not os.path.exists(GROUND_SCREENSHOT), "R12 ground screenshot no-clobber failed")
        return super().start()

    def bind_pie(self) -> bool:
        bound = super().bind_pie()
        if not bound:
            return False
        mesh_components = [
            component for component in self.pawn.get_components_by_class(unreal.SkeletalMeshComponent)
            if component.get_skeletal_mesh_asset() is not None
        ]
        require(len(mesh_components) == 1, "Expected one runtime character skeletal mesh component")
        mesh_component = mesh_components[0]
        require(_asset_path(mesh_component.get_skeletal_mesh_asset()) == EXPECTED_CHARACTER_MESH,
                "Runtime mannequin mesh mismatch")
        require(_asset_path(mesh_component.get_editor_property("anim_class")) == EXPECTED_CHARACTER_ANIM,
                "Runtime mannequin AnimBP mismatch")
        require(not bool(mesh_component.get_editor_property("hidden_in_game")),
                "Runtime mannequin is hidden")
        require(bool(mesh_component.get_editor_property("visible")),
                "Runtime mannequin is not visible")

        actors = list(unreal.GameplayStatics.get_all_actors_of_class(self.world, unreal.Actor))
        ships = [actor for actor in actors if actor.get_actor_label() == EXPECTED_SHIP_LABEL]
        require(len(ships) == 1, "Expected one R12 parked ship in PIE")
        self.ship = ships[0]
        ship_components = [
            component for component in self.ship.get_components_by_class(unreal.StaticMeshComponent)
            if component.get_editor_property("static_mesh") is not None
        ]
        require(len(ship_components) == 1, "Expected one runtime ship visual component")
        require(_asset_path(ship_components[0].get_editor_property("static_mesh")) == EXPECTED_SHIP_MESH,
                "Runtime StarSparrow mesh mismatch")
        require(not self.ship.get_actor_enable_collision(), "Visual-only ship collision is enabled")
        self.report["runtime_visual_contract"] = {
            "character_actor": self.pawn.get_path_name(),
            "character_mesh_component": mesh_component.get_path_name(),
            "character_mesh": EXPECTED_CHARACTER_MESH,
            "character_anim_blueprint": EXPECTED_CHARACTER_ANIM,
            "character_hidden_in_game": False,
            "character_visible": True,
            "ship_actor": self.ship.get_path_name(),
            "ship_label": EXPECTED_SHIP_LABEL,
            "ship_mesh": EXPECTED_SHIP_MESH,
            "ship_collision": "disabled",
            "ship_visual_only": True,
        }
        return True

    def frame_ground_view(self):
        pawn_location = self.pawn.get_actor_location()
        ship_location = self.ship.get_actor_location()
        radial_up = normalized(sub(pawn_location, self.center))
        toward_ship = sub(ship_location, pawn_location)
        tangent = unreal.Vector(
            toward_ship.x - radial_up.x * dot(toward_ship, radial_up),
            toward_ship.y - radial_up.y * dot(toward_ship, radial_up),
            toward_ship.z - radial_up.z * dot(toward_ship, radial_up),
        )
        tangent = normalized(tangent)
        rotation = unreal.MathLibrary.make_rot_from_xz(tangent, radial_up)
        require(bool(self.pawn.set_actor_rotation(rotation, True)),
                "Unable to face the transient PIE pawn toward the parked ship")
        self.controller.set_control_rotation(rotation)
        self.report["ground_view"] = {
            "pawn_location": vec(pawn_location),
            "ship_location": vec(ship_location),
            "distance_cm": length(toward_ship),
            "radial_up": vec(radial_up),
            "view_rotation": str(rotation),
            "transient_pie_actor_rotation_only": True,
            "persistent_map_actor_moved": False,
        }

    def finish(self):
        require(os.path.isfile(GROUND_SCREENSHOT) and os.path.getsize(GROUND_SCREENSHOT) > 0,
                "R12 ground screenshot missing")
        require(sha256(MAP_FILE) == EXPECTED_MAP_SHA, "PIE changed R12 home map")
        require(not dirty_packages(), f"PIE dirtied packages: {dirty_packages()}")
        for path, expected in PROTECTED.items():
            require(sha256(path) == expected, "Protected checkpoint drift: " + path)
        self.report["status"] = "PASS_REAL_D3D12_PIE_CHARACTER_SHIP_AND_RETAINED_FLIGHT"
        self.report["ground_screenshot"] = {
            "path": GROUND_SCREENSHOT,
            "sha256": sha256(GROUND_SCREENSHOT),
            "bytes": os.path.getsize(GROUND_SCREENSHOT),
        }
        self.report["flight_screenshot"] = {
            "path": SCREENSHOT,
            "sha256": sha256(SCREENSHOT),
            "bytes": os.path.getsize(SCREENSHOT),
        }
        atomic_json(RESULT, self.report)
        self.publish()
        self.level.editor_request_end_play()
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        unreal.log("REDMMO_R12_CHARACTER_SHIP_VALIDATION_PASS")

    def tick(self, delta):
        try:
            elapsed = time.monotonic() - self.phase_started
            if self.phase == "WAIT_GENERATION":
                require(elapsed <= 180.0, "PPG generation timeout")
                if self.generation_ready() and elapsed >= 3.0:
                    self.frame_ground_view()
                    self.set_phase("SETTLE_GROUND_VIEW")
                self.publish()
                return
            if self.phase == "SETTLE_GROUND_VIEW":
                require(elapsed <= 30.0, "R12 ground-view settle timeout")
                if elapsed >= 1.5:
                    unreal.SystemLibrary.execute_console_command(
                        self.world,
                        'HighResShot filename="{}" 1920x1080'.format(GROUND_SCREENSHOT.replace("\\", "/")),
                    )
                    self.ground_view_issued = True
                    self.set_phase("WAIT_GROUND_SCREENSHOT")
                self.publish()
                return
            if self.phase == "WAIT_GROUND_SCREENSHOT":
                require(elapsed <= 60.0, "R12 ground screenshot timeout")
                if os.path.isfile(GROUND_SCREENSHOT) and os.path.getsize(GROUND_SCREENSHOT) > 0:
                    self.inject_fly_toggle()
                    self.set_phase("WAIT_F_TOGGLE")
                self.publish()
                return
            return super().tick(delta)
        except Exception as error:
            self.fail(error)


try:
    _REDMMO_R12_CHARACTER_SHIP_VALIDATION = CharacterShipValidation()
    _REDMMO_R12_CHARACTER_SHIP_VALIDATION.start()
except Exception as _bootstrap_error:
    atomic_json(RESULT, {
        "schema": "redmmo.ppg_character_ship.r12.real_pie.v1",
        "status": "FAIL",
        "error": str(_bootstrap_error),
        "traceback": traceback.format_exc(),
    })
    unreal.log_error("REDMMO_R12_CHARACTER_SHIP_BOOTSTRAP_FAIL " + str(_bootstrap_error))

