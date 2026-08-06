from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Tools.build_redmmo_content_storage_manifest import (
    FileMetadata,
    InventoryFile,
    StorageManifestError,
    _ensure_casefold_unique,
    build_storage_manifest,
    manifest_bytes,
    sha256_file,
    validate_output_path,
    write_manifest_atomic,
)


ROOT = Path(__file__).resolve().parents[2]


class RedMMOContentStorageManifestTests(unittest.TestCase):
    def _write(self, root: Path, relative: str, payload: bytes) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

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
        self._write(
            root,
            "Plugins/RedHUD/Intermediate/Build/RedHUD.obj",
            b"derived",
        )

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

    def test_manifest_hashes_all_content_and_plugin_inputs_but_not_derived_roots(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture(root)
            before = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }

            manifest = build_storage_manifest(root, protected_hashes={})

            after = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(before, after)
            paths = {entry["path"] for entry in manifest["entries"]}
            self.assertIn("Titan.uproject", paths)
            self.assertIn("Content/RedMMO/Maps/Main.umap", paths)
            self.assertIn("Plugins/RedHUD/Source/RedHUD.cpp", paths)
            self.assertIn("Plugins/RedHUD/Resources/Frame.png", paths)
            self.assertNotIn(
                "Plugins/RedHUD/Binaries/Win64/RedHUD.dll",
                paths,
            )
            self.assertNotIn(
                "Plugins/RedHUD/Intermediate/Build/RedHUD.obj",
                paths,
            )
            self.assertEqual(manifest["scope"]["file_count"], 8)
            self.assertEqual(manifest["scope"]["project_content_file_count"], 2)
            self.assertEqual(manifest["scope"]["project_plugin_count"], 2)
            self.assertTrue(manifest["scope"]["tree_quiescent_during_scan"])
            self.assertEqual(
                manifest["status"],
                "checksummed_source_inputs_ready_external_storage_unverified",
            )
            self.assertEqual(
                manifest["storage_verification"],
                {
                    "external_storage_copied": False,
                    "external_storage_access_control_verified": False,
                    "restore_tested": False,
                    "manifest_only": True,
                },
            )
            for excluded_name in (
                ".git",
                ".vs",
                "Binaries",
                "DerivedDataCache",
                "Intermediate",
                "Saved",
            ):
                self.assertIn(excluded_name, manifest["claim_limit"])

            by_path = {entry["path"]: entry for entry in manifest["entries"]}
            self.assertEqual(
                by_path["Content/SoStylized/SM_Rock.uasset"]["sha256"],
                hashlib.sha256(b"rock").hexdigest().upper(),
            )
            plugins = {
                plugin["plugin_id"]: plugin for plugin in manifest["plugins"]
            }
            self.assertTrue(plugins["RedHUD"]["enabled_in_project_descriptor"])
            self.assertFalse(plugins["VendorKit"]["enabled_in_project_descriptor"])
            self.assertEqual(
                plugins["RedHUD"][
                    "excluded_generated_top_level_directories_present"
                ],
                ["Binaries", "Intermediate"],
            )

    def test_manifest_bytes_are_repeatable_and_aggregate_changes_with_payload(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture(root)
            first = build_storage_manifest(root, protected_hashes={})
            second = build_storage_manifest(root, protected_hashes={})
            self.assertEqual(manifest_bytes(first), manifest_bytes(second))

            content_file = root / "Content/RedMMO/Maps/Main.umap"
            content_file.write_bytes(b"changed")
            third = build_storage_manifest(root, protected_hashes={})
            self.assertNotEqual(
                first["scope"]["signature_sha256"],
                third["scope"]["signature_sha256"],
            )
            self.assertNotEqual(
                first["scope"]["project_content_signature_sha256"],
                third["scope"]["project_content_signature_sha256"],
            )

    def test_missing_invalid_or_ambiguous_required_inputs_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture(root)
            (root / "Content").rename(root / "MissingContent")
            with self.assertRaises(StorageManifestError):
                build_storage_manifest(root, protected_hashes={})

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture(root)
            (root / "Plugins/RedHUD/RedHUD.uplugin").write_text(
                "{broken",
                encoding="utf-8",
            )
            with self.assertRaises(StorageManifestError):
                build_storage_manifest(root, protected_hashes={})

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture(root)
            self._write(
                root,
                "Plugins/RedHUD/Ambiguous.uplugin",
                b'{"FileVersion": 3}',
            )
            with self.assertRaises(StorageManifestError):
                build_storage_manifest(root, protected_hashes={})

    def test_content_and_nested_plugin_reparse_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture(root)
            with patch(
                "Tools.build_redmmo_content_storage_manifest._is_link_or_reparse",
                side_effect=lambda path, metadata=None: path == root.absolute(),
            ), self.assertRaises(StorageManifestError):
                build_storage_manifest(root, protected_hashes={})

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture(root)
            with patch(
                "Tools.build_redmmo_content_storage_manifest._is_link_or_reparse",
                side_effect=lambda path, metadata=None: path.name == "Content",
            ), self.assertRaises(StorageManifestError):
                build_storage_manifest(root, protected_hashes={})

    def test_hard_link_alias_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture(root)
            source = root / "Content/RedMMO/Maps/Main.umap"
            alias = root / "Content/RedMMO/Maps/MainAlias.umap"
            try:
                alias.hardlink_to(source)
            except OSError as error:
                self.skipTest(f"hard links unavailable in fixture filesystem: {error}")
            with self.assertRaises(StorageManifestError):
                build_storage_manifest(root, protected_hashes={})

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture(root)
            with patch(
                "Tools.build_redmmo_content_storage_manifest._is_link_or_reparse",
                side_effect=lambda path, metadata=None: path.name == "Binaries",
            ), self.assertRaises(StorageManifestError):
                build_storage_manifest(root, protected_hashes={})

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture(root)
            with patch(
                "Tools.build_redmmo_content_storage_manifest._is_link_or_reparse",
                side_effect=lambda path, metadata=None: path.name == "RedHUD",
            ), self.assertRaises(StorageManifestError):
                build_storage_manifest(root, protected_hashes={})

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture(root)
            with patch(
                "Tools.build_redmmo_content_storage_manifest._is_link_or_reparse",
                side_effect=lambda path, metadata=None: path.name == "Resources",
            ), self.assertRaises(StorageManifestError):
                build_storage_manifest(root, protected_hashes={})

    def test_concurrent_file_mutation_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture(root)
            target = root / "Content/RedMMO/Maps/Main.umap"
            original = sha256_file
            mutated = False

            def mutate_after_hash(path: Path) -> str:
                nonlocal mutated
                digest = original(path)
                if path == target and not mutated:
                    mutated = True
                    path.write_bytes(b"mutated-after-hash")
                return digest

            with patch(
                "Tools.build_redmmo_content_storage_manifest.sha256_file",
                side_effect=mutate_after_hash,
            ), self.assertRaises(StorageManifestError):
                build_storage_manifest(root, protected_hashes={})

    def test_protected_input_missing_or_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture(root)
            relative = "Content/RedMMO/Maps/Main.umap"
            expected = hashlib.sha256(b"map").hexdigest().upper()
            manifest = build_storage_manifest(
                root,
                protected_hashes={relative: expected},
            )
            self.assertEqual(manifest["protected_inputs"][0]["matches"], True)

            with self.assertRaises(StorageManifestError):
                build_storage_manifest(
                    root,
                    protected_hashes={relative: "0" * 64},
                )
            with self.assertRaises(StorageManifestError):
                build_storage_manifest(
                    root,
                    protected_hashes={"Content/Missing.uasset": expected},
                )

    def test_case_insensitive_collisions_are_rejected(self) -> None:
        metadata = FileMetadata(1, 1, 1, 1, 1, 0, 0, 1)
        first = InventoryFile(
            Path("A"),
            "Content/Folder/File.uasset",
            "project_content",
            None,
            metadata,
        )
        second = InventoryFile(
            Path("B"),
            "content/folder/file.uasset",
            "project_content",
            None,
            metadata,
        )
        with self.assertRaises(StorageManifestError):
            _ensure_casefold_unique([first, second])

    def test_output_is_external_atomic_and_no_clobber(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnostics = root / "Diagnostics"
            diagnostics.mkdir()
            output = diagnostics / "M07" / "storage_manifest.json"
            resolved = validate_output_path(
                output,
                diagnostics_root=diagnostics,
            )
            write_manifest_atomic(resolved, b"{}\n")
            self.assertEqual(resolved.read_bytes(), b"{}\n")
            with self.assertRaises(StorageManifestError):
                write_manifest_atomic(resolved, b'{"replace":true}\n')
            with self.assertRaises(StorageManifestError):
                validate_output_path(
                    root / "outside.json",
                    diagnostics_root=diagnostics,
                )
            with self.assertRaises(StorageManifestError):
                validate_output_path(
                    diagnostics / "report.txt",
                    diagnostics_root=diagnostics,
                )
            linked_ancestor = diagnostics / "Linked"
            linked_ancestor.mkdir()
            with patch(
                "Tools.build_redmmo_content_storage_manifest._is_link_or_reparse",
                side_effect=lambda path, metadata=None: path == linked_ancestor,
            ), self.assertRaises(StorageManifestError):
                validate_output_path(
                    linked_ancestor / "report.json",
                    diagnostics_root=diagnostics,
                )

    def test_script_can_be_invoked_directly_from_project_root(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "Tools/build_redmmo_content_storage_manifest.py"),
                "--help",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("--project-root", result.stdout)


if __name__ == "__main__":
    unittest.main()
