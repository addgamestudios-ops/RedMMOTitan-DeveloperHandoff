#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "VibeMMOUIManagerSubsystem.generated.h"

class UVibeMMOUIStyleDataAsset;

UCLASS()
class VIBEMMOUIKIT_API UVibeMMOUIManagerSubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|Style")
	void SetActiveStyleDataAsset(UVibeMMOUIStyleDataAsset* InStyleDataAsset);

	UFUNCTION(BlueprintPure, Category = "Vibe MMO UI|Style")
	UVibeMMOUIStyleDataAsset* GetActiveStyleDataAsset() const;

private:
	UPROPERTY(Transient)
	TObjectPtr<UVibeMMOUIStyleDataAsset> ActiveStyleDataAsset;
};
