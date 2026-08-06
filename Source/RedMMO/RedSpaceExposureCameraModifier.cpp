#include "RedSpaceExposureCameraModifier.h"

#include "Camera/CameraTypes.h"
#include "Camera/PlayerCameraManager.h"
#include "Curves/CurveFloat.h"
#include "Engine/World.h"
#include "RedPlanetPresentationTuning.h"

DEFINE_LOG_CATEGORY_STATIC(LogRedSpaceExposure, Log, All);

URedSpaceExposureCameraModifier::URedSpaceExposureCameraModifier(
	const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	// Camera modifiers run from low numeric priority to high numeric priority.
	// This must be the last post-process blend so an active ship/cockpit camera
	// cannot restore its serialized exposure after the planet hand-off.
	Priority = 255;
	bExclusive = false;
	AlphaInTime = 0.f;
	AlphaOutTime = 0.f;
}

void URedSpaceExposureCameraModifier::SetPlanetFrame(
	const FVector& InCenter, const float InSurfaceRadiusCm,
	const bool bInFusedPrototype)
{
	PlanetCenter = InCenter;
	PlanetSurfaceRadiusCm = FMath::Max(InSurfaceRadiusCm, 1.f);
	bFusedPrototype = bInFusedPrototype;
}

void URedSpaceExposureCameraModifier::SetSurfaceNightExposure(const float InNightFactor)
{
	SurfaceNightExposureAlpha = bFusedPrototype
		? FMath::Clamp(InNightFactor, 0.f, 1.f)
		: 0.f;
}

