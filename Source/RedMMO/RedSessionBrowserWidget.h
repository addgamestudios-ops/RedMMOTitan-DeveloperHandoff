#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "Components/Button.h"
#include "RedGameInstance.h"
#include "RedSessionBrowserWidget.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FRedSessionResultClicked, int32, SearchIndex);

/** Button row that forwards its stable browser index with the click event. */
UCLASS()
class REDMMO_API URedSessionResultButton : public UButton
{
	GENERATED_BODY()

public:
	void InitializeResultButton(int32 InSearchIndex);

	UPROPERTY(BlueprintAssignable, Category = "Red|Multiplayer")
	FRedSessionResultClicked OnResultClicked;

	UPROPERTY(BlueprintReadOnly, Category = "Red|Multiplayer")
	int32 SearchIndex = INDEX_NONE;

private:
	UFUNCTION()
	void HandleInternalClick();
};

/**
 * Runtime-built Steam browser. It deliberately has no Blueprint dependency, so F8 is available
 * in editor, development, and packaged Windows builds even when the front-end map is skipped.
 */
UCLASS()
class REDMMO_API URedSessionBrowserWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	void SetBrowserOpen(bool bOpen);
	void ToggleBrowser();
	bool IsBrowserOpen() const { return bBrowserOpen; }

protected:
	virtual TSharedRef<SWidget> RebuildWidget() override;
	virtual void NativeConstruct() override;
	virtual void NativeDestruct() override;
	virtual FReply NativeOnKeyDown(const FGeometry& InGeometry, const FKeyEvent& InKeyEvent) override;

private:
	UPROPERTY(Transient)
	TObjectPtr<class UTextBlock> StatusText;

	UPROPERTY(Transient)
	TObjectPtr<class UTextBlock> ResultCountText;

	UPROPERTY(Transient)
	TObjectPtr<class UVerticalBox> ResultsList;

	UPROPERTY(Transient)
	TObjectPtr<UButton> HostButton;

	UPROPERTY(Transient)
	TObjectPtr<UButton> RefreshButton;

	UPROPERTY(Transient)
	TObjectPtr<UButton> JoinButton;

	UPROPERTY(Transient)
	TObjectPtr<UButton> ReconnectButton;

	UPROPERTY(Transient)
	TObjectPtr<UButton> InviteButton;

	UPROPERTY(Transient)
	TObjectPtr<UButton> LeaveButton;

	UPROPERTY(Transient)
	TArray<TObjectPtr<URedSessionResultButton>> ResultButtons;

	int32 SelectedSearchIndex = INDEX_NONE;
	bool bBrowserOpen = false;
	bool bDelegatesBound = false;

	void BuildWidgetTree();
	void BindGameInstanceDelegates();
	void UnbindGameInstanceDelegates();
	void RebuildResults();
	void RefreshStatePresentation();
	void RefreshResultSelection();
	void ApplyInputMode(bool bOpen);
	URedGameInstance* GetRedGameInstance() const;

	UFUNCTION()
	void HandleHostClicked();

	UFUNCTION()
	void HandleRefreshClicked();

	UFUNCTION()
	void HandleJoinClicked();

	UFUNCTION()
	void HandleReconnectClicked();

	UFUNCTION()
	void HandleInviteClicked();

	UFUNCTION()
	void HandleLeaveClicked();

	UFUNCTION()
	void HandleCloseClicked();

	UFUNCTION()
	void HandleResultSelected(int32 SearchIndex);

	UFUNCTION()
	void HandleSessionStateChanged(ERedSessionState NewState);

	UFUNCTION()
	void HandleSessionSearchFinished(bool bSuccess, int32 ResultCount);

	UFUNCTION()
	void HandleSessionResultsChanged(int32 ResultCount);

	UFUNCTION()
	void HandleSessionTravelReady(const FString& ConnectString);

	UFUNCTION()
	void HandleSessionStatus(const FString& StatusMessage);

	UFUNCTION()
	void HandleSessionError(const FString& ErrorMessage);
};
