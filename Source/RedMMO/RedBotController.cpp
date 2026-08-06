#include "RedBotController.h"
#include "RedPlayerCharacter.h"
#include "GameFramework/Character.h"
#include "Kismet/GameplayStatics.h"
#include "RedGravityBodies.h"

ARedBotController::ARedBotController()
{
	PrimaryActorTick.bCanEverTick = true;
}

void ARedBotController::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	APawn* Me = GetPawn();
	if (!Me)
	{
		return;
	}

	// Stress-test wander: roam local waypoints (no chase/fire) so N bots stay spread across the map,
	// each a live streaming source. Uses direct movement input — no navmesh needed.
	if (bWander)
	{
		const FVector MyLoc = Me->GetActorLocation();
		const FVector UpDir = RedGravity::UpAt(GetWorld(), MyLoc, FVector::UpVector);
		if (!bWanderInit) { WanderOrigin = MyLoc; bWanderInit = true; WanderRepick = 0.f; }
		WanderRepick -= DeltaSeconds;
		if (WanderRepick <= 0.f || FVector::DistSquared(MyLoc, WanderTarget) < FMath::Square(600.f))
		{
			FVector T = FVector::CrossProduct(UpDir, FVector::ForwardVector).GetSafeNormal();
			if (T.IsNearlyZero()) { T = FVector::CrossProduct(UpDir, FVector::RightVector).GetSafeNormal(); }
			const FVector B = FVector::CrossProduct(UpDir, T).GetSafeNormal();
			const float Ang = FMath::FRandRange(0.f, 2.f * PI);
			const float Rad = FMath::FRandRange(1500.f, FMath::Max(2000.f, WanderRadius));
			WanderTarget = WanderOrigin + (T * FMath::Cos(Ang) + B * FMath::Sin(Ang)) * Rad;
			WanderRepick = FMath::FRandRange(3.f, 7.f);
		}
		const FVector ToWp = FVector::VectorPlaneProject(WanderTarget - MyLoc, UpDir).GetSafeNormal();
		if (!ToWp.IsNearlyZero())
		{
			Me->AddMovementInput(ToWp, 1.f);
			Me->SetActorRotation(FRotationMatrix::MakeFromXZ(ToWp, UpDir).Rotator());
		}
		return;
	}

	if (!TargetPlayer.IsValid())
	{
		TargetPlayer = UGameplayStatics::GetPlayerCharacter(this, 0);
		if (!TargetPlayer.IsValid())
		{
			return;
		}
	}
	ACharacter* Target = TargetPlayer.Get();

	const FVector MyLoc = Me->GetActorLocation();
	const FVector TgtLoc = Target->GetActorLocation();
	const FVector ToTgt = TgtLoc - MyLoc;
	const float Dist = ToTgt.Size();

	// Radial up from the DOMINANT gravity body (planet OR moon), so bots fight correctly anywhere.
	// Steering along the surface tangent (toward the target) keeps the bot walking the sphere.
	// FLAT WORLD (Titan / no gravity body): fall back to world up, NOT direction-from-origin —
	// otherwise bots near the world origin orient to a random sideways vector and tilt/ragdoll.
	const FVector UpDir = RedGravity::UpAt(GetWorld(), MyLoc, FVector::UpVector);
	const FVector Tangent = FVector::VectorPlaneProject(ToTgt, UpDir).GetSafeNormal();

	if (Dist > ChaseStopRange && !Tangent.IsNearlyZero())
	{
		Me->AddMovementInput(Tangent, 1.f);
	}

	// Face the target around the radial up (keeps them upright on the curved surface).
	if (!Tangent.IsNearlyZero())
	{
		Me->SetActorRotation(FRotationMatrix::MakeFromXZ(Tangent, UpDir).Rotator());
	}

	FireCooldown -= DeltaSeconds;
	if (Dist <= FireRange && FireCooldown <= 0.f)
	{
		FireCooldown = FireInterval;
		if (ARedPlayerCharacter* Bot = Cast<ARedPlayerCharacter>(Me))
		{
			Bot->FireAtTarget(Target);
		}
	}
}
