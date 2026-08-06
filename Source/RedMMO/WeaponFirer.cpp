#include "WeaponFirer.h"
#include "RedBolt.h"
#include "Kismet/GameplayStatics.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "Camera/CameraComponent.h"
#include "InputCoreTypes.h"
#include "Engine/World.h"
#include "Engine/EngineTypes.h"
#include "Engine/SkeletalMesh.h"
#include "CollisionQueryParams.h"
#include "HAL/IConsoleManager.h"
#include "RedHUD.h"
#include "Components/ChildActorComponent.h"
#include "Components/MeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/ProjectileMovementComponent.h"
#include "Engine/PointLight.h"
#include "Components/PointLightComponent.h"
#include "Components/PrimitiveComponent.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimSequence.h"
#include "Animation/Skeleton.h"
#include "NiagaraFunctionLibrary.h"
#include "NiagaraSystem.h"
#include "Math/UnrealMathUtility.h"
#include "Math/RotationMatrix.h"
#include "UObject/ConstructorHelpers.h"

// Test toggle: `red.AutoFire 1` in the console makes the weapon fire every
// interval without input, so the spawn can be verified without a mouse click.
static TAutoConsoleVariable<int32> CVarRedAutoFire(
	TEXT("red.AutoFire"), 0, TEXT("Auto-fire the WeaponFirer for testing (0=off,1=on)"));

AWeaponFirer::AWeaponFirer()
{
	PrimaryActorTick.bCanEverTick = true;

	// Optional fire animation and muzzle FX from the retired DMD pack stay null.
}

void AWeaponFirer::BeginPlay()
{
	Super::BeginPlay();
	// RedPlayerCharacter now owns visible weapon pose and camera-directed shots.
	// The legacy firer should not rotate the held mesh every tick.
	bEnableGunPitch = false;

	// Ensure game input so left-click registers (the creator flow can leave UIOnly).
	if (APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0))
	{
		PC->SetInputMode(FInputModeGameOnly());
		PC->SetShowMouseCursor(false);
		PC->ClientSetHUD(ARedHUD::StaticClass());

		// Cache the camera + spring arm (and their base values) for ADS.
		ResolveViewComponents(PC->GetPawn());

		// Radial-aware aiming drives body facing in Tick, so disable the engine's
		// controller-desired rotation (it rotates around WORLD up, wrong on a planet).
		if (ACharacter* Ch = Cast<ACharacter>(PC->GetPawn()))
		{
			if (UCharacterMovementComponent* CMC = Ch->GetCharacterMovement())
			{
				CMC->bUseControllerDesiredRotation = false;
				CMC->bOrientRotationToMovement = false;
			}
		}
	}
}

