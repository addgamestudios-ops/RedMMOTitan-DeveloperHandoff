// Copyright Epic Games, Inc. All Rights Reserved.


#include "Validation/EditorValidator_Actors.h"
#include "GameFramework/Actor.h"
#include "Logging/TitanLogChannels.h"
#include "Misc/DataValidation.h"
#include "Engine/World.h"

// define a CVAR to control the max allowed bounding box size
static TAutoConsoleVariable<float> CVarTitanValidationMaxBoundingBox(
	TEXT("Titan.Validation.MaxBoundingBoxSize"),
	150000.0f,
	TEXT("Max allowed bounding box size for Titan Map Actors.\n")
	TEXT("Defaults to 1.5km"),
	ECVF_Default);

UEditorValidator_Actors::UEditorValidator_Actors()
	: Super()
{
}

bool UEditorValidator_Actors::CanValidateAsset_Implementation(const FAssetData& InAssetData, UObject* InAsset, FDataValidationContext& InContext) const
{
	// skip non-manual validation to avoid tanking performance on regular usage
	if (ShouldSkipTitanValidators())
	{
		return false;
	}

	if (InContext.GetValidationUsecase() != EDataValidationUsecase::Manual)
	{
		UE_LOG(LogTitan, Log, TEXT("Validation use case is not manual. Skipping."));

		return false;
	}
	
	// For WP Actors, we'll get the UWorld as the asset to validate
	if (InAsset && InAsset->IsA(UWorld::StaticClass()))
	{
		// ensure we get valid, loaded actors to validate
		TConstArrayView<FAssetData> ActorsToValidate = InContext.GetAssociatedExternalObjects();

		UE_LOG(LogTitan, Log, TEXT("Validating WP Actors. Count [%d]"), ActorsToValidate.Num());

		for (int32 idx = 0; idx < ActorsToValidate.Num(); ++idx)
		{
			const FAssetData& CurrentAsset = ActorsToValidate[idx];

			// ensure the asset is loaded
			if (!CurrentAsset.IsAssetLoaded())
			{
				UE_LOG(LogTitan, Log, TEXT("Current asset [%d] is unloaded"), idx);

				return false;
			}

			// ensure the asset is an AActor
			UObject* CurrentObj = CurrentAsset.FastGetAsset();

			if (CurrentObj && !CurrentObj->IsA(AActor::StaticClass()))
			{
				UE_LOG(LogTitan, Log, TEXT("Current asset [%d] is not an Actor"), idx);

				return false;
			}
		}
	}
	else {

		// not validating a UWorld 
		return false;
	}

	// 
	return true;
}

EDataValidationResult UEditorValidator_Actors::ValidateLoadedAsset_Implementation(const FAssetData& InAssetData, UObject* InAsset, FDataValidationContext& Context)
{
	// read the bounding box size from CVARs
	static const auto CVar = IConsoleManager::Get().FindConsoleVariable(TEXT("Titan.Validation.MaxBoundingBoxSize"));
	float Value = CVar->GetFloat();
	const FVector MaxActorBoundingBoxSize(Value);

	// get the validated actors list
	TConstArrayView<FAssetData> ActorsToValidate = Context.GetAssociatedExternalObjects();

	for (const FAssetData& CurrentAsset : ActorsToValidate)
	{
		AActor* ValidatedActor = Cast<AActor>(CurrentAsset.FastGetAsset(false));

		if(ValidatedActor)
		{
			// check for max bounds size
			FVector BoundsOrigin, BoundsExtent;
			ValidatedActor->GetActorBounds(false, BoundsOrigin, BoundsExtent, true);

			if (BoundsExtent.X > MaxActorBoundingBoxSize.X || BoundsExtent.Y > MaxActorBoundingBoxSize.Y || BoundsExtent.Z > MaxActorBoundingBoxSize.Z)
			{
				AssetFails(InAsset, FText::FromString(FString::Printf(TEXT("Actor [%s] Bounding Box is too large: [%s] MAX[%s]"), *ValidatedActor->GetName(), *BoundsExtent.ToString(), *MaxActorBoundingBoxSize.ToString())));
			}
		}
	}

	// passed all validations
	if (GetValidationResult() != EDataValidationResult::Invalid)
	{
		AssetPasses(InAsset);
	}

	return GetValidationResult();
}
