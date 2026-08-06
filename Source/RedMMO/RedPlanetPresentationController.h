#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "RedPlanetPresentationController.generated.h"

/**
 * Altitude-driven planet presentation switch.
 *
 * From orbit, the live voxel world should not be the primary visual surface:
 * it is expensive and exposes chunk/LOD bands. This controller keeps a cheap,
 * generated orbit proxy visible from space, then hands visibility back to the
 * real VibeVoxel detail layer as the camera approaches the atmosphere.
 */
UCLASS()
class REDMMO_API ARedPlanetPresentationController : public AActor
{
	GENERATED_BODY()

public:
	ARedPlanetPresentationController();

	virtual void BeginPlay() override;
	virtual void OnConstruction(const FTransform& Transform) override;
	virtual void Tick(float DeltaSeconds) override;
	virtual bool ShouldTickIfViewportsOnly() const override;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet")
	FVector PlanetCenter = FVector::ZeroVector;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet", meta = (ClampMin = "1.0"))
	float PlanetRadius = 382000.0f;

	/**
	 * Radius measured from the visible voxel/proxy shell bounds.
	 *
	 * Informational only by default. Generated sky/proxy shells can have huge
	 * bounds, and using those bounds for gameplay creates the fake invisible
	 * layer the player and ship were standing on.
	 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet")
	float CalibratedVisualSurfaceRadius = 0.0f;

	/** Legacy escape hatch for maps that intentionally want gameplay to follow a measured visual shell. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet")
	bool bUseVisualBoundsForGameplaySurface = false;

	/** Maximum extra radius visual calibration can add when the legacy option is enabled. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet", meta = (ClampMin = "0.0"))
	float MaxVisualSurfaceCalibrationDelta = 25000.0f;

	/**
	 * Small visual clearance above the authored gameplay radius.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet", meta = (ClampMin = "0.0"))
	float SurfaceVisualClearance = 0.0f;

	/**
	 * Invisible fallback gameplay shell for PIE.
	 *
	 * VibeVoxel owns the detailed surface, but on Mac UE 5.8 collision can be
	 * late or absent while voxel chunks build. This sphere gives CharacterMovement
	 * a stable walkable planet surface so the player does not fall through the
	 * visual/proxy planet during playtests.
	 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet")
	TObjectPtr<class USphereComponent> GameplaySurfaceCollider;

	/** Emergency-only PIE helper. Keep off for the real VibeVoxel desert planet proof. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet")
	bool bEnableGameplaySurfaceFallbackCollider = false;

	/**
	 * Debug-only fallback shell that matches the gameplay collider.
	 *
	 * Keep this disabled for the voxel desert proof. If this is visible, PIE can
	 * look like the player is standing on a fake helper planet instead of the
	 * actual voxel terrain.
	 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet")
	TObjectPtr<class UStaticMeshComponent> GameplaySurfaceVisual;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet")
	TObjectPtr<class UMaterialInterface> SurfaceVisualMaterial;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet")
	bool bShowGameplaySurfaceVisual = false;

	/** Above this altitude, prefer the cheap proxy and hide voxel detail. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet|LOD", meta = (ClampMin = "0.0"))
	float FarProxyOnlyAltitude = 3500000.0f;

	/** Below this altitude, the voxel terrain is close enough to become the primary detail layer. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet|LOD", meta = (ClampMin = "0.0"))
	float NearVoxelDetailAltitude = 900000.0f;

	/** Prevents rapid toggling near the thresholds. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet|LOD", meta = (ClampMin = "0.0"))
	float HysteresisAltitude = 800000.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet|LOD")
	FName OrbitProxyTag = TEXT("VibeOrbitProxy");

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet|LOD")
	FName VoxelDetailTag = TEXT("VibeVoxelDetail");

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet|Sky")
	FName SurfaceSkyTag = TEXT("VibeSurfaceSky");

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet|Sky")
	FName OrbitBackdropTag = TEXT("VibeOrbitBackdrop");

	/** Above this altitude, the generated orbit starfield can appear behind the planet. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet|Sky", meta = (ClampMin = "0.0"))
	float OrbitBackdropVisibleAltitude = 10000000.0f;

	/** Below this altitude, keep the accepted SoStylized surface sky visible for a long atmosphere overlap. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet|Sky", meta = (ClampMin = "0.0"))
	float SurfaceSkyVisibleAltitude = 14000000.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet|LOD")
	bool bTickInEditor = true;

	/**
	 * Temporary UE 5.8 presentation guard.
	 *
	 * The live VibeVoxel render shells currently expose obvious rings from the
	 * ground and from orbit. Keep the smooth proxy as the visible planet layer
	 * until the voxel LOD/material shell path is repaired; voxel collision can
	 * still exist underneath for playtests.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RedMMO|Planet|LOD")
	bool bForceProxyOnlyUntilVoxelShellFix = false;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|LOD")
	float LastAltitude = 0.0f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|LOD")
	bool bUsingFarProxy = true;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RedMMO|Planet|Sky")
	bool bUsingOrbitBackdrop = false;

	/** Rescans tagged actors. Useful after generated actors are added in editor. */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|Planet|LOD")
	void RefreshPresentationActors();

	UFUNCTION(BlueprintCallable, Category = "RedMMO|Planet")
	float GetPlayableSurfaceRadius() const;

	UFUNCTION(BlueprintCallable, Category = "RedMMO|Planet")
	float GetGameplaySurfaceRadius() const;

	UFUNCTION(BlueprintCallable, Category = "RedMMO|Planet")
	FVector GetSurfaceNormalAt(const FVector& WorldLocation) const;

	UFUNCTION(BlueprintCallable, Category = "RedMMO|Planet")
	FVector GetSurfaceLocationForActor(const FVector& WorldLocation, float ActorHalfHeight = 0.0f, float ExtraClearance = 0.0f) const;

protected:
	class USphereComponent* EnsureGameplaySurfaceCollider();
	void RefreshGameplaySurfaceCollider();
	class UStaticMeshComponent* EnsureGameplaySurfaceVisual();
	void RefreshGameplaySurfaceVisual();
	bool ResolveViewLocation(FVector& OutLocation) const;
	void ApplyPresentationState(bool bUseFarProxy);
	void ApplySkyPresentationState();
	static void SetActorPresentationVisible(AActor* Actor, bool bVisible);

private:
	UPROPERTY(Transient)
	TArray<TObjectPtr<AActor>> OrbitProxyActors;

	UPROPERTY(Transient)
	TArray<TObjectPtr<AActor>> VoxelDetailActors;

	UPROPERTY(Transient)
	TArray<TObjectPtr<AActor>> SurfaceSkyActors;

	UPROPERTY(Transient)
	TArray<TObjectPtr<AActor>> OrbitBackdropActors;
};
