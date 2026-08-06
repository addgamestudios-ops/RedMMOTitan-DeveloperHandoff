// Copyright Epic Games, Inc. All Rights Reserved.


#include "Character/TitanInputEventSet.h"
#include "Logging/TitanLogChannels.h"
#include "Character/TitanPawn.h"
#include "EnhancedInputComponent.h"

UTitanInputEventSet::UTitanInputEventSet(const FObjectInitializer& ObjectInitializer /*= FObjectInitializer::Get()*/)
: Super(ObjectInitializer)
{

}

void UTitanInputEventSet::GiveToPawn(ATitanPawn* TitanPawn, UEnhancedInputComponent* InputComponent) const
{
	check(TitanPawn);
	check(InputComponent);

	// iterate through all granted input events
	for (int32 idx = 0; idx < GrantedInputEvents.Num(); ++idx)
	{
		// get the input event
		const FTitanInputEventSet_InputEvent& InputEvent = GrantedInputEvents[idx];

		// ensure the input action is valid
		if (!IsValid(InputEvent.InputAction))
		{
			UE_LOG(LogTitanCharacter, Warning, TEXT("GrantedInputEvents[%d] on Input Event Set [%s] is not valid."), idx, *GetNameSafe(this));
		}

		// bind the input event
		TitanPawn->BindInputEvent(InputEvent.InputAction, InputEvent.InputEventTag, InputComponent);
	}
}