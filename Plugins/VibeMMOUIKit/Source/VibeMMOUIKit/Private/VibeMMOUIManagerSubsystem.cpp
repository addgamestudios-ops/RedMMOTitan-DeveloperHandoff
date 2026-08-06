#include "VibeMMOUIManagerSubsystem.h"

#include "Style/VibeMMOUIStyleDataAsset.h"

void UVibeMMOUIManagerSubsystem::SetActiveStyleDataAsset(UVibeMMOUIStyleDataAsset* InStyleDataAsset)
{
	ActiveStyleDataAsset = InStyleDataAsset;
}

UVibeMMOUIStyleDataAsset* UVibeMMOUIManagerSubsystem::GetActiveStyleDataAsset() const
{
	return ActiveStyleDataAsset;
}
