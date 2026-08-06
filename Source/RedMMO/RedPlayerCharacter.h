#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "RedResourcePickup.h"
#include "RedPlayerCharacter.generated.h"

class USpringArmComponent;
class UCameraComponent;
class URadialGravityComponent;
class USkeletalMeshComponent;
class UVibeMMOHUDWidget;
class USceneCaptureComponent2D;
class UTextureRenderTarget2D;
class UTexture2D;
class UFootstepTrailComponent;
class URedShorelineWaveComponent;
class UAnimSequence;
class ARedCloningStation;
class ARedOctosphereManager;
class UPointLightComponent;
class UNiagaraComponent;
class UNiagaraSystem;
class USplineMeshComponent;
class UMaterialInterface;
class UCameraShakeBase;
class UDamageType;
class UParticleSystemComponent;
class UAudioComponent;

/** The deliberately small launch loadout: exactly two abilities, assignable between Q and E. */
UENUM(BlueprintType)
enum class ERedPlayerAbility : uint8
{
	Grapple UMETA(DisplayName = "Grapple"),
	Slam UMETA(DisplayName = "Slam")
};

/**
 * Clean, self-contained third-person character for the persistent voxel planet.
 * Replaces the DMD match-shooter pawn (whose input/combat only ran inside a match).
 * Movement + camera + sphere gravity work standalone; weapon is layered on top.
 */
UCLASS()
class REDMMO_API ARedPlayerCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	ARedPlayerCharacter(const FObjectInitializer& ObjectInitializer);
	void SnapToPlanetSurfaceNow();
	void SetHUDSpaceMinimap(bool bSpace);
	/** Re-publishes the local surface capture after HUD/pawn BeginPlay order races. */
	void RefreshReplacementHUDMinimapPresentation();
	/** Forward the local camera trace's lock strength to the pack-authored HUD sight. */
	void SetHUDReticleTargetAlpha(float TargetAlpha);

	/** Local-only UI bridge used by the persistent Escape menu. */
	void PrepareForPauseMenu();
	bool CanOpenAbilityLoadout() const;
	void OpenAbilityLoadoutFromMenu();
	FText GetAbilityDisplayNameForSlot(int32 Slot) const;
	/** Local gameplay HUD access for the native settings/customization presenter. */
	UVibeMMOHUDWidget* GetActiveHUDWidget() const { return ActiveHUDWidget; }
	/** Whether the possessed controller exposes the installed PO-Art creator command. */
	bool CanOpenCharacterCreator() const;

	/** Opens the installed PO-Art creator from a real menu command. Returns false instead of silently falling back. */
	bool OpenCharacterCreatorFromMenu();

	/** Boarding a ship: freeze movement + gravity and ride along ATTACHED to the ship, so the pilot's
	 *  voxel collision invoker streams terrain around the ship all flight (far side is cooked before we
	 *  ever exit) and there is never a giant one-frame teleport at exit. */
	void OnBoardedShip(AActor* Ship);
	/** Exiting a ship: detach and place the pilot at ExitLocation, surface-aligned.
	 *  If bSnapToPlanetSurface: ground-trace toward the core (legacy RedShip beside-hull exit).
	 *  If false: keep ExitLocation as given (shuttle roof / hull-top exit — no under-terrain snap). */
	void OnExitedShip(const FVector& ExitLocation, const FVector& SuggestedForward, AActor* IgnoreForTrace,
		bool bSnapToPlanetSurface = true);

	/** While piloting: render the pilot ONLY in scene captures — the HUD portrait keeps showing the
	 *  face instead of whatever the capture points at, while the main view shows no pawn. */
	void SetPilotCaptureOnly(bool bCaptureOnly);

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void PawnClientRestart() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void PossessedBy(AController* NewController) override;
	/** Never base the pawn on a voxel component — they're recreated as the world updates and would teleport us. */
	virtual void SetBase(struct FMovementBaseInterfaceData* MovementBaseInterfaceData, FName BoneName = NAME_None, bool bNotifyActor = true) override;
	virtual void SetupPlayerInputComponent(UInputComponent* InInput) override;

	UPROPERTY(VisibleAnywhere, Category = "Red")
	USpringArmComponent* SpringArm;

	UPROPERTY(VisibleAnywhere, Category = "Red")
	UCameraComponent* Camera;

	UPROPERTY(VisibleAnywhere, Category = "Red")
	URadialGravityComponent* RadialGravity;

	/** Leaves soft sand scuffs/footprints on walkable planet terrain. */
	UPROPERTY(VisibleAnywhere, Category = "Red|Surface")
	UFootstepTrailComponent* FootstepTrail;

	/** Local spherical shoreline crests built from PlanetGen's real sea-level contour. */
	// Runtime-only on purpose: another reflected/default subobject changes the unversioned
	// native property schema used by the existing cooked character-creator Blueprints.
	URedShorelineWaveComponent* ShorelineWaves = nullptr;

	/** Local-only Sand VFX wind layer that follows the owning player's camera. */
	UPROPERTY(VisibleAnywhere, Category = "Red|Surface")
	TObjectPtr<UNiagaraComponent> AmbientSandFX;

	/** The held weapon (the DMD rifle mesh is assigned in the constructor / Blueprint). */
	UPROPERTY(VisibleAnywhere, Category = "Red")
	USkeletalMeshComponent* WeaponMesh;

	/** Renders the player's face/upper-body into a texture for the HUD portrait. */
	UPROPERTY(VisibleAnywhere, Category = "Red|UI")
	USceneCaptureComponent2D* PortraitCapture;

	/** Renders a top-down view of the area around the player for the HUD minimap. */
	UPROPERTY(VisibleAnywhere, Category = "Red|UI")
	USceneCaptureComponent2D* MinimapCapture;

	UPROPERTY(Transient)
	UTextureRenderTarget2D* PortraitRT;

	UPROPERTY(Transient)
	UTextureRenderTarget2D* MinimapRT;

	/** Mac gameplay HUD, created only for the locally controlled pawn. */
	UPROPERTY(Transient)
	TObjectPtr<UVibeMMOHUDWidget> ActiveHUDWidget;

	/** Authored card art kept as hard references so the HUD cannot regress to text-only slots. */
	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> EpicWeaponCardTexture;
	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> LegendaryWeaponCardTexture;

	/** Explicit mode requested by vehicle boarding. This remains true while the character is
	 *  unpossessed, so its still-owned HUD cannot be forced back to Surface by Tick. */
	bool bHUDSpaceMinimapRequested = false;
	FName LastReplacementMinimapCaptureFrameId = NAME_None;
	bool bReplacementMinimapSurfaceCaptureFresh = false;
	/** Last non-degenerate planet-tangent heading; holds the compass stable during nose-radial flight. */
	float LastStableCompassHeadingDegrees = 0.f;
	bool bHasStableCompassHeading = false;
	/** Stable gravity body that owns LastStableCompassHeadingDegrees. */
	FName LastStableCompassGravityBodyId = NAME_None;

	// --- tunables ---
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	TSubclassOf<AActor> ProjectileClass;

	/** Projectile enemy clones fire — a different color than the player's (set in the ctor). */
	UPROPERTY(EditAnywhere, Category = "Red|Fight")
	TSubclassOf<AActor> EnemyProjectileClass;

	/** Upper-body firing animation played on the character mesh when LMB fires.
	 *  NOTE: ABP_Basic_Locomotion has no Slot node, so this montage ticks but the pose is
	 *  discarded. Visible character shoot anim needs a Slot in the ABP (manual editor step).
	 */
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	class UAnimMontage* FireMontage;

	/** Weapon-mesh fire montage (bolt cycle / charging handle). Plays on the rifle's own
	 *  AnimInstance so the GUN visibly fires even though the character's body anim is gated. */
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	class UAnimMontage* WeaponFireMontage;

	/** Rifle Pro fire clip played through the project AnimBP's DefaultSlot. The slot is inside
	 *  the spine_03 overlay, so recoil affects the upper body without stopping running legs. */
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	class UAnimSequence* RifleFireAnim;

	/** Big muzzle flash Niagara system spawned at the rifle's Barrel socket every shot. */
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	class UNiagaraSystem* MuzzleFlashFX;

	/** Electric muzzle paired with ProjectilesVol1 profile 17 (slot 1 / ENERGY). */
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	class UNiagaraSystem* EnergyMuzzleFlashFX;

	/** Gunshot sound played at the muzzle on every shot (player + enemy), spatialized so distance matters. */
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	class USoundBase* WeaponFireSound;

	/** Distance falloff (DMD ATT_Shot) so far-off shots — including enemy fire — get quieter. */
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	class USoundAttenuation* WeaponSoundAttenuation;

	/** Skeletal meshes available in weapon slots (0 = primary, 1 = secondary). */
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	TArray<class USkeletalMesh*> WeaponSlotMeshes;

	/** Directional death falls played on down (random pick) — replaces the deformed ragdoll. */
	UPROPERTY(EditAnywhere, Category = "Red|Fight")
	TArray<class UAnimSequence*> DeathAnims;

	/** Rifle tracer tint — pixel-measured off P_Flash_4's rendered glow (hue ~354, hot rose-red). */
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	FLinearColor RifleBoltColor = FLinearColor(6.0f, 1.6f, 2.0f);

	/** Slot 1 is a broad cyan electric orb rather than a recolor of the rifle streak. */
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	FLinearColor EnergyBoltColor = FLinearColor(0.2f, 4.5f, 9.0f);

	/** Rifle tracer size in meters (length along flight / thickness). The profile formula's
	 *  clamp floor made rifle bolts a 3.5cm thread — these override it. */
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	float RifleBoltLength = 1.1f;
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	float RifleBoltRadius = 0.15f;
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	float EnergyBoltLength = 0.55f;
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	float EnergyBoltRadius = 0.30f;
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	float EnergyMuzzleSpeed = 7200.f;
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	float RifleMuzzleSpeed = 9800.f;

	/** Console exec: retint the rifle tracer live (`BoltColor 6 1.6 2`) — affects the next shots. */
	UFUNCTION(Exec)
	void BoltColor(float R, float G, float B);

	/** Console exec: resize the rifle tracer live (`BoltSize 1.1 0.15` = 1.1m long, 15cm thick). */
	UFUNCTION(Exec)
	void BoltSize(float LengthMeters, float ThicknessMeters);

	/** Server-owned equipped slot. The owning client predicts the visual swap; OnRep reconciles it. */
	UPROPERTY(ReplicatedUsing = OnRep_CurrentWeaponSlot, VisibleAnywhere, Category = "Red|Weapon")
	int32 CurrentWeaponSlot = 0;

	// --- Health / Shield ---
	UPROPERTY(EditAnywhere, Category = "Red|Health")
	float MaxHealth = 100.f;
	UPROPERTY(EditAnywhere, Category = "Red|Health")
	float MaxShield = 100.f;
	/** Armor is a replicated mitigation pool worn by the covered tall-female trooper ragdoll. */
	UPROPERTY(EditAnywhere, Category = "Red|Health", meta = (ClampMin = "0.0"))
	float MaxArmor = 100.f;
	/** Fraction of post-shield damage diverted into the armor pool while armor remains. */
	UPROPERTY(EditAnywhere, Category = "Red|Health", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float ArmorDamageMitigation = 0.35f;

	UPROPERTY(ReplicatedUsing = OnRep_HealthState, VisibleAnywhere, Category = "Red|Health")
	float Health = 100.f;
	UPROPERTY(ReplicatedUsing = OnRep_HealthState, VisibleAnywhere, Category = "Red|Health")
	float Shield = 100.f;
	UPROPERTY(ReplicatedUsing = OnRep_HealthState, VisibleAnywhere, BlueprintReadOnly, Category = "Red|Health")
	float Armor = 100.f;

	/** Jetpack thrust + sprint stamina (yellow HUD bar). */
	UPROPERTY(EditAnywhere, Category = "Red|Jetpack")
	float MaxFuel = 100.f;
	UPROPERTY(Replicated, VisibleAnywhere, Category = "Red|Jetpack")
	float Fuel = 100.f;
	UPROPERTY(EditAnywhere, Category = "Red|Jetpack")
	float FuelDrainPerSecond = 18.f;
	UPROPERTY(EditAnywhere, Category = "Red|Jetpack")
	float FuelRegenPerSecond = 22.f;
	UPROPERTY(EditAnywhere, Category = "Red|Jetpack")
	float SprintFuelDrainPerSecond = 12.f;

public:
	virtual float TakeDamage(float DamageAmount, FDamageEvent const& DamageEvent,
		AController* EventInstigator, AActor* DamageCauser) override;

	/** Server-only fatal damage used when an occupied vehicle is destroyed. This deliberately
	 *  bypasses the short landing shield, then enters the normal replicated downed/ragdoll/respawn flow. */
	void ApplyVehicleDestructionDeath(AController* EventInstigator, AActor* DamageCauser);

	float GetHealthFraction() const { return MaxHealth > 0.f ? Health / MaxHealth : 0.f; }
	float GetShieldFraction() const { return MaxShield > 0.f ? Shield / MaxShield : 0.f; }
	UFUNCTION(BlueprintPure, Category = "Red|Health")
	float GetArmorFraction() const { return MaxArmor > 0.f ? Armor / MaxArmor : 0.f; }
	float GetFuelFraction() const { return MaxFuel > 0.f ? Fuel / MaxFuel : 0.f; }
	bool IsDowned() const { return bDowned; }
	bool IsSkydiving() const { return bSkydiving; }

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	// --- Mined-resource inventory totals (persistent presentation belongs in inventory) ---
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, ReplicatedUsing = OnRep_Resources,
		Category = "Red|Resources")
	int32 ResStone = 0;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, ReplicatedUsing = OnRep_Resources,
		Category = "Red|Resources")
	int32 ResIron = 0;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, ReplicatedUsing = OnRep_Resources,
		Category = "Red|Resources")
	int32 ResCrystal = 0;

	/** Add a mined resource to inventory and notify only the credited local player. */
	UFUNCTION(BlueprintCallable, Category = "Red|Resources")
	void AddResource(ERedResourceType Type, int32 InAmount);

	// --- AI fight (enemy clones) ---
	/** Set on AI-spawned clones so they despawn on death and never run player-only logic. */
	UPROPERTY(Replicated, VisibleAnywhere, Category = "Red|Fight")
	bool bIsEnemy = false;
	/** Keep the focused environment build quiet by default; enable to spawn the opening patrol. */
	UPROPERTY(EditAnywhere, Category = "Red|Fight")
	bool bAutoSpawnEnemyWave = false;
	/** Damage the player's bolt deals to a pawn under the crosshair (per shot). ~10 for longer fights. */
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	float WeaponDamage = 10.f;
	/** Damage an enemy clone deals to the player per landed shot (~1 shield pip). */
	UPROPERTY(EditAnywhere, Category = "Red|Fight")
	float EnemyFireDamage = 10.f;
	/** Chance [0..1] an enemy shot is a crit (20–30 damage). */
	UPROPERTY(EditAnywhere, Category = "Red|Fight")
	float EnemyCritChance = 0.18f;
	/** Chance [0..1] an enemy shot actually lands (keeps the fight survivable). */
	UPROPERTY(EditAnywhere, Category = "Red|Fight")
	float EnemyHitChance = 0.55f;
	/** Random aim scatter (cm) for enemy fire. */
	UPROPERTY(EditAnywhere, Category = "Red|Fight")
	float EnemyAimSpread = 120.f;
	/** AI enemies fire toward a target via this (vs the player's camera-aimed Fire()). */
	void FireAtTarget(AActor* Target);
	/** Spawn Count enemy clones on a ring (default 300m), each possessed by an ARedBotController. */
	void SpawnEnemyWave(int32 Count, float RingRadius = 0.f);
	/** Console command: type "RedSpawnEnemies 3" (or any count). */
	UFUNCTION(Exec)
	void RedSpawnEnemies(int32 Count = 3);

	/** STRESS TEST (console: "StressBots 50 200000"): spawn N wandering bots spread over SpreadRadius,
	 *  each a WP streaming source (realistic MMO: N players = N loaded regions). Watch `stat unit`. */
	UFUNCTION(Exec)
	void StressBots(int32 N = 20, float SpreadRadius = 200000.f);

