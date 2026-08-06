#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "RedPlanetPresentationTuning.h"
#include "RedShuttleBase.generated.h"

class ARedBolt;
class UBoxComponent;
class UCameraComponent;
class USceneComponent;
class USpringArmComponent;
class UNiagaraSystem;
class USoundBase;
class USoundAttenuation;
struct FDamageEvent;

/**
 * C++ parent for the pack BP_Shuttle on a round planet.
 * While possessed: keeps hull zero-roll in the local radial frame, auto-starts pack EngineOn,
 * disables world-Z FloatingPawnMovement, and drives radial flight from WASD/Space.
 *
 * Pilot scheme:
 *  - Hold RMB + mouse → nose points with mouse (direct aim). Chase cam locked behind hull.
 *    W thrust flies straight along that nose — looking does NOT orbit the camera around the ship.
 *  - Hold Middle Mouse + mouse → head swivel only. LMB remains exclusively available for Fire.
 *  - Without RMB, mouse does not reorient the hull.
 *  - W / Space / Ctrl / A/D → thrust; Shift boost; Q/E barrel roll; O hangar door.
 */
UCLASS()
class REDMMO_API ARedShuttleBase : public APawn
{
	GENERATED_BODY()

public:
	ARedShuttleBase();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;
	virtual void PossessedBy(AController* NewController) override;
	virtual void PawnClientRestart() override;
	virtual void UnPossessed() override;
	virtual FVector GetVelocity() const override;
	virtual float TakeDamage(float DamageAmount, const FDamageEvent& DamageEvent,
		AController* EventInstigator, AActor* DamageCauser) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	/** Native occupant record used by replicated exit and destruction even if the vendor Driver field changes. */
	void RegisterOccupant(APawn* InOccupant);

	/** RMB-gated: free nose pitch/yaw in the local flight frame (not yaw-around-planet-up). */
	virtual void AddControllerYawInput(float Val) override;
	virtual void AddControllerPitchInput(float Val) override;

