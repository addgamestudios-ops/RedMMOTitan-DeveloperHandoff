from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from Tools.create_windows_friend_artifact import create_friend_artifact


INNER_EXE = b"synthetic-game-exe"


def _write(root: Path, relative: str, data: bytes) -> Path:
    path = root.joinpath(*Path(relative).parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _fixture(root: Path) -> tuple[Path, Path, Path, Path, Path]:
    packaged = root / "Package" / "Windows"
    files = {
        "NOTICES.txt": b"notices",
        "steam_appid.txt": b"480\r\n",
        "Titan.exe": b"bootstrap",
        "Titan/Binaries/Win64/steam_appid.txt": b"480\n",
        "Titan/Binaries/Win64/Titan.exe": INNER_EXE,
        "Titan/Plugins/SteamIntegrationKit/Source/SteamSdk/redistributable_bin/win64/steam_api64.dll": b"steam",
        "Titan/Content/Paks/Titan-Windows.pak": b"pak",
        "Titan/Content/Paks/Titan-Windows.utoc": b"utoc",
        "Titan/Content/Paks/Titan-Windows.ucas": b"ucas",
    }
    for relative, data in files.items():
        _write(packaged, relative, data)
    quickstart = _write(root, "inputs/quickstart.txt", b"friend guide")
    pdf = _write(root, "inputs/quickstart.pdf", b"%PDF synthetic")
    uat = _write(root, "inputs/uat.log", b"BUILD SUCCESSFUL")
    Path(str(uat) + ".exitcode").write_text("0\n", encoding="utf-8")
    ready = _write(
        root,
        "Package/REDMMO_PACKAGE_READY.txt",
        (
            f"archive={packaged.parent}\n"
            f"build_log={uat}\n"
            f"uat_exit_file={uat}.exitcode\n"
            "configuration=Development\n"
            "build_timestamp_utc=2026-07-18T22:00:00Z\n"
            "source_revision=0123456789abcdef\n"
            "source_dirty=false\n"
        ).encode(),
    )
    return packaged, ready, quickstart, pdf, uat


def _create(
    root: Path,
    packaged: Path,
    ready: Path,
    quickstart: Path,
    pdf: Path,
    uat: Path,
    *,
    output_name: str = "out",
) -> dict:
    return create_friend_artifact(
        packaged_root=packaged,
        ready_marker=ready,
        output_dir=root / output_name,
        label="RedMMOTitan_Friend_Test",
        quickstart_text=quickstart,
        quickstart_pdf=pdf,
        steam_app_id_file=packaged / "steam_appid.txt",
        uat_log=uat,
        configuration="Development",
        build_timestamp_utc="2026-07-18T22:00:00Z",
        source_revision="0123456789abcdef",
        source_dirty=False,
        source_archive_name="Package",
    )


class CreateWindowsFriendArtifactTests(unittest.TestCase):
    def test_builder_is_reproducible_and_strictly_self_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            packaged, ready, quickstart, pdf, uat = _fixture(root)
            first = _create(root, packaged, ready, quickstart, pdf, uat, output_name="out_a")
            second = _create(root, packaged, ready, quickstart, pdf, uat, output_name="out_b")
            verification = json.loads(Path(first["verification"]).read_text(encoding="utf-8"))
        self.assertEqual(first["artifact_sha256"], second["artifact_sha256"])
        self.assertEqual(first["runtime_acceptance"], "UNVERIFIED")
        self.assertTrue(verification["success"])
        self.assertEqual(verification["static_acceptance"], "PASS")
        self.assertEqual(verification["runtime_acceptance"], "UNVERIFIED")

    def test_builder_excludes_runtime_debug_and_staging_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            packaged, ready, quickstart, pdf, uat = _fixture(root)
            _write(packaged, "Titan/Saved/Logs/Titan.log", b"runtime")
            _write(packaged, "Titan/Binaries/Win64/Titan.pdb", b"symbols")
            _write(packaged, "Manifest_UFSFiles_Win64.txt", b"staging")
            (packaged / "Titan" / "Binaries" / "Win64" / "steam_appid.txt").unlink()
            result = _create(root, packaged, ready, quickstart, pdf, uat)
            with zipfile.ZipFile(result["zip"]) as archive:
                names = archive.namelist()
                manifest_name = "RedMMOTitan_Friend_Test/BUILD_MANIFEST.json"
                manifest = json.loads(archive.read(manifest_name))
                self.assertEqual(
                    archive.read("RedMMOTitan_Friend_Test/steam_appid.txt"), b"480\n"
                )
                self.assertEqual(
                    archive.read(
                        "RedMMOTitan_Friend_Test/Titan/Binaries/Win64/steam_appid.txt"
                    ),
                    b"480\n",
                )
        folded = "\n".join(names).casefold()
        self.assertNotIn("/saved/", folded)
        self.assertNotIn(".pdb", folded)
        self.assertNotIn("manifest_ufsfiles", folded)
        self.assertEqual(result["excluded_count"], 3)
        self.assertEqual(len(manifest["excluded_source_files"]), 3)

    def test_manifest_hashes_every_payload_except_itself(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            packaged, ready, quickstart, pdf, uat = _fixture(root)
            result = _create(root, packaged, ready, quickstart, pdf, uat)
            with zipfile.ZipFile(result["zip"]) as archive:
                wrapper = "RedMMOTitan_Friend_Test/"
                relatives = {
                    name[len(wrapper) :]
                    for name in archive.namelist()
                    if name.startswith(wrapper) and not name.endswith("/")
                }
                manifest = json.loads(archive.read(wrapper + "BUILD_MANIFEST.json"))
        self.assertEqual(set(manifest["files"]), relatives - {"BUILD_MANIFEST.json"})
        self.assertEqual(manifest["runtime_acceptance"], "UNVERIFIED")
        self.assertEqual(manifest["steam_app_id"], 480)

    def test_missing_required_payload_or_wrong_appid_fails_before_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            packaged, ready, quickstart, pdf, uat = _fixture(root)
            (packaged / "Titan.exe").unlink()
            with self.assertRaisesRegex(ValueError, "missing required"):
                _create(root, packaged, ready, quickstart, pdf, uat)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            packaged, ready, quickstart, pdf, uat = _fixture(root)
            (packaged / "steam_appid.txt").write_text("999", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must equal"):
                _create(root, packaged, ready, quickstart, pdf, uat)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            packaged, ready, quickstart, pdf, uat = _fixture(root)
            (packaged / "Titan" / "Content" / "Paks" / "Titan-Windows.ucas").unlink()
            with self.assertRaisesRegex(ValueError, "matching nonempty UTOC/UCAS"):
                _create(root, packaged, ready, quickstart, pdf, uat)

    def test_existing_output_is_immutable_and_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            packaged, ready, quickstart, pdf, uat = _fixture(root)
            first = _create(root, packaged, ready, quickstart, pdf, uat)
            self.assertTrue(Path(first["zip"]).is_file())
            with self.assertRaises(FileExistsError):
                _create(root, packaged, ready, quickstart, pdf, uat)

    def test_ready_marker_and_successful_uat_exit_are_mandatory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            packaged, ready, quickstart, pdf, uat = _fixture(root)
            Path(str(uat) + ".exitcode").write_text("1\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exit-code evidence"):
                _create(root, packaged, ready, quickstart, pdf, uat)


if __name__ == "__main__":
    unittest.main()
