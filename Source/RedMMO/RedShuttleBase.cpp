#include "RedShuttleBase.h"
#include "RedShipExplosionFX.h"

#include "Camera/CameraComponent.h"
#include "Components/AudioComponent.h"
#include "Components/BoxComponent.h"
#include "Components/ChildActorComponent.h"
#include "Components/InputComponent.h"
#include "Components/PrimitiveComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/World.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshSocket.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/FloatingPawnMovement.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "InputCoreTypes.h"
#include "NiagaraComponent.h"
#include "Particles/ParticleSystem.h"
#include "Particles/ParticleSystemComponent.h"
#include "RedGravityBodies.h"
#include "RedPlanetTerrainQuery.h"
#include "RedBolt.h"
#include "RedPlayerCharacter.h"
#include "RedSpaceScenery.h"
#include "Net/UnrealNetwork.h"
#include "Kismet/GameplayStatics.h"
#include "NiagaraFunctionLibrary.h"
#include "NiagaraSystem.h"
#include "Sound/SoundAttenuation.h"
#include "Sound/SoundBase.h"
#include "UObject/StrongObjectPtr.h"
#include "UObject/UnrealType.h"

DEFINE_LOG_CATEGORY_STATIC(LogRedShuttle, Log, All);

namespace RedShuttlePrivate
{
	static const FName EngineCompNames[] = {
		TEXT("BP_Engine_FL"), TEXT("BP_Engine_FR"),
		TEXT("BP_Engine_BL"), TEXT("BP_Engine_BR")
	};

	/** Pack Timeline_1: DoorHinge relative pitch 0 (closed) → -90 (open). */
	static constexpr float HangarDoorClosedPitch = 0.f;
	static constexpr float HangarDoorOpenPitch = -90.f;

	// The fitted body lobes remain a conservative ship/world envelope, but should not act as a
	// second invisible hull for characters or weapons.  Detailed purchased meshes handle traces
	// and projectile impacts; the separate thin deck pieces handle Pawn floor contact.
	static void ConfigureHullEnvelopeCollisionBox(UBoxComponent* Box)
	{
		if (!Box) { return; }
		Box->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
		Box->SetCollisionObjectType(ECC_Vehicle);
		Box->SetCollisionResponseToAllChannels(ECR_Ignore);
		Box->SetCollisionResponseToChannel(ECC_WorldStatic, ECR_Block);
		Box->SetCollisionResponseToChannel(ECC_Vehicle, ECR_Block);
		Box->SetGenerateOverlapEvents(false);
		Box->SetSimulatePhysics(false);
		Box->SetCanEverAffectNavigation(false);
		Box->CanCharacterStepUpOn = ECB_No;
	}

	static void ConfigureWalkableDeckCollisionBox(UBoxComponent* Box)
	{
		if (!Box) { return; }
		Box->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
		Box->SetCollisionObjectType(ECC_Vehicle);
		Box->SetCollisionResponseToAllChannels(ECR_Ignore);
		Box->SetCollisionResponseToChannel(ECC_Pawn, ECR_Block);
		Box->SetGenerateOverlapEvents(false);
		Box->SetSimulatePhysics(false);
		Box->SetCanEverAffectNavigation(false);
		Box->CanCharacterStepUpOn = ECB_Yes;
	}

	static void BindThrusterToAuthoredNozzle(AActor* EngineActor, UNiagaraComponent* Thruster)
	{
		static const FName BoundTag(TEXT("RedNozzleBound"));
		if (!EngineActor || !Thruster || Thruster->ComponentHasTag(BoundTag))
		{
			return;
		}
		TArray<UStaticMeshComponent*> Meshes;
		EngineActor->GetComponents<UStaticMeshComponent>(Meshes);
		UStaticMeshComponent* EngineMesh = nullptr;
		float LargestBounds = -1.f;
		bool bSelectedNamedEngine = false;
		for (UStaticMeshComponent* Mesh : Meshes)
		{
			if (!Mesh || !Mesh->GetStaticMesh())
			{
				continue;
			}
			FString Identity = Mesh->GetName() + TEXT(" ") + Mesh->GetStaticMesh()->GetName();
			Identity.ToLowerInline();
			const float BoundsSize = Mesh->Bounds.BoxExtent.SizeSquared();
			const bool bNamedEngine = Identity.Contains(TEXT("engine"));
			if (!EngineMesh || (bNamedEngine && !bSelectedNamedEngine)
				|| (bNamedEngine == bSelectedNamedEngine && BoundsSize > LargestBounds))
			{
				EngineMesh = Mesh;
				LargestBounds = BoundsSize;
				bSelectedNamedEngine = bNamedEngine;
			}
		}
		if (!EngineMesh)
		{
			return;
		}

		FName NozzleSocket = NAME_None;
		for (const TObjectPtr<UStaticMeshSocket>& SocketPtr : EngineMesh->GetStaticMesh()->Sockets)
		{
			const UStaticMeshSocket* Socket = SocketPtr.Get();
			if (!Socket)
			{
				continue;
			}
			FString SocketIdentity = Socket->SocketName.ToString();
			SocketIdentity.ToLowerInline();
			if (SocketIdentity.Contains(TEXT("nozzle"))
				|| SocketIdentity.Contains(TEXT("exhaust"))
				|| SocketIdentity.Contains(TEXT("thruster")))
			{
				NozzleSocket = Socket->SocketName;
				break;
			}
		}

		if (!NozzleSocket.IsNone())
		{
			Thruster->AttachToComponent(EngineMesh,
				FAttachmentTransformRules::SnapToTargetNotIncludingScale, NozzleSocket);
		}
		else
		{
			// The purchased BP_Engine variants author Niagara exactly at the mouth but some variants
			// parent it to the child-actor root. Preserve that authored world nozzle transform while
			// reparenting it to the moving engine mesh, so nozzle pitch can never leave fire behind.
			const FTransform AuthoredNozzleWorld = Thruster->GetComponentTransform();
			if (Thruster->GetAttachParent() != EngineMesh)
			{
				Thruster->AttachToComponent(EngineMesh,
					FAttachmentTransformRules::KeepWorldTransform);
			}
			Thruster->SetUsingAbsoluteLocation(false);
			Thruster->SetUsingAbsoluteRotation(false);
			Thruster->SetUsingAbsoluteScale(false);
			Thruster->SetWorldTransform(AuthoredNozzleWorld);
		}
		Thruster->ComponentTags.AddUnique(BoundTag);
		UE_LOG(LogRedShuttle, Display, TEXT("Bound %s to engine nozzle %s:%s"),
			*GetNameSafe(Thruster), *GetNameSafe(EngineMesh),
			NozzleSocket.IsNone() ? TEXT("authored transform") : *NozzleSocket.ToString());
	}

	/** Drive only the pack-native, nozzle-authored NS_Thrusters layer plus engine audio. */
	static void SetEngineFXActive(AActor* Ship, bool bOn, float Scale = 1.f)
	{
		if (!Ship) { return; }
		// Static raw UObject pointers are invisible to Unreal's garbage collector. The old
		// cache left AttenuationSettings pointing at reclaimed memory after a collection,
		// which crashed roughly eight seconds after boarding a shuttle in a long session.
		// Strong pointers keep these optional runtime-loaded assets alive for process life.
		static TStrongObjectPtr<USoundBase> CruiseEngine(LoadObject<USoundBase>(nullptr,
			TEXT("/Game/SpaceShip/Audio/SC_RocketEngine.SC_RocketEngine")));
		static TStrongObjectPtr<USoundBase> BoostEngine(LoadObject<USoundBase>(nullptr,
			TEXT("/Game/SpaceShip/Audio/SC_RocketEngineHigh.SC_RocketEngineHigh")));
		static TStrongObjectPtr<USoundAttenuation> EngineAttenuation(
			LoadObject<USoundAttenuation>(nullptr,
				TEXT("/Game/Vefects/Sand_VFX/Audio/SFX_Attenuation.SFX_Attenuation")));
		const bool bBoosting = Scale > 1.25f;
		USoundBase* DesiredEngineSound = bBoosting && BoostEngine.Get()
			? BoostEngine.Get() : CruiseEngine.Get();
		const float ChildEngineVolume = bBoosting ? 0.055f : 0.035f;
		const float RootEngineVolume = bBoosting ? 0.13f : 0.08f;
		const float EnginePitch = bBoosting ? 1.04f : 0.92f;

		auto DriveEngineActor = [&](AActor* Eng)
		{
			if (!Eng) { return; }

			// Pack-native NS_Thrusters / Niagara — re-enable when engines on (prior path
			// force-hid these every tick, which killed the pack's authored fire look).
			TArray<UNiagaraComponent*> NCs;
			Eng->GetComponents<UNiagaraComponent>(NCs);
			for (UNiagaraComponent* NC : NCs)
			{
				if (!NC) { continue; }
				const UNiagaraSystem* System = NC->GetAsset();
				const bool bAuthoredThruster =
					(System && System->GetName().Contains(TEXT("Thrusters")))
					|| NC->GetName().Contains(TEXT("Niagara"));
				if (!bAuthoredThruster) { continue; }
				BindThrusterToAuthoredNozzle(Eng, NC);
				NC->SetVisibility(bOn, true);
				NC->SetHiddenInGame(!bOn, true);
				if (bOn)
				{
					// Preserve the BP_Engine-authored nozzle transform. Re-scaling the entire
					// component displaced the flame as the nozzle pitched down/aft.
					if (!NC->IsActive())
					{
						NC->Activate(true);
					}
				}
				else
				{
					NC->Deactivate();
				}
			}

			// Purge the obsolete injected Cascade layer if a prior hot-reload created it.
			TArray<UParticleSystemComponent*> EngPS;
			Eng->GetComponents<UParticleSystemComponent>(EngPS);
			for (UParticleSystemComponent* PSC : EngPS)
			{
				if (!PSC) { continue; }
				const bool bInjectedExhaust = PSC->GetName().Contains(TEXT("RedCascadeExhaust"))
					|| (PSC->Template && PSC->Template->GetName().Contains(TEXT("Jet_Exhaust")));
				if (bInjectedExhaust)
				{
					// This Jet Pack effect supplied the black smoke and a detached second
					// flame layer. Keep only BP_Engine's nozzle-authored NS_Thrusters.
					PSC->Deactivate();
					PSC->SetVisibility(false, true);
					PSC->SetHiddenInGame(true, true);
				}
			}

			TArray<UAudioComponent*> EngAud;
			Eng->GetComponents<UAudioComponent>(EngAud);
			for (UAudioComponent* Aud : EngAud)
			{
				if (!Aud) { continue; }
				if (bOn)
				{
					if (DesiredEngineSound && Aud->Sound != DesiredEngineSound)
					{
						Aud->SetSound(DesiredEngineSound);
					}
					if (EngineAttenuation.Get())
					{
						Aud->AttenuationSettings = EngineAttenuation.Get();
					}
					Aud->bAllowSpatialization = true;
					Aud->SetVolumeMultiplier(ChildEngineVolume);
					Aud->SetPitchMultiplier(EnginePitch);
					if (!Aud->IsPlaying()) { Aud->Play(); }
				}
				else
				{
					Aud->Stop();
				}
			}
		};

		TArray<UAudioComponent*> Audios;
		Ship->GetComponents<UAudioComponent>(Audios);
		for (UAudioComponent* Aud : Audios)
		{
			if (!Aud) { continue; }
			const FString N = Aud->GetName();
			if (!(N.Contains(TEXT("Engine")) || N.Contains(TEXT("Thruster")) || N.Contains(TEXT("Jet"))))
			{
				continue;
			}
			if (bOn)
			{
				if (DesiredEngineSound && Aud->Sound != DesiredEngineSound)
				{
					Aud->SetSound(DesiredEngineSound);
				}
				if (EngineAttenuation.Get())
				{
					Aud->AttenuationSettings = EngineAttenuation.Get();
				}
				Aud->bAllowSpatialization = true;
				Aud->SetVolumeMultiplier(RootEngineVolume);
				Aud->SetPitchMultiplier(EnginePitch);
				if (!Aud->IsPlaying()) { Aud->Play(); }
			}
			else
			{
				Aud->Stop();
			}
		}
		// Drive each pack BP_Engine_* child without adding a second exhaust system.
		for (const FName& Name : EngineCompNames)
		{
			FObjectPropertyBase* Prop = FindFProperty<FObjectPropertyBase>(Ship->GetClass(), Name);
			if (!Prop) { continue; }
			UObject* Obj = Prop->GetObjectPropertyValue_InContainer(Ship);
			AActor* Eng = nullptr;
			if (UChildActorComponent* CAC = Cast<UChildActorComponent>(Obj))
			{
				Eng = CAC->GetChildActor();
			}
			else
			{
				Eng = Cast<AActor>(Obj);
			}
			DriveEngineActor(Eng);
		}
	}
}