	/** If true, mouse steer requires holding Right Mouse Button. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle")
	bool bRequireRightMouseToSteer = true;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle")
	bool bAutoStartEnginesOnPossess = true;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle")
	bool bRadialFrame = true;

	/** Soft zero-roll leveling toward radial-up (QInterp speed). Keep low so it doesn't fight RMB aim. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle", meta = (ClampMin = "0.0"))
	float RadialAlignSpeed = 1.6f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle", meta = (ClampMin = "100.0"))
	float FlightSpeed = 2640.f;

	/** Hold-Shift boost multiplier — dramatic (bigger plumes + louder + faster). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle", meta = (ClampMin = "1.0"))
	float BoostMultiplier = 3.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle", meta = (ClampMin = "0.1"))
	float FlightAccel = 5.f;

	/** Deg/sec for Q/E barrel roll on the pack visual mesh (CLM_Shuttle). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle", meta = (ClampMin = "0.0"))
	float BarrelRollSpeed = 120.f;

	/** Extra scale on pack mouse → nose aim (on top of PC InputYaw/PitchScale). Lower = less whippy. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle", meta = (ClampMin = "0.05", ClampMax = "2.0"))
	float SteerSensitivity = 0.22f;

	/** How quickly the hull follows NoseAim while RMB steering (QInterp). Higher = more direct. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle", meta = (ClampMin = "0.5", ClampMax = "40.0"))
	float SteerInterpSpeed = 22.f;

	/** Middle-mouse look-around sensitivity (on top of PC InputYaw/PitchScale). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle", meta = (ClampMin = "0.05", ClampMax = "2.0"))
	float LookSensitivity = 0.35f;

	/** How fast middle-mouse look offsets return to chase when Middle Mouse is released. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle", meta = (ClampMin = "1.0", ClampMax = "30.0"))
	float LookReturnSpeed = 3.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle")
	float CameraPitchMin = -80.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle")
	float CameraPitchMax = 80.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle")
	float LookPitchMin = -70.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle")
	float LookPitchMax = 70.f;

	/** Hangar door open/close speed (alpha units per second). Pack Timeline_1 ≈ 1s. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle", meta = (ClampMin = "0.1"))
	float HangarDoorSpeed = 1.25f;

	/** Minimum radial clearance of ship center above traced terrain (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle", meta = (ClampMin = "50.0"))
	float MinSurfaceClearance = 450.f;

	/** Optional L-toggle. It only changes handling near traced PlanetGen terrain. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Replicated, Category = "Red|Shuttle|Landing")
	bool bLandingAssistEnabled = false;
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Replicated, Category = "Red|Shuttle|Landing")
	bool bLandingSettled = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle|Landing", meta = (ClampMin = "500.0"))
	float LandingAssistTraceDistance = 8000.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle|Landing", meta = (ClampMin = "100.0"))
	float LandingAssistMaxDescentSpeed = 700.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle|Landing", meta = (ClampMin = "0.1"))
	float LandingAssistAlignSpeed = 3.5f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle|Landing", meta = (ClampMin = "0.0"))
	float LandingAssistLateralDamping = 4.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle|Landing", meta = (ClampMin = "5.0"))
	float LandingAssistTouchdownDistance = 45.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle|Landing", meta = (ClampMin = "0.0"))
	float LandingAssistSurfaceGap = 20.f;

	/** Spring-arm collision probe radius (cm). Must be large enough to catch planet mesh. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle", meta = (ClampMin = "5.0"))
	float CameraProbeSize = 120.f;

	/** Extra radial margin so chase cam never sits under terrain (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle", meta = (ClampMin = "0.0"))
	float CameraSurfaceMargin = 200.f;

	/** C toggles from the native cockpit view to this chase distance. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle|Camera", meta = (ClampMin = "500.0"))
	float ChaseCameraArmLength = 5200.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle|Camera")
	FVector ChaseCameraSocketOffset = FVector(0.f, 0.f, 900.f);

	/** Native camera placed inside the forward-upper hull bounds; C swaps it with the chase view. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Shuttle|Camera")
	TObjectPtr<USceneComponent> CockpitCameraAnchor;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Shuttle|Camera")
	TObjectPtr<UCameraComponent> CockpitCamera;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle|Camera",
		meta = (ClampMin = "0.0", ClampMax = "0.85"))
	float CockpitForwardFraction = 0.72f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle|Camera",
		meta = (ClampMin = "0.0", ClampMax = "0.9"))
	float CockpitHeightFraction = 0.82f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle|Camera")
	FVector CockpitCameraFineTune = FVector(0.f, 0.f, 70.f);

	/** Native chase camera used when the migrated pack does not expose a usable camera component. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Shuttle|Camera")
	TObjectPtr<USpringArmComponent> NativeChaseCameraBoom;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Shuttle|Camera")
	TObjectPtr<UCameraComponent> NativeChaseCamera;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle|Flight", meta = (ClampMin = "1.0", ClampMax = "4.0"))
	float SpaceSpeedMultiplier = 2.4f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle|Flight", meta = (ClampMin = "1.0", ClampMax = "3.0"))
	float SpaceAccelerationMultiplier = 1.25f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle|Flight", meta = (ClampMin = "10000.0"))
	float SpaceTransitionAltitudeCm =
		RedPlanetPresentationTuning::SpaceTransitionAltitudeCm;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle|Camera",
		meta = (ClampMin = "60.0", ClampMax = "120.0"))
	float CockpitFieldOfView = 92.f;

	/** Above this height AGL, V exits into local EVA instead of a surface-oriented path. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle|Camera", meta = (ClampMin = "100000.0"))
	float OrbitalExitMinAltitude = 1000000.f;

	UFUNCTION(BlueprintCallable, Category = "Red|Shuttle")
	void EnsureEnginesOn();

	/** Force engines + nozzle FX/sound off (landed / after exit). */
	UFUNCTION(BlueprintCallable, Category = "Red|Shuttle")
	void EnsureEnginesOff();

	UFUNCTION(BlueprintCallable, Category = "Red|Shuttle")
	void ToggleHangarDoor();

	/** False during the brief possession handoff after a pilot exits. */
	UFUNCTION(BlueprintPure, Category = "Red|Shuttle")
	bool CanAcceptBoarding() const;

	/** PIE/MCP helper: set world-space flight velocity used by the radial driver. */
	UFUNCTION(BlueprintCallable, Category = "Red|Shuttle")
	void SetFlightVelocity(FVector WorldVelocity) { FlightVelocity = WorldVelocity; }

	UFUNCTION(BlueprintPure, Category = "Red|Shuttle")
	FVector GetFlightVelocity() const { return FlightVelocity; }

	/** Normalized replicated hull integrity for the player HUD. */
	UFUNCTION(BlueprintPure, Category = "Red|Shuttle|Combat")
	float GetHealthFraction() const;

	UFUNCTION(BlueprintPure, Category = "Red|Shuttle|Combat")
	float GetWeaponHeatFraction() const;

	UFUNCTION(BlueprintPure, Category = "Red|Shuttle|Combat")
	bool IsWeaponOverheated() const { return bWeaponOverheated; }

	UFUNCTION(BlueprintPure, Category = "Red|Shuttle|Landing")
	bool IsLandingAssistEnabled() const { return bLandingAssistEnabled; }

	UFUNCTION(BlueprintPure, Category = "Red|Shuttle|Landing")
	bool IsLandingSettled() const { return bLandingSettled; }

	/** Fire one server-authoritative test shot (also usable by MCP/PIE automation). */
	UFUNCTION(BlueprintCallable, Category = "Red|Shuttle|Combat")
	void TestFire();

