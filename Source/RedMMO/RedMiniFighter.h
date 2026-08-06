#pragma once

#include "CoreMinimal.h"
#include "RedShip.h"
#include "RedMiniFighter.generated.h"

class UStaticMeshComponent;
class UPointLightComponent;

/**
 * Compact, carrier-launched StarSparrow assembled from the pack's individual modular meshes.
 * It deliberately inherits ARedShip so B/V boarding, C camera switching, replicated combat,
 * heat, landing assist, and the existing 6DOF controls remain the same as the full fighter.
 */
UCLASS()
class REDMMO_API ARedMiniFighter final : public ARedShip
{
	GENERATED_BODY()

public:
	ARedMiniFighter();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void OnConstruction(const FTransform& Transform) override;
	virtual void PossessedBy(AController* NewController) override;
	virtual void SetupPlayerInputComponent(UInputComponent* InInput) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	virtual bool ConfigureRuntimeCollisionHulls() override;

	/** Authority-only initial/recovery dock used by the runtime world subsystem. */
	bool DockToParent(AActor* ParentActor);

	UFUNCTION(BlueprintPure, Category = "Red|Mini Fighter|Docking")
	bool IsDocked() const { return IsValid(DockParent.Get()); }

	UFUNCTION(BlueprintPure, Category = "Red|Mini Fighter|Docking")
	AActor* GetDockParent() const { return DockParent.Get(); }

protected:
	/** Co-origin StarSparrow layers; no combined example mesh or prebuilt fighter Blueprint is used. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Mini Fighter|Modules")
	TObjectPtr<UStaticMeshComponent> CoreModule;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Mini Fighter|Modules")
	TObjectPtr<UStaticMeshComponent> Wing01Module;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Mini Fighter|Modules")
	TObjectPtr<UStaticMeshComponent> Wing02Module;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Mini Fighter|Modules")
	TObjectPtr<UStaticMeshComponent> Wing03Module;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Mini Fighter|Modules")
	TObjectPtr<UStaticMeshComponent> EngineModule;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Mini Fighter|Modules")
	TObjectPtr<UStaticMeshComponent> ThrusterModule;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Mini Fighter|Modules")
	TObjectPtr<UStaticMeshComponent> WeaponModule;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Mini Fighter|Modules")
	TObjectPtr<UStaticMeshComponent> PlasmaModule;

	/** Local shadowless fill that keeps the compact black hull readable on night-side terrain. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Red|Mini Fighter|Lighting")
	TObjectPtr<UPointLightComponent> ReadabilityFillLight;

	/** Uniform module scale relative to the full-size StarSparrow kit. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Red|Mini Fighter|Modules",
		meta = (ClampMin = "0.25", ClampMax = "1.0"))
	float CompactArtScale = 0.52f;

	/** Maximum distance to the computed rear-bay target for an R docking request. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Red|Mini Fighter|Docking",
		meta = (ClampMin = "100.0"))
	float DockingRange = 3500.f;

	/** Server rejects high-speed docking snaps. Units are cm/s relative to the parent craft. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Red|Mini Fighter|Docking",
		meta = (ClampMin = "0.0"))
	float MaxDockingRelativeSpeed = 3000.f;

	/** How far the docked fighter sits forward of the carrier's aft-most bound. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Red|Mini Fighter|Docking")
	float RearBayInset = 600.f;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Red|Mini Fighter|Docking")
	float RearBayVerticalOffset = 80.f;

	/** Clear space aft of the carrier before collision and flight are restored on launch. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Red|Mini Fighter|Docking",
		meta = (ClampMin = "100.0"))
	float LaunchClearance = 700.f;

private:
	void ApplyCompactModuleLayout();
	void ApplyMiniFighterHardpoints();
	void HandleDockInput();
	void ToggleDockingAuthority();
	bool UndockAuthority();
	AActor* FindBestDockParent() const;
	bool IsValidDockParent(const AActor* Candidate) const;
	FTransform BuildRearBayTransform(const AActor* ParentActor, bool bLaunchPosition) const;
	void ApplyDockedPresentation();
	void ApplyUndockedPresentation();

	UFUNCTION(Server, Reliable)
	void ServerToggleDocking();

	UFUNCTION()
	void OnRep_DockParent();

	/** Replicated in addition to normal actor RepAttachment so late joiners converge reliably. */
	UPROPERTY(VisibleInstanceOnly, ReplicatedUsing = OnRep_DockParent,
		Category = "Red|Mini Fighter|Docking")
	TObjectPtr<AActor> DockParent = nullptr;
};