ARedShuttleBase::ARedShuttleBase()
{
	PrimaryActorTick.bCanEverTick = true;
	bReplicates = true;
	SetReplicateMovement(true);
	ProjectileClass = ARedBolt::StaticClass();
	RedShuttleRoot = CreateDefaultSubobject<USceneComponent>(TEXT("RedShuttleRoot"));
	SetRootComponent(RedShuttleRoot);
	CockpitCameraAnchor = CreateDefaultSubobject<USceneComponent>(TEXT("CockpitCameraAnchor"));
	CockpitCameraAnchor->SetupAttachment(RedShuttleRoot);
	CockpitCameraAnchor->SetRelativeLocation(FVector(520.f, 0.f, 330.f));
	CockpitCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("CockpitCamera"));
	CockpitCamera->SetupAttachment(CockpitCameraAnchor);
	CockpitCamera->bUsePawnControlRotation = false;
	CockpitCamera->SetFieldOfView(CockpitFieldOfView);
	CockpitCamera->SetAutoActivate(false);
	CockpitCamera->Deactivate();
	NativeChaseCameraBoom = CreateDefaultSubobject<USpringArmComponent>(TEXT("NativeChaseCameraBoom"));
	NativeChaseCameraBoom->SetupAttachment(RedShuttleRoot);
	NativeChaseCameraBoom->TargetArmLength = ChaseCameraArmLength;
	NativeChaseCameraBoom->SocketOffset = ChaseCameraSocketOffset;
	NativeChaseCameraBoom->bUsePawnControlRotation = false;
	NativeChaseCameraBoom->bDoCollisionTest = true;
	NativeChaseCameraBoom->ProbeSize = CameraProbeSize;
	NativeChaseCameraBoom->ProbeChannel = ECC_Camera;
	NativeChaseCameraBoom->bEnableCameraLag = true;
	NativeChaseCameraBoom->CameraLagSpeed = 8.f;
	NativeChaseCameraBoom->bEnableCameraRotationLag = true;
	NativeChaseCameraBoom->CameraRotationLagSpeed = 10.f;
	NativeChaseCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("NativeChaseCamera"));
	NativeChaseCamera->SetupAttachment(NativeChaseCameraBoom, USpringArmComponent::SocketName);
	NativeChaseCamera->bUsePawnControlRotation = false;
	NativeChaseCamera->SetAutoActivate(false);
	NativeChaseCamera->Deactivate();
	RuntimeHullCollision = CreateDefaultSubobject<UBoxComponent>(TEXT("RuntimeHullCollision"));
	RuntimeHullCollision->SetupAttachment(RedShuttleRoot);
	RuntimeHullCollision->SetBoxExtent(FVector(1600.f, 720.f, 333.f));
	RuntimeHullCollision->SetRelativeLocation(FVector(-916.f, 0.f, 486.f));
	RedShuttlePrivate::ConfigureHullEnvelopeCollisionBox(RuntimeHullCollision);
	RuntimeDeckCollision = CreateDefaultSubobject<UBoxComponent>(TEXT("RuntimeDeckCollision"));
	RuntimeDeckCollision->SetupAttachment(RedShuttleRoot);
	RuntimeDeckCollision->SetBoxExtent(FVector(1450.f, 680.f, 24.f));
	RuntimeDeckCollision->SetRelativeLocation(FVector(-916.f, 0.f, 795.f));
	RedShuttlePrivate::ConfigureWalkableDeckCollisionBox(RuntimeDeckCollision);
	RuntimePortHullCollision = CreateDefaultSubobject<UBoxComponent>(TEXT("RuntimePortHullCollision"));
	RuntimePortHullCollision->SetupAttachment(RedShuttleRoot);
	RuntimePortHullCollision->SetBoxExtent(FVector(1250.f, 580.f, 250.f));
	RuntimePortHullCollision->SetRelativeLocation(FVector(-1150.f, -1300.f, 430.f));
	RedShuttlePrivate::ConfigureHullEnvelopeCollisionBox(RuntimePortHullCollision);
	RuntimeStarboardHullCollision = CreateDefaultSubobject<UBoxComponent>(TEXT("RuntimeStarboardHullCollision"));
	RuntimeStarboardHullCollision->SetupAttachment(RedShuttleRoot);
	RuntimeStarboardHullCollision->SetBoxExtent(FVector(1250.f, 580.f, 250.f));
	RuntimeStarboardHullCollision->SetRelativeLocation(FVector(-1150.f, 1300.f, 430.f));
	RedShuttlePrivate::ConfigureHullEnvelopeCollisionBox(RuntimeStarboardHullCollision);
	RuntimePortDeckCollision = CreateDefaultSubobject<UBoxComponent>(TEXT("RuntimePortDeckCollision"));
	RuntimePortDeckCollision->SetupAttachment(RedShuttleRoot);
	RuntimePortDeckCollision->SetBoxExtent(FVector(1180.f, 530.f, 18.f));
	RuntimePortDeckCollision->SetRelativeLocation(FVector(-1150.f, -1300.f, 662.f));
	RedShuttlePrivate::ConfigureWalkableDeckCollisionBox(RuntimePortDeckCollision);
	RuntimeStarboardDeckCollision = CreateDefaultSubobject<UBoxComponent>(TEXT("RuntimeStarboardDeckCollision"));
	RuntimeStarboardDeckCollision->SetupAttachment(RedShuttleRoot);
	RuntimeStarboardDeckCollision->SetBoxExtent(FVector(1180.f, 530.f, 18.f));
	RuntimeStarboardDeckCollision->SetRelativeLocation(FVector(-1150.f, 1300.f, 662.f));
	RedShuttlePrivate::ConfigureWalkableDeckCollisionBox(RuntimeStarboardDeckCollision);
	RuntimeLoadingRampCollision = CreateDefaultSubobject<UBoxComponent>(TEXT("RuntimeLoadingRampCollision"));
	RuntimeLoadingRampCollision->SetupAttachment(RedShuttleRoot);
	RuntimeLoadingRampCollision->SetBoxExtent(LoadingRampCollisionExtent);
	RuntimeLoadingRampCollision->SetRelativeLocation(LoadingRampCollisionLocation);
	RuntimeLoadingRampCollision->SetRelativeRotation(LoadingRampCollisionRotation);
	RedShuttlePrivate::ConfigureWalkableDeckCollisionBox(RuntimeLoadingRampCollision);
	WeaponMuzzleLeft = CreateDefaultSubobject<USceneComponent>(TEXT("WeaponMuzzleLeft"));
	WeaponMuzzleLeft->SetupAttachment(RedShuttleRoot);
	WeaponMuzzleLeft->SetRelativeLocation(FVector(1200.f, -350.f, 100.f));
	WeaponMuzzleRight = CreateDefaultSubobject<USceneComponent>(TEXT("WeaponMuzzleRight"));
	WeaponMuzzleRight->SetupAttachment(RedShuttleRoot);
	WeaponMuzzleRight->SetRelativeLocation(FVector(1200.f, 350.f, 100.f));
	// Last demotable so we run after almost everything; we also skip Super::Tick while
	// piloted so the pack EventGraph cannot yank us back to world +Z afterward.
	PrimaryActorTick.TickGroup = TG_LastDemotable;
}

void ARedShuttleBase::BeginPlay()
{
	Super::BeginPlay();
	SetActorEnableCollision(true);
	SetCanBeDamaged(true);
	if (HasAuthority())
	{
		FVector PlanetCenter = FVector::ZeroVector;
		FVector RadialUp = FVector::UpVector;
		GetPlanetFrame(PlanetCenter, RadialUp);
		ARedSpaceScenery::EnsureForWorld(GetWorld(), PlanetCenter);
	}
	// APawn has no native scene root and the pack supplies its root in the child Blueprint. Seat
	// inherited muzzle markers once that Blueprint hierarchy exists, preserving authored offsets.
	if (RootComponent)
	{
		if (WeaponMuzzleLeft && !WeaponMuzzleLeft->GetAttachParent())
		{
			WeaponMuzzleLeft->AttachToComponent(RootComponent, FAttachmentTransformRules::KeepRelativeTransform);
		}
		if (WeaponMuzzleRight && !WeaponMuzzleRight->GetAttachParent())
		{
			WeaponMuzzleRight->AttachToComponent(RootComponent, FAttachmentTransformRules::KeepRelativeTransform);
		}
	}
	if (HasAuthority())
	{
		MaxHealth = FMath::Max(1.f, MaxHealth);
		Health = MaxHealth;
		WeaponHeat = 0.f;
		bWeaponOverheated = false;
		ForceNetUpdate();
	}
	bRuntimeCollisionHullsConfigured = ConfigureRuntimeCollisionHulls();
	ConfigureCockpitCamera();
	ApplyFlightCameraMode();
	EnsureProjectileCollision();
	// Parked at map start: engines must be quiet until boarded.
	if (!GetController())
	{
		EnsureEnginesOff();
	}
}

void ARedShuttleBase::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);
	if (!PlayerInputComponent)
	{
		return;
	}
	PlayerInputComponent->BindAction(TEXT("Fire"), IE_Pressed, this, &ARedShuttleBase::StartFire);
	PlayerInputComponent->BindAction(TEXT("Fire"), IE_Released, this, &ARedShuttleBase::StopFire);
	PlayerInputComponent->BindAction(TEXT("EnterVehicle"), IE_Pressed, this, &ARedShuttleBase::ExitShuttle);
}

void ARedShuttleBase::StartFire()
{
	bFiring = true;
}

void ARedShuttleBase::StopFire()
{
	bFiring = false;
}

bool ARedShuttleBase::CanAcceptBoarding() const
{
	if (Health <= 0.f || bDeathHandled)
	{
		return false;
	}
	const UWorld* World = GetWorld();
	if (World && World->GetTimeSeconds() < NextBoardAllowedTime)
	{
		return false;
	}
	if (IsValid(Occupant))
	{
		return false;
	}
	// The pack can leave a stale Driver/Character object property populated while parked.
	// A real boarding owns the pawn through a player controller, which is authoritative and
	// cannot be confused with those Blueprint preview/default references.
	const AController* CurrentController = GetController();
	return !CurrentController || !CurrentController->IsPlayerController();
}

void ARedShuttleBase::RegisterOccupant(APawn* InOccupant)
{
	if (!HasAuthority() || !IsValid(InOccupant) || InOccupant == this)
	{
		return;
	}
	Occupant = InOccupant;
	ForceNetUpdate();
}

void ARedShuttleBase::ExitShuttle()
{
	if (IsLocallyControlled())
	{
		const double Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
		if (!bLocalExitInputArmed || Now < LocalExitInputReadyTime)
		{
			return;
		}
	}
	if (bExitRequestSent)
	{
		return;
	}
	bExitRequestSent = true;

	if (!HasAuthority())
	{
		ServerExitShuttle();
		return;
	}

	if (UWorld* World = GetWorld())
	{
		// Possession can move from the shuttle back to a character while the original V event is
		// still being dispatched. Lock the shuttle briefly so that event cannot immediately board
		// it again through the newly possessed pawn (or the listen-server host input stack).
		NextBoardAllowedTime = World->GetTimeSeconds() + 0.75;
	}
	EjectOccupantBeforeDeath();
	EnsureEnginesOff();
}

void ARedShuttleBase::ServerExitShuttle_Implementation()
{
	ExitShuttle();
}

void ARedShuttleBase::StartFireTest()
{
	StartFire();
}

void ARedShuttleBase::StopFireTest()
{
	StopFire();
}

void ARedShuttleBase::TestFire()
{
	Fire();
}

void ARedShuttleBase::Fire()
{
	if (HasAuthority())
	{
		TryFireAuthoritative();
	}
	else
	{
		// The client sends intent only. Muzzle, aim, cadence and heat remain authoritative.
		ServerFire();
	}
}

bool ARedShuttleBase::ComputeServerFireTransform(bool bUseLeftMuzzle,
	FVector& OutStart, FRotator& OutDirection) const
{
	if (!HasAuthority())
	{
		return false;
	}

	const FVector CraftForward = GetActorForwardVector().GetSafeNormal();
	const FVector CraftRight = GetActorRightVector().GetSafeNormal();
	const FVector CraftUp = GetActorUpVector().GetSafeNormal();
	if (CraftForward.IsNearlyZero() || CraftForward.ContainsNaN())
	{
		return false;
	}

	FVector BoundsOrigin = GetActorLocation();
	FVector BoundsExtent = FVector(900.f, 500.f, 300.f);
	GetActorBounds(/*bOnlyCollidingComponents=*/true, BoundsOrigin, BoundsExtent,
		/*bIncludeFromChildActors=*/true);
	if (BoundsExtent.GetMax() < 10.f || BoundsExtent.ContainsNaN())
	{
		GetActorBounds(/*bOnlyCollidingComponents=*/false, BoundsOrigin, BoundsExtent,
			/*bIncludeFromChildActors=*/true);
	}
	BoundsExtent.X = FMath::Max(BoundsExtent.X, 100.f);
	BoundsExtent.Y = FMath::Max(BoundsExtent.Y, 100.f);
	BoundsExtent.Z = FMath::Max(BoundsExtent.Z, 100.f);
	const float ForwardRadius = FVector::DotProduct(CraftForward.GetAbs(), BoundsExtent);

	// Prefer authored muzzle/fire-point scene components from the pack. They are server-owned
	// components, and the bounds check rejects unrelated helpers or accidentally distant FX.
	const USceneComponent* BestMuzzle = nullptr;
	float BestSideScore = -MAX_flt;
	const float MaxMuzzleDistance = FMath::Max(1500.f, BoundsExtent.Size() * 2.5f);
	TArray<USceneComponent*> Components;
	TArray<AActor*> ActorsToScan;
	ActorsToScan.Add(const_cast<ARedShuttleBase*>(this));
	for (int32 ActorIndex = 0; ActorIndex < ActorsToScan.Num() && ActorIndex < 32; ++ActorIndex)
	{
		AActor* CandidateActor = ActorsToScan[ActorIndex];
		if (!CandidateActor) { continue; }
		TArray<USceneComponent*> ActorComponents;
		CandidateActor->GetComponents<USceneComponent>(ActorComponents);
		Components.Append(ActorComponents);
		for (USceneComponent* Component : ActorComponents)
		{
			if (const UChildActorComponent* ChildComponent = Cast<UChildActorComponent>(Component))
			{
				if (AActor* Child = ChildComponent->GetChildActor())
				{
					ActorsToScan.AddUnique(Child);
				}
			}
		}
	}
	for (const USceneComponent* Component : Components)
	{
		if (!Component || !Component->IsRegistered())
		{
			continue;
		}
		const FString Name = Component->GetName().ToLower();
		if (!(Name.Contains(TEXT("muzzle")) || Name.Contains(TEXT("firepoint"))
			|| Name.Contains(TEXT("fire_point")) || Name.Contains(TEXT("gunpoint"))
			|| Name.Contains(TEXT("cannon_tip"))))
		{
			continue;
		}
		const FVector Location = Component->GetComponentLocation();
		const float ForwardProjection = FVector::DotProduct(Location - BoundsOrigin, CraftForward);
		if (Location.ContainsNaN() || FVector::Dist(Location, BoundsOrigin) > MaxMuzzleDistance
			|| ForwardProjection < FMath::Max(25.f, ForwardRadius * 0.35f))
		{
			continue;
		}
		const float Lateral = FVector::DotProduct(Location - BoundsOrigin, CraftRight);
		const float SideScore = (bUseLeftMuzzle ? -1.f : 1.f) * Lateral;
		if (!BestMuzzle || SideScore > BestSideScore)
		{
			BestMuzzle = Component;
			BestSideScore = SideScore;
		}
	}

	if (BestMuzzle)
	{
		OutStart = BestMuzzle->GetComponentLocation();
	}
	else
	{
		// A pack with no authored muzzle still fires from the physical nose, never the body.
		// Project the world AABB onto the craft axes to obtain a conservative hull clearance.
		const FVector AbsRight = CraftRight.GetAbs();
		const FVector AbsUp = CraftUp.GetAbs();
		const float LateralRadius = FVector::DotProduct(AbsRight, BoundsExtent);
		const float VerticalRadius = FVector::DotProduct(AbsUp, BoundsExtent);
		OutStart = BoundsOrigin
			+ CraftForward * (ForwardRadius + 90.f)
			+ CraftRight * (bUseLeftMuzzle ? -0.28f : 0.28f) * LateralRadius
			+ CraftUp * (0.08f * VerticalRadius);
	}

	FVector AimDirection = CraftForward;
	if (Controller)
	{
		const FVector RequestedAim = Controller->GetControlRotation().Vector().GetSafeNormal();
		if (!RequestedAim.IsNearlyZero() && !RequestedAim.ContainsNaN()
			&& FVector::DotProduct(RequestedAim, CraftForward) >= FMath::Clamp(MinFireAimDot, 0.f, 1.f))
		{
			AimDirection = RequestedAim;
		}
	}
	OutDirection = AimDirection.Rotation();
	return !OutStart.ContainsNaN();
}

