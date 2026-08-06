// Copyright Epic Games, Inc. All Rights Reserved.

#include "TitanDeveloperSettings.h"
#include "Misc/App.h"

UTitanDeveloperSettings::UTitanDeveloperSettings()
{
}

FName UTitanDeveloperSettings::GetCategoryName() const
{
	return FApp::GetProjectName();
}
