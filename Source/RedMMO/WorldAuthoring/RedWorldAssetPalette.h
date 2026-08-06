#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "RedWorldAssetPalette.generated.h"

class UStaticMesh;

/** Visual role controls how an approved asset may be used by hand placement and later PCG. */
UENUM(BlueprintType)
enum class ERedWorldAssetRole : uint8
{
	HeroLandmark,
	BiomeAnchor,
	Satellite,
	GroundCover,
	Rock,
	Architecture,
	VFXMarker
};

UENUM(BlueprintType)
enum class ERedWorldCollisionPolicy : uint8
{
	None,
	SimpleQuery,
	SimpleQueryAndPhysics
};

/**
 * One user-approved worldbuilding asset. Marketplace and generated assets stay out of this
 * palette until their scale, pivot, material, collision, variation, and performance are reviewed.
 */
USTRUCT(BlueprintType)
struct REDMMO_API FRedWorldAssetPaletteEntry
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Identity")
	FName EntryId = NAME_None;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Identity")
	TSoftObjectPtr<UStaticMesh> Mesh;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Identity")
	ERedWorldAssetRole Role = ERedWorldAssetRole::Satellite;

	/** Examples: CoralCoast, FungalCathedral, PortalOasis, Wet, Shade, CliffBase. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Placement")
	TArray<FName> BiomeTags;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Placement", meta = (ClampMin = "0.01"))
	FVector2D UniformScaleRange = FVector2D(0.8, 1.25);

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Placement", meta = (ClampMin = "0.0", ClampMax = "90.0"))
	FVector2D AllowedSlopeDegrees = FVector2D(0.0, 35.0);

	/** Radial offset from datum in centimetres. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Placement")
	FVector2D AllowedElevationCm = FVector2D(-30000.0, 30000.0);

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Placement")
	ERedWorldCollisionPolicy CollisionPolicy = ERedWorldCollisionPolicy::None;

	/** Hand placement is always allowed after approval. This separately controls procedural filler. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Approval")
	bool bApprovedForPCG = false;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Approval")
	bool bHandPlacementOnly = true;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Approval")
	bool bNaniteReviewed = false;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Approval", meta = (MultiLine = true))
	FString ReviewNotes;
};

/** Editable, code-free palette selected by the user for one biome or worldbuilding pass. */
UCLASS(BlueprintType)
class REDMMO_API URedWorldAssetPalette : public UDataAsset
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Palette")
	FName PaletteId = NAME_None;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Palette")
	TArray<FName> BiomeTags;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Palette")
	TArray<FRedWorldAssetPaletteEntry> Entries;

	UFUNCTION(BlueprintPure, Category = "RedMMO|World Authoring")
	bool FindEntry(FName EntryId, FRedWorldAssetPaletteEntry& OutEntry) const;
};

