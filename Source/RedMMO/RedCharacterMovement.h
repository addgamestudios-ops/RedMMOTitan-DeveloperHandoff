#pragma once

#include "CoreMinimal.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "RedCharacterMovement.generated.h"

/**
 * On SIMULATED PROXIES the replicated velocity arrives in spikes (real speed on net-update
 * frames, ~0 between) and acceleration is never replicated (it's input-derived, and proxies
 * get no input). Velocity-driven locomotion anim graphs read GetVelocity() + the "is moving"
 * gate from GetCurrentAcceleration(), so a remote character stays idle / stiff even while it
 * slides. This component holds the last real velocity briefly and synthesizes matching
 * acceleration on the proxy so the anim graph sees steady movement and animates the legs.
 */
UCLASS()
class REDMMO_API URedCharacterMovement : public UCharacterMovementComponent
{
	GENERATED_BODY()

public:
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	/** Radius of the playable planet surface used when voxel collision is late or missing. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet Movement", meta = (ClampMin = "1.0"))
	float PlanetSurfaceRadius = 382000.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet Movement")
	FVector PlanetCenter = FVector::ZeroVector;

	/** Flat (non-planet) maps: use normal downward gravity and skip all radial surface-snapping.
	 *  Set by the pawn when no planet controller is found (e.g. the SoStylized demo arena). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet Movement")
	bool bFlatMode = false;

	/** Small gap above the spherical surface after capsule half-height is applied. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet Movement", meta = (ClampMin = "0.0"))
	float SurfaceStickGap = 0.0f;

	/** Prefer the actual voxel/level collision under the pawn before falling back to the radius guard. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet Movement")
	bool bPreferPhysicalSurfaceTrace = true;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet Movement", meta = (ClampMin = "0.0"))
	float SurfaceTraceStartLift = 5000.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet Movement", meta = (ClampMin = "1000.0"))
	float SurfaceTraceDistance = 100000.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet Movement", meta = (ClampMin = "0.0"))
	float SurfaceTraceSnapDistance = 100000.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet Movement", meta = (ClampMin = "0.0"))
	float SurfaceTraceTolerance = 30.0f;

	/** Distance advantage required before switching between overlapping gravity bodies. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet Movement", meta = (ClampMin = "0.0"))
	float GravityBodySwitchHysteresis = 25000.0f;

	/** Forget where we last stood (ship exit / teleport): the guard radius from the boarding
	 *  point is meaningless at the destination — fresh-arrival semantics (datum catcher +
	 *  sky-trace rescue) take over until real ground is resolved again. */
	void ResetFallGuard() { FallGuardRadius = 0.f; }

	/** Read-only stable identity for diagnostics and authority reconciliation. */
	FName GetCurrentGravityBodyId() const { return CurrentGravityBodyId; }

private:
	bool FindPhysicalPlanetSurface(const ACharacter& Character, FVector& OutCapsuleCenter, FVector& OutSurfaceUp) const;

	FVector SteadyVel = FVector::ZeroVector;
	float ProxyHoldTimer = 0.f;
	/** Radius (from planet center) where this pawn last stood; used to clamp fall-through. */
	float FallGuardRadius = 0.f;
	FName CurrentGravityBodyId = NAME_None;
};
