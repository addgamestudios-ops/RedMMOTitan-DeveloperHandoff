#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "RedShip.generated.h"

class USphereComponent;
class UBoxComponent;
class USceneComponent;
class UStaticMeshComponent;
class USpringArmComponent;
class UCameraComponent;
class UMaterialInterface;
class UAudioComponent;
class URedSpaceDust;
class URedShipMovementComponent;
class URedShipCollisionDriver;
class ARedPlayerCharacter;
class UNiagaraSystem;
struct FDamageEvent;
struct FHitResult;

/**
 * Flyable spaceship (Space Colony SM_ship) using the proven Vibe 6DOF flight movement:
 * W/S thrust, A/D strafe, Space/LeftCtrl lift, mouse pitch/yaw, Q/E roll, Shift boost.
 * Planet-aware (radial auto-level + atmosphere/space mode + altitude speed cap). Fires RedBolt.
 * Pilot boards via ARedPlayerCharacter::EnterVehicle; press B to leave (V remains compatible). Press C to toggle cockpit camera.
 */
UCLASS()
class REDMMO_API ARedShip : public APawn
{
	GENERATED_BODY()

public:
	ARedShip();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void OnConstruction(const FTransform& Transform) override;
	virtual void SetupPlayerInputComponent(UInputComponent* InInput) override;
	virtual UPawnMovementComponent* GetMovementComponent() const override;
	virtual FVector GetVelocity() const override;
	virtual float TakeDamage(float DamageAmount, const FDamageEvent& DamageEvent,
		AController* EventInstigator, AActor* DamageCauser) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** Board this ship: hide + park the pilot and possess the ship. */
	virtual void EnterShip(ARedPlayerCharacter* InPilot);

	/** Normalized replicated hull integrity for HUDs and Blueprint vehicle wrappers. */
	UFUNCTION(BlueprintPure, Category = "Red|Ship|Combat")
	float GetHealthFraction() const;

	/** Normalized authoritative weapon heat (zero = cold, one = fully overheated). */
	UFUNCTION(BlueprintPure, Category = "Red|Ship|Combat")
	float GetWeaponHeatFraction() const;

	UFUNCTION(BlueprintPure, Category = "Red|Ship|Combat")
	bool IsWeaponOverheated() const { return bWeaponOverheated; }

	UFUNCTION(BlueprintPure, Category = "Red|Ship|Landing")
	bool IsLandingAssistEnabled() const { return bLandingAssistEnabled; }

	UFUNCTION(BlueprintPure, Category = "Red|Ship|Landing")
	bool IsLandingSettled() const { return bLandingSettled; }

	/** Fire one server-authoritative test shot (also usable by MCP/PIE automation). */
	UFUNCTION(BlueprintCallable, Category = "Red|Ship|Combat")
	void TestFire();

	/** Exact current-body landing surface query shared by landing, parking, and automation. */
	bool QueryLandingSurface(
		FHitResult& OutHit,
		FVector& OutRadialUp,
		bool* bOutMatchingPlanetTerrain = nullptr) const;

	/**
	 * Emits one read-only gravity-frame acceptance snapshot. Invoke explicitly
	 * before landing and after reboard; request ship-up alignment for settled
	 * acceptance phases. This is never called from Tick.
	 */
	UFUNCTION(Exec, BlueprintCallable, Category = "Red|Ship|Diagnostics")
	void LogGravityAcceptanceSnapshot(FString Phase, bool bRequireShipUpAlignment = false);

protected:
	UPROPERTY(VisibleAnywhere, Category = "Ship") USphereComponent* CollisionSphere;
	UPROPERTY(VisibleAnywhere, Category = "Ship") UStaticMeshComponent* Hull;
	/** Conservative ship/world envelope; detailed visible meshes handle weapon queries. */
	UPROPERTY(VisibleAnywhere, Category = "Ship|Collision") UBoxComponent* RuntimeHullCollision;
	/** Pawn-only central roof surface for stable character floor tests while parked. */
	UPROPERTY(VisibleAnywhere, Category = "Ship|Collision") UBoxComponent* RuntimeDeckCollision;
	UPROPERTY(VisibleAnywhere, Category = "Ship") USpringArmComponent* CameraBoom;
	UPROPERTY(VisibleAnywhere, Category = "Ship") UCameraComponent* ShipCamera;
	UPROPERTY(VisibleAnywhere, Category = "Ship") URedShipMovementComponent* ShipMovement;
	/** Async velocity-led voxel invoker + speed governor (smooth flight, no inline-cook hitches). */
	UPROPERTY(VisibleAnywhere, Category = "Ship") URedShipCollisionDriver* CollisionDriver;
	/** One flame plume per engine pod (2 outer wingtip + 2 inner). */
	UPROPERTY(VisibleAnywhere, Category = "Ship") TArray<UStaticMeshComponent*> Plumes;
	UPROPERTY(VisibleAnywhere, Category = "Ship|FX") TArray<TObjectPtr<USceneComponent>> PlumeHardpoints;
	UPROPERTY(VisibleAnywhere, Category = "Ship|Weapon") TObjectPtr<USceneComponent> TurretMuzzleLeft;
	UPROPERTY(VisibleAnywhere, Category = "Ship|Weapon") TObjectPtr<USceneComponent> TurretMuzzleRight;

