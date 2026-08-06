#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "RedMMOVoxelLibrary.generated.h"

/**
 * RedMMO project tooling exposed to Python/Blueprint.
 */
UCLASS()
class REDMMO_API URedMMOVoxelLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * Overwrite a CurveLinearColor's RGBA keys with the given gradient, then rebake the atlas it
	 * lives in (UCurveLinearColor exposes no key editing to Python). Used to smooth the stylized
	 * sky's blown-out horizon band while keeping the upper-sky blue. Times[i] -> Colors[i].
	 * Marks both packages dirty; save them from Python afterward.
	 */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|Sky")
	static bool SetColorCurveKeys(
		const FString& CurvePath,
		const FString& AtlasPath,
		const TArray<float>& Times,
		const TArray<FLinearColor>& Colors);
};
