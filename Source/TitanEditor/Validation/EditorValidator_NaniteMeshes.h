// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Validation/TitanEditorValidator.h"
#include "EditorValidator_NaniteMeshes.generated.h"

class UMaterial;

/**
 *  UEditorValidator_NaniteMeshes
 *  Validates Static Mesh properties that can cause compatibility issues with Nanite.
 *  - Invalid material types
 *  - Default material assigned
 *  - etc.
 */
UCLASS()
class TITANEDITOR_API UEditorValidator_NaniteMeshes : public UTitanEditorValidator
{
	GENERATED_BODY()
	
public:

	UEditorValidator_NaniteMeshes();

protected:
	using Super::CanValidateAsset_Implementation;

	/** returns true if the validator applies to the given asset */
	virtual bool CanValidateAsset_Implementation(const FAssetData& InAssetData, UObject* InObject, FDataValidationContext& InContext) const override;

	/** performs asset validation */
	virtual EDataValidationResult ValidateLoadedAsset_Implementation(const FAssetData& InAssetData, UObject* InAsset, FDataValidationContext& Context) override;

	/** pointer to the world grid material, used for validations */
	TObjectPtr<UMaterial> WorldGrid;
};
