// Copyright Epic Games, Inc. All Rights Reserved.


#include "Validation/TitanEditorValidator.h"
#include "Development/TitanDeveloperSettings.h"

bool UTitanEditorValidator::ShouldSkipTitanValidators() const
{
	return GetDefault<UTitanDeveloperSettings>()->bSkipTitanValidators;
}
