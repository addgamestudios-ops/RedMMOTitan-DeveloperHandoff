#pragma once

#include "CoreMinimal.h"
#include "RedVoxelAsteroidBackend.h"

/**
 * Bounded project-owned authority store for the isolated M12 prototype.
 *
 * Non-empty density/material chunks are retained sparsely while every chunk keeps
 * authenticated revision metadata. This class deliberately has no actor, renderer,
 * collision cooker, inventory, RPC, persistence service, or plugin dependency.
 * The backend can issue immutable, single-role build requests and accept exact
 * attempt-bound completions, but no presentation or collision adapter is wired.
 *
 * All calls are game-thread only. The backend is not wired into production runtime.
 */
class REDMMO_API FRedInMemorySparseVoxelBackend final
	: public IRedVoxelAsteroidBackend
{
public:
	FRedInMemorySparseVoxelBackend();
	virtual ~FRedInMemorySparseVoxelBackend() override;

	FRedInMemorySparseVoxelBackend(
		const FRedInMemorySparseVoxelBackend&) = delete;
	FRedInMemorySparseVoxelBackend& operator=(
		const FRedInMemorySparseVoxelBackend&) = delete;

	virtual bool InitializeVolume(
		const RedVoxelMining::FVolumeSpec& Spec,
		const RedVoxelMining::FAuthorityLimits& Limits,
		FString& OutError) override;
	virtual bool HasVolume(FName StableId) const override;
	virtual uint64 GetCurrentRevision(FName StableId) const override;
	virtual uint64 GetAuthorityGenerationToken(FName StableId) const override;
	virtual bool ApplyValidatedEdit(
		const RedVoxelMining::FValidatedEdit& Edit,
		RedVoxelMining::FApplyResult& OutResult,
		FString& OutError) override;
	virtual bool ReadChunkRevision(
		FName StableId,
		const FIntVector& ChunkCoordinate,
		RedVoxelMining::FChunkRevision& OutRevision,
		FString& OutError) const override;
	virtual bool CaptureCheckpointSet(
		FName StableId,
		RedVoxelMining::FVolumeCheckpoint& OutCheckpoint,
		FString& OutError) const override;
	virtual bool ExportOperationJournal(
		FName StableId,
		RedVoxelMining::FEditJournalExport& OutExport,
		FString& OutError) const override;
	virtual bool CaptureCheckpointForPersistence(
		FName StableId,
		RedVoxelMining::FCheckpointPersistenceRequest& OutRequest,
		FString& OutError) override;
	virtual bool AcknowledgePersistedCheckpoint(
		const RedVoxelMining::FCheckpointPersistenceAcknowledgement& Acknowledgement,
		FString& OutError) override;
	virtual bool InspectCheckpointSet(
		const RedVoxelMining::FVolumeCheckpoint& Checkpoint,
		RedVoxelMining::FVolumeCheckpointVerification& OutVerification,
		FString& OutError) const override;
	virtual bool RestoreCheckpointSetAtomically(
		const RedVoxelMining::FVolumeCheckpoint& Checkpoint,
		const RedVoxelMining::FVolumeCheckpointVerification& Verification,
		const RedVoxelMining::FCheckpointRestorePrecondition& Precondition,
		FString& OutError) override;
	virtual bool QueueChunkRebuild(
		const RedVoxelMining::FChunkRevision& Revision,
		RedVoxelMining::EGeneratedOutputRequirement OutputRole,
		RedVoxelMining::FGeneratedChunkBuildRequest& OutRequest,
		FString& OutError) override;
	virtual bool CompleteChunkRebuild(
		const RedVoxelMining::FGeneratedChunkBuildCompletion& Completion,
		FString& OutError) override;
	virtual bool QueryGeneratedOutputState(
		FName StableId,
		const FIntVector& ChunkCoordinate,
		RedVoxelMining::FGeneratedChunkOutputState& OutState,
		FString& OutError) const override;
	virtual void InvalidateBuildsOlderThan(
		FName StableId,
		uint64 GenerationToken) override;
	virtual bool ReleaseVolume(
		FName StableId,
		uint64 ExpectedAuthorityGenerationToken,
		FString& OutError) override;

private:
	class FImpl;
	TUniquePtr<FImpl> Impl;
};
