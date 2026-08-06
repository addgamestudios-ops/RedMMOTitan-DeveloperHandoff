#include "FootstepTrailComponent.h"
#include "RedGravityBodies.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Engine/DecalActor.h"
#include "Components/DecalComponent.h"
#include "Components/PrimitiveComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/World.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInterface.h"
#include "NiagaraFunctionLibrary.h"
#include "Math/RotationMatrix.h"
#include "PhysicalMaterials/PhysicalMaterial.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
	void AppendSurfaceIdentity(const UObject* Object, FString& OutIdentity)
	{
		if (!Object)
		{
			return;
		}

		OutIdentity += TEXT(" ");
		OutIdentity += Object->GetName();
		for (const UClass* Class = Object->GetClass(); Class; Class = Class->GetSuperClass())
		{
			OutIdentity += TEXT(" ");
			OutIdentity += Class->GetName();
		}

		if (const AActor* Actor = Cast<AActor>(Object))
		{
			for (const FName Tag : Actor->Tags)
			{
				OutIdentity += TEXT(" ");
				OutIdentity += Tag.ToString();
			}
		}
		else if (const UActorComponent* Component = Cast<UActorComponent>(Object))
		{
			for (const FName Tag : Component->ComponentTags)
			{
				OutIdentity += TEXT(" ");
				OutIdentity += Tag.ToString();
			}
		}
	}

	bool ClassIsCLMPlanet(const UClass* Class)
	{
		for (const UClass* Current = Class; Current; Current = Current->GetSuperClass())
		{
			if (Current->GetName() == TEXT("CLMPlanet"))
			{
				return true;
			}
		}
		return false;
	}
}

UFootstepTrailComponent::UFootstepTrailComponent()
{
	PrimaryComponentTick.bCanEverTick = true;

	// Use the pack's authored actor rather than projecting the full 2x2 footprint atlas as one tile.
	// This is a hard CDO reference so the Blueprint and its decal dependencies survive Win64 cook.
	static ConstructorHelpers::FClassFinder<AActor> SandFootprintActor(
		TEXT("/Game/Vefects/Sand_VFX/VFX/DynamicSandSurface/Blueprints/BP_Footstep_Decal"));
	if (SandFootprintActor.Succeeded())
	{
		FootprintDecalClass = SandFootprintActor.Class;
	}
}

FVector UFootstepTrailComponent::ResolveGravityDirection(const ACharacter& Character, const FVector& WorldLocation) const
{
	if (bUseGravityCoreDirection)
	{
		FVector PlanetCenter;
		float DatumRadius = 0.f;
		if (RedGravity::FindMeshPlanet(GetWorld(), PlanetCenter, DatumRadius))
		{
			const FVector PlanetDown = (PlanetCenter - WorldLocation).GetSafeNormal();
			if (!PlanetDown.IsNearlyZero())
			{
				return PlanetDown;
			}
		}
	}

	if (const UCharacterMovementComponent* CMC = Character.GetCharacterMovement())
	{
		const FVector MovementGravity = CMC->GetGravityDirection();
		if (!MovementGravity.IsNearlyZero())
		{
			return MovementGravity.GetSafeNormal();
		}
	}

	return FVector(0.0f, 0.0f, -1.0f);
}

bool UFootstepTrailComponent::TraceGroundAt(const AActor& Owner, const FVector& Origin, const FVector& Down, FHitResult& OutHit) const
{
	const FVector SafeDown = Down.GetSafeNormal();
	const FVector Start = Origin - SafeDown * TraceStartLift;
	const FVector End = Origin + SafeDown * TraceLength;

	FCollisionQueryParams Params(SCENE_QUERY_STAT(FootstepTrail), false, &Owner);
	Params.bReturnPhysicalMaterial = true;
	FCollisionObjectQueryParams ObjParams;
	ObjParams.AddObjectTypesToQuery(ECC_WorldStatic);
	ObjParams.AddObjectTypesToQuery(ECC_WorldDynamic);
	if (!GetWorld() || !GetWorld()->LineTraceSingleByObjectType(OutHit, Start, End, ObjParams, Params))
	{
		return false;
	}

	// The long radial trace is a terrain-discovery safety net, not permission to leave a mark on
	// a planet surface far below a falling/jetpacking pawn.
	return FVector::DistSquared(Origin, OutHit.ImpactPoint)
		<= FMath::Square(FMath::Max(1.f, MaxSurfaceContactDistance));
}

