#pragma once

#include "CoreMinimal.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"

/**
 * Shared presentation constants for the small playable planet.
 *
 * Keeping these in one place prevents the server, local client, vehicles and
 * procedural space scenery from disagreeing about where atmosphere ends.
 */
namespace RedPlanetPresentationTuning
{
	// A disposable, map-name-gated water presentation harness. Keeping the token,
	// material path, and conservative values here prevents the authority and local
	// client paths from drifting apart while leaving every production map unchanged.
	inline constexpr const TCHAR* NightWaterT04MapToken = TEXT("NightWater_T04");
	inline constexpr const TCHAR* NightWaterT04MaterialPath =
		TEXT("/Game/RedMMO/Environment/Tests/MI_RedClearWater_Night_T04.MI_RedClearWater_Night_T04");
	// T04 is a disposable visual A/B, not a production material swap. The legacy
	// So Stylized water root is masked and authored for a flat demo scene, so it
	// cannot be judged fairly as the 50 km radial ocean. Use the installed
	// WorldGen global-water instance only for the planet-wide test surface; local
	// RedOasisWater actors continue to use the project-owned So Stylized child.
	inline constexpr const TCHAR* NightWaterT04GlobalOceanMaterialPath =
		TEXT("/WorldGen/Materials/Water/MI_Water.MI_Water");
	// Project-owned radial diagnostic material. It reuses the purchased So Stylized
	// water normal texture, but deliberately omits the vendor demo master's planar
	// distance-field, scene-depth, and time-of-day branches that became a flashing
	// white shell on PlanetGen's spherical ocean.
	inline constexpr const TCHAR* NightWaterT04RadialMaterialPath =
		TEXT("/Game/RedMMO/Environment/Tests/MI_RedRadialWater_Night_T04_V4.MI_RedRadialWater_Night_T04_V4");
	// Opt-in development A/B. The default T04 body remains the known-coherent
	// WorldGen diagnostic ocean; this flag switches only the disposable harness to
	// the project-owned So Stylized child so it can be judged without another build.
	inline constexpr const TCHAR* NightWaterT04SoStylizedRadialFlag =
		TEXT("NightWaterSoStylizedRadial");

	inline bool UseNightWaterT04SoStylizedRadial()
	{
#if !UE_BUILD_SHIPPING
		return FParse::Param(FCommandLine::Get(), NightWaterT04SoStylizedRadialFlag);
#else
		return false;
#endif
	}

	inline const TCHAR* ResolveNightWaterT04GlobalOceanMaterialPath()
	{
		return UseNightWaterT04SoStylizedRadial()
			? NightWaterT04RadialMaterialPath
			: NightWaterT04GlobalOceanMaterialPath;
	}
	inline constexpr float NightWaterT04Scattering = 0.08f;
	inline constexpr float NightWaterT04Normal1Flatness = 0.64f;
	inline constexpr float NightWaterT04Normal2Flatness = 0.70f;
	inline constexpr float NightWaterT04DistantNormalFlatness = 0.82f;
	// Edge Waves is the flat-demo distance-field branch that produced blinking
	// white fragments on the radial ocean. Normal1/Normal2 panners remain active
	// and supply the desired fine animated surface motion.
	inline constexpr float NightWaterT04Waves = 0.0f;
	// The V1 radial proof repeated one normal 8,192 times around the 50 km
	// circumference. At normal gameplay distances that filtered into a nearly flat
	// surface, while distant grazing angles could alias into short white sparkles.
	// V3 uses the purchased So Stylized demo water normal twice at broader,
	// mismatched scales, fades its strength before orbit, and restores the pack's
	// Single Layer Water absorption/scattering model without its flat-demo edge
	// branches. These are parameters on the project-owned T04 material only;
	// vendor materials are never modified.
	inline constexpr float NightWaterT04RadialWaveTiling1 = 4096.0f;
	inline constexpr float NightWaterT04RadialWaveTiling2 = 6144.0f;
	inline constexpr float NightWaterT04RadialNormalStrength = 0.55f;
	inline constexpr float NightWaterT04RadialNormalFadeStartCm = 50000.0f;
	inline constexpr float NightWaterT04RadialNormalFadeEndCm = 250000.0f;
	inline constexpr float NightWaterT04RadialRoughness = 0.30f;
	inline constexpr float NightWaterT04RadialSpecular = 0.38f;
	inline constexpr float NightWaterT04RadialOpacity = 0.93f;
	inline constexpr FLinearColor NightWaterT04RadialTint =
		FLinearColor(0.015f, 0.16f, 0.52f, 1.0f);

	// The deterministic F7 shoreline sample used by the disposable night-water
	// validation map.  Keep its radial direction shared with the light lock: one
	// directional sun cannot make every point on a sphere night simultaneously,
	// so the test must deliberately make its captured coast the dark hemisphere.
	inline FVector NightWaterT04ShoreDirection()
	{
		return FVector(0.827164075f, 0.295964038f, -0.477707945f);
	}

