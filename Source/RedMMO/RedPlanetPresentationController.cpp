#include "RedPlanetPresentationController.h"

#include "Camera/PlayerCameraManager.h"
#include "Components/PrimitiveComponent.h"
#include "Components/SkyAtmosphereComponent.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInterface.h"

DEFINE_LOG_CATEGORY_STATIC(LogRedPlanetPresentation, Log, All);

namespace
{
constexpr float RedMinUsefulSurfaceRadius = 1000.0f;
constexpr float RedMvpGameplaySurfaceRadius = 382000.0f;
constexpr float RedMvpNearVoxelDetailAltitude = 900000.0f;
constexpr float RedMvpFarProxyOnlyAltitude = 3500000.0f;
constexpr float RedMvpHysteresisAltitude = 800000.0f;
constexpr float RedMvpOrbitBackdropAltitude = 10000000.0f;
constexpr float RedMvpSurfaceSkyAltitude = 14000000.0f;

void NormalizePlanetScale(ARedPlanetPresentationController& Controller)
{
	Controller.PlanetRadius = RedMvpGameplaySurfaceRadius;
	Controller.NearVoxelDetailAltitude = FMath::Max(Controller.NearVoxelDetailAltitude, RedMvpNearVoxelDetailAltitude);
	Controller.FarProxyOnlyAltitude = FMath::Max(Controller.FarProxyOnlyAltitude, RedMvpFarProxyOnlyAltitude);
	Controller.HysteresisAltitude = FMath::Max(Controller.HysteresisAltitude, RedMvpHysteresisAltitude);
	Controller.OrbitBackdropVisibleAltitude = FMath::Max(Controller.OrbitBackdropVisibleAltitude, RedMvpOrbitBackdropAltitude);
	Controller.SurfaceSkyVisibleAltitude = FMath::Max(Controller.SurfaceSkyVisibleAltitude, RedMvpSurfaceSkyAltitude);
	Controller.bUseVisualBoundsForGameplaySurface = false;
	Controller.bShowGameplaySurfaceVisual = false;
}

bool IsGeneratedPresentationShellName(const FString& ActorName)
{
	return ActorName.Contains(TEXT("Vibe_HorizonHazeShell")) ||
		ActorName.Contains(TEXT("Vibe_PlanetOrbitProxy")) ||
		ActorName.Contains(TEXT("Vibe_OrbitStarfield")) ||
		ActorName.Contains(TEXT("Vibe_PlanetAtmosphereRim")) ||
		ActorName.Contains(TEXT("Vibe_PlanetCloudBands")) ||
		ActorName.Contains(TEXT("Vibe_CleanStylizedSky")) ||
		ActorName.Contains(TEXT("Vibe_PlanetSkyAtmosphere")) ||
		ActorName.Contains(TEXT("Vibe_PlanetVolumetricClouds")) ||
		ActorName.Contains(TEXT("BP_StylizedSky_Lite")) ||
		ActorName.Contains(TEXT("StylizedSky")) ||
		ActorName.Contains(TEXT("SkyDome"));
}

void DisablePresentationShellCollision(AActor* Actor)
{
	if (!IsValid(Actor))
	{
		return;
	}

	TArray<UPrimitiveComponent*> Primitives;
	Actor->GetComponents<UPrimitiveComponent>(Primitives);
	for (UPrimitiveComponent* Primitive : Primitives)
	{
		if (!Primitive)
		{
			continue;
		}

		Primitive->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Primitive->SetCollisionResponseToAllChannels(ECR_Ignore);
		Primitive->CanCharacterStepUpOn = ECB_No;
	}
}
}