bool ARedShuttleBase::TryFireAuthoritative()
{
	if (!HasAuthority() || Health <= 0.f || !GetWorld() || bWeaponOverheated
		|| !ProjectileClass || !ProjectileClass->IsChildOf(ARedBolt::StaticClass()))
	{
		return false;
	}

	const double Now = GetWorld()->GetTimeSeconds();
	if (Now + static_cast<double>(KINDA_SMALL_NUMBER) < NextServerFireTime)
	{
		return false;
	}

	FVector Start;
	FRotator Direction;
	if (!ComputeServerFireTransform(bMuzzleLeft, Start, Direction))
	{
		return false;
	}

	FActorSpawnParameters Params;
	Params.Owner = this;
	Params.Instigator = this;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AActor* Spawned = GetWorld()->SpawnActor<AActor>(ProjectileClass, Start, Direction, Params);
	ARedBolt* Bolt = Cast<ARedBolt>(Spawned);
	if (!Bolt)
	{
		if (Spawned) { Spawned->Destroy(); }
		return false;
	}

	Bolt->ConfigureImpactProfile(18.f, 3.f, 750.f, 70.f);
	Bolt->SetBeamDimensions(8.f, 0.52f);
	Bolt->ConfigureGroundImpact(false, false, false);
	Bolt->SetImpactExplosion(true);
	const float MuzzleSpeed = 13000.f + GetVelocity().Size() * 1.15f;
	Bolt->LaunchWithVelocity(Direction.Vector() * MuzzleSpeed);

	NextServerFireTime = Now + FMath::Max(0.03f, FireInterval);
	bMuzzleLeft = !bMuzzleLeft;
	WeaponHeat = FMath::Clamp(WeaponHeat + FMath::Max(0.f, HeatPerShot), 0.f, FMath::Max(1.f, MaxWeaponHeat));
	if (WeaponHeat >= FMath::Max(1.f, MaxWeaponHeat) - KINDA_SMALL_NUMBER)
	{
		bWeaponOverheated = true;
	}
	MulticastFireCosmetics(Start, Direction.Vector());
	ForceNetUpdate();
	return true;
}

void ARedShuttleBase::ServerFire_Implementation()
{
	TryFireAuthoritative();
}

void ARedShuttleBase::MulticastFireCosmetics_Implementation(FVector_NetQuantize MuzzleLocation,
	FVector_NetQuantizeNormal ShotDirection)
{
	if (GetNetMode() == NM_DedicatedServer)
	{
		return;
	}
	const FVector Direction = FVector(ShotDirection).GetSafeNormal();
	if (WeaponMuzzleFlashFX && !Direction.IsNearlyZero())
	{
		UNiagaraFunctionLibrary::SpawnSystemAtLocation(this, WeaponMuzzleFlashFX,
			MuzzleLocation, Direction.Rotation(), FVector::OneVector, true, true,
			ENCPoolMethod::AutoRelease, true);
	}
	if (WeaponFireSound)
	{
		UGameplayStatics::PlaySoundAtLocation(this, WeaponFireSound, MuzzleLocation,
			1.5f, 0.86f, 0.f, WeaponFireAttenuation);
	}
}

void ARedShuttleBase::UpdateWeaponHeat(float DeltaSeconds)
{
	if (!HasAuthority() || DeltaSeconds <= 0.f || WeaponHeat <= 0.f)
	{
		return;
	}
	WeaponHeat = FMath::Max(0.f, WeaponHeat - FMath::Max(0.f, HeatCooldownPerSecond) * DeltaSeconds);
	if (bWeaponOverheated
		&& WeaponHeat <= FMath::Max(1.f, MaxWeaponHeat) * FMath::Clamp(OverheatRecoveryFraction, 0.f, 1.f))
	{
		bWeaponOverheated = false;
		ForceNetUpdate();
	}
}

float ARedShuttleBase::TakeDamage(float DamageAmount, const FDamageEvent& DamageEvent,
	AController* EventInstigator, AActor* DamageCauser)
{
	if (!HasAuthority() || Health <= 0.f || DamageAmount <= 0.f)
	{
		return 0.f;
	}
	const float AppliedDamage = FMath::Max(0.f,
		Super::TakeDamage(DamageAmount, DamageEvent, EventInstigator, DamageCauser));
	if (AppliedDamage <= 0.f)
	{
		return 0.f;
	}
	Health = FMath::Clamp(Health - AppliedDamage, 0.f, FMath::Max(1.f, MaxHealth));
	ForceNetUpdate();
	if (Health <= 0.f)
	{
		HandleDeath(EventInstigator, DamageCauser);
	}
	return AppliedDamage;
}

void ARedShuttleBase::OnRep_Health()
{
	if (Health <= 0.f)
	{
		HandleDeath();
	}
}

APawn* ARedShuttleBase::FindPackDriverPawn() const
{
	if (IsValid(Occupant) && Occupant != this)
	{
		return Occupant;
	}

	static const FName PreferredNames[] = {
		TEXT("Driver"), TEXT("Pilot"), TEXT("Character"),
		TEXT("PlayerCharacter"), TEXT("InteractingCharacter")
	};
	for (const FName Name : PreferredNames)
	{
		if (const FObjectPropertyBase* Property = FindFProperty<FObjectPropertyBase>(GetClass(), Name))
		{
			if (APawn* Candidate = Cast<APawn>(Property->GetObjectPropertyValue_InContainer(this)))
			{
				if (Candidate != this) { return Candidate; }
			}
		}
	}

	// Pack revisions occasionally rename Driver. Restrict the fallback to pawn-valued fields
	// whose names still clearly describe an occupant; engine child actors cannot match this.
	for (TFieldIterator<FProperty> It(GetClass()); It; ++It)
	{
		const FString Name = It->GetName().ToLower();
		if (!(Name.Contains(TEXT("driver")) || Name.Contains(TEXT("pilot"))
			|| Name.Contains(TEXT("character"))))
		{
			continue;
		}
		const FObjectPropertyBase* ObjectProperty = CastField<FObjectPropertyBase>(*It);
		if (!ObjectProperty) { continue; }
		if (APawn* Candidate = Cast<APawn>(ObjectProperty->GetObjectPropertyValue_InContainer(this)))
		{
			if (Candidate != this) { return Candidate; }
		}
	}
	return nullptr;
}

bool ARedShuttleBase::IsOrbitalExit() const
{
	FVector PlanetCenter = FVector::ZeroVector;
	float SurfaceRadius = 0.f;
	if (!RedGravity::QueryDominantBody(GetWorld(), GetActorLocation(), PlanetCenter, SurfaceRadius)
		|| SurfaceRadius <= 0.f)
	{
		// If the planet is not present/streamed, a ground snap is never a safe fallback.
		return true;
	}
	const float Altitude = static_cast<float>((GetActorLocation() - PlanetCenter).Size()) - SurfaceRadius;
	return FMath::IsFinite(Altitude)
		&& Altitude >= FMath::Max(100000.f, OrbitalExitMinAltitude);
}

void ARedShuttleBase::EjectOccupantBeforeDeath()
{
	if (!HasAuthority())
	{
		return;
	}
	APawn* Leaving = FindPackDriverPawn();
	AController* PilotController = GetController();
	if (!Leaving)
	{
		return;
	}

	const bool bOrbitalExit = IsOrbitalExit();
	FVector ExitLocation = GetActorLocation() + GetActorUpVector() * 500.f + GetActorRightVector() * 650.f;
	if (bOrbitalExit)
	{
		FVector BoundsOrigin = GetActorLocation();
		FVector BoundsExtent(1200.f, 700.f, 350.f);
		GetActorBounds(true, BoundsOrigin, BoundsExtent, true);
		const float SideSupport = FVector::DotProduct(GetActorRightVector().GetAbs(), BoundsExtent);
		ExitLocation = BoundsOrigin + GetActorRightVector() * (SideSupport + 250.f)
			+ GetActorUpVector() * 150.f;
	}
	else if (const FObjectPropertyBase* ExitProperty =
		FindFProperty<FObjectPropertyBase>(GetClass(), TEXT("DriverExitPosition")))
	{
		if (const USceneComponent* ExitComponent =
			Cast<USceneComponent>(ExitProperty->GetObjectPropertyValue_InContainer(this)))
		{
			ExitLocation = ExitComponent->GetComponentLocation();
		}
	}

	Occupant = nullptr;
	if (FObjectPropertyBase* DriverProperty = FindFProperty<FObjectPropertyBase>(GetClass(), TEXT("Driver")))
	{
		DriverProperty->SetObjectPropertyValue_InContainer(this, nullptr);
	}
	ForceNetUpdate();

	if (ARedPlayerCharacter* RedPilot = Cast<ARedPlayerCharacter>(Leaving))
	{
		RedPilot->OnExitedShip(ExitLocation, GetActorForwardVector(), this,
			/*bSnapToPlanetSurface=*/false);
		if (bOrbitalExit)
		{
			if (UCharacterMovementComponent* CharacterMovement = RedPilot->GetCharacterMovement())
			{
				CharacterMovement->SetMovementMode(MOVE_Flying);
				CharacterMovement->Velocity = FVector::ZeroVector;
			}
		}
		RedPilot->SetPilotCaptureOnly(false);
		RedPilot->SetActorHiddenInGame(false);
		RedPilot->SetActorEnableCollision(true);
	}
	else
	{
		Leaving->DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);
		Leaving->SetActorLocation(ExitLocation, false, nullptr, ETeleportType::TeleportPhysics);
		Leaving->SetActorHiddenInGame(false);
		Leaving->SetActorEnableCollision(true);
	}
	if (PilotController)
	{
		PilotController->Possess(Leaving);
	}
	if (ARedPlayerCharacter* RedPilot = Cast<ARedPlayerCharacter>(Leaving))
	{
		RedPilot->SetHUDSpaceMinimap(false);
	}
}

void ARedShuttleBase::HandleDeath(AController* DamageInstigator, AActor* DamageCauser)
{
	if (bDeathHandled)
	{
		return;
	}
	bDeathHandled = true;
	if (HasAuthority())
	{
		ARedShipExplosionFX::SpawnForDestroyedShip(this);
	}
	if (HasAuthority())
	{
		// The pack clears Driver/Occupant during possession restoration, so retain the original player
		// before ejecting. Restore it to a normal visible pawn first, then use the same lethal damage
		// path as on-foot PvP; this keeps ragdoll and the four-second respawn server-authoritative.
		APawn* FatalOccupant = FindPackDriverPawn();
		EjectOccupantBeforeDeath();
		if (ARedPlayerCharacter* FatalPilot = Cast<ARedPlayerCharacter>(FatalOccupant))
		{
			FatalPilot->ApplyVehicleDestructionDeath(DamageInstigator,
				IsValid(DamageCauser) ? DamageCauser : this);
		}
		else if (IsValid(FatalOccupant))
		{
			// Preserve sensible behaviour for a non-RED pawn supplied by a future shuttle pack.
			UGameplayStatics::ApplyDamage(FatalOccupant, BIG_NUMBER, DamageInstigator,
				IsValid(DamageCauser) ? DamageCauser : this, nullptr);
		}
	}
	bFiring = false;
	FlightVelocity = FVector::ZeroVector;
	EnsureEnginesOff();
	SetActorEnableCollision(false);
	if (UPawnMovementComponent* Movement = GetMovementComponent())
	{
		Movement->StopMovementImmediately();
		Movement->Deactivate();
	}
	SetActorHiddenInGame(true);
	SetActorTickEnabled(false);
}