private:
	/** Safe to call from BeginPlay and possession callbacks; creates at most one local HUD. */
	void TryCreateLocalHUD();
	void DestroyLocalHUD();
	void PublishReplacementHUDMinimap(bool bSpaceMode);
	FName ResolveReplacementHUDMinimapFrameId() const;
	void OnSpawnEnemiesKey();
	/** BeginPlay-timer callback: the real player spawns the opening 120m patrol (task: red blips). */
	void OnAutoSpawnWave();
	void UpdateHUDStatus();
	void UpdateHUDResources();
	UFUNCTION()
	void OnRep_Resources();
	void PresentResourceCreditLocal(ERedResourceType Type, int32 Amount);
	UFUNCTION(Client, Reliable)
	void ClientPresentResourceCredit(ERedResourceType Type, int32 Amount);
	void OnDowned();
	void Respawn();
	UPROPERTY(ReplicatedUsing = OnRep_Downed)
	bool bDowned = false;
	FTimerHandle RespawnTimer;

	UFUNCTION()
	void OnRep_HealthState();
	UFUNCTION()
	void OnRep_Downed();
	void ApplyDownedPresentation();
	void RestoreFromDownedPresentation();

	/** Vibe MMO UI Kit HUD Blueprint that supplies the WidgetTree built by the native widget. */
	UPROPERTY(EditAnywhere, Category = "Red|UI")
	TSubclassOf<UVibeMMOHUDWidget> HUDWidgetClass;

	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	FName WeaponSocket = TEXT("Weapon_TPS");

	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	FName MuzzleSocket = TEXT("Muzzle");

	/** Slide the rifle along its barrel (cm). Live: `WeaponGrip 4`. Base fallback offset (8,3,-2). */
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	float WeaponGripSlide = 4.0f;

	/** Pull the rifle toward/away from the chest (cm; positive = closer to torso). Live: `WeaponInward 6.7`. */
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	float WeaponInwardSlide = 6.7f;

	/** Raise/lower the rifle relative to the hand (cm; negative = down to close the hand-grip gap). Live: `WeaponRaise -4`. */
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	float WeaponRaiseSlide = -8.0f;

	/** Tip the barrel head up/down (deg; positive = muzzle DOWN). Live: `WeaponPitch 5`. */
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	float WeaponPitchDeg = 5.0f;

	/** Roll the weapon around its barrel (deg; rotates the "top" like a clock). -90 = right-side up,
	 *  angled toward the chest, hand clearing the stock (user-confirmed). Live: `WeaponRoll -90`. */
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	float WeaponRollDeg = -90.0f;

	/** Console execs: seat the rifle in the hand live (slide / raise-lower / tip / roll). */
	UFUNCTION(Exec)
	void WeaponGrip(float ForwardCm);
	UFUNCTION(Exec)
	void WeaponRaise(float UpCm);
	UFUNCTION(Exec)
	void WeaponPitch(float DownDeg);
	UFUNCTION(Exec)
	void WeaponRoll(float Deg);
	UFUNCTION(Exec)
	void WeaponInward(float TowardChestCm);
	/** Live-tune the extra rifle offset applied ONLY while aiming/firing (hand-socket frame, cm):
	 *  the ADS pose's support hand sits further forward than this rifle's length, so nudge the
	 *  rifle forward to meet it. Type e.g. `WeaponAimNudge 8 0 0` in the console. */
	UFUNCTION(Exec)
	void WeaponAimNudge(float X, float Y, float Z);

	/** Re-applies base offset + all three grip tunables to the weapon mesh transform. */
	void ApplyWeaponGripOffset();

