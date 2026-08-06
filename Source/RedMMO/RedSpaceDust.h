#pragma once

#include "CoreMinimal.h"
#include "Components/SceneComponent.h"
#include "RedSpaceDust.generated.h"

class UHierarchicalInstancedStaticMeshComponent;

/**
 * VELOCITY SENSATION: a field of thin glowing streaks anchored in WORLD space around the ship.
 * As the ship flies, streaks flow past (parallax = speed feeling); each streak that falls behind
 * is recycled ahead. Streaks stretch along the flight direction with speed. Static-mesh instances
 * only — Metal-safe, no GPU Niagara. Hidden below MinSpeed so parked/landed ships stay clean.
 */
UCLASS(ClassGroup = (Custom), meta = (BlueprintSpawnableComponent))
class REDMMO_API URedSpaceDust : public USceneComponent
{
	GENERATED_BODY()

public:
	URedSpaceDust();
	virtual void BeginPlay() override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	UPROPERTY(EditAnywhere, Category = "Red|Dust")
	int32 StreakCount = 60;
	/** Streaks only show above this speed (cm/s). */
	UPROPERTY(EditAnywhere, Category = "Red|Dust")
	float MinSpeed = 2500.f;
	/** Field radius around/ahead of the ship (cm). */
	UPROPERTY(EditAnywhere, Category = "Red|Dust")
	float FieldRadius = 9000.f;

private:
	UPROPERTY()
	UHierarchicalInstancedStaticMeshComponent* Streaks = nullptr;
	TArray<FVector> Points;   // world-space anchor per instance
	bool bVisibleNow = false;

	void ReseedAll(const FVector& Center);
	FVector RandomPointAround(const FVector& Center, const FVector& FlightDir) const;
};