float ARedShuttleBase::GetHealthFraction() const
{
	return FMath::Clamp(Health / FMath::Max(1.f, MaxHealth), 0.f, 1.f);
}

float ARedShuttleBase::GetWeaponHeatFraction() const
{
	return FMath::Clamp(WeaponHeat / FMath::Max(1.f, MaxWeaponHeat), 0.f, 1.f);
}

void ARedShuttleBase::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(ARedShuttleBase, MaxHealth);
	DOREPLIFETIME(ARedShuttleBase, Health);
	DOREPLIFETIME(ARedShuttleBase, WeaponHeat);
	DOREPLIFETIME(ARedShuttleBase, bWeaponOverheated);
	DOREPLIFETIME(ARedShuttleBase, bLandingAssistEnabled);
	DOREPLIFETIME(ARedShuttleBase, bLandingSettled);
	DOREPLIFETIME(ARedShuttleBase, Occupant);
}

bool ARedShuttleBase::ConfigureRuntimeCollisionHulls()
{
	if (!RuntimeHullCollision || !RuntimeDeckCollision
		|| !RuntimePortHullCollision || !RuntimeStarboardHullCollision
		|| !RuntimePortDeckCollision || !RuntimeStarboardDeckCollision
		|| !RuntimeLoadingRampCollision
		|| !RootComponent)
	{
		return false;
	}

	USceneComponent* CollisionBasis = FindPackVisualMesh();
	if (!CollisionBasis || !CollisionBasis->IsRegistered())
	{
		CollisionBasis = RootComponent;
	}
	UBoxComponent* CollisionPieces[] = {
		RuntimeHullCollision.Get(), RuntimeDeckCollision.Get(),
		RuntimePortHullCollision.Get(), RuntimeStarboardHullCollision.Get(),
		RuntimePortDeckCollision.Get(), RuntimeStarboardDeckCollision.Get(),
		RuntimeLoadingRampCollision.Get()
	};
	for (UBoxComponent* Piece : CollisionPieces)
	{
		if (Piece && Piece->GetAttachParent() != CollisionBasis)
		{
			Piece->AttachToComponent(CollisionBasis,
				FAttachmentTransformRules::SnapToTargetNotIncludingScale);
		}
	}

	// SM_Ship's measured local bounds are approximately X[-2517,684], Y[-1887,1887],
	// Z[153,820]. The old authored box was X[-1400,1400], Y[-700,700], Z[-160,360]: most
	// of both outer hulls and the complete roof were non-colliding. Use three body lobes and three
	// thin deck pieces instead of one aggregate AABB, which blocks the visible craft while leaving
	// the silhouette gaps empty (no 50m invisible glass walkway from child-engine/FX bounds).
	const FVector BodyCenter(-916.f, 0.f, 486.f);
	const FVector BodyExtent(1600.f, 720.f, 333.f);
	RuntimeHullCollision->SetRelativeLocation(BodyCenter);
	RuntimeHullCollision->SetRelativeRotation(FRotator::ZeroRotator);
	RuntimeHullCollision->SetBoxExtent(BodyExtent, false);

	// The rear loading door is visually a walkable ramp, but its purchased mesh has
	// query-only collision. Fit one thin Pawn floor to the visible ramp instead of
	// re-enabling the mesh's oversized simple collision.
	RuntimeLoadingRampCollision->SetRelativeLocation(LoadingRampCollisionLocation);
	RuntimeLoadingRampCollision->SetRelativeRotation(LoadingRampCollisionRotation);
	RuntimeLoadingRampCollision->SetBoxExtent(LoadingRampCollisionExtent, false);

	// The mesh's absolute max (819) comes from small upper details, not the broad roof.  Using it as
	// a full-size floor left boots roughly one foot above the visible shuttle.  Inset the walkable
	// plane to the broad roof and tighten its footprint so it cannot bridge silhouette gaps.
	const float DeckHalfHeight = 16.f;
	const FVector DeckExtent(1300.f, 560.f, DeckHalfHeight);
	const float DeckTop = 787.f;
	RuntimeDeckCollision->SetRelativeLocation(FVector(BodyCenter.X, 0.f,
		DeckTop - DeckHalfHeight));
	RuntimeDeckCollision->SetRelativeRotation(FRotator::ZeroRotator);
	RuntimeDeckCollision->SetBoxExtent(DeckExtent, false);

	const FVector SideHullExtent(1250.f, 580.f, 250.f);
	const FVector PortHullCenter(-1150.f, -1300.f, 430.f);
	const FVector StarboardHullCenter(-1150.f, 1300.f, 430.f);
	RuntimePortHullCollision->SetRelativeLocation(PortHullCenter);
	RuntimePortHullCollision->SetRelativeRotation(FRotator::ZeroRotator);
	RuntimePortHullCollision->SetBoxExtent(SideHullExtent, false);
	RuntimeStarboardHullCollision->SetRelativeLocation(StarboardHullCenter);
	RuntimeStarboardHullCollision->SetRelativeRotation(FRotator::ZeroRotator);
	RuntimeStarboardHullCollision->SetBoxExtent(SideHullExtent, false);

	const FVector SideDeckExtent(1050.f, 450.f, 14.f);
	RuntimePortDeckCollision->SetRelativeLocation(FVector(-1150.f, -1300.f, 636.f));
	RuntimePortDeckCollision->SetRelativeRotation(FRotator::ZeroRotator);
	RuntimePortDeckCollision->SetBoxExtent(SideDeckExtent, false);
	RuntimeStarboardDeckCollision->SetRelativeLocation(FVector(-1150.f, 1300.f, 636.f));
	RuntimeStarboardDeckCollision->SetRelativeRotation(FRotator::ZeroRotator);
	RuntimeStarboardDeckCollision->SetBoxExtent(SideDeckExtent, false);

	RedShuttlePrivate::ConfigureHullEnvelopeCollisionBox(RuntimeHullCollision);
	RedShuttlePrivate::ConfigureHullEnvelopeCollisionBox(RuntimePortHullCollision);
	RedShuttlePrivate::ConfigureHullEnvelopeCollisionBox(RuntimeStarboardHullCollision);
	RedShuttlePrivate::ConfigureWalkableDeckCollisionBox(RuntimeDeckCollision);
	RedShuttlePrivate::ConfigureWalkableDeckCollisionBox(RuntimePortDeckCollision);
	RedShuttlePrivate::ConfigureWalkableDeckCollisionBox(RuntimeStarboardDeckCollision);
	RedShuttlePrivate::ConfigureWalkableDeckCollisionBox(RuntimeLoadingRampCollision);
	// The fitted box represents the fully deployed ramp, not the closed door.
	// Keep it absent until deployment is effectively complete so closing the
	// hangar cannot leave a phantom floor behind the shuttle.
	RuntimeLoadingRampCollision->SetCollisionEnabled(
		HangarDoorAlpha >= 0.92f
			? ECollisionEnabled::QueryAndPhysics
			: ECollisionEnabled::NoCollision);
	UE_LOG(LogRedShuttle, Display,
		TEXT("Runtime collision fitted on %s: 3 hull + 3 roof deck + 1 loading-ramp pieces, body center=%s extent=%s deckZ=%.1f ramp=%s"),
		*GetName(), *BodyCenter.ToCompactString(), *BodyExtent.ToCompactString(),
		DeckTop, *LoadingRampCollisionLocation.ToCompactString());
	return true;
}

void ARedShuttleBase::EnsureProjectileCollision()
{
	// Bolts block Vehicle / WorldDynamic / PhysicsBody — make the hull hittable on those channels.
	TArray<UPrimitiveComponent*> Prims;
	GetComponents<UPrimitiveComponent>(Prims);
	for (UPrimitiveComponent* Prim : Prims)
	{
		if (!Prim) { continue; }
		const bool bRuntimeHull = Prim == RuntimeHullCollision
			|| Prim == RuntimePortHullCollision || Prim == RuntimeStarboardHullCollision;
		const bool bRuntimeDeck = Prim == RuntimeDeckCollision
			|| Prim == RuntimePortDeckCollision || Prim == RuntimeStarboardDeckCollision
			|| Prim == RuntimeLoadingRampCollision;
		const UStaticMeshComponent* StaticMesh = Cast<UStaticMeshComponent>(Prim);
		const USkeletalMeshComponent* SkeletalMesh = Cast<USkeletalMeshComponent>(Prim);
		const bool bVisualMesh = (StaticMesh && StaticMesh->GetStaticMesh())
			|| (SkeletalMesh && SkeletalMesh->GetSkeletalMeshAsset());
		// ControlTrigger, Door1 and Door2 are overlap volumes used by the pack's
		// interaction graph. Turning them into blockers creates invisible walls and
		// prevents the same overlap state that StartInteraction expects.
		if (!bRuntimeHull && !bRuntimeDeck && !bVisualMesh) { continue; }
		if (bRuntimeHull)
		{
			RedShuttlePrivate::ConfigureHullEnvelopeCollisionBox(Cast<UBoxComponent>(Prim));
			continue;
		}
		if (bRuntimeDeck)
		{
			RedShuttlePrivate::ConfigureWalkableDeckCollisionBox(Cast<UBoxComponent>(Prim));
			if (Prim == RuntimeLoadingRampCollision && HangarDoorAlpha < 0.92f)
			{
				Prim->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			}
			continue;
		}
		if (bVisualMesh)
		{
			// Preserve query collision so bolts and visibility traces still hit the detailed visible
			// hull, but Pawns only stand on the compact runtime deck. This removes broad authored
			// simple-collision floors without making the shuttle's wings immune to gunfire.
			Prim->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
			Prim->SetCollisionObjectType(ECC_Vehicle);
			Prim->SetCollisionResponseToAllChannels(ECR_Ignore);
			Prim->SetCollisionResponseToChannel(ECC_Visibility, ECR_Block);
			Prim->SetCollisionResponseToChannel(ECC_WorldDynamic, ECR_Block);
			Prim->SetCollisionResponseToChannel(ECC_PhysicsBody, ECR_Block);
			Prim->SetGenerateOverlapEvents(false);
			Prim->CanCharacterStepUpOn = ECB_No;
			continue;
		}
	}
}

void ARedShuttleBase::ConfigureCockpitCamera()
{
	if (bCockpitCameraPositioned || !CockpitCameraAnchor || !CockpitCamera)
	{
		return;
	}
	USceneComponent* Visual = FindPackVisualMesh();
	if (!Visual || !Visual->IsRegistered())
	{
		return;
	}
	if (CockpitCameraAnchor->GetAttachParent() != Visual)
	{
		CockpitCameraAnchor->AttachToComponent(Visual,
			FAttachmentTransformRules::SnapToTargetNotIncludingScale);
	}

	FVector HullCenter = FVector::ZeroVector;
	FVector HullExtent(1400.f, 700.f, 300.f);
	if (RuntimeHullCollision && RuntimeHullCollision->GetAttachParent() == Visual)
	{
		HullCenter = RuntimeHullCollision->GetRelativeLocation();
		HullExtent = RuntimeHullCollision->GetUnscaledBoxExtent();
	}
	FVector CockpitLocal = HullCenter + FVector(
		HullExtent.X * FMath::Clamp(CockpitForwardFraction, 0.f, 0.85f),
		0.f,
		HullExtent.Z * FMath::Clamp(CockpitHeightFraction, 0.f, 0.9f))
		+ CockpitCameraFineTune;
	// The vendor hull has no usable interior/cockpit visibility mask. Keep the forward camera
	// just above its physical roof so near-plane clipping can never fill the view with hull metal.
	CockpitLocal.Z = FMath::Max(CockpitLocal.Z, HullCenter.Z + HullExtent.Z + 35.f);
	CockpitCameraAnchor->SetRelativeLocation(CockpitLocal);
	CockpitCameraAnchor->SetRelativeRotation(FRotator::ZeroRotator);
	CockpitCamera->SetRelativeLocation(FVector::ZeroVector);
	CockpitCamera->SetRelativeRotation(FRotator::ZeroRotator);
	CockpitCamera->SetFieldOfView(CockpitFieldOfView);
	bCockpitCameraPositioned = true;
	UE_LOG(LogRedShuttle, Display, TEXT("Cockpit camera seated on %s at hull-local %s"),
		*GetNameSafe(this), *CockpitLocal.ToCompactString());
}

void ARedShuttleBase::ApplyFlightCameraMode()
{
	if (!CockpitCamera)
	{
		return;
	}
	TArray<UCameraComponent*> Cams;
	GetComponents<UCameraComponent>(Cams);
	UCameraComponent* PackChaseCamera = NativeChaseCamera;
	for (UCameraComponent* Cam : Cams)
	{
		if (!Cam || Cam == CockpitCamera || Cam == NativeChaseCamera)
		{
			continue;
		}
		if (!PackChaseCamera && Cam->GetFName() == TEXT("Camera"))
		{
			PackChaseCamera = Cam;
		}
	}
	const bool bUseCockpit = !bThirdPersonCamera || !PackChaseCamera;
	if (CockpitCamera->IsActive() != bUseCockpit)
	{
		CockpitCamera->SetActive(bUseCockpit, true);
	}
	CockpitCamera->SetRelativeRotation(bUseCockpit
		? FRotator(LookPitchOffset, LookYawOffset, 0.f)
		: FRotator::ZeroRotator);
	for (UCameraComponent* Cam : Cams)
	{
		if (!Cam || Cam == CockpitCamera)
		{
			continue;
		}
		const bool bShouldBeActive = !bUseCockpit && Cam == PackChaseCamera;
		if (Cam->IsActive() != bShouldBeActive)
		{
			Cam->SetActive(bShouldBeActive, true);
		}
	}
}

