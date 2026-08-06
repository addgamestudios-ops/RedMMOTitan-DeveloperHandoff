#include "RedPlanetHubReservationRegistry.h"

#include "Engine/Engine.h"
#include "RedMMO/RedCelestialFrameRegistry.h"
#include "RedMMO/Planet/RedPlanetRegionService.h"

namespace
{
	using namespace RedPlanet;

	struct FFrozenReservationBinding
	{
		int32 RegionIndex;
		uint32 StableSeed;
		ERegionArchetype Archetype;
		double UnitX;
		double UnitY;
		double UnitZ;
		double SuggestedHubRadiusCm;
		double ProtectedRadiusCm;
		double BlendRadiusCm;
		const TCHAR* ReservationId;
		const TCHAR* StableGuid;
		const TCHAR* SourcePatch;
	};

	// BEGIN GENERATED AUTHENTICATED RESERVATION BINDINGS
	// Canonical source: docs/PLANET_50KM_PCG_RESERVATIONS.json
	const FFrozenReservationBinding FrozenReservationBindings[] = {
		{ 0, 4087921631u, ERegionArchetype::CliffsideSpaceport, 0.26014749964806982, 0.070891539611216248, 0.962962962962963, 30097.45658, 18058.473948, 12038.982632, TEXT("R00_CliffsideSpaceport_MainHub"), TEXT("9F9FA3C4-36CF-52A3-B7AC-674DA3194545"), TEXT("RED_Patch_00") },
		{ 1, 1200338780u, ERegionArchetype::CoralCanopyCoast, -0.40728286329513169, 0.20975512502915319, 0.88888888888888884, 37068.731312, 22241.238787, 14827.492525, TEXT("R01_CoralCanopyCoast_MainHub"), TEXT("5E695431-C567-5AB3-AB1C-C6A09993D388"), TEXT("RED_Patch_01") },
		{ 2, 503587087u, ERegionArchetype::EmberMagentaRift, 0.20073498985791305, -0.54385869617488181, 0.81481481481481488, 42562.092397, 25537.255438, 17024.836959, TEXT("R02_EmberMagentaRift_MainHub"), TEXT("C998BD04-1E6E-531A-94E2-D33EDC08F0DC"), TEXT("RED_Patch_02") },
		{ 3, 31195182u, ERegionArchetype::FungalCathedral, 0.25419295339884346, 0.62184330618672123, 0.7407407407407407, 44405.236507, 26643.141904, 17762.094603, TEXT("R03_FungalCathedral_MainHub"), TEXT("6713DE01-93B0-5F0A-8828-9CFD31671628"), TEXT("RED_Patch_03") },
		{ 4, 1774671415u, ERegionArchetype::MonolithicPillarCavern, -0.67400599048398047, -0.31823180285330355, 0.66666666666666674, 42538.943442, 25523.366065, 17015.577377, TEXT("R04_MonolithicPillarCavern_MainHub"), TEXT("D030FEAC-8913-5FC2-8F70-A2E0B1FCFDDE"), TEXT("RED_Patch_04") },
		{ 5, 3761954552u, ERegionArchetype::VerdantSkyPlateau, 0.76940447797480416, -0.23843399186506264, 0.59259259259259256, 41185.163926, 24711.098356, 16474.06557, TEXT("R05_VerdantSkyPlateau_MainHub"), TEXT("0821D35B-EF67-5F98-BA30-AFBFA668D140"), TEXT("RED_Patch_05") },
		{ 6, 859365926u, ERegionArchetype::PortalOasis, -0.4312739309372749, 0.73833687599040543, 0.5185185185185186, 28761.361764, 17256.817058, 11504.544705, TEXT("R06_PortalOasis_MainHub"), TEXT("D02874C6-658A-566E-A309-F02688E37832"), TEXT("RED_Patch_06") },
		{ 7, 2952538554u, ERegionArchetype::CliffsideSpaceport, -0.18934244766908584, -0.87556757210003422, 0.44444444444444442, 29534.305902, 17720.583541, 11813.722361, TEXT("R07_CliffsideSpaceport_MainHub"), TEXT("A4D672AA-B5ED-5C57-B033-0F4105CA06E4"), TEXT("RED_Patch_07") },
		{ 8, 1406488490u, ERegionArchetype::CoralCanopyCoast, 0.75804682072430551, 0.53683405847755916, 0.37037037037037029, 49453.194407, 29671.916644, 19781.277763, TEXT("R08_CoralCanopyCoast_MainHub"), TEXT("E0AC3702-3173-5BD6-AB08-166C14AAC804"), TEXT("RED_Patch_08") },
		{ 9, 3437484218u, ERegionArchetype::EmberMagentaRift, -0.94759230217643664, 0.11948779710521976, 0.29629629629629628, 25390.687608, 15234.412565, 10156.275043, TEXT("R09_EmberMagentaRift_MainHub"), TEXT("DB8A12DD-8354-5E59-97F4-24618BE35D59"), TEXT("RED_Patch_09") },
		{ 10, 3035973309u, ERegionArchetype::FungalCathedral, 0.6308888631496602, -0.74336836514903337, 0.22222222222222221, 48990.84264, 29394.505584, 19596.337056, TEXT("R10_FungalCathedral_MainHub"), TEXT("D2DCB61A-E5BC-5E22-8D37-57BDEB9FA67C"), TEXT("RED_Patch_10") },
		{ 11, 903397063u, ERegionArchetype::MonolithicPillarCavern, 0.037469560167508374, 0.98825510788516957, 0.14814814814814814, 27253.320947, 16351.992568, 10901.328379, TEXT("R11_MonolithicPillarCavern_MainHub"), TEXT("76019238-C07C-5000-8DD9-EA1276A859A8"), TEXT("RED_Patch_11") },
		{ 12, 3551726211u, ERegionArchetype::VerdantSkyPlateau, -0.70101130085320162, -0.709292737609917, 0.07407407407407407, 25184.477877, 15110.686726, 10073.791151, TEXT("R12_VerdantSkyPlateau_MainHub"), TEXT("2D1EC31B-62EF-5C17-A86E-325A6249FA2B"), TEXT("RED_Patch_12") },
		{ 13, 2253223459u, ERegionArchetype::PortalOasis, 0.99876815020496024, 0.04962038025007523, 0.0, 47737.896308, 28642.737785, 19095.158523, TEXT("R13_PortalOasis_MainHub"), TEXT("10F07CDC-C04F-5DF8-B0F5-E3938171A274"), TEXT("RED_Patch_13") },
		{ 14, 2163523207u, ERegionArchetype::CliffsideSpaceport, -0.76786330571460237, 0.63631672560691932, -0.074074074074074181, 36343.947729, 21806.368637, 14537.579092, TEXT("R14_CliffsideSpaceport_MainHub"), TEXT("5D2B841C-1315-524E-B674-D10431D68AD0"), TEXT("RED_Patch_14") },
		{ 15, 3354735782u, ERegionArchetype::CoralCanopyCoast, 0.13523942097797426, -0.97967465273621157, -0.14814814814814814, 39802.096176, 23881.257706, 15920.838471, TEXT("R15_CoralCanopyCoast_MainHub"), TEXT("EE37C6F3-C688-5390-B27E-3FB177050588"), TEXT("RED_Patch_15") },
		{ 16, 1595341312u, ERegionArchetype::EmberMagentaRift, 0.55410057125043877, 0.802240513119697, -0.22222222222222232, 35390.745723, 21234.447434, 14156.298289, TEXT("R16_EmberMagentaRift_MainHub"), TEXT("D2685469-D7BF-5BD9-BBC3-033B1740FAC9"), TEXT("RED_Patch_16") },
		{ 17, 853668656u, ERegionArchetype::FungalCathedral, -0.931082559992262, -0.21282333349365828, -0.29629629629629628, 35542.968544, 21325.781126, 14217.187418, TEXT("R17_FungalCathedral_MainHub"), TEXT("AF824AA1-DEFB-541C-A142-4AB90974E15D"), TEXT("RED_Patch_17") },
		{ 18, 2119757880u, ERegionArchetype::MonolithicPillarCavern, 0.80752411446105132, -0.45905402004078927, -0.37037037037037046, 31142.396101, 18685.437661, 12456.95844, TEXT("R18_MonolithicPillarCavern_MainHub"), TEXT("29C8CA08-5EFC-529F-9176-A5F7CEBFD055"), TEXT("RED_Patch_18") },
		{ 19, 273275791u, ERegionArchetype::VerdantSkyPlateau, -0.27519501032682503, 0.85248861698775058, -0.44444444444444442, 29222.837342, 17533.702405, 11689.134937, TEXT("R19_VerdantSkyPlateau_MainHub"), TEXT("423C744D-0123-5FD8-9E7F-6BD9B102862E"), TEXT("RED_Patch_19") },
		{ 20, 3729679181u, ERegionArchetype::PortalOasis, -0.35596732939092, -0.77744826603424677, -0.5185185185185186, 28783.749269, 17270.249562, 11513.499708, TEXT("R20_PortalOasis_MainHub"), TEXT("D6E1BDCE-EE5B-50B2-B50D-F40346132723"), TEXT("RED_Patch_20") },
		{ 21, 859727408u, ERegionArchetype::CliffsideSpaceport, 0.74198242785719837, 0.31352208208597848, -0.59259259259259256, 43477.129547, 26086.277728, 17390.851819, TEXT("R21_CliffsideSpaceport_MainHub"), TEXT("371F9EE5-E8EE-541B-8F74-0460F84976AB"), TEXT("RED_Patch_21") },
		{ 22, 1979114190u, ERegionArchetype::CoralCanopyCoast, -0.70222960184983785, 0.24985824349293265, -0.66666666666666674, 46210.005654, 27726.003392, 18484.002261, TEXT("R22_CoralCanopyCoast_MainHub"), TEXT("FFDFEC26-64C9-58B1-9880-A3BA5593F9B9"), TEXT("RED_Patch_22") },
		{ 23, 1750913703u, ERegionArchetype::EmberMagentaRift, 0.31457739715459826, -0.593585896232632, -0.7407407407407407, 38485.612779, 23091.367667, 15394.245112, TEXT("R23_EmberMagentaRift_MainHub"), TEXT("8664FF55-7DBE-5D09-9943-B4EF225CC9DC"), TEXT("RED_Patch_23") },
		{ 24, 1277877202u, ERegionArchetype::FungalCathedral, 0.1458400336007882, 0.56107709110034054, -0.81481481481481488, 44167.677711, 26500.606626, 17667.071084, TEXT("R24_FungalCathedral_MainHub"), TEXT("ECFC214E-1CC9-5D0B-A23B-12FB4E1DE000"), TEXT("RED_Patch_24") },
		{ 25, 3647120752u, ERegionArchetype::MonolithicPillarCavern, -0.38448663849100112, -0.24909148526548797, -0.88888888888888884, 38974.271058, 23384.562635, 15589.708423, TEXT("R25_MonolithicPillarCavern_MainHub"), TEXT("09120C3A-B32A-56F5-916F-DC39130F1C90"), TEXT("RED_Patch_25") },
		{ 26, 3547374410u, ERegionArchetype::VerdantSkyPlateau, 0.265893102429119, -0.044757011095572043, -0.962962962962963, 36510.539741, 21906.323845, 14604.215896, TEXT("R26_VerdantSkyPlateau_MainHub"), TEXT("162A8A2C-6C23-5A5C-9626-ED819447FDBB"), TEXT("RED_Patch_26") }
	};
	// END GENERATED AUTHENTICATED RESERVATION BINDINGS

