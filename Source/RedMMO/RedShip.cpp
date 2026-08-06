#include "RedShip.h"

#include "RedShipMovementComponent.h"
#include "RedShipExplosionFX.h"
#include "RedPlayerCharacter.h"
#include "RedBolt.h"
#include "RedPlanetPresentationController.h"
#include "RedPlanetPresentationTuning.h"
#include "RedPlanetTerrainQuery.h"
#include "RedGravityBodies.h"
#include "Camera/CameraComponent.h"
#include "RedShipCollisionDriver.h"
#include "RedSpaceDust.h"
#include "RedSpaceScenery.h"
#include "Components/AudioComponent.h"
#include "Components/BoxComponent.h"
#include "Components/InputComponent.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Curves/CurveFloat.h"
#include "Engine/CollisionProfile.h"
#include "Engine/Engine.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshSocket.h"
#include "Engine/World.h"
#include "GameFramework/Controller.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "Components/SceneComponent.h"
#include "Materials/MaterialInterface.h"
#include "Math/RotationMatrix.h"
#include "UObject/ConstructorHelpers.h"
#include "EngineUtils.h"
#include "Kismet/GameplayStatics.h"
#include "Sound/SoundBase.h"
#include "Sound/SoundAttenuation.h"
#include "Net/UnrealNetwork.h"
#include "NiagaraFunctionLibrary.h"
#include "NiagaraSystem.h"

namespace RedShipPrivate
{
	static bool IsEnginePlaceholderCube(const UStaticMesh* Mesh)
	{
		return Mesh && Mesh->GetPathName().Equals(
			TEXT("/Engine/BasicShapes/Cube.Cube"), ESearchCase::IgnoreCase);
	}

	// The aggregate body box is useful as a conservative ship-vs-world envelope, but it must
	// never become a second invisible art mesh.  Pawns and weapon queries use the fitted deck and
	// the purchased mesh's own convex collision instead.
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

	// Character floor tests need one predictable, thin surface.  It deliberately ignores weapon
	// and visibility channels so the helper cannot produce rectangular ricochets or grapple hits.
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

	static void ConfigureDetailedVisualCollision(UStaticMeshComponent* Mesh)
	{
		if (!Mesh || !Mesh->GetStaticMesh()) { return; }
		Mesh->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
		Mesh->SetCollisionObjectType(ECC_Vehicle);
		Mesh->SetCollisionResponseToAllChannels(ECR_Ignore);
		Mesh->SetCollisionResponseToChannel(ECC_Visibility, ECR_Block);
		Mesh->SetCollisionResponseToChannel(ECC_WorldDynamic, ECR_Block);
		Mesh->SetCollisionResponseToChannel(ECC_PhysicsBody, ECR_Block);
		Mesh->SetGenerateOverlapEvents(false);
		Mesh->SetCanEverAffectNavigation(false);
		Mesh->CanCharacterStepUpOn = ECB_No;
	}
}

