// Copyright Epic Games, Inc. All Rights Reserved.

using UnrealBuildTool;

public class Titan : ModuleRules
{
	public Titan(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
	
		PublicDependencyModuleNames.AddRange(
			new string[] {
				"Core",
				"CoreUObject",
				"Engine",
				"InputCore",
				"GameplayTags",
				"EnhancedInput",
				"GameplayAbilities",
				"GameplayTasks",
				"AIModule",
				"Water",
				"PhysicsCore",
				"Slate",
				"CommonUI",
				"ImageCore",
				"DeveloperSettings",
				"TitanCamera",
				"TitanAbilities",
				"TitanMovement",
				"TitanRaft",
				"TitanUI",
				"TitanFramework",
				"PhotoAlbum",
				"Chaos"
			});

		PublicIncludePaths.AddRange(
			new string[] {
				"Titan",
				"Titan/Logging",
				"Titan/Character",
				"Titan/Development"
			});

        PrivateDependencyModuleNames.AddRange(
			new string[] {
				"ChunkDownloader"
			});

        // Uncomment if you are using Slate UI
        // PrivateDependencyModuleNames.AddRange(new string[] { "Slate", "SlateCore" });

        // Uncomment if you are using online features
        // PrivateDependencyModuleNames.Add("OnlineSubsystem");

        // To include OnlineSubsystemSteam, add it to the plugins section in your uproject file with the Enabled attribute set to true
    }
}