void AWeaponFirer::ResolveWeaponMesh(APawn* Pawn)
{
	CachedWeaponMesh = nullptr;
	CachedMuzzleSocket = NAME_None;
	bWeaponMeshRestCached = false;

	if (!Pawn)
	{
		return;
	}

	// Find the UChildActorComponent named "Weapon" (fall back to the first one).
	UChildActorComponent* WeaponChild = nullptr;
	{
		TArray<UChildActorComponent*> ChildComps;
		Pawn->GetComponents<UChildActorComponent>(ChildComps);
		for (UChildActorComponent* ChildComp : ChildComps)
		{
			if (ChildComp && ChildComp->GetName() == TEXT("Weapon"))
			{
				WeaponChild = ChildComp;
				break;
			}
		}
		if (!WeaponChild && ChildComps.Num() > 0)
		{
			WeaponChild = ChildComps[0];
		}
	}
	if (!WeaponChild)
	{
		return;
	}

	AActor* Gun = WeaponChild->GetChildActor();
	if (!Gun)
	{
		return;
	}

	// The weapon is modular/random, so gather ALL mesh parts and search them.
	TArray<UMeshComponent*> GunMeshes;
	Gun->GetComponents<UMeshComponent>(GunMeshes);
	if (GunMeshes.Num() == 0)
	{
		return;
	}

	// A socket counts as a muzzle if its name contains any of these (case-insensitive).
	auto IsMuzzleSocket = [](const FName& SocketName) -> bool
	{
		const FString S = SocketName.ToString().ToLower();
		return S.Contains(TEXT("muzzle")) || S.Contains(TEXT("fire"))
			|| S.Contains(TEXT("barrel")) || S.Contains(TEXT("shot"))
			|| S.Contains(TEXT("proj"));
	};

	UMeshComponent* BestMesh = nullptr;
	FName BestSocket = NAME_None;

	// 1) Explicit override wins, if it exists on any mesh.
	if (MuzzleSocketName != NAME_None)
	{
		for (UMeshComponent* M : GunMeshes)
		{
			if (M && M->DoesSocketExist(MuzzleSocketName))
			{
				BestMesh = M;
				BestSocket = MuzzleSocketName;
				break;
			}
		}
	}

	// 2) Otherwise scan every mesh's sockets for a muzzle-ish name.
	if (!BestMesh)
	{
		for (UMeshComponent* M : GunMeshes)
		{
			if (!M)
			{
				continue;
			}
			for (const FName& SocketName : M->GetAllSocketNames())
			{
				if (IsMuzzleSocket(SocketName))
				{
					BestMesh = M;
					BestSocket = SocketName;
					break;
				}
			}
			if (BestMesh)
			{
				break;
			}
		}
	}

	// 3) No muzzle socket anywhere: use the first mesh + forward fallback.
	if (!BestMesh)
	{
		BestMesh = GunMeshes[0];
	}

	CachedWeaponMesh = BestMesh;
	CachedMuzzleSocket = BestSocket;

	// Cache the gun mesh's rest transform for recoil recovery + gun-pitch aim.
	WeaponMeshRestRelLoc = BestMesh->GetRelativeLocation();
	GunBaseRelRot = BestMesh->GetRelativeRotation();
	bWeaponMeshRestCached = true;
}

void AWeaponFirer::ResolveViewComponents(APawn* Pawn)
{
	CachedCamera = nullptr;
	CachedSpringArm = nullptr;

	if (!Pawn)
	{
		return;
	}

	if (UCameraComponent* Cam = Pawn->FindComponentByClass<UCameraComponent>())
	{
		CachedCamera = Cam;
		BaseFOV = Cam->FieldOfView;
	}
	if (USpringArmComponent* Arm = Pawn->FindComponentByClass<USpringArmComponent>())
	{
		CachedSpringArm = Arm;
		BaseArm = Arm->TargetArmLength;
	}
}

