#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "VibeMMOUISettings.generated.h"

class UVibeMMOUIStyleDataAsset;

UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "Vibe MMO UI Kit"))
class VIBEMMOUIKIT_API UVibeMMOUISettings : public UDeveloperSettings
{
	GENERATED_BODY()

public:
	UVibeMMOUISettings();

	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Style")
	TSoftObjectPtr<UVibeMMOUIStyleDataAsset> DefaultStyleDataAsset;

	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "HUD")
	bool bUseMockHUDDataByDefault;
};
