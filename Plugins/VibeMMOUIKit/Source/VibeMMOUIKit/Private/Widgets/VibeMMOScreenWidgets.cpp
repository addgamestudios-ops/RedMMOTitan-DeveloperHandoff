#include "Widgets/VibeMMOScreenWidgets.h"

#include "Blueprint/WidgetTree.h"
#include "Components/BackgroundBlur.h"
#include "Components/Border.h"
#include "Components/Button.h"
#include "Components/ButtonSlot.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/HorizontalBox.h"
#include "Components/HorizontalBoxSlot.h"
#include "Components/Image.h"
#include "Components/Overlay.h"
#include "Components/OverlaySlot.h"
#include "Components/SizeBox.h"
#include "Components/TextBlock.h"
#include "Components/VerticalBox.h"
#include "Components/VerticalBoxSlot.h"
#include "Data/VibeMMOUIDataAssets.h"
#include "Styling/SlateBrush.h"

namespace VibeMMOScreens
{
	static const FLinearColor PanelFill(0.018f, 0.045f, 0.075f, 0.78f);
	static const FLinearColor PanelAltFill(0.026f, 0.068f, 0.108f, 0.72f);
	static const FLinearColor CyanStroke(0.72f, 0.92f, 1.0f, 0.42f);
	static const FLinearColor PurpleStroke(0.84f, 0.56f, 1.0f, 0.42f);
	static const FLinearColor GoldStroke(1.0f, 0.82f, 0.38f, 0.48f);

	static void AddCanvasChild(UCanvasPanel* RootCanvas, UWidget* Child, const FAnchors& Anchors, const FVector2D& Alignment, const FVector2D& Position, const FVector2D& Size)
	{
		if (!RootCanvas || !Child)
		{
			return;
		}

		if (UCanvasPanelSlot* CanvasSlot = RootCanvas->AddChildToCanvas(Child))
		{
			CanvasSlot->SetAnchors(Anchors);
			CanvasSlot->SetAlignment(Alignment);
			CanvasSlot->SetPosition(Position);
			CanvasSlot->SetSize(Size);
		}
	}

	static void AddGlassLayer(UWidgetTree* WidgetTree, UOverlay* Overlay, const FName Name, const FVector2D& Size, const UVibeMMOUIStyleDataAsset* Style)
	{
		if (!WidgetTree || !Overlay)
		{
			return;
		}

		const float BlurStrength = Style ? Style->GlassBlurStrength : 18.0f;
		const int32 BlurRadius = Style ? Style->GlassBlurRadius : 12;
		const float CornerRadius = Style ? Style->GlassCornerRadius : 10.0f;
		const FLinearColor Tint = Style ? Style->GlassPanelTint : PanelFill;

		UBackgroundBlur* Blur = WidgetTree->ConstructWidget<UBackgroundBlur>(UBackgroundBlur::StaticClass(), *FString::Printf(TEXT("%s_Blur"), *Name.ToString()));
		Blur->SetBlurStrength(BlurStrength);
		Blur->SetOverrideAutoRadiusCalculation(true);
		Blur->SetBlurRadius(BlurRadius);
		Blur->SetCornerRadius(FVector4(CornerRadius, CornerRadius, CornerRadius, CornerRadius));

		USizeBox* BlurSize = WidgetTree->ConstructWidget<USizeBox>(USizeBox::StaticClass(), *FString::Printf(TEXT("%s_BlurSize"), *Name.ToString()));
		BlurSize->SetWidthOverride(Size.X);
		BlurSize->SetHeightOverride(Size.Y);
		Blur->SetContent(BlurSize);

		if (UOverlaySlot* BlurSlot = Overlay->AddChildToOverlay(Blur))
		{
			BlurSlot->SetHorizontalAlignment(HAlign_Fill);
			BlurSlot->SetVerticalAlignment(VAlign_Fill);
		}

		UBorder* TintLayer = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), *FString::Printf(TEXT("%s_Tint"), *Name.ToString()));
		TintLayer->SetBrushColor(Tint);
		if (UOverlaySlot* TintSlot = Overlay->AddChildToOverlay(TintLayer))
		{
			TintSlot->SetHorizontalAlignment(HAlign_Fill);
			TintSlot->SetVerticalAlignment(VAlign_Fill);
		}
	}

	static void ApplyBrushResource(UImage* Image, UObject* Resource, const FVector2D& ImageSize)
	{
		if (!Image)
		{
			return;
		}

		if (!Resource)
		{
			Image->SetBrush(FSlateBrush());
			Image->SetVisibility(ESlateVisibility::Collapsed);
			return;
		}

		FSlateBrush Brush;
		Brush.SetResourceObject(Resource);
		Brush.ImageSize = ImageSize;
		Image->SetBrush(Brush);
		Image->SetVisibility(ESlateVisibility::HitTestInvisible);
	}

	static void MakeButtonChromeTransparent(UButton* Button)
	{
		if (!Button)
		{
			return;
		}

		FButtonStyle TransparentStyle = Button->GetStyle();
		TransparentStyle.Normal.DrawAs = ESlateBrushDrawType::NoDrawType;
		TransparentStyle.Hovered.DrawAs = ESlateBrushDrawType::Box;
		TransparentStyle.Hovered.TintColor = FSlateColor(FLinearColor(0.18f, 0.86f, 1.0f, 0.12f));
		TransparentStyle.Pressed.DrawAs = ESlateBrushDrawType::Box;
		TransparentStyle.Pressed.TintColor = FSlateColor(FLinearColor(0.18f, 0.86f, 1.0f, 0.24f));
		TransparentStyle.Disabled.DrawAs = ESlateBrushDrawType::NoDrawType;
		Button->SetStyle(TransparentStyle);
		Button->SetBackgroundColor(FLinearColor::Transparent);
	}
}

UVibeMMOMainMenuWidget::UVibeMMOMainMenuWidget()
	: bBuildDefaultMenuInCpp(true)
{
}

void UVibeMMOMainMenuWidget::NativePreConstruct()
{
	if (bBuildDefaultMenuInCpp)
	{
		BuildDefaultMenuTree();
	}

	Super::NativePreConstruct();
}

