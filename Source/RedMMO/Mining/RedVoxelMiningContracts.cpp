#include "RedVoxelMiningContracts.h"

namespace
{
	bool Fail(FString* OutReason, const TCHAR* Reason)
	{
		if (OutReason)
		{
			*OutReason = Reason;
		}
		return false;
	}

	void ClearReason(FString* OutReason)
	{
		if (OutReason)
		{
			OutReason->Reset();
		}
	}

	bool IsFiniteVector(const FVector& Value)
	{
		return FMath::IsFinite(Value.X)
			&& FMath::IsFinite(Value.Y)
			&& FMath::IsFinite(Value.Z);
	}

	bool IsPositiveAndAtMost(const FIntVector& Value, const int32 Maximum)
	{
		return Value.X > 0 && Value.Y > 0 && Value.Z > 0
			&& Value.X <= Maximum && Value.Y <= Maximum && Value.Z <= Maximum;
	}

	bool IsNonNegative(const FIntVector& Value)
	{
		return Value.X >= 0 && Value.Y >= 0 && Value.Z >= 0;
	}

	bool TryMultiplyPositive(
		const int32 X,
		const int32 Y,
		const int32 Z,
		int64& OutProduct)
	{
		OutProduct = 0;
		if (X <= 0 || Y <= 0 || Z <= 0)
		{
			return false;
		}

		const int64 MaxValue = TNumericLimits<int64>::Max();
		int64 Product = X;
		if (Product > MaxValue / Y)
		{
			return false;
		}
		Product *= Y;
		if (Product > MaxValue / Z)
		{
			return false;
		}
		OutProduct = Product * Z;
		return true;
	}

	bool IsAllowedCheckpointCodec(const FName CodecId)
	{
		static const FName RleV1(TEXT("red.codec.rle-v1"));
		return CodecId == RleV1;
	}

	uint32 FloatBits32(const float Value)
	{
		uint32 Bits = 0;
		static_assert(sizeof(Bits) == sizeof(Value));
		FMemory::Memcpy(&Bits, &Value, sizeof(Bits));
		return Bits;
	}

	uint64 DoubleBits64(const double Value)
	{
		uint64 Bits = 0;
		static_assert(sizeof(Bits) == sizeof(Value));
		FMemory::Memcpy(&Bits, &Value, sizeof(Bits));
		return Bits;
	}

	uint32 RotateRight32(const uint32 Value, const uint32 Bits)
	{
		return (Value >> Bits) | (Value << (32U - Bits));
	}

	FString Sha256Hex(const uint8* Data, const int32 DataLength)
	{
		static constexpr uint32 RoundConstants[64] = {
			0x428a2f98U, 0x71374491U, 0xb5c0fbcfU, 0xe9b5dba5U,
			0x3956c25bU, 0x59f111f1U, 0x923f82a4U, 0xab1c5ed5U,
			0xd807aa98U, 0x12835b01U, 0x243185beU, 0x550c7dc3U,
			0x72be5d74U, 0x80deb1feU, 0x9bdc06a7U, 0xc19bf174U,
			0xe49b69c1U, 0xefbe4786U, 0x0fc19dc6U, 0x240ca1ccU,
			0x2de92c6fU, 0x4a7484aaU, 0x5cb0a9dcU, 0x76f988daU,
			0x983e5152U, 0xa831c66dU, 0xb00327c8U, 0xbf597fc7U,
			0xc6e00bf3U, 0xd5a79147U, 0x06ca6351U, 0x14292967U,
			0x27b70a85U, 0x2e1b2138U, 0x4d2c6dfcU, 0x53380d13U,
			0x650a7354U, 0x766a0abbU, 0x81c2c92eU, 0x92722c85U,
			0xa2bfe8a1U, 0xa81a664bU, 0xc24b8b70U, 0xc76c51a3U,
			0xd192e819U, 0xd6990624U, 0xf40e3585U, 0x106aa070U,
			0x19a4c116U, 0x1e376c08U, 0x2748774cU, 0x34b0bcb5U,
			0x391c0cb3U, 0x4ed8aa4aU, 0x5b9cca4fU, 0x682e6ff3U,
			0x748f82eeU, 0x78a5636fU, 0x84c87814U, 0x8cc70208U,
			0x90befffaU, 0xa4506cebU, 0xbef9a3f7U, 0xc67178f2U
		};
		uint32 State[8] = {
			0x6a09e667U, 0xbb67ae85U, 0x3c6ef372U, 0xa54ff53aU,
			0x510e527fU, 0x9b05688cU, 0x1f83d9abU, 0x5be0cd19U
		};

		const int32 PaddedLength = ((DataLength + 9 + 63) / 64) * 64;
		TArray<uint8> Padded;
		Padded.SetNumZeroed(PaddedLength);
		if (DataLength > 0)
		{
			FMemory::Memcpy(Padded.GetData(), Data, DataLength);
		}
		Padded[DataLength] = 0x80U;
		const uint64 BitLength = static_cast<uint64>(DataLength) * 8U;
		for (int32 ByteIndex = 0; ByteIndex < 8; ++ByteIndex)
		{
			Padded[PaddedLength - 1 - ByteIndex] =
				static_cast<uint8>(BitLength >> (ByteIndex * 8));
		}

		for (int32 Offset = 0; Offset < PaddedLength; Offset += 64)
		{
			uint32 Words[64] = {};
			for (int32 WordIndex = 0; WordIndex < 16; ++WordIndex)
			{
				const int32 ByteOffset = Offset + WordIndex * 4;
				Words[WordIndex] =
					(static_cast<uint32>(Padded[ByteOffset]) << 24)
					| (static_cast<uint32>(Padded[ByteOffset + 1]) << 16)
					| (static_cast<uint32>(Padded[ByteOffset + 2]) << 8)
					| static_cast<uint32>(Padded[ByteOffset + 3]);
			}
			for (int32 WordIndex = 16; WordIndex < 64; ++WordIndex)
			{
				const uint32 SmallSigma0 =
					RotateRight32(Words[WordIndex - 15], 7)
					^ RotateRight32(Words[WordIndex - 15], 18)
					^ (Words[WordIndex - 15] >> 3);
				const uint32 SmallSigma1 =
					RotateRight32(Words[WordIndex - 2], 17)
					^ RotateRight32(Words[WordIndex - 2], 19)
					^ (Words[WordIndex - 2] >> 10);
				Words[WordIndex] = Words[WordIndex - 16]
					+ SmallSigma0
					+ Words[WordIndex - 7]
					+ SmallSigma1;
			}

			uint32 A = State[0];
			uint32 B = State[1];
			uint32 C = State[2];
			uint32 D = State[3];
			uint32 E = State[4];
			uint32 F = State[5];
			uint32 G = State[6];
			uint32 H = State[7];
			for (int32 Round = 0; Round < 64; ++Round)
			{
				const uint32 BigSigma1 =
					RotateRight32(E, 6)
					^ RotateRight32(E, 11)
					^ RotateRight32(E, 25);
				const uint32 Choose = (E & F) ^ (~E & G);
				const uint32 Temporary1 =
					H + BigSigma1 + Choose + RoundConstants[Round] + Words[Round];
				const uint32 BigSigma0 =
					RotateRight32(A, 2)
					^ RotateRight32(A, 13)
					^ RotateRight32(A, 22);
				const uint32 Majority = (A & B) ^ (A & C) ^ (B & C);
				const uint32 Temporary2 = BigSigma0 + Majority;
				H = G;
				G = F;
				F = E;
				E = D + Temporary1;
				D = C;
				C = B;
				B = A;
				A = Temporary1 + Temporary2;
			}
			State[0] += A;
			State[1] += B;
			State[2] += C;
			State[3] += D;
			State[4] += E;
			State[5] += F;
			State[6] += G;
			State[7] += H;
		}

		static constexpr TCHAR HexDigits[] = TEXT("0123456789ABCDEF");
		FString Result;
		Result.Reserve(64);
		for (const uint32 Word : State)
		{
			for (int32 Shift = 24; Shift >= 0; Shift -= 8)
			{
				const uint8 Byte = static_cast<uint8>(Word >> Shift);
				Result.AppendChar(HexDigits[Byte >> 4]);
				Result.AppendChar(HexDigits[Byte & 0x0f]);
			}
		}
		return Result;
	}

	bool HasSameImmutableClusterIdentity(
		const RedVoxelMining::FLooseClusterState& A,
		const RedVoxelMining::FLooseClusterState& B)
	{
		return A.ClusterId == B.ClusterId
			&& A.SourceAsteroidStableId == B.SourceAsteroidStableId
			&& A.MaterialId == B.MaterialId
			&& A.Amount == B.Amount
			&& A.SpawnServerTimeSeconds == B.SpawnServerTimeSeconds;
	}

