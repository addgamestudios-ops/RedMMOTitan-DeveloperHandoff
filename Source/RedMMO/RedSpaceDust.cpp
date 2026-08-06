#include "RedSpaceDust.h"

#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/Actor.h"
#include "Materials/MaterialInterface.h"

URedSpaceDust::URedSpaceDust()
{
	PrimaryComponentTick.bCanEverTick = true;
}

void URedSpaceDust::BeginPlay()
{
	Super::BeginPlay();
	// A component-created default subobject becomes an archetype child of an archetype child.
	// Reparented ship Blueprints cannot safely instance that hierarchy (template mismatch). Create
	// the purely cosmetic HISM on the live actor instead; every client owns its local streak field.
	AActor* Owner = GetOwner();
	if (!Streaks && Owner)
	{
		Streaks = NewObject<UHierarchicalInstancedStaticMeshComponent>(Owner, TEXT("DustStreaks"));
		if (Streaks)
		{
			Owner->AddInstanceComponent(Streaks);
			Streaks->SetupAttachment(this);
			Streaks->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			Streaks->SetCastShadow(false);
			Streaks->SetUsingAbsoluteLocation(true);   // instances live in WORLD space
			Streaks->SetUsingAbsoluteRotation(true);
			if (UStaticMesh* CubeMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")))
			{
				Streaks->SetStaticMesh(CubeMesh);
			}
			if (UMaterialInterface* GlowMat = LoadObject<UMaterialInterface>(nullptr,
				TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial")))
			{
				Streaks->SetMaterial(0, GlowMat);
			}
			Streaks->RegisterComponent();
		}
	}
	if (!Streaks)
	{
		SetComponentTickEnabled(false);
		return;
	}
	Streaks->SetWorldTransform(FTransform::Identity);
	Points.SetNum(StreakCount);
	ReseedAll(GetComponentLocation());
	for (int32 i = 0; i < StreakCount; ++i)
	{
		Streaks->AddInstance(FTransform(FQuat::Identity, Points[i], FVector(0.01f)), true);
	}
	Streaks->SetVisibility(false, true);
}

FVector URedSpaceDust::RandomPointAround(const FVector& Center, const FVector& FlightDir) const
{
	// biased AHEAD of the flight direction so streaks flow toward and past the camera
	const FVector Ahead = Center + FlightDir * FMath::FRandRange(0.2f, 1.0f) * FieldRadius;
	return Ahead + FMath::VRand() * FMath::FRandRange(0.15f, 0.9f) * FieldRadius;
}

void URedSpaceDust::ReseedAll(const FVector& Center)
{
	for (FVector& P : Points)
	{
		P = Center + FMath::VRand() * FMath::FRandRange(0.1f, 1.0f) * FieldRadius;
	}
}

void URedSpaceDust::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	AActor* Owner = GetOwner();
	if (!Owner || !Streaks || Points.Num() == 0)
	{
		return;
	}
	const FVector Vel = Owner->GetVelocity();
	const float Speed = (float)Vel.Size();
	const bool bShow = Speed > MinSpeed;
	if (bShow != bVisibleNow)
	{
		bVisibleNow = bShow;
		Streaks->SetVisibility(bShow, true);
		if (bShow)
		{
			ReseedAll(GetComponentLocation());
		}
	}
	if (!bShow)
	{
		return;
	}
	const FVector Center = GetComponentLocation();
	const FVector Dir = Vel / Speed;
	// streak length grows with speed: 2m at 25 m/s -> ~28m at boost speeds
	const float Len = FMath::Clamp(Speed * 0.0012f, 2.f, 28.f);
	const FQuat Rot = Dir.ToOrientationQuat();
	for (int32 i = 0; i < Points.Num(); ++i)
	{
		// recycle streaks that fell behind
		if (FVector::DotProduct(Points[i] - Center, Dir) < -FieldRadius * 0.4f
			|| FVector::DistSquared(Points[i], Center) > FieldRadius * FieldRadius * 2.25f)
		{
			Points[i] = RandomPointAround(Center, Dir);
		}
		Streaks->UpdateInstanceTransform(i,
			FTransform(Rot, Points[i], FVector(Len, 0.06f, 0.06f)),
			true, i == Points.Num() - 1, false);
	}
}
