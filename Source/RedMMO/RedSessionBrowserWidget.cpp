#include "RedSessionBrowserWidget.h"

#include "Blueprint/WidgetTree.h"
#include "Components/Border.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/HorizontalBox.h"
#include "Components/HorizontalBoxSlot.h"
#include "Components/ScrollBox.h"
#include "Components/Spacer.h"
#include "Components/TextBlock.h"
#include "Components/VerticalBox.h"
#include "Components/VerticalBoxSlot.h"
#include "GameFramework/PlayerController.h"
#include "Input/Events.h"
#include "InputCoreTypes.h"

namespace RedSessionBrowser
{
	const FLinearColor Cyan(0.10f, 0.82f, 1.00f, 1.00f);
	const FLinearColor TextPrimary(0.93f, 0.97f, 1.00f, 1.00f);
	const FLinearColor TextSecondary(0.55f, 0.68f, 0.78f, 1.00f);
	const FLinearColor Panel(0.018f, 0.030f, 0.055f, 0.97f);
	const FLinearColor PanelRaised(0.035f, 0.060f, 0.095f, 0.98f);
	const FLinearColor RowIdle(0.045f, 0.075f, 0.115f, 0.98f);
	const FLinearColor RowSelected(0.035f, 0.36f, 0.49f, 1.00f);
	const FLinearColor ErrorColor(1.00f, 0.24f, 0.20f, 1.00f);

	UTextBlock* MakeText(UWidgetTree* Tree, const TCHAR* Name, const FString& Value,
		int32 Size, const FLinearColor& Color)
	{
		UTextBlock* Text = Tree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), Name);
		Text->SetText(FText::FromString(Value));
		Text->SetColorAndOpacity(FSlateColor(Color));
		Text->SetAutoWrapText(true);
		FSlateFontInfo Font = Text->GetFont();
		Font.Size = Size;
		Text->SetFont(Font);
		return Text;
	}

	UButton* MakeButton(UWidgetTree* Tree, const TCHAR* Name, const FString& Label,
		const FLinearColor& Background = PanelRaised)
	{
		UButton* Button = Tree->ConstructWidget<UButton>(UButton::StaticClass(), Name);
		Button->SetBackgroundColor(Background);
		Button->SetToolTipText(FText::FromString(Label));
		UTextBlock* Text = MakeText(Tree, *FString::Printf(TEXT("%s_Label"), Name), Label,
			15, TextPrimary);
		Text->SetJustification(ETextJustify::Center);
		Button->AddChild(Text);
		return Button;
	}

	bool IsBusy(ERedSessionState State)
	{
		return State == ERedSessionState::Destroying
			|| State == ERedSessionState::Creating
			|| State == ERedSessionState::Searching
			|| State == ERedSessionState::Joining
			|| State == ERedSessionState::Traveling;
	}

	FString StateLabel(ERedSessionState State)
	{
		switch (State)
		{
		case ERedSessionState::Idle: return TEXT("Ready");
		case ERedSessionState::Destroying: return TEXT("Closing the previous Steam session...");
		case ERedSessionState::Creating: return TEXT("Creating a RED PvP server...");
		case ERedSessionState::Searching: return TEXT("Searching Steam for compatible RED servers...");
		case ERedSessionState::Joining: return TEXT("Joining the selected server...");
		case ERedSessionState::Traveling: return TEXT("Connecting...");
		case ERedSessionState::InSession: return TEXT("Connected to a RED multiplayer session");
		case ERedSessionState::Error: return TEXT("Steam multiplayer error");
		default: return TEXT("Ready");
		}
	}
}

void URedSessionResultButton::InitializeResultButton(int32 InSearchIndex)
{
	SearchIndex = InSearchIndex;
	OnClicked.RemoveDynamic(this, &URedSessionResultButton::HandleInternalClick);
	OnClicked.AddDynamic(this, &URedSessionResultButton::HandleInternalClick);
}

