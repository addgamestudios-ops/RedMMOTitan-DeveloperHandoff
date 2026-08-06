// Copyright Epic Games, Inc. All Rights Reserved.


#include "Development/TitanCheatManager.h"
#include "TitanLogChannels.h"
#include "TitanPawn.h"
#include "Components/CapsuleComponent.h"
#include "TitanPlayerController.h"
#include "TitanMoverComponent.h"

void UTitanCheatManager::TitanTeleportPlayer3D(float XCoord, float YCoord, float ZCoord)
{
	// get the player controller
	if (APlayerController* PC = GetOuterAPlayerController())
	{
		// get the pawn
		if(ATitanPawn* Pawn = Cast<ATitanPawn>(PC->GetPawn()))
		{
			// queue the pawn's teleport move
			Pawn->QueueTeleportMove(FVector(XCoord * 100.0f, YCoord * 100.0f, ZCoord * 100.0f));
		}
	}
}

void UTitanCheatManager::TitanTeleportPlayer2D(float XCoord, float YCoord)
{
	// get the player controller
	if (APlayerController* PC = GetOuterAPlayerController())
	{
		// get the pawn
		if (ATitanPawn* Pawn = Cast<ATitanPawn>(PC->GetPawn()))
		{
			// build the trace start and end locations
			FVector Start(XCoord * 100.0f, YCoord * 100.0f, TeleportMaxSweepZ);
			FVector End(XCoord * 100.0f, YCoord * 100.0f, TeleportMinSweepZ);

			UE_LOG(LogTitan, Log, TEXT("Start [%s] End [%s]"), *Start.ToCompactString(), *End.ToCompactString());

			// get the collision capsule size
			float Radius = 0.0f;
			float HalfHeight = 0.0f;

			Pawn->GetPlayerCapsule()->GetScaledCapsuleSize(Radius, HalfHeight);

			UE_LOG(LogTitan, Log, TEXT("Radius [%f] HalfHeight [%f]"), Radius, HalfHeight);
			
			FCollisionShape CollisionCapsule;
			CollisionCapsule.SetCapsule(Radius, HalfHeight);

			// initialize the collision params
			FCollisionQueryParams QueryParams;
			FCollisionResponseParams ResponseParams;
			//Pawn->GetPlayerCapsule()->InitSweepCollisionParams(QueryParams, ResponseParams);
			
			FHitResult Hit;

			// do a downwards sweep to find out the teleport location
			GetWorld()->SweepSingleByChannel(Hit,
				Start, End, Pawn->GetActorQuat(),
				Pawn->GetPlayerCapsule()->GetCollisionObjectType(), CollisionCapsule,
				QueryParams, ResponseParams);

			FVector TeleportLoc;

			// skip the teleport if the sweep started penetrating
			if (!Hit.bStartPenetrating)
			{
				// did we get a collision?
				if (Hit.bBlockingHit)
				{
					// teleport to the collision location
					TeleportLoc = Hit.Location;
				}
				else {

					// otherwise teleport to the sweep endpoint
					TeleportLoc = End;
				}

				UE_LOG(LogTitan, Log, TEXT("Resolved teleport to location [%s]"), *TeleportLoc.ToCompactString());

				// do the teleport
				TitanTeleportPlayer3D(TeleportLoc.X * 0.01f, TeleportLoc.Y * 0.01f, TeleportLoc.Z * 0.01f);
			}
			else {
				UE_LOG(LogTitan, Log, TEXT("Sweep started penetrating, skipping teleport"));
			}

		}
	}
}

void UTitanCheatManager::TitanTeleportPlayerToLandmark(int32 MarkerID)
{
	// TODO
}

void UTitanCheatManager::TitanGetMapCoords()
{
	// get the player controller
	if (APlayerController* PC = GetOuterAPlayerController())
	{
		FVector Loc;

		// get the pawn
		if (ATitanPawn* Pawn = Cast<ATitanPawn>(PC->GetPawn()))
		{
			// report the Pawn's current location
			Loc = Pawn->GetActorLocation() * 0.01f;

			UE_LOG(LogTitan, Warning, TEXT("Map Location [%s]"), *Loc.ToCompactString());
			
			if (GEngine)
			{
				GEngine->AddOnScreenDebugMessage(-1, 15.0f, FColor::Yellow, *Loc.ToCompactString());
			}
			
		}

		
	}
}

void UTitanCheatManager::TitanToggleStamina()
{
	// get the player controller
	if (APlayerController* PC = GetOuterAPlayerController())
	{
		// get the pawn
		if (ATitanPawn* Pawn = Cast<ATitanPawn>(PC->GetPawn()))
		{
			// report the Pawn's current location
			Pawn->GetMoverComponent()->ToggleStamina();

			if (Pawn->GetMoverComponent()->IsStaminaEnabled())
			{
				UE_LOG(LogTitan, Warning, TEXT("Stamina ENABLED"));

				if (GEngine)
				{

					GEngine->AddOnScreenDebugMessage(-1, 15.0f, FColor::Yellow, TEXT("Stamina ENABLED"));
				}
			}
			else {
				UE_LOG(LogTitan, Warning, TEXT("Stamina DISABLED"));

				if (GEngine)
				{

					GEngine->AddOnScreenDebugMessage(-1, 15.0f, FColor::Yellow, TEXT("Stamina DISABLED"));
				}
			}

		}


	}
}

void UTitanCheatManager::TitanBatchTimeLapsePhoto()
{
	// get the player controller
	if (ATitanPlayerController* PC = Cast<ATitanPlayerController>(GetOuterAPlayerController()))
	{
		
		PC->BatchLandmarkPhotos();
	}
}

void UTitanCheatManager::TitanSetTimeOfDayInHours(float Hour)
{
	// get the player controller
	if (ATitanPlayerController* PC = Cast<ATitanPlayerController>(GetOuterAPlayerController()))
	{

		PC->SetTimeOfDayInHours(Hour);
	}
}
