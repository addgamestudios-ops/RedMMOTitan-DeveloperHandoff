// Copyright Epic Games, Inc. All Rights Reserved.


#include "Validation/EditorValidator_Materials.h"
#include "Materials/MaterialInterface.h"

UEditorValidator_Materials::UEditorValidator_Materials()
	: Super()
{

}

EDataValidationResult UEditorValidator_Materials::ValidateLoadedAsset_Implementation(const FAssetData& InAssetData, UObject* InAsset, FDataValidationContext& Context)
{
	const UMaterialInterface* ValidatedMaterial = Cast<UMaterialInterface>(InAsset);
	check(ValidatedMaterial);

	// ensure max world position offset displacement is zero
	if(ValidatedMaterial->GetMaxWorldPositionOffsetDisplacement() > 0.0f)
	{
		AssetFails(InAsset, FText::FromString(FString::Printf(TEXT("Material has a nonzero World Position Offset Displacement"))));
	}

	// passed all validations
	if (GetValidationResult() != EDataValidationResult::Invalid)
	{
		AssetPasses(InAsset);
	}

	return GetValidationResult();
}

bool UEditorValidator_Materials::CanValidateAsset_Implementation(const FAssetData& InAssetData, UObject* InAsset, FDataValidationContext& InContext) const
{
	return (
		!ShouldSkipTitanValidators()
		&& (InAsset ? InAsset->IsA(UMaterialInterface::StaticClass()) : false)
		);
}