void ARedShuttleBase::ToggleFlightCamera()
{
	if (!IsLocallyControlled())
	{
		return;
	}
	bThirdPersonCamera = !bThirdPersonCamera;
	ConfigureCockpitCamera();
	ConfigureChaseCamera();
	if (APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		PC->SetViewTarget(this);
	}
	UE_LOG(LogRedShuttle, Display, TEXT("%s camera: %s"), *GetName(),
		bThirdPersonCamera ? TEXT("CHASE") : TEXT("COCKPIT"));
}

void ARedShuttleBase::ToggleLandingAssist()
{
	SetLandingAssistEnabled(!bLandingAssistEnabled);
}

void ARedShuttleBase::SetLandingAssistEnabled(const bool bEnabled)
{
	if (bLandingAssistEnabled == bEnabled)
	{
		return;
	}
	bLandingAssistEnabled = bEnabled;
	if (!bEnabled)
	{
		SetLandingSettled(false);
	}
	if (HasAuthority())
	{
		ForceNetUpdate();
	}
	else
	{
		ServerSetLandingAssistEnabled(bEnabled);
	}
	UE_LOG(LogRedShuttle, Display, TEXT("%s landing assist: %s"), *GetName(),
		bEnabled ? TEXT("ON") : TEXT("OFF"));
}

void ARedShuttleBase::ServerSetLandingAssistEnabled_Implementation(const bool bEnabled)
{
	if (!Controller || !Controller->IsPlayerController())
	{
		return;
	}
	SetLandingAssistEnabled(bEnabled);
}

void ARedShuttleBase::ConfigureChaseCamera()
{
	ConfigureCockpitCamera();
	const float DeltaSeconds = GetWorld() ? GetWorld()->GetDeltaSeconds() : 0.f;
	TArray<USpringArmComponent*> Arms;
	GetComponents<USpringArmComponent>(Arms);
	for (USpringArmComponent* Arm : Arms)
	{
		if (!Arm)
		{
			continue;
		}
		// Chase cam follows the HULL (PCR=false). Middle-mouse look is relative yaw/pitch
		// on the arm — never via ControlRotation, so RMB steer cannot ball-orbit the camera.
		Arm->bUsePawnControlRotation = false;
		Arm->bInheritPitch = true;
		Arm->bInheritYaw = true;
		Arm->bInheritRoll = true;
		Arm->SetUsingAbsoluteRotation(false);
		const float TargetArmLength = ChaseCameraArmLength;
		const FVector TargetSocketOffset = ChaseCameraSocketOffset;
		Arm->TargetArmLength = DeltaSeconds > 0.f
			? FMath::FInterpTo(Arm->TargetArmLength, TargetArmLength, DeltaSeconds, 8.f)
			: TargetArmLength;
		Arm->SocketOffset = DeltaSeconds > 0.f
			? FMath::VInterpTo(Arm->SocketOffset, TargetSocketOffset, DeltaSeconds, 8.f)
			: TargetSocketOffset;
		Arm->bDoCollisionTest = true;
		Arm->ProbeSize = CameraProbeSize;
		Arm->ProbeChannel = ECC_Camera;
		Arm->SetRelativeRotation(FRotator(LookPitchOffset, LookYawOffset, 0.f));
	}

	TArray<UCameraComponent*> Cams;
	GetComponents<UCameraComponent>(Cams);
	for (UCameraComponent* Cam : Cams)
	{
		if (!Cam || Cam == CockpitCamera)
		{
			continue;
		}
		Cam->bUsePawnControlRotation = false; // follow spring arm / hull, not control rot
		Cam->SetRelativeRotation(FRotator::ZeroRotator);
		Cam->SetUsingAbsoluteRotation(false);
	}
	ApplyFlightCameraMode();
}

void ARedShuttleBase::UpdateLookCamera(float DeltaSeconds)
{
	APlayerController* PC = Cast<APlayerController>(GetController());
	if (!PC)
	{
		bLocalExitInputArmed = false;
		LookYawOffset = 0.f;
		LookPitchOffset = 0.f;
		return;
	}

	const bool bRmb = PC->IsInputKeyDown(EKeys::RightMouseButton);
	const bool bFreeLook = PC->IsInputKeyDown(EKeys::MiddleMouseButton);

	// RMB steer owns the view — snap look offsets so cam locks behind the nose.
	if (bRmb)
	{
		LookYawOffset = 0.f;
		LookPitchOffset = 0.f;
	}
	else if (!bFreeLook)
	{
		// Release Middle Mouse: ease back to chase behind the hull.
		LookYawOffset = FMath::FInterpTo(LookYawOffset, 0.f, DeltaSeconds, LookReturnSpeed);
		LookPitchOffset = FMath::FInterpTo(LookPitchOffset, 0.f, DeltaSeconds, LookReturnSpeed);
	}
}

void ARedShuttleBase::PossessedBy(AController* NewController)
{
	Super::PossessedBy(NewController);
	bExitRequestSent = false;
	bLocalExitInputArmed = false;
	if (HasAuthority())
	{
		Occupant = FindPackDriverPawn();
		ForceNetUpdate();
	}
	if (bAutoStartEnginesOnPossess && Cast<APlayerController>(NewController))
	{
		bPendingEngineStart = true;
	}

	ConfigureChaseCamera();

	if (UFloatingPawnMovement* Mov = FindComponentByClass<UFloatingPawnMovement>())
	{
		Mov->StopMovementImmediately();
		Mov->SetComponentTickEnabled(false);
		Mov->Deactivate();
	}

	NoseAim = GetActorForwardVector().GetSafeNormal();
	bNoseAimValid = !NoseAim.IsNearlyZero();
	LookYawOffset = 0.f;
	LookPitchOffset = 0.f;
	bHangarDoorOWasDown = false;

	if (Cast<APlayerController>(NewController) && bRadialFrame)
	{
		AlignToRadialFrame(1.f);
	}
}

void ARedShuttleBase::PawnClientRestart()
{
	Super::PawnClientRestart();
	ConfigureChaseCamera();
	bExitRequestSent = false;
	bLocalExitInputArmed = false;
	if (APlayerController* PC = Cast<APlayerController>(GetController());
		PC && PC->IsLocalController())
	{
		PC->SetInputMode(FInputModeGameOnly());
		PC->bShowMouseCursor = false;
		PC->SetIgnoreMoveInput(false);
		PC->SetIgnoreLookInput(false);
		PC->SetViewTarget(this);
		UE_LOG(LogRedShuttle, Display, TEXT("Client shuttle input armed for %s via %s"),
			*GetNameSafe(this), *GetNameSafe(PC));
	}
}

void ARedShuttleBase::UnPossessed()
{
	bPendingEngineStart = false;
	bFiring = false;
	FlightVelocity = FVector::ZeroVector;
	bNoseAimValid = false;
	LookYawOffset = 0.f;
	LookPitchOffset = 0.f;
	bHangarDoorOWasDown = false;
	bBoostFXOn = false;
	ServerMoveAxes = FVector::ZeroVector;
	ServerRollAxis = 0.f;
	bServerBoostHeld = false;
	bServerSteering = false;
	if (HasAuthority())
	{
		Occupant = nullptr;
		ForceNetUpdate();
	}
	EnsureEnginesOff();
	if (UFloatingPawnMovement* Mov = FindComponentByClass<UFloatingPawnMovement>())
	{
		Mov->Activate();
		Mov->SetComponentTickEnabled(true);
	}
	Super::UnPossessed();
}

FVector ARedShuttleBase::GetVelocity() const
{
	// Pack AdjustEngineRotation (timer) keys nozzle pitch off GetVelocity()·Forward / MaxSpeed.
	// FloatingPawnMovement is disabled while piloted, so expose our radial flight velocity.
	if (GetController())
	{
		return FlightVelocity;
	}
	return Super::GetVelocity();
}

void ARedShuttleBase::AddControllerYawInput(float Val)
{
	if (!bRadialFrame || !GetController())
	{
		Super::AddControllerYawInput(Val);
		return;
	}

	APlayerController* PC = Cast<APlayerController>(GetController());
	if (!PC)
	{
		return;
	}

	const bool bRmb = PC->IsInputKeyDown(EKeys::RightMouseButton);
	const bool bFreeLook = PC->IsInputKeyDown(EKeys::MiddleMouseButton);

	// RMB = steer nose. Middle Mouse (without RMB) = camera look-around. Else swallow.
	if (bRmb || !bRequireRightMouseToSteer)
	{
		ApplySteerDelta(Val, 0.f);
	}
	else if (bFreeLook)
	{
		ApplyLookAroundDelta(Val, 0.f);
	}
}

void ARedShuttleBase::AddControllerPitchInput(float Val)
{
	if (!bRadialFrame || !GetController())
	{
		Super::AddControllerPitchInput(Val);
		return;
	}

	APlayerController* PC = Cast<APlayerController>(GetController());
	if (!PC)
	{
		return;
	}

	const bool bRmb = PC->IsInputKeyDown(EKeys::RightMouseButton);
	const bool bFreeLook = PC->IsInputKeyDown(EKeys::MiddleMouseButton);

	// Pack LookUp is -MouseY (mouse-up → negative Val). Negate so mouse-up = nose/look up.
	if (bRmb || !bRequireRightMouseToSteer)
	{
		ApplySteerDelta(0.f, -Val);
	}
	else if (bFreeLook)
	{
		ApplyLookAroundDelta(0.f, -Val);
	}
}

bool ARedShuttleBase::ApplyLookAroundDelta(float YawDeg, float PitchDeg)
{
	APlayerController* PC = Cast<APlayerController>(GetController());
	if (!PC || (FMath::IsNearlyZero(YawDeg) && FMath::IsNearlyZero(PitchDeg)))
	{
		return false;
	}

	PRAGMA_DISABLE_DEPRECATION_WARNINGS
	const float YawScale = PC->InputYawScale_DEPRECATED;
	const float PitchScale = PC->InputPitchScale_DEPRECATED;
	PRAGMA_ENABLE_DEPRECATION_WARNINGS

	LookYawOffset = FMath::UnwindDegrees(LookYawOffset + YawDeg * YawScale * LookSensitivity);
	LookPitchOffset = FMath::Clamp(
		LookPitchOffset + PitchDeg * PitchScale * LookSensitivity,
		LookPitchMin, LookPitchMax);
	return true;
}

bool ARedShuttleBase::ApplySteerDelta(float YawDeg, float PitchDeg)
{
	APlayerController* PC = Cast<APlayerController>(GetController());
	if (!PC || (FMath::IsNearlyZero(YawDeg) && FMath::IsNearlyZero(PitchDeg)))
	{
		return false;
	}

	FVector Center, RadialUp;
	if (!GetPlanetFrame(Center, RadialUp))
	{
		return false;
	}

	// Match APawn::AddControllerYaw/PitchInput → PC AddYaw/PitchInput (legacy scales on),
	// then damp with SteerSensitivity so RMB doesn't whip the nose around a sphere.
	PRAGMA_DISABLE_DEPRECATION_WARNINGS
	const float YawScale = PC->InputYawScale_DEPRECATED;
	const float PitchScale = PC->InputPitchScale_DEPRECATED;
	PRAGMA_ENABLE_DEPRECATION_WARNINGS
	const float YawDelta = YawDeg * YawScale * SteerSensitivity;
	const float PitchDelta = PitchDeg * PitchScale * SteerSensitivity;

	FVector Aim = bNoseAimValid ? NoseAim : GetActorForwardVector();
	if (Aim.IsNearlyZero())
	{
		Aim = PC->GetControlRotation().Vector();
	}
	Aim = Aim.GetSafeNormal();
	if (Aim.IsNearlyZero())
	{
		return false;
	}

	// Local flight frame from current nose + soft radial-up (zero roll).
	// Yaw around ship Up, pitch around ship Right — direct nose point, not planet-up orbit.
	FVector Up = FVector::VectorPlaneProject(RadialUp, Aim).GetSafeNormal();
	if (Up.IsNearlyZero())
	{
		Up = RadialUp;
	}
	const FVector Right = FVector::CrossProduct(Up, Aim).GetSafeNormal();
	Up = FVector::CrossProduct(Aim, Right).GetSafeNormal();
	if (Right.IsNearlyZero() || Up.IsNearlyZero())
	{
		return false;
	}

	if (!FMath::IsNearlyZero(YawDelta))
	{
		Aim = Aim.RotateAngleAxis(YawDelta, Up).GetSafeNormal();
	}
	if (!FMath::IsNearlyZero(PitchDelta))
	{
		Aim = Aim.RotateAngleAxis(PitchDelta, Right).GetSafeNormal();
	}

	// Soft pitch clamp vs radial-up so you can look up/down freely but not flip inverted.
	const float PitchVsRadial = FMath::RadiansToDegrees(FMath::Asin(
		FMath::Clamp(FVector::DotProduct(Aim, RadialUp), -1.f, 1.f)));
	if (PitchVsRadial < CameraPitchMin || PitchVsRadial > CameraPitchMax)
	{
		const float Clamped = FMath::Clamp(PitchVsRadial, CameraPitchMin, CameraPitchMax);
		const FVector Heading = FVector::VectorPlaneProject(Aim, RadialUp).GetSafeNormal();
		if (!Heading.IsNearlyZero())
		{
			const float PitchRad = FMath::DegreesToRadians(Clamped);
			Aim = (Heading * FMath::Cos(PitchRad) + RadialUp * FMath::Sin(PitchRad)).GetSafeNormal();
		}
	}

	NoseAim = Aim;
	bNoseAimValid = true;
	LookYawOffset = 0.f;
	LookPitchOffset = 0.f;
	// Snappy follow while RMB — soft interp was reading as "circle to a weird angle".
	ApplyNoseAim(NoseAim, RadialUp, /*bHardSnap=*/true);
	return true;
}

