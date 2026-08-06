// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "TitanSkinPreview.generated.h"

/**
 *	ATitanSkinPreview
 *	Base class for the Skin Preview actor used in the menu.
 *  No native functionality; simply enforcing notplaceable.
 */
UCLASS(abstract, notplaceable)
class TITAN_API ATitanSkinPreview : public AActor
{
	GENERATED_BODY()
	
public:	
	// Sets default values for this actor's properties
	ATitanSkinPreview();

};
