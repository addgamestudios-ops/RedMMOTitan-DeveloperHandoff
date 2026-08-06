#include "RedPlanetRegionService.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Containers/Set.h"
#include "Misc/AutomationTest.h"

namespace RedPlanet::Tests
{
	namespace Private
	{
		constexpr double ScalarTolerance = 1.0e-10;
		constexpr double UnitVectorTolerance = 1.0e-12;
		constexpr double RoundTripToleranceCm = 1.0;
		constexpr double Pi = 3.1415926535897932384626433832795;

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
	}

	IMPLEMENT_SIMPLE_AUTOMATION_TEST(
		FRedPlanetRegionServiceTest,
		"RedMMO.Planet.RegionService.DeterministicGeometry",
		EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

	bool FRedPlanetRegionServiceTest::RunTest(const FString& Parameters)
	{
		(void)Parameters;

		const FPlanetRegionService& Service = FPlanetRegionService::Get();
		const auto& Regions = Service.GetRegions();

		// Profile invariants protect the shared 50 km contract from partially updated constants.
		TestTrue(TEXT("The 50 km profile is internally consistent"),
			FPlanet50KmProfile::IsInternallyConsistent());
		TestEqual(TEXT("The profile has exactly 27 regions"),
			FPlanet50KmProfile::RegionCount, 27);
		TestTrue(TEXT("Diameter is exactly twice the radius"),
			FMath::Abs(FPlanet50KmProfile::DiameterCm
				- (2.0 * FPlanet50KmProfile::RadiusCm)) <= Private::ScalarTolerance);
		TestTrue(TEXT("Gravity radius is exactly twice the surface radius"),
			FMath::Abs(FPlanet50KmProfile::GravityRadiusCm
				- (2.0 * FPlanet50KmProfile::RadiusCm)) <= Private::ScalarTolerance);
		TestTrue(TEXT("Average region area covers the declared surface area"),
			FMath::Abs((FPlanet50KmProfile::AverageRegionAreaSquareKm
				* FPlanet50KmProfile::RegionCount)
				- FPlanet50KmProfile::SurfaceAreaSquareKm) <= Private::ScalarTolerance);
		TestTrue(TEXT("Smoke-test terrain height range is ordered"),
			FPlanet50KmProfile::SmokeTestMinTerrainHeightCm
				< FPlanet50KmProfile::SmokeTestMaxTerrainHeightCm);
		TestTrue(TEXT("Smoke-test sea level is normalized"),
			FPlanet50KmProfile::SmokeTestSeaLevel01 >= 0.0
				&& FPlanet50KmProfile::SmokeTestSeaLevel01 <= 1.0);
		TestTrue(TEXT("Authoring hub radius range is valid"),
			FPlanet50KmProfile::MinAuthoringHubRadiusCm > 0.0
				&& FPlanet50KmProfile::MaxAuthoringHubRadiusCm
					>= FPlanet50KmProfile::MinAuthoringHubRadiusCm);

		TestEqual(TEXT("Region array contains exactly the profile region count"),
			Regions.Num(), FPlanet50KmProfile::RegionCount);

		TSet<int32> UniqueIndices;
		TSet<uint32> UniqueSeeds;
		int32 UniqueSiteCount = 0;

		for (int32 RegionSlot = 0; RegionSlot < Regions.Num(); ++RegionSlot)
		{
			const FPlanetRegionMetadata& Region = Regions[RegionSlot];
			const FString Prefix = FString::Printf(TEXT("Region %d: "), RegionSlot);

			TestTrue(Prefix + TEXT("index is in range"),
				Region.RegionIndex >= 0 && Region.RegionIndex < FPlanet50KmProfile::RegionCount);
			UniqueIndices.Add(Region.RegionIndex);
			UniqueSeeds.Add(Region.StableSeed);

			TestTrue(Prefix + TEXT("site is finite"), Private::IsFinite(Region.UnitSite));
			TestTrue(Prefix + TEXT("site is a unit vector"),
				FMath::Abs(Region.UnitSite.Length() - 1.0) <= Private::UnitVectorTolerance);

			bool bSiteIsUnique = true;
			for (int32 PreviousSlot = 0; PreviousSlot < RegionSlot; ++PreviousSlot)
			{
				if ((Region.UnitSite - Regions[PreviousSlot].UnitSite).SquaredLength()
					<= Private::UnitVectorTolerance)
				{
					bSiteIsUnique = false;
					break;
				}
			}
			if (bSiteIsUnique)
			{
				++UniqueSiteCount;
			}

			TestEqual(Prefix + TEXT("its own site resolves to itself"),
				Service.FindNearestRegion(Region.UnitSite), Region.RegionIndex);

			const FPlanetRegionBlend Blend = Service.SampleBlendedRegions(
				Region.UnitSite, FPlanetRegionBlend::MaxContributors, 0.20);
			TestEqual(Prefix + TEXT("four-way blend has four contributors"),
				Blend.NumContributors, FPlanetRegionBlend::MaxContributors);
			TestTrue(Prefix + TEXT("dominant contributor exists"), Blend.GetDominant() != nullptr);
			if (Blend.GetDominant() != nullptr)
			{
				TestEqual(Prefix + TEXT("dominant contributor is the site's region"),
					Blend.GetDominant()->RegionIndex, Region.RegionIndex);
			}

			TSet<int32> BlendIndices;
			double WeightSum = 0.0;
			for (int32 ContributorSlot = 0;
				ContributorSlot < Blend.NumContributors;
				++ContributorSlot)
			{
				const FPlanetRegionWeight& Contributor = Blend.Contributors[ContributorSlot];
				const FString ContributorPrefix = Prefix + FString::Printf(
					TEXT("blend contributor %d: "), ContributorSlot);

				TestTrue(ContributorPrefix + TEXT("region index is valid"),
					Contributor.RegionIndex >= 0
						&& Contributor.RegionIndex < FPlanet50KmProfile::RegionCount);
				TestTrue(ContributorPrefix + TEXT("distance is finite and valid"),
					FMath::IsFinite(Contributor.GreatCircleDistanceRadians)
						&& Contributor.GreatCircleDistanceRadians >= 0.0
						&& Contributor.GreatCircleDistanceRadians <= Private::Pi);
				TestTrue(ContributorPrefix + TEXT("weight is finite and normalized"),
					FMath::IsFinite(Contributor.Weight)
						&& Contributor.Weight >= 0.0
						&& Contributor.Weight <= 1.0);

				if (ContributorSlot > 0)
				{
					const FPlanetRegionWeight& Previous = Blend.Contributors[ContributorSlot - 1];
					TestTrue(ContributorPrefix + TEXT("contributors are sorted nearest-first"),
						Contributor.GreatCircleDistanceRadians + Private::ScalarTolerance
							>= Previous.GreatCircleDistanceRadians);
					TestTrue(ContributorPrefix + TEXT("weights are sorted dominant-first"),
						Contributor.Weight <= Previous.Weight + Private::ScalarTolerance);
				}

				BlendIndices.Add(Contributor.RegionIndex);
				WeightSum += Contributor.Weight;
			}

			TestEqual(Prefix + TEXT("blend contributor indices are unique"),
				BlendIndices.Num(), Blend.NumContributors);
			TestTrue(Prefix + TEXT("four-way blend weights sum to one"),
				FMath::Abs(WeightSum - 1.0) <= Private::ScalarTolerance);
		}

		TestEqual(TEXT("All 27 region indices are unique"),
			UniqueIndices.Num(), FPlanet50KmProfile::RegionCount);
		TestEqual(TEXT("All 27 stable seeds are unique"),
			UniqueSeeds.Num(), FPlanet50KmProfile::RegionCount);
		TestEqual(TEXT("All 27 unit sites are unique"),
			UniqueSiteCount, FPlanet50KmProfile::RegionCount);

		const FVector3d FrameDirections[] =
		{
			FVector3d(0.0, 0.0, 1.0),
			FVector3d(0.0, 0.0, -1.0),
			FVector3d(1.0, 0.0, 0.0),
			FVector3d(1.0, 2.0, 3.0).GetSafeNormal(),
			FVector3d(-3.0, 1.0, 0.25).GetSafeNormal(),
			FVector3d::ZeroVector
		};

		auto ValidateFrame = [this](const FVector3d& Direction, const FString& Label)
		{
			const FPlanetTangentFrame Frame = FPlanetRegionService::MakeTangentFrame(Direction);
			TestTrue(Label + TEXT(": up is finite"), Private::IsFinite(Frame.UnitUp));
			TestTrue(Label + TEXT(": east is finite"), Private::IsFinite(Frame.UnitEast));
			TestTrue(Label + TEXT(": north is finite"), Private::IsFinite(Frame.UnitNorth));
			TestTrue(Label + TEXT(": up is unit length"),
				FMath::Abs(Frame.UnitUp.Length() - 1.0) <= Private::UnitVectorTolerance);
			TestTrue(Label + TEXT(": east is unit length"),
				FMath::Abs(Frame.UnitEast.Length() - 1.0) <= Private::UnitVectorTolerance);
			TestTrue(Label + TEXT(": north is unit length"),
				FMath::Abs(Frame.UnitNorth.Length() - 1.0) <= Private::UnitVectorTolerance);
			TestTrue(Label + TEXT(": up and east are perpendicular"),
				FMath::Abs(FVector3d::DotProduct(Frame.UnitUp, Frame.UnitEast))
					<= Private::UnitVectorTolerance);
			TestTrue(Label + TEXT(": up and north are perpendicular"),
				FMath::Abs(FVector3d::DotProduct(Frame.UnitUp, Frame.UnitNorth))
					<= Private::UnitVectorTolerance);
			TestTrue(Label + TEXT(": east and north are perpendicular"),
				FMath::Abs(FVector3d::DotProduct(Frame.UnitEast, Frame.UnitNorth))
					<= Private::UnitVectorTolerance);
			TestTrue(Label + TEXT(": frame is right-handed"),
				FVector3d::DotProduct(
					FVector3d::CrossProduct(Frame.UnitEast, Frame.UnitNorth),
					Frame.UnitUp) >= 1.0 - Private::UnitVectorTolerance);
		};

		for (int32 RegionSlot = 0; RegionSlot < Regions.Num(); ++RegionSlot)
		{
			ValidateFrame(Regions[RegionSlot].UnitSite,
				FString::Printf(TEXT("Region %d tangent frame"), RegionSlot));
		}
		for (int32 DirectionIndex = 0; DirectionIndex < UE_ARRAY_COUNT(FrameDirections); ++DirectionIndex)
		{
			ValidateFrame(FrameDirections[DirectionIndex],
				FString::Printf(TEXT("Representative tangent frame %d"), DirectionIndex));
		}

		const FVector2d RepresentativeOffsetsCm[] =
		{
			FVector2d::ZeroVector,
			FVector2d(250.0, 0.0),
			FVector2d(0.0, -750.0),
			FVector2d(2500.0, 4000.0),
			FVector2d(30000.0, -20000.0),
			FVector2d(-40000.0, 15000.0),
			FVector2d(17500.0, 42000.0)
		};
		const FVector3d RepresentativeAnchors[] =
		{
			Regions[0].UnitSite,
			Regions[FPlanet50KmProfile::RegionCount / 2].UnitSite,
			Regions[FPlanet50KmProfile::RegionCount - 1].UnitSite,
			FVector3d(0.0, 0.0, 1.0),
			FVector3d(0.0, 0.0, -1.0),
			FVector3d(1.0, -2.0, 0.5).GetSafeNormal()
		};

		for (int32 AnchorIndex = 0; AnchorIndex < UE_ARRAY_COUNT(RepresentativeAnchors); ++AnchorIndex)
		{
			for (int32 OffsetIndex = 0;
				OffsetIndex < UE_ARRAY_COUNT(RepresentativeOffsetsCm);
				++OffsetIndex)
			{
				const FVector2d& ExpectedOffset = RepresentativeOffsetsCm[OffsetIndex];
				const FVector3d TargetDirection = FPlanetRegionService::ExpMapDirection(
					RepresentativeAnchors[AnchorIndex], ExpectedOffset);
				const FVector2d RecoveredOffset = FPlanetRegionService::LogMapOffsetCm(
					RepresentativeAnchors[AnchorIndex], TargetDirection);
				const double ErrorCm = (RecoveredOffset - ExpectedOffset).Length();
				const FString Prefix = FString::Printf(
					TEXT("Exp/log round trip anchor %d offset %d: "), AnchorIndex, OffsetIndex);

				TestTrue(Prefix + TEXT("target direction is finite"),
					Private::IsFinite(TargetDirection));
				TestTrue(Prefix + TEXT("target direction remains unit length"),
					FMath::Abs(TargetDirection.Length() - 1.0)
						<= Private::UnitVectorTolerance);
				TestTrue(Prefix + TEXT("recovered offset is finite"),
					Private::IsFinite(RecoveredOffset));
				TestTrue(Prefix + TEXT("round-trip error is at most 1 cm"),
					FMath::IsFinite(ErrorCm) && ErrorCm <= Private::RoundTripToleranceCm);
			}
		}

		return true;
	}
}

#endif // WITH_DEV_AUTOMATION_TESTS
