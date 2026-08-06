#include "RedShipCollisionDriver.h"

#include "CollisionQueryParams.h"
#include "Components/SceneComponent.h"
#include "Engine/HitResult.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "RedShipMovementComponent.h"
#include "RedPlanetTerrainQuery.h"
#include "UObject/UnrealType.h"

URedShipCollisionDriver::URedShipCollisionDriver()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.TickGroup = TG_PrePhysics;
}

void URedShipCollisionDriver::BeginPlay()
{
	Super::BeginPlay();

	AActor* Owner = GetOwner();
	URedShipMovementComponent* Movement = Owner ? Owner->FindComponentByClass<URedShipMovementComponent>() : nullptr;
	if (!Movement)
	{
		UE_LOG(LogRedShip, Warning, TEXT("%s: no URedShipMovementComponent on owner — collision driver inactive"), *GetNameSafe(Owner));
		SetComponentTickEnabled(false);
		return;
	}

	ShipMovement = Movement;
	Movement->ExternalSpeedCap.BindUObject(this, &URedShipCollisionDriver::QuerySpeedCap);
	// The governor cap computed this frame must be consumed this frame: drive ticks before movement.
	Movement->PrimaryComponentTick.AddPrerequisite(this, PrimaryComponentTick);

	ResolveInvokerClass();
	CreateInvoker();
}

void URedShipCollisionDriver::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (URedShipMovementComponent* Movement = ShipMovement.Get())
	{
		Movement->ExternalSpeedCap.Unbind();
		Movement->PrimaryComponentTick.RemovePrerequisite(this, PrimaryComponentTick);
	}
	ShipMovement.Reset();

	if (InvokerComponent)
	{
		InvokerComponent->DestroyComponent();
		InvokerComponent = nullptr;
	}

	Super::EndPlay(EndPlayReason);
}

void URedShipCollisionDriver::TickComponent(const float DeltaTime, const ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	const AActor* Owner = GetOwner();
	const URedShipMovementComponent* Movement = ShipMovement.Get();
	if (!Owner || !Movement)
	{
		CachedSpeedCap = 0.0f;
		return;
	}

	const FVector ShipLocation = Owner->GetActorLocation();
	// ARedShip::GetVelocity exposes RemoteFlightVelocity on the server-authoritative remote path;
	// reading Movement->Velocity here returned stale/zero direction for multiplayer backstops.
	const FVector ShipVelocity = Owner->GetVelocity();
	const float AltitudeAGL = Movement->GetAltitudeAGL();

	// Hysteresis: enable at the threshold, release only once clear of threshold + band.
	const float DisableAltitude = InvokerEnableAltitudeAGL + InvokerAltitudeHysteresis;
	const bool bShouldEnable = AltitudeAGL <= (bInvokerEnabled ? DisableAltitude : InvokerEnableAltitudeAGL);

	if (bShouldEnable != bInvokerEnabled)
	{
		SetInvokerEnabled(bShouldEnable, AltitudeAGL);
	}

	if (bInvokerEnabled && InvokerComponent)
	{
		UpdateInvokerLocation(ShipLocation, ShipVelocity);
	}

	// Cook-ahead remains altitude-gated, but the exact active-terrain backstop runs at any altitude:
	// high terrain can sit well above the deliberately conservative gameplay datum.
	CachedSpeedCap = ComputeSpeedCap(ShipLocation, ShipVelocity, bShouldEnable);
}

float URedShipCollisionDriver::QuerySpeedCap() const
{
	return CachedSpeedCap;
}

void URedShipCollisionDriver::ResolveInvokerClass()
{
	if (bTriedResolvingClass)
	{
		return;
	}
	bTriedResolvingClass = true;

	InvokerClass = StaticLoadClass(USceneComponent::StaticClass(), nullptr, *InvokerClassPath);
	if (!InvokerClass)
	{
		UE_LOG(LogRedShip, Warning, TEXT("%s: invoker class '%s' not found — flying with governor + raycast backstop only (is the Voxel plugin enabled?)"),
			*GetNameSafe(GetOwner()), *InvokerClassPath);
	}
}

void URedShipCollisionDriver::CreateInvoker()
{
	if (InvokerComponent || !InvokerClass)
	{
		return;
	}

	AActor* Owner = GetOwner();
	USceneComponent* Root = Owner ? Owner->GetRootComponent() : nullptr;
	if (!Root)
	{
		return;
	}

	InvokerComponent = NewObject<USceneComponent>(Owner, InvokerClass, TEXT("VibeShipVoxelInvoker"));
	if (!InvokerComponent)
	{
		return;
	}

	// Attached for lifetime, absolute transform so velocity-leading placement is in world space.
	InvokerComponent->SetupAttachment(Root);
	InvokerComponent->SetUsingAbsoluteLocation(true);
	InvokerComponent->SetUsingAbsoluteRotation(true);
	InvokerComponent->RegisterComponent();
	InvokerComponent->SetWorldLocation(Owner->GetActorLocation());

	SetInvokerFloatProperty(TEXT("Radius"), InvokerRadius);
	SetInvokerBoolProperty(TEXT("bWaitForVoxelWorld"), bInvokerWaitForVoxelWorld);
	SetInvokerBoolProperty(TEXT("bEnabled"), false);
	bInvokerEnabled = false;

	UE_LOG(LogRedShip, Log, TEXT("%s: created voxel collision invoker '%s' (radius %.0f m, disabled until below %.0f m AGL)"),
		*GetNameSafe(Owner), *InvokerClass->GetName(), InvokerRadius / 100.0f, InvokerEnableAltitudeAGL / 100.0f);
}

