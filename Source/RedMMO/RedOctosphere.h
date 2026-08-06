#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "RedOctosphere.generated.h"

class UStaticMeshComponent;
class UMaterialInterface;
class UExponentialHeightFogComponent;
class UWorldPartitionStreamingSourceComponent;

/**
 * The Octosphere skeleton (FLAT-ILLUSION model, see Octosphere_Implementation_Guide.md).
 *
 * The planet is an octahedron of 8 faces. Each face is a ZONE that maps to a flat playable area.
 * You never pick a zone from a menu — your position/descent direction relative to the planet
 * center picks it (the octant you're over). This actor holds the octahedral math + the face->zone
 * registry + the altitude state (orbit / approach / surface); streaming + the impostor visual layer
 * on top of it.
 *
 * FLAT-ILLUSION: gravity on the ground stays straight-down (flat maps); the "sphere" is only the
 * orbital arrangement of the 8 zones + the descent transition. So this actor is the NAVIGATION /
 * streaming brain, not a real curved-gravity planet.
 */
UENUM(BlueprintType)
enum class ERedOctoLayer : uint8
{
	Orbit    UMETA(DisplayName = "Orbit (impostor)"),      // far: see the whole planet, no zone streamed
	Approach UMETA(DisplayName = "Approach (HLOD)"),        // descending: target zone streaming in
	Surface  UMETA(DisplayName = "Surface (flat zone)")     // landed: on the flat zone
};

UCLASS()
class REDMMO_API ARedOctosphereManager : public AActor
{
	GENERATED_BODY()

public:
	ARedOctosphereManager();

	/** Planet center in world space (the octant math is measured from here). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Octosphere")
	FVector PlanetCenter = FVector::ZeroVector;

	/** Nominal surface radius (cm). Altitude = dist(loc, center) - radius. Tunable for the prototype. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Octosphere")
	float PlanetRadius = 400000.f;

	/** Altitude (cm) below which the target zone is fully streamed and playable. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Octosphere")
	float SurfaceAltitude = 1000000.f;   // 10 km

	/** Altitude (cm) above which nothing streams (pure orbit / impostor). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Octosphere")
	float OrbitAltitude = 10000000.f;    // 100 km

	/** One entry per face (index 0..7) — the flat zone/level name that streams for that face. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Octosphere")
	TArray<FName> FaceZoneNames;

	/** Which face the local player is currently over/descending toward (server-authoritative). */
	UPROPERTY(Replicated, BlueprintReadOnly, Category = "Octosphere")
	int32 ActiveFaceIndex = 0;

	/** Current LOD layer of the local player. */
	UPROPERTY(BlueprintReadOnly, Category = "Octosphere")
	ERedOctoLayer ActiveLayer = ERedOctoLayer::Orbit;

	// --- The Drop: trajectory-picked target + descent HUD state (milestone #50) ---

	/** Zone name the descent trajectory is currently aimed at (server-authoritative, follows ActiveFaceIndex). */
	UPROPERTY(Replicated, BlueprintReadOnly, Category = "Octosphere|Drop")
	FName TargetZoneName;

	/** Local player's altitude above the (virtual) surface, cm. */
	UPROPERTY(BlueprintReadOnly, Category = "Octosphere|Drop")
	float ActiveAltitude = 0.f;

	/** 0 at the drop start altitude, 1 at the ground. */
	UPROPERTY(BlueprintReadOnly, Category = "Octosphere|Drop")
	float DescentProgress01 = 0.f;

	/** True once the target face has frozen (below LockAltitude) until the next orbit/redrop. */
	UPROPERTY(BlueprintReadOnly, Category = "Octosphere|Drop")
	bool bTargetLocked = false;

	/** Set by the pawn while it is actually diving (drives the HUD "[DIVING]" flag). */
	UPROPERTY(BlueprintReadOnly, Category = "Octosphere|Drop")
	bool bDropInProgress = false;

