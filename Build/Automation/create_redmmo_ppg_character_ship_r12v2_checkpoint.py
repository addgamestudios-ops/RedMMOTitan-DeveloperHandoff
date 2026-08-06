"""Create the fail-closed rollback point for the R12 visual correction."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess


PROJECT = r"D:\RedMMOTitanWindowsData\Projects\RedMMO"
REPO = r"D:\RedMMOTitan"
FILES = {
    os.path.join(PROJECT, r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"):
        "B66CE7E24465CB8ADA8F53D5F31B480289415D1641726BA7C276B0907BF20133",
    os.path.join(PROJECT, r"Content\RedMMO\Gameplay\Player\BP_RedPlanetCharacter_R11.uasset"):
        "8421120C7FEE24FD457775789F0758D32F8D34AC7F0ECE5DA2603CFAA146F768",
    os.path.join(PROJECT, r"Content\RedMMO\Gameplay\Player\GM_RedPlanet_R11.uasset"):
        "0696DE6039A5389BF0F872DB84D970E981C69184CD3AEA0279D89001B98BBEBD",
    os.path.join(PROJECT, r"Content\RedMMO\Gameplay\Input\IMC_RedPlanet_R11.uasset"):
        "09AC8B9CAB42342C49A22BC6CC1B4A1770B9FB56CE1E251A8E0B0C50581E1DC6",
    os.path.join(PROJECT, r"Content\RedMMO\Gameplay\World\BP_RedParkedStarSparrow_R12.uasset"):
        "C9FDCF7D0FE89DACE39D418B79A7951C37C699C1FEA7E485C85670B2AB864BD6",
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


def verify(records: dict[str, str], label: str) -> dict[str, str]:
    actual = {}
    for path, expected in records.items():
        if not os.path.isfile(path):
            raise RuntimeError(f"{label} missing: {path}")
        actual[path] = sha256(path)
        if actual[path] != expected:
            raise RuntimeError(
                f"{label} hash drift: {path} expected={expected} actual={actual[path]}"
            )
    return actual


def main() -> None:
    inputs = verify(FILES, "R12 serialized input")
    protected = verify(PROTECTED, "protected checkpoint")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
    rollback = os.path.join(
        r"D:\RedMMOTitanWindowsData\Rollback",
        f"RedMMO_PPG_CharacterShip_R12V2_{stamp}",
    )
    os.makedirs(rollback, exist_ok=False)
    copies = {}
    for source, value in inputs.items():
        target = os.path.join(rollback, os.path.basename(source) + ".pre_r12v2")
        shutil.copy2(source, target)
        if sha256(target) != value:
            raise RuntimeError(f"Rollback copy hash mismatch: {target}")
        copies[source] = target

    git_status_path = os.path.join(rollback, "redmmotitan_git_status_porcelain_v2.txt")
    git_status = subprocess.run(
        ["git", "status", "--porcelain=v2", "--untracked-files=all"],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout
    with open(git_status_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(git_status)

    manifest = {
        "schema": "redmmo.ppg_character_ship.r12v2.rollback.v1",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "project": PROJECT,
        "inputs": inputs,
        "protected_hashes": protected,
        "rollback_copies": copies,
        "git_status_snapshot": git_status_path,
        "authorized_scope": (
            "Only BP_RedPlanetCharacter_R11 camera/spring-arm defaults and the existing "
            "R12 visual-only parked-ship actor transform in RedMMO_PPG_HomeWorld."
        ),
        "rollback_method": (
            "Close Unreal and restore only these five retained copies over their exact source paths. "
            "Do not remove SoStylized or StarSparrow source packages."
        ),
    }
    manifest_path = os.path.join(rollback, "pre_r12v2_manifest.json")
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(manifest_path)


if __name__ == "__main__":
    main()
