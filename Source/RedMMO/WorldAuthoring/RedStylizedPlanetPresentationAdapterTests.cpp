#include "RedStylizedPlanetPresentationAdapter.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Engine/StaticMesh.h"
#include "Materials/Material.h"
#include "Misc/AutomationTest.h"

namespace RedStylizedPlanetPresentationAdapterTests
{
	FRedPlanetHubProtectionQuery MakeProtection(
		const float Weight,
		const TCHAR* ReservationId = TEXT("R00_Test_MainHub"))
	{
		FRedPlanetHubProtectionQuery Result;
		Result.bQueryValid = true;
		Result.ProtectionWeight = Weight;
		Result.bBlocked = Weight > 0.0f;
		Result.ReservationId = FName(ReservationId);
		FGuid::ParseExact(
			TEXT("9F9FA3C4-36CF-52A3-B7AC-674DA3194545"),
			EGuidFormats::DigitsWithHyphens,
			Result.StableGuid);
		return Result;
	}

	URedStylizedPlanetPresentationProfile* MakeProfile()
	{
		URedStylizedPlanetPresentationProfile* Profile =
			NewObject<URedStylizedPlanetPresentationProfile>();
		Profile->ProfileId = TEXT("presentation.red.scratch.stylized");
		Profile->BodyId = TEXT("planet.red.mars");
		Profile->SourceContract =
			ERedStylizedPlanetSourceContract::PlanetGen14VertexLayers;
		Profile->StylizedTerrainMaterialHook = NewObject<UMaterial>();
		Profile->StylizedWaterMaterialHook = NewObject<UMaterial>();

		URedWorldAssetPalette* Palette = NewObject<URedWorldAssetPalette>();
		Palette->PaletteId = TEXT("palette.red.scratch.tropical");

		FRedWorldAssetPaletteEntry ApprovedFoliage;
		ApprovedFoliage.EntryId = TEXT("foliage.lowpoly.tree.a");
		ApprovedFoliage.Mesh = NewObject<UStaticMesh>();
		ApprovedFoliage.Role = ERedWorldAssetRole::BiomeAnchor;
		ApprovedFoliage.bApprovedForPCG = true;
		ApprovedFoliage.bHandPlacementOnly = false;
		Palette->Entries.Add(ApprovedFoliage);

		FRedWorldAssetPaletteEntry ApprovedRock;
		ApprovedRock.EntryId = TEXT("rock.lowpoly.a");
		ApprovedRock.Mesh = NewObject<UStaticMesh>();
		ApprovedRock.Role = ERedWorldAssetRole::Rock;
		ApprovedRock.bApprovedForPCG = true;
		ApprovedRock.bHandPlacementOnly = false;
		Palette->Entries.Add(ApprovedRock);

		FRedWorldAssetPaletteEntry HandOnly;
		HandOnly.EntryId = TEXT("foliage.hero.handonly");
		HandOnly.Mesh = NewObject<UStaticMesh>();
		HandOnly.Role = ERedWorldAssetRole::HeroLandmark;
		HandOnly.bApprovedForPCG = false;
		HandOnly.bHandPlacementOnly = true;
		Palette->Entries.Add(HandOnly);

		FRedStylizedBiomePresentationBinding Tropical;
		Tropical.SourceBiomeId = TEXT("Tropical");
		Tropical.SourceBiomeIndex = 3;
		Tropical.AssetPalette = Palette;
		Tropical.FoliageEntryIds = {
			TEXT("foliage.lowpoly.tree.a"),
			TEXT("foliage.hero.handonly")
		};
		Tropical.RockEntryIds = { TEXT("rock.lowpoly.a") };
		Profile->BiomeBindings.Add(Tropical);
		return Profile;
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FRedStylizedPlanetPresentationMappingTest,
	"RedMMO.WorldAuthoring.StylizedPlanetPresentation.Mapping",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRedStylizedPlanetPresentationMappingTest::RunTest(const FString& Parameters)
{
	using namespace RedStylizedPlanetPresentationAdapterTests;
	(void)Parameters;

	URedStylizedPlanetPresentationProfile* Profile = MakeProfile();
	FRedStylizedPlanetSourceSignal Signal;
	Signal.TerrainLayerVertexWeights =
		FLinearColor(-1.0f, 0.35f, 1.25f, 0.10f);
	Signal.AuxiliaryLayerWeights = FVector2D(0.45f, 0.80f);
	Signal.ClimateBiomeIndex = 3;

	const FRedPlanetHubProtectionQuery Outside = MakeProtection(0.0f);
	const FRedStylizedPlanetPresentationResult Result =
		URedStylizedPlanetPresentationAdapter::EvaluateFromSignals(
			Profile, Signal, Outside, Outside, Outside);

	TestTrue(TEXT("Mapping is valid"), Result.bMappingValid);
	TestTrue(TEXT("Authenticated protection inputs are valid"),
		Result.bProtectionQueryValid);
	TestTrue(TEXT("Configured profile is ready for a later scratch binding"),
		Result.bReadyForScratchBinding);
	TestFalse(TEXT("Tropical binding resolves without fallback"),
		Result.bUsedFallbackBiomeBinding);
	TestEqual(TEXT("PlanetGen climate index resolves"), Result.ResolvedBiomeIndex, 3);
	TestEqual(TEXT("PlanetGen climate identity resolves"),
		Result.ResolvedBiomeId, FName(TEXT("Tropical")));
	TestEqual(TEXT("Negative water clamps to zero"), Result.SurfaceLayers.Water, 0.0f);
	TestEqual(TEXT("Rock above one clamps to one"), Result.SurfaceLayers.Rock, 1.0f);
	TestEqual(TEXT("Dominant layer is rock"),
		Result.DominantSurfaceLayer, FName(TEXT("Rock")));
	TestTrue(TEXT("Terrain material hook is present"), Result.bHasTerrainMaterialHook);
	TestTrue(TEXT("Water material hook is present"), Result.bHasWaterMaterialHook);
	TestEqual(TEXT("Only approved foliage hook is exposed"),
		Result.FoliageMeshHooks.Num(), 1);
	TestEqual(TEXT("Approved rock hook is exposed"),
		Result.RockMeshHooks.Num(), 1);
	TestEqual(TEXT("Outside hubs keeps procedural presentation"),
		Result.ProceduralTerrainPresentationWeight, 1.0f);
	TestEqual(TEXT("Outside hubs keeps procedural foliage"),
		Result.ProceduralFoliageWeight, 1.0f);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FRedStylizedPlanetPresentationHubBlendTest,
	"RedMMO.WorldAuthoring.StylizedPlanetPresentation.HubBlend",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRedStylizedPlanetPresentationHubBlendTest::RunTest(const FString& Parameters)
{
	using namespace RedStylizedPlanetPresentationAdapterTests;
	(void)Parameters;

	URedStylizedPlanetPresentationProfile* Profile = MakeProfile();
	FRedStylizedPlanetSourceSignal Signal;
	Signal.ClimateBiomeIndex = 3;

	const FRedPlanetHubProtectionQuery HalfBlend = MakeProtection(0.5f);
	const FRedStylizedPlanetPresentationResult HalfResult =
		URedStylizedPlanetPresentationAdapter::EvaluateFromSignals(
			Profile, Signal, HalfBlend, HalfBlend, HalfBlend);
	TestEqual(TEXT("Half blend exposes authored hub weight"),
		HalfResult.AuthoredHubBlendWeight, 0.5f);
	TestEqual(TEXT("Half blend attenuates procedural terrain presentation"),
		HalfResult.ProceduralTerrainPresentationWeight, 0.5f);
	TestEqual(TEXT("Half blend attenuates procedural foliage"),
		HalfResult.ProceduralFoliageWeight, 0.5f);
	TestEqual(TEXT("Half blend attenuates procedural rocks"),
		HalfResult.ProceduralRockWeight, 0.5f);
	TestEqual(TEXT("Half blend attenuates only local water decoration"),
		HalfResult.ProceduralWaterDecorationWeight, 0.5f);

	const FRedPlanetHubProtectionQuery HardCore = MakeProtection(1.0f);
	const FRedStylizedPlanetPresentationResult HardResult =
		URedStylizedPlanetPresentationAdapter::EvaluateFromSignals(
			Profile, Signal, HardCore, HardCore, HardCore);
	TestEqual(TEXT("Hard hub owns presentation blend"),
		HardResult.AuthoredHubBlendWeight, 1.0f);
	TestEqual(TEXT("Hard hub suppresses procedural presentation"),
		HardResult.ProceduralTerrainPresentationWeight, 0.0f);

	FRedPlanetHubProtectionQuery Invalid;
	const FRedStylizedPlanetPresentationResult InvalidResult =
		URedStylizedPlanetPresentationAdapter::EvaluateFromSignals(
			Profile, Signal, Invalid, Invalid, Invalid);
	TestFalse(TEXT("Invalid protection is reported"),
		InvalidResult.bProtectionQueryValid);
	TestFalse(TEXT("Invalid protection is not ready for binding"),
		InvalidResult.bReadyForScratchBinding);
	TestEqual(TEXT("Invalid protection fails closed to authored weight"),
		InvalidResult.AuthoredHubBlendWeight, 1.0f);
	TestEqual(TEXT("Invalid protection fails closed for foliage"),
		InvalidResult.ProceduralFoliageWeight, 0.0f);
	TestEqual(TEXT("Invalid protection fails closed for rocks"),
		InvalidResult.ProceduralRockWeight, 0.0f);
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
