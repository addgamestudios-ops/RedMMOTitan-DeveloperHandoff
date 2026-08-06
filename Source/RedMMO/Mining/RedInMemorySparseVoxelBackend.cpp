#include "RedInMemorySparseVoxelBackend.h"

namespace
{
	using namespace RedVoxelMining;

	static const FName RleCodecId(TEXT("red.codec.rle-v1"));
	static const FName PrototypeMaterialTableId(
		TEXT("red.material-table.prototype-v1"));
	static const FName StoneMaterialId(TEXT("red.material.stone"));
	static const FName IronMaterialId(TEXT("red.material.iron"));
	static const FName CrystalMaterialId(TEXT("red.material.crystal"));
	static const FName GeneratedOutputBuildProfileId(
		TEXT("red.voxel-output.profile.sparse-binary-v1"));
	static constexpr uint32 GeneratedOutputBuildProfileVersion = 1;

	/** Binary density plus fixed material ordinal in one canonical byte. */
	enum class ECellMaterial : uint8
	{
		Empty = 0,
		Stone = 1,
		Iron = 2,
		Crystal = 3
	};

	struct FStoredChunkMetadata
	{
		uint64 ContentRevision = 0;
		FString ContentSha256;
		FGeneratedChunkOutputState GeneratedOutput;
		FGeneratedChunkBuildTicket PresentationBuildTicket;
		FGeneratedChunkBuildTicket CollisionBuildTicket;
		bool bPresentationBuildPending = false;
		bool bCollisionBuildPending = false;
	};

	struct FStoredVolume
	{
		FVolumeSpec Spec;
		FAuthorityLimits Limits;
		uint64 CurrentRevision = 0;
		uint64 AuthorityGenerationToken = 1;
		uint64 MinimumAcceptedBuildGenerationToken = 1;
		TMap<int32, TArray<uint8>> NonEmptyChunks;
		TArray<FStoredChunkMetadata> ChunkMetadata;
		uint64 JournalBaseRevision = 0;
		bool bHasAcknowledgedCheckpoint = false;
		FString BaseCheckpointManifestSha256;
		FString BaseJournalTailSha256;
		FCheckpointPersistenceTicket PendingCheckpointTicket;
		FCheckpointPersistenceTicket LastAcknowledgedCheckpointTicket;
		bool bCheckpointPersistencePending = false;
		TArray<FEditOperation> Journal;
	};

	struct FManifestRecord
	{
		FIntVector ChunkCoordinate = FIntVector::ZeroValue;
		int32 UncompressedCellCount = 0;
		int32 UncompressedByteCount = 0;
		FName CodecId = NAME_None;
		FString PayloadSha256;
	};

	struct FDecodedCheckpoint
	{
		TMap<int32, TArray<uint8>> NonEmptyChunks;
		TArray<FStoredChunkMetadata> ChunkMetadata;
	};

	bool Fail(FString& OutError, const TCHAR* Error)
	{
		OutError = Error;
		return false;
	}

	bool Fail(FString& OutError, const FString& Error)
	{
		OutError = Error;
		return false;
	}

	bool RequireGameThread(FString& OutError)
	{
		if (!IsInGameThread())
		{
			return Fail(
				OutError,
				TEXT("the in-memory voxel authority backend is game-thread only"));
		}
		OutError.Reset();
		return true;
	}

	uint32 FloatBits(const float Value)
	{
		uint32 Bits = 0;
		static_assert(sizeof(Bits) == sizeof(Value));
		FMemory::Memcpy(&Bits, &Value, sizeof(Bits));
		return Bits;
	}

	bool AreLimitsEquivalent(
		const FAuthorityLimits& A,
		const FAuthorityLimits& B)
	{
		return A.MaxVolumeCellsPerAxis == B.MaxVolumeCellsPerAxis
			&& A.MaxChunkCellsPerAxis == B.MaxChunkCellsPerAxis
			&& A.MaxEditedCellsPerRequest == B.MaxEditedCellsPerRequest
			&& A.MaxDirtyChunksPerEdit == B.MaxDirtyChunksPerEdit
			&& A.MaxYieldEntriesPerEdit == B.MaxYieldEntriesPerEdit
			&& A.MaxClustersPerEdit == B.MaxClustersPerEdit
			&& A.MaxJournalOperationsPerCheckpoint
				== B.MaxJournalOperationsPerCheckpoint
			&& A.MaxRequestsPerSecond == B.MaxRequestsPerSecond
			&& A.MaxCheckpointChunks == B.MaxCheckpointChunks
			&& A.MaxCompressedCheckpointBytesPerChunk
				== B.MaxCompressedCheckpointBytesPerChunk
			&& A.MaxUncompressedCheckpointBytesPerChunk
				== B.MaxUncompressedCheckpointBytesPerChunk
			&& A.MaxCheckpointSetBytes == B.MaxCheckpointSetBytes
			&& FloatBits(A.MinCellSizeCm) == FloatBits(B.MinCellSizeCm)
			&& FloatBits(A.MaxCellSizeCm) == FloatBits(B.MaxCellSizeCm)
			&& FloatBits(A.MinBrushRadiusCm)
				== FloatBits(B.MinBrushRadiusCm)
			&& FloatBits(A.MaxBrushRadiusCm)
				== FloatBits(B.MaxBrushRadiusCm)
			&& FloatBits(A.MaxMiningRangeCm)
				== FloatBits(B.MaxMiningRangeCm)
			&& FloatBits(A.MaxSuctionRangeCm)
				== FloatBits(B.MaxSuctionRangeCm)
			&& FloatBits(A.MaxSuctionDurationSeconds)
				== FloatBits(B.MaxSuctionDurationSeconds)
			&& FloatBits(A.MaxReservationDurationSeconds)
				== FloatBits(B.MaxReservationDurationSeconds)
			&& FloatBits(A.MaxCollectionArrivalDistanceCm)
				== FloatBits(B.MaxCollectionArrivalDistanceCm)
			&& FloatBits(A.MaxCollectionArrivalGraceSeconds)
				== FloatBits(B.MaxCollectionArrivalGraceSeconds);
	}

	bool AreSpecsEquivalent(const FVolumeSpec& A, const FVolumeSpec& B)
	{
		return A.StableId == B.StableId
			&& A.MaterialTableId == B.MaterialTableId
			&& A.VolumeCellDimensions == B.VolumeCellDimensions
			&& A.ChunkCellDimensions == B.ChunkCellDimensions
			&& FloatBits(A.CellSizeCm) == FloatBits(B.CellSizeCm)
			&& A.BaseSeed == B.BaseSeed
			&& A.GenerationVersion == B.GenerationVersion
			&& A.CanonicalSpecSha256 == B.CanonicalSpecSha256;
	}

	bool ValidateSupportedSpec(
		const FVolumeSpec& Spec,
		const FAuthorityLimits& Limits,
		FString& OutError)
	{
		FString ValidationError;
		if (!ValidateVolumeSpec(Spec, Limits, &ValidationError))
		{
			return Fail(
				OutError,
				FString::Printf(
					TEXT("invalid volume specification: %s"),
					*ValidationError));
		}
		if (Spec.MaterialTableId != PrototypeMaterialTableId)
		{
			return Fail(
				OutError,
				TEXT("unsupported voxel material table for the bounded prototype"));
		}
		const int64 ChunkCellCount =
			static_cast<int64>(Spec.ChunkCellDimensions.X)
			* Spec.ChunkCellDimensions.Y
			* Spec.ChunkCellDimensions.Z;
		const FIntVector ChunkCounts(
			Spec.VolumeCellDimensions.X / Spec.ChunkCellDimensions.X,
			Spec.VolumeCellDimensions.Y / Spec.ChunkCellDimensions.Y,
			Spec.VolumeCellDimensions.Z / Spec.ChunkCellDimensions.Z);
		const int64 ChunkCount = static_cast<int64>(ChunkCounts.X)
			* ChunkCounts.Y * ChunkCounts.Z;
		const int64 WorstCaseCompressedChunkBytes = ChunkCellCount * 3;
		const int64 WorstCaseCheckpointBytes = ChunkCount
			* (ChunkCellCount + WorstCaseCompressedChunkBytes);
		if (ChunkCellCount
				> Limits.MaxUncompressedCheckpointBytesPerChunk
			|| WorstCaseCompressedChunkBytes
				> Limits.MaxCompressedCheckpointBytesPerChunk
			|| WorstCaseCheckpointBytes > Limits.MaxCheckpointSetBytes)
		{
			return Fail(
				OutError,
				TEXT("volume and checkpoint limits cannot represent every canonical chunk state"));
		}
		OutError.Reset();
		return true;
	}

	FIntVector GetChunkCounts(const FVolumeSpec& Spec)
	{
		return FIntVector(
			Spec.VolumeCellDimensions.X / Spec.ChunkCellDimensions.X,
			Spec.VolumeCellDimensions.Y / Spec.ChunkCellDimensions.Y,
			Spec.VolumeCellDimensions.Z / Spec.ChunkCellDimensions.Z);
	}

	int32 GetLinearIndex(
		const FIntVector& Coordinate,
		const FIntVector& Dimensions)
	{
		return Coordinate.X
			+ Dimensions.X * (Coordinate.Y + Dimensions.Y * Coordinate.Z);
	}

	FIntVector GetCoordinateFromLinearIndex(
		const int32 LinearIndex,
		const FIntVector& Dimensions)
	{
		const int32 XY = Dimensions.X * Dimensions.Y;
		const int32 Z = LinearIndex / XY;
		const int32 Remainder = LinearIndex - Z * XY;
		const int32 Y = Remainder / Dimensions.X;
		const int32 X = Remainder - Y * Dimensions.X;
		return FIntVector(X, Y, Z);
	}

	bool IsChunkCoordinateInBounds(
		const FIntVector& Coordinate,
		const FIntVector& ChunkCounts)
	{
		return Coordinate.X >= 0
			&& Coordinate.Y >= 0
			&& Coordinate.Z >= 0
			&& Coordinate.X < ChunkCounts.X
			&& Coordinate.Y < ChunkCounts.Y
			&& Coordinate.Z < ChunkCounts.Z;
	}

	int32 GetChunkCellCount(const FVolumeSpec& Spec)
	{
		return Spec.ChunkCellDimensions.X
			* Spec.ChunkCellDimensions.Y
			* Spec.ChunkCellDimensions.Z;
	}

	uint32 MixDeterministic32(uint32 Value)
	{
		Value ^= Value >> 16;
		Value *= 0x7FEB352DU;
		Value ^= Value >> 15;
		Value *= 0x846CA68BU;
		Value ^= Value >> 16;
		return Value;
	}

	uint8 GenerateCellMaterial(
		const FVolumeSpec& Spec,
		const FIntVector& CellCoordinate)
	{
		const int64 Dx = 2LL * CellCoordinate.X + 1
			- Spec.VolumeCellDimensions.X;
		const int64 Dy = 2LL * CellCoordinate.Y + 1
			- Spec.VolumeCellDimensions.Y;
		const int64 Dz = 2LL * CellCoordinate.Z + 1
			- Spec.VolumeCellDimensions.Z;
		const int32 MinimumDimension = FMath::Min3(
			Spec.VolumeCellDimensions.X,
			Spec.VolumeCellDimensions.Y,
			Spec.VolumeCellDimensions.Z);
		// Dx/Dy/Dz are doubled-cell coordinates. 9/16 of the containing
		// dimension yields a 27-36 m body at the 64-cell, 75-100 cm candidate.
		const int64 Radius = FMath::Max(
			1,
			(MinimumDimension * 9) / 16);
		if (Dx * Dx + Dy * Dy + Dz * Dz > Radius * Radius)
		{
			return static_cast<uint8>(ECellMaterial::Empty);
		}

		uint32 Hash = Spec.BaseSeed;
		Hash ^= Spec.GenerationVersion * 0x9E3779B9U;
		Hash ^= static_cast<uint32>(CellCoordinate.X) * 0x85EBCA6BU;
		Hash ^= static_cast<uint32>(CellCoordinate.Y) * 0xC2B2AE35U;
		Hash ^= static_cast<uint32>(CellCoordinate.Z) * 0x27D4EB2FU;
		Hash = MixDeterministic32(Hash);
		const uint32 MaterialBucket = Hash % 1000U;
		if (MaterialBucket < 35U)
		{
			return static_cast<uint8>(ECellMaterial::Crystal);
		}
		if (MaterialBucket < 130U)
		{
			return static_cast<uint8>(ECellMaterial::Iron);
		}
		return static_cast<uint8>(ECellMaterial::Stone);
	}

	FName GetMaterialId(const uint8 Material)
	{
		switch (static_cast<ECellMaterial>(Material))
		{
		case ECellMaterial::Stone:
			return StoneMaterialId;
		case ECellMaterial::Iron:
			return IronMaterialId;
		case ECellMaterial::Crystal:
			return CrystalMaterialId;
		default:
			return NAME_None;
		}
	}

