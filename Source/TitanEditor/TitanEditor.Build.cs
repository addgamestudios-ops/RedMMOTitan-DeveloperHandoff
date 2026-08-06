// Copyright Epic Games, Inc. All Rights Reserved.

using UnrealBuildTool;

public class TitanEditor : ModuleRules
{
	public TitanEditor(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
	
		PublicDependencyModuleNames.AddRange(new string[] {
			"Core",
			"CoreUObject",
			"Engine",
			"UnrealEd",
			"Titan",
            "PhotoAlbum"
        });

		PublicIncludePaths.AddRange(new string[] {
			"TitanEditor"
		});

		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"Slate",
			"SlateCore",
			"ToolMenus"
		});
	}
}
