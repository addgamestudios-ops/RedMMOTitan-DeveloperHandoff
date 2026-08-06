#if WITH_DEV_AUTOMATION_TESTS

#include "RedInMemorySparseVoxelBackend.h"
#include "Misc/AutomationTest.h"

namespace RedVoxelMiningTests
{
	const FName VolumeStableId(TEXT("asteroid.red.m12.native-journal"));
	const FName CollectorStableId(TEXT("player.red.m12.native-journal"));
	const FName MiningToolStableId(TEXT("tool.red.m12.hand-miner"));
	const FName PrototypeMaterialTableId(TEXT("red.material-table.prototype-v1"));

	RedVoxelMining::FVolumeSpec MakeVolumeSpec()
	{
		RedVoxelMining::FVolumeSpec Spec;
		Spec.StableId = VolumeStableId;
		Spec.MaterialTableId = PrototypeMaterialTableId;
		Spec.VolumeCellDimensions = FIntVector(16, 16, 16);
		Spec.ChunkCellDimensions = FIntVector(8, 8, 8);
		Spec.CellSizeCm = 100.f;
		Spec.BaseSeed = 0x4D31324AU;
		Spec.GenerationVersion = 1;
		return Spec;
	}

	bool ApplyAcceptedEdit(
		FRedInMemorySparseVoxelBackend& Backend,
		const uint64 RequestSequence,
		const FVector& LocalBrushCenter,
		RedVoxelMining::FApplyResult& OutResult,
		FString& OutError)
	{
		RedVoxelMining::FValidatedEdit Edit;
		Edit.TargetStableId = VolumeStableId;
		Edit.CollectorStableId = CollectorStableId;
		Edit.MiningToolStableId = MiningToolStableId;
		Edit.RequestSequence = RequestSequence;
		Edit.ExpectedRevision = Backend.GetCurrentRevision(VolumeStableId);
		Edit.LocalBrushCenter = LocalBrushCenter;
		Edit.LocalSurfaceNormal = FVector::UpVector;
		Edit.BrushRadiusCm = 25.f;
		Edit.AuthorityGenerationToken =
			Backend.GetAuthorityGenerationToken(VolumeStableId);
		Edit.PredictionToken = FGuid::NewGuid();

		return Backend.ApplyValidatedEdit(Edit, OutResult, OutError)
			&& OutResult.bAccepted;
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FRedVoxelJournalCheckpointPersistenceTest,
	"RedMMO.Mining.VoxelBackend.JournalCheckpointPersistence",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRedVoxelJournalCheckpointPersistenceTest::RunTest(
	const FString& Parameters)
{
	using namespace RedVoxelMining;
	using namespace RedVoxelMiningTests;
	(void)Parameters;

	FAuthorityLimits Limits;
	FVolumeSpec Spec = MakeVolumeSpec();
	FString CanonicalSpecSha256;
	const bool bFingerprintComputed =
		ComputeCanonicalVolumeSpecSha256(Spec, CanonicalSpecSha256);
	TestTrue(TEXT("The bounded volume spec receives a canonical fingerprint"),
		bFingerprintComputed);
	if (!bFingerprintComputed)
	{
		return false;
	}
	Spec.CanonicalSpecSha256 = MoveTemp(CanonicalSpecSha256);

	FRedInMemorySparseVoxelBackend Backend;
	FString Error;
	const bool bInitialized = Backend.InitializeVolume(Spec, Limits, Error);
	TestTrue(
		FString::Printf(TEXT("The bounded volume initializes: %s"), *Error),
		bInitialized);
	if (!bInitialized)
	{
		return false;
	}
	TestEqual(TEXT("A new volume begins at revision zero"),
		Backend.GetCurrentRevision(VolumeStableId), uint64(0));
	TestTrue(TEXT("A new volume has a live authority generation"),
		Backend.GetAuthorityGenerationToken(VolumeStableId) > uint64(0));

	FEditJournalExport BeforeAcknowledgement;
	const bool bExportedWithoutBase = Backend.ExportOperationJournal(
		VolumeStableId, BeforeAcknowledgement, Error);
	TestFalse(TEXT("Journal export fails before a checkpoint is acknowledged"),
		bExportedWithoutBase);
	TestFalse(TEXT("The refused early export explains its failure"),
		Error.IsEmpty());

	FApplyResult FirstResult;
	const bool bFirstEditAccepted = ApplyAcceptedEdit(
		Backend,
		1,
		FVector(-250.0, -50.0, -50.0),
		FirstResult,
		Error);
	TestTrue(
		FString::Printf(TEXT("The first deterministic cell edit is accepted: %s"), *Error),
		bFirstEditAccepted);
	if (!bFirstEditAccepted)
	{
		return false;
	}
	TestEqual(TEXT("The first edit begins at revision zero"),
		FirstResult.PreviousRevision, uint64(0));
	TestEqual(TEXT("The first edit advances to revision one"),
		FirstResult.AppliedRevision, uint64(1));
	TestEqual(TEXT("The first edit preserves its collector sequence"),
		FirstResult.RequestSequence, uint64(1));
	TestTrue(TEXT("The accepted first edit has no rejection reason"),
		FirstResult.RejectReason == EEditRejectReason::None);
	TestEqual(TEXT("The first bounded brush removes exactly one cell"),
		FirstResult.TotalRemovedCellCount, 1);

	FCheckpointPersistenceRequest FirstPersistenceRequest;
	const bool bCapturedFirstCheckpoint =
		Backend.CaptureCheckpointForPersistence(
			VolumeStableId, FirstPersistenceRequest, Error);
	TestTrue(
		FString::Printf(TEXT("Revision one receives a persistence ticket: %s"), *Error),
		bCapturedFirstCheckpoint);
	if (!bCapturedFirstCheckpoint)
	{
		return false;
	}
	TestEqual(TEXT("The first persistence ticket covers revision one"),
		FirstPersistenceRequest.Ticket.CheckpointThroughRevision, uint64(1));
	TestEqual(TEXT("The captured checkpoint covers revision one"),
		FirstPersistenceRequest.Checkpoint.ThroughRevision, uint64(1));
	FString PersistenceValidationError;
	const bool bPersistenceRequestValid =
		ValidateCheckpointPersistenceRequest(
			FirstPersistenceRequest, &PersistenceValidationError);
	TestTrue(
		FString::Printf(
			TEXT("The issued persistence envelope validates: %s"),
			*PersistenceValidationError),
		bPersistenceRequestValid);

	const FCheckpointPersistenceTicket& FirstTicket =
		FirstPersistenceRequest.Ticket;
	TestEqual(TEXT("The ticket targets the initialized volume"),
		FirstTicket.TargetStableId, Spec.StableId);
	TestEqual(TEXT("The ticket binds the canonical volume spec"),
		FirstTicket.VolumeSpecSha256, Spec.CanonicalSpecSha256);
	TestFalse(TEXT("The first ticket expects no acknowledged base"),
		FirstTicket.bExpectedAcknowledgedBase);
	TestEqual(TEXT("The first ticket expects revision-zero journal base"),
		FirstTicket.ExpectedJournalBaseRevision, uint64(0));
	TestTrue(TEXT("The first ticket expects no prior checkpoint manifest"),
		FirstTicket.ExpectedBaseCheckpointManifestSha256.IsEmpty());
	TestTrue(TEXT("The first ticket expects no prior journal tail"),
		FirstTicket.ExpectedBaseJournalTailSha256.IsEmpty());
	TestEqual(TEXT("The ticket binds the captured checkpoint manifest"),
		FirstTicket.CheckpointManifestSha256,
		FirstPersistenceRequest.Checkpoint.CanonicalManifestSha256);
	TestEqual(TEXT("The ticket binds the live authority generation"),
		FirstTicket.AuthorityGenerationToken,
		Backend.GetAuthorityGenerationToken(VolumeStableId));
	TestTrue(TEXT("The ticket carries a backend-instance capability"),
		FirstTicket.BackendInstanceId.IsValid());
	TestTrue(TEXT("The ticket carries a nonzero persistence request token"),
		FirstTicket.PersistenceRequestToken > uint64(0));

	FApplyResult SecondResult;
	const bool bSecondEditAccepted = ApplyAcceptedEdit(
		Backend,
		2,
		FVector(250.0, -50.0, -50.0),
		SecondResult,
		Error);
	TestTrue(
		FString::Printf(TEXT("A later edit is accepted before acknowledgement: %s"), *Error),
		bSecondEditAccepted);
	if (!bSecondEditAccepted)
	{
		return false;
	}
	TestEqual(TEXT("The later edit begins at revision one"),
		SecondResult.PreviousRevision, uint64(1));
	TestEqual(TEXT("The later edit advances to revision two"),
		SecondResult.AppliedRevision, uint64(2));
	TestEqual(TEXT("The later edit preserves its collector sequence"),
		SecondResult.RequestSequence, uint64(2));
	TestTrue(TEXT("The accepted later edit has no rejection reason"),
		SecondResult.RejectReason == EEditRejectReason::None);
	TestEqual(TEXT("The later bounded brush removes exactly one cell"),
		SecondResult.TotalRemovedCellCount, 1);

	FCheckpointPersistenceAcknowledgement FirstAcknowledgement;
	FirstAcknowledgement.Ticket = FirstPersistenceRequest.Ticket;
	FCheckpointPersistenceAcknowledgement WrongTokenAcknowledgement =
		FirstAcknowledgement;
	++WrongTokenAcknowledgement.Ticket.PersistenceRequestToken;
	const bool bAcceptedWrongToken =
		Backend.AcknowledgePersistedCheckpoint(
			WrongTokenAcknowledgement, Error);
	TestFalse(TEXT("A reconstructed persistence token is rejected"),
		bAcceptedWrongToken);
	TestFalse(TEXT("The rejected acknowledgement explains its failure"),
		Error.IsEmpty());
	TestTrue(TEXT("Wrong token reaches the exact pending-ticket rejection"),
		Error.Contains(TEXT(
			"does not match the exact live pending ticket")));
	TestEqual(TEXT("A rejected acknowledgement cannot change live density"),
		Backend.GetCurrentRevision(VolumeStableId), uint64(2));

	FEditJournalExport AfterRejectedAcknowledgement;
	TestFalse(
		TEXT("A rejected acknowledgement cannot promote a checkpoint base"),
		Backend.ExportOperationJournal(
			VolumeStableId, AfterRejectedAcknowledgement, Error));

	const bool bAcknowledgedPrefix = Backend.AcknowledgePersistedCheckpoint(
		FirstAcknowledgement, Error);
	TestTrue(
		FString::Printf(
			TEXT("The exact revision-one checkpoint is acknowledged: %s"),
			*Error),
		bAcknowledgedPrefix);
	if (!bAcknowledgedPrefix)
	{
		return false;
	}

	FEditJournalExport Export;
	const bool bExportedSuffix = Backend.ExportOperationJournal(
		VolumeStableId, Export, Error);
	TestTrue(
		FString::Printf(TEXT("The later journal suffix remains exportable: %s"), *Error),
		bExportedSuffix);
	if (!bExportedSuffix)
	{
		return false;
	}
	TestEqual(TEXT("The acknowledged checkpoint becomes the revision-one base"),
		Export.BaseCheckpointRevision, uint64(1));
	TestEqual(TEXT("The export binds the acknowledged checkpoint manifest"),
		Export.BaseCheckpointManifestSha256,
		FirstPersistenceRequest.Ticket.CheckpointManifestSha256);
	TestEqual(TEXT("The export binds the acknowledged journal tail"),
		Export.BaseJournalTailSha256,
		FirstPersistenceRequest.Ticket.CheckpointJournalTailSha256);
	TestEqual(TEXT("The export reaches the live revision"),
		Export.ThroughRevision, uint64(2));
	TestEqual(TEXT("Only the edit after the checkpoint remains"),
		Export.Operations.Num(), 1);
	if (Export.Operations.Num() != 1)
	{
		return false;
	}

	const FEditOperation& RemainingOperation = Export.Operations[0];
	TestEqual(TEXT("The retained operation begins at the acknowledged revision"),
		RemainingOperation.PreviousRevision, uint64(1));
	TestEqual(TEXT("The retained operation ends at the live revision"),
		RemainingOperation.Revision, uint64(2));
	TestEqual(TEXT("The retained operation preserves its collector sequence"),
		RemainingOperation.RequestSequence, uint64(2));
	TestEqual(TEXT("The retained suffix chains from the checkpoint history tail"),
		RemainingOperation.PreviousOperationSha256,
		FirstPersistenceRequest.Ticket.CheckpointJournalTailSha256);
	TestEqual(TEXT("The export final tail is the retained operation fingerprint"),
		Export.FinalJournalTailSha256,
		RemainingOperation.CanonicalOperationSha256);
	TestEqual(TEXT("Prefix acknowledgement does not roll back live density"),
		Backend.GetCurrentRevision(VolumeStableId), uint64(2));

	FString JournalValidationError;
	const bool bJournalValid = ValidateEditJournalExport(
		Export, Limits, &JournalValidationError);
	TestTrue(
		FString::Printf(
			TEXT("The detached suffix validates canonically: %s"),
			*JournalValidationError),
		bJournalValid);

	const FString ManifestBeforeDuplicate =
		Export.CanonicalManifestSha256;
	const FGuid OperationBeforeDuplicate =
		RemainingOperation.OperationId;
	const bool bDuplicateAcknowledged =
		Backend.AcknowledgePersistedCheckpoint(
			FirstAcknowledgement, Error);
	TestTrue(
		FString::Printf(
			TEXT("An exact duplicate acknowledgement is idempotent: %s"),
			*Error),
		bDuplicateAcknowledged);

	FEditJournalExport AfterDuplicate;
	const bool bExportedAfterDuplicate = Backend.ExportOperationJournal(
		VolumeStableId, AfterDuplicate, Error);
	TestTrue(
		FString::Printf(
			TEXT("The retained suffix survives duplicate acknowledgement: %s"),
			*Error),
		bExportedAfterDuplicate);
	if (!bExportedAfterDuplicate)
	{
		return false;
	}
	TestEqual(TEXT("Duplicate acknowledgement cannot alter the export manifest"),
		AfterDuplicate.CanonicalManifestSha256, ManifestBeforeDuplicate);
	TestEqual(TEXT("Duplicate acknowledgement cannot move the journal base"),
		AfterDuplicate.BaseCheckpointRevision, uint64(1));
	TestEqual(TEXT("Duplicate acknowledgement cannot change the live revision"),
		AfterDuplicate.ThroughRevision, uint64(2));
	TestEqual(TEXT("Duplicate acknowledgement cannot discard the later operation"),
		AfterDuplicate.Operations.Num(), 1);
	if (AfterDuplicate.Operations.Num() == 1)
	{
		TestTrue(TEXT("Duplicate acknowledgement preserves operation identity"),
			AfterDuplicate.Operations[0].OperationId
				== OperationBeforeDuplicate);
	}

	return !HasAnyErrors();
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FRedVoxelCheckpointCorruptionRestoreInvalidationTest,
	"RedMMO.Mining.VoxelBackend.CheckpointCorruptionRestoreInvalidation",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRedVoxelCheckpointCorruptionRestoreInvalidationTest::RunTest(
	const FString& Parameters)
{
	using namespace RedVoxelMining;
	using namespace RedVoxelMiningTests;
	(void)Parameters;

	FAuthorityLimits Limits;
	FVolumeSpec Spec = MakeVolumeSpec();
	FString CanonicalSpecSha256;
	const bool bFingerprintComputed =
		ComputeCanonicalVolumeSpecSha256(Spec, CanonicalSpecSha256);
	TestTrue(TEXT("The restore fixture receives a canonical spec fingerprint"),
		bFingerprintComputed);
	if (!bFingerprintComputed)
	{
		return false;
	}
	Spec.CanonicalSpecSha256 = MoveTemp(CanonicalSpecSha256);

	FRedInMemorySparseVoxelBackend Backend;
	FString Error;
	const bool bInitialized = Backend.InitializeVolume(Spec, Limits, Error);
	TestTrue(
		FString::Printf(TEXT("The restore fixture initializes: %s"), *Error),
		bInitialized);
	if (!bInitialized)
	{
		return false;
	}

	FApplyResult FirstResult;
	const bool bFirstEditAccepted = ApplyAcceptedEdit(
		Backend,
		1,
		FVector(-250.0, -50.0, -50.0),
		FirstResult,
		Error);
	TestTrue(
		FString::Printf(TEXT("The restore fixture accepts edit one: %s"), *Error),
		bFirstEditAccepted);
	if (!bFirstEditAccepted)
	{
		return false;
	}

	FCheckpointPersistenceRequest FirstPersistenceRequest;
	const bool bCapturedFirstCheckpoint =
		Backend.CaptureCheckpointForPersistence(
			VolumeStableId,
			FirstPersistenceRequest,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The revision-one durability base is captured: %s"),
			*Error),
		bCapturedFirstCheckpoint);
	if (!bCapturedFirstCheckpoint)
	{
		return false;
	}

	FCheckpointPersistenceAcknowledgement FirstAcknowledgement;
	FirstAcknowledgement.Ticket = FirstPersistenceRequest.Ticket;
	const bool bAcknowledgedFirstCheckpoint =
		Backend.AcknowledgePersistedCheckpoint(
			FirstAcknowledgement,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The revision-one durability base is acknowledged: %s"),
			*Error),
		bAcknowledgedFirstCheckpoint);
	if (!bAcknowledgedFirstCheckpoint)
	{
		return false;
	}

	FApplyResult SecondResult;
	const bool bSecondEditAccepted = ApplyAcceptedEdit(
		Backend,
		2,
		FVector(250.0, -50.0, -50.0),
		SecondResult,
		Error);
	TestTrue(
		FString::Printf(TEXT("The restore fixture accepts edit two: %s"), *Error),
		bSecondEditAccepted);
	if (!bSecondEditAccepted)
	{
		return false;
	}

	FEditJournalExport PreRestoreExport;
	const bool bExportedPreRestoreSuffix = Backend.ExportOperationJournal(
		VolumeStableId,
		PreRestoreExport,
		Error);
	TestTrue(
		FString::Printf(
			TEXT("The pre-restore suffix is exportable: %s"),
			*Error),
		bExportedPreRestoreSuffix);
	if (!bExportedPreRestoreSuffix)
	{
		return false;
	}
	TestEqual(TEXT("The pre-restore export retains the revision-one base"),
		PreRestoreExport.BaseCheckpointRevision, uint64(1));
	TestEqual(TEXT("The pre-restore export reaches revision two"),
		PreRestoreExport.ThroughRevision, uint64(2));
	TestEqual(TEXT("The pre-restore export contains one later operation"),
		PreRestoreExport.Operations.Num(), 1);
	if (PreRestoreExport.Operations.Num() != 1)
	{
		return false;
	}
	const FString PreRestoreExportManifest =
		PreRestoreExport.CanonicalManifestSha256;
	const FGuid PreRestoreOperationId =
		PreRestoreExport.Operations[0].OperationId;

	FCheckpointPersistenceRequest PendingRestoreRequest;
	const bool bCapturedPendingRestoreCheckpoint =
		Backend.CaptureCheckpointForPersistence(
			VolumeStableId,
			PendingRestoreRequest,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The revision-two restore checkpoint is captured: %s"),
			*Error),
		bCapturedPendingRestoreCheckpoint);
	if (!bCapturedPendingRestoreCheckpoint)
	{
		return false;
	}
	TestEqual(TEXT("The restore checkpoint covers revision two"),
		PendingRestoreRequest.Checkpoint.ThroughRevision, uint64(2));

	FVolumeCheckpointVerification TrustedVerification;
	const bool bInspectedPristineCheckpoint = Backend.InspectCheckpointSet(
		PendingRestoreRequest.Checkpoint,
		TrustedVerification,
		Error);
	TestTrue(
		FString::Printf(
			TEXT("The pristine restore checkpoint validates: %s"),
			*Error),
		bInspectedPristineCheckpoint);
	if (!bInspectedPristineCheckpoint)
	{
		return false;
	}

	const uint64 PreRestoreGeneration =
		Backend.GetAuthorityGenerationToken(VolumeStableId);
	FCheckpointRestorePrecondition RestorePrecondition;
	RestorePrecondition.TargetStableId = VolumeStableId;
	RestorePrecondition.Mode =
		ECheckpointRestoreMode::ReplaceQuiescedVolume;
	RestorePrecondition.ExpectedCurrentRevision = 2;
	RestorePrecondition.ExpectedAuthorityGenerationToken =
		PreRestoreGeneration;

	FVolumeCheckpoint CorruptedCheckpoint =
		PendingRestoreRequest.Checkpoint;
	if (CorruptedCheckpoint.Chunks.IsEmpty()
		|| CorruptedCheckpoint.Chunks[0]
			.CompressedDensityAndMaterial.IsEmpty())
	{
		AddError(TEXT("Captured checkpoint contains no payload to corrupt"));
		return false;
	}
	CorruptedCheckpoint.Chunks[0]
		.CompressedDensityAndMaterial.Last() ^= static_cast<uint8>(1);

	FVolumeCheckpointVerification CorruptedVerification;
	const bool bInspectedCorruptedCheckpoint =
		Backend.InspectCheckpointSet(
			CorruptedCheckpoint,
			CorruptedVerification,
			Error);
	TestFalse(TEXT("A payload-corrupted checkpoint fails bounded inspection"),
		bInspectedCorruptedCheckpoint);
	TestFalse(TEXT("Corrupted checkpoint inspection explains its failure"),
		Error.IsEmpty());

	const bool bRestoredCorruptedCheckpoint =
		Backend.RestoreCheckpointSetAtomically(
			CorruptedCheckpoint,
			TrustedVerification,
			RestorePrecondition,
			Error);
	TestFalse(TEXT("A payload-corrupted checkpoint cannot replace live state"),
		bRestoredCorruptedCheckpoint);
	TestFalse(TEXT("Corrupted checkpoint restore explains its failure"),
		Error.IsEmpty());
	TestEqual(TEXT("Rejected corruption cannot change the live revision"),
		Backend.GetCurrentRevision(VolumeStableId), uint64(2));
	TestEqual(TEXT("Rejected corruption cannot advance authority generation"),
		Backend.GetAuthorityGenerationToken(VolumeStableId),
		PreRestoreGeneration);

	FVolumeCheckpoint AfterCorruptionCheckpoint;
	const bool bCapturedAfterCorruption = Backend.CaptureCheckpointSet(
		VolumeStableId,
		AfterCorruptionCheckpoint,
		Error);
	TestTrue(
		FString::Printf(
			TEXT("Live state remains capturable after corruption rejection: %s"),
			*Error),
		bCapturedAfterCorruption);
	if (!bCapturedAfterCorruption)
	{
		return false;
	}
	TestEqual(TEXT("Rejected corruption cannot change the live manifest"),
		AfterCorruptionCheckpoint.CanonicalManifestSha256,
		PendingRestoreRequest.Checkpoint.CanonicalManifestSha256);

	FEditJournalExport AfterCorruptionExport;
	const bool bExportedAfterCorruption = Backend.ExportOperationJournal(
		VolumeStableId,
		AfterCorruptionExport,
		Error);
	TestTrue(
		FString::Printf(
			TEXT("Rejected corruption preserves the live journal export: %s"),
			*Error),
		bExportedAfterCorruption);
	if (!bExportedAfterCorruption)
	{
		return false;
	}
	TestEqual(TEXT("Rejected corruption preserves the export manifest"),
		AfterCorruptionExport.CanonicalManifestSha256,
		PreRestoreExportManifest);
	TestEqual(TEXT("Rejected corruption preserves the suffix operation count"),
		AfterCorruptionExport.Operations.Num(), 1);
	if (AfterCorruptionExport.Operations.Num() != 1)
	{
		return false;
	}
	TestTrue(TEXT("Rejected corruption preserves suffix operation identity"),
		AfterCorruptionExport.Operations[0].OperationId
			== PreRestoreOperationId);