bool URedSpaceExposureCameraModifier::ModifyCamera(
	const float DeltaTime, FMinimalViewInfo& InOutPOV)
{
	Super::ModifyCamera(DeltaTime, InOutPOV);
	if (IsDisabled())
	{
		return false;
	}
	if (bFusedPrototype)
	{
		const float ViewAltitudeCm =
			static_cast<float>((InOutPOV.Location - PlanetCenter).Size())
			- PlanetSurfaceRadiusCm;
		const float ExposureStartCm =
			RedPlanetPresentationTuning::AtmosphereHeightCm
			* RedPlanetPresentationTuning::OrbitExposureStartFraction;
		const float ExposureEndCm =
			RedPlanetPresentationTuning::AtmosphereHeightCm
			* RedPlanetPresentationTuning::OrbitExposureEndFraction;
		OrbitExposureAlpha = FMath::SmoothStep(
			ExposureStartCm, ExposureEndCm, ViewAltitudeCm);
	}
	else
	{
		OrbitExposureAlpha = 0.f;
	}

	// UCameraModifier's normal post-process path uses VTBlendOrder_Base. Unreal
	// applies the active pawn/vehicle camera after Base blends, which was exactly
	// why the old world component appeared active in logs but had no visual
	// effect. Add this one explicitly as Override so it is composed after the
	// current first/third-person camera settings.
	const float FinalOrbitBlendWeight = OrbitExposureAlpha * Alpha;
	// Do not fight the orbit hand-off.  Surface night needs the added guard only below
	// the space transition, where the old -10 EV histogram floor created white frames.
	const float FinalNightBlendWeight =
		(1.f - OrbitExposureAlpha) * SurfaceNightExposureAlpha * Alpha;
	if (CameraOwner && (FinalOrbitBlendWeight > KINDA_SMALL_NUMBER
		|| FinalNightBlendWeight > KINDA_SMALL_NUMBER))
	{
		// A non-null bias curve on an active cockpit camera is a hard post-process
		// override. Reuse one flat zero curve for both surface-night and orbital
		// guards so neither path inherits an authored brightening curve.
		if (!FlatExposureBiasCurve)
		{
			FlatExposureBiasCurve = NewObject<UCurveFloat>(this, TEXT("FlatOrbitExposureBias"));
			FlatExposureBiasCurve->FloatCurve.AddKey(-20.f, 0.f);
			FlatExposureBiasCurve->FloatCurve.AddKey(30.f, 0.f);
		}

		if (FinalNightBlendWeight > KINDA_SMALL_NUMBER)
		{
			FPostProcessSettings SurfaceNightExposure;
			ConfigureSurfaceNightExposure(SurfaceNightExposure);
			CameraOwner->AddCachedPPBlend(
				SurfaceNightExposure, FinalNightBlendWeight, VTBlendOrder_Override);
		}

		if (FinalOrbitBlendWeight <= KINDA_SMALL_NUMBER)
		{
			return false;
		}

		const UWorld* World = CameraOwner->GetWorld();
		const bool bNightWaterT04OrbitValidation = World
			&& RedPlanetPresentationTuning::IsNightWaterT04MapName(World->GetMapName())
			&& RedPlanetPresentationTuning::UseNightWaterT04SoStylizedRadial();
		FPostProcessSettings OrbitExposure;
		ConfigureOrbitExposure(OrbitExposure, bNightWaterT04OrbitValidation);
		// Numeric EV controls interpolate through ascent. At the fully orbital gate,
		// normalize even a pack cockpit serialized as Manual to Histogram so every
		// first/third-person view uses the same calibrated EV target.
		if (OrbitExposureAlpha >= 0.99f)
		{
			OrbitExposure.bOverride_AutoExposureMethod = true;
			OrbitExposure.AutoExposureMethod = AEM_Histogram;
			AActor* ViewTarget = CameraOwner->GetViewTarget();
			if (LastLoggedOrbitViewTarget.Get() != ViewTarget)
			{
				LastLoggedOrbitViewTarget = ViewTarget;
				const float LoggedMinEv = bNightWaterT04OrbitValidation
					? RedPlanetPresentationTuning::NightWaterT04OrbitExposureMinEv
					: RedPlanetPresentationTuning::OrbitExposureTargetEv;
				const float LoggedMaxEv = bNightWaterT04OrbitValidation
					? RedPlanetPresentationTuning::NightWaterT04OrbitExposureMaxEv
					: RedPlanetPresentationTuning::OrbitExposureTargetEv;
				UE_LOG(LogRedSpaceExposure, Display,
					TEXT("Orbit camera normalized: target=%s sourceMethod=%d sourceCurve=%s targetEV=[%.2f,%.2f] bias=%.2f nightWaterT04=%d"),
					*GetNameSafe(ViewTarget),
					static_cast<int32>(InOutPOV.PostProcessSettings.AutoExposureMethod),
					*GetNameSafe(InOutPOV.PostProcessSettings.AutoExposureBiasCurve),
					LoggedMinEv, LoggedMaxEv,
					RedPlanetPresentationTuning::OrbitExposureBias,
					bNightWaterT04OrbitValidation ? 1 : 0);
			}
		}
		CameraOwner->AddCachedPPBlend(
			OrbitExposure, FinalOrbitBlendWeight, VTBlendOrder_Override);
	}
	else if (OrbitExposureAlpha <= 0.01f)
	{
		LastLoggedOrbitViewTarget.Reset();
	}
	return false;
}