void URedSessionResultButton::HandleInternalClick()
{
	OnResultClicked.Broadcast(SearchIndex);
}

TSharedRef<SWidget> URedSessionBrowserWidget::RebuildWidget()
{
	// CreateWidget has initialized WidgetTree by this point. Construct the native tree before
	// UUserWidget asks its root for the Slate widget; re-entering Initialize here is unsafe.
	SetIsFocusable(true);
	BuildWidgetTree();
	return Super::RebuildWidget();
}

void URedSessionBrowserWidget::NativeConstruct()
{
	Super::NativeConstruct();
	BuildWidgetTree();
	BindGameInstanceDelegates();
	RebuildResults();
	RefreshStatePresentation();
}

void URedSessionBrowserWidget::NativeDestruct()
{
	UnbindGameInstanceDelegates();
	if (bBrowserOpen)
	{
		ApplyInputMode(false);
		bBrowserOpen = false;
	}
	Super::NativeDestruct();
}

FReply URedSessionBrowserWidget::NativeOnKeyDown(const FGeometry& InGeometry,
	const FKeyEvent& InKeyEvent)
{
	bool bCloseBrowser = InKeyEvent.GetKey() == EKeys::F8
		|| InKeyEvent.GetKey() == EKeys::Escape;
#if WITH_EDITOR
	bCloseBrowser = bCloseBrowser || InKeyEvent.GetKey() == EKeys::F6;
#endif
	if (bCloseBrowser)
	{
		SetBrowserOpen(false);
		return FReply::Handled();
	}
	return Super::NativeOnKeyDown(InGeometry, InKeyEvent);
}

void URedSessionBrowserWidget::SetBrowserOpen(bool bOpen)
{
	if (bBrowserOpen == bOpen && GetVisibility() == (bOpen ? ESlateVisibility::Visible : ESlateVisibility::Collapsed))
	{
		return;
	}

	bBrowserOpen = bOpen;
	SetVisibility(bOpen ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
	ApplyInputMode(bOpen);

	if (bOpen)
	{
		BindGameInstanceDelegates();
		RebuildResults();
		RefreshStatePresentation();
		SetKeyboardFocus();

		if (URedGameInstance* GameInstance = GetRedGameInstance())
		{
			if (GameInstance->SessionResults.IsEmpty()
				&& !RedSessionBrowser::IsBusy(GameInstance->SessionState)
				&& GameInstance->SessionState != ERedSessionState::InSession)
			{
				GameInstance->FindGames();
			}
		}
	}
}

void URedSessionBrowserWidget::ToggleBrowser()
{
	SetBrowserOpen(!bBrowserOpen);
}

void URedSessionBrowserWidget::BuildWidgetTree()
{
	if (!WidgetTree || WidgetTree->RootWidget)
	{
		return;
	}

	using namespace RedSessionBrowser;
	UCanvasPanel* Root = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(),
		TEXT("SessionBrowserRoot"));
	WidgetTree->RootWidget = Root;

	UBorder* ScreenDimmer = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(),
		TEXT("ScreenDimmer"));
	ScreenDimmer->SetBrushColor(FLinearColor(0.0f, 0.005f, 0.015f, 0.72f));
	if (UCanvasPanelSlot* DimmerSlot = Root->AddChildToCanvas(ScreenDimmer))
	{
		DimmerSlot->SetAnchors(FAnchors(0.0f, 0.0f, 1.0f, 1.0f));
		DimmerSlot->SetOffsets(FMargin(0.0f));
	}

	UBorder* Window = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(),
		TEXT("SessionBrowserWindow"));
	Window->SetBrushColor(Panel);
	Window->SetPadding(FMargin(30.0f, 24.0f));
	if (UCanvasPanelSlot* WindowSlot = Root->AddChildToCanvas(Window))
	{
		WindowSlot->SetAnchors(FAnchors(0.5f));
		WindowSlot->SetAlignment(FVector2D(0.5f));
		WindowSlot->SetSize(FVector2D(980.0f, 680.0f));
	}

	UVerticalBox* Main = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(),
		TEXT("SessionBrowserContent"));
	Window->AddChild(Main);

	UHorizontalBox* Header = WidgetTree->ConstructWidget<UHorizontalBox>(UHorizontalBox::StaticClass(),
		TEXT("SessionBrowserHeader"));
	if (UVerticalBoxSlot* HeaderSlot = Main->AddChildToVerticalBox(Header))
	{
		HeaderSlot->SetPadding(FMargin(0.0f, 0.0f, 0.0f, 14.0f));
	}

	UVerticalBox* HeaderCopy = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(),
		TEXT("SessionBrowserHeaderCopy"));
	if (UHorizontalBoxSlot* CopySlot = Header->AddChildToHorizontalBox(HeaderCopy))
	{
		CopySlot->SetSize(FSlateChildSize(ESlateSizeRule::Fill));
		CopySlot->SetVerticalAlignment(VAlign_Center);
	}
	HeaderCopy->AddChildToVerticalBox(MakeText(WidgetTree, TEXT("SessionBrowserTitle"),
		TEXT("MULTIPLAYER LOBBY"), 30, TextPrimary));