bool UFootstepTrailComponent::IsSandSurfaceHit(const FHitResult& Hit) const
{
	const UPrimitiveComponent* HitComponent = Hit.GetComponent();
	const AActor* HitActor = Hit.GetActor();
	if (!HitComponent || !HitActor)
	{
		return false;
	}

	FString Identity;
	AppendSurfaceIdentity(HitComponent, Identity);
	bool bOwnedByCLMPlanet = false;
	for (const AActor* Actor = HitActor; Actor; Actor = Actor->GetOwner())
	{
		AppendSurfaceIdentity(Actor, Identity);
		bOwnedByCLMPlanet |= ClassIsCLMPlanet(Actor->GetClass());
	}
	for (int32 MaterialIndex = 0; MaterialIndex < HitComponent->GetNumMaterials(); ++MaterialIndex)
	{
		AppendSurfaceIdentity(HitComponent->GetMaterial(MaterialIndex), Identity);
	}
	Identity.ToLowerInline();

	// Hard rejects always win, including if a vehicle mesh happens to use a material with "sand"
	// in its name. RedNoSandFX is also available as an explicit component/actor opt-out.
	static const TCHAR* RejectedTokens[] =
	{
		TEXT("rednosandfx"), TEXT("ship"), TEXT("shuttle"), TEXT("fighter"),
		TEXT("spacecraft"), TEXT("vehicle"), TEXT("character"), TEXT("player"),
		TEXT("pawn"), TEXT("weapon"), TEXT("water"), TEXT("ocean"), TEXT("lake"),
		TEXT("foliage"), TEXT("grass"), TEXT("flower"), TEXT("plant"), TEXT("cactus"),
		TEXT("rock"), TEXT("boulder"), TEXT("cliff"), TEXT("building"), TEXT("structure")
	};
	for (const TCHAR* Token : RejectedTokens)
	{
		if (Identity.Contains(Token))
		{
			return false;
		}
	}

	// Config/DefaultEngine.ini defines SurfaceType4 as Sand. Once biome layers supply physical
	// materials this is authoritative: snow/grass/rock CLM pixels will not inherit desert FX simply
	// because they share a generated chunk actor. Default means the older PlanetGen asset supplied
	// no layer physical material, so the cook-safe CLM identity fallback below remains necessary.
	if (const UPhysicalMaterial* PhysicalMaterial = Hit.PhysMaterial.Get())
	{
		if (PhysicalMaterial->SurfaceType != SurfaceType_Default)
		{
			return PhysicalMaterial->SurfaceType == SurfaceType4;
		}
	}

	// Authored sand meshes can opt in by tag/name/material even when they are not a CLM chunk.
	if (Identity.Contains(TEXT("redsandsurface"))
		|| Identity.Contains(TEXT("sandsurface"))
		|| Identity.Contains(TEXT("desert"))
		|| Identity.Contains(TEXT("dune")))
	{
		return true;
	}

	// PlanetGen's streamed procedural chunks use generic component/material names in some builds.
	// The current main CLM world is the desert surface; accepting only CLM/PlanetGen terrain keeps
	// footprints off every dynamic prop while still surviving those generic cooked chunk names.
	if (bOwnedByCLMPlanet
		|| Identity.Contains(TEXT("clmplanet"))
		|| Identity.Contains(TEXT("clm_planet"))
		|| Identity.Contains(TEXT("planetgen"))
		|| Identity.Contains(TEXT("planet_chunk"))
		|| Identity.Contains(TEXT("planetchunk"))
		|| Identity.Contains(TEXT("terrain_chunk"))
		|| Identity.Contains(TEXT("terrainchunk")))
	{
		return true;
	}

	// Last-resort match for PlanetGen versions whose runtime-mesh component has a generic name but
	// is owned at the actual mesh-planet centre. Ordinary ships and surface props are not.
	FVector PlanetCenter;
	float DatumRadius = 0.f;
	const FString ComponentClass = HitComponent->GetClass()->GetName().ToLower();
	const bool bRuntimeMesh = ComponentClass.Contains(TEXT("procedural"))
		|| ComponentClass.Contains(TEXT("dynamicmesh"))
		|| ComponentClass.Contains(TEXT("realtimemesh"))
		|| ComponentClass.Contains(TEXT("runtimemesh"));
	return bRuntimeMesh
		&& RedGravity::FindMeshPlanet(GetWorld(), PlanetCenter, DatumRadius)
		&& FVector::DistSquared(HitActor->GetActorLocation(), PlanetCenter)
			<= FMath::Square(FMath::Max(5000.f, DatumRadius * 0.05f));
}

