"""Focused regression coverage for the safe planet authoring workflow.

All generated fixtures live under the two production-approved SourceArt roots,
use tiny odd resolutions, and are deleted after each test.  No Unreal process is
started by this suite.

Run from the repository root with::

    python -m unittest Tools.tests.test_planet_authoring_workflow
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
from PIL import Image


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = REPOSITORY_ROOT / "Tools"
WORKFLOW_PATH = TOOLS_ROOT / "generate_planet_authoring_patches.py"
AUTHORING_ROOT = REPOSITORY_ROOT / "SourceArt" / "Planet50Km" / "AuthoringPatches"
MACRO_FACE_ROOT = (
    REPOSITORY_ROOT / "SourceArt" / "Planet50Km" / "MacroFacesFromPatches"
)
TEST_RESOLUTION = 9

if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

import generate_planet_authoring_patches as authoring
import planet_patch_compositor as compositor


def _tree_bytes(root: Path) -> dict[str, bytes]:
    """Snapshot every regular file below ``root`` using stable relative names."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _edited_pixel(values: np.ndarray) -> np.ndarray:
    result = np.asarray(values).copy()
    center = tuple(dimension // 2 for dimension in result.shape[:2])
    result[center] = int(result[center]) ^ 1
    return result


class PlanetAuthoringWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        AUTHORING_ROOT.mkdir(parents=True, exist_ok=True)
        MACRO_FACE_ROOT.mkdir(parents=True, exist_ok=True)

        self._patch_temp = tempfile.TemporaryDirectory(
            prefix="workflow_test_", dir=AUTHORING_ROOT
        )
        self.addCleanup(self._patch_temp.cleanup)
        self.patch_output = Path(self._patch_temp.name)

        self._face_temp = tempfile.TemporaryDirectory(
            prefix="workflow_test_", dir=MACRO_FACE_ROOT
        )
        self.addCleanup(self._face_temp.cleanup)
        self.face_output = Path(self._face_temp.name)

        self.profile_path = self.patch_output / "RED_TestPatchProfile.json"
        compositor.build_default_profile(self.profile_path)
        self.profile = compositor.load_profile(self.profile_path)
        authoring.generate_patch_rasters(
            self.profile,
            self.patch_output,
            TEST_RESOLUTION,
            self.profile_path,
        )
        self.source_names = authoring._expected_patch_filenames(self.profile)
        self.assertEqual(
            len(self.source_names),
            135,
            "the fixture must contain exactly five source rasters for each of 27 patches",
        )

    def _run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["TMP"] = str(self.patch_output)
        environment["TEMP"] = str(self.patch_output)
        return subprocess.run(
            [sys.executable, str(WORKFLOW_PATH), *arguments],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def _bake_existing(self) -> dict[str, object]:
        return authoring.bake_existing(
            self.profile_path,
            self.patch_output,
            self.face_output,
            TEST_RESOLUTION,
            TEST_RESOLUTION,
        )

    def _source_artifact_bytes(self) -> dict[str, bytes]:
        return {
            filename: (self.patch_output / filename).read_bytes()
            for filename in [*self.source_names, authoring.PATCH_MANIFEST_NAME]
        }

    def test_strict_bake_cli_leaves_all_135_source_rasters_unchanged(self) -> None:
        before = {
            filename: (self.patch_output / filename).read_bytes()
            for filename in self.source_names
        }
        manifest_path = self.patch_output / authoring.PATCH_MANIFEST_NAME
        manifest_before = manifest_path.read_bytes()

        completed = self._run_cli(
            "bake-existing",
            "--profile",
            str(self.profile_path),
            "--patch-output",
            str(self.patch_output),
            "--face-output",
            str(self.face_output),
            "--patch-resolution",
            str(TEST_RESOLUTION),
            "--face-resolution",
            str(TEST_RESOLUTION),
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=(
                "bake-existing CLI failed\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            ),
        )
        self.assertIn("RED_PATCH_BAKE_READY mode=bake-existing", completed.stdout)

        for filename, expected_bytes in before.items():
            with self.subTest(source_raster=filename):
                self.assertEqual(
                    (self.patch_output / filename).read_bytes(),
                    expected_bytes,
                    f"strict bake modified source raster {filename}",
                )
        self.assertEqual(
            manifest_path.read_bytes(),
            manifest_before,
            "strict bake modified the accepted source manifest",
        )

    def test_missing_command_fails_closed_without_writing_sources(self) -> None:
        patch_before = _tree_bytes(self.patch_output)
        face_before = _tree_bytes(self.face_output)

        completed = self._run_cli()

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("the following arguments are required: command", completed.stderr)
        self.assertEqual(_tree_bytes(self.patch_output), patch_before)
        self.assertEqual(_tree_bytes(self.face_output), face_before)

    def test_manifest_role_and_encoding_swaps_are_rejected(self) -> None:
        manifest_path = self.patch_output / authoring.PATCH_MANIFEST_NAME
        original_bytes = manifest_path.read_bytes()
        original = json.loads(original_bytes.decode("utf-8"))

        def swap_roles(manifest: dict[str, object]) -> None:
            files = manifest["patches"][0]["files"]  # type: ignore[index]
            files["height_raw"], files["height_png"] = (
                files["height_png"],
                files["height_raw"],
            )

        def swap_encodings(manifest: dict[str, object]) -> None:
            files = manifest["patches"][0]["files"]  # type: ignore[index]
            raw = files["height_raw"]
            png = files["height_png"]
            raw["encoding"], png["encoding"] = png["encoding"], raw["encoding"]

        for label, mutation in (
            ("role entries", swap_roles),
            ("encoding declarations", swap_encodings),
        ):
            with self.subTest(structural_tamper=label):
                candidate = copy.deepcopy(original)
                mutation(candidate)
                manifest_path.write_text(
                    json.dumps(candidate, indent=2) + "\n", encoding="utf-8"
                )
                face_before = _tree_bytes(self.face_output)
                try:
                    with self.assertRaisesRegex(ValueError, "noncanonical"):
                        self._bake_existing()
                    self.assertEqual(
                        _tree_bytes(self.face_output),
                        face_before,
                        f"rejected {label} tamper wrote macro-face artifacts",
                    )
                finally:
                    manifest_path.write_bytes(original_bytes)

    def test_initialize_refuses_existing_sources_without_force(self) -> None:
        patch_before = _tree_bytes(self.patch_output)
        face_before = _tree_bytes(self.face_output)

        with self.assertRaisesRegex(ValueError, "refuses to overwrite"):
            authoring.initialize_blockout(
                self.profile_path,
                self.patch_output,
                self.face_output,
                TEST_RESOLUTION,
                TEST_RESOLUTION,
            )

        self.assertEqual(
            _tree_bytes(self.patch_output),
            patch_before,
            "a refused initialize-blockout call modified source artifacts",
        )
        self.assertEqual(
            _tree_bytes(self.face_output),
            face_before,
            "a refused initialize-blockout call wrote macro-face artifacts",
        )

    def test_accept_edits_syncs_changed_height_png_to_r16_without_reencoding_png(
        self,
    ) -> None:
        patch = self.profile["patches"][0]
        raw_path = self.patch_output / str(patch["height_file"])
        png_path = self.patch_output / authoring._height_png_name(patch)
        with Image.open(png_path) as image:
            edited_height = _edited_pixel(np.asarray(image, dtype=np.uint16))
        Image.fromarray(edited_height).save(png_path, format="PNG")
        edited_png_bytes = png_path.read_bytes()

        manifest = authoring.accept_authored_edits(
            self.profile,
            self.patch_output,
            self.profile_path,
            TEST_RESOLUTION,
            "auto",
        )

        self.assertEqual(
            png_path.read_bytes(),
            edited_png_bytes,
            "accept-edits re-encoded the manually edited height PNG",
        )
        self.assertEqual(
            raw_path.read_bytes(),
            edited_height.astype("<u2", copy=False).tobytes(order="C"),
            "accept-edits did not synchronize the R16 companion from the PNG",
        )
        provenance = manifest["provenance"]
        self.assertEqual(
            provenance["height_resolutions"],
            [
                {
                    "patch_id": 0,
                    "source": "png",
                    "raw_changed_from_parent": False,
                    "png_changed_from_parent": True,
                }
            ],
        )
        self.assertEqual(
            {record["file"] for record in provenance["changed_files"]},
            {raw_path.name, png_path.name},
        )

    def test_raw_only_height_conflict_fails_auto_mode_without_writes(self) -> None:
        patch = self.profile["patches"][0]
        raw_path = self.patch_output / str(patch["height_file"])
        raw_height = np.fromfile(raw_path, dtype="<u2").reshape(
            (TEST_RESOLUTION, TEST_RESOLUTION)
        )
        _edited_pixel(raw_height).astype("<u2", copy=False).tofile(raw_path)
        patch_before = _tree_bytes(self.patch_output)
        face_before = _tree_bytes(self.face_output)

        with self.assertRaisesRegex(ValueError, "R16/PNG conflict"):
            authoring.accept_authored_edits(
                self.profile,
                self.patch_output,
                self.profile_path,
                TEST_RESOLUTION,
                "auto",
            )

        self.assertEqual(
            _tree_bytes(self.patch_output),
            patch_before,
            "failed auto conflict resolution wrote into the source tree",
        )
        self.assertEqual(
            _tree_bytes(self.face_output),
            face_before,
            "failed auto conflict resolution wrote macro-face artifacts",
        )

    def test_authority_mask_edit_updates_manifest_provenance(self) -> None:
        patch = self.profile["patches"][2]
        mask_path = self.patch_output / str(patch["authority_mask_file"])
        manifest_path = self.patch_output / authoring.PATCH_MANIFEST_NAME
        parent_manifest_bytes = manifest_path.read_bytes()
        parent_manifest = json.loads(parent_manifest_bytes.decode("utf-8"))
        parent_mask_hash = parent_manifest["patches"][2]["files"]["authority"][
            "sha256"
        ]

        with Image.open(mask_path) as image:
            edited_mask = np.asarray(image, dtype=np.uint8).copy()
        edited_mask[TEST_RESOLUTION // 2, TEST_RESOLUTION // 2] = 255
        Image.fromarray(edited_mask, mode="L").save(mask_path, format="PNG")
        edited_mask_bytes = mask_path.read_bytes()
        edited_mask_hash = _sha256_bytes(edited_mask_bytes)

        manifest = authoring.accept_authored_edits(
            self.profile,
            self.patch_output,
            self.profile_path,
            TEST_RESOLUTION,
            "auto",
        )

        self.assertEqual(
            mask_path.read_bytes(),
            edited_mask_bytes,
            "accept-edits rewrote the authoritative mask bytes",
        )
        provenance = manifest["provenance"]
        self.assertEqual(
            provenance["parent_manifest_sha256"],
            _sha256_bytes(parent_manifest_bytes),
        )
        self.assertEqual(
            provenance["parent_raster_dataset_sha256"],
            parent_manifest["raster_dataset_sha256"],
        )
        self.assertEqual(provenance["height_resolutions"], [])
        self.assertEqual(
            provenance["changed_files"],
            [
                {
                    "file": mask_path.name,
                    "parent_sha256": parent_mask_hash,
                    "accepted_sha256": edited_mask_hash,
                }
            ],
        )
        self.assertEqual(
            manifest["patches"][2]["files"]["authority"]["sha256"],
            edited_mask_hash,
        )

    def test_no_change_accept_leaves_manifest_byte_identical(self) -> None:
        manifest_path = self.patch_output / authoring.PATCH_MANIFEST_NAME
        manifest_before = manifest_path.read_bytes()
        tree_before = _tree_bytes(self.patch_output)

        returned = authoring.accept_authored_edits(
            self.profile,
            self.patch_output,
            self.profile_path,
            TEST_RESOLUTION,
            "auto",
        )

        self.assertEqual(returned, json.loads(manifest_before.decode("utf-8")))
        self.assertEqual(
            manifest_path.read_bytes(),
            manifest_before,
            "no-change accept rewrote the source manifest",
        )
        self.assertEqual(
            _tree_bytes(self.patch_output),
            tree_before,
            "no-change accept wrote unexpected source-tree artifacts",
        )

    def test_approved_snapshot_restores_the_complete_source_revision(self) -> None:
        artifact_names = [*self.source_names, authoring.PATCH_MANIFEST_NAME]
        baseline = {
            filename: (self.patch_output / filename).read_bytes()
            for filename in artifact_names
        }
        snapshot = authoring.snapshot_accepted_sources(
            self.profile, self.patch_output, self.profile_path
        )
        self.assertTrue((snapshot / "REVISION.json").is_file())

        patch = self.profile["patches"][5]
        mask_path = self.patch_output / str(patch["authority_mask_file"])
        with Image.open(mask_path) as image:
            edited = np.asarray(image, dtype=np.uint8).copy()
        edited[TEST_RESOLUTION // 2, TEST_RESOLUTION // 2] = 255
        Image.fromarray(edited, mode="L").save(mask_path, format="PNG")
        authoring.accept_authored_edits(
            self.profile,
            self.patch_output,
            self.profile_path,
            TEST_RESOLUTION,
            "auto",
        )
        self.assertNotEqual(mask_path.read_bytes(), baseline[mask_path.name])

        restored = authoring.restore_source_snapshot(
            self.profile,
            snapshot,
            self.patch_output,
            self.profile_path,
        )

        self.assertEqual(restored["raster_dataset_sha256"], json.loads(
            baseline[authoring.PATCH_MANIFEST_NAME].decode("utf-8")
        )["raster_dataset_sha256"])
        for filename, expected_bytes in baseline.items():
            with self.subTest(restored_file=filename):
                self.assertEqual((self.patch_output / filename).read_bytes(), expected_bytes)

    def test_accept_cli_invalid_face_preflight_preserves_unaccepted_source_bytes(
        self,
    ) -> None:
        patch = self.profile["patches"][0]
        png_path = self.patch_output / authoring._height_png_name(patch)
        with Image.open(png_path) as image:
            edited = _edited_pixel(np.asarray(image, dtype=np.uint16))
        Image.fromarray(edited).save(png_path, format="PNG")
        source_before = self._source_artifact_bytes()
        tree_before = _tree_bytes(self.patch_output)
        face_before = _tree_bytes(self.face_output)

        completed = self._run_cli(
            "accept-edits",
            "--profile",
            str(self.profile_path),
            "--patch-output",
            str(self.patch_output),
            "--face-output",
            str(self.face_output),
            "--patch-resolution",
            str(TEST_RESOLUTION),
            "--face-resolution",
            "4",
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("face resolution must be an odd integer", completed.stderr)
        self.assertEqual(self._source_artifact_bytes(), source_before)
        self.assertEqual(_tree_bytes(self.patch_output), tree_before)
        self.assertEqual(_tree_bytes(self.face_output), face_before)

    def test_restore_cli_resolution_mismatch_fails_before_source_mutation(self) -> None:
        snapshot = authoring.snapshot_accepted_sources(
            self.profile, self.patch_output, self.profile_path
        )
        patch = self.profile["patches"][3]
        mask_path = self.patch_output / str(patch["authority_mask_file"])
        with Image.open(mask_path) as image:
            edited = _edited_pixel(np.asarray(image, dtype=np.uint8))
        Image.fromarray(edited, mode="L").save(mask_path, format="PNG")
        authoring.accept_authored_edits(
            self.profile,
            self.patch_output,
            self.profile_path,
            TEST_RESOLUTION,
            "auto",
        )
        tree_before = _tree_bytes(self.patch_output)
        face_before = _tree_bytes(self.face_output)

        completed = self._run_cli(
            "restore-snapshot",
            "--profile",
            str(self.profile_path),
            "--patch-output",
            str(self.patch_output),
            "--face-output",
            str(self.face_output),
            "--snapshot",
            str(snapshot),
            "--patch-resolution",
            str(TEST_RESOLUTION + 2),
            "--face-resolution",
            str(TEST_RESOLUTION),
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("does not match --patch-resolution", completed.stderr)
        self.assertEqual(_tree_bytes(self.patch_output), tree_before)
        self.assertEqual(_tree_bytes(self.face_output), face_before)

    def test_accept_transaction_rolls_source_back_when_face_bake_fails(self) -> None:
        patch = self.profile["patches"][4]
        mask_path = self.patch_output / str(patch["authority_mask_file"])
        with Image.open(mask_path) as image:
            edited = _edited_pixel(np.asarray(image, dtype=np.uint8))
        Image.fromarray(edited, mode="L").save(mask_path, format="PNG")
        source_before = self._source_artifact_bytes()

        with mock.patch.object(
            authoring, "bake_macro_faces", side_effect=RuntimeError("forced face failure")
        ):
            with self.assertRaisesRegex(RuntimeError, "forced face failure"):
                authoring.accept_edits_and_bake(
                    self.profile_path,
                    self.patch_output,
                    self.face_output,
                    TEST_RESOLUTION,
                    TEST_RESOLUTION,
                )

        self.assertEqual(self._source_artifact_bytes(), source_before)

    def test_restore_transaction_rolls_source_back_when_face_bake_fails(self) -> None:
        snapshot = authoring.snapshot_accepted_sources(
            self.profile, self.patch_output, self.profile_path
        )
        patch = self.profile["patches"][6]
        mask_path = self.patch_output / str(patch["authority_mask_file"])
        with Image.open(mask_path) as image:
            edited = _edited_pixel(np.asarray(image, dtype=np.uint8))
        Image.fromarray(edited, mode="L").save(mask_path, format="PNG")
        authoring.accept_authored_edits(
            self.profile,
            self.patch_output,
            self.profile_path,
            TEST_RESOLUTION,
            "auto",
        )
        source_before = self._source_artifact_bytes()

        with mock.patch.object(
            authoring, "bake_macro_faces", side_effect=RuntimeError("forced face failure")
        ):
            with self.assertRaisesRegex(RuntimeError, "forced face failure"):
                authoring.restore_snapshot_and_bake(
                    self.profile_path,
                    snapshot,
                    self.patch_output,
                    self.face_output,
                    TEST_RESOLUTION,
                    TEST_RESOLUTION,
                )

        self.assertEqual(self._source_artifact_bytes(), source_before)

    def test_corrupt_existing_snapshot_metadata_is_rejected_on_reuse(self) -> None:
        snapshot = authoring.snapshot_accepted_sources(
            self.profile, self.patch_output, self.profile_path
        )
        (snapshot / "REVISION.json").write_text("{corrupt", encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "cannot read revision backup"):
            authoring.snapshot_accepted_sources(
                self.profile, self.patch_output, self.profile_path
            )

    def test_tampered_content_addressed_snapshot_is_rejected_before_restore(self) -> None:
        snapshot = authoring.snapshot_accepted_sources(
            self.profile, self.patch_output, self.profile_path
        )
        target_name = str(self.profile["patches"][7]["authority_mask_file"])
        target = snapshot / target_name
        with Image.open(target) as image:
            edited = _edited_pixel(np.asarray(image, dtype=np.uint8))
        Image.fromarray(edited, mode="L").save(target, format="PNG")
        source_before = self._source_artifact_bytes()

        with self.assertRaisesRegex(RuntimeError, "revision backup hash mismatch"):
            authoring.restore_source_snapshot(
                self.profile,
                snapshot,
                self.patch_output,
                self.profile_path,
            )

        self.assertEqual(self._source_artifact_bytes(), source_before)

    def test_face_bake_rejects_source_edit_after_raster_load_without_publication(
        self,
    ) -> None:
        self._bake_existing()
        face_before = _tree_bytes(self.face_output)
        patch = self.profile["patches"][8]
        target = self.patch_output / str(patch["authority_mask_file"])
        source_bytes = target.read_bytes()
        original_loader = authoring.load_patch_rasters

        def load_then_edit(*args: object, **kwargs: object) -> object:
            loaded = original_loader(*args, **kwargs)
            with Image.open(target) as image:
                edited = _edited_pixel(np.asarray(image, dtype=np.uint8))
            Image.fromarray(edited, mode="L").save(target, format="PNG")
            return loaded

        try:
            with mock.patch.object(
                authoring, "load_patch_rasters", side_effect=load_then_edit
            ):
                with self.assertRaisesRegex(RuntimeError, "source raster changed"):
                    self._bake_existing()
        finally:
            target.write_bytes(source_bytes)

        self.assertEqual(_tree_bytes(self.face_output), face_before)

    def test_accept_rollback_preserves_a_concurrent_editor_save(self) -> None:
        accepted_patch = self.profile["patches"][9]
        accepted_mask = self.patch_output / str(accepted_patch["authority_mask_file"])
        with Image.open(accepted_mask) as image:
            accepted_edit = _edited_pixel(np.asarray(image, dtype=np.uint8))
        Image.fromarray(accepted_edit, mode="L").save(accepted_mask, format="PNG")

        concurrent_patch = self.profile["patches"][10]
        concurrent_mask = self.patch_output / str(concurrent_patch["authority_mask_file"])
        original_accept = authoring.accept_authored_edits
        concurrent_bytes = b""

        def accept_then_save(*args: object, **kwargs: object) -> dict[str, object]:
            nonlocal concurrent_bytes
            manifest = original_accept(*args, **kwargs)
            with Image.open(concurrent_mask) as image:
                concurrent_edit = _edited_pixel(np.asarray(image, dtype=np.uint8))
            Image.fromarray(concurrent_edit, mode="L").save(concurrent_mask, format="PNG")
            concurrent_bytes = concurrent_mask.read_bytes()
            return manifest

        with mock.patch.object(
            authoring, "accept_authored_edits", side_effect=accept_then_save
        ):
            with self.assertRaisesRegex(RuntimeError, "preserving the newer live files"):
                authoring.accept_edits_and_bake(
                    self.profile_path,
                    self.patch_output,
                    self.face_output,
                    TEST_RESOLUTION,
                    TEST_RESOLUTION,
                )

        self.assertEqual(concurrent_mask.read_bytes(), concurrent_bytes)

    def test_restore_preflight_preserves_a_concurrent_editor_save(self) -> None:
        snapshot = authoring.snapshot_accepted_sources(
            self.profile, self.patch_output, self.profile_path
        )
        target = self.patch_output / str(
            self.profile["patches"][11]["authority_mask_file"]
        )
        original_restore = authoring.restore_source_snapshot
        concurrent_bytes = b""

        def save_then_restore(*args: object, **kwargs: object) -> dict[str, object]:
            nonlocal concurrent_bytes
            with Image.open(target) as image:
                concurrent_edit = _edited_pixel(np.asarray(image, dtype=np.uint8))
            Image.fromarray(concurrent_edit, mode="L").save(target, format="PNG")
            concurrent_bytes = target.read_bytes()
            return original_restore(*args, **kwargs)

        with mock.patch.object(
            authoring, "restore_source_snapshot", side_effect=save_then_restore
        ):
            with self.assertRaisesRegex(RuntimeError, "preserving the newer live files"):
                authoring.restore_snapshot_and_bake(
                    self.profile_path,
                    snapshot,
                    self.patch_output,
                    self.face_output,
                    TEST_RESOLUTION,
                    TEST_RESOLUTION,
                )

        self.assertEqual(target.read_bytes(), concurrent_bytes)


if __name__ == "__main__":
    unittest.main()