ARedPlanetPresentationController::ARedPlanetPresentationController()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = true;

	GameplaySurfaceCollider = CreateDefaultSubobject<USphereComponent>(TEXT("GameplaySurfaceCollider"));
	SetRootComponent(GameplaySurfaceCollider);
	GameplaySurfaceCollider->SetCollisionObjectType(ECC_WorldStatic);
	GameplaySurfaceCollider->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	GameplaySurfaceCollider->SetCollisionResponseToAllChannels(ECR_Ignore);
	GameplaySurfaceCollider->SetGenerateOverlapEvents(false);
	GameplaySurfaceCollider->SetCanEverAffectNavigation(false);
	GameplaySurfaceCollider->CanCharacterStepUpOn = ECB_No;
	GameplaySurfaceCollider->SetHiddenInGame(true);
	GameplaySurfaceCollider->SetVisibility(false, true);

	GameplaySurfaceVisual = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("GameplaySurfaceVisual"));
	GameplaySurfaceVisual->SetupAttachment(GameplaySurfaceCollider);
	GameplaySurfaceVisual->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	GameplaySurfaceVisual->SetCollisionResponseToAllChannels(ECR_Ignore);
	GameplaySurfaceVisual->SetGenerateOverlapEvents(false);
	GameplaySurfaceVisual->SetCanEverAffectNavigation(false);
	GameplaySurfaceVisual->SetCastShadow(false);
	if (UStaticMesh* SphereMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere")))
	{
		GameplaySurfaceVisual->SetStaticMesh(SphereMesh);
	}

	NormalizePlanetScale(*this);
	GameplaySurfaceCollider->SetSphereRadius(GetGameplaySurfaceRadius(), false);
}

void ARedPlanetPresentationController::BeginPlay()
{
	Super::BeginPlay();
	NormalizePlanetScale(*this);
	RefreshPresentationActors();
	RefreshGameplaySurfaceCollider();
	RefreshGameplaySurfaceVisual();
}

void ARedPlanetPresentationController::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	NormalizePlanetScale(*this);
	RefreshPresentationActors();
	RefreshGameplaySurfaceCollider();
	RefreshGameplaySurfaceVisual();
}

bool ARedPlanetPresentationController::ShouldTickIfViewportsOnly() const
{
	// NEVER tick in the editor viewport. The per-tick presentation refresh leaks memory
	// unboundedly while the map is merely OPEN (linear ~0.1 GB/s -> 185 GB editor lock-up on
	// Map_MoonI). The altitude-driven presentation switch only needs to run during play, where
	// the actor ticks regardless of this flag, so runtime behaviour (surface-sky <-> orbit
	// starfield transition) is unaffected.
	return false;
}

void ARedPlanetPresentationController::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (OrbitProxyActors.Num() == 0 || VoxelDetailActors.Num() == 0)
	{
		RefreshPresentationActors();
	}
	RefreshGameplaySurfaceCollider();
	RefreshGameplaySurfaceVisual();

	FVector ViewLocation = FVector::ZeroVector;
	if (!ResolveViewLocation(ViewLocation))
	{
		return;
	}

	LastAltitude = FMath::Max(0.0f, static_cast<float>((ViewLocation - PlanetCenter).Size() - GetGameplaySurfaceRadius()));

	bool bDesiredFarProxy = bUsingFarProxy;
	if (LastAltitude >= FarProxyOnlyAltitude + HysteresisAltitude)
	{
		bDesiredFarProxy = true;
	}
	else if (LastAltitude <= NearVoxelDetailAltitude - HysteresisAltitude)
	{
		bDesiredFarProxy = false;
	}

	if (bDesiredFarProxy != bUsingFarProxy)
	{
		UE_LOG(LogRedPlanetPresentation, Display,
			TEXT("Planet presentation switched to %s at %.0f cm AGL"),
			bDesiredFarProxy ? TEXT("orbit proxy") : TEXT("voxel detail"),
			LastAltitude);
	}

	ApplyPresentationState(bDesiredFarProxy);
}