#if WITH_EDITOR
	const FString BrowserSubtitle = TEXT("Create a PvP game or join a friend's game  /  F6 in PIE, F8 packaged");
#else
	const FString BrowserSubtitle = TEXT("Create a PvP game or join a friend's game  /  Steam must be running");
#endif
	HeaderCopy->AddChildToVerticalBox(MakeText(WidgetTree, TEXT("SessionBrowserSubtitle"),
		BrowserSubtitle, 14, TextSecondary));

	UButton* CloseButton = MakeButton(WidgetTree, TEXT("SessionBrowserClose"), TEXT("CLOSE"));
	CloseButton->OnClicked.AddDynamic(this, &URedSessionBrowserWidget::HandleCloseClicked);
	if (UHorizontalBoxSlot* CloseSlot = Header->AddChildToHorizontalBox(CloseButton))
	{
		CloseSlot->SetPadding(FMargin(14.0f, 6.0f, 0.0f, 6.0f));
		CloseSlot->SetHorizontalAlignment(HAlign_Fill);
		CloseSlot->SetVerticalAlignment(VAlign_Fill);
	}

	UBorder* StatusBorder = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(),
		TEXT("SessionBrowserStatusBorder"));
	StatusBorder->SetBrushColor(PanelRaised);
	StatusBorder->SetPadding(FMargin(14.0f, 10.0f));
	if (UVerticalBoxSlot* StatusSlot = Main->AddChildToVerticalBox(StatusBorder))
	{
		StatusSlot->SetPadding(FMargin(0.0f, 0.0f, 0.0f, 14.0f));
	}
	StatusText = MakeText(WidgetTree, TEXT("SessionBrowserStatus"), TEXT("Ready"), 15, Cyan);
	StatusBorder->AddChild(StatusText);

	UHorizontalBox* ResultsHeader = WidgetTree->ConstructWidget<UHorizontalBox>(
		UHorizontalBox::StaticClass(), TEXT("SessionBrowserResultsHeader"));
	if (UVerticalBoxSlot* ResultsHeaderSlot = Main->AddChildToVerticalBox(ResultsHeader))
	{
		ResultsHeaderSlot->SetPadding(FMargin(2.0f, 0.0f, 2.0f, 8.0f));
	}
	UTextBlock* ResultsLabel = MakeText(WidgetTree, TEXT("SessionBrowserResultsLabel"),
		TEXT("AVAILABLE SERVERS"), 13, TextSecondary);
	if (UHorizontalBoxSlot* LabelSlot = ResultsHeader->AddChildToHorizontalBox(ResultsLabel))
	{
		LabelSlot->SetSize(FSlateChildSize(ESlateSizeRule::Fill));
	}
	ResultCountText = MakeText(WidgetTree, TEXT("SessionBrowserResultCount"), TEXT("0 FOUND"),
		13, TextSecondary);
	ResultsHeader->AddChildToHorizontalBox(ResultCountText);

	UBorder* ResultsBorder = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(),
		TEXT("SessionBrowserResultsBorder"));
	ResultsBorder->SetBrushColor(FLinearColor(0.008f, 0.015f, 0.028f, 0.92f));
	ResultsBorder->SetPadding(FMargin(10.0f));
	if (UVerticalBoxSlot* ResultsSlot = Main->AddChildToVerticalBox(ResultsBorder))
	{
		ResultsSlot->SetSize(FSlateChildSize(ESlateSizeRule::Fill));
		ResultsSlot->SetPadding(FMargin(0.0f, 0.0f, 0.0f, 18.0f));
	}

	UScrollBox* Scroll = WidgetTree->ConstructWidget<UScrollBox>(UScrollBox::StaticClass(),
		TEXT("SessionBrowserScroll"));
	Scroll->SetScrollBarVisibility(ESlateVisibility::Visible);
	ResultsBorder->AddChild(Scroll);
	ResultsList = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(),
		TEXT("SessionBrowserResultsList"));
	Scroll->AddChild(ResultsList);

	UHorizontalBox* Actions = WidgetTree->ConstructWidget<UHorizontalBox>(UHorizontalBox::StaticClass(),
		TEXT("SessionBrowserActions"));
	Main->AddChildToVerticalBox(Actions);

	HostButton = MakeButton(WidgetTree, TEXT("SessionBrowserHost"), TEXT("CREATE GAME"),
		FLinearColor(0.03f, 0.34f, 0.46f, 1.0f));
	RefreshButton = MakeButton(WidgetTree, TEXT("SessionBrowserRefresh"), TEXT("FIND GAMES"));
	JoinButton = MakeButton(WidgetTree, TEXT("SessionBrowserJoin"), TEXT("JOIN SELECTED"),
		FLinearColor(0.03f, 0.46f, 0.31f, 1.0f));
	ReconnectButton = MakeButton(WidgetTree, TEXT("SessionBrowserReconnect"), TEXT("RECONNECT"));
	InviteButton = MakeButton(WidgetTree, TEXT("SessionBrowserInvite"), TEXT("INVITE FRIENDS"),
		FLinearColor(0.20f, 0.25f, 0.58f, 1.0f));
	LeaveButton = MakeButton(WidgetTree, TEXT("SessionBrowserLeave"), TEXT("LEAVE GAME"),
		FLinearColor(0.48f, 0.055f, 0.075f, 1.0f));
	InviteButton->SetToolTipText(FText::FromString(
		TEXT("Host an active Steam session, then open Steam's friend invite dialog")));
	HostButton->OnClicked.AddDynamic(this, &URedSessionBrowserWidget::HandleHostClicked);
	RefreshButton->OnClicked.AddDynamic(this, &URedSessionBrowserWidget::HandleRefreshClicked);
	JoinButton->OnClicked.AddDynamic(this, &URedSessionBrowserWidget::HandleJoinClicked);
	ReconnectButton->OnClicked.AddDynamic(this, &URedSessionBrowserWidget::HandleReconnectClicked);
	InviteButton->OnClicked.AddDynamic(this, &URedSessionBrowserWidget::HandleInviteClicked);
	LeaveButton->OnClicked.AddDynamic(this, &URedSessionBrowserWidget::HandleLeaveClicked);

	const TArray<UButton*> ActionButtons = {
		HostButton, RefreshButton, JoinButton, ReconnectButton, InviteButton, LeaveButton
	};
	for (int32 Index = 0; Index < ActionButtons.Num(); ++Index)
	{
		if (UHorizontalBoxSlot* ActionSlot = Actions->AddChildToHorizontalBox(ActionButtons[Index]))
		{
			ActionSlot->SetSize(FSlateChildSize(ESlateSizeRule::Fill));
			ActionSlot->SetPadding(FMargin(Index > 0 ? 5.0f : 0.0f, 0.0f,
				Index + 1 < ActionButtons.Num() ? 5.0f : 0.0f, 0.0f));
			ActionSlot->SetVerticalAlignment(VAlign_Fill);
		}
	}
}

