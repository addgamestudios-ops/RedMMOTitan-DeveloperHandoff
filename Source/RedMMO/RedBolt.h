#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "RedBolt.generated.h"

class USceneComponent;
class USphereComponent;
class UStaticMeshComponent;
class UProjectileMovementComponent;
class UNiagaraComponent;
class UNiagaraSystem;
class UParticleSystem;
class UMaterialInterface;
class UMaterialInstanceDynamic;
class UStaticMesh;

/** Small replicated presentation payload so every client renders the authoritative bolt profile. */
USTRUCT()
struct FRedBoltVisualProfile
{
	GENERATED_BODY()

	UPROPERTY()
	FLinearColor Color = FLinearColor::White;

	UPROPERTY()
	float LengthScale = 1.6f;

	UPROPERTY()
	float RadiusScale = 0.07f;

	UPROPERTY()
	bool bOverrideColor = false;

	/** 0 = native fallback, 1 = electric energy orb, 2 = ballistic rifle streak. */
	UPROPERTY()
	uint8 EffectProfile = 0;
};

/** Replicated energy bolt: a stretched glowing-blue shape that flies straight. */
UCLASS()
class REDMMO_API ARedBolt : public AActor
{
	GENERATED_BODY()

public:
	ARedBolt();

	/** Override the bolt's world velocity (ship guns fire fast bolts that inherit ship speed so
	 *  they don't trail behind a fast ship). Call right after spawn. */
	void LaunchWithVelocity(const FVector& WorldVelocity);

	/** Visual/impact profile so rifle shots and ship cannons can share the same bolt class. */
	void ConfigureImpactProfile(float InVisualScale, float InImpactScale, float InCraterRadius, float InDamage);
	/** Tint the tracer beam (BoltColor param on M_BoltTracer). Rifle = neon violet to match its
	 *  muzzle flash; ship keeps the default cyan. */
	void SetBeamColor(const FLinearColor& InColor);

	/** Override the beam's visual size after ConfigureImpactProfile (mesh-scale units: 1.0 = 1m).
	 *  Length rides local X (the travel axis); Radius is the beam thickness (Y=Z). */
	void SetBeamDimensions(float InLengthScale, float InRadiusScale);

	/** Select a paired ProjectilesVol1 projectile + impact profile. Replicated as part of the
	 * visual payload so remote clients never collapse both weapons back to one shared tracer. */
	void SetEffectProfile(uint8 InEffectProfile);

	/** Terrain response profile: rifle shots can be dust-only while ship cannons cut voxels. */
	void ConfigureGroundImpact(bool bInApplyVoxelCrater, bool bInSpawnCraterDecal, bool bInSpawnImpactMark);

	/** Enable a Metal-safe Cascade explosion on impact (GPU-Niagara HeavyImpactFX won't render on Apple Silicon). */
	void SetImpactExplosion(bool bEnable) { bSpawnImpactExplosion = bEnable; }

protected:
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** Visible impact FX spawned where the bolt hits something. */
	UPROPERTY(EditAnywhere, Category = "Red")
	UNiagaraSystem* ImpactFX;

	/** Paired ProjectilesVol1 electric-orb presentation (slot 1 / ENERGY). */
	UPROPERTY(EditAnywhere, Category = "Red|Weapon Profiles")
	UNiagaraSystem* EnergyProjectileFX;

	UPROPERTY(EditAnywhere, Category = "Red|Weapon Profiles")
	UNiagaraSystem* EnergyImpactFX;

	/** Paired ProjectilesVol1 compact ballistic presentation (slot 2 / RIFLE). */
	UPROPERTY(EditAnywhere, Category = "Red|Weapon Profiles")
	UNiagaraSystem* RifleProjectileFX;

	UPROPERTY(EditAnywhere, Category = "Red|Weapon Profiles")
	UNiagaraSystem* RifleImpactFX;

	/** Cascade projectile FX that flies WITH the bolt. CPU-sim Cascade renders on Apple Silicon/Metal,
	 *  unlike GPU Niagara — this is the visible "cool bolt" from the ProjectilesVol1 pack. */
	UPROPERTY(EditAnywhere, Category = "Red")
	UParticleSystem* ProjectileFX;

	/** Metal-safe Cascade explosion spawned at the impact when bSpawnImpactExplosion is set (ship cannons). */
	UPROPERTY(EditAnywhere, Category = "Red")
	UParticleSystem* ImpactExplosionCascade;

	/** When true, spawn ImpactExplosionCascade on any blocking hit (ship cannon blast). */
	UPROPERTY(EditAnywhere, Category = "Red")
	bool bSpawnImpactExplosion = false;

	/** Extra heavy burst for ship-scale impacts. */
	UPROPERTY(EditAnywhere, Category = "Red")
	UNiagaraSystem* HeavyImpactFX;

