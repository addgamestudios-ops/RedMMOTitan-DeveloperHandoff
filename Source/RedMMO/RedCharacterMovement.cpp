#include "RedCharacterMovement.h"

#include "Components/CapsuleComponent.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Character.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "RedGravityBodies.h"

namespace
{
bool IsRejectedPlanetSurfaceIdentity(const AActor* HitActor, const UPrimitiveComponent* HitComponent)
{
	FString Text;
	Text += GetNameSafe(HitActor);
	Text += TEXT(" ");
	Text += GetNameSafe(HitActor ? HitActor->GetClass() : nullptr);
	Text += TEXT(" ");
	Text += GetNameSafe(HitComponent);
	Text += TEXT(" ");
	Text += GetNameSafe(HitComponent ? HitComponent->GetClass() : nullptr);
	Text.ToLowerInline();

	static const TCHAR* RejectedTokens[] =
	{
		TEXT("gameplaysurfacecollider"),
		TEXT("gameplaysurfacevisual"),
		TEXT("presentation"),
		TEXT("proxy"),
		TEXT("shell"),
		TEXT("sky"),
		TEXT("atmosphere"),
		TEXT("haze"),
		TEXT("cloud"),
		TEXT("dome"),
		TEXT("starlayer"),
		TEXT("ship"),
		TEXT("bolt"),
		TEXT("projectile"),
		TEXT("weapon"),
		TEXT("character"),
		TEXT("player"),
		TEXT("mining"),
		TEXT("asteroid"),
		TEXT("reticle"),
		TEXT("hud")
	};

	for (const TCHAR* Token : RejectedTokens)
	{
		if (Text.Contains(Token))
		{
			return true;
		}
	}
	return false;
}

bool IsRejectedPlanetSurfaceHit(const FHitResult& Hit)
{
	return IsRejectedPlanetSurfaceIdentity(Hit.GetActor(), Hit.GetComponent());
}

bool HasPlanetGenActorIdentity(const AActor* Actor)
{
	FString Identity;
	Identity.Reserve(192);
	for (int32 OwnerDepth = 0; IsValid(Actor) && OwnerDepth < 8; ++OwnerDepth, Actor = Actor->GetOwner())
	{
		Identity += Actor->GetName();
		Identity += TEXT(" ");
		for (const UClass* Class = Actor->GetClass(); Class; Class = Class->GetSuperClass())
		{
			Identity += Class->GetName();
			Identity += TEXT(" ");
		}
	}
	Identity.ToLowerInline();
	if (Identity.Contains(TEXT("clmplanet")) || Identity.Contains(TEXT("planetgen")))
	{
		return true;
	}
	return Identity.Contains(TEXT("clm"))
		&& (Identity.Contains(TEXT("planet")) || Identity.Contains(TEXT("terrain"))
			|| Identity.Contains(TEXT("chunk")));
}

bool IsPlanetGenTerrainHit(const FHitResult& Hit)
{
	if (!Hit.bBlockingHit || IsRejectedPlanetSurfaceHit(Hit))
	{
		return false;
	}

	FString ComponentIdentity;
	const UPrimitiveComponent* Component = Hit.GetComponent();
	ComponentIdentity += GetNameSafe(Component);
	ComponentIdentity += TEXT(" ");
	for (const UClass* Class = Component ? Component->GetClass() : nullptr; Class; Class = Class->GetSuperClass())
	{
		ComponentIdentity += Class->GetName();
		ComponentIdentity += TEXT(" ");
	}
	ComponentIdentity.ToLowerInline();
	const bool bProceduralMesh = ComponentIdentity.Contains(TEXT("proceduralmesh"))
		|| ComponentIdentity.Contains(TEXT("dynamicmesh"));
	const bool bNamedTerrainComponent = ComponentIdentity.Contains(TEXT("terrainchunk"))
		|| ComponentIdentity.Contains(TEXT("planetchunk"))
		|| (ComponentIdentity.Contains(TEXT("clm")) && ComponentIdentity.Contains(TEXT("mesh")));
	if (HasPlanetGenActorIdentity(Hit.GetActor()))
	{
		return bProceduralMesh || bNamedTerrainComponent;
	}
	FString ActorIdentity = GetNameSafe(Hit.GetActor());
	ActorIdentity.ToLowerInline();
	return (bProceduralMesh || bNamedTerrainComponent) && (ActorIdentity.Contains(TEXT("clm"))
		|| ActorIdentity.Contains(TEXT("planetchunk"))
		|| ActorIdentity.Contains(TEXT("terrainchunk")));
}
}