void UVibeMMOMainMenuWidget::BuildDefaultMenuTree()
{
	if (!WidgetTree || bDefaultMenuTreeBuilt)
	{
		return;
	}

	if (WidgetTree->RootWidget && WidgetTree->RootWidget->GetFName() != FName(TEXT("DefaultVibeMainMenuRoot")))
	{
		return;
	}

	UCanvasPanel* RootCanvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("DefaultVibeMainMenuRoot"));
	WidgetTree->RootWidget = RootCanvas;

	UBorder* Backdrop = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("MainMenuBackdrop"));
	Backdrop->SetBrushColor(FLinearColor(0.01f, 0.018f, 0.034f, 0.42f));
	VibeMMOScreens::AddCanvasChild(RootCanvas, Backdrop, FAnchors(0.0f, 0.0f, 1.0f, 1.0f), FVector2D::ZeroVector, FVector2D::ZeroVector, FVector2D::ZeroVector);

	UHorizontalBox* TopNav = WidgetTree->ConstructWidget<UHorizontalBox>(UHorizontalBox::StaticClass(), TEXT("MainMenuTopNav"));
	VibeMMOScreens::AddCanvasChild(RootCanvas, TopNav, FAnchors(0.03f, 0.035f, 0.97f, 0.035f), FVector2D::ZeroVector, FVector2D::ZeroVector, FVector2D(0.0f, 60.0f));

	const TArray<FText> NavItems = {
		FText::FromString(TEXT("VIBE MMO UI KIT")),
		FText::FromString(TEXT("NEWS")),
		FText::FromString(TEXT("SERVERS")),
		FText::FromString(TEXT("CHARACTERS")),
		FText::FromString(TEXT("STORE")),
		FText::FromString(TEXT("SETTINGS"))
	};

	for (int32 Index = 0; Index < NavItems.Num(); ++Index)
	{
		UTextBlock* NavText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), *FString::Printf(TEXT("MainMenuTopNavText_%d"), Index));
		NavText->SetText(NavItems[Index]);
		NavText->SetJustification(Index == 0 ? ETextJustify::Left : ETextJustify::Center);
		ApplyTextRole(NavText, Index == 0 ? EVibeMMOUIFontRole::ImportantLabel : EVibeMMOUIFontRole::SettingsBody);
		if (UHorizontalBoxSlot* NavBoxSlot = TopNav->AddChildToHorizontalBox(NavText))
		{
			NavBoxSlot->SetPadding(Index == 0 ? FMargin(0.0f, 0.0f, 520.0f, 0.0f) : FMargin(18.0f, 0.0f));
			NavBoxSlot->SetHorizontalAlignment(Index == 0 ? HAlign_Left : HAlign_Center);
			NavBoxSlot->SetVerticalAlignment(VAlign_Center);
		}
	}

	UCanvasPanel* HeroPanel = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("MainMenuHeroPanel"));
	VibeMMOScreens::AddCanvasChild(RootCanvas, HeroPanel, FAnchors(0.045f, 0.18f), FVector2D::ZeroVector, FVector2D::ZeroVector, FVector2D(720.0f, 620.0f));
	const UVibeMMOUIStyleDataAsset* Style = GetResolvedStyleDataAsset();

	TitleText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("TitleText"));
	TitleText->SetText(FText::FromString(TEXT("RED FRONTIER")));
	TitleText->SetJustification(ETextJustify::Left);
	ApplyTextRole(TitleText, EVibeMMOUIFontRole::MainMenuTitle);
	VibeMMOScreens::AddCanvasChild(HeroPanel, TitleText, FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D::ZeroVector, FVector2D(660.0f, 92.0f));

	UTextBlock* SubtitleText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("MainMenuSubtitleText"));
	SubtitleText->SetText(FText::FromString(TEXT("A SCI-FI MMO UI FOUNDATION")));
	SubtitleText->SetJustification(ETextJustify::Left);
	ApplyTextRole(SubtitleText, EVibeMMOUIFontRole::ImportantLabel);
	VibeMMOScreens::AddCanvasChild(HeroPanel, SubtitleText, FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D(4.0f, 86.0f), FVector2D(560.0f, 40.0f));

	UTextBlock* BodyText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("MainMenuBodyText"));
	BodyText->SetText(FText::FromString(TEXT("Choose a realm, inspect population, and jump into the character flow.")));
	BodyText->SetJustification(ETextJustify::Left);
	ApplyTextRole(BodyText, EVibeMMOUIFontRole::CompanionBody);
	VibeMMOScreens::AddCanvasChild(HeroPanel, BodyText, FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D(4.0f, 138.0f), FVector2D(640.0f, 34.0f));

	UVerticalBox* MenuStack = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), TEXT("MainMenuButtonStack"));
	VibeMMOScreens::AddCanvasChild(HeroPanel, MenuStack, FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D(2.0f, 256.0f), FVector2D(360.0f, 260.0f));

	const TArray<FText> MenuItems = {
		FText::FromString(TEXT("PLAY NOW")),
		FText::FromString(TEXT("SELECT CHARACTER")),
		FText::FromString(TEXT("OPTIONS"))
	};

	for (int32 Index = 0; Index < MenuItems.Num(); ++Index)
	{
		UOverlay* ButtonFrame = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), *FString::Printf(TEXT("MainMenuButton_%d"), Index));
		VibeMMOScreens::AddGlassLayer(WidgetTree, ButtonFrame, *FString::Printf(TEXT("MainMenuButtonGlass_%d"), Index), FVector2D(360.0f, 58.0f), Style);

		UBorder* Outer = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), *FString::Printf(TEXT("MainMenuButtonOuter_%d"), Index));
		Outer->SetBrushColor(Index == 0 ? VibeMMOScreens::CyanStroke : FLinearColor(1.0f, 1.0f, 1.0f, 0.16f));
		if (UOverlaySlot* OuterSlot = ButtonFrame->AddChildToOverlay(Outer))
		{
			OuterSlot->SetHorizontalAlignment(HAlign_Fill);
			OuterSlot->SetVerticalAlignment(VAlign_Fill);
		}

		UBorder* Inner = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), *FString::Printf(TEXT("MainMenuButtonInner_%d"), Index));
		Inner->SetBrushColor(Index == 0 ? FLinearColor(0.08f, 0.58f, 1.0f, 0.28f) : FLinearColor(0.8f, 0.9f, 1.0f, 0.08f));
		if (UOverlaySlot* InnerSlot = ButtonFrame->AddChildToOverlay(Inner))
		{
			InnerSlot->SetPadding(FMargin(3.0f));
			InnerSlot->SetHorizontalAlignment(HAlign_Fill);
			InnerSlot->SetVerticalAlignment(VAlign_Fill);
		}

		UTextBlock* ItemText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), *FString::Printf(TEXT("MainMenuButtonText_%d"), Index));
		ItemText->SetText(MenuItems[Index]);
		ItemText->SetJustification(ETextJustify::Left);
		ApplyTextRole(ItemText, EVibeMMOUIFontRole::ImportantLabel);
		if (UOverlaySlot* TextSlot = ButtonFrame->AddChildToOverlay(ItemText))
		{
			TextSlot->SetPadding(FMargin(24.0f, 0.0f));
			TextSlot->SetHorizontalAlignment(HAlign_Left);
			TextSlot->SetVerticalAlignment(VAlign_Center);
		}

		if (UVerticalBoxSlot* StackSlot = MenuStack->AddChildToVerticalBox(ButtonFrame))
		{
			StackSlot->SetPadding(FMargin(0.0f, 0.0f, 0.0f, 20.0f));
			StackSlot->SetHorizontalAlignment(HAlign_Fill);
		}
	}

	UOverlay* FeaturedPanel = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), TEXT("MainMenuFeaturedPanel"));
	VibeMMOScreens::AddCanvasChild(RootCanvas, FeaturedPanel, FAnchors(0.64f, 0.22f), FVector2D::ZeroVector, FVector2D::ZeroVector, FVector2D(430.0f, 430.0f));
	VibeMMOScreens::AddGlassLayer(WidgetTree, FeaturedPanel, TEXT("MainMenuFeaturedGlass"), FVector2D(430.0f, 430.0f), Style);

	UBorder* FeaturedOuter = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("MainMenuFeaturedOuter"));
	FeaturedOuter->SetBrushColor(VibeMMOScreens::CyanStroke);
	if (UOverlaySlot* FeaturedOuterSlot = FeaturedPanel->AddChildToOverlay(FeaturedOuter))
	{
		FeaturedOuterSlot->SetHorizontalAlignment(HAlign_Fill);
		FeaturedOuterSlot->SetVerticalAlignment(VAlign_Fill);
	}

	UBorder* FeaturedInner = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("MainMenuFeaturedInner"));
	FeaturedInner->SetBrushColor(FLinearColor(0.72f, 0.86f, 1.0f, 0.08f));
	if (UOverlaySlot* FeaturedInnerSlot = FeaturedPanel->AddChildToOverlay(FeaturedInner))
	{
		FeaturedInnerSlot->SetPadding(FMargin(4.0f));
		FeaturedInnerSlot->SetHorizontalAlignment(HAlign_Fill);
		FeaturedInnerSlot->SetVerticalAlignment(VAlign_Fill);
	}

	UTextBlock* CharacterMark = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("MainMenuFeaturedCharacterText"));
	CharacterMark->SetText(FText::FromString(TEXT("HERO\\nPREVIEW")));
	CharacterMark->SetJustification(ETextJustify::Center);
	ApplyTextRole(CharacterMark, EVibeMMOUIFontRole::TalentTreeTitle);
	if (UOverlaySlot* CharacterMarkSlot = FeaturedPanel->AddChildToOverlay(CharacterMark))
	{
		CharacterMarkSlot->SetHorizontalAlignment(HAlign_Center);
		CharacterMarkSlot->SetVerticalAlignment(VAlign_Center);
	}

	UOverlay* AccountPanel = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), TEXT("MainMenuAccountPanel"));
	VibeMMOScreens::AddCanvasChild(RootCanvas, AccountPanel, FAnchors(0.34f, 0.64f), FVector2D::ZeroVector, FVector2D::ZeroVector, FVector2D(1140.0f, 300.0f));
	VibeMMOScreens::AddGlassLayer(WidgetTree, AccountPanel, TEXT("MainMenuAccountGlass"), FVector2D(1140.0f, 300.0f), Style);

	UBorder* AccountOuter = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("MainMenuAccountOuter"));
	AccountOuter->SetBrushColor(FLinearColor(0.08f, 0.78f, 1.0f, 0.38f));
	if (UOverlaySlot* AccountOuterSlot = AccountPanel->AddChildToOverlay(AccountOuter))
	{
		AccountOuterSlot->SetHorizontalAlignment(HAlign_Fill);
		AccountOuterSlot->SetVerticalAlignment(VAlign_Fill);
	}

	UBorder* AccountInner = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("MainMenuAccountInner"));
	AccountInner->SetBrushColor(FLinearColor(0.72f, 0.86f, 1.0f, 0.08f));
	if (UOverlaySlot* AccountInnerSlot = AccountPanel->AddChildToOverlay(AccountInner))
	{
		AccountInnerSlot->SetPadding(FMargin(2.0f));
		AccountInnerSlot->SetHorizontalAlignment(HAlign_Fill);
		AccountInnerSlot->SetVerticalAlignment(VAlign_Fill);
	}

	UTextBlock* AccountText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("MainMenuAccountText"));
	AccountText->SetText(FText::FromString(TEXT("START FLOW\\nPlay opens server select before character select. In-game inventory, equipment, talents, map, quests, and settings live after entering the world.")));
	AccountText->SetJustification(ETextJustify::Left);
	ApplyTextRole(AccountText, EVibeMMOUIFontRole::ImportantLabel);
	if (UOverlaySlot* AccountTextSlot = AccountPanel->AddChildToOverlay(AccountText))
	{
		AccountTextSlot->SetPadding(FMargin(32.0f, 26.0f));
		AccountTextSlot->SetHorizontalAlignment(HAlign_Left);
		AccountTextSlot->SetVerticalAlignment(VAlign_Top);
	}

	bDefaultMenuTreeBuilt = true;
}

void UVibeMMOMainMenuWidget::ApplyVibeStyle_Implementation()
{
	Super::ApplyVibeStyle_Implementation();
	ApplyTextRole(TitleText, EVibeMMOUIFontRole::MainMenuTitle);
}

UVibeMMOServerSelectWidget::UVibeMMOServerSelectWidget()
	: bBuildDefaultServerSelectInCpp(true)
{
}

void UVibeMMOServerSelectWidget::NativePreConstruct()
{
	if (bBuildDefaultServerSelectInCpp)
	{
		BuildDefaultServerSelectTree();
	}

	Super::NativePreConstruct();
}

