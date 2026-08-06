// Copyright Epic Games, Inc. All Rights Reserved.


#include "Validation/EditorValidator_Textures.h"
#include "Engine/Texture2D.h"

static TAutoConsoleVariable<int32> CVarTextureValidatorMaxSize(
	TEXT("Titan.Validation.MaxValidTextureSize"),
	4096,
	TEXT("Sets the maximum allowed texture size for the Texture asset validator.")
);

UEditorValidator_Textures::UEditorValidator_Textures()
	: Super()
{

}

EDataValidationResult UEditorValidator_Textures::ValidateLoadedAsset_Implementation(const FAssetData& InAssetData, UObject* InAsset, FDataValidationContext& Context)
{
	const UTexture2D* ValidatedTexture = Cast<UTexture2D>(InAsset);
	check(ValidatedTexture);

	// check the X size of the texture
	if ((ValidatedTexture->GetSizeX() & (ValidatedTexture->GetSizeX()) - 1) != 0)
	{
		AssetFails(InAsset, FText::FromString(FString::Printf(TEXT("Texture doesn't have a power of 2 X Size."))));
	}

	// check the Y size of the texture
	if ((ValidatedTexture->GetSizeY() & (ValidatedTexture->GetSizeY()) - 1) != 0)
	{
		AssetFails(InAsset, FText::FromString(FString::Printf(TEXT("Texture doesn't have a power of 2 Y Size."))));
	}

	// check if the size exceeds the CVar setting
	if (ValidatedTexture->GetSizeX() > CVarTextureValidatorMaxSize.GetValueOnAnyThread() || ValidatedTexture->GetSizeY() > CVarTextureValidatorMaxSize.GetValueOnAnyThread())
	{
		AssetFails(InAsset, FText::FromString(FString::Printf(TEXT("Texture size is greater than %d."), CVarTextureValidatorMaxSize.GetValueOnAnyThread())));
	}

	// passed all validations
	if (GetValidationResult() != EDataValidationResult::Invalid)
	{
		AssetPasses(InAsset);
	}

	return GetValidationResult();
}

bool UEditorValidator_Textures::CanValidateAsset_Implementation(const FAssetData& InAssetData, UObject* InAsset, FDataValidationContext& InContext) const
{
	// only validate Texture2D
	return (
		!ShouldSkipTitanValidators()
		&& (InAsset ? InAsset->IsA(UTexture2D::StaticClass()) : false)
		);
}