public:
	// --- Milestone 1: The Drop (orbital skydive) ---
	/** Fortnite-style dive: gentler gravity + full air steering + a terminal speed, so you fall
	 *  from orbit and steer to your landing while the ground streams in below you. */
	UPROPERTY(EditAnywhere, Category = "Red|Skydive")
	float SkydiveGravityScale = 0.35f;
	UPROPERTY(EditAnywhere, Category = "Red|Skydive")
	float SkydiveAirControl = 1.0f;
	UPROPERTY(EditAnywhere, Category = "Red|Skydive")
	float SkydiveMaxFallSpeed = 3500.f;   // cm/s terminal velocity while diving
	// Replicated so remote clients light up the red plume on a falling pawn (see OnRep_Skydiving).
	UPROPERTY(ReplicatedUsing = OnRep_Skydiving, BlueprintReadOnly, Category = "Red|Skydive")
	bool bSkydiving = false;

	UFUNCTION()
	void OnRep_Skydiving();

	/** Full-body freefall pose played while diving (Mixamo, retargeted to SKEL_UE4_Tall_Female_TRPR). */
	UPROPERTY(EditAnywhere, Category = "Red|Skydive")
	UAnimSequence* SkydiveFreefallAnim = nullptr;

	/** One-shot touchdown clip played on landing before locomotion resumes (Mixamo, retargeted). */
	UPROPERTY(EditAnywhere, Category = "Red|Skydive")
	UAnimSequence* SkydiveLandAnim = nullptr;

	/** Backward movement speed as a fraction of forward (you don't sprint backwards). */
	UPROPERTY(EditAnywhere, Category = "Red|Movement")
	float BackpedalSpeedScale = 0.5f;

	UFUNCTION(BlueprintCallable, Category = "Red|Skydive")
	void StartSkydive();
	UFUNCTION(BlueprintCallable, Category = "Red|Skydive")
	void StopSkydive();
	/** Timer callback: land clip finished → resume the AnimBlueprint. */
	void FinishSkydiveLand();

	/** The Drop: teleport onto the cloning-station deck; if bArmDive, start the freefall immediately.
	 *  Returns false if there is no station (caller falls back to the PlayerStart flow). */
	UFUNCTION(BlueprintCallable, Category = "Red|Skydive")
	bool BoardStationAndDrop(bool bArmDive);

	/** Octosphere drop: arm the dive in place (pawn already spawned high in the air) and set the
	 *  re-entry terminal velocity for this drop. Tick starts the freefall the moment it enters
	 *  MOVE_Falling. InFallSpeed <= 0 keeps the default SkydiveMaxFallSpeed. */
	UFUNCTION(BlueprintCallable, Category = "Red|Skydive")
	void BeginOrbitalDrop(float InFallSpeed = -1.f);

	/** Held-jump jetpack thrust during the orbital drop: slows / hovers / reverses the descent. */
	void StartJetpack();
	void StopJetpack();

	/** Debug/inspect (F9): first press opens a stable, unobstructed full-globe view;
	 *  second press starts the playable re-entry from that same position. */
	void RestartOrbitalDrop();
	/** Local-only F9 inspection state. It deliberately does not replicate or alter gameplay. */
	bool bOrbitInspectionActive = false;
	/** Development acceptance helper: toggle the existing two-hour cycle between
	 * production speed and a 30-second rendered day/night verification cycle. */
	void ToggleFastDayNightTest();
	/** Development-only acceptance helper: move to a verified fused-terrain shoreline
	 * so the spherical water and shore waves can be judged outside the submerged spawn. */
	void TeleportToShorelineVisualTest();

	/** Octosphere orbital drop active — robust controlled descent, independent of the bSkydiving toggle. */
	UPROPERTY(ReplicatedUsing = OnRep_JetpackState, BlueprintReadOnly, Category = "Red|Skydive")
	bool bOrbitalDropActive = false;
	/** Controlled constant descent speed during the orbital drop (cm/s). ~25s over an 8km drop at 32000. */
	UPROPERTY(EditAnywhere, Category = "Red|Skydive")
	float OrbitalDropFallSpeed = 32000.f;
	/** Fortnite-style dive: descent speed when leveled out / spread (cm/s) — the slow glide. */
	UPROPERTY(EditAnywhere, Category = "Red|Skydive")
	float OrbitalDropSlowFallSpeed = 8000.f;
	/** Fortnite-style dive: descent speed when the camera is pitched straight DOWN (cm/s) — the plunge. */
	UPROPERTY(EditAnywhere, Category = "Red|Skydive")
	float OrbitalDropDiveFallSpeed = 18000.f;
	/** Upward speed the jetpack subtracts from the descent while held (cm/s). Just above the descent
	 *  speed so holding Space brakes a 320m/s fall into a gentle ~20m/s rise = near-hover to study the
	 *  planet; release to resume the dive. (> descent = climb; press B to jump fully back to orbit.) */
	UPROPERTY(EditAnywhere, Category = "Red|Skydive")
	float JetpackThrustSpeed = 34000.f;
	UPROPERTY(ReplicatedUsing = OnRep_JetpackState)
	bool bJetpackThrusting = false;

	/** General JETPACK — double-tap Space to engage, then hold Space to thrust upward. Separate from
	 *  the orbital-drop thruster above. Infinite for now (no fuel); add a fuel meter later to balance. */
	UPROPERTY(EditAnywhere, Category = "Red|Jetpack")
	float JetpackAccel = 2600.f;            // cm/s^2 upward while held (beats ~980 gravity → net rise)
	UPROPERTY(EditAnywhere, Category = "Red|Jetpack")
	float JetpackMaxUpSpeed = 950.f;        // cm/s cap on climb speed
	/** Shift while jetpacking: stronger climb (human sprint key doubles as air boost). */
	UPROPERTY(EditAnywhere, Category = "Red|Jetpack")
	float JetpackBoostAccelMult = 1.85f;
	UPROPERTY(EditAnywhere, Category = "Red|Jetpack")
	float JetpackBoostMaxUpMult = 1.55f;
	UPROPERTY(EditAnywhere, Category = "Red|Jetpack")
	float JetpackDoubleTapWindow = 0.30f;   // s — two Space taps within this window engage the pack
	UPROPERTY(ReplicatedUsing = OnRep_JetpackState)
	bool bJetpackOn = false;                // engaged (stays on until you land)
	UPROPERTY(Replicated)
	bool bSprintHeld = false;               // Shift held (ground sprint + air jetpack boost)
	UPROPERTY(Replicated)
	bool bJumpHeld = false;                 // Space currently held
	float LastJumpPressTime = -10.f;        // for double-tap detection
	UFUNCTION()
	void OnRep_JetpackState();
	/** Pack-intended attach: ChildActor of Sci-Fi_Jetpack_Master_BP on spine_03 (see
	 *  SciFI_Jetpack_ThirdPersonCharacter). Owns skeletal mesh + Exhaust_L/R plume FX. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Jetpack")
	TObjectPtr<class UChildActorComponent> JetpackActor;
	/** Legacy static-mesh / tank placeholders (kept so existing Blueprint defaults don't break; hidden). */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Jetpack")
	TObjectPtr<UStaticMeshComponent> JetpackMesh;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Jetpack")
	TObjectPtr<UStaticMeshComponent> JetpackTankL;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Jetpack")
	TObjectPtr<UStaticMeshComponent> JetpackTankR;
	UPROPERTY(EditAnywhere, Category = "Red|Jetpack")
	FName JetpackSocket = TEXT("spine_03");
	/** ChildActor seat on spine_03 — pack demo (SciFI_Jetpack_ThirdPersonCharacter) uses identity;
	 *  Master BP applies its own (0,5,0) nudge on the Jetpack SKC. */
	UPROPERTY(EditAnywhere, Category = "Red|Jetpack")
	FVector JetpackLocation = FVector(0.f, 0.f, 0.f);
	UPROPERTY(EditAnywhere, Category = "Red|Jetpack")
	FRotator JetpackRotation = FRotator(0.f, 0.f, 0.f);
	UPROPERTY(EditAnywhere, Category = "Red|Jetpack")
	FVector JetpackScale = FVector(1.f, 1.f, 1.f);
	/** Legacy Cascade exhaust — restored: Jet_Exhaust_PS seated on Exhaust_L/R, absolute MakeFromX(actor-down). */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Jetpack")
	TObjectPtr<UParticleSystemComponent> JetpackExhaust;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Jetpack")
	TObjectPtr<UParticleSystemComponent> JetpackExhaustL;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Jetpack")
	TObjectPtr<UParticleSystemComponent> JetpackExhaustR;
	UPROPERTY() TObjectPtr<UParticleSystem> JetpackExhaustFX;
	/** Hidden cyan cone stand-ins (pose reference only — Cascade is the visible plume). */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Jetpack")
	TObjectPtr<UStaticMeshComponent> JetpackPlumeCone;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Jetpack")
	TObjectPtr<UStaticMeshComponent> JetpackPlumeConeL;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Jetpack")
	TObjectPtr<UStaticMeshComponent> JetpackPlumeConeR;
	UPROPERTY() TObjectPtr<UMaterialInterface> JetpackPlumeMaterial;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Jetpack")
	TObjectPtr<UAudioComponent> JetpackThrustAudio;
	UPROPERTY() TObjectPtr<USoundBase> JetpackThrustSound;
	bool bThrustFXWanted = false;           // set each Tick when jetpack is thrusting (drives the plume)
	bool bJetPlumeOn = false;               // current plume state — only toggle FX on a change
	bool bJetpackFlyAnimOn = false;         // hover/thrust pose while jetpacking
	UPROPERTY() TObjectPtr<UAnimSequence> JetpackHoverAnim = nullptr;
	/** Show/hide the pack ChildActor (and legacy mesh) — hidden on alien body. */
	UFUNCTION(BlueprintCallable, Category = "Red|Jetpack")
	void SetJetpackVisible(bool bVisible);
	/** Activate/deactivate nozzle plumes (Cascade Jet_Exhaust_PS on Exhaust_L/R + mid) while thrusting. */
	UFUNCTION(BlueprintCallable, Category = "Red|Jetpack")
	void SetJetpackThrustFX(bool bOn);
	/** Re-seat Cascade plumes onto pack Exhaust_L/R (+ midpoint); hide cyan cones; suppress pack-BP hip FX. */
	void EnsureJetpackExhaustAttached();
	/** Temporary hover/thrust pose while jetpacking (NOT skydive). Restores AnimBP on land. */
	void UpdateJetpackFlightAnim(bool bCombatAim);
	bool bJetpackExhaustAttached = false;

	// --- HOVERBOARD (B): a board you ride — fast, low-friction, accelerates DOWNHILL (surf/snowboard
	//     feel) so you slide off cliffs at speed, then chain jetpack (dbl-Space) → grapple (RMB) → SLAM (Ctrl). ---
	void ToggleHoverboard();
	void StartSlam();
	/** Master switch for the hoverboard (mesh + underglow + toggle + auto-glide board). OFF for now — it
	 *  cluttered the view during the drop and reads as a placeholder cube. Flip true to bring it back. */
	UPROPERTY(EditAnywhere, Category = "Red|Hoverboard")
	bool bHoverboardEnabled = false;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Hoverboard")
	TObjectPtr<UStaticMeshComponent> HoverboardMesh;
	UPROPERTY(EditAnywhere, Category = "Red|Hoverboard")
	float HoverboardMaxSpeed = 3200.f;      // cm/s cruise cap (downhill pushes you toward it fast)
	UPROPERTY(EditAnywhere, Category = "Red|Hoverboard")
	float HoverboardSlopeAccel = 5200.f;    // cm/s^2 downhill pull at max steepness = "slide down cliffs"
	UPROPERTY(EditAnywhere, Category = "Red|Hoverboard")
	float HoverboardFriction = 0.35f;       // low ground friction = glide
	UPROPERTY(BlueprintReadOnly, Category = "Red|Hoverboard")
	bool bHoverboarding = false;
	float SavedGroundFriction = 8.f;
	float SavedBrakingWalk = 2048.f;
	/** SLAM (Left-Ctrl): while airborne, dive straight down; on impact fire the landing-slam AOE. */
	UPROPERTY(EditAnywhere, Category = "Red|Hoverboard")
	float SlamDiveSpeed = 9000.f;
	/** Authority owns slam damage/state; the autonomous owner may predict only the dive movement. */
	UPROPERTY(ReplicatedUsing = OnRep_Slamming)
	bool bSlamming = false;
	// AUTO HOVER-GLIDE: go off a cliff and the board auto-catches you — float down at a controlled rate
	// (no crash), hugging the surface. Holding Space (jetpack) or Ctrl (slam) overrides it.
	UPROPERTY(EditAnywhere, Category = "Red|Hoverboard")
	float HoverHeight = 80.f;             // cm gap held above the ground when close
	UPROPERTY(EditAnywhere, Category = "Red|Hoverboard")
	float HoverSinkSpeed = 1400.f;        // cm/s controlled descent (vs a ~40 m/s crash)
	UPROPERTY(EditAnywhere, Category = "Red|Hoverboard")
	float CliffCatchDistance = 10000.f;   // cm below to look for ground to glide over
	UPROPERTY(EditAnywhere, Category = "Red|Hoverboard")
	float HoverEngageMinDrop = 600.f;     // cm — only auto-catch on a real cliff (~6m), not a small hop
	bool bAutoGlide = false;

	// --- Movement VISUAL FX (2026-07-08): jetpack thrust flame, speed trail, board underglow. The
	//     jetpack canister mesh is HIDDEN (it mounted wrong); the flame is the jetpack read now. ---
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|FX")
	TObjectPtr<UNiagaraComponent> JetpackFlame;
	UPROPERTY() TObjectPtr<UNiagaraSystem> JetpackFlameFX;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|FX")
	TObjectPtr<UNiagaraComponent> SpeedTrail;
	UPROPERTY() TObjectPtr<UNiagaraSystem> SpeedTrailFX;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|FX")
	TObjectPtr<UPointLightComponent> BoardGlow;
	bool bTrailOn = false;
	bool bBoardGlowOn = false;

	/** Short downward trace: true when real ground is within the capsule — the genuine touchdown gate
	 *  (the CMC can report a spurious MOVE_Walking tick at altitude, which must NOT end the dive). */
	bool IsNearGround() const;

	/** When true, death respawns onto the cloning station and redrops instead of a ground PlayerStart. */
	UPROPERTY(EditAnywhere, Category = "Red|Skydive")
	bool bDropLoopEnabled = true;
	/** Console test: launch up a touch and enter the dive (stand in for the station jump). */
	UFUNCTION(Exec)
	void Skydive();

	// --- The Drop: RED atmospheric-entry plume (trails the falling diver; the "RED = DEAD incoming" read) ---
	/** Guaranteed-red glow (Metal-safe, seen from the ground) — the primary threat signal. */
	UPROPERTY(VisibleAnywhere, Category = "Red|Skydive|Plume")
	TObjectPtr<UPointLightComponent> PlumeLight;
	/** Trailing smoke/fire volume (best-effort red tint; swappable). */
	UPROPERTY(VisibleAnywhere, Category = "Red|Skydive|Plume")
	TObjectPtr<UNiagaraComponent> PlumeSmoke;
	UPROPERTY(EditAnywhere, Category = "Red|Skydive|Plume")
	TObjectPtr<UNiagaraSystem> PlumeSmokeFX;
	UPROPERTY(EditAnywhere, Category = "Red|Skydive|Plume")
	FLinearColor PlumeColor = FLinearColor(1.f, 0.06f, 0.02f);
	UPROPERTY(EditAnywhere, Category = "Red|Skydive|Plume")
	float PlumeLightIntensity = 12000.f;   // toned down from 80000 so it glows, not screen-washes
	UPROPERTY(EditAnywhere, Category = "Red|Skydive|Plume")
	float PlumeLightRadius = 3000.f;
	UPROPERTY(EditAnywhere, Category = "Red|Skydive|Plume")
	float PlumeSmokeScale = 8.f;
	void SetPlumeActive(bool bOn);

	// --- The Drop: landing SLAM (crater + AoE + knockback + landing-shield invuln on touchdown) ---
	UPROPERTY(EditAnywhere, Category = "Red|Slam")
	TObjectPtr<UNiagaraSystem> SlamExplosionFX;
	/** Secondary Sand FX rock/debris burst layered under the broad dust impact. */
	UPROPERTY(EditAnywhere, Category = "Red|Slam")
	TObjectPtr<UNiagaraSystem> SlamDebrisFX;
	/** Stylized ground crack is a mesh fallback, so the impact still reads if deferred decals are unavailable. */
	UPROPERTY(EditAnywhere, Category = "Red|Slam")
	TObjectPtr<class UStaticMesh> SlamGroundCrackMesh;
	UPROPERTY(EditAnywhere, Category = "Red|Slam")
	TObjectPtr<UMaterialInterface> SlamGroundCrackMaterial;
	UPROPERTY(EditAnywhere, Category = "Red|Slam")
	TObjectPtr<UMaterialInterface> SlamCraterDecalMaterial;
	/** Native Action Trooper clips on the exact Tall-Female skeleton used by the gameplay pawn. */
	UPROPERTY(EditAnywhere, Category = "Red|Slam|Animation")
	TObjectPtr<UAnimSequence> SlamWindupAnim;
	UPROPERTY(EditAnywhere, Category = "Red|Slam|Animation")
	TObjectPtr<UAnimSequence> SlamDiveAnim;
	UPROPERTY(EditAnywhere, Category = "Red|Slam|Animation")
	TObjectPtr<UAnimSequence> SlamImpactAnim;
	/** Pressing E on the ground performs a short readable hop before the downward smash. */
	UPROPERTY(EditAnywhere, Category = "Red|Slam|Movement")
	float SlamHopSpeed = 850.f;
	UPROPERTY(EditAnywhere, Category = "Red|Slam|Movement")
	float SlamGroundWindupDuration = 0.34f;
	UPROPERTY(EditAnywhere, Category = "Red|Slam|Movement")
	float SlamAirWindupDuration = 0.14f;
	UPROPERTY(EditAnywhere, Category = "Red|Slam")
	TSubclassOf<UCameraShakeBase> SlamCameraShake;
	UPROPERTY(EditAnywhere, Category = "Red|Slam")
	TSubclassOf<UDamageType> SlamDamageType;
	UPROPERTY(EditAnywhere, Category = "Red|Slam")
	FLinearColor SlamLightColor = FLinearColor(1.f, 0.05f, 0.02f);
	UPROPERTY(EditAnywhere, Category = "Red|Slam")
	float SlamMinImpactSpeed = 1200.f;   // below this (a hop) = no slam
	UPROPERTY(EditAnywhere, Category = "Red|Slam")
	float SlamBaseDamage = 60.f;
	UPROPERTY(EditAnywhere, Category = "Red|Slam")
	float SlamMinDamageFrac = 0.25f;
	UPROPERTY(EditAnywhere, Category = "Red|Slam")
	float SlamInnerRadius = 200.f;
	UPROPERTY(EditAnywhere, Category = "Red|Slam")
	float SlamOuterRadius = 650.f;
	UPROPERTY(EditAnywhere, Category = "Red|Slam")
	float SlamKnockback = 900.f;
	UPROPERTY(EditAnywhere, Category = "Red|Slam")
	float SlamInvulnDuration = 1.0f;
	UPROPERTY(EditAnywhere, Category = "Red|Slam")
	float SlamLightIntensity = 50000.f;
	UPROPERTY(EditAnywhere, Category = "Red|Slam")
	float SlamLightRadius = 1400.f;
	UPROPERTY(EditAnywhere, Category = "Red|Slam")
	float SlamLightLifetime = 0.35f;
	UPROPERTY(EditAnywhere, Category = "Red|Slam")
	float SlamFXScale = 2.5f;
	UPROPERTY(EditAnywhere, Category = "Red|Slam")
	float SlamShakeInnerRadius = 500.f;
	UPROPERTY(EditAnywhere, Category = "Red|Slam")
	float SlamShakeOuterRadius = 4000.f;
	UPROPERTY(EditAnywhere, Category = "Red|Slam")
	bool bSlamFriendlyFire = true;

	// --- Grapple hook (RMB / Q): reel-in, Just Cause style. CMC-native (Titan's is GAS/Mover, not portable). ---
	UPROPERTY(EditAnywhere, Category = "Red|Grapple")
	TObjectPtr<UNiagaraSystem> GrappleRopeFX;      // BeamsPack NS_BeamOnly_02 (continuous lightning tether)
	/** Electric head that visibly shoots along the new plasma tether and rests at its anchor. */
	UPROPERTY(EditAnywhere, Category = "Red|Grapple|Visual")
	TObjectPtr<UNiagaraSystem> GrapplePlasmaHeadFX;
	UPROPERTY(EditAnywhere, Category = "Red|Grapple")
	float GrappleMaxRange = 25000.f;                // cm — how far you can hook (~250 m; planet mesas)
	UPROPERTY(EditAnywhere, Category = "Red|Grapple")
	float GrappleMinRange = 150.f;                  // cm — ignore only the floor directly underfoot
	UPROPERTY(EditAnywhere, Category = "Red|Grapple")
	float GrappleSpeed = 3000.f;                    // cm/s CAP on approach speed (smooth pull, not a yank)
	UPROPERTY(EditAnywhere, Category = "Red|Grapple")
	float GrapplePullAccel = 5000.f;                // cm/s^2 ramp toward the anchor (keeps momentum → swing)
	UPROPERTY(EditAnywhere, Category = "Red|Grapple")
	float GrappleDrag = 0.9f;                        // per-second velocity damping so the swing settles smoothly
	UPROPERTY(EditAnywhere, Category = "Red|Grapple")
	float GrappleArrivalDist = 250.f;               // cm — stop when this close to the anchor
	UPROPERTY(EditAnywhere, Category = "Red|Grapple")
	float GrappleMaxTime = 6.f;                      // s — safety timeout (longer for swings)
	UPROPERTY(EditAnywhere, Category = "Red|Grapple")
	float GrappleExitBoost = 0.45f;                 // fraction of reel speed kept as an arc-off launch
	/** One server-authoritative damage application when a player tether is accepted. */
	UPROPERTY(EditAnywhere, Category = "Red|Grapple|PvP", meta = (ClampMin = "0.0"))
	float GrapplePlayerDamage = 20.f;
	UPROPERTY(EditAnywhere, Category = "Red|Grapple|PvP")
	TSubclassOf<UDamageType> GrappleDamageType;
	/** Each participant accelerates toward the shared midpoint at this rate. */
	UPROPERTY(EditAnywhere, Category = "Red|Grapple|PvP", meta = (ClampMin = "0.0"))
	float GrapplePlayerPullAccel = 2600.f;
	/** Per-participant speed cap toward the shared midpoint; prevents network correction launches. */
	UPROPERTY(EditAnywhere, Category = "Red|Grapple|PvP", meta = (ClampMin = "100.0"))
	float GrapplePlayerPullSpeed = 1800.f;
	/** Release the player tether before the capsules overlap. */
	UPROPERTY(EditAnywhere, Category = "Red|Grapple|PvP", meta = (ClampMin = "100.0"))
	float GrapplePlayerMinSeparation = 300.f;
	/** Jetpack-while-grappling combo: hold Space mid-reel to reel FASTER and gain altitude. */
	UPROPERTY(EditAnywhere, Category = "Red|Grapple")
	float GrappleJetpackSpeedMult = 1.8f;
	UPROPERTY(EditAnywhere, Category = "Red|Grapple")
	float GrappleJetpackLift = 6500.f;              // cm/s upward added while jetpacking on the grapple
	UPROPERTY(EditAnywhere, Category = "Red|Grapple")
	FName GrappleHandSocket = TEXT("hand_r");       // rope origin
	/** Width multiplier for the crossed plasma ribbons (the donor mesh is 100 cm wide). */
	UPROPERTY(EditAnywhere, Category = "Red|Grapple|Visual", meta = (ClampMin = "0.01", ClampMax = "0.25"))
	float GrapplePlasmaWidth = 0.18f;
	/** Fast width modulation keeps the tether reading as energized plasma instead of a rigid cable. */
	UPROPERTY(EditAnywhere, Category = "Red|Grapple|Visual", meta = (ClampMin = "0.0", ClampMax = "0.75"))
	float GrapplePlasmaPulse = 0.28f;
	/** Time for the plasma head to visibly shoot from the hand to a newly accepted anchor. */
	UPROPERTY(EditAnywhere, Category = "Red|Grapple|Visual", meta = (ClampMin = "0.01", ClampMax = "0.5"))
	float GrapplePlasmaLaunchTime = 0.14f;
	/** Keep the project-owned plasma ribbons under the Beams Pack ribbon until the vendor renderer is
	 * visually verified on the target GPU. This preserves a readable tether if Niagara is loaded but
	 * imperceptible at runtime; it can be disabled per character once the vendor-only presentation passes. */
	UPROPERTY(EditAnywhere, Category = "Red|Grapple|Visual")
	bool bKeepGrappleFallbackVisible = true;

	UFUNCTION()
	void OnRep_Grappling();

