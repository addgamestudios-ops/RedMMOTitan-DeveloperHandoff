#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "FootstepTrailComponent.generated.h"

class ACharacter;
class UMaterialInterface;
class UNiagaraSystem;
class USoundBase;
struct FHitResult;

/**
 * Drops a fading decal on the ground behind a walking Character to leave a
 * footstep / scuff trail in the sand. Traces toward the character's current
 * gravity direction so it works anywhere on a spherical planet.
 */
UCLASS(ClassGroup=(RedMMO), meta=(BlueprintSpawnableComponent))
class REDMMO_API UFootstepTrailComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UFootstepTrailComponent();

	/** Decal material to stamp into the ground (a soft dark sand scuff). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Footstep Trail")
	UMaterialInterface* DecalMaterial = nullptr;

	/** Authored Sand FX footprint actor. Its decal material selects a sole from the pack atlas. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Footstep Trail")
	TSubclassOf<AActor> FootprintDecalClass;

	/** Distance the character must travel between trail marks (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Footstep Trail")
	float StepDistance = 180.0f;

	/** Decal box size: X = projection depth, Y/Z = footprint extent (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Footstep Trail")
	FVector DecalSize = FVector(12.0f, 15.0f, 34.0f);

	/** Seconds before a trail mark disappears. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Footstep Trail")
	float DecalLifeSpan = 45.0f;

	/** Lift the decal projector just off the collision surface so curved procedural chunks do not z-fight it away. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Footstep Trail")
	float FootprintSurfaceOffset = 3.0f;

	/** Keep the small boot silhouette visible from the normal third-person camera distance. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Footstep Trail")
	float FootprintFadeScreenSize = 0.00005f;

	/** How far to trace toward the ground (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Footstep Trail")
	float TraceLength = 250.0f;

	/** How far above the requested mark origin to begin ground traces (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Footstep Trail")
	float TraceStartLift = 90.0f;

	/**
	 * Maximum distance from the requested foot/character origin to the contacted surface.
	 * TraceLength can remain large for radial worlds, but a planet many metres below a falling
	 * character must never manufacture a footprint in mid-air.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Footstep Trail")
	float MaxSurfaceContactDistance = 220.0f;

	/** Side-to-side spacing between alternating left/right sand marks (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Footstep Trail")
	float FootSeparation = 34.0f;

	/** Pushes the footprint slightly behind the actor center so it lands under the trailing foot. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Footstep Trail")
	float FootBackOffset = 18.0f;

	/** Small random twist so repeated marks do not look stamped by a machine. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Footstep Trail")
	float RandomYawDegrees = 7.0f;

	/** Alternating outward toe angle makes the left/right boot trail immediately readable. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Footstep Trail")
	float FootToeOutDegrees = 5.0f;

	/** Adds a longer shallow scuff while the character is moving quickly. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Footstep Trail|Scuff")
	bool bSpawnForwardScuff = true;

	/** Minimum tangential movement speed before a forward scuff is added. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Footstep Trail|Scuff")
	float MinSpeedForForwardScuff = 520.0f;

	/** Distance ahead of the foot placement used by the shallow speed scuff. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Footstep Trail|Scuff")
	float ForwardScuffDistance = 42.0f;

	/** Visual size multiplier for the shallow speed scuff. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Footstep Trail|Scuff")
	float ForwardScuffScale = 1.8f;

	/** Optional dust/sand puff spawned at each trail mark. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Footstep Trail|FX")
	TObjectPtr<class UNiagaraSystem> StepPuffSystem = nullptr;

	/** Scale for the optional dust/sand puff. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Footstep Trail|FX")
	float StepPuffScale = 0.65f;

	/** Extra dust scale applied from tangential movement speed. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Footstep Trail|FX")
	float SpeedDustScale = 0.0012f;

	/** Optional footstep sound played at each trail mark. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Footstep Trail|Audio")
	TObjectPtr<class USoundBase> StepSound = nullptr;

	/** Volume for the optional footstep sound. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Footstep Trail|Audio")
	float StepSoundVolume = 0.35f;

	/**
	 * Use radial gravity toward the PlanetGen center before CharacterMovement gravity. The legacy
	 * property name is retained so existing Blueprint and level values continue to deserialize.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Footstep Trail|Gravity")
	bool bUseGravityCoreDirection = true;

	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

private:
	FVector ResolveGravityDirection(const ACharacter& Character, const FVector& WorldLocation) const;
	bool TraceGroundAt(const AActor& Owner, const FVector& Origin, const FVector& Down, FHitResult& OutHit) const;
	bool IsSandSurfaceHit(const FHitResult& Hit) const;
	void SpawnSandMark(const FHitResult& Hit, const FVector& Forward, float SizeScale, float TangentSpeed,
		bool bLeftFoot, bool bSpawnFootprint, bool bPlayAudio) const;

	FVector LastSpawnLocation = FVector::ZeroVector;
	bool bHasLast = false;
	bool bNextLeftFoot = true;
};