void UVibeMMOServerSelectWidget::BuildDefaultServerSelectTree()
{
	if (!WidgetTree || bDefaultServerTreeBuilt)
	{
		return;
	}

	if (WidgetTree->RootWidget && WidgetTree->RootWidget->GetFName() != FName(TEXT("DefaultVibeServerSelectRoot")))
	{
		return;
	}

	UCanvasPanel* RootCanvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("DefaultVibeServerSelectRoot"));
	WidgetTree->RootWidget = RootCanvas;

	UBorder* Backdrop = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("ServerSelectBackdrop"));
	Backdrop->SetBrushColor(FLinearColor(0.01f, 0.018f, 0.034f, 0.42f));
	VibeMMOScreens::AddCanvasChild(RootCanvas, Backdrop, FAnchors(0.0f, 0.0f, 1.0f, 1.0f), FVector2D::ZeroVector, FVector2D::ZeroVector, FVector2D::ZeroVector);
	const UVibeMMOUIStyleDataAsset* Style = GetResolvedStyleDataAsset();

	UHorizontalBox* TopNav = WidgetTree->ConstructWidget<UHorizontalBox>(UHorizontalBox::StaticClass(), TEXT("ServerSelectTopNav"));
	VibeMMOScreens::AddCanvasChild(RootCanvas, TopNav, FAnchors(0.03f, 0.035f, 0.97f, 0.035f), FVector2D::ZeroVector, FVector2D::ZeroVector, FVector2D(0.0f, 60.0f));

	const TArray<FText> NavItems = {
		FText::FromString(TEXT("VIBE MMO UI KIT")),
		FText::FromString(TEXT("NEWS")),
		FText::FromString(TEXT("SERVERS")),
		FText::FromString(TEXT("CHARACTERS")),
		FText::FromString(TEXT("STORE")),
		FText::FromString(TEXT("SETTINGS"))
	};

	for (int32 Index = 0; Index < NavItems.Num(); ++Index)
	{
		UTextBlock* NavText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), *FString::Printf(TEXT("ServerSelectTopNavText_%d"), Index));
		NavText->SetText(NavItems[Index]);
		NavText->SetJustification(Index == 0 ? ETextJustify::Left : ETextJustify::Center);
		ApplyTextRole(NavText, Index == 0 ? EVibeMMOUIFontRole::ImportantLabel : EVibeMMOUIFontRole::SettingsBody);
		if (UHorizontalBoxSlot* NavBoxSlot = TopNav->AddChildToHorizontalBox(NavText))
		{
			NavBoxSlot->SetPadding(Index == 0 ? FMargin(0.0f, 0.0f, 520.0f, 0.0f) : FMargin(18.0f, 0.0f));
			NavBoxSlot->SetHorizontalAlignment(Index == 0 ? HAlign_Left : HAlign_Center);
			NavBoxSlot->SetVerticalAlignment(VAlign_Center);
		}
	}

	TitleText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("TitleText"));
	TitleText->SetText(FText::FromString(TEXT("SELECT REALM")));
	TitleText->SetJustification(ETextJustify::Left);
	ApplyTextRole(TitleText, EVibeMMOUIFontRole::MainMenuTitle);
	VibeMMOScreens::AddCanvasChild(RootCanvas, TitleText, FAnchors(0.07f, 0.18f), FVector2D::ZeroVector, FVector2D::ZeroVector, FVector2D(720.0f, 90.0f));

	UTextBlock* InstructionText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("ServerSelectInstructionText"));
	InstructionText->SetText(FText::FromString(TEXT("Inspect population, ruleset, queue, and region before entering the character flow.")));
	InstructionText->SetJustification(ETextJustify::Left);
	ApplyTextRole(InstructionText, EVibeMMOUIFontRole::CompanionBody);
	VibeMMOScreens::AddCanvasChild(RootCanvas, InstructionText, FAnchors(0.07f, 0.28f), FVector2D::ZeroVector, FVector2D::ZeroVector, FVector2D(760.0f, 42.0f));

	UOverlay* RealmPanel = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), TEXT("ServerSelectRealmPanel"));
	VibeMMOScreens::AddCanvasChild(RootCanvas, RealmPanel, FAnchors(0.5f, 0.68f), FVector2D(0.5f, 0.5f), FVector2D::ZeroVector, FVector2D(1180.0f, 370.0f));
	VibeMMOScreens::AddGlassLayer(WidgetTree, RealmPanel, TEXT("ServerSelectRealmGlass"), FVector2D(1180.0f, 370.0f), Style);

	UBorder* RealmOuter = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("ServerSelectRealmOuter"));
	RealmOuter->SetBrushColor(Style ? Style->GlassPanelBorderColor : FLinearColor(0.86f, 0.95f, 1.0f, 0.36f));
	if (UOverlaySlot* RealmOuterSlot = RealmPanel->AddChildToOverlay(RealmOuter))
	{
		RealmOuterSlot->SetHorizontalAlignment(HAlign_Fill);
		RealmOuterSlot->SetVerticalAlignment(VAlign_Fill);
	}

	UBorder* RealmInner = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("ServerSelectRealmInner"));
	RealmInner->SetBrushColor(FLinearColor(0.72f, 0.86f, 1.0f, 0.08f));
	if (UOverlaySlot* RealmInnerSlot = RealmPanel->AddChildToOverlay(RealmInner))
	{
		RealmInnerSlot->SetPadding(FMargin(2.0f));
		RealmInnerSlot->SetHorizontalAlignment(HAlign_Fill);
		RealmInnerSlot->SetVerticalAlignment(VAlign_Fill);
	}

	UVerticalBox* PanelStack = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), TEXT("ServerSelectPanelStack"));
	if (UOverlaySlot* PanelStackSlot = RealmPanel->AddChildToOverlay(PanelStack))
	{
		PanelStackSlot->SetPadding(FMargin(34.0f, 28.0f));
		PanelStackSlot->SetHorizontalAlignment(HAlign_Fill);
		PanelStackSlot->SetVerticalAlignment(VAlign_Fill);
	}

	UTextBlock* PanelTitle = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("ServerSelectPanelTitle"));
	PanelTitle->SetText(FText::FromString(TEXT("AVAILABLE REALMS")));
	PanelTitle->SetJustification(ETextJustify::Left);
	ApplyTextRole(PanelTitle, EVibeMMOUIFontRole::TalentTreeTitle);
	if (UVerticalBoxSlot* PanelTitleSlot = PanelStack->AddChildToVerticalBox(PanelTitle))
	{
		PanelTitleSlot->SetHorizontalAlignment(HAlign_Left);
	}

	UHorizontalBox* ServerRow = WidgetTree->ConstructWidget<UHorizontalBox>(UHorizontalBox::StaticClass(), TEXT("ServerCardRow"));
	if (UVerticalBoxSlot* ServerRowSlot = PanelStack->AddChildToVerticalBox(ServerRow))
	{
		ServerRowSlot->SetPadding(FMargin(0.0f, 22.0f, 0.0f, 0.0f));
		ServerRowSlot->SetHorizontalAlignment(HAlign_Fill);
	}

	struct FServerCardSpec
	{
		const TCHAR* Name;
		const TCHAR* Region;
		const TCHAR* RuleSet;
		const TCHAR* Status;
		FLinearColor StrokeColor;
	};

	const FServerCardSpec Cards[] = {
		{ TEXT("AURORA"), TEXT("NA EAST"), TEXT("PVE"), TEXT("LOW QUEUE"), VibeMMOScreens::CyanStroke },
		{ TEXT("EMBER"), TEXT("EU CENTRAL"), TEXT("PVP"), TEXT("MEDIUM"), VibeMMOScreens::GoldStroke },
		{ TEXT("NOVA"), TEXT("TEST REALM"), TEXT("PTR"), TEXT("LOCKED"), VibeMMOScreens::PurpleStroke }
	};

	for (int32 Index = 0; Index < UE_ARRAY_COUNT(Cards); ++Index)
	{
		UOverlay* Card = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), *FString::Printf(TEXT("ServerCard_%d"), Index));
		VibeMMOScreens::AddGlassLayer(WidgetTree, Card, *FString::Printf(TEXT("ServerCardGlass_%d"), Index), FVector2D(326.0f, 236.0f), Style);

		UBorder* Outer = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), *FString::Printf(TEXT("ServerCardOuter_%d"), Index));
		Outer->SetBrushColor(Cards[Index].StrokeColor);
		if (UOverlaySlot* OuterSlot = Card->AddChildToOverlay(Outer))
		{
			OuterSlot->SetHorizontalAlignment(HAlign_Fill);
			OuterSlot->SetVerticalAlignment(VAlign_Fill);
		}

		UBorder* Inner = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), *FString::Printf(TEXT("ServerCardInner_%d"), Index));
		Inner->SetBrushColor(FLinearColor(0.76f, 0.88f, 1.0f, 0.08f));
		if (UOverlaySlot* InnerSlot = Card->AddChildToOverlay(Inner))
		{
			InnerSlot->SetPadding(FMargin(4.0f));
			InnerSlot->SetHorizontalAlignment(HAlign_Fill);
			InnerSlot->SetVerticalAlignment(VAlign_Fill);
		}

		UVerticalBox* CardStack = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), *FString::Printf(TEXT("ServerCardStack_%d"), Index));
		if (UOverlaySlot* StackSlot = Card->AddChildToOverlay(CardStack))
		{
			StackSlot->SetPadding(FMargin(20.0f));
			StackSlot->SetHorizontalAlignment(HAlign_Fill);
			StackSlot->SetVerticalAlignment(VAlign_Fill);
		}

		UBorder* MiniMap = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), *FString::Printf(TEXT("ServerCardMiniMap_%d"), Index));
		MiniMap->SetBrushColor(FLinearColor(0.78f, 0.92f, 1.0f, 0.10f));
		USizeBox* MiniMapSize = WidgetTree->ConstructWidget<USizeBox>(USizeBox::StaticClass(), *FString::Printf(TEXT("ServerCardMiniMapSize_%d"), Index));
		MiniMapSize->SetHeightOverride(74.0f);
		MiniMap->SetContent(MiniMapSize);
		if (UVerticalBoxSlot* MiniMapSlot = CardStack->AddChildToVerticalBox(MiniMap))
		{
			MiniMapSlot->SetHorizontalAlignment(HAlign_Fill);
			MiniMapSlot->SetPadding(FMargin(0.0f, 0.0f, 0.0f, 16.0f));
		}

		UTextBlock* NameText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), *FString::Printf(TEXT("ServerCardName_%d"), Index));
		NameText->SetText(FText::FromString(Cards[Index].Name));
		ApplyTextRole(NameText, EVibeMMOUIFontRole::ImportantLabel);
		if (UVerticalBoxSlot* NameSlot = CardStack->AddChildToVerticalBox(NameText))
		{
			NameSlot->SetHorizontalAlignment(HAlign_Left);
		}

		UTextBlock* RegionText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), *FString::Printf(TEXT("ServerCardRegion_%d"), Index));
		RegionText->SetText(FText::FromString(Cards[Index].Region));
		ApplyTextRole(RegionText, EVibeMMOUIFontRole::CompanionBody);
		if (UVerticalBoxSlot* RegionSlot = CardStack->AddChildToVerticalBox(RegionText))
		{
			RegionSlot->SetPadding(FMargin(0.0f, 16.0f, 0.0f, 0.0f));
			RegionSlot->SetHorizontalAlignment(HAlign_Left);
		}

		UTextBlock* RuleText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), *FString::Printf(TEXT("ServerCardRule_%d"), Index));
		RuleText->SetText(FText::FromString(Cards[Index].RuleSet));
		ApplyTextRole(RuleText, EVibeMMOUIFontRole::SettingsBody);
		if (UVerticalBoxSlot* RuleSlot = CardStack->AddChildToVerticalBox(RuleText))
		{
			RuleSlot->SetPadding(FMargin(0.0f, 8.0f, 0.0f, 0.0f));
			RuleSlot->SetHorizontalAlignment(HAlign_Left);
		}

		UTextBlock* StatusText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), *FString::Printf(TEXT("ServerCardStatus_%d"), Index));
		StatusText->SetText(FText::FromString(Cards[Index].Status));
		ApplyTextRole(StatusText, EVibeMMOUIFontRole::InventoryRarityLabel);
		if (UVerticalBoxSlot* StatusSlot = CardStack->AddChildToVerticalBox(StatusText))
		{
			StatusSlot->SetPadding(FMargin(0.0f, 16.0f, 0.0f, 0.0f));
			StatusSlot->SetHorizontalAlignment(HAlign_Left);
		}

		USizeBox* CardSize = WidgetTree->ConstructWidget<USizeBox>(USizeBox::StaticClass(), *FString::Printf(TEXT("ServerCardSize_%d"), Index));
		CardSize->SetWidthOverride(326.0f);
		CardSize->SetHeightOverride(236.0f);
		CardSize->SetContent(Card);

		if (UHorizontalBoxSlot* RowSlot = ServerRow->AddChildToHorizontalBox(CardSize))
		{
			RowSlot->SetPadding(FMargin(16.0f, 0.0f));
			RowSlot->SetHorizontalAlignment(HAlign_Fill);
			RowSlot->SetVerticalAlignment(VAlign_Fill);
		}
	}

	UOverlay* ConnectButton = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), TEXT("ServerSelectConnectButton"));
	VibeMMOScreens::AddCanvasChild(RootCanvas, ConnectButton, FAnchors(0.76f, 0.88f), FVector2D(0.5f, 0.5f), FVector2D::ZeroVector, FVector2D(320.0f, 64.0f));
	VibeMMOScreens::AddGlassLayer(WidgetTree, ConnectButton, TEXT("ServerSelectConnectGlass"), FVector2D(320.0f, 64.0f), Style);

	UBorder* ConnectOuter = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("ServerSelectConnectOuter"));
	ConnectOuter->SetBrushColor(VibeMMOScreens::CyanStroke);
	if (UOverlaySlot* ConnectOuterSlot = ConnectButton->AddChildToOverlay(ConnectOuter))
	{
		ConnectOuterSlot->SetHorizontalAlignment(HAlign_Fill);
		ConnectOuterSlot->SetVerticalAlignment(VAlign_Fill);
	}

	UBorder* ConnectInner = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("ServerSelectConnectInner"));
	ConnectInner->SetBrushColor(FLinearColor(0.08f, 0.58f, 1.0f, 0.28f));
	if (UOverlaySlot* ConnectInnerSlot = ConnectButton->AddChildToOverlay(ConnectInner))
	{
		ConnectInnerSlot->SetPadding(FMargin(3.0f));
		ConnectInnerSlot->SetHorizontalAlignment(HAlign_Fill);
		ConnectInnerSlot->SetVerticalAlignment(VAlign_Fill);
	}

	UTextBlock* ConnectText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("ServerSelectConnectText"));
	ConnectText->SetText(FText::FromString(TEXT("CONNECT")));
	ApplyTextRole(ConnectText, EVibeMMOUIFontRole::ImportantLabel);
	if (UOverlaySlot* ConnectTextSlot = ConnectButton->AddChildToOverlay(ConnectText))
	{
		ConnectTextSlot->SetHorizontalAlignment(HAlign_Center);
		ConnectTextSlot->SetVerticalAlignment(VAlign_Center);
	}

	bDefaultServerTreeBuilt = true;
}

void UVibeMMOServerSelectWidget::ApplyVibeStyle_Implementation()
{
	Super::ApplyVibeStyle_Implementation();
	ApplyTextRole(TitleText, EVibeMMOUIFontRole::MainMenuTitle);
}

UVibeMMOCharacterSelectWidget::UVibeMMOCharacterSelectWidget()
	: bBuildDefaultCharacterSelectInCpp(true)
{
}

void UVibeMMOCharacterSelectWidget::NativePreConstruct()
{
	if (bBuildDefaultCharacterSelectInCpp)
	{
		BuildDefaultCharacterSelectTree();
	}

	Super::NativePreConstruct();
}

void UVibeMMOCharacterSelectWidget::SetCharacterPreviewResource(const int32 CharacterIndex, UObject* PreviewResource)
{
	if (!CharacterPreviewImages.IsValidIndex(CharacterIndex))
	{
		return;
	}

	VibeMMOScreens::ApplyBrushResource(CharacterPreviewImages[CharacterIndex], PreviewResource, FVector2D(170.0f, 260.0f));
}