void ARedPlanetPresentationController::RefreshPresentationActors()
{
	OrbitProxyActors.Reset();
	VoxelDetailActors.Reset();
	SurfaceSkyActors.Reset();
	OrbitBackdropActors.Reset();
	CalibratedVisualSurfaceRadius = 0.0f;

	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}

	for (TActorIterator<AActor> It(World); It; ++It)
	{
		AActor* Actor = *It;
		if (!IsValid(Actor) || Actor == this)
		{
			continue;
		}

		if (Actor->Tags.Contains(OrbitProxyTag))
		{
			OrbitProxyActors.Add(Actor);
		}
		if (Actor->Tags.Contains(SurfaceSkyTag))
		{
			SurfaceSkyActors.Add(Actor);
		}
		if (Actor->Tags.Contains(OrbitBackdropTag))
		{
			OrbitBackdropActors.Add(Actor);
		}

		FString ActorName = Actor->GetName();
#if WITH_EDITOR
		ActorName += TEXT(" ");
		ActorName += Actor->GetActorLabel();
#endif
		const FString ClassName = Actor->GetClass() ? Actor->GetClass()->GetName() : FString();
		const bool bLooksLikeOrbitProxy =
			ActorName.Contains(TEXT("Vibe_PlanetOrbitProxy")) ||
			ClassName.Contains(TEXT("PlanetOrbitProxy"));
		const bool bGeneratedPresentationShell = IsGeneratedPresentationShellName(ActorName);
		const bool bHasExplicitVoxelDetailTag = Actor->Tags.Contains(VoxelDetailTag);
		const bool bLooksLikeVoxelDetail =
			!bGeneratedPresentationShell &&
			(ActorName.Contains(TEXT("VoxelWorld")) ||
				ClassName.Contains(TEXT("VoxelWorld")) ||
				ActorName.Contains(TEXT("VibeVoxel")) ||
				ActorName.Contains(TEXT("Vibe_Voxel")) ||
				ClassName.Contains(TEXT("Voxel")) ||
				(bHasExplicitVoxelDetailTag && (ActorName.Contains(TEXT("Voxel")) || ClassName.Contains(TEXT("Voxel")))));
		const bool bLooksLikeSurfaceSky =
			ActorName.Contains(TEXT("BP_StylizedSky_Lite")) ||
			ActorName.Contains(TEXT("StylizedSky"));
		const bool bLooksLikeOrbitBackdrop =
			ActorName.Contains(TEXT("Vibe_OrbitStarfield")) ||
			ActorName.Contains(TEXT("OrbitStarfield"));

		if (bGeneratedPresentationShell)
		{
			DisablePresentationShellCollision(Actor);
		}

		if (bLooksLikeOrbitProxy && !OrbitProxyActors.Contains(Actor))
		{
			OrbitProxyActors.Add(Actor);
		}

		if (bLooksLikeVoxelDetail && !VoxelDetailActors.Contains(Actor))
		{
			VoxelDetailActors.Add(Actor);
			FVector BoundsOrigin = FVector::ZeroVector;
			FVector BoundsExtent = FVector::ZeroVector;
			Actor->GetActorBounds(false, BoundsOrigin, BoundsExtent);
			const FVector LocalOrigin = BoundsOrigin - PlanetCenter;
			const float BoundsRadius = FMath::Max3(
				FMath::Abs(static_cast<float>(LocalOrigin.X)) + static_cast<float>(BoundsExtent.X),
				FMath::Abs(static_cast<float>(LocalOrigin.Y)) + static_cast<float>(BoundsExtent.Y),
				FMath::Abs(static_cast<float>(LocalOrigin.Z)) + static_cast<float>(BoundsExtent.Z));
			if (BoundsRadius > RedMinUsefulSurfaceRadius)
			{
				CalibratedVisualSurfaceRadius = FMath::Max(CalibratedVisualSurfaceRadius, BoundsRadius);
			}
		}
		if (bLooksLikeSurfaceSky && !SurfaceSkyActors.Contains(Actor))
		{
			SurfaceSkyActors.Add(Actor);
		}
		if (bLooksLikeOrbitBackdrop && !OrbitBackdropActors.Contains(Actor))
		{
			OrbitBackdropActors.Add(Actor);
		}
	}

	ApplyPresentationState(bUsingFarProxy);
	ApplySkyPresentationState();

	UE_LOG(LogRedPlanetPresentation, Display,
		TEXT("Planet presentation scan: %d orbit proxy actor(s), %d voxel detail actor(s), %d surface sky actor(s), %d orbit backdrop actor(s), visual radius %.0f cm"),
		OrbitProxyActors.Num(),
		VoxelDetailActors.Num(),
		SurfaceSkyActors.Num(),
		OrbitBackdropActors.Num(),
		CalibratedVisualSurfaceRadius);
}

USphereComponent* ARedPlanetPresentationController::EnsureGameplaySurfaceCollider()
{
	if (GameplaySurfaceCollider)
	{
		return GameplaySurfaceCollider;
	}

	GameplaySurfaceCollider = NewObject<USphereComponent>(this, TEXT("GameplaySurfaceCollider"));
	if (!GameplaySurfaceCollider)
	{
		return nullptr;
	}

	GameplaySurfaceCollider->SetCollisionObjectType(ECC_WorldStatic);
	GameplaySurfaceCollider->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	GameplaySurfaceCollider->SetCollisionResponseToAllChannels(ECR_Ignore);
	GameplaySurfaceCollider->SetGenerateOverlapEvents(false);
	GameplaySurfaceCollider->SetCanEverAffectNavigation(false);
	GameplaySurfaceCollider->CanCharacterStepUpOn = ECB_No;
	GameplaySurfaceCollider->SetHiddenInGame(true);
	GameplaySurfaceCollider->SetVisibility(false, true);

	if (!RootComponent)
	{
		SetRootComponent(GameplaySurfaceCollider);
	}
	else
	{
		GameplaySurfaceCollider->AttachToComponent(RootComponent, FAttachmentTransformRules::KeepWorldTransform);
	}

	AddInstanceComponent(GameplaySurfaceCollider);
	GameplaySurfaceCollider->RegisterComponent();
	return GameplaySurfaceCollider;
}

