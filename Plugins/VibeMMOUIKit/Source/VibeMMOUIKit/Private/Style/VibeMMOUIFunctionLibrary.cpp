#include "Style/VibeMMOUIFunctionLibrary.h"

#include "Components/TextBlock.h"
#include "Misc/Paths.h"
#include "Styling/CoreStyle.h"

namespace
{
	int32 GetFallbackFontSizeForRole(const EVibeMMOUIFontRole Role)
	{
		switch (Role)
		{
		case EVibeMMOUIFontRole::HUDNumber:
			return 28;
		case EVibeMMOUIFontRole::AbilityKeybind:
			return 22;
		case EVibeMMOUIFontRole::WeaponSlotNumber:
			return 22;
		case EVibeMMOUIFontRole::LevelBadge:
			return 18;
		case EVibeMMOUIFontRole::Heading:
			return 28;
		case EVibeMMOUIFontRole::MainMenuTitle:
			return 64;
		case EVibeMMOUIFontRole::CharacterCreatorSectionHeader:
			return 34;
		case EVibeMMOUIFontRole::TalentTreeTitle:
			return 38;
		case EVibeMMOUIFontRole::InventoryRarityLabel:
			return 24;
		case EVibeMMOUIFontRole::ImportantLabel:
			return 26;
		case EVibeMMOUIFontRole::CompanionBody:
		case EVibeMMOUIFontRole::QuestBody:
			return 18;
		case EVibeMMOUIFontRole::TooltipBody:
		case EVibeMMOUIFontRole::SettingsBody:
			return 16;
		default:
			return 18;
		}
	}
}

FSlateFontInfo UVibeMMOUIFunctionLibrary::ResolveFontForRole(const UVibeMMOUIStyleDataAsset* StyleDataAsset, const EVibeMMOUIFontRole Role)
{
	if (StyleDataAsset)
	{
		return StyleDataAsset->GetFontForRole(Role);
	}

	const FString SairaPath = FPaths::ProjectContentDir() / TEXT("UI/RED_Game/Fonts/Saira-BlackItalic.ttf");
	FSlateFontInfo FallbackFont = FPaths::FileExists(SairaPath)
		? FSlateFontInfo(SairaPath, GetFallbackFontSizeForRole(Role))
		: FCoreStyle::GetDefaultFontStyle(FName(TEXT("Bold")), GetFallbackFontSizeForRole(Role));
	FallbackFont.LetterSpacing = 0;
	FallbackFont.OutlineSettings.OutlineSize = 2;
	FallbackFont.OutlineSettings.OutlineColor = FLinearColor(0.0f, 0.0f, 0.0f, 0.78f);
	return FallbackFont;
}

FTextBlockStyle UVibeMMOUIFunctionLibrary::ResolveTextBlockStyleForRole(const UVibeMMOUIStyleDataAsset* StyleDataAsset, const EVibeMMOUIFontRole Role)
{
	if (StyleDataAsset)
	{
		return StyleDataAsset->GetTextBlockStyleForRole(Role);
	}

	FTextBlockStyle FallbackStyle;
	FallbackStyle.SetFont(ResolveFontForRole(nullptr, Role));
	FallbackStyle.SetColorAndOpacity(FSlateColor(FLinearColor::White));
	FallbackStyle.SetShadowOffset(FVector2D(1.0f, 1.0f));
	FallbackStyle.SetShadowColorAndOpacity(FLinearColor(0.0f, 0.0f, 0.0f, 0.45f));
	return FallbackStyle;
}

void UVibeMMOUIFunctionLibrary::ApplyTextRoleToTextBlock(UTextBlock* TextBlock, const UVibeMMOUIStyleDataAsset* StyleDataAsset, const EVibeMMOUIFontRole Role)
{
	if (!TextBlock)
	{
		return;
	}

	const FTextBlockStyle TextStyle = ResolveTextBlockStyleForRole(StyleDataAsset, Role);
	TextBlock->SetFont(TextStyle.Font);
	TextBlock->SetColorAndOpacity(TextStyle.ColorAndOpacity);
	TextBlock->SetShadowOffset(TextStyle.ShadowOffset);
	TextBlock->SetShadowColorAndOpacity(TextStyle.ShadowColorAndOpacity);
}
