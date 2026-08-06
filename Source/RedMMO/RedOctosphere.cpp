#include "RedOctosphere.h"
#include "RedCloningStation.h"
#include "RedPlayerCharacter.h"
#include "Kismet/GameplayStatics.h"
#include "GameFramework/Pawn.h"
#include "Net/UnrealNetwork.h"
#include "DrawDebugHelpers.h"
#include "EngineUtils.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Components/StaticMeshComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Engine/ExponentialHeightFog.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInterface.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/WorldPartitionStreamingSourceComponent.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
	// Octahedron face-center directions (unit ±0.577 corners) — guide OctosphereConstants::FaceCenters.
	static const FVector GFaceCenters[8] = {
		FVector( 0.5773503f,  0.5773503f,  0.5773503f), // 0 North +X +Z
		FVector(-0.5773503f,  0.5773503f,  0.5773503f), // 1 North -X +Z
		FVector(-0.5773503f,  0.5773503f, -0.5773503f), // 2 North -X -Z
		FVector( 0.5773503f,  0.5773503f, -0.5773503f), // 3 North +X -Z
		FVector( 0.5773503f, -0.5773503f,  0.5773503f), // 4 South +X +Z
		FVector(-0.5773503f, -0.5773503f,  0.5773503f), // 5 South -X +Z
		FVector(-0.5773503f, -0.5773503f, -0.5773503f), // 6 South -X -Z
		FVector( 0.5773503f, -0.5773503f, -0.5773503f), // 7 South +X -Z
	};

	// Faces sharing an edge — guide OctosphereConstants::Adjacency.
	static const int32 GAdjacency[8][3] = {
		{1, 3, 4}, {0, 2, 5}, {1, 3, 6}, {0, 2, 7},
		{0, 5, 7}, {1, 4, 6}, {2, 5, 7}, {3, 4, 6},
	};
}

ARedOctosphereManager::ARedOctosphereManager()
{
	PrimaryActorTick.bCanEverTick = true;
	bReplicates = true;
	bAlwaysRelevant = true;
	FaceZoneNames.Init(NAME_None, 8);

	// Root + the visible planet-proxy sphere (the "planet" you fly into; hides on the ground so you
	// land into the flat face). Absolute transform so it sits at PlanetCenter regardless of the actor.
	USceneComponent* Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	RootComponent = Root;
	PlanetProxyMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("PlanetProxy"));
	PlanetProxyMesh->SetupAttachment(Root);
	PlanetProxyMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	PlanetProxyMesh->SetCastShadow(false);
	PlanetProxyMesh->SetUsingAbsoluteLocation(true);
	PlanetProxyMesh->SetUsingAbsoluteScale(true);
	static ConstructorHelpers::FObjectFinder<UStaticMesh> SphereAsset(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	if (SphereAsset.Succeeded())
	{
		PlanetProxyMesh->SetStaticMesh(SphereAsset.Object);
	}
	// PlanetGen owns the visible planetary surface. Do not synchronously load an imported
	// landscape material in this CDO: UE's Landscape module may not be initialized yet,
	// and material post-load can crash before the editor reaches the MCP startup phase.

	// Cloud-dive: a World Partition streaming source pinned to this actor. The GameMode parks the actor
	// on the landing spot, so the target cell streams in from the START of play and is fully loaded by
	// the time the diver drops below the cloud deck — no half-loaded checkerboard tiles on emergence.
	LandingStreamSource = CreateDefaultSubobject<UWorldPartitionStreamingSourceComponent>(TEXT("LandingStreamSource"));
}

void ARedOctosphereManager::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(ARedOctosphereManager, ActiveFaceIndex);
	DOREPLIFETIME(ARedOctosphereManager, TargetZoneName);
}

