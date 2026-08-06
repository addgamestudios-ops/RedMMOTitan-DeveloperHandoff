#include "RedCelestialFrameRegistry.h"

#include "Engine/World.h"
#include "GameFramework/Actor.h"

namespace
{
	constexpr float FrameCenterToleranceCm = 0.01f;

	struct FRevisionState
	{
		TWeakObjectPtr<UWorld> World;
		FName StableId = NAME_None;
		uint64 HighWaterRevision = 0;
		bool bConflict = false;
	};

	struct FAuthorityState
	{
		TWeakObjectPtr<UWorld> World;
		TWeakObjectPtr<AActor> Authority;
		FName StableId = NAME_None;
	};

	bool IsStructurallyValid(const RedCelestialFrames::FFrameRegistration& Registration)
	{
		UWorld* World = Registration.World.Get();
		AActor* Authority = Registration.Authority.Get();
		return IsValid(World) && IsValid(Authority) && Authority->GetWorld() == World
			&& World->GetNetMode() != NM_Client && Authority->HasAuthority()
			&& !Registration.StableId.IsNone()
			&& !Registration.Center.ContainsNaN()
			&& FMath::IsFinite(Registration.NominalRadiusCm)
			&& Registration.NominalRadiusCm > 0.0
			&& Registration.Revision > 0
			&& Registration.Revision < TNumericLimits<uint64>::Max()
			&& Authority->GetActorLocation().Equals(
				Registration.Center, FrameCenterToleranceCm);
	}

	bool IsNextRevision(const uint64 CurrentRevision, const uint64 CandidateRevision)
	{
		return CurrentRevision < TNumericLimits<uint64>::Max()
			&& CandidateRevision == CurrentRevision + 1;
	}

	class FCelestialFrameRegistry
	{
	public:
		bool RegisterOrUpdate(const RedCelestialFrames::FFrameRegistration& Registration)
		{
			if (!IsInGameThread() || !IsStructurallyValid(Registration))
			{
				return false;
			}

			UWorld* World = Registration.World.Get();
			AActor* Authority = Registration.Authority.Get();
			FRevisionState* State = FindRevisionState(World, Registration.StableId);
			FAuthorityState* AuthorityState = AuthorityStates.FindByPredicate(
				[Authority](const FAuthorityState& Existing)
				{
					return Existing.Authority.Get() == Authority;
				});
			if (AuthorityState && (AuthorityState->World.Get() != World
				|| AuthorityState->StableId != Registration.StableId))
			{
				return false;
			}

			for (RedCelestialFrames::FFrameRegistration& Existing : Registrations)
			{
				if (Existing.Authority.Get() != Authority)
				{
					continue;
				}

				// One authority cannot silently change world or durable identity. An update must also
				// advance both its binding revision and the stable ID's retained high-water mark.
				if (Existing.World.Get() != World
					|| Existing.StableId != Registration.StableId
					|| !State
					|| !IsNextRevision(Existing.Revision, Registration.Revision)
					|| !IsNextRevision(State->HighWaterRevision, Registration.Revision))
				{
					return false;
				}

				Existing = Registration;
				State->HighWaterRevision = Registration.Revision;
				if (!AuthorityState)
				{
					AddAuthorityState(World, Authority, Registration.StableId);
				}
				return true;
			}

			const bool bHasExistingStableId = Registrations.ContainsByPredicate(
				[World, &Registration](const RedCelestialFrames::FFrameRegistration& Existing)
				{
					return Existing.World.Get() == World
						&& Existing.StableId == Registration.StableId;
				});
			if (bHasExistingStableId)
			{
				// Record a sticky conflict even when the competing authority used a stale or
				// non-sequential revision. Rejected input never advances the accepted high-water mark,
				// so it cannot saturate or capture this ID.
				if (!State)
				{
					State = &AddRevisionState(
						World, Registration.StableId, 0);
				}
				State->bConflict = true;
				return false;
			}

			if (State)
			{
				if (!IsNextRevision(State->HighWaterRevision, Registration.Revision))
				{
					return false;
				}
				State->HighWaterRevision = Registration.Revision;
				State->bConflict = false;
			}
			else
			{
				if (Registration.Revision != 1)
				{
					return false;
				}
				State = &AddRevisionState(
					World, Registration.StableId, Registration.Revision);
			}

			Registrations.Add(Registration);
			if (!AuthorityState)
			{
				AddAuthorityState(World, Authority, Registration.StableId);
			}
			return true;
		}

