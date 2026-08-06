#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "RedMiniFighterWorldSubsystem.generated.h"

/**
 * Runtime-only authoritative spawner. This avoids a map edit and waits until BeginPlay actors
 * (including streamed shuttle Blueprints) exist before creating one rear-bay mini fighter.
 */
UCLASS()
class REDMMO_API URedMiniFighterWorldSubsystem final : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Deinitialize() override;

private:
	void TryEnsureRearBayFighter();
	AActor* FindPreferredDockParent() const;

	FTimerHandle SpawnRetryTimer;
	int32 SpawnAttempts = 0;
};