	bool HasSameAuthorityLimits(
		const RedVoxelMining::FAuthorityLimits& A,
		const RedVoxelMining::FAuthorityLimits& B)
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
			&& A.MinCellSizeCm == B.MinCellSizeCm
			&& A.MaxCellSizeCm == B.MaxCellSizeCm
			&& A.MinBrushRadiusCm == B.MinBrushRadiusCm
			&& A.MaxBrushRadiusCm == B.MaxBrushRadiusCm
			&& A.MaxMiningRangeCm == B.MaxMiningRangeCm
			&& A.MaxSuctionRangeCm == B.MaxSuctionRangeCm
			&& A.MaxSuctionDurationSeconds == B.MaxSuctionDurationSeconds
			&& A.MaxReservationDurationSeconds
				== B.MaxReservationDurationSeconds
			&& A.MaxCollectionArrivalDistanceCm
				== B.MaxCollectionArrivalDistanceCm
			&& A.MaxCollectionArrivalGraceSeconds
				== B.MaxCollectionArrivalGraceSeconds;
	}

	bool HasSameVolumeSpec(
		const RedVoxelMining::FVolumeSpec& A,
		const RedVoxelMining::FVolumeSpec& B)
	{
		return A.StableId == B.StableId
			&& A.MaterialTableId == B.MaterialTableId
			&& A.VolumeCellDimensions == B.VolumeCellDimensions
			&& A.ChunkCellDimensions == B.ChunkCellDimensions
			&& A.CellSizeCm == B.CellSizeCm
			&& A.BaseSeed == B.BaseSeed
			&& A.GenerationVersion == B.GenerationVersion
			&& A.CanonicalSpecSha256 == B.CanonicalSpecSha256;
	}
}

bool RedVoxelMining::IsNamespacedStableId(const FName StableId)
{
	if (StableId.IsNone())
	{
		return false;
	}

	const FString Text = StableId.ToString();
	int32 NamespaceSeparator = INDEX_NONE;
	if (!Text.FindChar(TEXT('.'), NamespaceSeparator)
		|| NamespaceSeparator <= 0
		|| NamespaceSeparator >= Text.Len() - 1
		|| Text.Contains(TEXT("|"))
		|| Text.Contains(TEXT("=")))
	{
		return false;
	}
	for (const TCHAR Character : Text)
	{
		if (FChar::IsWhitespace(Character))
		{
			return false;
		}
	}
	return true;
}

bool RedVoxelMining::IsCanonicalSha256(const FString& Value)
{
	if (Value.Len() != 64)
	{
		return false;
	}
	for (const TCHAR Character : Value)
	{
		if (!FChar::IsHexDigit(Character))
		{
			return false;
		}
	}
	return true;
}

bool RedVoxelMining::IsNextRevision(
	const uint64 CurrentRevision,
	const uint64 CandidateRevision)
{
	return CurrentRevision < TNumericLimits<uint64>::Max()
		&& CandidateRevision == CurrentRevision + 1;
}

bool RedVoxelMining::ComputeCanonicalSha256(
	const uint8* Data,
	const int32 DataLength,
	FString& OutSha256)
{
	OutSha256.Reset();
	if (DataLength < 0 || (DataLength > 0 && Data == nullptr))
	{
		return false;
	}
	OutSha256 = Sha256Hex(Data, DataLength);
	return IsCanonicalSha256(OutSha256);
}

bool RedVoxelMining::ComputeCanonicalVolumeSpecSha256(
	const FVolumeSpec& Spec,
	FString& OutSha256)
{
	OutSha256.Reset();
	uint32 CellSizeBits = 0;
	static_assert(sizeof(CellSizeBits) == sizeof(Spec.CellSizeCm));
	FMemory::Memcpy(&CellSizeBits, &Spec.CellSizeCm, sizeof(CellSizeBits));

	const FString CanonicalText = FString::Printf(
		TEXT("red.voxel-volume-spec.v1|stable=%s|material=%s|volume=%d,%d,%d|chunk=%d,%d,%d|cell-bits=%08X|seed=%u|generation=%u"),
		*Spec.StableId.ToString().ToLower(),
		*Spec.MaterialTableId.ToString().ToLower(),
		Spec.VolumeCellDimensions.X,
		Spec.VolumeCellDimensions.Y,
		Spec.VolumeCellDimensions.Z,
		Spec.ChunkCellDimensions.X,
		Spec.ChunkCellDimensions.Y,
		Spec.ChunkCellDimensions.Z,
		CellSizeBits,
		Spec.BaseSeed,
		Spec.GenerationVersion);
	const FTCHARToUTF8 Utf8(*CanonicalText);
	OutSha256 = Sha256Hex(
		reinterpret_cast<const uint8*>(Utf8.Get()),
		Utf8.Length());
	return IsCanonicalSha256(OutSha256);
}

bool RedVoxelMining::ValidateAuthorityLimits(
	const FAuthorityLimits& Limits,
	FString* OutReason)
{
	ClearReason(OutReason);
	if (Limits.MaxVolumeCellsPerAxis <= 0
		|| Limits.MaxVolumeCellsPerAxis > PrototypeHardMaxVolumeCellsPerAxis
		|| Limits.MaxChunkCellsPerAxis <= 0
		|| Limits.MaxChunkCellsPerAxis > PrototypeHardMaxChunkCellsPerAxis
		|| Limits.MaxChunkCellsPerAxis > Limits.MaxVolumeCellsPerAxis
		|| Limits.MaxEditedCellsPerRequest <= 0
		|| Limits.MaxEditedCellsPerRequest > PrototypeHardMaxEditedCellsPerRequest
		|| Limits.MaxDirtyChunksPerEdit <= 0
		|| Limits.MaxDirtyChunksPerEdit > PrototypeHardMaxDirtyChunksPerEdit
		|| Limits.MaxYieldEntriesPerEdit <= 0
		|| Limits.MaxYieldEntriesPerEdit > PrototypeHardMaxYieldEntriesPerEdit
		|| Limits.MaxClustersPerEdit <= 0
		|| Limits.MaxClustersPerEdit > PrototypeHardMaxClustersPerEdit
		|| Limits.MaxJournalOperationsPerCheckpoint <= 0
		|| Limits.MaxJournalOperationsPerCheckpoint
			> PrototypeHardMaxJournalOperationsPerCheckpoint
		|| Limits.MaxRequestsPerSecond <= 0
		|| Limits.MaxRequestsPerSecond > PrototypeHardMaxRequestsPerSecond
		|| Limits.MaxCheckpointChunks <= 0
		|| Limits.MaxCheckpointChunks > PrototypeHardMaxCheckpointChunks
		|| Limits.MaxCompressedCheckpointBytesPerChunk <= 0
		|| Limits.MaxCompressedCheckpointBytesPerChunk
			> PrototypeHardMaxCompressedBytesPerChunk
		|| Limits.MaxUncompressedCheckpointBytesPerChunk <= 0
		|| Limits.MaxUncompressedCheckpointBytesPerChunk
			> PrototypeHardMaxUncompressedBytesPerChunk
		|| Limits.MaxCheckpointSetBytes <= 0
		|| Limits.MaxCheckpointSetBytes > PrototypeHardMaxCheckpointSetBytes)
	{
		return Fail(OutReason, TEXT("integer authority limits exceed immutable prototype ceilings"));
	}

	if (!FMath::IsFinite(Limits.MinCellSizeCm)
		|| !FMath::IsFinite(Limits.MaxCellSizeCm)
		|| Limits.MinCellSizeCm <= 0.f
		|| Limits.MaxCellSizeCm < Limits.MinCellSizeCm
		|| Limits.MaxCellSizeCm > PrototypeHardMaxCellSizeCm
		|| !FMath::IsFinite(Limits.MinBrushRadiusCm)
		|| !FMath::IsFinite(Limits.MaxBrushRadiusCm)
		|| Limits.MinBrushRadiusCm <= 0.f
		|| Limits.MaxBrushRadiusCm < Limits.MinBrushRadiusCm
		|| Limits.MaxBrushRadiusCm > PrototypeHardMaxBrushRadiusCm
		|| !FMath::IsFinite(Limits.MaxMiningRangeCm)
		|| Limits.MaxMiningRangeCm <= 0.f
		|| Limits.MaxMiningRangeCm > PrototypeHardMaxMiningRangeCm
		|| !FMath::IsFinite(Limits.MaxSuctionRangeCm)
		|| Limits.MaxSuctionRangeCm <= 0.f
		|| Limits.MaxSuctionRangeCm > PrototypeHardMaxSuctionRangeCm
		|| !FMath::IsFinite(Limits.MaxSuctionDurationSeconds)
		|| Limits.MaxSuctionDurationSeconds <= 0.f
		|| Limits.MaxSuctionDurationSeconds > PrototypeHardMaxSuctionDurationSeconds
		|| !FMath::IsFinite(Limits.MaxReservationDurationSeconds)
		|| Limits.MaxReservationDurationSeconds < Limits.MaxSuctionDurationSeconds
		|| Limits.MaxReservationDurationSeconds
			> PrototypeHardMaxReservationDurationSeconds
		|| !FMath::IsFinite(Limits.MaxCollectionArrivalDistanceCm)
		|| Limits.MaxCollectionArrivalDistanceCm <= 0.f
		|| Limits.MaxCollectionArrivalDistanceCm
			> PrototypeHardMaxCollectionArrivalDistanceCm
		|| !FMath::IsFinite(Limits.MaxCollectionArrivalGraceSeconds)
		|| Limits.MaxCollectionArrivalGraceSeconds < 0.f
		|| Limits.MaxCollectionArrivalGraceSeconds
			> PrototypeHardMaxCollectionArrivalGraceSeconds)
	{
		return Fail(OutReason, TEXT("floating-point authority limits exceed immutable prototype ceilings"));
	}
	return true;
}

