from __future__ import annotations

import copy
import ctypes
import errno
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from Tools.build_redmmo_content_storage_manifest import (
    build_storage_manifest,
    manifest_bytes,
)
from Tools.verify_redmmo_content_storage_restore import (
    WINDOWS_DIRECTORY_PIN_ACCESS,
    WINDOWS_FILE_ADD_FILE,
    WINDOWS_FILE_ADD_SUBDIRECTORY,
    WINDOWS_FILE_ATTRIBUTE_TEMPORARY,
    WINDOWS_FILE_NON_DIRECTORY_FILE,
    WINDOWS_FILE_OPEN,
    WINDOWS_FILE_OPEN_REPARSE_POINT,
    WINDOWS_FILE_SHARE_DELETE,
    WINDOWS_FILE_SHARE_READ,
    WINDOWS_FILE_SHARE_WRITE,
    WINDOWS_FILE_SYNCHRONOUS_IO_NONALERT,
    WINDOWS_FILE_WRITE_THROUGH,
    WINDOWS_FILE_LIST_DIRECTORY,
    WINDOWS_MANIFEST_FILE_ACCESS,
    WINDOWS_FILE_RENAME_INFORMATION,
    RestoreVerificationError,
    _WindowsFileRenameInformation,
    _discover_restored_tree,
    _metadata,
    _open_binary_read,
    _path_signature,
    _paths_overlap,
    _require_plain_directory,
    _require_regular_file,
    _sha256_file,
    _signature,
    _windows_handle_metadata,
    _windows_flush_handle,
    _windows_nt_create_relative,
    _windows_nt_open_manifest_relative,
    _windows_publish_open_file_no_clobber,
    _windows_require_plain_directory_handle,
    _windows_require_plain_file_handle,
    load_authenticated_manifest,
    report_bytes,
    validate_output_path,
    validate_input_isolation,
    verify_isolated_restore,
    write_report_atomic,
)


ROOT = Path(__file__).resolve().parents[2]


def _windows_extended_path(path: Path) -> Path:
    absolute = str(path.absolute())
    if absolute.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + absolute.lstrip("\\"))
    return Path("\\\\?\\" + absolute)


