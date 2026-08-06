from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path

from Tools.export_redmmo_asset_registry_catalog import (
    CatalogExportError,
    PRIORITY_LIBRARY_ROOTS,
    build_report,
    canonical_top_level_asset_path,
    collect_unreal_registry_records,
    infer_candidate_roles,
    normalize_record,
    report_bytes,
    validate_output_path,
    validate_unreal_identity,
    write_report_atomic,
)


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "Tools/export_redmmo_asset_registry_catalog.py"


class _FakeTopLevelAssetPath:
    package_name = "/Script/Engine"
    asset_name = "StaticMesh"

    def __str__(self) -> str:
        return "<Struct 'TopLevelAssetPath' at 0x00000000DEADBEEF>"


class _FakeAssetData:
    def __init__(self, root: str, index: int) -> None:
        self.package_name = f"{root}/Meshes/SM_Candidate_{index}"
        self.package_path = f"{root}/Meshes"
        self.asset_name = f"SM_Candidate_{index}"
        self.asset_class_path = _FakeTopLevelAssetPath()

    def get_tag_value(self, tag_name: str):
        if str(tag_name) == "NumLODs":
            return "3"
        if str(tag_name) == "Dimensions":
            return True, "100x100x100"
        return None


class _FakeRegistry:
    def __init__(self) -> None:
        self.waited = False
        self.queries: list[tuple[str, bool, bool]] = []

    def wait_for_completion(self) -> None:
        self.waited = True

    def get_assets_by_path(self, root: str, recursive: bool, on_disk: bool):
        self.queries.append((str(root), recursive, on_disk))
        return [_FakeAssetData(str(root), len(self.queries))]


class _FakeAssetRegistryHelpers:
    registry = _FakeRegistry()

    @classmethod
    def get_asset_registry(cls):
        return cls.registry


class _FakeUnreal:
    AssetRegistryHelpers = _FakeAssetRegistryHelpers

    @staticmethod
    def Name(value: str) -> str:
        return value


class RedMMOAssetRegistryCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeAssetRegistryHelpers.registry = _FakeRegistry()

    def _records_for_all_roots(self):
        return [
            normalize_record(
                package_name=f"{root}/Meshes/SM_Rock_A",
                package_path=f"{root}/Meshes",
                asset_name="SM_Rock_A",
                asset_class_path="/Script/Engine.StaticMesh",
                registry_tags={"NumLODs": "4"},
            )
            for root in PRIORITY_LIBRARY_ROOTS
        ]

    def test_priority_roots_are_exact_and_vendor_scoped(self) -> None:
        self.assertEqual(
            PRIORITY_LIBRARY_ROOTS,
            (
                "/Game/SoStylized",
                "/Game/StylizedDesertOasis",
                "/Game/AlienJungle",
                "/Game/TropicalAlienWorld",
                "/Game/Alien_Grass_Pack",
                "/Game/Alien_Plants_Pack",
            ),
        )
        self.assertIn(
            "Geology",
            infer_candidate_roles(
                "/Game/SoStylized/Rocks/SM_Rock_A",
                "/Script/Engine.StaticMesh",
            ),
        )

    def test_report_is_deterministic_and_explicitly_candidate_only(self) -> None:
        records = list(reversed(self._records_for_all_roots()))
        first = build_report(
            records,
            engine_version="5.8.0",
            project_file=r"D:\RedMMOTitan\Titan.uproject",
        )
        second = build_report(
            list(reversed(records)),
            engine_version="5.8.0",
            project_file=r"D:\RedMMOTitan\Titan.uproject",
        )
        self.assertEqual(report_bytes(first), report_bytes(second))
        self.assertEqual(first["status"], "candidate_only")
        self.assertFalse(first["method"]["loads_asset_uobjects"])
        self.assertFalse(first["method"]["mutates_unreal_packages"])
        self.assertEqual(first["scope"]["candidate_count"], 6)
        self.assertEqual(first["scope"]["duplicate_basename_group_count"], 1)
        for candidate in first["candidates"]:
            self.assertEqual(candidate["source_policy"], "vendor_source_immutable")
            self.assertTrue(candidate["requires_license_review"])

        with self.assertRaises(CatalogExportError):
            build_report(
                records[:-1],
                engine_version="5.8.0",
                project_file="Titan.uproject",
            )

    def test_fake_unreal_contract_waits_and_queries_only_on_disk_recursively(self) -> None:
        records = collect_unreal_registry_records(_FakeUnreal)
        registry = _FakeAssetRegistryHelpers.registry
        self.assertTrue(registry.waited)
        self.assertEqual(
            registry.queries,
            [(root, True, True) for root in PRIORITY_LIBRARY_ROOTS],
        )
        self.assertEqual(len(records), len(PRIORITY_LIBRARY_ROOTS))
        self.assertTrue(
            all(
                record["registry_tags"]
                == {"Dimensions": "100x100x100", "NumLODs": "3"}
                for record in records
            )
        )
        self.assertTrue(
            all(
                record["asset_class_path"] == "/Script/Engine.StaticMesh"
                for record in records
            )
        )

    def test_top_level_asset_path_and_runtime_identity_fail_closed(self) -> None:
        class_path = canonical_top_level_asset_path(_FakeTopLevelAssetPath())
        self.assertEqual(class_path, "/Script/Engine.StaticMesh")
        self.assertNotIn("DEADBEEF", class_path)
        with self.assertRaises(CatalogExportError):
            canonical_top_level_asset_path("<unstable debug wrapper>")

        expected_project = ROOT / "Titan.uproject"
        validate_unreal_identity("5.8.0", str(expected_project))
        with self.assertRaises(CatalogExportError):
            validate_unreal_identity("5.7.6", str(expected_project))
        with self.assertRaises(CatalogExportError):
            validate_unreal_identity("5.8.0", str(ROOT / "Other.uproject"))

    def test_output_is_atomic_and_restricted_to_external_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnostics = root / "Diagnostics"
            output = diagnostics / "M07" / "catalog.json"
            resolved = validate_output_path(output, diagnostics_root=diagnostics)
            write_report_atomic(resolved, b"{}\n")
            self.assertEqual(resolved.read_bytes(), b"{}\n")
            with self.assertRaises(CatalogExportError):
                write_report_atomic(resolved, b"{\"overwrite\": true}\n")
            self.assertEqual(resolved.read_bytes(), b"{}\n")
            with self.assertRaises(CatalogExportError):
                validate_output_path(root / "project" / "catalog.json", diagnostics_root=diagnostics)
            with self.assertRaises(CatalogExportError):
                validate_output_path(diagnostics / "catalog.yaml", diagnostics_root=diagnostics)

    def test_live_script_has_no_asset_load_or_mutation_call(self) -> None:
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        forbidden = {
            "load_asset",
            "get_asset",
            "save_asset",
            "save_loaded_asset",
            "delete_asset",
            "rename_asset",
            "duplicate_asset",
            "import_asset",
            "checkout_asset",
        }
        calls = []
        top_level_unreal_imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    calls.append(node.func.attr)
                elif isinstance(node.func, ast.Name):
                    calls.append(node.func.id)
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in node.names]
                if "unreal" in names and node.col_offset == 0:
                    top_level_unreal_imports.append(node)
        self.assertFalse(forbidden.intersection(calls))
        self.assertFalse(top_level_unreal_imports)
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("AssetRegistryHelpers.get_asset_registry()", source)
        self.assertIn("registry.wait_for_completion()", source)
        self.assertIn("registry.get_assets_by_path(", source)


if __name__ == "__main__":
    unittest.main()