bool RedVoxelMining::ValidateVolumeSpec(
	const FVolumeSpec& Spec,
	const FAuthorityLimits& Limits,
	FString* OutReason)
{
	ClearReason(OutReason);
	if (!ValidateAuthorityLimits(Limits, OutReason))
	{
		return false;
	}
	if (!IsNamespacedStableId(Spec.StableId)
		|| !IsNamespacedStableId(Spec.MaterialTableId)
		|| !IsCanonicalSha256(Spec.CanonicalSpecSha256))
	{
		return Fail(OutReason, TEXT("volume identity, material table, or canonical fingerprint is invalid"));
	}
	FString RecomputedSpecSha256;
	if (!ComputeCanonicalVolumeSpecSha256(Spec, RecomputedSpecSha256)
		|| Spec.CanonicalSpecSha256 != RecomputedSpecSha256)
	{
		return Fail(OutReason, TEXT("volume canonical fingerprint does not match its immutable fields"));
	}
	if (!IsPositiveAndAtMost(Spec.VolumeCellDimensions, Limits.MaxVolumeCellsPerAxis)
		|| !IsPositiveAndAtMost(Spec.ChunkCellDimensions, Limits.MaxChunkCellsPerAxis)
		|| Spec.ChunkCellDimensions.X > Spec.VolumeCellDimensions.X
		|| Spec.ChunkCellDimensions.Y > Spec.VolumeCellDimensions.Y
		|| Spec.ChunkCellDimensions.Z > Spec.VolumeCellDimensions.Z
		|| Spec.VolumeCellDimensions.X % Spec.ChunkCellDimensions.X != 0
		|| Spec.VolumeCellDimensions.Y % Spec.ChunkCellDimensions.Y != 0
		|| Spec.VolumeCellDimensions.Z % Spec.ChunkCellDimensions.Z != 0)
	{
		return Fail(OutReason, TEXT("volume dimensions must be bounded multiples of chunk dimensions"));
	}

	int64 VolumeCellCount = 0;
	int64 ChunkCellCount = 0;
	const FIntVector ChunkCounts(
		Spec.VolumeCellDimensions.X / Spec.ChunkCellDimensions.X,
		Spec.VolumeCellDimensions.Y / Spec.ChunkCellDimensions.Y,
		Spec.VolumeCellDimensions.Z / Spec.ChunkCellDimensions.Z);
	int64 TotalChunkCount = 0;
	if (!TryMultiplyPositive(
			Spec.VolumeCellDimensions.X,
			Spec.VolumeCellDimensions.Y,
			Spec.VolumeCellDimensions.Z,
			VolumeCellCount)
		|| !TryMultiplyPositive(
			Spec.ChunkCellDimensions.X,
			Spec.ChunkCellDimensions.Y,
			Spec.ChunkCellDimensions.Z,
			ChunkCellCount)
		|| !TryMultiplyPositive(
			ChunkCounts.X,
			ChunkCounts.Y,
			ChunkCounts.Z,
			TotalChunkCount)
		|| VolumeCellCount <= 0
		|| ChunkCellCount <= 0
		|| TotalChunkCount > Limits.MaxCheckpointChunks)
	{
		return Fail(OutReason, TEXT("volume, chunk, or checkpoint multiplication is unsafe"));
	}
	if (!FMath::IsFinite(Spec.CellSizeCm)
		|| Spec.CellSizeCm < Limits.MinCellSizeCm
		|| Spec.CellSizeCm > Limits.MaxCellSizeCm
		|| Spec.BaseSeed == 0
		|| Spec.GenerationVersion == 0)
	{
		return Fail(OutReason, TEXT("cell size, base seed, or generation version is invalid"));
	}
	return true;
}

bool RedVoxelMining::ValidateClientRequestEnvelope(
	const FClientEditRequest& Request,
	const FAuthorityLimits& Limits,
	FString* OutReason)
{
	ClearReason(OutReason);
	if (!ValidateAuthorityLimits(Limits, OutReason))
	{
		return false;
	}
	if (!IsNamespacedStableId(Request.TargetStableId)
		|| !IsNamespacedStableId(Request.MiningToolStableId))
	{
		return Fail(OutReason, TEXT("request target and tool require namespaced stable IDs"));
	}
	if (Request.RequestSequence == 0
		|| Request.RequestSequence == TNumericLimits<uint64>::Max()
		|| Request.ExpectedRevision == TNumericLimits<uint64>::Max())
	{
		return Fail(OutReason, TEXT("request sequence or expected revision is invalid"));
	}
	if (!IsFiniteVector(Request.AimOrigin)
		|| !IsFiniteVector(Request.AimDirection)
		|| !Request.AimDirection.IsUnit(0.02)
		|| !FMath::IsFinite(Request.BrushRadiusCm)
		|| Request.BrushRadiusCm < Limits.MinBrushRadiusCm
		|| Request.BrushRadiusCm > Limits.MaxBrushRadiusCm
		|| !Request.PredictionToken.IsValid())
	{
		return Fail(OutReason, TEXT("request aim, brush, or prediction token is invalid"));
	}
	return true;
}

bool RedVoxelMining::ValidateServerEdit(
	const FValidatedEdit& Edit,
	const FAuthorityLimits& Limits,
	FString* OutReason)
{
	ClearReason(OutReason);
	if (!ValidateAuthorityLimits(Limits, OutReason))
	{
		return false;
	}
	if (!IsNamespacedStableId(Edit.TargetStableId)
		|| !IsNamespacedStableId(Edit.CollectorStableId)
		|| !IsNamespacedStableId(Edit.MiningToolStableId)
		|| Edit.RequestSequence == 0
		|| Edit.RequestSequence == TNumericLimits<uint64>::Max()
		|| Edit.ExpectedRevision == TNumericLimits<uint64>::Max()
		|| Edit.AuthorityGenerationToken == 0
		|| Edit.AuthorityGenerationToken == TNumericLimits<uint64>::Max())
	{
		return Fail(OutReason, TEXT("server edit identity, sequence, revision, or generation token is invalid"));
	}
	if (!IsFiniteVector(Edit.LocalBrushCenter)
		|| !IsFiniteVector(Edit.LocalSurfaceNormal)
		|| !Edit.LocalSurfaceNormal.IsUnit(0.02)
		|| !FMath::IsFinite(Edit.BrushRadiusCm)
		|| Edit.BrushRadiusCm < Limits.MinBrushRadiusCm
		|| Edit.BrushRadiusCm > Limits.MaxBrushRadiusCm
		|| !Edit.PredictionToken.IsValid())
	{
		return Fail(OutReason, TEXT("server edit brush or prediction token is invalid"));
	}
	return true;
}

bool RedVoxelMining::CanAcceptNextClientRequest(
	const FRequestSequenceState& State,
	const FClientEditRequest& Request,
	const FName AuthorityCollectorStableId,
	const uint64 CurrentVolumeRevision,
	const FAuthorityLimits& Limits,
	FString* OutReason)
{
	ClearReason(OutReason);
	if (!ValidateClientRequestEnvelope(Request, Limits, OutReason))
	{
		return false;
	}
	if (!IsNamespacedStableId(State.TargetStableId)
		|| !IsNamespacedStableId(State.CollectorStableId)
		|| State.CollectorStableId != AuthorityCollectorStableId
		|| State.TargetStableId != Request.TargetStableId)
	{
		return Fail(OutReason, TEXT("request sequence authority or stable target is invalid"));
	}
	if (CurrentVolumeRevision == TNumericLimits<uint64>::Max()
		|| Request.ExpectedRevision != CurrentVolumeRevision)
	{
		return Fail(OutReason, TEXT("request expected revision is stale or cannot advance"));
	}
	if (!IsNextRevision(State.LastAcceptedSequence, Request.RequestSequence))
	{
		return Fail(OutReason, TEXT("request sequence is duplicate, stale, skipped, or overflowed"));
	}
	if (Request.PredictionToken == State.LastAcceptedPredictionToken)
	{
		return Fail(OutReason, TEXT("request prediction token was already accepted"));
	}
	return true;
}