void AWeaponFirer::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0);
	if (!PC)
	{
		return;
	}

	APawn* Pawn = PC->GetPawn();

	// If something (e.g. the character-creator flow) left the controller in
	// UI-only mode, the left-click won't reach IsInputKeyDown. Re-assert game
	// input whenever a cursor is showing so firing always works.
	if (PC->bShowMouseCursor)
	{
		PC->SetInputMode(FInputModeGameOnly());
		PC->SetShowMouseCursor(false);
	}

	const bool bADSInput = PC->IsInputKeyDown(EKeys::RightMouseButton);

	// --- ADS: interp FOV + spring-arm length toward their targets ---
	{
		if (!CachedCamera.IsValid() || !CachedSpringArm.IsValid())
		{
			ResolveViewComponents(Pawn);
		}

		if (UCameraComponent* Cam = CachedCamera.Get())
		{
			const float TargetFOV = bADSInput ? (BaseFOV * ADSFovScale) : BaseFOV;
			const float NewFOV = FMath::FInterpTo(Cam->FieldOfView, TargetFOV, DeltaSeconds, ADSInterpSpeed);
			Cam->SetFieldOfView(NewFOV);
		}
		if (USpringArmComponent* Arm = CachedSpringArm.Get())
		{
			const float TargetArm = bADSInput ? (BaseArm * ADSArmScale) : BaseArm;
			Arm->TargetArmLength = FMath::FInterpTo(Arm->TargetArmLength, TargetArm, DeltaSeconds, ADSInterpSpeed);
		}
	}

	// --- Recoil recovery: ease the weapon mesh back toward its rest location ---
	if (bWeaponMeshRestCached)
	{
		if (UMeshComponent* RecoilMesh = CachedWeaponMesh.Get())
		{
			const FVector CurRel = RecoilMesh->GetRelativeLocation();
			const FVector RestedRel = FMath::VInterpTo(CurRel, WeaponMeshRestRelLoc, DeltaSeconds, RecoilRecoverSpeed);
			RecoilMesh->SetRelativeLocation(RestedRel);
		}
	}

	// --- Aim: face the body toward the look direction (radial-gravity aware) and
	// tilt the gun up/down with the look elevation. Body 'up' is the surface normal
	// (kept aligned by RadialGravityComponent), so we work in that local frame. ---
	if (Pawn)
	{
		FVector AimCamLoc;
		FRotator AimCamRot;
		PC->GetPlayerViewPoint(AimCamLoc, AimCamRot);
		const FVector LookDir = AimCamRot.Vector();
		const FVector Up = Pawn->GetActorUpVector();

		const float TangentSpeed = FVector::VectorPlaneProject(Pawn->GetVelocity(), Up).Size();
		const bool bShouldBodyAim = bEnableBodyAim && (bADSInput || TangentSpeed > 80.0f);
		if (bShouldBodyAim)
		{
			FVector DesiredFwd = LookDir - FVector::DotProduct(LookDir, Up) * Up;
			if (!DesiredFwd.IsNearlyZero())
			{
				DesiredFwd.Normalize();
				const FRotator DesiredRot = FRotationMatrix::MakeFromZX(Up, DesiredFwd).Rotator();
				const FRotator NewRot =
					FMath::RInterpTo(Pawn->GetActorRotation(), DesiredRot, DeltaSeconds, BodyAimSpeed);
				Pawn->SetActorRotation(NewRot);
			}
		}

		if (bEnableGunPitch)
		{
			if (!CachedWeaponMesh.IsValid())
			{
				ResolveWeaponMesh(Pawn);
			}
			if (UMeshComponent* GunMesh = CachedWeaponMesh.Get())
			{
				// Aim the whole gun along the look direction so it visibly tracks the
				// reticle (pitch + yaw), independent of the gun's local axes.
				// GunAimOffsetRot corrects the barrel axis live if needed.
				const FQuat AimQ = LookDir.Rotation().Quaternion() * GunAimOffsetRot.Quaternion();
				GunMesh->SetWorldRotation(AimQ);

				AimLogAccum += DeltaSeconds;
				if (AimLogAccum > 0.5f)
				{
					AimLogAccum = 0.f;
					const float Dot =
						FMath::Clamp(static_cast<float>(FVector::DotProduct(LookDir, Up)), -1.f, 1.f);
					UE_LOG(LogTemp, Warning, TEXT("RedAim: gun=%s elevDeg=%.1f look=%s"),
						*GunMesh->GetName(), FMath::RadiansToDegrees(FMath::Asin(Dot)),
						*LookDir.ToString());
				}
			}
		}
	}

	// --- Cooling ---
	Heat = FMath::Max(0.f, Heat - CoolRate * DeltaSeconds);
	if (bOverheated && Heat <= MaxHeat * 0.25f)
	{
		bOverheated = false;
	}

	if (!ProjectileClass)
	{
		return;
	}

	UWorld* World = GetWorld();
	if (!Pawn || !World)
	{
		return;
	}

	const float Now = World->GetTimeSeconds();
	if (Now - LastFireTime < FireInterval)
	{
		return;
	}
	const bool bFire = PC->IsInputKeyDown(EKeys::LeftMouseButton)
		|| CVarRedAutoFire.GetValueOnGameThread() > 0;
	if (!bFire)
	{
		return;
	}
	if (bOverheated)
	{
		return;
	}
	LastFireTime = Now;
	Heat += HeatPerShot;
	if (Heat >= MaxHeat)
	{
		Heat = MaxHeat;
		bOverheated = true;
	}

	// --- Resolve the muzzle world location from the weapon barrel (first) ---
	if (!CachedWeaponMesh.IsValid())
	{
		ResolveWeaponMesh(Pawn);
	}

	// Camera view drives the aim. Camera forward is the player's actual look
	// direction, so it is correct regardless of radial planet gravity.
	FVector CamLoc;
	FRotator CamRot;
	PC->GetPlayerViewPoint(CamLoc, CamRot);
	const FVector CamFwd = CamRot.Vector();

	FVector MuzzleLoc;
	if (UMeshComponent* WeaponMesh = CachedWeaponMesh.Get())
	{
		if (CachedMuzzleSocket != NAME_None && WeaponMesh->DoesSocketExist(CachedMuzzleSocket))
		{
			MuzzleLoc = WeaponMesh->GetSocketLocation(CachedMuzzleSocket);
		}
		else
		{
			// No socket: use the gun's world position. We deliberately do NOT
			// offset along the gun's forward axis (unreliable on the random
			// modular weapon); the bolt is pushed forward along the AIM below.
			MuzzleLoc = WeaponMesh->GetComponentLocation();
		}
	}
	else
	{
		// No weapon mesh found: fire from in front of the camera.
		MuzzleLoc = CamLoc + CamFwd * MuzzleFallbackForward;
	}

	// Optional crosshair convergence: trace from the camera, ignoring the player
	// AND the gun, and reject too-close hits so we never aim at our own body/weapon.
	FVector AimPoint = CamLoc + CamFwd * 100000.f;
	{
		FCollisionQueryParams QP;
		QP.AddIgnoredActor(this);
		QP.AddIgnoredActor(Pawn);
		if (UMeshComponent* WeaponMesh = CachedWeaponMesh.Get())
		{
			if (AActor* GunActor = WeaponMesh->GetOwner())
			{
				QP.AddIgnoredActor(GunActor);
			}
		}
		FHitResult Hit;
		if (World->LineTraceSingleByChannel(Hit, CamLoc, AimPoint, ECC_Visibility, QP))
		{
			if (Hit.Distance > MinAimDistance)
			{
				AimPoint = Hit.ImpactPoint;
			}
		}
	}

	// Direction muzzle -> aim, GUARANTEED forward: if it would point backward or
	// sideways relative to the camera, fall back to the pure camera forward.
	FVector FireDir = (AimPoint - MuzzleLoc).GetSafeNormal();
	if (FireDir.IsNearlyZero() || FVector::DotProduct(FireDir, CamFwd) < 0.1f)
	{
		FireDir = CamFwd;
	}
	const FRotator FireRot = FireDir.Rotation();

	// Spawn slightly ahead of the muzzle so the bolt never overlaps the body.
	const FVector SpawnLoc = MuzzleLoc + FireDir * MuzzleClearForward;

	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	Params.Owner = this;
	Params.Instigator = Pawn;

	if (AActor* Proj = World->SpawnActor<AActor>(ProjectileClass, SpawnLoc, FireRot, Params))
	{
		if (ARedBolt* RedBolt = Cast<ARedBolt>(Proj))
		{
			RedBolt->ConfigureImpactProfile(2.2f, 3.4f, 120.f, 12.f);
			RedBolt->ConfigureGroundImpact(false, false, false);
		}
		// Never collide with / push the firing pawn, but keep world collision
		// enabled so sand hits can produce dust without carving rifle craters.
		if (UPrimitiveComponent* ProjPrim = Cast<UPrimitiveComponent>(Proj->GetRootComponent()))
		{
			ProjPrim->IgnoreActorWhenMoving(Pawn, true);
		}
		Proj->SetLifeSpan(BoltLifeSpan);
	}
	// Muzzle flash: a big, brief, self-lit blue blob at the barrel. Reuses the bolt
	// visual (a mesh + emissive material), which renders on Metal -- unlike the
	// pack's GPU-simulated Niagara muzzle flashes, which spawn but never draw here.
	if (ProjectileClass)
	{
		FActorSpawnParameters FlashParams;
		FlashParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		FlashParams.Owner = this;
		FlashParams.Instigator = Pawn;

		// Star-burst muzzle flash: fan several scaled blue blobs out from the muzzle
		// (forward + up/down/left/right + diagonals) so flames spread vertically and
		// horizontally for a big flash. Reuses the bolt visual (renders on Metal).
		static const FRotator FlameOffsets[] = {
			FRotator(0.f, 0.f, 0.f),      // forward
			FRotator(78.f, 0.f, 0.f),     // up
			FRotator(-78.f, 0.f, 0.f),    // down
			FRotator(0.f, 65.f, 0.f),     // right
			FRotator(0.f, -65.f, 0.f),    // left
			FRotator(45.f, 45.f, 0.f),    // up-right
			FRotator(-45.f, -45.f, 0.f),  // down-left
		};
		for (const FRotator& Off : FlameOffsets)
		{
			const FRotator FlameRot = (FireRot.Quaternion() * Off.Quaternion()).Rotator();
			AActor* Flash = World->SpawnActor<AActor>(ProjectileClass, SpawnLoc, FlameRot, FlashParams);
			if (!Flash)
			{
				continue;
			}
			Flash->SetActorScale3D(FVector(MuzzleFlashScale,
				MuzzleFlashScale * MuzzleFlashFatness, MuzzleFlashScale * MuzzleFlashFatness));
			if (UProjectileMovementComponent* PM = Flash->FindComponentByClass<UProjectileMovementComponent>())
			{
				PM->StopMovementImmediately();
				PM->Deactivate();
			}
			// No collision + no shadow (a big scaled mesh would throw a weird shadow).
			TArray<UPrimitiveComponent*> FlashPrims;
			Flash->GetComponents<UPrimitiveComponent>(FlashPrims);
			for (UPrimitiveComponent* FlashPrim : FlashPrims)
			{
				FlashPrim->SetCollisionEnabled(ECollisionEnabled::NoCollision);
				FlashPrim->SetCastShadow(false);
			}
			Flash->SetLifeSpan(MuzzleFlashLife);
		}
	}

	// Bright blue light burst at the muzzle (renders via Lumen on Metal).
	if (APointLight* FlashLight = World->SpawnActor<APointLight>(APointLight::StaticClass(), FTransform(SpawnLoc)))
	{
		if (UPointLightComponent* PLC = FlashLight->FindComponentByClass<UPointLightComponent>())
		{
			PLC->SetMobility(EComponentMobility::Movable);
			PLC->SetLightColor(FLinearColor(0.1f, 0.45f, 1.f));
			PLC->SetIntensity(MuzzleLightIntensity);
			PLC->SetAttenuationRadius(1200.f);
			PLC->SetCastShadows(false);
		}
		FlashLight->SetLifeSpan(MuzzleFlashLife);
	}

	// (Kept) GPU Niagara muzzle plume -- harmless; does not render on Metal here.
	if (MuzzleFX)
	{
		UNiagaraFunctionLibrary::SpawnSystemAtLocation(
			World, MuzzleFX, SpawnLoc, FireRot, FVector(MuzzleFXScale));
	}
	if (MuzzleClass)
	{
		World->SpawnActor<AActor>(MuzzleClass, MuzzleLoc, FireRot, Params);
	}

	// --- Fire animation: only if FireAnim's skeleton matches the body mesh's ---
	if (FireAnim)
	{
		if (USkeletalMeshComponent* BodyMesh = Pawn->FindComponentByClass<USkeletalMeshComponent>())
		{
			USkeletalMesh* BodyAsset = BodyMesh->GetSkeletalMeshAsset();
			USkeleton* BodySkeleton = BodyAsset ? BodyAsset->GetSkeleton() : nullptr;
			if (BodySkeleton && BodySkeleton == FireAnim->GetSkeleton())
			{
				if (UAnimInstance* AI = BodyMesh->GetAnimInstance())
				{
					AI->PlaySlotAnimationAsDynamicMontage(FireAnim, AnimSlot, 0.04f, 0.15f);
				}
			}
		}
	}

	// --- Guaranteed procedural recoil (works regardless of skeleton) ---
	// Positive pitch input = view kicks UP (RotationInput.Pitch adds to ViewRotation.Pitch).
	PC->AddPitchInput(RecoilPitch);

	// Weapon-mesh kickback: push back along local -X; Tick interps it home.
	if (UMeshComponent* KickMesh = CachedWeaponMesh.Get())
	{
		if (!bWeaponMeshRestCached)
		{
			WeaponMeshRestRelLoc = KickMesh->GetRelativeLocation();
			bWeaponMeshRestCached = true;
		}
		const FVector KickedRel = KickMesh->GetRelativeLocation() - FVector(RecoilKick, 0.f, 0.f);
		KickMesh->SetRelativeLocation(KickedRel);
	}
}