private:
	bool TryGrapple();                              // activates whichever Q/E slot currently owns Grapple
	bool FindValidGrapplePoint(const FVector& TraceOrigin, const FVector& TraceDirection,
		FVector& OutPoint, FVector& OutNormal, ARedPlayerCharacter*& OutPlayerTarget) const;
	bool IsValidGrapplePlayerTarget(const ARedPlayerCharacter* Target, bool bCheckReservation) const;
	bool HasGrappleLineOfSight(const ARedPlayerCharacter* Target) const;
	FVector GetGrappleTargetPoint() const;
	void StartGrapple(const FVector& Point, const FVector& SurfaceNormal,
		ARedPlayerCharacter* PlayerTarget = nullptr);
	void StopGrapple(bool bBoost);                  // exit to MOVE_Falling (+ optional arc boost)
	void StopGrappleAndNotifyAuthority(bool bBoost); // local prediction plus owner->server stop
	void StopGrappleInput();                        // local release + explicit authoritative stop RPC
	UFUNCTION(Server, Reliable)
	void ServerStopGrapple(bool bBoost);
	void TickGrapple(float DeltaSeconds);           // reel + update rope
	void SetGrappleRope(bool bOn);
	void UpdateGrappleTether();

	UPROPERTY(ReplicatedUsing = OnRep_Grappling)
	bool bGrappling = false;
	UPROPERTY(Replicated)
	FVector GrapplePoint = FVector::ZeroVector;
	UPROPERTY(Replicated)
	FVector_NetQuantizeNormal GrappleNormal = FVector::UpVector;
	/** Dynamic PvP endpoint. Null keeps the existing fixed terrain-anchor behavior. */
	UPROPERTY(Replicated)
	TObjectPtr<ARedPlayerCharacter> GrappleTarget = nullptr;
	/** Authority-only reservation prevents several grapplers from destabilizing one target. */
	TWeakObjectPtr<ARedPlayerCharacter> GrappledBy;
	float GrappleElapsed = 0.f;
	float SavedGrappleGravity = 1.f;
	/** Live Beams VFX Pack tether. The spline components below are load/cook fallbacks only. */
	UPROPERTY(VisibleAnywhere, Transient, Category = "Red|Grapple|Visual")
	TObjectPtr<UNiagaraComponent> GrappleRope;
	UPROPERTY(Transient)
	TObjectPtr<UNiagaraComponent> GrapplePlasmaHead;
	/** Cook-safe fallback ribbons, shown only when the Beams VFX Pack asset cannot load. */
	UPROPERTY(VisibleAnywhere, Category = "Red|Grapple|Visual")
	TObjectPtr<USplineMeshComponent> GrapplePlasmaBeamA;
	UPROPERTY(VisibleAnywhere, Category = "Red|Grapple|Visual")
	TObjectPtr<USplineMeshComponent> GrapplePlasmaBeamB;
	float GrappleVisualStartTime = 0.0f;
