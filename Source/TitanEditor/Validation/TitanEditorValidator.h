// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "EditorValidatorBase.h"
#include "TitanEditorValidator.generated.h"

/**
 *  UTitanEditorValidator
 *  Base class for all Titan Editor Asset Validators
 */
UCLASS(config=Editor)
class TITANEDITOR_API UTitanEditorValidator : public UEditorValidatorBase
{
	GENERATED_BODY()
	
protected:

	/** Used by subclasses as a controllable validator skip */
	bool ShouldSkipTitanValidators() const;
};
