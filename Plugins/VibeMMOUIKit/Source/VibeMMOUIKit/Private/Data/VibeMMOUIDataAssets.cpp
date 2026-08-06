#include "Data/VibeMMOUIDataAssets.h"

FVibeMMOHUDAnchorSlot::FVibeMMOHUDAnchorSlot()
	: Anchors(0.0f, 0.0f)
	, Alignment(FVector2D::ZeroVector)
	, Position(FVector2D::ZeroVector)
	, Size(FVector2D(100.0f, 100.0f))
{
}

FVibeMMOHUDAnchorSlot::FVibeMMOHUDAnchorSlot(const FAnchors& InAnchors, const FVector2D& InAlignment, const FVector2D& InPosition, const FVector2D& InSize)
	: Anchors(InAnchors)
	, Alignment(InAlignment)
	, Position(InPosition)
	, Size(InSize)
{
}

UVibeMMOHUDLayoutDataAsset::UVibeMMOHUDLayoutDataAsset()
	: StatusPanelSlot(FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D(42.0f, 38.0f), FVector2D(390.0f, 176.0f))
	, CompassSlot(FAnchors(0.5f, 0.0f), FVector2D(0.5f, 0.0f), FVector2D(0.0f, 28.0f), FVector2D(620.0f, 54.0f))
	, MinimapSlot(FAnchors(1.0f, 0.0f), FVector2D(1.0f, 0.0f), FVector2D(-32.0f, 28.0f), FVector2D(210.0f, 210.0f))
	, ReticleSlot(FAnchors(0.5f, 0.5f), FVector2D(0.5f, 0.5f), FVector2D::ZeroVector, FVector2D(84.0f, 84.0f))
	, AbilityBarSlot(FAnchors(0.5f, 1.0f), FVector2D(0.5f, 1.0f), FVector2D(0.0f, -48.0f), FVector2D(560.0f, 126.0f))
	, WeaponStackSlot(FAnchors(1.0f, 1.0f), FVector2D(1.0f, 1.0f), FVector2D(-42.0f, -58.0f), FVector2D(170.0f, 206.0f))
{
	DefaultAbilityKeyLabels = {
		FText::FromString(TEXT("Q")),
		FText::FromString(TEXT("E")),
		FText::FromString(TEXT("R")),
		FText::FromString(TEXT("F")),
		FText::FromString(TEXT("X"))
	};

	DefaultWeaponSlotLabels = {
		FText::FromString(TEXT("1")),
		FText::FromString(TEXT("2"))
	};
}

UVibeMMOCharacterCreationDataAsset::UVibeMMOCharacterCreationDataAsset()
{
	FactionNames = {
		FText::FromString(TEXT("Auric Vanguard")),
		FText::FromString(TEXT("Neon Concord")),
		FText::FromString(TEXT("Driftborn Union"))
	};

	RaceNames = {
		FText::FromString(TEXT("Human")),
		FText::FromString(TEXT("Astral")),
		FText::FromString(TEXT("Synth")),
		FText::FromString(TEXT("Nomad"))
	};

	BodyTypeLabels = {
		FText::FromString(TEXT("Body Type A")),
		FText::FromString(TEXT("Body Type B")),
		FText::FromString(TEXT("Body Type C"))
	};
}
