#include "RedPlayerCharacter.h"

#include "RedPlanetGenCompat.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimMontage.h"
#include "Animation/AnimSequence.h"
#include "UObject/UnrealType.h"
#include "NiagaraFunctionLibrary.h"
#include "NiagaraSystem.h"
#include "NiagaraComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/MeshComponent.h"
#include "Components/PrimitiveComponent.h"
#include "Components/ChildActorComponent.h"
#include "Components/InputComponent.h"
#include "Components/AudioComponent.h"
#include "Sound/SoundBase.h"
#include "Particles/ParticleSystem.h"
#include "Particles/ParticleSystemComponent.h"
#include "PhysicalMaterials/PhysicalMaterial.h"
#include "Components/PointLightComponent.h"
#include "Components/DecalComponent.h"
#include "Components/SplineMeshComponent.h"
#include "Camera/CameraShakeBase.h"
#include "GameFramework/DamageType.h"
#include "GenericTeamAgentInterface.h"
#include "Net/UnrealNetwork.h"
#include "Interfaces/MovementBaseInterface.h"
#include "Engine/DamageEvents.h"
#include "Camera/CameraComponent.h"
#include "Camera/CameraActor.h"
#include "Components/CapsuleComponent.h"
#include "Components/BoxComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/SpringArmComponent.h"
#include "RadialGravityComponent.h"
#include "RedBolt.h"
#include "RedShip.h"
#include "RedShipMovementComponent.h"
#include "RedMiniFighter.h"
#include "RedShuttleBase.h"
#include "RedBotController.h"
#include "RedCharacterMovement.h"
#include "RedCloningStation.h"
#include "RedOctosphere.h"
#include "RedGameMode.h"
#include "RedHUD.h"
#include "RedPauseMenuWidget.h"
#include "Components/WorldPartitionStreamingSourceComponent.h"
#include "RedPlanetPresentationController.h"
#include "RedPlanetPresentationTuning.h"
#include "RedMineableAsteroid.h"
#include "RedShipExplosionFX.h"
#include "RedSpaceScenery.h"
#include "FootstepTrailComponent.h"
#include "RedShorelineWaveComponent.h"
#include "EngineUtils.h"
#include "Components/SkyAtmosphereComponent.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/SceneComponent.h"
#include "RedGravityBodies.h"
#include "RedDayNight.h"
#include "PlanetGen/CLMPlanet.h"
#include "Kismet/GameplayStatics.h"
#include "GameFramework/PlayerStart.h"
#include "Blueprint/UserWidget.h"
#include "Blueprint/WidgetTree.h"
#include "Components/SceneCaptureComponent2D.h"
#include "Components/TextBlock.h"
#include "Engine/TextureRenderTarget2D.h"
#include "Engine/Texture2D.h"
#include "Engine/Engine.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/GameStateBase.h"
#include "Widgets/VibeMMOHUDWidget.h"
#include "UObject/ConstructorHelpers.h"
#include "Materials/MaterialInterface.h"
#include "Materials/MaterialInstance.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Engine/StaticMeshActor.h"
#include "Components/StaticMeshComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "Sound/SoundBase.h"
#include "Sound/SoundAttenuation.h"
#include "TimerManager.h"
#include "UnrealClient.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMisc.h"
#include "Framework/Application/SlateApplication.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "UObject/UObjectIterator.h"

DEFINE_LOG_CATEGORY_STATIC(LogRedPlayerCharacter, Log, All);

namespace
{
void MakeClientAtmosphereAttachmentChainMovable(USceneComponent* Component)
{
	TArray<USceneComponent*> AttachmentChain;
	for (USceneComponent* Current = Component; Current; Current = Current->GetAttachParent())
	{
		AttachmentChain.Add(Current);
	}
	for (int32 Index = AttachmentChain.Num() - 1; Index >= 0; --Index)
	{
		if (AttachmentChain[Index]->Mobility != EComponentMobility::Movable)
		{
			AttachmentChain[Index]->SetMobility(EComponentMobility::Movable);
		}
	}
}

void GatherVehicleInteractionHulls(const AActor* Vehicle,
	TArray<const UPrimitiveComponent*>& OutHulls)
{
	OutHulls.Reset();
	if (!IsValid(Vehicle))
	{
		return;
	}

	TArray<UPrimitiveComponent*> Primitives;
	Vehicle->GetComponents<UPrimitiveComponent>(Primitives);
	for (const UPrimitiveComponent* Primitive : Primitives)
	{
		if (!Primitive || !Primitive->IsRegistered())
		{
			continue;
		}
		const FString Name = Primitive->GetName();
		if (Name.StartsWith(TEXT("Runtime")) && Name.Contains(TEXT("Collision")))
		{
			OutHulls.Add(Primitive);
		}
	}
}

float VehicleBoardingDistanceSquared(const AActor* Vehicle, const FVector& WorldPoint)
{
	if (!IsValid(Vehicle))
	{
		return TNumericLimits<float>::Max();
	}

	TArray<const UPrimitiveComponent*> InteractionHulls;
	GatherVehicleInteractionHulls(Vehicle, InteractionHulls);
	float BestDistanceSquared = TNumericLimits<float>::Max();
	for (const UPrimitiveComponent* InteractionHull : InteractionHulls)
	{
		const FBox HullBox = InteractionHull->Bounds.GetBox();
		if (HullBox.IsValid)
		{
			BestDistanceSquared = FMath::Min(BestDistanceSquared,
				HullBox.ComputeSquaredDistanceToPoint(WorldPoint));
		}
	}
	if (BestDistanceSquared < TNumericLimits<float>::Max())
	{
		return BestDistanceSquared;
	}
	return FVector::DistSquared(Vehicle->GetActorLocation(), WorldPoint);
}

FVector VehicleBoardingAimPoint(const AActor* Vehicle)
{
	if (!IsValid(Vehicle))
	{
		return FVector::ZeroVector;
	}

	TArray<const UPrimitiveComponent*> InteractionHulls;
	GatherVehicleInteractionHulls(Vehicle, InteractionHulls);
	FBox CombinedBounds(ForceInit);
	for (const UPrimitiveComponent* InteractionHull : InteractionHulls)
	{
		const FBox HullBox = InteractionHull->Bounds.GetBox();
		if (HullBox.IsValid)
		{
			CombinedBounds += HullBox;
		}
	}
	if (CombinedBounds.IsValid)
	{
		return CombinedBounds.GetCenter();
	}

	FVector Origin = Vehicle->GetActorLocation();
	FVector Extent = FVector::ZeroVector;
	Vehicle->GetActorBounds(false, Origin, Extent, true);
	return Origin;
}

float VehicleBoardingAimDot(const AActor* Vehicle, const FVector& ViewOrigin,
	const FVector& ViewForward)
{
	const FVector ToVehicle = VehicleBoardingAimPoint(Vehicle) - ViewOrigin;
	if (ToVehicle.IsNearlyZero())
	{
		return 1.f;
	}
	return FVector::DotProduct(ViewForward.GetSafeNormal(), ToVehicle.GetSafeNormal());
}

bool IsPlayerPlanetGenTerrainActor(const AActor* Actor)
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
	return Identity.Contains(TEXT("clmplanet"))
		|| Identity.Contains(TEXT("planetgen"))
		|| Identity.Contains(TEXT("planetchunk"))
		|| Identity.Contains(TEXT("terrainchunk"));
}

bool IsPlayerPlanetGenTerrainHit(const FHitResult& Hit)
{
	const UPrimitiveComponent* HitComponent = Hit.GetComponent();
	FString ComponentIdentity;
	ComponentIdentity += GetNameSafe(HitComponent);
	ComponentIdentity += TEXT(" ");
	for (const UClass* Class = HitComponent ? HitComponent->GetClass() : nullptr; Class; Class = Class->GetSuperClass())
	{
		ComponentIdentity += Class->GetName();
		ComponentIdentity += TEXT(" ");
	}
	ComponentIdentity.ToLowerInline();

	FString Identity;
	Identity.Reserve(256);
	Identity += ComponentIdentity;

	const AActor* Actor = Hit.GetActor();
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
	static const TCHAR* RejectedTokens[] =
	{
		TEXT("gameplaysurfacecollider"), TEXT("gameplaysurfacevisual"), TEXT("presentation"),
		TEXT("proxy"), TEXT("shell"), TEXT("sky"), TEXT("atmosphere"), TEXT("haze"),
		TEXT("cloud"), TEXT("dome"), TEXT("ship"), TEXT("weapon"), TEXT("projectile")
	};
	for (const TCHAR* Token : RejectedTokens)
	{
		if (Identity.Contains(Token))
		{
			return false;
		}
	}

	// PlanetGen's live chunks are components owned by ACLMPlanet/BP_CLMPlanet. Some plugin
	// versions expose the owner directly, while others report a procedural chunk actor, so keep
	// the test reflection/name based and require either the CLM identity or a procedural terrain
	// identity. Static-mesh props such as palms, rocks, ships and oasis dressing do not qualify.
	const bool bProceduralMesh = ComponentIdentity.Contains(TEXT("proceduralmesh"))
		|| ComponentIdentity.Contains(TEXT("dynamicmesh"));
	const bool bNamedTerrainComponent = ComponentIdentity.Contains(TEXT("terrainchunk"))
		|| ComponentIdentity.Contains(TEXT("planetchunk"))
		|| (ComponentIdentity.Contains(TEXT("clm")) && ComponentIdentity.Contains(TEXT("mesh")));
	if (Identity.Contains(TEXT("clmplanet")) || Identity.Contains(TEXT("planetgen")))
	{
		return bProceduralMesh || bNamedTerrainComponent;
	}
	const bool bTerrainContext = Identity.Contains(TEXT("clm"))
		|| Identity.Contains(TEXT("planetchunk"))
		|| Identity.Contains(TEXT("terrainchunk"));
	return (bProceduralMesh || bNamedTerrainComponent) && bTerrainContext;
}
}

ARedPlayerCharacter::ARedPlayerCharacter(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer.SetDefaultSubobjectClass<URedCharacterMovement>(ACharacter::CharacterMovementComponentName))
{
	PrimaryActorTick.bCanEverTick = true;
	// Run AFTER all physics + animation evaluation so the WeaponMesh world rotation we set
	// for barrel-pitch isn't overwritten by the skeletal mesh's bone-update reattaching
	// the gun to the hand socket each frame.
	PrimaryActorTick.TickGroup = TG_PostPhysics;
	bReplicates = true;
	WeaponSlotHeat.Init(0.0f, 2);
	WeaponSlotOverheated.Init(0, 2);
	bAlignWeaponBarrelToCamera = false;  // visual aim comes from the spine overlay; keep the rifle rigidly seated in the hand
	AimLeftRightScale = 0.0f;

	// Camera boom on the capsule. GRAVITY-ALIGNED ORBIT CAMERA (GravityCore pattern): the boom uses
	// ABSOLUTE rotation driven by UpdateOrbitCamera (heading vector + clamped pitch) — NOT control
	// rotation, whose world-frame yaw/pitch/roll cannot represent a stable sphere camera.
	SpringArm = CreateDefaultSubobject<USpringArmComponent>(TEXT("SpringArm"));
	SpringArm->SetupAttachment(RootComponent);
	SpringArm->TargetArmLength = BaseArmLength;
	SpringArm->bUsePawnControlRotation = false;
	SpringArm->SetUsingAbsoluteRotation(true);
	// Positional lag soaks up the capsule's micro-corrections on rough voxel ground — without it
	// every floor-adjust kicks the camera and the whole frame "jerks" while running.
	SpringArm->bEnableCameraLag = true;
	SpringArm->CameraLagSpeed = 16.f;
	SpringArm->CameraLagMaxDistance = 100.f;
	// Lag OFF: with lag on, Fire() reads a one-frame-stale camera position (fresh forward),
	// so while yawing the bolt fires down last frame's ray and drifts left of the reticle.
	SpringArm->bEnableCameraLag = false;
	SpringArm->SocketOffset = FVector(0.f, 60.f, 60.f); // over-the-shoulder

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(SpringArm);
	Camera->bUsePawnControlRotation = false;
	Camera->SetFieldOfView(BaseFOV);

	AmbientSandFX = CreateDefaultSubobject<UNiagaraComponent>(TEXT("AmbientSandFX"));
	AmbientSandFX->SetupAttachment(Camera);
	AmbientSandFX->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	AmbientSandFX->SetAutoActivate(false);
	AmbientSandFX->SetVisibility(false, true);
	static ConstructorHelpers::FObjectFinder<UNiagaraSystem> AmbientSandSystem(
		TEXT("/Game/Vefects/Sand_VFX/VFX/AmbientSand/NS_Flying_Sand_Around_Camera.NS_Flying_Sand_Around_Camera"));
	if (AmbientSandSystem.Succeeded())
	{
		AmbientSandFX->SetAsset(AmbientSandSystem.Object);
	}

	// Sphere gravity + surface orientation (reused proven component). Control-rotation rebasing is
	// OFF: the orbit camera doesn't read control rotation, so rebasing it just wastes work.
	RadialGravity = CreateDefaultSubobject<URadialGravityComponent>(TEXT("RadialGravity"));
	RadialGravity->bOrientToSurface = true;
	RadialGravity->bRebaseControlRotation = false;

	FootstepTrail = CreateDefaultSubobject<UFootstepTrailComponent>(TEXT("FootstepTrail"));
	if (FootstepTrail)
	{
		// Sand VFX supplies a real normal-only sole decal and compact lit ground puff, so prints
		// read as pressed into the PlanetGen sand rather than a square/glowing placeholder.
		static ConstructorHelpers::FObjectFinder<UMaterialInterface> FootprintMaterial(
			TEXT("/Game/Vefects/Sand_VFX/VFX/DynamicSandSurface/Materials/M_VFX_Footstep_Decal.M_VFX_Footstep_Decal"));
		if (FootprintMaterial.Succeeded())
		{
			FootstepTrail->DecalMaterial = FootprintMaterial.Object;
		}
		static ConstructorHelpers::FObjectFinder<UNiagaraSystem> FootstepPuff(
			TEXT("/Game/Vefects/Sand_VFX/VFX/LitSandPuff/NS_SandPuff_Small.NS_SandPuff_Small"));
		if (FootstepPuff.Succeeded())
		{
			FootstepTrail->StepPuffSystem = FootstepPuff.Object;
		}
		static ConstructorHelpers::FObjectFinder<USoundBase> FootstepSound(
			TEXT("/Game/SoStylized/Sounds/Step/SC_Steps_Dirt.SC_Steps_Dirt"));
		if (FootstepSound.Succeeded())
		{
			FootstepTrail->StepSound = FootstepSound.Object;
		}
		FootstepTrail->StepDistance = 150.0f;  // readable alternating trail without machine-gun stamping
		// X = projection DEPTH: was 42 → the decal box climbed 42cm up onto the shins/knees. 12 keeps it
		// hugging the ground. Y=width, Z=length(along movement) → ~1:2 to match the boot-sole texture.
		FootstepTrail->DecalSize = FVector(18.0f, 26.0f, 52.0f);
		FootstepTrail->DecalLifeSpan = 45.0f;
		FootstepTrail->FootprintSurfaceOffset = 3.5f;
		FootstepTrail->FootprintFadeScreenSize = 0.00002f;
		FootstepTrail->TraceLength = 12000.0f;
		FootstepTrail->TraceStartLift = 140.0f;
		FootstepTrail->FootSeparation = 38.0f;
		FootstepTrail->FootBackOffset = 20.0f;
		FootstepTrail->ForwardScuffDistance = 58.0f;
		FootstepTrail->ForwardScuffScale = 2.1f;
		FootstepTrail->MinSpeedForForwardScuff = 460.0f;
		FootstepTrail->StepPuffScale = 0.75f;
		FootstepTrail->SpeedDustScale = 0.0016f;
		FootstepTrail->StepSoundVolume = 0.28f;
	}

	// Held weapon mesh, attached to the hand socket on the character mesh.
	WeaponMesh = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("WeaponMesh"));
	WeaponMesh->SetupAttachment(GetMesh(), WeaponSocket);
	WeaponMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	// Projectiles use the camera ray and the visible barrel now follows that ray too, so
	// the held rifle visibly tracks the reticle instead of staying frozen in a carry pose.

	// RED atmospheric-entry plume (The Drop): a guaranteed-red glow + a trailing smoke volume on the
	// spine, hidden until the pawn is diving. The point light is the Metal-safe threat signal seen
	// from the ground; the Niagara adds volume (best-effort red tint).
	PlumeLight = CreateDefaultSubobject<UPointLightComponent>(TEXT("PlumeLight"));
	PlumeLight->SetupAttachment(GetMesh(), FName(TEXT("spine_03")));
	PlumeLight->SetMobility(EComponentMobility::Movable);
	PlumeLight->SetLightColor(PlumeColor);
	PlumeLight->SetIntensity(PlumeLightIntensity);
	PlumeLight->SetAttenuationRadius(PlumeLightRadius);
	PlumeLight->SetCastShadows(false);
	PlumeLight->SetVisibility(false);
	PlumeSmoke = CreateDefaultSubobject<UNiagaraComponent>(TEXT("PlumeSmoke"));
	PlumeSmoke->SetupAttachment(GetMesh(), FName(TEXT("spine_03")));
	PlumeSmoke->bAutoActivate = false;
	PlumeSmoke->SetRelativeScale3D(FVector(PlumeSmokeScale));
	PlumeSmoke->SetVisibility(false);

	// Sci-fi jetpack — pack-intended workflow (Jet_Packs_Sci-Fi):
	// ChildActor of Sci-Fi_Jetpack_Master_BP on spine_03 at identity (demo character does the same).
	// Master BP owns the skeletal pack mesh, Exhaust_L/R Cascade plumes, and engine audio. Do NOT
	// hack a static mesh onto the bone with a manual pivot offset (that put the pack inside/on shoulder).
	JetpackActor = CreateDefaultSubobject<UChildActorComponent>(TEXT("JetpackActor"));
	JetpackActor->SetupAttachment(GetMesh(), JetpackSocket);
	JetpackActor->SetRelativeLocation(JetpackLocation);
	JetpackActor->SetRelativeRotation(JetpackRotation);
	JetpackActor->SetRelativeScale3D(JetpackScale);
	{
		static ConstructorHelpers::FClassFinder<AActor> JetpackBP(
			TEXT("/Game/Jet_Packs_Sci-Fi/Blueprints/Sci-Fi_Jetpack_Master_BP"));
		if (JetpackBP.Succeeded())
		{
			JetpackActor->SetChildActorClass(JetpackBP.Class);
		}
	}

	// The stock SoStylized water material animates correctly on the sphere, but its authored edge
	// foam depends on mesh distance fields (PlanetGen runtime chunks cannot provide them).  This
	// local-only component samples the same deterministic terrain and draws real shoreline crests.

	// Legacy static mesh + dual-tank placeholders — kept for Blueprint compatibility, always hidden.
	JetpackMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("JetpackMesh"));
	JetpackMesh->SetupAttachment(GetMesh(), JetpackSocket);
	JetpackMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	JetpackMesh->SetVisibility(false);
	JetpackMesh->SetHiddenInGame(true);
	JetpackTankL = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("JetpackTankL"));
	JetpackTankL->SetupAttachment(GetMesh(), JetpackSocket);
	JetpackTankL->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	JetpackTankL->SetVisibility(false);
	JetpackTankR = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("JetpackTankR"));
	JetpackTankR->SetupAttachment(GetMesh(), JetpackSocket);
	JetpackTankR->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	JetpackTankR->SetVisibility(false);

	// Pack Cascade fire+smoke (Jet_Exhaust_PS). Seated on Exhaust_L/R with absolute
	// MakeFromX(actor-down) so thrust aims world-down (Cascade emits along local +X).
	// Cyan mesh cones kept as hidden stand-ins only — never shown while Cascade is live.
	auto MakeExhaustPSC = [this](const TCHAR* Name, const FVector& RelLoc) -> UParticleSystemComponent*
	{
		UParticleSystemComponent* PSC = CreateDefaultSubobject<UParticleSystemComponent>(Name);
		PSC->SetupAttachment(GetMesh(), JetpackSocket);
		PSC->bAutoActivate = false;
		PSC->SetVisibility(false);
		PSC->SetHiddenInGame(true);
		PSC->SetRelativeLocation(RelLoc);
		// Slightly undersized vs pack demo — cuts heat-refraction wash on the legs.
		PSC->SetRelativeScale3D(FVector(0.85f));
		return PSC;
	};
	JetpackExhaust = MakeExhaustPSC(TEXT("JetpackExhaust"), FVector(-22.f, 0.f, -14.f));
	JetpackExhaustL = MakeExhaustPSC(TEXT("JetpackExhaustL"), FVector(-20.f, -12.f, -12.f));
	JetpackExhaustR = MakeExhaustPSC(TEXT("JetpackExhaustR"), FVector(-20.f, 12.f, -12.f));
	{
		// Prefer the stronger authored exhaust and retain the pack's normal plume as fallback.
		static ConstructorHelpers::FObjectFinder<UParticleSystem> ExhaustPSLarge(
			TEXT("/Game/Jet_Packs_Sci-Fi/Particles/Large_Jet_Exhaust_PS.Large_Jet_Exhaust_PS"));
		static ConstructorHelpers::FObjectFinder<UParticleSystem> ExhaustPS(
			TEXT("/Game/Jet_Packs_Sci-Fi/Particles/Jet_Exhaust_PS.Jet_Exhaust_PS"));
		JetpackExhaustFX = ExhaustPSLarge.Succeeded()
			? ExhaustPSLarge.Object
			: (ExhaustPS.Succeeded() ? ExhaustPS.Object : nullptr);
		if (JetpackExhaustFX)
		{
			JetpackExhaust->SetTemplate(JetpackExhaustFX);
			JetpackExhaustL->SetTemplate(JetpackExhaustFX);
			JetpackExhaustR->SetTemplate(JetpackExhaustFX);
		}
	}

	// Hidden cyan cone stand-ins (pose reference only — Cascade is the visible plume).
	static ConstructorHelpers::FObjectFinder<UStaticMesh> PlumeConeMesh(
		TEXT("/Engine/BasicShapes/Cone.Cone"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> PlumeMatCyan(
		TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	if (PlumeMatCyan.Succeeded()) { JetpackPlumeMaterial = PlumeMatCyan.Object; }
	auto MakePlumeCone = [&](const TCHAR* Name) -> UStaticMeshComponent*
	{
		UStaticMeshComponent* Cone = CreateDefaultSubobject<UStaticMeshComponent>(Name);
		Cone->SetupAttachment(GetMesh(), JetpackSocket);
		Cone->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Cone->SetCastShadow(false);
		Cone->SetVisibility(false);
		Cone->SetHiddenInGame(true);
		if (PlumeConeMesh.Succeeded()) { Cone->SetStaticMesh(PlumeConeMesh.Object); }
		if (JetpackPlumeMaterial) { Cone->SetMaterial(0, JetpackPlumeMaterial); }
		Cone->SetRelativeScale3D(FVector(0.10f, 0.10f, 0.50f));
		return Cone;
	};
	JetpackPlumeCone = MakePlumeCone(TEXT("JetpackPlumeCone"));
	JetpackPlumeConeL = MakePlumeCone(TEXT("JetpackPlumeConeL"));
	JetpackPlumeConeR = MakePlumeCone(TEXT("JetpackPlumeConeR"));

	JetpackThrustAudio = CreateDefaultSubobject<UAudioComponent>(TEXT("JetpackThrustAudio"));
	JetpackThrustAudio->SetupAttachment(GetMesh(), JetpackSocket);
	JetpackThrustAudio->bAutoActivate = false;
	// World-space attenuation keeps remote packs local to their wearer instead of playing a
	// UI/full-volume loop for every replicated character.
	JetpackThrustAudio->SetUISound(false);
	JetpackThrustAudio->bIsUISound = false;
	JetpackThrustAudio->bAllowSpatialization = true;
	JetpackThrustAudio->bOverrideAttenuation = true;
	JetpackThrustAudio->AttenuationOverrides.bAttenuate = true;
	JetpackThrustAudio->AttenuationOverrides.bSpatialize = true;
	JetpackThrustAudio->AttenuationOverrides.DistanceAlgorithm = EAttenuationDistanceModel::NaturalSound;
	JetpackThrustAudio->AttenuationOverrides.AttenuationShape = EAttenuationShape::Sphere;
	JetpackThrustAudio->AttenuationOverrides.AttenuationShapeExtents = FVector(250.f, 0.f, 0.f);
	JetpackThrustAudio->AttenuationOverrides.FalloffDistance = 6000.f;
	{
		static ConstructorHelpers::FObjectFinder<USoundBase> ThrustCue(
			TEXT("/Game/Jet_Packs_Sci-Fi/Audio/Jet_Engine_Light_Loop_Cue.Jet_Engine_Light_Loop_Cue"));
		if (ThrustCue.Succeeded())
		{
			JetpackThrustSound = ThrustCue.Object;
			JetpackThrustAudio->SetSound(ThrustCue.Object);
		}
	}

	// Legacy Niagara flame accent (unused — pack exhaust is the thrust read now).
	JetpackFlame = CreateDefaultSubobject<UNiagaraComponent>(TEXT("JetpackFlame"));
	JetpackFlame->SetupAttachment(GetMesh(), JetpackSocket);
	JetpackFlame->bAutoActivate = false;
	JetpackFlame->SetVisibility(false);
	JetpackFlame->SetHiddenInGame(true);

	// Speed TRAIL — motion streaks behind you when riding fast.
	SpeedTrail = CreateDefaultSubobject<UNiagaraComponent>(TEXT("SpeedTrail"));
	SpeedTrail->SetupAttachment(GetCapsuleComponent());
	SpeedTrail->bAutoActivate = false;
	SpeedTrail->SetVisibility(false);
	if (SpeedTrailFX) { SpeedTrail->SetAsset(SpeedTrailFX); }

	// Hoverboard UNDERGLOW — a cyan light under the board so it reads as a tech board, not a gray plank.
	BoardGlow = CreateDefaultSubobject<UPointLightComponent>(TEXT("BoardGlow"));
	BoardGlow->SetupAttachment(GetCapsuleComponent());
	BoardGlow->SetRelativeLocation(FVector(10.f, 0.f, -GetCapsuleComponent()->GetScaledCapsuleHalfHeight() + 4.f));
	BoardGlow->SetLightColor(FLinearColor(0.0f, 0.85f, 1.0f));
	BoardGlow->SetIntensity(9000.f);
	BoardGlow->SetAttenuationRadius(320.f);
	BoardGlow->SetCastShadows(false);
	BoardGlow->SetVisibility(false);

	// HOVERBOARD: a flat board under the feet, shown only while riding. Placeholder engine-cube shape
	// (reads as a board) — swap for a real hoverboard mesh later.
	HoverboardMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("HoverboardMesh"));
	HoverboardMesh->SetupAttachment(GetCapsuleComponent());
	HoverboardMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	HoverboardMesh->SetRelativeLocation(FVector(10.f, 0.f, -GetCapsuleComponent()->GetScaledCapsuleHalfHeight() + 8.f));
	HoverboardMesh->SetRelativeScale3D(FVector(1.4f, 0.5f, 0.12f));
	HoverboardMesh->SetVisibility(false);
	static ConstructorHelpers::FObjectFinder<UStaticMesh> BoardAsset(TEXT("/Engine/BasicShapes/Cube.Cube"));
	if (BoardAsset.Succeeded()) { HoverboardMesh->SetStaticMesh(BoardAsset.Object); }
	// Optional plume FX from the retired pack remains null.

	// Landing slam: the purchased Sand FX pack supplies the broad ground burst and rock/debris layer.
	// A StylizedFX crack mesh is the non-decal ground read, while native Tall-Female Trooper jump
	// clips provide a skeleton-correct wind-up, dive silhouette and one-shot landing recovery.
	static ConstructorHelpers::FObjectFinder<UNiagaraSystem> SlamSandImpact(
		TEXT("/Game/Vefects/Sand_VFX/VFX/Impacts/NS_Sand_Impact_Ground_Big.NS_Sand_Impact_Ground_Big"));
	static ConstructorHelpers::FObjectFinder<UNiagaraSystem> SlamRockImpact(
		TEXT("/Game/Vefects/Sand_VFX/VFX/Rocks/Once/NS_Rock_Eruption_Once.NS_Rock_Eruption_Once"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> SlamCrackMesh(
		TEXT("/Game/StylizedFX_2/Meshes/MS_LandCrack_00.MS_LandCrack_00"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> SlamCrackMaterial(
		TEXT("/Game/StylizedFX_2/MI/MI_LandCrack.MI_LandCrack"));
	static ConstructorHelpers::FObjectFinder<UAnimSequence> SlamWindupAnimation(
		TEXT("/Game/Action_Trooper/Animations/Tall_Female/A_Female_Tall_ThirdPersonJump_Start.A_Female_Tall_ThirdPersonJump_Start"));
	static ConstructorHelpers::FObjectFinder<UAnimSequence> SlamDiveAnimation(
		TEXT("/Game/Action_Trooper/Animations/Tall_Female/A_Female_Tall_ThirdPersonJump_Loop.A_Female_Tall_ThirdPersonJump_Loop"));
	static ConstructorHelpers::FObjectFinder<UAnimSequence> SlamImpactAnimation(
		TEXT("/Game/Action_Trooper/Animations/Tall_Female/A_Female_Tall_ThirdPersonJump_End.A_Female_Tall_ThirdPersonJump_End"));
	SlamExplosionFX = SlamSandImpact.Succeeded() ? SlamSandImpact.Object : nullptr;
	SlamDebrisFX = SlamRockImpact.Succeeded() ? SlamRockImpact.Object : nullptr;
	SlamGroundCrackMesh = SlamCrackMesh.Succeeded() ? SlamCrackMesh.Object : nullptr;
	SlamGroundCrackMaterial = SlamCrackMaterial.Succeeded() ? SlamCrackMaterial.Object : nullptr;
	SlamWindupAnim = SlamWindupAnimation.Succeeded() ? SlamWindupAnimation.Object : nullptr;
	SlamDiveAnim = SlamDiveAnimation.Succeeded() ? SlamDiveAnimation.Object : nullptr;
	SlamImpactAnim = SlamImpactAnimation.Succeeded() ? SlamImpactAnimation.Object : nullptr;
	// Keep skydive playback on the active Tall Female skeleton. These compatible,
	// constructor-loaded animations are also guaranteed to be included in a cook.
	SkydiveFreefallAnim = SlamDiveAnim;
	SkydiveLandAnim = SlamImpactAnim;

	// Grapple energy tether: the purchased Beams VFX Pack supplies a continuous lightning/plasma
	// beam whose exposed User.BeamLength parameter lets gameplay stretch it from the hand to the
	// replicated anchor every frame.  The crossed spline ribbons remain a cook-safe fallback only.
	static ConstructorHelpers::FObjectFinder<UNiagaraSystem> GrapplePackBeamAsset(
		TEXT("/Game/BeamsPack/VFX/Beams/NS_BeamOnly_02.NS_BeamOnly_02"));
	GrappleRopeFX = GrapplePackBeamAsset.Succeeded() ? GrapplePackBeamAsset.Object : nullptr;
	GrappleRope = CreateDefaultSubobject<UNiagaraComponent>(TEXT("GrappleBeamsPackFX"));
	GrappleRope->SetupAttachment(GetMesh(), GrappleHandSocket);
	GrappleRope->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	GrappleRope->SetGenerateOverlapEvents(false);
	GrappleRope->SetCastShadow(false);
	GrappleRope->SetReceivesDecals(false);
	GrappleRope->SetAutoActivate(false);
	GrappleRope->SetVisibility(false, true);
	GrappleRope->SetHiddenInGame(true, true);
	// The beam can reach 250 m.  Override the compact authored preview bounds so the renderer does
	// not cull its far end while the component origin remains correctly seated on the hand socket.
	GrappleRope->SetSystemFixedBounds(FBox(
		FVector(-500.0f, -500.0f, -500.0f),
		FVector(GrappleMaxRange + 500.0f, GrappleMaxRange + 500.0f, GrappleMaxRange + 500.0f)));
	if (GrappleRopeFX)
	{
		GrappleRope->SetAsset(GrappleRopeFX);
	}

	static ConstructorHelpers::FObjectFinder<UStaticMesh> GrappleBeamMesh(
		TEXT("/Game/ProjectilesVol1/Models/SM_BeamMesh.SM_BeamMesh"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> GrappleBeamMaterial(
		TEXT("/Game/RedMMO/Materials/MI_RedGrapplePlasma.MI_RedGrapplePlasma"));
	static ConstructorHelpers::FObjectFinder<UNiagaraSystem> GrappleHeadAsset(
		TEXT("/Game/ProjectilesVol1/Effects/P_Projectile_17.P_Projectile_17"));
	GrapplePlasmaHeadFX = GrappleHeadAsset.Succeeded() ? GrappleHeadAsset.Object : nullptr;
	auto MakeGrappleBeam = [&](const TCHAR* Name, const float Roll) -> USplineMeshComponent*
	{
		USplineMeshComponent* Beam = CreateDefaultSubobject<USplineMeshComponent>(Name);
		Beam->SetupAttachment(GetMesh(), GrappleHandSocket);
		Beam->SetMobility(EComponentMobility::Movable);
		Beam->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Beam->SetGenerateOverlapEvents(false);
		Beam->SetCastShadow(false);
		Beam->SetReceivesDecals(false);
		Beam->SetForwardAxis(ESplineMeshAxis::Y, false);
		Beam->SetStartRoll(Roll, false);
		Beam->SetEndRoll(Roll, false);
		Beam->SetVisibility(false, true);
		Beam->SetHiddenInGame(true, true);
		if (GrappleBeamMesh.Succeeded())
		{
			Beam->SetStaticMesh(GrappleBeamMesh.Object);
		}
		if (GrappleBeamMaterial.Succeeded())
		{
			Beam->SetMaterial(0, GrappleBeamMaterial.Object);
		}
		return Beam;
	};
	GrapplePlasmaBeamA = MakeGrappleBeam(TEXT("GrapplePlasmaBeamA"), 0.0f);
	GrapplePlasmaBeamB = MakeGrappleBeam(TEXT("GrapplePlasmaBeamB"), HALF_PI);

	// Portrait capture: small camera in front of the character pointing back at the
	// face/upper body. Render target is created + assigned at BeginPlay (NewObject).
	PortraitCapture = CreateDefaultSubobject<USceneCaptureComponent2D>(TEXT("PortraitCapture"));
	PortraitCapture->SetupAttachment(GetCapsuleComponent());
	PortraitCapture->SetRelativeLocation(FVector(140.f, 0.f, 60.f));
	PortraitCapture->SetRelativeRotation(FRotator(0.f, 180.f, 0.f));
	PortraitCapture->FOVAngle = 25.f;
	PortraitCapture->CaptureSource = ESceneCaptureSource::SCS_FinalColorLDR;
	// PERF: these captures re-render the scene; every-frame = ~7ms/frame (22% of GPU) for tiny HUD
	// widgets. Drive them off a ~7Hz timer instead (RefreshHudCaptures) — imperceptible on the HUD.
	PortraitCapture->bCaptureEveryFrame = false;
	PortraitCapture->bCaptureOnMovement = false;
	PortraitCapture->bAlwaysPersistRenderingState = true;
	// ShowOnlyActors keeps other PRIMITIVES out, but the sky atmosphere/fog/clouds still render as
	// background — which painted the HUD portrait a flat planet-brown. Capture the character only.
	PortraitCapture->ShowFlags.SetAtmosphere(false);
	PortraitCapture->ShowFlags.SetFog(false);
	PortraitCapture->ShowFlags.SetVolumetricFog(false);
	PortraitCapture->ShowFlags.SetCloud(false);
	// Keep the neck-and-helmet portrait readable on the planet's dark side. The
	// capture uses the character's authored base colors over a solid HUD backdrop
	// instead of inheriting the live world's night exposure.
	PortraitCapture->ShowFlags.SetLighting(false);
	PortraitCapture->ShowFlags.SetPostProcessing(false);

	// Minimap capture: high above the player, looking straight down (orthographic).
	MinimapCapture = CreateDefaultSubobject<USceneCaptureComponent2D>(TEXT("MinimapCapture"));
	MinimapCapture->SetupAttachment(GetCapsuleComponent());
	MinimapCapture->SetRelativeLocation(FVector(0.f, 0.f, 5000.f));
	MinimapCapture->SetRelativeRotation(FRotator(-90.f, 0.f, 0.f));
	MinimapCapture->ProjectionType = ECameraProjectionMode::Orthographic;
	MinimapCapture->OrthoWidth = 6000.f;
	MinimapCapture->CaptureSource = ESceneCaptureSource::SCS_FinalColorLDR;
	MinimapCapture->bCaptureEveryFrame = false;   // PERF: timer-driven, not every frame (see RefreshHudCaptures)
	MinimapCapture->bCaptureOnMovement = false;
	MinimapCapture->bAlwaysPersistRenderingState = true;
	// The minimap re-renders the WHOLE scene top-down — it's the bulk of the capture cost. Strip the
	// expensive lighting/shadow/GI features it doesn't need for a flat overhead map.
	MinimapCapture->ShowFlags.SetDynamicShadows(false);
	MinimapCapture->ShowFlags.SetLumenGlobalIllumination(false);
	MinimapCapture->ShowFlags.SetLumenReflections(false);
	MinimapCapture->ShowFlags.SetAtmosphere(false);
	MinimapCapture->ShowFlags.SetFog(false);
	MinimapCapture->ShowFlags.SetVolumetricFog(false);
	MinimapCapture->ShowFlags.SetCloud(false);
	MinimapCapture->ShowFlags.SetAntiAliasing(false);

	// Character faces its movement direction; the controller drives the camera, not the body.
	bUseControllerRotationPitch = false;
	bUseControllerRotationYaw = false;
	bUseControllerRotationRoll = false;
	if (UCharacterMovementComponent* CMC = GetCharacterMovement())
	{
		// Do not let CharacterMovement and Tick both own yaw. The camera can swivel
		// freely; Tick rotates the body only when movement/large aim offset needs it.
		CMC->bOrientRotationToMovement = false;
		CMC->bUseControllerDesiredRotation = false;
		CMC->RotationRate = FRotator(0.f, 360.f, 0.f);
		CMC->JumpZVelocity = 600.f;
		CMC->AirControl = 0.35f;
		CMC->MaxWalkSpeed = 400.f;   // matches run anim; 548 Fortnite run is a follow-up (needs play-rate scaling)
		CMC->GroundFriction = 4.f;
	}

	// Default body mesh (Trooper) + locomotion anim BP.
	if (USkeletalMeshComponent* M = GetMesh())
	{
		// Always tick the pose, even on simulated proxies seen by other players,
		// so remote characters animate (legs run) instead of floating.
		M->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
		// SELF-CONSISTENT trooper rig: the Action_Trooper pack's UE4 Tall-Female armored body +
		// its OWN AnimBP, both on SKEL_UE4_Tall_Female_TRPR. The old setup drove a UE5F-trooper
		// mesh (SKEL_UE5F_89_TRPR) with a DMD AnimBP on the UE5 mannequin skeleton — that
		// skeleton gap was the stiff run + the wrong two-handed hold. Body+anims+ABP on ONE
		// skeleton = smooth native run, correct deformation, zero retargeting.
		static ConstructorHelpers::FObjectFinder<USkeletalMesh> BodyMesh(
			TEXT("/Game/Action_Trooper/Meshes/Trooper_UE4_Tall_Female/SK_TF_Trooper_Standalone_Covered.SK_TF_Trooper_Standalone_Covered"));
		static ConstructorHelpers::FObjectFinder<USkeletalMesh> ModularUpperMesh(
			TEXT("/Game/Action_Trooper/Meshes/Trooper_UE4_Tall_Female/SK_TF_Trooper_Upper.SK_TF_Trooper_Upper"));
		// ABP_ThirdPerson_Female_Tall ships with the pack: a smooth Idle/Run blendspace
		// (BS_ThirdPerson_Female_Tall_IdleRun) + jump, authored FOR this skeleton. It is
		// UNARMED locomotion — the two-handed rifle hold is layered on separately (see the
		// rifle-overlay pass); this baseline fixes the run and the skeleton mismatch first.
		static ConstructorHelpers::FClassFinder<UAnimInstance> AnimBP(
			TEXT("/Game/RedMMO/Characters/ABP_RedTrooperFemale.ABP_RedTrooperFemale_C"));

		// Custom Alien body: the user's Alien_Rigged skeletal mesh. We DELIBERATELY do NOT load its
		// retargeted ABP — that ABP keeps re-breaking its state-machine compile (K2Node_TransitionRuleGetter
		// on the additive/jump anims) and throws a "Play in Editor? unresolved compiler errors" MODAL on
		// every Play. Instead the alien runs single-node playback of the retargeted Idle/Run sequences
		// (UpdateAlienLocomotion, speed-driven). Clean, no AnimBlueprint, no compile error, no modal.
		// Cache both bodies so SwapBody() can flip between them live; ApplyBody() sets the active one.
		TrooperBodyMesh  = BodyMesh.Succeeded()  ? BodyMesh.Object  : nullptr;
		TrooperUpperBodyMesh = ModularUpperMesh.Succeeded() ? ModularUpperMesh.Object : nullptr;
		TrooperAnimClass = AnimBP.Succeeded()    ? AnimBP.Class     : nullptr;
		ApplyBody();
	}

	// Put the Trooper rifle in the hand. It rides the hand socket via a relative transform
	// (see WeaponHandLocalLocation/Rotation) — NO absolute-rotation aim-hack, which is what
	// pointed every gun skyward. Up/down aim comes from the spine aim-offset.
	static ConstructorHelpers::FObjectFinder<USkeletalMesh> TrooperRifle(
		TEXT("/Game/RedMMO/Weapons/SK_RedTrooper_Rifle_A.SK_RedTrooper_Rifle_A"));
	static ConstructorHelpers::FObjectFinder<USkeletalMesh> TrooperRifleB(
		TEXT("/Game/Action_Trooper/Meshes/Trooper_Accessories/SK_Trooper_Weapon_Rifle_B.SK_Trooper_Weapon_Rifle_B"));
	WeaponSlotMeshes.SetNum(2);
	if (TrooperRifle.Succeeded() && WeaponMesh)
	{
		WeaponMesh->SetSkeletalMesh(TrooperRifle.Object);
		WeaponSlotMeshes[0] = TrooperRifle.Object;
	}
	if (TrooperRifleB.Succeeded())
	{
		WeaponSlotMeshes[1] = TrooperRifleB.Object;
	}
	else if (TrooperRifle.Succeeded())
	{
		// Keep slot 2 operable in stripped cooks; full project builds resolve Rifle B above.
		WeaponSlotMeshes[1] = TrooperRifle.Object;
	}

	// Weapon fire audio: a sci-fi shot cue + DMD distance attenuation, so shots have sound and
	// far-off fire (including enemies') falls off instead of being heard planet-wide.
	// Retired weapon audio is intentionally absent.

	// The C++ bolt: SWEEPING collision that actually blocks ships + ground. The pack BP
	// (BP_Projectile_4) is NOT an ARedBolt — it flies on overlap-only logic and sailed straight
	// through hulls ("I shoot straight through" — three user reports before this was caught).
	ProjectileClass = ARedBolt::StaticClass();
	// Enemies fire the SAME clean laser bolt (was BP_Projectile_8 = an "arrow"-shaped pack projectile
	// with heavy per-bolt Cascade FX = the ugly look + a chunk of combat lag). Tinted red at spawn
	// (see FireAtTarget) so their fire still reads distinct from the player's.
	EnemyProjectileClass = ARedBolt::StaticClass();

	// No body-fire montage: AM_Dry_Fire_Rifle is FULL-BODY and stopped the legs when firing while
	// running (confirmed live 2026-06-29). The gun's own WeaponFireMontage handles visible firing.
	// Leave FireMontage null so firing never overrides locomotion. (Swap in an UPPER-BODY-only fire
	// montage here later if a body fire pose is wanted.)
	FireMontage = nullptr;
	// Weapon-mesh fire montage (bolt cycle / charging handle).
	// Optional weapon montage remains null.
	static ConstructorHelpers::FObjectFinder<UAnimSequence> RifleFireAnimation(
		TEXT("/Game/RedMMO/Anims/Rifle/A_Rifle_Fire_Single.A_Rifle_Fire_Single"));
	RifleFireAnim = RifleFireAnimation.Succeeded() ? RifleFireAnimation.Object : nullptr;

	// Muzzle flash matched to the projectile (ProjectilesVol1 P_Flash_4 = same neon as P_Projectile_4).
	static ConstructorHelpers::FObjectFinder<UNiagaraSystem> MuzzleFlashAsset(
		TEXT("/Game/ProjectilesVol1/Effects/P_Flash_4.P_Flash_4"));
	MuzzleFlashFX = MuzzleFlashAsset.Succeeded() ? MuzzleFlashAsset.Object : nullptr;
	static ConstructorHelpers::FObjectFinder<UNiagaraSystem> EnergyMuzzleFlashAsset(
		TEXT("/Game/ProjectilesVol1/Effects/P_Flash_17.P_Flash_17"));
	EnergyMuzzleFlashFX = EnergyMuzzleFlashAsset.Succeeded() ? EnergyMuzzleFlashAsset.Object : nullptr;

	// Two weapon variants for slots 1 and 2 (energy + bullet rifles).
	// Optional weapon variant list remains empty.

	// Directional death falls: the DMD set is on the UE5 mannequin skeleton and will NOT play
	// on the trooper's SKEL_UE4_Tall_Female_TRPR (PlayAnimation no-ops on a mismatched skeleton
	// → the corpse would freeze upright). Leave DeathAnims empty so OnDowned ragdolls (the
	// trooper standalone ships its own physics asset, so the ragdoll is clean). TODO: retarget
	// A_Death_F/B/L/R onto the trooper skeleton and re-populate this array.

	// Vibe MMO UI Kit HUD — use the WBP subclass (it supplies the WidgetTree the kit
	// populates; the native class has no WidgetTree so it renders blank).
	static ConstructorHelpers::FClassFinder<UVibeMMOHUDWidget> HUDBP(
		TEXT("/Game/RedMMO/UI/WBP_VibeMMOHUD"));
	if (HUDBP.Succeeded())
	{
		HUDWidgetClass = HUDBP.Class;
	}
	static ConstructorHelpers::FObjectFinder<UTexture2D> EpicWeaponCardAsset(
		TEXT("/Game/RedMMO/UI/Generated/weapon_slot_epic.weapon_slot_epic"));
	static ConstructorHelpers::FObjectFinder<UTexture2D> LegendaryWeaponCardAsset(
		TEXT("/Game/RedMMO/UI/Generated/weapon_slot_legendary.weapon_slot_legendary"));
	EpicWeaponCardTexture = EpicWeaponCardAsset.Succeeded() ? EpicWeaponCardAsset.Object : nullptr;
	LegendaryWeaponCardTexture = LegendaryWeaponCardAsset.Succeeded() ? LegendaryWeaponCardAsset.Object : nullptr;
	static ConstructorHelpers::FObjectFinder<UTexture2D> GrappleIconAsset(
		TEXT("/Game/SciFi_Skills_Icon/Textures/Tex_b_05.Tex_b_05"));
	static ConstructorHelpers::FObjectFinder<UTexture2D> SlamIconAsset(
		TEXT("/Game/SciFi_Skills_Icon/Textures/Tex_r_02.Tex_r_02"));
	GrappleAbilityIcon = GrappleIconAsset.Succeeded() ? GrappleIconAsset.Object : nullptr;
	SlamAbilityIcon = SlamIconAsset.Succeeded() ? SlamIconAsset.Object : nullptr;
}

bool ARedPlayerCharacter::TryActivatePlanetGenMovement()
{
	UWorld* World = GetWorld();
	FVector Center = FVector::ZeroVector;
	float DatumRadius = 0.f;
	float PeakRadius = 0.f;
	if (!World || !RedGravity::FindMeshPlanet(World, Center, DatumRadius, &PeakRadius))
	{
		return false;
	}

	if (URedCharacterMovement* RedMove = Cast<URedCharacterMovement>(GetCharacterMovement()))
	{
		const bool bBodyChanged = RedMove->bFlatMode
			|| !RedMove->PlanetCenter.Equals(Center, 1.0f)
			|| !FMath::IsNearlyEqual(RedMove->PlanetSurfaceRadius, DatumRadius, 1.0f);
		RedMove->PlanetCenter = Center;
		RedMove->PlanetSurfaceRadius = DatumRadius;
		RedMove->SurfaceStickGap = 0.0f;
		RedMove->bFlatMode = false;
		if (bBodyChanged)
		{
			// A legacy controller radius (382 km) is not valid history for the 6 km CLM body.
			RedMove->ResetFallGuard();
		}
	}

	const UCharacterMovementComponent* Movement = GetCharacterMovement();
	const bool bMovementLocked = GetAttachParentActor() != nullptr
		|| (Movement && Movement->MovementMode == MOVE_None);
	if (RadialGravity)
	{
		RadialGravity->PlanetCenter = Center;
		// Boarding deliberately disables this component. Discovery may complete while the pawn is
		// attached to a ship, so only re-enable it for a free character.
		if (!bMovementLocked)
		{
			RadialGravity->SetComponentTickEnabled(true);
		}
	}

	GetWorldTimerManager().ClearTimer(PlanetGenDiscoveryTimer);
	PlanetGenDiscoveryAttemptsRemaining = 0;
	UE_LOG(LogRedPlayerCharacter, Display,
		TEXT("PlanetGen movement active for %s Center=%s Datum=%.1f Peak=%.1f"),
		*GetNameSafe(this), *Center.ToCompactString(), DatumRadius, PeakRadius);
	return true;
}

void ARedPlayerCharacter::StartPlanetSurfaceSnap()
{
	UCharacterMovementComponent* Movement = GetCharacterMovement();
	if (GetLocalRole() == ROLE_SimulatedProxy || bDowned || bOrbitalDropActive || bSkydiving
		|| GetAttachParentActor() != nullptr || !Movement || Movement->MovementMode == MOVE_None)
	{
		return;
	}

	SurfaceSnapAttemptsRemaining = 80;
	GetWorldTimerManager().SetTimer(
		SurfaceSnapRetryTimer, this, &ARedPlayerCharacter::TrySnapToPlanetSurface, 0.1f, true, 0.05f);
	TrySnapToPlanetSurface();
}

void ARedPlayerCharacter::RetryPlanetGenInitialization()
{
	if (TryActivatePlanetGenMovement())
	{
		StartPlanetSurfaceSnap();
		return;
	}

	if (--PlanetGenDiscoveryAttemptsRemaining > 0)
	{
		return;
	}

	GetWorldTimerManager().ClearTimer(PlanetGenDiscoveryTimer);
	// A true legacy-only map keeps its fallback, but it is not allowed to analytically snap the
	// pawn to the old 382 km controller shell until PlanetGen has had a bounded startup window.
	if (const URedCharacterMovement* RedMove = Cast<URedCharacterMovement>(GetCharacterMovement());
		RedMove && !RedMove->bFlatMode)
	{
		StartPlanetSurfaceSnap();
	}
}

void ARedPlayerCharacter::BeginPlay()
{
	Super::BeginPlay();

	// The spring arm uses an absolute, gravity-aligned heading. Seed that heading
	// from the spawn transform instead of the class-default +X vector, otherwise a
	// pawn spawned facing -Y begins with its camera looking 90 degrees sideways.
	const FVector InitialUp = RedGravity::UpAt(
		GetWorld(), GetActorLocation(), GetActorUpVector());
	const FVector InitialForward = FVector::VectorPlaneProject(
		GetActorForwardVector(), InitialUp).GetSafeNormal();
	if (!InitialForward.IsNearlyZero())
	{
		CameraForward = InitialForward;
		CameraPitch = -10.f;
	}

	// Add presentation only after cooked CDO serialization has finished. This preserves
	// compatibility with the existing creator pack while still providing sphere tangents
	// and the local SoStylized shoreline crest ribbon.
	if (!ShorelineWaves)
	{
		ShorelineWaves = NewObject<URedShorelineWaveComponent>(
			this, TEXT("ShorelineWaves_Runtime"));
		if (ShorelineWaves)
		{
			AddInstanceComponent(ShorelineWaves);
			ShorelineWaves->RegisterComponent();
		}
	}

	// The creator now owns the complete deep-red trooper appearance through its Tall Female data
	// tables. Cache its optional weapon component on both gameplay and preview pawns. Gameplay keeps
	// it suppressed; preview shows either that selected weapon or RED's native Rifle A, never both.
	TInlineComponentArray<USkeletalMeshComponent*> SkeletalMeshes;
	GetComponents(SkeletalMeshes);
	for (USkeletalMeshComponent* Component : SkeletalMeshes)
	{
		if (Component && Component->GetFName() == FName(TEXT("SK_Weapon")))
		{
			CreatorWeaponMesh = Component;
			break;
		}
	}
	UpdateCreatorWeaponVisibility();

	// Seat the pack Master BP ChildActor on spine_03 (pack demo workflow) and hide legacy meshes.
	if (JetpackActor && GetMesh())
	{
		JetpackActor->AttachToComponent(GetMesh(), FAttachmentTransformRules::SnapToTargetNotIncludingScale, JetpackSocket);
		JetpackActor->SetRelativeLocationAndRotation(JetpackLocation, JetpackRotation);
		JetpackActor->SetRelativeScale3D(JetpackScale);
		if (!JetpackActor->GetChildActor() && JetpackActor->GetChildActorClass())
		{
			JetpackActor->CreateChildActor();
		}
	}
	SetJetpackVisible(!bUseAlienBody);
	bJetpackExhaustAttached = false;
	EnsureJetpackExhaustAttached();
	SetJetpackThrustFX(false);   // Master BP defaults exhaust ON — keep quiet until thrusting
	if (JetpackMesh)  { JetpackMesh->SetVisibility(false);  JetpackMesh->SetHiddenInGame(true); }
	if (JetpackTankL) { JetpackTankL->SetVisibility(false); JetpackTankL->SetHiddenInGame(true); }
	if (JetpackTankR) { JetpackTankR->SetVisibility(false); JetpackTankR->SetHiddenInGame(true); }
	if (JetpackExhaust) { JetpackExhaust->SetVisibility(false); JetpackExhaust->Deactivate(); }
	if (JetpackExhaustL) { JetpackExhaustL->SetVisibility(false); JetpackExhaustL->Deactivate(); }
	if (JetpackExhaustR) { JetpackExhaustR->SetVisibility(false); JetpackExhaustR->Deactivate(); }
	if (JetpackFlame)   { JetpackFlame->SetVisibility(false); JetpackFlame->Deactivate(); }

	UE_LOG(LogRedPlayerCharacter, Display, TEXT("BeginPlay %s Location=%s Radius=%.1f Controller=%s LocalRole=%d RemoteRole=%d"),
		*GetNameSafe(this),
		*GetActorLocation().ToCompactString(),
		GetActorLocation().Size(),
		*GetNameSafe(GetController()),
		static_cast<int32>(GetLocalRole()),
		static_cast<int32>(GetRemoteRole()));

	if (APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		PC->SetInputMode(FInputModeGameOnly());
		PC->bShowMouseCursor = false;
		PC->SetIgnoreMoveInput(false);
		PC->SetIgnoreLookInput(false);
	}

	// First hostile patrol so the world (and the minimap's red blips) isn't empty. Delayed so the
	// pawn has settled on the voxel surface, and re-checked in the callback: enemy clones run this
	// BeginPlay too, with bIsEnemy still false (it's set right after SpawnActor returns).
	if (bAutoSpawnEnemyWave)
	{
		FTimerHandle AutoWaveHandle;
		GetWorldTimerManager().SetTimer(AutoWaveHandle, this, &ARedPlayerCharacter::OnAutoSpawnWave, 2.5f, false);
	}

	// PlanetGen is the production body. Resolve it before the old presentation controller so a
	// map that retains both can never place the pawn on the controller's 382 km shell.
	const bool bUsingPlanetGen = TryActivatePlanetGenMovement();
	bool bFoundPlanet = bUsingPlanetGen;
	if (!bFoundPlanet)
	{
		for (TActorIterator<ARedPlanetPresentationController> It(GetWorld()); It; ++It)
		{
			const ARedPlanetPresentationController* PlanetController = *It;
			if (!IsValid(PlanetController))
			{
				continue;
			}
			if (URedCharacterMovement* RedMove = Cast<URedCharacterMovement>(GetCharacterMovement()))
			{
				RedMove->PlanetCenter = PlanetController->PlanetCenter;
				RedMove->PlanetSurfaceRadius = PlanetController->GetGameplaySurfaceRadius();
				RedMove->SurfaceStickGap = 0.0f;
				RedMove->bFlatMode = false;
			}
			if (RadialGravity)
			{
				RadialGravity->PlanetCenter = PlanetController->PlanetCenter;
			}
			bFoundPlanet = true;
			break;
		}
	}

	// Fallback: no PlanetController, but if a voxel planet (VoxelWorld) exists, STILL use radial
	// gravity toward it. Otherwise flat world-Z gravity makes the player fall off the FAR side of
	// the sphere (world "down" points into space there). This is the "no gravity on the far side" fix.
	if (!bFoundPlanet)
	{
		for (TActorIterator<AActor> It(GetWorld()); It; ++It)
		{
			if (IsValid(*It) && It->GetClass()->GetName() == TEXT("VoxelWorld"))
			{
				const FVector Center = It->GetActorLocation();  // voxel planet sits at the world origin
				if (URedCharacterMovement* RedMove = Cast<URedCharacterMovement>(GetCharacterMovement()))
				{
					RedMove->PlanetCenter = Center;
					RedMove->PlanetSurfaceRadius = 381800.f;   // measured ground radius near spawn
					RedMove->SurfaceStickGap = 0.0f;
					RedMove->bFlatMode = false;
				}
				if (RadialGravity)
				{
					RadialGravity->PlanetCenter = Center;
					RadialGravity->SetComponentTickEnabled(true);
				}
				bFoundPlanet = true;
				break;
			}
		}
	}

	if (bUsingPlanetGen)
	{
		StartPlanetSurfaceSnap();
	}
	else
	{
		if (!bFoundPlanet)
		{
			// No body yet: retain normal -Z gravity while BP_CLMPlanet finishes spawning.
			if (URedCharacterMovement* RedMove = Cast<URedCharacterMovement>(GetCharacterMovement()))
			{
				RedMove->bFlatMode = true;
			}
			if (RadialGravity)
			{
				RadialGravity->SetComponentTickEnabled(false);
			}
		}

		// Retry for 20 seconds (80 * 0.25s). The bound prevents a permanent timer on a genuine
		// flat/legacy map; a legacy analytic surface snap is deferred until this window expires.
		PlanetGenDiscoveryAttemptsRemaining = 80;
		GetWorldTimerManager().SetTimer(PlanetGenDiscoveryTimer, this,
			&ARedPlayerCharacter::RetryPlanetGenInitialization, 0.25f, true, 0.25f);
	}

	// Reset health/shield to max on (re)spawn.
	Health = MaxHealth;
	Shield = MaxShield;
	Armor = MaxArmor;
	EnsureWeaponSlotState();
	if (HasAuthority())
	{
		WeaponSlotHeat.Init(0.0f, 2);
		WeaponSlotOverheated.Init(0, 2);
		CurrentWeaponSlot = FMath::Clamp(CurrentWeaponSlot, 0, 1);
	}

	if (WeaponMesh && GetMesh())
	{
		// The focused pack set has no compatible skeletal rifle; keep the optional
		// weapon component empty while native projectile gameplay remains available.

		// The Action_Trooper skeleton bakes `hand_rSocket` at the right-hand grip with the
		// exact position+rotation its rifles were authored for — attach there with IDENTITY
		// and the gun sits cleanly in the hand (verified: 0cm to socket, ~10cm to wrist bone
		// = in the palm). NOTE: ik_hand_gun is NOT the grip on this rig (it sits ~35cm off in
		// unarmed poses), which is why the gun floated at the chest. Fallbacks below cover
		// other rigs. `bIdentityMount` = the socket already encodes the correct grip.
		static const FName GripSocket(TEXT("hand_rSocket"));
		FName AttachSocket = NAME_None;
		bool bIdentityMount = false;
		if (GetMesh()->DoesSocketExist(GripSocket)) { AttachSocket = GripSocket; bIdentityMount = true; }
		else if (GetMesh()->DoesSocketExist(WeaponSocket)) { AttachSocket = WeaponSocket; bIdentityMount = true; }
		else if (GetMesh()->DoesSocketExist(FName(TEXT("hand_r")))) { AttachSocket = FName(TEXT("hand_r")); }

		WeaponMesh->AttachToComponent(GetMesh(), FAttachmentTransformRules::SnapToTargetNotIncludingScale, AttachSocket);
		WeaponMesh->SetHiddenInGame(false, true);
		WeaponMesh->SetVisibility(true, true);
		WeaponMesh->SetRelativeScale3D(FVector::OneVector);
		if (bIdentityMount)
		{
			WeaponMesh->SetRelativeLocationAndRotation(FVector::ZeroVector, FRotator::ZeroRotator);
		}
		else if (AttachSocket != NAME_None)
		{
			// Bare hand_r bone (no authored grip socket) — legacy manual grip offset.
			WeaponMesh->SetRelativeRotation(FRotator(0.0f, 85.0f, -6.0f));
			ApplyWeaponGripOffset();
		}

		UE_LOG(LogRedPlayerCharacter, Display, TEXT("Weapon attach: Mesh=%s Socket=%s IdentityMount=%s Hidden=%s"),
			*GetNameSafe(WeaponMesh->GetSkeletalMeshAsset()),
			*AttachSocket.ToString(),
			bIdentityMount ? TEXT("yes") : TEXT("no"),
			WeaponMesh->bHiddenInGame ? TEXT("yes") : TEXT("no"));
	}

	// The AnimBP keeps the carry pose while AlignWeaponBarrelToCamera trims the weapon
	// rotation onto the camera ray late in the frame.
	if (USkeletalMeshComponent* M = GetMesh())
	{
		AddTickPrerequisiteComponent(M);
	}
	if (WeaponMesh)
	{
		AddTickPrerequisiteComponent(WeaponMesh);
		// Ride the hand socket with relative rotation — no absolute-rotation aim-hack.
		WeaponMesh->SetUsingAbsoluteRotation(false);
	}
	ApplyCurrentWeaponSlot();

	if (Camera)
	{
		Camera->SetFieldOfView(BaseFOV);
	}

	// BeginPlay can precede controller replication on a joining client. PawnClientRestart retries
	// this idempotent path after local possession becomes usable.
	TryCreateLocalHUD();
	UpdateHUDResources();

#if !UE_BUILD_SHIPPING
	// Disposable visual-acceptance harness for the isolated Night_T03 map.  Normal
	// clients never enter this branch, and Shipping builds do not contain it.  The
	// delayed sequence gives the cooked PlanetGen world, sky material, exposure, and
	// streaming state time to settle before capturing the exact surface and F9 orbit
	// views without synthesizing Windows input.
	if (FParse::Param(FCommandLine::Get(), TEXT("RedNightT03AutoCapture"))
		&& IsLocallyControlled() && GetWorld()
		&& GetWorld()->GetMapName().Contains(TEXT("Night_T03")))
	{
		FString CaptureDirectory;
		FParse::Value(FCommandLine::Get(), TEXT("RedNightT03CaptureDir="), CaptureDirectory);
		if (CaptureDirectory.IsEmpty())
		{
			CaptureDirectory = FPaths::Combine(
				FPaths::ProjectSavedDir(), TEXT("Screenshots/Night_T03_Auto"));
		}
		CaptureDirectory = FPaths::ConvertRelativePathToFull(CaptureDirectory);
		IFileManager::Get().MakeDirectory(*CaptureDirectory, true);

		const TWeakObjectPtr<ARedPlayerCharacter> WeakThis(this);
		FTimerHandle SurfaceCaptureHandle;
		GetWorldTimerManager().SetTimer(SurfaceCaptureHandle,
			FTimerDelegate::CreateLambda([WeakThis, CaptureDirectory]()
			{
				if (!WeakThis.IsValid())
				{
					return;
				}
				const FString Filename = FPaths::Combine(
					CaptureDirectory, TEXT("Night_T03_Surface.png"));
				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("Night_T03 auto capture requested: phase=surface file=%s location=%s"),
					*Filename, *WeakThis->GetActorLocation().ToCompactString());
				FScreenshotRequest::RequestScreenshot(
					Filename, false, false, false, FIntRect(), true);
			}), 18.0f, false);

		FTimerHandle OrbitTransitionHandle;
		GetWorldTimerManager().SetTimer(OrbitTransitionHandle,
			FTimerDelegate::CreateLambda([WeakThis]()
			{
				if (WeakThis.IsValid())
				{
					UE_LOG(LogRedPlayerCharacter, Display,
						TEXT("Night_T03 auto capture transition: invoking F9 orbit inspection path"));
					WeakThis->RestartOrbitalDrop();
				}
			}), 21.0f, false);

		FTimerHandle OrbitCaptureHandle;
		GetWorldTimerManager().SetTimer(OrbitCaptureHandle,
			FTimerDelegate::CreateLambda([WeakThis, CaptureDirectory]()
			{
				if (!WeakThis.IsValid())
				{
					return;
				}
				const FString Filename = FPaths::Combine(
					CaptureDirectory, TEXT("Night_T03_Orbit.png"));
				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("Night_T03 auto capture requested: phase=orbit file=%s location=%s"),
					*Filename, *WeakThis->GetActorLocation().ToCompactString());
				FScreenshotRequest::RequestScreenshot(
					Filename, false, false, false, FIntRect(), true);
			}), 31.0f, false);

		FTimerHandle ExitHandle;
		GetWorldTimerManager().SetTimer(ExitHandle,
			FTimerDelegate::CreateLambda([]()
			{
				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("Night_T03 auto capture sequence complete; requesting clean exit"));
				FPlatformMisc::RequestExit(false);
			}), 35.0f, false);

		UE_LOG(LogRedPlayerCharacter, Display,
			TEXT("Night_T03 auto capture armed: directory=%s surface=18s orbit=31s exit=35s"),
			*CaptureDirectory);
	}

	// T04 counterpart to the Night_T03 harness above.  This path is deliberately
	// gated by the disposable test map, the radial-water A/B flag, and its own
	// explicit capture flag.  It exercises the same F7 and F9 functions a player
	// uses, but asks Unreal's renderer to write the evidence directly so Windows
	// foreground-window quirks cannot invalidate the visual acceptance run.
	if (FParse::Param(FCommandLine::Get(), TEXT("RedNightWaterT04AutoCapture"))
		&& FParse::Param(FCommandLine::Get(), TEXT("NightWaterSoStylizedRadial"))
		&& IsLocallyControlled() && GetWorld()
		&& RedPlanetPresentationTuning::IsNightWaterT04MapName(GetWorld()->GetMapName()))
	{
		FString CaptureDirectory;
		FParse::Value(FCommandLine::Get(), TEXT("RedNightWaterT04CaptureDir="), CaptureDirectory);
		if (CaptureDirectory.IsEmpty())
		{
			CaptureDirectory = FPaths::Combine(
				FPaths::ProjectSavedDir(), TEXT("Screenshots/NightWater_T04_Auto"));
		}
		CaptureDirectory = FPaths::ConvertRelativePathToFull(CaptureDirectory);
		IFileManager::Get().MakeDirectory(*CaptureDirectory, true);
		const bool bCapturePhysicalMoon =
			FParse::Param(FCommandLine::Get(), TEXT("RedNightWaterT04MoonAudit"));
		const bool bCaptureWaterTemporalAudit =
			FParse::Param(FCommandLine::Get(), TEXT("RedNightWaterT04WaterAudit"));

		const TWeakObjectPtr<ARedPlayerCharacter> WeakThis(this);
		FTimerHandle ShoreTransitionHandle;
		GetWorldTimerManager().SetTimer(ShoreTransitionHandle,
			FTimerDelegate::CreateLambda([WeakThis, bCaptureWaterTemporalAudit]()
			{
				if (WeakThis.IsValid())
				{
					UE_LOG(LogRedPlayerCharacter, Display,
						TEXT("NightWater_T04 auto capture transition: invoking F7 shoreline path"));
					WeakThis->TeleportToShorelineVisualTest();
					// The temporal water gate needs registered frames of the surface,
					// not a clipped player/weapon silhouette. This is opt-in diagnostic
					// behavior only; ordinary F7 and every production map keep the pawn.
					if (bCaptureWaterTemporalAudit)
					{
						WeakThis->SetActorHiddenInGame(true);
					}
				}
			}), 8.0f, false);

		if (bCaptureWaterTemporalAudit)
		{
			FTimerHandle ShoreCaptureAHandle;
			GetWorldTimerManager().SetTimer(ShoreCaptureAHandle,
				FTimerDelegate::CreateLambda([WeakThis, CaptureDirectory]()
				{
					if (!WeakThis.IsValid())
					{
						return;
					}
					const FString Filename = FPaths::Combine(
						CaptureDirectory, TEXT("NightWater_T04_Shore_A.png"));
					UE_LOG(LogRedPlayerCharacter, Display,
						TEXT("NightWater_T04 auto capture requested: phase=shore_a file=%s location=%s"),
						*Filename, *WeakThis->GetActorLocation().ToCompactString());
					FScreenshotRequest::RequestScreenshot(
						Filename, false, false, false, FIntRect(), true);
				}), 14.0f, false);
		}

		FTimerHandle ShoreCaptureHandle;
		GetWorldTimerManager().SetTimer(ShoreCaptureHandle,
			FTimerDelegate::CreateLambda([WeakThis, CaptureDirectory]()
			{
				if (!WeakThis.IsValid())
				{
					return;
				}
				const FString Filename = FPaths::Combine(
					CaptureDirectory, TEXT("NightWater_T04_Shore.png"));
				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("NightWater_T04 auto capture requested: phase=shore file=%s location=%s"),
					*Filename, *WeakThis->GetActorLocation().ToCompactString());
				FScreenshotRequest::RequestScreenshot(
					Filename, false, false, false, FIntRect(), true);
			}), 18.0f, false);

		if (bCaptureWaterTemporalAudit)
		{
			FTimerHandle ShoreCaptureCHandle;
			GetWorldTimerManager().SetTimer(ShoreCaptureCHandle,
				FTimerDelegate::CreateLambda([WeakThis, CaptureDirectory]()
				{
					if (!WeakThis.IsValid())
					{
						return;
					}
					const FString Filename = FPaths::Combine(
						CaptureDirectory, TEXT("NightWater_T04_Shore_C.png"));
					UE_LOG(LogRedPlayerCharacter, Display,
						TEXT("NightWater_T04 auto capture requested: phase=shore_c file=%s location=%s"),
						*Filename, *WeakThis->GetActorLocation().ToCompactString());
					FScreenshotRequest::RequestScreenshot(
						Filename, false, false, false, FIntRect(), true);
				}), 22.0f, false);
		}

		if (bCapturePhysicalMoon)
		{
			FTimerHandle MoonAimHandle;
			GetWorldTimerManager().SetTimer(MoonAimHandle,
				FTimerDelegate::CreateLambda([WeakThis]()
				{
					if (!WeakThis.IsValid() || !WeakThis->GetWorld())
					{
						return;
					}

					for (TActorIterator<ARedSpaceScenery> It(WeakThis->GetWorld()); It; ++It)
					{
						FVector MoonCenter = FVector::ZeroVector;
						float MoonRadius = 0.f;
						float MoonInfluenceRadius = 0.f;
						if (!It->GetMoonGravityBody(
							MoonCenter, MoonRadius, MoonInfluenceRadius))
						{
							continue;
						}

						const FVector ViewLocation = WeakThis->Camera
							? WeakThis->Camera->GetComponentLocation()
							: WeakThis->GetActorLocation();
						const FVector ViewToMoon = (MoonCenter - ViewLocation).GetSafeNormal();
						const FVector LocalUp = RedGravity::UpAt(
							WeakThis->GetWorld(), ViewLocation, WeakThis->GetActorUpVector());
						const FVector TangentDirection = FVector::VectorPlaneProject(
							ViewToMoon, LocalUp).GetSafeNormal();
						if (ViewToMoon.IsNearlyZero() || TangentDirection.IsNearlyZero())
						{
							UE_LOG(LogRedPlayerCharacter, Error,
								TEXT("NightWater_T04 moon audit failed to derive camera direction: view=%s moon=%s"),
								*ViewLocation.ToCompactString(), *MoonCenter.ToCompactString());
							return;
						}

						WeakThis->CameraForward = TangentDirection;
						const float MoonElevationDegrees = FMath::RadiansToDegrees(FMath::Asin(
							FMath::Clamp(FVector::DotProduct(ViewToMoon, LocalUp), -1.f, 1.f)));
						WeakThis->CameraPitch = FMath::Clamp(
							MoonElevationDegrees, WeakThis->CameraPitchMin, WeakThis->CameraPitchMax);
						WeakThis->UpdateOrbitCamera();
						UE_LOG(LogRedPlayerCharacter, Display,
							TEXT("NightWater_T04 moon audit framed physical body: center=%s radius=%.0fcm distance=%.0fcm elevation=%.2fdeg camera=%s"),
							*MoonCenter.ToCompactString(), MoonRadius,
							FVector::Distance(ViewLocation, MoonCenter), MoonElevationDegrees,
							*ViewLocation.ToCompactString());
						return;
					}

					UE_LOG(LogRedPlayerCharacter, Error,
						TEXT("NightWater_T04 moon audit found no RedSpaceScenery actor"));
				}), 20.0f, false);

			FTimerHandle MoonCaptureHandle;
			GetWorldTimerManager().SetTimer(MoonCaptureHandle,
				FTimerDelegate::CreateLambda([WeakThis, CaptureDirectory]()
				{
					if (!WeakThis.IsValid())
					{
						return;
					}
					const FString Filename = FPaths::Combine(
						CaptureDirectory, TEXT("NightWater_T04_Moon.png"));
					UE_LOG(LogRedPlayerCharacter, Display,
						TEXT("NightWater_T04 auto capture requested: phase=moon file=%s location=%s"),
						*Filename, *WeakThis->GetActorLocation().ToCompactString());
					FScreenshotRequest::RequestScreenshot(
						Filename, false, false, false, FIntRect(), true);
				}), 23.0f, false);
		}

		const float OrbitTransitionSeconds = bCapturePhysicalMoon
			? 26.0f : (bCaptureWaterTemporalAudit ? 26.0f : 21.0f);
		const float OrbitCaptureSeconds = bCapturePhysicalMoon
			? 36.0f : (bCaptureWaterTemporalAudit ? 34.0f : 31.0f);
		const float ExitSeconds = bCapturePhysicalMoon
			? 40.0f : (bCaptureWaterTemporalAudit ? 38.0f : 35.0f);

		FTimerHandle OrbitTransitionHandle;
		GetWorldTimerManager().SetTimer(OrbitTransitionHandle,
			FTimerDelegate::CreateLambda([WeakThis]()
			{
				if (WeakThis.IsValid())
				{
					UE_LOG(LogRedPlayerCharacter, Display,
						TEXT("NightWater_T04 auto capture transition: invoking F9 orbit inspection path"));
					WeakThis->RestartOrbitalDrop();
				}
			}), OrbitTransitionSeconds, false);

		FTimerHandle OrbitCaptureHandle;
		GetWorldTimerManager().SetTimer(OrbitCaptureHandle,
			FTimerDelegate::CreateLambda([WeakThis, CaptureDirectory]()
			{
				if (!WeakThis.IsValid())
				{
					return;
				}
				const FString Filename = FPaths::Combine(
					CaptureDirectory, TEXT("NightWater_T04_Orbit.png"));
				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("NightWater_T04 auto capture requested: phase=orbit file=%s location=%s"),
					*Filename, *WeakThis->GetActorLocation().ToCompactString());
				FScreenshotRequest::RequestScreenshot(
					Filename, false, false, false, FIntRect(), true);
			}), OrbitCaptureSeconds, false);

		FTimerHandle ExitHandle;
		GetWorldTimerManager().SetTimer(ExitHandle,
			FTimerDelegate::CreateLambda([]()
			{
				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("NightWater_T04 auto capture sequence complete; requesting clean exit"));
				FPlatformMisc::RequestExit(false);
			}), ExitSeconds, false);

		UE_LOG(LogRedPlayerCharacter, Display,
			TEXT("NightWater_T04 auto capture armed: directory=%s shore=%s moon=%s orbit=%.0fs exit=%.0fs"),
			*CaptureDirectory,
			bCaptureWaterTemporalAudit ? TEXT("14s/18s/22s") : TEXT("18s"),
			bCapturePhysicalMoon ? TEXT("23s") : TEXT("disabled"),
			OrbitCaptureSeconds, ExitSeconds);
	}

	// Bounded, non-shipping real-GPU acceptance harness for the production daytime
	// sky and globally distributed HI-5 cloud deck. It captures the normal fused
	// surface view, invokes the same F9 orbit inspection path available to a player,
	// captures the orbit presentation, and exits cleanly. No normal client enters
	// this branch without the explicit command-line flag.
	if (FParse::Param(FCommandLine::Get(), TEXT("RedSkyCloudAutoCapture"))
		&& IsLocallyControlled() && GetWorld()
		&& GetWorld()->GetMapName().EndsWith(
			TEXT("RedPlanetGen_50km_FusedPrototype"), ESearchCase::CaseSensitive))
	{
		FString CaptureDirectory;
		FParse::Value(FCommandLine::Get(), TEXT("RedSkyCloudCaptureDir="), CaptureDirectory);
		if (CaptureDirectory.IsEmpty())
		{
			CaptureDirectory = FPaths::Combine(
				FPaths::ProjectSavedDir(), TEXT("Screenshots/SkyCloud_Auto"));
		}
		CaptureDirectory = FPaths::ConvertRelativePathToFull(CaptureDirectory);
		IFileManager::Get().MakeDirectory(*CaptureDirectory, true);

		const TWeakObjectPtr<ARedPlayerCharacter> WeakThis(this);
		FTimerHandle SurfaceCaptureHandle;
		GetWorldTimerManager().SetTimer(SurfaceCaptureHandle,
			FTimerDelegate::CreateLambda([WeakThis, CaptureDirectory]()
			{
				if (!WeakThis.IsValid())
				{
					return;
				}
				const FString Filename = FPaths::Combine(
					CaptureDirectory, TEXT("SkyCloud_Surface.png"));
				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("RED_SKY_CLOUD_CAPTURE phase=surface file=%s location=%s"),
					*Filename, *WeakThis->GetActorLocation().ToCompactString());
				FScreenshotRequest::RequestScreenshot(
					Filename, false, false, false, FIntRect(), true);
			}), 18.0f, false);

		FTimerHandle OrbitTransitionHandle;
		GetWorldTimerManager().SetTimer(OrbitTransitionHandle,
			FTimerDelegate::CreateLambda([WeakThis]()
			{
				if (WeakThis.IsValid())
				{
					UE_LOG(LogRedPlayerCharacter, Display,
						TEXT("RED_SKY_CLOUD_CAPTURE transition=F9_orbit"));
					WeakThis->RestartOrbitalDrop();
				}
			}), 21.0f, false);

		FTimerHandle OrbitCaptureHandle;
		GetWorldTimerManager().SetTimer(OrbitCaptureHandle,
			FTimerDelegate::CreateLambda([WeakThis, CaptureDirectory]()
			{
				if (!WeakThis.IsValid())
				{
					return;
				}
				const FString Filename = FPaths::Combine(
					CaptureDirectory, TEXT("SkyCloud_Orbit.png"));
				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("RED_SKY_CLOUD_CAPTURE phase=orbit file=%s location=%s"),
					*Filename, *WeakThis->GetActorLocation().ToCompactString());
				FScreenshotRequest::RequestScreenshot(
					Filename, false, false, false, FIntRect(), true);
			}), 31.0f, false);

		FTimerHandle ExitHandle;
		GetWorldTimerManager().SetTimer(ExitHandle,
			FTimerDelegate::CreateLambda([]()
			{
				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("RED_SKY_CLOUD_CAPTURE complete=1 requesting_clean_exit=1"));
				FPlatformMisc::RequestExit(false);
			}), 35.0f, false);

		UE_LOG(LogRedPlayerCharacter, Display,
			TEXT("RED_SKY_CLOUD_CAPTURE armed=1 directory=%s surface=18s orbit=31s exit=35s"),
			*CaptureDirectory);
	}

	// One-body acceptance probe for one playable ring-world moon. It is deliberately
	// non-shipping, production-map gated, and command-line only: normal gameplay never teleports
	// the pawn. The probe discovers the exact runtime component by stable ID, lets the ordinary
	// movement/gravity stack settle onto its collision, samples that state twice, writes one
	// renderer-backed frame, and exits. A screenshot can prove rendered presence and the telemetry
	// can prove physical contact/body selection; subjective camera/landing feel still needs a player.
	const bool bRingMoonAProbe = FParse::Param(
		FCommandLine::Get(), TEXT("RedRingMoonAProbe"));
	const bool bRingMoonBProbe = FParse::Param(
		FCommandLine::Get(), TEXT("RedRingMoonBProbe"));
	const bool bRingMoonCProbe = FParse::Param(
		FCommandLine::Get(), TEXT("RedRingMoonCProbe"));
	if ((bRingMoonAProbe || bRingMoonBProbe || bRingMoonCProbe)
		&& IsLocallyControlled() && GetWorld()
		&& GetWorld()->GetMapName().EndsWith(TEXT("RedPlanetGen"), ESearchCase::CaseSensitive))
	{
		const FString TargetDisplaySuffix = bRingMoonBProbe
			? TEXT("B") : (bRingMoonCProbe ? TEXT("C") : TEXT("A"));
		const FString TargetStableSuffix = TargetDisplaySuffix.ToLower();
		const FName TargetStableId(*FString::Printf(
			TEXT("moon.red.ring-01.%s"), *TargetStableSuffix));
		const FName TargetComponentTag(*FString::Printf(
			TEXT("RedGravityBodyId=moon.red.ring-01.%s"), *TargetStableSuffix));
		FString CaptureDirectory;
		FParse::Value(FCommandLine::Get(), TEXT("RedRingMoonProbeCaptureDir="), CaptureDirectory);
		if (CaptureDirectory.IsEmpty())
		{
			CaptureDirectory = FPaths::Combine(
				FPaths::ProjectSavedDir(), FString::Printf(
					TEXT("Screenshots/RingMoon%s_Probe"), *TargetDisplaySuffix));
		}
		CaptureDirectory = FPaths::ConvertRelativePathToFull(CaptureDirectory);
		IFileManager::Get().MakeDirectory(*CaptureDirectory, true);

		const auto ResolveTarget = [TargetStableId, TargetComponentTag](
			ARedPlayerCharacter* Pawn, UPrimitiveComponent*& OutComponent,
			FVector& OutCenter, float& OutSurfaceRadius, FVector& OutRingCenter) -> bool
		{
			OutComponent = nullptr;
			OutCenter = FVector::ZeroVector;
			OutSurfaceRadius = -1.f;
			OutRingCenter = FVector::ZeroVector;
			if (!Pawn || !Pawn->GetWorld())
			{
				return false;
			}

			for (TActorIterator<ARedSpaceScenery> It(Pawn->GetWorld()); It; ++It)
			{
				UPrimitiveComponent* CandidateComponent = nullptr;
				TArray<UPrimitiveComponent*> Components;
				It->GetComponents<UPrimitiveComponent>(Components);
				for (UPrimitiveComponent* Component : Components)
				{
					if (IsValid(Component) && Component->ComponentHasTag(TargetComponentTag))
					{
						CandidateComponent = Component;
						break;
					}
				}

				TArray<FName> StableIds;
				TArray<int32> Priorities;
				TArray<FVector> Centers;
				TArray<float> SurfaceRadii;
				TArray<float> InfluenceRadii;
				It->AppendGravityBodies(
					StableIds, Priorities, Centers, SurfaceRadii, InfluenceRadii);
				const int32 BodyIndex = StableIds.IndexOfByKey(TargetStableId);
				if (CandidateComponent && Centers.IsValidIndex(BodyIndex)
					&& SurfaceRadii.IsValidIndex(BodyIndex))
				{
					OutComponent = CandidateComponent;
					OutCenter = Centers[BodyIndex];
					OutSurfaceRadius = SurfaceRadii[BodyIndex];
					OutRingCenter = It->GetActorLocation() + It->RingWorldRelativeLocation;
					return OutSurfaceRadius > 0.f;
				}
			}
			return false;
		};

		const auto EvaluateContact = [ResolveTarget, TargetStableId](
			ARedPlayerCharacter* Pawn, const TCHAR* Phase) -> bool
		{
			UPrimitiveComponent* TargetComponent = nullptr;
			FVector MoonCenter = FVector::ZeroVector;
			float MoonRadius = -1.f;
			FVector RingCenter = FVector::ZeroVector;
			if (!ResolveTarget(Pawn, TargetComponent, MoonCenter, MoonRadius, RingCenter))
			{
				UE_LOG(LogRedPlayerCharacter, Error,
					TEXT("RED_RING_MOON_PROBE_FAIL phase=%s reason=target_not_found"), Phase);
				return false;
			}

			URedCharacterMovement* Movement = Cast<URedCharacterMovement>(
				Pawn->GetCharacterMovement());
			const FVector Location = Pawn->GetActorLocation();
			const FVector ExpectedUp = (Location - MoonCenter).GetSafeNormal();
			const float CapsuleHalfHeight = Pawn->GetCapsuleComponent()
				? Pawn->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 96.f;
			const float SurfaceGap = FVector::Distance(Location, MoonCenter)
				- MoonRadius - CapsuleHalfHeight;
			const float UpDot = FVector::DotProduct(Pawn->GetActorUpVector(), ExpectedUp);

			FCollisionObjectQueryParams ObjectTypes;
			ObjectTypes.AddObjectTypesToQuery(ECC_WorldStatic);
			ObjectTypes.AddObjectTypesToQuery(ECC_WorldDynamic);
			FCollisionQueryParams QueryParams(
				SCENE_QUERY_STAT(RedRingMoonProbeTrace), false, Pawn);
			FHitResult TraceHit;
			const bool bTraceHit = Pawn->GetWorld()->LineTraceSingleByObjectType(
				TraceHit, Location + ExpectedUp * 1000.f,
				Location - ExpectedUp * (CapsuleHalfHeight + 3000.f),
				ObjectTypes, QueryParams) && TraceHit.bBlockingHit;
			const bool bTraceExact = bTraceHit && TraceHit.GetComponent() == TargetComponent;
			const bool bFloorExact = Movement && Movement->CurrentFloor.bBlockingHit
				&& Movement->CurrentFloor.HitResult.GetComponent() == TargetComponent;
			const bool bWalking = Movement && Movement->IsMovingOnGround();
			const FName MovementBodyId = Movement
				? Movement->GetCurrentGravityBodyId() : NAME_None;
			const FName RadialBodyId = Pawn->RadialGravity
				? Pawn->RadialGravity->GetCurrentGravityBodyId() : NAME_None;
			RedGravity::FBodyQueryResult QueryBody;
			const bool bQueryBody = RedGravity::QueryDominantBodyDetailed(
				Pawn->GetWorld(), Location, TargetStableId, 25000.f, QueryBody);
			const bool bGravityExact = bQueryBody && QueryBody.StableId == TargetStableId
				&& MovementBodyId == TargetStableId && RadialBodyId == TargetStableId;
			const bool bContactExact = bWalking && bFloorExact && bTraceExact
				&& FMath::Abs(SurfaceGap) <= 40.f && UpDot >= 0.995f
				&& Pawn->GetVelocity().Size() <= 80.f;
			const FString QueryBodyId = bQueryBody
				? QueryBody.StableId.ToString() : TEXT("none");

			UE_LOG(LogRedPlayerCharacter, Display,
				TEXT("RED_RING_MOON_SAMPLE phase=%s component=%s movement=%s radial=%s query=%s walking=%d floorExact=%d traceExact=%d gap=%.2fcm upDot=%.5f speed=%.2f pass=%d"),
				Phase, *GetNameSafe(TargetComponent), *MovementBodyId.ToString(),
				*RadialBodyId.ToString(), *QueryBodyId,
				bWalking ? 1 : 0, bFloorExact ? 1 : 0, bTraceExact ? 1 : 0,
				SurfaceGap, UpDot, Pawn->GetVelocity().Size(),
				(bGravityExact && bContactExact) ? 1 : 0);
			return bGravityExact && bContactExact;
		};

		const TWeakObjectPtr<ARedPlayerCharacter> WeakThis(this);
		const TSharedRef<bool, ESPMode::ThreadSafe> FirstSamplePassed =
			MakeShared<bool, ESPMode::ThreadSafe>(false);
		const TSharedRef<bool, ESPMode::ThreadSafe> ProbePassed =
			MakeShared<bool, ESPMode::ThreadSafe>(false);
		FTimerHandle SetupHandle;
		GetWorldTimerManager().SetTimer(SetupHandle,
			FTimerDelegate::CreateLambda([WeakThis, ResolveTarget, TargetStableId]()
			{
				if (!WeakThis.IsValid())
				{
					return;
				}
				UPrimitiveComponent* TargetComponent = nullptr;
				FVector MoonCenter = FVector::ZeroVector;
				float MoonRadius = -1.f;
				FVector RingCenter = FVector::ZeroVector;
				if (!ResolveTarget(WeakThis.Get(), TargetComponent, MoonCenter, MoonRadius, RingCenter))
				{
					UE_LOG(LogRedPlayerCharacter, Error,
						TEXT("RED_RING_MOON_PROBE_FAIL phase=setup reason=target_not_found"));
					return;
				}

				FVector TowardRing = (RingCenter - MoonCenter).GetSafeNormal();
				FVector Side = FVector::CrossProduct(TowardRing, FVector::UpVector).GetSafeNormal();
				if (Side.IsNearlyZero())
				{
					Side = FVector::CrossProduct(TowardRing, FVector::ForwardVector).GetSafeNormal();
				}
				const FVector SurfaceUp = (TowardRing * 0.423f + Side * 0.906f).GetSafeNormal();
				const FVector Forward = FVector::VectorPlaneProject(TowardRing, SurfaceUp).GetSafeNormal();
				const float CapsuleHalfHeight = WeakThis->GetCapsuleComponent()
					? WeakThis->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 96.f;
				WeakThis->GetWorldTimerManager().ClearTimer(WeakThis->PlanetGenDiscoveryTimer);
				WeakThis->GetWorldTimerManager().ClearTimer(WeakThis->SurfaceSnapRetryTimer);
				WeakThis->SetActorEnableCollision(true);
				WeakThis->SetActorHiddenInGame(false);
				WeakThis->SetActorLocation(
					MoonCenter + SurfaceUp * (MoonRadius + CapsuleHalfHeight + 15.f),
					false, nullptr, ETeleportType::TeleportPhysics);
				WeakThis->SetActorRotation(
					FRotationMatrix::MakeFromXZ(Forward, SurfaceUp).Rotator(),
					ETeleportType::TeleportPhysics);
				WeakThis->CameraForward = Forward;
				WeakThis->CameraPitch = 8.f;
				WeakThis->UpdateOrbitCamera();
				if (URedCharacterMovement* Movement = Cast<URedCharacterMovement>(
					WeakThis->GetCharacterMovement()))
				{
					Movement->ResetFallGuard();
					Movement->StopMovementImmediately();
					Movement->SetMovementMode(MOVE_Falling);
				}
				if (WeakThis->RadialGravity)
				{
					WeakThis->RadialGravity->ResetRebase();
					WeakThis->RadialGravity->SetComponentTickEnabled(true);
				}
				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("RED_RING_MOON_TARGET id=%s component=%s center=%s radius=%.1fcm location=%s"),
					*TargetStableId.ToString(), *GetNameSafe(TargetComponent),
					*MoonCenter.ToCompactString(), MoonRadius,
					*WeakThis->GetActorLocation().ToCompactString());
			}), 8.0f, false);

		FTimerHandle FirstAuditHandle;
		GetWorldTimerManager().SetTimer(FirstAuditHandle,
			FTimerDelegate::CreateLambda([WeakThis, EvaluateContact, FirstSamplePassed]()
			{
				*FirstSamplePassed = WeakThis.IsValid()
					&& EvaluateContact(WeakThis.Get(), TEXT("settled_a"));
			}), 14.0f, false);

		FTimerHandle FinalAuditHandle;
		GetWorldTimerManager().SetTimer(FinalAuditHandle,
			FTimerDelegate::CreateLambda(
				[WeakThis, EvaluateContact, FirstSamplePassed, CaptureDirectory,
					TargetStableId, TargetDisplaySuffix, ProbePassed]()
			{
				if (!WeakThis.IsValid())
				{
					return;
				}
				const bool bFinalSamplePassed = EvaluateContact(
					WeakThis.Get(), TEXT("settled_b"));
				const bool bContinuousPass = *FirstSamplePassed && bFinalSamplePassed;
				*ProbePassed = bContinuousPass;
				const int32 PassedSamples = (*FirstSamplePassed ? 1 : 0)
					+ (bFinalSamplePassed ? 1 : 0);
				if (bContinuousPass)
				{
					UE_LOG(LogRedPlayerCharacter, Display,
						TEXT("RED_RING_MOON_CONTACT_PASS id=%s passedSamples=2 intervalSeconds=2"),
						*TargetStableId.ToString());
					UE_LOG(LogRedPlayerCharacter, Display,
						TEXT("RED_RING_MOON_GRAVITY_PASS id=%s"),
						*TargetStableId.ToString());
				}
				else
				{
					UE_LOG(LogRedPlayerCharacter, Error,
						TEXT("RED_RING_MOON_CONTACT_FAIL id=%s passedSamples=%d intervalSeconds=2"),
						*TargetStableId.ToString(), PassedSamples);
					UE_LOG(LogRedPlayerCharacter, Error,
						TEXT("RED_RING_MOON_GRAVITY_FAIL id=%s"),
						*TargetStableId.ToString());
				}
				const FString Filename = FPaths::Combine(
					CaptureDirectory, FString::Printf(
						TEXT("RingMoon%s_Standing.png"), *TargetDisplaySuffix));
				FScreenshotRequest::RequestScreenshot(
					Filename, false, false, false, FIntRect(), true);
				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("RED_RING_MOON_CAPTURE requested=%s"), *Filename);
			}), 16.0f, false);

		FTimerHandle ExitHandle;
		GetWorldTimerManager().SetTimer(ExitHandle,
			FTimerDelegate::CreateLambda([ProbePassed]()
			{
				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("RED_RING_MOON_PROBE_COMPLETE pass=%d requesting_clean_exit=1"),
					*ProbePassed ? 1 : 0);
				FPlatformMisc::RequestExit(false);
			}), 19.0f, false);

		UE_LOG(LogRedPlayerCharacter, Display,
			TEXT("Red ring Moon %s probe armed: id=%s directory=%s setup=8s audits=14s/16s exit=19s"),
			*TargetDisplaySuffix, *TargetStableId.ToString(), *CaptureDirectory);
	}

	// Disposable, command-line-only proof for the purchased Beams VFX grapple. The previous
	// screenshot attempt raced a normal 0.33-second gameplay pull, so it could not distinguish an
	// invisible vendor renderer from a missed frame. This audit freezes only the local diagnostic
	// pawn, holds a fixed endpoint in the active third-person view, captures three settled frames,
	// and reports projected hand/end coordinates plus primitive render state. Normal clients and
	// Shipping builds never enter this branch.
	if (FParse::Param(FCommandLine::Get(), TEXT("RedGrappleTetherAutoCapture"))
		&& IsLocallyControlled() && GetWorld())
	{
		FString CaptureDirectory;
		FParse::Value(FCommandLine::Get(), TEXT("RedGrappleTetherCaptureDir="), CaptureDirectory);
		if (CaptureDirectory.IsEmpty())
		{
			CaptureDirectory = FPaths::Combine(
				FPaths::ProjectSavedDir(), TEXT("Screenshots/GrappleTether_Auto"));
		}
		CaptureDirectory = FPaths::ConvertRelativePathToFull(CaptureDirectory);
		IFileManager::Get().MakeDirectory(*CaptureDirectory, true);

		const bool bVendorOnly =
			FParse::Param(FCommandLine::Get(), TEXT("RedGrappleTetherVendorOnly"));
		const TWeakObjectPtr<ARedPlayerCharacter> WeakThis(this);

		FTimerHandle GrappleSetupHandle;
		GetWorldTimerManager().SetTimer(GrappleSetupHandle,
			FTimerDelegate::CreateLambda([WeakThis, bVendorOnly]()
			{
				if (!WeakThis.IsValid() || !WeakThis->Camera || !WeakThis->GetMesh())
				{
					UE_LOG(LogRedPlayerCharacter, Error,
						TEXT("Grapple tether audit setup failed: pawn/camera/mesh unavailable"));
					return;
				}

				WeakThis->SetActorHiddenInGame(false);
				WeakThis->CameraPitch = -8.0f;
				WeakThis->UpdateOrbitCamera();
				const FVector ViewLocation = WeakThis->Camera->GetComponentLocation();
				const FVector ViewDirection = WeakThis->Camera->GetForwardVector().GetSafeNormal();
				const FVector Endpoint = ViewLocation + ViewDirection * 4200.0f;
				WeakThis->bKeepGrappleFallbackVisible = !bVendorOnly;
				WeakThis->StartGrapple(Endpoint, -ViewDirection, nullptr);
				if (UCharacterMovementComponent* Movement = WeakThis->GetCharacterMovement())
				{
					Movement->Velocity = FVector::ZeroVector;
					Movement->DisableMovement();
				}

				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("Grapple tether audit started: vendorOnly=%d asset=%s endpoint=%s length=%.1fcm"),
					bVendorOnly ? 1 : 0,
					WeakThis->GrappleRope && WeakThis->GrappleRope->GetAsset()
						? *WeakThis->GrappleRope->GetAsset()->GetPathName() : TEXT("none"),
					*Endpoint.ToCompactString(),
					FVector::Distance(WeakThis->GetMesh()->GetSocketLocation(WeakThis->GrappleHandSocket),
						Endpoint));
			}), 8.0f, false);

		auto ScheduleGrappleCapture =
			[this, WeakThis, CaptureDirectory](const float DelaySeconds, const FString& Phase)
		{
			FTimerHandle CaptureHandle;
			GetWorldTimerManager().SetTimer(CaptureHandle,
				FTimerDelegate::CreateLambda([WeakThis, CaptureDirectory, Phase]()
				{
					if (!WeakThis.IsValid() || !WeakThis->GetMesh())
					{
						return;
					}
					const FVector HandWorld = WeakThis->GetMesh()->DoesSocketExist(WeakThis->GrappleHandSocket)
						? WeakThis->GetMesh()->GetSocketLocation(WeakThis->GrappleHandSocket)
						: WeakThis->GetMesh()->GetComponentLocation();
					const FVector EndWorld = WeakThis->GetGrappleTargetPoint();
					FVector2D HandScreen(-1.0, -1.0);
					FVector2D EndScreen(-1.0, -1.0);
					int32 ViewWidth = 0;
					int32 ViewHeight = 0;
					bool bHandProjected = false;
					bool bEndProjected = false;
					if (APlayerController* PC = Cast<APlayerController>(WeakThis->GetController()))
					{
						PC->GetViewportSize(ViewWidth, ViewHeight);
						bHandProjected = PC->ProjectWorldLocationToScreen(HandWorld, HandScreen, true);
						bEndProjected = PC->ProjectWorldLocationToScreen(EndWorld, EndScreen, true);
					}
					const FBox VendorBounds = WeakThis->GrappleRope
						? WeakThis->GrappleRope->Bounds.GetBox() : FBox(EForceInit::ForceInit);
					UE_LOG(LogRedPlayerCharacter, Display,
						TEXT("Grapple tether audit capture: phase=%s vendorActive=%d vendorVisible=%d vendorHidden=%d vendorShouldRender=%d vendorRecentlyRendered=%d fallbackA=%d fallbackB=%d handProjected=%d handScreen=%s endProjected=%d endScreen=%s viewport=%dx%d bounds=%s"),
						*Phase,
						WeakThis->GrappleRope && WeakThis->GrappleRope->IsActive() ? 1 : 0,
						WeakThis->GrappleRope && WeakThis->GrappleRope->IsVisible() ? 1 : 0,
						WeakThis->GrappleRope && WeakThis->GrappleRope->bHiddenInGame ? 1 : 0,
						WeakThis->GrappleRope && WeakThis->GrappleRope->ShouldRender() ? 1 : 0,
						WeakThis->GrappleRope && WeakThis->GrappleRope->WasRecentlyRendered(0.5f) ? 1 : 0,
						WeakThis->GrapplePlasmaBeamA && WeakThis->GrapplePlasmaBeamA->IsVisible() ? 1 : 0,
						WeakThis->GrapplePlasmaBeamB && WeakThis->GrapplePlasmaBeamB->IsVisible() ? 1 : 0,
						bHandProjected ? 1 : 0, *HandScreen.ToString(),
						bEndProjected ? 1 : 0, *EndScreen.ToString(),
						ViewWidth, ViewHeight, *VendorBounds.ToString());

					const FString Filename = FPaths::Combine(
						CaptureDirectory, FString::Printf(TEXT("GrappleTether_%s.png"), *Phase));
					FScreenshotRequest::RequestScreenshot(
						Filename, false, false, false, FIntRect(), true);
				}), DelaySeconds, false);
		};
		ScheduleGrappleCapture(9.5f, TEXT("A"));
		ScheduleGrappleCapture(11.0f, TEXT("B"));
		ScheduleGrappleCapture(12.5f, TEXT("C"));

		FTimerHandle GrappleExitHandle;
		GetWorldTimerManager().SetTimer(GrappleExitHandle,
			FTimerDelegate::CreateLambda([]()
			{
				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("Grapple tether auto capture sequence complete; requesting clean exit"));
				FPlatformMisc::RequestExit(false);
			}), 14.0f, false);

		UE_LOG(LogRedPlayerCharacter, Display,
			TEXT("Grapple tether auto capture armed: directory=%s setup=8s captures=9.5s/11s/12.5s exit=14s vendorOnly=%d"),
			*CaptureDirectory, bVendorOnly ? 1 : 0);
	}

	// Isolated real-GPU acceptance harness for the project-owned So Stylized sparkle layer.
	// The material swap itself is separately gated in RedGameMode by -RedSandSparkleT02;
	// this branch only creates a transient camera and screenshots on a RedPlanetGen map.
	// It never saves the map and is absent from Shipping builds.
	if (FParse::Param(FCommandLine::Get(), TEXT("RedSandSparkleT02AutoCapture"))
		&& FParse::Param(FCommandLine::Get(), TEXT("RedSandSparkleT02"))
		&& IsLocallyControlled() && GetWorld()
		&& GetWorld()->GetMapName().Contains(TEXT("RedPlanetGen")))
	{
		FString CaptureDirectory;
		FParse::Value(FCommandLine::Get(), TEXT("RedSandSparkleT02CaptureDir="), CaptureDirectory);
		if (CaptureDirectory.IsEmpty())
		{
			CaptureDirectory = FPaths::Combine(
				FPaths::ProjectSavedDir(), TEXT("Screenshots/SandSparkle_T02_Auto"));
		}
		CaptureDirectory = FPaths::ConvertRelativePathToFull(CaptureDirectory);
		IFileManager::Get().MakeDirectory(*CaptureDirectory, true);

		const TWeakObjectPtr<ARedPlayerCharacter> WeakThis(this);
		const TSharedRef<TWeakObjectPtr<ACameraActor>> AuditCamera =
			MakeShared<TWeakObjectPtr<ACameraActor>>();

		FTimerHandle SetupHandle;
		GetWorldTimerManager().SetTimer(SetupHandle,
			FTimerDelegate::CreateLambda([WeakThis, AuditCamera]()
			{
				if (!WeakThis.IsValid() || !WeakThis->GetWorld())
				{
					return;
				}
				const FVector PawnLocation = WeakThis->GetActorLocation();
				const FVector Up = PawnLocation.GetSafeNormal();
				FVector Forward = FVector::VectorPlaneProject(
					WeakThis->GetActorForwardVector(), Up).GetSafeNormal();
				if (Forward.IsNearlyZero())
				{
					Forward = FVector::CrossProduct(FVector::ZAxisVector, Up).GetSafeNormal();
				}
				if (Forward.IsNearlyZero())
				{
					Forward = FVector::CrossProduct(FVector::XAxisVector, Up).GetSafeNormal();
				}
				const FVector CameraLocation = PawnLocation + Up * 90.0f - Forward * 120.0f;
				const FVector GroundTarget = PawnLocation - Up * 90.0f + Forward * 250.0f;
				FActorSpawnParameters SpawnParameters;
				SpawnParameters.Name = TEXT("RedSandSparkleT02AuditCamera");
				SpawnParameters.ObjectFlags |= RF_Transient;
				ACameraActor* CameraActor = WeakThis->GetWorld()->SpawnActor<ACameraActor>(
					CameraLocation, (GroundTarget - CameraLocation).Rotation(), SpawnParameters);
				if (!CameraActor)
				{
					UE_LOG(LogRedPlayerCharacter, Error,
						TEXT("RED_SAND_T02 setup failed: transient camera could not spawn"));
					return;
				}
				CameraActor->GetCameraComponent()->SetFieldOfView(62.0f);
				*AuditCamera = CameraActor;
				if (APlayerController* PC = Cast<APlayerController>(WeakThis->GetController()))
				{
					PC->SetViewTarget(CameraActor);
				}
				WeakThis->SetActorHiddenInGame(true);
				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("RED_SAND_T02 setup camera=%s pawn=%s up=%s"),
					*CameraLocation.ToCompactString(), *PawnLocation.ToCompactString(),
					*Up.ToCompactString());
			}), 9.0f, false);

		auto ScheduleCapture = [this, WeakThis, AuditCamera, CaptureDirectory](
			const float DelaySeconds, const FString& Phase)
		{
			FTimerHandle CaptureHandle;
			GetWorldTimerManager().SetTimer(CaptureHandle,
				FTimerDelegate::CreateLambda([WeakThis, AuditCamera, CaptureDirectory, Phase]()
				{
					if (!WeakThis.IsValid() || !AuditCamera->IsValid())
					{
						return;
					}
					const FString Filename = FPaths::Combine(
						CaptureDirectory, FString::Printf(TEXT("SandSparkle_T02_%s.png"), *Phase));
					UE_LOG(LogRedPlayerCharacter, Display,
						TEXT("RED_SAND_T02_CAPTURE phase=%s file=%s camera=%s"),
						*Phase, *Filename,
						*AuditCamera->Get()->GetActorLocation().ToCompactString());
					FScreenshotRequest::RequestScreenshot(
						Filename, false, false, false, FIntRect(), true);
				}), DelaySeconds, false);
		};
		ScheduleCapture(12.0f, TEXT("Close_A"));

		FTimerHandle ParallaxMoveHandle;
		GetWorldTimerManager().SetTimer(ParallaxMoveHandle,
			FTimerDelegate::CreateLambda([WeakThis, AuditCamera]()
			{
				if (!WeakThis.IsValid() || !AuditCamera->IsValid())
				{
					return;
				}
				const FVector PawnLocation = WeakThis->GetActorLocation();
				const FVector Up = PawnLocation.GetSafeNormal();
				FVector Forward = FVector::VectorPlaneProject(
					WeakThis->GetActorForwardVector(), Up).GetSafeNormal();
				if (Forward.IsNearlyZero())
				{
					Forward = FVector::CrossProduct(FVector::XAxisVector, Up).GetSafeNormal();
				}
				const FVector Side = FVector::CrossProduct(Up, Forward).GetSafeNormal();
				const FVector CameraLocation = PawnLocation + Up * 90.0f - Forward * 120.0f + Side * 100.0f;
				const FVector GroundTarget = PawnLocation - Up * 90.0f + Forward * 250.0f;
				AuditCamera->Get()->SetActorLocationAndRotation(
					CameraLocation, (GroundTarget - CameraLocation).Rotation());
			}), 13.2f, false);
		ScheduleCapture(14.4f, TEXT("Close_B"));

		FTimerHandle ObliqueMoveHandle;
		GetWorldTimerManager().SetTimer(ObliqueMoveHandle,
			FTimerDelegate::CreateLambda([WeakThis, AuditCamera]()
			{
				if (!WeakThis.IsValid() || !AuditCamera->IsValid())
				{
					return;
				}
				const FVector PawnLocation = WeakThis->GetActorLocation();
				const FVector Up = PawnLocation.GetSafeNormal();
				FVector Forward = FVector::VectorPlaneProject(
					WeakThis->GetActorForwardVector(), Up).GetSafeNormal();
				if (Forward.IsNearlyZero())
				{
					Forward = FVector::CrossProduct(FVector::XAxisVector, Up).GetSafeNormal();
				}
				const FVector Side = FVector::CrossProduct(Up, Forward).GetSafeNormal();
				const FVector CameraLocation = PawnLocation + Up * 260.0f - Forward * 500.0f + Side * 200.0f;
				const FVector GroundTarget = PawnLocation - Up * 90.0f + Forward * 220.0f;
				AuditCamera->Get()->SetActorLocationAndRotation(
					CameraLocation, (GroundTarget - CameraLocation).Rotation());
			}), 15.6f, false);
		ScheduleCapture(17.2f, TEXT("Oblique"));

		FTimerHandle ExitHandle;
		GetWorldTimerManager().SetTimer(ExitHandle,
			FTimerDelegate::CreateLambda([]()
			{
				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("RED_SAND_T02_COMPLETE requesting_clean_exit=1"));
				FPlatformMisc::RequestExit(false);
			}), 19.5f, false);

		UE_LOG(LogRedPlayerCharacter, Display,
			TEXT("RED_SAND_T02 auto capture armed: directory=%s setup=9s close=12s/14.4s oblique=17.2s exit=19.5s"),
			*CaptureDirectory);
	}

	// One-client real-GPU acceptance harness for DEF-0003 and DEF-0008. This is
	// deliberately command-line-only, absent from Shipping, and creates only
	// transient actors. It first records the unmodified surface view with no audit
	// asteroid, then frames the mining target beyond the deep-space field guard.
	// It exercises the production RegisterMiningHit path, checks that collision
	// shuts down at zero, holds the intact rock for the configured two seconds,
	// observes the explosion/debris and replicated reward receipt, then exits.
	if (FParse::Param(FCommandLine::Get(), TEXT("RedDEF0003DepletionAutoCapture"))
		&& IsLocallyControlled() && HasAuthority() && GetWorld())
	{
		FString CaptureDirectory;
		FParse::Value(FCommandLine::Get(), TEXT("RedDEF0003CaptureDir="), CaptureDirectory);
		if (CaptureDirectory.IsEmpty())
		{
			CaptureDirectory = FPaths::Combine(
				FPaths::ProjectSavedDir(), TEXT("Screenshots/DEF0003_Depletion_Auto"));
		}
		CaptureDirectory = FPaths::ConvertRelativePathToFull(CaptureDirectory);
		IFileManager::Get().MakeDirectory(*CaptureDirectory, true);
		const bool bUltrawideReceiptAudit = FParse::Param(
			FCommandLine::Get(), TEXT("RedDEF0004UltrawideReceiptAudit"));
		const bool bLegacyInventoryInteractionAudit = FParse::Param(
			FCommandLine::Get(), TEXT("RedDEF0004InventoryAudit"));
		const bool bControllerInventoryAudit = FParse::Param(
			FCommandLine::Get(), TEXT("RedDEF0004ControllerInventoryAudit"));
		const bool bUltrawideInventoryAudit = FParse::Param(
			FCommandLine::Get(),
			TEXT("RedDEF0004ControllerInventoryUltrawideAudit"));
		if (bLegacyInventoryInteractionAudit && bControllerInventoryAudit)
		{
			UE_LOG(LogRedPlayerCharacter, Error,
				TEXT("RED_DEF0004_CONTROLLER_RESULT pass=0 reason=mutually_exclusive_inventory_audits syntheticEngineControllerRoute=0 physicalControllerTested=0"));
			FPlatformMisc::RequestExit(false);
			return;
		}
		if (bUltrawideInventoryAudit && !bControllerInventoryAudit)
		{
			UE_LOG(LogRedPlayerCharacter, Error,
				TEXT("RED_DEF0004_ULTRAWIDE_INVENTORY_RESULT pass=0 reason=requires_controller_inventory_audit"));
			FPlatformMisc::RequestExit(false);
			return;
		}
		if (bUltrawideInventoryAudit && bUltrawideReceiptAudit)
		{
			UE_LOG(LogRedPlayerCharacter, Error,
				TEXT("RED_DEF0004_ULTRAWIDE_INVENTORY_RESULT pass=0 reason=mutually_exclusive_ultrawide_audits"));
			FPlatformMisc::RequestExit(false);
			return;
		}
		const bool bInventoryInteractionAudit =
			bLegacyInventoryInteractionAudit || bControllerInventoryAudit;
		const int32 ControllerInventoryViewportWidth =
			bUltrawideInventoryAudit ? 3440 : 1280;
		const int32 ControllerInventoryViewportHeight =
			bUltrawideInventoryAudit ? 1440 : 720;

		const TWeakObjectPtr<ARedPlayerCharacter> WeakThis(this);
		const TSharedRef<TWeakObjectPtr<ARedMineableAsteroid>> AuditAsteroid =
			MakeShared<TWeakObjectPtr<ARedMineableAsteroid>>();
		const TSharedRef<TWeakObjectPtr<ACameraActor>> AuditCamera =
			MakeShared<TWeakObjectPtr<ACameraActor>>();
		const TSharedRef<int32> InitialIron = MakeShared<int32>(ResIron);
		const TSharedRef<bool> SurfacePassed = MakeShared<bool>(false);
		const TSharedRef<bool> SetupPassed = MakeShared<bool>(false);
		const TSharedRef<bool> BeforePassed = MakeShared<bool>(false);
		const TSharedRef<bool> BeginPassed = MakeShared<bool>(false);
		const TSharedRef<bool> BeginHUDPassed = MakeShared<bool>(false);
		const TSharedRef<bool> MidPassed = MakeShared<bool>(false);
		const TSharedRef<bool> UltrawideFadePassed =
			MakeShared<bool>(!bUltrawideReceiptAudit);
		const TSharedRef<bool> InventoryOpenedPassed =
			MakeShared<bool>(!bInventoryInteractionAudit);
		const TSharedRef<bool> InventoryRefreshPassed =
			MakeShared<bool>(!bInventoryInteractionAudit);
		const TSharedRef<bool> InventoryClosedPassed =
			MakeShared<bool>(!bInventoryInteractionAudit);
		const TSharedRef<bool> ControllerInputPassed =
			MakeShared<bool>(true);

		auto ScheduleDEF0003Capture =
			[this, WeakThis, AuditAsteroid, CaptureDirectory](
				const float DelaySeconds, const FString& Phase)
		{
			FTimerHandle CaptureHandle;
			GetWorldTimerManager().SetTimer(CaptureHandle,
				FTimerDelegate::CreateLambda(
					[WeakThis, AuditAsteroid, CaptureDirectory, Phase]()
				{
					if (!WeakThis.IsValid())
					{
						return;
					}
					const FString Filename = FPaths::Combine(
						CaptureDirectory,
						FString::Printf(TEXT("DEF0003_%s.png"), *Phase));
					UE_LOG(LogRedPlayerCharacter, Display,
						TEXT("RED_DEF0003_CAPTURE phase=%s file=%s asteroidValid=%d"),
						*Phase, *Filename, AuditAsteroid->IsValid() ? 1 : 0);
					FScreenshotRequest::RequestScreenshot(
						Filename, true, false, false, FIntRect(), true);
				}), DelaySeconds, false);
		};

		FTimerHandle SurfaceAuditHandle;
		GetWorldTimerManager().SetTimer(SurfaceAuditHandle,
			FTimerDelegate::CreateLambda([WeakThis, SurfacePassed]()
			{
				if (!WeakThis.IsValid() || !WeakThis->GetWorld())
				{
					UE_LOG(LogRedPlayerCharacter, Error,
						TEXT("RED_DEF0008_SURFACE_FAIL reason=player_or_world_invalid"));
					return;
				}

				FVector PlanetCenter = FVector::ZeroVector;
				float DatumRadius = 0.f;
				float PeakRadius = 0.f;
				const bool bPlanetFrameResolved = RedGravity::FindMeshPlanet(
					WeakThis->GetWorld(), PlanetCenter, DatumRadius, &PeakRadius)
					&& DatumRadius > 0.f && PeakRadius >= DatumRadius;
				const float SurfaceRadius = bPlanetFrameResolved
					? (DatumRadius + PeakRadius) * 0.5f : 0.f;

				FVector ViewLocation = WeakThis->GetActorLocation();
				FRotator ViewRotation = WeakThis->GetActorRotation();
				if (const APlayerController* PC =
						Cast<APlayerController>(WeakThis->GetController());
					PC && PC->IsLocalController())
				{
					PC->GetPlayerViewPoint(ViewLocation, ViewRotation);
				}
				const float ViewAltitudeCm = bPlanetFrameResolved
					? FVector::Distance(ViewLocation, PlanetCenter) - SurfaceRadius
					: TNumericLimits<float>::Max();

				int32 ProductionFieldCount = 0;
				int32 AuditAsteroidCount = 0;
				float MinimumFieldAltitudeCm = TNumericLimits<float>::Max();
				float MinimumViewDistanceCm = TNumericLimits<float>::Max();
				bool bFieldContractPassed = true;
				for (TActorIterator<ARedMineableAsteroid> It(WeakThis->GetWorld()); It; ++It)
				{
					const ARedMineableAsteroid* Asteroid = *It;
					if (!IsValid(Asteroid))
					{
						continue;
					}
					if (Asteroid->ActorHasTag(TEXT("RedDEF0003AuditAsteroid")))
					{
						++AuditAsteroidCount;
						continue;
					}
					if (!Asteroid->ActorHasTag(TEXT("RedMarsMineableBelt")))
					{
						continue;
					}

					++ProductionFieldCount;
					const float AltitudeCm = bPlanetFrameResolved
						? FVector::Distance(Asteroid->GetActorLocation(), PlanetCenter)
							- SurfaceRadius
						: -1.f;
					const float ViewDistanceCm =
						FVector::Distance(ViewLocation, Asteroid->GetActorLocation());
					MinimumFieldAltitudeCm =
						FMath::Min(MinimumFieldAltitudeCm, AltitudeCm);
					MinimumViewDistanceCm =
						FMath::Min(MinimumViewDistanceCm, ViewDistanceCm);
					bFieldContractPassed &= AltitudeCm
							>= RedPlanetPresentationTuning::DeepSpaceAsteroidInnerAltitudeCm
								- 1.f
						&& AltitudeCm
							<= RedPlanetPresentationTuning::DeepSpaceAsteroidOuterAltitudeCm
								+ 1.f
						&& FMath::IsNearlyEqual(
							Asteroid->GetPresentationCullDistance(),
							RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm,
							1.f)
						&& ViewDistanceCm
							> RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm;
				}

				*SurfacePassed = bPlanetFrameResolved
					&& ViewAltitudeCm < RedPlanetPresentationTuning::AtmosphereHeightCm
					&& ProductionFieldCount == 24
					&& AuditAsteroidCount == 0
					&& bFieldContractPassed;
				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("RED_DEF0008_SURFACE pass=%d frame=%d viewAltitudeKm=%.3f atmosphereKm=%.3f productionField=%d auditAsteroids=%d fieldContract=%d minimumFieldAltitudeKm=%.3f minimumViewDistanceKm=%.3f cullKm=%.3f"),
					*SurfacePassed ? 1 : 0,
					bPlanetFrameResolved ? 1 : 0,
					ViewAltitudeCm * 0.00001f,
					RedPlanetPresentationTuning::AtmosphereHeightCm * 0.00001f,
					ProductionFieldCount,
					AuditAsteroidCount,
					bFieldContractPassed ? 1 : 0,
					MinimumFieldAltitudeCm * 0.00001f,
					MinimumViewDistanceCm * 0.00001f,
					RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm
						* 0.00001f);
			}), 5.8f, false);
		if (!bControllerInventoryAudit)
		{
			ScheduleDEF0003Capture(6.1f, TEXT("Surface"));
		}
		if (bLegacyInventoryInteractionAudit)
		{
			FTimerHandle InventoryOpenHandle;
			GetWorldTimerManager().SetTimer(InventoryOpenHandle,
				FTimerDelegate::CreateLambda(
					[WeakThis, InventoryOpenedPassed]()
				{
					if (!WeakThis.IsValid() || !WeakThis->GetWorld())
					{
						UE_LOG(LogRedPlayerCharacter, Error,
							TEXT("RED_DEF0004_INVENTORY_OPEN pass=0 reason=player_or_world_invalid"));
						return;
					}

					APlayerController* PC =
						Cast<APlayerController>(WeakThis->GetController());
					ARedHUD* HUD = PC ? Cast<ARedHUD>(PC->GetHUD()) : nullptr;
					if (!PC || !HUD)
					{
						UE_LOG(LogRedPlayerCharacter, Error,
							TEXT("RED_DEF0004_INVENTORY_OPEN pass=0 reason=controller_or_hud_invalid"));
						return;
					}

					HUD->TogglePauseMenu();
					URedPauseMenuWidget* PauseMenu = nullptr;
					for (TObjectIterator<URedPauseMenuWidget> It; It; ++It)
					{
						if (It->GetWorld() == WeakThis->GetWorld()
							&& It->IsInViewport())
						{
							PauseMenu = *It;
							break;
						}
					}
					if (PauseMenu)
					{
						if (UFunction* HandleInventory =
							PauseMenu->FindFunction(TEXT("HandleInventory")))
						{
							PauseMenu->ProcessEvent(HandleInventory, nullptr);
						}
					}

					URedEmbeddedInventoryWidget* Inventory =
						PauseMenu && PauseMenu->WidgetTree
							? PauseMenu->WidgetTree
								->FindWidget<URedEmbeddedInventoryWidget>(
									FName(TEXT("PauseInventoryWidget")))
							: nullptr;
					int32 Stone = INDEX_NONE;
					int32 Iron = INDEX_NONE;
					int32 Crystal = INDEX_NONE;
					FString Summary;
					int32 ViewportWidth = 0;
					int32 ViewportHeight = 0;
					PC->GetViewportSize(ViewportWidth, ViewportHeight);
					const bool bTotalsPassed = Inventory
						&& Inventory->GetResourceTotals(
							Stone, Iron, Crystal, Summary)
						&& Stone == WeakThis->ResStone
						&& Iron == WeakThis->ResIron
						&& Crystal == WeakThis->ResCrystal;
					*InventoryOpenedPassed = PauseMenu
						&& PauseMenu->IsVisible()
						&& bTotalsPassed
						&& ViewportWidth == 1280
						&& ViewportHeight == 720;
					UE_LOG(LogRedPlayerCharacter, Display,
						TEXT("RED_DEF0004_INVENTORY_OPEN pass=%d viewport=%dx%d visible=%d stone=%d iron=%d crystal=%d summary=\"%s\""),
						*InventoryOpenedPassed ? 1 : 0,
						ViewportWidth, ViewportHeight,
						PauseMenu && PauseMenu->IsVisible() ? 1 : 0,
						Stone, Iron, Crystal,
						*Summary.ReplaceCharWithEscapedChar());
				}), 6.35f, false);
			ScheduleDEF0003Capture(
				6.75f, TEXT("InventoryBeforeMining"));
		}
		else if (bControllerInventoryAudit)
		{
			UE_LOG(LogRedPlayerCharacter, Display,
				TEXT("RED_DEF0004_CONTROLLER_ARMED provenance=synthetic_engine_controller_callback injection=FSlateApplication_ProcessKeyDownEvent physicalControllerTested=0 start=6.35 ironSelect=8.65 refresh=10.90 close=13.20"));

			auto ScheduleControllerInput =
				[this, WeakThis, ControllerInputPassed](
					const float DelaySeconds,
					const FKey Key,
					const int32 Sequence,
					const FString& Phase)
			{
				FTimerHandle InputHandle;
				GetWorldTimerManager().SetTimer(InputHandle,
					FTimerDelegate::CreateLambda(
						[WeakThis, ControllerInputPassed, Key, Sequence, Phase]()
					{
						if (!WeakThis.IsValid() || !WeakThis->GetWorld()
							|| !FSlateApplication::IsInitialized())
						{
							*ControllerInputPassed = false;
							UE_LOG(LogRedPlayerCharacter, Error,
								TEXT("RED_DEF0004_CONTROLLER_INPUT seq=%d phase=%s key=%s pressHandled=0 releaseHandled=0 reason=player_world_or_slate_invalid"),
								Sequence, *Phase, *Key.ToString());
							return;
						}

						auto FindPauseMenu = [WeakThis]()
							-> URedPauseMenuWidget*
						{
							for (TObjectIterator<URedPauseMenuWidget> It; It; ++It)
							{
								if (It->GetWorld() == WeakThis->GetWorld()
									&& It->IsInViewport())
								{
									return *It;
								}
							}
							return nullptr;
						};

						auto QueryFocus = [](URedPauseMenuWidget* PauseMenu)
							-> FString
						{
							if (!PauseMenu)
							{
								return TEXT("none");
							}
							FString Region;
							int32 Primary = INDEX_NONE;
							int32 Category = INDEX_NONE;
							int32 Visual = INDEX_NONE;
							int32 Stable = INDEX_NONE;
							FString Focused;
							bool bHasFocus = false;
							PauseMenu->GetControllerInventoryState(
								Region, Primary, Category, Visual, Stable,
								Focused, bHasFocus);
							return FString::Printf(
								TEXT("%s:p%d:c%d:v%d:s%d:%s:focus%d"),
								*Region, Primary, Category, Visual, Stable,
								*Focused, bHasFocus ? 1 : 0);
						};

						const FString BeforeFocus = QueryFocus(FindPauseMenu());
						const FModifierKeysState Modifiers;
						const FKeyEvent PressEvent(
							Key, Modifiers, 0, false, 0, 0);
						const bool bPressHandled =
							FSlateApplication::Get().ProcessKeyDownEvent(
								PressEvent);
						const FKeyEvent ReleaseEvent(
							Key, Modifiers, 0, false, 0, 0);
						const bool bReleaseHandled =
							FSlateApplication::Get().ProcessKeyUpEvent(
								ReleaseEvent);
						const FString AfterFocus = QueryFocus(FindPauseMenu());
						UE_LOG(LogRedPlayerCharacter, Display,
							TEXT("RED_DEF0004_CONTROLLER_INPUT seq=%d phase=%s key=%s pressHandled=%d releaseHandled=%d before=\"%s\" after=\"%s\" provenance=synthetic_engine_controller_callback physicalControllerTested=0"),
							Sequence, *Phase, *Key.ToString(),
							bPressHandled ? 1 : 0,
							bReleaseHandled ? 1 : 0,
							*BeforeFocus.ReplaceCharWithEscapedChar(),
							*AfterFocus.ReplaceCharWithEscapedChar());
					}), DelaySeconds, false);
			};

			auto ScheduleControllerInventoryAdvance =
				[this, WeakThis, ControllerInputPassed](
					const float DelaySeconds, const int32 Sequence)
			{
				FTimerHandle InputHandle;
				GetWorldTimerManager().SetTimer(InputHandle,
					FTimerDelegate::CreateLambda(
						[WeakThis, ControllerInputPassed, Sequence]()
					{
						if (!WeakThis.IsValid() || !WeakThis->GetWorld()
							|| !FSlateApplication::IsInitialized())
						{
							*ControllerInputPassed = false;
							UE_LOG(LogRedPlayerCharacter, Error,
								TEXT("RED_DEF0004_CONTROLLER_INPUT seq=%d phase=AdaptiveInventory key=None pressHandled=0 releaseHandled=0 reason=player_world_or_slate_invalid adaptive=1"),
								Sequence);
							return;
						}

						URedPauseMenuWidget* PauseMenu = nullptr;
						for (TObjectIterator<URedPauseMenuWidget> It; It; ++It)
						{
							if (It->GetWorld() == WeakThis->GetWorld()
								&& It->IsInViewport())
							{
								PauseMenu = *It;
								break;
							}
						}
						FString Region;
						int32 Primary = INDEX_NONE;
						int32 Category = INDEX_NONE;
						int32 Visual = INDEX_NONE;
						int32 Stable = INDEX_NONE;
						FString Focused;
						bool bHasFocus = false;
						const bool bState = PauseMenu
							&& PauseMenu->GetControllerInventoryState(
								Region, Primary, Category, Visual, Stable,
								Focused, bHasFocus);
						const FString BeforeFocus = FString::Printf(
							TEXT("%s:p%d:c%d:v%d:s%d:%s:focus%d"),
							*Region, Primary, Category, Visual, Stable,
							*Focused, bHasFocus ? 1 : 0);

						FKey Key;
						FString Phase;
						bool bComplete = false;
						if (!bState || !bHasFocus)
						{
							Phase = TEXT("InvalidState");
						}
						else if (Region == TEXT("PrimaryMenu")
							&& Primary == 3)
						{
							Key = EKeys::Gamepad_FaceButton_Bottom;
							Phase = TEXT("InventoryAccept");
						}
						else if (Region == TEXT("InventoryCategory"))
						{
							const int32 ResourcesCategory =
								static_cast<int32>(
									EVibeMMOInventoryCategory::Resources);
							if (Category < ResourcesCategory)
							{
								Key = EKeys::Gamepad_DPad_Right;
								Phase = TEXT("CategoryRight");
							}
							else if (Category == ResourcesCategory
								&& Stable != INDEX_NONE)
							{
								Key = EKeys::Gamepad_FaceButton_Bottom;
								Phase = TEXT("ResourcesAccept");
							}
							else if (Category == ResourcesCategory)
							{
								Key = EKeys::Gamepad_DPad_Down;
								Phase = TEXT("GridStone");
							}
						}
						else if (Region == TEXT("InventoryGrid")
							&& Visual == 0)
						{
							Key = EKeys::Gamepad_DPad_Right;
							Phase = TEXT("GridIron");
						}
						else if (Region == TEXT("InventoryGrid")
							&& Visual == 1 && Stable != 3)
						{
							Key = EKeys::Gamepad_FaceButton_Bottom;
							Phase = TEXT("IronAccept");
						}
						else if (Region == TEXT("InventoryGrid")
							&& Visual == 1 && Stable == 3)
						{
							Phase = TEXT("Complete");
							bComplete = true;
						}

						if (bComplete)
						{
							UE_LOG(LogRedPlayerCharacter, Display,
								TEXT("RED_DEF0004_CONTROLLER_INPUT seq=%d phase=%s key=None pressHandled=1 releaseHandled=1 before=\"%s\" after=\"%s\" adaptive=1 provenance=synthetic_engine_controller_callback physicalControllerTested=0"),
								Sequence, *Phase,
								*BeforeFocus.ReplaceCharWithEscapedChar(),
								*BeforeFocus.ReplaceCharWithEscapedChar());
							return;
						}
						if (!Key.IsValid())
						{
							*ControllerInputPassed = false;
							UE_LOG(LogRedPlayerCharacter, Error,
								TEXT("RED_DEF0004_CONTROLLER_INPUT seq=%d phase=%s key=None pressHandled=0 releaseHandled=0 before=\"%s\" reason=unhandled_inventory_state adaptive=1"),
								Sequence, *Phase,
								*BeforeFocus.ReplaceCharWithEscapedChar());
							return;
						}

						const FModifierKeysState Modifiers;
						const FKeyEvent PressEvent(
							Key, Modifiers, 0, false, 0, 0);
						const bool bPressHandled =
							FSlateApplication::Get().ProcessKeyDownEvent(
								PressEvent);
						const FKeyEvent ReleaseEvent(
							Key, Modifiers, 0, false, 0, 0);
						const bool bReleaseHandled =
							FSlateApplication::Get().ProcessKeyUpEvent(
								ReleaseEvent);
						FString AfterRegion;
						int32 AfterPrimary = INDEX_NONE;
						int32 AfterCategory = INDEX_NONE;
						int32 AfterVisual = INDEX_NONE;
						int32 AfterStable = INDEX_NONE;
						FString AfterFocused;
						bool bAfterHasFocus = false;
						PauseMenu->GetControllerInventoryState(
							AfterRegion, AfterPrimary, AfterCategory,
							AfterVisual, AfterStable, AfterFocused,
							bAfterHasFocus);
						FString AfterFocus = FString::Printf(
							TEXT("%s:p%d:c%d:v%d:s%d:%s:focus%d"),
							*AfterRegion, AfterPrimary, AfterCategory,
							AfterVisual, AfterStable, *AfterFocused,
							bAfterHasFocus ? 1 : 0);
						bool bFallbackRouteUsed = false;
						if (Region == TEXT("PrimaryMenu")
							&& Key == EKeys::Gamepad_FaceButton_Bottom
							&& AfterFocus == BeforeFocus)
						{
							bFallbackRouteUsed =
								PauseMenu->RouteControllerKey(Key, false);
							PauseMenu->GetControllerInventoryState(
								AfterRegion, AfterPrimary, AfterCategory,
								AfterVisual, AfterStable, AfterFocused,
								bAfterHasFocus);
							AfterFocus = FString::Printf(
								TEXT("%s:p%d:c%d:v%d:s%d:%s:focus%d"),
								*AfterRegion, AfterPrimary, AfterCategory,
								AfterVisual, AfterStable, *AfterFocused,
								bAfterHasFocus ? 1 : 0);
						}
						UE_LOG(LogRedPlayerCharacter, Display,
							TEXT("RED_DEF0004_CONTROLLER_INPUT seq=%d phase=%s key=%s pressHandled=%d releaseHandled=%d fallbackRoute=%d before=\"%s\" after=\"%s\" adaptive=1 provenance=synthetic_engine_controller_callback physicalControllerTested=0"),
							Sequence, *Phase, *Key.ToString(),
							bPressHandled ? 1 : 0,
							bReleaseHandled ? 1 : 0,
							bFallbackRouteUsed ? 1 : 0,
							*BeforeFocus.ReplaceCharWithEscapedChar(),
							*AfterFocus.ReplaceCharWithEscapedChar());
					}), DelaySeconds, false);
			};

			ScheduleControllerInput(
				6.35f, EKeys::Gamepad_Special_Right, 1, TEXT("Open"));
			ScheduleControllerInput(
				6.75f, EKeys::Gamepad_DPad_Down, 2, TEXT("PrimaryDown1"));
			ScheduleControllerInput(
				6.95f, EKeys::Gamepad_DPad_Down, 3, TEXT("PrimaryDown2"));
			ScheduleControllerInput(
				7.15f, EKeys::Gamepad_DPad_Down, 4, TEXT("PrimaryInventory"));
			ScheduleControllerInventoryAdvance(7.35f, 5);
			ScheduleControllerInventoryAdvance(7.55f, 6);
			ScheduleControllerInventoryAdvance(7.75f, 7);
			ScheduleControllerInventoryAdvance(7.95f, 8);
			ScheduleControllerInventoryAdvance(8.15f, 9);
			ScheduleControllerInventoryAdvance(8.35f, 10);
			ScheduleControllerInventoryAdvance(8.55f, 11);
			ScheduleControllerInventoryAdvance(8.75f, 12);
			ScheduleControllerInventoryAdvance(8.85f, 13);

			FTimerHandle ControllerOpenCheckHandle;
			GetWorldTimerManager().SetTimer(
				ControllerOpenCheckHandle,
				FTimerDelegate::CreateLambda(
					[WeakThis, ControllerInputPassed,
						ControllerInventoryViewportWidth,
						ControllerInventoryViewportHeight,
						bUltrawideInventoryAudit]()
				{
					APlayerController* PC = WeakThis.IsValid()
						? Cast<APlayerController>(WeakThis->GetController())
						: nullptr;
					URedPauseMenuWidget* PauseMenu = nullptr;
					for (TObjectIterator<URedPauseMenuWidget> It; It; ++It)
					{
						if (WeakThis.IsValid()
							&& It->GetWorld() == WeakThis->GetWorld()
							&& It->IsInViewport())
						{
							PauseMenu = *It;
							break;
						}
					}
					FString Region;
					int32 Primary = INDEX_NONE;
					int32 Category = INDEX_NONE;
					int32 Visual = INDEX_NONE;
					int32 Stable = INDEX_NONE;
					FString Focused;
					bool bHasFocus = false;
					const bool bState = PauseMenu
						&& PauseMenu->GetControllerInventoryState(
							Region, Primary, Category, Visual, Stable,
							Focused, bHasFocus);
					int32 ViewportWidth = 0;
					int32 ViewportHeight = 0;
					if (PC)
					{
						PC->GetViewportSize(ViewportWidth, ViewportHeight);
					}
					const bool bPassed = PauseMenu && PauseMenu->IsVisible()
						&& bState && Region == TEXT("PrimaryMenu")
						&& Primary == 0
						&& bHasFocus
						&& ViewportWidth == ControllerInventoryViewportWidth
						&& ViewportHeight == ControllerInventoryViewportHeight;
					*ControllerInputPassed &= bPassed;
					UE_LOG(LogRedPlayerCharacter, Display,
						TEXT("RED_DEF0004_CONTROLLER_OPEN pass=%d viewport=%dx%d expectedViewport=%dx%d ultrawideInventoryAudit=%d visible=%d region=%s primary=%d focused=%s hasFocus=%d provenance=synthetic_engine_controller_callback physicalControllerTested=0"),
						bPassed ? 1 : 0,
						ViewportWidth, ViewportHeight,
						ControllerInventoryViewportWidth,
						ControllerInventoryViewportHeight,
						bUltrawideInventoryAudit ? 1 : 0,
						PauseMenu && PauseMenu->IsVisible() ? 1 : 0,
						*Region, Primary, *Focused, bHasFocus ? 1 : 0);
				}), 6.58f, false);
			ScheduleDEF0003Capture(
				6.62f,
				bUltrawideInventoryAudit
					? TEXT("Controller_3440x1440_OverviewOpen")
					: TEXT("Controller_OverviewOpen"));

			FTimerHandle ControllerIronCheckHandle;
			GetWorldTimerManager().SetTimer(
				ControllerIronCheckHandle,
				FTimerDelegate::CreateLambda(
					[WeakThis, InitialIron, ControllerInputPassed,
						InventoryOpenedPassed,
						ControllerInventoryViewportWidth,
						ControllerInventoryViewportHeight,
						bUltrawideInventoryAudit]()
				{
					if (!WeakThis.IsValid() || !WeakThis->GetWorld())
					{
						*ControllerInputPassed = false;
						UE_LOG(LogRedPlayerCharacter, Error,
							TEXT("RED_DEF0004_CONTROLLER_IRON_SELECT pass=0 reason=player_or_world_invalid"));
						return;
					}

					APlayerController* PC =
						Cast<APlayerController>(WeakThis->GetController());
					URedPauseMenuWidget* PauseMenu = nullptr;
					for (TObjectIterator<URedPauseMenuWidget> It; It; ++It)
					{
						if (It->GetWorld() == WeakThis->GetWorld()
							&& It->IsInViewport())
						{
							PauseMenu = *It;
							break;
						}
					}
					URedEmbeddedInventoryWidget* Inventory =
						PauseMenu && PauseMenu->WidgetTree
							? PauseMenu->WidgetTree
								->FindWidget<URedEmbeddedInventoryWidget>(
									FName(TEXT("PauseInventoryWidget")))
							: nullptr;
					FString Region;
					int32 Primary = INDEX_NONE;
					int32 Category = INDEX_NONE;
					int32 Visual = INDEX_NONE;
					int32 Stable = INDEX_NONE;
					FString Focused;
					bool bHasFocus = false;
					const bool bState = PauseMenu
						&& PauseMenu->GetControllerInventoryState(
							Region, Primary, Category, Visual, Stable,
							Focused, bHasFocus);
					const FString Name = Inventory && Inventory->ItemNameText
						? Inventory->ItemNameText->GetText().ToString()
						: TEXT("missing");
					const FString Rarity =
						Inventory && Inventory->RarityLabelText
						? Inventory->RarityLabelText->GetText().ToString()
						: TEXT("missing");
					const FString Description =
						Inventory && Inventory->ItemDescriptionText
						? Inventory->ItemDescriptionText->GetText().ToString()
						: TEXT("missing");
					int32 ViewportWidth = 0;
					int32 ViewportHeight = 0;
					if (PC)
					{
						PC->GetViewportSize(ViewportWidth, ViewportHeight);
					}
					*InventoryOpenedPassed = PauseMenu
						&& PauseMenu->IsVisible() && Inventory && bState
						&& WeakThis->ResStone == 0
						&& *InitialIron == 0
						&& WeakThis->ResCrystal == 0
						&& Region == TEXT("InventoryGrid")
						&& Primary == 3
						&& Category
							== static_cast<int32>(
								EVibeMMOInventoryCategory::Resources)
						&& Visual == 1 && Stable == 3
						&& Focused == TEXT("InventorySlotButton_1")
						&& bHasFocus
						&& Inventory->GetInventoryCategory()
							== EVibeMMOInventoryCategory::Resources
						&& Inventory->GetSelectedInventoryItemIndex() == 3
						&& Name == TEXT("IRON")
						&& Rarity == FString::Printf(
							TEXT("STORED: %d"), *InitialIron)
						&& Description.Contains(TEXT("Metallic ore"))
						&& ViewportWidth == ControllerInventoryViewportWidth
						&& ViewportHeight == ControllerInventoryViewportHeight;
					*ControllerInputPassed &= *InventoryOpenedPassed;
					UE_LOG(LogRedPlayerCharacter, Display,
						TEXT("RED_DEF0004_CONTROLLER_IRON_SELECT pass=%d viewport=%dx%d expectedViewport=%dx%d ultrawideInventoryAudit=%d visible=%d region=%s primary=%d category=%d visual=%d stable=%d focused=%s hasFocus=%d activeCategory=%d selected=%d name=\"%s\" rarity=\"%s\" description=\"%s\" provenance=synthetic_engine_controller_callback physicalControllerTested=0"),
						*InventoryOpenedPassed ? 1 : 0,
						ViewportWidth, ViewportHeight,
						ControllerInventoryViewportWidth,
						ControllerInventoryViewportHeight,
						bUltrawideInventoryAudit ? 1 : 0,
						PauseMenu && PauseMenu->IsVisible() ? 1 : 0,
						*Region, Primary, Category, Visual, Stable,
						*Focused, bHasFocus ? 1 : 0,
						Inventory
							? static_cast<int32>(
								Inventory->GetInventoryCategory())
							: INDEX_NONE,
						Inventory
							? Inventory->GetSelectedInventoryItemIndex()
							: INDEX_NONE,
						*Name.ReplaceCharWithEscapedChar(),
						*Rarity.ReplaceCharWithEscapedChar(),
						*Description.ReplaceCharWithEscapedChar());
				}), 9.00f, false);
			ScheduleDEF0003Capture(
				9.08f,
				bUltrawideInventoryAudit
					? TEXT("Controller_3440x1440_Resources_Iron0_Selected")
					: TEXT("Controller_Resources_Iron0_Selected"));
		}

		FTimerHandle SetupHandle;
		GetWorldTimerManager().SetTimer(SetupHandle,
			FTimerDelegate::CreateLambda(
				[WeakThis, AuditAsteroid, AuditCamera, InitialIron, SetupPassed]()
			{
				if (!WeakThis.IsValid() || !WeakThis->GetWorld())
				{
					UE_LOG(LogRedPlayerCharacter, Error,
						TEXT("RED_DEF0003_SETUP_FAIL reason=player_or_world_invalid"));
					return;
				}

				FVector PlanetCenter = FVector::ZeroVector;
				float DatumRadius = 0.f;
				float PeakRadius = 0.f;
				if (!RedGravity::FindMeshPlanet(
						WeakThis->GetWorld(), PlanetCenter, DatumRadius, &PeakRadius)
					|| DatumRadius <= 0.f || PeakRadius < DatumRadius)
				{
					UE_LOG(LogRedPlayerCharacter, Error,
						TEXT("RED_DEF0003_SETUP_FAIL reason=planet_frame"));
					return;
				}
				const float SurfaceRadius = (DatumRadius + PeakRadius) * 0.5f;
				const FVector PawnLocation = WeakThis->GetActorLocation();
				FVector Up = (PawnLocation - PlanetCenter).GetSafeNormal();
				if (Up.IsNearlyZero())
				{
					Up = WeakThis->GetActorUpVector().GetSafeNormal();
				}
				if (Up.IsNearlyZero())
				{
					Up = FVector::UpVector;
				}
				FVector Forward = WeakThis->Camera
					? WeakThis->Camera->GetForwardVector() : WeakThis->GetActorForwardVector();
				Forward = FVector::VectorPlaneProject(Forward, Up).GetSafeNormal();
				if (Forward.IsNearlyZero())
				{
					Forward = FVector::CrossProduct(Up, FVector::RightVector).GetSafeNormal();
				}
				if (Forward.IsNearlyZero())
				{
					Forward = FVector::ForwardVector;
				}

				const float TargetAltitudeCm =
					(RedPlanetPresentationTuning::DeepSpaceAsteroidInnerAltitudeCm
						+ RedPlanetPresentationTuning::DeepSpaceAsteroidOuterAltitudeCm)
					* 0.5f;
				const FVector AsteroidLocation =
					PlanetCenter + Up * (SurfaceRadius + TargetAltitudeCm);
				const FVector CameraLocation = AsteroidLocation - Forward * 50000.f;
				const FRotator CameraRotation = (AsteroidLocation - CameraLocation).Rotation();
				const FTransform AsteroidTransform(
					CameraRotation, AsteroidLocation, FVector(1.f));

				FActorSpawnParameters CameraParameters;
				CameraParameters.Name = TEXT("RedDEF0003AuditCamera");
				CameraParameters.ObjectFlags |= RF_Transient;
				ACameraActor* CameraActor = WeakThis->GetWorld()->SpawnActor<ACameraActor>(
					CameraLocation, CameraRotation, CameraParameters);
				if (!CameraActor)
				{
					UE_LOG(LogRedPlayerCharacter, Error,
						TEXT("RED_DEF0003_SETUP_FAIL reason=camera_spawn"));
					return;
				}
				CameraActor->GetCameraComponent()->SetFieldOfView(52.f);

				ARedMineableAsteroid* Asteroid =
					WeakThis->GetWorld()->SpawnActorDeferred<ARedMineableAsteroid>(
						ARedMineableAsteroid::StaticClass(), AsteroidTransform,
						WeakThis.Get(), WeakThis.Get(),
						ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
				if (!Asteroid)
				{
					CameraActor->Destroy();
					UE_LOG(LogRedPlayerCharacter, Error,
						TEXT("RED_DEF0003_SETUP_FAIL reason=asteroid_spawn"));
					return;
				}
				Asteroid->SetFlags(RF_Transient);
				Asteroid->Tags.Add(TEXT("RedDEF0003AuditAsteroid"));
				Asteroid->OreCapacity = 18.f;
				Asteroid->DepletionPresentationSeconds = 2.f;
				Asteroid->DepletionRewardType = ERedResourceType::Iron;
				Asteroid->DepletionRewardAmount = 6;
				UGameplayStatics::FinishSpawningActor(Asteroid, AsteroidTransform);
				Asteroid->SetPresentationCullDistance(
					RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm);

				FVector BoundsOrigin;
				FVector BoundsExtent;
				Asteroid->GetActorBounds(false, BoundsOrigin, BoundsExtent, true);
				const float FramingRadius = FMath::Max(1.f, BoundsExtent.Size());
				const float FramingDistance = FMath::Clamp(
					FramingRadius * 10.f,
					35000.f,
					RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm * 0.25f);
				const FVector FramedCameraLocation =
					BoundsOrigin - Forward * FramingDistance + Up * (FramingRadius * 0.20f);
				const FRotator FramedCameraRotation =
					(BoundsOrigin - FramedCameraLocation).Rotation();
				CameraActor->SetActorLocationAndRotation(
					FramedCameraLocation, FramedCameraRotation, false, nullptr,
					ETeleportType::TeleportPhysics);
				const float TargetAltitudeMeasuredCm =
					FVector::Distance(Asteroid->GetActorLocation(), PlanetCenter)
						- SurfaceRadius;
				const float CameraAltitudeCm =
					FVector::Distance(FramedCameraLocation, PlanetCenter)
						- SurfaceRadius;
				const float CameraDistanceCm =
					FVector::Distance(FramedCameraLocation, BoundsOrigin);
				const float AngularDiameterDegrees = FMath::RadiansToDegrees(
					2.f * FMath::Atan2(FramingRadius, CameraDistanceCm));

				*AuditAsteroid = Asteroid;
				*AuditCamera = CameraActor;
				*InitialIron = WeakThis->ResIron;
				if (APlayerController* PC = Cast<APlayerController>(WeakThis->GetController()))
				{
					PC->SetViewTarget(CameraActor);
					PC->SetIgnoreMoveInput(true);
					PC->SetIgnoreLookInput(true);
				}
				if (UCharacterMovementComponent* Movement =
					WeakThis->GetCharacterMovement())
				{
					Movement->StopMovementImmediately();
					Movement->DisableMovement();
				}

				*SetupPassed = Asteroid->HasActorBegunPlay()
					&& Asteroid->OreRemaining == 18.f
					&& Asteroid->DepletionPresentationSeconds == 2.f
					&& Asteroid->GetActorScale3D().Equals(FVector(1.f), 0.001f)
					&& !Asteroid->ActorHasTag(TEXT("RedMarsMineableBelt"))
					&& TargetAltitudeMeasuredCm
						>= RedPlanetPresentationTuning::DeepSpaceAsteroidInnerAltitudeCm
							- 1.f
					&& TargetAltitudeMeasuredCm
						<= RedPlanetPresentationTuning::DeepSpaceAsteroidOuterAltitudeCm
							+ 1.f
					&& CameraAltitudeCm
						>= RedPlanetPresentationTuning::SpaceTransitionAltitudeCm
					&& FMath::IsNearlyEqual(
						Asteroid->GetPresentationCullDistance(),
						RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm,
						1.f)
					&& CameraDistanceCm
						< RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm
					&& AngularDiameterDegrees >= 3.f
					&& AngularDiameterDegrees <= 14.f;
				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("RED_DEF0003_SETUP pass=%d asteroid=%s staticMesh=%s voxel=0 ore=%.0f delay=%.2f location=%s targetAltitudeKm=%.3f cameraAltitudeKm=%.3f spaceTransitionKm=%.3f bounds=%s framingRadius=%.0f cameraDistance=%.0f angularDiameterDeg=%.2f cullKm=%.3f camera=%s"),
					*SetupPassed ? 1 : 0, *GetNameSafe(Asteroid),
					*GetNameSafe(Asteroid->FindComponentByClass<UStaticMeshComponent>()
						? Asteroid->FindComponentByClass<UStaticMeshComponent>()->GetStaticMesh()
						: nullptr),
					Asteroid->OreRemaining, Asteroid->DepletionPresentationSeconds,
					*AsteroidLocation.ToCompactString(),
					TargetAltitudeMeasuredCm * 0.00001f,
					CameraAltitudeCm * 0.00001f,
					RedPlanetPresentationTuning::SpaceTransitionAltitudeCm * 0.00001f,
					*BoundsExtent.ToCompactString(),
					FramingRadius, CameraDistanceCm, AngularDiameterDegrees,
					RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm
						* 0.00001f,
					*FramedCameraLocation.ToCompactString());
			}), 7.0f, false);

		FTimerHandle BeforeAuditHandle;
		GetWorldTimerManager().SetTimer(BeforeAuditHandle,
			FTimerDelegate::CreateLambda(
				[WeakThis, AuditAsteroid, AuditCamera, BeforePassed]()
			{
				if (!WeakThis.IsValid() || !AuditAsteroid->IsValid()
					|| !AuditCamera->IsValid())
				{
					UE_LOG(LogRedPlayerCharacter, Error,
						TEXT("RED_DEF0003_BEFORE_FAIL reason=audit_actor_invalid"));
					return;
				}
				ARedMineableAsteroid* Asteroid = AuditAsteroid->Get();
				FCollisionQueryParams QueryParams(
					SCENE_QUERY_STAT(RedDEF0003BeforeTrace), false, WeakThis.Get());
				FHitResult Hit;
				const FVector Start = AuditCamera->Get()->GetActorLocation();
				const FVector End = Asteroid->GetActorLocation()
					+ (Asteroid->GetActorLocation() - Start).GetSafeNormal() * 2500.f;
				const bool bTraceHit = WeakThis->GetWorld()->LineTraceSingleByChannel(
					Hit, Start, End, ECC_Visibility, QueryParams);
				const bool bTraceExact = bTraceHit && Hit.GetActor() == Asteroid;
				*BeforePassed = Asteroid->GetActorEnableCollision()
					&& !Asteroid->IsHidden()
					&& Asteroid->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Active
					&& bTraceExact;
				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("RED_DEF0003_BEFORE pass=%d collision=%d hidden=%d phase=%d traceExact=%d hit=%s"),
					*BeforePassed ? 1 : 0,
					Asteroid->GetActorEnableCollision() ? 1 : 0,
					Asteroid->IsHidden() ? 1 : 0,
					static_cast<int32>(Asteroid->DepletionState.Phase),
					bTraceExact ? 1 : 0, *GetNameSafe(Hit.GetActor()));
			}), 9.0f, false);

		if (!bControllerInventoryAudit)
		{
			ScheduleDEF0003Capture(9.2f, TEXT("SpaceBefore"));
		}

		FTimerHandle BeginAuditHandle;
		GetWorldTimerManager().SetTimer(BeginAuditHandle,
			FTimerDelegate::CreateLambda(
				[WeakThis, AuditAsteroid, InitialIron, BeginPassed, BeginHUDPassed]()
			{
				if (!WeakThis.IsValid() || !AuditAsteroid->IsValid())
				{
					UE_LOG(LogRedPlayerCharacter, Error,
						TEXT("RED_DEF0003_BEGIN_FAIL reason=audit_actor_invalid"));
					return;
				}
				ARedMineableAsteroid* Asteroid = AuditAsteroid->Get();
				const float Extracted = Asteroid->RegisterMiningHit(1.f, WeakThis.Get());
				const float RejectedExtracted =
					Asteroid->RegisterMiningHit(1.f, WeakThis.Get());
				int32 PreFinishExplosionCount = 0;
				for (TActorIterator<ARedShipExplosionFX> It(WeakThis->GetWorld()); It; ++It)
				{
					ARedShipExplosionFX* Explosion = *It;
					if (!IsValid(Explosion) || Explosion->GetOwner() != Asteroid)
					{
						continue;
					}
					++PreFinishExplosionCount;
				}
				int32 ReceiptCount = 0;
				for (TActorIterator<ARedResourcePickup> It(WeakThis->GetWorld()); It; ++It)
				{
					if (It->GetOwner() == Asteroid
						&& It->ResourceType == ERedResourceType::Iron
						&& It->Amount == 6 && !It->bCollectible)
					{
						++ReceiptCount;
					}
				}
				const bool bRewardExactlyOnce =
					WeakThis->ResIron == *InitialIron + 6;
				*BeginPassed = FMath::IsNearlyEqual(Extracted, 18.f)
					&& FMath::IsNearlyZero(RejectedExtracted)
					&& Asteroid->OreRemaining == 0.f
					&& Asteroid->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Depleting
					&& !Asteroid->GetActorEnableCollision()
					&& !Asteroid->IsHidden()
					&& Asteroid->DepletionState.bRewardSpawned
					&& Asteroid->DepletionState.bRewardGranted
					&& bRewardExactlyOnce
					&& PreFinishExplosionCount == 0
					&& ReceiptCount == 1;
				FString InventoryText = TEXT("unavailable");
				bool bPersistentTallyVisible = true;
				bool bInventoryCachePassed = false;
				FString MiningResultText = TEXT("unavailable");
				bool bMiningResultVisible = false;
				float MiningResultSeconds = 0.0f;
				bool bMiningResultPassed = false;
				if (APlayerController* PC =
						Cast<APlayerController>(WeakThis->GetController());
					PC && PC->IsLocalController())
				{
					if (ARedHUD* ReplacementHUD = Cast<ARedHUD>(PC->GetHUD()))
					{
						bInventoryCachePassed =
							ReplacementHUD->QueryReplacementHUDResources(
								WeakThis->ResStone, WeakThis->ResIron,
								WeakThis->ResCrystal,
								InventoryText,
								bPersistentTallyVisible);
						bMiningResultPassed =
							ReplacementHUD->QueryReplacementHUDMiningResult(
								static_cast<uint8>(ERedResourceType::Iron),
								6,
								MiningResultText,
								bMiningResultVisible,
								MiningResultSeconds);
					}
				}
				*BeginHUDPassed = bInventoryCachePassed
					&& !bPersistentTallyVisible
					&& InventoryText.IsEmpty()
					&& bMiningResultPassed
					&& bMiningResultVisible
					&& MiningResultSeconds > 0.0f;
				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("RED_DEF0003_BEGIN pass=%d extracted=%.0f rejected=%.0f phase=%d collision=%d hidden=%d preFinishExplosions=%d receipts=%d ironBefore=%d ironAfter=%d rewardSpawned=%d rewardGranted=%d inventoryCachePass=%d persistentTallyVisible=%d miningResultPass=%d miningResultVisible=%d miningResultSeconds=%.2f miningResultText=\"%s\""),
					*BeginPassed ? 1 : 0, Extracted, RejectedExtracted,
					static_cast<int32>(Asteroid->DepletionState.Phase),
					Asteroid->GetActorEnableCollision() ? 1 : 0,
					Asteroid->IsHidden() ? 1 : 0,
					PreFinishExplosionCount, ReceiptCount,
					*InitialIron, WeakThis->ResIron,
					Asteroid->DepletionState.bRewardSpawned ? 1 : 0,
					Asteroid->DepletionState.bRewardGranted ? 1 : 0,
					bInventoryCachePassed ? 1 : 0,
					bPersistentTallyVisible ? 1 : 0,
					bMiningResultPassed ? 1 : 0,
					bMiningResultVisible ? 1 : 0,
					MiningResultSeconds,
					*MiningResultText);
			}), 10.5f, false);
		if (!bControllerInventoryAudit)
		{
			ScheduleDEF0003Capture(10.75f, TEXT("SpaceReward"));
		}
		if (bInventoryInteractionAudit)
		{
			FTimerHandle InventoryRefreshHandle;
			GetWorldTimerManager().SetTimer(InventoryRefreshHandle,
				FTimerDelegate::CreateLambda(
					[WeakThis, InitialIron, bControllerInventoryAudit,
						bUltrawideInventoryAudit,
						ControllerInventoryViewportWidth,
						ControllerInventoryViewportHeight,
						ControllerInputPassed, InventoryRefreshPassed]()
				{
					if (!WeakThis.IsValid() || !WeakThis->GetWorld())
					{
						UE_LOG(LogRedPlayerCharacter, Error,
							TEXT("RED_DEF0004_INVENTORY_REFRESH pass=0 reason=player_or_world_invalid"));
						return;
					}

					APlayerController* PC =
						Cast<APlayerController>(WeakThis->GetController());
					ARedHUD* HUD = PC ? Cast<ARedHUD>(PC->GetHUD()) : nullptr;
					URedPauseMenuWidget* PauseMenu = nullptr;
					for (TObjectIterator<URedPauseMenuWidget> It; It; ++It)
					{
						if (It->GetWorld() == WeakThis->GetWorld()
							&& It->IsInViewport())
						{
							PauseMenu = *It;
							break;
						}
					}
					URedEmbeddedInventoryWidget* Inventory =
						PauseMenu && PauseMenu->WidgetTree
							? PauseMenu->WidgetTree
								->FindWidget<URedEmbeddedInventoryWidget>(
									FName(TEXT("PauseInventoryWidget")))
							: nullptr;
					int32 Stone = INDEX_NONE;
					int32 Iron = INDEX_NONE;
					int32 Crystal = INDEX_NONE;
					FString Summary;
					const UTextBlock* StoneCard = Inventory && Inventory->WidgetTree
						? Inventory->WidgetTree->FindWidget<UTextBlock>(
							FName(TEXT("RedStoneQuantity")))
						: nullptr;
					const UTextBlock* IronCard = Inventory && Inventory->WidgetTree
						? Inventory->WidgetTree->FindWidget<UTextBlock>(
							FName(TEXT("RedIronQuantity")))
						: nullptr;
					const UTextBlock* CrystalCard = Inventory && Inventory->WidgetTree
						? Inventory->WidgetTree->FindWidget<UTextBlock>(
							FName(TEXT("RedCrystalQuantity")))
						: nullptr;
					const FString StoneCardText = StoneCard
						? StoneCard->GetText().ToString() : TEXT("missing");
					const FString IronCardText = IronCard
						? IronCard->GetText().ToString() : TEXT("missing");
					const FString CrystalCardText = CrystalCard
						? CrystalCard->GetText().ToString() : TEXT("missing");
					FString PersistentText = TEXT("unavailable");
					bool bPersistentTallyVisible = true;
					const bool bTallyHidden = HUD
						&& HUD->QueryReplacementHUDResources(
							WeakThis->ResStone,
							WeakThis->ResIron,
							WeakThis->ResCrystal,
							PersistentText,
							bPersistentTallyVisible)
						&& PersistentText.IsEmpty()
						&& !bPersistentTallyVisible;
					FString ControllerRegion;
					int32 ControllerPrimary = INDEX_NONE;
					int32 ControllerCategory = INDEX_NONE;
					int32 ControllerVisual = INDEX_NONE;
					int32 ControllerStable = INDEX_NONE;
					FString ControllerFocused;
					bool bControllerHasFocus = false;
					const bool bControllerState = !bControllerInventoryAudit
						|| (PauseMenu
							&& PauseMenu->GetControllerInventoryState(
								ControllerRegion,
								ControllerPrimary,
								ControllerCategory,
								ControllerVisual,
								ControllerStable,
								ControllerFocused,
								bControllerHasFocus));
					int32 ViewportWidth = 0;
					int32 ViewportHeight = 0;
					if (PC)
					{
						PC->GetViewportSize(ViewportWidth, ViewportHeight);
					}
					const FString DetailName =
						Inventory && Inventory->ItemNameText
						? Inventory->ItemNameText->GetText().ToString()
						: TEXT("missing");
					const FString DetailRarity =
						Inventory && Inventory->RarityLabelText
						? Inventory->RarityLabelText->GetText().ToString()
						: TEXT("missing");
					const FString DetailDescription =
						Inventory && Inventory->ItemDescriptionText
						? Inventory->ItemDescriptionText->GetText().ToString()
						: TEXT("missing");
					const bool bResourceTotalsRead = Inventory
						&& Inventory->GetResourceTotals(
							Stone, Iron, Crystal, Summary);
					const bool bControllerSelectionPassed =
						!bControllerInventoryAudit
						|| (bControllerState
							&& Stone == 0
							&& Iron == 6
							&& Crystal == 0
							&& ControllerRegion == TEXT("InventoryGrid")
							&& ControllerPrimary == 3
							&& ControllerCategory
								== static_cast<int32>(
									EVibeMMOInventoryCategory::Resources)
							&& ControllerVisual == 1
							&& ControllerStable == 3
							&& ControllerFocused
								== TEXT("InventorySlotButton_1")
							&& bControllerHasFocus
							&& Inventory
							&& Inventory->GetInventoryCategory()
								== EVibeMMOInventoryCategory::Resources
							&& Inventory->GetSelectedInventoryItemIndex() == 3
							&& DetailName == TEXT("IRON")
							&& ViewportWidth
								== ControllerInventoryViewportWidth
							&& ViewportHeight
								== ControllerInventoryViewportHeight
							&& DetailRarity == FString::Printf(
								TEXT("STORED: %d"), Iron)
							&& DetailDescription.Contains(TEXT("Metallic ore")));
					*InventoryRefreshPassed = PauseMenu
						&& PauseMenu->IsVisible()
						&& Inventory
						&& bResourceTotalsRead
						&& Stone == WeakThis->ResStone
						&& Iron == *InitialIron + 6
						&& Iron == WeakThis->ResIron
						&& Crystal == WeakThis->ResCrystal
						&& StoneCardText == FString::FromInt(Stone)
						&& IronCardText == FString::FromInt(Iron)
						&& CrystalCardText == FString::FromInt(Crystal)
						&& bTallyHidden
						&& bControllerSelectionPassed;
					if (bControllerInventoryAudit)
					{
						*ControllerInputPassed &= *InventoryRefreshPassed;
						UE_LOG(LogRedPlayerCharacter, Display,
							TEXT("RED_DEF0004_CONTROLLER_REFRESH pass=%d viewport=%dx%d expectedViewport=%dx%d ultrawideInventoryAudit=%d region=%s primary=%d category=%d visual=%d stable=%d focused=%s hasFocus=%d activeCategory=%d selected=%d name=\"%s\" rarity=\"%s\" description=\"%s\" cardTexts=\"%s/%s/%s\" provenance=synthetic_engine_controller_callback physicalControllerTested=0"),
							*InventoryRefreshPassed ? 1 : 0,
							ViewportWidth, ViewportHeight,
							ControllerInventoryViewportWidth,
							ControllerInventoryViewportHeight,
							bUltrawideInventoryAudit ? 1 : 0,
							*ControllerRegion, ControllerPrimary,
							ControllerCategory, ControllerVisual,
							ControllerStable, *ControllerFocused,
							bControllerHasFocus ? 1 : 0,
							Inventory
								? static_cast<int32>(
									Inventory->GetInventoryCategory())
								: INDEX_NONE,
							Inventory
								? Inventory->GetSelectedInventoryItemIndex()
								: INDEX_NONE,
							*DetailName.ReplaceCharWithEscapedChar(),
							*DetailRarity.ReplaceCharWithEscapedChar(),
							*DetailDescription.ReplaceCharWithEscapedChar(),
							*StoneCardText.ReplaceCharWithEscapedChar(),
							*IronCardText.ReplaceCharWithEscapedChar(),
							*CrystalCardText.ReplaceCharWithEscapedChar());
					}
					UE_LOG(LogRedPlayerCharacter, Display,
						TEXT("RED_DEF0004_INVENTORY_REFRESH pass=%d visible=%d stone=%d ironBefore=%d ironAfter=%d crystal=%d cardTexts=\"%s/%s/%s\" tallyVisible=%d tallyText=\"%s\" summary=\"%s\""),
						*InventoryRefreshPassed ? 1 : 0,
						PauseMenu && PauseMenu->IsVisible() ? 1 : 0,
						Stone, *InitialIron, Iron, Crystal,
						*StoneCardText.ReplaceCharWithEscapedChar(),
						*IronCardText.ReplaceCharWithEscapedChar(),
						*CrystalCardText.ReplaceCharWithEscapedChar(),
						bPersistentTallyVisible ? 1 : 0,
						*PersistentText.ReplaceCharWithEscapedChar(),
						*Summary.ReplaceCharWithEscapedChar());
				}), 10.90f, false);
			ScheduleDEF0003Capture(
				12.20f,
				bControllerInventoryAudit
					? (bUltrawideInventoryAudit
						? TEXT("Controller_3440x1440_Resources_Iron6_Selected")
						: TEXT("Controller_Resources_Iron6_Selected"))
					: TEXT("InventoryAfterMining"));

			FTimerHandle InventoryCloseHandle;
			GetWorldTimerManager().SetTimer(InventoryCloseHandle,
				FTimerDelegate::CreateLambda(
					[WeakThis, bControllerInventoryAudit,
						bUltrawideInventoryAudit,
						ControllerInventoryViewportWidth,
						ControllerInventoryViewportHeight,
						ControllerInputPassed, InventoryClosedPassed]()
				{
					if (!WeakThis.IsValid() || !WeakThis->GetWorld())
					{
						UE_LOG(LogRedPlayerCharacter, Error,
							TEXT("RED_DEF0004_INVENTORY_CLOSE pass=0 reason=player_or_world_invalid"));
						return;
					}

					APlayerController* PC =
						Cast<APlayerController>(WeakThis->GetController());
					ARedHUD* HUD = PC ? Cast<ARedHUD>(PC->GetHUD()) : nullptr;
					bool bControllerCloseHandled = true;
					bool bControllerCloseReleased = true;
					if (bControllerInventoryAudit)
					{
						bControllerCloseHandled = false;
						bControllerCloseReleased = false;
						if (FSlateApplication::IsInitialized())
						{
							const FModifierKeysState Modifiers;
							const FKeyEvent PressEvent(
								EKeys::Gamepad_FaceButton_Right,
								Modifiers, 0, false, 0, 0);
							bControllerCloseHandled =
								FSlateApplication::Get().ProcessKeyDownEvent(
									PressEvent);
							const FKeyEvent ReleaseEvent(
								EKeys::Gamepad_FaceButton_Right,
								Modifiers, 0, false, 0, 0);
							bControllerCloseReleased =
								FSlateApplication::Get().ProcessKeyUpEvent(
									ReleaseEvent);
						}
					}
					else if (HUD)
					{
						HUD->ClosePauseMenu();
					}
					URedPauseMenuWidget* PauseMenu = nullptr;
					for (TObjectIterator<URedPauseMenuWidget> It; It; ++It)
					{
						if (It->GetWorld() == WeakThis->GetWorld()
							&& It->IsInViewport())
						{
							PauseMenu = *It;
							break;
						}
					}
					FString PersistentText = TEXT("unavailable");
					bool bPersistentTallyVisible = true;
					const bool bTallyHidden = HUD
						&& HUD->QueryReplacementHUDResources(
							WeakThis->ResStone,
							WeakThis->ResIron,
							WeakThis->ResCrystal,
							PersistentText,
							bPersistentTallyVisible)
						&& PersistentText.IsEmpty()
						&& !bPersistentTallyVisible;
					int32 ViewportWidth = 0;
					int32 ViewportHeight = 0;
					if (PC)
					{
						PC->GetViewportSize(ViewportWidth, ViewportHeight);
					}
					*InventoryClosedPassed = PauseMenu
						&& !PauseMenu->IsVisible()
						&& PC
						&& !PC->bShowMouseCursor
						&& bTallyHidden
						&& (!bControllerInventoryAudit
							|| (ViewportWidth
									== ControllerInventoryViewportWidth
								&& ViewportHeight
									== ControllerInventoryViewportHeight));
					if (bControllerInventoryAudit)
					{
						*ControllerInputPassed &= *InventoryClosedPassed;
						UE_LOG(LogRedPlayerCharacter, Display,
							TEXT("RED_DEF0004_CONTROLLER_INPUT seq=14 phase=Close key=%s pressHandled=%d releaseHandled=%d provenance=synthetic_engine_controller_callback physicalControllerTested=0"),
							*EKeys::Gamepad_FaceButton_Right.ToString(),
							bControllerCloseHandled ? 1 : 0,
							bControllerCloseReleased ? 1 : 0);
						UE_LOG(LogRedPlayerCharacter, Display,
							TEXT("RED_DEF0004_CONTROLLER_CLOSE pass=%d viewport=%dx%d expectedViewport=%dx%d ultrawideInventoryAudit=%d visible=%d mouseCursor=%d tallyVisible=%d tallyText=\"%s\" provenance=synthetic_engine_controller_callback physicalControllerTested=0"),
							*InventoryClosedPassed ? 1 : 0,
							ViewportWidth, ViewportHeight,
							ControllerInventoryViewportWidth,
							ControllerInventoryViewportHeight,
							bUltrawideInventoryAudit ? 1 : 0,
							PauseMenu && PauseMenu->IsVisible() ? 1 : 0,
							PC && PC->bShowMouseCursor ? 1 : 0,
							bPersistentTallyVisible ? 1 : 0,
							*PersistentText.ReplaceCharWithEscapedChar());
					}
					UE_LOG(LogRedPlayerCharacter, Display,
						TEXT("RED_DEF0004_INVENTORY_CLOSE pass=%d visible=%d mouseCursor=%d tallyVisible=%d tallyText=\"%s\""),
						*InventoryClosedPassed ? 1 : 0,
						PauseMenu && PauseMenu->IsVisible() ? 1 : 0,
						PC && PC->bShowMouseCursor ? 1 : 0,
						bPersistentTallyVisible ? 1 : 0,
						*PersistentText.ReplaceCharWithEscapedChar());
				}), 13.20f, false);
			ScheduleDEF0003Capture(
				13.50f,
				bControllerInventoryAudit
					? (bUltrawideInventoryAudit
						? TEXT("Controller_3440x1440_Closed")
						: TEXT("Controller_Closed"))
					: TEXT("InventoryClosed"));
		}

		FTimerHandle MidAuditHandle;
		GetWorldTimerManager().SetTimer(MidAuditHandle,
			FTimerDelegate::CreateLambda(
				[WeakThis, AuditAsteroid, AuditCamera, InitialIron, MidPassed]()
			{
				if (!WeakThis.IsValid() || !AuditAsteroid->IsValid()
					|| !AuditCamera->IsValid())
				{
					UE_LOG(LogRedPlayerCharacter, Error,
						TEXT("RED_DEF0003_MID_FAIL reason=audit_actor_invalid"));
					return;
				}
				ARedMineableAsteroid* Asteroid = AuditAsteroid->Get();
				FCollisionQueryParams QueryParams(
					SCENE_QUERY_STAT(RedDEF0003AfterTrace), false, WeakThis.Get());
				FHitResult Hit;
				const FVector Start = AuditCamera->Get()->GetActorLocation();
				const FVector End = Asteroid->GetActorLocation()
					+ (Asteroid->GetActorLocation() - Start).GetSafeNormal() * 2500.f;
				const bool bTraceHit = WeakThis->GetWorld()->LineTraceSingleByChannel(
					Hit, Start, End, ECC_Visibility, QueryParams);
				const bool bInvisibleBlocker = bTraceHit && Hit.GetActor() == Asteroid;
				int32 ReceiptCount = 0;
				for (TActorIterator<ARedResourcePickup> It(WeakThis->GetWorld()); It; ++It)
				{
					if (It->GetOwner() == Asteroid
						&& It->ResourceType == ERedResourceType::Iron
						&& It->Amount == 6 && !It->bCollectible)
					{
						++ReceiptCount;
					}
				}
				*MidPassed = Asteroid->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Depleting
					&& !Asteroid->GetActorEnableCollision()
					&& !bInvisibleBlocker
					&& !Asteroid->IsHidden()
					&& ReceiptCount == 1
					&& WeakThis->ResIron == *InitialIron + 6;
				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("RED_DEF0003_MID pass=%d phase=%d collision=%d hidden=%d invisibleBlocker=%d hit=%s receipts=%d iron=%d"),
					*MidPassed ? 1 : 0,
					static_cast<int32>(Asteroid->DepletionState.Phase),
					Asteroid->GetActorEnableCollision() ? 1 : 0,
					Asteroid->IsHidden() ? 1 : 0,
					bInvisibleBlocker ? 1 : 0, *GetNameSafe(Hit.GetActor()),
					ReceiptCount, WeakThis->ResIron);
			}), 11.75f, false);
		if (!bControllerInventoryAudit)
		{
			ScheduleDEF0003Capture(11.82f, TEXT("SpaceTransition"));
			ScheduleDEF0003Capture(12.72f, TEXT("SpaceExplosion"));
			ScheduleDEF0003Capture(13.1f, TEXT("SpaceDebris"));
		}
		if (bUltrawideReceiptAudit)
		{
			FTimerHandle UltrawideFadeAuditHandle;
			GetWorldTimerManager().SetTimer(UltrawideFadeAuditHandle,
				FTimerDelegate::CreateLambda(
					[WeakThis, UltrawideFadePassed]()
				{
					if (!WeakThis.IsValid())
					{
						UE_LOG(LogRedPlayerCharacter, Error,
							TEXT("RED_DEF0004_ULTRAWIDE_FADE_FAIL reason=player_invalid"));
						return;
					}

					int32 ViewportWidth = 0;
					int32 ViewportHeight = 0;
					FString MiningResultText = TEXT("unavailable");
					bool bMiningResultVisible = false;
					float MiningResultSeconds = 0.0f;
					bool bMiningResultPassed = false;
					if (APlayerController* PC =
							Cast<APlayerController>(WeakThis->GetController());
						PC && PC->IsLocalController())
					{
						PC->GetViewportSize(ViewportWidth, ViewportHeight);
						if (ARedHUD* ReplacementHUD = Cast<ARedHUD>(PC->GetHUD()))
						{
							bMiningResultPassed =
								ReplacementHUD->QueryReplacementHUDMiningResult(
									static_cast<uint8>(ERedResourceType::Iron),
									6,
									MiningResultText,
									bMiningResultVisible,
									MiningResultSeconds);
						}
					}
					const float ViewportAspect = ViewportHeight > 0
						? static_cast<float>(ViewportWidth)
							/ static_cast<float>(ViewportHeight)
						: 0.0f;
					const bool bViewportPassed =
						ViewportWidth == 3440 && ViewportHeight == 1440;
					*UltrawideFadePassed = bViewportPassed
						&& ViewportAspect > 2.30f
						&& bMiningResultPassed
						&& bMiningResultVisible
						&& MiningResultSeconds > 0.0f
						&& MiningResultSeconds < 0.70f
						&& MiningResultText == TEXT("IRON  +6");
					UE_LOG(LogRedPlayerCharacter, Display,
						TEXT("RED_DEF0004_ULTRAWIDE_FADE pass=%d viewport=%dx%d aspect=%.3f hudPass=%d visible=%d secondsRemaining=%.2f text=\"%s\""),
						*UltrawideFadePassed ? 1 : 0,
						ViewportWidth, ViewportHeight, ViewportAspect,
						bMiningResultPassed ? 1 : 0,
						bMiningResultVisible ? 1 : 0,
						MiningResultSeconds,
						*MiningResultText);
				}), 13.40f, false);
			ScheduleDEF0003Capture(13.46f, TEXT("SpaceFade"));
		}

		FTimerHandle FinalAuditHandle;
		GetWorldTimerManager().SetTimer(FinalAuditHandle,
			FTimerDelegate::CreateLambda(
				[WeakThis, AuditAsteroid, InitialIron, SurfacePassed,
					SetupPassed, BeforePassed, BeginPassed, BeginHUDPassed,
					MidPassed, bUltrawideReceiptAudit, UltrawideFadePassed,
					bInventoryInteractionAudit, bControllerInventoryAudit,
					bUltrawideInventoryAudit,
					ControllerInputPassed, InventoryOpenedPassed,
					InventoryRefreshPassed, InventoryClosedPassed,
					CaptureDirectory]()
			{
				if (!WeakThis.IsValid() || !AuditAsteroid->IsValid())
				{
					UE_LOG(LogRedPlayerCharacter, Error,
						TEXT("RED_DEF0003_FINAL_FAIL reason=audit_actor_invalid"));
					return;
				}
				ARedMineableAsteroid* Asteroid = AuditAsteroid->Get();
				const float RejectedAfter =
					Asteroid->RegisterMiningHit(1.f, WeakThis.Get());
				int32 ExplosionCount = 0;
				int32 SimulatingDebris = 0;
				for (TActorIterator<ARedShipExplosionFX> It(WeakThis->GetWorld()); It; ++It)
				{
					ARedShipExplosionFX* Explosion = *It;
					if (!IsValid(Explosion) || Explosion->GetOwner() != Asteroid)
					{
						continue;
					}
					++ExplosionCount;
					TArray<UStaticMeshComponent*> DebrisComponents;
					Explosion->GetComponents<UStaticMeshComponent>(DebrisComponents);
					for (const UStaticMeshComponent* Debris : DebrisComponents)
					{
						if (Debris && Debris->IsSimulatingPhysics())
						{
							++SimulatingDebris;
						}
					}
				}
				int32 ProductionFieldCount = 0;
				int32 PristineProductionMembers = 0;
				for (TActorIterator<ARedMineableAsteroid> It(WeakThis->GetWorld()); It; ++It)
				{
					const ARedMineableAsteroid* FieldMember = *It;
					if (!IsValid(FieldMember)
						|| !FieldMember->ActorHasTag(TEXT("RedMarsMineableBelt")))
					{
						continue;
					}
					++ProductionFieldCount;
					if (FieldMember->DepletionState.Phase
							== ERedMineableAsteroidDepletionPhase::Active
						&& FMath::IsNearlyEqual(
							FieldMember->OreRemaining, FieldMember->OreCapacity)
						&& FMath::IsNearlyEqual(
							FieldMember->GetPresentationCullDistance(),
							RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm,
							1.f))
					{
						++PristineProductionMembers;
					}
				}
				const bool bProductionFieldUnaffected =
					ProductionFieldCount == 24 && PristineProductionMembers == 24;
				const bool bFinalStatePassed =
					Asteroid->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Depleted
					&& !Asteroid->GetActorEnableCollision()
					&& Asteroid->IsHidden()
					&& FMath::IsNearlyZero(RejectedAfter)
					&& WeakThis->ResIron == *InitialIron + 6
					&& ExplosionCount == 1
					&& SimulatingDebris >= 8
					&& bProductionFieldUnaffected;
				WeakThis->UpdateHUDResources();
				FString InventoryText = TEXT("unavailable");
				bool bPersistentTallyVisible = true;
				bool bInventoryCachePassed = false;
				FString MiningResultText = TEXT("unavailable");
				bool bMiningResultVisible = true;
				float MiningResultSeconds = -1.0f;
				bool bMiningResultPassed = false;
				if (APlayerController* PC =
						Cast<APlayerController>(WeakThis->GetController());
					PC && PC->IsLocalController())
				{
					if (ARedHUD* ReplacementHUD = Cast<ARedHUD>(PC->GetHUD()))
					{
						bInventoryCachePassed =
							ReplacementHUD->QueryReplacementHUDResources(
								WeakThis->ResStone, WeakThis->ResIron,
								WeakThis->ResCrystal,
								InventoryText,
								bPersistentTallyVisible);
						bMiningResultPassed =
							ReplacementHUD->QueryReplacementHUDMiningResult(
								static_cast<uint8>(ERedResourceType::Iron),
								6,
								MiningResultText,
								bMiningResultVisible,
								MiningResultSeconds);
					}
				}
				const bool bRuntimePassed = *SurfacePassed
					&& *SetupPassed && *BeforePassed
					&& *BeginPassed && *MidPassed && bFinalStatePassed;
				const bool bAcceptancePassed =
					bRuntimePassed && *BeginHUDPassed
					&& bInventoryCachePassed
					&& !bPersistentTallyVisible
					&& InventoryText.IsEmpty()
					&& bMiningResultPassed
					&& !bMiningResultVisible
					&& MiningResultSeconds <= 0.0f
					&& *UltrawideFadePassed
					&& *ControllerInputPassed
					&& *InventoryOpenedPassed
					&& *InventoryRefreshPassed
					&& *InventoryClosedPassed;
				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("RED_DEF0003_RESULT acceptancePass=%d runtimePass=%d surface=%d setup=%d before=%d begin=%d beginHUD=%d mid=%d final=%d phase=%d collision=%d hidden=%d rejectedAfter=%.0f explosions=%d debris=%d productionField=%d pristineProduction=%d productionUnaffected=%d ironBefore=%d ironAfter=%d inventoryCachePass=%d persistentTallyVisible=%d miningResultPass=%d miningResultVisible=%d miningResultSeconds=%.2f miningResultText=\"%s\" ultrawideAudit=%d ultrawideFade=%d inventoryAudit=%d controllerAudit=%d ultrawideInventoryAudit=%d controllerInput=%d inventoryOpened=%d inventoryRefresh=%d inventoryClosed=%d"),
					bAcceptancePassed ? 1 : 0, bRuntimePassed ? 1 : 0,
					*SurfacePassed ? 1 : 0,
					*SetupPassed ? 1 : 0, *BeforePassed ? 1 : 0,
					*BeginPassed ? 1 : 0, *BeginHUDPassed ? 1 : 0,
					*MidPassed ? 1 : 0,
					bFinalStatePassed ? 1 : 0,
					static_cast<int32>(Asteroid->DepletionState.Phase),
					Asteroid->GetActorEnableCollision() ? 1 : 0,
					Asteroid->IsHidden() ? 1 : 0, RejectedAfter,
					ExplosionCount, SimulatingDebris,
					ProductionFieldCount, PristineProductionMembers,
					bProductionFieldUnaffected ? 1 : 0,
					*InitialIron, WeakThis->ResIron,
					bInventoryCachePassed ? 1 : 0,
					bPersistentTallyVisible ? 1 : 0,
					bMiningResultPassed ? 1 : 0,
					bMiningResultVisible ? 1 : 0,
					MiningResultSeconds,
					*MiningResultText,
					bUltrawideReceiptAudit ? 1 : 0,
					*UltrawideFadePassed ? 1 : 0,
					bInventoryInteractionAudit ? 1 : 0,
					bControllerInventoryAudit ? 1 : 0,
					bUltrawideInventoryAudit ? 1 : 0,
					*ControllerInputPassed ? 1 : 0,
					*InventoryOpenedPassed ? 1 : 0,
					*InventoryRefreshPassed ? 1 : 0,
					*InventoryClosedPassed ? 1 : 0);
				if (bControllerInventoryAudit)
				{
					const FString GraphicsRHI = FApp::GetGraphicsRHI();
					const bool bD3D12 = GraphicsRHI.Contains(
							TEXT("D3D12"), ESearchCase::IgnoreCase)
						|| GraphicsRHI.Contains(
							TEXT("DirectX 12"), ESearchCase::IgnoreCase);
					const FString ControllerCaptureVariant =
						bUltrawideInventoryAudit
							? TEXT("Controller_3440x1440")
							: TEXT("Controller");
					const TArray<FString> RequiredCaptures = {
						FString::Printf(
							TEXT("DEF0003_%s_OverviewOpen.png"),
							*ControllerCaptureVariant),
						FString::Printf(
							TEXT("DEF0003_%s_Resources_Iron0_Selected.png"),
							*ControllerCaptureVariant),
						FString::Printf(
							TEXT("DEF0003_%s_Resources_Iron6_Selected.png"),
							*ControllerCaptureVariant),
						FString::Printf(
							TEXT("DEF0003_%s_Closed.png"),
							*ControllerCaptureVariant)
					};
					bool bCaptureArtifactsPassed = true;
					for (const FString& CaptureName : RequiredCaptures)
					{
						bCaptureArtifactsPassed &=
							IFileManager::Get().FileSize(
								*FPaths::Combine(
									CaptureDirectory, CaptureName))
								> 0;
					}
					int32 ViewportWidth = 0;
					int32 ViewportHeight = 0;
					if (APlayerController* PC =
							Cast<APlayerController>(
								WeakThis->GetController()))
					{
						PC->GetViewportSize(
							ViewportWidth, ViewportHeight);
					}
					const bool bSyntheticRoutePassed =
						*ControllerInputPassed
						&& *InventoryOpenedPassed
						&& *InventoryRefreshPassed
						&& *InventoryClosedPassed;
					const int32 ExpectedViewportWidth =
						bUltrawideInventoryAudit ? 3440 : 1280;
					const int32 ExpectedViewportHeight =
						bUltrawideInventoryAudit ? 1440 : 720;
					const bool bRealGPUArtifactsPassed =
						bD3D12
						&& ViewportWidth == ExpectedViewportWidth
						&& ViewportHeight == ExpectedViewportHeight
						&& bCaptureArtifactsPassed;
					const bool bControllerResultPassed =
						bSyntheticRoutePassed && bRealGPUArtifactsPassed;
					UE_LOG(LogRedPlayerCharacter, Display,
						TEXT("RED_DEF0004_CONTROLLER_RESULT pass=%d syntheticRoutePass=%d realGPUArtifactsPass=%d ultrawideInventoryAudit=%d physicalControllerTested=0 provenance=synthetic_engine_controller_callback injection=FSlateApplication_ProcessKeyDownEvent rhi=\"%s\" viewport=%dx%d expectedViewport=%dx%d captures=%d category=Resources focusedSlot=1 stableItem=3 exactCardText=\"0/6/0\""),
						bControllerResultPassed ? 1 : 0,
						bSyntheticRoutePassed ? 1 : 0,
						bRealGPUArtifactsPassed ? 1 : 0,
						bUltrawideInventoryAudit ? 1 : 0,
						*GraphicsRHI.ReplaceCharWithEscapedChar(),
						ViewportWidth, ViewportHeight,
						ExpectedViewportWidth, ExpectedViewportHeight,
						bCaptureArtifactsPassed ? 1 : 0);
					if (bUltrawideInventoryAudit)
					{
						UE_LOG(LogRedPlayerCharacter, Display,
							TEXT("RED_DEF0004_ULTRAWIDE_INVENTORY_RESULT pass=%d controllerRoutePass=%d realGPUArtifactsPass=%d physicalControllerTested=0 rhi=\"%s\" viewport=%dx%d expectedViewport=3440x1440 captures=%d category=Resources focusedSlot=1 stableItem=3 exactCardText=\"0/6/0\""),
							bControllerResultPassed ? 1 : 0,
							bSyntheticRoutePassed ? 1 : 0,
							bRealGPUArtifactsPassed ? 1 : 0,
							*GraphicsRHI.ReplaceCharWithEscapedChar(),
							ViewportWidth, ViewportHeight,
							bCaptureArtifactsPassed ? 1 : 0);
					}
				}
			}), bUltrawideInventoryAudit ? 15.0f : 14.0f, false);
		if (!bControllerInventoryAudit)
		{
			ScheduleDEF0003Capture(14.2f, TEXT("SpaceAfter"));
		}

		FTimerHandle ExitHandle;
		GetWorldTimerManager().SetTimer(ExitHandle,
			FTimerDelegate::CreateLambda([]()
			{
				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("RED_DEF0003_COMPLETE requesting_clean_exit=1"));
				FPlatformMisc::RequestExit(false);
			}), bUltrawideInventoryAudit ? 16.0f : 15.0f, false);

		UE_LOG(LogRedPlayerCharacter, Display,
			TEXT("RED_DEF0003_ARMED directory=%s surfaceAudit=5.8s surfaceCapture=6.1s deepSpaceSetup=7s spaceBefore=%s hit=10.5s spaceReward=10.75s mid=11.75s spaceExplosion=12.72s ultrawideAudit=%d ultrawideFade=13.40s/13.46s inventoryAudit=%d controllerInventoryAudit=%d ultrawideInventoryAudit=%d inventoryOpen=6.35s adaptiveInventory=7.35s-8.85s controllerIronCheck=9.00s inventoryRefresh=10.90s inventoryCapture=12.00s inventoryClose=13.20s inventoryClosedCapture=13.50s receiptExpired=%s spaceAfter=14.2s exit=%s"),
			*CaptureDirectory,
			bControllerInventoryAudit ? TEXT("9.45s") : TEXT("9.2s"),
			bUltrawideReceiptAudit ? 1 : 0,
			bInventoryInteractionAudit ? 1 : 0,
			bControllerInventoryAudit ? 1 : 0,
			bUltrawideInventoryAudit ? 1 : 0,
			bUltrawideInventoryAudit ? TEXT("15s") : TEXT("14s"),
			bUltrawideInventoryAudit ? TEXT("16s") : TEXT("15s"));
	}
#endif
}

void ARedPlayerCharacter::TryCreateLocalHUD()
{
	if (ActiveHUDWidget || !HUDWidgetClass || GetNetMode() == NM_DedicatedServer
		|| !IsLocallyControlled())
	{
		return;
	}

	APlayerController* PC = Cast<APlayerController>(GetController());
	if (!PC || !PC->IsLocalController())
	{
		return;
	}

	if (AmbientSandFX && AmbientSandFX->GetAsset())
	{
		AmbientSandFX->SetVisibility(true, true);
		AmbientSandFX->Activate(true);
	}

	UVibeMMOHUDWidget* Hud = CreateWidget<UVibeMMOHUDWidget>(PC, HUDWidgetClass);
	if (!Hud)
	{
		return;
	}

	// WBP_VibeMMOHUD may preserve old editor-authored defaults even when the native
	// kit constructor changes.  Clear both mock paths before rebuilding so no demo
	// values, targeting boxes, or placeholder labels can flash over the live HUD.
	Hud->bUseMockValues = false;
	Hud->bUseMockTargetingRectangles = false;
	Hud->RebuildDefaultHUDLayout();
	Hud->AddToViewport(10);
	ActiveHUDWidget = Hud;
	if (ARedHUD* PixelHUD = Cast<ARedHUD>(PC->GetHUD());
		PixelHUD && PixelHUD->HasPixelExactHUD())
	{
		PixelHUD->RegisterLegacyCombatHUD(this, Hud);
		// Preserve the existing gameplay/data backend without allowing its old
		// visuals to cover the supplied pixel-exact art.
		Hud->SetVisibility(ESlateVisibility::Collapsed);
	}
	Hud->OnAbilityLoadoutSwapRequested.AddDynamic(
		this, &ARedPlayerCharacter::HandleAbilityLoadoutSwapRequested);
	Hud->SetWeaponSlotRarity(0, EVibeMMOItemRarity::Epic);
	Hud->SetWeaponSlotRarity(1, EVibeMMOItemRarity::Legendary);
	// Restore the authored weapon-card imagery after the HUD tree rebuild. These cooked textures
	// are paired with the same Epic/Legendary semantic backgrounds above, so imagery never falls
	// back to the temporary ENERGY/RIFLE words or paints the wrong rarity over a slot.
	UTexture2D* WeaponCards[] = { EpicWeaponCardTexture.Get(), LegendaryWeaponCardTexture.Get() };
	for (int32 Slot = 0; Slot < UE_ARRAY_COUNT(WeaponCards); ++Slot)
	{
		if (WeaponCards[Slot])
		{
			Hud->SetWeaponIconResource(Slot, WeaponCards[Slot]);
		}
	}
	Hud->SetSelectedWeaponSlot(CurrentWeaponSlot);
	UpdateHUDStatus();
	UpdateHUDResources();
	Hud->SetMinimapMode(bHUDSpaceMinimapRequested
		? EVibeMMOMinimapMode::Space : EVibeMMOMinimapMode::Surface);

	if (!PortraitRT)
	{
		PortraitRT = NewObject<UTextureRenderTarget2D>(this, TEXT("PortraitRT"));
		PortraitRT->RenderTargetFormat = ETextureRenderTargetFormat::RTF_RGBA8;
		PortraitRT->ClearColor = FLinearColor(0.012f, 0.055f, 0.09f, 1.0f);
		PortraitRT->InitAutoFormat(256, 320);
		PortraitRT->UpdateResourceImmediate(true);
	}
	if (PortraitCapture)
	{
		PortraitCapture->bAlwaysPersistRenderingState = true;
		PortraitCapture->TextureTarget = PortraitRT;
		PortraitCapture->ShowOnlyActors.Reset();
		PortraitCapture->ShowOnlyActors.Add(this);
		PortraitCapture->CaptureScene();
	}
	Hud->SetPortraitResource(PortraitRT);

	if (!MinimapRT)
	{
		MinimapRT = NewObject<UTextureRenderTarget2D>(this, TEXT("MinimapRT"));
		MinimapRT->RenderTargetFormat = ETextureRenderTargetFormat::RTF_RGBA8;
		MinimapRT->InitAutoFormat(512, 512);
		MinimapRT->UpdateResourceImmediate(true);
	}
	if (MinimapCapture)
	{
		MinimapCapture->bAlwaysPersistRenderingState = true;
		MinimapCapture->TextureTarget = MinimapRT;
		MinimapCapture->CaptureScene();
		LastReplacementMinimapCaptureFrameId =
			ResolveReplacementHUDMinimapFrameId();
		bReplacementMinimapSurfaceCaptureFresh =
			!LastReplacementMinimapCaptureFrameId.IsNone();
	}
	Hud->SetMinimapResource(MinimapRT);
	RefreshReplacementHUDMinimapPresentation();

	GetWorldTimerManager().SetTimer(
		HudCaptureTimer, this, &ARedPlayerCharacter::RefreshHudCaptures, 0.15f, true);
	RefreshAbilityLoadoutForWeapon();
}

void ARedPlayerCharacter::DestroyLocalHUD()
{
	CloseAbilityLoadout();
	GetWorldTimerManager().ClearTimer(HudCaptureTimer);
	if (ActiveHUDWidget)
	{
		if (APlayerController* PC = ActiveHUDWidget->GetOwningPlayer())
		{
			if (ARedHUD* PixelHUD = Cast<ARedHUD>(PC->GetHUD()))
			{
				PixelHUD->UnregisterLegacyCombatHUD(this, ActiveHUDWidget);
			}
		}
		ActiveHUDWidget->RemoveFromParent();
		ActiveHUDWidget = nullptr;
	}
	if (PortraitCapture)
	{
		PortraitCapture->TextureTarget = nullptr;
	}
	if (MinimapCapture)
	{
		MinimapCapture->TextureTarget = nullptr;
	}
	PortraitRT = nullptr;
	MinimapRT = nullptr;
	LastReplacementMinimapCaptureFrameId = NAME_None;
	bReplacementMinimapSurfaceCaptureFresh = false;
}

void ARedPlayerCharacter::PawnClientRestart()
{
	Super::PawnClientRestart();
	TryCreateLocalHUD();
	UpdateHUDResources();
}

void ARedPlayerCharacter::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	// A mid-grapple disconnect/despawn must not leave the world-owned projectile head alive.
	// Release the authority reservation as well, otherwise the target can remain ungrappleable.
	if (HasAuthority() && IsValid(GrappleTarget) && GrappleTarget->GrappledBy.Get() == this)
	{
		GrappleTarget->GrappledBy.Reset();
	}
	bGrappling = false;
	GrappleTarget = nullptr;
	SetGrappleRope(false);
	DestroyLocalHUD();
	PredictedFireMuzzles.Reset();
	PredictedFireDirections.Reset();
	if (JetpackThrustAudio)
	{
		JetpackThrustAudio->Stop();
	}
	Super::EndPlay(EndPlayReason);
}

bool ARedPlayerCharacter::FindPlanetSurfaceBelow(FVector& OutLocation, FVector& OutNormal) const
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return false;
	}

	const FVector Location = GetActorLocation();
	FVector MeshPlanetCenter = FVector::ZeroVector;
	float MeshPlanetDatumRadius = 0.f;
	float MeshPlanetPeakRadius = 0.f;
	const bool bHasMeshPlanet = RedGravity::FindMeshPlanet(
		World, MeshPlanetCenter, MeshPlanetDatumRadius, &MeshPlanetPeakRadius);

	// Secondary gravity bodies (the physical moon) must use their actual collision surface.
	// The home-planet startup path below deliberately carries a 6.5m cook clearance; applying
	// that clearance to the moon made the player appear to run roughly 9-10m above its mesh.
	FVector DominantCenter = FVector::ZeroVector;
	float DominantSurfaceRadius = 0.f;
	const bool bHasDominantBody = RedGravity::QueryDominantBody(
		World, Location, DominantCenter, DominantSurfaceRadius);
	const bool bOnSecondaryBody = bHasDominantBody && DominantSurfaceRadius > 0.f
		&& (!bHasMeshPlanet || !DominantCenter.Equals(MeshPlanetCenter, 1000.f));
	if (bOnSecondaryBody)
	{
		FVector BodyUp = (Location - DominantCenter).GetSafeNormal();
		if (BodyUp.IsNearlyZero()) { BodyUp = FVector::UpVector; }
		const float CapsuleHalfHeight = GetCapsuleComponent()
			? GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 96.f;
		FCollisionObjectQueryParams BodyObjects;
		BodyObjects.AddObjectTypesToQuery(ECC_WorldStatic);
		BodyObjects.AddObjectTypesToQuery(ECC_WorldDynamic);
		FCollisionQueryParams BodyQuery(SCENE_QUERY_STAT(RedSecondaryBodySurfaceSnap), true, this);
		TArray<FHitResult> BodyHits;
		const FVector TraceStart = DominantCenter + BodyUp * (DominantSurfaceRadius + 50000.f);
		const FVector TraceEnd = DominantCenter + BodyUp * FMath::Max(100.f, DominantSurfaceRadius - 50000.f);
		World->LineTraceMultiByObjectType(BodyHits, TraceStart, TraceEnd, BodyObjects, BodyQuery);
		for (const FHitResult& BodyHit : BodyHits)
		{
			const UPrimitiveComponent* HitComponent = BodyHit.GetComponent();
			if (!BodyHit.bBlockingHit || !HitComponent
				|| (!HitComponent->ComponentHasTag(TEXT("RedGravityBody.Moon"))
					&& !HitComponent->ComponentHasTag(TEXT("RedGravityBody.PlayableRingMoon"))))
			{
				continue;
			}
			OutNormal = (BodyHit.ImpactPoint - DominantCenter).GetSafeNormal();
			if (OutNormal.IsNearlyZero()) { OutNormal = BodyUp; }
			OutLocation = BodyHit.ImpactPoint + OutNormal * (CapsuleHalfHeight + 2.f);
			return true;
		}
		// Collision may be one frame late after replication. The exact scenery radius is still a
		// substantially better temporary rest point than the home-planet cook clearance.
		OutNormal = BodyUp;
		OutLocation = DominantCenter + BodyUp * (DominantSurfaceRadius + CapsuleHalfHeight + 2.f);
		return true;
	}

	const ARedPlanetPresentationController* PlanetController = nullptr;
	if (!bHasMeshPlanet)
	{
		for (TActorIterator<ARedPlanetPresentationController> It(World); It; ++It)
		{
			if (IsValid(*It))
			{
				PlanetController = *It;
				break;
			}
		}
	}

	FVector Up = FVector::UpVector;
	if (bHasMeshPlanet)
	{
		Up = (Location - MeshPlanetCenter).GetSafeNormal();
	}
	else if (PlanetController)
	{
		Up = PlanetController->GetSurfaceNormalAt(Location);
	}
	else
	{
		Up = RedGravity::UpAt(World, Location,
			Location.IsNearlyZero() ? FVector::UpVector : Location.GetSafeNormal());
	}
	if (Up.IsNearlyZero())
	{
		Up = FVector::UpVector;
	}
	const float CapsuleHalfHeight = GetCapsuleComponent() ? GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 96.0f;
	constexpr float SurfaceClearance = 650.0f;

	if (PlanetController)
	{
		// The generated planet uses visual/orbit shells that can report collision above the
		// playable radius. Trust the planet controller for pawn placement so PIE always starts
		// on the intended gameplay surface.
		OutNormal = Up;
		OutLocation = PlanetController->GetSurfaceLocationForActor(Location, CapsuleHalfHeight, SurfaceClearance);
		return true;
	}

	constexpr float ProbeAbove = 12000.0f;
	constexpr float ProbeBelow = 350000.0f;

	FHitResult Hit;
	// For PlanetGen, always cast from above its authored terrain envelope down to the underground
	// datum. This also recovers a pawn left near the old 382 km controller shell without ever using
	// that shell as a valid destination. Legacy/flat probes retain their local trace range.
	const FVector Start = bHasMeshPlanet
		? MeshPlanetCenter + Up * (MeshPlanetPeakRadius + ProbeAbove)
		: Location + Up * ProbeAbove;
	const FVector End = bHasMeshPlanet
		? MeshPlanetCenter + Up * FMath::Max(1000.0f, MeshPlanetDatumRadius - 5000.0f)
		: Location - Up * ProbeBelow;
	FCollisionObjectQueryParams ObjectParams;
	ObjectParams.AddObjectTypesToQuery(ECC_WorldStatic);
	ObjectParams.AddObjectTypesToQuery(ECC_WorldDynamic);
	FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(RedPlanetSurfaceSnap), false, this);
	// PlanetGen chunks expose async-cooked procedural triangle collision. Complex
	// traces are required to hit that surface; flat/legacy maps keep simple traces.
	QueryParams.bTraceComplex = bHasMeshPlanet;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		AActor* Actor = *It;
		if (!IsValid(Actor))
		{
			continue;
		}
		if (Actor->IsA<APawn>() || (bHasMeshPlanet && !IsPlayerPlanetGenTerrainActor(Actor)))
		{
			QueryParams.AddIgnoredActor(Actor);
			continue;
		}

		FString ActorName = Actor->GetName();
#if WITH_EDITOR
		ActorName += TEXT(" ");
		ActorName += Actor->GetActorLabel();
#endif
		if (ActorName.Contains(TEXT("Vibe_Horizon")) ||
			ActorName.Contains(TEXT("Vibe_Orbit")) ||
			ActorName.Contains(TEXT("Vibe_PlanetOrbitProxy")) ||
			ActorName.Contains(TEXT("Vibe_PlanetAtmosphere")) ||
			ActorName.Contains(TEXT("Vibe_PlanetCloudBands")) ||
			ActorName.Contains(TEXT("Vibe_CleanStylizedSky")) ||
			ActorName.Contains(TEXT("Vibe_PlanetSkyAtmosphere")) ||
			ActorName.Contains(TEXT("Vibe_PlanetVolumetricClouds")) ||
			ActorName.Contains(TEXT("BP_StylizedSky_Lite")) ||
			ActorName.Contains(TEXT("SkyDome")) ||
			ActorName.Contains(TEXT("StylizedSky")))
		{
			QueryParams.AddIgnoredActor(Actor);
		}
	}

	bool bFoundSurfaceHit = false;
	if (bHasMeshPlanet)
	{
		// PlanetGen's async-cooked procedural mesh is reliably queryable through the complex
		// Visibility path (the same path used by UE's official SceneTools.trace_world). All
		// non-PlanetGen actors were ignored above, so the first blocker is the local terrain chunk.
		bFoundSurfaceHit = World->LineTraceSingleByChannel(
			Hit, Start, End, ECC_Visibility, QueryParams)
			&& Hit.bBlockingHit
			&& IsPlayerPlanetGenTerrainHit(Hit);
		if (bFoundSurfaceHit)
		{
			const float HitRadius = FVector::Dist(Hit.ImpactPoint, MeshPlanetCenter);
			bFoundSurfaceHit = HitRadius >= MeshPlanetDatumRadius - 5000.0f
				&& HitRadius <= MeshPlanetPeakRadius + 5000.0f;
		}

		// A freshly created async procedural body can temporarily be absent from the world's broadphase
		// even after its cooked triangle body is valid. Query the known PlanetGen chunk components
		// directly as a narrow fallback so startup does not depend on that registration window.
		if (!bFoundSurfaceHit)
		{
			float OutermostRadius = -1.0f;
			for (TActorIterator<AActor> It(World); It; ++It)
			{
				AActor* TerrainActor = *It;
				if (!IsValid(TerrainActor) || !IsPlayerPlanetGenTerrainActor(TerrainActor))
				{
					continue;
				}

				TInlineComponentArray<UPrimitiveComponent*> PrimitiveComponents(TerrainActor);
				for (UPrimitiveComponent* Primitive : PrimitiveComponents)
				{
					if (!IsValid(Primitive) || !Primitive->IsQueryCollisionEnabled())
					{
						continue;
					}

					FString ComponentIdentity = GetNameSafe(Primitive);
					ComponentIdentity += TEXT(" ");
					ComponentIdentity += Primitive->GetClass()->GetName();
					ComponentIdentity.ToLowerInline();
					if (!ComponentIdentity.Contains(TEXT("proceduralmesh"))
						&& !ComponentIdentity.Contains(TEXT("dynamicmesh"))
						&& !ComponentIdentity.Contains(TEXT("terrainchunk"))
						&& !ComponentIdentity.Contains(TEXT("planetchunk")))
					{
						continue;
					}

					FHitResult Candidate;
					if (!Primitive->LineTraceComponent(Candidate, Start, End, QueryParams))
					{
						continue;
					}
					const float CandidateRadius = FVector::Dist(Candidate.ImpactPoint, MeshPlanetCenter);
					if (CandidateRadius < MeshPlanetDatumRadius - 5000.0f
						|| CandidateRadius > MeshPlanetPeakRadius + 5000.0f
						|| CandidateRadius <= OutermostRadius)
					{
						continue;
					}

					Hit = Candidate;
					OutermostRadius = CandidateRadius;
					bFoundSurfaceHit = true;
				}
			}
		}
	}
	else
	{
		bFoundSurfaceHit = World->LineTraceSingleByObjectType(Hit, Start, End, ObjectParams, QueryParams)
			&& Hit.bBlockingHit;
	}

	if (bFoundSurfaceHit)
	{
		// Body/surface up = SMOOTH radial direction (planet center -> point), NOT the bumpy voxel
		// triangle normal -- the raw hit normal jitters frame-to-frame and the 0.1s snap timer was
		// hard-setting the body to it 10x/sec, so the whole body rocked ("running on marbles").
		// The LOCATION still comes from the real hit point below, so the body still follows terrain height.
		OutNormal = bHasMeshPlanet
			? (Hit.ImpactPoint - MeshPlanetCenter).GetSafeNormal()
			: Hit.ImpactNormal.GetSafeNormal();
		if (OutNormal.IsNearlyZero() || FVector::DotProduct(OutNormal, Up) < 0.2f)
		{
			OutNormal = Up;
		}
		OutLocation = Hit.ImpactPoint + OutNormal * (CapsuleHalfHeight + SurfaceClearance);
		return true;
	}

	return false;
}

void ARedPlayerCharacter::TrySnapToPlanetSurface()
{
	UCharacterMovementComponent* Movement = GetCharacterMovement();
	if (GetLocalRole() == ROLE_SimulatedProxy || bDowned || GetAttachParentActor() != nullptr
		|| (Movement && Movement->MovementMode == MOVE_None))
	{
		GetWorldTimerManager().ClearTimer(SurfaceSnapRetryTimer);
		return;
	}
	// During an orbital drop / skydive the pawn is SUPPOSED to be falling from altitude — never snap it
	// to the ground. On a low drop the surface is within trace range, so the spawn-time snap would
	// teleport the diver straight down and kill the dive (this defeated the whole drop below ~3 km).
	if (bOrbitalDropActive || bSkydiving)
	{
		GetWorldTimerManager().ClearTimer(SurfaceSnapRetryTimer);
		return;
	}

	FVector SurfaceLocation = FVector::ZeroVector;
	FVector SurfaceNormal = FVector::UpVector;
	const bool bFoundSurface = FindPlanetSurfaceBelow(SurfaceLocation, SurfaceNormal);
	if (!bFoundSurface)
	{
		// PlanetGen builds terrain and async-cooks procedural collision after play starts. Hold the
		// pawn just outside the authored terrain envelope until its local chunk is queryable, rather
		// than allowing it to fall through an uncooked surface and eventually abandoning the retry.
		FVector PlanetCenter = FVector::ZeroVector;
		float DatumRadius = 0.0f;
		float PeakRadius = 0.0f;
		if (RedGravity::FindMeshPlanet(GetWorld(), PlanetCenter, DatumRadius, &PeakRadius))
		{
			FVector WaitingUp = (GetActorLocation() - PlanetCenter).GetSafeNormal();
			if (WaitingUp.IsNearlyZero())
			{
				WaitingUp = FVector::UpVector;
			}
			const FVector WaitingLocation = PlanetCenter + WaitingUp * (PeakRadius + 5000.0f);
			SetActorLocation(WaitingLocation, false, nullptr, ETeleportType::TeleportPhysics);
			if (Movement)
			{
				Movement->Velocity = FVector::ZeroVector;
			}
			SurfaceSnapAttemptsRemaining = 80;
			return;
		}

		if (--SurfaceSnapAttemptsRemaining <= 0)
		{
			GetWorldTimerManager().ClearTimer(SurfaceSnapRetryTimer);
			UE_LOG(LogRedPlayerCharacter, Warning, TEXT("Surface snap gave up for %s at %s; no PlanetGen terrain hit under pawn."),
				*GetNameSafe(this),
				*GetActorLocation().ToCompactString());
		}
		return;
	}

	SurfaceSnapAttemptsRemaining = 80;
	// Once the pawn is grounded + walking near the surface, STOP this 0.1s re-snap. Continuing to
	// teleport the pawn onto the smooth sphere surface 10x/sec while it runs over bumpy terrain is the
	// "running on marbles" bob. The movement component's own per-tick surface snap keeps it grounded
	// from here; this timer only exists to land the pawn at spawn.
	if (GetCharacterMovement() && GetCharacterMovement()->MovementMode == MOVE_Walking
		&& FVector::Dist(GetActorLocation(), SurfaceLocation) < 200.0f)
	{
		GetWorldTimerManager().ClearTimer(SurfaceSnapRetryTimer);
		return;
	}
	const float DistanceToTarget = FVector::Dist(GetActorLocation(), SurfaceLocation);
	if (DistanceToTarget > 1.0f)
	{
		const FVector StableUp = SurfaceNormal.IsNearlyZero() ? FVector::UpVector : SurfaceNormal.GetSafeNormal();
		const FVector TangentVelocity = FVector::VectorPlaneProject(GetVelocity(), StableUp);
		SetActorLocation(SurfaceLocation, false, nullptr, ETeleportType::TeleportPhysics);
		// Preserve the body's CURRENT facing during the periodic re-snap — only re-level UP to the
		// surface. Using the camera here re-yawed the body toward the camera 10x/sec, and as the
		// radial up shifts while running, that yaw jittered = head/upper-body bobbing back and forth.
		// The smooth body-turn (bShouldTurnBody, below) is what faces the camera; the snap must not fight it.
		FVector TangentForward = FVector::VectorPlaneProject(GetActorForwardVector(), StableUp).GetSafeNormal();
		if (!TangentForward.IsNearlyZero())
		{
			SetActorRotation(FRotationMatrix::MakeFromZX(StableUp, TangentForward).Rotator(), ETeleportType::TeleportPhysics);
		}
		if (UCharacterMovementComponent* CMC = GetCharacterMovement())
		{
			CMC->Velocity = TangentVelocity;
			CMC->SetMovementMode(MOVE_Walking);
		}
		UE_LOG(LogRedPlayerCharacter, Display, TEXT("Surface snap %s -> %s Delta=%.1f Normal=%s"),
			*GetNameSafe(this),
			*SurfaceLocation.ToCompactString(),
			DistanceToTarget,
			*SurfaceNormal.ToCompactString());
	}

	if (DistanceToTarget <= 25.0f)
	{
		GetWorldTimerManager().ClearTimer(SurfaceSnapRetryTimer);
	}
}

void ARedPlayerCharacter::SnapToPlanetSurfaceNow()
{
	SurfaceSnapAttemptsRemaining = 80;

	// This is called after a teleport (notably exiting the ship, possibly on the FAR side of the
	// planet). Two things must be reset or the camera flips + shakes:
	//  1) Clear the gravity rebase's stored "up" so it doesn't rebase the control rotation by the
	//     huge one-frame surface-normal delta between the old and new positions.
	//  2) Give the controller a clean upright look direction. Use the RADIAL up derived from the
	//     LOCATION (planet at origin) — never the actor's up, which can still be stale mid-flip.
	if (RadialGravity)
	{
		RadialGravity->ResetRebase();
	}
	if (AController* C = GetController())
	{
		// Radial up from the DOMINANT gravity body (moon-aware); in deep space keep the CURRENT up
		// (matches the movement components' hold-last-body behavior — never snap to origin-radial).
		const FVector Up = RedGravity::UpAt(GetWorld(), GetActorLocation(), GetActorUpVector());
		FVector Fwd = FVector::VectorPlaneProject(GetActorForwardVector(), Up).GetSafeNormal();
		if (Fwd.IsNearlyZero())
		{
			Fwd = FVector::VectorPlaneProject(FVector::ForwardVector, Up).GetSafeNormal();
		}
		if (!Up.IsNearlyZero() && !Fwd.IsNearlyZero())
		{
			C->SetControlRotation(FRotationMatrix::MakeFromZX(Up, Fwd).Rotator());
			// Re-seed the orbit camera to face the body's forward, level with the new surface.
			CameraForward = Fwd;
			CameraPitch = -10.f;
		}
	}

	TrySnapToPlanetSurface();
	GetWorldTimerManager().SetTimer(SurfaceSnapRetryTimer, this, &ARedPlayerCharacter::TrySnapToPlanetSurface, 0.1f, true, 0.05f);
}

void ARedPlayerCharacter::OnBoardedShip(AActor* Ship)
{
	// Stop everything that could fight the ride-along, then attach so our position (and the voxel
	// collision invoker) tracks the ship for the whole flight.
	GetWorldTimerManager().ClearTimer(SurfaceSnapRetryTimer);
	CloseAbilityLoadout();
	StopGrappleInput();
	StopFiring();       // the LMB release goes to the SHIP after possession — never leave rapid-fire running
	bADS = false;
	if (UCharacterMovementComponent* CMC = GetCharacterMovement())
	{
		CMC->StopMovementImmediately();
		CMC->DisableMovement();
	}
	if (RadialGravity)
	{
		RadialGravity->SetComponentTickEnabled(false);
	}
	if (Ship)
	{
		AttachToActor(Ship, FAttachmentTransformRules::KeepWorldTransform);
	}
}

void ARedPlayerCharacter::OnExitedShip(const FVector& ExitLocation, const FVector& SuggestedForward, AActor* IgnoreForTrace,
	bool bSnapToPlanetSurface)
{
	DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);

	// Prefer the ship's up when exiting onto the hull so space / radial landings stay upright on the roof.
	FVector UpHint = GetActorUpVector();
	if (IgnoreForTrace)
	{
		UpHint = IgnoreForTrace->GetActorUpVector();
	}
	const FVector Up = RedGravity::UpAt(GetWorld(), ExitLocation, UpHint);
	FVector Fwd = FVector::VectorPlaneProject(SuggestedForward, Up).GetSafeNormal();
	if (Fwd.IsNearlyZero())
	{
		Fwd = FVector::VectorPlaneProject(FVector::ForwardVector, Up).GetSafeNormal();
	}

	FVector Landing = ExitLocation;
	// Planet ground-snap is for beside-hull RedShip exits only. Shuttle roof exits must NOT
	// trace into the planet — a start point under the mesh / inside the hull was placing the
	// pawn under terrain (far-side / inner-face hit).
	if (bSnapToPlanetSurface)
	{
		if (UWorld* W = GetWorld())
		{
			FCollisionQueryParams Q(SCENE_QUERY_STAT(RedShipExitGround), false, this);
			if (IgnoreForTrace)
			{
				Q.AddIgnoredActor(IgnoreForTrace);
			}
			FHitResult Hit;
			if (W->LineTraceSingleByChannel(Hit, ExitLocation + Up * 2000.f, ExitLocation - Up * 60000.f, ECC_Visibility, Q)
				&& Hit.bBlockingHit)
			{
				const float HalfHeight = GetCapsuleComponent() ? GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 96.f;
				Landing = Hit.ImpactPoint + Up * (HalfHeight + 10.f);
			}
		}
	}

	// Deterministic placement: surface-aligned rotation set together with the location, velocity zeroed.
	SetActorLocationAndRotation(Landing, FRotationMatrix::MakeFromZX(Up, Fwd).ToQuat(), false, nullptr, ETeleportType::TeleportPhysics);
	if (UCharacterMovementComponent* CMC = GetCharacterMovement())
	{
		CMC->StopMovementImmediately();
		CMC->SetGravityDirection(-Up);
		CMC->SetMovementMode(MOVE_Falling);   // the surface snap + radial gravity land us cleanly
	}
	if (URedCharacterMovement* RedCMC = Cast<URedCharacterMovement>(GetCharacterMovement()))
	{
		// The guard radius from the boarding point is meaningless here (same-body flights don't
		// switch bodies, so it never auto-resets): over uncooked terrain it would hold the pawn at
		// the takeoff ground level — inside a hill or high in the air. Fresh-arrival semantics.
		RedCMC->ResetFallGuard();
	}

	// The exit point is beside the hull; if the grounded capsule still touches a wing/skid, the
	// depenetration solver shoves the pawn every tick while it settles ("jiggling on the screen").
	// Ignore the ship for the first moments — by then the pawn stands clear on the ground.
	if (IgnoreForTrace && bSnapToPlanetSurface)
	{
		if (UCapsuleComponent* Cap = GetCapsuleComponent())
		{
			Cap->IgnoreActorWhenMoving(IgnoreForTrace, true);
			TWeakObjectPtr<ARedPlayerCharacter> WeakThis(this);
			TWeakObjectPtr<AActor> WeakShip(IgnoreForTrace);
			GetWorldTimerManager().SetTimer(ShipIgnoreTimer, FTimerDelegate::CreateLambda([WeakThis, WeakShip]()
			{
				if (WeakThis.IsValid() && WeakShip.IsValid())
				{
					if (UCapsuleComponent* C = WeakThis->GetCapsuleComponent())
					{
						C->IgnoreActorWhenMoving(WeakShip.Get(), false);
					}
				}
			}), 2.0f, false);
		}
	}
	if (RadialGravity)
	{
		RadialGravity->SetComponentTickEnabled(true);
		RadialGravity->ResetRebase();
	}
}

void ARedPlayerCharacter::SetPilotCaptureOnly(bool bCaptureOnly)
{
	TArray<UPrimitiveComponent*> Prims;
	GetComponents<UPrimitiveComponent>(Prims);
	for (UPrimitiveComponent* Prim : Prims)
	{
		if (Prim && (Prim->IsA<USkeletalMeshComponent>() || Prim->IsA<UStaticMeshComponent>()))
		{
			Prim->SetVisibleInSceneCaptureOnly(bCaptureOnly);
		}
	}
}

void ARedPlayerCharacter::SetHUDSpaceMinimap(const bool bSpace)
{
	bHUDSpaceMinimapRequested = bSpace;
	if (ActiveHUDWidget)
	{
		ActiveHUDWidget->SetMinimapMode(
			bSpace ? EVibeMMOMinimapMode::Space : EVibeMMOMinimapMode::Surface);
	}
	RefreshReplacementHUDMinimapPresentation();
}

FName ARedPlayerCharacter::ResolveReplacementHUDMinimapFrameId() const
{
	if (const URedCharacterMovement* RedMovement =
		Cast<URedCharacterMovement>(GetCharacterMovement()))
	{
		if (!RedMovement->GetCurrentGravityBodyId().IsNone())
		{
			return RedMovement->GetCurrentGravityBodyId();
		}
		RedGravity::FBodyQueryResult Body;
		if (RedGravity::QueryDominantBodyDetailed(
			GetWorld(),
			GetActorLocation(),
			NAME_None,
			RedMovement->GravityBodySwitchHysteresis,
			Body))
		{
			return Body.StableId;
		}
	}
	return NAME_None;
}

void ARedPlayerCharacter::PublishReplacementHUDMinimap(const bool bSpaceMode)
{
	APlayerController* HUDPlayerController = Cast<APlayerController>(GetController());
	if (!HUDPlayerController && ActiveHUDWidget)
	{
		HUDPlayerController = ActiveHUDWidget->GetOwningPlayer();
	}
	if (!HUDPlayerController || !HUDPlayerController->IsLocalController())
	{
		return;
	}

	if (ARedHUD* ReplacementHUD = Cast<ARedHUD>(HUDPlayerController->GetHUD()))
	{
		const FName CelestialFrameId =
			ResolveReplacementHUDMinimapFrameId();
		if (bSpaceMode || CelestialFrameId.IsNone())
		{
			// Never let a later return to the surface present the last pixels
			// captured before flight/possession or a transient frame loss.
			LastReplacementMinimapCaptureFrameId = NAME_None;
			bReplacementMinimapSurfaceCaptureFresh = false;
		}
		else if (!IsValid(MinimapRT)
			|| !IsValid(MinimapCapture)
			|| MinimapCapture->TextureTarget != MinimapRT)
		{
			LastReplacementMinimapCaptureFrameId = NAME_None;
			bReplacementMinimapSurfaceCaptureFresh = false;
		}
		else if (!bReplacementMinimapSurfaceCaptureFresh
			|| LastReplacementMinimapCaptureFrameId != CelestialFrameId)
		{
			// A mode or gravity-frame transition must produce pixels in the new
			// frame before the replacement widget is allowed to expose the RT.
			MinimapCapture->CaptureScene();
			LastReplacementMinimapCaptureFrameId = CelestialFrameId;
			bReplacementMinimapSurfaceCaptureFresh = true;
		}
		const bool bSurfaceReady =
			!bSpaceMode
			&& !CelestialFrameId.IsNone()
			&& bReplacementMinimapSurfaceCaptureFresh
			&& LastReplacementMinimapCaptureFrameId == CelestialFrameId
			&& IsValid(MinimapRT)
			&& IsValid(MinimapCapture)
			&& MinimapCapture->TextureTarget == MinimapRT;
		ReplacementHUD->UpdateReplacementHUDMinimap(
			this,
			bSurfaceReady ? MinimapRT : nullptr,
			bSurfaceReady ? CelestialFrameId : NAME_None,
			bSpaceMode);
	}
}

void ARedPlayerCharacter::RefreshReplacementHUDMinimapPresentation()
{
	bool bSpaceMode = bHUDSpaceMinimapRequested;
	APlayerController* HUDPlayerController = Cast<APlayerController>(GetController());
	if (!HUDPlayerController && ActiveHUDWidget)
	{
		HUDPlayerController = ActiveHUDWidget->GetOwningPlayer();
	}
	if (HUDPlayerController)
	{
		const AActor* ReferenceActor = HUDPlayerController->GetViewTarget();
		bSpaceMode = bSpaceMode
			|| Cast<ARedShip>(HUDPlayerController->GetPawn()) != nullptr
			|| Cast<ARedShip>(ReferenceActor) != nullptr;
	}
	PublishReplacementHUDMinimap(bSpaceMode);
}

void ARedPlayerCharacter::SetHUDReticleTargetAlpha(const float TargetAlpha)
{
	if (ActiveHUDWidget)
	{
		ActiveHUDWidget->SetReticleTargetAlpha(TargetAlpha);
	}
}

void ARedPlayerCharacter::SetBase(FMovementBaseInterfaceData* MovementBaseInterfaceData, FName BoneName, bool bNotifyActor)
{
	// UE 5.8 routes the real base-setting through the FMovementBaseInterfaceData overload — the old
	// UPrimitiveComponent* override never fired, so the Voxel plugin kept basing us on a chunk and
	// spamming CanBeBaseForCharacter warnings. Voxel collision/mesh components are destroyed +
	// recreated as the world streams, so basing on one teleports the pawn off the planet. Reject
	// regenerated terrain bases — radial gravity + surface snap hold us on the planet.
	UPrimitiveComponent* NewBase = (MovementBaseInterfaceData && MovementBaseInterfaceData->IsValid())
		? Cast<UPrimitiveComponent>(MovementBaseInterfaceData->GetMovementBaseObject())
		: nullptr;
	FString BaseIdentity;
	if (NewBase)
	{
		BaseIdentity += NewBase->GetName();
		for (const UClass* Class = NewBase->GetClass(); Class; Class = Class->GetSuperClass())
		{
			BaseIdentity += TEXT(" ");
			BaseIdentity += Class->GetName();
		}
		for (const AActor* BaseOwner = NewBase->GetOwner(); IsValid(BaseOwner); BaseOwner = BaseOwner->GetOwner())
		{
			BaseIdentity += TEXT(" ");
			BaseIdentity += BaseOwner->GetName();
			BaseIdentity += TEXT(" ");
			BaseIdentity += GetNameSafe(BaseOwner->GetClass());
		}
		BaseIdentity.ToLowerInline();
	}
	const bool bLegacyVoxelBase = BaseIdentity.Contains(TEXT("voxel"));
	const bool bPlanetGenBase = BaseIdentity.Contains(TEXT("clmplanet"))
		|| BaseIdentity.Contains(TEXT("planetgen"))
		|| ((BaseIdentity.Contains(TEXT("proceduralmesh")) || BaseIdentity.Contains(TEXT("dynamicmesh")))
			&& (BaseIdentity.Contains(TEXT("clm")) || BaseIdentity.Contains(TEXT("planetchunk"))
				|| BaseIdentity.Contains(TEXT("terrainchunk"))));
	if (NewBase && (bLegacyVoxelBase || bPlanetGenBase))
	{
		// Clear to no base, but only when we currently have one — re-applying null every terrain
		// update disrupts movement velocity (stutter / "barely walking").
		if (GetMovementBaseObject() != nullptr)
		{
			Super::SetBase(static_cast<FMovementBaseInterfaceData*>(nullptr), BoneName, bNotifyActor);
		}
		return;
	}
	Super::SetBase(MovementBaseInterfaceData, BoneName, bNotifyActor);
}

void ARedPlayerCharacter::UpdateSkyFade()
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}

	// Altitude of the VIEW, planet centre = world origin. Use the LOCAL player controller's camera
	// (not GetController(), which is null while the ship possesses us) so the fade follows the SHIP
	// when flying — this is the "sky never faded because we read the hidden pawn's old spot" fix.
	FVector ViewLoc = GetActorLocation();
	if (APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0))
	{
		if (PC->PlayerCameraManager)
		{
			ViewLoc = PC->PlayerCameraManager->GetCameraLocation();
		}
	}
	FVector PlanetCenter = FVector::ZeroVector;
	float MeshPlanetRadius = 600000.f;
	float MeshPlanetDatumRadius = MeshPlanetRadius;
	float MeshPlanetPeakRadius = MeshPlanetRadius;
	if (RedGravity::FindMeshPlanet(
		World, PlanetCenter, MeshPlanetDatumRadius, &MeshPlanetPeakRadius))
	{
		MeshPlanetRadius = (MeshPlanetDatumRadius + MeshPlanetPeakRadius) * 0.5f;
	}
	const bool bFusedPrototype =
		World->GetMapName().Contains(TEXT("50km_FusedPrototype"));
	const float AtmosphereBottomRadiusKm =
		FMath::Max(1.f, MeshPlanetDatumRadius / 100000.f);
	// The local client must mirror GameMode's thin rendered shell.  The separate
	// AtmosphereHeightCm constant remains the gameplay/exposure ascent depth.
	const float AtmosphereHeightKm = RedPlanetPresentationTuning::VisualAtmosphereHeightKm
		+ FMath::Max(MeshPlanetRadius / 100000.f - AtmosphereBottomRadiusKm, 0.f);

	// Bind SkyAtmosphere early — star fade must use its BottomRadius + AtmosphereHeight, NOT
	// PeakRadius (mountains inflate "surface" by ~0.4 km and kept AltFade at 0 above the beach).
	if (!CachedAtmosphere.IsValid())
	{
		const float Now = World->GetTimeSeconds();
		if (Now >= NextAtmosphereBindTime)
		{
			NextAtmosphereBindTime = Now + 2.f;
			UDirectionalLightComponent* CanonicalAtmosphereSun = nullptr;
			for (TActorIterator<AActor> It(World); It && !CanonicalAtmosphereSun; ++It)
			{
				TArray<UDirectionalLightComponent*> Lights;
				It->GetComponents<UDirectionalLightComponent>(Lights);
				for (UDirectionalLightComponent* Light : Lights)
				{
					if (IsValid(Light) && Light->IsUsedAsAtmosphereSunLight()
						&& Light->GetAtmosphereSunLightIndex() == 0u)
					{
						CanonicalAtmosphereSun = Light;
						break;
					}
				}
			}
			if (CanonicalAtmosphereSun
				&& World->GetMapName().Contains(TEXT("50km_FusedPrototype")))
			{
				MakeClientAtmosphereAttachmentChainMovable(CanonicalAtmosphereSun);
				CanonicalAtmosphereSun->SetIntensity(
					RedPlanetPresentationTuning::DaylightSunIlluminanceLux);
				CanonicalAtmosphereSun->SetAtmosphereSunLight(true);
			}

			TArray<USkyAtmosphereComponent*> AtmosphereComponents;
			USkyAtmosphereComponent* CanonicalAtmosphere = nullptr;
			for (TActorIterator<AActor> It(World); It; ++It)
			{
				TArray<USkyAtmosphereComponent*> Atmospheres;
				It->GetComponents<USkyAtmosphereComponent>(Atmospheres);
				for (USkyAtmosphereComponent* AtmComp : Atmospheres)
				{
					if (!IsValid(AtmComp))
					{
						continue;
					}
					// GameMode is server-only in network play. Promote the client-side
					// SunSky chain before any Set* call so the same presentation reaches
					// Steam clients instead of silently no-oping on a Static component.
					MakeClientAtmosphereAttachmentChainMovable(AtmComp);
					AtmComp->SetWorldScale3D(FVector::OneVector);
					AtmosphereComponents.Add(AtmComp);
					if (CanonicalAtmosphereSun
						&& AtmComp->GetOwner() == CanonicalAtmosphereSun->GetOwner())
					{
						CanonicalAtmosphere = AtmComp;
					}
					// GameMode exists only on the server. Reassert the physical atmosphere on
					// each local client as it binds the map component so remote Steam clients
					// receive the same persistent soft orbital limb.
					AtmComp->TransformMode =
						ESkyAtmosphereTransformMode::PlanetCenterAtComponentTransform;
					AtmComp->SetBottomRadius(AtmosphereBottomRadiusKm);
					AtmComp->SetAtmosphereHeight(AtmosphereHeightKm);
					AtmComp->SetRayleighScattering(
						RedPlanetPresentationTuning::RayleighScatteringColor);
					AtmComp->SetRayleighExponentialDistribution(
						RedPlanetPresentationTuning::RayleighHeightKm);
					AtmComp->SetMieScattering(FLinearColor::White);
					AtmComp->SetMieExponentialDistribution(
						RedPlanetPresentationTuning::MieHeightKm);
					AtmComp->SetRayleighScatteringScale(
						RedPlanetPresentationTuning::RayleighScatteringScale);
					AtmComp->SetMieScatteringScale(
						RedPlanetPresentationTuning::MieScatteringScale);
					AtmComp->SetMieAbsorptionScale(
						RedPlanetPresentationTuning::MieAbsorptionScale);
					AtmComp->SetOtherAbsorptionScale(
						RedPlanetPresentationTuning::OtherAbsorptionScale);
					AtmComp->SetMieAnisotropy(
						RedPlanetPresentationTuning::MieAnisotropy);
					AtmComp->SetMultiScatteringFactor(
						RedPlanetPresentationTuning::MultiScatteringFactor);
					AtmComp->SetAerialPespectiveViewDistanceScale(
						RedPlanetPresentationTuning::AerialPerspectiveScale);
					AtmComp->SetGroundAlbedo(FColor(180, 140, 90));
					AtmComp->SetSkyLuminanceFactor(
						RedPlanetPresentationTuning::SkyLuminanceFactor);
					AtmComp->SetSkyAndAerialPerspectiveLuminanceFactor(
						RedPlanetPresentationTuning::SkyAndAerialLuminanceFactor);
					if (!AtmComp->GetComponentLocation().Equals(PlanetCenter, 1.0f))
					{
						AtmComp->SetWorldLocation(PlanetCenter, false, nullptr,
							ETeleportType::TeleportPhysics);
					}
				}
			}
			if (!CanonicalAtmosphere && AtmosphereComponents.Num() > 0)
			{
				CanonicalAtmosphere = AtmosphereComponents[0];
			}
			for (USkyAtmosphereComponent* AtmComp : AtmosphereComponents)
			{
				if (AtmComp == CanonicalAtmosphere)
				{
					AtmComp->ComponentTags.Remove(TEXT("RedDisabledSkyAtmosphere"));
					continue;
				}
				AtmComp->ComponentTags.AddUnique(TEXT("RedDisabledSkyAtmosphere"));
				AtmComp->SetVisibility(false, true);
				AtmComp->SetHiddenInGame(true, true);
				AtmComp->MarkRenderStateDirty();
			}
			if (CanonicalAtmosphere)
			{
				CanonicalAtmosphere->SetVisibility(true, true);
				CanonicalAtmosphere->SetHiddenInGame(false, true);
				CanonicalAtmosphere->MarkRenderStateDirty();
				CachedAtmosphere = CanonicalAtmosphere;
				AtmosphereBaseRayleigh =
					RedPlanetPresentationTuning::RayleighScatteringScale;
				AtmosphereBaseMie = RedPlanetPresentationTuning::MieScatteringScale;
				AtmosphereFadeAlpha = 1.f;
				AtmosphereFadeTarget = 1.f;
				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("Sky fade bound canonical atmosphere %s.%s; disabled %d duplicate(s); mobility=%d registered=%d skyLum=%s rayleigh=%.4f mie=%.4f"),
					*GetNameSafe(CanonicalAtmosphere->GetOwner()),
					*CanonicalAtmosphere->GetName(),
					FMath::Max(AtmosphereComponents.Num() - 1, 0),
					static_cast<int32>(CanonicalAtmosphere->Mobility),
					CanonicalAtmosphere->IsRegistered() ? 1 : 0,
					*CanonicalAtmosphere->SkyLuminanceFactor.ToString(),
					CanonicalAtmosphere->RayleighScatteringScale,
					CanonicalAtmosphere->MieScatteringScale);
			}
		}
	}

	// Atmosphere shell shared by server, clients, vehicles and procedural space scenery.
	float BottomRadiusCm = AtmosphereBottomRadiusKm * 100000.f;
	float AtmHeightCm = AtmosphereHeightKm * 100000.f;
	if (CachedAtmosphere.IsValid())
	{
		BottomRadiusCm = FMath::Max(CachedAtmosphere->BottomRadius, 1.f) * 100000.f;
		AtmHeightCm = FMath::Max(CachedAtmosphere->AtmosphereHeight, 0.25f) * 100000.f;
	}
	const float Altitude = (float)(ViewLoc - PlanetCenter).Size() - BottomRadiusCm;
	// The fused 50 km planet's terrain mesh is intentionally offset from the
	// atmosphere datum. Water orbit presentation must use the visible mesh
	// surface, otherwise the water can be hidden while the player is still at
	// the shoreline.
	const float PresentationAltitudeCm =
		static_cast<float>((ViewLoc - PlanetCenter).Size()) - MeshPlanetRadius;

	// PlanetGen's Single Layer Water component is a correct-radius full sphere,
	// but its view-dependent refraction can visually expand beyond the macro land
	// mesh during ascent. Keep the authentic So Stylized water near the player,
	// then hand the distant view to the authored macro surface. Hysteresis avoids
	// a visibility flicker while hovering near the transition.
	// ActiveHUDWidget remains owned by this local player while a ship possesses the
	// controller, so it is the durable local-presentation marker during flight.
	const bool bMacroSurfaceReady = CachedPlanetMacroSurface.IsValid()
		&& CachedPlanetMacroSurface->IsVisible()
		&& !CachedPlanetMacroSurface->bHiddenInGame;
	if ((IsLocallyControlled() || ActiveHUDWidget != nullptr)
		&& CachedPlanetWaterMeshes.Num() > 0)
	{
		const bool bNightWaterT04RadialOrbitValidation =
			RedPlanetPresentationTuning::IsNightWaterT04MapName(World->GetMapName())
			&& RedPlanetPresentationTuning::UseNightWaterT04SoStylizedRadial();
		// The blank-canvas fused prototype intentionally keeps its authored sea
		// datum and ocean masks but does not present PlanetGen's complete water
		// sphere.  A full sphere surrounds low authored terrain and reads as a
		// second ocean/sky layer during ascent.  Dedicated water validation maps
		// remain independent from this production-map safety gate.
		const bool bFusedPrototypeWithoutMaskedOceans =
			World->GetMapName().Contains(TEXT("50km_FusedPrototype"))
			&& !bNightWaterT04RadialOrbitValidation;
		const auto UsesNightWaterT04RadialMaterial = [](const UMeshComponent* WaterMesh)
		{
			UMaterialInterface* Candidate = WaterMesh ? WaterMesh->GetMaterial(0) : nullptr;
			for (int32 ParentDepth = 0; Candidate && ParentDepth < 8; ++ParentDepth)
			{
				if (Candidate->GetPathName()
					== RedPlanetPresentationTuning::NightWaterT04RadialMaterialPath)
				{
					return true;
				}
				const UMaterialInstance* Instance = Cast<UMaterialInstance>(Candidate);
				Candidate = Instance ? Instance->Parent : nullptr;
			}
			return false;
		};
		// Water presentation is independent from the molecular atmosphere thickness.
		// Raising the shell to contain HI-5 clouds must never bring the full spherical
		// water mesh back into a flight/orbit view. Hide by 0.40 km with hysteresis.
		constexpr float HideWaterAboveCm = 40000.f;
		constexpr float ShowWaterBelowCm = 30000.f;
		const bool bShouldHideWater = bFusedPrototypeWithoutMaskedOceans
			|| (bMacroSurfaceReady
				&& (bPlanetWaterHiddenForOrbit
					? PresentationAltitudeCm > ShowWaterBelowCm
					: PresentationAltitudeCm > HideWaterAboveCm));
		const bool bWaterVisibilityPolicyChanged =
			bShouldHideWater != bPlanetWaterHiddenForOrbit;
		// Reconcile the disposable T04 orbit view while it remains above the threshold,
		// not only on the first altitude transition. This covers streamed replacement
		// meshes and restores the normal hide immediately when F9 begins re-entry.
		const bool bNeedsNightWaterOrbitReconcile =
			bNightWaterT04RadialOrbitValidation && bShouldHideWater;
		if (bWaterVisibilityPolicyChanged || bNeedsNightWaterOrbitReconcile)
		{
			bPlanetWaterHiddenForOrbit = bShouldHideWater;
			static const FName OrbitHiddenTag(TEXT("RedOrbitWaterHidden"));
			int32 ChangedMeshes = 0;
			int32 KeptRadialMeshes = 0;
			for (const TWeakObjectPtr<UMeshComponent>& WeakWaterMesh : CachedPlanetWaterMeshes)
			{
				if (UMeshComponent* WaterMesh = WeakWaterMesh.Get())
				{
					const bool bKeepRadialVisible = bPlanetWaterHiddenForOrbit
						&& bNightWaterT04RadialOrbitValidation
						&& bOrbitInspectionActive
						&& UsesNightWaterT04RadialMaterial(WaterMesh);
					if (bKeepRadialVisible)
					{
						++KeptRadialMeshes;
						if (WaterMesh->ComponentHasTag(OrbitHiddenTag))
						{
							WaterMesh->ComponentTags.Remove(OrbitHiddenTag);
							WaterMesh->SetHiddenInGame(false, true);
							WaterMesh->MarkRenderStateDirty();
							++ChangedMeshes;
						}
					}
					else if (bPlanetWaterHiddenForOrbit && !WaterMesh->bHiddenInGame)
					{
						WaterMesh->ComponentTags.AddUnique(OrbitHiddenTag);
						WaterMesh->SetHiddenInGame(true, true);
						WaterMesh->MarkRenderStateDirty();
						++ChangedMeshes;
					}
					else if (!bPlanetWaterHiddenForOrbit
						&& WaterMesh->ComponentHasTag(OrbitHiddenTag))
					{
						WaterMesh->ComponentTags.Remove(OrbitHiddenTag);
						WaterMesh->SetHiddenInGame(false, true);
						WaterMesh->MarkRenderStateDirty();
						++ChangedMeshes;
					}
				}
			}
			if (bWaterVisibilityPolicyChanged || ChangedMeshes > 0)
			{
				UE_LOG(LogRedPlayerCharacter, Display,
					TEXT("Planet water orbit presentation: hidden=%d surfaceAltitude=%.2fkm cached=%d changed=%d radialKeptVisible=%d nightWaterT04=%d orbitInspection=%d"),
					bPlanetWaterHiddenForOrbit ? 1 : 0, PresentationAltitudeCm * 0.00001f,
					CachedPlanetWaterMeshes.Num(), ChangedMeshes, KeptRadialMeshes,
					bNightWaterT04RadialOrbitValidation ? 1 : 0,
					bOrbitInspectionActive ? 1 : 0);
			}
		}
	}
	// The physical visual limb is intentionally thin, but the playable ascent remains
	// eight kilometres deep. Drive sky/exposure presentation from the nominal surface
	// and shared gameplay transition so it cannot snap to space a few hundred metres up.
	const float StarFadeStartCm = RedPlanetPresentationTuning::AtmosphereHeightCm
		* RedPlanetPresentationTuning::OrbitExposureStartFraction;
	const float StarFadeEndCm = RedPlanetPresentationTuning::AtmosphereHeightCm
		* RedPlanetPresentationTuning::OrbitExposureEndFraction;
	const float AltFade = FMath::SmoothStep(
		StarFadeStartCm, StarFadeEndCm, PresentationAltitudeCm);
	// The small physical shell needs a strong sky-only daylight lift at the
	// surface, but that would make the orbital limb look opaque. Fade it down in
	// 5% steps during ascent; quantization avoids rebuilding atmosphere LUTs every
	// frame while preserving a smooth visual transition.
	if (CachedAtmosphere.IsValid())
	{
		const float QuantizedSkyFade = FMath::RoundToFloat(AltFade * 20.f) / 20.f;
		const FLinearColor DesiredSkyLuminance = FMath::Lerp(
			RedPlanetPresentationTuning::SkyLuminanceFactor,
			RedPlanetPresentationTuning::OrbitSkyLuminanceFactor,
			QuantizedSkyFade);
		if (!CachedAtmosphere->SkyLuminanceFactor.Equals(DesiredSkyLuminance, 0.02f))
		{
			CachedAtmosphere->SetSkyLuminanceFactor(DesiredSkyLuminance);
		}
		const FLinearColor DesiredAerialLuminance = FMath::Lerp(
			RedPlanetPresentationTuning::SkyAndAerialLuminanceFactor,
			RedPlanetPresentationTuning::OrbitSkyAndAerialLuminanceFactor,
			QuantizedSkyFade);
		if (!CachedAtmosphere->SkyAndAerialPerspectiveLuminanceFactor.Equals(
			DesiredAerialLuminance, 0.02f))
		{
			CachedAtmosphere->SetSkyAndAerialPerspectiveLuminanceFactor(
				DesiredAerialLuminance);
		}
	}

	// NIGHT stars disabled for now — a mis-bound sun was able to punch star-noise into daytime
	// sky/sand (grey grain + white streaks). Space stars use AltFade only.
	const float NightFade = 0.f;
	const float Fade = AltFade;

	// Star sphere = TWO mirrored hemisphere meshes tagged "SpaceStarDome" — bind and drive them ALL.
	// Enemy clones share this class but must not each rescan the world; and on maps with no dome the
	// scan retries at most every 2s instead of every frame.
	if (bIsEnemy)
	{
		return;
	}

	// Keep the home planet's atmosphere present from the surface, moon, and deep orbit.
	if (CachedAtmosphere.IsValid())
	{
		// Never zero the physical planet atmosphere because the viewer travelled into
		// orbit. With PlanetCenterAtComponentTransform it remains a correct distant limb.
		// Keep the full physical density at the surface, then thin only the orbital
		// optical depth. The atmosphere component remains present, preserving its
		// blue limb, while sunlit terrain is no longer hidden by an opaque gray dome.
		const bool bNightWaterT04RadialPresentation =
			RedPlanetPresentationTuning::IsNightWaterT04MapName(World->GetMapName())
			&& RedPlanetPresentationTuning::UseNightWaterT04SoStylizedRadial();
		const bool bNightWaterT04OrbitAtmosphereSuppression =
			bOrbitInspectionActive && bNightWaterT04RadialPresentation;
		const float OrbitAtmosphereDensityFraction =
			bNightWaterT04OrbitAtmosphereSuppression
				? RedPlanetPresentationTuning::NightWaterT04OrbitAtmosphereDensityFraction
				: RedPlanetPresentationTuning::OrbitAtmosphereDensityFraction;
		const float DesiredAtmosphereFadeTarget = FMath::Lerp(
			1.f, OrbitAtmosphereDensityFraction, AltFade);
		const bool bEnteringNightWaterT04Suppression =
			bNightWaterT04OrbitAtmosphereSuppression && AtmosphereFadeTarget > 0.001f;
		const bool bLeavingNightWaterT04Suppression =
			!bNightWaterT04OrbitAtmosphereSuppression && bNightWaterT04RadialPresentation
			&& AtmosphereFadeTarget <= 0.001f && AltFade >= 0.99f;
		AtmosphereFadeTarget = DesiredAtmosphereFadeTarget;
		if (bEnteringNightWaterT04Suppression || bLeavingNightWaterT04Suppression)
		{
			UE_LOG(LogRedPlayerCharacter, Display,
				TEXT("NightWater_T04 orbit atmosphere proof: suppressed=%d targetDensity=%.3f orbitInspection=%d altFade=%.2f"),
				bNightWaterT04OrbitAtmosphereSuppression ? 1 : 0,
				OrbitAtmosphereDensityFraction,
				bOrbitInspectionActive ? 1 : 0, AltFade);
		}
		if (!FMath::IsNearlyEqual(AtmosphereFadeAlpha, AtmosphereFadeTarget, 0.001f))
		{
			AtmosphereFadeAlpha = FMath::FInterpTo(AtmosphereFadeAlpha, AtmosphereFadeTarget, World->GetDeltaSeconds(), 2.5f);
		}
		// SkyAtmosphere setters invalidate and regenerate the atmosphere LUTs. Calling them
		// every frame caused thousands of redundant LUT rebuilds, visible stutter, and GPU
		// memory pressure in long packaged runs. Reassert only when the desired value changed.
		const float DesiredRayleighScale = AtmosphereBaseRayleigh * AtmosphereFadeAlpha;
		const float DesiredMieScale = AtmosphereBaseMie * AtmosphereFadeAlpha;
		if (!FMath::IsNearlyEqual(
			CachedAtmosphere->RayleighScatteringScale, DesiredRayleighScale, 0.0001f))
		{
			CachedAtmosphere->SetRayleighScatteringScale(DesiredRayleighScale);
		}
		if (!FMath::IsNearlyEqual(
			CachedAtmosphere->MieScatteringScale, DesiredMieScale, 0.0001f))
		{
			CachedAtmosphere->SetMieScatteringScale(DesiredMieScale);
		}
	}

	if (SkyFadeDMIs.Num() == 0 || !CachedSunLight || SkyStarDomeMeshes.Num() == 0)
	{
		const float Now = World->GetTimeSeconds();
		// Throttle the world scan only — never skip applying SpaceFade below.
		if (Now >= NextSkyDomeBindTime)
		{
			NextSkyDomeBindTime = Now + 2.f;
			if (SkyFadeDMIs.Num() == 0 || SkyStarDomeMeshes.Num() == 0)
			{
				SkyFadeDMIs.Reset();
				SkyStarDomeMeshes.Reset();
				for (TActorIterator<AStaticMeshActor> It(World); It; ++It)
				{
					const bool bTagged = It->ActorHasTag(TEXT("SpaceStarDome"));
					const bool bLabeled = It->GetActorNameOrLabel().Contains(TEXT("SpaceStarDome"));
					if (!bTagged && !bLabeled)
					{
						continue;
					}
					if (!bTagged)
					{
						It->Tags.AddUnique(FName(TEXT("SpaceStarDome")));
					}
					if (UStaticMeshComponent* SMC = It->GetStaticMeshComponent())
					{
						// Domes are recentered on the camera every tick — Static mobility spams
						// "has to be Movable if you'd like to move" (~2 warnings/frame).
						if (SMC->Mobility != EComponentMobility::Movable)
						{
							SMC->SetMobility(EComponentMobility::Movable);
						}
						SMC->SetCastShadow(false);
						SMC->SetCollisionEnabled(ECollisionEnabled::NoCollision);
						SMC->bNeverDistanceCull = true;
						SMC->BoundsScale = 50.f;
						// Prefer the live star mat (engine T_Sky_Stars) over any stale slot.
						if (UMaterialInterface* StarMat = LoadObject<UMaterialInterface>(nullptr,
								TEXT("/Game/RedMMO/Materials/M_SpaceStars_Live.M_SpaceStars_Live")))
						{
							SMC->SetMaterial(0, StarMat);
						}
						if (UMaterialInstanceDynamic* DMI = SMC->CreateAndSetMaterialInstanceDynamic(0))
						{
							DMI->SetScalarParameterValue(TEXT("SpaceFade"), 0.f);
							DMI->SetScalarParameterValue(TEXT("StarBrightness"), 0.f);
							SkyFadeDMIs.Add(DMI);
							SkyStarDomeMeshes.Add(SMC);
						}
						// Stay hidden until AltFade says we're in space — never flash on bind.
						SMC->SetVisibility(false);
						SMC->SetHiddenInGame(true);
						It->SetActorHiddenInGame(true);
					}
				}
			}
			if (!CachedSunLight)
			{
				// The sky BP's atmosphere sun (see ARedDayNight::FindSun for the same heuristic).
				UDirectionalLightComponent* Best = nullptr;
				float BestIntensity = 0.f;
				for (TActorIterator<AActor> It(World); It; ++It)
				{
					TArray<UDirectionalLightComponent*> Lights;
					It->GetComponents<UDirectionalLightComponent>(Lights);
					for (UDirectionalLightComponent* L : Lights)
					{
						if (L->GetName().Contains(TEXT("SkyDirectionalLight")))
						{
							CachedSunLight = L;
							break;
						}
						if (L->Intensity > BestIntensity)
						{
							BestIntensity = L->Intensity;
							Best = L;
						}
					}
					if (CachedSunLight)
					{
						break;
					}
				}
				if (!CachedSunLight)
				{
					CachedSunLight = Best;
				}
			}
		}
	}

	// Star domes: additive T_Sky_Stars spheres LEAK onto sand/sky even when "hidden"
	// (Metal still draws them → grey grain sky + white streak rain). Destroy on ground;
	// respawn only in space.
	const bool bShowStarDomes = Fade > 0.35f;
	if (!bShowStarDomes)
	{
		if (SkyStarDomeMeshes.Num() > 0 || SkyFadeDMIs.Num() > 0)
		{
			for (const TWeakObjectPtr<UStaticMeshComponent>& WeakSMC : SkyStarDomeMeshes)
			{
				if (UStaticMeshComponent* SMC = WeakSMC.Get())
				{
					if (AActor* Dome = SMC->GetOwner())
					{
						Dome->Destroy();
					}
				}
			}
			SkyStarDomeMeshes.Reset();
			SkyFadeDMIs.Reset();
		}
		// Catch map leftovers once in a while
		static float NextOrphanDomeKill = 0.f;
		const float NowKill = World->GetTimeSeconds();
		if (NowKill >= NextOrphanDomeKill)
		{
			NextOrphanDomeKill = NowKill + 2.f;
			for (TActorIterator<AStaticMeshActor> It(World); It; ++It)
			{
				if (!It->ActorHasTag(TEXT("SpaceStarDome"))
					&& !It->GetActorNameOrLabel().Contains(TEXT("SpaceStarDome")))
				{
					continue;
				}
				It->Destroy();
			}
		}
	}
	else
	{
		// Need domes in space — ask GameMode to ensure, then bind next tick if empty.
		const float NowEnsure = World->GetTimeSeconds();
		if (SkyStarDomeMeshes.Num() == 0 && NowEnsure >= NextSpaceStarEnsureTime)
		{
			NextSpaceStarEnsureTime = NowEnsure + 2.f;
			if (HasAuthority())
			{
				// Retire the missing-material star-dome path. The deterministic scenery actor
				// builds a camera-relative emissive HISM field on every peer instead.
				ARedSpaceScenery::EnsureForWorld(World, PlanetCenter);
			}
		}
		for (const TWeakObjectPtr<UStaticMeshComponent>& WeakSMC : SkyStarDomeMeshes)
		{
			if (UStaticMeshComponent* SMC = WeakSMC.Get())
			{
				SMC->SetVisibility(true);
				SMC->SetHiddenInGame(false);
				if (AActor* Dome = SMC->GetOwner())
				{
					Dome->SetActorHiddenInGame(false);
					Dome->SetActorLocation(ViewLoc);
				}
			}
		}
		for (UMaterialInstanceDynamic* DMI : SkyFadeDMIs)
		{
			if (DMI)
			{
				DMI->SetScalarParameterValue(TEXT("SpaceFade"), Fade);
				DMI->SetScalarParameterValue(TEXT("StarFade"), Fade);
				// Sparse thresholded stars — keep brightness modest (25 was a white blizzard).
				DMI->SetScalarParameterValue(TEXT("StarBrightness"), 5.0f);
				DMI->SetScalarParameterValue(TEXT("Brightness"), 5.0f);
				DMI->SetScalarParameterValue(TEXT("StarThreshold"), 0.82f);
			}
		}
	}

#if !UE_BUILD_SHIPPING
	{
		static float NextStarFadeLog = 0.f;
		const float NowLog = World->GetTimeSeconds();
		if (NowLog >= NextStarFadeLog)
		{
			NextStarFadeLog = NowLog + 5.f;
			UE_LOG(LogTemp, Display,
				TEXT("UpdateSkyFade: alt=%.0fcm (%.2fkm) AltFade=%.2f Fade=%.2f show=%d domes=%d"),
				Altitude, Altitude * 0.00001f, AltFade, Fade, bShowStarDomes ? 1 : 0,
				SkyStarDomeMeshes.Num());
		}
	}
#endif
}

void ARedPlayerCharacter::EnsureClientWaterPresentation()
{
	UWorld* World = GetWorld();
	// The pawn can lose local possession when a player boards a vehicle, while the
	// HUD remains local.  PlanetGen streaming can also create the macro surface or
	// WaterSphere after the original eight one-second probes.  Do not permanently
	// give up in either case: purge stale stream-owned weak references and retry at
	// a low rate until the presentation components have actually arrived.
	const bool bOwnsLocalPresentation = IsLocallyControlled() || ActiveHUDWidget != nullptr;
	if (!World || !bOwnsLocalPresentation
		|| World->GetTimeSeconds() < NextClientWaterPresentationTime)
	{
		return;
	}
	CachedPlanetWaterMeshes.RemoveAll([](const TWeakObjectPtr<UMeshComponent>& WeakWaterMesh)
	{
		return !WeakWaterMesh.IsValid();
	});
	const bool bFusedDryFoundation =
		World->GetMapName().Contains(TEXT("50km_FusedPrototype"))
		&& CachedPlanetMacroSurface.IsValid();
	if (bFusedDryFoundation)
	{
		// Once the dry fused macro surface has streamed in, no global WaterSphere is
		// expected.  Treat that as a settled state instead of scanning every actor,
		// component and water material once per second forever.
		ClientWaterPresentationAttempts = 0;
		NextClientWaterPresentationTime = World->GetTimeSeconds() + 60.f;
		return;
	}
	const bool bNeedsWaterDiscovery = CachedPlanetWaterMeshes.Num() == 0
		|| !CachedPlanetMacroSurface.IsValid();
	NextClientWaterPresentationTime = World->GetTimeSeconds()
		+ (bNeedsWaterDiscovery ? 1.f : 12.f);
	if (bNeedsWaterDiscovery)
	{
		++ClientWaterPresentationAttempts;
	}

	const bool bNightWaterVisualTest =
		RedPlanetPresentationTuning::IsNightWaterT04MapName(World->GetMapName());
	const bool bUseSoStylizedRadialAB = bNightWaterVisualTest
		&& RedPlanetPresentationTuning::UseNightWaterT04SoStylizedRadial();
	const TCHAR* GlobalOceanWaterMaterialPath = bNightWaterVisualTest
		? RedPlanetPresentationTuning::ResolveNightWaterT04GlobalOceanMaterialPath()
		: TEXT("/Game/RedMMO/Environment/MI_RedClearWater.MI_RedClearWater");
	const TCHAR* OasisWaterMaterialPath = bNightWaterVisualTest
		? RedPlanetPresentationTuning::NightWaterT04MaterialPath
		: GlobalOceanWaterMaterialPath;
	UMaterialInterface* GlobalOceanWater = LoadObject<UMaterialInterface>(nullptr, GlobalOceanWaterMaterialPath);
	UMaterialInterface* OasisWater = LoadObject<UMaterialInterface>(nullptr, OasisWaterMaterialPath);

	static const FName AppliedTag(TEXT("RedSoStylizedWaterApplied"));
	int32 UpdatedComponents = 0;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		AActor* Actor = *It;
		if (!IsValid(Actor))
		{
			continue;
		}
		const FString Label = Actor->GetActorNameOrLabel();
		const FString ClassName = Actor->GetClass()->GetName();
		bool bPlanetActor = false;
		for (const UClass* Class = Actor->GetClass(); Class; Class = Class->GetSuperClass())
		{
			if (Class->GetName() == TEXT("CLMPlanet"))
			{
				bPlanetActor = true;
				break;
			}
		}
		const bool bOceanActor = Label.Contains(TEXT("Ocean"))
			|| ClassName.Contains(TEXT("WaterBodyOcean"));
		const bool bOasisActor = Actor->ActorHasTag(TEXT("RedOasisWater"))
			|| Label.Contains(TEXT("RedOasisWater"));
		if (!bPlanetActor && !bOceanActor && !bOasisActor)
		{
			continue;
		}

		TArray<UMeshComponent*> Meshes;
		Actor->GetComponents<UMeshComponent>(Meshes);
		for (UMeshComponent* WaterMesh : Meshes)
		{
			if (!IsValid(WaterMesh))
			{
				continue;
			}
			const FString ComponentName = WaterMesh->GetName();
			if (bPlanetActor && ComponentName.Contains(TEXT("ResidentMacroSurface")))
			{
				CachedPlanetMacroSurface = WaterMesh;
				continue;
			}
			if (bPlanetActor && ComponentName.Contains(TEXT("WaterSphere")))
			{
				CachedPlanetWaterMeshes.AddUnique(WaterMesh);
			}
			const bool bWaterSurface = bOasisActor
				|| ComponentName.Contains(TEXT("WaterSphere"))
				|| ComponentName.Contains(TEXT("Ocean"))
				|| (bOceanActor && ComponentName.Contains(TEXT("Water")));
			// The normal cache intentionally tracks only PlanetGen's spherical ocean.
			// The disposable radial F9 isolation must also know about any local water
			// surface so everything except the selected radial body can be hidden.
			if (bUseSoStylizedRadialAB && bWaterSurface)
			{
				CachedPlanetWaterMeshes.AddUnique(WaterMesh);
			}
			UMaterialInterface* SelectedWater = bOasisActor ? OasisWater : GlobalOceanWater;
			const bool bUsesWorldGenGlobalOcean = bNightWaterVisualTest && !bOasisActor
				&& SelectedWater && SelectedWater->GetPathName().StartsWith(TEXT("/WorldGen/"));
			const bool bUsesProjectRadialOcean = bNightWaterVisualTest && !bOasisActor
				&& SelectedWater
				&& SelectedWater->GetPathName().Contains(TEXT("MI_RedRadialWater_Night_T04_V4"));
			bool bAlreadyUsesSelectedWater = WaterMesh->GetMaterial(0) == SelectedWater;
			if (const UMaterialInstance* CurrentInstance = Cast<UMaterialInstance>(WaterMesh->GetMaterial(0)))
			{
				bAlreadyUsesSelectedWater = bAlreadyUsesSelectedWater
					|| CurrentInstance->Parent == SelectedWater;
			}
			if (WaterMesh->ComponentHasTag(AppliedTag)
				&& (!bNightWaterVisualTest || bAlreadyUsesSelectedWater))
			{
				continue;
			}
			if (!bWaterSurface)
			{
				continue;
			}
			if (!SelectedWater)
			{
				continue;
			}
			for (int32 MaterialIndex = 0;
				MaterialIndex < FMath::Max(1, WaterMesh->GetNumMaterials()); ++MaterialIndex)
			{
				if (bUsesWorldGenGlobalOcean)
				{
					WaterMesh->SetMaterial(MaterialIndex, SelectedWater);
				}
				else if (UMaterialInstanceDynamic* WaterDMI = WaterMesh->CreateDynamicMaterialInstance(
					MaterialIndex, SelectedWater))
				{
					if (bUsesProjectRadialOcean)
					{
						WaterDMI->SetVectorParameterValue(TEXT("WaterTint"),
							RedPlanetPresentationTuning::NightWaterT04RadialTint);
						WaterDMI->SetScalarParameterValue(TEXT("WaveTiling1"),
							RedPlanetPresentationTuning::NightWaterT04RadialWaveTiling1);
						WaterDMI->SetScalarParameterValue(TEXT("WaveTiling2"),
							RedPlanetPresentationTuning::NightWaterT04RadialWaveTiling2);
						WaterDMI->SetScalarParameterValue(TEXT("NormalStrength"),
							RedPlanetPresentationTuning::NightWaterT04RadialNormalStrength);
						WaterDMI->SetScalarParameterValue(TEXT("NormalFadeStartCm"),
							RedPlanetPresentationTuning::NightWaterT04RadialNormalFadeStartCm);
						WaterDMI->SetScalarParameterValue(TEXT("NormalFadeEndCm"),
							RedPlanetPresentationTuning::NightWaterT04RadialNormalFadeEndCm);
						WaterDMI->SetScalarParameterValue(TEXT("Roughness"),
							RedPlanetPresentationTuning::NightWaterT04RadialRoughness);
						WaterDMI->SetScalarParameterValue(TEXT("Specular"),
							RedPlanetPresentationTuning::NightWaterT04RadialSpecular);
						WaterDMI->SetScalarParameterValue(TEXT("Opacity"),
							RedPlanetPresentationTuning::NightWaterT04RadialOpacity);
					}
					WaterDMI->SetVectorParameterValue(TEXT("Emissive Color"), FLinearColor::Black);
					WaterDMI->SetScalarParameterValue(TEXT("Water Scattering"),
						bNightWaterVisualTest ? RedPlanetPresentationTuning::NightWaterT04Scattering : 0.10f);
					if (!bOasisActor)
					{
						WaterDMI->SetScalarParameterValue(TEXT("Normal1 Flatness"),
							bNightWaterVisualTest ? RedPlanetPresentationTuning::NightWaterT04Normal1Flatness : 0.78f);
						WaterDMI->SetScalarParameterValue(TEXT("Normal2 Flatness"),
							bNightWaterVisualTest ? RedPlanetPresentationTuning::NightWaterT04Normal2Flatness : 0.82f);
						WaterDMI->SetScalarParameterValue(TEXT("Distant Normal Flatness"),
							bNightWaterVisualTest ? RedPlanetPresentationTuning::NightWaterT04DistantNormalFlatness : 0.88f);
						WaterDMI->SetScalarParameterValue(TEXT("Foam Multiply"), 0.f);
						// Mirror the authority-side T04 exception for a streaming client
						// that creates its own dynamic water instance after possession.
						if (bNightWaterVisualTest && !bUsesProjectRadialOcean)
						{
							WaterDMI->SetScalarParameterValue(TEXT("Caustic Strength"), 0.f);
							WaterDMI->SetScalarParameterValue(TEXT("Day Emission Multiplier"), 0.f);
							WaterDMI->SetScalarParameterValue(TEXT("Night Emission Multiplier"), 0.f);
							WaterDMI->SetScalarParameterValue(TEXT("Sunrise Emission Multiplier"), 0.f);
							WaterDMI->SetScalarParameterValue(TEXT("Sunset Emission Multiplier"), 0.f);
							WaterDMI->SetScalarParameterValue(TEXT("Overcast Emission Multiplier"), 0.f);
							WaterDMI->SetScalarParameterValue(TEXT("Specular"), 0.10f);
							WaterDMI->SetScalarParameterValue(TEXT("Roughness"), 0.52f);
						}
						WaterDMI->SetScalarParameterValue(TEXT("Waves"),
							bNightWaterVisualTest ? RedPlanetPresentationTuning::NightWaterT04Waves : 0.f);
					}
				}
				else
				{
					WaterMesh->SetMaterial(MaterialIndex, SelectedWater);
				}
			}
			WaterMesh->ComponentTags.AddUnique(AppliedTag);
			WaterMesh->SetCastShadow(false);
			WaterMesh->SetReceivesDecals(false);
			WaterMesh->MarkRenderStateDirty();
			++UpdatedComponents;
		}
	}

	if (UpdatedComponents > 0)
	{
		UE_LOG(LogRedPlayerCharacter, Display,
			TEXT("Client water presentation: %s on %d components (attempt %d)"),
			bNightWaterVisualTest
				? (bUseSoStylizedRadialAB
					? TEXT("NightWater_T04 project-owned SoStylized radial A/B")
					: TEXT("NightWater_T04 WorldGen global-ocean A/B plus SoStylized oasis"))
				: TEXT("production SoStylized water"),
			UpdatedComponents, ClientWaterPresentationAttempts);
	}
	if (CachedPlanetMacroSurface.IsValid()
		&& (CachedPlanetWaterMeshes.Num() > 0
			|| World->GetMapName().Contains(TEXT("50km_FusedPrototype"))))
	{
		// Treat the counter as a diagnostic for the current streaming wait rather
		// than a lifetime ceiling.  If a later stream unload invalidates either cache,
		// the next tick resumes the one-second discovery cadence.
		ClientWaterPresentationAttempts = 0;
	}
}

void ARedPlayerCharacter::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	// F9's first press is a visual acceptance camera, not a falling gameplay state.
	// Hold the pawn exactly at the inspection radius until the second F9 begins re-entry.
	if (bOrbitInspectionActive)
	{
		if (UCharacterMovementComponent* InspectionMovement = GetCharacterMovement())
		{
			InspectionMovement->StopMovementImmediately();
			if (InspectionMovement->MovementMode != MOVE_Flying)
			{
				InspectionMovement->SetMovementMode(MOVE_Flying);
			}
		}
	}
	// Each equipped rifle owns its own heat reservoir. Inactive weapons continue cooling, while
	// simulated proxies consume the server's replicated values instead of running an extra clock.
	if (HasAuthority() || IsLocallyControlled())
	{
		EnsureWeaponSlotState();
		bool bUnlockedAnySlot = false;
		for (int32 Slot = 0; Slot < 2; ++Slot)
		{
			WeaponSlotHeat[Slot] = FMath::Max(
				0.0f, WeaponSlotHeat[Slot] - WeaponHeatCoolRate * DeltaSeconds);
			if (WeaponSlotOverheated[Slot] != 0
				&& WeaponSlotHeat[Slot] <= MaxWeaponHeat * WeaponHeatResumeFraction)
			{
				WeaponSlotOverheated[Slot] = 0;
				bUnlockedAnySlot = true;
			}
		}
		if (HasAuthority() && bUnlockedAnySlot)
		{
			ForceNetUpdate();
		}
	}
	// Creator row changes can repopulate SK_Weapon at runtime; resolve visibility on the next frame.
	UpdateCreatorWeaponVisibility();
	// The creator can reapply its vendor AnimBP after a body-row change. Keep every native trooper
	// on RED's tracked rifle overlay except during explicit full-body skydive/death playback.
	if (!bDowned && !bSkydiving && !bOrbitalDropActive && IsUsingTrooperBody() && TrooperAnimClass)
	{
		if (USkeletalMeshComponent* CharacterMesh = GetMesh();
			CharacterMesh && CharacterMesh->GetAnimationMode() == EAnimationMode::AnimationBlueprint
			&& CharacterMesh->GetAnimClass() != TrooperAnimClass)
		{
			CharacterMesh->SetAnimInstanceClass(TrooperAnimClass);
		}
	}
	EnsureClientWaterPresentation();
	UpdateSkyFade();
	UpdateAlienLocomotion();
	// Smooth ADS zoom: pull the camera in close + tighten the shoulder offset so it reads
	// as aiming down the sight rather than just zooming the third-person view.
	if (Camera && SpringArm)
	{
		const float TargetFOV = bADS ? ADSFOV : BaseFOV;
		const float TargetArm = bADS ? ADSArmLength : (BaseArmLength + ZoomArmOffset);
		const FVector TargetSocket = bADS ? FVector(0.f, 45.f, 68.f) : FVector(0.f, 60.f, 60.f);
		Camera->SetFieldOfView(FMath::FInterpTo(Camera->FieldOfView, TargetFOV, DeltaSeconds, ADSInterpSpeed));
		SpringArm->TargetArmLength = FMath::FInterpTo(SpringArm->TargetArmLength, TargetArm, DeltaSeconds, ADSInterpSpeed);
		SpringArm->SocketOffset = FMath::VInterpTo(SpringArm->SocketOffset, TargetSocket, DeltaSeconds, ADSInterpSpeed);
	}
	APlayerController* HUDPlayerController = Cast<APlayerController>(GetController());
	if (!HUDPlayerController && ActiveHUDWidget)
	{
		HUDPlayerController = ActiveHUDWidget->GetOwningPlayer();
	}
	if (Camera && HUDPlayerController && HUDPlayerController->IsLocalController())
	{
		float HeadingYaw = Camera->GetComponentRotation().Yaw;
		bool bUseSpaceMinimap = bHUDSpaceMinimapRequested;
		AActor* ReferenceActor = this;
		ARedShip* ReferenceShip = Cast<ARedShip>(GetAttachParentActor());
		if (ReferenceShip)
		{
			ReferenceActor = ReferenceShip;
		}
		if (HUDPlayerController)
		{
			if (AActor* ViewTarget = HUDPlayerController->GetViewTarget())
			{
				ReferenceActor = ViewTarget;
				ReferenceShip = Cast<ARedShip>(ViewTarget);
			}
			bUseSpaceMinimap = bUseSpaceMinimap
				|| Cast<ARedShip>(HUDPlayerController->GetPawn()) != nullptr
				|| Cast<ARedShip>(ReferenceActor) != nullptr;
		}
		if (ReferenceShip)
		{
			// World Euler yaw is undefined for a craft travelling around a sphere and spun wildly when
			// the ship pitched nose-radial. Derive heading in the dominant planet's tangent frame.
			const URedShipMovementComponent* ReferenceMovement =
				Cast<URedShipMovementComponent>(ReferenceShip->GetMovementComponent());
			const FName CompassGravityBodyId = ReferenceMovement
				? ReferenceMovement->GetCurrentGravityBodyId() : NAME_None;
			if (CompassGravityBodyId.IsNone()
				|| LastStableCompassGravityBodyId != CompassGravityBodyId)
			{
				bHasStableCompassHeading = false;
				LastStableCompassGravityBodyId = NAME_None;
			}
			const FVector PlanetCenter = ReferenceMovement
				? ReferenceMovement->PlanetCenter : FVector::ZeroVector;
			const FVector Radial = ReferenceShip->GetActorLocation() - PlanetCenter;
			const FVector LocalUp = Radial.IsNearlyZero()
				? ReferenceShip->GetActorUpVector().GetSafeNormal() : Radial.GetSafeNormal();
			const FVector TangentForward = FVector::VectorPlaneProject(
				ReferenceShip->GetActorForwardVector(), LocalUp).GetSafeNormal();
			FVector TangentNorth = FVector::VectorPlaneProject(
				FVector::UpVector, LocalUp).GetSafeNormal();
			if (TangentNorth.IsNearlyZero())
			{
				TangentNorth = FVector::VectorPlaneProject(
					FVector::ForwardVector, LocalUp).GetSafeNormal();
			}
			const FVector TangentEast = FVector::CrossProduct(
				TangentNorth, LocalUp).GetSafeNormal();
			if (!TangentForward.IsNearlyZero() && !TangentNorth.IsNearlyZero()
				&& !TangentEast.IsNearlyZero())
			{
				HeadingYaw = FMath::Fmod(FMath::RadiansToDegrees(FMath::Atan2(
					FVector::DotProduct(TangentForward, TangentEast),
					FVector::DotProduct(TangentForward, TangentNorth))) + 360.f, 360.f);
				if (!CompassGravityBodyId.IsNone())
				{
					LastStableCompassHeadingDegrees = HeadingYaw;
					LastStableCompassGravityBodyId = CompassGravityBodyId;
					bHasStableCompassHeading = true;
				}
			}
			else if (bHasStableCompassHeading)
			{
				if (!CompassGravityBodyId.IsNone()
					&& LastStableCompassGravityBodyId == CompassGravityBodyId)
				{
					HeadingYaw = LastStableCompassHeadingDegrees;
				}
			}
		}
		else
		{
			bHasStableCompassHeading = false;
			LastStableCompassGravityBodyId = NAME_None;
			HeadingYaw = ReferenceActor->GetActorRotation().Yaw;
		}

		if (HUDPlayerController)
		{
			if (ARedHUD* ReplacementHUD = Cast<ARedHUD>(HUDPlayerController->GetHUD()))
			{
				ReplacementHUD->UpdateReplacementHUDCompass(HeadingYaw);
				PublishReplacementHUDMinimap(bUseSpaceMinimap);
			}
		}
		if (ActiveHUDWidget)
		{
			ActiveHUDWidget->SetCompassHeadingDegrees(HeadingYaw);
			ActiveHUDWidget->SetMinimapMode(
				bUseSpaceMinimap ? EVibeMMOMinimapMode::Space : EVibeMMOMinimapMode::Surface);

			if (!bUseSpaceMinimap && GetWorld())
			{
				TArray<FVector2D> Blips;
				const FVector MyLocation = GetActorLocation();
				const FVector Forward = GetActorForwardVector();
				const FVector Right = GetActorRightVector();
				constexpr float PixelsPerCm = 292.f / 6000.f;
				for (TActorIterator<ARedPlayerCharacter> It(GetWorld()); It; ++It)
				{
					ARedPlayerCharacter* Other = *It;
					if (!IsValid(Other) || Other == this || !Other->bIsEnemy || Other->IsDowned())
					{
						continue;
					}
					const FVector Delta = Other->GetActorLocation() - MyLocation;
					Blips.Add(FVector2D(
						FVector::DotProduct(Delta, Right),
						-FVector::DotProduct(Delta, Forward)) * PixelsPerCm);
					if (Blips.Num() >= 8)
					{
						break;
					}
				}
				ActiveHUDWidget->SetMinimapBlips(Blips);
			}
		}
	}
	// Smooth walk<->sprint ramp so the run/sprint blend doesn't stutter on the speed change.
	if (UCharacterMovementComponent* CMC = GetCharacterMovement())
	{
		// Backpedal cap: moving backward relative to facing (only happens in combat, when the body
		// faces the aim) is slow — you don't sprint backwards. When relaxed the body faces the move
		// direction, so this never triggers.
		float EffectiveTarget = bHoverboarding ? HoverboardMaxSpeed : TargetWalkSpeed;
		const FVector Vel2D = GetVelocity().GetSafeNormal2D();
		if (!bHoverboarding && !Vel2D.IsNearlyZero() && FVector::DotProduct(Vel2D, GetActorForwardVector()) < -0.2f)
		{
			EffectiveTarget = TargetWalkSpeed * BackpedalSpeedScale;
		}
		CMC->MaxWalkSpeed = FMath::FInterpTo(CMC->MaxWalkSpeed, EffectiveTarget, DeltaSeconds, 6.f);
	}

	// Gravity-aligned orbit camera: rebuild the boom from (heading vector, local up, clamped pitch)
	// BEFORE anything below reads the camera's forward (body facing, aim offset, fire).
	UpdateOrbitCamera();

	// Combat aim state = ADS OR holding fire OR just fired. Gates body facing + spine aim-offset +
	// the AnimBP relaxed<->aim overlay (bIsAiming). Holstered = never combat-aim.
	const bool bCombatAim = IsCombatAiming();

	// One trajectory for pose, muzzle flash, and projectile. The owner resolves the camera reticle to
	// an actual point; simulated copies use the replicated accepted/desired barrel direction.
	FVector AimPointWorld = GetMuzzleWorldLocation() + ReplicatedAimDirection.GetSafeNormal() * 100000.f;
	FVector AimDirectionWorld = ReplicatedAimDirection.GetSafeNormal();
	if (AimDirectionWorld.IsNearlyZero()) { AimDirectionWorld = GetActorForwardVector(); }
	if (bCombatAim && IsPlayerControlled() && IsLocallyControlled())
	{
		FVector LocalAimPoint;
		FVector LocalShotDirection;
		if (ResolveWeaponAim(LocalAimPoint, LocalShotDirection))
		{
			AimPointWorld = LocalAimPoint;
			AimDirectionWorld = LocalShotDirection;
			ReplicatedAimDirection = LocalShotDirection;

			const float Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.f;
			const bool bDirectionChanged = LastSentAimDirection.IsNearlyZero()
				|| FVector::DotProduct(LastSentAimDirection.GetSafeNormal(), LocalShotDirection) < 0.99995f;
			if (bDirectionChanged && (Now - LastAimDirectionSendTime) >= 0.05f)
			{
				LastSentAimDirection = LocalShotDirection;
				LastAimDirectionSendTime = Now;
				if (HasAuthority())
				{
					ForceNetUpdate();
				}
				else
				{
					ServerSetAimDirection(LocalShotDirection);
				}
			}
		}
	}

	// Body facing (Fortnite-style, sphere-aware):
	//  - Running & NOT firing/aiming: face the MOVEMENT direction (clean run, no camera-chase wobble,
	//    and no spine bend — see the aim-offset gate below).
	//  - Firing OR aiming (bCombatAim): face the AIM direction so you actually FACE what you shoot —
	//    no more running one way and firing out of your own back — and the gun tracks the crosshair.
	//  - At rest & not aiming: don't rotate; mouse-look just orbits the camera.
	if (Controller && GetMesh() && !GetMesh()->IsSimulatingPhysics())
	{
		const FVector Up = GetActorUpVector();
		const FVector AimFwd  = FVector::VectorPlaneProject(AimDirectionWorld, Up).GetSafeNormal();
		// Face the INPUT (acceleration) direction while it exists: it is rock-steady when holding a
		// key, whereas the VELOCITY direction chatters on bumpy voxel ground and made the body (and
		// the anim Direction) weave left-right every frame while running.
		const FVector FacingBasis = (GetCharacterMovement() && GetCharacterMovement()->GetCurrentAcceleration().SizeSquared() > 10000.f)
			? GetCharacterMovement()->GetCurrentAcceleration() : GetVelocity();
		const FVector MoveFwd = FVector::VectorPlaneProject(FacingBasis, Up).GetSafeNormal();
		const float TangentSpeed = FVector::VectorPlaneProject(GetVelocity(), Up).Size();
		const bool bMoving = TangentSpeed > 80.0f;
		const FVector DesiredFwd = (bCombatAim || !bMoving || MoveFwd.IsNearlyZero()) ? AimFwd : MoveFwd;
		const FVector CurrentFwd = FVector::VectorPlaneProject(GetActorForwardVector(), Up).GetSafeNormal();
		if (!DesiredFwd.IsNearlyZero() && !CurrentFwd.IsNearlyZero())
		{
			const float YawDeltaDeg = FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(FVector::DotProduct(CurrentFwd, DesiredFwd), -1.0f, 1.0f)));
			if (bMoving && YawDeltaDeg > 1.0f)
			{
				const FQuat TargetQuat = FRotationMatrix::MakeFromZX(Up, DesiredFwd).ToQuat();
				const float TurnSpeed = bCombatAim ? 16.0f : 11.0f;  // snap to face the target fast when firing
				SetActorRotation(FQuat::Slerp(GetActorQuat(), TargetQuat, FMath::Clamp(DeltaSeconds * TurnSpeed, 0.f, 1.f)));
				bTurnInPlacePivoting = false;
			}
			else if (bCombatAim)
			{
				// TURN-IN-PLACE (standing aim): feet stay PLANTED while the spine aim-offset tracks
				// the target; past StartAngle the body does ONE fast pivot burst to re-center — the
				// Fortnite plant-and-pivot — instead of continuously twisting the idle pose under the
				// camera ("standing there with crossed legs").
				if (!bTurnInPlacePivoting && YawDeltaDeg > TurnInPlaceStartAngle)
				{
					bTurnInPlacePivoting = true;
					TurnInPlaceDirSign = (((CurrentFwd ^ DesiredFwd) | Up) >= 0.f) ? 1.f : -1.f;   // +1 = pivoting right
				}
				if (bTurnInPlacePivoting)
				{
					const FQuat TargetQuat = FRotationMatrix::MakeFromZX(Up, DesiredFwd).ToQuat();
					SetActorRotation(FQuat::Slerp(GetActorQuat(), TargetQuat, FMath::Clamp(DeltaSeconds * TurnInPlacePivotSpeed, 0.f, 1.f)));
					if (YawDeltaDeg < TurnInPlaceStopAngle)
					{
						bTurnInPlacePivoting = false;
					}
				}
			}
		}
	}

	// Sphere-correct locomotion inputs for the AnimBP (see header) — computed AFTER the body turn so
	// Direction is measured against this frame's final facing. Plus sprint play-rate matching.
	{
		const FVector Up = GetActorUpVector();
		const FVector TangentVel = FVector::VectorPlaneProject(GetVelocity(), Up);
		AnimGroundSpeed = (float)TangentVel.Size();
		const FVector TangentFwd = FVector::VectorPlaneProject(GetActorForwardVector(), Up).GetSafeNormal();
		float RawDirectionDeg = 0.f;
		if (AnimGroundSpeed > 10.f && !TangentFwd.IsNearlyZero())
		{
			const FVector VelDir = TangentVel.GetSafeNormal();
			const float CosAngle = FMath::Clamp((float)(TangentFwd | VelDir), -1.f, 1.f);
			const float DirSign = (((TangentFwd ^ VelDir) | Up) >= 0.f) ? 1.f : -1.f;   // +90 = moving to the actor's RIGHT
			RawDirectionDeg = DirSign * FMath::RadiansToDegrees(FMath::Acos(CosAngle));
		}
		// Wrap-aware smoothing: raw direction jitters a few degrees per frame on rough terrain and
		// the blendspace visibly flickered between forward and the strafe samples ("jerking back
		// and forth left and right"). ~10/s catch-up is invisible on real turns.
		AnimDirectionDeg = FRotator::NormalizeAxis(
			AnimDirectionDeg + FRotator::NormalizeAxis(RawDirectionDeg - AnimDirectionDeg) * FMath::Clamp(DeltaSeconds * 10.f, 0.f, 1.f));
		// PIVOT STEP: while turning in place, feed the legs the blendspace's own strafe samples
		// in the pivot direction so the feet step around the turn instead of dragging idle.
		if (bTurnInPlacePivoting && AnimGroundSpeed < TurnInPlaceStepSpeed)
		{
			AnimGroundSpeed = TurnInPlaceStepSpeed;
			AnimDirectionDeg = TurnInPlaceDirSign * 90.f;
		}
		bAnimShouldMove = (AnimGroundSpeed > 80.f) || bTurnInPlacePivoting;

		// RUN-BOB STABILIZER (see header): counter-translate the mesh by a damped fraction of the
		// pelvis bounce. Baseline follows slowly (0.8/s) so the ~3Hz stride oscillation is measured
		// against it while slopes/terrain drift pass through untouched. Reads LAST frame's pose
		// (one-frame lag, invisible at 60+fps).
		// Skip entirely on ragdolled bodies: SetRelativeLocation/Rotation on a simulating mesh does
		// nothing but spam "Attempting to move a fully simulated skeletal mesh" every frame while a
		// corpse waits out its despawn timer.
		if (USkeletalMeshComponent* BobMesh = (!bDowned && GetMesh() && !GetMesh()->IsSimulatingPhysics()) ? GetMesh() : nullptr)
		{
			const FVector PelvisRel = BobMesh->GetBoneLocation(TEXT("pelvis")) - GetActorLocation();
			// Subtract the correction we are already applying — the bone position INCLUDES our own
			// mesh offset, and measuring the actuated signal fed the correction back into itself
			// (0.65 damp in a closed loop = 1.86x AMPLIFIED bob instead of damped).
			const float PelvisVert = (float)FVector::DotProduct(PelvisRel, Up) - BobCorrV;
			const float PelvisLat = (float)FVector::DotProduct(PelvisRel, GetActorRightVector()) - BobCorrL;
			if (BobBaselineVert > 1.0e8f)
			{
				BobBaselineVert = PelvisVert;
				BobBaselineLat = PelvisLat;
			}
			BobBaselineVert = FMath::FInterpTo(BobBaselineVert, PelvisVert, DeltaSeconds, 0.8f);
			BobBaselineLat = FMath::FInterpTo(BobBaselineLat, PelvisLat, DeltaSeconds, 0.8f);
			const bool bStabilize = GetCharacterMovement()
				&& GetCharacterMovement()->MovementMode == MOVE_Walking && AnimGroundSpeed > 150.f;
			const float TargetV = bStabilize ? FMath::Clamp((BobBaselineVert - PelvisVert) * RunBobDamp, -25.f, 25.f) : 0.f;
			const float TargetL = bStabilize ? FMath::Clamp((BobBaselineLat - PelvisLat) * RunBobDamp, -15.f, 15.f) : 0.f;
			BobCorrV = FMath::FInterpTo(BobCorrV, TargetV, DeltaSeconds, 30.f);
			BobCorrL = FMath::FInterpTo(BobCorrL, TargetL, DeltaSeconds, 30.f);
			FVector MeshRel = BobMesh->GetRelativeLocation();
			MeshRel.Z = -GetCapsuleComponent()->GetScaledCapsuleHalfHeight() + BobCorrV;
			MeshRel.Y = BobCorrL;
			BobMesh->SetRelativeLocation(MeshRel);

			// ROLL stabilizer: the run cycle rocks the torso ±7.9 deg per stride ("bobbing back and
			// forth") — counter-roll the mesh around the actor's forward axis by a damped fraction
			// of the spine lean. Open loop: subtract the correction already applied.
			{
				const FVector SpineUp = BobMesh->GetSocketTransform(TEXT("spine_03"), RTS_World).TransformVectorNoScale(FVector(0.f, 1.f, 0.f));
				const float MeasuredRoll = FMath::RadiansToDegrees(FMath::Asin(FMath::Clamp((float)FVector::DotProduct(SpineUp, GetActorRightVector()), -1.f, 1.f)));
				const float RawRoll = MeasuredRoll - BobRollCorr;
				BobRollBaseline = FMath::FInterpTo(BobRollBaseline, RawRoll, DeltaSeconds, 0.8f);
				const float TargetRoll = bStabilize ? FMath::Clamp((BobRollBaseline - RawRoll) * RunRollDamp, -10.f, 10.f) : 0.f;
				BobRollCorr = FMath::FInterpTo(BobRollCorr, TargetRoll, DeltaSeconds, 30.f);
				const FQuat BaseRel = FRotator(0.f, -90.f, 0.f).Quaternion();
				BobMesh->SetRelativeRotation((FQuat(FVector::ForwardVector, FMath::DegreesToRadians(BobRollCorr)) * BaseRel).Rotator());
			}
		}
		// The locomotion blendspace is authored to 400 cm/s: above it (sprint = 800) scale the
		// whole-pose play rate so foot speed matches ground speed instead of slow-motion gliding.
		if (USkeletalMeshComponent* RateMesh = GetMesh())
		{
			const float TargetRate = (AnimGroundSpeed > 410.f) ? FMath::Clamp(AnimGroundSpeed / 400.f, 1.f, 2.2f) : 1.f;
			RateMesh->GlobalAnimRateScale = FMath::FInterpTo(RateMesh->GlobalAnimRateScale, TargetRate, DeltaSeconds, 8.f);
		}
	}

	// Procedural aim-offset driver: feed the AnimBP "AimRotation" (the spine Transform Modify Bone added
	// by URedMMOEditorTools::AddAimModifyBone) so the chest/arms/gun follow the camera up/down + center.
	// Axis mapping is live-tunable (AimPitchScale/AimRollScale) so it can be corrected via UECP, no rebuild.
	if (GetMesh() && !GetMesh()->IsSimulatingPhysics())
	{
		if (UAnimInstance* AI = GetMesh()->GetAnimInstance())
		{
			const bool bFallBlock = GetCharacterMovement() && GetCharacterMovement()->IsFalling()
				&& !bJetpackOn && !bOrbitalDropActive;
			const float FocalWeight = (bCombatAim && !bSkydiving && !bFallBlock) ? 1.f : 0.f;
			if (FStructProperty* TargetProperty = CastField<FStructProperty>(AI->GetClass()->FindPropertyByName(FocalAimTargetVarName)))
			{
				if (TargetProperty->Struct == TBaseStructure<FVector>::Get())
				{
					*TargetProperty->ContainerPtrToValuePtr<FVector>(AI) =
						GetMesh()->GetComponentTransform().InverseTransformPosition(AimPointWorld);
				}
			}
			if (FFloatProperty* WeightProperty = CastField<FFloatProperty>(AI->GetClass()->FindPropertyByName(FocalAimWeightVarName)))
			{
				WeightProperty->SetPropertyValue_InContainer(AI, FocalWeight);
			}
			if (FStructProperty* SP = CastField<FStructProperty>(AI->GetClass()->FindPropertyByName(AimRotationVarName)))
			{
				if (SP->Struct == TBaseStructure<FRotator>::Get())
				{
					const FVector LocalAim = GetActorQuat().UnrotateVector(AimDirectionWorld);
					const float Horiz = FMath::Max(0.01f, FMath::Sqrt(LocalAim.X * LocalAim.X + LocalAim.Y * LocalAim.Y));
					const float CamPitch = FMath::RadiansToDegrees(FMath::Atan2(LocalAim.Z, Horiz));    // up/down
					const float CamYaw = FMath::RadiansToDegrees(FMath::Atan2(LocalAim.Y, LocalAim.X)); // left/right residual
					FRotator Aim(0.f, 0.f, 0.f);
					// Drive all three component-space axes from CamPitch via live-tunable scales (the
					// correct up/down axis is skeleton-dependent; default Pitch=1). AimUpDownScale is a
					// global magnitude so the whole aim can be scaled/inverted live.
					const float P = (CamPitch + AimUpDownBias) * AimUpDownScale;
					Aim.Pitch = FMath::Clamp(P * AimPitchScale, -AimMaxAngle, AimMaxAngle);
					Aim.Yaw   = FMath::Clamp(P * AimYawScale + CamYaw * AimLeftRightScale + AimLeftRightBias, -AimMaxAngle, AimMaxAngle);
					Aim.Roll  = FMath::Clamp(P * AimRollScale, -AimMaxAngle, AimMaxAngle);
					// Only bend the upper body to aim while AIMING or FIRING (bCombatAim). While just
					// running/looking around, keep the spine NEUTRAL so the gun/body stay in the clean run
					// pose and looking up/down doesn't rock the whole body back and forth.
					*SP->ContainerPtrToValuePtr<FRotator>(AI) = bCombatAim ? Aim : FRotator::ZeroRotator;
				}
			}
		}
	}

	// Aim STANCE flag for the AnimBP (relaxed hip-carry <-> firing pose blend). True while ADS,
	// holding fire, or briefly after a shot — otherwise the upper body stays in the relaxed carry.
	if (USkeletalMeshComponent* AimM = GetMesh())
	{
		if (UAnimInstance* AimAI = AimM->GetAnimInstance())
		{
			const UCharacterMovementComponent* AimMovement = GetCharacterMovement();
			const bool bFallBlock = AimMovement && AimMovement->IsFalling()
				&& !bJetpackOn && !bOrbitalDropActive;
			const bool bJetpackAimPose = bCombatAim && !bSkydiving && bJetpackOn
				&& AimMovement && AimMovement->IsFalling();
			const float AimGroundSpeed = FVector::VectorPlaneProject(GetVelocity(), GetActorUpVector()).Size();
			const bool bMovingAimPose = bCombatAim && !bJetpackAimPose && !bSkydiving
				&& AimMovement && AimMovement->IsMovingOnGround() && AimGroundSpeed > 140.f;

			if (FBoolProperty* BoolP = CastField<FBoolProperty>(AimAI->GetClass()->FindPropertyByName(TEXT("bIsAiming"))))
			{
				// Allow combat aim while jetpacking in air (shoot-while-flying).
				BoolP->SetPropertyValue_InContainer(AimAI, bCombatAim && !bSkydiving && !bFallBlock);
			}
			// Fade the rifle-pose overlay off when holstered (empty hands -> base locomotion).
			if (FFloatProperty* WeightP = CastField<FFloatProperty>(AimAI->GetClass()->FindPropertyByName(TEXT("WeaponDrawnWeight"))))
			{
				WeightP->SetPropertyValue_InContainer(AimAI, (bHolstered || bSkydiving || bFallBlock) ? 0.0f : 1.0f);
			}
			// Animated upper-body selectors live immediately before DefaultSlot. The fire montage still
			// evaluates after them, and FocalRig performs the final exact muzzle correction after the LBB.
			if (FBoolProperty* MovingPoseP = CastField<FBoolProperty>(AimAI->GetClass()->FindPropertyByName(TEXT("bRifleAimMoving"))))
			{
				MovingPoseP->SetPropertyValue_InContainer(AimAI, bMovingAimPose);
			}
			if (FBoolProperty* JetpackPoseP = CastField<FBoolProperty>(AimAI->GetClass()->FindPropertyByName(TEXT("bRifleJetpackAim"))))
			{
				JetpackPoseP->SetPropertyValue_InContainer(AimAI, bJetpackAimPose);
			}
		}
	}

	// While aiming/firing, slide the rifle forward in the hand-socket frame so the support hand
	// lands on the foregrip rather than the muzzle tip (the ADS pose is authored for a longer
	// rifle). Zero offset while carrying keeps the clean two-handed hold. Live-tune: WeaponAimNudge.
	if (WeaponMesh && !bHolstered)
	{
		WeaponMesh->SetRelativeLocation(bCombatAim ? WeaponAimNudgeOffset : FVector::ZeroVector);
	}

	// Skydive: hold terminal velocity while diving, and auto-exit the moment we touch down.
	// Armed drop: the dive begins the moment the pawn actually leaves the station deck.
	if (bDropArmed && !bSkydiving && !bDowned)
	{
		if (UCharacterMovementComponent* ArmedCMC = GetCharacterMovement())
		{
			if (ArmedCMC->MovementMode == MOVE_Falling)
			{
				bDropArmed = false;
				StartSkydive();
			}
		}
	}

	if (bSkydiving)
	{
		if (UCharacterMovementComponent* CMC = GetCharacterMovement())
		{
			const FVector GravDir = CMC->GetGravityDirection().GetSafeNormal();   // "down"
			float FallSpeed = FVector::DotProduct(CMC->Velocity, GravDir);        // + = descending

			if (bOrbitalDropActive)
			{
				// Re-entry descent: drive the along-gravity speed to a controlled constant (the weak
				// dive gravity alone never reaches terminal over an 8km drop). The jetpack subtracts
				// from it — hold to slow, hover, or climb — while WASD still steers via AirControl
				// (only the vertical component is overridden here). Horizontal velocity is untouched.
				// Fortnite dive: pitch the camera DOWN to plunge fast, level out to slow-glide. CameraPitch
				// is 0 at level and negative looking down, so -Pitch/75 maps [level..straight-down] -> [0..1].
				const float DiveAlpha = FMath::Clamp(-CameraPitch / 75.f, 0.f, 1.f);
				const float DiveTarget = FMath::Lerp(OrbitalDropSlowFallSpeed, OrbitalDropDiveFallSpeed, DiveAlpha);
				float TargetDown = DiveTarget - (bJetpackThrusting ? JetpackThrustSpeed : 0.f);
				CMC->Velocity += GravDir * (TargetDown - FallSpeed);
				FallSpeed = TargetDown;

				// Horizontal STEERING (Fortnite-style point-and-dive): glide toward where WASD points at
				// a strong, controllable speed so the diver picks where to land. The heading is built
				// from CameraForward (the yaw-only, gravity-tangent heading) + WASD — NOT the pitched
				// camera — so looking straight DOWN to aim doesn't collapse or flip the steer direction.
				const FVector DiveUp = -GravDir;
				FVector SteerFwd = FVector::VectorPlaneProject(CameraForward, DiveUp).GetSafeNormal();
				if (SteerFwd.IsNearlyZero()) { SteerFwd = FVector::VectorPlaneProject(GetActorForwardVector(), DiveUp).GetSafeNormal(); }
				const FVector SteerRight = FVector::CrossProduct(DiveUp, SteerFwd).GetSafeNormal();
				FVector InDir = SteerFwd * DropSteerFwd + SteerRight * DropSteerRight;
				if (InDir.SizeSquared() > 1.f) { InDir = InDir.GetSafeNormal(); }   // clamp diagonal to unit
				const FVector CurHoriz = FVector::VectorPlaneProject(CMC->Velocity, DiveUp);
				const FVector DesiredHoriz = InDir * DropSteerSpeed;                // zero input -> bleed to a stop
				const FVector NewHoriz = FMath::VInterpTo(CurHoriz, DesiredHoriz, DeltaSeconds, DropSteerAccel);
				CMC->Velocity += (NewHoriz - CurHoriz);
				// We fully author the horizontal velocity here, so AirControl must NOT also push it (it
				// would overshoot DropSteerSpeed and feel mushy/framerate-dependent). Set once below in
				// BeginOrbitalDrop. Camera stays FREE the whole way down — no per-frame pitch override.
			}
			else if (FallSpeed > SkydiveMaxFallSpeed)
			{
				CMC->Velocity -= GravDir * (FallSpeed - SkydiveMaxFallSpeed);
				FallSpeed = SkydiveMaxFallSpeed;
			}

			// Cache the impact speed ONLY while airborne. On the touchdown frame the CMC has already
			// flipped to Walking and zeroed the into-ground velocity; caching then would overwrite the
			// real impact speed with ~0 and the slam would never fire.
			if (CMC->MovementMode == MOVE_Falling)
			{
				LastFallSpeed = FMath::Max(0.f, FallSpeed);
			}
			// Touchdown ONLY when genuinely near ground. The CMC occasionally reports a spurious
			// MOVE_Walking tick at high altitude (phantom floor) which would otherwise end the dive
			// mid-air; the ground trace rejects it and keeps the pawn diving.
			const bool bGroundMode = (CMC->MovementMode == MOVE_Walking || CMC->MovementMode == MOVE_NavWalking);
			if (bGroundMode && IsNearGround())
			{
				StopSkydive();   // consumes LastFallSpeed -> DoLandingSlam; clears bOrbitalDropActive
			}
		}
	}

	// AUTO HOVER-GLIDE: you went off a cliff — instead of plummeting and crashing, the board catches you
	// and floats you down at a controlled rate, riding the slope. Holding Space (jetpack) or Ctrl (slam)
	// overrides it; it auto-releases when you land.
	if (UCharacterMovementComponent* GCMC = GetCharacterMovement())
	{
		UWorld* GW = GetWorld();
		const bool bBusy = bSkydiving || bOrbitalDropActive || bSlamming || bGrappling || bJumpHeld;
		const FVector GUp = -GCMC->GetGravityDirection().GetSafeNormal();
		const float HalfH = GetCapsuleComponent() ? GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 88.f;
		FHitResult GHit; bool bGround = false; float GroundGap = 1.0e9f;
		if (GW && !bBusy)
		{
			FCollisionQueryParams GQP(SCENE_QUERY_STAT(HoverGlide), false, this);
			const FVector GLoc = GetActorLocation();
			bGround = GW->LineTraceSingleByChannel(GHit, GLoc, GLoc - GUp * (HalfH + CliffCatchDistance), ECC_WorldStatic, GQP);
			if (bGround) { GroundGap = FVector::DotProduct((GLoc - GUp * HalfH) - GHit.ImpactPoint, GUp); }
		}
		const bool bFalling = (GCMC->MovementMode == MOVE_Falling);
		if (bHoverboardEnabled && !bBusy && bFalling && bGround && (bAutoGlide || GroundGap > HoverEngageMinDrop))
		{
			if (!bAutoGlide) { bAutoGlide = true; if (bHoverboardEnabled && HoverboardMesh) { HoverboardMesh->SetVisibility(true); } }
			// pin the fall to a gentle sink, cushioning to a hover as the ground comes close
			const float WantSink = (GroundGap > HoverHeight) ? HoverSinkSpeed : 0.f;
			const float AlongDown = FVector::DotProduct(GCMC->Velocity, -GUp);
			GCMC->Velocity += (-GUp) * (WantSink - AlongDown);
			// ride the slope down + cap horizontal speed
			FVector FloorN = GHit.ImpactNormal; if (FloorN.IsNearlyZero()) { FloorN = GUp; }
			const float Steep = FMath::Clamp(1.f - FVector::DotProduct(FloorN, GUp), 0.f, 1.f);
			if (Steep > 0.02f) { GCMC->Velocity += FVector::VectorPlaneProject(-GUp, FloorN).GetSafeNormal() * (HoverboardSlopeAccel * Steep * DeltaSeconds); }
			const FVector GHVel = FVector::VectorPlaneProject(GCMC->Velocity, GUp);
			if (GHVel.Size() > HoverboardMaxSpeed) { GCMC->Velocity -= GHVel.GetSafeNormal() * (GHVel.Size() - HoverboardMaxSpeed); }
		}
		else if (bAutoGlide)   // landed / jetpacked / no ground below → release
		{
			bAutoGlide = false;
			if (!bHoverboarding && HoverboardMesh) { HoverboardMesh->SetVisibility(false); }
		}
	}

	// HOVERBOARD: while riding on the ground, glide with low friction and accelerate DOWNHILL by how
	// steep the slope is (surf/snowboard feel) — carry that speed off a cliff into the jetpack/grapple chain.
	if (bHoverboarding && !bSlamming)
	{
		if (UCharacterMovementComponent* HCMC = GetCharacterMovement())
		{
			if (HCMC->MovementMode == MOVE_Walking || HCMC->MovementMode == MOVE_NavWalking)
			{
				const FVector GravUp = -HCMC->GetGravityDirection().GetSafeNormal();
				FVector FloorN = HCMC->CurrentFloor.HitResult.ImpactNormal;
				if (FloorN.IsNearlyZero()) { FloorN = GravUp; }
				const float Steep = FMath::Clamp(1.f - FVector::DotProduct(FloorN, GravUp), 0.f, 1.f);
				if (Steep > 0.02f)
				{
					const FVector DownSlope = FVector::VectorPlaneProject(-GravUp, FloorN).GetSafeNormal();
					HCMC->Velocity += DownSlope * (HoverboardSlopeAccel * Steep * DeltaSeconds);
				}
				const FVector HVel = FVector::VectorPlaneProject(HCMC->Velocity, GravUp);
				if (HVel.Size() > HoverboardMaxSpeed)
				{
					HCMC->Velocity -= HVel.GetSafeNormal() * (HVel.Size() - HoverboardMaxSpeed);
				}
			}
		}
	}

	// SLAM finisher (Left-Ctrl in the air): pin a hard downward dive; on touchdown fire the landing-slam AOE.
	if (bSlamming && GetLocalRole() != ROLE_SimulatedProxy)
	{
		if (UCharacterMovementComponent* SCMC = GetCharacterMovement())
		{
			if (SCMC->MovementMode == MOVE_Falling)
			{
				const FVector GravDir = SCMC->GetGravityDirection().GetSafeNormal();
				if (SlamWindupRemaining > 0.f)
				{
					SlamWindupRemaining = FMath::Max(0.f, SlamWindupRemaining - DeltaSeconds);
					// Hold back a premature fall during the anticipation frame so the hop/pose can be read.
					const float AlongDown = FVector::DotProduct(SCMC->Velocity, GravDir);
					if (AlongDown > 1200.f)
					{
						SCMC->Velocity -= GravDir * (AlongDown - 1200.f);
					}
				}
				else
				{
					const float Along = FVector::DotProduct(SCMC->Velocity, GravDir);
					SCMC->Velocity += GravDir * (SlamDiveSpeed - Along);
				}
			}
			else
			{
				bSlamming = false;
				SlamWindupRemaining = 0.f;
				PlaySlamImpactPose();
				// Owner prediction stops at touchdown, but only authority applies damage/state and
				// multicasts the impact. This prevents a client-local duplicate crater/explosion.
				if (HasAuthority())
				{
					DoLandingSlam(SlamDiveSpeed);
					ForceNetUpdate();
				}
			}
		}
	}

	// General JETPACK: after a double-tap of Space (bJetpackOn), holding Space thrusts you UP. Distinct
	// from the orbital-drop thruster and the skydive. Disengages once you settle back on the ground.
	bThrustFXWanted = false;   // recomputed here + in TickGrapple; drives the plume after TickGrapple
	const bool bCanSimulateJetpack = GetLocalRole() != ROLE_SimulatedProxy;
	if (!bCanSimulateJetpack)
	{
		bThrustFXWanted = bJetpackOn && bJumpHeld && Fuel > 0.f;
	}
	if (bCanSimulateJetpack && bJetpackOn && !bOrbitalDropActive && !bSkydiving && !bGrappling && !bSlamming)
	{
		if (UCharacterMovementComponent* JCMC = GetCharacterMovement())
		{
			const bool bGrounded = (JCMC->MovementMode == MOVE_Walking || JCMC->MovementMode == MOVE_NavWalking);
			if (bGrounded && !bJumpHeld)
			{
				bJetpackOn = false;   // landed and not thrusting → turn the pack off
			}
			else if (bJumpHeld && Fuel > 0.f)
			{
				if (bGrounded) { JCMC->SetMovementMode(MOVE_Falling); }   // lift off the ground
				const FVector Up = -JCMC->GetGravityDirection().GetSafeNormal();
				const float Accel = bSprintHeld ? (JetpackAccel * JetpackBoostAccelMult) : JetpackAccel;
				const float MaxUp = bSprintHeld ? (JetpackMaxUpSpeed * JetpackBoostMaxUpMult) : JetpackMaxUpSpeed;
				JCMC->Velocity += Up * Accel * DeltaSeconds;        // thrust beats gravity → rise
				const float UpSpeed = FVector::DotProduct(JCMC->Velocity, Up);
				if (UpSpeed > MaxUp) { JCMC->Velocity -= Up * (UpSpeed - MaxUp); }
				bThrustFXWanted = true;   // plume on while thrusting
				Fuel = FMath::Max(0.f, Fuel - FuelDrainPerSecond * DeltaSeconds);
			}
		}
	}

	// Fuel: drain on ground sprint, regen when not thrusting/sprinting.
	{
		const bool bGroundSprint = bSprintHeld && !bThrustFXWanted && GetCharacterMovement()
			&& (GetCharacterMovement()->MovementMode == MOVE_Walking || GetCharacterMovement()->MovementMode == MOVE_NavWalking);
		// Do not recharge one frame at a time while the player is still demanding thrust at
		// zero fuel. That made the plume/audio alternate on/off every tick. Releasing thrust
		// starts regeneration; holding an empty pack keeps it cleanly off.
		const bool bFuelThrustRequested = (bJetpackOn && bJumpHeld)
			|| (bOrbitalDropActive && bJetpackThrusting);
		if (bGroundSprint)
		{
			Fuel = FMath::Max(0.f, Fuel - SprintFuelDrainPerSecond * DeltaSeconds);
		}
		else if (!bThrustFXWanted && !bFuelThrustRequested)
		{
			Fuel = FMath::Min(MaxFuel, Fuel + FuelRegenPerSecond * DeltaSeconds);
		}
	}

	TickGrapple(DeltaSeconds);   // reel toward the anchor (jetpack mid-grapple sets bThrustFXWanted too)

	// Pack-native Exhaust_L/R plume while thrusting (general jetpack OR hold-Space during orbital drop).
	// The RED atmospheric-entry plume (SetPlumeActive) is separate and still owned by the skydive path.
	{
		const bool bPackThrustFX = bThrustFXWanted || (bOrbitalDropActive && bJetpackThrusting);
		if (bPackThrustFX != bJetPlumeOn)
		{
			SetJetpackThrustFX(bPackThrustFX);
			bJetPlumeOn = bPackThrustFX;
		}
		else if (bPackThrustFX)
		{
			// Cascade emits along local +X — keep absolute MakeFromX(actor-down) on nozzles.
			const FVector PlumeDir = -GetActorUpVector().GetSafeNormal();
			if (!PlumeDir.IsNearlyZero())
			{
				const FRotator PlumeWorldRot = FRotationMatrix::MakeFromX(PlumeDir).Rotator();
				AActor* Pack = JetpackActor ? JetpackActor->GetChildActor() : nullptr;
				USkeletalMeshComponent* PackMesh = Pack
					? Pack->FindComponentByClass<USkeletalMeshComponent>() : nullptr;
				const FName SockL(TEXT("Exhaust_L"));
				const FName SockR(TEXT("Exhaust_R"));
				if (PackMesh && PackMesh->DoesSocketExist(SockL) && PackMesh->DoesSocketExist(SockR))
				{
					const FVector LocL = PackMesh->GetSocketLocation(SockL);
					const FVector LocR = PackMesh->GetSocketLocation(SockR);
					const FVector LocM = 0.5f * (LocL + LocR);
					auto PinPSC = [&PlumeWorldRot](UParticleSystemComponent* PSC, const FVector& Loc)
					{
						if (!PSC || !PSC->IsActive()) { return; }
						PSC->SetWorldLocation(Loc);
						PSC->SetWorldRotation(PlumeWorldRot);
					};
					PinPSC(JetpackExhaustL, LocL);
					PinPSC(JetpackExhaustR, LocR);
					PinPSC(JetpackExhaust, LocM);
				}
			}
			// Heal thrust loop if weapon concurrency ever stops it mid-flight.
			if (JetpackThrustAudio && GetNetMode() != NM_DedicatedServer)
			{
				JetpackThrustAudio->bIsUISound = false;
				JetpackThrustAudio->SetUISound(false);
				JetpackThrustAudio->bAllowSpatialization = true;
				JetpackThrustAudio->SetVolumeMultiplier(bSprintHeld ? 1.4f : 1.0f);
				JetpackThrustAudio->SetPitchMultiplier(bSprintHeld ? 1.15f : 1.0f);
				if (!JetpackThrustAudio->IsPlaying())
				{
					JetpackThrustAudio->Play();
				}
			}
		}
	}

	UpdateJetpackFlightAnim(bCombatAim);
	UpdateHUDStatus(); // keep yellow fuel bar live

	// Objective aim proof: the rifle socket is positioned at the real barrel tip, so the normalized
	// grip-to-muzzle vector is the visible barrel axis even though the socket's decorative rotation
	// is yawed for Niagara. Keep this readable in PIE/MCP for standing, running, and jetpack tests.
	WeaponDesiredAimDirectionWorld = AimDirectionWorld.GetSafeNormal();
	WeaponBarrelDirectionWorld = FVector::ZeroVector;
	WeaponBarrelAimDot = -1.0f;
	if (WeaponMesh)
	{
		WeaponBarrelDirectionWorld = (GetMuzzleWorldLocation() - WeaponMesh->GetComponentLocation()).GetSafeNormal();
		if (!WeaponBarrelDirectionWorld.IsNearlyZero() && !WeaponDesiredAimDirectionWorld.IsNearlyZero())
		{
			WeaponBarrelAimDot = FMath::Clamp(
				FVector::DotProduct(WeaponBarrelDirectionWorld, WeaponDesiredAimDirectionWorld), -1.0f, 1.0f);
		}
	}

	// Speed trail + board underglow while riding (trail needs real speed; glow shows whenever riding).
	{
		const bool bRiding = bHoverboardEnabled && (bHoverboarding || bAutoGlide);   // hoverboard OFF => no green speed-trail glow
		const bool bFast = bRiding && GetVelocity().Size() > 900.f;
		if (bFast != bTrailOn)
		{
			bTrailOn = bFast;
			if (SpeedTrail) { SpeedTrail->SetVisibility(bFast); if (bFast) { SpeedTrail->Activate(true); } else { SpeedTrail->Deactivate(); } }
		}
		// Board underglow REMOVED — it drowned the whole character in a green wash you couldn't see through.
		(void)bBoardGlowOn;
	}

	// Only point the barrel at the camera while actually aiming/firing. When relaxed, let the
	// weapon ride the hand socket (the two-handed chest carry) instead of always aiming forward.
	{
		if (IsCombatAiming())
		{
			AlignWeaponBarrelToCamera(DeltaSeconds);
		}
		else if (WeaponMesh && WeaponMesh->IsUsingAbsoluteRotation())
		{
			// Hand the gun back to the hand socket so it follows the relaxed carry pose.
			WeaponMesh->SetUsingAbsoluteRotation(false);
			WeaponMesh->SetRelativeRotation(FRotator::ZeroRotator);
		}
	}
}

void ARedPlayerCharacter::AlignWeaponBarrelToCamera(float DeltaSeconds)
{
	if (!bAlignWeaponBarrelToCamera || !WeaponMesh || !Camera)
	{
		return;
	}

	const FVector LocalAimAxis = WeaponBarrelSocketAimAxis.GetSafeNormal();
	const FVector DesiredAim = Camera->GetForwardVector().GetSafeNormal();
	if (LocalAimAxis.IsNearlyZero() || DesiredAim.IsNearlyZero())
	{
		return;
	}
	if (!WeaponMesh->IsUsingAbsoluteRotation())
	{
		WeaponMesh->SetUsingAbsoluteRotation(true);
	}

	const FQuat BarrelQuat = WeaponMesh->DoesSocketExist(MuzzleSocket)
		? WeaponMesh->GetSocketTransform(MuzzleSocket, RTS_World).GetRotation()
		: WeaponMesh->GetComponentQuat();
	const FVector CurrentAim = BarrelQuat.RotateVector(LocalAimAxis).GetSafeNormal();
	if (CurrentAim.IsNearlyZero())
	{
		return;
	}

	const FQuat DeltaToCamera = FQuat::FindBetweenNormals(CurrentAim, DesiredAim);
	const FQuat TargetWorldRotation = DeltaToCamera * WeaponMesh->GetComponentQuat();
	const float Alpha = FMath::Clamp(DeltaSeconds * WeaponAimAlignSpeed, 0.0f, 1.0f);
	WeaponMesh->SetWorldRotation(FQuat::Slerp(WeaponMesh->GetComponentQuat(), TargetWorldRotation, Alpha));
}

void ARedPlayerCharacter::PossessedBy(AController* NewController)
{
	Super::PossessedBy(NewController);
	TryCreateLocalHUD();
	UpdateHUDResources();

	if (APlayerController* PC = Cast<APlayerController>(NewController))
	{
		PC->SetInputMode(FInputModeGameOnly());
		PC->bShowMouseCursor = false;
		PC->SetIgnoreMoveInput(false);
		PC->SetIgnoreLookInput(false);
		UE_LOG(LogRedPlayerCharacter, Display, TEXT("Player possession input armed for %s via %s"),
			*GetNameSafe(this),
			*GetNameSafe(PC));
	}

	// Returning from piloting the migrated shuttle: pack re-possesses us at DriverExitPosition.
	// Place ON TOP of the hull (not planet ground-trace — that was spawning under terrain).
	if (bWasPilotingShuttle)
	{
		bWasPilotingShuttle = false;
		AActor* Ship = PilotedShuttle;
		PilotedShuttle = nullptr;
		// Force engines off on the parked shuttle after exit.
		if (ARedShuttleBase* Shuttle = Cast<ARedShuttleBase>(Ship))
		{
			Shuttle->EnsureEnginesOff();
		}
		else if (Ship)
		{
			if (UFunction* EngFn = Ship->FindFunction(FName(TEXT("ToggleEngines"))))
			{
				void* EngParms = FMemory_Alloca(EngFn->ParmsSize);
				FMemory::Memzero(EngParms, EngFn->ParmsSize);
				for (TFieldIterator<FProperty> It(EngFn); It && (It->PropertyFlags & CPF_Parm); ++It)
				{
					if (FBoolProperty* BP = CastField<FBoolProperty>(*It))
					{
						BP->SetPropertyValue_InContainer(EngParms, false);
						break;
					}
				}
				Ship->ProcessEvent(EngFn, EngParms);
			}
			if (FBoolProperty* EngineOnProp = FindFProperty<FBoolProperty>(Ship->GetClass(), TEXT("EngineOn")))
			{
				EngineOnProp->SetPropertyValue_InContainer(Ship, false);
			}
			if (FBoolProperty* FlyProp = FindFProperty<FBoolProperty>(Ship->GetClass(), TEXT("InFlyingElevation")))
			{
				FlyProp->SetPropertyValue_InContainer(Ship, false);
			}
		}
		SetPilotCaptureOnly(false);
		SetActorHiddenInGame(false);
		SetActorEnableCollision(true);

		FVector ExitLoc = GetActorLocation();
		FVector ExitFwd = GetActorForwardVector();
		if (Ship)
		{
			const FVector ShipUp = Ship->GetActorUpVector().GetSafeNormal();
			FVector Origin = Ship->GetActorLocation();
			FVector Extent = FVector(200.f, 200.f, 120.f);
			Ship->GetActorBounds(/*bOnlyCollidingComponents=*/false, Origin, Extent);
			// Project AABB extent onto ship-up → distance from origin to roof.
			const float RoofHalf =
				FMath::Abs(Extent.X * ShipUp.X) +
				FMath::Abs(Extent.Y * ShipUp.Y) +
				FMath::Abs(Extent.Z * ShipUp.Z);
			const float HalfHeight = GetCapsuleComponent()
				? GetCapsuleComponent()->GetScaledCapsuleHalfHeight()
				: 96.f;
			ExitLoc = Origin + ShipUp * (RoofHalf + HalfHeight + 30.f);
			ExitFwd = Ship->GetActorForwardVector();
		}
		OnExitedShip(ExitLoc, ExitFwd, Ship, /*bSnapToPlanetSurface=*/false);
		SetHUDSpaceMinimap(false);
	}
}

void ARedPlayerCharacter::SetupPlayerInputComponent(UInputComponent* InInput)
{
	Super::SetupPlayerInputComponent(InInput);
	UE_LOG(LogRedPlayerCharacter, Display, TEXT("Input bound for %s using %s"),
		*GetNameSafe(this),
		*GetNameSafe(InInput));
	InInput->BindAxis(TEXT("MoveForward"), this, &ARedPlayerCharacter::MoveForward);
	InInput->BindAxis(TEXT("MoveRight"), this, &ARedPlayerCharacter::MoveRight);
	InInput->BindAxis(TEXT("Turn"), this, &ARedPlayerCharacter::Turn);
	InInput->BindAxis(TEXT("LookUp"), this, &ARedPlayerCharacter::LookUp);
	InInput->BindAxis(TEXT("CameraZoom"), this, &ARedPlayerCharacter::OnCameraZoom);
	InInput->BindAction(TEXT("Jump"), IE_Pressed, this, &ACharacter::Jump);
	InInput->BindAction(TEXT("Jump"), IE_Released, this, &ACharacter::StopJumping);
	// Same key doubles as the orbital-drop jetpack (only bites while bOrbitalDropActive).
	InInput->BindAction(TEXT("Jump"), IE_Pressed, this, &ARedPlayerCharacter::StartJetpack);
	InInput->BindAction(TEXT("Jump"), IE_Released, this, &ARedPlayerCharacter::StopJetpack);
	InInput->BindAction(TEXT("Fire"), IE_Pressed, this, &ARedPlayerCharacter::StartFiring);
	InInput->BindAction(TEXT("Fire"), IE_Released, this, &ARedPlayerCharacter::StopFiring);
	InInput->BindAction(TEXT("ADS"), IE_Pressed, this, &ARedPlayerCharacter::StartADS);
	InInput->BindAction(TEXT("ADS"), IE_Released, this, &ARedPlayerCharacter::StopADS);
	InInput->BindAction(TEXT("Holster"), IE_Pressed, this, &ARedPlayerCharacter::ToggleHolster);
	InInput->BindAction(TEXT("Sprint"), IE_Pressed, this, &ARedPlayerCharacter::StartSprint);
	InInput->BindAction(TEXT("Sprint"), IE_Released, this, &ARedPlayerCharacter::StopSprint);
	InInput->BindAction(TEXT("Weapon1"), IE_Pressed, this, &ARedPlayerCharacter::OnWeapon1);
	InInput->BindAction(TEXT("Weapon2"), IE_Pressed, this, &ARedPlayerCharacter::OnWeapon2);
	InInput->BindAction(TEXT("AbilityQ"), IE_Pressed, this, &ARedPlayerCharacter::OnAbilityQ);
	InInput->BindAction(TEXT("AbilityQ"), IE_Released, this, &ARedPlayerCharacter::OnAbilityQReleased);
	InInput->BindAction(TEXT("AbilityE"), IE_Pressed, this, &ARedPlayerCharacter::OnAbilityE);
	InInput->BindAction(TEXT("AbilityE"), IE_Released, this, &ARedPlayerCharacter::OnAbilityEReleased);
	InInput->BindAction(TEXT("AbilityLoadout"), IE_Pressed, this, &ARedPlayerCharacter::ToggleAbilityLoadout);
	InInput->BindAction(TEXT("EnterVehicle"), IE_Pressed, this, &ARedPlayerCharacter::EnterVehicle);
	InInput->BindAction(TEXT("EnterMiniFighter"), IE_Pressed, this, &ARedPlayerCharacter::EnterMiniFighter);
	InInput->BindAction(TEXT("SpawnEnemies"), IE_Pressed, this, &ARedPlayerCharacter::OnSpawnEnemiesKey);
	InInput->BindAction(TEXT("OrbitDrop"), IE_Pressed, this, &ARedPlayerCharacter::RestartOrbitalDrop);
	InInput->BindAction(TEXT("FastDayNightTest"), IE_Pressed, this, &ARedPlayerCharacter::ToggleFastDayNightTest);
#if !UE_BUILD_SHIPPING
	InInput->BindAction(TEXT("ShorelineVisualTest"), IE_Pressed, this, &ARedPlayerCharacter::TeleportToShorelineVisualTest);
#endif
	InInput->BindAction(TEXT("Hoverboard"), IE_Pressed, this, &ARedPlayerCharacter::ToggleHoverboard);
	InInput->BindAction(TEXT("CharacterCreator"), IE_Pressed, this, &ARedPlayerCharacter::ToggleCharacterCreator);
}

void ARedPlayerCharacter::EnterVehicle()
{
	if (bDowned)
	{
		return;
	}
	if (!HasAuthority())
	{
		ServerEnterVehicle();
		return;
	}

	// B/V is one interaction across every RED craft. Prefer the vehicle the player is looking at,
	// then fall back to physical hull distance when none is reasonably centered. Hull distance alone
	// cannot disambiguate a mini fighter parked inside a shuttle bay: the character is frequently
	// zero centimetres from the shuttle's large box, so the carrier used to steal every board press.
	struct FBoardCandidate
	{
		AActor* Actor = nullptr;
		ARedShip* Ship = nullptr;
		bool bShuttle = false;
		bool bMiniFighter = false;
		float DistanceSquared = TNumericLimits<float>::Max();
		float AimDistanceSquared = TNumericLimits<float>::Max();
		float AimDot = -1.f;
	};

	const FVector Me = GetActorLocation();
	FVector ViewOrigin = Me;
	FRotator EyeRotation = GetActorRotation();
	GetActorEyesViewPoint(ViewOrigin, EyeRotation);
	const FVector ViewForward = GetController()
		? GetController()->GetControlRotation().Vector().GetSafeNormal()
		: EyeRotation.Vector().GetSafeNormal();
	const float MaxDistSq = FMath::Square(FMath::Max(0.f, VehicleBoardRadius));
	constexpr float IntentionalLookDot = 0.55f;

	TArray<FBoardCandidate> Candidates;
	int32 PlayerOccupiedShipCount = 0;
	TArray<AActor*> Ships;
	UGameplayStatics::GetAllActorsOfClass(GetWorld(), ARedShip::StaticClass(), Ships);
	for (AActor* A : Ships)
	{
		ARedShip* Ship = Cast<ARedShip>(A);
		if (!IsValid(Ship) || Ship->IsActorBeingDestroyed()
			|| Ship->GetHealthFraction() <= 0.f)
		{
			continue;
		}
		// A placed Blueprint craft can carry a harmless AI/default controller. Treat only a
		// real player controller as an occupied seat; possession will safely replace an AI
		// controller when the interacting player boards. The old any-controller test made
		// BP_RedModularStarSparrow permanently invisible to B/V selection.
		if (const AController* ExistingController = Ship->GetController();
			ExistingController && ExistingController->IsPlayerController())
		{
			++PlayerOccupiedShipCount;
			continue;
		}
		const float DistanceSquared = VehicleBoardingDistanceSquared(Ship, Me);
		if (DistanceSquared <= MaxDistSq)
		{
			FBoardCandidate& Candidate = Candidates.AddDefaulted_GetRef();
			Candidate.Actor = Ship;
			Candidate.Ship = Ship;
			Candidate.bMiniFighter = Ship->IsA<ARedMiniFighter>();
			Candidate.DistanceSquared = DistanceSquared;
			Candidate.AimDistanceSquared = FVector::DistSquared(
				VehicleBoardingAimPoint(Ship), ViewOrigin);
			Candidate.AimDot = VehicleBoardingAimDot(Ship, ViewOrigin, ViewForward);
		}
	}

	TArray<AActor*> Shuttles;
	UGameplayStatics::GetAllActorsOfClass(GetWorld(), ARedShuttleBase::StaticClass(), Shuttles);
	for (AActor* A : Shuttles)
	{
		if (!IsValid(A) || A == this || A->IsActorBeingDestroyed())
		{
			continue;
		}
		if (const ARedShuttleBase* RedShuttle = Cast<ARedShuttleBase>(A);
			RedShuttle && !RedShuttle->CanAcceptBoarding())
		{
			continue;
		}
		const float DistanceSquared = VehicleBoardingDistanceSquared(A, Me);
		if (DistanceSquared <= MaxDistSq)
		{
			FBoardCandidate& Candidate = Candidates.AddDefaulted_GetRef();
			Candidate.Actor = A;
			Candidate.bShuttle = true;
			Candidate.DistanceSquared = DistanceSquared;
			Candidate.AimDistanceSquared = FVector::DistSquared(
				VehicleBoardingAimPoint(A), ViewOrigin);
			Candidate.AimDot = VehicleBoardingAimDot(A, ViewOrigin, ViewForward);
		}
	}

	FBoardCandidate* Selected = nullptr;
	for (FBoardCandidate& Candidate : Candidates)
	{
		if (Candidate.AimDot < IntentionalLookDot)
		{
			continue;
		}
		if (!Selected || Selected->AimDot < IntentionalLookDot
			|| Candidate.AimDot > Selected->AimDot + 0.015f
			|| (FMath::IsNearlyEqual(Candidate.AimDot, Selected->AimDot, 0.015f)
				&& Candidate.AimDistanceSquared < Selected->AimDistanceSquared))
		{
			Selected = &Candidate;
		}
	}
	if (!Selected)
	{
		for (FBoardCandidate& Candidate : Candidates)
		{
			if (!Selected || Candidate.DistanceSquared < Selected->DistanceSquared)
			{
				Selected = &Candidate;
			}
		}
	}

	if (!Selected)
	{
		UE_LOG(LogRedPlayerCharacter, Warning,
			TEXT("Board input found no usable craft: ships=%d candidates=%d playerOccupied=%d radius=%.0fcm"),
			Ships.Num(), Candidates.Num(), PlayerOccupiedShipCount, VehicleBoardRadius);
		return; // No unoccupied vehicle is within the server-authoritative boarding radius.
	}

	UE_LOG(LogRedPlayerCharacter, Display,
		TEXT("Board selection: %s type=%s hullDistance=%.0fcm aimDot=%.3f candidates=%d"),
		*GetNameSafe(Selected->Actor),
		Selected->bShuttle ? TEXT("shuttle")
			: (Selected->bMiniFighter ? TEXT("mini-fighter") : TEXT("fighter")),
		FMath::Sqrt(Selected->DistanceSquared), Selected->AimDot, Candidates.Num());
	if (Selected->Ship)
	{
		Selected->Ship->EnterShip(this);
		return;
	}
	if (Selected->bShuttle)
	{
		TryBoardSpecificShuttle(Selected->Actor);
	}
}

void ARedPlayerCharacter::ServerEnterVehicle_Implementation()
{
	EnterVehicle();
}

void ARedPlayerCharacter::EnterMiniFighter()
{
	if (bDowned)
	{
		return;
	}
	if (!HasAuthority())
	{
		ServerEnterMiniFighter();
		return;
	}

	// F resolves mini fighters only. Prefer the craft under the reticle, then use physical hull
	// distance among mini fighters only. It can never silently select the shuttle around the bay.
	const FVector Me = GetActorLocation();
	FVector ViewOrigin = Me;
	FRotator EyeRotation = GetActorRotation();
	GetActorEyesViewPoint(ViewOrigin, EyeRotation);
	const FVector ViewForward = GetController()
		? GetController()->GetControlRotation().Vector().GetSafeNormal()
		: EyeRotation.Vector().GetSafeNormal();
	const float MaxDistSq = FMath::Square(FMath::Max(0.f, VehicleBoardRadius));

	ARedMiniFighter* Best = nullptr;
	float BestDistanceSq = TNumericLimits<float>::Max();
	float BestAimDot = -1.f;
	for (TActorIterator<ARedMiniFighter> It(GetWorld()); It; ++It)
	{
		ARedMiniFighter* Fighter = *It;
		if (!IsValid(Fighter) || Fighter->IsActorBeingDestroyed()
			|| Fighter->GetHealthFraction() <= 0.f
			|| (Fighter->GetController() && Fighter->GetController()->IsPlayerController()))
		{
			continue;
		}
		const float DistanceSq = VehicleBoardingDistanceSquared(Fighter, Me);
		if (DistanceSq > MaxDistSq)
		{
			continue;
		}
		const float AimDot = VehicleBoardingAimDot(Fighter, ViewOrigin, ViewForward);
		const bool bBetterAim = AimDot >= 0.35f
			&& (BestAimDot < 0.35f || AimDot > BestAimDot + 0.015f);
		const bool bBetterFallback = BestAimDot < 0.35f && AimDot < 0.35f
			&& DistanceSq < BestDistanceSq;
		if (!Best || bBetterAim || bBetterFallback)
		{
			Best = Fighter;
			BestDistanceSq = DistanceSq;
			BestAimDot = AimDot;
		}
	}
	if (!Best)
	{
		// F remains the dedicated mini-fighter key when one is available, but it is also a
		// forgiving interaction fallback for a nearby full-size craft.
		EnterVehicle();
		return;
	}

	UE_LOG(LogRedPlayerCharacter, Display,
		TEXT("Mini-fighter F selection: %s hullDistance=%.0fcm aimDot=%.3f"),
		*GetNameSafe(Best), FMath::Sqrt(BestDistanceSq), BestAimDot);
	Best->EnterShip(this);
}

void ARedPlayerCharacter::ServerEnterMiniFighter_Implementation()
{
	EnterMiniFighter();
}

bool ARedPlayerCharacter::TryBoardShuttle()
{
	UWorld* W = GetWorld();
	if (!W) { return false; }
	// This public helper retains nearest-shuttle behavior for Blueprint automation. Normal B/V input
	// routes through EnterVehicle and passes its already view-selected shuttle to the specific path.
	TArray<AActor*> Shuttles;
	UGameplayStatics::GetAllActorsOfClass(W, ARedShuttleBase::StaticClass(), Shuttles);
	AActor* BestShuttle = nullptr;
	float BestDistSq = FLT_MAX;
	const FVector Me = GetActorLocation();
	for (AActor* A : Shuttles)
	{
		if (!IsValid(A) || A == this || A->IsActorBeingDestroyed())
		{
			continue;
		}
		if (const ARedShuttleBase* RedShuttle = Cast<ARedShuttleBase>(A);
			RedShuttle && !RedShuttle->CanAcceptBoarding())
		{
			continue;
		}
		const float D = VehicleBoardingDistanceSquared(A, Me);
		if (D < BestDistSq) { BestDistSq = D; BestShuttle = A; }
	}
	if (!BestShuttle || BestDistSq > FMath::Square(VehicleBoardRadius))
	{
		return false;
	}
	return TryBoardSpecificShuttle(BestShuttle);
}

bool ARedPlayerCharacter::TryBoardSpecificShuttle(AActor* BestShuttle)
{
	AController* const BoardingController = GetController();
	ARedShuttleBase* const RedShuttle = Cast<ARedShuttleBase>(BestShuttle);
	if (!BoardingController || !IsValid(RedShuttle)
		|| RedShuttle->IsActorBeingDestroyed() || !RedShuttle->CanAcceptBoarding())
	{
		return false;
	}
	const float BestDistSq = VehicleBoardingDistanceSquared(RedShuttle, GetActorLocation());
	if (BestDistSq > FMath::Square(FMath::Max(0.f, VehicleBoardRadius)))
	{
		return false;
	}

	// Boarding is fully native. The purchased single-player StartInteraction graph used
	// PlayerController(0), started latent callbacks, and competed with replicated possession.
	SetHUDSpaceMinimap(true);
	OnBoardedShip(RedShuttle);
	PilotedShuttle = RedShuttle;
	bWasPilotingShuttle = true;

#if 0
	// Invoke BPI_Interactable::StartInteraction(Character=this). Build the param frame from the
	// function's own layout so we never assume struct offsets.
	// Native RED code below owns seating and possession. Do not execute the purchased pack's
	// single-player interaction graph; it starts latent callbacks and selects PlayerController(0).
	if (UFunction* Fn = nullptr)
	{
		void* Parms = FMemory_Alloca(Fn->ParmsSize);
		FMemory::Memzero(Parms, Fn->ParmsSize);
		for (TFieldIterator<FProperty> It(Fn); It && (It->PropertyFlags & CPF_Parm); ++It)
		{
			if (FObjectPropertyBase* OP = CastField<FObjectPropertyBase>(*It))
			{
				OP->SetObjectPropertyValue(OP->ContainerPtrToValuePtr<void>(Parms), this);
				break;   // single object param → the pilot
			}
		}
		BestShuttle->ProcessEvent(Fn, Parms);
	}
#endif

#if 0
	// Enforce the authoritative multiplayer possession contract after the pack graph has applied
	// its seating/door presentation. Possession replication then makes the shuttle autonomous on
	// the correct client, which also activates its chase camera and client-side flight input.
	if (APawn* ShuttlePawn = Cast<APawn>(BestShuttle))
	{
		if (AController* PackSelectedController = ShuttlePawn->GetController();
			PackSelectedController && PackSelectedController != BoardingController)
		{
			const TWeakObjectPtr<APawn> PreviousPawn = PreInteractionPawns.FindRef(PackSelectedController);
			PackSelectedController->UnPossess();
			if (APawn* PawnToRestore = PreviousPawn.Get();
				PawnToRestore && PawnToRestore != ShuttlePawn && PawnToRestore->GetController() == nullptr)
			{
				PackSelectedController->Possess(PawnToRestore);
			}
		}

		if (ShuttlePawn->GetController() != BoardingController)
		{
			BoardingController->Possess(ShuttlePawn);
			UE_LOG(LogRedPlayerCharacter, Display,
				TEXT("Assigned shuttle %s to interacting controller %s"),
				*GetNameSafe(ShuttlePawn), *GetNameSafe(BoardingController));
		}
		if (ARedShuttleBase* RedShuttle = Cast<ARedShuttleBase>(ShuttlePawn))
		{
			RedShuttle->RegisterOccupant(this);
			RedShuttle->EnsureEnginesOn();
		}
	}

	// Pack flight is gated on EngineOn (+ InFlyingElevation). The toggle is InputKey T →
	// ToggleEngines(On/Off), NOT E. Auto-start so boarding isn't a dead stick.
	// Engine state and nozzle presentation are native as well; do not start the legacy timer graph.
#endif
	if (RedShuttle->GetController() != BoardingController)
	{
		BoardingController->Possess(RedShuttle);
		UE_LOG(LogRedPlayerCharacter, Display,
			TEXT("Assigned shuttle %s to interacting controller %s"),
			*GetNameSafe(RedShuttle), *GetNameSafe(BoardingController));
	}
	RedShuttle->RegisterOccupant(this);
	RedShuttle->EnsureEnginesOn();

#if 0
	if (UFunction* EngFn = nullptr)
	{
		void* EngParms = FMemory_Alloca(EngFn->ParmsSize);
		FMemory::Memzero(EngParms, EngFn->ParmsSize);
		for (TFieldIterator<FProperty> It(EngFn); It && (It->PropertyFlags & CPF_Parm); ++It)
		{
			if (FBoolProperty* BP = CastField<FBoolProperty>(*It))
			{
				BP->SetPropertyValue_InContainer(EngParms, true);
				break;
			}
		}
		BestShuttle->ProcessEvent(EngFn, EngParms);
	}
#endif
	if (FBoolProperty* EngineOnProp = FindFProperty<FBoolProperty>(RedShuttle->GetClass(), TEXT("EngineOn")))
	{
		EngineOnProp->SetPropertyValue_InContainer(RedShuttle, true);
	}
	if (FBoolProperty* FlyProp = FindFProperty<FBoolProperty>(RedShuttle->GetClass(), TEXT("InFlyingElevation")))
	{
		FlyProp->SetPropertyValue_InContainer(RedShuttle, true);
	}

	UE_LOG(LogRedPlayerCharacter, Display, TEXT("Boarded shuttle %s (%.0fcm away)"),
		*GetNameSafe(RedShuttle), FMath::Sqrt(BestDistSq));
	return true;
}

void ARedPlayerCharacter::ApplyBody()
{
	USkeletalMeshComponent* M = GetMesh();
	if (!M) { return; }
	const float HalfH = GetCapsuleComponent() ? GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 88.f;
	if (bUseAlienBody && AlienBodyMesh)
	{
		M->SetSkeletalMesh(AlienBodyMesh);
		// Alien pivot is at the feet; scale to fit the capsule, feet at its bottom, faced forward.
		M->SetRelativeLocationAndRotation(FVector(0.f, 0.f, -HalfH), FRotator(0.f, -90.f, 0.f));
		M->SetRelativeScale3D(FVector(AlienBodyScale));
		// No AnimBlueprint for the alien — single-node playback (UpdateAlienLocomotion swaps Idle/Run by speed).
		M->SetAnimInstanceClass(nullptr);
		M->SetAnimationMode(EAnimationMode::AnimationSingleNode);
		bAlienRunning = false;
		if (AlienIdleAnim) { M->PlayAnimation(AlienIdleAnim, true); }
		// Hide trooper-only attachments that ride bones the alien lacks (they'd fling off / read as a suitcase).
		if (WeaponMesh)     { WeaponMesh->SetVisibility(false); }
		SetJetpackVisible(false);
		SetJetpackThrustFX(false);
		if (HoverboardMesh) { HoverboardMesh->SetVisibility(false); }
	}
	else if (TrooperBodyMesh)
	{
		M->SetSkeletalMesh(TrooperBodyMesh);
		M->SetRelativeLocationAndRotation(FVector(0.f, 0.f, -HalfH), FRotator(0.f, -90.f, 0.f));
		M->SetRelativeScale3D(FVector::OneVector);
		// Restore AnimBlueprint mode (may have been left in single-node by the alien / skydive paths).
		M->SetAnimationMode(EAnimationMode::AnimationBlueprint);
		if (TrooperAnimClass) { M->SetAnimInstanceClass(TrooperAnimClass); }
		if (WeaponMesh)
		{
			WeaponMesh->SetHiddenInGame(false, true);
			WeaponMesh->SetVisibility(true, true);
		}
		if (JetpackActor)
		{
			// ApplyBody() also runs from the CDO constructor — AttachToComponent needs registration.
			if (JetpackActor->IsRegistered())
			{
				JetpackActor->AttachToComponent(M, FAttachmentTransformRules::SnapToTargetNotIncludingScale, JetpackSocket);
			}
			else
			{
				JetpackActor->SetupAttachment(M, JetpackSocket);
			}
			JetpackActor->SetRelativeLocationAndRotation(JetpackLocation, JetpackRotation);
			JetpackActor->SetRelativeScale3D(JetpackScale);
			if (JetpackActor->IsRegistered() && !JetpackActor->GetChildActor() && JetpackActor->GetChildActorClass())
			{
				JetpackActor->CreateChildActor();
			}
			SetJetpackVisible(true);
			SetJetpackThrustFX(false);
		}
	}
}

bool ARedPlayerCharacter::IsUsingTrooperBody() const
{
	const USkeletalMeshComponent* CharacterMesh = GetMesh();
	if (!CharacterMesh)
	{
		return false;
	}
	const USkeletalMesh* Current = CharacterMesh->GetSkeletalMeshAsset();
	return Current && (Current == TrooperBodyMesh || Current == TrooperUpperBodyMesh);
}

void ARedPlayerCharacter::SetJetpackVisible(bool bVisible)
{
	if (JetpackActor)
	{
		JetpackActor->SetVisibility(bVisible, true);
		JetpackActor->SetHiddenInGame(!bVisible, true);
		if (AActor* Pack = JetpackActor->GetChildActor())
		{
			Pack->SetActorHiddenInGame(!bVisible);
			TArray<UPrimitiveComponent*> PrimComps;
			Pack->GetComponents<UPrimitiveComponent>(PrimComps);
			for (UPrimitiveComponent* Prim : PrimComps)
			{
				if (!Prim) { continue; }
				// Keep exhaust/audio hidden until thrust — only show the pack mesh when visible.
				if (Prim->IsA<UParticleSystemComponent>() || Prim->IsA<UAudioComponent>())
				{
					continue;
				}
				Prim->SetVisibility(bVisible);
				Prim->SetHiddenInGame(!bVisible);
			}
		}
	}
	// Legacy static mesh stays hidden always.
	if (JetpackMesh)  { JetpackMesh->SetVisibility(false);  JetpackMesh->SetHiddenInGame(true); }
	if (JetpackTankL) { JetpackTankL->SetVisibility(false); JetpackTankL->SetHiddenInGame(true); }
	if (JetpackTankR) { JetpackTankR->SetVisibility(false); JetpackTankR->SetHiddenInGame(true); }
}

void ARedPlayerCharacter::EnsureJetpackExhaustAttached()
{
	AActor* Pack = JetpackActor ? JetpackActor->GetChildActor() : nullptr;
	if (!Pack)
	{
		bJetpackExhaustAttached = false;
		return;
	}

	USkeletalMeshComponent* PackMesh = Pack->FindComponentByClass<USkeletalMeshComponent>();
	if (!PackMesh)
	{
		bJetpackExhaustAttached = false;
		return;
	}

	auto IsOurExhaust = [this](const UParticleSystemComponent* PSC) -> bool
	{
		return PSC == JetpackExhaust || PSC == JetpackExhaustL || PSC == JetpackExhaustR;
	};
	auto IsExhaustFX = [](const UParticleSystemComponent* PSC) -> bool
	{
		if (!PSC) { return false; }
		if (PSC->Template)
		{
			const FString N = PSC->Template->GetName();
			if (N.Contains(TEXT("Exhaust")) || N.Contains(TEXT("Jet_Exhaust")))
			{
				return true;
			}
		}
		const FString CompName = PSC->GetName();
		return CompName.Contains(TEXT("Exhaust")) || CompName.Contains(TEXT("JetpackExhaust"));
	};
	auto SuppressExhaustPSC = [](UParticleSystemComponent* PSC)
	{
		if (!PSC) { return; }
		PSC->Deactivate();
		PSC->SetVisibility(false);
		PSC->SetHiddenInGame(true);
		PSC->SetComponentTickEnabled(false);
		PSC->SetTemplate(nullptr);
	};

	// Sci-Fi Master BP "Spawn exhausts" parents Cascade to the OWNER character's Exhaust_* sockets
	// (demo mannequin hip/hand sockets) — that is the left-hip triple plume. Kill those every seat.
	TArray<UParticleSystemComponent*> CharParticles;
	GetComponents<UParticleSystemComponent>(CharParticles);
	for (UParticleSystemComponent* PSC : CharParticles)
	{
		if (!PSC || IsOurExhaust(PSC)) { continue; }
		if (IsExhaustFX(PSC))
		{
			SuppressExhaustPSC(PSC);
		}
	}
	TArray<UParticleSystemComponent*> PackParticles;
	Pack->GetComponents<UParticleSystemComponent>(PackParticles);
	for (UParticleSystemComponent* PSC : PackParticles)
	{
		if (!PSC || IsOurExhaust(PSC)) { continue; }
		SuppressExhaustPSC(PSC);
	}

	// Keep pack BP from re-spawning owner-socket exhaust while we drive nozzle locals.
	for (const FName PropName : { FName(TEXT("bThrustersOn")), FName(TEXT("ThrustersOn")),
		FName(TEXT("bExhaustOn")), FName(TEXT("EngineOn")), FName(TEXT("bFlying")),
		FName(TEXT("Jetpack Flying")), FName(TEXT("Jetpack_Flying")) })
	{
		if (FBoolProperty* BP = FindFProperty<FBoolProperty>(Pack->GetClass(), PropName))
		{
			BP->SetPropertyValue_InContainer(Pack, false);
		}
	}

	// SK_Angular Exhaust_L/R = nozzle bottoms. Seat Cascade fire+smoke there with absolute
	// MakeFromX(actor-down). Kill pack-BP Cascade (hip sockets) but keep OUR locals.
	const FName SockL(TEXT("Exhaust_L"));
	const FName SockR(TEXT("Exhaust_R"));
	const bool bHasL = PackMesh->DoesSocketExist(SockL);
	const bool bHasR = PackMesh->DoesSocketExist(SockR);
	const FVector PlumeDir = -GetActorUpVector().GetSafeNormal();
	// Cascade Jet_Exhaust_PS emits along local +X — aim +X = actor-down.
	const FRotator PlumeWorldRot = PlumeDir.IsNearlyZero()
		? FRotator(0.f, 0.f, 0.f)
		: FRotationMatrix::MakeFromX(PlumeDir).Rotator();
	const float PlumeScale = 0.85f;

	auto HideCone = [](UStaticMeshComponent* Cone)
	{
		if (!Cone) { return; }
		Cone->SetVisibility(false);
		Cone->SetHiddenInGame(true);
	};
	HideCone(JetpackPlumeCone);
	HideCone(JetpackPlumeConeL);
	HideCone(JetpackPlumeConeR);

	auto SeatPSC = [&](UParticleSystemComponent* PSC, const FVector& WorldLoc)
	{
		if (!PSC) { return; }
		if (JetpackExhaustFX && PSC->Template != JetpackExhaustFX)
		{
			PSC->SetTemplate(JetpackExhaustFX);
		}
		PSC->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
		PSC->AttachToComponent(PackMesh, FAttachmentTransformRules::KeepWorldTransform, NAME_None);
		PSC->SetUsingAbsoluteRotation(true);
		PSC->SetWorldLocation(WorldLoc);
		PSC->SetWorldRotation(PlumeWorldRot);
		PSC->SetRelativeScale3D(FVector(PlumeScale));
		// Heat-refraction spheres warp the legs — keep fire+smoke, drop distortion.
		PSC->SetEmitterEnable(TEXT("Refraction Spheres"), false);
		PSC->SetEmitterEnable(TEXT("Refraction"), false);
		PSC->SetVisibility(false);
		PSC->SetHiddenInGame(true);
		PSC->SetComponentTickEnabled(true);
	};

	if (bHasL && bHasR)
	{
		const FVector LocL = PackMesh->GetSocketLocation(SockL);
		const FVector LocR = PackMesh->GetSocketLocation(SockR);
		const FVector LocM = 0.5f * (LocL + LocR);
		SeatPSC(JetpackExhaustL, LocL);
		SeatPSC(JetpackExhaustR, LocR);
		SeatPSC(JetpackExhaust, LocM);
	}
	else
	{
		const FBox LocalBounds = PackMesh->GetLocalBounds().GetBox();
		const float Z = LocalBounds.Min.Z + 2.f;
		const float Y = FMath::Max(8.f, LocalBounds.GetExtent().Y * 0.35f);
		const FTransform MeshXform = PackMesh->GetComponentTransform();
		SeatPSC(JetpackExhaust, MeshXform.TransformPosition(FVector(0.f, 0.f, Z)));
		SeatPSC(JetpackExhaustL, MeshXform.TransformPosition(FVector(0.f, -Y, Z)));
		SeatPSC(JetpackExhaustR, MeshXform.TransformPosition(FVector(0.f, Y, Z)));
	}

	if (JetpackFlame)
	{
		JetpackFlame->Deactivate();
		JetpackFlame->SetVisibility(false);
		JetpackFlame->SetHiddenInGame(true);
	}

	bJetpackExhaustAttached = true;
	UE_LOG(LogRedPlayerCharacter, Display,
		TEXT("EnsureJetpackExhaustAttached: Cascade Jet_Exhaust_PS on pack=%s sockets L=%d R=%d (cones hidden)"),
		*Pack->GetName(), bHasL ? 1 : 0, bHasR ? 1 : 0);
}

void ARedPlayerCharacter::SetJetpackThrustFX(bool bOn)
{
	EnsureJetpackExhaustAttached();

	AActor* Pack = JetpackActor ? JetpackActor->GetChildActor() : nullptr;
	if (Pack)
	{
		// Never arm Master BP thruster bools — that re-spawns Cascade on owner hip sockets.
		for (const FName PropName : { FName(TEXT("bThrustersOn")), FName(TEXT("ThrustersOn")),
			FName(TEXT("bExhaustOn")), FName(TEXT("EngineOn")), FName(TEXT("bFlying")),
			FName(TEXT("Jetpack Flying")), FName(TEXT("Jetpack_Flying")) })
		{
			if (FBoolProperty* BP = FindFProperty<FBoolProperty>(Pack->GetClass(), PropName))
			{
				BP->SetPropertyValue_InContainer(Pack, false);
			}
		}

		// Keep pack-native Cascade suppressed (we drive nozzle-seated locals only).
		TArray<UParticleSystemComponent*> PackParticles;
		Pack->GetComponents<UParticleSystemComponent>(PackParticles);
		for (UParticleSystemComponent* PSC : PackParticles)
		{
			if (!PSC) { continue; }
			if (PSC == JetpackExhaust || PSC == JetpackExhaustL || PSC == JetpackExhaustR) { continue; }
			PSC->Deactivate();
			PSC->SetVisibility(false);
			PSC->SetHiddenInGame(true);
		}

		// Re-suppress any owner-hip exhaust the pack BP may have just spawned.
		TArray<UParticleSystemComponent*> CharParticles;
		GetComponents<UParticleSystemComponent>(CharParticles);
		for (UParticleSystemComponent* PSC : CharParticles)
		{
			if (!PSC || PSC == JetpackExhaust || PSC == JetpackExhaustL || PSC == JetpackExhaustR)
			{
				continue;
			}
			if (PSC->Template && (PSC->Template->GetName().Contains(TEXT("Exhaust"))
				|| PSC->Template->GetName().Contains(TEXT("Jet_Exhaust"))))
			{
				PSC->Deactivate();
				PSC->SetVisibility(false);
				PSC->SetHiddenInGame(true);
				PSC->SetTemplate(nullptr);
			}
		}

		TArray<UAudioComponent*> Audios;
		Pack->GetComponents<UAudioComponent>(Audios);
		for (UAudioComponent* Aud : Audios)
		{
			if (!Aud) { continue; }
			// Pack BP audio is often a one-shot / shared-concurrency cue that weapon fire
			// steals — keep it silent; our JetpackThrustAudio owns the continuous loop.
			Aud->Stop();
			Aud->SetVisibility(false);
		}
	}

	// Cascade fire+smoke on nozzles; cyan cones stay hidden.
	const FVector PlumeDir = -GetActorUpVector().GetSafeNormal();
	const FRotator PlumeWorldRot = PlumeDir.IsNearlyZero()
		? FRotator(0.f, 0.f, 0.f)
		: FRotationMatrix::MakeFromX(PlumeDir).Rotator();
	const float PlumeScale = bSprintHeld ? 1.15f : 0.85f;

	auto HideCone = [](UStaticMeshComponent* Cone)
	{
		if (!Cone) { return; }
		Cone->SetVisibility(false);
		Cone->SetHiddenInGame(true);
	};
	HideCone(JetpackPlumeCone);
	HideCone(JetpackPlumeConeL);
	HideCone(JetpackPlumeConeR);

	auto DrivePSC = [bOn, &PlumeWorldRot, PlumeScale](UParticleSystemComponent* PSC)
	{
		if (!PSC) { return; }
		PSC->SetRelativeScale3D(FVector(PlumeScale));
		PSC->SetWorldRotation(PlumeWorldRot);
		PSC->SetEmitterEnable(TEXT("Refraction Spheres"), false);
		PSC->SetEmitterEnable(TEXT("Refraction"), false);
		if (bOn)
		{
			PSC->SetVisibility(true);
			PSC->SetHiddenInGame(false);
			PSC->SetComponentTickEnabled(true);
			if (!PSC->IsActive())
			{
				PSC->Activate(true);
			}
		}
		else
		{
			PSC->Deactivate();
			PSC->SetVisibility(false);
			PSC->SetHiddenInGame(true);
		}
	};
	DrivePSC(JetpackExhaust);
	DrivePSC(JetpackExhaustL);
	DrivePSC(JetpackExhaustR);

	if (JetpackFlame)
	{
		JetpackFlame->Deactivate();
		JetpackFlame->SetVisibility(false);
		JetpackFlame->SetHiddenInGame(true);
	}

	if (JetpackThrustAudio)
	{
		if (bOn && GetNetMode() != NM_DedicatedServer)
		{
			JetpackThrustAudio->bIsUISound = false;
			JetpackThrustAudio->SetUISound(false);
			JetpackThrustAudio->bAllowSpatialization = true;
			JetpackThrustAudio->SetVolumeMultiplier(bSprintHeld ? 1.4f : 1.0f);
			JetpackThrustAudio->SetPitchMultiplier(bSprintHeld ? 1.15f : 1.0f);
			if (!JetpackThrustAudio->IsPlaying())
			{
				JetpackThrustAudio->Play();
			}
		}
		else
		{
			JetpackThrustAudio->Stop();
		}
	}
}

void ARedPlayerCharacter::UpdateJetpackFlightAnim(bool bCombatAim)
{
	if (!IsUsingTrooperBody() || bUseAlienBody || bSkydiving || bOrbitalDropActive || bDowned)
	{
		return;
	}
	USkeletalMeshComponent* M = GetMesh();
	if (!M) { return; }
	(void)bCombatAim;

	const bool bAirJet = bJetpackOn && GetCharacterMovement()
		&& GetCharacterMovement()->IsFalling();
	// Hover/thrust pose — NOT Mixamo skydive. Prefer Jump_Loop as a temporary standing-hover
	// until a real Mixamo jetpack hover / flying idle is imported.
	// CRITICAL: drop Jump_Loop while combat-aiming so AnimBP weapon-aim pose can drive arms.
	// (A prior "hiccup" fix froze Jump_Loop for all airborne time → open-hand shoot pose.)
	// Keep the project trooper AnimBP active in flight. PlanetGen's Manny-only sequence bypasses
	// the rifle overlay and is on a different skeleton; the AnimBP jump state supplies the legs.
	const bool bWantFlyPose = bAirJet && false;
	if (bWantFlyPose == bJetpackFlyAnimOn)
	{
		return;
	}
	bJetpackFlyAnimOn = bWantFlyPose;
	if (bWantFlyPose)
	{
		if (!JetpackHoverAnim)
		{
			JetpackHoverAnim = LoadObject<UAnimSequence>(nullptr,
				TEXT("/PlanetGen/Characters/Mannequins/Animations/Manny/Flying/A_Flying_Idle.A_Flying_Idle"));
		}
		if (JetpackHoverAnim)
		{
			M->PlayAnimation(JetpackHoverAnim, true);
		}
		else
		{
			// Last resort: keep AnimBP rather than skydive freefall.
			M->SetAnimationMode(EAnimationMode::AnimationBlueprint);
		}
	}
	else
	{
		M->SetAnimationMode(EAnimationMode::AnimationBlueprint);
		if (TrooperAnimClass && M->GetAnimClass() != TrooperAnimClass)
		{
			M->SetAnimInstanceClass(TrooperAnimClass);
		}
	}
}

void ARedPlayerCharacter::SwapBody()
{
	bUseAlienBody = !bUseAlienBody;
	ApplyBody();
	UE_LOG(LogRedPlayerCharacter, Display, TEXT("SwapBody -> %s"), bUseAlienBody ? TEXT("ALIEN") : TEXT("TROOPER"));
}

void ARedPlayerCharacter::UpdateAlienLocomotion()
{
	// The alien has no AnimBlueprint; swap its single-node Idle/Run sequences by ground speed.
	if (!bUseAlienBody) { return; }
	USkeletalMeshComponent* M = GetMesh();
	if (!M || !AlienIdleAnim || !AlienRunAnim) { return; }
	// Skip while airborne — the skydive/jump paths drive the mesh then; resume on the ground.
	if (const UCharacterMovementComponent* Move = GetCharacterMovement())
	{
		if (Move->MovementMode == MOVE_Falling) { return; }
	}
	const float Speed = GetVelocity().Size();
	// Hysteresis so we don't flip-flop right at the threshold.
	const bool bWantRun = bAlienRunning ? (Speed > 60.f) : (Speed > 140.f);
	if (bWantRun != bAlienRunning || M->GetAnimationMode() != EAnimationMode::AnimationSingleNode)
	{
		bAlienRunning = bWantRun;
		M->PlayAnimation(bAlienRunning ? AlienRunAnim : AlienIdleAnim, true);
	}
}

void ARedPlayerCharacter::SelectWeapon(int32 Slot)
{
	if (bDowned || bAbilityLoadoutOpen || !WeaponMesh
		|| !WeaponSlotMeshes.IsValidIndex(Slot) || !WeaponSlotMeshes[Slot]
		|| Slot == CurrentWeaponSlot)
	{
		return;
	}

	// A held-fire timer belongs to the old gun. Always stop it before predicting or accepting a swap.
	StopFiring();
	CurrentWeaponSlot = Slot;
	ApplyCurrentWeaponSlot();
	if (HasAuthority())
	{
		ForceNetUpdate();
	}
	else
	{
		ServerSelectWeapon(Slot);
	}
}

void ARedPlayerCharacter::ServerSelectWeapon_Implementation(const int32 Slot)
{
	if (bDowned || !WeaponMesh || !WeaponSlotMeshes.IsValidIndex(Slot) || !WeaponSlotMeshes[Slot])
	{
		return;
	}
	GetWorldTimerManager().ClearTimer(FireTimerHandle);
	bIsFiringHeld = false;
	bReplicatedAimHeld = false;
	CurrentWeaponSlot = Slot;
	ApplyCurrentWeaponSlot();
	ForceNetUpdate();
}

void ARedPlayerCharacter::EnsureWeaponSlotState()
{
	while (WeaponSlotHeat.Num() < 2)
	{
		WeaponSlotHeat.Add(0.0f);
	}
	while (WeaponSlotOverheated.Num() < 2)
	{
		WeaponSlotOverheated.Add(0);
	}
	if (WeaponSlotHeat.Num() > 2)
	{
		WeaponSlotHeat.SetNum(2);
	}
	if (WeaponSlotOverheated.Num() > 2)
	{
		WeaponSlotOverheated.SetNum(2);
	}
}

float ARedPlayerCharacter::GetWeaponHeatForSlot(const int32 Slot) const
{
	return WeaponSlotHeat.IsValidIndex(Slot) ? FMath::Max(0.0f, WeaponSlotHeat[Slot]) : 0.0f;
}

bool ARedPlayerCharacter::IsWeaponSlotOverheated(const int32 Slot) const
{
	return WeaponSlotOverheated.IsValidIndex(Slot) && WeaponSlotOverheated[Slot] != 0;
}

float ARedPlayerCharacter::GetWeaponHeatNormalized() const
{
	return MaxWeaponHeat > 0.0f
		? FMath::Clamp(GetWeaponHeatForSlot(CurrentWeaponSlot) / MaxWeaponHeat, 0.0f, 1.0f)
		: 0.0f;
}

bool ARedPlayerCharacter::IsWeaponOverheated() const
{
	return IsWeaponSlotOverheated(CurrentWeaponSlot);
}

void ARedPlayerCharacter::ApplyCurrentWeaponSlot()
{
	const int32 SafeSlot = FMath::Clamp(CurrentWeaponSlot, 0, 1);
	if (WeaponMesh && WeaponSlotMeshes.IsValidIndex(SafeSlot) && WeaponSlotMeshes[SafeSlot])
	{
		WeaponMesh->SetSkeletalMesh(WeaponSlotMeshes[SafeSlot]);
		WeaponMesh->SetUsingAbsoluteRotation(bAlignWeaponBarrelToCamera);
	}
	if (ActiveHUDWidget)
	{
		ActiveHUDWidget->SetSelectedWeaponSlot(SafeSlot);
	}
	RefreshAbilityLoadoutForWeapon();
}

void ARedPlayerCharacter::OnRep_CurrentWeaponSlot()
{
	GetWorldTimerManager().ClearTimer(FireTimerHandle);
	bIsFiringHeld = false;
	ApplyCurrentWeaponSlot();
}

void ARedPlayerCharacter::OnRep_WeaponHeatState()
{
	EnsureWeaponSlotState();
	UpdateHUDStatus();
}

void ARedPlayerCharacter::ToggleCharacterCreator()
{
	if (OpenCharacterCreatorFromMenu())
	{
		return;
	}

	// Development fallback when the optional Fab pack is absent or its controller failed to load.
	SwapBody();
}

bool ARedPlayerCharacter::CanOpenCharacterCreator() const
{
	const APlayerController* PlayerController = Cast<APlayerController>(Controller);
	return PlayerController
		&& PlayerController->FindFunction(TEXT("ToggleCharacterWindow")) != nullptr;
}

bool ARedPlayerCharacter::OpenCharacterCreatorFromMenu()
{
	APlayerController* PlayerController = Cast<APlayerController>(Controller);
	if (!PlayerController)
	{
		return false;
	}

	// Implemented by PO-Art's BP_PlayerController_Advanced_Customisation. Calling by
	// reflection keeps the RedMMO C++ module independent of a vendor Blueprint class.
	UFunction* ToggleFunction = PlayerController->FindFunction(TEXT("ToggleCharacterWindow"));
	if (!ToggleFunction)
	{
		return false;
	}

	PlayerController->ProcessEvent(ToggleFunction, nullptr);
	UpdateCreatorWeaponVisibility();
	UE_LOG(LogRedPlayerCharacter, Display, TEXT("Character creator toggled from the game menu"));
	return true;
}

void ARedPlayerCharacter::UpdateCreatorWeaponVisibility()
{
	if (!CreatorWeaponMesh)
	{
		return;
	}

	const bool bIsCreatorPreview = GetClass()->GetName().Contains(TEXT("Character_Preview"));
	if (!bIsCreatorPreview)
	{
		// Gameplay always fires RED's native Action Trooper rifle.
		CreatorWeaponMesh->SetHiddenInGame(true, true);
		CreatorWeaponMesh->SetVisibility(false, true);
		return;
	}

	// In the creator preview, a selected vendor weapon takes the native rifle's place. The
	// Unequipped row leaves SK_Weapon hidden, so the native Rifle A remains the preview fallback.
	const bool bVendorWeaponVisible = CreatorWeaponMesh->GetSkeletalMeshAsset()
		&& CreatorWeaponMesh->IsVisible()
		&& !CreatorWeaponMesh->bHiddenInGame;
	if (WeaponMesh)
	{
		WeaponMesh->SetHiddenInGame(bVendorWeaponVisible, true);
		WeaponMesh->SetVisibility(!bVendorWeaponVisible, true);
	}
}

void ARedPlayerCharacter::RefreshAbilityLoadoutForWeapon()
{
	if (!ActiveHUDWidget)
	{
		return;
	}

	for (int32 Index = 0; Index < 2; ++Index)
	{
		const ERedPlayerAbility Ability = GetAbilityForSlot(Index);
		UTexture2D* Texture = Ability == ERedPlayerAbility::Grapple
			? GrappleAbilityIcon.Get() : SlamAbilityIcon.Get();
		if (Texture)
		{
			ActiveHUDWidget->SetAbilityIconResource(Index, Texture);
		}
		else
		{
			ActiveHUDWidget->SetAbilitySlotVisible(Index, true);
		}
		ActiveHUDWidget->SetAbilitySlotLabel(Index, FText::FromString(
			Ability == ERedPlayerAbility::Grapple ? TEXT("GRAPPLE") : TEXT("SLAM")));
	}
	// The launch combat bar has exactly Q/E. R/F/X remain truly absent rather than decorative cells.
	for (int32 Index = 2; Index < 5; ++Index)
	{
		ActiveHUDWidget->ClearAbilitySlot(Index);
	}
	ActiveHUDWidget->SetAbilityKeyLabels(
		FText::FromString(TEXT("Q")), FText::FromString(TEXT("E")),
		FText::GetEmpty(), FText::GetEmpty(), FText::GetEmpty());
	ActiveHUDWidget->SetAbilityLoadoutOverlayVisible(
		bAbilityLoadoutOpen, AbilitySlotQ == ERedPlayerAbility::Grapple);
	UpdateAbilityHUD();
}

void ARedPlayerCharacter::OnAbilityQ()
{
	TryActivateAbilitySlot(0);
}

void ARedPlayerCharacter::OnAbilityE()
{
	TryActivateAbilitySlot(1);
}

void ARedPlayerCharacter::OnAbilityQReleased()
{
	StopAbilitySlot(0);
}

void ARedPlayerCharacter::OnAbilityEReleased()
{
	StopAbilitySlot(1);
}

ERedPlayerAbility ARedPlayerCharacter::GetAbilityForSlot(const int32 Slot) const
{
	return Slot == 0 ? AbilitySlotQ : AbilitySlotE;
}

int32 ARedPlayerCharacter::FindAbilitySlot(const ERedPlayerAbility Ability) const
{
	if (AbilitySlotQ == Ability) { return 0; }
	if (AbilitySlotE == Ability) { return 1; }
	return INDEX_NONE;
}

float ARedPlayerCharacter::GetAbilityCooldownDuration(const ERedPlayerAbility Ability) const
{
	return Ability == ERedPlayerAbility::Grapple ? GrappleCooldown : SlamCooldown;
}

float ARedPlayerCharacter::GetAbilityCooldownEnd(const ERedPlayerAbility Ability) const
{
	return Ability == ERedPlayerAbility::Grapple
		? GrappleCooldownEndServerTime : SlamCooldownEndServerTime;
}

float ARedPlayerCharacter::GetAbilityClockSeconds() const
{
	if (const UWorld* World = GetWorld())
	{
		if (const AGameStateBase* GameState = World->GetGameState())
		{
			return GameState->GetServerWorldTimeSeconds();
		}
		return World->GetTimeSeconds();
	}
	return 0.0f;
}

void ARedPlayerCharacter::SetPredictedAbilityCooldown(
	const ERedPlayerAbility Ability, const float EndTime)
{
	if (Ability == ERedPlayerAbility::Grapple)
	{
		GrappleCooldownEndServerTime = EndTime;
	}
	else
	{
		SlamCooldownEndServerTime = EndTime;
	}
	UpdateAbilityHUD();
}

void ARedPlayerCharacter::UpdateAbilityHUD(ARedHUD* ReplacementHUD)
{
	if (!ReplacementHUD)
	{
		APlayerController* HUDPlayerController = Cast<APlayerController>(GetController());
		if (!HUDPlayerController && ActiveHUDWidget)
		{
			HUDPlayerController = ActiveHUDWidget->GetOwningPlayer();
		}
		if (HUDPlayerController && HUDPlayerController->IsLocalController())
		{
			ReplacementHUD = Cast<ARedHUD>(HUDPlayerController->GetHUD());
		}
	}

	if (!ActiveHUDWidget && !ReplacementHUD)
	{
		return;
	}

	const float Now = GetAbilityClockSeconds();
	const bool bAbilityDisabled = bDowned || bAbilityLoadoutOpen;
	for (int32 Slot = 0; Slot < 2; ++Slot)
	{
		const ERedPlayerAbility Ability = GetAbilityForSlot(Slot);
		const float Remaining = FMath::Max(0.0f, GetAbilityCooldownEnd(Ability) - Now);
		const float Duration = GetAbilityCooldownDuration(Ability);
		if (ActiveHUDWidget)
		{
			ActiveHUDWidget->SetAbilityCooldownState(Slot, Remaining, Duration);
		}
		if (ReplacementHUD)
		{
			// Replacement index 0 is Ultimate; Q and E are indices 1 and 2.
			ReplacementHUD->UpdateReplacementHUDAbilityState(
				Slot + 1, Remaining, Duration, bAbilityDisabled);
		}
	}
}

bool ARedPlayerCharacter::TryActivateAbilitySlot(const int32 Slot)
{
	if (Slot < 0 || Slot > 1 || bDowned || bAbilityLoadoutOpen || !GetWorld())
	{
		return false;
	}
	const ERedPlayerAbility Ability = GetAbilityForSlot(Slot);
	const float Now = GetAbilityClockSeconds();
	if (GetAbilityCooldownEnd(Ability) > Now)
	{
		return false;
	}

	const FVector TraceOrigin = Camera ? Camera->GetComponentLocation() : GetActorLocation();
	const FVector TraceDirection = Camera ? Camera->GetForwardVector() : GetActorForwardVector();
	if (HasAuthority())
	{
		return ActivateAbilityAuthoritative(Slot, TraceOrigin, TraceDirection);
	}

	// Predict only reversible owner movement and the local cooldown presentation. Damage, accepted
	// grapple anchor, and replicated state remain server-owned.
	if (Ability == ERedPlayerAbility::Grapple)
	{
		FVector PredictedPoint;
		FVector PredictedNormal;
		ARedPlayerCharacter* PredictedTarget = nullptr;
		if (bGrappling || !FindValidGrapplePoint(
			TraceOrigin, TraceDirection, PredictedPoint, PredictedNormal, PredictedTarget))
		{
			return false;
		}
		StartGrapple(PredictedPoint, PredictedNormal, PredictedTarget);
	}
	else
	{
		StartSlam();
		if (!bSlamming)
		{
			return false;
		}
	}

	SetPredictedAbilityCooldown(Ability, Now + GetAbilityCooldownDuration(Ability));
	ServerActivateAbility(Slot, TraceOrigin, TraceDirection.GetSafeNormal());
	return true;
}

bool ARedPlayerCharacter::ActivateAbilityAuthoritative(const int32 Slot,
	const FVector& TraceOrigin, const FVector& TraceDirection)
{
	if (!HasAuthority() || Slot < 0 || Slot > 1 || bDowned || !GetWorld())
	{
		return false;
	}
	const ERedPlayerAbility Ability = GetAbilityForSlot(Slot);
	const float Now = GetAbilityClockSeconds();
	if (GetAbilityCooldownEnd(Ability) > Now)
	{
		return false;
	}

	if (Ability == ERedPlayerAbility::Grapple)
	{
		const FVector SafeDirection = TraceDirection.GetSafeNormal();
		if (bGrappling || TraceOrigin.ContainsNaN() || SafeDirection.IsNearlyZero()
			|| FVector::DistSquared(TraceOrigin, GetActorLocation()) > FMath::Square(1600.0f))
		{
			return false;
		}
		FVector ServerPoint;
		FVector ServerNormal;
		ARedPlayerCharacter* ServerTarget = nullptr;
		if (!FindValidGrapplePoint(TraceOrigin, SafeDirection,
			ServerPoint, ServerNormal, ServerTarget))
		{
			return false;
		}
		StartGrapple(ServerPoint, ServerNormal, ServerTarget);
		if (ServerTarget)
		{
			UGameplayStatics::ApplyDamage(ServerTarget, FMath::Max(0.f, GrapplePlayerDamage),
				GetController(), this,
				GrappleDamageType ? GrappleDamageType
					: TSubclassOf<UDamageType>(UDamageType::StaticClass()));
			// A lethal accepted hit still consumes the ability, but never drags a ragdoll.
			if (ServerTarget->IsDowned())
			{
				StopGrapple(false);
			}
		}
	}
	else
	{
		StartSlam();
		if (!bSlamming)
		{
			return false;
		}
	}

	SetPredictedAbilityCooldown(Ability, Now + GetAbilityCooldownDuration(Ability));
	ForceNetUpdate();
	return true;
}

void ARedPlayerCharacter::ServerActivateAbility_Implementation(const int32 Slot,
	FVector_NetQuantize TraceOrigin, FVector_NetQuantizeNormal TraceDirection)
{
	if (!ActivateAbilityAuthoritative(Slot, TraceOrigin, TraceDirection))
	{
		ClientRejectAbilityActivation(Slot);
	}
}

void ARedPlayerCharacter::ClientRejectAbilityActivation_Implementation(const int32 Slot)
{
	if (Slot < 0 || Slot > 1)
	{
		return;
	}
	const ERedPlayerAbility Ability = GetAbilityForSlot(Slot);
	SetPredictedAbilityCooldown(Ability, 0.0f);
	if (Ability == ERedPlayerAbility::Grapple && bGrappling)
	{
		StopGrapple(false);
	}
	else if (Ability == ERedPlayerAbility::Slam)
	{
		bSlamming = false;
		SlamWindupRemaining = 0.f;
		GetWorldTimerManager().ClearTimer(SlamDivePoseTimer);
		RestoreSlamAnimation();
	}
}

void ARedPlayerCharacter::StopAbilitySlot(const int32 Slot)
{
	if (Slot >= 0 && Slot <= 1 && GetAbilityForSlot(Slot) == ERedPlayerAbility::Grapple)
	{
		StopGrappleInput();
	}
}

void ARedPlayerCharacter::ToggleAbilityLoadout()
{
	if (!IsLocallyControlled() || !ActiveHUDWidget || bDowned)
	{
		return;
	}
	if (bAbilityLoadoutOpen)
	{
		CloseAbilityLoadout();
		return;
	}

	StopFiring();
	StopGrappleInput();
	bAbilityLoadoutOpen = true;
	ActiveHUDWidget->SetVisibility(ESlateVisibility::Visible);
	if (APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		if (ARedHUD* PixelHUD = Cast<ARedHUD>(PC->GetHUD()))
		{
			PixelHUD->SetPixelExactHUDVisible(false);
		}
	}
	ActiveHUDWidget->SetAbilityLoadoutOverlayVisible(
		true, AbilitySlotQ == ERedPlayerAbility::Grapple);
	if (APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		FInputModeGameAndUI InputMode;
		// Keep keyboard focus on the viewport so Tab reaches this same action again to close; mouse
		// hit testing still reaches the visible swap button through GameAndUI mode.
		InputMode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
		InputMode.SetHideCursorDuringCapture(false);
		PC->SetInputMode(InputMode);
		PC->bShowMouseCursor = true;
		PC->SetIgnoreMoveInput(true);
		PC->SetIgnoreLookInput(true);
	}
}

void ARedPlayerCharacter::PrepareForPauseMenu()
{
	if (!IsLocallyControlled())
	{
		return;
	}

	// A UI-only input mode will not deliver release events to gameplay. Clear
	// held local actions before Escape takes focus so firing/grapple cannot stick.
	StopFiring();
	StopGrappleInput();
	CloseAbilityLoadout();
}

bool ARedPlayerCharacter::CanOpenAbilityLoadout() const
{
	return IsLocallyControlled() && ActiveHUDWidget && !bDowned;
}

void ARedPlayerCharacter::OpenAbilityLoadoutFromMenu()
{
	if (CanOpenAbilityLoadout() && !bAbilityLoadoutOpen)
	{
		ToggleAbilityLoadout();
	}
}

FText ARedPlayerCharacter::GetAbilityDisplayNameForSlot(const int32 Slot) const
{
	return FText::FromString(GetAbilityForSlot(Slot) == ERedPlayerAbility::Grapple
		? TEXT("GRAPPLE") : TEXT("KINETIC SLAM"));
}

void ARedPlayerCharacter::CloseAbilityLoadout()
{
	if (!bAbilityLoadoutOpen)
	{
		return;
	}
	bAbilityLoadoutOpen = false;
	if (ActiveHUDWidget)
	{
		ActiveHUDWidget->SetAbilityLoadoutOverlayVisible(
			false, AbilitySlotQ == ERedPlayerAbility::Grapple);
	}
	if (APlayerController* PC = Cast<APlayerController>(GetController()); PC && PC->IsLocalController())
	{
		if (ARedHUD* PixelHUD = Cast<ARedHUD>(PC->GetHUD());
			PixelHUD && PixelHUD->HasPixelExactHUD())
		{
			// Refresh after clearing bAbilityLoadoutOpen so cached replacement art cannot
			// reappear disabled for a frame before the next status tick.
			UpdateAbilityHUD(PixelHUD);
			PixelHUD->SetPixelExactHUDVisible(true);
			if (ActiveHUDWidget)
			{
				ActiveHUDWidget->SetVisibility(ESlateVisibility::Collapsed);
			}
		}
		PC->SetInputMode(FInputModeGameOnly());
		PC->bShowMouseCursor = false;
		PC->SetIgnoreMoveInput(false);
		PC->SetIgnoreLookInput(false);
	}
}

void ARedPlayerCharacter::HandleAbilityLoadoutSwapRequested()
{
	if (!bAbilityLoadoutOpen)
	{
		return;
	}
	const ERedPlayerAbility NewQ = AbilitySlotE;
	const ERedPlayerAbility NewE = AbilitySlotQ;
	AbilitySlotQ = NewQ;
	AbilitySlotE = NewE;
	OnRep_AbilityLoadout();
	if (HasAuthority())
	{
		ForceNetUpdate();
	}
	else
	{
		ServerSetAbilityLoadout(NewQ, NewE);
	}
}

void ARedPlayerCharacter::ServerSetAbilityLoadout_Implementation(
	const ERedPlayerAbility NewQ, const ERedPlayerAbility NewE)
{
	const bool bKnownQ = NewQ == ERedPlayerAbility::Grapple || NewQ == ERedPlayerAbility::Slam;
	const bool bKnownE = NewE == ERedPlayerAbility::Grapple || NewE == ERedPlayerAbility::Slam;
	if (!bKnownQ || !bKnownE || NewQ == NewE)
	{
		return;
	}
	AbilitySlotQ = NewQ;
	AbilitySlotE = NewE;
	ForceNetUpdate();
}

void ARedPlayerCharacter::OnRep_AbilityLoadout()
{
	RefreshAbilityLoadoutForWeapon();
}

void ARedPlayerCharacter::OnRep_AbilityCooldowns()
{
	UpdateAbilityHUD();
}

// --- Grapple hook (reel-in). CMC-native; Titan's GAS/Mover grapple is not portable to this pawn. ---
namespace
{
/** Reject non-terrain anchors. ARedPlayerCharacter is handled explicitly before this filter. */
bool IsRejectedGrappleHit(const FHitResult& Hit)
{
	const UPrimitiveComponent* HitComponent = Hit.GetComponent();
	FString Text;
	Text += GetNameSafe(Hit.GetActor());
	Text += TEXT(" ");
	Text += GetNameSafe(Hit.GetActor() ? Hit.GetActor()->GetClass() : nullptr);
	Text += TEXT(" ");
	Text += GetNameSafe(HitComponent);
	Text += TEXT(" ");
	Text += GetNameSafe(HitComponent ? HitComponent->GetClass() : nullptr);
	Text.ToLowerInline();

	static const TCHAR* RejectedTokens[] =
	{
		TEXT("bolt"), TEXT("projectile"),
		TEXT("sky"), TEXT("atmosphere"), TEXT("dome"), TEXT("starlayer"),
		TEXT("water"), TEXT("ocean"), TEXT("pickup"), TEXT("hud"), TEXT("reticle")
	};
	for (const TCHAR* Token : RejectedTokens)
	{
		if (Text.Contains(Token)) { return true; }
	}
	// Titan "NoGrapple" physical surface (SurfaceType1) — honor it when present.
	if ((Hit.GetActor() && Hit.GetActor()->ActorHasTag(TEXT("NoGrapple")))
		|| (HitComponent && HitComponent->ComponentHasTag(TEXT("NoGrapple"))))
	{
		return true;
	}
	if (const UPhysicalMaterial* PhysMat = Hit.PhysMaterial.Get())
	{
		// SurfaceType1 is the authored NoGrapple channel; SurfaceType10 is water.
		if (PhysMat->SurfaceType == SurfaceType1 || PhysMat->SurfaceType == SurfaceType10)
		{
			return true;
		}
	}
	return false;
}

FGenericTeamId GetExplicitGrappleTeam(const ARedPlayerCharacter* Character)
{
	if (!Character)
	{
		return FGenericTeamId::NoTeam;
	}
	if (const IGenericTeamAgentInterface* TeamAgent =
		Cast<IGenericTeamAgentInterface>(const_cast<ARedPlayerCharacter*>(Character)))
	{
		return TeamAgent->GetGenericTeamId();
	}
	if (const IGenericTeamAgentInterface* TeamController =
		Cast<IGenericTeamAgentInterface>(Character->GetController()))
	{
		return TeamController->GetGenericTeamId();
	}
	return FGenericTeamId::NoTeam;
}
} // namespace

bool ARedPlayerCharacter::IsCombatAiming() const
{
	if (bHolstered) { return false; }
	const bool bHeldAim = IsLocallyControlled() ? (bADS || bIsFiringHeld) : bReplicatedAimHeld;
	if (bHeldAim) { return true; }
	const float Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.f;
	return (Now - LastFireTime) < 0.45f;
}

bool ARedPlayerCharacter::TryGrapple()
{
	const int32 GrappleSlot = FindAbilitySlot(ERedPlayerAbility::Grapple);
	return GrappleSlot != INDEX_NONE && TryActivateAbilitySlot(GrappleSlot);
}

bool ARedPlayerCharacter::IsValidGrapplePlayerTarget(
	const ARedPlayerCharacter* Target, const bool bCheckReservation) const
{
	if (!IsValid(Target) || Target == this || bDowned || Target->IsDowned()
		|| bSkydiving || bOrbitalDropActive || Target->bSkydiving || Target->bOrbitalDropActive)
	{
		return false;
	}
	// PlayerState is replicated to non-owning clients even though their PlayerController is not,
	// which keeps local hit prediction functional without admitting spawned bot clones.
	if (!Target->GetPlayerState() && !Target->IsPlayerControlled())
	{
		return false;
	}
	if (HasAuthority()
		&& (!Target->GetController() || !Target->GetController()->IsPlayerController()))
	{
		return false;
	}
	if (GetController() && GetController() == Target->GetController())
	{
		return false;
	}
	if (Target->bGrappling)
	{
		return false;
	}
	if (bCheckReservation && Target->GrappledBy.IsValid()
		&& Target->GrappledBy.Get() != this)
	{
		return false;
	}

	// The current PvP mode has no native team assignment. If a future mode supplies explicit
	// GenericTeam IDs, equal non-NoTeam IDs are treated as friendly and cannot be tethered.
	const FGenericTeamId MyTeam = GetExplicitGrappleTeam(this);
	const FGenericTeamId TheirTeam = GetExplicitGrappleTeam(Target);
	if (MyTeam.GetId() != FGenericTeamId::NoTeam.GetId()
		&& TheirTeam.GetId() != FGenericTeamId::NoTeam.GetId()
		&& MyTeam.GetId() == TheirTeam.GetId())
	{
		return false;
	}
	return true;
}

bool ARedPlayerCharacter::HasGrappleLineOfSight(const ARedPlayerCharacter* Target) const
{
	if (!IsValid(Target) || !GetWorld())
	{
		return false;
	}
	FCollisionQueryParams Params(SCENE_QUERY_STAT(GrapplePlayerLOS), false, this);
	FHitResult Hit;
	const FVector Start = GetActorLocation() + GetActorUpVector() * 45.f;
	const FVector End = Target->GetActorLocation() + Target->GetActorUpVector() * 45.f;
	if (!GetWorld()->LineTraceSingleByChannel(Hit, Start, End, ECC_Visibility, Params))
	{
		return true;
	}
	return Hit.GetActor() == Target;
}

FVector ARedPlayerCharacter::GetGrappleTargetPoint() const
{
	return IsValid(GrappleTarget)
		? GrappleTarget->GetActorLocation() + GrappleTarget->GetActorUpVector() * 45.f
		: GrapplePoint;
}

bool ARedPlayerCharacter::FindValidGrapplePoint(const FVector& TraceOrigin,
	const FVector& TraceDirection, FVector& OutPoint, FVector& OutNormal,
	ARedPlayerCharacter*& OutPlayerTarget) const
{
	OutPoint = FVector::ZeroVector;
	OutNormal = FVector::UpVector;
	OutPlayerTarget = nullptr;
	if (bDowned || bSkydiving || !GetWorld() || TraceOrigin.ContainsNaN()
		|| TraceDirection.ContainsNaN())
	{
		return false;
	}
	const FVector SafeDirection = TraceDirection.GetSafeNormal();
	if (SafeDirection.IsNearlyZero())
	{
		return false;
	}
	const FVector TraceStart = TraceOrigin + SafeDirection * 50.0f;
	const FVector TraceEnd = TraceOrigin + SafeDirection * GrappleMaxRange;

	FCollisionQueryParams QP(SCENE_QUERY_STAT(Grapple), false, this);
	QP.bReturnPhysicalMaterial = true;

	// Query the authored Grapple channel and object types. Pawns often do not block a custom terrain
	// channel, so the Pawn object query is necessary for PvP while WorldStatic/Dynamic preserve CLM.
	TArray<FHitResult> Hits;
	GetWorld()->LineTraceMultiByChannel(Hits, TraceStart, TraceEnd, ECC_GameTraceChannel1, QP);
	TArray<FHitResult> VisibilityHits;
	GetWorld()->LineTraceMultiByChannel(VisibilityHits, TraceStart, TraceEnd, ECC_Visibility, QP);
	Hits.Append(VisibilityHits);
	TArray<FHitResult> ObjectHits;
	FCollisionObjectQueryParams ObjParams;
	ObjParams.AddObjectTypesToQuery(ECC_WorldStatic);
	ObjParams.AddObjectTypesToQuery(ECC_WorldDynamic);
	ObjParams.AddObjectTypesToQuery(ECC_PhysicsBody);
	ObjParams.AddObjectTypesToQuery(ECC_Vehicle);
	ObjParams.AddObjectTypesToQuery(ECC_Destructible);
	ObjParams.AddObjectTypesToQuery(static_cast<ECollisionChannel>(13));
	GetWorld()->LineTraceMultiByObjectType(ObjectHits, TraceStart, TraceEnd, ObjParams, QP);
	Hits.Append(ObjectHits);

	// A one-pixel line trace makes a moving replicated capsule unnecessarily hard to acquire at
	// grapple range. Sweep only the Pawn channel by roughly half a character width; terrain and
	// structures retain the exact line trace above, so this cannot hook empty space near a wall.
	TArray<FHitResult> PlayerHits;
	FCollisionObjectQueryParams PlayerParams;
	PlayerParams.AddObjectTypesToQuery(ECC_Pawn);
	GetWorld()->SweepMultiByObjectType(PlayerHits, TraceStart, TraceEnd, FQuat::Identity,
		PlayerParams, FCollisionShape::MakeSphere(48.0f), QP);
	Hits.Append(PlayerHits);
	Hits.Sort([&TraceStart](const FHitResult& A, const FHitResult& B)
	{
		return FVector::DistSquared(TraceStart, A.ImpactPoint)
			< FVector::DistSquared(TraceStart, B.ImpactPoint);
	});

	const FHitResult* Best = nullptr;
	float BestDistSq = TNumericLimits<float>::Max();
	const FVector SelfLoc = GetActorLocation();
	// An accepted anchor must survive the first TickGrapple arrival test.  Previously a
	// 150–250 cm hit consumed the cooldown, started the rope, then immediately stopped
	// before either the pull or its VFX could be perceived.
	const float EffectiveMinRange = FMath::Max(GrappleMinRange, GrappleArrivalDist + 1.0f);
	const float MinRangeSq = EffectiveMinRange * EffectiveMinRange;
	for (const FHitResult& Hit : Hits)
	{
		if (!Hit.bBlockingHit) { continue; }
		const float DistSq = (Hit.ImpactPoint - SelfLoc).SizeSquared();
		if (DistSq < MinRangeSq) { continue; } // ignore floor under feet / point-blank
		if (ARedPlayerCharacter* PlayerTarget = Cast<ARedPlayerCharacter>(Hit.GetActor()))
		{
			if (Best && DistSq >= BestDistSq)
			{
				break;
			}
			if (IsValidGrapplePlayerTarget(PlayerTarget, /*bCheckReservation=*/true)
				&& HasGrappleLineOfSight(PlayerTarget))
			{
				OutPlayerTarget = PlayerTarget;
				OutPoint = PlayerTarget->GetActorLocation() + PlayerTarget->GetActorUpVector() * 45.f;
				OutNormal = (SelfLoc - OutPoint).GetSafeNormal();
				if (OutNormal.IsNearlyZero()) { OutNormal = PlayerTarget->GetActorUpVector(); }
				return true;
			}
			// An invalid/downed/friendly player blocks the trace; never acquire terrain behind them.
			return false;
		}
		if (IsRejectedGrappleHit(Hit)) { continue; }
		if (DistSq < BestDistSq)
		{
			BestDistSq = DistSq;
			Best = &Hit;
		}
	}
	if (!Best)
	{
		return false;
	}
	OutPoint = Best->ImpactPoint;
	OutNormal = Best->ImpactNormal.GetSafeNormal();
	if (OutNormal.IsNearlyZero()) { OutNormal = -SafeDirection; }
	return true;
}

void ARedPlayerCharacter::StartGrapple(const FVector& Point,
	const FVector& SurfaceNormal, ARedPlayerCharacter* PlayerTarget)
{
	if (bGrappling) { return; }
	GrappleTarget = PlayerTarget;
	GrapplePoint = IsValid(PlayerTarget)
		? PlayerTarget->GetActorLocation() + PlayerTarget->GetActorUpVector() * 45.f
		: Point;
	GrappleNormal = SurfaceNormal.GetSafeNormal();
	if (GrappleNormal.IsNearlyZero()) { GrappleNormal = -GetActorForwardVector(); }
	GrappleElapsed = 0.f;
	bGrappling = true;
	if (HasAuthority() && IsValid(PlayerTarget))
	{
		PlayerTarget->GrappledBy = this;
	}
	if (UCharacterMovementComponent* CMC = GetCharacterMovement())
	{
		SavedGrappleGravity = CMC->GravityScale;
		CMC->GravityScale = 0.f;
		CMC->SetMovementMode(MOVE_Flying);
		// Clear any residual downward velocity so radial gravity doesn't fight the first reel frame.
		CMC->Velocity = FVector::VectorPlaneProject(CMC->Velocity, -CMC->GetGravityDirection().GetSafeNormal());
	}
	UE_LOG(LogRedPlayerCharacter, Display,
		TEXT("Grapple start: pawn=%s anchorDistance=%.1fcm target=%s ropeAsset=%s"),
		*GetName(), FVector::Distance(GetActorLocation(), GrapplePoint),
		IsValid(PlayerTarget) ? *PlayerTarget->GetName() : TEXT("terrain"),
		GrappleRope && GrappleRope->GetAsset() ? *GrappleRope->GetAsset()->GetName() : TEXT("none"));
	SetGrappleRope(true);
}

void ARedPlayerCharacter::StopGrapple(bool bBoost)
{
	if (!bGrappling) { return; }
	const bool bWasPlayerTether = GrappleTarget != nullptr;
	if (HasAuthority() && IsValid(GrappleTarget) && GrappleTarget->GrappledBy.Get() == this)
	{
		GrappleTarget->GrappledBy.Reset();
	}
	bGrappling = false;
	if (UCharacterMovementComponent* CMC = GetCharacterMovement())
	{
		CMC->GravityScale = SavedGrappleGravity;
		const FVector Dir = (GrapplePoint - GetActorLocation()).GetSafeNormal();
		CMC->SetMovementMode(MOVE_Falling);
		// Terrain keeps the existing arc-off reward. PvP keeps the capped shared pull velocity,
		// avoiding a final launch spike that would amplify network corrections.
		if (!bWasPlayerTether)
		{
			CMC->Velocity = bBoost ? Dir * GrappleSpeed * GrappleExitBoost : FVector::ZeroVector;
		}
	}
	GrappleTarget = nullptr;
	SetGrappleRope(false);
	if (HasAuthority())
	{
		ForceNetUpdate();
	}
}

void ARedPlayerCharacter::StopGrappleInput()
{
	StopGrappleAndNotifyAuthority(true);
}

void ARedPlayerCharacter::StopGrappleAndNotifyAuthority(const bool bBoost)
{
	if (!bGrappling)
	{
		return;
	}
	StopGrapple(bBoost);
	if (!HasAuthority() && IsLocallyControlled())
	{
		ServerStopGrapple(bBoost);
	}
}

void ARedPlayerCharacter::ServerStopGrapple_Implementation(const bool bBoost)
{
	if (bGrappling)
	{
		StopGrapple(bBoost);
	}
}

void ARedPlayerCharacter::TickGrapple(float DeltaSeconds)
{
	if (!bGrappling) { return; }
	// Simulated proxies receive the authoritative pawn transform and anchor through replication;
	// they only need to update the visual tether, never run another local movement simulation.
	if (GetLocalRole() == ROLE_SimulatedProxy)
	{
		UpdateGrappleTether();
		return;
	}
	if (GrappleTarget && !IsValid(GrappleTarget))
	{
		StopGrappleAndNotifyAuthority(false);
		return;
	}

	if (IsValid(GrappleTarget))
	{
		ARedPlayerCharacter* PlayerTarget = GrappleTarget.Get();
		GrapplePoint = GetGrappleTargetPoint();
		if (!IsValidGrapplePlayerTarget(PlayerTarget, /*bCheckReservation=*/HasAuthority())
			|| (HasAuthority() && !HasGrappleLineOfSight(PlayerTarget)))
		{
			StopGrappleAndNotifyAuthority(false);
			return;
		}

		GrappleElapsed += DeltaSeconds;
		const FVector SelfLocation = GetActorLocation();
		const FVector TargetLocation = PlayerTarget->GetActorLocation();
		const float Separation = FVector::Distance(SelfLocation, TargetLocation);
		if (Separation <= FMath::Max(100.f, GrapplePlayerMinSeparation)
			|| Separation > GrappleMaxRange * 1.10f || GrappleElapsed >= GrappleMaxTime)
		{
			StopGrappleAndNotifyAuthority(false);
			return;
		}

		UCharacterMovementComponent* SelfMovement = GetCharacterMovement();
		if (!SelfMovement)
		{
			StopGrappleAndNotifyAuthority(false);
			return;
		}
		const FVector Midpoint = (SelfLocation + TargetLocation) * 0.5f;
		const FVector SelfDirection = (Midpoint - SelfLocation).GetSafeNormal();
		const float PullAccel = FMath::Max(0.f, GrapplePlayerPullAccel);
		const float PullSpeed = FMath::Max(100.f, GrapplePlayerPullSpeed);
		auto ApplyCappedPull = [PullAccel, PullSpeed, DeltaSeconds](
			UCharacterMovementComponent* Movement, const FVector& Direction)
		{
			if (!Movement || Direction.IsNearlyZero())
			{
				return;
			}
			Movement->Velocity += Direction * PullAccel * DeltaSeconds;
			const float TowardSpeed = FVector::DotProduct(Movement->Velocity, Direction);
			if (TowardSpeed > PullSpeed)
			{
				Movement->Velocity -= Direction * (TowardSpeed - PullSpeed);
			}
		};
		ApplyCappedPull(SelfMovement, SelfDirection);

		// Only authority moves the victim. The victim's autonomous proxy receives ordinary CMC
		// corrections; direct client-side mutation would let either participant inject velocity.
		if (HasAuthority())
		{
			if (UCharacterMovementComponent* TargetMovement = PlayerTarget->GetCharacterMovement())
			{
				if (TargetMovement->MovementMode == MOVE_Walking
					|| TargetMovement->MovementMode == MOVE_NavWalking)
				{
					TargetMovement->SetMovementMode(MOVE_Falling);
				}
				ApplyCappedPull(TargetMovement, (Midpoint - TargetLocation).GetSafeNormal());
			}
		}

		if (bJumpHeld)
		{
			const FVector Up = -SelfMovement->GetGravityDirection().GetSafeNormal();
			SelfMovement->Velocity += Up * JetpackAccel * DeltaSeconds;
			bThrustFXWanted = true;
		}
		UpdateGrappleTether();
		return;
	}

	GrappleElapsed += DeltaSeconds;
	UCharacterMovementComponent* CMC = GetCharacterMovement();
	if (!CMC) { StopGrappleAndNotifyAuthority(false); return; }
	const FVector ToPoint = GrapplePoint - GetActorLocation();
	const float Dist = ToPoint.Size();
	if (Dist <= GrappleArrivalDist || GrappleElapsed >= GrappleMaxTime)
	{
		UE_LOG(LogRedPlayerCharacter, Display,
			TEXT("Grapple stop: pawn=%s reason=%s distance=%.1fcm elapsed=%.2fs"),
			*GetName(), Dist <= GrappleArrivalDist ? TEXT("arrival") : TEXT("timeout"),
			Dist, GrappleElapsed);
		StopGrappleAndNotifyAuthority(Dist <= GrappleArrivalDist); // boost only on a real arrival
		return;
	}
	// Smooth pull: ACCELERATE toward the anchor while KEEPING your momentum, so you swing/arc in and
	// carry speed (a real grappling-hook feel) instead of a hard instant yank that slams you into the wall.
	const FVector ToDir = ToPoint.GetSafeNormal();
	CMC->Velocity += ToDir * GrapplePullAccel * DeltaSeconds;
	if (bJumpHeld)   // jetpack mid-grapple = upward FLOAT (airy momentum), NOT a faster reel
	{
		const FVector Up = -CMC->GetGravityDirection().GetSafeNormal();
		CMC->Velocity += Up * JetpackAccel * DeltaSeconds;
		bThrustFXWanted = true;
	}
	// Cap the speed TOWARD the anchor so it never wall-slams; a gentle drag settles the swing smoothly.
	const float TowardSpd = FVector::DotProduct(CMC->Velocity, ToDir);
	if (TowardSpd > GrappleSpeed) { CMC->Velocity -= ToDir * (TowardSpd - GrappleSpeed); }
	CMC->Velocity -= CMC->Velocity * FMath::Clamp(GrappleDrag * DeltaSeconds, 0.f, 0.9f);
	if (GrappleRope)
	{
		GrappleRope->SetVectorParameter(TEXT("BeamEnd"), GrapplePoint);
		GrappleRope->SetVectorParameter(TEXT("User.BeamEnd"), GrapplePoint);
	}
	UpdateGrappleTether();
}

void ARedPlayerCharacter::SetGrappleRope(bool bOn)
{
	if (bOn)
	{
		if (GrappleRope && GrappleRopeFX && GrappleRope->GetAsset() != GrappleRopeFX)
		{
			GrappleRope->SetAsset(GrappleRopeFX);
		}
		const bool bUseBeamsPack = GrappleRope && GrappleRope->GetAsset();
		const bool bUseReadableFallback = !bUseBeamsPack || bKeepGrappleFallbackVisible;
		const bool bBeamWasVisible = (bUseBeamsPack && GrappleRope->IsVisible())
			|| (GrapplePlasmaBeamA && GrapplePlasmaBeamA->IsVisible())
			|| (GrapplePlasmaBeamB && GrapplePlasmaBeamB->IsVisible());
		if (!bBeamWasVisible)
		{
			GrappleVisualStartTime = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0f;
		}
		if (bUseBeamsPack)
		{
			GrappleRope->SetHiddenInGame(false, true);
			GrappleRope->SetVisibility(true, true);
		}
		if (!GrapplePlasmaHead && GrapplePlasmaHeadFX && GetWorld() && GetMesh())
		{
			const FVector HandWorld = GetMesh()->DoesSocketExist(GrappleHandSocket)
				? GetMesh()->GetSocketLocation(GrappleHandSocket)
				: GetMesh()->GetComponentLocation();
			const FVector TargetWorld = GetGrappleTargetPoint();
			GrapplePlasmaHead = UNiagaraFunctionLibrary::SpawnSystemAtLocation(
				GetWorld(), GrapplePlasmaHeadFX, HandWorld,
				(TargetWorld - HandWorld).Rotation(), FVector(0.34f), false, true);
		}
		for (USplineMeshComponent* Beam : { GrapplePlasmaBeamA.Get(), GrapplePlasmaBeamB.Get() })
		{
			if (Beam && Beam->GetStaticMesh())
			{
				// The fallback stays beneath the purchased Beams Pack ribbon until the target GPU has
				// visually proven that the vendor renderer reads at gameplay distance.
				Beam->SetHiddenInGame(!bUseReadableFallback, true);
				Beam->SetVisibility(bUseReadableFallback, true);
			}
		}
		UpdateGrappleTether();
		if (bUseBeamsPack && !GrappleRope->IsActive())
		{
			// Apply the transform and User.BeamLength before the first activation so the vendor
			// ribbon never begins from its authored zero-length preview state.
			GrappleRope->Activate(true);
		}
		UE_LOG(LogRedPlayerCharacter, Display,
			TEXT("Grapple tether: pawn=%s vendor=%d active=%d visible=%d fallback=%d"),
			*GetName(), bUseBeamsPack ? 1 : 0,
			GrappleRope && GrappleRope->IsActive() ? 1 : 0,
			GrappleRope && GrappleRope->IsVisible() ? 1 : 0,
			bUseReadableFallback ? 1 : 0);
	}
	else
	{
		if (GrappleRope)
		{
			GrappleRope->DeactivateImmediate();
			GrappleRope->SetVisibility(false, true);
			GrappleRope->SetHiddenInGame(true, true);
		}
		if (GrapplePlasmaHead)
		{
			GrapplePlasmaHead->DeactivateImmediate();
			GrapplePlasmaHead->DestroyComponent();
			GrapplePlasmaHead = nullptr;
		}
		for (USplineMeshComponent* Beam : { GrapplePlasmaBeamA.Get(), GrapplePlasmaBeamB.Get() })
		{
			if (Beam)
			{
				Beam->SetVisibility(false, true);
				Beam->SetHiddenInGame(true, true);
			}
		}
	}
}

void ARedPlayerCharacter::UpdateGrappleTether()
{
	if (!bGrappling || !GetMesh())
	{
		return;
	}

	const FVector HandWorld = GetMesh()->DoesSocketExist(GrappleHandSocket)
		? GetMesh()->GetSocketLocation(GrappleHandSocket)
		: GetMesh()->GetComponentLocation();
	const float Time = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0f;
	const float LaunchAlpha = GrapplePlasmaLaunchTime > KINDA_SMALL_NUMBER
		? FMath::Clamp((Time - GrappleVisualStartTime) / GrapplePlasmaLaunchTime, 0.0f, 1.0f)
		: 1.0f;
	const FVector TargetWorld = GetGrappleTargetPoint();
	const FVector VisualEndWorld = FMath::Lerp(HandWorld, TargetWorld, LaunchAlpha);
	const FVector VisualSpanWorld = VisualEndWorld - HandWorld;
	const float VisualLength = VisualSpanWorld.Size();
	const float PulseScale = 1.0f + GrapplePlasmaPulse * FMath::Sin(Time * 18.0f);
	const float DistanceReadability = FMath::Clamp(
		FMath::Sqrt(VisualLength / 2500.0f), 1.0f, 2.6f);
	const FVector2D StartScale(GrapplePlasmaWidth * PulseScale * DistanceReadability);
	const FVector2D EndScale(GrapplePlasmaWidth * 0.55f * PulseScale * DistanceReadability);
	if (GrappleRope && GrappleRope->GetAsset() && GrappleRope->IsVisible()
		&& VisualLength > KINDA_SMALL_NUMBER)
	{
		// NS_BeamOnly_02 builds BeamEnd as (0, 0, User.BeamLength). Keep the component exactly at the
		// hand and rotate its authored local +Z onto the current anchor direction.
		const FQuat BeamRotation = FQuat::FindBetweenNormals(
			FVector::UpVector, VisualSpanWorld.GetSafeNormal());
		GrappleRope->SetWorldLocationAndRotation(
			HandWorld, BeamRotation);
		GrappleRope->SetFloatParameter(TEXT("User.BeamLength"), VisualLength);
		// Setting the non-prefixed alias as well keeps this compatible with pack revisions that expose
		// the same input through an inherited emitter parameter rather than the user namespace.
		GrappleRope->SetFloatParameter(TEXT("BeamLength"), VisualLength);
	}
	if (GrapplePlasmaHead)
	{
		GrapplePlasmaHead->SetWorldLocation(VisualEndWorld);
		GrapplePlasmaHead->SetWorldRotation((TargetWorld - HandWorld).Rotation());
		GrapplePlasmaHead->SetWorldScale3D(FVector(
			0.28f * FMath::Min(DistanceReadability, 1.8f) * PulseScale));
	}

	for (USplineMeshComponent* Beam : { GrapplePlasmaBeamA.Get(), GrapplePlasmaBeamB.Get() })
	{
		if (!Beam || !Beam->IsVisible())
		{
			continue;
		}

		const FTransform BeamTransform = Beam->GetComponentTransform();
		const FVector Start = BeamTransform.InverseTransformPosition(HandWorld);
		const FVector End = BeamTransform.InverseTransformPosition(VisualEndWorld);
		const FVector Span = End - Start;
		const float Length = Span.Size();
		if (Length <= KINDA_SMALL_NUMBER)
		{
			continue;
		}

		// Straight tangents keep the line of energy exact while the authored material supplies the
		// traveling noise/plasma motion. Crossed rolls prevent a ribbon from disappearing edge-on.
		const FVector Tangent = Span.GetSafeNormal() * Length;
		Beam->SetStartScale(StartScale, false);
		Beam->SetEndScale(EndScale, false);
		Beam->SetStartAndEnd(Start, Tangent, End, Tangent, true);
	}
}

void ARedPlayerCharacter::OnRep_Grappling()
{
	SetGrappleRope(bGrappling);   // remote clients show/hide the rope with the replicated state
	if (!bGrappling && IsLocallyControlled())
	{
		if (UCharacterMovementComponent* CMC = GetCharacterMovement())
		{
			CMC->GravityScale = SavedGrappleGravity;
			if (CMC->MovementMode == MOVE_Flying)
			{
				CMC->SetMovementMode(MOVE_Falling);
			}
		}
	}
}

void ARedPlayerCharacter::RefreshHudCaptures()
{
	// Timer-driven. Each CaptureScene re-renders the scene, so doing it here instead of every frame
	// is the single biggest GPU win (~7ms/frame) with no perceptible HUD change.
	// ALTERNATE the two captures across ticks: capturing both in the SAME frame makes the portrait's
	// render bleed into the minimap render target's corner (shared transient scene buffers on Metal).
	// Interleaving also halves the per-tick capture cost.
	if (!IsValid(ActiveHUDWidget) || !ActiveHUDWidget->IsInViewport())
	{
		return;
	}

	const ESlateVisibility LegacyHUDVisibility = ActiveHUDWidget->GetVisibility();
	const bool bLegacyHUDPainted =
		LegacyHUDVisibility != ESlateVisibility::Collapsed
		&& LegacyHUDVisibility != ESlateVisibility::Hidden;
	bool bReplacementSurfaceMinimapPainted = false;
	if (APlayerController* HUDPlayerController = ActiveHUDWidget->GetOwningPlayer())
	{
		if (ARedHUD* ReplacementHUD = Cast<ARedHUD>(HUDPlayerController->GetHUD()))
		{
			bReplacementSurfaceMinimapPainted =
				ReplacementHUD->IsReplacementHUDMinimapActive(this);
		}
	}
	if (!bLegacyHUDPainted && !bReplacementSurfaceMinimapPainted)
	{
		return;
	}

	if (!bLegacyHUDPainted)
	{
		if (MinimapCapture && MinimapCapture->TextureTarget)
		{
			MinimapCapture->CaptureScene();
			LastReplacementMinimapCaptureFrameId =
				ResolveReplacementHUDMinimapFrameId();
			bReplacementMinimapSurfaceCaptureFresh =
				!LastReplacementMinimapCaptureFrameId.IsNone();
		}
		return;
	}

	bHudCapturePortraitTurn = !bHudCapturePortraitTurn;
	if (bHudCapturePortraitTurn)
	{
		if (PortraitCapture && PortraitCapture->TextureTarget) { PortraitCapture->CaptureScene(); }
	}
	else if (MinimapCapture && MinimapCapture->TextureTarget)
	{
		MinimapCapture->CaptureScene();
	}
}

void ARedPlayerCharacter::UpdateHUDStatus()
{
	ARedHUD* ReplacementHUD = nullptr;
	APlayerController* HUDPlayerController = Cast<APlayerController>(GetController());
	if (!HUDPlayerController && ActiveHUDWidget)
	{
		HUDPlayerController = ActiveHUDWidget->GetOwningPlayer();
	}
	if (HUDPlayerController && HUDPlayerController->IsLocalController())
	{
		ReplacementHUD = Cast<ARedHUD>(HUDPlayerController->GetHUD());
	}

	if (ReplacementHUD)
	{
		ReplacementHUD->UpdateReplacementHUDVitals(
			Shield, MaxShield, Health, MaxHealth, Fuel, MaxFuel);
	}

	if (ActiveHUDWidget)
	{
		ActiveHUDWidget->SetLiveStatus(
			FMath::RoundToInt(Shield), FMath::RoundToInt(Health),
			GetShieldFraction(), GetHealthFraction(), GetFuelFraction());
	}

	for (int32 Slot = 0; Slot < 2; ++Slot)
	{
		const float Heat = GetWeaponHeatForSlot(Slot);
		const bool bOverheated = IsWeaponSlotOverheated(Slot);
		const float HeatFraction = MaxWeaponHeat > 0.0f ? Heat / MaxWeaponHeat : 0.0f;
		const bool bCoolingWeapon = Heat > KINDA_SMALL_NUMBER
			&& (Slot != CurrentWeaponSlot || !bIsFiringHeld || bOverheated);
		if (ActiveHUDWidget)
		{
			ActiveHUDWidget->SetWeaponHeatState(
				Slot, HeatFraction, bOverheated, bCoolingWeapon);
		}
		if (ReplacementHUD)
		{
			const float ResumeHeat = MaxWeaponHeat * WeaponHeatResumeFraction;
			const float CooldownRemaining = bOverheated && WeaponHeatCoolRate > KINDA_SMALL_NUMBER
				? FMath::Max(0.f, (Heat - ResumeHeat) / WeaponHeatCoolRate) : 0.f;
			ReplacementHUD->UpdateReplacementHUDWeaponState(
				Slot, HeatFraction, bOverheated, CooldownRemaining, Slot == CurrentWeaponSlot);
		}
	}

	UpdateAbilityHUD(ReplacementHUD);
}

void ARedPlayerCharacter::AddResource(ERedResourceType Type, int32 InAmount)
{
	if (!HasAuthority())
	{
		return;
	}

	const int32 Add = FMath::Max(1, InAmount);
	switch (Type)
	{
	case ERedResourceType::Crystal: ResCrystal += Add; break;
	case ERedResourceType::Iron:    ResIron    += Add; break;
	case ERedResourceType::Stone:
	default:                        ResStone   += Add; break;
	}

	if (!bIsEnemy)
	{
		if (APlayerController* PC = Cast<APlayerController>(GetController()))
		{
			if (PC->IsLocalController())
			{
				PresentResourceCreditLocal(Type, Add);
			}
			else
			{
				ClientPresentResourceCredit(Type, Add);
			}
		}
	}
	UpdateHUDResources();
	ForceNetUpdate();
}

void ARedPlayerCharacter::ClientPresentResourceCredit_Implementation(
	const ERedResourceType Type, const int32 Amount)
{
	PresentResourceCreditLocal(Type, Amount);
}

void ARedPlayerCharacter::PresentResourceCreditLocal(
	const ERedResourceType Type, const int32 Amount)
{
	if (Amount <= 0)
	{
		return;
	}
	if (APlayerController* PC = Cast<APlayerController>(GetController());
		PC && PC->IsLocalController())
	{
		if (ARedHUD* ReplacementHUD = Cast<ARedHUD>(PC->GetHUD()))
		{
			ReplacementHUD->ShowReplacementHUDMiningResult(
				static_cast<uint8>(Type),
				Amount);
		}
	}
}

void ARedPlayerCharacter::OnRep_Resources()
{
	UpdateHUDResources();
}

void ARedPlayerCharacter::UpdateHUDResources()
{
	if (APlayerController* PC = Cast<APlayerController>(GetController());
		PC && PC->IsLocalController())
	{
		if (ARedHUD* ReplacementHUD = Cast<ARedHUD>(PC->GetHUD()))
		{
			ReplacementHUD->UpdateReplacementHUDResources(
				ResStone, ResIron, ResCrystal);
		}
	}
}

float ARedPlayerCharacter::TakeDamage(float DamageAmount, FDamageEvent const& DamageEvent,
	AController* EventInstigator, AActor* DamageCauser)
{
	if (!HasAuthority())
	{
		return 0.f;
	}
	const float Super_Applied = Super::TakeDamage(DamageAmount, DamageEvent, EventInstigator, DamageCauser);
	if (DamageAmount <= 0.f || bDowned || bLandingInvuln)  // landing shield absorbs everything during touchdown
	{
		return Super_Applied;
	}
	// Shield absorbs first, then health drains.
	float Remaining = DamageAmount;
	if (Shield > 0.f)
	{
		const float Absorb = FMath::Min(Shield, Remaining);
		Shield -= Absorb;
		Remaining -= Absorb;
	}
	// The covered trooper's armor mitigates a configured share of post-shield damage. The prevented
	// amount consumes the replicated armor pool, so PvP clients converge on the same protection state.
	if (Remaining > 0.0f && Armor > 0.0f && ArmorDamageMitigation > 0.0f)
	{
		const float Prevented = FMath::Min(Armor, Remaining * ArmorDamageMitigation);
		Armor = FMath::Max(0.0f, Armor - Prevented);
		Remaining -= Prevented;
	}
	if (Remaining > 0.f)
	{
		Health = FMath::Max(0.f, Health - Remaining);
	}
	if (Health <= 0.f)
	{
		OnDowned();
	}
	UpdateHUDStatus();   // refresh the upper-left bars so damage shows immediately
	ForceNetUpdate();
	return DamageAmount;
}

void ARedPlayerCharacter::ApplyVehicleDestructionDeath(AController* EventInstigator, AActor* DamageCauser)
{
	if (!HasAuthority() || bDowned)
	{
		return;
	}

	// A ship kill must not be swallowed by the brief post-slam landing shield. Feed enough damage
	// through TakeDamage to exhaust the current shield, armor and health, preserving the one normal
	// server-authoritative death path (including ragdoll replication and the four-second respawn).
	GetWorldTimerManager().ClearTimer(LandingInvulnTimer);
	bLandingInvuln = false;
	const float LethalDamage = FMath::Max(1.f,
		FMath::Max(0.f, Shield) + FMath::Max(0.f, Armor) + FMath::Max(0.f, Health) + 1.f);
	FDamageEvent VehicleDeathEvent;
	TakeDamage(LethalDamage, VehicleDeathEvent, EventInstigator,
		IsValid(DamageCauser) ? DamageCauser : nullptr);
}

void ARedPlayerCharacter::OnRep_HealthState()
{
	UpdateHUDStatus();
}

void ARedPlayerCharacter::ApplyDownedPresentation()
{
	if (UCharacterMovementComponent* CMC = GetCharacterMovement())
	{
		CMC->StopMovementImmediately();
		CMC->DisableMovement();
	}
	if (APlayerController* PC = Cast<APlayerController>(GetController()); PC && IsLocallyControlled())
	{
		DisableInput(PC);
	}
	if (USkeletalMeshComponent* M = GetMesh())
	{
		M->SetAnimationMode(EAnimationMode::AnimationCustomMode);
		M->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPose;
		M->SetCollisionProfileName(TEXT("Ragdoll"));
		M->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
		M->SetAllBodiesBelowSimulatePhysics(FName(TEXT("pelvis")), true, true);
		M->SetAllBodiesBelowPhysicsBlendWeight(FName(TEXT("pelvis")), 1.f);
		M->SetSimulatePhysics(true);
		M->WakeAllRigidBodies();
	}
	if (UCapsuleComponent* Capsule = GetCapsuleComponent())
	{
		Capsule->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	}
	if (WeaponMesh)
	{
		WeaponMesh->SetVisibility(false, true);
	}
}

void ARedPlayerCharacter::RestoreFromDownedPresentation()
{
	if (UCapsuleComponent* Capsule = GetCapsuleComponent())
	{
		Capsule->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	}
	if (USkeletalMeshComponent* M = GetMesh())
	{
		M->SetSimulatePhysics(false);
		M->SetAllBodiesBelowSimulatePhysics(FName(TEXT("pelvis")), false, true);
		M->SetCollisionProfileName(TEXT("CharacterMesh"));
		M->AttachToComponent(GetCapsuleComponent(), FAttachmentTransformRules::SnapToTargetNotIncludingScale);
		M->SetRelativeLocationAndRotation(
			FVector(0.f, 0.f, -GetCapsuleComponent()->GetScaledCapsuleHalfHeight()),
			FRotator(0.f, -90.f, 0.f));
		M->SetAnimationMode(EAnimationMode::AnimationBlueprint);
		M->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
		if (TrooperAnimClass && IsUsingTrooperBody())
		{
			M->SetAnimInstanceClass(TrooperAnimClass);
		}
	}
	if (UCharacterMovementComponent* CMC = GetCharacterMovement(); CMC && CMC->MovementMode == MOVE_None)
	{
		CMC->SetMovementMode(MOVE_Falling);
	}
	if (APlayerController* PC = Cast<APlayerController>(GetController()); PC && IsLocallyControlled())
	{
		EnableInput(PC);
	}
	if (WeaponMesh)
	{
		WeaponMesh->SetVisibility(true, true);
		ApplyHolsterState();
	}
}

void ARedPlayerCharacter::OnRep_Downed()
{
	if (bDowned)
	{
		GetWorldTimerManager().ClearTimer(FireTimerHandle);
		bIsFiringHeld = false;
		CloseAbilityLoadout();
		ApplyDownedPresentation();
	}
	else
	{
		RestoreFromDownedPresentation();
	}
	UpdateHUDStatus();
}

void ARedPlayerCharacter::OnDowned()
{
	if (bDowned)
	{
		return;
	}
	bDowned = true;
	bReplicatedAimHeld = false;
	bSlamming = false;
	StopFiring();
	CloseAbilityLoadout();
	StopGrappleInput();

	// A downed pawn calls DisableMovement() below, so it never reaches MOVE_Walking and StopSkydive
	// never auto-fires — clear the dive/plume here or they linger on the ragdoll until respawn.
	if (bSkydiving)
	{
		bSkydiving = false;
		SetPlumeActive(false);
		if (ARedOctosphereManager* Octo = ResolveOctosphere()) { Octo->SetDropInProgress(false); }
	}
	bOrbitalDropActive = false;
	bJetpackThrusting = false;
	bDropArmed = false;
	GetWorldTimerManager().ClearTimer(LandingInvulnTimer);
	bLandingInvuln = false;

	// Enemy clones don't get a respawn flow — they despawn a few seconds after dying.
	if (bIsEnemy)
	{
		SetLifeSpan(3.f);
	}

	// Stop movement + ignore input while downed.
	if (UCharacterMovementComponent* CMC = GetCharacterMovement())
	{
		CMC->StopMovementImmediately();
		CMC->DisableMovement();
	}
	if (APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		DisableInput(PC);
	}

	// Death: hand the corpse fully to physics for a natural ragdoll. The mesh ticks with
	// AlwaysTickPoseAndRefreshBones (so remote pawns animate), which means the AnimBP keeps
	// re-authoring the upper-body pose every frame — if physics doesn't FULLY own the bones it
	// fights the sim and the limbs collapse inward ("melting / vaporized from the inside").
	// The cure: stop the anim graph from writing the pose, detach the mesh from the capsule so
	// the root can fall freely, then simulate every body at full physics blend weight.
	if (USkeletalMeshComponent* M = GetMesh())
	{
		if (DeathAnims.Num() > 0)
		{
			M->PlayAnimation(DeathAnims[FMath::RandRange(0, DeathAnims.Num() - 1)], false);
		}
		// Always finish in ragdoll, including when an optional death clip is configured. This keeps
		// the authority and clients (which enter here through OnRep_Downed) on the same presentation.
		M->SetAnimationMode(EAnimationMode::AnimationCustomMode);
		M->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPose;
			// NOTE: do NOT detach the mesh — a detached ragdoll drags the capsule far off (the
			// pawn ended up 2.7km from origin, off the floor, and respawned stuck). The standard
			// attached ragdoll simulates the bones in world space while the capsule stays put.
		M->SetCollisionProfileName(TEXT("Ragdoll"));
		M->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
		M->SetAllBodiesBelowSimulatePhysics(FName(TEXT("pelvis")), true, true);
		M->SetAllBodiesBelowPhysicsBlendWeight(FName(TEXT("pelvis")), 1.f);
		M->SetSimulatePhysics(true);
		M->WakeAllRigidBodies();
	}
	// Corpses shouldn't act as invisible walls.
	if (UCapsuleComponent* Cap = GetCapsuleComponent())
	{
		Cap->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	}
	// Drop the weapon from view.
	if (WeaponMesh)
	{
		WeaponMesh->SetVisibility(false);
	}

	// Auto-respawn after a few seconds.
	GetWorldTimerManager().SetTimer(RespawnTimer, this, &ARedPlayerCharacter::Respawn, 4.f, false);
}

void ARedPlayerCharacter::Respawn()
{
	bDowned = false;
	bReplicatedAimHeld = false;
	Health = MaxHealth;
	Shield = MaxShield;
	Armor = MaxArmor;
	WeaponSlotHeat.Init(0.0f, 2);
	WeaponSlotOverheated.Init(0, 2);
	GrappleCooldownEndServerTime = 0.0f;
	SlamCooldownEndServerTime = 0.0f;
	GetWorldTimerManager().ClearTimer(LandingInvulnTimer);  // no stale invuln on a mid-touchdown death/redrop
	bLandingInvuln = false;

	// Restore capsule collision (OnDowned turned it off for the corpse), then choose where to respawn.
	// THE DROP: return to the cloning station and redrop; else fall back to a ground PlayerStart.
	// Resetting in place left the pawn wherever the ragdoll came to rest — off the floor (stuck) or
	// in the crossfire. Board WITHOUT arming the dive yet; the mesh un-ragdoll + AnimBP restore below
	// would clobber the freefall pose, so we re-arm at the very end of Respawn.
	bool bBoardedForRedrop = false;
	if (UCapsuleComponent* Cap = GetCapsuleComponent())
	{
		Cap->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
		if (bDropLoopEnabled)
		{
			bBoardedForRedrop = BoardStationAndDrop(false);
		}
		if (!bBoardedForRedrop)
		{
			FVector Dest(0.f, 0.f, 200.f);
			if (ARedGameMode* GM = GetWorld() ? Cast<ARedGameMode>(GetWorld()->GetAuthGameMode()) : nullptr)
			{
				Dest = GM->FixedDropGroundPoint;   // same volcano land as first spawn, NOT the ocean PlayerStart
			}
			else if (AActor* Start = UGameplayStatics::GetActorOfClass(GetWorld(), APlayerStart::StaticClass()))
			{
				Dest = Start->GetActorLocation() + FVector(0.f, 0.f, Cap->GetScaledCapsuleHalfHeight() + 20.f);
			}
			SetActorLocationAndRotation(Dest, FRotator::ZeroRotator, false, nullptr, ETeleportType::TeleportPhysics);
		}
	}

	// Stand back up from ragdoll: stop physics, re-attach the mesh to the capsule and
	// restore its authored relative transform (matches the constructor offset).
	if (USkeletalMeshComponent* M = GetMesh())
	{
		M->SetSimulatePhysics(false);
		M->SetAllBodiesBelowSimulatePhysics(FName(TEXT("pelvis")), false, true);
		M->SetAllBodiesBelowPhysicsBlendWeight(FName(TEXT("pelvis")), 0.f);
		M->SetCollisionProfileName(TEXT("CharacterMesh"));
		M->AttachToComponent(GetCapsuleComponent(), FAttachmentTransformRules::SnapToTargetNotIncludingScale);
		M->SetRelativeLocationAndRotation(FVector(0.f, 0.f, -GetCapsuleComponent()->GetScaledCapsuleHalfHeight()), FRotator(0.f, -90.f, 0.f));
		// Restore AnimBP-driven animation (OnDowned switched to custom mode for the ragdoll).
		M->SetAnimationMode(EAnimationMode::AnimationBlueprint);
		M->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
	}
	if (UCharacterMovementComponent* CMC = GetCharacterMovement())
	{
		CMC->SetMovementMode(MOVE_Walking);
	}
	if (APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		EnableInput(PC);
		PC->SetInputMode(FInputModeGameOnly());
		PC->bShowMouseCursor = false;
		PC->SetIgnoreMoveInput(false);
		PC->SetIgnoreLookInput(false);
	}
	if (WeaponMesh)
	{
		WeaponMesh->SetVisibility(true);
	}

	// THE DROP: back on the station deck with the AnimBP restored. ARM the dive — it starts the
	// moment the player steps off the deck (starting it here would insta-cancel on the deck floor).
	if (bBoardedForRedrop)
	{
		bSkydiving = false;
		bDropArmed = true;
	}
	ForceNetUpdate();
}

void ARedPlayerCharacter::StartSprint()
{
	bSprintHeld = true;
	TargetWalkSpeed = SprintSpeed;
	if (!HasAuthority()) { ServerSetJetpackInput(bJetpackOn, bJumpHeld, true, bJetpackThrusting); }
}

void ARedPlayerCharacter::StopSprint()
{
	bSprintHeld = false;
	TargetWalkSpeed = WalkSpeed;
	if (!HasAuthority()) { ServerSetJetpackInput(bJetpackOn, bJumpHeld, false, bJetpackThrusting); }
}

void ARedPlayerCharacter::MoveForward(float Value)
{
	DropSteerFwd = Value;   // captured every frame (incl. 0 on release) for pitch-independent dive steering
	if (!Controller || Value == 0.f || !Camera)
	{
		return;
	}
	const FVector Up = GetActorUpVector();
	const FVector Fwd = FVector::VectorPlaneProject(Camera->GetForwardVector(), Up).GetSafeNormal();
	AddMovementInput(Fwd, Value);
}

void ARedPlayerCharacter::MoveRight(float Value)
{
	DropSteerRight = Value;   // captured every frame (incl. 0 on release) for pitch-independent dive steering
	if (!Controller || Value == 0.f || !Camera)
	{
		return;
	}
	const FVector Up = GetActorUpVector();
	const FVector Right = FVector::VectorPlaneProject(Camera->GetRightVector(), Up).GetSafeNormal();
	AddMovementInput(Right, Value);
}

void ARedPlayerCharacter::Turn(float Value)
{
	// Orbit-camera yaw: rotate the heading VECTOR around the local gravity up — full 360, always
	// level, works identically anywhere on any body.
	if (Value == 0.f)
	{
		return;
	}
	const FVector Up = RedGravity::UpAt(GetWorld(), GetActorLocation(), GetActorUpVector());
	CameraForward = CameraForward.RotateAngleAxis(Value * LookYawScale, Up).GetSafeNormal();
}

void ARedPlayerCharacter::LookUp(float Value)
{
	// Orbit-camera pitch: a clamped SCALAR (sign matches the old engine pitch feel: mouse-up looks up).
	if (Value == 0.f)
	{
		return;
	}
	CameraPitch = FMath::Clamp(CameraPitch - Value * LookPitchScale, CameraPitchMin, CameraPitchMax);
}

void ARedPlayerCharacter::UpdateOrbitCamera()
{
	if (!SpringArm)
	{
		return;
	}
	const FVector Up = RedGravity::UpAt(GetWorld(), GetActorLocation(), GetActorUpVector());

	// Keep the heading tangent to the (possibly changed) gravity plane as we move across the
	// surface, without altering where the player is looking.
	CameraForward = FVector::VectorPlaneProject(CameraForward, Up).GetSafeNormal();
	if (CameraForward.IsNearlyZero())
	{
		CameraForward = FVector::VectorPlaneProject(GetActorForwardVector(), Up).GetSafeNormal();
	}
	if (CameraForward.IsNearlyZero())
	{
		return;
	}

	// Boom rotation = heading + gravity up, then pitch about the boom's right axis.
	const FQuat YawRot = FRotationMatrix::MakeFromZX(Up, CameraForward).ToQuat();
	const FQuat FinalRot = YawRot * FQuat(FRotator(CameraPitch, 0.f, 0.f));
	SpringArm->SetWorldRotation(FinalRot);
}

void ARedPlayerCharacter::OnCameraZoom(float Value)
{
	// Never zoom while riding/boarding a ship — the possessed craft owns the wheel as throttle.
	if (Value == 0.f || GetAttachParentActor() != nullptr || !IsLocallyControlled())
	{
		return;
	}
	// Scroll up = zoom in (shorter arm); scroll down/back = zoom out (longer arm).
	ZoomArmOffset = FMath::Clamp(ZoomArmOffset - Value * ZoomStep, ZoomMin, ZoomMax);
}

void ARedPlayerCharacter::StartFiring()
{
	if (bDowned || bAbilityLoadoutOpen)
	{
		return;
	}
	bIsFiringHeld = true;
	bReplicatedAimHeld = true;
	if (!HasAuthority())
	{
		ServerSetCombatAimHeld(true);
	}
	Fire();  // immediate first shot on press
	if (GetWorld() && FireRate > 0.f)
	{
		GetWorldTimerManager().SetTimer(FireTimerHandle, this, &ARedPlayerCharacter::Fire, FireRate, true);
	}
}

void ARedPlayerCharacter::StopFiring()
{
	bIsFiringHeld = false;
	if (HasAuthority())
	{
		bReplicatedAimHeld = false;
		ForceNetUpdate();
	}
	else
	{
		ServerSetCombatAimHeld(false);
	}
	GetWorldTimerManager().ClearTimer(FireTimerHandle);
}

bool ARedPlayerCharacter::ResolveWeaponAim(FVector& OutAimPoint, FVector& OutShotDirection) const
{
	OutAimPoint = FVector::ZeroVector;
	OutShotDirection = FVector::ZeroVector;
	if (!Camera || !GetWorld())
	{
		return false;
	}

	// Prefer a pawn on the reticle (small object sweep), then resolve environment geometry with a
	// visibility trace. The final direction always starts at the ACTUAL barrel tip, eliminating
	// camera/barrel parallax while still honoring the crosshair.
	const FVector CamLoc = Camera->GetComponentLocation();
	const FVector CamFwd = Camera->GetForwardVector().GetSafeNormal();
	const FVector SweepStart = CamLoc + CamFwd * 50.f;
	const FVector SweepEnd = CamLoc + CamFwd * 100000.f;
	FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(RedWeaponAim), false, this);

	FHitResult PawnHit;
	FCollisionObjectQueryParams PawnObj;
	PawnObj.AddObjectTypesToQuery(ECC_Pawn);
	if (GetWorld()->SweepSingleByObjectType(PawnHit, SweepStart, SweepEnd,
		FQuat::Identity, PawnObj, FCollisionShape::MakeSphere(35.f), QueryParams))
	{
		OutAimPoint = PawnHit.ImpactPoint;
	}
	else
	{
		FHitResult Hit;
		OutAimPoint = GetWorld()->LineTraceSingleByChannel(
			Hit, SweepStart, SweepEnd, ECC_Visibility, QueryParams) ? Hit.ImpactPoint : SweepEnd;
	}

	const FVector MuzzleLocation = WeaponMesh ? GetMuzzleWorldLocation() : (CamLoc + CamFwd * 120.f);
	OutShotDirection = (OutAimPoint - MuzzleLocation).GetSafeNormal();
	return !OutShotDirection.IsNearlyZero();
}

void ARedPlayerCharacter::Fire()
{
	if (bHolstered) { ToggleHolster(); }  // auto-draw from the back, then fire
	// UpperBody slot montage gives visible firing feedback without taking over the legs.

	// Always-visible firing feedback: cycle the rifle's bolt via its own AnimInstance.

	// Muzzle flash at the gun barrel tip (no Barrel socket on this rifle; barrel runs along the
	// weapon's local +Y, so offset forward along Y to reach the muzzle).

	EnsureWeaponSlotState();
	const int32 FireSlot = FMath::Clamp(CurrentWeaponSlot, 0, 1);
	if (bDowned || !ProjectileClass || !Camera || IsWeaponSlotOverheated(FireSlot)
		|| WeaponSlotHeat[FireSlot] >= MaxWeaponHeat)
	{
		return;
	}
	FVector AimPoint;
	FVector ToTarget;
	if (!ResolveWeaponAim(AimPoint, ToTarget)) { return; }
	// Fire from the camera reticle ray, not the right-hand barrel. The visible rifle still
	// animates and flashes, but the authoritative projectile now follows exactly what the
	// player is aiming at instead of streaking left from barrel/camera parallax.
	// Spawn from the BARREL TIP (weapon transform + MuzzleFlashOffset — the same spot as the
	// muzzle flash). The weapon COMPONENT location is the grip pivot in the hand, which put the
	// bolt origin at the middle of the body. Direction still aims at the crosshair target.
	const FVector MuzzleLoc = GetMuzzleWorldLocation();
	// Prediction-local presentation uses the exact same origin/direction submitted to authority.
	uint16 FireSequence = NextLocalFireSequence++;
	if (FireSequence == 0)
	{
		FireSequence = NextLocalFireSequence++;
	}
	// Bound stale entries from rejected or dropped unreliable shots.
	if (PredictedFireMuzzles.Num() >= 32)
	{
		PredictedFireMuzzles.Reset();
		PredictedFireDirections.Reset();
	}
	PredictedFireMuzzles.Add(FireSequence, MuzzleLoc);
	PredictedFireDirections.Add(FireSequence, ToTarget);
	PlayFireCosmetics(MuzzleLoc, ToTarget, FireSlot);
	if (!HasAuthority())
	{
		// Owner prediction keeps the heat lock responsive; the replicated server value reconciles it.
		WeaponSlotHeat[FireSlot] = FMath::Min(
			MaxWeaponHeat, WeaponSlotHeat[FireSlot] + WeaponHeatPerShot);
		WeaponSlotOverheated[FireSlot] = WeaponSlotHeat[FireSlot] >= MaxWeaponHeat ? 1 : 0;
	}
	// Server-authoritative so the replicated bolt is visible to all players.
	if (HasAuthority())
	{
		TryFireAuthoritative(ToTarget, MuzzleLoc, FireSequence);
	}
	else
	{
		ServerFire(MuzzleLoc, ToTarget, FireSequence);
	}
}

void ARedPlayerCharacter::ServerFire_Implementation(FVector_NetQuantize ClientMuzzleLocation,
	FVector_NetQuantizeNormal AimDirection, uint16 ClientFireSequence)
{
	TryFireAuthoritative(AimDirection, ClientMuzzleLocation, ClientFireSequence);
}

void ARedPlayerCharacter::PlayFireCosmetics(const FVector& MuzzleLocation, const FVector& ShotDirection,
	const int32 WeaponSlot)
{
	LastFireTime = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.f;

	if (RifleFireAnim && GetMesh())
	{
		if (UAnimInstance* AnimInstance = GetMesh()->GetAnimInstance())
		{
			AnimInstance->PlaySlotAnimationAsDynamicMontage(
				RifleFireAnim, FName(TEXT("DefaultSlot")), 0.04f, 0.12f, 1.2f, 1, 0.f, 0.f);
		}
	}
	else if (FireMontage && GetMesh() && GetMesh()->GetAnimInstance())
	{
		GetMesh()->GetAnimInstance()->Montage_Play(FireMontage, 1.f);
	}

	if (WeaponFireMontage && WeaponMesh && WeaponMesh->GetAnimInstance())
	{
		WeaponMesh->GetAnimInstance()->Montage_Play(WeaponFireMontage, 1.f);
	}

	UNiagaraSystem* SelectedMuzzleFlash = WeaponSlot == 0 && EnergyMuzzleFlashFX
		? EnergyMuzzleFlashFX : MuzzleFlashFX;
	if (SelectedMuzzleFlash && WeaponMesh)
	{
		// P_Flash_4 emits along local +X. Align +X to the accepted projectile trajectory
		// instead of inheriting the rifle socket rotation, which made the flash point down.
		const FVector SafeDirection = ShotDirection.GetSafeNormal();
		const FRotator FlashRotation = SafeDirection.IsNearlyZero()
			? WeaponMesh->GetComponentRotation()
			: SafeDirection.Rotation();
		UNiagaraFunctionLibrary::SpawnSystemAtLocation(
			GetWorld(), SelectedMuzzleFlash, MuzzleLocation, FlashRotation,
			WeaponSlot == 0 ? FVector(1.18f) : FVector::OneVector, true);
	}

	if (WeaponFireSound)
	{
		UGameplayStatics::PlaySoundAtLocation(
			this, WeaponFireSound, MuzzleLocation, 1.f, 1.f, 0.f, WeaponSoundAttenuation);
	}
}

bool ARedPlayerCharacter::TryFireAuthoritative(const FVector& AimDirection,
	const FVector& RequestedMuzzleLocation, uint16 ClientFireSequence)
{
	if (!HasAuthority() || bDowned || !ProjectileClass || !GetWorld())
	{
		return false;
	}
	EnsureWeaponSlotState();
	const int32 FireSlot = FMath::Clamp(CurrentWeaponSlot, 0, 1);
	if (IsWeaponSlotOverheated(FireSlot) || WeaponSlotHeat[FireSlot] >= MaxWeaponHeat)
	{
		WeaponSlotOverheated[FireSlot] = 1;
		ForceNetUpdate();
		return false;
	}

	const float Now = GetWorld()->GetTimeSeconds();
	const float MinServerInterval = FMath::Max(0.04f, FireRate * 0.75f);
	if ((Now - LastServerFireTime) < MinServerInterval)
	{
		return false;
	}

	const FVector SafeAim = AimDirection.GetSafeNormal();
	if (SafeAim.IsNearlyZero())
	{
		return false;
	}

	if (bHolstered)
	{
		bHolstered = false;
		ApplyHolsterState();
	}

	LastServerFireTime = Now;
	LastFireTime = Now;
	bReplicatedAimHeld = true;
	ReplicatedAimDirection = SafeAim;
	WeaponSlotHeat[FireSlot] = FMath::Min(
		MaxWeaponHeat, WeaponSlotHeat[FireSlot] + WeaponHeatPerShot);
	WeaponSlotOverheated[FireSlot] = WeaponSlotHeat[FireSlot] >= MaxWeaponHeat ? 1 : 0;
	const FVector ServerMuzzleLocation = GetMuzzleWorldLocation();
	FVector MuzzleLocation = ServerMuzzleLocation;
	// The owning client's AnimBP can be one network frame ahead of the server's simulated pose.
	// Accept the visual barrel tip only inside a tight authoritative envelope; otherwise fall back
	// to the server socket so a client cannot invent a remote firing origin.
	if (!RequestedMuzzleLocation.ContainsNaN()
		&& FVector::DistSquared(RequestedMuzzleLocation, GetActorLocation()) <= FMath::Square(180.f)
		&& FVector::DistSquared(RequestedMuzzleLocation, ServerMuzzleLocation) <= FMath::Square(175.f))
	{
		MuzzleLocation = RequestedMuzzleLocation;
	}
	SpawnBolt(MuzzleLocation + SafeAim * 10.f, SafeAim.Rotation(), FireSlot);
	MulticastFireCosmetics(MuzzleLocation, SafeAim, ClientFireSequence, static_cast<uint8>(FireSlot));
	ForceNetUpdate();
	return true;
}

void ARedPlayerCharacter::MulticastFireCosmetics_Implementation(
	FVector_NetQuantize MuzzleLocation, FVector_NetQuantizeNormal ShotDirection,
	uint16 ClientFireSequence, uint8 WeaponSlot)
{
	ReplicatedAimDirection = ShotDirection;
	// Suppress the owner's authoritative echo only when it matches that exact predicted shot.
	// If authority corrected an out-of-envelope barrel pose, replay at the accepted transform.
	if (IsPlayerControlled() && IsLocallyControlled())
	{
		const FVector* PredictedMuzzle = PredictedFireMuzzles.Find(ClientFireSequence);
		const FVector* PredictedDirection = PredictedFireDirections.Find(ClientFireSequence);
		const FVector AcceptedDirection = ShotDirection.GetSafeNormal();
		const bool bPredictionMatches = ClientFireSequence != 0 && PredictedMuzzle && PredictedDirection
			&& FVector::DistSquared(*PredictedMuzzle, MuzzleLocation) <= FMath::Square(2.f)
			&& FVector::DotProduct(PredictedDirection->GetSafeNormal(), AcceptedDirection) >= 0.9999f;
		PredictedFireMuzzles.Remove(ClientFireSequence);
		PredictedFireDirections.Remove(ClientFireSequence);
		if (!bPredictionMatches)
		{
			PlayFireCosmetics(MuzzleLocation, AcceptedDirection, WeaponSlot);
		}
		else
		{
			LastFireTime = GetWorld() ? GetWorld()->GetTimeSeconds() : LastFireTime;
		}
	}
	else
	{
		PlayFireCosmetics(MuzzleLocation, ShotDirection, WeaponSlot);
	}
}

void ARedPlayerCharacter::ServerSetCombatAimHeld_Implementation(bool bHeld)
{
	bReplicatedAimHeld = bHeld && !bDowned && !bHolstered;
	ForceNetUpdate();
}

void ARedPlayerCharacter::ServerSetAimDirection_Implementation(FVector_NetQuantizeNormal AimDirection)
{
	const FVector SafeAim = AimDirection.GetSafeNormal();
	if (!SafeAim.IsNearlyZero() && !SafeAim.ContainsNaN())
	{
		ReplicatedAimDirection = SafeAim;
	}
}

FVector ARedPlayerCharacter::GetMuzzleWorldLocation() const
{
	if (WeaponMesh)
	{
		if (WeaponMesh->DoesSocketExist(MuzzleSocket))
		{
			return WeaponMesh->GetSocketLocation(MuzzleSocket);
		}
		return WeaponMesh->GetComponentTransform().TransformPosition(MuzzleFlashOffset);
	}
	return GetActorLocation() + GetActorForwardVector() * 100.f;
}

void ARedPlayerCharacter::SpawnBolt(FVector Start, FRotator Dir, const int32 WeaponSlot)
{
	if (!HasAuthority() || !ProjectileClass || !GetWorld())
	{
		return;
	}
	FActorSpawnParameters Params;
	Params.Owner = this;
	Params.Instigator = this;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AActor* Spawned = GetWorld()->SpawnActor<AActor>(ProjectileClass, Start, Dir, Params);
	if (ARedBolt* Bolt = Cast<ARedBolt>(Spawned))
	{
		// Mining carve DISABLED again: the runtime VoxelStampActor renders a visible (black) preview
		// blob in PIE that piles up one-per-shot. Re-enable only once the stamp preview is suppressed
		// at the plugin source (or replaced with a preview-less runtime surface edit).
		// ProjectilesVol1 hit systems are authored near unit scale. The old value 8 was
		// specific to the retired DMD impact and made the replacement burst enormous.
		const bool bEnergyWeapon = WeaponSlot == 0;
		Bolt->ConfigureImpactProfile(
			bEnergyWeapon ? 1.45f : 0.95f,
			bEnergyWeapon ? 1.25f : 0.78f,
			0.f, WeaponDamage);
		Bolt->ConfigureGroundImpact(false, false, false);
		Bolt->SetEffectProfile(bEnergyWeapon ? 1 : 2);
		Bolt->SetBeamColor(bEnergyWeapon ? EnergyBoltColor : RifleBoltColor);
		Bolt->SetBeamDimensions(
			bEnergyWeapon ? EnergyBoltLength : RifleBoltLength,
			bEnergyWeapon ? EnergyBoltRadius : RifleBoltRadius);
		// Energy is a broad electric orb; rifle is a faster, compact ballistic streak.
		const float MuzzleSpeed = bEnergyWeapon ? EnergyMuzzleSpeed : RifleMuzzleSpeed;
		Bolt->LaunchWithVelocity(Dir.Vector() * MuzzleSpeed + GetVelocity() * 0.35f);
	}
	// Gunshot audio at the muzzle, spatialized (ATT_Shot) so distant shots — player + enemy — fall off.
}

void ARedPlayerCharacter::ApplyWeaponGripOffset()
{
	if (!WeaponMesh)
	{
		return;
	}
	// Directions expressed in hand_r bone space (measured live in the carry pose):
	//   barrel-forward = (-0.97, 0.09, 0.23);  char-up = (-0.012, -0.668, 0.744)
	const FVector Base(8.0f, 3.0f, -2.0f);
	const FVector BarrelInHand(-0.97f, 0.09f, 0.23f);
	const FVector UpInHand(-0.012f, -0.668f, 0.744f);
	const FVector InwardInHand(0.495f, 0.649f, 0.577f);   // toward the chest (measured: -charFwd in hand space)
	WeaponMesh->SetRelativeLocation(Base + BarrelInHand * WeaponGripSlide + UpInHand * WeaponRaiseSlide + InwardInHand * WeaponInwardSlide);

	// Base carry rotation, then LOCAL tips: pitch around local X tips the barrel (local +Y) up/down;
	// roll around local Y (the barrel) rotates the "top" like a clock face toward the chest.
	const FQuat BaseRot = FRotator(0.0f, 85.0f, -6.0f).Quaternion();
	const FQuat PitchDelta(FVector::ForwardVector, FMath::DegreesToRadians(-WeaponPitchDeg));
	const FQuat RollDelta(FVector::RightVector, FMath::DegreesToRadians(WeaponRollDeg));
	WeaponMesh->SetRelativeRotation((BaseRot * PitchDelta * RollDelta).Rotator());
}

void ARedPlayerCharacter::WeaponGrip(float ForwardCm)
{
	WeaponGripSlide = ForwardCm;
	ApplyWeaponGripOffset();
	if (GEngine) { GEngine->AddOnScreenDebugMessage(-1, 3.f, FColor::Cyan, FString::Printf(TEXT("WeaponGrip %.1f"), ForwardCm)); }
}

void ARedPlayerCharacter::WeaponRaise(float UpCm)
{
	WeaponRaiseSlide = UpCm;
	ApplyWeaponGripOffset();
	if (GEngine) { GEngine->AddOnScreenDebugMessage(-1, 3.f, FColor::Cyan, FString::Printf(TEXT("WeaponRaise %.1f (neg=down)"), UpCm)); }
}

void ARedPlayerCharacter::WeaponPitch(float DownDeg)
{
	WeaponPitchDeg = DownDeg;
	ApplyWeaponGripOffset();
	if (GEngine) { GEngine->AddOnScreenDebugMessage(-1, 3.f, FColor::Cyan, FString::Printf(TEXT("WeaponPitch %.1f (pos=muzzle down)"), DownDeg)); }
}

void ARedPlayerCharacter::WeaponRoll(float Deg)
{
	WeaponRollDeg = Deg;
	ApplyWeaponGripOffset();
	if (GEngine) { GEngine->AddOnScreenDebugMessage(-1, 3.f, FColor::Cyan, FString::Printf(TEXT("WeaponRoll %.1f (top 11->2 o'clock ~90)"), Deg)); }
}

void ARedPlayerCharacter::WeaponInward(float TowardChestCm)
{
	WeaponInwardSlide = TowardChestCm;
	ApplyWeaponGripOffset();
	if (GEngine) { GEngine->AddOnScreenDebugMessage(-1, 3.f, FColor::Cyan, FString::Printf(TEXT("WeaponInward %.1f (pos=toward chest)"), TowardChestCm)); }
}

void ARedPlayerCharacter::WeaponAimNudge(float X, float Y, float Z)
{
	WeaponAimNudgeOffset = FVector(X, Y, Z);
	if (GEngine) { GEngine->AddOnScreenDebugMessage(-1, 3.f, FColor::Cyan, FString::Printf(TEXT("WeaponAimNudge (%.1f, %.1f, %.1f) — applied while aiming"), X, Y, Z)); }
}

ARedOctosphereManager* ARedPlayerCharacter::ResolveOctosphere()
{
	if (ARedOctosphereManager* Cached = CachedOctosphere.Get())
	{
		return Cached;
	}
	if (GetWorld())
	{
		for (TActorIterator<ARedOctosphereManager> It(GetWorld()); It; ++It)
		{
			if (IsValid(*It)) { CachedOctosphere = *It; return *It; }
		}
	}
	return nullptr;
}

bool ARedPlayerCharacter::BoardStationAndDrop(bool bArmDive)
{
	if (bIsEnemy) { return false; }  // enemy clones don't drop

	ARedCloningStation* Station = CachedStation.Get();
	if (!Station && GetWorld())
	{
		for (TActorIterator<ARedCloningStation> It(GetWorld()); It; ++It)
		{
			if (IsValid(*It)) { Station = *It; CachedStation = Station; break; }
		}
	}
	if (!Station) { return false; }

	// Clear the radial fall-guard so the deck's orbital radius isn't mistaken for "ground" (else the dive stalls).
	if (URedCharacterMovement* RedCMC = Cast<URedCharacterMovement>(GetCharacterMovement()))
	{
		RedCMC->ResetFallGuard();
	}

	const FTransform DropXf = Station->GetDropTransform();
	SetActorLocationAndRotation(DropXf.GetLocation(), DropXf.GetRotation().Rotator(), false, nullptr, ETeleportType::TeleportPhysics);

	bSkydiving = false;  // clear any stale air-death dive
	// ARM the dive instead of starting it: on the deck the CMC is "walking", so StartSkydive here
	// would insta-cancel. Tick starts the real dive the moment the pawn steps off and starts falling.
	bDropArmed = bArmDive;
	if (GEngine) { GEngine->AddOnScreenDebugMessage(-1, 4.f, FColor::Cyan, TEXT("THE DROP - boarded station. Step off the edge to dive!")); }
	return true;
}

void ARedPlayerCharacter::BeginOrbitalDrop(float InFallSpeed)
{
	// Pawn is already spawned high in the air (octosphere test). Clear the radial fall-guard so the
	// spawn altitude isn't read as "ground", set the controlled re-entry descent speed, then start the
	// dive directly: put the CMC into MOVE_Falling and engage the freefall pose immediately (no wait
	// for the arm->fall handshake, which was ambiguous at the spawn frame).
	if (URedCharacterMovement* RedCMC = Cast<URedCharacterMovement>(GetCharacterMovement()))
	{
		RedCMC->ResetFallGuard();
	}
	// Kill the spawn-time surface snap so it can't teleport the diver to the ground mid-fall.
	GetWorldTimerManager().ClearTimer(SurfaceSnapRetryTimer);
	if (InFallSpeed > 0.f)
	{
		OrbitalDropFallSpeed = InFallSpeed;
		SkydiveMaxFallSpeed = InFallSpeed;   // keeps the landing-slam strength span scaled to this drop
	}
	bOrbitalDropActive = true;
	bJetpackThrusting = false;
	bDropArmed = false;
	if (UCharacterMovementComponent* CMC = GetCharacterMovement())
	{
		CMC->SetMovementMode(MOVE_Falling);
		CMC->Velocity = FVector::ZeroVector;
	}
	// Open the dive looking DOWN at the planet, then hand the camera to the player (Tick no longer
	// forces the pitch, so the mouse is free to look wherever you want the whole way down).
	CameraPitch = OrbitalDropCameraPitch;
	StartSkydive();   // sets bSkydiving, freefall pose, plume, dive gravity — Tick drives the descent
	// Tick authors the horizontal steer velocity itself; kill air-control so it doesn't fight it.
	if (UCharacterMovementComponent* DiveCMC = GetCharacterMovement()) { DiveCMC->AirControl = 0.f; }
	if (GEngine) { GEngine->AddOnScreenDebugMessage(-1, 4.f, FColor::Cyan, TEXT("ORBITAL DROP - free-falling into the planet (hold Space = jetpack)")); }
}

bool ARedPlayerCharacter::IsNearGround() const
{
	UWorld* W = GetWorld();
	if (!W) { return false; }
	const FVector Up = GetActorUpVector();
	const float HalfH = GetCapsuleComponent() ? GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 90.f;
	const FVector Start = GetActorLocation();
	const FVector End = Start - Up * (HalfH + 150.f);
	FHitResult Hit;
	FCollisionQueryParams QP(SCENE_QUERY_STAT(DropGround), false, this);
	return W->LineTraceSingleByChannel(Hit, Start, End, ECC_WorldStatic, QP);
}

void ARedPlayerCharacter::StartJetpack()
{
	// During the orbital drop, Space is the descent-slowing thruster (existing behavior).
	if (bOrbitalDropActive)
	{
		bJetpackThrusting = true;
		if (!HasAuthority()) { ServerSetJetpackInput(bJetpackOn, bJumpHeld, bSprintHeld, true); }
		return;
	}
	// Otherwise Space is the general JETPACK: two quick taps engage it, then hold to thrust upward.
	bJumpHeld = true;
	const float Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.f;
	if (Now - LastJumpPressTime <= JetpackDoubleTapWindow) { bJetpackOn = true; }
	LastJumpPressTime = Now;
	if (!HasAuthority()) { ServerSetJetpackInput(bJetpackOn, bJumpHeld, bSprintHeld, false); }
}

void ARedPlayerCharacter::StopJetpack()
{
	if (!HasAuthority()) { ServerSetJetpackInput(bJetpackOn, false, bSprintHeld, false); }
	bJetpackThrusting = false;   // orbital-drop thruster
	bJumpHeld = false;           // general jetpack: release Space → stop thrusting (fall)
}

void ARedPlayerCharacter::ServerSetJetpackInput_Implementation(
	bool bEngaged, bool bThrust, bool bBoost, bool bOrbitalThrust)
{
	if (bDowned) { return; }
	bJetpackOn = bEngaged;
	bJumpHeld = bThrust;
	bSprintHeld = bBoost;
	bJetpackThrusting = bOrbitalThrust;
	ForceNetUpdate();
}

void ARedPlayerCharacter::OnRep_JetpackState()
{
	bThrustFXWanted = (bJetpackOn && bJumpHeld) || (bOrbitalDropActive && bJetpackThrusting);
	UpdateJetpackFlightAnim(IsCombatAiming());
}

void ARedPlayerCharacter::ToggleHoverboard()
{
	if (!bHoverboardEnabled) { return; }   // hoverboard removed for now (see bHoverboardEnabled)
	if (bDowned || bOrbitalDropActive || bSkydiving) { return; }
	UCharacterMovementComponent* CMC = GetCharacterMovement();
	if (!CMC) { return; }
	bHoverboarding = !bHoverboarding;
	if (bHoverboarding)
	{
		SavedGroundFriction = CMC->GroundFriction;
		SavedBrakingWalk    = CMC->BrakingDecelerationWalking;
		CMC->GroundFriction = HoverboardFriction;   // glide
		CMC->BrakingDecelerationWalking = 120.f;     // barely brakes → keeps momentum off cliffs
		if (HoverboardMesh) { HoverboardMesh->SetVisibility(true); }
		if (GEngine) { GEngine->AddOnScreenDebugMessage(-1, 2.f, FColor::Cyan, TEXT("HOVERBOARD ON — ride slopes to build speed; off a cliff → dbl-Space jetpack, RMB grapple, Ctrl slam")); }
	}
	else
	{
		CMC->GroundFriction = SavedGroundFriction;
		CMC->BrakingDecelerationWalking = SavedBrakingWalk;
		if (HoverboardMesh) { HoverboardMesh->SetVisibility(false); }
	}
}

void ARedPlayerCharacter::StartSlam()
{
	if (bSlamming || bDowned || bSkydiving || bOrbitalDropActive)
	{
		return;
	}

	UCharacterMovementComponent* CMC = GetCharacterMovement();
	if (!CMC)
	{
		return;
	}
	const bool bGrounded = CMC->MovementMode == MOVE_Walking || CMC->MovementMode == MOVE_NavWalking;
	if (!bGrounded && CMC->MovementMode != MOVE_Falling)
	{
		return;
	}

	bSlamming = true;
	SlamWindupRemaining = bGrounded ? SlamGroundWindupDuration : SlamAirWindupDuration;
	if (bGrounded)
	{
		// E is useful on foot: pop into a short, readable anticipation hop, then drive straight back
		// into the surface. Preserve horizontal momentum so the move still feels responsive while running.
		FVector Up = -CMC->GetGravityDirection().GetSafeNormal();
		if (Up.IsNearlyZero())
		{
			Up = RedGravity::UpAt(GetWorld(), GetActorLocation(), GetActorUpVector());
		}
		const FVector TangentVelocity = FVector::VectorPlaneProject(CMC->Velocity, Up);
		CMC->SetMovementMode(MOVE_Falling);
		CMC->Velocity = TangentVelocity + Up * SlamHopSpeed;
		CMC->UpdateComponentVelocity();
	}

	BeginSlamPresentation(SlamWindupRemaining);
	if (HasAuthority())
	{
		ForceNetUpdate();
	}
}

void ARedPlayerCharacter::OnRep_Slamming()
{
	if (bSlamming)
	{
		BeginSlamPresentation(SlamGroundWindupDuration);
	}
	else if (!GetWorldTimerManager().IsTimerActive(SlamImpactPoseTimer))
	{
		RestoreSlamAnimation();
	}
}

void ARedPlayerCharacter::BeginSlamPresentation(float WindupSeconds)
{
	if (GetNetMode() == NM_DedicatedServer || !GetWorld())
	{
		return;
	}
	GetWorldTimerManager().ClearTimer(SlamDivePoseTimer);
	GetWorldTimerManager().ClearTimer(SlamImpactPoseTimer);

	USkeletalMeshComponent* M = GetMesh();
	if (!M || !IsUsingTrooperBody())
	{
		return;
	}
	if (SlamWindupAnim)
	{
		M->PlayAnimation(SlamWindupAnim, false);
		M->SetPlayRate(1.15f);
	}
	if (SlamDiveAnim)
	{
		GetWorldTimerManager().SetTimer(SlamDivePoseTimer, this,
			&ARedPlayerCharacter::PlaySlamDivePose, FMath::Max(0.03f, WindupSeconds), false);
	}
}

void ARedPlayerCharacter::PlaySlamDivePose()
{
	if (!bSlamming || GetNetMode() == NM_DedicatedServer)
	{
		return;
	}
	if (USkeletalMeshComponent* M = GetMesh(); M && IsUsingTrooperBody() && SlamDiveAnim)
	{
		M->PlayAnimation(SlamDiveAnim, true);
		M->SetPlayRate(1.35f);
	}
}

void ARedPlayerCharacter::PlaySlamImpactPose()
{
	if (GetNetMode() == NM_DedicatedServer || !GetWorld())
	{
		return;
	}
	GetWorldTimerManager().ClearTimer(SlamDivePoseTimer);
	GetWorldTimerManager().ClearTimer(SlamImpactPoseTimer);
	if (USkeletalMeshComponent* M = GetMesh(); M && IsUsingTrooperBody() && SlamImpactAnim)
	{
		M->PlayAnimation(SlamImpactAnim, false);
		M->SetPlayRate(0.9f);
		const float RecoveryTime = FMath::Clamp(SlamImpactAnim->GetPlayLength() / 0.9f, 0.28f, 1.25f);
		GetWorldTimerManager().SetTimer(SlamImpactPoseTimer, this,
			&ARedPlayerCharacter::RestoreSlamAnimation, RecoveryTime, false);
	}
	else
	{
		RestoreSlamAnimation();
	}
}

void ARedPlayerCharacter::RestoreSlamAnimation()
{
	if (bSlamming || bDowned)
	{
		return;
	}
	if (USkeletalMeshComponent* M = GetMesh())
	{
		M->SetPlayRate(1.0f);
		M->SetAnimationMode(EAnimationMode::AnimationBlueprint);
		if (IsUsingTrooperBody() && TrooperAnimClass && M->GetAnimClass() != TrooperAnimClass)
		{
			M->SetAnimInstanceClass(TrooperAnimClass);
		}
	}
}

void ARedPlayerCharacter::RestartOrbitalDrop()
{
	if (bDowned) { return; }
	if (bOrbitInspectionActive)
	{
		bOrbitInspectionActive = false;
		SetActorHiddenInGame(false);
		BeginOrbitalDrop(3000.f);
		if (GEngine)
		{
			GEngine->AddOnScreenDebugMessage(-1, 3.f, FColor::Cyan,
				TEXT("ORBITAL DROP - re-entry active (hold Space for jetpack)"));
		}
		return;
	}
	// Prefer the live PlanetGen frame. The old octosphere manager can coexist in migrated maps,
	// but using it first teleported the tester above a retired six-kilometre prototype instead
	// of the fused 50 km planet.
	FVector Target = GetActorLocation() + FVector(0.f, 0.f, 800000.f);
	FVector PlanetCenter = FVector::ZeroVector;
	float SafetyDatumRadius = 0.f;
	float PeakRadius = 0.f;
	if (RedGravity::FindMeshPlanet(GetWorld(), PlanetCenter, SafetyDatumRadius, &PeakRadius))
	{
		const float NominalSurfaceRadius = (SafetyDatumRadius + PeakRadius) * 0.5f;
		FVector RadialDirection = (GetActorLocation() - PlanetCenter).GetSafeNormal();
		if (RadialDirection.IsNearlyZero())
		{
			RadialDirection = FVector::UpVector;
		}
		// At 15 km the small globe's 40.6 degree angular diameter only barely fits
		// the 80 degree horizontal / 50.5 degree vertical camera even at the -85
		// pitch clamp. Twenty-five kilometres leaves a safe full-globe margin on
		// 16:9 and ultrawide acceptance captures without changing normal gameplay FOV.
		constexpr float InspectionAltitudeCm = 2500000.f;
		Target = PlanetCenter + RadialDirection * (NominalSurfaceRadius + InspectionAltitudeCm);
	}
	else if (ARedOctosphereManager* Octo = ResolveOctosphere())
	{
		const FVector C = Octo->PlanetCenter;
		const float R = Octo->PlanetRadius;
		const float DropAlt = FMath::Max(100000.f, Octo->DropStartAltitude);
		Target = FVector(C.X, C.Y, C.Z + R + DropAlt);   // top of the sphere + drop altitude
	}
	SetActorLocation(Target, false, nullptr, ETeleportType::TeleportPhysics);
	bOrbitInspectionActive = true;
	bOrbitalDropActive = false;
	bSkydiving = false;
	bDropArmed = false;
	bJetpackThrusting = false;
	bADS = false;
	if (UCharacterMovementComponent* InspectionMovement = GetCharacterMovement())
	{
		InspectionMovement->StopMovementImmediately();
		InspectionMovement->SetMovementMode(MOVE_Flying);
	}
	// Keep the live pawn/camera so mouse orbit and presentation systems still run,
	// while removing the body and rifle from the full-globe acceptance frame.
	SetActorHiddenInGame(true);
	if (Camera)
	{
		Camera->SetFieldOfView(BaseFOV);
	}
	// Centre the first stable frame on the globe; mouse look remains free.
	CameraPitch = CameraPitchMin;
	UpdateOrbitCamera();
	if (GEngine)
	{
		GEngine->AddOnScreenDebugMessage(-1, 4.f, FColor::Cyan,
			TEXT("ORBIT INSPECTION - stable view (F9 again to begin re-entry)"));
	}
}

void ARedPlayerCharacter::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(ARedPlayerCharacter, bSkydiving);
	DOREPLIFETIME(ARedPlayerCharacter, bGrappling);
	DOREPLIFETIME(ARedPlayerCharacter, GrapplePoint);
	DOREPLIFETIME(ARedPlayerCharacter, GrappleNormal);
	DOREPLIFETIME(ARedPlayerCharacter, GrappleTarget);
	DOREPLIFETIME(ARedPlayerCharacter, Health);
	DOREPLIFETIME(ARedPlayerCharacter, Shield);
	DOREPLIFETIME(ARedPlayerCharacter, Armor);
	DOREPLIFETIME(ARedPlayerCharacter, Fuel);
	DOREPLIFETIME(ARedPlayerCharacter, bDowned);
	DOREPLIFETIME(ARedPlayerCharacter, bHolstered);
	DOREPLIFETIME(ARedPlayerCharacter, bReplicatedAimHeld);
	DOREPLIFETIME(ARedPlayerCharacter, ReplicatedAimDirection);
	DOREPLIFETIME(ARedPlayerCharacter, CurrentWeaponSlot);
	DOREPLIFETIME(ARedPlayerCharacter, WeaponSlotHeat);
	DOREPLIFETIME(ARedPlayerCharacter, WeaponSlotOverheated);
	DOREPLIFETIME(ARedPlayerCharacter, ResStone);
	DOREPLIFETIME(ARedPlayerCharacter, ResIron);
	DOREPLIFETIME(ARedPlayerCharacter, ResCrystal);
	DOREPLIFETIME(ARedPlayerCharacter, AbilitySlotQ);
	DOREPLIFETIME(ARedPlayerCharacter, AbilitySlotE);
	DOREPLIFETIME(ARedPlayerCharacter, GrappleCooldownEndServerTime);
	DOREPLIFETIME(ARedPlayerCharacter, SlamCooldownEndServerTime);
	DOREPLIFETIME(ARedPlayerCharacter, bSlamming);
	DOREPLIFETIME(ARedPlayerCharacter, bIsEnemy);
	DOREPLIFETIME(ARedPlayerCharacter, bOrbitalDropActive);
	DOREPLIFETIME(ARedPlayerCharacter, bJetpackOn);
	DOREPLIFETIME(ARedPlayerCharacter, bJetpackThrusting);
	DOREPLIFETIME(ARedPlayerCharacter, bJumpHeld);
	DOREPLIFETIME(ARedPlayerCharacter, bSprintHeld);
}

void ARedPlayerCharacter::ToggleFastDayNightTest()
{
	if (!GetWorld())
	{
		return;
	}
	for (TActorIterator<ARedDayNight> It(GetWorld()); It; ++It)
	{
		if (!IsValid(*It))
		{
			continue;
		}
		const bool bEnableFastCycle = It->DayLengthSeconds > 60.f;
		It->DayLengthSeconds = bEnableFastCycle ? 30.f : 7200.f;
		if (GEngine)
		{
			GEngine->AddOnScreenDebugMessage(-1, 3.f, FColor::Cyan,
				bEnableFastCycle
					? TEXT("RENDER TEST: 30-second day/night cycle enabled")
					: TEXT("RENDER TEST: two-hour day/night cycle restored"));
		}
		return;
	}
}

void ARedPlayerCharacter::TeleportToShorelineVisualTest()
{
#if !UE_BUILD_SHIPPING
	if (!GetWorld() || !IsLocallyControlled())
	{
		return;
	}

	// Deterministically sampled from the fused 50 km height field at a physical
	// land/sea crossing. Keep this visual-only camera ten metres above the true
	// PlanetGen sea datum; falling onto the nearby low collision LOD put the camera
	// inside the global water sphere and produced a misleading white/blue frame.
	ACLMPlanet* Planet = nullptr;
	for (TActorIterator<ACLMPlanet> It(GetWorld()); It; ++It)
	{
		if (IsValid(*It))
		{
			Planet = *It;
			break;
		}
	}
	const FVector SampleCenterDirection =
		RedPlanetPresentationTuning::NightWaterT04ShoreDirection();
	FVector ResolvedCoastDirection = SampleCenterDirection;
	FVector PlanetCenter = FVector::ZeroVector;
	float WaterRadiusCm = 796475.1f;
	FVector ForwardTowardWater = FVector::VectorPlaneProject(
		FVector::CrossProduct(SampleCenterDirection, FVector::UpVector),
		SampleCenterDirection).GetSafeNormal();
	float MinimumSignedHeightCm = TNumericLimits<float>::Max();
	float MaximumSignedHeightCm = TNumericLimits<float>::Lowest();
	if (Planet)
	{
		PlanetCenter = Planet->GetActorLocation();
		const float SeaHeightCm = Planet->MinHeight
			+ (Planet->MaxHeight - Planet->MinHeight) * Planet->SeaLevel;
		WaterRadiusCm = Planet->PlanetRadius + SeaHeightCm;
		FVector TangentX = FVector::CrossProduct(
			SampleCenterDirection, FVector::UpVector).GetSafeNormal();
		if (TangentX.IsNearlyZero())
		{
			TangentX = FVector::CrossProduct(
				SampleCenterDirection, FVector::ForwardVector).GetSafeNormal();
		}
		const FVector TangentY = FVector::CrossProduct(
			SampleCenterDirection, TangentX).GetSafeNormal();
		FVector WaterDirection = SampleCenterDirection;
		FVector LandDirection = SampleCenterDirection;
		constexpr int32 BearingCount = 32;
		constexpr float ProbeAngleRadians = 0.0125f;
		for (int32 BearingIndex = 0; BearingIndex < BearingCount; ++BearingIndex)
		{
			const float Bearing = UE_TWO_PI * static_cast<float>(BearingIndex)
				/ static_cast<float>(BearingCount);
			const FVector Tangent = TangentX * FMath::Cos(Bearing)
				+ TangentY * FMath::Sin(Bearing);
			const FVector Direction = (SampleCenterDirection * FMath::Cos(ProbeAngleRadians)
				+ Tangent * FMath::Sin(ProbeAngleRadians)).GetSafeNormal();
			float ResolvedHeightCm = 0.f;
			if (!RedPlanetGenCompat::SampleResolvedSurface(Planet, Direction, ResolvedHeightCm))
			{
				continue;
			}
			const float SignedHeightCm = ResolvedHeightCm - SeaHeightCm;
			if (SignedHeightCm < MinimumSignedHeightCm)
			{
				MinimumSignedHeightCm = SignedHeightCm;
				WaterDirection = Direction;
			}
			if (SignedHeightCm > MaximumSignedHeightCm)
			{
				MaximumSignedHeightCm = SignedHeightCm;
				LandDirection = Direction;
			}
		}
		// Resolve the actual zero-height crossing between the best water and land
		// samples. The old harness measured both, then left the pawn at the unrelated
		// centre direction, so the screenshot contained only a distant blue horizon.
		if (MinimumSignedHeightCm <= 0.f && MaximumSignedHeightCm >= 0.f)
		{
			for (int32 Iteration = 0; Iteration < 18; ++Iteration)
			{
				const FVector MidDirection = (WaterDirection + LandDirection).GetSafeNormal();
				float MidHeightCm = 0.f;
				if (!RedPlanetGenCompat::SampleResolvedSurface(Planet, MidDirection, MidHeightCm))
				{
					break;
				}
				if (MidHeightCm - SeaHeightCm <= 0.f)
				{
					WaterDirection = MidDirection;
					MinimumSignedHeightCm = MidHeightCm - SeaHeightCm;
				}
				else
				{
					LandDirection = MidDirection;
					MaximumSignedHeightCm = MidHeightCm - SeaHeightCm;
				}
			}
			ResolvedCoastDirection = (WaterDirection + LandDirection).GetSafeNormal();
		}
		ForwardTowardWater = FVector::VectorPlaneProject(
			WaterDirection - LandDirection, ResolvedCoastDirection).GetSafeNormal();
	}
	if (ForwardTowardWater.IsNearlyZero())
	{
		ForwardTowardWater = FVector::CrossProduct(
			ResolvedCoastDirection, FVector::UpVector).GetSafeNormal();
	}
	const FVector ShorelineLocation = PlanetCenter
		+ ResolvedCoastDirection * (WaterRadiusCm + 300.f);
	SetActorLocation(ShorelineLocation, false, nullptr, ETeleportType::TeleportPhysics);
	SetActorRotation(FRotationMatrix::MakeFromXZ(
		ForwardTowardWater, ResolvedCoastDirection).Rotator());
	CameraForward = ForwardTowardWater;
	// Keep the resolved coast in the lower frame and the ocean across the centre.
	// Positive pitch looked upward in the actual orbit camera and reduced the
	// verified ocean to 3.49 percent of the frame.  A modest downward angle keeps
	// the near shore and enough moving water visible without returning to the old
	// -24 degree terrain-only composition.
	CameraPitch = -10.f;
	UpdateOrbitCamera();
	if (UCharacterMovementComponent* Movement = GetCharacterMovement())
	{
		Movement->StopMovementImmediately();
		Movement->SetMovementMode(MOVE_Flying);
	}

	UE_LOG(LogTemp, Display,
		TEXT("Shoreline visual test teleport: location=%s waterRadius=%.1fcm waterSigned=%.3fcm landSigned=%.3fcm cameraForward=%s pitch=%.1f"),
		*ShorelineLocation.ToCompactString(), WaterRadiusCm,
		MinimumSignedHeightCm, MaximumSignedHeightCm,
		*CameraForward.ToCompactString(), CameraPitch);
	if (GEngine)
	{
		GEngine->AddOnScreenDebugMessage(-1, 5.f, FColor::Cyan,
			TEXT("SHORELINE VISUAL TEST - F7 (camera held above fused sea datum)"));
	}
#endif
}

void ARedPlayerCharacter::OnRep_Skydiving()
{
	// Remote clients see the plume light up / go out as the pawn dives (authority drives it directly).
	SetPlumeActive(bSkydiving);
}

void ARedPlayerCharacter::SetPlumeActive(bool bOn)
{
	if (PlumeLight)
	{
		PlumeLight->SetLightColor(PlumeColor);
		PlumeLight->SetIntensity(PlumeLightIntensity);
		PlumeLight->SetAttenuationRadius(PlumeLightRadius);
		PlumeLight->SetVisibility(bOn);
	}
	if (PlumeSmoke)
	{
		if (bOn && PlumeSmokeFX)
		{
			if (PlumeSmoke->GetAsset() != PlumeSmokeFX) { PlumeSmoke->SetAsset(PlumeSmokeFX); }
			PlumeSmoke->SetRelativeScale3D(FVector(PlumeSmokeScale));
			PlumeSmoke->SetColorParameter(TEXT("Color"), PlumeColor);  // best-effort tint (may be ignored)
			PlumeSmoke->SetVisibility(true);
			PlumeSmoke->Activate(true);
		}
		else
		{
			PlumeSmoke->Deactivate();
			PlumeSmoke->SetVisibility(false);
		}
	}
}

void ARedPlayerCharacter::StartSkydive()
{
	if (bSkydiving) { return; }
	bSkydiving = true;
	// RED re-entry plume ON during the dive — a red glow + smoke trail BEHIND you (the cloning-facility
	// re-entry look). The point light is toned down (see PlumeLightIntensity) so it reads as a glow, not
	// the screen-wash it was before.
	SetPlumeActive(true);
	if (ARedOctosphereManager* Octo = ResolveOctosphere()) { Octo->SetDropInProgress(true); }
	if (GetWorld()) { GetWorld()->GetTimerManager().ClearTimer(SkydiveLandTimer); }  // cancel a pending land revert
	if (UCharacterMovementComponent* CMC = GetCharacterMovement())
	{
		SavedGravityScale = CMC->GravityScale;
		SavedAirControl = CMC->AirControl;
		CMC->GravityScale = SkydiveGravityScale;
		CMC->AirControl = SkydiveAirControl;
		CMC->SetMovementMode(MOVE_Falling);
	}
	// Play the dramatic full-body freefall (Mixamo, retargeted). Single-node overrides the ABP so
	// the whole body reads as a spread-eagle dive; the CMC still drives the capsule underneath.
	if (USkeletalMeshComponent* M = GetMesh(); M && IsUsingTrooperBody())
	{
		if (SkydiveFreefallAnim)
		{
			M->PlayAnimation(SkydiveFreefallAnim, true);  // looping single-node
		}
	}
}

void ARedPlayerCharacter::StopSkydive()
{
	if (!bSkydiving) { return; }
	// TOUCHDOWN: the ONLY slam fire site. StopSkydive is auto-called from Tick the frame the CMC flips
	// MOVE_Falling->MOVE_Walking, so this IS the landing. Gate on real drop speed so a hop doesn't slam.
	const float Impact = LastFallSpeed;
	LastFallSpeed = 0.f;
	if (!bIsEnemy && HasAuthority() && Impact >= SlamMinImpactSpeed)
	{
		DoLandingSlam(Impact);
	}
	bSkydiving = false;
	bOrbitalDropActive = false;   // end the controlled re-entry descent on touchdown
	bJetpackThrusting = false;
	CameraPitch = -12.f;   // reset the orbit camera to a normal ground angle (drop tilted it down)
	SetPlumeActive(false);   // RED plume off on landing
	if (ARedOctosphereManager* Octo = ResolveOctosphere()) { Octo->SetDropInProgress(false); }
	if (UCharacterMovementComponent* CMC = GetCharacterMovement())
	{
		CMC->GravityScale = SavedGravityScale;
		CMC->AirControl = SavedAirControl;
	}
	// Touchdown: play the Mixamo landing clip once (single-node override), then hand the body back
	// to the AnimBlueprint when it finishes. If the land clip is missing, revert immediately.
	if (USkeletalMeshComponent* M = GetMesh(); M && IsUsingTrooperBody())
	{
		if (IsUsingTrooperBody() && SkydiveLandAnim && GetWorld())
		{
			M->PlayAnimation(SkydiveLandAnim, false);  // one-shot
			GetWorld()->GetTimerManager().SetTimer(SkydiveLandTimer, this,
				&ARedPlayerCharacter::FinishSkydiveLand, SkydiveLandAnim->GetPlayLength(), false);
		}
		else
		{
			M->SetAnimationMode(EAnimationMode::AnimationBlueprint);
		}
	}
}

void ARedPlayerCharacter::FinishSkydiveLand()
{
	// Land clip finished (or was interrupted by a new dive) — resume normal locomotion, unless a new
	// dive already took over the mesh (bSkydiving guards against clobbering the freefall pose).
	if (bSkydiving) { return; }
	if (USkeletalMeshComponent* M = GetMesh())
	{
		M->SetAnimationMode(EAnimationMode::AnimationBlueprint);
		if (IsUsingTrooperBody() && TrooperAnimClass && M->GetAnimClass() != TrooperAnimClass)
		{
			M->SetAnimInstanceClass(TrooperAnimClass);
		}
	}
}

void ARedPlayerCharacter::DoLandingSlam(float ImpactSpeed)
{
	UWorld* World = GetWorld();
	if (!World) { return; }

	// Strength 0..1 across [SlamMinImpactSpeed .. terminal].
	const float SpeedSpan = FMath::Max(SkydiveMaxFallSpeed - SlamMinImpactSpeed, 1.f);
	const float Strength01 = FMath::Clamp((ImpactSpeed - SlamMinImpactSpeed) / SpeedSpan, 0.f, 1.f);

	// Find the ground point + normal under the feet (radial "up" as fallback).
	const FVector Up = RedGravity::UpAt(World, GetActorLocation(), GetActorUpVector());
	const float HalfH = GetCapsuleComponent() ? GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 90.f;
	FVector GroundPoint = GetActorLocation() - Up * HalfH;
	FVector GroundUp = Up;
	{
		FHitResult GroundHit;
		FCollisionQueryParams GP(SCENE_QUERY_STAT(DropSlam), false, this);
		if (World->LineTraceSingleByChannel(GroundHit, GetActorLocation() + Up * 200.f, GetActorLocation() - Up * 4000.f, ECC_Visibility, GP))
		{
			GroundPoint = GroundHit.ImpactPoint;
			GroundUp = GroundHit.ImpactNormal.GetSafeNormal();
		}
	}

	// Landing shield: brief invuln so the fall + your own slam don't kill you.
	bLandingInvuln = true;
	World->GetTimerManager().SetTimer(LandingInvulnTimer, this, &ARedPlayerCharacter::EndLandingInvuln, SlamInvulnDuration, false);

	// Radial AoE damage (server), diver excluded.
	const float Damage = SlamBaseDamage * FMath::Lerp(0.4f, 1.f, Strength01);
	TArray<AActor*> IgnoreActors;
	IgnoreActors.Add(this);
	UGameplayStatics::ApplyRadialDamageWithFalloff(World, Damage, Damage * SlamMinDamageFrac, GroundPoint,
		SlamInnerRadius, SlamOuterRadius, 1.f,
		SlamDamageType ? SlamDamageType : TSubclassOf<UDamageType>(UDamageType::StaticClass()),
		IgnoreActors, this, GetController(), ECC_Visibility);

	// Radial knockback (launch nearby pawns up-and-out).
	TArray<AActor*> Pawns;
	UGameplayStatics::GetAllActorsOfClass(World, ARedPlayerCharacter::StaticClass(), Pawns);
	for (AActor* A : Pawns)
	{
		ARedPlayerCharacter* RC = Cast<ARedPlayerCharacter>(A);
		if (!RC || RC == this || RC->IsDowned()) { continue; }
		if (!bSlamFriendlyFire && !RC->bIsEnemy) { continue; }
		const FVector To = RC->GetActorLocation() - GroundPoint;
		const float Dist = To.Size();
		if (Dist > SlamOuterRadius) { continue; }
		const float Falloff = 1.f - Dist / SlamOuterRadius;
		const FVector Dir = (To.GetSafeNormal() + GroundUp * 0.6f).GetSafeNormal();
		const float Power = SlamKnockback * FMath::Lerp(0.5f, 1.f, Strength01) * Falloff;
		RC->LaunchCharacter(Dir * Power, true, true);
	}

	// One multicast drives the FX on host + all clients (and standalone) exactly once.
	MulticastSlamFX(GroundPoint, GroundUp, Strength01);
}

void ARedPlayerCharacter::MulticastSlamFX_Implementation(FVector Center, FVector GroundUp, float Strength01)
{
	PlaySlamFX_Local(Center, GroundUp, Strength01);
}

void ARedPlayerCharacter::PlaySlamFX_Local(const FVector& Center, const FVector& GroundUp, float Strength01)
{
	UWorld* World = GetWorld();
	if (!World) { return; }
	const FVector SafeGroundUp = GroundUp.GetSafeNormal().IsNearlyZero() ? GetActorUpVector() : GroundUp.GetSafeNormal();
	// Sand FX ground systems are authored Z-up. GroundUp.Rotation() points local X along the normal,
	// which turns the burst sideways/into the terrain on a spherical planet.
	const FRotator GroundRot = FRotationMatrix::MakeFromZ(SafeGroundUp).Rotator();
	const float Scale = SlamFXScale * FMath::Lerp(0.7f, 1.f, Strength01);
	PlaySlamImpactPose();

	if (SlamExplosionFX)
	{
		UNiagaraFunctionLibrary::SpawnSystemAtLocation(World, SlamExplosionFX,
			Center + SafeGroundUp * 8.f, GroundRot, FVector(Scale), true, true, ENCPoolMethod::AutoRelease);
	}
	if (SlamDebrisFX)
	{
		UNiagaraFunctionLibrary::SpawnSystemAtLocation(World, SlamDebrisFX,
			Center + SafeGroundUp * 5.f, GroundRot, FVector(FMath::Lerp(0.75f, 1.15f, Strength01)),
			true, true, ENCPoolMethod::AutoRelease);
	}
	if (SlamGroundCrackMesh)
	{
		FActorSpawnParameters CrackParams;
		CrackParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		CrackParams.ObjectFlags |= RF_Transient;
		if (AStaticMeshActor* Crack = World->SpawnActor<AStaticMeshActor>(
			AStaticMeshActor::StaticClass(), Center + SafeGroundUp * 2.5f, GroundRot, CrackParams))
		{
			UStaticMeshComponent* CrackComponent = Crack->GetStaticMeshComponent();
			CrackComponent->SetMobility(EComponentMobility::Movable);
			CrackComponent->SetStaticMesh(SlamGroundCrackMesh);
			if (SlamGroundCrackMaterial)
			{
				CrackComponent->SetMaterial(0, SlamGroundCrackMaterial);
			}
			CrackComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			CrackComponent->SetGenerateOverlapEvents(false);
			CrackComponent->SetCastShadow(false);
			CrackComponent->SetReceivesDecals(false);
			const float SourceDiameter = FMath::Max(1.f, SlamGroundCrackMesh->GetBounds().BoxExtent.GetMax() * 2.f);
			const float DesiredDiameter = SlamOuterRadius * 2.f * FMath::Lerp(0.65f, 1.f, Strength01);
			Crack->SetActorScale3D(FVector(DesiredDiameter / SourceDiameter));
			Crack->SetReplicates(false);
			Crack->SetLifeSpan(12.f);
		}
	}
	if (SlamCraterDecalMaterial)
	{
		const float R = SlamOuterRadius * FMath::Lerp(0.6f, 1.f, Strength01);
		const float Depth = FMath::Clamp(R * 0.28f, 48.f, 520.f);
		if (UDecalComponent* Dec = UGameplayStatics::SpawnDecalAtLocation(World, SlamCraterDecalMaterial,
			FVector(Depth, R, R), Center + SafeGroundUp * 8.f, GroundRot, 12.f))
		{
			Dec->SetFadeOut(8.f, 4.f, false);
		}
	}
	// Guaranteed-red flash: a transient point light on a throwaway actor (Metal-safe, no asset).
	if (AActor* LightHost = World->SpawnActor<AActor>(AActor::StaticClass(), Center + SafeGroundUp * 60.f, GroundRot))
	{
		UPointLightComponent* Flash = NewObject<UPointLightComponent>(LightHost);
		LightHost->SetRootComponent(Flash);
		Flash->RegisterComponent();
		Flash->SetMobility(EComponentMobility::Movable);
		Flash->SetLightColor(SlamLightColor);
		Flash->SetIntensity(SlamLightIntensity * FMath::Lerp(0.6f, 1.f, Strength01));
		Flash->SetAttenuationRadius(SlamLightRadius);
		Flash->SetCastShadows(false);
		LightHost->SetLifeSpan(SlamLightLifetime);
	}
	if (SlamCameraShake)
	{
		UGameplayStatics::PlayWorldCameraShake(World, SlamCameraShake, Center, SlamShakeInnerRadius, SlamShakeOuterRadius, 1.f, false);
	}
}

void ARedPlayerCharacter::Skydive()
{
	// Already airborne? Dive right here (don't yank the player back to the deck). Otherwise board
	// the station and arm — the dive starts when they step off the edge.
	if (UCharacterMovementComponent* CMC = GetCharacterMovement())
	{
		if (CMC->MovementMode == MOVE_Falling && !bSkydiving)
		{
			StartSkydive();
			if (GEngine) { GEngine->AddOnScreenDebugMessage(-1, 3.f, FColor::Cyan, TEXT("THE DROP - diving! steer with WASD")); }
			return;
		}
	}
	if (!BoardStationAndDrop(true))
	{
		StartSkydive();   // no station (flat arena test): dive in place
	}
}

void ARedPlayerCharacter::BoltColor(float R, float G, float B)
{
	RifleBoltColor = FLinearColor(R, G, B);
	if (GEngine)
	{
		GEngine->AddOnScreenDebugMessage(-1, 3.f, FColor::White,
			FString::Printf(TEXT("BoltColor %.1f %.1f %.1f"), R, G, B));
	}
}

void ARedPlayerCharacter::BoltSize(float LengthMeters, float ThicknessMeters)
{
	RifleBoltLength = LengthMeters;
	RifleBoltRadius = ThicknessMeters;
	if (GEngine)
	{
		GEngine->AddOnScreenDebugMessage(-1, 3.f, FColor::White,
			FString::Printf(TEXT("BoltSize %.2fm x %.2fm"), LengthMeters, ThicknessMeters));
	}
}

void ARedPlayerCharacter::FireAtTarget(AActor* Target)
{
	EnsureWeaponSlotState();
	const int32 FireSlot = FMath::Clamp(CurrentWeaponSlot, 0, 1);
	if (!HasAuthority() || !Target || !ProjectileClass || !GetWorld()
		|| IsWeaponSlotOverheated(FireSlot) || WeaponSlotHeat[FireSlot] >= MaxWeaponHeat)
	{
		return;
	}
	if (bHolstered) { bHolstered = false; ApplyHolsterState(); }  // draw if stowed
	LastFireTime = GetWorld()->GetTimeSeconds();
	const FVector MuzzleLoc = GetMuzzleWorldLocation();
	const FVector TargetLoc = Target->GetActorLocation() + FMath::VRand() * EnemyAimSpread;
	const FVector ToTarget = (TargetLoc - MuzzleLoc).GetSafeNormal();
	ReplicatedAimDirection = ToTarget;
	WeaponSlotHeat[FireSlot] = FMath::Min(
		MaxWeaponHeat, WeaponSlotHeat[FireSlot] + WeaponHeatPerShot);
	WeaponSlotOverheated[FireSlot] = WeaponSlotHeat[FireSlot] >= MaxWeaponHeat ? 1 : 0;
	MulticastFireCosmetics(MuzzleLoc, ToTarget, 0, 1);
	const FVector Start = MuzzleLoc + ToTarget * 40.f;
	const TSubclassOf<AActor> Cls = EnemyProjectileClass ? EnemyProjectileClass : ProjectileClass;
	if (Cls)
	{
		FActorSpawnParameters Params;
		Params.Owner = this;
		Params.Instigator = this;
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		if (AActor* Proj = GetWorld()->SpawnActor<AActor>(Cls, Start, ToTarget.Rotation(), Params))
		{
			if (ARedBolt* EnemyBolt = Cast<ARedBolt>(Proj))
			{
				float DamageForShot = EnemyFireDamage;
				if (FMath::FRand() <= EnemyCritChance)
				{
					DamageForShot = FMath::FRandRange(20.f, 30.f);
				}
				EnemyBolt->ConfigureImpactProfile(1.2f, 1.0f, 0.f, DamageForShot);
				EnemyBolt->ConfigureGroundImpact(false, false, false);
				EnemyBolt->SetEffectProfile(2);
				EnemyBolt->SetBeamColor(FLinearColor(1.0f, 0.14f, 0.08f));  // enemy fire = red
				EnemyBolt->SetBeamDimensions(RifleBoltLength, RifleBoltRadius);
				EnemyBolt->LaunchWithVelocity(ToTarget * 9000.f + GetVelocity() * 0.35f);
			}
		}
	}
	// Hitscan with a hit chance so a few shooters don't melt the player instantly.
	// Most hits ~10 (1 shield pip); occasional crits 20–30 for longer fights.
}

void ARedPlayerCharacter::SpawnEnemyWave(int32 Count, float RingRadius)
{
	UWorld* W = GetWorld();
	if (!W || Count <= 0)
	{
		return;
	}
	const FVector MyLoc = GetActorLocation();
	// Radial frame around the DOMINANT gravity body (works on the planet AND on moons). If there is
	// NO body (flat arena / deep space), fall back to a flat ring around the actor — never a sphere
	// around the world origin.
	FVector BodyCenter = FVector::ZeroVector;
	float BodySurfaceRadius = -1.f;
	const bool bHasBody = RedGravity::QueryDominantBody(W, MyLoc, BodyCenter, BodySurfaceRadius);
	const FVector Up = bHasBody ? (MyLoc - BodyCenter).GetSafeNormal() : GetActorUpVector();
	FVector Tangent = FVector::CrossProduct(Up, FVector::ForwardVector).GetSafeNormal();
	if (Tangent.IsNearlyZero())
	{
		Tangent = FVector::CrossProduct(Up, FVector::RightVector).GetSafeNormal();
	}
	const FVector BiTangent = FVector::CrossProduct(Up, Tangent).GetSafeNormal();
	const float SurfRadius = (float)(MyLoc - BodyCenter).Size();
	const float Ring = RingRadius > 0.f ? RingRadius : 30000.f;
	for (int32 i = 0; i < Count; ++i)
	{
		const float Ang = (2.f * PI * i) / FMath::Max(1, Count);
		const FVector Dir = (Tangent * FMath::Cos(Ang) + BiTangent * FMath::Sin(Ang)).GetSafeNormal();
		// Step out along the tangent; on a body, re-project onto its sphere; flat -> straight ring.
		const FVector SpawnUp = bHasBody ? ((MyLoc + Dir * Ring) - BodyCenter).GetSafeNormal() : Up;
		// Place the spawn on ACTUAL floor. Walk inward from the ring toward the player and
		// down-trace at each step; first floor hit wins. On the flat test map the 120m ring
		// lands past the floor edge (bots were falling to the kill-Z, z<-70000), so pulling
		// inward guarantees they land on the floor near the player; on the real 8km map the
		// ring itself hits on the first iteration and nothing changes.
		FVector OutLoc = MyLoc + Dir * Ring + SpawnUp * 400.f;
		{
			FCollisionQueryParams GParams;
			GParams.AddIgnoredActor(this);
			FCollisionObjectQueryParams GroundObjectTypes;
			GroundObjectTypes.AddObjectTypesToQuery(ECC_WorldStatic);
			GroundObjectTypes.AddObjectTypesToQuery(ECC_WorldDynamic);
			bool bFound = false;
			for (float R = Ring; R >= 800.f && !bFound; R *= 0.6f)
			{
				const FVector Probe = bHasBody
					? BodyCenter + ((MyLoc + Dir * R) - BodyCenter).GetSafeNormal() * (SurfRadius + 400.f)
					: MyLoc + Dir * R + SpawnUp * 400.f;
				FHitResult GroundHit;
				if (W->LineTraceSingleByObjectType(GroundHit, Probe + SpawnUp * 3000.f,
					Probe - SpawnUp * 30000.f, GroundObjectTypes, GParams))
				{
					OutLoc = GroundHit.ImpactPoint + SpawnUp * 100.f;
					bFound = true;
				}
			}
			if (!bFound)
			{
				OutLoc = MyLoc + SpawnUp * 100.f;   // last resort: on the player's own floor
			}
		}
		const FRotator SpawnRot = FRotationMatrix::MakeFromXZ(-Dir, SpawnUp).Rotator();
		FActorSpawnParameters P;
		P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		ARedPlayerCharacter* Enemy = W->SpawnActor<ARedPlayerCharacter>(GetClass(), OutLoc, SpawnRot, P);
		if (Enemy)
		{
			Enemy->bIsEnemy = true;
			Enemy->ForceNetUpdate();
			if (ARedBotController* Bot = W->SpawnActor<ARedBotController>(ARedBotController::StaticClass()))
			{
				Bot->Possess(Enemy);
			}
		}
	}
	UE_LOG(LogRedPlayerCharacter, Display, TEXT("[RedFight] spawned %d enemy clones %.0fm out"), Count, Ring / 100.f);
}

void ARedPlayerCharacter::StressBots(int32 N, float SpreadRadius)
{
	UWorld* W = GetWorld();
	if (!W || N <= 0) { return; }
	const FVector MyLoc = GetActorLocation();
	FVector BodyCenter = FVector::ZeroVector; float BodyRad = -1.f;
	const bool bHasBody = RedGravity::QueryDominantBody(W, MyLoc, BodyCenter, BodyRad);
	const FVector Up = bHasBody ? (MyLoc - BodyCenter).GetSafeNormal() : GetActorUpVector();
	FVector Tangent = FVector::CrossProduct(Up, FVector::ForwardVector).GetSafeNormal();
	if (Tangent.IsNearlyZero()) { Tangent = FVector::CrossProduct(Up, FVector::RightVector).GetSafeNormal(); }
	const FVector BiTangent = FVector::CrossProduct(Up, Tangent).GetSafeNormal();
	const float Spread = SpreadRadius > 0.f ? SpreadRadius : 200000.f;

	int32 Spawned = 0;
	for (int32 i = 0; i < N; ++i)
	{
		const float Ang = FMath::FRandRange(0.f, 2.f * PI);
		const float Rad = FMath::Sqrt(FMath::FRand()) * Spread;   // uniform over the disc, not clustered at center
		const FVector Dir = (Tangent * FMath::Cos(Ang) + BiTangent * FMath::Sin(Ang)).GetSafeNormal();
		const FVector Base = MyLoc + Dir * Rad;
		// Down-trace to floor if the cell is loaded; else spawn a little high and let the bot's own
		// streaming source load its cell + gravity settle it.
		FVector OutLoc = Base + Up * 500.f;
		FCollisionQueryParams GP; GP.AddIgnoredActor(this);
		FHitResult GH;
		if (W->LineTraceSingleByChannel(GH, Base + Up * 20000.f, Base - Up * 40000.f, ECC_WorldStatic, GP))
		{
			OutLoc = GH.ImpactPoint + Up * 120.f;
		}
		FActorSpawnParameters P;
		P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		ARedPlayerCharacter* Bot = W->SpawnActor<ARedPlayerCharacter>(GetClass(),
			OutLoc, FRotationMatrix::MakeFromXZ(Tangent, Up).Rotator(), P);
		if (!Bot) { continue; }
		Bot->bIsEnemy = true;
		Bot->ForceNetUpdate();
		// Each bot is its own WP streaming source so its region stays loaded out here (the realistic
		// MMO load: N spread players = N loaded regions). Without this a distant bot falls through
		// unloaded terrain.
		if (UWorldPartitionStreamingSourceComponent* SS = NewObject<UWorldPartitionStreamingSourceComponent>(Bot))
		{
			SS->RegisterComponent();
			SS->EnableStreamingSource();
		}
		if (ARedBotController* BC = W->SpawnActor<ARedBotController>(ARedBotController::StaticClass()))
		{
			BC->bWander = true;
			BC->Possess(Bot);
		}
		++Spawned;
	}
	if (GEngine)
	{
		GEngine->AddOnScreenDebugMessage(-1, 6.f, FColor::Orange,
			FString::Printf(TEXT("StressBots: %d/%d wandering streaming-source bots over %.0fm (watch: stat unit)"), Spawned, N, Spread / 100.f));
	}
	UE_LOG(LogRedPlayerCharacter, Display, TEXT("[Stress] spawned %d/%d wander bots, spread %.0fcm"), Spawned, N, Spread);
}

void ARedPlayerCharacter::RedSpawnEnemies(int32 Count)
{
	SpawnEnemyWave(Count > 0 ? Count : 3);
}

void ARedPlayerCharacter::OnSpawnEnemiesKey()
{
	SpawnEnemyWave(3);
}

void ARedPlayerCharacter::OnAutoSpawnWave()
{
	// Fires on every pawn's BeginPlay timer — only the real, server-side player spawns the patrol
	// (enemy clones have bIsEnemy set by now; bots are not player-controlled).
	if (bIsEnemy || !HasAuthority() || !IsPlayerControlled())
	{
		return;
	}
	SpawnEnemyWave(3, 12000.f);   // 120 m out: rim blips immediately, contact in under a minute
}

void ARedPlayerCharacter::StartADS()
{
	// Right-mouse = FIRE GRAPPLE, no aim-zoom. If nothing's in grapple range the click just does nothing
	// (it will NOT zoom). ADS was removed from RMB per the "just grapple, don't zoom" request.
	TryGrapple();
}

void ARedPlayerCharacter::StopADS()
{
	// Release right-mouse → let go of the grapple with an arc-off boost.
	StopGrappleInput();
	bADS = false;
}

void ARedPlayerCharacter::ToggleHolster()
{
	if (!WeaponMesh || !GetMesh()) { return; }
	bHolstered = !bHolstered;
	ApplyHolsterState();
	if (HasAuthority())
	{
		ForceNetUpdate();
	}
	else
	{
		ServerSetHolstered(bHolstered);
	}
}

void ARedPlayerCharacter::ApplyHolsterState()
{
	if (!WeaponMesh || !GetMesh()) { return; }
	if (bHolstered)
	{
		WeaponMesh->SetUsingAbsoluteRotation(false);
		WeaponMesh->AttachToComponent(GetMesh(), FAttachmentTransformRules::SnapToTargetNotIncludingScale, HolsterSocket);
		WeaponMesh->SetRelativeLocationAndRotation(HolsterLocation, HolsterRotation);
	}
	else
	{
		AttachWeaponToHand();
	}
}

void ARedPlayerCharacter::OnRep_Holstered()
{
	ApplyHolsterState();
}

void ARedPlayerCharacter::ServerSetHolstered_Implementation(bool bNewHolstered)
{
	if (bDowned) { return; }
	bHolstered = bNewHolstered;
	if (bHolstered)
	{
		bReplicatedAimHeld = false;
	}
	ApplyHolsterState();
	ForceNetUpdate();
}

void ARedPlayerCharacter::AttachWeaponToHand()
{
	if (!WeaponMesh || !GetMesh()) { return; }
	static const FName TrooperGrip(TEXT("hand_rSocket"));
	static const FName HandR(TEXT("hand_r"));
	FName AttachSocket = NAME_None;
	bool bAuthored = false;
	if (GetMesh()->DoesSocketExist(TrooperGrip))
	{
		AttachSocket = TrooperGrip;
		bAuthored = true;
	}
	else if (GetMesh()->DoesSocketExist(WeaponSocket))
	{
		AttachSocket = WeaponSocket;
		bAuthored = true;
	}
	else if (GetMesh()->DoesSocketExist(HandR))
	{
		AttachSocket = HandR;
	}
	WeaponMesh->SetUsingAbsoluteRotation(false);
	WeaponMesh->AttachToComponent(GetMesh(), FAttachmentTransformRules::SnapToTargetNotIncludingScale, AttachSocket);
	if (bAuthored)
	{
		WeaponMesh->SetRelativeLocationAndRotation(FVector::ZeroVector, FRotator::ZeroRotator);
	}
	else if (AttachSocket != NAME_None)
	{
		WeaponMesh->SetRelativeLocation(FVector(8.0f, 3.0f, -2.0f));
		WeaponMesh->SetRelativeRotation(FRotator(0.0f, 85.0f, -6.0f));
	}
}
