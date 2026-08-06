#include "RedGameMode.h"

#include "EngineUtils.h"
#include "TimerManager.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Engine/World.h"
#include "Engine/Level.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/SkyAtmosphereComponent.h"
#include "Components/VolumetricCloudComponent.h"
#include "Components/HeterogeneousVolumeComponent.h"
#include "Engine/SkyLight.h"
#include "Engine/DirectionalLight.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Engine/ExponentialHeightFog.h"
#include "Engine/PostProcessVolume.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/Engine.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialParameterCollection.h"
#include "Materials/MaterialParameterCollectionInstance.h"
#include "GameFramework/PlayerStart.h"
#include "GameFramework/PlayerController.h"
#include "RedHUD.h"
#include "RedGameInstance.h"
#include "RedOrbitalMiningSite.h"
#include "RedCloningStation.h"
#include "RedOctosphere.h"
#include "RedGravityBodies.h"
#include "RedFoliageField.h"
#include "RedDayNight.h"
#include "RedSpaceScenery.h"
#include "RedPlayerCharacter.h"
#include "RedShip.h"
#include "RedShuttleBase.h"
#include "RedMiniFighter.h"
#include "RedPlanetTerrainQuery.h"
#include "RedPlanetPresentationController.h"
#include "RedPlanetPresentationTuning.h"
#include "InputCoreTypes.h"
#include "GameFramework/PawnMovementComponent.h"
#include "UObject/UnrealType.h"
#include "UObject/ConstructorHelpers.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Engine/Texture.h"
#include "Components/MeshComponent.h"

DEFINE_LOG_CATEGORY_STATIC(LogRedGameMode, Log, All);

