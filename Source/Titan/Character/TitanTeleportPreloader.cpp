// Copyright Epic Games, Inc. All Rights Reserved.


#include "Character/TitanTeleportPreloader.h"
#include "Components/WorldPartitionStreamingSourceComponent.h"
#include "TitanLogChannels.h"
#include "Engine/World.h"
#include "TimerManager.h"

ATitanTeleportPreloader::ATitanTeleportPreloader()
{
 	PrimaryActorTick.bCanEverTick = true;
	
	// create the streaming source component
	StreamingSource = CreateDefaultSubobject<UWorldPartitionStreamingSourceComponent>(TEXT("Streaming Source"));

	check(StreamingSource);

	// set streaming source priority to highest
	StreamingSource->Priority = EStreamingSourcePriority::Highest;
}

void ATitanTeleportPreloader::BeginPlay()
{
	Super::BeginPlay();

	UE_LOG(LogTitan, Error, TEXT("Preloader Created"));

	// enable the streaming source
	StreamingSource->EnableStreamingSource();
	
	// set the timer to check if the preload is complete
	GetWorld()->GetTimerManager().SetTimer(PreloadTimer, this, &ATitanTeleportPreloader::CheckPreload, 0.5f, true);
}

void ATitanTeleportPreloader::EndPlay(EEndPlayReason::Type EndPlayReason)
{
	Super::EndPlay(EndPlayReason);

	// ensure the timer is cleared
	GetWorld()->GetTimerManager().ClearTimer(PreloadTimer);
}

void ATitanTeleportPreloader::CheckPreload()
{
	UE_LOG(LogTitan, Error, TEXT("Checking Preload"));

	// are we done streaming?
	if (StreamingSource->IsStreamingCompleted())
	{
		UE_LOG(LogTitan, Error, TEXT("Preload Complete"));

		// call the delegate
		OnPreloadComplete.ExecuteIfBound();

		// destroy the preloader
		Destroy();
	}
}