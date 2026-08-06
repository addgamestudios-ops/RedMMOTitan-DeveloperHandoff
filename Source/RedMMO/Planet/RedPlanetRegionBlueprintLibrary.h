#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "RedPlanetRegionBlueprintLibrary.generated.h"

/** Blueprint-safe copy of one deterministic RED planet authoring region. */
USTRUCT(BlueprintType)
struct REDMMO_API FRedPlanetRegionQuery
{
	GENERATED_BODY()

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region")
	int32 RegionIndex = INDEX_NONE;

	/** Unsigned service seed represented as int64 so Blueprint preserves every uint32 value. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region")
	int64 Seed = 0;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region")
	int32 VariationIndex = 0;

	/** Stable authoring name such as CoralCanopyCoast or PortalOasis. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region")
	FName ArchetypeTag = NAME_None;

	/** Unit direction from planet centre to the deterministic region site. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region")
	FVector UnitSite = FVector::UpVector;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region")
	double NominalAreaSquareKm = 0.0;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region", meta = (Units = "cm"))
	double SuggestedHubRadiusCm = 0.0;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region", meta = (Units = "cm"))
	double SuggestedFlattenCoreRadiusCm = 0.0;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region", meta = (Units = "cm"))
	double SuggestedFlattenBlendRadiusCm = 0.0;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region|Climate", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float Temperature01 = 0.5f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region|Climate", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float Moisture01 = 0.5f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region|Climate", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float AlienIntensity01 = 0.5f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region|Climate", meta = (ClampMin = "-1.0", ClampMax = "1.0"))
	float ElevationBias = 0.0f;
};

/** One normalized contributor returned by a blended region query. */
USTRUCT(BlueprintType)
struct REDMMO_API FRedPlanetRegionBlendEntry
{
	GENERATED_BODY()

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region")
	FRedPlanetRegionQuery Region;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region", meta = (Units = "rad"))
	double GreatCircleDistanceRadians = 0.0;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	double Weight = 0.0;
};

/** Orthonormal surface frame. Local X is east, Y is north, and Z is radial up. */
USTRUCT(BlueprintType)
struct REDMMO_API FRedPlanetTangentFrameQuery
{
	GENERATED_BODY()

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region")
	FVector UnitUp = FVector::UpVector;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region")
	FVector UnitEast = FVector::ForwardVector;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region")
	FVector UnitNorth = FVector::RightVector;
};

/** Reflection boundary for RedPlanet::FPlanetRegionService. It owns no mutable layout state. */
UCLASS()
class REDMMO_API URedPlanetRegionBlueprintLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintPure, Category = "RedMMO|Planet Region")
	static int32 GetPlanetRegionCount();

	UFUNCTION(BlueprintPure, Category = "RedMMO|Planet Region")
	static bool GetPlanetRegion(int32 RegionIndex, FRedPlanetRegionQuery& OutRegion);

	UFUNCTION(BlueprintPure, Category = "RedMMO|Planet Region")
	static TArray<FRedPlanetRegionQuery> GetAllPlanetRegions();

	UFUNCTION(BlueprintPure, Category = "RedMMO|Planet Region")
	static FRedPlanetRegionQuery FindNearestPlanetRegion(const FVector& SurfaceDirection);

	UFUNCTION(BlueprintPure, Category = "RedMMO|Planet Region", meta = (ClampMin = "1", ClampMax = "4"))
	static TArray<FRedPlanetRegionBlendEntry> SamplePlanetRegionBlend(
		const FVector& SurfaceDirection,
		int32 MaxContributors = 4,
		double SigmaRadians = 0.20);

	UFUNCTION(BlueprintPure, Category = "RedMMO|Planet Region|Tangent")
	static FRedPlanetTangentFrameQuery MakePlanetTangentFrame(
		const FVector& SurfaceDirection,
		const FVector& PlanetNorthAxis);

	UFUNCTION(BlueprintPure, Category = "RedMMO|Planet Region|Tangent")
	static FVector PlanetTangentOffsetToDirection(
		const FVector& AnchorSurfaceDirection,
		const FVector2D& LocalOffsetCm,
		double PlanetRadiusCm,
		const FVector& PlanetNorthAxis);

	UFUNCTION(BlueprintPure, Category = "RedMMO|Planet Region|Tangent")
	static FVector PlanetTangentOffsetToPosition(
		const FVector& PlanetCenter,
		const FVector& AnchorSurfaceDirection,
		const FVector2D& LocalOffsetCm,
		double AltitudeCm,
		double PlanetRadiusCm,
		const FVector& PlanetNorthAxis);

	UFUNCTION(BlueprintPure, Category = "RedMMO|Planet Region|Tangent")
	static FVector2D PlanetDirectionToTangentOffset(
		const FVector& AnchorSurfaceDirection,
		const FVector& TargetSurfaceDirection,
		double PlanetRadiusCm,
		const FVector& PlanetNorthAxis);
};
