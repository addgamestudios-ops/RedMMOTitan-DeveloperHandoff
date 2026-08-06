#include "RedPlanetMacroHeightmap.h"

namespace RedPlanet
{
	namespace MacroHeightmapPrivate
	{
		constexpr double DirectionToleranceSquared = 1.0e-24;
		constexpr double MaxChannelValue = 65535.0;
		constexpr double QuarterPi = 0.78539816339744830961566084581988;
		constexpr double FourOverPi = 1.2732395447351626861510701069801;

		int32 FaceToIndex(EPlanetCubeFace Face)
		{
			return static_cast<int32>(Face);
		}

		bool IsFinite(const FVector3d& Value)
		{
			return FMath::IsFinite(Value.X)
				&& FMath::IsFinite(Value.Y)
				&& FMath::IsFinite(Value.Z);
		}

		bool IsFinite(const FVector2d& Value)
		{
			return FMath::IsFinite(Value.X) && FMath::IsFinite(Value.Y);
		}

		double BilerpChannel(
			uint16 C00,
			uint16 C10,
			uint16 C01,
			uint16 C11,
			double FractionX,
			double FractionY)
		{
			const double Row0 = FMath::Lerp(static_cast<double>(C00), static_cast<double>(C10), FractionX);
			const double Row1 = FMath::Lerp(static_cast<double>(C01), static_cast<double>(C11), FractionX);
			return FMath::Lerp(Row0, Row1, FractionY) / MaxChannelValue;
		}

		FIntVector ToIntegerAxis(const FVector3d& Axis)
		{
			return FIntVector(
				FMath::RoundToInt(Axis.X),
				FMath::RoundToInt(Axis.Y),
				FMath::RoundToInt(Axis.Z));
		}

		FIntVector MakeBorderKey(
			EPlanetCubeFace Face,
			int32 X,
			int32 Y,
			int32 Resolution)
		{
			const int32 Span = Resolution - 1;
			const int32 ScaledU = (2 * X) - Span;
			const int32 ScaledV = (2 * Y) - Span;
			const FIntVector Normal = ToIntegerAxis(FPlanetCubeTopology::GetFaceNormal(Face));
			const FIntVector UAxis = ToIntegerAxis(FPlanetCubeTopology::GetFaceUAxis(Face));
			const FIntVector VAxis = ToIntegerAxis(FPlanetCubeTopology::GetFaceVAxis(Face));

			return FIntVector(
				(Normal.X * Span) + (UAxis.X * ScaledU) + (VAxis.X * ScaledV),
				(Normal.Y * Span) + (UAxis.Y * ScaledU) + (VAxis.Y * ScaledV),
				(Normal.Z * Span) + (UAxis.Z * ScaledU) + (VAxis.Z * ScaledV));
		}

		struct FBorderAccumulator
		{
			uint64 ElevationSum = 0;
			uint64 LandSum = 0;
			uint64 BiomeSum = 0;
			uint32 Count = 0;
		};
	}

	bool FPlanetCubeTopology::TryDirectionToFaceUV(
		const FVector3d& Direction,
		FPlanetCubeFaceAddress& OutAddress)
	{
		OutAddress = FPlanetCubeFaceAddress{};
		if (!MacroHeightmapPrivate::IsFinite(Direction)
			|| Direction.SquaredLength() <= MacroHeightmapPrivate::DirectionToleranceSquared)
		{
			return false;
		}

		const FVector3d UnitDirection = Direction.GetSafeNormal();
		const double AbsX = FMath::Abs(UnitDirection.X);
		const double AbsY = FMath::Abs(UnitDirection.Y);
		const double AbsZ = FMath::Abs(UnitDirection.Z);

		// Deliberate >= ordering is the stable edge/corner tie breaker documented in the header.
		if (AbsX >= AbsY && AbsX >= AbsZ)
		{
			OutAddress.Face = UnitDirection.X >= 0.0
				? EPlanetCubeFace::PositiveX
				: EPlanetCubeFace::NegativeX;
		}
		else if (AbsY >= AbsZ)
		{
			OutAddress.Face = UnitDirection.Y >= 0.0
				? EPlanetCubeFace::PositiveY
				: EPlanetCubeFace::NegativeY;
		}
		else
		{
			OutAddress.Face = UnitDirection.Z >= 0.0
				? EPlanetCubeFace::PositiveZ
				: EPlanetCubeFace::NegativeZ;
		}

		const FVector3d Normal = GetFaceNormal(OutAddress.Face);
		const double Denominator = FVector3d::DotProduct(UnitDirection, Normal);
		if (!FMath::IsFinite(Denominator) || Denominator <= 0.0)
		{
			return false;
		}

		const double TangentU = FMath::Clamp(
			FVector3d::DotProduct(UnitDirection, GetFaceUAxis(OutAddress.Face)) / Denominator,
			-1.0,
			1.0);
		const double TangentV = FMath::Clamp(
			FVector3d::DotProduct(UnitDirection, GetFaceVAxis(OutAddress.Face)) / Denominator,
			-1.0,
			1.0);
		const double FaceU = FMath::Atan(TangentU) * MacroHeightmapPrivate::FourOverPi;
		const double FaceV = FMath::Atan(TangentV) * MacroHeightmapPrivate::FourOverPi;

		OutAddress.UV01 = FVector2d((FaceU + 1.0) * 0.5, (FaceV + 1.0) * 0.5);
		OutAddress.bIsValid = MacroHeightmapPrivate::IsFinite(OutAddress.UV01);
		return OutAddress.bIsValid;
	}