	inline bool IsNightWaterT04MapName(const FString& MapName)
	{
		return MapName.Contains(NightWaterT04MapToken);
	}

	// Eight kilometres gives the 50 km-circumference world enough vertical room
	// for a readable cloud deck and a gradual flight transition. Four kilometres
	// was crossed in only a few seconds and made the ocean/atmosphere layers read
	// like stacked shells when looking back from a vehicle.
	inline constexpr float AtmosphereHeightKm = 8.0f;
	inline constexpr float AtmosphereHeightCm = AtmosphereHeightKm * 100000.0f;
	// The rendered molecular limb is intentionally much thinner than the playable
	// ascent.  An 8 km SkyAtmosphere on this roughly 8 km-radius body doubled its
	// apparent diameter in orbit.  Flight, exposure, stars and vehicle state still
	// use AtmosphereHeightKm; only the optical shell and HI-5 bounds use this value.
	inline constexpr float VisualAtmosphereHeightKm = 1.8f;
	inline constexpr float VisualAtmosphereHeightCm = VisualAtmosphereHeightKm * 100000.0f;
	static_assert(VisualAtmosphereHeightKm > 0.0f,
		"The visual atmosphere shell must have positive height.");
	static_assert(VisualAtmosphereHeightKm < AtmosphereHeightKm,
		"The visual atmosphere must remain independent from the longer gameplay ascent.");
	// Begin the vacuum crossfade mid-ascent so a normal climb clearly exits atmosphere.
	inline constexpr float OrbitExposureStartFraction = 0.55f;
	inline constexpr float OrbitExposureEndFraction = 1.00f;
	// The V3 real-GPU frame proved EV 14.5 still closed the camera far enough to
	// erase the atmosphere limb and all but the brightest stars. Eleven keeps the
	// sunlit planet readable while the unlit vacuum remains genuinely black.
	inline constexpr float OrbitExposureTargetEv = 13.5f;
	// Target EV is the single orbit exposure control. A second negative bias was
	// appropriate only for the retired Manual path and would double-darken the
	// Histogram result.
	inline constexpr float OrbitExposureBias = 0.0f;
	// The legacy fused-map PPV allowed histogram exposure to roam from -10 to 20 EV.
	// Once the opaque daylight sky is hidden at night, the histogram can select its -10
	// floor and turn moonlit terrain into a completely white frame.  Keep the surface-night
	// range deliberately narrow enough to retain a readable cool night while preventing that
	// runaway adaptation.  This is applied only after the daytime fallback sky is gone.
	inline constexpr float SurfaceNightExposureMinEv = -3.0f;
	inline constexpr float SurfaceNightExposureMaxEv = 2.0f;
	inline constexpr float SurfaceNightExposureBias = 0.0f;
	// The disposable radial-water orbit check remains over its intentionally dark
	// coast.  Reuse the readable night histogram range instead of applying the
	// production daylight-orbit EV to moonlight that is roughly sixteen stops dimmer.
	inline constexpr float NightWaterT04OrbitExposureMinEv = -3.0f;
	inline constexpr float NightWaterT04OrbitExposureMaxEv = 2.0f;
	inline constexpr float NightWaterT04OrbitStarEmissionCompensation = 1.0f;
	// The F9 water-comparison camera exposes the intentionally moonlit coast. The
	// normal 75 klux atmosphere sun otherwise blows the disposable frame into a
	// white annulus. Suppress scattering only while that exact inspection is active;
	// ordinary T04 ascent and every production map retain the normal orbit density.
	inline constexpr float NightWaterT04OrbitAtmosphereDensityFraction = 0.0f;
	// V3 thinned the physical atmosphere to 18% at orbit, which made the limb
	// disappear despite the component remaining present. Keep a translucent but
	// readable fraction instead of fading the actual atmosphere almost to zero.
	// Near-zero vacuum density so AltFade≈1 reads as true space exit, not a permanent haze shell.
	inline constexpr float OrbitAtmosphereDensityFraction = 0.04f;
	// The main orbit camera runs near daylight EV while the minimap does not. V4C
	// proved that geometry visible in the minimap was still below the main-view
	// threshold, so compensate the tiny emissive discs after the vacuum hand-off.
	inline constexpr float OrbitStarEmissionCompensation = 3.0f;

	// Surface-only painted sky. Keep the source deliberately more saturated than
	// the desired on-screen baby blue because filmic tone mapping and histogram
	// exposure pull very bright sky emission toward neutral grey.
	inline constexpr FLinearColor SurfaceBabyBlueColor =
		FLinearColor(0.35f, 0.72f, 1.0f, 1.0f);
	inline constexpr float SurfaceBabyBlueEmission = 18000.0f;

