// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "GameplayTagContainer.h"
#include "TitanInputEventSet.generated.h"

class UInputAction;
class ATitanPawn;
class UEnhancedInputComponent;

/**
 *  FTitanInputEventSet_InputEvent
 *  An individual input event struct to translate an input action to a Gameplay Event
 */
USTRUCT(BlueprintType)
struct FTitanInputEventSet_InputEvent
{
	GENERATED_BODY()

public:

	// Input Action that triggers the event
	UPROPERTY(EditDefaultsOnly)
	TObjectPtr<UInputAction> InputAction = nullptr;

	// Tag of the event triggered in the ASC when the action is triggered
	UPROPERTY(EditDefaultsOnly)
	FGameplayTag InputEventTag;
};

/**
 *  UTitanInputEventSet
 *  Non-mutable data asset used to bind Gameplay Event triggers to Input Actions
 */
UCLASS(BlueprintType, Const)
class TITAN_API UTitanInputEventSet : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:

	UTitanInputEventSet(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	void GiveToPawn(ATitanPawn* TitanPawn, UEnhancedInputComponent* InputComponent) const;

protected:

	// Input Events to bind when this input event set is granted.
	UPROPERTY(EditDefaultsOnly, Category="Input Events", meta=(TitleProperty=InputAction))
	TArray<FTitanInputEventSet_InputEvent> GrantedInputEvents;
};