void UVibeMMOCharacterSelectWidget::BuildDefaultCharacterSelectTree()
{
	if (!WidgetTree || bDefaultCharacterSelectTreeBuilt)
	{
		return;
	}

	if (WidgetTree->RootWidget && WidgetTree->RootWidget->GetFName() != FName(TEXT("DefaultVibeCharacterSelectRoot")))
	{
		return;
	}

	CharacterPreviewImages.Reset();
	const UVibeMMOUIStyleDataAsset* Style = GetResolvedStyleDataAsset();

	UCanvasPanel* RootCanvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("DefaultVibeCharacterSelectRoot"));
	WidgetTree->RootWidget = RootCanvas;

	UBorder* Backdrop = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("CharacterSelectBackdrop"));
	Backdrop->SetBrushColor(FLinearColor(0.01f, 0.018f, 0.034f, 0.42f));
	VibeMMOScreens::AddCanvasChild(RootCanvas, Backdrop, FAnchors(0.0f, 0.0f, 1.0f, 1.0f), FVector2D::ZeroVector, FVector2D::ZeroVector, FVector2D::ZeroVector);

	TitleText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("CharacterSelectTitleText"));
	TitleText->SetText(FText::FromString(TEXT("CHARACTER SELECT")));
	TitleText->SetJustification(ETextJustify::Left);
	ApplyTextRole(TitleText, EVibeMMOUIFontRole::MainMenuTitle);
	VibeMMOScreens::AddCanvasChild(RootCanvas, TitleText, FAnchors(0.065f, 0.09f), FVector2D::ZeroVector, FVector2D::ZeroVector, FVector2D(720.0f, 84.0f));

	UTextBlock* RealmText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("CharacterSelectRealmText"));
	RealmText->SetText(FText::FromString(TEXT("AURORA  /  NA EAST  /  LOW QUEUE")));
	ApplyTextRole(RealmText, EVibeMMOUIFontRole::ImportantLabel);
	VibeMMOScreens::AddCanvasChild(RootCanvas, RealmText, FAnchors(0.065f, 0.18f), FVector2D::ZeroVector, FVector2D::ZeroVector, FVector2D(520.0f, 36.0f));

	UOverlay* PreviewPanel = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), TEXT("CharacterSelectPreviewPanel"));
	VibeMMOScreens::AddCanvasChild(RootCanvas, PreviewPanel, FAnchors(0.58f, 0.5f), FVector2D(0.5f, 0.5f), FVector2D::ZeroVector, FVector2D(430.0f, 650.0f));
	VibeMMOScreens::AddGlassLayer(WidgetTree, PreviewPanel, TEXT("CharacterSelectPreviewGlass"), FVector2D(430.0f, 650.0f), Style);

	UImage* FeaturedPreviewImage = WidgetTree->ConstructWidget<UImage>(UImage::StaticClass(), TEXT("CharacterSelectFeaturedPreviewImage"));
	FeaturedPreviewImage->SetVisibility(ESlateVisibility::Collapsed);
	if (UOverlaySlot* FeaturedImageSlot = PreviewPanel->AddChildToOverlay(FeaturedPreviewImage))
	{
		FeaturedImageSlot->SetPadding(FMargin(18.0f));
		FeaturedImageSlot->SetHorizontalAlignment(HAlign_Fill);
		FeaturedImageSlot->SetVerticalAlignment(VAlign_Fill);
	}
	CharacterPreviewImages.Add(FeaturedPreviewImage);

	UTextBlock* FeaturedFallback = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("CharacterSelectFeaturedFallbackText"));
	FeaturedFallback->SetText(FText::FromString(TEXT("SELECTED\\nCHARACTER RENDER")));
	FeaturedFallback->SetJustification(ETextJustify::Center);
	ApplyTextRole(FeaturedFallback, EVibeMMOUIFontRole::TalentTreeTitle);
	if (UOverlaySlot* FallbackSlot = PreviewPanel->AddChildToOverlay(FeaturedFallback))
	{
		FallbackSlot->SetHorizontalAlignment(HAlign_Center);
		FallbackSlot->SetVerticalAlignment(VAlign_Center);
	}

	UVerticalBox* RosterStack = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), TEXT("CharacterSelectRosterStack"));
	VibeMMOScreens::AddCanvasChild(RootCanvas, RosterStack, FAnchors(0.065f, 0.32f), FVector2D::ZeroVector, FVector2D::ZeroVector, FVector2D(430.0f, 390.0f));

	struct FCharacterCardSpec
	{
		const TCHAR* Name;
		const TCHAR* Detail;
		FLinearColor Accent;
	};

	const FCharacterCardSpec Cards[] = {
		{ TEXT("VEX ARDEN"), TEXT("LV 31 VOID RANGER"), VibeMMOScreens::CyanStroke },
		{ TEXT("MIRA SOL"), TEXT("LV 12 TECH MAGE"), VibeMMOScreens::PurpleStroke },
		{ TEXT("NEW CHARACTER"), TEXT("CREATE SLOT"), FLinearColor(0.22f, 0.96f, 0.48f, 0.48f) }
	};

	for (int32 Index = 0; Index < UE_ARRAY_COUNT(Cards); ++Index)
	{
		UOverlay* Card = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), *FString::Printf(TEXT("CharacterSelectCard_%d"), Index));
		VibeMMOScreens::AddGlassLayer(WidgetTree, Card, *FString::Printf(TEXT("CharacterSelectCardGlass_%d"), Index), FVector2D(430.0f, 88.0f), Style);

		UBorder* CardBorder = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), *FString::Printf(TEXT("CharacterSelectCardBorder_%d"), Index));
		CardBorder->SetBrushColor(Cards[Index].Accent);
		if (UOverlaySlot* BorderSlot = Card->AddChildToOverlay(CardBorder))
		{
			BorderSlot->SetHorizontalAlignment(HAlign_Fill);
			BorderSlot->SetVerticalAlignment(VAlign_Fill);
		}

		UVerticalBox* CardTextStack = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), *FString::Printf(TEXT("CharacterSelectCardTextStack_%d"), Index));
		if (UOverlaySlot* TextStackSlot = Card->AddChildToOverlay(CardTextStack))
		{
			TextStackSlot->SetPadding(FMargin(24.0f, 12.0f));
			TextStackSlot->SetHorizontalAlignment(HAlign_Fill);
			TextStackSlot->SetVerticalAlignment(VAlign_Fill);
		}

		UTextBlock* NameText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), *FString::Printf(TEXT("CharacterSelectCardName_%d"), Index));
		NameText->SetText(FText::FromString(Cards[Index].Name));
		ApplyTextRole(NameText, EVibeMMOUIFontRole::ImportantLabel);
		if (UVerticalBoxSlot* NameSlot = CardTextStack->AddChildToVerticalBox(NameText))
		{
			NameSlot->SetHorizontalAlignment(HAlign_Left);
		}

		UTextBlock* DetailText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), *FString::Printf(TEXT("CharacterSelectCardDetail_%d"), Index));
		DetailText->SetText(FText::FromString(Cards[Index].Detail));
		ApplyTextRole(DetailText, EVibeMMOUIFontRole::SettingsBody);
		if (UVerticalBoxSlot* DetailSlot = CardTextStack->AddChildToVerticalBox(DetailText))
		{
			DetailSlot->SetPadding(FMargin(0.0f, 4.0f, 0.0f, 0.0f));
			DetailSlot->SetHorizontalAlignment(HAlign_Left);
		}

		if (UVerticalBoxSlot* RosterSlot = RosterStack->AddChildToVerticalBox(Card))
		{
			RosterSlot->SetPadding(FMargin(0.0f, 0.0f, 0.0f, 18.0f));
			RosterSlot->SetHorizontalAlignment(HAlign_Fill);
		}
	}

	UOverlay* EnterButton = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), TEXT("CharacterSelectEnterButton"));
	VibeMMOScreens::AddCanvasChild(RootCanvas, EnterButton, FAnchors(0.58f, 0.86f), FVector2D(0.5f, 0.5f), FVector2D::ZeroVector, FVector2D(330.0f, 64.0f));
	VibeMMOScreens::AddGlassLayer(WidgetTree, EnterButton, TEXT("CharacterSelectEnterGlass"), FVector2D(330.0f, 64.0f), Style);

	UTextBlock* EnterText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("CharacterSelectEnterText"));
	EnterText->SetText(FText::FromString(TEXT("ENTER WORLD")));
	ApplyTextRole(EnterText, EVibeMMOUIFontRole::ImportantLabel);
	if (UOverlaySlot* EnterTextSlot = EnterButton->AddChildToOverlay(EnterText))
	{
		EnterTextSlot->SetHorizontalAlignment(HAlign_Center);
		EnterTextSlot->SetVerticalAlignment(VAlign_Center);
	}

	bDefaultCharacterSelectTreeBuilt = true;
}

void UVibeMMOCharacterSelectWidget::ApplyCharacterSelectTextRoles()
{
	ApplyTextRole(TitleText, EVibeMMOUIFontRole::MainMenuTitle);
}

void UVibeMMOCharacterSelectWidget::ApplyVibeStyle_Implementation()
{
	Super::ApplyVibeStyle_Implementation();
	ApplyCharacterSelectTextRoles();
}

UVibeMMOCharacterCreatorWidget::UVibeMMOCharacterCreatorWidget()
	: bBuildDefaultCharacterCreatorInCpp(true)
{
}

void UVibeMMOCharacterCreatorWidget::NativePreConstruct()
{
	if (bBuildDefaultCharacterCreatorInCpp)
	{
		BuildDefaultCharacterCreatorTree();
	}

	Super::NativePreConstruct();
}

void UVibeMMOCharacterCreatorWidget::SetCharacterPreviewResource(UObject* PreviewResource)
{
	VibeMMOScreens::ApplyBrushResource(CharacterPreviewImage, PreviewResource, FVector2D(360.0f, 560.0f));
}