	/** Altitude (cm) at/below which the trajectory-picked target face freezes. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Octosphere|Drop")
	float LockAltitude = 450000.f;

	/** Altitude (cm) the current drop started from — the span the descent progress bar fills over. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Octosphere|Drop")
	float DropStartAltitude = 1000000.f;

	UPROPERTY(EditAnywhere, Category = "Octosphere|Drop")
	bool bShowDropHUD = true;

	UPROPERTY(EditAnywhere, Category = "Octosphere|Drop")
	bool bShowLayerVisuals = true;

	// --- Ground landing markers: where each falling diver is aimed (the "incoming here" ground read) ---
	UPROPERTY(EditAnywhere, Category = "Octosphere|Marker")
	bool bShowLandingMarkers = true;
	UPROPERTY(EditAnywhere, Category = "Octosphere|Marker")
	FLinearColor MarkerColor = FLinearColor(1.f, 0.05f, 0.02f);
	UPROPERTY(EditAnywhere, Category = "Octosphere|Marker")
	float MarkerMaxRadius = 1200.f;
	UPROPERTY(EditAnywhere, Category = "Octosphere|Marker")
	float MarkerBeamHeight = 30000.f;

	// --- Planet PROXY: the visible sphere seen from orbit that hides on the ground (the flat-illusion) ---
	/** The impostor planet: a sphere mesh centered at PlanetCenter, sized to PlanetRadius, shown in
	 *  Orbit/Approach and hidden at Surface. This is what makes the flat face read as a whole planet
	 *  while you fly in — you land into the flat square once it hides. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Octosphere|Proxy")
	TObjectPtr<UStaticMeshComponent> PlanetProxyMesh;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Octosphere|Proxy")
	TObjectPtr<UMaterialInterface> PlanetProxyMaterial;

	// CLOUD-DIVE: the visible impostor sphere is OFF by default. Staring at a flat-tile-as-sphere was
	// what exposed the streaming + the flat/curved seam; instead you fall through an opaque cloud deck
	// that hides the whole handoff and emerge onto pre-streamed terrain. Set true to bring the sphere back.
	UPROPERTY(EditAnywhere, Category = "Octosphere|Proxy")
	bool bShowPlanetProxy = false;

	/** Pins a WorldPartition streaming source to this actor (parked on the landing spot) so the target
	 *  cell is loaded before the diver emerges below the clouds — no half-loaded checkerboard tiles. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Octosphere|Proxy")
	TObjectPtr<UWorldPartitionStreamingSourceComponent> LandingStreamSource;

	// --- Atmosphere-entry blend (NMS-style): hide the flat-tile<->sphere seam inside a cloud/whiteout
	//     band, and fog the tile's far edge into a matching horizon. All keyed off ActiveAltitude. ---
	/** Surface (near-ground) height-fog density the descent ramps UP to — hazes the far tile edge so it
	 *  dissolves into the horizon instead of reading as a hard line. Orbit stays near-clear for the sphere. */
	UPROPERTY(EditAnywhere, Category = "Octosphere|Blend", meta = (ClampMin = "0.0"))
	float SurfaceFogDensity = 0.0006f;
	/** Warm desert horizon tint the descent fog fades to (matches the sphere's lit sand limb). */
	UPROPERTY(EditAnywhere, Category = "Octosphere|Blend")
	FLinearColor DescentFogColor = FLinearColor(0.82f, 0.70f, 0.52f);
	UPROPERTY(EditAnywhere, Category = "Octosphere|Blend")
	bool bDeckWhiteout = true;

	/** Point the manager at the station's virtual planet + scale the layer thresholds to the drop height. */
	UFUNCTION(BlueprintCallable, Category = "Octosphere|Drop")
	void ConfigureForDrop(const FVector& Center, float Radius, float InDropAltitude);

	/** The pawn calls this on StartSkydive/StopSkydive. */
	UFUNCTION(BlueprintCallable, Category = "Octosphere|Drop")
	void SetDropInProgress(bool bInDropping) { bDropInProgress = bInDropping; }

	/** Cast the fall path (position + velocity) onto the virtual surface sphere; returns the landing
	 *  direction from PlanetCenter (bOutValid false if the ray misses / velocity is ~0). */
	UFUNCTION(BlueprintPure, Category = "Octosphere|Drop")
	FVector ProjectTrajectoryToSurfaceDir(const FVector& WorldLocation, const FVector& WorldVelocity, bool& bOutValid) const;

