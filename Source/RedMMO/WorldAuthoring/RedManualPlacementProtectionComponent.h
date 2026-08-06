#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "RedManualPlacementProtectionComponent.generated.h"

/**
 * Marks a handcrafted actor/POI as protected from procedural cleanup and exposes a spherical
 * reservation test that PCG adapters can query. The component never deletes or moves content.
 */
UCLASS(ClassGroup = (RedMMO), BlueprintType, Blueprintable,
	meta = (BlueprintSpawnableComponent, DisplayName = "Red Manual Placement Protection"))
class REDMMO_API URedManualPlacementProtectionComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	URedManualPlacementProtectionComponent();

	/** Stable author-facing name, for example R03_PortalOasis_MainHub. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Reservation")
	FName ReservationId = NAME_None;

	/** World-space planet centre used by the spherical/geodesic distance test. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Reservation")
	FVector PlanetCenter = FVector::ZeroVector;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Reservation", meta = (ClampMin = "1.0", Units = "cm"))
	float ProtectedRadiusCm = 2500.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Reservation", meta = (ClampMin = "0.0", Units = "cm"))
	float BlendRadiusCm = 1000.f;

	/** Feature types denied inside the reservation: Foliage, Rock, Creature, Resource, Water, POI. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Reservation")
	TArray<FName> BlockedFeatureTags;

	/** True when the point is inside the hard protected radius on the planet surface. */
	UFUNCTION(BlueprintPure, Category = "RedMMO|World Authoring")
	bool ContainsWorldPoint(const FVector& WorldPoint) const;

	/** 1 inside the hard radius, fades to 0 through BlendRadiusCm, and is 0 outside. */
	UFUNCTION(BlueprintPure, Category = "RedMMO|World Authoring")
	float GetProtectionWeight(const FVector& WorldPoint) const;

	/** True when this reservation denies FeatureTag at WorldPoint. Unknown/empty tags fail closed. */
	UFUNCTION(BlueprintPure, Category = "RedMMO|World Authoring")
	bool BlocksFeatureAtWorldPoint(FName FeatureTag, const FVector& WorldPoint) const;

	/** Feature-aware weight for PCG/WorldGen adapters; returns 0 only for explicitly allowed tags. */
	UFUNCTION(BlueprintPure, Category = "RedMMO|World Authoring")
	float GetFeatureProtectionWeight(FName FeatureTag, const FVector& WorldPoint) const;

protected:
	virtual void OnRegister() override;

private:
	float GetSurfaceArcDistanceCm(const FVector& WorldPoint) const;
};
