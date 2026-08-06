#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "RedHUDBlueprintLibrary.generated.h"

class APlayerController;
class URedHUDWidget;

UCLASS()
class REDHUDRUNTIME_API URedHUDBlueprintLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    UFUNCTION(BlueprintCallable, Category="RED HUD", meta=(DefaultToSelf="OwningPlayer"))
    static URedHUDWidget* CreateAndAddRedHUD(APlayerController* OwningPlayer, int32 ZOrder = 100);
};
