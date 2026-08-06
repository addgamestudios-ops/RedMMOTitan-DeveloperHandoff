#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PawnMovementComponent.h"
#include "RedShipMovementComponent.generated.h"

class UCurveFloat;
class UBoxComponent;
class UPrimitiveComponent;
class AActor;

DECLARE_LOG_CATEGORY_EXTERN(LogRedShip, Log, All);

/** External speed cap in cm/s (<=0 = no cap). Optional governor hook. */
DECLARE_DELEGATE_RetVal(float, FRedShipExternalSpeedCap);

/**
 * Kinematic 6DOF flight movement (ported verbatim from the proven Vibe ship).
 * Per tick: DesiredVelocity = local input rotated to world * CurrentMaxSpeed; Velocity VInterpTo
 * (arcade in atmosphere, drift in space); quaternion-only rotation (no gimbal lock); radial
 * auto-level toward (Ship - PlanetCenter) in atmosphere; swept SafeMoveUpdatedComponent +
 * SlideAlongSurface; altitude speed cap interpolated, never stepped.
 */
UCLASS(BlueprintType, Blueprintable, ClassGroup = (Red), meta = (BlueprintSpawnableComponent))
class REDMMO_API URedShipMovementComponent : public UPawnMovementComponent
{
	GENERATED_BODY()

public:
	URedShipMovementComponent();

	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
	virtual float GetMaxSpeed() const override;
	virtual bool ResolvePenetrationImpl(const FVector& Adjustment, const FHitResult& Hit, const FQuat& NewRotationQuat) override;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Ship|Planet")
	FVector PlanetCenter = FVector::ZeroVector;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Ship|Planet", meta = (ClampMin = "0.0"))
	float PlanetRadius = 0.0f;

	/** Altitude AGL (cm) where atmosphere handling ends and space begins. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Ship|Planet", meta = (ClampMin = "0.0"))
	float AtmosphereTopAltitude = 500000.0f;

	/** Minimum root clearance above the planet surface; prevents the ship from flying through the shell. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Ship|Planet", meta = (ClampMin = "0.0"))
	float MinimumSurfaceClearance = 300.0f;

	/** Distance advantage required before an overlapping moon replaces the current gravity body. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Ship|Planet", meta = (ClampMin = "0.0"))
	float GravityBodySwitchHysteresis = 50000.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Ship|Handling", meta = (ClampMin = "0.0", UIMax = "20.0"))
	float ResponsivenessAtmosphere = 5.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Ship|Handling", meta = (ClampMin = "0.0", UIMax = "20.0"))
	float ResponsivenessSpace = 2.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Ship|Handling", meta = (ClampMin = "0.0", UIMax = "360.0"))
	float PitchRateDeg = 90.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Ship|Handling", meta = (ClampMin = "0.0", UIMax = "360.0"))
	float YawRateDeg = 60.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Ship|Handling", meta = (ClampMin = "0.0", UIMax = "360.0"))
	float RollRateDeg = 120.0f;

	// 0 = full manual 6DOF (no auto-leveling fighting the pilot when pitching up to leave atmosphere).
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Ship|Handling", meta = (ClampMin = "0.0", UIMax = "10.0"))
	float AutoLevelStrength = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Ship|Handling")
	bool bAutoLevelYieldsToRollInput = true;

	/** Altitude->speed cap curve. X = altitude AGL (km), Y = max speed (m/s). FallbackMaxSpeed if unset. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Ship|Speed")
	TObjectPtr<UCurveFloat> AltitudeSpeedCurve;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Ship|Speed", meta = (ClampMin = "100.0"))
	float FallbackMaxSpeed = 12000.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Ship|Speed", meta = (ClampMin = "0.1", UIMax = "10.0"))
	float SpeedCapInterpRate = 1.5f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Ship|Speed", meta = (ClampMin = "1.0", UIMax = "5.0"))
	float BoostSpeedMultiplier = 1.35f;

	/** Vacuum cruise multiplier applied after leaving AtmosphereTopAltitude. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Ship|Speed", meta = (ClampMin = "1.0", ClampMax = "4.0"))
	float SpaceSpeedMultiplier = 2.25f;

	/** Additional response in vacuum so the craft continues to build speed instead of feeling capped. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Ship|Speed", meta = (ClampMin = "1.0", ClampMax = "3.0"))
	float SpaceAccelerationMultiplier = 1.35f;

	/** Absolute safety cap after vacuum and boost multipliers (cm/s). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Ship|Speed", meta = (ClampMin = "1000.0"))
	/** Raised so an 8 km atmosphere climb can reach vacuum without a soft speed wall. */
	float AbsoluteMaxSpeed = 180000.f;

	FRedShipExternalSpeedCap ExternalSpeedCap;

	UFUNCTION(BlueprintCallable, Category = "Red|Ship")
	void AddMoveInput(const FVector& LocalInput);

	UFUNCTION(BlueprintCallable, Category = "Red|Ship")
	void AddRotationInput(const FVector& RotationInput);

	UFUNCTION(BlueprintCallable, Category = "Red|Ship")
	void SetBoostInput(bool bInBoost);

	/** Clears all queued/latched pilot input without changing the configured flight model. */
	UFUNCTION(BlueprintCallable, Category = "Red|Ship")
	void ClearFlightInputState();

