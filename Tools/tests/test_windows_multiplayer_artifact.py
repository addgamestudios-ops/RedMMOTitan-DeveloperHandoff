from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from Tools.verify_windows_multiplayer_artifact import FAIL, NOT_OBSERVABLE, PASS, verify_artifact


WRAPPER = "FriendBuild"
INNER_EXE = b"synthetic-inner-game-executable"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _base_members() -> dict[str, bytes]:
    game_hash = _sha256(INNER_EXE)
    return {
        "BUILD_INFO.txt": (
            "RED MMO TITAN TEST\nCorrect game executable SHA-256:\n" + game_hash + "\n"
        ).encode(),
        "NOTICES.txt": b"notices",
        "READ_ME_FIRST.txt": b"guide",
        "READ_ME_FIRST.pdf": b"%PDF synthetic",
        "steam_appid.txt": b"480\r\n",
        "Titan.exe": b"bootstrap",
        "Titan/Binaries/Win64/steam_appid.txt": b"480\n",
        "Titan/Binaries/Win64/Titan.exe": INNER_EXE,
        "Titan/Plugins/SteamIntegrationKit/Source/SteamSdk/redistributable_bin/win64/steam_api64.dll": b"steam",
        "Titan/Content/Paks/Titan-Windows.pak": b"pak",
        "Titan/Content/Paks/Titan-Windows.utoc": b"utoc",
        "Titan/Content/Paks/Titan-Windows.ucas": b"ucas",
    }


def _write_artifact(
    root: Path,
    *,
    overrides: dict[str, bytes] | None = None,
    omissions: set[str] | None = None,
    extras: dict[str, bytes] | None = None,
) -> tuple[Path, Path, dict[str, bytes]]:
    members = _base_members()
    members.update(overrides or {})
    for item in omissions or set():
        members.pop(item, None)
    members.update(extras or {})
    zip_path = root / "friend.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative, payload in members.items():
            archive.writestr(f"{WRAPPER}/{relative}", payload)
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest().upper()
    sidecar = root / "friend.zip.sha256"
    sidecar.write_text(f"{digest} *friend.zip\n", encoding="utf-8")
    return zip_path, sidecar, members


def _status(report: dict, criterion_id: str) -> str:
    return next(item["status"] for item in report["criteria"] if item["id"] == criterion_id)


