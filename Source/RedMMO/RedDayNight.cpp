#include "RedDayNight.h"
#include "RedPlanetPresentationTuning.h"

#include "Components/DirectionalLightComponent.h"
#include "Components/SceneComponent.h"
#include "EngineUtils.h"
#include "GameFramework/GameStateBase.h"
#include "Net/UnrealNetwork.h"

DEFINE_LOG_CATEGORY_STATIC(LogRedDayNight, Log, All);

namespace
{
void MakeSunAttachmentChainMovable(USceneComponent* Component)
{
	// SunSky's directional light is commonly attached below a Static root named "Scene".
	// Moving only the light then emits a warning every day/night step and leaves the sun frozen.
	// Promote parents first so the final light rotation is a valid runtime transform update.
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
}

ARedDayNight::ARedDayNight()
{
	PrimaryActorTick.bCanEverTick = true;
	bReplicates = true;
	bAlwaysRelevant = true;
	// Step the sun instead of sliding it every frame: a continuously-moving directional light
	// invalidates shadow + Lumen caches EVERY frame (the whole voxel planet re-renders into the
	// shadow maps = "slow motion" hitching). At a 30-min day, 2s steps are ~0.4 deg — invisible.
	PrimaryActorTick.TickInterval = 2.0f;

	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));

	// Night fill: dim, cool, shadowless "moonlight" locked opposite the sun. Enough to read the
	// terrain and light the volumetric clouds at night without ever looking like daytime.
	MoonLight = CreateDefaultSubobject<UDirectionalLightComponent>(TEXT("MoonLight"));
	MoonLight->SetupAttachment(RootComponent);
	// Fixed exposure and disabled Lumen leave the captured sky nearly black on the far
	// hemisphere. Keep this below the 3.0-lux gameplay sun, but high enough that terrain,
	// ships and non-emissive SoStylized water remain readable from orbit at night.
	MoonLight->SetIntensity(0.85f);
	MoonLight->SetLightColor(FLinearColor(0.48f, 0.60f, 0.92f));
	MoonLight->SetIndirectLightingIntensity(0.55f);
	MoonLight->SetVolumetricScatteringIntensity(0.18f);
	MoonLight->SetCastShadows(false);
	MoonLight->SetAtmosphereSunLight(false);
	MoonLight->SetForwardShadingPriority(0);
}

void ARedDayNight::BeginPlay()
{
	Super::BeginPlay();
	FindSun();
	if (Sun)
	{
		SunStartRotation = Sun->GetComponentRotation();
	}
	UE_LOG(LogRedDayNight, Display,
		TEXT("RedDayNight: cycleLength=%.1fs moon fill intensity=%.2f indirect=%.2f volumetric=%.2f shadows=%d"),
		DayLengthSeconds,
		MoonLight ? MoonLight->Intensity : 0.f,
		MoonLight ? MoonLight->IndirectLightingIntensity : 0.f,
		MoonLight ? MoonLight->VolumetricScatteringIntensity : 0.f,
		MoonLight && MoonLight->CastShadows ? 1 : 0);
	if (HasAuthority())
	{
		CycleStartServerTime = GetWorld() && GetWorld()->GetGameState()
			? GetWorld()->GetGameState()->GetServerWorldTimeSeconds()
			: 0.f;
		ForceNetUpdate();
	}
	// Night_T03 and NightWater_T04 are disposable visual-validation maps.  The normal F10 accelerated
	// cycle made real-GPU captures race between day and night, which meant a valid
	// star-state log could be paired with a daylight screenshot seconds later. Lock
	// this map to midnight so every capture evaluates the same physical atmosphere,
	// moon fill, terrain, water, and star field. Production maps retain their normal
	// replicated two-hour cycle and remain byte-for-byte unchanged by this branch.
	bLockedNightVisualTest = GetWorld()
		&& (GetWorld()->GetMapName().Contains(TEXT("Night_T03"))
			|| GetWorld()->GetMapName().Contains(TEXT("NightWater_T04")));
	if (bLockedNightVisualTest && Sun)
	{
		// A deferred SunSky/atmosphere retry can restore its serialized light transform
		// several seconds after BeginPlay. Run this test-only owner in PostUpdateWork at
		// full cadence so it reasserts midnight after those retries instead of allowing a
		// stable capture to silently flip back to daytime.
		PrimaryActorTick.TickInterval = 0.f;
		PrimaryActorTick.TickGroup = TG_PostUpdateWork;
		SetActorTickEnabled(true);
		ApplyLockedNight();
		// The installed SunSky blueprint owns an Event Tick that re-applies its
		// serialized SolarTime to this same DirectionalLight roughly ten seconds after
		// BeginPlay. It would otherwise undo the locked test rotation after our first
		// valid frame. Disable only that owner on the disposable night-visual test maps; the
		// GameMode still configures its atmosphere and every production map keeps SunSky
		// ticking normally.
		if (AActor* SunOwner = Sun->GetOwner())
		{
			SunOwner->SetActorTickEnabled(false);
			UE_LOG(LogRedDayNight, Display,
				TEXT("RedDayNight: night visual test disabled SunSky runtime clock on %s"),
				*GetNameSafe(SunOwner));
		}
		UE_LOG(LogRedDayNight, Display,
			TEXT("RedDayNight: night visual test locked to midnight with a +43 degree moon-source pitch offset; PostUpdateWork reassertion enabled for stable GPU validation"));
	}
}

void ARedDayNight::GetLifetimeReplicatedProps(
	TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(ARedDayNight, DayLengthSeconds);
	DOREPLIFETIME(ARedDayNight, CycleStartServerTime);
}