void UVibeMMOCharacterCreatorWidget::BuildDefaultCharacterCreatorTree()
{
	if (!WidgetTree || bDefaultCharacterCreatorTreeBuilt)
	{
		return;
	}

	if (WidgetTree->RootWidget && WidgetTree->RootWidget->GetFName() != FName(TEXT("DefaultVibeCharacterCreatorRoot")))
	{
		return;
	}

	const UVibeMMOUIStyleDataAsset* Style = GetResolvedStyleDataAsset();
	const UVibeMMOCharacterCreationDataAsset* CreatorData = CharacterCreatorDataAsset;

	UCanvasPanel* RootCanvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("DefaultVibeCharacterCreatorRoot"));
	WidgetTree->RootWidget = RootCanvas;

	UBorder* Backdrop = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("CharacterCreatorBackdrop"));
	Backdrop->SetBrushColor(FLinearColor(0.01f, 0.018f, 0.034f, 0.42f));
	VibeMMOScreens::AddCanvasChild(RootCanvas, Backdrop, FAnchors(0.0f, 0.0f, 1.0f, 1.0f), FVector2D::ZeroVector, FVector2D::ZeroVector, FVector2D::ZeroVector);

	SectionHeaderText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("CharacterCreatorTitleText"));
	SectionHeaderText->SetText(FText::FromString(TEXT("CREATE CHARACTER")));
	ApplyTextRole(SectionHeaderText, EVibeMMOUIFontRole::MainMenuTitle);
	VibeMMOScreens::AddCanvasChild(RootCanvas, SectionHeaderText, FAnchors(0.055f, 0.08f), FVector2D::ZeroVector, FVector2D::ZeroVector, FVector2D(760.0f, 84.0f));

	DescriptionText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("CharacterCreatorDescriptionText"));
	DescriptionText->SetText(FText::FromString(TEXT("Pick origin, body, class fantasy, and cosmetics before entering the world.")));
	DescriptionText->SetJustification(ETextJustify::Left);
	ApplyTextRole(DescriptionText, EVibeMMOUIFontRole::CompanionBody);
	VibeMMOScreens::AddCanvasChild(RootCanvas, DescriptionText, FAnchors(0.055f, 0.17f), FVector2D::ZeroVector, FVector2D::ZeroVector, FVector2D(780.0f, 36.0f));

	UOverlay* OptionPanel = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), TEXT("CharacterCreatorOptionPanel"));
	VibeMMOScreens::AddCanvasChild(RootCanvas, OptionPanel, FAnchors(0.055f, 0.27f), FVector2D::ZeroVector, FVector2D::ZeroVector, FVector2D(430.0f, 610.0f));
	VibeMMOScreens::AddGlassLayer(WidgetTree, OptionPanel, TEXT("CharacterCreatorOptionGlass"), FVector2D(430.0f, 610.0f), Style);

	UVerticalBox* OptionStack = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), TEXT("CharacterCreatorOptionStack"));
	if (UOverlaySlot* OptionStackSlot = OptionPanel->AddChildToOverlay(OptionStack))
	{
		OptionStackSlot->SetPadding(FMargin(26.0f, 22.0f));
		OptionStackSlot->SetHorizontalAlignment(HAlign_Fill);
		OptionStackSlot->SetVerticalAlignment(VAlign_Fill);
	}

	struct FCreatorSectionSpec
	{
		const TCHAR* Title;
		TArray<FText> Options;
	};

	const TArray<FText> FactionOptions = (CreatorData && !CreatorData->FactionNames.IsEmpty()) ? CreatorData->FactionNames : TArray<FText>{
		FText::FromString(TEXT("Auric Vanguard")),
		FText::FromString(TEXT("Neon Concord")),
		FText::FromString(TEXT("Driftborn Union"))
	};

	const TArray<FText> RaceOptions = (CreatorData && !CreatorData->RaceNames.IsEmpty()) ? CreatorData->RaceNames : TArray<FText>{
		FText::FromString(TEXT("Human")),
		FText::FromString(TEXT("Astral")),
		FText::FromString(TEXT("Synth"))
	};

	const TArray<FText> BodyOptions = (CreatorData && !CreatorData->BodyTypeLabels.IsEmpty()) ? CreatorData->BodyTypeLabels : TArray<FText>{
		FText::FromString(TEXT("Body Type A")),
		FText::FromString(TEXT("Body Type B")),
		FText::FromString(TEXT("Body Type C"))
	};

	const FCreatorSectionSpec Sections[] = {
		{ TEXT("FACTION"), FactionOptions },
		{ TEXT("ANCESTRY"), RaceOptions },
		{ TEXT("BODY"), BodyOptions },
		{ TEXT("CLASS"), { FText::FromString(TEXT("Void Ranger")), FText::FromString(TEXT("Tech Mage")), FText::FromString(TEXT("Pulse Knight")) } }
	};

	for (int32 SectionIndex = 0; SectionIndex < UE_ARRAY_COUNT(Sections); ++SectionIndex)
	{
		UTextBlock* SectionTitle = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), *FString::Printf(TEXT("CharacterCreatorSectionTitle_%d"), SectionIndex));
		SectionTitle->SetText(FText::FromString(Sections[SectionIndex].Title));
		ApplyTextRole(SectionTitle, EVibeMMOUIFontRole::CharacterCreatorSectionHeader);
		if (UVerticalBoxSlot* SectionTitleSlot = OptionStack->AddChildToVerticalBox(SectionTitle))
		{
			SectionTitleSlot->SetPadding(FMargin(0.0f, SectionIndex == 0 ? 0.0f : 26.0f, 0.0f, 8.0f));
			SectionTitleSlot->SetHorizontalAlignment(HAlign_Left);
		}

		UHorizontalBox* OptionRow = WidgetTree->ConstructWidget<UHorizontalBox>(UHorizontalBox::StaticClass(), *FString::Printf(TEXT("CharacterCreatorOptionRow_%d"), SectionIndex));
		if (UVerticalBoxSlot* OptionRowSlot = OptionStack->AddChildToVerticalBox(OptionRow))
		{
			OptionRowSlot->SetHorizontalAlignment(HAlign_Fill);
		}

		for (int32 OptionIndex = 0; OptionIndex < Sections[SectionIndex].Options.Num(); ++OptionIndex)
		{
			UOverlay* OptionChip = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), *FString::Printf(TEXT("CharacterCreatorOptionChip_%d_%d"), SectionIndex, OptionIndex));
			VibeMMOScreens::AddGlassLayer(WidgetTree, OptionChip, *FString::Printf(TEXT("CharacterCreatorOptionChipGlass_%d_%d"), SectionIndex, OptionIndex), FVector2D(112.0f, 42.0f), Style);

			UBorder* ChipBorder = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), *FString::Printf(TEXT("CharacterCreatorOptionChipBorder_%d_%d"), SectionIndex, OptionIndex));
			ChipBorder->SetBrushColor(OptionIndex == 0 ? VibeMMOScreens::CyanStroke : FLinearColor(1.0f, 1.0f, 1.0f, 0.14f));
			if (UOverlaySlot* ChipBorderSlot = OptionChip->AddChildToOverlay(ChipBorder))
			{
				ChipBorderSlot->SetHorizontalAlignment(HAlign_Fill);
				ChipBorderSlot->SetVerticalAlignment(VAlign_Fill);
			}

			UTextBlock* OptionText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), *FString::Printf(TEXT("CharacterCreatorOptionText_%d_%d"), SectionIndex, OptionIndex));
			OptionText->SetText(Sections[SectionIndex].Options[OptionIndex]);
			ApplyTextRole(OptionText, EVibeMMOUIFontRole::SettingsBody);
			if (UOverlaySlot* OptionTextSlot = OptionChip->AddChildToOverlay(OptionText))
			{
				OptionTextSlot->SetPadding(FMargin(8.0f, 0.0f));
				OptionTextSlot->SetHorizontalAlignment(HAlign_Center);
				OptionTextSlot->SetVerticalAlignment(VAlign_Center);
			}

			if (UHorizontalBoxSlot* ChipRowSlot = OptionRow->AddChildToHorizontalBox(OptionChip))
			{
				ChipRowSlot->SetPadding(FMargin(0.0f, 0.0f, 10.0f, 0.0f));
				ChipRowSlot->SetHorizontalAlignment(HAlign_Left);
				ChipRowSlot->SetVerticalAlignment(VAlign_Center);
			}
		}
	}

	UOverlay* PreviewPanel = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), TEXT("CharacterCreatorPreviewPanel"));
	VibeMMOScreens::AddCanvasChild(RootCanvas, PreviewPanel, FAnchors(0.57f, 0.52f), FVector2D(0.5f, 0.5f), FVector2D::ZeroVector, FVector2D(440.0f, 650.0f));
	VibeMMOScreens::AddGlassLayer(WidgetTree, PreviewPanel, TEXT("CharacterCreatorPreviewGlass"), FVector2D(440.0f, 650.0f), Style);

	CharacterPreviewImage = WidgetTree->ConstructWidget<UImage>(UImage::StaticClass(), TEXT("CharacterCreatorPreviewImage"));
	CharacterPreviewImage->SetVisibility(ESlateVisibility::Collapsed);
	if (UOverlaySlot* PreviewImageSlot = PreviewPanel->AddChildToOverlay(CharacterPreviewImage))
	{
		PreviewImageSlot->SetPadding(FMargin(18.0f));
		PreviewImageSlot->SetHorizontalAlignment(HAlign_Fill);
		PreviewImageSlot->SetVerticalAlignment(VAlign_Fill);
	}

	UTextBlock* PreviewFallback = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("CharacterCreatorPreviewFallbackText"));
	PreviewFallback->SetText(FText::FromString(TEXT("LIVE\\nCUSTOMIZATION\\nPREVIEW")));
	PreviewFallback->SetJustification(ETextJustify::Center);
	ApplyTextRole(PreviewFallback, EVibeMMOUIFontRole::TalentTreeTitle);
	if (UOverlaySlot* PreviewFallbackSlot = PreviewPanel->AddChildToOverlay(PreviewFallback))
	{
		PreviewFallbackSlot->SetHorizontalAlignment(HAlign_Center);
		PreviewFallbackSlot->SetVerticalAlignment(VAlign_Center);
	}

	UOverlay* CreateButton = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), TEXT("CharacterCreatorCreateButton"));
	VibeMMOScreens::AddCanvasChild(RootCanvas, CreateButton, FAnchors(0.57f, 0.885f), FVector2D(0.5f, 0.5f), FVector2D::ZeroVector, FVector2D(330.0f, 64.0f));
	VibeMMOScreens::AddGlassLayer(WidgetTree, CreateButton, TEXT("CharacterCreatorCreateGlass"), FVector2D(330.0f, 64.0f), Style);

	UTextBlock* CreateText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("CharacterCreatorCreateText"));
	CreateText->SetText(FText::FromString(TEXT("CREATE")));
	ApplyTextRole(CreateText, EVibeMMOUIFontRole::ImportantLabel);
	if (UOverlaySlot* CreateTextSlot = CreateButton->AddChildToOverlay(CreateText))
	{
		CreateTextSlot->SetHorizontalAlignment(HAlign_Center);
		CreateTextSlot->SetVerticalAlignment(VAlign_Center);
	}

	bDefaultCharacterCreatorTreeBuilt = true;
}

void UVibeMMOCharacterCreatorWidget::ApplyCharacterCreatorTextRoles()
{
	ApplyTextRole(SectionHeaderText, EVibeMMOUIFontRole::MainMenuTitle);
	ApplyTextRole(DescriptionText, EVibeMMOUIFontRole::CompanionBody);
}

void UVibeMMOCharacterCreatorWidget::ApplyVibeStyle_Implementation()
{
	Super::ApplyVibeStyle_Implementation();
	ApplyCharacterCreatorTextRoles();
}

void UVibeMMOInventorySlotButton::InitializeInventorySlot(
	UVibeMMOInventoryWidget* InOwner, const int32 InVisualSlotIndex)
{
	InventoryOwner = InOwner;
	VisualSlotIndex = InVisualSlotIndex;
	OnClicked.RemoveDynamic(this, &UVibeMMOInventorySlotButton::HandleSlotClicked);
	OnClicked.AddDynamic(this, &UVibeMMOInventorySlotButton::HandleSlotClicked);
}

void UVibeMMOInventorySlotButton::SetStableItemIndex(const int32 InStableItemIndex)
{
	StableItemIndex = InStableItemIndex;
}

void UVibeMMOInventorySlotButton::HandleSlotClicked()
{
	if (InventoryOwner.IsValid() && StableItemIndex != INDEX_NONE)
	{
		InventoryOwner->SelectInventoryItem(StableItemIndex);
	}
}

UVibeMMOInventoryWidget::UVibeMMOInventoryWidget()
	: bBuildDefaultInventoryInCpp(true)
{
	InventoryItems.SetNum(InventoryCapacity);
}

void UVibeMMOInventoryWidget::NativePreConstruct()
{
	if (bBuildDefaultInventoryInCpp)
	{
		BuildDefaultInventoryTree();
	}

	Super::NativePreConstruct();
}

void UVibeMMOInventoryWidget::SetInventoryItemResource(const int32 ItemIndex, UObject* IconResource)
{
	if (!InventoryItems.IsValidIndex(ItemIndex))
	{
		return;
	}

	FVibeMMOInventoryItemPresentation Presentation = InventoryItems[ItemIndex];
	if (Presentation.bIsPopulated)
	{
		Presentation.IconResource = IconResource;
		InventoryItems[ItemIndex] = MoveTemp(Presentation);
		RefreshInventorySlots();
		return;
	}

	if (!IconResource)
	{
		return;
	}

	Presentation.bIsPopulated = true;
	Presentation.Category = EVibeMMOInventoryCategory::Weapons;
	Presentation.IconResource = IconResource;
	if (Presentation.DisplayName.IsEmpty())
	{
		Presentation.DisplayName = FText::FromString(
			FString::Printf(TEXT("CARRIED ITEM %02d"), ItemIndex + 1));
	}
	if (Presentation.Rarity.IsEmpty())
	{
		Presentation.Rarity = FText::FromString(
			ItemIndex == 0 ? TEXT("EPIC") : ItemIndex == 1 ? TEXT("LEGENDARY") : TEXT("WEAPON"));
	}
	if (Presentation.Description.IsEmpty())
	{
		Presentation.Description = FText::FromString(TEXT("A carried combat item from the active loadout."));
	}
	if (Presentation.RarityColor.Equals(FLinearColor::White))
	{
		Presentation.RarityColor = ItemIndex == 0 ? VibeMMOScreens::PurpleStroke
			: ItemIndex == 1 ? VibeMMOScreens::GoldStroke
			: VibeMMOScreens::CyanStroke;
	}
	SetInventoryItemPresentation(ItemIndex, Presentation);
}

void UVibeMMOInventoryWidget::RebuildDefaultInventoryLayout()
{
	if (WidgetTree && bDefaultInventoryTreeBuilt && WidgetTree->RootWidget
		&& WidgetTree->RootWidget->GetFName() == FName(TEXT("DefaultVibeInventoryRoot")))
	{
		WidgetTree->RootWidget = nullptr;
		bDefaultInventoryTreeBuilt = false;
	}
	BuildDefaultInventoryTree();
	RefreshInventorySlots();
}