int32 ARedOctosphereManager::FaceIndexForDirection(const FVector& DirFromCenter)
{
	// Octant classification (guide convention: Y = poles, X = east, Z = front).
	const bool bNorth = DirFromCenter.Y >= 0.f;
	const bool bEast  = DirFromCenter.X >= 0.f;
	const bool bFront = DirFromCenter.Z >= 0.f;
	if (bNorth)
	{
		if (bEast && bFront)  return 0;
		if (!bEast && bFront) return 1;
		if (!bEast && !bFront) return 2;
		return 3; // bEast && !bFront
	}
	if (bFront && bEast)   return 4;
	if (bFront && !bEast)  return 5;
	if (!bFront && !bEast) return 6;
	return 7; // !bFront && bEast
}

FVector ARedOctosphereManager::FaceCenterDir(int32 FaceIndex)
{
	return GFaceCenters[FMath::Clamp(FaceIndex, 0, 7)];
}

void ARedOctosphereManager::GetAdjacentFaces(int32 FaceIndex, int32& OutA, int32& OutB, int32& OutC)
{
	const int32 F = FMath::Clamp(FaceIndex, 0, 7);
	OutA = GAdjacency[F][0];
	OutB = GAdjacency[F][1];
	OutC = GAdjacency[F][2];
}

int32 ARedOctosphereManager::GetFaceIndexForLocation(const FVector& WorldLocation) const
{
	return FaceIndexForDirection((WorldLocation - PlanetCenter).GetSafeNormal());
}

float ARedOctosphereManager::GetAltitude(const FVector& WorldLocation) const
{
	return FVector::Dist(WorldLocation, PlanetCenter) - PlanetRadius;
}

ERedOctoLayer ARedOctosphereManager::LayerForAltitude(float Altitude) const
{
	if (Altitude >= OrbitAltitude)   return ERedOctoLayer::Orbit;
	if (Altitude >= SurfaceAltitude) return ERedOctoLayer::Approach;
	return ERedOctoLayer::Surface;
}

FName ARedOctosphereManager::GetZoneForFace(int32 FaceIndex) const
{
	return FaceZoneNames.IsValidIndex(FaceIndex) ? FaceZoneNames[FaceIndex] : NAME_None;
}

void ARedOctosphereManager::BeginPlay()
{
	Super::BeginPlay();
	if (FaceZoneNames.Num() != 8)
	{
		FaceZoneNames.SetNum(8);
	}

	// Adopt the cloning station's virtual planet (center below the drop + radius) if one exists, so the
	// octant math + altitude are measured against the real drop geometry rather than the 400km default.
	if (GetWorld())
	{
		for (TActorIterator<ARedCloningStation> It(GetWorld()); It; ++It)
		{
			if (IsValid(*It))
			{
				ConfigureForDrop(It->GetVirtualPlanetCenter(), It->GetVirtualPlanetRadius(), It->GetDropAltitude());
				break;
			}
		}
	}
	TargetZoneName = GetZoneForFace(ActiveFaceIndex);

	ConfigureDescentFog();
}

void ARedOctosphereManager::ConfigureForDrop(const FVector& Center, float Radius, float InDropAltitude)
{
	PlanetCenter = Center;
	if (Radius > 0.f)
	{
		PlanetRadius = Radius;
	}
	if (InDropAltitude > 0.f)
	{
		// Scale the layer thresholds to the actual drop so Orbit->Approach->Surface all trigger on a
		// short prototype drop (the 10km/100km defaults would leave a 1km drop permanently "Surface").
		DropStartAltitude = InDropAltitude;
		// Atmosphere-entry deck: a whiteout band the swaps hide inside. Both the ground-reveal and the
		// sphere-hide fire near DeckMid (peak whiteout) so the flat-tile<->sphere seam is never seen in
		// clear air. Orbit = above the deck (sphere only); Surface = below it (fogged tile only).
		DeckTopAlt      = InDropAltitude * 0.52f;   // 4.16km @ 8km — enter whiteout
		DeckMidAlt      = InDropAltitude * 0.43f;   // 3.44km — peak whiteout
		DeckBottomAlt   = InDropAltitude * 0.34f;   // 2.72km — exit whiteout
		GroundRevealAlt = InDropAltitude * 0.44f;   // 3.52km — reveal tile (whiteout ~opaque)
		SphereHideAlt   = InDropAltitude * 0.42f;   // 3.36km — hide sphere (whiteout ~opaque)

		OrbitAltitude   = DeckTopAlt;               // above deck = Orbit (sphere only)
		SurfaceAltitude = DeckBottomAlt;            // below deck = Surface (tile only); between = Approach
		LockAltitude    = InDropAltitude * 0.45f;   // target face freezes here
	}
}

