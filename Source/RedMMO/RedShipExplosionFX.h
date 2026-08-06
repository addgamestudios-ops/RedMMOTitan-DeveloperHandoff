#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "RedShipExplosionFX.generated.h"

class UMaterialInterface;
class UParticleSystem;
class UPointLightComponent;
class USceneComponent;
class UAudioComponent;
class USoundBase;
class UStaticMesh;
class UStaticMeshComponent;

/**
 * Short-lived replicated presentation actor for a destroyed fighter or shuttle.
 *
 * The authoritative vehicle spawns one of these before it shuts down. Every client then
 * creates the same pack-native Cascade bursts plus local Chaos rigid-body debris. Debris is
 * deliberately cosmetic: it can bounce off the world, but it cannot damage or push players
 * and does not add a replicated physics burden to a PvP match.
 */
UCLASS(NotBlueprintable, Transient)
class REDMMO_API ARedShipExplosionFX : public AActor
{
	GENERATED_BODY()

public:
	ARedShipExplosionFX();

	/** Spawn a ship-sized effect from authority. Returns null on clients or invalid worlds. */
	static ARedShipExplosionFX* SpawnForDestroyedShip(AActor* DestroyedShip);
	/** Spawn a shorter finite-relevancy effect for a depleted mineable asteroid. */
	static ARedShipExplosionFX* SpawnForDepletedAsteroid(AActor* DepletedAsteroid,
		float StartedServerTimeSeconds, float ReplayWindowSeconds);

	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** Local audio-device proof retained after the short one-shot component auto-destroys. */
	bool DidStartLocalExplosionSound() const { return bLocalExplosionSoundStarted; }
	/** Exact loaded cue identity used by runtime acceptance; empty when the asset failed to load. */
	FString GetExplosionSoundAssetPath() const;

private:
	static ARedShipExplosionFX* SpawnForDestroyedActor(AActor* DestroyedActor,
		float MinEffectScale, float MaxEffectScale, bool bInAlwaysRelevant,
		float NetCullDistanceCm, float LifeSpanSeconds,
		float StartedServerTimeSeconds, float ReplayWindowSeconds);
	void TryStartPresentation();
	void SpawnPrimaryCosmetics();
	void SpawnSecondaryBurst();
	void SpawnChaosDebris();

	UPROPERTY(VisibleAnywhere)
	TObjectPtr<USceneComponent> SceneRoot;

	/** Guaranteed renderer-independent flash behind the authored particle lights. */
	UPROPERTY(VisibleAnywhere)
	TObjectPtr<UPointLightComponent> FlashLight;

	/** Red/orange stylized fire, smoke, glow sphere and radial boom wave. */
	UPROPERTY()
	TObjectPtr<UParticleSystem> PrimaryExplosion;

	/** Smaller purple-hot secondary core for a staged detonation. */
	UPROPERTY()
	TObjectPtr<UParticleSystem> SecondaryExplosion;

	UPROPERTY()
	TObjectPtr<USoundBase> ExplosionSound;

	UPROPERTY(Transient)
	TObjectPtr<UAudioComponent> ExplosionSoundComponent;

	UPROPERTY()
	TObjectPtr<UStaticMesh> DebrisMesh;

	UPROPERTY()
	TObjectPtr<UMaterialInterface> DarkDebrisMaterial;

	UPROPERTY()
	TObjectPtr<UMaterialInterface> HotDebrisMaterial;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMeshComponent>> DebrisPieces;

	/** Initial-bunch values selected from the destroyed craft's bounds and velocity. */
	UPROPERTY(Replicated)
	float EffectScale = 5.f;

	UPROPERTY(Replicated)
	FVector SourceVelocity = FVector::ZeroVector;

	/** Nonzero for replay-bounded transient effects such as asteroid depletion. */
	UPROPERTY(Replicated)
	float PresentationStartedServerTimeSeconds = 0.f;

	UPROPERTY(Replicated)
	float PresentationReplayWindowSeconds = 0.f;

	FTimerHandle SecondaryBurstTimer;
	FTimerHandle PresentationRetryTimer;
	bool bPresentationStarted = false;
	bool bLocalExplosionSoundStarted = false;
	float ElapsedSeconds = 0.f;
	float PeakLightIntensity = 0.f;
};
