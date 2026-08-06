#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "RedDayNight.generated.h"

class UDirectionalLightComponent;

/**
 * Slow planetary day/night cycle. Rotates the sky's atmosphere sun through a full revolution every
 * DayLengthSeconds, and carries a built-in cool "moonlight" fill locked opposite the sun so the night
 * side is never pitch black — just darker, readable, with the star sky fading in (see UpdateSkyFade).
 */
UCLASS()
class REDMMO_API ARedDayNight : public AActor
{
	GENERATED_BODY()

public:
	ARedDayNight();
	virtual void GetLifetimeReplicatedProps(
		TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** Seconds for one full day+night revolution (default two real hours). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Replicated, Category = "Red|DayNight", meta = (ClampMin = "30.0"))
	float DayLengthSeconds = 7200.f;

	/** Cool low-intensity fill locked opposite the sun — keeps nights visible instead of black. */
	UPROPERTY(VisibleAnywhere, Category = "Red|DayNight")
	UDirectionalLightComponent* MoonLight;

	virtual void Tick(float DeltaSeconds) override;

protected:
	virtual void BeginPlay() override;

private:
	/** The sky's atmosphere sun (found by name/intensity heuristic at BeginPlay). */
	UPROPERTY(Transient)
	UDirectionalLightComponent* Sun = nullptr;

	FRotator SunStartRotation = FRotator::ZeroRotator;
	/** Disposable Night_T03 validation state. Never enabled by a production map. */
	bool bLockedNightVisualTest = false;
	bool bLockedNightRotationResolved = false;
	FRotator LockedNightSunRotation = FRotator::ZeroRotator;
	float CycleTime = 0.f;

	/** Server-clock epoch keeps every multiplayer peer on the same solar phase. */
	UPROPERTY(Replicated)
	float CycleStartServerTime = -1.f;

	void FindSun();
	void ApplyLockedNight();
};