	bool ContainsSolidCell(const TArray<uint8>& Cells)
	{
		for (const uint8 Cell : Cells)
		{
			if (Cell != static_cast<uint8>(ECellMaterial::Empty))
			{
				return true;
			}
		}
		return false;
	}

	bool ValidateChunkCellsAgainstBase(
		const FVolumeSpec& Spec,
		const FIntVector& ChunkCoordinate,
		const TArray<uint8>& Cells,
		int64* OutRemovedCellCount,
		FString& OutError)
	{
		if (OutRemovedCellCount)
		{
			*OutRemovedCellCount = 0;
		}
		if (Cells.Num() != GetChunkCellCount(Spec))
		{
			return Fail(
				OutError,
				TEXT("decoded chunk does not contain the exact cell count"));
		}
		for (int32 LocalZ = 0; LocalZ < Spec.ChunkCellDimensions.Z; ++LocalZ)
		{
			for (int32 LocalY = 0; LocalY < Spec.ChunkCellDimensions.Y; ++LocalY)
			{
				for (int32 LocalX = 0; LocalX < Spec.ChunkCellDimensions.X; ++LocalX)
				{
					const FIntVector LocalCell(LocalX, LocalY, LocalZ);
					const int32 LocalIndex =
						GetLinearIndex(LocalCell, Spec.ChunkCellDimensions);
					const FIntVector GlobalCell(
						ChunkCoordinate.X * Spec.ChunkCellDimensions.X + LocalX,
						ChunkCoordinate.Y * Spec.ChunkCellDimensions.Y + LocalY,
						ChunkCoordinate.Z * Spec.ChunkCellDimensions.Z + LocalZ);
					const uint8 BaseMaterial =
						GenerateCellMaterial(Spec, GlobalCell);
					const uint8 StoredMaterial = Cells[LocalIndex];
					const bool bUnmodifiedSolid =
						BaseMaterial != static_cast<uint8>(ECellMaterial::Empty)
						&& StoredMaterial == BaseMaterial;
					const bool bMinedEmpty =
						BaseMaterial != static_cast<uint8>(ECellMaterial::Empty)
						&& StoredMaterial
							== static_cast<uint8>(ECellMaterial::Empty);
					const bool bBaseEmpty =
						BaseMaterial == static_cast<uint8>(ECellMaterial::Empty)
						&& StoredMaterial
							== static_cast<uint8>(ECellMaterial::Empty);
					if (!bUnmodifiedSolid && !bMinedEmpty && !bBaseEmpty)
					{
						return Fail(
							OutError,
							TEXT("checkpoint attempts material injection or solid creation"));
					}
					if (bMinedEmpty && OutRemovedCellCount)
					{
						++(*OutRemovedCellCount);
					}
				}
			}
		}
		OutError.Reset();
		return true;
	}

	bool HashBytes(const TArray<uint8>& Bytes, FString& OutSha256)
	{
		return ComputeCanonicalSha256(
			Bytes.IsEmpty() ? nullptr : Bytes.GetData(),
			Bytes.Num(),
			OutSha256);
	}

	bool HashChunkContent(
		const FVolumeSpec& Spec,
		const FIntVector& ChunkCoordinate,
		const TArray<uint8>& Cells,
		FString& OutSha256)
	{
		const FString Prefix = FString::Printf(
			TEXT("red.voxel-chunk-content.v1|spec=%s|chunk=%d,%d,%d|"),
			*Spec.CanonicalSpecSha256,
			ChunkCoordinate.X,
			ChunkCoordinate.Y,
			ChunkCoordinate.Z);
		const FTCHARToUTF8 Utf8(*Prefix);
		TArray<uint8> CanonicalBytes;
		CanonicalBytes.Reserve(Utf8.Length() + Cells.Num());
		CanonicalBytes.Append(
			reinterpret_cast<const uint8*>(Utf8.Get()),
			Utf8.Length());
		CanonicalBytes.Append(Cells);
		return HashBytes(CanonicalBytes, OutSha256);
	}

	bool HashCanonicalText(const FString& Text, FString& OutSha256)
	{
		const FTCHARToUTF8 Utf8(*Text);
		return ComputeCanonicalSha256(
			reinterpret_cast<const uint8*>(Utf8.Get()),
			Utf8.Length(),
			OutSha256);
	}

	void GetChunkCells(
		const FStoredVolume& Volume,
		const int32 ChunkIndex,
		TArray<uint8>& OutCells)
	{
		const int32 CellCount = GetChunkCellCount(Volume.Spec);
		const TArray<uint8>* Stored = Volume.NonEmptyChunks.Find(ChunkIndex);
		if (Stored)
		{
			OutCells = *Stored;
		}
		else
		{
			OutCells.SetNumZeroed(CellCount);
		}
	}

	void SetGeneratedOutputIdentity(
		const FVolumeSpec& Spec,
		const FIntVector& ChunkCoordinate,
		const uint64 ContentRevision,
		const FString& ContentSha256,
		const uint64 GenerationToken,
		FStoredChunkMetadata& Metadata)
	{
		Metadata.ContentRevision = ContentRevision;
		Metadata.ContentSha256 = ContentSha256;
		Metadata.GeneratedOutput.TargetStableId = Spec.StableId;
		Metadata.GeneratedOutput.ChunkCoordinate = ChunkCoordinate;
		Metadata.GeneratedOutput.ContentRevision = ContentRevision;
		Metadata.GeneratedOutput.ContentSha256 = ContentSha256;
		Metadata.GeneratedOutput.GenerationToken = GenerationToken;
		Metadata.GeneratedOutput.bPresentationReady = false;
		Metadata.GeneratedOutput.bCollisionReady = false;
		Metadata.GeneratedOutput.PresentationOutputSha256.Reset();
		Metadata.GeneratedOutput.CollisionOutputSha256.Reset();
		Metadata.PresentationBuildTicket = FGeneratedChunkBuildTicket();
		Metadata.CollisionBuildTicket = FGeneratedChunkBuildTicket();
		Metadata.bPresentationBuildPending = false;
		Metadata.bCollisionBuildPending = false;
	}

	bool EncodeCanonicalRle(
		const TArray<uint8>& Cells,
		TArray<uint8>& OutCompressed,
		FString& OutError)
	{
		OutCompressed.Reset();
		if (Cells.IsEmpty())
		{
			return Fail(OutError, TEXT("cannot encode an empty voxel chunk"));
		}
		int32 Cursor = 0;
		while (Cursor < Cells.Num())
		{
			const uint8 Value = Cells[Cursor];
			if (Value > static_cast<uint8>(ECellMaterial::Crystal))
			{
				return Fail(OutError, TEXT("voxel chunk contains an unknown material ordinal"));
			}
			int32 RunLength = 1;
			while (Cursor + RunLength < Cells.Num()
				&& Cells[Cursor + RunLength] == Value
				&& RunLength < TNumericLimits<uint16>::Max())
			{
				++RunLength;
			}
			OutCompressed.Add(static_cast<uint8>(RunLength & 0xff));
			OutCompressed.Add(static_cast<uint8>((RunLength >> 8) & 0xff));
			OutCompressed.Add(Value);
			Cursor += RunLength;
		}
		OutError.Reset();
		return true;
	}

	bool DecodeCanonicalRle(
		const TArray<uint8>& Compressed,
		const int32 ExpectedCellCount,
		const int32 MaxCompressedBytes,
		const int32 MaxUncompressedBytes,
		TArray<uint8>& OutCells,
		FString& OutError)
	{
		OutCells.Reset();
		if (ExpectedCellCount <= 0
			|| ExpectedCellCount > MaxUncompressedBytes
			|| Compressed.IsEmpty()
			|| Compressed.Num() > MaxCompressedBytes
			|| Compressed.Num() % 3 != 0)
		{
			return Fail(OutError, TEXT("RLE payload size or record alignment is invalid"));
		}
		OutCells.Reserve(ExpectedCellCount);
		for (int32 Offset = 0; Offset < Compressed.Num(); Offset += 3)
		{
			const int32 RunLength = static_cast<int32>(Compressed[Offset])
				| (static_cast<int32>(Compressed[Offset + 1]) << 8);
			const uint8 Value = Compressed[Offset + 2];
			if (RunLength <= 0
				|| Value > static_cast<uint8>(ECellMaterial::Crystal)
				|| RunLength > ExpectedCellCount - OutCells.Num())
			{
				return Fail(OutError, TEXT("RLE payload contains an invalid or overflowing run"));
			}
			OutCells.AddUninitialized(RunLength);
			FMemory::Memset(
				OutCells.GetData() + OutCells.Num() - RunLength,
				Value,
				RunLength);
		}
		if (OutCells.Num() != ExpectedCellCount)
		{
			return Fail(OutError, TEXT("RLE payload does not expand to the exact chunk size"));
		}

		TArray<uint8> CanonicalEncoding;
		FString EncodingError;
		if (!EncodeCanonicalRle(OutCells, CanonicalEncoding, EncodingError)
			|| CanonicalEncoding != Compressed)
		{
			return Fail(OutError, TEXT("RLE payload is not in canonical run form"));
		}
		OutError.Reset();
		return true;
	}

	bool ManifestRecordLess(
		const FManifestRecord& A,
		const FManifestRecord& B)
	{
		if (A.ChunkCoordinate.X != B.ChunkCoordinate.X)
		{
			return A.ChunkCoordinate.X < B.ChunkCoordinate.X;
		}
		if (A.ChunkCoordinate.Y != B.ChunkCoordinate.Y)
		{
			return A.ChunkCoordinate.Y < B.ChunkCoordinate.Y;
		}
		return A.ChunkCoordinate.Z < B.ChunkCoordinate.Z;
	}

	bool BuildManifestSha256(
		const FVolumeCheckpoint& Checkpoint,
		TArray<FManifestRecord> Records,
		FString& OutSha256)
	{
		Records.Sort(ManifestRecordLess);
		const FVolumeSpec& Spec = Checkpoint.VolumeSpec;
		const FAuthorityLimits& Limits = Checkpoint.AuthorityLimits;
		FString Canonical = FString::Printf(
			TEXT("red.voxel-checkpoint-manifest.v1")
			TEXT("|target=%s|spec=%s|material=%s|volume=%d,%d,%d")
			TEXT("|chunk=%d,%d,%d|cell-bits=%08X|seed=%u|generation=%u")
			TEXT("|through=%llu")
			TEXT("|limits=%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d")
			TEXT(",%08X,%08X,%08X,%08X,%08X,%08X,%08X,%08X,%08X"),
			*Checkpoint.TargetStableId.ToString().ToLower(),
			*Spec.CanonicalSpecSha256,
			*Spec.MaterialTableId.ToString().ToLower(),
			Spec.VolumeCellDimensions.X,
			Spec.VolumeCellDimensions.Y,
			Spec.VolumeCellDimensions.Z,
			Spec.ChunkCellDimensions.X,
			Spec.ChunkCellDimensions.Y,
			Spec.ChunkCellDimensions.Z,
			FloatBits(Spec.CellSizeCm),
			Spec.BaseSeed,
			Spec.GenerationVersion,
			static_cast<unsigned long long>(Checkpoint.ThroughRevision),
			Limits.MaxVolumeCellsPerAxis,
			Limits.MaxChunkCellsPerAxis,
			Limits.MaxEditedCellsPerRequest,
			Limits.MaxDirtyChunksPerEdit,
			Limits.MaxYieldEntriesPerEdit,
			Limits.MaxClustersPerEdit,
			Limits.MaxJournalOperationsPerCheckpoint,
			Limits.MaxRequestsPerSecond,
			Limits.MaxCheckpointChunks,
			Limits.MaxCompressedCheckpointBytesPerChunk,
			Limits.MaxUncompressedCheckpointBytesPerChunk,
			Limits.MaxCheckpointSetBytes,
			FloatBits(Limits.MinCellSizeCm),
			FloatBits(Limits.MaxCellSizeCm),
			FloatBits(Limits.MinBrushRadiusCm),
			FloatBits(Limits.MaxBrushRadiusCm),
			FloatBits(Limits.MaxMiningRangeCm),
			FloatBits(Limits.MaxSuctionRangeCm),
			FloatBits(Limits.MaxSuctionDurationSeconds),
			FloatBits(Limits.MaxReservationDurationSeconds),
			FloatBits(Limits.MaxCollectionArrivalDistanceCm));
		Canonical += FString::Printf(
			TEXT(",%08X"),
			FloatBits(Limits.MaxCollectionArrivalGraceSeconds));

		for (const FManifestRecord& Record : Records)
		{
			Canonical += FString::Printf(
				TEXT("|entry=%d,%d,%d:%d:%d:%s:%s"),
				Record.ChunkCoordinate.X,
				Record.ChunkCoordinate.Y,
				Record.ChunkCoordinate.Z,
				Record.UncompressedCellCount,
				Record.UncompressedByteCount,
				*Record.CodecId.ToString().ToLower(),
				*Record.PayloadSha256);
		}
		return HashCanonicalText(Canonical, OutSha256);
	}