	constexpr const TCHAR* AuthenticatedReservationDatasetSha256 =
		TEXT("D6DE83918473FFD5D8E27AF5502A39A1E25B3370F7D837F62C831A302F66F3B5");
	constexpr double DirectionTolerance = 1.0e-12;
	constexpr double RadiusToleranceCm = 1.0e-5;
	constexpr double GeodesicBoundaryToleranceCm = 1.0e-4;

	static_assert(UE_ARRAY_COUNT(FrozenReservationBindings) == FPlanet50KmProfile::RegionCount,
		"Authenticated reservation count must remain 27");
	static_assert(FPlanet50KmProfile::LayoutSeed == 0x52454435u,
		"Authenticated reservations require the RED5 layout seed");
	static_assert(FPlanet50KmProfile::RadiusCm == 795774.7154594767,
		"Authenticated reservations require the protected 50 km radius");

	const FName& GetReservationBodyIdName()
	{
		static const FName BodyId(TEXT("planet.red.mars"));
		return BodyId;
	}

	const TArray<FName>& GetBlockedFeatureTags()
	{
		static const TArray<FName> Tags = {
			TEXT("Foliage"), TEXT("Rock"), TEXT("Creature"),
			TEXT("Resource"), TEXT("Water"), TEXT("POI")
		};
		return Tags;
	}