namespace
{
constexpr float RedPlanetFallbackSurfaceRadius = 382000.f;
constexpr float RedSpawnSlotSpacing = 450.f;
constexpr int32 RedSpawnSlotsPerRing = 8;

void MakeAtmosphereAttachmentChainMovable(USceneComponent* Component)
{
	// SunSky's SkyAtmosphere is commonly attached below a Static root named "Scene". Promote
	// parents first so centering the atmosphere on the procedural planet is a legal runtime move.
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

bool IsProtectedDesertContentPath(const FString& ObjectPath)
{
	const FString LowerPath = ObjectPath.ToLower();
	return LowerPath.Contains(TEXT("/game/sostylized/"))
		|| LowerPath.Contains(TEXT("/game/stylizeddesertoasis/"));
}

float ComputeVehicleRootAboveRuntimeHullBottom(const AActor* Vehicle, const FVector& SurfaceUp)
{
	if (!IsValid(Vehicle))
	{
		return 100.f;
	}

	const FVector Up = SurfaceUp.GetSafeNormal();
	const float RootProjection = FVector::DotProduct(Vehicle->GetActorLocation(), Up);
	float LowestProjection = TNumericLimits<float>::Max();
	bool bFoundRuntimeHull = false;
	TArray<UPrimitiveComponent*> Primitives;
	Vehicle->GetComponents<UPrimitiveComponent>(Primitives);
	for (const UPrimitiveComponent* Primitive : Primitives)
	{
		if (!IsValid(Primitive) || !Primitive->IsRegistered())
		{
			continue;
		}
		const FString ComponentName = Primitive->GetName();
		if (!ComponentName.StartsWith(TEXT("Runtime"))
			|| !ComponentName.Contains(TEXT("Collision")))
		{
			continue;
		}
		const FBoxSphereBounds Bounds = Primitive->Bounds;
		const float Support = FVector::DotProduct(Bounds.BoxExtent, Up.GetAbs());
		LowestProjection = FMath::Min(LowestProjection,
			FVector::DotProduct(Bounds.Origin, Up) - Support);
		bFoundRuntimeHull = true;
	}

	if (!bFoundRuntimeHull)
	{
		FVector BoundsOrigin = Vehicle->GetActorLocation();
		FVector BoundsExtent(100.f);
		Vehicle->GetActorBounds(false, BoundsOrigin, BoundsExtent, false);
		const float Support = FVector::DotProduct(BoundsExtent, Up.GetAbs());
		LowestProjection = FVector::DotProduct(BoundsOrigin, Up) - Support;
	}
	return FMath::Max(0.f, RootProjection - LowestProjection);
}

/** Oasis actors and both approved art packs are never candidates for the legacy Titan-art strip. */
bool IsProtectedDesertActor(const AActor* Actor)
{
	if (!IsValid(Actor))
	{
		return false;
	}

	if (Actor->ActorHasTag(TEXT("RedOasisPocket"))
		|| IsProtectedDesertContentPath(Actor->GetPathName())
		|| IsProtectedDesertContentPath(Actor->GetClass()->GetPathName()))
	{
		return true;
	}

	TArray<UStaticMeshComponent*> StaticMeshComponents;
	Actor->GetComponents<UStaticMeshComponent>(StaticMeshComponents);
	for (const UStaticMeshComponent* MeshComponent : StaticMeshComponents)
	{
		if (MeshComponent && MeshComponent->GetStaticMesh()
			&& IsProtectedDesertContentPath(MeshComponent->GetStaticMesh()->GetPathName()))
		{
			return true;
		}
	}

	TArray<UMeshComponent*> MeshComponents;
	Actor->GetComponents<UMeshComponent>(MeshComponents);
	for (const UMeshComponent* MeshComponent : MeshComponents)
	{
		if (!MeshComponent)
		{
			continue;
		}
		for (int32 MaterialIndex = 0; MaterialIndex < MeshComponent->GetNumMaterials(); ++MaterialIndex)
		{
			const UMaterialInterface* Material = MeshComponent->GetMaterial(MaterialIndex);
			if (Material && IsProtectedDesertContentPath(Material->GetPathName()))
			{
				return true;
			}
		}
	}

	return false;
}

bool IsProceduralSurfaceDressingActor(const AActor* Actor)
{
	if (!IsValid(Actor))
	{
		return false;
	}
	// RedSpaceScenery deliberately reuses a Stylized Desert Oasis boulder for its
	// orbital asteroid instances.  Mesh-path classification below must never turn
	// that shared art dependency into an instruction to hide the entire moon/star/
	// asteroid presentation actor.
	if (Actor->ActorHasTag(TEXT("RedSpaceScenery")))
	{
		return false;
	}
	auto IsClassOrSuperNamed = [](const UClass* Class, const TCHAR* Name)
	{
		for (const UClass* Current = Class; Current; Current = Current->GetSuperClass())
		{
			if (Current->GetName() == Name)
			{
				return true;
			}
		}
		return false;
	};
	if (Actor->IsA<ARedFoliageField>()
		|| IsClassOrSuperNamed(Actor->GetClass(), TEXT("CLMPlanet"))
		|| IsClassOrSuperNamed(Actor->GetClass(), TEXT("CLMPlanetChunk"))
		|| Actor->ActorHasTag(TEXT("RedProceduralBiomeField"))
		|| Actor->ActorHasTag(TEXT("RedOasisPocket")))
	{
		return true;
	}

	FString Identity = Actor->GetName();
#if WITH_EDITOR
	Identity += TEXT(" ");
	Identity += Actor->GetActorLabel();
#endif
	Identity.ToLowerInline();
	if (Identity.Contains(TEXT("redoasisrock"))
		|| Identity.Contains(TEXT("redoasisdune"))
		|| Identity.Contains(TEXT("redproceduralbiomefield")))
	{
		return true;
	}

	TArray<UStaticMeshComponent*> MeshComponents;
	Actor->GetComponents<UStaticMeshComponent>(MeshComponents);
	for (const UStaticMeshComponent* MeshComponent : MeshComponents)
	{
		const UStaticMesh* Mesh = MeshComponent ? MeshComponent->GetStaticMesh() : nullptr;
		const FString MeshPath = Mesh ? Mesh->GetPathName().ToLower() : FString();
		if (MeshPath.Contains(TEXT("/game/sostylized/environment/foliage/"))
			|| MeshPath.Contains(TEXT("/game/sostylized/environment/rocks/"))
			|| MeshPath.Contains(TEXT("/game/stylizeddesertoasis/meshes/rocks/")))
		{
			return true;
		}
	}
	return false;
}

void DisableProceduralSurfaceDressingActor(AActor* Actor)
{
	if (!IsValid(Actor))
	{
		return;
	}
	if (ARedFoliageField* Field = Cast<ARedFoliageField>(Actor))
	{
		Field->bSuppressAllProceduralDressing = true;
		Field->ClearFoliage();
	}

	auto IsClassOrSuperNamed = [](const UClass* Class, const TCHAR* Name)
	{
		for (const UClass* Current = Class; Current; Current = Current->GetSuperClass())
		{
			if (Current->GetName() == Name)
			{
				return true;
			}
		}
		return false;
	};
	const bool bPlanetGenPlanet = IsClassOrSuperNamed(Actor->GetClass(), TEXT("CLMPlanet"));
	const bool bPlanetGenChunk = IsClassOrSuperNamed(Actor->GetClass(), TEXT("CLMPlanetChunk"));
	if (bPlanetGenPlanet)
	{
		for (const TCHAR* BoolName : { TEXT("bEnableFoliage"), TEXT("bEnableGrass") })
		{
			if (FBoolProperty* Property = FindFProperty<FBoolProperty>(Actor->GetClass(), BoolName))
			{
				Property->SetPropertyValue_InContainer(Actor, false);
			}
		}
		for (const TCHAR* ArrayName : { TEXT("FoliageAssets"), TEXT("GrassAssets") })
		{
			if (FArrayProperty* Property = FindFProperty<FArrayProperty>(Actor->GetClass(), ArrayName))
			{
				FScriptArrayHelper ArrayHelper(
					Property, Property->ContainerPtrToValuePtr<void>(Actor));
				ArrayHelper.EmptyValues();
			}
		}
	}
	if (bPlanetGenPlanet || bPlanetGenChunk)
	{
		// PlanetGen terrain is a procedural mesh, while both sparse foliage and dense grass use
		// instanced components. Clear only those components; hiding the whole chunk would erase land.
		TArray<UInstancedStaticMeshComponent*> InstancedComponents;
		Actor->GetComponents<UInstancedStaticMeshComponent>(InstancedComponents);
		for (UInstancedStaticMeshComponent* Instanced : InstancedComponents)
		{
			if (!Instanced)
			{
				continue;
			}
			Instanced->ClearInstances();
			Instanced->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			Instanced->SetCollisionResponseToAllChannels(ECR_Ignore);
			Instanced->SetVisibility(false, true);
			Instanced->SetHiddenInGame(true, true);
		}
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
		Primitive->SetVisibility(false, true);
		Primitive->SetHiddenInGame(true, true);
		Primitive->CanCharacterStepUpOn = ECB_No;
	}
	Actor->SetActorEnableCollision(false);
	Actor->SetActorHiddenInGame(true);
}

// NOTE: the RedFantasyContentTokens allow-list was retired — IsFantasyBuildingActor now strips ALL
// /Game/Environment/ art wholesale (every Titan prop set floated ~40m above the flat tile or clashed
// with the sci-fi desert), so a token list is no longer needed. The desert LOOK is the Landscape
// sculpt + material under /Game/Landscape/, which is never touched.

FVector SafeNormalOrUp(const FVector& Value)
{
	return Value.IsNearlyZero() ? FVector::UpVector : Value.GetSafeNormal();
}

FVector BuildSurfaceTangent(const FVector& Up, const FVector& Seed)
{
	FVector Tangent = FVector::VectorPlaneProject(Seed, Up).GetSafeNormal();
	if (Tangent.IsNearlyZero())
	{
		Tangent = FVector::VectorPlaneProject(FVector::RightVector, Up).GetSafeNormal();
	}
	return Tangent.IsNearlyZero() ? FVector::ForwardVector : Tangent;
}

FVector BuildOrbitalMiningDirection(const FVector& PlanetCenter, const float SurfaceRadius, const AActor* PreferredStart)
{
	const FVector BaseLocation = PreferredStart ? PreferredStart->GetActorLocation()
		: (PlanetCenter + FVector::UpVector * FMath::Max(10000.f, SurfaceRadius));
	const FVector BaseUp = SafeNormalOrUp(BaseLocation - PlanetCenter);
	const FVector TangentX = BuildSurfaceTangent(BaseUp, PreferredStart ? PreferredStart->GetActorForwardVector() : FVector::ForwardVector);
	const FVector TangentY = (BaseUp ^ TangentX).GetSafeNormal();

	// Slightly forward and around the limb: visible from the starter surface, but still
	// reads as an orbital destination between the Mars body and its moon corridor.
	return SafeNormalOrUp(BaseUp * 0.82f + TangentX * 0.52f + TangentY * 0.21f);
}

float GetDefaultPawnCapsuleHalfHeight(const UClass* PawnClass)
{
	const ACharacter* DefaultCharacter = PawnClass ? Cast<ACharacter>(PawnClass->GetDefaultObject()) : nullptr;
	const UCapsuleComponent* Capsule = DefaultCharacter ? DefaultCharacter->GetCapsuleComponent() : nullptr;
	return Capsule ? Capsule->GetScaledCapsuleHalfHeight() : 96.0f;
}

// Returns true if a real planet body exists in the world. False = FLAT world (Titan / arena):
// callers must spawn with plain -Z gravity, NOT re-project onto a fictitious 382km sphere.
bool ResolvePlayablePlanetSurface(const UWorld* World, FVector& OutCenter, float& OutRadius)
{
	OutCenter = FVector::ZeroVector;
	OutRadius = RedPlanetFallbackSurfaceRadius;

	if (!World)
	{
		return false;
	}

	// CLM PlanetGen mesh planet (real streaming sphere) wins over the voxel-legacy presentation
	// controller, whose analytic radius is hardwired to the old 382 km voxel MVP.
	if (RedGravity::FindMeshPlanet(const_cast<UWorld*>(World), OutCenter, OutRadius))
	{
		return true;
	}

	for (TActorIterator<ARedPlanetPresentationController> It(World); It; ++It)
	{
		const ARedPlanetPresentationController* Controller = *It;
		if (IsValid(Controller))
		{
			OutCenter = Controller->PlanetCenter;
			OutRadius = Controller->GetGameplaySurfaceRadius();
			return true;
		}
	}
	return false;
}
}

ARedGameMode::ARedGameMode()
{
	// Tick so we can keep the flat-world pack shuttle LEVEL to the sphere (its BP auto-stabilizes to
	// WORLD up every frame, which reads as nose-down / wing-down anywhere but the poles). Re-level in
	// TG_LastDemotable AFTER the pack's own tick so RED's radial orientation is the final word each
	// frame (gear on the surface, wings level to the local horizon).
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = true;
	PrimaryActorTick.TickGroup = TG_LastDemotable;

	// The uncooked lean diagnostic client can explicitly avoid the customization Blueprint.
	// This flag is test-only: normal editor, packaged, and multiplayer launches keep the
	// project-owned modular human and character-creator controller below.
#if !UE_BUILD_SHIPPING
	const bool bUseNativeDiagnosticPawn = FParse::Param(
		FCommandLine::Get(), TEXT("RedNativeDiagnosticPawn"));
#else
	constexpr bool bUseNativeDiagnosticPawn = false;
#endif
	DefaultPawnClass = ARedPlayerCharacter::StaticClass();
	PlayerControllerClass = APlayerController::StaticClass();
	if (!bUseNativeDiagnosticPawn)
	{
		// The project-owned gameplay copy keeps the PO-Art modular human and character creator while
		// restricting its UI dispatcher bindings to the locally controlled pawn in multiplayer.
		static ConstructorHelpers::FClassFinder<ARedPlayerCharacter> ModularHumanPawn(
			TEXT("/Game/RedMMO/Characters/BP_RedGameplayCharacter"));
		if (ModularHumanPawn.Succeeded())
		{
			DefaultPawnClass = ModularHumanPawn.Class;
		}

		// The project-local controller preserves the PO-Art character-preview window while
		// preventing its HUD widget from being created for non-local multiplayer controllers.
		static ConstructorHelpers::FClassFinder<APlayerController> CharacterCreatorController(
			TEXT("/Game/RedMMO/UI/BP_RedMultiplayerPlayerController"));
		if (CharacterCreatorController.Succeeded())
		{
			PlayerControllerClass = CharacterCreatorController.Class;
		}
	}
	else
	{
		UE_LOG(LogRedGameMode, Display,
			TEXT("RedNativeDiagnosticPawn active: bypassing customization pawn/controller Blueprints"));
	}

	// Keep the installed SoStylized water family and the project-tinted High Five instances as hard
	// CDO references. Runtime repair uses these objects so the Win64 cook includes the real animated
	// wave/shore-foam material rather than the old project-owned clear-water fallback.
	// The pack's rectangular plane exposed a hard floating shoreline on PlanetGen dunes, so the
	// project-owned irregular disk remains only the oasis carrier mesh.
	static ConstructorHelpers::FObjectFinder<UStaticMesh> WaterPlane(
		TEXT("/Game/RedMMO/Environment/SM_RedOasisPoolOrganic.SM_RedOasisPoolOrganic"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> WaterWaves(
		TEXT("/Game/RedMMO/Environment/MI_RedClearWater.MI_RedClearWater"));
	if (WaterPlane.Succeeded())
	{
		SoStylizedWaterMesh = WaterPlane.Object;
	}
	if (WaterWaves.Succeeded())
	{
		SoStylizedWaterMaterial = WaterWaves.Object;
	}

	// MI_001 ships without an Input SVT override. MI_003 is the equivalent
	// authored VDB-backed source and remains visible when wrapped by a runtime MID.
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> CloudViolet(
		TEXT("/Game/Cloudz_Hi5/Materials/Instances/MI_Cloudz_Hi5_003.MI_Cloudz_Hi5_003"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> CloudCyan(
		TEXT("/Game/Cloudz_Hi5/Materials/Instances/MI_Cloudz_Hi5_002.MI_Cloudz_Hi5_002"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> CloudGold(
		TEXT("/Game/Cloudz_Hi5/Materials/Instances/MI_Cloudz_Hi5_004.MI_Cloudz_Hi5_004"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> CloudRose(
		TEXT("/Game/Cloudz_Hi5/Materials/Instances/MI_Cloudz_Hi5_005.MI_Cloudz_Hi5_005"));
	// Twelve atmosphere-bounded placements reuse the four authored High Five materials. An
	// icosahedral layout covers the poles as well as the equator; the old eight cube corners
	// left every bank 54.7 degrees from the +Z fused-map spawn and looked like an empty sky.
	HighFiveCloudMaterials.SetNum(12);
	HighFiveCloudDynamicMaterials.SetNum(12);
	if (CloudViolet.Succeeded()) { HighFiveCloudMaterials[0] = CloudViolet.Object; }
	if (CloudCyan.Succeeded()) { HighFiveCloudMaterials[1] = CloudCyan.Object; }
	if (CloudGold.Succeeded()) { HighFiveCloudMaterials[2] = CloudGold.Object; }
	if (CloudRose.Succeeded()) { HighFiveCloudMaterials[3] = CloudRose.Object; }
	for (int32 Index = 4; Index < HighFiveCloudMaterials.Num(); ++Index)
	{
		HighFiveCloudMaterials[Index] = HighFiveCloudMaterials[Index % 4];
	}
	// Dynamic targeting reticle on top of the Vibe HUD (the kit's static crosshair was
	// disabled in VibeMMOHUDWidget::BuildDefaultHUDTree to avoid a double crosshair).
	HUDClass = ARedHUD::StaticClass();
}

void ARedGameMode::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	UpdateSpaceships(DeltaSeconds);
	UpdateHighFiveCloudLighting(DeltaSeconds);
}

void ARedGameMode::UpdateHighFiveCloudLighting(float DeltaSeconds)
{
	HighFiveCloudLightingAccumulator += DeltaSeconds;
	if (HighFiveCloudLightingAccumulator < 0.20f)
	{
		return;
	}
	HighFiveCloudLightingAccumulator = 0.f;

	UWorld* World = GetWorld();
	FVector PlanetCenter = FVector::ZeroVector;
	float SurfaceRadius = 0.f;
	if (!World || !RedGravity::FindMeshPlanet(World, PlanetCenter, SurfaceRadius))
	{
		return;
	}

	ADirectionalLight* AtmosphereSun = nullptr;
	for (TActorIterator<ADirectionalLight> It(World); It; ++It)
	{
		UDirectionalLightComponent* Light = Cast<UDirectionalLightComponent>(It->GetLightComponent());
		if (IsValid(Light) && Light->bAtmosphereSunLight
			&& Light->AtmosphereSunLightIndex == 0)
		{
			AtmosphereSun = *It;
			break;
		}
	}
	if (!AtmosphereSun)
	{
		return;
	}

	// Direction from the planet toward the sun. Directional-light forward is the
	// direction the light travels, so the celestial source lies opposite it.
	const FVector ToSun = -AtmosphereSun->GetActorForwardVector().GetSafeNormal();
	const int32 Count = FMath::Min(
		HighFiveCloudVolumes.Num(), HighFiveCloudDynamicMaterials.Num());
	for (int32 Index = 0; Index < Count; ++Index)
	{
		AHeterogeneousVolume* Volume = HighFiveCloudVolumes[Index];
		UMaterialInstanceDynamic* Material = HighFiveCloudDynamicMaterials[Index];
		if (!IsValid(Volume) || !IsValid(Material))
		{
			continue;
		}

		const FVector Radial = (Volume->GetActorLocation() - PlanetCenter).GetSafeNormal();
		const float SolarElevation = FVector::DotProduct(Radial, ToSun);
		// Fade across a broad 21-degree twilight band. Fully transparent before the
		// VDB enters the dark silhouette prevents its finite AABB from becoming a
		// black rectangle, while daylight banks retain the accepted 0.08 density.
		const float Daylight = FMath::SmoothStep(-0.22f, 0.15f, SolarElevation);
		Material->SetScalarParameterValue(TEXT("Density Multiplier"), 0.08f * Daylight);
	}
}

void ARedGameMode::UpdateSpaceships(float DeltaSeconds)
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	FVector Center;
	float SurfaceRadius = 0.f;
	if (!RedGravity::FindMeshPlanet(World, Center, SurfaceRadius))
	{
		return;   // flat/arena maps: leave the ship's own world-up orientation alone
	}
	for (TActorIterator<APawn> It(World); It; ++It)
	{
		APawn* Ship = *It;
		if (!IsValid(Ship) || !Ship->GetClass()->GetName().Contains(TEXT("Shuttle")))
		{
			continue;
		}
		// Tick after the shuttle once so our re-level wins over pack world-+Z stabilize
		// (same TG_LastDemotable). Without this, parked ships sit on a wing at the basin.
		if (!PrimaryActorTick.GetPrerequisites().Contains(FTickPrerequisite(Ship, Ship->PrimaryActorTick)))
		{
			PrimaryActorTick.AddPrerequisite(Ship, Ship->PrimaryActorTick);
		}

		const FVector Up = (Ship->GetActorLocation() - Center).GetSafeNormal();
		if (Up.IsNearlyZero())
		{
			continue;
		}
		// Current heading = forward projected onto the local tangent plane.
		FVector Forward = FVector::VectorPlaneProject(Ship->GetActorForwardVector(), Up).GetSafeNormal();
		if (Forward.IsNearlyZero())
		{
			Forward = FVector::VectorPlaneProject(FVector::ForwardVector, Up).GetSafeNormal();
		}

		if (Cast<APlayerController>(Ship->GetController()))
		{
			// BOARDED: ARedShuttleBase drives radial flight; do not force park re-level.
			PilotedShip = nullptr;
			continue;
		}
		// PARKED: re-level to the surface (gear down, wings level to local horizon), preserving heading.
		PilotedShip = nullptr;
		Ship->SetActorRotation(FRotationMatrix::MakeFromZX(Up, Forward).Rotator(), ETeleportType::TeleportPhysics);
	}
}

void ARedGameMode::EnsureSpawnVehiclesOnPlanetSurface()
{
	UWorld* World = GetWorld();
	if (!World || !HasAuthority())
	{
		return;
	}

	const FString MapName = World->GetMapName();
	if (!MapName.Contains(TEXT("RedPlanetGen"))
		|| MapName.Contains(TEXT("50km"), ESearchCase::IgnoreCase)
		|| MapName.Contains(TEXT("ArtistCanvas"), ESearchCase::IgnoreCase))
	{
		World->GetTimerManager().ClearTimer(VehicleSurfacePlacementTimer);
		return;
	}

	FVector PlanetCenter = FVector::ZeroVector;
	float DatumRadius = 0.f;
	float PeakRadius = 0.f;
	if (!RedGravity::FindMeshPlanet(World, PlanetCenter, DatumRadius, &PeakRadius))
	{
		return;
	}

	AActor* AnchorActor = nullptr;
	for (TActorIterator<APlayerController> It(World); It; ++It)
	{
		if (APawn* Pawn = It->GetPawn())
		{
			AnchorActor = Pawn;
			break;
		}
	}
	if (!AnchorActor)
	{
		for (TActorIterator<APlayerStart> It(World); It; ++It)
		{
			AnchorActor = *It;
			break;
		}
	}
	if (!AnchorActor)
	{
		return;
	}

	FVector AnchorUp = (AnchorActor->GetActorLocation() - PlanetCenter).GetSafeNormal();
	if (AnchorUp.IsNearlyZero())
	{
		AnchorUp = FVector::UpVector;
	}
	FVector TangentForward = FVector::VectorPlaneProject(
		AnchorActor->GetActorForwardVector(), AnchorUp).GetSafeNormal();
	if (TangentForward.IsNearlyZero())
	{
		TangentForward = FVector::CrossProduct(FVector::RightVector, AnchorUp).GetSafeNormal();
	}
	FVector TangentRight = FVector::CrossProduct(AnchorUp, TangentForward).GetSafeNormal();
	if (TangentRight.IsNearlyZero())
	{
		TangentRight = FVector::RightVector;
	}

	struct FVehicleSurfaceSlot
	{
		AActor* Vehicle = nullptr;
		float ForwardOffsetCm = 0.f;
		float RightOffsetCm = 0.f;
	};
	TArray<FVehicleSurfaceSlot> Slots;
	for (TActorIterator<ARedShuttleBase> It(World); It; ++It)
	{
		ARedShuttleBase* Shuttle = *It;
		if (IsValid(Shuttle) && !Shuttle->IsActorBeingDestroyed())
		{
			Slots.Add({ Shuttle, 5000.f, 2500.f });
			break;
		}
	}
	for (TActorIterator<ARedShip> It(World); It; ++It)
	{
		ARedShip* Fighter = *It;
		if (IsValid(Fighter) && !Fighter->IsActorBeingDestroyed()
			&& !Fighter->IsA<ARedMiniFighter>() && !Fighter->GetAttachParentActor())
		{
			Slots.Add({ Fighter, 6000.f, -3500.f });
			break;
		}
	}

	int32 ReadyVehicleCount = 0;
	for (const FVehicleSurfaceSlot& Slot : Slots)
	{
		AActor* Vehicle = Slot.Vehicle;
		if (!IsValid(Vehicle))
		{
			continue;
		}
		if (Vehicle->ActorHasTag(TEXT("RedSpawnVehicleSurfaced")))
		{
			++ReadyVehicleCount;
			continue;
		}
		if (const APawn* VehiclePawn = Cast<APawn>(Vehicle);
			VehiclePawn && VehiclePawn->GetController()
			&& VehiclePawn->GetController()->IsPlayerController())
		{
			++ReadyVehicleCount;
			continue;
		}

		bool bRuntimeHullReady = false;
		TArray<UPrimitiveComponent*> Primitives;
		Vehicle->GetComponents<UPrimitiveComponent>(Primitives);
		for (const UPrimitiveComponent* Primitive : Primitives)
		{
			const FString ComponentName = IsValid(Primitive) ? Primitive->GetName() : FString();
			if (ComponentName.StartsWith(TEXT("Runtime"))
				&& ComponentName.Contains(TEXT("Collision")))
			{
				bRuntimeHullReady = true;
				break;
			}
		}
		if (!bRuntimeHullReady)
		{
			continue;
		}

		const FVector TangentOffset = TangentForward * Slot.ForwardOffsetCm
			+ TangentRight * Slot.RightOffsetCm;
		const FVector TargetDirection = (AnchorUp * FMath::Max(DatumRadius, PeakRadius)
			+ TangentOffset).GetSafeNormal();
		const FVector TraceStart = PlanetCenter + TargetDirection * (PeakRadius + 100000.f);
		const FVector TraceEnd = PlanetCenter + TargetDirection
			* FMath::Max(1000.f, DatumRadius - 100000.f);
		FHitResult TerrainHit;
		if (RedPlanetTerrainQuery::LineTrace(
			World, PlanetCenter, TraceStart, TraceEnd, TerrainHit)
			!= ERedPlanetTerrainQueryResult::Hit)
		{
			continue;
		}

		FVector SurfaceUp = (TerrainHit.ImpactPoint - PlanetCenter).GetSafeNormal();
		if (SurfaceUp.IsNearlyZero())
		{
			SurfaceUp = TargetDirection;
		}
		FVector VehicleForward = FVector::VectorPlaneProject(TangentForward, SurfaceUp).GetSafeNormal();
		if (VehicleForward.IsNearlyZero())
		{
			VehicleForward = FVector::VectorPlaneProject(
				Vehicle->GetActorForwardVector(), SurfaceUp).GetSafeNormal();
		}
		const float RootAboveBottom = ComputeVehicleRootAboveRuntimeHullBottom(Vehicle, SurfaceUp);
		const FVector ParkLocation = TerrainHit.ImpactPoint
			+ SurfaceUp * (RootAboveBottom + 25.f);
		Vehicle->SetActorLocationAndRotation(ParkLocation,
			FRotationMatrix::MakeFromZX(SurfaceUp, VehicleForward).Rotator(), false,
			nullptr, ETeleportType::TeleportPhysics);
		if (APawn* VehiclePawn = Cast<APawn>(Vehicle))
		{
			if (UPawnMovementComponent* Movement = VehiclePawn->GetMovementComponent())
			{
				Movement->StopMovementImmediately();
			}
		}
		Vehicle->Tags.AddUnique(TEXT("RedSpawnVehicleSurfaced"));
		Vehicle->ForceNetUpdate();
		++ReadyVehicleCount;
		UE_LOG(LogRedGameMode, Display,
			TEXT("Surface-parked spawn vehicle %s at %s terrain=%s clearance=25cm"),
			*GetNameSafe(Vehicle), *ParkLocation.ToCompactString(),
			*TerrainHit.ImpactPoint.ToCompactString());
	}

	++VehicleSurfacePlacementAttempts;
	if ((Slots.Num() >= 2 && ReadyVehicleCount == Slots.Num())
		|| VehicleSurfacePlacementAttempts >= 60)
	{
		World->GetTimerManager().ClearTimer(VehicleSurfacePlacementTimer);
		if (ReadyVehicleCount == Slots.Num())
		{
			UE_LOG(LogRedGameMode, Display,
				TEXT("Spawn vehicle surface pass finished: ready=%d expected=%d attempts=%d"),
				ReadyVehicleCount, Slots.Num(), VehicleSurfacePlacementAttempts);
		}
		else
		{
			UE_LOG(LogRedGameMode, Warning,
				TEXT("Spawn vehicle surface pass timed out: ready=%d expected=%d attempts=%d"),
				ReadyVehicleCount, Slots.Num(), VehicleSurfacePlacementAttempts);
		}
	}
}

void ARedGameMode::BeginPlay()
{
	Super::BeginPlay();

	// Explicitly finalize a hosted Steam lobby after same-map ServerTravel. In that case
	// PostLoadMapWithWorld is not guaranteed to fire, but GameMode BeginPlay always does.
	if (UWorld* World = GetWorld())
	{
		if (URedGameInstance* GameInstance = Cast<URedGameInstance>(World->GetGameInstance()))
		{
			GameInstance->NotifyGameplayWorldReady(World);
		}
	}

	// PlanetGen: with BiomeParams.bEnabled=false, desert SandMult stays 0 and only the thin beach
	// band (UV1.x) samples the Sand material layer — inland "dunes" read as grass/rock noise, so
	// SoStylized LayerParameter[3] never shows. Flip biomes on via reflection (no PlanetGen dep)
	// before chunks finish streaming so arid lowlands get SandW and MI_PlanetBiome_RED sand.
	if (UWorld* World = GetWorld())
	{
		for (TActorIterator<AActor> It(World); It; ++It)
		{
			AActor* Actor = *It;
			if (!IsValid(Actor))
			{
				continue;
			}
			bool bIsPlanet = false;
			for (const UClass* C = Actor->GetClass(); C; C = C->GetSuperClass())
			{
				if (C->GetName() == TEXT("CLMPlanet"))
				{
					bIsPlanet = true;
					break;
				}
			}
			if (!bIsPlanet)
			{
				continue;
			}
			if (FStructProperty* BiomeProp = FindFProperty<FStructProperty>(Actor->GetClass(), TEXT("BiomeParams")))
			{
				void* BiomePtr = BiomeProp->ContainerPtrToValuePtr<void>(Actor);
				if (FBoolProperty* EnabledProp = FindFProperty<FBoolProperty>(BiomeProp->Struct, TEXT("bEnabled")))
				{
					EnabledProp->SetPropertyValue_InContainer(BiomePtr, true);
					UE_LOG(LogTemp, Display, TEXT("RedGameMode: enabled PlanetGen Sand-layer selection on %s (desert/ocean-only pass)"),
						*Actor->GetName());
				}
			}
			break;
		}
	}

	// Remove saved and runtime surface dressing without altering the PlanetGen height field or ocean.
	RemoveProceduralSurfaceDressing();

	// Point TerrainMaterial at the sphere-safe desert material (no mesh/height overwrite).
	SoStylizedSandRetryCount = 0;
	EnsureSoStylizedSandOnPlanetTerrain();
	ConfigureNightWaterT04MaterialBridge();
	EnsureSoStylizedOceanWater();
	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().SetTimer(
			SoStylizedSandRetryTimer, this, &ARedGameMode::EnsureSoStylizedSandOnPlanetTerrain,
			0.75f, true);
		VehicleSurfacePlacementAttempts = 0;
		World->GetTimerManager().SetTimer(
			VehicleSurfacePlacementTimer, this,
			&ARedGameMode::EnsureSpawnVehiclesOnPlanetSurface,
			1.0f, true, 10.0f);
		// Oasis pockets after planet/PlayerStart settle (not next-tick — FindMeshPlanet needs CLM).
	}

	// TitanMain ships no SkyLight — it relied on Lumen GI for ambient fill. With Lumen off (the perf/
	// de-gloom pass) there was NO ambient, so shadowed/back-lit meshes (volcanic spikes, rocks) rendered
	// as pure-black silhouettes. A cheap real-time SkyLight restores fill without bringing Lumen back.
	EnsureSkyLight();
	EnsureAtmosphereAndClouds();
	// Do NOT EnsureSpaceStarDomes here — additive star spheres leak onto sand/sky even when hidden
	// on Metal. UpdateSkyFade spawns them only after clearing the atmosphere.
	// Purge any map-persisted SpaceStarDome leftovers immediately (old fix scripts saved them).
	if (UWorld* World = GetWorld())
	{
		for (TActorIterator<AStaticMeshActor> It(World); It; ++It)
		{
			if (It->ActorHasTag(TEXT("SpaceStarDome"))
				|| It->GetActorNameOrLabel().Contains(TEXT("SpaceStarDome")))
			{
				UE_LOG(LogRedGameMode, Display, TEXT("BeginPlay: destroying leftover %s"),
					*It->GetActorNameOrLabel());
				It->Destroy();
			}
		}
		// PlanetGen / map defaults can reset VolumetricCloud planet_radius back to Earth 6360
		// after BeginPlay — re-assert blue sky + matched cloud radius for a few seconds.
		AtmosphereCloudRetryCount = 0;
		World->GetTimerManager().SetTimer(
			AtmosphereCloudRetryTimer, this, &ARedGameMode::EnsureAtmosphereAndClouds,
			1.0f, true);
	}

	// Kill World Partition HLOD: on this Metal setup the HLOD bake renders as black/checkerboard proxy
	// tiles — that is what made the flat face read as a SQUARE from orbit and littered the surface with
	// floating black rock proxies. The octosphere proxy sphere is the far-view now, so HLOD is dead
	// weight (also a draw-call win). Done here at runtime (NOT in DefaultEngine.ini [SystemSettings],
	// which applies pre-WorldPartition-init and SIGSEGVs ConsoleManager). Revisit if HLOD is re-baked.
	#if PLATFORM_MAC
	if (GetWorld())
	{
		GetWorld()->Exec(GetWorld(), TEXT("wp.Runtime.HLOD 0"));
		GetWorld()->Exec(GetWorld(), TEXT("r.HLOD 0"));
	}
	#endif

	if (bStripFantasyBuildings && GetWorld())
	{
		// PRIMARY: hide matching content the instant its WP cell streams in (before first render) — this
		// is what kills the "two games flashing in and out" the timer sweep couldn't (content was visible
		// for up to a full sweep interval each time a cell (re)loaded as the player moved around).
		LevelAddedHandle = FWorldDelegates::LevelAddedToWorld.AddUObject(this, &ARedGameMode::OnLevelAddedToWorld);

		// BACKUP: a periodic full sweep for anything the per-cell hook misses (persistent-level actors,
		// actors added via other paths). We HIDE rather than Destroy: some Titan structures are
		// ChildActorComponent children or referenced by BP_MeshAnimationOverSpline arrays — destroying
		// them dangles those references and SIGSEGVs during streaming registration. Hiding is safe.
		SweepFantasyActors();
		GetWorldTimerManager().SetTimer(FantasyStripSweepTimer, this, &ARedGameMode::SweepFantasyActors, 2.5f, true);
	}

	// Desert ZONES (#59): the same baked desert, presented as 8 distinct drop-zones by re-lighting +
	// color-grading it at runtime — the stable way to "replicate the map" without duplicating heavy
	// 20MB Landscape levels (which crashes the UE5.8 editor). The mood is (re)applied + advanced in
	// RestartPlayer so every drop/respawn lands in the NEXT desert zone.
}

namespace
{
	struct FRedZoneMood
	{
		const TCHAR* Name;
		FLinearColor Light;
		float Intensity;
		float SunPitch;
		FVector4 Gain;   // post-process ColorGain (per-channel multiply + luminance)
		FVector4 Sat;    // post-process ColorSaturation
	};
	// 8 desert moods on one geometry. Gain/Sat shift the WHOLE image (incl. the stylized sky) via an
	// unbound post-process volume; Light/SunPitch retint the scene's directional sun.
	static const FRedZoneMood GRedZoneMoods[8] = {
		// Dialed down 2026-07-07: intensities 5-8 + saturations >1 blew the desert out (auto-exposure is
		// off). Natural daylight (~2.4-3.2 intensity), subtle colour gain, and saturation < 1 everywhere.
		{ TEXT("Dawn Dunes"),      FLinearColor(1.00f,0.90f,0.76f), 2.9f, -20.f, FVector4(1.02f,1.00f,0.96f,1.f), FVector4(0.90f,0.90f,0.90f,1.f) },
		{ TEXT("Blood Noon"),      FLinearColor(1.00f,0.68f,0.55f), 3.1f, -55.f, FVector4(1.05f,0.94f,0.88f,1.f), FVector4(0.92f,0.90f,0.87f,1.f) },
		{ TEXT("Amethyst Dusk"),   FLinearColor(0.94f,0.80f,0.98f), 2.4f, -10.f, FVector4(1.00f,0.96f,1.04f,1.f), FVector4(0.90f,0.88f,0.92f,1.f) },
		{ TEXT("Bleached Wastes"), FLinearColor(1.00f,0.98f,0.94f), 3.2f, -70.f, FVector4(1.02f,1.02f,1.00f,1.f), FVector4(0.82f,0.82f,0.83f,1.f) },
		{ TEXT("Emerald Oasis"),   FLinearColor(0.88f,1.00f,0.86f), 2.9f, -40.f, FVector4(0.96f,1.03f,0.97f,1.f), FVector4(0.90f,0.93f,0.90f,1.f) },
		{ TEXT("Ashen Night"),     FLinearColor(0.62f,0.74f,1.00f), 1.7f, -25.f, FVector4(0.92f,0.95f,1.06f,1.f), FVector4(0.85f,0.88f,0.93f,1.f) },
		{ TEXT("Storm Ochre"),     FLinearColor(1.00f,0.80f,0.60f), 2.5f, -30.f, FVector4(1.04f,0.97f,0.84f,1.f), FVector4(0.88f,0.86f,0.81f,1.f) },
		{ TEXT("Cobalt Frost"),    FLinearColor(0.80f,0.92f,1.00f), 2.7f, -35.f, FVector4(0.93f,0.98f,1.06f,1.f), FVector4(0.90f,0.93f,0.98f,1.f) },
	};
}

void ARedGameMode::ApplyZoneMood(int32 Index)
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	// The desert ZoneMood LOCKS exposure to 1.0 (so bright sand doesn't blow out). On a CLM mesh planet
	// (dim sun + SkyAtmosphere) that pinned exposure renders the whole world BLACK. Skip it there and let
	// the map's own SkyAtmosphere + auto-exposure light the planet.
	{
		FVector MeshCenter; float MeshRadius;
		if (RedGravity::FindMeshPlanet(World, MeshCenter, MeshRadius))
		{
			return;
		}
	}
	Index = ((Index % 8) + 8) % 8;
	ZoneIndex = Index;
	const FRedZoneMood& M = GRedZoneMoods[Index];

	// Retint the scene's directional sun (color + strength + angle = time-of-day feel).
	for (TActorIterator<ADirectionalLight> It(World); It; ++It)
	{
		if (UDirectionalLightComponent* C = Cast<UDirectionalLightComponent>(It->GetLightComponent()))
		{
			C->SetLightColor(M.Light);
			C->SetIntensity(M.Intensity);
		}
		It->SetActorRotation(FRotator(M.SunPitch, 35.f, 0.f));
	}

	// One reused unbound post-process volume carries the per-zone color grade (tints the whole frame,
	// including the stylized sky, so each zone reads as a genuinely different desert).
	if (!IsValid(ZoneMoodPPV))
	{
		for (TActorIterator<APostProcessVolume> It(World); It; ++It)
		{
			if (It->GetName().Contains(TEXT("ZoneMood"))) { ZoneMoodPPV = *It; break; }
		}
		if (!IsValid(ZoneMoodPPV))
		{
			FActorSpawnParameters P;
			P.Name = TEXT("RedZoneMoodPPV");
			ZoneMoodPPV = World->SpawnActor<APostProcessVolume>(APostProcessVolume::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator, P);
		}
	}
	if (IsValid(ZoneMoodPPV))
	{
		ZoneMoodPPV->bUnbound = true;
		ZoneMoodPPV->Priority = 100.f;
		FPostProcessSettings& S = ZoneMoodPPV->Settings;
		S.bOverride_ColorGain = true;        S.ColorGain = M.Gain;
		S.bOverride_ColorSaturation = true;  S.ColorSaturation = M.Sat;
		// LOCK exposure: the big flat desert sand fills the frame and blows out to white under
		// auto-exposure. Pinning min=max=1 disables adaptation (matches the r.DefaultFeature.AutoExposure
		// False test that made the sand read as sand instead of white).
		S.bOverride_AutoExposureMinBrightness = true; S.AutoExposureMinBrightness = 1.0f;
		S.bOverride_AutoExposureMaxBrightness = true; S.AutoExposureMaxBrightness = 1.0f;
	}

	if (GEngine)
	{
		GEngine->AddOnScreenDebugMessage(7100, 6.f, FColor::Cyan,
			FString::Printf(TEXT("DESERT ZONE %d/8  -  %s"), Index + 1, M.Name));
	}
}

void ARedGameMode::OnLevelAddedToWorld(ULevel* Level, UWorld* World)
{
	if (!Level || World != GetWorld())
	{
		return;
	}
	// Hide matching actors as soon as the cell's level is added — set before their components register,
	// so they never draw a visible frame. O(actors in this cell), not O(all actors).
	for (AActor* A : Level->Actors)
	{
		if (bSuppressProceduralSurfaceDressing && IsProceduralSurfaceDressingActor(A))
		{
			DisableProceduralSurfaceDressingActor(A);
			continue;
		}
		if (bStripFantasyBuildings && IsValid(A) && !A->IsHidden()
			&& (IsFantasyBuildingActor(A) || IsPointOfInterestMarker(A)))
		{
			StripFantasyActor(A);
		}
	}
}

void ARedGameMode::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	RestoreNightWaterT04MaterialBridge();
	if (GetWorld())
	{
		GetWorldTimerManager().ClearTimer(FantasyStripSweepTimer);
		GetWorldTimerManager().ClearTimer(SoStylizedSandRetryTimer);
		GetWorldTimerManager().ClearTimer(AtmosphereCloudRetryTimer);
		GetWorldTimerManager().ClearTimer(VehicleSurfacePlacementTimer);
		GetWorldTimerManager().ClearTimer(OasisTerraformTimer);
		GetWorldTimerManager().ClearTimer(ProceduralBiomeTimer);
	}
	if (LevelAddedHandle.IsValid())
	{
		FWorldDelegates::LevelAddedToWorld.Remove(LevelAddedHandle);
		LevelAddedHandle.Reset();
	}
	Super::EndPlay(EndPlayReason);
}

UMaterialInterface* ARedGameMode::ResolveSoStylizedWaterMaterialForCurrentMap() const
{
	if (!SoStylizedWaterMaterial)
	{
		return nullptr;
	}
	const UWorld* World = GetWorld();
	if (!World || !RedPlanetPresentationTuning::IsNightWaterT04MapName(World->GetMapName()))
	{
		return SoStylizedWaterMaterial;
	}
	// The default test isolates planet-ocean topology with the known-coherent
	// WorldGen body. A development command-line flag can select the project-owned
	// So Stylized child for a paired radial-material A/B without touching any map.
	if (UMaterialInterface* GlobalOceanMaterial = LoadObject<UMaterialInterface>(nullptr,
		RedPlanetPresentationTuning::ResolveNightWaterT04GlobalOceanMaterialPath()))
	{
		return GlobalOceanMaterial;
	}
	if (UMaterialInterface* NightWaterMaterial = LoadObject<UMaterialInterface>(nullptr,
		RedPlanetPresentationTuning::NightWaterT04MaterialPath))
	{
		return NightWaterMaterial;
	}
	UE_LOG(LogRedGameMode, Warning,
		TEXT("NightWater_T04 could not load its selected global-ocean material or project-owned So Stylized fallback; using production water."));
	return SoStylizedWaterMaterial;
}

void ARedGameMode::ConfigureNightWaterT04MaterialBridge()
{
	UWorld* World = GetWorld();
	if (!World || bNightWaterT04MpcOverrideApplied
		|| !RedPlanetPresentationTuning::IsNightWaterT04MapName(World->GetMapName()))
	{
		return;
	}
	NightWaterT04EnvironmentCollection = LoadObject<UMaterialParameterCollection>(nullptr,
		TEXT("/Game/SoStylized/Environment/MPC_GlobalEnvironment.MPC_GlobalEnvironment"));
	if (!NightWaterT04EnvironmentCollection)
	{
		UE_LOG(LogRedGameMode, Warning,
			TEXT("NightWater_T04 could not load the SoStylized day-cycle collection; inherited material values remain unchanged."));
		return;
	}
	if (UMaterialParameterCollectionInstance* CollectionInstance =
		World->GetParameterCollectionInstance(NightWaterT04EnvironmentCollection))
	{
		if (CollectionInstance->GetScalarParameterValue(TEXT("Day Cycle Progress"),
			NightWaterT04PreviousDayCycleProgress)
			&& CollectionInstance->SetScalarParameterValue(TEXT("Day Cycle Progress"), 0.0f))
		{
			bNightWaterT04MpcOverrideApplied = true;
			UE_LOG(LogRedGameMode, Display,
				TEXT("NightWater_T04: reset map-local SoStylized Day Cycle Progress to its non-emissive phase (previous %.3f)."),
				NightWaterT04PreviousDayCycleProgress);
		}
	}
}

void ARedGameMode::RestoreNightWaterT04MaterialBridge()
{
	UWorld* World = GetWorld();
	if (!World || !bNightWaterT04MpcOverrideApplied || !NightWaterT04EnvironmentCollection)
	{
		return;
	}
	if (UMaterialParameterCollectionInstance* CollectionInstance =
		World->GetParameterCollectionInstance(NightWaterT04EnvironmentCollection))
	{
		CollectionInstance->SetScalarParameterValue(TEXT("Day Cycle Progress"),
			NightWaterT04PreviousDayCycleProgress);
	}
	bNightWaterT04MpcOverrideApplied = false;
}

void ARedGameMode::EnsureSoStylizedSandOnPlanetTerrain()
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}

	++SoStylizedSandRetryCount;

	// SAFE Mars-dune path (2026-07-11):
	// Demo map uses MI_Landscape_Desert + MF_DesertSand on a FLAT Landscape (UV0).
	// Applying that (or M_PlanetDesertSand_WA / MI_SoStylizedDesertSand_Planet) as a full
	// mesh material on PlanetGen sphere chunks → dark/light stripes. Do NOT do that.
	// Instead: keep PlanetGen M_Planet / MI_PlanetBiome_RED (sphere-aware layers) and rely on
	// SoStylized T_DesertSand_* already wired into Sand LayerParameter[3] via editor tools.
	UMaterialInterface* BiomeSand = nullptr;
#if !UE_BUILD_SHIPPING
	const bool bUseIsolatedSparkleT02 = FParse::Param(
		FCommandLine::Get(), TEXT("RedSandSparkleT02"));
	if (bUseIsolatedSparkleT02)
	{
		BiomeSand = LoadObject<UMaterialInterface>(nullptr,
			TEXT("/Game/RedMMO/Materials/DesertSparkleTest/MI_PlanetBiome_DesertSparkle_T02.MI_PlanetBiome_DesertSparkle_T02"));
		if (!BiomeSand)
		{
			UE_LOG(LogRedGameMode, Error,
				TEXT("EnsureSoStylizedSand: -RedSandSparkleT02 requested but isolated test MI is missing; using the safe default"));
		}
	}
#endif
	if (!BiomeSand)
	{
		BiomeSand = LoadObject<UMaterialInterface>(nullptr,
			TEXT("/Game/RedMMO/Materials/MI_PlanetBiome_RED.MI_PlanetBiome_RED"));
	}

	bool bTouched = false;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		AActor* Actor = *It;
		if (!IsValid(Actor)) { continue; }
		bool bIsPlanet = false;
		for (const UClass* C = Actor->GetClass(); C; C = C->GetSuperClass())
		{
			if (C->GetName() == TEXT("CLMPlanet"))
			{
				bIsPlanet = true;
				break;
			}
		}
		if (!bIsPlanet) { continue; }
		if (bSuppressProceduralSurfaceDressing)
		{
			// Re-assert after PlanetGen initialization: disable both scatter systems and empty
			// their asset arrays before streamed chunks can inherit them.
			DisableProceduralSurfaceDressingActor(Actor);
		}

		if (BiomeSand)
		{
			if (FObjectPropertyBase* MatProp = FindFProperty<FObjectPropertyBase>(Actor->GetClass(), TEXT("TerrainMaterial")))
			{
				UObject* Cur = MatProp->GetObjectPropertyValue_InContainer(Actor);
				const FString CurPath = Cur ? Cur->GetPathName() : FString();
				// Only replace if something else (WA / Oasis MI_Desert) was forced on — never
				// thrash when already on PlanetBiome / PlanetDesert.
				const bool bAlreadyBiome = CurPath == BiomeSand->GetPathName();
				if (!bAlreadyBiome)
				{
					MatProp->SetObjectPropertyValue_InContainer(Actor, BiomeSand);
					bTouched = true;
				}
			}
		}

		if (FStructProperty* BiomeProp = FindFProperty<FStructProperty>(Actor->GetClass(), TEXT("BiomeParams")))
		{
			void* BiomePtr = BiomeProp->ContainerPtrToValuePtr<void>(Actor);
			auto SetBool = [](UStruct* Struct, void* Ptr, const TCHAR* Name, bool Val)
			{
				if (FBoolProperty* P = FindFProperty<FBoolProperty>(Struct, Name))
				{
					P->SetPropertyValue_InContainer(Ptr, Val);
				}
			};
			auto SetFloat = [](UStruct* Struct, void* Ptr, const TCHAR* Name, float Val)
			{
				if (FFloatProperty* P = FindFProperty<FFloatProperty>(Struct, Name))
				{
					P->SetPropertyValue_InContainer(Ptr, Val);
				}
			};
			// Keep material-layer selection active while the configured climate corners below
			// remain desert-only.  Disabling it bypasses SandMult and hides the corrected
			// So Stylized Sand layer except for the shoreline mask.
			SetBool(BiomeProp->Struct, BiomePtr, TEXT("bEnabled"), true);
			SetBool(BiomeProp->Struct, BiomePtr, TEXT("bAutoScaleClimate"), false);
			SetFloat(BiomeProp->Struct, BiomePtr, TEXT("LatitudeWeight"), 0.78f);
			SetFloat(BiomeProp->Struct, BiomePtr, TEXT("ClimateBandMultiplier"), 1.35f);
			SetFloat(BiomeProp->Struct, BiomePtr, TEXT("BiomeBlend"), 0.12f);
			// This retry is a sand-material validation pass, not a terrain/foliage pass.  Cover the
			// full non-water elevation range so the Sand material layer is visible from spawn through
			// the high dunes; the previous 0.50 cap exposed the non-sand fallback on upper terrain.
			SetFloat(BiomeProp->Struct, BiomePtr, TEXT("DesertSandTopNorm"), 1.00f);
			SetFloat(BiomeProp->Struct, BiomePtr, TEXT("PolarLatitude"), 62.f);
			SetFloat(BiomeProp->Struct, BiomePtr, TEXT("PolarBlend"), 12.f);

			// PlanetGen stores density/threshold controls inside four nested climate corners. The old
			// top-level SandMult/GrassMult reflection wrote nothing, making the entire planet desert.
			auto ConfigureCorner = [&](const TCHAR* CornerName, float SnowStart, float RockStart,
				float GrassMult, float SandMult)
			{
				if (FStructProperty* CornerProp = FindFProperty<FStructProperty>(BiomeProp->Struct, CornerName))
				{
					void* CornerPtr = CornerProp->ContainerPtrToValuePtr<void>(BiomePtr);
					SetFloat(CornerProp->Struct, CornerPtr, TEXT("SnowStart"), SnowStart);
					SetFloat(CornerProp->Struct, CornerPtr, TEXT("RockStart"), RockStart);
					SetFloat(CornerProp->Struct, CornerPtr, TEXT("GrassMult"), GrassMult);
					SetFloat(CornerProp->Struct, CornerPtr, TEXT("SandMult"), SandMult);
				}
			};
			ConfigureCorner(TEXT("Tundra"), 2.00f, 2.00f, 0.00f, 1.00f);
			ConfigureCorner(TEXT("Boreal"), 2.00f, 2.00f, 0.00f, 1.00f);
			ConfigureCorner(TEXT("Desert"), 2.00f, 2.00f, 0.00f, 1.00f);
			ConfigureCorner(TEXT("Tropical"), 2.00f, 2.00f, 0.00f, 1.00f);

			// These actor-level controls govern the high-altitude snow/rock transition everywhere.
			SetFloat(Actor->GetClass(), Actor, TEXT("SnowStart"), 2.00f);
			SetFloat(Actor->GetClass(), Actor, TEXT("SnowBlend"), 0.00f);
			SetFloat(Actor->GetClass(), Actor, TEXT("RockStart"), 2.00f);
			bTouched = true;
		}
		break;
	}

	if (SoStylizedSandRetryCount == 1 || bTouched)
	{
		UE_LOG(LogRedGameMode, Display,
			TEXT("EnsureSoStylizedSand: biome-layer path (no mesh overwrite) mat=%s touched=%d try=%d"),
			BiomeSand ? *BiomeSand->GetName() : TEXT("NULL"), bTouched ? 1 : 0, SoStylizedSandRetryCount);
	}
	if (SoStylizedSandRetryCount >= 6)
	{
		World->GetTimerManager().ClearTimer(SoStylizedSandRetryTimer);
	}
}

void ARedGameMode::EnsureSoStylizedOceanWater()
{
	UWorld* World = GetWorld();
	UMaterialInterface* ActiveWaterMaterial = ResolveSoStylizedWaterMaterialForCurrentMap();
	if (!World || !ActiveWaterMaterial)
	{
		return;
	}
	const bool bNightWaterVisualTest =
		RedPlanetPresentationTuning::IsNightWaterT04MapName(World->GetMapName());
	const bool bUsesWorldGenGlobalOcean = bNightWaterVisualTest
		&& ActiveWaterMaterial->GetPathName().StartsWith(TEXT("/WorldGen/"));
	const bool bUsesProjectRadialOcean = bNightWaterVisualTest
		&& ActiveWaterMaterial->GetPathName().Contains(TEXT("MI_RedRadialWater_Night_T04_V4"));

	int32 UpdatedComponents = 0;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		AActor* Actor = *It;
		if (!IsValid(Actor) || Actor->GetActorNameOrLabel().Contains(TEXT("RedOasisWater")))
		{
			continue;
		}

		const FString DisplayLabel = Actor->GetActorNameOrLabel();
		const FString ClassName = Actor->GetClass()->GetName();
		bool bPlanetActor = false;
		for (const UClass* C = Actor->GetClass(); C; C = C->GetSuperClass())
		{
			if (C->GetName() == TEXT("CLMPlanet"))
			{
				bPlanetActor = true;
				break;
			}
		}
		const bool bOceanActor = DisplayLabel.Contains(TEXT("Ocean"))
			|| ClassName.Contains(TEXT("WaterBodyOcean"));

		// Keep the PlanetGen source property in sync so regenerated water components inherit the same
		// visible family instead of reverting to M_PlanetWater.
		if (bPlanetActor)
		{
			if (FObjectPropertyBase* WaterMaterialProperty =
				FindFProperty<FObjectPropertyBase>(Actor->GetClass(), TEXT("WaterMaterial")))
			{
				if (WaterMaterialProperty->PropertyClass
					&& WaterMaterialProperty->PropertyClass->IsChildOf(UMaterialInterface::StaticClass()))
				{
					WaterMaterialProperty->SetObjectPropertyValue_InContainer(Actor, ActiveWaterMaterial);
				}
			}
		}

		TArray<UMeshComponent*> MeshComponents;
		Actor->GetComponents<UMeshComponent>(MeshComponents);
		for (UMeshComponent* MeshComponent : MeshComponents)
		{
			if (!IsValid(MeshComponent))
			{
				continue;
			}
			const FString ComponentName = MeshComponent->GetName();
			const bool bOceanSurface = ComponentName.Contains(TEXT("WaterSphere"))
				|| ComponentName.Contains(TEXT("Ocean"))
				|| (bOceanActor && ComponentName.Contains(TEXT("Water")));
			if (!bOceanSurface)
			{
				continue;
			}

			for (int32 MaterialIndex = 0; MaterialIndex < FMath::Max(1, MeshComponent->GetNumMaterials()); ++MaterialIndex)
			{
				// The T04 WorldGen branch is deliberately left at its authored defaults: this
				// is a topology A/B test, and the So Stylized scalar names are not valid
				// controls for a different material family.
				if (bUsesWorldGenGlobalOcean)
				{
					MeshComponent->SetMaterial(MaterialIndex, ActiveWaterMaterial);
				}
				// Restore the pack's authentic animated normals, edge waves/foam, caustics and
				// refraction. Its day-cycle material function is built for the flat demo map,
				// so zero only the emissive input and let RED's sun/moon light the radial planet.
				else if (UMaterialInstanceDynamic* WaterDMI = MeshComponent->CreateDynamicMaterialInstance(
					MaterialIndex, ActiveWaterMaterial))
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
					// Single-Layer Water scattering was brighter than the moonlit terrain on
					// the dark hemisphere. Keep it clear and blue by day without making the
					// ocean look internally illuminated at night.
					WaterDMI->SetScalarParameterValue(TEXT("Water Scattering"),
						bNightWaterVisualTest ? RedPlanetPresentationTuning::NightWaterT04Scattering : 0.10f);
					// PlanetGen terrain cannot contribute to the global distance field, so the
					// vendor edge-foam branch has no valid shoreline mask on this sphere. Keep
					// the authentic panners/clear-water shading, strengthen the now-corrected
					// moving normals, and let RedShorelineWaveComponent provide traced crests.
					WaterDMI->SetScalarParameterValue(TEXT("Normal1 Flatness"),
						bNightWaterVisualTest ? RedPlanetPresentationTuning::NightWaterT04Normal1Flatness : 0.78f);
					WaterDMI->SetScalarParameterValue(TEXT("Normal2 Flatness"),
						bNightWaterVisualTest ? RedPlanetPresentationTuning::NightWaterT04Normal2Flatness : 0.82f);
					WaterDMI->SetScalarParameterValue(TEXT("Distant Normal Flatness"),
						bNightWaterVisualTest ? RedPlanetPresentationTuning::NightWaterT04DistantNormalFlatness : 0.88f);
					WaterDMI->SetScalarParameterValue(TEXT("Foam Multiply"), 0.f);
					// The So Stylized caustic pass assumes a shallow, planar receiver.
					// On the radial PlanetGen ocean it becomes a full white sheet on the
					// dark hemisphere. Keep the pack's normal/refraction response, but
					// disable this one invalid branch exclusively on the T04 test map.
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
				else
				{
					MeshComponent->SetMaterial(MaterialIndex, ActiveWaterMaterial);
				}
			}
			MeshComponent->SetCastShadow(false);
			MeshComponent->SetReceivesDecals(false);
			MeshComponent->ComponentTags.AddUnique(TEXT("RedSoStylizedWaterApplied"));
			MeshComponent->MarkRenderStateDirty();
			if (bUsesProjectRadialOcean)
			{
				const UMaterialInterface* AppliedMaterial = MeshComponent->GetMaterial(0);
				UE_LOG(LogRedGameMode, Display,
					TEXT("NightWater_T04 radial component: actor=%s component=%s material=%s visible=%d location=%s extent=%s scale=%s"),
					*DisplayLabel, *ComponentName,
					AppliedMaterial ? *AppliedMaterial->GetPathName() : TEXT("NULL"),
					MeshComponent->IsVisible() ? 1 : 0,
					*MeshComponent->GetComponentLocation().ToCompactString(),
					*MeshComponent->Bounds.BoxExtent.ToCompactString(),
					*MeshComponent->GetComponentScale().ToCompactString());
			}
			++UpdatedComponents;
		}
	}