class WindowsMultiplayerArtifactTests(unittest.TestCase):
    def test_minimal_valid_artifact_passes_static_and_never_claims_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            zip_path, sidecar, _ = _write_artifact(Path(temp))
            first = verify_artifact(zip_path, sidecar)
            second = verify_artifact(zip_path, sidecar)
        self.assertTrue(first["success"])
        self.assertEqual(first["runtime_acceptance"], "UNVERIFIED")
        self.assertEqual(_status(first, "runtime_logs"), NOT_OBSERVABLE)
        self.assertEqual(first, second)

    def test_sidecar_mismatch_fails_before_blessing_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            zip_path, sidecar, _ = _write_artifact(Path(temp))
            sidecar.write_text("0" * 64 + " *friend.zip\n", encoding="utf-8")
            report = verify_artifact(zip_path, sidecar)
        self.assertFalse(report["success"])
        self.assertEqual(_status(report, "archive_sha256"), FAIL)

    def test_unsafe_case_colliding_and_runtime_generated_paths_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            zip_path, sidecar, _ = _write_artifact(
                Path(temp),
                extras={
                    "../escape.txt": b"escape",
                    "read_me_first.TXT": b"case collision",
                    "Titan/Saved/Crashes/crash.log": b"fatal",
                },
            )
            report = verify_artifact(zip_path, sidecar)
        self.assertFalse(report["success"])
        self.assertEqual(_status(report, "archive_paths"), FAIL)
        self.assertEqual(_status(report, "distributable_hygiene"), FAIL)

    def test_required_payload_appid_containers_and_declared_hash_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            zip_path, sidecar, _ = _write_artifact(
                Path(temp),
                overrides={
                    "steam_appid.txt": b"999",
                    "BUILD_INFO.txt": b"Correct game executable SHA-256:\n" + (b"0" * 64),
                    "Titan/Content/Paks/Titan-Windows.ucas": b"",
                },
                omissions={"NOTICES.txt"},
            )
            report = verify_artifact(zip_path, sidecar)
        self.assertFalse(report["success"])
        self.assertEqual(_status(report, "required_payload"), FAIL)
        self.assertEqual(_status(report, "steam_appid"), FAIL)
        self.assertEqual(_status(report, "content_containers"), FAIL)
        self.assertEqual(_status(report, "declared_game_exe_sha256"), FAIL)

    def test_strict_manifest_validates_declared_payload_hashes(self) -> None:
        payloads = _base_members()
        manifest = {
            "source_archive_name": "Titan.zip",
            "configuration": "Development",
            "build_timestamp_utc": "2026-07-18T00:00:00Z",
            "source_revision": "abc123",
            "uat_log_sha256": "1" * 64,
            "files": {relative: _sha256(payload) for relative, payload in payloads.items()},
        }
        with tempfile.TemporaryDirectory() as temp:
            zip_path, sidecar, _ = _write_artifact(
                Path(temp), extras={"BUILD_MANIFEST.json": json.dumps(manifest).encode()}
            )
            report = verify_artifact(zip_path, sidecar, strict=True)
        self.assertTrue(report["success"])
        self.assertEqual(_status(report, "strict_manifest"), PASS)

    def test_strict_manifest_missing_or_hash_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            zip_path, sidecar, _ = _write_artifact(Path(temp))
            missing = verify_artifact(zip_path, sidecar, strict=True)
        self.assertEqual(_status(missing, "strict_manifest"), FAIL)

        manifest = {
            "source_archive_name": "Titan.zip",
            "configuration": "Development",
            "build_timestamp_utc": "2026-07-18T00:00:00Z",
            "source_revision": "abc123",
            "uat_log_sha256": "1" * 64,
            "files": {"Titan/Binaries/Win64/Titan.exe": "2" * 64},
        }
        with tempfile.TemporaryDirectory() as temp:
            zip_path, sidecar, _ = _write_artifact(
                Path(temp), extras={"BUILD_MANIFEST.json": json.dumps(manifest).encode()}
            )
            mismatch = verify_artifact(zip_path, sidecar, strict=True)
        self.assertEqual(_status(mismatch, "strict_manifest"), FAIL)

    def test_extracted_payload_allows_saved_extras_but_rejects_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            zip_path, sidecar, _ = _write_artifact(root)
            extracted = root / "extracted"
            with zipfile.ZipFile(zip_path) as archive:
                archive.extractall(extracted)
            saved = extracted / WRAPPER / "Titan" / "Saved" / "Logs" / "runtime.log"
            saved.parent.mkdir(parents=True)
            saved.write_text("runtime", encoding="utf-8")
            clean = verify_artifact(zip_path, sidecar, extracted_root=extracted)
            (extracted / WRAPPER / "Titan" / "Binaries" / "Win64" / "Titan.exe").write_bytes(b"mutated")
            mutated = verify_artifact(zip_path, sidecar, extracted_root=extracted)
        self.assertTrue(clean["success"])
        self.assertEqual(_status(clean, "extracted_payload"), PASS)
        self.assertEqual(len(clean["allowed_saved_extras"]), 1)
        self.assertFalse(mutated["success"])
        self.assertEqual(_status(mutated, "extracted_payload"), FAIL)

    def test_runtime_logs_require_clean_matching_build_and_all_actions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            zip_path, sidecar, _ = _write_artifact(root)
            host = root / "host.log"
            client = root / "client.log"
            host.write_text(
                "BuildId=build42 HOST_CREATED LOBBY_CREATED RESPAWN GRAPPLE WEAPON SHUTTLE FIGHTER",
                encoding="utf-8",
            )
            client.write_text("BuildId=build42 LOBBY_FOUND JOIN_SUCCEEDED", encoding="utf-8")
            passing = verify_artifact(zip_path, sidecar, host_log=host, client_log=client)
            client.write_text("BuildId=other OnlineSubsystem = NULL", encoding="utf-8")
            failing = verify_artifact(zip_path, sidecar, host_log=host, client_log=client)
        self.assertTrue(passing["success"])
        self.assertEqual(passing["runtime_acceptance"], "LOG_MARKERS_PASS")
        self.assertEqual(_status(passing, "runtime_logs"), PASS)
        self.assertFalse(failing["success"])
        self.assertEqual(_status(failing, "runtime_logs"), FAIL)


if __name__ == "__main__":
    unittest.main()
