#pragma once

#include "CoreMinimal.h"

/**
 * Backend-neutral authority contracts for the isolated M12 voxel-mining prototype.
 *
 * Client requests are untrusted hints. Only the server may produce FValidatedEdit,
 * apply it through IRedVoxelAsteroidBackend, convert the returned material yield
 * into loose clusters, and commit collection after an attracting cluster arrives.
 * Generated mesh and collision are outputs; density and material cells are truth.
 */
namespace RedVoxelMining
{
	inline constexpr int32 PrototypeHardMaxVolumeCellsPerAxis = 64;
	inline constexpr int32 PrototypeHardMaxChunkCellsPerAxis = 16;
	inline constexpr int32 PrototypeHardMaxEditedCellsPerRequest = 2048;
	inline constexpr int32 PrototypeHardMaxDirtyChunksPerEdit = 8;
	inline constexpr int32 PrototypeHardMaxYieldEntriesPerEdit = 4;
	inline constexpr int32 PrototypeHardMaxClustersPerEdit = 4;
	inline constexpr int32 PrototypeHardMaxJournalOperationsPerCheckpoint = 512;
	inline constexpr int32 PrototypeHardMaxRequestsPerSecond = 8;
	inline constexpr int32 PrototypeHardMaxCheckpointChunks = 64;
	inline constexpr int32 PrototypeHardMaxCompressedBytesPerChunk = 256 * 1024;
	inline constexpr int32 PrototypeHardMaxUncompressedBytesPerChunk = 64 * 1024;
	inline constexpr int32 PrototypeHardMaxCheckpointSetBytes = 16 * 1024 * 1024;
	inline constexpr uint32 PrototypeEditAlgorithmVersion = 1;
	inline constexpr float PrototypeHardMaxCellSizeCm = 100.f;
	inline constexpr float PrototypeHardMaxBrushRadiusCm = 300.f;
	inline constexpr float PrototypeHardMaxMiningRangeCm = 2500.f;
	inline constexpr float PrototypeHardMaxSuctionRangeCm = 2000.f;
	inline constexpr float PrototypeHardMaxSuctionDurationSeconds = 4.f;
	inline constexpr float PrototypeHardMaxReservationDurationSeconds = 6.f;
	inline constexpr float PrototypeHardMaxCollectionArrivalDistanceCm = 150.f;
	inline constexpr float PrototypeHardMaxCollectionArrivalGraceSeconds = 0.5f;

	enum class EEditRejectReason : uint8
	{
		None,
		BackendUnavailable,
		InvalidTarget,
		InvalidSequence,
		DuplicateRequest,
		SkippedSequence,
		StaleRevision,
		RevisionOverflow,
		InvalidTool,
		OutOfRange,
		Obstructed,
		RateLimited,
		InvalidBrush,
		ZeroRemovedVolume,
		JournalCapacityReached,
		CheckpointMismatch
	};

	enum class ELooseClusterPhase : uint8
	{
		Loose,
		Reserved,
		Attracting,
		Collected,
		Cancelled
	};

	enum class ECheckpointRestoreMode : uint8
	{
		InitializeAbsentVolume,
		ReplaceQuiescedVolume
	};

	enum class EGeneratedOutputRequirement : uint8
	{
		Presentation = 1,
		Collision = 2,
		PresentationAndCollision = 3
	};