	if (UpdatedComponents > 0)
	{
		UE_LOG(LogRedGameMode, Display,
			TEXT("EnsureSoStylizedOceanWater: applied %s to %d ocean/PlanetGen components"),
			bUsesWorldGenGlobalOcean ? TEXT("NightWater_T04 WorldGen global-ocean A/B")
			: (bNightWaterVisualTest ? TEXT("NightWater_T04 SoStylized fallback") : TEXT("production SoStylized water")),
			UpdatedComponents);
	}
}

void ARedGameMode::RemoveProceduralSurfaceDressing()
{
	UWorld* World = GetWorld();
	if (!World || !bSuppressProceduralSurfaceDressing)
	{
		return;
	}

	int32 RemovedActorCount = 0;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		AActor* Actor = *It;
		if (!IsProceduralSurfaceDressingActor(Actor))
		{
			continue;
		}
		DisableProceduralSurfaceDressingActor(Actor);
		++RemovedActorCount;
	}
	ProceduralBiomeField = nullptr;
	World->GetTimerManager().ClearTimer(OasisTerraformTimer);
	World->GetTimerManager().ClearTimer(ProceduralBiomeTimer);
	UE_LOG(LogRedGameMode, Display,
		TEXT("Desert/ocean cleanup disabled %d foliage/rock/cliff/snow dressing actors; terrain and water retained."),
		RemovedActorCount);
}

