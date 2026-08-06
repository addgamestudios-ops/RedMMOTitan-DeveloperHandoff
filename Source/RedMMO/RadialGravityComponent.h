#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "RadialGravityComponent.generated.h"

/**
 * Pulls the owning Character toward a point (the planet core) every tick by
 * driving the CharacterMovementComponent's gravity direction, and optionally
 * keeps the capsule oriented so "up" is the local surface normal. Lets a
 * Character walk anywhere on a spherical voxel planet.
 */
UCLASS(ClassGroup=(RedMMO), meta=(BlueprintSpawnableComponent))
class REDMMO_API URadialGravityComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	URadialGravityComponent();

	/** World-space point gravity pulls toward. The planet is centered at the world origin. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Radial Gravity")
	FVector PlanetCenter = FVector::ZeroVector;

	/** Re-orient the owner each tick so its up vector points away from the center (surface normal). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Radial Gravity")
	bool bOrientToSurface = true;

	/** Rotate the controller's look direction with the surface so the third-person camera stays level as you walk around the sphere. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Radial Gravity")
	bool bRebaseControlRotation = true;

	/** Prevent rapid body flipping while two gravity influence volumes overlap. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Radial Gravity", meta = (ClampMin = "0.0"))
	float GravityBodySwitchHysteresis = 25000.0f;

	/** Read-only stable identity for diagnostics and authority reconciliation. */
	FName GetCurrentGravityBodyId() const { return CurrentGravityBodyId; }

	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	/** Clear the stored surface normal so the NEXT tick doesn't rebase the camera by a huge one-frame
	 *  delta. Call after teleporting the owner (e.g. exiting a ship on the far side of the planet). */
	void ResetRebase() { bHasPrevUp = false; }

private:
	FVector PrevUp = FVector::ZeroVector;
	bool bHasPrevUp = false;
	FName CurrentGravityBodyId = NAME_None;
};