	UFUNCTION(BlueprintCallable, Category = "Red|Shuttle|Combat")
	void StartFireTest();

	UFUNCTION(BlueprintCallable, Category = "Red|Shuttle|Combat")
	void StopFireTest();

	/** Exact current-body surface query shared by landing, terrain/camera clamps, and automation. */
	bool QueryPlanetSurface(const FVector& From, FVector& OutHitPoint, FVector& OutHitNormal) const;

	/** Stable inherited scene root; pack Blueprint components attach beneath it on recompile. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Shuttle")
	TObjectPtr<USceneComponent> RedShuttleRoot;

	/** Conservative ship/world envelope; visible pack meshes handle weapon queries. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Shuttle|Collision")
	TObjectPtr<UBoxComponent> RuntimeHullCollision;

	/** Pawn-only roof surface; keeps character floor tests stable on the parked shuttle. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Shuttle|Collision")
	TObjectPtr<UBoxComponent> RuntimeDeckCollision;

	/** Port and starboard hull lobes follow the purchased mesh silhouette without one huge AABB. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Shuttle|Collision")
	TObjectPtr<UBoxComponent> RuntimePortHullCollision;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Shuttle|Collision")
	TObjectPtr<UBoxComponent> RuntimeStarboardHullCollision;

	/** Walkable tops for the two outer hull lobes; kept separate to leave the silhouette gaps empty. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Shuttle|Collision")
	TObjectPtr<UBoxComponent> RuntimePortDeckCollision;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Shuttle|Collision")
	TObjectPtr<UBoxComponent> RuntimeStarboardDeckCollision;

	/** Thin pawn-only floor fitted to the rear loading ramp. It intentionally does not
	 *  block weapons or visibility, avoiding the former invisible-wall hull problem. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Shuttle|Collision")
	TObjectPtr<UBoxComponent> RuntimeLoadingRampCollision;

	/** Root-local center/half-size/rotation for the purchased shuttle's deployed rear ramp. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle|Collision|Loading Ramp")
	FVector LoadingRampCollisionLocation = FVector(-2860.f, 0.f, 245.f);
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle|Collision|Loading Ramp")
	FVector LoadingRampCollisionExtent = FVector(900.f, 690.f, 18.f);
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Red|Shuttle|Collision|Loading Ramp")
	FRotator LoadingRampCollisionRotation = FRotator(13.f, 0.f, 0.f);

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Replicated, Category = "Red|Shuttle|Combat", meta = (ClampMin = "1.0"))
	float MaxHealth = 2200.f;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, ReplicatedUsing = OnRep_Health, Category = "Red|Shuttle|Combat")
	float Health = 2200.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Red|Shuttle|Combat")
	TSubclassOf<AActor> ProjectileClass;

	/** Explicit inherited hardpoints. Child Blueprints can position these at the exact barrel tips. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Shuttle|Combat")
	TObjectPtr<USceneComponent> WeaponMuzzleLeft;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Shuttle|Combat")
	TObjectPtr<USceneComponent> WeaponMuzzleRight;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Red|Shuttle|Combat")
	TObjectPtr<UNiagaraSystem> WeaponMuzzleFlashFX;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Red|Shuttle|Combat")
	TObjectPtr<USoundBase> WeaponFireSound;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Red|Shuttle|Combat")
	TObjectPtr<USoundAttenuation> WeaponFireAttenuation;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Red|Shuttle|Combat", meta = (ClampMin = "0.03"))
	float FireInterval = 0.18f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Red|Shuttle|Combat", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float MinFireAimDot = 0.55f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Red|Shuttle|Combat", meta = (ClampMin = "1.0"))
	float MaxWeaponHeat = 100.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Red|Shuttle|Combat", meta = (ClampMin = "0.0"))
	float HeatPerShot = 16.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Red|Shuttle|Combat", meta = (ClampMin = "0.0"))
	float HeatCooldownPerSecond = 24.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Red|Shuttle|Combat", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float OverheatRecoveryFraction = 0.35f;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Replicated, Category = "Red|Shuttle|Combat")
	float WeaponHeat = 0.f;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Replicated, Category = "Red|Shuttle|Combat")
	bool bWeaponOverheated = false;

protected:
	void AlignToRadialFrame(float DeltaSeconds);
	void ApplyHeldFlightInput(class APlayerController* PC, float DeltaSeconds);
	void ApplyBarrelRollInput(class APlayerController* PC, float DeltaSeconds);
	void ApplyHangarDoorInput(class APlayerController* PC, float DeltaSeconds);
	void UpdateHangarDoor(float DeltaSeconds);
	void UpdateEngineNozzles();
	void UpdateBoostFX(bool bBoost);
	void ConfigureChaseCamera();
	void ConfigureCockpitCamera();
	void ApplyFlightCameraMode();
	void ToggleFlightCamera();
	void ToggleLandingAssist();
	void SetLandingAssistEnabled(bool bEnabled);
	UFUNCTION(Server, Reliable)
	void ServerSetLandingAssistEnabled(bool bEnabled);
	void ApplyLandingAssist(float DeltaSeconds);
	float GetLandingSupportDistance(const FVector& SurfaceNormal) const;
	void SetLandingSettled(bool bSettled);
	void UpdateLookCamera(float DeltaSeconds);
	bool ConfigureRuntimeCollisionHulls();
	void EnsureProjectileCollision();
	/** Keep hull center above planet surface (line-trace toward center + radial push). */
	void ClampAboveTerrain();
	/** Keep chase camera above planet surface (spring-arm collide + radial clamp). */
	void ClampCameraAboveTerrain();
	bool GetPlanetFrame(FVector& OutCenter, FVector& OutRadialUp) const;
	bool ApplySteerDelta(float YawDeg, float PitchDeg);
	bool ApplyLookAroundDelta(float YawDeg, float PitchDeg);
	void ApplyNoseAim(const FVector& Aim, const FVector& RadialUp, bool bHardSnap);
	void GatherLocalFlightInput(class APlayerController* PC);
	void UpdateAuthoritativeRemoteAim(float DeltaSeconds);
	UFUNCTION(Server, Unreliable)
	void ServerSetFlightInput(FVector MoveAxes, float RollAxis, bool bBoost,
		FVector_NetQuantizeNormal DesiredNoseAim, bool bSteering);
	static bool SetBoolProperty(UObject* Obj, FName Name, bool bValue);
	static bool GetBoolProperty(UObject* Obj, FName Name, bool& OutValue);
	USceneComponent* FindPackVisualMesh() const;
	USceneComponent* FindDoorHinge() const;
	void StartFire();
	void StopFire();
	/** Leave the shuttle with the same replicated EnterVehicle action used to board it. */
	void ExitShuttle();
	UFUNCTION(Server, Reliable)
	void ServerExitShuttle();
	void Fire();
	UFUNCTION(Server, Reliable)
	void ServerFire();
	UFUNCTION(NetMulticast, Unreliable)
	void MulticastFireCosmetics(FVector_NetQuantize MuzzleLocation, FVector_NetQuantizeNormal ShotDirection);
	bool TryFireAuthoritative();
	bool ComputeServerFireTransform(bool bUseLeftMuzzle, FVector& OutStart, FRotator& OutDirection) const;
	void UpdateWeaponHeat(float DeltaSeconds);
	void HandleDeath(AController* DamageInstigator = nullptr, AActor* DamageCauser = nullptr);
	UFUNCTION()
	void OnRep_Health();
	APawn* FindPackDriverPawn() const;
	bool IsOrbitalExit() const;
	void EjectOccupantBeforeDeath();

