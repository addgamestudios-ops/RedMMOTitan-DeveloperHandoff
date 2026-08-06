#include "RedImpostorFade.h"

#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"

ARedImpostorFade::ARedImpostorFade()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickInterval = 0.2f;   // distance checks don't need frame rate
}

void ARedImpostorFade::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	FVector ViewLoc = FVector::ZeroVector;
	if (APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0))
	{
		if (PC->PlayerCameraManager)
		{
			ViewLoc = PC->PlayerCameraManager->GetCameraLocation();
		}
	}
	if (ViewLoc.IsNearlyZero())
	{
		return;
	}

	for (const FRedImpostorEntry& Entry : Impostors)
	{
		if (!Entry.Impostor || Entry.HideDistance <= 0.f)
		{
			continue;
		}
		const float Dist = (float)FVector::Dist(ViewLoc, Entry.Impostor->GetActorLocation());
		const bool bCurrentlyHidden = Entry.Impostor->IsHidden();
		if (!bCurrentlyHidden && Dist < Entry.HideDistance)
		{
			Entry.Impostor->SetActorHiddenInGame(true);
		}
		else if (bCurrentlyHidden && Dist > Entry.HideDistance * 1.1f)   // hysteresis: no flicker
		{
			Entry.Impostor->SetActorHiddenInGame(false);
		}
	}
}