void UVibeMMOInventoryWidget::SetInventoryItemPresentation(
	const int32 StableItemIndex, const FVibeMMOInventoryItemPresentation& Presentation)
{
	if (!InventoryItems.IsValidIndex(StableItemIndex))
	{
		return;
	}

	if (!Presentation.bIsPopulated)
	{
		ClearInventoryItemPresentation(StableItemIndex);
		return;
	}

	FVibeMMOInventoryItemPresentation Sanitized = Presentation;
	Sanitized.bIsPopulated = true;
	if (Sanitized.DisplayName.IsEmpty())
	{
		Sanitized.DisplayName = FText::FromString(
			FString::Printf(TEXT("ITEM %02d"), StableItemIndex + 1));
	}
	if (Sanitized.Rarity.IsEmpty())
	{
		Sanitized.Rarity = FText::FromString(TEXT("COMMON"));
	}
	if (Sanitized.Description.IsEmpty())
	{
		Sanitized.Description = FText::FromString(TEXT("No description is available for this item."));
	}
	InventoryItems[StableItemIndex] = MoveTemp(Sanitized);
	if (SelectedStableItemIndex == StableItemIndex
		&& !IsPresentationVisible(InventoryItems[StableItemIndex]))
	{
		SelectedStableItemIndex = INDEX_NONE;
		OnInventoryItemSelected.Broadcast(INDEX_NONE);
	}
	RefreshInventorySlots();
}

void UVibeMMOInventoryWidget::ClearInventoryItemPresentation(const int32 StableItemIndex)
{
	if (!InventoryItems.IsValidIndex(StableItemIndex))
	{
		return;
	}

	InventoryItems[StableItemIndex] = FVibeMMOInventoryItemPresentation();
	if (SelectedStableItemIndex == StableItemIndex)
	{
		SelectedStableItemIndex = INDEX_NONE;
		OnInventoryItemSelected.Broadcast(INDEX_NONE);
	}
	RefreshInventorySlots();
}

bool UVibeMMOInventoryWidget::GetInventoryItemPresentation(
	const int32 StableItemIndex, FVibeMMOInventoryItemPresentation& OutPresentation) const
{
	if (!InventoryItems.IsValidIndex(StableItemIndex))
	{
		return false;
	}

	OutPresentation = InventoryItems[StableItemIndex];
	return OutPresentation.bIsPopulated;
}

void UVibeMMOInventoryWidget::SetInventoryCategory(const EVibeMMOInventoryCategory Category)
{
	ActiveCategory = Category;
	if (InventoryItems.IsValidIndex(SelectedStableItemIndex)
		&& !IsPresentationVisible(InventoryItems[SelectedStableItemIndex]))
	{
		SelectedStableItemIndex = INDEX_NONE;
		OnInventoryItemSelected.Broadcast(INDEX_NONE);
	}
	RefreshInventorySlots();
}

bool UVibeMMOInventoryWidget::SelectInventoryItem(const int32 StableItemIndex)
{
	if (!InventoryItems.IsValidIndex(StableItemIndex)
		|| !InventoryItems[StableItemIndex].bIsPopulated
		|| !IsPresentationVisible(InventoryItems[StableItemIndex]))
	{
		return false;
	}

	SelectedStableItemIndex = StableItemIndex;
	RefreshInventorySlots();
	OnInventoryItemSelected.Broadcast(StableItemIndex);
	return true;
}

void UVibeMMOInventoryWidget::BuildDefaultInventoryTree()
{
	if (!WidgetTree || bDefaultInventoryTreeBuilt)
	{
		return;
	}

	if (WidgetTree->RootWidget && WidgetTree->RootWidget->GetFName() != FName(TEXT("DefaultVibeInventoryRoot")))
	{
		return;
	}

	InventoryItemImages.Reset();
	InventoryPlaceholderTexts.Reset();
	InventorySlotButtons.Reset();
	InventorySlotBorders.Reset();
	InventoryCategoryButtons.Reset();
	InventoryCategoryLabels.Reset();
	if (InventoryItems.Num() != InventoryCapacity)
	{
		InventoryItems.SetNum(InventoryCapacity);
	}
	const UVibeMMOUIStyleDataAsset* Style = GetResolvedStyleDataAsset();

	UCanvasPanel* RootCanvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("DefaultVibeInventoryRoot"));
	WidgetTree->RootWidget = RootCanvas;

	UOverlay* Panel = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), TEXT("InventoryPanel"));
	VibeMMOScreens::AddCanvasChild(RootCanvas, Panel, FAnchors(0.5f, 0.5f), FVector2D(0.5f, 0.5f), FVector2D(0.0f, 0.0f), FVector2D(980.0f, 640.0f));
	VibeMMOScreens::AddGlassLayer(WidgetTree, Panel, TEXT("InventoryPanelGlass"), FVector2D(980.0f, 640.0f), Style);

	UBorder* PanelBorder = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("InventoryPanelBorder"));
	PanelBorder->SetBrushColor(Style ? Style->GlassPanelBorderColor : VibeMMOScreens::CyanStroke);
	if (UOverlaySlot* BorderSlot = Panel->AddChildToOverlay(PanelBorder))
	{
		BorderSlot->SetHorizontalAlignment(HAlign_Fill);
		BorderSlot->SetVerticalAlignment(VAlign_Fill);
	}

	UCanvasPanel* ContentCanvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("InventoryContentCanvas"));
	if (UOverlaySlot* ContentSlot = Panel->AddChildToOverlay(ContentCanvas))
	{
		ContentSlot->SetPadding(FMargin(32.0f, 26.0f));
		ContentSlot->SetHorizontalAlignment(HAlign_Fill);
		ContentSlot->SetVerticalAlignment(VAlign_Fill);
	}

	TitleText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("InventoryTitleText"));
	TitleText->SetText(FText::FromString(TEXT("INVENTORY")));
	TitleText->SetJustification(ETextJustify::Left);
	ApplyTextRole(TitleText, EVibeMMOUIFontRole::TalentTreeTitle);
	VibeMMOScreens::AddCanvasChild(ContentCanvas, TitleText, FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D(0.0f, 0.0f), FVector2D(380.0f, 48.0f));

	UHorizontalBox* Tabs = WidgetTree->ConstructWidget<UHorizontalBox>(UHorizontalBox::StaticClass(), TEXT("InventoryTabs"));
	VibeMMOScreens::AddCanvasChild(ContentCanvas, Tabs, FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D(0.0f, 56.0f), FVector2D(540.0f, 40.0f));

	const TArray<FText> TabLabels = {
		FText::FromString(TEXT("ALL")),
		FText::FromString(TEXT("WEAPONS")),
		FText::FromString(TEXT("RESOURCES")),
		FText::FromString(TEXT("CONSUMABLES"))
	};

	for (int32 Index = 0; Index < TabLabels.Num(); ++Index)
	{
		UButton* TabButton = WidgetTree->ConstructWidget<UButton>(
			UButton::StaticClass(), *FString::Printf(TEXT("InventoryCategoryButton_%d"), Index));
		VibeMMOScreens::MakeButtonChromeTransparent(TabButton);
		TabButton->SetToolTipText(FText::Format(
			FText::FromString(TEXT("Show {0} inventory items")), TabLabels[Index]));
		switch (Index)
		{
		case 0:
			TabButton->OnClicked.AddDynamic(this, &UVibeMMOInventoryWidget::HandleAllCategoryClicked);
			break;
		case 1:
			TabButton->OnClicked.AddDynamic(this, &UVibeMMOInventoryWidget::HandleWeaponsCategoryClicked);
			break;
		case 2:
			TabButton->OnClicked.AddDynamic(this, &UVibeMMOInventoryWidget::HandleResourcesCategoryClicked);
			break;
		default:
			TabButton->OnClicked.AddDynamic(this, &UVibeMMOInventoryWidget::HandleConsumablesCategoryClicked);
			break;
		}

		UTextBlock* TabText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), *FString::Printf(TEXT("InventoryTabText_%d"), Index));
		TabText->SetText(TabLabels[Index]);
		ApplyTextRole(TabText, Index == 0 ? EVibeMMOUIFontRole::ImportantLabel : EVibeMMOUIFontRole::SettingsBody);
		if (UButtonSlot* ButtonContentSlot = Cast<UButtonSlot>(TabButton->AddChild(TabText)))
		{
			ButtonContentSlot->SetPadding(FMargin(0.0f));
			ButtonContentSlot->SetHorizontalAlignment(HAlign_Center);
			ButtonContentSlot->SetVerticalAlignment(VAlign_Center);
		}
		if (UHorizontalBoxSlot* TabSlot = Tabs->AddChildToHorizontalBox(TabButton))
		{
			TabSlot->SetPadding(FMargin(0.0f, 0.0f, 26.0f, 0.0f));
			TabSlot->SetHorizontalAlignment(HAlign_Left);
			TabSlot->SetVerticalAlignment(VAlign_Center);
		}
		InventoryCategoryButtons.Add(TabButton);
		InventoryCategoryLabels.Add(TabText);
	}

	UCanvasPanel* GridCanvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("InventoryGridCanvas"));
	VibeMMOScreens::AddCanvasChild(ContentCanvas, GridCanvas, FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D(0.0f, 116.0f), FVector2D(560.0f, 400.0f));

	const int32 Columns = 8;
	const int32 Rows = 5;
	const float SlotSize = 58.0f;
	const float Gap = 12.0f;
	for (int32 Index = 0; Index < Columns * Rows; ++Index)
	{
		const int32 Column = Index % Columns;
		const int32 Row = Index / Columns;
		UVibeMMOInventorySlotButton* SlotButton = WidgetTree->ConstructWidget<UVibeMMOInventorySlotButton>(
			UVibeMMOInventorySlotButton::StaticClass(), *FString::Printf(TEXT("InventorySlotButton_%d"), Index));
		SlotButton->InitializeInventorySlot(this, Index);
		VibeMMOScreens::MakeButtonChromeTransparent(SlotButton);

		UOverlay* InventorySlot = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), *FString::Printf(TEXT("InventorySlot_%d"), Index));
		VibeMMOScreens::AddGlassLayer(WidgetTree, InventorySlot, *FString::Printf(TEXT("InventorySlotGlass_%d"), Index), FVector2D(SlotSize, SlotSize), Style);

		UBorder* SlotBorder = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), *FString::Printf(TEXT("InventorySlotBorder_%d"), Index));
		SlotBorder->SetBrushColor(Index == 0 ? VibeMMOScreens::PurpleStroke
			: Index == 1 ? VibeMMOScreens::GoldStroke
			: FLinearColor(1.0f, 1.0f, 1.0f, 0.13f));
		if (UOverlaySlot* SlotBorderOverlay = InventorySlot->AddChildToOverlay(SlotBorder))
		{
			SlotBorderOverlay->SetHorizontalAlignment(HAlign_Fill);
			SlotBorderOverlay->SetVerticalAlignment(VAlign_Fill);
		}
		InventorySlotBorders.Add(SlotBorder);

		UImage* IconImage = WidgetTree->ConstructWidget<UImage>(UImage::StaticClass(), *FString::Printf(TEXT("InventorySlotIcon_%d"), Index));
		IconImage->SetVisibility(ESlateVisibility::Collapsed);
		if (UOverlaySlot* IconSlot = InventorySlot->AddChildToOverlay(IconImage))
		{
			IconSlot->SetPadding(FMargin(6.0f));
			IconSlot->SetHorizontalAlignment(HAlign_Fill);
			IconSlot->SetVerticalAlignment(VAlign_Fill);
		}
		InventoryItemImages.Add(IconImage);

		UTextBlock* Placeholder = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), *FString::Printf(TEXT("InventorySlotPlaceholder_%d"), Index));
		Placeholder->SetText(FText::FromString(TEXT("EMPTY")));
		ApplyTextRole(Placeholder, EVibeMMOUIFontRole::SettingsBody);
		if (UOverlaySlot* PlaceholderSlot = InventorySlot->AddChildToOverlay(Placeholder))
		{
			PlaceholderSlot->SetHorizontalAlignment(HAlign_Center);
			PlaceholderSlot->SetVerticalAlignment(VAlign_Center);
		}
		InventoryPlaceholderTexts.Add(Placeholder);

		if (UButtonSlot* SlotContent = Cast<UButtonSlot>(SlotButton->AddChild(InventorySlot)))
		{
			SlotContent->SetPadding(FMargin(0.0f));
			SlotContent->SetHorizontalAlignment(HAlign_Fill);
			SlotContent->SetVerticalAlignment(VAlign_Fill);
		}
		InventorySlotButtons.Add(SlotButton);
		VibeMMOScreens::AddCanvasChild(GridCanvas, SlotButton, FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D(Column * (SlotSize + Gap), Row * (SlotSize + Gap)), FVector2D(SlotSize, SlotSize));
	}

	UOverlay* DetailPanel = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), TEXT("InventoryDetailPanel"));
	VibeMMOScreens::AddCanvasChild(ContentCanvas, DetailPanel, FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D(610.0f, 110.0f), FVector2D(300.0f, 404.0f));
	VibeMMOScreens::AddGlassLayer(WidgetTree, DetailPanel, TEXT("InventoryDetailGlass"), FVector2D(300.0f, 404.0f), Style);

	UVerticalBox* DetailStack = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), TEXT("InventoryDetailStack"));
	if (UOverlaySlot* DetailStackSlot = DetailPanel->AddChildToOverlay(DetailStack))
	{
		DetailStackSlot->SetPadding(FMargin(24.0f));
		DetailStackSlot->SetHorizontalAlignment(HAlign_Fill);
		DetailStackSlot->SetVerticalAlignment(VAlign_Fill);
	}

	RarityLabelText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("InventoryRarityLabelText"));
	RarityLabelText->SetText(FText::FromString(TEXT("CARRIED LOADOUT")));
	ApplyTextRole(RarityLabelText, EVibeMMOUIFontRole::InventoryRarityLabel);
	if (UVerticalBoxSlot* RaritySlot = DetailStack->AddChildToVerticalBox(RarityLabelText))
	{
		RaritySlot->SetHorizontalAlignment(HAlign_Left);
	}

	ItemNameText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("InventoryItemNameText"));
	ItemNameText->SetText(FText::FromString(TEXT("EQUIPPED WEAPONS")));
	ApplyTextRole(ItemNameText, EVibeMMOUIFontRole::ImportantLabel);
	if (UVerticalBoxSlot* ItemNameSlot = DetailStack->AddChildToVerticalBox(ItemNameText))
	{
		ItemNameSlot->SetPadding(FMargin(0.0f, 16.0f, 0.0f, 0.0f));
		ItemNameSlot->SetHorizontalAlignment(HAlign_Left);
	}

	ItemDescriptionText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("InventoryItemDescriptionText"));
	ItemDescriptionText->SetText(FText::FromString(TEXT("Equipped combat items appear in the first slots. Persistent loot storage and crafting will populate this screen when the inventory backend is connected.")));
	ItemDescriptionText->SetAutoWrapText(true);
	ApplyTextRole(ItemDescriptionText, EVibeMMOUIFontRole::TooltipBody);
	if (UVerticalBoxSlot* DescriptionSlot = DetailStack->AddChildToVerticalBox(ItemDescriptionText))
	{
		DescriptionSlot->SetPadding(FMargin(0.0f, 18.0f, 0.0f, 0.0f));
		DescriptionSlot->SetHorizontalAlignment(HAlign_Fill);
	}

	InventoryCountText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("InventoryCurrencyText"));
	InventoryCountText->SetText(FText::FromString(TEXT("CARRIED ITEMS  0 / 40")));
	ApplyTextRole(InventoryCountText, EVibeMMOUIFontRole::ImportantLabel);
	VibeMMOScreens::AddCanvasChild(ContentCanvas, InventoryCountText, FAnchors(0.0f, 1.0f), FVector2D(0.0f, 1.0f), FVector2D(0.0f, 0.0f), FVector2D(360.0f, 42.0f));

	bDefaultInventoryTreeBuilt = true;
	RefreshInventorySlots();
}