bool RedVoxelMining::CommitAcceptedClientRequest(
	FRequestSequenceState& State,
	const FClientEditRequest& Request,
	const FValidatedEdit& Edit,
	const FApplyResult& ValidatedResult,
	const FVolumeSpec& Volume,
	const FAuthorityLimits& Limits,
	FString* OutReason)
{
	ClearReason(OutReason);
	if (!CanAcceptNextClientRequest(
			State,
			Request,
			State.CollectorStableId,
			ValidatedResult.PreviousRevision,
			Limits,
			OutReason)
		|| !ValidatedResult.bAccepted
		|| Request.TargetStableId != Edit.TargetStableId
		|| State.CollectorStableId != Edit.CollectorStableId
		|| Request.MiningToolStableId != Edit.MiningToolStableId
		|| Request.RequestSequence != Edit.RequestSequence
		|| Request.ExpectedRevision != Edit.ExpectedRevision
		|| Request.PredictionToken != Edit.PredictionToken
		|| !ValidateApplyResult(
			ValidatedResult,
			Edit,
			Volume,
			Limits,
			OutReason))
	{
		return false;
	}

	State.LastAcceptedSequence = Request.RequestSequence;
	State.LastAcceptedRevision = ValidatedResult.AppliedRevision;
	State.LastAcceptedPredictionToken = Request.PredictionToken;
	return true;
}

bool RedVoxelMining::ValidateApplyResult(
	const FApplyResult& Result,
	const FValidatedEdit& Edit,
	const FVolumeSpec& Volume,
	const FAuthorityLimits& Limits,
	FString* OutReason)
{
	ClearReason(OutReason);
	if (!ValidateVolumeSpec(Volume, Limits, OutReason)
		|| !ValidateServerEdit(Edit, Limits, OutReason))
	{
		return false;
	}
	if (Edit.TargetStableId != Volume.StableId
		|| Result.TargetStableId != Edit.TargetStableId
		|| Result.RequestSequence != Edit.RequestSequence
		|| Result.PredictionToken != Edit.PredictionToken
		|| Result.AuthorityGenerationToken != Edit.AuthorityGenerationToken
		|| Result.PreviousRevision != Edit.ExpectedRevision)
	{
		return Fail(OutReason, TEXT("apply result does not match the validated edit and authoritative volume"));
	}
	if (!Result.bAccepted)
	{
		if (Result.RejectReason == EEditRejectReason::None
			|| Result.AppliedRevision != Result.PreviousRevision
			|| Result.TotalRemovedCellCount != 0
			|| !Result.MaterialYields.IsEmpty()
			|| !Result.DirtyChunkCoordinates.IsEmpty())
		{
			return Fail(OutReason, TEXT("a rejected edit must preserve revision and contain no mutation or yield"));
		}
		return true;
	}

	if (Result.RejectReason != EEditRejectReason::None
		|| !IsNextRevision(Result.PreviousRevision, Result.AppliedRevision)
		|| Result.TotalRemovedCellCount <= 0
		|| Result.TotalRemovedCellCount > Limits.MaxEditedCellsPerRequest
		|| Result.MaterialYields.IsEmpty()
		|| Result.MaterialYields.Num() > Limits.MaxYieldEntriesPerEdit
		|| Result.DirtyChunkCoordinates.IsEmpty()
		|| Result.DirtyChunkCoordinates.Num() > Limits.MaxDirtyChunksPerEdit)
	{
		return Fail(OutReason, TEXT("accepted edit revision, removed volume, yields, or dirty chunks are invalid"));
	}

	const double CellVolumeCm3 = static_cast<double>(Volume.CellSizeCm)
		* Volume.CellSizeCm * Volume.CellSizeCm;
	int64 YieldCellTotal = 0;
	TSet<FName> MaterialIds;
	for (const FMaterialYield& Yield : Result.MaterialYields)
	{
		const double ExpectedVolumeCm3 = Yield.RemovedCellCount * CellVolumeCm3;
		const double VolumeToleranceCm3 = FMath::Max(0.01, ExpectedVolumeCm3 * 1.e-6);
		if (!IsNamespacedStableId(Yield.MaterialId)
			|| Yield.RemovedCellCount <= 0
			|| !FMath::IsFinite(Yield.RemovedVolumeCm3)
			|| !FMath::IsNearlyEqual(
				Yield.RemovedVolumeCm3,
				ExpectedVolumeCm3,
				VolumeToleranceCm3)
			|| MaterialIds.Contains(Yield.MaterialId))
		{
			return Fail(OutReason, TEXT("accepted material yield is invalid, duplicated, or not cell-derived"));
		}
		MaterialIds.Add(Yield.MaterialId);
		YieldCellTotal += Yield.RemovedCellCount;
	}
	if (YieldCellTotal != Result.TotalRemovedCellCount)
	{
		return Fail(OutReason, TEXT("material yield cells must exactly equal removed cells"));
	}

	TSet<FIntVector> DirtyChunks;
	const FIntVector ChunkCounts(
		Volume.VolumeCellDimensions.X / Volume.ChunkCellDimensions.X,
		Volume.VolumeCellDimensions.Y / Volume.ChunkCellDimensions.Y,
		Volume.VolumeCellDimensions.Z / Volume.ChunkCellDimensions.Z);
	for (const FIntVector& ChunkCoordinate : Result.DirtyChunkCoordinates)
	{
		if (!IsNonNegative(ChunkCoordinate)
			|| ChunkCoordinate.X >= ChunkCounts.X
			|| ChunkCoordinate.Y >= ChunkCounts.Y
			|| ChunkCoordinate.Z >= ChunkCounts.Z
			|| DirtyChunks.Contains(ChunkCoordinate))
		{
			return Fail(OutReason, TEXT("dirty chunk coordinates must be unique and in bounds"));
		}
		DirtyChunks.Add(ChunkCoordinate);
	}
	return true;
}

bool RedVoxelMining::ValidateChunkCheckpoint(
	const FChunkCheckpoint& Checkpoint,
	const FChunkCheckpointVerification& Verification,
	const FVolumeSpec& Volume,
	const FAuthorityLimits& Limits,
	FString* OutReason)
{
	ClearReason(OutReason);
	if (!ValidateVolumeSpec(Volume, Limits, OutReason))
	{
		return false;
	}
	if (Checkpoint.TargetStableId != Volume.StableId
		|| Checkpoint.GenerationVersion != Volume.GenerationVersion
		|| Checkpoint.ThroughRevision == TNumericLimits<uint64>::Max()
		|| Checkpoint.BaseSeed != Volume.BaseSeed
		|| Checkpoint.MaterialTableId != Volume.MaterialTableId
		|| Checkpoint.VolumeSpecSha256 != Volume.CanonicalSpecSha256
		|| !IsAllowedCheckpointCodec(Checkpoint.CodecId)
		|| !IsCanonicalSha256(Checkpoint.CanonicalPayloadSha256)
		|| Checkpoint.CanonicalPayloadSha256
			!= Verification.RecomputedCanonicalPayloadSha256)
	{
		return Fail(OutReason, TEXT("checkpoint identity, spec, codec, or canonical payload hash is invalid"));
	}

	const FIntVector ChunkCounts(
		Volume.VolumeCellDimensions.X / Volume.ChunkCellDimensions.X,
		Volume.VolumeCellDimensions.Y / Volume.ChunkCellDimensions.Y,
		Volume.VolumeCellDimensions.Z / Volume.ChunkCellDimensions.Z);
	if (!IsNonNegative(Checkpoint.ChunkCoordinate)
		|| Checkpoint.ChunkCoordinate != Verification.ChunkCoordinate
		|| Checkpoint.ChunkCoordinate.X >= ChunkCounts.X
		|| Checkpoint.ChunkCoordinate.Y >= ChunkCounts.Y
		|| Checkpoint.ChunkCoordinate.Z >= ChunkCounts.Z)
	{
		return Fail(OutReason, TEXT("checkpoint chunk coordinate is outside the volume"));
	}

	int64 ExpectedCellCount = 0;
	if (!TryMultiplyPositive(
			Volume.ChunkCellDimensions.X,
			Volume.ChunkCellDimensions.Y,
			Volume.ChunkCellDimensions.Z,
			ExpectedCellCount)
		|| Checkpoint.UncompressedCellCount != ExpectedCellCount
		|| Checkpoint.UncompressedByteCount <= 0
		|| Checkpoint.UncompressedByteCount
			> Limits.MaxUncompressedCheckpointBytesPerChunk
		|| Checkpoint.UncompressedByteCount
			!= Verification.ActualUncompressedByteCount
		|| Checkpoint.CompressedDensityAndMaterial.IsEmpty()
		|| Checkpoint.CompressedDensityAndMaterial.Num()
			> Limits.MaxCompressedCheckpointBytesPerChunk)
	{
		return Fail(OutReason, TEXT("checkpoint cells, decompressed bytes, or compressed payload are invalid"));
	}
	return true;
}

