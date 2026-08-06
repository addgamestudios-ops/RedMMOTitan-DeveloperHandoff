// Copyright Epic Games, Inc. All Rights Reserved.


#include "Validation/EditorValidator_NaniteMeshes.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInterface.h"
#include "UObject/ConstructorHelpers.h"
#include "Materials/Material.h"

static TAutoConsoleVariable<int32> CVarMeshValidatorMaxTriangleCount(
	TEXT("Titan.Validation.MaxValidMeshTriangleCount"),
	10000,
	TEXT("Sets the maximum allowed texture size for the Texture asset validator.")
);

UEditorValidator_NaniteMeshes::UEditorValidator_NaniteMeshes()
	: Super()
{
	// find the world grid material
	static ConstructorHelpers::FObjectFinder<UMaterial> MaterialRef(TEXT("/Engine/EngineMaterials/WorldGridMaterial"));
	WorldGrid = MaterialRef.Object;
	check(WorldGrid != nullptr);
}

bool UEditorValidator_NaniteMeshes::CanValidateAsset_Implementation(const FAssetData& InAssetData, UObject* InAsset, FDataValidationContext& InContext) const
{
	// applies to Static Meshes only
	return (!ShouldSkipTitanValidators() && (InAsset ? InAsset->IsA(UStaticMesh::StaticClass()) : false));
}

EDataValidationResult UEditorValidator_NaniteMeshes::ValidateLoadedAsset_Implementation(const FAssetData& InAssetData, UObject* InAsset, FDataValidationContext& Context)
{
	// cast the mesh we're validating
	const UStaticMesh* ValidatedMesh = Cast<UStaticMesh>(InAsset);
	check(ValidatedMesh);

	// skip any meshes that are not using Nanite
	if (ValidatedMesh->IsNaniteEnabled())
	{
		const int32 TriangleCount = ValidatedMesh->GetNumTriangles(0);

		UE_LOG(LogTemp, Log, TEXT("Mesh Tri Count: %d"), TriangleCount);

		if (TriangleCount > CVarMeshValidatorMaxTriangleCount.GetValueOnAnyThread())
		{
			AssetFails(InAsset, FText::FromString(FString::Printf(TEXT("Mesh LOD 0 has more than %d triangles."), CVarMeshValidatorMaxTriangleCount.GetValueOnAnyThread())));
		}

		// get the mesh materials
		const TArray<FStaticMaterial>& MeshMaterials = ValidatedMesh->GetStaticMaterials();

		for (int32 idx = 0; idx < MeshMaterials.Num(); ++idx)
		{
			const FStaticMaterial& CurrentMaterial = MeshMaterials[idx];

			// do we have a valid material assigned?
			if (!CurrentMaterial.MaterialInterface)
			{

				AssetFails(InAsset, FText::FromString(FString::Printf(TEXT("No valid material interface at index [%d]"), idx)));

			}
			else {
			
				const FString MaterialName = CurrentMaterial.MaterialInterface->GetName();

				// ensure the material is not WorldGrid
				if (CurrentMaterial.MaterialInterface->GetMaterial() == WorldGrid)
				{
					AssetFails(InAsset, FText::FromString(FString::Printf(TEXT("Material at index [%d][%s] is the default world grid material"), idx, *MaterialName)));
				}

				// ensure the material is not a deferred decal
				if (CurrentMaterial.MaterialInterface->IsDeferredDecal())
				{
					AssetFails(InAsset, FText::FromString(FString::Printf(TEXT("Material at index [%d][%s] is a deferred decal"), idx, *MaterialName)));
				}

				// ensure the blend mode is opaque or masked
				EBlendMode BlendMode = CurrentMaterial.MaterialInterface->GetBlendMode();

				if (BlendMode != EBlendMode::BLEND_Opaque && BlendMode != EBlendMode::BLEND_Masked)
				{
					AssetFails(InAsset, FText::FromString(FString::Printf(TEXT("Material at index [%d][%s] is not opaque or masked"), idx, *MaterialName)));
				}

				// check for customized uvs
				if (CurrentMaterial.MaterialInterface->HasCustomizedUVs())
				{
					AssetFails(InAsset, FText::FromString(FString::Printf(TEXT("Material at index [%d][%s] has customized UVs"), idx, *MaterialName)));
				}

				// check for vertex interpolator
				if (CurrentMaterial.MaterialInterface->HasVertexInterpolator())
				{
					AssetFails(InAsset, FText::FromString(FString::Printf(TEXT("Material at index [%d][%s] has a vertex interpolator"), idx, *MaterialName)));
				}

				// check for WPO
				if (CurrentMaterial.MaterialInterface->ShouldAlwaysEvaluateWorldPositionOffset())
				{
					AssetFails(InAsset, FText::FromString(FString::Printf(TEXT("Material at index [%d][%s] has WPO enabled"), idx, *MaterialName)));
				}
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
