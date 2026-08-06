#if WITH_DEV_AUTOMATION_TESTS

#include "Blueprint/WidgetTree.h"
#include "Components/Border.h"
#include "Components/Button.h"
#include "Components/TextBlock.h"
#include "Engine/Texture2D.h"
#include "Misc/AutomationTest.h"
#include "Widgets/VibeMMOScreenWidgets.h"

namespace VibeMMOInventoryInteractionTests
{
	static FVibeMMOInventoryItemPresentation MakeItem(
		const EVibeMMOInventoryCategory Category,
		const TCHAR* Name,
		const TCHAR* Rarity,
		const TCHAR* Description,
		const FLinearColor& RarityColor)
	{
		FVibeMMOInventoryItemPresentation Item;
		Item.bIsPopulated = true;
		Item.Category = Category;
		Item.DisplayName = FText::FromString(Name);
		Item.Rarity = FText::FromString(Rarity);
		Item.Description = FText::FromString(Description);
		Item.RarityColor = RarityColor;
		return Item;
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FVibeMMOInventoryInteractionTest,
	"VibeMMO.UI.Inventory.NativeInteractions",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FVibeMMOInventoryInteractionTest::RunTest(const FString& Parameters)
{
	using namespace VibeMMOInventoryInteractionTests;

	UVibeMMOInventoryWidget* Inventory = NewObject<UVibeMMOInventoryWidget>();
	TestTrue(TEXT("Inventory initializes without PIE"), Inventory->Initialize());
	Inventory->RebuildDefaultInventoryLayout();
	TestNotNull(TEXT("Default inventory builds its item-name field"), Inventory->ItemNameText.Get());
	TestNotNull(TEXT("Default inventory builds its rarity field"), Inventory->RarityLabelText.Get());
	TestNotNull(TEXT("Default inventory builds its description field"), Inventory->ItemDescriptionText.Get());
	if (!Inventory->ItemNameText || !Inventory->RarityLabelText || !Inventory->ItemDescriptionText)
	{
		return false;
	}

	UButton* AllButton = Cast<UButton>(Inventory->WidgetTree->FindWidget(TEXT("InventoryCategoryButton_0")));
	UButton* WeaponsButton = Cast<UButton>(Inventory->WidgetTree->FindWidget(TEXT("InventoryCategoryButton_1")));
	UButton* ResourcesButton = Cast<UButton>(Inventory->WidgetTree->FindWidget(TEXT("InventoryCategoryButton_2")));
	UButton* ConsumablesButton = Cast<UButton>(Inventory->WidgetTree->FindWidget(TEXT("InventoryCategoryButton_3")));
	TestNotNull(TEXT("All category is a real button"), AllButton);
	TestNotNull(TEXT("Weapons category is a real button"), WeaponsButton);
	TestNotNull(TEXT("Resources category is a real button"), ResourcesButton);
	TestNotNull(TEXT("Consumables category is a real button"), ConsumablesButton);
	if (!AllButton || !WeaponsButton || !ResourcesButton || !ConsumablesButton)
	{
		return false;
	}

	TestTrue(TEXT("All category owns a native callback"),
		AllButton->OnClicked.Contains(Inventory, TEXT("HandleAllCategoryClicked")));
	TestTrue(TEXT("Weapons category owns a native callback"),
		WeaponsButton->OnClicked.Contains(Inventory, TEXT("HandleWeaponsCategoryClicked")));
	TestTrue(TEXT("Resources category owns a native callback"),
		ResourcesButton->OnClicked.Contains(Inventory, TEXT("HandleResourcesCategoryClicked")));
	TestTrue(TEXT("Consumables category owns a native callback"),
		ConsumablesButton->OnClicked.Contains(Inventory, TEXT("HandleConsumablesCategoryClicked")));

	Inventory->SetInventoryItemPresentation(5, MakeItem(
		EVibeMMOInventoryCategory::Weapons,
		TEXT("Pulse Rifle"), TEXT("EPIC"), TEXT("Stable energy rifle presentation."),
		FLinearColor(0.70f, 0.30f, 1.0f, 1.0f)));
	Inventory->SetInventoryItemPresentation(11, MakeItem(
		EVibeMMOInventoryCategory::Resources,
		TEXT("Titan Alloy"), TEXT("RARE"), TEXT("Structural crafting resource."),
		FLinearColor(0.20f, 0.65f, 1.0f, 1.0f)));
	Inventory->SetInventoryItemPresentation(23, MakeItem(
		EVibeMMOInventoryCategory::Consumables,
		TEXT("Coolant Cell"), TEXT("UNCOMMON"), TEXT("Purges weapon heat."),
		FLinearColor(0.25f, 0.95f, 0.45f, 1.0f)));

	const TArray<int32> AllItems = Inventory->GetVisibleInventoryItemIndices();
	TestEqual(TEXT("All filter exposes every populated item"), AllItems.Num(), 3);
	if (AllItems.Num() == 3)
	{
		TestEqual(TEXT("All filter preserves the first stable index"), AllItems[0], 5);
		TestEqual(TEXT("All filter preserves the second stable index"), AllItems[1], 11);
		TestEqual(TEXT("All filter preserves the third stable index"), AllItems[2], 23);
	}

	UVibeMMOInventorySlotButton* EmptySlot = Cast<UVibeMMOInventorySlotButton>(
		Inventory->WidgetTree->FindWidget(TEXT("InventorySlotButton_3")));
	TestNotNull(TEXT("Empty visual cell is still represented by a button"), EmptySlot);
	if (EmptySlot)
	{
		TestFalse(TEXT("Empty visual cell is disabled"), EmptySlot->GetIsEnabled());
		TestTrue(TEXT("Empty visual cell explains why it is disabled"),
			!EmptySlot->GetToolTipText().IsEmpty());
	}

	WeaponsButton->OnClicked.Broadcast();
	TestEqual(TEXT("Weapons button changes the active filter"),
		Inventory->GetInventoryCategory(), EVibeMMOInventoryCategory::Weapons);
	const TArray<int32> Weapons = Inventory->GetVisibleInventoryItemIndices();
	TestEqual(TEXT("Weapons filter has one match"), Weapons.Num(), 1);
	if (Weapons.Num() == 1)
	{
		TestEqual(TEXT("Filtered item retains its stable backend index"), Weapons[0], 5);
	}

	UVibeMMOInventorySlotButton* FirstVisibleSlot = Cast<UVibeMMOInventorySlotButton>(
		Inventory->WidgetTree->FindWidget(TEXT("InventorySlotButton_0")));
	TestNotNull(TEXT("Filtered item uses a real slot button"), FirstVisibleSlot);
	if (!FirstVisibleSlot)
	{
		return false;
	}
	TestTrue(TEXT("Slot owns its native forwarding callback"),
		FirstVisibleSlot->OnClicked.Contains(FirstVisibleSlot, TEXT("HandleSlotClicked")));
	TestTrue(TEXT("Populated slot is enabled"), FirstVisibleSlot->GetIsEnabled());
	TestEqual(TEXT("Visual slot forwards the stable item index"),
		FirstVisibleSlot->GetStableItemIndex(), 5);
	UBorder* FirstVisibleBorder = Cast<UBorder>(
		Inventory->WidgetTree->FindWidget(TEXT("InventorySlotBorder_0")));
	TestNotNull(TEXT("Filtered item has a visible rarity/selection border"), FirstVisibleBorder);
	const FLinearColor UnselectedBorderColor = FirstVisibleBorder
		? FirstVisibleBorder->GetBrushColor() : FLinearColor::Transparent;

	FirstVisibleSlot->OnClicked.Broadcast();
	TestEqual(TEXT("Native slot callback selects the stable item"),
		Inventory->GetSelectedInventoryItemIndex(), 5);
	TestEqual(TEXT("Selection updates item name"),
		Inventory->ItemNameText->GetText().ToString(), FString(TEXT("Pulse Rifle")));
	TestEqual(TEXT("Selection updates rarity"),
		Inventory->RarityLabelText->GetText().ToString(), FString(TEXT("EPIC")));
	TestEqual(TEXT("Selection updates description"),
		Inventory->ItemDescriptionText->GetText().ToString(),
		FString(TEXT("Stable energy rifle presentation.")));
	if (FirstVisibleBorder)
	{
		TestFalse(TEXT("Selected slot has distinct visual feedback"),
			FirstVisibleBorder->GetBrushColor().Equals(UnselectedBorderColor));
	}

	FVibeMMOInventoryItemPresentation ReclassifiedWeapon;
	TestTrue(TEXT("Selected weapon presentation can be retrieved"),
		Inventory->GetInventoryItemPresentation(5, ReclassifiedWeapon));
	ReclassifiedWeapon.Category = EVibeMMOInventoryCategory::Resources;
	Inventory->SetInventoryItemPresentation(5, ReclassifiedWeapon);
	TestEqual(TEXT("Reclassifying the selected item outside the active filter clears selection"),
		Inventory->GetSelectedInventoryItemIndex(), INDEX_NONE);

	ResourcesButton->OnClicked.Broadcast();
	TestEqual(TEXT("Changing to resources clears a hidden weapon selection"),
		Inventory->GetSelectedInventoryItemIndex(), INDEX_NONE);
	const TArray<int32> Resources = Inventory->GetVisibleInventoryItemIndices();
	TestEqual(TEXT("Resources filter includes the reclassified rifle and original resource"), Resources.Num(), 2);
	if (Resources.Num() == 2)
	{
		TestEqual(TEXT("Reclassified rifle retains its stable index"), Resources[0], 5);
		TestEqual(TEXT("Original resource retains its stable index"), Resources[1], 11);
	}

	ConsumablesButton->OnClicked.Broadcast();
	const TArray<int32> Consumables = Inventory->GetVisibleInventoryItemIndices();
	TestEqual(TEXT("Consumables filter has one match"), Consumables.Num(), 1);
	if (Consumables.Num() == 1)
	{
		TestEqual(TEXT("Consumable filter retains its stable index"), Consumables[0], 23);
	}

	AllButton->OnClicked.Broadcast();
	TestEqual(TEXT("All button restores the unfiltered category"),
		Inventory->GetInventoryCategory(), EVibeMMOInventoryCategory::All);
	TestFalse(TEXT("An empty stable index cannot be selected"), Inventory->SelectInventoryItem(7));

	FVibeMMOInventoryItemPresentation ResourceBeforeIconRefresh;
	TestTrue(TEXT("Resource presentation exists before a legacy icon refresh"),
		Inventory->GetInventoryItemPresentation(11, ResourceBeforeIconRefresh));
	UTexture2D* ReplacementIcon = NewObject<UTexture2D>();
	Inventory->SetInventoryItemResource(11, ReplacementIcon);
	FVibeMMOInventoryItemPresentation ResourceAfterIconRefresh;
	TestTrue(TEXT("Legacy icon refresh preserves the populated item"),
		Inventory->GetInventoryItemPresentation(11, ResourceAfterIconRefresh));
	TestEqual(TEXT("Legacy icon refresh preserves item category"),
		ResourceAfterIconRefresh.Category, EVibeMMOInventoryCategory::Resources);
	TestTrue(TEXT("Legacy icon refresh changes only the icon resource"),
		ResourceAfterIconRefresh.IconResource == ReplacementIcon);
	Inventory->SetInventoryItemResource(11, nullptr);
	TestTrue(TEXT("Clearing an icon does not erase the inventory record"),
		Inventory->GetInventoryItemPresentation(11, ResourceAfterIconRefresh));
	TestNull(TEXT("Clearing an icon clears only the icon resource"),
		ResourceAfterIconRefresh.IconResource.Get());

	Inventory->RebuildDefaultInventoryLayout();
	UButton* RebuiltAllButton = Cast<UButton>(
		Inventory->WidgetTree->FindWidget(TEXT("InventoryCategoryButton_0")));
	TestNotNull(TEXT("Explicit rebuild restores the native inventory tree"),
		Inventory->WidgetTree->RootWidget.Get());
	TestNotNull(TEXT("Rebuilt inventory still exposes an All filter"), RebuiltAllButton);
	if (RebuiltAllButton)
	{
		TestTrue(TEXT("Rebuilt All filter remains bound to a real handler"),
			RebuiltAllButton->OnClicked.Contains(
				Inventory, FName(TEXT("HandleAllCategoryClicked"))));
	}
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