	FVector3d FPlanetCubeTopology::FaceUVToDirection(
		EPlanetCubeFace Face,
		const FVector2d& UV01)
	{
		if (!IsValidFace(Face) || !MacroHeightmapPrivate::IsFinite(UV01))
		{
			return FVector3d::ZeroVector;
		}

		const double SignedU = (FMath::Clamp(UV01.X, 0.0, 1.0) * 2.0) - 1.0;
		const double SignedV = (FMath::Clamp(UV01.Y, 0.0, 1.0) * 2.0) - 1.0;
		const double TangentU = FMath::Tan(SignedU * MacroHeightmapPrivate::QuarterPi);
		const double TangentV = FMath::Tan(SignedV * MacroHeightmapPrivate::QuarterPi);
		return (GetFaceNormal(Face)
			+ (GetFaceUAxis(Face) * TangentU)
			+ (GetFaceVAxis(Face) * TangentV)).GetSafeNormal();
	}

	FVector3d FPlanetCubeTopology::GetFaceNormal(EPlanetCubeFace Face)
	{
		switch (Face)
		{
		case EPlanetCubeFace::PositiveX: return FVector3d(1.0, 0.0, 0.0);
		case EPlanetCubeFace::NegativeX: return FVector3d(-1.0, 0.0, 0.0);
		case EPlanetCubeFace::PositiveY: return FVector3d(0.0, 1.0, 0.0);
		case EPlanetCubeFace::NegativeY: return FVector3d(0.0, -1.0, 0.0);
		case EPlanetCubeFace::PositiveZ: return FVector3d(0.0, 0.0, 1.0);
		case EPlanetCubeFace::NegativeZ: return FVector3d(0.0, 0.0, -1.0);
		default: return FVector3d::ZeroVector;
		}
	}

	FVector3d FPlanetCubeTopology::GetFaceUAxis(EPlanetCubeFace Face)
	{
		switch (Face)
		{
		case EPlanetCubeFace::PositiveX: return FVector3d(0.0, 1.0, 0.0);
		case EPlanetCubeFace::NegativeX: return FVector3d(0.0, -1.0, 0.0);
		case EPlanetCubeFace::PositiveY: return FVector3d(-1.0, 0.0, 0.0);
		case EPlanetCubeFace::NegativeY: return FVector3d(1.0, 0.0, 0.0);
		case EPlanetCubeFace::PositiveZ: return FVector3d(1.0, 0.0, 0.0);
		case EPlanetCubeFace::NegativeZ: return FVector3d(1.0, 0.0, 0.0);
		default: return FVector3d::ZeroVector;
		}
	}

	FVector3d FPlanetCubeTopology::GetFaceVAxis(EPlanetCubeFace Face)
	{
		switch (Face)
		{
		case EPlanetCubeFace::PositiveX: return FVector3d(0.0, 0.0, 1.0);
		case EPlanetCubeFace::NegativeX: return FVector3d(0.0, 0.0, 1.0);
		case EPlanetCubeFace::PositiveY: return FVector3d(0.0, 0.0, 1.0);
		case EPlanetCubeFace::NegativeY: return FVector3d(0.0, 0.0, 1.0);
		case EPlanetCubeFace::PositiveZ: return FVector3d(0.0, 1.0, 0.0);
		case EPlanetCubeFace::NegativeZ: return FVector3d(0.0, -1.0, 0.0);
		default: return FVector3d::ZeroVector;
		}
	}

	bool FPlanetCubeTopology::IsValidFace(EPlanetCubeFace Face)
	{
		const int32 FaceIndex = MacroHeightmapPrivate::FaceToIndex(Face);
		return FaceIndex >= 0 && FaceIndex < MacroCubeFaceCount;
	}

