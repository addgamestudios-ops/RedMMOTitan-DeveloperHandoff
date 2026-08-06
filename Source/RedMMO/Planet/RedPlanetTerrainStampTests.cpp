// REDMMO_HAS_PLANETGEN_FORK_APIS_GATE
#if __has_include("PlanetGen/PlanetGenTerrainStamp.h")
#include "PlanetGen/PlanetGenTerrainStamp.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Misc/AutomationTest.h"

namespace RedPlanet::TerrainStampTests
{
	namespace Private
	{
		constexpr float PlanetRadiusCm = 795775.0f;
		constexpr float BaseHeightCm = -1200.0f;
		constexpr float TargetHeightCm = 3500.0f;
		constexpr float CoreRadiusCm = 50000.0f;
		constexpr float FeatherRadiusCm = 25000.0f;
		constexpr float HeightToleranceCm = 0.25f;

		FPlanetGenResolvedTerrainStamp MakeResolvedStamp(
			int32 StableId,
			const FVector& SurfaceDirection,
			float TargetCm,
			float CoreCm = CoreRadiusCm,
			float FeatherCm = FeatherRadiusCm)
		{
			FPlanetGenResolvedTerrainStamp Stamp;
			Stamp.StableId = StableId;
			Stamp.SurfaceDirection = SurfaceDirection.GetSafeNormal();
			Stamp.CoreRadiusCm = CoreCm;
			Stamp.FeatherRadiusCm = FeatherCm;
			Stamp.ResolvedTargetHeightCm = TargetCm;
			return Stamp;
		}

		FVector RotateAlongGreatCircle(
			const FVector& UnitDirection,
			const FVector& UnitRotationAxis,
			float ArcDistanceCm)
		{
			const float AngleRadians = ArcDistanceCm / PlanetRadiusCm;
			return FQuat(UnitRotationAxis.GetSafeNormal(), AngleRadians)
				.RotateVector(UnitDirection.GetSafeNormal())
				.GetSafeNormal();
		}

		bool IsFiniteVector(const FVector& Value)
		{
			return FMath::IsFinite(Value.X)
				&& FMath::IsFinite(Value.Y)
				&& FMath::IsFinite(Value.Z);
		}

	}