class RedMMOContentStorageRestoreVerifierTests(unittest.TestCase):
    def _create_junction(self, link: Path, target: Path) -> None:
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=result.stdout + result.stderr,
        )

    def _write(self, root: Path, relative: str, payload: bytes) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    @unittest.skipUnless(os.name == "nt", "Windows native file identity")
    def test_windows_handle_metadata_includes_native_128_bit_identity(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            dir=r"D:\RedMMOTitanWindowsData\Diagnostics",
        ) as temporary_name:
            path = Path(temporary_name) / "identity.bin"
            path.write_bytes(b"redmmo-file-identity\n")

            import msvcrt

            descriptor = os.open(
                path,
                os.O_RDONLY | getattr(os, "O_BINARY", 0),
            )
            try:
                handle = msvcrt.get_osfhandle(descriptor)
                first = _windows_handle_metadata(handle, "identity fixture")
                second = _windows_handle_metadata(handle, "identity fixture")
            finally:
                os.close(descriptor)

            self.assertEqual(first, second)
            self.assertGreater(first.identity_volume_serial, 0)
            self.assertIsInstance(first.file_id_128, bytes)
            self.assertEqual(len(first.file_id_128), 16)
            self.assertTrue(any(first.file_id_128))
            observed = path.stat()
            self.assertEqual(first.volume_serial, observed.st_dev)
            self.assertEqual(first.file_id, observed.st_ino)

    @unittest.skipUnless(os.name == "nt", "Windows native file identity")
    def test_windows_handle_metadata_preserves_full_native_identity(
        self,
    ) -> None:
        captured: list[tuple[int, int]] = []
        expected_id = bytes.fromhex(
            "00112233445566778899AABBCCDDEEFF"
        )

        class FakeKernel32:
            def __init__(
                self,
                *,
                identity: bytes = expected_id,
                query_succeeds: bool = True,
                zero_identity: bool = False,
            ) -> None:
                self.identity = identity
                self.query_succeeds = query_succeeds
                self.zero_identity = zero_identity

            def GetFileInformationByHandle(
                self,
                _handle: int,
                raw: object,
            ) -> bool:
                observed = raw._obj
                observed.dwFileAttributes = 0x80
                observed.dwVolumeSerialNumber = 0xAABBCCDD
                observed.nFileSizeHigh = 0
                observed.nFileSizeLow = 3
                observed.nNumberOfLinks = 1
                observed.nFileIndexHigh = 0x01020304
                observed.nFileIndexLow = 0x05060708
                return True

            def GetFileInformationByHandleEx(
                self,
                _handle: int,
                information_class: int,
                raw: object,
                raw_size: int,
            ) -> bool:
                captured.append((information_class, raw_size))
                if not self.query_succeeds:
                    ctypes.set_last_error(50)
                    return False
                observed = raw._obj
                if self.zero_identity:
                    observed.VolumeSerialNumber = 0
                    identity = bytes(16)
                else:
                    observed.VolumeSerialNumber = 0x1122334455667788
                    identity = self.identity
                for index, value in enumerate(identity):
                    observed.FileId.Identifier[index] = value
                return True

        with patch(
            "Tools.verify_redmmo_content_storage_restore._windows_apis",
            return_value=(FakeKernel32(), object()),
        ):
            observed = _windows_handle_metadata(123, "identity fixture")

        self.assertEqual(captured, [(18, 24)])
        self.assertEqual(
            observed.identity_volume_serial,
            0x1122334455667788,
        )
        self.assertEqual(observed.file_id_128, expected_id)
        self.assertEqual(observed.file_id, 0x0102030405060708)

        changed_id = expected_id[:-1] + b"\xFE"
        with patch(
            "Tools.verify_redmmo_content_storage_restore._windows_apis",
            return_value=(FakeKernel32(identity=changed_id), object()),
        ):
            changed = _windows_handle_metadata(123, "identity fixture")
        self.assertEqual(changed.volume_serial, observed.volume_serial)
        self.assertEqual(changed.file_id, observed.file_id)
        self.assertNotEqual(changed, observed)

        with patch(
            "Tools.verify_redmmo_content_storage_restore._windows_apis",
            return_value=(FakeKernel32(zero_identity=True), object()),
        ), self.assertRaisesRegex(
            RestoreVerificationError,
            "identity is unavailable",
        ):
            _windows_handle_metadata(123, "identity fixture")

        with patch(
            "Tools.verify_redmmo_content_storage_restore._windows_apis",
            return_value=(FakeKernel32(query_succeeds=False), object()),
        ), self.assertRaisesRegex(
            RestoreVerificationError,
            "unable to query native Windows identity fixture",
        ):
            _windows_handle_metadata(123, "identity fixture")

    def _fixture(self, root: Path) -> None:
        project = {
            "FileVersion": 3,
            "EngineAssociation": "5.8",
            "Modules": [{"Name": "RedMMO", "Type": "Runtime"}],
            "Plugins": [
                {"Name": "RedHUD", "Enabled": True},
                {"Name": "VendorKit", "Enabled": False},
            ],
        }
        self._write(
            root,
            "Titan.uproject",
            (json.dumps(project, indent=2) + "\n").encode("utf-8"),
        )
        self._write(root, "Content/RedMMO/Maps/Main.umap", b"map")
        self._write(root, "Content/SoStylized/SM_Rock.uasset", b"rock")

        red_hud = {
            "FileVersion": 3,
            "VersionName": "1.0.0",
            "FriendlyName": "RED HUD",
            "CreatedBy": "RED MMO",
            "CanContainContent": True,
            "Installed": False,
        }
        self._write(
            root,
            "Plugins/RedHUD/RedHUD.uplugin",
            json.dumps(red_hud).encode("utf-8"),
        )
        self._write(root, "Plugins/RedHUD/Source/RedHUD.cpp", b"source")
        self._write(root, "Plugins/RedHUD/Resources/Frame.png", b"source-art")
        self._write(root, "Plugins/RedHUD/Binaries/Win64/RedHUD.dll", b"derived")

        vendor = {
            "FileVersion": 3,
            "VersionName": "2.0",
            "FriendlyName": "Vendor Kit",
            "CreatedBy": "Vendor",
            "CanContainContent": True,
            "Installed": False,
        }
        self._write(
            root,
            "Plugins/VendorKit/VendorKit.uplugin",
            json.dumps(vendor).encode("utf-8"),
        )
        self._write(
            root,
            "Plugins/VendorKit/Content/UI/T_Frame.uasset",
            b"frame",
        )

    def _copy_manifest_scope(
        self,
        source: Path,
        restore: Path,
        entries: list[dict[str, object]],
    ) -> None:
        restore.mkdir()
        for entry in entries:
            relative = str(entry["path"])
            destination = restore / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / relative, destination)

    def _authenticated_fixture(
        self,
        temporary: Path,
    ) -> tuple[
        Path,
        Path,
        dict[str, object],
        list[dict[str, object]],
        str,
    ]:
        source = temporary / "Source"
        source.mkdir()
        self._fixture(source)
        manifest = build_storage_manifest(source, protected_hashes={})
        manifest_path = temporary / "Manifest" / "storage_manifest.json"
        manifest_path.parent.mkdir()
        payload = manifest_bytes(manifest)
        manifest_path.write_bytes(payload)
        expected_digest = hashlib.sha256(payload).hexdigest().upper()
        loaded, entries, observed_digest = load_authenticated_manifest(
            manifest_path,
            expected_digest,
        )
        self.assertEqual(manifest, loaded)
        self.assertEqual(expected_digest, observed_digest)
        restore = temporary / "Restore"
        self._copy_manifest_scope(source, restore, entries)
        return source, restore, loaded, entries, observed_digest

    def _assert_authenticated_manifest_rejected(
        self,
        manifest_path: Path,
        manifest: dict[str, object],
        pattern: str,
    ) -> None:
        payload = manifest_bytes(manifest)
        manifest_path.write_bytes(payload)
        with self.assertRaisesRegex(RestoreVerificationError, pattern):
            load_authenticated_manifest(
                manifest_path,
                hashlib.sha256(payload).hexdigest().upper(),
            )

    def test_exact_synthetic_restore_rehashes_without_modifying_either_tree(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            source, restore, manifest, entries, digest = (
                self._authenticated_fixture(temporary)
            )
            source_before = {
                path.relative_to(source).as_posix(): path.read_bytes()
                for path in source.rglob("*")
                if path.is_file()
            }
            restore_before = {
                path.relative_to(restore).as_posix(): path.read_bytes()
                for path in restore.rglob("*")
                if path.is_file()
            }

            first = verify_isolated_restore(
                manifest,
                entries,
                digest,
                restore,
            )
            second = verify_isolated_restore(
                manifest,
                entries,
                digest,
                restore,
            )

            self.assertEqual(report_bytes(first), report_bytes(second))
            self.assertEqual(
                first["status"],
                "isolated_tree_matches_authenticated_manifest_acl_unverified",
            )
            self.assertTrue(first["restore"]["exact_path_set"])
            self.assertTrue(first["restore"]["every_file_rehashed"])
            self.assertTrue(
                first["restore"]["stable_opened_file_identity_hashing"]
            )
            self.assertFalse(
                first["storage_verification"]["payload_copied_by_this_tool"]
            )
            self.assertFalse(
                first["storage_verification"][
                    "external_storage_access_control_verified"
                ]
            )
            self.assertIn("does not copy payloads", first["claim_limit"])
            self.assertEqual(
                source_before,
                {
                    path.relative_to(source).as_posix(): path.read_bytes()
                    for path in source.rglob("*")
                    if path.is_file()
                },
            )
            self.assertEqual(
                restore_before,
                {
                    path.relative_to(restore).as_posix(): path.read_bytes()
                    for path in restore.rglob("*")
                    if path.is_file()
                },
            )

    def test_direct_api_reauthenticates_inputs_before_restore_scan(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            _, restore, manifest, entries, digest = (
                self._authenticated_fixture(temporary)
            )

            invalid_cases: list[
                tuple[
                    str,
                    dict[str, object],
                    list[dict[str, object]],
                    str,
                    str,
                ]
            ] = []
            invalid_cases.append(
                (
                    "wrong_digest",
                    manifest,
                    entries,
                    "0" * 64,
                    "storage manifest SHA-256 mismatch",
                )
            )

            detached_entries = copy.deepcopy(entries)
            detached_entries[0]["scope"] = (
                "project_content"
                if detached_entries[0]["scope"] != "project_content"
                else "project_descriptor"
            )
            invalid_cases.append(
                (
                    "detached_entries",
                    manifest,
                    detached_entries,
                    digest,
                    "entries do not exactly match",
                )
            )

            invalid_manifest = copy.deepcopy(manifest)
            invalid_manifest["storage_verification"]["manifest_only"] = False
            invalid_payload = (
                json.dumps(invalid_manifest, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            invalid_cases.append(
                (
                    "semantically_invalid_manifest",
                    invalid_manifest,
                    invalid_manifest["entries"],
                    hashlib.sha256(invalid_payload).hexdigest().upper(),
                    "must remain manifest-only",
                )
            )

            for (
                label,
                supplied_manifest,
                supplied_entries,
                supplied_digest,
                pattern,
            ) in invalid_cases:
                with self.subTest(case=label), patch(
                    "Tools.verify_redmmo_content_storage_restore."
                    "_discover_restored_tree",
                    wraps=_discover_restored_tree,
                ) as discover:
                    with self.assertRaisesRegex(
                        RestoreVerificationError,
                        pattern,
                    ):
                        verify_isolated_restore(
                            supplied_manifest,
                            supplied_entries,
                            supplied_digest,
                            restore,
                        )
                    discover.assert_not_called()

    def test_direct_api_uses_one_private_authenticated_input_snapshot(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            _, restore, manifest, entries, digest = (
                self._authenticated_fixture(temporary)
            )
            caller_manifest = copy.deepcopy(manifest)
            caller_entries = copy.deepcopy(entries)
            discoveries = 0

            def discover_then_mutate(
                root: Path,
            ) -> tuple[object, tuple[str, ...]]:
                nonlocal discoveries
                observed = _discover_restored_tree(root)
                discoveries += 1
                if discoveries == 1:
                    caller_manifest["scope"]["signature_sha256"] = "0" * 64
                    caller_entries.clear()
                return observed

            with patch(
                "Tools.verify_redmmo_content_storage_restore."
                "_discover_restored_tree",
                side_effect=discover_then_mutate,
            ):
                report = verify_isolated_restore(
                    caller_manifest,
                    caller_entries,
                    digest,
                    restore,
                )

            self.assertEqual(discoveries, 2)
            self.assertEqual(
                report["manifest"]["manifest_sha256"],
                digest,
            )
            self.assertEqual(
                report["manifest"]["payload_signature_sha256"],
                manifest["scope"]["signature_sha256"],
            )
            self.assertEqual(caller_entries, [])

    def test_direct_api_rejects_invalid_envelopes_before_restore_scan(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            _, restore, manifest, entries, digest = (
                self._authenticated_fixture(temporary)
            )
            invalid_inputs = [
                (
                    "malformed_digest",
                    manifest,
                    entries,
                    "not-a-digest",
                    "expected manifest SHA-256 must be",
                ),
                (
                    "non_plain_manifest",
                    MappingProxyType(manifest),
                    entries,
                    digest,
                    "manifest input must be a plain JSON object",
                ),
                (
                    "non_plain_entries",
                    manifest,
                    tuple(entries),
                    digest,
                    "entries input must be a plain JSON array",
                ),
            ]
            for (
                label,
                supplied_manifest,
                supplied_entries,
                supplied_digest,
                pattern,
            ) in invalid_inputs:
                with self.subTest(case=label), patch(
                    "Tools.verify_redmmo_content_storage_restore."
                    "_discover_restored_tree",
                    wraps=_discover_restored_tree,
                ) as discover:
                    with self.assertRaisesRegex(
                        RestoreVerificationError,
                        pattern,
                    ):
                        verify_isolated_restore(
                            supplied_manifest,
                            supplied_entries,
                            supplied_digest,
                            restore,
                        )
                    discover.assert_not_called()

            for label, invalid_claim, pattern in (
                (
                    "nonfinite_manifest_value",
                    float("nan"),
                    "not canonical JSON data",
                ),
                (
                    "circular_manifest_value",
                    None,
                    "not canonical JSON data",
                ),
            ):
                supplied_manifest = copy.deepcopy(manifest)
                supplied_manifest["claim_limit"] = (
                    supplied_manifest
                    if label == "circular_manifest_value"
                    else invalid_claim
                )
                with self.subTest(case=label), patch(
                    "Tools.verify_redmmo_content_storage_restore."
                    "_discover_restored_tree",
                    wraps=_discover_restored_tree,
                ) as discover:
                    with self.assertRaisesRegex(
                        RestoreVerificationError,
                        pattern,
                    ):
                        verify_isolated_restore(
                            supplied_manifest,
                            entries,
                            digest,
                            restore,
                        )
                    discover.assert_not_called()

            with patch(
                "Tools.verify_redmmo_content_storage_restore."
                "MAX_MANIFEST_BYTES",
                64,
            ), patch(
                "Tools.verify_redmmo_content_storage_restore."
                "_discover_restored_tree",
                wraps=_discover_restored_tree,
            ) as discover, self.assertRaisesRegex(
                RestoreVerificationError,
                "exceeds the 64-byte limit",
            ):
                verify_isolated_restore(
                    manifest,
                    entries,
                    digest,
                    restore,
                )
            discover.assert_not_called()

    def test_manifest_requires_pinned_raw_digest_and_canonical_unique_json(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            source = temporary / "Source"
            source.mkdir()
            self._fixture(source)
            manifest = build_storage_manifest(source, protected_hashes={})
            manifest_path = temporary / "Manifest" / "storage_manifest.json"
            manifest_path.parent.mkdir()
            payload = manifest_bytes(manifest)
            manifest_path.write_bytes(payload)
            with self.assertRaisesRegex(
                RestoreVerificationError,
                "SHA-256 mismatch",
            ):
                load_authenticated_manifest(manifest_path, "0" * 64)

            noncanonical = json.dumps(manifest).encode("utf-8")
            manifest_path.write_bytes(noncanonical)
            with self.assertRaisesRegex(
                RestoreVerificationError,
                "canonical serialized form",
            ):
                load_authenticated_manifest(
                    manifest_path,
                    hashlib.sha256(noncanonical).hexdigest().upper(),
                )

            duplicate = (
                b'{"schema_version":1,"schema_version":1,'
                b'"manifest_id":"duplicate"}\n'
            )
            manifest_path.write_bytes(duplicate)
            with self.assertRaisesRegex(
                RestoreVerificationError,
                "duplicate JSON object key",
            ):
                load_authenticated_manifest(
                    manifest_path,
                    hashlib.sha256(duplicate).hexdigest().upper(),
                )

    def test_manifest_identity_replacement_after_validation_fails_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            source = temporary / "Source"
            source.mkdir()
            self._fixture(source)
            manifest = build_storage_manifest(source, protected_hashes={})
            payload = manifest_bytes(manifest)
            manifest_path = (
                temporary / "Manifest" / "storage_manifest.json"
            ).absolute()
            manifest_path.parent.mkdir()
            manifest_path.write_bytes(payload)
            decoy = temporary / "byte_identical_decoy.json"
            displaced = temporary / "displaced_original.json"
            decoy.write_bytes(payload)
            original_identity = (
                manifest_path.stat().st_dev,
                manifest_path.stat().st_ino,
            )
            decoy_identity = (
                decoy.stat().st_dev,
                decoy.stat().st_ino,
            )
            self.assertNotEqual(original_identity, decoy_identity)
            validations = 0

            def swap_between_validation_and_open(
                path: Path,
                root: Path,
                label: str,
            ) -> object:
                nonlocal validations
                if path.absolute() == manifest_path:
                    if validations == 0:
                        observed = _require_regular_file(path, root, label)
                        os.replace(manifest_path, displaced)
                        os.replace(decoy, manifest_path)
                        validations = 1
                        return observed
                    if validations == 1:
                        os.replace(manifest_path, decoy)
                        os.replace(displaced, manifest_path)
                        validations = 2
                return _require_regular_file(path, root, label)

            try:
                with patch(
                    "Tools.verify_redmmo_content_storage_restore."
                    "_require_regular_file",
                    side_effect=swap_between_validation_and_open,
                ), self.assertRaisesRegex(
                    RestoreVerificationError,
                    "identity changed between validation and stable open",
                ):
                    load_authenticated_manifest(
                        manifest_path,
                        hashlib.sha256(payload).hexdigest().upper(),
                    )
            finally:
                if displaced.exists():
                    if manifest_path.exists():
                        os.replace(manifest_path, decoy)
                    os.replace(displaced, manifest_path)

            self.assertEqual(validations, 1)
            self.assertEqual(
                (
                    manifest_path.stat().st_dev,
                    manifest_path.stat().st_ino,
                ),
                original_identity,
            )
            self.assertEqual(manifest_path.read_bytes(), payload)
            self.assertEqual(decoy.read_bytes(), payload)

    @unittest.skipUnless(os.name == "nt", "Windows stable manifest handle")
    def test_manifest_stable_handle_denies_concurrent_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            source = temporary / "Source"
            source.mkdir()
            self._fixture(source)
            manifest = build_storage_manifest(source, protected_hashes={})
            payload = manifest_bytes(manifest)
            manifest_path = temporary / "Manifest" / "storage_manifest.json"
            manifest_path.parent.mkdir()
            manifest_path.write_bytes(payload)
            writer_opened = False
            writer_error: OSError | None = None
            probed = False

            def probe_competing_writer(
                handle: int,
                label: str,
            ) -> object:
                nonlocal probed, writer_error, writer_opened
                observed = _windows_require_plain_file_handle(handle, label)
                if label == "storage manifest" and not probed:
                    probed = True
                    try:
                        descriptor = os.open(
                            manifest_path,
                            os.O_WRONLY | getattr(os, "O_BINARY", 0),
                        )
                    except OSError as error:
                        writer_error = error
                    else:
                        writer_opened = True
                        os.close(descriptor)
                return observed

            with patch(
                "Tools.verify_redmmo_content_storage_restore."
                "_windows_require_plain_file_handle",
                side_effect=probe_competing_writer,
            ):
                loaded, _entries, observed_digest = (
                    load_authenticated_manifest(
                        manifest_path,
                        hashlib.sha256(payload).hexdigest().upper(),
                    )
                )

            self.assertEqual(loaded, manifest)
            self.assertEqual(
                observed_digest,
                hashlib.sha256(payload).hexdigest().upper(),
            )
            self.assertTrue(probed)
            self.assertFalse(writer_opened)
            self.assertIsNotNone(writer_error)
            assert writer_error is not None
            self.assertEqual(writer_error.errno, errno.EACCES)

    @unittest.skipUnless(os.name == "nt", "Windows manifest parent handle")
    def test_manifest_parent_pinning_uses_read_only_directory_access(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            parent = Path(temporary_name).resolve()
            manifest_path = parent / "storage_manifest.json"
            payload = b"{}\n"
            manifest_path.write_bytes(payload)

            with patch(
                "Tools.verify_redmmo_content_storage_restore."
                "_windows_open_pinned_directory",
                side_effect=RestoreVerificationError("access probe"),
            ) as pinned, self.assertRaisesRegex(
                RestoreVerificationError,
                "access probe",
            ):
                load_authenticated_manifest(
                    manifest_path,
                    hashlib.sha256(payload).hexdigest().upper(),
                )

            desired_access = pinned.call_args.kwargs["desired_access"]
            self.assertEqual(desired_access, WINDOWS_DIRECTORY_PIN_ACCESS)
            forbidden_access = (
                WINDOWS_FILE_LIST_DIRECTORY
                | WINDOWS_FILE_ADD_FILE
                | WINDOWS_FILE_ADD_SUBDIRECTORY
            )
            self.assertEqual(desired_access & forbidden_access, 0)
            share_mode = pinned.call_args.kwargs["share_mode"]
            self.assertEqual(
                share_mode,
                WINDOWS_FILE_SHARE_READ | WINDOWS_FILE_SHARE_WRITE,
            )
            self.assertEqual(share_mode & WINDOWS_FILE_SHARE_DELETE, 0)
            self.assertEqual(
                pinned.call_args.args,
                (
                    parent,
                    _metadata(parent),
                    "manifest parent",
                ),
            )

    @unittest.skipUnless(os.name == "nt", "Windows manifest parent handle")
    def test_manifest_parent_junction_swap_is_denied_until_auth_returns(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            dir=r"D:\RedMMOTitanWindowsData\Diagnostics",
        ) as temporary_name:
            root = Path(temporary_name)
            source = root / "Source"
            source.mkdir()
            self._fixture(source)
            manifest = build_storage_manifest(source, protected_hashes={})
            payload = manifest_bytes(manifest)
            digest = hashlib.sha256(payload).hexdigest().upper()
            parent = root / "Manifest"
            parent.mkdir()
            manifest_path = parent / "storage_manifest.json"
            manifest_path.write_bytes(payload)
            original_parent_identity = (
                parent.stat().st_dev,
                parent.stat().st_ino,
            )
            displaced = root / "Manifest_Original"
            attacker = root / "Attacker"
            attacker.mkdir()
            attacker_manifest = attacker / manifest_path.name
            attacker_manifest.write_bytes(payload)
            self.assertNotEqual(
                (
                    manifest_path.stat().st_dev,
                    manifest_path.stat().st_ino,
                ),
                (
                    attacker_manifest.stat().st_dev,
                    attacker_manifest.stat().st_ino,
                ),
            )
            parent_validations = 0
            rename_error: OSError | None = None
            junction_installed = False

            def attempt_swap_after_final_path_check(
                handle: int,
                label: str,
            ) -> object:
                nonlocal junction_installed, parent_validations, rename_error
                observed = _windows_require_plain_directory_handle(
                    handle,
                    label,
                )
                if label == "manifest parent":
                    parent_validations += 1
                    if parent_validations == 2:
                        try:
                            parent.rename(displaced)
                        except OSError as error:
                            rename_error = error
                        else:
                            self._create_junction(parent, attacker)
                            junction_installed = True
                return observed

            try:
                with patch(
                    "Tools.verify_redmmo_content_storage_restore."
                    "_windows_require_plain_directory_handle",
                    side_effect=attempt_swap_after_final_path_check,
                ):
                    loaded, entries, observed_digest = (
                        load_authenticated_manifest(
                            manifest_path,
                            digest,
                        )
                    )
            finally:
                if displaced.exists():
                    if os.path.lexists(parent):
                        ctypes.set_last_error(0)
                        removed = ctypes.windll.kernel32.RemoveDirectoryW(
                            str(parent)
                        )
                        self.assertTrue(
                            removed,
                            msg=str(
                                ctypes.WinError(ctypes.get_last_error())
                            ),
                        )
                    displaced.rename(parent)

            self.assertEqual(loaded, manifest)
            self.assertEqual(entries, manifest["entries"])
            self.assertEqual(observed_digest, digest)
            self.assertEqual(parent_validations, 2)
            self.assertIsNotNone(rename_error)
            assert rename_error is not None
            self.assertEqual(rename_error.errno, errno.EACCES)
            self.assertFalse(junction_installed)
            self.assertFalse(displaced.exists())
            self.assertEqual(
                (
                    parent.stat().st_dev,
                    parent.stat().st_ino,
                ),
                original_parent_identity,
            )
            self.assertEqual(manifest_path.read_bytes(), payload)
            self.assertEqual(attacker_manifest.read_bytes(), payload)

    def test_manifest_rejects_unknown_schema_unsafe_paths_and_type_tricks(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            source = temporary / "Source"
            source.mkdir()
            self._fixture(source)
            baseline = build_storage_manifest(source, protected_hashes={})
            manifest_path = temporary / "Manifest" / "storage_manifest.json"
            manifest_path.parent.mkdir()

            mutants: list[dict[str, object]] = []
            unknown = copy.deepcopy(baseline)
            unknown["untrusted_extension"] = True
            mutants.append(unknown)
            backslash = copy.deepcopy(baseline)
            backslash["entries"][0]["path"] = "Content\\escape.uasset"
            mutants.append(backslash)
            traversal = copy.deepcopy(baseline)
            traversal["entries"][0]["path"] = "../escape.uasset"
            mutants.append(traversal)
            alternate_stream = copy.deepcopy(baseline)
            alternate_stream["entries"][0]["path"] = "Content/A.uasset:evil"
            mutants.append(alternate_stream)
            bool_size = copy.deepcopy(baseline)
            bool_size["entries"][0]["bytes"] = True
            mutants.append(bool_size)
            lowercase_hash = copy.deepcopy(baseline)
            lowercase_hash["entries"][0]["sha256"] = str(
                lowercase_hash["entries"][0]["sha256"]
            ).lower()
            mutants.append(lowercase_hash)
            bool_schema = copy.deepcopy(baseline)
            bool_schema["schema_version"] = True
            mutants.append(bool_schema)
            overflow = copy.deepcopy(baseline)
            overflow["entries"][0]["bytes"] = 1 << 63
            mutants.append(overflow)
            case_prefix = copy.deepcopy(baseline)
            case_prefix["entries"][0]["path"] = "Content/Foo/A.uasset"
            case_prefix["entries"][1]["path"] = "Content/foo/B.uasset"
            mutants.append(case_prefix)
            file_directory_conflict = copy.deepcopy(baseline)
            file_directory_conflict["entries"][0]["path"] = "Content/Foo"
            file_directory_conflict["entries"][1]["path"] = (
                "Content/Foo/B.uasset"
            )
            mutants.append(file_directory_conflict)

            for mutant in mutants:
                payload = manifest_bytes(mutant)
                manifest_path.write_bytes(payload)
                with self.subTest(mutant=mutants.index(mutant)):
                    with self.assertRaises(RestoreVerificationError):
                        load_authenticated_manifest(
                            manifest_path,
                            hashlib.sha256(payload).hexdigest().upper(),
                        )

            baseline_payload = manifest_bytes(baseline)
            byte_token = (
                f'"bytes": {baseline["entries"][0]["bytes"]}'
            ).encode("utf-8")
            self.assertIn(byte_token, baseline_payload)
            nonfinite = baseline_payload.replace(
                byte_token,
                b'"bytes": NaN',
                1,
            )
            manifest_path.write_bytes(nonfinite)
            with self.assertRaisesRegex(
                RestoreVerificationError,
                "non-finite JSON number",
            ):
                load_authenticated_manifest(
                    manifest_path,
                    hashlib.sha256(nonfinite).hexdigest().upper(),
                )

    def test_authenticated_manifest_rejects_semantic_schema_drift(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            source = temporary / "Source"
            source.mkdir()
            self._fixture(source)
            baseline = build_storage_manifest(source, protected_hashes={})
            manifest_path = temporary / "Manifest" / "storage_manifest.json"
            manifest_path.parent.mkdir()

            selection_type = copy.deepcopy(baseline)
            selection_type["selection_policy"]["content_files"] = True
            self._assert_authenticated_manifest_rejected(
                manifest_path,
                selection_type,
                "selection policy does not match",
            )

            engine_type = copy.deepcopy(baseline)
            engine_type["project_identity"]["engine_association"] = False
            self._assert_authenticated_manifest_rejected(
                manifest_path,
                engine_type,
                "engine association is unexpected",
            )

            module_type = copy.deepcopy(baseline)
            module_type["project_identity"]["module_names"] = "RedMMO"
            self._assert_authenticated_manifest_rejected(
                manifest_path,
                module_type,
                "project_identity.module_names must be a JSON array",
            )

            plugin_metadata_type = copy.deepcopy(baseline)
            plugin_metadata_type["plugins"][0]["friendly_name"] = False
            self._assert_authenticated_manifest_rejected(
                manifest_path,
                plugin_metadata_type,
                "friendly_name must be a string or null",
            )

            plugin_bool_type = copy.deepcopy(baseline)
            plugin_bool_type["plugins"][0]["installed"] = "false"
            self._assert_authenticated_manifest_rejected(
                manifest_path,
                plugin_bool_type,
                "installed must be a boolean or null",
            )

            plugin_list_type = copy.deepcopy(baseline)
            plugin_list_type["plugins"][0][
                "excluded_generated_top_level_directories_present"
            ] = "Binaries"
            self._assert_authenticated_manifest_rejected(
                manifest_path,
                plugin_list_type,
                "must be a JSON array",
            )

            plugin_order = copy.deepcopy(baseline)
            plugin_order["plugins"].reverse()
            self._assert_authenticated_manifest_rejected(
                manifest_path,
                plugin_order,
                "canonical plugin ID order",
            )

            descriptor_target = copy.deepcopy(baseline)
            plugin = descriptor_target["plugins"][0]
            source_entry = next(
                row
                for row in descriptor_target["entries"]
                if row["path"] == "Plugins/RedHUD/Source/RedHUD.cpp"
            )
            plugin["descriptor_path"] = source_entry["path"]
            plugin["descriptor_sha256"] = source_entry["sha256"]
            self._assert_authenticated_manifest_rejected(
                manifest_path,
                descriptor_target,
                "immediate matching .uplugin child",
            )

            protected_duplicate = copy.deepcopy(baseline)
            protected_entry = protected_duplicate["entries"][0]
            protected_record = {
                "path": protected_entry["path"],
                "expected_sha256": protected_entry["sha256"],
                "observed_sha256": protected_entry["sha256"],
                "matches": True,
            }
            protected_duplicate["protected_inputs"] = [
                protected_record,
                copy.deepcopy(protected_record),
            ]
            self._assert_authenticated_manifest_rejected(
                manifest_path,
                protected_duplicate,
                "protected inputs must be unique",
            )

            unhashable_scope = copy.deepcopy(baseline)
            unhashable_scope["entries"][0]["scope"] = {}
            self._assert_authenticated_manifest_rejected(
                manifest_path,
                unhashable_scope,
                "has invalid scope",
            )

    def test_authenticated_manifest_rejects_excluded_plugin_root_entry(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            source = temporary / "Source"
            source.mkdir()
            self._fixture(source)
            mutant = build_storage_manifest(source, protected_hashes={})
            manifest_path = temporary / "Manifest" / "storage_manifest.json"
            manifest_path.parent.mkdir()

            moved = next(
                row
                for row in mutant["entries"]
                if row["path"] == "Plugins/RedHUD/Source/RedHUD.cpp"
            )
            moved["path"] = "Plugins/RedHUD/Binaries/Win64/Injected.dll"
            mutant["entries"].sort(key=lambda row: row["path"].casefold())
            mutant["scope"]["payload_signature_sha256"] = _signature(
                mutant["entries"]
            )
            mutant["scope"]["path_signature_sha256"] = _path_signature(
                mutant["entries"]
            )
            red_hud_members = [
                row
                for row in mutant["entries"]
                if row["plugin_id"] == "RedHUD"
            ]
            red_hud = next(
                plugin
                for plugin in mutant["plugins"]
                if plugin["plugin_id"] == "RedHUD"
            )
            red_hud["signature_sha256"] = _signature(red_hud_members)

            self._assert_authenticated_manifest_rejected(
                manifest_path,
                mutant,
                "excluded generated plugin root",
            )

    def test_missing_unexpected_and_changed_restore_payloads_fail_closed(
        self,
    ) -> None:
        for mutation in (
            "missing",
            "unexpected",
            "extra_empty_directory",
            "changed",
            "size",
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as name:
                temporary = Path(name)
                _, restore, manifest, entries, digest = (
                    self._authenticated_fixture(temporary)
                )
                target = restore / str(entries[0]["path"])
                if mutation == "missing":
                    target.unlink()
                elif mutation == "unexpected":
                    self._write(restore, "Unexpected/file.bin", b"extra")
                elif mutation == "extra_empty_directory":
                    (restore / "UnexpectedEmpty").mkdir()
                elif mutation == "changed":
                    payload = bytearray(target.read_bytes())
                    payload[0] ^= 0x01
                    target.write_bytes(payload)
                else:
                    target.write_bytes(target.read_bytes() + b"x")
                with self.assertRaises(RestoreVerificationError):
                    verify_isolated_restore(
                        manifest,
                        entries,
                        digest,
                        restore,
                    )

    def test_restore_reparse_and_hard_link_topology_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            _, restore, manifest, entries, digest = (
                self._authenticated_fixture(temporary)
            )
            linked_directory = restore / "Linked"
            linked_directory.mkdir()
            with patch(
                "Tools.verify_redmmo_content_storage_restore."
                "_is_link_or_reparse",
                side_effect=lambda path, metadata=None: path == linked_directory,
            ), self.assertRaisesRegex(
                RestoreVerificationError,
                "reparse",
            ):
                verify_isolated_restore(
                    manifest,
                    entries,
                    digest,
                    restore,
                )

        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            _, restore, manifest, entries, digest = (
                self._authenticated_fixture(temporary)
            )
            source = restore / str(entries[0]["path"])
            alias = restore / "Alias.bin"
            try:
                alias.hardlink_to(source)
            except OSError as error:
                self.skipTest(
                    f"hard links unavailable in fixture filesystem: {error}"
                )
            with self.assertRaisesRegex(
                RestoreVerificationError,
                "hard-linked",
            ):
                verify_isolated_restore(
                    manifest,
                    entries,
                    digest,
                    restore,
                )

    def test_concurrent_restored_file_mutation_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            _, restore, manifest, entries, digest = (
                self._authenticated_fixture(temporary)
            )
            target = restore / str(entries[0]["path"])
            original = _sha256_file
            mutated = False

            def mutate_after_hash(
                path: Path,
                expected_metadata: object = None,
                root: Path | None = None,
            ) -> str:
                nonlocal mutated
                observed = original(path, expected_metadata, root)
                if path == target and not mutated:
                    mutated = True
                    path.write_bytes(path.read_bytes() + b"mutated")
                return observed

            with patch(
                "Tools.verify_redmmo_content_storage_restore._sha256_file",
                side_effect=mutate_after_hash,
            ), self.assertRaisesRegex(
                RestoreVerificationError,
                "changed while hashing",
            ):
                verify_isolated_restore(
                    manifest,
                    entries,
                    digest,
                    restore,
                )

    def test_aba_path_replacement_between_discovery_and_open_fails_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            _, restore, manifest, entries, digest = (
                self._authenticated_fixture(temporary)
            )
            target_entry = next(
                row for row in entries if int(row["bytes"]) > 0
            )
            target = restore / str(target_entry["path"])
            expected_payload = target.read_bytes()
            corrupt_payload = bytearray(expected_payload)
            corrupt_payload[0] ^= 0x01
            corrupt_bytes = bytes(corrupt_payload)
            target.write_bytes(corrupt_bytes)

            trusted = temporary / "TrustedExpected.bin"
            displaced = temporary / "DisplacedCorrupt.bin"
            trusted.write_bytes(expected_payload)
            original_open = _open_binary_read
            injections = 0

            class SwapBackOnExit:
                def __init__(self, handle: object) -> None:
                    self.handle = handle

                def __enter__(self) -> object:
                    return self.handle

                def __exit__(
                    self,
                    exc_type: object,
                    exc_value: object,
                    traceback: object,
                ) -> bool:
                    self.handle.close()
                    try:
                        os.replace(target, trusted)
                    finally:
                        os.replace(displaced, target)
                    return False

            def open_with_aba(path: Path) -> object:
                nonlocal injections
                if path == target and injections == 0:
                    injections += 1
                    os.replace(target, displaced)
                    os.replace(trusted, target)
                    return SwapBackOnExit(original_open(path))
                return original_open(path)

            with patch(
                "Tools.verify_redmmo_content_storage_restore._open_binary_read",
                side_effect=open_with_aba,
            ), (
                self.assertRaisesRegex(
                    RestoreVerificationError,
                    "restored file identity changed before hashing",
                )
            ):
                verify_isolated_restore(
                    manifest,
                    entries,
                    digest,
                    restore,
                )

            self.assertEqual(injections, 1)
            self.assertEqual(target.read_bytes(), corrupt_bytes)
            self.assertEqual(trusted.read_bytes(), expected_payload)

    def test_active_project_is_refused_as_restore_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            source = temporary / "Source"
            source.mkdir()
            self._fixture(source)
            manifest = build_storage_manifest(source, protected_hashes={})
            entries = manifest["entries"]
            with self.assertRaisesRegex(
                RestoreVerificationError,
                "isolated from the active Unreal project",
            ):
                verify_isolated_restore(
                    manifest,
                    entries,
                    "0" * 64,
                    ROOT,
                )

    @unittest.skipUnless(os.name == "nt", "Windows path alias contract")
    def test_windows_extended_alias_cannot_bypass_active_project_isolation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            dir=r"D:\RedMMOTitanWindowsData\Diagnostics",
        ) as temporary_name:
            temporary = Path(temporary_name)
            manifest_parent = temporary / "Manifest"
            manifest_parent.mkdir()
            manifest_path = manifest_parent / "storage_manifest.json"
            manifest_path.write_text("{}\n", encoding="utf-8")

            for restore_root in (
                _windows_extended_path(ROOT),
                _windows_extended_path(ROOT / "Content"),
            ):
                with self.subTest(restore_root=restore_root):
                    with self.assertRaisesRegex(
                        RestoreVerificationError,
                        "isolated from the active Unreal project",
                    ):
                        validate_input_isolation(
                            manifest_path,
                            restore_root,
                        )

            nested_manifest = temporary / "Restore" / "storage_manifest.json"
            nested_manifest.parent.mkdir()
            nested_manifest.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(
                RestoreVerificationError,
                "outside the restored tree",
            ):
                validate_input_isolation(
                    nested_manifest,
                    _windows_extended_path(nested_manifest.parent),
                )

            with self.assertRaisesRegex(
                RestoreVerificationError,
                "isolated from the active Unreal project",
            ):
                verify_isolated_restore(
                    {},
                    [],
                    "0" * 64,
                    _windows_extended_path(ROOT.parent),
                )

    @unittest.skipUnless(os.name == "nt", "Windows path identity contract")
    def test_windows_overlap_fails_closed_without_stable_identity(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=r"D:\RedMMOTitanWindowsData\Diagnostics",
        ) as temporary_name:
            root = Path(temporary_name)
            first = root / "First"
            second = root / "Second"
            first.mkdir()
            second.mkdir()
            original_metadata = _metadata

            def metadata_without_first_identity(path: Path) -> object:
                observed = original_metadata(path)
                if path.absolute() == first.absolute():
                    return replace(observed, inode=0)
                return observed

            with patch(
                "Tools.verify_redmmo_content_storage_restore._metadata",
                side_effect=metadata_without_first_identity,
            ), self.assertRaisesRegex(
                RestoreVerificationError,
                "stable path identity is unavailable",
            ):
                _paths_overlap(first, second)

    @unittest.skipUnless(os.name == "nt", "Windows local path contract")
    def test_windows_network_and_device_namespaces_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=r"D:\RedMMOTitanWindowsData\Diagnostics",
        ) as temporary_name:
            temporary = Path(temporary_name)
            manifest_path = temporary / "storage_manifest.json"
            manifest_path.write_text("{}\n", encoding="utf-8")
            project_tail = str(ROOT)[3:].replace("\\", "/")
            unsupported_roots = (
                Path(f"//localhost/D$/{project_tail}"),
                Path(f"//?/UNC/localhost/D$/{project_tail}"),
                Path("//./D:/RedMMOTitan"),
                Path("//?/Volume{00000000-0000-0000-0000-000000000000}/"),
            )
            for restore_root in unsupported_roots:
                with self.subTest(restore_root=restore_root):
                    with self.assertRaisesRegex(
                        RestoreVerificationError,
                        "must use a local DOS drive path",
                    ):
                        validate_input_isolation(manifest_path, restore_root)

            with patch(
                "Tools.verify_redmmo_content_storage_restore._windows_drive_type",
                return_value=4,
            ), self.assertRaisesRegex(
                RestoreVerificationError,
                "available non-network DOS drive",
            ):
                _require_plain_directory(ROOT, "mapped restore root")

    def test_output_is_external_atomic_no_clobber_and_not_in_restore(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            root = Path(temporary_name)
            diagnostics = root / "Diagnostics"
            diagnostics.mkdir()
            restore = root / "Restore"
            restore.mkdir()
            output = diagnostics / "M07" / "restore_report.json"
            resolved = validate_output_path(
                output,
                diagnostics_root=diagnostics,
                restore_root=restore,
            )
            write_report_atomic(
                resolved,
                b"{}\n",
                diagnostics_root=diagnostics,
                restore_root=restore,
            )
            self.assertEqual(resolved.read_bytes(), b"{}\n")
            with self.assertRaises(RestoreVerificationError):
                write_report_atomic(
                    resolved,
                    b'{"replace":true}\n',
                    diagnostics_root=diagnostics,
                    restore_root=restore,
                )
            with self.assertRaises(RestoreVerificationError):
                validate_output_path(
                    root / "outside.json",
                    diagnostics_root=diagnostics,
                    restore_root=restore,
                )
            with self.assertRaisesRegex(
                RestoreVerificationError,
                "outside the restored tree",
            ):
                validate_output_path(
                    restore / "report.json",
                    diagnostics_root=restore,
                    restore_root=restore,
                )

    @unittest.skipUnless(os.name == "nt", "Windows path alias contract")
    def test_windows_extended_alias_cannot_bypass_restore_output_isolation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            dir=r"D:\RedMMOTitanWindowsData\Diagnostics",
        ) as temporary_name:
            root = Path(temporary_name)
            diagnostics = root / "Diagnostics"
            diagnostics.mkdir()
            output = diagnostics / "M07" / "restore_report.json"

            with self.assertRaisesRegex(
                RestoreVerificationError,
                "outside the restored tree",
            ):
                validate_output_path(
                    output,
                    diagnostics_root=diagnostics,
                    restore_root=_windows_extended_path(diagnostics),
                )

            sibling_restore = root / "Restore"
            sibling_restore.mkdir()
            self.assertEqual(
                validate_output_path(
                    output,
                    diagnostics_root=diagnostics,
                    restore_root=_windows_extended_path(sibling_restore),
                ),
                output,
            )

    @unittest.skipUnless(os.name == "nt", "Windows publication handle contract")
    def test_output_parent_junction_swap_after_validation_is_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            dir=r"D:\RedMMOTitanWindowsData\Diagnostics",
        ) as temporary_name:
            root = Path(temporary_name)
            diagnostics = root / "Diagnostics"
            diagnostics.mkdir()
            parent = diagnostics / "M07"
            parent.mkdir()
            displaced = root / "M07_Original"
            attacker = root / "Attacker"
            attacker.mkdir()
            output = parent / "restore_report.json"
            validated = validate_output_path(
                output,
                diagnostics_root=diagnostics,
            )
            parent.rename(displaced)
            self._create_junction(parent, attacker)
            try:
                with self.assertRaisesRegex(
                    RestoreVerificationError,
                    "linked or reparse output ancestor",
                ):
                    write_report_atomic(
                        validated,
                        b'{"trusted":true}\n',
                        diagnostics_root=diagnostics,
                    )
                self.assertFalse((attacker / output.name).exists())
                self.assertEqual(list(attacker.glob("*.tmp")), [])
                self.assertEqual(list(displaced.glob("*.tmp")), [])
            finally:
                os.rmdir(parent)
                displaced.rename(parent)

    @unittest.skipUnless(os.name == "nt", "Windows publication handle contract")
    def test_publication_parent_swap_cannot_redirect_final_or_cleanup(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            dir=r"D:\RedMMOTitanWindowsData\Diagnostics",
        ) as temporary_name:
            root = Path(temporary_name)
            diagnostics = root / "Diagnostics"
            diagnostics.mkdir()
            parent = diagnostics / "M07"
            parent.mkdir()
            displaced = root / "M07_Original"
            attacker = root / "Attacker"
            attacker.mkdir()
            output = parent / "restore_report.json"
            attempted = False
            attacker_sentinel: Path | None = None
            attacker_final = attacker / output.name
            attacker_final.write_bytes(b"attacker-final-sentinel")

            def swap_parent_before_temp(
                parent_handle: int,
                name: str,
                *,
                directory: bool,
            ) -> tuple[int, int]:
                nonlocal attempted, attacker_sentinel
                if not directory and not attempted:
                    attempted = True
                    parent.rename(displaced)
                    self._create_junction(parent, attacker)
                    attacker_sentinel = attacker / name
                    attacker_sentinel.write_bytes(b"attacker-sentinel")
                return _windows_nt_create_relative(
                    parent_handle,
                    name,
                    directory=directory,
                )

            try:
                with patch(
                    "Tools.verify_redmmo_content_storage_restore."
                    "_windows_nt_create_relative",
                    side_effect=swap_parent_before_temp,
                ), self.assertRaisesRegex(
                    RestoreVerificationError,
                    "parent path no longer names the pinned",
                ):
                    write_report_atomic(
                        output,
                        b'{"trusted":true}\n',
                        diagnostics_root=diagnostics,
                    )
                self.assertTrue(attempted)
                self.assertIsNotNone(attacker_sentinel)
                assert attacker_sentinel is not None
                self.assertEqual(
                    attacker_sentinel.read_bytes(),
                    b"attacker-sentinel",
                )
                self.assertEqual(
                    attacker_final.read_bytes(),
                    b"attacker-final-sentinel",
                )
                self.assertFalse((displaced / output.name).exists())
                self.assertEqual(list(displaced.glob("*.tmp")), [])
            finally:
                if os.path.lexists(parent):
                    os.rmdir(parent)
                if attacker_sentinel is not None:
                    attacker_sentinel.unlink(missing_ok=True)
                attacker_final.unlink(missing_ok=True)
                if displaced.exists():
                    displaced.rename(parent)

    @unittest.skipUnless(os.name == "nt", "Windows publication handle contract")
    def test_temporary_report_is_exclusive_and_not_marked_temporary(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            dir=r"D:\RedMMOTitanWindowsData\Diagnostics",
        ) as temporary_name:
            root = Path(temporary_name)
            diagnostics = root / "Diagnostics"
            diagnostics.mkdir()
            parent = diagnostics / "M07"
            parent.mkdir()
            output = parent / "restore_report.json"
            second_writer_opened = False
            second_writer_error: OSError | None = None

            def probe_exclusive_temporary(
                parent_handle: int,
                name: str,
                *,
                directory: bool,
            ) -> tuple[int, int]:
                nonlocal second_writer_opened, second_writer_error
                result = _windows_nt_create_relative(
                    parent_handle,
                    name,
                    directory=directory,
                )
                if not directory:
                    try:
                        descriptor = os.open(
                            parent / name,
                            os.O_WRONLY | getattr(os, "O_BINARY", 0),
                        )
                    except OSError as error:
                        second_writer_error = error
                    else:
                        second_writer_opened = True
                        os.close(descriptor)
                return result

            with patch(
                "Tools.verify_redmmo_content_storage_restore."
                "_windows_nt_create_relative",
                side_effect=probe_exclusive_temporary,
            ):
                write_report_atomic(
                    output,
                    b'{"trusted":true}\n',
                    diagnostics_root=diagnostics,
                )

            self.assertFalse(second_writer_opened)
            self.assertIsNotNone(second_writer_error)
            assert second_writer_error is not None
            self.assertEqual(second_writer_error.errno, errno.EACCES)
            self.assertEqual(output.read_bytes(), b'{"trusted":true}\n')
            attributes = getattr(output.stat(), "st_file_attributes", 0)
            self.assertFalse(attributes & WINDOWS_FILE_ATTRIBUTE_TEMPORARY)

    @unittest.skipUnless(os.name == "nt", "Windows publication handle contract")
    def test_native_no_clobber_rename_uses_retained_parent_handle(
        self,
    ) -> None:
        captured: list[dict[str, int | str]] = []
        flush_calls: list[int] = []

        class FakeKernel32:
            def FlushFileBuffers(self, handle: int) -> bool:
                flush_calls.append(handle)
                return True

        class FakeNtdll:
            def NtSetInformationFile(
                self,
                file_handle: int,
                _io_status: object,
                raw: ctypes.Array[ctypes.c_char],
                raw_length: int,
                information_class: int,
            ) -> int:
                rename = _WindowsFileRenameInformation.from_buffer(raw)
                name_offset = _WindowsFileRenameInformation.FileName.offset
                name_bytes = ctypes.string_at(
                    ctypes.addressof(raw) + name_offset,
                    rename.FileNameLength,
                )
                captured.append(
                    {
                        "file_handle": file_handle,
                        "root_directory": rename.RootDirectory,
                        "flags": rename.u.Flags,
                        "raw_length": raw_length,
                        "information_class": information_class,
                        "filename": name_bytes.decode("utf-16-le"),
                    }
                )
                return 0

        with patch(
            "Tools.verify_redmmo_content_storage_restore._windows_apis",
            return_value=(FakeKernel32(), FakeNtdll()),
        ):
            _windows_publish_open_file_no_clobber(
                111,
                222,
                "restore_report.json",
            )

        self.assertEqual(
            captured,
            [
                {
                    "file_handle": 111,
                    "root_directory": 222,
                    "flags": 0,
                    "raw_length": (
                        ctypes.sizeof(_WindowsFileRenameInformation)
                        + len("restore_report.json".encode("utf-16-le"))
                        + 2
                    ),
                    "information_class": WINDOWS_FILE_RENAME_INFORMATION,
                    "filename": "restore_report.json",
                }
            ],
        )
        self.assertEqual(flush_calls, [111])

    @unittest.skipUnless(os.name == "nt", "Windows publication durability")
    def test_native_publish_uses_write_through_and_post_rename_flush(
        self,
    ) -> None:
        events: list[tuple[object, ...]] = []

        class FakeKernel32:
            def FlushFileBuffers(self, handle: int) -> bool:
                events.append(("flush", handle))
                return True

        class FakeNtdll:
            def NtCreateFile(
                self,
                output: object,
                _access: int,
                _attributes: object,
                io_status: object,
                _allocation_size: object,
                _file_attributes: int,
                _share_mode: int,
                _disposition: int,
                options: int,
                _ea_buffer: object,
                _ea_length: int,
            ) -> int:
                output._obj.value = 111
                io_status._obj.Information = 2
                events.append(("create", options))
                return 0

            def NtSetInformationFile(
                self,
                file_handle: int,
                _io_status: object,
                raw: ctypes.Array[ctypes.c_char],
                _raw_length: int,
                _information_class: int,
            ) -> int:
                rename = _WindowsFileRenameInformation.from_buffer(raw)
                name_offset = _WindowsFileRenameInformation.FileName.offset
                name_bytes = ctypes.string_at(
                    ctypes.addressof(raw) + name_offset,
                    rename.FileNameLength,
                )
                events.append(
                    (
                        "rename",
                        file_handle,
                        rename.RootDirectory,
                        name_bytes.decode("utf-16-le"),
                    )
                )
                return 0

        with patch(
            "Tools.verify_redmmo_content_storage_restore._windows_apis",
            return_value=(FakeKernel32(), FakeNtdll()),
        ):
            handle, information = _windows_nt_create_relative(
                222,
                ".redmmo-restore-report-test.tmp",
                directory=False,
            )
            directory_handle, directory_information = (
                _windows_nt_create_relative(
                    222,
                    "CreatedParent",
                    directory=True,
                )
            )
            _windows_publish_open_file_no_clobber(
                handle,
                222,
                "restore_report.json",
            )

        self.assertEqual(directory_handle, 111)
        self.assertEqual(information, 2)
        self.assertEqual(directory_information, 2)
        self.assertTrue(events[0][1] & WINDOWS_FILE_WRITE_THROUGH)
        self.assertTrue(events[1][1] & WINDOWS_FILE_WRITE_THROUGH)
        self.assertEqual(
            events[2:],
            [
                ("rename", 111, 222, "restore_report.json"),
                ("flush", 111),
            ],
        )

    @unittest.skipUnless(os.name == "nt", "Windows publication durability")
    def test_post_rename_flush_failure_cleans_published_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            dir=r"D:\RedMMOTitanWindowsData\Diagnostics",
        ) as temporary_name:
            root = Path(temporary_name)
            diagnostics = root / "Diagnostics"
            diagnostics.mkdir()
            parent = diagnostics / "M07"
            parent.mkdir()
            output = parent / "restore_report.json"

            def fail_published_flush(handle: int, label: str) -> None:
                if label == "published report file":
                    raise RestoreVerificationError(
                        "injected published report file flush failure"
                    )
                _windows_flush_handle(handle, label)

            with patch(
                "Tools.verify_redmmo_content_storage_restore."
                "_windows_flush_handle",
                side_effect=fail_published_flush,
            ), self.assertRaisesRegex(
                RestoreVerificationError,
                "published report file flush failure",
            ):
                write_report_atomic(
                    output,
                    b'{"trusted":true}\n',
                    diagnostics_root=diagnostics,
                )

            self.assertFalse(output.exists())
            self.assertEqual(list(parent.glob("*.tmp")), [])

    @unittest.skipUnless(os.name == "nt", "Windows manifest handle contract")
    def test_native_manifest_open_uses_retained_parent_and_safe_flags(
        self,
    ) -> None:
        captured: list[dict[str, int]] = []

        class FakeNtdll:
            def NtCreateFile(
                self,
                output: object,
                access: int,
                attributes: object,
                _io_status: object,
                _allocation_size: object,
                file_attributes: int,
                share_mode: int,
                disposition: int,
                options: int,
                _ea_buffer: object,
                _ea_length: int,
            ) -> int:
                output._obj.value = 777
                captured.append(
                    {
                        "access": access,
                        "root_directory": attributes._obj.RootDirectory,
                        "file_attributes": file_attributes,
                        "share_mode": share_mode,
                        "disposition": disposition,
                        "options": options,
                    }
                )
                return 0

        with patch(
            "Tools.verify_redmmo_content_storage_restore._windows_apis",
            return_value=(object(), FakeNtdll()),
        ):
            handle = _windows_nt_open_manifest_relative(
                222,
                "storage_manifest.json",
            )

        self.assertEqual(handle, 777)
        self.assertEqual(
            captured,
            [
                {
                    "access": WINDOWS_MANIFEST_FILE_ACCESS,
                    "root_directory": 222,
                    "file_attributes": 0,
                    "share_mode": WINDOWS_FILE_SHARE_READ,
                    "disposition": WINDOWS_FILE_OPEN,
                    "options": (
                        WINDOWS_FILE_NON_DIRECTORY_FILE
                        | WINDOWS_FILE_SYNCHRONOUS_IO_NONALERT
                        | WINDOWS_FILE_OPEN_REPARSE_POINT
                    ),
                }
            ],
        )

    @unittest.skipUnless(os.name == "nt", "Windows publication handle contract")
    def test_late_competing_report_is_not_clobbered(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=r"D:\RedMMOTitanWindowsData\Diagnostics",
        ) as temporary_name:
            root = Path(temporary_name)
            diagnostics = root / "Diagnostics"
            diagnostics.mkdir()
            parent = diagnostics / "M07"
            parent.mkdir()
            output = parent / "restore_report.json"
            sentinel = b'{"existing":true}\n'
            injected = False

            def inject_competing_report(
                file_handle: int,
                parent_handle: int,
                final_name: str,
            ) -> None:
                nonlocal injected
                injected = True
                output.write_bytes(sentinel)
                _windows_publish_open_file_no_clobber(
                    file_handle,
                    parent_handle,
                    final_name,
                )

            with patch(
                "Tools.verify_redmmo_content_storage_restore."
                "_windows_publish_open_file_no_clobber",
                side_effect=inject_competing_report,
            ), self.assertRaisesRegex(
                RestoreVerificationError,
                "refusing to overwrite output",
            ):
                write_report_atomic(
                    output,
                    b'{"replace":true}\n',
                    diagnostics_root=diagnostics,
                )
            self.assertTrue(injected)
            self.assertEqual(output.read_bytes(), sentinel)
            self.assertEqual(list(parent.glob("*.tmp")), [])

    def test_manifest_must_remain_outside_restored_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            root = Path(temporary_name)
            restore = root / "Restore"
            restore.mkdir()
            manifest_path = restore / "storage_manifest.json"
            manifest_path.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(
                RestoreVerificationError,
                "outside the restored tree",
            ):
                validate_input_isolation(manifest_path, restore)

    def test_script_can_be_invoked_directly_from_project_root(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(
                    ROOT
                    / "Tools/verify_redmmo_content_storage_restore.py"
                ),
                "--help",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("--expected-manifest-sha256", result.stdout)
        self.assertIn("--restore-root", result.stdout)


if __name__ == "__main__":
    unittest.main()
