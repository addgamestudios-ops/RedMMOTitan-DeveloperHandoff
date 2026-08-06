#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "RedOrbitalMiningSite.generated.h"

class UPointLightComponent;
class USphereComponent;
class UStaticMeshComponent;

/**
 * Runtime orbital mining landmark built from the AsteroidSpaceport pack.
 * Ship bolts can hit this actor to drain an ore pool, giving the orbital site
 * a first gameplay purpose instead of being only scenery.
 */
UCLASS()
class REDMMO_API ARedOrbitalMiningSite : public AActor
{
	GENERATED_BODY()

public:
	ARedOrbitalMiningSite();

	/** Aligns the station so its local up points away from the planet. */
	void AlignToPlanet(const FVector& InPlanetCenter);

	/** Called by projectiles when they strike the asteroid or mining facility. */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|Mining")
	float RegisterMiningHit(const FHitResult& Hit, float MiningStrength, AActor* MiningInstigator);

	UFUNCTION(BlueprintCallable, Category = "RedMMO|Mining")
	float GetOreFraction() const;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Mining", meta = (ClampMin = "0.0"))
	float OreRemaining = 250000.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Mining", meta = (ClampMin = "1.0"))
	float OreCapacity = 250000.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Mining", meta = (ClampMin = "1.0"))
	float ShipBoltMiningMultiplier = 18.0f;

protected:
	virtual void BeginPlay() override;

	UPROPERTY(VisibleAnywhere, Category = "RedMMO|Mining")
	TObjectPtr<USceneComponent> SceneRoot;

	UPROPERTY(VisibleAnywhere, Category = "RedMMO|Mining")
	TObjectPtr<UStaticMeshComponent> AsteroidPortMesh;

	UPROPERTY(VisibleAnywhere, Category = "RedMMO|Mining")
	TObjectPtr<UStaticMeshComponent> MiningAsteroidMesh;

	UPROPERTY(VisibleAnywhere, Category = "RedMMO|Mining")
	TObjectPtr<UStaticMeshComponent> FacilityMesh;

	UPROPERTY(VisibleAnywhere, Category = "RedMMO|Mining")
	TObjectPtr<UStaticMeshComponent> MiningRingMesh;

	UPROPERTY(VisibleAnywhere, Category = "RedMMO|Mining")
	TObjectPtr<UStaticMeshComponent> MiningTowerMesh;

	UPROPERTY(VisibleAnywhere, Category = "RedMMO|Mining")
	TObjectPtr<UStaticMeshComponent> MiningBridgeMesh;

	UPROPERTY(VisibleAnywhere, Category = "RedMMO|Mining")
	TObjectPtr<UStaticMeshComponent> MiningTorusMesh;

	UPROPERTY(VisibleAnywhere, Category = "RedMMO|Mining")
	TObjectPtr<UStaticMeshComponent> AntennaMesh;

	UPROPERTY(VisibleAnywhere, Category = "RedMMO|Mining")
	TObjectPtr<USphereComponent> MiningRange;

	UPROPERTY(VisibleAnywhere, Category = "RedMMO|Mining")
	TObjectPtr<UPointLightComponent> BeaconLight;

private:
	void ConfigureMineableMesh(UStaticMeshComponent* Mesh) const;
	void RefreshBeacon();

	FVector PlanetCenter = FVector::ZeroVector;
};
