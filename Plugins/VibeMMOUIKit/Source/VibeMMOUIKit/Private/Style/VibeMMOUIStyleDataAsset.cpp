#include "Style/VibeMMOUIStyleDataAsset.h"

#include "Misc/Paths.h"
#include "Styling/CoreStyle.h"

namespace VibeMMOStyleDefaults
{
	static FString GetProjectSairaBlackItalicPath()
	{
		return FPaths::ProjectContentDir() / TEXT("UI/RED_Game/Fonts/Saira-BlackItalic.ttf");
	}

	static FSlateFontInfo MakeDefaultFont(const FName TypefaceName, const int32 Size, const int32 OutlineSize)
	{
		FSlateFontInfo Font = FCoreStyle::GetDefaultFontStyle(TypefaceName, Size);
		Font.LetterSpacing = 0;
		Font.OutlineSettings.OutlineSize = OutlineSize;
		Font.OutlineSettings.OutlineColor = FLinearColor(0.0f, 0.0f, 0.0f, 0.78f);
		return Font;
	}

	static FSlateFontInfo MakeSairaHeroFont(const int32 Size, const int32 OutlineSize)
	{
		const FString SairaPath = GetProjectSairaBlackItalicPath();
		FSlateFontInfo Font = FPaths::FileExists(SairaPath)
			? FSlateFontInfo(SairaPath, Size)
			: MakeDefaultFont(FName(TEXT("Bold")), Size, OutlineSize);
		Font.LetterSpacing = 0;
		Font.OutlineSettings.OutlineSize = OutlineSize;
		Font.OutlineSettings.OutlineColor = FLinearColor(0.0f, 0.0f, 0.0f, 0.78f);
		return Font;
	}
}

FVibeMMOFontRoleSizes::FVibeMMOFontRoleSizes()
	: HUDNumberSize(34)
	, AbilityKeybindSize(22)
	, WeaponSlotNumberSize(22)
	, LevelBadgeSize(20)
	, HeadingSize(28)
	, MainMenuTitleSize(64)
	, CharacterCreatorSectionHeaderSize(34)
	, TalentTreeTitleSize(38)
	, InventoryRarityLabelSize(24)
	, ImportantLabelSize(26)
	, CompanionBodySize(18)
	, TooltipBodySize(16)
	, QuestBodySize(18)
	, SettingsBodySize(16)
{
}

FVibeMMOTextTreatment::FVibeMMOTextTreatment()
	: TextColor(FLinearColor::White)
	, OutlineSize(2)
	, OutlineColor(FLinearColor(0.02f, 0.025f, 0.04f, 0.9f))
	, ShadowOffset(FVector2D(1.5f, 2.0f))
	, ShadowColor(FLinearColor(0.0f, 0.0f, 0.0f, 0.65f))
{
}

UVibeMMOUIStyleDataAsset::UVibeMMOUIStyleDataAsset()
	: PrimaryHeroFont(VibeMMOStyleDefaults::MakeSairaHeroFont(34, 2))
	, CompanionFont(VibeMMOStyleDefaults::MakeDefaultFont(FName(TEXT("Regular")), 18, 1))
	, ShieldColor(FLinearColor(0.05f, 0.25f, 1.0f, 1.0f))
	, HealthColor(FLinearColor(0.23f, 0.86f, 0.13f, 1.0f))
	, EnergyColor(FLinearColor(1.0f, 0.67f, 0.0f, 1.0f))
	, CommonRarityColor(FLinearColor(0.85f, 0.88f, 0.92f, 1.0f))
	, UncommonRarityColor(FLinearColor(0.16f, 0.92f, 0.36f, 1.0f))
	, RareRarityColor(FLinearColor(0.12f, 0.46f, 1.0f, 1.0f))
	, EpicRarityColor(FLinearColor(0.68f, 0.22f, 1.0f, 1.0f))
	, LegendaryRarityColor(FLinearColor(1.0f, 0.66f, 0.08f, 1.0f))
	, MythicRarityColor(FLinearColor(1.0f, 0.18f, 0.08f, 1.0f))
	// RED uses a dark, readable tactical glass surface.  The previous pale-blue
	// tint washed out over bright sand and made white labels compete with the
	// world.  Keep the blur, but give every screen a consistent deep-navy base.
	, GlassPanelTint(FLinearColor(0.018f, 0.045f, 0.075f, 0.78f))
	, GlassPanelBorderColor(FLinearColor(0.72f, 0.92f, 1.0f, 0.34f))
	, GlassHighlightColor(FLinearColor(1.0f, 1.0f, 1.0f, 0.42f))
	, GlassBlurStrength(16.0f)
	, GlassBlurRadius(10)
	, GlassCornerRadius(12.0f)
	, HUDSafeZonePadding(32.0f, 28.0f, 32.0f, 28.0f)
	, AbilitySlotSize(74.0f)
	, WeaponSlotSize(92.0f)
{
	CompanionTextTreatment.OutlineSize = 0;
	CompanionTextTreatment.ShadowOffset = FVector2D(1.0f, 1.0f);
	CompanionTextTreatment.ShadowColor = FLinearColor(0.0f, 0.0f, 0.0f, 0.45f);
}