void ARedShuttleBase::ApplyNoseAim(const FVector& AimIn, const FVector& RadialUp, bool bHardSnap)
{
	APlayerController* PC = Cast<APlayerController>(GetController());
	if (!PC || AimIn.IsNearlyZero() || RadialUp.IsNearlyZero())
	{
		return;
	}

	const FVector Aim = AimIn.GetSafeNormal();
	// Zero-roll hull: forward = nose, up ≈ radial (MakeFromXZ projects up onto plane ⊥ forward).
	const FQuat DesiredQuat = FRotationMatrix::MakeFromXZ(Aim, RadialUp).ToQuat();
	const FQuat OldQuat = GetActorQuat();
	const FQuat NewQuat = bHardSnap
		? DesiredQuat
		: FMath::QInterpTo(OldQuat, DesiredQuat, GetWorld() ? GetWorld()->GetDeltaSeconds() : (1.f / 60.f), SteerInterpSpeed);

	FlightVelocity = NewQuat.RotateVector(OldQuat.UnrotateVector(FlightVelocity));
	SetActorRotation(NewQuat, ETeleportType::TeleportPhysics);

	// Keep control rot in sync for any pack/UI consumers; chase cam follows the actor
	// (PCR=false + optional middle-mouse relative look), so do not slam SpringArm to CtrlRot.
	PC->SetControlRotation(NewQuat.Rotator());
}

void ARedShuttleBase::GatherLocalFlightInput(APlayerController* PC)
{
	CurrentMoveAxes = FVector::ZeroVector;
	CurrentRollAxis = 0.f;
	bCurrentBoostHeld = false;
	if (!PC)
	{
		return;
	}
	if (PC->IsInputKeyDown(EKeys::W)) { CurrentMoveAxes.X += 1.f; }
	if (PC->IsInputKeyDown(EKeys::S)) { CurrentMoveAxes.X -= 1.f; }
	if (PC->IsInputKeyDown(EKeys::D)) { CurrentMoveAxes.Y += 1.f; }
	if (PC->IsInputKeyDown(EKeys::A)) { CurrentMoveAxes.Y -= 1.f; }
	if (PC->IsInputKeyDown(EKeys::SpaceBar)) { CurrentMoveAxes.Z += 1.f; }
	if (PC->IsInputKeyDown(EKeys::LeftControl)) { CurrentMoveAxes.Z -= 1.f; }
	if (PC->IsInputKeyDown(EKeys::E)) { CurrentRollAxis += 1.f; }
	if (PC->IsInputKeyDown(EKeys::Q)) { CurrentRollAxis -= 1.f; }
	bCurrentBoostHeld = PC->IsInputKeyDown(EKeys::LeftShift);
}

void ARedShuttleBase::ServerSetFlightInput_Implementation(FVector MoveAxes, float RollAxis,
	bool bBoost, FVector_NetQuantizeNormal DesiredNoseAim, bool bSteering)
{
	if (!Controller || !Controller->IsPlayerController())
	{
		return;
	}
	if (MoveAxes.ContainsNaN() || !FMath::IsFinite(RollAxis))
	{
		return;
	}
	ServerMoveAxes = FVector(
		FMath::Clamp(MoveAxes.X, -1.f, 1.f),
		FMath::Clamp(MoveAxes.Y, -1.f, 1.f),
		FMath::Clamp(MoveAxes.Z, -1.f, 1.f));
	ServerRollAxis = FMath::Clamp(RollAxis, -1.f, 1.f);
	bServerBoostHeld = bBoost;
	bServerSteering = bSteering;
	const FVector RequestedAim = FVector(DesiredNoseAim).GetSafeNormal();
	if (!RequestedAim.IsNearlyZero() && !RequestedAim.ContainsNaN())
	{
		ServerDesiredNoseAim = RequestedAim;
	}
	LastServerFlightInputTime = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
}

void ARedShuttleBase::UpdateAuthoritativeRemoteAim(float DeltaSeconds)
{
	if (!bServerSteering || DeltaSeconds <= 0.f || ServerDesiredNoseAim.IsNearlyZero())
	{
		return;
	}
	const FVector CurrentAim = bNoseAimValid ? NoseAim.GetSafeNormal() : GetActorForwardVector().GetSafeNormal();
	if (CurrentAim.IsNearlyZero())
	{
		return;
	}
	NoseAim = FMath::VInterpNormalRotationTo(CurrentAim, ServerDesiredNoseAim.GetSafeNormal(),
		DeltaSeconds, 150.f).GetSafeNormal();
	bNoseAimValid = !NoseAim.IsNearlyZero();
}

void ARedShuttleBase::Tick(float DeltaSeconds)
{
	if (!bRuntimeCollisionHullsConfigured)
	{
		bRuntimeCollisionHullsConfigured = ConfigureRuntimeCollisionHulls();
		if (bRuntimeCollisionHullsConfigured)
		{
			bCockpitCameraPositioned = false;
			ConfigureCockpitCamera();
		}
	}
	UpdateWeaponHeat(DeltaSeconds);
	if (FireCooldown > 0.f)
	{
		FireCooldown -= DeltaSeconds;
	}
	if (bFiring && FireCooldown <= 0.f)
	{
		Fire();
		FireCooldown = FMath::Max(0.03f, FireInterval);
	}

	APlayerController* PC = Cast<APlayerController>(GetController());
	if (!PC)
	{
		bLocalExitInputArmed = false;
		// PARKED on a mesh planet: do NOT call Super::Tick — the pack EventGraph re-levels to
		// WORLD +Z every frame, which at the basin (radial ≈ world Y) lays the ship on its wing
		// (right·radial ≈ 1). Skip pack tick and keep hull radial-up / gear-down ourselves.
		// Also force engines OFF so landed ships don't keep roaring.
		EnsureEnginesOff();
		if (bLandingAssistEnabled)
		{
			if (GetLocalRole() != ROLE_SimulatedProxy)
			{
				ApplyLandingAssist(DeltaSeconds);
			}
			return;
		}
		if (bRadialFrame)
		{
			FVector Center, RadialUp;
			if (GetPlanetFrame(Center, RadialUp))
			{
				AlignToRadialFrame(DeltaSeconds);
				return;
			}
		}
		Super::Tick(DeltaSeconds);
		return;
	}

	// The migrated Blueprint can rebuild/replace its legacy action bindings during possession.
	// Read the raw V/gamepad edge from the owning controller in C++ so leaving is dependable on
	// clients as well as the listen server. The grace period prevents the boarding press itself
	// from being reinterpreted as an immediate exit on the first possessed frame.
	if (IsLocallyControlled())
	{
		const double Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
		if (PC->WasInputKeyJustPressed(EKeys::L))
		{
			// The migrated pack Blueprint can replace action bindings, so poll this one reliable edge.
			ToggleLandingAssist();
		}
		if (PC->WasInputKeyJustPressed(EKeys::C))
		{
			// Keep camera switching reliable even when the migrated pack rebuilds its input bindings.
			ToggleFlightCamera();
		}
		if (!bLocalExitInputArmed)
		{
			bLocalExitInputArmed = true;
			LocalExitInputReadyTime = Now + 0.75;
		}
		else if (Now >= LocalExitInputReadyTime
			&& (PC->WasInputKeyJustPressed(EKeys::B)
				|| PC->WasInputKeyJustPressed(EKeys::V)
				|| PC->WasInputKeyJustPressed(EKeys::Gamepad_FaceButton_Top)))
		{
			ExitShuttle();
			return;
		}
	}
	else
	{
		bLocalExitInputArmed = false;
	}

	// CRITICAL: do NOT call Super::Tick while piloted — pack EventGraph assumes world +Z
	// (SwayShip2 / TurnShip / world-up leveling). We re-drive look, roll, nozzles, flight, door.

	if (HasAuthority() && !Occupant)
	{
		Occupant = FindPackDriverPawn();
		if (Occupant) { ForceNetUpdate(); }
	}

	const bool bRemoteAuthority = HasAuthority() && !PC->IsLocalController();
	if (bRemoteAuthority)
	{
		if (!GetWorld() || GetWorld()->GetTimeSeconds() - LastServerFlightInputTime > 0.30)
		{
			ServerMoveAxes = FVector::ZeroVector;
			ServerRollAxis = 0.f;
			bServerBoostHeld = false;
			bServerSteering = false;
		}
		CurrentMoveAxes = ServerMoveAxes;
		CurrentRollAxis = ServerRollAxis;
		bCurrentBoostHeld = bServerBoostHeld;
		UpdateAuthoritativeRemoteAim(DeltaSeconds);
	}
	else
	{
		GatherLocalFlightInput(PC);
		if (!HasAuthority() && IsLocallyControlled())
		{
			const FVector Aim = bNoseAimValid ? NoseAim : GetActorForwardVector();
			const bool bSteering = !bRequireRightMouseToSteer
				|| PC->IsInputKeyDown(EKeys::RightMouseButton);
			ServerSetFlightInput(CurrentMoveAxes, CurrentRollAxis, bCurrentBoostHeld,
				Aim.GetSafeNormal(), bSteering);
		}
	}
	if (bLandingAssistEnabled && bLandingSettled && CurrentMoveAxes.Z > 0.35f)
	{
		SetLandingAssistEnabled(false);
	}

	if (!bLandingSettled)
	{
		bEnginesForcedOff = false;
		if (bPendingEngineStart)
		{
			EnsureEnginesOn();
			bPendingEngineStart = false;
		}

		SetBoolProperty(this, TEXT("EngineOn"), true);
		SetBoolProperty(this, TEXT("InFlyingElevation"), true);
	}

	if (UFloatingPawnMovement* Mov = FindComponentByClass<UFloatingPawnMovement>())
	{
		if (Mov->IsActive() || Mov->IsComponentTickEnabled())
		{
			Mov->StopMovementImmediately();
			Mov->SetComponentTickEnabled(false);
			Mov->Deactivate();
		}
	}

	// Pack BP may flip SpringArm inherit flags each tick — re-assert every frame.
	UpdateLookCamera(DeltaSeconds);
	ConfigureChaseCamera();

	// Soft radial level only when NOT RMB-steering — otherwise AlignToRadialFrame and
	// ApplySteerDelta fight each other. While RMB is held, hard-follow NoseAim each tick
	// so W flies straight where the nose points (no soft circle lag).
	const bool bRmbSteer = bRemoteAuthority
		? bServerSteering
		: (!bRequireRightMouseToSteer || PC->IsInputKeyDown(EKeys::RightMouseButton));
	if (bRadialFrame && !bLandingSettled)
	{
		if (bRmbSteer)
		{
			FVector Center, RadialUp;
			if (bNoseAimValid && GetPlanetFrame(Center, RadialUp))
			{
				ApplyNoseAim(NoseAim, RadialUp, /*bHardSnap=*/true);
			}
		}
		else
		{
			AlignToRadialFrame(DeltaSeconds);
		}
	}

	if (!bLandingSettled)
	{
		ApplyBarrelRollInput(PC, DeltaSeconds);
	}
	ApplyHangarDoorInput(PC, DeltaSeconds);
	UpdateHangarDoor(DeltaSeconds);
	ApplyHeldFlightInput(PC, DeltaSeconds);
	if (!bLandingAssistEnabled)
	{
		ClampAboveTerrain();
	}
	if (GetLocalRole() != ROLE_SimulatedProxy)
	{
		ApplyLandingAssist(DeltaSeconds);
	}
	ClampCameraAboveTerrain();
	if (!bLandingSettled)
	{
		UpdateEngineNozzles();
	}

	const bool bBoost = bCurrentBoostHeld && !bLandingSettled;
	UpdateBoostFX(bBoost);
	if (bLandingSettled)
	{
		EnsureEnginesOff();
	}
	else
	{
		// Re-assert the pack-authored nozzle thrusters + engine audio; child actors can spawn late.
		RedShuttlePrivate::SetEngineFXActive(this, true, bBoost ? 2.4f : 1.f);
	}

	// UpdateEngineNozzles above is the sole owner. Do not manually invoke the purchased
	// Blueprint's timer function with a null parameter frame every tick.
}

bool ARedShuttleBase::SetBoolProperty(UObject* Obj, FName Name, bool bValue)
{
	if (!Obj)
	{
		return false;
	}
	if (FBoolProperty* Prop = FindFProperty<FBoolProperty>(Obj->GetClass(), Name))
	{
		Prop->SetPropertyValue_InContainer(Obj, bValue);
		return true;
	}
	return false;
}

bool ARedShuttleBase::GetBoolProperty(UObject* Obj, FName Name, bool& OutValue)
{
	OutValue = false;
	if (!Obj)
	{
		return false;
	}
	if (FBoolProperty* Prop = FindFProperty<FBoolProperty>(Obj->GetClass(), Name))
	{
		OutValue = Prop->GetPropertyValue_InContainer(Obj);
		return true;
	}
	return false;
}

