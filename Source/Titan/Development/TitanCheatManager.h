// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/CheatManager.h"
#include "TitanCheatManager.generated.h"

/**
 *  UTitanCheatManager
 *  Main cheat manager class for the Titan Player Controller
 */
UCLASS(Within=TitanPlayerController)
class TITAN_API UTitanCheatManager : public UCheatManager
{
	GENERATED_BODY()

protected:

	float TeleportMinSweepZ = -10000.0f;

	float TeleportMaxSweepZ = 40000.0f;
	
public:

	/** Teleports the player tot he given map coords. */
	UFUNCTION(Exec)
	void TitanTeleportPlayer3D(float XCoord, float YCoord, float ZCoord);

	/** Teleports the player to the given map coords. Casts a ray down from the sky to find the Z coordinate */
	UFUNCTION(Exec)
	void TitanTeleportPlayer2D(float XCoord, float YCoord);

	/** Teleports the player to the landmark with the given ID */
	UFUNCTION(Exec)
	void TitanTeleportPlayerToLandmark(int32 MarkerID);

	/** Prints the current map coordinates to the log. */
	UFUNCTION(Exec)
	void TitanGetMapCoords();

	/** Enables or disables stamina on the player character. */
	UFUNCTION(Exec)
	void TitanToggleStamina();

	/** Batches a round of photos from each landmark on the map */
	UFUNCTION(Exec)
	void TitanBatchTimeLapsePhoto();

	/** Sets the Time of Day */
	UFUNCTION(Exec)
	void TitanSetTimeOfDayInHours(float Hour);
};
