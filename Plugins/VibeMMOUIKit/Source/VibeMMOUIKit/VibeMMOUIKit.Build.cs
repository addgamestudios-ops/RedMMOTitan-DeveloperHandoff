using UnrealBuildTool;

public class VibeMMOUIKit : ModuleRules
{
	public VibeMMOUIKit(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(
			new string[]
			{
				"Core",
				"CoreUObject",
				"DeveloperSettings",
				"Engine",
				"InputCore",
				"Slate",
				"SlateCore",
				"UMG"
			}
		);

		PrivateDependencyModuleNames.AddRange(
			new string[]
			{
				// FUniqueNetIdRepl::ToString for account-isolated local save slots.
				"CoreOnline"
			}
		);
	}
}
