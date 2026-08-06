"""Run the reviewed real-PIE PPG surface probe at the R12V3 ship offset."""

from __future__ import annotations

import hashlib


SOURCE = r"D:\RedMMOTitan\Build\Automation\probe_redmmo_ppg_ship_surface_r12.py"
EXPECTED_SOURCE_SHA = "0872A08FCC2DFC91F19F48C6745CDC56B2878AD7822983A9FFA795F60C212745"


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def replace_exact(source, old, new, count=None):
    actual = source.count(old)
    if count is not None and actual != count:
        raise RuntimeError(f"Reviewed surface-probe marker drift: {old!r} count={actual}")
    if actual == 0:
        raise RuntimeError(f"Reviewed surface-probe marker missing: {old!r}")
    return source.replace(old, new)


if sha256(SOURCE) != EXPECTED_SOURCE_SHA:
    raise RuntimeError("Reviewed R12 surface-probe hash drift")
with open(SOURCE, "r", encoding="utf-8") as handle:
    code = handle.read()
code = replace_exact(
    code,
    'EXPECTED_MAP_SHA = "3F98136280504222E5340DB7044F0F3564E8BFFD7221C4EC2F2DF655CE2FFAEC"',
    'EXPECTED_MAP_SHA = "0A7252E93F6F75FA7FAFAD856C7249E6964C27E34B9DD1386202080E2FD2D6CF"',
    1,
)
code = replace_exact(
    code,
    r'ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_CharacterShip_R12_20260802"',
    r'ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_CharacterShip_R12V3_20260802"',
    1,
)
code = replace_exact(code, "probe_redmmo_ppg_ship_surface_r12_result.json",
                     "probe_redmmo_ppg_ship_surface_r12v3_result.json", 1)
code = replace_exact(code, "probe_redmmo_ppg_ship_surface_r12_state.json",
                     "probe_redmmo_ppg_ship_surface_r12v3_state.json", 1)
code = replace_exact(code, "probe_redmmo_ppg_ship_surface_r12.done",
                     "probe_redmmo_ppg_ship_surface_r12v3.done", 1)
code = replace_exact(code, "self.ship_offset_x = 5200.0",
                     "self.ship_offset_x = 2400.0", 1)
code = replace_exact(code, "self.ship_offset_y = -1600.0",
                     "self.ship_offset_y = -500.0", 1)
code = replace_exact(code, "redmmo.ppg_character_ship.r12.surface_probe.v1",
                     "redmmo.ppg_character_ship.r12v3.surface_probe.v1", 1)
exec(compile(code, SOURCE, "exec"), globals(), globals())