void ARedShuttleBase::EnsureEnginesOn()
{
	bool bAlreadyOn = false;
	GetBoolProperty(this, TEXT("EngineOn"), bAlreadyOn);

	// Native flight owns engine state and nozzle/audio presentation. Starting the pack's latent
	// single-player graph here and then overriding it every frame left stale UObject references.
	SetBoolProperty(this, TEXT("EngineOn"), true);
	SetBoolProperty(this, TEXT("InFlyingElevation"), true);
	bEnginesForcedOff = false;
	RedShuttlePrivate::SetEngineFXActive(this, true, 1.f);

	bool bOn = false;
	GetBoolProperty(this, TEXT("EngineOn"), bOn);
	UE_LOG(LogRedShuttle, Display, TEXT("EnsureEnginesOn on %s (was=%d now=%d)"),
		*GetName(), bAlreadyOn ? 1 : 0, bOn ? 1 : 0);
}

void ARedShuttleBase::EnsureEnginesOff()
{
	if (bEnginesForcedOff)
	{
		// Still re-assert FX off — pack EventGraph can re-light nozzles.
		RedShuttlePrivate::SetEngineFXActive(this, false, 1.f);
		SetBoolProperty(this, TEXT("EngineOn"), false);
		SetBoolProperty(this, TEXT("InFlyingElevation"), false);
		return;
	}

	SetBoolProperty(this, TEXT("EngineOn"), false);
	SetBoolProperty(this, TEXT("InFlyingElevation"), false);
	RedShuttlePrivate::SetEngineFXActive(this, false, 1.f);
	bEnginesForcedOff = true;
	bBoostFXOn = false;
	UE_LOG(LogRedShuttle, Display, TEXT("EnsureEnginesOff on %s"), *GetName());
}

bool ARedShuttleBase::GetPlanetFrame(FVector& OutCenter, FVector& OutRadialUp) const
{
	OutCenter = FVector::ZeroVector;
	OutRadialUp = FVector::UpVector;
	UWorld* World = GetWorld();
	if (!World)
	{
		return false;
	}

	FVector Center = FVector::ZeroVector;
	float SurfaceRadius = 0.f;
	if (!RedGravity::QueryDominantBody(World, GetActorLocation(), Center, SurfaceRadius)
		|| SurfaceRadius <= 0.f)
	{
		// PlanetGen can stream in after this actor. Do not invent a radial frame around world origin.
		return false;
	}

	const FVector Loc = GetActorLocation();
	const FVector RadialUp = (Loc - Center).GetSafeNormal();
	if (RadialUp.IsNearlyZero())
	{
		return false;
	}
	OutCenter = Center;
	OutRadialUp = RadialUp;
	return true;
}

void ARedShuttleBase::AlignToRadialFrame(float DeltaSeconds)
{
	FVector Center, RadialUp;
	if (!GetPlanetFrame(Center, RadialUp))
	{
		return;
	}

	if (APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		// Piloted: soft-level zero-roll toward radial-up while PRESERVING free nose aim.
		// Do NOT rebuild aim from tangent-plane heading + CameraPitchDeg — that was the
		// "spinning on a ball / invisible circle" path (yaw around planet up only).
		if (!bNoseAimValid || NoseAim.IsNearlyZero())
		{
			NoseAim = GetActorForwardVector().GetSafeNormal();
			if (NoseAim.IsNearlyZero())
			{
				NoseAim = PC->GetControlRotation().Vector().GetSafeNormal();
			}
			bNoseAimValid = !NoseAim.IsNearlyZero();
		}
		if (!bNoseAimValid)
		{
			return;
		}

		// Soft radial leveling only (keeps wings level); nose stays where mouse pointed.
		const FQuat OldQuat = GetActorQuat();
		const FQuat DesiredQuat = FRotationMatrix::MakeFromXZ(NoseAim, RadialUp).ToQuat();
		const bool bHard = DeltaSeconds >= 0.99f || RadialAlignSpeed <= KINDA_SMALL_NUMBER;
		const FQuat NewQuat = bHard
			? DesiredQuat
			: FMath::QInterpTo(OldQuat, DesiredQuat, DeltaSeconds, RadialAlignSpeed);

		FlightVelocity = NewQuat.RotateVector(OldQuat.UnrotateVector(FlightVelocity));
		SetActorRotation(NewQuat, ETeleportType::TeleportPhysics);
		PC->SetControlRotation(NewQuat.Rotator());
	}
	else
	{
		// Parked: flat radial-upright (no free pitch).
		FVector Forward = FVector::VectorPlaneProject(GetActorForwardVector(), RadialUp).GetSafeNormal();
		if (Forward.IsNearlyZero())
		{
			Forward = FVector::VectorPlaneProject(FVector::ForwardVector, RadialUp).GetSafeNormal();
		}
		if (Forward.IsNearlyZero())
		{
			return;
		}
		const FQuat OldQuat = GetActorQuat();
		const FQuat NewQuat = FRotationMatrix::MakeFromZX(RadialUp, Forward).ToQuat();
		FlightVelocity = NewQuat.RotateVector(OldQuat.UnrotateVector(FlightVelocity));
		SetActorRotation(NewQuat, ETeleportType::TeleportPhysics);
	}
}

void ARedShuttleBase::ApplyHeldFlightInput(APlayerController* PC, float DeltaSeconds)
{
	if (!PC || DeltaSeconds <= 0.f)
	{
		return;
	}
	if (bLandingAssistEnabled && bLandingSettled)
	{
		FlightVelocity = FVector::ZeroVector;
		return;
	}

	// Poll keys directly — pack axis bindings assume FloatingPawnMovement (disabled while piloted).
	const bool bBoost = bCurrentBoostHeld;
	float VacuumAlpha = 0.f;
	FVector BodyCenter = FVector::ZeroVector;
	float BodyRadius = 0.f;
	if (RedGravity::QueryDominantBody(GetWorld(), GetActorLocation(), BodyCenter, BodyRadius)
		&& BodyRadius > 0.f)
	{
		const float Altitude = static_cast<float>((GetActorLocation() - BodyCenter).Size()) - BodyRadius;
		VacuumAlpha = FMath::Clamp((Altitude - SpaceTransitionAltitudeCm) / 75000.f, 0.f, 1.f);
	}
	const float EnvironmentSpeedMultiplier = FMath::Lerp(1.f,
		FMath::Max(1.f, SpaceSpeedMultiplier), VacuumAlpha);
	const float MaxSpeed = FlightSpeed * EnvironmentSpeedMultiplier
		* (bBoost ? BoostMultiplier : 1.f);
	const float EffectiveAccel = FlightAccel * FMath::Lerp(1.f,
		FMath::Max(1.f, SpaceAccelerationMultiplier), VacuumAlpha);

	FVector LocalInput = CurrentMoveAxes;
	if (!LocalInput.IsNearlyZero())
	{
		LocalInput = LocalInput.GetSafeNormal();
		// Thrust in the nose/hull frame: W = along nose (RMB aim), A/D strafe, Space/Ctrl lift.
		// Prefer live NoseAim when valid so W tracks the steered nose, not a lagging hull quat.
		FVector Fwd = (bNoseAimValid && !NoseAim.IsNearlyZero()) ? NoseAim.GetSafeNormal() : GetActorForwardVector();
		FVector RightV = GetActorRightVector();
		FVector UpV = GetActorUpVector();
		FVector Center, RadialUp;
		if (GetPlanetFrame(Center, RadialUp))
		{
			UpV = RadialUp;
			RightV = FVector::CrossProduct(UpV, Fwd).GetSafeNormal();
			if (RightV.IsNearlyZero())
			{
				RightV = GetActorRightVector();
			}
			UpV = FVector::CrossProduct(Fwd, RightV).GetSafeNormal();
			if (UpV.IsNearlyZero())
			{
				UpV = RadialUp;
			}
		}
		const FVector Desired =
			(Fwd * LocalInput.X + RightV * LocalInput.Y + UpV * LocalInput.Z) * MaxSpeed;
		FlightVelocity = FMath::VInterpTo(FlightVelocity, Desired, DeltaSeconds, EffectiveAccel);
	}
	else
	{
		FlightVelocity = FMath::VInterpTo(FlightVelocity, FVector::ZeroVector, DeltaSeconds, EffectiveAccel * 0.35f);
	}

	if (!FlightVelocity.IsNearlyZero())
	{
		// No sweep — large hull vs planet mesh was eating W/A/S/D while Space (up) still cleared.
		// Terrain penetration is corrected by ClampAboveTerrain after the move.
		AddActorWorldOffset(FlightVelocity * DeltaSeconds, /*bSweep=*/false);
	}
}

bool ARedShuttleBase::QueryPlanetSurface(const FVector& From, FVector& OutHitPoint, FVector& OutHitNormal) const
{
	OutHitPoint = FVector::ZeroVector;
	OutHitNormal = FVector::UpVector;
	UWorld* World = GetWorld();
	if (!World)
	{
		return false;
	}

	FVector Center, RadialUp;
	if (!GetPlanetFrame(Center, RadialUp))
	{
		return false;
	}

	// Trace from above the ship toward planet center so we hit the outer terrain skin.
	const FVector Start = From + RadialUp * 50000.f;
	const FVector End = Center;
	FHitResult Hit;
	const ERedPlanetTerrainQueryResult TerrainResult = RedPlanetTerrainQuery::LineTrace(
		World, Center, Start, End, Hit);
	if (TerrainResult == ERedPlanetTerrainQueryResult::Hit)
	{
		OutHitPoint = Hit.ImpactPoint;
		OutHitNormal = Hit.ImpactNormal.GetSafeNormal();
		if (OutHitNormal.IsNearlyZero())
		{
			OutHitNormal = RadialUp;
		}
		return true;
	}
	if (TerrainResult == ERedPlanetTerrainQueryResult::NoHit)
	{
		return false;
	}

	// A legacy/static moon has no matching PlanetGen actor and keeps the previous channel traces.
	FCollisionQueryParams Params(SCENE_QUERY_STAT(RedShuttleSurface), /*bTraceComplex=*/true);
	Params.AddIgnoredActor(this);
	if (World->LineTraceSingleByChannel(Hit, Start, End, ECC_WorldStatic, Params)
		|| World->LineTraceSingleByChannel(Hit, Start, End, ECC_Visibility, Params))
	{
		OutHitPoint = Hit.ImpactPoint;
		OutHitNormal = Hit.ImpactNormal.GetSafeNormal();
		if (OutHitNormal.IsNearlyZero())
		{
			OutHitNormal = RadialUp;
		}
		return true;
	}
	return false;
}

void ARedShuttleBase::ClampAboveTerrain()
{
	FVector Center, RadialUp;
	if (!GetPlanetFrame(Center, RadialUp))
	{
		return;
	}

	const FVector Loc = GetActorLocation();
	FVector HitPoint, HitNormal;
	float MinRadius = 0.f;
	if (QueryPlanetSurface(Loc, HitPoint, HitNormal))
	{
		MinRadius = (HitPoint - Center).Size() + MinSurfaceClearance;
	}
	else
	{
		// Fallback to the dominant body's authored surface.  Preserve the home planet's
		// conservative mountain peak, while a nearby moon uses its own solid sphere.
		FVector DominantCenter = FVector::ZeroVector;
		float DominantSurfaceRadius = 0.f;
		if (RedGravity::QueryDominantBody(GetWorld(), Loc, DominantCenter, DominantSurfaceRadius)
			&& DominantSurfaceRadius > 1000.f)
		{
			Center = DominantCenter;
			MinRadius = DominantSurfaceRadius + MinSurfaceClearance;
			FVector HomeCenter = FVector::ZeroVector;
			float HomeDatumRadius = 0.f;
			float HomePeakRadius = 0.f;
			if (RedGravity::FindMeshPlanet(
				GetWorld(), HomeCenter, HomeDatumRadius, &HomePeakRadius)
				&& HomeCenter.Equals(Center, 100.f)
				&& HomePeakRadius > DominantSurfaceRadius)
			{
				MinRadius = HomePeakRadius + MinSurfaceClearance;
			}
			RadialUp = (Loc - Center).GetSafeNormal();
			if (RadialUp.IsNearlyZero())
			{
				return;
			}
		}
		else
		{
			return;
		}
	}

	const float CurRadius = (Loc - Center).Size();
	if (CurRadius < MinRadius)
	{
		const FVector SafeLoc = Center + RadialUp * MinRadius;
		SetActorLocation(SafeLoc, false, nullptr, ETeleportType::TeleportPhysics);
		// Kill inward (into-planet) velocity so thrust into ground doesn't chatter.
		const float Inward = FVector::DotProduct(FlightVelocity, RadialUp);
		if (Inward < 0.f)
		{
			FlightVelocity -= RadialUp * Inward;
		}
	}
}

float ARedShuttleBase::GetLandingSupportDistance(const FVector& SurfaceNormal) const
{
	const UPrimitiveComponent* BoundsComponent = RuntimeHullCollision
		? Cast<UPrimitiveComponent>(RuntimeHullCollision)
		: Cast<UPrimitiveComponent>(GetRootComponent());
	if (!BoundsComponent)
	{
		return FMath::Max(50.f, MinSurfaceClearance);
	}
	const FBoxSphereBounds Bounds = BoundsComponent->Bounds;
	const FVector Normal = SurfaceNormal.GetSafeNormal();
	const float Support = FVector::DotProduct(Bounds.BoxExtent, Normal.GetAbs());
	const float LowestProjection = FVector::DotProduct(Bounds.Origin, Normal) - Support;
	return FMath::Max(50.f,
		FVector::DotProduct(GetActorLocation(), Normal) - LowestProjection)
		+ FMath::Max(0.f, LandingAssistSurfaceGap);
}