public:

private:
	float SavedGravityScale = 1.f;
	float SavedAirControl = 0.2f;
	FTimerHandle SkydiveLandTimer;
	/** PERF: re-render the HUD portrait + minimap captures at a low rate instead of every frame. */
	FTimerHandle HudCaptureTimer;
	/** Alternates portrait vs minimap capture each tick so they never render in the same frame
	 *  (same-frame capture bled the portrait into the minimap's corner on Metal). */
	bool bHudCapturePortraitTurn = false;
	void RefreshHudCaptures();
	/** Cached so the redrop/HUD path doesn't iterate all actors on every death. */
	TWeakObjectPtr<ARedCloningStation> CachedStation;
	TWeakObjectPtr<ARedOctosphereManager> CachedOctosphere;
	/** Resolve (and cache) the level's octosphere manager, or nullptr if none. */
	ARedOctosphereManager* ResolveOctosphere();

	// The Drop: armed on boarding the station; the dive STARTS when the pawn actually leaves the deck
	// (arming while standing insta-cancelled — the CMC "landed" on the deck the same frame).
	bool bDropArmed = false;

	// Landing slam runtime state.
	float LastFallSpeed = 0.f;          // cached ONLY while MOVE_Falling (see Tick) → the touchdown impact speed
	bool bLandingInvuln = false;        // brief post-slam invuln window (TakeDamage early-returns while true)
	FTimerHandle LandingInvulnTimer;
	FTimerHandle SlamDivePoseTimer;
	FTimerHandle SlamImpactPoseTimer;
	float SlamWindupRemaining = 0.f;
	void EndLandingInvuln() { bLandingInvuln = false; }
	UFUNCTION()
	void OnRep_Slamming();
	void BeginSlamPresentation(float WindupSeconds);
	void PlaySlamDivePose();
	void PlaySlamImpactPose();
	void RestoreSlamAnimation();
	/** Authority: radial damage + knockback + invuln + fire the FX multicast. */
	void DoLandingSlam(float ImpactSpeed);
	/** Cosmetic slam FX (explosion, crater decal, red flash, camera shake) — runs on every client. */
	void PlaySlamFX_Local(const FVector& Center, const FVector& GroundUp, float Strength01);
	UFUNCTION(NetMulticast, Unreliable)
	void MulticastSlamFX(FVector Center, FVector GroundUp, float Strength01);