bool URedCharacterMovement::FindPhysicalPlanetSurface(const ACharacter& Character, FVector& OutCapsuleCenter, FVector& OutSurfaceUp) const
{
	UWorld* World = Character.GetWorld();
	if (!World)
	{
		return false;
	}

	const FVector ActorLocation = Character.GetActorLocation();
	FVector TraceUp = ActorLocation - PlanetCenter;
	if (TraceUp.IsNearlyZero())
	{
		TraceUp = FVector::UpVector;
	}
	else
	{
		TraceUp.Normalize();
	}

	const UCapsuleComponent* Capsule = Character.GetCapsuleComponent();
	const float CapsuleHalfHeight = Capsule ? Capsule->GetScaledCapsuleHalfHeight() : 96.0f;
	const FVector TraceStart = ActorLocation + TraceUp * SurfaceTraceStartLift;
	const FVector TraceEnd = ActorLocation - TraceUp * SurfaceTraceDistance;

	FCollisionObjectQueryParams ObjectParams;
	ObjectParams.AddObjectTypesToQuery(ECC_WorldStatic);
	ObjectParams.AddObjectTypesToQuery(ECC_WorldDynamic);

	FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(RedPhysicalPlanetSurface), false);
	QueryParams.AddIgnoredActor(&Character);

	TArray<FHitResult> Hits;
	World->LineTraceMultiByObjectType(Hits, TraceStart, TraceEnd, ObjectParams, QueryParams);
	for (const FHitResult& Hit : Hits)
	{
		if (!Hit.bBlockingHit || IsRejectedPlanetSurfaceHit(Hit))
		{
			continue;
		}

		OutSurfaceUp = Hit.Location - PlanetCenter;
		if (OutSurfaceUp.IsNearlyZero())
		{
			OutSurfaceUp = Hit.ImpactNormal.IsNearlyZero() ? TraceUp : Hit.ImpactNormal.GetSafeNormal();
		}
		else
		{
			OutSurfaceUp.Normalize();
		}
		OutCapsuleCenter = Hit.Location + OutSurfaceUp * (CapsuleHalfHeight + SurfaceStickGap);
		return true;
	}

	return false;
}

