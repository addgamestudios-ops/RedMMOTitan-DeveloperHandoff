#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "RedSpaceScenery.generated.h"

class UHierarchicalInstancedStaticMeshComponent;
class UDirectionalLightComponent;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class UPostProcessComponent;
class UProceduralMeshComponent;
class URedSpaceExposureCameraModifier;
class USceneComponent;
class UStaticMeshComponent;
class UStaticMesh;
class UWorld;

/**
 * Deterministic, lightweight orbital scenery shared by every client.
 * Spawned once by the authority from whichever project ship initializes first.
 */
UCLASS(NotPlaceable)
class REDMMO_API ARedSpaceScenery : public AActor
{
	GENERATED_BODY()

public:
	ARedSpaceScenery();
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void Tick(float DeltaSeconds) override;

	/** Return the existing scenery actor or spawn the one authoritative shared instance. */
	static ARedSpaceScenery* EnsureForWorld(UWorld* World, const FVector& AnchorCenter);

	/** Solid reachable moon used by the multi-body gravity query and aligned with the moon fill. */
	bool GetMoonGravityBody(
		FVector& OutCenter, float& OutSurfaceRadius, float& OutInfluenceRadius) const;

	/**
	 * Append every enabled project-owned celestial gravity body. The home-system moon is
	 * always eligible. The retired custom Saturn prototype and its three test moons are
	 * excluded unless that legacy implementation is explicitly re-enabled in source.
	 */
	void AppendGravityBodies(
		TArray<FName>& OutStableIds, TArray<int32>& OutPriorities,
		TArray<FVector>& OutCenters, TArray<float>& OutSurfaceRadii,
		TArray<float>& OutInfluenceRadii) const;

	/** Seeds the roughly 60 km orbit radius; runtime direction follows the coherent moon fill. */
	UPROPERTY(EditDefaultsOnly, Category = "Red|Space|Moon")
	FVector MoonRelativeLocation = FVector(4800000.f, -3000000.f, 2000000.f);

	UPROPERTY(EditDefaultsOnly, Category = "Red|Space|Moon", meta = (ClampMin = "10000.0"))
	float MoonSurfaceRadiusCm = 90000.f;

	/** Gravity changes over only on approach, not halfway through ordinary planet orbit. */
	UPROPERTY(EditDefaultsOnly, Category = "Red|Space|Moon", meta = (ClampMin = "10000.0"))
	float MoonGravityInfluenceRadiusCm = 800000.f;

	/** Retired custom Saturn prototype. Retained only as source-level rollback data. */
	UPROPERTY(EditDefaultsOnly, Category = "Red|Space|Ring World")
	FVector RingWorldRelativeLocation = FVector(-2800000.f, 1600000.f, 800000.f);

	UPROPERTY(EditDefaultsOnly, Category = "Red|Space|Ring World", meta = (ClampMin = "50000.0"))
	float RingWorldSurfaceRadiusCm = 250000.f;

	UPROPERTY(EditDefaultsOnly, Category = "Red|Space|Ring World", meta = (ClampMin = "50000.0"))
	float RingWorldGravityInfluenceRadiusCm = 950000.f;

	/** Local moon offsets are relative to the ring-world centre, not the Mars centre. */
	UPROPERTY(EditDefaultsOnly, Category = "Red|Space|Ring World|Moons")
	FVector RingMoonARelativeOffset = FVector(1050000.f, 250000.f, 260000.f);

	UPROPERTY(EditDefaultsOnly, Category = "Red|Space|Ring World|Moons")
	FVector RingMoonBRelativeOffset = FVector(-1350000.f, -320000.f, -180000.f);

	UPROPERTY(EditDefaultsOnly, Category = "Red|Space|Ring World|Moons")
	FVector RingMoonCRelativeOffset = FVector(300000.f, 1550000.f, 420000.f);

	UPROPERTY(EditDefaultsOnly, Category = "Red|Space|Ring World|Moons")
	FVector RingMoonSurfaceRadiiCm = FVector(115000.f, 90000.f, 70000.f);

	UPROPERTY(EditDefaultsOnly, Category = "Red|Space|Ring World|Moons")
	FVector RingMoonGravityInfluenceRadiiCm = FVector(520000.f, 440000.f, 360000.f);