public:

	// --- Back-holster (rifle on the spine, barrel down; H toggles holster/draw). Transform is
	// live-tunable so the back position can be dialed in via UECP without a rebuild. ---
	UPROPERTY(EditAnywhere, Category = "Red|Weapon|Holster")
	FName HolsterSocket = TEXT("spine_03");
	UPROPERTY(EditAnywhere, Category = "Red|Weapon|Holster")
	FVector HolsterLocation = FVector(20.f, -21.f, -5.f);                  // tuned live: up the back, centered, off the body
	UPROPERTY(EditAnywhere, Category = "Red|Weapon|Holster")
	FRotator HolsterRotation = FRotator(-24.155939f, 86.379787f, -0.863638f); // tuned live: vertical, barrel down (barrel = rifle local Y)
	UPROPERTY(ReplicatedUsing = OnRep_Holstered)
	bool bHolstered = false;
	UFUNCTION()
	void OnRep_Holstered();
	void ApplyHolsterState();

	/** Mouse look sensitivity (degrees per input unit) for the gravity-aligned orbit camera. */
	UPROPERTY(EditAnywhere, Category = "Red|Camera")
	float LookYawScale = 2.5f;
	UPROPERTY(EditAnywhere, Category = "Red|Camera")
	float LookPitchScale = 2.5f;

	/** Orbit-camera pitch limits (degrees; positive = looking up). Min widened to -85 so the re-entry
	 *  drop can tilt the camera steeply DOWN to watch the desert planet rush up. */
	UPROPERTY(EditAnywhere, Category = "Red|Camera")
	float CameraPitchMin = -85.f;
	UPROPERTY(EditAnywhere, Category = "Red|Camera")
	float CameraPitchMax = 65.f;

	/** The camera pitch the drop STARTS at (set once in BeginOrbitalDrop so the diver opens looking
	 *  DOWN at the planet). After that the camera is FREE — the player aims it with the mouse the whole
	 *  way down. -55 = a stable downward opening angle (past ~-80 the boom gimbals). Reset to ~-12 on
	 *  touchdown (StopSkydive). Tunable live. */
	UPROPERTY(EditAnywhere, Category = "Red|Camera")
	float OrbitalDropCameraPitch = -55.f;

	/** Skydive horizontal STEER: hold WASD to glide toward the yaw-heading direction at this speed
	 *  (cm/s) so you can pick where to land — AirControl alone is negligible against the ~140 m/s
	 *  descent. Release input and horizontal drift bleeds to a stop. Accel = how snappily it responds.
	 *  9000 vs the 14000 cm/s descent = a ~0.64 glide ratio: strong, controllable, not floaty. */
	UPROPERTY(EditAnywhere, Category = "Red|Skydive")
	float DropSteerSpeed = 9000.f;
	UPROPERTY(EditAnywhere, Category = "Red|Skydive")
	float DropSteerAccel = 2.4f;
	/** Raw WASD axis captured each frame (MoveForward/MoveRight), used to steer the dive from the
	 *  yaw-only heading instead of the pitched camera — so looking straight DOWN to aim doesn't
	 *  collapse/flip the steer direction. Transient. */
	float DropSteerFwd = 0.f;
	float DropSteerRight = 0.f;

	UPROPERTY(EditAnywhere, Category = "Red|Camera")
	float BaseFOV = 80.f;  // Fortnite BR locked FOV
	UPROPERTY(EditAnywhere, Category = "Red|Camera")
	float ADSFOV = 55.f;
	UPROPERTY(EditAnywhere, Category = "Red|Camera")
	float BaseArmLength = 300.f;
	UPROPERTY(EditAnywhere, Category = "Red|Camera")
	float ADSArmLength = 130.f;
	UPROPERTY(EditAnywhere, Category = "Red|Camera")
	float ADSInterpSpeed = 10.f;
	/** Mouse-wheel zoom: added to BaseArmLength in the hip view (does not apply while ADS). */
	UPROPERTY(EditAnywhere, Category = "Red|Camera")
	float ZoomStep = 70.f;
	UPROPERTY(EditAnywhere, Category = "Red|Camera")
	float ZoomMin = -150.f;   // zoom in closer than BaseArmLength
	UPROPERTY(EditAnywhere, Category = "Red|Camera")
	float ZoomMax = 700.f;    // zoom way out
	float ZoomArmOffset = 0.f;
	void OnCameraZoom(float Value);
	/** Hold LMB = rapid fire: StartFiring fires once + starts a repeating timer; StopFiring clears it.
	 *  BlueprintCallable so automated PIE self-tests can fire and measure muzzle/aim alignment. */
	UFUNCTION(BlueprintCallable, Category = "Red|Weapon")
	void StartFiring();
	UFUNCTION(BlueprintCallable, Category = "Red|Weapon")
	void StopFiring();
	/** World-space barrel tip: the weapon transform pushed out by MuzzleFlashOffset (the same
	 *  offset the muzzle flash uses). Bolts spawn HERE — not at the weapon pivot, which sits at
	 *  the grip in the hand ("projectiles launching from the middle of the body"). */
	UFUNCTION(BlueprintCallable, Category = "Red|Weapon")
	FVector GetMuzzleWorldLocation() const;
	/** Energy weapons have no magazine/reload. Firing adds heat; an overheated weapon resumes only
	 *  after passive cooling reaches WeaponHeatResumeFraction. */
	UFUNCTION(BlueprintPure, Category = "Red|Weapon|Heat")
	float GetWeaponHeatNormalized() const;
	UFUNCTION(BlueprintPure, Category = "Red|Weapon|Heat")
	bool IsWeaponOverheated() const;
	FTimerHandle FireTimerHandle;
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	float FireRate = 0.12f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Red|Weapon|Heat", meta = (AllowPrivateAccess = "true", ClampMin = "1.0"))
	float MaxWeaponHeat = 100.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Red|Weapon|Heat", meta = (AllowPrivateAccess = "true", ClampMin = "0.0"))
	float WeaponHeatPerShot = 7.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Red|Weapon|Heat", meta = (AllowPrivateAccess = "true", ClampMin = "0.0"))
	float WeaponHeatCoolRate = 28.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Red|Weapon|Heat", meta = (AllowPrivateAccess = "true", ClampMin = "0.0", ClampMax = "1.0"))
	float WeaponHeatResumeFraction = 0.25f;
	/** Independent heat and overheat lock for each replicated weapon slot. */
	UPROPERTY(ReplicatedUsing = OnRep_WeaponHeatState, VisibleAnywhere, BlueprintReadOnly, Category = "Red|Weapon|Heat", meta = (AllowPrivateAccess = "true"))
	TArray<float> WeaponSlotHeat;
	UPROPERTY(ReplicatedUsing = OnRep_WeaponHeatState, VisibleAnywhere, BlueprintReadOnly, Category = "Red|Weapon|Heat", meta = (AllowPrivateAccess = "true"))
	TArray<uint8> WeaponSlotOverheated;
	/** Muzzle flash placement, live-tunable (barrel runs along weapon local +Y; yaw 90 points the flash down it). */
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	FVector MuzzleFlashOffset = FVector(0.f, 55.f, 7.f);
	UPROPERTY(EditAnywhere, Category = "Red|Weapon")
	FRotator MuzzleFlashRot = FRotator(0.f, 90.f, 0.f);

	UPROPERTY(EditAnywhere, Category = "Red|Move")
	float WalkSpeed = 400.f;  // matches the locomotion blendspace; 548 Fortnite run needs anim play-rate scaling first
	UPROPERTY(EditAnywhere, Category = "Red|Move")
	float SprintSpeed = 800.f;

public:
	/** SPHERE-CORRECT locomotion values for the AnimBP. The stock event-graph math is world-frame
	 *  (VSizeXY flattens velocity to world XY, CalculateDirection works in world yaw) — on a planet
	 *  where "up" isn't Z, GroundSpeed underreads (idle-blend gliding, the "slow motion" run) and
	 *  Direction is garbage (strafe samples while running forward, the "crossed legs"). The ABP
	 *  reads THESE instead; computed every Tick in the pawn's own tangent frame. */
	UPROPERTY(BlueprintReadOnly, Category = "Red|Anim")
	float AnimGroundSpeed = 0.f;
	UPROPERTY(BlueprintReadOnly, Category = "Red|Anim")
	float AnimDirectionDeg = 0.f;
	/** Drives the ABP's ShouldMove (Idle<->Standing state): moving OR pivoting in place. The old
	 *  ABP-side computation (speed AND acceleration) could never see a pivot, so the legs stayed
	 *  in the Idle state and dragged ("crossed legs") while the body rotated. */
	UPROPERTY(BlueprintReadOnly, Category = "Red|Anim")
	bool bAnimShouldMove = false;

	/** RUN-BOB STABILIZER: the DMD run cycle bounces the body ±17cm vertically per stride (measured)
	 *  — reads as "head bobbing" at speed. The mesh is counter-translated by this fraction of the
	 *  pelvis deviation from its slow-follow baseline. 0 = raw animation, 1 = fully level. */
	UPROPERTY(EditAnywhere, Category = "Red|Anim")
	float RunBobDamp = 0.65f;
	/** Counter-roll fraction for the run cycle's authored torso rock (measured ±7.9° per stride —
	 *  "bobbing back and forth"). 0 = raw animation, 1 = fully level shoulders. */
	UPROPERTY(EditAnywhere, Category = "Red|Anim")
	float RunRollDamp = 0.0f;   // counter-roll DISABLED: phase lag made it additive, not subtractive

