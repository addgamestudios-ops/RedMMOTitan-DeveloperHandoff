#pragma once

#include "CoreMinimal.h"
#include "RedHUDTypes.generated.h"

UENUM(BlueprintType)
enum class ERedHUDInputScheme : uint8
{
    KeyboardMouse UMETA(DisplayName="Keyboard / Mouse"),
    Gamepad       UMETA(DisplayName="Gamepad")
};

/**
 * Replacement-HUD navigation modes are explicit so a surface render target is
 * never reused as a fake space radar. Space remains fail-closed until it has an
 * authoritative contact producer and reviewed projection.
 */
UENUM(BlueprintType)
enum class ERedHUDMinimapMode : uint8
{
    Absent  UMETA(DisplayName="Absent"),
    Surface UMETA(DisplayName="Surface"),
    Space   UMETA(DisplayName="Space (Unavailable)")
};

USTRUCT(BlueprintType)
struct FRedHUDPlayerVitals
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    int32 Level = 30;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    float Health = 1779.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    float MaxHealth = 1779.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    float Shield = 100.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    float MaxShield = 100.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    float Energy = 100.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    float MaxEnergy = 100.0f;
};

USTRUCT(BlueprintType)
struct FRedHUDWeaponState
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    int32 Magazine = 32;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    int32 Reserve = 248;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    bool bEquipped = false;

	/** 0..1 weapon heat. RED weapons do not use ammunition. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD", meta=(ClampMin="0.0", ClampMax="1.0"))
	float HeatPercent = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
	bool bOverheated = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD", meta=(ClampMin="0.0"))
	float OverheatCooldownRemaining = 0.0f;
};

USTRUCT(BlueprintType)
struct FRedHUDEnemyState
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    bool bVisible = true;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    FString Name = TEXT("BROODHUNTER");

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    int32 Level = 25;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    float Health = 100.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    float MaxHealth = 100.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    bool bBoss = false;
};

USTRUCT(BlueprintType)
struct FRedHUDQuestState
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    bool bVisible = true;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    FString Title = TEXT("Locate the Ancient Waygate");

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    FString Objective = TEXT("Enter the Sunken Archive");

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    int32 Current = 0;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    int32 Target = 1;
};

USTRUCT(BlueprintType)
struct FRedHUDAbilityState
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    float CooldownRemaining = 0.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    float CooldownDuration = 0.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD", meta=(ClampMin="0.0", ClampMax="1.0"))
    float ChargePercent = 1.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    bool bReady = true;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    bool bSelected = false;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    bool bDisabled = false;
};

USTRUCT(BlueprintType)
struct FRedHUDSnapshot
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    FRedHUDPlayerVitals Player;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    FRedHUDWeaponState Weapon1;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    FRedHUDWeaponState Weapon2;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    FRedHUDEnemyState Enemy;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    FRedHUDQuestState Quest;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    TArray<int32> ConsumableCounts = { 6, 3, 12 };

    // 0 = Ultimate, 1 = Left/Q, 2 = Right/E, 3 = Bottom/R.
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="RED HUD")
    TArray<FRedHUDAbilityState> Abilities;
};
