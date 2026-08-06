// Copyright Epic Games, Inc. All Rights Reserved.

using UnrealBuildTool;
using System.Collections.Generic;

public class TitanEditorTarget : TargetRules
{
	public TitanEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		ExtraModuleNames.Add("RedMMO");
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
	}
}
