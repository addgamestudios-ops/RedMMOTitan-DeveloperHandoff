"""Run the reviewed R12 character/ship + R11 flight gate against R12V2."""

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
    'EXPECTED_MAP_SHA = "013873CF751E7B1A7A3C042C2FC3CD6527760CB6B0A1B0416A8C69AAA31F4BC6"',
    1,
)
code = replace_exact(
    code,
    r'R12_ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_CharacterShip_R12_20260802"',
    r'R12_ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_CharacterShip_R12V2_20260802"',
    1,
)
code = replace_exact(code, "validate_redmmo_ppg_character_ship_r12_state.json",
                     "validate_redmmo_ppg_character_ship_r12v2_state.json", 1)
code = replace_exact(code, "validate_redmmo_ppg_character_ship_r12_result.json",
                     "validate_redmmo_ppg_character_ship_r12v2_result.json", 1)
code = replace_exact(code, "RedMMO_R12_character_ship_ground_PIE_1920x1080.png",
                     "RedMMO_R12V2_character_ship_ground_PIE_1920x1080.png", 1)
code = replace_exact(code, "RedMMO_R12_flight_descent_PIE_1920x1080.png",
                     "RedMMO_R12V2_flight_descent_PIE_1920x1080.png", 1)
code = replace_exact(code, "redmmo.ppg_character_ship.r12.real_pie.v1",
                     "redmmo.ppg_character_ship.r12v2.real_pie.v1")
exec(compile(code, SOURCE, "exec"), globals(), globals())
