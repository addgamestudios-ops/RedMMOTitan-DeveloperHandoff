"""Focused tests for fused macro-face authentication and post-verification.

The module under test imports Unreal only inside ``main()``, so this suite runs
with ordinary CPython and never starts an Unreal process.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = REPOSITORY_ROOT / "Tools"
TEST_TEMP_ROOT = REPOSITORY_ROOT / "Saved" / "ToolTests"

if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

import import_fused_macro_heightfield as importer


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


class FusedMacroAuthenticationTests(unittest.TestCase):
    def setUp(self) -> None:
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        self._temp = tempfile.TemporaryDirectory(
            prefix="fused_import_test_", dir=TEST_TEMP_ROOT
        )
        self.addCleanup(self._temp.cleanup)
        self.source_dir = Path(self._temp.name)
        self.patch_dataset = "A" * 64

        faces: list[dict[str, object]] = []
        raster_hashes: list[tuple[str, str]] = []
        for face_index, face_name in enumerate(importer.FACE_NAMES):
            face: dict[str, object] = {
                "face_index": face_index,
                "name": face_name,
            }
            files: dict[str, dict[str, str]] = {}
            for role, top_key, filename_template, encoding in importer.FACE_FILE_CONTRACTS:
                filename = filename_template.format(face=face_name)
                payload = (f"{face_index}:{face_name}:{role}\n".encode("ascii")) * (
                    face_index + 1
                )
                (self.source_dir / filename).write_bytes(payload)
                file_hash = _sha256_bytes(payload)
                face[top_key] = filename
                files[role] = {
                    "file": filename,
                    "encoding": encoding,
                    "sha256": file_hash,
                }
                raster_hashes.append((filename, file_hash))
            face["files"] = files
            faces.append(face)

        self.dataset = importer.dataset_sha256(raster_hashes)
        self.manifest: dict[str, object] = {
            "schema": importer.EXPECTED_SCHEMA,
            "resolution": importer.EXPECTED_RESOLUTION,
            "height_encoding": importer.EXPECTED_HEIGHT_ENCODING,
            "raw_height_encoding": importer.EXPECTED_RAW_HEIGHT_ENCODING,
            "min_height_cm": importer.EXPECTED_MIN_HEIGHT_CM,
            "max_height_cm": importer.EXPECTED_MAX_HEIGHT_CM,
            "biome_channels": dict(importer.EXPECTED_BIOME_CHANNELS),
            "source_patch_raster_dataset_sha256": self.patch_dataset,
            "coverage_validation": {"passed": True},
            "seam_validation": {"passed": True},
            "raster_dataset_sha256": self.dataset,
            "faces": faces,
        }

    def authenticate(self, manifest: dict[str, object] | None = None) -> str:
        return importer.authenticate_face_dataset(
            self.source_dir,
            self.manifest if manifest is None else manifest,
            expected_face_dataset=self.dataset,
            expected_patch_dataset=self.patch_dataset,
        )

    def test_authenticates_all_24_files_and_canonical_dataset_digest(self) -> None:
        with mock.patch.object(
            importer, "sha256_file", wraps=importer.sha256_file
        ) as hash_file:
            self.assertEqual(self.authenticate(), self.dataset)
        self.assertEqual(hash_file.call_count, 24)

        records = [("z.bin", "1" * 64), ("a.bin", "2" * 64)]
        expected = hashlib.sha256()
        for filename, file_hash in sorted(records):
            expected.update(filename.encode("utf-8"))
            expected.update(b"\0")
            expected.update(file_hash.encode("ascii"))
            expected.update(b"\n")
        self.assertEqual(importer.dataset_sha256(records), expected.hexdigest().upper())

    def test_requires_canonical_land_and_biome_names(self) -> None:
        for top_key, replacement in (
            ("land_file", "RED_Land_WRONG.png"),
            ("biome_file", "RED_Biomes_WRONG.png"),
        ):
            with self.subTest(top_key=top_key):
                candidate = copy.deepcopy(self.manifest)
                candidate["faces"][0][top_key] = replacement  # type: ignore[index]
                with self.assertRaisesRegex(RuntimeError, f"noncanonical {top_key}"):
                    self.authenticate(candidate)

    def test_requires_exact_nested_role_filename_encoding_and_sha256(self) -> None:
        candidate = copy.deepcopy(self.manifest)
        candidate["faces"][0]["files"]["land"]["encoding"] = "PNG RGBA8"  # type: ignore[index]
        with self.assertRaisesRegex(RuntimeError, "land has a noncanonical encoding"):
            self.authenticate(candidate)

        candidate = copy.deepcopy(self.manifest)
        candidate["faces"][0]["files"]["biomes"]["file"] = "RED_Biomes_NX.png"  # type: ignore[index]
        with self.assertRaisesRegex(RuntimeError, "noncanonical nested biomes filename"):
            self.authenticate(candidate)

        candidate = copy.deepcopy(self.manifest)
        declared_hash = candidate["faces"][0]["files"]["height"]["sha256"]  # type: ignore[index]
        candidate["faces"][0]["files"]["height"]["sha256"] = declared_hash.lower()  # type: ignore[index, union-attr]
        with self.assertRaisesRegex(RuntimeError, "uppercase 64-character SHA256"):
            self.authenticate(candidate)

        candidate = copy.deepcopy(self.manifest)
        candidate["faces"][0]["files"]["preview"] = {  # type: ignore[index]
            "file": "preview.png",
            "encoding": "PNG RGB8",
            "sha256": "B" * 64,
        }
        with self.assertRaisesRegex(RuntimeError, "must contain exactly"):
            self.authenticate(candidate)

    def test_requires_exact_rgba_biome_channel_map(self) -> None:
        candidate = copy.deepcopy(self.manifest)
        candidate["biome_channels"] = {
            "r": "desert",
            "g": "temperate",
            "b": "alien",
            "a": "cold_or_mountain",
        }
        with self.assertRaisesRegex(RuntimeError, "noncanonical RGBA biome channel map"):
            self.authenticate(candidate)

        candidate = copy.deepcopy(self.manifest)
        candidate["biome_channels"]["extra"] = "invalid"  # type: ignore[index]
        with self.assertRaisesRegex(RuntimeError, "noncanonical RGBA biome channel map"):
            self.authenticate(candidate)

    def test_rejects_file_tampering_before_import(self) -> None:
        filename = self.manifest["faces"][2]["land_file"]  # type: ignore[index]
        (self.source_dir / filename).write_bytes(b"tampered")  # type: ignore[arg-type]
        with self.assertRaisesRegex(RuntimeError, "Fused-face hash mismatch for PY land"):
            self.authenticate()

    def test_recomputes_full_dataset_digest_from_actual_hashes(self) -> None:
        candidate = copy.deepcopy(self.manifest)
        filename = candidate["faces"][0]["land_file"]  # type: ignore[index]
        changed_payload = b"changed but individually re-declared"
        (self.source_dir / filename).write_bytes(changed_payload)  # type: ignore[arg-type]
        candidate["faces"][0]["files"]["land"]["sha256"] = _sha256_bytes(  # type: ignore[index]
            changed_payload
        )

        # The per-file declaration now matches, but the approved full-dataset
        # digest remains unchanged and must still reject the altered bake.
        with self.assertRaisesRegex(RuntimeError, "Fused-face dataset hash mismatch"):
            self.authenticate(candidate)

    def test_rejects_missing_raster(self) -> None:
        filename = self.manifest["faces"][5]["biome_file"]  # type: ignore[index]
        (self.source_dir / filename).unlink()  # type: ignore[arg-type]
        with self.assertRaisesRegex(RuntimeError, "Missing fused-face raster"):
            self.authenticate()


class ApprovedFusedMacroDatasetTests(unittest.TestCase):
    def test_repository_approved_dataset_authenticates_without_mutation(self) -> None:
        source_dir = REPOSITORY_ROOT / importer.SOURCE_RELATIVE
        manifest_path = source_dir / "RED_MacroWorld.json"
        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        self.assertEqual(
            importer.authenticate_face_dataset(source_dir, manifest),
            importer.EXPECTED_FACE_DATASET,
        )


class _SizedArray:
    def __init__(self, size: int) -> None:
        self.size = size

    def __len__(self) -> int:
        return self.size


class _FakeClass:
    def get_name(self) -> str:
        return "PlanetGenMacroHeightfieldAsset"


class _FakeAsset:
    def __init__(self, properties: dict[str, object]) -> None:
        self.properties = properties
        self.accessed: list[str] = []

    def get_class(self) -> _FakeClass:
        return _FakeClass()

    def get_editor_property(self, property_name: str) -> object:
        self.accessed.append(property_name)
        return self.properties[property_name]


class ImportedAssetPostVerificationTests(unittest.TestCase):
    def make_asset(self) -> _FakeAsset:
        expected_samples = importer.EXPECTED_RESOLUTION**2
        properties: dict[str, object] = {
            "resolution": importer.EXPECTED_RESOLUTION,
            "min_height_cm": importer.EXPECTED_MIN_HEIGHT_CM,
            "max_height_cm": importer.EXPECTED_MAX_HEIGHT_CM,
        }
        for property_name in (
            importer.HEIGHT_FACE_PROPERTIES
            + importer.LAND_FACE_PROPERTIES
            + importer.BIOME_FACE_PROPERTIES
        ):
            properties[property_name] = _SizedArray(expected_samples)
        return _FakeAsset(properties)

    def test_post_verifies_all_six_height_land_and_biome_arrays(self) -> None:
        asset = self.make_asset()
        expected_samples = importer.EXPECTED_RESOLUTION**2
        self.assertEqual(
            importer.verify_imported_asset(asset),
            (importer.EXPECTED_RESOLUTION, expected_samples),
        )
        self.assertEqual(
            set(asset.accessed),
            {
                "resolution",
                "min_height_cm",
                "max_height_cm",
                *importer.HEIGHT_FACE_PROPERTIES,
                *importer.LAND_FACE_PROPERTIES,
                *importer.BIOME_FACE_PROPERTIES,
            },
        )

    def test_each_land_and_biome_array_is_required_at_full_resolution(self) -> None:
        expected_samples = importer.EXPECTED_RESOLUTION**2
        for property_name in (
            importer.LAND_FACE_PROPERTIES + importer.BIOME_FACE_PROPERTIES
        ):
            with self.subTest(property_name=property_name):
                asset = self.make_asset()
                asset.properties[property_name] = _SizedArray(expected_samples - 1)
                with self.assertRaisesRegex(RuntimeError, property_name):
                    importer.verify_imported_asset(asset)


if __name__ == "__main__":
    unittest.main()
