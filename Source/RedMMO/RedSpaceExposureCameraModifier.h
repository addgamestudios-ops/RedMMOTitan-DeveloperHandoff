#pragma once

#include "Camera/CameraModifier.h"
#include "CoreMinimal.h"
#include "RedSpaceExposureCameraModifier.generated.h"

class UCurveFloat;

/**
 * Final-camera exposure hand-off for the fused small planet.
 *
 * A post-process component on a world actor is blended before some pawn and
 * vehicle camera overrides.  That let the surface camera look acceptable while
 * the same sunlit planet clipped to white from orbit.  A camera modifier is
 * evaluated by APlayerCameraManager after the active character/ship camera has
 * produced its POV, so the transition is identical in every view mode.
 */
UCLASS(NotBlueprintable, Transient)
class REDMMO_API URedSpaceExposureCameraModifier final : public UCameraModifier
{
	GENERATED_BODY()

public:
	URedSpaceExposureCameraModifier(const FObjectInitializer& ObjectInitializer);

	void SetPlanetFrame(const FVector& InCenter, float InSurfaceRadiusCm,
		bool bInFusedPrototype);

	/**
	 * Applies a local-only guard after sunset.  The daylight sky continues to use the
	 * production histogram response; only the dark physical-sky interval is constrained.
	 */
	void SetSurfaceNightExposure(float InNightFactor);

	virtual bool ModifyCamera(float DeltaTime, FMinimalViewInfo& InOutPOV) override;

private:
	void ConfigureOrbitExposure(FPostProcessSettings& PostProcessSettings,
		bool bNightWaterT04OrbitValidation) const;
	void ConfigureSurfaceNightExposure(FPostProcessSettings& PostProcessSettings) const;

	UPROPERTY(Transient)
	TObjectPtr<UCurveFloat> FlatExposureBiasCurve;

	FVector PlanetCenter = FVector::ZeroVector;
	float PlanetSurfaceRadiusCm = 600000.f;
	float OrbitExposureAlpha = 0.f;
	float SurfaceNightExposureAlpha = 0.f;
	bool bFusedPrototype = false;
	TWeakObjectPtr<AActor> LastLoggedOrbitViewTarget;
};
