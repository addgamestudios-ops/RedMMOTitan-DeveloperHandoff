#include "RedMiniFighter.h"

#include "Components/BoxComponent.h"
#include "Components/InputComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "EngineUtils.h"
#include "GameFramework/Controller.h"
#include "GameFramework/PlayerController.h"
#include "InputCoreTypes.h"
#include "Materials/MaterialInterface.h"
#include "Math/RotationMatrix.h"
#include "Net/UnrealNetwork.h"
#include "RedShipCollisionDriver.h"
#include "RedShipMovementComponent.h"
#include "RedShuttleBase.h"
#include "RedSpaceDust.h"
#include "UObject/ConstructorHelpers.h"

DEFINE_LOG_CATEGORY_STATIC(LogRedMiniFighter, Log, All);

namespace RedMiniFighterPrivate
{
	static float AabbSupport(const FVector& WorldExtent, const FVector& Direction)
	{
		return FVector::DotProduct(WorldExtent, Direction.GetSafeNormal().GetAbs());
	}

	static void ConfigureModule(UStaticMeshComponent* Component, UStaticMesh* Mesh,
		UMaterialInterface* Material, const float Scale)
	{
		if (!Component)
		{
			return;
		}
		Component->SetStaticMesh(Mesh);
		// Use the StarSparrow asset's authored convex collision for shots and grapple traces.  Pawn
		// floor contact is handled by the much smaller central deck helper below, avoiding a broad
		// invisible shelf across the fins and wings.
		Component->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
		Component->SetCollisionObjectType(ECC_Vehicle);
		Component->SetCollisionResponseToAllChannels(ECR_Ignore);
		Component->SetCollisionResponseToChannel(ECC_Visibility, ECR_Block);
		Component->SetCollisionResponseToChannel(ECC_WorldDynamic, ECR_Block);
		Component->SetCollisionResponseToChannel(ECC_PhysicsBody, ECR_Block);
		Component->SetGenerateOverlapEvents(false);
		Component->SetCanEverAffectNavigation(false);
		Component->CanCharacterStepUpOn = ECB_No;
		Component->SetRelativeLocation(FVector::ZeroVector);
		Component->SetRelativeRotation(FRotator::ZeroRotator);
		Component->SetRelativeScale3D(FVector(Scale));
		if (Mesh && Material)
		{
			const int32 MaterialSlots = FMath::Max(1, Mesh->GetStaticMaterials().Num());
			for (int32 Slot = 0; Slot < MaterialSlots; ++Slot)
			{
				Component->SetMaterial(Slot, Material);
			}
		}
	}
}