void URedSessionBrowserWidget::BindGameInstanceDelegates()
{
	if (bDelegatesBound)
	{
		return;
	}
	if (URedGameInstance* GameInstance = GetRedGameInstance())
	{
		GameInstance->OnSessionStateChanged.AddDynamic(this,
			&URedSessionBrowserWidget::HandleSessionStateChanged);
		GameInstance->OnSessionSearchFinished.AddDynamic(this,
			&URedSessionBrowserWidget::HandleSessionSearchFinished);
		GameInstance->OnSessionResultsChanged.AddDynamic(this,
			&URedSessionBrowserWidget::HandleSessionResultsChanged);
		GameInstance->OnSessionTravelReady.AddDynamic(this,
			&URedSessionBrowserWidget::HandleSessionTravelReady);
		GameInstance->OnSessionStatus.AddDynamic(this,
			&URedSessionBrowserWidget::HandleSessionStatus);
		GameInstance->OnSessionError.AddDynamic(this,
			&URedSessionBrowserWidget::HandleSessionError);
		bDelegatesBound = true;
	}
}

void URedSessionBrowserWidget::UnbindGameInstanceDelegates()
{
	if (!bDelegatesBound)
	{
		return;
	}
	if (URedGameInstance* GameInstance = GetRedGameInstance())
	{
		GameInstance->OnSessionStateChanged.RemoveDynamic(this,
			&URedSessionBrowserWidget::HandleSessionStateChanged);
		GameInstance->OnSessionSearchFinished.RemoveDynamic(this,
			&URedSessionBrowserWidget::HandleSessionSearchFinished);
		GameInstance->OnSessionResultsChanged.RemoveDynamic(this,
			&URedSessionBrowserWidget::HandleSessionResultsChanged);
		GameInstance->OnSessionTravelReady.RemoveDynamic(this,
			&URedSessionBrowserWidget::HandleSessionTravelReady);
		GameInstance->OnSessionStatus.RemoveDynamic(this,
			&URedSessionBrowserWidget::HandleSessionStatus);
		GameInstance->OnSessionError.RemoveDynamic(this,
			&URedSessionBrowserWidget::HandleSessionError);
	}
	bDelegatesBound = false;
}

