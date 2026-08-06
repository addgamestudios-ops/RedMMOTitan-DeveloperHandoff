#include "RedPlanetRegionService.h"

namespace RedPlanet
{
	namespace Private
	{
		constexpr double TwoPi = 6.283185307179586476925286766559;
		constexpr double GoldenAngle = 2.3999632297286533222315555066336;
		constexpr double DirectionEpsilonSquared = 1.0e-20;

		uint32 Mix32(uint32 Value)
		{
			Value += 0x9e3779b9u;
			Value = (Value ^ (Value >> 16u)) * 0x85ebca6bu;
			Value = (Value ^ (Value >> 13u)) * 0xc2b2ae35u;
			return Value ^ (Value >> 16u);
		}

		uint32 RegionHash(const int32 RegionIndex, const uint32 Lane)
		{
			return Mix32(FPlanet50KmProfile::LayoutSeed
				^ (static_cast<uint32>(RegionIndex) * 0x9e3779b9u)
				^ (Lane * 0x85ebca6bu));
		}

		double UnitFloat(const int32 RegionIndex, const uint32 Lane)
		{
			// Use exactly 24 high-quality bits so results remain identical across float modes.
			return static_cast<double>(RegionHash(RegionIndex, Lane) & 0x00ffffffu) / 16777215.0;
		}

		FVector3d NormalizeOrNorth(const FVector3d& Direction)
		{
			return Direction.SquaredLength() > DirectionEpsilonSquared
				? Direction.GetSafeNormal()
				: FVector3d(0.0, 0.0, 1.0);
		}
	}

	bool FPlanet50KmProfile::IsInternallyConsistent(const double ToleranceCm)
	{
		return FMath::Abs((RadiusCm * Private::TwoPi) - CircumferenceCm) <= FMath::Max(0.0, ToleranceCm)
			&& RegionCount > 0
			&& MinAuthoringHubRadiusCm > 0.0
			&& MaxAuthoringHubRadiusCm >= MinAuthoringHubRadiusCm;
	}

	const FPlanetRegionService& FPlanetRegionService::Get()
	{
		static const FPlanetRegionService Instance;
		return Instance;
	}

	FPlanetRegionService::FPlanetRegionService()
	{
		const double PhaseRadians = Private::UnitFloat(0, 99u) * Private::TwoPi;

		for (int32 RegionIndex = 0; RegionIndex < FPlanet50KmProfile::RegionCount; ++RegionIndex)
		{
			// Half-step sampling avoids putting sites directly on the pole and gives all hubs a
			// well-defined local tangent heading.
			const double Fraction = (static_cast<double>(RegionIndex) + 0.5)
				/ static_cast<double>(FPlanet50KmProfile::RegionCount);
			const double Z = 1.0 - (2.0 * Fraction);
			const double RingRadius = FMath::Sqrt(FMath::Max(0.0, 1.0 - (Z * Z)));
			const double Longitude = PhaseRadians + (Private::GoldenAngle * RegionIndex);

			FPlanetRegionMetadata& Region = Regions[RegionIndex];
			Region.RegionIndex = RegionIndex;
			Region.StableSeed = Private::RegionHash(RegionIndex, 0u);
			Region.VariationIndex = static_cast<uint8>(Private::RegionHash(RegionIndex, 1u) % 4u);
			Region.UnitSite = FVector3d(
				RingRadius * FMath::Cos(Longitude),
				RingRadius * FMath::Sin(Longitude),
				Z);

			// Cycling before variation guarantees that all seven art-bible families occur three or
			// four times instead of leaving their representation to chance.
			const int32 ArchetypeOffset = static_cast<int32>(FPlanet50KmProfile::LayoutSeed % 7u);
			Region.Archetype = static_cast<ERegionArchetype>((RegionIndex + ArchetypeOffset) % 7);
			Region.NominalAreaSquareKm = FPlanet50KmProfile::AverageRegionAreaSquareKm;

			const double HubAlpha = Private::UnitFloat(RegionIndex, 2u);
			Region.SuggestedHubRadiusCm = FMath::Lerp(
				FPlanet50KmProfile::MinAuthoringHubRadiusCm,
				FPlanet50KmProfile::MaxAuthoringHubRadiusCm,
				HubAlpha);
			Region.SuggestedFlattenCoreRadiusCm = Region.SuggestedHubRadiusCm * 0.60;
			Region.SuggestedFlattenBlendRadiusCm = Region.SuggestedHubRadiusCm * 0.40;

			const double EquatorWarmth = 1.0 - FMath::Abs(Z);
			Region.Temperature01 = static_cast<float>(FMath::Clamp(
				(EquatorWarmth * 0.75) + (Private::UnitFloat(RegionIndex, 3u) * 0.25), 0.0, 1.0));
			Region.Moisture01 = static_cast<float>(Private::UnitFloat(RegionIndex, 4u));
			Region.AlienIntensity01 = static_cast<float>(
				0.55 + (Private::UnitFloat(RegionIndex, 5u) * 0.45));
			Region.ElevationBias = static_cast<float>(
				-0.35 + (Private::UnitFloat(RegionIndex, 6u) * 0.70));
		}
	}