	FName ToArchetypeTag(const ERegionArchetype Archetype)
	{
		switch (Archetype)
		{
		case ERegionArchetype::CoralCanopyCoast:
			return TEXT("CoralCanopyCoast");
		case ERegionArchetype::EmberMagentaRift:
			return TEXT("EmberMagentaRift");
		case ERegionArchetype::FungalCathedral:
			return TEXT("FungalCathedral");
		case ERegionArchetype::MonolithicPillarCavern:
			return TEXT("MonolithicPillarCavern");
		case ERegionArchetype::VerdantSkyPlateau:
			return TEXT("VerdantSkyPlateau");
		case ERegionArchetype::PortalOasis:
			return TEXT("PortalOasis");
		case ERegionArchetype::CliffsideSpaceport:
			return TEXT("CliffsideSpaceport");
		default:
			return NAME_None;
		}
	}

	bool IsAuthenticatedLayout()
	{
		static const bool bAuthenticated = []
		{
			const auto& Regions = FPlanetRegionService::Get().GetRegions();
			for (int32 Index = 0; Index < FPlanet50KmProfile::RegionCount; ++Index)
			{
				const FPlanetRegionMetadata& Metadata = Regions[Index];
				const FFrozenReservationBinding& Binding = FrozenReservationBindings[Index];
				const bool bMatches = Metadata.RegionIndex == Binding.RegionIndex
					&& Metadata.StableSeed == Binding.StableSeed
					&& Metadata.Archetype == Binding.Archetype
					&& FMath::IsNearlyEqual(Metadata.UnitSite.X, Binding.UnitX, DirectionTolerance)
					&& FMath::IsNearlyEqual(Metadata.UnitSite.Y, Binding.UnitY, DirectionTolerance)
					&& FMath::IsNearlyEqual(Metadata.UnitSite.Z, Binding.UnitZ, DirectionTolerance)
					&& FMath::IsNearlyEqual(Metadata.SuggestedHubRadiusCm,
						Binding.SuggestedHubRadiusCm, RadiusToleranceCm)
					&& FMath::IsNearlyEqual(Metadata.SuggestedFlattenCoreRadiusCm,
						Binding.ProtectedRadiusCm, RadiusToleranceCm)
					&& FMath::IsNearlyEqual(Metadata.SuggestedFlattenBlendRadiusCm,
						Binding.BlendRadiusCm, RadiusToleranceCm);
				if (!bMatches)
				{
					UE_LOG(LogTemp, Error,
						TEXT("RED hub reservation dataset %s rejected service drift at region %d"),
						AuthenticatedReservationDatasetSha256, Index);
					return false;
				}
			}
			return true;
		}();
		return bAuthenticated;
	}

