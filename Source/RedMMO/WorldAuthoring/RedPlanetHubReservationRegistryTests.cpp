#include "RedPlanetHubReservationRegistry.h"

#include <limits>

#if WITH_DEV_AUTOMATION_TESTS

#include "Components/SceneComponent.h"
#include "Misc/AutomationTest.h"
#include "RedMMO/Planet/RedPlanetRegionService.h"
#include "UObject/UObjectGlobals.h"

namespace RedPlanetHubReservationRegistryTests
{
	constexpr int32 ExpectedReservationCount = 27;
	constexpr double WeightTolerance = 1.0e-4;

	const FName BlockedFeatureTags[] = {
		TEXT("Foliage"), TEXT("Rock"), TEXT("Creature"),
		TEXT("Resource"), TEXT("Water"), TEXT("POI")
	};

	const TCHAR* ExpectedStableGuids[ExpectedReservationCount] = {
		TEXT("9F9FA3C4-36CF-52A3-B7AC-674DA3194545"),
		TEXT("5E695431-C567-5AB3-AB1C-C6A09993D388"),
		TEXT("C998BD04-1E6E-531A-94E2-D33EDC08F0DC"),
		TEXT("6713DE01-93B0-5F0A-8828-9CFD31671628"),
		TEXT("D030FEAC-8913-5FC2-8F70-A2E0B1FCFDDE"),
		TEXT("0821D35B-EF67-5F98-BA30-AFBFA668D140"),
		TEXT("D02874C6-658A-566E-A309-F02688E37832"),
		TEXT("A4D672AA-B5ED-5C57-B033-0F4105CA06E4"),
		TEXT("E0AC3702-3173-5BD6-AB08-166C14AAC804"),
		TEXT("DB8A12DD-8354-5E59-97F4-24618BE35D59"),
		TEXT("D2DCB61A-E5BC-5E22-8D37-57BDEB9FA67C"),
		TEXT("76019238-C07C-5000-8DD9-EA1276A859A8"),
		TEXT("2D1EC31B-62EF-5C17-A86E-325A6249FA2B"),
		TEXT("10F07CDC-C04F-5DF8-B0F5-E3938171A274"),
		TEXT("5D2B841C-1315-524E-B674-D10431D68AD0"),
		TEXT("EE37C6F3-C688-5390-B27E-3FB177050588"),
		TEXT("D2685469-D7BF-5BD9-BBC3-033B1740FAC9"),
		TEXT("AF824AA1-DEFB-541C-A142-4AB90974E15D"),
		TEXT("29C8CA08-5EFC-529F-9176-A5F7CEBFD055"),
		TEXT("423C744D-0123-5FD8-9E7F-6BD9B102862E"),
		TEXT("D6E1BDCE-EE5B-50B2-B50D-F40346132723"),
		TEXT("371F9EE5-E8EE-541B-8F74-0460F84976AB"),
		TEXT("FFDFEC26-64C9-58B1-9880-A3BA5593F9B9"),
		TEXT("8664FF55-7DBE-5D09-9943-B4EF225CC9DC"),
		TEXT("ECFC214E-1CC9-5D0B-A23B-12FB4E1DE000"),
		TEXT("09120C3A-B32A-56F5-916F-DC39130F1C90"),
		TEXT("162A8A2C-6C23-5A5C-9626-ED819447FDBB")
	};

	FName ExpectedArchetypeTag(const RedPlanet::ERegionArchetype Archetype)
	{
		switch (Archetype)
		{
		case RedPlanet::ERegionArchetype::CoralCanopyCoast:
			return TEXT("CoralCanopyCoast");
		case RedPlanet::ERegionArchetype::EmberMagentaRift:
			return TEXT("EmberMagentaRift");
		case RedPlanet::ERegionArchetype::FungalCathedral:
			return TEXT("FungalCathedral");
		case RedPlanet::ERegionArchetype::MonolithicPillarCavern:
			return TEXT("MonolithicPillarCavern");
		case RedPlanet::ERegionArchetype::VerdantSkyPlateau:
			return TEXT("VerdantSkyPlateau");
		case RedPlanet::ERegionArchetype::PortalOasis:
			return TEXT("PortalOasis");
		case RedPlanet::ERegionArchetype::CliffsideSpaceport:
			return TEXT("CliffsideSpaceport");
		default:
			return NAME_None;
		}
	}

