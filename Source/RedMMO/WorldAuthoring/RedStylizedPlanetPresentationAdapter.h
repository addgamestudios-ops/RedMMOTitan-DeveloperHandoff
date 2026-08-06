#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "RedPlanetHubReservationRegistry.h"
#include "RedWorldAssetPalette.h"
#include "RedStylizedPlanetPresentationAdapter.generated.h"

class UMaterialInterface;

/**
 * Presentation-source contracts supported by the project-owned adapter.
 *
 * This enum does not enable either plugin. It documents how an already-generated
 * surface describes its biome/layer outputs to the adapter.
 */
UENUM(BlueprintType)
enum class ERedStylizedPlanetSourceContract : uint8
{
	PlanetGen14VertexLayers UMETA(DisplayName = "PlanetGen 1.4 Vertex Layers"),
	PPG10NamedBiomes UMETA(DisplayName = "PPG 1.0 Named Biomes")
};

/**
 * Existing generator outputs supplied to the presentation adapter.
 *
 * PlanetGen 1.4 uses TerrainLayerVertexWeights as R=water, G=grass, B=rock,
 * A=snow and AuxiliaryLayerWeights as X=beach, Y=desert sand. PPG callers use
 * NamedBiomeId and may additionally pass vertex-color masks.
 */
USTRUCT(BlueprintType)
struct REDMMO_API FRedStylizedPlanetSourceSignal
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet|Presentation")
	FLinearColor TerrainLayerVertexWeights = FLinearColor::Transparent;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet|Presentation")
	FVector2D AuxiliaryLayerWeights = FVector2D::ZeroVector;

	/** PlanetGen 1.4 climate slot: 0=tundra, 1=boreal, 2=desert, 3=tropical. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet|Presentation")
	int32 ClimateBiomeIndex = INDEX_NONE;

	/** Named PPG biome identity. Ignored by the PlanetGen 1.4 contract. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet|Presentation")
	FName NamedBiomeId = NAME_None;
};

/** Clamped presentation weights decoded from the generator-owned surface. */
USTRUCT(BlueprintType)
struct REDMMO_API FRedStylizedSurfaceLayerWeights
{
	GENERATED_BODY()

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	float Water = 0.0f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	float Grass = 0.0f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	float Rock = 0.0f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	float Snow = 0.0f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	float Beach = 0.0f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	float DesertSand = 0.0f;
};

/**
 * One generator-biome to project-owned stylized palette binding.
 *
 * Entry IDs resolve only through an approved Red world palette. The adapter
 * exposes eligible entries; it never loads or spawns their meshes.
 */
USTRUCT(BlueprintType)
struct REDMMO_API FRedStylizedBiomePresentationBinding
{
	GENERATED_BODY()

	/** PPG named biome identity. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	FName SourceBiomeId = NAME_None;

	/** PlanetGen 1.4 climate slot. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	int32 SourceBiomeIndex = INDEX_NONE;

	/**
	 * Optional PPG per-biome surface-material hook.
	 *
	 * PlanetGen 1.4 has one terrain material and deliberately ignores this
	 * override; its stylized material must consume the existing vertex/UV masks.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	TSoftObjectPtr<UMaterialInterface> PPGSurfaceMaterialHook;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	TObjectPtr<URedWorldAssetPalette> AssetPalette = nullptr;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	TArray<FName> FoliageEntryIds;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	TArray<FName> RockEntryIds;
};

/**
 * Scratch-only presentation profile.
 *
 * The profile contains references, not generated terrain settings. It has no
 * radius, sea datum, atmosphere, gravity, collision, replication, or streaming
 * authority.
 */
UCLASS(BlueprintType)
class REDMMO_API URedStylizedPlanetPresentationProfile : public UDataAsset
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	FName ProfileId = NAME_None;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	FName BodyId = TEXT("planet.red.mars");

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	ERedStylizedPlanetSourceContract SourceContract =
		ERedStylizedPlanetSourceContract::PlanetGen14VertexLayers;

