#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "RedGameMode.generated.h"

class ARedOrbitalMiningSite;
class ARedCloningStation;
class ARedOctosphereManager;
class ARedFoliageField;
class APostProcessVolume;
class AHeterogeneousVolume;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class UMaterialParameterCollection;
class UStaticMesh;

/** Minimal persistent-world GameMode: spawns the clean Red character with a standard controller. */
UCLASS()
class REDMMO_API ARedGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	ARedGameMode();

	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void RestartPlayer(AController* NewPlayer) override;
	virtual APawn* SpawnDefaultPawnAtTransform_Implementation(AController* NewPlayer, const FTransform& SpawnTransform) override;

	/** Per-frame ship handling on the CLM sphere: PARKED shuttles are re-leveled to radial up (gear on the
	 *  surface); a BOARDED shuttle is FLOWN by RED in the planet's radial frame (level to the surface,
	 *  thrust along the surface, A/D to steer, Space/Ctrl to climb/descend) — because the flat-world pack
	 *  ship flies in world space and reads as sideways/uncontrollable on a sphere. No-op on flat maps. */
	void UpdateSpaceships(float DeltaSeconds);

	/** Max radial flight speed (cm/s) for the RED-driven ship. */
	UPROPERTY(EditAnywhere, Category = "RedMMO|Ship")
	float ShipFlightThrust = 22000.f;   // ~220 m/s cruise (Shift boosts)

	/** How fast the ship ramps to/from target speed (higher = snappier, lower = floatier). Inertia. */
	UPROPERTY(EditAnywhere, Category = "RedMMO|Ship")
	float ShipFlightAccel = 1.6f;

	/** Extra keyboard yaw (deg/s) from A/D, on top of mouse aim. */
	UPROPERTY(EditAnywhere, Category = "RedMMO|Ship")
	float ShipFlightYawSpeed = 45.f;

	/** Hold-Shift boost multiplier. */
	UPROPERTY(EditAnywhere, Category = "RedMMO|Ship")
	float ShipFlightBoost = 3.f;

private:
	/** The shuttle RED is currently flying (boarded), plus its smoothed velocity for inertia. */
	UPROPERTY()
	TObjectPtr<APawn> PilotedShip = nullptr;
	FVector PilotedVelocity = FVector::ZeroVector;

