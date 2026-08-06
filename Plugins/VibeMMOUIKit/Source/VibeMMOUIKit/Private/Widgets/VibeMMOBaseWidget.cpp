#include "Widgets/VibeMMOBaseWidget.h"

#include "Components/TextBlock.h"
#include "Style/VibeMMOUIFunctionLibrary.h"
#include "Style/VibeMMOUISettings.h"

void UVibeMMOBaseWidget::SetStyleDataAsset(UVibeMMOUIStyleDataAsset* InStyleDataAsset)
{
	StyleDataAsset = InStyleDataAsset;
	ApplyVibeStyle();
}

UVibeMMOUIStyleDataAsset* UVibeMMOBaseWidget::GetResolvedStyleDataAsset() const
{
	if (StyleDataAsset)
	{
		return StyleDataAsset;
	}

	const UVibeMMOUISettings* Settings = GetDefault<UVibeMMOUISettings>();
	if (!Settings)
	{
		return nullptr;
	}

	TSoftObjectPtr<UVibeMMOUIStyleDataAsset> DefaultStyle = Settings->DefaultStyleDataAsset;
	return DefaultStyle.LoadSynchronous();
}

void UVibeMMOBaseWidget::ApplyTextRole(UTextBlock* TextBlock, const EVibeMMOUIFontRole Role) const
{
	UVibeMMOUIFunctionLibrary::ApplyTextRoleToTextBlock(TextBlock, GetResolvedStyleDataAsset(), Role);
}

void UVibeMMOBaseWidget::ApplyVibeStyle_Implementation()
{
}

void UVibeMMOBaseWidget::NativePreConstruct()
{
	Super::NativePreConstruct();
	ApplyVibeStyle();
}