void ARedGameMode::EnsureProceduralBiomeField()
{
	// Compatibility entry point for old Blueprints: clean up instead of spawning surface dressing.
	RemoveProceduralSurfaceDressing();
	return;

	#if 0
	UWorld* World = GetWorld();
	if (!World || !HasAuthority())
	{
		return;
	}

	for (TActorIterator<ARedFoliageField> It(World); It; ++It)
	{
		if (IsValid(*It) && It->ActorHasTag(TEXT("RedProceduralBiomeField")))
		{
			ProceduralBiomeField = *It;
			return;
		}
	}

	AActor* Anchor = nullptr;
	for (TActorIterator<APlayerController> It(World); It; ++It)
	{
		if (IsValid(It->GetPawn()))
		{
			Anchor = It->GetPawn();
			break;
		}
	}
	if (!Anchor)
	{
		for (TActorIterator<APlayerStart> It(World); It; ++It)
		{
			Anchor = *It;
			break;
		}
	}

	FVector PlanetCenter;
	float DatumRadius = 0.f;
	if (!Anchor || !RedGravity::FindMeshPlanet(World, PlanetCenter, DatumRadius))
	{
		World->GetTimerManager().SetTimer(
			ProceduralBiomeTimer, this, &ARedGameMode::EnsureProceduralBiomeField, 2.f, false);
		return;
	}

	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	ProceduralBiomeField = World->SpawnActor<ARedFoliageField>(
		ARedFoliageField::StaticClass(), FTransform(FQuat::Identity, Anchor->GetActorLocation()), Params);
	if (ProceduralBiomeField)
	{
		ProceduralBiomeField->Tags.AddUnique(TEXT("RedProceduralBiomeField"));
	#if WITH_EDITOR
		ProceduralBiomeField->SetActorLabel(TEXT("RedProceduralBiomeField_LocalPlayableRegion"));
	#endif
		UE_LOG(LogRedGameMode, Display,
			TEXT("EnsureProceduralBiomeField: spawned bounded local biome field at %s (4458 max samples)"),
			*Anchor->GetActorLocation().ToCompactString());
	}
	#endif
}

void ARedGameMode::EnsureOasisTerraformingPockets()
{
	// Compatibility entry point for old maps: oceans remain, but rocks/ridges stay suppressed.
	RemoveProceduralSurfaceDressing();
	return;

	#if 0
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}

	auto RetryWhenPlanetCollisionIsReady = [&]()
	{
		World->GetTimerManager().SetTimer(
			OasisTerraformTimer, this, &ARedGameMode::EnsureOasisTerraformingPockets, 2.0f, false);
	};

	FVector PlanetCenter = FVector::ZeroVector;
	float DatumRadius = 0.f;
	float PeakRadius = 0.f;
	if (!RedGravity::FindMeshPlanet(World, PlanetCenter, DatumRadius, &PeakRadius)
		|| DatumRadius < 1000.f || PeakRadius <= DatumRadius)
	{
		// PlanetGen actors/chunks can arrive after BeginPlay. Keep trying rather than projecting the
		// oasis onto the deliberately underground gameplay datum.
		RetryWhenPlanetCollisionIsReady();
		return;
	}

	// Keep a concrete reference to the CLM planet so dressing traces cannot accidentally settle on
	// a saved water plane, parked ship, or previously spawned prop. FindMeshPlanet deliberately only
	// exposes center/radii, so resolve the reflected actor once here without taking a PlanetGen module
	// dependency.
	AActor* MeshPlanetActor = nullptr;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		for (const UClass* C = It->GetClass(); C; C = C->GetSuperClass())
		{
			if (C->GetName() == TEXT("CLMPlanet"))
			{
				MeshPlanetActor = *It;
				break;
			}
		}
		if (MeshPlanetActor)
		{
			break;
		}
	}
	if (!MeshPlanetActor)
	{
		RetryWhenPlanetCollisionIsReady();
		return;
	}

	// Anchor near PlayerStart / current pawn — beach/spawn proof pockets.
	FVector Anchor = FVector::ZeroVector;
	bool bHaveAnchor = false;
	{
		TActorIterator<APlayerStart> It(World);
		if (It)
		{
			Anchor = It->GetActorLocation();
			bHaveAnchor = true;
		}
	}
	if (!bHaveAnchor)
	{
		if (APlayerController* PC = World->GetFirstPlayerController())
		{
			if (APawn* Pawn = PC->GetPawn())
			{
				Anchor = Pawn->GetActorLocation();
				bHaveAnchor = true;
			}
		}
	}
	if (!bHaveAnchor)
	{
		// Basin attractor from prior handovers.
		Anchor = PlanetCenter + FVector(0.288f, 0.957f, 0.024f).GetSafeNormal() * PeakRadius;
	}

	const FVector Up = (Anchor - PlanetCenter).GetSafeNormal();
	FVector Tangent = FVector::CrossProduct(Up, FVector::UpVector).GetSafeNormal();
	if (Tangent.IsNearlyZero())
	{
		Tangent = FVector::CrossProduct(Up, FVector::ForwardVector).GetSafeNormal();
	}
	const FVector Bitangent = FVector::CrossProduct(Up, Tangent).GetSafeNormal();

	struct FSurfaceCandidate
	{
		FVector SurfaceDirection = FVector::ForwardVector;
		FVector Radial = FVector::UpVector;
		FHitResult Hit;
	};

	FCollisionObjectQueryParams SurfaceObjectTypes;
	SurfaceObjectTypes.AddObjectTypesToQuery(ECC_WorldStatic);
	SurfaceObjectTypes.AddObjectTypesToQuery(ECC_WorldDynamic);
	FCollisionQueryParams SurfaceQuery(SCENE_QUERY_STAT(RedOasisSurfaceTrace), false);

	auto IsPlanetTerrainActor = [MeshPlanetActor](const AActor* Candidate) -> bool
	{
		for (const AActor* Current = Candidate; IsValid(Current); )
		{
			if (Current == MeshPlanetActor)
			{
				return true;
			}
			for (const UClass* C = Current->GetClass(); C; C = C->GetSuperClass())
			{
				const FString ClassName = C->GetName();
				if (ClassName == TEXT("CLMPlanet")
					|| ClassName.Contains(TEXT("CLMChunk"))
					|| ClassName.Contains(TEXT("PlanetChunk"))
					|| ClassName.Contains(TEXT("TerrainChunk")))
				{
					return true;
				}
			}

			const AActor* Next = Current->GetOwner();
			if (!IsValid(Next))
			{
				Next = Current->GetAttachParentActor();
			}
			if (Next == Current)
			{
				break;
			}
			Current = Next;
		}
		return false;
	};

	auto TracePlanetSurface = [&](const FVector& CandidateLocation, FSurfaceCandidate& OutCandidate) -> bool
	{
		OutCandidate.Radial = (CandidateLocation - PlanetCenter).GetSafeNormal();
		if (OutCandidate.Radial.IsNearlyZero())
		{
			return false;
		}

		const FVector TraceStart = PlanetCenter + OutCandidate.Radial * (PeakRadius + 5000.f);
		const FVector TraceEnd = PlanetCenter + OutCandidate.Radial * DatumRadius;
		FCollisionQueryParams FilteredQuery = SurfaceQuery;
		for (int32 Attempt = 0; Attempt < 16; ++Attempt)
		{
			FHitResult Hit;
			if (!World->LineTraceSingleByObjectType(
				Hit, TraceStart, TraceEnd, SurfaceObjectTypes, FilteredQuery))
			{
				return false;
			}
			if (Hit.bBlockingHit && IsPlanetTerrainActor(Hit.GetActor()))
			{
				OutCandidate.Hit = Hit;
				return true;
			}

			// Object traces stop at the first blocker. Peel unrelated blockers one actor/component at a
			// time so saved water, ships, and props cannot become the terrain support or hide it.
			if (AActor* BlockingActor = Hit.GetActor())
			{
				FilteredQuery.AddIgnoredActor(BlockingActor);
			}
			else if (UPrimitiveComponent* BlockingComponent = Hit.GetComponent())
			{
				FilteredQuery.AddIgnoredComponent(BlockingComponent);
			}
			else
			{
				return false;
			}
		}
		return false;
	};

	// Resolve every pocket and dune against live PlanetGen collision before spawning anything. If a
	// streaming chunk is not collision-ready yet, this avoids leaving one tagged partial oasis that
	// would suppress all later retries.
	const float PocketOffsetsCm[] = { 1800.f, -2200.f, 3200.f };
	const float PocketAnglesDeg[] = { 25.f, -55.f, 110.f };
	FSurfaceCandidate PocketCandidates[UE_ARRAY_COUNT(PocketOffsetsCm)];
	for (int32 i = 0; i < UE_ARRAY_COUNT(PocketOffsetsCm); ++i)
	{
		const float Ang = PocketAnglesDeg[i];
		PocketCandidates[i].SurfaceDirection =
			(Tangent * FMath::Cos(FMath::DegreesToRadians(Ang))
				+ Bitangent * FMath::Sin(FMath::DegreesToRadians(Ang))).GetSafeNormal();
		const FVector CandidateLocation = Anchor + PocketCandidates[i].SurfaceDirection * PocketOffsetsCm[i];
		if (!TracePlanetSurface(CandidateLocation, PocketCandidates[i]))
		{
			RetryWhenPlanetCollisionIsReady();
			return;
		}
	}

	// Replace the old project rectangle with an organic carrier mesh and the installed SoStylized
	// clear-water material.  Planetary water must remain level with radial gravity; aligning it to a
	// dune normal made the plane pass through the third-person camera.  The slope-aware inward offset
	// clips the irregular shoreline into the sand instead of exposing a floating edge.
	TArray<AStaticMeshActor*> OasisWaterActors;
	for (TActorIterator<AStaticMeshActor> It(World); It; ++It)
	{
		if (It->ActorHasTag(TEXT("RedOasisWater"))
			|| It->GetActorNameOrLabel().Contains(TEXT("RedOasisWater")))
		{
			OasisWaterActors.Add(*It);
		}
	}
	OasisWaterActors.Sort([](const AStaticMeshActor& A, const AStaticMeshActor& B)
	{
		return A.GetActorNameOrLabel() < B.GetActorNameOrLabel();
	});

	const FVector2D DesiredPoolHalfExtents[] = {
		FVector2D(500.f, 380.f),
		FVector2D(430.f, 330.f),
		FVector2D(470.f, 350.f),
	};
	int32 RepairedWaterCount = 0;
	UMaterialInterface* ActiveWaterMaterial = ResolveSoStylizedWaterMaterialForCurrentMap();
	if (SoStylizedWaterMesh && ActiveWaterMaterial)
	{
		const FVector SourceExtent = SoStylizedWaterMesh->GetBounds().BoxExtent.ComponentMax(FVector(1.f));
		for (int32 i = 0; i < UE_ARRAY_COUNT(PocketCandidates); ++i)
		{
			AStaticMeshActor* WaterActor = OasisWaterActors.IsValidIndex(i) ? OasisWaterActors[i] : nullptr;
			if (!WaterActor)
			{
				FActorSpawnParameters Params;
				Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
				WaterActor = World->SpawnActor<AStaticMeshActor>(AStaticMeshActor::StaticClass(),
					FTransform::Identity, Params);
				if (!WaterActor)
				{
					continue;
				}
			#if WITH_EDITOR
				WaterActor->SetActorLabel(*FString::Printf(TEXT("RedOasisWater_%d"), i));
			#endif
			}

			WaterActor->Tags.AddUnique(TEXT("RedOasisWater"));
			WaterActor->SetMobility(EComponentMobility::Movable);
			UStaticMeshComponent* WaterComponent = WaterActor->GetStaticMeshComponent();
			if (!WaterComponent)
			{
				continue;
			}
			WaterComponent->SetMobility(EComponentMobility::Movable);
			WaterComponent->SetStaticMesh(SoStylizedWaterMesh);
			if (UMaterialInstanceDynamic* WaterDMI = WaterComponent->CreateDynamicMaterialInstance(
				0, ActiveWaterMaterial))
			{
				WaterDMI->SetVectorParameterValue(TEXT("Emissive Color"), FLinearColor::Black);
			}
			else
			{
				WaterComponent->SetMaterial(0, ActiveWaterMaterial);
			}
			WaterComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			WaterComponent->SetGenerateOverlapEvents(false);
			WaterComponent->SetCastShadow(false);
			WaterComponent->SetReceivesDecals(false);
			WaterComponent->ComponentTags.AddUnique(TEXT("RedSoStylizedWaterApplied"));

			const FSurfaceCandidate& Candidate = PocketCandidates[i];
			const FVector WaterUp = Candidate.Radial;
			FVector WaterForward = FVector::VectorPlaneProject(Candidate.SurfaceDirection, WaterUp).GetSafeNormal();
			if (WaterForward.IsNearlyZero())
			{
				WaterForward = Tangent;
			}
			const FVector2D TargetExtent = DesiredPoolHalfExtents[i];
			const FVector WaterScale(
				TargetExtent.X / SourceExtent.X,
				TargetExtent.Y / SourceExtent.Y,
				1.f);
			const FVector TerrainNormal = Candidate.Hit.ImpactNormal.GetSafeNormal();
			const float SlopeCos = FMath::Clamp(FVector::DotProduct(TerrainNormal, WaterUp), 0.2f, 1.f);
			const float SlopeTangent = FMath::Sqrt(FMath::Max(0.f, 1.f - SlopeCos * SlopeCos)) / SlopeCos;
			const float ShorelineInsetCm = FMath::Clamp(
				18.f + SlopeTangent * FMath::Min(TargetExtent.X, TargetExtent.Y) * 0.45f,
				25.f, 110.f);
			WaterActor->SetActorTransform(FTransform(
				FRotationMatrix::MakeFromZX(WaterUp, WaterForward).ToQuat(),
				Candidate.Hit.ImpactPoint - WaterUp * ShorelineInsetCm,
				WaterScale), false, nullptr, ETeleportType::TeleportPhysics);
			WaterComponent->MarkRenderStateDirty();
			++RepairedWaterCount;
		}
	}

	EnsureSoStylizedOceanWater();
	UE_LOG(LogRedGameMode, Display,
		TEXT("EnsureOasisTerraformingPockets: level-seated %d organic SoStylized water pools"),
		RepairedWaterCount);

	// Saved rock actors count as an already-built dressing set, but never bypass the water repair above.
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		if (It->ActorHasTag(TEXT("RedOasisPocket")))
		{
			return;
		}
	}

	// Every rock gets its own PlanetGen trace. Offsetting tangent to a single center hit looked fine
	// on a flat test map, but on real relief it left rocks hovering or buried on sloped basin edges.
	constexpr int32 RocksPerPocket = 2;
	FSurfaceCandidate RockCandidates[UE_ARRAY_COUNT(PocketOffsetsCm)][RocksPerPocket];
	for (int32 i = 0; i < UE_ARRAY_COUNT(PocketOffsetsCm); ++i)
	{
		for (int32 r = 0; r < RocksPerPocket; ++r)
		{
			const FVector RockDirection =
				(PocketCandidates[i].SurfaceDirection.RotateAngleAxis(40.f + r * 70.f, PocketCandidates[i].Radial))
				.GetSafeNormal();
			RockCandidates[i][r].SurfaceDirection = RockDirection;
			const FVector CandidateLocation =
				PocketCandidates[i].Hit.ImpactPoint + RockDirection * (280.f + r * 90.f);
			if (!TracePlanetSurface(CandidateLocation, RockCandidates[i][r]))
			{
				RetryWhenPlanetCollisionIsReady();
				return;
			}
		}
	}

	FSurfaceCandidate DuneCandidates[4];
	for (int32 d = 0; d < UE_ARRAY_COUNT(DuneCandidates); ++d)
	{
		const float Ang = 40.f + d * 55.f;
		DuneCandidates[d].SurfaceDirection =
			(Tangent * FMath::Cos(FMath::DegreesToRadians(Ang))
				+ Bitangent * FMath::Sin(FMath::DegreesToRadians(Ang))).GetSafeNormal();
		const FVector CandidateLocation = Anchor + DuneCandidates[d].SurfaceDirection * (4500.f + d * 900.f);
		if (!TracePlanetSurface(CandidateLocation, DuneCandidates[d]))
		{
			RetryWhenPlanetCollisionIsReady();
			return;
		}
	}

	UStaticMesh* RockMeshes[] = {
		LoadObject<UStaticMesh>(nullptr, TEXT("/Game/StylizedDesertOasis/Meshes/Rocks/SM_Rock_01.SM_Rock_01")),
		LoadObject<UStaticMesh>(nullptr, TEXT("/Game/StylizedDesertOasis/Meshes/Rocks/SM_Boulder_02.SM_Boulder_02")),
		LoadObject<UStaticMesh>(nullptr, TEXT("/Game/StylizedDesertOasis/Meshes/Rocks/SM_SmallRock_01.SM_SmallRock_01")),
	};
	UStaticMesh* DuneMeshes[] = {
		LoadObject<UStaticMesh>(nullptr, TEXT("/Game/SoStylized/Environment/Rocks/Desert/SM_RockDesert_Shelf01.SM_RockDesert_Shelf01")),
		LoadObject<UStaticMesh>(nullptr, TEXT("/Game/SoStylized/Environment/Rocks/Desert/SM_RockDesert_Shelf02.SM_RockDesert_Shelf02")),
	};

	auto SpawnMesh = [&](UStaticMesh* Mesh, const FVector& Loc, const FRotator& Rot, float Scale,
		UMaterialInterface* MatOverride, const TCHAR* Label) -> AStaticMeshActor*
	{
		if (!Mesh) { return nullptr; }
		FActorSpawnParameters Params;
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		// Let the level assign the UObject name. MakeUniqueObjectName(World, ...) uses the
		// wrong outer for actors (their outer is the level), so repeated PIE sessions can
		// return an already-taken name and UE 5.8 fatals while spawning the oasis.
		AStaticMeshActor* A = World->SpawnActor<AStaticMeshActor>(Loc, Rot, Params);
		if (!A) { return nullptr; }
		A->Tags.Add(TEXT("RedOasisPocket"));
	#if WITH_EDITOR
		A->SetActorLabel(Label);
	#endif
		A->SetMobility(EComponentMobility::Movable);
		if (UStaticMeshComponent* SMC = A->GetStaticMeshComponent())
		{
			SMC->SetMobility(EComponentMobility::Movable);
			SMC->SetStaticMesh(Mesh);
			SMC->SetWorldScale3D(FVector(Scale));
			SMC->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
			SMC->SetCastShadow(true);
			if (MatOverride)
			{
				SMC->SetMaterial(0, MatOverride);
			}
		}
		return A;
	};

	int32 Spawned = 0;
	// Three terraforming pockets around spawn (rocks only). The former scaled plane
	// water meshes rendered as opaque black slabs on PlanetGen, so water stays omitted
	// until a planet-conforming translucent solution is available.
	for (int32 i = 0; i < UE_ARRAY_COUNT(PocketCandidates); ++i)
	{
		// Each rock uses its own terrain hit so the transform follows local relief.
		for (int32 r = 0; r < RocksPerPocket; ++r)
		{
			const FSurfaceCandidate& RockCandidate = RockCandidates[i][r];
			const FVector RockLoc = RockCandidate.Hit.ImpactPoint + RockCandidate.Radial * 8.f;
			const FRotator RockRot = FRotationMatrix::MakeFromZX(
				RockCandidate.Radial, RockCandidate.SurfaceDirection).Rotator();
			if (SpawnMesh(RockMeshes[(i + r) % UE_ARRAY_COUNT(RockMeshes)], RockLoc, RockRot,
				1.05f + 0.12f * static_cast<float>((i + r) % 3), nullptr,
				*FString::Printf(TEXT("RedOasisRock_%d_%d"), i, r)))
			{
				++Spawned;
			}
		}
	}

	// A few broad SoStylized desert silhouettes near spawn (real meshes, not UV stripes).
	for (int32 d = 0; d < UE_ARRAY_COUNT(DuneCandidates); ++d)
	{
		const FVector& Dir = DuneCandidates[d].SurfaceDirection;
		const FVector& Radial = DuneCandidates[d].Radial;
		const FVector DuneLoc = DuneCandidates[d].Hit.ImpactPoint + Radial * 30.f;
		const FRotator Rot = FRotationMatrix::MakeFromZX(Radial, Dir).Rotator();
		UStaticMesh* Dune = DuneMeshes[d % 2];
		// Prefer authored dune materials; only force biome sand if mesh has no usable mat.
		if (SpawnMesh(Dune, DuneLoc, Rot, 2.5f + d * 0.4f, nullptr,
			*FString::Printf(TEXT("RedMarsDune_%d"), d)))
		{
			++Spawned;
		}
	}

	UE_LOG(LogRedGameMode, Display,
		TEXT("EnsureOasisTerraformingPockets: spawned %d PlanetGen-conforming actors (3 rock clusters + 4 desert ridges; no palms/runtime water) near %s"),
		Spawned, *Anchor.ToCompactString());
	#endif
}