	/** Hard limits for the first isolated prototype, not production capacity claims. */
	struct REDMMO_API FAuthorityLimits
	{
		int32 MaxVolumeCellsPerAxis = 64;
		int32 MaxChunkCellsPerAxis = 16;
		int32 MaxEditedCellsPerRequest = 2048;
		int32 MaxDirtyChunksPerEdit = 8;
		int32 MaxYieldEntriesPerEdit = 4;
		int32 MaxClustersPerEdit = 4;
		int32 MaxJournalOperationsPerCheckpoint = 512;
		int32 MaxRequestsPerSecond = 8;
		int32 MaxCheckpointChunks = 64;
		int32 MaxCompressedCheckpointBytesPerChunk = 256 * 1024;
		int32 MaxUncompressedCheckpointBytesPerChunk = 64 * 1024;
		int32 MaxCheckpointSetBytes = 16 * 1024 * 1024;
		float MinCellSizeCm = 75.f;
		float MaxCellSizeCm = 100.f;
		float MinBrushRadiusCm = 25.f;
		float MaxBrushRadiusCm = 300.f;
		float MaxMiningRangeCm = 2500.f;
		float MaxSuctionRangeCm = 2000.f;
		float MaxSuctionDurationSeconds = 4.f;
		float MaxReservationDurationSeconds = 6.f;
		float MaxCollectionArrivalDistanceCm = 150.f;
		float MaxCollectionArrivalGraceSeconds = 0.5f;
	};

	/** Immutable deterministic volume identity and dimensions. */
	struct REDMMO_API FVolumeSpec
	{
		FName StableId = NAME_None;
		FName MaterialTableId = NAME_None;
		FIntVector VolumeCellDimensions = FIntVector(64, 64, 64);
		FIntVector ChunkCellDimensions = FIntVector(16, 16, 16);
		float CellSizeCm = 100.f;
		uint32 BaseSeed = 0;
		uint32 GenerationVersion = 0;
		FString CanonicalSpecSha256;
	};

	/**
	 * Network envelope received from a client. Passing structural validation never authorizes an
	 * edit: the server still re-traces tool state, range, line of sight, target, and rate limits.
	 */
	struct REDMMO_API FClientEditRequest
	{
		FName TargetStableId = NAME_None;
		FName MiningToolStableId = NAME_None;
		uint64 RequestSequence = 0;
		uint64 ExpectedRevision = 0;
		FVector AimOrigin = FVector::ZeroVector;
		FVector AimDirection = FVector::ForwardVector;
		float BrushRadiusCm = 0.f;
		FGuid PredictionToken;
	};

	/** Server-produced command after all gameplay and anti-cheat validation succeeds. */
	struct REDMMO_API FValidatedEdit
	{
		FName TargetStableId = NAME_None;
		FName CollectorStableId = NAME_None;
		FName MiningToolStableId = NAME_None;
		uint64 RequestSequence = 0;
		uint64 ExpectedRevision = 0;
		FVector LocalBrushCenter = FVector::ZeroVector;
		FVector LocalSurfaceNormal = FVector::UpVector;
		float BrushRadiusCm = 0.f;
		uint64 AuthorityGenerationToken = 0;
		FGuid PredictionToken;
	};

	/**
	 * Server-owned contiguous request high-water state for one collector and asteroid.
	 * It is never populated from a client payload and has exactly one game-thread writer.
	 */
	struct REDMMO_API FRequestSequenceState
	{
		FName TargetStableId = NAME_None;
		FName CollectorStableId = NAME_None;
		uint64 LastAcceptedSequence = 0;
		uint64 LastAcceptedRevision = 0;
		FGuid LastAcceptedPredictionToken;
	};

	/** Yield derived only from cells that actually changed from solid to empty. */
	struct REDMMO_API FMaterialYield
	{
		FName MaterialId = NAME_None;
		int32 RemovedCellCount = 0;
		double RemovedVolumeCm3 = 0.0;
	};

	/** Atomic backend result. Rejections retain the prior revision and contain no yield. */
	struct REDMMO_API FApplyResult
	{
		FName TargetStableId = NAME_None;
		uint64 RequestSequence = 0;
		FGuid PredictionToken;
		uint64 AuthorityGenerationToken = 0;
		bool bAccepted = false;
		EEditRejectReason RejectReason = EEditRejectReason::BackendUnavailable;
		uint64 PreviousRevision = 0;
		uint64 AppliedRevision = 0;
		int32 TotalRemovedCellCount = 0;
		TArray<FMaterialYield> MaterialYields;
		TArray<FIntVector> DirtyChunkCoordinates;
	};

