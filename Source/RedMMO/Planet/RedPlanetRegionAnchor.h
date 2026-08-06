#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "RedPlanetRegionAnchor.generated.h"

class UBillboardComponent;
class USceneComponent;
class UTextRenderComponent;

/**
 * Lightweight, non-colliding authoring marker for one deterministic region site.
 *
 * The actor mirrors immutable FPlanetRegionService metadata. It creates no gameplay boundary,
 * does not stream terrain, and deliberately has no tick, collision, nav, overlap, or replication.
 */
UCLASS(BlueprintType, Blueprintable)
class REDMMO_API ARedPlanetRegionAnchor : public AActor
{
	GENERATED_BODY()

public:
	ARedPlanetRegionAnchor();

	virtual void OnConstruction(const FTransform& Transform) override;

	/** Refreshes all read-only metadata and owned actor tags from RegionIndex. */
	UFUNCTION(BlueprintCallable, CallInEditor, Category = "RedMMO|Planet Region")
	void RefreshFromRegionService();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region")
	TObjectPtr<USceneComponent> SceneRoot;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region", meta = (ClampMin = "0", ClampMax = "26", UIMin = "0", UIMax = "26"))
	int32 RegionIndex = 0;

	/** Centre used only when bPositionAtRegionSite is enabled. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region|Placement")
	FVector PlanetCenter = FVector::ZeroVector;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region|Placement", meta = (ClampMin = "1.0", Units = "cm"))
	double PlanetRadiusCm = 795774.7154594767;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region|Placement")
	bool bPositionAtRegionSite = true;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region|Placement")
	bool bOrientToSurface = true;

	/** Unsigned service seed represented as int64 so Blueprint preserves every uint32 value. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region")
	int64 Seed = 0;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region")
	int32 VariationIndex = 0;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region")
	FName ArchetypeTag = NAME_None;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region")
	FVector UnitSite = FVector::UpVector;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region")
	double NominalAreaSquareKm = 0.0;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region", meta = (Units = "cm"))
	double SuggestedHubRadiusCm = 0.0;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region", meta = (Units = "cm"))
	double SuggestedFlattenCoreRadiusCm = 0.0;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region", meta = (Units = "cm"))
	double SuggestedFlattenBlendRadiusCm = 0.0;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region|Climate", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float Temperature01 = 0.5f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region|Climate", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float Moisture01 = 0.5f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region|Climate", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float AlienIntensity01 = 0.5f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet Region|Climate", meta = (ClampMin = "-1.0", ClampMax = "1.0"))
	float ElevationBias = 0.0f;

#if WITH_EDITORONLY_DATA
	UPROPERTY(VisibleAnywhere, Category = "RedMMO|Planet Region|Visualization")
	TObjectPtr<UBillboardComponent> EditorBillboard;

	UPROPERTY(VisibleAnywhere, Category = "RedMMO|Planet Region|Visualization")
	TObjectPtr<UTextRenderComponent> EditorLabel;
#endif

private:
	void RefreshOwnedActorTags();
	void RefreshPlacement();

#if WITH_EDITORONLY_DATA
	void RefreshEditorVisualization();
#endif
};