void UFootstepTrailComponent::SpawnSandMark(
	const FHitResult& Hit,
	const FVector& Forward,
	float SizeScale,
	float TangentSpeed,
	bool bLeftFoot,
	bool bSpawnFootprint,
	bool bPlayAudio) const
{
	if (!GetWorld())
	{
		return;
	}

	const FVector SurfaceNormal = Hit.ImpactNormal.GetSafeNormal();
	FVector SurfaceForward = FVector::VectorPlaneProject(Forward, SurfaceNormal).GetSafeNormal();
	if (SurfaceForward.IsNearlyZero())
	{
		SurfaceForward = FVector::VectorPlaneProject(GetOwner()->GetActorForwardVector(), SurfaceNormal).GetSafeNormal();
	}
	if (SurfaceForward.IsNearlyZero())
	{
		SurfaceForward = FVector::CrossProduct(SurfaceNormal, FVector::RightVector).GetSafeNormal();
	}

	const float ToeOut = bLeftFoot ? -FootToeOutDegrees : FootToeOutDegrees;
	const float RandomTwist = FMath::FRandRange(-RandomYawDegrees, RandomYawDegrees);
	SurfaceForward = SurfaceForward.RotateAngleAxis(ToeOut + RandomTwist, SurfaceNormal).GetSafeNormal();

	// BP_Footstep_Decal owns the pack's atlas setup and fade behavior. Preserve its authored material:
	// replacing it with the parent material here loses the Blueprint's selected sole/frame and can make
	// the mark disappear while the Niagara puff still renders. A generic decal is retained as a cook-safe
	// fallback, but it is only used when the authored actor/component did not materialize.
	if (bSpawnFootprint && (FootprintDecalClass || DecalMaterial))
	{
		const FRotator DecalRot = FRotationMatrix::MakeFromXZ(SurfaceNormal, SurfaceForward).Rotator();
		const FVector DecalLocation = Hit.ImpactPoint + SurfaceNormal * FootprintSurfaceOffset;
		AActor* DecalActor = nullptr;
		if (FootprintDecalClass)
		{
			FActorSpawnParameters SpawnParams;
			SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			DecalActor = GetWorld()->SpawnActor<AActor>(FootprintDecalClass, DecalLocation, DecalRot, SpawnParams);
		}

		UDecalComponent* DC = DecalActor ? DecalActor->FindComponentByClass<UDecalComponent>() : nullptr;
		if (!DC)
		{
			if (DecalActor)
			{
				DecalActor->Destroy();
			}
			ADecalActor* GenericDecal = GetWorld()->SpawnActor<ADecalActor>(DecalLocation, DecalRot);
			DecalActor = GenericDecal;
			DC = GenericDecal ? GenericDecal->GetDecal() : nullptr;
		}

		if (DecalActor && DC)
		{
			// Do not overwrite the Sand FX Blueprint's authored decal material. Only fill a genuinely
			// empty component (or the generic fallback) with the hard-referenced pack material.
			if (!DC->GetDecalMaterial() && DecalMaterial)
			{
				DC->SetDecalMaterial(DecalMaterial);
			}
			DC->DecalSize = DecalSize * FMath::Max(0.1f, SizeScale);
			DC->SetFadeScreenSize(FMath::Min(DC->FadeScreenSize, FootprintFadeScreenSize));
			DC->SetSortOrder(FMath::Max(DC->SortOrder, 20));
			DC->SetFadeOut(DecalLifeSpan * 0.78f, DecalLifeSpan * 0.22f, false);
			DC->SetHiddenInGame(false, true);
			DC->SetVisibility(true, true);
			DC->MarkRenderStateDirty();
			DecalActor->SetLifeSpan(DecalLifeSpan);
		}
	}

	const FRotator SurfaceRotation = FRotationMatrix::MakeFromZ(SurfaceNormal).Rotator();
	if (StepPuffSystem)
	{
		const float SpeedBoost = FMath::Clamp(TangentSpeed * SpeedDustScale, 0.0f, 0.9f);
		const float PuffScale = StepPuffScale * (1.0f + SpeedBoost) * FMath::Sqrt(FMath::Max(0.1f, SizeScale));
		UNiagaraFunctionLibrary::SpawnSystemAtLocation(
			GetWorld(),
			StepPuffSystem,
			Hit.ImpactPoint + SurfaceNormal * 2.0f,
			SurfaceRotation,
			FVector(PuffScale),
			true,
			true,
			ENCPoolMethod::AutoRelease);
	}
	if (bPlayAudio && StepSound)
	{
		UGameplayStatics::PlaySoundAtLocation(GetWorld(), StepSound, Hit.ImpactPoint, StepSoundVolume);
	}
}

void UFootstepTrailComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	AActor* Owner = GetOwner();
	ACharacter* Char = Cast<ACharacter>(Owner);
	if (GetNetMode() == NM_DedicatedServer
		|| !Char
		|| (!FootprintDecalClass && !DecalMaterial && !StepPuffSystem && !StepSound))
	{
		return;
	}

	UCharacterMovementComponent* CMC = Char->GetCharacterMovement();
	if (!CMC || !CMC->IsMovingOnGround())
	{
		return;
	}

	const FVector Loc = Owner->GetActorLocation();
	if (bHasLast && FVector::Dist(Loc, LastSpawnLocation) < StepDistance)
	{
		return;
	}

	// Trace toward the character's gravity direction (planet core) to find the ground.
	const FVector Down = ResolveGravityDirection(*Char, Loc);

	FHitResult CenterHit;
	if (TraceGroundAt(*Owner, Loc, Down, CenterHit) && IsSandSurfaceHit(CenterHit))
	{
		const FVector SurfaceNormal = CenterHit.ImpactNormal.GetSafeNormal();
		const FVector TangentVelocity = FVector::VectorPlaneProject(Char->GetVelocity(), SurfaceNormal);
		const float TangentSpeed = TangentVelocity.Size();

		FVector SurfaceForward = TangentVelocity.GetSafeNormal();
		if (SurfaceForward.IsNearlyZero())
		{
			SurfaceForward = FVector::VectorPlaneProject(Owner->GetActorForwardVector(), SurfaceNormal).GetSafeNormal();
		}
		FVector SurfaceRight = FVector::CrossProduct(SurfaceNormal, SurfaceForward).GetSafeNormal();
		if (SurfaceRight.IsNearlyZero())
		{
			SurfaceRight = FVector::VectorPlaneProject(Owner->GetActorRightVector(), SurfaceNormal).GetSafeNormal();
		}

		const bool bLeftFoot = bNextLeftFoot;
		const float FootSide = bLeftFoot ? -0.5f : 0.5f;
		FVector FootOrigin = Loc - SurfaceForward * FootBackOffset + SurfaceRight * FootSeparation * FootSide;
		if (const USkeletalMeshComponent* CharacterMesh = Char->GetMesh())
		{
			const FName FootBone = bLeftFoot ? FName(TEXT("foot_l")) : FName(TEXT("foot_r"));
			if (CharacterMesh->DoesSocketExist(FootBone))
			{
				FootOrigin = CharacterMesh->GetSocketLocation(FootBone);
			}
		}

		FHitResult FootHit;
		if (TraceGroundAt(*Owner, FootOrigin, Down, FootHit) && IsSandSurfaceHit(FootHit))
		{
			SpawnSandMark(FootHit, SurfaceForward, 1.0f, TangentSpeed, bLeftFoot, true, true);

			if (bSpawnForwardScuff && TangentSpeed >= MinSpeedForForwardScuff)
			{
				FHitResult ScuffHit;
				if (TraceGroundAt(*Owner, FootOrigin + SurfaceForward * ForwardScuffDistance, Down, ScuffHit)
					&& IsSandSurfaceHit(ScuffHit))
				{
					// The forward speed accent is dust only. A second enlarged sole decal was the
					// dominant square seen behind each real footprint in the previous build.
					SpawnSandMark(ScuffHit, SurfaceForward, ForwardScuffScale, TangentSpeed,
						bLeftFoot, false, false);
				}
			}

			LastSpawnLocation = Loc;
			bHasLast = true;
			bNextLeftFoot = !bNextLeftFoot;
		}
	}
}