	bool FPlanetMacroHeightGrid::Initialize(
		int32 InResolution,
		const FPlanetMacroTexel16& Fill)
	{
		const int64 TexelCount = static_cast<int64>(InResolution) * static_cast<int64>(InResolution);
		if (InResolution < 2 || TexelCount > MAX_int32)
		{
			Reset();
			return false;
		}

		Resolution = InResolution;
		Texels.Init(Fill, static_cast<int32>(TexelCount));
		return true;
	}

	void FPlanetMacroHeightGrid::Reset()
	{
		Resolution = 0;
		Texels.Reset();
	}

	bool FPlanetMacroHeightGrid::IsValid() const
	{
		return Resolution >= 2
			&& Texels.Num() == static_cast<int64>(Resolution) * static_cast<int64>(Resolution);
	}

	bool FPlanetMacroHeightGrid::SetTexel(
		int32 X,
		int32 Y,
		const FPlanetMacroTexel16& Texel)
	{
		if (!IsValid() || X < 0 || X >= Resolution || Y < 0 || Y >= Resolution)
		{
			return false;
		}

		Texels[(Y * Resolution) + X] = Texel;
		return true;
	}

	const FPlanetMacroTexel16& FPlanetMacroHeightGrid::GetTexelChecked(int32 X, int32 Y) const
	{
		check(IsValid());
		check(X >= 0 && X < Resolution && Y >= 0 && Y < Resolution);
		return Texels[(Y * Resolution) + X];
	}

	FPlanetMacroTexel16& FPlanetMacroHeightGrid::GetTexelChecked(int32 X, int32 Y)
	{
		check(IsValid());
		check(X >= 0 && X < Resolution && Y >= 0 && Y < Resolution);
		return Texels[(Y * Resolution) + X];
	}

	FPlanetMacroSample FPlanetMacroHeightGrid::SampleBilinear(const FVector2d& UV01) const
	{
		FPlanetMacroSample Result;
		if (!IsValid() || !MacroHeightmapPrivate::IsFinite(UV01))
		{
			return Result;
		}

		const double GridX = FMath::Clamp(UV01.X, 0.0, 1.0) * (Resolution - 1);
		const double GridY = FMath::Clamp(UV01.Y, 0.0, 1.0) * (Resolution - 1);
		const int32 X0 = FMath::FloorToInt(GridX);
		const int32 Y0 = FMath::FloorToInt(GridY);
		const int32 X1 = FMath::Min(X0 + 1, Resolution - 1);
		const int32 Y1 = FMath::Min(Y0 + 1, Resolution - 1);
		const double FractionX = GridX - X0;
		const double FractionY = GridY - Y0;

		const FPlanetMacroTexel16& C00 = GetTexelChecked(X0, Y0);
		const FPlanetMacroTexel16& C10 = GetTexelChecked(X1, Y0);
		const FPlanetMacroTexel16& C01 = GetTexelChecked(X0, Y1);
		const FPlanetMacroTexel16& C11 = GetTexelChecked(X1, Y1);

		Result.Elevation01 = static_cast<float>(MacroHeightmapPrivate::BilerpChannel(
			C00.Elevation01, C10.Elevation01, C01.Elevation01, C11.Elevation01,
			FractionX, FractionY));
		Result.LandMask01 = static_cast<float>(MacroHeightmapPrivate::BilerpChannel(
			C00.LandMask01, C10.LandMask01, C01.LandMask01, C11.LandMask01,
			FractionX, FractionY));
		Result.BiomeMask01 = static_cast<float>(MacroHeightmapPrivate::BilerpChannel(
			C00.BiomeMask01, C10.BiomeMask01, C01.BiomeMask01, C11.BiomeMask01,
			FractionX, FractionY));
		Result.SourceUV01 = FVector2d(
			FMath::Clamp(UV01.X, 0.0, 1.0),
			FMath::Clamp(UV01.Y, 0.0, 1.0));
		Result.bIsValid = true;
		return Result;
	}

	bool FPlanetMacroHeightmap::Initialize(
		int32 FaceResolution,
		const FPlanetMacroTexel16& Fill)
	{
		Reset();
		for (FPlanetMacroHeightGrid& Face : Faces)
		{
			if (!Face.Initialize(FaceResolution, Fill))
			{
				Reset();
				return false;
			}
		}
		return true;
	}

	void FPlanetMacroHeightmap::Reset()
	{
		for (FPlanetMacroHeightGrid& Face : Faces)
		{
			Face.Reset();
		}
	}