FVector ARedOctosphereManager::ProjectTrajectoryToSurfaceDir(const FVector& WorldLocation, const FVector& WorldVelocity, bool& bOutValid) const
{
	// Ray (position + velocity) vs the virtual surface sphere. Valid because gravity pulls toward
	// PlanetCenter (radial in true mode; center-straight-below in the flat-illusion prototype) — NOT
	// because "down". The near hit is where the current fall path meets the ground.
	bOutValid = false;
	const FVector Rel = WorldLocation - PlanetCenter;
	const float Dist = Rel.Size();
	const FVector RayDir = WorldVelocity.GetSafeNormal();
	if (RayDir.IsNearlyZero() || Dist < 1.f)
	{
		return Rel.GetSafeNormal();
	}
	const float B = 2.f * FVector::DotProduct(Rel, RayDir);
	const float C = Dist * Dist - PlanetRadius * PlanetRadius;
	const float Disc = B * B - 4.f * C;
	if (Disc < 0.f)
	{
		return Rel.GetSafeNormal();
	}
	const float Sq = FMath::Sqrt(Disc);
	const float T0 = (-B - Sq) * 0.5f;
	const float T1 = (-B + Sq) * 0.5f;
	const float T = (T0 > 0.f) ? T0 : T1;
	if (T <= 0.f)
	{
		return Rel.GetSafeNormal();
	}
	const FVector Hit = WorldLocation + RayDir * T;
	bOutValid = true;
	return (Hit - PlanetCenter).GetSafeNormal();
}

void ARedOctosphereManager::UpdateDropState(const FVector& Loc, const FVector& Velocity)
{
	ActiveAltitude = GetAltitude(Loc);
	const ERedOctoLayer Layer = LayerForAltitude(ActiveAltitude);

	// Unlock on (re)entering orbit — a fresh drop re-arms the live steer; lock once we fall past LockAltitude.
	if (Layer == ERedOctoLayer::Orbit)
	{
		bTargetLocked = false;
	}
	else if (!bTargetLocked && ActiveAltitude <= LockAltitude)
	{
		bTargetLocked = true;
	}

	// Server owns the trajectory-picked target. While unlocked, aim at where the fall path lands;
	// once locked (or on the client), hold the replicated ActiveFaceIndex.
	if (HasAuthority() && !bTargetLocked)
	{
		bool bValid = false;
		const FVector LandDir = ProjectTrajectoryToSurfaceDir(Loc, Velocity, bValid);
		ActiveFaceIndex = bValid ? FaceIndexForDirection(LandDir) : GetFaceIndexForLocation(Loc);
		TargetZoneName = GetZoneForFace(ActiveFaceIndex);
		if (TargetZoneName.IsNone())
		{
			TargetZoneName = *FString::Printf(TEXT("Face_%d"), ActiveFaceIndex);
		}
	}

	const float Span = FMath::Max(DropStartAltitude, 1.f);
	DescentProgress01 = FMath::Clamp(1.f - ActiveAltitude / Span, 0.f, 1.f);

	if (Layer != LastLayerForCue)
	{
		OnLayerChanged(LastLayerForCue, Layer);
		LastLayerForCue = Layer;
	}
	ActiveLayer = Layer;
}