bool RedVoxelMining::ValidateVolumeCheckpoint(
	const FVolumeCheckpoint& Checkpoint,
	const FVolumeCheckpointVerification& Verification,
	const FVolumeSpec& Volume,
	const FAuthorityLimits& Limits,
	FString* OutReason)
{
	ClearReason(OutReason);
	if (!ValidateVolumeSpec(Volume, Limits, OutReason))
	{
		return false;
	}
	if (!ValidateAuthorityLimits(Checkpoint.AuthorityLimits, OutReason)
		|| !ValidateVolumeSpec(
			Checkpoint.VolumeSpec,
			Checkpoint.AuthorityLimits,
			OutReason)
		|| !HasSameAuthorityLimits(Checkpoint.AuthorityLimits, Limits)
		|| !HasSameVolumeSpec(Checkpoint.VolumeSpec, Volume))
	{
		return Fail(
			OutReason,
			TEXT("checkpoint portable spec or authority limits do not match the expected volume"));
	}
	if (Checkpoint.TargetStableId != Volume.StableId
		|| Checkpoint.VolumeSpec.StableId != Volume.StableId
		|| Checkpoint.VolumeSpec.CanonicalSpecSha256
			!= Volume.CanonicalSpecSha256
		|| Checkpoint.GenerationVersion != Volume.GenerationVersion
		|| Checkpoint.BaseSeed != Volume.BaseSeed
		|| Checkpoint.MaterialTableId != Volume.MaterialTableId
		|| Checkpoint.VolumeSpecSha256 != Volume.CanonicalSpecSha256
		|| Checkpoint.ThroughRevision == TNumericLimits<uint64>::Max()
		|| !IsCanonicalSha256(Checkpoint.CanonicalManifestSha256)
		|| Checkpoint.CanonicalManifestSha256
			!= Verification.RecomputedCanonicalManifestSha256)
	{
		return Fail(OutReason, TEXT("checkpoint-set identity, spec, or manifest hash is invalid"));
	}

	const FIntVector ChunkCounts(
		Volume.VolumeCellDimensions.X / Volume.ChunkCellDimensions.X,
		Volume.VolumeCellDimensions.Y / Volume.ChunkCellDimensions.Y,
		Volume.VolumeCellDimensions.Z / Volume.ChunkCellDimensions.Z);
	int64 ExpectedChunkCount = 0;
	if (!TryMultiplyPositive(
			ChunkCounts.X,
			ChunkCounts.Y,
			ChunkCounts.Z,
			ExpectedChunkCount)
		|| ExpectedChunkCount > Limits.MaxCheckpointChunks
		|| Checkpoint.Chunks.Num() != ExpectedChunkCount
		|| Verification.Chunks.Num() != ExpectedChunkCount)
	{
		return Fail(OutReason, TEXT("checkpoint set does not contain the exact bounded chunk manifest"));
	}

	int64 TotalStoredBytes = 0;
	TSet<FIntVector> SeenChunks;
	for (const FChunkCheckpoint& Chunk : Checkpoint.Chunks)
	{
		if (Chunk.ThroughRevision != Checkpoint.ThroughRevision
			|| SeenChunks.Contains(Chunk.ChunkCoordinate))
		{
			return Fail(OutReason, TEXT("checkpoint chunk revision is inconsistent or duplicated"));
		}
		const FChunkCheckpointVerification* ChunkVerification =
			Verification.Chunks.FindByPredicate(
				[&Chunk](const FChunkCheckpointVerification& Candidate)
				{
					return Candidate.ChunkCoordinate == Chunk.ChunkCoordinate;
				});
		if (!ChunkVerification
			|| !ValidateChunkCheckpoint(
				Chunk,
				*ChunkVerification,
				Volume,
				Limits,
				OutReason))
		{
			return false;
		}
		SeenChunks.Add(Chunk.ChunkCoordinate);
		TotalStoredBytes += Chunk.CompressedDensityAndMaterial.Num();
		TotalStoredBytes += Chunk.UncompressedByteCount;
		if (TotalStoredBytes > Limits.MaxCheckpointSetBytes)
		{
			return Fail(OutReason, TEXT("checkpoint set exceeds its aggregate byte ceiling"));
		}
	}
	return true;
}

bool RedVoxelMining::ValidateCheckpointPersistenceTicket(
	const FCheckpointPersistenceTicket& Ticket,
	FString* OutReason)
{
	ClearReason(OutReason);
	if (!IsNamespacedStableId(Ticket.TargetStableId)
		|| !IsCanonicalSha256(Ticket.VolumeSpecSha256)
		|| !IsCanonicalSha256(Ticket.CheckpointManifestSha256)
		|| Ticket.CheckpointThroughRevision == TNumericLimits<uint64>::Max()
		|| Ticket.AuthorityGenerationToken == 0
		|| Ticket.AuthorityGenerationToken == TNumericLimits<uint64>::Max()
		|| !Ticket.BackendInstanceId.IsValid()
		|| Ticket.PersistenceRequestToken == 0
		|| Ticket.PersistenceRequestToken == TNumericLimits<uint64>::Max())
	{
		return Fail(
			OutReason,
			TEXT("checkpoint persistence ticket identity, revision, generation, or token is invalid"));
	}
	if (Ticket.ExpectedJournalBaseRevision > Ticket.CheckpointThroughRevision)
	{
		return Fail(
			OutReason,
			TEXT("checkpoint persistence ticket precedes its expected journal base"));
	}
	if (Ticket.bExpectedAcknowledgedBase)
	{
		if (!IsCanonicalSha256(
				Ticket.ExpectedBaseCheckpointManifestSha256)
			|| (!Ticket.ExpectedBaseJournalTailSha256.IsEmpty()
				&& !IsCanonicalSha256(
					Ticket.ExpectedBaseJournalTailSha256)))
		{
			return Fail(
				OutReason,
				TEXT("acknowledged checkpoint base identity is malformed"));
		}
	}
	else if (!Ticket.ExpectedBaseCheckpointManifestSha256.IsEmpty()
		|| !Ticket.ExpectedBaseJournalTailSha256.IsEmpty())
	{
		return Fail(
			OutReason,
			TEXT("an unacknowledged checkpoint base cannot carry durable identity"));
	}
	if (!Ticket.CheckpointJournalTailSha256.IsEmpty()
		&& !IsCanonicalSha256(Ticket.CheckpointJournalTailSha256))
	{
		return Fail(OutReason, TEXT("checkpoint journal tail is malformed"));
	}
	if (Ticket.CheckpointThroughRevision
			== Ticket.ExpectedJournalBaseRevision
		&& (Ticket.CheckpointJournalTailSha256
				!= Ticket.ExpectedBaseJournalTailSha256
			|| (Ticket.bExpectedAcknowledgedBase
				&& Ticket.CheckpointManifestSha256
					!= Ticket.ExpectedBaseCheckpointManifestSha256)))
	{
		return Fail(
			OutReason,
			TEXT("same-revision checkpoint identity does not match its acknowledged journal base"));
	}
	if (Ticket.CheckpointThroughRevision
			> Ticket.ExpectedJournalBaseRevision
		&& !IsCanonicalSha256(Ticket.CheckpointJournalTailSha256))
	{
		return Fail(
			OutReason,
			TEXT("an advanced checkpoint requires a canonical journal tail"));
	}
	return true;
}

bool RedVoxelMining::ValidateCheckpointPersistenceRequest(
	const FCheckpointPersistenceRequest& Request,
	FString* OutReason)
{
	ClearReason(OutReason);
	if (!ValidateCheckpointPersistenceTicket(
			Request.Ticket,
			OutReason))
	{
		return false;
	}
	const FCheckpointPersistenceTicket& Ticket =
		Request.Ticket;
	const FVolumeCheckpoint& Checkpoint =
		Request.Checkpoint;
	if (Checkpoint.TargetStableId != Ticket.TargetStableId
		|| Checkpoint.VolumeSpec.StableId
			!= Ticket.TargetStableId
		|| Checkpoint.VolumeSpecSha256
			!= Ticket.VolumeSpecSha256
		|| Checkpoint.VolumeSpec.CanonicalSpecSha256
			!= Ticket.VolumeSpecSha256
		|| Checkpoint.ThroughRevision
			!= Ticket.CheckpointThroughRevision
		|| Checkpoint.CanonicalManifestSha256
			!= Ticket.CheckpointManifestSha256
		|| Checkpoint.GenerationVersion
			!= Checkpoint.VolumeSpec.GenerationVersion
		|| Checkpoint.BaseSeed
			!= Checkpoint.VolumeSpec.BaseSeed
		|| Checkpoint.MaterialTableId
			!= Checkpoint.VolumeSpec.MaterialTableId)
	{
		return Fail(
			OutReason,
			TEXT("checkpoint persistence request ticket and checkpoint identity do not match"));
	}
	return true;
}