		bool Unregister(
			UWorld* World,
			const FName StableId,
			const uint64 ExpectedRevision)
		{
			if (!IsInGameThread() || !IsValid(World) || World->GetNetMode() == NM_Client
				|| StableId.IsNone() || ExpectedRevision == 0)
			{
				return false;
			}

			for (int32 Index = 0; Index < Registrations.Num(); ++Index)
			{
				const RedCelestialFrames::FFrameRegistration& Existing = Registrations[Index];
				if (Existing.World.Get() == World && Existing.StableId == StableId
					&& Existing.Revision == ExpectedRevision)
				{
					Registrations.RemoveAt(Index);
					return true;
				}
			}
			return false;
		}

		bool ResolveExact(
			UWorld* World,
			const FName StableId,
			RedCelestialFrames::FFrameSnapshot& OutSnapshot) const
		{
			OutSnapshot = RedCelestialFrames::FFrameSnapshot();
			if (!IsInGameThread() || !IsValid(World) || World->GetNetMode() == NM_Client
				|| StableId.IsNone())
			{
				return false;
			}

			const FRevisionState* State = FindRevisionState(World, StableId);
			if (!State || State->bConflict)
			{
				return false;
			}

			int32 MatchingRegistrationCount = 0;
			RedCelestialFrames::FFrameSnapshot Candidate;
			for (const RedCelestialFrames::FFrameRegistration& Registration : Registrations)
			{
				if (Registration.StableId != StableId || Registration.World.Get() != World)
				{
					continue;
				}

				++MatchingRegistrationCount;
				if (MatchingRegistrationCount > 1 || !IsStructurallyValid(Registration)
					|| Registration.Revision != State->HighWaterRevision)
				{
					return false;
				}

				Candidate.StableId = Registration.StableId;
				Candidate.Center = Registration.Center;
				Candidate.NominalRadiusCm = Registration.NominalRadiusCm;
				Candidate.Revision = Registration.Revision;
			}

			if (MatchingRegistrationCount != 1)
			{
				return false;
			}

			OutSnapshot = Candidate;
			return true;
		}

		void RemoveWorld(UWorld* World)
		{
			if (!IsInGameThread() || !IsValid(World) || World->GetNetMode() == NM_Client
				|| (!World->IsBeingCleanedUp() && !World->IsCleanedUp()))
			{
				return;
			}
			Registrations.RemoveAll(
				[World](const RedCelestialFrames::FFrameRegistration& Registration)
				{
					return Registration.World.Get() == World;
				});
			RevisionStates.RemoveAll(
				[World](const FRevisionState& State)
				{
					return State.World.Get() == World;
				});
			AuthorityStates.RemoveAll(
				[World](const FAuthorityState& State)
				{
					return State.World.Get() == World;
				});
		}

	private:
		FRevisionState* FindRevisionState(UWorld* World, const FName StableId)
		{
			return RevisionStates.FindByPredicate(
				[World, StableId](const FRevisionState& State)
				{
					return State.World.Get() == World && State.StableId == StableId;
				});
		}

		const FRevisionState* FindRevisionState(UWorld* World, const FName StableId) const
		{
			return RevisionStates.FindByPredicate(
				[World, StableId](const FRevisionState& State)
				{
					return State.World.Get() == World && State.StableId == StableId;
				});
		}

		FRevisionState& AddRevisionState(
			UWorld* World,
			const FName StableId,
			const uint64 HighWaterRevision)
		{
			FRevisionState& State = RevisionStates.AddDefaulted_GetRef();
			State.World = World;
			State.StableId = StableId;
			State.HighWaterRevision = HighWaterRevision;
			return State;
		}

		void AddAuthorityState(UWorld* World, AActor* Authority, const FName StableId)
		{
			FAuthorityState& State = AuthorityStates.AddDefaulted_GetRef();
			State.World = World;
			State.Authority = Authority;
			State.StableId = StableId;
		}

		TArray<RedCelestialFrames::FFrameRegistration> Registrations;
		TArray<FRevisionState> RevisionStates;
		TArray<FAuthorityState> AuthorityStates;
	};

	FCelestialFrameRegistry GCelestialFrameRegistry;
}

bool RedCelestialFrames::RegisterOrUpdate(const FFrameRegistration& Registration)
{
	return GCelestialFrameRegistry.RegisterOrUpdate(Registration);
}

bool RedCelestialFrames::Unregister(
	UWorld* World,
	const FName StableId,
	const uint64 ExpectedRevision)
{
	return GCelestialFrameRegistry.Unregister(World, StableId, ExpectedRevision);
}

bool RedCelestialFrames::ResolveExact(
	UWorld* World,
	const FName StableId,
	FFrameSnapshot& OutSnapshot)
{
	return GCelestialFrameRegistry.ResolveExact(World, StableId, OutSnapshot);
}

void RedCelestialFrames::RemoveWorld(UWorld* World)
{
	GCelestialFrameRegistry.RemoveWorld(World);
}