	void SeedRejectedResult(
		const FValidatedEdit& Edit,
		FApplyResult& OutResult)
	{
		OutResult = FApplyResult();
		OutResult.TargetStableId = Edit.TargetStableId;
		OutResult.RequestSequence = Edit.RequestSequence;
		OutResult.PredictionToken = Edit.PredictionToken;
		OutResult.AuthorityGenerationToken = Edit.AuthorityGenerationToken;
		OutResult.PreviousRevision = Edit.ExpectedRevision;
		OutResult.AppliedRevision = Edit.ExpectedRevision;
	}

	bool ReturnValidatedRejection(
		const FStoredVolume& Volume,
		const FValidatedEdit& Edit,
		const EEditRejectReason RejectReason,
		FApplyResult& OutResult,
		FString& OutError)
	{
		SeedRejectedResult(Edit, OutResult);
		OutResult.bAccepted = false;
		OutResult.RejectReason = RejectReason;
		FString ValidationError;
		if (!ValidateApplyResult(
				OutResult,
				Edit,
				Volume.Spec,
				Volume.Limits,
				&ValidationError))
		{
			return Fail(
				OutError,
				FString::Printf(
					TEXT("internal rejected-result validation failed: %s"),
					*ValidationError));
		}
		OutError.Reset();
		return true;
	}

	bool BuildEditContentSha256(
		const FApplyResult& Result,
		const TArray<TPair<FIntVector, FString>>& ChunkHashes,
		FString& OutSha256)
	{
		FString Canonical = FString::Printf(
			TEXT("red.voxel-edit-result.v1|target=%s|revision=%llu|sequence=%llu|removed=%d"),
			*Result.TargetStableId.ToString().ToLower(),
			static_cast<unsigned long long>(Result.AppliedRevision),
			static_cast<unsigned long long>(Result.RequestSequence),
			Result.TotalRemovedCellCount);
		for (const FMaterialYield& Yield : Result.MaterialYields)
		{
			Canonical += FString::Printf(
				TEXT("|yield=%s:%d"),
				*Yield.MaterialId.ToString().ToLower(),
				Yield.RemovedCellCount);
		}
		for (const TPair<FIntVector, FString>& ChunkHash : ChunkHashes)
		{
			Canonical += FString::Printf(
				TEXT("|chunk=%d,%d,%d:%s"),
				ChunkHash.Key.X,
				ChunkHash.Key.Y,
				ChunkHash.Key.Z,
				*ChunkHash.Value);
		}
		return HashCanonicalText(Canonical, OutSha256);
	}

	bool VerificationsEquivalent(
		const FVolumeCheckpointVerification& A,
		const FVolumeCheckpointVerification& B)
	{
		if (A.RecomputedCanonicalManifestSha256
				!= B.RecomputedCanonicalManifestSha256
			|| A.Chunks.Num() != B.Chunks.Num())
		{
			return false;
		}
		for (const FChunkCheckpointVerification& Expected : A.Chunks)
		{
			const FChunkCheckpointVerification* Actual =
				B.Chunks.FindByPredicate(
					[&Expected](const FChunkCheckpointVerification& Candidate)
					{
						return Candidate.ChunkCoordinate
							== Expected.ChunkCoordinate;
					});
			if (!Actual
				|| Actual->ActualUncompressedByteCount
					!= Expected.ActualUncompressedByteCount
				|| Actual->RecomputedCanonicalPayloadSha256
					!= Expected.RecomputedCanonicalPayloadSha256)
			{
				return false;
			}
		}
		return true;
	}

	bool DecodeCheckpointToTemporaryState(
		const FVolumeCheckpoint& Checkpoint,
		const uint64 GenerationToken,
		FDecodedCheckpoint& OutDecoded,
		FString& OutError)
	{
		OutDecoded = FDecodedCheckpoint();
		const FVolumeSpec& Spec = Checkpoint.VolumeSpec;
		const FAuthorityLimits& Limits = Checkpoint.AuthorityLimits;
		const FIntVector ChunkCounts = GetChunkCounts(Spec);
		const int32 TotalChunkCount =
			ChunkCounts.X * ChunkCounts.Y * ChunkCounts.Z;
		const int32 ExpectedCellCount = GetChunkCellCount(Spec);
		OutDecoded.ChunkMetadata.SetNum(TotalChunkCount);

		for (const FChunkCheckpoint& Chunk : Checkpoint.Chunks)
		{
			if (!IsChunkCoordinateInBounds(
					Chunk.ChunkCoordinate,
					ChunkCounts))
			{
				return Fail(OutError, TEXT("checkpoint contains an out-of-bounds chunk"));
			}
			const int32 ChunkIndex =
				GetLinearIndex(Chunk.ChunkCoordinate, ChunkCounts);
			TArray<uint8> Cells;
			if (!DecodeCanonicalRle(
					Chunk.CompressedDensityAndMaterial,
					ExpectedCellCount,
					Limits.MaxCompressedCheckpointBytesPerChunk,
					Limits.MaxUncompressedCheckpointBytesPerChunk,
					Cells,
					OutError))
			{
				return false;
			}
			FString PayloadSha256;
			if (!HashBytes(Cells, PayloadSha256)
				|| PayloadSha256 != Chunk.CanonicalPayloadSha256)
			{
				return Fail(OutError, TEXT("checkpoint decoded payload hash mismatch"));
			}
			if (!ValidateChunkCellsAgainstBase(
					Spec,
					Chunk.ChunkCoordinate,
					Cells,
					nullptr,
					OutError))
			{
				return false;
			}
			FString ContentSha256;
			if (!HashChunkContent(
					Spec,
					Chunk.ChunkCoordinate,
					Cells,
					ContentSha256))
			{
				return Fail(
					OutError,
					TEXT("failed to hash restored chunk content identity"));
			}
			if (ContainsSolidCell(Cells))
			{
				OutDecoded.NonEmptyChunks.Add(ChunkIndex, MoveTemp(Cells));
			}
			SetGeneratedOutputIdentity(
				Spec,
				Chunk.ChunkCoordinate,
				Checkpoint.ThroughRevision,
				ContentSha256,
				GenerationToken,
				OutDecoded.ChunkMetadata[ChunkIndex]);
		}
		OutError.Reset();
		return true;
	}

	bool ValidateSubtractiveReplacement(
		const FStoredVolume& Existing,
		const FDecodedCheckpoint& Candidate,
		const uint64 CandidateRevision,
		FString& OutError)
	{
		const FIntVector ChunkCounts = GetChunkCounts(Existing.Spec);
		const int32 TotalChunkCount =
			ChunkCounts.X * ChunkCounts.Y * ChunkCounts.Z;
		const int32 ChunkCellCount = GetChunkCellCount(Existing.Spec);
		uint64 NewlyRemovedCellCount = 0;
		for (int32 ChunkIndex = 0; ChunkIndex < TotalChunkCount; ++ChunkIndex)
		{
			TArray<uint8> ExistingCells;
			GetChunkCells(Existing, ChunkIndex, ExistingCells);
			TArray<uint8> CandidateCells;
			const TArray<uint8>* StoredCandidate =
				Candidate.NonEmptyChunks.Find(ChunkIndex);
			if (StoredCandidate)
			{
				CandidateCells = *StoredCandidate;
			}
			else
			{
				CandidateCells.SetNumZeroed(ChunkCellCount);
			}
			for (int32 CellIndex = 0;
				CellIndex < ChunkCellCount;
				++CellIndex)
			{
				if (ExistingCells[CellIndex]
						== static_cast<uint8>(ECellMaterial::Empty)
					&& CandidateCells[CellIndex]
						!= static_cast<uint8>(ECellMaterial::Empty))
				{
					return Fail(
						OutError,
						TEXT("checkpoint would restore previously removed material"));
				}
				if (ExistingCells[CellIndex]
						!= static_cast<uint8>(ECellMaterial::Empty)
					&& CandidateCells[CellIndex]
						!= static_cast<uint8>(ECellMaterial::Empty)
					&& CandidateCells[CellIndex] != ExistingCells[CellIndex])
				{
					return Fail(
						OutError,
						TEXT("checkpoint would change an existing material ordinal"));
				}
				if (ExistingCells[CellIndex]
						!= static_cast<uint8>(ECellMaterial::Empty)
					&& CandidateCells[CellIndex]
						== static_cast<uint8>(ECellMaterial::Empty))
				{
					++NewlyRemovedCellCount;
				}
			}
		}
		const uint64 RevisionDelta =
			CandidateRevision - Existing.CurrentRevision;
		const uint64 MaxNewlyRemovedByRevision =
			RevisionDelta > TNumericLimits<uint64>::Max()
					/ static_cast<uint64>(
						Existing.Limits.MaxEditedCellsPerRequest)
				? TNumericLimits<uint64>::Max()
				: RevisionDelta
					* static_cast<uint64>(
						Existing.Limits.MaxEditedCellsPerRequest);
		if ((RevisionDelta == 0 && NewlyRemovedCellCount != 0)
			|| (RevisionDelta > 0
				&& (NewlyRemovedCellCount < RevisionDelta
					|| NewlyRemovedCellCount
						> MaxNewlyRemovedByRevision)))
		{
			return Fail(
				OutError,
				TEXT("checkpoint revision delta does not match subtractive cell changes"));
		}
		OutError.Reset();
		return true;
	}

	bool IsSingleGeneratedOutputRole(
		const EGeneratedOutputRequirement OutputRole)
	{
		return OutputRole == EGeneratedOutputRequirement::Presentation
			|| OutputRole == EGeneratedOutputRequirement::Collision;
	}

	bool AreChunkRevisionsEquivalent(
		const FChunkRevision& A,
		const FChunkRevision& B)
	{
		return A.TargetStableId == B.TargetStableId
			&& A.ChunkCoordinate == B.ChunkCoordinate
			&& A.ContentRevision == B.ContentRevision
			&& A.ContentSha256 == B.ContentSha256
			&& A.GenerationToken == B.GenerationToken;
	}

	bool AreBuildTicketsEquivalent(
		const FGeneratedChunkBuildTicket& A,
		const FGeneratedChunkBuildTicket& B)
	{
		return AreChunkRevisionsEquivalent(
				A.SourceRevision,
				B.SourceRevision)
			&& A.VolumeSpecSha256 == B.VolumeSpecSha256
			&& A.OutputRole == B.OutputRole
			&& A.BuildProfileId == B.BuildProfileId
			&& A.BuildProfileVersion == B.BuildProfileVersion
			&& A.BackendInstanceId == B.BackendInstanceId
			&& A.BuildRequestToken == B.BuildRequestToken;
	}

	bool AreCheckpointPersistenceTicketsEquivalent(
		const FCheckpointPersistenceTicket& A,
		const FCheckpointPersistenceTicket& B)
	{
		return A.TargetStableId == B.TargetStableId
			&& A.VolumeSpecSha256 == B.VolumeSpecSha256
			&& A.bExpectedAcknowledgedBase
				== B.bExpectedAcknowledgedBase
			&& A.ExpectedJournalBaseRevision
				== B.ExpectedJournalBaseRevision
			&& A.ExpectedBaseCheckpointManifestSha256
				== B.ExpectedBaseCheckpointManifestSha256
			&& A.ExpectedBaseJournalTailSha256
				== B.ExpectedBaseJournalTailSha256
			&& A.CheckpointThroughRevision
				== B.CheckpointThroughRevision
			&& A.CheckpointManifestSha256
				== B.CheckpointManifestSha256
			&& A.CheckpointJournalTailSha256
				== B.CheckpointJournalTailSha256
			&& A.AuthorityGenerationToken
				== B.AuthorityGenerationToken
			&& A.BackendInstanceId == B.BackendInstanceId
			&& A.PersistenceRequestToken
				== B.PersistenceRequestToken;
	}