	bool TryMakeReservation(
		const FFrozenReservationBinding& Binding,
		FRedPlanetHubReservation& OutReservation)
	{
		FGuid ParsedGuid;
		if (!FGuid::ParseExact(Binding.StableGuid, EGuidFormats::DigitsWithHyphens, ParsedGuid))
		{
			OutReservation = FRedPlanetHubReservation();
			return false;
		}

		FRedPlanetHubReservation Result;
		Result.BodyId = GetReservationBodyIdName();
		Result.AuthoringRegionId = FName(*FString::Printf(
			TEXT("planet.red.mars.authoring-region.r%02d"), Binding.RegionIndex));
		Result.ReservationId = FName(Binding.ReservationId);
		Result.StableGuid = ParsedGuid;
		Result.RegionIndex = Binding.RegionIndex;
		Result.StableSeed = static_cast<int64>(Binding.StableSeed);
		Result.SourcePatch = FName(Binding.SourcePatch);
		Result.ArchetypeTag = ToArchetypeTag(Binding.Archetype);
		Result.UnitCenterDirection = FVector(Binding.UnitX, Binding.UnitY, Binding.UnitZ);
		Result.PlanetRadiusCm = FPlanet50KmProfile::RadiusCm;
		Result.SuggestedHubRadiusCm = Binding.SuggestedHubRadiusCm;
		Result.ProtectedRadiusCm = Binding.ProtectedRadiusCm;
		Result.BlendRadiusCm = Binding.BlendRadiusCm;
		Result.BlockedFeatureTags = GetBlockedFeatureTags();
		OutReservation = MoveTemp(Result);
		return true;
	}

