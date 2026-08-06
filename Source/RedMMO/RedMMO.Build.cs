using System.IO;
using UnrealBuildTool;

public class RedMMO : ModuleRules
{
	public RedMMO(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		// RedMMOEditorTools includes ControlRig/RigVM authoring APIs. Keeping it out of the gameplay
		// unity translation unit avoids multi-gigabyte compiler pressure and makes incremental builds
		// recompile only the file that changed.
		bUseUnity = false;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "Niagara", "UMG", "VibeMMOUIKit", "RedHUDRuntime", "AIModule", "GameplayTasks", "Json", "OnlineSubsystem", "OnlineSubsystemUtils" });
		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"Slate", "SlateCore",
			// Local-only spherical shoreline ribbons sample PlanetGen's deterministic height field and
			// repair the procedural ocean's tangent basis before SoStylized normal maps are rendered.
			"ProceduralMeshComponent", "PlanetGen"
		});

		// Marketplace FocalRig is optional. Intermediate-only Fab leftovers (no .uplugin / no
		// Binaries) must not hard-fail TitanEditor. When an official FocalRig.uplugin returns,
		// this auto-relinks the module and enables REDMMO_WITH_MARKETPLACE_FOCALRIG.
		bool bHasOfficialFocalRig = Target.bBuildEditor && HasOfficialFocalRigPayload();
		PublicDefinitions.Add(bHasOfficialFocalRig
			? "REDMMO_WITH_MARKETPLACE_FOCALRIG=1"
			: "REDMMO_WITH_MARKETPLACE_FOCALRIG=0");

		// Editor-only deps for the C++ authoring tools (URedMMOEditorTools): AnimGraph node types
		// + Blueprint compile/utils. Guarded so packaged/runtime builds never link editor modules.
		if (Target.bBuildEditor)
		{
			PrivateDependencyModuleNames.AddRange(new string[]
			{
				"UnrealEd", "AssetRegistry", "AnimGraph", "AnimGraphRuntime", "BlueprintGraph", "MaterialEditor",
				// DEF-0003 editor automation records the live client master output to a WAV artifact.
				"AudioMixer",
				"ControlRig", "ControlRigDeveloper", "ControlRigEditor",
				"RigVM", "RigVMDeveloper",
				// CreateContext() is exported by PlatformCrypto, while the returned
				// FEncryptionContext::CalcSHA256 implementation is exported by its
				// context module and therefore must be a direct link dependency.
				"PlatformCrypto", "PlatformCryptoContext"
			});

			if (bHasOfficialFocalRig)
			{
				PrivateDependencyModuleNames.Add("FocalRig");
			}
		}
	}

	private bool HasOfficialFocalRigPayload()
	{
		string MarketplaceRoot = Path.Combine(EngineDirectory, "Plugins", "Marketplace");
		if (Directory.Exists(MarketplaceRoot))
		{
			foreach (string Dir in Directory.GetDirectories(MarketplaceRoot, "*FocalRig*"))
			{
				if (File.Exists(Path.Combine(Dir, "FocalRig.uplugin")))
				{
					return true;
				}
			}
		}

		string ProjectPlugin = Path.Combine(ModuleDirectory, "..", "..", "Plugins", "FocalRig", "FocalRig.uplugin");
		return File.Exists(Path.GetFullPath(ProjectPlugin));
	}
}