	UFUNCTION(BlueprintPure, Category = "Red|Ship")
	float GetAltitudeAGL() const;

	UFUNCTION(BlueprintPure, Category = "Red|Ship")
	bool IsInAtmosphere() const;

	UFUNCTION(BlueprintPure, Category = "Red|Ship")
	float GetCurrentMaxSpeed() const;

	UFUNCTION(BlueprintPure, Category = "Red|Ship")
	bool IsBoosting() const;

	UFUNCTION(BlueprintPure, Category = "Red|Ship")
	FVector GetLastMoveInput() const;

	UFUNCTION(BlueprintPure, Category = "Red|Ship")
	FVector GetLastRotationInput() const;

	/** Stable body selected by the movement tick; read-only for acceptance telemetry. */
	UFUNCTION(BlueprintPure, Category = "Red|Ship|Planet")
	FName GetCurrentGravityBodyId() const { return CurrentGravityBodyId; }

	/** Shared local/server swept move, slide, exact-terrain recovery, and velocity bookkeeping. */
	void MoveWithPlanetCollision(const FVector& Delta, const FQuat& NewRotation, float DeltaTime);

	/**
	 * Registers the single fitted body envelope used for translation and bounded angular preflight.
	 * The root remains UpdatedComponent and is the only component moved by this movement component.
	 */
	void SetTranslationCollisionEnvelope(UBoxComponent* InEnvelope);
	UBoxComponent* GetTranslationCollisionEnvelope() const;

	/**
	 * Atomically commits a local landing/parking pose only after preflighting the sphere-root
	 * native route and either the fitted-box translation route or a conservative two-degree
	 * fitted-box screw-motion corridor. The endpoint must also be native-clear for both shapes
	 * and exact-terrain-clear for the fitted envelope. Deferred scoped movement prevents a
	 * rejected postcheck from escaping; every failed route or postcheck preserves the prior pose.
	 */
	bool TryCommitClearPlacement(
		const FVector& TargetRootLocation,
		const FQuat& TargetRootRotation,
		bool bRequireMatchingPlanet,
		ETeleportType Teleport);

protected:
	virtual bool MoveUpdatedComponentImpl(
		const FVector& Delta,
		const FQuat& NewRotation,
		bool bSweep,
		FHitResult* OutHit = nullptr,
		ETeleportType Teleport = ETeleportType::None) override;
	static FVector ComputeNewVelocity(const FVector& CurrentVelocity, const FVector& DesiredVelocity, float Responsiveness, float MaxSpeed, float DeltaTime);
	float EvaluateAltitudeSpeedCap(float AltitudeAGL) const;
	FQuat ComputeNewRotation(const FQuat& CurrentQuat, const FVector& ClampedRotationInput, float DeltaTime) const;
	void UpdateFlightMode(float AltitudeAGL);
	bool TryResolvePassiveTerrainPenetration();
	void ClampToPlanetSurface();

private:
	enum class ESurfaceRecoveryPolicy : uint8
	{
		ExactTerrainPenetration,
		LegacyVoid
	};

	enum class ESurfaceRecoveryResult : uint8
	{
		Rejected,
		NotRequired,
		Committed
	};

	enum class ETranslationEnvelopeOverlapMode : uint8
	{
		None,
		NativeDeferred,
		ExactTerrain
	};

	void ClearPendingTranslationEnvelopePenetration();
	ESurfaceRecoveryResult TryCommitBoundedSurfaceRecovery(
		const FVector& RequestedRootLocation,
		ESurfaceRecoveryPolicy Policy,
		const FHitResult* AuthenticatedSurfaceHit = nullptr,
		const FIntVector* AuthenticatedSurfaceChunkKey = nullptr);

	FVector PendingMoveInput = FVector::ZeroVector;
	FVector PendingRotationInput = FVector::ZeroVector;
	FVector LastMoveInput = FVector::ZeroVector;
	FVector LastRotationInput = FVector::ZeroVector;
	bool bPendingBoostInput = false;
	bool bBoostActive = false;
	bool bInAtmosphere = false;
	bool bFlightModeInitialized = false;
	bool bGovernorEngaged = false;
	bool bPositionCorrected = false;
	bool bSurfaceVelocityAdjusted = false;
	bool bResolvingPassiveTerrainPenetration = false;
	bool bResolvingTranslationEnvelopePenetration = false;
	bool bSuppressNextTranslationEnvelopeOverlapToken = false;
	bool bAngularEnvelopeMoveVetoed = false;
	ETranslationEnvelopeOverlapMode PendingTranslationEnvelopeOverlapMode =
		ETranslationEnvelopeOverlapMode::None;
	TWeakObjectPtr<UPrimitiveComponent> PendingTranslationEnvelopeHitComponent;
	FVector PendingTranslationEnvelopeRootStart = FVector::ZeroVector;
	FQuat PendingTranslationEnvelopeRootRotation = FQuat::Identity;
	UPROPERTY(Transient)
	TObjectPtr<UBoxComponent> TranslationCollisionEnvelope;
	mutable bool bWarnedMissingCurve = false;
	float CurrentMaxSpeed = -1.0f;
	double NextPassiveTerrainProbeWorldSeconds = 0.0;
	FName CurrentGravityBodyId = NAME_None;
};