void URedSessionBrowserWidget::RebuildResults()
{
	if (!ResultsList || !ResultCountText)
	{
		return;
	}

	using namespace RedSessionBrowser;
	ResultsList->ClearChildren();
	ResultButtons.Reset();

	URedGameInstance* GameInstance = GetRedGameInstance();
	const int32 ResultCount = GameInstance ? GameInstance->SessionResults.Num() : 0;
	ResultCountText->SetText(FText::FromString(FString::Printf(TEXT("%d FOUND"), ResultCount)));

	int32 FirstJoinableIndex = INDEX_NONE;
	bool bSelectionStillValid = false;
	if (GameInstance)
	{
		for (const FRedSessionResultSummary& Result : GameInstance->SessionResults)
		{
			if (Result.bJoinable && FirstJoinableIndex == INDEX_NONE)
			{
				FirstJoinableIndex = Result.SearchIndex;
			}
			bSelectionStillValid |= Result.SearchIndex == SelectedSearchIndex && Result.bJoinable;

			URedSessionResultButton* Row = WidgetTree->ConstructWidget<URedSessionResultButton>(
				URedSessionResultButton::StaticClass(),
				*FString::Printf(TEXT("SessionResult_%d"), Result.SearchIndex));
			Row->InitializeResultButton(Result.SearchIndex);
			Row->OnResultClicked.AddDynamic(this, &URedSessionBrowserWidget::HandleResultSelected);
			Row->SetToolTipText(FText::FromString(TEXT("Select this RED-compatible Steam server")));

			UHorizontalBox* RowContent = WidgetTree->ConstructWidget<UHorizontalBox>(
				UHorizontalBox::StaticClass(),
				*FString::Printf(TEXT("SessionResultContent_%d"), Result.SearchIndex));
			UVerticalBox* ServerCopy = WidgetTree->ConstructWidget<UVerticalBox>(
				UVerticalBox::StaticClass(),
				*FString::Printf(TEXT("SessionResultCopy_%d"), Result.SearchIndex));
			if (UHorizontalBoxSlot* CopySlot = RowContent->AddChildToHorizontalBox(ServerCopy))
			{
				CopySlot->SetSize(FSlateChildSize(ESlateSizeRule::Fill));
				CopySlot->SetPadding(FMargin(14.0f, 9.0f));
			}
			ServerCopy->AddChildToVerticalBox(MakeText(WidgetTree,
				*FString::Printf(TEXT("SessionResultName_%d"), Result.SearchIndex),
				Result.ServerName, 18, TextPrimary));
			const FString Details = FString::Printf(TEXT("%s  /  %s  /  %s"),
				Result.OwnerName.IsEmpty() ? TEXT("Steam host") : *Result.OwnerName,
				Result.MapName.IsEmpty() ? TEXT("Red Planet") : *Result.MapName,
				Result.SessionType.IsEmpty() ? TEXT("PvP") : *Result.SessionType);
			ServerCopy->AddChildToVerticalBox(MakeText(WidgetTree,
				*FString::Printf(TEXT("SessionResultDetails_%d"), Result.SearchIndex),
				Details, 12, TextSecondary));

			const FString Metrics = FString::Printf(TEXT("%d / %d PLAYERS     %d ms%s"),
				Result.CurrentPlayers, Result.MaxPlayers, Result.PingMs,
				Result.bJoinable ? TEXT("") : TEXT("     FULL"));
			UTextBlock* MetricsText = MakeText(WidgetTree,
				*FString::Printf(TEXT("SessionResultMetrics_%d"), Result.SearchIndex),
				Metrics, 14, Result.bJoinable ? Cyan : ErrorColor);
			MetricsText->SetJustification(ETextJustify::Right);
			if (UHorizontalBoxSlot* MetricsSlot = RowContent->AddChildToHorizontalBox(MetricsText))
			{
				MetricsSlot->SetPadding(FMargin(20.0f, 16.0f, 14.0f, 12.0f));
				MetricsSlot->SetVerticalAlignment(VAlign_Center);
			}
			Row->AddChild(RowContent);
			if (UVerticalBoxSlot* RowSlot = ResultsList->AddChildToVerticalBox(Row))
			{
				RowSlot->SetPadding(FMargin(0.0f, 0.0f, 0.0f, 8.0f));
			}
			ResultButtons.Add(Row);
		}
	}

	if (!bSelectionStillValid)
	{
		SelectedSearchIndex = FirstJoinableIndex;
	}

	if (ResultCount == 0)
	{
		UTextBlock* EmptyText = MakeText(WidgetTree, TEXT("SessionBrowserEmpty"),
			TEXT("No compatible RED servers found yet.\nOne player: CREATE GAME.  Other player: FIND GAMES, select it, then JOIN SELECTED."),
			16, TextSecondary);
		EmptyText->SetJustification(ETextJustify::Center);
		if (UVerticalBoxSlot* EmptySlot = ResultsList->AddChildToVerticalBox(EmptyText))
		{
			EmptySlot->SetPadding(FMargin(20.0f, 80.0f));
		}
	}

	RefreshResultSelection();
}