	/**
	 * Canonical hash-chained operation retained after an accepted edit.
	 * Export is supported for trusted server-side persistence transfer. Replay,
	 * import, replication, and a client-safe late-join DTO remain separate
	 * unimplemented trust boundaries.
	 */
	struct REDMMO_API FEditOperation
	{
		FName TargetStableId = NAME_None;
		FString VolumeSpecSha256;
		FGuid OperationId;
		FName CollectorStableId = NAME_None;
		FName MiningToolStableId = NAME_None;
		uint32 EditAlgorithmVersion = 0;
		uint64 PreviousRevision = 0;
		uint64 Revision = 0;
		uint64 RequestSequence = 0;
		FGuid PredictionToken;
		FVector LocalBrushCenter = FVector::ZeroVector;
		FVector LocalSurfaceNormal = FVector::UpVector;
		float BrushRadiusCm = 0.f;
		int32 RemovedCellCount = 0;
		FString ResultContentSha256;
		FString PreviousOperationSha256;
		FString CanonicalOperationSha256;
	};

	/** Revision and generation token used to reject stale asynchronous mesh/collision work. */
	struct REDMMO_API FChunkRevision
	{
		FName TargetStableId = NAME_None;
		FIntVector ChunkCoordinate = FIntVector::ZeroValue;
		uint64 ContentRevision = 0;
		FString ContentSha256;
		uint64 GenerationToken = 0;
	};

	/**
	 * Backend-issued, single-role capability for one immutable generated-output job.
	 *
	 * The instance ID and request token are server-private process-local replay guards.
	 * They are not authentication signatures and must never be accepted without an
	 * exact comparison against the backend's live pending ticket.
	 */
	struct REDMMO_API FGeneratedChunkBuildTicket
	{
		FChunkRevision SourceRevision;
		FString VolumeSpecSha256;
		EGeneratedOutputRequirement OutputRole =
			static_cast<EGeneratedOutputRequirement>(0);
		FName BuildProfileId = NAME_None;
		uint32 BuildProfileVersion = 0;
		FGuid BackendInstanceId;
		uint64 BuildRequestToken = 0;
	};

	/** Immutable bounded density/material snapshot consumed by a future output adapter. */
	struct REDMMO_API FGeneratedChunkBuildRequest
	{
		FGeneratedChunkBuildTicket Ticket;
		FVolumeSpec VolumeSpec;
		TArray<uint8> CanonicalDensityAndMaterial;
	};

	/**
	 * Completion proof returned by a project-owned output adapter.
	 * OutputSha256 fingerprints the role-specific generated artifact; it is not
	 * a cryptographic signature and cannot by itself prove that rendering or
	 * collision cooking actually occurred.
	 */
	struct REDMMO_API FGeneratedChunkBuildCompletion
	{
		FGeneratedChunkBuildTicket Ticket;
		FString OutputSha256;
	};

	/** Bounded serialized density/material state for one chunk. */
	struct REDMMO_API FChunkCheckpoint
	{
		FName TargetStableId = NAME_None;
		FIntVector ChunkCoordinate = FIntVector::ZeroValue;
		uint32 GenerationVersion = 0;
		uint64 ThroughRevision = 0;
		uint32 BaseSeed = 0;
		FName MaterialTableId = NAME_None;
		FString VolumeSpecSha256;
		int32 UncompressedCellCount = 0;
		int32 UncompressedByteCount = 0;
		FName CodecId = NAME_None;
		TArray<uint8> CompressedDensityAndMaterial;
		FString CanonicalPayloadSha256;
	};