	const TArray<FRedPlanetHubReservation>& GetAuthenticatedReservations()
	{
		static const TArray<FRedPlanetHubReservation> Reservations = []
		{
			TArray<FRedPlanetHubReservation> Result;
			if (!IsAuthenticatedLayout())
			{
				return Result;
			}

			Result.Reserve(FPlanet50KmProfile::RegionCount);
			for (const FFrozenReservationBinding& Binding : FrozenReservationBindings)
			{
				FRedPlanetHubReservation Reservation;
				if (!TryMakeReservation(Binding, Reservation))
				{
					UE_LOG(LogTemp, Error,
						TEXT("RED hub reservation dataset %s rejected invalid GUID at region %d"),
						AuthenticatedReservationDatasetSha256, Binding.RegionIndex);
					Result.Reset();
					return Result;
				}
				Result.Add(MoveTemp(Reservation));
			}
			return Result;
		}();
		return Reservations;
	}

	double GetReservationWeight(
		const FFrozenReservationBinding& Binding,
		const FVector3d& QueryDirection,
		const double NominalRadiusCm)
	{
		const FVector3d ReservationDirection(Binding.UnitX, Binding.UnitY, Binding.UnitZ);
		const double Dot = FMath::Clamp(
			FVector3d::DotProduct(QueryDirection, ReservationDirection), -1.0, 1.0);
		const double DistanceCm = FMath::Acos(Dot) * NominalRadiusCm;
		const double HardRadiusCm = FMath::Max(0.0, Binding.ProtectedRadiusCm);
		if (DistanceCm <= HardRadiusCm + GeodesicBoundaryToleranceCm)
		{
			return 1.0;
		}

		const double BlendRadiusCm = FMath::Max(0.0, Binding.BlendRadiusCm);
		if (BlendRadiusCm <= UE_DOUBLE_SMALL_NUMBER
			|| DistanceCm >= HardRadiusCm + BlendRadiusCm - GeodesicBoundaryToleranceCm)
		{
			return 0.0;
		}

		return 1.0 - ((DistanceCm - HardRadiusCm) / BlendRadiusCm);
	}
}

FName URedPlanetHubReservationRegistry::GetReservationBodyId()
{
	return GetReservationBodyIdName();
}

FString URedPlanetHubReservationRegistry::GetReservationDatasetSha256()
{
	return AuthenticatedReservationDatasetSha256;
}

int32 URedPlanetHubReservationRegistry::GetHubReservationCount()
{
	return GetAuthenticatedReservations().Num();
}

bool URedPlanetHubReservationRegistry::GetHubReservation(
	const int32 RegionIndex,
	FRedPlanetHubReservation& OutReservation)
{
	const TArray<FRedPlanetHubReservation>& Reservations = GetAuthenticatedReservations();
	if (!Reservations.IsValidIndex(RegionIndex))
	{
		OutReservation = FRedPlanetHubReservation();
		return false;
	}

	OutReservation = Reservations[RegionIndex];
	return true;
}