void ARedOctosphereManager::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	APawn* Pawn = UGameplayStatics::GetPlayerPawn(this, 0);
	if (Pawn)
	{
		UpdateDropState(Pawn->GetActorLocation(), Pawn->GetVelocity());
	}

	// The visible planet: sit it at PlanetCenter, size it to PlanetRadius. Hide it BELOW SphereHideAlt
	// (which is inside the whiteout deck) so the swap is never seen in clear air — not at the Surface
	// boundary, which would pop in clear air.
	if (PlanetProxyMesh)
	{
		PlanetProxyMesh->SetWorldLocation(PlanetCenter);
		PlanetProxyMesh->SetWorldScale3D(FVector(PlanetRadius / 50.f)); // BasicShapes/Sphere = 50cm radius
		const bool bVisible = bShowPlanetProxy && (ActiveAltitude >= SphereHideAlt);
		if (PlanetProxyMesh->IsVisible() != bVisible)
		{
			PlanetProxyMesh->SetVisibility(bVisible);
		}
	}

	// Cloud-dive: the real flat ground (+ broken HLOD) is hidden ABOVE GroundRevealAlt so from orbit you
	// see cloud tops / open sky, NOT half-loaded terrain. It "loads in" (already pre-streamed by the
	// landing source) as you cross GroundRevealAlt — which sits inside the opaque cloud band, so the
	// reveal happens behind the whiteout. Re-applied each tick to catch WP-streamed cells.
	SetGroundWorldHidden(ActiveAltitude >= GroundRevealAlt);

	// Cloud-pass whiteout: opaque white while crossing the deck. With the impostor sphere gone there is
	// nothing for it to clash with — it simply reads as flying through a cloud layer.
	if (bDeckWhiteout)
	{
		DriveDeckWhiteout();
	}
	DriveDescentFog();

	if (bShowDropHUD)
	{
		DrawDropHUD();
	}
	if (bShowLayerVisuals)
	{
		DrawLayerVisuals();
	}
	if (bShowLandingMarkers)
	{
		DrawLandingMarkers();
	}
}

void ARedOctosphereManager::SetGroundWorldHidden(bool bOrbitHide)
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	// Runs every tick (no early-out) because WorldPartitionHLOD must ALWAYS be hidden — the r.HLOD cvar
	// stops NEW generation but does not unhide/unload the ~800 already-streamed proxies, which render as
	// the black/checkerboard tiles. SetActorHiddenInGame on the HLOD actor does stop its proxy mesh.
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		AActor* A = *It;
		if (!IsValid(A))
		{
			continue;
		}
		const FString CN = A->GetClass()->GetName();
		bool bWant;
		if (CN.Contains(TEXT("HLOD")))
		{
			bWant = true;   // broken on Metal -> always hidden (belt-and-suspenders to r.HLOD 0)
		}
		// Real ground content: hidden above the deck (orbit) so only the planet-proxy sphere is seen,
		// shown below (land into it). Covers the streamed-world classes (Landscape/WaterBody/WaterZone)
		// AND the baked SoStylized desert island content (mesas/props = StaticMeshActor, BP_Water_C,
		// InstancedFoliageActor, BP_TumbleweedZone, desert Niagara VFX). The sky/lights/pawn/manager do
		// not match, so orbit keeps its sky + sun and the sphere stays lit. Re-applied each tick.
		else if (CN.Contains(TEXT("Landscape")) || CN.Contains(TEXT("Water")) ||
			CN.Contains(TEXT("StaticMeshActor")) || CN.Contains(TEXT("InstancedFoliage")) ||
			CN.Contains(TEXT("Tumbleweed")) || CN.Contains(TEXT("NiagaraActor")))
		{
			// Only hide the real ground in orbit when a proxy sphere is standing in for it. With the proxy
			// OFF (island-from-above model), the real desert IS the planet you watch the whole way down —
			// keep it visible always.
			bWant = bOrbitHide && bShowPlanetProxy;
		}
		else
		{
			continue;
		}
		if (A->IsHidden() != bWant)
		{
			A->SetActorHiddenInGame(bWant);
		}
	}
	bGroundHidden = bOrbitHide;
}

