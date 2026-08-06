from __future__ import annotations

import ast
import importlib.util
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace
from unittest import mock
import sys
import tempfile
import unittest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "import_redmmo_stylized_source_library.py"
)
SPEC = importlib.util.spec_from_file_location("stylized_import", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeClass:
    def get_name(self) -> str:
        return "Texture2D"


class FakeImportData:
    def __init__(self, source_path: Path) -> None:
        self.source_path = source_path

    def get_first_filename(self) -> str:
        return str(self.source_path)


class FakeAsset:
    def __init__(self, source_path: Path) -> None:
        self.metadata: dict[str, str] = {}
        self.properties = {
            "lod_group": "world",
            "srgb": True,
            "compression_settings": "default",
            "asset_import_data": FakeImportData(source_path),
        }

    def get_class(self) -> FakeClass:
        return FakeClass()

    def get_editor_property(self, name: str) -> object:
        return self.properties[name]

    def set_editor_property(self, name: str, value: object) -> None:
        self.properties[name] = value


class FakeEditorAssetLibrary:
    @staticmethod
    def get_metadata_tag(asset: FakeAsset, tag_name: str) -> str:
        return asset.metadata.get(tag_name, "")

    @staticmethod
    def set_metadata_tag(
        asset: FakeAsset, tag_name: str, value: str
    ) -> None:
        asset.metadata[tag_name] = value


FAKE_UNREAL = SimpleNamespace(
    TextureGroup=SimpleNamespace(TEXTUREGROUP_WORLD="world"),
    TextureCompressionSettings=SimpleNamespace(
        TC_DEFAULT="default",
        TC_NORMALMAP="normal",
        TC_MASKS="masks",
    ),
    EditorAssetLibrary=FakeEditorAssetLibrary,
)


class StylizedSourceImportTests(unittest.TestCase):
    def make_source(self, root: Path) -> None:
        sources = {
            "Stylized_Grass/Grass.Wavy/Grass.Wavy_Color.png": b"color",
            "Stylized_Grass/Grass.Wavy/Grass.Wavy_Normal.png": b"normal",
            "Stylized_Water/Falls/Falls_Opacity.png": b"mask",
            "Stylized_Maps/World.4040/World.4040_Color.dds": b"map",
            "__MACOSX/Stylized_Grass/._ignored.png": b"ignored",
            "Stylized_Grass/Grass.Wavy/notes.txt": b"ignored",
        }
        for relative, payload in sources.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)

    def build_test_plan(self, source: Path) -> dict[str, object]:
        return MODULE.build_import_plan(
            source,
            enforce_default_identity=False,
        )

    def validate_test_plan(
        self,
        plan: dict[str, object],
        source: Path,
        **kwargs: object,
    ) -> list[object]:
        return MODULE.validate_import_plan(
            plan,
            expected_source_root=source,
            **kwargs,
        )

    def test_segment_sanitation_is_unreal_safe_and_deterministic(self) -> None:
        self.assertEqual(MODULE.sanitize_segment("World.4040"), "World_4040")
        self.assertEqual(MODULE.sanitize_segment(" 12 rocks! "), "N_12_rocks")
        long_name = "x" * 100
        self.assertEqual(
            MODULE.sanitize_segment(long_name),
            MODULE.sanitize_segment(long_name),
        )
        self.assertLessEqual(
            len(MODULE.sanitize_segment(long_name)),
            MODULE.MAX_SEGMENT_LENGTH,
        )

    def test_semantic_classification_uses_terminal_suffix_precedence(self) -> None:
        cases = {
            "Tree_Normal.png": "normal",
            "Tree_DXTNormal.dds": "normal",
            "Tree_ORM.dds": "mask",
            "Tree_Opacity.png": "mask",
            "Tree_Color.png": "color",
            "Tree_NormalUncompressed_Color.png": "color",
            "Tree_dxtnormal_Color.dds": "color",
        }
        for filename, expected in cases.items():
            with self.subTest(filename=filename):
                self.assertEqual(
                    MODULE.classify_texture_semantic(filename), expected
                )

    def test_plan_records_hashes_approval_and_deterministic_fingerprints(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            self.make_source(source)
            first = self.build_test_plan(source)
            second = self.build_test_plan(source)
            self.assertEqual(first["record_count"], 4)
            self.assertEqual(first["dataset_sha256"], second["dataset_sha256"])
            self.assertEqual(first["plan_sha256"], second["plan_sha256"])
            self.assertEqual(
                first["source_provenance"], MODULE.SOURCE_PROVENANCE
            )
            self.assertEqual(
                first["license_approval"]["status"],
                MODULE.LICENSE_APPROVAL_STATUS,
            )
            self.assertTrue(first["license_approval"]["approved"])
            self.assertTrue(
                all(
                    len(record["source_sha256"]) == 64
                    and record["stable_source_id"].startswith("RED-STYLIZED-")
                    for record in first["records"]
                )
            )
            self.assertEqual(len(self.validate_test_plan(first, source)), 4)

    def test_plan_excludes_metadata_and_non_texture_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            self.make_source(source)
            plan = self.build_test_plan(source)
            relative_paths = {
                record["relative_path"] for record in plan["records"]
            }
            self.assertNotIn(
                "__MACOSX/Stylized_Grass/._ignored.png", relative_paths
            )
            self.assertTrue(
                all(
                    record["object_path"].startswith(
                        MODULE.DEFAULT_DESTINATION_ROOT + "/"
                    )
                    for record in plan["records"]
                )
            )

    def test_ordinary_mapping_remains_compatible_with_existing_probe_names(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            texture = (
                source
                / "Stylized_Grass"
                / "Clutter_Corrupted_Grass_000"
                / "Clutter_Corrupted_Grass_000_Color.png"
            )
            texture.parent.mkdir(parents=True)
            texture.write_bytes(b"probe")
            plan = self.build_test_plan(source)
            record = plan["records"][0]
            self.assertEqual(
                record["object_path"],
                "/Game/RedMMO/ArtLibrary/StylizedSource/"
                "Stylized_Grass/Clutter_Corrupted_Grass_000/"
                "Clutter_Corrupted_Grass_000_Color",
            )

    def test_png_dds_name_collision_gets_stable_hash_suffixes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            first = source / "Stylized_Rock" / "Rock" / "Rock_Color.png"
            second = source / "Stylized_Rock" / "Rock" / "Rock_Color.dds"
            first.parent.mkdir(parents=True)
            first.write_bytes(b"png")
            second.write_bytes(b"dds")
            plan = self.build_test_plan(source)
            names = [record["destination_name"] for record in plan["records"]]
            self.assertEqual(len(names), 2)
            self.assertEqual(len(set(names)), 2)
            self.assertTrue(all(name.startswith("Rock_Color_") for name in names))
            self.validate_test_plan(plan, source)

    def test_plan_validation_detects_size_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            self.make_source(source)
            plan = self.build_test_plan(source)
            target = source / plan["records"][0]["relative_path"]
            target.write_bytes(target.read_bytes() + b"changed")
            with self.assertRaisesRegex(RuntimeError, "Source size changed"):
                self.validate_test_plan(plan, source)

    def test_sha_detects_equal_size_equal_mtime_source_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            self.make_source(source)
            plan = self.build_test_plan(source)
            target = source / plan["records"][0]["relative_path"]
            metadata = target.stat()
            payload = target.read_bytes()
            target.write_bytes(bytes([payload[0] ^ 0x01]) + payload[1:])
            os.utime(
                target,
                ns=(metadata.st_atime_ns, metadata.st_mtime_ns),
            )
            with self.assertRaisesRegex(RuntimeError, "Source SHA256 changed"):
                self.validate_test_plan(plan, source)

    def test_plan_digest_detects_record_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            self.make_source(source)
            plan = self.build_test_plan(source)
            plan["records"][0]["source_mtime_ns"] += 1
            with self.assertRaisesRegex(RuntimeError, "plan digest mismatch"):
                self.validate_test_plan(
                    plan,
                    source,
                    verify_source_metadata=False,
                    verify_source_hashes=False,
                )

    def test_default_identity_is_mandatory_for_production_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            self.make_source(source)
            with self.assertRaisesRegex(RuntimeError, "must be exactly"):
                MODULE.build_import_plan(source)
            with self.assertRaisesRegex(RuntimeError, "must be exactly"):
                MODULE.build_import_plan(
                    source,
                    "/Game/RedMMO/Elsewhere",
                    enforce_default_identity=True,
                )
            plan = self.build_test_plan(source)
            with self.assertRaisesRegex(RuntimeError, "source root identity"):
                MODULE.validate_import_plan(plan)

    def test_path_traversal_is_rejected_even_with_recomputed_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            self.make_source(source)
            plan = self.build_test_plan(source)
            plan["records"][0]["relative_path"] = "../escape.png"
            plan["records"][0]["stable_source_id"] = MODULE._stable_source_id(
                "../escape.png"
            )
            with self.assertRaisesRegex(RuntimeError, "Unsafe planned"):
                self.validate_test_plan(
                    plan,
                    source,
                    verify_source_metadata=False,
                    verify_source_hashes=False,
                )

    def test_source_symlink_is_rejected_when_platform_can_create_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            real = source / "real.png"
            real.write_bytes(b"real")
            link = source / "Stylized_Grass" / "Grass" / "Grass_Color.png"
            link.parent.mkdir(parents=True)
            try:
                link.symlink_to(real)
            except OSError as exc:
                self.skipTest(f"Symlink creation unavailable: {exc}")
            with self.assertRaisesRegex(RuntimeError, "link or reparse"):
                list(MODULE.iter_source_files(source))

    def test_link_and_windows_reparse_metadata_fail_closed(self) -> None:
        cases = (
            SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0),
            SimpleNamespace(
                st_mode=stat.S_IFREG,
                st_file_attributes=getattr(
                    stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
                ),
            ),
        )
        for metadata in cases:
            with self.subTest(metadata=metadata):
                with mock.patch.object(
                    MODULE, "_lstat", return_value=metadata
                ):
                    with self.assertRaisesRegex(
                        RuntimeError, "link or reparse"
                    ):
                        MODULE._reject_link_or_reparse(
                            Path("fixture"), "Fixture"
                        )

    def test_walk_error_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)

            def broken_walk(*args: object, **kwargs: object) -> list[object]:
                kwargs["onerror"](PermissionError("denied"))
                return []

            with mock.patch.object(MODULE.os, "walk", side_effect=broken_walk):
                with self.assertRaisesRegex(RuntimeError, "Cannot walk"):
                    list(MODULE.iter_source_files(source))

    def test_no_clobber_json_writer_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "reports" / "plan.json"
            payload = {"schema": "test", "value": 1}
            MODULE.write_json_no_clobber(output, payload)
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8")), payload
            )
            with self.assertRaisesRegex(RuntimeError, "overwrite"):
                MODULE.write_json_no_clobber(output, payload)
            self.assertEqual(list(output.parent.glob("*.tmp")), [])

    def test_existing_asset_requires_exact_metadata_settings_and_source(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            self.make_source(source)
            plan = self.build_test_plan(source)
            record = MODULE.ImportRecord(**plan["records"][0])
            source_path = source / record.relative_path
            asset = FakeAsset(source_path)
            with self.assertRaisesRegex(RuntimeError, "metadata is unverified"):
                MODULE._verify_texture_asset(
                    FAKE_UNREAL,
                    asset,
                    record,
                    source_path=source_path,
                    plan_sha256=plan["plan_sha256"],
                    import_representation=MODULE.DIRECT_PNG_REPRESENTATION,
                    import_payload_sha256=record.source_sha256,
                )

            MODULE._set_asset_metadata(
                FAKE_UNREAL,
                asset,
                MODULE._expected_metadata(
                    record,
                    source_path=source_path,
                    plan_sha256=plan["plan_sha256"],
                    import_representation=MODULE.DIRECT_PNG_REPRESENTATION,
                    import_payload_sha256=record.source_sha256,
                ),
            )
            MODULE._set_texture_properties(
                FAKE_UNREAL, asset, record.semantic
            )
            MODULE._verify_texture_asset(
                FAKE_UNREAL,
                asset,
                record,
                source_path=source_path,
                plan_sha256=plan["plan_sha256"],
                import_representation=MODULE.DIRECT_PNG_REPRESENTATION,
                import_payload_sha256=record.source_sha256,
            )

    def test_stages_dds_to_authenticated_png_without_touching_source(
        self,
    ) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is unavailable")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            diagnostics = root / "diagnostics"
            diagnostics.mkdir()
            category = source / "Stylized_Crystal"
            category.mkdir(parents=True)
            dds_path = category / "Crystal_Color.dds"
            png_path = category / "Crystal_Normal.png"
            Image.new("RGBA", (4, 4), (40, 90, 140, 255)).save(
                dds_path,
                format="DDS",
                pixel_format="DXT1",
            )
            Image.new("RGB", (4, 4), (127, 127, 255)).save(
                png_path,
                format="PNG",
            )
            original_dds = dds_path.read_bytes()

            with (
                mock.patch.object(MODULE, "DEFAULT_SOURCE_ROOT", source),
                mock.patch.object(
                    MODULE, "DEFAULT_DIAGNOSTICS_ROOT", diagnostics
                ),
            ):
                plan = MODULE.build_import_plan(source)
                plan_path = diagnostics / "plan.json"
                MODULE.write_json_no_clobber(plan_path, plan)
                output = diagnostics / "batch"
                output.mkdir()
                manifest = MODULE.stage_import_batch(
                    plan_path,
                    ("Stylized_Crystal",),
                    0,
                    2,
                    output,
                )
                self.assertEqual(manifest["result_count"], 2)
                self.assertEqual(manifest["staged_dds_count"], 1)
                self.assertEqual(dds_path.read_bytes(), original_dds)

                staged_entries = {
                    entry["source_suffix"]: entry
                    for entry in manifest["records"]
                }
                dds_entry = staged_entries[".dds"]
                staged_png = Path(dds_entry["import_path"])
                self.assertTrue(staged_png.is_file())
                self.assertEqual(staged_png.suffix, ".png")
                self.assertEqual(
                    MODULE.sha256_file(staged_png),
                    dds_entry["import_payload_sha256"],
                )
                self.assertEqual(
                    staged_entries[".png"]["representation"],
                    MODULE.DIRECT_PNG_REPRESENTATION,
                )

                records = MODULE.validate_import_plan(
                    plan,
                    expected_source_root=source,
                    verify_source_hashes=False,
                )
                _, selected = MODULE.select_import_records(
                    records,
                    ("Stylized_Crystal",),
                    0,
                    2,
                )
                selected_sources = {
                    record.index: source / record.relative_path
                    for record in selected
                }
                manifest_path = output / MODULE.STAGE_MANIFEST_FILENAME
                _, imports = MODULE._load_stage_manifest(
                    manifest_path,
                    expected_manifest_file_sha256=MODULE.sha256_file(
                        manifest_path
                    ),
                    plan_path=plan_path.resolve(),
                    plan_file_sha256=MODULE.sha256_file(plan_path),
                    plan=plan,
                    categories=("Stylized_Crystal",),
                    start=0,
                    limit=2,
                    selected=selected,
                    selected_sources=selected_sources,
                )
                self.assertEqual(len(imports), 2)

                staged_png.write_bytes(b"tampered")
                with self.assertRaisesRegex(
                    RuntimeError, "payload SHA256 mismatch"
                ):
                    MODULE._load_stage_manifest(
                        manifest_path,
                        expected_manifest_file_sha256=MODULE.sha256_file(
                            manifest_path
                        ),
                        plan_path=plan_path.resolve(),
                        plan_file_sha256=MODULE.sha256_file(plan_path),
                        plan=plan,
                        categories=("Stylized_Crystal",),
                        start=0,
                        limit=2,
                        selected=selected,
                        selected_sources=selected_sources,
                    )

    def test_source_code_has_no_source_delete_or_overwrite_api(self) -> None:
        source_text = SCRIPT_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source_text)
        attributes = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
        }
        self.assertNotIn("unlink", attributes)
        self.assertNotIn("rmtree", source_text)
        self.assertNotIn("shutil", source_text)
        self.assertNotIn("os.replace", source_text)
        self.assertNotIn('"replace_existing", True', source_text)


if __name__ == "__main__":
    unittest.main()