void ARedPlanetPresentationController::RefreshGameplaySurfaceCollider()
{
	USphereComponent* SurfaceCollider = EnsureGameplaySurfaceCollider();
	if (!SurfaceCollider)
	{
		return;
	}

	SurfaceCollider->SetWorldLocation(PlanetCenter);
	SurfaceCollider->SetSphereRadius(GetGameplaySurfaceRadius(), true);
	SurfaceCollider->SetHiddenInGame(true);
	SurfaceCollider->SetVisibility(false, true);
	SurfaceCollider->SetCollisionObjectType(ECC_WorldStatic);
	SurfaceCollider->SetCollisionEnabled(
		bEnableGameplaySurfaceFallbackCollider ? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::NoCollision);
	SurfaceCollider->SetCollisionResponseToAllChannels(
		bEnableGameplaySurfaceFallbackCollider ? ECR_Block : ECR_Ignore);
	SurfaceCollider->SetGenerateOverlapEvents(false);
	SurfaceCollider->SetCanEverAffectNavigation(false);
	SurfaceCollider->CanCharacterStepUpOn = bEnableGameplaySurfaceFallbackCollider ? ECB_Yes : ECB_No;
}

UStaticMeshComponent* ARedPlanetPresentationController::EnsureGameplaySurfaceVisual()
{
	if (GameplaySurfaceVisual)
	{
		return GameplaySurfaceVisual;
	}

	GameplaySurfaceVisual = NewObject<UStaticMeshComponent>(this, TEXT("GameplaySurfaceVisual"));
	if (!GameplaySurfaceVisual)
	{
		return nullptr;
	}

	if (UStaticMesh* SphereMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere")))
	{
		GameplaySurfaceVisual->SetStaticMesh(SphereMesh);
	}

	if (USceneComponent* AttachParent = EnsureGameplaySurfaceCollider())
	{
		GameplaySurfaceVisual->AttachToComponent(AttachParent, FAttachmentTransformRules::KeepWorldTransform);
	}
	else if (RootComponent)
	{
		GameplaySurfaceVisual->AttachToComponent(RootComponent, FAttachmentTransformRules::KeepWorldTransform);
	}

	GameplaySurfaceVisual->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	GameplaySurfaceVisual->SetCollisionResponseToAllChannels(ECR_Ignore);
	GameplaySurfaceVisual->SetGenerateOverlapEvents(false);
	GameplaySurfaceVisual->SetCanEverAffectNavigation(false);
	GameplaySurfaceVisual->SetCastShadow(false);

	AddInstanceComponent(GameplaySurfaceVisual);
	GameplaySurfaceVisual->RegisterComponent();
	return GameplaySurfaceVisual;
}

void ARedPlanetPresentationController::RefreshGameplaySurfaceVisual()
{
	UStaticMeshComponent* SurfaceVisual = EnsureGameplaySurfaceVisual();
	if (!SurfaceVisual)
	{
		return;
	}

	constexpr float EngineBasicSphereRadius = 50.0f;
	const float SurfaceRadius = FMath::Max(GetGameplaySurfaceRadius(), RedMinUsefulSurfaceRadius);
	const float SurfaceScale = SurfaceRadius / EngineBasicSphereRadius;

	SurfaceVisual->SetWorldLocation(PlanetCenter);
	SurfaceVisual->SetWorldScale3D(FVector(SurfaceScale));
	SurfaceVisual->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	SurfaceVisual->SetCollisionResponseToAllChannels(ECR_Ignore);
	SurfaceVisual->SetGenerateOverlapEvents(false);
	SurfaceVisual->SetCanEverAffectNavigation(false);
	SurfaceVisual->SetCastShadow(false);
	if (!bShowGameplaySurfaceVisual)
	{
		SurfaceVisual->SetHiddenInGame(true, true);
		SurfaceVisual->SetVisibility(false, true);
		return;
	}

	UMaterialInterface* ResolvedSurfaceMaterial = SurfaceVisualMaterial;
	if (!ResolvedSurfaceMaterial)
	{
		ResolvedSurfaceMaterial = LoadObject<UMaterialInterface>(nullptr,
			TEXT("/Game/StylizedDesertOasis/Materials/Instances/Environment/MI_Desert.MI_Desert"));
	}
	if (ResolvedSurfaceMaterial)
	{
		SurfaceVisual->SetMaterial(0, ResolvedSurfaceMaterial);
	}
	SurfaceVisual->SetHiddenInGame(!bShowGameplaySurfaceVisual, true);
	SurfaceVisual->SetVisibility(bShowGameplaySurfaceVisual, true);
}

float ARedPlanetPresentationController::GetPlayableSurfaceRadius() const
{
	return FMath::Max(PlanetRadius + SurfaceVisualClearance, RedMinUsefulSurfaceRadius);
}

float ARedPlanetPresentationController::GetGameplaySurfaceRadius() const
{
	return GetPlayableSurfaceRadius();
}

FVector ARedPlanetPresentationController::GetSurfaceNormalAt(const FVector& WorldLocation) const
{
	const FVector FromCenter = WorldLocation - PlanetCenter;
	return FromCenter.IsNearlyZero() ? FVector::UpVector : FromCenter.GetSafeNormal();
}

FVector ARedPlanetPresentationController::GetSurfaceLocationForActor(const FVector& WorldLocation, const float ActorHalfHeight, const float ExtraClearance) const
{
	const FVector SurfaceNormal = GetSurfaceNormalAt(WorldLocation);
	const float Clearance = FMath::Max(0.0f, ActorHalfHeight) + FMath::Max(0.0f, ExtraClearance);
	return PlanetCenter + SurfaceNormal * (GetGameplaySurfaceRadius() + Clearance);
}

bool ARedPlanetPresentationController::ResolveViewLocation(FVector& OutLocation) const
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return false;
	}

	if (APlayerController* PC = UGameplayStatics::GetPlayerController(World, 0))
	{
		FVector CameraLocation = FVector::ZeroVector;
		FRotator CameraRotation = FRotator::ZeroRotator;
		PC->GetPlayerViewPoint(CameraLocation, CameraRotation);
		OutLocation = CameraLocation;
		return true;
	}

	OutLocation = GetActorLocation();
	return true;
}