	UPROPERTY(EditDefaultsOnly, Category = "Red|Space|Ring World|Mining",
		meta = (ClampMin = "0", ClampMax = "96"))
	int32 RingMineableAsteroidCount = 32;

private:
	void BuildScenery();
	void ResolveHomePlanetFrame();
	void ResolveSunLight();
	void ResolveMoonLight();
	void UpdateMoonAlignment(float DeltaSeconds);
	void BuildRingWorld();
	void SpawnRingMineableAsteroids();
	void DisableLegacySaturnPrototype();
	float ComputeLocalNightFactor(const FVector& ViewLocation) const;
	void UpdateLocalSpacePresentation(float DeltaSeconds);
	void EnsureLocalSurfaceSky();
	void SetLocalSurfaceSkyVisible(bool bVisible);

	UPROPERTY(VisibleAnywhere, Category = "Red|Space")
	TObjectPtr<USceneComponent> SceneryRoot;

	/**
	 * Local camera-relative star shell. Three procedural-mesh sections carry the dim, medium,
	 * and bright magnitude layers. This deliberately avoids the instanced-static-mesh vertex
	 * factory: the cooked plume material has no ISM permutation and therefore rendered the
	 * previous HISM stars with the invisible default material in packaged builds.
	 */
	UPROPERTY(VisibleAnywhere, Category = "Red|Space")
	TObjectPtr<UProceduralMeshComponent> StarField;

	/**
	 * One camera-relative sky sphere rendered with a texture-free analytic star material.
	 * This is the primary packaged-client path; the procedural discs remain a safe fallback
	 * when the authored material is unavailable.
	 */
	UPROPERTY(VisibleAnywhere, Category = "Red|Space")
	TObjectPtr<UStaticMeshComponent> AnalyticStarDome;

	UPROPERTY(VisibleAnywhere, Category = "Red|Space")
	TObjectPtr<UHierarchicalInstancedStaticMeshComponent> Asteroids;

	UPROPERTY(VisibleAnywhere, Category = "Red|Space")
	TObjectPtr<UStaticMeshComponent> Moon;

	/** Slight emissive shell keeps the physical moon readable against the night sky. */
	UPROPERTY(VisibleAnywhere, Category = "Red|Space")
	TObjectPtr<UStaticMeshComponent> MoonGlow;

	/** Presentation-only gas giant. Its body and rings are explicitly collision-free. */
	UPROPERTY(VisibleAnywhere, Category = "Red|Space|Ring World")
	TObjectPtr<UStaticMeshComponent> RingWorldBody;

	UPROPERTY(VisibleAnywhere, Category = "Red|Space|Ring World")
	TObjectPtr<UProceduralMeshComponent> RingWorldBands;

	/** Three low-cost, collidable prototype moons that use RED's radial gravity query. */
	UPROPERTY(VisibleAnywhere, Category = "Red|Space|Ring World|Moons")
	TObjectPtr<UStaticMeshComponent> RingMoonA;

	UPROPERTY(VisibleAnywhere, Category = "Red|Space|Ring World|Moons")
	TObjectPtr<UStaticMeshComponent> RingMoonB;

	UPROPERTY(VisibleAnywhere, Category = "Red|Space|Ring World|Moons")
	TObjectPtr<UStaticMeshComponent> RingMoonC;

	/** Test-only low-energy key used to measure the moon without the planetary sun clipping it. */
	UPROPERTY(VisibleAnywhere, Category = "Red|Space")
	TObjectPtr<UDirectionalLightComponent> MoonAuditKeyLight;

	/**
	 * Local camera-only exposure guard. The bright surface grade stays untouched at
	 * ground level; this layer fades in near the atmosphere ceiling so black space
	 * cannot make eye adaptation bleach the sunlit planet.
	 */
	UPROPERTY(VisibleAnywhere, Category = "Red|Space")
	TObjectPtr<UPostProcessComponent> OrbitExposurePostProcess;

	/** Final active-camera exposure hand-off shared by character and ship views. */
	UPROPERTY(Transient)
	TObjectPtr<URedSpaceExposureCameraModifier> OrbitExposureCameraModifier;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> StarMaterialDynamic;
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> MediumStarMaterialDynamic;
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> BrightStarMaterialDynamic;
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> AnalyticStarDomeMaterialDynamic;
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> MoonGlowMaterialDynamic;
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> RingWorldMaterialDynamic;
	UPROPERTY(Transient)
	TArray<TObjectPtr<UMaterialInstanceDynamic>> RingBandMaterialDynamics;

