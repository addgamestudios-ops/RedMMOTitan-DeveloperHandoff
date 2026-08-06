"""Create the byte-exact pre-R73 rollback checkpoint.

This is offline and copies only the current project-owned ProfileV1 packages
whose bindings R73 may change, plus immutable reference packages needed to
prove that the transaction did not touch the home map or prior successors.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
CONTENT = PROJECT / "Content"
ROLLBACK = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeProfileV1BiomePresentation_R73_20260805T2343Z")
FILES = {
    PROJECT / "RedMMO.uproject": "3BF3D8D1D1C7F892A2CD4873F7C0390EC1AF3CA8F77E60549169563D18DBF86F",
    CONTENT / r"RedMMO\Maps\RedMMO_PPG_HomeWorld.umap": "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3",
    CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\DA_PPG_ProfileV1_PlanetData.uasset": "BD5E46F3132A6A8947C1258AB18C0F152DD4836755A414B9CC876E3BD0D6CB0D",
    CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Profiles\DA_PPG_ProfileV1_NoPalms_R66.uasset": "C0EE6CB0A2D9D679D1FB4D64747555D55A5AF18ABED4AEC2666A1D5BECDA97DC",
    CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\M_PPG_ProfileV1_RoleSurface_R71.uasset": "EA3A5704BDA1706C7720CDFB51F39CE370CCD844E6FECEDEB53CF3ACC4F555DE",
    CONTENT / r"RedMMO\WorldAuthoring\PPG\ProfileV1\Materials\MI_PPG_ProfileV1_RoleSurface_R71.uasset": "D4D222CF92769F99631B649198DD8C38032BD67B7853CD7B0A288E1657301253",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"): "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"): "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


if ROLLBACK.exists():
    raise SystemExit("R73 rollback no-clobber failed")
for path, expected in FILES.items():
    if not path.is_file() or sha256(path) != expected:
        raise SystemExit("R73 checkpoint input drift: " + str(path))

ROLLBACK.mkdir(parents=True, exist_ok=False)
records = []
for index, (path, expected) in enumerate(FILES.items()):
    destination = ROLLBACK / ("{:02d}_{}".format(index, path.name))
    shutil.copy2(path, destination)
    if sha256(destination) != expected:
        raise SystemExit("R73 checkpoint copy mismatch: " + str(path))
    records.append({"source": str(path), "copy": str(destination), "sha256": expected})

manifest = {
    "schema": "redmmo.ppg.profile_v1_biome_presentation.rollback.r73.v1",
    "captured_utc": datetime.now(timezone.utc).isoformat(),
    "records": records,
    "planned_new_assets": [
        "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Profiles/DA_PPG_ProfileV1_RockOnly_R73",
        "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Materials/M_PPG_ProfileV1_BiomePresentation_R73",
        "/Game/RedMMO/WorldAuthoring/PPG/ProfileV1/Materials/MI_PPG_ProfileV1_BiomePresentation_R73",
    ],
    "restore": (
        "With Unreal closed, restore 02_DA_PPG_ProfileV1_PlanetData.uasset to its source path, "
        "delete only the three planned R73 assets, then fresh reload and MapCheck. Prior R71/R66, "
        "the home map, vendor assets and protected maps remain immutable references."),
}
payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
with (ROLLBACK / "manifest.json").open("xb") as stream:
    stream.write(payload)
    stream.flush()
    os.fsync(stream.fileno())

print(json.dumps({"status": "PASS_R73_CHECKPOINT", "rollback": str(ROLLBACK), "records": len(records)}, sort_keys=True))
