#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "RedResourcePickup.generated.h"

class USphereComponent;
class UStaticMeshComponent;
class UMaterialInstanceDynamic;
class UAudioComponent;
class USoundBase;

/** Mineable resource types, ordered by depth (surface -> deep). */
UENUM(BlueprintType)
enum class ERedResourceType : uint8
{
	Stone   UMETA(DisplayName = "Stone"),
	Iron    UMETA(DisplayName = "Iron"),
	Crystal UMETA(DisplayName = "Crystal")
};

/**
 * A collectible resource chunk dropped when the player mines into the planet.
 * Spins + bobs above the ground, glows in its type color, and is gathered by
 * walking over it (sphere overlap -> ARedPlayerCharacter::AddResource).
 * Fully self-contained C++ — no Blueprint asset required.
 */
UCLASS()
class REDMMO_API ARedResourcePickup : public AActor
{
	GENERATED_BODY()

public:
	ARedResourcePickup();

	/** Set the type/amount and orient the bob toward the planet's radial up. Call right after spawn. */
	void InitResource(ERedResourceType InType, int32 InAmount, const FVector& PlanetCenter,
		bool bInCollectible = true);

	/** Maps a depth-below-surface (cm) to the resource type that lives at that layer. */
	static ERedResourceType TypeForDepth(float DepthBelowSurfaceCm);

	/** True only on the local player that actually received this direct-credit receipt. */
	bool DidStartLocalRewardSound() const { return bLocalRewardSoundStarted; }
	/** Exact loaded cue identity used by runtime acceptance; empty when the asset failed to load. */
	FString GetRewardSoundAssetPath() const;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, ReplicatedUsing = OnRep_ResourceDefinition,
		Category = "Red|Resource")
	ERedResourceType ResourceType = ERedResourceType::Stone;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, ReplicatedUsing = OnRep_ResourceDefinition,
		Category = "Red|Resource")
	int32 Amount = 1;

	/** False for a replicated visual receipt when inventory was credited directly. */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, ReplicatedUsing = OnRep_ResourceDefinition,
		Category = "Red|Resource")
	bool bCollectible = true;

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	virtual void OnRep_Instigator() override;

protected:
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	UFUNCTION()
	void OnCollectOverlap(UPrimitiveComponent* OverlappedComp, AActor* OtherActor,
		UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& Sweep);
	UFUNCTION()
	void OnRep_ResourceDefinition();

	UPROPERTY(VisibleAnywhere, Category = "Red|Resource")
	USceneComponent* SceneRoot;

	UPROPERTY(VisibleAnywhere, Category = "Red|Resource")
	UStaticMeshComponent* MeshComp;

	UPROPERTY(VisibleAnywhere, Category = "Red|Resource")
	USphereComponent* CollectSphere;

private:
	UPROPERTY(Transient)
	UMaterialInstanceDynamic* GlowMID = nullptr;

	UPROPERTY()
	TObjectPtr<USoundBase> RewardSound;

	UPROPERTY(Transient)
	TObjectPtr<UAudioComponent> RewardSoundComponent;

	UPROPERTY(ReplicatedUsing = OnRep_ResourceDefinition)
	FVector_NetQuantizeNormal RadialUp = FVector::UpVector;

	bool bConsumed = false;
	bool bLocalRewardSoundStarted = false;
	float TimeAlive = 0.f;

	void ApplyResourcePresentation();
	void ApplyCollectionState();
	void TryStartLocalRewardSound();
	static FLinearColor ColorForType(ERedResourceType Type);
};
