#include "RedHUDBlueprintLibrary.h"

#include "RedHUDWidget.h"
#include "Blueprint/UserWidget.h"
#include "GameFramework/PlayerController.h"

URedHUDWidget* URedHUDBlueprintLibrary::CreateAndAddRedHUD(APlayerController* OwningPlayer, const int32 ZOrder)
{
    if (!IsValid(OwningPlayer) || !OwningPlayer->IsLocalController())
    {
        return nullptr;
    }

    URedHUDWidget* Widget = CreateWidget<URedHUDWidget>(OwningPlayer, URedHUDWidget::StaticClass());
    if (Widget)
    {
        Widget->AddToPlayerScreen(ZOrder);
    }

    return Widget;
}