void ARedGameMode::EnsureSkyLight()
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}

	auto Configure = [](USkyLightComponent* SkyComp)
	{
		if (!SkyComp) { return; }
		// Movable + real-time capture = ambient tracks the SkyAtmosphere (fixes silhouette pawns).
		SkyComp->SetMobility(EComponentMobility::Movable);
		SkyComp->bRealTimeCapture = true;
		SkyComp->bLowerHemisphereIsBlack = false;
		// Use an exact bounded ambient level. Taking Max against serialized demo values
		// let an old bright SkyLight bleach the entire night hemisphere tan from orbit.
		SkyComp->SetIntensity(0.65f);
		SkyComp->SetIndirectLightingIntensity(0.55f);
		SkyComp->SetVolumetricScatteringIntensity(0.20f);
		SkyComp->MarkRenderStateDirty();
	};

	bool bFound = false;
	for (TActorIterator<ASkyLight> It(World); It; ++It)
	{
		Configure(It->GetLightComponent());
		bFound = true;
	}
	if (!bFound)
	{
		FActorSpawnParameters Params;
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		ASkyLight* Sky = World->SpawnActor<ASkyLight>(ASkyLight::StaticClass(), FTransform::Identity, Params);
		Configure(Sky ? Sky->GetLightComponent() : nullptr);
	}

	ARedDayNight* NightFill = nullptr;
	for (TActorIterator<ARedDayNight> It(World); It; ++It)
	{
		if (IsValid(*It))
		{
			NightFill = *It;
			break;
		}
	}
	if (!NightFill)
	{
		FActorSpawnParameters Params;
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		NightFill = World->SpawnActor<ARedDayNight>(
			ARedDayNight::StaticClass(), FTransform::Identity, Params);
	}
	if (NightFill && NightFill->MoonLight)
	{
		NightFill->Tags.AddUnique(TEXT("RedNightFill"));
		// Reassert the two-hour cycle here so a serialized map actor cannot retain the
		// old accelerated test value after the native default changes.
		NightFill->DayLengthSeconds = 7200.f;
		// Match ARedDayNight's native fill even when an older serialized map actor is reused.
		// This is deliberately below the capped 3.0-lux sun: night remains night, but the
		// dark hemisphere and non-emissive ocean are no longer near-black with Lumen disabled.
		NightFill->MoonLight->SetIntensity(0.85f);
		NightFill->MoonLight->SetLightColor(FLinearColor(0.48f, 0.60f, 0.92f));
		NightFill->MoonLight->SetIndirectLightingIntensity(0.55f);
		NightFill->MoonLight->SetVolumetricScatteringIntensity(0.18f);
		NightFill->MoonLight->SetCastShadows(false);
		NightFill->MoonLight->SetAtmosphereSunLight(false);
		NightFill->MoonLight->MarkRenderStateDirty();
		NightFill->ForceNetUpdate();
		UE_LOG(LogRedGameMode, Display,
			TEXT("EnsureSkyLight: coherent moon fill intensity=%.2f indirect=%.2f volumetric=%.2f"),
			NightFill->MoonLight->Intensity,
			NightFill->MoonLight->IndirectLightingIntensity,
			NightFill->MoonLight->VolumetricScatteringIntensity);
	}

	// Surface-only maps still need the visible moon and night star shell. Vehicles also call
	// this helper, but GameMode is the unconditional authoritative owner of world presentation.
	ARedSpaceScenery::EnsureForWorld(World, FVector::ZeroVector);
}

void ARedGameMode::EnsureHighFiveCloudVolumes(
	const FVector& PlanetCenter, float PlanetRadiusCm, float PlanetPeakRadiusCm,
	float AtmosphereHeightCm)
{
	UWorld* World = GetWorld();
	if (!World || PlanetRadiusCm < 1000.f || PlanetPeakRadiusCm < PlanetRadiusCm
		|| AtmosphereHeightCm < 1000.f || HighFiveCloudMaterials.Num() < 12)
	{
		return;
	}
	// Sparse-volume textures report unstable first-frame bounds while their first
	// streaming mip is being resolved. Keep them hidden through the initial pass
	// and first timed retry; revealing tiny warm-up volumes caused the coloured
	// dots/specks seen in the packaged surface test.
	const bool bWarmSettledClouds = AtmosphereCloudRetryCount >= 3;
	const bool bRevealSettledClouds = AtmosphereCloudRetryCount >= 4;

	struct FCloudPreset
	{
		const TCHAR* Name;
		FVector PlanetDirection;
		float NominalCenterAltitudeCm;
		float MinimumBaseClearanceCm;
		float YawDegrees;
	};
	const FCloudPreset Presets[] = {
		// The twelve vertices of an icosahedron provide deterministic, near-uniform spherical
		// coverage. Equal scale/altitude prevents a spawn-side megabank while each hemisphere
		// still has several readable, separated cloud masses.
		// One offset polar bank per hemisphere guarantees visible high-latitude
		// coverage without stacking several actors over the +Z player spawn.
		// These first two preserve the global deck while guaranteeing two separate
		// readable banks in the fused spawn's initial -Y view after the phase rotation.
		{ TEXT("Violet_0PP"), FVector( 0.35414f, -0.16513f, 0.92050f), 122000.f, 12000.f, -18.f },
		{ TEXT("Cyan_0NP"),   FVector( 0.40451f,  0.20611f, 0.89101f), 122000.f, 12000.f,  27.f },
		{ TEXT("Gold_0PN"),   FVector( 0.f,  1.f, -1.618034f), 122000.f, 12000.f,  63.f },
		{ TEXT("Rose_0NN"),   FVector(-0.259f, 0.f, -0.966f), 122000.f, 12000.f, -54.f },
		{ TEXT("Violet_P0P"), FVector( 1.f,  1.618034f, 0.f), 122000.f, 12000.f,  38.f },
		{ TEXT("Cyan_N0P"),   FVector(-1.f,  1.618034f, 0.f), 122000.f, 12000.f, -31.f },
		{ TEXT("Gold_P0N"),   FVector( 1.f, -1.618034f, 0.f), 122000.f, 12000.f,  74.f },
		{ TEXT("Rose_N0N"),   FVector(-1.f, -1.618034f, 0.f), 122000.f, 12000.f, -67.f },
		{ TEXT("Violet_PP0"), FVector( 1.618034f, 0.f,  1.f), 122000.f, 12000.f,  14.f },
		{ TEXT("Cyan_NP0"),   FVector(-1.618034f, 0.f,  1.f), 122000.f, 12000.f, -42.f },
		{ TEXT("Gold_PN0"),   FVector( 1.618034f, 0.f, -1.f), 122000.f, 12000.f,  51.f },
		{ TEXT("Rose_NN0"),   FVector(-1.618034f, 0.f, -1.f), 122000.f, 12000.f, -76.f },
	};
	// These are a restrained presentation grade for the actual HI-5 material instances,
	// not replacement meshes or a generic cloud shader.  The pack's VDB breakup remains
	// intact; this prevents the scene's high-lux sun plus blackbody emission from reducing
	// every authored cyan/gold/rose/violet bank to the same charcoal silhouette.
	const FLinearColor CloudScatteringColors[] = {
		FLinearColor(0.78f, 0.34f, 1.00f), // violet
		FLinearColor(0.25f, 0.95f, 1.00f), // cyan
		FLinearColor(1.00f, 0.72f, 0.22f), // gold
		FLinearColor(1.00f, 0.30f, 0.62f), // rose
	};
	const FLinearColor CloudAbsorptionColors[] = {
		FLinearColor(0.12f, 0.03f, 0.20f),
		FLinearColor(0.02f, 0.15f, 0.18f),
		FLinearColor(0.20f, 0.10f, 0.01f),
		FLinearColor(0.22f, 0.02f, 0.08f),
	};

	// RedPlanetGen already contains four authored HeterogeneousVolume actors. Earlier
	// builds failed to recognize their generic map names and spawned four more copies,
	// leaving the original dots in the sky. Adopt those actors by stable name order for
	// the first four placements, then spawn only the additional coverage volumes.
	TArray<AHeterogeneousVolume*> AvailableMapVolumes;
	for (TActorIterator<AHeterogeneousVolume> It(World); It; ++It)
	{
		if (IsValid(*It))
		{
			AvailableMapVolumes.Add(*It);
		}
	}
	AvailableMapVolumes.Sort([](const AHeterogeneousVolume& A, const AHeterogeneousVolume& B)
	{
		return A.GetName() < B.GetName();
	});

	TSet<AHeterogeneousVolume*> ClaimedVolumes;
	HighFiveCloudVolumes.SetNum(UE_ARRAY_COUNT(Presets));
	int32 ConfiguredCount = 0;
	int32 NorthernCloudCount = 0;
	int32 SouthernCloudCount = 0;
	int32 EquatorialCloudCount = 0;
	float MinimumObservedBaseClearanceCm = BIG_NUMBER;
	float MinimumObservedTopClearanceCm = BIG_NUMBER;
	for (int32 Index = 0; Index < UE_ARRAY_COUNT(Presets); ++Index)
	{
		if (!HighFiveCloudMaterials[Index])
		{
			continue;
		}

		const FString DesiredLabel = FString::Printf(TEXT("RedHi5Cloud_%s"), Presets[Index].Name);
		AHeterogeneousVolume* Volume = nullptr;
		for (TActorIterator<AHeterogeneousVolume> It(World); It; ++It)
		{
			if (It->GetActorNameOrLabel().Contains(DesiredLabel)
				|| It->ActorHasTag(FName(*DesiredLabel)))
			{
				Volume = *It;
				break;
			}
		}
		if (Volume)
		{
			ClaimedVolumes.Add(Volume);
		}
		if (!Volume)
		{
			for (AHeterogeneousVolume* Candidate : AvailableMapVolumes)
			{
				if (IsValid(Candidate) && !ClaimedVolumes.Contains(Candidate))
				{
					Volume = Candidate;
					ClaimedVolumes.Add(Volume);
					break;
				}
			}
		}
		if (!Volume)
		{
			FActorSpawnParameters Params;
			Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			Volume = World->SpawnActor<AHeterogeneousVolume>(
				AHeterogeneousVolume::StaticClass(), FTransform::Identity, Params);
			if (!Volume)
			{
				continue;
			}
			ClaimedVolumes.Add(Volume);
		#if WITH_EDITOR
			Volume->SetActorLabel(DesiredLabel);
		#endif
		}

		Volume->Tags.AddUnique(TEXT("RedHi5Cloud"));
		Volume->Tags.AddUnique(FName(*DesiredLabel));
		// The map owns four persistent volumes, so enable movement replication on those
		// exact level actors. This carries the authoritative transform to clients instead
		// of leaving them at the old saved-map positions while only the server moves them.
		Volume->SetReplicates(true);
		Volume->SetReplicateMovement(true);
		Volume->bAlwaysRelevant = true;
		Volume->SetNetUpdateFrequency(1.f);

		// Rotate the uniform icosahedral distribution so the closest polar bank sits
		// in the fused prototype's initial -Y view instead of 90 degrees off-camera.
		// The global coverage is unchanged; only the phase around the planet changes.
		const FVector CloudDirection = Presets[Index].PlanetDirection
			.RotateAngleAxis(-90.f, FVector::UpVector).GetSafeNormal();
		FVector CloudForward = FVector::CrossProduct(FVector::UpVector, CloudDirection).GetSafeNormal();
		if (CloudForward.IsNearlyZero())
		{
			CloudForward = FVector::ForwardVector;
		}

		if (UHeterogeneousVolumeComponent* CloudComponent =
			Volume->FindComponentByClass<UHeterogeneousVolumeComponent>())
		{
			MakeAtmosphereAttachmentChainMovable(CloudComponent);
			if (!HighFiveCloudDynamicMaterials[Index])
			{
				HighFiveCloudDynamicMaterials[Index] = UMaterialInstanceDynamic::Create(
					HighFiveCloudMaterials[Index], this);
			}
			UMaterialInstanceDynamic* CloudMaterial =
				HighFiveCloudDynamicMaterials[Index];
			if (CloudMaterial)
			{
				// Only override presentation parameters. Input SVT, temperature and
				// remap controls are inherited intact from the authored HI5 instance.
				// Keep the authored VDB breakup while giving each globally distributed
				// bank enough optical depth to read as a cloud. The previous 0.20 value
				// drove multiple scattering toward opaque grey in direct daylight.
				// Retry three makes the zero-density volume render-relevant so its SVT
				// streams without showing a tiny speck.  The settled state uses the HI-5
				// overview's MI_006 density: readable at the initial daylight spawn while
				// the twelve-bank layout still prevents an opaque spawn cloud bank.
				CloudMaterial->SetScalarParameterValue(
					TEXT("Density Multiplier"), bRevealSettledClouds ? 0.08f : 0.f);
				// Preserve the HI-5 SVT, temperature and remap controls, but grade the
				// scattering/absorption palette explicitly.  This keeps the world-space
				// HI-5 VDBs while producing readable colored cloud banks in the fused
				// planet's daylight rather than charcoal silhouettes.
				const int32 PaletteIndex = Index % UE_ARRAY_COUNT(CloudScatteringColors);
				CloudMaterial->SetVectorParameterValue(
					TEXT("Scattering Color"), CloudScatteringColors[PaletteIndex]);
				CloudMaterial->SetVectorParameterValue(
					TEXT("Absorption Color"), CloudAbsorptionColors[PaletteIndex]);
				CloudMaterial->SetScalarParameterValue(TEXT("Blackbody Multiplier"), 0.15f);
				CloudComponent->SetMaterial(0, CloudMaterial);
			}
			else
			{
				CloudComponent->SetMaterial(0, HighFiveCloudMaterials[Index]);
			}

			// The four VDBs do not share an up axis or dimensions. Determine the physically
			// thinnest transformed frame axis and map that to radial up, leaving the two broad
			// axes tangent to the planet. This keeps the cloud masses large without allowing
			// their long side to intersect terrain or extend beyond the atmosphere shell.
			const FVector HalfResolution = FVector(CloudComponent->VolumeResolution) * 0.5f;
			const FVector FrameHalfAxes[] = {
				CloudComponent->FrameTransform.TransformVector(FVector::ForwardVector) * HalfResolution.X,
				CloudComponent->FrameTransform.TransformVector(FVector::RightVector) * HalfResolution.Y,
				CloudComponent->FrameTransform.TransformVector(FVector::UpVector) * HalfResolution.Z,
			};
			int32 ThinAxis = 0;
			int32 BroadAxis = 1;
			for (int32 Axis = 1; Axis < UE_ARRAY_COUNT(FrameHalfAxes); ++Axis)
			{
				if (FrameHalfAxes[Axis].SizeSquared() < FrameHalfAxes[ThinAxis].SizeSquared())
				{
					ThinAxis = Axis;
				}
			}
			for (int32 Axis = 0; Axis < UE_ARRAY_COUNT(FrameHalfAxes); ++Axis)
			{
				if (Axis != ThinAxis
					&& (BroadAxis == ThinAxis
						|| FrameHalfAxes[Axis].SizeSquared() > FrameHalfAxes[BroadAxis].SizeSquared()))
				{
					BroadAxis = Axis;
				}
			}
			// The four HI-5 VDBs have very different baked voxel scales. A single
			// uniform actor scale made violet/cyan tiny while gold/rose became huge.
			// Normalize every preset to a readable regional bank, not a continent-sized
			// wall. On the 50 km-circumference world a 6.5 km VDB protruded far beyond
			// the planet silhouette in orbit. V4C then showed 2.2 km banks filling the
			// upper surface frame, so use compact 0.9 km regional masses; twelve banks
			// still provide global coverage without recreating a continuous dark deck.
			constexpr float TargetLongestTangentExtentCm = 90000.f;
			constexpr float TargetRadialThicknessCm = 20000.f;
			FVector AppliedScale(TargetLongestTangentExtentCm /
				FMath::Max(2.f * FrameHalfAxes[BroadAxis].Size(), 1.f));
			AppliedScale[ThinAxis] = TargetRadialThicknessCm /
				FMath::Max(2.f * FrameHalfAxes[ThinAxis].Size(), 1.f);
			const FVector LocalThinDirection = FrameHalfAxes[ThinAxis].GetSafeNormal();
			FVector LocalBroadDirection = FVector::VectorPlaneProject(
				FrameHalfAxes[BroadAxis], LocalThinDirection).GetSafeNormal();
			if (LocalBroadDirection.IsNearlyZero())
			{
				LocalBroadDirection = FVector::CrossProduct(
					LocalThinDirection, FVector::ForwardVector).GetSafeNormal();
			}
			CloudForward = CloudForward.RotateAngleAxis(
				Presets[Index].YawDegrees - 90.f, CloudDirection);
			const FQuat LocalFrameBasis =
				FRotationMatrix::MakeFromZX(LocalThinDirection, LocalBroadDirection).ToQuat();
			const FQuat WorldCloudBasis =
				FRotationMatrix::MakeFromZX(CloudDirection, CloudForward).ToQuat();
			const FQuat CloudRotation =
				(WorldCloudBasis * LocalFrameBasis.Inverse()).GetNormalized();

			const float NominalCloudRadius = PlanetRadiusCm + Presets[Index].NominalCenterAltitudeCm;
			Volume->SetActorTransform(FTransform(
				CloudRotation,
				PlanetCenter + CloudDirection * NominalCloudRadius,
				AppliedScale), false, nullptr, ETeleportType::TeleportPhysics);
			CloudComponent->UpdateBounds();

			// The High Five assets have different SVT frame bounds and a non-centred pivot.
			// Measure each transformed oriented box in the radial frame; this avoids the much
			// larger world-axis AABB that would push a broad tangent cloud out into space.
			auto MeasureRadialBounds = [&]()
			{
				struct FRadialBounds
				{
					float CenterRadius = 0.f;
					float HalfExtent = 0.f;
					float InnerRadius = 0.f;
					float OuterRadius = 0.f;
				};

				FRadialBounds Result;
				const FVector HalfResolution = FVector(CloudComponent->VolumeResolution) * 0.5f;
				const FVector LocalCenter = CloudComponent->bPivotAtCentroid
					? FVector::ZeroVector : HalfResolution;
				const FTransform VolumeToWorld =
					CloudComponent->FrameTransform * CloudComponent->GetComponentTransform();
				// Exact point-to-oriented-box distance. Sampling only the eight corners
				// overestimated the inner radius for broad tangent clouds because the
				// inward face centre is closer to the planet than any corner.
				const FVector LocalMinimum = LocalCenter - HalfResolution;
				const FVector LocalMaximum = LocalCenter + HalfResolution;
				const FVector PlanetCenterInVolume =
					VolumeToWorld.InverseTransformPosition(PlanetCenter);
				const FVector ClosestLocalPoint(
					FMath::Clamp(PlanetCenterInVolume.X, LocalMinimum.X, LocalMaximum.X),
					FMath::Clamp(PlanetCenterInVolume.Y, LocalMinimum.Y, LocalMaximum.Y),
					FMath::Clamp(PlanetCenterInVolume.Z, LocalMinimum.Z, LocalMaximum.Z));
				Result.InnerRadius = static_cast<float>((
					VolumeToWorld.TransformPosition(ClosestLocalPoint) - PlanetCenter).Size());
				for (int32 CornerIndex = 0; CornerIndex < 8; ++CornerIndex)
				{
					const FVector LocalCorner = LocalCenter + FVector(
						(CornerIndex & 1) ? HalfResolution.X : -HalfResolution.X,
						(CornerIndex & 2) ? HalfResolution.Y : -HalfResolution.Y,
						(CornerIndex & 4) ? HalfResolution.Z : -HalfResolution.Z);
					const float CornerRadius = static_cast<float>(
						(VolumeToWorld.TransformPosition(LocalCorner) - PlanetCenter).Size());
					Result.OuterRadius = FMath::Max(Result.OuterRadius, CornerRadius);
				}
				Result.CenterRadius = (Result.InnerRadius + Result.OuterRadius) * 0.5f;
				Result.HalfExtent = (Result.OuterRadius - Result.InnerRadius) * 0.5f;
				return Result;
			};

			const float RequiredInnerRadius =
				PlanetPeakRadiusCm + Presets[Index].MinimumBaseClearanceCm;
			// Clouds occupy the lower part of the thin rendered shell. The separate
			// eight-kilometre gameplay ascent is not a cloud-placement volume; putting
			// VDBs at its midpoint made them look detached in space on this small planet.
			constexpr float AtmosphereTopClearanceCm = 12000.f;
			constexpr float CloudDeckTopAltitudeCm = 280000.f;
			const float MaximumCloudAltitudeCm = FMath::Min(
				CloudDeckTopAltitudeCm,
				FMath::Max(AtmosphereHeightCm - AtmosphereTopClearanceCm, 0.f));
			const float MaximumOuterRadius = PlanetRadiusCm + MaximumCloudAltitudeCm;
			if (MaximumOuterRadius <= RequiredInnerRadius + 1000.f)
			{
				UE_LOG(LogRedGameMode, Warning,
					TEXT("HighFive cloud %s hidden: invalid atmosphere slab inner=%.0f outer=%.0f"),
					Presets[Index].Name, RequiredInnerRadius, MaximumOuterRadius);
				CloudComponent->SetVisibility(false, true);
				Volume->SetActorHiddenInGame(true);
				continue;
			}

			auto FittedBounds = MeasureRadialBounds();
			const float MaximumHalfExtent =
				(MaximumOuterRadius - RequiredInnerRadius) * 0.5f;
			for (int32 FitAttempt = 0;
				FitAttempt < 3 && FittedBounds.HalfExtent > MaximumHalfExtent
					&& FittedBounds.HalfExtent > 1.f;
				++FitAttempt)
			{
				// Radial thickness is already normalized. If planetary curvature still makes
				// the oriented box too deep, reduce only its two tangent axes; never collapse
				// the authored cloud vertically or return it to a tiny speck.
				const float FitRatio = FMath::Clamp(
					(MaximumHalfExtent / FittedBounds.HalfExtent) * 0.96f, 0.01f, 1.f);
				for (int32 Axis = 0; Axis < 3; ++Axis)
				{
					if (Axis != ThinAxis)
					{
						AppliedScale[Axis] *= FitRatio;
					}
				}
				Volume->SetActorScale3D(AppliedScale);
				CloudComponent->UpdateBounds();
				FittedBounds = MeasureRadialBounds();
			}

			// Preserve the authored lower-atmosphere deck instead of forcing every bank
			// to the midpoint of the full legal slab. Clamp the nominal 1.22 km centre
			// only when the transformed VDB bounds require additional clearance.
			const float MinimumCenterRadius = RequiredInnerRadius + FittedBounds.HalfExtent;
			const float MaximumCenterRadius = MaximumOuterRadius - FittedBounds.HalfExtent;
			const float TargetCenterRadius = FMath::Clamp(
				NominalCloudRadius, MinimumCenterRadius, MaximumCenterRadius);
			Volume->AddActorWorldOffset(
				CloudDirection * (TargetCenterRadius - FittedBounds.CenterRadius),
				false, nullptr, ETeleportType::TeleportPhysics);
			CloudComponent->UpdateBounds();
			for (int32 CenterAttempt = 0; CenterAttempt < 3; ++CenterAttempt)
			{
				FittedBounds = MeasureRadialBounds();
				if (FittedBounds.InnerRadius >= RequiredInnerRadius
					&& FittedBounds.OuterRadius <= MaximumOuterRadius)
				{
					break;
				}
				Volume->AddActorWorldOffset(
					CloudDirection * (TargetCenterRadius - FittedBounds.CenterRadius),
					false, nullptr, ETeleportType::TeleportPhysics);
				CloudComponent->UpdateBounds();
			}

			auto FinalBounds = MeasureRadialBounds();
			constexpr float CloudBoundsToleranceCm = 250.f;
			if (FinalBounds.InnerRadius < RequiredInnerRadius - CloudBoundsToleranceCm
				|| FinalBounds.OuterRadius > MaximumOuterRadius + CloudBoundsToleranceCm)
			{
				UE_LOG(LogRedGameMode, Warning,
					TEXT("HighFive cloud %s hidden: final bounds escaped atmosphere inner=%.0f/%.0f outer=%.0f/%.0f"),
					Presets[Index].Name, FinalBounds.InnerRadius, RequiredInnerRadius,
					FinalBounds.OuterRadius, MaximumOuterRadius);
				CloudComponent->SetVisibility(false, true);
				Volume->SetActorHiddenInGame(true);
				continue;
			}

			CloudComponent->SetVisibility(bWarmSettledClouds, true);
			CloudComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			CloudComponent->SetCollisionResponseToAllChannels(ECR_Ignore);
			CloudComponent->SetGenerateOverlapEvents(false);
			CloudComponent->SetCastShadow(false);
			CloudComponent->SetStreamingMipBias(0);
			CloudComponent->bIssueBlockingRequests = false;
			CloudComponent->StepFactor = 1.f;
			CloudComponent->ShadowStepFactor = 2.f;
			CloudComponent->MarkRenderStateDirty();

			const float FinalBaseClearanceCm =
				FinalBounds.InnerRadius - PlanetPeakRadiusCm;
			const float FinalTopClearanceCm =
				PlanetRadiusCm + AtmosphereHeightCm
				- FinalBounds.OuterRadius;
			const float FinalCenterAltitudeCm = FinalBounds.CenterRadius - PlanetRadiusCm;
			MinimumObservedBaseClearanceCm = FMath::Min(
				MinimumObservedBaseClearanceCm, FinalBaseClearanceCm);
			MinimumObservedTopClearanceCm = FMath::Min(
				MinimumObservedTopClearanceCm, FinalTopClearanceCm);
			if (CloudDirection.Z > 0.25f)
			{
				++NorthernCloudCount;
			}
			else if (CloudDirection.Z < -0.25f)
			{
				++SouthernCloudCount;
			}
			else
			{
				++EquatorialCloudCount;
			}
			UE_LOG(LogRedGameMode, Display,
				TEXT("HighFive cloud %s: direction=(%.3f,%.3f,%.3f) centerAlt=%.0fcm baseClear=%.0fcm topClear=%.0fcm scale=(%.0f,%.0f,%.0f) thinAxis=%d"),
				Presets[Index].Name, CloudDirection.X, CloudDirection.Y, CloudDirection.Z,
				FinalCenterAltitudeCm, FinalBaseClearanceCm, FinalTopClearanceCm,
				AppliedScale.X, AppliedScale.Y, AppliedScale.Z, ThinAxis);
		}
		else
		{
			// Fail closed: a saved placeholder actor without a render component must
			// never be counted or revealed as an atmosphere cloud.
			Volume->SetActorHiddenInGame(true);
			Volume->SetActorEnableCollision(false);
			continue;
		}
		HighFiveCloudVolumes[Index] = Volume;
		Volume->SetActorHiddenInGame(!bWarmSettledClouds);
		Volume->SetActorEnableCollision(false);
		Volume->ForceNetUpdate();
		++ConfiguredCount;
	}

	int32 HiddenDuplicateCount = 0;
	for (TActorIterator<AHeterogeneousVolume> It(World); It; ++It)
	{
		AHeterogeneousVolume* Candidate = *It;
		if (!IsValid(Candidate) || ClaimedVolumes.Contains(Candidate))
		{
			continue;
		}
		UHeterogeneousVolumeComponent* CandidateComponent =
			Candidate->FindComponentByClass<UHeterogeneousVolumeComponent>();
		const UMaterialInterface* CandidateMaterial = CandidateComponent
			? CandidateComponent->GetMaterial(0) : nullptr;
		const bool bIsHighFiveCloud = Candidate->ActorHasTag(TEXT("RedHi5Cloud"))
			|| (CandidateMaterial
				&& CandidateMaterial->GetPathName().Contains(TEXT("/Game/Cloudz_Hi5/")));
		if (!bIsHighFiveCloud)
		{
			continue;
		}
		if (CandidateComponent)
		{
			CandidateComponent->SetVisibility(false, true);
			CandidateComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			CandidateComponent->SetCollisionResponseToAllChannels(ECR_Ignore);
		}
		Candidate->SetActorHiddenInGame(true);
		Candidate->SetActorEnableCollision(false);
		++HiddenDuplicateCount;
	}

	const int32 ExpectedCloudCount = UE_ARRAY_COUNT(Presets);
	const bool bCoverageContractPass = ConfiguredCount == ExpectedCloudCount
		&& NorthernCloudCount >= 3 && SouthernCloudCount >= 3
		&& EquatorialCloudCount >= 3
		&& MinimumObservedBaseClearanceCm >= 0.f
		&& MinimumObservedTopClearanceCm >= 0.f;
	UE_LOG(LogRedGameMode, Display,
		TEXT("RED_HI5_CLOUD_COVERAGE pass=%d configured=%d/%d north=%d south=%d equator=%d minBaseClear=%.0fcm minTopClear=%.0fcm revealed=%d hiddenDuplicates=%d"),
		bCoverageContractPass ? 1 : 0, ConfiguredCount, ExpectedCloudCount,
		NorthernCloudCount, SouthernCloudCount, EquatorialCloudCount,
		MinimumObservedBaseClearanceCm, MinimumObservedTopClearanceCm,
		bRevealSettledClouds ? 1 : 0, HiddenDuplicateCount);
}

