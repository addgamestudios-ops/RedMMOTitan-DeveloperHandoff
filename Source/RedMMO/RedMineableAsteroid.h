#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "RedResourcePickup.h"
#include "RedMineableAsteroid.generated.h"

class UStaticMeshComponent;
class UStaticMesh;

UENUM(BlueprintType)
enum class ERedMineableAsteroidDepletionPhase : uint8
{
	Active,
	Depleting,
	Depleted
};

/** Atomic initial-bunch state for deterministic depletion and late-join presentation. */
USTRUCT(BlueprintType)
struct FRedMineableAsteroidDepletionState
{
	GENERATED_BODY()

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "Red|Mining")
	ERedMineableAsteroidDepletionPhase Phase = ERedMineableAsteroidDepletionPhase::Active;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "Red|Mining")
	float StartedServerTimeSeconds = 0.f;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "Red|Mining")
	float PresentationDurationSeconds = 0.f;

	/** Internal unsigned revision for stale timer rejection; intentionally not Blueprint-exposed. */
	UPROPERTY(VisibleInstanceOnly, Category = "Red|Mining")
	uint32 Sequence = 0;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "Red|Mining")
	bool bRewardSpawned = false;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "Red|Mining")
	bool bRewardGranted = false;
};

/** Lightweight replicated ore rock used as an actual target among the decorative asteroid field. */
UCLASS(NotPlaceable)
class REDMMO_API ARedMineableAsteroid : public AActor
{
	GENERATED_BODY()

public:
	ARedMineableAsteroid();

	/**
	 * Assign the immutable namespaced identity used by save, replication,
	 * telemetry, and evidence. Authority may initialize it exactly once.
	 */
	bool InitializeStableMemberId(FName InStableMemberId);
	FName GetStableMemberId() const { return StableMemberId; }

	float RegisterMiningHit(float MiningStrength, AActor* MiningInstigator);
	/** Limits presentation range without changing replicated relevance or depletion state. */
	void SetPresentationCullDistance(float CullDistanceCm);
	float GetPresentationCullDistance() const { return PresentationCullDistanceCm; }

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Replicated, Category = "Red|Mining")
	float OreCapacity = 6000.f;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, ReplicatedUsing = OnRep_OreRemaining,
		Category = "Red|Mining")
	float OreRemaining = 6000.f;

	/** Deterministic replicated choice from the purchased mining-asteroid mesh set. */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, ReplicatedUsing = OnRep_VisualVariant,
		Category = "Red|Mining")
	uint8 VisualVariant = 0;

	/** Replicated because PrimitiveComponent draw distance is local component state. */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, ReplicatedUsing = OnRep_PresentationCullDistance,
		Category = "Red|Mining")
	float PresentationCullDistanceCm = 0.f;

	/** One-way authority-owned state retained on the actor for late joiners. */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, ReplicatedUsing = OnRep_DepletionState,
		Category = "Red|Mining")
	FRedMineableAsteroidDepletionState DepletionState;

	/** Time the intact mesh remains readable after collision shuts down. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Red|Mining|Depletion",
		meta = (ClampMin = "0.5", ClampMax = "8.0"))
	float DepletionPresentationSeconds = 2.f;

	/** Exactly one replicated collectible is spawned when this asteroid reaches zero. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Red|Mining|Depletion")
	ERedResourceType DepletionRewardType = ERedResourceType::Iron;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Red|Mining|Depletion",
		meta = (ClampMin = "1", ClampMax = "100"))
	int32 DepletionRewardAmount = 6;

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	virtual bool IsNetRelevantFor(const AActor* RealViewer, const AActor* ViewTarget,
		const FVector& SrcLocation) const override;

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Mining")
	TObjectPtr<UStaticMeshComponent> RockMesh;

	UPROPERTY()
	TArray<TObjectPtr<UStaticMesh>> AsteroidMeshes;

private:
	/** Initial-bunch identity; never infer durable identity from actor name or spawn order. */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Replicated, Category = "Red|Mining",
		meta = (AllowPrivateAccess = "true"))
	FName StableMemberId = NAME_None;

	UFUNCTION()
	void OnRep_OreRemaining();
	UFUNCTION()
	void OnRep_VisualVariant();
	UFUNCTION()
	void OnRep_PresentationCullDistance();
	UFUNCTION()
	void OnRep_DepletionState();
	void ApplyVisualVariant();
	void ApplyPresentationCullDistance();
	void ApplyDepletionPresentation();
	void BeginDepletion(AActor* MiningInstigator);
	void FinishDepletion(uint32 ExpectedSequence);
	void TrySpawnDepletionReward(AActor* MiningInstigator);
	float GetSynchronizedServerTimeSeconds() const;

	FTimerHandle DepletionTimer;
};
