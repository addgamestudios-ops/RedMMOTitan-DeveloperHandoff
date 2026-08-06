#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "WeaponFirer.generated.h"

class UAnimSequenceBase;
class UMeshComponent;
class UCameraComponent;
class USpringArmComponent;
class UNiagaraSystem;

/**
 * Reliable, planet-aware weapon firer. While the fire key is held (and the
 * cooldown has elapsed) it spawns ProjectileClass from the gun's muzzle socket
 * along the CAMERA look direction. The camera direction is correct regardless of
 * radial planet gravity, and a forward-guard guarantees a shot can never travel
 * backward. The bolt is told to ignore the firing pawn so it can never collide
 * with or launch the player. Built in C++ to bypass unreliable BP-graph authoring.
 *
 * Also drives RMB aim-down-sights (FOV + spring-arm zoom) and guaranteed
 * procedural recoil (camera pitch kick + weapon-mesh kickback), so firing reads
 * even when a body-compatible fire animation is unavailable.
 */
UCLASS(ClassGroup=(RedMMO))
class REDMMO_API AWeaponFirer : public AActor
{
	GENERATED_BODY()

public:
	AWeaponFirer();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	/** The projectile actor to spawn (set to BP_RedProjectile). */
	UPROPERTY(EditAnywhere, Category = "Weapon")
	TSubclassOf<AActor> ProjectileClass;

	/** Optional muzzle-flash actor spawned at the same point (BP_RedMuzzle). */
	UPROPERTY(EditAnywhere, Category = "Weapon")
	TSubclassOf<AActor> MuzzleClass;

	/** Big blue Niagara muzzle plume spawned at the barrel each shot. */
	UPROPERTY(EditAnywhere, Category = "Weapon")
	UNiagaraSystem* MuzzleFX = nullptr;

	/** Scale for the muzzle plume (bigger = more massive). */
	UPROPERTY(EditAnywhere, Category = "Weapon")
	float MuzzleFXScale = 2.5f;

	/** Muzzle flash: scale of each blue flame blob in the star-burst at the barrel
	 *  (reuses the bolt visual, which renders on Metal unlike GPU Niagara). */
	UPROPERTY(EditAnywhere, Category = "Weapon")
	float MuzzleFlashScale = 14.f;

	/** Muzzle flash: lifetime of the flash blobs (seconds). */
	UPROPERTY(EditAnywhere, Category = "Weapon")
	float MuzzleFlashLife = 0.1f;

	/** Muzzle flash: how fat each flame blob is (widens the thin bolt into a flame). */
	UPROPERTY(EditAnywhere, Category = "Weapon")
	float MuzzleFlashFatness = 3.f;

	/** Muzzle flash: blue point-light burst intensity per shot. */
	UPROPERTY(EditAnywhere, Category = "Weapon")
	float MuzzleLightIntensity = 800000.f;

	/** Minimum seconds between shots. */
	UPROPERTY(EditAnywhere, Category = "Weapon")
	float FireInterval = 0.1f;

	/** Fallback distance in front of the weapon mesh used when no muzzle socket exists. */
	UPROPERTY(EditAnywhere, Category = "Weapon")
	float MuzzleFallbackForward = 60.f;

	/** Reject camera-trace hits closer than this (cm) so a shot never aims at the gun/body. */
	UPROPERTY(EditAnywhere, Category = "Weapon")
	float MinAimDistance = 250.f;

	/** Spawn the bolt this far ahead of the muzzle along the fire direction (cm), to clear the body. */
	UPROPERTY(EditAnywhere, Category = "Weapon")
	float MuzzleClearForward = 25.f;

	/** Optional explicit muzzle socket on the weapon mesh (overrides auto-detection). */
	UPROPERTY(EditAnywhere, Category = "Weapon")
	FName MuzzleSocketName = NAME_None;

	/** Bolt lifespan applied on spawn (seconds) so bolts never accumulate. */
	UPROPERTY(EditAnywhere, Category = "Weapon")
	float BoltLifeSpan = 1.6f;

	/** Heat added per shot. */
	UPROPERTY(EditAnywhere, Category = "Weapon|Heat")
	float MaxHeat = 100.f;

	UPROPERTY(EditAnywhere, Category = "Weapon|Heat")
	float HeatPerShot = 7.f;

