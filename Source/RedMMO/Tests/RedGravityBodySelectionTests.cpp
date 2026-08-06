#if WITH_DEV_AUTOMATION_TESTS

#include "../RedGravityBodies.h"

#include "Misc/AutomationTest.h"

namespace RedGravityBodySelectionTests
{
	static RedGravity::FBodyCandidate MakeBody(
		const TCHAR* StableId, const FVector& Center, const float SurfaceRadius,
		const float InfluenceRadius, const int32 Priority)
	{
		RedGravity::FBodyCandidate Body;
		Body.StableId = FName(StableId);
		Body.Center = Center;
		Body.SurfaceRadius = SurfaceRadius;
		Body.SelectionSurfaceRadius = SurfaceRadius;
		Body.InfluenceRadius = InfluenceRadius;
		Body.Priority = Priority;
		return Body;
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FRedGravityBodySelectionTest,
	"RedMMO.Gravity.DeterministicBodySelection",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRedGravityBodySelectionTest::RunTest(const FString& Parameters)
{
	using namespace RedGravityBodySelectionTests;
	using namespace RedGravity;

	const FBodyCandidate Planet = MakeBody(
		TEXT("planet.red.mars"), FVector::ZeroVector, 1000.f, 100000.f, 100);
	const FBodyCandidate MoonA = MakeBody(
		TEXT("moon.red.ring-01.a"), FVector(3000.f, 0.f, 0.f), 500.f, 2500.f, 200);
	const FBodyCandidate MoonB = MakeBody(
		TEXT("moon.red.ring-01.b"), FVector(-3000.f, 0.f, 0.f), 500.f, 2500.f, 200);

	FBodyQueryResult Result;
	TestTrue(TEXT("nearest surface candidate resolves"), SelectDominantBody(
		{ Planet, MoonA, MoonB }, FVector(3400.f, 0.f, 0.f), NAME_None, 0.f, Result));
	TestEqual(TEXT("nearest moon wins"), Result.StableId, FName(TEXT("moon.red.ring-01.a")));

	TestTrue(TEXT("outside moon influence still resolves planet"), SelectDominantBody(
		{ Planet, MoonA }, FVector(7000.f, 0.f, 0.f), NAME_None, 0.f, Result));
	TestEqual(TEXT("out-of-influence moon is rejected"), Result.StableId, FName(TEXT("planet.red.mars")));

	const FBodyCandidate LowPriority = MakeBody(
		TEXT("moon.red.priority.low"), FVector::ZeroVector, 1000.f, 20000.f, 100);
	const FBodyCandidate HighPriority = MakeBody(
		TEXT("moon.red.priority.high"), FVector(10000.f, 0.f, 0.f), 1000.f, 20000.f, 300);
	TestTrue(TEXT("priority overlap resolves"), SelectDominantBody(
		{ LowPriority, HighPriority }, FVector(1100.f, 0.f, 0.f), NAME_None, 0.f, Result));
	TestEqual(TEXT("higher explicit priority wins even when farther from its surface"),
		Result.StableId, FName(TEXT("moon.red.priority.high")));
	TestTrue(TEXT("higher priority bypasses lower-priority hysteresis"), SelectDominantBody(
		{ LowPriority, HighPriority }, FVector(1100.f, 0.f, 0.f),
		FName(TEXT("moon.red.priority.low")), 20000.f, Result));
	TestEqual(TEXT("hysteresis cannot retain a lower-priority body"),
		Result.StableId, FName(TEXT("moon.red.priority.high")));

	const FBodyCandidate LexicalA = MakeBody(
		TEXT("moon.red.tie.a"), FVector(3000.f, 0.f, 0.f), 500.f, 3000.f, 200);
	const FBodyCandidate LexicalB = MakeBody(
		TEXT("moon.red.tie.b"), FVector(-3000.f, 0.f, 0.f), 500.f, 3000.f, 200);
	TestTrue(TEXT("stable-ID tie resolves"), SelectDominantBody(
		{ LexicalB, LexicalA }, FVector::ZeroVector, NAME_None, 0.f, Result));
	TestEqual(TEXT("lexical stable ID is deterministic final tie-break"),
		Result.StableId, FName(TEXT("moon.red.tie.a")));

	const FBodyCandidate PeerA = MakeBody(
		TEXT("moon.red.peer.a"), FVector(-1000.f, 0.f, 0.f), 100.f, 5000.f, 200);
	const FBodyCandidate PeerB = MakeBody(
		TEXT("moon.red.peer.b"), FVector(1000.f, 0.f, 0.f), 100.f, 5000.f, 200);
	TestTrue(TEXT("equal-priority hysteresis query resolves"), SelectDominantBody(
		{ PeerA, PeerB }, FVector(100.f, 0.f, 0.f), FName(TEXT("moon.red.peer.a")),
		300.f, Result));
	TestEqual(TEXT("previous body is held inside hysteresis band"),
		Result.StableId, FName(TEXT("moon.red.peer.a")));

	TestTrue(TEXT("equal-priority switch query resolves"), SelectDominantBody(
		{ PeerA, PeerB }, FVector(400.f, 0.f, 0.f), FName(TEXT("moon.red.peer.a")),
		300.f, Result));
	TestEqual(TEXT("better body wins after hysteresis is exceeded"),
		Result.StableId, FName(TEXT("moon.red.peer.b")));

	TestTrue(TEXT("previous body remains eligible inside its influence exit band"), SelectDominantBody(
		{ Planet, MoonA }, FVector(5600.f, 0.f, 0.f), FName(TEXT("moon.red.ring-01.a")),
		600.f, Result));
	TestEqual(TEXT("previous higher-priority moon is held through the exit margin"),
		Result.StableId, FName(TEXT("moon.red.ring-01.a")));
	TestTrue(TEXT("query resolves after exit margin"), SelectDominantBody(
		{ Planet, MoonA }, FVector(6200.f, 0.f, 0.f), FName(TEXT("moon.red.ring-01.a")),
		600.f, Result));
	TestEqual(TEXT("previous moon is released beyond influence plus hysteresis"),
		Result.StableId, FName(TEXT("planet.red.mars")));

	FBodyQueryResult ForwardOrder;
	FBodyQueryResult ReverseOrder;
	TestTrue(TEXT("forward order resolves"), SelectDominantBody(
		{ LexicalA, LexicalB }, FVector::ZeroVector, NAME_None, 0.f, ForwardOrder));
	TestTrue(TEXT("reverse order resolves"), SelectDominantBody(
		{ LexicalB, LexicalA }, FVector::ZeroVector, NAME_None, 0.f, ReverseOrder));
	TestEqual(TEXT("candidate iteration order cannot change the selected stable ID"),
		ForwardOrder.StableId, ReverseOrder.StableId);

	FBodyCandidate NearA = MakeBody(
		TEXT("moon.red.near.a"), FVector(1100.04, 0.0, 0.0), 100.f, 3000.f, 200);
	FBodyCandidate NearB = MakeBody(
		TEXT("moon.red.near.b"), FVector(-1100.08, 0.0, 0.0), 100.f, 3000.f, 200);
	FBodyCandidate NearC = MakeBody(
		TEXT("moon.red.near.c"), FVector(0.0, 1100.12, 0.0), 100.f, 3000.f, 200);
	FBodyQueryResult NearOrderA;
	FBodyQueryResult NearOrderB;
	FBodyQueryResult NearOrderC;
	TestTrue(TEXT("three-body near-tie order A resolves"), SelectDominantBody(
		{ NearA, NearB, NearC }, FVector::ZeroVector, NAME_None, 0.f, NearOrderA));
	TestTrue(TEXT("three-body near-tie order B resolves"), SelectDominantBody(
		{ NearC, NearA, NearB }, FVector::ZeroVector, NAME_None, 0.f, NearOrderB));
	TestTrue(TEXT("three-body near-tie order C resolves"), SelectDominantBody(
		{ NearB, NearC, NearA }, FVector::ZeroVector, NAME_None, 0.f, NearOrderC));
	TestEqual(TEXT("quantized total order is invariant for permutation B"),
		NearOrderA.StableId, NearOrderB.StableId);
	TestEqual(TEXT("quantized total order is invariant for permutation C"),
		NearOrderA.StableId, NearOrderC.StableId);

	TestFalse(TEXT("duplicate stable IDs fail closed"), SelectDominantBody(
		{ MoonA, MoonA }, FVector(3400.f, 0.f, 0.f), NAME_None, 0.f, Result));

	FBodyCandidate InvalidNaN = MakeBody(
		TEXT("moon.red.invalid.nan"), FVector(NAN, 0.f, 0.f), 100.f, 1000.f, 999);
	FBodyCandidate InvalidInfluence = MakeBody(
		TEXT("moon.red.invalid.influence"), FVector::ZeroVector, 100.f, -1.f, 999);
	TestTrue(TEXT("malformed candidates are ignored when one valid body remains"), SelectDominantBody(
		{ InvalidNaN, InvalidInfluence, Planet }, FVector(1200.f, 0.f, 0.f),
		NAME_None, 0.f, Result));
	TestEqual(TEXT("valid body survives malformed candidates"),
		Result.StableId, FName(TEXT("planet.red.mars")));

	FBodyCandidate SelectionDatum = MakeBody(
		TEXT("moon.red.selection-datum"), FVector::ZeroVector, 100.f, 10000.f, 250);
	SelectionDatum.SelectionSurfaceRadius = 1000.f;
	TestTrue(TEXT("separate selection datum resolves"), SelectDominantBody(
		{ Planet, SelectionDatum }, FVector(1005.f, 0.f, 0.f), NAME_None, 0.f, Result));
	TestEqual(TEXT("selection datum controls scoring"),
		Result.StableId, FName(TEXT("moon.red.selection-datum")));
	TestEqual(TEXT("physical surface radius remains the returned contract"),
		Result.SurfaceRadius, 100.f);

	TestTrue(TEXT("missing previous ID falls back to deterministic selection"), SelectDominantBody(
		{ LexicalB, LexicalA }, FVector::ZeroVector, FName(TEXT("moon.red.missing")),
		1000.f, Result));
	TestEqual(TEXT("missing previous ID does not perturb the total-order winner"),
		Result.StableId, FName(TEXT("moon.red.tie.a")));

	return !HasAnyErrors();
}

#endif