ARedMiniFighter::ARedMiniFighter()
{
	// This class keeps the ARedShip visual anchor/camera/movement but replaces its placeholder hull
	// with the actual StarSparrow modular layers. Hard references guarantee the parts are cooked.
	// StarSparrow module assets point along local +X. The generic ship's -90 degree art yaw is
	// correct for SM_ship (+Y nose), but turned this modular craft sideways to its flight vector.
	MeshYaw = 0.f;
	MeshForwardAxis = FVector::XAxisVector;
	if (Hull)
	{
		Hull->SetStaticMesh(nullptr);
		Hull->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Hull->SetRelativeLocation(FVector::ZeroVector);
		Hull->SetRelativeRotation(FRotator::ZeroRotator);
	}

	auto MakeModule = [this](const TCHAR* Name) -> UStaticMeshComponent*
	{
		UStaticMeshComponent* Module = CreateDefaultSubobject<UStaticMeshComponent>(Name);
		Module->SetupAttachment(Hull ? static_cast<USceneComponent*>(Hull) : GetRootComponent());
		return Module;
	};

	CoreModule = MakeModule(TEXT("Mini_Core"));
	Wing01Module = MakeModule(TEXT("Mini_Wing01"));
	Wing02Module = MakeModule(TEXT("Mini_Wing02"));
	Wing03Module = MakeModule(TEXT("Mini_Wing03"));
	EngineModule = MakeModule(TEXT("Mini_Engine"));
	ThrusterModule = MakeModule(TEXT("Mini_Thruster"));
	WeaponModule = MakeModule(TEXT("Mini_Weapon"));
	PlasmaModule = MakeModule(TEXT("Mini_Plasma"));

	// The inherited speed field is made from ordinary cube instances. Viewed end-on from this
	// short chase camera, a nearby instance reads as a black square that follows the fighter.
	// Disable it only for the compact craft; full-size ships retain their existing speed effect.
	if (SpaceDust)
	{
		SpaceDust->StreakCount = 0;
		SpaceDust->SetAutoActivate(false);
		SpaceDust->SetComponentTickEnabled(false);
	}

	// A small craft made mostly from black modules disappears on the planet's night side. This
	// movable, shadowless local fill rotates with the fighter and has a short radius, so it reveals
	// the silhouette without lighting the wider environment or creating a visible helper mesh.
	ReadabilityFillLight = CreateDefaultSubobject<UPointLightComponent>(TEXT("Mini_ReadabilityFill"));
	ReadabilityFillLight->SetupAttachment(CollisionSphere);
	ReadabilityFillLight->SetMobility(EComponentMobility::Movable);
	ReadabilityFillLight->SetRelativeLocation(FVector(-140.f, 0.f, 320.f));
	ReadabilityFillLight->SetIntensity(3500.f);
	ReadabilityFillLight->SetLightColor(FLinearColor(0.20f, 0.48f, 1.0f));
	ReadabilityFillLight->SetAttenuationRadius(1100.f);
	ReadabilityFillLight->SetCastShadows(false);

	static ConstructorHelpers::FObjectFinder<UStaticMesh> CoreMesh(
		TEXT("/Game/StarSparrow/Meshes/Modules/SM_Parts_StarSparrow_Core.SM_Parts_StarSparrow_Core"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Wing01Mesh(
		TEXT("/Game/StarSparrow/Meshes/Modules/SM_Parts_StarSparrow_Wing_01.SM_Parts_StarSparrow_Wing_01"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Wing02Mesh(
		TEXT("/Game/StarSparrow/Meshes/Modules/SM_Parts_StarSparrow_Wing_02.SM_Parts_StarSparrow_Wing_02"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Wing03Mesh(
		TEXT("/Game/StarSparrow/Meshes/Modules/SM_Parts_StarSparrow_Wing_03.SM_Parts_StarSparrow_Wing_03"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> EngineMesh(
		TEXT("/Game/StarSparrow/Meshes/Modules/SM_Parts_StarSparrow_Engine.SM_Parts_StarSparrow_Engine"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> ThrusterMesh(
		TEXT("/Game/StarSparrow/Meshes/Modules/SM_Parts_StarSparrow_Thruster.SM_Parts_StarSparrow_Thruster"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> WeaponMesh(
		TEXT("/Game/StarSparrow/Meshes/Modules/SM_Parts_StarSparrow_Weapon.SM_Parts_StarSparrow_Weapon"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> PlasmaMesh(
		TEXT("/Game/StarSparrow/Meshes/Modules/SM_Parts_StarSparrow_Plasma.SM_Parts_StarSparrow_Plasma"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> RedMaterial(
		TEXT("/Game/StarSparrow/Materials/MI_StarSparrow_Red.MI_StarSparrow_Red"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> BlackMaterial(
		TEXT("/Game/StarSparrow/Materials/MI_StarSparrow_Black.MI_StarSparrow_Black"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> CyanMaterial(
		TEXT("/Game/StarSparrow/Materials/MI_StarSparrow_Cyan.MI_StarSparrow_Cyan"));

	RedMiniFighterPrivate::ConfigureModule(CoreModule, CoreMesh.Object,
		RedMaterial.Object, CompactArtScale);
	RedMiniFighterPrivate::ConfigureModule(Wing01Module, Wing01Mesh.Object,
		RedMaterial.Object, CompactArtScale);
	RedMiniFighterPrivate::ConfigureModule(Wing02Module, Wing02Mesh.Object,
		RedMaterial.Object, CompactArtScale);
	RedMiniFighterPrivate::ConfigureModule(Wing03Module, Wing03Mesh.Object,
		BlackMaterial.Object, CompactArtScale);
	RedMiniFighterPrivate::ConfigureModule(EngineModule, EngineMesh.Object,
		BlackMaterial.Object, CompactArtScale);
	RedMiniFighterPrivate::ConfigureModule(ThrusterModule, ThrusterMesh.Object,
		BlackMaterial.Object, CompactArtScale);
	RedMiniFighterPrivate::ConfigureModule(WeaponModule, WeaponMesh.Object,
		BlackMaterial.Object, CompactArtScale);
	RedMiniFighterPrivate::ConfigureModule(PlasmaModule, PlasmaMesh.Object,
		CyanMaterial.Object, CompactArtScale);

	// Compact interceptor tuning: lower durability and collision mass, faster turn/cruise, quick guns.
	MaxHealth = 850.f;
	Health = MaxHealth;
	FighterCruiseSpeed = 16500.f;
	FireInterval = 0.11f;
	HeatPerShot = 11.f;
	HeatCooldownPerSecond = 32.f;
	MinFireAimDot = 0.62f;
	ChaseArmLength = 2700.f;
	ChaseCameraOffset = FVector(0.f, 0.f, 430.f);
	FirstPersonArmLength = 0.f;
	FirstPersonCameraOffset = FVector(360.f, 0.f, 105.f);
	BaseFOV = 94.f;
	BoostFOV = 111.f;
	OrbitalExitMinAltitude = 1000000.f;

	if (CollisionSphere)
	{
		CollisionSphere->SetSphereRadius(145.f, false);
	}
	if (RuntimeHullCollision)
	{
		RuntimeHullCollision->SetBoxExtent(FVector(480.f, 390.f, 155.f), false);
		RuntimeHullCollision->SetRelativeLocation(FVector::ZeroVector);
	}
	if (RuntimeDeckCollision)
	{
		RuntimeDeckCollision->SetBoxExtent(FVector(280.f, 210.f, 15.f), false);
		RuntimeDeckCollision->SetRelativeLocation(FVector(0.f, 0.f, 170.f));
	}
	if (ShipMovement)
	{
		ShipMovement->FallbackMaxSpeed = FighterCruiseSpeed;
		ShipMovement->ResponsivenessAtmosphere = 7.5f;
		ShipMovement->ResponsivenessSpace = 3.3f;
		ShipMovement->PitchRateDeg = 115.f;
		ShipMovement->YawRateDeg = 92.f;
		ShipMovement->RollRateDeg = 155.f;
		ShipMovement->BoostSpeedMultiplier = 1.5f;
		ShipMovement->MinimumSurfaceClearance = 180.f;
	}

	ApplyMiniFighterHardpoints();
}

void ARedMiniFighter::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	ApplyCompactModuleLayout();
	ApplyMiniFighterHardpoints();
}

void ARedMiniFighter::BeginPlay()
{
	Super::BeginPlay();
	// Component BeginPlay may still construct its cosmetic HISM even with auto activation off.
	// Reassert hidden/no-tick state so no inherited cube can become visible on this fighter.
	if (SpaceDust)
	{
		SpaceDust->SetComponentTickEnabled(false);
		SpaceDust->SetVisibility(false, true);
	}
	ApplyCompactModuleLayout();
	ApplyMiniFighterHardpoints();
	UE_LOG(LogRedMiniFighter, Display,
		TEXT("Compact collision restored on %s: hull extent=%s deck extent=%s"),
		*GetNameSafe(this),
		RuntimeHullCollision ? *RuntimeHullCollision->GetUnscaledBoxExtent().ToCompactString() : TEXT("none"),
		RuntimeDeckCollision ? *RuntimeDeckCollision->GetUnscaledBoxExtent().ToCompactString() : TEXT("none"));
	if (DockParent)
	{
		ApplyDockedPresentation();
	}
}

bool ARedMiniFighter::ConfigureRuntimeCollisionHulls()
{
	// ARedShip normally derives a box from every registered visual mesh. StarSparrow is a
	// co-origin stack of modular layers, and during runtime spawning those components can report
	// one-frame stale bounds in the planet frame. That previously produced a transient collision
	// box hundreds of kilometres tall before BeginPlay restored the compact values, which is the
	// source of the invisible walkway behind a newly spawned fighter. Use the fighter's authored
	// physical envelope from the first base BeginPlay call onward instead.
	ApplyCompactModuleLayout();
	return RuntimeHullCollision && RuntimeDeckCollision && CollisionSphere;
}

void ARedMiniFighter::PossessedBy(AController* NewController)
{
	Super::PossessedBy(NewController);

	// Boarding an unoccupied fighter in the shuttle bay must select and launch this pawn, not
	// leave the controller attached to a movement-disabled child of the shuttle. Possession only
	// happens on the authority, after ARedShip has accepted the pilot, so this cannot be spoofed by
	// a client proximity request and cannot undock an occupied craft on somebody else's request.
	if (HasAuthority() && DockParent && NewController && NewController->IsPlayerController())
	{
		UndockAuthority();
	}
}

void ARedMiniFighter::Tick(const float DeltaSeconds)
{
	// MovementComponent ticks independently from the actor, so DockToParent deactivates it too.
	// Avoiding the base tick also suspends weapons/heat/camera interpolation while hard-docked.
	if (DockParent && !IsValidDockParent(DockParent))
	{
		// A destroyed carrier, or a shuttle whose hull reached zero, must not leave the
		// fighter permanently attached with movement and collision disabled.
		if (HasAuthority())
		{
			DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);
			DockParent = nullptr;
			bLandingAssistEnabled = false;
			bLandingSettled = false;
			ApplyUndockedPresentation();
			FlushNetDormancy();
			ForceNetUpdate();
		}
		else
		{
			// The server owns DockParent. Wait for its replicated clear before re-enabling
			// local movement so the client cannot briefly fly an attached fighter.
			return;
		}
	}
	if (DockParent)
	{
		if (GetAttachParentActor() != DockParent)
		{
			ApplyDockedPresentation();
		}
		return;
	}
	Super::Tick(DeltaSeconds);
	// This compact hull has one centered exhaust bell. ARedShip owns four legacy plume components;
	// keep exactly the first and suppress the unused three after the base visual update.
	for (int32 Index = 1; Index < Plumes.Num(); ++Index)
	{
		if (UStaticMeshComponent* Plume = Plumes[Index])
		{
			Plume->SetVisibility(false, true);
			Plume->SetHiddenInGame(true, true);
		}
	}
}

void ARedMiniFighter::SetupPlayerInputComponent(UInputComponent* InInput)
{
	Super::SetupPlayerInputComponent(InInput);
	if (InInput)
	{
		// Direct key binding keeps R independent of character reload mappings; RedMMO weapons use heat.
		InInput->BindKey(EKeys::R, IE_Pressed, this, &ARedMiniFighter::HandleDockInput);
	}
}

void ARedMiniFighter::ApplyCompactModuleLayout()
{
	if (Hull)
	{
		// ARedShip offsets its full-size placeholder downward; co-origin modules must stay centered.
		Hull->SetRelativeLocation(FVector::ZeroVector);
		Hull->SetRelativeRotation(FRotator::ZeroRotator);
		Hull->SetStaticMesh(nullptr);
		Hull->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	}
	UStaticMeshComponent* const Modules[] = {
		CoreModule.Get(), Wing01Module.Get(), Wing02Module.Get(), Wing03Module.Get(),
		EngineModule.Get(), ThrusterModule.Get(), WeaponModule.Get(), PlasmaModule.Get()
	};
	for (UStaticMeshComponent* Module : Modules)
	{
		if (Module)
		{
			Module->SetRelativeLocation(FVector::ZeroVector);
			Module->SetRelativeRotation(FRotator::ZeroRotator);
			Module->SetRelativeScale3D(FVector(CompactArtScale));
			Module->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
			Module->SetCollisionObjectType(ECC_Vehicle);
			Module->SetCollisionResponseToAllChannels(ECR_Ignore);
			Module->SetCollisionResponseToChannel(ECC_Visibility, ECR_Block);
			Module->SetCollisionResponseToChannel(ECC_WorldDynamic, ECR_Block);
			Module->SetCollisionResponseToChannel(ECC_PhysicsBody, ECR_Block);
			Module->SetGenerateOverlapEvents(false);
			Module->CanCharacterStepUpOn = ECB_No;
		}
	}

	// Merge asset-local bounds, never component world bounds. This keeps the physical envelope
	// compact even when the fighter is spawned while attached to a planet-relative shuttle.
	FBox ModuleBounds(ForceInit);
	FBox CoreBounds(ForceInit);
	for (UStaticMeshComponent* Module : Modules)
	{
		if (Module && Module->GetStaticMesh())
		{
			const FBox LayerBounds = Module->GetStaticMesh()->GetBoundingBox().TransformBy(
				Module->GetRelativeTransform());
			ModuleBounds += LayerBounds;
			if (Module == CoreModule.Get())
			{
				CoreBounds += LayerBounds;
			}
		}
	}
	FVector BodyCenter = FVector::ZeroVector;
	FVector BodyExtent(360.f, 240.f, 125.f);
	if (ModuleBounds.IsValid && !ModuleBounds.GetCenter().ContainsNaN()
		&& !ModuleBounds.GetExtent().ContainsNaN())
	{
		BodyCenter = ModuleBounds.GetCenter();
		const FVector RawExtent = ModuleBounds.GetExtent() + FVector(12.f);
		BodyExtent = FVector(
			FMath::Clamp(RawExtent.X, 180.f, 650.f),
			FMath::Clamp(RawExtent.Y, 100.f, 450.f),
			FMath::Clamp(RawExtent.Z, 60.f, 220.f));
	}
	if (RuntimeHullCollision)
	{
		RuntimeHullCollision->SetRelativeLocation(BodyCenter);
		RuntimeHullCollision->SetRelativeRotation(FRotator::ZeroRotator);
		RuntimeHullCollision->SetBoxExtent(BodyExtent, false);
	}
	if (RuntimeDeckCollision)
	{
		const FBox& WalkableBounds = CoreBounds.IsValid ? CoreBounds : ModuleBounds;
		const FVector WalkableCenter = WalkableBounds.IsValid
			? WalkableBounds.GetCenter() : BodyCenter;
		const FVector WalkableExtent = WalkableBounds.IsValid
			? WalkableBounds.GetExtent() : BodyExtent;
		const float DeckHalfHeight = 8.f;
		const float DeckSurfaceZ = WalkableBounds.IsValid
			? WalkableBounds.Max.Z - 3.f : BodyCenter.Z + BodyExtent.Z - 3.f;
		RuntimeDeckCollision->SetRelativeLocation(FVector(WalkableCenter.X, WalkableCenter.Y,
			DeckSurfaceZ - DeckHalfHeight));
		RuntimeDeckCollision->SetRelativeRotation(FRotator::ZeroRotator);
		RuntimeDeckCollision->SetBoxExtent(FVector(
			FMath::Clamp(WalkableExtent.X * 0.78f, 70.f, BodyExtent.X * 0.66f),
			FMath::Clamp(WalkableExtent.Y * 0.68f, 45.f, BodyExtent.Y * 0.60f),
			DeckHalfHeight), false);
		// Pawn-only: detailed module convexes catch shots/traces while this helper only stabilizes
		// character floor contact over the central fuselage.
		RuntimeDeckCollision->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
		RuntimeDeckCollision->SetCollisionObjectType(ECC_Vehicle);
		RuntimeDeckCollision->SetCollisionResponseToAllChannels(ECR_Ignore);
		RuntimeDeckCollision->SetCollisionResponseToChannel(ECC_Pawn, ECR_Block);
		RuntimeDeckCollision->SetGenerateOverlapEvents(false);
		RuntimeDeckCollision->SetCanEverAffectNavigation(false);
		RuntimeDeckCollision->CanCharacterStepUpOn = ECB_Yes;
	}
}

void ARedMiniFighter::ApplyMiniFighterHardpoints()
{
	// Module-native axes: nose +X, rear -X, right +Y, up +Z. Only index zero is visible.
	static const FVector MiniPlumeOffset(-570.f, 0.f, 15.f);
	for (int32 Index = 0; Index < PlumeHardpoints.Num(); ++Index)
	{
		if (USceneComponent* Hardpoint = PlumeHardpoints[Index].Get())
		{
			Hardpoint->SetRelativeLocation(MiniPlumeOffset);
			Hardpoint->SetRelativeRotation(FRotator::ZeroRotator);
		}
	}
	for (int32 Index = 0; Index < Plumes.Num(); ++Index)
	{
		if (UStaticMeshComponent* Plume = Plumes[Index])
		{
			Plume->SetRelativeRotation(
				FRotationMatrix::MakeFromX(-FVector::XAxisVector).Rotator());
			if (Index > 0)
			{
				Plume->SetVisibility(false, true);
				Plume->SetHiddenInGame(true, true);
			}
		}
	}

	const FRotator ForwardRotation = FVector::XAxisVector.Rotation();
	if (TurretMuzzleLeft)
	{
		TurretMuzzleLeft->SetRelativeLocation(FVector(625.f, -185.f, 35.f));
		TurretMuzzleLeft->SetRelativeRotation(ForwardRotation);
	}
	if (TurretMuzzleRight)
	{
		TurretMuzzleRight->SetRelativeLocation(FVector(625.f, 185.f, 35.f));
		TurretMuzzleRight->SetRelativeRotation(ForwardRotation);
	}
}

void ARedMiniFighter::HandleDockInput()
{
	if (HasAuthority())
	{
		ToggleDockingAuthority();
	}
	else
	{
		ServerToggleDocking();
	}
}

void ARedMiniFighter::ServerToggleDocking_Implementation()
{
	// Ownership of a possessed pawn already gates this RPC to its controlling connection.
	// Recheck the controller and all spatial/speed constraints on the authority.
	if (!Controller || !Controller->IsPlayerController() || Health <= 0.f)
	{
		return;
	}
	ToggleDockingAuthority();
}

void ARedMiniFighter::ToggleDockingAuthority()
{
	if (!HasAuthority() || !Controller || !Controller->IsPlayerController() || Health <= 0.f)
	{
		return;
	}
	if (DockParent)
	{
		UndockAuthority();
		return;
	}

	AActor* Candidate = FindBestDockParent();
	if (!Candidate)
	{
		UE_LOG(LogRedMiniFighter, Display,
			TEXT("Dock request rejected for %s: no valid rear bay in range"), *GetName());
		return;
	}
	const FTransform DockTransform = BuildRearBayTransform(Candidate, false);
	const float DockDistance = FVector::Distance(GetActorLocation(), DockTransform.GetLocation());
	const float RelativeSpeed = (GetVelocity() - Candidate->GetVelocity()).Size();
	if (DockDistance > FMath::Max(100.f, DockingRange)
		|| RelativeSpeed > FMath::Max(0.f, MaxDockingRelativeSpeed))
	{
		UE_LOG(LogRedMiniFighter, Display,
			TEXT("Dock request rejected for %s: distance %.0f/%.0f, relative speed %.0f/%.0f"),
			*GetName(), DockDistance, DockingRange, RelativeSpeed, MaxDockingRelativeSpeed);
		return;
	}
	DockToParent(Candidate);
}

bool ARedMiniFighter::DockToParent(AActor* ParentActor)
{
	if (!HasAuthority() || !IsValidDockParent(ParentActor) || Health <= 0.f)
	{
		return false;
	}

	if (GetAttachParentActor())
	{
		DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);
	}
	SetActorTransform(BuildRearBayTransform(ParentActor, false), false, nullptr,
		ETeleportType::TeleportPhysics);
	DockParent = ParentActor;
	bLandingAssistEnabled = false;
	bLandingSettled = false;
	AttachToActor(ParentActor, FAttachmentTransformRules::KeepWorldTransform);
	ApplyDockedPresentation();
	FlushNetDormancy();
	ForceNetUpdate();
	ParentActor->ForceNetUpdate();
	UE_LOG(LogRedMiniFighter, Display, TEXT("%s docked in rear bay of %s"),
		*GetName(), *GetNameSafe(ParentActor));
	return true;
}

bool ARedMiniFighter::UndockAuthority()
{
	if (!HasAuthority() || !DockParent)
	{
		return false;
	}

	AActor* PreviousParent = DockParent;
	const FTransform LaunchTransform = BuildRearBayTransform(PreviousParent, true);
	DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);
	DockParent = nullptr;
	bLandingAssistEnabled = false;
	bLandingSettled = false;
	SetActorTransform(LaunchTransform, false, nullptr, ETeleportType::TeleportPhysics);
	ApplyUndockedPresentation();
	FlushNetDormancy();
	ForceNetUpdate();
	if (PreviousParent)
	{
		PreviousParent->ForceNetUpdate();
	}
	UE_LOG(LogRedMiniFighter, Display, TEXT("%s launched from %s"),
		*GetName(), *GetNameSafe(PreviousParent));
	return true;
}

AActor* ARedMiniFighter::FindBestDockParent() const
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return nullptr;
	}

	AActor* Best = nullptr;
	float BestDistanceSq = TNumericLimits<float>::Max();
	auto Consider = [this, &Best, &BestDistanceSq](AActor* Candidate)
	{
		if (!IsValidDockParent(Candidate))
		{
			return;
		}
		const FVector Target = BuildRearBayTransform(Candidate, false).GetLocation();
		const float DistanceSq = FVector::DistSquared(GetActorLocation(), Target);
		if (DistanceSq < BestDistanceSq)
		{
			BestDistanceSq = DistanceSq;
			Best = Candidate;
		}
	};

	for (TActorIterator<ARedShuttleBase> It(World); It; ++It)
	{
		Consider(*It);
	}
	if (Best)
	{
		return Best;
	}

	// Future-proof fallback for a replicated carrier class that is not derived from the shuttle.
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		AActor* Candidate = *It;
		if (!Candidate)
		{
			continue;
		}
		const FString Identity = Candidate->GetName() + TEXT(" ") + Candidate->GetClass()->GetName();
		if (Identity.Contains(TEXT("Carrier"), ESearchCase::IgnoreCase))
		{
			Consider(Candidate);
		}
	}
	return Best;
}

bool ARedMiniFighter::IsValidDockParent(const AActor* Candidate) const
{
	if (!IsValid(Candidate) || Candidate == this || !Candidate->GetRootComponent()
		|| Candidate->IsActorBeingDestroyed() || !Candidate->GetIsReplicated())
	{
		return false;
	}
	if (Candidate->IsA<ARedShuttleBase>())
	{
		return static_cast<const ARedShuttleBase*>(Candidate)->GetHealthFraction() > 0.f;
	}
	const FString Identity = Candidate->GetName() + TEXT(" ") + Candidate->GetClass()->GetName();
	return Identity.Contains(TEXT("Carrier"), ESearchCase::IgnoreCase);
}

FTransform ARedMiniFighter::BuildRearBayTransform(const AActor* ParentActor,
	const bool bLaunchPosition) const
{
	if (!ParentActor)
	{
		return GetActorTransform();
	}

	// The migrated shuttle is an assembly of a hull plus four child-engine actors. Its aggregate
	// world AABB includes engine/FX bounds and previously placed the fighter ~30m behind the visual
	// craft. For this known parent, calculate the bay in its authored local hull frame. This remains
	// stable under planet-relative rotation and does not change when engine effects animate.
	if (const ARedShuttleBase* Shuttle = Cast<ARedShuttleBase>(ParentActor))
	{
		FVector BodyCenter(0.f, 0.f, 100.f);
		FVector BodyExtent(1400.f, 700.f, 260.f);
		if (Shuttle->RuntimeHullCollision)
		{
			BodyCenter = Shuttle->RuntimeHullCollision->GetRelativeLocation();
			BodyExtent = Shuttle->RuntimeHullCollision->GetUnscaledBoxExtent();
		}

		const float RearX = BodyCenter.X - FMath::Max(300.f, BodyExtent.X);
		const float LocalX = bLaunchPosition
			? RearX - FMath::Max(100.f, LaunchClearance)
			: RearX + FMath::Clamp(RearBayInset, 0.f, FMath::Max(300.f, BodyExtent.X));
		const FVector LocalLocation(LocalX, BodyCenter.Y,
			BodyCenter.Z + RearBayVerticalOffset);
		const FTransform ParentTransform = ParentActor->GetActorTransform();
		return FTransform(ParentTransform.GetRotation(),
			ParentTransform.TransformPosition(LocalLocation), FVector::OneVector);
	}

	FVector BoundsOrigin = ParentActor->GetActorLocation();
	FVector BoundsExtent(1400.f, 700.f, 350.f);
	ParentActor->GetActorBounds(true, BoundsOrigin, BoundsExtent, false);
	if (BoundsExtent.GetMax() < 100.f || BoundsExtent.ContainsNaN())
	{
		BoundsOrigin = ParentActor->GetActorLocation();
		BoundsExtent = FVector(1400.f, 700.f, 350.f);
	}
	FVector Forward = ParentActor->GetActorForwardVector().GetSafeNormal();
	FVector Up = ParentActor->GetActorUpVector().GetSafeNormal();
	if (Forward.IsNearlyZero()) { Forward = FVector::ForwardVector; }
	if (Up.IsNearlyZero()) { Up = FVector::UpVector; }

	const float RearSupport = FMath::Clamp(
		RedMiniFighterPrivate::AabbSupport(BoundsExtent, Forward), 300.f, 3000.f);
	const float AftDistance = bLaunchPosition
		? RearSupport + FMath::Max(100.f, LaunchClearance)
		: FMath::Max(200.f, RearSupport - FMath::Clamp(RearBayInset, 0.f, RearSupport * 0.8f));
	const FVector Location = BoundsOrigin - Forward * AftDistance + Up * RearBayVerticalOffset;
	const FQuat Rotation = FRotationMatrix::MakeFromXZ(Forward, Up).ToQuat();
	return FTransform(Rotation, Location, FVector::OneVector);
}

void ARedMiniFighter::ApplyDockedPresentation()
{
	if (!DockParent)
	{
		return;
	}
	if (GetAttachParentActor() != DockParent)
	{
		SetActorTransform(BuildRearBayTransform(DockParent, false), false, nullptr,
			ETeleportType::TeleportPhysics);
		AttachToActor(DockParent, FAttachmentTransformRules::KeepWorldTransform);
	}
	SetActorEnableCollision(false);
	if (ShipMovement)
	{
		ShipMovement->StopMovementImmediately();
		ShipMovement->Deactivate();
	}
	if (CollisionDriver)
	{
		CollisionDriver->Deactivate();
	}
	for (UStaticMeshComponent* Plume : Plumes)
	{
		if (Plume)
		{
			Plume->SetVisibility(false, true);
			Plume->SetHiddenInGame(true, true);
		}
	}
	if (ReadabilityFillLight)
	{
		ReadabilityFillLight->SetVisibility(false, true);
	}
}

void ARedMiniFighter::ApplyUndockedPresentation()
{
	SetActorEnableCollision(Health > 0.f);
	if (Health > 0.f && ShipMovement)
	{
		ShipMovement->Activate(true);
		ShipMovement->StopMovementImmediately();
	}
	if (Health > 0.f && CollisionDriver)
	{
		CollisionDriver->Activate(true);
	}
	if (ReadabilityFillLight)
	{
		ReadabilityFillLight->SetVisibility(Health > 0.f, true);
	}
}

void ARedMiniFighter::OnRep_DockParent()
{
	if (DockParent)
	{
		ApplyDockedPresentation();
	}
	else
	{
		if (GetAttachParentActor())
		{
			DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);
		}
		ApplyUndockedPresentation();
	}
}

void ARedMiniFighter::GetLifetimeReplicatedProps(
	TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(ARedMiniFighter, DockParent);
}
