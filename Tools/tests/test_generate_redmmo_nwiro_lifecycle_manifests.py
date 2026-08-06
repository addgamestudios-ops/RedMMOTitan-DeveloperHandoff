"""Contracts for the fixed NWIRO lifecycle evidence publisher."""

from __future__ import annotations

import unittest

from Tools.generate_redmmo_nwiro_lifecycle_manifests import (
    EXPECTED_CHANGED_FILES,
    EXPECTED_CUMULATIVE_CHANGED_FILES,
    EXPECTED_FILE_COUNT,
    EXPECTED_RECORD_SET_SHA256,
    LifecycleManifestError,
    _semantic_hash,
    build_documents,
)


CAPTURED_UTC = "2026-07-25T12:45:00Z"


class NwiroLifecycleManifestTests(unittest.TestCase):
    def test_build_is_deterministic_for_same_capture_time(self) -> None:
        first = build_documents(CAPTURED_UTC)
        second = build_documents(CAPTURED_UTC)
        self.assertEqual(first, second)

    def test_candidate_tree_is_exact_and_static_only(self) -> None:
        candidate, _ = build_documents(CAPTURED_UTC)
        self.assertEqual(EXPECTED_FILE_COUNT, candidate["tree"]["file_count"])
        self.assertEqual(
            EXPECTED_RECORD_SET_SHA256,
            candidate["tree"]["record_set_sha256"],
        )
        self.assertEqual("static", candidate["evidence_class"])
        self.assertFalse(candidate["controls"]["candidate_static_accepted"])
        self.assertFalse(candidate["controls"]["runtime_accepted"])

    def test_delta_is_complete_three_file_lifecycle_modification_only(
        self,
    ) -> None:
        candidate, delta = build_documents(CAPTURED_UTC)
        self.assertEqual(
            list(EXPECTED_CHANGED_FILES),
            delta["expected_modified_paths"],
        )
        self.assertEqual(
            list(EXPECTED_CUMULATIVE_CHANGED_FILES),
            candidate["cumulative_vendor_baseline_modified_paths"],
        )
        self.assertEqual(3, delta["counts"]["modified"])
        self.assertEqual(87, delta["counts"]["unchanged"])
        self.assertEqual(0, delta["counts"]["added"])
        self.assertEqual(0, delta["counts"]["removed"])
        self.assertEqual(0, delta["counts"]["renamed"])

    def test_forbidden_runtime_authorities_remain_false(self) -> None:
        candidate, _ = build_documents(CAPTURED_UTC)
        controls = candidate["controls"]
        for key in (
            "production_activation_authorized",
            "compile_authorized",
            "install_authorized",
            "unreal_launch_authorized",
            "mcp_authorized",
            "network_authorized",
            "provider_authorized",
            "asset_or_map_mutation_authorized",
        ):
            self.assertIs(controls[key], False, key)

    def test_manifest_semantic_hashes_recompute(self) -> None:
        candidate, delta = build_documents(CAPTURED_UTC)
        self.assertEqual(
            candidate["manifest_semantic_sha256"],
            _semantic_hash(candidate),
        )
        self.assertEqual(
            delta["manifest_semantic_sha256"],
            _semantic_hash(delta),
        )

    def test_noncanonical_timestamp_is_rejected(self) -> None:
        for value in (
            "",
            "2026-07-25",
            "2026-07-25T12:45:00+00:00",
            "2026-07-25T12:45:00Z ",
        ):
            with self.subTest(value=value):
                with self.assertRaises(LifecycleManifestError):
                    build_documents(value)


if __name__ == "__main__":
    unittest.main()