public:

	// --- Sci-fi theme strip (#58) ---
	/** Remove the Project Titan fantasy structures (shops/taverns/markets/temples/villages/carnival)
	 *  that clash with the sci-fi theme. Runtime removal keyed to the /Game/Environment content folders;
	 *  re-catches actors as World Partition streams them in. Set false to restore the original set. */
	UPROPERTY(EditAnywhere, Category = "RedMMO|Theme")
	bool bStripFantasyBuildings = true;

	/** Temporary desert/ocean-only pass. Turn this off later before hand-placing approved props. */
	UPROPERTY(EditAnywhere, Category = "RedMMO|Theme")
	bool bSuppressProceduralSurfaceDressing = true;

	/** Extra gap above the playable planet surface after capsule half-height is applied. */
	UPROPERTY(EditAnywhere, Category = "RedMMO|Spawn", meta = (ClampMin = "0.0"))
	float SpawnSurfaceGap = 1000.0f;

	/** Spawn the first orbital asteroid/mining facility so Mars/moon space has a real mining target. */
	UPROPERTY(EditAnywhere, Category = "RedMMO|Mining")
	bool bSpawnOrbitalMiningSite = false;

	/** Height above the gameplay surface for the default orbital mining site. */
	UPROPERTY(EditAnywhere, Category = "RedMMO|Mining", meta = (ClampMin = "10000.0"))
	float OrbitalMiningSiteSurfaceAltitude = 150000000.0f;

	// --- The Drop (milestone #50) ---

	/** Spawn the orbital cloning station and start/respawn the player diving from it.
	 *  OFF for now — spawn directly on the ground (the drop/orbit is re-enabled later once landing is solid). */
	UPROPERTY(EditAnywhere, Category = "RedMMO|Drop")
	bool bStartAtCloningStation = false;

	/** Height (cm) of the cloning-station deck above the landing ground. Tunable for drop length/feel:
	 *  raise it (and/or SkydiveMaxFallSpeed on the pawn) for a taller, longer dive. */
	UPROPERTY(EditAnywhere, Category = "RedMMO|Drop", meta = (ClampMin = "10000.0"))
	float CloningStationDropAltitude = 60000.f;   // ~600 m — ~20s glide at the current skydive tunables

	/** Virtual planet radius the octant math is measured against (large = near-flat altitude). */
	UPROPERTY(EditAnywhere, Category = "RedMMO|Drop", meta = (ClampMin = "100000.0"))
	float CloningStationVirtualRadius = 4000000.f;   // 40 km

	/** OFF (2026-07-07): on the baked SciFiHub hub there are no cells to stream, so we do NOT free-fall
	 *  onto a fixed point (that -10000 spawn was the "fall through half-loaded terrain" bug). False =>
	 *  RedGameMode spawns the trooper standing at the hub's PlayerStart. Only used by the retired drop. */
	UPROPERTY(EditAnywhere, Category = "RedMMO|Drop")
	bool bUseFixedDropGround = false;
	// OPEN FLAT LOWLAND, scan-picked 2026-07-06: a downward line-trace grid found this the flattest
	// (Δ209 over 2.5km neighbours), cliff-free Landscape spot — the volcano flank kept dropping the
	// pawn into a ravine whose walls collapsed the third-person camera to a top-down view. Ground is
	// ~-16223; spawn a few km up so the pawn free-falls onto it while cells stream in.
	// DESERT PLANET landing point (2026-07-07): the SoStylized Demonstration_Desert hero spot near the
	// oasis (ground ~z900). The octosphere virtual planet's NORTH POLE sits here, so the diver free-falls
	// from OctoTestDropAltitude straight down onto the real baked desert island. No streaming, no HLOD.
	UPROPERTY(EditAnywhere, Category = "RedMMO|Drop")
	FVector FixedDropGroundPoint = FVector(10566.f, 35180.f, 900.f);

	// --- Octosphere (flat-illusion) — REVIVED 2026-07-07 on the baked SoStylized desert ---
	// ON: spawn high in orbit → see the desert-planet proxy sphere → free-fall through a whiteout band
	// that hides the sphere + reveals the real desert → land on the baked island. This broke before ONLY
	// because it sat on the STREAMED TitanMain (broken HLOD = checkerboard, unstreamed cells = missing
	// pieces). On the baked non-WP desert there is no streaming/HLOD, and the island's ocean border hides
	// the tile edge — so the illusion finally reads as a real planet you land on. The proxy sphere is
	// turned visible in EnsureOctosphereManager (bShowPlanetProxy=true).
	// TEMP for the multiplayer netcode test: false = ground spawns (the octosphere drop returns ONE
	// fixed point with no per-player offset, so 2 players stack). Re-enable with a per-player drop
	// offset once see+shoot is proven in split-screen PIE.
	// TEMP 2026-07-08 for the BP_Shuttle pilot test: false = trooper spawns STANDING at the desert
	// PlayerStart with plain -Z gravity (matches the shuttle's world-space FloatingPawnMovement) so you
	// can walk straight to the parked ship, press V, and fly. Flip back to true to restore the orbital drop.
	UPROPERTY(EditAnywhere, Category = "RedMMO|Octosphere")
	bool bOctosphereTest = false;
	/** Virtual planet radius (cm) — the sphere the flat face is the north-pole tangent tile of. */
	UPROPERTY(EditAnywhere, Category = "RedMMO|Octosphere")
	float OctoTestRadius = 1000000.f;        // 10 km
	/** Altitude (cm) above the face to spawn at — the free-fall descent length. Tuned to 3.5 km: the
	 *  SoStylized island is only ~1 km wide, so from 5-8 km it's an unreadable speck; at ~3.5 km and below
	 *  it fills the frame as a coral landmass ringed by ocean — the "diving onto the desert planet" look. */
	UPROPERTY(EditAnywhere, Category = "RedMMO|Octosphere")
	float OctoTestDropAltitude = 350000.f;   // 3.5 km — the readable-island descent band

	// ---- CLM mesh-planet orbital drop (the octosphere on the REAL streaming sphere) ----
	/** Spawn the diver HIGH on the radial above the surface point and free-fall into the CLM mesh planet.
	 *  SELF-GATING: only fires when a CLM mesh planet exists in the level (RedGravity::FindMeshPlanet), so
	 *  it's a harmless no-op on the flat desert / Titan maps. This is the octosphere drop on RedPlanetGen.
	 *  Verified 80-100 fps for the whole warm descent (the "3 fps" scare was cold shader-compile on the
	 *  FIRST PIE + a polluted test session, NOT a real render/trace cost). */
	UPROPERTY(EditAnywhere, Category = "RedMMO|Drop")
	bool bMeshPlanetDrop = false;   // TEMP off: standing spawn at the lit spot to perfect the desert look; flip true to restore the drop
	/** Altitude (cm) above the CLM surface to spawn the diver. Kept LOW so you drop into the local area
	 *  (not the whole planet) and the fall is a snappy ~15-30 s (Fortnite dive: look down to plunge,
	 *  level out to glide). Real fall = this + the ~500 m peak-to-terrain gap. */
	UPROPERTY(EditAnywhere, Category = "RedMMO|Drop", meta = (ClampMin = "10000.0"))
	float MeshPlanetDropAltitude = 200000.f;   // 2 km nominal (~2.5 km real fall)

	ARedCloningStation* GetCloningStation() const { return SpawnedCloningStation; }

	// --- Desert ZONES (#59): one baked desert re-lit + colour-graded into 8 distinct drop-zones ---
	/** Which of the 8 desert moods is active (Dawn Dunes / Blood Noon / Amethyst Dusk / …). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Zones")
	int32 ZoneIndex = 0;

	/** Apply a zone mood: retint the sun + drive an unbound colour-grade volume. Wraps 0..7. */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|Zones")
	void ApplyZoneMood(int32 Index);

	/** Spawn/repair SpaceStarDome A/B. Player destroys them on the ground (additive leak) and
	 *  calls this again when entering space. */
	void EnsureSpaceStarDomes();

