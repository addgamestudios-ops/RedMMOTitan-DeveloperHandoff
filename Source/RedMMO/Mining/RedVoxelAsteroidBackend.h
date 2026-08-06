#pragma once

#include "CoreMinimal.h"
#include "RedVoxelMiningContracts.h"

/**
 * Project-owned isolation boundary for any admitted voxel implementation.
 *
 * Implementations may use a provenance-cleared plugin or a project-owned sparse-density store,
 * but plugin, DynamicMesh, ProceduralMesh, and collision-cook types must not cross this interface.
 * The backend never owns player inventory, reward presentation, collection actors, or client RPCs.
 */
class REDMMO_API IRedVoxelAsteroidBackend
{
public:
	virtual ~IRedVoxelAsteroidBackend() = default;

	virtual bool InitializeVolume(
		const RedVoxelMining::FVolumeSpec& Spec,
		const RedVoxelMining::FAuthorityLimits& Limits,
		FString& OutError) = 0;
	virtual bool HasVolume(FName StableId) const = 0;
	virtual uint64 GetCurrentRevision(FName StableId) const = 0;
	virtual uint64 GetAuthorityGenerationToken(FName StableId) const = 0;

	/**
	 * Applies one already server-validated brush command. The result must pass
	 * RedVoxelMining::ValidateApplyResult against that exact command and the
	 * authoritative volume spec before any loose cluster is created. Returning
	 * false guarantees that density, journal, revision, and output state did not change.
	 * An implementation must construct and validate its complete accepted result before
	 * atomically committing the density, journal, revision, and output invalidation.
	 */
	virtual bool ApplyValidatedEdit(
		const RedVoxelMining::FValidatedEdit& Edit,
		RedVoxelMining::FApplyResult& OutResult,
		FString& OutError) = 0;

	virtual bool ReadChunkRevision(
		FName StableId,
		const FIntVector& ChunkCoordinate,
		RedVoxelMining::FChunkRevision& OutRevision,
		FString& OutError) const = 0;
	virtual bool CaptureCheckpointSet(
		FName StableId,
		RedVoxelMining::FVolumeCheckpoint& OutCheckpoint,
		FString& OutError) const = 0;

	/**
	 * Returns the exact contiguous in-memory edit suffix after the last checkpoint
	 * explicitly acknowledged by a trusted persistence adapter. Export is read-only
	 * and fails before an acknowledged baseline exists.
	 */
	virtual bool ExportOperationJournal(
		FName StableId,
		RedVoxelMining::FEditJournalExport& OutExport,
		FString& OutError) const = 0;

	/**
	 * Captures one full checkpoint and issues a process-local, generation-bound
	 * capability for its eventual persistence acknowledgement. Reissuing supersedes
	 * the older pending checkpoint ticket for this volume.
	 */
	virtual bool CaptureCheckpointForPersistence(
		FName StableId,
		RedVoxelMining::FCheckpointPersistenceRequest& OutRequest,
		FString& OutError) = 0;

	/**
	 * Trusted server-side acknowledgement boundary. An exact live pending ticket may
	 * compact only the journal prefix covered by its checkpoint. This method cannot
	 * prove filesystem/database fsync and must never be exposed to clients or RPCs.
	 */
	virtual bool AcknowledgePersistedCheckpoint(
		const RedVoxelMining::FCheckpointPersistenceAcknowledgement& Acknowledgement,
		FString& OutError) = 0;

	/**
	 * Performs bounded decompression and canonical field hashing without mutating live state.
	 * It must validate every chunk before RestoreCheckpointSetAtomically may be called.
	 */
	virtual bool InspectCheckpointSet(
		const RedVoxelMining::FVolumeCheckpoint& Checkpoint,
		RedVoxelMining::FVolumeCheckpointVerification& OutVerification,
		FString& OutError) const = 0;

	/**
	 * Atomically replaces the whole authoritative volume. Returning false guarantees that no
	 * chunk, revision, journal, generated output, or collision state changed. The implementation
	 * must validate Precondition, require absence for InitializeAbsentVolume, or acquire an
	 * exclusive quiesced transaction and compare exact current revision/generation for
	 * ReplaceQuiescedVolume. A successful replacement advances the generation token exactly once;
	 * this routine never rolls a live volume back to an older content revision.
	 */
	virtual bool RestoreCheckpointSetAtomically(
		const RedVoxelMining::FVolumeCheckpoint& Checkpoint,
		const RedVoxelMining::FVolumeCheckpointVerification& Verification,
		const RedVoxelMining::FCheckpointRestorePrecondition& Precondition,
		FString& OutError) = 0;

	/**
	 * Issues one backend-instance-bound, single-role build request containing an
	 * immutable copy of the exact authoritative chunk. Reissuing the same role
	 * supersedes its older pending ticket without affecting the other role.
	 */
	virtual bool QueueChunkRebuild(
		const RedVoxelMining::FChunkRevision& Revision,
		RedVoxelMining::EGeneratedOutputRequirement OutputRole,
		RedVoxelMining::FGeneratedChunkBuildRequest& OutRequest,
		FString& OutError) = 0;

	/**
	 * Accepts one exact pending ticket after a project-owned adapter generated the
	 * requested role. Implementations must revalidate live target, spec, coordinate,
	 * per-chunk revision/hash, authority generation, backend instance, build profile,
	 * and one-time request token before readiness changes.
	 */
	virtual bool CompleteChunkRebuild(
		const RedVoxelMining::FGeneratedChunkBuildCompletion& Completion,
		FString& OutError) = 0;
	virtual bool QueryGeneratedOutputState(
		FName StableId,
		const FIntVector& ChunkCoordinate,
		RedVoxelMining::FGeneratedChunkOutputState& OutState,
		FString& OutError) const = 0;
	virtual void InvalidateBuildsOlderThan(
		FName StableId,
		uint64 GenerationToken) = 0;

	/**
	 * Releases one exact live authority generation.
	 *
	 * Lifecycle owners must retain the generation token returned for the volume they
	 * created and present it here. A missing volume, zero token, or stale/future token
	 * fails without mutating the live volume or its stable-ID generation tombstone.
	 * This prevents a delayed teardown for generation N from deleting a recreated
	 * generation N+1 that reused the same stable ID.
	 */
	virtual bool ReleaseVolume(
		FName StableId,
		uint64 ExpectedAuthorityGenerationToken,
		FString& OutError) = 0;
};