void ARedGameMode::EnsureAtmosphereAndClouds()
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	const bool bFusedPrototype =
		World->GetMapName().Contains(TEXT("50km_FusedPrototype"));

	// PlanetGen world is ~6 km radius — SkyAtmosphere.BottomRadius is already ~6.
	// VolumetricCloud defaults to Earth 6360 km; mismatched radius makes clouds invisible
	// and washes the sky into a grey/white banded void.
	float PlanetRadiusKm = 6.f;
	FVector PlanetCenter = FVector::ZeroVector;
	float PlanetRadiusCm = PlanetRadiusKm * 100000.f;
	float PlanetDatumRadiusCm = PlanetRadiusCm;
	float PlanetPeakRadiusCm = PlanetRadiusCm;
	if (RedGravity::FindMeshPlanet(
		World, PlanetCenter, PlanetDatumRadiusCm, &PlanetPeakRadiusCm))
	{
		// FindMeshPlanet's primary radius is deliberately below the deepest
		// authored terrain. Keep that safety datum as SkyAtmosphere's ground;
		// using the nominal midpoint put valley cameras underneath the
		// atmosphere and rendered an otherwise lit daytime sky black.
		PlanetRadiusCm = (PlanetDatumRadiusCm + PlanetPeakRadiusCm) * 0.5f;
		PlanetRadiusKm = FMath::Max(PlanetRadiusCm / 100000.f, 1.f);
	}
	// Keep the eight-kilometre gameplay ascent independent from the rendered
	// molecular shell.  On this deliberately small planet an 8 km physical
	// SkyAtmosphere is as thick as the planet radius and turns the distant world
	// into an opaque blue/white ball.  The 1.8 km shell contains the HI-5 banks;
	// gameplay, exposure, stars and vehicles still use the separate 8 km hand-off.
	const float AtmosphereBottomRadiusKm =
		FMath::Max(PlanetDatumRadiusCm / 100000.f, 1.f);
	// Lowering the physical ground to the terrain datum must not lower the visible
	// limb's outer edge. Add the datum-to-nominal offset here; the separate shared
	// gameplay transition still provides the requested eight-kilometre ascent.
	const float AtmosphereHeightKm = RedPlanetPresentationTuning::VisualAtmosphereHeightKm
		+ FMath::Max(PlanetRadiusKm - AtmosphereBottomRadiusKm, 0.f);
	// Resolve the only light that actually drives atmospheric scattering first.
	// The fused maps contain both BPCLMPlanet's stale atmosphere and SunSky's real
	// atmosphere. Iterator order is not a rendering contract, so bind the component
	// owned by the index-0 atmosphere sun and suppress every duplicate deterministically.
	UDirectionalLightComponent* AtmosphereSun = nullptr;
	float AtmosphereSunIntensity = -1.f;
	TArray<UDirectionalLightComponent*> AtmosphereSunCandidates;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		TArray<UDirectionalLightComponent*> DirectionalLights;
		It->GetComponents<UDirectionalLightComponent>(DirectionalLights);
		for (UDirectionalLightComponent* Candidate : DirectionalLights)
		{
			if (IsValid(Candidate) && Candidate->IsUsedAsAtmosphereSunLight()
				&& Candidate->GetAtmosphereSunLightIndex() == 0u)
			{
				AtmosphereSunCandidates.Add(Candidate);
				if (Candidate->Intensity > AtmosphereSunIntensity)
				{
					AtmosphereSunIntensity = Candidate->Intensity;
					AtmosphereSun = Candidate;
				}
			}
		}
	}
	// Broken demo maps can serialize more than one index-0 sun. Day/night and
	// space scenery both bind the brightest candidate, so make the renderer use
	// that exact component as well instead of relying on actor iterator order.
	for (UDirectionalLightComponent* Candidate : AtmosphereSunCandidates)
	{
		if (Candidate != AtmosphereSun)
		{
			Candidate->SetAtmosphereSunLight(false);
			Candidate->MarkRenderStateDirty();
			UE_LOG(LogRedGameMode, Display,
				TEXT("EnsureAtmosphereAndClouds: disabled duplicate atmosphere sun %s.%s intensity=%.2f"),
				*GetNameSafe(Candidate->GetOwner()), *Candidate->GetName(), Candidate->Intensity);
		}
	}

	TArray<USkyAtmosphereComponent*> AtmosphereComponents;
	USkyAtmosphereComponent* CanonicalAtmosphere = nullptr;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		TArray<USkyAtmosphereComponent*> Atmospheres;
		It->GetComponents<USkyAtmosphereComponent>(Atmospheres);
		for (USkyAtmosphereComponent* Atm : Atmospheres)
		{
			if (!IsValid(Atm))
			{
				continue;
			}
			// Every SkyAtmosphere Set* call is ignored for a registered Static
			// component. SunSky serializes this component below a Static root, so
			// promote the entire attachment chain before changing any dynamic data.
			MakeAtmosphereAttachmentChainMovable(Atm);
			// PlanetGen/SunSky instances can retain an inherited authored scale. The
			// radius values below are absolute kilometres and require unit world scale.
			Atm->SetWorldScale3D(FVector::OneVector);
			Atm->SetBottomRadius(AtmosphereBottomRadiusKm);
			Atm->SetAtmosphereHeight(AtmosphereHeightKm);
			Atm->TransformMode = ESkyAtmosphereTransformMode::PlanetCenterAtComponentTransform;
			Atm->SetRayleighScatteringScale(
				RedPlanetPresentationTuning::RayleighScatteringScale);
			Atm->SetRayleighExponentialDistribution(
				RedPlanetPresentationTuning::RayleighHeightKm);
			Atm->SetMieScatteringScale(
				RedPlanetPresentationTuning::MieScatteringScale);
			Atm->SetMieScattering(FLinearColor::White);
			Atm->SetMieAbsorptionScale(
				RedPlanetPresentationTuning::MieAbsorptionScale);
			Atm->SetOtherAbsorptionScale(
				RedPlanetPresentationTuning::OtherAbsorptionScale);
			Atm->SetMieAnisotropy(
				RedPlanetPresentationTuning::MieAnisotropy);
			Atm->SetMieExponentialDistribution(
				RedPlanetPresentationTuning::MieHeightKm);
			Atm->SetMultiScatteringFactor(
				RedPlanetPresentationTuning::MultiScatteringFactor);
			Atm->SetAerialPespectiveViewDistanceScale(
				RedPlanetPresentationTuning::AerialPerspectiveScale);
			Atm->SetGroundAlbedo(FColor(180, 140, 90));
			Atm->SetSkyLuminanceFactor(
				RedPlanetPresentationTuning::SkyLuminanceFactor);
			Atm->SetSkyAndAerialPerspectiveLuminanceFactor(
				RedPlanetPresentationTuning::SkyAndAerialLuminanceFactor);
			Atm->SetRayleighScattering(
				RedPlanetPresentationTuning::RayleighScatteringColor);
			// Atmosphere must sit at planet center for PlanetCenterAtComponentTransform.
			if (!It->GetActorLocation().Equals(PlanetCenter, 1.0f))
			{
				It->SetActorLocation(PlanetCenter);
			}
			// SunSky blueprints can serialize a non-zero relative transform below
			// their root. Moving only the owner then leaves the atmosphere shell
			// offset from the fused planet, so enforce the component centre too.
			if (!Atm->GetComponentLocation().Equals(PlanetCenter, 1.0f))
			{
				Atm->SetWorldLocation(PlanetCenter, false, nullptr,
					ETeleportType::TeleportPhysics);
			}
			AtmosphereComponents.Add(Atm);
			if (AtmosphereSun && Atm->GetOwner() == AtmosphereSun->GetOwner())
			{
				CanonicalAtmosphere = Atm;
			}
		}
	}
	if (!CanonicalAtmosphere && AtmosphereComponents.Num() > 0)
	{
		CanonicalAtmosphere = AtmosphereComponents[0];
	}
	for (USkyAtmosphereComponent* Atm : AtmosphereComponents)
	{
		if (Atm == CanonicalAtmosphere)
		{
			Atm->ComponentTags.Remove(TEXT("RedDisabledSkyAtmosphere"));
			continue;
		}
		Atm->ComponentTags.AddUnique(TEXT("RedDisabledSkyAtmosphere"));
		Atm->SetVisibility(false, true);
		Atm->SetHiddenInGame(true, true);
		Atm->MarkRenderStateDirty();
		UE_LOG(LogRedGameMode, Display,
			TEXT("EnsureAtmosphereAndClouds: disabled duplicate atmosphere %s.%s"),
			*GetNameSafe(Atm->GetOwner()), *Atm->GetName());
	}
	if (CanonicalAtmosphere)
	{
		// SunSky assets can retain an authored direction override. Clear it so the
		// physical atmosphere follows the replicated rotating index-0 sun.
		CanonicalAtmosphere->ResetAtmosphereLightDirectionOverride(0);
		// Register/dirty the canonical atmosphere last; UE renders the most recently
		// enabled component when a broken map serializes more than one.
		CanonicalAtmosphere->SetVisibility(true, true);
		CanonicalAtmosphere->SetHiddenInGame(false, true);
		CanonicalAtmosphere->MarkRenderStateDirty();
		int32 ActiveAtmosphereCount = 0;
		for (const USkyAtmosphereComponent* Atm : AtmosphereComponents)
		{
			if (IsValid(Atm) && Atm->IsVisible()
				&& !Atm->ComponentHasTag(TEXT("RedDisabledSkyAtmosphere")))
			{
				++ActiveAtmosphereCount;
			}
		}
		const FVector CanonicalScale = CanonicalAtmosphere->GetComponentScale();
		const float ExpectedOuterRadiusKm =
			PlanetRadiusKm + RedPlanetPresentationTuning::VisualAtmosphereHeightKm;
		const float ActualOuterRadiusKm =
			CanonicalAtmosphere->BottomRadius + CanonicalAtmosphere->AtmosphereHeight;
		const float ActualVisualTopAglKm = ActualOuterRadiusKm - PlanetRadiusKm;
		const bool bAtmosphereContractPass =
			FMath::IsNearlyEqual(ActualOuterRadiusKm, ExpectedOuterRadiusKm, 0.02f)
			&& CanonicalScale.Equals(FVector::OneVector, 0.001f)
			&& ActiveAtmosphereCount == 1
			&& RedPlanetPresentationTuning::VisualAtmosphereHeightKm
				< RedPlanetPresentationTuning::AtmosphereHeightKm;
		UE_LOG(LogRedGameMode, Display,
			TEXT("Visual atmosphere contract: nominalSurface=%.2fkm bottom=%.2fkm componentHeight=%.2fkm visualTopAGL=%.2fkm gameplayTransition=%.2fkm scale=%s atmospheres=%d active=%d pass=%d"),
			PlanetRadiusKm, CanonicalAtmosphere->BottomRadius,
			CanonicalAtmosphere->AtmosphereHeight, ActualVisualTopAglKm,
			RedPlanetPresentationTuning::SpaceTransitionAltitudeCm / 100000.f,
			*CanonicalScale.ToString(), AtmosphereComponents.Num(),
			ActiveAtmosphereCount, bAtmosphereContractPass ? 1 : 0);
		if (!bAtmosphereContractPass)
		{
			UE_LOG(LogRedGameMode, Error,
				TEXT("Visual atmosphere contract failed: expectedOuter=%.2fkm actualOuter=%.2fkm"),
				ExpectedOuterRadiusKm, ActualOuterRadiusKm);
		}
		UE_LOG(LogRedGameMode, Display,
			TEXT("EnsureAtmosphereAndClouds: soft orbital limb height=%.1fkm rayleigh=%.4f/%.2fkm bottomR=%.2f on %s; atmospheres=%d canonical=1 centerError=%.1fcm"),
			AtmosphereHeightKm, RedPlanetPresentationTuning::RayleighScatteringScale,
			RedPlanetPresentationTuning::RayleighHeightKm, AtmosphereBottomRadiusKm,
			*GetNameSafe(CanonicalAtmosphere->GetOwner()), AtmosphereComponents.Num(),
			(CanonicalAtmosphere->GetComponentLocation() - PlanetCenter).Size());
		UE_LOG(LogRedGameMode, Display,
			TEXT("EnsureAtmosphereAndClouds: canonical skyLum=%s skyAerial=%s rayleighColor=%s mieAbs=%.6f otherAbs=%.6f anisotropy=%.2f"),
			*CanonicalAtmosphere->SkyLuminanceFactor.ToString(),
			*CanonicalAtmosphere->SkyAndAerialPerspectiveLuminanceFactor.ToString(),
			*CanonicalAtmosphere->RayleighScattering.ToString(),
			CanonicalAtmosphere->MieAbsorptionScale,
			CanonicalAtmosphere->OtherAbsorptionScale,
			CanonicalAtmosphere->MieAnisotropy);
	}
	if (AtmosphereSun)
	{
		MakeAtmosphereAttachmentChainMovable(AtmosphereSun);
		const float DesiredSunIntensity = bFusedPrototype
			? RedPlanetPresentationTuning::DaylightSunIlluminanceLux
			: FMath::Max(AtmosphereSun->Intensity, 5.0f);
		AtmosphereSun->SetIntensity(DesiredSunIntensity);
		// Forward shading supports one primary directional light. Give the real
		// atmosphere sun an unambiguous priority over the shadowless moon fill and
		// disabled demo-sky lights so the renderer does not choose by screen coverage.
		AtmosphereSun->SetForwardShadingPriority(1);
		if (bFusedPrototype)
		{
			AtmosphereSun->SetLightColor(FLinearColor(1.0f, 0.97f, 0.92f));
		}
		AtmosphereSun->SetAtmosphereSunLight(true);
		AtmosphereSun->MarkRenderStateDirty();
		UE_LOG(LogRedGameMode, Display,
			TEXT("EnsureAtmosphereAndClouds: canonical sun=%s.%s int=%.2f atmSun=1 candidates=%d"),
			*GetNameSafe(AtmosphereSun->GetOwner()), *AtmosphereSun->GetName(),
			AtmosphereSun->Intensity, AtmosphereSunCandidates.Num());
	}
	// The legacy fused-map PPV was authored for the old orange test sphere.  Its
	// gain/tint/LUT survive even when saturation, contrast and gamma are reset, and
	// that residual grade turns the physically correct daytime atmosphere into a
	// dark navy slab.  Keep exposure stable for the bright desert, but neutralize
	// every colour-only control so the SkyAtmosphere owns the daylight palette.
	for (TActorIterator<APostProcessVolume> It(World); It; ++It)
	{
		if (!It->bUnbound
			|| (!bFusedPrototype && It->GetName().Contains(TEXT("ZoneMood"))))
		{
			continue;
		}
		FPostProcessSettings& Settings = It->Settings;
		Settings.bOverride_ColorSaturation = true;
		Settings.ColorSaturation = FVector4(1.f, 1.f, 1.f, 1.f);
		Settings.bOverride_ColorContrast = true;
		Settings.ColorContrast = FVector4(1.f, 1.f, 1.f, 1.f);
		Settings.bOverride_ColorGamma = true;
		Settings.ColorGamma = FVector4(1.f, 1.f, 1.f, 1.f);
		Settings.bOverride_ColorGain = true;
		Settings.ColorGain = FVector4(1.f, 1.f, 1.f, 1.f);
		Settings.bOverride_ColorOffset = true;
		Settings.ColorOffset = FVector4(0.f, 0.f, 0.f, 0.f);
		Settings.bOverride_SceneColorTint = true;
		Settings.SceneColorTint = FLinearColor::White;
		Settings.bOverride_ColorGradingIntensity = true;
		Settings.ColorGradingIntensity = 0.f;
		Settings.bOverride_ColorGradingLUT = true;
		Settings.ColorGradingLUT = nullptr;
		Settings.bOverride_WhiteTemp = true;
		Settings.WhiteTemp = 6500.f;
		Settings.bOverride_WhiteTint = true;
		Settings.WhiteTint = 0.f;
		if (bFusedPrototype)
		{
			Settings.bOverride_AutoExposureMethod = true;
			Settings.AutoExposureMethod = AEM_Histogram;
			Settings.bOverride_AutoExposureMinBrightness = true;
			Settings.AutoExposureMinBrightness = -10.0f;
			Settings.bOverride_AutoExposureMaxBrightness = true;
			Settings.AutoExposureMaxBrightness = 20.0f;
			Settings.bOverride_AutoExposureBias = true;
			// Keep the physical 75 klux daylight readable against the HDR surface sky.
			// Larger global offsets wash out orbit and the authored star field.
			Settings.AutoExposureBias = 0.8f;
			Settings.bOverride_AutoExposureApplyPhysicalCameraExposure = true;
			Settings.AutoExposureApplyPhysicalCameraExposure = false;
			Settings.bOverride_AutoExposureSpeedUp = true;
			Settings.AutoExposureSpeedUp = 4.0f;
			Settings.bOverride_AutoExposureSpeedDown = true;
			Settings.AutoExposureSpeedDown = 2.0f;
		}
		UE_LOG(LogRedGameMode, Display,
			TEXT("EnsureAtmosphereAndClouds: neutralized legacy sky grade on %s gain=%s tint=%s LUTIntensity=%.2f exposureOverride=%d/%d exposure=%.2f/%.2f"),
			*It->GetName(), *Settings.ColorGain.ToString(),
			*Settings.SceneColorTint.ToString(), Settings.ColorGradingIntensity,
			Settings.bOverride_AutoExposureMinBrightness ? 1 : 0,
			Settings.bOverride_AutoExposureMaxBrightness ? 1 : 0,
			Settings.AutoExposureMinBrightness,
			Settings.AutoExposureMaxBrightness);
	}

	// Height fog was washing the sky into a grey/white banded void on the beach.
	for (TActorIterator<AExponentialHeightFog> It(World); It; ++It)
	{
		if (UExponentialHeightFogComponent* Fog = It->GetComponent())
		{
			Fog->SetFogDensity(FMath::Min(Fog->FogDensity, 0.0002f));
			Fog->SetFogMaxOpacity(0.15f);
			Fog->SetStartDistance(FMath::Max(Fog->StartDistance, 80000.f));
			Fog->SetFogInscatteringColor(FLinearColor(0.55f, 0.72f, 1.0f));
			Fog->SetSecondFogData(FExponentialHeightFogData());
			Fog->MarkRenderStateDirty();
			UE_LOG(LogRedGameMode, Display, TEXT("EnsureAtmosphereAndClouds: toned fog on %s"), *It->GetName());
		}
	}

	// The selected planet cloud language is the authored High Five VDB set. Disable the generic
	// PlanetGen layer without hiding its owning SunSky actor (which also owns the physical
	// atmosphere and sun). The previous AVolumetricCloud iterator missed the component nested
	// inside SunSky_C and left both cloud systems competing in the same sky.
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		TArray<UVolumetricCloudComponent*> GenericCloudComponents;
		It->GetComponents<UVolumetricCloudComponent>(GenericCloudComponents);
		for (UVolumetricCloudComponent* CloudComponent : GenericCloudComponents)
		{
			if (!IsValid(CloudComponent))
			{
				continue;
			}
			MakeAtmosphereAttachmentChainMovable(CloudComponent);
			CloudComponent->SetPlanetRadius(PlanetRadiusKm);
			CloudComponent->SetLayerBottomAltitude(0.25f);
			CloudComponent->SetLayerHeight(0.80f);
			CloudComponent->SetVisibility(false, true);
			CloudComponent->SetHiddenInGame(true, true);
			CloudComponent->MarkRenderStateDirty();
		}
	}

	EnsureHighFiveCloudVolumes(
		PlanetCenter, PlanetRadiusCm, PlanetPeakRadiusCm,
		// HI-5 bounds must fit inside the rendered molecular shell, not merely
		// inside the longer gameplay ascent used for flight and star transitions.
		RedPlanetPresentationTuning::VisualAtmosphereHeightCm);

	if (GEngine)
	{
		GEngine->Exec(World, TEXT("r.VolumetricCloud 1"));
		GEngine->Exec(World, TEXT("r.VolumetricRenderTarget 1"));
		GEngine->Exec(World, TEXT("r.VolumetricCloud.ViewRaySampleMaxCount 64"));
		GEngine->Exec(World, TEXT("r.VolumetricCloud.Shadow.ViewRaySampleMaxCount 32"));
		GEngine->Exec(World, TEXT("r.HeterogeneousVolumes 1"));
		GEngine->Exec(World, TEXT("r.HeterogeneousVolumes.MaxTraceDistance 2000000"));
		GEngine->Exec(World, TEXT("r.HeterogeneousVolumes.MaxShadowTraceDistance 800000"));
		GEngine->Exec(World, TEXT("r.FilmGrain 0"));
		GEngine->Exec(World, TEXT("r.Tonemapper.GrainQuantization 0"));
		GEngine->Exec(World, TEXT("r.SkyAtmosphere.FastSkyLUT 1"));
		GEngine->Exec(World, TEXT("r.SkyAtmosphere.FastSkyLUT.SampleCountMax 128"));
		GEngine->Exec(World, TEXT("r.SkyAtmosphere.FastSkyLUT.DistanceToSampleCountMax 8"));
		GEngine->Exec(World, TEXT("r.SkyAtmosphere.SampleCountMin 4"));
		GEngine->Exec(World, TEXT("r.SkyAtmosphere.SampleCountMax 64"));
		GEngine->Exec(World, TEXT("r.SkyAtmosphere.DistanceToSampleCountMax 50"));
		GEngine->Exec(World, TEXT("r.SkyAtmosphere.FastSkyLUT.Width 256"));
		GEngine->Exec(World, TEXT("r.SkyAtmosphere.FastSkyLUT.Height 128"));
		GEngine->Exec(World, TEXT("r.SkyAtmosphere.AerialPerspectiveLUT.Width 96"));
		GEngine->Exec(World, TEXT("r.SkyAtmosphere.AerialPerspectiveLUT.DepthResolution 48"));
		GEngine->Exec(World, TEXT("r.SkyAtmosphere.AerialPerspectiveLUT.Depth 24"));
		GEngine->Exec(World, TEXT("r.SkyAtmosphere.AerialPerspectiveLUT.SampleCountMaxPerSlice 6"));
	}

	// Destroy any leftover SM_Cloud / Plane cards from prior sessions — do NOT respawn.
	EnsureSparseCloudCards();

	++AtmosphereCloudRetryCount;
	// UHeterogeneousVolumeComponent resolves its sparse-volume frame transform on
	// the first visible render tick. Keep one retry after reveal so the 4 km bank
	// normalization uses the real VDB frame scale instead of the identity warm-up
	// transform that collapsed the final clouds back into tiny coloured specks.
	if (AtmosphereCloudRetryCount >= 5)
	{
		World->GetTimerManager().ClearTimer(AtmosphereCloudRetryTimer);
		UE_LOG(LogRedGameMode, Display,
			TEXT("EnsureAtmosphereAndClouds: settled after %d retries (timer cleared)"),
			AtmosphereCloudRetryCount);
	}
}