FSlateFontInfo UVibeMMOUIStyleDataAsset::GetFontForRole(const EVibeMMOUIFontRole Role) const
{
	FSlateFontInfo Font = IsHeroFontRole(Role) ? PrimaryHeroFont : CompanionFont;
	const FVibeMMOTextTreatment& Treatment = GetTreatmentForRole(Role);

	Font.Size = GetSizeForRole(Role);
	Font.LetterSpacing = 0;
	Font.OutlineSettings.OutlineSize = Treatment.OutlineSize;
	Font.OutlineSettings.OutlineColor = Treatment.OutlineColor;

	return Font;
}

FTextBlockStyle UVibeMMOUIStyleDataAsset::GetTextBlockStyleForRole(const EVibeMMOUIFontRole Role) const
{
	const FVibeMMOTextTreatment& Treatment = GetTreatmentForRole(Role);

	FTextBlockStyle TextStyle;
	TextStyle.SetFont(GetFontForRole(Role));
	TextStyle.SetColorAndOpacity(FSlateColor(Treatment.TextColor));
	TextStyle.SetShadowOffset(Treatment.ShadowOffset);
	TextStyle.SetShadowColorAndOpacity(Treatment.ShadowColor);

	return TextStyle;
}

bool UVibeMMOUIStyleDataAsset::IsHeroFontRole(const EVibeMMOUIFontRole Role) const
{
	switch (Role)
	{
	case EVibeMMOUIFontRole::HUDNumber:
	case EVibeMMOUIFontRole::AbilityKeybind:
	case EVibeMMOUIFontRole::WeaponSlotNumber:
	case EVibeMMOUIFontRole::LevelBadge:
	case EVibeMMOUIFontRole::Heading:
	case EVibeMMOUIFontRole::MainMenuTitle:
	case EVibeMMOUIFontRole::CharacterCreatorSectionHeader:
	case EVibeMMOUIFontRole::TalentTreeTitle:
	case EVibeMMOUIFontRole::InventoryRarityLabel:
	case EVibeMMOUIFontRole::ImportantLabel:
		return true;
	case EVibeMMOUIFontRole::CompanionBody:
	case EVibeMMOUIFontRole::TooltipBody:
	case EVibeMMOUIFontRole::QuestBody:
	case EVibeMMOUIFontRole::SettingsBody:
		return false;
	default:
		return false;
	}
}

int32 UVibeMMOUIStyleDataAsset::GetSizeForRole(const EVibeMMOUIFontRole Role) const
{
	switch (Role)
	{
	case EVibeMMOUIFontRole::HUDNumber:
		return FontRoleSizes.HUDNumberSize;
	case EVibeMMOUIFontRole::AbilityKeybind:
		return FontRoleSizes.AbilityKeybindSize;
	case EVibeMMOUIFontRole::WeaponSlotNumber:
		return FontRoleSizes.WeaponSlotNumberSize;
	case EVibeMMOUIFontRole::LevelBadge:
		return FontRoleSizes.LevelBadgeSize;
	case EVibeMMOUIFontRole::Heading:
		return FontRoleSizes.HeadingSize;
	case EVibeMMOUIFontRole::MainMenuTitle:
		return FontRoleSizes.MainMenuTitleSize;
	case EVibeMMOUIFontRole::CharacterCreatorSectionHeader:
		return FontRoleSizes.CharacterCreatorSectionHeaderSize;
	case EVibeMMOUIFontRole::TalentTreeTitle:
		return FontRoleSizes.TalentTreeTitleSize;
	case EVibeMMOUIFontRole::InventoryRarityLabel:
		return FontRoleSizes.InventoryRarityLabelSize;
	case EVibeMMOUIFontRole::ImportantLabel:
		return FontRoleSizes.ImportantLabelSize;
	case EVibeMMOUIFontRole::CompanionBody:
		return FontRoleSizes.CompanionBodySize;
	case EVibeMMOUIFontRole::TooltipBody:
		return FontRoleSizes.TooltipBodySize;
	case EVibeMMOUIFontRole::QuestBody:
		return FontRoleSizes.QuestBodySize;
	case EVibeMMOUIFontRole::SettingsBody:
		return FontRoleSizes.SettingsBodySize;
	default:
		return FontRoleSizes.CompanionBodySize;
	}
}

const FVibeMMOTextTreatment& UVibeMMOUIStyleDataAsset::GetTreatmentForRole(const EVibeMMOUIFontRole Role) const
{
	return IsHeroFontRole(Role) ? HeroTextTreatment : CompanionTextTreatment;
}