	bool bPendingEngineStart = false;
	bool bRuntimeCollisionHullsConfigured = false;
	bool bEnginesForcedOff = false;
	bool bLocalExitInputArmed = false;
	bool bExitRequestSent = false;
	bool bBoostFXOn = false;
	bool bThirdPersonCamera = false;
	bool bCockpitCameraPositioned = false;
	bool bFiring = false;
	bool bMuzzleLeft = true;
	bool bDeathHandled = false;
	float FireCooldown = 0.f;
	double NextServerFireTime = 0.0;
	double LocalExitInputReadyTime = 0.0;
	FVector CurrentMoveAxes = FVector::ZeroVector;
	float CurrentRollAxis = 0.f;
	bool bCurrentBoostHeld = false;
	FVector ServerMoveAxes = FVector::ZeroVector;
	float ServerRollAxis = 0.f;
	bool bServerBoostHeld = false;
	bool bServerSteering = false;
	FVector ServerDesiredNoseAim = FVector::ForwardVector;
	double LastServerFlightInputTime = -100.0;
	double NextBoardAllowedTime = 0.0;
	UPROPERTY(Replicated)
	TObjectPtr<APawn> Occupant = nullptr;
	FVector FlightVelocity = FVector::ZeroVector;

	/** Current nose aim (unit). Source of truth for thrust; middle-mouse look does not change this. */
	FVector NoseAim = FVector::ForwardVector;
	bool bNoseAimValid = false;

	/** Middle-mouse head-swivel offsets on the chase spring arm (degrees, hull-local). */
	float LookYawOffset = 0.f;
	float LookPitchOffset = 0.f;

	/** Hangar rear door: 0 = closed, 1 = open (DoorHinge pitch 0 → -90). */
	bool bHangarDoorOpen = false;
	float HangarDoorAlpha = 0.f;
	bool bHangarDoorOWasDown = false;
};