void ARedGameMode::EnsureSparseCloudCards()
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}

	// User rejected fake 2D SM_Cloud / Plane cards — destroy leftovers, never respawn.
	// Clear sky (no volumetric mist) is preferred over card artifacts.
	TArray<AActor*> ToDestroy;
	for (TActorIterator<AStaticMeshActor> It(World); It; ++It)
	{
		if (It->ActorHasTag(TEXT("RedCloudCard"))
			|| It->GetActorNameOrLabel().Contains(TEXT("RedCloudCard")))
		{
			ToDestroy.Add(*It);
		}
	}
	for (AActor* Card : ToDestroy)
	{
		UE_LOG(LogRedGameMode, Display, TEXT("EnsureSparseCloudCards: destroying %s"),
			*Card->GetName());
		Card->Destroy();
	}
	if (ToDestroy.Num() > 0)
	{
		UE_LOG(LogRedGameMode, Display,
			TEXT("EnsureSparseCloudCards: removed %d 2D cloud cards (no respawn)"),
			ToDestroy.Num());
	}
}

void ARedGameMode::EnsureSpaceStarDomes()
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}

	UMaterialInterface* StarMat = LoadObject<UMaterialInterface>(nullptr,
		TEXT("/Game/RedMMO/Materials/M_SpaceStars_Live.M_SpaceStars_Live"));
	if (!StarMat)
	{
		StarMat = LoadObject<UMaterialInterface>(nullptr,
			TEXT("/Game/RedMMO/Materials/M_SpaceStars.M_SpaceStars"));
	}
	UStaticMesh* StarMesh = LoadObject<UStaticMesh>(nullptr,
		TEXT("/Game/AlienFantasyEnvironmentMe/Content/AlienEnvMegaPackVol1/Meshes/AlienJunglePlants/Space/SM_StarSphere.SM_StarSphere"));
	if (!StarMesh)
	{
		StarMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	}
	if (!StarMat || !StarMesh)
	{
		UE_LOG(LogRedGameMode, Warning, TEXT("EnsureSpaceStarDomes: missing mat=%s mesh=%s"),
			StarMat ? TEXT("ok") : TEXT("null"), StarMesh ? TEXT("ok") : TEXT("null"));
		return;
	}

	const FBoxSphereBounds MeshBounds = StarMesh->GetBounds();
	const float LocalR = FMath::Max(MeshBounds.SphereRadius, 1.f);
	// ~200 km shell — large enough that orbital play stays inside even before camera-recenter.
	const float TargetRadiusCm = 20000000.f;
	const float Scale = TargetRadiusCm / LocalR;

	auto EnsureOne = [&](const FString& Label, const FRotator& Rot)
	{
		AStaticMeshActor* Found = nullptr;
		for (TActorIterator<AStaticMeshActor> It(World); It; ++It)
		{
			if (It->ActorHasTag(TEXT("SpaceStarDome")) && It->GetActorNameOrLabel().Contains(Label))
			{
				Found = *It;
				break;
			}
			if (It->GetActorNameOrLabel().Contains(Label))
			{
				Found = *It;
				break;
			}
		}
		if (!Found)
		{
			FActorSpawnParameters Params;
			Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			Found = World->SpawnActor<AStaticMeshActor>(AStaticMeshActor::StaticClass(), FTransform(Rot), Params);
			if (Found)
			{
			#if WITH_EDITOR
				Found->SetActorLabel(Label);
			#endif
				UE_LOG(LogRedGameMode, Display, TEXT("EnsureSpaceStarDomes: spawned %s"), *Label);
			}
		}
		if (!Found)
		{
			return;
		}
		Found->Tags.AddUnique(FName(TEXT("SpaceStarDome")));
		Found->SetActorHiddenInGame(false);
		if (UStaticMeshComponent* SMC = Found->GetStaticMeshComponent())
		{
			if (SMC->Mobility != EComponentMobility::Movable)
			{
				SMC->SetMobility(EComponentMobility::Movable);
			}
			SMC->SetStaticMesh(StarMesh);
			SMC->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			SMC->SetCastShadow(false);
			SMC->SetVisibility(true);
			SMC->SetHiddenInGame(false);
			SMC->bNeverDistanceCull = true;
			SMC->BoundsScale = 50.f;
			if (UMaterialInstanceDynamic* DMI = UMaterialInstanceDynamic::Create(StarMat, SMC))
			{
				DMI->SetScalarParameterValue(TEXT("SpaceFade"), 1.f);
				DMI->SetScalarParameterValue(TEXT("StarBrightness"), 5.f);
				DMI->SetScalarParameterValue(TEXT("StarThreshold"), 0.82f);
				SMC->SetMaterial(0, DMI);
			}
			else
			{
				SMC->SetMaterial(0, StarMat);
			}
			SMC->MarkRenderStateDirty();
		}
		Found->SetActorScale3D(FVector(Scale));
		Found->SetActorRotation(Rot);
	};

	EnsureOne(TEXT("SpaceStarDome_A"), FRotator(0.f, 0.f, 0.f));
	EnsureOne(TEXT("SpaceStarDome_B"), FRotator(180.f, 0.f, 0.f));
}

bool ARedGameMode::IsFantasyBuildingActor(const AActor* Actor) const
{
	if (!IsValid(Actor) || IsProtectedDesertActor(Actor))
	{
		return false;
	}
	// Scan EVERY static-mesh component (not just AStaticMeshActor::GetStaticMeshComponent) so Blueprint
	// actors are caught too — the floating volcanic rocks are BP_SM_SpikeRock_01_C / BP_LargeChunkyRocks
	// etc., which are NOT AStaticMeshActor and used to slip through and stay in the scene.
	TArray<UStaticMeshComponent*> MeshComps;
	Actor->GetComponents<UStaticMeshComponent>(MeshComps);
	for (const UStaticMeshComponent* MeshComp : MeshComps)
	{
		const UStaticMesh* Mesh = MeshComp ? MeshComp->GetStaticMesh() : nullptr;
		if (!Mesh)
		{
			continue;
		}
		const FString Path = Mesh->GetPathName().ToLower();
		// The volcano smoke plume lives under /Game/VFX/ (not /Game/Environment/) — strip it anywhere.
		if (Path.Contains(TEXT("volcanosmoke")))
		{
			return true;
		}
		// Strip ALL Project Titan environment art (never our own /Game/RedMMO content, the proxy sphere,
		// or engine shapes). Every Titan prop set — desert nomad camp / potions / mine tools, wooden
		// docks, marshland, grassland, global rocks, lanterns, balloon, acorn, volcanic, sulfur — either
		// clashes with the sci-fi theme or floats ~40m above the flat tile (authored for other terrain).
		// The desert LOOK is the Landscape sculpt + material (/Game/Landscape/), which is untouched; the
		// bright-desert art pass re-adds proper grounded flowers/structures later.
		if (Path.Contains(TEXT("/game/environment/")))
		{
			return true;
		}
	}
	return false;
}

bool ARedGameMode::IsPointOfInterestMarker(const AActor* Actor) const
{
	if (!IsValid(Actor))
	{
		return false;
	}
	// The big yellow region/quest beacons are BP_RegionalMarker / BP_FastTravelMarker (Titan open-world
	// POI system, DL_Markers data layer). Their yellow rectangle is a world-space UI widget, so the
	// mesh-path strip never sees them — match by class name instead.
	const FString CN = Actor->GetClass()->GetName();
	const bool bIsLegacyMarker = CN.Contains(TEXT("RegionalMarker")) || CN.Contains(TEXT("FastTravelMarker"));
	return bIsLegacyMarker && !IsProtectedDesertActor(Actor);
}