	/** Purchased rim material selected only by the exact T04 moon-audit gate. */
	UPROPERTY(EditDefaultsOnly, Category = "Red|Space|Moon")
	TObjectPtr<UMaterialInterface> MoonFresnelGlowMaterial;

	/** Production fallback retained outside the disposable T04 moon audit. */
	UPROPERTY(EditDefaultsOnly, Category = "Red|Space|Moon")
	TObjectPtr<UMaterialInterface> MoonAdditiveGlowMaterial;

	/** Hard reference guarantees the analytic star material is cooked with Windows clients. */
	UPROPERTY(EditDefaultsOnly, Category = "Red|Space|Stars")
	TObjectPtr<UMaterialInterface> AnalyticStarDomeMaterial;

	/**
	 * Disposable Night_T03-only material used to validate the star render layer.
	 * It remains separate from the production material and is selected only by
	 * the isolated visual-test map at runtime.
	 */
	UPROPERTY(EditDefaultsOnly, Category = "Red|Space|Stars")
	TObjectPtr<UMaterialInterface> NightT03StarDiagnosticMaterial;

	/**
	 * Depth-independent additive proof used only by the non-Shipping T04 automatic
	 * capture. It isolates the procedural star render layer and is never promoted
	 * to normal gameplay because it can deliberately draw through the planet.
	 */
	UPROPERTY(EditDefaultsOnly, Category = "Red|Space|Stars")
	TObjectPtr<UMaterialInterface> NightWaterT04StarOverlayProofMaterial;

	/**
	 * Project-owned Night_T03-only sky material backed by the installed
	 * SpaceColony Milky Way texture. The vendor texture is referenced read-only;
	 * this material is selected only by the disposable visual-test map.
	 */
	UPROPERTY(EditDefaultsOnly, Category = "Red|Space|Stars")
	TObjectPtr<UMaterialInterface> NightT03MilkyWayMaterial;

	/** Known-rendering basic sphere used only by the Night_T03 Milky Way harness. */
	UPROPERTY(EditDefaultsOnly, Category = "Red|Space|Stars")
	TObjectPtr<UStaticMesh> NightT03BasicSphereMesh;

	/** Legacy inward-facing engine sky sphere retained as a read-only diagnostic input. */
	UPROPERTY(EditDefaultsOnly, Category = "Red|Space|Stars")
	TObjectPtr<UStaticMesh> NightT03SkySphereMesh;

	/** Hard reference keeps the fused surface sky material in cooked Windows clients. */
	UPROPERTY(EditDefaultsOnly, Category = "Red|Space|Surface Sky")
	TObjectPtr<UMaterialInterface> SurfaceBabyBlueSkyMaterial;

	/**
	 * So Stylized's clear sky is a local-only daytime backdrop. Its bundled
	 * clouds, lights, fog and post process are disabled so HI5 remains the only
	 * cloud layer and SkyAtmosphere remains responsible for the orbital limb.
	 */
	UPROPERTY(Transient)
	TObjectPtr<AActor> LocalStylizedSurfaceSky;
	UPROPERTY(Transient)
	TObjectPtr<UStaticMeshComponent> LocalStylizedSkyDome;
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> LocalStylizedSkyMaterial;

	FVector HomePlanetCenter = FVector::ZeroVector;
	float HomePlanetSurfaceRadiusCm = 600000.f;
	bool bHomePlanetFrameResolved = false;
	float BuiltSurfaceRadiusCm = 0.f;
	TWeakObjectPtr<UDirectionalLightComponent> CachedSunLight;
	TWeakObjectPtr<UDirectionalLightComponent> CachedMoonLight;
	float NextSunLookupTime = 0.f;
	float NextMoonLookupTime = 0.f;
	float NextPlanetFrameResolveTime = 0.f;
	bool bHasLoggedStarVisibility = false;
	bool bLastStarsVisible = false;
	bool bMoonAlignedToFill = false;
	bool bLocalSurfaceSkyVisible = false;
	bool bHasLoggedOrbitExposureActive = false;
	/** The cooked additive fallback exposes HDR Color but no Emission parameter. */
	bool bStarMaterialUsesEmissionParameter = false;
	bool bAnalyticStarDomeReady = false;
	bool bUsingNightT03MilkyWaySky = false;
	bool bUsingNightWaterT04StarOverlayProof = false;
	bool bUsingNightWaterT04MoonAudit = false;
	bool bRingWorldBuilt = false;
	int32 DimStarCount = 0;
	int32 MediumStarCount = 0;
	int32 BrightStarCount = 0;
};
