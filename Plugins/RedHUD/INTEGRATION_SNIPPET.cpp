// Example: add to your existing PlayerController class.

#include "RedHUDBlueprintLibrary.h"
#include "RedHUDWidget.h"

void AYourPlayerController::BeginPlay()
{
    Super::BeginPlay();

    if (IsLocalController())
    {
        RedHUDWidget = URedHUDBlueprintLibrary::CreateAndAddRedHUD(this, 100);

        if (RedHUDWidget)
        {
            RedHUDWidget->SetInputScheme(ERedHUDInputScheme::Gamepad);

            // ExactArt mode keeps every supplied pixel and baked placeholder value unchanged.
            RedHUDWidget->SetLiveDataMode(false);
        }
    }
}

// Update from your replicated/local presentation data, not directly from arbitrary actors.
void AYourPlayerController::RefreshHUD()
{
    if (!RedHUDWidget)
    {
        return;
    }

    FRedHUDSnapshot Snapshot;
    Snapshot.Player.Health = CurrentHealth;
    Snapshot.Player.MaxHealth = MaxHealth;
    Snapshot.Weapon1.Magazine = PrimaryMagazine;
    Snapshot.Weapon1.Reserve = PrimaryReserve;
    Snapshot.Weapon1.bEquipped = true;
    Snapshot.Weapon2.Magazine = SecondaryMagazine;
    Snapshot.Weapon2.Reserve = SecondaryReserve;
    Snapshot.Enemy.bVisible = LockedTarget != nullptr;
    Snapshot.Enemy.Name = LockedTarget ? LockedTarget->GetDisplayName() : TEXT("");
    Snapshot.Enemy.Level = LockedTarget ? LockedTarget->GetLevel() : 0;
    Snapshot.Enemy.Health = LockedTarget ? LockedTarget->GetHealth() : 0.0f;
    Snapshot.Enemy.MaxHealth = LockedTarget ? LockedTarget->GetMaxHealth() : 1.0f;
    Snapshot.Quest.Title = ActiveQuestTitle;
    Snapshot.Quest.Objective = ActiveQuestObjective;
    Snapshot.Quest.Current = ActiveQuestCurrent;
    Snapshot.Quest.Target = ActiveQuestTarget;
    Snapshot.ConsumableCounts = { Consumable1, Consumable2, Consumable3 };
    Snapshot.Abilities.SetNum(4);

    RedHUDWidget->ApplySnapshot(Snapshot);
}