private:

	// Procedural aim-offset: drives the AnimBP "AimRotation" var (the spine Transform Modify Bone added
	// by URedMMOEditorTools::AddAimModifyBone) so the chest+arms+gun pitch/yaw to follow the camera.
	// All EditAnywhere so the sign/amount can be tuned live via UECP without a rebuild.
	// spine_04 component-space frame (derived empirically): X=forward, Y=up, Z=right.
	// up/down aim = rotate around the RIGHT axis = FRotator.Yaw ; left/right = around UP axis = FRotator.Pitch.
	UPROPERTY(EditAnywhere, Category = "Red|Aim")
	float AimUpDownScale = 1.0f;     // global aim magnitude (1.5 leaned too hard on the new trooper spine_03)
	// Component-space axis for "look up/down" is skeleton-dependent. Drive all 3 from CamPitch via
	// these live-tunable scales so the correct axis can be dialed in via UECP without a rebuild.
	UPROPERTY(EditAnywhere, Category = "Red|Aim")
	float AimPitchScale = 0.0f;      // CamPitch -> FRotator.Pitch (unused — mesh is yaw-rotated)
	UPROPERTY(EditAnywhere, Category = "Red|Aim")
	float AimYawScale = 0.0f;        // CamPitch -> FRotator.Yaw (the old guess)
	UPROPERTY(EditAnywhere, Category = "Red|Aim")
	float AimRollScale = -1.0f;      // CamPitch -> FRotator.Roll = up/down aim (correct axis on this 90deg-rotated mesh; negated)
	UPROPERTY(EditAnywhere, Category = "Red|Aim")
	float AimLeftRightScale = 1.0f;  // CamYaw -> FRotator.Yaw = left/right aim (correct axis, standing)
	/** Constant up/down correction (deg, added to CamPitch before the axis scales): zeroes the
	 *  firing pose's built-in barrel tilt ("always pointed a little up"). Tuned live in PIE. */
	UPROPERTY(EditAnywhere, Category = "Red|Aim")
	float AimUpDownBias = 0.0f;   // was -11.9 for the OLD rig; on the trooper it bent the spine ~18deg
	                              // down every time you fired at a level camera ("crouched, head down").
	                              // The barrel is leveled by AlignWeaponBarrelToCamera now, not this bias.

	/** Turn-in-place (standing aim): feet stay planted while the spine tracks the aim; past
	 *  StartAngle the body does one fast pivot burst back under the camera (plant-and-pivot,
	 *  not a continuous leg twist). StartAngle stays under AimMaxAngle so the gun never
	 *  saturates before the feet catch up. */
	UPROPERTY(EditAnywhere, Category = "Red|Aim")
	float TurnInPlaceStartAngle = 45.f;
	UPROPERTY(EditAnywhere, Category = "Red|Aim")
	float TurnInPlaceStopAngle = 6.f;
	UPROPERTY(EditAnywhere, Category = "Red|Aim")
	float TurnInPlacePivotSpeed = 18.f;
	/** While pivoting, the legs play the locomotion blendspace's own strafe samples at this blend
	 *  speed (cm/s on the Y axis) in the pivot direction — the feet visibly STEP around the turn
	 *  instead of dragging the idle pose. No dedicated turn asset needed. */
	UPROPERTY(EditAnywhere, Category = "Red|Aim")
	float TurnInPlaceStepSpeed = 170.f;
	bool bTurnInPlacePivoting = false;
	float TurnInPlaceDirSign = 1.f;
	float BobBaselineVert = 1.0e9f;   // sentinel: initialize from the first sample
	float BobBaselineLat = 0.f;
	float BobCorrV = 0.f;
	float BobCorrL = 0.f;
	float BobRollBaseline = 0.f;
	float BobRollCorr = 0.f;         // degrees of mesh counter-roll currently applied
	UPROPERTY(EditAnywhere, Category = "Red|Aim")
	float AimLeftRightBias = 7.5f;   // PIE-measured 2026-07-02: barrel was 7.2 deg left -> now +0.2
	UPROPERTY(EditAnywhere, Category = "Red|Aim")
	float AimMaxAngle = 50.0f;
	UPROPERTY(EditAnywhere, Category = "Red|Aim")
	FName AimRotationVarName = TEXT("AimRotation");
	/** FocalRig inputs on ABP_RedTrooperFemale. Target is hierarchy-global (mesh component space). */
	UPROPERTY(EditAnywhere, Category = "Red|Aim")
	FName FocalAimTargetVarName = TEXT("FocalAimTarget");
	UPROPERTY(EditAnywhere, Category = "Red|Aim")
	FName FocalAimWeightVarName = TEXT("FocalAimWeight");
	/** Live verification of the visible physical barrel (grip->Muzzle) against the exact accepted
	 * projectile direction. Exposed to editor/MCP diagnostics so future animation changes cannot
	 * silently reintroduce a sideways or backward gun. 1.0 is perfect alignment. */
	UPROPERTY(VisibleAnywhere, Category = "Red|Aim|Debug")
	float WeaponBarrelAimDot = -1.0f;
	UPROPERTY(VisibleAnywhere, Category = "Red|Aim|Debug")
	FVector WeaponBarrelDirectionWorld = FVector::ZeroVector;
	UPROPERTY(VisibleAnywhere, Category = "Red|Aim|Debug")
	FVector WeaponDesiredAimDirectionWorld = FVector::ZeroVector;
	UPROPERTY(EditAnywhere, Category = "Red|Aim")
	bool bAlignWeaponBarrelToCamera = false;
	UPROPERTY(EditAnywhere, Category = "Red|Aim")
	FVector WeaponBarrelSocketAimAxis = FVector(0.0f, 1.0f, 0.0f);
	/** Extra rifle offset (hand-socket frame, cm) applied only while aiming/firing so the support
	 *  hand meets the foregrip. Tune live with `WeaponAimNudge X Y Z`. */
	UPROPERTY(EditAnywhere, Category = "Red|Aim")
	FVector WeaponAimNudgeOffset = FVector::ZeroVector;
	UPROPERTY(EditAnywhere, Category = "Red|Aim", meta = (ClampMin = "0.0"))
	float WeaponAimAlignSpeed = 35.0f;

	UPROPERTY(EditAnywhere, Category = "Red|Vehicle", meta = (ClampMin = "0.0"))
	float VehicleBoardRadius = 6500.0f;

	/** Play as the custom Alien body (Alien_Rigged on Alien_Rigged_Skeleton). Rig deforms cleanly (bone
	 *  rolls fixed). Driven by single-node Idle/Run playback (see AlienIdleAnim/AlienRunAnim +
	 *  UpdateAlienLocomotion) — NOT an AnimBlueprint, because the retargeted ABP keeps failing to compile.
	 *  Retained as a development fallback when the imported character creator is unavailable.
	 *  Default false = trooper (its own full ABP). */
	UPROPERTY(EditAnywhere, Category = "Red|Body")
	bool bUseAlienBody = false;
	/** Uniform scale for the Alien body (it authors ~233cm; ~0.75 fits the ~180cm player capsule). */
	UPROPERTY(EditAnywhere, Category = "Red|Body", meta = (ClampMin = "0.1"))
	float AlienBodyScale = 0.75f;

	// Cached bodies for the development fallback swap. Loaded in the ctor.
	UPROPERTY(Transient) TObjectPtr<USkeletalMesh> TrooperBodyMesh;
	/** Creator-native modular upper used by the default deep-red trooper preset. */
	UPROPERTY(Transient) TObjectPtr<USkeletalMesh> TrooperUpperBodyMesh;
	UPROPERTY(Transient) TObjectPtr<USkeletalMesh> AlienBodyMesh;
	UPROPERTY(Transient) TSubclassOf<class UAnimInstance> TrooperAnimClass;
	/** The PO-Art creator owns a second weapon component. Gameplay always uses the native rifle;
	 *  creator preview swaps between the native rifle and a selected vendor weapon without overlap. */
	UPROPERTY(Transient) TObjectPtr<USkeletalMeshComponent> CreatorWeaponMesh;
	/** Enforce exactly one visible weapon on gameplay and character-creator preview pawns. */
	void UpdateCreatorWeaponVisibility();
	// The alien has NO AnimBlueprint — its retargeted ABP keeps re-breaking its state-machine compile
	// (K2Node_TransitionRuleGetter on the additive/jump anims) and throws a "Play in Editor? unresolved
	// compiler errors" modal on every Play. Instead it runs single-node playback of these retargeted
	// sequences, speed-swapped in Tick (UpdateAlienLocomotion): clean, no compile error, no modal.
	UPROPERTY(Transient) TObjectPtr<class UAnimSequence> AlienIdleAnim;
	UPROPERTY(Transient) TObjectPtr<class UAnimSequence> AlienRunAnim;
	bool bAlienRunning = false;
	/** Apply the current bUseAlienBody choice to GetMesh() (mesh, anim class, transform, trooper-only attachments). */
	void ApplyBody();
	/** True while either the standalone or creator-native modular female trooper drives the gameplay mesh. */
	bool IsUsingTrooperBody() const;
	/** Speed-driven single-node Idle/Run swap for the alien body (no AnimBlueprint). Called from Tick. */
	void UpdateAlienLocomotion();
	/** Toggle between the legacy trooper and alien development bodies. */
	void SwapBody();
	/** Opens/closes the imported PO-Art character creator; falls back to SwapBody if unavailable. */
	void ToggleCharacterCreator();