bool UVibeMMOInventoryWidget::IsPresentationVisible(
	const FVibeMMOInventoryItemPresentation& Presentation) const
{
	return Presentation.bIsPopulated
		&& (ActiveCategory == EVibeMMOInventoryCategory::All
			|| Presentation.Category == ActiveCategory);
}

void UVibeMMOInventoryWidget::RefreshInventorySlots()
{
	VisibleStableItemIndices.Reset();
	int32 PopulatedCount = 0;
	for (int32 StableIndex = 0; StableIndex < InventoryItems.Num(); ++StableIndex)
	{
		const FVibeMMOInventoryItemPresentation& Presentation = InventoryItems[StableIndex];
		if (Presentation.bIsPopulated)
		{
			++PopulatedCount;
		}
		if (IsPresentationVisible(Presentation))
		{
			VisibleStableItemIndices.Add(StableIndex);
		}
	}

	for (int32 VisualIndex = 0; VisualIndex < InventorySlotButtons.Num(); ++VisualIndex)
	{
		UVibeMMOInventorySlotButton* SlotButton = InventorySlotButtons[VisualIndex];
		if (!SlotButton)
		{
			continue;
		}

		const int32 StableIndex = VisibleStableItemIndices.IsValidIndex(VisualIndex)
			? VisibleStableItemIndices[VisualIndex]
			: INDEX_NONE;
		SlotButton->SetStableItemIndex(StableIndex);
		SlotButton->SetIsEnabled(StableIndex != INDEX_NONE);

		UImage* IconImage = InventoryItemImages.IsValidIndex(VisualIndex)
			? InventoryItemImages[VisualIndex].Get() : nullptr;
		UTextBlock* Placeholder = InventoryPlaceholderTexts.IsValidIndex(VisualIndex)
			? InventoryPlaceholderTexts[VisualIndex].Get() : nullptr;
		UBorder* SlotBorder = InventorySlotBorders.IsValidIndex(VisualIndex)
			? InventorySlotBorders[VisualIndex].Get() : nullptr;

		if (StableIndex == INDEX_NONE)
		{
			VibeMMOScreens::ApplyBrushResource(IconImage, nullptr, FVector2D(50.0f, 50.0f));
			if (Placeholder)
			{
				Placeholder->SetText(FText::FromString(TEXT("EMPTY")));
				Placeholder->SetVisibility(ESlateVisibility::HitTestInvisible);
			}
			if (SlotBorder)
			{
				SlotBorder->SetBrushColor(FLinearColor(1.0f, 1.0f, 1.0f, 0.13f));
			}
			SlotButton->SetToolTipText(FText::FromString(
				TEXT("Empty slot - no item is available in this category.")));
			continue;
		}

		const FVibeMMOInventoryItemPresentation& Presentation = InventoryItems[StableIndex];
		VibeMMOScreens::ApplyBrushResource(
			IconImage, Presentation.IconResource.Get(), FVector2D(50.0f, 50.0f));
		if (Placeholder)
		{
			const bool bHasIcon = Presentation.IconResource != nullptr;
			Placeholder->SetText(bHasIcon
				? FText::GetEmpty()
				: FText::FromString(Presentation.DisplayName.ToString().ToUpper().Left(8)));
			Placeholder->SetVisibility(bHasIcon
				? ESlateVisibility::Collapsed
				: ESlateVisibility::HitTestInvisible);
		}
		if (SlotBorder)
		{
			FLinearColor BorderColor = Presentation.RarityColor;
			BorderColor.A = StableIndex == SelectedStableItemIndex ? 1.0f : 0.48f;
			SlotBorder->SetBrushColor(BorderColor);
		}
		SlotButton->SetToolTipText(Presentation.DisplayName);
	}

	if (InventoryCountText)
	{
		InventoryCountText->SetText(FText::FromString(
			FString::Printf(TEXT("CARRIED ITEMS  %d / %d"), PopulatedCount, InventoryCapacity)));
	}

	RefreshInventoryCategoryTabs();
	RefreshInventoryDetails();
}

void UVibeMMOInventoryWidget::RefreshInventoryDetails()
{
	const bool bHasSelection = InventoryItems.IsValidIndex(SelectedStableItemIndex)
		&& IsPresentationVisible(InventoryItems[SelectedStableItemIndex]);
	if (!bHasSelection)
	{
		if (RarityLabelText)
		{
			RarityLabelText->SetText(FText::FromString(TEXT("SELECT AN ITEM")));
			RarityLabelText->SetColorAndOpacity(FSlateColor(FLinearColor::White));
		}
		if (ItemNameText)
		{
			ItemNameText->SetText(FText::FromString(TEXT("INVENTORY DETAILS")));
		}
		if (ItemDescriptionText)
		{
			ItemDescriptionText->SetText(FText::FromString(
				TEXT("Choose an available item to inspect its rarity and description.")));
		}
		return;
	}

	const FVibeMMOInventoryItemPresentation& Presentation = InventoryItems[SelectedStableItemIndex];
	if (RarityLabelText)
	{
		RarityLabelText->SetText(Presentation.Rarity);
		RarityLabelText->SetColorAndOpacity(FSlateColor(Presentation.RarityColor));
	}
	if (ItemNameText)
	{
		ItemNameText->SetText(Presentation.DisplayName);
	}
	if (ItemDescriptionText)
	{
		ItemDescriptionText->SetText(Presentation.Description);
	}
}

void UVibeMMOInventoryWidget::RefreshInventoryCategoryTabs()
{
	for (int32 Index = 0; Index < InventoryCategoryLabels.Num(); ++Index)
	{
		if (UTextBlock* Label = InventoryCategoryLabels[Index])
		{
			const bool bActive = Index == static_cast<int32>(ActiveCategory);
			ApplyTextRole(Label, bActive
				? EVibeMMOUIFontRole::ImportantLabel
				: EVibeMMOUIFontRole::SettingsBody);
			Label->SetColorAndOpacity(FSlateColor(
				FLinearColor(1.0f, 1.0f, 1.0f, bActive ? 1.0f : 0.58f)));
		}
	}
}

void UVibeMMOInventoryWidget::HandleAllCategoryClicked()
{
	SetInventoryCategory(EVibeMMOInventoryCategory::All);
}

void UVibeMMOInventoryWidget::HandleWeaponsCategoryClicked()
{
	SetInventoryCategory(EVibeMMOInventoryCategory::Weapons);
}

void UVibeMMOInventoryWidget::HandleResourcesCategoryClicked()
{
	SetInventoryCategory(EVibeMMOInventoryCategory::Resources);
}

void UVibeMMOInventoryWidget::HandleConsumablesCategoryClicked()
{
	SetInventoryCategory(EVibeMMOInventoryCategory::Consumables);
}

void UVibeMMOInventoryWidget::ApplyInventoryTextRoles()
{
	ApplyTextRole(TitleText, EVibeMMOUIFontRole::TalentTreeTitle);
	ApplyTextRole(RarityLabelText, EVibeMMOUIFontRole::InventoryRarityLabel);
	ApplyTextRole(ItemNameText, EVibeMMOUIFontRole::ImportantLabel);
	ApplyTextRole(ItemDescriptionText, EVibeMMOUIFontRole::TooltipBody);
}

void UVibeMMOInventoryWidget::ApplyVibeStyle_Implementation()
{
	Super::ApplyVibeStyle_Implementation();
	ApplyInventoryTextRoles();
	RefreshInventoryCategoryTabs();
	RefreshInventoryDetails();
}

UVibeMMOEquipmentWidget::UVibeMMOEquipmentWidget()
	: bBuildDefaultEquipmentInCpp(true)
{
}

void UVibeMMOEquipmentWidget::NativePreConstruct()
{
	if (bBuildDefaultEquipmentInCpp)
	{
		BuildDefaultEquipmentTree();
	}

	Super::NativePreConstruct();
}

void UVibeMMOEquipmentWidget::SetCharacterPreviewResource(UObject* PreviewResource)
{
	VibeMMOScreens::ApplyBrushResource(CharacterPreviewImage, PreviewResource, FVector2D(340.0f, 520.0f));
}

