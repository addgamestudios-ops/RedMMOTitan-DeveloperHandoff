#include "RadialGravityComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/Controller.h"
#include "RedGravityBodies.h"

URadialGravityComponent::URadialGravityComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.TickGroup = TG_PrePhysics;
}

void URadialGravityComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	AActor* Owner = GetOwner();
	if (!Owner)
	{
		return;
	}

	// Multi-body: re-center on the DOMINANT gravity body at our location (GravityCore volumes,
	// priority resolves overlaps — near a moon, the moon wins). In deep space between volumes the
	// query fails and we HOLD the last body (never fall back to world -Z).
	{
		RedGravity::FBodyQueryResult Body;
		if (RedGravity::QueryDominantBodyDetailed(
			GetWorld(), Owner->GetActorLocation(), CurrentGravityBodyId,
			GravityBodySwitchHysteresis, Body))
		{
			CurrentGravityBodyId = Body.StableId;
			PlanetCenter = Body.Center;
		}
	}

	const FVector ToCenter = PlanetCenter - Owner->GetActorLocation();
	if (ToCenter.IsNearlyZero())
	{
		return;
	}

	const FVector GravityDir = ToCenter.GetSafeNormal();
	const FVector DesiredUp = -GravityDir;

	ACharacter* Char = Cast<ACharacter>(Owner);

	// SIMULATED PROXY (this character as seen on OTHER players' screens): set the gravity
	// DIRECTION so the proxy's floor check finds the curved sphere surface (without it, the
	// CMC's default -Z floor check fails on the planet and the proxy reads as airborne ->
	// plays the falling animation). We do NOT rotate the CAPSULE per-tick here — that fought
	// the proxy movement pipeline and zeroed velocity; the velocity is re-synthesized in
	// URedCharacterMovement, and the body is tilted by rotating the MESH only (visual). The
	// threshold no-ops if the capsule tilt already arrived over the wire (no double-tilt).
	if (Owner->GetLocalRole() == ROLE_SimulatedProxy)
	{
		if (Char)
		{
			if (UCharacterMovementComponent* CMC = Char->GetCharacterMovement())
			{
				CMC->SetGravityDirection(GravityDir);
			}
			if (USkeletalMeshComponent* MeshComp = Char->GetMesh())
			{
				const FQuat MeshQuat = MeshComp->GetComponentQuat();
				const FVector MeshUp = MeshQuat.GetAxisZ();
				if ((MeshUp | DesiredUp) < 0.99995f)
				{
					MeshComp->SetWorldRotation(FQuat::FindBetweenNormals(MeshUp, DesiredUp) * MeshQuat);
				}
			}
		}
		return;
	}

	// Drive the character movement gravity toward the planet core.
	if (Char)
	{
		if (UCharacterMovementComponent* CMC = Char->GetCharacterMovement())
		{
			CMC->SetGravityDirection(GravityDir);
		}
	}

	// Align ONLY the capsule's up axis to the surface normal with the smallest
	// possible rotation, leaving yaw/look to the controller so the camera does
	// not fight the orientation. (The previous full MakeFromZX rebuild
	// overwrote the controller's yaw every tick and swung the camera around.)
	if (bOrientToSurface)
	{
		const FQuat CurrentQuat = Owner->GetActorQuat();
		const FVector CurrentUp = CurrentQuat.GetAxisZ();
		const float UpDot = (float)(CurrentUp | DesiredUp);
		if (UpDot < -0.9f)
		{
			// Near-antiparallel (e.g. arriving on the far side): FindBetweenNormals is degenerate
			// (arbitrary axis -> random spin). Build the surface-aligned rotation directly instead,
			// preserving whatever forward projects onto the new tangent plane.
			FVector Fwd = FVector::VectorPlaneProject(CurrentQuat.GetAxisX(), DesiredUp).GetSafeNormal();
			if (Fwd.IsNearlyZero())
			{
				Fwd = FVector::VectorPlaneProject(FVector::ForwardVector, DesiredUp).GetSafeNormal();
			}
			Owner->SetActorRotation(FRotationMatrix::MakeFromZX(DesiredUp, Fwd).Rotator());
		}
		else if (UpDot < 0.99995f)
		{
			const FQuat DeltaQuat = FQuat::FindBetweenNormals(CurrentUp, DesiredUp);
			Owner->SetActorRotation(DeltaQuat * CurrentQuat);
		}
	}

	// Keep the third-person camera level with the local ground: as the player
	// walks around the sphere the "up" rotates, so rotate the controller's look
	// direction by the same delta. The player's own look input is preserved.
	const FVector NewUp = -GravityDir;
	if (bRebaseControlRotation && Char)
	{
		if (AController* Controller = Char->GetController())
		{
			// Keep DOUBLE precision: walking deltas are ~1e-10 below 1.0 and vanish in a float cast,
			// which turned this rebase into dead code and let the camera slowly de-level while running.
			const double CosDelta = (PrevUp | NewUp);
			if (bHasPrevUp && CosDelta > 0.9962)          // <= ~5 deg/frame: normal locomotion
			{
				if (CosDelta < 1.0 - 1.0e-14)             // any real change at all -> rebase smoothly
				{
					const FQuat SurfaceDelta = FQuat::FindBetweenNormals(PrevUp, NewUp);
					const FQuat NewControl = SurfaceDelta * Controller->GetControlRotation().Quaternion();
					// ROLL-FREE: accumulating per-frame deltas picks up parallel-transport roll on a
					// sphere (fast on a small moon -> diagonal horizon, motion sickness). Keep the
					// EXACT view direction but rebuild the rotation LEVEL to the local up each frame.
					const FVector Fwd = NewControl.GetForwardVector();
					if (FMath::Abs((float)(Fwd | NewUp)) < 0.98f)
					{
						Controller->SetControlRotation(FRotationMatrix::MakeFromXZ(Fwd, NewUp).Rotator());
					}
					else
					{
						// Looking nearly straight up/down: MakeFromXZ degenerates; keep the delta result.
						Controller->SetControlRotation(NewControl.Rotator());
					}
				}
			}
			// > ~5 deg in one frame = teleport (far-side ship exit) or collision bounce: DON'T whip
			// the camera by it — PrevUp resyncs below and the exit path sets a clean control rotation.
		}
	}
	PrevUp = NewUp;
	bHasPrevUp = true;
}