void ARedOctosphereManager::DriveDeckWhiteout()
{
	APlayerCameraManager* PCM = UGameplayStatics::GetPlayerCameraManager(this, 0);
	if (!PCM)
	{
		return;
	}
	// Triangle ramp across the deck, peaking (opaque white) at DeckMid where both swaps fire. Smoothstep
	// for a soft in/out. Everywhere outside the deck the fade is 0.
	float Alpha = 0.f;
	if (ActiveAltitude < DeckTopAlt && ActiveAltitude > DeckBottomAlt && DeckTopAlt > DeckBottomAlt)
	{
		Alpha = (ActiveAltitude >= DeckMidAlt)
			? 1.f - (ActiveAltitude - DeckMidAlt) / FMath::Max(1.f, DeckTopAlt - DeckMidAlt)
			: (ActiveAltitude - DeckBottomAlt) / FMath::Max(1.f, DeckMidAlt - DeckBottomAlt);
		Alpha = FMath::Clamp(Alpha, 0.f, 1.f);
		Alpha = Alpha * Alpha * (3.f - 2.f * Alpha);   // smoothstep
	}

	if (Alpha > 0.f)
	{
		PCM->SetManualCameraFade(Alpha, FLinearColor::White, false);
		bManagingCameraFade = true;
	}
	else if (bManagingCameraFade)
	{
		PCM->SetManualCameraFade(0.f, FLinearColor::White, false);   // clear once on leaving the deck
		bManagingCameraFade = false;
	}
}

void ARedOctosphereManager::ConfigureDescentFog()
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	for (TActorIterator<AExponentialHeightFog> It(World); It; ++It)
	{
		if (AExponentialHeightFog* Fog = *It)
		{
			CachedFog = Fog->GetComponent();
			break;
		}
	}
	if (!CachedFog)
	{
		return;
	}
	// One-time static setup: a low-falloff warm-desert horizon haze with a full-opacity far edge, only
	// biting past ~2km so near/mid combat stays crisp. Density itself is driven per-tick by DriveDescentFog.
	CachedFog->SetFogHeightFalloff(0.20f);       // clears with height so the surface scene isn't washed out
	CachedFog->SetStartDistance(300000.f);       // 3km -> near/mid tile fully crisp, only the far edge fogs
	CachedFog->SetFogMaxOpacity(0.65f);          // never a full white-out on the surface (light desert haze)
	CachedFog->SetFogInscatteringColor(DescentFogColor);
	CachedFog->SetSecondFogData(FExponentialHeightFogData());   // clear any stale second layer
	CachedFog->SetFogDensity(OrbitFogDensity);   // start near-clear (orbit)
}

void ARedOctosphereManager::DriveDescentFog()
{
	if (!CachedFog)
	{
		return;
	}
	// Ramp density 0(orbit)->1(surface) across the deck so the orbit sphere stays crisp and the surface
	// tile's far edge dissolves into the warm horizon. Uses the same altitude the whiteout does.
	float T = 0.f;
	if (ActiveAltitude <= DeckBottomAlt)
	{
		T = 1.f;
	}
	else if (ActiveAltitude < DeckTopAlt && DeckTopAlt > DeckBottomAlt)
	{
		T = 1.f - (ActiveAltitude - DeckBottomAlt) / (DeckTopAlt - DeckBottomAlt);
		T = FMath::Clamp(T, 0.f, 1.f);
		T = T * T * (3.f - 2.f * T);
	}
	const float Density = FMath::Lerp(OrbitFogDensity, SurfaceFogDensity, T);
	CachedFog->SetFogDensity(Density);
}

