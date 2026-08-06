// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "CommonActivatableWidget.h"
#include "Framework/Application/NavigationConfig.h"
#include "Input/UIActionBindingHandle.h"
#include "TitanActivatableWidget.generated.h"

class UInputAction;

/**
 *  FTitanNavigationConfig
 *  Custom navigation config that disables joypad and tab widget navigation.
 *  Used to prevent navigation clashing when closing and scrolling the map.
 */
class TITAN_API FTitanNavigationConfig : public FNavigationConfig
{

public:
	FTitanNavigationConfig();

	virtual ~FTitanNavigationConfig();
};

/**
 *  UTitanActivatableWidget
 *  Base class for in-game widgets.
 *  Provides input action mappings to close the menu through shortcut keys.
 *  Implements analog stick events to aid in map scrolling.
 *  Implements an optional navigation config override to resolve a clash in map scrolling.
 */
UCLASS()
class TITAN_API UTitanActivatableWidget : public UCommonActivatableWidget
{
	GENERATED_BODY()
	
protected:

	/** Menu Close Input Actions */
	UPROPERTY(EditAnywhere, Category ="Titan")
	TArray<TObjectPtr <UInputAction>> MenuCloseActions;

	/** Menu close binding handles */
	TArray<FUIActionBindingHandle> MenuCloseBindingHandles;

	/** Set to true to apply the navigation config override to disable joypad and tab navigation. */
	UPROPERTY(EditAnywhere, Category="Titan")
	bool bUseNavConfigOverride = false;

	/** Construct override to register the close action bindings */
	virtual void NativeConstruct() override;

	/** Destruct override to deregister the close action bindings */
	virtual void NativeDestruct() override;

	/** Activation override to apply the custom nav config */
	virtual void NativeOnActivated() override;

	/** Deactivation override to restore the standard nav config */
	virtual void NativeOnDeactivated() override;

	/** Detect and handle Zoom/Scroll/Rotate */
	virtual FReply NativeOnAnalogValueChanged(const FGeometry& InGeometry, const FAnalogInputEvent& InAnalogEvent) override;

	/** Menu close delegate handler */
	UFUNCTION()
	void HandleMenuClose();

	/** Blueprint event to close the menu*/
	UFUNCTION(BlueprintImplementableEvent, Category="Titan", meta=(DisplayName="On Menu Close"))
	void BP_MenuClose();

	/** Blueprint event to scroll the menu on the X axis */
	UFUNCTION(BlueprintImplementableEvent, Category="Titan", meta = (DisplayName = "On Menu Scroll X"))
	void BP_MenuScrollX(const float Value);

	/** Blueprint event to scroll the menu on the Y axis */
	UFUNCTION(BlueprintImplementableEvent, Category="Titan", meta = (DisplayName = "On Menu Scroll Y"))
	void BP_MenuScrollY(const float Value);

	/** Blueprint event to zoom the menu */
	UFUNCTION(BlueprintImplementableEvent, Category="Titan", meta = (DisplayName = "On Menu Zoom"))
	void BP_MenuZoom(float Value);

	/** Blueprint event to rotate the menu */
	UFUNCTION(BlueprintImplementableEvent, Category="Titan", meta = (DisplayName = "On Menu Rotate"))
	void BP_MenuRotate(float Value);
};
