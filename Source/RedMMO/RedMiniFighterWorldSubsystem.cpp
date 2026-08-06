#include "RedMiniFighterWorldSubsystem.h"

#include "Engine/World.h"
#include "EngineUtils.h"
#include "RedMiniFighter.h"
#include "RedShuttleBase.h"
#include "TimerManager.h"

DEFINE_LOG_CATEGORY_STATIC(LogRedMiniFighterSpawner, Log, All);

bool URedMiniFighterWorldSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	if (!Super::ShouldCreateSubsystem(Outer))
	{
		return false;
	}
	const UWorld* World = Cast<UWorld>(Outer);
	return World && (World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE);
}

void URedMiniFighterWorldSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	if (!InWorld.IsGameWorld() || InWorld.GetNetMode() == NM_Client)
	{
		return;
	}

	// A short delay lets level actors and Blueprint component hierarchies finish BeginPlay first.
	InWorld.GetTimerManager().SetTimer(SpawnRetryTimer, this,
		&URedMiniFighterWorldSubsystem::TryEnsureRearBayFighter,
		1.0f, true, 0.75f);
}

void URedMiniFighterWorldSubsystem::Deinitialize()
{
	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().ClearTimer(SpawnRetryTimer);
	}
	Super::Deinitialize();
}

void URedMiniFighterWorldSubsystem::TryEnsureRearBayFighter()
{
	UWorld* World = GetWorld();
	if (!World || !World->IsGameWorld() || World->GetNetMode() == NM_Client)
	{
		return;
	}

	for (TActorIterator<ARedMiniFighter> It(World); It; ++It)
	{
		if (IsValid(*It) && !It->IsActorBeingDestroyed())
		{
			World->GetTimerManager().ClearTimer(SpawnRetryTimer);
			return;
		}
	}

	AActor* DockParent = FindPreferredDockParent();
	if (!DockParent)
	{
		// World Partition may deliver the shuttle after world BeginPlay. Retry for two minutes.
		if (++SpawnAttempts >= 120)
		{
			World->GetTimerManager().ClearTimer(SpawnRetryTimer);
			UE_LOG(LogRedMiniFighterSpawner, Warning,
				TEXT("No replicated ARedShuttleBase/carrier appeared; mini fighter was not spawned"));
		}
		return;
	}

	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	ARedMiniFighter* Fighter = World->SpawnActor<ARedMiniFighter>(
		ARedMiniFighter::StaticClass(), DockParent->GetActorTransform(), Params);
	if (!Fighter || !Fighter->DockToParent(DockParent))
	{
		if (Fighter)
		{
			Fighter->Destroy();
		}
		UE_LOG(LogRedMiniFighterSpawner, Warning,
			TEXT("Rear-bay mini fighter spawn/dock failed; retrying"));
		return;
	}

	World->GetTimerManager().ClearTimer(SpawnRetryTimer);
	UE_LOG(LogRedMiniFighterSpawner, Display,
		TEXT("Spawned replicated mini fighter %s on %s"),
		*GetNameSafe(Fighter), *GetNameSafe(DockParent));
}

AActor* URedMiniFighterWorldSubsystem::FindPreferredDockParent() const
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return nullptr;
	}

	for (TActorIterator<ARedShuttleBase> It(World); It; ++It)
	{
		ARedShuttleBase* Shuttle = *It;
		if (IsValid(Shuttle) && !Shuttle->IsActorBeingDestroyed()
			&& Shuttle->GetIsReplicated() && Shuttle->GetRootComponent()
			&& Shuttle->GetHealthFraction() > 0.f)
		{
			return Shuttle;
		}
	}

	// Optional future carrier support without coupling this first pass to a specific pack class.
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		AActor* Candidate = *It;
		if (!IsValid(Candidate) || Candidate->IsActorBeingDestroyed()
			|| !Candidate->GetIsReplicated() || !Candidate->GetRootComponent())
		{
			continue;
		}
		const FString Identity = Candidate->GetName() + TEXT(" ") + Candidate->GetClass()->GetName();
		if (Identity.Contains(TEXT("Carrier"), ESearchCase::IgnoreCase))
		{
			return Candidate;
		}
	}
	return nullptr;
}