	bool FPlanetMacroHeightmap::IsValid() const
	{
		const int32 ExpectedResolution = Faces[0].GetResolution();
		if (ExpectedResolution < 2)
		{
			return false;
		}

		for (const FPlanetMacroHeightGrid& Face : Faces)
		{
			if (!Face.IsValid() || Face.GetResolution() != ExpectedResolution)
			{
				return false;
			}
		}
		return true;
	}

	int32 FPlanetMacroHeightmap::GetResolution() const
	{
		return IsValid() ? Faces[0].GetResolution() : 0;
	}

	const FPlanetMacroHeightGrid& FPlanetMacroHeightmap::GetFaceChecked(EPlanetCubeFace Face) const
	{
		check(FPlanetCubeTopology::IsValidFace(Face));
		return Faces[MacroHeightmapPrivate::FaceToIndex(Face)];
	}

	FPlanetMacroHeightGrid& FPlanetMacroHeightmap::GetFaceChecked(EPlanetCubeFace Face)
	{
		check(FPlanetCubeTopology::IsValidFace(Face));
		return Faces[MacroHeightmapPrivate::FaceToIndex(Face)];
	}

	FPlanetMacroSample FPlanetMacroHeightmap::SampleDirection(const FVector3d& Direction) const
	{
		FPlanetMacroSample Result;
		if (!IsValid())
		{
			return Result;
		}

		FPlanetCubeFaceAddress Address;
		if (!FPlanetCubeTopology::TryDirectionToFaceUV(Direction, Address))
		{
			return Result;
		}

		Result = GetFaceChecked(Address.Face).SampleBilinear(Address.UV01);
		Result.SourceFace = Address.Face;
		Result.SourceUV01 = Address.UV01;
		return Result;
	}

	bool FPlanetMacroHeightmap::FuseSharedBorders()
	{
		if (!IsValid())
		{
			return false;
		}

		const int32 Resolution = GetResolution();
		TMap<FIntVector, MacroHeightmapPrivate::FBorderAccumulator> Accumulators;

		for (int32 FaceIndex = 0; FaceIndex < MacroCubeFaceCount; ++FaceIndex)
		{
			const EPlanetCubeFace Face = static_cast<EPlanetCubeFace>(FaceIndex);
			const FPlanetMacroHeightGrid& Grid = Faces[FaceIndex];
			for (int32 Y = 0; Y < Resolution; ++Y)
			{
				for (int32 X = 0; X < Resolution; ++X)
				{
					if (X != 0 && X != Resolution - 1 && Y != 0 && Y != Resolution - 1)
					{
						continue;
					}

					const FIntVector Key = MacroHeightmapPrivate::MakeBorderKey(
						Face, X, Y, Resolution);
					const FPlanetMacroTexel16& Texel = Grid.GetTexelChecked(X, Y);
					MacroHeightmapPrivate::FBorderAccumulator& Accumulator = Accumulators.FindOrAdd(Key);
					Accumulator.ElevationSum += Texel.Elevation01;
					Accumulator.LandSum += Texel.LandMask01;
					Accumulator.BiomeSum += Texel.BiomeMask01;
					++Accumulator.Count;
				}
			}
		}

		for (int32 FaceIndex = 0; FaceIndex < MacroCubeFaceCount; ++FaceIndex)
		{
			const EPlanetCubeFace Face = static_cast<EPlanetCubeFace>(FaceIndex);
			FPlanetMacroHeightGrid& Grid = Faces[FaceIndex];
			for (int32 Y = 0; Y < Resolution; ++Y)
			{
				for (int32 X = 0; X < Resolution; ++X)
				{
					if (X != 0 && X != Resolution - 1 && Y != 0 && Y != Resolution - 1)
					{
						continue;
					}

					const FIntVector Key = MacroHeightmapPrivate::MakeBorderKey(
						Face, X, Y, Resolution);
					const MacroHeightmapPrivate::FBorderAccumulator* Accumulator = Accumulators.Find(Key);
					if (Accumulator == nullptr || Accumulator->Count == 0)
					{
						return false;
					}

					const uint64 HalfCount = Accumulator->Count / 2;
					FPlanetMacroTexel16& Texel = Grid.GetTexelChecked(X, Y);
					Texel.Elevation01 = static_cast<uint16>(
						(Accumulator->ElevationSum + HalfCount) / Accumulator->Count);
					Texel.LandMask01 = static_cast<uint16>(
						(Accumulator->LandSum + HalfCount) / Accumulator->Count);
					Texel.BiomeMask01 = static_cast<uint16>(
						(Accumulator->BiomeSum + HalfCount) / Accumulator->Count);
				}
			}
		}

		return true;
	}
}
