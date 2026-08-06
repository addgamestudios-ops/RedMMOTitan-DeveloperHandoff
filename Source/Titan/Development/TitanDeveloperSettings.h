// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "Engine/DeveloperSettings.h"
#include "UObject/PrimaryAssetId.h"
#include "UObject/SoftObjectPath.h"
#include "TitanDeveloperSettings.generated.h"

/**
 * Developer settings / editor cheats
 */
UCLASS(config=EditorPerProjectUserSettings)
class TITAN_API UTitanDeveloperSettings : public UDeveloperSettings
{
	GENERATED_BODY()

public:
	UTitanDeveloperSettings();

	//~UDeveloperSettings interface
	virtual FName GetCategoryName() const override;
	//~End of UDeveloperSettings interface

#if WITH_EDITORONLY_DATA
	/** A list of common maps that will be accessible via the editor the toolbar */
	UPROPERTY(config, EditAnywhere, BlueprintReadOnly, Category=Maps, meta=(AllowedClasses="/Script/Engine.World"))
	TArray<FSoftObjectPath> CommonEditorMaps;

	/** If true, all Titan-specific asset validators will be skipped */
	UPROPERTY(config, EditAnywhere, Category="Data Validation")
	bool bSkipTitanValidators = false;

#endif
};
