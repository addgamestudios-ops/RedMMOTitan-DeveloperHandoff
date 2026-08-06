#include "RedFlightRecorder.h"

#include "Dom/JsonObject.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "RedPlayerCharacter.h"
#include "Serialization/JsonSerializer.h"

namespace
{
constexpr int32 RedRecorderCapacity = 3600;   // ~60s at 60fps

// Console access (Python: unreal.SystemLibrary.execute_console_command(world, "Red.FlightRecorder.Dump"))
FAutoConsoleCommandWithWorld GRedDumpFlightRecorder(
	TEXT("Red.FlightRecorder.Dump"),
	TEXT("Write the gameplay flight-recorder ring buffer to Saved/FlightRecorder/"),
	FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
	{
		if (World)
		{
			if (URedFlightRecorder* Recorder = World->GetSubsystem<URedFlightRecorder>())
			{
				const FString Path = Recorder->DumpToFile();
				UE_LOG(LogTemp, Display, TEXT("FlightRecorder dumped: %s"), *Path);
			}
		}
	}));
}

bool URedFlightRecorder::ShouldCreateSubsystem(UObject* Outer) const
{
	if (!Super::ShouldCreateSubsystem(Outer))
	{
		return false;
	}
	const UWorld* World = Cast<UWorld>(Outer);
	return World && (World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE);
}

void URedFlightRecorder::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	Ring.SetNumZeroed(RedRecorderCapacity);
	Head = 0;
	bWrapped = false;
}

void URedFlightRecorder::Tick(float DeltaTime)
{
	UWorld* World = GetWorld();
	if (!World || Ring.Num() == 0)
	{
		return;
	}
	APawn* Pawn = UGameplayStatics::GetPlayerPawn(World, 0);
	if (!Pawn)
	{
		return;
	}

	FSample& S = Ring[Head];
	S.T = (float)World->GetTimeSeconds();
	S.Dt = DeltaTime;
	S.Loc = FVector3f(Pawn->GetActorLocation());
	S.Vel = FVector3f(Pawn->GetVelocity());
	S.MoveMode = 255;
	S.GroundSpeed = 0.f;
	S.DirDeg = 0.f;
	S.RateScale = 1.f;
	if (const ARedPlayerCharacter* Char = Cast<ARedPlayerCharacter>(Pawn))
	{
		if (const UCharacterMovementComponent* CMC = Char->GetCharacterMovement())
		{
			S.MoveMode = (uint8)CMC->MovementMode.GetValue();
		}
		S.GroundSpeed = Char->AnimGroundSpeed;
		S.DirDeg = Char->AnimDirectionDeg;
		if (const USkeletalMeshComponent* Mesh = Char->GetMesh())
		{
			S.RateScale = Mesh->GlobalAnimRateScale;
		}
	}

	Head = (Head + 1) % Ring.Num();
	if (Head == 0)
	{
		bWrapped = true;
	}
}

FString URedFlightRecorder::DumpToFile()
{
	const int32 Count = bWrapped ? Ring.Num() : Head;
	TArray<TSharedPtr<FJsonValue>> Frames;
	Frames.Reserve(Count);
	const int32 Start = bWrapped ? Head : 0;
	for (int32 i = 0; i < Count; ++i)
	{
		const FSample& S = Ring[(Start + i) % Ring.Num()];
		TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
		J->SetNumberField(TEXT("t"), S.T);
		J->SetNumberField(TEXT("dt"), S.Dt);
		J->SetNumberField(TEXT("x"), S.Loc.X);
		J->SetNumberField(TEXT("y"), S.Loc.Y);
		J->SetNumberField(TEXT("z"), S.Loc.Z);
		J->SetNumberField(TEXT("speed"), FVector3f(S.Vel).Size());
		J->SetNumberField(TEXT("mode"), S.MoveMode);
		J->SetNumberField(TEXT("gspd"), S.GroundSpeed);
		J->SetNumberField(TEXT("dir"), S.DirDeg);
		J->SetNumberField(TEXT("rate"), S.RateScale);
		Frames.Add(MakeShared<FJsonValueObject>(J));
	}
	TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetNumberField(TEXT("frame_count"), Count);
	Root->SetArrayField(TEXT("frames"), Frames);

	FString Out;
	const TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Writer =
		TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Out);
	FJsonSerializer::Serialize(Root, Writer);

	const FString Dir = FPaths::ProjectSavedDir() / TEXT("FlightRecorder");
	const FString File = Dir / FString::Printf(TEXT("FR_%.0f.json"), FPlatformTime::Seconds());
	FFileHelper::SaveStringToFile(Out, *File);
	return File;
}
