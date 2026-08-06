#pragma once

#include "CoreMinimal.h"

class AActor;
class UWorld;

/**
 * Shared stable-ID boundary for immutable celestial-frame snapshots.
 *
 * Registration and lookup are game-thread-only. Runtime producers must explicitly bind an
 * authority actor to one namespaced stable ID and a revision that begins at 1 and advances exactly
 * by 1 for every accepted bind. Consumers
 * receive a value snapshot and must never infer identity from actor name, class, distance, radius,
 * spawn order, or the fact that only one candidate exists.
 */
namespace RedCelestialFrames
{
	struct REDMMO_API FFrameRegistration
	{
		FName StableId = NAME_None;
		TWeakObjectPtr<UWorld> World;
		TWeakObjectPtr<AActor> Authority;
		FVector Center = FVector::ZeroVector;
		double NominalRadiusCm = -1.0;
		uint64 Revision = 0;
	};

	/**
	 * Read-only value copied out for one exact-ID consumer operation. It deliberately contains no
	 * UObject pointers, so a game-thread-produced snapshot can be passed to a future worker task.
	 */
	struct REDMMO_API FFrameSnapshot
	{
		FName StableId = NAME_None;
		FVector Center = FVector::ZeroVector;
		double NominalRadiusCm = -1.0;
		uint64 Revision = 0;
	};

	/**
	 * Adds or advances one explicit server/standalone binding. A conflicting authority poisons the
	 * exact ID deterministically without advancing its accepted revision; a non-sequential revision
	 * cannot create or resurrect a binding.
	 * No runtime producer is wired by this source-only checkpoint.
	 */
	REDMMO_API bool RegisterOrUpdate(const FFrameRegistration& Registration);

	/**
	 * Removes only the binding at ExpectedRevision. Its high-water tombstone remains until a newer
	 * explicit registration or RemoveWorld, so stale teardown/re-registration fails closed.
	 */
	REDMMO_API bool Unregister(
		UWorld* World,
		FName StableId,
		uint64 ExpectedRevision);

	/** Convenience exact-ID lookup used by consumers. */
	REDMMO_API bool ResolveExact(
		UWorld* World,
		FName StableId,
		FFrameSnapshot& OutSnapshot);

	/**
	 * Cleanup hook for the future authority-owned producer. It is rejected for a live world and may
	 * run only while the server/standalone world is being cleaned up or is already cleaned up.
	 */
	REDMMO_API void RemoveWorld(UWorld* World);
}