void ARedGameMode::StripFantasyActor(AActor* Actor)
{
	if (!IsValid(Actor) || IsProtectedDesertActor(Actor))
	{
		return;
	}

	// Reference-safe removal: hide + drop collision (never Destroy — see BeginPlay note).
	if (!Actor->IsHidden())
	{
		// Static-mobility meshes log "Mobility should be Movable" (a per-actor spam that hitches the
		// game thread) when their collision is toggled — flip to Movable first to silence it. The actor
		// is hidden anyway, so the dynamic-mobility cost is irrelevant.
		if (USceneComponent* Root = Actor->GetRootComponent())
		{
			if (Root->Mobility != EComponentMobility::Movable)
			{
				Root->SetMobility(EComponentMobility::Movable);
			}
		}
		Actor->SetActorHiddenInGame(true);
		Actor->SetActorEnableCollision(false);
	}
}

void ARedGameMode::SweepFantasyActors()
{
	if (!bStripFantasyBuildings || !GetWorld())
	{
		return;
	}
	int32 Hidden = 0;
	// Iterate ALL actors (not just AStaticMeshActor) so Blueprint-wrapped volcanic props (spike rocks,
	// walls, ropes, shields) are swept too. IsFantasyBuildingActor gates on the /game/environment/ path
	// + token list, so our own content, the pawn, and engine shapes are never touched.
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		AActor* A = *It;
		if (bSuppressProceduralSurfaceDressing && IsProceduralSurfaceDressingActor(A))
		{
			DisableProceduralSurfaceDressingActor(A);
			continue;
		}
		if (IsValid(A) && !A->IsHidden() && (IsFantasyBuildingActor(A) || IsPointOfInterestMarker(A)))
		{
			StripFantasyActor(A);
			++Hidden;
		}
	}
	if (Hidden > 0)
	{
		UE_LOG(LogRedGameMode, Verbose, TEXT("Fantasy strip sweep hid %d actors"), Hidden);
	}
}

void ARedGameMode::RestartPlayer(AController* NewPlayer)
{
	if (!NewPlayer || NewPlayer->IsPendingKillPending())
	{
		return;
	}

	AActor* StartSpot = FindPlayerStart(NewPlayer);
	if (!StartSpot)
	{
		TActorIterator<APlayerStart> It(GetWorld());
		if (It)
		{
			StartSpot = *It;
		}
	}

	EnsureOrbitalMiningSite(StartSpot);
	EnsureCloningStation(StartSpot);
	EnsureOctosphereManager();

	const FTransform SpawnTransform = BuildPlanetSpawnTransform(NewPlayer, StartSpot);
	UE_LOG(LogRedGameMode, Display, TEXT("RestartPlayer surface slot: Controller=%s StartSpot=%s Location=%s Rotation=%s"),
		*GetNameSafe(NewPlayer),
		*GetNameSafe(StartSpot),
		*SpawnTransform.GetLocation().ToCompactString(),
		*SpawnTransform.GetRotation().Rotator().ToCompactString());

	RestartPlayerAtTransform(NewPlayer, SpawnTransform);

	// Each drop lands in the next desert zone (mood cycles through all 8 → "drop into a different
	// desert every time"). Apply the current zone, then advance for the next respawn.
	ApplyZoneMood(ZoneIndex);
	ZoneIndex = (ZoneIndex + 1) % 8;

	// The Drop: put the fresh pawn on the station deck and arm the dive immediately (no mesh-restore
	// follows on an initial spawn, so it's safe to start the freefall pose here).
	if (bStartAtCloningStation && IsValid(SpawnedCloningStation))
	{
		if (ARedPlayerCharacter* Diver = Cast<ARedPlayerCharacter>(NewPlayer->GetPawn()))
		{
			Diver->BoardStationAndDrop(true);
		}
	}
	// Octosphere test: the pawn already spawned ~8 km up (BuildPlanetSpawnTransform). Arm the orbital
	// drop so it free-falls into the planet with the freefall pose + a re-entry terminal velocity that
	// makes the whole descent ~25s regardless of the drop height.
	else if (bOctosphereTest)
	{
		if (ARedPlayerCharacter* Diver = Cast<ARedPlayerCharacter>(NewPlayer->GetPawn()))
		{
			const float ReentryFallSpeed = FMath::Max(6000.f, OctoTestDropAltitude / 25.f);
			Diver->BeginOrbitalDrop(ReentryFallSpeed);
		}
	}
	// CLM mesh-planet drop: the pawn spawned high on the radial (BuildPlanetSpawnTransform). Arm the same
	// free-fall re-entry into the real streaming sphere — RED radial gravity drives the descent + landing.
	else if (bMeshPlanetDrop)
	{
		FVector MeshCenter;
		float MeshRadius;
		if (RedGravity::FindMeshPlanet(GetWorld(), MeshCenter, MeshRadius))
		{
			if (ARedPlayerCharacter* Diver = Cast<ARedPlayerCharacter>(NewPlayer->GetPawn()))
			{
				// The descent speed is now driven by camera pitch (Fortnite dive) in the character Tick;
				// pass the dive max so the landing-slam strength scales to a full plunge.
				Diver->BeginOrbitalDrop(Diver->OrbitalDropDiveFallSpeed);
			}
		}
	}
}

APawn* ARedGameMode::SpawnDefaultPawnAtTransform_Implementation(AController* NewPlayer, const FTransform& SpawnTransform)
{
	UClass* PawnClass = GetDefaultPawnClassForController(NewPlayer);
	if (!PawnClass || !GetWorld())
	{
		return nullptr;
	}

	FActorSpawnParameters SpawnInfo;
	SpawnInfo.Instigator = GetInstigator();
	SpawnInfo.ObjectFlags |= RF_Transient;
	SpawnInfo.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

	APawn* ResultPawn = GetWorld()->SpawnActor<APawn>(PawnClass, SpawnTransform, SpawnInfo);
	if (!ResultPawn)
	{
		UE_LOG(LogRedGameMode, Warning, TEXT("Could not spawn pawn %s at %s"),
			*GetNameSafe(PawnClass),
			*SpawnTransform.ToHumanReadableString());
	}
	else
	{
		ResultPawn->SetActorTransform(SpawnTransform, false, nullptr, ETeleportType::TeleportPhysics);
	}
	return ResultPawn;
}

FTransform ARedGameMode::BuildPlanetSpawnTransform(AController* NewPlayer, AActor* PreferredStart)
{
	// CLM mesh-planet orbital drop: spawn HIGH on the radial above the surface point so the pawn
	// free-falls into the real streaming sphere. Self-gating on a CLM planet being present.
	if (bMeshPlanetDrop)
	{
		FVector MeshCenter;
		float MeshRadius;
		if (RedGravity::FindMeshPlanet(GetWorld(), MeshCenter, MeshRadius))
		{
			// Drop toward the PlayerStart's surface point (the lit sub-solar spawn), else the north pole.
			const FVector ToStart = PreferredStart ? (PreferredStart->GetActorLocation() - MeshCenter) : FVector::ZeroVector;
			const FVector Dir = ToStart.IsNearlyZero() ? FVector::UpVector : ToStart.GetSafeNormal();
			const FVector Loc = MeshCenter + Dir * (MeshRadius + MeshPlanetDropAltitude);
			// Upright on the sphere: capsule up = radial. RED's radial gravity holds it through the dive.
			return FTransform(FRotationMatrix::MakeFromZ(Dir).Rotator(), Loc);
		}
	}

	// CLM mesh planet, STANDING spawn (drop OFF): spawn just above the terrain on the PlayerStart radial so
	// the pawn settles STRAIGHT DOWN (no skydive drift) onto the lit spawn point — for perfecting the
	// surface look. RestartPlayer does not arm the orbital drop while bMeshPlanetDrop is false.
	if (!bMeshPlanetDrop)
	{
		FVector MeshCenter;
		float MeshRadius, PeakRadius = 0.f;
		if (RedGravity::FindMeshPlanet(GetWorld(), MeshCenter, MeshRadius, &PeakRadius))
		{
			const FVector ToStart = PreferredStart ? (PreferredStart->GetActorLocation() - MeshCenter) : FVector::ZeroVector;
			const FVector Dir = ToStart.IsNearlyZero() ? FVector::UpVector : ToStart.GetSafeNormal();
			const FVector Loc = MeshCenter + Dir * (PeakRadius + 5000.f);   // just above the highest terrain
			return FTransform(FRotationMatrix::MakeFromZ(Dir).Rotator(), Loc);
		}
	}

	// Octosphere test: spawn HIGH above the flat face so the pawn free-falls into the planet-proxy
	// sphere and lands into the flat square once it hides (the flat-illusion proof).
	if (bOctosphereTest)
	{
		return FTransform(FRotator::ZeroRotator,
			FVector(FixedDropGroundPoint.X, FixedDropGroundPoint.Y, FixedDropGroundPoint.Z + OctoTestDropAltitude));
	}

	// Hard override: spawn at the pinned known-good land point, ignoring the (ocean-corner) PlayerStart.
	// High Z -> pawn free-falls onto real terrain while cells stream in beneath it. This is the reliable
	// fix — a blindly-placed PlayerStart kept dropping the player into the sea.
	if (bUseFixedDropGround)
	{
		return FTransform(FRotator::ZeroRotator, FixedDropGroundPoint);
	}

	const int32 Slot = SpawnSequence++;
	FVector PlanetCenter = FVector::ZeroVector;
	float SurfaceRadius = RedPlanetFallbackSurfaceRadius;
	const bool bHasPlanet = ResolvePlayablePlanetSurface(GetWorld(), PlanetCenter, SurfaceRadius);

	// FLAT WORLD (Titan / arena — no planet controller and the start isn't inside any gravity body):
	// spawn upright at the PlayerStart with plain -Z gravity. Skips all the radial sphere math that
	// would otherwise hoist the pawn ~3.8km up and tilt it toward the world origin.
	if (!bHasPlanet)
	{
		FVector BodyCenter; float BodyRadius;
		const bool bStartInBody = PreferredStart &&
			RedGravity::QueryDominantBody(GetWorld(), PreferredStart->GetActorLocation(), BodyCenter, BodyRadius);
		if (!bStartInBody)
		{
			if (PreferredStart)
			{
				return FTransform(PreferredStart->GetActorRotation(),
					PreferredStart->GetActorLocation() + FVector(0.f, 0.f, GetDefaultPawnCapsuleHalfHeight(GetDefaultPawnClassForController(NewPlayer)) + SpawnSurfaceGap));
			}
			return FTransform(FRotator::ZeroRotator, FVector(0.f, 0.f, 200.f));
		}
	}

	// Multi-body: if the PlayerStart sits inside a gravity body's volume (e.g. the Phobos STARTING
	// AREA), spawn around THAT body. Without this the math below re-projects a moon start back onto
	// the home planet's surface (the "spawned on the planet under the moon" bug).
	if (PreferredStart)
	{
		FVector BodyCenter;
		float BodySurfaceRadius;
		if (RedGravity::QueryDominantBody(GetWorld(), PreferredStart->GetActorLocation(), BodyCenter, BodySurfaceRadius))
		{
			PlanetCenter = BodyCenter;
			if (BodySurfaceRadius > 0.f)
			{
				SurfaceRadius = BodySurfaceRadius;
			}
		}
	}

	const UClass* PawnClass = GetDefaultPawnClassForController(NewPlayer);
	const float SpawnRadius = SurfaceRadius + GetDefaultPawnCapsuleHalfHeight(PawnClass) + SpawnSurfaceGap;

	FVector BaseLocation = PreferredStart ? PreferredStart->GetActorLocation() : (PlanetCenter + FVector::UpVector * SpawnRadius);
	if ((BaseLocation - PlanetCenter).SizeSquared() < FMath::Square(10000.f))
	{
		BaseLocation = PlanetCenter + FVector::UpVector * SpawnRadius;
	}

	const FVector BaseDirection = SafeNormalOrUp(BaseLocation - PlanetCenter);
	const FVector Up = BaseDirection;
	const FVector SeedForward = PreferredStart ? PreferredStart->GetActorForwardVector() : FVector::ForwardVector;
	const FVector TangentX = BuildSurfaceTangent(Up, SeedForward);
	const FVector TangentY = (Up ^ TangentX).GetSafeNormal();

	const int32 Ring = Slot / RedSpawnSlotsPerRing;
	const int32 RingSlot = Slot % RedSpawnSlotsPerRing;
	const float Angle = (2.f * PI * static_cast<float>(RingSlot)) / static_cast<float>(RedSpawnSlotsPerRing);
	const float Radius = (Slot == 0) ? 0.f : RedSpawnSlotSpacing * static_cast<float>(Ring + 1);
	const FVector TangentOffset = (TangentX * FMath::Cos(Angle) + TangentY * FMath::Sin(Angle)) * Radius;
	const FVector SpawnDirection = SafeNormalOrUp(BaseDirection * SurfaceRadius + TangentOffset);
	const FVector SpawnLocation = PlanetCenter + SpawnDirection * SpawnRadius;

	const FVector SpawnUp = SafeNormalOrUp(SpawnLocation - PlanetCenter);
	FVector Forward = BuildSurfaceTangent(SpawnUp, TangentX);
	if (PreferredStart)
	{
		Forward = BuildSurfaceTangent(SpawnUp, PreferredStart->GetActorForwardVector());
	}
	const FRotator SpawnRotation = FRotationMatrix::MakeFromZX(SpawnUp, Forward).Rotator();

	return FTransform(SpawnRotation, SpawnLocation);
}

void ARedGameMode::EnsureOrbitalMiningSite(AActor* PreferredStart)
{
	if (!bSpawnOrbitalMiningSite || !GetWorld() || IsValid(SpawnedOrbitalMiningSite))
	{
		return;
	}

	FVector PlanetCenter = FVector::ZeroVector;
	float SurfaceRadius = RedPlanetFallbackSurfaceRadius;
	ResolvePlayablePlanetSurface(GetWorld(), PlanetCenter, SurfaceRadius);

	const FVector OrbitDirection = BuildOrbitalMiningDirection(PlanetCenter, SurfaceRadius, PreferredStart);
	const float EffectiveSurfaceAltitude = FMath::Max(OrbitalMiningSiteSurfaceAltitude, 150000000.0f);
	const FVector SiteLocation = PlanetCenter + OrbitDirection * (SurfaceRadius + EffectiveSurfaceAltitude);
	const FVector SiteUp = SafeNormalOrUp(SiteLocation - PlanetCenter);
	const FVector SiteForward = BuildSurfaceTangent(SiteUp, FVector::ForwardVector);
	const FRotator SiteRotation = FRotationMatrix::MakeFromZX(SiteUp, SiteForward).Rotator();

	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	Params.Name = TEXT("Vibe_Orbital_Mining_Asteroid_Site");

	SpawnedOrbitalMiningSite = GetWorld()->SpawnActor<ARedOrbitalMiningSite>(
		ARedOrbitalMiningSite::StaticClass(),
		SiteLocation,
		SiteRotation,
		Params);

	if (SpawnedOrbitalMiningSite)
	{
		SpawnedOrbitalMiningSite->AlignToPlanet(PlanetCenter);
		UE_LOG(LogRedGameMode, Display,
			TEXT("Spawned orbital mining site: Location=%s SurfaceAltitude=%.0f DistanceFromCenter=%.0f"),
			*SiteLocation.ToCompactString(),
			EffectiveSurfaceAltitude,
			(SiteLocation - PlanetCenter).Size());
	}
}

void ARedGameMode::EnsureCloningStation(AActor* PreferredStart)
{
	if (!bStartAtCloningStation || !GetWorld() || IsValid(SpawnedCloningStation))
	{
		return;
	}

	FVector PlanetCenter = FVector::ZeroVector;
	float SurfaceRadius = RedPlanetFallbackSurfaceRadius;
	const bool bHasPlanet = ResolvePlayablePlanetSurface(GetWorld(), PlanetCenter, SurfaceRadius);

	// The ground point the drop lands on + the up axis the pawn falls along.
	FVector GroundPoint;
	FVector DropUp;
	if (bHasPlanet)
	{
		// Radial world: land on the sphere under the start; up = radial.
		const FVector Dir = PreferredStart ? SafeNormalOrUp(PreferredStart->GetActorLocation() - PlanetCenter) : FVector::UpVector;
		GroundPoint = PlanetCenter + Dir * SurfaceRadius;
		DropUp = Dir;
	}
	else
	{
		// Flat world (Titan / arena): land at the pinned known-good terrain spot (a blind PlayerStart
		// placed the station over the ocean); fall back to the PlayerStart only if unpinned.
		GroundPoint = bUseFixedDropGround ? FixedDropGroundPoint
			: (PreferredStart ? PreferredStart->GetActorLocation() : FVector::ZeroVector);
		DropUp = FVector::UpVector;
	}

	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	const FVector SpawnLoc = GroundPoint + DropUp * CloningStationDropAltitude;

	SpawnedCloningStation = GetWorld()->SpawnActor<ARedCloningStation>(
		ARedCloningStation::StaticClass(), SpawnLoc, FRotator::ZeroRotator, Params);
	if (SpawnedCloningStation)
	{
		SpawnedCloningStation->SetupDrop(GroundPoint, DropUp, CloningStationDropAltitude, CloningStationVirtualRadius);
		UE_LOG(LogRedGameMode, Display, TEXT("Spawned cloning station: Deck=%s DropAltitude=%.0f VirtualRadius=%.0f"),
			*SpawnLoc.ToCompactString(), CloningStationDropAltitude, CloningStationVirtualRadius);
	}
}

void ARedGameMode::EnsureOctosphereManager()
{
	if (!GetWorld() || (!bStartAtCloningStation && !bOctosphereTest))
	{
		return;
	}
	// Reuse a manager already placed in the level; otherwise spawn one.
	if (!IsValid(SpawnedOctosphereManager))
	{
		for (TActorIterator<ARedOctosphereManager> It(GetWorld()); It; ++It)
		{
			if (IsValid(*It)) { SpawnedOctosphereManager = *It; break; }
		}
		if (!IsValid(SpawnedOctosphereManager))
		{
			FActorSpawnParameters Params;
			Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			SpawnedOctosphereManager = GetWorld()->SpawnActor<ARedOctosphereManager>(
				ARedOctosphereManager::StaticClass(), FTransform::Identity, Params);
		}
	}
	if (!IsValid(SpawnedOctosphereManager))
	{
		return;
	}
	// Configure it NOW (a pre-placed manager's BeginPlay may have run before this).
	if (bOctosphereTest)
	{
		// Virtual planet whose NORTH POLE is the flat face: center is straight down by the radius, so
		// the sphere's top sits at the face's ground level and the pawn free-falls onto it.
		const FVector Center(FixedDropGroundPoint.X, FixedDropGroundPoint.Y, FixedDropGroundPoint.Z - OctoTestRadius);
		SpawnedOctosphereManager->ConfigureForDrop(Center, OctoTestRadius, OctoTestDropAltitude);
		// Sit the manager ON the landing spot so its WorldPartition streaming source PRELOADS that cell
		// from the start of play — the terrain is fully in before the diver emerges below the cloud deck
		// (kills the half-loaded checkerboard tiles). The octant math uses PlanetCenter, not this actor's
		// location, so moving the actor here is safe.
		SpawnedOctosphereManager->SetActorLocation(
			FVector(FixedDropGroundPoint.X, FixedDropGroundPoint.Y, FixedDropGroundPoint.Z));
		// DESERT PLANET (island-from-above model): the 20000x runtime-scaled proxy sphere would not render
		// on Metal (bounds/cull quirk), and the REAL coral desert island — ringed by ocean, hazed by the
		// atmosphere — already reads as a planet surface from altitude. So keep the proxy OFF and leave the
		// real terrain VISIBLE the whole descent: you free-fall belly-down (camera tilted down via
		// OrbitalDropCameraPitch) watching the desert island grow beneath you, then land. No sphere to hide,
		// so no whiteout swap needed either.
		SpawnedOctosphereManager->bShowPlanetProxy = false;
		SpawnedOctosphereManager->bDeckWhiteout = false;
	}
	else if (IsValid(SpawnedCloningStation))
	{
		SpawnedOctosphereManager->ConfigureForDrop(
			SpawnedCloningStation->GetVirtualPlanetCenter(),
			SpawnedCloningStation->GetVirtualPlanetRadius(),
			SpawnedCloningStation->GetDropAltitude());
	}
}