	/** Sand/dust kick-up for ground hits. */
	UPROPERTY(EditAnywhere, Category = "Red")
	UNiagaraSystem* SurfaceDustFX;

	/** Short-lived visible crater mark on terrain hits. */
	UPROPERTY(EditAnywhere, Category = "Red")
	UMaterialInterface* CraterDecalMaterial;

	/** Fallback physical impact mark for surfaces that do not receive deferred decals. */
	UPROPERTY(EditAnywhere, Category = "Red")
	UStaticMesh* ImpactMarkMesh;

	UPROPERTY(EditAnywhere, Category = "Red")
	UMaterialInterface* ImpactMarkMaterial;

	/** Server-authoritative damage dealt to the hit actor. */
	UPROPERTY(EditAnywhere, Category = "Red")
	float Damage = 10.f;

	UPROPERTY(EditAnywhere, Category = "Red")
	float ImpactFXScale = 1.f;

	UPROPERTY(EditAnywhere, Category = "Red")
	float SurfaceDustScale = 1.15f;

	UPROPERTY(EditAnywhere, Category = "Red")
	float CraterRadius = 90.f;

	UPROPERTY(EditAnywhere, Category = "Red")
	float CraterLifeSpan = 18.f;

	/** Runtime VibeVoxel crater stamp. This is the real terrain cut; decals/meshes are just visual feedback. */
	UPROPERTY(EditAnywhere, Category = "Red|Voxel")
	bool bApplyVoxelCrater = false;

	UPROPERTY(EditAnywhere, Category = "Red|Voxel")
	bool bSpawnCraterDecal = false;

	UPROPERTY(EditAnywhere, Category = "Red|Voxel")
	bool bSpawnImpactMark = false;

	UPROPERTY(EditAnywhere, Category = "Red|Voxel")
	bool bSpawnHeavyImpactFX = false;

	UPROPERTY(EditAnywhere, Category = "Red|Voxel")
	float VoxelCraterLifeSpan = 240.f;

	/** Mining: a ground crater drops a depth-typed resource pickup the player can collect. */
	UPROPERTY(EditAnywhere, Category = "Red|Voxel|Mining")
	bool bDropMinedResource = true;

	/** Planet surface radius reference (cm) used to classify mine depth into resource layers. */
	UPROPERTY(EditAnywhere, Category = "Red|Voxel|Mining")
	float PlanetBaseRadius = 381406.f;

	/** Planet center (world). Default origin matches the VoxelWorld at (0,0,0). */
	UPROPERTY(EditAnywhere, Category = "Red|Voxel|Mining")
	FVector PlanetCenter = FVector::ZeroVector;

protected:
	UFUNCTION()
	void OnHit(UPrimitiveComponent* HitComp, AActor* OtherActor, UPrimitiveComponent* OtherComp,
		FVector NormalImpulse, const FHitResult& Hit);

	/** Server-owned impact result, fanned out so every player sees the same hit location and FX. */
	UFUNCTION(NetMulticast, Reliable)
	void MulticastImpactCosmetics(FVector_NetQuantize ImpactPoint, FVector_NetQuantizeNormal ImpactNormal,
		uint8 InEffectProfile, float InProfileScale, float InSurfaceDustScale, float InCraterRadius,
		bool bInSpawnHeavyImpactFX, bool bInSpawnImpactExplosion,
		bool bInSpawnCraterDecal, bool bInSpawnImpactMark, bool bHitPawn);

	UFUNCTION()
	void OnRep_BeamVisualProfile();

private:
	void ApplyBeamVisualProfile();
	UNiagaraSystem* ResolveProjectileFX() const;
	UNiagaraSystem* ResolveImpactFX() const;
	void DisableAfterImpact();

	bool CanSpawnCraterDecal() const;

	void SpawnVoxelCraterStamp(const FHitResult& Hit);

	/** Drop a resource pickup whose type depends on how deep below the surface the hit landed. */
	void SpawnMinedResource(const FHitResult& Hit);

	/** Sphere collision = physics root (drives OnHit). ProjectileMovement updates this. */
	UPROPERTY(VisibleAnywhere)
	USphereComponent* Collision;

	UPROPERTY(VisibleAnywhere)
	UStaticMeshComponent* Mesh;

	/** Authoritative color and dimensions; applied through OnRep on remote copies. */
	UPROPERTY(ReplicatedUsing = OnRep_BeamVisualProfile)
	FRedBoltVisualProfile BeamVisualProfile;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> BeamMaterialInstance;

	/** ProjectilesVol1 visual attached to the native swept-collision bolt. This keeps RED's reliable
	 *  hit behavior while using the imported pack's authored projectile art. */
	UPROPERTY(VisibleAnywhere)
	UNiagaraComponent* ProjectileNiagara;

	UPROPERTY(VisibleAnywhere)
	UProjectileMovementComponent* Movement;

	bool bImpactProcessed = false;
};