	bool ValidateStoredJournalState(
		const FStoredVolume& Volume,
		FString& OutFinalTailSha256,
		FString& OutError)
	{
		OutFinalTailSha256.Reset();
		if (Volume.JournalBaseRevision > Volume.CurrentRevision)
		{
			return Fail(
				OutError,
				TEXT("journal base revision exceeds live authority revision"));
		}
		if (Volume.bHasAcknowledgedCheckpoint)
		{
			if (!IsCanonicalSha256(
					Volume.BaseCheckpointManifestSha256)
				|| (!Volume.BaseJournalTailSha256.IsEmpty()
					&& !IsCanonicalSha256(
						Volume.BaseJournalTailSha256)))
			{
				return Fail(
					OutError,
					TEXT("acknowledged journal base identity is malformed"));
			}
		}
		else if (!Volume.BaseCheckpointManifestSha256.IsEmpty()
			|| !Volume.BaseJournalTailSha256.IsEmpty())
		{
			return Fail(
				OutError,
				TEXT("unacknowledged journal base retains durable identity"));
		}

		const uint64 RevisionDelta =
			Volume.CurrentRevision - Volume.JournalBaseRevision;
		if (RevisionDelta
				> static_cast<uint64>(
					Volume.Limits.MaxJournalOperationsPerCheckpoint)
			|| Volume.Journal.Num()
				!= static_cast<int32>(RevisionDelta))
		{
			return Fail(
				OutError,
				TEXT("live journal is not the exact bounded suffix after its base"));
		}

		uint64 ExpectedPreviousRevision =
			Volume.JournalBaseRevision;
		FString ExpectedPreviousTail =
			Volume.BaseJournalTailSha256;
		FString ValidationError;
		TSet<FGuid> SeenOperationIds;
		TSet<FString> SeenCollectorSequences;
		for (const FEditOperation& Operation : Volume.Journal)
		{
			if (!ValidateEditOperation(
					Operation,
					Volume.Limits,
					&ValidationError))
			{
				return Fail(
					OutError,
					FString::Printf(
						TEXT("live journal contains a malformed operation: %s"),
						*ValidationError));
			}
			const FString CollectorSequenceKey =
				FString::Printf(
					TEXT("%s:%llu"),
					*Operation.CollectorStableId
						.ToString()
						.ToLower(),
					static_cast<unsigned long long>(
						Operation.RequestSequence));
			if (SeenOperationIds.Contains(Operation.OperationId)
				|| SeenCollectorSequences.Contains(
					CollectorSequenceKey))
			{
				return Fail(
					OutError,
					TEXT("live journal repeats an operation or collector sequence identity"));
			}
			SeenOperationIds.Add(Operation.OperationId);
			SeenCollectorSequences.Add(
				CollectorSequenceKey);
			if (Operation.TargetStableId
					!= Volume.Spec.StableId
				|| Operation.VolumeSpecSha256
					!= Volume.Spec.CanonicalSpecSha256
				|| Operation.PreviousRevision
					!= ExpectedPreviousRevision
				|| Operation.PreviousOperationSha256
					!= ExpectedPreviousTail)
			{
				return Fail(
					OutError,
					TEXT("live journal contains a foreign, gapped, or unchained operation"));
			}
			ExpectedPreviousRevision = Operation.Revision;
			ExpectedPreviousTail =
				Operation.CanonicalOperationSha256;
		}
		if (ExpectedPreviousRevision != Volume.CurrentRevision)
		{
			return Fail(
				OutError,
				TEXT("live journal tail revision does not match authority revision"));
		}
		OutFinalTailSha256 = MoveTemp(ExpectedPreviousTail);
		OutError.Reset();
		return true;
	}
}

class FRedInMemorySparseVoxelBackend::FImpl
{
public:
	TMap<FName, FStoredVolume> Volumes;
	/** Stable-ID tombstones prevent stale async work from matching a recreated volume. */
	TMap<FName, uint64> LastIssuedGenerationTokens;
	/** Process-local epoch prevents callbacks crossing backend object lifetimes. */
	FGuid BackendInstanceId = FGuid::NewGuid();
	/** Monotonic attempt identity shared across roles and volumes in this backend. */
	uint64 LastIssuedBuildRequestToken = 0;
	/** Monotonic process-local identity shared across persistence requests. */
	uint64 LastIssuedPersistenceRequestToken = 0;
};

FRedInMemorySparseVoxelBackend::FRedInMemorySparseVoxelBackend()
	: Impl(MakeUnique<FImpl>())
{
}

FRedInMemorySparseVoxelBackend::~FRedInMemorySparseVoxelBackend() = default;

bool FRedInMemorySparseVoxelBackend::InitializeVolume(
	const FVolumeSpec& Spec,
	const FAuthorityLimits& Limits,
	FString& OutError)
{
	if (!RequireGameThread(OutError))
	{
		return false;
	}
	if (Impl->Volumes.Contains(Spec.StableId))
	{
		return Fail(OutError, TEXT("a volume with this stable ID already exists"));
	}
	if (!ValidateSupportedSpec(Spec, Limits, OutError))
	{
		return false;
	}
	const uint64 LastIssuedGenerationToken =
		Impl->LastIssuedGenerationTokens.FindRef(Spec.StableId);
	if (LastIssuedGenerationToken
		>= TNumericLimits<uint64>::Max() - 1)
	{
		return Fail(
			OutError,
			TEXT("stable volume generation token cannot safely advance"));
	}
	const uint64 NewGenerationToken =
		LastIssuedGenerationToken + 1;

	FStoredVolume Candidate;
	Candidate.Spec = Spec;
	Candidate.Limits = Limits;
	Candidate.CurrentRevision = 0;
	Candidate.AuthorityGenerationToken = NewGenerationToken;
	Candidate.MinimumAcceptedBuildGenerationToken =
		NewGenerationToken;
	Candidate.JournalBaseRevision = 0;
	Candidate.bHasAcknowledgedCheckpoint = false;

	const FIntVector ChunkCounts = GetChunkCounts(Spec);
	const int32 TotalChunkCount =
		ChunkCounts.X * ChunkCounts.Y * ChunkCounts.Z;
	const int32 ChunkCellCount = GetChunkCellCount(Spec);
	Candidate.ChunkMetadata.SetNum(TotalChunkCount);

	for (int32 ChunkIndex = 0; ChunkIndex < TotalChunkCount; ++ChunkIndex)
	{
		const FIntVector ChunkCoordinate =
			GetCoordinateFromLinearIndex(ChunkIndex, ChunkCounts);
		TArray<uint8> Cells;
		Cells.SetNumUninitialized(ChunkCellCount);
		for (int32 LocalZ = 0; LocalZ < Spec.ChunkCellDimensions.Z; ++LocalZ)
		{
			for (int32 LocalY = 0; LocalY < Spec.ChunkCellDimensions.Y; ++LocalY)
			{
				for (int32 LocalX = 0; LocalX < Spec.ChunkCellDimensions.X; ++LocalX)
				{
					const FIntVector LocalCell(LocalX, LocalY, LocalZ);
					const FIntVector GlobalCell(
						ChunkCoordinate.X * Spec.ChunkCellDimensions.X + LocalX,
						ChunkCoordinate.Y * Spec.ChunkCellDimensions.Y + LocalY,
						ChunkCoordinate.Z * Spec.ChunkCellDimensions.Z + LocalZ);
					Cells[GetLinearIndex(
						LocalCell,
						Spec.ChunkCellDimensions)] =
							GenerateCellMaterial(Spec, GlobalCell);
				}
			}
		}

		FString ContentSha256;
		if (!HashChunkContent(
				Spec,
				ChunkCoordinate,
				Cells,
				ContentSha256))
		{
			return Fail(OutError, TEXT("failed to hash deterministic base chunk"));
		}
		if (ContainsSolidCell(Cells))
		{
			Candidate.NonEmptyChunks.Add(ChunkIndex, MoveTemp(Cells));
		}
		SetGeneratedOutputIdentity(
			Spec,
			ChunkCoordinate,
			0,
			ContentSha256,
			NewGenerationToken,
			Candidate.ChunkMetadata[ChunkIndex]);
	}

	Impl->Volumes.Add(Spec.StableId, MoveTemp(Candidate));
	Impl->LastIssuedGenerationTokens.Add(
		Spec.StableId,
		NewGenerationToken);
	OutError.Reset();
	return true;
}

bool FRedInMemorySparseVoxelBackend::HasVolume(const FName StableId) const
{
	return IsInGameThread() && Impl->Volumes.Contains(StableId);
}

uint64 FRedInMemorySparseVoxelBackend::GetCurrentRevision(
	const FName StableId) const
{
	if (!IsInGameThread())
	{
		return 0;
	}
	const FStoredVolume* Volume = Impl->Volumes.Find(StableId);
	return Volume ? Volume->CurrentRevision : 0;
}

uint64 FRedInMemorySparseVoxelBackend::GetAuthorityGenerationToken(
	const FName StableId) const
{
	if (!IsInGameThread())
	{
		return 0;
	}
	const FStoredVolume* Volume = Impl->Volumes.Find(StableId);
	return Volume ? Volume->AuthorityGenerationToken : 0;
}

