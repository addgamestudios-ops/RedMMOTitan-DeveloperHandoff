"""Create the fail-closed rollback point for Red MMO R12 player presentation."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess


PROJECT = r"D:\RedMMOTitanWindowsData\Projects\RedMMO"
REPO = r"D:\RedMMOTitan"
HOME_MAP = os.path.join(PROJECT, r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap")
R11_PAWN = os.path.join(PROJECT, r"Content\RedMMO\Gameplay\Player\BP_RedPlanetCharacter_R11.uasset")
R11_GM = os.path.join(PROJECT, r"Content\RedMMO\Gameplay\Player\GM_RedPlanet_R11.uasset")
R11_IMC = os.path.join(PROJECT, r"Content\RedMMO\Gameplay\Input\IMC_RedPlanet_R11.uasset")
R12_SHIP = os.path.join(PROJECT, r"Content\RedMMO\Gameplay\World\BP_RedParkedStarSparrow_R12.uasset")

EXPECTED = {
    HOME_MAP: "3F98136280504222E5340DB7044F0F3564E8BFFD7221C4EC2F2DF655CE2FFAEC",
    R11_PAWN: "B86B12ACF5CFB9A8DBC82650F56D815B0C6BE8BC32A099A510C5A085158931E6",
    R11_GM: "0696DE6039A5389BF0F872DB84D970E981C69184CD3AEA0279D89001B98BBEBD",
    R11_IMC: "09AC8B9CAB42342C49A22BC6CC1B4A1770B9FB56CE1E251A8E0B0C50581E1DC6",
}
SELECTED_SOURCES = {
    os.path.join(PROJECT, r"Content\SoStylized\Demo\Pawn\Mannequin\Character\Mesh\SK_Mannequin.uasset"):
        "79BA34451C4B5DC4AB0FEF7A0F1F8356B548A805B30C3F8167706559637BFF74",
    os.path.join(PROJECT, r"Content\SoStylized\Demo\Pawn\Mannequin\Animations\ThirdPerson_AnimBP.uasset"):
        "6E4FCBE46EF2CD932DF12A45E7EC456F487372D70E171FC36699EABE99AB7BB9",
    os.path.join(PROJECT, r"Content\StarSparrow\Meshes\Examples\SM_StarSparrow01.uasset"):
        "E4242DBE42E1AB50BEC4EF97F7CA024F9157EE108B579736DE74BAECAADBD990",
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


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def assert_hashes(records: dict[str, str], label: str) -> dict[str, str]:
    actual = {}
    for path, expected in records.items():
        if not os.path.isfile(path):
            raise RuntimeError(f"{label} missing: {path}")
        value = sha256(path)
        actual[path] = value
        if value != expected:
            raise RuntimeError(f"{label} hash drift: {path} expected={expected} actual={value}")
    return actual


def main() -> None:
    current = assert_hashes(EXPECTED, "R11 input")
    sources = assert_hashes(SELECTED_SOURCES, "selected source")
    protected = assert_hashes(PROTECTED, "protected checkpoint")
    if os.path.exists(R12_SHIP):
        raise RuntimeError(f"R12 no-clobber target already exists: {R12_SHIP}")

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
    rollback = os.path.join(
        r"D:\RedMMOTitanWindowsData\Rollback",
        f"RedMMO_PPG_CharacterShip_R12_{stamp}",
    )
    os.makedirs(rollback, exist_ok=False)
    copies = {}
    for source in (HOME_MAP, R11_PAWN, R11_GM, R11_IMC):
        target = os.path.join(rollback, os.path.basename(source) + ".pre_r12")
        shutil.copy2(source, target)
        if sha256(target) != current[source]:
            raise RuntimeError(f"Rollback copy hash mismatch: {target}")
        copies[source] = target

    git_status = subprocess.run(
        ["git", "status", "--porcelain=v2", "--untracked-files=all"],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout
    git_status_path = os.path.join(rollback, "redmmotitan_git_status_porcelain_v2.txt")
    with open(git_status_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(git_status)

    manifest = {
        "schema": "redmmo.ppg_character_ship.r12.rollback.v1",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "project": PROJECT,
        "inputs": current,
        "selected_sources": sources,
        "protected_hashes": protected,
        "rollback_copies": copies,
        "r12_target_required_absent": R12_SHIP,
        "git_status_snapshot": git_status_path,
        "rollback_method": (
            "Close Unreal; restore only the four retained pre-R12 copies over their exact source paths; "
            "delete only BP_RedParkedStarSparrow_R12 if it was created. StarSparrow and SoStylized source "
            "packages are selected read-only inputs and must never be removed by rollback."
        ),
    }
    manifest_path = os.path.join(rollback, "pre_r12_manifest.json")
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(manifest_path)


if __name__ == "__main__":
    main()
