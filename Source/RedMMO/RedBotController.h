#pragma once

#include "CoreMinimal.h"
#include "AIController.h"
#include "RedBotController.generated.h"

/**
 * Minimal sphere-aware enemy brain. No navmesh (the voxel planet has none): each tick it steers the
 * pawn straight at the player along the surface tangent, faces them, and fires when in range.
 */
UCLASS()
class REDMMO_API ARedBotController : public AAIController
{
	GENERATED_BODY()

public:
	ARedBotController();
	virtual void Tick(float DeltaSeconds) override;

	/** Stop closing once this near the player (so they don't shove into you). */
	UPROPERTY(EditAnywhere, Category = "Bot")
	float ChaseStopRange = 1400.f;

	/** Open fire once within this range. */
	UPROPERTY(EditAnywhere, Category = "Bot")
	float FireRange = 5000.f;

	/** Seconds between shots. */
	UPROPERTY(EditAnywhere, Category = "Bot")
	float FireInterval = 1.1f;

	/** Stress-test WANDER mode: roam random local waypoints instead of chasing the player. Keeps bots
	 *  spread out so each stays a live WP streaming source across the map (real distributed load). */
	UPROPERTY(EditAnywhere, Category = "Bot")
	bool bWander = false;
	UPROPERTY(EditAnywhere, Category = "Bot")
	float WanderRadius = 8000.f;

private:
	float FireCooldown = 0.f;
	TWeakObjectPtr<class ACharacter> TargetPlayer;
	// Wander state.
	FVector WanderOrigin = FVector::ZeroVector;
	FVector WanderTarget = FVector::ZeroVector;
	float WanderRepick = 0.f;
	bool bWanderInit = false;
};
