#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "VibeMMOUIPlayerControllerBase.generated.h"

class UVibeMMOHUDWidget;
class UVibeMMOUIStyleDataAsset;

UCLASS()
class VIBEMMOUIKIT_API AVibeMMOUIPlayerControllerBase : public APlayerController
{
	GENERATED_BODY()

public:
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Vibe MMO UI|HUD")
	TSubclassOf<UVibeMMOHUDWidget> HUDWidgetClass;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Vibe MMO UI|Style")
	TObjectPtr<UVibeMMOUIStyleDataAsset> StyleDataAsset;

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD")
	UVibeMMOHUDWidget* CreateAndShowHUD();

	UFUNCTION(BlueprintPure, Category = "Vibe MMO UI|HUD")
	UVibeMMOHUDWidget* GetHUDWidget() const;

protected:
	virtual void BeginPlay() override;

private:
	UPROPERTY(Transient)
	TObjectPtr<UVibeMMOHUDWidget> HUDWidget;
};