void URedSessionBrowserWidget::RefreshStatePresentation()
{
	URedGameInstance* GameInstance = GetRedGameInstance();
	if (!GameInstance || !StatusText)
	{
		return;
	}

	using namespace RedSessionBrowser;
	const bool bBusy = IsBusy(GameInstance->SessionState);
	FString Status = StateLabel(GameInstance->SessionState);
	FLinearColor StatusColor = Cyan;
	if (!GameInstance->LastSessionError.IsEmpty()
		&& GameInstance->SessionState == ERedSessionState::Error)
	{
		Status = GameInstance->LastSessionError;
		StatusColor = ErrorColor;
	}
	StatusText->SetText(FText::FromString(Status));
	StatusText->SetColorAndOpacity(FSlateColor(StatusColor));

	const bool bInSession = GameInstance->SessionState == ERedSessionState::InSession;
	if (HostButton)
	{
		const bool bEnabled = !bBusy && !bInSession;
		HostButton->SetIsEnabled(bEnabled);
		HostButton->SetToolTipText(FText::FromString(bEnabled
			? TEXT("Create a Steam multiplayer game and become the host.")
			: (bInSession ? TEXT("Leave the current game before creating another one.") : TEXT("Please wait for the current session operation to finish."))));
	}
	if (RefreshButton)
	{
		const bool bEnabled = !bBusy && !bInSession;
		RefreshButton->SetIsEnabled(bEnabled);
		RefreshButton->SetToolTipText(FText::FromString(bEnabled
			? TEXT("Search Steam for compatible RED games.")
			: (bInSession ? TEXT("Leave the current game before searching for another one.") : TEXT("Please wait for the current session operation to finish."))));
	}
	if (ReconnectButton)
	{
		const bool bEnabled = !bBusy && !bInSession && GameInstance->CanReconnect();
		ReconnectButton->SetIsEnabled(bEnabled);
		ReconnectButton->SetToolTipText(FText::FromString(bEnabled
			? TEXT("Reconnect to the most recent compatible game.")
			: (GameInstance->CanReconnect() ? TEXT("Reconnect is unavailable during the current session operation.") : TEXT("There is no previous game available to reconnect to."))));
	}
	if (InviteButton)
	{
		const bool bEnabled = !bBusy && GameInstance->CanInviteSteamFriends();
		InviteButton->SetIsEnabled(bEnabled);
		InviteButton->SetToolTipText(FText::FromString(bEnabled
			? TEXT("Open Steam's friend invite dialog for the active hosted game.")
			: TEXT("Host an active Steam game before inviting friends.")));
	}
	if (LeaveButton)
	{
		const bool bEnabled = !bBusy && bInSession;
		LeaveButton->SetIsEnabled(bEnabled);
		LeaveButton->SetToolTipText(FText::FromString(bEnabled
			? TEXT("Leave the current multiplayer game and return to solo play.")
			: TEXT("You are not currently in a multiplayer game.")));
	}
	RefreshResultSelection();
}