	/**
	 * PlanetGen 1.4 hook: one sphere-safe material consuming its existing
	 * R/G/B/A vertex layers and UV1 beach/desert signals.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	TSoftObjectPtr<UMaterialInterface> StylizedTerrainMaterialHook;

	/** Presentation-only replacement hook. It does not alter the water radius or sea datum. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	TSoftObjectPtr<UMaterialInterface> StylizedWaterMaterialHook;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	FRedStylizedBiomePresentationBinding FallbackBinding;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	TArray<FRedStylizedBiomePresentationBinding> BiomeBindings;

	const FRedStylizedBiomePresentationBinding& ResolveBinding(
		const FRedStylizedPlanetSourceSignal& SourceSignal,
		bool& bOutUsedFallback) const;
};

/**
 * Query-only result for a future scratch material/PCG bridge.
 *
 * Procedural water decoration weight applies only to local decorative water
 * placement. It never disables or moves the generator-owned global water shell.
 */
USTRUCT(BlueprintType)
struct REDMMO_API FRedStylizedPlanetPresentationResult
{
	GENERATED_BODY()

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	bool bMappingValid = false;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	bool bProtectionQueryValid = false;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	bool bReadyForScratchBinding = false;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	bool bUsedFallbackBiomeBinding = true;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	bool bHasTerrainMaterialHook = false;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	bool bHasWaterMaterialHook = false;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	FName ResolvedBiomeId = NAME_None;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	int32 ResolvedBiomeIndex = INDEX_NONE;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	FName DominantSurfaceLayer = NAME_None;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	FRedStylizedSurfaceLayerWeights SurfaceLayers;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	TSoftObjectPtr<UMaterialInterface> TerrainMaterialHook;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	TSoftObjectPtr<UMaterialInterface> WaterMaterialHook;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	TArray<FRedWorldAssetPaletteEntry> FoliageMeshHooks;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	TArray<FRedWorldAssetPaletteEntry> RockMeshHooks;

	/** 1 in a protected hub, fades through the authenticated geodesic blend ring, 0 outside. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation",
		meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float AuthoredHubBlendWeight = 1.0f;

	/** Presentation-layer weight only; it never changes terrain position or collision. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation",
		meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float ProceduralTerrainPresentationWeight = 0.0f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation",
		meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float ProceduralFoliageWeight = 0.0f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation",
		meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float ProceduralRockWeight = 0.0f;

	/** Local decoration only; the global water material remains selected independently. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation",
		meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float ProceduralWaterDecorationWeight = 0.0f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	FName ReservationId = NAME_None;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Presentation")
	FGuid ReservationGuid;
};

/**
 * Reversible, query-only bridge between generated biome outputs and stylized
 * project-owned presentation assets.
 *
 * It does not set a material, regenerate a planet, spawn foliage, or mutate an
 * authored hub. A later approved scratch consumer must explicitly consume the
 * returned hooks and weights.
 */
UCLASS()
class REDMMO_API URedStylizedPlanetPresentationAdapter : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintPure, Category = "RedMMO|Planet|Presentation")
	static FRedStylizedPlanetPresentationResult EvaluateFromSignals(
		const URedStylizedPlanetPresentationProfile* Profile,
		const FRedStylizedPlanetSourceSignal& SourceSignal,
		const FRedPlanetHubProtectionQuery& FoliageProtection,
		const FRedPlanetHubProtectionQuery& RockProtection,
		const FRedPlanetHubProtectionQuery& WaterDecorationProtection);

	UFUNCTION(BlueprintCallable, Category = "RedMMO|Planet|Presentation",
		meta = (WorldContext = "WorldContextObject"))
	static FRedStylizedPlanetPresentationResult EvaluateAtWorldPoint(
		const UObject* WorldContextObject,
		const URedStylizedPlanetPresentationProfile* Profile,
		const FRedStylizedPlanetSourceSignal& SourceSignal,
		const FVector& WorldPoint);
};