bool RedVoxelMining::ComputeCanonicalEditOperationSha256(
	const FEditOperation& Operation,
	FString& OutSha256)
{
	OutSha256.Reset();
	if (!IsNamespacedStableId(Operation.TargetStableId)
		|| !IsCanonicalSha256(Operation.VolumeSpecSha256)
		|| !Operation.OperationId.IsValid()
		|| !IsNamespacedStableId(Operation.CollectorStableId)
		|| !IsNamespacedStableId(Operation.MiningToolStableId)
		|| !Operation.PredictionToken.IsValid()
		|| !IsCanonicalSha256(Operation.ResultContentSha256)
		|| (!Operation.PreviousOperationSha256.IsEmpty()
			&& !IsCanonicalSha256(
				Operation.PreviousOperationSha256)))
	{
		return false;
	}
	const FString PreviousOperation =
		Operation.PreviousOperationSha256.IsEmpty()
			? TEXT("none")
			: Operation.PreviousOperationSha256;
	const FString Canonical = FString::Printf(
		TEXT("red.voxel-edit-operation.v1")
		TEXT("|target=%s|spec=%s|operation=%s|collector=%s|tool=%s")
		TEXT("|algorithm=%u|previous=%llu|revision=%llu|sequence=%llu")
		TEXT("|prediction=%s")
		TEXT("|center-bits=%016llX,%016llX,%016llX")
		TEXT("|normal-bits=%016llX,%016llX,%016llX")
		TEXT("|radius-bits=%08X|removed=%d|result=%s|previous-operation=%s"),
		*Operation.TargetStableId.ToString().ToLower(),
		*Operation.VolumeSpecSha256,
		*Operation.OperationId.ToString(EGuidFormats::Digits).ToLower(),
		*Operation.CollectorStableId.ToString().ToLower(),
		*Operation.MiningToolStableId.ToString().ToLower(),
		Operation.EditAlgorithmVersion,
		static_cast<unsigned long long>(Operation.PreviousRevision),
		static_cast<unsigned long long>(Operation.Revision),
		static_cast<unsigned long long>(Operation.RequestSequence),
		*Operation.PredictionToken.ToString(EGuidFormats::Digits).ToLower(),
		static_cast<unsigned long long>(
			DoubleBits64(Operation.LocalBrushCenter.X)),
		static_cast<unsigned long long>(
			DoubleBits64(Operation.LocalBrushCenter.Y)),
		static_cast<unsigned long long>(
			DoubleBits64(Operation.LocalBrushCenter.Z)),
		static_cast<unsigned long long>(
			DoubleBits64(Operation.LocalSurfaceNormal.X)),
		static_cast<unsigned long long>(
			DoubleBits64(Operation.LocalSurfaceNormal.Y)),
		static_cast<unsigned long long>(
			DoubleBits64(Operation.LocalSurfaceNormal.Z)),
		FloatBits32(Operation.BrushRadiusCm),
		Operation.RemovedCellCount,
		*Operation.ResultContentSha256,
		*PreviousOperation);
	const FTCHARToUTF8 Utf8(*Canonical);
	return ComputeCanonicalSha256(
		reinterpret_cast<const uint8*>(Utf8.Get()),
		Utf8.Length(),
		OutSha256);
}

bool RedVoxelMining::ValidateEditOperation(
	const FEditOperation& Operation,
	const FAuthorityLimits& Limits,
	FString* OutReason)
{
	ClearReason(OutReason);
	if (!ValidateAuthorityLimits(Limits, OutReason))
	{
		return false;
	}
	if (!IsNamespacedStableId(Operation.TargetStableId)
		|| !IsCanonicalSha256(Operation.VolumeSpecSha256)
		|| !Operation.OperationId.IsValid()
		|| !IsNamespacedStableId(Operation.CollectorStableId)
		|| !IsNamespacedStableId(Operation.MiningToolStableId)
		|| Operation.EditAlgorithmVersion != PrototypeEditAlgorithmVersion
		|| !IsNextRevision(
			Operation.PreviousRevision,
			Operation.Revision)
		|| Operation.RequestSequence == 0
		|| Operation.RequestSequence == TNumericLimits<uint64>::Max()
		|| !Operation.PredictionToken.IsValid())
	{
		return Fail(
			OutReason,
			TEXT("edit operation identity, algorithm, revision, sequence, or token is invalid"));
	}
	if (!IsFiniteVector(Operation.LocalBrushCenter)
		|| !IsFiniteVector(Operation.LocalSurfaceNormal)
		|| !Operation.LocalSurfaceNormal.IsUnit(0.02)
		|| !FMath::IsFinite(Operation.BrushRadiusCm)
		|| Operation.BrushRadiusCm < Limits.MinBrushRadiusCm
		|| Operation.BrushRadiusCm > Limits.MaxBrushRadiusCm
		|| Operation.RemovedCellCount <= 0
		|| Operation.RemovedCellCount > Limits.MaxEditedCellsPerRequest)
	{
		return Fail(
			OutReason,
			TEXT("edit operation brush or removed-cell count is invalid"));
	}
	if (!IsCanonicalSha256(Operation.ResultContentSha256)
		|| (!Operation.PreviousOperationSha256.IsEmpty()
			&& !IsCanonicalSha256(
				Operation.PreviousOperationSha256))
		|| !IsCanonicalSha256(Operation.CanonicalOperationSha256))
	{
		return Fail(OutReason, TEXT("edit operation hash identity is malformed"));
	}
	FString RecomputedSha256;
	if (!ComputeCanonicalEditOperationSha256(
			Operation,
			RecomputedSha256)
		|| RecomputedSha256 != Operation.CanonicalOperationSha256)
	{
		return Fail(
			OutReason,
			TEXT("edit operation canonical hash does not match its fields"));
	}
	return true;
}

bool RedVoxelMining::ComputeCanonicalEditJournalSha256(
	const FEditJournalExport& Export,
	FString& OutSha256)
{
	OutSha256.Reset();
	if (!IsNamespacedStableId(Export.TargetStableId)
		|| !IsCanonicalSha256(Export.VolumeSpecSha256)
		|| !IsCanonicalSha256(
			Export.BaseCheckpointManifestSha256)
		|| (!Export.BaseJournalTailSha256.IsEmpty()
			&& !IsCanonicalSha256(
				Export.BaseJournalTailSha256))
		|| (!Export.FinalJournalTailSha256.IsEmpty()
			&& !IsCanonicalSha256(
				Export.FinalJournalTailSha256))
		|| Export.ThroughRevision
			< Export.BaseCheckpointRevision)
	{
		return false;
	}
	const uint64 RevisionDelta =
		Export.ThroughRevision
			- Export.BaseCheckpointRevision;
	if (Export.Operations.Num()
			> PrototypeHardMaxJournalOperationsPerCheckpoint
		|| RevisionDelta
			!= static_cast<uint64>(Export.Operations.Num()))
	{
		return false;
	}
	for (const FEditOperation& Operation : Export.Operations)
	{
		if (!IsCanonicalSha256(
			Operation.CanonicalOperationSha256))
		{
			return false;
		}
	}
	const FString BaseManifest =
		Export.BaseCheckpointManifestSha256.IsEmpty()
			? TEXT("none")
			: Export.BaseCheckpointManifestSha256;
	const FString BaseTail =
		Export.BaseJournalTailSha256.IsEmpty()
			? TEXT("none")
			: Export.BaseJournalTailSha256;
	const FString FinalTail =
		Export.FinalJournalTailSha256.IsEmpty()
			? TEXT("none")
			: Export.FinalJournalTailSha256;
	FString Canonical = FString::Printf(
		TEXT("red.voxel-edit-journal-export.v1")
		TEXT("|target=%s|spec=%s|base=%llu|base-manifest=%s")
		TEXT("|base-tail=%s|through=%llu|count=%d|final-tail=%s"),
		*Export.TargetStableId.ToString().ToLower(),
		*Export.VolumeSpecSha256,
		static_cast<unsigned long long>(
			Export.BaseCheckpointRevision),
		*BaseManifest,
		*BaseTail,
		static_cast<unsigned long long>(Export.ThroughRevision),
		Export.Operations.Num(),
		*FinalTail);
	for (const FEditOperation& Operation : Export.Operations)
	{
		Canonical += FString::Printf(
			TEXT("|operation=%s"),
			*Operation.CanonicalOperationSha256);
	}
	const FTCHARToUTF8 Utf8(*Canonical);
	return ComputeCanonicalSha256(
		reinterpret_cast<const uint8*>(Utf8.Get()),
		Utf8.Length(),
		OutSha256);
}

