"""Contracts for the fixed NWIRO activation-parent replay publisher."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from Tools import create_redmmo_nwiro_activation_replay as sut


class NwiroActivationReplayTests(unittest.TestCase):
    @staticmethod
    def _parent_snapshot() -> sut.TreeSnapshot:
        parent = sut._authenticated_json(
            sut.PARENT_MANIFEST,
            sut.PARENT_MANIFEST_SHA256,
        )
        tree = parent["tree"]
        return sut.TreeSnapshot(
            root=sut._path_text(sut.OUTPUT_TREE),
            directories=tuple(tree["directories"]),
            files=tuple(tree["files"]),
            file_count=tree["file_count"],
            directory_count_excluding_root=tree[
                "directory_count_excluding_root"
            ],
            total_bytes=tree["total_bytes"],
            record_set_sha256=tree["record_set_sha256"],
            topology_sha256=tree["topology_sha256"],
        )

    def test_exact_historical_method_sets_are_pinned(self) -> None:
        source = __import__(
            "Tools.tests.test_redmmo_nwiro_activation_ownership_source",
            fromlist=["NwiroActivationOwnershipSourceTests"],
        )
        manifest = __import__(
            "Tools.tests.test_generate_redmmo_nwiro_activation_ownership_manifests",
            fromlist=["NwiroActivationOwnershipManifestTests"],
        )
        self.assertEqual(
            sut.SOURCE_TEST_METHODS,
            sut._method_names(
                source.NwiroActivationOwnershipSourceTests
            ),
        )
        self.assertEqual(
            sut.MANIFEST_TEST_METHODS,
            sut._method_names(
                manifest.NwiroActivationOwnershipManifestTests
            ),
        )
        self.assertEqual(22, len(sut.SOURCE_TEST_METHODS) + len(sut.MANIFEST_TEST_METHODS))

    def test_overlay_is_exactly_three_parent_files(self) -> None:
        self.assertEqual(
            {
                "Source/NwiroIntegrationKit/Private/NwiroIKBridge.cpp",
                "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
                "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.h",
            },
            set(sut.OVERLAY_SOURCES),
        )
        self.assertEqual(
            sut.EXPECTED_ROLLBACK_TOTAL_BYTES,
            sum(
                int(record["bytes"])
                for record in sut.OVERLAY_SOURCES.values()
            ),
        )

    def test_authenticated_inputs_reconstruct_parent_logically(self) -> None:
        boundary = sut._authenticate_inputs()
        parent = sut._parent_records(boundary["parent"])
        current = sut._records(boundary["current"])
        rollback = sut._records(boundary["rollback"])
        reconstructed: dict[str, tuple[int, str]] = {}
        for relative, record in parent.items():
            if relative in sut.OVERLAY_SOURCES:
                selected = rollback[
                    str(sut.OVERLAY_SOURCES[relative]["rollback_name"])
                ]
            else:
                selected = current[relative]
            reconstructed[relative] = (
                int(selected["bytes"]),
                str(selected["sha256"]),
            )
        self.assertEqual(
            {
                relative: (
                    int(record["bytes"]),
                    str(record["sha256"]),
                )
                for relative, record in parent.items()
            },
            reconstructed,
        )

    def test_execution_authorization_forbids_runtime_and_mutation(self) -> None:
        authorization, _ = sut._authenticate_authorization()
        authorities = authorization["authorities"]
        self.assertIs(authorities["replay_publication_authorized"], True)
        self.assertIs(
            authorities["historical_offline_assertion_replay_authorized"],
            True,
        )
        for field in (
            "source_mutation_authorized",
            "live_candidate_swap_authorized",
            "junction_or_link_authorized",
            "build_authorized",
            "install_authorized",
            "unreal_launch_authorized",
            "mcp_initialize_authorized",
            "mcp_tool_call_authorized",
            "network_authorized",
            "provider_call_authorized",
            "asset_load_authorized",
            "asset_or_map_mutation_authorized",
            "vendor_plugin_mutation_authorized",
            "codex_config_mutation_authorized",
            "runtime_acceptance_claim_authorized",
            "static_candidate_acceptance_claim_authorized",
        ):
            self.assertIs(authorities[field], False, field)

    def test_replay_target_is_external_and_not_a_plugin_root(self) -> None:
        target = sut._path_text(sut.OUTPUT_ROOT).casefold()
        for forbidden in (
            sut._path_text(sut.PROJECT_ROOT / "Plugins").casefold(),
            sut._path_text(Path(r"D:\UE_5.8\Engine\Plugins")).casefold(),
            sut._path_text(sut.CURRENT_CANDIDATE_ROOT).casefold(),
        ):
            self.assertNotEqual(forbidden, target)
            self.assertFalse(target.startswith(forbidden.rstrip("/") + "/"))

    def test_locked_reader_authenticates_one_fixed_input(self) -> None:
        payload = sut._stable_payload(sut.HISTORICAL_SOURCE_TEST)
        self.assertEqual(
            sut.HISTORICAL_SOURCE_TEST_SHA256,
            sut._sha256(payload),
        )

    def test_manifest_rejects_noncanonical_timestamp_before_output(self) -> None:
        fake = mock.Mock()
        with self.assertRaises(sut.ActivationReplayError):
            sut._manifest_document(
                captured_utc="2026-07-25 13:00:00",
                authorization_hash="A" * 64,
                snapshot=fake,
            )
        self.assertFalse(fake.semantic_payload.called)

    def test_publish_refuses_existing_target_before_authentication(self) -> None:
        with mock.patch.object(
            sut, "_lexists", return_value=True
        ), mock.patch.object(sut, "_authenticate_inputs") as authenticate:
            with self.assertRaises(sut.ActivationReplayError):
                sut.publish()
        authenticate.assert_not_called()

    def test_manifest_false_authorities_are_explicit(self) -> None:
        snapshot = self._parent_snapshot()
        document = sut._manifest_document(
            captured_utc="2026-07-25T13:00:00Z",
            authorization_hash="A" * 64,
            snapshot=snapshot,
        )
        self.assertEqual(
            document["manifest_semantic_sha256"],
            sut._semantic_hash(document),
        )
        json.loads(sut._canonical_file_bytes(document).decode("utf-8"))
        for field in (
            "candidate_static_accepted",
            "runtime_authorized",
            "build_authorized",
            "install_authorized",
            "unreal_launch_authorized",
            "mcp_initialize_authorized",
            "mcp_tool_call_authorized",
            "network_authorized",
            "provider_call_authorized",
            "asset_or_map_mutation_authorized",
            "power_loss_durability_proven",
        ):
            self.assertIs(document[field], False, field)

    def test_manifest_rejects_semantically_rehashed_forged_lineage(self) -> None:
        snapshot = self._parent_snapshot()
        document = sut._manifest_document(
            captured_utc="2026-07-25T13:00:00Z",
            authorization_hash="A" * 64,
            snapshot=snapshot,
        )
        document["lineage"]["parent_activation_evidence"]["raw_sha256"] = (
            "B" * 64
        )
        document["manifest_semantic_sha256"] = sut._semantic_hash(document)
        with self.assertRaisesRegex(
            sut.ActivationReplayError,
            "exact reconstructed document",
        ):
            sut._verify_manifest(document, snapshot, "A" * 64)

    def test_preloaded_historical_module_is_refused(self) -> None:
        name = next(iter(sut.HISTORICAL_MODULES))
        with mock.patch.dict(sut.sys.modules, {name: mock.Mock()}):
            with self.assertRaisesRegex(
                sut.ActivationReplayError,
                "fresh interpreter",
            ):
                sut._require_fresh_historical_modules()

    def test_runner_pins_proxy_counts_restoration_and_postflight(self) -> None:
        source = Path(sut.__file__).read_text(encoding="utf-8")
        for required in (
            'proxy_counts != {"candidate": 4, "rollback": 4}',
            "source_test.CANDIDATE_ROOT = original_source_root",
            "generator._scan_two_pass = original_scan",
            "post_verified = verify()",
            "with _held_read_locks(",
            "_fresh_historical_imports() as",
        ):
            self.assertIn(required, source)

    def test_manifest_discloses_unproven_source_ancestor_atomicity(self) -> None:
        document = sut._manifest_document(
            captured_utc="2026-07-25T13:00:00Z",
            authorization_hash="A" * 64,
            snapshot=self._parent_snapshot(),
        )
        reconstruction = document["reconstruction"]
        self.assertIs(
            reconstruction["source_ancestor_path_atomicity_proven"],
            False,
        )
        self.assertIs(reconstruction["publisher_created_link"], False)
        self.assertIn("not proven", document["claim_limit"])

    def test_publisher_has_no_recursive_cleanup_or_live_swap(self) -> None:
        source = Path(sut.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "shutil.rmtree",
            "os.remove(",
            ".unlink(",
            "CURRENT_CANDIDATE_ROOT.rename",
            "os.symlink",
            "mklink",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("run_owned_orphan_transaction_preserved_on_failure", source)


if __name__ == "__main__":
    unittest.main()
