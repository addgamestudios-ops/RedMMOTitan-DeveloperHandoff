"""Static contract for the native M12 backend automation source file.

This suite proves only that the intended C++ automation harness is present and
scope-contained. It does not compile or execute that harness.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
NATIVE_TEST = (
    ROOT
    / "Source/RedMMO/Mining/RedInMemorySparseVoxelBackendTests.cpp"
)


def automation_body(source: str, signature: str) -> str:
    start = source.index(signature)
    next_registration = re.search(
        r"(?m)^\s*IMPLEMENT_SIMPLE_AUTOMATION_TEST\(",
        source[start:],
    )
    next_test = (
        -1
        if next_registration is None
        else start + next_registration.start()
    )
    guard_end = source.index(
        "#endif // WITH_DEV_AUTOMATION_TESTS",
        start,
    )
    end = guard_end if next_test == -1 else min(next_test, guard_end)
    return source[start:end]


class NativeBackendAutomationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = NATIVE_TEST.read_text(encoding="utf-8")
        cls.source_compact = " ".join(cls.source.split())
        restore_signature = (
            "bool FRedVoxelCheckpointCorruptionRestoreInvalidationTest"
            "::RunTest"
        )
        cls.restore_source = automation_body(cls.source, restore_signature)
        reissue_signature = (
            "bool FRedVoxelPersistenceTicketReissueTest::RunTest"
        )
        cls.reissue_source = automation_body(cls.source, reissue_signature)
        cls.reissue_compact = " ".join(cls.reissue_source.split())
        generated_output_signature = (
            "bool FRedVoxelGeneratedOutputRoleIsolationAndStaleCompletionTest"
            "::RunTest"
        )
        cls.generated_output_source = automation_body(
            cls.source,
            generated_output_signature,
        )
        cls.generated_output_compact = " ".join(
            cls.generated_output_source.split()
        )
        deterministic_init_signature = (
            "bool FRedVoxelDeterministicInitializationTest::RunTest"
        )
        cls.deterministic_init_source = automation_body(
            cls.source,
            deterministic_init_signature,
        )
        cls.deterministic_init_compact = " ".join(
            cls.deterministic_init_source.split()
        )
        multi_volume_signature = (
            "bool FRedVoxelMultiVolumeIsolationTest::RunTest"
        )
        cls.multi_volume_source = automation_body(
            cls.source,
            multi_volume_signature,
        )
        cls.multi_volume_compact = " ".join(
            cls.multi_volume_source.split()
        )
        equivocation_signature = (
            "bool FRedVoxelSameRevisionCheckpointManifestEquivocationTest"
            "::RunTest"
        )
        cls.equivocation_source = automation_body(
            cls.source,
            equivocation_signature,
        )
        cls.equivocation_compact = " ".join(
            cls.equivocation_source.split()
        )
        capacity_signature = (
            "bool FRedVoxelJournalCapacityReleaseTest::RunTest"
        )
        cls.capacity_source = automation_body(
            cls.source,
            capacity_signature,
        )
        cls.capacity_compact = " ".join(
            cls.capacity_source.split()
        )
        release_signature = (
            "bool FRedVoxelReleaseRecreateGenerationCASTest::RunTest"
        )
        cls.release_source = automation_body(
            cls.source,
            release_signature,
        )
        cls.release_compact = " ".join(
            cls.release_source.split()
        )

    def test_native_automation_is_product_filtered_and_dev_guarded(self):
        for token in (
            '#include "RedInMemorySparseVoxelBackend.h"',
            "#if WITH_DEV_AUTOMATION_TESTS",
            '#include "Misc/AutomationTest.h"',
            "IMPLEMENT_SIMPLE_AUTOMATION_TEST(",
            "FRedVoxelJournalCheckpointPersistenceTest",
            '"RedMMO.Mining.VoxelBackend.JournalCheckpointPersistence"',
            "FRedVoxelCheckpointCorruptionRestoreInvalidationTest",
            (
                '"RedMMO.Mining.VoxelBackend.'
                'CheckpointCorruptionRestoreInvalidation"'
            ),
            "FRedVoxelPersistenceTicketReissueTest",
            '"RedMMO.Mining.VoxelBackend.PersistenceTicketReissue"',
            (
                "FRedVoxelGeneratedOutputRoleIsolationAnd"
                "StaleCompletionTest"
            ),
            (
                '"RedMMO.Mining.VoxelBackend.'
                'GeneratedOutputRoleIsolationAndStaleCompletion"'
            ),
            "FRedVoxelDeterministicInitializationTest",
            (
                '"RedMMO.Mining.VoxelBackend.'
                'DeterministicInitialization"'
            ),
            "FRedVoxelMultiVolumeIsolationTest",
            '"RedMMO.Mining.VoxelBackend.MultiVolumeIsolation"',
            "FRedVoxelSameRevisionCheckpointManifestEquivocationTest",
            (
                '"RedMMO.Mining.VoxelBackend.'
                'SameRevisionCheckpointManifestEquivocation"'
            ),
            "FRedVoxelJournalCapacityReleaseTest",
            (
                '"RedMMO.Mining.VoxelBackend.'
                'JournalCapacityRelease"'
            ),
            "FRedVoxelReleaseRecreateGenerationCASTest",
            (
                '"RedMMO.Mining.VoxelBackend.'
                'ReleaseRecreateGenerationCAS"'
            ),
            "EAutomationTestFlags_ApplicationContextMask",
            "EAutomationTestFlags::ProductFilter",
            "#endif // WITH_DEV_AUTOMATION_TESTS",
        ):
            self.assertIn(token, self.source)
        self.assertEqual(
            self.source.count("IMPLEMENT_SIMPLE_AUTOMATION_TEST("),
            9,
        )
        guard = self.source.index("#if WITH_DEV_AUTOMATION_TESTS")
        backend_include = self.source.index(
            '#include "RedInMemorySparseVoxelBackend.h"'
        )
        implementation = self.source.index("IMPLEMENT_SIMPLE_AUTOMATION_TEST(")
        last_implementation = self.source.rindex(
            "IMPLEMENT_SIMPLE_AUTOMATION_TEST("
        )
        guard_end = self.source.rindex(
            "#endif // WITH_DEV_AUTOMATION_TESTS"
        )
        self.assertLess(guard, backend_include)
        self.assertLess(backend_include, implementation)
        self.assertLess(implementation, guard_end)
        self.assertLess(last_implementation, guard_end)
        self.assertEqual(
            self.source.count(
                "EAutomationTestFlags_ApplicationContextMask"
            ),
            9,
        )
        self.assertEqual(
            self.source.count("EAutomationTestFlags::ProductFilter"),
            9,
        )
        self.assertEqual(
            self.source.count("#if WITH_DEV_AUTOMATION_TESTS"),
            1,
        )
        self.assertEqual(
            self.source.count("#endif // WITH_DEV_AUTOMATION_TESTS"),
            1,
        )
        self.assertTrue(
            self.source.rstrip().endswith(
                "#endif // WITH_DEV_AUTOMATION_TESTS"
            )
        )
        registrations = (
            (
                "FRedVoxelJournalCheckpointPersistenceTest",
                "RedMMO.Mining.VoxelBackend."
                "JournalCheckpointPersistence",
            ),
            (
                "FRedVoxelCheckpointCorruptionRestoreInvalidationTest",
                "RedMMO.Mining.VoxelBackend."
                "CheckpointCorruptionRestoreInvalidation",
            ),
            (
                "FRedVoxelPersistenceTicketReissueTest",
                "RedMMO.Mining.VoxelBackend.PersistenceTicketReissue",
            ),
            (
                "FRedVoxelGeneratedOutputRoleIsolationAnd"
                "StaleCompletionTest",
                "RedMMO.Mining.VoxelBackend."
                "GeneratedOutputRoleIsolationAndStaleCompletion",
            ),
            (
                "FRedVoxelDeterministicInitializationTest",
                "RedMMO.Mining.VoxelBackend."
                "DeterministicInitialization",
            ),
            (
                "FRedVoxelMultiVolumeIsolationTest",
                "RedMMO.Mining.VoxelBackend.MultiVolumeIsolation",
            ),
            (
                "FRedVoxelSameRevisionCheckpointManifestEquivocationTest",
                "RedMMO.Mining.VoxelBackend."
                "SameRevisionCheckpointManifestEquivocation",
            ),
            (
                "FRedVoxelJournalCapacityReleaseTest",
                "RedMMO.Mining.VoxelBackend.JournalCapacityRelease",
            ),
            (
                "FRedVoxelReleaseRecreateGenerationCASTest",
                "RedMMO.Mining.VoxelBackend."
                "ReleaseRecreateGenerationCAS",
            ),
        )
        for test_class, test_path in registrations:
            registration = (
                "IMPLEMENT_SIMPLE_AUTOMATION_TEST( "
                f"{test_class}, "
                f'"{test_path}", '
                "EAutomationTestFlags_ApplicationContextMask | "
                "EAutomationTestFlags::ProductFilter)"
            )
            self.assertEqual(
                self.source_compact.count(registration),
                1,
            )
        self.assertNotIn(
            "FRedVoxelPersistenceTicketReissueTest",
            self.restore_source,
        )
        self.assertNotIn(
            "#endif // WITH_DEV_AUTOMATION_TESTS",
            self.restore_source,
        )
        self.assertNotIn(
            "FRedVoxelGeneratedOutputRoleIsolationAndStaleCompletionTest",
            self.reissue_source,
        )
        self.assertNotIn(
            "#endif // WITH_DEV_AUTOMATION_TESTS",
            self.generated_output_source,
        )
        self.assertNotIn(
            "FRedVoxelDeterministicInitializationTest",
            self.generated_output_source,
        )
        self.assertNotIn(
            "#endif // WITH_DEV_AUTOMATION_TESTS",
            self.deterministic_init_source,
        )
        self.assertNotIn(
            "FRedVoxelMultiVolumeIsolationTest",
            self.deterministic_init_source,
        )
        self.assertNotIn(
            "#endif // WITH_DEV_AUTOMATION_TESTS",
            self.multi_volume_source,
        )
        self.assertNotIn(
            "FRedVoxelSameRevisionCheckpointManifestEquivocationTest",
            self.multi_volume_source,
        )
        self.assertNotIn(
            "#endif // WITH_DEV_AUTOMATION_TESTS",
            self.equivocation_source,
        )
        self.assertNotIn(
            "FRedVoxelJournalCapacityReleaseTest",
            self.equivocation_source,
        )
        self.assertNotIn(
            "#endif // WITH_DEV_AUTOMATION_TESTS",
            self.capacity_source,
        )
        self.assertNotIn(
            "#endif // WITH_DEV_AUTOMATION_TESTS",
            self.release_source,
        )

    def test_fixture_is_small_deterministic_and_canonically_fingerprinted(self):
        for token in (
            'TEXT("asteroid.red.m12.native-journal")',
            'TEXT("red.material-table.prototype-v1")',
            "FIntVector(16, 16, 16)",
            "FIntVector(8, 8, 8)",
            "Spec.CellSizeCm = 100.f",
            "Spec.BaseSeed = 0x4D31324AU",
            "Spec.GenerationVersion = 1",
            "ComputeCanonicalVolumeSpecSha256(Spec, CanonicalSpecSha256)",
            "Spec.CanonicalSpecSha256 = MoveTemp(CanonicalSpecSha256)",
            "Backend.InitializeVolume(Spec, Limits, Error)",
        ):
            self.assertIn(token, self.source)
        self.assertLess(
            self.source.index("ComputeCanonicalVolumeSpecSha256("),
            self.source.index("Backend.InitializeVolume("),
        )

    def test_prefix_checkpoint_is_captured_between_two_accepted_edits(self):
        first_edit = self.source.index("const bool bFirstEditAccepted")
        capture = self.source.index("const bool bCapturedFirstCheckpoint")
        second_edit = self.source.index("const bool bSecondEditAccepted")
        acknowledgement = self.source.index("const bool bAcknowledgedPrefix")
        export = self.source.index("const bool bExportedSuffix")
        self.assertLess(first_edit, capture)
        self.assertLess(capture, second_edit)
        self.assertLess(second_edit, acknowledgement)
        self.assertLess(acknowledgement, export)
        for token in (
            "&& OutResult.bAccepted",
            "FirstResult.RejectReason == EEditRejectReason::None",
            "SecondResult.RejectReason == EEditRejectReason::None",
            "FirstPersistenceRequest.Ticket.CheckpointThroughRevision, uint64(1)",
            "FirstPersistenceRequest.Checkpoint.ThroughRevision, uint64(1)",
            "ValidateCheckpointPersistenceRequest(",
        ):
            self.assertIn(token, self.source)

    def test_wrong_token_rejection_cannot_promote_or_roll_back_state(self):
        wrong_ack = self.source.index("const bool bAcceptedWrongToken")
        exact_ack = self.source.index("const bool bAcknowledgedPrefix")
        self.assertLess(wrong_ack, exact_ack)
        for token in (
            "++WrongTokenAcknowledgement.Ticket.PersistenceRequestToken",
            "A reconstructed persistence token is rejected",
            "does not match the exact live pending ticket",
            "A rejected acknowledgement cannot change live density",
            "Backend.GetCurrentRevision(VolumeStableId), uint64(2)",
            "A rejected acknowledgement cannot promote a checkpoint base",
            "Backend.ExportOperationJournal(",
        ):
            self.assertIn(token, self.source)

    def test_export_proves_prefix_compaction_and_later_suffix_preservation(self):
        for token in (
            "Export.BaseCheckpointRevision, uint64(1)",
            "Export.ThroughRevision, uint64(2)",
            "Export.Operations.Num(), 1",
            "RemainingOperation.PreviousRevision, uint64(1)",
            "RemainingOperation.Revision, uint64(2)",
            "RemainingOperation.RequestSequence, uint64(2)",
            "FirstPersistenceRequest.Ticket.CheckpointJournalTailSha256",
            "Export.FinalJournalTailSha256",
            "RemainingOperation.CanonicalOperationSha256",
            "Backend.GetCurrentRevision(VolumeStableId), uint64(2)",
            "ValidateEditJournalExport(",
        ):
            self.assertIn(token, self.source)

    def test_duplicate_acknowledgement_must_leave_export_identity_unchanged(self):
        duplicate = self.source.index(
            "An exact duplicate acknowledgement is idempotent"
        )
        reexport = self.source.index("const bool bExportedAfterDuplicate")
        self.assertLess(duplicate, reexport)
        for token in (
            "ManifestBeforeDuplicate",
            "OperationBeforeDuplicate",
            "AfterDuplicate.CanonicalManifestSha256, ManifestBeforeDuplicate",
            "AfterDuplicate.Operations.Num(), 1",
            "AfterDuplicate.Operations[0].OperationId",
            "== OperationBeforeDuplicate",
        ):
            self.assertIn(token, self.source)

    def test_restore_scenario_establishes_a_real_base_and_later_suffix(self):
        body = self.restore_source
        first_capture = body.index("const bool bCapturedFirstCheckpoint")
        first_ack = body.index("const bool bAcknowledgedFirstCheckpoint")
        second_edit = body.index("const bool bSecondEditAccepted")
        pre_export = body.index("const bool bExportedPreRestoreSuffix")
        restore_capture = body.index(
            "const bool bCapturedPendingRestoreCheckpoint"
        )
        self.assertLess(first_capture, first_ack)
        self.assertLess(first_ack, second_edit)
        self.assertLess(second_edit, pre_export)
        self.assertLess(pre_export, restore_capture)
        for token in (
            "PreRestoreExport.BaseCheckpointRevision, uint64(1)",
            "PreRestoreExport.ThroughRevision, uint64(2)",
            "PreRestoreExport.Operations.Num(), 1",
            "PreRestoreExportManifest",
            "PreRestoreOperationId",
        ):
            self.assertIn(token, body)

    def test_corrupted_checkpoint_rejection_is_explicitly_atomic(self):
        body = self.restore_source
        corrupt = body.index("CompressedDensityAndMaterial.Last() ^=")
        inspect = body.index("const bool bInspectedCorruptedCheckpoint")
        restore = body.index("const bool bRestoredCorruptedCheckpoint")
        recapture = body.index("const bool bCapturedAfterCorruption")
        reexport = body.index("const bool bExportedAfterCorruption")
        pristine_restore = body.index(
            "const bool bRestoredPristineCheckpoint"
        )
        self.assertLess(corrupt, inspect)
        self.assertLess(inspect, restore)
        self.assertLess(restore, recapture)
        self.assertLess(recapture, reexport)
        self.assertLess(reexport, pristine_restore)
        for token in (
            "CompressedDensityAndMaterial.Last() ^=",
            "Captured checkpoint contains no payload to corrupt",
            "A payload-corrupted checkpoint fails bounded inspection",
            "A payload-corrupted checkpoint cannot replace live state",
            "Rejected corruption cannot change the live revision",
            "Rejected corruption cannot advance authority generation",
            "Rejected corruption cannot change the live manifest",
            "Rejected corruption preserves the export manifest",
            "Rejected corruption preserves suffix operation identity",
        ):
            self.assertIn(token, body)

    def test_exact_restore_advances_generation_and_invalidates_old_ticket(self):
        body = self.restore_source
        restore = body.index("const bool bRestoredPristineCheckpoint")
        prior_base_ack = body.index(
            "const bool bAcceptedPriorBaseAcknowledgement"
        )
        stale_ack = body.index("const bool bAcceptedStaleAcknowledgement")
        blocked_export = body.index(
            "const bool bExportedBeforeFreshAcknowledgement"
        )
        fresh_capture = body.index("const bool bCapturedFreshCheckpoint")
        self.assertLess(restore, prior_base_ack)
        self.assertLess(prior_base_ack, stale_ack)
        self.assertLess(stale_ack, blocked_export)
        self.assertLess(blocked_export, fresh_capture)
        for token in (
            "ECheckpointRestoreMode::ReplaceQuiescedVolume",
            "RestorePrecondition.ExpectedCurrentRevision = 2",
            "RestoreCheckpointSetAtomically(",
            "Exact restore preserves checkpoint revision",
            "Exact restore advances authority generation once",
            "Exact restore preserves checkpoint content identity",
            "Restore invalidates the previously acknowledged base ticket",
            "The prior base ticket is rejected as stale authority state",
            "Restore invalidates the pre-restore persistence ticket",
            "targets stale or foreign authority state",
            "requires an explicitly acknowledged checkpoint base",
        ):
            self.assertIn(token, body)

    def test_fresh_post_restore_ack_exports_an_empty_revision_two_base(self):
        body = self.restore_source
        fresh_capture = body.index("const bool bCapturedFreshCheckpoint")
        captured_only_export = body.index(
            "Capture alone cannot promote a durability base"
        )
        fresh_ack = body.index("const bool bAcknowledgedFreshCheckpoint")
        fresh_export = body.index("const bool bExportedFreshBaseline")
        validation = body.index("const bool bFreshExportValid")
        self.assertLess(fresh_capture, captured_only_export)
        self.assertLess(captured_only_export, fresh_ack)
        self.assertLess(fresh_ack, fresh_export)
        self.assertLess(fresh_export, validation)
        for token in (
            "FreshTicket.bExpectedAcknowledgedBase",
            "FreshTicket.ExpectedJournalBaseRevision, uint64(2)",
            "FreshTicket.ExpectedBaseCheckpointManifestSha256.IsEmpty()",
            "FreshTicket.ExpectedBaseJournalTailSha256.IsEmpty()",
            "FreshTicket.CheckpointJournalTailSha256.IsEmpty()",
            "Fresh persistence advances the request capability",
            "FreshBaselineExport.BaseCheckpointRevision, uint64(2)",
            "FreshBaselineExport.ThroughRevision, uint64(2)",
            "FreshBaselineExport.Operations.Num(), 0",
            "FreshBaselineExport.BaseCheckpointManifestSha256",
            "FreshTicket.CheckpointManifestSha256",
            "FreshBaselineExport.BaseJournalTailSha256.IsEmpty()",
            "FreshBaselineExport.FinalJournalTailSha256.IsEmpty()",
            "Fresh export identity differs from pre-restore suffix",
            "ValidateEditJournalExport(",
        ):
            self.assertIn(token, body)

    def test_reissue_supersedes_only_the_pending_capability_token(self):
        body = self.reissue_source
        base_capture = body.index("const bool bCapturedBaseRequest")
        base_ack = body.index("const bool bAcknowledgedBaseRequest")
        second_edit = body.index("const bool bSecondEditAccepted")
        pre_export = body.index("const bool bExportedPreReissueSuffix")
        first_capture = body.index("const bool bCapturedFirstRequest")
        reissue_capture = body.index("const bool bCapturedReissuedRequest")
        stale_ack = body.index("const bool bAcceptedSupersededTicket")
        exact_ack = body.index("const bool bAcknowledgedReissuedTicket")
        self.assertLess(base_capture, base_ack)
        self.assertLess(base_ack, second_edit)
        self.assertLess(second_edit, pre_export)
        self.assertLess(pre_export, first_capture)
        self.assertLess(first_capture, reissue_capture)
        self.assertLess(reissue_capture, stale_ack)
        self.assertLess(stale_ack, exact_ack)
        for token in (
            "ValidateCheckpointPersistenceRequest(",
            "Reissue preserves the exact target",
            "Reissue preserves the canonical volume spec",
            "Reissue preserves acknowledged-base expectation",
            "Reissue retains a real acknowledged durability base",
            "Reissue preserves the expected journal base revision",
            "Reissue expects the acknowledged revision-one base",
            "Reissue preserves the expected base checkpoint manifest",
            "Reissue binds the acknowledged base checkpoint manifest",
            "Reissue preserves the expected base journal tail",
            "Reissue binds the acknowledged base journal tail",
            "Reissue preserves the checkpoint revision",
            "Reissue checkpoint covers revision two",
            "Reissue preserves the checkpoint manifest",
            "Reissue preserves the checkpoint journal tail",
            "Reissue preserves the authority generation",
            "Reissue remains bound to the same backend instance",
            "Reissue advances its persistence capability token",
            "Reissue advances the capability token exactly once",
            "> FirstTicket.PersistenceRequestToken",
            "- FirstTicket.PersistenceRequestToken",
        ):
            self.assertIn(token, body)
        for expression in (
            "ReissuedTicket.TargetStableId, FirstTicket.TargetStableId",
            "ReissuedTicket.VolumeSpecSha256, FirstTicket.VolumeSpecSha256",
            (
                "ReissuedTicket.bExpectedAcknowledgedBase, "
                "FirstTicket.bExpectedAcknowledgedBase"
            ),
            (
                "ReissuedTicket.ExpectedJournalBaseRevision, "
                "FirstTicket.ExpectedJournalBaseRevision"
            ),
            (
                "ReissuedTicket.ExpectedBaseCheckpointManifestSha256, "
                "FirstTicket.ExpectedBaseCheckpointManifestSha256"
            ),
            (
                "ReissuedTicket.ExpectedBaseJournalTailSha256, "
                "FirstTicket.ExpectedBaseJournalTailSha256"
            ),
            (
                "ReissuedTicket.CheckpointThroughRevision, "
                "FirstTicket.CheckpointThroughRevision"
            ),
            (
                "ReissuedTicket.CheckpointManifestSha256, "
                "FirstTicket.CheckpointManifestSha256"
            ),
            (
                "ReissuedTicket.CheckpointJournalTailSha256, "
                "FirstTicket.CheckpointJournalTailSha256"
            ),
            (
                "ReissuedTicket.AuthorityGenerationToken, "
                "FirstTicket.AuthorityGenerationToken"
            ),
            (
                "ReissuedTicket.BackendInstanceId "
                "== FirstTicket.BackendInstanceId"
            ),
            (
                "ReissuedTicket.PersistenceRequestToken "
                "- FirstTicket.PersistenceRequestToken, uint64(1)"
            ),
        ):
            self.assertIn(expression, self.reissue_compact)

    def test_superseded_reissue_cannot_promote_or_mutate_live_state(self):
        body = self.reissue_source
        stale_ack = body.index("const bool bAcceptedSupersededTicket")
        blocked_export = body.index(
            "const bool bExportedAfterSupersededRejection"
        )
        exact_ack = body.index("const bool bAcknowledgedReissuedTicket")
        self.assertLess(stale_ack, blocked_export)
        self.assertLess(blocked_export, exact_ack)
        for token in (
            "The superseded persistence ticket is rejected",
            "does not match the exact live pending ticket",
            "Superseded rejection cannot change live revision",
            "Backend.GetCurrentRevision(VolumeStableId), uint64(2)",
            "Superseded rejection cannot move the durability base",
            "Superseded rejection cannot change export revision",
            "Superseded rejection cannot compact the live suffix",
            "Superseded rejection preserves export identity",
            "Superseded rejection preserves suffix operation identity",
            "PreReissueExportManifest",
            "PreReissueOperationId",
        ):
            self.assertIn(token, body)

    def test_exact_reissue_acknowledges_one_canonical_empty_suffix_base(self):
        body = self.reissue_source
        exact_ack = body.index("const bool bAcknowledgedReissuedTicket")
        export = body.index("const bool bExportedReissuedBaseline")
        validation = body.index("const bool bReissuedExportValid")
        self.assertLess(exact_ack, export)
        self.assertLess(export, validation)
        for token in (
            "The exact reissued persistence ticket is acknowledged",
            "ReissuedBaselineExport.BaseCheckpointRevision, uint64(2)",
            "ReissuedBaselineExport.ThroughRevision, uint64(2)",
            "ReissuedBaselineExport.Operations.Num(), 0",
            "ReissuedBaselineExport.BaseCheckpointManifestSha256",
            "ReissuedTicket.CheckpointManifestSha256",
            "ReissuedBaselineExport.BaseJournalTailSha256",
            "ReissuedBaselineExport.FinalJournalTailSha256",
            "ReissuedTicket.CheckpointJournalTailSha256",
            "ValidateEditJournalExport(",
            "The reissued baseline validates canonically",
        ):
            self.assertIn(token, body)

    def test_generated_output_scenario_is_bounded_and_uses_exact_roles(self):
        body = self.generated_output_source
        compact = self.generated_output_compact
        self.assertEqual(
            body.count("FRedInMemorySparseVoxelBackend Backend;"),
            1,
        )
        self.assertEqual(
            len(
                re.findall(
                    r"\bFRedInMemorySparseVoxelBackend\s+\w+\s*;",
                    body,
                )
            ),
            1,
        )
        self.assertEqual(
            body.count("Backend.InitializeVolume(Spec, Limits, Error)"),
            1,
        )
        self.assertEqual(body.count("Backend.ReadChunkRevision("), 4)
        self.assertEqual(body.count("Backend.QueueChunkRebuild("), 7)
        self.assertEqual(body.count("Backend.CompleteChunkRebuild("), 10)
        self.assertEqual(body.count("Backend.QueryGeneratedOutputState("), 15)
        self.assertEqual(body.count("ApplyAcceptedEdit("), 1)
        for forbidden in (
            "CaptureCheckpoint",
            "Persistence",
            "RestoreCheckpoint",
            "ReleaseVolume",
            "InvalidateBuildsOlderThan",
        ):
            self.assertNotIn(forbidden, body)
        for expression in (
            "const FIntVector TargetChunk(0, 0, 0)",
            "const FIntVector UnrelatedChunk(1, 0, 0)",
            (
                "Backend.QueueChunkRebuild( InitialTargetRevision, "
                "EGeneratedOutputRequirement::PresentationAndCollision, "
                "RejectedCombinedRequest, Error)"
            ),
            (
                'TestFalse(TEXT("One ticket cannot authorize both '
                'generated-output roles"), bQueuedCombinedRole)'
            ),
            (
                'TestEqual(TEXT("Rejected combined-role request remains '
                'default"), RejectedCombinedRequest.Ticket.'
                "BuildRequestToken, uint64(0))"
            ),
            (
                "Backend.QueueChunkRebuild( InitialTargetRevision, "
                "EGeneratedOutputRequirement::Presentation, "
                "InitialTargetPresentationRequest, Error)"
            ),
            (
                "Backend.QueueChunkRebuild( InitialTargetRevision, "
                "EGeneratedOutputRequirement::Collision, "
                "InitialTargetCollisionRequest, Error)"
            ),
            (
                "InitialTargetPresentationRequest.Ticket.OutputRole "
                "== EGeneratedOutputRequirement::Presentation"
            ),
            (
                "InitialTargetCollisionRequest.Ticket.OutputRole "
                "== EGeneratedOutputRequirement::Collision"
            ),
            (
                "InitialTargetCollisionRequest.Ticket.BuildRequestToken "
                "- InitialTargetPresentationRequest.Ticket.BuildRequestToken, "
                "uint64(1)"
            ),
            (
                "InitialTargetPresentationRequest.Ticket.BuildRequestToken, "
                "uint64(1)"
            ),
            (
                "UnrelatedPresentationRequest.Ticket.BuildRequestToken "
                "- InitialTargetCollisionRequest.Ticket.BuildRequestToken, "
                "uint64(1)"
            ),
            (
                "InitialTargetPresentationRequest.CanonicalDensityAndMaterial "
                "== InitialTargetCollisionRequest."
                "CanonicalDensityAndMaterial"
            ),
            (
                "AfterCombinedRoleRejection.TargetStableId "
                "== InitialTargetState.TargetStableId"
            ),
            (
                "AfterCombinedRoleRejection.ChunkCoordinate "
                "== InitialTargetState.ChunkCoordinate"
            ),
            (
                "AfterCombinedRoleRejection.ContentRevision "
                "== InitialTargetState.ContentRevision"
            ),
            (
                "AfterCombinedRoleRejection.ContentSha256 "
                "== InitialTargetState.ContentSha256"
            ),
            (
                "AfterCombinedRoleRejection.GenerationToken "
                "== InitialTargetState.GenerationToken"
            ),
            (
                "AfterCombinedRoleRejection.PresentationOutputSha256 "
                "== InitialTargetState.PresentationOutputSha256"
            ),
            (
                "AfterCombinedRoleRejection.CollisionOutputSha256 "
                "== InitialTargetState.CollisionOutputSha256"
            ),
            (
                'TestFalse(TEXT("Combined-role rejection cannot ready '
                'presentation"), AfterCombinedRoleRejection.'
                "bPresentationReady)"
            ),
            (
                'TestFalse(TEXT("Combined-role rejection cannot ready '
                'collision"), AfterCombinedRoleRejection.bCollisionReady)'
            ),
        ):
            self.assertIn(expression, compact)
        for expression in (
            (
                'TestTrue(TEXT("Presentation-only state satisfies '
                'presentation"), AreGeneratedOutputsCurrent( '
                "InitialTargetRevision, PresentationOnlyState, "
                "EGeneratedOutputRequirement::Presentation))"
            ),
            (
                'TestFalse(TEXT("Presentation-only state cannot satisfy '
                'collision"), AreGeneratedOutputsCurrent( '
                "InitialTargetRevision, PresentationOnlyState, "
                "EGeneratedOutputRequirement::Collision))"
            ),
            (
                'TestFalse(TEXT("Presentation-only state cannot satisfy '
                'both roles"), AreGeneratedOutputsCurrent( '
                "InitialTargetRevision, PresentationOnlyState, "
                "EGeneratedOutputRequirement::PresentationAndCollision))"
            ),
            (
                'TestTrue(TEXT("Initial exact completions satisfy both '
                'roles"), AreGeneratedOutputsCurrent( '
                "InitialTargetRevision, InitialBothRolesReadyState, "
                "EGeneratedOutputRequirement::"
                "PresentationAndCollision))"
            ),
        ):
            self.assertIn(expression, compact)
        digests = re.findall(
            (
                r"const FString \w+Sha256\(\s*"
                r'TEXT\("([0-9A-Fa-f]+)"\)\s*\);'
            ),
            body,
        )
        self.assertEqual(len(digests), 7)
        self.assertEqual(set(digests), {str(i) * 64 for i in range(1, 8)})

    def test_generated_output_presentation_completion_is_role_isolated(self):
        body = self.generated_output_source
        compact = self.generated_output_compact
        queue_presentation = body.index(
            "const bool bQueuedInitialTargetPresentation"
        )
        queue_collision = body.index(
            "const bool bQueuedInitialTargetCollision"
        )
        complete_presentation = body.index(
            "const bool bCompletedInitialTargetPresentation"
        )
        query_presentation = body.index(
            "const bool bQueriedPresentationOnlyState"
        )
        complete_collision = body.index(
            "const bool bCompletedInitialTargetCollision"
        )
        query_both = body.index(
            "const bool bQueriedInitialBothRolesReadyState"
        )
        target_edit = body.index("const bool bEditAccepted")
        self.assertLess(queue_presentation, queue_collision)
        self.assertLess(queue_collision, complete_presentation)
        self.assertLess(complete_presentation, query_presentation)
        self.assertLess(query_presentation, complete_collision)
        self.assertLess(complete_collision, query_both)
        self.assertLess(query_both, target_edit)
        for expression in (
            (
                "InitialTargetPresentationCompletion.Ticket "
                "= InitialTargetPresentationRequest.Ticket"
            ),
            (
                "InitialTargetPresentationCompletion.OutputSha256 "
                "= InitialTargetPresentationSha256"
            ),
            (
                "Backend.CompleteChunkRebuild( "
                "InitialTargetPresentationCompletion, Error)"
            ),
            (
                "PresentationOnlyState.bPresentationReady "
                "&& !PresentationOnlyState.bCollisionReady"
            ),
            (
                "PresentationOnlyState.PresentationOutputSha256, "
                "InitialTargetPresentationSha256"
            ),
            "PresentationOnlyState.CollisionOutputSha256.IsEmpty()",
            (
                "AreGeneratedOutputsCurrent( InitialTargetRevision, "
                "PresentationOnlyState, "
                "EGeneratedOutputRequirement::Presentation)"
            ),
            (
                "AreGeneratedOutputsCurrent( InitialTargetRevision, "
                "PresentationOnlyState, "
                "EGeneratedOutputRequirement::Collision)"
            ),
            (
                "AreGeneratedOutputsCurrent( InitialTargetRevision, "
                "PresentationOnlyState, "
                "EGeneratedOutputRequirement::PresentationAndCollision)"
            ),
            (
                "InitialTargetCollisionCompletion.Ticket "
                "= InitialTargetCollisionRequest.Ticket"
            ),
            (
                "InitialTargetCollisionCompletion.OutputSha256 "
                "= InitialTargetCollisionSha256"
            ),
            (
                "Backend.CompleteChunkRebuild( "
                "InitialTargetCollisionCompletion, Error)"
            ),
            (
                "InitialBothRolesReadyState.bPresentationReady "
                "&& InitialBothRolesReadyState.bCollisionReady"
            ),
            (
                "InitialBothRolesReadyState.PresentationOutputSha256, "
                "InitialTargetPresentationSha256"
            ),
            (
                "InitialBothRolesReadyState.CollisionOutputSha256, "
                "InitialTargetCollisionSha256"
            ),
            (
                "AreGeneratedOutputsCurrent( InitialTargetRevision, "
                "InitialBothRolesReadyState, "
                "EGeneratedOutputRequirement::PresentationAndCollision)"
            ),
        ):
            self.assertIn(expression, compact)

    def test_generated_output_edit_stales_target_but_not_unrelated_chunk(self):
        body = self.generated_output_source
        compact = self.generated_output_compact
        target_edit = body.index("const bool bEditAccepted")
        stale_presentation = body.index(
            "const bool bAcceptedStalePresentationCompletion"
        )
        stale_collision = body.index(
            "const bool bAcceptedStaleCollisionCompletion"
        )
        query_after_stale = body.index(
            "const bool bQueriedAfterStaleTargetCompletions"
        )
        complete_unrelated = body.index(
            "const bool bCompletedUnrelatedPresentation"
        )
        self.assertLess(target_edit, stale_presentation)
        self.assertLess(stale_presentation, stale_collision)
        self.assertLess(stale_collision, query_after_stale)
        self.assertLess(query_after_stale, complete_unrelated)
        for expression in (
            (
                "ApplyAcceptedEdit( Backend, 1, "
                "FVector(-250.0, -50.0, -50.0), EditResult, Error)"
            ),
            "EditResult.DirtyChunkCoordinates.Num(), 1",
            "EditResult.DirtyChunkCoordinates[0] == TargetChunk",
            "Backend.GetCurrentRevision(VolumeStableId), uint64(1)",
            (
                "UpdatedUnrelatedRevision.ContentRevision, "
                "InitialUnrelatedRevision.ContentRevision"
            ),
            (
                "UpdatedUnrelatedRevision.ContentSha256, "
                "InitialUnrelatedRevision.ContentSha256"
            ),
            (
                "Backend.CompleteChunkRebuild( "
                "InitialTargetPresentationCompletion, Error)"
            ),
            (
                "const bool bAcceptedStalePresentationCompletion = "
                "Backend.CompleteChunkRebuild( "
                "InitialTargetPresentationCompletion, Error); "
                'TestFalse(TEXT("The pre-edit presentation completion '
                'becomes stale"), bAcceptedStalePresentationCompletion)'
            ),
            (
                "Backend.CompleteChunkRebuild( "
                "InitialTargetCollisionCompletion, Error)"
            ),
            (
                "const bool bAcceptedStaleCollisionCompletion = "
                "Backend.CompleteChunkRebuild( "
                "InitialTargetCollisionCompletion, Error); "
                'TestFalse(TEXT("The pre-edit collision completion '
                'becomes stale"), bAcceptedStaleCollisionCompletion)'
            ),
            "completion is stale or does not match live authority",
            (
                "AfterStaleTargetCompletions."
                "PresentationOutputSha256.IsEmpty()"
            ),
            (
                "AfterStaleTargetCompletions."
                "CollisionOutputSha256.IsEmpty()"
            ),
            (
                "Backend.CompleteChunkRebuild( "
                "UnrelatedPresentationCompletion, Error)"
            ),
            (
                "UnrelatedAfterEditState.bPresentationReady "
                "&& !UnrelatedAfterEditState.bCollisionReady"
            ),
            (
                "UnrelatedAfterEditState.PresentationOutputSha256, "
                "UnrelatedPresentationSha256"
            ),
            (
                "AreGeneratedOutputsCurrent( InitialUnrelatedRevision, "
                "UnrelatedAfterEditState, "
                "EGeneratedOutputRequirement::Presentation)"
            ),
        ):
            self.assertIn(expression, compact)
        state_fields = (
            "TargetStableId",
            "ChunkCoordinate",
            "ContentRevision",
            "ContentSha256",
            "GenerationToken",
            "bPresentationReady",
            "bCollisionReady",
            "PresentationOutputSha256",
            "CollisionOutputSha256",
        )
        for field in state_fields:
            self.assertIn(
                (
                    f"AfterStalePresentationCompletion.{field} "
                    f"== EditedTargetState.{field}"
                ),
                compact,
            )
            self.assertIn(
                (
                    f"AfterStaleTargetCompletions.{field} "
                    f"== AfterStalePresentationCompletion.{field}"
                ),
                compact,
            )

    def test_generated_output_retry_supersedes_only_presentation_role(self):
        body = self.generated_output_source
        compact = self.generated_output_compact
        queue_presentation = body.index("const bool bQueuedFreshPresentation")
        queue_collision = body.index("const bool bQueuedFreshCollision")
        requeue_presentation = body.index(
            "const bool bRequeuedFreshPresentation"
        )
        query_before_reject = body.index(
            "const bool bQueriedBeforeSupersededPresentationCompletion"
        )
        reject_old = body.index(
            "const bool bAcceptedSupersededPresentation"
        )
        query_after_reject = body.index(
            "const bool bQueriedAfterSupersededPresentationCompletion"
        )
        complete_collision = body.index(
            "const bool bCompletedFreshCollision"
        )
        query_collision = body.index(
            "const bool bQueriedCollisionOnlyState"
        )
        complete_presentation = body.index(
            "const bool bCompletedFreshPresentation"
        )
        self.assertLess(queue_presentation, queue_collision)
        self.assertLess(queue_collision, requeue_presentation)
        self.assertLess(requeue_presentation, query_before_reject)
        self.assertLess(query_before_reject, reject_old)
        self.assertLess(reject_old, query_after_reject)
        self.assertLess(query_after_reject, complete_collision)
        self.assertLess(complete_collision, query_collision)
        self.assertLess(query_collision, complete_presentation)
        for expression in (
            (
                "FreshCollisionRequest.Ticket.BuildRequestToken "
                "- FreshPresentationRequest.Ticket.BuildRequestToken, "
                "uint64(1)"
            ),
            (
                "FreshPresentationRetryRequest.Ticket.BuildRequestToken "
                "- FreshCollisionRequest.Ticket.BuildRequestToken, "
                "uint64(1)"
            ),
            (
                "SupersededPresentationCompletion.Ticket "
                "= FreshPresentationRequest.Ticket"
            ),
            (
                "Backend.QueryGeneratedOutputState( VolumeStableId, "
                "TargetChunk, BeforeSupersededPresentationCompletion, Error)"
            ),
            (
                "const bool bAcceptedSupersededPresentation = "
                "Backend.CompleteChunkRebuild( "
                "SupersededPresentationCompletion, Error); "
                'TestFalse(TEXT("The superseded presentation attempt is '
                'rejected"), bAcceptedSupersededPresentation)'
            ),
            "completion ticket is not the active role attempt",
            (
                "Backend.QueryGeneratedOutputState( VolumeStableId, "
                "TargetChunk, AfterSupersededPresentationCompletion, Error)"
            ),
            (
                "FreshCollisionCompletion.Ticket "
                "= FreshCollisionRequest.Ticket"
            ),
            (
                "CollisionOnlyState.PresentationOutputSha256.IsEmpty()"
            ),
            (
                "CollisionOnlyState.CollisionOutputSha256, "
                "FreshCollisionSha256"
            ),
            (
                'TestFalse(TEXT("Collision-only state cannot satisfy '
                'presentation"), AreGeneratedOutputsCurrent( '
                "UpdatedTargetRevision, CollisionOnlyState, "
                "EGeneratedOutputRequirement::Presentation))"
            ),
            (
                'TestTrue(TEXT("Collision-only state satisfies collision"), '
                "AreGeneratedOutputsCurrent( UpdatedTargetRevision, "
                "CollisionOnlyState, "
                "EGeneratedOutputRequirement::Collision))"
            ),
            (
                'TestFalse(TEXT("Collision-only state cannot satisfy both '
                'roles"), AreGeneratedOutputsCurrent( '
                "UpdatedTargetRevision, CollisionOnlyState, "
                "EGeneratedOutputRequirement::PresentationAndCollision))"
            ),
            (
                "FreshPresentationCompletion.Ticket "
                "= FreshPresentationRetryRequest.Ticket"
            ),
            (
                "BothRolesReadyState.PresentationOutputSha256, "
                "FreshPresentationSha256"
            ),
            (
                "BothRolesReadyState.CollisionOutputSha256, "
                "FreshCollisionSha256"
            ),
            (
                'TestTrue(TEXT("The exact final state satisfies both roles"), '
                "AreGeneratedOutputsCurrent( UpdatedTargetRevision, "
                "BothRolesReadyState, EGeneratedOutputRequirement::"
                "PresentationAndCollision))"
            ),
        ):
            self.assertIn(expression, compact)
        state_fields = (
            "TargetStableId",
            "ChunkCoordinate",
            "ContentRevision",
            "ContentSha256",
            "GenerationToken",
            "bPresentationReady",
            "bCollisionReady",
            "PresentationOutputSha256",
            "CollisionOutputSha256",
        )
        for field in state_fields:
            self.assertIn(
                (
                    f"AfterSupersededPresentationCompletion.{field} "
                    f"== BeforeSupersededPresentationCompletion.{field}"
                ),
                compact,
            )

    def test_generated_output_duplicate_is_idempotent_and_conflict_atomic(self):
        body = self.generated_output_source
        compact = self.generated_output_compact
        complete = body.index("const bool bCompletedFreshPresentation")
        duplicate = body.index(
            "const bool bAcceptedDuplicatePresentation"
        )
        conflict = body.index(
            "const bool bAcceptedConflictingPresentation"
        )
        final_query = body.index("const bool bQueriedFinalTargetState")
        self.assertLess(complete, duplicate)
        self.assertLess(duplicate, conflict)
        self.assertLess(conflict, final_query)
        self.assertEqual(
            compact.count(
                "Backend.CompleteChunkRebuild( "
                "FreshPresentationCompletion, Error)"
            ),
            2,
        )
        for expression in (
            (
                "const bool bAcceptedDuplicatePresentation = "
                "Backend.CompleteChunkRebuild( "
                "FreshPresentationCompletion, Error); TestTrue( "
                'FString::Printf( TEXT("An exact duplicate presentation '
                'completion is idempotent: %s"), *Error), '
                "bAcceptedDuplicatePresentation)"
            ),
            (
                "ConflictingPresentationCompletion "
                "= FreshPresentationCompletion"
            ),
            (
                "ConflictingPresentationCompletion.OutputSha256 "
                "= ConflictingPresentationSha256"
            ),
            (
                "const bool bAcceptedConflictingPresentation = "
                "Backend.CompleteChunkRebuild( "
                "ConflictingPresentationCompletion, Error); "
                'TestFalse(TEXT("A conflicting duplicate presentation is '
                'rejected"), bAcceptedConflictingPresentation)'
            ),
            "completion conflicts with the accepted role output",
            (
                "FinalTargetState.bPresentationReady "
                "&& FinalTargetState.bCollisionReady"
            ),
            (
                "FinalTargetState.PresentationOutputSha256, "
                "FreshPresentationSha256"
            ),
            (
                "FinalTargetState.CollisionOutputSha256, "
                "FreshCollisionSha256"
            ),
            (
                'TestTrue(TEXT("Duplicate callbacks preserve exact current '
                'identity"), AreGeneratedOutputsCurrent( '
                "UpdatedTargetRevision, FinalTargetState, "
                "EGeneratedOutputRequirement::PresentationAndCollision))"
            ),
        ):
            self.assertIn(expression, compact)
        state_fields = (
            "TargetStableId",
            "ChunkCoordinate",
            "ContentRevision",
            "ContentSha256",
            "GenerationToken",
            "bPresentationReady",
            "bCollisionReady",
            "PresentationOutputSha256",
            "CollisionOutputSha256",
        )
        for field in state_fields:
            self.assertIn(
                (
                    f"AfterDuplicatePresentation.{field} "
                    f"== BothRolesReadyState.{field}"
                ),
                compact,
            )
            self.assertIn(
                (
                    f"FinalTargetState.{field} "
                    f"== AfterDuplicatePresentation.{field}"
                ),
                compact,
            )

    def test_deterministic_initialization_is_bounded_and_twin_instanced(self):
        body = self.deterministic_init_source
        compact = self.deterministic_init_compact
        first_init = body.index("const bool bFirstInitialized")
        second_init = body.index("const bool bSecondInitialized")
        first_checkpoint = body.index(
            "const bool bCapturedFirstCheckpoint"
        )
        second_checkpoint = body.index(
            "const bool bCapturedSecondCheckpoint"
        )
        self.assertLess(first_init, second_init)
        self.assertLess(second_init, first_checkpoint)
        self.assertLess(first_checkpoint, second_checkpoint)
        self.assertEqual(
            body.count(
                "FRedInMemorySparseVoxelBackend FirstBackend;"
            ),
            1,
        )
        self.assertEqual(
            body.count(
                "FRedInMemorySparseVoxelBackend SecondBackend;"
            ),
            1,
        )
        self.assertEqual(
            len(
                re.findall(
                    r"\bFRedInMemorySparseVoxelBackend\s+\w+\s*;",
                    body,
                )
            ),
            2,
        )
        self.assertEqual(body.count(".InitializeVolume("), 3)
        for forbidden in (
            "ApplyValidatedEdit",
            "CompleteChunkRebuild",
            "CaptureCheckpointForPersistence",
            "AcknowledgePersistedCheckpoint",
            "ExportOperationJournal",
            "RestoreCheckpointSetAtomically",
            "ReleaseVolume",
            "InvalidateBuildsOlderThan",
            "MaxJournalOperationsPerCheckpoint",
        ):
            self.assertNotIn(forbidden, body)
        for expression in (
            "FVolumeSpec Spec = MakeVolumeSpec()",
            (
                "ComputeCanonicalVolumeSpecSha256("
                "Spec, CanonicalSpecSha256)"
            ),
            "Spec.CanonicalSpecSha256 = MoveTemp(CanonicalSpecSha256)",
            "FRedInMemorySparseVoxelBackend FirstBackend",
            "FRedInMemorySparseVoxelBackend SecondBackend",
            "FirstBackend.InitializeVolume(Spec, Limits, Error)",
            "SecondBackend.InitializeVolume(Spec, Limits, Error)",
            "FirstBackend.HasVolume(VolumeStableId)",
            "SecondBackend.HasVolume(VolumeStableId)",
            (
                "FirstBackend.GetCurrentRevision(VolumeStableId), "
                "uint64(0)"
            ),
            (
                "SecondBackend.GetCurrentRevision(VolumeStableId), "
                "uint64(0)"
            ),
            "FirstGeneration > uint64(0) && FirstGeneration == SecondGeneration",
            (
                "(Spec.VolumeCellDimensions.X / "
                "Spec.ChunkCellDimensions.X)"
            ),
            "ExpectedChunkCount, 8",
            "FirstCheckpoint.Chunks.Num(), ExpectedChunkCount",
            "SecondCheckpoint.Chunks.Num(), ExpectedChunkCount",
        ):
            self.assertIn(expression, compact)

    def test_deterministic_initialization_matches_all_chunk_content(self):
        compact = self.deterministic_init_compact
        for expression in (
            (
                "for (int32 ChunkIndex = 0; "
                "ChunkIndex < ExpectedChunkCount; ++ChunkIndex)"
            ),
            (
                "FirstCheckpoint.CanonicalManifestSha256, "
                "SecondCheckpoint.CanonicalManifestSha256"
            ),
            (
                "FirstChunk.ChunkCoordinate "
                "== SecondChunk.ChunkCoordinate"
            ),
            (
                "FirstChunk.CanonicalPayloadSha256 "
                "== SecondChunk.CanonicalPayloadSha256"
            ),
            (
                "FirstChunk.CompressedDensityAndMaterial "
                "== SecondChunk.CompressedDensityAndMaterial"
            ),
            (
                "FirstBackend.ReadChunkRevision( VolumeStableId, "
                "FirstChunk.ChunkCoordinate, FirstRevision, Error)"
            ),
            (
                "SecondBackend.ReadChunkRevision( VolumeStableId, "
                "SecondChunk.ChunkCoordinate, SecondRevision, Error)"
            ),
            (
                "FirstRevision.TargetStableId "
                "== SecondRevision.TargetStableId"
            ),
            (
                "FirstRevision.ChunkCoordinate "
                "== SecondRevision.ChunkCoordinate"
            ),
            (
                "FirstRevision.ContentRevision "
                "== SecondRevision.ContentRevision"
            ),
            (
                "FirstRevision.ContentSha256 "
                "== SecondRevision.ContentSha256"
            ),
            (
                "FirstRevision.GenerationToken "
                "== SecondRevision.GenerationToken"
            ),
            "FirstRevision.ContentRevision, uint64(0)",
            "IsCanonicalSha256(FirstRevision.ContentSha256)",
        ):
            self.assertIn(expression, compact)

    def test_duplicate_initialization_rejection_is_atomic(self):
        body = self.deterministic_init_source
        compact = self.deterministic_init_compact
        baseline = body.index("const uint64 RevisionBeforeDuplicate")
        duplicate = body.index("const bool bDuplicateInitialized")
        recapture = body.index("const bool bCapturedAfterDuplicate")
        queue_after_rejection = body.index("const bool bQueuedFirstBuild")
        self.assertLess(baseline, duplicate)
        self.assertLess(duplicate, recapture)
        self.assertLess(recapture, queue_after_rejection)
        for expression in (
            (
                "const bool bDuplicateInitialized = "
                "FirstBackend.InitializeVolume("
                "Spec, Limits, DuplicateError)"
            ),
            (
                'TestFalse(TEXT("Duplicate initialization of one stable ID '
                'is rejected"), bDuplicateInitialized)'
            ),
            "a volume with this stable ID already exists",
            (
                "FirstBackend.GetCurrentRevision(VolumeStableId), "
                "RevisionBeforeDuplicate"
            ),
            (
                "FirstBackend.GetAuthorityGenerationToken(VolumeStableId), "
                "GenerationBeforeDuplicate"
            ),
            (
                "AfterDuplicateCheckpoint.CanonicalManifestSha256, "
                "ManifestBeforeDuplicate"
            ),
            (
                "AfterDuplicateCheckpoint.Chunks.Num(), "
                "FirstCheckpoint.Chunks.Num()"
            ),
            (
                "for (int32 ChunkIndex = 0; "
                "ChunkIndex < FirstCheckpoint.Chunks.Num(); "
                "++ChunkIndex)"
            ),
            (
                "AfterChunk.ChunkCoordinate "
                "== BeforeChunk.ChunkCoordinate"
            ),
            (
                "AfterChunk.ThroughRevision "
                "== BeforeChunk.ThroughRevision"
            ),
            (
                "AfterChunk.CanonicalPayloadSha256 "
                "== BeforeChunk.CanonicalPayloadSha256"
            ),
            (
                "AfterChunk.CompressedDensityAndMaterial "
                "== BeforeChunk.CompressedDensityAndMaterial"
            ),
            (
                "SecondBackend.ReadChunkRevision( VolumeStableId, "
                "BeforeChunk.ChunkCoordinate, BaselineRevision, Error)"
            ),
            (
                "FirstBackend.ReadChunkRevision( VolumeStableId, "
                "AfterChunk.ChunkCoordinate, "
                "AfterDuplicateRevision, Error)"
            ),
            (
                "AfterDuplicateRevision.TargetStableId "
                "== BaselineRevision.TargetStableId"
            ),
            (
                "AfterDuplicateRevision.ChunkCoordinate "
                "== BaselineRevision.ChunkCoordinate"
            ),
            (
                "AfterDuplicateRevision.ContentRevision "
                "== BaselineRevision.ContentRevision"
            ),
            (
                "AfterDuplicateRevision.ContentSha256 "
                "== BaselineRevision.ContentSha256"
            ),
            (
                "AfterDuplicateRevision.GenerationToken "
                "== BaselineRevision.GenerationToken"
            ),
            "FirstBuildRequest.Ticket.BuildRequestToken == uint64(1)",
        ):
            self.assertIn(expression, compact)

    def test_deterministic_initialization_yields_identical_build_snapshots(self):
        body = self.deterministic_init_source
        compact = self.deterministic_init_compact
        first_read = body.index("const bool bReadFirstSnapshotRevision")
        second_read = body.index("const bool bReadSecondSnapshotRevision")
        first_queue = body.index("const bool bQueuedFirstBuild")
        second_queue = body.index("const bool bQueuedSecondBuild")
        self.assertLess(first_read, second_read)
        self.assertLess(second_read, first_queue)
        self.assertLess(first_queue, second_queue)
        for expression in (
            "const FIntVector SnapshotChunk(0, 0, 0)",
            (
                "FirstBackend.QueueChunkRebuild( "
                "FirstSnapshotRevision, "
                "EGeneratedOutputRequirement::Presentation, "
                "FirstBuildRequest, Error)"
            ),
            (
                "SecondBackend.QueueChunkRebuild( "
                "SecondSnapshotRevision, "
                "EGeneratedOutputRequirement::Presentation, "
                "SecondBuildRequest, Error)"
            ),
            "ValidateGeneratedChunkBuildTicket(",
            (
                "FirstBuildRequest.CanonicalDensityAndMaterial "
                "== SecondBuildRequest.CanonicalDensityAndMaterial"
            ),
            (
                "FirstBuildRequest.Ticket.SourceRevision.ContentSha256 "
                "== SecondBuildRequest.Ticket.SourceRevision.ContentSha256"
            ),
            (
                "FirstBuildRequest.Ticket.VolumeSpecSha256 "
                "== SecondBuildRequest.Ticket.VolumeSpecSha256"
            ),
            (
                "FirstBuildRequest.Ticket.OutputRole "
                "== SecondBuildRequest.Ticket.OutputRole"
            ),
            (
                "FirstBuildRequest.Ticket.BuildProfileId "
                "== SecondBuildRequest.Ticket.BuildProfileId"
            ),
            (
                "FirstBuildRequest.Ticket.BuildProfileVersion "
                "== SecondBuildRequest.Ticket.BuildProfileVersion"
            ),
            (
                "FirstBuildRequest.Ticket.BackendInstanceId.IsValid()"
            ),
            (
                "SecondBuildRequest.Ticket.BackendInstanceId.IsValid()"
            ),
            (
                "FirstBuildRequest.Ticket.BackendInstanceId "
                "!= SecondBuildRequest.Ticket.BackendInstanceId"
            ),
            (
                "ComputeCanonicalSha256( "
                "FirstBuildRequest.CanonicalDensityAndMaterial.GetData(), "
                "FirstBuildRequest.CanonicalDensityAndMaterial.Num(), "
                "FirstBuildPayloadSha256)"
            ),
            (
                "ComputeCanonicalSha256( "
                "SecondBuildRequest.CanonicalDensityAndMaterial.GetData(), "
                "SecondBuildRequest.CanonicalDensityAndMaterial.Num(), "
                "SecondBuildPayloadSha256)"
            ),
            (
                "FirstBuildPayloadSha256 "
                "== FirstSnapshotCheckpoint->CanonicalPayloadSha256"
            ),
            (
                "SecondBuildPayloadSha256 "
                "== SecondSnapshotCheckpoint->CanonicalPayloadSha256"
            ),
            (
                "FirstBuildPayloadSha256 "
                "== SecondBuildPayloadSha256"
            ),
        ):
            self.assertIn(expression, compact)

    def test_deterministic_build_queue_cannot_fake_readiness_or_mutate_content(
        self,
    ):
        compact = self.deterministic_init_compact
        for expression in (
            (
                "FirstBackend.QueryGeneratedOutputState( "
                "VolumeStableId, SnapshotChunk, FirstOutputState, Error)"
            ),
            (
                "SecondBackend.QueryGeneratedOutputState( "
                "VolumeStableId, SnapshotChunk, SecondOutputState, Error)"
            ),
            "!FirstOutputState.bPresentationReady",
            "!FirstOutputState.bCollisionReady",
            "!SecondOutputState.bPresentationReady",
            "!SecondOutputState.bCollisionReady",
            "FirstOutputState.PresentationOutputSha256.IsEmpty()",
            "FirstOutputState.CollisionOutputSha256.IsEmpty()",
            "SecondOutputState.PresentationOutputSha256.IsEmpty()",
            "SecondOutputState.CollisionOutputSha256.IsEmpty()",
            (
                "FirstBackend.GetCurrentRevision(VolumeStableId), "
                "uint64(0)"
            ),
            (
                "SecondBackend.GetCurrentRevision(VolumeStableId), "
                "uint64(0)"
            ),
            (
                "AfterBuildRequestCheckpoint.CanonicalManifestSha256, "
                "ManifestBeforeDuplicate"
            ),
        ):
            self.assertIn(expression, compact)

    def test_multi_volume_scenario_is_bounded_and_distinct(self):
        body = self.multi_volume_source
        compact = self.multi_volume_compact
        self.assertEqual(
            len(
                re.findall(
                    r"\bFRedInMemorySparseVoxelBackend\s+\w+\s*;",
                    body,
                )
            ),
            1,
        )
        self.assertEqual(body.count("Backend.InitializeVolume("), 2)
        self.assertEqual(body.count("Backend.ApplyValidatedEdit("), 3)
        self.assertEqual(body.count("Backend.QueueChunkRebuild("), 3)
        self.assertEqual(body.count("Backend.CompleteChunkRebuild("), 4)
        self.assertEqual(
            body.count("Backend.CaptureCheckpointForPersistence("),
            2,
        )
        self.assertEqual(
            body.count("Backend.AcknowledgePersistedCheckpoint("),
            4,
        )
        first_hash = body.index("const bool bFirstFingerprintComputed")
        second_hash = body.index("const bool bSecondFingerprintComputed")
        first_init = body.index("const bool bFirstInitialized")
        second_init = body.index("const bool bSecondInitialized")
        self.assertLess(first_hash, second_hash)
        self.assertLess(second_hash, first_init)
        self.assertLess(first_init, second_init)
        for expression in (
            'TEXT("asteroid.red.m12.multi-volume-a")',
            'TEXT("asteroid.red.m12.multi-volume-b")',
            "FVolumeSpec FirstSpec = MakeVolumeSpec()",
            "FirstSpec.StableId = FirstVolumeStableId",
            "FVolumeSpec SecondSpec = MakeVolumeSpec()",
            "SecondSpec.StableId = SecondVolumeStableId",
            "SecondSpec.BaseSeed = 0x4D31324BU",
            (
                "ComputeCanonicalVolumeSpecSha256( "
                "FirstSpec, FirstCanonicalSpecSha256)"
            ),
            (
                "ComputeCanonicalVolumeSpecSha256( "
                "SecondSpec, SecondCanonicalSpecSha256)"
            ),
            (
                "FirstSpec.CanonicalSpecSha256 "
                "!= SecondSpec.CanonicalSpecSha256"
            ),
            "FRedInMemorySparseVoxelBackend Backend",
            "Backend.InitializeVolume(FirstSpec, Limits, Error)",
            "Backend.InitializeVolume(SecondSpec, Limits, Error)",
            "Backend.HasVolume(FirstVolumeStableId)",
            "Backend.HasVolume(SecondVolumeStableId)",
            (
                "Backend.GetCurrentRevision(FirstVolumeStableId) "
                "== uint64(0)"
            ),
            (
                "Backend.GetCurrentRevision(SecondVolumeStableId) "
                "== uint64(0)"
            ),
            (
                "const uint64 FirstAuthorityGeneration = "
                "Backend.GetAuthorityGenerationToken( "
                "FirstVolumeStableId)"
            ),
            (
                "const uint64 SecondAuthorityGeneration = "
                "Backend.GetAuthorityGenerationToken( "
                "SecondVolumeStableId)"
            ),
            "FirstAuthorityGeneration > uint64(0)",
            "SecondAuthorityGeneration > uint64(0)",
        ):
            self.assertIn(expression, compact)

    def test_multi_volume_edit_preserves_the_other_volume_exactly(self):
        body = self.multi_volume_source
        compact = self.multi_volume_compact
        first_baseline = body.index("const bool bCapturedFirstBeforeEdit")
        second_baseline = body.index("const bool bCapturedSecondBeforeEdit")
        apply_edit = body.index("const bool bFirstEditAccepted")
        first_after = body.index("const bool bCapturedFirstAfterEdit")
        second_after = body.index(
            "const bool bCapturedSecondAfterFirstEdit"
        )
        cross_edit = body.index("const bool bCrossVolumeEditHandled")
        cross_capture = body.index(
            "const bool bCapturedFirstAfterCrossEdit"
        )
        second_edit = body.index("const bool bSecondEditAccepted")
        second_capture = body.index(
            "const bool bCapturedFirstAfterSecondEdit"
        )
        second_export = body.index(
            "const bool bExportedFirstAfterSecondEdit"
        )
        self.assertLess(first_baseline, second_baseline)
        self.assertLess(second_baseline, apply_edit)
        self.assertLess(apply_edit, first_after)
        self.assertLess(first_after, second_after)
        self.assertLess(second_after, cross_edit)
        self.assertLess(cross_edit, cross_capture)
        self.assertLess(cross_capture, second_edit)
        self.assertLess(second_edit, second_capture)
        self.assertLess(second_capture, second_export)
        for expression in (
            "FirstEdit.TargetStableId = FirstVolumeStableId",
            "FirstEdit.RequestSequence = 1",
            "FirstEdit.ExpectedRevision = 0",
            (
                "FirstEdit.AuthorityGenerationToken = "
                "Backend.GetAuthorityGenerationToken( "
                "FirstVolumeStableId)"
            ),
            (
                "Backend.ApplyValidatedEdit( "
                "FirstEdit, FirstEditResult, Error)"
            ),
            "bFirstEditAccepted && FirstEditResult.bAccepted",
            (
                "FirstEditResult.TargetStableId "
                "== FirstVolumeStableId"
            ),
            "FirstEditResult.PreviousRevision == uint64(0)",
            "FirstEditResult.AppliedRevision == uint64(1)",
            "FirstEditResult.TotalRemovedCellCount == 1",
            (
                "Backend.GetCurrentRevision(FirstVolumeStableId), "
                "uint64(1)"
            ),
            (
                "Backend.GetCurrentRevision(SecondVolumeStableId), "
                "uint64(0)"
            ),
            (
                "FirstAfterEditCheckpoint.CanonicalManifestSha256 "
                "!= FirstBeforeEditCheckpoint.CanonicalManifestSha256"
            ),
            (
                "SecondAfterFirstEditCheckpoint.CanonicalManifestSha256 "
                "== SecondBeforeEditCheckpoint.CanonicalManifestSha256"
            ),
            (
                "for (int32 ChunkIndex = 0; "
                "ChunkIndex < SecondBeforeEditCheckpoint.Chunks.Num(); "
                "++ChunkIndex)"
            ),
            "AfterChunk.TargetStableId == BeforeChunk.TargetStableId",
            (
                "AfterChunk.ChunkCoordinate "
                "== BeforeChunk.ChunkCoordinate"
            ),
            "AfterChunk.ThroughRevision == BeforeChunk.ThroughRevision",
            (
                "AfterChunk.CanonicalPayloadSha256 "
                "== BeforeChunk.CanonicalPayloadSha256"
            ),
            (
                "AfterChunk.CompressedDensityAndMaterial "
                "== BeforeChunk.CompressedDensityAndMaterial"
            ),
            (
                "SecondAfterFirstEditRevision.ContentSha256 "
                "== SecondBeforeEditRevision.ContentSha256"
            ),
            (
                "SecondAfterFirstEditRevision.GenerationToken "
                "== SecondBeforeEditRevision.GenerationToken"
            ),
            (
                "SecondAfterFirstEditOutput.TargetStableId "
                "== SecondBeforeEditOutput.TargetStableId"
            ),
            (
                "SecondAfterFirstEditOutput.ChunkCoordinate "
                "== SecondBeforeEditOutput.ChunkCoordinate"
            ),
            (
                "SecondAfterFirstEditOutput.ContentRevision "
                "== SecondBeforeEditOutput.ContentRevision"
            ),
            (
                "SecondAfterFirstEditOutput.ContentSha256 "
                "== SecondBeforeEditOutput.ContentSha256"
            ),
            (
                "SecondAfterFirstEditOutput.GenerationToken "
                "== SecondBeforeEditOutput.GenerationToken"
            ),
            "!SecondAfterFirstEditOutput.bPresentationReady",
            "!SecondAfterFirstEditOutput.bCollisionReady",
            (
                "SecondAfterFirstEditOutput."
                "PresentationOutputSha256.IsEmpty()"
            ),
            (
                "SecondAfterFirstEditOutput."
                "CollisionOutputSha256.IsEmpty()"
            ),
            "FValidatedEdit CrossVolumeEdit = FirstEdit",
            (
                "CrossVolumeEdit.TargetStableId "
                "= SecondVolumeStableId"
            ),
            "CrossVolumeEdit.RequestSequence = 1",
            (
                "CrossVolumeEdit.ExpectedRevision "
                "= FirstEditResult.AppliedRevision"
            ),
            (
                "CrossVolumeEdit.AuthorityGenerationToken "
                "= SecondAuthorityGeneration"
            ),
            (
                "Backend.ApplyValidatedEdit( "
                "CrossVolumeEdit, CrossVolumeEditResult, Error)"
            ),
            "bCrossVolumeEditHandled",
            (
                'TestFalse( TEXT("A first-volume revision cannot authorize '
                'a second-volume edit"), CrossVolumeEditResult.bAccepted)'
            ),
            "CrossVolumeEditResult.TargetStableId == SecondVolumeStableId",
            (
                "CrossVolumeEditResult.RequestSequence "
                "== CrossVolumeEdit.RequestSequence"
            ),
            (
                "CrossVolumeEditResult.PredictionToken "
                "== CrossVolumeEdit.PredictionToken"
            ),
            (
                "CrossVolumeEditResult.AuthorityGenerationToken "
                "== CrossVolumeEdit.AuthorityGenerationToken"
            ),
            (
                "CrossVolumeEditResult.RejectReason "
                "== EEditRejectReason::StaleRevision"
            ),
            (
                "CrossVolumeEditResult.PreviousRevision "
                "== CrossVolumeEdit.ExpectedRevision"
            ),
            (
                "CrossVolumeEditResult.AppliedRevision "
                "== CrossVolumeEdit.ExpectedRevision"
            ),
            "CrossVolumeEditResult.TotalRemovedCellCount == 0",
            "CrossVolumeEditResult.MaterialYields.IsEmpty()",
            "CrossVolumeEditResult.DirtyChunkCoordinates.IsEmpty()",
            (
                "FirstAfterCrossEditCheckpoint.CanonicalManifestSha256 "
                "== FirstAfterEditCheckpoint.CanonicalManifestSha256"
            ),
            (
                "SecondAfterCrossEditCheckpoint.CanonicalManifestSha256 "
                "== SecondAfterFirstEditCheckpoint."
                "CanonicalManifestSha256"
            ),
            "FValidatedEdit SecondEdit = FirstEdit",
            "SecondEdit.TargetStableId = SecondVolumeStableId",
            "SecondEdit.RequestSequence = 1",
            "SecondEdit.ExpectedRevision = 0",
            (
                "SecondEdit.AuthorityGenerationToken "
                "= SecondAuthorityGeneration"
            ),
            (
                "Backend.ApplyValidatedEdit( "
                "SecondEdit, SecondEditResult, Error)"
            ),
            "bSecondEditAccepted && SecondEditResult.bAccepted",
            (
                "SecondEditResult.TargetStableId "
                "== SecondVolumeStableId"
            ),
            "SecondEditResult.RequestSequence == uint64(1)",
            (
                "SecondEditResult.PredictionToken "
                "== SecondEdit.PredictionToken"
            ),
            (
                "SecondEditResult.AuthorityGenerationToken "
                "== SecondAuthorityGeneration"
            ),
            (
                "SecondEditResult.RejectReason "
                "== EEditRejectReason::None"
            ),
            "SecondEditResult.PreviousRevision == uint64(0)",
            "SecondEditResult.AppliedRevision == uint64(1)",
            "SecondEditResult.TotalRemovedCellCount == 1",
            (
                "SecondAfterOwnEditOutput.TargetStableId "
                "== SecondVolumeStableId"
            ),
            (
                "SecondAfterOwnEditOutput.ChunkCoordinate "
                "== TargetChunk"
            ),
            (
                "SecondAfterOwnEditOutput.ContentRevision "
                "== uint64(1)"
            ),
            (
                "IsCanonicalSha256( "
                "SecondAfterOwnEditOutput.ContentSha256)"
            ),
            (
                "SecondAfterOwnEditOutput.ContentSha256 "
                "!= SecondAfterFirstEditRevision.ContentSha256"
            ),
            (
                "SecondAfterOwnEditOutput.GenerationToken "
                "== SecondAuthorityGeneration"
            ),
            "!SecondAfterOwnEditOutput.bPresentationReady",
            "!SecondAfterOwnEditOutput.bCollisionReady",
            (
                "SecondAfterOwnEditOutput."
                "PresentationOutputSha256.IsEmpty()"
            ),
            (
                "SecondAfterOwnEditOutput."
                "CollisionOutputSha256.IsEmpty()"
            ),
            (
                "FirstAfterSecondEditCheckpoint."
                "CanonicalManifestSha256 "
                "== FirstFinalCheckpoint.CanonicalManifestSha256"
            ),
            (
                "SecondAfterOwnEditCheckpoint."
                "CanonicalManifestSha256 "
                "!= SecondFinalCheckpoint.CanonicalManifestSha256"
            ),
            (
                "Backend.GetCurrentRevision(FirstVolumeStableId) "
                "== uint64(1)"
            ),
            (
                "Backend.GetCurrentRevision(SecondVolumeStableId) "
                "== uint64(1)"
            ),
            (
                "Backend.ExportOperationJournal( "
                "FirstVolumeStableId, FirstAfterSecondEditExport, Error)"
            ),
            (
                "Backend.ExportOperationJournal( "
                "SecondVolumeStableId, SecondAfterOwnEditExport, Error)"
            ),
            (
                "ValidateEditJournalExport( "
                "FirstAfterSecondEditExport, Limits, "
                "&FirstAfterSecondEditExportValidationError)"
            ),
            (
                "ValidateEditJournalExport( "
                "SecondAfterOwnEditExport, Limits, "
                "&SecondAfterOwnEditExportValidationError)"
            ),
            (
                "SecondAfterOwnEditExport.Operations.Num(), 1"
            ),
            (
                "const FEditOperation& SecondOwnedOperation "
                "= SecondAfterOwnEditExport.Operations[0]"
            ),
            (
                "SecondAfterOwnEditExport.TargetStableId "
                "== SecondVolumeStableId"
            ),
            (
                "SecondAfterOwnEditExport.VolumeSpecSha256 "
                "== SecondSpec.CanonicalSpecSha256"
            ),
            (
                "SecondAfterOwnEditExport.BaseCheckpointRevision "
                "== uint64(0)"
            ),
            (
                "SecondAfterOwnEditExport."
                "BaseCheckpointManifestSha256 "
                "== SecondPersistenceRequest.Ticket."
                "CheckpointManifestSha256"
            ),
            (
                "SecondAfterOwnEditExport.BaseJournalTailSha256 "
                "== SecondPersistenceRequest.Ticket."
                "CheckpointJournalTailSha256"
            ),
            (
                "SecondAfterOwnEditExport.ThroughRevision "
                "== uint64(1)"
            ),
            (
                "SecondOwnedOperation.TargetStableId "
                "== SecondVolumeStableId"
            ),
            (
                "SecondOwnedOperation.VolumeSpecSha256 "
                "== SecondSpec.CanonicalSpecSha256"
            ),
            "SecondOwnedOperation.PreviousRevision == uint64(0)",
            "SecondOwnedOperation.Revision == uint64(1)",
            "SecondOwnedOperation.RequestSequence == uint64(1)",
            (
                "SecondOwnedOperation.PredictionToken "
                "== SecondEdit.PredictionToken"
            ),
            (
                "SecondAfterOwnEditExport.FinalJournalTailSha256 "
                "== SecondOwnedOperation.CanonicalOperationSha256"
            ),
        ):
            self.assertIn(expression, compact)
        output_fields = (
            "TargetStableId",
            "ChunkCoordinate",
            "ContentRevision",
            "ContentSha256",
            "GenerationToken",
            "bPresentationReady",
            "bCollisionReady",
            "PresentationOutputSha256",
            "CollisionOutputSha256",
        )
        for field in output_fields:
            self.assertIn(
                (
                    f"FirstAfterSecondEditOutput.{field} "
                    f"== FirstBeforeSecondEditOutput.{field}"
                ),
                compact,
            )
        for field in (
            "TargetStableId",
            "VolumeSpecSha256",
            "BaseCheckpointRevision",
            "BaseCheckpointManifestSha256",
            "BaseJournalTailSha256",
            "ThroughRevision",
            "FinalJournalTailSha256",
            "CanonicalManifestSha256",
        ):
            self.assertIn(
                (
                    f"FirstAfterSecondEditExport.{field} "
                    f"== FirstAfterSecondAcknowledgement.{field}"
                ),
                compact,
            )
        self.assertIn(
            (
                "FirstAfterSecondEditExport.Operations.Num() "
                "== FirstAfterSecondAcknowledgement.Operations.Num()"
            ),
            compact,
        )

    def test_multi_volume_build_capabilities_are_volume_local_and_atomic(
        self,
    ):
        body = self.multi_volume_source
        compact = self.multi_volume_compact
        rejected_queue = body.index(
            "const bool bQueuedCrossVolumeRequest"
        )
        first_queue = body.index("const bool bQueuedFirstPresentation")
        second_queue = body.index("const bool bQueuedSecondPresentation")
        foreign = body.index(
            "const bool bAcceptedForeignSecondCompletion"
        )
        hybrid = body.index("const bool bAcceptedHybridSecondCompletion")
        exact_second = body.index("const bool bCompletedExactSecond")
        exact_first = body.index("const bool bCompletedExactFirst")
        self.assertLess(rejected_queue, first_queue)
        self.assertLess(first_queue, second_queue)
        self.assertLess(second_queue, foreign)
        self.assertLess(foreign, hybrid)
        self.assertLess(hybrid, exact_second)
        self.assertLess(exact_second, exact_first)
        for expression in (
            (
                "FChunkRevision CrossVolumeBuildRevision "
                "= FirstAfterEditRevision"
            ),
            (
                "CrossVolumeBuildRevision.TargetStableId "
                "= SecondVolumeStableId"
            ),
            (
                "Backend.QueueChunkRebuild( "
                "CrossVolumeBuildRevision, "
                "EGeneratedOutputRequirement::Presentation, "
                "RejectedCrossVolumeRequest, Error)"
            ),
            "is stale or does not match authority content",
            (
                "RejectedCrossVolumeRequest.Ticket."
                "BuildRequestToken == uint64(0)"
            ),
            (
                "RejectedCrossVolumeRequest."
                "CanonicalDensityAndMaterial.IsEmpty()"
            ),
            (
                "FirstAfterRejectedQueue.TargetStableId "
                "== FirstAfterEditRevision.TargetStableId"
            ),
            (
                "FirstAfterRejectedQueue.ContentSha256 "
                "== FirstAfterEditRevision.ContentSha256"
            ),
            "!FirstAfterRejectedQueue.bPresentationReady",
            "!FirstAfterRejectedQueue.bCollisionReady",
            (
                "SecondAfterRejectedQueue.TargetStableId "
                "== SecondAfterFirstEditRevision.TargetStableId"
            ),
            (
                "SecondAfterRejectedQueue.ContentSha256 "
                "== SecondAfterFirstEditRevision.ContentSha256"
            ),
            "!SecondAfterRejectedQueue.bPresentationReady",
            "!SecondAfterRejectedQueue.bCollisionReady",
            (
                "Backend.QueueChunkRebuild( "
                "FirstAfterEditRevision, "
                "EGeneratedOutputRequirement::Presentation, "
                "FirstPresentationRequest, Error)"
            ),
            (
                "Backend.QueueChunkRebuild( "
                "SecondAfterFirstEditRevision, "
                "EGeneratedOutputRequirement::Presentation, "
                "SecondPresentationRequest, Error)"
            ),
            (
                "FirstPresentationRequest.Ticket.SourceRevision."
                "TargetStableId == FirstVolumeStableId"
            ),
            (
                "SecondPresentationRequest.Ticket.SourceRevision."
                "TargetStableId == SecondVolumeStableId"
            ),
            (
                "FirstPresentationRequest.Ticket.VolumeSpecSha256 "
                "== FirstSpec.CanonicalSpecSha256"
            ),
            (
                "SecondPresentationRequest.Ticket.VolumeSpecSha256 "
                "== SecondSpec.CanonicalSpecSha256"
            ),
            (
                "FirstPresentationRequest.Ticket.BackendInstanceId "
                "== SecondPresentationRequest.Ticket.BackendInstanceId"
            ),
            (
                "FirstPresentationRequest.Ticket.BuildRequestToken "
                "== uint64(1)"
            ),
            (
                "FirstPresentationRequest.Ticket.BuildRequestToken "
                "+ uint64(1) "
                "== SecondPresentationRequest.Ticket.BuildRequestToken"
            ),
            (
                "ForeignSecondCompletion.Ticket "
                "= SecondPresentationRequest.Ticket"
            ),
            (
                "ForeignSecondCompletion.Ticket.SourceRevision."
                "ContentRevision = FirstPresentationRequest.Ticket."
                "SourceRevision.ContentRevision"
            ),
            (
                "ForeignSecondCompletion.Ticket.SourceRevision."
                "ContentSha256 = FirstPresentationRequest.Ticket."
                "SourceRevision.ContentSha256"
            ),
            (
                "ForeignSecondCompletion.Ticket.SourceRevision."
                "GenerationToken = FirstPresentationRequest.Ticket."
                "SourceRevision.GenerationToken"
            ),
            (
                "ForeignSecondCompletion.Ticket.VolumeSpecSha256 "
                "= FirstPresentationRequest.Ticket.VolumeSpecSha256"
            ),
            (
                "ValidateGeneratedChunkBuildCompletion( "
                "ForeignSecondCompletion, "
                "&ForeignCompletionValidationError)"
            ),
            (
                "ForeignSecondCompletion.Ticket.BuildRequestToken "
                "== SecondPresentationRequest.Ticket.BuildRequestToken"
            ),
            (
                "ForeignSecondCompletion.Ticket.VolumeSpecSha256 "
                "!= SecondPresentationRequest.Ticket.VolumeSpecSha256"
            ),
            (
                "Backend.CompleteChunkRebuild( "
                "ForeignSecondCompletion, Error)"
            ),
            (
                'TestFalse( TEXT("First-volume authority identity cannot '
                'complete the second ticket"), '
                "bAcceptedForeignSecondCompletion)"
            ),
            "is stale or does not match live authority",
            (
                "HybridSecondCompletion.Ticket = "
                "SecondPresentationRequest.Ticket"
            ),
            (
                "HybridSecondCompletion.Ticket.BuildRequestToken = "
                "FirstPresentationRequest.Ticket.BuildRequestToken"
            ),
            (
                "ValidateGeneratedChunkBuildCompletion( "
                "HybridSecondCompletion, "
                "&HybridCompletionValidationError)"
            ),
            (
                "HybridSecondCompletion.Ticket.BuildRequestToken "
                "!= SecondPresentationRequest.Ticket.BuildRequestToken"
            ),
            (
                "Backend.CompleteChunkRebuild( "
                "HybridSecondCompletion, Error)"
            ),
            (
                'TestFalse(TEXT("A first-volume attempt token cannot '
                'authorize the second ticket"), '
                "bAcceptedHybridSecondCompletion)"
            ),
            "is not the active role attempt",
            "!FirstAfterHybridCompletion.bPresentationReady",
            "!FirstAfterHybridCompletion.bCollisionReady",
            "!SecondAfterHybridCompletion.bPresentationReady",
            "!SecondAfterHybridCompletion.bCollisionReady",
            (
                "FirstAfterHybridCompletion.TargetStableId "
                "== FirstAfterEditRevision.TargetStableId"
            ),
            (
                "FirstAfterHybridCompletion.ChunkCoordinate "
                "== FirstAfterEditRevision.ChunkCoordinate"
            ),
            (
                "FirstAfterHybridCompletion.ContentRevision "
                "== FirstAfterEditRevision.ContentRevision"
            ),
            (
                "FirstAfterHybridCompletion.ContentSha256 "
                "== FirstAfterEditRevision.ContentSha256"
            ),
            (
                "FirstAfterHybridCompletion.GenerationToken "
                "== FirstAfterEditRevision.GenerationToken"
            ),
            (
                "SecondAfterHybridCompletion.TargetStableId "
                "== SecondAfterFirstEditRevision.TargetStableId"
            ),
            (
                "SecondAfterHybridCompletion.ChunkCoordinate "
                "== SecondAfterFirstEditRevision.ChunkCoordinate"
            ),
            (
                "SecondAfterHybridCompletion.ContentRevision "
                "== SecondAfterFirstEditRevision.ContentRevision"
            ),
            (
                "SecondAfterHybridCompletion.ContentSha256 "
                "== SecondAfterFirstEditRevision.ContentSha256"
            ),
            (
                "SecondAfterHybridCompletion.GenerationToken "
                "== SecondAfterFirstEditRevision.GenerationToken"
            ),
            (
                "FirstAfterHybridCompletion."
                "PresentationOutputSha256.IsEmpty()"
            ),
            (
                "SecondAfterHybridCompletion."
                "PresentationOutputSha256.IsEmpty()"
            ),
            (
                "FirstAfterHybridCompletion."
                "CollisionOutputSha256.IsEmpty()"
            ),
            (
                "SecondAfterHybridCompletion."
                "CollisionOutputSha256.IsEmpty()"
            ),
            (
                "ExactSecondCompletion.Ticket = "
                "SecondPresentationRequest.Ticket"
            ),
            (
                "ExactFirstCompletion.Ticket = "
                "FirstPresentationRequest.Ticket"
            ),
            "SecondAfterExactCompletion.bPresentationReady",
            "!SecondAfterExactCompletion.bCollisionReady",
            (
                "SecondAfterExactCompletion.PresentationOutputSha256 "
                "== SecondPresentationSha256"
            ),
            (
                "FirstWhileSecondComplete.TargetStableId "
                "== FirstAfterEditRevision.TargetStableId"
            ),
            (
                "FirstWhileSecondComplete.ContentSha256 "
                "== FirstAfterEditRevision.ContentSha256"
            ),
            "!FirstWhileSecondComplete.bPresentationReady",
            "!FirstWhileSecondComplete.bCollisionReady",
            "FirstWhileSecondComplete.PresentationOutputSha256.IsEmpty()",
            "FirstWhileSecondComplete.CollisionOutputSha256.IsEmpty()",
            "FirstAfterExactCompletion.bPresentationReady",
            "!FirstAfterExactCompletion.bCollisionReady",
            (
                "FirstAfterExactCompletion.PresentationOutputSha256 "
                "== FirstPresentationSha256"
            ),
            (
                "SecondAfterBothCompletions.TargetStableId "
                "== SecondAfterFirstEditRevision.TargetStableId"
            ),
            (
                "SecondAfterBothCompletions.ContentSha256 "
                "== SecondAfterFirstEditRevision.ContentSha256"
            ),
            "!SecondAfterBothCompletions.bCollisionReady",
            "SecondAfterBothCompletions.CollisionOutputSha256.IsEmpty()",
            (
                "SecondAfterBothCompletions.PresentationOutputSha256 "
                "== SecondPresentationSha256"
            ),
            (
                "FirstAfterExactCompletion.PresentationOutputSha256 "
                "!= SecondAfterBothCompletions.PresentationOutputSha256"
            ),
        ):
            self.assertIn(expression, compact)
        identity_fields = (
            "TargetStableId",
            "ChunkCoordinate",
            "ContentRevision",
            "ContentSha256",
            "GenerationToken",
        )
        for state, revision in (
            ("FirstAfterRejectedQueue", "FirstAfterEditRevision"),
            ("SecondAfterRejectedQueue", "SecondAfterFirstEditRevision"),
            ("FirstAfterHybridCompletion", "FirstAfterEditRevision"),
            (
                "SecondAfterHybridCompletion",
                "SecondAfterFirstEditRevision",
            ),
            (
                "SecondAfterExactCompletion",
                "SecondAfterFirstEditRevision",
            ),
            ("FirstWhileSecondComplete", "FirstAfterEditRevision"),
            ("FirstAfterExactCompletion", "FirstAfterEditRevision"),
            (
                "SecondAfterBothCompletions",
                "SecondAfterFirstEditRevision",
            ),
        ):
            for field in identity_fields:
                self.assertIn(
                    f"{state}.{field} == {revision}.{field}",
                    compact,
                )
        for state in (
            "FirstAfterRejectedQueue",
            "SecondAfterRejectedQueue",
            "FirstAfterHybridCompletion",
            "SecondAfterHybridCompletion",
            "FirstWhileSecondComplete",
        ):
            for field in ("bPresentationReady", "bCollisionReady"):
                self.assertIn(f"!{state}.{field}", compact)
            for field in (
                "PresentationOutputSha256",
                "CollisionOutputSha256",
            ):
                self.assertIn(f"{state}.{field}.IsEmpty()", compact)
        for state, expected_sha in (
            ("SecondAfterExactCompletion", "SecondPresentationSha256"),
            ("FirstAfterExactCompletion", "FirstPresentationSha256"),
            ("SecondAfterBothCompletions", "SecondPresentationSha256"),
        ):
            self.assertIn(
                f"&& {state}.bPresentationReady",
                compact,
            )
            self.assertIn(f"!{state}.bCollisionReady", compact)
            self.assertIn(
                f"{state}.PresentationOutputSha256 == {expected_sha}",
                compact,
            )
            self.assertIn(
                f"{state}.CollisionOutputSha256.IsEmpty()",
                compact,
            )

    def test_multi_volume_persistence_capabilities_are_volume_local(self):
        body = self.multi_volume_source
        compact = self.multi_volume_compact
        first_capture = body.index("const bool bCapturedFirstPersistence")
        second_capture = body.index("const bool bCapturedSecondPersistence")
        foreign = body.index(
            "const bool bAcceptedForeignSecondAcknowledgement"
        )
        hybrid = body.index(
            "const bool bAcceptedHybridSecondAcknowledgement"
        )
        exact_first = body.index("const bool bAcknowledgedExactFirst")
        exact_second = body.index("const bool bAcknowledgedExactSecond")
        first_reexport = body.index(
            "const bool bExportedFirstAfterSecondAcknowledgement"
        )
        self.assertLess(first_capture, second_capture)
        self.assertLess(second_capture, foreign)
        self.assertLess(foreign, hybrid)
        self.assertLess(hybrid, exact_first)
        self.assertLess(exact_first, exact_second)
        self.assertLess(exact_second, first_reexport)
        for expression in (
            (
                "Backend.CaptureCheckpointForPersistence( "
                "FirstVolumeStableId, FirstPersistenceRequest, Error)"
            ),
            (
                "Backend.CaptureCheckpointForPersistence( "
                "SecondVolumeStableId, SecondPersistenceRequest, Error)"
            ),
            (
                "ValidateCheckpointPersistenceRequest( "
                "FirstPersistenceRequest, "
                "&FirstPersistenceRequestValidationError)"
            ),
            (
                "ValidateCheckpointPersistenceRequest( "
                "SecondPersistenceRequest, "
                "&SecondPersistenceRequestValidationError)"
            ),
            (
                "bFirstPersistenceRequestValid "
                "&& bSecondPersistenceRequestValid"
            ),
            (
                "FirstPersistenceRequest.Ticket.TargetStableId "
                "== FirstVolumeStableId"
            ),
            (
                "SecondPersistenceRequest.Ticket.TargetStableId "
                "== SecondVolumeStableId"
            ),
            (
                "FirstPersistenceRequest.Ticket.VolumeSpecSha256 "
                "== FirstSpec.CanonicalSpecSha256"
            ),
            (
                "SecondPersistenceRequest.Ticket.VolumeSpecSha256 "
                "== SecondSpec.CanonicalSpecSha256"
            ),
            (
                "FirstPersistenceRequest.Ticket.BackendInstanceId "
                "== SecondPersistenceRequest.Ticket.BackendInstanceId"
            ),
            (
                "FirstPersistenceRequest.Ticket.PersistenceRequestToken "
                "+ uint64(1) "
                "== SecondPersistenceRequest.Ticket."
                "PersistenceRequestToken"
            ),
            (
                "ForeignSecondAcknowledgement.Ticket "
                "= SecondPersistenceRequest.Ticket"
            ),
            (
                "ForeignSecondAcknowledgement.Ticket.VolumeSpecSha256 "
                "= FirstPersistenceRequest.Ticket.VolumeSpecSha256"
            ),
            (
                "ForeignSecondAcknowledgement.Ticket."
                "CheckpointThroughRevision = FirstPersistenceRequest."
                "Ticket.CheckpointThroughRevision"
            ),
            (
                "ForeignSecondAcknowledgement.Ticket."
                "CheckpointManifestSha256 = FirstPersistenceRequest."
                "Ticket.CheckpointManifestSha256"
            ),
            (
                "ForeignSecondAcknowledgement.Ticket."
                "CheckpointJournalTailSha256 = FirstPersistenceRequest."
                "Ticket.CheckpointJournalTailSha256"
            ),
            (
                "ValidateCheckpointPersistenceTicket( "
                "ForeignSecondAcknowledgement.Ticket, "
                "&ForeignAcknowledgementValidationError)"
            ),
            (
                "ForeignSecondAcknowledgement.Ticket."
                "PersistenceRequestToken "
                "== SecondPersistenceRequest.Ticket."
                "PersistenceRequestToken"
            ),
            (
                "ForeignSecondAcknowledgement.Ticket.VolumeSpecSha256 "
                "!= SecondPersistenceRequest.Ticket.VolumeSpecSha256"
            ),
            (
                "Backend.AcknowledgePersistedCheckpoint( "
                "ForeignSecondAcknowledgement, Error)"
            ),
            (
                'TestFalse( TEXT("First-volume checkpoint identity cannot '
                'acknowledge the second ticket"), '
                "bAcceptedForeignSecondAcknowledgement)"
            ),
            "targets stale or foreign authority state",
            (
                "HybridSecondAcknowledgement.Ticket = "
                "SecondPersistenceRequest.Ticket"
            ),
            (
                "HybridSecondAcknowledgement.Ticket."
                "PersistenceRequestToken = "
                "FirstPersistenceRequest.Ticket.PersistenceRequestToken"
            ),
            (
                "ValidateCheckpointPersistenceTicket( "
                "HybridSecondAcknowledgement.Ticket, "
                "&HybridAcknowledgementValidationError)"
            ),
            (
                "HybridSecondAcknowledgement.Ticket."
                "PersistenceRequestToken "
                "!= SecondPersistenceRequest.Ticket."
                "PersistenceRequestToken"
            ),
            (
                "Backend.AcknowledgePersistedCheckpoint( "
                "HybridSecondAcknowledgement, Error)"
            ),
            (
                'TestFalse( TEXT("A first-volume persistence token cannot '
                'acknowledge the second ticket"), '
                "bAcceptedHybridSecondAcknowledgement)"
            ),
            "does not match the exact live pending ticket",
            (
                "Backend.ExportOperationJournal( "
                "FirstVolumeStableId, FirstBeforeAcknowledgement, Error)"
            ),
            (
                "Backend.ExportOperationJournal( "
                "SecondVolumeStableId, SecondBeforeAcknowledgement, Error)"
            ),
            (
                "ExactFirstAcknowledgement.Ticket = "
                "FirstPersistenceRequest.Ticket"
            ),
            (
                "ExactSecondAcknowledgement.Ticket = "
                "SecondPersistenceRequest.Ticket"
            ),
            (
                "FirstAfterAcknowledgement.TargetStableId "
                "== FirstVolumeStableId"
            ),
            (
                "FirstAfterAcknowledgement.VolumeSpecSha256 "
                "== FirstSpec.CanonicalSpecSha256"
            ),
            (
                "FirstAfterAcknowledgement."
                "BaseCheckpointRevision == uint64(1)"
            ),
            (
                "FirstAfterAcknowledgement."
                "BaseCheckpointManifestSha256 "
                "== FirstPersistenceRequest.Ticket."
                "CheckpointManifestSha256"
            ),
            (
                "FirstAfterAcknowledgement.BaseJournalTailSha256 "
                "== FirstPersistenceRequest.Ticket."
                "CheckpointJournalTailSha256"
            ),
            "FirstAfterAcknowledgement.ThroughRevision == uint64(1)",
            "FirstAfterAcknowledgement.Operations.IsEmpty()",
            (
                "FirstAfterAcknowledgement.FinalJournalTailSha256 "
                "== FirstPersistenceRequest.Ticket."
                "CheckpointJournalTailSha256"
            ),
            (
                "SecondAfterAcknowledgement.TargetStableId "
                "== SecondVolumeStableId"
            ),
            (
                "SecondAfterAcknowledgement.VolumeSpecSha256 "
                "== SecondSpec.CanonicalSpecSha256"
            ),
            (
                "SecondAfterAcknowledgement."
                "BaseCheckpointRevision == uint64(0)"
            ),
            (
                "SecondAfterAcknowledgement."
                "BaseCheckpointManifestSha256 "
                "== SecondPersistenceRequest.Ticket."
                "CheckpointManifestSha256"
            ),
            (
                "SecondAfterAcknowledgement.BaseJournalTailSha256 "
                "== SecondPersistenceRequest.Ticket."
                "CheckpointJournalTailSha256"
            ),
            "SecondAfterAcknowledgement.ThroughRevision == uint64(0)",
            "SecondAfterAcknowledgement.Operations.IsEmpty()",
            (
                "SecondAfterAcknowledgement.FinalJournalTailSha256 "
                "== SecondPersistenceRequest.Ticket."
                "CheckpointJournalTailSha256"
            ),
            (
                "ValidateEditJournalExport( "
                "FirstAfterSecondAcknowledgement, Limits, "
                "&FirstExportValidationError)"
            ),
            (
                "ValidateEditJournalExport( "
                "SecondAfterAcknowledgement, Limits, "
                "&SecondExportValidationError)"
            ),
            (
                "FirstAfterSecondAcknowledgement.CanonicalManifestSha256 "
                "== FirstAfterAcknowledgement.CanonicalManifestSha256"
            ),
            (
                "FirstAfterSecondAcknowledgement."
                "BaseCheckpointManifestSha256 "
                "== FirstAfterAcknowledgement."
                "BaseCheckpointManifestSha256"
            ),
            (
                "FirstAfterSecondAcknowledgement."
                "BaseJournalTailSha256 "
                "== FirstAfterAcknowledgement.BaseJournalTailSha256"
            ),
            (
                "FirstAfterSecondAcknowledgement."
                "FinalJournalTailSha256 "
                "== FirstAfterAcknowledgement.FinalJournalTailSha256"
            ),
        ):
            self.assertIn(expression, compact)

    def test_multi_volume_scenario_excludes_unrelated_lifecycle_and_runtime(
        self,
    ):
        body = self.multi_volume_source
        compact = self.multi_volume_compact
        for expression in (
            (
                "FirstFinalCheckpoint.CanonicalManifestSha256 "
                "== FirstAfterEditCheckpoint.CanonicalManifestSha256"
            ),
            (
                "SecondFinalCheckpoint.CanonicalManifestSha256 "
                "== SecondAfterFirstEditCheckpoint."
                "CanonicalManifestSha256"
            ),
            (
                "Backend.GetCurrentRevision(FirstVolumeStableId) "
                "== uint64(1)"
            ),
            (
                "Backend.GetCurrentRevision(SecondVolumeStableId) "
                "== uint64(0)"
            ),
            (
                "Backend.GetAuthorityGenerationToken("
                "FirstVolumeStableId) == FirstAuthorityGeneration"
            ),
            (
                "Backend.GetAuthorityGenerationToken("
                "SecondVolumeStableId) == SecondAuthorityGeneration"
            ),
        ):
            self.assertIn(expression, compact)
        for forbidden in (
            "ReleaseVolume",
            "RestoreCheckpointSetAtomically",
            "InspectCheckpointSet",
            "InvalidateBuildsOlderThan",
            "ECheckpointRestoreMode",
            "InitializeAbsentVolume",
            "ReplaceQuiescedVolume",
            "MaxJournalOperationsPerCheckpoint",
            "JournalCapacityReached",
            "AActor",
            "UWorld",
            "OpenLevel",
            "LoadMap",
            "Inventory",
            "ProceduralMesh",
            "DynamicMesh",
            "VoxelPlugin",
            "Steam",
        ):
            self.assertNotIn(forbidden, body)
        self.assertNotIn(
            "FRedInMemorySparseVoxelBackend FirstBackend",
            compact,
        )
        self.assertNotIn(
            "FRedInMemorySparseVoxelBackend SecondBackend",
            compact,
        )

    def test_same_revision_equivocation_establishes_one_real_durable_base(
        self,
    ):
        body = self.equivocation_source
        compact = self.equivocation_compact
        initialization = body.index("const bool bInitialized")
        first_edit = body.index("const bool bFirstEditAccepted")
        base_capture = body.index("const bool bCapturedBaseRequest")
        base_acknowledgement = body.index("const bool bAcknowledgedBase")
        baseline_export = body.index("const bool bExportedBaseline")
        baseline_checkpoint = body.index(
            "const bool bCapturedBaselineCheckpoint"
        )
        same_revision_capture = body.index(
            "const bool bCapturedSameRevisionRequest"
        )
        self.assertLess(initialization, first_edit)
        self.assertLess(first_edit, base_capture)
        self.assertLess(base_capture, base_acknowledgement)
        self.assertLess(base_acknowledgement, baseline_export)
        self.assertLess(baseline_export, baseline_checkpoint)
        self.assertLess(baseline_checkpoint, same_revision_capture)
        self.assertEqual(
            len(
                re.findall(
                    r"\bFRedInMemorySparseVoxelBackend\s+\w+\s*;",
                    body,
                )
            ),
            1,
        )
        self.assertEqual(body.count("Backend.InitializeVolume("), 1)
        self.assertEqual(body.count("ApplyAcceptedEdit("), 1)
        for expression in (
            "FirstResult.PreviousRevision == uint64(0)",
            "FirstResult.AppliedRevision == uint64(1)",
            "FirstResult.RequestSequence == uint64(1)",
            "FirstResult.RejectReason == EEditRejectReason::None",
            "FirstResult.TotalRemovedCellCount == 1",
            "Backend.GetCurrentRevision(VolumeStableId) == uint64(1)",
            (
                "ValidateCheckpointPersistenceRequest( "
                "BasePersistenceRequest, &BaseRequestValidationError)"
            ),
            (
                "BaseAcknowledgement.Ticket "
                "= BasePersistenceRequest.Ticket"
            ),
            (
                "Backend.AcknowledgePersistedCheckpoint( "
                "BaseAcknowledgement, Error)"
            ),
            (
                "BaselineExport.BaseCheckpointRevision == uint64(1)"
            ),
            "BaselineExport.ThroughRevision == uint64(1)",
            "BaselineExport.Operations.IsEmpty()",
            (
                "BaselineCheckpoint.CanonicalManifestSha256 "
                "== BasePersistenceRequest.Ticket."
                "CheckpointManifestSha256"
            ),
            "!BaselineCheckpoint.Chunks.IsEmpty()",
        ):
            self.assertIn(expression, compact)

    def test_same_revision_reissue_binds_the_exact_acknowledged_identity(
        self,
    ):
        body = self.equivocation_source
        compact = self.equivocation_compact
        self.assertEqual(
            body.count("Backend.CaptureCheckpointForPersistence("),
            2,
        )
        for expression in (
            (
                "ValidateCheckpointPersistenceRequest( "
                "SameRevisionRequest, &SameRevisionValidationError)"
            ),
            "SameRevisionTicket.bExpectedAcknowledgedBase",
            (
                "SameRevisionTicket.ExpectedJournalBaseRevision "
                "== uint64(1)"
            ),
            (
                "SameRevisionTicket.CheckpointThroughRevision "
                "== uint64(1)"
            ),
            (
                "SameRevisionTicket.ExpectedBaseCheckpointManifestSha256 "
                "== BasePersistenceRequest.Ticket."
                "CheckpointManifestSha256"
            ),
            (
                "SameRevisionTicket.CheckpointManifestSha256 "
                "== SameRevisionTicket."
                "ExpectedBaseCheckpointManifestSha256"
            ),
            (
                "SameRevisionTicket.ExpectedBaseJournalTailSha256 "
                "== BasePersistenceRequest.Ticket."
                "CheckpointJournalTailSha256"
            ),
            (
                "SameRevisionTicket.CheckpointJournalTailSha256 "
                "== SameRevisionTicket.ExpectedBaseJournalTailSha256"
            ),
            (
                "SameRevisionTicket.AuthorityGenerationToken "
                "== GenerationBeforeEquivocation"
            ),
            (
                "SameRevisionTicket.BackendInstanceId "
                "== BasePersistenceRequest.Ticket.BackendInstanceId"
            ),
            (
                "SameRevisionTicket.PersistenceRequestToken "
                "== BasePersistenceRequest.Ticket."
                "PersistenceRequestToken + uint64(1)"
            ),
        ):
            self.assertIn(expression, compact)
        self.assertIn(
            'TestTrue(TEXT("The new request binds the exact '
            'acknowledged base identity"), '
            "SameRevisionTicket.bExpectedAcknowledgedBase",
            compact,
        )

    def test_same_revision_equivocation_is_canonical_and_reason_specific(
        self,
    ):
        body = self.equivocation_source
        compact = self.equivocation_compact
        conflict_build = body.index(
            "FCheckpointPersistenceRequest ConflictingRequest"
        )
        validation = body.index("const bool bConflictingRequestValid")
        acknowledgement = body.index(
            "const bool bAcknowledgedConflictingManifest"
        )
        self.assertLess(conflict_build, validation)
        self.assertLess(validation, acknowledgement)
        for expression in (
            (
                "const FString ConflictingCanonicalManifestSha256 "
                "= BaselineExport.CanonicalManifestSha256"
            ),
            (
                "IsCanonicalSha256("
                "ConflictingCanonicalManifestSha256)"
            ),
            (
                "ConflictingCanonicalManifestSha256 "
                "!= SameRevisionTicket.CheckpointManifestSha256"
            ),
            "ConflictingRequest = SameRevisionRequest",
            (
                "ConflictingRequest.Ticket.CheckpointManifestSha256 "
                "= ConflictingCanonicalManifestSha256"
            ),
            (
                "ConflictingRequest.Checkpoint."
                "CanonicalManifestSha256 "
                "= ConflictingCanonicalManifestSha256"
            ),
            (
                "ConflictingRequest.Ticket."
                "ExpectedBaseCheckpointManifestSha256 "
                "== SameRevisionTicket."
                "ExpectedBaseCheckpointManifestSha256"
            ),
            (
                "ValidateCheckpointPersistenceRequest( "
                "ConflictingRequest, &ConflictingValidationError)"
            ),
            (
                'TestFalse(TEXT("A same-revision conflicting manifest '
                'is invalid"), bConflictingRequestValid)'
            ),
            (
                "ConflictingAcknowledgement.Ticket "
                "= ConflictingRequest.Ticket"
            ),
            (
                "Backend.AcknowledgePersistedCheckpoint( "
                "ConflictingAcknowledgement, Error)"
            ),
            (
                'TestFalse(TEXT("The backend rejects same-revision '
                'manifest equivocation"), '
                "bAcknowledgedConflictingManifest)"
            ),
        ):
            self.assertIn(expression, compact)
        self.assertGreaterEqual(
            body.count(
                "same-revision checkpoint identity does not match "
                "its acknowledged journal base"
            ),
            2,
        )
        self.assertIn(
            'TestTrue(TEXT("Validation identifies same-revision '
            'checkpoint equivocation"), '
            "ConflictingValidationError.Contains(TEXT( "
            '"same-revision checkpoint identity does not match '
            'its acknowledged journal base")))',
            compact,
        )
        self.assertIn(
            'TestTrue(TEXT("The backend rejection names the '
            'same-revision identity"), Error.Contains(TEXT( '
            '"same-revision checkpoint identity does not match '
            'its acknowledged journal base")))',
            compact,
        )
        self.assertIsNone(
            re.search(
                r"ConflictingRequest\.Ticket\."
                r"ExpectedBaseCheckpointManifestSha256\s*=(?!=)",
                body,
            ),
        )
        conflict_slice = body[
            body.index(
                "FCheckpointPersistenceRequest ConflictingRequest"
            ) : body.index("FString ConflictingValidationError")
        ]
        conflict_mutations = re.findall(
            r"(ConflictingRequest(?:\.[A-Za-z_][A-Za-z0-9_]*)+)"
            r"\s*(\+\+|--|\+=|-=|\*=|/=|%=|&=|\|=|\^=|<<=|>>=|=(?!=))",
            conflict_slice,
        )
        self.assertEqual(
            conflict_mutations,
            [
                (
                    "ConflictingRequest.Ticket."
                    "CheckpointManifestSha256",
                    "=",
                ),
                (
                    "ConflictingRequest.Checkpoint."
                    "CanonicalManifestSha256",
                    "=",
                ),
            ],
        )
        self.assertIsNone(
            re.search(
                r"(?:\+\+|--)\s*ConflictingRequest"
                r"(?:\.[A-Za-z_][A-Za-z0-9_]*)+",
                conflict_slice,
            ),
        )

    def test_same_revision_equivocation_rejection_is_checkpoint_and_export_atomic(
        self,
    ):
        body = self.equivocation_source
        compact = self.equivocation_compact
        rejection = body.index(
            "const bool bAcknowledgedConflictingManifest"
        )
        checkpoint = body.index(
            "const bool bCapturedAfterEquivocation"
        )
        export = body.index("const bool bExportedAfterEquivocation")
        self.assertLess(rejection, checkpoint)
        self.assertLess(checkpoint, export)
        self.assertIn(
            'TestTrue(TEXT("Equivocation preserves the complete '
            'checkpoint identity"), '
            "AfterEquivocationCheckpoint.TargetStableId",
            compact,
        )
        self.assertRegex(
            body,
            r"for\s*\(\s*int32\s+ChunkIndex\s*=\s*0\s*;"
            r"\s*ChunkIndex\s*<\s*BaselineCheckpoint\.Chunks\.Num\(\)"
            r"\s*;\s*\+\+ChunkIndex\s*\)",
        )
        self.assertIn(
            "const FChunkCheckpoint& BeforeChunk = "
            "BaselineCheckpoint.Chunks[ChunkIndex]",
            compact,
        )
        self.assertIn(
            "const FChunkCheckpoint& AfterChunk = "
            "AfterEquivocationCheckpoint.Chunks[ChunkIndex]",
            compact,
        )
        self.assertIn(
            'TestTrue( FString::Printf( TEXT("Equivocation preserves '
            'checkpoint chunk %d"), ChunkIndex), '
            "AfterChunk.TargetStableId == BeforeChunk.TargetStableId",
            compact,
        )
        self.assertIn(
            'TestTrue(TEXT("Equivocation leaves every export '
            'identity field exact"), '
            "ExportAfterEquivocation.TargetStableId",
            compact,
        )
        for expression in (
            (
                "Backend.GetCurrentRevision(VolumeStableId), "
                "RevisionBeforeEquivocation"
            ),
            (
                "Backend.GetAuthorityGenerationToken(VolumeStableId), "
                "GenerationBeforeEquivocation"
            ),
            (
                "AfterEquivocationCheckpoint.TargetStableId "
                "== BaselineCheckpoint.TargetStableId"
            ),
            (
                "AfterEquivocationCheckpoint.VolumeSpecSha256 "
                "== BaselineCheckpoint.VolumeSpecSha256"
            ),
            (
                "AfterEquivocationCheckpoint.ThroughRevision "
                "== BaselineCheckpoint.ThroughRevision"
            ),
            (
                "AfterEquivocationCheckpoint.CanonicalManifestSha256 "
                "== BaselineCheckpoint.CanonicalManifestSha256"
            ),
            (
                "AfterEquivocationCheckpoint.Chunks.Num() "
                "== BaselineCheckpoint.Chunks.Num()"
            ),
            "AfterChunk.TargetStableId == BeforeChunk.TargetStableId",
            (
                "AfterChunk.ChunkCoordinate "
                "== BeforeChunk.ChunkCoordinate"
            ),
            "AfterChunk.ThroughRevision == BeforeChunk.ThroughRevision",
            (
                "AfterChunk.VolumeSpecSha256 "
                "== BeforeChunk.VolumeSpecSha256"
            ),
            (
                "AfterChunk.CanonicalPayloadSha256 "
                "== BeforeChunk.CanonicalPayloadSha256"
            ),
            (
                "AfterChunk.CompressedDensityAndMaterial "
                "== BeforeChunk.CompressedDensityAndMaterial"
            ),
        ):
            self.assertIn(expression, compact)
        for field in (
            "TargetStableId",
            "VolumeSpecSha256",
            "BaseCheckpointRevision",
            "BaseCheckpointManifestSha256",
            "BaseJournalTailSha256",
            "ThroughRevision",
            "FinalJournalTailSha256",
            "CanonicalManifestSha256",
        ):
            self.assertIn(
                f"ExportAfterEquivocation.{field} "
                f"== BaselineExport.{field}",
                compact,
            )
        self.assertIn(
            "ExportAfterEquivocation.Operations.Num() "
            "== BaselineExport.Operations.Num()",
            compact,
        )

    def test_same_revision_capabilities_survive_and_scope_stays_bounded(
        self,
    ):
        body = self.equivocation_source
        compact = self.equivocation_compact
        rejection = body.index(
            "const bool bAcknowledgedConflictingManifest"
        )
        duplicate = body.index(
            "const bool bDuplicateBaseStillIdempotent"
        )
        exact = body.index(
            "const bool bAcknowledgedExactSameRevision"
        )
        final_export = body.index("const bool bExportedFinal")
        self.assertLess(rejection, duplicate)
        self.assertLess(duplicate, exact)
        self.assertLess(exact, final_export)
        self.assertEqual(
            body.count("Backend.AcknowledgePersistedCheckpoint("),
            4,
        )
        self.assertEqual(body.count("Backend.ExportOperationJournal("), 3)
        self.assertEqual(body.count("Backend.CaptureCheckpointSet("), 2)
        self.assertIn(
            "const bool bDuplicateBaseStillIdempotent = "
            "Backend.AcknowledgePersistedCheckpoint( "
            "BaseAcknowledgement, Error)",
            compact,
        )
        self.assertIn(
            "const bool bAcknowledgedExactSameRevision = "
            "Backend.AcknowledgePersistedCheckpoint( "
            "ExactSameRevisionAcknowledgement, Error)",
            compact,
        )
        for expression in (
            (
                "Backend.AcknowledgePersistedCheckpoint( "
                "BaseAcknowledgement, Error)"
            ),
            (
                'TestTrue( FString::Printf( TEXT("The prior '
                'acknowledgement remains duplicate-idempotent: %s"), '
                "*Error), bDuplicateBaseStillIdempotent)"
            ),
            (
                "ExactSameRevisionAcknowledgement.Ticket "
                "= SameRevisionRequest.Ticket"
            ),
            (
                "Backend.AcknowledgePersistedCheckpoint( "
                "ExactSameRevisionAcknowledgement, Error)"
            ),
            (
                'TestTrue( FString::Printf( TEXT("The untouched pending '
                'same-revision ticket still acknowledges: %s"), '
                "*Error), bAcknowledgedExactSameRevision)"
            ),
            (
                "ValidateEditJournalExport( "
                "FinalExport, Limits, &FinalExportValidationError)"
            ),
        ):
            self.assertIn(expression, compact)
        for field in (
            "TargetStableId",
            "VolumeSpecSha256",
            "BaseCheckpointRevision",
            "BaseCheckpointManifestSha256",
            "BaseJournalTailSha256",
            "ThroughRevision",
            "FinalJournalTailSha256",
            "CanonicalManifestSha256",
        ):
            self.assertIn(
                f"FinalExport.{field} == BaselineExport.{field}",
                compact,
            )
        self.assertIn(
            'TestTrue(TEXT("Exact acknowledgement preserves the '
            'durable base bytes"), '
            "FinalExport.TargetStableId == BaselineExport.TargetStableId",
            compact,
        )
        for forbidden in (
            "RestoreCheckpointSetAtomically",
            "InspectCheckpointSet",
            "ReleaseVolume",
            "InvalidateBuildsOlderThan",
            "QueueChunkRebuild",
            "CompleteChunkRebuild",
            "MaxJournalOperationsPerCheckpoint",
            "JournalCapacityReached",
            "FRedInMemorySparseVoxelBackend SecondBackend",
            "AActor",
            "UWorld",
            "OpenLevel",
            "LoadMap",
            "Inventory",
            "ProceduralMesh",
            "DynamicMesh",
            "VoxelPlugin",
            "Steam",
        ):
            self.assertNotIn(forbidden, body)

    def test_journal_capacity_release_is_one_slot_and_strictly_ordered(
        self,
    ):
        body = self.capacity_source
        compact = self.capacity_compact
        initialization = body.index("const bool bInitialized")
        zero_capture = body.index(
            "const bool bCapturedRevisionZeroRequest"
        )
        zero_ack = body.index("const bool bAcknowledgedRevisionZero")
        first_edit = body.index("const bool bFirstEditAccepted")
        first_rejection = body.index(
            "const bool bCapacityRejectionHandled"
        )
        release_capture = body.index(
            "const bool bCapturedCapacityReleaseRequest"
        )
        capture_only_rejection = body.index(
            "const bool bCaptureOnlyCapacityRejectionHandled"
        )
        release_ack = body.index(
            "const bool bAcknowledgedCapacityRelease"
        )
        accepted_retry = body.index(
            "const bool bRetriedCapacityEditAccepted"
        )
        final_export = body.index("const bool bExportedFinal")
        self.assertLess(initialization, zero_capture)
        self.assertLess(zero_capture, zero_ack)
        self.assertLess(zero_ack, first_edit)
        self.assertLess(first_edit, first_rejection)
        self.assertLess(first_rejection, release_capture)
        self.assertLess(release_capture, capture_only_rejection)
        self.assertLess(capture_only_rejection, release_ack)
        self.assertLess(release_ack, accepted_retry)
        self.assertLess(accepted_retry, final_export)
        self.assertIn(
            "Limits.MaxJournalOperationsPerCheckpoint = 1",
            compact,
        )
        self.assertLess(
            body.index("Limits.MaxJournalOperationsPerCheckpoint = 1"),
            initialization,
        )
        self.assertEqual(
            body.count("FRedInMemorySparseVoxelBackend Backend;"),
            1,
        )
        self.assertEqual(
            len(
                re.findall(
                    r"\bFRedInMemorySparseVoxelBackend\s+\w+\s*;",
                    body,
                )
            ),
            1,
        )
        self.assertEqual(body.count("Backend.InitializeVolume("), 1)
        self.assertEqual(body.count("ApplyAcceptedEdit("), 1)
        self.assertEqual(body.count("Backend.ApplyValidatedEdit("), 3)
        self.assertEqual(
            body.count("Backend.CaptureCheckpointForPersistence("),
            2,
        )
        self.assertEqual(
            body.count("Backend.AcknowledgePersistedCheckpoint("),
            2,
        )
        self.assertEqual(body.count("Backend.ExportOperationJournal("), 5)
        self.assertEqual(body.count("Backend.CaptureCheckpointSet("), 4)

    def test_full_journal_returns_one_exact_atomic_capacity_rejection(
        self,
    ):
        body = self.capacity_source
        compact = self.capacity_compact
        for expression in (
            "CapacityEdit.TargetStableId = VolumeStableId",
            "CapacityEdit.CollectorStableId = CollectorStableId",
            "CapacityEdit.MiningToolStableId = MiningToolStableId",
            "CapacityEdit.RequestSequence = 2",
            "CapacityEdit.ExpectedRevision = 1",
            (
                "CapacityEdit.LocalBrushCenter = "
                "FVector(-150.0, -50.0, -50.0)"
            ),
            "CapacityEdit.AuthorityGenerationToken = AuthorityGeneration",
            "CapacityEdit.PredictionToken = FGuid::NewGuid()",
            (
                "const bool bCapacityRejectionHandled = "
                "Backend.ApplyValidatedEdit( CapacityEdit, "
                "CapacityResult, Error)"
            ),
            (
                'TestTrue(TEXT("A full journal returns a validated '
                'capacity result"), bCapacityRejectionHandled)'
            ),
            (
                "!CapacityResult.bAccepted && "
                "CapacityResult.RejectReason == "
                "EEditRejectReason::JournalCapacityReached"
            ),
            (
                "CapacityResult.TargetStableId "
                "== CapacityEdit.TargetStableId"
            ),
            (
                "CapacityResult.RequestSequence "
                "== CapacityEdit.RequestSequence"
            ),
            (
                "CapacityResult.PredictionToken "
                "== CapacityEdit.PredictionToken"
            ),
            (
                "CapacityResult.AuthorityGenerationToken "
                "== CapacityEdit.AuthorityGenerationToken"
            ),
            "CapacityResult.PreviousRevision == uint64(1)",
            "CapacityResult.AppliedRevision == uint64(1)",
            "CapacityResult.TotalRemovedCellCount == 0",
            "CapacityResult.MaterialYields.IsEmpty()",
            "CapacityResult.DirtyChunkCoordinates.IsEmpty()",
            "ValidateApplyResult( CapacityResult, CapacityEdit, Spec, Limits",
            (
                "Backend.GetCurrentRevision(VolumeStableId) == uint64(1)"
            ),
            (
                "Backend.GetAuthorityGenerationToken(VolumeStableId) "
                "== AuthorityGeneration"
            ),
        ):
            self.assertIn(expression, compact)
        self.assertIn(
            (
                'TestTrue(TEXT("The otherwise-valid second edit is '
                'rejected only for capacity"), '
                "bCapacityRejectionHandled && "
                "!CapacityResult.bAccepted"
            ),
            compact,
        )
        self.assertNotIn(
            "TestFalse(TEXT(\"A full journal",
            compact,
        )

    def test_capacity_refusal_preserves_checkpoint_and_journal_bytes(
        self,
    ):
        body = self.capacity_source
        compact = self.capacity_compact
        before_checkpoint = body.index("BeforeCapacityCheckpoint")
        refusal = body.index("const bool bCapacityRejectionHandled")
        after_checkpoint = body.index("AfterCapacityCheckpoint")
        after_export = body.index("AfterCapacityExport")
        release_capture = body.index(
            "const bool bCapturedCapacityReleaseRequest"
        )
        self.assertLess(before_checkpoint, refusal)
        self.assertLess(refusal, after_checkpoint)
        self.assertLess(after_checkpoint, after_export)
        self.assertLess(after_export, release_capture)
        for field in (
            "TargetStableId",
            "MaterialTableId",
            "VolumeSpecSha256",
            "ThroughRevision",
            "CanonicalManifestSha256",
        ):
            self.assertIn(
                f"AfterCapacityCheckpoint.{field} "
                f"== BeforeCapacityCheckpoint.{field}",
                compact,
            )
        self.assertIn(
            (
                "AfterCapacityCheckpoint.Chunks.Num() "
                "== BeforeCapacityCheckpoint.Chunks.Num()"
            ),
            compact,
        )
        self.assertIn(
            (
                'TestTrue(TEXT("Capacity refusal preserves complete '
                'checkpoint identity"), '
                "AfterCapacityCheckpoint.TargetStableId "
                "== BeforeCapacityCheckpoint.TargetStableId"
            ),
            compact,
        )
        self.assertIn(
            (
                "for (int32 ChunkIndex = 0; ChunkIndex < "
                "BeforeCapacityCheckpoint.Chunks.Num(); ++ChunkIndex)"
            ),
            compact,
        )
        for expression in (
            (
                "const FChunkCheckpoint& BeforeChunk = "
                "BeforeCapacityCheckpoint.Chunks[ChunkIndex]"
            ),
            (
                "const FChunkCheckpoint& AfterChunk = "
                "AfterCapacityCheckpoint.Chunks[ChunkIndex]"
            ),
            "AfterChunk.TargetStableId == BeforeChunk.TargetStableId",
            (
                "AfterChunk.ChunkCoordinate "
                "== BeforeChunk.ChunkCoordinate"
            ),
            "AfterChunk.ThroughRevision == BeforeChunk.ThroughRevision",
            (
                "AfterChunk.VolumeSpecSha256 "
                "== BeforeChunk.VolumeSpecSha256"
            ),
            (
                "AfterChunk.CanonicalPayloadSha256 "
                "== BeforeChunk.CanonicalPayloadSha256"
            ),
            (
            "AfterChunk.CompressedDensityAndMaterial "
                "== BeforeChunk.CompressedDensityAndMaterial"
            ),
        ):
            self.assertIn(expression, compact)
        self.assertIn(
            (
                "TestTrue( FString::Printf( TEXT(\"Capacity refusal "
                "preserves checkpoint chunk %d\"), ChunkIndex), "
                "AfterChunk.TargetStableId == BeforeChunk.TargetStableId"
            ),
            compact,
        )
        for field in (
            "TargetStableId",
            "VolumeSpecSha256",
            "BaseCheckpointRevision",
            "BaseCheckpointManifestSha256",
            "BaseJournalTailSha256",
            "ThroughRevision",
            "FinalJournalTailSha256",
            "CanonicalManifestSha256",
        ):
            self.assertIn(
                f"AfterCapacityExport.{field} "
                f"== BeforeCapacityExport.{field}",
                compact,
            )
        for field in (
            "OperationId",
            "ResultContentSha256",
            "PreviousOperationSha256",
            "CanonicalOperationSha256",
        ):
            self.assertIn(
                f"RetainedFirstOperation.{field} "
                f"== FirstOperation.{field}",
                compact,
            )
        self.assertIn(
            (
                'TestTrue(TEXT("Capacity refusal preserves the complete '
                'one-operation suffix"), '
                "AfterCapacityExport.TargetStableId "
                "== BeforeCapacityExport.TargetStableId"
            ),
            compact,
        )

    def test_capture_alone_does_not_release_but_exact_acknowledgement_does(
        self,
    ):
        body = self.capacity_source
        compact = self.capacity_compact
        release_capture = body.index(
            "const bool bCapturedCapacityReleaseRequest"
        )
        capture_only_refusal = body.index(
            "const bool bCaptureOnlyCapacityRejectionHandled"
        )
        release_ack = body.index(
            "const bool bAcknowledgedCapacityRelease"
        )
        released_export = body.index(
            "const bool bExportedReleasedCapacity"
        )
        self.assertLess(release_capture, capture_only_refusal)
        self.assertLess(capture_only_refusal, release_ack)
        self.assertLess(release_ack, released_export)
        self.assertIn(
            (
                'TestTrue(TEXT("Checkpoint capture alone does not '
                'release journal capacity"), '
                "bCaptureOnlyCapacityRejectionHandled && "
                "!CaptureOnlyCapacityResult.bAccepted"
            ),
            compact,
        )
        self.assertIn(
            (
                "TestTrue( FString::Printf( TEXT(\"The untouched exact "
                "ticket acknowledges after capture-only refusal: %s\"), "
                "*Error), bAcknowledgedCapacityRelease)"
            ),
            compact,
        )
        self.assertIn(
            (
                'TestTrue(TEXT("Exact acknowledgement releases the sole '
                'journal slot"), '
                "ReleasedCapacityExport.TargetStableId == VolumeStableId"
            ),
            compact,
        )
        for expression in (
            "CapacityReleaseRequest.Ticket.bExpectedAcknowledgedBase",
            (
                "CapacityReleaseRequest.Ticket."
                "ExpectedJournalBaseRevision == uint64(0)"
            ),
            (
                "CapacityReleaseRequest.Ticket."
                "ExpectedBaseCheckpointManifestSha256 "
                "== RevisionZeroRequest.Ticket."
                "CheckpointManifestSha256"
            ),
            (
                "CapacityReleaseRequest.Ticket."
                "ExpectedBaseJournalTailSha256 "
                "== RevisionZeroRequest.Ticket."
                "CheckpointJournalTailSha256"
            ),
            (
                "CapacityReleaseRequest.Ticket."
                "CheckpointThroughRevision == uint64(1)"
            ),
            (
                "CapacityReleaseRequest.Ticket."
                "CheckpointManifestSha256 "
                "== BeforeCapacityCheckpoint."
                "CanonicalManifestSha256"
            ),
            (
                "CapacityReleaseRequest.Ticket."
                "CheckpointJournalTailSha256 "
                "== FirstOperation.CanonicalOperationSha256"
            ),
            (
                "const bool bCaptureOnlyCapacityRejectionHandled = "
                "Backend.ApplyValidatedEdit( CapacityEdit, "
                "CaptureOnlyCapacityResult, Error)"
            ),
            (
                "!CaptureOnlyCapacityResult.bAccepted && "
                "CaptureOnlyCapacityResult.RejectReason == "
                "EEditRejectReason::JournalCapacityReached"
            ),
            (
                "CapacityReleaseAcknowledgement.Ticket "
                "= CapacityReleaseRequest.Ticket"
            ),
            (
                "const bool bAcknowledgedCapacityRelease = "
                "Backend.AcknowledgePersistedCheckpoint( "
                "CapacityReleaseAcknowledgement, Error)"
            ),
            "ReleasedCapacityExport.BaseCheckpointRevision == uint64(1)",
            "ReleasedCapacityExport.ThroughRevision == uint64(1)",
            "ReleasedCapacityExport.Operations.IsEmpty()",
            (
                "ReleasedCapacityExport.BaseCheckpointManifestSha256 "
                "== CapacityReleaseRequest.Ticket."
                "CheckpointManifestSha256"
            ),
            (
                "ReleasedCapacityExport.BaseJournalTailSha256 "
                "== CapacityReleaseRequest.Ticket."
                "CheckpointJournalTailSha256"
            ),
            (
                "ReleasedCapacityExport.FinalJournalTailSha256 "
                "== CapacityReleaseRequest.Ticket."
                "CheckpointJournalTailSha256"
            ),
            (
                "ValidateEditJournalExport( ReleasedCapacityExport, "
                "Limits, &ReleasedExportValidationError)"
            ),
            (
                "AfterReleaseCheckpoint.CanonicalManifestSha256 "
                "== BeforeCapacityCheckpoint.CanonicalManifestSha256"
            ),
        ):
            self.assertIn(expression, compact)

    def test_identical_refused_edit_retries_and_rechains_after_release(
        self,
    ):
        body = self.capacity_source
        compact = self.capacity_compact
        first_refusal = body.index(
            "const bool bCapacityRejectionHandled"
        )
        accepted_retry = body.index(
            "const bool bRetriedCapacityEditAccepted"
        )
        final_export = body.index("const bool bExportedFinal")
        self.assertLess(first_refusal, accepted_retry)
        self.assertLess(accepted_retry, final_export)
        immutable_retry_span = body[first_refusal:accepted_retry]
        mutation_patterns = (
            r"(?:\+\+|--)\s*CapacityEdit\b",
            r"\bCapacityEdit\s*(?:\+\+|--)",
            r"\bCapacityEdit\s*(?:[+\-*/%&|^]?=(?!=))",
            r"(?:\+\+|--)\s*CapacityEdit\.\w+",
            (
                r"\bCapacityEdit\.\w+\s*"
                r"(?:\+\+|--|[+\-*/%&|^]?=(?!=))"
            ),
            r"\bCapacityEdit(?:\.\w+)+\s*\(",
        )
        for pattern in mutation_patterns:
            self.assertIsNone(re.search(pattern, immutable_retry_span))
        release_ticket_start = body.index(
            "const bool bCapturedCapacityReleaseRequest"
        )
        release_ticket_end = body.index(
            "CapacityReleaseAcknowledgement.Ticket"
        )
        immutable_ticket_span = body[
            release_ticket_start:release_ticket_end
        ]
        ticket_mutation_patterns = (
            (
                r"(?:\+\+|--)\s*"
                r"CapacityReleaseRequest\.Ticket(?:\.\w+)?"
            ),
            (
                r"CapacityReleaseRequest\.Ticket(?:\.\w+)?\s*"
                r"(?:\+\+|--|[+\-*/%&|^]?=(?!=))"
            ),
            (
                r"CapacityReleaseRequest\.Ticket"
                r"(?:\.\w+)+\s*\("
            ),
        )
        for pattern in ticket_mutation_patterns:
            self.assertIsNone(re.search(pattern, immutable_ticket_span))
        for assertion in (
            (
                "TestTrue( FString::Printf( TEXT(\"The identical refused "
                "edit succeeds after exact acknowledgement: %s\"), "
                "*Error), bRetriedCapacityEditAccepted && "
                "RetriedCapacityResult.bAccepted)"
            ),
            (
                'TestTrue(TEXT("The retry preserves exact request '
                'identity and advances once"), '
                "RetriedCapacityResult.TargetStableId "
                "== CapacityEdit.TargetStableId"
            ),
            (
                'TestTrue(TEXT("The retried operation rechains from the '
                'acknowledged checkpoint"), '
                "FinalExport.TargetStableId == VolumeStableId"
            ),
            (
                'TestTrue(TEXT("The successful retry changes the '
                'checkpoint exactly once"), '
                "bCapturedFinalCheckpoint && "
                "FinalCheckpoint.ThroughRevision == uint64(2)"
            ),
            (
                'TestTrue(TEXT("Journal compaction cannot change '
                'authoritative density"), '
                "AfterReleaseCheckpoint.TargetStableId "
                "== BeforeCapacityCheckpoint.TargetStableId"
            ),
        ):
            self.assertIn(assertion, compact)
        for expression in (
            (
                "const bool bRetriedCapacityEditAccepted = "
                "Backend.ApplyValidatedEdit( CapacityEdit, "
                "RetriedCapacityResult, Error)"
            ),
            "RetriedCapacityResult.bAccepted",
            (
                "RetriedCapacityResult.TargetStableId "
                "== CapacityEdit.TargetStableId"
            ),
            (
                "RetriedCapacityResult.RequestSequence "
                "== CapacityEdit.RequestSequence"
            ),
            (
                "RetriedCapacityResult.PredictionToken "
                "== CapacityEdit.PredictionToken"
            ),
            (
                "RetriedCapacityResult.AuthorityGenerationToken "
                "== CapacityEdit.AuthorityGenerationToken"
            ),
            (
                "RetriedCapacityResult.RejectReason "
                "== EEditRejectReason::None"
            ),
            "RetriedCapacityResult.PreviousRevision == uint64(1)",
            "RetriedCapacityResult.AppliedRevision == uint64(2)",
            "RetriedCapacityResult.TotalRemovedCellCount == 1",
            "FinalExport.BaseCheckpointRevision == uint64(1)",
            "FinalExport.ThroughRevision == uint64(2)",
            (
                "RetriedOperation.PreviousOperationSha256 "
                "== CapacityReleaseRequest.Ticket."
                "CheckpointJournalTailSha256"
            ),
            (
                "RetriedOperation.RequestSequence "
                "== CapacityEdit.RequestSequence"
            ),
            (
                "RetriedOperation.PredictionToken "
                "== CapacityEdit.PredictionToken"
            ),
            "RetriedOperation.PreviousRevision == uint64(1)",
            "RetriedOperation.Revision == uint64(2)",
            "RetriedOperation.RemovedCellCount == 1",
            (
                "FinalExport.FinalJournalTailSha256 "
                "== RetriedOperation.CanonicalOperationSha256"
            ),
            (
                "ValidateEditJournalExport( FinalExport, Limits, "
                "&FinalExportValidationError)"
            ),
            "FinalCheckpoint.ThroughRevision == uint64(2)",
            (
                "FinalCheckpoint.CanonicalManifestSha256 "
                "!= BeforeCapacityCheckpoint.CanonicalManifestSha256"
            ),
        ):
            self.assertIn(expression, compact)

    def test_journal_capacity_release_scope_excludes_lifecycle_and_runtime(
        self,
    ):
        body = self.capacity_source
        compact = self.capacity_compact
        for forbidden in (
            "ReleaseVolume",
            "RestoreCheckpointSetAtomically",
            "InspectCheckpointSet",
            "ECheckpointRestoreMode",
            "InitializeAbsentVolume",
            "ReplaceQuiescedVolume",
            "FRedInMemorySparseVoxelBackend SecondBackend",
            "SecondVolumeStableId",
            "QueueChunkRebuild",
            "CompleteChunkRebuild",
            "InvalidateBuildsOlderThan",
            "QueryGeneratedOutputState",
            "AActor",
            "UWorld",
            "OpenLevel",
            "LoadMap",
            "Inventory",
            "ProceduralMesh",
            "DynamicMesh",
            "VoxelPlugin",
            "Steam",
            "IFileManager",
            "FArchive",
        ):
            self.assertNotIn(forbidden, body)
        for forbidden in (
            "++CapacityReleaseRequest.Ticket.PersistenceRequestToken",
            "--CapacityReleaseRequest.Ticket.PersistenceRequestToken",
        ):
            self.assertNotIn(forbidden, compact)
        for mutation in (
            r"CapacityReleaseRequest\.Ticket\."
            r"CheckpointManifestSha256\s*=(?!=)",
            r"CapacityReleaseRequest\.Ticket\."
            r"CheckpointJournalTailSha256\s*=(?!=)",
        ):
            self.assertIsNone(re.search(mutation, body))

    def test_generation_cas_release_rejects_aba_and_preserves_live_state(
        self,
    ):
        body = self.release_source
        compact = self.release_compact
        first_init = body.index("const bool bFirstInitialized")
        exact_first_release = body.index(
            "const bool bReleasedFirstGeneration"
        )
        second_init = body.index("const bool bSecondInitialized")
        before_stale_capture = body.index(
            "const bool bCapturedBeforeStaleRelease"
        )
        stale_release = body.index("const bool bAcceptedStaleRelease")
        after_stale_capture = body.index(
            "const bool bCapturedAfterStaleRelease"
        )
        exact_second_release = body.index(
            "const bool bReleasedSecondGeneration"
        )
        third_init = body.index("const bool bThirdInitialized")
        self.assertLess(first_init, exact_first_release)
        self.assertLess(exact_first_release, second_init)
        self.assertLess(second_init, before_stale_capture)
        self.assertLess(before_stale_capture, stale_release)
        self.assertLess(stale_release, after_stale_capture)
        self.assertLess(after_stale_capture, exact_second_release)
        self.assertLess(exact_second_release, third_init)

        self.assertEqual(body.count("Backend.InitializeVolume("), 3)
        self.assertEqual(body.count("Backend.ReleaseVolume("), 6)
        self.assertEqual(body.count("Backend.CaptureCheckpointSet("), 3)
        self.assertEqual(body.count("ApplyAcceptedEdit("), 1)
        for expression in (
            (
                "const bool bAcceptedStaleRelease = "
                "Backend.ReleaseVolume( VolumeStableId, "
                "FirstGeneration, Error)"
            ),
            (
                "const bool bAcceptedFutureRelease = "
                "Backend.ReleaseVolume( VolumeStableId, "
                "SecondGeneration + 1, Error)"
            ),
            (
                "const bool bReleasedSecondGeneration = "
                "Backend.ReleaseVolume( VolumeStableId, "
                "SecondGeneration, Error)"
            ),
            (
                "Backend.ReleaseVolume( VolumeStableId, 0, Error)"
            ),
            (
                "Backend.ReleaseVolume( VolumeStableId, "
                "FirstGeneration, Error)"
            ),
            (
                "Backend.ReleaseVolume( VolumeStableId, "
                "SecondGeneration + 1, Error)"
            ),
            (
                "Backend.ReleaseVolume( VolumeStableId, "
                "SecondGeneration, Error)"
            ),
            (
                "SecondGeneration, FirstGeneration + 1"
            ),
            (
                "ThirdGeneration, SecondGeneration + 1"
            ),
            (
                "Backend.GetCurrentRevision(VolumeStableId) == uint64(1)"
            ),
            (
                "Backend.GetAuthorityGenerationToken(VolumeStableId) "
                "== SecondGeneration"
            ),
            (
                "AfterStaleReleaseCheckpoint.CanonicalManifestSha256 "
                "== BeforeStaleReleaseCheckpoint.CanonicalManifestSha256"
            ),
            (
                "AfterChunk.CompressedDensityAndMaterial "
                "== BeforeChunk.CompressedDensityAndMaterial"
            ),
        ):
            self.assertIn(expression, compact)
        for diagnostic in (
            "nonzero authority generation token",
            "target does not exist",
            "stale or future authority generation",
        ):
            self.assertIn(diagnostic, body)

    def test_generation_cas_release_scenario_is_backend_only(self):
        body = self.release_source
        for forbidden in (
            "RestoreCheckpointSetAtomically",
            "InspectCheckpointSet",
            "QueueChunkRebuild",
            "CompleteChunkRebuild",
            "InvalidateBuildsOlderThan",
            "AActor",
            "UWorld",
            "OpenLevel",
            "LoadMap",
            "Inventory",
            "ProceduralMesh",
            "DynamicMesh",
            "VoxelPlugin",
            "Steam",
            "IFileManager",
            "FArchive",
        ):
            self.assertNotIn(forbidden, body)

    def test_native_harness_remains_backend_only(self):
        for forbidden in (
            "AActor",
            "UWorld",
            "OpenLevel",
            "LoadMap",
            "Inventory",
            "ProceduralMesh",
            "DynamicMesh",
            "VoxelPlugin",
            "Steam",
        ):
            self.assertNotIn(forbidden, self.source)


if __name__ == "__main__":
    unittest.main()