	FVector ToWorldPoint(
		const FVector& PlanetCenter,
		const FVector3d& SurfaceDirection)
	{
		return PlanetCenter + FVector(SurfaceDirection.GetSafeNormal())
			* RedPlanet::FPlanet50KmProfile::RadiusCm;
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FRedPlanetHubReservationAuthenticatedRecordsTest,
	"RedMMO.WorldAuthoring.HubReservations.AuthenticatedRecords",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRedPlanetHubReservationAuthenticatedRecordsTest::RunTest(const FString& Parameters)
{
	using namespace RedPlanetHubReservationRegistryTests;
	(void)Parameters;

	TestEqual(TEXT("Authenticated dataset hash is frozen"),
		URedPlanetHubReservationRegistry::GetReservationDatasetSha256(),
		FString(TEXT("D6DE83918473FFD5D8E27AF5502A39A1E25B3370F7D837F62C831A302F66F3B5")));
	TestEqual(TEXT("Reservation body is RED Mars"),
		URedPlanetHubReservationRegistry::GetReservationBodyId(),
		FName(TEXT("planet.red.mars")));
	TestEqual(TEXT("All 27 authenticated reservations are available"),
		URedPlanetHubReservationRegistry::GetHubReservationCount(),
		ExpectedReservationCount);

	const TArray<FRedPlanetHubReservation> Reservations =
		URedPlanetHubReservationRegistry::GetAllHubReservations();
	TestEqual(TEXT("Bulk query returns all authenticated reservations"),
		Reservations.Num(), ExpectedReservationCount);

	for (int32 Index = 0; Index < Reservations.Num(); ++Index)
	{
		const FRedPlanetHubReservation& Reservation = Reservations[Index];
		const RedPlanet::FPlanetRegionMetadata& Metadata =
			RedPlanet::FPlanetRegionService::Get().GetRegionChecked(Index);
		const FString Prefix = FString::Printf(TEXT("Reservation %d: "), Index);
		const FName ExpectedArchetype = ExpectedArchetypeTag(Metadata.Archetype);
		TestEqual(Prefix + TEXT("index is stable"), Reservation.RegionIndex, Index);
		TestEqual(Prefix + TEXT("body ID is stable"), Reservation.BodyId,
			FName(TEXT("planet.red.mars")));
		TestEqual(Prefix + TEXT("authoring-region ID is namespaced"),
			Reservation.AuthoringRegionId,
			FName(*FString::Printf(
				TEXT("planet.red.mars.authoring-region.r%02d"), Index)));
		TestEqual(Prefix + TEXT("seed matches authenticated service row"),
			Reservation.StableSeed, static_cast<int64>(Metadata.StableSeed));
		TestEqual(Prefix + TEXT("source patch is exact"), Reservation.SourcePatch,
			FName(*FString::Printf(TEXT("RED_Patch_%02d"), Index)));
		TestEqual(Prefix + TEXT("archetype tag is exact"),
			Reservation.ArchetypeTag, ExpectedArchetype);
		TestEqual(Prefix + TEXT("reservation ID is exact"), Reservation.ReservationId,
			FName(*FString::Printf(
				TEXT("R%02d_%s_MainHub"), Index, *ExpectedArchetype.ToString())));
		FGuid ExpectedGuid;
		TestTrue(Prefix + TEXT("expected GUID parses"),
			FGuid::ParseExact(
				ExpectedStableGuids[Index], EGuidFormats::DigitsWithHyphens, ExpectedGuid));
		TestEqual(Prefix + TEXT("GUID value is exact"),
			Reservation.StableGuid, ExpectedGuid);
		TestTrue(Prefix + TEXT("direction matches authenticated service row"),
			(FVector3d(Reservation.UnitCenterDirection) - Metadata.UnitSite).Length()
				<= 1.0e-12);
		TestEqual(Prefix + TEXT("planet radius is protected"),
			Reservation.PlanetRadiusCm, RedPlanet::FPlanet50KmProfile::RadiusCm);
		TestTrue(Prefix + TEXT("hub radius is exact"),
			FMath::IsNearlyEqual(
				Reservation.SuggestedHubRadiusCm, Metadata.SuggestedHubRadiusCm, 1.0e-5));
		TestTrue(Prefix + TEXT("protected radius is exact"),
			FMath::IsNearlyEqual(Reservation.ProtectedRadiusCm,
				Metadata.SuggestedFlattenCoreRadiusCm, 1.0e-5));
		TestTrue(Prefix + TEXT("blend radius is exact"),
			FMath::IsNearlyEqual(Reservation.BlendRadiusCm,
				Metadata.SuggestedFlattenBlendRadiusCm, 1.0e-5));
		TestEqual(Prefix + TEXT("blocked tag set has no extras"),
			Reservation.BlockedFeatureTags.Num(),
			static_cast<int32>(UE_ARRAY_COUNT(BlockedFeatureTags)));
		for (const FName FeatureTag : BlockedFeatureTags)
		{
			TestTrue(Prefix + TEXT("required feature tag is blocked"),
				Reservation.BlockedFeatureTags.Contains(FeatureTag));
		}
	}

	FRedPlanetHubReservation InvalidReservation;
	TestFalse(TEXT("Negative reservation index is rejected"),
		URedPlanetHubReservationRegistry::GetHubReservation(-1, InvalidReservation));
	TestFalse(TEXT("Past-end reservation index is rejected"),
		URedPlanetHubReservationRegistry::GetHubReservation(
			ExpectedReservationCount, InvalidReservation));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FRedPlanetHubReservationProtectionQueriesTest,
	"RedMMO.WorldAuthoring.HubReservations.ProtectionQueries",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRedPlanetHubReservationProtectionQueriesTest::RunTest(const FString& Parameters)
{
	using namespace RedPlanetHubReservationRegistryTests;
	(void)Parameters;

	const FName BodyId = URedPlanetHubReservationRegistry::GetReservationBodyId();
	const FVector PlanetCenter(123456.0, -654321.0, 77777.0);
	const TArray<FRedPlanetHubReservation> Reservations =
		URedPlanetHubReservationRegistry::GetAllHubReservations();
	if (Reservations.Num() != ExpectedReservationCount)
	{
		AddError(TEXT("Authenticated reservation layout was rejected before query tests"));
		return false;
	}

	for (const FRedPlanetHubReservation& Reservation : Reservations)
	{
		const FString Prefix = FString::Printf(
			TEXT("Reservation %d center: "), Reservation.RegionIndex);
		const FVector CenterPoint = ToWorldPoint(
			PlanetCenter, FVector3d(Reservation.UnitCenterDirection));
		for (const FName FeatureTag : BlockedFeatureTags)
		{
			const FRedPlanetHubProtectionQuery Query =
				URedPlanetHubReservationRegistry::QueryFeatureProtectionAtCenter(
					BodyId, FeatureTag, CenterPoint, PlanetCenter,
					RedPlanet::FPlanet50KmProfile::RadiusCm);
			TestTrue(Prefix + TEXT("query is valid"), Query.bQueryValid);
			TestTrue(Prefix + TEXT("feature is blocked"), Query.bBlocked);
			TestTrue(Prefix + TEXT("center has full protection"),
				FMath::IsNearlyEqual(
					static_cast<double>(Query.ProtectionWeight), 1.0, WeightTolerance));
			TestEqual(Prefix + TEXT("strongest reservation identity is stable"),
				Query.StableGuid, Reservation.StableGuid);
		}
	}

	const FRedPlanetHubReservation& First = Reservations[0];
	const FVector3d FirstDirection(First.UnitCenterDirection);
	const FVector3d HardEdgeDirection = RedPlanet::FPlanetRegionService::ExpMapDirection(
		FirstDirection, FVector2d(First.ProtectedRadiusCm, 0.0));
	const FRedPlanetHubProtectionQuery HardEdge =
		URedPlanetHubReservationRegistry::QueryFeatureProtectionAtCenter(
			BodyId, TEXT("Foliage"), ToWorldPoint(PlanetCenter, HardEdgeDirection),
			PlanetCenter, RedPlanet::FPlanet50KmProfile::RadiusCm);
	TestTrue(TEXT("Exact hard edge query is valid"), HardEdge.bQueryValid);
	TestTrue(TEXT("Exact hard edge remains blocked"), HardEdge.bBlocked);
	TestTrue(TEXT("Exact hard edge has full protection"),
		FMath::IsNearlyEqual(
			static_cast<double>(HardEdge.ProtectionWeight), 1.0, WeightTolerance));

	const FVector3d HalfBlendDirection = RedPlanet::FPlanetRegionService::ExpMapDirection(
		FirstDirection,
		FVector2d(First.ProtectedRadiusCm + (0.5 * First.BlendRadiusCm), 0.0));
	const FRedPlanetHubProtectionQuery HalfBlend =
		URedPlanetHubReservationRegistry::QueryFeatureProtectionAtCenter(
			BodyId, TEXT("Foliage"), ToWorldPoint(PlanetCenter, HalfBlendDirection),
			PlanetCenter, RedPlanet::FPlanet50KmProfile::RadiusCm);
	TestTrue(TEXT("Half-blend query is valid"), HalfBlend.bQueryValid);
	TestTrue(TEXT("Half-blend query remains blocked"), HalfBlend.bBlocked);
	TestTrue(TEXT("Half-blend weight is one half"),
		FMath::IsNearlyEqual(
			static_cast<double>(HalfBlend.ProtectionWeight), 0.5, WeightTolerance));

	const FVector3d BlendEdgeDirection = RedPlanet::FPlanetRegionService::ExpMapDirection(
		FirstDirection,
		FVector2d(First.ProtectedRadiusCm + First.BlendRadiusCm, 0.0));
	const FRedPlanetHubProtectionQuery BlendEdge =
		URedPlanetHubReservationRegistry::QueryFeatureProtectionAtCenter(
			BodyId, TEXT("Foliage"), ToWorldPoint(PlanetCenter, BlendEdgeDirection),
			PlanetCenter, RedPlanet::FPlanet50KmProfile::RadiusCm);
	TestTrue(TEXT("Exact blend edge query is valid"), BlendEdge.bQueryValid);
	TestFalse(TEXT("Exact blend edge is not blocked"), BlendEdge.bBlocked);
	TestTrue(TEXT("Exact blend edge has zero protection"),
		FMath::IsNearlyZero(
			static_cast<double>(BlendEdge.ProtectionWeight), WeightTolerance));

	const FVector3d OutsideDirection = RedPlanet::FPlanetRegionService::ExpMapDirection(
		FirstDirection,
		FVector2d(First.ProtectedRadiusCm + First.BlendRadiusCm + 1.0, 0.0));
	const FRedPlanetHubProtectionQuery Outside =
		URedPlanetHubReservationRegistry::QueryFeatureProtectionAtCenter(
			BodyId, TEXT("Foliage"), ToWorldPoint(PlanetCenter, OutsideDirection),
			PlanetCenter, RedPlanet::FPlanet50KmProfile::RadiusCm);
	TestTrue(TEXT("Outside query is valid"), Outside.bQueryValid);
	TestFalse(TEXT("Outside all hub blends is not blocked"), Outside.bBlocked);
	TestTrue(TEXT("Outside protection weight is zero"),
		FMath::IsNearlyZero(static_cast<double>(Outside.ProtectionWeight), WeightTolerance));

	const FVector FirstCenterPoint = ToWorldPoint(PlanetCenter, FirstDirection);
	auto TestFailsClosed = [this](
		const FString& Prefix, const FRedPlanetHubProtectionQuery& Query)
	{
		TestFalse(Prefix + TEXT(" is invalid"), Query.bQueryValid);
		TestTrue(Prefix + TEXT(" remains blocked"), Query.bBlocked);
		TestTrue(Prefix + TEXT(" keeps full protection"),
			FMath::IsNearlyEqual(
				static_cast<double>(Query.ProtectionWeight), 1.0, WeightTolerance));
		TestTrue(Prefix + TEXT(" has no reservation ID"), Query.ReservationId.IsNone());
		TestFalse(Prefix + TEXT(" has no stable GUID"), Query.StableGuid.IsValid());
	};
	const TArray<FName> InvalidTags = {
		FName(),
		FName(TEXT("Folige"))
	};
	for (const FName InvalidTag : InvalidTags)
	{
		const FRedPlanetHubProtectionQuery Invalid =
			URedPlanetHubReservationRegistry::QueryFeatureProtectionAtCenter(
				BodyId, InvalidTag, FirstCenterPoint, PlanetCenter,
				RedPlanet::FPlanet50KmProfile::RadiusCm);
		TestFalse(TEXT("Unregistered feature tag is invalid"), Invalid.bQueryValid);
		TestTrue(TEXT("Unregistered feature tag fails blocked"), Invalid.bBlocked);
		TestTrue(TEXT("Unregistered feature tag fails at full protection"),
			FMath::IsNearlyEqual(
				static_cast<double>(Invalid.ProtectionWeight), 1.0, WeightTolerance));
		TestFailsClosed(TEXT("Unregistered feature tag"), Invalid);
	}

	const FRedPlanetHubProtectionQuery WrongBody =
		URedPlanetHubReservationRegistry::QueryFeatureProtectionAtCenter(
			TEXT("planet.wrong"), TEXT("Foliage"), FirstCenterPoint, PlanetCenter,
			RedPlanet::FPlanet50KmProfile::RadiusCm);
	TestFalse(TEXT("Wrong body query is invalid"), WrongBody.bQueryValid);
	TestTrue(TEXT("Wrong body query fails blocked"), WrongBody.bBlocked);
	TestFailsClosed(TEXT("Wrong body helper query"), WrongBody);

	USceneComponent* ContextWithoutWorld = NewObject<USceneComponent>();
	const FRedPlanetHubProtectionQuery PublicWrongBody =
		URedPlanetHubReservationRegistry::QueryFeatureProtection(
			ContextWithoutWorld, TEXT("planet.wrong"), TEXT("Foliage"), FirstCenterPoint);
	TestFailsClosed(TEXT("Wrong body public query"), PublicWrongBody);

	const FRedPlanetHubProtectionQuery ZeroDirection =
		URedPlanetHubReservationRegistry::QueryFeatureProtectionAtCenter(
			BodyId, TEXT("Foliage"), PlanetCenter, PlanetCenter,
			RedPlanet::FPlanet50KmProfile::RadiusCm);
	TestFalse(TEXT("Zero direction query is invalid"), ZeroDirection.bQueryValid);
	TestTrue(TEXT("Zero direction query fails blocked"), ZeroDirection.bBlocked);
	TestFailsClosed(TEXT("Zero direction query"), ZeroDirection);

	const FRedPlanetHubProtectionQuery WrongRadius =
		URedPlanetHubReservationRegistry::QueryFeatureProtectionAtCenter(
			BodyId, TEXT("Foliage"), FirstCenterPoint, PlanetCenter,
			RedPlanet::FPlanet50KmProfile::RadiusCm + 100.0);
	TestFalse(TEXT("Mismatched nominal radius is invalid"), WrongRadius.bQueryValid);
	TestTrue(TEXT("Mismatched nominal radius fails blocked"), WrongRadius.bBlocked);
	TestFailsClosed(TEXT("Mismatched nominal radius query"), WrongRadius);

	const double QuietNaN = std::numeric_limits<double>::quiet_NaN();
	const FRedPlanetHubProtectionQuery NaNPoint =
		URedPlanetHubReservationRegistry::QueryFeatureProtectionAtCenter(
			BodyId, TEXT("Foliage"), FVector(QuietNaN, 0.0, 0.0), PlanetCenter,
			RedPlanet::FPlanet50KmProfile::RadiusCm);
	TestFailsClosed(TEXT("NaN point query"), NaNPoint);
	const FRedPlanetHubProtectionQuery NaNCenter =
		URedPlanetHubReservationRegistry::QueryFeatureProtectionAtCenter(
			BodyId, TEXT("Foliage"), FirstCenterPoint, FVector(QuietNaN, 0.0, 0.0),
			RedPlanet::FPlanet50KmProfile::RadiusCm);
	TestFailsClosed(TEXT("NaN center query"), NaNCenter);
	for (const double InvalidRadius : { QuietNaN, 0.0, -1.0 })
	{
		const FRedPlanetHubProtectionQuery InvalidRadiusQuery =
			URedPlanetHubReservationRegistry::QueryFeatureProtectionAtCenter(
				BodyId, TEXT("Foliage"), FirstCenterPoint, PlanetCenter, InvalidRadius);
		TestFailsClosed(TEXT("Invalid nominal radius query"), InvalidRadiusQuery);
	}

	const FRedPlanetHubProtectionQuery NullWorldContext =
		URedPlanetHubReservationRegistry::QueryFeatureProtection(
			nullptr, BodyId, TEXT("Foliage"), FirstCenterPoint);
	TestFalse(TEXT("Null world context is invalid"), NullWorldContext.bQueryValid);
	TestTrue(TEXT("Null world context fails blocked"), NullWorldContext.bBlocked);
	TestFailsClosed(TEXT("Null world context query"), NullWorldContext);

	const FRedPlanetHubProtectionQuery MissingWorld =
		URedPlanetHubReservationRegistry::QueryFeatureProtection(
			ContextWithoutWorld, BodyId, TEXT("Foliage"), FirstCenterPoint);
	TestFalse(TEXT("Context without a world is invalid"), MissingWorld.bQueryValid);
	TestTrue(TEXT("Context without a world fails blocked"), MissingWorld.bBlocked);
	TestFailsClosed(TEXT("Context without world query"), MissingWorld);
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