void URedSessionBrowserWidget::RefreshResultSelection()
{
	using namespace RedSessionBrowser;
	bool bSelectedJoinable = false;
	URedGameInstance* GameInstance = GetRedGameInstance();
	for (URedSessionResultButton* Row : ResultButtons)
	{
		if (!Row)
		{
			continue;
		}
		const bool bSelected = Row->SearchIndex == SelectedSearchIndex;
		Row->SetBackgroundColor(bSelected ? RowSelected : RowIdle);
		if (bSelected && GameInstance)
		{
			FRedSessionResultSummary Summary;
			bSelectedJoinable = GameInstance->GetSessionResultSummary(Row->SearchIndex, Summary)
				&& Summary.bJoinable;
		}
	}

	if (JoinButton)
	{
		const bool bBusy = GameInstance && IsBusy(GameInstance->SessionState);
		const bool bEnabled = GameInstance && bSelectedJoinable && !bBusy;
		JoinButton->SetIsEnabled(bEnabled);
		JoinButton->SetToolTipText(FText::FromString(bEnabled
			? TEXT("Join the selected compatible Steam game.")
			: (bBusy ? TEXT("Please wait for the current session operation to finish.") : TEXT("Select a joinable server from the list first."))));
	}
}

void URedSessionBrowserWidget::ApplyInputMode(bool bOpen)
{
	APlayerController* PlayerController = GetOwningPlayer();
	if (!PlayerController)
	{
		return;
	}

	if (bOpen)
	{
		FInputModeGameAndUI InputMode;
		InputMode.SetWidgetToFocus(TakeWidget());
		InputMode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
		InputMode.SetHideCursorDuringCapture(false);
		PlayerController->SetInputMode(InputMode);
		PlayerController->SetShowMouseCursor(true);
	}
	else
	{
		FInputModeGameOnly InputMode;
		PlayerController->SetInputMode(InputMode);
		PlayerController->SetShowMouseCursor(false);
	}
}