	const TStaticArray<FPlanetRegionMetadata, FPlanet50KmProfile::RegionCount>&
	FPlanetRegionService::GetRegions() const
	{
		return Regions;
	}

	const FPlanetRegionMetadata& FPlanetRegionService::GetRegionChecked(const int32 RegionIndex) const
	{
		checkf(
			RegionIndex >= 0 && RegionIndex < FPlanet50KmProfile::RegionCount,
			TEXT("Invalid RED planet region index: %d"),
			RegionIndex);
		return Regions[RegionIndex];
	}

	int32 FPlanetRegionService::FindNearestRegion(const FVector3d& SurfaceDirection) const
	{
		const FVector3d QueryDirection = Private::NormalizeOrNorth(SurfaceDirection);
		int32 BestIndex = 0;
		double BestDot = -2.0;

		for (const FPlanetRegionMetadata& Region : Regions)
		{
			const double Dot = FVector3d::DotProduct(QueryDirection, Region.UnitSite);
			if (Dot > BestDot)
			{
				BestDot = Dot;
				BestIndex = Region.RegionIndex;
			}
		}

		return BestIndex;
	}

	FPlanetRegionBlend FPlanetRegionService::SampleBlendedRegions(
		const FVector3d& SurfaceDirection,
		const int32 MaxContributors,
		const double SigmaRadians) const
	{
		FPlanetRegionBlend Result;
		const FVector3d QueryDirection = Private::NormalizeOrNorth(SurfaceDirection);
		const int32 ContributorLimit = FMath::Clamp(
			MaxContributors, 1, FPlanetRegionBlend::MaxContributors);

		TStaticArray<int32, FPlanetRegionBlend::MaxContributors> BestIndices;
		TStaticArray<double, FPlanetRegionBlend::MaxContributors> BestDistances;
		for (int32 Slot = 0; Slot < FPlanetRegionBlend::MaxContributors; ++Slot)
		{
			BestIndices[Slot] = INDEX_NONE;
			BestDistances[Slot] = TNumericLimits<double>::Max();
		}

		// Small fixed insertion set avoids a heap allocation or sorting all 27 sites per query.
		for (const FPlanetRegionMetadata& Region : Regions)
		{
			const double Distance = GreatCircleDistanceRadians(QueryDirection, Region.UnitSite);
			for (int32 Slot = 0; Slot < ContributorLimit; ++Slot)
			{
				if (Distance < BestDistances[Slot])
				{
					for (int32 Shift = ContributorLimit - 1; Shift > Slot; --Shift)
					{
						BestDistances[Shift] = BestDistances[Shift - 1];
						BestIndices[Shift] = BestIndices[Shift - 1];
					}
					BestDistances[Slot] = Distance;
					BestIndices[Slot] = Region.RegionIndex;
					break;
				}
			}
		}

		const double SafeSigma = FMath::Max(SigmaRadians, 1.0e-6);
		const double InverseTwoSigmaSquared = 1.0 / (2.0 * SafeSigma * SafeSigma);
		const double NearestDistanceSquared = BestDistances[0] * BestDistances[0];
		double WeightSum = 0.0;

		for (int32 Slot = 0; Slot < ContributorLimit && BestIndices[Slot] != INDEX_NONE; ++Slot)
		{
			FPlanetRegionWeight& Contributor = Result.Contributors[Result.NumContributors++];
			Contributor.RegionIndex = BestIndices[Slot];
			Contributor.GreatCircleDistanceRadians = BestDistances[Slot];
			// Subtracting the nearest exponent keeps the dominant weight at exactly one before
			// normalization and avoids underflow for narrow authoring blends.
			const double DistanceSquared = BestDistances[Slot] * BestDistances[Slot];
			Contributor.Weight = FMath::Exp(
				-(DistanceSquared - NearestDistanceSquared) * InverseTwoSigmaSquared);
			WeightSum += Contributor.Weight;
		}

		if (WeightSum > UE_DOUBLE_SMALL_NUMBER)
		{
			for (int32 Slot = 0; Slot < Result.NumContributors; ++Slot)
			{
				Result.Contributors[Slot].Weight /= WeightSum;
			}
		}

		return Result;
	}

	double FPlanetRegionService::GreatCircleDistanceRadians(const FVector3d& A, const FVector3d& B)
	{
		const FVector3d UnitA = Private::NormalizeOrNorth(A);
		const FVector3d UnitB = Private::NormalizeOrNorth(B);
		return FMath::Acos(FMath::Clamp(FVector3d::DotProduct(UnitA, UnitB), -1.0, 1.0));
	}

