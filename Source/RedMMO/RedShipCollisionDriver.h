#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Engine/EngineTypes.h"
#include "RedShipCollisionDriver.generated.h"

class USceneComponent;
class URedShipMovementComponent;

/**
 * Manages a voxel collision invoker for AVibeShipPawn (P1 Ship Flight).
 *
 * Soft dependency: the invoker component class (UVoxelCollisionInvokerComponent) is resolved
 * by object path at runtime and its properties are written via reflection, so
 * VibeEngineRuntime has no build dependency on the Voxel plugin. With the Voxel plugin
 * disabled the driver degrades to governor + raycast backstop only.
 *
 * Behavior:
 * - Invoker disabled above InvokerEnableAltitudeAGL (~1 km AGL), with hysteresis.
 * - Velocity-leading placement: invoker leads the ship by up to MaxLeadDistance along velocity.
 * - Speed governor: caches a speed cap each tick that URedShipMovementComponent queries,
 *   keeping async voxel collision cooking ahead of the pawn near ground.
 * - Forward raycast along the travel vector as anti-tunneling backstop.
 */
UCLASS(BlueprintType, ClassGroup = (Red), meta = (BlueprintSpawnableComponent))
class URedShipCollisionDriver : public UActorComponent
{
	GENERATED_BODY()

public:
	URedShipCollisionDriver();

	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	/** Object path of the voxel collision invoker component class, resolved by name at runtime (soft dependency). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe|Ship|Invoker")
	FString InvokerClassPath = TEXT("/Script/Voxel.VoxelCollisionInvokerComponent");

	/** The invoker is active only below this altitude AGL in cm (~1 km default). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe|Ship|Invoker", meta = (ClampMin = "0.0"))
	float InvokerEnableAltitudeAGL = 100000.0f;

	/** Hysteresis band in cm above the enable altitude, to avoid enable/disable toggle spam. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe|Ship|Invoker", meta = (ClampMin = "0.0"))
	float InvokerAltitudeHysteresis = 10000.0f;

	/** Radius in cm of cooked collision around the invoker. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe|Ship|Invoker", meta = (ClampMin = "1000.0"))
	float InvokerRadius = 15000.0f;

	/** Seconds of velocity lead applied to the invoker position. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe|Ship|Invoker", meta = (ClampMin = "0.0", UIMax = "10.0"))
	float InvokerLeadTime = 1.5f;

	/** Max lead distance in cm. Keep well under the voxel ~5 km / 1M-chunk invoker cap. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe|Ship|Invoker", meta = (ClampMin = "0.0"))
	float MaxLeadDistance = 40000.0f;

	/**
	 * If true the invoker requests an inline (blocking) collision cook when on uncooked ground.
	 * Off by default: the governor + raycast backstop handle it without game-thread hitches.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe|Ship|Invoker")
	bool bInvokerWaitForVoxelWorld = false;

	/** Governor cap = (MaxLeadDistance + InvokerRadius) / this: seconds the cooked bubble must stay ahead of flight. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe|Ship|Governor", meta = (ClampMin = "0.1", UIMax = "10.0"))
	float GovernorCookAheadTime = 2.0f;

	/** Forward raycast backstop look-ahead, in seconds of travel along the velocity vector. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe|Ship|Governor", meta = (ClampMin = "0.0", UIMax = "10.0"))
	float BackstopLookAheadTime = 1.5f;

	/** Fraction of the raycast hit distance the ship may cover per BackstopLookAheadTime when terrain is dead ahead. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe|Ship|Governor", meta = (ClampMin = "0.05", ClampMax = "1.0"))
	float BackstopBrakeFraction = 0.5f;

	/** The governor never caps below this speed in cm/s, so the ship can always land. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe|Ship|Governor", meta = (ClampMin = "100.0"))
	float GovernorMinSpeed = 3000.0f;

	/** Channel used by the anti-tunneling forward raycast (voxel terrain blocks WorldStatic). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe|Ship|Governor")
	TEnumAsByte<ECollisionChannel> BackstopTraceChannel = ECC_WorldStatic;

	/** Speed cap in cm/s the movement component queries each tick; <= 0 means no cap. */
	float QuerySpeedCap() const;

private:
	void ResolveInvokerClass();
	void CreateInvoker();
	void SetInvokerEnabled(bool bNewEnabled, float AltitudeAGL);
	void UpdateInvokerLocation(const FVector& ShipLocation, const FVector& ShipVelocity);
	float ComputeSpeedCap(const FVector& ShipLocation, const FVector& ShipVelocity, bool bIncludeCookAheadCap) const;

	bool SetInvokerBoolProperty(FName PropertyName, bool bValue) const;
	bool SetInvokerFloatProperty(FName PropertyName, float Value) const;

	UPROPERTY(Transient)
	TObjectPtr<UClass> InvokerClass;

	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> InvokerComponent;

	TWeakObjectPtr<URedShipMovementComponent> ShipMovement;

	float CachedSpeedCap = 0.0f;
	bool bInvokerEnabled = false;
	bool bTriedResolvingClass = false;
};