	/** Whole-volume checkpoint transaction; partial per-chunk restore is forbidden. */
	struct REDMMO_API FVolumeCheckpoint
	{
		FName TargetStableId = NAME_None;
		/** Portable immutable spec required to inspect or initialize an absent volume. */
		FVolumeSpec VolumeSpec;
		/** Captured prototype policy; its canonical manifest contribution prevents drift. */
		FAuthorityLimits AuthorityLimits;
		uint32 GenerationVersion = 0;
		uint32 BaseSeed = 0;
		FName MaterialTableId = NAME_None;
		FString VolumeSpecSha256;
		uint64 ThroughRevision = 0;
		FString CanonicalManifestSha256;
		TArray<FChunkCheckpoint> Chunks;
	};

	/**
	 * Process-local capability issued with one exact checkpoint persistence request.
	 *
	 * The trusted persistence adapter must not acknowledge durable storage with a
	 * reconstructed ticket. BackendInstanceId and PersistenceRequestToken are replay
	 * guards, not signatures, and are accepted only by exact comparison with live state.
	 */
	struct REDMMO_API FCheckpointPersistenceTicket
	{
		FName TargetStableId = NAME_None;
		FString VolumeSpecSha256;
		bool bExpectedAcknowledgedBase = false;
		uint64 ExpectedJournalBaseRevision = 0;
		FString ExpectedBaseCheckpointManifestSha256;
		FString ExpectedBaseJournalTailSha256;
		uint64 CheckpointThroughRevision = 0;
		FString CheckpointManifestSha256;
		FString CheckpointJournalTailSha256;
		uint64 AuthorityGenerationToken = 0;
		FGuid BackendInstanceId;
		uint64 PersistenceRequestToken = 0;
	};

	/** Exact full-volume checkpoint and the capability required to acknowledge it. */
	struct REDMMO_API FCheckpointPersistenceRequest
	{
		FCheckpointPersistenceTicket Ticket;
		FVolumeCheckpoint Checkpoint;
	};

	/**
	 * Trusted adapter declaration that the exact issued checkpoint is durable.
	 * This plain value is not proof of fsync, replication, or external storage health.
	 */
	struct REDMMO_API FCheckpointPersistenceAcknowledgement
	{
		FCheckpointPersistenceTicket Ticket;
	};

	/**
	 * Portable contiguous edit suffix anchored to the last acknowledged checkpoint.
	 *
	 * An empty operation list is valid only when ThroughRevision equals
	 * BaseCheckpointRevision. CanonicalManifestSha256 covers the complete envelope
	 * and ordered operation hashes; it is an integrity fingerprint, not a signature
	 * or proof that this export belongs to the current live server incarnation.
	 */
	struct REDMMO_API FEditJournalExport
	{
		FName TargetStableId = NAME_None;
		FString VolumeSpecSha256;
		uint64 BaseCheckpointRevision = 0;
		FString BaseCheckpointManifestSha256;
		FString BaseJournalTailSha256;
		uint64 ThroughRevision = 0;
		TArray<FEditOperation> Operations;
		FString FinalJournalTailSha256;
		FString CanonicalManifestSha256;
	};

	/** Results of bounded decompression and canonical field hashing outside live state. */
	struct REDMMO_API FChunkCheckpointVerification
	{
		FIntVector ChunkCoordinate = FIntVector::ZeroValue;
		int32 ActualUncompressedByteCount = 0;
		FString RecomputedCanonicalPayloadSha256;
	};

	struct REDMMO_API FVolumeCheckpointVerification
	{
		FString RecomputedCanonicalManifestSha256;
		TArray<FChunkCheckpointVerification> Chunks;
	};

	/**
	 * Server-owned compare-and-swap precondition for a whole-volume restore.
	 * InitializeAbsentVolume requires no live volume. ReplaceQuiescedVolume requires
	 * exact current revision/generation and rejects rollback to an older revision.
	 */
	struct REDMMO_API FCheckpointRestorePrecondition
	{
		FName TargetStableId = NAME_None;
		ECheckpointRestoreMode Mode = ECheckpointRestoreMode::InitializeAbsentVolume;
		uint64 ExpectedCurrentRevision = 0;
		uint64 ExpectedAuthorityGenerationToken = 0;
	};