bool FRedInMemorySparseVoxelBackend::ApplyValidatedEdit(
	const FValidatedEdit& Edit,
	FApplyResult& OutResult,
	FString& OutError)
{
	SeedRejectedResult(Edit, OutResult);
	if (!RequireGameThread(OutError))
	{
		return false;
	}
	FStoredVolume* Volume = Impl->Volumes.Find(Edit.TargetStableId);
	if (!Volume)
	{
		OutResult.RejectReason = EEditRejectReason::InvalidTarget;
		return Fail(OutError, TEXT("validated edit target does not exist"));
	}

	FString ValidationError;
	if (!ValidateServerEdit(Edit, Volume->Limits, &ValidationError))
	{
		OutResult.RejectReason = EEditRejectReason::InvalidBrush;
		return Fail(
			OutError,
			FString::Printf(TEXT("invalid server edit: %s"), *ValidationError));
	}
	FString CurrentJournalTailSha256;
	if (!ValidateStoredJournalState(
			*Volume,
			CurrentJournalTailSha256,
			OutError))
	{
		return false;
	}
	if (Edit.AuthorityGenerationToken != Volume->AuthorityGenerationToken)
	{
		return ReturnValidatedRejection(
			*Volume,
			Edit,
			EEditRejectReason::CheckpointMismatch,
			OutResult,
			OutError);
	}
	if (Edit.ExpectedRevision != Volume->CurrentRevision)
	{
		return ReturnValidatedRejection(
			*Volume,
			Edit,
			EEditRejectReason::StaleRevision,
			OutResult,
			OutError);
	}
	if (Volume->Journal.ContainsByPredicate(
			[&Edit](const FEditOperation& Operation)
			{
				return Operation.CollectorStableId
						== Edit.CollectorStableId
					&& Operation.RequestSequence
						== Edit.RequestSequence;
			}))
	{
		return ReturnValidatedRejection(
			*Volume,
			Edit,
			EEditRejectReason::DuplicateRequest,
			OutResult,
			OutError);
	}
	if (Volume->CurrentRevision == TNumericLimits<uint64>::Max())
	{
		return ReturnValidatedRejection(
			*Volume,
			Edit,
			EEditRejectReason::RevisionOverflow,
			OutResult,
			OutError);
	}
	const FGuid CandidateOperationId = FGuid::NewGuid();
	if (!CandidateOperationId.IsValid()
		|| Volume->Journal.ContainsByPredicate(
			[&CandidateOperationId](
				const FEditOperation& Operation)
			{
				return Operation.OperationId
					== CandidateOperationId;
			}))
	{
		return Fail(
			OutError,
			TEXT("failed to allocate a unique edit operation identity"));
	}
	if (Volume->Journal.Num()
		>= Volume->Limits.MaxJournalOperationsPerCheckpoint)
	{
		return ReturnValidatedRejection(
			*Volume,
			Edit,
			EEditRejectReason::JournalCapacityReached,
			OutResult,
			OutError);
	}

	const FVolumeSpec& Spec = Volume->Spec;
	const float HalfX = Spec.VolumeCellDimensions.X * 0.5f;
	const float HalfY = Spec.VolumeCellDimensions.Y * 0.5f;
	const float HalfZ = Spec.VolumeCellDimensions.Z * 0.5f;
	const float Radius = Edit.BrushRadiusCm;
	const float CellSize = Spec.CellSizeCm;
	const FIntVector MinCell(
		FMath::Clamp(
			FMath::FloorToInt(
				(Edit.LocalBrushCenter.X - Radius) / CellSize + HalfX - 0.5f),
			0,
			Spec.VolumeCellDimensions.X - 1),
		FMath::Clamp(
			FMath::FloorToInt(
				(Edit.LocalBrushCenter.Y - Radius) / CellSize + HalfY - 0.5f),
			0,
			Spec.VolumeCellDimensions.Y - 1),
		FMath::Clamp(
			FMath::FloorToInt(
				(Edit.LocalBrushCenter.Z - Radius) / CellSize + HalfZ - 0.5f),
			0,
			Spec.VolumeCellDimensions.Z - 1));
	const FIntVector MaxCell(
		FMath::Clamp(
			FMath::CeilToInt(
				(Edit.LocalBrushCenter.X + Radius) / CellSize + HalfX - 0.5f),
			0,
			Spec.VolumeCellDimensions.X - 1),
		FMath::Clamp(
			FMath::CeilToInt(
				(Edit.LocalBrushCenter.Y + Radius) / CellSize + HalfY - 0.5f),
			0,
			Spec.VolumeCellDimensions.Y - 1),
		FMath::Clamp(
			FMath::CeilToInt(
				(Edit.LocalBrushCenter.Z + Radius) / CellSize + HalfZ - 0.5f),
			0,
			Spec.VolumeCellDimensions.Z - 1));

	TMap<int32, TArray<uint8>> CandidateChunks;
	TSet<int32> DirtyChunkIndices;
	int32 MaterialCounts[4] = {0, 0, 0, 0};
	int32 RemovedCellCount = 0;
	const double RadiusSquared =
		static_cast<double>(Radius) * static_cast<double>(Radius);
	const FIntVector ChunkCounts = GetChunkCounts(Spec);

	for (int32 Z = MinCell.Z; Z <= MaxCell.Z; ++Z)
	{
		for (int32 Y = MinCell.Y; Y <= MaxCell.Y; ++Y)
		{
			for (int32 X = MinCell.X; X <= MaxCell.X; ++X)
			{
				const double CenterX =
					(static_cast<double>(X) + 0.5 - HalfX) * CellSize;
				const double CenterY =
					(static_cast<double>(Y) + 0.5 - HalfY) * CellSize;
				const double CenterZ =
					(static_cast<double>(Z) + 0.5 - HalfZ) * CellSize;
				const double Dx = CenterX - Edit.LocalBrushCenter.X;
				const double Dy = CenterY - Edit.LocalBrushCenter.Y;
				const double Dz = CenterZ - Edit.LocalBrushCenter.Z;
				if (Dx * Dx + Dy * Dy + Dz * Dz > RadiusSquared)
				{
					continue;
				}

				const FIntVector ChunkCoordinate(
					X / Spec.ChunkCellDimensions.X,
					Y / Spec.ChunkCellDimensions.Y,
					Z / Spec.ChunkCellDimensions.Z);
				const int32 ChunkIndex =
					GetLinearIndex(ChunkCoordinate, ChunkCounts);
				TArray<uint8>* CandidateCells =
					CandidateChunks.Find(ChunkIndex);
				if (!CandidateCells)
				{
					TArray<uint8> InitialCells;
					GetChunkCells(*Volume, ChunkIndex, InitialCells);
					CandidateCells = &CandidateChunks.Add(
						ChunkIndex,
						MoveTemp(InitialCells));
				}
				const FIntVector LocalCell(
					X % Spec.ChunkCellDimensions.X,
					Y % Spec.ChunkCellDimensions.Y,
					Z % Spec.ChunkCellDimensions.Z);
				const int32 LocalIndex =
					GetLinearIndex(LocalCell, Spec.ChunkCellDimensions);
				const uint8 PriorMaterial = (*CandidateCells)[LocalIndex];
				if (PriorMaterial == static_cast<uint8>(ECellMaterial::Empty))
				{
					continue;
				}
				if (PriorMaterial > static_cast<uint8>(ECellMaterial::Crystal))
				{
					return Fail(
						OutError,
						TEXT("live voxel state contains an unknown material ordinal"));
				}
				(*CandidateCells)[LocalIndex] =
					static_cast<uint8>(ECellMaterial::Empty);
				++MaterialCounts[PriorMaterial];
				++RemovedCellCount;
				DirtyChunkIndices.Add(ChunkIndex);
				if (RemovedCellCount
						> Volume->Limits.MaxEditedCellsPerRequest
					|| DirtyChunkIndices.Num()
						> Volume->Limits.MaxDirtyChunksPerEdit)
				{
					return ReturnValidatedRejection(
						*Volume,
						Edit,
						EEditRejectReason::InvalidBrush,
						OutResult,
						OutError);
				}
			}
		}
	}

	if (RemovedCellCount == 0)
	{
		return ReturnValidatedRejection(
			*Volume,
			Edit,
			EEditRejectReason::ZeroRemovedVolume,
			OutResult,
			OutError);
	}

	TArray<int32> SortedDirtyChunkIndices = DirtyChunkIndices.Array();
	SortedDirtyChunkIndices.Sort(
		[&ChunkCounts](const int32 A, const int32 B)
		{
			FManifestRecord Left;
			Left.ChunkCoordinate =
				GetCoordinateFromLinearIndex(A, ChunkCounts);
			FManifestRecord Right;
			Right.ChunkCoordinate =
				GetCoordinateFromLinearIndex(B, ChunkCounts);
			return ManifestRecordLess(Left, Right);
		});
	const uint64 AppliedRevision = Volume->CurrentRevision + 1;
	OutResult = FApplyResult();
	OutResult.TargetStableId = Edit.TargetStableId;
	OutResult.RequestSequence = Edit.RequestSequence;
	OutResult.PredictionToken = Edit.PredictionToken;
	OutResult.AuthorityGenerationToken =
		Volume->AuthorityGenerationToken;
	OutResult.bAccepted = true;
	OutResult.RejectReason = EEditRejectReason::None;
	OutResult.PreviousRevision = Volume->CurrentRevision;
	OutResult.AppliedRevision = AppliedRevision;
	OutResult.TotalRemovedCellCount = RemovedCellCount;

	const double CellVolumeCm3 = static_cast<double>(CellSize)
		* CellSize * CellSize;
	for (const uint8 Material : {
			static_cast<uint8>(ECellMaterial::Stone),
			static_cast<uint8>(ECellMaterial::Iron),
			static_cast<uint8>(ECellMaterial::Crystal)})
	{
		if (MaterialCounts[Material] <= 0)
		{
			continue;
		}
		FMaterialYield Yield;
		Yield.MaterialId = GetMaterialId(Material);
		Yield.RemovedCellCount = MaterialCounts[Material];
		Yield.RemovedVolumeCm3 =
			MaterialCounts[Material] * CellVolumeCm3;
		OutResult.MaterialYields.Add(Yield);
	}

	TArray<TPair<FIntVector, FString>> CandidateChunkHashes;
	for (const int32 ChunkIndex : SortedDirtyChunkIndices)
	{
		const FIntVector ChunkCoordinate =
			GetCoordinateFromLinearIndex(ChunkIndex, ChunkCounts);
		OutResult.DirtyChunkCoordinates.Add(ChunkCoordinate);
		FString ContentSha256;
		if (!HashChunkContent(
				Spec,
				ChunkCoordinate,
				CandidateChunks.FindChecked(ChunkIndex),
				ContentSha256))
		{
			return Fail(OutError, TEXT("failed to hash candidate voxel chunk"));
		}
		CandidateChunkHashes.Emplace(ChunkCoordinate, MoveTemp(ContentSha256));
	}

	if (OutResult.MaterialYields.Num()
			> Volume->Limits.MaxYieldEntriesPerEdit)
	{
		return ReturnValidatedRejection(
			*Volume,
			Edit,
			EEditRejectReason::InvalidBrush,
			OutResult,
			OutError);
	}
	if (!ValidateApplyResult(
			OutResult,
			Edit,
			Volume->Spec,
			Volume->Limits,
			&ValidationError))
	{
		return Fail(
			OutError,
			FString::Printf(
				TEXT("candidate edit result failed authority validation: %s"),
				*ValidationError));
	}

	FEditOperation AcceptedOperation;
	AcceptedOperation.TargetStableId = Edit.TargetStableId;
	AcceptedOperation.VolumeSpecSha256 =
		Volume->Spec.CanonicalSpecSha256;
	AcceptedOperation.OperationId = CandidateOperationId;
	AcceptedOperation.CollectorStableId =
		Edit.CollectorStableId;
	AcceptedOperation.MiningToolStableId =
		Edit.MiningToolStableId;
	AcceptedOperation.EditAlgorithmVersion =
		PrototypeEditAlgorithmVersion;
	AcceptedOperation.PreviousRevision =
		OutResult.PreviousRevision;
	AcceptedOperation.Revision = AppliedRevision;
	AcceptedOperation.RequestSequence = Edit.RequestSequence;
	AcceptedOperation.PredictionToken = Edit.PredictionToken;
	AcceptedOperation.LocalBrushCenter = Edit.LocalBrushCenter;
	AcceptedOperation.LocalSurfaceNormal =
		Edit.LocalSurfaceNormal;
	AcceptedOperation.BrushRadiusCm = Edit.BrushRadiusCm;
	AcceptedOperation.RemovedCellCount = RemovedCellCount;
	AcceptedOperation.PreviousOperationSha256 =
		CurrentJournalTailSha256;
	if (!BuildEditContentSha256(
			OutResult,
			CandidateChunkHashes,
			AcceptedOperation.ResultContentSha256))
	{
		return Fail(OutError, TEXT("failed to hash candidate edit journal entry"));
	}
	if (!ComputeCanonicalEditOperationSha256(
			AcceptedOperation,
			AcceptedOperation.CanonicalOperationSha256)
		|| !ValidateEditOperation(
			AcceptedOperation,
			Volume->Limits,
			&ValidationError))
	{
		return Fail(
			OutError,
			FString::Printf(
				TEXT("candidate edit operation failed canonical validation: %s"),
				*ValidationError));
	}

	// Commit begins only after the complete result, chunk hashes, and journal entry validate.
	for (int32 DirtyIndex = 0;
		DirtyIndex < SortedDirtyChunkIndices.Num();
		++DirtyIndex)
	{
		const int32 ChunkIndex = SortedDirtyChunkIndices[DirtyIndex];
		TArray<uint8> Cells = MoveTemp(CandidateChunks.FindChecked(ChunkIndex));
		if (ContainsSolidCell(Cells))
		{
			Volume->NonEmptyChunks.Add(ChunkIndex, MoveTemp(Cells));
		}
		else
		{
			Volume->NonEmptyChunks.Remove(ChunkIndex);
		}
		SetGeneratedOutputIdentity(
			Spec,
			CandidateChunkHashes[DirtyIndex].Key,
			AppliedRevision,
			CandidateChunkHashes[DirtyIndex].Value,
			Volume->AuthorityGenerationToken,
			Volume->ChunkMetadata[ChunkIndex]);
	}
	Volume->CurrentRevision = AppliedRevision;
	Volume->Journal.Add(MoveTemp(AcceptedOperation));
	OutError.Reset();
	return true;
}

bool FRedInMemorySparseVoxelBackend::ReadChunkRevision(
	const FName StableId,
	const FIntVector& ChunkCoordinate,
	FChunkRevision& OutRevision,
	FString& OutError) const
{
	OutRevision = FChunkRevision();
	if (!RequireGameThread(OutError))
	{
		return false;
	}
	const FStoredVolume* Volume = Impl->Volumes.Find(StableId);
	if (!Volume)
	{
		return Fail(OutError, TEXT("volume does not exist"));
	}
	const FIntVector ChunkCounts = GetChunkCounts(Volume->Spec);
	if (!IsChunkCoordinateInBounds(ChunkCoordinate, ChunkCounts))
	{
		return Fail(OutError, TEXT("chunk coordinate is out of bounds"));
	}
	const int32 ChunkIndex =
		GetLinearIndex(ChunkCoordinate, ChunkCounts);
	const FStoredChunkMetadata& Metadata =
		Volume->ChunkMetadata[ChunkIndex];
	OutRevision.TargetStableId = StableId;
	OutRevision.ChunkCoordinate = ChunkCoordinate;
	OutRevision.ContentRevision = Metadata.ContentRevision;
	OutRevision.ContentSha256 = Metadata.ContentSha256;
	OutRevision.GenerationToken = Volume->AuthorityGenerationToken;
	OutError.Reset();
	return true;
}

bool FRedInMemorySparseVoxelBackend::CaptureCheckpointSet(
	const FName StableId,
	FVolumeCheckpoint& OutCheckpoint,
	FString& OutError) const
{
	OutCheckpoint = FVolumeCheckpoint();
	if (!RequireGameThread(OutError))
	{
		return false;
	}
	const FStoredVolume* Volume = Impl->Volumes.Find(StableId);
	if (!Volume)
	{
		return Fail(OutError, TEXT("volume does not exist"));
	}

	FVolumeCheckpoint Candidate;
	Candidate.TargetStableId = StableId;
	Candidate.VolumeSpec = Volume->Spec;
	Candidate.AuthorityLimits = Volume->Limits;
	Candidate.GenerationVersion = Volume->Spec.GenerationVersion;
	Candidate.BaseSeed = Volume->Spec.BaseSeed;
	Candidate.MaterialTableId = Volume->Spec.MaterialTableId;
	Candidate.VolumeSpecSha256 = Volume->Spec.CanonicalSpecSha256;
	Candidate.ThroughRevision = Volume->CurrentRevision;

	const FIntVector ChunkCounts = GetChunkCounts(Volume->Spec);
	const int32 TotalChunkCount =
		ChunkCounts.X * ChunkCounts.Y * ChunkCounts.Z;
	const int32 ChunkCellCount = GetChunkCellCount(Volume->Spec);
	TArray<FManifestRecord> ManifestRecords;
	ManifestRecords.Reserve(TotalChunkCount);
	Candidate.Chunks.Reserve(TotalChunkCount);
	int64 TotalStoredBytes = 0;

	for (int32 ChunkIndex = 0; ChunkIndex < TotalChunkCount; ++ChunkIndex)
	{
		const FIntVector ChunkCoordinate =
			GetCoordinateFromLinearIndex(ChunkIndex, ChunkCounts);
		TArray<uint8> Cells;
		GetChunkCells(*Volume, ChunkIndex, Cells);
		FChunkCheckpoint Chunk;
		Chunk.TargetStableId = StableId;
		Chunk.ChunkCoordinate = ChunkCoordinate;
		Chunk.GenerationVersion = Volume->Spec.GenerationVersion;
		Chunk.ThroughRevision = Volume->CurrentRevision;
		Chunk.BaseSeed = Volume->Spec.BaseSeed;
		Chunk.MaterialTableId = Volume->Spec.MaterialTableId;
		Chunk.VolumeSpecSha256 = Volume->Spec.CanonicalSpecSha256;
		Chunk.UncompressedCellCount = ChunkCellCount;
		Chunk.UncompressedByteCount = Cells.Num();
		Chunk.CodecId = RleCodecId;
		if (!EncodeCanonicalRle(
				Cells,
				Chunk.CompressedDensityAndMaterial,
				OutError)
			|| !HashBytes(Cells, Chunk.CanonicalPayloadSha256))
		{
			return false;
		}
		if (Chunk.CompressedDensityAndMaterial.Num()
				> Volume->Limits.MaxCompressedCheckpointBytesPerChunk
			|| Chunk.UncompressedByteCount
				> Volume->Limits.MaxUncompressedCheckpointBytesPerChunk)
		{
			return Fail(OutError, TEXT("captured checkpoint chunk exceeds policy limits"));
		}
		TotalStoredBytes += Chunk.CompressedDensityAndMaterial.Num();
		TotalStoredBytes += Chunk.UncompressedByteCount;
		if (TotalStoredBytes > Volume->Limits.MaxCheckpointSetBytes)
		{
			return Fail(OutError, TEXT("captured checkpoint set exceeds policy limits"));
		}

		FManifestRecord Record;
		Record.ChunkCoordinate = ChunkCoordinate;
		Record.UncompressedCellCount = Chunk.UncompressedCellCount;
		Record.UncompressedByteCount = Chunk.UncompressedByteCount;
		Record.CodecId = Chunk.CodecId;
		Record.PayloadSha256 = Chunk.CanonicalPayloadSha256;
		ManifestRecords.Add(MoveTemp(Record));
		Candidate.Chunks.Add(MoveTemp(Chunk));
	}
	if (!BuildManifestSha256(
			Candidate,
			MoveTemp(ManifestRecords),
			Candidate.CanonicalManifestSha256))
	{
		return Fail(OutError, TEXT("failed to hash checkpoint manifest"));
	}

	FVolumeCheckpointVerification Verification;
	if (!InspectCheckpointSet(Candidate, Verification, OutError))
	{
		return false;
	}
	OutCheckpoint = MoveTemp(Candidate);
	OutError.Reset();
	return true;
}