URedGameInstance* URedSessionBrowserWidget::GetRedGameInstance() const
{
	return Cast<URedGameInstance>(GetGameInstance());
}

void URedSessionBrowserWidget::HandleHostClicked()
{
	if (URedGameInstance* GameInstance = GetRedGameInstance()) GameInstance->HostGame();
}

void URedSessionBrowserWidget::HandleRefreshClicked()
{
	if (URedGameInstance* GameInstance = GetRedGameInstance()) GameInstance->FindGames();
}

void URedSessionBrowserWidget::HandleJoinClicked()
{
	if (URedGameInstance* GameInstance = GetRedGameInstance())
	{
		if (SelectedSearchIndex == INDEX_NONE)
		{
			for (const FRedSessionResultSummary& Result : GameInstance->SessionResults)
			{
				if (Result.bJoinable)
				{
					SelectedSearchIndex = Result.SearchIndex;
					break;
				}
			}
		}
		if (SelectedSearchIndex != INDEX_NONE)
		{
			GameInstance->JoinIndex(SelectedSearchIndex);
		}
	}
}

void URedSessionBrowserWidget::HandleReconnectClicked()
{
	if (URedGameInstance* GameInstance = GetRedGameInstance()) GameInstance->Reconnect();
}

void URedSessionBrowserWidget::HandleInviteClicked()
{
	if (URedGameInstance* GameInstance = GetRedGameInstance()) GameInstance->InviteSteamFriends();
}

void URedSessionBrowserWidget::HandleLeaveClicked()
{
	if (URedGameInstance* GameInstance = GetRedGameInstance()) GameInstance->LeaveGame();
}

void URedSessionBrowserWidget::HandleCloseClicked()
{
	SetBrowserOpen(false);
}

void URedSessionBrowserWidget::HandleResultSelected(int32 SearchIndex)
{
	SelectedSearchIndex = SearchIndex;
	RefreshResultSelection();
}

void URedSessionBrowserWidget::HandleSessionStateChanged(ERedSessionState NewState)
{
	RefreshStatePresentation();
}

void URedSessionBrowserWidget::HandleSessionSearchFinished(bool bSuccess, int32 ResultCount)
{
	RebuildResults();
	RefreshStatePresentation();
}

void URedSessionBrowserWidget::HandleSessionResultsChanged(int32 ResultCount)
{
	RebuildResults();
	RefreshStatePresentation();
}

void URedSessionBrowserWidget::HandleSessionTravelReady(const FString& ConnectString)
{
	if (StatusText)
	{
		StatusText->SetText(FText::FromString(TEXT("Connection ready. Traveling to the RED server...")));
		StatusText->SetColorAndOpacity(FSlateColor(RedSessionBrowser::Cyan));
	}
}

void URedSessionBrowserWidget::HandleSessionStatus(const FString& StatusMessage)
{
	if (StatusText)
	{
		StatusText->SetText(FText::FromString(StatusMessage));
		StatusText->SetColorAndOpacity(FSlateColor(RedSessionBrowser::Cyan));
	}
}

void URedSessionBrowserWidget::HandleSessionError(const FString& ErrorMessage)
{
	RefreshStatePresentation();
	if (StatusText)
	{
		StatusText->SetText(FText::FromString(ErrorMessage));
		StatusText->SetColorAndOpacity(FSlateColor(RedSessionBrowser::ErrorColor));
	}
}