void ARedPlanetPresentationController::ApplyPresentationState(const bool bUseFarProxy)
{
	bUsingFarProxy = bUseFarProxy;

	const bool bHasRealVoxelDetail = VoxelDetailActors.Num() > 0 && !bForceProxyOnlyUntilVoxelShellFix;
	const bool bShowVoxelDetail = bHasRealVoxelDetail && !bUseFarProxy;
	const bool bShowGameplaySurface = bShowGameplaySurfaceVisual && !bUseFarProxy && !bShowVoxelDetail;
	const bool bShowProxy = bUseFarProxy;

	for (AActor* Actor : OrbitProxyActors)
	{
		FString ActorName = IsValid(Actor) ? Actor->GetName() : FString();
#if WITH_EDITOR
		if (IsValid(Actor))
		{
			ActorName += TEXT(" ");
			ActorName += Actor->GetActorLabel();
		}
#endif
		// Retire the opaque proxy rim and painted cloud-band shells. They produced the
		// hard blue cut-out and clouds beyond the limb; physical SkyAtmosphere and real
		// volumetric clouds now remain active at orbital distance.
		const bool bLegacyAtmosphereArtifact =
			ActorName.Contains(TEXT("Vibe_PlanetAtmosphereRim"))
			|| ActorName.Contains(TEXT("Vibe_PlanetCloudBands"));
		SetActorPresentationVisible(Actor, bShowProxy && !bLegacyAtmosphereArtifact);
		DisablePresentationShellCollision(Actor);
	}
	for (AActor* Actor : VoxelDetailActors)
	{
		SetActorPresentationVisible(Actor, bShowVoxelDetail);
		if (!bShowVoxelDetail)
		{
			DisablePresentationShellCollision(Actor);
		}
	}
	if (GameplaySurfaceVisual)
	{
		GameplaySurfaceVisual->SetHiddenInGame(!bShowGameplaySurface, true);
		GameplaySurfaceVisual->SetVisibility(bShowGameplaySurface, true);
	}

	ApplySkyPresentationState();
}