private:
	// movement (camera-relative, projected onto the local surface plane)
	void MoveForward(float Value);
	void MoveRight(float Value);
	/** BlueprintCallable so automated PIE self-tests can drive mouse-look (spin/aim sweeps). */
	UFUNCTION(BlueprintCallable, Category = "Red|Camera")
	void Turn(float Value);
	UFUNCTION(BlueprintCallable, Category = "Red|Camera")
	void LookUp(float Value);

	/** Gravity-aligned ORBIT camera (GravityCore pattern): heading = a world vector kept tangent to
	 *  the local gravity plane; pitch = a clamped scalar. The boom is rebuilt from these each tick —
	 *  roll and pole-spin are structurally impossible. Control rotation is NOT used for the camera. */
	void UpdateOrbitCamera();
	FVector CameraForward = FVector::ForwardVector;
	float CameraPitch = -10.f;
	/** Activates radial movement from the live PlanetGen actor, discovered by reflection. */
	bool TryActivatePlanetGenMovement();
	/** Bounded startup retry for worlds where BP_CLMPlanet spawns after the player. */
	void RetryPlanetGenInitialization();
	/** Starts the existing landing retry without disturbing boarded/frozen/drop states. */
	void StartPlanetSurfaceSnap();
	void TrySnapToPlanetSurface();
	bool FindPlanetSurfaceBelow(FVector& OutLocation, FVector& OutNormal) const;

	/** Drives the SpaceStarDome's SpaceFade by view altitude (0 = ground/cyan sky, 1 = dark space + stars). */
	void UpdateSkyFade();
	/** Applies authentic SoStylized animated water locally; GameMode does not exist on remote clients. */
	void EnsureClientWaterPresentation();
	float NextClientWaterPresentationTime = 0.f;
	int32 ClientWaterPresentationAttempts = 0;
	/** PlanetGen's near-surface Single Layer Water sphere. It is hidden only for
	 *  this local viewer after ascent so refraction cannot masquerade as an
	 *  oversized globe around the authored macro planet. */
	TArray<TWeakObjectPtr<class UMeshComponent>> CachedPlanetWaterMeshes;
	TWeakObjectPtr<class UMeshComponent> CachedPlanetMacroSurface;
	bool bPlanetWaterHiddenForOrbit = false;
	UPROPERTY(Transient)
	TArray<TObjectPtr<class UMaterialInstanceDynamic>> SkyFadeDMIs;
	/** Star dome meshes recentered on the camera each tick so space never leaves the shell. */
	TArray<TWeakObjectPtr<class UStaticMeshComponent>> SkyStarDomeMeshes;
	float NextSkyDomeBindTime = 0.f;
	float NextSpaceStarEnsureTime = 0.f;
	/** The sky's atmosphere sun — used to fade the star sky in at NIGHT (sun below local horizon). */
	UPROPERTY(Transient)
	class UDirectionalLightComponent* CachedSunLight = nullptr;

	// weapon
	void Fire();
	/** Resolve the exact camera-reticle hit point and the barrel-tip direction used by both FocalRig
	 *  and projectile spawning. */
	bool ResolveWeaponAim(FVector& OutAimPoint, FVector& OutShotDirection) const;
	void PlayFireCosmetics(const FVector& MuzzleLocation, const FVector& ShotDirection, int32 WeaponSlot);
	bool TryFireAuthoritative(const FVector& AimDirection, const FVector& RequestedMuzzleLocation,
		uint16 ClientFireSequence);
	void AlignWeaponBarrelToCamera(float DeltaSeconds);
	UFUNCTION(Server, Reliable)
	void ServerFire(FVector_NetQuantize ClientMuzzleLocation, FVector_NetQuantizeNormal AimDirection,
		uint16 ClientFireSequence);
	UFUNCTION(NetMulticast, Unreliable)
	void MulticastFireCosmetics(FVector_NetQuantize MuzzleLocation, FVector_NetQuantizeNormal ShotDirection,
		uint16 ClientFireSequence, uint8 WeaponSlot);
	UFUNCTION(Server, Reliable)
	void ServerSetCombatAimHeld(bool bHeld);
	UFUNCTION(Server, Unreliable)
	void ServerSetAimDirection(FVector_NetQuantizeNormal AimDirection);
	UFUNCTION(Server, Reliable)
	void ServerSetHolstered(bool bNewHolstered);
	UFUNCTION(Server, Reliable)
	void ServerSetJetpackInput(bool bEngaged, bool bThrust, bool bBoost, bool bOrbitalThrust);
	void SpawnBolt(FVector Start, FRotator Dir, int32 WeaponSlot);
	void StartADS();
	void StopADS();
	void ToggleHolster();        // H: rifle to back (barrel down) or back to hand
	void AttachWeaponToHand();   // draw: re-attach the rifle to the hand socket
	void StartSprint();
	void StopSprint();

	void SelectWeapon(int32 Slot);
	void ApplyCurrentWeaponSlot();
	void EnsureWeaponSlotState();
	float GetWeaponHeatForSlot(int32 Slot) const;
	bool IsWeaponSlotOverheated(int32 Slot) const;
	UFUNCTION()
	void OnRep_CurrentWeaponSlot();
	UFUNCTION()
	void OnRep_WeaponHeatState();
	UFUNCTION(Server, Reliable)
	void ServerSelectWeapon(int32 Slot);
	/** Refresh ability bar icons/visibility for the active weapon loadout. */
	void RefreshAbilityLoadoutForWeapon();
	void OnWeapon1() { SelectWeapon(0); }
	void OnWeapon2() { SelectWeapon(1); }
	// Exactly two replicated active abilities. The loadout overlay can swap them between Q and E.
	UPROPERTY(ReplicatedUsing = OnRep_AbilityLoadout)
	ERedPlayerAbility AbilitySlotQ = ERedPlayerAbility::Grapple;
	UPROPERTY(ReplicatedUsing = OnRep_AbilityLoadout)
	ERedPlayerAbility AbilitySlotE = ERedPlayerAbility::Slam;
	/** Hard references keep the purchased ability icons inside restricted -CookDir builds. */
	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> GrappleAbilityIcon;
	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> SlamAbilityIcon;
	UPROPERTY(EditAnywhere, Category = "Red|Abilities", meta = (ClampMin = "0.0"))
	float GrappleCooldown = 4.0f;
	UPROPERTY(EditAnywhere, Category = "Red|Abilities", meta = (ClampMin = "0.0"))
	float SlamCooldown = 6.0f;
	UPROPERTY(ReplicatedUsing = OnRep_AbilityCooldowns)
	float GrappleCooldownEndServerTime = 0.0f;
	UPROPERTY(ReplicatedUsing = OnRep_AbilityCooldowns)
	float SlamCooldownEndServerTime = 0.0f;
	bool bAbilityLoadoutOpen = false;

	void OnAbilityQ();
	void OnAbilityE();
	void OnAbilityQReleased();
	void OnAbilityEReleased();
	bool TryActivateAbilitySlot(int32 Slot);
	void StopAbilitySlot(int32 Slot);
	bool ActivateAbilityAuthoritative(int32 Slot, const FVector& TraceOrigin, const FVector& TraceDirection);
	ERedPlayerAbility GetAbilityForSlot(int32 Slot) const;
	int32 FindAbilitySlot(ERedPlayerAbility Ability) const;
	float GetAbilityCooldownDuration(ERedPlayerAbility Ability) const;
	float GetAbilityCooldownEnd(ERedPlayerAbility Ability) const;
	float GetAbilityClockSeconds() const;
	void SetPredictedAbilityCooldown(ERedPlayerAbility Ability, float EndTime);
	void UpdateAbilityHUD(class ARedHUD* ReplacementHUD = nullptr);
	void ToggleAbilityLoadout();
	void CloseAbilityLoadout();
	UFUNCTION()
	void HandleAbilityLoadoutSwapRequested();
	UFUNCTION()
	void OnRep_AbilityLoadout();
	UFUNCTION()
	void OnRep_AbilityCooldowns();
	UFUNCTION(Server, Reliable)
	void ServerActivateAbility(int32 Slot, FVector_NetQuantize TraceOrigin, FVector_NetQuantizeNormal TraceDirection);
	UFUNCTION(Client, Reliable)
	void ClientRejectAbilityActivation(int32 Slot);
	UFUNCTION(Server, Reliable)
	void ServerSetAbilityLoadout(ERedPlayerAbility NewQ, ERedPlayerAbility NewE);

	/** Contextually board the aimed-at or nearest RED craft within reach (B/V): shuttle,
	 *  standard fighter, or mini fighter. BlueprintCallable for automated board/exit tests. */
	UFUNCTION(BlueprintCallable, Category = "Red|Ship")
	void EnterVehicle();
	/** Client-owned request; the server re-finds the nearest vehicle and validates board range. */
	UFUNCTION(Server, Reliable)
	void ServerEnterVehicle();
	/** Optional direct mini-fighter shortcut (F). B/V can also select a mini fighter contextually. */
	UFUNCTION(BlueprintCallable, Category = "Red|Ship")
	void EnterMiniFighter();
	UFUNCTION(Server, Reliable)
	void ServerEnterMiniFighter();

	/** Board a migrated Pilotable-Spaceship-System shuttle (BP_Shuttle) by triggering its native
	 *  BPI_Interactable "StartInteraction" — the ship then possesses/seats/flies/exits itself. RED just
	 *  freezes the pilot on board (OnBoardedShip) and restores + regrounds it when the ship re-possesses
	 *  us on exit (see PossessedBy). Returns true if a shuttle was in reach and boarded. */
	UFUNCTION(BlueprintCallable, Category = "Red|Ship")
	bool TryBoardShuttle();
	/** Authority-only boarding path for the shuttle already selected by the shared B/V chooser. */
	bool TryBoardSpecificShuttle(AActor* ShuttleActor);
	UPROPERTY(Transient)
	TObjectPtr<AActor> PilotedShuttle = nullptr;
	bool bWasPilotingShuttle = false;

	bool bADS = false;
	/** True while LMB is held (StartFiring..StopFiring) — keeps the aim/firing overlay up for the whole burst. */
	bool bIsFiringHeld = false;
	/** Authority-owned held-aim state used by listen-server and simulated-proxy copies. */
	UPROPERTY(Replicated)
	bool bReplicatedAimHeld = false;
	/** World-space barrel direction replicated for simulated proxies. The local owner still uses the
	 *  current camera trace; authority validates each shot separately. */
	UPROPERTY(Replicated)
	FVector_NetQuantizeNormal ReplicatedAimDirection = FVector::ForwardVector;
	FVector LastSentAimDirection = FVector::ZeroVector;
	float LastAimDirectionSendTime = -100.f;
	float LastFireTime = -100.f;  // time of last shot; drives the aim-stance blend (relaxed <-> firing pose)
	float LastServerFireTime = -100.f;
	/** Sequence-keyed owner prediction lets the authoritative multicast be suppressed only when
	 *  the server used the same muzzle and direction. Corrected shots replay at the accepted pose. */
	uint16 NextLocalFireSequence = 1;
	TMap<uint16, FVector> PredictedFireMuzzles;
	TMap<uint16, FVector> PredictedFireDirections;
	/** Shared combat-aim gate: drawn weapon + (ADS OR holding fire OR recently fired). */
	bool IsCombatAiming() const;
	float TargetWalkSpeed = 400.f;
	FTimerHandle SurfaceSnapRetryTimer;
	int32 SurfaceSnapAttemptsRemaining = 80;
	FTimerHandle PlanetGenDiscoveryTimer;
	int32 PlanetGenDiscoveryAttemptsRemaining = 0;

	/** Clears the temporary pawn-vs-ship collision ignore after a deboard. */
	FTimerHandle ShipIgnoreTimer;

	/** Home-planet SkyAtmosphere binding. Scattering remains enabled in orbit so its limb persists. */
	TWeakObjectPtr<class USkyAtmosphereComponent> CachedAtmosphere;
	float AtmosphereBaseRayleigh = 1.f;
	float AtmosphereBaseMie = 1.f;
	float AtmosphereFadeAlpha = 1.f;
	float AtmosphereFadeTarget = 1.f;
	float NextAtmosphereBindTime = 0.f;
};