void URedShipCollisionDriver::SetInvokerEnabled(const bool bNewEnabled, const float AltitudeAGL)
{
	bInvokerEnabled = bNewEnabled && InvokerComponent != nullptr;

	if (InvokerComponent)
	{
		SetInvokerBoolProperty(TEXT("bEnabled"), bInvokerEnabled);
		UE_LOG(LogRedShip, Log, TEXT("%s: collision invoker %s (altitude AGL %.0f m)"),
			*GetNameSafe(GetOwner()), bInvokerEnabled ? TEXT("ENABLED") : TEXT("DISABLED"), AltitudeAGL / 100.0f);
	}
}

void URedShipCollisionDriver::UpdateInvokerLocation(const FVector& ShipLocation, const FVector& ShipVelocity)
{
	const FVector Lead = (ShipVelocity * InvokerLeadTime).GetClampedToMaxSize(MaxLeadDistance);
	InvokerComponent->SetWorldLocation(ShipLocation + Lead);
}

float URedShipCollisionDriver::ComputeSpeedCap(
	const FVector& ShipLocation,
	const FVector& ShipVelocity,
	const bool bIncludeCookAheadCap) const
{
	// 1) Cook-ahead cap: never outrun the cooked collision bubble around the led invoker.
	bool bHasSpeedCap = bIncludeCookAheadCap;
	float SpeedCap = bIncludeCookAheadCap
		? (MaxLeadDistance + InvokerRadius) / FMath::Max(GovernorCookAheadTime, 0.1f)
		: TNumericLimits<float>::Max();

	// 2) Raycast backstop: brake against terrain dead ahead along the travel vector.
	const float Speed = static_cast<float>(ShipVelocity.Size());
	UWorld* World = GetWorld();
	if (World && Speed > UE_KINDA_SMALL_NUMBER && BackstopLookAheadTime > 0.0f)
	{
		const FVector Direction = ShipVelocity / Speed;
		const float TraceLength = Speed * BackstopLookAheadTime + InvokerRadius;

		const FVector TraceEnd = ShipLocation + Direction * TraceLength;
		FHitResult Hit;
		ERedPlanetTerrainQueryResult TerrainResult = ERedPlanetTerrainQueryResult::NoMatchingPlanet;
		if (const URedShipMovementComponent* Movement = ShipMovement.Get())
		{
			TerrainResult = RedPlanetTerrainQuery::LineTrace(
				World, Movement->PlanetCenter, ShipLocation, TraceEnd, Hit);
		}

		bool bBackstopHit = TerrainResult == ERedPlanetTerrainQueryResult::Hit;
		if (TerrainResult == ERedPlanetTerrainQueryResult::NoMatchingPlanet)
		{
			const FCollisionQueryParams Params(
				TEXT("VibeShipBackstop"), /*bInTraceComplex*/ false, GetOwner());
			bBackstopHit = World->LineTraceSingleByChannel(
				Hit, ShipLocation, TraceEnd, BackstopTraceChannel, Params);
		}
		if (bBackstopHit && Hit.bBlockingHit)
		{
			const float BrakeCap = (Hit.Distance * BackstopBrakeFraction) / FMath::Max(BackstopLookAheadTime, 0.1f);
			SpeedCap = FMath::Min(SpeedCap, BrakeCap);
			bHasSpeedCap = true;
		}
	}

	return bHasSpeedCap ? FMath::Max(SpeedCap, GovernorMinSpeed) : 0.0f;
}

bool URedShipCollisionDriver::SetInvokerBoolProperty(const FName PropertyName, const bool bValue) const
{
	if (!InvokerComponent)
	{
		return false;
	}

	const FBoolProperty* Property = FindFProperty<FBoolProperty>(InvokerComponent->GetClass(), PropertyName);
	if (!Property)
	{
		UE_LOG(LogRedShip, Warning, TEXT("%s: bool property '%s' not found on %s"),
			*GetNameSafe(GetOwner()), *PropertyName.ToString(), *InvokerComponent->GetClass()->GetName());
		return false;
	}

	Property->SetPropertyValue_InContainer(InvokerComponent, bValue);
	return true;
}

bool URedShipCollisionDriver::SetInvokerFloatProperty(const FName PropertyName, const float Value) const
{
	if (!InvokerComponent)
	{
		return false;
	}

	const FFloatProperty* Property = FindFProperty<FFloatProperty>(InvokerComponent->GetClass(), PropertyName);
	if (!Property)
	{
		UE_LOG(LogRedShip, Warning, TEXT("%s: float property '%s' not found on %s"),
			*GetNameSafe(GetOwner()), *PropertyName.ToString(), *InvokerComponent->GetClass()->GetName());
		return false;
	}

	Property->SetPropertyValue_InContainer(InvokerComponent, Value);
	return true;
}
