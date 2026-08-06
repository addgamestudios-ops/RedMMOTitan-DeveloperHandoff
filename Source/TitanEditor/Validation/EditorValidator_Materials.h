// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Validation/TitanEditorValidator.h"
#include "EditorValidator_Materials.generated.h"

/**
 * 
 */
UCLASS()
class TITANEDITOR_API UEditorValidator_Materials : public UTitanEditorValidator
{
	GENERATED_BODY()
	
public:

	UEditorValidator_Materials();

protected:
	using Super::CanValidateAsset_Implementation;

	/** returns true if the validator applies to the given asset */
	virtual bool CanValidateAsset_Implementation(const FAssetData& InAssetData, UObject* InObject, FDataValidationContext& InContext) const override;

	/** performs asset validation */
	virtual EDataValidationResult ValidateLoadedAsset_Implementation(const FAssetData& InAssetData, UObject* InAsset, FDataValidationContext& Context) override;

};