void URedSpaceExposureCameraModifier::ConfigureSurfaceNightExposure(
	FPostProcessSettings& PostProcessSettings) const
{
	PostProcessSettings.bOverride_AutoExposureMethod = true;
	PostProcessSettings.AutoExposureMethod = AEM_Histogram;
	PostProcessSettings.bOverride_AutoExposureMinBrightness = true;
	PostProcessSettings.AutoExposureMinBrightness =
		RedPlanetPresentationTuning::SurfaceNightExposureMinEv;
	PostProcessSettings.bOverride_AutoExposureMaxBrightness = true;
	PostProcessSettings.AutoExposureMaxBrightness =
		RedPlanetPresentationTuning::SurfaceNightExposureMaxEv;
	PostProcessSettings.bOverride_AutoExposureBias = true;
	PostProcessSettings.AutoExposureBias =
		RedPlanetPresentationTuning::SurfaceNightExposureBias;
	PostProcessSettings.bOverride_AutoExposureBiasCurve = FlatExposureBiasCurve != nullptr;
	PostProcessSettings.AutoExposureBiasCurve = FlatExposureBiasCurve;
	PostProcessSettings.bOverride_AutoExposureApplyPhysicalCameraExposure = true;
	PostProcessSettings.AutoExposureApplyPhysicalCameraExposure = false;
	PostProcessSettings.bOverride_AutoExposureSpeedUp = true;
	PostProcessSettings.AutoExposureSpeedUp = 3.f;
	PostProcessSettings.bOverride_AutoExposureSpeedDown = true;
	PostProcessSettings.AutoExposureSpeedDown = 1.5f;
	PostProcessSettings.bOverride_LocalExposureHighlightContrastScale = true;
	PostProcessSettings.LocalExposureHighlightContrastScale = 1.f;
	PostProcessSettings.bOverride_LocalExposureShadowContrastScale = true;
	PostProcessSettings.LocalExposureShadowContrastScale = 1.f;
	PostProcessSettings.bOverride_LocalExposureDetailStrength = true;
	PostProcessSettings.LocalExposureDetailStrength = 0.f;
}

void URedSpaceExposureCameraModifier::ConfigureOrbitExposure(
	FPostProcessSettings& PostProcessSettings,
	const bool bNightWaterT04OrbitValidation) const
{
	// Keep the active camera's histogram method during the fractional hand-off.
	// Unreal treats enum/bool post-process fields as hard switches at any nonzero
	// weight, while these numeric EV limits interpolate correctly and avoid an
	// abrupt exposure pop at the lower atmosphere boundary.
	PostProcessSettings.bOverride_AutoExposureMinBrightness = true;
	PostProcessSettings.AutoExposureMinBrightness =
		bNightWaterT04OrbitValidation
			? RedPlanetPresentationTuning::NightWaterT04OrbitExposureMinEv
			: RedPlanetPresentationTuning::OrbitExposureTargetEv;
	PostProcessSettings.bOverride_AutoExposureMaxBrightness = true;
	PostProcessSettings.AutoExposureMaxBrightness =
		bNightWaterT04OrbitValidation
			? RedPlanetPresentationTuning::NightWaterT04OrbitExposureMaxEv
			: RedPlanetPresentationTuning::OrbitExposureTargetEv;
	PostProcessSettings.bOverride_AutoExposureBias = true;
	// The physical daylight rig is intentionally bright.  Close exposure only as
	// the camera leaves the atmosphere so space stays black and the sunlit planet
	// keeps colour/detail instead of becoming an opaque white disc.
	PostProcessSettings.AutoExposureBias =
		RedPlanetPresentationTuning::OrbitExposureBias;
	PostProcessSettings.bOverride_AutoExposureBiasCurve =
		FlatExposureBiasCurve != nullptr;
	PostProcessSettings.AutoExposureBiasCurve = FlatExposureBiasCurve;
	// Normalize every camera for the complete transition.  Waiting until the
	// final 1% allowed pack cockpits using Manual/physical-camera exposure to
	// jump between unrelated exposure systems at the atmosphere boundary.
	PostProcessSettings.bOverride_AutoExposureMethod = true;
	PostProcessSettings.AutoExposureMethod = AEM_Histogram;
	PostProcessSettings.bOverride_AutoExposureApplyPhysicalCameraExposure = true;
	PostProcessSettings.AutoExposureApplyPhysicalCameraExposure = false;
	PostProcessSettings.bOverride_LocalExposureHighlightContrastScale = true;
	PostProcessSettings.LocalExposureHighlightContrastScale = 1.f;
	PostProcessSettings.bOverride_LocalExposureShadowContrastScale = true;
	PostProcessSettings.LocalExposureShadowContrastScale = 1.f;
	PostProcessSettings.bOverride_LocalExposureDetailStrength = true;
	PostProcessSettings.LocalExposureDetailStrength = 0.f;
}
