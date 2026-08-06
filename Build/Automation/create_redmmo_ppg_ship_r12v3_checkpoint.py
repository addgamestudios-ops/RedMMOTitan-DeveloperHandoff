"""Checkpoint the serialized R12V2 map before ship-only visual framing correction."""

import datetime as dt
import hashlib
import json
import os
import shutil


MAP = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
EXPECTED_MAP = "013873CF751E7B1A7A3C042C2FC3CD6527760CB6B0A1B0416A8C69AAA31F4BC6"
PROTECTED = {
    r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap":
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap":
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
    r"D:\RedMMOTitan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap":
        "211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7",
    r"D:\RedMMOTitanWindowsData\Rollback\BeforeCoastDatum_20260714\RedPlanetGen_50km_FusedPrototype.umap":
        "A9C42C0D1B0429DD1018F00F0D2AB8A18F66C07291611964EFF5F9710F3B0C6A",
}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


if sha256(MAP) != EXPECTED_MAP:
    raise RuntimeError("R12V2 map hash drift")
for path, expected in PROTECTED.items():
    if sha256(path) != expected:
        raise RuntimeError("Protected checkpoint drift: " + path)
stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
folder = os.path.join(
    r"D:\RedMMOTitanWindowsData\Rollback", f"RedMMO_PPG_Ship_R12V3_{stamp}"
)
os.makedirs(folder, exist_ok=False)
copy = os.path.join(folder, "RedMMO_PPG_HomeWorld.umap.pre_r12v3")
shutil.copy2(MAP, copy)
if sha256(copy) != EXPECTED_MAP:
    raise RuntimeError("R12V3 rollback copy mismatch")
manifest = {
    "schema": "redmmo.ppg_ship.r12v3.rollback.v1",
    "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    "map": MAP,
    "map_sha256": EXPECTED_MAP,
    "rollback_copy": copy,
    "protected_hashes": PROTECTED,
    "authorized_scope": "Only the existing R12 visual-only parked StarSparrow transform/scale.",
    "rollback_method": "Close Unreal and restore only this map copy over the exact map path.",
}
manifest_path = os.path.join(folder, "pre_r12v3_manifest.json")
with open(manifest_path, "w", encoding="utf-8", newline="\n") as handle:
    json.dump(manifest, handle, indent=2, sort_keys=True)
    handle.write("\n")
print(manifest_path)