	UPROPERTY(EditAnywhere, Category = "Ship|Weapon") TSubclassOf<AActor> ProjectileClass;
	UPROPERTY(EditAnywhere, Category = "Ship|Weapon") class USoundBase* ShipFireSound;
	UPROPERTY(EditAnywhere, Category = "Ship|Weapon") class USoundAttenuation* ShipFireAttenuation;
	/** Optional muzzle burst. Its local +X is aligned with the accepted shot direction. */
	UPROPERTY(EditAnywhere, Category = "Ship|Weapon") TObjectPtr<UNiagaraSystem> ShipMuzzleFlashFX;
	UPROPERTY(EditAnywhere, Category = "Ship|FX") UMaterialInterface* PlumeMaterial;
	/** Looping engine rumble — the deep foundation layer; volume/pitch ride the throttle. */
	UPROPERTY(VisibleAnywhere, Category = "Ship|FX") UAudioComponent* EngineAudio;
	/** Looping engine character layer (hum/turbine/thrum) on top of the rumble. */
	UPROPERTY(VisibleAnywhere, Category = "Ship|FX") UAudioComponent* EngineWhineAudio;
	/** Selectable character loops — cycle live with the `EngineStyle N` console exec while piloting. */
	UPROPERTY(EditAnywhere, Category = "Ship|FX") TArray<USoundBase*> EngineWhineStyles;
	/** Speed-feel streak field (see URedSpaceDust). */
	UPROPERTY(VisibleAnywhere, Category = "Ship|FX") URedSpaceDust* SpaceDust;

	/** Yaw applied to the art mesh so SM_ship's +Y nose points along the pawn's +X. */
	UPROPERTY(EditAnywhere, Category = "Ship") float MeshYaw = 270.f;
	/** Native forward axis of the art asset, used by server-side muzzle aim validation. */
	UPROPERTY(EditAnywhere, Category = "Ship|Weapon") FVector MeshForwardAxis = FVector::YAxisVector;

	UPROPERTY(EditAnywhere, Category = "Ship|Camera") float BaseFOV = 90.f;
	UPROPERTY(EditAnywhere, Category = "Ship|Camera") float BoostFOV = 108.f;
	UPROPERTY(EditAnywhere, Category = "Ship|Camera") float FOVInterpSpeed = 4.f;
	UPROPERTY(EditAnywhere, Category = "Ship|Camera") float MaxVisualBankAngle = 30.f;
	UPROPERTY(EditAnywhere, Category = "Ship|Camera") float VisualBankInterpSpeed = 5.f;
	UPROPERTY(EditAnywhere, Category = "Ship|Camera") float ChaseArmLength = 5200.f;
	UPROPERTY(EditAnywhere, Category = "Ship|Camera") float FirstPersonArmLength = 0.f;
	UPROPERTY(EditAnywhere, Category = "Ship|Camera") FVector ChaseCameraOffset = FVector(0.f, 0.f, 950.f);  // ship sits low in frame so the center reticle floats clear of the hull
	UPROPERTY(EditAnywhere, Category = "Ship|Camera") FVector FirstPersonCameraOffset = FVector(950.f, 0.f, 280.f);
	/** Mouse-wheel cruise step applied to FighterCruiseSpeed / FallbackMaxSpeed (cm/s per notch). */
	UPROPERTY(EditAnywhere, Category = "Ship|Handling", meta = (ClampMin = "100.0"))
	float ThrottleWheelStep = 2000.f;
	UPROPERTY(EditAnywhere, Category = "Ship|Handling", meta = (ClampMin = "500.0"))
	float MinCruiseSpeed = 1000.f;
	UPROPERTY(EditAnywhere, Category = "Ship|Handling", meta = (ClampMin = "1000.0"))
	float MaxCruiseSpeed = 120000.f;
	/** Above this height AGL, V exits into local EVA instead of searching for planet ground. */
	UPROPERTY(EditAnywhere, Category = "Ship|Camera", meta = (ClampMin = "100000.0"))
	float OrbitalExitMinAltitude = 1000000.f;

