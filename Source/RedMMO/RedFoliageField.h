#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "TimerManager.h"
#include "RedFoliageField.generated.h"

class UHierarchicalInstancedStaticMeshComponent;
class UStaticMesh;
class UMaterialInterface;

/**
 * Dense instanced ground cover for the PlanetGen mesh planet (ported from the proven Vibe field).
 * One HISM per mesh, tens of thousands of instances radially traced onto the live CLM surface
 * around this actor — the cheap way to Fortnite-grass density. Instances bake into the map.
 */
UCLASS(BlueprintType, Blueprintable)
class REDMMO_API ARedFoliageField : public AActor
{
	GENERATED_BODY()

public:
	ARedFoliageField();

	// Dense ground cover. Ferns are deliberately excluded: this layer is recoloured into
	// a two-tone extraterrestrial grass carpet at runtime.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedFoliage")
	TArray<TSoftObjectPtr<UStaticMesh>> GrassMeshes;

	// Sparser bulb, marsh-tail and broad-leaf silhouettes. Ordinary ferns are deliberately absent.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedFoliage")
	TArray<TSoftObjectPtr<UStaticMesh>> FlowerMeshes;

	// Desert boulders/clumps and large cliff/hoodoo silhouettes. Palm assets are deliberately absent.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedFoliage|Biome")
	TArray<TSoftObjectPtr<UStaticMesh>> RockMeshes;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedFoliage|Biome")
	TArray<TSoftObjectPtr<UStaticMesh>> CliffMeshes;

	// Ice-blue plants used only on polar or high-altitude samples.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedFoliage|Biome")
	TArray<TSoftObjectPtr<UStaticMesh>> SnowMeshes;

	/** SoStylized grass default materials are RVT-driven and render GRAY on this planet —
	 *  the project-local instance disables colormap/RVT switches so Base Color stays alien. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedFoliage")
	TSoftObjectPtr<UMaterialInterface> GrassOverrideMaterial;

	// Each ground-cover mesh gets a distinct, saturated colour. The SoStylized material's
	// real exposed parameter is named "Base Color", so this preserves its cutout and wind.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedFoliage|Alien Palette")
	TArray<FLinearColor> GrassTintPalette;

	// Bulb/marsh-tail/broad-leaf components cycle through this palette. Runtime dynamic
	// instances preserve every mesh's authored opacity texture while replacing its earth tones.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedFoliage|Alien Palette")
	TArray<FLinearColor> AlienAccentTintPalette;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedFoliage")
	int32 GrassCount = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedFoliage")
	int32 FlowerCount = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedFoliage|Biome")
	int32 RockCount = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedFoliage|Biome")
	int32 CliffCount = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedFoliage|Biome")
	int32 SnowAccentCount = 0;

	// Scatter radius along the surface from this actor, in cm.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedFoliage")
	float Radius = 52000.f;

	// If > 0, skip any instance whose surface point is below this radius from the planet
	// centre (i.e. underwater). Keeps foliage off the seafloor.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedFoliage")
	float SeaLevelRadius = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedFoliage")
	float GrassMinHeight = 30.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedFoliage")
	float GrassMaxHeight = 72.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedFoliage")
	int32 Seed = 1337;

	// When true, an empty field scatters itself 2.5s after BeginPlay. Off by default:
	// baked instances load with the level; re-tracing at runtime is very expensive.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedFoliage")
	bool bAutoGenerateOnPlay = false;

	/** Hard runtime guard for the current desert/ocean-only art pass. Also clears baked HISMs. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedFoliage")
	bool bSuppressAllProceduralDressing = true;

	UFUNCTION(BlueprintPure, Category = "RedFoliage")
	int32 GetInstanceTotal() const;

	// Build (or rebuild) all instances now. Works in-editor and from Python.
	UFUNCTION(BlueprintCallable, CallInEditor, Category = "RedFoliage")
	void Regenerate();

	UFUNCTION(BlueprintCallable, CallInEditor, Category = "RedFoliage")
	void ClearFoliage();

protected:
	virtual void BeginPlay() override;

private:
	enum class EScatterLayer : uint8
	{
		Grass,
		AlienAccent,
		DesertRock,
		DesertCliff,
		SnowAccent,
	};

	UPROPERTY()
	TArray<UHierarchicalInstancedStaticMeshComponent*> Hisms;

	FTimerHandle RegenerateRetryTimer;
	bool bWaitingForPlanetTerrain = false;

	void ScheduleRegenerationRetry(const TCHAR* Reason);
	UHierarchicalInstancedStaticMeshComponent* MakeHism(
		UStaticMesh* Mesh, bool bOverrideMaterial, bool bEnableCollision,
		EScatterLayer Layer, int32 MaterialVariant);
	int32 ScatterSet(const TArray<TSoftObjectPtr<UStaticMesh>>& Meshes, int32 Count,
		float MinH, float MaxH, bool bOverrideMaterial, bool bEnableCollision,
		EScatterLayer Layer, FRandomStream& Rng,
		const FVector& PlanetCenter, float DatumRadius, float PeakRadius,
		const AActor* PlanetActor, bool& bOutLoadedAnyMesh, bool& bOutFoundTerrainHit);
};