	/** Exact output readiness used to reject obsolete async presentation/collision work. */
	struct REDMMO_API FGeneratedChunkOutputState
	{
		FName TargetStableId = NAME_None;
		FIntVector ChunkCoordinate = FIntVector::ZeroValue;
		uint64 ContentRevision = 0;
		FString ContentSha256;
		uint64 GenerationToken = 0;
		bool bPresentationReady = false;
		bool bCollisionReady = false;
		FString PresentationOutputSha256;
		FString CollisionOutputSha256;
	};

	/**
	 * Server-authority logical collection snapshot. Presentation may interpolate or render
	 * particles, but only the server-owned state revision can advance collection. A future
	 * replication DTO must omit ReservationToken and other server-private proof fields.
	 */
	struct REDMMO_API FLooseClusterState
	{
		FGuid ClusterId;
		FName SourceAsteroidStableId = NAME_None;
		FName MaterialId = NAME_None;
		int32 Amount = 0;
		ELooseClusterPhase Phase = ELooseClusterPhase::Loose;
		FName CollectorStableId = NAME_None;
		FGuid ReservationToken;
		uint64 Revision = 0;
		double SpawnServerTimeSeconds = 0.0;
		double ReservationExpiryServerTimeSeconds = 0.0;
		double AttractionStartServerTimeSeconds = 0.0;
		double ExpectedArrivalServerTimeSeconds = 0.0;
		double CollectedServerTimeSeconds = 0.0;
	};

	/** Server-observed proof that one attracting cluster actually reached its collector. */
	struct REDMMO_API FServerSuctionArrivalEvidence
	{
		FGuid ClusterId;
		FName SourceAsteroidStableId = NAME_None;
		FName CollectorStableId = NAME_None;
		FGuid ReservationToken;
		uint64 ObservedClusterRevision = 0;
		FVector ClusterLocation = FVector::ZeroVector;
		FVector CollectorLocation = FVector::ZeroVector;
		double ObservedServerTimeSeconds = 0.0;
		bool bCollectorEligible = false;
		bool bLineOfSightClear = false;
	};

	/** Idempotency key and exact payload for the future durable inventory ledger. */
	struct REDMMO_API FInventoryCreditCommit
	{
		FGuid ClusterId;
		uint64 CollectedRevision = 0;
		FName CollectorStableId = NAME_None;
		FName MaterialId = NAME_None;
		int32 Amount = 0;
	};