bool FRedInMemorySparseVoxelBackend::ExportOperationJournal(
	const FName StableId,
	FEditJournalExport& OutExport,
	FString& OutError) const
{
	OutExport = FEditJournalExport();
	if (!RequireGameThread(OutError))
	{
		return false;
	}
	const FStoredVolume* Volume = Impl->Volumes.Find(StableId);
	if (!Volume)
	{
		return Fail(OutError, TEXT("volume does not exist"));
	}
	if (!Volume->bHasAcknowledgedCheckpoint)
	{
		return Fail(
			OutError,
			TEXT("journal export requires an explicitly acknowledged checkpoint base"));
	}

	FString FinalJournalTailSha256;
	if (!ValidateStoredJournalState(
			*Volume,
			FinalJournalTailSha256,
			OutError))
	{
		return false;
	}

	FEditJournalExport Candidate;
	Candidate.TargetStableId = StableId;
	Candidate.VolumeSpecSha256 =
		Volume->Spec.CanonicalSpecSha256;
	Candidate.BaseCheckpointRevision =
		Volume->JournalBaseRevision;
	Candidate.BaseCheckpointManifestSha256 =
		Volume->BaseCheckpointManifestSha256;
	Candidate.BaseJournalTailSha256 =
		Volume->BaseJournalTailSha256;
	Candidate.ThroughRevision = Volume->CurrentRevision;
	Candidate.Operations = Volume->Journal;
	Candidate.FinalJournalTailSha256 =
		MoveTemp(FinalJournalTailSha256);
	if (!ComputeCanonicalEditJournalSha256(
			Candidate,
			Candidate.CanonicalManifestSha256))
	{
		return Fail(
			OutError,
			TEXT("failed to hash canonical journal export"));
	}
	FString ValidationError;
	if (!ValidateEditJournalExport(
			Candidate,
			Volume->Limits,
			&ValidationError))
	{
		return Fail(
			OutError,
			FString::Printf(
				TEXT("candidate journal export failed validation: %s"),
				*ValidationError));
	}

	OutExport = MoveTemp(Candidate);
	OutError.Reset();
	return true;
}

bool FRedInMemorySparseVoxelBackend::CaptureCheckpointForPersistence(
	const FName StableId,
	FCheckpointPersistenceRequest& OutRequest,
	FString& OutError)
{
	OutRequest = FCheckpointPersistenceRequest();
	if (!RequireGameThread(OutError))
	{
		return false;
	}
	FStoredVolume* Volume = Impl->Volumes.Find(StableId);
	if (!Volume)
	{
		return Fail(OutError, TEXT("volume does not exist"));
	}

	FString FinalJournalTailSha256;
	if (!ValidateStoredJournalState(
			*Volume,
			FinalJournalTailSha256,
			OutError))
	{
		return false;
	}
	if (Impl->LastIssuedPersistenceRequestToken
		>= TNumericLimits<uint64>::Max() - 1)
	{
		return Fail(
			OutError,
			TEXT("checkpoint persistence request token cannot safely advance"));
	}

	FCheckpointPersistenceRequest Candidate;
	if (!CaptureCheckpointSet(
			StableId,
			Candidate.Checkpoint,
			OutError))
	{
		return false;
	}
	FCheckpointPersistenceTicket& Ticket =
		Candidate.Ticket;
	Ticket.TargetStableId = StableId;
	Ticket.VolumeSpecSha256 =
		Volume->Spec.CanonicalSpecSha256;
	Ticket.bExpectedAcknowledgedBase =
		Volume->bHasAcknowledgedCheckpoint;
	Ticket.ExpectedJournalBaseRevision =
		Volume->JournalBaseRevision;
	if (Volume->bHasAcknowledgedCheckpoint)
	{
		Ticket.ExpectedBaseCheckpointManifestSha256 =
			Volume->BaseCheckpointManifestSha256;
		Ticket.ExpectedBaseJournalTailSha256 =
			Volume->BaseJournalTailSha256;
	}
	Ticket.CheckpointThroughRevision =
		Candidate.Checkpoint.ThroughRevision;
	Ticket.CheckpointManifestSha256 =
		Candidate.Checkpoint.CanonicalManifestSha256;
	Ticket.CheckpointJournalTailSha256 =
		MoveTemp(FinalJournalTailSha256);
	Ticket.AuthorityGenerationToken =
		Volume->AuthorityGenerationToken;
	Ticket.BackendInstanceId = Impl->BackendInstanceId;
	Ticket.PersistenceRequestToken =
		Impl->LastIssuedPersistenceRequestToken + 1;

	FString ValidationError;
	if (!ValidateCheckpointPersistenceRequest(
			Candidate,
			&ValidationError)
		|| Ticket.CheckpointThroughRevision
			!= Volume->CurrentRevision
		|| Ticket.CheckpointManifestSha256
			!= Candidate.Checkpoint.CanonicalManifestSha256)
	{
		return Fail(
			OutError,
			FString::Printf(
				TEXT("captured checkpoint persistence request failed validation: %s"),
				*ValidationError));
	}

	// The live pending capability changes only after the checkpoint and ticket validate.
	Impl->LastIssuedPersistenceRequestToken =
		Ticket.PersistenceRequestToken;
	Volume->PendingCheckpointTicket = Ticket;
	Volume->bCheckpointPersistencePending = true;
	OutRequest = MoveTemp(Candidate);
	OutError.Reset();
	return true;
}

bool FRedInMemorySparseVoxelBackend::AcknowledgePersistedCheckpoint(
	const FCheckpointPersistenceAcknowledgement& Acknowledgement,
	FString& OutError)
{
	if (!RequireGameThread(OutError))
	{
		return false;
	}
	FString ValidationError;
	if (!ValidateCheckpointPersistenceTicket(
			Acknowledgement.Ticket,
			&ValidationError))
	{
		return Fail(
			OutError,
			FString::Printf(
				TEXT("checkpoint persistence acknowledgement is malformed: %s"),
				*ValidationError));
	}

	const FCheckpointPersistenceTicket& Ticket =
		Acknowledgement.Ticket;
	FStoredVolume* Volume =
		Impl->Volumes.Find(Ticket.TargetStableId);
	if (!Volume)
	{
		return Fail(OutError, TEXT("volume does not exist"));
	}
	if (Ticket.VolumeSpecSha256
			!= Volume->Spec.CanonicalSpecSha256
		|| Ticket.AuthorityGenerationToken
			!= Volume->AuthorityGenerationToken
		|| Ticket.BackendInstanceId != Impl->BackendInstanceId)
	{
		return Fail(
			OutError,
			TEXT("checkpoint persistence acknowledgement targets stale or foreign authority state"));
	}
	FString CurrentJournalTailSha256;
	if (!ValidateStoredJournalState(
			*Volume,
			CurrentJournalTailSha256,
			OutError))
	{
		return false;
	}

	// An exact duplicate of the currently committed acknowledgement is idempotent.
	if (Volume->bHasAcknowledgedCheckpoint
		&& AreCheckpointPersistenceTicketsEquivalent(
			Ticket,
			Volume->LastAcknowledgedCheckpointTicket)
		&& Volume->JournalBaseRevision
			== Ticket.CheckpointThroughRevision
		&& Volume->BaseCheckpointManifestSha256
			== Ticket.CheckpointManifestSha256
		&& Volume->BaseJournalTailSha256
			== Ticket.CheckpointJournalTailSha256)
	{
		OutError.Reset();
		return true;
	}

	if (!Volume->bCheckpointPersistencePending
		|| !AreCheckpointPersistenceTicketsEquivalent(
			Ticket,
			Volume->PendingCheckpointTicket))
	{
		return Fail(
			OutError,
			TEXT("checkpoint persistence acknowledgement does not match the exact live pending ticket"));
	}
	const FString ExpectedBaseManifestSha256 =
		Volume->bHasAcknowledgedCheckpoint
			? Volume->BaseCheckpointManifestSha256
			: FString();
	const FString ExpectedBaseJournalTailSha256 =
		Volume->bHasAcknowledgedCheckpoint
			? Volume->BaseJournalTailSha256
			: FString();
	if (Ticket.bExpectedAcknowledgedBase
			!= Volume->bHasAcknowledgedCheckpoint
		|| Ticket.ExpectedJournalBaseRevision
			!= Volume->JournalBaseRevision
		|| Ticket.ExpectedBaseCheckpointManifestSha256
			!= ExpectedBaseManifestSha256
		|| Ticket.ExpectedBaseJournalTailSha256
			!= ExpectedBaseJournalTailSha256
		|| Ticket.CheckpointThroughRevision
			< Volume->JournalBaseRevision
		|| Ticket.CheckpointThroughRevision
			> Volume->CurrentRevision)
	{
		return Fail(
			OutError,
			TEXT("checkpoint persistence acknowledgement failed its exact live base compare-and-swap"));
	}

	const uint64 PrefixCount64 =
		Ticket.CheckpointThroughRevision
			- Volume->JournalBaseRevision;
	if (PrefixCount64
		> static_cast<uint64>(Volume->Journal.Num()))
	{
		return Fail(
			OutError,
			TEXT("checkpoint persistence ticket covers a journal prefix that is no longer live"));
	}
	const int32 PrefixCount =
		static_cast<int32>(PrefixCount64);
	const FString CheckpointJournalTailSha256 =
		PrefixCount == 0
			? Volume->BaseJournalTailSha256
			: Volume->Journal[PrefixCount - 1]
				.CanonicalOperationSha256;
	if (CheckpointJournalTailSha256
			!= Ticket.CheckpointJournalTailSha256)
	{
		return Fail(
			OutError,
			TEXT("checkpoint persistence ticket history tail does not match its live journal prefix"));
	}

	if (Ticket.CheckpointThroughRevision
		== Volume->CurrentRevision)
	{
		if (CurrentJournalTailSha256
			!= Ticket.CheckpointJournalTailSha256)
		{
			return Fail(
				OutError,
				TEXT("checkpoint persistence ticket does not cover the current journal tail"));
		}
		FVolumeCheckpoint LiveCheckpoint;
		if (!CaptureCheckpointSet(
				Ticket.TargetStableId,
				LiveCheckpoint,
				OutError))
		{
			return false;
		}
		if (LiveCheckpoint.CanonicalManifestSha256
			!= Ticket.CheckpointManifestSha256)
		{
			return Fail(
				OutError,
				TEXT("checkpoint persistence ticket manifest no longer matches live authority state"));
		}
	}

	TArray<FEditOperation> StagedJournalSuffix;
	StagedJournalSuffix.Reserve(
		Volume->Journal.Num() - PrefixCount);
	for (int32 OperationIndex = PrefixCount;
		OperationIndex < Volume->Journal.Num();
		++OperationIndex)
	{
		StagedJournalSuffix.Add(
			Volume->Journal[OperationIndex]);
	}
	if (!StagedJournalSuffix.IsEmpty()
		&& StagedJournalSuffix[0].PreviousOperationSha256
			!= Ticket.CheckpointJournalTailSha256)
	{
		return Fail(
			OutError,
			TEXT("staged journal suffix is not chained to the acknowledged checkpoint"));
	}

	// A trusted adapter declaration commits the checkpoint base and prefix compaction
	// together. This in-memory transition does not itself prove external fsync.
	Volume->bHasAcknowledgedCheckpoint = true;
	Volume->JournalBaseRevision =
		Ticket.CheckpointThroughRevision;
	Volume->BaseCheckpointManifestSha256 =
		Ticket.CheckpointManifestSha256;
	Volume->BaseJournalTailSha256 =
		Ticket.CheckpointJournalTailSha256;
	Volume->Journal = MoveTemp(StagedJournalSuffix);
	Volume->LastAcknowledgedCheckpointTicket = Ticket;
	Volume->PendingCheckpointTicket =
		FCheckpointPersistenceTicket();
	Volume->bCheckpointPersistencePending = false;
	OutError.Reset();
	return true;
}

