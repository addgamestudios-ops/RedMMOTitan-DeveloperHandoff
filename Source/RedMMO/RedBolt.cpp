#include "RedBolt.h"

#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/DecalComponent.h"
#include "Engine/DamageEvents.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/ProjectileMovementComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/Material.h"
#include "MaterialDomain.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Net/UnrealNetwork.h"
#include "NiagaraFunctionLibrary.h"
#include "NiagaraComponent.h"
#include "NiagaraSystem.h"
#include "Particles/ParticleSystem.h"
#include "Kismet/GameplayStatics.h"
#include "RedOrbitalMiningSite.h"
#include "RedMineableAsteroid.h"
#include "RedResourcePickup.h"
#include "UObject/ConstructorHelpers.h"

ARedBolt::ARedBolt()
{
	PrimaryActorTick.bCanEverTick = true;   // forces its beam flat each frame
	bReplicates = true;
	SetReplicateMovement(true);
	InitialLifeSpan = 3.f;

	// Sphere is the root + collider. ProjectileMovement moves it; OnHit fires when it
	// overlaps a Pawn/world surface — that's how we detect bolt impacts.
	Collision = CreateDefaultSubobject<USphereComponent>(TEXT("Collision"));
	Collision->InitSphereRadius(8.f);
	Collision->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	// WorldDynamic = doesn't BE a "projectile object", so we don't have to also-block-self.
	Collision->SetCollisionObjectType(ECC_WorldDynamic);
	Collision->SetCollisionResponseToAllChannels(ECR_Ignore);
	Collision->SetCollisionResponseToChannel(ECC_Pawn, ECR_Block);
	Collision->SetCollisionResponseToChannel(ECC_WorldStatic, ECR_Block);
	Collision->SetCollisionResponseToChannel(static_cast<ECollisionChannel>(13), ECR_Block); // Vibe/Voxel collision object channel
	// Block WorldDynamic too — pack shuttle meshes often stay WorldDynamic (not Vehicle).
	Collision->SetCollisionResponseToChannel(ECC_WorldDynamic, ECR_Block);
	Collision->SetCollisionResponseToChannel(ECC_Vehicle, ECR_Block);        // ships are solid: impact, don't pass through
	Collision->SetCollisionResponseToChannel(ECC_PhysicsBody, ECR_Block);
	Collision->SetGenerateOverlapEvents(false);
	Collision->SetNotifyRigidBodyCollision(true);
	RootComponent = Collision;
	Collision->OnComponentHit.AddDynamic(this, &ARedBolt::OnHit);

	// Visible emissive tracer. GPU Niagara beams don't render on Apple Silicon/Metal, so the
	// projectile carries its own mesh. A sphere stretched along travel (bRotationFollowsVelocity
	// aligns local X to velocity) reads as a plasma-bolt streak, not a "blue can".
	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	Mesh->SetupAttachment(Collision);
	static ConstructorHelpers::FObjectFinder<UStaticMesh> TracerMeshAsset(
		TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	if (TracerMeshAsset.Succeeded())
	{
		Mesh->SetStaticMesh(TracerMeshAsset.Object);
	}
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> TracerMatAsset(
		TEXT("/Game/RedMMO/Materials/M_BoltTracer.M_BoltTracer"));
	if (TracerMatAsset.Succeeded())
	{
		Mesh->SetMaterial(0, TracerMatAsset.Object);
	}
	// Laser bolt: a long thin bright beam stretched along local X = the travel axis (bRotationFollowsVelocity
	// keeps X on velocity), so it always lies along its flight. Renders on Metal (mesh, not GPU Niagara).
	Mesh->SetRelativeScale3D(FVector(1.6f, 0.07f, 0.07f));  // ~1.6m laser beam, 7cm thick
	Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Mesh->SetGenerateOverlapEvents(false);
	Mesh->SetCastShadow(false);
	Mesh->SetComponentTickEnabled(false);

	// Preserve the replicated native collision component for compatibility, but keep the new
	// ProjectilesVol1 overlay dormant: the Mac presentation was the clean emissive bolt above.
	ProjectileNiagara = CreateDefaultSubobject<UNiagaraComponent>(TEXT("ProjectileNiagara"));
	ProjectileNiagara->SetupAttachment(Collision);
	ProjectileNiagara->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	ProjectileNiagara->SetGenerateOverlapEvents(false);
	ProjectileNiagara->SetAutoActivate(false);
	ProjectileNiagara->SetVisibility(false);

	Movement = CreateDefaultSubobject<UProjectileMovementComponent>(TEXT("Movement"));
	// Rifle bolts need to feel snappy while strafing — 12 m/s was a slow lob; ~90 m/s hits fair.
	Movement->InitialSpeed = 9000.f;
	Movement->MaxSpeed = 9000.f;
	Movement->ProjectileGravityScale = 0.f;
	Movement->bRotationFollowsVelocity = false;  // we lock the beam flat ourselves in Tick
	Movement->bInitialVelocityInLocalSpace = true;

	// Cascade projectile FX (CPU-sim -> renders on Apple Silicon/Metal, unlike GPU Niagara). This is
	// the visible "cool bolt" from the ProjectilesVol1 pack; it flies attached to the bolt.
	// Optional projectile/impact effects from retired packs remain null.

	// Metal-safe Cascade explosion for impacts (the DMD Niagara impacts are GPU and don't render
	// on Apple Silicon, which is why ship hits showed no blast). Enabled per-bolt via SetImpactExplosion.

	// P_Hit_3 is the closest installed match to the former DMD blue impact and is authored
	// for unit scale; rifle profiles therefore use 1.0 rather than the retired DMD scale 8.
	static ConstructorHelpers::FObjectFinder<UNiagaraSystem> ImpactFXAsset(
		TEXT("/Game/ProjectilesVol1/Effects/P_Hit_3.P_Hit_3"));
	ImpactFX = ImpactFXAsset.Succeeded() ? ImpactFXAsset.Object : nullptr;

	// Two deliberately different paired profiles from ProjectilesVol1. Profile 17 is an
	// electricity/sphere system; profile 4 is the compact bullet + trail system. Loading both
	// here creates hard cooker references and avoids runtime soft-load regressions.
	static ConstructorHelpers::FObjectFinder<UNiagaraSystem> EnergyProjectileAsset(
		TEXT("/Game/ProjectilesVol1/Effects/P_Projectile_17.P_Projectile_17"));
	static ConstructorHelpers::FObjectFinder<UNiagaraSystem> EnergyImpactAsset(
		TEXT("/Game/ProjectilesVol1/Effects/P_Hit_17.P_Hit_17"));
	static ConstructorHelpers::FObjectFinder<UNiagaraSystem> RifleProjectileAsset(
		TEXT("/Game/ProjectilesVol1/Effects/P_Projectile_4.P_Projectile_4"));
	static ConstructorHelpers::FObjectFinder<UNiagaraSystem> RifleImpactAsset(
		TEXT("/Game/ProjectilesVol1/Effects/P_Hit_4.P_Hit_4"));
	EnergyProjectileFX = EnergyProjectileAsset.Succeeded() ? EnergyProjectileAsset.Object : nullptr;
	EnergyImpactFX = EnergyImpactAsset.Succeeded() ? EnergyImpactAsset.Object : nullptr;
	RifleProjectileFX = RifleProjectileAsset.Succeeded() ? RifleProjectileAsset.Object : nullptr;
	RifleImpactFX = RifleImpactAsset.Succeeded() ? RifleImpactAsset.Object : nullptr;

	// Blue projectile impact mark fallback.
	static ConstructorHelpers::FObjectFinder<UStaticMesh> ImpactMarkMeshAsset(
		TEXT("/Engine/BasicShapes/Plane.Plane"));
	if (ImpactMarkMeshAsset.Succeeded())
	{
		ImpactMarkMesh = ImpactMarkMeshAsset.Object;
	}
}

void ARedBolt::BeginPlay()
{
	Super::BeginPlay();
	ApplyBeamVisualProfile();

	// BP subclasses (BP_Projectile_*) serialize their component's response array from before the
	// Vehicle block existed — the ctor default is overridden by that saved data, so re-assert at
	// runtime: ships must be solid to every bolt, Blueprint or native.
	if (Collision)
	{
		if (HasAuthority())
		{
			Collision->SetCollisionResponseToChannel(ECC_Vehicle, ECR_Block);
			Collision->SetCollisionResponseToChannel(ECC_WorldDynamic, ECR_Block);
			Collision->SetCollisionResponseToChannel(ECC_PhysicsBody, ECR_Block);
			Collision->SetCollisionResponseToChannel(ECC_Pawn, ECR_Block);
		}
		else
		{
			// Only authority resolves hits. Proxy sweeps against independently streamed terrain
			// can otherwise stop ProjectileMovement and leave a visibly frozen client bolt.
			Collision->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			Collision->SetNotifyRigidBodyCollision(false);
		}
	}
	if (!HasAuthority() && Movement)
	{
		Movement->bSweepCollision = false;
	}
	if (Mesh)
	{
		Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Mesh->SetGenerateOverlapEvents(false);
		Mesh->SetComponentTickEnabled(false);
		// The bolt beam ALWAYS lies flat (horizontal), yawed along its travel direction — like a
		// floating log, no matter the aim pitch or camera angle. Absolute rotation so the projectile's
		// velocity-following rotation can never tip it up to vertical.
		Mesh->SetUsingAbsoluteRotation(true);
		Mesh->SetWorldRotation(GetActorRotation());
	}
	// Never collide with the firer — otherwise shooting straight up spawns the bolt inside
	// our own capsule, the sphere blocks instantly, and the bolt freezes in mid-air.
	if (AActor* Own = GetOwner())
	{
		Collision->IgnoreActorWhenMoving(Own, true);
	}
	if (AActor* Inst = GetInstigator())
	{
		Collision->IgnoreActorWhenMoving(Inst, true);
	}
}

void ARedBolt::LaunchWithVelocity(const FVector& WorldVelocity)
{
	if (Movement)
	{
		Movement->bInitialVelocityInLocalSpace = false;
		Movement->MaxSpeed = FMath::Max(Movement->MaxSpeed, (float)WorldVelocity.Size() * 1.05f);
		Movement->Velocity = WorldVelocity;
		Movement->UpdateComponentVelocity();
	}
}

void ARedBolt::SetBeamColor(const FLinearColor& InColor)
{
	BeamVisualProfile.Color = InColor;
	BeamVisualProfile.bOverrideColor = true;
	ApplyBeamVisualProfile();
	if (HasAuthority())
	{
		ForceNetUpdate();
	}
}

void ARedBolt::SetBeamDimensions(float InLengthScale, float InRadiusScale)
{
	BeamVisualProfile.LengthScale = FMath::Clamp(InLengthScale, 0.1f, 20.f);
	BeamVisualProfile.RadiusScale = FMath::Clamp(InRadiusScale, 0.02f, 2.f);
	ApplyBeamVisualProfile();
	if (HasAuthority())
	{
		ForceNetUpdate();
	}
}

void ARedBolt::SetEffectProfile(const uint8 InEffectProfile)
{
	BeamVisualProfile.EffectProfile = FMath::Min<uint8>(InEffectProfile, 2);
	ApplyBeamVisualProfile();
	if (HasAuthority())
	{
		ForceNetUpdate();
	}
}

void ARedBolt::OnRep_BeamVisualProfile()
{
	ApplyBeamVisualProfile();
}

void ARedBolt::ApplyBeamVisualProfile()
{
	if (!Mesh)
	{
		return;
	}

	const float Length = FMath::Clamp(BeamVisualProfile.LengthScale, 0.1f, 20.f);
	const float Radius = FMath::Clamp(BeamVisualProfile.RadiusScale, 0.02f, 2.f);
	Mesh->SetRelativeScale3D(FVector(Length, Radius, Radius));

	if (BeamVisualProfile.bOverrideColor)
	{
		if (!BeamMaterialInstance)
		{
			BeamMaterialInstance = Mesh->CreateAndSetMaterialInstanceDynamic(0);
		}
		if (BeamMaterialInstance)
		{
			BeamMaterialInstance->SetVectorParameterValue(TEXT("BoltColor"), BeamVisualProfile.Color);
		}
	}

	if (ProjectileNiagara)
	{
		UNiagaraSystem* SelectedProjectileFX = ResolveProjectileFX();
		if (ProjectileNiagara->GetAsset() != SelectedProjectileFX)
		{
			ProjectileNiagara->DeactivateImmediate();
			ProjectileNiagara->SetAsset(SelectedProjectileFX);
		}
		const bool bUsePackProjectile = SelectedProjectileFX != nullptr;
		ProjectileNiagara->SetVisibility(bUsePackProjectile, true);
		if (bUsePackProjectile && !ProjectileNiagara->IsActive())
		{
			ProjectileNiagara->Activate(true);
		}
	}
}

UNiagaraSystem* ARedBolt::ResolveProjectileFX() const
{
	switch (BeamVisualProfile.EffectProfile)
	{
	case 1: return EnergyProjectileFX;
	case 2: return RifleProjectileFX;
	default: return nullptr;
	}
}

UNiagaraSystem* ARedBolt::ResolveImpactFX() const
{
	switch (BeamVisualProfile.EffectProfile)
	{
	case 1: return EnergyImpactFX ? EnergyImpactFX : ImpactFX;
	case 2: return RifleImpactFX ? RifleImpactFX : ImpactFX;
	default: return ImpactFX;
	}
}

void ARedBolt::ConfigureImpactProfile(float InVisualScale, float InImpactScale, float InCraterRadius, float InDamage)
{
	const float ProfileScale = FMath::Max(0.2f, InVisualScale);
	SetActorScale3D(FVector::OneVector);
	if (Mesh && Mesh->GetStaticMesh())
	{
		const float BeamRadius = FMath::Clamp(FMath::Sqrt(ProfileScale) * 0.024f, 0.035f, 0.16f);
		const float BeamLength = FMath::Clamp(FMath::Sqrt(ProfileScale) * 0.38f, 0.42f, 2.2f);
		// LENGTH ON X: the ctor scale and the per-tick velocity alignment both treat local X as
		// the travel axis — the old (R, R, Length) put the beam PERPENDICULAR to flight, so every
		// configured bolt flew broadside ("vertical ones, not laying down horizontally").
		SetBeamDimensions(BeamLength, BeamRadius);
	}
	ImpactFXScale = FMath::Max(0.1f, InImpactScale);
	SurfaceDustScale = FMath::Max(0.1f, InImpactScale * 0.9f);
	CraterRadius = FMath::Max(20.f, InCraterRadius);
	Damage = FMath::Max(0.f, InDamage);
	if (Collision)
	{
		const float DesiredWorldRadius = FMath::Clamp(5.f + FMath::Sqrt(ProfileScale) * 1.6f, 6.f, 22.f);
		Collision->SetSphereRadius(DesiredWorldRadius, true);
	}
}

void ARedBolt::ConfigureGroundImpact(bool bInApplyVoxelCrater, bool bInSpawnCraterDecal, bool bInSpawnImpactMark)
{
	bApplyVoxelCrater = bInApplyVoxelCrater;
	bSpawnCraterDecal = bInSpawnCraterDecal;
	bSpawnImpactMark = bInSpawnImpactMark;
	bSpawnHeavyImpactFX = bInApplyVoxelCrater || bInSpawnCraterDecal || bInSpawnImpactMark;
}

void ARedBolt::OnHit(UPrimitiveComponent* /*HitComp*/, AActor* OtherActor, UPrimitiveComponent* /*OtherComp*/,
	FVector /*NormalImpulse*/, const FHitResult& Hit)
{
	if (bImpactProcessed || OtherActor == this || OtherActor == GetOwner())
	{
		return;
	}
	// Replicated client copies may predict this collision, but only the server owns the impact,
	// damage, terrain/resource mutations, and actor destruction.
	if (!HasAuthority())
	{
		return;
	}
	bImpactProcessed = true;

	if (ARedOrbitalMiningSite* MiningSite = Cast<ARedOrbitalMiningSite>(OtherActor))
	{
		const float MiningStrength = bApplyVoxelCrater
			? FMath::Max(Damage * 6.0f, CraterRadius * 0.15f)
			: Damage;
		MiningSite->RegisterMiningHit(Hit, MiningStrength, GetOwner() ? GetOwner() : GetInstigator());
	}
	else if (ARedMineableAsteroid* MineableAsteroid = Cast<ARedMineableAsteroid>(OtherActor))
	{
		const float MiningStrength = bApplyVoxelCrater
			? FMath::Max(1.f, CraterRadius * 0.02f)
			: FMath::Max(1.f, Damage);
		MineableAsteroid->RegisterMiningHit(MiningStrength,
			GetOwner() ? GetOwner() : GetInstigator());
	}

	// Spawn the impact burst at the hit point, oriented away from the surface.
	const float ProfileScale = FMath::Max(0.1f, ImpactFXScale);
	if (UNiagaraSystem* SelectedImpactFX = ResolveImpactFX())
	{
		UNiagaraFunctionLibrary::SpawnSystemAtLocation(GetWorld(), SelectedImpactFX, Hit.ImpactPoint,
			Hit.ImpactNormal.Rotation(), FVector(ProfileScale), true);
	}
	if (bSpawnHeavyImpactFX && HeavyImpactFX && ProfileScale >= 2.f)
	{
		UNiagaraFunctionLibrary::SpawnSystemAtLocation(GetWorld(), HeavyImpactFX, Hit.ImpactPoint,
			Hit.ImpactNormal.Rotation(), FVector(ProfileScale * 0.75f), true);
	}
	// Metal-safe Cascade blast (ship cannon) — a real visible explosion where GPU Niagara can't render.
	if (bSpawnImpactExplosion && ImpactExplosionCascade)
	{
		UGameplayStatics::SpawnEmitterAtLocation(GetWorld(), ImpactExplosionCascade, Hit.ImpactPoint,
			Hit.ImpactNormal.Rotation(), FVector(FMath::Clamp(ProfileScale, 1.f, 3.f)), true);
	}
	const bool bHitPawn = OtherActor && Cast<APawn>(OtherActor);
	if (!bHitPawn && Hit.bBlockingHit)
	{
		if (bApplyVoxelCrater)
		{
			SpawnVoxelCraterStamp(Hit);
			if (bDropMinedResource)
			{
				SpawnMinedResource(Hit);
			}
		}

		if (SurfaceDustFX)
		{
			const float DustScale = ProfileScale >= 2.f ? SurfaceDustScale * 1.65f : SurfaceDustScale;
			UNiagaraFunctionLibrary::SpawnSystemAtLocation(GetWorld(), SurfaceDustFX,
				Hit.ImpactPoint + Hit.ImpactNormal * 4.f, Hit.ImpactNormal.Rotation(),
				FVector(DustScale), true);
		}
		if (bSpawnCraterDecal && CanSpawnCraterDecal())
		{
			const float Radius = FMath::Max(30.f, CraterRadius);
			const float ProjectionDepth = FMath::Clamp(Radius * 0.28f, 48.f, 520.f);
			if (UDecalComponent* CraterDecal = UGameplayStatics::SpawnDecalAtLocation(
				GetWorld(),
				CraterDecalMaterial,
				FVector(ProjectionDepth, Radius, Radius),
				Hit.ImpactPoint + Hit.ImpactNormal * 8.f,
				Hit.ImpactNormal.Rotation(),
				CraterLifeSpan))
			{
				CraterDecal->SetFadeOut(CraterLifeSpan * 0.72f, CraterLifeSpan * 0.28f, false);
			}
		}
		if (bSpawnImpactMark && ImpactMarkMesh && ImpactMarkMaterial && GetWorld())
		{
			FVector SurfaceNormal = Hit.ImpactNormal.GetSafeNormal();
			if (SurfaceNormal.IsNearlyZero())
			{
				SurfaceNormal = FVector::UpVector;
			}
			const FQuat AlignToSurface = FQuat::FindBetweenNormals(FVector::UpVector, SurfaceNormal);
			const FQuat RandomSpin(SurfaceNormal, FMath::FRandRange(-PI, PI));
			const float Radius = FMath::Max(40.f, CraterRadius);
			const float PlaneScale = Radius / 50.f; // Engine plane is roughly 100cm wide.

			FActorSpawnParameters MarkParams;
			MarkParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			AStaticMeshActor* ImpactMark = GetWorld()->SpawnActor<AStaticMeshActor>(
				AStaticMeshActor::StaticClass(),
				Hit.ImpactPoint + SurfaceNormal * 5.f,
				(RandomSpin * AlignToSurface).Rotator(),
				MarkParams);
			if (ImpactMark && ImpactMark->GetStaticMeshComponent())
			{
				UStaticMeshComponent* MarkMesh = ImpactMark->GetStaticMeshComponent();
				MarkMesh->SetMobility(EComponentMobility::Movable);
				MarkMesh->SetStaticMesh(ImpactMarkMesh);
				MarkMesh->SetMaterial(0, ImpactMarkMaterial);
				MarkMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
				MarkMesh->SetGenerateOverlapEvents(false);
				MarkMesh->SetCastShadow(false);
				MarkMesh->SetReceivesDecals(false);
				ImpactMark->SetActorScale3D(FVector(PlaneScale, PlaneScale, 1.f));
				ImpactMark->SetActorEnableCollision(false);
				ImpactMark->SetLifeSpan(CraterLifeSpan);
			}
		}
	}
	MulticastImpactCosmetics(Hit.ImpactPoint, Hit.ImpactNormal.GetSafeNormal(),
		BeamVisualProfile.EffectProfile, ProfileScale,
		SurfaceDustScale, CraterRadius, bSpawnHeavyImpactFX, bSpawnImpactExplosion,
		bSpawnCraterDecal, bSpawnImpactMark, bHitPawn);

	// Damage is server-authoritative. Replicated client copies still render the impact but must not
	// mutate local health independently of the server.
	if (HasAuthority() && OtherActor)
	{
		AController* Inst = GetInstigatorController();
		FDamageEvent DmgEvent;
		OtherActor->TakeDamage(Damage, DmgEvent, Inst, this);
	}
	// Consume the visible/colliding bolt immediately, but retain its actor channel briefly so the
	// reliable impact multicast is delivered before server destruction closes that channel.
	DisableAfterImpact();
	ForceNetUpdate();
	SetLifeSpan(0.20f);
}

void ARedBolt::MulticastImpactCosmetics_Implementation(FVector_NetQuantize ImpactPoint,
	FVector_NetQuantizeNormal ImpactNormal, uint8 InEffectProfile,
	float InProfileScale, float InSurfaceDustScale,
	float InCraterRadius, bool bInSpawnHeavyImpactFX, bool bInSpawnImpactExplosion,
	bool bInSpawnCraterDecal, bool bInSpawnImpactMark, bool bHitPawn)
{
	// The authority already ran the original full impact path in OnHit. This multicast supplies
	// the same server-selected contact point to remote clients without allowing client collision
	// callbacks to destroy or damage the replicated bolt independently.
	if (HasAuthority() || !GetWorld())
	{
		return;
	}
	BeamVisualProfile.EffectProfile = FMath::Min<uint8>(InEffectProfile, 2);
	ApplyBeamVisualProfile();
	DisableAfterImpact();

	const FVector Point = ImpactPoint;
	FVector SurfaceNormal = FVector(ImpactNormal).GetSafeNormal();
	if (SurfaceNormal.IsNearlyZero())
	{
		SurfaceNormal = FVector::UpVector;
	}
	const FRotator ImpactRotation = SurfaceNormal.Rotation();
	const float ProfileScale = FMath::Max(0.1f, InProfileScale);

	if (UNiagaraSystem* SelectedImpactFX = ResolveImpactFX())
	{
		UNiagaraFunctionLibrary::SpawnSystemAtLocation(GetWorld(), SelectedImpactFX, Point,
			ImpactRotation, FVector(ProfileScale), true);
	}
	if (bInSpawnHeavyImpactFX && HeavyImpactFX && ProfileScale >= 2.f)
	{
		UNiagaraFunctionLibrary::SpawnSystemAtLocation(GetWorld(), HeavyImpactFX, Point,
			ImpactRotation, FVector(ProfileScale * 0.75f), true);
	}
	if (bInSpawnImpactExplosion && ImpactExplosionCascade)
	{
		UGameplayStatics::SpawnEmitterAtLocation(GetWorld(), ImpactExplosionCascade, Point,
			ImpactRotation, FVector(FMath::Clamp(ProfileScale, 1.f, 3.f)), true);
	}
	if (bHitPawn)
	{
		return;
	}

	if (SurfaceDustFX)
	{
		const float DustScale = ProfileScale >= 2.f ? InSurfaceDustScale * 1.65f : InSurfaceDustScale;
		UNiagaraFunctionLibrary::SpawnSystemAtLocation(GetWorld(), SurfaceDustFX,
			Point + SurfaceNormal * 4.f, ImpactRotation, FVector(DustScale), true);
	}
	if (bInSpawnCraterDecal && CanSpawnCraterDecal())
	{
		const float Radius = FMath::Max(30.f, InCraterRadius);
		const float ProjectionDepth = FMath::Clamp(Radius * 0.28f, 48.f, 520.f);
		if (UDecalComponent* CraterDecal = UGameplayStatics::SpawnDecalAtLocation(
			GetWorld(), CraterDecalMaterial, FVector(ProjectionDepth, Radius, Radius),
			Point + SurfaceNormal * 8.f, ImpactRotation, CraterLifeSpan))
		{
			CraterDecal->SetFadeOut(CraterLifeSpan * 0.72f, CraterLifeSpan * 0.28f, false);
		}
	}
	if (bInSpawnImpactMark && ImpactMarkMesh && ImpactMarkMaterial)
	{
		const FQuat AlignToSurface = FQuat::FindBetweenNormals(FVector::UpVector, SurfaceNormal);
		const FQuat RandomSpin(SurfaceNormal, FMath::FRandRange(-PI, PI));
		const float Radius = FMath::Max(40.f, InCraterRadius);
		const float PlaneScale = Radius / 50.f;

		FActorSpawnParameters MarkParams;
		MarkParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		AStaticMeshActor* ImpactMark = GetWorld()->SpawnActor<AStaticMeshActor>(
			AStaticMeshActor::StaticClass(), Point + SurfaceNormal * 5.f,
			(RandomSpin * AlignToSurface).Rotator(), MarkParams);
		if (ImpactMark && ImpactMark->GetStaticMeshComponent())
		{
			UStaticMeshComponent* MarkMesh = ImpactMark->GetStaticMeshComponent();
			MarkMesh->SetMobility(EComponentMobility::Movable);
			MarkMesh->SetStaticMesh(ImpactMarkMesh);
			MarkMesh->SetMaterial(0, ImpactMarkMaterial);
			MarkMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			MarkMesh->SetGenerateOverlapEvents(false);
			MarkMesh->SetCastShadow(false);
			MarkMesh->SetReceivesDecals(false);
			ImpactMark->SetActorScale3D(FVector(PlaneScale, PlaneScale, 1.f));
			ImpactMark->SetActorEnableCollision(false);
			ImpactMark->SetLifeSpan(CraterLifeSpan);
		}
	}
}

void ARedBolt::DisableAfterImpact()
{
	bImpactProcessed = true;
	if (Collision)
	{
		Collision->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Collision->SetNotifyRigidBodyCollision(false);
	}
	if (Movement)
	{
		Movement->StopMovementImmediately();
		Movement->Deactivate();
	}
	if (Mesh)
	{
		Mesh->SetVisibility(false, true);
	}
	if (ProjectileNiagara)
	{
		ProjectileNiagara->Deactivate();
		ProjectileNiagara->SetVisibility(false, true);
	}
}

void ARedBolt::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(ARedBolt, BeamVisualProfile);
}