	REDMMO_API bool IsNamespacedStableId(FName StableId);
	REDMMO_API bool IsCanonicalSha256(const FString& Value);
	REDMMO_API bool IsNextRevision(uint64 CurrentRevision, uint64 CandidateRevision);
	REDMMO_API bool ComputeCanonicalSha256(
		const uint8* Data,
		int32 DataLength,
		FString& OutSha256);
	REDMMO_API bool ComputeCanonicalVolumeSpecSha256(
		const FVolumeSpec& Spec,
		FString& OutSha256);
	REDMMO_API bool ValidateAuthorityLimits(
		const FAuthorityLimits& Limits,
		FString* OutReason = nullptr);
	REDMMO_API bool ValidateVolumeSpec(
		const FVolumeSpec& Spec,
		const FAuthorityLimits& Limits,
		FString* OutReason = nullptr);
	REDMMO_API bool ValidateClientRequestEnvelope(
		const FClientEditRequest& Request,
		const FAuthorityLimits& Limits,
		FString* OutReason = nullptr);
	REDMMO_API bool ValidateServerEdit(
		const FValidatedEdit& Edit,
		const FAuthorityLimits& Limits,
		FString* OutReason = nullptr);
	REDMMO_API bool CanAcceptNextClientRequest(
		const FRequestSequenceState& State,
		const FClientEditRequest& Request,
		FName AuthorityCollectorStableId,
		uint64 CurrentVolumeRevision,
		const FAuthorityLimits& Limits,
		FString* OutReason = nullptr);
	REDMMO_API bool CommitAcceptedClientRequest(
		FRequestSequenceState& State,
		const FClientEditRequest& Request,
		const FValidatedEdit& Edit,
		const FApplyResult& ValidatedResult,
		const FVolumeSpec& Volume,
		const FAuthorityLimits& Limits,
		FString* OutReason = nullptr);
	REDMMO_API bool ValidateApplyResult(
		const FApplyResult& Result,
		const FValidatedEdit& Edit,
		const FVolumeSpec& Volume,
		const FAuthorityLimits& Limits,
		FString* OutReason = nullptr);
	REDMMO_API bool ValidateChunkCheckpoint(
		const FChunkCheckpoint& Checkpoint,
		const FChunkCheckpointVerification& Verification,
		const FVolumeSpec& Volume,
		const FAuthorityLimits& Limits,
		FString* OutReason = nullptr);
	REDMMO_API bool ValidateVolumeCheckpoint(
		const FVolumeCheckpoint& Checkpoint,
		const FVolumeCheckpointVerification& Verification,
		const FVolumeSpec& Volume,
		const FAuthorityLimits& Limits,
		FString* OutReason = nullptr);
	REDMMO_API bool ValidateCheckpointPersistenceTicket(
		const FCheckpointPersistenceTicket& Ticket,
		FString* OutReason = nullptr);
	/**
	 * Cross-checks the issued ticket against the checkpoint envelope. Full bounded
	 * chunk inspection remains the backend's Capture/Inspect responsibility.
	 */
	REDMMO_API bool ValidateCheckpointPersistenceRequest(
		const FCheckpointPersistenceRequest& Request,
		FString* OutReason = nullptr);
	REDMMO_API bool ComputeCanonicalEditOperationSha256(
		const FEditOperation& Operation,
		FString& OutSha256);
	REDMMO_API bool ValidateEditOperation(
		const FEditOperation& Operation,
		const FAuthorityLimits& Limits,
		FString* OutReason = nullptr);
	REDMMO_API bool ComputeCanonicalEditJournalSha256(
		const FEditJournalExport& Export,
		FString& OutSha256);
	REDMMO_API bool ValidateEditJournalExport(
		const FEditJournalExport& Export,
		const FAuthorityLimits& Limits,
		FString* OutReason = nullptr);
	REDMMO_API bool ValidateCheckpointRestorePrecondition(
		const FCheckpointRestorePrecondition& Precondition,
		const FVolumeCheckpoint& Checkpoint,
		FString* OutReason = nullptr);
	REDMMO_API bool AreGeneratedOutputsCurrent(
		const FChunkRevision& Expected,
		const FGeneratedChunkOutputState& Actual,
		EGeneratedOutputRequirement Requirement);
	REDMMO_API bool ValidateGeneratedChunkBuildTicket(
		const FGeneratedChunkBuildTicket& Ticket,
		FString* OutReason = nullptr);
	REDMMO_API bool ValidateGeneratedChunkBuildCompletion(
		const FGeneratedChunkBuildCompletion& Completion,
		FString* OutReason = nullptr);
	REDMMO_API bool ValidateLooseClusterState(
		const FLooseClusterState& State,
		const FAuthorityLimits& Limits,
		FString* OutReason = nullptr);
	REDMMO_API bool CanTransitionLooseCluster(
		const FLooseClusterState& Current,
		const FLooseClusterState& Next,
		const FAuthorityLimits& Limits);
	REDMMO_API bool BuildInventoryCreditCommit(
		const FLooseClusterState& Current,
		const FLooseClusterState& Collected,
		const FServerSuctionArrivalEvidence& Evidence,
		const FAuthorityLimits& Limits,
		FInventoryCreditCommit& OutCommit,
		FString* OutReason = nullptr);
}
