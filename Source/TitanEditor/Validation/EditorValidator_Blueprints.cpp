// Copyright Epic Games, Inc. All Rights Reserved.


#include "Validation/EditorValidator_Blueprints.h"
#include "Components/PrimitiveComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/ChildActorComponent.h"
#include "Components/ActorComponent.h"
#include "Engine/Blueprint.h"
#include "Logging/TitanLogChannels.h"
#include "EdGraph/EdGraph.h"
#include "Engine/SimpleConstructionScript.h"
#include "Engine/SCS_Node.h"

UEditorValidator_Blueprints::UEditorValidator_Blueprints()
	: Super()
{

}

bool UEditorValidator_Blueprints::CanValidateAsset_Implementation(const FAssetData& InAssetData, UObject* InAsset, FDataValidationContext& InContext) const
{
	return (!ShouldSkipTitanValidators() && (InAsset ? InAsset->IsA(UBlueprint::StaticClass()) : false));
}

EDataValidationResult UEditorValidator_Blueprints::ValidateLoadedAsset_Implementation(const FAssetData& InAssetData, UObject* InAsset, FDataValidationContext& Context)
{
	// cast the BP we're validating
	const UBlueprint* ValidatedBP = Cast<UBlueprint>(InAsset);
	check(ValidatedBP);

	// get the component templates from the Simple Construction Script
	if (ValidatedBP->SimpleConstructionScript)
	{
		TArray<USCS_Node*> ConstructionScriptNodes = ValidatedBP->SimpleConstructionScript->GetAllNodes();

		for (const USCS_Node* CurrentNode : ConstructionScriptNodes)
		{
			if (CurrentNode && CurrentNode->ComponentTemplate)
			{
				// ensure we don't have a child actor component
				if (CurrentNode->ComponentTemplate->IsA(UChildActorComponent::StaticClass()))
				{
					AssetFails(InAsset, FText::FromString("Blueprint has a Child Actor Component."));
				}

				// ensure we don't have a skeletal mesh
				if (CurrentNode->ComponentTemplate->IsA(USkeletalMeshComponent::StaticClass()))
				{
					AssetFails(InAsset, FText::FromString("Blueprint has a Skeletal Mesh Component."));
				}

				// ensure we don't have movable primitive comps
				const UPrimitiveComponent* CurrentPrimitive = Cast<UPrimitiveComponent>(CurrentNode->ComponentTemplate);

				if (CurrentPrimitive)
				{
					if (CurrentPrimitive->Mobility != EComponentMobility::Static)
					{
						AssetFails(InAsset, FText::FromString("Blueprint has a non-static Primitive Component."));
					}
				}
			}
		}
	}

	// look for a construction script
	static FName ConstructionScriptName("UserConstructionScript");

	for (const TObjectPtr<UEdGraph> CurrentGraph : ValidatedBP->FunctionGraphs)
	{
		if (CurrentGraph->GetFName() == ConstructionScriptName)
		{
			if (CurrentGraph->Nodes.Num() > 1)
			{
				AssetFails(InAsset, FText::FromString("Blueprint has a construction script."));
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