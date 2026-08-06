"""Run the reviewed R12V2 reload/MapCheck against the ship-only R12V3 map."""

import hashlib


SOURCE = r"D:\RedMMOTitan\Build\Automation\reload_mapcheck_redmmo_ppg_character_ship_r12v2.py"
EXPECTED_SHA = "AF0588C0C0C99096113E8A1698779FD36C46F824961293C8627EA9284F578479"


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


if sha256(SOURCE) != EXPECTED_SHA:
    raise RuntimeError("Reviewed R12V2 reload script hash drift")
with open(SOURCE, "r", encoding="utf-8") as handle:
    code = handle.read()
replacements = {
    "013873CF751E7B1A7A3C042C2FC3CD6527760CB6B0A1B0416A8C69AAA31F4BC6":
        "0A7252E93F6F75FA7FAFAD856C7249E6964C27E34B9DD1386202080E2FD2D6CF",
    r"RedMMO_PPG_CharacterShip_R12V2_20260802": r"RedMMO_PPG_CharacterShip_R12V3_20260802",
    "reload_mapcheck_redmmo_ppg_character_ship_r12v2_result.json":
        "reload_mapcheck_redmmo_ppg_character_ship_r12v3_result.json",
    "reload_mapcheck_redmmo_ppg_character_ship_r12v2.done":
        "reload_mapcheck_redmmo_ppg_character_ship_r12v3.done",
    "redmmo.ppg_character_ship.r12v2.reload_mapcheck.v1":
        "redmmo.ppg_character_ship.r12v3.reload_mapcheck.v1",
}
for old, new in replacements.items():
    if old not in code:
        raise RuntimeError("Reviewed reload marker missing: " + old)
    code = code.replace(old, new)
exec(compile(code, SOURCE, "exec"), globals(), globals())
