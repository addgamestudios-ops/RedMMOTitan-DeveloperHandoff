"""Create the map-only rollback point for the R13 PlayerStart camera seed."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone


PROJECT = r"D:\RedMMOTitanWindowsData\Projects\RedMMO"
REPO = r"D:\RedMMOTitan"
HOME_MAP = os.path.join(
    PROJECT, r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
)
EXPECTED = {
    HOME_MAP: "0A7252E93F6F75FA7FAFAD856C7249E6964C27E34B9DD1386202080E2FD2D6CF",
    os.path.join(
        PROJECT,
        r"Content\RedMMO\Gameplay\Player\BP_RedPlanetCharacter_R11.uasset",
    ): "65A0413D1921F8ED2F6E4E3893B1C6B5CA3A0D1F7BCFC9AF9BF987940ECDC11E",
    os.path.join(
        PROJECT, r"Content\RedMMO\Gameplay\Player\GM_RedPlanet_R11.uasset"
    ): "0696DE6039A5389BF0F872DB84D970E981C69184CD3AEA0279D89001B98BBEBD",
    os.path.join(
        PROJECT, r"Content\RedMMO\Gameplay\Input\IMC_RedPlanet_R11.uasset"
    ): "09AC8B9CAB42342C49A22BC6CC1B4A1770B9FB56CE1E251A8E0B0C50581E1DC6",
    os.path.join(
        PROJECT,
        r"Content\RedMMO\Gameplay\World\BP_RedParkedStarSparrow_R12.uasset",
    ): "C9FDCF7D0FE89DACE39D418B79A7951C37C699C1FEA7E485C85670B2AB864BD6",
}
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
CANDIDATE_RESULT = (
    r"D:\RedMMOTitanWindowsData\Diagnostics"
    r"\RedMMO_PPG_PlayerStartCamera_R13Candidate3_20260802"
    r"\validate_redmmo_ppg_playerstart_camera_candidate_r13_result.json"
)
ROLLBACK = (
    r"D:\RedMMOTitanWindowsData\Rollback"
    r"\RedMMO_PPG_PlayerStartCamera_R13_20260802_Candidate3"
)
MANIFEST = os.path.join(ROLLBACK, "pre_r13_playerstart_manifest.json")


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def verify(records: dict[str, str], label: str) -> dict[str, str]:
    actual: dict[str, str] = {}
    for path, expected in records.items():
        if not os.path.isfile(path):
            raise RuntimeError(f"{label} missing: {path}")
        actual[path] = sha256(path)
        if actual[path] != expected:
            raise RuntimeError(
                f"{label} hash drift: {path} expected={expected} "
                f"actual={actual[path]}"
            )
    return actual


if os.path.exists(ROLLBACK):
    raise RuntimeError(f"R13 rollback path already exists: {ROLLBACK}")
verified = verify(EXPECTED, "R13 source")
protected = verify(PROTECTED, "protected checkpoint")
if not os.path.isfile(CANDIDATE_RESULT):
    raise RuntimeError("R13 Candidate3 result is missing")
with open(CANDIDATE_RESULT, "r", encoding="utf-8") as handle:
    candidate = json.load(handle)
gate = candidate.get("candidate_structural_gate", {})
if not (
    candidate.get("home_map_sha256") == EXPECTED[HOME_MAP]
    and gate.get("ship_in_front") is True
    and gate.get("not_skyward") is True
    and str(candidate.get("status", "")).startswith("PASS_REAL_D3D12_NO_SAVE")
):
    raise RuntimeError("R13 Candidate3 evidence did not pass the reviewed gate")

os.makedirs(ROLLBACK, exist_ok=False)
map_copy = os.path.join(ROLLBACK, "RedMMO_PPG_HomeWorld.umap.pre_r13_playerstart")
shutil.copy2(HOME_MAP, map_copy)
if sha256(map_copy) != EXPECTED[HOME_MAP]:
    raise RuntimeError("R13 rollback map-copy hash mismatch")
git_status = subprocess.run(
    ["git", "status", "--porcelain=v2", "--untracked-files=all"],
    cwd=REPO,
    check=True,
    capture_output=True,
    text=True,
).stdout
git_status_path = os.path.join(ROLLBACK, "redmmotitan_git_status_porcelain_v2.txt")
with open(git_status_path, "w", encoding="utf-8", newline="\n") as handle:
    handle.write(git_status)

payload = {
    "schema": "redmmo.ppg_playerstart_camera.r13.rollback.v1",
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "authorized_scope": (
        "Only the unique home-map PlayerStart rotation may change from "
        "(47.790019,158.480630,161.955720) to (0,-5.282777,0)."
    ),
    "home_map": HOME_MAP,
    "home_map_sha256": EXPECTED[HOME_MAP],
    "rollback_copy": map_copy,
    "verified_project_files": verified,
    "protected_hashes": protected,
    "candidate3_result": CANDIDATE_RESULT,
    "candidate3_result_sha256": sha256(CANDIDATE_RESULT),
    "git_status": git_status_path,
    "rollback_method": (
        "Close Unreal, then copy rollback_copy over home_map. No other file is "
        "part of this map-only mutation."
    ),
}
with open(MANIFEST, "x", encoding="utf-8", newline="\n") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
print(MANIFEST)
