// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "TitanTeleportPreloader.generated.h"

class UWorldPartitionStreamingSourceComponent;

DECLARE_DYNAMIC_DELEGATE(FOnTeleportPreloadComplete);

/**
 *  ATitanTeleportPreloader
 *  A basic actor that ensures World Partition loads the target area of the level prior to teleporting
 */
UCLASS()
class TITAN_API ATitanTeleportPreloader : public AActor
{
	GENERATED_BODY()
	
public:	
	// Sets default values for this actor's properties
	ATitanTeleportPreloader();

private:

	/** WP Streaming source */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components", meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UWorldPartitionStreamingSourceComponent> StreamingSource;

protected:

	/** True while the actor is actively preloading the level */
	bool bPreloading = false;

	/** Timer to keep track of preloading */
	FTimerHandle PreloadTimer;

protected:
	
	/** Initialization */
	virtual void BeginPlay() override;

	/** Cleanup */
	virtual void EndPlay(EEndPlayReason::Type EndPlayReason) override;

	/** Called from a timer to check if the level preload has completed */
	void CheckPreload();

public:

	/** Delegate to call when the level preload is complete */
	FOnTeleportPreloadComplete OnPreloadComplete;

};
