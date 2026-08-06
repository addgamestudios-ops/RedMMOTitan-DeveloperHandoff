#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "RedImpostorFade.generated.h"

USTRUCT()
struct FRedImpostorEntry
{
	GENERATED_BODY()

	/** The pretty prop (celestial-body sphere) shown from far away. */
	UPROPERTY(EditAnywhere)
	TObjectPtr<AActor> Impostor = nullptr;

	/** Hide the prop when the camera is closer than this to the prop's center (cm). 0 = never hide. */
	UPROPERTY(EditAnywhere)
	float HideDistance = 0.f;
};

/**
 * "The postcard becomes the place": celestial bodies keep a beautiful prop sphere as their distant
 * look; as the local camera flies inside HideDistance the prop hides and the real voxel terrain
 * (streaming in underneath) carries the view. 10% hysteresis prevents flicker at the boundary.
 * Props managed here must have collision disabled — the voxel body is the physical one.
 */
UCLASS()
class REDMMO_API ARedImpostorFade : public AActor
{
	GENERATED_BODY()

public:
	ARedImpostorFade();

	UPROPERTY(EditAnywhere, Category = "Red|Impostors")
	TArray<FRedImpostorEntry> Impostors;

	virtual void Tick(float DeltaSeconds) override;
};