bool FRedInMemorySparseVoxelBackend::InspectCheckpointSet(
	const FVolumeCheckpoint& Checkpoint,
	FVolumeCheckpointVerification& OutVerification,
	FString& OutError) const
{
	OutVerification = FVolumeCheckpointVerification();
	if (!RequireGameThread(OutError))
	{
		return false;
	}
	FString ValidationError;
	if (!ValidateAuthorityLimits(
			Checkpoint.AuthorityLimits,
			&ValidationError)
		|| !ValidateVolumeSpec(
			Checkpoint.VolumeSpec,
			Checkpoint.AuthorityLimits,
			&ValidationError))
	{
		return Fail(
			OutError,
			FString::Printf(
				TEXT("checkpoint portable policy or spec is invalid: %s"),
				*ValidationError));
	}
	if (!ValidateSupportedSpec(
			Checkpoint.VolumeSpec,
			Checkpoint.AuthorityLimits,
			OutError))
	{
		return false;
	}

	const FVolumeSpec& Spec = Checkpoint.VolumeSpec;
	const FAuthorityLimits& Limits = Checkpoint.AuthorityLimits;
	const FIntVector ChunkCounts = GetChunkCounts(Spec);
	const int32 ExpectedChunkCount =
		ChunkCounts.X * ChunkCounts.Y * ChunkCounts.Z;
	const int32 ExpectedCellCount = GetChunkCellCount(Spec);
	if (Checkpoint.Chunks.Num() != ExpectedChunkCount
		|| Checkpoint.Chunks.Num() > Limits.MaxCheckpointChunks)
	{
		return Fail(OutError, TEXT("checkpoint does not contain the exact chunk count"));
	}

	TSet<FIntVector> SeenChunks;
	TArray<FManifestRecord> ManifestRecords;
	ManifestRecords.Reserve(ExpectedChunkCount);
	OutVerification.Chunks.Reserve(ExpectedChunkCount);
	int64 TotalStoredBytes = 0;
	int64 TotalRemovedCellCount = 0;
	for (const FChunkCheckpoint& Chunk : Checkpoint.Chunks)
	{
		if (!IsChunkCoordinateInBounds(Chunk.ChunkCoordinate, ChunkCounts)
			|| SeenChunks.Contains(Chunk.ChunkCoordinate)
			|| Chunk.TargetStableId != Checkpoint.TargetStableId
			|| Chunk.ThroughRevision != Checkpoint.ThroughRevision)
		{
			return Fail(
				OutError,
				TEXT("checkpoint chunk identity, coordinate, or revision is invalid"));
		}
		SeenChunks.Add(Chunk.ChunkCoordinate);
		TArray<uint8> Cells;
		if (!DecodeCanonicalRle(
				Chunk.CompressedDensityAndMaterial,
				ExpectedCellCount,
				Limits.MaxCompressedCheckpointBytesPerChunk,
				Limits.MaxUncompressedCheckpointBytesPerChunk,
				Cells,
				OutError))
		{
			return false;
		}
		int64 RemovedCellCount = 0;
		if (!ValidateChunkCellsAgainstBase(
				Spec,
				Chunk.ChunkCoordinate,
				Cells,
				&RemovedCellCount,
				OutError))
		{
			return false;
		}
		TotalRemovedCellCount += RemovedCellCount;

		FChunkCheckpointVerification ChunkVerification;
		ChunkVerification.ChunkCoordinate = Chunk.ChunkCoordinate;
		ChunkVerification.ActualUncompressedByteCount = Cells.Num();
		if (!HashBytes(
				Cells,
				ChunkVerification.RecomputedCanonicalPayloadSha256))
		{
			return Fail(OutError, TEXT("failed to hash inspected checkpoint chunk"));
		}
		TotalStoredBytes += Chunk.CompressedDensityAndMaterial.Num();
		TotalStoredBytes += Cells.Num();
		if (TotalStoredBytes > Limits.MaxCheckpointSetBytes)
		{
			return Fail(OutError, TEXT("checkpoint exceeds aggregate byte limit"));
		}

		FManifestRecord Record;
		Record.ChunkCoordinate = Chunk.ChunkCoordinate;
		Record.UncompressedCellCount = ExpectedCellCount;
		Record.UncompressedByteCount = Cells.Num();
		Record.CodecId = Chunk.CodecId;
		Record.PayloadSha256 =
			ChunkVerification.RecomputedCanonicalPayloadSha256;
		ManifestRecords.Add(MoveTemp(Record));
		OutVerification.Chunks.Add(MoveTemp(ChunkVerification));
	}
	const uint64 RemovedCellCount =
		static_cast<uint64>(TotalRemovedCellCount);
	const uint64 ThroughRevision = Checkpoint.ThroughRevision;
	const uint64 MaxRemovedByRevision =
		ThroughRevision > TNumericLimits<uint64>::Max()
				/ static_cast<uint64>(Limits.MaxEditedCellsPerRequest)
			? TNumericLimits<uint64>::Max()
			: ThroughRevision
				* static_cast<uint64>(Limits.MaxEditedCellsPerRequest);
	if ((ThroughRevision == 0 && RemovedCellCount != 0)
		|| (ThroughRevision > 0
			&& (RemovedCellCount < ThroughRevision
				|| RemovedCellCount > MaxRemovedByRevision)))
	{
		return Fail(
			OutError,
			TEXT("checkpoint removed-cell count is impossible for its accepted revision"));
	}
	if (!BuildManifestSha256(
			Checkpoint,
			MoveTemp(ManifestRecords),
			OutVerification.RecomputedCanonicalManifestSha256))
	{
		return Fail(OutError, TEXT("failed to hash inspected checkpoint manifest"));
	}
	OutVerification.Chunks.Sort(
		[](const FChunkCheckpointVerification& A,
			const FChunkCheckpointVerification& B)
		{
			FManifestRecord Left;
			Left.ChunkCoordinate = A.ChunkCoordinate;
			FManifestRecord Right;
			Right.ChunkCoordinate = B.ChunkCoordinate;
			return ManifestRecordLess(Left, Right);
		});
	if (!ValidateVolumeCheckpoint(
			Checkpoint,
			OutVerification,
			Spec,
			Limits,
			&ValidationError))
	{
		return Fail(
			OutError,
			FString::Printf(
				TEXT("checkpoint authority validation failed: %s"),
				*ValidationError));
	}
	OutError.Reset();
	return true;
}

bool FRedInMemorySparseVoxelBackend::RestoreCheckpointSetAtomically(
	const FVolumeCheckpoint& Checkpoint,
	const FVolumeCheckpointVerification& Verification,
	const FCheckpointRestorePrecondition& Precondition,
	FString& OutError)
{
	if (!RequireGameThread(OutError))
	{
		return false;
	}
	FVolumeCheckpointVerification TrustedVerification;
	if (!InspectCheckpointSet(
			Checkpoint,
			TrustedVerification,
			OutError))
	{
		return false;
	}
	if (!VerificationsEquivalent(TrustedVerification, Verification))
	{
		return Fail(
			OutError,
			TEXT("caller checkpoint verification does not match fresh bounded inspection"));
	}
	FString ValidationError;
	if (!ValidateCheckpointRestorePrecondition(
			Precondition,
			Checkpoint,
			&ValidationError))
	{
		return Fail(
			OutError,
			FString::Printf(
				TEXT("checkpoint restore precondition is invalid: %s"),
				*ValidationError));
	}

	FStoredVolume* Existing =
		Impl->Volumes.Find(Checkpoint.TargetStableId);
	uint64 NewGenerationToken = 0;
	switch (Precondition.Mode)
	{
	case ECheckpointRestoreMode::InitializeAbsentVolume:
		if (Existing)
		{
			return Fail(
				OutError,
				TEXT("absent-volume restore target already exists"));
		}
		{
			const uint64 LastIssuedGenerationToken =
				Impl->LastIssuedGenerationTokens.FindRef(
					Checkpoint.TargetStableId);
			if (LastIssuedGenerationToken
				>= TNumericLimits<uint64>::Max() - 1)
			{
				return Fail(
					OutError,
					TEXT("stable volume generation token cannot safely advance"));
			}
			NewGenerationToken =
				LastIssuedGenerationToken + 1;
		}
		break;
	case ECheckpointRestoreMode::ReplaceQuiescedVolume:
		if (!Existing
			|| Existing->CurrentRevision
				!= Precondition.ExpectedCurrentRevision
			|| Existing->AuthorityGenerationToken
				!= Precondition.ExpectedAuthorityGenerationToken
			|| !AreSpecsEquivalent(Existing->Spec, Checkpoint.VolumeSpec)
			|| !AreLimitsEquivalent(
				Existing->Limits,
				Checkpoint.AuthorityLimits)
			|| Impl->LastIssuedGenerationTokens.FindRef(
				Checkpoint.TargetStableId)
				!= Existing->AuthorityGenerationToken)
		{
			return Fail(
				OutError,
				TEXT("live volume does not satisfy exact restore compare-and-swap state"));
		}
		if (Existing->AuthorityGenerationToken
			>= TNumericLimits<uint64>::Max() - 1)
		{
			return Fail(
				OutError,
				TEXT("authority generation token cannot safely advance"));
		}
		if (Checkpoint.ThroughRevision == Existing->CurrentRevision)
		{
			FVolumeCheckpoint LiveCheckpoint;
			if (!CaptureCheckpointSet(
					Checkpoint.TargetStableId,
					LiveCheckpoint,
					OutError))
			{
				return false;
			}
			if (LiveCheckpoint.CanonicalManifestSha256
				!= Checkpoint.CanonicalManifestSha256)
			{
				return Fail(
					OutError,
					TEXT("equal-revision checkpoint content does not match live authority state"));
			}
		}
		NewGenerationToken =
			Existing->AuthorityGenerationToken + 1;
		break;
	default:
		return Fail(OutError, TEXT("unsupported checkpoint restore mode"));
	}

	FDecodedCheckpoint Decoded;
	if (!DecodeCheckpointToTemporaryState(
			Checkpoint,
			NewGenerationToken,
			Decoded,
			OutError))
	{
		return false;
	}
	if (Existing
		&& !ValidateSubtractiveReplacement(
			*Existing,
			Decoded,
			Checkpoint.ThroughRevision,
			OutError))
	{
		return false;
	}

	FStoredVolume Candidate;
	Candidate.Spec = Checkpoint.VolumeSpec;
	Candidate.Limits = Checkpoint.AuthorityLimits;
	Candidate.CurrentRevision = Checkpoint.ThroughRevision;
	Candidate.AuthorityGenerationToken = NewGenerationToken;
	Candidate.MinimumAcceptedBuildGenerationToken =
		NewGenerationToken;
	Candidate.NonEmptyChunks = MoveTemp(Decoded.NonEmptyChunks);
	Candidate.ChunkMetadata = MoveTemp(Decoded.ChunkMetadata);
	// A valid imported checkpoint is not silently declared durable by this process.
	// It becomes the unacknowledged journal base and requires a fresh capture/ticket
	// acknowledgement before any portable suffix may be exported.
	Candidate.JournalBaseRevision =
		Checkpoint.ThroughRevision;
	Candidate.bHasAcknowledgedCheckpoint = false;
	Candidate.BaseCheckpointManifestSha256.Reset();
	Candidate.BaseJournalTailSha256.Reset();
	Candidate.PendingCheckpointTicket =
		FCheckpointPersistenceTicket();
	Candidate.LastAcknowledgedCheckpointTicket =
		FCheckpointPersistenceTicket();
	Candidate.bCheckpointPersistencePending = false;
	Candidate.Journal.Reset();

	// The final game-thread commit block begins only after full validation.
	Impl->Volumes.Add(
		Checkpoint.TargetStableId,
		MoveTemp(Candidate));
	Impl->LastIssuedGenerationTokens.Add(
		Checkpoint.TargetStableId,
		NewGenerationToken);
	OutError.Reset();
	return true;
}