void ARedOctosphereManager::DrawLandingMarkers() const
{
#if ENABLE_DRAW_DEBUG
	UWorld* World = GetWorld();
	if (!World) { return; }
	// One marker per falling diver: a red vertical beam + a shrinking ground ring at the predicted
	// landing spot. Many rings converging on one area = a hotspot ("RED = DEAD incoming").
	for (TActorIterator<ARedPlayerCharacter> It(World); It; ++It)
	{
		ARedPlayerCharacter* Diver = *It;
		if (!IsValid(Diver) || !Diver->IsSkydiving() || Diver->bIsEnemy) { continue; }

		const FVector Loc = Diver->GetActorLocation();
		bool bValid = false;
		const FVector LandDir = ProjectTrajectoryToSurfaceDir(Loc, Diver->GetVelocity(), bValid);
		const FVector Up = (Loc - PlanetCenter).GetSafeNormal();
		FVector Ground = bValid ? (PlanetCenter + LandDir * PlanetRadius) : (Loc - Up * GetAltitude(Loc));

		// Refine to the real surface with a downward trace.
		FHitResult Hit;
		FCollisionQueryParams GP(SCENE_QUERY_STAT(DropMarker), false, Diver);
		if (World->LineTraceSingleByChannel(Hit, Ground + Up * 20000.f, Ground - Up * 20000.f, ECC_WorldStatic, GP))
		{
			Ground = Hit.ImpactPoint;
		}

		const FColor Col = MarkerColor.ToFColor(true);
		const float Prog = FMath::Clamp(1.f - GetAltitude(Loc) / FMath::Max(1.f, DropStartAltitude), 0.f, 1.f);
		const float Radius = FMath::Max(60.f, MarkerMaxRadius * (1.f - Prog));   // ring shrinks as they near the ground
		FVector T1 = FVector::CrossProduct(Up, FVector::ForwardVector).GetSafeNormal();
		if (T1.IsNearlyZero()) { T1 = FVector::CrossProduct(Up, FVector::RightVector).GetSafeNormal(); }
		const FVector T2 = FVector::CrossProduct(Up, T1).GetSafeNormal();
		DrawDebugCircle(World, Ground + Up * 5.f, Radius, 32, Col, false, -1.f, 0, 30.f, T1, T2, false);
		DrawDebugLine(World, Ground, Ground + Up * MarkerBeamHeight, Col, false, -1.f, 0, 24.f);
	}
#endif
}

namespace
{
	FColor LayerColor(ERedOctoLayer Layer)
	{
		switch (Layer)
		{
		case ERedOctoLayer::Orbit:    return FColor(120, 180, 255);
		case ERedOctoLayer::Approach: return FColor(255, 180, 60);
		default:                      return FColor(120, 255, 140);
		}
	}
	const TCHAR* LayerName(ERedOctoLayer Layer)
	{
		switch (Layer)
		{
		case ERedOctoLayer::Orbit:    return TEXT("ORBIT");
		case ERedOctoLayer::Approach: return TEXT("APPROACH");
		default:                      return TEXT("SURFACE");
		}
	}
}