	/** Heat removed per second while not firing. */
	UPROPERTY(EditAnywhere, Category = "Weapon|Heat")
	float CoolRate = 28.f;

	/** Current heat (read by the HUD). */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Weapon|Heat")
	float Heat = 0.f;

	/** True while overheated (cannot fire until cooled). Read by the HUD. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Weapon|Heat")
	bool bOverheated = false;

	/** Fire animation played on the character each shot (only if skeleton-compatible). */
	UPROPERTY(EditAnywhere, Category = "Weapon|Anim")
	UAnimSequenceBase* FireAnim = nullptr;

	/** Anim-graph slot the fire montage plays into. */
	UPROPERTY(EditAnywhere, Category = "Weapon|Anim")
	FName AnimSlot = TEXT("DefaultSlot");

	/** ADS: camera FOV scale while RMB held (BaseFOV * this). */
	UPROPERTY(EditAnywhere, Category = "Weapon|ADS")
	float ADSFovScale = 0.65f;

	/** ADS: spring-arm length scale while RMB held (BaseArm * this). */
	UPROPERTY(EditAnywhere, Category = "Weapon|ADS")
	float ADSArmScale = 0.6f;

	/** ADS: interp speed for FOV / arm toward their targets. */
	UPROPERTY(EditAnywhere, Category = "Weapon|ADS")
	float ADSInterpSpeed = 12.f;

	/** Recoil: camera pitch kick per shot (scaled by input). */
	UPROPERTY(EditAnywhere, Category = "Weapon|Recoil")
	float RecoilPitch = 0.6f;

	/** Recoil: weapon-mesh backward kick distance per shot (local -X, cm). */
	UPROPERTY(EditAnywhere, Category = "Weapon|Recoil")
	float RecoilKick = 4.f;

	/** Recoil: interp speed recovering the weapon mesh toward its rest location. */
	UPROPERTY(EditAnywhere, Category = "Weapon|Recoil")
	float RecoilRecoverSpeed = 10.f;

	/** Aim: optional body facing while moving/ADS. RedPlayerCharacter owns idle mouse-look. */
	UPROPERTY(EditAnywhere, Category = "Weapon|Aim")
	bool bEnableBodyAim = false;

	/** Aim: how fast the body turns toward your look direction. */
	UPROPERTY(EditAnywhere, Category = "Weapon|Aim")
	float BodyAimSpeed = 12.f;

	/** Aim: tilt the gun up/down with your look elevation. */
	UPROPERTY(EditAnywhere, Category = "Weapon|Aim")
	bool bEnableGunPitch = false;

	/** Aim: gun pitch multiplier (flip sign if it tilts the wrong way). */
	UPROPERTY(EditAnywhere, Category = "Weapon|Aim")
	float GunPitchScale = 1.f;

	/** Aim: offset applied to the gun's aim so the barrel (not just +X) points at the
	 *  reticle. Tune live on the placed actor if the gun points the wrong way. */
	UPROPERTY(EditAnywhere, Category = "Weapon|Aim")
	FRotator GunAimOffsetRot = FRotator::ZeroRotator;

private:
	float AimLogAccum = 0.f;

	float LastFireTime = -1000.f;

	/** Cached weapon mesh + chosen muzzle socket so we don't search every shot. */
	TWeakObjectPtr<UMeshComponent> CachedWeaponMesh;
	FName CachedMuzzleSocket = NAME_None;

	/** Cached camera / spring-arm for ADS, plus their base (rest) values. */
	TWeakObjectPtr<UCameraComponent> CachedCamera;
	TWeakObjectPtr<USpringArmComponent> CachedSpringArm;
	float BaseFOV = 90.f;
	float BaseArm = 0.f;

	/** Rest relative location of the weapon mesh, for recoil recovery. */
	FVector WeaponMeshRestRelLoc = FVector::ZeroVector;
	bool bWeaponMeshRestCached = false;

	/** Rest relative rotation of the weapon mesh, for gun-pitch aim. */
	FRotator GunBaseRelRot = FRotator::ZeroRotator;

	/** Resolve (and cache) the weapon mesh + muzzle socket for the given pawn. */
	void ResolveWeaponMesh(APawn* Pawn);

	/** Resolve (and cache) the camera + spring arm + base values for the pawn. */
	void ResolveViewComponents(APawn* Pawn);
};
