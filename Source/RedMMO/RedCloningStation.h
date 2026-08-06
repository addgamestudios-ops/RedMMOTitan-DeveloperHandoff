#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "RedCloningStation.generated.h"

class UStaticMeshComponent;
class UPointLightComponent;

/**
 * Orbital cloning station for "The Drop" (milestone #50). A platform high above a zone that the
 * player stands on and dives from — the Fortnite battle-bus. It also supplies the VIRTUAL planet
 * center + radius that ARedOctosphereManager measures the descent trajectory against.
 *
 * FLAT-ILLUSION prototype: the virtual planet center is placed straight BELOW the landing spot
 * (along the drop's up axis), so on a flat map the pawn falls straight down toward it — altitude
 * reads monotonically as height, and horizontal steering flips the octant cleanly. Built from
 * engine basic shapes (the AsteroidSpaceport pack isn't in this project).
 */
UCLASS()
class REDMMO_API ARedCloningStation : public AActor
{
	GENERATED_BODY()

public:
	ARedCloningStation();

	/** Place + orient the station DropAltitude above GroundPoint along DropUp, and set the virtual
	 *  planet (center = GroundPoint - DropUp * VirtualRadius, straight below the landing spot). */
	void SetupDrop(const FVector& InGroundPoint, const FVector& InDropUp, float InDropAltitude, float InVirtualRadius);

	/** World transform to stand a pawn on the deck (deck top + capsule clearance). */
	FTransform GetDropTransform() const;

	FVector GetVirtualPlanetCenter() const { return VirtualPlanetCenter; }
	float   GetVirtualPlanetRadius() const { return VirtualPlanetRadius; }
	float   GetDropAltitude() const { return DropAltitude; }

protected:
	UPROPERTY(VisibleAnywhere, Category = "Drop")
	TObjectPtr<USceneComponent> SceneRoot;

	/** Wide flat disc you stand on — Blocks Pawn (the deck surface). */
	UPROPERTY(VisibleAnywhere, Category = "Drop")
	TObjectPtr<UStaticMeshComponent> DeckMesh;

	/** Decorative bulk hanging under the deck — ignores Pawn so it never snags the diver. */
	UPROPERTY(VisibleAnywhere, Category = "Drop")
	TObjectPtr<UStaticMeshComponent> CoreMesh;

	UPROPERTY(VisibleAnywhere, Category = "Drop")
	TObjectPtr<UPointLightComponent> BeaconLight;

	/** Capsule clearance added above the deck top when standing a pawn on it. */
	UPROPERTY(EditAnywhere, Category = "Drop")
	float DeckClearance = 110.f;

private:
	FVector VirtualPlanetCenter = FVector::ZeroVector;
	float   VirtualPlanetRadius = 0.f;
	float   DropAltitude = 0.f;
	FVector DropUp = FVector::UpVector;
};