	IMPLEMENT_SIMPLE_AUTOMATION_TEST(
		FRedPlanetTerrainStampMathTest,
		"RedMMO.Planet.TerrainStamp.DeterministicGeodesicMath",
		EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

	bool FRedPlanetTerrainStampMathTest::RunTest(const FString& Parameters)
	{
		(void)Parameters;

		const FVector StampCenter = FVector::ForwardVector;
		const FPlanetGenResolvedTerrainStamp PrimaryStamp = Private::MakeResolvedStamp(
			10, StampCenter, Private::TargetHeightCm);

		// Empty captures and disabled authoring entries must leave the original terrain untouched.
		const TArray<FPlanetGenResolvedTerrainStamp> EmptyStamps;
		TestEqual(
			TEXT("An empty resolved stamp capture is a no-op"),
			PlanetGenTerrainStamp::ApplyResolvedStamps(
				Private::BaseHeightCm,
				StampCenter,
				Private::PlanetRadiusCm,
				EmptyStamps),
			Private::BaseHeightCm);

		FPlanetGenTerrainStamp DisabledAuthoredStamp;
		DisabledAuthoredStamp.bEnabled = false;
		DisabledAuthoredStamp.StableId = 99;
		DisabledAuthoredStamp.SurfaceDirection = StampCenter;
		DisabledAuthoredStamp.CoreRadiusCm = Private::CoreRadiusCm;
		DisabledAuthoredStamp.FeatherRadiusCm = Private::FeatherRadiusCm;
		DisabledAuthoredStamp.Mode = EPlanetGenTerrainStampMode::AbsoluteRadialHeight;
		DisabledAuthoredStamp.TargetHeightCm = Private::TargetHeightCm;

		FPlanetGenResolvedTerrainStamp DisabledResolved;
		TestFalse(
			TEXT("The pure resolver rejects a disabled authored stamp"),
			PlanetGenTerrainStamp::ResolveTerrainStamp(
				DisabledAuthoredStamp, Private::BaseHeightCm, DisabledResolved));
		const TArray<FPlanetGenResolvedTerrainStamp> DisabledCapture;
		TestEqual(
			TEXT("A disabled authored stamp is therefore a terrain no-op"),
			PlanetGenTerrainStamp::ApplyResolvedStamps(
				Private::BaseHeightCm,
				StampCenter,
				Private::PlanetRadiusCm,
				DisabledCapture),
			Private::BaseHeightCm);

		const TArray<FPlanetGenResolvedTerrainStamp> SingleStamp = { PrimaryStamp };
		const FVector MidCoreDirection = Private::RotateAlongGreatCircle(
			StampCenter, FVector::UpVector, Private::CoreRadiusCm * 0.5f);
		const FVector CoreBoundaryDirection = Private::RotateAlongGreatCircle(
			StampCenter, FVector::UpVector, Private::CoreRadiusCm);
		const FVector OuterBoundaryDirection = Private::RotateAlongGreatCircle(
			StampCenter,
			FVector::UpVector,
			Private::CoreRadiusCm + Private::FeatherRadiusCm);

		TestEqual(
			TEXT("The stamp center resolves exactly to the target height"),
			PlanetGenTerrainStamp::ApplyResolvedStamps(
				Private::BaseHeightCm,
				StampCenter,
				Private::PlanetRadiusCm,
				SingleStamp),
			Private::TargetHeightCm);
		TestTrue(
			TEXT("A sample inside the constant core resolves to the target height"),
			FMath::IsNearlyEqual(
				PlanetGenTerrainStamp::ApplyResolvedStamps(
					Private::BaseHeightCm,
					MidCoreDirection,
					Private::PlanetRadiusCm,
					SingleStamp),
				Private::TargetHeightCm,
				Private::HeightToleranceCm));
		TestTrue(
			TEXT("The nominal core boundary remains at the target height"),
			FMath::IsNearlyEqual(
				PlanetGenTerrainStamp::ApplyResolvedStamps(
					Private::BaseHeightCm,
					CoreBoundaryDirection,
					Private::PlanetRadiusCm,
					SingleStamp),
				Private::TargetHeightCm,
				Private::HeightToleranceCm));
		TestTrue(
			TEXT("The outer feather edge returns to the unstamped base height"),
			FMath::IsNearlyEqual(
				PlanetGenTerrainStamp::ApplyResolvedStamps(
					Private::BaseHeightCm,
					OuterBoundaryDirection,
					Private::PlanetRadiusCm,
					SingleStamp),
				Private::BaseHeightCm,
				Private::HeightToleranceCm));

		TestEqual(
			TEXT("Influence is exactly one at the core boundary"),
			PlanetGenTerrainStamp::EvaluateInfluence(
				Private::CoreRadiusCm,
				Private::CoreRadiusCm,
				Private::FeatherRadiusCm),
			1.0f);
		TestEqual(
			TEXT("Influence is exactly zero at the outer feather boundary"),
			PlanetGenTerrainStamp::EvaluateInfluence(
				Private::CoreRadiusCm + Private::FeatherRadiusCm,
				Private::CoreRadiusCm,
				Private::FeatherRadiusCm),
			0.0f);

		// SmoothStep should be continuous and have an approximately zero first derivative on both sides.
		constexpr float BoundaryProbeCm = 10.0f;
		const float CoreMinus = PlanetGenTerrainStamp::EvaluateInfluence(
			Private::CoreRadiusCm - BoundaryProbeCm,
			Private::CoreRadiusCm,
			Private::FeatherRadiusCm);
		const float CoreExact = PlanetGenTerrainStamp::EvaluateInfluence(
			Private::CoreRadiusCm,
			Private::CoreRadiusCm,
			Private::FeatherRadiusCm);
		const float CorePlus = PlanetGenTerrainStamp::EvaluateInfluence(
			Private::CoreRadiusCm + BoundaryProbeCm,
			Private::CoreRadiusCm,
			Private::FeatherRadiusCm);
		const float OuterRadiusCm = Private::CoreRadiusCm + Private::FeatherRadiusCm;
		const float OuterMinus = PlanetGenTerrainStamp::EvaluateInfluence(
			OuterRadiusCm - BoundaryProbeCm,
			Private::CoreRadiusCm,
			Private::FeatherRadiusCm);
		const float OuterExact = PlanetGenTerrainStamp::EvaluateInfluence(
			OuterRadiusCm,
			Private::CoreRadiusCm,
			Private::FeatherRadiusCm);
		const float OuterPlus = PlanetGenTerrainStamp::EvaluateInfluence(
			OuterRadiusCm + BoundaryProbeCm,
			Private::CoreRadiusCm,
			Private::FeatherRadiusCm);

		const float CoreLeftSlope = (CoreExact - CoreMinus) / BoundaryProbeCm;
		const float CoreRightSlope = (CorePlus - CoreExact) / BoundaryProbeCm;
		const float OuterLeftSlope = (OuterExact - OuterMinus) / BoundaryProbeCm;
		const float OuterRightSlope = (OuterPlus - OuterExact) / BoundaryProbeCm;
		TestTrue(TEXT("Core-boundary influence samples are finite"),
			FMath::IsFinite(CoreMinus) && FMath::IsFinite(CoreExact) && FMath::IsFinite(CorePlus));
		TestTrue(TEXT("Outer-boundary influence samples are finite"),
			FMath::IsFinite(OuterMinus) && FMath::IsFinite(OuterExact) && FMath::IsFinite(OuterPlus));
		TestTrue(TEXT("Influence is continuous around the core boundary"),
			FMath::Abs(CorePlus - CoreMinus) <= 1.0e-5f);
		TestTrue(TEXT("Influence is continuous around the outer boundary"),
			FMath::Abs(OuterPlus - OuterMinus) <= 1.0e-5f);
		TestTrue(TEXT("The core-boundary first derivative is C1-like"),
			FMath::Abs(CoreLeftSlope - CoreRightSlope) <= 1.0e-6f);
		TestTrue(TEXT("The outer-boundary first derivative is C1-like"),
			FMath::Abs(OuterLeftSlope - OuterRightSlope) <= 1.0e-6f);

		// Three partially overlapping stamps exercise sorted weighted overlap semantics.
		const FVector OverlapSample = Private::RotateAlongGreatCircle(
			StampCenter, FVector::UpVector, 56000.0f);
		const FPlanetGenResolvedTerrainStamp StampA = Private::MakeResolvedStamp(
			300, StampCenter, 1800.0f, 40000.0f, 40000.0f);
		const FPlanetGenResolvedTerrainStamp StampB = Private::MakeResolvedStamp(
			100,
			Private::RotateAlongGreatCircle(StampCenter, FVector::UpVector, 25000.0f),
			-600.0f,
			30000.0f,
			45000.0f);
		const FPlanetGenResolvedTerrainStamp StampC = Private::MakeResolvedStamp(
			200,
			Private::RotateAlongGreatCircle(StampCenter, FVector::UpVector, 70000.0f),
			5200.0f,
			25000.0f,
			35000.0f);

		TArray<FPlanetGenResolvedTerrainStamp> ForwardOrder = { StampA, StampB, StampC };
		TArray<FPlanetGenResolvedTerrainStamp> ReverseOrder = { StampC, StampB, StampA };
		TArray<FPlanetGenResolvedTerrainStamp> MixedOrder = { StampB, StampA, StampC };
		PlanetGenTerrainStamp::SortResolvedStamps(ForwardOrder);
		PlanetGenTerrainStamp::SortResolvedStamps(ReverseOrder);
		PlanetGenTerrainStamp::SortResolvedStamps(MixedOrder);
		const float ForwardHeight = PlanetGenTerrainStamp::ApplyResolvedStamps(
			Private::BaseHeightCm,
			OverlapSample,
			Private::PlanetRadiusCm,
			ForwardOrder);
		const float ReverseHeight = PlanetGenTerrainStamp::ApplyResolvedStamps(
			Private::BaseHeightCm,
			OverlapSample,
			Private::PlanetRadiusCm,
			ReverseOrder);
		const float MixedHeight = PlanetGenTerrainStamp::ApplyResolvedStamps(
			Private::BaseHeightCm,
			OverlapSample,
			Private::PlanetRadiusCm,
			MixedOrder);
		TestTrue(TEXT("The weighted overlap output is finite"), FMath::IsFinite(ForwardHeight));
		TestEqual(TEXT("Reversing authored overlap order produces an identical result"),
			ReverseHeight, ForwardHeight);
		TestEqual(TEXT("A mixed authored overlap order produces an identical result"),
			MixedHeight, ForwardHeight);

		// Repeated representative valid and invalid inputs must remain finite and deterministic.
		const FVector RepresentativeDirections[] =
		{
			FVector::ForwardVector,
			FVector::RightVector,
			FVector::UpVector,
			-FVector::ForwardVector,
			FVector(1.0, 1.0, 0.0).GetSafeNormal(),
			FVector(-2.0, 0.5, 1.0).GetSafeNormal()
		};
		for (int32 DirectionIndex = 0;
			DirectionIndex < UE_ARRAY_COUNT(RepresentativeDirections);
			++DirectionIndex)
		{
			const FVector& Direction = RepresentativeDirections[DirectionIndex];
			const float DistanceCm = PlanetGenTerrainStamp::GreatCircleDistanceCm(
				Direction, StampCenter, Private::PlanetRadiusCm);
			const float FirstHeight = PlanetGenTerrainStamp::ApplyResolvedStamps(
				Private::BaseHeightCm,
				Direction,
				Private::PlanetRadiusCm,
				ForwardOrder);
			const float RepeatedHeight = PlanetGenTerrainStamp::ApplyResolvedStamps(
				Private::BaseHeightCm,
				Direction,
				Private::PlanetRadiusCm,
				ForwardOrder);
			const FString Prefix = FString::Printf(TEXT("Representative direction %d: "), DirectionIndex);
			TestTrue(Prefix + TEXT("direction is finite"), Private::IsFiniteVector(Direction));
			TestTrue(Prefix + TEXT("great-circle distance is finite"), FMath::IsFinite(DistanceCm));
			TestTrue(Prefix + TEXT("resolved height is finite"), FMath::IsFinite(FirstHeight));
			TestEqual(Prefix + TEXT("repeated evaluation is bit-stable"), RepeatedHeight, FirstHeight);
		}

		const float ZeroDirectionHeight = PlanetGenTerrainStamp::ApplyResolvedStamps(
			Private::BaseHeightCm,
			FVector::ZeroVector,
			Private::PlanetRadiusCm,
			SingleStamp);
		const float ZeroRadiusHeight = PlanetGenTerrainStamp::ApplyResolvedStamps(
			Private::BaseHeightCm,
			StampCenter,
			0.0f,
			SingleStamp);
		TestTrue(TEXT("A zero sample direction still produces a finite result"),
			FMath::IsFinite(ZeroDirectionHeight));
		TestEqual(TEXT("A zero sample direction cannot influence terrain"),
			ZeroDirectionHeight, Private::BaseHeightCm);
		TestTrue(TEXT("A nonpositive planet radius still produces a finite result"),
			FMath::IsFinite(ZeroRadiusHeight));
		TestEqual(TEXT("A nonpositive planet radius cannot influence terrain"),
			ZeroRadiusHeight, Private::BaseHeightCm);

		// A +X/+Y cube-face seam must not appear in direction-only geodesic stamp math.
		const FVector CubeFaceSeamCenter = FVector(1.0, 1.0, 0.0).GetSafeNormal();
		constexpr float SeamOffsetCm = 18000.0f;
		const FVector PositiveSeamSide = Private::RotateAlongGreatCircle(
			CubeFaceSeamCenter, FVector::UpVector, SeamOffsetCm);
		const FVector NegativeSeamSide = Private::RotateAlongGreatCircle(
			CubeFaceSeamCenter, FVector::UpVector, -SeamOffsetCm);
		TestTrue(TEXT("The positive seam sample lies on the +Y cube face"),
			PositiveSeamSide.Y > PositiveSeamSide.X);
		TestTrue(TEXT("The negative seam sample lies on the +X cube face"),
			NegativeSeamSide.X > NegativeSeamSide.Y);

		const float PositiveDistanceCm = PlanetGenTerrainStamp::GreatCircleDistanceCm(
			PositiveSeamSide, CubeFaceSeamCenter, Private::PlanetRadiusCm);
		const float NegativeDistanceCm = PlanetGenTerrainStamp::GreatCircleDistanceCm(
			NegativeSeamSide, CubeFaceSeamCenter, Private::PlanetRadiusCm);
		const FPlanetGenResolvedTerrainStamp SeamStamp = Private::MakeResolvedStamp(
			500, CubeFaceSeamCenter, 2250.0f, 8000.0f, 30000.0f);
		const TArray<FPlanetGenResolvedTerrainStamp> SeamStamps = { SeamStamp };
		const float PositiveSeamHeight = PlanetGenTerrainStamp::ApplyResolvedStamps(
			Private::BaseHeightCm,
			PositiveSeamSide,
			Private::PlanetRadiusCm,
			SeamStamps);
		const float NegativeSeamHeight = PlanetGenTerrainStamp::ApplyResolvedStamps(
			Private::BaseHeightCm,
			NegativeSeamSide,
			Private::PlanetRadiusCm,
			SeamStamps);
		TestTrue(TEXT("Both representative seam directions are finite"),
			Private::IsFiniteVector(PositiveSeamSide) && Private::IsFiniteVector(NegativeSeamSide));
		TestTrue(TEXT("Symmetric seam distances are equivalent"),
			FMath::IsNearlyEqual(PositiveDistanceCm, NegativeDistanceCm, 1.0f));
		TestTrue(TEXT("Symmetric samples across a cube-face seam receive equivalent terrain heights"),
			FMath::IsNearlyEqual(PositiveSeamHeight, NegativeSeamHeight, Private::HeightToleranceCm));
		TestTrue(TEXT("The positive seam output is finite"), FMath::IsFinite(PositiveSeamHeight));
		TestTrue(TEXT("The negative seam output is finite"), FMath::IsFinite(NegativeSeamHeight));

		return true;
	}
}

#endif // WITH_DEV_AUTOMATION_TESTS

#else
// Stock Marketplace PlanetGen 1.7 lacks TerrainStamp/MacroHeightfield fork APIs.
// These automation suites are compiled out until Plugins/PlanetGenPinned_* is restored.
#endif