from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Tools.audit_redmmo_asset_library import (
    AuditError,
    build_report,
    infer_asset_type,
    infer_candidate_categories,
    report_bytes,
    validate_output_path,
    write_report_atomic,
)


class RedMMOAssetLibraryAuditTests(unittest.TestCase):
    def _package(self, root: Path, relative: str, payload: bytes = b"fixture") -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def test_prefix_and_candidate_classification_are_explicitly_provisional(self) -> None:
        self.assertEqual(infer_asset_type("SM_Rock_A", ".uasset"), ("StaticMesh", "SM_"))
        self.assertEqual(infer_asset_type("MI_Grass_A", ".uasset"), ("MaterialInstance", "MI_"))
        self.assertEqual(infer_asset_type("UnknownThing", ".uasset"), ("Unknown", ""))
        self.assertEqual(infer_asset_type("World_A", ".umap"), ("Map", ""))

        categories = infer_candidate_categories(
            Path("Alien/Cliff/Grass/SM_RockGrass_A.uasset"),
            "StaticMesh",
        )
        self.assertIn("Geology", categories)
        self.assertIn("Vegetation.Grass", categories)

    def test_report_separates_owned_vendor_external_and_plugin_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            content = root / "Content"
            plugins = root / "Plugins"
            self._package(content, "RedMMO/ArtLibrary/SM_RedRock.uasset")
            self._package(content, "SoStylized/Rocks/SM_RedRock.uasset")
            self._package(content, "Alien_Grass_Pack/Grass/SM_Blade_A.uasset")
            self._package(content, "__ExternalActors__/Maps/Actor_A.uasset")
            self._package(content, "Maps/TestMap.umap")
            self._package(
                plugins,
                "VibeMMOUIKit/Content/UI/T_VibeFrame.uasset",
            )

            before = {
                path.relative_to(root).as_posix(): (path.stat().st_size, path.stat().st_mtime_ns)
                for path in root.rglob("*")
                if path.is_file()
            }
            report = build_report(content, plugins)
            after = {
                path.relative_to(root).as_posix(): (path.stat().st_size, path.stat().st_mtime_ns)
                for path in root.rglob("*")
                if path.is_file()
            }

            self.assertEqual(before, after)
            self.assertEqual(report["scope"]["package_count"], 6)
            self.assertEqual(report["scope"]["asset_count"], 5)
            self.assertEqual(report["scope"]["map_count"], 1)
            self.assertEqual(report["scope"]["basename_collision_group_count"], 1)
            self.assertTrue(report["scope"]["tree_quiescent_during_scan"])

            kinds = {
                record["package_path"]: record["source_kind"]
                for record in report["packages"]
            }
            self.assertEqual(kinds["/Game/RedMMO/ArtLibrary/SM_RedRock"], "project_owned")
            self.assertEqual(kinds["/Game/SoStylized/Rocks/SM_RedRock"], "vendor_or_sample")
            self.assertEqual(
                kinds["/Game/__ExternalActors__/Maps/Actor_A"],
                "world_partition_external",
            )
            self.assertEqual(
                kinds["/VibeMMOUIKit/UI/T_VibeFrame"],
                "plugin_content",
            )

            pack_summary = {
                item["library_root"]: item
                for item in report["selected_art_pack_summary"]
            }
            self.assertTrue(pack_summary["SoStylized"]["present"])
            self.assertTrue(pack_summary["Alien_Grass_Pack"]["present"])
            self.assertFalse(pack_summary["Alien_Plants_Pack"]["present"])

            collision = report["basename_collisions"][0]
            self.assertEqual(collision["normalized_asset_name"], "sm_redrock")
            self.assertEqual(collision["package_count"], 2)

    def test_report_bytes_are_deterministic_for_a_quiescent_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            content = root / "Content"
            plugins = root / "Plugins"
            self._package(content, "RedMMO/World/SM_Tree_A.uasset", b"123")

            first = report_bytes(build_report(content, plugins))
            second = report_bytes(build_report(content, plugins))
            self.assertEqual(first, second)

    def test_output_is_restricted_to_the_explicit_diagnostics_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnostics = root / "Diagnostics"
            allowed = diagnostics / "AssetAudit" / "report.json"
            resolved = validate_output_path(allowed, diagnostics_root=diagnostics)
            write_report_atomic(resolved, b"{}\n")
            self.assertEqual(resolved.read_bytes(), b"{}\n")

            with self.assertRaises(AuditError):
                validate_output_path(root / "outside.json", diagnostics_root=diagnostics)
            with self.assertRaises(AuditError):
                validate_output_path(diagnostics / "report.txt", diagnostics_root=diagnostics)


if __name__ == "__main__":
    unittest.main()
