"""Contracts for the fixed NWIRO activation/ownership evidence publisher."""

from __future__ import annotations

import json
import unittest
from unittest import mock

from Tools import generate_redmmo_nwiro_activation_ownership_manifests as sut


CAPTURED_UTC = "2026-07-25T11:30:09.216000Z"


class NwiroActivationOwnershipManifestTests(unittest.TestCase):
    def test_documents_bind_exact_five_file_delta_and_inert_claims(self) -> None:
        candidate, delta = sut.build_documents(CAPTURED_UTC)
        self.assertEqual(
            list(sut.EXPECTED_CHANGED_FILES),
            [record["path"] for record in delta["modified"]],
        )
        current = {
            record["path"]: record["sha256"]
            for record in candidate["tree"]["files"]
            if record["path"] in sut.EXPECTED_CURRENT_FILES
        }
        self.assertEqual(sut.EXPECTED_CURRENT_FILES, current)
        self.assertEqual(
            sut.EXPECTED_CURRENT_RECORD_SET_SHA256,
            candidate["tree"]["record_set_sha256"],
        )
        self.assertEqual(
            {
                "unchanged": 85,
                "modified": 5,
                "added": 0,
                "removed": 0,
                "renamed": 0,
                "directories_unchanged": 10,
                "directories_added": 0,
                "directories_removed": 0,
            },
            delta["counts"],
        )
        controls = candidate["controls"]
        self.assertIs(controls["source_default_off_implemented"], True)
        self.assertIs(controls["process_wide_single_owner_implemented"], True)
        for field in (
            "source_default_off_accepted",
            "process_wide_single_owner_accepted",
            "restricted_mode_implemented",
            "candidate_static_accepted",
            "production_activation_authorized",
            "build_authorized",
            "compile_authorized",
            "install_authorized",
            "unreal_launch_authorized",
            "mcp_initialize_authorized",
            "mcp_tool_call_authorized",
            "network_authorized",
            "provider_call_authorized",
            "runtime_authorized",
            "project_asset_or_map_mutation_authorized",
        ):
            self.assertIs(controls[field], False, field)
        self.assertIn("same Windows logon/session", candidate["process_owner_scope"])
        self.assertIn("native two-process", candidate["claim_limit"])
        self.assertEqual(4, len(candidate["known_open_bypasses"]))
        self.assertEqual(5, candidate["rollback_subset"]["file_count"])
        self.assertIn(
            "raw_sha256",
            candidate["lineage"]["source_contract_test"],
        )

    def test_documents_are_canonical_and_deterministic(self) -> None:
        first = sut.build_documents(CAPTURED_UTC)
        second = sut.build_documents(CAPTURED_UTC)
        for left, right in zip(first, second):
            self.assertEqual(
                sut._canonical_file_bytes(left),
                sut._canonical_file_bytes(right),
            )
            self.assertEqual(
                left["manifest_semantic_sha256"],
                sut._semantic_hash(left),
            )
            json.loads(sut._canonical_file_bytes(left).decode("utf-8"))

    def test_invalid_timestamp_fails_before_scanning(self) -> None:
        with mock.patch.object(sut, "_authenticate_boundary") as boundary:
            with self.assertRaises(sut.ActivationOwnershipManifestError):
                sut.build_documents("2026-07-25 11:30:09")
        boundary.assert_not_called()

    def test_publish_refuses_either_existing_fixed_output(self) -> None:
        with mock.patch.object(
            sut, "_lexists", return_value=True
        ), mock.patch.object(sut, "build_documents") as build:
            with self.assertRaises(sut.ActivationOwnershipManifestError):
                sut.publish()
        build.assert_not_called()

    def test_publish_refuses_orphan_transaction_namespace(self) -> None:
        orphan = mock.Mock()
        orphan.name = (
            ".NwiroRestrictedProbeActivationOwnershipEvidenceV1.txn.orphan"
        )
        with mock.patch.object(sut, "_lexists", return_value=False), mock.patch.object(
            sut.Path, "iterdir", return_value=iter([orphan])
        ), mock.patch.object(sut, "build_documents") as build:
            with self.assertRaises(sut.ActivationOwnershipManifestError):
                sut.publish()
        build.assert_not_called()

    def test_delta_binds_candidate_raw_bytes(self) -> None:
        candidate, delta = sut.build_documents(CAPTURED_UTC)
        self.assertEqual(
            sut._sha256(sut._canonical_file_bytes(candidate)),
            delta["candidate_manifest"]["raw_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
