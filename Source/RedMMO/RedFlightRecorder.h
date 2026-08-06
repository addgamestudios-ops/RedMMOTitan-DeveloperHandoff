#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "RedFlightRecorder.generated.h"

/**
 * ALWAYS-ON gameplay black box (game/PIE worlds only): samples the player's controlled pawn
 * every frame into a ~60s ring buffer — position, velocity, movement mode, the sphere-correct
 * anim inputs, anim play rate, and frame time. When something "glitches", dump the buffer and
 * read what actually happened frame by frame instead of reconstructing it from a description.
 * Costs one small struct copy per frame; no allocation after init.
 */
UCLASS()
class REDMMO_API URedFlightRecorder : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(URedFlightRecorder, STATGROUP_Tickables); }

	/** Write the ring buffer to Saved/FlightRecorder/FR_<seconds>.json. Returns the file path. */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|Diagnostics")
	FString DumpToFile();

private:
	struct FSample
	{
		float T = 0.f;            // world seconds
		float Dt = 0.f;           // frame delta
		FVector3f Loc = FVector3f::ZeroVector;
		FVector3f Vel = FVector3f::ZeroVector;
		uint8 MoveMode = 0;       // EMovementMode (255 = pawn is a ship / non-character)
		float GroundSpeed = 0.f;  // ARedPlayerCharacter::AnimGroundSpeed
		float DirDeg = 0.f;       // ARedPlayerCharacter::AnimDirectionDeg
		float RateScale = 1.f;    // mesh GlobalAnimRateScale
	};

	TArray<FSample> Ring;
	int32 Head = 0;
	bool bWrapped = false;
};