void ARedDayNight::FindSun()
{
	// Bind the light that actually drives SkyAtmosphere. The production SunSky component is named
	// simply "DirectionalLight", so component-name matching can silently select an unrelated fill.
	// Only use intensity as a last resort for maps that have not marked an atmosphere sun.
	UDirectionalLightComponent* AtmosphereSun = nullptr;
	float AtmosphereSunIntensity = -1.f;
	UDirectionalLightComponent* Best = nullptr;
	float BestIntensity = -1.f;
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		TArray<UDirectionalLightComponent*> Lights;
		It->GetComponents<UDirectionalLightComponent>(Lights);
		for (UDirectionalLightComponent* L : Lights)
		{
			const AActor* LightOwner = IsValid(L) ? L->GetOwner() : nullptr;
			const bool bIsNightFill = L == MoonLight
				|| (IsValid(L) && L->GetName().Contains(TEXT("MoonLight")))
				|| (IsValid(LightOwner) && LightOwner->ActorHasTag(TEXT("RedNightFill")));
			if (!IsValid(L) || bIsNightFill)
			{
				continue;
			}
			if (L->IsUsedAsAtmosphereSunLight() && L->GetAtmosphereSunLightIndex() == 0u)
			{
				// Match the renderer when a broken map contains duplicate index-0 suns.
				if (L->Intensity > AtmosphereSunIntensity)
				{
					AtmosphereSunIntensity = L->Intensity;
					AtmosphereSun = L;
				}
				continue;
			}
			if (L->Intensity > BestIntensity)
			{
				BestIntensity = L->Intensity;
				Best = L;
			}
		}
	}
	if (AtmosphereSun)
	{
		Sun = AtmosphereSun;
		MakeSunAttachmentChainMovable(Sun);
		UE_LOG(LogRedDayNight, Display,
			TEXT("RedDayNight: bound atmosphere sun %s (index=0 intensity=%.2f)"),
			*GetNameSafe(Sun), Sun->Intensity);
		return;
	}
	Sun = Best;
	MakeSunAttachmentChainMovable(Sun);
	if (Sun)
	{
		UE_LOG(LogRedDayNight, Display,
			TEXT("RedDayNight: atmosphere sun index 0 unavailable; brightest fallback=%s intensity=%.2f"),
			*GetNameSafe(Sun), Sun->Intensity);
	}
}

void ARedDayNight::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (!Sun)
	{
		FindSun();
		if (!Sun)
		{
			return;
		}
		SunStartRotation = Sun->GetComponentRotation();
	}
	if (bLockedNightVisualTest)
	{
		ApplyLockedNight();
		return;
	}

	float PhaseSeconds = 0.f;
	if (CycleStartServerTime >= 0.f && GetWorld() && GetWorld()->GetGameState())
	{
		PhaseSeconds = FMath::Max(0.f,
			GetWorld()->GetGameState()->GetServerWorldTimeSeconds() - CycleStartServerTime);
	}
	else
	{
		CycleTime += DeltaSeconds;
		PhaseSeconds = CycleTime;
	}
	const float Degrees = 360.f * (PhaseSeconds / FMath::Max(30.f, DayLengthSeconds));

	// Sweep the sun's pitch through a full revolution (overhead -> sunset -> under the planet -> dawn).
	const FRotator SunRot(FRotator::NormalizeAxis(SunStartRotation.Pitch - Degrees), SunStartRotation.Yaw, 0.f);
	Sun->SetWorldRotation(SunRot);

	// Moonlight rides exactly opposite: as the sun sets, the cool fill rises.
	const FRotator MoonRot(FRotator::NormalizeAxis(SunRot.Pitch + 180.f), SunRot.Yaw, 0.f);
	MoonLight->SetWorldRotation(MoonRot);
}

void ARedDayNight::ApplyLockedNight()
{
	if (!Sun)
	{
		return;
	}
	if (!bLockedNightRotationResolved)
	{
		const bool bNightWaterShoreTest = GetWorld()
			&& RedPlanetPresentationTuning::IsNightWaterT04MapName(GetWorld()->GetMapName());
		if (bNightWaterShoreTest)
		{
			// The F7 validation coast lies on a different hemisphere from the
			// normal test spawn.  Point the light's forward ray at that coast,
			// putting the solar source below its local horizon.  This is map-gated
			// test harness behavior; production and the general Night_T03 harness
			// retain the spawn-relative midnight rotation below.
			LockedNightSunRotation =
				RedPlanetPresentationTuning::NightWaterT04ShoreDirection().Rotation();
		}
		else
		{
			LockedNightSunRotation = FRotator(
				FRotator::NormalizeAxis(SunStartRotation.Pitch - 180.f),
				SunStartRotation.Yaw, 0.f);
		}
		bLockedNightRotationResolved = true;
	}
	Sun->SetWorldRotation(LockedNightSunRotation);
	if (MoonLight)
	{
		// The default opposite light puts the physical moon roughly 74 degrees above
		// the spawn camera at locked midnight.  This disposable map-only cadence has
		// no player look automation, so bring it to a readable 30-ish degree sky
		// elevation for a genuine GPU surface capture.  The sun remains below the
		// horizon and production continues to use the exactly-opposite rotation above.
		constexpr float NightT03MoonSourcePitchOffsetDeg = 43.f;
		MoonLight->SetWorldRotation(FRotator(
			FRotator::NormalizeAxis(LockedNightSunRotation.Pitch + 180.f
				+ NightT03MoonSourcePitchOffsetDeg),
			LockedNightSunRotation.Yaw, 0.f));
	}
}