void URedCharacterMovement::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	// Set the radial gravity direction BEFORE Super so this frame's floor check uses the
	// correct (toward-planet-center) direction. RadialGravityComponent also runs in
	// TG_PrePhysics, but tick order between sibling components isn't guaranteed; if it
	// ticks AFTER Super, the floor check ran with stale gravity and the proxy flips to
	// MOVE_FALLING → falling animation. Setting gravity here closes that race.
	if (bFlatMode)
	{
		SetGravityDirection(FVector::DownVector);
	}
	else if (AActor* OwnerActor = GetOwner())
	{
		const FVector Loc = OwnerActor->GetActorLocation();

		// Multi-body: re-center on the DOMINANT gravity body FIRST — for ALL roles, including
		// simulated proxies (PlanetCenter never replicates, so a remote player standing on a moon
		// would otherwise keep home-planet gravity forever and read as airborne). Hold the last
		// body when no volume contains us (deep space). On a body SWITCH the fall-guard radius
		// from the old body is meaningless in the new frame — reset it.
		{
			RedGravity::FBodyQueryResult Body;
			if (RedGravity::QueryDominantBodyDetailed(
				GetWorld(), Loc, CurrentGravityBodyId,
				GravityBodySwitchHysteresis, Body))
			{
				if (!CurrentGravityBodyId.IsNone()
					&& Body.StableId != CurrentGravityBodyId)
				{
					FallGuardRadius = 0.f;
				}
				CurrentGravityBodyId = Body.StableId;
				PlanetCenter = Body.Center;
				if (Body.SurfaceRadius > 0.f)
				{
					PlanetSurfaceRadius = Body.SurfaceRadius;
				}
			}
		}

		const FVector FromCenter = Loc - PlanetCenter;
		if (!FromCenter.IsNearlyZero())
		{
			SetGravityDirection(-FromCenter.GetSafeNormal());
		}
	}

	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	ACharacter* Char = Cast<ACharacter>(GetOwner());
	if (!Char)
	{
		return;
	}
	const ENetRole Role = Char->GetLocalRole();

	if (Role == ROLE_SimulatedProxy)
	{
		// Stop the proxy ever locally extrapolating gravity. On a transient missed-floor tick
		// (the voxel chunk under a far/standing proxy not yet physics-queryable) the engine
		// would flip Walking->Falling and accumulate fall velocity, sinking the capsule through
		// the planet. bSimGravityDisabled makes SimulateMovement zero velocity, skip the fall
		// accumulation, and re-land from a wider floor distance. Covers STANDING and MOVING
		// proxies (the old Velocity>10 snap missed the standing case). Re-set every tick because
		// the engine clears it on each net update.
		Char->bSimGravityDisabled = true;

		// Drive the locomotion ABP from the REPLICATED velocity (the engine Velocity member is
		// zeroed by bSimGravityDisabled). It arrives in spikes, so hold the last real value for
		// a short window and synthesize matching acceleration -> steady run pose, no regression.
		const float RepSpeed = (float)Char->GetReplicatedMovement().LinearVelocity.Size();
		if (RepSpeed > 10.f)
		{
			SteadyVel = Char->GetReplicatedMovement().LinearVelocity;
			ProxyHoldTimer = 0.25f;
		}
		else if (ProxyHoldTimer > 0.f)
		{
			ProxyHoldTimer -= DeltaTime;
		}
		else
		{
			SteadyVel = FVector::ZeroVector;
		}
		Velocity = SteadyVel;
		Acceleration = (SteadyVel.Size() > 10.f) ? SteadyVel.GetSafeNormal() * GetMaxAcceleration() : FVector::ZeroVector;
		return;
	}

	// Flat (non-planet) maps: skip all radial snapping/fall-guard; the standard CharacterMovement
	// floor collision + downward gravity handles walking.
	if (bFlatMode)
	{
		return;
	}

	// Frozen or riding (boarded a ship: MOVE_None + attached): NO radial snapping. Without this
	// gate the surface snap keeps teleporting the hidden attached pilot onto the terrain UNDER the
	// climbing ship every tick — pinning it to the ground track, growing the attach offset to
	// kilometers, and dragging its voxel collision invoker away from the ship it should stream for.
	if (MovementMode == MOVE_None || (Char->GetAttachParentActor() != nullptr))
	{
		return;
	}

	// Authority + AutonomousProxy (locally-simulated movement): radial anti-sink. The voxel
	// collision under a far/standing player can be missing for a tick or two; rather than let
	// the pawn sink toward the planet core, never allow the radial distance to drop below where
	// we last stood while in MOVE_Falling. Clamp + force a fresh floor check so we re-ground the
	// instant the chunk is queryable. Terrain-safe: tracks the live grounded radius every tick.
	const FVector Loc = Char->GetActorLocation();
	const FVector FromCenter = Loc - PlanetCenter;
	const float R = (float)FromCenter.Size();
	const UCapsuleComponent* Capsule = Char->GetCapsuleComponent();
	const float CapsuleHalfHeight = Capsule ? Capsule->GetScaledCapsuleHalfHeight() : 96.0f;
	const float MinimumCenterRadius = PlanetSurfaceRadius + CapsuleHalfHeight + SurfaceStickGap;
	bool bResolvedPhysicalSurface = false;
	if (bPreferPhysicalSurfaceTrace && MovementMode != MOVE_Flying)
	{
		FVector SurfaceCapsuleCenter = FVector::ZeroVector;
		FVector SurfaceUp = FVector::UpVector;
		if (FindPhysicalPlanetSurface(*Char, SurfaceCapsuleCenter, SurfaceUp))
		{
			bResolvedPhysicalSurface = true;
			const float SignedDistanceToSurface = FVector::DotProduct(Loc - SurfaceCapsuleCenter, SurfaceUp);
			const float ResolvedRadius = (float)(SurfaceCapsuleCenter - PlanetCenter).Size();
			// A hit ABOVE the capsule top means we are UNDER an arch/cave roof whose TOP resolved
			// as "the surface" — snapping there teleports the pawn through solid rock, and writing
			// it to the guard slingshots jumps up onto the roof. The one legitimate above-us hit is
			// the cook pop-out (terrain solidified on top of a pawn that sank while it cooked):
			// recognizable because the rest spot is where we last stood (guard match), or because
			// we have no ground history on this body yet (fresh arrival). Under a roof we still
			// count as resolved (keeps the datum catcher off) but neither snap nor touch the guard.
			const bool bHitAbovePawn = SignedDistanceToSurface < -(CapsuleHalfHeight + 50.0f);
			const bool bCookPopOut = (FallGuardRadius <= 0.f) || (FMath::Abs(ResolvedRadius - FallGuardRadius) <= 100.0f);
			if (!bHitAbovePawn || bCookPopOut)
			{
				// Snap ONLY when arriving from a fall (descending/idle within 60cm of the resting
				// spot, or sunk below it — the cook-latency pop-out). NEVER while ascending and
				// NEVER while MOVE_Walking: the engine owns grounded movement, and snapping a
				// walking pawn to the trace point teleported it on slopes/props every tick (the
				// sideways skip). 60cm sits above the old 2-30cm dead zone (hovering in
				// MOVE_Falling, grounded by neither the engine floor check nor the snap) and
				// safely below the ~184cm jump apex — 200cm snapped every jump back down at apex.
				const float RadialVel = FVector::DotProduct(Velocity, SurfaceUp);
				const bool bFallingNearSurface = (MovementMode == MOVE_Falling) && (RadialVel <= 50.0f);
				if (bFallingNearSurface && SignedDistanceToSurface <= 60.0f)
				{
					Char->SetActorLocation(SurfaceCapsuleCenter, false, nullptr, ETeleportType::TeleportPhysics);
					Velocity = FVector::VectorPlaneProject(Velocity, SurfaceUp);
					FallGuardRadius = ResolvedRadius;
					bForceNextFloorCheck = true;
					SetMovementMode(MOVE_Walking);
					return;
				}

				// The resolved REAL ground below us is the truth — SET the guard to it (Max() kept
				// a stale higher radius when dropping into craters/low terrain, so one
				// missed-collision tick teleported the pawn back up to the old level: the Mars
				// bounce war).
				FallGuardRadius = ResolvedRadius;
			}
		}
	}

	// Analytic datum catcher — ONLY for a body we have NEVER resolved real ground on
	// (FallGuardRadius==0: fresh arrival over not-yet-cooked voxel). Once any physical ground
	// has been seen, the guard below is the authority. Unconditionally clamping to the datum
	// fought every real surface that sits BELOW it (craters, stamp smoothing) — each
	// missed-collision tick teleported the pawn up to the datum and back: the Mars disaster.
	// Hold in MOVE_Falling (hover honestly until the terrain cooks, then the snap grounds us);
	// flipping to MOVE_Walking on nothing made the engine floor check thrash walk/fall.
	if (!bResolvedPhysicalSurface && FallGuardRadius <= 0.f && R > 1.0f && R < MinimumCenterRadius)
	{
		const FVector Dir = FromCenter.GetSafeNormal();

		// Sky-trace rescue: before holding at the datum, look for the OUTERMOST cooked ground along
		// our radial ray, starting above PlanetGen's reflected peak-radius envelope. The
		// pawn's own downward trace starts only 50m up — terrain that cooks in TALLER than that
		// around a datum-held pawn would entomb it with no recovery. PlanetGen terrain is normally
		// WorldDynamic; arbitrary props and ships are ignored before tracing both terrain types.
		{
			FCollisionObjectQueryParams SkyObjectParams;
			SkyObjectParams.AddObjectTypesToQuery(ECC_WorldStatic);
			SkyObjectParams.AddObjectTypesToQuery(ECC_WorldDynamic);
			FCollisionQueryParams SkyQueryParams(SCENE_QUERY_STAT(RedDatumSkyRescue), false);
			SkyQueryParams.AddIgnoredActor(Char);

			FVector LivePlanetCenter = PlanetCenter;
			float LiveDatumRadius = PlanetSurfaceRadius;
			float LivePeakRadius = MinimumCenterRadius + 200000.0f;
			const bool bHasPlanetGen = RedGravity::FindMeshPlanet(
				GetWorld(), LivePlanetCenter, LiveDatumRadius, &LivePeakRadius);
			if (bHasPlanetGen)
			{
				for (TActorIterator<AActor> It(GetWorld()); It; ++It)
				{
					AActor* CandidateActor = *It;
					if (!IsValid(CandidateActor) || CandidateActor == Char)
					{
						continue;
					}
					if (!HasPlanetGenActorIdentity(CandidateActor))
					{
						SkyQueryParams.AddIgnoredActor(CandidateActor);
						continue;
					}

					TInlineComponentArray<UPrimitiveComponent*> PrimitiveComponents;
					CandidateActor->GetComponents(PrimitiveComponents);
					for (UPrimitiveComponent* Primitive : PrimitiveComponents)
					{
						if (IsRejectedPlanetSurfaceIdentity(CandidateActor, Primitive))
						{
							SkyQueryParams.AddIgnoredComponent(Primitive);
						}
					}
				}
			}

			TArray<FHitResult> SkyHits;
			const FVector SkyStart = bHasPlanetGen
				? LivePlanetCenter + Dir * (LivePeakRadius + 5000.0f)
				: PlanetCenter + Dir * (MinimumCenterRadius + 200000.0f);
			GetWorld()->LineTraceMultiByObjectType(SkyHits, SkyStart, Loc, SkyObjectParams, SkyQueryParams);
			for (const FHitResult& SkyHit : SkyHits)
			{
				if (bHasPlanetGen ? !IsPlanetGenTerrainHit(SkyHit)
					: (!SkyHit.bBlockingHit || IsRejectedPlanetSurfaceHit(SkyHit)))
				{
					continue;
				}
				if (bHasPlanetGen)
				{
					const float HitRadius = FVector::Dist(SkyHit.ImpactPoint, LivePlanetCenter);
					if (HitRadius < LiveDatumRadius - 5000.0f || HitRadius > LivePeakRadius + 5000.0f)
					{
						continue;
					}
				}
				FVector GroundUp = SkyHit.Location - PlanetCenter;
				GroundUp = GroundUp.IsNearlyZero() ? Dir : GroundUp.GetSafeNormal();
				const FVector RescueCenter = SkyHit.Location + GroundUp * (CapsuleHalfHeight + SurfaceStickGap);
				Char->SetActorLocation(RescueCenter, false, nullptr, ETeleportType::TeleportPhysics);
				Velocity = FVector::VectorPlaneProject(Velocity, GroundUp);
				FallGuardRadius = (float)(RescueCenter - PlanetCenter).Size();
				bForceNextFloorCheck = true;
				SetMovementMode(MOVE_Walking);
				return;
			}
		}

		Char->SetActorLocation(PlanetCenter + Dir * MinimumCenterRadius, false, nullptr, ETeleportType::TeleportPhysics);
		// ZERO the velocity (was VectorPlaneProject, which kept the tangential component). Preserving it
		// turned a datum-held pawn into a frictionless bead that slid across the datum sphere to the terrain
		// global-minimum basin — so a pawn spawned anywhere the terrain hadn't cooked yet (e.g. the world
		// pole) never held its spawn direction. Zeroed, it stays put while the chunk cooks and the sky-rescue
		// above pops it onto the real ground.
		Velocity = FVector::ZeroVector;
		bForceNextFloorCheck = true;
		return;
	}

	if (MovementMode == MOVE_Walking)
	{
		// Trust the REAL ground: R is where we are actually standing. Flooring this at
		// MinimumCenterRadius poisoned the guard wherever terrain sits BELOW the nominal surface
		// radius (the far side is ~4m lower) — every falling tick then teleported the pawn 4m up:
		// "running in place / can't move 5m / skipping in the air".
		FallGuardRadius = R;
	}
	else if (MovementMode == MOVE_Falling && FallGuardRadius > 0.f && R < FallGuardRadius - 30.f)
	{
		const FVector Dir = FromCenter.GetSafeNormal();
		Char->SetActorLocation(PlanetCenter + Dir * FallGuardRadius, false, nullptr, ETeleportType::TeleportPhysics);
		Velocity = FVector::VectorPlaneProject(Velocity, Dir); // remove the toward-core component
		bForceNextFloorCheck = true;
	}
}
