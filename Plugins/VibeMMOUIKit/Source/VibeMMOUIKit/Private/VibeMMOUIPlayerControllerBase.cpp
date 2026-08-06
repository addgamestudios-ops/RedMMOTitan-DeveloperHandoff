#include "VibeMMOUIPlayerControllerBase.h"

#include "Blueprint/UserWidget.h"
#include "Engine/GameInstance.h"
#include "VibeMMOUIManagerSubsystem.h"
#include "Widgets/VibeMMOHUDWidget.h"

void AVibeMMOUIPlayerControllerBase::BeginPlay()
{
	Super::BeginPlay();

	if (HUDWidgetClass)
	{
		CreateAndShowHUD();
	}
}

UVibeMMOHUDWidget* AVibeMMOUIPlayerControllerBase::CreateAndShowHUD()
{
	if (HUDWidget)
	{
		return HUDWidget;
	}

	if (!HUDWidgetClass)
	{
		return nullptr;
	}

	HUDWidget = CreateWidget<UVibeMMOHUDWidget>(this, HUDWidgetClass);
	if (!HUDWidget)
	{
		return nullptr;
	}

	if (StyleDataAsset)
	{
		HUDWidget->SetStyleDataAsset(StyleDataAsset);

		if (UGameInstance* GameInstance = GetGameInstance())
		{
			if (UVibeMMOUIManagerSubsystem* UIManager = GameInstance->GetSubsystem<UVibeMMOUIManagerSubsystem>())
			{
				UIManager->SetActiveStyleDataAsset(StyleDataAsset);
			}
		}
	}

	HUDWidget->AddToViewport();
	return HUDWidget;
}

UVibeMMOHUDWidget* AVibeMMOUIPlayerControllerBase::GetHUDWidget() const
{
	return HUDWidget;
}
