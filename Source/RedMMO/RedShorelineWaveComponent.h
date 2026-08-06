#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "RedShorelineWaveComponent.generated.h"

class ACLMPlanet;
class UMaterialInstanceDynamic;
class UProceduralMeshComponent;

/**
 * Local presentation for a radial PlanetGen ocean.
 *
 * SoStylized's main water material supplies the clear animated surface. Its edge-wave mask uses
 * DistanceToNearestSurface, which cannot see PlanetGen's runtime ProceduralMesh terrain. This
 * component samples PlanetGen's deterministic height field around the owning player, extracts the
 * actual sea-level contour, and renders a narrow animated SoStylized wave ribbon there. It also
 * replaces PlanetGen's default +X tangents on the water sphere so its moving normal maps remain
 * stable around the whole planet.
 */
UCLASS(ClassGroup = (Red), meta = (BlueprintSpawnableComponent))
class REDMMO_API URedShorelineWaveComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	URedShorelineWaveComponent();

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType,
		FActorComponentTickFunction* ThisTickFunction) override;

private:
	UPROPERTY(Transient)
	TObjectPtr<UProceduralMeshComponent> WaveMesh;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> WaveMaterial;

	TWeakObjectPtr<ACLMPlanet> CachedPlanet;

	FVector LastRibbonDirection = FVector::ZeroVector;
	FVector LastRibbonOwnerLocation = FVector(FLT_MAX);
	int32 LastRepairedWaterVertexCount = 0;
	float NextPlanetResolveTime = 0.f;
	float NextTangentAuditTime = 0.f;
	bool bLoggedNightWaterT04Suppression = false;

	bool EnsureLocalResources();
	void ResolvePlanet();
	void RepairWaterSphereTangents();
	void RebuildShorelineRibbon();
	void HideRibbon();
	float SampleSignedShoreHeight(const FVector& SphereDirection) const;
};