	FPlanetTangentFrame FPlanetRegionService::MakeTangentFrame(
		const FVector3d& SurfaceDirection,
		const FVector3d& PlanetNorthAxis)
	{
		FPlanetTangentFrame Frame;
		Frame.UnitUp = Private::NormalizeOrNorth(SurfaceDirection);
		const FVector3d NorthAxis = Private::NormalizeOrNorth(PlanetNorthAxis);
		FVector3d NorthTangent = NorthAxis
			- (Frame.UnitUp * FVector3d::DotProduct(NorthAxis, Frame.UnitUp));

		if (NorthTangent.SquaredLength() <= Private::DirectionEpsilonSquared)
		{
			const FVector3d FallbackAxis = FMath::Abs(Frame.UnitUp.X) < 0.9
				? FVector3d(1.0, 0.0, 0.0)
				: FVector3d(0.0, 1.0, 0.0);
			NorthTangent = FallbackAxis
				- (Frame.UnitUp * FVector3d::DotProduct(FallbackAxis, Frame.UnitUp));
		}

		Frame.UnitNorth = NorthTangent.GetSafeNormal();
		Frame.UnitEast = FVector3d::CrossProduct(Frame.UnitNorth, Frame.UnitUp).GetSafeNormal();
		Frame.UnitNorth = FVector3d::CrossProduct(Frame.UnitUp, Frame.UnitEast).GetSafeNormal();
		return Frame;
	}

	FVector3d FPlanetRegionService::ExpMapDirection(
		const FVector3d& AnchorSurfaceDirection,
		const FVector2d& LocalOffsetCm,
		const double PlanetRadiusCm,
		const FVector3d& PlanetNorthAxis)
	{
		const FPlanetTangentFrame Frame = MakeTangentFrame(AnchorSurfaceDirection, PlanetNorthAxis);
		const FVector3d Tangent = (Frame.UnitEast * LocalOffsetCm.X)
			+ (Frame.UnitNorth * LocalOffsetCm.Y);
		const double ArcLengthCm = Tangent.Length();
		if (ArcLengthCm <= UE_DOUBLE_SMALL_NUMBER || PlanetRadiusCm <= UE_DOUBLE_SMALL_NUMBER)
		{
			return Frame.UnitUp;
		}

		const double AngleRadians = ArcLengthCm / PlanetRadiusCm;
		double SinAngle = 0.0;
		double CosAngle = 1.0;
		FMath::SinCos(&SinAngle, &CosAngle, AngleRadians);
		return ((Frame.UnitUp * CosAngle) + ((Tangent / ArcLengthCm) * SinAngle)).GetSafeNormal();
	}

	FVector3d FPlanetRegionService::ExpMapPosition(
		const FVector3d& PlanetCenter,
		const FVector3d& AnchorSurfaceDirection,
		const FVector2d& LocalOffsetCm,
		const double AltitudeCm,
		const double PlanetRadiusCm,
		const FVector3d& PlanetNorthAxis)
	{
		const FVector3d SurfaceDirection = ExpMapDirection(
			AnchorSurfaceDirection, LocalOffsetCm, PlanetRadiusCm, PlanetNorthAxis);
		return PlanetCenter + (SurfaceDirection * FMath::Max(0.0, PlanetRadiusCm + AltitudeCm));
	}

	FVector2d FPlanetRegionService::LogMapOffsetCm(
		const FVector3d& AnchorSurfaceDirection,
		const FVector3d& TargetSurfaceDirection,
		const double PlanetRadiusCm,
		const FVector3d& PlanetNorthAxis)
	{
		const FPlanetTangentFrame Frame = MakeTangentFrame(AnchorSurfaceDirection, PlanetNorthAxis);
		const FVector3d Target = Private::NormalizeOrNorth(TargetSurfaceDirection);
		const double Dot = FMath::Clamp(FVector3d::DotProduct(Frame.UnitUp, Target), -1.0, 1.0);
		const double AngleRadians = FMath::Acos(Dot);
		if (AngleRadians <= UE_DOUBLE_SMALL_NUMBER || PlanetRadiusCm <= UE_DOUBLE_SMALL_NUMBER)
		{
			return FVector2d::ZeroVector;
		}

		FVector3d TangentDirection = Target - (Frame.UnitUp * Dot);
		if (TangentDirection.SquaredLength() <= Private::DirectionEpsilonSquared)
		{
			// The logarithmic map is directionally ambiguous at the antipode. East is a stable,
			// documented fallback so authoring tools do not emit NaNs.
			TangentDirection = Frame.UnitEast;
		}
		else
		{
			TangentDirection.Normalize();
		}

		const double ArcLengthCm = AngleRadians * PlanetRadiusCm;
		return FVector2d(
			FVector3d::DotProduct(TangentDirection, Frame.UnitEast) * ArcLengthCm,
			FVector3d::DotProduct(TangentDirection, Frame.UnitNorth) * ArcLengthCm);
	}
}
