#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "Style/VibeMMOUIStyleDataAsset.h"
#include "VibeMMOUIFunctionLibrary.generated.h"

class UTextBlock;

UCLASS()
class VIBEMMOUIKIT_API UVibeMMOUIFunctionLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintPure, Category = "Vibe MMO UI|Typography")
	static FSlateFontInfo ResolveFontForRole(const UVibeMMOUIStyleDataAsset* StyleDataAsset, EVibeMMOUIFontRole Role);

	UFUNCTION(BlueprintPure, Category = "Vibe MMO UI|Typography")
	static FTextBlockStyle ResolveTextBlockStyleForRole(const UVibeMMOUIStyleDataAsset* StyleDataAsset, EVibeMMOUIFontRole Role);

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|Typography")
	static void ApplyTextRoleToTextBlock(UTextBlock* TextBlock, const UVibeMMOUIStyleDataAsset* StyleDataAsset, EVibeMMOUIFontRole Role);
};