private:
	FTransform BuildPlanetSpawnTransform(AController* NewPlayer, AActor* PreferredStart);
	void EnsureOrbitalMiningSite(AActor* PreferredStart);
	void EnsureCloningStation(AActor* PreferredStart);
	void EnsureOctosphereManager();
	// Adds a real-time SkyLight if the map has none (ambient fill after Lumen was disabled).
	void EnsureSkyLight();
	/** Wait for PlanetGen collision, then park the production shuttle/fighter beside PlayerStart. */
	void EnsureSpawnVehiclesOnPlanetSurface();
	/** Force the ~1 km atmosphere shell and keep the real volumetric cloud paths enabled. */
	void EnsureAtmosphereAndClouds();
	/** Smoothly remove HI-5 VDB banks from the night-side terminator before their
	 * finite volume bounds can read as rectangular black steps. */
	void UpdateHighFiveCloudLighting(float DeltaSeconds);
	/** Destroy leftover RedCloudCard SM_Cloud/Plane actors — do not respawn (clear sky preferred). */
	void EnsureSparseCloudCards();
	/** Repair/spawn twelve colored High Five volumes in equal angular cells around the atmosphere. */
	void EnsureHighFiveCloudVolumes(
		const FVector& PlanetCenter, float PlanetRadiusCm, float PlanetPeakRadiusCm,
		float AtmosphereHeightCm);

	/**
	 * Mars dune look (safe path): keep PlanetGen MI_PlanetBiome_RED (sphere UVs) as TerrainMaterial,
	 * boost SandMult. Never overwrite chunk meshes with MF_DesertSand / world-XY mats (stripes).
	 * SoStylized T_DesertSand_* are wired into Sand LayerParameter via editor tools (asset-side).
	 */
	void EnsureSoStylizedSandOnPlanetTerrain();

	/** Surface-trace SoStylized water/rocks and desert ridges near spawn; never spawn palms. */
	void EnsureOasisTerraformingPockets();
	/** Apply the same SoStylized waves material to the PlanetGen/ocean surface components. */
	void EnsureSoStylizedOceanWater();
	/** Resolve a disposable direct child only on NightWater_T04; production uses the CDO material. */
	UMaterialInterface* ResolveSoStylizedWaterMaterialForCurrentMap() const;
	/** Map-local bridge for the vendor water material's day-cycle collection; restores on EndPlay. */
	void ConfigureNightWaterT04MaterialBridge();
	void RestoreNightWaterT04MaterialBridge();
	/** Spawn one deterministic, trace-bounded biome field around the initial playable region. */
	void EnsureProceduralBiomeField();
	/** Remove old/generated foliage, rocks, cliffs, and snow accents; preserve terrain and water. */
	void RemoveProceduralSurfaceDressing();

	// Fantasy-building strip (#58): hide Titan settlement art, incl. actors WP streams in later.
	void StripFantasyActor(AActor* Actor);
	bool IsFantasyBuildingActor(const AActor* Actor) const;
	/** Titan open-world POI beacons (yellow region / fast-travel markers) — matched by CLASS name
	 *  (their yellow visual is a world-space UI widget, not a /game/environment/ mesh). */
	bool IsPointOfInterestMarker(const AActor* Actor) const;
	void SweepFantasyActors();
	/** Hide matching Titan content the frame its World Partition cell streams in — kills the "flashing
	 *  in and out every couple seconds" the timer sweep left (content was visible until the next tick). */
	void OnLevelAddedToWorld(ULevel* Level, UWorld* World);

	FTimerHandle FantasyStripSweepTimer;
	FTimerHandle SoStylizedSandRetryTimer;
	FTimerHandle AtmosphereCloudRetryTimer;
	FTimerHandle VehicleSurfacePlacementTimer;
	FTimerHandle OasisTerraformTimer;
	FTimerHandle ProceduralBiomeTimer;
	int32 SoStylizedSandRetryCount = 0;
	int32 AtmosphereCloudRetryCount = 0;
	int32 VehicleSurfacePlacementAttempts = 0;
	FDelegateHandle LevelAddedHandle;

	/** CDO-hard references keep the external art packs reachable by Win64 cooks. */
	UPROPERTY()
	TObjectPtr<UStaticMesh> SoStylizedWaterMesh;

	UPROPERTY()
	TObjectPtr<UMaterialInterface> SoStylizedWaterMaterial;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialParameterCollection> NightWaterT04EnvironmentCollection;
	float NightWaterT04PreviousDayCycleProgress = 0.f;
	bool bNightWaterT04MpcOverrideApplied = false;

	UPROPERTY()
	TArray<TObjectPtr<UMaterialInterface>> HighFiveCloudMaterials;

	/** Per-bank color/density overrides; inherited SVT bindings remain untouched. */
	UPROPERTY(Transient)
	TArray<TObjectPtr<UMaterialInstanceDynamic>> HighFiveCloudDynamicMaterials;

	UPROPERTY(Transient)
	TArray<TObjectPtr<AHeterogeneousVolume>> HighFiveCloudVolumes;

	float HighFiveCloudLightingAccumulator = 0.f;

	UPROPERTY()
	TObjectPtr<ARedFoliageField> ProceduralBiomeField;

	int32 SpawnSequence = 0;

	UPROPERTY()
	TObjectPtr<ARedOrbitalMiningSite> SpawnedOrbitalMiningSite;

	UPROPERTY()
	TObjectPtr<ARedCloningStation> SpawnedCloningStation;

	UPROPERTY()
	TObjectPtr<ARedOctosphereManager> SpawnedOctosphereManager;

	// Reused unbound post-process volume carrying the active zone's colour grade.
	UPROPERTY()
	TObjectPtr<APostProcessVolume> ZoneMoodPPV;
};