void ARedOctosphereManager::DrawDropHUD() const
{
	// Guard on GEngine only (NOT ENABLE_DRAW_DEBUG) so the readout survives in non-Development builds,
	// matching every other on-screen HUD in the project. Fixed keys 7000-7004 update lines in place.
	if (!GEngine)
	{
		return;
	}
	const FColor Col = LayerColor(ActiveLayer);
	GEngine->AddOnScreenDebugMessage(7000, 0.f, Col,
		FString::Printf(TEXT("THE DROP - %s%s"), LayerName(ActiveLayer), bDropInProgress ? TEXT("  [DIVING]") : TEXT("")));
	GEngine->AddOnScreenDebugMessage(7001, 0.f, FColor::White,
		FString::Printf(TEXT("ALT %.2f km"), ActiveAltitude / 100000.f));
	GEngine->AddOnScreenDebugMessage(7002, 0.f, bTargetLocked ? FColor::Green : FColor::Yellow,
		FString::Printf(TEXT("TARGET face %d (%s)%s"), ActiveFaceIndex, *TargetZoneName.ToString(),
			bTargetLocked ? TEXT(" [LOCKED]") : TEXT(" ...steering")));

	const int32 Filled = FMath::Clamp(FMath::RoundToInt(DescentProgress01 * 20.f), 0, 20);
	FString Bar = TEXT("[");
	for (int32 i = 0; i < 20; ++i) { Bar += (i < Filled) ? TEXT("=") : TEXT("-"); }
	Bar += FString::Printf(TEXT("] %d%%"), FMath::RoundToInt(DescentProgress01 * 100.f));
	GEngine->AddOnScreenDebugMessage(7003, 0.f, Col, Bar);

	if (ActiveLayer == ERedOctoLayer::Approach)
	{
		const float T = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.f;
		if (FMath::Fmod(T, 1.f) < 0.5f)
		{
			GEngine->AddOnScreenDebugMessage(7004, 0.f, FColor(255, 210, 90),
				FString::Printf(TEXT(">>> STREAMING IN: %s <<<"), *TargetZoneName.ToString()));
		}
	}
}

void ARedOctosphereManager::OnLayerChanged(ERedOctoLayer From, ERedOctoLayer To)
{
	if (!GEngine)
	{
		return;
	}
	FString Msg;
	if (To == ERedOctoLayer::Orbit)
	{
		Msg = TEXT("BOARDING STATION - pick your drop");
	}
	else if (From == ERedOctoLayer::Orbit && To == ERedOctoLayer::Approach)
	{
		Msg = FString::Printf(TEXT("ENTERING ATMOSPHERE - streaming in %s"), *TargetZoneName.ToString());
	}
	else if (To == ERedOctoLayer::Surface)
	{
		Msg = FString::Printf(TEXT("TOUCHDOWN - %s"), *TargetZoneName.ToString());
	}
	if (!Msg.IsEmpty())
	{
		GEngine->AddOnScreenDebugMessage(-1, 3.5f, LayerColor(To), Msg);
	}
}

void ARedOctosphereManager::DrawLayerVisuals() const
{
#if ENABLE_DRAW_DEBUG
	if (!GetWorld())
	{
		return;
	}
	// Whole-planet wireframe: bright in Orbit, faint in Approach, off at Surface (the impostor stand-in).
	if (ActiveLayer != ERedOctoLayer::Surface)
	{
		const FColor SphereCol = (ActiveLayer == ERedOctoLayer::Orbit) ? FColor(90, 140, 220) : FColor(50, 80, 130);
		DrawDebugSphere(GetWorld(), PlanetCenter, PlanetRadius, 24, SphereCol, false, -1.f, 0, 30.f);
	}
	// 8 zone spokes, the trajectory-picked one bright yellow.
	for (int32 i = 0; i < 8; ++i)
	{
		const FVector End = PlanetCenter + FaceCenterDir(i) * PlanetRadius;
		const bool bActive = (i == ActiveFaceIndex);
		DrawDebugLine(GetWorld(), PlanetCenter, End,
			bActive ? FColor::Yellow : FColor(60, 90, 140), false, -1.f, 0, bActive ? 40.f : 10.f);
	}
	// Approach: a landing beam down the target face + a label.
	if (ActiveLayer == ERedOctoLayer::Approach)
	{
		const FVector Target = PlanetCenter + FaceCenterDir(ActiveFaceIndex) * PlanetRadius;
		DrawDebugLine(GetWorld(), Target + FaceCenterDir(ActiveFaceIndex) * 200000.f, Target,
			FColor(255, 200, 80), false, -1.f, 0, 60.f);
		DrawDebugString(GetWorld(), Target, TEXT("ZONE STREAMING"), nullptr, FColor::Yellow, 0.f);
	}
#endif
}