	/** Optional mouse-look gate. Disabled by default so PIE mouse steering works without RMB capture edge cases. */
	UPROPERTY(EditAnywhere, Category = "Ship|Input") bool bRequireRightMouseForLook = false;

	/** Optional L-toggle. Only affects the craft inside LandingAssistTraceDistance of real terrain. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Replicated, Category = "Red|Ship|Landing")
	bool bLandingAssistEnabled = false;
	/** True after a server-authoritative touchdown; replicated for Blueprint/audio presentation. */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Replicated, Category = "Red|Ship|Landing")
	bool bLandingSettled = false;
	UPROPERTY(EditAnywhere, Category = "Red|Ship|Landing", meta = (ClampMin = "500.0"))
	float LandingAssistTraceDistance = 8000.f;
	UPROPERTY(EditAnywhere, Category = "Red|Ship|Landing", meta = (ClampMin = "100.0"))
	float LandingAssistMaxDescentSpeed = 900.f;
	UPROPERTY(EditAnywhere, Category = "Red|Ship|Landing", meta = (ClampMin = "0.1"))
	float LandingAssistAlignSpeed = 3.5f;
	UPROPERTY(EditAnywhere, Category = "Red|Ship|Landing", meta = (ClampMin = "0.0"))
	float LandingAssistLateralDamping = 4.f;
	UPROPERTY(EditAnywhere, Category = "Red|Ship|Landing", meta = (ClampMin = "5.0"))
	float LandingAssistTouchdownDistance = 45.f;
	UPROPERTY(EditAnywhere, Category = "Red|Ship|Landing", meta = (ClampMin = "0.0"))
	float LandingAssistSurfaceGap = 20.f;

	/** Controllable no-curve cruise cap. Applied over stale Blueprint component defaults at runtime. */
	UPROPERTY(EditAnywhere, Category = "Ship|Handling", meta = (ClampMin = "1000.0", ClampMax = "30000.0"))
	float FighterCruiseSpeed = 12000.f;

	UPROPERTY(EditAnywhere, Category = "Ship|Weapon") float FireInterval = 0.14f;
	/** Minimum dot between accepted aim and the craft nose (0.25 keeps chase-camera aim fireable). */
	UPROPERTY(EditAnywhere, Category = "Ship|Weapon", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float MinFireAimDot = 0.25f;

	/** Hull durability. Health is initialized from this value by the authority. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Replicated, Category = "Red|Ship|Combat", meta = (ClampMin = "1.0"))
	float MaxHealth = 1600.f;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, ReplicatedUsing = OnRep_Health, Category = "Red|Ship|Combat")
	float Health = 1600.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Red|Ship|Combat", meta = (ClampMin = "1.0"))
	float MaxWeaponHeat = 100.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Red|Ship|Combat", meta = (ClampMin = "0.0"))
	float HeatPerShot = 13.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Red|Ship|Combat", meta = (ClampMin = "0.0"))
	float HeatCooldownPerSecond = 28.f;

	/** An overheated cannon becomes available again only after cooling below this fraction. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Red|Ship|Combat", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float OverheatRecoveryFraction = 0.35f;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Replicated, Category = "Red|Ship|Combat")
	float WeaponHeat = 0.f;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Replicated, Category = "Red|Ship|Combat")
	bool bWeaponOverheated = false;

private:
	// input -> movement component
	void ThrustInput(float V);
	void StrafeInput(float V);
	void LiftInput(float V);
	void PitchInput(float V);
	void YawInput(float V);
	void RollInput(float V);
	/** Mouse wheel: cruise thrust/speed. Steals CameraZoom so the chase arm stays framed. */
	void ThrottleWheelInput(float V);
	void StartBoost();
	void StopBoost();
	void ToggleLandingAssist();
	void SetLandingAssistEnabled(bool bEnabled);
	UFUNCTION(Server, Reliable)
	void ServerSetLandingAssistEnabled(bool bEnabled);
	void ApplyLandingAssist(float DeltaSeconds);
	float GetLandingSupportDistance(
		const FVector& SurfaceNormal,
		const FQuat& TargetRootRotation) const;
	FVector GetLandingFlightVelocity() const;
	void SetLandingFlightVelocity(const FVector& NewVelocity);
	void SetLandingSettled(bool bSettled);
	bool IsLookAllowed() const;
	void ApplyRemoteAuthoritativeFlight(float DeltaSeconds);
	UFUNCTION(Server, Unreliable)
	void ServerSetFlightInput(FVector MoveAxes, FVector RotationAxes, bool bBoost);

	// weapon
	void StartFire();
	void StopFire();
	void Fire();
	void ToggleShipCamera();
	UFUNCTION(Server, Reliable)
	void ServerFire();
	UFUNCTION(NetMulticast, Unreliable)
	void MulticastFireCosmetics(FVector_NetQuantize MuzzleLocation, FVector_NetQuantizeNormal ShotDirection);
	bool TryFireAuthoritative();
	bool ComputeServerFireTransform(bool bUseLeftMuzzle, FVector& OutStart, FRotator& OutDirection) const;
	bool SpawnBolt(FVector Start, FRotator Dir);
	void UpdateWeaponHeat(float DeltaSeconds);
	void HandleDeath(AController* DamageInstigator = nullptr, AActor* DamageCauser = nullptr);
	UFUNCTION()
	void OnRep_Health();

	/** BlueprintCallable so automated PIE self-tests can drive the full board/exit loop. */
	UFUNCTION(BlueprintCallable, Category = "Red|Ship")
	virtual void ExitShip();
	UFUNCTION(Server, Reliable)
	void ServerExitShip();
	void ExitShipAuthority(bool bEmergencyEject);
	bool IsOrbitalExit() const;
	void UpdateVisuals(float DeltaSeconds);
	/**
	 * Runs the virtual hull fit and publishes its fitted translation envelope only after the
	 * complete derived implementation succeeds. BeginPlay and retry Tick must use this wrapper.
	 */
	bool TryConfigureRuntimeCollisionHulls();
	/** Fit collision to the visual hull. Specialized modular craft may override this with authored bounds. */
	virtual bool ConfigureRuntimeCollisionHulls();
	bool BindPlumeHardpointsToDetectedNozzles();
	void ApplyHardpointLayout();
	void ApplyPlumeLayout(bool bEditorPreview);

	bool bBoostHeld = false;
	bool bFiring = false;
public:
	/** BlueprintCallable so automated PIE self-tests can fire the ship's guns. */
	UFUNCTION(BlueprintCallable, Category = "Red|Ship")
	void StartFireTest() { bFiring = true; }
	UFUNCTION(BlueprintCallable, Category = "Red|Ship")
	void StopFireTest() { bFiring = false; }
	/** Console exec (routes here while piloting): swap the engine character loop live to A/B styles. */
	UFUNCTION(Exec)
	void EngineStyle(int32 StyleIndex);
private:
	int32 CurrentEngineStyle = 0;
	float FireCooldown = 0.f;
	double NextServerFireTime = 0.0;
	bool bMuzzleLeft = true;
	bool bDeathHandled = false;
	FVector LocalMoveAxes = FVector::ZeroVector;
	FVector LocalRotationAxes = FVector::ZeroVector;
	FVector ServerMoveAxes = FVector::ZeroVector;
	FVector ServerRotationAxes = FVector::ZeroVector;
	FVector RemoteFlightVelocity = FVector::ZeroVector;
	bool bServerBoostHeld = false;
	double LastServerFlightInputTime = -100.0;
	float CurrentVisualBank = 0.f;
	/** Chase by default so the craft stays framed; C toggles cockpit. */
	bool bFirstPersonCamera = false;
	bool bRuntimeCollisionHullsConfigured = false;
	/** Zero means the legacy measured hardpoints are active; positive means runtime nozzle anchors. */
	int32 DetectedNozzleCount = 0;
	bool bLoggedDetectedNozzles = false;

	/** Authority-owned occupant reference; replicated so all clients agree whether the craft is piloted. */
	UPROPERTY(Replicated) TObjectPtr<ARedPlayerCharacter> Pilot = nullptr;
};
