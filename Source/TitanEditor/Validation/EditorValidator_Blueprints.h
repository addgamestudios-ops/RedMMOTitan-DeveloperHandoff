// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Validation/TitanEditorValidator.h"
#include "EditorValidator_Blueprints.generated.h"

/**
 *  UEditorValidator_Blueprints
 *  Validates level construction Blueprints that could cause performance bottlenecks
 *  - Construction Scripts
 *  - Child Actor Component usage
 *  - Skeletal Mesh Component usage
 */
UCLASS()
class TITANEDITOR_API UEditorValidator_Blueprints : public UTitanEditorValidator
{
	GENERATED_BODY()

public:

	UEditorValidator_Blueprints();
	
protected:
	using Super::CanValidateAsset_Implementation;

	/** returns true if the validator applies to the given asset */
	virtual bool CanValidateAsset_Implementation(const FAssetData& InAssetData, UObject* InObject, FDataValidationContext& InContext) const override;

	/** performs asset validation */
	virtual EDataValidationResult ValidateLoadedAsset_Implementation(const FAssetData& InAssetData, UObject* InAsset, FDataValidationContext& Context) override;

};