bool FRedInMemorySparseVoxelBackend::QueueChunkRebuild(
	const FChunkRevision& Revision,
	const EGeneratedOutputRequirement OutputRole,
	FGeneratedChunkBuildRequest& OutRequest,
	FString& OutError)
{
	OutRequest = FGeneratedChunkBuildRequest();
	if (!RequireGameThread(OutError))
	{
		return false;
	}
	if (!IsSingleGeneratedOutputRole(OutputRole))
	{
		return Fail(
			OutError,
			TEXT("chunk rebuild requests must authorize exactly one output role"));
	}
	FStoredVolume* Volume =
		Impl->Volumes.Find(Revision.TargetStableId);
	if (!Volume)
	{
		return Fail(OutError, TEXT("volume does not exist"));
	}
	const FIntVector ChunkCounts = GetChunkCounts(Volume->Spec);
	if (!IsChunkCoordinateInBounds(
			Revision.ChunkCoordinate,
			ChunkCounts))
	{
		return Fail(OutError, TEXT("chunk coordinate is out of bounds"));
	}
	const int32 ChunkIndex =
		GetLinearIndex(Revision.ChunkCoordinate, ChunkCounts);
	FStoredChunkMetadata& Metadata =
		Volume->ChunkMetadata[ChunkIndex];
	if (Revision.ContentRevision != Metadata.ContentRevision
		|| Revision.ContentSha256 != Metadata.ContentSha256
		|| Revision.GenerationToken != Volume->AuthorityGenerationToken
		|| Revision.GenerationToken
			< Volume->MinimumAcceptedBuildGenerationToken
		|| Metadata.GeneratedOutput.TargetStableId
			!= Revision.TargetStableId
		|| Metadata.GeneratedOutput.ChunkCoordinate
			!= Revision.ChunkCoordinate
		|| Metadata.GeneratedOutput.ContentRevision
			!= Revision.ContentRevision
		|| Metadata.GeneratedOutput.ContentSha256
			!= Revision.ContentSha256
		|| Metadata.GeneratedOutput.GenerationToken
			!= Revision.GenerationToken)
	{
		return Fail(
			OutError,
			TEXT("chunk rebuild request is stale or does not match authority content"));
	}
	const bool bPresentationRole =
		OutputRole == EGeneratedOutputRequirement::Presentation;
	if ((bPresentationRole
			&& Metadata.GeneratedOutput.bPresentationReady)
		|| (!bPresentationRole
			&& Metadata.GeneratedOutput.bCollisionReady))
	{
		return Fail(
			OutError,
			TEXT("the requested generated-output role is already ready"));
	}
	if (!Impl->BackendInstanceId.IsValid()
		|| Impl->LastIssuedBuildRequestToken
			>= TNumericLimits<uint64>::Max() - 1)
	{
		return Fail(
			OutError,
			TEXT("generated-output build ticket identity is exhausted or invalid"));
	}

	TArray<uint8> ImmutableCells;
	GetChunkCells(*Volume, ChunkIndex, ImmutableCells);
	FString RecomputedContentSha256;
	if (ImmutableCells.Num() != GetChunkCellCount(Volume->Spec)
		|| !HashChunkContent(
			Volume->Spec,
			Revision.ChunkCoordinate,
			ImmutableCells,
			RecomputedContentSha256)
		|| RecomputedContentSha256 != Revision.ContentSha256)
	{
		return Fail(
			OutError,
			TEXT("immutable chunk build snapshot does not match authority content"));
	}

	const uint64 NewBuildRequestToken =
		Impl->LastIssuedBuildRequestToken + 1;
	FGeneratedChunkBuildTicket CandidateTicket;
	CandidateTicket.SourceRevision = Revision;
	CandidateTicket.VolumeSpecSha256 =
		Volume->Spec.CanonicalSpecSha256;
	CandidateTicket.OutputRole = OutputRole;
	CandidateTicket.BuildProfileId =
		GeneratedOutputBuildProfileId;
	CandidateTicket.BuildProfileVersion =
		GeneratedOutputBuildProfileVersion;
	CandidateTicket.BackendInstanceId =
		Impl->BackendInstanceId;
	CandidateTicket.BuildRequestToken =
		NewBuildRequestToken;
	FString TicketReason;
	if (!ValidateGeneratedChunkBuildTicket(
			CandidateTicket,
			&TicketReason))
	{
		return Fail(
			OutError,
			FString::Printf(
				TEXT("generated-output build ticket validation failed: %s"),
				*TicketReason));
	}

	FGeneratedChunkBuildRequest CandidateRequest;
	CandidateRequest.Ticket = CandidateTicket;
	CandidateRequest.VolumeSpec = Volume->Spec;
	CandidateRequest.CanonicalDensityAndMaterial =
		MoveTemp(ImmutableCells);

	// Commit begins only after source identity, immutable cells, and ticket validate.
	if (bPresentationRole)
	{
		Metadata.PresentationBuildTicket =
			CandidateTicket;
		Metadata.bPresentationBuildPending = true;
	}
	else
	{
		Metadata.CollisionBuildTicket =
			CandidateTicket;
		Metadata.bCollisionBuildPending = true;
	}
	Impl->LastIssuedBuildRequestToken =
		NewBuildRequestToken;
	OutRequest = MoveTemp(CandidateRequest);
	OutError.Reset();
	return true;
}

bool FRedInMemorySparseVoxelBackend::CompleteChunkRebuild(
	const FGeneratedChunkBuildCompletion& Completion,
	FString& OutError)
{
	if (!RequireGameThread(OutError))
	{
		return false;
	}
	FString CompletionReason;
	if (!ValidateGeneratedChunkBuildCompletion(
			Completion,
			&CompletionReason))
	{
		return Fail(
			OutError,
			FString::Printf(
				TEXT("generated-output completion validation failed: %s"),
				*CompletionReason));
	}

	const FGeneratedChunkBuildTicket& Ticket =
		Completion.Ticket;
	FStoredVolume* Volume =
		Impl->Volumes.Find(Ticket.SourceRevision.TargetStableId);
	if (!Volume)
	{
		return Fail(OutError, TEXT("volume does not exist"));
	}
	const FIntVector ChunkCounts = GetChunkCounts(Volume->Spec);
	if (!IsChunkCoordinateInBounds(
			Ticket.SourceRevision.ChunkCoordinate,
			ChunkCounts))
	{
		return Fail(OutError, TEXT("chunk coordinate is out of bounds"));
	}
	const int32 ChunkIndex =
		GetLinearIndex(
			Ticket.SourceRevision.ChunkCoordinate,
			ChunkCounts);
	FStoredChunkMetadata& Metadata =
		Volume->ChunkMetadata[ChunkIndex];
	if (Ticket.VolumeSpecSha256
			!= Volume->Spec.CanonicalSpecSha256
		|| Ticket.BuildProfileId
			!= GeneratedOutputBuildProfileId
		|| Ticket.BuildProfileVersion
			!= GeneratedOutputBuildProfileVersion
		|| Ticket.BackendInstanceId
			!= Impl->BackendInstanceId
		|| Ticket.SourceRevision.ContentRevision
			!= Metadata.ContentRevision
		|| Ticket.SourceRevision.ContentSha256
			!= Metadata.ContentSha256
		|| Ticket.SourceRevision.GenerationToken
			!= Volume->AuthorityGenerationToken
		|| Ticket.SourceRevision.GenerationToken
			< Volume->MinimumAcceptedBuildGenerationToken
		|| Metadata.GeneratedOutput.TargetStableId
			!= Ticket.SourceRevision.TargetStableId
		|| Metadata.GeneratedOutput.ChunkCoordinate
			!= Ticket.SourceRevision.ChunkCoordinate
		|| Metadata.GeneratedOutput.ContentRevision
			!= Ticket.SourceRevision.ContentRevision
		|| Metadata.GeneratedOutput.ContentSha256
			!= Ticket.SourceRevision.ContentSha256
		|| Metadata.GeneratedOutput.GenerationToken
			!= Ticket.SourceRevision.GenerationToken)
	{
		return Fail(
			OutError,
			TEXT("generated-output completion is stale or does not match live authority"));
	}

	const bool bPresentationRole =
		Ticket.OutputRole
			== EGeneratedOutputRequirement::Presentation;
	FGeneratedChunkBuildTicket& StoredTicket =
		bPresentationRole
			? Metadata.PresentationBuildTicket
			: Metadata.CollisionBuildTicket;
	bool& bBuildPending =
		bPresentationRole
			? Metadata.bPresentationBuildPending
			: Metadata.bCollisionBuildPending;
	bool& bOutputReady =
		bPresentationRole
			? Metadata.GeneratedOutput.bPresentationReady
			: Metadata.GeneratedOutput.bCollisionReady;
	FString& StoredOutputSha256 =
		bPresentationRole
			? Metadata.GeneratedOutput.PresentationOutputSha256
			: Metadata.GeneratedOutput.CollisionOutputSha256;

	if (!AreBuildTicketsEquivalent(Ticket, StoredTicket))
	{
		return Fail(
			OutError,
			TEXT("generated-output completion ticket is not the active role attempt"));
	}
	if (!bBuildPending)
	{
		if (bOutputReady
			&& StoredOutputSha256 == Completion.OutputSha256)
		{
			OutError.Reset();
			return true;
		}
		return Fail(
			OutError,
			TEXT("generated-output completion conflicts with the accepted role output"));
	}

	// Role readiness changes only after every live identity and ticket check passes.
	bOutputReady = true;
	StoredOutputSha256 = Completion.OutputSha256;
	bBuildPending = false;
	OutError.Reset();
	return true;
}

bool FRedInMemorySparseVoxelBackend::QueryGeneratedOutputState(
	const FName StableId,
	const FIntVector& ChunkCoordinate,
	FGeneratedChunkOutputState& OutState,
	FString& OutError) const
{
	OutState = FGeneratedChunkOutputState();
	if (!RequireGameThread(OutError))
	{
		return false;
	}
	const FStoredVolume* Volume = Impl->Volumes.Find(StableId);
	if (!Volume)
	{
		return Fail(OutError, TEXT("volume does not exist"));
	}
	const FIntVector ChunkCounts = GetChunkCounts(Volume->Spec);
	if (!IsChunkCoordinateInBounds(ChunkCoordinate, ChunkCounts))
	{
		return Fail(OutError, TEXT("chunk coordinate is out of bounds"));
	}
	const int32 ChunkIndex =
		GetLinearIndex(ChunkCoordinate, ChunkCounts);
	OutState = Volume->ChunkMetadata[ChunkIndex].GeneratedOutput;
	OutError.Reset();
	return true;
}

void FRedInMemorySparseVoxelBackend::InvalidateBuildsOlderThan(
	const FName StableId,
	const uint64 GenerationToken)
{
	if (!IsInGameThread())
	{
		return;
	}
	FStoredVolume* Volume = Impl->Volumes.Find(StableId);
	if (!Volume
		|| GenerationToken == 0
		|| GenerationToken > Volume->AuthorityGenerationToken)
	{
		return;
	}
	Volume->MinimumAcceptedBuildGenerationToken = FMath::Max(
		Volume->MinimumAcceptedBuildGenerationToken,
		GenerationToken);
	for (FStoredChunkMetadata& Metadata : Volume->ChunkMetadata)
	{
		if (Metadata.GeneratedOutput.GenerationToken < GenerationToken)
		{
			Metadata.GeneratedOutput.bPresentationReady = false;
			Metadata.GeneratedOutput.bCollisionReady = false;
			Metadata.GeneratedOutput.PresentationOutputSha256.Reset();
			Metadata.GeneratedOutput.CollisionOutputSha256.Reset();
			Metadata.PresentationBuildTicket =
				FGeneratedChunkBuildTicket();
			Metadata.CollisionBuildTicket =
				FGeneratedChunkBuildTicket();
			Metadata.bPresentationBuildPending = false;
			Metadata.bCollisionBuildPending = false;
		}
	}
}

bool FRedInMemorySparseVoxelBackend::ReleaseVolume(
	const FName StableId,
	const uint64 ExpectedAuthorityGenerationToken,
	FString& OutError)
{
	if (!RequireGameThread(OutError))
	{
		return false;
	}
	if (ExpectedAuthorityGenerationToken == 0)
	{
		return Fail(
			OutError,
			TEXT("volume release requires a nonzero authority generation token"));
	}
	FStoredVolume* Volume = Impl->Volumes.Find(StableId);
	if (!Volume)
	{
		return Fail(
			OutError,
			TEXT("volume release target does not exist"));
	}
	if (Volume->AuthorityGenerationToken
		!= ExpectedAuthorityGenerationToken)
	{
		return Fail(
			OutError,
			TEXT("volume release targets a stale or future authority generation"));
	}

	const int32 RemovedCount = Impl->Volumes.Remove(StableId);
	if (RemovedCount != 1)
	{
		return Fail(
			OutError,
			TEXT("exact volume release failed atomically"));
	}
	OutError.Reset();
	return true;
}
