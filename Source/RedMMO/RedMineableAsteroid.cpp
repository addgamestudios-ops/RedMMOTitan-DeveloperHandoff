#include "RedMineableAsteroid.h"

#include "RedPlanetPresentationTuning.h"
#include "RedPlayerCharacter.h"
#include "RedShipExplosionFX.h"

#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/Pawn.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/Crc.h"
#include "Net/UnrealNetwork.h"
#include "TimerManager.h"
#include "UObject/ConstructorHelpers.h"

DEFINE_LOG_CATEGORY_STATIC(LogRedMineableAsteroid, Log, All);

ARedMineableAsteroid::ARedMineableAsteroid()
{
	PrimaryActorTick.bCanEverTick = false;
	bReplicates = true;
	// The belt is static. Replicating transforms forever made every ore rock globally relevant;
	// clients only need its initial spawn transform plus the small ore/variant state below.
	SetReplicateMovement(false);
	bAlwaysRelevant = false;
	SetNetCullDistanceSquared(FMath::Square(5000000.f));
	SetNetUpdateFrequency(2.f);
	SetMinNetUpdateFrequency(0.5f);
	SetCanBeDamaged(true);
	Tags.Add(TEXT("RedMineableSpaceAsteroid"));
	PresentationCullDistanceCm = RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm;

	RockMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("RockMesh"));
	SetRootComponent(RockMesh);
	static ConstructorHelpers::FObjectFinder<UStaticMesh> LargeAsteroid(
		TEXT("/Game/AsteroidSpaceport/Meshes/Asteroids/SM_Mining_Asteroid_Large.SM_Mining_Asteroid_Large"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> MediumAsteroid(
		TEXT("/Game/AsteroidSpaceport/Meshes/Asteroids/SM_Mining_Asteroid_Med.SM_Mining_Asteroid_Med"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> SmallAsteroid(
		TEXT("/Game/AsteroidSpaceport/Meshes/Asteroids/SM_Mining_Asteroid_Small.SM_Mining_Asteroid_Small"));
	if (LargeAsteroid.Succeeded())
	{
		AsteroidMeshes.Add(LargeAsteroid.Object);
	}
	if (MediumAsteroid.Succeeded())
	{
		AsteroidMeshes.Add(MediumAsteroid.Object);
	}
	if (SmallAsteroid.Succeeded())
	{
		AsteroidMeshes.Add(SmallAsteroid.Object);
	}
	if (AsteroidMeshes.Num() == 0)
	{
		static ConstructorHelpers::FObjectFinder<UStaticMesh> FallbackRock(
			TEXT("/Game/StylizedDesertOasis/Meshes/Rocks/SM_Boulder_03.SM_Boulder_03"));
		if (FallbackRock.Succeeded())
		{
			AsteroidMeshes.Add(FallbackRock.Object);
		}
	}
	ApplyVisualVariant();
	RockMesh->SetMobility(EComponentMobility::Movable);
	RockMesh->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	RockMesh->SetCollisionObjectType(ECC_WorldStatic);
	RockMesh->SetCollisionResponseToAllChannels(ECR_Block);
	RockMesh->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore);
	RockMesh->SetGenerateOverlapEvents(false);
	RockMesh->SetCanEverAffectNavigation(false);
	// Primitive-component draw distance is not replicated. Apply the shared deep-space
	// presentation limit in the constructor so dedicated/listen servers and every remote
	// client get the same cutoff before the first rendered frame.
	ApplyPresentationCullDistance();
}

bool ARedMineableAsteroid::IsNetRelevantFor(
	const AActor* RealViewer,
	const AActor* ViewTarget,
	const FVector& SrcLocation) const
{
	const bool bBaseRelevant =
		Super::IsNetRelevantFor(RealViewer, ViewTarget, SrcLocation);
	if (bBaseRelevant
		|| DepletionState.Phase
			!= ERedMineableAsteroidDepletionPhase::Depleted)
	{
		return bBaseRelevant;
	}

	// AActor rejects hidden actors with collision disabled before evaluating their distance.
	// Depleted asteroids deliberately have both traits, but retain their replicated terminal
	// state for late joiners. Preserve the existing 50 km distance gate without making every
	// field member globally relevant or resurrecting invisible collision.
	return RootComponent && IsWithinNetRelevancyDistance(SrcLocation);
}

void ARedMineableAsteroid::BeginPlay()
{
	Super::BeginPlay();
	if (HasAuthority())
	{
		OreCapacity = FMath::Max(1.f, OreCapacity);
		OreRemaining = OreCapacity;
		DepletionState = FRedMineableAsteroidDepletionState();
		if (AsteroidMeshes.Num() > 0)
		{
			const FString VariantIdentity = StableMemberId.IsNone()
				? GetName()
				: StableMemberId.ToString();
			VisualVariant = static_cast<uint8>(
				FCrc::StrCrc32(*VariantIdentity)
				% static_cast<uint32>(AsteroidMeshes.Num()));
		}
	}
	ApplyVisualVariant();
	ApplyDepletionPresentation();
}

void ARedMineableAsteroid::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	GetWorldTimerManager().ClearTimer(DepletionTimer);
	Super::EndPlay(EndPlayReason);
}

bool ARedMineableAsteroid::InitializeStableMemberId(const FName InStableMemberId)
{
	if (!HasAuthority() || InStableMemberId.IsNone())
	{
		UE_LOG(LogRedMineableAsteroid, Error,
			TEXT("Rejected invalid stable-member initialization for %s authority=%d id=%s"),
			*GetName(), HasAuthority() ? 1 : 0, *InStableMemberId.ToString());
		return false;
	}
	if (!StableMemberId.IsNone())
	{
		const bool bMatchesExisting = StableMemberId == InStableMemberId;
		if (!bMatchesExisting)
		{
			UE_LOG(LogRedMineableAsteroid, Error,
				TEXT("Rejected stable-member reassignment for %s existing=%s requested=%s"),
				*GetName(), *StableMemberId.ToString(), *InStableMemberId.ToString());
		}
		return bMatchesExisting;
	}

	StableMemberId = InStableMemberId;
	if (HasActorBegunPlay())
	{
		ForceNetUpdate();
	}
	return true;
}

float ARedMineableAsteroid::RegisterMiningHit(const float MiningStrength, AActor* MiningInstigator)
{
	if (!HasAuthority()
		|| DepletionState.Phase != ERedMineableAsteroidDepletionPhase::Active
		|| OreRemaining <= 0.f
		|| MiningStrength <= 0.f)
	{
		return 0.f;
	}
	const float Extracted = FMath::Min(OreRemaining, MiningStrength * 18.f);
	OreRemaining = FMath::Max(0.f, OreRemaining - Extracted);
	if (OreRemaining <= 0.f)
	{
		BeginDepletion(MiningInstigator);
	}
	FlushNetDormancy();
	ForceNetUpdate();
	UE_LOG(LogRedMineableAsteroid, Display,
		TEXT("Asteroid mined: %s by %s extracted=%.0f remaining=%.0f"),
		*GetName(), *GetNameSafe(MiningInstigator), Extracted, OreRemaining);
	return Extracted;
}

void ARedMineableAsteroid::SetPresentationCullDistance(const float CullDistanceCm)
{
	PresentationCullDistanceCm = FMath::Max(0.f, CullDistanceCm);
	ApplyPresentationCullDistance();
	if (HasAuthority())
	{
		ForceNetUpdate();
	}
}

void ARedMineableAsteroid::OnRep_OreRemaining()
{
	// Ore and the atomic depletion payload can arrive in either RepNotify order. Presentation
	// is always derived from the authority-owned payload, never directly from zero ore.
	ApplyDepletionPresentation();
}

void ARedMineableAsteroid::OnRep_VisualVariant()
{
	ApplyVisualVariant();
}

void ARedMineableAsteroid::OnRep_PresentationCullDistance()
{
	ApplyPresentationCullDistance();
}

void ARedMineableAsteroid::OnRep_DepletionState()
{
	ApplyDepletionPresentation();
}

void ARedMineableAsteroid::ApplyVisualVariant()
{
	if (!RockMesh || AsteroidMeshes.Num() == 0)
	{
		return;
	}
	RockMesh->SetStaticMesh(AsteroidMeshes[
		static_cast<int32>(VisualVariant) % AsteroidMeshes.Num()]);
}

void ARedMineableAsteroid::ApplyPresentationCullDistance()
{
	if (RockMesh)
	{
		RockMesh->SetCullDistance(FMath::Max(0.f, PresentationCullDistanceCm));
	}
}

float ARedMineableAsteroid::GetSynchronizedServerTimeSeconds() const
{
	if (const UWorld* World = GetWorld())
	{
		if (const AGameStateBase* GameState = World->GetGameState())
		{
			return static_cast<float>(GameState->GetServerWorldTimeSeconds());
		}
		// Authority defines the timestamp and may use its own clock before GameState exists.
		// A client must never compare that timestamp to an unrelated local world clock.
		return HasAuthority() ? World->GetTimeSeconds() : -1.f;
	}
	return -1.f;
}

void ARedMineableAsteroid::ApplyDepletionPresentation()
{
	GetWorldTimerManager().ClearTimer(DepletionTimer);

	if (DepletionState.Phase == ERedMineableAsteroidDepletionPhase::Active)
	{
		SetActorHiddenInGame(false);
		SetActorEnableCollision(true);
		return;
	}

	// Mining stops immediately at zero on every peer. Only the intact presentation persists.
	SetActorEnableCollision(false);
	if (DepletionState.Phase == ERedMineableAsteroidDepletionPhase::Depleted)
	{
		SetActorHiddenInGame(true);
		return;
	}

	SetActorHiddenInGame(false);
	const float SynchronizedNow = GetSynchronizedServerTimeSeconds();
	if (SynchronizedNow < 0.f)
	{
		// Initial actor state can precede GameState on a joining client. Keep collision off and
		// retry briefly instead of displaying a full delay against an unrelated local clock.
		GetWorldTimerManager().SetTimer(DepletionTimer, this,
			&ARedMineableAsteroid::ApplyDepletionPresentation, 0.05f, false);
		return;
	}
	const float Elapsed = FMath::Max(
		0.f, SynchronizedNow - DepletionState.StartedServerTimeSeconds);
	const float Remaining = FMath::Max(
		0.f, DepletionState.PresentationDurationSeconds - Elapsed);
	if (Remaining <= KINDA_SMALL_NUMBER)
	{
		FinishDepletion(DepletionState.Sequence);
		return;
	}

	FTimerDelegate FinishDelegate;
	FinishDelegate.BindUObject(this, &ARedMineableAsteroid::FinishDepletion,
		DepletionState.Sequence);
	GetWorldTimerManager().SetTimer(DepletionTimer, FinishDelegate, Remaining, false);
}

void ARedMineableAsteroid::BeginDepletion(AActor* MiningInstigator)
{
	if (!HasAuthority()
		|| DepletionState.Phase != ERedMineableAsteroidDepletionPhase::Active)
	{
		return;
	}

	OreRemaining = 0.f;
	DepletionState.Phase = ERedMineableAsteroidDepletionPhase::Depleting;
	DepletionState.StartedServerTimeSeconds = GetSynchronizedServerTimeSeconds();
	DepletionState.PresentationDurationSeconds = FMath::Clamp(
		DepletionPresentationSeconds, 0.5f, 8.f);
	++DepletionState.Sequence;
	ApplyDepletionPresentation();

	TrySpawnDepletionReward(MiningInstigator);
	FlushNetDormancy();
	ForceNetUpdate();

	UE_LOG(LogRedMineableAsteroid, Display,
		TEXT("Asteroid depletion started: %s sequence=%u delay=%.2f rewardSpawned=%d rewardGranted=%d"),
		*GetName(), DepletionState.Sequence,
		DepletionState.PresentationDurationSeconds,
		DepletionState.bRewardSpawned ? 1 : 0,
		DepletionState.bRewardGranted ? 1 : 0);
}

void ARedMineableAsteroid::FinishDepletion(const uint32 ExpectedSequence)
{
	if (DepletionState.Sequence != ExpectedSequence
		|| DepletionState.Phase != ERedMineableAsteroidDepletionPhase::Depleting)
	{
		return;
	}

	if (!HasAuthority())
	{
		// A client may reach the synchronized deadline before the final replicated payload.
		// Hide locally but never mutate the authoritative state or spawn any artifact.
		SetActorHiddenInGame(true);
		SetActorEnableCollision(false);
		return;
	}

	DepletionState.Phase = ERedMineableAsteroidDepletionPhase::Depleted;
	++DepletionState.Sequence;
	ApplyDepletionPresentation();

	// Hide the intact rock before starting destruction presentation. Spawning this at zero ore
	// left the explosion and Chaos debris occluded behind the deliberately retained two-second
	// transition mesh. The replicated actor remains finite-range and its rigid debris is cosmetic.
	float ExplosionStartedServerTimeSeconds = GetSynchronizedServerTimeSeconds();
	if (ExplosionStartedServerTimeSeconds < 0.f && GetWorld())
	{
		ExplosionStartedServerTimeSeconds = GetWorld()->GetTimeSeconds();
	}
	ARedShipExplosionFX::SpawnForDepletedAsteroid(
		this, ExplosionStartedServerTimeSeconds, 0.5f);

	FlushNetDormancy();
	ForceNetUpdate();
	UE_LOG(LogRedMineableAsteroid, Display,
		TEXT("Asteroid depletion finished: %s sequence=%u rewardSpawned=%d rewardGranted=%d"),
		*GetName(), DepletionState.Sequence,
		DepletionState.bRewardSpawned ? 1 : 0,
		DepletionState.bRewardGranted ? 1 : 0);
}

void ARedMineableAsteroid::TrySpawnDepletionReward(AActor* MiningInstigator)
{
	if (!HasAuthority()
		|| DepletionState.bRewardSpawned
		|| DepletionState.bRewardGranted
		|| !GetWorld())
	{
		return;
	}

	ARedPlayerCharacter* RewardPlayer = Cast<ARedPlayerCharacter>(MiningInstigator);
	if (!RewardPlayer && IsValid(MiningInstigator))
	{
		RewardPlayer = Cast<ARedPlayerCharacter>(MiningInstigator->GetInstigator());
	}
	const int32 RewardAmount = FMath::Clamp(DepletionRewardAmount, 1, 100);
	if (IsValid(RewardPlayer) && !RewardPlayer->bIsEnemy)
	{
		RewardPlayer->AddResource(DepletionRewardType, RewardAmount);
		DepletionState.bRewardGranted = true;
	}

	FVector BoundsOrigin = GetActorLocation();
	FVector BoundsExtent(200.f);
	GetActorBounds(false, BoundsOrigin, BoundsExtent, true);
	FVector TowardMiner = IsValid(MiningInstigator)
		? (MiningInstigator->GetActorLocation() - BoundsOrigin).GetSafeNormal()
		: FVector::ZeroVector;
	if (TowardMiner.IsNearlyZero())
	{
		TowardMiner = GetActorUpVector().GetSafeNormal();
	}
	if (TowardMiner.IsNearlyZero())
	{
		TowardMiner = FVector::UpVector;
	}

	const FVector SpawnLocation = BoundsOrigin
		+ TowardMiner * (FMath::Max(100.0, BoundsExtent.GetMax()) + 140.0);
	const FTransform SpawnTransform(FQuat::Identity, SpawnLocation);
	ARedResourcePickup* Reward = GetWorld()->SpawnActorDeferred<ARedResourcePickup>(
		ARedResourcePickup::StaticClass(), SpawnTransform, this,
		Cast<APawn>(MiningInstigator), ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
	if (!Reward)
	{
		UE_LOG(LogRedMineableAsteroid, Warning,
			TEXT("Asteroid depletion reward spawn failed: %s"), *GetName());
		return;
	}

	// When an owning player was resolved, inventory is already credited exactly once and this
	// actor is replicated feedback only. Otherwise it remains an authority-collected fallback.
	Reward->InitResource(DepletionRewardType, RewardAmount, FVector::ZeroVector,
		/*bInCollectible=*/!DepletionState.bRewardGranted);
	UGameplayStatics::FinishSpawningActor(Reward, SpawnTransform);
	Reward->ForceNetUpdate();
	DepletionState.bRewardSpawned = true;
}

void ARedMineableAsteroid::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(ARedMineableAsteroid, StableMemberId);
	DOREPLIFETIME(ARedMineableAsteroid, OreCapacity);
	DOREPLIFETIME(ARedMineableAsteroid, OreRemaining);
	DOREPLIFETIME(ARedMineableAsteroid, VisualVariant);
	DOREPLIFETIME(ARedMineableAsteroid, PresentationCullDistanceCm);
	DOREPLIFETIME(ARedMineableAsteroid, DepletionState);
}