bool RedVoxelMining::ValidateEditJournalExport(
	const FEditJournalExport& Export,
	const FAuthorityLimits& Limits,
	FString* OutReason)
{
	ClearReason(OutReason);
	if (!ValidateAuthorityLimits(Limits, OutReason))
	{
		return false;
	}
	if (!IsNamespacedStableId(Export.TargetStableId)
		|| !IsCanonicalSha256(Export.VolumeSpecSha256)
		|| !IsCanonicalSha256(
			Export.BaseCheckpointManifestSha256)
		|| (!Export.BaseJournalTailSha256.IsEmpty()
			&& !IsCanonicalSha256(
				Export.BaseJournalTailSha256))
		|| (!Export.FinalJournalTailSha256.IsEmpty()
			&& !IsCanonicalSha256(
				Export.FinalJournalTailSha256))
		|| !IsCanonicalSha256(Export.CanonicalManifestSha256)
		|| Export.ThroughRevision < Export.BaseCheckpointRevision)
	{
		return Fail(
			OutReason,
			TEXT("journal export envelope identity, hash, or revision is invalid"));
	}
	const uint64 RevisionDelta =
		Export.ThroughRevision - Export.BaseCheckpointRevision;
	if (RevisionDelta
			> static_cast<uint64>(
				Limits.MaxJournalOperationsPerCheckpoint)
		|| Export.Operations.Num()
			!= static_cast<int32>(RevisionDelta))
	{
		return Fail(
			OutReason,
			TEXT("journal export is not the exact bounded suffix after its checkpoint"));
	}

	uint64 ExpectedPreviousRevision =
		Export.BaseCheckpointRevision;
	FString ExpectedPreviousTail =
		Export.BaseJournalTailSha256;
	TSet<FGuid> SeenOperationIds;
	TSet<FString> SeenCollectorSequences;
	for (const FEditOperation& Operation : Export.Operations)
	{
		if (!ValidateEditOperation(Operation, Limits, OutReason))
		{
			return false;
		}
		const FString CollectorSequenceKey =
			FString::Printf(
				TEXT("%s:%llu"),
				*Operation.CollectorStableId.ToString().ToLower(),
				static_cast<unsigned long long>(
					Operation.RequestSequence));
		if (SeenOperationIds.Contains(Operation.OperationId)
			|| SeenCollectorSequences.Contains(
				CollectorSequenceKey))
		{
			return Fail(
				OutReason,
				TEXT("journal export repeats an operation or per-collector request identity"));
		}
		SeenOperationIds.Add(Operation.OperationId);
		SeenCollectorSequences.Add(CollectorSequenceKey);
		if (Operation.TargetStableId != Export.TargetStableId
			|| Operation.VolumeSpecSha256
				!= Export.VolumeSpecSha256
			|| Operation.PreviousRevision
				!= ExpectedPreviousRevision
			|| Operation.PreviousOperationSha256
				!= ExpectedPreviousTail)
		{
			return Fail(
				OutReason,
				TEXT("journal export contains a foreign, malformed, gapped, or unchained operation"));
		}
		ExpectedPreviousRevision = Operation.Revision;
		ExpectedPreviousTail =
			Operation.CanonicalOperationSha256;
	}
	if (ExpectedPreviousRevision != Export.ThroughRevision
		|| ExpectedPreviousTail != Export.FinalJournalTailSha256)
	{
		return Fail(
			OutReason,
			TEXT("journal export final revision or history tail is inconsistent"));
	}
	FString RecomputedManifestSha256;
	if (!ComputeCanonicalEditJournalSha256(
			Export,
			RecomputedManifestSha256)
		|| RecomputedManifestSha256
			!= Export.CanonicalManifestSha256)
	{
		return Fail(
			OutReason,
			TEXT("journal export manifest does not match its exact ordered suffix"));
	}
	return true;
}

bool RedVoxelMining::ValidateCheckpointRestorePrecondition(
	const FCheckpointRestorePrecondition& Precondition,
	const FVolumeCheckpoint& Checkpoint,
	FString* OutReason)
{
	ClearReason(OutReason);
	if (!IsNamespacedStableId(Precondition.TargetStableId)
		|| Precondition.TargetStableId != Checkpoint.TargetStableId
		|| Checkpoint.ThroughRevision == TNumericLimits<uint64>::Max())
	{
		return Fail(OutReason, TEXT("checkpoint restore target or checkpoint revision is invalid"));
	}

	switch (Precondition.Mode)
	{
	case ECheckpointRestoreMode::InitializeAbsentVolume:
		if (Precondition.ExpectedCurrentRevision != 0
			|| Precondition.ExpectedAuthorityGenerationToken != 0)
		{
			return Fail(OutReason, TEXT("absent-volume initialization cannot claim live revision or generation state"));
		}
		return true;
	case ECheckpointRestoreMode::ReplaceQuiescedVolume:
		if (Precondition.ExpectedCurrentRevision == TNumericLimits<uint64>::Max()
			|| Precondition.ExpectedAuthorityGenerationToken == 0
			|| Precondition.ExpectedAuthorityGenerationToken
				>= TNumericLimits<uint64>::Max() - 1
			|| Checkpoint.ThroughRevision < Precondition.ExpectedCurrentRevision)
		{
			return Fail(OutReason, TEXT("quiesced restore is stale or cannot safely advance generation"));
		}
		return true;
	default:
		return Fail(OutReason, TEXT("checkpoint restore mode is invalid"));
	}
}

bool RedVoxelMining::AreGeneratedOutputsCurrent(
	const FChunkRevision& Expected,
	const FGeneratedChunkOutputState& Actual,
	const EGeneratedOutputRequirement Requirement)
{
	const uint8 RequirementBits = static_cast<uint8>(Requirement);
	const bool bRequiresPresentation =
		(RequirementBits & static_cast<uint8>(
			EGeneratedOutputRequirement::Presentation)) != 0;
	const bool bRequiresCollision =
		(RequirementBits & static_cast<uint8>(
			EGeneratedOutputRequirement::Collision)) != 0;
	return IsNamespacedStableId(Expected.TargetStableId)
		&& IsCanonicalSha256(Expected.ContentSha256)
		&& Expected.GenerationToken > 0
		&& Expected.GenerationToken < TNumericLimits<uint64>::Max()
		&& RequirementBits > 0
		&& RequirementBits
			<= static_cast<uint8>(
				EGeneratedOutputRequirement::PresentationAndCollision)
		&& Actual.TargetStableId == Expected.TargetStableId
		&& Actual.ChunkCoordinate == Expected.ChunkCoordinate
		&& Actual.ContentRevision == Expected.ContentRevision
		&& Actual.ContentSha256 == Expected.ContentSha256
		&& Actual.GenerationToken == Expected.GenerationToken
		&& (!Actual.bPresentationReady
			|| IsCanonicalSha256(Actual.PresentationOutputSha256))
		&& (!Actual.bCollisionReady
			|| IsCanonicalSha256(Actual.CollisionOutputSha256))
		&& (Actual.bPresentationReady
			|| Actual.PresentationOutputSha256.IsEmpty())
		&& (Actual.bCollisionReady
			|| Actual.CollisionOutputSha256.IsEmpty())
		&& (!bRequiresPresentation || Actual.bPresentationReady)
		&& (!bRequiresCollision || Actual.bCollisionReady);
}

bool RedVoxelMining::ValidateGeneratedChunkBuildTicket(
	const FGeneratedChunkBuildTicket& Ticket,
	FString* OutReason)
{
	ClearReason(OutReason);
	const uint8 OutputRole = static_cast<uint8>(Ticket.OutputRole);
	if (!IsNamespacedStableId(Ticket.SourceRevision.TargetStableId)
		|| Ticket.SourceRevision.ChunkCoordinate.X < 0
		|| Ticket.SourceRevision.ChunkCoordinate.Y < 0
		|| Ticket.SourceRevision.ChunkCoordinate.Z < 0
		|| !IsCanonicalSha256(Ticket.SourceRevision.ContentSha256)
		|| Ticket.SourceRevision.GenerationToken == 0
		|| Ticket.SourceRevision.GenerationToken
			== TNumericLimits<uint64>::Max()
		|| !IsCanonicalSha256(Ticket.VolumeSpecSha256)
		|| (OutputRole
				!= static_cast<uint8>(
					EGeneratedOutputRequirement::Presentation)
			&& OutputRole
				!= static_cast<uint8>(
					EGeneratedOutputRequirement::Collision))
		|| !IsNamespacedStableId(Ticket.BuildProfileId)
		|| Ticket.BuildProfileVersion == 0
		|| !Ticket.BackendInstanceId.IsValid()
		|| Ticket.BuildRequestToken == 0
		|| Ticket.BuildRequestToken == TNumericLimits<uint64>::Max())
	{
		return Fail(
			OutReason,
			TEXT("generated chunk build ticket is malformed or not single-role"));
	}
	return true;
}

bool RedVoxelMining::ValidateGeneratedChunkBuildCompletion(
	const FGeneratedChunkBuildCompletion& Completion,
	FString* OutReason)
{
	ClearReason(OutReason);
	if (!ValidateGeneratedChunkBuildTicket(
			Completion.Ticket,
			OutReason)
		|| !IsCanonicalSha256(Completion.OutputSha256))
	{
		return Fail(
			OutReason,
			TEXT("generated chunk build completion is malformed"));
	}
	return true;
}