void UVibeMMOEquipmentWidget::SetEquipmentSlotResource(const int32 SlotIndex, UObject* IconResource)
{
	if (!EquipmentSlotImages.IsValidIndex(SlotIndex))
	{
		return;
	}

	VibeMMOScreens::ApplyBrushResource(EquipmentSlotImages[SlotIndex], IconResource, FVector2D(58.0f, 58.0f));
}

void UVibeMMOEquipmentWidget::BuildDefaultEquipmentTree()
{
	if (!WidgetTree || bDefaultEquipmentTreeBuilt)
	{
		return;
	}

	if (WidgetTree->RootWidget && WidgetTree->RootWidget->GetFName() != FName(TEXT("DefaultVibeEquipmentRoot")))
	{
		return;
	}

	EquipmentSlotImages.Reset();
	CharacterPreviewImage = nullptr;
	const UVibeMMOUIStyleDataAsset* Style = GetResolvedStyleDataAsset();

	UCanvasPanel* RootCanvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("DefaultVibeEquipmentRoot"));
	WidgetTree->RootWidget = RootCanvas;

	UOverlay* Panel = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), TEXT("EquipmentPanel"));
	VibeMMOScreens::AddCanvasChild(RootCanvas, Panel, FAnchors(0.5f, 0.5f), FVector2D(0.5f, 0.5f), FVector2D(0.0f, 0.0f), FVector2D(1040.0f, 700.0f));
	VibeMMOScreens::AddGlassLayer(WidgetTree, Panel, TEXT("EquipmentPanelGlass"), FVector2D(1040.0f, 700.0f), Style);

	UBorder* PanelBorder = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("EquipmentPanelBorder"));
	PanelBorder->SetBrushColor(Style ? Style->GlassPanelBorderColor : VibeMMOScreens::CyanStroke);
	if (UOverlaySlot* BorderSlot = Panel->AddChildToOverlay(PanelBorder))
	{
		BorderSlot->SetHorizontalAlignment(HAlign_Fill);
		BorderSlot->SetVerticalAlignment(VAlign_Fill);
	}

	UCanvasPanel* ContentCanvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("EquipmentContentCanvas"));
	if (UOverlaySlot* ContentSlot = Panel->AddChildToOverlay(ContentCanvas))
	{
		ContentSlot->SetPadding(FMargin(32.0f, 26.0f));
		ContentSlot->SetHorizontalAlignment(HAlign_Fill);
		ContentSlot->SetVerticalAlignment(VAlign_Fill);
	}

	TitleText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("EquipmentTitleText"));
	TitleText->SetText(FText::FromString(TEXT("CHARACTER")));
	TitleText->SetJustification(ETextJustify::Left);
	ApplyTextRole(TitleText, EVibeMMOUIFontRole::TalentTreeTitle);
	VibeMMOScreens::AddCanvasChild(ContentCanvas, TitleText, FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D(0.0f, 0.0f), FVector2D(420.0f, 48.0f));

	UTextBlock* ClassText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("EquipmentClassText"));
	ClassText->SetText(FText::FromString(TEXT("LEVEL 31  /  VOID RANGER")));
	ApplyTextRole(ClassText, EVibeMMOUIFontRole::ImportantLabel);
	VibeMMOScreens::AddCanvasChild(ContentCanvas, ClassText, FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D(0.0f, 54.0f), FVector2D(420.0f, 36.0f));

	UOverlay* CharacterPanel = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), TEXT("EquipmentCharacterRenderPanel"));
	VibeMMOScreens::AddCanvasChild(ContentCanvas, CharacterPanel, FAnchors(0.5f, 0.0f), FVector2D(0.5f, 0.0f), FVector2D(0.0f, 90.0f), FVector2D(350.0f, 520.0f));
	VibeMMOScreens::AddGlassLayer(WidgetTree, CharacterPanel, TEXT("EquipmentCharacterRenderGlass"), FVector2D(350.0f, 520.0f), Style);

	CharacterPreviewImage = WidgetTree->ConstructWidget<UImage>(UImage::StaticClass(), TEXT("EquipmentCharacterPreviewImage"));
	CharacterPreviewImage->SetVisibility(ESlateVisibility::Collapsed);
	if (UOverlaySlot* PreviewImageSlot = CharacterPanel->AddChildToOverlay(CharacterPreviewImage))
	{
		PreviewImageSlot->SetPadding(FMargin(10.0f));
		PreviewImageSlot->SetHorizontalAlignment(HAlign_Fill);
		PreviewImageSlot->SetVerticalAlignment(VAlign_Fill);
	}

	UTextBlock* CharacterFallbackText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("EquipmentCharacterFallbackText"));
	CharacterFallbackText->SetText(FText::FromString(TEXT("CHARACTER\\nRENDER TARGET")));
	CharacterFallbackText->SetJustification(ETextJustify::Center);
	ApplyTextRole(CharacterFallbackText, EVibeMMOUIFontRole::ImportantLabel);
	if (UOverlaySlot* FallbackSlot = CharacterPanel->AddChildToOverlay(CharacterFallbackText))
	{
		FallbackSlot->SetHorizontalAlignment(HAlign_Center);
		FallbackSlot->SetVerticalAlignment(VAlign_Center);
	}

	struct FEquipmentSlotSpec
	{
		const TCHAR* Label;
		FVector2D Position;
		FLinearColor Accent;
	};

	const FEquipmentSlotSpec SlotSpecs[] = {
		{ TEXT("HEAD"), FVector2D(120.0f, 112.0f), VibeMMOScreens::CyanStroke },
		{ TEXT("SHOULDER"), FVector2D(120.0f, 202.0f), VibeMMOScreens::CyanStroke },
		{ TEXT("CHEST"), FVector2D(120.0f, 292.0f), VibeMMOScreens::GoldStroke },
		{ TEXT("GLOVES"), FVector2D(120.0f, 382.0f), VibeMMOScreens::CyanStroke },
		{ TEXT("LEGS"), FVector2D(120.0f, 472.0f), VibeMMOScreens::PurpleStroke },
		{ TEXT("BOOTS"), FVector2D(120.0f, 562.0f), VibeMMOScreens::CyanStroke },
		{ TEXT("MAIN"), FVector2D(790.0f, 112.0f), VibeMMOScreens::GoldStroke },
		{ TEXT("OFF"), FVector2D(790.0f, 202.0f), VibeMMOScreens::GoldStroke },
		{ TEXT("DEVICE"), FVector2D(790.0f, 292.0f), VibeMMOScreens::PurpleStroke },
		{ TEXT("RING"), FVector2D(790.0f, 382.0f), VibeMMOScreens::PurpleStroke },
		{ TEXT("RELIC"), FVector2D(790.0f, 472.0f), VibeMMOScreens::CyanStroke },
		{ TEXT("CORE"), FVector2D(790.0f, 562.0f), VibeMMOScreens::GoldStroke }
	};

	for (int32 Index = 0; Index < UE_ARRAY_COUNT(SlotSpecs); ++Index)
	{
		UOverlay* EquipmentSlot = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), *FString::Printf(TEXT("EquipmentSlot_%d"), Index));
		VibeMMOScreens::AddGlassLayer(WidgetTree, EquipmentSlot, *FString::Printf(TEXT("EquipmentSlotGlass_%d"), Index), FVector2D(170.0f, 68.0f), Style);

		UBorder* SlotBorder = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), *FString::Printf(TEXT("EquipmentSlotBorder_%d"), Index));
		SlotBorder->SetBrushColor(SlotSpecs[Index].Accent);
		if (UOverlaySlot* SlotBorderOverlay = EquipmentSlot->AddChildToOverlay(SlotBorder))
		{
			SlotBorderOverlay->SetHorizontalAlignment(HAlign_Fill);
			SlotBorderOverlay->SetVerticalAlignment(VAlign_Fill);
		}

		UImage* IconImage = WidgetTree->ConstructWidget<UImage>(UImage::StaticClass(), *FString::Printf(TEXT("EquipmentSlotIcon_%d"), Index));
		IconImage->SetVisibility(ESlateVisibility::Collapsed);
		if (UOverlaySlot* IconSlot = EquipmentSlot->AddChildToOverlay(IconImage))
		{
			IconSlot->SetPadding(FMargin(8.0f, 7.0f, 104.0f, 7.0f));
			IconSlot->SetHorizontalAlignment(HAlign_Fill);
			IconSlot->SetVerticalAlignment(VAlign_Fill);
		}
		EquipmentSlotImages.Add(IconImage);

		UTextBlock* SlotLabel = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), *FString::Printf(TEXT("EquipmentSlotLabel_%d"), Index));
		SlotLabel->SetText(FText::FromString(SlotSpecs[Index].Label));
		ApplyTextRole(SlotLabel, EVibeMMOUIFontRole::SettingsBody);
		if (UOverlaySlot* LabelSlot = EquipmentSlot->AddChildToOverlay(SlotLabel))
		{
			LabelSlot->SetPadding(FMargin(76.0f, 0.0f, 10.0f, 0.0f));
			LabelSlot->SetHorizontalAlignment(HAlign_Left);
			LabelSlot->SetVerticalAlignment(VAlign_Center);
		}

		VibeMMOScreens::AddCanvasChild(ContentCanvas, EquipmentSlot, FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, SlotSpecs[Index].Position, FVector2D(170.0f, 68.0f));
	}

	UOverlay* StatsPanel = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), TEXT("EquipmentStatsPanel"));
	VibeMMOScreens::AddCanvasChild(ContentCanvas, StatsPanel, FAnchors(0.5f, 1.0f), FVector2D(0.5f, 1.0f), FVector2D(0.0f, 0.0f), FVector2D(500.0f, 72.0f));
	VibeMMOScreens::AddGlassLayer(WidgetTree, StatsPanel, TEXT("EquipmentStatsGlass"), FVector2D(500.0f, 72.0f), Style);

	UTextBlock* StatsText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("EquipmentStatsText"));
	StatsText->SetText(FText::FromString(TEXT("POWER 1,248     ARMOR 842     CRIT 18%     HASTE 12%")));
	ApplyTextRole(StatsText, EVibeMMOUIFontRole::ImportantLabel);
	if (UOverlaySlot* StatsTextSlot = StatsPanel->AddChildToOverlay(StatsText))
	{
		StatsTextSlot->SetHorizontalAlignment(HAlign_Center);
		StatsTextSlot->SetVerticalAlignment(VAlign_Center);
	}

	bDefaultEquipmentTreeBuilt = true;
}

void UVibeMMOEquipmentWidget::ApplyEquipmentTextRoles()
{
	ApplyTextRole(TitleText, EVibeMMOUIFontRole::TalentTreeTitle);
}

void UVibeMMOEquipmentWidget::ApplyVibeStyle_Implementation()
{
	Super::ApplyVibeStyle_Implementation();
	ApplyEquipmentTextRoles();
}

void UVibeMMOAbilityBarWidget::ApplyVibeStyle_Implementation()
{
	Super::ApplyVibeStyle_Implementation();
	ApplyTextRole(AbilityKeyQText, EVibeMMOUIFontRole::AbilityKeybind);
	ApplyTextRole(AbilityKeyEText, EVibeMMOUIFontRole::AbilityKeybind);
	ApplyTextRole(AbilityKeyRText, EVibeMMOUIFontRole::AbilityKeybind);
	ApplyTextRole(AbilityKeyFText, EVibeMMOUIFontRole::AbilityKeybind);
	ApplyTextRole(AbilityKeyXText, EVibeMMOUIFontRole::AbilityKeybind);
}

void UVibeMMOTalentTreeWidget::ApplyVibeStyle_Implementation()
{
	Super::ApplyVibeStyle_Implementation();
	ApplyTextRole(TitleText, EVibeMMOUIFontRole::TalentTreeTitle);
	ApplyTextRole(TalentTooltipText, EVibeMMOUIFontRole::TooltipBody);
}

void UVibeMMOCraftingWidget::ApplyVibeStyle_Implementation()
{
	Super::ApplyVibeStyle_Implementation();
	ApplyTextRole(SectionHeaderText, EVibeMMOUIFontRole::ImportantLabel);
}