void ARedPlanetPresentationController::ApplySkyPresentationState()
{
	const float SkyHysteresis = FMath::Max(0.0f, HysteresisAltitude);

	bool bShowOrbitBackdrop = bUsingOrbitBackdrop;
	if (LastAltitude >= OrbitBackdropVisibleAltitude + SkyHysteresis)
	{
		bShowOrbitBackdrop = true;
	}
	else if (LastAltitude <= OrbitBackdropVisibleAltitude - SkyHysteresis)
	{
		bShowOrbitBackdrop = false;
	}

	const bool bShowSurfaceSky = LastAltitude <= SurfaceSkyVisibleAltitude + SkyHysteresis;

	if (bShowOrbitBackdrop != bUsingOrbitBackdrop)
	{
		UE_LOG(LogRedPlanetPresentation, Display,
			TEXT("Planet sky presentation switched orbit backdrop %s at %.0f cm AGL"),
			bShowOrbitBackdrop ? TEXT("on") : TEXT("off"),
			LastAltitude);
	}

	bUsingOrbitBackdrop = bShowOrbitBackdrop;

	for (AActor* Actor : SurfaceSkyActors)
	{
		SetActorPresentationVisible(Actor, bShowSurfaceSky);
		DisablePresentationShellCollision(Actor);
	}
	for (AActor* Actor : OrbitBackdropActors)
	{
		SetActorPresentationVisible(Actor, bShowOrbitBackdrop);
		DisablePresentationShellCollision(Actor);
	}
}

void ARedPlanetPresentationController::SetActorPresentationVisible(AActor* Actor, const bool bVisible)
{
	if (!IsValid(Actor))
	{
		return;
	}
	FString ActorName = Actor->GetName();
#if WITH_EDITOR
	ActorName += TEXT(" ");
	ActorName += Actor->GetActorLabel();
#endif
	const bool bLegacyAtmosphereArtifact =
		ActorName.Contains(TEXT("Vibe_PlanetAtmosphereRim"))
		|| ActorName.Contains(TEXT("Vibe_PlanetCloudBands"));
	const bool bEffectiveVisible = bVisible && !bLegacyAtmosphereArtifact;

	TArray<USkyAtmosphereComponent*> Atmospheres;
	Actor->GetComponents<USkyAtmosphereComponent>(Atmospheres);
	bool bOwnsPhysicalAtmosphere = false;
	for (USkyAtmosphereComponent* Atmosphere : Atmospheres)
	{
		if (Atmosphere && !Atmosphere->ComponentHasTag(TEXT("RedDisabledSkyAtmosphere")))
		{
			bOwnsPhysicalAtmosphere = true;
			break;
		}
	}

	// Surface-sky Blueprints often own both a cosmetic sky dome and the physical
	// SkyAtmosphere. At orbital LOD, hide only their mesh primitives; hiding the whole
	// actor made the planet's blue limb disappear at the far-sky threshold.
	Actor->SetActorHiddenInGame(!bEffectiveVisible && !bOwnsPhysicalAtmosphere);

#if WITH_EDITOR
	Actor->SetIsTemporarilyHiddenInEditor(!bEffectiveVisible && !bOwnsPhysicalAtmosphere);
#endif

	TArray<UPrimitiveComponent*> Primitives;
	Actor->GetComponents<UPrimitiveComponent>(Primitives);
	for (UPrimitiveComponent* Primitive : Primitives)
	{
		if (!Primitive)
		{
			continue;
		}
		Primitive->SetVisibility(bEffectiveVisible, true);
		Primitive->SetHiddenInGame(!bEffectiveVisible, true);
	}
	for (USkyAtmosphereComponent* Atmosphere : Atmospheres)
	{
		if (Atmosphere)
		{
			if (Atmosphere->ComponentHasTag(TEXT("RedDisabledSkyAtmosphere")))
			{
				Atmosphere->SetVisibility(false, true);
				Atmosphere->SetHiddenInGame(true, true);
				continue;
			}
			Atmosphere->SetVisibility(true, true);
			Atmosphere->SetHiddenInGame(false, true);
		}
	}

	if (IsGeneratedPresentationShellName(ActorName))
	{
		DisablePresentationShellCollision(Actor);
	}
}