bool RedVoxelMining::ValidateLooseClusterState(
	const FLooseClusterState& State,
	const FAuthorityLimits& Limits,
	FString* OutReason)
{
	ClearReason(OutReason);
	if (!ValidateAuthorityLimits(Limits, OutReason)
		|| !State.ClusterId.IsValid()
		|| !IsNamespacedStableId(State.SourceAsteroidStableId)
		|| !IsNamespacedStableId(State.MaterialId)
		|| State.Amount <= 0
		|| State.Amount > Limits.MaxEditedCellsPerRequest
		|| State.Revision == 0
		|| !FMath::IsFinite(State.SpawnServerTimeSeconds)
		|| !FMath::IsFinite(State.ReservationExpiryServerTimeSeconds)
		|| !FMath::IsFinite(State.AttractionStartServerTimeSeconds)
		|| !FMath::IsFinite(State.ExpectedArrivalServerTimeSeconds)
		|| !FMath::IsFinite(State.CollectedServerTimeSeconds)
		|| State.SpawnServerTimeSeconds < 0.0)
	{
		return Fail(OutReason, TEXT("loose cluster identity, amount, revision, or time is invalid"));
	}

	switch (State.Phase)
	{
	case ELooseClusterPhase::Loose:
		if (!State.CollectorStableId.IsNone()
			|| State.ReservationToken.IsValid()
			|| State.ReservationExpiryServerTimeSeconds != 0.0
			|| State.AttractionStartServerTimeSeconds != 0.0
			|| State.ExpectedArrivalServerTimeSeconds != 0.0
			|| State.CollectedServerTimeSeconds != 0.0)
		{
			return Fail(OutReason, TEXT("loose cluster cannot retain reservation or arrival state"));
		}
		return true;
	case ELooseClusterPhase::Reserved:
		if (!IsNamespacedStableId(State.CollectorStableId)
			|| !State.ReservationToken.IsValid()
			|| State.ReservationExpiryServerTimeSeconds <= State.SpawnServerTimeSeconds
			|| State.ReservationExpiryServerTimeSeconds - State.SpawnServerTimeSeconds
				> Limits.MaxReservationDurationSeconds
			|| State.AttractionStartServerTimeSeconds != 0.0
			|| State.ExpectedArrivalServerTimeSeconds != 0.0
			|| State.CollectedServerTimeSeconds != 0.0)
		{
			return Fail(OutReason, TEXT("reserved cluster timing or reservation identity is invalid"));
		}
		return true;
	case ELooseClusterPhase::Attracting:
	case ELooseClusterPhase::Collected:
		if (!IsNamespacedStableId(State.CollectorStableId)
			|| !State.ReservationToken.IsValid()
			|| State.AttractionStartServerTimeSeconds < State.SpawnServerTimeSeconds
			|| State.ExpectedArrivalServerTimeSeconds
				<= State.AttractionStartServerTimeSeconds
			|| State.ExpectedArrivalServerTimeSeconds
				- State.AttractionStartServerTimeSeconds
				> Limits.MaxSuctionDurationSeconds
			|| State.ReservationExpiryServerTimeSeconds
				< State.ExpectedArrivalServerTimeSeconds
			|| State.ReservationExpiryServerTimeSeconds - State.SpawnServerTimeSeconds
				> Limits.MaxReservationDurationSeconds)
		{
			return Fail(OutReason, TEXT("attracting cluster timing or reservation identity is invalid"));
		}
		if (State.Phase == ELooseClusterPhase::Attracting)
		{
			return State.CollectedServerTimeSeconds == 0.0
				? true
				: Fail(OutReason, TEXT("attracting cluster cannot already have a collected time"));
		}
		if (State.CollectedServerTimeSeconds < State.AttractionStartServerTimeSeconds
			|| State.CollectedServerTimeSeconds > State.ReservationExpiryServerTimeSeconds
			|| State.CollectedServerTimeSeconds
				> State.ExpectedArrivalServerTimeSeconds
					+ Limits.MaxCollectionArrivalGraceSeconds)
		{
			return Fail(OutReason, TEXT("collected cluster time is outside the authoritative arrival window"));
		}
		return true;
	case ELooseClusterPhase::Cancelled:
		return true;
	default:
		return Fail(OutReason, TEXT("loose cluster phase is invalid"));
	}
}

bool RedVoxelMining::CanTransitionLooseCluster(
	const FLooseClusterState& Current,
	const FLooseClusterState& Next,
	const FAuthorityLimits& Limits)
{
	if (!ValidateLooseClusterState(Current, Limits)
		|| !ValidateLooseClusterState(Next, Limits)
		|| !HasSameImmutableClusterIdentity(Current, Next)
		|| !IsNextRevision(Current.Revision, Next.Revision))
	{
		return false;
	}

	switch (Current.Phase)
	{
	case ELooseClusterPhase::Loose:
		return Next.Phase == ELooseClusterPhase::Reserved;
	case ELooseClusterPhase::Reserved:
		if (Next.Phase == ELooseClusterPhase::Attracting
			|| Next.Phase == ELooseClusterPhase::Cancelled)
		{
			return Next.CollectorStableId == Current.CollectorStableId
				&& Next.ReservationToken == Current.ReservationToken
				&& Next.ReservationExpiryServerTimeSeconds
					== Current.ReservationExpiryServerTimeSeconds;
		}
		return Next.Phase == ELooseClusterPhase::Loose;
	case ELooseClusterPhase::Attracting:
		if (Next.Phase == ELooseClusterPhase::Collected
			|| Next.Phase == ELooseClusterPhase::Cancelled)
		{
			return Next.CollectorStableId == Current.CollectorStableId
				&& Next.ReservationToken == Current.ReservationToken
				&& Next.ReservationExpiryServerTimeSeconds
					== Current.ReservationExpiryServerTimeSeconds
				&& Next.AttractionStartServerTimeSeconds
					== Current.AttractionStartServerTimeSeconds
				&& Next.ExpectedArrivalServerTimeSeconds
					== Current.ExpectedArrivalServerTimeSeconds;
		}
		return Next.Phase == ELooseClusterPhase::Loose;
	case ELooseClusterPhase::Collected:
	case ELooseClusterPhase::Cancelled:
	default:
		return false;
	}
}

bool RedVoxelMining::BuildInventoryCreditCommit(
	const FLooseClusterState& Current,
	const FLooseClusterState& Collected,
	const FServerSuctionArrivalEvidence& Evidence,
	const FAuthorityLimits& Limits,
	FInventoryCreditCommit& OutCommit,
	FString* OutReason)
{
	OutCommit = FInventoryCreditCommit();
	ClearReason(OutReason);
	if (Current.Phase != ELooseClusterPhase::Attracting
		|| Collected.Phase != ELooseClusterPhase::Collected
		|| !CanTransitionLooseCluster(Current, Collected, Limits)
		|| Evidence.ClusterId != Current.ClusterId
		|| Evidence.SourceAsteroidStableId != Current.SourceAsteroidStableId
		|| Evidence.CollectorStableId != Current.CollectorStableId
		|| Evidence.ReservationToken != Current.ReservationToken
		|| Evidence.ObservedClusterRevision != Current.Revision
		|| !Evidence.bCollectorEligible
		|| !Evidence.bLineOfSightClear
		|| !IsFiniteVector(Evidence.ClusterLocation)
		|| !IsFiniteVector(Evidence.CollectorLocation)
		|| !FMath::IsFinite(Evidence.ObservedServerTimeSeconds)
		|| Evidence.ObservedServerTimeSeconds < Current.AttractionStartServerTimeSeconds
		|| Evidence.ObservedServerTimeSeconds > Current.ReservationExpiryServerTimeSeconds
		|| Evidence.ObservedServerTimeSeconds
			> Current.ExpectedArrivalServerTimeSeconds
				+ Limits.MaxCollectionArrivalGraceSeconds
		|| !FMath::IsNearlyEqual(
			Evidence.ObservedServerTimeSeconds,
			Collected.CollectedServerTimeSeconds,
			1.e-4)
		|| FVector::DistSquared(
			Evidence.ClusterLocation,
			Evidence.CollectorLocation)
			> FMath::Square(Limits.MaxCollectionArrivalDistanceCm))
	{
		return Fail(OutReason, TEXT("server suction arrival evidence is missing, stale, obstructed, expired, or too far away"));
	}

	OutCommit.ClusterId = Collected.ClusterId;
	OutCommit.CollectedRevision = Collected.Revision;
	OutCommit.CollectorStableId = Collected.CollectorStableId;
	OutCommit.MaterialId = Collected.MaterialId;
	OutCommit.Amount = Collected.Amount;
	return true;
}
