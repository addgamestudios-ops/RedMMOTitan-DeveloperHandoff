// Copyright Epic Games, Inc. All Rights Reserved.


#include "UI/TitanActivatableWidget.h"
#include "Logging/TitanLogChannels.h"
#include "CommonUITypes.h"
#include "Input/CommonUIInputTypes.h"
#include "Framework/Application/SlateApplication.h"

FTitanNavigationConfig::FTitanNavigationConfig()
{
	bAnalogNavigation = false;
	bTabNavigation = false;
}

FTitanNavigationConfig::~FTitanNavigationConfig()
{
}

void UTitanActivatableWidget::NativeConstruct()
{
	if (CommonUI::IsEnhancedInputSupportEnabled())
	{
		// bind all close actions
		for (TObjectPtr<UInputAction>& CurrentAction : MenuCloseActions)
		{
			FBindUIActionArgs BindArgs(CurrentAction, false, FSimpleDelegate::CreateUObject(this, &UTitanActivatableWidget::HandleMenuClose));
			BindArgs.bIsPersistent = false;
			BindArgs.InputMode = ECommonInputMode::Menu;

			MenuCloseBindingHandles.Add(RegisterUIActionBinding(BindArgs));
		}
	}

	Super::NativeConstruct();
}

void UTitanActivatableWidget::NativeDestruct()
{
	// unregister all binding handles
	for (FUIActionBindingHandle& CurrentHandle : MenuCloseBindingHandles)
	{
		CurrentHandle.Unregister();
	}

	MenuCloseBindingHandles.Empty();

	Super::NativeDestruct();
}

void UTitanActivatableWidget::NativeOnActivated()
{
	// override the navigation config
	if (bUseNavConfigOverride)
	{
		FSlateApplication::Get().SetNavigationConfig(MakeShared<FNavigationConfig>(FTitanNavigationConfig()));
	}

	Super::NativeOnActivated();
}

void UTitanActivatableWidget::NativeOnDeactivated()
{
	// reset the navigation config
	FSlateApplication::Get().SetNavigationConfig(MakeShared<FNavigationConfig>(FNavigationConfig()));

	Super::NativeOnDeactivated();
}

FReply UTitanActivatableWidget::NativeOnAnalogValueChanged(const FGeometry& InGeometry, const FAnalogInputEvent& InAnalogEvent)
{
	// get the pressed key and its analog value
	FKey Key = InAnalogEvent.GetKey();
	float Value = InAnalogEvent.GetAnalogValue();
	
	// call the corresponding widget event
	if (Key == EKeys::Gamepad_LeftX)
	{
		BP_MenuScrollX(Value);
	}
	else if (Key == EKeys::Gamepad_LeftY)
	{
		BP_MenuScrollY(Value);
	}
	else  if (Key == EKeys::Gamepad_RightY)
	{
		BP_MenuZoom(Value);
	}
	else  if (Key == EKeys::Gamepad_RightX)
	{
		BP_MenuRotate(Value);
	}
	
	return Super::NativeOnAnalogValueChanged(InGeometry, InAnalogEvent);
}

void UTitanActivatableWidget::HandleMenuClose()
{
	// pass to BP
	BP_MenuClose();
}