TArray<FRedPlanetHubReservation> URedPlanetHubReservationRegistry::GetAllHubReservations()
{
	return GetAuthenticatedReservations();
}

FRedPlanetHubProtectionQuery URedPlanetHubReservationRegistry::QueryFeatureProtection(
	const UObject* WorldContextObject,
	const FName BodyId,
	const FName FeatureTag,
	const FVector& WorldPoint)
{
	FRedPlanetHubProtectionQuery Result;
	if (!IsInGameThread() || !WorldContextObject || !GEngine || BodyId.IsNone()
		|| BodyId != GetReservationBodyIdName() || FeatureTag.IsNone()
		|| WorldPoint.ContainsNaN())
	{
		return Result;
	}

	UWorld* World = GEngine->GetWorldFromContextObject(
		WorldContextObject, EGetWorldErrorMode::ReturnNull);
	RedCelestialFrames::FFrameSnapshot BodyFrame;
	if (!World || !RedCelestialFrames::ResolveExact(World, BodyId, BodyFrame)
		|| BodyFrame.StableId != BodyId || BodyFrame.Center.ContainsNaN()
		|| !FMath::IsFinite(BodyFrame.NominalRadiusCm)
		|| BodyFrame.NominalRadiusCm <= 0.0
		|| !FMath::IsNearlyEqual(
			BodyFrame.NominalRadiusCm,
			RedPlanet::FPlanet50KmProfile::RadiusCm,
			1.0))
	{
		return Result;
	}

	return QueryFeatureProtectionAtCenter(
		BodyId, FeatureTag, WorldPoint, BodyFrame.Center,
		BodyFrame.NominalRadiusCm);
}

FRedPlanetHubProtectionQuery
URedPlanetHubReservationRegistry::QueryFeatureProtectionAtCenter(
	const FName BodyId,
	const FName FeatureTag,
	const FVector& WorldPoint,
	const FVector& ResolvedBodyCenter,
	const double NominalRadiusCm)
{
	FRedPlanetHubProtectionQuery Result;
	const TArray<FRedPlanetHubReservation>& Reservations = GetAuthenticatedReservations();
	if (Reservations.Num() != RedPlanet::FPlanet50KmProfile::RegionCount)
	{
		return Result;
	}

	const FVector PointOffset = WorldPoint - ResolvedBodyCenter;
	if (BodyId.IsNone() || BodyId != GetReservationBodyIdName() || FeatureTag.IsNone()
		|| WorldPoint.ContainsNaN() || ResolvedBodyCenter.ContainsNaN()
		|| !FMath::IsFinite(NominalRadiusCm) || NominalRadiusCm <= 0.0
		|| !FMath::IsNearlyEqual(
			NominalRadiusCm, RedPlanet::FPlanet50KmProfile::RadiusCm, 1.0)
		|| PointOffset.ContainsNaN() || PointOffset.IsNearlyZero())
	{
		return Result;
	}

	// The placement taxonomy is closed. Typos and future, unregistered feature classes must
	// never bypass a protected hub footprint.
	if (!GetBlockedFeatureTags().Contains(FeatureTag))
	{
		return Result;
	}

	Result.bQueryValid = true;
	Result.bBlocked = false;
	Result.ProtectionWeight = 0.0f;

	const FVector3d QueryDirection = FVector3d(PointOffset).GetSafeNormal();
	double BestWeight = 0.0;
	for (int32 Index = 0; Index < Reservations.Num(); ++Index)
	{
		const double Weight = GetReservationWeight(
			FrozenReservationBindings[Index], QueryDirection, NominalRadiusCm);
		if (Weight > BestWeight)
		{
			BestWeight = Weight;
			Result.ReservationId = Reservations[Index].ReservationId;
			Result.StableGuid = Reservations[Index].StableGuid;
		}
	}

	Result.ProtectionWeight = static_cast<float>(BestWeight);
	Result.bBlocked = Result.ProtectionWeight > 0.0f;
	return Result;
}