ARedShip::ARedShip()
{
	PrimaryActorTick.bCanEverTick = true;
	bReplicates = true;
	SetReplicateMovement(true);
	// Parked player craft are not ambient AI pawns. APawn defaults placed actors to
	// PlacedInWorld AI auto-possession, which gave BP_RedModularStarSparrow an AIController
	// and made the boarding chooser treat it as occupied forever.
	AutoPossessAI = EAutoPossessAI::Disabled;
	AutoPossessPlayer = EAutoReceiveInput::Disabled;

	// Ship rotation is driven by the movement component, never the controller.
	bUseControllerRotationPitch = false;
	bUseControllerRotationYaw = false;
	bUseControllerRotationRoll = false;

	// Kinematic collision root (swept by the movement component, never physics-simulated).
	CollisionSphere = CreateDefaultSubobject<USphereComponent>(TEXT("CollisionSphere"));
	CollisionSphere->InitSphereRadius(260.0f);
	CollisionSphere->SetCollisionProfileName(UCollisionProfile::BlockAll_ProfileName);
	CollisionSphere->SetCollisionObjectType(ECC_Vehicle);   // bolts block Vehicle (they ignore WorldDynamic)
	CollisionSphere->SetSimulatePhysics(false);
	// Never push the third-person camera probe around: standing near the parked ship had the
	// spring arm fighting this invisible sphere — camera snapping in/out ("flashing").
	CollisionSphere->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
	CollisionSphere->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore);
	CollisionSphere->SetCollisionResponseToChannel(ECC_WorldDynamic, ECR_Ignore);
	CollisionSphere->SetCollisionResponseToChannel(ECC_Visibility, ECR_Ignore);
	RootComponent = CollisionSphere;

	// Art mesh (visual only) — yawed so SM_ship's +Y nose points along the pawn's +X. Roll bank lives here.
	Hull = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Hull"));
	Hull->SetupAttachment(CollisionSphere);
	// Query-only per-triangle collision (SM_ship uses complex-as-simple): rifle bolts explode on
	// the wings/nose instead of passing through, and pawns bump against the hull. The movement
	// component still sweeps ONLY the root sphere, so flight physics are unchanged.
	Hull->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	Hull->SetCollisionObjectType(ECC_Vehicle);
	Hull->SetCollisionResponseToAllChannels(ECR_Block);
	Hull->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
		// Keep the art visually parked near the surface while the collision root sits close
		// enough that landing no longer feels blocked by an invisible high shell.
		Hull->SetRelativeLocation(FVector(0.f, 0.f, -240.f));
	Hull->SetRelativeRotation(FRotator(0.f, MeshYaw, 0.f));
	// Do not ship an Engine cube as fallback art.  BP_RedModularStarSparrow supplies its own
	// component stack, and the old inherited cube was the small black box seen below the fighter.
	Hull->SetStaticMesh(nullptr);
	RuntimeHullCollision = CreateDefaultSubobject<UBoxComponent>(TEXT("RuntimeHullCollision"));
	RuntimeHullCollision->SetupAttachment(CollisionSphere);
	RuntimeHullCollision->SetBoxExtent(FVector(1100.f, 900.f, 300.f));
	RuntimeHullCollision->SetRelativeLocation(FVector(0.f, 0.f, 40.f));
	RedShipPrivate::ConfigureHullEnvelopeCollisionBox(RuntimeHullCollision);
	RuntimeDeckCollision = CreateDefaultSubobject<UBoxComponent>(TEXT("RuntimeDeckCollision"));
	RuntimeDeckCollision->SetupAttachment(CollisionSphere);
	RuntimeDeckCollision->SetBoxExtent(FVector(650.f, 500.f, 20.f));
	RuntimeDeckCollision->SetRelativeLocation(FVector(0.f, 0.f, 360.f));
	RedShipPrivate::ConfigureWalkableDeckCollisionBox(RuntimeDeckCollision);

	CameraBoom = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraBoom"));
	CameraBoom->SetupAttachment(CollisionSphere);
	CameraBoom->TargetArmLength = ChaseArmLength;
	CameraBoom->SocketOffset = ChaseCameraOffset;
	CameraBoom->bUsePawnControlRotation = false;
	CameraBoom->bDoCollisionTest = true;  // chase default; cockpit mode disables probing
	CameraBoom->ProbeSize = 24.f;
	CameraBoom->ProbeChannel = ECC_Camera;
	CameraBoom->bEnableCameraLag = true;
	CameraBoom->bEnableCameraRotationLag = true;
	CameraBoom->CameraLagSpeed = 10.0f;
	CameraBoom->CameraRotationLagSpeed = 8.0f;
	CameraBoom->bUseCameraLagSubstepping = true;
	CameraBoom->CameraLagMaxTimeStep = 1.0f / 60.0f;
	CameraBoom->CameraLagMaxDistance = 600.0f; // tighter than 1200 so steer doesn't feel floaty/laggy

	ShipCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("ShipCamera"));
	ShipCamera->SetupAttachment(CameraBoom, USpringArmComponent::SocketName);
	ShipCamera->bUsePawnControlRotation = false;
	ShipCamera->SetFieldOfView(BaseFOV);

	// Planet-aware 6DOF movement (UpdatedComponent auto-binds to the root).
	ShipMovement = CreateDefaultSubobject<URedShipMovementComponent>(TEXT("ShipMovement"));
	ShipMovement->PlanetCenter = FVector::ZeroVector;
	ShipMovement->PlanetRadius = 382000.0f;       // Match the generated planet shell; do not float on a separate gameplay sphere.
	ShipMovement->AtmosphereTopAltitude =
		RedPlanetPresentationTuning::SpaceTransitionAltitudeCm;
	ShipMovement->FallbackMaxSpeed = FighterCruiseSpeed;

	// Streams the voxel planet around the ship via an ASYNC, velocity-led invoker + a speed
	// governor (so we never outrun the cook). This is what makes the Vibe ship fly smooth —
	// it replaces the old root-attached inline invoker that hitched the game thread every tick.
	CollisionDriver = CreateDefaultSubobject<URedShipCollisionDriver>(TEXT("CollisionDriver"));

	// Engine plumes prefer RedMMO's local bright cone material/mesh. The Paragon
	// thruster asset is a useful fallback, but it reads too faintly at ship-camera
	// distance on Mac/Metal.
	static ConstructorHelpers::FObjectFinder<UStaticMesh> ThrusterMesh(
		TEXT("/Engine/BasicShapes/Cone.Cone"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> ConeMesh(TEXT("/Engine/BasicShapes/Cone.Cone"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> ThrusterMat(
		TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> FallbackFlameMat(
		TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	if (FallbackFlameMat.Succeeded())
	{
		PlumeMaterial = FallbackFlameMat.Object;
	}
	else if (ThrusterMat.Succeeded())
	{
		PlumeMaterial = ThrusterMat.Object;
	}
		auto MakeHardpoint = [&](const TCHAR* Name) -> USceneComponent*
		{
			USceneComponent* Hardpoint = CreateDefaultSubobject<USceneComponent>(Name);
			Hardpoint->SetupAttachment(Hull);
			PlumeHardpoints.Add(Hardpoint);
			return Hardpoint;
		};
		USceneComponent* PlumeOuterL = MakeHardpoint(TEXT("HP_PlumeOuterL"));
		USceneComponent* PlumeOuterR = MakeHardpoint(TEXT("HP_PlumeOuterR"));
		USceneComponent* PlumeInnerL = MakeHardpoint(TEXT("HP_PlumeInnerL"));
		USceneComponent* PlumeInnerR = MakeHardpoint(TEXT("HP_PlumeInnerR"));
		TurretMuzzleLeft = CreateDefaultSubobject<USceneComponent>(TEXT("HP_TurretMuzzleLeft"));
		TurretMuzzleLeft->SetupAttachment(Hull);
		TurretMuzzleRight = CreateDefaultSubobject<USceneComponent>(TEXT("HP_TurretMuzzleRight"));
		TurretMuzzleRight->SetupAttachment(Hull);

		// Plumes attach to explicit engine hardpoints so the visual flame and engine pod
		// cannot drift apart when the hull banks or the ship art gets reoriented.
		auto MakePlume = [&](const TCHAR* Name, USceneComponent* Parent) -> UStaticMeshComponent*
		{
			UStaticMeshComponent* P = CreateDefaultSubobject<UStaticMeshComponent>(Name);
			P->SetupAttachment(Parent ? Parent : Hull);
			P->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			P->SetCastShadow(false);
			if (ConeMesh.Succeeded()) { P->SetStaticMesh(ConeMesh.Object); }
			else if (ThrusterMesh.Succeeded()) { P->SetStaticMesh(ThrusterMesh.Object); }
			if (PlumeMaterial) { P->SetMaterial(0, PlumeMaterial); }
			P->SetRelativeLocation(FVector::ZeroVector);
			// SM_Thruster_Cone: pivot at the cone BASE, axis +X, 60cm long, radius 50 —
			// length lives on X, radial size on Y/Z (the old MakeFromZ + Z-length scale
			// pointed the geometry sideways: plumes read as floating dots).
			P->SetRelativeRotation(FRotationMatrix::MakeFromX(-FVector::YAxisVector).Rotator());
			P->SetRelativeScale3D(FVector(2.0f, 1.1f, 1.1f));
		// Keep plumes hidden until the ship is actually piloted. Detached preview cones were
		// reading like broken FX around the parked ship.
		P->SetHiddenInGame(true);
		P->SetVisibility(false, true);
		Plumes.Add(P);
		return P;
	};
		MakePlume(TEXT("PlumeOuterL"), PlumeOuterL);
		MakePlume(TEXT("PlumeOuterR"), PlumeOuterR);
		MakePlume(TEXT("PlumeInnerL"), PlumeInnerL);
		MakePlume(TEXT("PlumeInnerR"), PlumeInnerR);
		ApplyHardpointLayout();
		ApplyPlumeLayout(true);

	ProjectileClass = ARedBolt::StaticClass();

	// Ship cannon audio: sci-fi shot (pitched down at fire for a heavier report) + distance falloff.
	// Retired ship weapon audio remains optional and unset.

	// Velocity-sensation dust: world-anchored streaks that flow past when flying fast.
	SpaceDust = CreateDefaultSubobject<URedSpaceDust>(TEXT("SpaceDust"));
	SpaceDust->SetupAttachment(CollisionSphere);

	// Engine sound = synthesized seamless loops (S_ShipEngine*): a deep sub rumble that always
	// plays, plus a selectable character layer. `EngineStyle 0/1/2` in the console swaps the
	// character loop live while piloting.
	EngineAudio = CreateDefaultSubobject<UAudioComponent>(TEXT("EngineAudio"));
	EngineAudio->SetupAttachment(Hull);
	EngineAudio->bAutoActivate = false;
	// Retired synthesized engine loops remain optional and unset.

	EngineWhineAudio = CreateDefaultSubobject<UAudioComponent>(TEXT("EngineWhineAudio"));
	EngineWhineAudio->SetupAttachment(Hull);
	EngineWhineAudio->bAutoActivate = false;
	if (EngineWhineStyles.Num() > 0) { EngineWhineAudio->SetSound(EngineWhineStyles[0]); }
}

void ARedShip::EngineStyle(int32 StyleIndex)
{
	if (!EngineWhineAudio || EngineWhineStyles.Num() == 0) { return; }
	CurrentEngineStyle = FMath::Clamp(StyleIndex, 0, EngineWhineStyles.Num() - 1);
	const bool bWasPlaying = EngineWhineAudio->IsPlaying();
	EngineWhineAudio->SetSound(EngineWhineStyles[CurrentEngineStyle]);
	if (bWasPlaying) { EngineWhineAudio->Play(); }
	if (GEngine)
	{
		GEngine->AddOnScreenDebugMessage(-1, 3.f, FColor::Cyan,
			FString::Printf(TEXT("Engine style %d/%d"), CurrentEngineStyle, EngineWhineStyles.Num() - 1));
	}
}

void ARedShip::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	if (Hull)
	{
		// Existing Blueprint instances can retain the native component's former default even after
		// the C++ CDO changes.  Strip that exact Engine helper while preserving any real hull a child
		// Blueprint deliberately assigns.
		if (RedShipPrivate::IsEnginePlaceholderCube(Hull->GetStaticMesh()))
		{
			Hull->SetStaticMesh(nullptr);
			Hull->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		}
		Hull->SetRelativeLocation(FVector(0.f, 0.f, -240.f));
	}
	if (ShipMovement && ShipMovement->MinimumSurfaceClearance > 300.0f)
	{
		ShipMovement->MinimumSurfaceClearance = 300.0f;
	}
	if (ShipMovement && !ShipMovement->AltitudeSpeedCurve)
	{
		ShipMovement->FallbackMaxSpeed = FMath::Clamp(FighterCruiseSpeed, 1000.f, 30000.f);
	}
	ApplyPlumeLayout(true);
}

void ARedShip::BeginPlay()
{
	Super::BeginPlay();
	SetActorEnableCollision(true);
	SetCanBeDamaged(true);
	if (ShipMovement && !ShipMovement->AltitudeSpeedCurve)
	{
		// BP_RedModularStarSparrow serialized the old 750 m/s component default.
		// Apply the ship-level tuning property so existing assets inherit the controllable cap.
		ShipMovement->FallbackMaxSpeed = FMath::Clamp(FighterCruiseSpeed, 1000.f, 30000.f);
	}
	bRuntimeCollisionHullsConfigured = TryConfigureRuntimeCollisionHulls();
	if (HasAuthority())
	{
		MaxHealth = FMath::Max(1.f, MaxHealth);
		Health = MaxHealth;
		WeaponHeat = 0.f;
		bWeaponOverheated = false;
		ForceNetUpdate();
	}
	for (TActorIterator<ARedPlanetPresentationController> It(GetWorld()); It; ++It)
	{
		ARedPlanetPresentationController* PlanetController = *It;
		if (!IsValid(PlanetController))
		{
			continue;
		}
		PlanetController->RefreshPresentationActors();
		if (ShipMovement)
		{
			ShipMovement->PlanetCenter = PlanetController->PlanetCenter;
			ShipMovement->PlanetRadius = PlanetController->GetGameplaySurfaceRadius();
			ShipMovement->MinimumSurfaceClearance = FMath::Min(ShipMovement->MinimumSurfaceClearance, 300.0f);
		}
		const FVector FromCenter = GetActorLocation() - PlanetController->PlanetCenter;
		const FVector RadialUp = FromCenter.IsNearlyZero() ? FVector::UpVector : FromCenter.GetSafeNormal();
		const float MinShipRadius = PlanetController->GetGameplaySurfaceRadius()
			+ (ShipMovement ? ShipMovement->MinimumSurfaceClearance : 300.0f);
		if (HasAuthority()
			&& ShipMovement
			&& bRuntimeCollisionHullsConfigured
			&& FVector::Dist(GetActorLocation(), PlanetController->PlanetCenter) < MinShipRadius)
		{
			const FVector BeginPlayRecoveryLocation =
				PlanetController->PlanetCenter + RadialUp * MinShipRadius;
			const bool bBeginPlayRecoveryCommitted =
				ShipMovement->TryCommitClearPlacement(
					BeginPlayRecoveryLocation,
					GetActorQuat(),
					true,
					ETeleportType::TeleportPhysics);
			if (bBeginPlayRecoveryCommitted)
			{
				ForceNetUpdate();
			}
			else
			{
				UE_LOG(LogRedShip, Warning,
					TEXT("%s: BeginPlay surface recovery rejected by bounded placement preflight"),
					*GetNameSafe(this));
			}
		}
		break;
	}
	if (HasAuthority())
	{
		ARedSpaceScenery::EnsureForWorld(GetWorld(),
			ShipMovement ? ShipMovement->PlanetCenter : FVector::ZeroVector);
	}
	ApplyPlumeLayout(false);
}

void ARedShip::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (!bRuntimeCollisionHullsConfigured)
	{
		bRuntimeCollisionHullsConfigured = TryConfigureRuntimeCollisionHulls();
	}
	if (IsLocallyControlled() && !HasAuthority())
	{
		ServerSetFlightInput(LocalMoveAxes, LocalRotationAxes, bBoostHeld);
	}
	if (HasAuthority() && Controller && !Controller->IsLocalController())
	{
		ApplyRemoteAuthoritativeFlight(DeltaSeconds);
	}
	if (GetLocalRole() != ROLE_SimulatedProxy)
	{
		ApplyLandingAssist(DeltaSeconds);
	}
	if (Pilot)
	{
		Pilot->SetHUDSpaceMinimap(true);
	}
	UpdateVisuals(DeltaSeconds);
	UpdateWeaponHeat(DeltaSeconds);

	if (FireCooldown > 0.f) { FireCooldown -= DeltaSeconds; }
	if (bFiring && FireCooldown <= 0.f) { Fire(); FireCooldown = FireInterval; }
}

UPawnMovementComponent* ARedShip::GetMovementComponent() const
{
	return ShipMovement;
}

FVector ARedShip::GetVelocity() const
{
	if (HasAuthority() && Controller && !Controller->IsLocalController())
	{
		return RemoteFlightVelocity;
	}
	return Super::GetVelocity();
}

void ARedShip::SetupPlayerInputComponent(UInputComponent* InInput)
{
	Super::SetupPlayerInputComponent(InInput);
	// W/S thrust, A/D strafe, Space/LeftCtrl lift, mouse pitch/yaw, E/Q roll, Shift boost.
	InInput->BindAxis(TEXT("MoveForward"), this, &ARedShip::ThrustInput);
	InInput->BindAxis(TEXT("MoveRight"), this, &ARedShip::StrafeInput);
	InInput->BindAxis(TEXT("ShipLift"), this, &ARedShip::LiftInput);
	InInput->BindAxis(TEXT("LookUp"), this, &ARedShip::PitchInput);
	InInput->BindAxis(TEXT("Turn"), this, &ARedShip::YawInput);
	InInput->BindAxis(TEXT("ShipRoll"), this, &ARedShip::RollInput);
	// Mouse wheel must change cruise speed, never spring-arm zoom. Bind both axis names so
	// an imported CameraZoom mapping cannot pull the chase camera out of frame.
	InInput->BindAxis(TEXT("ShipThrottle"), this, &ARedShip::ThrottleWheelInput);
	InInput->BindAxis(TEXT("CameraZoom"), this, &ARedShip::ThrottleWheelInput);
	InInput->BindAction(TEXT("Sprint"), IE_Pressed, this, &ARedShip::StartBoost);
	InInput->BindAction(TEXT("Sprint"), IE_Released, this, &ARedShip::StopBoost);
	InInput->BindAction(TEXT("Fire"), IE_Pressed, this, &ARedShip::StartFire);
	InInput->BindAction(TEXT("Fire"), IE_Released, this, &ARedShip::StopFire);
	InInput->BindAction(TEXT("EnterVehicle"), IE_Pressed, this, &ARedShip::ExitShip);
	InInput->BindAction(TEXT("ToggleShipCamera"), IE_Pressed, this, &ARedShip::ToggleShipCamera);
	InInput->BindAction(TEXT("ToggleLandingAssist"), IE_Pressed, this, &ARedShip::ToggleLandingAssist);
}

// --- input (fire every frame via legacy axes; push straight to the movement component) ---
void ARedShip::ThrustInput(float V)
{
	LocalMoveAxes.X = FMath::Clamp(V, -1.f, 1.f);
	if (bLandingAssistEnabled && bLandingSettled)
	{
		// W is the primary flight gesture. A parked craft must not remain input-locked just because
		// the pilot does not know that positive lift is a second way to release landing assist.
		if (V > 0.35f) { SetLandingAssistEnabled(false); }
		else { return; }
	}
	if (ShipMovement)
	{
		ShipMovement->AddMoveInput(FVector(V, 0.f, 0.f));
		ShipMovement->SetBoostInput(bBoostHeld); // pushed every frame (held boost)
	}
}
void ARedShip::StrafeInput(float V)
{
	LocalMoveAxes.Y = FMath::Clamp(V, -1.f, 1.f);
	if (bLandingAssistEnabled && bLandingSettled) { return; }
	if (ShipMovement) ShipMovement->AddMoveInput(FVector(0.f, V, 0.f));
}
void ARedShip::LiftInput(float V)
{
	LocalMoveAxes.Z = FMath::Clamp(V, -1.f, 1.f);
	if (bLandingAssistEnabled && bLandingSettled)
	{
		if (V > 0.35f) { SetLandingAssistEnabled(false); }
		else { return; }
	}
	if (ShipMovement) ShipMovement->AddMoveInput(FVector(0.f, 0.f, V));
}
// Negate: the shared "LookUp" axis is -MouseY, but the Vibe scheme wants mouse-up = nose-up (raw +MouseY).
void ARedShip::PitchInput(float V)
{
	const bool bAllowed = IsLookAllowed();
	LocalRotationAxes.X = bAllowed ? FMath::Clamp(-V, -1.f, 1.f) : 0.f;
	if (bLandingAssistEnabled && bLandingSettled) { return; }
	if (ShipMovement && bAllowed) ShipMovement->AddRotationInput(FVector(-V, 0.f, 0.f));
}
void ARedShip::YawInput(float V)
{
	const bool bAllowed = IsLookAllowed();
	LocalRotationAxes.Y = bAllowed ? FMath::Clamp(V, -1.f, 1.f) : 0.f;
	if (bLandingAssistEnabled && bLandingSettled) { return; }
	if (ShipMovement && bAllowed) ShipMovement->AddRotationInput(FVector(0.f, V, 0.f));
}
void ARedShip::RollInput(float V)
{
	LocalRotationAxes.Z = FMath::Clamp(V, -1.f, 1.f);
	if (bLandingAssistEnabled && bLandingSettled) { return; }
	if (ShipMovement) ShipMovement->AddRotationInput(FVector(0.f, 0.f, V));
}
void ARedShip::StartBoost() { bBoostHeld = true; }
void ARedShip::StopBoost() { bBoostHeld = false; }

void ARedShip::ThrottleWheelInput(float V)
{
	if (FMath::IsNearlyZero(V) || !ShipMovement)
	{
		return;
	}
	FighterCruiseSpeed = FMath::Clamp(
		FighterCruiseSpeed + V * ThrottleWheelStep,
		MinCruiseSpeed,
		MaxCruiseSpeed);
	ShipMovement->FallbackMaxSpeed = FighterCruiseSpeed;
	// Keep the chase/cockpit arm on the authored lengths — never treat wheel as zoom.
	if (CameraBoom)
	{
		CameraBoom->TargetArmLength = bFirstPersonCamera ? FirstPersonArmLength : ChaseArmLength;
	}
}

void ARedShip::ToggleLandingAssist()
{
	SetLandingAssistEnabled(!bLandingAssistEnabled);
}

void ARedShip::SetLandingAssistEnabled(const bool bEnabled)
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
}

void ARedShip::ServerSetLandingAssistEnabled_Implementation(const bool bEnabled)
{
	if (!Controller || !Controller->IsPlayerController())
	{
		return;
	}
	SetLandingAssistEnabled(bEnabled);
}

bool ARedShip::IsLookAllowed() const
{
	if (!bRequireRightMouseForLook) { return true; }
	const APlayerController* PC = Cast<APlayerController>(GetController());
	return PC && PC->IsInputKeyDown(EKeys::RightMouseButton);
}

void ARedShip::ServerSetFlightInput_Implementation(FVector MoveAxes, FVector RotationAxes, bool bBoost)
{
	if (!Controller || !Controller->IsPlayerController())
	{
		return;
	}
	if (MoveAxes.ContainsNaN() || RotationAxes.ContainsNaN())
	{
		return;
	}
	if (bLandingAssistEnabled && bLandingSettled
		&& (MoveAxes.X > 0.35f || MoveAxes.Z > 0.35f))
	{
		SetLandingAssistEnabled(false);
	}
	ServerMoveAxes = FVector(
		FMath::Clamp(MoveAxes.X, -1.f, 1.f),
		FMath::Clamp(MoveAxes.Y, -1.f, 1.f),
		FMath::Clamp(MoveAxes.Z, -1.f, 1.f));
	ServerRotationAxes = FVector(
		FMath::Clamp(RotationAxes.X, -1.f, 1.f),
		FMath::Clamp(RotationAxes.Y, -1.f, 1.f),
		FMath::Clamp(RotationAxes.Z, -1.f, 1.f));
	bServerBoostHeld = bBoost;
	LastServerFlightInputTime = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
}

void ARedShip::ApplyRemoteAuthoritativeFlight(float DeltaSeconds)
{
	if (!ShipMovement || !CollisionSphere || !GetWorld() || DeltaSeconds <= 0.f)
	{
		return;
	}
	if (bLandingAssistEnabled && bLandingSettled)
	{
		RemoteFlightVelocity = FVector::ZeroVector;
		ShipMovement->Velocity = FVector::ZeroVector;
		return;
	}
	if (GetWorld()->GetTimeSeconds() - LastServerFlightInputTime > 0.30)
	{
		ServerMoveAxes = FVector::ZeroVector;
		ServerRotationAxes = FVector::ZeroVector;
		bServerBoostHeld = false;
	}

	const FVector RotationInput(
		FMath::Clamp(ServerRotationAxes.X, -1.f, 1.f),
		FMath::Clamp(ServerRotationAxes.Y, -1.f, 1.f),
		FMath::Clamp(ServerRotationAxes.Z, -1.f, 1.f));
	const float PitchRad = FMath::DegreesToRadians(ShipMovement->PitchRateDeg) * RotationInput.X * DeltaSeconds;
	const float YawRad = FMath::DegreesToRadians(ShipMovement->YawRateDeg) * RotationInput.Y * DeltaSeconds;
	const float RollRad = FMath::DegreesToRadians(ShipMovement->RollRateDeg) * RotationInput.Z * DeltaSeconds;
	const FQuat DeltaQuat =
		FQuat(FVector::XAxisVector, -RollRad) *
		FQuat(FVector::YAxisVector, -PitchRad) *
		FQuat(FVector::ZAxisVector, YawRad);
	FQuat NewRotation = GetActorQuat() * DeltaQuat;
	NewRotation.Normalize();

	const float Altitude = ShipMovement->GetAltitudeAGL();
	float MaxSpeed = FMath::Max(100.f, ShipMovement->FallbackMaxSpeed);
	if (ShipMovement->AltitudeSpeedCurve)
	{
		const float AltitudeKm = FMath::Max(0.f, Altitude) / 100000.f;
		MaxSpeed = FMath::Max(100.f,
			ShipMovement->AltitudeSpeedCurve->GetFloatValue(AltitudeKm) * 100.f);
	}
	if (bServerBoostHeld)
	{
		MaxSpeed *= FMath::Max(1.f, ShipMovement->BoostSpeedMultiplier);
	}
	const bool bInAtmosphere = ShipMovement->PlanetRadius > 0.f
		&& Altitude < ShipMovement->AtmosphereTopAltitude;
	if (!bInAtmosphere)
	{
		MaxSpeed *= FMath::Max(1.f, ShipMovement->SpaceSpeedMultiplier);
	}
	MaxSpeed = FMath::Min(MaxSpeed, FMath::Max(100.f, ShipMovement->AbsoluteMaxSpeed));
	if (CollisionDriver)
	{
		const float GovernorCap = CollisionDriver->QuerySpeedCap();
		if (GovernorCap > 0.f) { MaxSpeed = FMath::Min(MaxSpeed, GovernorCap); }
	}
	const float Responsiveness = bInAtmosphere
		? ShipMovement->ResponsivenessAtmosphere
		: ShipMovement->ResponsivenessSpace * FMath::Max(1.f, ShipMovement->SpaceAccelerationMultiplier);
	const FVector DesiredVelocity = NewRotation.RotateVector(ServerMoveAxes.GetClampedToMaxSize(1.f)) * MaxSpeed;
	RemoteFlightVelocity = FMath::VInterpTo(RemoteFlightVelocity, DesiredVelocity,
		DeltaSeconds, FMath::Max(0.f, Responsiveness)).GetClampedToMaxSize(MaxSpeed);

	const FVector Delta = RemoteFlightVelocity * DeltaSeconds;
	ShipMovement->Velocity = RemoteFlightVelocity;
	ShipMovement->MoveWithPlanetCollision(Delta, NewRotation, DeltaSeconds);
	RemoteFlightVelocity = ShipMovement->Velocity;
}

bool ARedShip::QueryLandingSurface(
	FHitResult& OutHit,
	FVector& OutRadialUp,
	bool* bOutMatchingPlanetTerrain) const
{
	OutHit = FHitResult();
	OutRadialUp = FVector::UpVector;
	if (bOutMatchingPlanetTerrain)
	{
		*bOutMatchingPlanetTerrain = false;
	}
	if (!GetWorld() || !ShipMovement || ShipMovement->PlanetRadius <= 0.f)
	{
		return false;
	}
	const FVector FromCenter = GetActorLocation() - ShipMovement->PlanetCenter;
	OutRadialUp = FromCenter.GetSafeNormal();
	if (OutRadialUp.IsNearlyZero())
	{
		return false;
	}

	const FVector Start = GetActorLocation() + OutRadialUp * 50000.f;
	const FVector End = GetActorLocation()
		- OutRadialUp * FMath::Max(500.f, LandingAssistTraceDistance);
	const ERedPlanetTerrainQueryResult TerrainResult = RedPlanetTerrainQuery::LineTrace(
		GetWorld(), ShipMovement->PlanetCenter, Start, End, OutHit);
	if (TerrainResult != ERedPlanetTerrainQueryResult::NoMatchingPlanet)
	{
		if (bOutMatchingPlanetTerrain)
		{
			*bOutMatchingPlanetTerrain = true;
		}
		return TerrainResult == ERedPlanetTerrainQueryResult::Hit && OutHit.bBlockingHit;
	}

	// Legacy/static bodies retain their original collision path. A matching PlanetGen body never
	// falls through to presentation shells or arbitrary geometry masquerading as terrain.
	FCollisionObjectQueryParams ObjectParams;
	ObjectParams.AddObjectTypesToQuery(ECC_WorldStatic);
	FCollisionQueryParams Params(SCENE_QUERY_STAT(RedShipLandingAssist), true, this);
	return GetWorld()->LineTraceSingleByObjectType(OutHit, Start, End, ObjectParams, Params)
		&& OutHit.bBlockingHit;
}

void ARedShip::LogGravityAcceptanceSnapshot(
	FString Phase, const bool bRequireShipUpAlignment)
{
	Phase.TrimStartAndEndInline();
	if (Phase.IsEmpty())
	{
		Phase = TEXT("manual");
	}
	for (int32 Index = 0; Index < Phase.Len(); ++Index)
	{
		const TCHAR Character = Phase[Index];
		const bool bSafeCharacter = FChar::IsAlnum(Character)
			|| Character == TEXT('_') || Character == TEXT('-') || Character == TEXT('.');
		if (!bSafeCharacter)
		{
			Phase[Index] = TEXT('_');
		}
	}
	Phase = Phase.Left(64);

	UWorld* World = GetWorld();
	if (!World || !ShipMovement)
	{
		UE_LOG(LogRedShip, Warning,
			TEXT("RED_SHIP_GRAVITY_ACCEPTANCE phase=\"%s\" result=FAIL reason=%s localRole=%d netMode=%d authority=%d alignmentRequired=%d landingAssist=%d settled=%d"),
			*Phase, World ? TEXT("missing_movement") : TEXT("missing_world"),
			static_cast<int32>(GetLocalRole()), static_cast<int32>(GetNetMode()),
			HasAuthority() ? 1 : 0, bRequireShipUpAlignment ? 1 : 0,
			bLandingAssistEnabled ? 1 : 0,
			bLandingSettled ? 1 : 0);
		return;
	}

	const FVector Location = GetActorLocation();
	const FName CachedBodyId = ShipMovement->GetCurrentGravityBodyId();
	RedGravity::FBodyQueryResult QueriedBody;
	const bool bQueryFound = RedGravity::QueryDominantBodyDetailed(
		World, Location, CachedBodyId,
		ShipMovement->GravityBodySwitchHysteresis, QueriedBody);

	const bool bCachedFrameValid = !CachedBodyId.IsNone()
		&& !ShipMovement->PlanetCenter.ContainsNaN()
		&& FMath::IsFinite(ShipMovement->PlanetRadius)
		&& ShipMovement->PlanetRadius > 0.f;
	const bool bQueriedFrameValid = bQueryFound && !QueriedBody.StableId.IsNone()
		&& !QueriedBody.Center.ContainsNaN()
		&& FMath::IsFinite(QueriedBody.SurfaceRadius)
		&& QueriedBody.SurfaceRadius > 0.f;
	const bool bBodyIdMatch = bCachedFrameValid && bQueriedFrameValid
		&& CachedBodyId == QueriedBody.StableId;

	const FVector CachedRadialUp = bCachedFrameValid
		? (Location - ShipMovement->PlanetCenter).GetSafeNormal()
		: FVector::ZeroVector;
	const FVector QueriedRadialUp = bQueriedFrameValid
		? (Location - QueriedBody.Center).GetSafeNormal()
		: FVector::ZeroVector;
	const float CenterDeltaCm = bCachedFrameValid && bQueriedFrameValid
		? FVector::Distance(ShipMovement->PlanetCenter, QueriedBody.Center) : -1.f;
	const float RadiusDeltaCm = bCachedFrameValid && bQueriedFrameValid
		? FMath::Abs(ShipMovement->PlanetRadius - QueriedBody.SurfaceRadius) : -1.f;
	const float RadialUpDot = !CachedRadialUp.IsNearlyZero() && !QueriedRadialUp.IsNearlyZero()
		? FVector::DotProduct(CachedRadialUp, QueriedRadialUp) : -2.f;
	const float ShipUpDot = !QueriedRadialUp.IsNearlyZero()
		? FVector::DotProduct(GetActorUpVector().GetSafeNormal(), QueriedRadialUp) : -2.f;

	const bool bCenterMatch = CenterDeltaCm >= 0.f && CenterDeltaCm <= 1.f;
	const bool bRadiusMatch = RadiusDeltaCm >= 0.f && RadiusDeltaCm <= 1.f;
	const bool bRadialUpMatch = RadialUpDot >= 0.9999f;
	const bool bFramePass = bBodyIdMatch && bCenterMatch && bRadiusMatch && bRadialUpMatch;
	const bool bShipUpMatch = ShipUpDot >= 0.95f;
	const bool bAlignmentPass = !bRequireShipUpAlignment || bShipUpMatch;
	const bool bAcceptancePass = bFramePass && bAlignmentPass;
	const TCHAR* Reason = TEXT("ok");
	if (!bQueryFound)
	{
		Reason = TEXT("no_dominant_body");
	}
	else if (!bCachedFrameValid)
	{
		Reason = TEXT("invalid_cached_frame");
	}
	else if (!bQueriedFrameValid)
	{
		Reason = TEXT("invalid_queried_frame");
	}
	else if (!bBodyIdMatch)
	{
		Reason = TEXT("body_id_mismatch");
	}
	else if (!bCenterMatch)
	{
		Reason = TEXT("center_mismatch");
	}
	else if (!bRadiusMatch)
	{
		Reason = TEXT("radius_mismatch");
	}
	else if (!bRadialUpMatch)
	{
		Reason = TEXT("radial_up_mismatch");
	}
	else if (!bAlignmentPass)
	{
		Reason = TEXT("ship_up_mismatch");
	}

	const FString CachedCenter = ShipMovement->PlanetCenter.ToCompactString();
	const FString QueriedCenter = QueriedBody.Center.ToCompactString();
	const FString CachedBodyName = CachedBodyId.ToString();
	const FString QueriedBodyName = QueriedBody.StableId.ToString();
	const FString Snapshot = FString::Printf(
		TEXT("RED_SHIP_GRAVITY_ACCEPTANCE phase=\"%s\" result=%s reason=%s localRole=%d netMode=%d authority=%d cachedBody=%s queriedBody=%s cachedCenter=\"%s\" queriedCenter=\"%s\" cachedRadiusCm=%.3f queriedRadiusCm=%.3f centerDeltaCm=%.3f radiusDeltaCm=%.3f radialUpDot=%.6f shipUpDot=%.6f framePass=%d alignmentRequired=%d alignmentPass=%d landingAssist=%d settled=%d"),
		*Phase, bAcceptancePass ? TEXT("PASS") : TEXT("FAIL"), Reason,
		static_cast<int32>(GetLocalRole()), static_cast<int32>(GetNetMode()),
		HasAuthority() ? 1 : 0, *CachedBodyName, *QueriedBodyName,
		*CachedCenter, *QueriedCenter, ShipMovement->PlanetRadius,
		QueriedBody.SurfaceRadius, CenterDeltaCm, RadiusDeltaCm, RadialUpDot,
		ShipUpDot, bFramePass ? 1 : 0, bRequireShipUpAlignment ? 1 : 0,
		bAlignmentPass ? 1 : 0, bLandingAssistEnabled ? 1 : 0,
		bLandingSettled ? 1 : 0);
	if (bAcceptancePass)
	{
		UE_LOG(LogRedShip, Display, TEXT("%s"), *Snapshot);
	}
	else
	{
		UE_LOG(LogRedShip, Warning, TEXT("%s"), *Snapshot);
	}
}

float ARedShip::GetLandingSupportDistance(
	const FVector& SurfaceNormal,
	const FQuat& TargetRootRotation) const
{
	const FVector Normal = SurfaceNormal.GetSafeNormal();
	if (Normal.IsNearlyZero())
	{
		return FMath::Max(20.f, ShipMovement ? ShipMovement->MinimumSurfaceClearance : 300.f);
	}

	const UBoxComponent* FittedEnvelope = ShipMovement
		? ShipMovement->GetTranslationCollisionEnvelope()
		: nullptr;
	if (FittedEnvelope
		&& FittedEnvelope->GetAttachParent() == CollisionSphere
		&& !TargetRootRotation.ContainsNaN()
		&& TargetRootRotation.IsNormalized())
	{
		const FTransform CurrentRootTransform = GetActorTransform();
		const FVector EnvelopeCenterLocal =
			CurrentRootTransform.InverseTransformPosition(
				FittedEnvelope->GetComponentLocation());
		const FQuat EnvelopeRelativeRotation = (
			GetActorQuat().Inverse()
				* FittedEnvelope->GetComponentQuat()).GetNormalized();
		const FTransform TargetRootTransform(
			TargetRootRotation,
			GetActorLocation(),
			CurrentRootTransform.GetScale3D());
		const FVector TargetEnvelopeCenter =
			TargetRootTransform.TransformPosition(EnvelopeCenterLocal);
		const FQuat TargetEnvelopeRotation = (
			TargetRootRotation * EnvelopeRelativeRotation).GetNormalized();
		const FVector Extent = FittedEnvelope->GetScaledBoxExtent();
		const float OrientedSupport =
			FMath::Abs(FVector::DotProduct(TargetEnvelopeRotation.GetAxisX(), Normal)) * Extent.X
			+ FMath::Abs(FVector::DotProduct(TargetEnvelopeRotation.GetAxisY(), Normal)) * Extent.Y
			+ FMath::Abs(FVector::DotProduct(TargetEnvelopeRotation.GetAxisZ(), Normal)) * Extent.Z;
		const float RootToLowestPoint = OrientedSupport
			- FVector::DotProduct(
				TargetEnvelopeCenter - GetActorLocation(), Normal);
		return FMath::Max(20.f, RootToLowestPoint)
			+ FMath::Max(0.f, LandingAssistSurfaceGap);
	}

	const UPrimitiveComponent* BoundsComponent = RuntimeHullCollision
		? Cast<UPrimitiveComponent>(RuntimeHullCollision)
		: Cast<UPrimitiveComponent>(CollisionSphere);
	if (!BoundsComponent)
	{
		return FMath::Max(20.f, ShipMovement ? ShipMovement->MinimumSurfaceClearance : 300.f);
	}
	const FBoxSphereBounds Bounds = BoundsComponent->Bounds;
	const float Support = FVector::DotProduct(Bounds.BoxExtent, Normal.GetAbs());
	const float LowestProjection = FVector::DotProduct(Bounds.Origin, Normal) - Support;
	return FMath::Max(20.f,
		FVector::DotProduct(GetActorLocation(), Normal) - LowestProjection)
		+ FMath::Max(0.f, LandingAssistSurfaceGap);
}

FVector ARedShip::GetLandingFlightVelocity() const
{
	if (HasAuthority() && Controller && !Controller->IsLocalController())
	{
		return RemoteFlightVelocity;
	}
	return ShipMovement ? ShipMovement->Velocity : FVector::ZeroVector;
}

void ARedShip::SetLandingFlightVelocity(const FVector& NewVelocity)
{
	if (ShipMovement)
	{
		ShipMovement->Velocity = NewVelocity;
		ShipMovement->UpdateComponentVelocity();
	}
	if (HasAuthority() && Controller && !Controller->IsLocalController())
	{
		RemoteFlightVelocity = NewVelocity;
	}
}

void ARedShip::SetLandingSettled(const bool bSettled)
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

void ARedShip::ApplyLandingAssist(const float DeltaSeconds)
{
	if (!bLandingAssistEnabled || DeltaSeconds <= 0.f || !ShipMovement)
	{
		return;
	}
	const FVector MoveInput = HasAuthority() && Controller && !Controller->IsLocalController()
		? ServerMoveAxes : LocalMoveAxes;
	if (MoveInput.Z > 0.35f)
	{
		// Deliberate lift is an intuitive takeoff gesture and returns the craft to full combat flight.
		SetLandingAssistEnabled(false);
		return;
	}

	FHitResult SurfaceHit;
	FVector RadialUp;
	bool bMatchingPlanetTerrain = false;
	if (!QueryLandingSurface(
		SurfaceHit, RadialUp, &bMatchingPlanetTerrain))
	{
		SetLandingSettled(false);
		return;
	}
	// A triangle normal can point inward on the moon or roll sharply across low-poly terrain.
	// Landing gear is gravity-aligned: the traced point supplies height, dominant-body radial up
	// supplies the stable orientation. This guarantees the craft cannot settle upside down.
	const FVector SurfaceNormal = RadialUp;
	const auto StopInwardLandingVelocity = [this, &SurfaceNormal]()
	{
		const FVector CurrentVelocity = GetLandingFlightVelocity();
		const float InwardSpeed = FVector::DotProduct(CurrentVelocity, SurfaceNormal);
		if (InwardSpeed < 0.f)
		{
			SetLandingFlightVelocity(CurrentVelocity - SurfaceNormal * InwardSpeed);
		}
	};

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
	const FQuat NewRotation = (bLandingSettled
		? DesiredRotation
		: FMath::QInterpTo(GetActorQuat(), DesiredRotation, DeltaSeconds,
			FMath::Max(0.1f, LandingAssistAlignSpeed))).GetNormalized();
	if (!ShipMovement->TryCommitClearPlacement(
		GetActorLocation(),
		NewRotation,
		bMatchingPlanetTerrain,
		ETeleportType::TeleportPhysics))
	{
		StopInwardLandingVelocity();
		SetLandingSettled(false);
		return;
	}

	const float CurrentSupportDistance = GetLandingSupportDistance(
		SurfaceNormal, NewRotation);
	const float Clearance = FVector::DotProduct(
		GetActorLocation() - SurfaceHit.ImpactPoint, SurfaceNormal) - CurrentSupportDistance;
	const float TouchdownSupportDistance = GetLandingSupportDistance(
		SurfaceNormal, DesiredRotation);
	const FVector TouchdownLocation = SurfaceHit.ImpactPoint
		+ SurfaceNormal * TouchdownSupportDistance;
	if (bLandingSettled)
	{
		if (ShipMovement->TryCommitClearPlacement(
			TouchdownLocation,
			DesiredRotation,
			bMatchingPlanetTerrain,
			ETeleportType::TeleportPhysics))
		{
			SetLandingFlightVelocity(FVector::ZeroVector);
		}
		else
		{
			StopInwardLandingVelocity();
			SetLandingSettled(false);
		}
		return;
	}

	FVector Velocity = GetLandingFlightVelocity();
	const float NormalSpeed = FVector::DotProduct(Velocity, SurfaceNormal);
	FVector TangentialVelocity = FVector::VectorPlaneProject(Velocity, SurfaceNormal);
	const float NearAlpha = FMath::Clamp(
		1.f - FMath::Max(0.f, Clearance) / FMath::Max(500.f, LandingAssistTraceDistance), 0.f, 1.f);
	TangentialVelocity = FMath::VInterpTo(TangentialVelocity, FVector::ZeroVector,
		DeltaSeconds, FMath::Lerp(0.5f, FMath::Max(0.f, LandingAssistLateralDamping), NearAlpha));
	const float DesiredDownSpeed = -FMath::Clamp(FMath::Max(0.f, Clearance) * 0.55f,
		55.f, FMath::Max(100.f, LandingAssistMaxDescentSpeed));
	const float NewNormalSpeed = FMath::FInterpTo(NormalSpeed, DesiredDownSpeed,
		DeltaSeconds, 2.5f);
	const FVector AssistedVelocity = TangentialVelocity + SurfaceNormal * NewNormalSpeed;
	if (!Controller)
	{
		const FVector AssistedLocation = GetActorLocation() + AssistedVelocity * DeltaSeconds;
		if (!ShipMovement->TryCommitClearPlacement(
			AssistedLocation,
			GetActorQuat(),
			bMatchingPlanetTerrain,
			ETeleportType::TeleportPhysics))
		{
			StopInwardLandingVelocity();
			return;
		}
	}
	SetLandingFlightVelocity(AssistedVelocity);

	if (Clearance <= FMath::Max(5.f, LandingAssistTouchdownDistance)
		&& (Clearance <= 0.f || FMath::Abs(NewNormalSpeed) <= 180.f))
	{
		if (ShipMovement->TryCommitClearPlacement(
			TouchdownLocation,
			DesiredRotation,
			bMatchingPlanetTerrain,
			ETeleportType::TeleportPhysics))
		{
			SetLandingFlightVelocity(FVector::ZeroVector);
			if (HasAuthority())
			{
				SetLandingSettled(true);
			}
		}
		else
		{
			StopInwardLandingVelocity();
			SetLandingSettled(false);
		}
	}
}

void ARedShip::StartFire() { bFiring = true; }
void ARedShip::StopFire() { bFiring = false; }

void ARedShip::Fire()
{
	if (HasAuthority())
	{
		TryFireAuthoritative();
	}
	else
	{
		// A client requests a shot, never a transform. The authority owns muzzle selection,
		// aim validation, cadence and heat.
		ServerFire();
	}
}

bool ARedShip::ComputeServerFireTransform(bool bUseLeftMuzzle, FVector& OutStart, FRotator& OutDirection) const
{
	if (!HasAuthority())
	{
		return false;
	}

	const USceneComponent* Muzzle = bUseLeftMuzzle ? TurretMuzzleLeft.Get() : TurretMuzzleRight.Get();
	const FTransform HullTransform = Hull ? Hull->GetComponentTransform() : GetActorTransform();
	const FVector VisualForward = Hull
		? HullTransform.TransformVectorNoScale(MeshForwardAxis.GetSafeNormal()).GetSafeNormal()
		: GetActorForwardVector().GetSafeNormal();
	const FVector VisualUp = Hull
		? HullTransform.TransformVectorNoScale(FVector::ZAxisVector).GetSafeNormal()
		: GetActorUpVector().GetSafeNormal();

	OutStart = (Muzzle && Muzzle->GetOwner() == this && Muzzle->IsRegistered()) ? Muzzle->GetComponentLocation()
		: (GetActorLocation() + VisualForward * 1150.f + VisualUp * -430.f);

	// The camera is a server-owned component following the authoritative hull. Converge each
	// barrel on its center ray without accepting a client-provided position or direction.
	FVector AimDirection = VisualForward;
	if (ShipCamera)
	{
		const FVector AimPoint = ShipCamera->GetComponentLocation()
			+ ShipCamera->GetForwardVector().GetSafeNormal() * 200000.f;
		const FVector CameraAim = (AimPoint - OutStart).GetSafeNormal();
		if (!CameraAim.IsNearlyZero() && !CameraAim.ContainsNaN()
			&& FVector::DotProduct(CameraAim, VisualForward) >= FMath::Clamp(MinFireAimDot, 0.f, 1.f))
		{
			AimDirection = CameraAim;
		}
	}
	OutDirection = AimDirection.Rotation();
	return !OutStart.ContainsNaN() && !AimDirection.IsNearlyZero();
}

bool ARedShip::TryFireAuthoritative()
{
	if (!HasAuthority() || Health <= 0.f || !ProjectileClass || !GetWorld() || bWeaponOverheated
		|| !ProjectileClass->IsChildOf(ARedBolt::StaticClass()))
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

	if (!SpawnBolt(Start, Direction))
	{
		return false;
	}
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

void ARedShip::ServerFire_Implementation()
{
	TryFireAuthoritative();
}

bool ARedShip::SpawnBolt(FVector Start, FRotator Dir)
{
	if (!HasAuthority() || !ProjectileClass || !GetWorld()) return false;
	FActorSpawnParameters Params;
	Params.Owner = this;
	Params.Instigator = this;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AActor* Spawned = GetWorld()->SpawnActor<AActor>(ProjectileClass, Start, Dir, Params);
	ARedBolt* Bolt = Cast<ARedBolt>(Spawned);
	if (!Bolt)
	{
		if (Spawned) { Spawned->Destroy(); }
		return false;
	}
	if (Bolt)
	{
		Bolt->ConfigureImpactProfile(16.f, 2.5f, 600.f, 55.f); // BIG readable ship bolt, modest blast, sane damage
		// The profile formula caps at 1.5m x 9.6cm — sub-pixel from the 52m chase camera. Cannon-scale beam:
		Bolt->SetBeamDimensions(7.f, 0.45f);
		Bolt->ConfigureGroundImpact(false, false, false);     // no giant voxel crater / black-blob stamp
		Bolt->SetImpactExplosion(true);                        // Metal-safe Cascade explosion on hit
		// muzzle speed rides ABOVE the ship's own speed so you can never outrun your shots,
		// while staying a slow visible tracer when parked. Fired along the aim (no lateral
		// inheritance — that arced shots away from the crosshair like fake gravity).
		const float MuzzleSpeed = 12000.f + (float)GetVelocity().Size() * 1.15f;
		Bolt->LaunchWithVelocity(Dir.Vector() * MuzzleSpeed);
	}
	// Ship cannon report. The chase camera sits ~60m behind the muzzles — ATT_Shot's falloff
	// silenced the spatialized shot for the PILOT ("no sound for projectiles"). Play a flat 2D
	// report for the local pilot + the spatialized one for everyone else in the world.
	return true;
}

void ARedShip::MulticastFireCosmetics_Implementation(FVector_NetQuantize MuzzleLocation,
	FVector_NetQuantizeNormal ShotDirection)
{
	if (GetNetMode() == NM_DedicatedServer)
	{
		return;
	}
	const FVector Direction = FVector(ShotDirection).GetSafeNormal();
	if (ShipMuzzleFlashFX && !Direction.IsNearlyZero())
	{
		UNiagaraFunctionLibrary::SpawnSystemAtLocation(this, ShipMuzzleFlashFX,
			MuzzleLocation, Direction.Rotation(), FVector::OneVector, true, true,
			ENCPoolMethod::AutoRelease, true);
	}
	if (ShipFireSound)
	{
		UGameplayStatics::PlaySoundAtLocation(this, ShipFireSound, MuzzleLocation,
			2.0f, 0.72f, 0.f, ShipFireAttenuation);
		const APlayerController* PilotPC = Cast<APlayerController>(GetController());
		if (PilotPC && PilotPC->IsLocalController())
		{
			UGameplayStatics::PlaySound2D(this, ShipFireSound, 0.9f, 0.72f);
		}
	}
}

void ARedShip::UpdateWeaponHeat(float DeltaSeconds)
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

float ARedShip::TakeDamage(float DamageAmount, const FDamageEvent& DamageEvent,
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

void ARedShip::OnRep_Health()
{
	if (Health <= 0.f)
	{
		HandleDeath();
	}
}

void ARedShip::HandleDeath(AController* DamageInstigator, AActor* DamageCauser)
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

	// Capture the occupant before possession changes clear Pilot. The server restores possession,
	// attachment, visibility and collision first so the replicated corpse belongs to the player pawn
	// rather than remaining hidden inside a disabled vehicle, then kills it through the normal player
	// damage/downed/respawn path. Empty ships retain their existing destruction behaviour.
	if (HasAuthority() && Pilot)
	{
		ARedPlayerCharacter* FatalPilot = Pilot;
		ExitShipAuthority(/*bEmergencyEject=*/true);
		if (IsValid(FatalPilot))
		{
			FatalPilot->ApplyVehicleDestructionDeath(DamageInstigator,
				IsValid(DamageCauser) ? DamageCauser : this);
		}
	}
	bFiring = false;
	bBoostHeld = false;
	RemoteFlightVelocity = FVector::ZeroVector;
	SetActorEnableCollision(false);
	if (ShipMovement) { ShipMovement->StopMovementImmediately(); ShipMovement->Deactivate(); }
	if (CollisionDriver) { CollisionDriver->Deactivate(); }
	if (EngineAudio) { EngineAudio->Stop(); }
	if (EngineWhineAudio) { EngineWhineAudio->Stop(); }
	for (UStaticMeshComponent* Plume : Plumes)
	{
		if (Plume) { Plume->SetVisibility(false, true); Plume->SetHiddenInGame(true); }
	}
	SetActorHiddenInGame(true);
	SetActorTickEnabled(false);
}

float ARedShip::GetHealthFraction() const
{
	return FMath::Clamp(Health / FMath::Max(1.f, MaxHealth), 0.f, 1.f);
}

float ARedShip::GetWeaponHeatFraction() const
{
	return FMath::Clamp(WeaponHeat / FMath::Max(1.f, MaxWeaponHeat), 0.f, 1.f);
}

void ARedShip::TestFire()
{
	Fire();
}

void ARedShip::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(ARedShip, MaxHealth);
	DOREPLIFETIME(ARedShip, Health);
	DOREPLIFETIME(ARedShip, WeaponHeat);
	DOREPLIFETIME(ARedShip, bWeaponOverheated);
	DOREPLIFETIME(ARedShip, bLandingAssistEnabled);
	DOREPLIFETIME(ARedShip, bLandingSettled);
	DOREPLIFETIME(ARedShip, Pilot);
}

void ARedShip::ToggleShipCamera()
{
	bFirstPersonCamera = !bFirstPersonCamera;
}

void ARedShip::UpdateVisuals(float DeltaSeconds)
{
	if (!ShipMovement) return;

	// FOV boost kick.
	if (ShipCamera)
	{
		const float TargetFOV = ShipMovement->IsBoosting() ? BoostFOV : BaseFOV;
		ShipCamera->SetFieldOfView(FMath::FInterpTo(ShipCamera->FieldOfView, TargetFOV, DeltaSeconds, FOVInterpSpeed));
	}
	if (CameraBoom)
	{
		const float TargetArmLength = bFirstPersonCamera ? FirstPersonArmLength : ChaseArmLength;
		const FVector TargetOffset = bFirstPersonCamera ? FirstPersonCameraOffset : ChaseCameraOffset;
		// Hard-set the framed chase/cockpit length so no leftover CameraZoom path can
		// walk TargetArmLength out past the ship silhouette.
		CameraBoom->TargetArmLength = FMath::FInterpTo(CameraBoom->TargetArmLength, TargetArmLength, DeltaSeconds, 7.0f);
		if (!bFirstPersonCamera
			&& FMath::Abs(CameraBoom->TargetArmLength - ChaseArmLength) > ChaseArmLength * 0.35f)
		{
			CameraBoom->TargetArmLength = ChaseArmLength;
		}
		CameraBoom->SocketOffset = FMath::VInterpTo(CameraBoom->SocketOffset, TargetOffset, DeltaSeconds, 7.0f);
		CameraBoom->bDoCollisionTest = !bFirstPersonCamera;
	}

	// Visual bank on the hull from yaw + strafe (absolute set, never accumulated, never control rotation).
	if (Hull)
	{
		const FVector RotIn = ShipMovement->GetLastRotationInput();
		const FVector MovIn = ShipMovement->GetLastMoveInput();
		const float BankInput = FMath::Clamp(RotIn.Y + 0.5f * MovIn.Y, -1.f, 1.f);
		const float TargetBank = -BankInput * MaxVisualBankAngle;
		CurrentVisualBank = FMath::FInterpTo(CurrentVisualBank, TargetBank, DeltaSeconds, VisualBankInterpSpeed);
		Hull->SetRelativeRotation(FRotator(0.f, MeshYaw, CurrentVisualBank));
	}

	// Runtime-detected modular nozzles use one flame per real mouth. The four-cone legacy layout
	// remains only for the monolithic fallback hull that has no discoverable engine components.
	const bool bPiloted = IsValid(Pilot) && Cast<APlayerController>(GetController()) != nullptr;
	const float Thr = bPiloted ? FMath::Clamp(ShipMovement->GetLastMoveInput().X, 0.f, 1.f) : 0.0f;
	const bool bBoostPlume = bPiloted && ShipMovement->IsBoosting();
	// Idle = dark. Any forward thrust or boost restores engine blooms/plumes.
	const bool bShowPlumes = bPiloted && (Thr > 0.02f || bBoostPlume);
	// Two-layer engine mix: constant deep rumble underneath, character loop (hum/turbine/thrum)
	// on top. Rumble barely pitches (subs sound wrong shifted); the character layer carries the
	// throttle response. Both flat (non-spatialized) — the pilot's own engines, not a world sound.
	const bool bBoost = ShipMovement && ShipMovement->IsBoosting();
	if (EngineAudio)
	{
		if (bPiloted)
		{
			EngineAudio->bAllowSpatialization = false;
			if (!EngineAudio->IsPlaying()) { EngineAudio->Play(); }
			EngineAudio->SetVolumeMultiplier(0.10f + Thr * 0.16f);
			EngineAudio->SetPitchMultiplier(0.88f + Thr * 0.10f);
		}
		else if (EngineAudio->IsPlaying())
		{
			EngineAudio->Stop();
		}
	}
	if (EngineWhineAudio)
	{
		if (bPiloted)
		{
			EngineWhineAudio->bAllowSpatialization = false;
			if (!EngineWhineAudio->IsPlaying()) { EngineWhineAudio->Play(); }
			EngineWhineAudio->SetVolumeMultiplier(0.03f + Thr * 0.14f + (bBoost ? 0.04f : 0.f));
			EngineWhineAudio->SetPitchMultiplier(0.80f + Thr * 0.16f + (bBoost ? 0.04f : 0.f));
		}
		else if (EngineWhineAudio->IsPlaying())
		{
			EngineWhineAudio->Stop();
		}
	}
	const float Len = 2.0f + Thr * (ShipMovement->IsBoosting() ? 9.0f : 5.5f);   // 1.2m idle -> 4.5m run -> 6.6m boost (cone is 60cm)
	const float Wid = 1.1f + Thr * 0.5f;                                          // base radius 50 -> 55..80cm, matches the bells
	for (int32 Index = 0; Index < Plumes.Num(); ++Index)
	{
		UStaticMeshComponent* P = Plumes[Index];
		if (!P) continue;
		const bool bUsesRealNozzle = DetectedNozzleCount <= 0 || Index < DetectedNozzleCount;
		const bool bShowThisPlume = bShowPlumes && bUsesRealNozzle;
		P->SetHiddenInGame(!bShowThisPlume);
		P->SetVisibility(bShowThisPlume, true);
		if (!bShowThisPlume)
		{
			P->SetRelativeScale3D(FVector(2.0f, 1.1f, 1.1f));
			continue;
		}
		P->SetRelativeScale3D(FVector(Len, Wid, Wid));
	}
}

bool ARedShip::TryConfigureRuntimeCollisionHulls()
{
	if (ShipMovement)
	{
		ShipMovement->SetTranslationCollisionEnvelope(nullptr);
	}

	const bool bReady = ConfigureRuntimeCollisionHulls();
	if (ShipMovement)
	{
		ShipMovement->SetTranslationCollisionEnvelope(
			bReady ? RuntimeHullCollision : nullptr);
	}
	return bReady;
}

bool ARedShip::ConfigureRuntimeCollisionHulls()
{
	if (!RuntimeHullCollision || !RuntimeDeckCollision || !CollisionSphere)
	{
		return false;
	}

	if (Hull && RedShipPrivate::IsEnginePlaceholderCube(Hull->GetStaticMesh()))
	{
		Hull->SetStaticMesh(nullptr);
		Hull->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	}
	// Child Blueprint component serialization may retain the old BlockAll responses.  Reassert the
	// movement root's narrow responsibility at runtime so its 260 cm sphere cannot suspend a Pawn
	// above the visible fighter or absorb a shot before the detailed mesh does.
	CollisionSphere->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
	CollisionSphere->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore);
	CollisionSphere->SetCollisionResponseToChannel(ECC_WorldDynamic, ECR_Ignore);
	CollisionSphere->SetCollisionResponseToChannel(ECC_Visibility, ECR_Ignore);

	FBox LocalBounds(ForceInit);
	FBox DeckReferenceBounds(ForceInit);
	const FTransform RootTransform = CollisionSphere->GetComponentTransform();
	TArray<UStaticMeshComponent*> MeshComponents;
	GetComponents<UStaticMeshComponent>(MeshComponents);
	for (UStaticMeshComponent* Mesh : MeshComponents)
	{
		if (!Mesh || !Mesh->IsRegistered() || !Mesh->GetStaticMesh()
			|| Plumes.Contains(const_cast<UStaticMeshComponent*>(Mesh))
			|| Mesh->GetName().Contains(TEXT("Plume"))
			|| RedShipPrivate::IsEnginePlaceholderCube(Mesh->GetStaticMesh()))
		{
			continue;
		}

		RedShipPrivate::ConfigureDetailedVisualCollision(Mesh);

		// Transform the asset box itself instead of inverse-transforming the component's world AABB.
		// The latter preserves the AABB's world-axis expansion and made radial/tilted ships report a
		// much taller local hull than their visible mesh.
		const FBox AssetBounds = Mesh->GetStaticMesh()->GetBoundingBox();
		if (!AssetBounds.IsValid) { continue; }
		const FTransform MeshTransform = Mesh->GetComponentTransform();
		FBox MeshRootBounds(ForceInit);
		for (int32 CornerIndex = 0; CornerIndex < 8; ++CornerIndex)
		{
			const FVector AssetCorner(
				(CornerIndex & 1) ? AssetBounds.Max.X : AssetBounds.Min.X,
				(CornerIndex & 2) ? AssetBounds.Max.Y : AssetBounds.Min.Y,
				(CornerIndex & 4) ? AssetBounds.Max.Z : AssetBounds.Min.Z);
			MeshRootBounds += RootTransform.InverseTransformPosition(
				MeshTransform.TransformPosition(AssetCorner));
		}
		LocalBounds += MeshRootBounds;

		const FString AssetName = Mesh->GetStaticMesh()->GetName();
		const bool bCentralDeckReference = Mesh == Hull
			|| AssetName.Contains(TEXT("Core"), ESearchCase::IgnoreCase)
			|| AssetName.Contains(TEXT("Body"), ESearchCase::IgnoreCase)
			|| AssetName.Contains(TEXT("Hull"), ESearchCase::IgnoreCase)
			|| AssetName.Contains(TEXT("Cockpit"), ESearchCase::IgnoreCase);
		if (bCentralDeckReference)
		{
			DeckReferenceBounds += MeshRootBounds;
		}
	}

	if (!LocalBounds.IsValid || LocalBounds.GetSize().GetMax() < 100.f)
	{
		return false;
	}

	const FVector RawExtent = LocalBounds.GetExtent();
	const FVector BodyExtent(
		FMath::Clamp(RawExtent.X, 250.f, 8000.f),
		FMath::Clamp(RawExtent.Y, 150.f, 5000.f),
		FMath::Clamp(RawExtent.Z, 80.f, 2500.f));
	const FVector BodyCenter = LocalBounds.GetCenter();
	RuntimeHullCollision->SetRelativeLocation(BodyCenter);
	RuntimeHullCollision->SetRelativeRotation(FRotator::ZeroRotator);
	RuntimeHullCollision->SetBoxExtent(BodyExtent, false);

	// Tall fins and wing tips are not a walkable roof.  Use the central core/body/cockpit layers
	// when present, falling back to the complete visible mesh only for single-mesh craft.
	const FBox& WalkableBounds = DeckReferenceBounds.IsValid ? DeckReferenceBounds : LocalBounds;
	const FVector WalkableCenter = WalkableBounds.GetCenter();
	const FVector WalkableExtent = WalkableBounds.GetExtent();
	const float DeckHalfHeight = 10.f;
	const float DeckSurfaceZ = WalkableBounds.Max.Z - 4.f;
	RuntimeDeckCollision->SetRelativeLocation(FVector(
		WalkableCenter.X, WalkableCenter.Y, DeckSurfaceZ - DeckHalfHeight));
	RuntimeDeckCollision->SetRelativeRotation(FRotator::ZeroRotator);
	RuntimeDeckCollision->SetBoxExtent(FVector(
		FMath::Clamp(WalkableExtent.X * 0.82f, 100.f, BodyExtent.X * 0.72f),
		FMath::Clamp(WalkableExtent.Y * 0.72f, 70.f, BodyExtent.Y * 0.66f),
		DeckHalfHeight), false);

	RedShipPrivate::ConfigureHullEnvelopeCollisionBox(RuntimeHullCollision);
	RedShipPrivate::ConfigureWalkableDeckCollisionBox(RuntimeDeckCollision);
	UE_LOG(LogRedShip, Display,
		TEXT("Runtime modular collision fitted on %s: body center=%s extent=%s walkable deckZ=%.1f"),
		*GetName(), *BodyCenter.ToCompactString(), *BodyExtent.ToCompactString(),
		DeckSurfaceZ);
	return true;
}

bool ARedShip::BindPlumeHardpointsToDetectedNozzles()
{
	// The saved modular Sparrow is assembled from named Engine/Thruster mesh layers. Bind the
	// visible flame bases to those live components so Blueprint layout changes cannot leave the
	// exhaust floating at an old hand-measured hull coordinate.
	if (!Hull || GetClass()->GetName().Contains(TEXT("MiniFighter")))
	{
		return false;
	}

	struct FNozzleCandidate
	{
		UStaticMeshComponent* Component = nullptr;
		FVector WorldLocation = FVector::ZeroVector;
	};
	TArray<FNozzleCandidate> Candidates;
	const FVector ShipForward = GetActorForwardVector().GetSafeNormal();
	const FVector ShipRight = GetActorRightVector().GetSafeNormal();
	if (ShipForward.IsNearlyZero() || ShipRight.IsNearlyZero())
	{
		return false;
	}

	auto AddCandidate = [&Candidates](UStaticMeshComponent* Component, const FVector& Location)
	{
		if (!Component || Location.ContainsNaN())
		{
			return;
		}
		for (const FNozzleCandidate& Existing : Candidates)
		{
			if (FVector::DistSquared(Existing.WorldLocation, Location) < FMath::Square(25.f))
			{
				return;
			}
		}
		FNozzleCandidate Candidate;
		Candidate.Component = Component;
		Candidate.WorldLocation = Location;
		Candidates.Add(Candidate);
	};

	auto GatherCandidates = [&](const bool bThrusterPass)
	{
		TArray<UStaticMeshComponent*> MeshComponents;
		GetComponents<UStaticMeshComponent>(MeshComponents);
		for (UStaticMeshComponent* MeshComponent : MeshComponents)
		{
			if (!MeshComponent || !MeshComponent->GetStaticMesh()
				|| MeshComponent == Hull || Plumes.Contains(MeshComponent))
			{
				continue;
			}
			FString Identity = MeshComponent->GetName() + TEXT(" ")
				+ MeshComponent->GetStaticMesh()->GetName();
			Identity.ToLowerInline();
			const bool bThruster = Identity.Contains(TEXT("thruster"));
			const bool bEngine = Identity.Contains(TEXT("engine"));
			if ((bThrusterPass && !bThruster) || (!bThrusterPass && (!bEngine || bThruster)))
			{
				continue;
			}

			bool bFoundSocket = false;
			for (const TObjectPtr<UStaticMeshSocket>& SocketPtr : MeshComponent->GetStaticMesh()->Sockets)
			{
				const UStaticMeshSocket* Socket = SocketPtr.Get();
				if (!Socket)
				{
					continue;
				}
				FString SocketName = Socket->SocketName.ToString();
				SocketName.ToLowerInline();
				if (!SocketName.Contains(TEXT("nozzle")) && !SocketName.Contains(TEXT("exhaust"))
					&& !SocketName.Contains(TEXT("thruster")))
				{
					continue;
				}
				AddCandidate(MeshComponent,
					MeshComponent->GetSocketTransform(Socket->SocketName, RTS_World).GetLocation());
				bFoundSocket = true;
			}
			if (bFoundSocket)
			{
				continue;
			}

			const FBoxSphereBounds Bounds = MeshComponent->Bounds;
			const float AftSupport = FVector::DotProduct(Bounds.BoxExtent, ShipForward.GetAbs());
			const float SideSupport = FVector::DotProduct(Bounds.BoxExtent, ShipRight.GetAbs());
			const FVector AftCenter = Bounds.Origin - ShipForward * AftSupport;
			// A single StarSparrow Thruster layer contains the symmetric left/right mouths.
			// Split at half its lateral support; separately placed modules naturally de-duplicate.
			if (SideSupport >= 50.f)
			{
				const float HalfSpacing = SideSupport * 0.5f;
				AddCandidate(MeshComponent, AftCenter - ShipRight * HalfSpacing);
				AddCandidate(MeshComponent, AftCenter + ShipRight * HalfSpacing);
			}
			else
			{
				AddCandidate(MeshComponent, AftCenter);
			}
		}
	};

	GatherCandidates(/*bThrusterPass=*/true);
	if (Candidates.Num() < 2)
	{
		GatherCandidates(/*bThrusterPass=*/false);
	}
	if (Candidates.Num() < 2 || PlumeHardpoints.Num() < 2)
	{
		return false;
	}
	Candidates.Sort([&ShipRight](const FNozzleCandidate& A, const FNozzleCandidate& B)
	{
		return FVector::DotProduct(A.WorldLocation, ShipRight)
			< FVector::DotProduct(B.WorldLocation, ShipRight);
	});
	const FNozzleCandidate Nozzles[] = {Candidates[0], Candidates.Last()};
	for (int32 Index = 0; Index < 2; ++Index)
	{
		USceneComponent* Hardpoint = PlumeHardpoints[Index].Get();
		if (!Hardpoint || !Nozzles[Index].Component)
		{
			return false;
		}
		Hardpoint->AttachToComponent(Nozzles[Index].Component,
			FAttachmentTransformRules::KeepWorldTransform);
		Hardpoint->SetWorldLocation(Nozzles[Index].WorldLocation);
		Hardpoint->SetWorldRotation(Hull->GetComponentQuat());
		Hardpoint->SetAbsolute(false, false, true);
		Hardpoint->SetWorldScale3D(FVector::OneVector);
	}
	DetectedNozzleCount = 2;
	if (!bLoggedDetectedNozzles)
	{
		bLoggedDetectedNozzles = true;
		UE_LOG(LogRedShip, Display, TEXT("Detected modular nozzle anchors on %s: L=%s R=%s"),
			*GetNameSafe(this), *Nozzles[0].WorldLocation.ToCompactString(),
			*Nozzles[1].WorldLocation.ToCompactString());
	}
	return true;
}

void ARedShip::ApplyHardpointLayout()
{
	// MEASURED from SM_ship LOD0 vertices (rear rim slab Y<-940): TWIN engine bells centered at
	// x=+/-45, z~505, rim depth to Y~-988 — the old offsets (+/-790 / +/-335) floated in empty
	// space off the wings ("big gap between the engine and the plume"). Main pair sits in the
	// bell mouths; the trailing pair rides 50cm behind them for layered glow depth.
	static const FVector PlumeOffsets[] =
	{
		FVector(-45.f, -985.f, 505.f),
		FVector( 45.f, -985.f, 505.f),
		FVector(-45.f, -1035.f, 505.f),
		FVector( 45.f, -1035.f, 505.f),
	};

	if (!BindPlumeHardpointsToDetectedNozzles())
	{
		DetectedNozzleCount = 0;
		for (int32 Index = 0; Index < PlumeHardpoints.Num(); ++Index)
		{
			USceneComponent* Hardpoint = PlumeHardpoints[Index].Get();
			if (!Hardpoint)
			{
				continue;
			}
			if (Hardpoint->GetAttachParent() != Hull)
			{
				Hardpoint->AttachToComponent(Hull,
					FAttachmentTransformRules::SnapToTargetNotIncludingScale);
			}
			Hardpoint->SetAbsolute(false, false, false);
			const int32 OffsetIndex = FMath::Min(Index,
				static_cast<int32>(UE_ARRAY_COUNT(PlumeOffsets) - 1));
			Hardpoint->SetRelativeLocation(PlumeOffsets[OffsetIndex]);
			Hardpoint->SetRelativeRotation(FRotator::ZeroRotator);
		}
	}

	// Imported SM_ship native axes: nose/front +Y, rear -Y, up +Z.
	const FRotator NoseForwardRotation = FVector::YAxisVector.Rotation();
	// MEASURED from SM_ship vertices: the wingtip gun pods cluster at (±751, Y 200..800, Z≈652).
	// The old (±65, 1120, -640) was under the nose BELLY — parked, that is INSIDE the terrain, so
	// bolts spawned underground and impact-exploded the same frame ("no weapons, no sound").
	if (TurretMuzzleLeft)
	{
		TurretMuzzleLeft->SetRelativeLocation(FVector(-751.f, 1050.f, 652.f));
		TurretMuzzleLeft->SetRelativeRotation(NoseForwardRotation);
	}
	if (TurretMuzzleRight)
	{
		TurretMuzzleRight->SetRelativeLocation(FVector(751.f, 1050.f, 652.f));
		TurretMuzzleRight->SetRelativeRotation(NoseForwardRotation);
	}
}

void ARedShip::ApplyPlumeLayout(bool bEditorPreview)
{
	ApplyHardpointLayout();

	UMaterialInterface* ResolvedPlumeMaterial = LoadObject<UMaterialInterface>(
		nullptr,
		TEXT("/Game/RedMMO/Materials/M_ShipPlume_Cyan.M_ShipPlume_Cyan"));
	if (!ResolvedPlumeMaterial)
	{
		ResolvedPlumeMaterial = PlumeMaterial;
	}

	for (int32 Index = 0; Index < Plumes.Num(); ++Index)
	{
		UStaticMeshComponent* Plume = Plumes[Index];
		if (!Plume) continue;

		if (PlumeHardpoints.IsValidIndex(Index) && PlumeHardpoints[Index])
		{
			Plume->AttachToComponent(PlumeHardpoints[Index].Get(), FAttachmentTransformRules::KeepRelativeTransform);
		}
		Plume->SetRelativeLocation(FVector::ZeroVector);
		Plume->SetRelativeRotation(FRotationMatrix::MakeFromX(-FVector::YAxisVector).Rotator());
		if (ResolvedPlumeMaterial)
		{
			Plume->SetMaterial(0, ResolvedPlumeMaterial);
		}
		if (bEditorPreview)
		{
			Plume->SetRelativeScale3D(FVector(2.0f, 1.1f, 1.1f));
			Plume->SetHiddenInGame(true);
			Plume->SetVisibility(false, true);
		}
		else
		{
			Plume->SetHiddenInGame(true);
			Plume->SetVisibility(false, true);
		}
	}
}

void ARedShip::EnterShip(ARedPlayerCharacter* InPilot)
{
	// Possession must only be changed by the authority. A client-side proximity interaction
	// needs to route through its owned player pawn/controller before calling this method.
	if (!HasAuthority() || !InPilot || IsValid(Pilot) || Health <= 0.f) return;
	AController* C = InPilot->GetController();
	if (!C) return;
	// A previous surface park intentionally leaves landing assist settled while the craft is empty.
	// Possession starts a new flight session: clear that lock and every input/velocity latch before
	// the new controller can supply its first frame of input.
	SetLandingAssistEnabled(false);
	SetLandingSettled(false);
	bFiring = false;
	bBoostHeld = false;
	LocalMoveAxes = FVector::ZeroVector;
	LocalRotationAxes = FVector::ZeroVector;
	ServerMoveAxes = FVector::ZeroVector;
	ServerRotationAxes = FVector::ZeroVector;
	RemoteFlightVelocity = FVector::ZeroVector;
	bServerBoostHeld = false;
	LastServerFlightInputTime = -100.0;
	if (ShipMovement)
	{
		ShipMovement->ClearFlightInputState();
		ShipMovement->StopMovementImmediately();
	}
	// Some placed modular-fighter Blueprints spawn with an AI/default controller even though
	// they are intended as parked player vehicles. Release that controller explicitly before
	// possession so the player interaction cannot silently fail on this asset.
	if (AController* ExistingController = GetController();
		ExistingController && ExistingController != C)
	{
		if (ExistingController->IsPlayerController())
		{
			return;
		}
		ExistingController->UnPossess();
	}
	Pilot = InPilot;
	ForceNetUpdate();
	Pilot->SetHUDSpaceMinimap(true);
	InPilot->SetActorEnableCollision(false);
	InPilot->SetPilotCaptureOnly(true);   // invisible in the main view, still renders in the HUD portrait capture
	InPilot->OnBoardedShip(this);   // freeze + attach: pilot (and its voxel invoker) rides with the ship
	SetInstigator(InPilot->GetInstigator() ? InPilot->GetInstigator() : InPilot);
	C->Possess(this);
	if (APlayerController* PC = Cast<APlayerController>(C))
	{
		PC->SetInputMode(FInputModeGameOnly());
		PC->bShowMouseCursor = false;
		PC->SetIgnoreMoveInput(false);
		PC->SetIgnoreLookInput(false);
	}
}

void ARedShip::ExitShip()
{
	if (HasAuthority())
	{
		ExitShipAuthority(/*bEmergencyEject=*/false);
	}
	else
	{
		ServerExitShip();
	}
}

void ARedShip::ServerExitShip_Implementation()
{
	ExitShipAuthority(/*bEmergencyEject=*/false);
}

bool ARedShip::IsOrbitalExit() const
{
	if (!ShipMovement)
	{
		return false;
	}
	const float Altitude = ShipMovement->GetAltitudeAGL();
	return FMath::IsFinite(Altitude)
		&& Altitude >= FMath::Max(100000.f, OrbitalExitMinAltitude);
}

void ARedShip::ExitShipAuthority(bool bEmergencyEject)
{
	if (!HasAuthority() || !Pilot) return;
	AController* C = GetController();
	const FVector FromPlanet = GetActorLocation() - (ShipMovement ? ShipMovement->PlanetCenter : FVector::ZeroVector);
	const FVector PlanetUp = FromPlanet.IsNearlyZero() ? GetActorUpVector() : FromPlanet.GetSafeNormal();
	const bool bOrbitalExit = IsOrbitalExit();

	// PARK the ship before placing the pilot. The only collider is a 260cm core sphere under an
	// 875cm-wide hull: left where the sphere stopped, the wings/nose interpenetrated the terrain
	// ("crashes into the surface" at dismount). Trace the ground and set the hull's LOWEST point
	// just above it along the local up; kill any residual velocity so it stays put.
	bool bParkPlacementCommitted = bOrbitalExit || bEmergencyEject;
	if (!bOrbitalExit && !bEmergencyEject)
	{
		if (UWorld* ParkWorld = GetWorld())
		{
			FCollisionQueryParams ParkParams(SCENE_QUERY_STAT(RedShipParkTrace), false);
			ParkParams.AddIgnoredActor(this);
			if (Pilot) { ParkParams.AddIgnoredActor(Pilot); }
			FHitResult ParkHit;
			const FVector RootLoc = GetActorLocation();
			const FVector ParkStart = RootLoc + PlanetUp * 500.f;
			const FVector ParkEnd = RootLoc - PlanetUp * 100000.f;
			const ERedPlanetTerrainQueryResult ParkTerrainResult = RedPlanetTerrainQuery::LineTrace(
				ParkWorld,
				ShipMovement ? ShipMovement->PlanetCenter : FVector::ZeroVector,
				ParkStart,
				ParkEnd,
				ParkHit);
			bool bParkHit = ParkTerrainResult == ERedPlanetTerrainQueryResult::Hit;
			if (ParkTerrainResult == ERedPlanetTerrainQueryResult::NoMatchingPlanet)
			{
				FCollisionObjectQueryParams ParkObj;
				ParkObj.AddObjectTypesToQuery(ECC_WorldStatic);
				bParkHit = ParkWorld->LineTraceSingleByObjectType(
					ParkHit, ParkStart, ParkEnd, ParkObj, ParkParams);
			}
			if (bParkHit && ParkHit.bBlockingHit)
			{
				FVector ParkForward = FVector::VectorPlaneProject(GetActorForwardVector(), PlanetUp).GetSafeNormal();
				if (ParkForward.IsNearlyZero())
				{
					ParkForward = FVector::VectorPlaneProject(GetActorRightVector(), PlanetUp).GetSafeNormal();
				}
				if (ParkForward.IsNearlyZero())
				{
					ParkForward = FVector::VectorPlaneProject(FVector::ForwardVector, PlanetUp).GetSafeNormal();
				}
				if (!ParkForward.IsNearlyZero() && ShipMovement)
				{
					const FQuat ParkRotation = FRotationMatrix::MakeFromXZ(
						ParkForward, PlanetUp).ToQuat();
					const float SupportDistance = GetLandingSupportDistance(
						PlanetUp, ParkRotation);
					const FVector ParkLocation = ParkHit.ImpactPoint
						+ PlanetUp * SupportDistance;
					const bool bRequireMatchingPlanet =
						ParkTerrainResult != ERedPlanetTerrainQueryResult::NoMatchingPlanet;
					bParkPlacementCommitted = ShipMovement->TryCommitClearPlacement(
						ParkLocation,
						ParkRotation,
						bRequireMatchingPlanet,
						ETeleportType::TeleportPhysics);
					if (bParkPlacementCommitted)
					{
						SetLandingAssistEnabled(true);
						SetLandingSettled(true);
					}
				}
			}
		}
	}
	if (!bParkPlacementCommitted)
	{
		UE_LOG(LogRedShip, Warning,
			TEXT("%s: exit rejected because no exact/native-clear fitted parking pose was available"),
			*GetNameSafe(this));
		return;
	}

	// Only release the pilot and zero flight state after parking commits. A rejected normal exit
	// preserves the prior transform, velocity, possession, and input axes; emergency/orbital exits
	// deliberately bypass surface parking and continue through their established escape paths.
	bFiring = false;
	bBoostHeld = false;
	if (ShipMovement)
	{
		ShipMovement->ClearFlightInputState();
		ShipMovement->StopMovementImmediately();
	}
	LocalMoveAxes = FVector::ZeroVector;
	LocalRotationAxes = FVector::ZeroVector;
	ServerMoveAxes = FVector::ZeroVector;
	ServerRotationAxes = FVector::ZeroVector;
	RemoteFlightVelocity = FVector::ZeroVector;
	bServerBoostHeld = false;
	LastServerFlightInputTime = -100.0;
	if (bOrbitalExit || bEmergencyEject)
	{
		SetLandingSettled(false);
	}

	// Exit BEYOND the wingspan, on GROUND THAT EXISTS: probe candidate spots around the ship and
	// take the first with a cooked surface under it — a blind fixed offset sometimes hung the
	// pilot over a dip or an uncooked patch ("standing in the air, bouncing").
	FVector ExitLoc = GetActorLocation() + PlanetUp * 150.f + GetActorRightVector() * 1150.f;
	if (bOrbitalExit)
	{
		FVector BoundsOrigin = GetActorLocation();
		FVector BoundsExtent(900.f, 900.f, 400.f);
		GetActorBounds(true, BoundsOrigin, BoundsExtent, true);
		const float SideSupport = FVector::DotProduct(GetActorRightVector().GetAbs(), BoundsExtent);
		ExitLoc = BoundsOrigin + GetActorRightVector() * (SideSupport + 250.f) + PlanetUp * 150.f;
	}
	else if (UWorld* ExitWorld = GetWorld())
	{
		FCollisionQueryParams ExitParams(SCENE_QUERY_STAT(RedShipExitProbe), false);
		ExitParams.AddIgnoredActor(this);
		if (Pilot) { ExitParams.AddIgnoredActor(Pilot); }
		const FVector Candidates[] =
		{
			GetActorRightVector() * 1150.f,
			GetActorRightVector() * -1150.f,
			GetActorForwardVector() * 1400.f,
			GetActorForwardVector() * -1400.f,
		};
		for (const FVector& Side : Candidates)
		{
			const FVector Base = GetActorLocation() + Side;
			FHitResult ProbeHit;
			const FVector ProbeStart = Base + PlanetUp * 500.f;
			const FVector ProbeEnd = Base - PlanetUp * 3000.f;
			const ERedPlanetTerrainQueryResult ExitTerrainResult = RedPlanetTerrainQuery::LineTrace(
				ExitWorld,
				ShipMovement ? ShipMovement->PlanetCenter : FVector::ZeroVector,
				ProbeStart,
				ProbeEnd,
				ProbeHit);
			bool bProbeHit = ExitTerrainResult == ERedPlanetTerrainQueryResult::Hit;
			if (ExitTerrainResult == ERedPlanetTerrainQueryResult::NoMatchingPlanet)
			{
				FCollisionObjectQueryParams ExitObj;
				ExitObj.AddObjectTypesToQuery(ECC_WorldStatic);
				bProbeHit = ExitWorld->LineTraceSingleByObjectType(
					ProbeHit, ProbeStart, ProbeEnd, ExitObj, ExitParams);
			}
			if (bProbeHit && ProbeHit.bBlockingHit)
			{
				ExitLoc = ProbeHit.Location + PlanetUp * 150.f;
				break;
			}
		}
	}
	Pilot->OnExitedShip(ExitLoc, GetActorForwardVector(), this,
		/*bSnapToPlanetSurface=*/!bEmergencyEject && !bOrbitalExit);
	if (bOrbitalExit)
	{
		if (UCharacterMovementComponent* CharacterMovement = Pilot->GetCharacterMovement())
		{
			CharacterMovement->SetMovementMode(MOVE_Flying);
			CharacterMovement->Velocity = FVector::ZeroVector;
		}
	}
	Pilot->SetPilotCaptureOnly(false);
	Pilot->SetActorHiddenInGame(false);
	Pilot->SetActorEnableCollision(true);
	ARedPlayerCharacter* Leaving = Pilot;
	Pilot = nullptr;
	ForceNetUpdate();
	if (C) { C->Possess(Leaving); }
	if (APlayerController* PC = Cast<APlayerController>(C))
	{
		PC->SetInputMode(FInputModeGameOnly());
		PC->bShowMouseCursor = false;
		PC->SetIgnoreMoveInput(false);
		PC->SetIgnoreLookInput(false);
	}
	if (Leaving)
	{
		Leaving->SetHUDSpaceMinimap(false);
		if (!bEmergencyEject && !bOrbitalExit)
		{
			Leaving->SnapToPlanetSurfaceNow();
		}
	}
}