void ARedBolt::SpawnMinedResource(const FHitResult& Hit)
{
	if (!GetWorld() || !Hit.bBlockingHit)
	{
		return;
	}

	// Depth below the surface = how far under the reference radius the hit landed.
	const float HitRadius = (Hit.ImpactPoint - PlanetCenter).Size();
	const float DepthBelow = PlanetBaseRadius - HitRadius;

	// Ignore hits well above the surface (e.g. structures) — only planet mining yields resources.
	if (DepthBelow < -600.f)
	{
		return;
	}

	const ERedResourceType Type = ARedResourcePickup::TypeForDepth(DepthBelow);

	FVector SurfaceNormal = Hit.ImpactNormal.GetSafeNormal();
	if (SurfaceNormal.IsNearlyZero())
	{
		SurfaceNormal = (Hit.ImpactPoint - PlanetCenter).GetSafeNormal();
	}

	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	ARedResourcePickup* Pickup = GetWorld()->SpawnActor<ARedResourcePickup>(
		ARedResourcePickup::StaticClass(),
		Hit.ImpactPoint + SurfaceNormal * 45.f,
		SurfaceNormal.Rotation(),
		Params);
	if (Pickup)
	{
		Pickup->InitResource(Type, 1, PlanetCenter);
	}
}

bool ARedBolt::CanSpawnCraterDecal() const
{
	if (!CraterDecalMaterial)
	{
		return false;
	}

	const UMaterial* Material = CraterDecalMaterial->GetMaterial();
	return Material && Material->MaterialDomain == MD_DeferredDecal;
}

void ARedBolt::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	// Align the beam along its actual flight direction. (The old "world-horizontal" lock only made
	// sense near the spawn pole — on the far side of the sphere, world-flat points at the SKY, so
	// the stretched tracer looked like bolts raining down from above.)
	if (Mesh)
	{
		const FVector Vel = GetVelocity();
		if (!Vel.IsNearlyZero())
		{
			Mesh->SetWorldRotation(Vel.GetSafeNormal().Rotation());
		}
	}
}

void ARedBolt::SpawnVoxelCraterStamp(const FHitResult& Hit)
{
	(void)Hit;
	// Runtime terrain deformation is disabled while the project runs without the Voxel plugin.
}
