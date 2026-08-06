#include "RedPlanetRegionAnchor.h"

#include "RedPlanetRegionBlueprintLibrary.h"
#include "RedPlanetRegionService.h"
#include "Components/BillboardComponent.h"
#include "Components/SceneComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/Texture2D.h"
#include "Math/RotationMatrix.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
	const FName RegionAnchorTag(TEXT("RedPlanetRegion"));
	const FName LegacyRegionAnchorTag(TEXT("RedPlanetRegionAnchor"));
	const FString RegionIndexTagPrefix(TEXT("RedRegion_"));
	const FString BiomeTagPrefix(TEXT("RedBiome_"));

	bool IsRegionArchetypeTag(const FName Tag)
	{
		static const TArray<FName> RegionArchetypes = {
			TEXT("CoralCanopyCoast"),
			TEXT("EmberMagentaRift"),
			TEXT("FungalCathedral"),
			TEXT("MonolithicPillarCavern"),
			TEXT("VerdantSkyPlateau"),
			TEXT("PortalOasis"),
			TEXT("CliffsideSpaceport")
		};
		return RegionArchetypes.Contains(Tag);
	}

#if WITH_EDITORONLY_DATA
	FColor RegionVisualizationColor(const int32 RegionIndex)
	{
		static const FColor Palette[] = {
			FColor(41, 220, 220),
			FColor(255, 72, 128),
			FColor(214, 128, 255),
			FColor(117, 176, 255),
			FColor(123, 232, 112),
			FColor(255, 208, 74),
			FColor(255, 139, 71)
		};
		return Palette[FMath::Abs(RegionIndex) % UE_ARRAY_COUNT(Palette)];
	}
#endif
}

ARedPlanetRegionAnchor::ARedPlanetRegionAnchor()
{
	PrimaryActorTick.bCanEverTick = false;
	PrimaryActorTick.bStartWithTickEnabled = false;
	bReplicates = false;
	SetReplicateMovement(false);
	bIsEditorOnlyActor = true;
	SetCanBeDamaged(false);
	SetActorEnableCollision(false);

	SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("SceneRoot"));
	SceneRoot->SetMobility(EComponentMobility::Static);
	SceneRoot->SetCanEverAffectNavigation(false);
	SetRootComponent(SceneRoot);

#if WITH_EDITORONLY_DATA
	EditorBillboard = CreateEditorOnlyDefaultSubobject<UBillboardComponent>(TEXT("EditorBillboard"));
	if (EditorBillboard)
	{
		EditorBillboard->SetupAttachment(SceneRoot);
		EditorBillboard->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		EditorBillboard->SetGenerateOverlapEvents(false);
		EditorBillboard->SetCanEverAffectNavigation(false);
		EditorBillboard->SetHiddenInGame(true);
		EditorBillboard->SetRelativeScale3D(FVector(2.0));

		static ConstructorHelpers::FObjectFinderOptional<UTexture2D> RegionSprite(
			TEXT("/Engine/EditorResources/S_TargetPoint.S_TargetPoint"));
		EditorBillboard->SetSprite(RegionSprite.Get());
	}

	EditorLabel = CreateEditorOnlyDefaultSubobject<UTextRenderComponent>(TEXT("EditorLabel"));
	if (EditorLabel)
	{
		EditorLabel->SetupAttachment(SceneRoot);
		EditorLabel->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		EditorLabel->SetGenerateOverlapEvents(false);
		EditorLabel->SetCanEverAffectNavigation(false);
		EditorLabel->SetHiddenInGame(true);
		EditorLabel->SetHorizontalAlignment(EHorizTextAligment::EHTA_Center);
		EditorLabel->SetVerticalAlignment(EVerticalTextAligment::EVRTA_TextCenter);
		EditorLabel->SetWorldSize(2400.0f);
		EditorLabel->SetRelativeLocation(FVector(0.0, 0.0, 4000.0));
	}
#endif

	RefreshFromRegionService();
}

void ARedPlanetRegionAnchor::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	RefreshFromRegionService();
}

void ARedPlanetRegionAnchor::RefreshFromRegionService()
{
	RegionIndex = FMath::Clamp(
		RegionIndex, 0, RedPlanet::FPlanet50KmProfile::RegionCount - 1);

	FRedPlanetRegionQuery Region;
	if (!URedPlanetRegionBlueprintLibrary::GetPlanetRegion(RegionIndex, Region))
	{
		return;
	}

	Seed = Region.Seed;
	VariationIndex = Region.VariationIndex;
	ArchetypeTag = Region.ArchetypeTag;
	UnitSite = Region.UnitSite;
	NominalAreaSquareKm = Region.NominalAreaSquareKm;
	SuggestedHubRadiusCm = Region.SuggestedHubRadiusCm;
	SuggestedFlattenCoreRadiusCm = Region.SuggestedFlattenCoreRadiusCm;
	SuggestedFlattenBlendRadiusCm = Region.SuggestedFlattenBlendRadiusCm;
	Temperature01 = Region.Temperature01;
	Moisture01 = Region.Moisture01;
	AlienIntensity01 = Region.AlienIntensity01;
	ElevationBias = Region.ElevationBias;

	RefreshOwnedActorTags();
	RefreshPlacement();

#if WITH_EDITORONLY_DATA
	RefreshEditorVisualization();
#endif
}

void ARedPlanetRegionAnchor::RefreshOwnedActorTags()
{
	Tags.RemoveAll([](const FName Tag)
	{
		const FString TagString = Tag.ToString();
		return Tag == RegionAnchorTag
			|| Tag == LegacyRegionAnchorTag
			|| TagString.StartsWith(RegionIndexTagPrefix)
			|| TagString.StartsWith(BiomeTagPrefix)
			|| TagString.StartsWith(TEXT("RedPlanetRegion_"))
			|| IsRegionArchetypeTag(Tag);
	});

	Tags.AddUnique(RegionAnchorTag);
	Tags.AddUnique(FName(*FString::Printf(TEXT("%s%02d"), *RegionIndexTagPrefix, RegionIndex)));
	if (!ArchetypeTag.IsNone())
	{
		Tags.AddUnique(FName(*(BiomeTagPrefix + ArchetypeTag.ToString())));
	}
}

void ARedPlanetRegionAnchor::RefreshPlacement()
{
	const FVector SafeUnitSite = UnitSite.GetSafeNormal(SMALL_NUMBER, FVector::UpVector);
	if (bPositionAtRegionSite && IsValid(SceneRoot))
	{
		SetActorLocation(PlanetCenter + (SafeUnitSite * FMath::Max(1.0, PlanetRadiusCm)), false);
	}

	if (bOrientToSurface && IsValid(SceneRoot))
	{
		const FRedPlanetTangentFrameQuery Frame =
			URedPlanetRegionBlueprintLibrary::MakePlanetTangentFrame(SafeUnitSite, FVector::UpVector);
		SetActorRotation(FRotationMatrix::MakeFromXZ(Frame.UnitEast, Frame.UnitUp).Rotator());
	}
}

#if WITH_EDITORONLY_DATA
void ARedPlanetRegionAnchor::RefreshEditorVisualization()
{
	const FColor Color = RegionVisualizationColor(RegionIndex);
	if (EditorLabel)
	{
		EditorLabel->SetText(FText::FromString(FString::Printf(
			TEXT("Region %02d\n%s\nSeed %llu"),
			RegionIndex,
			*ArchetypeTag.ToString(),
			static_cast<unsigned long long>(Seed))));
		EditorLabel->SetTextRenderColor(Color);
	}
}
#endif
