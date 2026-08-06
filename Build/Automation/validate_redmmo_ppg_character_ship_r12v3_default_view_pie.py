"""Run R12V3 from the untouched gameplay camera before any flight input."""

from __future__ import annotations

import hashlib


SOURCE = r"D:\RedMMOTitan\Build\Automation\validate_redmmo_ppg_character_ship_r12_pie.py"
EXPECTED_SOURCE_SHA = "D377D160407B042EAA1C31299697FA0D6B8B6B0A1B73D4F55819ACAF7001847C"


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def replace_exact(source, old, new, count=None):
    actual = source.count(old)
    if count is not None and actual != count:
        raise RuntimeError(f"Reviewed validator marker drift: {old!r} count={actual}")
    if actual == 0:
        raise RuntimeError(f"Reviewed validator marker missing: {old!r}")
    return source.replace(old, new)


if sha256(SOURCE) != EXPECTED_SOURCE_SHA:
    raise RuntimeError("Reviewed R12 validator hash drift")
with open(SOURCE, "r", encoding="utf-8") as handle:
    code = handle.read()
code = replace_exact(
    code,
    'EXPECTED_MAP_SHA = "B66CE7E24465CB8ADA8F53D5F31B480289415D1641726BA7C276B0907BF20133"',
    'EXPECTED_MAP_SHA = "0A7252E93F6F75FA7FAFAD856C7249E6964C27E34B9DD1386202080E2FD2D6CF"',
    1,
)
code = replace_exact(
    code,
    r'R12_ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_CharacterShip_R12_20260802"',
    r'R12_ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_CharacterShip_R12V3Default2_20260802"',
    1,
)
code = replace_exact(
    code,
    "r'ROOT = r\"D:\\RedMMOTitanWindowsData\\Diagnostics\\RedMMO_PPG_CharacterShip_R12_20260802\"'",
    "r'ROOT = r\"D:\\RedMMOTitanWindowsData\\Diagnostics\\RedMMO_PPG_CharacterShip_R12V3Default2_20260802\"'",
    1,
)
code = replace_exact(code, "validate_redmmo_ppg_character_ship_r12_state.json",
                     "validate_redmmo_ppg_character_ship_r12v3_default2_state.json", 1)
code = replace_exact(code, "validate_redmmo_ppg_character_ship_r12_result.json",
                     "validate_redmmo_ppg_character_ship_r12v3_default2_result.json", 1)
code = replace_exact(code, "RedMMO_R12_character_ship_ground_PIE_1920x1080.png",
                     "RedMMO_R12V3_default2_character_ship_ground_PIE_1920x1080.png", 1)
code = replace_exact(code, "RedMMO_R12_flight_descent_PIE_1920x1080.png",
                     "RedMMO_R12V3_default2_flight_descent_PIE_1920x1080.png", 1)
code = replace_exact(code, "redmmo.ppg_character_ship.r12.real_pie.v1",
                     "redmmo.ppg_character_ship.r12v3_default2.real_pie.v1")
code = replace_exact(
    code,
    '''        rotation = unreal.MathLibrary.make_rot_from_xz(tangent, radial_up)
        require(bool(self.pawn.set_actor_rotation(rotation, True)),
                "Unable to face the transient PIE pawn toward the parked ship")
        self.controller.set_control_rotation(rotation)
        self.report["ground_view"] = {''',
    '''        requested_rotation = unreal.MathLibrary.make_rot_from_xz(tangent, radial_up)
        rotation = self.controller.get_control_rotation()
        camera_location, camera_rotation = player_view(self.controller, self.pawn)
        camera_forward = unreal.MathLibrary.get_forward_vector(camera_rotation)
        camera_to_ship = normalized(sub(ship_location, camera_location))
        self.report["ground_view"] = {''',
    1,
)
code = replace_exact(
    code,
    '''            "view_rotation": str(rotation),
            "transient_pie_actor_rotation_only": True,
            "persistent_map_actor_moved": False,''',
    '''            "view_rotation": str(rotation),
            "requested_ship_facing_rotation_not_applied": str(requested_rotation),
            "camera_location": vec(camera_location),
            "camera_forward": vec(camera_forward),
            "camera_to_ship_direction": vec(camera_to_ship),
            "camera_forward_dot_ship": dot(camera_forward, camera_to_ship),
            "transient_pie_actor_rotation_only": False,
            "persistent_map_actor_moved": False,''',
    1,
)
exec(compile(code, SOURCE, "exec"), globals(), globals())
