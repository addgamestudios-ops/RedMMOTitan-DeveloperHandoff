#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "Style/VibeMMOUIStyleDataAsset.h"
#include "VibeMMOBaseWidget.generated.h"

class UTextBlock;

UCLASS(Abstract, Blueprintable)
class VIBEMMOUIKIT_API UVibeMMOBaseWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Vibe MMO UI|Style", meta = (ExposeOnSpawn = true))
	TObjectPtr<UVibeMMOUIStyleDataAsset> StyleDataAsset;

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|Style")
	void SetStyleDataAsset(UVibeMMOUIStyleDataAsset* InStyleDataAsset);

	UFUNCTION(BlueprintPure, Category = "Vibe MMO UI|Style")
	UVibeMMOUIStyleDataAsset* GetResolvedStyleDataAsset() const;

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|Typography")
	void ApplyTextRole(UTextBlock* TextBlock, EVibeMMOUIFontRole Role) const;

	UFUNCTION(BlueprintNativeEvent, Category = "Vibe MMO UI|Style")
	void ApplyVibeStyle();
	virtual void ApplyVibeStyle_Implementation();

protected:
	virtual void NativePreConstruct() override;
};