	// SkyAtmosphere stores the colour normalized and the coefficient magnitude in
	// the Scale property. 1.1 was therefore roughly 33x the physical blue-channel
	// coefficient and collapsed the visible limb into a bright, opaque band.
	// This small-world shell has much less vertical optical depth than Earth's
	// sixty-kilometre atmosphere. The engine defaults therefore rendered this
	// small world as saturated navy even at noon. These coefficients retain a
	// transparent orbital limb while restoring a clear, bright baby-blue sky.
	inline constexpr float RayleighScatteringScale = 0.340f;
	inline constexpr float MieScatteringScale = 0.006f;
	// Reassert these values at runtime so a serialized SunSky component cannot
	// silently inherit a dense/strongly forward-scattering atmosphere from an
	// older map revision. The gameplay shell does not contain Earth's ozone
	// layer, so its auxiliary absorption is intentionally disabled.
	inline constexpr float MieAbsorptionScale = 0.000444f;
	inline constexpr float OtherAbsorptionScale = 0.0f;
	inline constexpr float MieAnisotropy = 0.72f;
	inline constexpr FLinearColor RayleighScatteringColor =
		FLinearColor(0.175f, 0.410f, 1.0f, 1.0f);
	inline constexpr float MultiScatteringFactor = 1.00f;

	// These distributions belong to the thin visual limb, not the eight-kilometre
	// gameplay ascent. Keeping them below the rendered shell height prevents the
	// gray atmosphere from becoming nearly as thick as the small planet itself.
	inline constexpr float RayleighHeightKm = 0.85f;
	inline constexpr float MieHeightKm = 0.30f;
	inline constexpr float AerialPerspectiveScale = 0.82f;
	// SunSky's physical daylight baseline. The fused prototype had serialized an
	// intensity of 5 lux, roughly fourteen stops below this value, which left the
	// atmosphere navy even when its art-direction multiplier was raised.
	inline constexpr float DaylightSunIlluminanceLux = 75000.0f;

	// The physical atmosphere is deliberately tiny, so art-direct its sky-only
	// luminance toward the clear, pale Fortnite-like blue requested for daytime.
	// Terrain exposure stays independent while the orbital limb remains driven
	// by the atmosphere rather than a painted sphere.
	// SkyAtmosphere's Rayleigh result is naturally blue-biased. A uniform gain
	// made that result brighter but the red-heavy luminance multiplier washed the
	// surface sky to grey-green. Preserve the brighter scattering while biasing the
	// final sky/aerial luminance toward the requested clear Fortnite-like baby blue.
	inline constexpr FLinearColor SkyLuminanceFactor =
		FLinearColor(2.00f, 2.80f, 3.70f, 1.0f);
	// Fade the art-directed surface lift back toward a physical value during
	// ascent so the distant limb remains soft and translucent from space.
	inline constexpr FLinearColor OrbitSkyLuminanceFactor =
		FLinearColor(1.0f, 1.0f, 1.0f, 1.0f);
	inline constexpr FLinearColor SkyAndAerialLuminanceFactor =
		FLinearColor(1.80f, 2.40f, 3.10f, 1.0f);
	inline constexpr FLinearColor OrbitSkyAndAerialLuminanceFactor =
		FLinearColor(1.0f, 1.0f, 1.0f, 1.0f);

	// Leave a small buffer beyond the molecular shell before switching vehicles
	// and the star field to their vacuum presentation.
	inline constexpr float SpaceTransitionAltitudeCm =
		AtmosphereHeightCm * OrbitExposureEndFraction;
	static_assert(SpaceTransitionAltitudeCm > VisualAtmosphereHeightCm,
		"The gameplay space transition must remain above the rendered atmosphere shell.");
	inline constexpr float AsteroidVisibleAltitudeCm = SpaceTransitionAltitudeCm;
	// Mining fields belong in deep space, not inside or immediately above the
	// atmospheric shell. Keep the field farther away than its own draw distance so
	// no rock can render through the atmosphere; the final clearance is intentional
	// travel space for the later warp-drive handoff.
	inline constexpr float AsteroidRenderCullDistanceCm = 2000000.0f;
	inline constexpr float AsteroidAtmosphereClearanceCm = 1000000.0f;
	inline constexpr float AsteroidPresentationTopCm =
		VisualAtmosphereHeightCm > SpaceTransitionAltitudeCm
			? VisualAtmosphereHeightCm : SpaceTransitionAltitudeCm;
	inline constexpr float DeepSpaceAsteroidInnerAltitudeCm =
		AsteroidPresentationTopCm + AsteroidRenderCullDistanceCm
			+ AsteroidAtmosphereClearanceCm;
	inline constexpr float DeepSpaceAsteroidOuterAltitudeCm =
		DeepSpaceAsteroidInnerAltitudeCm + 3000000.0f;
	static_assert(DeepSpaceAsteroidInnerAltitudeCm
		>= AsteroidPresentationTopCm + AsteroidRenderCullDistanceCm
			+ AsteroidAtmosphereClearanceCm,
		"Deep-space asteroids must remain beyond the atmosphere, their full draw distance, and the travel clearance.");
	static_assert(DeepSpaceAsteroidOuterAltitudeCm > DeepSpaceAsteroidInnerAltitudeCm,
		"The deep-space asteroid band must have positive radial depth.");
}
