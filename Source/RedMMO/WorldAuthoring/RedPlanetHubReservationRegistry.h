#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "RedPlanetHubReservationRegistry.generated.h"

class FRedPlanetHubReservationProtectionQueriesTest;

/** Immutable runtime copy of one authenticated 50 km hub reservation. */
USTRUCT(BlueprintType)
struct REDMMO_API FRedPlanetHubReservation
{
	GENERATED_BODY()

	/** Stable celestial owner. Current records belong only to RED Mars. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|World Authoring|Reservation")
	FName BodyId = NAME_None;

	/** Immutable namespaced authoring-region identity; independent of archetype labels. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|World Authoring|Reservation")
	FName AuthoringRegionId = NAME_None;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|World Authoring|Reservation")
	FName ReservationId = NAME_None;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|World Authoring|Reservation")
	FGuid StableGuid;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|World Authoring|Reservation")
	int32 RegionIndex = INDEX_NONE;

	/** Unsigned service seed stored as int64 so Blueprint preserves all uint32 values. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|World Authoring|Reservation")
	int64 StableSeed = 0;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|World Authoring|Reservation")
	FName SourcePatch = NAME_None;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|World Authoring|Reservation")
	FName ArchetypeTag = NAME_None;

	/** Unit direction from the owning body's centre to the hub anchor. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|World Authoring|Reservation")
	FVector UnitCenterDirection = FVector::UpVector;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|World Authoring|Reservation", meta = (Units = "cm"))
	double PlanetRadiusCm = 0.0;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|World Authoring|Reservation", meta = (Units = "cm"))
	double SuggestedHubRadiusCm = 0.0;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|World Authoring|Reservation", meta = (Units = "cm"))
	double ProtectedRadiusCm = 0.0;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|World Authoring|Reservation", meta = (Units = "cm"))
	double BlendRadiusCm = 0.0;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|World Authoring|Reservation")
	TArray<FName> BlockedFeatureTags;
};

/** Result returned to future PCG/WorldGen adapters. Invalid inputs fail closed. */
USTRUCT(BlueprintType)
struct REDMMO_API FRedPlanetHubProtectionQuery
{
	GENERATED_BODY()

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|World Authoring|Reservation")
	bool bQueryValid = false;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|World Authoring|Reservation")
	bool bBlocked = true;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|World Authoring|Reservation",
		meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float ProtectionWeight = 1.0f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|World Authoring|Reservation")
	FName ReservationId = NAME_None;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|World Authoring|Reservation")
	FGuid StableGuid;
};

/**
 * Query-only runtime bridge for RED Mars' 27 authenticated hub reservations.
 *
 * It owns no mutable layout state and never enables or spawns PCG/WorldGen content. Its public
 * world query requires an exact stable-ID celestial-frame registration. No producer is wired by
 * this checkpoint, so future adapters must abort placement when bQueryValid=false.
 */
UCLASS()
class REDMMO_API URedPlanetHubReservationRegistry : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintPure, Category = "RedMMO|World Authoring|Reservation")
	static FName GetReservationBodyId();

	UFUNCTION(BlueprintPure, Category = "RedMMO|World Authoring|Reservation")
	static FString GetReservationDatasetSha256();

	UFUNCTION(BlueprintPure, Category = "RedMMO|World Authoring|Reservation")
	static int32 GetHubReservationCount();

	UFUNCTION(BlueprintPure, Category = "RedMMO|World Authoring|Reservation")
	static bool GetHubReservation(int32 RegionIndex, FRedPlanetHubReservation& OutReservation);

	UFUNCTION(BlueprintPure, Category = "RedMMO|World Authoring|Reservation")
	static TArray<FRedPlanetHubReservation> GetAllHubReservations();

	/**
	 * Accepts only RED Mars' canonical body ID, requires exactly one explicit frame registration for
	 * that ID in the supplied world, validates its nominal physical radius, and returns the strongest
	 * geodesic reservation at WorldPoint for FeatureTag. Missing/wrong/duplicate/stale body bindings,
	 * unregistered feature tags, invalid directions, and worker-thread calls fail closed.
	 */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|World Authoring|Reservation",
		meta = (WorldContext = "WorldContextObject"))
	static FRedPlanetHubProtectionQuery QueryFeatureProtection(
		const UObject* WorldContextObject,
		FName BodyId,
		FName FeatureTag,
		const FVector& WorldPoint);

private:
	friend class FRedPlanetHubReservationProtectionQueriesTest;

	/** Pure geodesic helper used only after the public API resolves an authenticated body frame. */
	static FRedPlanetHubProtectionQuery QueryFeatureProtectionAtCenter(
		FName BodyId,
		FName FeatureTag,
		const FVector& WorldPoint,
		const FVector& ResolvedBodyCenter,
		double NominalRadiusCm);
};
