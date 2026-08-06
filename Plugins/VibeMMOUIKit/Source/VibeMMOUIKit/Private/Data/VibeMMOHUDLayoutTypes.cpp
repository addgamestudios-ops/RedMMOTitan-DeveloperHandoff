#include "Data/VibeMMOHUDLayoutTypes.h"

namespace
{
	double SanitizeFinite(const double Value, const double DefaultValue)
	{
		return FMath::IsFinite(Value) ? Value : DefaultValue;
	}

	float SanitizeFinite(const float Value, const float DefaultValue)
	{
		return FMath::IsFinite(Value) ? Value : DefaultValue;
	}
}

bool VibeMMOHUDLayout::IsValidElement(const EVibeMMOHUDElement Element)
{
	return Element >= EVibeMMOHUDElement::StatusPanel && Element < EVibeMMOHUDElement::Count;
}

const TArray<EVibeMMOHUDElement>& VibeMMOHUDLayout::GetElements()
{
	static const TArray<EVibeMMOHUDElement> Elements = {
		EVibeMMOHUDElement::StatusPanel,
		EVibeMMOHUDElement::Compass,
		EVibeMMOHUDElement::Minimap,
		EVibeMMOHUDElement::Reticle,
		EVibeMMOHUDElement::AbilityBar,
		EVibeMMOHUDElement::WeaponStack,
		EVibeMMOHUDElement::PartyPanel,
		EVibeMMOHUDElement::EnemyPanel,
		EVibeMMOHUDElement::UtilityBar
	};
	return Elements;
}

void FVibeMMOHUDElementLayout::Sanitize()
{
	NormalizedOffset.X = FMath::Clamp(
		SanitizeFinite(NormalizedOffset.X, 0.0),
		-static_cast<double>(VibeMMOHUDLayout::MaximumNormalizedOffset),
		static_cast<double>(VibeMMOHUDLayout::MaximumNormalizedOffset));
	NormalizedOffset.Y = FMath::Clamp(
		SanitizeFinite(NormalizedOffset.Y, 0.0),
		-static_cast<double>(VibeMMOHUDLayout::MaximumNormalizedOffset),
		static_cast<double>(VibeMMOHUDLayout::MaximumNormalizedOffset));
	Scale = FMath::Clamp(
		SanitizeFinite(Scale, 1.0f),
		VibeMMOHUDLayout::MinimumScale,
		VibeMMOHUDLayout::MaximumScale);
	Opacity = FMath::Clamp(
		SanitizeFinite(Opacity, 1.0f),
		VibeMMOHUDLayout::MinimumOpacity,
		VibeMMOHUDLayout::MaximumOpacity);
}

bool FVibeMMOHUDElementLayout::IsDefault() const
{
	return NormalizedOffset.IsNearlyZero()
		&& FMath::IsNearlyEqual(Scale, 1.0f)
		&& FMath::IsNearlyEqual(Opacity, 1.0f)
		&& !bLocked
		&& !bHidden;
}

bool FVibeMMOHUDElementLayout::NearlyEquals(const FVibeMMOHUDElementLayout& Other) const
{
	return NormalizedOffset.Equals(Other.NormalizedOffset)
		&& FMath::IsNearlyEqual(Scale, Other.Scale)
		&& FMath::IsNearlyEqual(Opacity, Other.Opacity)
		&& bLocked == Other.bLocked
		&& bHidden == Other.bHidden;
}

FVibeMMOHUDElementLayout FVibeMMOHUDLayoutProfile::GetElementLayout(const EVibeMMOHUDElement Element) const
{
	if (const FVibeMMOHUDElementLayout* Layout = ElementOverrides.Find(Element))
	{
		return *Layout;
	}
	return FVibeMMOHUDElementLayout();
}

bool FVibeMMOHUDLayoutProfile::HasElementOverride(const EVibeMMOHUDElement Element) const
{
	return VibeMMOHUDLayout::IsValidElement(Element) && ElementOverrides.Contains(Element);
}

void FVibeMMOHUDLayoutProfile::SetElementLayout(
	const EVibeMMOHUDElement Element,
	const FVibeMMOHUDElementLayout& Layout)
{
	if (!VibeMMOHUDLayout::IsValidElement(Element))
	{
		return;
	}

	FVibeMMOHUDElementLayout Sanitized = Layout;
	Sanitized.Sanitize();
	if (Sanitized.IsDefault())
	{
		ElementOverrides.Remove(Element);
	}
	else
	{
		ElementOverrides.Add(Element, Sanitized);
	}
}

void FVibeMMOHUDLayoutProfile::ResetElement(const EVibeMMOHUDElement Element)
{
	ElementOverrides.Remove(Element);
}

void FVibeMMOHUDLayoutProfile::ResetToDefault()
{
	ElementOverrides.Reset();
}

void FVibeMMOHUDLayoutProfile::Sanitize()
{
	TArray<EVibeMMOHUDElement> ElementsToRemove;
	for (TPair<EVibeMMOHUDElement, FVibeMMOHUDElementLayout>& Pair : ElementOverrides)
	{
		if (!VibeMMOHUDLayout::IsValidElement(Pair.Key))
		{
			ElementsToRemove.Add(Pair.Key);
			continue;
		}

		Pair.Value.Sanitize();
		if (Pair.Value.IsDefault())
		{
			ElementsToRemove.Add(Pair.Key);
		}
	}

	for (const EVibeMMOHUDElement Element : ElementsToRemove)
	{
		ElementOverrides.Remove(Element);
	}
}

bool FVibeMMOHUDLayoutProfile::NearlyEquals(const FVibeMMOHUDLayoutProfile& Other) const
{
	if (ElementOverrides.Num() != Other.ElementOverrides.Num())
	{
		return false;
	}

	for (const TPair<EVibeMMOHUDElement, FVibeMMOHUDElementLayout>& Pair : ElementOverrides)
	{
		const FVibeMMOHUDElementLayout* OtherLayout = Other.ElementOverrides.Find(Pair.Key);
		if (!OtherLayout || !Pair.Value.NearlyEquals(*OtherLayout))
		{
			return false;
		}
	}
	return true;
}