void ARedShuttleBase::SetLandingSettled(const bool bSettled)
{
	if (bLandingSettled == bSettled)
	{
		return;
	}
	bLandingSettled = bSettled;
	if (HasAuthority())
	{
		ForceNetUpdate();
	}
}

void ARedShuttleBase::ApplyLandingAssist(const float DeltaSeconds)
{
	if (!bLandingAssistEnabled || DeltaSeconds <= 0.f)
	{
		return;
	}

	FVector Center, RadialUp;
	if (!GetPlanetFrame(Center, RadialUp))
	{
		SetLandingSettled(false);
		return;
	}
	FVector HitPoint, SurfaceNormal;
	if (!QueryPlanetSurface(GetActorLocation(), HitPoint, SurfaceNormal))
	{
		SetLandingSettled(false);
		return;
	}
	// Use physical collision for touchdown height but dominant-body radial up for attitude.
	// Raw mesh normals on a coarse moon can flip/tilt between triangles and previously allowed
	// the shuttle to settle inverted.
	SurfaceNormal = RadialUp;

	const float InitialSupportDistance = GetLandingSupportDistance(SurfaceNormal);
	const float InitialClearance = FVector::DotProduct(
		GetActorLocation() - HitPoint, SurfaceNormal) - InitialSupportDistance;
	if (!bLandingSettled
		&& InitialClearance > FMath::Max(500.f, LandingAssistTraceDistance))
	{
		return;
	}

	FVector Forward = FVector::VectorPlaneProject(GetActorForwardVector(), SurfaceNormal).GetSafeNormal();
	if (Forward.IsNearlyZero())
	{
		Forward = FVector::CrossProduct(GetActorRightVector(), SurfaceNormal).GetSafeNormal();
	}
	if (Forward.IsNearlyZero())
	{
		return;
	}
	const FQuat DesiredRotation = FRotationMatrix::MakeFromXZ(Forward, SurfaceNormal).ToQuat();
	const FQuat NewRotation = bLandingSettled
		? DesiredRotation
		: FMath::QInterpTo(GetActorQuat(), DesiredRotation, DeltaSeconds,
			FMath::Max(0.1f, LandingAssistAlignSpeed));
	SetActorRotation(NewRotation, ETeleportType::TeleportPhysics);
	NoseAim = NewRotation.GetForwardVector().GetSafeNormal();
	bNoseAimValid = !NoseAim.IsNearlyZero();
	if (APlayerController* PC = Cast<APlayerController>(GetController());
		PC && PC->IsLocalController())
	{
		PC->SetControlRotation(NewRotation.Rotator());
	}

	const float SupportDistance = GetLandingSupportDistance(SurfaceNormal);
	const float Clearance = FVector::DotProduct(
		GetActorLocation() - HitPoint, SurfaceNormal) - SupportDistance;
	const FVector TouchdownLocation = HitPoint + SurfaceNormal * SupportDistance;
	if (bLandingSettled)
	{
		SetActorLocation(TouchdownLocation, false, nullptr, ETeleportType::TeleportPhysics);
		FlightVelocity = FVector::ZeroVector;
		return;
	}

	const float NormalSpeed = FVector::DotProduct(FlightVelocity, SurfaceNormal);
	FVector TangentialVelocity = FVector::VectorPlaneProject(FlightVelocity, SurfaceNormal);
	const float NearAlpha = FMath::Clamp(
		1.f - FMath::Max(0.f, Clearance) / FMath::Max(500.f, LandingAssistTraceDistance), 0.f, 1.f);
	TangentialVelocity = FMath::VInterpTo(TangentialVelocity, FVector::ZeroVector,
		DeltaSeconds, FMath::Lerp(0.5f, FMath::Max(0.f, LandingAssistLateralDamping), NearAlpha));
	const float DesiredDownSpeed = -FMath::Clamp(FMath::Max(0.f, Clearance) * 0.55f,
		45.f, FMath::Max(100.f, LandingAssistMaxDescentSpeed));
	const float NewNormalSpeed = FMath::FInterpTo(NormalSpeed, DesiredDownSpeed,
		DeltaSeconds, 2.5f);
	FlightVelocity = TangentialVelocity + SurfaceNormal * NewNormalSpeed;
	if (!Controller)
	{
		AddActorWorldOffset(FlightVelocity * DeltaSeconds, false, nullptr,
			ETeleportType::TeleportPhysics);
	}

	if (Clearance <= FMath::Max(5.f, LandingAssistTouchdownDistance)
		&& (Clearance <= 0.f || FMath::Abs(NewNormalSpeed) <= 160.f))
	{
		SetActorLocation(TouchdownLocation, false, nullptr, ETeleportType::TeleportPhysics);
		SetActorRotation(DesiredRotation, ETeleportType::TeleportPhysics);
		FlightVelocity = FVector::ZeroVector;
		SetLandingSettled(true);
	}
}

void ARedShuttleBase::ClampCameraAboveTerrain()
{
	FVector Center, RadialUp;
	if (!GetPlanetFrame(Center, RadialUp))
	{
		return;
	}

	TArray<UCameraComponent*> Cams;
	GetComponents<UCameraComponent>(Cams);
	for (UCameraComponent* Cam : Cams)
	{
		if (!Cam || Cam == CockpitCamera || !Cam->IsActive())
		{
			continue;
		}
		const FVector CamLoc = Cam->GetComponentLocation();
		FVector HitPoint, HitNormal;
		float MinRadius = 0.f;
		if (QueryPlanetSurface(CamLoc, HitPoint, HitNormal))
		{
			MinRadius = (HitPoint - Center).Size() + CameraSurfaceMargin;
		}
		else
		{
			FVector DominantCenter = FVector::ZeroVector;
			float DominantSurfaceRadius = 0.f;
			if (!RedGravity::QueryDominantBody(
				GetWorld(), CamLoc, DominantCenter, DominantSurfaceRadius)
				|| DominantSurfaceRadius < 1000.f)
			{
				continue;
			}
			Center = DominantCenter;
			MinRadius = DominantSurfaceRadius + CameraSurfaceMargin;
			FVector HomeCenter = FVector::ZeroVector;
			float HomeDatumRadius = 0.f;
			float HomePeakRadius = 0.f;
			if (RedGravity::FindMeshPlanet(
				GetWorld(), HomeCenter, HomeDatumRadius, &HomePeakRadius)
				&& HomeCenter.Equals(Center, 100.f)
				&& HomePeakRadius > DominantSurfaceRadius)
			{
				MinRadius = HomePeakRadius + CameraSurfaceMargin;
			}
		}

		const FVector CamRadial = (CamLoc - Center).GetSafeNormal();
		if (CamRadial.IsNearlyZero())
		{
			continue;
		}
		const float CamR = (CamLoc - Center).Size();
		if (CamR < MinRadius)
		{
			// Pull camera out radially; spring arm will re-settle next tick with collision.
			Cam->SetWorldLocation(Center + CamRadial * MinRadius);
		}
	}
}

USceneComponent* ARedShuttleBase::FindPackVisualMesh() const
{
	// Pack TurnShip / sway targets CLM_Shuttle (scene component on the BP).
	if (FObjectPropertyBase* Prop = FindFProperty<FObjectPropertyBase>(GetClass(), TEXT("CLM_Shuttle")))
	{
		if (UObject* Obj = Prop->GetObjectPropertyValue_InContainer(this))
		{
			if (USceneComponent* SC = Cast<USceneComponent>(Obj))
			{
				return SC;
			}
			if (AActor* Act = Cast<AActor>(Obj))
			{
				return Act->GetRootComponent();
			}
		}
	}
	return nullptr;
}

USceneComponent* ARedShuttleBase::FindDoorHinge() const
{
	if (FObjectPropertyBase* Prop = FindFProperty<FObjectPropertyBase>(GetClass(), TEXT("DoorHinge")))
	{
		if (UObject* Obj = Prop->GetObjectPropertyValue_InContainer(this))
		{
			if (USceneComponent* SC = Cast<USceneComponent>(Obj))
			{
				return SC;
			}
		}
	}
	// Fallback: component name search (pack may expose it only as a component).
	TArray<USceneComponent*> Comps;
	GetComponents<USceneComponent>(Comps);
	for (USceneComponent* SC : Comps)
	{
		if (SC && SC->GetFName() == TEXT("DoorHinge"))
		{
			return SC;
		}
	}
	return nullptr;
}

void ARedShuttleBase::ToggleHangarDoor()
{
	bHangarDoorOpen = !bHangarDoorOpen;
	UE_LOG(LogRedShuttle, Display, TEXT("Hangar door %s on %s"),
		bHangarDoorOpen ? TEXT("OPEN") : TEXT("CLOSE"), *GetName());
}

void ARedShuttleBase::ApplyHangarDoorInput(APlayerController* PC, float /*DeltaSeconds*/)
{
	if (!PC)
	{
		return;
	}
	// Pack EventGraph: InputKey O → FlipFlop → Timeline_1 → DoorHinge pitch.
	// We skip Super::Tick while piloted, so that graph never runs — edge-detect O here.
	const bool bDown = PC->IsInputKeyDown(EKeys::O);
	if (bDown && !bHangarDoorOWasDown)
	{
		ToggleHangarDoor();
	}
	bHangarDoorOWasDown = bDown;
}

void ARedShuttleBase::UpdateHangarDoor(float DeltaSeconds)
{
	if (DeltaSeconds <= 0.f)
	{
		return;
	}
	USceneComponent* Hinge = FindDoorHinge();
	if (!Hinge)
	{
		return;
	}

	const float Target = bHangarDoorOpen ? 1.f : 0.f;
	HangarDoorAlpha = FMath::FInterpConstantTo(HangarDoorAlpha, Target, DeltaSeconds, HangarDoorSpeed);
	const float Pitch = FMath::Lerp(
		RedShuttlePrivate::HangarDoorClosedPitch,
		RedShuttlePrivate::HangarDoorOpenPitch,
		HangarDoorAlpha);
	Hinge->SetRelativeRotation(FRotator(Pitch, 0.f, 0.f));
	if (RuntimeLoadingRampCollision)
	{
		RuntimeLoadingRampCollision->SetCollisionEnabled(
			HangarDoorAlpha >= 0.92f
				? ECollisionEnabled::QueryAndPhysics
				: ECollisionEnabled::NoCollision);
	}
}

void ARedShuttleBase::ApplyBarrelRollInput(APlayerController* PC, float DeltaSeconds)
{
	if (!PC || DeltaSeconds <= 0.f || BarrelRollSpeed <= 0.f)
	{
		return;
	}

	// Pack maps Q/E → "Turning"; project also has ShipRoll on Q/E. Hold-keys so we don't
	// depend on Event Tick (skipped while piloted).
	const float Roll = CurrentRollAxis;
	if (FMath::IsNearlyZero(Roll))
	{
		return;
	}

	if (USceneComponent* Visual = FindPackVisualMesh())
	{
		Visual->AddLocalRotation(FRotator(0.f, 0.f, Roll * BarrelRollSpeed * DeltaSeconds));
	}
	else
	{
		AddActorLocalRotation(FRotator(0.f, 0.f, Roll * BarrelRollSpeed * DeltaSeconds));
	}
}

void ARedShuttleBase::UpdateEngineNozzles()
{
	// Pack AdjustEngineRotation used Velocity·Forward / MaxSpeed.
	// Prefer held thrust intent so Space (lift) keeps plumes DOWN even while coasting,
	// and W+Space blends aft/down from the combined input.
	const float ForwardIntent = CurrentMoveAxes.X;
	const float UpIntent = CurrentMoveAxes.Z;

	float Alpha = 0.f; // 0 = down plumes, 1 = aft plumes
	if (!FMath::IsNearlyZero(ForwardIntent) || !FMath::IsNearlyZero(UpIntent))
	{
		const float Fwd = FMath::Max(ForwardIntent, 0.f);
		const float Up = FMath::Max(UpIntent, 0.f);
		const float Sum = Fwd + Up;
		Alpha = (Sum > KINDA_SMALL_NUMBER) ? (Fwd / Sum) : 0.f;
	}
	else
	{
		const float MaxSpeed = FMath::Max(FlightSpeed, 1.f);
		const float ForwardSpeed = FVector::DotProduct(FlightVelocity, GetActorForwardVector());
		Alpha = FMath::Clamp(ForwardSpeed / MaxSpeed, 0.f, 1.f);
	}

	// Pack: Pitch = clamp(Alpha*-90 + 90) → 90° down at rest/lift, 0° aft at full forward.
	const float Pitch = FMath::Clamp(Alpha * -90.f + 90.f, 0.f, 135.f);
	const FRotator EngineRot(Pitch, 0.f, 0.f);

	for (const FName& Name : RedShuttlePrivate::EngineCompNames)
	{
		FObjectPropertyBase* Prop = FindFProperty<FObjectPropertyBase>(GetClass(), Name);
		if (!Prop)
		{
			continue;
		}
		UObject* Obj = Prop->GetObjectPropertyValue_InContainer(this);
		if (!Obj)
		{
			continue;
		}

		if (UChildActorComponent* CAC = Cast<UChildActorComponent>(Obj))
		{
			CAC->SetRelativeRotation(EngineRot);
		}
		else if (USceneComponent* SC = Cast<USceneComponent>(Obj))
		{
			SC->SetRelativeRotation(EngineRot);
		}
		else if (AActor* Act = Cast<AActor>(Obj))
		{
			if (USceneComponent* Root = Act->GetRootComponent())
			{
				Root->SetRelativeRotation(EngineRot);
			}
		}
	}
}

void ARedShuttleBase::UpdateBoostFX(bool bBoost)
{
	bBoostFXOn = bBoost;
	// Tick path re-asserts SetEngineFXActive; this only tracks boost state for callers.
}
