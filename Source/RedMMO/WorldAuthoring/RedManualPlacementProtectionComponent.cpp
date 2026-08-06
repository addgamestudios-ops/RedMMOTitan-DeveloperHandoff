#include "RedManualPlacementProtectionComponent.h"

#include "GameFramework/Actor.h"

URedManualPlacementProtectionComponent::URedManualPlacementProtectionComponent()
{
	PrimaryComponentTick.bCanEverTick = false;
	BlockedFeatureTags = {
		TEXT("Foliage"), TEXT("Rock"), TEXT("Creature"), TEXT("Resource"), TEXT("Water"), TEXT("POI")
	};
}

void URedManualPlacementProtectionComponent::OnRegister()
{
	Super::OnRegister();
	if (AActor* Owner = GetOwner())
	{
		Owner->Tags.AddUnique(TEXT("RedManualPOI"));
		Owner->Tags.AddUnique(TEXT("PCGProtected"));
	}
}

float URedManualPlacementProtectionComponent::GetSurfaceArcDistanceCm(
	const FVector& WorldPoint) const
{
	const AActor* Owner = GetOwner();
	if (!Owner)
	{
		return TNumericLimits<float>::Max();
	}

	const FVector OwnerOffset = Owner->GetActorLocation() - PlanetCenter;
	const FVector PointOffset = WorldPoint - PlanetCenter;
	const float RadiusCm = OwnerOffset.Size();
	if (RadiusCm <= UE_KINDA_SMALL_NUMBER || PointOffset.IsNearlyZero())
	{
		return TNumericLimits<float>::Max();
	}

	const float Dot = FMath::Clamp(
		FVector::DotProduct(OwnerOffset / RadiusCm, PointOffset.GetSafeNormal()), -1.f, 1.f);
	return FMath::Acos(Dot) * RadiusCm;
}

bool URedManualPlacementProtectionComponent::ContainsWorldPoint(
	const FVector& WorldPoint) const
{
	return GetSurfaceArcDistanceCm(WorldPoint) <= FMath::Max(0.f, ProtectedRadiusCm);
}

float URedManualPlacementProtectionComponent::GetProtectionWeight(
	const FVector& WorldPoint) const
{
	const float DistanceCm = GetSurfaceArcDistanceCm(WorldPoint);
	const float HardRadius = FMath::Max(0.f, ProtectedRadiusCm);
	if (DistanceCm <= HardRadius)
	{
		return 1.f;
	}

	const float Blend = FMath::Max(0.f, BlendRadiusCm);
	if (Blend <= UE_KINDA_SMALL_NUMBER || DistanceCm >= HardRadius + Blend)
	{
		return 0.f;
	}

	return 1.f - ((DistanceCm - HardRadius) / Blend);
}

bool URedManualPlacementProtectionComponent::BlocksFeatureAtWorldPoint(
	const FName FeatureTag, const FVector& WorldPoint) const
{
	return GetFeatureProtectionWeight(FeatureTag, WorldPoint) > 0.f;
}

float URedManualPlacementProtectionComponent::GetFeatureProtectionWeight(
	const FName FeatureTag, const FVector& WorldPoint) const
{
	// A procedural caller must identify its feature class. Treating NAME_None as denied prevents
	// a newly added adapter from silently placing content through handcrafted work.
	if (!FeatureTag.IsNone() && !BlockedFeatureTags.Contains(FeatureTag))
	{
		return 0.f;
	}

	return GetProtectionWeight(WorldPoint);
}