	// --- Pure octahedral math (lifted from the guide's OctosphereConstants) ---

	/** Which of the 8 octahedron faces a unit direction (from the planet center) is over. */
	UFUNCTION(BlueprintPure, Category = "Octosphere")
	static int32 FaceIndexForDirection(const FVector& DirFromCenter);

	/** The outward center direction (unit) of a face — one of the eight ±0.577 corners. */
	UFUNCTION(BlueprintPure, Category = "Octosphere")
	static FVector FaceCenterDir(int32 FaceIndex);

	/** The three faces sharing an edge with FaceIndex. */
	UFUNCTION(BlueprintPure, Category = "Octosphere")
	static void GetAdjacentFaces(int32 FaceIndex, int32& OutA, int32& OutB, int32& OutC);

	/** Face index for a world location (measured from PlanetCenter). */
	UFUNCTION(BlueprintPure, Category = "Octosphere")
	int32 GetFaceIndexForLocation(const FVector& WorldLocation) const;

	/** Altitude above the nominal surface (cm) for a world location. */
	UFUNCTION(BlueprintPure, Category = "Octosphere")
	float GetAltitude(const FVector& WorldLocation) const;

	/** LOD layer for a given altitude. */
	UFUNCTION(BlueprintPure, Category = "Octosphere")
	ERedOctoLayer LayerForAltitude(float Altitude) const;

	/** The zone name mapped to a face (NAME_None if unset). */
	UFUNCTION(BlueprintPure, Category = "Octosphere")
	FName GetZoneForFace(int32 FaceIndex) const;

protected:
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

private:
	/** Per-tick: recompute altitude/layer, the trajectory-picked target face (authority), and the lock. */
	void UpdateDropState(const FVector& Loc, const FVector& Velocity);
	void DrawDropHUD() const;
	void DrawLayerVisuals() const;
	void OnLayerChanged(ERedOctoLayer From, ERedOctoLayer To);
	/** Flat-illusion core: hide the real flat ground (Landscape) from orbit so only the planet-proxy
	 *  sphere is seen; reveal it on approach so you "land into the square". Also ALWAYS hides the broken
	 *  WorldPartitionHLOD proxies (the checkerboard). Re-applied each tick to catch WP-streamed cells. */
	void SetGroundWorldHidden(bool bHidden);
	bool bGroundHidden = false;

	/** Drive the white "atmosphere-entry" camera fade so both the ground-reveal and sphere-hide happen
	 *  INSIDE the whiteout band (the seam is never seen in clear air). */
	void DriveDeckWhiteout();
	/** Ramp height-fog density from near-clear (orbit, sphere crisp) to SurfaceFogDensity (surface,
	 *  tile edge dissolved), keyed off ActiveAltitude. */
	void DriveDescentFog();
	/** Find + one-time-configure the level's ExponentialHeightFog for the descent blend. */
	void ConfigureDescentFog();

	// Deck band + swap altitudes (cm), derived from the drop height in ConfigureForDrop.
	float DeckTopAlt = 0.f;      // enter whiteout (Orbit->Approach)
	float DeckMidAlt = 0.f;      // peak whiteout
	float DeckBottomAlt = 0.f;   // exit whiteout (Approach->Surface)
	float GroundRevealAlt = 0.f; // reveal the flat tile (inside the whiteout)
	float SphereHideAlt = 0.f;   // hide the proxy sphere (inside the whiteout)
	bool bManagingCameraFade = false;
	float OrbitFogDensity = 0.0002f;   // near-clear so the orbit sphere stays crisp

	UPROPERTY()
	TObjectPtr<UExponentialHeightFogComponent> CachedFog;
	/** Draw a red beam + shrinking ring at every falling diver's predicted landing spot. */
	void DrawLandingMarkers() const;

	/** Last layer we fired a transition cue for (so cues fire exactly once). */
	ERedOctoLayer LastLayerForCue = ERedOctoLayer::Orbit;
};