	const bool bRestoredPristineCheckpoint =
		Backend.RestoreCheckpointSetAtomically(
			PendingRestoreRequest.Checkpoint,
			TrustedVerification,
			RestorePrecondition,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The exact revision-two checkpoint restores atomically: %s"),
			*Error),
		bRestoredPristineCheckpoint);
	if (!bRestoredPristineCheckpoint)
	{
		return false;
	}
	TestEqual(TEXT("Exact restore preserves checkpoint revision"),
		Backend.GetCurrentRevision(VolumeStableId), uint64(2));
	TestEqual(TEXT("Exact restore advances authority generation once"),
		Backend.GetAuthorityGenerationToken(VolumeStableId),
		PreRestoreGeneration + 1);

	FVolumeCheckpoint RestoredLiveCheckpoint;
	const bool bCapturedRestoredLiveCheckpoint =
		Backend.CaptureCheckpointSet(
			VolumeStableId,
			RestoredLiveCheckpoint,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The restored live state remains canonically capturable: %s"),
			*Error),
		bCapturedRestoredLiveCheckpoint);
	if (!bCapturedRestoredLiveCheckpoint)
	{
		return false;
	}
	TestEqual(TEXT("Exact restore preserves checkpoint content identity"),
		RestoredLiveCheckpoint.CanonicalManifestSha256,
		PendingRestoreRequest.Checkpoint.CanonicalManifestSha256);

	const bool bAcceptedPriorBaseAcknowledgement =
		Backend.AcknowledgePersistedCheckpoint(
			FirstAcknowledgement,
			Error);
	TestFalse(TEXT("Restore invalidates the previously acknowledged base ticket"),
		bAcceptedPriorBaseAcknowledgement);
	TestTrue(TEXT("The prior base ticket is rejected as stale authority state"),
		Error.Contains(TEXT("targets stale or foreign authority state")));

	FCheckpointPersistenceAcknowledgement StaleAcknowledgement;
	StaleAcknowledgement.Ticket = PendingRestoreRequest.Ticket;
	const bool bAcceptedStaleAcknowledgement =
		Backend.AcknowledgePersistedCheckpoint(
			StaleAcknowledgement,
			Error);
	TestFalse(TEXT("Restore invalidates the pre-restore persistence ticket"),
		bAcceptedStaleAcknowledgement);
	TestTrue(TEXT("The old ticket is rejected as stale authority state"),
		Error.Contains(TEXT("targets stale or foreign authority state")));
	TestEqual(TEXT("Rejected stale acknowledgement cannot change generation"),
		Backend.GetAuthorityGenerationToken(VolumeStableId),
		PreRestoreGeneration + 1);

	FEditJournalExport ExportBeforeFreshAcknowledgement;
	const bool bExportedBeforeFreshAcknowledgement =
		Backend.ExportOperationJournal(
			VolumeStableId,
			ExportBeforeFreshAcknowledgement,
			Error);
	TestFalse(TEXT("Restore requires a fresh acknowledged durability base"),
		bExportedBeforeFreshAcknowledgement);
	TestTrue(TEXT("Blocked post-restore export names its durability gate"),
		Error.Contains(TEXT(
			"requires an explicitly acknowledged checkpoint base")));

	FCheckpointPersistenceRequest FreshPersistenceRequest;
	const bool bCapturedFreshCheckpoint =
		Backend.CaptureCheckpointForPersistence(
			VolumeStableId,
			FreshPersistenceRequest,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("A fresh post-restore checkpoint is captured: %s"),
			*Error),
		bCapturedFreshCheckpoint);
	if (!bCapturedFreshCheckpoint)
	{
		return false;
	}
	const FCheckpointPersistenceTicket& FreshTicket =
		FreshPersistenceRequest.Ticket;
	TestFalse(TEXT("The restored volume has no acknowledged durability base"),
		FreshTicket.bExpectedAcknowledgedBase);
	TestEqual(TEXT("Fresh persistence starts from restored revision two"),
		FreshTicket.ExpectedJournalBaseRevision, uint64(2));
	TestTrue(TEXT("Fresh persistence expects no prior checkpoint manifest"),
		FreshTicket.ExpectedBaseCheckpointManifestSha256.IsEmpty());
	TestTrue(TEXT("Fresh persistence expects no prior journal tail"),
		FreshTicket.ExpectedBaseJournalTailSha256.IsEmpty());
	TestTrue(TEXT("Fresh restored checkpoint has no retained operation tail"),
		FreshTicket.CheckpointJournalTailSha256.IsEmpty());
	TestEqual(TEXT("Fresh ticket binds the advanced authority generation"),
		FreshTicket.AuthorityGenerationToken,
		PreRestoreGeneration + 1);
	TestTrue(TEXT("Fresh persistence advances the request capability"),
		FreshTicket.PersistenceRequestToken
			> PendingRestoreRequest.Ticket.PersistenceRequestToken);
	TestEqual(TEXT("Fresh checkpoint preserves restored content identity"),
		FreshTicket.CheckpointManifestSha256,
		PendingRestoreRequest.Checkpoint.CanonicalManifestSha256);

	FEditJournalExport ExportAfterFreshCapture;
	TestFalse(TEXT("Capture alone cannot promote a durability base"),
		Backend.ExportOperationJournal(
			VolumeStableId,
			ExportAfterFreshCapture,
			Error));

	FCheckpointPersistenceAcknowledgement FreshAcknowledgement;
	FreshAcknowledgement.Ticket = FreshTicket;
	const bool bAcknowledgedFreshCheckpoint =
		Backend.AcknowledgePersistedCheckpoint(
			FreshAcknowledgement,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The fresh post-restore checkpoint is acknowledged: %s"),
			*Error),
		bAcknowledgedFreshCheckpoint);
	if (!bAcknowledgedFreshCheckpoint)
	{
		return false;
	}

	FEditJournalExport FreshBaselineExport;
	const bool bExportedFreshBaseline = Backend.ExportOperationJournal(
		VolumeStableId,
		FreshBaselineExport,
		Error);
	TestTrue(
		FString::Printf(
			TEXT("The fresh post-restore baseline exports: %s"),
			*Error),
		bExportedFreshBaseline);
	if (!bExportedFreshBaseline)
	{
		return false;
	}
	TestEqual(TEXT("Fresh export begins at restored revision two"),
		FreshBaselineExport.BaseCheckpointRevision, uint64(2));
	TestEqual(TEXT("Fresh export ends at restored revision two"),
		FreshBaselineExport.ThroughRevision, uint64(2));
	TestEqual(TEXT("Fresh export contains no stale pre-restore suffix"),
		FreshBaselineExport.Operations.Num(), 0);
	TestEqual(TEXT("Fresh export binds the newly acknowledged manifest"),
		FreshBaselineExport.BaseCheckpointManifestSha256,
		FreshTicket.CheckpointManifestSha256);
	TestTrue(TEXT("Fresh export has no stale base journal tail"),
		FreshBaselineExport.BaseJournalTailSha256.IsEmpty());
	TestTrue(TEXT("Fresh export has no stale final journal tail"),
		FreshBaselineExport.FinalJournalTailSha256.IsEmpty());
	TestTrue(TEXT("Fresh export identity differs from pre-restore suffix"),
		FreshBaselineExport.CanonicalManifestSha256
			!= PreRestoreExportManifest);

	FString FreshExportValidationError;
	const bool bFreshExportValid = ValidateEditJournalExport(
		FreshBaselineExport,
		Limits,
		&FreshExportValidationError);
	TestTrue(
		FString::Printf(
			TEXT("The fresh post-restore export validates: %s"),
			*FreshExportValidationError),
		bFreshExportValid);

	return !HasAnyErrors();
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FRedVoxelPersistenceTicketReissueTest,
	"RedMMO.Mining.VoxelBackend.PersistenceTicketReissue",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRedVoxelPersistenceTicketReissueTest::RunTest(
	const FString& Parameters)
{
	using namespace RedVoxelMining;
	using namespace RedVoxelMiningTests;
	(void)Parameters;

	FAuthorityLimits Limits;
	FVolumeSpec Spec = MakeVolumeSpec();
	FString CanonicalSpecSha256;
	const bool bFingerprintComputed =
		ComputeCanonicalVolumeSpecSha256(Spec, CanonicalSpecSha256);
	TestTrue(TEXT("The reissue fixture receives a canonical spec fingerprint"),
		bFingerprintComputed);
	if (!bFingerprintComputed)
	{
		return false;
	}
	Spec.CanonicalSpecSha256 = MoveTemp(CanonicalSpecSha256);

	FRedInMemorySparseVoxelBackend Backend;
	FString Error;
	const bool bInitialized = Backend.InitializeVolume(Spec, Limits, Error);
	TestTrue(
		FString::Printf(TEXT("The reissue fixture initializes: %s"), *Error),
		bInitialized);
	if (!bInitialized)
	{
		return false;
	}

	FApplyResult FirstResult;
	const bool bFirstEditAccepted = ApplyAcceptedEdit(
		Backend,
		1,
		FVector(-250.0, -50.0, -50.0),
		FirstResult,
		Error);
	TestTrue(
		FString::Printf(TEXT("The reissue fixture accepts one edit: %s"), *Error),
		bFirstEditAccepted);
	if (!bFirstEditAccepted)
	{
		return false;
	}
	TestEqual(TEXT("The reissue fixture reaches revision one"),
		Backend.GetCurrentRevision(VolumeStableId), uint64(1));

	FCheckpointPersistenceRequest BasePersistenceRequest;
	const bool bCapturedBaseRequest =
		Backend.CaptureCheckpointForPersistence(
			VolumeStableId,
			BasePersistenceRequest,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The revision-one durability base is captured: %s"),
			*Error),
		bCapturedBaseRequest);
	if (!bCapturedBaseRequest)
	{
		return false;
	}

	FCheckpointPersistenceAcknowledgement BaseAcknowledgement;
	BaseAcknowledgement.Ticket = BasePersistenceRequest.Ticket;
	const bool bAcknowledgedBaseRequest =
		Backend.AcknowledgePersistedCheckpoint(
			BaseAcknowledgement,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The revision-one durability base is acknowledged: %s"),
			*Error),
		bAcknowledgedBaseRequest);
	if (!bAcknowledgedBaseRequest)
	{
		return false;
	}

	FApplyResult SecondResult;
	const bool bSecondEditAccepted = ApplyAcceptedEdit(
		Backend,
		2,
		FVector(250.0, -50.0, -50.0),
		SecondResult,
		Error);
	TestTrue(
		FString::Printf(TEXT("The reissue fixture accepts edit two: %s"), *Error),
		bSecondEditAccepted);
	if (!bSecondEditAccepted)
	{
		return false;
	}
	TestEqual(TEXT("The reissue fixture reaches revision two"),
		Backend.GetCurrentRevision(VolumeStableId), uint64(2));

	FEditJournalExport PreReissueExport;
	const bool bExportedPreReissueSuffix =
		Backend.ExportOperationJournal(
			VolumeStableId,
			PreReissueExport,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The revision-two suffix exports before reissue: %s"),
			*Error),
		bExportedPreReissueSuffix);
	if (!bExportedPreReissueSuffix)
	{
		return false;
	}
	TestEqual(TEXT("The pre-reissue export retains the revision-one base"),
		PreReissueExport.BaseCheckpointRevision, uint64(1));
	TestEqual(TEXT("The pre-reissue export reaches revision two"),
		PreReissueExport.ThroughRevision, uint64(2));
	TestEqual(TEXT("The pre-reissue export contains one suffix operation"),
		PreReissueExport.Operations.Num(), 1);
	if (PreReissueExport.Operations.Num() != 1)
	{
		return false;
	}
	const FString PreReissueExportManifest =
		PreReissueExport.CanonicalManifestSha256;
	const FGuid PreReissueOperationId =
		PreReissueExport.Operations[0].OperationId;

	FCheckpointPersistenceRequest FirstRequest;
	const bool bCapturedFirstRequest =
		Backend.CaptureCheckpointForPersistence(
			VolumeStableId,
			FirstRequest,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The first revision-two persistence request is captured: %s"),
			*Error),
		bCapturedFirstRequest);
	if (!bCapturedFirstRequest)
	{
		return false;
	}

	FCheckpointPersistenceRequest ReissuedRequest;
	const bool bCapturedReissuedRequest =
		Backend.CaptureCheckpointForPersistence(
			VolumeStableId,
			ReissuedRequest,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The unchanged revision-two request is reissued: %s"),
			*Error),
		bCapturedReissuedRequest);
	if (!bCapturedReissuedRequest)
	{
		return false;
	}

	FString FirstValidationError;
	const bool bFirstRequestValid =
		ValidateCheckpointPersistenceRequest(
			FirstRequest,
			&FirstValidationError);
	TestTrue(
		FString::Printf(
			TEXT("The first detached request validates: %s"),
			*FirstValidationError),
		bFirstRequestValid);
	FString ReissuedValidationError;
	const bool bReissuedRequestValid =
		ValidateCheckpointPersistenceRequest(
			ReissuedRequest,
			&ReissuedValidationError);
	TestTrue(
		FString::Printf(
			TEXT("The reissued detached request validates: %s"),
			*ReissuedValidationError),
		bReissuedRequestValid);

	const FCheckpointPersistenceTicket& FirstTicket = FirstRequest.Ticket;
	const FCheckpointPersistenceTicket& ReissuedTicket =
		ReissuedRequest.Ticket;
	TestEqual(TEXT("Reissue preserves the exact target"),
		ReissuedTicket.TargetStableId, FirstTicket.TargetStableId);
	TestEqual(TEXT("Reissue preserves the canonical volume spec"),
		ReissuedTicket.VolumeSpecSha256, FirstTicket.VolumeSpecSha256);
	TestEqual(TEXT("Reissue preserves acknowledged-base expectation"),
		ReissuedTicket.bExpectedAcknowledgedBase,
		FirstTicket.bExpectedAcknowledgedBase);
	TestTrue(TEXT("Reissue retains a real acknowledged durability base"),
		ReissuedTicket.bExpectedAcknowledgedBase);
	TestEqual(TEXT("Reissue preserves the expected journal base revision"),
		ReissuedTicket.ExpectedJournalBaseRevision,
		FirstTicket.ExpectedJournalBaseRevision);
	TestEqual(TEXT("Reissue expects the acknowledged revision-one base"),
		ReissuedTicket.ExpectedJournalBaseRevision, uint64(1));
	TestEqual(TEXT("Reissue preserves the expected base checkpoint manifest"),
		ReissuedTicket.ExpectedBaseCheckpointManifestSha256,
		FirstTicket.ExpectedBaseCheckpointManifestSha256);
	TestEqual(TEXT("Reissue binds the acknowledged base checkpoint manifest"),
		ReissuedTicket.ExpectedBaseCheckpointManifestSha256,
		BasePersistenceRequest.Ticket.CheckpointManifestSha256);
	TestEqual(TEXT("Reissue preserves the expected base journal tail"),
		ReissuedTicket.ExpectedBaseJournalTailSha256,
		FirstTicket.ExpectedBaseJournalTailSha256);
	TestEqual(TEXT("Reissue binds the acknowledged base journal tail"),
		ReissuedTicket.ExpectedBaseJournalTailSha256,
		BasePersistenceRequest.Ticket.CheckpointJournalTailSha256);
	TestEqual(TEXT("Reissue preserves the checkpoint revision"),
		ReissuedTicket.CheckpointThroughRevision,
		FirstTicket.CheckpointThroughRevision);
	TestEqual(TEXT("Reissue checkpoint covers revision two"),
		ReissuedTicket.CheckpointThroughRevision, uint64(2));
	TestEqual(TEXT("Reissue preserves the checkpoint manifest"),
		ReissuedTicket.CheckpointManifestSha256,
		FirstTicket.CheckpointManifestSha256);
	TestEqual(TEXT("Reissue preserves the checkpoint journal tail"),
		ReissuedTicket.CheckpointJournalTailSha256,
		FirstTicket.CheckpointJournalTailSha256);
	TestEqual(TEXT("Reissue preserves the authority generation"),
		ReissuedTicket.AuthorityGenerationToken,
		FirstTicket.AuthorityGenerationToken);
	TestTrue(TEXT("Reissue remains bound to the same backend instance"),
		ReissuedTicket.BackendInstanceId == FirstTicket.BackendInstanceId);
	TestTrue(TEXT("Reissue advances its persistence capability token"),
		ReissuedTicket.PersistenceRequestToken
			> FirstTicket.PersistenceRequestToken);
	TestEqual(TEXT("Reissue advances the capability token exactly once"),
		ReissuedTicket.PersistenceRequestToken
			- FirstTicket.PersistenceRequestToken,
		uint64(1));

	FCheckpointPersistenceAcknowledgement FirstAcknowledgement;
	FirstAcknowledgement.Ticket = FirstTicket;
	const bool bAcceptedSupersededTicket =
		Backend.AcknowledgePersistedCheckpoint(
			FirstAcknowledgement,
			Error);
	TestFalse(TEXT("The superseded persistence ticket is rejected"),
		bAcceptedSupersededTicket);
	TestTrue(TEXT("Superseded rejection names the exact pending capability"),
		Error.Contains(TEXT(
			"does not match the exact live pending ticket")));
	TestEqual(TEXT("Superseded rejection cannot change live revision"),
		Backend.GetCurrentRevision(VolumeStableId), uint64(2));

	FEditJournalExport ExportAfterSupersededRejection;
	const bool bExportedAfterSupersededRejection =
		Backend.ExportOperationJournal(
			VolumeStableId,
			ExportAfterSupersededRejection,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The earlier durability base remains exportable: %s"),
			*Error),
		bExportedAfterSupersededRejection);
	if (!bExportedAfterSupersededRejection)
	{
		return false;
	}
	TestEqual(TEXT("Superseded rejection cannot move the durability base"),
		ExportAfterSupersededRejection.BaseCheckpointRevision, uint64(1));
	TestEqual(TEXT("Superseded rejection cannot change export revision"),
		ExportAfterSupersededRejection.ThroughRevision, uint64(2));
	TestEqual(TEXT("Superseded rejection cannot compact the live suffix"),
		ExportAfterSupersededRejection.Operations.Num(), 1);
	TestEqual(TEXT("Superseded rejection preserves export identity"),
		ExportAfterSupersededRejection.CanonicalManifestSha256,
		PreReissueExportManifest);
	if (ExportAfterSupersededRejection.Operations.Num() == 1)
	{
		TestTrue(TEXT("Superseded rejection preserves suffix operation identity"),
			ExportAfterSupersededRejection.Operations[0].OperationId
				== PreReissueOperationId);
	}

	FCheckpointPersistenceAcknowledgement ReissuedAcknowledgement;
	ReissuedAcknowledgement.Ticket = ReissuedTicket;
	const bool bAcknowledgedReissuedTicket =
		Backend.AcknowledgePersistedCheckpoint(
			ReissuedAcknowledgement,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The exact reissued persistence ticket is acknowledged: %s"),
			*Error),
		bAcknowledgedReissuedTicket);
	if (!bAcknowledgedReissuedTicket)
	{
		return false;
	}

	FEditJournalExport ReissuedBaselineExport;
	const bool bExportedReissuedBaseline =
		Backend.ExportOperationJournal(
			VolumeStableId,
			ReissuedBaselineExport,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The reissued durability baseline exports: %s"),
			*Error),
		bExportedReissuedBaseline);
	if (!bExportedReissuedBaseline)
	{
		return false;
	}
	TestEqual(TEXT("The reissued base starts at revision two"),
		ReissuedBaselineExport.BaseCheckpointRevision, uint64(2));
	TestEqual(TEXT("The reissued base reaches revision two"),
		ReissuedBaselineExport.ThroughRevision, uint64(2));
	TestEqual(TEXT("The reissued base contains no suffix operations"),
		ReissuedBaselineExport.Operations.Num(), 0);
	TestEqual(TEXT("The reissued base binds the exact checkpoint manifest"),
		ReissuedBaselineExport.BaseCheckpointManifestSha256,
		ReissuedTicket.CheckpointManifestSha256);
	TestEqual(TEXT("The reissued base binds the exact checkpoint journal tail"),
		ReissuedBaselineExport.BaseJournalTailSha256,
		ReissuedTicket.CheckpointJournalTailSha256);
	TestEqual(TEXT("The empty suffix retains the acknowledged history tail"),
		ReissuedBaselineExport.FinalJournalTailSha256,
		ReissuedTicket.CheckpointJournalTailSha256);

	FString ExportValidationError;
	const bool bReissuedExportValid = ValidateEditJournalExport(
		ReissuedBaselineExport,
		Limits,
		&ExportValidationError);
	TestTrue(
		FString::Printf(
			TEXT("The reissued baseline validates canonically: %s"),
			*ExportValidationError),
		bReissuedExportValid);

	return !HasAnyErrors();
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FRedVoxelGeneratedOutputRoleIsolationAndStaleCompletionTest,
	"RedMMO.Mining.VoxelBackend.GeneratedOutputRoleIsolationAndStaleCompletion",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRedVoxelGeneratedOutputRoleIsolationAndStaleCompletionTest::RunTest(
	const FString& Parameters)
{
	using namespace RedVoxelMining;
	using namespace RedVoxelMiningTests;
	(void)Parameters;

	FAuthorityLimits Limits;
	FVolumeSpec Spec = MakeVolumeSpec();
	FString CanonicalSpecSha256;
	const bool bFingerprintComputed =
		ComputeCanonicalVolumeSpecSha256(Spec, CanonicalSpecSha256);
	TestTrue(TEXT("The generated-output fixture receives a canonical fingerprint"),
		bFingerprintComputed);
	if (!bFingerprintComputed)
	{
		return false;
	}
	Spec.CanonicalSpecSha256 = MoveTemp(CanonicalSpecSha256);

	FRedInMemorySparseVoxelBackend Backend;
	FString Error;
	const bool bInitialized = Backend.InitializeVolume(Spec, Limits, Error);
	TestTrue(
		FString::Printf(
			TEXT("The generated-output fixture initializes: %s"),
			*Error),
		bInitialized);
	if (!bInitialized)
	{
		return false;
	}

	const FIntVector TargetChunk(0, 0, 0);
	const FIntVector UnrelatedChunk(1, 0, 0);
	FChunkRevision InitialTargetRevision;
	const bool bReadInitialTargetRevision = Backend.ReadChunkRevision(
		VolumeStableId,
		TargetChunk,
		InitialTargetRevision,
		Error);
	TestTrue(
		FString::Printf(
			TEXT("The target chunk exposes its initial revision: %s"),
			*Error),
		bReadInitialTargetRevision);
	if (!bReadInitialTargetRevision)
	{
		return false;
	}
	FChunkRevision InitialUnrelatedRevision;
	const bool bReadInitialUnrelatedRevision = Backend.ReadChunkRevision(
		VolumeStableId,
		UnrelatedChunk,
		InitialUnrelatedRevision,
		Error);
	TestTrue(
		FString::Printf(
			TEXT("The unrelated chunk exposes its initial revision: %s"),
			*Error),
		bReadInitialUnrelatedRevision);
	if (!bReadInitialUnrelatedRevision)
	{
		return false;
	}
	TestEqual(TEXT("The target chunk starts at content revision zero"),
		InitialTargetRevision.ContentRevision, uint64(0));
	TestEqual(TEXT("The unrelated chunk starts at content revision zero"),
		InitialUnrelatedRevision.ContentRevision, uint64(0));
	TestTrue(TEXT("Both chunks share one live authority generation"),
		InitialTargetRevision.GenerationToken
			== InitialUnrelatedRevision.GenerationToken
		&& InitialTargetRevision.GenerationToken > uint64(0));

	FGeneratedChunkOutputState InitialTargetState;
	const bool bQueriedInitialTargetState =
		Backend.QueryGeneratedOutputState(
			VolumeStableId,
			TargetChunk,
			InitialTargetState,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The target output state is queryable: %s"),
			*Error),
		bQueriedInitialTargetState);
	if (!bQueriedInitialTargetState)
	{
		return false;
	}
	TestTrue(TEXT("The target output identity matches its initial revision"),
		InitialTargetState.TargetStableId
				== InitialTargetRevision.TargetStableId
			&& InitialTargetState.ChunkCoordinate
				== InitialTargetRevision.ChunkCoordinate
			&& InitialTargetState.ContentRevision
				== InitialTargetRevision.ContentRevision
			&& InitialTargetState.ContentSha256
				== InitialTargetRevision.ContentSha256
			&& InitialTargetState.GenerationToken
				== InitialTargetRevision.GenerationToken);
	TestFalse(TEXT("Initial target presentation is not fabricated ready"),
		InitialTargetState.bPresentationReady);
	TestFalse(TEXT("Initial target collision is not fabricated ready"),
		InitialTargetState.bCollisionReady);
	TestTrue(TEXT("Initial target presentation has no output fingerprint"),
		InitialTargetState.PresentationOutputSha256.IsEmpty());
	TestTrue(TEXT("Initial target collision has no output fingerprint"),
		InitialTargetState.CollisionOutputSha256.IsEmpty());

	FGeneratedChunkOutputState InitialUnrelatedState;
	const bool bQueriedInitialUnrelatedState =
		Backend.QueryGeneratedOutputState(
			VolumeStableId,
			UnrelatedChunk,
			InitialUnrelatedState,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The unrelated output state is queryable: %s"),
			*Error),
		bQueriedInitialUnrelatedState);
	if (!bQueriedInitialUnrelatedState)
	{
		return false;
	}
	TestTrue(TEXT("The unrelated output identity matches its initial revision"),
		InitialUnrelatedState.TargetStableId
				== InitialUnrelatedRevision.TargetStableId
			&& InitialUnrelatedState.ChunkCoordinate
				== InitialUnrelatedRevision.ChunkCoordinate
			&& InitialUnrelatedState.ContentRevision
				== InitialUnrelatedRevision.ContentRevision
			&& InitialUnrelatedState.ContentSha256
				== InitialUnrelatedRevision.ContentSha256
			&& InitialUnrelatedState.GenerationToken
				== InitialUnrelatedRevision.GenerationToken);
	TestFalse(TEXT("Initial unrelated presentation is not fabricated ready"),
		InitialUnrelatedState.bPresentationReady);
	TestFalse(TEXT("Initial unrelated collision is not fabricated ready"),
		InitialUnrelatedState.bCollisionReady);
	TestTrue(TEXT("Initial unrelated presentation has no output fingerprint"),
		InitialUnrelatedState.PresentationOutputSha256.IsEmpty());
	TestTrue(TEXT("Initial unrelated collision has no output fingerprint"),
		InitialUnrelatedState.CollisionOutputSha256.IsEmpty());

	FGeneratedChunkBuildRequest RejectedCombinedRequest;
	const bool bQueuedCombinedRole = Backend.QueueChunkRebuild(
		InitialTargetRevision,
		EGeneratedOutputRequirement::PresentationAndCollision,
		RejectedCombinedRequest,
		Error);
	TestFalse(TEXT("One ticket cannot authorize both generated-output roles"),
		bQueuedCombinedRole);
	TestTrue(TEXT("Combined-role rejection names the single-role boundary"),
		Error.Contains(TEXT("must authorize exactly one output role")));
	TestEqual(TEXT("Rejected combined-role request remains default"),
		RejectedCombinedRequest.Ticket.BuildRequestToken,
		uint64(0));
	FGeneratedChunkOutputState AfterCombinedRoleRejection;
	const bool bQueriedAfterCombinedRoleRejection =
		Backend.QueryGeneratedOutputState(
			VolumeStableId,
			TargetChunk,
			AfterCombinedRoleRejection,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("Combined-role rejection leaves target state queryable: %s"),
			*Error),
		bQueriedAfterCombinedRoleRejection);
	TestTrue(TEXT("Combined-role rejection cannot mutate target identity"),
		AfterCombinedRoleRejection.TargetStableId
				== InitialTargetState.TargetStableId
			&& AfterCombinedRoleRejection.ChunkCoordinate
				== InitialTargetState.ChunkCoordinate
			&& AfterCombinedRoleRejection.ContentRevision
				== InitialTargetState.ContentRevision
			&& AfterCombinedRoleRejection.ContentSha256
				== InitialTargetState.ContentSha256
			&& AfterCombinedRoleRejection.GenerationToken
				== InitialTargetState.GenerationToken);
	TestFalse(TEXT("Combined-role rejection cannot ready presentation"),
		AfterCombinedRoleRejection.bPresentationReady);
	TestFalse(TEXT("Combined-role rejection cannot ready collision"),
		AfterCombinedRoleRejection.bCollisionReady);
	TestTrue(TEXT("Combined-role rejection cannot install presentation output"),
		AfterCombinedRoleRejection.PresentationOutputSha256
			== InitialTargetState.PresentationOutputSha256);
	TestTrue(TEXT("Combined-role rejection cannot install collision output"),
		AfterCombinedRoleRejection.CollisionOutputSha256
			== InitialTargetState.CollisionOutputSha256);

	FGeneratedChunkBuildRequest InitialTargetPresentationRequest;
	const bool bQueuedInitialTargetPresentation =
		Backend.QueueChunkRebuild(
			InitialTargetRevision,
			EGeneratedOutputRequirement::Presentation,
			InitialTargetPresentationRequest,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("Initial target presentation work is queued: %s"),
			*Error),
		bQueuedInitialTargetPresentation);
	if (!bQueuedInitialTargetPresentation)
	{
		return false;
	}
	FGeneratedChunkBuildRequest InitialTargetCollisionRequest;
	const bool bQueuedInitialTargetCollision =
		Backend.QueueChunkRebuild(
			InitialTargetRevision,
			EGeneratedOutputRequirement::Collision,
			InitialTargetCollisionRequest,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("Initial target collision work is queued independently: %s"),
			*Error),
		bQueuedInitialTargetCollision);
	if (!bQueuedInitialTargetCollision)
	{
		return false;
	}
	FGeneratedChunkBuildRequest UnrelatedPresentationRequest;
	const bool bQueuedUnrelatedPresentation =
		Backend.QueueChunkRebuild(
			InitialUnrelatedRevision,
			EGeneratedOutputRequirement::Presentation,
			UnrelatedPresentationRequest,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("Unrelated presentation work is queued independently: %s"),
			*Error),
		bQueuedUnrelatedPresentation);
	if (!bQueuedUnrelatedPresentation)
	{
		return false;
	}
	TestTrue(TEXT("Target presentation ticket authorizes presentation only"),
		InitialTargetPresentationRequest.Ticket.OutputRole
			== EGeneratedOutputRequirement::Presentation);
	TestTrue(TEXT("Target collision ticket authorizes collision only"),
		InitialTargetCollisionRequest.Ticket.OutputRole
			== EGeneratedOutputRequirement::Collision);
	TestTrue(TEXT("Target role tickets bind the same immutable source"),
		InitialTargetPresentationRequest.Ticket.SourceRevision.TargetStableId
				== InitialTargetCollisionRequest.Ticket.SourceRevision.TargetStableId
			&& InitialTargetPresentationRequest.Ticket.SourceRevision.ChunkCoordinate
				== InitialTargetCollisionRequest.Ticket.SourceRevision.ChunkCoordinate
			&& InitialTargetPresentationRequest.Ticket.SourceRevision.ContentRevision
				== InitialTargetCollisionRequest.Ticket.SourceRevision.ContentRevision
			&& InitialTargetPresentationRequest.Ticket.SourceRevision.ContentSha256
				== InitialTargetCollisionRequest.Ticket.SourceRevision.ContentSha256
			&& InitialTargetPresentationRequest.Ticket.SourceRevision.GenerationToken
				== InitialTargetCollisionRequest.Ticket.SourceRevision.GenerationToken);
	TestTrue(TEXT("Target role tickets bind one backend instance"),
		InitialTargetPresentationRequest.Ticket.BackendInstanceId
			== InitialTargetCollisionRequest.Ticket.BackendInstanceId);
	TestEqual(TEXT("Collision queue consumes the next capability token"),
		InitialTargetCollisionRequest.Ticket.BuildRequestToken
			- InitialTargetPresentationRequest.Ticket.BuildRequestToken,
		uint64(1));
	TestEqual(TEXT("Rejected combined-role queue consumes no capability token"),
		InitialTargetPresentationRequest.Ticket.BuildRequestToken,
		uint64(1));
	TestEqual(TEXT("Unrelated queue consumes the next capability token"),
		UnrelatedPresentationRequest.Ticket.BuildRequestToken
			- InitialTargetCollisionRequest.Ticket.BuildRequestToken,
		uint64(1));
	TestTrue(TEXT("Target role requests carry one exact immutable snapshot"),
		InitialTargetPresentationRequest.CanonicalDensityAndMaterial
			== InitialTargetCollisionRequest.CanonicalDensityAndMaterial);

	const FString InitialTargetPresentationSha256(
		TEXT("1111111111111111111111111111111111111111111111111111111111111111"));
	const FString InitialTargetCollisionSha256(
		TEXT("2222222222222222222222222222222222222222222222222222222222222222"));
	const FString UnrelatedPresentationSha256(
		TEXT("3333333333333333333333333333333333333333333333333333333333333333"));
	const FString SupersededPresentationSha256(
		TEXT("4444444444444444444444444444444444444444444444444444444444444444"));
	const FString FreshCollisionSha256(
		TEXT("5555555555555555555555555555555555555555555555555555555555555555"));
	const FString FreshPresentationSha256(
		TEXT("6666666666666666666666666666666666666666666666666666666666666666"));
	const FString ConflictingPresentationSha256(
		TEXT("7777777777777777777777777777777777777777777777777777777777777777"));

	FGeneratedChunkBuildCompletion InitialTargetPresentationCompletion;
	InitialTargetPresentationCompletion.Ticket =
		InitialTargetPresentationRequest.Ticket;
	InitialTargetPresentationCompletion.OutputSha256 =
		InitialTargetPresentationSha256;
	const bool bCompletedInitialTargetPresentation =
		Backend.CompleteChunkRebuild(
			InitialTargetPresentationCompletion,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("Initial target presentation completes independently: %s"),
			*Error),
		bCompletedInitialTargetPresentation);
	if (!bCompletedInitialTargetPresentation)
	{
		return false;
	}

	FGeneratedChunkOutputState PresentationOnlyState;
	const bool bQueriedPresentationOnlyState =
		Backend.QueryGeneratedOutputState(
			VolumeStableId,
			TargetChunk,
			PresentationOnlyState,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("Presentation-only target state is queryable: %s"),
			*Error),
		bQueriedPresentationOnlyState);
	TestTrue(TEXT("Presentation completes without fabricating collision"),
		PresentationOnlyState.bPresentationReady
			&& !PresentationOnlyState.bCollisionReady);
	TestEqual(TEXT("Presentation stores its exact output fingerprint"),
		PresentationOnlyState.PresentationOutputSha256,
		InitialTargetPresentationSha256);
	TestTrue(TEXT("Pending collision retains no accepted fingerprint"),
		PresentationOnlyState.CollisionOutputSha256.IsEmpty());
	TestTrue(TEXT("Presentation-only state satisfies presentation"),
		AreGeneratedOutputsCurrent(
			InitialTargetRevision,
			PresentationOnlyState,
			EGeneratedOutputRequirement::Presentation));
	TestFalse(TEXT("Presentation-only state cannot satisfy collision"),
		AreGeneratedOutputsCurrent(
			InitialTargetRevision,
			PresentationOnlyState,
			EGeneratedOutputRequirement::Collision));
	TestFalse(TEXT("Presentation-only state cannot satisfy both roles"),
		AreGeneratedOutputsCurrent(
			InitialTargetRevision,
			PresentationOnlyState,
			EGeneratedOutputRequirement::PresentationAndCollision));

	FGeneratedChunkBuildCompletion InitialTargetCollisionCompletion;
	InitialTargetCollisionCompletion.Ticket =
		InitialTargetCollisionRequest.Ticket;
	InitialTargetCollisionCompletion.OutputSha256 =
		InitialTargetCollisionSha256;
	const bool bCompletedInitialTargetCollision =
		Backend.CompleteChunkRebuild(
			InitialTargetCollisionCompletion,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("Pending initial collision survives presentation completion: %s"),
			*Error),
		bCompletedInitialTargetCollision);
	if (!bCompletedInitialTargetCollision)
	{
		return false;
	}
	FGeneratedChunkOutputState InitialBothRolesReadyState;
	const bool bQueriedInitialBothRolesReadyState =
		Backend.QueryGeneratedOutputState(
			VolumeStableId,
			TargetChunk,
			InitialBothRolesReadyState,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The initial two-role target state is queryable: %s"),
			*Error),
		bQueriedInitialBothRolesReadyState);
	TestTrue(TEXT("Initial completions ready both independent roles"),
		InitialBothRolesReadyState.bPresentationReady
			&& InitialBothRolesReadyState.bCollisionReady);
	TestEqual(TEXT("Initial two-role state retains presentation output"),
		InitialBothRolesReadyState.PresentationOutputSha256,
		InitialTargetPresentationSha256);
	TestEqual(TEXT("Initial two-role state retains collision output"),
		InitialBothRolesReadyState.CollisionOutputSha256,
		InitialTargetCollisionSha256);
	TestTrue(TEXT("Initial exact completions satisfy both roles"),
		AreGeneratedOutputsCurrent(
			InitialTargetRevision,
			InitialBothRolesReadyState,
			EGeneratedOutputRequirement::PresentationAndCollision));

	FApplyResult EditResult;
	const bool bEditAccepted = ApplyAcceptedEdit(
		Backend,
		1,
		FVector(-250.0, -50.0, -50.0),
		EditResult,
		Error);
	TestTrue(
		FString::Printf(
			TEXT("The deterministic target-chunk edit is accepted: %s"),
			*Error),
		bEditAccepted);
	if (!bEditAccepted)
	{
		return false;
	}
	TestEqual(TEXT("The deterministic edit dirties one chunk"),
		EditResult.DirtyChunkCoordinates.Num(), 1);
	if (EditResult.DirtyChunkCoordinates.Num() != 1)
	{
		return false;
	}
	TestTrue(TEXT("The deterministic edit dirties only the target chunk"),
		EditResult.DirtyChunkCoordinates[0] == TargetChunk);
	TestEqual(TEXT("The target edit advances the global volume revision"),
		Backend.GetCurrentRevision(VolumeStableId), uint64(1));

	FChunkRevision UpdatedTargetRevision;
	const bool bReadUpdatedTargetRevision = Backend.ReadChunkRevision(
		VolumeStableId,
		TargetChunk,
		UpdatedTargetRevision,
		Error);
	TestTrue(
		FString::Printf(
			TEXT("The edited target exposes its updated revision: %s"),
			*Error),
		bReadUpdatedTargetRevision);
	if (!bReadUpdatedTargetRevision)
	{
		return false;
	}
	FChunkRevision UpdatedUnrelatedRevision;
	const bool bReadUpdatedUnrelatedRevision = Backend.ReadChunkRevision(
		VolumeStableId,
		UnrelatedChunk,
		UpdatedUnrelatedRevision,
		Error);
	TestTrue(
		FString::Printf(
			TEXT("The unrelated chunk remains queryable after the edit: %s"),
			*Error),
		bReadUpdatedUnrelatedRevision);
	if (!bReadUpdatedUnrelatedRevision)
	{
		return false;
	}
	TestEqual(TEXT("The edited target advances to content revision one"),
		UpdatedTargetRevision.ContentRevision, uint64(1));
	TestTrue(TEXT("The edited target receives a new content fingerprint"),
		UpdatedTargetRevision.ContentSha256
			!= InitialTargetRevision.ContentSha256);
	TestEqual(TEXT("An unrelated chunk retains its content revision"),
		UpdatedUnrelatedRevision.ContentRevision,
		InitialUnrelatedRevision.ContentRevision);
	TestEqual(TEXT("An unrelated chunk retains its content fingerprint"),
		UpdatedUnrelatedRevision.ContentSha256,
		InitialUnrelatedRevision.ContentSha256);
	TestEqual(TEXT("The edit does not rotate authority generation"),
		UpdatedTargetRevision.GenerationToken,
		InitialTargetRevision.GenerationToken);
	TestEqual(TEXT("The unrelated chunk keeps that authority generation"),
		UpdatedUnrelatedRevision.GenerationToken,
		InitialUnrelatedRevision.GenerationToken);

	FGeneratedChunkOutputState EditedTargetState;
	const bool bQueriedEditedTargetState =
		Backend.QueryGeneratedOutputState(
			VolumeStableId,
			TargetChunk,
			EditedTargetState,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The edited target output state is queryable: %s"),
			*Error),
		bQueriedEditedTargetState);
	TestTrue(TEXT("The edited target output identity advances exactly"),
		EditedTargetState.ContentRevision
				== UpdatedTargetRevision.ContentRevision
			&& EditedTargetState.ContentSha256
				== UpdatedTargetRevision.ContentSha256
			&& EditedTargetState.GenerationToken
				== UpdatedTargetRevision.GenerationToken);
	TestFalse(TEXT("Editing invalidates presentation readiness"),
		EditedTargetState.bPresentationReady);
	TestFalse(TEXT("Editing invalidates collision readiness"),
		EditedTargetState.bCollisionReady);
	TestTrue(TEXT("Editing clears the presentation fingerprint"),
		EditedTargetState.PresentationOutputSha256.IsEmpty());
	TestTrue(TEXT("Editing clears the collision fingerprint"),
		EditedTargetState.CollisionOutputSha256.IsEmpty());

	const bool bAcceptedStalePresentationCompletion =
		Backend.CompleteChunkRebuild(
			InitialTargetPresentationCompletion,
			Error);
	TestFalse(TEXT("The pre-edit presentation completion becomes stale"),
		bAcceptedStalePresentationCompletion);
	TestTrue(TEXT("Stale presentation names the live-authority mismatch"),
		Error.Contains(TEXT(
			"completion is stale or does not match live authority")));
	FGeneratedChunkOutputState AfterStalePresentationCompletion;
	const bool bQueriedAfterStalePresentationCompletion =
		Backend.QueryGeneratedOutputState(
			VolumeStableId,
			TargetChunk,
			AfterStalePresentationCompletion,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The target remains queryable after stale presentation: %s"),
			*Error),
		bQueriedAfterStalePresentationCompletion);
	TestTrue(TEXT("Stale presentation preserves every target state field"),
		AfterStalePresentationCompletion.TargetStableId
				== EditedTargetState.TargetStableId
			&& AfterStalePresentationCompletion.ChunkCoordinate
				== EditedTargetState.ChunkCoordinate
			&& AfterStalePresentationCompletion.ContentRevision
				== EditedTargetState.ContentRevision
			&& AfterStalePresentationCompletion.ContentSha256
				== EditedTargetState.ContentSha256
			&& AfterStalePresentationCompletion.GenerationToken
				== EditedTargetState.GenerationToken
			&& AfterStalePresentationCompletion.bPresentationReady
				== EditedTargetState.bPresentationReady
			&& AfterStalePresentationCompletion.bCollisionReady
				== EditedTargetState.bCollisionReady
			&& AfterStalePresentationCompletion.PresentationOutputSha256
				== EditedTargetState.PresentationOutputSha256
			&& AfterStalePresentationCompletion.CollisionOutputSha256
				== EditedTargetState.CollisionOutputSha256);
	const bool bAcceptedStaleCollisionCompletion =
		Backend.CompleteChunkRebuild(
			InitialTargetCollisionCompletion,
			Error);
	TestFalse(TEXT("The pre-edit collision completion becomes stale"),
		bAcceptedStaleCollisionCompletion);
	TestTrue(TEXT("Stale collision names the live-authority mismatch"),
		Error.Contains(TEXT(
			"completion is stale or does not match live authority")));

	FGeneratedChunkOutputState AfterStaleTargetCompletions;
	const bool bQueriedAfterStaleTargetCompletions =
		Backend.QueryGeneratedOutputState(
			VolumeStableId,
			TargetChunk,
			AfterStaleTargetCompletions,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The target remains queryable after stale callbacks: %s"),
			*Error),
		bQueriedAfterStaleTargetCompletions);
	TestTrue(TEXT("Stale collision preserves every target state field"),
		AfterStaleTargetCompletions.TargetStableId
				== AfterStalePresentationCompletion.TargetStableId
			&& AfterStaleTargetCompletions.ChunkCoordinate
				== AfterStalePresentationCompletion.ChunkCoordinate
			&& AfterStaleTargetCompletions.ContentRevision
				== AfterStalePresentationCompletion.ContentRevision
			&& AfterStaleTargetCompletions.ContentSha256
				== AfterStalePresentationCompletion.ContentSha256
			&& AfterStaleTargetCompletions.GenerationToken
				== AfterStalePresentationCompletion.GenerationToken
			&& AfterStaleTargetCompletions.bPresentationReady
				== AfterStalePresentationCompletion.bPresentationReady
			&& AfterStaleTargetCompletions.bCollisionReady
				== AfterStalePresentationCompletion.bCollisionReady
			&& AfterStaleTargetCompletions.PresentationOutputSha256
				== AfterStalePresentationCompletion.PresentationOutputSha256
			&& AfterStaleTargetCompletions.CollisionOutputSha256
				== AfterStalePresentationCompletion.CollisionOutputSha256);
	TestFalse(TEXT("Stale callbacks cannot resurrect presentation"),
		AfterStaleTargetCompletions.bPresentationReady);
	TestFalse(TEXT("Stale callbacks cannot resurrect collision"),
		AfterStaleTargetCompletions.bCollisionReady);
	TestTrue(TEXT("Stale callbacks cannot install a presentation hash"),
		AfterStaleTargetCompletions.PresentationOutputSha256.IsEmpty());
	TestTrue(TEXT("Stale callbacks cannot install a collision hash"),
		AfterStaleTargetCompletions.CollisionOutputSha256.IsEmpty());

	FGeneratedChunkBuildCompletion UnrelatedPresentationCompletion;
	UnrelatedPresentationCompletion.Ticket =
		UnrelatedPresentationRequest.Ticket;
	UnrelatedPresentationCompletion.OutputSha256 =
		UnrelatedPresentationSha256;
	const bool bCompletedUnrelatedPresentation =
		Backend.CompleteChunkRebuild(
			UnrelatedPresentationCompletion,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("An unrelated pending completion survives the global edit: %s"),
			*Error),
		bCompletedUnrelatedPresentation);
	if (!bCompletedUnrelatedPresentation)
	{
		return false;
	}
	FGeneratedChunkOutputState UnrelatedAfterEditState;
	const bool bQueriedUnrelatedAfterEditState =
		Backend.QueryGeneratedOutputState(
			VolumeStableId,
			UnrelatedChunk,
			UnrelatedAfterEditState,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The completed unrelated state is queryable: %s"),
			*Error),
		bQueriedUnrelatedAfterEditState);
	TestTrue(TEXT("Unrelated presentation alone becomes ready"),
		UnrelatedAfterEditState.bPresentationReady
			&& !UnrelatedAfterEditState.bCollisionReady);
	TestEqual(TEXT("Unrelated completion stores its exact fingerprint"),
		UnrelatedAfterEditState.PresentationOutputSha256,
		UnrelatedPresentationSha256);
	TestTrue(TEXT("Unrelated completion remains current per chunk"),
		AreGeneratedOutputsCurrent(
			InitialUnrelatedRevision,
			UnrelatedAfterEditState,
			EGeneratedOutputRequirement::Presentation));
	TestEqual(TEXT("Unrelated completion does not roll back global revision"),
		Backend.GetCurrentRevision(VolumeStableId), uint64(1));

	FGeneratedChunkBuildRequest FreshPresentationRequest;
	const bool bQueuedFreshPresentation =
		Backend.QueueChunkRebuild(
			UpdatedTargetRevision,
			EGeneratedOutputRequirement::Presentation,
			FreshPresentationRequest,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("Fresh target presentation work is queued: %s"),
			*Error),
		bQueuedFreshPresentation);
	if (!bQueuedFreshPresentation)
	{
		return false;
	}
	FGeneratedChunkBuildRequest FreshCollisionRequest;
	const bool bQueuedFreshCollision =
		Backend.QueueChunkRebuild(
			UpdatedTargetRevision,
			EGeneratedOutputRequirement::Collision,
			FreshCollisionRequest,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("Fresh target collision work is queued independently: %s"),
			*Error),
		bQueuedFreshCollision);
	if (!bQueuedFreshCollision)
	{
		return false;
	}
	FGeneratedChunkBuildRequest FreshPresentationRetryRequest;
	const bool bRequeuedFreshPresentation =
		Backend.QueueChunkRebuild(
			UpdatedTargetRevision,
			EGeneratedOutputRequirement::Presentation,
			FreshPresentationRetryRequest,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("Fresh presentation requeue supersedes only its role: %s"),
			*Error),
		bRequeuedFreshPresentation);
	if (!bRequeuedFreshPresentation)
	{
		return false;
	}
	TestEqual(TEXT("Fresh collision queue consumes the next token"),
		FreshCollisionRequest.Ticket.BuildRequestToken
			- FreshPresentationRequest.Ticket.BuildRequestToken,
		uint64(1));
	TestEqual(TEXT("Fresh presentation retry consumes the next token"),
		FreshPresentationRetryRequest.Ticket.BuildRequestToken
			- FreshCollisionRequest.Ticket.BuildRequestToken,
		uint64(1));
	TestTrue(TEXT("Fresh presentation retry keeps the exact source identity"),
		FreshPresentationRetryRequest.Ticket.SourceRevision.TargetStableId
				== FreshPresentationRequest.Ticket.SourceRevision.TargetStableId
			&& FreshPresentationRetryRequest.Ticket.SourceRevision.ChunkCoordinate
				== FreshPresentationRequest.Ticket.SourceRevision.ChunkCoordinate
			&& FreshPresentationRetryRequest.Ticket.SourceRevision.ContentRevision
				== FreshPresentationRequest.Ticket.SourceRevision.ContentRevision
			&& FreshPresentationRetryRequest.Ticket.SourceRevision.ContentSha256
				== FreshPresentationRequest.Ticket.SourceRevision.ContentSha256
			&& FreshPresentationRetryRequest.Ticket.SourceRevision.GenerationToken
				== FreshPresentationRequest.Ticket.SourceRevision.GenerationToken);

	FGeneratedChunkOutputState BeforeSupersededPresentationCompletion;
	const bool bQueriedBeforeSupersededPresentationCompletion =
		Backend.QueryGeneratedOutputState(
			VolumeStableId,
			TargetChunk,
			BeforeSupersededPresentationCompletion,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The target is queryable before superseded completion: %s"),
			*Error),
		bQueriedBeforeSupersededPresentationCompletion);
	if (!bQueriedBeforeSupersededPresentationCompletion)
	{
		return false;
	}
	FGeneratedChunkBuildCompletion SupersededPresentationCompletion;
	SupersededPresentationCompletion.Ticket =
		FreshPresentationRequest.Ticket;
	SupersededPresentationCompletion.OutputSha256 =
		SupersededPresentationSha256;
	const bool bAcceptedSupersededPresentation =
		Backend.CompleteChunkRebuild(
			SupersededPresentationCompletion,
			Error);
	TestFalse(TEXT("The superseded presentation attempt is rejected"),
		bAcceptedSupersededPresentation);
	TestTrue(TEXT("Superseded presentation names the active-attempt mismatch"),
		Error.Contains(TEXT(
			"completion ticket is not the active role attempt")));
	FGeneratedChunkOutputState AfterSupersededPresentationCompletion;
	const bool bQueriedAfterSupersededPresentationCompletion =
		Backend.QueryGeneratedOutputState(
			VolumeStableId,
			TargetChunk,
			AfterSupersededPresentationCompletion,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The target remains queryable after superseded completion: %s"),
			*Error),
		bQueriedAfterSupersededPresentationCompletion);
	if (!bQueriedAfterSupersededPresentationCompletion)
	{
		return false;
	}
	TestTrue(TEXT("Superseded completion preserves every target state field"),
		AfterSupersededPresentationCompletion.TargetStableId
				== BeforeSupersededPresentationCompletion.TargetStableId
			&& AfterSupersededPresentationCompletion.ChunkCoordinate
				== BeforeSupersededPresentationCompletion.ChunkCoordinate
			&& AfterSupersededPresentationCompletion.ContentRevision
				== BeforeSupersededPresentationCompletion.ContentRevision
			&& AfterSupersededPresentationCompletion.ContentSha256
				== BeforeSupersededPresentationCompletion.ContentSha256
			&& AfterSupersededPresentationCompletion.GenerationToken
				== BeforeSupersededPresentationCompletion.GenerationToken
			&& AfterSupersededPresentationCompletion.bPresentationReady
				== BeforeSupersededPresentationCompletion.bPresentationReady
			&& AfterSupersededPresentationCompletion.bCollisionReady
				== BeforeSupersededPresentationCompletion.bCollisionReady
			&& AfterSupersededPresentationCompletion.PresentationOutputSha256
				== BeforeSupersededPresentationCompletion.PresentationOutputSha256
			&& AfterSupersededPresentationCompletion.CollisionOutputSha256
				== BeforeSupersededPresentationCompletion.CollisionOutputSha256);

	FGeneratedChunkBuildCompletion FreshCollisionCompletion;
	FreshCollisionCompletion.Ticket = FreshCollisionRequest.Ticket;
	FreshCollisionCompletion.OutputSha256 = FreshCollisionSha256;
	const bool bCompletedFreshCollision = Backend.CompleteChunkRebuild(
		FreshCollisionCompletion,
		Error);
	TestTrue(
		FString::Printf(
			TEXT("Collision survives same-chunk presentation requeue: %s"),
			*Error),
		bCompletedFreshCollision);
	if (!bCompletedFreshCollision)
	{
		return false;
	}

	FGeneratedChunkOutputState CollisionOnlyState;
	const bool bQueriedCollisionOnlyState =
		Backend.QueryGeneratedOutputState(
			VolumeStableId,
			TargetChunk,
			CollisionOnlyState,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("Collision-only target state is queryable: %s"),
			*Error),
		bQueriedCollisionOnlyState);
	TestFalse(TEXT("Presentation requeue leaves presentation unready"),
		CollisionOnlyState.bPresentationReady);
	TestTrue(TEXT("Collision completion readies only collision"),
		CollisionOnlyState.bCollisionReady);
	TestTrue(TEXT("Presentation requeue leaves no accepted presentation hash"),
		CollisionOnlyState.PresentationOutputSha256.IsEmpty());
	TestEqual(TEXT("Collision stores its exact output fingerprint"),
		CollisionOnlyState.CollisionOutputSha256,
		FreshCollisionSha256);
	TestFalse(TEXT("Collision-only state cannot satisfy presentation"),
		AreGeneratedOutputsCurrent(
			UpdatedTargetRevision,
			CollisionOnlyState,
			EGeneratedOutputRequirement::Presentation));
	TestTrue(TEXT("Collision-only state satisfies collision"),
		AreGeneratedOutputsCurrent(
			UpdatedTargetRevision,
			CollisionOnlyState,
			EGeneratedOutputRequirement::Collision));
	TestFalse(TEXT("Collision-only state cannot satisfy both roles"),
		AreGeneratedOutputsCurrent(
			UpdatedTargetRevision,
			CollisionOnlyState,
			EGeneratedOutputRequirement::PresentationAndCollision));

	FGeneratedChunkBuildCompletion FreshPresentationCompletion;
	FreshPresentationCompletion.Ticket =
		FreshPresentationRetryRequest.Ticket;
	FreshPresentationCompletion.OutputSha256 =
		FreshPresentationSha256;
	const bool bCompletedFreshPresentation =
		Backend.CompleteChunkRebuild(
			FreshPresentationCompletion,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The exact fresh presentation attempt completes: %s"),
			*Error),
		bCompletedFreshPresentation);
	if (!bCompletedFreshPresentation)
	{
		return false;
	}

	FGeneratedChunkOutputState BothRolesReadyState;
	const bool bQueriedBothRolesReadyState =
		Backend.QueryGeneratedOutputState(
			VolumeStableId,
			TargetChunk,
			BothRolesReadyState,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The two-role target state is queryable: %s"),
			*Error),
		bQueriedBothRolesReadyState);
	TestTrue(TEXT("Exact fresh completions ready both independent roles"),
		BothRolesReadyState.bPresentationReady
			&& BothRolesReadyState.bCollisionReady);
	TestEqual(TEXT("Final presentation fingerprint remains exact"),
		BothRolesReadyState.PresentationOutputSha256,
		FreshPresentationSha256);
	TestEqual(TEXT("Final collision fingerprint remains exact"),
		BothRolesReadyState.CollisionOutputSha256,
		FreshCollisionSha256);
	TestTrue(TEXT("The exact final state satisfies both roles"),
		AreGeneratedOutputsCurrent(
			UpdatedTargetRevision,
			BothRolesReadyState,
			EGeneratedOutputRequirement::PresentationAndCollision));

	const bool bAcceptedDuplicatePresentation =
		Backend.CompleteChunkRebuild(
			FreshPresentationCompletion,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("An exact duplicate presentation completion is idempotent: %s"),
			*Error),
		bAcceptedDuplicatePresentation);
	FGeneratedChunkOutputState AfterDuplicatePresentation;
	const bool bQueriedAfterDuplicatePresentation =
		Backend.QueryGeneratedOutputState(
			VolumeStableId,
			TargetChunk,
			AfterDuplicatePresentation,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The target remains queryable after exact duplicate: %s"),
			*Error),
		bQueriedAfterDuplicatePresentation);
	TestTrue(TEXT("Exact duplicate preserves every accepted state field"),
		AfterDuplicatePresentation.TargetStableId
				== BothRolesReadyState.TargetStableId
			&& AfterDuplicatePresentation.ChunkCoordinate
				== BothRolesReadyState.ChunkCoordinate
			&& AfterDuplicatePresentation.ContentRevision
				== BothRolesReadyState.ContentRevision
			&& AfterDuplicatePresentation.ContentSha256
				== BothRolesReadyState.ContentSha256
			&& AfterDuplicatePresentation.GenerationToken
				== BothRolesReadyState.GenerationToken
			&& AfterDuplicatePresentation.bPresentationReady
				== BothRolesReadyState.bPresentationReady
			&& AfterDuplicatePresentation.bCollisionReady
				== BothRolesReadyState.bCollisionReady
			&& AfterDuplicatePresentation.PresentationOutputSha256
				== BothRolesReadyState.PresentationOutputSha256
			&& AfterDuplicatePresentation.CollisionOutputSha256
				== BothRolesReadyState.CollisionOutputSha256);
	FGeneratedChunkBuildCompletion ConflictingPresentationCompletion =
		FreshPresentationCompletion;
	ConflictingPresentationCompletion.OutputSha256 =
		ConflictingPresentationSha256;
	const bool bAcceptedConflictingPresentation =
		Backend.CompleteChunkRebuild(
			ConflictingPresentationCompletion,
			Error);
	TestFalse(TEXT("A conflicting duplicate presentation is rejected"),
		bAcceptedConflictingPresentation);
	TestTrue(TEXT("Conflicting duplicate names accepted-output conflict"),
		Error.Contains(TEXT(
			"completion conflicts with the accepted role output")));

	FGeneratedChunkOutputState FinalTargetState;
	const bool bQueriedFinalTargetState =
		Backend.QueryGeneratedOutputState(
			VolumeStableId,
			TargetChunk,
			FinalTargetState,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The final target state remains queryable: %s"),
			*Error),
		bQueriedFinalTargetState);
	TestTrue(TEXT("Conflict rejection preserves every accepted state field"),
		FinalTargetState.TargetStableId
				== AfterDuplicatePresentation.TargetStableId
			&& FinalTargetState.ChunkCoordinate
				== AfterDuplicatePresentation.ChunkCoordinate
			&& FinalTargetState.ContentRevision
				== AfterDuplicatePresentation.ContentRevision
			&& FinalTargetState.ContentSha256
				== AfterDuplicatePresentation.ContentSha256
			&& FinalTargetState.GenerationToken
				== AfterDuplicatePresentation.GenerationToken
			&& FinalTargetState.bPresentationReady
				== AfterDuplicatePresentation.bPresentationReady
			&& FinalTargetState.bCollisionReady
				== AfterDuplicatePresentation.bCollisionReady
			&& FinalTargetState.PresentationOutputSha256
				== AfterDuplicatePresentation.PresentationOutputSha256
			&& FinalTargetState.CollisionOutputSha256
				== AfterDuplicatePresentation.CollisionOutputSha256);
	TestTrue(TEXT("Duplicate callbacks preserve both ready roles"),
		FinalTargetState.bPresentationReady
			&& FinalTargetState.bCollisionReady);
	TestEqual(TEXT("Conflicting duplicate cannot replace presentation output"),
		FinalTargetState.PresentationOutputSha256,
		FreshPresentationSha256);
	TestEqual(TEXT("Conflicting duplicate cannot replace collision output"),
		FinalTargetState.CollisionOutputSha256,
		FreshCollisionSha256);
	TestTrue(TEXT("Duplicate callbacks preserve exact current identity"),
		AreGeneratedOutputsCurrent(
			UpdatedTargetRevision,
			FinalTargetState,
			EGeneratedOutputRequirement::PresentationAndCollision));

	return !HasAnyErrors();
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FRedVoxelDeterministicInitializationTest,
	"RedMMO.Mining.VoxelBackend.DeterministicInitialization",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRedVoxelDeterministicInitializationTest::RunTest(
	const FString& Parameters)
{
	using namespace RedVoxelMining;
	using namespace RedVoxelMiningTests;
	(void)Parameters;

	FAuthorityLimits Limits;
	FVolumeSpec Spec = MakeVolumeSpec();
	FString CanonicalSpecSha256;
	const bool bFingerprintComputed =
		ComputeCanonicalVolumeSpecSha256(Spec, CanonicalSpecSha256);
	TestTrue(
		TEXT("The deterministic fixture receives a canonical fingerprint"),
		bFingerprintComputed);
	if (!bFingerprintComputed)
	{
		return false;
	}
	Spec.CanonicalSpecSha256 = MoveTemp(CanonicalSpecSha256);

	FRedInMemorySparseVoxelBackend FirstBackend;
	FRedInMemorySparseVoxelBackend SecondBackend;
	FString Error;
	const bool bFirstInitialized =
		FirstBackend.InitializeVolume(Spec, Limits, Error);
	TestTrue(
		FString::Printf(
			TEXT("The first deterministic fixture initializes: %s"),
			*Error),
		bFirstInitialized);
	if (!bFirstInitialized)
	{
		return false;
	}
	const bool bSecondInitialized =
		SecondBackend.InitializeVolume(Spec, Limits, Error);
	TestTrue(
		FString::Printf(
			TEXT("The second deterministic fixture initializes: %s"),
			*Error),
		bSecondInitialized);
	if (!bSecondInitialized)
	{
		return false;
	}

	TestTrue(TEXT("Both fresh backends contain the stable volume"),
		FirstBackend.HasVolume(VolumeStableId)
			&& SecondBackend.HasVolume(VolumeStableId));
	TestEqual(TEXT("The first deterministic volume begins at revision zero"),
		FirstBackend.GetCurrentRevision(VolumeStableId), uint64(0));
	TestEqual(TEXT("The second deterministic volume begins at revision zero"),
		SecondBackend.GetCurrentRevision(VolumeStableId), uint64(0));
	const uint64 FirstGeneration =
		FirstBackend.GetAuthorityGenerationToken(VolumeStableId);
	const uint64 SecondGeneration =
		SecondBackend.GetAuthorityGenerationToken(VolumeStableId);
	TestTrue(TEXT("Fresh backends issue the same first live generation"),
		FirstGeneration > uint64(0)
			&& FirstGeneration == SecondGeneration);

	FVolumeCheckpoint FirstCheckpoint;
	const bool bCapturedFirstCheckpoint =
		FirstBackend.CaptureCheckpointSet(
			VolumeStableId,
			FirstCheckpoint,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The first revision-zero checkpoint is captured: %s"),
			*Error),
		bCapturedFirstCheckpoint);
	if (!bCapturedFirstCheckpoint)
	{
		return false;
	}
	FVolumeCheckpoint SecondCheckpoint;
	const bool bCapturedSecondCheckpoint =
		SecondBackend.CaptureCheckpointSet(
			VolumeStableId,
			SecondCheckpoint,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The second revision-zero checkpoint is captured: %s"),
			*Error),
		bCapturedSecondCheckpoint);
	if (!bCapturedSecondCheckpoint)
	{
		return false;
	}

	const int32 ExpectedChunkCount =
		(Spec.VolumeCellDimensions.X / Spec.ChunkCellDimensions.X)
		* (Spec.VolumeCellDimensions.Y / Spec.ChunkCellDimensions.Y)
		* (Spec.VolumeCellDimensions.Z / Spec.ChunkCellDimensions.Z);
	TestEqual(TEXT("The bounded fixture contains exactly eight chunks"),
		ExpectedChunkCount, 8);
	TestEqual(TEXT("The first checkpoint covers every bounded chunk"),
		FirstCheckpoint.Chunks.Num(), ExpectedChunkCount);
	TestEqual(TEXT("The second checkpoint covers every bounded chunk"),
		SecondCheckpoint.Chunks.Num(), ExpectedChunkCount);
	if (FirstCheckpoint.Chunks.Num() != ExpectedChunkCount
		|| SecondCheckpoint.Chunks.Num() != ExpectedChunkCount)
	{
		return false;
	}
	TestTrue(TEXT("Both checkpoints bind the same canonical spec"),
		FirstCheckpoint.VolumeSpecSha256 == Spec.CanonicalSpecSha256
			&& SecondCheckpoint.VolumeSpecSha256
				== Spec.CanonicalSpecSha256);
	TestTrue(TEXT("Both checkpoint manifests are canonical fingerprints"),
		IsCanonicalSha256(FirstCheckpoint.CanonicalManifestSha256)
			&& IsCanonicalSha256(
				SecondCheckpoint.CanonicalManifestSha256));
	TestEqual(TEXT("Identical initialization yields one checkpoint manifest"),
		FirstCheckpoint.CanonicalManifestSha256,
		SecondCheckpoint.CanonicalManifestSha256);
	TestTrue(TEXT("Both checkpoints remain at revision zero"),
		FirstCheckpoint.ThroughRevision == uint64(0)
			&& SecondCheckpoint.ThroughRevision == uint64(0));

	for (int32 ChunkIndex = 0;
		ChunkIndex < ExpectedChunkCount;
		++ChunkIndex)
	{
		const FChunkCheckpoint& FirstChunk =
			FirstCheckpoint.Chunks[ChunkIndex];
		const FChunkCheckpoint& SecondChunk =
			SecondCheckpoint.Chunks[ChunkIndex];
		TestTrue(
			FString::Printf(
				TEXT("Chunk %d preserves deterministic ordering"),
				ChunkIndex),
			FirstChunk.ChunkCoordinate
				== SecondChunk.ChunkCoordinate);
		TestTrue(
			FString::Printf(
				TEXT("Chunk %d has canonical payload fingerprints"),
				ChunkIndex),
			IsCanonicalSha256(FirstChunk.CanonicalPayloadSha256)
				&& IsCanonicalSha256(
					SecondChunk.CanonicalPayloadSha256));
		TestTrue(
			FString::Printf(
				TEXT("Chunk %d has identical payload fingerprints"),
				ChunkIndex),
			FirstChunk.CanonicalPayloadSha256
				== SecondChunk.CanonicalPayloadSha256);
		TestTrue(
			FString::Printf(
				TEXT("Chunk %d has identical canonical RLE bytes"),
				ChunkIndex),
			FirstChunk.CompressedDensityAndMaterial
				== SecondChunk.CompressedDensityAndMaterial);

		FChunkRevision FirstRevision;
		const bool bReadFirstRevision =
			FirstBackend.ReadChunkRevision(
				VolumeStableId,
				FirstChunk.ChunkCoordinate,
				FirstRevision,
				Error);
		TestTrue(
			FString::Printf(
				TEXT("First chunk %d revision is readable: %s"),
				ChunkIndex,
				*Error),
			bReadFirstRevision);
		if (!bReadFirstRevision)
		{
			return false;
		}
		FChunkRevision SecondRevision;
		const bool bReadSecondRevision =
			SecondBackend.ReadChunkRevision(
				VolumeStableId,
				SecondChunk.ChunkCoordinate,
				SecondRevision,
				Error);
		TestTrue(
			FString::Printf(
				TEXT("Second chunk %d revision is readable: %s"),
				ChunkIndex,
				*Error),
			bReadSecondRevision);
		if (!bReadSecondRevision)
		{
			return false;
		}
		TestTrue(
			FString::Printf(
				TEXT("Chunk %d has identical authority content identity"),
				ChunkIndex),
			FirstRevision.TargetStableId
					== SecondRevision.TargetStableId
				&& FirstRevision.ChunkCoordinate
					== SecondRevision.ChunkCoordinate
				&& FirstRevision.ContentRevision
					== SecondRevision.ContentRevision
				&& FirstRevision.ContentSha256
					== SecondRevision.ContentSha256
				&& FirstRevision.GenerationToken
					== SecondRevision.GenerationToken);
		TestEqual(
			FString::Printf(
				TEXT("Chunk %d begins at content revision zero"),
				ChunkIndex),
			FirstRevision.ContentRevision,
			uint64(0));
		TestTrue(
			FString::Printf(
				TEXT("Chunk %d content identity is canonical"),
				ChunkIndex),
			IsCanonicalSha256(FirstRevision.ContentSha256));
	}

	const uint64 RevisionBeforeDuplicate =
		FirstBackend.GetCurrentRevision(VolumeStableId);
	const uint64 GenerationBeforeDuplicate =
		FirstBackend.GetAuthorityGenerationToken(VolumeStableId);
	const FString ManifestBeforeDuplicate =
		FirstCheckpoint.CanonicalManifestSha256;
	FString DuplicateError;
	const bool bDuplicateInitialized =
		FirstBackend.InitializeVolume(Spec, Limits, DuplicateError);
	TestFalse(TEXT("Duplicate initialization of one stable ID is rejected"),
		bDuplicateInitialized);
	TestTrue(TEXT("Duplicate rejection names the stable-ID collision"),
		DuplicateError.Contains(
			TEXT("a volume with this stable ID already exists")));
	TestEqual(TEXT("Duplicate rejection cannot advance live revision"),
		FirstBackend.GetCurrentRevision(VolumeStableId),
		RevisionBeforeDuplicate);
	TestEqual(TEXT("Duplicate rejection cannot advance authority generation"),
		FirstBackend.GetAuthorityGenerationToken(VolumeStableId),
		GenerationBeforeDuplicate);
	FVolumeCheckpoint AfterDuplicateCheckpoint;
	const bool bCapturedAfterDuplicate =
		FirstBackend.CaptureCheckpointSet(
			VolumeStableId,
			AfterDuplicateCheckpoint,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("State remains capturable after duplicate rejection: %s"),
			*Error),
		bCapturedAfterDuplicate);
	if (!bCapturedAfterDuplicate)
	{
		return false;
	}
	TestEqual(TEXT("Duplicate rejection preserves exact canonical content"),
		AfterDuplicateCheckpoint.CanonicalManifestSha256,
		ManifestBeforeDuplicate);
	TestEqual(TEXT("Duplicate rejection preserves the complete chunk set"),
		AfterDuplicateCheckpoint.Chunks.Num(),
		FirstCheckpoint.Chunks.Num());
	if (AfterDuplicateCheckpoint.Chunks.Num()
		!= FirstCheckpoint.Chunks.Num())
	{
		return false;
	}
	for (int32 ChunkIndex = 0;
		ChunkIndex < FirstCheckpoint.Chunks.Num();
		++ChunkIndex)
	{
		const FChunkCheckpoint& BeforeChunk =
			FirstCheckpoint.Chunks[ChunkIndex];
		const FChunkCheckpoint& AfterChunk =
			AfterDuplicateCheckpoint.Chunks[ChunkIndex];
		TestTrue(
			FString::Printf(
				TEXT("Duplicate rejection preserves chunk %d"),
				ChunkIndex),
			AfterChunk.ChunkCoordinate == BeforeChunk.ChunkCoordinate
				&& AfterChunk.ThroughRevision
					== BeforeChunk.ThroughRevision
				&& AfterChunk.CanonicalPayloadSha256
					== BeforeChunk.CanonicalPayloadSha256
				&& AfterChunk.CompressedDensityAndMaterial
					== BeforeChunk.CompressedDensityAndMaterial);

		FChunkRevision BaselineRevision;
		const bool bReadBaselineRevision =
			SecondBackend.ReadChunkRevision(
				VolumeStableId,
				BeforeChunk.ChunkCoordinate,
				BaselineRevision,
				Error);
		TestTrue(
			FString::Printf(
				TEXT("Twin baseline chunk %d remains readable: %s"),
				ChunkIndex,
				*Error),
			bReadBaselineRevision);
		if (!bReadBaselineRevision)
		{
			return false;
		}
		FChunkRevision AfterDuplicateRevision;
		const bool bReadAfterDuplicateRevision =
			FirstBackend.ReadChunkRevision(
				VolumeStableId,
				AfterChunk.ChunkCoordinate,
				AfterDuplicateRevision,
				Error);
		TestTrue(
			FString::Printf(
				TEXT("Rejected duplicate chunk %d remains readable: %s"),
				ChunkIndex,
				*Error),
			bReadAfterDuplicateRevision);
		if (!bReadAfterDuplicateRevision)
		{
			return false;
		}
		TestTrue(
			FString::Printf(
				TEXT("Duplicate rejection preserves chunk %d identity"),
				ChunkIndex),
			AfterDuplicateRevision.TargetStableId
					== BaselineRevision.TargetStableId
				&& AfterDuplicateRevision.ChunkCoordinate
					== BaselineRevision.ChunkCoordinate
				&& AfterDuplicateRevision.ContentRevision
					== BaselineRevision.ContentRevision
				&& AfterDuplicateRevision.ContentSha256
					== BaselineRevision.ContentSha256
				&& AfterDuplicateRevision.GenerationToken
					== BaselineRevision.GenerationToken);
	}

	const FIntVector SnapshotChunk(0, 0, 0);
	const FChunkCheckpoint* FirstSnapshotCheckpoint =
		FirstCheckpoint.Chunks.FindByPredicate(
			[&SnapshotChunk](const FChunkCheckpoint& Chunk)
			{
				return Chunk.ChunkCoordinate == SnapshotChunk;
			});
	const FChunkCheckpoint* SecondSnapshotCheckpoint =
		SecondCheckpoint.Chunks.FindByPredicate(
			[&SnapshotChunk](const FChunkCheckpoint& Chunk)
			{
				return Chunk.ChunkCoordinate == SnapshotChunk;
			});
	TestTrue(TEXT("Both checkpoints contain the selected snapshot chunk"),
		FirstSnapshotCheckpoint != nullptr
			&& SecondSnapshotCheckpoint != nullptr);
	if (!FirstSnapshotCheckpoint || !SecondSnapshotCheckpoint)
	{
		return false;
	}
	FChunkRevision FirstSnapshotRevision;
	const bool bReadFirstSnapshotRevision =
		FirstBackend.ReadChunkRevision(
			VolumeStableId,
			SnapshotChunk,
			FirstSnapshotRevision,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The first snapshot source is readable: %s"),
			*Error),
		bReadFirstSnapshotRevision);
	if (!bReadFirstSnapshotRevision)
	{
		return false;
	}
	FChunkRevision SecondSnapshotRevision;
	const bool bReadSecondSnapshotRevision =
		SecondBackend.ReadChunkRevision(
			VolumeStableId,
			SnapshotChunk,
			SecondSnapshotRevision,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The second snapshot source is readable: %s"),
			*Error),
		bReadSecondSnapshotRevision);
	if (!bReadSecondSnapshotRevision)
	{
		return false;
	}
	TestTrue(TEXT("The selected snapshot sources are identical"),
		FirstSnapshotRevision.TargetStableId
				== SecondSnapshotRevision.TargetStableId
			&& FirstSnapshotRevision.ChunkCoordinate
				== SecondSnapshotRevision.ChunkCoordinate
			&& FirstSnapshotRevision.ContentRevision
				== SecondSnapshotRevision.ContentRevision
			&& FirstSnapshotRevision.ContentSha256
				== SecondSnapshotRevision.ContentSha256
			&& FirstSnapshotRevision.GenerationToken
				== SecondSnapshotRevision.GenerationToken);

	FGeneratedChunkBuildRequest FirstBuildRequest;
	const bool bQueuedFirstBuild =
		FirstBackend.QueueChunkRebuild(
			FirstSnapshotRevision,
			EGeneratedOutputRequirement::Presentation,
			FirstBuildRequest,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The first detached authority snapshot is issued: %s"),
			*Error),
		bQueuedFirstBuild);
	if (!bQueuedFirstBuild)
	{
		return false;
	}
	FGeneratedChunkBuildRequest SecondBuildRequest;
	const bool bQueuedSecondBuild =
		SecondBackend.QueueChunkRebuild(
			SecondSnapshotRevision,
			EGeneratedOutputRequirement::Presentation,
			SecondBuildRequest,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The second detached authority snapshot is issued: %s"),
			*Error),
		bQueuedSecondBuild);
	if (!bQueuedSecondBuild)
	{
		return false;
	}
	FString FirstTicketReason;
	FString SecondTicketReason;
	TestTrue(TEXT("Both build capabilities validate structurally"),
		ValidateGeneratedChunkBuildTicket(
			FirstBuildRequest.Ticket,
			&FirstTicketReason)
			&& ValidateGeneratedChunkBuildTicket(
				SecondBuildRequest.Ticket,
				&SecondTicketReason));
	TestTrue(TEXT("Build snapshots preserve the canonical volume spec"),
		FirstBuildRequest.VolumeSpec.CanonicalSpecSha256
				== Spec.CanonicalSpecSha256
			&& SecondBuildRequest.VolumeSpec.CanonicalSpecSha256
				== Spec.CanonicalSpecSha256);
	TestTrue(TEXT("Identical initialization yields identical build bytes"),
		FirstBuildRequest.CanonicalDensityAndMaterial
			== SecondBuildRequest.CanonicalDensityAndMaterial);
	FString FirstBuildPayloadSha256;
	const bool bHashedFirstBuildPayload =
		ComputeCanonicalSha256(
			FirstBuildRequest.CanonicalDensityAndMaterial.GetData(),
			FirstBuildRequest.CanonicalDensityAndMaterial.Num(),
			FirstBuildPayloadSha256);
	FString SecondBuildPayloadSha256;
	const bool bHashedSecondBuildPayload =
		ComputeCanonicalSha256(
			SecondBuildRequest.CanonicalDensityAndMaterial.GetData(),
			SecondBuildRequest.CanonicalDensityAndMaterial.Num(),
			SecondBuildPayloadSha256);
	TestTrue(TEXT("Both detached snapshots receive canonical payload hashes"),
		bHashedFirstBuildPayload
			&& bHashedSecondBuildPayload
			&& IsCanonicalSha256(FirstBuildPayloadSha256)
			&& IsCanonicalSha256(SecondBuildPayloadSha256));
	TestTrue(TEXT("Detached snapshots bind their checkpoint payloads"),
		FirstBuildPayloadSha256
				== FirstSnapshotCheckpoint->CanonicalPayloadSha256
			&& SecondBuildPayloadSha256
				== SecondSnapshotCheckpoint->CanonicalPayloadSha256
			&& FirstBuildPayloadSha256
				== SecondBuildPayloadSha256);
	TestTrue(TEXT("Build tickets bind identical canonical source identity"),
		FirstBuildRequest.Ticket.SourceRevision.TargetStableId
				== SecondBuildRequest.Ticket.SourceRevision.TargetStableId
			&& FirstBuildRequest.Ticket.SourceRevision.ChunkCoordinate
				== SecondBuildRequest.Ticket.SourceRevision.ChunkCoordinate
			&& FirstBuildRequest.Ticket.SourceRevision.ContentRevision
				== SecondBuildRequest.Ticket.SourceRevision.ContentRevision
			&& FirstBuildRequest.Ticket.SourceRevision.ContentSha256
				== SecondBuildRequest.Ticket.SourceRevision.ContentSha256
			&& FirstBuildRequest.Ticket.SourceRevision.GenerationToken
				== SecondBuildRequest.Ticket.SourceRevision.GenerationToken
			&& FirstBuildRequest.Ticket.VolumeSpecSha256
				== SecondBuildRequest.Ticket.VolumeSpecSha256
			&& FirstBuildRequest.Ticket.OutputRole
				== SecondBuildRequest.Ticket.OutputRole
			&& FirstBuildRequest.Ticket.BuildProfileId
				== SecondBuildRequest.Ticket.BuildProfileId
			&& FirstBuildRequest.Ticket.BuildProfileVersion
				== SecondBuildRequest.Ticket.BuildProfileVersion);
	TestTrue(TEXT("Fresh backends each issue their first build attempt"),
		FirstBuildRequest.Ticket.BuildRequestToken == uint64(1)
			&& SecondBuildRequest.Ticket.BuildRequestToken == uint64(1));
	TestTrue(TEXT("Backend-instance capabilities remain process local"),
		FirstBuildRequest.Ticket.BackendInstanceId.IsValid()
			&& SecondBuildRequest.Ticket.BackendInstanceId.IsValid()
			&& FirstBuildRequest.Ticket.BackendInstanceId
				!= SecondBuildRequest.Ticket.BackendInstanceId);
	TestEqual(TEXT("Build snapshot issuance cannot advance revision"),
		FirstBackend.GetCurrentRevision(VolumeStableId), uint64(0));
	TestEqual(TEXT("Twin build snapshot issuance cannot advance revision"),
		SecondBackend.GetCurrentRevision(VolumeStableId), uint64(0));

	FGeneratedChunkOutputState FirstOutputState;
	const bool bQueriedFirstOutputState =
		FirstBackend.QueryGeneratedOutputState(
			VolumeStableId,
			SnapshotChunk,
			FirstOutputState,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("First pending output state remains queryable: %s"),
			*Error),
		bQueriedFirstOutputState);
	FGeneratedChunkOutputState SecondOutputState;
	const bool bQueriedSecondOutputState =
		SecondBackend.QueryGeneratedOutputState(
			VolumeStableId,
			SnapshotChunk,
			SecondOutputState,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("Second pending output state remains queryable: %s"),
			*Error),
		bQueriedSecondOutputState);
	TestTrue(TEXT("Queued work cannot fabricate output readiness"),
		bQueriedFirstOutputState
			&& bQueriedSecondOutputState
			&& !FirstOutputState.bPresentationReady
			&& !FirstOutputState.bCollisionReady
			&& !SecondOutputState.bPresentationReady
			&& !SecondOutputState.bCollisionReady
			&& FirstOutputState.PresentationOutputSha256.IsEmpty()
			&& FirstOutputState.CollisionOutputSha256.IsEmpty()
			&& SecondOutputState.PresentationOutputSha256.IsEmpty()
			&& SecondOutputState.CollisionOutputSha256.IsEmpty());

	FVolumeCheckpoint AfterBuildRequestCheckpoint;
	const bool bCapturedAfterBuildRequest =
		FirstBackend.CaptureCheckpointSet(
			VolumeStableId,
			AfterBuildRequestCheckpoint,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("Canonical state remains capturable after build issuance: %s"),
			*Error),
		bCapturedAfterBuildRequest);
	TestEqual(TEXT("Build capabilities cannot mutate canonical content"),
		AfterBuildRequestCheckpoint.CanonicalManifestSha256,
		ManifestBeforeDuplicate);

	return !HasAnyErrors();
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FRedVoxelMultiVolumeIsolationTest,
	"RedMMO.Mining.VoxelBackend.MultiVolumeIsolation",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRedVoxelMultiVolumeIsolationTest::RunTest(
	const FString& Parameters)
{
	using namespace RedVoxelMining;
	using namespace RedVoxelMiningTests;
	(void)Parameters;

	const FName FirstVolumeStableId(
		TEXT("asteroid.red.m12.multi-volume-a"));
	const FName SecondVolumeStableId(
		TEXT("asteroid.red.m12.multi-volume-b"));
	const FName MultiVolumeCollectorStableId(
		TEXT("player.red.m12.multi-volume"));
	const FIntVector TargetChunk(0, 0, 0);

	FAuthorityLimits Limits;
	FVolumeSpec FirstSpec = MakeVolumeSpec();
	FirstSpec.StableId = FirstVolumeStableId;
	FString FirstCanonicalSpecSha256;
	const bool bFirstFingerprintComputed =
		ComputeCanonicalVolumeSpecSha256(
			FirstSpec,
			FirstCanonicalSpecSha256);
	TestTrue(
		TEXT("The first live volume receives a canonical fingerprint"),
		bFirstFingerprintComputed);
	if (!bFirstFingerprintComputed)
	{
		return false;
	}
	FirstSpec.CanonicalSpecSha256 =
		MoveTemp(FirstCanonicalSpecSha256);

	FVolumeSpec SecondSpec = MakeVolumeSpec();
	SecondSpec.StableId = SecondVolumeStableId;
	SecondSpec.BaseSeed = 0x4D31324BU;
	FString SecondCanonicalSpecSha256;
	const bool bSecondFingerprintComputed =
		ComputeCanonicalVolumeSpecSha256(
			SecondSpec,
			SecondCanonicalSpecSha256);
	TestTrue(
		TEXT("The second live volume receives a canonical fingerprint"),
		bSecondFingerprintComputed);
	if (!bSecondFingerprintComputed)
	{
		return false;
	}
	SecondSpec.CanonicalSpecSha256 =
		MoveTemp(SecondCanonicalSpecSha256);
	TestTrue(TEXT("The live volume specs remain distinct"),
		FirstSpec.StableId != SecondSpec.StableId
			&& FirstSpec.BaseSeed != SecondSpec.BaseSeed
			&& FirstSpec.CanonicalSpecSha256
				!= SecondSpec.CanonicalSpecSha256);

	FRedInMemorySparseVoxelBackend Backend;
	FString Error;
	const bool bFirstInitialized =
		Backend.InitializeVolume(FirstSpec, Limits, Error);
	TestTrue(
		FString::Printf(
			TEXT("The first live volume initializes: %s"),
			*Error),
		bFirstInitialized);
	if (!bFirstInitialized)
	{
		return false;
	}
	const bool bSecondInitialized =
		Backend.InitializeVolume(SecondSpec, Limits, Error);
	TestTrue(
		FString::Printf(
			TEXT("The second live volume initializes beside it: %s"),
			*Error),
		bSecondInitialized);
	if (!bSecondInitialized)
	{
		return false;
	}
	TestTrue(TEXT("One backend owns both distinct live volumes"),
		Backend.HasVolume(FirstVolumeStableId)
			&& Backend.HasVolume(SecondVolumeStableId));
	const uint64 FirstAuthorityGeneration =
		Backend.GetAuthorityGenerationToken(
			FirstVolumeStableId);
	const uint64 SecondAuthorityGeneration =
		Backend.GetAuthorityGenerationToken(
			SecondVolumeStableId);
	TestTrue(TEXT("Both live volumes receive valid authority generations"),
		FirstAuthorityGeneration > uint64(0)
			&& SecondAuthorityGeneration > uint64(0));
	TestTrue(TEXT("Both live volumes begin at revision zero"),
		Backend.GetCurrentRevision(FirstVolumeStableId) == uint64(0)
			&& Backend.GetCurrentRevision(SecondVolumeStableId)
				== uint64(0));

	FVolumeCheckpoint FirstBeforeEditCheckpoint;
	const bool bCapturedFirstBeforeEdit =
		Backend.CaptureCheckpointSet(
			FirstVolumeStableId,
			FirstBeforeEditCheckpoint,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The first pre-edit checkpoint is captured: %s"),
			*Error),
		bCapturedFirstBeforeEdit);
	if (!bCapturedFirstBeforeEdit)
	{
		return false;
	}
	FVolumeCheckpoint SecondBeforeEditCheckpoint;
	const bool bCapturedSecondBeforeEdit =
		Backend.CaptureCheckpointSet(
			SecondVolumeStableId,
			SecondBeforeEditCheckpoint,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The second pre-edit checkpoint is captured: %s"),
			*Error),
		bCapturedSecondBeforeEdit);
	if (!bCapturedSecondBeforeEdit)
	{
		return false;
	}
	TestTrue(TEXT("Distinct live volumes have distinct checkpoint identity"),
		FirstBeforeEditCheckpoint.TargetStableId
				!= SecondBeforeEditCheckpoint.TargetStableId
			&& FirstBeforeEditCheckpoint.VolumeSpecSha256
				!= SecondBeforeEditCheckpoint.VolumeSpecSha256
			&& FirstBeforeEditCheckpoint.CanonicalManifestSha256
				!= SecondBeforeEditCheckpoint.CanonicalManifestSha256);

	FChunkRevision SecondBeforeEditRevision;
	const bool bReadSecondBeforeEditRevision =
		Backend.ReadChunkRevision(
			SecondVolumeStableId,
			TargetChunk,
			SecondBeforeEditRevision,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The second target chunk is readable before the first edit: %s"),
			*Error),
		bReadSecondBeforeEditRevision);
	if (!bReadSecondBeforeEditRevision)
	{
		return false;
	}
	FGeneratedChunkOutputState SecondBeforeEditOutput;
	const bool bReadSecondBeforeEditOutput =
		Backend.QueryGeneratedOutputState(
			SecondVolumeStableId,
			TargetChunk,
			SecondBeforeEditOutput,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The second output state is readable before the first edit: %s"),
			*Error),
		bReadSecondBeforeEditOutput);
	if (!bReadSecondBeforeEditOutput)
	{
		return false;
	}

	FValidatedEdit FirstEdit;
	FirstEdit.TargetStableId = FirstVolumeStableId;
	FirstEdit.CollectorStableId =
		MultiVolumeCollectorStableId;
	FirstEdit.MiningToolStableId = MiningToolStableId;
	FirstEdit.RequestSequence = 1;
	FirstEdit.ExpectedRevision = 0;
	FirstEdit.LocalBrushCenter =
		FVector(-250.0, -50.0, -50.0);
	FirstEdit.LocalSurfaceNormal = FVector::UpVector;
	FirstEdit.BrushRadiusCm = 25.f;
	FirstEdit.AuthorityGenerationToken =
		Backend.GetAuthorityGenerationToken(
			FirstVolumeStableId);
	FirstEdit.PredictionToken = FGuid::NewGuid();
	FApplyResult FirstEditResult;
	const bool bFirstEditAccepted =
		Backend.ApplyValidatedEdit(
			FirstEdit,
			FirstEditResult,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The first volume accepts its exact edit: %s"),
			*Error),
		bFirstEditAccepted && FirstEditResult.bAccepted);
	if (!bFirstEditAccepted || !FirstEditResult.bAccepted)
	{
		return false;
	}
	TestTrue(TEXT("The accepted edit is bound only to the first volume"),
		FirstEditResult.TargetStableId == FirstVolumeStableId
			&& FirstEditResult.PreviousRevision == uint64(0)
			&& FirstEditResult.AppliedRevision == uint64(1)
			&& FirstEditResult.TotalRemovedCellCount == 1);
	TestEqual(TEXT("The first live volume advances to revision one"),
		Backend.GetCurrentRevision(FirstVolumeStableId), uint64(1));
	TestEqual(TEXT("The second live volume remains at revision zero"),
		Backend.GetCurrentRevision(SecondVolumeStableId), uint64(0));

	FVolumeCheckpoint FirstAfterEditCheckpoint;
	const bool bCapturedFirstAfterEdit =
		Backend.CaptureCheckpointSet(
			FirstVolumeStableId,
			FirstAfterEditCheckpoint,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The edited first checkpoint is captured: %s"),
			*Error),
		bCapturedFirstAfterEdit);
	if (!bCapturedFirstAfterEdit)
	{
		return false;
	}
	FVolumeCheckpoint SecondAfterFirstEditCheckpoint;
	const bool bCapturedSecondAfterFirstEdit =
		Backend.CaptureCheckpointSet(
			SecondVolumeStableId,
			SecondAfterFirstEditCheckpoint,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The untouched second checkpoint is recaptured: %s"),
			*Error),
		bCapturedSecondAfterFirstEdit);
	if (!bCapturedSecondAfterFirstEdit)
	{
		return false;
	}
	TestTrue(TEXT("The accepted edit changes only the first manifest"),
		FirstAfterEditCheckpoint.CanonicalManifestSha256
				!= FirstBeforeEditCheckpoint.CanonicalManifestSha256
			&& SecondAfterFirstEditCheckpoint.CanonicalManifestSha256
				== SecondBeforeEditCheckpoint.CanonicalManifestSha256);
	TestEqual(TEXT("The second checkpoint retains its complete chunk set"),
		SecondAfterFirstEditCheckpoint.Chunks.Num(),
		SecondBeforeEditCheckpoint.Chunks.Num());
	if (SecondAfterFirstEditCheckpoint.Chunks.Num()
		!= SecondBeforeEditCheckpoint.Chunks.Num())
	{
		return false;
	}
	for (int32 ChunkIndex = 0;
		ChunkIndex < SecondBeforeEditCheckpoint.Chunks.Num();
		++ChunkIndex)
	{
		const FChunkCheckpoint& BeforeChunk =
			SecondBeforeEditCheckpoint.Chunks[ChunkIndex];
		const FChunkCheckpoint& AfterChunk =
			SecondAfterFirstEditCheckpoint.Chunks[ChunkIndex];
		TestTrue(
			FString::Printf(
				TEXT("First-volume edit preserves second-volume chunk %d"),
				ChunkIndex),
			AfterChunk.TargetStableId == BeforeChunk.TargetStableId
				&& AfterChunk.ChunkCoordinate
					== BeforeChunk.ChunkCoordinate
				&& AfterChunk.ThroughRevision
					== BeforeChunk.ThroughRevision
				&& AfterChunk.CanonicalPayloadSha256
					== BeforeChunk.CanonicalPayloadSha256
				&& AfterChunk.CompressedDensityAndMaterial
					== BeforeChunk.CompressedDensityAndMaterial);
	}

	FChunkRevision FirstAfterEditRevision;
	const bool bReadFirstAfterEditRevision =
		Backend.ReadChunkRevision(
			FirstVolumeStableId,
			TargetChunk,
			FirstAfterEditRevision,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The edited first target chunk is readable: %s"),
			*Error),
		bReadFirstAfterEditRevision);
	if (!bReadFirstAfterEditRevision)
	{
		return false;
	}
	FChunkRevision SecondAfterFirstEditRevision;
	const bool bReadSecondAfterFirstEditRevision =
		Backend.ReadChunkRevision(
			SecondVolumeStableId,
			TargetChunk,
			SecondAfterFirstEditRevision,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The untouched second target chunk is readable: %s"),
			*Error),
		bReadSecondAfterFirstEditRevision);
	if (!bReadSecondAfterFirstEditRevision)
	{
		return false;
	}
	TestTrue(TEXT("Chunk revisions remain bound to their own live volume"),
		FirstAfterEditRevision.TargetStableId == FirstVolumeStableId
			&& FirstAfterEditRevision.ContentRevision == uint64(1)
			&& SecondAfterFirstEditRevision.TargetStableId
				== SecondVolumeStableId
			&& SecondAfterFirstEditRevision.ContentRevision == uint64(0)
			&& SecondAfterFirstEditRevision.ContentSha256
				== SecondBeforeEditRevision.ContentSha256
			&& SecondAfterFirstEditRevision.GenerationToken
				== SecondBeforeEditRevision.GenerationToken);

	FGeneratedChunkOutputState SecondAfterFirstEditOutput;
	const bool bReadSecondAfterFirstEditOutput =
		Backend.QueryGeneratedOutputState(
			SecondVolumeStableId,
			TargetChunk,
			SecondAfterFirstEditOutput,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The untouched second output state remains readable: %s"),
			*Error),
		bReadSecondAfterFirstEditOutput);
	TestTrue(TEXT("First-volume edit cannot mutate second-volume output state"),
		bReadSecondAfterFirstEditOutput
			&& SecondAfterFirstEditOutput.TargetStableId
				== SecondBeforeEditOutput.TargetStableId
			&& SecondAfterFirstEditOutput.ChunkCoordinate
				== SecondBeforeEditOutput.ChunkCoordinate
			&& SecondAfterFirstEditOutput.ContentRevision
				== SecondBeforeEditOutput.ContentRevision
			&& SecondAfterFirstEditOutput.ContentSha256
				== SecondBeforeEditOutput.ContentSha256
			&& SecondAfterFirstEditOutput.GenerationToken
				== SecondBeforeEditOutput.GenerationToken
			&& !SecondAfterFirstEditOutput.bPresentationReady
			&& !SecondAfterFirstEditOutput.bCollisionReady
			&& SecondAfterFirstEditOutput.PresentationOutputSha256.IsEmpty()
			&& SecondAfterFirstEditOutput.CollisionOutputSha256.IsEmpty());

	FValidatedEdit CrossVolumeEdit = FirstEdit;
	CrossVolumeEdit.TargetStableId = SecondVolumeStableId;
	CrossVolumeEdit.RequestSequence = 1;
	CrossVolumeEdit.ExpectedRevision =
		FirstEditResult.AppliedRevision;
	CrossVolumeEdit.AuthorityGenerationToken =
		SecondAuthorityGeneration;
	CrossVolumeEdit.PredictionToken = FGuid::NewGuid();
	FApplyResult CrossVolumeEditResult;
	const bool bCrossVolumeEditHandled =
		Backend.ApplyValidatedEdit(
			CrossVolumeEdit,
			CrossVolumeEditResult,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The cross-volume stale edit is handled deterministically: %s"),
			*Error),
		bCrossVolumeEditHandled);
	if (!bCrossVolumeEditHandled)
	{
		return false;
	}
	TestFalse(
		TEXT("A first-volume revision cannot authorize a second-volume edit"),
		CrossVolumeEditResult.bAccepted);
	TestTrue(TEXT("The rejected cross-volume edit preserves its requested stale revision"),
		CrossVolumeEditResult.TargetStableId == SecondVolumeStableId
			&& CrossVolumeEditResult.RequestSequence
				== CrossVolumeEdit.RequestSequence
			&& CrossVolumeEditResult.PredictionToken
				== CrossVolumeEdit.PredictionToken
			&& CrossVolumeEditResult.AuthorityGenerationToken
				== CrossVolumeEdit.AuthorityGenerationToken
			&& CrossVolumeEditResult.RejectReason
				== EEditRejectReason::StaleRevision
			&& CrossVolumeEditResult.PreviousRevision
				== CrossVolumeEdit.ExpectedRevision
			&& CrossVolumeEditResult.AppliedRevision
				== CrossVolumeEdit.ExpectedRevision
			&& CrossVolumeEditResult.TotalRemovedCellCount == 0
			&& CrossVolumeEditResult.MaterialYields.IsEmpty()
			&& CrossVolumeEditResult.DirtyChunkCoordinates.IsEmpty());

	FVolumeCheckpoint FirstAfterCrossEditCheckpoint;
	const bool bCapturedFirstAfterCrossEdit =
		Backend.CaptureCheckpointSet(
			FirstVolumeStableId,
			FirstAfterCrossEditCheckpoint,
			Error);
	FVolumeCheckpoint SecondAfterCrossEditCheckpoint;
	const bool bCapturedSecondAfterCrossEdit =
		Backend.CaptureCheckpointSet(
			SecondVolumeStableId,
			SecondAfterCrossEditCheckpoint,
			Error);
	TestTrue(TEXT("Both volumes remain capturable after cross-edit rejection"),
		bCapturedFirstAfterCrossEdit
			&& bCapturedSecondAfterCrossEdit);
	TestTrue(TEXT("Cross-edit rejection cannot mutate either canonical volume"),
		bCapturedFirstAfterCrossEdit
			&& bCapturedSecondAfterCrossEdit
			&& FirstAfterCrossEditCheckpoint.CanonicalManifestSha256
				== FirstAfterEditCheckpoint.CanonicalManifestSha256
			&& SecondAfterCrossEditCheckpoint.CanonicalManifestSha256
				== SecondAfterFirstEditCheckpoint.CanonicalManifestSha256
			&& Backend.GetCurrentRevision(FirstVolumeStableId) == uint64(1)
			&& Backend.GetCurrentRevision(SecondVolumeStableId) == uint64(0)
			&& Backend.GetAuthorityGenerationToken(FirstVolumeStableId)
				== FirstAuthorityGeneration
			&& Backend.GetAuthorityGenerationToken(SecondVolumeStableId)
				== SecondAuthorityGeneration);

	FChunkRevision CrossVolumeBuildRevision =
		FirstAfterEditRevision;
	CrossVolumeBuildRevision.TargetStableId =
		SecondVolumeStableId;
	FGeneratedChunkBuildRequest RejectedCrossVolumeRequest;
	const bool bQueuedCrossVolumeRequest =
		Backend.QueueChunkRebuild(
			CrossVolumeBuildRevision,
			EGeneratedOutputRequirement::Presentation,
			RejectedCrossVolumeRequest,
			Error);
	TestFalse(
		TEXT("First-volume content cannot queue work against the second volume"),
		bQueuedCrossVolumeRequest);
	TestTrue(TEXT("Cross-volume queue rejection names the authority mismatch"),
		Error.Contains(
			TEXT("is stale or does not match authority content")));
	TestTrue(TEXT("Rejected cross-volume queue leaves a default request"),
		RejectedCrossVolumeRequest.Ticket.BuildRequestToken == uint64(0)
			&& RejectedCrossVolumeRequest.CanonicalDensityAndMaterial.IsEmpty());
	FGeneratedChunkOutputState FirstAfterRejectedQueue;
	const bool bReadFirstAfterRejectedQueue =
		Backend.QueryGeneratedOutputState(
			FirstVolumeStableId,
			TargetChunk,
			FirstAfterRejectedQueue,
			Error);
	FGeneratedChunkOutputState SecondAfterRejectedQueue;
	const bool bReadSecondAfterRejectedQueue =
		Backend.QueryGeneratedOutputState(
			SecondVolumeStableId,
			TargetChunk,
			SecondAfterRejectedQueue,
			Error);
	TestTrue(TEXT("Both outputs remain queryable after cross-volume queue rejection"),
		bReadFirstAfterRejectedQueue
			&& bReadSecondAfterRejectedQueue);
	if (!bReadFirstAfterRejectedQueue
		|| !bReadSecondAfterRejectedQueue)
	{
		return false;
	}
	TestTrue(TEXT("Cross-volume queue rejection preserves both output states"),
		FirstAfterRejectedQueue.TargetStableId
				== FirstAfterEditRevision.TargetStableId
			&& FirstAfterRejectedQueue.ChunkCoordinate
				== FirstAfterEditRevision.ChunkCoordinate
			&& FirstAfterRejectedQueue.ContentRevision
				== FirstAfterEditRevision.ContentRevision
			&& FirstAfterRejectedQueue.ContentSha256
				== FirstAfterEditRevision.ContentSha256
			&& FirstAfterRejectedQueue.GenerationToken
				== FirstAfterEditRevision.GenerationToken
			&& !FirstAfterRejectedQueue.bPresentationReady
			&& !FirstAfterRejectedQueue.bCollisionReady
			&& FirstAfterRejectedQueue.PresentationOutputSha256.IsEmpty()
			&& FirstAfterRejectedQueue.CollisionOutputSha256.IsEmpty()
			&& SecondAfterRejectedQueue.TargetStableId
				== SecondAfterFirstEditRevision.TargetStableId
			&& SecondAfterRejectedQueue.ChunkCoordinate
				== SecondAfterFirstEditRevision.ChunkCoordinate
			&& SecondAfterRejectedQueue.ContentRevision
				== SecondAfterFirstEditRevision.ContentRevision
			&& SecondAfterRejectedQueue.ContentSha256
				== SecondAfterFirstEditRevision.ContentSha256
			&& SecondAfterRejectedQueue.GenerationToken
				== SecondAfterFirstEditRevision.GenerationToken
			&& !SecondAfterRejectedQueue.bPresentationReady
			&& !SecondAfterRejectedQueue.bCollisionReady
			&& SecondAfterRejectedQueue.PresentationOutputSha256.IsEmpty()
			&& SecondAfterRejectedQueue.CollisionOutputSha256.IsEmpty());

	FGeneratedChunkBuildRequest FirstPresentationRequest;
	const bool bQueuedFirstPresentation =
		Backend.QueueChunkRebuild(
			FirstAfterEditRevision,
			EGeneratedOutputRequirement::Presentation,
			FirstPresentationRequest,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The first volume receives its own presentation ticket: %s"),
			*Error),
		bQueuedFirstPresentation);
	if (!bQueuedFirstPresentation)
	{
		return false;
	}
	FGeneratedChunkBuildRequest SecondPresentationRequest;
	const bool bQueuedSecondPresentation =
		Backend.QueueChunkRebuild(
			SecondAfterFirstEditRevision,
			EGeneratedOutputRequirement::Presentation,
			SecondPresentationRequest,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The second volume receives its own presentation ticket: %s"),
			*Error),
		bQueuedSecondPresentation);
	if (!bQueuedSecondPresentation)
	{
		return false;
	}
	TestTrue(TEXT("Build tickets bind their distinct live volumes"),
		FirstPresentationRequest.Ticket.SourceRevision.TargetStableId
				== FirstVolumeStableId
			&& SecondPresentationRequest.Ticket.SourceRevision.TargetStableId
				== SecondVolumeStableId
			&& FirstPresentationRequest.Ticket.VolumeSpecSha256
				== FirstSpec.CanonicalSpecSha256
			&& SecondPresentationRequest.Ticket.VolumeSpecSha256
				== SecondSpec.CanonicalSpecSha256);
	TestTrue(TEXT("Build capabilities share one backend but not one token"),
		FirstPresentationRequest.Ticket.BackendInstanceId.IsValid()
			&& FirstPresentationRequest.Ticket.BackendInstanceId
				== SecondPresentationRequest.Ticket.BackendInstanceId
			&& FirstPresentationRequest.Ticket.BuildRequestToken
				== uint64(1)
			&& FirstPresentationRequest.Ticket.BuildRequestToken
				+ uint64(1)
				== SecondPresentationRequest.Ticket.BuildRequestToken);

	const FString FirstPresentationSha256(
		TEXT("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"));
	const FString SecondPresentationSha256(
		TEXT("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"));
	FGeneratedChunkBuildCompletion ForeignSecondCompletion;
	ForeignSecondCompletion.Ticket =
		SecondPresentationRequest.Ticket;
	ForeignSecondCompletion.Ticket.SourceRevision.ContentRevision =
		FirstPresentationRequest.Ticket.SourceRevision.ContentRevision;
	ForeignSecondCompletion.Ticket.SourceRevision.ContentSha256 =
		FirstPresentationRequest.Ticket.SourceRevision.ContentSha256;
	ForeignSecondCompletion.Ticket.SourceRevision.GenerationToken =
		FirstPresentationRequest.Ticket.SourceRevision.GenerationToken;
	ForeignSecondCompletion.Ticket.VolumeSpecSha256 =
		FirstPresentationRequest.Ticket.VolumeSpecSha256;
	ForeignSecondCompletion.OutputSha256 =
		SecondPresentationSha256;
	FString ForeignCompletionValidationError;
	TestTrue(
		FString::Printf(
			TEXT("The foreign-identity completion remains structurally valid: %s"),
			*ForeignCompletionValidationError),
		ValidateGeneratedChunkBuildCompletion(
			ForeignSecondCompletion,
			&ForeignCompletionValidationError));
	TestTrue(TEXT("The foreign completion retains the second target and token but splices first-volume authority identity"),
		ForeignSecondCompletion.Ticket.SourceRevision.TargetStableId
				== SecondVolumeStableId
			&& ForeignSecondCompletion.Ticket.SourceRevision.ChunkCoordinate
				== SecondPresentationRequest.Ticket.SourceRevision.ChunkCoordinate
			&& ForeignSecondCompletion.Ticket.BuildRequestToken
				== SecondPresentationRequest.Ticket.BuildRequestToken
			&& ForeignSecondCompletion.Ticket.VolumeSpecSha256
				== FirstPresentationRequest.Ticket.VolumeSpecSha256
			&& ForeignSecondCompletion.Ticket.VolumeSpecSha256
				!= SecondPresentationRequest.Ticket.VolumeSpecSha256
			&& ForeignSecondCompletion.Ticket.SourceRevision.ContentRevision
				== FirstPresentationRequest.Ticket.SourceRevision.ContentRevision
			&& ForeignSecondCompletion.Ticket.SourceRevision.ContentSha256
				== FirstPresentationRequest.Ticket.SourceRevision.ContentSha256
			&& ForeignSecondCompletion.Ticket.SourceRevision.GenerationToken
				== FirstPresentationRequest.Ticket.SourceRevision.GenerationToken);
	const bool bAcceptedForeignSecondCompletion =
		Backend.CompleteChunkRebuild(
			ForeignSecondCompletion,
			Error);
	TestFalse(
		TEXT("First-volume authority identity cannot complete the second ticket"),
		bAcceptedForeignSecondCompletion);
	TestTrue(TEXT("The foreign build identity reaches live-authority rejection"),
		Error.Contains(
			TEXT("is stale or does not match live authority")));

	FGeneratedChunkBuildCompletion HybridSecondCompletion;
	HybridSecondCompletion.Ticket =
		SecondPresentationRequest.Ticket;
	HybridSecondCompletion.Ticket.BuildRequestToken =
		FirstPresentationRequest.Ticket.BuildRequestToken;
	HybridSecondCompletion.OutputSha256 =
		SecondPresentationSha256;
	FString HybridCompletionValidationError;
	TestTrue(
		FString::Printf(
			TEXT("The hybrid completion remains structurally valid: %s"),
			*HybridCompletionValidationError),
		ValidateGeneratedChunkBuildCompletion(
			HybridSecondCompletion,
			&HybridCompletionValidationError));
	TestTrue(TEXT("The hybrid keeps second-volume identity with only the first token"),
		HybridSecondCompletion.Ticket.SourceRevision.TargetStableId
				== SecondPresentationRequest.Ticket.SourceRevision.TargetStableId
			&& HybridSecondCompletion.Ticket.SourceRevision.ChunkCoordinate
				== SecondPresentationRequest.Ticket.SourceRevision.ChunkCoordinate
			&& HybridSecondCompletion.Ticket.SourceRevision.ContentRevision
				== SecondPresentationRequest.Ticket.SourceRevision.ContentRevision
			&& HybridSecondCompletion.Ticket.SourceRevision.ContentSha256
				== SecondPresentationRequest.Ticket.SourceRevision.ContentSha256
			&& HybridSecondCompletion.Ticket.SourceRevision.GenerationToken
				== SecondPresentationRequest.Ticket.SourceRevision.GenerationToken
			&& HybridSecondCompletion.Ticket.VolumeSpecSha256
				== SecondPresentationRequest.Ticket.VolumeSpecSha256
			&& HybridSecondCompletion.Ticket.OutputRole
				== SecondPresentationRequest.Ticket.OutputRole
			&& HybridSecondCompletion.Ticket.BuildProfileId
				== SecondPresentationRequest.Ticket.BuildProfileId
			&& HybridSecondCompletion.Ticket.BuildProfileVersion
				== SecondPresentationRequest.Ticket.BuildProfileVersion
			&& HybridSecondCompletion.Ticket.BackendInstanceId
				== SecondPresentationRequest.Ticket.BackendInstanceId
			&& HybridSecondCompletion.Ticket.BuildRequestToken
				== FirstPresentationRequest.Ticket.BuildRequestToken
			&& HybridSecondCompletion.Ticket.BuildRequestToken
				!= SecondPresentationRequest.Ticket.BuildRequestToken);
	const bool bAcceptedHybridSecondCompletion =
		Backend.CompleteChunkRebuild(
			HybridSecondCompletion,
			Error);
	TestFalse(TEXT("A first-volume attempt token cannot authorize the second ticket"),
		bAcceptedHybridSecondCompletion);
	TestTrue(TEXT("The hybrid build capability reaches exact attempt rejection"),
		Error.Contains(
			TEXT("is not the active role attempt")));

	FGeneratedChunkOutputState FirstAfterHybridCompletion;
	const bool bReadFirstAfterHybridCompletion =
		Backend.QueryGeneratedOutputState(
			FirstVolumeStableId,
			TargetChunk,
			FirstAfterHybridCompletion,
			Error);
	FGeneratedChunkOutputState SecondAfterHybridCompletion;
	const bool bReadSecondAfterHybridCompletion =
		Backend.QueryGeneratedOutputState(
			SecondVolumeStableId,
			TargetChunk,
			SecondAfterHybridCompletion,
			Error);
	TestTrue(TEXT("Foreign and hybrid completions leave both output states queryable"),
		bReadFirstAfterHybridCompletion
			&& bReadSecondAfterHybridCompletion);
	if (!bReadFirstAfterHybridCompletion
		|| !bReadSecondAfterHybridCompletion)
	{
		return false;
	}
	TestTrue(TEXT("Foreign and hybrid completions cannot mutate either output identity"),
		FirstAfterHybridCompletion.TargetStableId
				== FirstAfterEditRevision.TargetStableId
			&& FirstAfterHybridCompletion.ChunkCoordinate
				== FirstAfterEditRevision.ChunkCoordinate
			&& FirstAfterHybridCompletion.ContentRevision
				== FirstAfterEditRevision.ContentRevision
			&& FirstAfterHybridCompletion.ContentSha256
				== FirstAfterEditRevision.ContentSha256
			&& FirstAfterHybridCompletion.GenerationToken
				== FirstAfterEditRevision.GenerationToken
			&& SecondAfterHybridCompletion.TargetStableId
				== SecondAfterFirstEditRevision.TargetStableId
			&& SecondAfterHybridCompletion.ChunkCoordinate
				== SecondAfterFirstEditRevision.ChunkCoordinate
			&& SecondAfterHybridCompletion.ContentRevision
				== SecondAfterFirstEditRevision.ContentRevision
			&& SecondAfterHybridCompletion.ContentSha256
				== SecondAfterFirstEditRevision.ContentSha256
			&& SecondAfterHybridCompletion.GenerationToken
				== SecondAfterFirstEditRevision.GenerationToken);
	TestTrue(TEXT("Foreign and hybrid completions cannot ready or fingerprint either volume"),
		!FirstAfterHybridCompletion.bPresentationReady
			&& !FirstAfterHybridCompletion.bCollisionReady
			&& FirstAfterHybridCompletion.PresentationOutputSha256.IsEmpty()
			&& FirstAfterHybridCompletion.CollisionOutputSha256.IsEmpty()
			&& !SecondAfterHybridCompletion.bPresentationReady
			&& !SecondAfterHybridCompletion.bCollisionReady
			&& SecondAfterHybridCompletion.PresentationOutputSha256.IsEmpty()
			&& SecondAfterHybridCompletion.CollisionOutputSha256.IsEmpty());

	FGeneratedChunkBuildCompletion ExactSecondCompletion;
	ExactSecondCompletion.Ticket =
		SecondPresentationRequest.Ticket;
	ExactSecondCompletion.OutputSha256 =
		SecondPresentationSha256;
	const bool bCompletedExactSecond =
		Backend.CompleteChunkRebuild(
			ExactSecondCompletion,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The second volume retains its exact pending ticket: %s"),
			*Error),
		bCompletedExactSecond);
	FGeneratedChunkOutputState SecondAfterExactCompletion;
	const bool bReadSecondAfterExactCompletion =
		Backend.QueryGeneratedOutputState(
			SecondVolumeStableId,
			TargetChunk,
			SecondAfterExactCompletion,
			Error);
	FGeneratedChunkOutputState FirstWhileSecondComplete;
	const bool bReadFirstWhileSecondComplete =
		Backend.QueryGeneratedOutputState(
			FirstVolumeStableId,
			TargetChunk,
			FirstWhileSecondComplete,
			Error);
	TestTrue(TEXT("Both outputs remain queryable after exact second completion"),
		bReadSecondAfterExactCompletion
			&& bReadFirstWhileSecondComplete);
	if (!bReadSecondAfterExactCompletion
		|| !bReadFirstWhileSecondComplete)
	{
		return false;
	}
	TestTrue(TEXT("Only the exact second completion readies the second volume"),
		SecondAfterExactCompletion.TargetStableId
				== SecondAfterFirstEditRevision.TargetStableId
			&& SecondAfterExactCompletion.ChunkCoordinate
				== SecondAfterFirstEditRevision.ChunkCoordinate
			&& SecondAfterExactCompletion.ContentRevision
				== SecondAfterFirstEditRevision.ContentRevision
			&& SecondAfterExactCompletion.ContentSha256
				== SecondAfterFirstEditRevision.ContentSha256
			&& SecondAfterExactCompletion.GenerationToken
				== SecondAfterFirstEditRevision.GenerationToken
			&& SecondAfterExactCompletion.bPresentationReady
			&& !SecondAfterExactCompletion.bCollisionReady
			&& SecondAfterExactCompletion.PresentationOutputSha256
				== SecondPresentationSha256
			&& SecondAfterExactCompletion.CollisionOutputSha256.IsEmpty()
			&& FirstWhileSecondComplete.TargetStableId
				== FirstAfterEditRevision.TargetStableId
			&& FirstWhileSecondComplete.ChunkCoordinate
				== FirstAfterEditRevision.ChunkCoordinate
			&& FirstWhileSecondComplete.ContentRevision
				== FirstAfterEditRevision.ContentRevision
			&& FirstWhileSecondComplete.ContentSha256
				== FirstAfterEditRevision.ContentSha256
			&& FirstWhileSecondComplete.GenerationToken
				== FirstAfterEditRevision.GenerationToken
			&& !FirstWhileSecondComplete.bPresentationReady
			&& !FirstWhileSecondComplete.bCollisionReady
			&& FirstWhileSecondComplete.PresentationOutputSha256.IsEmpty()
			&& FirstWhileSecondComplete.CollisionOutputSha256.IsEmpty());

	FGeneratedChunkBuildCompletion ExactFirstCompletion;
	ExactFirstCompletion.Ticket =
		FirstPresentationRequest.Ticket;
	ExactFirstCompletion.OutputSha256 =
		FirstPresentationSha256;
	const bool bCompletedExactFirst =
		Backend.CompleteChunkRebuild(
			ExactFirstCompletion,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The first volume also retains its exact pending ticket: %s"),
			*Error),
		bCompletedExactFirst);
	FGeneratedChunkOutputState FirstAfterExactCompletion;
	const bool bReadFirstAfterExactCompletion =
		Backend.QueryGeneratedOutputState(
			FirstVolumeStableId,
			TargetChunk,
			FirstAfterExactCompletion,
			Error);
	FGeneratedChunkOutputState SecondAfterBothCompletions;
	const bool bReadSecondAfterBothCompletions =
		Backend.QueryGeneratedOutputState(
			SecondVolumeStableId,
			TargetChunk,
			SecondAfterBothCompletions,
			Error);
	TestTrue(TEXT("Both outputs remain queryable after exact first completion"),
		bReadFirstAfterExactCompletion
			&& bReadSecondAfterBothCompletions);
	if (!bReadFirstAfterExactCompletion
		|| !bReadSecondAfterBothCompletions)
	{
		return false;
	}
	TestTrue(TEXT("Exact completions retain role and volume-specific output"),
		FirstAfterExactCompletion.TargetStableId
				== FirstAfterEditRevision.TargetStableId
			&& FirstAfterExactCompletion.ChunkCoordinate
				== FirstAfterEditRevision.ChunkCoordinate
			&& FirstAfterExactCompletion.ContentRevision
				== FirstAfterEditRevision.ContentRevision
			&& FirstAfterExactCompletion.ContentSha256
				== FirstAfterEditRevision.ContentSha256
			&& FirstAfterExactCompletion.GenerationToken
				== FirstAfterEditRevision.GenerationToken
			&& FirstAfterExactCompletion.bPresentationReady
			&& !FirstAfterExactCompletion.bCollisionReady
			&& FirstAfterExactCompletion.PresentationOutputSha256
				== FirstPresentationSha256
			&& FirstAfterExactCompletion.CollisionOutputSha256.IsEmpty()
			&& SecondAfterBothCompletions.TargetStableId
				== SecondAfterFirstEditRevision.TargetStableId
			&& SecondAfterBothCompletions.ChunkCoordinate
				== SecondAfterFirstEditRevision.ChunkCoordinate
			&& SecondAfterBothCompletions.ContentRevision
				== SecondAfterFirstEditRevision.ContentRevision
			&& SecondAfterBothCompletions.ContentSha256
				== SecondAfterFirstEditRevision.ContentSha256
			&& SecondAfterBothCompletions.GenerationToken
				== SecondAfterFirstEditRevision.GenerationToken
			&& SecondAfterBothCompletions.bPresentationReady
			&& !SecondAfterBothCompletions.bCollisionReady
			&& SecondAfterBothCompletions.PresentationOutputSha256
				== SecondPresentationSha256
			&& SecondAfterBothCompletions.CollisionOutputSha256.IsEmpty()
			&& FirstAfterExactCompletion.PresentationOutputSha256
				!= SecondAfterBothCompletions.PresentationOutputSha256);

	FCheckpointPersistenceRequest FirstPersistenceRequest;
	const bool bCapturedFirstPersistence =
		Backend.CaptureCheckpointForPersistence(
			FirstVolumeStableId,
			FirstPersistenceRequest,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The first volume receives its own persistence ticket: %s"),
			*Error),
		bCapturedFirstPersistence);
	if (!bCapturedFirstPersistence)
	{
		return false;
	}
	FCheckpointPersistenceRequest SecondPersistenceRequest;
	const bool bCapturedSecondPersistence =
		Backend.CaptureCheckpointForPersistence(
			SecondVolumeStableId,
			SecondPersistenceRequest,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The second volume receives its own persistence ticket: %s"),
			*Error),
		bCapturedSecondPersistence);
	if (!bCapturedSecondPersistence)
	{
		return false;
	}
	FString FirstPersistenceRequestValidationError;
	const bool bFirstPersistenceRequestValid =
		ValidateCheckpointPersistenceRequest(
			FirstPersistenceRequest,
			&FirstPersistenceRequestValidationError);
	FString SecondPersistenceRequestValidationError;
	const bool bSecondPersistenceRequestValid =
		ValidateCheckpointPersistenceRequest(
			SecondPersistenceRequest,
			&SecondPersistenceRequestValidationError);
	TestTrue(
		FString::Printf(
			TEXT("Both per-volume persistence envelopes validate: first=%s second=%s"),
			*FirstPersistenceRequestValidationError,
			*SecondPersistenceRequestValidationError),
		bFirstPersistenceRequestValid
			&& bSecondPersistenceRequestValid);
	if (!bFirstPersistenceRequestValid
		|| !bSecondPersistenceRequestValid)
	{
		return false;
	}
	TestTrue(TEXT("Persistence tickets bind their distinct live volumes"),
		FirstPersistenceRequest.Ticket.TargetStableId
				== FirstVolumeStableId
			&& SecondPersistenceRequest.Ticket.TargetStableId
				== SecondVolumeStableId
			&& FirstPersistenceRequest.Ticket.VolumeSpecSha256
				== FirstSpec.CanonicalSpecSha256
			&& SecondPersistenceRequest.Ticket.VolumeSpecSha256
				== SecondSpec.CanonicalSpecSha256);
	TestTrue(TEXT("Persistence capabilities share one backend but not one token"),
		FirstPersistenceRequest.Ticket.BackendInstanceId.IsValid()
			&& FirstPersistenceRequest.Ticket.BackendInstanceId
				== SecondPersistenceRequest.Ticket.BackendInstanceId
			&& FirstPersistenceRequest.Ticket.PersistenceRequestToken
				+ uint64(1)
				== SecondPersistenceRequest.Ticket.PersistenceRequestToken);

	FCheckpointPersistenceAcknowledgement ForeignSecondAcknowledgement;
	ForeignSecondAcknowledgement.Ticket =
		SecondPersistenceRequest.Ticket;
	ForeignSecondAcknowledgement.Ticket.VolumeSpecSha256 =
		FirstPersistenceRequest.Ticket.VolumeSpecSha256;
	ForeignSecondAcknowledgement.Ticket.CheckpointThroughRevision =
		FirstPersistenceRequest.Ticket.CheckpointThroughRevision;
	ForeignSecondAcknowledgement.Ticket.CheckpointManifestSha256 =
		FirstPersistenceRequest.Ticket.CheckpointManifestSha256;
	ForeignSecondAcknowledgement.Ticket.CheckpointJournalTailSha256 =
		FirstPersistenceRequest.Ticket.CheckpointJournalTailSha256;
	FString ForeignAcknowledgementValidationError;
	TestTrue(
		FString::Printf(
			TEXT("The foreign-identity persistence ticket remains structurally valid: %s"),
			*ForeignAcknowledgementValidationError),
		ValidateCheckpointPersistenceTicket(
			ForeignSecondAcknowledgement.Ticket,
			&ForeignAcknowledgementValidationError));
	TestTrue(TEXT("The foreign acknowledgement retains the second target and token but splices first-volume checkpoint identity"),
		ForeignSecondAcknowledgement.Ticket.TargetStableId
				== SecondVolumeStableId
			&& ForeignSecondAcknowledgement.Ticket.PersistenceRequestToken
				== SecondPersistenceRequest.Ticket.PersistenceRequestToken
			&& ForeignSecondAcknowledgement.Ticket.VolumeSpecSha256
				== FirstPersistenceRequest.Ticket.VolumeSpecSha256
			&& ForeignSecondAcknowledgement.Ticket.VolumeSpecSha256
				!= SecondPersistenceRequest.Ticket.VolumeSpecSha256
			&& ForeignSecondAcknowledgement.Ticket.CheckpointThroughRevision
				== FirstPersistenceRequest.Ticket.CheckpointThroughRevision
			&& ForeignSecondAcknowledgement.Ticket.CheckpointManifestSha256
				== FirstPersistenceRequest.Ticket.CheckpointManifestSha256
			&& ForeignSecondAcknowledgement.Ticket.CheckpointJournalTailSha256
				== FirstPersistenceRequest.Ticket.CheckpointJournalTailSha256);
	const bool bAcceptedForeignSecondAcknowledgement =
		Backend.AcknowledgePersistedCheckpoint(
			ForeignSecondAcknowledgement,
			Error);
	TestFalse(
		TEXT("First-volume checkpoint identity cannot acknowledge the second ticket"),
		bAcceptedForeignSecondAcknowledgement);
	TestTrue(TEXT("The foreign persistence identity reaches authority rejection"),
		Error.Contains(
			TEXT("targets stale or foreign authority state")));

	FCheckpointPersistenceAcknowledgement HybridSecondAcknowledgement;
	HybridSecondAcknowledgement.Ticket =
		SecondPersistenceRequest.Ticket;
	HybridSecondAcknowledgement.Ticket.PersistenceRequestToken =
		FirstPersistenceRequest.Ticket.PersistenceRequestToken;
	FString HybridAcknowledgementValidationError;
	TestTrue(
		FString::Printf(
			TEXT("The hybrid persistence ticket remains structurally valid: %s"),
			*HybridAcknowledgementValidationError),
		ValidateCheckpointPersistenceTicket(
			HybridSecondAcknowledgement.Ticket,
			&HybridAcknowledgementValidationError));
	TestTrue(TEXT("The hybrid keeps second-volume persistence identity with only the first token"),
		HybridSecondAcknowledgement.Ticket.TargetStableId
				== SecondPersistenceRequest.Ticket.TargetStableId
			&& HybridSecondAcknowledgement.Ticket.VolumeSpecSha256
				== SecondPersistenceRequest.Ticket.VolumeSpecSha256
			&& HybridSecondAcknowledgement.Ticket.CheckpointThroughRevision
				== SecondPersistenceRequest.Ticket.CheckpointThroughRevision
			&& HybridSecondAcknowledgement.Ticket.CheckpointManifestSha256
				== SecondPersistenceRequest.Ticket.CheckpointManifestSha256
			&& HybridSecondAcknowledgement.Ticket.CheckpointJournalTailSha256
				== SecondPersistenceRequest.Ticket.CheckpointJournalTailSha256
			&& HybridSecondAcknowledgement.Ticket.AuthorityGenerationToken
				== SecondPersistenceRequest.Ticket.AuthorityGenerationToken
			&& HybridSecondAcknowledgement.Ticket.BackendInstanceId
				== SecondPersistenceRequest.Ticket.BackendInstanceId
			&& HybridSecondAcknowledgement.Ticket.PersistenceRequestToken
				== FirstPersistenceRequest.Ticket.PersistenceRequestToken
			&& HybridSecondAcknowledgement.Ticket.PersistenceRequestToken
				!= SecondPersistenceRequest.Ticket.PersistenceRequestToken);
	const bool bAcceptedHybridSecondAcknowledgement =
		Backend.AcknowledgePersistedCheckpoint(
			HybridSecondAcknowledgement,
			Error);
	TestFalse(
		TEXT("A first-volume persistence token cannot acknowledge the second ticket"),
		bAcceptedHybridSecondAcknowledgement);
	TestTrue(TEXT("The hybrid persistence capability reaches exact ticket rejection"),
		Error.Contains(
			TEXT("does not match the exact live pending ticket")));

	FEditJournalExport FirstBeforeAcknowledgement;
	TestFalse(TEXT("Hybrid rejection cannot promote the first durability base"),
		Backend.ExportOperationJournal(
			FirstVolumeStableId,
			FirstBeforeAcknowledgement,
			Error));
	FEditJournalExport SecondBeforeAcknowledgement;
	TestFalse(TEXT("Hybrid rejection cannot promote the second durability base"),
		Backend.ExportOperationJournal(
			SecondVolumeStableId,
			SecondBeforeAcknowledgement,
			Error));

	FCheckpointPersistenceAcknowledgement ExactFirstAcknowledgement;
	ExactFirstAcknowledgement.Ticket =
		FirstPersistenceRequest.Ticket;
	const bool bAcknowledgedExactFirst =
		Backend.AcknowledgePersistedCheckpoint(
			ExactFirstAcknowledgement,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The first exact persistence ticket remains usable: %s"),
			*Error),
		bAcknowledgedExactFirst);
	if (!bAcknowledgedExactFirst)
	{
		return false;
	}
	FEditJournalExport FirstAfterAcknowledgement;
	const bool bExportedFirstAfterAcknowledgement =
		Backend.ExportOperationJournal(
			FirstVolumeStableId,
			FirstAfterAcknowledgement,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The first acknowledged base exports independently: %s"),
			*Error),
		bExportedFirstAfterAcknowledgement);
	if (!bExportedFirstAfterAcknowledgement)
	{
		return false;
	}
	FEditJournalExport SecondWhileFirstAcknowledged;
	TestFalse(
		TEXT("First acknowledgement cannot promote the second durability base"),
		Backend.ExportOperationJournal(
			SecondVolumeStableId,
			SecondWhileFirstAcknowledged,
			Error));

	FCheckpointPersistenceAcknowledgement ExactSecondAcknowledgement;
	ExactSecondAcknowledgement.Ticket =
		SecondPersistenceRequest.Ticket;
	const bool bAcknowledgedExactSecond =
		Backend.AcknowledgePersistedCheckpoint(
			ExactSecondAcknowledgement,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The second exact persistence ticket remains usable: %s"),
			*Error),
		bAcknowledgedExactSecond);
	if (!bAcknowledgedExactSecond)
	{
		return false;
	}
	FEditJournalExport SecondAfterAcknowledgement;
	const bool bExportedSecondAfterAcknowledgement =
		Backend.ExportOperationJournal(
			SecondVolumeStableId,
			SecondAfterAcknowledgement,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The second acknowledged base exports independently: %s"),
			*Error),
		bExportedSecondAfterAcknowledgement);
	if (!bExportedSecondAfterAcknowledgement)
	{
		return false;
	}
	FEditJournalExport FirstAfterSecondAcknowledgement;
	const bool bExportedFirstAfterSecondAcknowledgement =
		Backend.ExportOperationJournal(
			FirstVolumeStableId,
			FirstAfterSecondAcknowledgement,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The first base remains exact after second acknowledgement: %s"),
			*Error),
		bExportedFirstAfterSecondAcknowledgement);
	if (!bExportedFirstAfterSecondAcknowledgement)
	{
		return false;
	}
	FString FirstExportValidationError;
	const bool bFirstExportValid =
		ValidateEditJournalExport(
			FirstAfterSecondAcknowledgement,
			Limits,
			&FirstExportValidationError);
	FString SecondExportValidationError;
	const bool bSecondExportValid =
		ValidateEditJournalExport(
			SecondAfterAcknowledgement,
			Limits,
			&SecondExportValidationError);
	TestTrue(
		FString::Printf(
			TEXT("Both per-volume journal exports validate: first=%s second=%s"),
			*FirstExportValidationError,
			*SecondExportValidationError),
		bFirstExportValid && bSecondExportValid);
	TestTrue(TEXT("Each exact acknowledgement commits only its own revision"),
		bExportedFirstAfterAcknowledgement
			&& bExportedSecondAfterAcknowledgement
			&& bExportedFirstAfterSecondAcknowledgement
			&& FirstAfterAcknowledgement.TargetStableId
				== FirstVolumeStableId
			&& FirstAfterAcknowledgement.VolumeSpecSha256
				== FirstSpec.CanonicalSpecSha256
			&& FirstAfterAcknowledgement.BaseCheckpointRevision == uint64(1)
			&& FirstAfterAcknowledgement.BaseCheckpointManifestSha256
				== FirstPersistenceRequest.Ticket.CheckpointManifestSha256
			&& FirstAfterAcknowledgement.BaseJournalTailSha256
				== FirstPersistenceRequest.Ticket.CheckpointJournalTailSha256
			&& FirstAfterAcknowledgement.ThroughRevision == uint64(1)
			&& FirstAfterAcknowledgement.Operations.IsEmpty()
			&& FirstAfterAcknowledgement.FinalJournalTailSha256
				== FirstPersistenceRequest.Ticket.CheckpointJournalTailSha256
			&& IsCanonicalSha256(
				FirstAfterAcknowledgement.CanonicalManifestSha256)
			&& SecondAfterAcknowledgement.TargetStableId
				== SecondVolumeStableId
			&& SecondAfterAcknowledgement.VolumeSpecSha256
				== SecondSpec.CanonicalSpecSha256
			&& SecondAfterAcknowledgement.BaseCheckpointRevision == uint64(0)
			&& SecondAfterAcknowledgement.BaseCheckpointManifestSha256
				== SecondPersistenceRequest.Ticket.CheckpointManifestSha256
			&& SecondAfterAcknowledgement.BaseJournalTailSha256
				== SecondPersistenceRequest.Ticket.CheckpointJournalTailSha256
			&& SecondAfterAcknowledgement.ThroughRevision == uint64(0)
			&& SecondAfterAcknowledgement.Operations.IsEmpty()
			&& SecondAfterAcknowledgement.FinalJournalTailSha256
				== SecondPersistenceRequest.Ticket.CheckpointJournalTailSha256
			&& IsCanonicalSha256(
				SecondAfterAcknowledgement.CanonicalManifestSha256));
	TestTrue(TEXT("Second acknowledgement cannot change the first export"),
		FirstAfterSecondAcknowledgement.TargetStableId
				== FirstAfterAcknowledgement.TargetStableId
			&& FirstAfterSecondAcknowledgement.VolumeSpecSha256
				== FirstAfterAcknowledgement.VolumeSpecSha256
			&& FirstAfterSecondAcknowledgement.BaseCheckpointRevision
				== FirstAfterAcknowledgement.BaseCheckpointRevision
			&& FirstAfterSecondAcknowledgement.BaseCheckpointManifestSha256
				== FirstAfterAcknowledgement.BaseCheckpointManifestSha256
			&& FirstAfterSecondAcknowledgement.BaseJournalTailSha256
				== FirstAfterAcknowledgement.BaseJournalTailSha256
			&& FirstAfterSecondAcknowledgement.ThroughRevision
				== FirstAfterAcknowledgement.ThroughRevision
			&& FirstAfterSecondAcknowledgement.Operations.Num()
				== FirstAfterAcknowledgement.Operations.Num()
			&& FirstAfterSecondAcknowledgement.FinalJournalTailSha256
				== FirstAfterAcknowledgement.FinalJournalTailSha256
			&& FirstAfterSecondAcknowledgement.CanonicalManifestSha256
				== FirstAfterAcknowledgement.CanonicalManifestSha256);

	FVolumeCheckpoint FirstFinalCheckpoint;
	const bool bCapturedFirstFinal =
		Backend.CaptureCheckpointSet(
			FirstVolumeStableId,
			FirstFinalCheckpoint,
			Error);
	FVolumeCheckpoint SecondFinalCheckpoint;
	const bool bCapturedSecondFinal =
		Backend.CaptureCheckpointSet(
			SecondVolumeStableId,
			SecondFinalCheckpoint,
			Error);
	TestTrue(TEXT("Both canonical volumes remain capturable after isolation checks"),
		bCapturedFirstFinal && bCapturedSecondFinal);
	TestTrue(TEXT("Capabilities and acknowledgements cannot cross-mutate content"),
		bCapturedFirstFinal
			&& bCapturedSecondFinal
			&& FirstFinalCheckpoint.CanonicalManifestSha256
				== FirstAfterEditCheckpoint.CanonicalManifestSha256
			&& SecondFinalCheckpoint.CanonicalManifestSha256
				== SecondAfterFirstEditCheckpoint.CanonicalManifestSha256
			&& Backend.GetCurrentRevision(FirstVolumeStableId) == uint64(1)
			&& Backend.GetCurrentRevision(SecondVolumeStableId) == uint64(0)
			&& Backend.GetAuthorityGenerationToken(FirstVolumeStableId)
				== FirstAuthorityGeneration
			&& Backend.GetAuthorityGenerationToken(SecondVolumeStableId)
				== SecondAuthorityGeneration);

	FGeneratedChunkOutputState FirstBeforeSecondEditOutput;
	const bool bReadFirstBeforeSecondEditOutput =
		Backend.QueryGeneratedOutputState(
			FirstVolumeStableId,
			TargetChunk,
			FirstBeforeSecondEditOutput,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The first output is readable before the second edit: %s"),
			*Error),
		bReadFirstBeforeSecondEditOutput);
	FValidatedEdit SecondEdit = FirstEdit;
	SecondEdit.TargetStableId = SecondVolumeStableId;
	SecondEdit.RequestSequence = 1;
	SecondEdit.ExpectedRevision = 0;
	SecondEdit.AuthorityGenerationToken =
		SecondAuthorityGeneration;
	SecondEdit.PredictionToken = FGuid::NewGuid();
	FApplyResult SecondEditResult;
	const bool bSecondEditAccepted =
		Backend.ApplyValidatedEdit(
			SecondEdit,
			SecondEditResult,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The second volume accepts its own exact edit: %s"),
			*Error),
		bSecondEditAccepted && SecondEditResult.bAccepted);
	if (!bReadFirstBeforeSecondEditOutput
		|| !bSecondEditAccepted
		|| !SecondEditResult.bAccepted)
	{
		return false;
	}
	TestTrue(TEXT("The accepted second edit is bound only to the second volume"),
		SecondEditResult.TargetStableId == SecondVolumeStableId
			&& SecondEditResult.RequestSequence == uint64(1)
			&& SecondEditResult.PredictionToken
				== SecondEdit.PredictionToken
			&& SecondEditResult.AuthorityGenerationToken
				== SecondAuthorityGeneration
			&& SecondEditResult.RejectReason
				== EEditRejectReason::None
			&& SecondEditResult.PreviousRevision == uint64(0)
			&& SecondEditResult.AppliedRevision == uint64(1)
			&& SecondEditResult.TotalRemovedCellCount == 1);

	FGeneratedChunkOutputState FirstAfterSecondEditOutput;
	const bool bReadFirstAfterSecondEditOutput =
		Backend.QueryGeneratedOutputState(
			FirstVolumeStableId,
			TargetChunk,
			FirstAfterSecondEditOutput,
			Error);
	FGeneratedChunkOutputState SecondAfterOwnEditOutput;
	const bool bReadSecondAfterOwnEditOutput =
		Backend.QueryGeneratedOutputState(
			SecondVolumeStableId,
			TargetChunk,
			SecondAfterOwnEditOutput,
			Error);
	TestTrue(TEXT("Both outputs remain queryable after the second accepted edit"),
		bReadFirstAfterSecondEditOutput
			&& bReadSecondAfterOwnEditOutput);
	if (!bReadFirstAfterSecondEditOutput
		|| !bReadSecondAfterOwnEditOutput)
	{
		return false;
	}
	TestTrue(TEXT("Second-volume mutation preserves every first-volume output field"),
		FirstAfterSecondEditOutput.TargetStableId
				== FirstBeforeSecondEditOutput.TargetStableId
			&& FirstAfterSecondEditOutput.ChunkCoordinate
				== FirstBeforeSecondEditOutput.ChunkCoordinate
			&& FirstAfterSecondEditOutput.ContentRevision
				== FirstBeforeSecondEditOutput.ContentRevision
			&& FirstAfterSecondEditOutput.ContentSha256
				== FirstBeforeSecondEditOutput.ContentSha256
			&& FirstAfterSecondEditOutput.GenerationToken
				== FirstBeforeSecondEditOutput.GenerationToken
			&& FirstAfterSecondEditOutput.bPresentationReady
				== FirstBeforeSecondEditOutput.bPresentationReady
			&& FirstAfterSecondEditOutput.bCollisionReady
				== FirstBeforeSecondEditOutput.bCollisionReady
			&& FirstAfterSecondEditOutput.PresentationOutputSha256
				== FirstBeforeSecondEditOutput.PresentationOutputSha256
			&& FirstAfterSecondEditOutput.CollisionOutputSha256
				== FirstBeforeSecondEditOutput.CollisionOutputSha256);
	TestTrue(TEXT("The accepted second edit invalidates only its own generated output"),
		SecondAfterOwnEditOutput.TargetStableId == SecondVolumeStableId
			&& SecondAfterOwnEditOutput.ChunkCoordinate == TargetChunk
			&& SecondAfterOwnEditOutput.ContentRevision == uint64(1)
			&& IsCanonicalSha256(
				SecondAfterOwnEditOutput.ContentSha256)
			&& SecondAfterOwnEditOutput.ContentSha256
				!= SecondAfterFirstEditRevision.ContentSha256
			&& SecondAfterOwnEditOutput.GenerationToken
				== SecondAuthorityGeneration
			&& !SecondAfterOwnEditOutput.bPresentationReady
			&& !SecondAfterOwnEditOutput.bCollisionReady
			&& SecondAfterOwnEditOutput.PresentationOutputSha256.IsEmpty()
			&& SecondAfterOwnEditOutput.CollisionOutputSha256.IsEmpty());

	FVolumeCheckpoint FirstAfterSecondEditCheckpoint;
	const bool bCapturedFirstAfterSecondEdit =
		Backend.CaptureCheckpointSet(
			FirstVolumeStableId,
			FirstAfterSecondEditCheckpoint,
			Error);
	FVolumeCheckpoint SecondAfterOwnEditCheckpoint;
	const bool bCapturedSecondAfterOwnEdit =
		Backend.CaptureCheckpointSet(
			SecondVolumeStableId,
			SecondAfterOwnEditCheckpoint,
			Error);
	TestTrue(TEXT("Both canonical volumes remain capturable after the second edit"),
		bCapturedFirstAfterSecondEdit
			&& bCapturedSecondAfterOwnEdit);
	TestTrue(TEXT("A valid second-volume edit cannot commit into the first volume"),
		bCapturedFirstAfterSecondEdit
			&& bCapturedSecondAfterOwnEdit
			&& FirstAfterSecondEditCheckpoint.CanonicalManifestSha256
				== FirstFinalCheckpoint.CanonicalManifestSha256
			&& SecondAfterOwnEditCheckpoint.CanonicalManifestSha256
				!= SecondFinalCheckpoint.CanonicalManifestSha256
			&& Backend.GetCurrentRevision(FirstVolumeStableId) == uint64(1)
			&& Backend.GetCurrentRevision(SecondVolumeStableId) == uint64(1)
			&& Backend.GetAuthorityGenerationToken(FirstVolumeStableId)
				== FirstAuthorityGeneration
			&& Backend.GetAuthorityGenerationToken(SecondVolumeStableId)
				== SecondAuthorityGeneration);

	FEditJournalExport FirstAfterSecondEditExport;
	const bool bExportedFirstAfterSecondEdit =
		Backend.ExportOperationJournal(
			FirstVolumeStableId,
			FirstAfterSecondEditExport,
			Error);
	FEditJournalExport SecondAfterOwnEditExport;
	const bool bExportedSecondAfterOwnEdit =
		Backend.ExportOperationJournal(
			SecondVolumeStableId,
			SecondAfterOwnEditExport,
			Error);
	TestTrue(TEXT("Both durability journals export after the second edit"),
		bExportedFirstAfterSecondEdit
			&& bExportedSecondAfterOwnEdit);
	if (!bExportedFirstAfterSecondEdit
		|| !bExportedSecondAfterOwnEdit)
	{
		return false;
	}
	FString FirstAfterSecondEditExportValidationError;
	const bool bFirstAfterSecondEditExportValid =
		ValidateEditJournalExport(
			FirstAfterSecondEditExport,
			Limits,
			&FirstAfterSecondEditExportValidationError);
	FString SecondAfterOwnEditExportValidationError;
	const bool bSecondAfterOwnEditExportValid =
		ValidateEditJournalExport(
			SecondAfterOwnEditExport,
			Limits,
			&SecondAfterOwnEditExportValidationError);
	TestTrue(
		FString::Printf(
			TEXT("Both post-edit per-volume journal exports validate: first=%s second=%s"),
			*FirstAfterSecondEditExportValidationError,
			*SecondAfterOwnEditExportValidationError),
		bFirstAfterSecondEditExportValid
			&& bSecondAfterOwnEditExportValid);
	TestTrue(TEXT("The second edit preserves the first acknowledged base and export exactly"),
		FirstAfterSecondEditExport.TargetStableId
				== FirstAfterSecondAcknowledgement.TargetStableId
			&& FirstAfterSecondEditExport.VolumeSpecSha256
				== FirstAfterSecondAcknowledgement.VolumeSpecSha256
			&& FirstAfterSecondEditExport.BaseCheckpointRevision
				== FirstAfterSecondAcknowledgement.BaseCheckpointRevision
			&& FirstAfterSecondEditExport.BaseCheckpointManifestSha256
				== FirstAfterSecondAcknowledgement.BaseCheckpointManifestSha256
			&& FirstAfterSecondEditExport.BaseJournalTailSha256
				== FirstAfterSecondAcknowledgement.BaseJournalTailSha256
			&& FirstAfterSecondEditExport.ThroughRevision
				== FirstAfterSecondAcknowledgement.ThroughRevision
			&& FirstAfterSecondEditExport.Operations.Num()
				== FirstAfterSecondAcknowledgement.Operations.Num()
			&& FirstAfterSecondEditExport.FinalJournalTailSha256
				== FirstAfterSecondAcknowledgement.FinalJournalTailSha256
			&& FirstAfterSecondEditExport.CanonicalManifestSha256
				== FirstAfterSecondAcknowledgement.CanonicalManifestSha256);
	TestEqual(TEXT("The second durability suffix contains only its accepted edit"),
		SecondAfterOwnEditExport.Operations.Num(), 1);
	if (SecondAfterOwnEditExport.Operations.Num() != 1)
	{
		return false;
	}
	const FEditOperation& SecondOwnedOperation =
		SecondAfterOwnEditExport.Operations[0];
	TestTrue(TEXT("The second durability suffix is bound entirely to the second volume"),
		SecondAfterOwnEditExport.TargetStableId == SecondVolumeStableId
			&& SecondAfterOwnEditExport.VolumeSpecSha256
				== SecondSpec.CanonicalSpecSha256
			&& SecondAfterOwnEditExport.BaseCheckpointRevision == uint64(0)
			&& SecondAfterOwnEditExport.BaseCheckpointManifestSha256
				== SecondPersistenceRequest.Ticket.CheckpointManifestSha256
			&& SecondAfterOwnEditExport.BaseJournalTailSha256
				== SecondPersistenceRequest.Ticket.CheckpointJournalTailSha256
			&& SecondAfterOwnEditExport.ThroughRevision == uint64(1)
			&& SecondOwnedOperation.TargetStableId == SecondVolumeStableId
			&& SecondOwnedOperation.VolumeSpecSha256
				== SecondSpec.CanonicalSpecSha256
			&& SecondOwnedOperation.PreviousRevision == uint64(0)
			&& SecondOwnedOperation.Revision == uint64(1)
			&& SecondOwnedOperation.RequestSequence == uint64(1)
			&& SecondOwnedOperation.PredictionToken
				== SecondEdit.PredictionToken
			&& SecondAfterOwnEditExport.FinalJournalTailSha256
				== SecondOwnedOperation.CanonicalOperationSha256
			&& IsCanonicalSha256(
				SecondAfterOwnEditExport.CanonicalManifestSha256));

	return !HasAnyErrors();
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FRedVoxelSameRevisionCheckpointManifestEquivocationTest,
	"RedMMO.Mining.VoxelBackend.SameRevisionCheckpointManifestEquivocation",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRedVoxelSameRevisionCheckpointManifestEquivocationTest::RunTest(
	const FString& Parameters)
{
	using namespace RedVoxelMining;
	using namespace RedVoxelMiningTests;
	(void)Parameters;

	FAuthorityLimits Limits;
	FVolumeSpec Spec = MakeVolumeSpec();
	FString CanonicalSpecSha256;
	const bool bFingerprintComputed =
		ComputeCanonicalVolumeSpecSha256(Spec, CanonicalSpecSha256);
	TestTrue(
		TEXT("The same-revision fixture receives a canonical spec fingerprint"),
		bFingerprintComputed);
	if (!bFingerprintComputed)
	{
		return false;
	}
	Spec.CanonicalSpecSha256 = MoveTemp(CanonicalSpecSha256);

	FRedInMemorySparseVoxelBackend Backend;
	FString Error;
	const bool bInitialized =
		Backend.InitializeVolume(Spec, Limits, Error);
	TestTrue(
		FString::Printf(
			TEXT("The same-revision fixture initializes: %s"),
			*Error),
		bInitialized);
	if (!bInitialized)
	{
		return false;
	}

	FApplyResult FirstResult;
	const bool bFirstEditAccepted = ApplyAcceptedEdit(
		Backend,
		1,
		FVector(-250.0, -50.0, -50.0),
		FirstResult,
		Error);
	TestTrue(
		FString::Printf(
			TEXT("The same-revision fixture accepts one edit: %s"),
			*Error),
		bFirstEditAccepted);
	if (!bFirstEditAccepted)
	{
		return false;
	}
	TestTrue(TEXT("The fixture establishes one exact revision-one edit"),
		FirstResult.PreviousRevision == uint64(0)
			&& FirstResult.AppliedRevision == uint64(1)
			&& FirstResult.RequestSequence == uint64(1)
			&& FirstResult.RejectReason == EEditRejectReason::None
			&& FirstResult.TotalRemovedCellCount == 1
			&& Backend.GetCurrentRevision(VolumeStableId) == uint64(1));

	FCheckpointPersistenceRequest BasePersistenceRequest;
	const bool bCapturedBaseRequest =
		Backend.CaptureCheckpointForPersistence(
			VolumeStableId,
			BasePersistenceRequest,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The revision-one durability base is captured: %s"),
			*Error),
		bCapturedBaseRequest);
	if (!bCapturedBaseRequest)
	{
		return false;
	}
	FString BaseRequestValidationError;
	const bool bBaseRequestValid =
		ValidateCheckpointPersistenceRequest(
			BasePersistenceRequest,
			&BaseRequestValidationError);
	TestTrue(
		FString::Printf(
			TEXT("The initial durability envelope validates: %s"),
			*BaseRequestValidationError),
		bBaseRequestValid);

	FCheckpointPersistenceAcknowledgement BaseAcknowledgement;
	BaseAcknowledgement.Ticket = BasePersistenceRequest.Ticket;
	const bool bAcknowledgedBase =
		Backend.AcknowledgePersistedCheckpoint(
			BaseAcknowledgement,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The revision-one durability base is acknowledged: %s"),
			*Error),
		bAcknowledgedBase);
	if (!bAcknowledgedBase)
	{
		return false;
	}

	FEditJournalExport BaselineExport;
	const bool bExportedBaseline =
		Backend.ExportOperationJournal(
			VolumeStableId,
			BaselineExport,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The acknowledged revision-one base exports: %s"),
			*Error),
		bExportedBaseline);
	if (!bExportedBaseline)
	{
		return false;
	}
	TestTrue(TEXT("The acknowledged base is an exact empty revision-one suffix"),
		BaselineExport.TargetStableId == VolumeStableId
			&& BaselineExport.VolumeSpecSha256
				== Spec.CanonicalSpecSha256
			&& BaselineExport.BaseCheckpointRevision == uint64(1)
			&& BaselineExport.BaseCheckpointManifestSha256
				== BasePersistenceRequest.Ticket.CheckpointManifestSha256
			&& BaselineExport.BaseJournalTailSha256
				== BasePersistenceRequest.Ticket.CheckpointJournalTailSha256
			&& BaselineExport.ThroughRevision == uint64(1)
			&& BaselineExport.Operations.IsEmpty()
			&& BaselineExport.FinalJournalTailSha256
				== BasePersistenceRequest.Ticket.CheckpointJournalTailSha256
			&& IsCanonicalSha256(
				BaselineExport.CanonicalManifestSha256));
	FString BaselineExportValidationError;
	const bool bBaselineExportValid =
		ValidateEditJournalExport(
			BaselineExport,
			Limits,
			&BaselineExportValidationError);
	TestTrue(
		FString::Printf(
			TEXT("The acknowledged base export validates: %s"),
			*BaselineExportValidationError),
		bBaselineExportValid);

	FVolumeCheckpoint BaselineCheckpoint;
	const bool bCapturedBaselineCheckpoint =
		Backend.CaptureCheckpointSet(
			VolumeStableId,
			BaselineCheckpoint,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The acknowledged live checkpoint remains capturable: %s"),
			*Error),
		bCapturedBaselineCheckpoint);
	if (!bCapturedBaselineCheckpoint)
	{
		return false;
	}
	TestTrue(TEXT("The live checkpoint matches the acknowledged base exactly"),
		BaselineCheckpoint.ThroughRevision == uint64(1)
			&& BaselineCheckpoint.CanonicalManifestSha256
				== BasePersistenceRequest.Ticket.CheckpointManifestSha256
			&& !BaselineCheckpoint.Chunks.IsEmpty());

	const uint64 RevisionBeforeEquivocation =
		Backend.GetCurrentRevision(VolumeStableId);
	const uint64 GenerationBeforeEquivocation =
		Backend.GetAuthorityGenerationToken(VolumeStableId);

	FCheckpointPersistenceRequest SameRevisionRequest;
	const bool bCapturedSameRevisionRequest =
		Backend.CaptureCheckpointForPersistence(
			VolumeStableId,
			SameRevisionRequest,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("An unchanged revision-one persistence request is issued: %s"),
			*Error),
		bCapturedSameRevisionRequest);
	if (!bCapturedSameRevisionRequest)
	{
		return false;
	}
	FString SameRevisionValidationError;
	const bool bSameRevisionRequestValid =
		ValidateCheckpointPersistenceRequest(
			SameRevisionRequest,
			&SameRevisionValidationError);
	TestTrue(
		FString::Printf(
			TEXT("The exact same-revision envelope validates: %s"),
			*SameRevisionValidationError),
		bSameRevisionRequestValid);
	const FCheckpointPersistenceTicket& SameRevisionTicket =
		SameRevisionRequest.Ticket;
	TestTrue(TEXT("The new request binds the exact acknowledged base identity"),
		SameRevisionTicket.bExpectedAcknowledgedBase
			&& SameRevisionTicket.ExpectedJournalBaseRevision == uint64(1)
			&& SameRevisionTicket.CheckpointThroughRevision == uint64(1)
			&& SameRevisionTicket.ExpectedBaseCheckpointManifestSha256
				== BasePersistenceRequest.Ticket.CheckpointManifestSha256
			&& SameRevisionTicket.CheckpointManifestSha256
				== SameRevisionTicket.ExpectedBaseCheckpointManifestSha256
			&& SameRevisionTicket.ExpectedBaseJournalTailSha256
				== BasePersistenceRequest.Ticket.CheckpointJournalTailSha256
			&& SameRevisionTicket.CheckpointJournalTailSha256
				== SameRevisionTicket.ExpectedBaseJournalTailSha256
			&& SameRevisionTicket.AuthorityGenerationToken
				== GenerationBeforeEquivocation
			&& SameRevisionTicket.BackendInstanceId
				== BasePersistenceRequest.Ticket.BackendInstanceId
			&& SameRevisionTicket.PersistenceRequestToken
				== BasePersistenceRequest.Ticket.PersistenceRequestToken
					+ uint64(1));

	const FString ConflictingCanonicalManifestSha256 =
		BaselineExport.CanonicalManifestSha256;
	TestTrue(TEXT("The conflicting manifest is canonical and distinct"),
		IsCanonicalSha256(ConflictingCanonicalManifestSha256)
			&& ConflictingCanonicalManifestSha256
				!= SameRevisionTicket.CheckpointManifestSha256);
	FCheckpointPersistenceRequest ConflictingRequest =
		SameRevisionRequest;
	ConflictingRequest.Ticket.CheckpointManifestSha256 =
		ConflictingCanonicalManifestSha256;
	ConflictingRequest.Checkpoint.CanonicalManifestSha256 =
		ConflictingCanonicalManifestSha256;
	TestTrue(TEXT("Only the detached checkpoint manifest is equivocated"),
		ConflictingRequest.Ticket.TargetStableId
				== SameRevisionTicket.TargetStableId
			&& ConflictingRequest.Ticket.VolumeSpecSha256
				== SameRevisionTicket.VolumeSpecSha256
			&& ConflictingRequest.Ticket.bExpectedAcknowledgedBase
				== SameRevisionTicket.bExpectedAcknowledgedBase
			&& ConflictingRequest.Ticket.ExpectedJournalBaseRevision
				== SameRevisionTicket.ExpectedJournalBaseRevision
			&& ConflictingRequest.Ticket.ExpectedBaseCheckpointManifestSha256
				== SameRevisionTicket.ExpectedBaseCheckpointManifestSha256
			&& ConflictingRequest.Ticket.ExpectedBaseJournalTailSha256
				== SameRevisionTicket.ExpectedBaseJournalTailSha256
			&& ConflictingRequest.Ticket.CheckpointThroughRevision
				== SameRevisionTicket.CheckpointThroughRevision
			&& ConflictingRequest.Ticket.CheckpointJournalTailSha256
				== SameRevisionTicket.CheckpointJournalTailSha256
			&& ConflictingRequest.Ticket.AuthorityGenerationToken
				== SameRevisionTicket.AuthorityGenerationToken
			&& ConflictingRequest.Ticket.BackendInstanceId
				== SameRevisionTicket.BackendInstanceId
			&& ConflictingRequest.Ticket.PersistenceRequestToken
				== SameRevisionTicket.PersistenceRequestToken);

	FString ConflictingValidationError;
	const bool bConflictingRequestValid =
		ValidateCheckpointPersistenceRequest(
			ConflictingRequest,
			&ConflictingValidationError);
	TestFalse(TEXT("A same-revision conflicting manifest is invalid"),
		bConflictingRequestValid);
	TestTrue(TEXT("Validation identifies same-revision checkpoint equivocation"),
		ConflictingValidationError.Contains(TEXT(
			"same-revision checkpoint identity does not match its acknowledged journal base")));

	FCheckpointPersistenceAcknowledgement ConflictingAcknowledgement;
	ConflictingAcknowledgement.Ticket =
		ConflictingRequest.Ticket;
	const bool bAcknowledgedConflictingManifest =
		Backend.AcknowledgePersistedCheckpoint(
			ConflictingAcknowledgement,
			Error);
	TestFalse(TEXT("The backend rejects same-revision manifest equivocation"),
		bAcknowledgedConflictingManifest);
	TestTrue(TEXT("The backend rejection names the same-revision identity"),
		Error.Contains(TEXT(
			"same-revision checkpoint identity does not match its acknowledged journal base")));
	TestEqual(TEXT("Equivocation cannot change live revision"),
		Backend.GetCurrentRevision(VolumeStableId),
		RevisionBeforeEquivocation);
	TestEqual(TEXT("Equivocation cannot advance authority generation"),
		Backend.GetAuthorityGenerationToken(VolumeStableId),
		GenerationBeforeEquivocation);

	FVolumeCheckpoint AfterEquivocationCheckpoint;
	const bool bCapturedAfterEquivocation =
		Backend.CaptureCheckpointSet(
			VolumeStableId,
			AfterEquivocationCheckpoint,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("Live content remains capturable after rejection: %s"),
			*Error),
		bCapturedAfterEquivocation);
	if (!bCapturedAfterEquivocation)
	{
		return false;
	}
	TestTrue(TEXT("Equivocation preserves the complete checkpoint identity"),
		AfterEquivocationCheckpoint.TargetStableId
				== BaselineCheckpoint.TargetStableId
			&& AfterEquivocationCheckpoint.VolumeSpecSha256
				== BaselineCheckpoint.VolumeSpecSha256
			&& AfterEquivocationCheckpoint.ThroughRevision
				== BaselineCheckpoint.ThroughRevision
			&& AfterEquivocationCheckpoint.CanonicalManifestSha256
				== BaselineCheckpoint.CanonicalManifestSha256
			&& AfterEquivocationCheckpoint.Chunks.Num()
				== BaselineCheckpoint.Chunks.Num());
	if (AfterEquivocationCheckpoint.Chunks.Num()
		!= BaselineCheckpoint.Chunks.Num())
	{
		return false;
	}
	for (int32 ChunkIndex = 0;
		ChunkIndex < BaselineCheckpoint.Chunks.Num();
		++ChunkIndex)
	{
		const FChunkCheckpoint& BeforeChunk =
			BaselineCheckpoint.Chunks[ChunkIndex];
		const FChunkCheckpoint& AfterChunk =
			AfterEquivocationCheckpoint.Chunks[ChunkIndex];
		TestTrue(
			FString::Printf(
				TEXT("Equivocation preserves checkpoint chunk %d"),
				ChunkIndex),
			AfterChunk.TargetStableId == BeforeChunk.TargetStableId
				&& AfterChunk.ChunkCoordinate
					== BeforeChunk.ChunkCoordinate
				&& AfterChunk.ThroughRevision
					== BeforeChunk.ThroughRevision
				&& AfterChunk.VolumeSpecSha256
					== BeforeChunk.VolumeSpecSha256
				&& AfterChunk.CanonicalPayloadSha256
					== BeforeChunk.CanonicalPayloadSha256
				&& AfterChunk.CompressedDensityAndMaterial
					== BeforeChunk.CompressedDensityAndMaterial);
	}

	FEditJournalExport ExportAfterEquivocation;
	const bool bExportedAfterEquivocation =
		Backend.ExportOperationJournal(
			VolumeStableId,
			ExportAfterEquivocation,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The prior durability base remains exportable: %s"),
			*Error),
		bExportedAfterEquivocation);
	if (!bExportedAfterEquivocation)
	{
		return false;
	}
	TestTrue(TEXT("Equivocation leaves every export identity field exact"),
		ExportAfterEquivocation.TargetStableId
				== BaselineExport.TargetStableId
			&& ExportAfterEquivocation.VolumeSpecSha256
				== BaselineExport.VolumeSpecSha256
			&& ExportAfterEquivocation.BaseCheckpointRevision
				== BaselineExport.BaseCheckpointRevision
			&& ExportAfterEquivocation.BaseCheckpointManifestSha256
				== BaselineExport.BaseCheckpointManifestSha256
			&& ExportAfterEquivocation.BaseJournalTailSha256
				== BaselineExport.BaseJournalTailSha256
			&& ExportAfterEquivocation.ThroughRevision
				== BaselineExport.ThroughRevision
			&& ExportAfterEquivocation.Operations.Num()
				== BaselineExport.Operations.Num()
			&& ExportAfterEquivocation.FinalJournalTailSha256
				== BaselineExport.FinalJournalTailSha256
			&& ExportAfterEquivocation.CanonicalManifestSha256
				== BaselineExport.CanonicalManifestSha256);

	const bool bDuplicateBaseStillIdempotent =
		Backend.AcknowledgePersistedCheckpoint(
			BaseAcknowledgement,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The prior acknowledgement remains duplicate-idempotent: %s"),
			*Error),
		bDuplicateBaseStillIdempotent);
	FCheckpointPersistenceAcknowledgement ExactSameRevisionAcknowledgement;
	ExactSameRevisionAcknowledgement.Ticket =
		SameRevisionRequest.Ticket;
	const bool bAcknowledgedExactSameRevision =
		Backend.AcknowledgePersistedCheckpoint(
			ExactSameRevisionAcknowledgement,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The untouched pending same-revision ticket still acknowledges: %s"),
			*Error),
		bAcknowledgedExactSameRevision);

	FEditJournalExport FinalExport;
	const bool bExportedFinal =
		Backend.ExportOperationJournal(
			VolumeStableId,
			FinalExport,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The exact same-revision acknowledgement exports: %s"),
			*Error),
		bExportedFinal);
	if (!bExportedFinal)
	{
		return false;
	}
	TestTrue(TEXT("Exact acknowledgement preserves the durable base bytes"),
		FinalExport.TargetStableId == BaselineExport.TargetStableId
			&& FinalExport.VolumeSpecSha256
				== BaselineExport.VolumeSpecSha256
			&& FinalExport.BaseCheckpointRevision
				== BaselineExport.BaseCheckpointRevision
			&& FinalExport.BaseCheckpointManifestSha256
				== BaselineExport.BaseCheckpointManifestSha256
			&& FinalExport.BaseJournalTailSha256
				== BaselineExport.BaseJournalTailSha256
			&& FinalExport.ThroughRevision
				== BaselineExport.ThroughRevision
			&& FinalExport.Operations.Num()
				== BaselineExport.Operations.Num()
			&& FinalExport.FinalJournalTailSha256
				== BaselineExport.FinalJournalTailSha256
			&& FinalExport.CanonicalManifestSha256
				== BaselineExport.CanonicalManifestSha256);
	FString FinalExportValidationError;
	const bool bFinalExportValid =
		ValidateEditJournalExport(
			FinalExport,
			Limits,
			&FinalExportValidationError);
	TestTrue(
		FString::Printf(
			TEXT("The final unchanged durability base validates: %s"),
			*FinalExportValidationError),
		bFinalExportValid);

	return !HasAnyErrors();
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FRedVoxelJournalCapacityReleaseTest,
	"RedMMO.Mining.VoxelBackend.JournalCapacityRelease",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRedVoxelJournalCapacityReleaseTest::RunTest(
	const FString& Parameters)
{
	using namespace RedVoxelMining;
	using namespace RedVoxelMiningTests;
	(void)Parameters;

	FAuthorityLimits Limits;
	Limits.MaxJournalOperationsPerCheckpoint = 1;
	FVolumeSpec Spec = MakeVolumeSpec();
	FString CanonicalSpecSha256;
	const bool bFingerprintComputed =
		ComputeCanonicalVolumeSpecSha256(Spec, CanonicalSpecSha256);
	TestTrue(
		TEXT("The capacity fixture receives a canonical spec fingerprint"),
		bFingerprintComputed);
	if (!bFingerprintComputed)
	{
		return false;
	}
	Spec.CanonicalSpecSha256 = MoveTemp(CanonicalSpecSha256);

	FRedInMemorySparseVoxelBackend Backend;
	FString Error;
	const bool bInitialized =
		Backend.InitializeVolume(Spec, Limits, Error);
	TestTrue(
		FString::Printf(
			TEXT("The one-slot journal fixture initializes: %s"),
			*Error),
		bInitialized);
	if (!bInitialized)
	{
		return false;
	}
	const uint64 AuthorityGeneration =
		Backend.GetAuthorityGenerationToken(VolumeStableId);
	TestTrue(TEXT("The one-slot fixture starts at revision zero with live authority"),
		Backend.GetCurrentRevision(VolumeStableId) == uint64(0)
			&& AuthorityGeneration > uint64(0));

	FCheckpointPersistenceRequest RevisionZeroRequest;
	const bool bCapturedRevisionZeroRequest =
		Backend.CaptureCheckpointForPersistence(
			VolumeStableId,
			RevisionZeroRequest,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The revision-zero durability base is captured: %s"),
			*Error),
		bCapturedRevisionZeroRequest);
	if (!bCapturedRevisionZeroRequest)
	{
		return false;
	}
	FString RevisionZeroValidationError;
	const bool bRevisionZeroRequestValid =
		ValidateCheckpointPersistenceRequest(
			RevisionZeroRequest,
			&RevisionZeroValidationError);
	TestTrue(
		FString::Printf(
			TEXT("The revision-zero persistence envelope validates: %s"),
			*RevisionZeroValidationError),
		bRevisionZeroRequestValid);
	TestTrue(TEXT("The initial ticket binds an unacknowledged revision-zero base"),
		!RevisionZeroRequest.Ticket.bExpectedAcknowledgedBase
			&& RevisionZeroRequest.Ticket.ExpectedJournalBaseRevision
				== uint64(0)
			&& RevisionZeroRequest.Ticket.ExpectedBaseCheckpointManifestSha256
				.IsEmpty()
			&& RevisionZeroRequest.Ticket.ExpectedBaseJournalTailSha256
				.IsEmpty()
			&& RevisionZeroRequest.Ticket.CheckpointThroughRevision
				== uint64(0)
			&& RevisionZeroRequest.Checkpoint.ThroughRevision
				== uint64(0)
			&& RevisionZeroRequest.Ticket.CheckpointManifestSha256
				== RevisionZeroRequest.Checkpoint.CanonicalManifestSha256
			&& RevisionZeroRequest.Ticket.AuthorityGenerationToken
				== AuthorityGeneration);

	FCheckpointPersistenceAcknowledgement RevisionZeroAcknowledgement;
	RevisionZeroAcknowledgement.Ticket =
		RevisionZeroRequest.Ticket;
	const bool bAcknowledgedRevisionZero =
		Backend.AcknowledgePersistedCheckpoint(
			RevisionZeroAcknowledgement,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The exact revision-zero ticket is acknowledged: %s"),
			*Error),
		bAcknowledgedRevisionZero);
	if (!bAcknowledgedRevisionZero)
	{
		return false;
	}

	FEditJournalExport EmptyBaseExport;
	const bool bExportedEmptyBase =
		Backend.ExportOperationJournal(
			VolumeStableId,
			EmptyBaseExport,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The acknowledged revision-zero base exports: %s"),
			*Error),
		bExportedEmptyBase);
	if (!bExportedEmptyBase)
	{
		return false;
	}
	TestTrue(TEXT("The initial durability base is an exact empty suffix"),
		EmptyBaseExport.TargetStableId == VolumeStableId
			&& EmptyBaseExport.VolumeSpecSha256
				== Spec.CanonicalSpecSha256
			&& EmptyBaseExport.BaseCheckpointRevision == uint64(0)
			&& EmptyBaseExport.BaseCheckpointManifestSha256
				== RevisionZeroRequest.Ticket.CheckpointManifestSha256
			&& EmptyBaseExport.BaseJournalTailSha256
				== RevisionZeroRequest.Ticket.CheckpointJournalTailSha256
			&& EmptyBaseExport.ThroughRevision == uint64(0)
			&& EmptyBaseExport.Operations.IsEmpty()
			&& EmptyBaseExport.FinalJournalTailSha256
				== RevisionZeroRequest.Ticket.CheckpointJournalTailSha256
			&& IsCanonicalSha256(
				EmptyBaseExport.CanonicalManifestSha256));

	FApplyResult FirstResult;
	const bool bFirstEditAccepted = ApplyAcceptedEdit(
		Backend,
		1,
		FVector(-250.0, -50.0, -50.0),
		FirstResult,
		Error);
	TestTrue(
		FString::Printf(
			TEXT("The first edit fills the sole journal slot: %s"),
			*Error),
		bFirstEditAccepted);
	if (!bFirstEditAccepted)
	{
		return false;
	}
	TestTrue(TEXT("The first edit advances exactly from revision zero to one"),
		FirstResult.TargetStableId == VolumeStableId
			&& FirstResult.RequestSequence == uint64(1)
			&& FirstResult.AuthorityGenerationToken
				== AuthorityGeneration
			&& FirstResult.bAccepted
			&& FirstResult.RejectReason == EEditRejectReason::None
			&& FirstResult.PreviousRevision == uint64(0)
			&& FirstResult.AppliedRevision == uint64(1)
			&& FirstResult.TotalRemovedCellCount == 1
			&& Backend.GetCurrentRevision(VolumeStableId) == uint64(1));

	FVolumeCheckpoint BeforeCapacityCheckpoint;
	const bool bCapturedBeforeCapacity =
		Backend.CaptureCheckpointSet(
			VolumeStableId,
			BeforeCapacityCheckpoint,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The revision-one checkpoint is captured before refusal: %s"),
			*Error),
		bCapturedBeforeCapacity);
	if (!bCapturedBeforeCapacity)
	{
		return false;
	}

	FEditJournalExport BeforeCapacityExport;
	const bool bExportedBeforeCapacity =
		Backend.ExportOperationJournal(
			VolumeStableId,
			BeforeCapacityExport,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The full one-slot journal exports before refusal: %s"),
			*Error),
		bExportedBeforeCapacity);
	if (!bExportedBeforeCapacity
		|| BeforeCapacityExport.Operations.Num() != 1)
	{
		return false;
	}
	const FEditOperation& FirstOperation =
		BeforeCapacityExport.Operations[0];
	TestTrue(TEXT("The pre-refusal suffix occupies exactly one bounded slot"),
		BeforeCapacityExport.BaseCheckpointRevision == uint64(0)
			&& BeforeCapacityExport.BaseCheckpointManifestSha256
				== RevisionZeroRequest.Ticket.CheckpointManifestSha256
			&& BeforeCapacityExport.BaseJournalTailSha256
				== RevisionZeroRequest.Ticket.CheckpointJournalTailSha256
			&& BeforeCapacityExport.ThroughRevision == uint64(1)
			&& FirstOperation.PreviousRevision == uint64(0)
			&& FirstOperation.Revision == uint64(1)
			&& FirstOperation.RequestSequence == uint64(1)
			&& FirstOperation.PreviousOperationSha256
				== RevisionZeroRequest.Ticket.CheckpointJournalTailSha256
			&& BeforeCapacityExport.FinalJournalTailSha256
				== FirstOperation.CanonicalOperationSha256
			&& IsCanonicalSha256(
				BeforeCapacityExport.CanonicalManifestSha256));

	FValidatedEdit CapacityEdit;
	CapacityEdit.TargetStableId = VolumeStableId;
	CapacityEdit.CollectorStableId = CollectorStableId;
	CapacityEdit.MiningToolStableId = MiningToolStableId;
	CapacityEdit.RequestSequence = 2;
	CapacityEdit.ExpectedRevision = 1;
	CapacityEdit.LocalBrushCenter =
		FVector(-150.0, -50.0, -50.0);
	CapacityEdit.LocalSurfaceNormal = FVector::UpVector;
	CapacityEdit.BrushRadiusCm = 25.f;
	CapacityEdit.AuthorityGenerationToken =
		AuthorityGeneration;
	CapacityEdit.PredictionToken = FGuid::NewGuid();
	TestTrue(TEXT("The refused request has a stable prediction identity"),
		CapacityEdit.PredictionToken.IsValid());

	FApplyResult CapacityResult;
	const bool bCapacityRejectionHandled =
		Backend.ApplyValidatedEdit(
			CapacityEdit,
			CapacityResult,
			Error);
	TestTrue(TEXT("A full journal returns a validated capacity result"),
		bCapacityRejectionHandled);
	TestTrue(TEXT("The otherwise-valid second edit is rejected only for capacity"),
		bCapacityRejectionHandled
			&& !CapacityResult.bAccepted
			&& CapacityResult.RejectReason
				== EEditRejectReason::JournalCapacityReached
			&& CapacityResult.TargetStableId
				== CapacityEdit.TargetStableId
			&& CapacityResult.RequestSequence
				== CapacityEdit.RequestSequence
			&& CapacityResult.PredictionToken
				== CapacityEdit.PredictionToken
			&& CapacityResult.AuthorityGenerationToken
				== CapacityEdit.AuthorityGenerationToken
			&& CapacityResult.PreviousRevision == uint64(1)
			&& CapacityResult.AppliedRevision == uint64(1)
			&& CapacityResult.TotalRemovedCellCount == 0
			&& CapacityResult.MaterialYields.IsEmpty()
			&& CapacityResult.DirtyChunkCoordinates.IsEmpty()
			&& Error.IsEmpty());
	FString CapacityResultValidationError;
	TestTrue(
		FString::Printf(
			TEXT("The capacity rejection validates against the exact edit: %s"),
			*CapacityResultValidationError),
		ValidateApplyResult(
			CapacityResult,
			CapacityEdit,
			Spec,
			Limits,
			&CapacityResultValidationError));
	TestTrue(TEXT("Capacity refusal preserves live revision and generation"),
		Backend.GetCurrentRevision(VolumeStableId) == uint64(1)
			&& Backend.GetAuthorityGenerationToken(VolumeStableId)
				== AuthorityGeneration);

	FVolumeCheckpoint AfterCapacityCheckpoint;
	const bool bCapturedAfterCapacity =
		Backend.CaptureCheckpointSet(
			VolumeStableId,
			AfterCapacityCheckpoint,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The checkpoint remains capturable after refusal: %s"),
			*Error),
		bCapturedAfterCapacity);
	if (!bCapturedAfterCapacity)
	{
		return false;
	}
	TestTrue(TEXT("Capacity refusal preserves complete checkpoint identity"),
		AfterCapacityCheckpoint.TargetStableId
				== BeforeCapacityCheckpoint.TargetStableId
			&& AfterCapacityCheckpoint.MaterialTableId
				== BeforeCapacityCheckpoint.MaterialTableId
			&& AfterCapacityCheckpoint.VolumeSpecSha256
				== BeforeCapacityCheckpoint.VolumeSpecSha256
			&& AfterCapacityCheckpoint.ThroughRevision
				== BeforeCapacityCheckpoint.ThroughRevision
			&& AfterCapacityCheckpoint.CanonicalManifestSha256
				== BeforeCapacityCheckpoint.CanonicalManifestSha256
			&& AfterCapacityCheckpoint.Chunks.Num()
				== BeforeCapacityCheckpoint.Chunks.Num()
			&& !BeforeCapacityCheckpoint.Chunks.IsEmpty());
	if (AfterCapacityCheckpoint.Chunks.Num()
		!= BeforeCapacityCheckpoint.Chunks.Num())
	{
		return false;
	}
	for (int32 ChunkIndex = 0;
		ChunkIndex < BeforeCapacityCheckpoint.Chunks.Num();
		++ChunkIndex)
	{
		const FChunkCheckpoint& BeforeChunk =
			BeforeCapacityCheckpoint.Chunks[ChunkIndex];
		const FChunkCheckpoint& AfterChunk =
			AfterCapacityCheckpoint.Chunks[ChunkIndex];
		TestTrue(
			FString::Printf(
				TEXT("Capacity refusal preserves checkpoint chunk %d"),
				ChunkIndex),
			AfterChunk.TargetStableId == BeforeChunk.TargetStableId
				&& AfterChunk.ChunkCoordinate
					== BeforeChunk.ChunkCoordinate
				&& AfterChunk.ThroughRevision
					== BeforeChunk.ThroughRevision
				&& AfterChunk.VolumeSpecSha256
					== BeforeChunk.VolumeSpecSha256
				&& AfterChunk.CanonicalPayloadSha256
					== BeforeChunk.CanonicalPayloadSha256
				&& AfterChunk.CompressedDensityAndMaterial
					== BeforeChunk.CompressedDensityAndMaterial);
	}

	FEditJournalExport AfterCapacityExport;
	const bool bExportedAfterCapacity =
		Backend.ExportOperationJournal(
			VolumeStableId,
			AfterCapacityExport,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The full suffix remains exportable after refusal: %s"),
			*Error),
		bExportedAfterCapacity);
	if (!bExportedAfterCapacity
		|| AfterCapacityExport.Operations.Num() != 1)
	{
		return false;
	}
	const FEditOperation& RetainedFirstOperation =
		AfterCapacityExport.Operations[0];
	TestTrue(TEXT("Capacity refusal preserves the complete one-operation suffix"),
		AfterCapacityExport.TargetStableId
				== BeforeCapacityExport.TargetStableId
			&& AfterCapacityExport.VolumeSpecSha256
				== BeforeCapacityExport.VolumeSpecSha256
			&& AfterCapacityExport.BaseCheckpointRevision
				== BeforeCapacityExport.BaseCheckpointRevision
			&& AfterCapacityExport.BaseCheckpointManifestSha256
				== BeforeCapacityExport.BaseCheckpointManifestSha256
			&& AfterCapacityExport.BaseJournalTailSha256
				== BeforeCapacityExport.BaseJournalTailSha256
			&& AfterCapacityExport.ThroughRevision
				== BeforeCapacityExport.ThroughRevision
			&& AfterCapacityExport.FinalJournalTailSha256
				== BeforeCapacityExport.FinalJournalTailSha256
			&& AfterCapacityExport.CanonicalManifestSha256
				== BeforeCapacityExport.CanonicalManifestSha256
			&& RetainedFirstOperation.OperationId
				== FirstOperation.OperationId
			&& RetainedFirstOperation.ResultContentSha256
				== FirstOperation.ResultContentSha256
			&& RetainedFirstOperation.PreviousOperationSha256
				== FirstOperation.PreviousOperationSha256
			&& RetainedFirstOperation.CanonicalOperationSha256
				== FirstOperation.CanonicalOperationSha256);

	FCheckpointPersistenceRequest CapacityReleaseRequest;
	const bool bCapturedCapacityReleaseRequest =
		Backend.CaptureCheckpointForPersistence(
			VolumeStableId,
			CapacityReleaseRequest,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The full revision-one checkpoint is captured for durability: %s"),
			*Error),
		bCapturedCapacityReleaseRequest);
	if (!bCapturedCapacityReleaseRequest)
	{
		return false;
	}
	FString CapacityReleaseValidationError;
	const bool bCapacityReleaseRequestValid =
		ValidateCheckpointPersistenceRequest(
			CapacityReleaseRequest,
			&CapacityReleaseValidationError);
	TestTrue(
		FString::Printf(
			TEXT("The capacity-release persistence envelope validates: %s"),
			*CapacityReleaseValidationError),
		bCapacityReleaseRequestValid);
	TestTrue(TEXT("The release ticket binds the exact full journal prefix"),
		CapacityReleaseRequest.Ticket.bExpectedAcknowledgedBase
			&& CapacityReleaseRequest.Ticket.ExpectedJournalBaseRevision
				== uint64(0)
			&& CapacityReleaseRequest.Ticket.ExpectedBaseCheckpointManifestSha256
				== RevisionZeroRequest.Ticket.CheckpointManifestSha256
			&& CapacityReleaseRequest.Ticket.ExpectedBaseJournalTailSha256
				== RevisionZeroRequest.Ticket.CheckpointJournalTailSha256
			&& CapacityReleaseRequest.Ticket.CheckpointThroughRevision
				== uint64(1)
			&& CapacityReleaseRequest.Ticket.CheckpointManifestSha256
				== BeforeCapacityCheckpoint.CanonicalManifestSha256
			&& CapacityReleaseRequest.Ticket.CheckpointJournalTailSha256
				== FirstOperation.CanonicalOperationSha256
			&& CapacityReleaseRequest.Ticket.AuthorityGenerationToken
				== AuthorityGeneration);

	FApplyResult CaptureOnlyCapacityResult;
	const bool bCaptureOnlyCapacityRejectionHandled =
		Backend.ApplyValidatedEdit(
			CapacityEdit,
			CaptureOnlyCapacityResult,
			Error);
	TestTrue(TEXT("Checkpoint capture alone does not release journal capacity"),
		bCaptureOnlyCapacityRejectionHandled
			&& !CaptureOnlyCapacityResult.bAccepted
			&& CaptureOnlyCapacityResult.RejectReason
				== EEditRejectReason::JournalCapacityReached
			&& CaptureOnlyCapacityResult.TargetStableId
				== CapacityResult.TargetStableId
			&& CaptureOnlyCapacityResult.RequestSequence
				== CapacityResult.RequestSequence
			&& CaptureOnlyCapacityResult.PredictionToken
				== CapacityResult.PredictionToken
			&& CaptureOnlyCapacityResult.AuthorityGenerationToken
				== CapacityResult.AuthorityGenerationToken
			&& CaptureOnlyCapacityResult.PreviousRevision
				== CapacityResult.PreviousRevision
			&& CaptureOnlyCapacityResult.AppliedRevision
				== CapacityResult.AppliedRevision
			&& CaptureOnlyCapacityResult.TotalRemovedCellCount == 0
			&& CaptureOnlyCapacityResult.MaterialYields.IsEmpty()
			&& CaptureOnlyCapacityResult.DirtyChunkCoordinates.IsEmpty()
			&& Error.IsEmpty()
			&& Backend.GetCurrentRevision(VolumeStableId) == uint64(1)
			&& Backend.GetAuthorityGenerationToken(VolumeStableId)
				== AuthorityGeneration);

	FCheckpointPersistenceAcknowledgement CapacityReleaseAcknowledgement;
	CapacityReleaseAcknowledgement.Ticket =
		CapacityReleaseRequest.Ticket;
	const bool bAcknowledgedCapacityRelease =
		Backend.AcknowledgePersistedCheckpoint(
			CapacityReleaseAcknowledgement,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The untouched exact ticket acknowledges after capture-only refusal: %s"),
			*Error),
		bAcknowledgedCapacityRelease);
	if (!bAcknowledgedCapacityRelease)
	{
		return false;
	}
	TestTrue(TEXT("Acknowledgement compaction preserves revision and authority generation"),
		Backend.GetCurrentRevision(VolumeStableId) == uint64(1)
			&& Backend.GetAuthorityGenerationToken(VolumeStableId)
				== AuthorityGeneration);

	FEditJournalExport ReleasedCapacityExport;
	const bool bExportedReleasedCapacity =
		Backend.ExportOperationJournal(
			VolumeStableId,
			ReleasedCapacityExport,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The acknowledged revision-one base exports after compaction: %s"),
			*Error),
		bExportedReleasedCapacity);
	if (!bExportedReleasedCapacity)
	{
		return false;
	}
	TestTrue(TEXT("Exact acknowledgement releases the sole journal slot"),
		ReleasedCapacityExport.TargetStableId == VolumeStableId
			&& ReleasedCapacityExport.VolumeSpecSha256
				== Spec.CanonicalSpecSha256
			&& ReleasedCapacityExport.BaseCheckpointRevision == uint64(1)
			&& ReleasedCapacityExport.BaseCheckpointManifestSha256
				== CapacityReleaseRequest.Ticket.CheckpointManifestSha256
			&& ReleasedCapacityExport.BaseJournalTailSha256
				== CapacityReleaseRequest.Ticket.CheckpointJournalTailSha256
			&& ReleasedCapacityExport.ThroughRevision == uint64(1)
			&& ReleasedCapacityExport.Operations.IsEmpty()
			&& ReleasedCapacityExport.FinalJournalTailSha256
				== CapacityReleaseRequest.Ticket.CheckpointJournalTailSha256
			&& IsCanonicalSha256(
				ReleasedCapacityExport.CanonicalManifestSha256));
	FString ReleasedExportValidationError;
	TestTrue(
		FString::Printf(
			TEXT("The empty released-capacity suffix validates: %s"),
			*ReleasedExportValidationError),
		ValidateEditJournalExport(
			ReleasedCapacityExport,
			Limits,
			&ReleasedExportValidationError));

	FVolumeCheckpoint AfterReleaseCheckpoint;
	const bool bCapturedAfterRelease =
		Backend.CaptureCheckpointSet(
			VolumeStableId,
			AfterReleaseCheckpoint,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The live checkpoint remains capturable after compaction: %s"),
			*Error),
		bCapturedAfterRelease);
	if (!bCapturedAfterRelease)
	{
		return false;
	}
	TestTrue(TEXT("Journal compaction cannot change authoritative density"),
		AfterReleaseCheckpoint.TargetStableId
				== BeforeCapacityCheckpoint.TargetStableId
			&& AfterReleaseCheckpoint.VolumeSpecSha256
				== BeforeCapacityCheckpoint.VolumeSpecSha256
			&& AfterReleaseCheckpoint.ThroughRevision
				== BeforeCapacityCheckpoint.ThroughRevision
			&& AfterReleaseCheckpoint.CanonicalManifestSha256
				== BeforeCapacityCheckpoint.CanonicalManifestSha256
			&& AfterReleaseCheckpoint.Chunks.Num()
				== BeforeCapacityCheckpoint.Chunks.Num());

	FApplyResult RetriedCapacityResult;
	const bool bRetriedCapacityEditAccepted =
		Backend.ApplyValidatedEdit(
			CapacityEdit,
			RetriedCapacityResult,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The identical refused edit succeeds after exact acknowledgement: %s"),
			*Error),
		bRetriedCapacityEditAccepted
			&& RetriedCapacityResult.bAccepted);
	if (!bRetriedCapacityEditAccepted
		|| !RetriedCapacityResult.bAccepted)
	{
		return false;
	}
	TestTrue(TEXT("The retry preserves exact request identity and advances once"),
		RetriedCapacityResult.TargetStableId
				== CapacityEdit.TargetStableId
			&& RetriedCapacityResult.RequestSequence
				== CapacityEdit.RequestSequence
			&& RetriedCapacityResult.PredictionToken
				== CapacityEdit.PredictionToken
			&& RetriedCapacityResult.AuthorityGenerationToken
				== CapacityEdit.AuthorityGenerationToken
			&& RetriedCapacityResult.RejectReason
				== EEditRejectReason::None
			&& RetriedCapacityResult.PreviousRevision == uint64(1)
			&& RetriedCapacityResult.AppliedRevision == uint64(2)
			&& RetriedCapacityResult.TotalRemovedCellCount == 1
			&& Backend.GetCurrentRevision(VolumeStableId) == uint64(2)
			&& Backend.GetAuthorityGenerationToken(VolumeStableId)
				== AuthorityGeneration);

	FEditJournalExport FinalExport;
	const bool bExportedFinal =
		Backend.ExportOperationJournal(
			VolumeStableId,
			FinalExport,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The retried edit exports as the sole new suffix: %s"),
			*Error),
		bExportedFinal);
	if (!bExportedFinal || FinalExport.Operations.Num() != 1)
	{
		return false;
	}
	const FEditOperation& RetriedOperation =
		FinalExport.Operations[0];
	TestTrue(TEXT("The retried operation rechains from the acknowledged checkpoint"),
		FinalExport.TargetStableId == VolumeStableId
			&& FinalExport.VolumeSpecSha256
				== Spec.CanonicalSpecSha256
			&& FinalExport.BaseCheckpointRevision == uint64(1)
			&& FinalExport.BaseCheckpointManifestSha256
				== CapacityReleaseRequest.Ticket.CheckpointManifestSha256
			&& FinalExport.BaseJournalTailSha256
				== CapacityReleaseRequest.Ticket.CheckpointJournalTailSha256
			&& FinalExport.ThroughRevision == uint64(2)
			&& RetriedOperation.TargetStableId
				== CapacityEdit.TargetStableId
			&& RetriedOperation.CollectorStableId
				== CapacityEdit.CollectorStableId
			&& RetriedOperation.MiningToolStableId
				== CapacityEdit.MiningToolStableId
			&& RetriedOperation.PreviousRevision == uint64(1)
			&& RetriedOperation.Revision == uint64(2)
			&& RetriedOperation.RequestSequence
				== CapacityEdit.RequestSequence
			&& RetriedOperation.PredictionToken
				== CapacityEdit.PredictionToken
			&& RetriedOperation.LocalBrushCenter
				== CapacityEdit.LocalBrushCenter
			&& RetriedOperation.PreviousOperationSha256
				== CapacityReleaseRequest.Ticket.CheckpointJournalTailSha256
			&& RetriedOperation.RemovedCellCount == 1
			&& FinalExport.FinalJournalTailSha256
				== RetriedOperation.CanonicalOperationSha256
			&& IsCanonicalSha256(
				FinalExport.CanonicalManifestSha256));
	FString FinalExportValidationError;
	TestTrue(
		FString::Printf(
			TEXT("The post-release one-operation suffix validates: %s"),
			*FinalExportValidationError),
		ValidateEditJournalExport(
			FinalExport,
			Limits,
			&FinalExportValidationError));

	FVolumeCheckpoint FinalCheckpoint;
	const bool bCapturedFinalCheckpoint =
		Backend.CaptureCheckpointSet(
			VolumeStableId,
			FinalCheckpoint,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The revision-two checkpoint is captured after retry: %s"),
			*Error),
		bCapturedFinalCheckpoint);
	TestTrue(TEXT("The successful retry changes the checkpoint exactly once"),
		bCapturedFinalCheckpoint
			&& FinalCheckpoint.ThroughRevision == uint64(2)
			&& FinalCheckpoint.CanonicalManifestSha256
				!= BeforeCapacityCheckpoint.CanonicalManifestSha256
			&& FinalCheckpoint.Chunks.Num()
				== BeforeCapacityCheckpoint.Chunks.Num());

	return !HasAnyErrors();
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FRedVoxelReleaseRecreateGenerationCASTest,
	"RedMMO.Mining.VoxelBackend.ReleaseRecreateGenerationCAS",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRedVoxelReleaseRecreateGenerationCASTest::RunTest(
	const FString& Parameters)
{
	using namespace RedVoxelMining;
	using namespace RedVoxelMiningTests;
	(void)Parameters;

	FAuthorityLimits Limits;
	FVolumeSpec Spec = MakeVolumeSpec();
	FString CanonicalSpecSha256;
	const bool bFingerprintComputed =
		ComputeCanonicalVolumeSpecSha256(Spec, CanonicalSpecSha256);
	TestTrue(
		TEXT("The release fixture receives a canonical fingerprint"),
		bFingerprintComputed);
	if (!bFingerprintComputed)
	{
		return false;
	}
	Spec.CanonicalSpecSha256 = MoveTemp(CanonicalSpecSha256);

	FRedInMemorySparseVoxelBackend Backend;
	FString Error;
	const bool bFirstInitialized =
		Backend.InitializeVolume(Spec, Limits, Error);
	TestTrue(
		FString::Printf(
			TEXT("Generation one initializes before lifecycle release: %s"),
			*Error),
		bFirstInitialized);
	if (!bFirstInitialized)
	{
		return false;
	}
	const uint64 FirstGeneration =
		Backend.GetAuthorityGenerationToken(VolumeStableId);
	TestTrue(TEXT("Generation one is a live nonzero capability"),
		FirstGeneration > uint64(0));

	FVolumeCheckpoint FirstCheckpoint;
	const bool bCapturedFirstCheckpoint =
		Backend.CaptureCheckpointSet(
			VolumeStableId,
			FirstCheckpoint,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("Generation one checkpoint is capturable: %s"),
			*Error),
		bCapturedFirstCheckpoint);
	if (!bCapturedFirstCheckpoint)
	{
		return false;
	}

	const bool bAcceptedZeroGenerationRelease =
		Backend.ReleaseVolume(
			VolumeStableId,
			0,
			Error);
	TestFalse(TEXT("A zero-generation release is rejected"),
		bAcceptedZeroGenerationRelease);
	TestTrue(TEXT("Zero-generation rejection explains its failure"),
		Error.Contains(TEXT("nonzero authority generation token")));
	TestTrue(TEXT("Zero-generation rejection preserves generation one"),
		Backend.HasVolume(VolumeStableId)
			&& Backend.GetCurrentRevision(VolumeStableId) == uint64(0)
			&& Backend.GetAuthorityGenerationToken(VolumeStableId)
				== FirstGeneration);

	const bool bReleasedFirstGeneration =
		Backend.ReleaseVolume(
			VolumeStableId,
			FirstGeneration,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The exact generation-one release succeeds: %s"),
			*Error),
		bReleasedFirstGeneration);
	TestTrue(TEXT("Exact release removes only generation one"),
		bReleasedFirstGeneration
			&& !Backend.HasVolume(VolumeStableId)
			&& Backend.GetCurrentRevision(VolumeStableId) == uint64(0)
			&& Backend.GetAuthorityGenerationToken(VolumeStableId)
				== uint64(0)
			&& Error.IsEmpty());

	const bool bAcceptedMissingRelease =
		Backend.ReleaseVolume(
			VolumeStableId,
			FirstGeneration,
			Error);
	TestFalse(TEXT("A duplicate release of a missing generation is rejected"),
		bAcceptedMissingRelease);
	TestTrue(TEXT("Missing-generation rejection explains its failure"),
		Error.Contains(TEXT("target does not exist")));
	TestFalse(TEXT("Missing-generation rejection cannot recreate a volume"),
		Backend.HasVolume(VolumeStableId));

	const bool bSecondInitialized =
		Backend.InitializeVolume(Spec, Limits, Error);
	TestTrue(
		FString::Printf(
			TEXT("The same stable ID recreates as generation two: %s"),
			*Error),
		bSecondInitialized);
	if (!bSecondInitialized)
	{
		return false;
	}
	const uint64 SecondGeneration =
		Backend.GetAuthorityGenerationToken(VolumeStableId);
	TestEqual(TEXT("Recreation advances the tombstoned generation once"),
		SecondGeneration,
		FirstGeneration + 1);

	FApplyResult SecondGenerationEditResult;
	const bool bSecondGenerationEditAccepted =
		ApplyAcceptedEdit(
			Backend,
			1,
			FVector(-250.0, -50.0, -50.0),
			SecondGenerationEditResult,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("Generation two obtains distinct authoritative content: %s"),
			*Error),
		bSecondGenerationEditAccepted);
	if (!bSecondGenerationEditAccepted)
	{
		return false;
	}

	FVolumeCheckpoint BeforeStaleReleaseCheckpoint;
	const bool bCapturedBeforeStaleRelease =
		Backend.CaptureCheckpointSet(
			VolumeStableId,
			BeforeStaleReleaseCheckpoint,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("Generation two is captured before stale teardown: %s"),
			*Error),
		bCapturedBeforeStaleRelease);
	if (!bCapturedBeforeStaleRelease)
	{
		return false;
	}

	const bool bAcceptedStaleRelease =
		Backend.ReleaseVolume(
			VolumeStableId,
			FirstGeneration,
			Error);
	TestFalse(TEXT("A delayed generation-one release cannot delete generation two"),
		bAcceptedStaleRelease);
	TestTrue(TEXT("Stale lifecycle rejection explains its failure"),
		Error.Contains(TEXT("stale or future authority generation")));
	TestTrue(TEXT("Stale release preserves generation-two authority identity"),
		Backend.HasVolume(VolumeStableId)
			&& Backend.GetCurrentRevision(VolumeStableId) == uint64(1)
			&& Backend.GetAuthorityGenerationToken(VolumeStableId)
				== SecondGeneration);

	FVolumeCheckpoint AfterStaleReleaseCheckpoint;
	const bool bCapturedAfterStaleRelease =
		Backend.CaptureCheckpointSet(
			VolumeStableId,
			AfterStaleReleaseCheckpoint,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("Generation two remains capturable after stale teardown: %s"),
			*Error),
		bCapturedAfterStaleRelease);
	if (!bCapturedAfterStaleRelease)
	{
		return false;
	}
	TestTrue(TEXT("Stale release preserves the complete checkpoint envelope"),
		AfterStaleReleaseCheckpoint.TargetStableId
				== BeforeStaleReleaseCheckpoint.TargetStableId
			&& AfterStaleReleaseCheckpoint.VolumeSpecSha256
				== BeforeStaleReleaseCheckpoint.VolumeSpecSha256
			&& AfterStaleReleaseCheckpoint.MaterialTableId
				== BeforeStaleReleaseCheckpoint.MaterialTableId
			&& AfterStaleReleaseCheckpoint.ThroughRevision
				== BeforeStaleReleaseCheckpoint.ThroughRevision
			&& AfterStaleReleaseCheckpoint.CanonicalManifestSha256
				== BeforeStaleReleaseCheckpoint.CanonicalManifestSha256
			&& AfterStaleReleaseCheckpoint.Chunks.Num()
				== BeforeStaleReleaseCheckpoint.Chunks.Num());
	if (AfterStaleReleaseCheckpoint.Chunks.Num()
		!= BeforeStaleReleaseCheckpoint.Chunks.Num())
	{
		return false;
	}
	for (int32 ChunkIndex = 0;
		ChunkIndex < BeforeStaleReleaseCheckpoint.Chunks.Num();
		++ChunkIndex)
	{
		const FChunkCheckpoint& BeforeChunk =
			BeforeStaleReleaseCheckpoint.Chunks[ChunkIndex];
		const FChunkCheckpoint& AfterChunk =
			AfterStaleReleaseCheckpoint.Chunks[ChunkIndex];
		TestTrue(
			FString::Printf(
				TEXT("Stale release preserves checkpoint chunk %d"),
				ChunkIndex),
			AfterChunk.TargetStableId == BeforeChunk.TargetStableId
				&& AfterChunk.ChunkCoordinate
					== BeforeChunk.ChunkCoordinate
				&& AfterChunk.ThroughRevision
					== BeforeChunk.ThroughRevision
				&& AfterChunk.VolumeSpecSha256
					== BeforeChunk.VolumeSpecSha256
				&& AfterChunk.CanonicalPayloadSha256
					== BeforeChunk.CanonicalPayloadSha256
				&& AfterChunk.CompressedDensityAndMaterial
					== BeforeChunk.CompressedDensityAndMaterial);
	}

	const bool bAcceptedFutureRelease =
		Backend.ReleaseVolume(
			VolumeStableId,
			SecondGeneration + 1,
			Error);
	TestFalse(TEXT("A future-generation release is rejected"),
		bAcceptedFutureRelease);
	TestTrue(TEXT("Future-generation rejection preserves generation two"),
		Error.Contains(TEXT("stale or future authority generation"))
			&& Backend.HasVolume(VolumeStableId)
			&& Backend.GetCurrentRevision(VolumeStableId) == uint64(1)
			&& Backend.GetAuthorityGenerationToken(VolumeStableId)
				== SecondGeneration);

	const bool bReleasedSecondGeneration =
		Backend.ReleaseVolume(
			VolumeStableId,
			SecondGeneration,
			Error);
	TestTrue(
		FString::Printf(
			TEXT("The exact generation-two release succeeds: %s"),
			*Error),
		bReleasedSecondGeneration);
	TestTrue(TEXT("Exact release removes generation two"),
		bReleasedSecondGeneration
			&& !Backend.HasVolume(VolumeStableId)
			&& Error.IsEmpty());

	const bool bThirdInitialized =
		Backend.InitializeVolume(Spec, Limits, Error);
	TestTrue(
		FString::Printf(
			TEXT("The same stable ID recreates as generation three: %s"),
			*Error),
		bThirdInitialized);
	if (!bThirdInitialized)
	{
		return false;
	}
	const uint64 ThirdGeneration =
		Backend.GetAuthorityGenerationToken(VolumeStableId);
	TestEqual(TEXT("A second recreation advances the tombstone exactly once"),
		ThirdGeneration,
		SecondGeneration + 1);
	TestTrue(TEXT("Generation three is live and begins at revision zero"),
		Backend.HasVolume(VolumeStableId)
			&& Backend.GetCurrentRevision(VolumeStableId) == uint64(0)
			&& ThirdGeneration > SecondGeneration
			&& Error.IsEmpty());

	return !HasAnyErrors();
}

#endif // WITH_DEV_AUTOMATION_TESTS
