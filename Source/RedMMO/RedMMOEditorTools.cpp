#include "RedMMOEditorTools.h"

#if WITH_EDITOR
#include "Animation/AnimBlueprint.h"
#include "Animation/AnimSequenceBase.h"
#include "Animation/AnimNodeBase.h"
// The UAnimGraphNode_* editor headers transitively include their FAnimNode_* runtime structs.
#include "AnimGraphNode_SequenceEvaluator.h"
#include "AnimGraphNode_SequencePlayer.h"
#include "AnimGraphNode_Slot.h"
#include "AnimGraphNode_ModifyBone.h"
#include "AnimGraphNode_BlendListByBool.h"
#include "AnimGraphNode_LayeredBoneBlend.h"
#include "AnimGraphNode_Root.h"
#include "AnimGraphNode_ComponentToLocalSpace.h"
#include "AnimGraphNode_LocalToComponentSpace.h"
#include "AnimGraphNode_ControlRig.h"
#include "BoneControllers/AnimNode_ModifyBone.h"
#include "ControlRigBlueprintFactory.h"
#include "ControlRigBlueprintLegacy.h"
#include "Rigs/RigHierarchyController.h"
#include "RigVMModel/RigVMController.h"
#include "RigVMModel/RigVMGraph.h"
#include "RigVMModel/RigVMNode.h"
#include "RigVMModel/Nodes/RigVMUnitNode.h"
#include "RigVMModel/Nodes/RigVMVariableNode.h"
#include "Units/Execution/RigUnit_BeginExecution.h"
#if REDMMO_WITH_MARKETPLACE_FOCALRIG
#include "AimChain/FocalRigUnit_AimChain.h"
#include "AimWeapon/FocalRigUnit_AimWeapon.h"
#include "FocalRigSettings.h"
#include "Utility/FocalRigRigVMHelpers.h"
#endif
#include "Units/Highlevel/Hierarchy/RigUnit_AimBone.h"
#include "K2Node_VariableGet.h"
#include "EdGraphSchema_K2.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphPin.h"
#include "EdGraphUtilities.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "UObject/UnrealType.h"
#include "Engine/Blueprint.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/SkeletalMeshSocket.h"
#include "AnimationRuntime.h"
#include "GameFramework/Actor.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "Components/StaticMeshComponent.h"
#include "Editor.h"
#include "Subsystems/EditorActorSubsystem.h"
#include "ScopedTransaction.h"
#include "RedGravityBodies.h"
#include "RedPlanetTerrainQuery.h"
#include "IPlatformCrypto.h"
#include "ImageCore.h"
#include "ImageUtils.h"
#if __has_include("PlanetGenMacroHeightfieldAsset.h")
#include "PlanetGenMacroHeightfieldAsset.h"
#define REDMMO_HAS_PLANETGEN_MACROHEIGHTFIELD 1
#else
#define REDMMO_HAS_PLANETGEN_MACROHEIGHTFIELD 0
#endif
#include "FileHelpers.h"
#include "Dom/JsonObject.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "Serialization/Archive.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonReader.h"
#include "Materials/Material.h"
#include "Materials/MaterialFunction.h"
#include "Materials/MaterialExpressionSubtract.h"
#include "Materials/MaterialInstanceConstant.h"
#include "Materials/MaterialFunctionInstance.h"
#include "Materials/MaterialLayersFunctions.h"
#include "Materials/MaterialParameters.h"
#include "StaticParameterSet.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "UObject/Package.h"
#include "UObject/UObjectGlobals.h"
#include "UObject/SavePackage.h"
#include "Materials/MaterialExpressionConstant.h"
#include "Materials/MaterialExpressionScalarParameter.h"
#include "Materials/MaterialExpressionVectorParameter.h"
#include "Materials/MaterialExpressionTextureBase.h"
#include "Materials/MaterialExpressionMaterialFunctionCall.h"
#include "MaterialEditingLibrary.h"
#include "MaterialEditor/MaterialEditorInstanceConstant.h"
#include "Engine/Texture.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "HAL/IConsoleManager.h"

namespace RedMMOEditorToolsPrivate
{
	/** GetMaterialLayers() returns false when EditorOnly LayerStates were cooked/stripped.
	 *  Fall back to parent Material's cached runtime layer stack so Sand can still be resolved. */
	static bool TryGetLayers(UMaterialInstanceConstant* MI, FMaterialLayersFunctions& OutLayers)
	{
		if (MI->GetMaterialLayers(OutLayers) && OutLayers.Layers.Num() > 0)
		{
			return true;
		}

		UMaterialInterface* Parent = MI->Parent;
		while (Parent)
		{
			if (Parent->GetMaterialLayers(OutLayers) && OutLayers.Layers.Num() > 0)
			{
				return true;
			}
			if (const UMaterialInstance* ParentMI = Cast<UMaterialInstance>(Parent))
			{
				Parent = ParentMI->Parent;
			}
			else
			{
				break;
			}
		}

		// Last resort: match by layer asset name (MFI_Sand / MF_GrassLayer / …) using
		// the known PlanetGen stack order when names are missing.
		return false;
	}

	static bool ResolveLayerIndex(UMaterialInstanceConstant* MI, const FString& LayerNameOrIndex, int32& OutIndex, FString& OutResolvedName, FString& OutError)
	{
		const FString Want = LayerNameOrIndex.TrimStartAndEnd();

		// Numeric indices can be applied even when GetMaterialLayers() fails
		// (EditorOnly LayerStates often empty on this MI → GetMaterialLayers returns false).
		if (Want.IsNumeric())
		{
			OutIndex = FCString::Atoi(*Want);
			if (OutIndex < 0 || OutIndex > 15)
			{
				OutError = FString::Printf(TEXT("ERR: layer index %d out of sane range"), OutIndex);
				return false;
			}
			OutResolvedName = FString::Printf(TEXT("Layer %d"), OutIndex);
			FMaterialLayersFunctions Layers;
			if (TryGetLayers(MI, Layers) && Layers.Layers.IsValidIndex(OutIndex))
			{
				const FString Name = Layers.GetLayerName(OutIndex).ToString();
				const FString AssetName = Layers.Layers[OutIndex] ? Layers.Layers[OutIndex]->GetName() : FString();
				OutResolvedName = !Name.IsEmpty() ? Name : AssetName;
			}
			return true;
		}

		FMaterialLayersFunctions Layers;
		if (!TryGetLayers(MI, Layers))
		{
			OutError = TEXT("ERR: MI has no material layers (GetMaterialLayers failed). Pass a numeric Sand index (try 0..4).");
			return false;
		}

		FString WantNorm = Want;
		WantNorm.ReplaceInline(TEXT(" "), TEXT(""));
		for (int32 i = 0; i < Layers.Layers.Num(); ++i)
		{
			const FString Name = Layers.GetLayerName(i).ToString();
			const FString AssetName = Layers.Layers[i] ? Layers.Layers[i]->GetName() : FString();
			FString NameNorm = Name;
			NameNorm.ReplaceInline(TEXT(" "), TEXT(""));
			if (Name.Equals(Want, ESearchCase::IgnoreCase)
				|| NameNorm.Equals(WantNorm, ESearchCase::IgnoreCase)
				|| AssetName.Equals(Want, ESearchCase::IgnoreCase)
				|| AssetName.Contains(Want, ESearchCase::IgnoreCase))
			{
				OutIndex = i;
				OutResolvedName = Name.IsEmpty() ? AssetName : Name;
				return true;
			}
		}

		TArray<FString> Names;
		for (int32 i = 0; i < Layers.Layers.Num(); ++i)
		{
			const FString Name = Layers.GetLayerName(i).ToString();
			const FString AssetName = Layers.Layers[i] ? Layers.Layers[i]->GetName() : TEXT("null");
			Names.Add(FString::Printf(TEXT("%d:%s(%s)"), i, *Name, *AssetName));
		}
		OutError = FString::Printf(TEXT("ERR: layer '%s' not found. Available: %s"), *Want, *FString::Join(Names, TEXT(", ")));
		return false;
	}

	static FString AssociationToString(EMaterialParameterAssociation Assoc)
	{
		switch (Assoc)
		{
		case EMaterialParameterAssociation::LayerParameter: return TEXT("Layer");
		case EMaterialParameterAssociation::BlendParameter: return TEXT("Blend");
		default: return TEXT("Global");
		}
	}
}
#endif

FString URedMMOEditorTools::SetAnimGraphSequence(const FString& AnimBlueprintPath, const FString& FromAnimNameOrPath, const FString& ToAnimPath)
{
#if WITH_EDITOR
	UAnimBlueprint* ABP = LoadObject<UAnimBlueprint>(nullptr, *AnimBlueprintPath);
	if (!ABP) { return FString::Printf(TEXT("ERR: AnimBlueprint not found: %s"), *AnimBlueprintPath); }

	UAnimSequenceBase* ToAnim = LoadObject<UAnimSequenceBase>(nullptr, *ToAnimPath);
	if (!ToAnim) { return FString::Printf(TEXT("ERR: target animation not found: %s"), *ToAnimPath); }

	auto Matches = [&](UAnimSequenceBase* Cur) -> bool
	{
		if (FromAnimNameOrPath.IsEmpty()) { return true; }
		if (!Cur) { return false; }
		return Cur->GetPathName() == FromAnimNameOrPath || Cur->GetName() == FromAnimNameOrPath;
	};

	// Read/write the "Sequence" object property on the node's FAnimNode struct via reflection
	// (robust to per-version accessor changes; no node creation = no graph-topology mutation).
	FObjectProperty* EvalSeqProp = CastField<FObjectProperty>(FAnimNode_SequenceEvaluator::StaticStruct()->FindPropertyByName(TEXT("Sequence")));
	FObjectProperty* PlaySeqProp = CastField<FObjectProperty>(FAnimNode_SequencePlayer::StaticStruct()->FindPropertyByName(TEXT("Sequence")));

	TArray<UEdGraph*> Graphs;
	ABP->GetAllGraphs(Graphs);
	int32 Swapped = 0;
	TArray<FString> Details;

	for (UEdGraph* G : Graphs)
	{
		if (!G) { continue; }
		for (UEdGraphNode* N : G->Nodes)
		{
			if (UAnimGraphNode_SequenceEvaluator* SE = Cast<UAnimGraphNode_SequenceEvaluator>(N))
			{
				if (!EvalSeqProp) { continue; }
				UAnimSequenceBase* Cur = Cast<UAnimSequenceBase>(EvalSeqProp->GetObjectPropertyValue_InContainer(&SE->Node));
				if (Matches(Cur))
				{
					SE->Modify();
					EvalSeqProp->SetObjectPropertyValue_InContainer(&SE->Node, ToAnim);
					Details.Add(FString::Printf(TEXT("SeqEval[%s]"), Cur ? *Cur->GetName() : TEXT("None")));
					++Swapped;
				}
			}
			else if (UAnimGraphNode_SequencePlayer* SP = Cast<UAnimGraphNode_SequencePlayer>(N))
			{
				if (!PlaySeqProp) { continue; }
				UAnimSequenceBase* Cur = Cast<UAnimSequenceBase>(PlaySeqProp->GetObjectPropertyValue_InContainer(&SP->Node));
				if (Matches(Cur))
				{
					SP->Modify();
					PlaySeqProp->SetObjectPropertyValue_InContainer(&SP->Node, ToAnim);
					Details.Add(FString::Printf(TEXT("SeqPlayer[%s]"), Cur ? *Cur->GetName() : TEXT("None")));
					++Swapped;
				}
			}
		}
	}

	if (Swapped > 0)
	{
		FBlueprintEditorUtils::MarkBlueprintAsModified(ABP);
		FKismetEditorUtilities::CompileBlueprint(ABP);
	}

	return FString::Printf(TEXT("OK: swapped %d node(s) -> %s : %s"), Swapped, *ToAnim->GetName(), *FString::Join(Details, TEXT(", ")));
#else
	return TEXT("ERR: editor-only tool");
#endif
}

#if WITH_EDITOR
// Find a node's pose pin (input or output) — matched by the pose-link struct subcategory so it never
// confuses the pose flow with a data pin like Rotation (also a struct).
static UEdGraphPin* FindPosePin(UEdGraphNode* Node, EEdGraphPinDirection Dir)
{
	if (!Node) { return nullptr; }
	for (UEdGraphPin* P : Node->Pins)
	{
		if (P && P->Direction == Dir)
		{
			const UObject* Sub = P->PinType.PinSubCategoryObject.Get();
			if (Sub == FPoseLink::StaticStruct() || Sub == FComponentSpacePoseLink::StaticStruct())
			{
				return P;
			}
		}
	}
	return nullptr;
}
#endif

FString URedMMOEditorTools::AddAimModifyBone(const FString& AnimBlueprintPath, const FString& BoneName, const FString& AimVarName)
{
#if WITH_EDITOR
	UAnimBlueprint* ABP = LoadObject<UAnimBlueprint>(nullptr, *AnimBlueprintPath);
	if (!ABP) { return FString::Printf(TEXT("ERR: AnimBlueprint not found: %s"), *AnimBlueprintPath); }

	UEdGraph* AnimGraph = nullptr;
	TArray<UEdGraph*> Graphs;
	ABP->GetAllGraphs(Graphs);
	for (UEdGraph* G : Graphs) { if (G && G->GetFName() == FName(TEXT("AnimGraph"))) { AnimGraph = G; break; } }
	if (!AnimGraph) { return TEXT("ERR: AnimGraph not found"); }

	// The ComponentToLocal node whose pose output feeds the Root (Output Pose).
	UAnimGraphNode_ComponentToLocalSpace* C2L = nullptr;
	for (UEdGraphNode* N : AnimGraph->Nodes)
	{
		UAnimGraphNode_ComponentToLocalSpace* C = Cast<UAnimGraphNode_ComponentToLocalSpace>(N);
		if (!C) { continue; }
		for (UEdGraphPin* P : C->Pins)
		{
			if (P->Direction != EGPD_Output) { continue; }
			for (UEdGraphPin* L : P->LinkedTo)
			{
				if (L && L->GetOwningNode() && L->GetOwningNode()->IsA<UAnimGraphNode_Root>()) { C2L = C; }
			}
		}
	}
	if (!C2L) { return TEXT("ERR: output ComponentToLocal node not found"); }

	UEdGraphPin* C2LIn = FindPosePin(C2L, EGPD_Input);
	if (!C2LIn || C2LIn->LinkedTo.Num() == 0) { return TEXT("ERR: ComponentToLocal input not linked"); }
	UEdGraphPin* SrcOut = C2LIn->LinkedTo[0];

	if (SrcOut->GetOwningNode() && SrcOut->GetOwningNode()->IsA<UAnimGraphNode_ModifyBone>())
	{
		// Already present from a prior run — re-assert bone/mode/exposed-pin/wiring (a half-wired
		// node = the aim var never reaches the bone = gun never moves).
		UAnimGraphNode_ModifyBone* EMB = Cast<UAnimGraphNode_ModifyBone>(SrcOut->GetOwningNode());
		const FName VN0(*AimVarName);
		FEdGraphPinType RT0; RT0.PinCategory = UEdGraphSchema_K2::PC_Struct; RT0.PinSubCategoryObject = TBaseStructure<FRotator>::Get();
		FBlueprintEditorUtils::AddMemberVariable(ABP, VN0, RT0);
		EMB->Node.BoneToModify.BoneName = FName(*BoneName);
		EMB->Node.RotationMode = EBoneModificationMode::BMM_Additive;
		EMB->Node.RotationSpace = EBoneControlSpace::BCS_ComponentSpace;
		for (FOptionalPinFromProperty& Opt : EMB->ShowPinForProperties)
		{
			if (Opt.PropertyName == FName(TEXT("Rotation"))) { Opt.bShowPin = true; }
		}
		EMB->ReconstructNode();
		UEdGraphPin* RP0 = EMB->FindPin(FName(TEXT("Rotation")), EGPD_Input);
		FString WN = TEXT("rotation already wired");
		if (RP0 && RP0->LinkedTo.Num() == 0)
		{
			FGraphNodeCreator<UK2Node_VariableGet> VG0(*AnimGraph);
			UK2Node_VariableGet* G0 = VG0.CreateNode(false);
			G0->VariableReference.SetSelfMember(VN0);
			VG0.Finalize();
			G0->NodePosX = EMB->NodePosX - 260; G0->NodePosY = EMB->NodePosY + 40;
			UEdGraphPin* GO0 = G0->FindPin(VN0, EGPD_Output);
			if (GO0) { GO0->MakeLinkTo(RP0); WN = TEXT("rotation RE-WIRED"); }
		}
		FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(ABP);
		FKismetEditorUtilities::CompileBlueprint(ABP);
		return FString::Printf(TEXT("OK: fixed existing ModifyBone bone=%s (%s)"), *BoneName, *WN);
	}

	// Add the FRotator member variable that drives the aim (idempotent).
	const FName VN(*AimVarName);
	FEdGraphPinType RotType;
	RotType.PinCategory = UEdGraphSchema_K2::PC_Struct;
	RotType.PinSubCategoryObject = TBaseStructure<FRotator>::Get();
	FBlueprintEditorUtils::AddMemberVariable(ABP, VN, RotType);

	// Create the Transform (Modify) Bone node, configure additive component-space.
	FGraphNodeCreator<UAnimGraphNode_ModifyBone> MBCreator(*AnimGraph);
	UAnimGraphNode_ModifyBone* MB = MBCreator.CreateNode(false);
	MB->Node.BoneToModify.BoneName = FName(*BoneName);
	MB->Node.RotationMode = EBoneModificationMode::BMM_Additive;
	MB->Node.RotationSpace = EBoneControlSpace::BCS_ComponentSpace;
	MBCreator.Finalize();
	MB->NodePosX = C2L->NodePosX - 280;
	MB->NodePosY = C2L->NodePosY + 180;
	// Expose the Rotation property as an input pin (after Finalize populated ShowPinForProperties), then reconstruct.
	for (FOptionalPinFromProperty& Opt : MB->ShowPinForProperties)
	{
		if (Opt.PropertyName == FName(TEXT("Rotation"))) { Opt.bShowPin = true; }
	}
	MB->ReconstructNode();

	// Variable getter for the aim rotation.
	FGraphNodeCreator<UK2Node_VariableGet> VGCreator(*AnimGraph);
	UK2Node_VariableGet* VG = VGCreator.CreateNode(false);
	VG->VariableReference.SetSelfMember(VN);
	VGCreator.Finalize();
	VG->NodePosX = MB->NodePosX - 260;
	VG->NodePosY = MB->NodePosY + 40;

	// Wire pose chain: SrcOut -> MB(in) -> MB(out) -> C2L(in)
	UEdGraphPin* MBIn = FindPosePin(MB, EGPD_Input);
	UEdGraphPin* MBOut = FindPosePin(MB, EGPD_Output);
	if (!MBIn || !MBOut) { return TEXT("ERR: ModifyBone pose pins not found"); }
	SrcOut->BreakLinkTo(C2LIn);
	SrcOut->MakeLinkTo(MBIn);
	MBOut->MakeLinkTo(C2LIn);

	// Wire the variable getter -> ModifyBone.Rotation
	UEdGraphPin* RotPin = MB->FindPin(FName(TEXT("Rotation")), EGPD_Input);
	UEdGraphPin* VGOut = VG->FindPin(VN, EGPD_Output);
	FString WireNote = TEXT("rotation pin unwired");
	if (RotPin && VGOut) { VGOut->MakeLinkTo(RotPin); WireNote = TEXT("rotation pin wired"); }

	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(ABP);
	FKismetEditorUtilities::CompileBlueprint(ABP);

	return FString::Printf(TEXT("OK: inserted ModifyBone(%s) additive component-space, var '%s', %s"),
		*BoneName, *AimVarName, *WireNote);
#else
	return TEXT("ERR: editor-only tool");
#endif
}

FString URedMMOEditorTools::InstallFocalRigAim(
	const FString& AnimBlueprintPath,
	const FString& CharacterMeshPath,
	const FString& WeaponMeshPath,
	const FString& ControlRigAssetPath)
{
#if WITH_EDITOR
#if !REDMMO_WITH_MARKETPLACE_FOCALRIG
	// Marketplace FocalRig payload is Intermediate-only / unrestorable. Build a stock ControlRig
	// AimItem substitute that preserves the same AnimBP variable contract (FocalAimTarget/Weight)
	// so gameplay can keep driving aim without the Fab plugin.
	UAnimBlueprint* ABP = LoadObject<UAnimBlueprint>(nullptr, *AnimBlueprintPath);
	USkeletalMesh* CharacterMesh = LoadObject<USkeletalMesh>(nullptr, *CharacterMeshPath);
	if (!ABP) { return FString::Printf(TEXT("ERR: AnimBlueprint not found: %s"), *AnimBlueprintPath); }
	if (!CharacterMesh) { return FString::Printf(TEXT("ERR: character mesh not found: %s"), *CharacterMeshPath); }

	FString RigObjectPath = ControlRigAssetPath;
	if (!RigObjectPath.Contains(TEXT(".")))
	{
		FString RigAssetName;
		if (!RigObjectPath.Split(TEXT("/"), nullptr, &RigAssetName, ESearchCase::CaseSensitive, ESearchDir::FromEnd)
			|| RigAssetName.IsEmpty())
		{
			return FString::Printf(TEXT("ERR: invalid ControlRig asset path: %s"), *ControlRigAssetPath);
		}
		RigObjectPath += TEXT(".") + RigAssetName;
	}

	UControlRigBlueprint* RigBP = LoadObject<UControlRigBlueprint>(nullptr, *RigObjectPath);
	const bool bCreatedRig = RigBP == nullptr;
	if (!RigBP)
	{
		RigBP = UControlRigBlueprintFactory::CreateNewControlRigAsset(ControlRigAssetPath, false);
	}
	if (!RigBP) { return FString::Printf(TEXT("ERR: could not create ControlRig: %s"), *ControlRigAssetPath); }

	URigHierarchy* Hierarchy = RigBP->GetHierarchy();
	URigHierarchyController* HierarchyController = RigBP->GetHierarchyController();
	if (!Hierarchy || !HierarchyController) { return TEXT("ERR: ControlRig hierarchy/controller unavailable"); }

	const FRigElementKey RootKey(TEXT("root"), ERigElementType::Bone);
	if (!Hierarchy->Contains(RootKey))
	{
		HierarchyController->ImportBones(CharacterMesh, NAME_None, false, false, false, false);
	}
	RigBP->SetPreviewMesh(CharacterMesh);

	const FRigElementKey SpineKey(TEXT("spine_03"), ERigElementType::Bone);
	if (!Hierarchy->Contains(SpineKey))
	{
		return TEXT("ERR: spine_03 missing from ControlRig hierarchy (stock aim substitute)");
	}

	auto HasRigVariable = [RigBP](const FName Name)
	{
		return RigBP->GetMemberVariables().ContainsByPredicate(
			[Name](const FRigVMGraphVariableDescription& Variable) { return Variable.Name == Name; });
	};
	const FName AimTargetName(TEXT("AimTarget"));
	const FName AimWeightName(TEXT("AimWeight"));
	if (!HasRigVariable(AimTargetName))
	{
		RigBP->AddMemberVariable(AimTargetName, TBaseStructure<FVector>::Get()->GetPathName(),
			true, false, TEXT("(X=0,Y=10000,Z=0)"));
	}
	if (!HasRigVariable(AimWeightName))
	{
		RigBP->AddMemberVariable(AimWeightName, TEXT("float"), true, false, TEXT("0.0"));
	}

	URigVMGraph* Model = RigBP->GetModel();
	URigVMController* RigController = RigBP->GetOrCreateController(Model);
	if (!Model || !RigController) { return TEXT("ERR: ControlRig model/controller unavailable"); }

	URigVMUnitNode* BeginNode = nullptr;
	for (URigVMNode* Node : Model->GetNodes())
	{
		if (URigVMUnitNode* Unit = Cast<URigVMUnitNode>(Node))
		{
			if (Unit->GetScriptStruct() == FRigUnit_BeginExecution::StaticStruct())
			{
				BeginNode = Unit;
				break;
			}
		}
	}
	if (!BeginNode)
	{
		BeginNode = RigController->AddUnitNode(FRigUnit_BeginExecution::StaticStruct(), TEXT("Execute"),
			FVector2D(-500.f, 0.f), TEXT("ForwardsSolve"), false, false);
	}

	FRigUnit_AimItem SpineAimDefaults;
	SpineAimDefaults.Item = SpineKey;
	SpineAimDefaults.Primary.Weight = 1.f;
	SpineAimDefaults.Primary.Axis = FVector::XAxisVector;
	SpineAimDefaults.Primary.Target = FVector(0.f, 10000.f, 0.f);
	SpineAimDefaults.Primary.Kind = EControlRigVectorKind::Location;
	SpineAimDefaults.Secondary.Weight = 0.f;
	SpineAimDefaults.Weight = 1.f;

	URigVMUnitNode* SpineAimNode = Cast<URigVMUnitNode>(Model->FindNodeByName(TEXT("RedStockSpineAim")));
	if (!SpineAimNode)
	{
		SpineAimNode = RigController->AddUnitNode(SpineAimDefaults, TEXT("Execute"), FVector2D(0.f, 0.f),
			TEXT("RedStockSpineAim"), false, false);
	}
	if (!SpineAimNode) { return TEXT("ERR: failed to add stock ControlRig AimItem unit"); }

	URigVMVariableNode* AimTargetNode = Cast<URigVMVariableNode>(Model->FindNodeByName(TEXT("GetAimTarget")));
	if (!AimTargetNode)
	{
		AimTargetNode = RigController->AddVariableNode(AimTargetName, TEXT("FVector"), TBaseStructure<FVector>::Get(),
			true, TEXT("(X=0,Y=10000,Z=0)"), FVector2D(-350.f, 180.f), TEXT("GetAimTarget"), false, false);
	}
	URigVMVariableNode* AimWeightNode = Cast<URigVMVariableNode>(Model->FindNodeByName(TEXT("GetAimWeight")));
	if (!AimWeightNode)
	{
		AimWeightNode = RigController->AddVariableNode(AimWeightName, TEXT("float"), nullptr,
			true, TEXT("0.0"), FVector2D(-350.f, 300.f), TEXT("GetAimWeight"), false, false);
	}
	if (!AimTargetNode || !AimWeightNode) { return TEXT("ERR: failed to add ControlRig variable getter nodes"); }

	RigController->AddLink(BeginNode->GetNodePath() + TEXT(".ExecutePin"),
		SpineAimNode->GetNodePath() + TEXT(".ExecutePin"), false, false);
	RigController->AddLink(AimTargetNode->GetValuePin()->GetPinPath(),
		SpineAimNode->GetNodePath() + TEXT(".Primary.Target"), false, false);
	RigController->AddLink(AimWeightNode->GetValuePin()->GetPinPath(),
		SpineAimNode->GetNodePath() + TEXT(".Weight"), false, false);

	RigBP->PropagateHierarchyFromBPToInstances();
	RigBP->RecompileVM();
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(RigBP);
	FKismetEditorUtilities::CompileBlueprint(RigBP);

	UEdGraph* AnimGraph = nullptr;
	TArray<UEdGraph*> Graphs;
	ABP->GetAllGraphs(Graphs);
	for (UEdGraph* Graph : Graphs)
	{
		if (Graph && Graph->GetFName() == FName(TEXT("AnimGraph"))) { AnimGraph = Graph; break; }
	}
	if (!AnimGraph) { return TEXT("ERR: AnimGraph not found"); }

	const FName ABPAimTargetName(TEXT("FocalAimTarget"));
	const FName ABPAimWeightName(TEXT("FocalAimWeight"));
	FEdGraphPinType VectorType;
	VectorType.PinCategory = UEdGraphSchema_K2::PC_Struct;
	VectorType.PinSubCategoryObject = TBaseStructure<FVector>::Get();
	FBlueprintEditorUtils::AddMemberVariable(ABP, ABPAimTargetName, VectorType);
	FEdGraphPinType FloatType;
	FloatType.PinCategory = UEdGraphSchema_K2::PC_Real;
	FloatType.PinSubCategory = UEdGraphSchema_K2::PC_Float;
	FBlueprintEditorUtils::AddMemberVariable(ABP, ABPAimWeightName, FloatType);

	UAnimGraphNode_Root* RootNode = nullptr;
	UAnimGraphNode_ControlRig* ControlRigNode = nullptr;
	for (UEdGraphNode* GraphNode : AnimGraph->Nodes)
	{
		if (!RootNode) { RootNode = Cast<UAnimGraphNode_Root>(GraphNode); }
		if (!ControlRigNode) { ControlRigNode = Cast<UAnimGraphNode_ControlRig>(GraphNode); }
	}
	if (!RootNode) { return TEXT("ERR: AnimGraph output Root node not found"); }

	const bool bCreatedAnimNode = ControlRigNode == nullptr;
	if (!ControlRigNode)
	{
		FGraphNodeCreator<UAnimGraphNode_ControlRig> Creator(*AnimGraph);
		ControlRigNode = Creator.CreateNode(false);
		ControlRigNode->Node.SetControlRigClass(RigBP->GetControlRigAssetReference().GetBlueprintClass());
		Creator.Finalize();
		ControlRigNode->NodePosX = RootNode->NodePosX - 220;
		ControlRigNode->NodePosY = RootNode->NodePosY;
		ControlRigNode->AddSourceTargetProperties(ABPAimTargetName, AimTargetName);
		ControlRigNode->AddSourceTargetProperties(ABPAimWeightName, AimWeightName);
		ControlRigNode->ReconstructNode();
	}
	else
	{
		ControlRigNode->Node.SetControlRigClass(RigBP->GetControlRigAssetReference().GetBlueprintClass());
		ControlRigNode->ReconstructNode();
	}

	UEdGraphPin* RootIn = FindPosePin(RootNode, EGPD_Input);
	UEdGraphPin* RigIn = FindPosePin(ControlRigNode, EGPD_Input);
	UEdGraphPin* RigOut = FindPosePin(ControlRigNode, EGPD_Output);
	if (!RootIn || !RigIn || !RigOut) { return TEXT("ERR: ControlRig/Root pose pins unresolved"); }
	if (bCreatedAnimNode)
	{
		if (RootIn->LinkedTo.Num() != 1) { return TEXT("ERR: Root input must have exactly one source pose"); }
		UEdGraphPin* SourcePose = RootIn->LinkedTo[0];
		SourcePose->BreakLinkTo(RootIn);
		SourcePose->MakeLinkTo(RigIn);
		RigOut->MakeLinkTo(RootIn);
	}

	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(ABP);
	FKismetEditorUtilities::CompileBlueprint(ABP);
	RigBP->MarkPackageDirty();
	ABP->MarkPackageDirty();
	TArray<UPackage*> PackagesToSave { RigBP->GetOutermost(), ABP->GetOutermost() };
	FEditorFileUtils::PromptForCheckoutAndSave(PackagesToSave, false, false);

	return FString::Printf(
		TEXT("OK: stock ControlRig aim substitute installed (marketplace FocalRig absent; rig=%s, createdRig=%d, animNode=%s). Restore Fab FocalRig.uplugin then set Titan.uproject FocalRig Enabled=true to re-enable official AimChain/AimWeapon."),
		*RigBP->GetPathName(), bCreatedRig ? 1 : 0, bCreatedAnimNode ? TEXT("created") : TEXT("updated"));
#else
	UAnimBlueprint* ABP = LoadObject<UAnimBlueprint>(nullptr, *AnimBlueprintPath);
	USkeletalMesh* CharacterMesh = LoadObject<USkeletalMesh>(nullptr, *CharacterMeshPath);
	USkeletalMesh* RifleMesh = LoadObject<USkeletalMesh>(nullptr, *WeaponMeshPath);
	if (!ABP) { return FString::Printf(TEXT("ERR: AnimBlueprint not found: %s"), *AnimBlueprintPath); }
	if (!CharacterMesh) { return FString::Printf(TEXT("ERR: character mesh not found: %s"), *CharacterMeshPath); }
	if (!RifleMesh) { return FString::Printf(TEXT("ERR: weapon mesh not found: %s"), *WeaponMeshPath); }

	FString RigObjectPath = ControlRigAssetPath;
	if (!RigObjectPath.Contains(TEXT(".")))
	{
		FString RigAssetName;
		if (!RigObjectPath.Split(TEXT("/"), nullptr, &RigAssetName, ESearchCase::CaseSensitive, ESearchDir::FromEnd)
			|| RigAssetName.IsEmpty())
		{
			return FString::Printf(TEXT("ERR: invalid ControlRig asset path: %s"), *ControlRigAssetPath);
		}
		RigObjectPath += TEXT(".") + RigAssetName;
	}

	UControlRigBlueprint* RigBP = LoadObject<UControlRigBlueprint>(nullptr, *RigObjectPath);
	const bool bCreatedRig = RigBP == nullptr;
	if (!RigBP)
	{
		RigBP = UControlRigBlueprintFactory::CreateNewControlRigAsset(ControlRigAssetPath, false);
	}
	if (!RigBP) { return FString::Printf(TEXT("ERR: could not create ControlRig: %s"), *ControlRigAssetPath); }

	URigHierarchy* Hierarchy = RigBP->GetHierarchy();
	URigHierarchyController* HierarchyController = RigBP->GetHierarchyController();
	if (!Hierarchy || !HierarchyController) { return TEXT("ERR: ControlRig hierarchy/controller unavailable"); }

	// Import only missing bones. Never replace the hierarchy on an update: the virtual muzzle is a user null.
	const FRigElementKey RootKey(TEXT("root"), ERigElementType::Bone);
	if (!Hierarchy->Contains(RootKey))
	{
		HierarchyController->ImportBones(CharacterMesh, NAME_None, false, false, false, false);
	}
	RigBP->SetPreviewMesh(CharacterMesh);

	const FReferenceSkeleton& CharRef = CharacterMesh->GetRefSkeleton();
	const USkeletalMeshSocket* GripSocket = CharacterMesh->FindSocket(TEXT("hand_rSocket"));
	const FName GripBoneName = GripSocket ? GripSocket->BoneName : FName(TEXT("hand_r"));
	const int32 GripBoneIndex = CharRef.FindBoneIndex(GripBoneName);
	if (GripBoneIndex == INDEX_NONE)
	{
		return FString::Printf(TEXT("ERR: grip bone '%s' missing from character skeleton"), *GripBoneName.ToString());
	}
	const FRigElementKey GripBoneKey(GripBoneName, ERigElementType::Bone);
	if (!Hierarchy->Contains(GripBoneKey))
	{
		return FString::Printf(TEXT("ERR: grip bone '%s' missing from ControlRig hierarchy"), *GripBoneName.ToString());
	}

	const FTransform GripBoneGlobal = FAnimationRuntime::GetComponentSpaceTransformRefPose(CharRef, GripBoneIndex);
	const FTransform GripSocketLocal = GripSocket ? GripSocket->GetSocketLocalTransform() : FTransform::Identity;
	const FTransform GripGlobal = GripSocketLocal * GripBoneGlobal;

	// Resolve the rifle's muzzle transform in rifle-component space. This project deliberately falls
	// back to the same offset used by GetMuzzleWorldLocation when the asset has no authored socket.
	FTransform RifleMuzzle = FTransform::Identity;
	if (const USkeletalMeshSocket* RifleMuzzleSocket = RifleMesh->FindSocket(TEXT("Muzzle")))
	{
		const FReferenceSkeleton& RifleRef = RifleMesh->GetRefSkeleton();
		const int32 MuzzleBoneIndex = RifleRef.FindBoneIndex(RifleMuzzleSocket->BoneName);
		if (MuzzleBoneIndex != INDEX_NONE)
		{
			RifleMuzzle = RifleMuzzleSocket->GetSocketLocalTransform()
				* FAnimationRuntime::GetComponentSpaceTransformRefPose(RifleRef, MuzzleBoneIndex);
		}
	}
	else
	{
		RifleMuzzle.SetLocation(FVector(0.f, 55.f, 7.f));
	}

	const FTransform MuzzleInRig = RifleMuzzle * GripGlobal;
	// Aim along the physical grip-to-muzzle line, not the socket's decorative rotation. The project
	// rifle's Muzzle socket sits at (+55,-7,0) along the mesh barrel but is yawed 90 degrees to orient
	// the Niagara effect. Treating that rotated socket +Y as the barrel points the virtual muzzle in
	// the opposite direction and makes FocalRig lift the rifle backward over the character's head.
	FVector BarrelDirection = (MuzzleInRig.GetLocation() - GripGlobal.GetLocation()).GetSafeNormal();
	if (BarrelDirection.IsNearlyZero())
	{
		BarrelDirection = MuzzleInRig.TransformVectorNoScale(FVector::XAxisVector).GetSafeNormal();
	}
	if (BarrelDirection.IsNearlyZero()) { BarrelDirection = FVector::XAxisVector; }
	FVector MuzzleUp = FVector::ZAxisVector;
	if (FMath::Abs(FVector::DotProduct(BarrelDirection, MuzzleUp)) > 0.98f)
	{
		MuzzleUp = FVector::XAxisVector;
	}
	const FTransform VirtualMuzzleTransform(
		FRotationMatrix::MakeFromXZ(BarrelDirection, MuzzleUp).ToQuat(),
		MuzzleInRig.GetLocation(), FVector::OneVector);

	const FRigElementKey VirtualMuzzleKey(TEXT("red_virtual_muzzle"), ERigElementType::Null);
	if (!Hierarchy->Contains(VirtualMuzzleKey))
	{
		HierarchyController->AddNull(VirtualMuzzleKey.Name, GripBoneKey, VirtualMuzzleTransform,
			/*bTransformInGlobal=*/true, /*bSetupUndo=*/false, /*bPrintPythonCommand=*/false);
	}
	else
	{
		Hierarchy->SetInitialGlobalTransform(VirtualMuzzleKey, VirtualMuzzleTransform, true, false);
		Hierarchy->SetGlobalTransform(VirtualMuzzleKey, VirtualMuzzleTransform,
			/*bInitial=*/false, /*bAffectChildren=*/true, /*bSetupUndo=*/false, /*bPrintPythonCommand=*/false);
	}

	auto HasRigVariable = [RigBP](const FName Name)
	{
		return RigBP->GetMemberVariables().ContainsByPredicate(
			[Name](const FRigVMGraphVariableDescription& Variable) { return Variable.Name == Name; });
	};
	const FName AimTargetName(TEXT("AimTarget"));
	const FName AimWeightName(TEXT("AimWeight"));
	if (!HasRigVariable(AimTargetName))
	{
		// UE 5.8's runtime ControlRig asset requires a type-object path for UStruct variables;
		// the legacy short spelling "FVector" asserts in FRigVMExternalVariable integrity checks.
		RigBP->AddMemberVariable(AimTargetName, TBaseStructure<FVector>::Get()->GetPathName(),
			true, false, TEXT("(X=0,Y=10000,Z=0)"));
	}
	if (!HasRigVariable(AimWeightName))
	{
		RigBP->AddMemberVariable(AimWeightName, TEXT("float"), true, false, TEXT("0.0"));
	}

	URigVMGraph* Model = RigBP->GetModel();
	URigVMController* RigController = RigBP->GetOrCreateController(Model);
	if (!Model || !RigController) { return TEXT("ERR: ControlRig model/controller unavailable"); }

	URigVMUnitNode* BeginNode = nullptr;
	for (URigVMNode* Node : Model->GetNodes())
	{
		if (URigVMUnitNode* Unit = Cast<URigVMUnitNode>(Node))
		{
			if (Unit->GetScriptStruct() == FRigUnit_BeginExecution::StaticStruct())
			{
				BeginNode = Unit;
				break;
			}
		}
	}
	if (!BeginNode)
	{
		BeginNode = RigController->AddUnitNode(FRigUnit_BeginExecution::StaticStruct(), TEXT("Execute"),
			FVector2D(-500.f, 0.f), TEXT("ForwardsSolve"), false, false);
	}

	FFocalRigUnit_AimChain AimDefaults;
	AimDefaults.Child.Element = VirtualMuzzleKey;
	AimDefaults.Child.AimMode = EFocalRigAimMode::LocalAxis;
	AimDefaults.Child.LocalAxis = FVector::XAxisVector;
	AimDefaults.bApplyFullRotationToFinalBone = true;
	AimDefaults.AimLockWeight = 0.f;
	AimDefaults.Weight = 1.f;

	FFocalRigAimChainSegment TorsoSegment;
	for (const FName BoneName : { FName(TEXT("spine_01")), FName(TEXT("spine_02")), FName(TEXT("spine_03")) })
	{
		const FRigElementKey BoneKey(BoneName, ERigElementType::Bone);
		if (Hierarchy->Contains(BoneKey)) { TorsoSegment.Bones.Add(BoneKey); }
	}
	if (TorsoSegment.Bones.IsEmpty()) { return TEXT("ERR: no spine_01..spine_03 bones found for FocalRig chain"); }

	const FQuat RootSpineRotation = Hierarchy->GetInitialGlobalTransform(TorsoSegment.Bones[0]).GetRotation();
	auto ClosestLocalAxis = [](const FQuat& LocalToGlobal, const FVector& GlobalDirection)
	{
		const FVector Local = LocalToGlobal.UnrotateVector(GlobalDirection.GetSafeNormal());
		const FVector Abs = Local.GetAbs();
		if (Abs.X >= Abs.Y && Abs.X >= Abs.Z) { return FVector(FMath::Sign(Local.X), 0.f, 0.f); }
		if (Abs.Y >= Abs.Z) { return FVector(0.f, FMath::Sign(Local.Y), 0.f); }
		return FVector(0.f, 0.f, FMath::Sign(Local.Z));
	};
	TorsoSegment.RotationClamp.Mode = EFocalRigRotationClampMode::Euler;
	TorsoSegment.RotationClamp.Space = EFocalRigClampSpace::Global;
	TorsoSegment.RotationClamp.ReferenceFrame = FRotationMatrix::MakeFromZX(
		ClosestLocalAxis(RootSpineRotation, FVector::ZAxisVector),
		ClosestLocalAxis(RootSpineRotation, GetDefault<UFocalRigSettings>()->GlobalForwardAxis)).ToQuat();
	const float BoneCount = static_cast<float>(TorsoSegment.Bones.Num());
	TorsoSegment.RotationClamp.Euler.Pitch = FFloatInterval(-55.f / BoneCount, 55.f / BoneCount);
	TorsoSegment.RotationClamp.Euler.Roll = FFloatInterval(-6.f / BoneCount, 6.f / BoneCount);
	TorsoSegment.RotationClamp.Euler.Yaw = FFloatInterval(-55.f / BoneCount, 55.f / BoneCount);
	TorsoSegment.PreserveUpright.Weight = 0.75f;
	TorsoSegment.RotationFractionPerBone = 0.65f;
	TorsoSegment.Smoothing.bEnabled = false;
	AimDefaults.ChainSegments = { TorsoSegment };

	URigVMUnitNode* AimNode = Cast<URigVMUnitNode>(Model->FindNodeByName(TEXT("FocalAimChain")));
	if (!AimNode)
	{
		AimNode = RigController->AddUnitNode(AimDefaults, TEXT("Execute"), FVector2D(0.f, 0.f),
			TEXT("FocalAimChain"), false, false);
	}
	if (!AimNode) { return TEXT("ERR: failed to add FocalRig Aim Chain unit"); }
	FocalRig::SetPinValue(RigController, AimNode->GetFName(), AimDefaults.Child, &FFocalRigUnit_AimChain::Child);
	FocalRig::SetPinValue(RigController, AimNode->GetFName(), AimDefaults.ChainSegments, &FFocalRigUnit_AimChain::ChainSegments);
	FocalRig::SetPinValue(RigController, AimNode->GetFName(), AimDefaults.bApplyFullRotationToFinalBone, &FFocalRigUnit_AimChain::bApplyFullRotationToFinalBone);
	FocalRig::SetPinValue(RigController, AimNode->GetFName(), AimDefaults.AimLockWeight, &FFocalRigUnit_AimChain::AimLockWeight);

	// Aim Weapon is the final correction. Explicitly configure the virtual muzzle and BOTH arms;
	// FocalRig's automatic setup would otherwise pick the first single-arm candidate on this
	// character-only hierarchy because the real rifle is a separate mesh component.
	FFocalRigUnit_AimWeapon WeaponAimDefaults;
	WeaponAimDefaults.MuzzleAdjustment.Muzzle = AimDefaults.Child;
	WeaponAimDefaults.MuzzleAdjustment.PoseOverride.Weight = 0.f;
	WeaponAimDefaults.MuzzleAdjustment.MuzzleDistance.Smoothing.bEnabled = false;
	WeaponAimDefaults.MuzzleAdjustment.PivotRotation.Pivots =
	{
		FRigElementKey(TEXT("upperarm_r"), ERigElementType::Bone),
		FRigElementKey(TEXT("upperarm_l"), ERigElementType::Bone)
	};
	WeaponAimDefaults.MuzzleAdjustment.PivotRotation.Smoothing.bEnabled = false;
	WeaponAimDefaults.MuzzleAdjustment.AimDownSights.Weight = 0.f;
	WeaponAimDefaults.MuzzleAdjustment.AimDownSights.RotationAroundSightsSmoothing.bEnabled = false;
	WeaponAimDefaults.MuzzleAdjustment.Straighten.Weight = 0.f;
	WeaponAimDefaults.MuzzleAdjustment.BodyDepenetration.Weight = 0.f;
	WeaponAimDefaults.MuzzleAdjustment.WeaponBob.Weight = 0.f;
	WeaponAimDefaults.MuzzleAdjustment.IdleSway.Weight = 0.f;
	WeaponAimDefaults.MuzzleAdjustment.LandingDip.Weight = 0.f;
	WeaponAimDefaults.MuzzleAdjustment.AimLockWeight = 0.f;
	WeaponAimDefaults.Weight = 1.f;

	URigVMUnitNode* WeaponAimNode = Cast<URigVMUnitNode>(Model->FindNodeByName(TEXT("FocalAimWeapon")));
	if (!WeaponAimNode)
	{
		WeaponAimNode = RigController->AddUnitNode(WeaponAimDefaults, TEXT("Execute"), FVector2D(350.f, 0.f),
			TEXT("FocalAimWeapon"), false, false);
	}
	if (!WeaponAimNode) { return TEXT("ERR: failed to add FocalRig Aim Weapon unit"); }
	FocalRig::SetPinValue(RigController, WeaponAimNode->GetFName(), WeaponAimDefaults.MuzzleAdjustment,
		&FFocalRigUnit_AimWeapon::MuzzleAdjustment);
	FocalRig::SetPinValue(RigController, WeaponAimNode->GetFName(), WeaponAimDefaults.ArmAdjustment,
		&FFocalRigUnit_AimWeapon::ArmAdjustment);

	URigVMVariableNode* AimTargetNode = Cast<URigVMVariableNode>(Model->FindNodeByName(TEXT("GetAimTarget")));
	if (!AimTargetNode)
	{
		AimTargetNode = RigController->AddVariableNode(AimTargetName, TEXT("FVector"), TBaseStructure<FVector>::Get(),
			true, TEXT("(X=0,Y=10000,Z=0)"), FVector2D(-350.f, 180.f), TEXT("GetAimTarget"), false, false);
	}
	URigVMVariableNode* AimWeightNode = Cast<URigVMVariableNode>(Model->FindNodeByName(TEXT("GetAimWeight")));
	if (!AimWeightNode)
	{
		AimWeightNode = RigController->AddVariableNode(AimWeightName, TEXT("float"), nullptr,
			true, TEXT("0.0"), FVector2D(-350.f, 300.f), TEXT("GetAimWeight"), false, false);
	}
	if (!AimTargetNode || !AimWeightNode) { return TEXT("ERR: failed to add ControlRig variable getter nodes"); }

	// UE 5.8 renamed the mutable RigVM flow pin to ExecutePin.
	RigController->AddLink(BeginNode->GetNodePath() + TEXT(".ExecutePin"),
		AimNode->GetNodePath() + TEXT(".ExecutePin"), false, false);
	RigController->AddLink(AimNode->GetNodePath() + TEXT(".ExecutePin"),
		WeaponAimNode->GetNodePath() + TEXT(".ExecutePin"), false, false);
	RigController->AddLink(AimTargetNode->GetValuePin()->GetPinPath(),
		AimNode->GetNodePath() + TEXT(".Target"), false, false);
	RigController->AddLink(AimTargetNode->GetValuePin()->GetPinPath(),
		WeaponAimNode->GetNodePath() + TEXT(".Target"), false, false);
	RigController->AddLink(AimWeightNode->GetValuePin()->GetPinPath(),
		AimNode->GetNodePath() + TEXT(".Weight"), false, false);
	RigController->AddLink(AimWeightNode->GetValuePin()->GetPinPath(),
		WeaponAimNode->GetNodePath() + TEXT(".Weight"), false, false);

	RigBP->PropagateHierarchyFromBPToInstances();
	RigBP->RecompileVM();
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(RigBP);
	FKismetEditorUtilities::CompileBlueprint(RigBP);

	UEdGraph* AnimGraph = nullptr;
	TArray<UEdGraph*> Graphs;
	ABP->GetAllGraphs(Graphs);
	for (UEdGraph* Graph : Graphs)
	{
		if (Graph && Graph->GetFName() == FName(TEXT("AnimGraph"))) { AnimGraph = Graph; break; }
	}
	if (!AnimGraph) { return TEXT("ERR: AnimGraph not found"); }

	// Bypass the legacy single-spine correction before adding FocalRig, otherwise both solvers rotate
	// spine_03 and the barrel overshoots. The orphaned editor node is intentionally retained for easy rollback.
	int32 BypassedModifyBones = 0;
	for (UEdGraphNode* GraphNode : AnimGraph->Nodes)
	{
		UAnimGraphNode_ModifyBone* ModifyBone = Cast<UAnimGraphNode_ModifyBone>(GraphNode);
		if (!ModifyBone || !ModifyBone->Node.BoneToModify.BoneName.ToString().StartsWith(TEXT("spine_"))) { continue; }
		UEdGraphPin* InPose = FindPosePin(ModifyBone, EGPD_Input);
		UEdGraphPin* OutPose = FindPosePin(ModifyBone, EGPD_Output);
		if (!InPose || !OutPose || InPose->LinkedTo.Num() != 1 || OutPose->LinkedTo.Num() != 1) { continue; }
		UEdGraphPin* SourcePose = InPose->LinkedTo[0];
		UEdGraphPin* DestPose = OutPose->LinkedTo[0];
		SourcePose->BreakLinkTo(InPose);
		OutPose->BreakLinkTo(DestPose);
		SourcePose->MakeLinkTo(DestPose);
		++BypassedModifyBones;
	}

	const FName ABPAimTargetName(TEXT("FocalAimTarget"));
	const FName ABPAimWeightName(TEXT("FocalAimWeight"));
	FEdGraphPinType VectorType;
	VectorType.PinCategory = UEdGraphSchema_K2::PC_Struct;
	VectorType.PinSubCategoryObject = TBaseStructure<FVector>::Get();
	FBlueprintEditorUtils::AddMemberVariable(ABP, ABPAimTargetName, VectorType);
	FEdGraphPinType FloatType;
	FloatType.PinCategory = UEdGraphSchema_K2::PC_Real;
	FloatType.PinSubCategory = UEdGraphSchema_K2::PC_Float;
	FBlueprintEditorUtils::AddMemberVariable(ABP, ABPAimWeightName, FloatType);

	UAnimGraphNode_Root* RootNode = nullptr;
	UAnimGraphNode_ControlRig* ControlRigNode = nullptr;
	for (UEdGraphNode* GraphNode : AnimGraph->Nodes)
	{
		if (!RootNode) { RootNode = Cast<UAnimGraphNode_Root>(GraphNode); }
		if (!ControlRigNode) { ControlRigNode = Cast<UAnimGraphNode_ControlRig>(GraphNode); }
	}
	if (!RootNode) { return TEXT("ERR: AnimGraph output Root node not found"); }

	const bool bCreatedAnimNode = ControlRigNode == nullptr;
	if (!ControlRigNode)
	{
		FGraphNodeCreator<UAnimGraphNode_ControlRig> Creator(*AnimGraph);
		ControlRigNode = Creator.CreateNode(false);
		ControlRigNode->Node.SetControlRigClass(RigBP->GetControlRigAssetReference().GetBlueprintClass());
		Creator.Finalize();
		ControlRigNode->NodePosX = RootNode->NodePosX - 220;
		ControlRigNode->NodePosY = RootNode->NodePosY;
		ControlRigNode->AddSourceTargetProperties(ABPAimTargetName, AimTargetName);
		ControlRigNode->AddSourceTargetProperties(ABPAimWeightName, AimWeightName);
		ControlRigNode->ReconstructNode();
	}
	else
	{
		ControlRigNode->Node.SetControlRigClass(RigBP->GetControlRigAssetReference().GetBlueprintClass());
		ControlRigNode->ReconstructNode();
	}

	UEdGraphPin* RootIn = FindPosePin(RootNode, EGPD_Input);
	UEdGraphPin* RigIn = FindPosePin(ControlRigNode, EGPD_Input);
	UEdGraphPin* RigOut = FindPosePin(ControlRigNode, EGPD_Output);
	if (!RootIn || !RigIn || !RigOut) { return TEXT("ERR: ControlRig/Root pose pins unresolved"); }
	if (bCreatedAnimNode)
	{
		if (RootIn->LinkedTo.Num() != 1) { return TEXT("ERR: Root input must have exactly one source pose"); }
		UEdGraphPin* SourcePose = RootIn->LinkedTo[0];
		SourcePose->BreakLinkTo(RootIn);
		SourcePose->MakeLinkTo(RigIn);
		RigOut->MakeLinkTo(RootIn);
	}

	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(ABP);
	FKismetEditorUtilities::CompileBlueprint(ABP);
	RigBP->MarkPackageDirty();
	ABP->MarkPackageDirty();
	TArray<UPackage*> PackagesToSave { RigBP->GetOutermost(), ABP->GetOutermost() };
	FEditorFileUtils::PromptForCheckoutAndSave(PackagesToSave, false, false);

	return FString::Printf(TEXT("OK: FocalRig aim installed (rig=%s, virtualMuzzle=%s, spineBones=%d, bypassedModifyBone=%d, animNode=%s)"),
		*RigBP->GetPathName(), *VirtualMuzzleKey.Name.ToString(), TorsoSegment.Bones.Num(), BypassedModifyBones,
		bCreatedAnimNode ? TEXT("created") : TEXT("updated"));
#endif // REDMMO_WITH_MARKETPLACE_FOCALRIG
#else
	return TEXT("ERR: editor-only tool");
#endif // WITH_EDITOR
}

FString URedMMOEditorTools::InstallRifleMovementPoses(
	const FString& AnimBlueprintPath,
	const FString& MovingAimPosePath,
	const FString& JetpackAimPosePath,
	const FString& MovingBoolVarName,
	const FString& JetpackBoolVarName)
{
#if WITH_EDITOR
	UAnimBlueprint* ABP = LoadObject<UAnimBlueprint>(nullptr, *AnimBlueprintPath);
	UAnimSequenceBase* MovingAimAnim = LoadObject<UAnimSequenceBase>(nullptr, *MovingAimPosePath);
	UAnimSequenceBase* JetpackAimAnim = LoadObject<UAnimSequenceBase>(nullptr, *JetpackAimPosePath);
	if (!ABP) { return FString::Printf(TEXT("ERR: AnimBlueprint not found: %s"), *AnimBlueprintPath); }
	if (!MovingAimAnim) { return FString::Printf(TEXT("ERR: moving rifle aim animation not found: %s"), *MovingAimPosePath); }
	if (!JetpackAimAnim) { return FString::Printf(TEXT("ERR: jetpack rifle aim animation not found: %s"), *JetpackAimPosePath); }
	if (ABP->TargetSkeleton && (MovingAimAnim->GetSkeleton() != ABP->TargetSkeleton
		|| JetpackAimAnim->GetSkeleton() != ABP->TargetSkeleton))
	{
		return TEXT("ERR: moving/jetpack rifle animations do not use the AnimBlueprint target skeleton");
	}

	UEdGraph* AnimGraph = nullptr;
	TArray<UEdGraph*> Graphs;
	ABP->GetAllGraphs(Graphs);
	for (UEdGraph* Graph : Graphs)
	{
		if (Graph && Graph->GetFName() == FName(TEXT("AnimGraph"))) { AnimGraph = Graph; break; }
	}
	if (!AnimGraph) { return TEXT("ERR: AnimGraph not found"); }

	// Animation-asset identity is a durable idempotency marker even if the graph has been rearranged.
	bool bHasMovingPlayer = false;
	bool bHasJetpackPlayer = false;
	UAnimGraphNode_Slot* DefaultSlot = nullptr;
	for (UEdGraphNode* GraphNode : AnimGraph->Nodes)
	{
		if (UAnimGraphNode_SequencePlayer* Player = Cast<UAnimGraphNode_SequencePlayer>(GraphNode))
		{
			bHasMovingPlayer |= Player->Node.GetSequence() == MovingAimAnim;
			bHasJetpackPlayer |= Player->Node.GetSequence() == JetpackAimAnim;
		}
		if (UAnimGraphNode_Slot* Slot = Cast<UAnimGraphNode_Slot>(GraphNode))
		{
			if (Slot->Node.SlotName == FName(TEXT("DefaultSlot")))
			{
				DefaultSlot = Slot;
			}
		}
	}
	if (bHasMovingPlayer && bHasJetpackPlayer)
	{
		return TEXT("OK: animated moving/jetpack rifle selectors already present");
	}
	if (bHasMovingPlayer != bHasJetpackPlayer)
	{
		return TEXT("ERR: partial moving/jetpack rifle selector installation detected; inspect AnimGraph before retrying");
	}
	if (!DefaultSlot) { return TEXT("ERR: DefaultSlot node not found"); }

	UEdGraphPin* SlotIn = FindPosePin(DefaultSlot, EGPD_Input);
	if (!SlotIn || SlotIn->LinkedTo.Num() != 1)
	{
		return TEXT("ERR: DefaultSlot source must have exactly one linked pose");
	}
	UEdGraphPin* ExistingStanceOut = SlotIn->LinkedTo[0];

	const FName MovingVarName(*MovingBoolVarName);
	const FName JetpackVarName(*JetpackBoolVarName);
	FEdGraphPinType BoolType;
	BoolType.PinCategory = UEdGraphSchema_K2::PC_Boolean;
	FBlueprintEditorUtils::AddMemberVariable(ABP, MovingVarName, BoolType);
	FBlueprintEditorUtils::AddMemberVariable(ABP, JetpackVarName, BoolType);

	auto AddSequencePlayer = [AnimGraph](UAnimSequenceBase* Animation, const int32 X, const int32 Y)
	{
		FGraphNodeCreator<UAnimGraphNode_SequencePlayer> Creator(*AnimGraph);
		UAnimGraphNode_SequencePlayer* Player = Creator.CreateNode(false);
		Player->Node.SetSequence(Animation);
		Player->Node.SetLoopAnimation(true);
		Creator.Finalize();
		Player->NodePosX = X;
		Player->NodePosY = Y;
		return Player;
	};

	auto AddBoolBlend = [AnimGraph](const int32 X, const int32 Y)
	{
		FGraphNodeCreator<UAnimGraphNode_BlendListByBool> Creator(*AnimGraph);
		UAnimGraphNode_BlendListByBool* Blend = Creator.CreateNode(false);
		Creator.Finalize();
		Blend->NodePosX = X;
		Blend->NodePosY = Y;
		return Blend;
	};

	auto AddBoolGetter = [AnimGraph](const FName VariableName, const int32 X, const int32 Y)
	{
		FGraphNodeCreator<UK2Node_VariableGet> Creator(*AnimGraph);
		UK2Node_VariableGet* Getter = Creator.CreateNode(false);
		Getter->VariableReference.SetSelfMember(VariableName);
		Creator.Finalize();
		Getter->NodePosX = X;
		Getter->NodePosY = Y;
		return Getter;
	};

	const int32 SlotX = DefaultSlot->NodePosX;
	const int32 SlotY = DefaultSlot->NodePosY;
	UAnimGraphNode_SequencePlayer* MovingPlayer = AddSequencePlayer(MovingAimAnim, SlotX - 650, SlotY + 210);
	UAnimGraphNode_BlendListByBool* MovingBlend = AddBoolBlend(SlotX - 430, SlotY + 70);
	UK2Node_VariableGet* MovingGetter = AddBoolGetter(MovingVarName, SlotX - 650, SlotY + 390);
	UAnimGraphNode_SequencePlayer* JetpackPlayer = AddSequencePlayer(JetpackAimAnim, SlotX - 420, SlotY + 300);
	UAnimGraphNode_BlendListByBool* JetpackBlend = AddBoolBlend(SlotX - 210, SlotY + 70);
	UK2Node_VariableGet* JetpackGetter = AddBoolGetter(JetpackVarName, SlotX - 420, SlotY + 480);

	auto ResolveBlendPins = [](UAnimGraphNode_BlendListByBool* Blend, UEdGraphPin*& OutPose,
		UEdGraphPin*& ActiveBool, TArray<UEdGraphPin*>& PoseInputs)
	{
		OutPose = FindPosePin(Blend, EGPD_Output);
		ActiveBool = nullptr;
		PoseInputs.Reset();
		for (UEdGraphPin* Pin : Blend->Pins)
		{
			if (!Pin || Pin->Direction != EGPD_Input) { continue; }
			const UObject* SubCategory = Pin->PinType.PinSubCategoryObject.Get();
			if (SubCategory == FPoseLink::StaticStruct() || SubCategory == FComponentSpacePoseLink::StaticStruct())
			{
				PoseInputs.Add(Pin);
			}
			else if (Pin->PinType.PinCategory == UEdGraphSchema_K2::PC_Boolean)
			{
				ActiveBool = Pin;
			}
		}
		return OutPose && ActiveBool && PoseInputs.Num() >= 2;
	};

	UEdGraphPin* MovingBlendOut = nullptr;
	UEdGraphPin* MovingBoolIn = nullptr;
	TArray<UEdGraphPin*> MovingPoseIns;
	UEdGraphPin* JetpackBlendOut = nullptr;
	UEdGraphPin* JetpackBoolIn = nullptr;
	TArray<UEdGraphPin*> JetpackPoseIns;
	UEdGraphPin* MovingAnimOut = FindPosePin(MovingPlayer, EGPD_Output);
	UEdGraphPin* JetpackAnimOut = FindPosePin(JetpackPlayer, EGPD_Output);
	if (!ResolveBlendPins(MovingBlend, MovingBlendOut, MovingBoolIn, MovingPoseIns)
		|| !ResolveBlendPins(JetpackBlend, JetpackBlendOut, JetpackBoolIn, JetpackPoseIns)
		|| !MovingAnimOut || !JetpackAnimOut)
	{
		return TEXT("ERR: moving/jetpack rifle selector pins could not be resolved");
	}

	UEdGraphPin* MovingBoolOut = MovingGetter->FindPin(MovingVarName, EGPD_Output);
	UEdGraphPin* JetpackBoolOut = JetpackGetter->FindPin(JetpackVarName, EGPD_Output);
	if (!MovingBoolOut || !JetpackBoolOut)
	{
		return TEXT("ERR: moving/jetpack rifle selector variable pins could not be resolved");
	}

	// UE's bool blend deliberately maps TRUE to pose index 0 and FALSE to pose index 1.
	ExistingStanceOut->BreakLinkTo(SlotIn);
	ExistingStanceOut->MakeLinkTo(MovingPoseIns[1]);
	MovingAnimOut->MakeLinkTo(MovingPoseIns[0]);
	MovingBoolOut->MakeLinkTo(MovingBoolIn);
	MovingBlendOut->MakeLinkTo(JetpackPoseIns[1]);
	JetpackAnimOut->MakeLinkTo(JetpackPoseIns[0]);
	JetpackBoolOut->MakeLinkTo(JetpackBoolIn);
	JetpackBlendOut->MakeLinkTo(SlotIn);

	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(ABP);
	FKismetEditorUtilities::CompileBlueprint(ABP);
	ABP->MarkPackageDirty();
	TArray<UPackage*> PackagesToSave { ABP->GetOutermost() };
	FEditorFileUtils::PromptForCheckoutAndSave(PackagesToSave, false, false);

	return FString::Printf(TEXT("OK: animated rifle selectors installed (moving=%s via %s, jetpack=%s via %s, before=%s)"),
		*MovingAimAnim->GetName(), *MovingBoolVarName, *JetpackAimAnim->GetName(), *JetpackBoolVarName,
		*DefaultSlot->Node.SlotName.ToString());
#else
	return TEXT("ERR: editor-only tool");
#endif
}

FString URedMMOEditorTools::InsertAimPoseBlend(const FString& AnimBlueprintPath, const FString& AimPosePath, const FString& RelaxedPosePath, const FString& BoolVarName)
{
#if WITH_EDITOR
	UAnimBlueprint* ABP = LoadObject<UAnimBlueprint>(nullptr, *AnimBlueprintPath);
	if (!ABP) { return FString::Printf(TEXT("ERR: AnimBlueprint not found: %s"), *AnimBlueprintPath); }

	UEdGraph* AnimGraph = nullptr;
	TArray<UEdGraph*> Graphs;
	ABP->GetAllGraphs(Graphs);
	for (UEdGraph* G : Graphs) { if (G && G->GetFName() == FName(TEXT("AnimGraph"))) { AnimGraph = G; break; } }
	if (!AnimGraph) { return TEXT("ERR: AnimGraph not found"); }

	UAnimSequenceBase* AimAnim = LoadObject<UAnimSequenceBase>(nullptr, *AimPosePath);
	UAnimSequenceBase* RelaxedAnim = LoadObject<UAnimSequenceBase>(nullptr, *RelaxedPosePath);
	if (!AimAnim || !RelaxedAnim) { return TEXT("ERR: aim or relaxed pose anim not found"); }

	FObjectProperty* EvalSeqProp = CastField<FObjectProperty>(FAnimNode_SequenceEvaluator::StaticStruct()->FindPropertyByName(TEXT("Sequence")));
	if (!EvalSeqProp) { return TEXT("ERR: SequenceEvaluator Sequence property not found"); }

	// Idempotency: bail if a BlendListByBool is already in the graph.
	for (UEdGraphNode* N : AnimGraph->Nodes)
	{
		if (Cast<UAnimGraphNode_BlendListByBool>(N)) { return TEXT("OK: aim-pose blend already present"); }
	}

	// Find the overlay SeqEvaluator currently playing the aim pose (its output feeds the Layered Blend).
	UAnimGraphNode_SequenceEvaluator* AimSE = nullptr;
	for (UEdGraphNode* N : AnimGraph->Nodes)
	{
		if (UAnimGraphNode_SequenceEvaluator* SE = Cast<UAnimGraphNode_SequenceEvaluator>(N))
		{
			if (Cast<UAnimSequenceBase>(EvalSeqProp->GetObjectPropertyValue_InContainer(&SE->Node)) == AimAnim) { AimSE = SE; break; }
		}
	}
	if (!AimSE) { return TEXT("ERR: overlay SeqEvaluator playing the aim pose not found (run SetAnimGraphSequence to set it first)"); }

	UEdGraphPin* AimOut = FindPosePin(AimSE, EGPD_Output);
	if (!AimOut || AimOut->LinkedTo.Num() == 0) { return TEXT("ERR: aim SeqEval output not linked to the overlay"); }
	UEdGraphPin* OverlayIn = AimOut->LinkedTo[0];   // the LayeredBlend BlendPoses_0 pin

	// New bool member variable that selects the stance.
	const FName VN(*BoolVarName);
	FEdGraphPinType BoolType; BoolType.PinCategory = UEdGraphSchema_K2::PC_Boolean;
	FBlueprintEditorUtils::AddMemberVariable(ABP, VN, BoolType);

	// New SeqEvaluator for the relaxed carry pose.
	FGraphNodeCreator<UAnimGraphNode_SequenceEvaluator> RelaxCreator(*AnimGraph);
	UAnimGraphNode_SequenceEvaluator* RelaxedSE = RelaxCreator.CreateNode(false);
	EvalSeqProp->SetObjectPropertyValue_InContainer(&RelaxedSE->Node, RelaxedAnim);
	RelaxCreator.Finalize();
	RelaxedSE->NodePosX = AimSE->NodePosX; RelaxedSE->NodePosY = AimSE->NodePosY + 170;

	// Blend Poses by bool.
	FGraphNodeCreator<UAnimGraphNode_BlendListByBool> BlendCreator(*AnimGraph);
	UAnimGraphNode_BlendListByBool* Blend = BlendCreator.CreateNode(false);
	BlendCreator.Finalize();
	Blend->NodePosX = AimSE->NodePosX + 250; Blend->NodePosY = AimSE->NodePosY + 70;

	// Getter for the bool.
	FGraphNodeCreator<UK2Node_VariableGet> VGCreator(*AnimGraph);
	UK2Node_VariableGet* VG = VGCreator.CreateNode(false);
	VG->VariableReference.SetSelfMember(VN);
	VGCreator.Finalize();
	VG->NodePosX = Blend->NodePosX - 200; VG->NodePosY = Blend->NodePosY + 120;

	// Discover the blend's pins by type (pose inputs in order = index 0 [true] then 1 [false]).
	UEdGraphPin* BlendOut = FindPosePin(Blend, EGPD_Output);
	UEdGraphPin* BoolIn = nullptr;
	TArray<UEdGraphPin*> PoseIns;
	for (UEdGraphPin* P : Blend->Pins)
	{
		if (!P || P->Direction != EGPD_Input) { continue; }
		const UObject* Sub = P->PinType.PinSubCategoryObject.Get();
		if (Sub == FPoseLink::StaticStruct() || Sub == FComponentSpacePoseLink::StaticStruct()) { PoseIns.Add(P); }
		else if (P->PinType.PinCategory == UEdGraphSchema_K2::PC_Boolean) { BoolIn = P; }
	}
	if (!BlendOut || PoseIns.Num() < 2 || !BoolIn)
	{
		return FString::Printf(TEXT("ERR: blend pins not resolved (out=%d poseIns=%d bool=%d)"), BlendOut ? 1 : 0, PoseIns.Num(), BoolIn ? 1 : 0);
	}

	// Rewire: aim -> blend.true(0), relaxed -> blend.false(1), bool -> active, blend -> overlay.
	AimOut->BreakLinkTo(OverlayIn);
	AimOut->MakeLinkTo(PoseIns[0]);
	if (UEdGraphPin* RelaxedOut = FindPosePin(RelaxedSE, EGPD_Output)) { RelaxedOut->MakeLinkTo(PoseIns[1]); }
	if (UEdGraphPin* VGOut = VG->FindPin(VN, EGPD_Output)) { VGOut->MakeLinkTo(BoolIn); }
	BlendOut->MakeLinkTo(OverlayIn);

	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(ABP);
	FKismetEditorUtilities::CompileBlueprint(ABP);

	return FString::Printf(TEXT("OK: aim-pose blend in. true(aim)=%s false(relaxed)=%s bool='%s'"), *AimAnim->GetName(), *RelaxedAnim->GetName(), *BoolVarName);
#else
	return TEXT("ERR: editor-only tool");
#endif
}

FString URedMMOEditorTools::InsertRifleOverlay(const FString& AnimBlueprintPath, const FString& OverlayPosePath, const FString& BranchBone)
{
#if WITH_EDITOR
	UAnimBlueprint* ABP = LoadObject<UAnimBlueprint>(nullptr, *AnimBlueprintPath);
	if (!ABP) { return FString::Printf(TEXT("ERR: AnimBlueprint not found: %s"), *AnimBlueprintPath); }

	UEdGraph* AnimGraph = nullptr;
	TArray<UEdGraph*> Graphs;
	ABP->GetAllGraphs(Graphs);
	for (UEdGraph* G : Graphs) { if (G && G->GetFName() == FName(TEXT("AnimGraph"))) { AnimGraph = G; break; } }
	if (!AnimGraph) { return TEXT("ERR: AnimGraph not found"); }

	// Idempotent: bail if an overlay is already present.
	for (UEdGraphNode* N : AnimGraph->Nodes) { if (Cast<UAnimGraphNode_LayeredBoneBlend>(N)) { return TEXT("OK: rifle overlay already present"); } }

	UAnimSequenceBase* OverlayAnim = LoadObject<UAnimSequenceBase>(nullptr, *OverlayPosePath);
	if (!OverlayAnim) { return FString::Printf(TEXT("ERR: overlay pose not found: %s"), *OverlayPosePath); }

	// Root (Output Pose) and the locomotion pose currently feeding it.
	UAnimGraphNode_Root* Root = nullptr;
	for (UEdGraphNode* N : AnimGraph->Nodes) { if (UAnimGraphNode_Root* R = Cast<UAnimGraphNode_Root>(N)) { Root = R; break; } }
	if (!Root) { return TEXT("ERR: Root (Output Pose) node not found"); }
	UEdGraphPin* RootIn = FindPosePin(Root, EGPD_Input);
	if (!RootIn || RootIn->LinkedTo.Num() == 0) { return TEXT("ERR: Root input not linked"); }
	UEdGraphPin* SrcOut = RootIn->LinkedTo[0];   // locomotion state-machine output (local space)

	// Overlay SequenceEvaluator holding the rifle pose (a single frame = a static upper-body pose).
	FObjectProperty* EvalSeqProp = CastField<FObjectProperty>(FAnimNode_SequenceEvaluator::StaticStruct()->FindPropertyByName(TEXT("Sequence")));
	FGraphNodeCreator<UAnimGraphNode_SequenceEvaluator> SECreator(*AnimGraph);
	UAnimGraphNode_SequenceEvaluator* SE = SECreator.CreateNode(false);
	if (EvalSeqProp) { EvalSeqProp->SetObjectPropertyValue_InContainer(&SE->Node, OverlayAnim); }
	SECreator.Finalize();
	SE->NodePosX = Root->NodePosX - 520; SE->NodePosY = Root->NodePosY + 240;

	// Layered Blend Per Bone: one overlay layer branching at BranchBone (upper body only).
	FGraphNodeCreator<UAnimGraphNode_LayeredBoneBlend> LBBCreator(*AnimGraph);
	UAnimGraphNode_LayeredBoneBlend* LBB = LBBCreator.CreateNode(false);
	LBB->Node.LayerSetup.SetNum(1);
	LBB->Node.LayerSetup[0].BranchFilters.SetNum(1);
	LBB->Node.LayerSetup[0].BranchFilters[0].BoneName = FName(*BranchBone);
	LBB->Node.LayerSetup[0].BranchFilters[0].BlendDepth = 4;
	LBB->Node.BlendPoses.SetNum(1);
	LBB->Node.BlendWeights.SetNum(1);
	LBB->Node.BlendWeights[0] = 1.f;
	LBBCreator.Finalize();
	LBB->NodePosX = Root->NodePosX - 340; LBB->NodePosY = Root->NodePosY + 40;
	LBB->ReconstructNode();   // regenerate BasePose / BlendPoses_0 / BlendWeights_0 pins

	// Local<->Component passthrough tail so AddAimModifyBone has a ComponentToLocal->Root to splice into.
	FGraphNodeCreator<UAnimGraphNode_LocalToComponentSpace> L2CCreator(*AnimGraph);
	UAnimGraphNode_LocalToComponentSpace* L2C = L2CCreator.CreateNode(false);
	L2CCreator.Finalize();
	L2C->NodePosX = Root->NodePosX - 200; L2C->NodePosY = Root->NodePosY;

	FGraphNodeCreator<UAnimGraphNode_ComponentToLocalSpace> C2LCreator(*AnimGraph);
	UAnimGraphNode_ComponentToLocalSpace* C2L = C2LCreator.CreateNode(false);
	C2LCreator.Finalize();
	C2L->NodePosX = Root->NodePosX - 70; C2L->NodePosY = Root->NodePosY;

	// Resolve pins.
	UEdGraphPin* BaseIn = LBB->FindPin(FName(TEXT("BasePose")), EGPD_Input);
	UEdGraphPin* OverlayIn = LBB->FindPin(FName(TEXT("BlendPoses_0")), EGPD_Input);
	UEdGraphPin* LBBOut = FindPosePin(LBB, EGPD_Output);
	UEdGraphPin* SEOut = FindPosePin(SE, EGPD_Output);
	UEdGraphPin* L2CIn = FindPosePin(L2C, EGPD_Input);
	UEdGraphPin* L2COut = FindPosePin(L2C, EGPD_Output);
	UEdGraphPin* C2LIn = FindPosePin(C2L, EGPD_Input);
	UEdGraphPin* C2LOut = FindPosePin(C2L, EGPD_Output);
	if (!BaseIn || !OverlayIn || !LBBOut || !SEOut || !L2CIn || !L2COut || !C2LIn || !C2LOut)
	{
		return FString::Printf(TEXT("ERR: overlay pins not resolved (base=%d overlay=%d lbbOut=%d seOut=%d)"),
			BaseIn ? 1 : 0, OverlayIn ? 1 : 0, LBBOut ? 1 : 0, SEOut ? 1 : 0);
	}

	// Wire: locomotion -> LBB.base ; overlay -> LBB.blend0 ; LBB -> L2C -> C2L -> Root.
	SrcOut->BreakLinkTo(RootIn);
	SrcOut->MakeLinkTo(BaseIn);
	SEOut->MakeLinkTo(OverlayIn);
	LBBOut->MakeLinkTo(L2CIn);
	L2COut->MakeLinkTo(C2LIn);
	C2LOut->MakeLinkTo(RootIn);

	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(ABP);
	FKismetEditorUtilities::CompileBlueprint(ABP);
	return FString::Printf(TEXT("OK: rifle overlay inserted (branch=%s, pose=%s)"), *BranchBone, *OverlayAnim->GetName());
#else
	return TEXT("ERR: editor-only tool");
#endif
}

FString URedMMOEditorTools::DriveOverlayWeightByVar(const FString& AnimBlueprintPath, const FString& VarName)
{
#if WITH_EDITOR
	UAnimBlueprint* ABP = LoadObject<UAnimBlueprint>(nullptr, *AnimBlueprintPath);
	if (!ABP) { return FString::Printf(TEXT("ERR: AnimBlueprint not found: %s"), *AnimBlueprintPath); }

	UEdGraph* AnimGraph = nullptr;
	TArray<UEdGraph*> Graphs;
	ABP->GetAllGraphs(Graphs);
	for (UEdGraph* G : Graphs) { if (G && G->GetFName() == FName(TEXT("AnimGraph"))) { AnimGraph = G; break; } }
	if (!AnimGraph) { return TEXT("ERR: AnimGraph not found"); }

	UAnimGraphNode_LayeredBoneBlend* LBB = nullptr;
	for (UEdGraphNode* N : AnimGraph->Nodes) { if (UAnimGraphNode_LayeredBoneBlend* L = Cast<UAnimGraphNode_LayeredBoneBlend>(N)) { LBB = L; break; } }
	if (!LBB) { return TEXT("ERR: LayeredBoneBlend node not found"); }

	UEdGraphPin* WeightPin = LBB->FindPin(FName(TEXT("BlendWeights_0")), EGPD_Input);
	if (!WeightPin)
	{
		for (UEdGraphPin* P : LBB->Pins)
		{
			if (P && P->Direction == EGPD_Input && P->PinType.PinCategory == UEdGraphSchema_K2::PC_Real)
			{
				WeightPin = P; break;
			}
		}
	}
	if (!WeightPin) { return TEXT("ERR: LBB overlay weight (BlendWeights_0) pin not found"); }
	if (WeightPin->LinkedTo.Num() > 0) { return TEXT("OK: overlay weight already driven"); }

	const FName VN(*VarName);
	FEdGraphPinType FloatType;
	FloatType.PinCategory = UEdGraphSchema_K2::PC_Real;
	FloatType.PinSubCategory = UEdGraphSchema_K2::PC_Float;
	FBlueprintEditorUtils::AddMemberVariable(ABP, VN, FloatType);

	FGraphNodeCreator<UK2Node_VariableGet> VGCreator(*AnimGraph);
	UK2Node_VariableGet* VG = VGCreator.CreateNode(false);
	VG->VariableReference.SetSelfMember(VN);
	VGCreator.Finalize();
	VG->NodePosX = LBB->NodePosX - 320; VG->NodePosY = LBB->NodePosY + 220;

	UEdGraphPin* VGOut = VG->FindPin(VN, EGPD_Output);
	FString WireNote = TEXT("var unwired");
	if (VGOut) { VGOut->MakeLinkTo(WeightPin); WireNote = TEXT("wired"); }

	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(ABP);
	FKismetEditorUtilities::CompileBlueprint(ABP);
	return FString::Printf(TEXT("OK: overlay weight (pin '%s') driven by var '%s' (%s)"), *WeightPin->PinName.ToString(), *VarName, *WireNote);
#else
	return TEXT("ERR: editor-only tool");
#endif
}

#if WITH_EDITOR
namespace
{
// Walk a struct's properties for asset references (blendspaces, sequences, meshes...), one
// recursion level into nested structs — covers FAnimNode_* payloads inside UAnimGraphNode_*.
void RedCollectAssetRefsFromStruct(const UScriptStruct* Struct, const void* Ptr, TSet<FString>& Out, int32 Depth)
{
	if (!Struct || !Ptr || Depth > 2)
	{
		return;
	}
	for (TFieldIterator<FProperty> It(Struct); It; ++It)
	{
		if (const FObjectPropertyBase* ObjProp = CastField<FObjectPropertyBase>(*It))
		{
			if (const UObject* Value = ObjProp->GetObjectPropertyValue_InContainer(Ptr))
			{
				if (Value->IsAsset())
				{
					Out.Add(Value->GetPathName());
				}
			}
		}
		else if (const FStructProperty* StructProp = CastField<FStructProperty>(*It))
		{
			RedCollectAssetRefsFromStruct(StructProp->Struct, StructProp->ContainerPtrToValuePtr<void>(Ptr), Out, Depth + 1);
		}
	}
}

void RedCollectAssetRefsFromNode(const UEdGraphNode* Node, TSet<FString>& Out)
{
	for (TFieldIterator<FProperty> It(Node->GetClass()); It; ++It)
	{
		if (const FObjectPropertyBase* ObjProp = CastField<FObjectPropertyBase>(*It))
		{
			if (const UObject* Value = ObjProp->GetObjectPropertyValue_InContainer(Node))
			{
				if (Value->IsAsset())
				{
					Out.Add(Value->GetPathName());
				}
			}
		}
		else if (const FStructProperty* StructProp = CastField<FStructProperty>(*It))
		{
			RedCollectAssetRefsFromStruct(StructProp->Struct, StructProp->ContainerPtrToValuePtr<void>(Node), Out, 1);
		}
	}
}
}
#endif

FString URedMMOEditorTools::DumpBlueprintGraphs(const FString& BlueprintPath, bool bIncludePinDetails)
{
#if WITH_EDITOR
	UBlueprint* BP = LoadObject<UBlueprint>(nullptr, *BlueprintPath);
	if (!BP)
	{
		return FString::Printf(TEXT("ERR: blueprint not found: %s"), *BlueprintPath);
	}

	TArray<UEdGraph*> Graphs;
	BP->GetAllGraphs(Graphs);

	TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetStringField(TEXT("blueprint"), BlueprintPath);
	Root->SetStringField(TEXT("parent_class"), GetNameSafe(BP->ParentClass));
	Root->SetNumberField(TEXT("graph_count"), Graphs.Num());

	TArray<TSharedPtr<FJsonValue>> GraphArr;
	for (UEdGraph* Graph : Graphs)
	{
		if (!Graph)
		{
			continue;
		}
		TSharedRef<FJsonObject> GraphJson = MakeShared<FJsonObject>();
		GraphJson->SetStringField(TEXT("name"), Graph->GetName());
		GraphJson->SetStringField(TEXT("outer"), GetNameSafe(Graph->GetOuter()));

		TArray<TSharedPtr<FJsonValue>> NodeArr;
		for (UEdGraphNode* Node : Graph->Nodes)
		{
			if (!Node)
			{
				continue;
			}
			TSharedRef<FJsonObject> NodeJson = MakeShared<FJsonObject>();
			NodeJson->SetStringField(TEXT("id"), Node->NodeGuid.ToString(EGuidFormats::Digits));
			NodeJson->SetStringField(TEXT("class"), Node->GetClass()->GetName());
			NodeJson->SetStringField(TEXT("title"), Node->GetNodeTitle(ENodeTitleType::ListView).ToString());

			// Full property export (capped): exposes what pin links can't show — property-access
			// BINDINGS (variable -> anim node pin), state-machine payloads, literals in maps/arrays.
			{
				TSharedRef<FJsonObject> PropsJson = MakeShared<FJsonObject>();
				int32 PropCount = 0;
				for (TFieldIterator<FProperty> It(Node->GetClass()); It && PropCount < 24; ++It)
				{
					const FProperty* Prop = *It;
					const FString PName = Prop->GetName();
					if (PName.StartsWith(TEXT("NodePos")) || PName == TEXT("NodeGuid") || PName == TEXT("NodeComment")
						|| PName == TEXT("Pins") || PName == TEXT("ErrorMsg") || PName == TEXT("AdvancedPinDisplay")
						|| PName == TEXT("NodeWidth") || PName == TEXT("NodeHeight") || PName == TEXT("EnabledState"))
					{
						continue;
					}
					FString Exported;
					Prop->ExportTextItem_Direct(Exported, Prop->ContainerPtrToValuePtr<void>(Node), nullptr, nullptr, PPF_None);
					if (Exported.IsEmpty() || Exported == TEXT("()") || Exported == TEXT("False") || Exported == TEXT("0"))
					{
						continue;
					}
					if (Exported.Len() > 400)
					{
						Exported = Exported.Left(400) + TEXT("...");
					}
					PropsJson->SetStringField(PName, Exported);
					++PropCount;
				}
				if (PropsJson->Values.Num())
				{
					NodeJson->SetObjectField(TEXT("props"), PropsJson);
				}
			}

			TSet<FString> AssetRefs;
			RedCollectAssetRefsFromNode(Node, AssetRefs);
			if (AssetRefs.Num())
			{
				TArray<TSharedPtr<FJsonValue>> AssetArr;
				for (const FString& Path : AssetRefs)
				{
					AssetArr.Add(MakeShared<FJsonValueString>(Path));
				}
				NodeJson->SetArrayField(TEXT("assets"), AssetArr);
			}

			if (bIncludePinDetails)
			{
				TArray<TSharedPtr<FJsonValue>> PinArr;
				for (const UEdGraphPin* Pin : Node->Pins)
				{
					if (!Pin)
					{
						continue;
					}
					TSharedRef<FJsonObject> PinJson = MakeShared<FJsonObject>();
					PinJson->SetStringField(TEXT("name"), Pin->PinName.ToString());
					PinJson->SetStringField(TEXT("dir"), Pin->Direction == EGPD_Input ? TEXT("in") : TEXT("out"));
					FString TypeStr = Pin->PinType.PinCategory.ToString();
					if (const UObject* SubObj = Pin->PinType.PinSubCategoryObject.Get())
					{
						TypeStr += TEXT(":") + SubObj->GetName();
					}
					PinJson->SetStringField(TEXT("type"), TypeStr);
					if (!Pin->DefaultValue.IsEmpty())
					{
						PinJson->SetStringField(TEXT("default"), Pin->DefaultValue);
					}
					if (Pin->DefaultObject)
					{
						PinJson->SetStringField(TEXT("default_object"), Pin->DefaultObject->GetPathName());
					}
					if (Pin->LinkedTo.Num())
					{
						TArray<TSharedPtr<FJsonValue>> LinkArr;
						for (const UEdGraphPin* Linked : Pin->LinkedTo)
						{
							if (Linked && Linked->GetOwningNode())
							{
								LinkArr.Add(MakeShared<FJsonValueString>(
									Linked->GetOwningNode()->NodeGuid.ToString(EGuidFormats::Digits) + TEXT(":") + Linked->PinName.ToString()));
							}
						}
						PinJson->SetArrayField(TEXT("links"), LinkArr);
					}
					PinArr.Add(MakeShared<FJsonValueObject>(PinJson));
				}
				NodeJson->SetArrayField(TEXT("pins"), PinArr);
			}
			NodeArr.Add(MakeShared<FJsonValueObject>(NodeJson));
		}
		GraphJson->SetArrayField(TEXT("nodes"), NodeArr);
		GraphArr.Add(MakeShared<FJsonValueObject>(GraphJson));
	}
	Root->SetArrayField(TEXT("graphs"), GraphArr);

	FString Out;
	const TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Writer =
		TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Out);
	FJsonSerializer::Serialize(Root, Writer);
	return Out;
#else
	return TEXT("ERR: editor-only");
#endif
}

FString URedMMOEditorTools::ImportPlanetGenMacroHeightfield(
	const FString& SourceDirectory,
	const FString& AssetPackagePath)
{
#if WITH_EDITOR
#if !REDMMO_HAS_PLANETGEN_MACROHEIGHTFIELD
	return TEXT("ERR: PlanetGen MacroHeightfield fork API absent; restore Plugins/PlanetGenPinned_* with PlanetGenMacroHeightfieldAsset.h, then retry");
#else
	if (!IsInGameThread())
	{
		return TEXT("ERR: macro heightfield import must run on the editor game thread");
	}

	FString SourceRoot = SourceDirectory.TrimStartAndEnd();
	if (SourceRoot.IsEmpty())
	{
		return TEXT("ERR: source directory is empty");
	}
	SourceRoot = FPaths::IsRelative(SourceRoot)
		? FPaths::ConvertRelativePathToFull(FPaths::ProjectDir(), SourceRoot)
		: FPaths::ConvertRelativePathToFull(SourceRoot);
	FPaths::NormalizeDirectoryName(SourceRoot);
	FPaths::CollapseRelativeDirectories(SourceRoot);
	if (!IFileManager::Get().DirectoryExists(*SourceRoot))
	{
		return FString::Printf(TEXT("ERR: source directory not found: %s"), *SourceRoot);
	}

	const FString ManifestPath = FPaths::Combine(SourceRoot, TEXT("RED_MacroWorld.json"));
	FString ManifestText;
	if (!FFileHelper::LoadFileToString(ManifestText, *ManifestPath))
	{
		return FString::Printf(TEXT("ERR: manifest not found or unreadable: %s"), *ManifestPath);
	}

	TSharedPtr<FJsonObject> Manifest;
	const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ManifestText);
	if (!FJsonSerializer::Deserialize(Reader, Manifest) || !Manifest.IsValid())
	{
		return FString::Printf(TEXT("ERR: invalid JSON manifest: %s"), *ManifestPath);
	}
	auto IsCanonicalSha256 = [](const FString& Value)
	{
		if (Value.Len() != 64 || Value != Value.ToUpper())
		{
			return false;
		}
		for (int32 Index = 0; Index < Value.Len(); ++Index)
		{
			const TCHAR Character = Value[Index];
			if (!FChar::IsHexDigit(Character))
			{
				return false;
			}
		}
		return true;
	};

	FString Schema;
	FString HeightEncoding;
	FString RawEncoding;
	FString DeclaredDatasetSha256;
	FString DeclaredPatchDatasetSha256;
	int32 Resolution = 0;
	double MinHeightCm64 = 0.0;
	double MaxHeightCm64 = 0.0;
	if (!Manifest->TryGetStringField(TEXT("schema"), Schema)
		|| Schema != TEXT("redmmotitan.macro_planet_faces.v1"))
	{
		return FString::Printf(TEXT("ERR: unsupported or missing manifest schema: %s"), *Schema);
	}
	if (!Manifest->TryGetStringField(TEXT("height_encoding"), HeightEncoding)
		|| HeightEncoding != TEXT("unsigned 16-bit normalized"))
	{
		return FString::Printf(TEXT("ERR: unsupported or missing height_encoding: %s"), *HeightEncoding);
	}
	if (!Manifest->TryGetStringField(TEXT("raw_height_encoding"), RawEncoding)
		|| RawEncoding != TEXT("little-endian unsigned 16-bit row-major"))
	{
		return FString::Printf(TEXT("ERR: unsupported or missing raw_height_encoding: %s"), *RawEncoding);
	}
	if (!Manifest->TryGetStringField(TEXT("raster_dataset_sha256"), DeclaredDatasetSha256)
		|| !IsCanonicalSha256(DeclaredDatasetSha256))
	{
		return TEXT("ERR: manifest must contain a canonical uppercase raster_dataset_sha256");
	}
	// This UFUNCTION is callable without the Python orchestration layer, so the approved raster
	// root must be pinned here as well. Manifest-owned per-file hashes alone only prove internal
	// consistency: a modified manifest could otherwise approve an arbitrary replacement dataset.
	static constexpr const TCHAR* ApprovedDatasetSha256 =
		TEXT("AAE25CCA654D3D966C7AE3C5A00A911BA2576E67592D5B1443D9145D0BC2399A");
	static constexpr const TCHAR* ApprovedPatchDatasetSha256 =
		TEXT("228E1CDAC65F0AFFB51101E8639AC65C57063FC4C72D74588D24A194A87504ED");
	if (DeclaredDatasetSha256 != ApprovedDatasetSha256)
	{
		return FString::Printf(
			TEXT("ERR: raster dataset is not the approved 50 km face bake (expected %s, manifest=%s)"),
			ApprovedDatasetSha256, *DeclaredDatasetSha256);
	}
	if (!Manifest->TryGetStringField(
			TEXT("source_patch_raster_dataset_sha256"), DeclaredPatchDatasetSha256)
		|| !IsCanonicalSha256(DeclaredPatchDatasetSha256)
		|| DeclaredPatchDatasetSha256 != ApprovedPatchDatasetSha256)
	{
		return FString::Printf(
			TEXT("ERR: faces are not declared from the approved 27-patch dataset (expected %s, manifest=%s)"),
			ApprovedPatchDatasetSha256, *DeclaredPatchDatasetSha256);
	}
	const TSharedPtr<FJsonObject>* BiomeChannels = nullptr;
	FString DesertChannel;
	FString TemperateChannel;
	FString ColdChannel;
	FString AlienChannel;
	if (!Manifest->TryGetObjectField(TEXT("biome_channels"), BiomeChannels)
		|| !BiomeChannels || !BiomeChannels->IsValid()
		|| !(*BiomeChannels)->TryGetStringField(TEXT("r"), DesertChannel)
		|| !(*BiomeChannels)->TryGetStringField(TEXT("g"), TemperateChannel)
		|| !(*BiomeChannels)->TryGetStringField(TEXT("b"), ColdChannel)
		|| !(*BiomeChannels)->TryGetStringField(TEXT("a"), AlienChannel)
		|| DesertChannel != TEXT("desert")
		|| TemperateChannel != TEXT("temperate")
		|| ColdChannel != TEXT("cold_or_mountain")
		|| AlienChannel != TEXT("alien"))
	{
		return TEXT("ERR: biome_channels must map RGBA exactly to desert/temperate/cold_or_mountain/alien");
	}
	if (!Manifest->TryGetNumberField(TEXT("resolution"), Resolution)
		|| !Manifest->TryGetNumberField(TEXT("min_height_cm"), MinHeightCm64)
		|| !Manifest->TryGetNumberField(TEXT("max_height_cm"), MaxHeightCm64))
	{
		return TEXT("ERR: manifest must contain numeric resolution/min_height_cm/max_height_cm");
	}
	const float MinHeightCm = static_cast<float>(MinHeightCm64);
	const float MaxHeightCm = static_cast<float>(MaxHeightCm64);
	// The approved bake is exactly 257x257 with a fixed decode range. Pinning these semantics is
	// as important as pinning the raster digest: changing only the manifest range would otherwise
	// reinterpret authenticated uint16 samples as different terrain heights.
	if (Resolution != 257
		|| MinHeightCm64 != -30000.0 || MaxHeightCm64 != 30000.0
		|| !FMath::IsFinite(MinHeightCm64) || !FMath::IsFinite(MaxHeightCm64)
		|| !FMath::IsFinite(MinHeightCm) || !FMath::IsFinite(MaxHeightCm)
		|| MaxHeightCm <= MinHeightCm)
	{
		return FString::Printf(
			TEXT("ERR: invalid manifest dimensions/decode range (resolution=%d, min=%g, max=%g)"),
			Resolution, MinHeightCm64, MaxHeightCm64);
	}

	const TSharedPtr<FJsonObject>* SeamValidation = nullptr;
	bool bSeamValidationPassed = false;
	if (!Manifest->TryGetObjectField(TEXT("seam_validation"), SeamValidation)
		|| !SeamValidation || !SeamValidation->IsValid()
		|| !(*SeamValidation)->TryGetBoolField(TEXT("passed"), bSeamValidationPassed)
		|| !bSeamValidationPassed)
	{
		return TEXT("ERR: manifest does not record a passing cube-face seam validation");
	}

	const int64 SampleCount64 = static_cast<int64>(Resolution) * Resolution;
	const int64 ByteCount64 = SampleCount64 * static_cast<int64>(sizeof(uint16));
	if (SampleCount64 > MAX_int32 || ByteCount64 > MAX_int32)
	{
		return TEXT("ERR: macro heightfield resolution exceeds supported in-memory array size");
	}
	const int32 SampleCount = static_cast<int32>(SampleCount64);
	const int32 ByteCount = static_cast<int32>(ByteCount64);
	const int32 ExpectedBoundaryComparisons = 12 * Resolution - 8;
	const int32 ExpectedUniqueBoundarySamples = 12 * Resolution - 16;
	bool bValidatedFromPersistedFiles = false;
	int32 RecordedComparisons = 0;
	int32 RecordedExpectedComparisons = 0;
	int32 RecordedUniqueBoundarySamples = 0;
	int32 RecordedMaxHeightDelta = -1;
	int32 RecordedMaxLandDelta = -1;
	int32 RecordedMaxBiomeDelta = -1;
	if (!(*SeamValidation)->TryGetBoolField(
			TEXT("validated_from_persisted_files"), bValidatedFromPersistedFiles)
		|| !bValidatedFromPersistedFiles
		|| !(*SeamValidation)->TryGetNumberField(
			TEXT("shared_boundary_comparisons"), RecordedComparisons)
		|| !(*SeamValidation)->TryGetNumberField(
			TEXT("expected_shared_boundary_comparisons"), RecordedExpectedComparisons)
		|| !(*SeamValidation)->TryGetNumberField(
			TEXT("unique_boundary_samples"), RecordedUniqueBoundarySamples)
		|| !(*SeamValidation)->TryGetNumberField(
			TEXT("max_height_delta_u16"), RecordedMaxHeightDelta)
		|| !(*SeamValidation)->TryGetNumberField(
			TEXT("max_land_delta_u8"), RecordedMaxLandDelta)
		|| !(*SeamValidation)->TryGetNumberField(
			TEXT("max_biome_delta_u8"), RecordedMaxBiomeDelta)
		|| RecordedComparisons != ExpectedBoundaryComparisons
		|| RecordedExpectedComparisons != ExpectedBoundaryComparisons
		|| RecordedUniqueBoundarySamples != ExpectedUniqueBoundarySamples
		|| RecordedMaxHeightDelta != 0
		|| RecordedMaxLandDelta != 0
		|| RecordedMaxBiomeDelta != 0)
	{
		return TEXT("ERR: manifest seam_validation does not match the exact persisted zero-delta cube contract");
	}

	const TSharedPtr<FJsonObject>* CoverageValidation = nullptr;
	bool bCoveragePassed = false;
	int32 RecordedFaceSampleCount = 0;
	int32 RecordedUncoveredSamples = -1;
	if (!Manifest->TryGetObjectField(TEXT("coverage_validation"), CoverageValidation)
		|| !CoverageValidation || !CoverageValidation->IsValid()
		|| !(*CoverageValidation)->TryGetBoolField(TEXT("passed"), bCoveragePassed)
		|| !bCoveragePassed
		|| !(*CoverageValidation)->TryGetNumberField(
			TEXT("face_sample_count"), RecordedFaceSampleCount)
		|| !(*CoverageValidation)->TryGetNumberField(
			TEXT("uncovered_samples"), RecordedUncoveredSamples)
		|| RecordedFaceSampleCount != SampleCount * PlanetGenMacroCubeFaceCount
		|| RecordedUncoveredSamples != 0)
	{
		return TEXT("ERR: manifest coverage_validation does not cover every cube-face sample");
	}

	static const TCHAR* FaceNames[PlanetGenMacroCubeFaceCount] =
	{
		TEXT("PX"), TEXT("NX"), TEXT("PY"), TEXT("NY"), TEXT("PZ"), TEXT("NZ")
	};
	const TArray<TSharedPtr<FJsonValue>>* ManifestFaces = nullptr;
	if (!Manifest->TryGetArrayField(TEXT("faces"), ManifestFaces)
		|| !ManifestFaces || ManifestFaces->Num() != PlanetGenMacroCubeFaceCount)
	{
		return TEXT("ERR: manifest must describe exactly six cube faces");
	}
	struct FManifestFaceInputs
	{
		FString HeightPngFilename;
		FString RawHeightFilename;
		FString LandFilename;
		FString BiomeFilename;
		FString HeightPngSha256;
		FString RawHeightSha256;
		FString LandSha256;
		FString BiomeSha256;
	};
	struct FDatasetHashEntry
	{
		FString Filename;
		FString Sha256;
	};
	TStaticArray<FManifestFaceInputs, PlanetGenMacroCubeFaceCount> FaceInputs;
	TArray<FDatasetHashEntry> DatasetHashEntries;
	DatasetHashEntries.Reserve(PlanetGenMacroCubeFaceCount * 4);

	auto ReadManifestFileRecord = [&IsCanonicalSha256](
		const TSharedPtr<FJsonObject>& FilesObject,
		const TCHAR* Role,
		const FString& ExpectedFilename,
		const TCHAR* ExpectedEncoding,
		FString& OutSha256,
		FString& OutError)
	{
		const TSharedPtr<FJsonObject>* Record = nullptr;
		FString Filename;
		FString Encoding;
		if (!FilesObject.IsValid()
			|| !FilesObject->TryGetObjectField(Role, Record)
			|| !Record || !Record->IsValid()
			|| !(*Record)->TryGetStringField(TEXT("file"), Filename)
			|| !(*Record)->TryGetStringField(TEXT("encoding"), Encoding)
			|| !(*Record)->TryGetStringField(TEXT("sha256"), OutSha256)
			|| Filename != ExpectedFilename
			|| Encoding != ExpectedEncoding
			|| !IsCanonicalSha256(OutSha256))
		{
			OutError = FString::Printf(
				TEXT("manifest files.%s must be %s / %s with an uppercase SHA-256"),
				Role, *ExpectedFilename, ExpectedEncoding);
			return false;
		}
		return true;
	};

	for (int32 FaceIndex = 0; FaceIndex < PlanetGenMacroCubeFaceCount; ++FaceIndex)
	{
		const TSharedPtr<FJsonValue>& FaceValue = (*ManifestFaces)[FaceIndex];
		if (!FaceValue.IsValid() || FaceValue->Type != EJson::Object)
		{
			return FString::Printf(TEXT("ERR: manifest face %d is not an object"), FaceIndex);
		}
		const TSharedPtr<FJsonObject> FaceObject = FaceValue->AsObject();
		int32 ManifestFaceIndex = INDEX_NONE;
		FString ManifestFaceName;
		FString ManifestHeightPngFilename;
		FString ManifestRawFilename;
		FString ManifestLandFilename;
		FString ManifestBiomeFilename;
		const FString ExpectedHeightPngFilename =
			FString::Printf(TEXT("RED_Height_%s_16.png"), FaceNames[FaceIndex]);
		const FString ExpectedRawFilename =
			FString::Printf(TEXT("RED_Height_%s.r16"), FaceNames[FaceIndex]);
		const FString ExpectedLandFilename =
			FString::Printf(TEXT("RED_Land_%s.png"), FaceNames[FaceIndex]);
		const FString ExpectedBiomeFilename =
			FString::Printf(TEXT("RED_Biomes_%s.png"), FaceNames[FaceIndex]);
		if (!FaceObject.IsValid()
			|| !FaceObject->TryGetNumberField(TEXT("face_index"), ManifestFaceIndex)
			|| !FaceObject->TryGetStringField(TEXT("name"), ManifestFaceName)
			|| !FaceObject->TryGetStringField(TEXT("height_file"), ManifestHeightPngFilename)
			|| !FaceObject->TryGetStringField(TEXT("raw_height_file"), ManifestRawFilename)
			|| !FaceObject->TryGetStringField(TEXT("land_file"), ManifestLandFilename)
			|| !FaceObject->TryGetStringField(TEXT("biome_file"), ManifestBiomeFilename)
			|| ManifestFaceIndex != FaceIndex
			|| ManifestFaceName != FaceNames[FaceIndex]
			|| ManifestHeightPngFilename != ExpectedHeightPngFilename
			|| ManifestRawFilename != ExpectedRawFilename
			|| ManifestLandFilename != ExpectedLandFilename
			|| ManifestBiomeFilename != ExpectedBiomeFilename)
		{
			return FString::Printf(
				TEXT("ERR: manifest face %d must use canonical %s height/land/biome filenames"),
				FaceIndex, FaceNames[FaceIndex]);
		}

		const TSharedPtr<FJsonObject>* FilesObject = nullptr;
		if (!FaceObject->TryGetObjectField(TEXT("files"), FilesObject)
			|| !FilesObject || !FilesObject->IsValid())
		{
			return FString::Printf(TEXT("ERR: manifest face %s has no files object"), FaceNames[FaceIndex]);
		}
		FManifestFaceInputs& Inputs = FaceInputs[FaceIndex];
		Inputs.HeightPngFilename = ExpectedHeightPngFilename;
		Inputs.RawHeightFilename = ExpectedRawFilename;
		Inputs.LandFilename = ExpectedLandFilename;
		Inputs.BiomeFilename = ExpectedBiomeFilename;
		FString RecordError;
		if (!ReadManifestFileRecord(
				*FilesObject, TEXT("height"), Inputs.HeightPngFilename,
				TEXT("PNG grayscale uint16"), Inputs.HeightPngSha256, RecordError)
			|| !ReadManifestFileRecord(
				*FilesObject, TEXT("raw_height"), Inputs.RawHeightFilename,
				TEXT("little-endian uint16 row-major"), Inputs.RawHeightSha256, RecordError)
			|| !ReadManifestFileRecord(
				*FilesObject, TEXT("land"), Inputs.LandFilename,
				TEXT("PNG L8"), Inputs.LandSha256, RecordError)
			|| !ReadManifestFileRecord(
				*FilesObject, TEXT("biomes"), Inputs.BiomeFilename,
				TEXT("PNG RGBA8"), Inputs.BiomeSha256, RecordError))
		{
			return FString::Printf(TEXT("ERR: face %s: %s"), FaceNames[FaceIndex], *RecordError);
		}
	}

	IPlatformCrypto* CryptoModule =
		FModuleManager::LoadModulePtr<IPlatformCrypto>(FName(TEXT("PlatformCrypto")));
	TUniquePtr<FEncryptionContext> CryptoContext;
	if (CryptoModule)
	{
		CryptoContext = CryptoModule->CreateContext();
	}
	if (!CryptoContext)
	{
		return TEXT("ERR: PlatformCrypto SHA-256 context is unavailable");
	}
	auto ComputeSha256 = [CryptoContextPtr = CryptoContext.Get()](
		const TArray<uint8>& Bytes, FString& OutSha256)
	{
		if (!CryptoContextPtr || Bytes.Num() <= 0)
		{
			return false;
		}
		TArray<uint8> Digest;
		if (!CryptoContextPtr->CalcSHA256(
				TArrayView<const uint8>(Bytes.GetData(), Bytes.Num()), Digest)
			|| Digest.Num() != 32)
		{
			return false;
		}
		OutSha256 = BytesToHex(Digest.GetData(), Digest.Num());
		return true;
	};
	auto LoadAuthenticatedFile = [
		&SourceRoot, &ComputeSha256, &DatasetHashEntries](
		const FString& Filename,
		const FString& ExpectedSha256,
		int64 MinimumFileBytes,
		int64 MaximumFileBytes,
		TArray<uint8>& OutBytes,
		FString& OutError)
	{
		const FString Path = FPaths::Combine(SourceRoot, Filename);
		OutBytes.Reset();
		TUniquePtr<FArchive> FileReader(IFileManager::Get().CreateFileReader(*Path));
		if (!FileReader)
		{
			OutError = FString::Printf(TEXT("source raster not found or unreadable: %s"), *Path);
			return false;
		}
		const int64 FileBytes = FileReader->TotalSize();
		if (FileBytes < MinimumFileBytes || FileBytes > MaximumFileBytes || FileBytes > MAX_int32)
		{
			OutError = FString::Printf(
				TEXT("source raster size is outside the authenticated role bound: %s (%lld bytes, allowed %lld..%lld)"),
				*Path, FileBytes, MinimumFileBytes, MaximumFileBytes);
			return false;
		}
		OutBytes.SetNumUninitialized(static_cast<int32>(FileBytes));
		FileReader->Serialize(OutBytes.GetData(), FileBytes);
		if (FileReader->IsError() || FileReader->Tell() != FileBytes)
		{
			OutError = FString::Printf(
				TEXT("source raster could not be read completely: %s"), *Path);
			OutBytes.Reset();
			return false;
		}
		FString ActualSha256;
		if (!ComputeSha256(OutBytes, ActualSha256))
		{
			OutError = FString::Printf(TEXT("could not SHA-256 source raster: %s"), *Path);
			return false;
		}
		if (ActualSha256 != ExpectedSha256)
		{
			OutError = FString::Printf(
				TEXT("SHA-256 mismatch for %s (expected %s, got %s)"),
				*Filename, *ExpectedSha256, *ActualSha256);
			return false;
		}
		DatasetHashEntries.Add(FDatasetHashEntry{ Filename, ActualSha256 });
		return true;
	};
	auto ValidatePngHeader = [Resolution](
		const TArray<uint8>& Bytes,
		uint8 ExpectedBitDepth,
		uint8 ExpectedColorType,
		const FString& Filename,
		FString& OutError)
	{
		static constexpr uint8 PngSignature[8] = { 137, 80, 78, 71, 13, 10, 26, 10 };
		auto ReadBigEndian32 = [](const uint8* Data)
		{
			return (static_cast<uint32>(Data[0]) << 24)
				| (static_cast<uint32>(Data[1]) << 16)
				| (static_cast<uint32>(Data[2]) << 8)
				| static_cast<uint32>(Data[3]);
		};
		if (Bytes.Num() < 33
			|| FMemory::Memcmp(Bytes.GetData(), PngSignature, sizeof(PngSignature)) != 0
			|| ReadBigEndian32(Bytes.GetData() + 8) != 13
			|| FMemory::Memcmp(Bytes.GetData() + 12, "IHDR", 4) != 0
			|| ReadBigEndian32(Bytes.GetData() + 16) != static_cast<uint32>(Resolution)
			|| ReadBigEndian32(Bytes.GetData() + 20) != static_cast<uint32>(Resolution)
			|| Bytes[24] != ExpectedBitDepth
			|| Bytes[25] != ExpectedColorType
			|| Bytes[26] != 0
			|| Bytes[27] != 0
			|| Bytes[28] != 0)
		{
			OutError = FString::Printf(
				TEXT("%s is not an exact non-interlaced %dx%d %u-bit PNG color type %u"),
				*Filename, Resolution, Resolution, ExpectedBitDepth, ExpectedColorType);
			return false;
		}
		return true;
	};

	TStaticArray<TArray<uint16>, PlanetGenMacroCubeFaceCount> FaceSamples;
	TStaticArray<TArray<uint8>, PlanetGenMacroCubeFaceCount> LandSamples;
	TStaticArray<TArray<FColor>, PlanetGenMacroCubeFaceCount> BiomeSamples;
	// PNG IDAT payloads can be slightly larger than their decoded scanlines. Allow a generous,
	// resolution-scaled bound plus container overhead, but reject giant inputs before allocating.
	static constexpr int64 PngContainerOverheadBytes = 4ll * 1024ll * 1024ll;
	const int64 HeightPngMaximumBytes = ByteCount64 + Resolution + PngContainerOverheadBytes;
	const int64 LandPngMaximumBytes = SampleCount64 + Resolution + PngContainerOverheadBytes;
	const int64 BiomePngMaximumBytes = SampleCount64 * 4 + Resolution + PngContainerOverheadBytes;
	for (int32 FaceIndex = 0; FaceIndex < PlanetGenMacroCubeFaceCount; ++FaceIndex)
	{
		const FManifestFaceInputs& Inputs = FaceInputs[FaceIndex];
		TArray<uint8> Bytes;
		FString AuthenticationError;
		if (!LoadAuthenticatedFile(
				Inputs.HeightPngFilename, Inputs.HeightPngSha256,
				33, HeightPngMaximumBytes, Bytes, AuthenticationError)
			|| !ValidatePngHeader(
				Bytes, 16, 0, Inputs.HeightPngFilename, AuthenticationError))
		{
			return FString::Printf(TEXT("ERR: %s"), *AuthenticationError);
		}
		FImage HeightImage;
		if (!FImageUtils::DecompressImage(Bytes.GetData(), Bytes.Num(), HeightImage)
			|| HeightImage.SizeX != Resolution
			|| HeightImage.SizeY != Resolution
			|| HeightImage.NumSlices != 1
			|| HeightImage.Format != ERawImageFormat::G16
			|| HeightImage.AsG16().Num() != SampleCount)
		{
			return FString::Printf(
				TEXT("ERR: %s did not decode losslessly as %dx%d G16"),
				*Inputs.HeightPngFilename, Resolution, Resolution);
		}
		Bytes.Reset();
		if (!LoadAuthenticatedFile(
			Inputs.RawHeightFilename, Inputs.RawHeightSha256,
			ByteCount64, ByteCount64, Bytes, AuthenticationError))
		{
			return FString::Printf(TEXT("ERR: %s"), *AuthenticationError);
		}
		if (Bytes.Num() != ByteCount)
		{
			return FString::Printf(
				TEXT("ERR: %s has %d bytes; expected %d for %dx%d uint16 samples"),
				*Inputs.RawHeightFilename, Bytes.Num(), ByteCount, Resolution, Resolution);
		}

		TArray<uint16>& Samples = FaceSamples[FaceIndex];
		Samples.SetNumUninitialized(SampleCount);
		for (int32 SampleIndex = 0; SampleIndex < SampleCount; ++SampleIndex)
		{
			const int32 ByteIndex = SampleIndex * 2;
			Samples[SampleIndex] = static_cast<uint16>(Bytes[ByteIndex])
				| (static_cast<uint16>(Bytes[ByteIndex + 1]) << 8);
			if (HeightImage.AsG16()[SampleIndex] != Samples[SampleIndex])
			{
				return FString::Printf(
					TEXT("ERR: %s differs from %s at row-major sample %d"),
					*Inputs.HeightPngFilename, *Inputs.RawHeightFilename, SampleIndex);
			}
		}

		Bytes.Reset();
		if (!LoadAuthenticatedFile(
				Inputs.LandFilename, Inputs.LandSha256,
				33, LandPngMaximumBytes, Bytes, AuthenticationError)
			|| !ValidatePngHeader(Bytes, 8, 0, Inputs.LandFilename, AuthenticationError))
		{
			return FString::Printf(TEXT("ERR: %s"), *AuthenticationError);
		}
		FImage LandImage;
		if (!FImageUtils::DecompressImage(Bytes.GetData(), Bytes.Num(), LandImage)
			|| LandImage.SizeX != Resolution
			|| LandImage.SizeY != Resolution
			|| LandImage.NumSlices != 1
			|| LandImage.Format != ERawImageFormat::G8
			|| LandImage.AsG8().Num() != SampleCount)
		{
			return FString::Printf(
				TEXT("ERR: %s did not decode losslessly as %dx%d G8"),
				*Inputs.LandFilename, Resolution, Resolution);
		}
		TArray<uint8>& FaceLand = LandSamples[FaceIndex];
		FaceLand.SetNumUninitialized(SampleCount);
		// Copy decoded storage directly: PNG rows remain Y=0..Resolution-1 and G8 bytes are
		// authored mask weights, not colors to be gamma-transformed.
		FMemory::Memcpy(FaceLand.GetData(), LandImage.AsG8().GetData(), SampleCount);

		Bytes.Reset();
		if (!LoadAuthenticatedFile(
				Inputs.BiomeFilename, Inputs.BiomeSha256,
				33, BiomePngMaximumBytes, Bytes, AuthenticationError)
			|| !ValidatePngHeader(Bytes, 8, 6, Inputs.BiomeFilename, AuthenticationError))
		{
			return FString::Printf(TEXT("ERR: %s"), *AuthenticationError);
		}
		FImage BiomeImage;
		if (!FImageUtils::DecompressImage(Bytes.GetData(), Bytes.Num(), BiomeImage)
			|| BiomeImage.SizeX != Resolution
			|| BiomeImage.SizeY != Resolution
			|| BiomeImage.NumSlices != 1
			|| BiomeImage.Format != ERawImageFormat::BGRA8
			|| BiomeImage.AsBGRA8().Num() != SampleCount)
		{
			return FString::Printf(
				TEXT("ERR: %s did not decode losslessly as %dx%d BGRA8/FColor"),
				*Inputs.BiomeFilename, Resolution, Resolution);
		}
		TArray<FColor>& FaceBiomes = BiomeSamples[FaceIndex];
		FaceBiomes.SetNumUninitialized(SampleCount);
		// FColor exposes semantic R/G/B/A even though its native byte layout is BGRA. Direct copy
		// preserves the four authored uint8 weights without a color-space conversion or Y flip.
		FMemory::Memcpy(
			FaceBiomes.GetData(), BiomeImage.AsBGRA8().GetData(),
			static_cast<SIZE_T>(SampleCount) * sizeof(FColor));
	}

	DatasetHashEntries.Sort([](const FDatasetHashEntry& A, const FDatasetHashEntry& B)
	{
		return A.Filename < B.Filename;
	});
	TArray<uint8> DatasetIndexBytes;
	for (const FDatasetHashEntry& Entry : DatasetHashEntries)
	{
		FTCHARToUTF8 FilenameUtf8(*Entry.Filename);
		DatasetIndexBytes.Append(
			reinterpret_cast<const uint8*>(FilenameUtf8.Get()), FilenameUtf8.Length());
		DatasetIndexBytes.Add(0);
		FTCHARToUTF8 HashUtf8(*Entry.Sha256);
		DatasetIndexBytes.Append(
			reinterpret_cast<const uint8*>(HashUtf8.Get()), HashUtf8.Length());
		DatasetIndexBytes.Add(static_cast<uint8>('\n'));
	}
	FString ActualDatasetSha256;
	if (DatasetHashEntries.Num() != PlanetGenMacroCubeFaceCount * 4
		|| !ComputeSha256(DatasetIndexBytes, ActualDatasetSha256)
		|| ActualDatasetSha256 != DeclaredDatasetSha256)
	{
		return FString::Printf(
			TEXT("ERR: canonical 24-file raster dataset SHA-256 mismatch (manifest=%s actual=%s)"),
			*DeclaredDatasetSha256, *ActualDatasetSha256);
	}

	struct FMaskBorderSample
	{
		uint8 Land = 0;
		FColor Biome = FColor::Transparent;
		int32 Occurrences = 0;
	};
	TMap<FIntVector, FMaskBorderSample> MaskBorderSamples;
	int32 MaskBoundaryComparisons = 0;
	const int32 BorderExtent = Resolution - 1;
	for (int32 FaceIndex = 0; FaceIndex < PlanetGenMacroCubeFaceCount; ++FaceIndex)
	{
		const EPlanetGenMacroCubeFace Face = static_cast<EPlanetGenMacroCubeFace>(FaceIndex);
		for (int32 Y = 0; Y < Resolution; ++Y)
		{
			for (int32 X = 0; X < Resolution; ++X)
			{
				if (X != 0 && Y != 0 && X != Resolution - 1 && Y != Resolution - 1)
				{
					continue;
				}
				const int32 U = 2 * X - BorderExtent;
				const int32 V = 2 * Y - BorderExtent;
				const FVector KeyVector =
					FPlanetGenMacroHeightfieldCapture::GetFaceNormal(Face) * BorderExtent
					+ FPlanetGenMacroHeightfieldCapture::GetFaceU(Face) * U
					+ FPlanetGenMacroHeightfieldCapture::GetFaceV(Face) * V;
				const FIntVector Key(
					FMath::RoundToInt(KeyVector.X),
					FMath::RoundToInt(KeyVector.Y),
					FMath::RoundToInt(KeyVector.Z));
				const int32 SampleIndex = Y * Resolution + X;
				FMaskBorderSample* Existing = MaskBorderSamples.Find(Key);
				if (!Existing)
				{
					FMaskBorderSample Initial;
					Initial.Land = LandSamples[FaceIndex][SampleIndex];
					Initial.Biome = BiomeSamples[FaceIndex][SampleIndex];
					Initial.Occurrences = 1;
					MaskBorderSamples.Add(Key, Initial);
					continue;
				}
				++MaskBoundaryComparisons;
				++Existing->Occurrences;
				if (Existing->Land != LandSamples[FaceIndex][SampleIndex]
					|| Existing->Biome != BiomeSamples[FaceIndex][SampleIndex])
				{
					return FString::Printf(
						TEXT("ERR: decoded land/biome cube-face seam mismatch at face=%s x=%d y=%d"),
						FaceNames[FaceIndex], X, Y);
				}
			}
		}
	}
	if (MaskBoundaryComparisons != ExpectedBoundaryComparisons
		|| MaskBorderSamples.Num() != ExpectedUniqueBoundarySamples)
	{
		return TEXT("ERR: decoded mask boundary topology count does not match the canonical cube");
	}
	for (const TPair<FIntVector, FMaskBorderSample>& Pair : MaskBorderSamples)
	{
		if (Pair.Value.Occurrences != 2 && Pair.Value.Occurrences != 3)
		{
			return TEXT("ERR: decoded mask boundary has a noncanonical edge/corner occurrence count");
		}
	}

	// Exercise the same validation/capture path used by ACLMPlanet before touching a content package.
	UPlanetGenMacroHeightfieldAsset* Candidate =
		NewObject<UPlanetGenMacroHeightfieldAsset>(GetTransientPackage());
	Candidate->Resolution = Resolution;
	Candidate->MinHeightCm = MinHeightCm;
	Candidate->MaxHeightCm = MaxHeightCm;
	// Validate the source borders before enabling runtime fusion. A stale manifest must not be
	// allowed to hide a modified raw edge merely because BuildCapture averages it afterward.
	Candidate->bFuseSharedBordersOnCapture = false;
	Candidate->PositiveX = MoveTemp(FaceSamples[0]);
	Candidate->NegativeX = MoveTemp(FaceSamples[1]);
	Candidate->PositiveY = MoveTemp(FaceSamples[2]);
	Candidate->NegativeY = MoveTemp(FaceSamples[3]);
	Candidate->PositiveZ = MoveTemp(FaceSamples[4]);
	Candidate->NegativeZ = MoveTemp(FaceSamples[5]);
	Candidate->LandPositiveX = MoveTemp(LandSamples[0]);
	Candidate->LandNegativeX = MoveTemp(LandSamples[1]);
	Candidate->LandPositiveY = MoveTemp(LandSamples[2]);
	Candidate->LandNegativeY = MoveTemp(LandSamples[3]);
	Candidate->LandPositiveZ = MoveTemp(LandSamples[4]);
	Candidate->LandNegativeZ = MoveTemp(LandSamples[5]);
	Candidate->BiomePositiveX = MoveTemp(BiomeSamples[0]);
	Candidate->BiomeNegativeX = MoveTemp(BiomeSamples[1]);
	Candidate->BiomePositiveY = MoveTemp(BiomeSamples[2]);
	Candidate->BiomeNegativeY = MoveTemp(BiomeSamples[3]);
	Candidate->BiomePositiveZ = MoveTemp(BiomeSamples[4]);
	Candidate->BiomeNegativeZ = MoveTemp(BiomeSamples[5]);
	FPlanetGenMacroHeightfieldCapture ValidationCapture;
	FString ValidationError;
	if (!Candidate->BuildCapture(ValidationCapture, &ValidationError))
	{
		return FString::Printf(TEXT("ERR: PlanetGen rejected source faces: %s"), *ValidationError);
	}
	FPlanetGenMacroHeightfieldCapture FusedCapture = ValidationCapture;
	if (!FusedCapture.FuseSharedBorders())
	{
		return TEXT("ERR: PlanetGen could not validate shared cube-face borders");
	}
	for (int32 FaceIndex = 0; FaceIndex < PlanetGenMacroCubeFaceCount; ++FaceIndex)
	{
		const EPlanetGenMacroCubeFace Face = static_cast<EPlanetGenMacroCubeFace>(FaceIndex);
		for (int32 Y = 0; Y < Resolution; ++Y)
		{
			for (int32 X = 0; X < Resolution; ++X)
			{
				if (X != 0 && Y != 0 && X != Resolution - 1 && Y != Resolution - 1)
				{
					continue;
				}
				if (ValidationCapture.GetEncodedSampleChecked(Face, X, Y)
					!= FusedCapture.GetEncodedSampleChecked(Face, X, Y))
				{
					return FString::Printf(
						TEXT("ERR: raw cube-face seam mismatch at face=%s x=%d y=%d"),
						FaceNames[FaceIndex], X, Y);
				}
			}
		}
	}
	Candidate->bFuseSharedBordersOnCapture = true;
	ValidationCapture.Reset();
	FusedCapture.Reset();

	FString PackagePath = AssetPackagePath.TrimStartAndEnd();
	if (PackagePath.Contains(TEXT(".")))
	{
		PackagePath = FPackageName::ObjectPathToPackageName(PackagePath);
	}
	FText PackagePathError;
	if (!PackagePath.StartsWith(TEXT("/Game/"))
		|| !FPackageName::IsValidLongPackageName(PackagePath, false, &PackagePathError))
	{
		return FString::Printf(
			TEXT("ERR: destination must be a valid /Game asset package path: %s (%s)"),
			*PackagePath, *PackagePathError.ToString());
	}
	const FString AssetName = FPackageName::GetLongPackageAssetName(PackagePath);
	if (AssetName.IsEmpty())
	{
		return FString::Printf(TEXT("ERR: destination package has no asset name: %s"), *PackagePath);
	}
	const FString ObjectPath = PackagePath + TEXT(".") + AssetName;
	const FString OutputFilename = FPackageName::LongPackageNameToFilename(
		PackagePath, FPackageName::GetAssetPackageExtension());
	FString ExistingPackageFilename;
	const bool bPackageAlreadyExists =
		FPackageName::DoesPackageExist(PackagePath, &ExistingPackageFilename);
	if (bPackageAlreadyExists
		&& !ExistingPackageFilename.EndsWith(FPackageName::GetAssetPackageExtension()))
	{
		return FString::Printf(TEXT("ERR: destination package is not a data asset: %s"), *ExistingPackageFilename);
	}
	if (bPackageAlreadyExists && IFileManager::Get().IsReadOnly(*ExistingPackageFilename))
	{
		return FString::Printf(TEXT("ERR: destination package is read-only: %s"), *ExistingPackageFilename);
	}
	if (!IFileManager::Get().MakeDirectory(*FPaths::GetPath(OutputFilename), true))
	{
		return FString::Printf(TEXT("ERR: could not create destination directory: %s"), *FPaths::GetPath(OutputFilename));
	}

	UObject* ExistingObject = StaticLoadObject(
		UObject::StaticClass(), nullptr, *ObjectPath, nullptr, LOAD_NoWarn);
	if (ExistingObject && !ExistingObject->IsA<UPlanetGenMacroHeightfieldAsset>())
	{
		return FString::Printf(
			TEXT("ERR: destination already contains %s, not UPlanetGenMacroHeightfieldAsset: %s"),
			*ExistingObject->GetClass()->GetName(), *ObjectPath);
	}
	if (bPackageAlreadyExists && !ExistingObject)
	{
		return FString::Printf(
			TEXT("ERR: package exists but expected asset object could not be loaded: %s"), *ObjectPath);
	}

	UPlanetGenMacroHeightfieldAsset* Asset =
		Cast<UPlanetGenMacroHeightfieldAsset>(ExistingObject);
	const bool bCreatedAsset = Asset == nullptr;
	UPackage* Package = nullptr;
	if (bCreatedAsset)
	{
		Package = CreatePackage(*PackagePath);
		if (!Package)
		{
			return FString::Printf(TEXT("ERR: failed to create package: %s"), *PackagePath);
		}
		Asset = NewObject<UPlanetGenMacroHeightfieldAsset>(
			Package, *AssetName, RF_Public | RF_Standalone | RF_Transactional);
	}
	else
	{
		Package = Asset->GetOutermost();
	}
	if (!Asset || !Package)
	{
		return FString::Printf(TEXT("ERR: failed to resolve destination asset: %s"), *ObjectPath);
	}

	const bool bPackageWasDirty = Package->IsDirty();
	const int32 PreviousResolution = Asset->Resolution;
	const float PreviousMinHeightCm = Asset->MinHeightCm;
	const float PreviousMaxHeightCm = Asset->MaxHeightCm;
	const bool bPreviousFuseBorders = Asset->bFuseSharedBordersOnCapture;

	Asset->Modify();
	Asset->PreEditChange(nullptr);
	// Move the previous bulk arrays into rollback storage rather than duplicating them. At the
	// importer ceiling this avoids another complete multi-channel planet allocation.
	TArray<uint16> PreviousPositiveX = MoveTemp(Asset->PositiveX);
	TArray<uint16> PreviousNegativeX = MoveTemp(Asset->NegativeX);
	TArray<uint16> PreviousPositiveY = MoveTemp(Asset->PositiveY);
	TArray<uint16> PreviousNegativeY = MoveTemp(Asset->NegativeY);
	TArray<uint16> PreviousPositiveZ = MoveTemp(Asset->PositiveZ);
	TArray<uint16> PreviousNegativeZ = MoveTemp(Asset->NegativeZ);
	TArray<uint8> PreviousLandPositiveX = MoveTemp(Asset->LandPositiveX);
	TArray<uint8> PreviousLandNegativeX = MoveTemp(Asset->LandNegativeX);
	TArray<uint8> PreviousLandPositiveY = MoveTemp(Asset->LandPositiveY);
	TArray<uint8> PreviousLandNegativeY = MoveTemp(Asset->LandNegativeY);
	TArray<uint8> PreviousLandPositiveZ = MoveTemp(Asset->LandPositiveZ);
	TArray<uint8> PreviousLandNegativeZ = MoveTemp(Asset->LandNegativeZ);
	TArray<FColor> PreviousBiomePositiveX = MoveTemp(Asset->BiomePositiveX);
	TArray<FColor> PreviousBiomeNegativeX = MoveTemp(Asset->BiomeNegativeX);
	TArray<FColor> PreviousBiomePositiveY = MoveTemp(Asset->BiomePositiveY);
	TArray<FColor> PreviousBiomeNegativeY = MoveTemp(Asset->BiomeNegativeY);
	TArray<FColor> PreviousBiomePositiveZ = MoveTemp(Asset->BiomePositiveZ);
	TArray<FColor> PreviousBiomeNegativeZ = MoveTemp(Asset->BiomeNegativeZ);
	Asset->Resolution = Candidate->Resolution;
	Asset->MinHeightCm = Candidate->MinHeightCm;
	Asset->MaxHeightCm = Candidate->MaxHeightCm;
	Asset->bFuseSharedBordersOnCapture = Candidate->bFuseSharedBordersOnCapture;
	Asset->PositiveX = MoveTemp(Candidate->PositiveX);
	Asset->NegativeX = MoveTemp(Candidate->NegativeX);
	Asset->PositiveY = MoveTemp(Candidate->PositiveY);
	Asset->NegativeY = MoveTemp(Candidate->NegativeY);
	Asset->PositiveZ = MoveTemp(Candidate->PositiveZ);
	Asset->NegativeZ = MoveTemp(Candidate->NegativeZ);
	Asset->LandPositiveX = MoveTemp(Candidate->LandPositiveX);
	Asset->LandNegativeX = MoveTemp(Candidate->LandNegativeX);
	Asset->LandPositiveY = MoveTemp(Candidate->LandPositiveY);
	Asset->LandNegativeY = MoveTemp(Candidate->LandNegativeY);
	Asset->LandPositiveZ = MoveTemp(Candidate->LandPositiveZ);
	Asset->LandNegativeZ = MoveTemp(Candidate->LandNegativeZ);
	Asset->BiomePositiveX = MoveTemp(Candidate->BiomePositiveX);
	Asset->BiomeNegativeX = MoveTemp(Candidate->BiomeNegativeX);
	Asset->BiomePositiveY = MoveTemp(Candidate->BiomePositiveY);
	Asset->BiomeNegativeY = MoveTemp(Candidate->BiomeNegativeY);
	Asset->BiomePositiveZ = MoveTemp(Candidate->BiomePositiveZ);
	Asset->BiomeNegativeZ = MoveTemp(Candidate->BiomeNegativeZ);
	Asset->PostEditChange();
	Package->MarkPackageDirty();

	FSavePackageArgs SaveArgs;
	SaveArgs.TopLevelFlags = RF_Public | RF_Standalone;
	SaveArgs.SaveFlags = SAVE_NoError;
	if (!UPackage::SavePackage(Package, Asset, *OutputFilename, SaveArgs))
	{
		if (bCreatedAsset)
		{
			Asset->ClearFlags(RF_Public | RF_Standalone);
			Asset->Rename(nullptr, GetTransientPackage(),
				REN_DontCreateRedirectors | REN_NonTransactional);
			Asset->MarkAsGarbage();
		}
		else
		{
			Asset->PreEditChange(nullptr);
			Asset->Resolution = PreviousResolution;
			Asset->MinHeightCm = PreviousMinHeightCm;
			Asset->MaxHeightCm = PreviousMaxHeightCm;
			Asset->bFuseSharedBordersOnCapture = bPreviousFuseBorders;
			Asset->PositiveX = MoveTemp(PreviousPositiveX);
			Asset->NegativeX = MoveTemp(PreviousNegativeX);
			Asset->PositiveY = MoveTemp(PreviousPositiveY);
			Asset->NegativeY = MoveTemp(PreviousNegativeY);
			Asset->PositiveZ = MoveTemp(PreviousPositiveZ);
			Asset->NegativeZ = MoveTemp(PreviousNegativeZ);
			Asset->LandPositiveX = MoveTemp(PreviousLandPositiveX);
			Asset->LandNegativeX = MoveTemp(PreviousLandNegativeX);
			Asset->LandPositiveY = MoveTemp(PreviousLandPositiveY);
			Asset->LandNegativeY = MoveTemp(PreviousLandNegativeY);
			Asset->LandPositiveZ = MoveTemp(PreviousLandPositiveZ);
			Asset->LandNegativeZ = MoveTemp(PreviousLandNegativeZ);
			Asset->BiomePositiveX = MoveTemp(PreviousBiomePositiveX);
			Asset->BiomeNegativeX = MoveTemp(PreviousBiomeNegativeX);
			Asset->BiomePositiveY = MoveTemp(PreviousBiomePositiveY);
			Asset->BiomeNegativeY = MoveTemp(PreviousBiomeNegativeY);
			Asset->BiomePositiveZ = MoveTemp(PreviousBiomePositiveZ);
			Asset->BiomeNegativeZ = MoveTemp(PreviousBiomeNegativeZ);
			Asset->PostEditChange();
		}
		Package->SetDirtyFlag(bPackageWasDirty);
		return FString::Printf(TEXT("ERR: failed to save destination package: %s"), *OutputFilename);
	}

	if (bCreatedAsset)
	{
		FAssetRegistryModule::AssetCreated(Asset);
	}
	return FString::Printf(
		TEXT("OK: %s %s from %s (%dx%d, %lld height+land+RGBA samples per channel set, min=%gcm, max=%gcm, dataset=%s, borders=fuse-on-capture)"),
		bCreatedAsset ? TEXT("created") : TEXT("updated"), *ObjectPath, *SourceRoot,
		Resolution, Resolution, SampleCount64 * PlanetGenMacroCubeFaceCount,
		static_cast<double>(MinHeightCm), static_cast<double>(MaxHeightCm),
		*ActualDatasetSha256);
#endif // REDMMO_HAS_PLANETGEN_MACROHEIGHTFIELD
#else
	return TEXT("ERR: editor-only");
#endif // WITH_EDITOR
}


FString URedMMOEditorTools::DumpMaterialExpressions(const FString& MaterialPath)
{
#if WITH_EDITOR
	UMaterial* Mat = LoadObject<UMaterial>(nullptr, *MaterialPath);
	if (!Mat)
	{
		return TEXT("ERR: material not found");
	}
	TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetStringField(TEXT("material"), MaterialPath);
	TArray<TSharedPtr<FJsonValue>> Arr;
	int32 Index = 0;
	for (UMaterialExpression* Expr : Mat->GetExpressions())
	{
		if (!Expr) { ++Index; continue; }
		TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
		J->SetNumberField(TEXT("i"), Index++);
		J->SetStringField(TEXT("class"), Expr->GetClass()->GetName());
		if (const UMaterialExpressionConstant* C = Cast<UMaterialExpressionConstant>(Expr))
		{
			J->SetNumberField(TEXT("value"), C->R);
		}
		else if (const UMaterialExpressionScalarParameter* SP = Cast<UMaterialExpressionScalarParameter>(Expr))
		{
			J->SetStringField(TEXT("param"), SP->ParameterName.ToString());
			J->SetNumberField(TEXT("default"), SP->DefaultValue);
		}
		else if (const UMaterialExpressionVectorParameter* VP = Cast<UMaterialExpressionVectorParameter>(Expr))
		{
			J->SetStringField(TEXT("param"), VP->ParameterName.ToString());
			J->SetStringField(TEXT("default"), VP->DefaultValue.ToString());
		}
		else if (const UMaterialExpressionTextureBase* TB = Cast<UMaterialExpressionTextureBase>(Expr))
		{
			J->SetStringField(TEXT("texture"), GetNameSafe(TB->Texture));
		}
		else if (const UMaterialExpressionMaterialFunctionCall* FC = Cast<UMaterialExpressionMaterialFunctionCall>(Expr))
		{
			J->SetStringField(TEXT("function"), GetNameSafe(FC->MaterialFunction));
		}
		FString Desc = Expr->GetDescription();
		if (!Desc.IsEmpty()) { J->SetStringField(TEXT("desc"), Desc.Left(80)); }
		Arr.Add(MakeShared<FJsonValueObject>(J));
	}
	Root->SetArrayField(TEXT("expressions"), Arr);
	FString Out;
	const TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> W =
		TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Out);
	FJsonSerializer::Serialize(Root, W);
	return Out;
#else
	return TEXT("ERR: editor-only");
#endif
}

FString URedMMOEditorTools::SetMaterialScalarConstants(const FString& MaterialPath, float FromValue, float ToValue)
{
#if WITH_EDITOR
	UMaterial* Mat = LoadObject<UMaterial>(nullptr, *MaterialPath);
	if (!Mat)
	{
		return TEXT("ERR: material not found");
	}
	int32 Changed = 0;
	for (UMaterialExpression* Expr : Mat->GetExpressions())
	{
		if (UMaterialExpressionConstant* C = Cast<UMaterialExpressionConstant>(Expr))
		{
			if (FMath::IsNearlyEqual(C->R, FromValue, 0.001f))
			{
				C->Modify();
				C->R = ToValue;
				++Changed;
			}
		}
	}
	if (Changed > 0)
	{
		UMaterialEditingLibrary::RecompileMaterial(Mat);
	}
	return FString::Printf(TEXT("OK: changed %d constant(s) %g -> %g"), Changed, FromValue, ToValue);
#else
	return TEXT("ERR: editor-only");
#endif
}


FString URedMMOEditorTools::InsertSubtractAfterExpression(const FString& MaterialPath, int32 ExprIndex, float ConstB)
{
#if WITH_EDITOR
	UMaterial* Mat = LoadObject<UMaterial>(nullptr, *MaterialPath);
	if (!Mat)
	{
		return TEXT("ERR: material not found");
	}
	TArray<UMaterialExpression*> Exprs;
	for (UMaterialExpression* E : Mat->GetExpressions()) { Exprs.Add(E); }
	if (!Exprs.IsValidIndex(ExprIndex))
	{
		return FString::Printf(TEXT("ERR: expr index %d out of range (%d expressions)"), ExprIndex, Exprs.Num());
	}
	UMaterialExpression* Target = Exprs[ExprIndex];
	Mat->Modify();
	UMaterialExpressionSubtract* Sub = Cast<UMaterialExpressionSubtract>(UMaterialEditingLibrary::CreateMaterialExpression(
		Mat, UMaterialExpressionSubtract::StaticClass(),
		Target->MaterialExpressionEditorX + 160, Target->MaterialExpressionEditorY + 40));
	if (!Sub)
	{
		return TEXT("ERR: could not create Subtract");
	}
	Sub->ConstB = ConstB;

	bool bHookedA = false;
	int32 Rewired = 0;
	auto RewireInput = [&](FExpressionInput* In)
	{
		if (!In || In->Expression != Target)
		{
			return;
		}
		if (!bHookedA)
		{
			// Subtract.A takes over the exact tap the first consumer used (output index + mask).
			Sub->A.Expression = Target;
			Sub->A.OutputIndex = In->OutputIndex;
			Sub->A.Mask = In->Mask;
			Sub->A.MaskR = In->MaskR; Sub->A.MaskG = In->MaskG; Sub->A.MaskB = In->MaskB; Sub->A.MaskA = In->MaskA;
			bHookedA = true;
		}
		In->Expression = Sub;
		In->OutputIndex = 0;
		In->Mask = 0;
		In->MaskR = 0; In->MaskG = 0; In->MaskB = 0; In->MaskA = 0;
		++Rewired;
	};
	for (UMaterialExpression* Expr : Exprs)
	{
		if (Expr == Target)
		{
			continue;
		}
		for (int32 i = 0; ; ++i)
		{
			FExpressionInput* In = Expr->GetInput(i);
			if (!In)
			{
				break;
			}
			RewireInput(In);
		}
	}
	for (int32 P = 0; P < MP_MAX; ++P)
	{
		RewireInput(Mat->GetExpressionInputForProperty(static_cast<EMaterialProperty>(P)));
	}
	if (Rewired == 0)
	{
		return TEXT("ERR: no consumers of that expression — nothing rewired (Subtract left dangling)");
	}
	UMaterialEditingLibrary::RecompileMaterial(Mat);
	return FString::Printf(TEXT("OK: inserted Subtract(ConstB=%g) after expr %d (%s), rewired %d consumer input(s)"),
		ConstB, ExprIndex, *Target->GetClass()->GetName(), Rewired);
#else
	return TEXT("ERR: editor-only");
#endif
}


FString URedMMOEditorTools::SetMIStaticSwitch(const FString& MIPath, const FString& ParamName, bool bValue)
{
#if WITH_EDITOR
	UMaterialInstanceConstant* MI = LoadObject<UMaterialInstanceConstant>(nullptr, *MIPath);
	if (!MI)
	{
		return TEXT("ERR: material instance not found");
	}
	FStaticParameterSet Params;
	MI->GetStaticParameterValues(Params);
	bool bFound = false;
	for (FStaticSwitchParameter& Sw : Params.StaticSwitchParameters)
	{
		if (Sw.ParameterInfo.Name == FName(*ParamName))
		{
			Sw.Value = bValue;
			Sw.bOverride = true;
			bFound = true;
		}
	}
	if (!bFound)
	{
		FStaticSwitchParameter NewSw;
		NewSw.ParameterInfo.Name = FName(*ParamName);
		NewSw.Value = bValue;
		NewSw.bOverride = true;
		Params.StaticSwitchParameters.Add(NewSw);
	}
	MI->UpdateStaticPermutation(Params);
	MI->MarkPackageDirty();
	return FString::Printf(TEXT("OK: %s '%s' -> %s (%s)"), *MIPath, *ParamName,
		bValue ? TEXT("true") : TEXT("false"), bFound ? TEXT("overrode existing") : TEXT("added override"));
#else
	return TEXT("ERR: editor-only");
#endif
}


FString URedMMOEditorTools::SetMILayerStaticSwitch(
	const FString& MIPath,
	const FString& LayerNameOrIndex,
	const FString& ParamName,
	bool bValue)
{
#if WITH_EDITOR
	UMaterialInstanceConstant* MI = LoadObject<UMaterialInstanceConstant>(nullptr, *MIPath);
	if (!MI)
	{
		return FString::Printf(TEXT("ERR: material instance not found: %s"), *MIPath);
	}

	int32 LayerIndex = INDEX_NONE;
	FString ResolvedName;
	FString Err;
	if (!RedMMOEditorToolsPrivate::ResolveLayerIndex(MI, LayerNameOrIndex, LayerIndex, ResolvedName, Err))
	{
		return Err;
	}

	const FMaterialParameterInfo Info(
		FName(*ParamName), EMaterialParameterAssociation::LayerParameter, LayerIndex);
	bool OldValue = false;
	FGuid ParameterGuid;
	if (!MI->GetStaticSwitchParameterValue(FHashedMaterialParameterInfo(Info), OldValue, ParameterGuid))
	{
		return FString::Printf(
			TEXT("ERR: static switch '%s' not found on %s layer[%d]='%s'"),
			*ParamName, *MIPath, LayerIndex, *ResolvedName);
	}

	// MaterialEditingLibrary's public static-switch helper hardcodes LayerParameter index 0.
	// Use the same engine path with the resolved index, then construct the transient editor proxy
	// that preserves MaterialLayersParameters when the MIC is subsequently opened in the editor.
	MI->SetStaticSwitchParameterValueEditorOnly(Info, bValue);
	UMaterialEditorInstanceConstant* EditorProxy =
		NewObject<UMaterialEditorInstanceConstant>(GetTransientPackage(), NAME_None, RF_Transactional);
	EditorProxy->SetSourceInstance(MI);
	UMaterialEditingLibrary::UpdateMaterialInstance(MI);
	TArray<UPackage*> PackagesToSave;
	PackagesToSave.Add(MI->GetOutermost());
	FEditorFileUtils::PromptForCheckoutAndSave(PackagesToSave, /*bCheckDirty=*/false, /*bPromptToSave=*/false);

	return FString::Printf(
		TEXT("OK: %s layer[%d]='%s' static %s %s -> %s"),
		*MIPath, LayerIndex, *ResolvedName, *ParamName,
		OldValue ? TEXT("true") : TEXT("false"),
		bValue ? TEXT("true") : TEXT("false"));
#else
	return TEXT("ERR: editor-only");
#endif
}


FString URedMMOEditorTools::DumpMILayerParameters(const FString& MIPath)
{
#if WITH_EDITOR
	UMaterialInstanceConstant* MI = LoadObject<UMaterialInstanceConstant>(nullptr, *MIPath);
	if (!MI)
	{
		return TEXT("ERR: material instance not found");
	}

	TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetStringField(TEXT("mi"), MIPath);
	Root->SetStringField(TEXT("parent"), GetNameSafe(MI->Parent));

	FMaterialLayersFunctions Layers;
	const bool bHasLayers = RedMMOEditorToolsPrivate::TryGetLayers(MI, Layers);
	Root->SetBoolField(TEXT("hasLayers"), bHasLayers);

	TArray<TSharedPtr<FJsonValue>> LayerArr;
	if (bHasLayers)
	{
		for (int32 i = 0; i < Layers.Layers.Num(); ++i)
		{
			TSharedRef<FJsonObject> L = MakeShared<FJsonObject>();
			L->SetNumberField(TEXT("index"), i);
			L->SetStringField(TEXT("name"), Layers.GetLayerName(i).ToString());
			L->SetStringField(TEXT("asset"), GetPathNameSafe(Layers.Layers[i]));
			if (Layers.Blends.IsValidIndex(i))
			{
				L->SetStringField(TEXT("blend"), GetPathNameSafe(Layers.Blends[i]));
			}
			LayerArr.Add(MakeShared<FJsonValueObject>(L));
		}
	}
	Root->SetArrayField(TEXT("layers"), LayerArr);

	auto DumpParams = [MI](EMaterialParameterType Type, const TCHAR* Field, TSharedRef<FJsonObject> Into)
	{
		TMap<FMaterialParameterInfo, FMaterialParameterMetadata> Params;
		MI->GetAllParametersOfType(Type, Params);
		TArray<TSharedPtr<FJsonValue>> Arr;
		for (const TPair<FMaterialParameterInfo, FMaterialParameterMetadata>& Pair : Params)
		{
			TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
			J->SetStringField(TEXT("name"), Pair.Key.Name.ToString());
			J->SetStringField(TEXT("assoc"), RedMMOEditorToolsPrivate::AssociationToString(Pair.Key.Association));
			J->SetNumberField(TEXT("index"), Pair.Key.Index);
			if (Type == EMaterialParameterType::Texture)
			{
				J->SetStringField(TEXT("value"), GetPathNameSafe(Pair.Value.Value.Texture));
			}
			else if (Type == EMaterialParameterType::Scalar)
			{
				J->SetNumberField(TEXT("value"), Pair.Value.Value.Float[0]);
			}
			else if (Type == EMaterialParameterType::Vector)
			{
				const FLinearColor C = Pair.Value.Value.AsLinearColor();
				J->SetStringField(TEXT("value"), C.ToString());
			}
			J->SetBoolField(TEXT("bOverride"), Pair.Value.bOverride);
			Arr.Add(MakeShared<FJsonValueObject>(J));
		}
		Into->SetArrayField(Field, Arr);
	};

	DumpParams(EMaterialParameterType::Texture, TEXT("textures"), Root);
	DumpParams(EMaterialParameterType::Scalar, TEXT("scalars"), Root);
	DumpParams(EMaterialParameterType::Vector, TEXT("vectors"), Root);

	// Also list currently overridden texture values on the MIC itself.
	TArray<TSharedPtr<FJsonValue>> Overrides;
	for (const FTextureParameterValue& TV : MI->TextureParameterValues)
	{
		TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
		J->SetStringField(TEXT("name"), TV.ParameterInfo.Name.ToString());
		J->SetStringField(TEXT("assoc"), RedMMOEditorToolsPrivate::AssociationToString(TV.ParameterInfo.Association));
		J->SetNumberField(TEXT("index"), TV.ParameterInfo.Index);
		J->SetStringField(TEXT("value"), GetPathNameSafe(TV.ParameterValue));
		Overrides.Add(MakeShared<FJsonValueObject>(J));
	}
	Root->SetArrayField(TEXT("textureOverrides"), Overrides);

	FString Out;
	TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Writer =
		TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Out);
	FJsonSerializer::Serialize(Root, Writer);
	return Out;
#else
	return TEXT("ERR: editor-only");
#endif
}


FString URedMMOEditorTools::SetMILayerTextureParameter(
	const FString& MIPath,
	const FString& LayerNameOrIndex,
	const FString& ParamName,
	const FString& TexturePath)
{
#if WITH_EDITOR
	UMaterialInstanceConstant* MI = LoadObject<UMaterialInstanceConstant>(nullptr, *MIPath);
	if (!MI)
	{
		return FString::Printf(TEXT("ERR: material instance not found: %s"), *MIPath);
	}

	UTexture* Tex = LoadObject<UTexture>(nullptr, *TexturePath);
	if (!Tex)
	{
		return FString::Printf(TEXT("ERR: texture not found: %s"), *TexturePath);
	}

	int32 LayerIndex = INDEX_NONE;
	FString ResolvedName;
	FString Err;
	if (!RedMMOEditorToolsPrivate::ResolveLayerIndex(MI, LayerNameOrIndex, LayerIndex, ResolvedName, Err))
	{
		return Err;
	}

	const FMaterialParameterInfo Info(FName(*ParamName), EMaterialParameterAssociation::LayerParameter, LayerIndex);
	MI->SetTextureParameterValueEditorOnly(Info, Tex);
	UMaterialEditingLibrary::UpdateMaterialInstance(MI);
	MI->MarkPackageDirty();

	TArray<UPackage*> PackagesToSave;
	PackagesToSave.Add(MI->GetOutermost());
	FEditorFileUtils::PromptForCheckoutAndSave(PackagesToSave, /*bCheckDirty=*/false, /*bPromptToSave=*/false);

	UTexture* Verify = nullptr;
	MI->GetTextureParameterValue(FHashedMaterialParameterInfo(Info), Verify);
	return FString::Printf(
		TEXT("OK: %s layer[%d]='%s' %s -> %s (verify=%s)"),
		*MIPath, LayerIndex, *ResolvedName, *ParamName, *GetNameSafe(Tex), *GetNameSafe(Verify));
#else
	return TEXT("ERR: editor-only");
#endif
}


FString URedMMOEditorTools::SetMILayerScalarParameter(
	const FString& MIPath,
	const FString& LayerNameOrIndex,
	const FString& ParamName,
	float Value)
{
#if WITH_EDITOR
	UMaterialInstanceConstant* MI = LoadObject<UMaterialInstanceConstant>(nullptr, *MIPath);
	if (!MI)
	{
		return FString::Printf(TEXT("ERR: material instance not found: %s"), *MIPath);
	}

	int32 LayerIndex = INDEX_NONE;
	FString ResolvedName;
	FString Err;
	if (!RedMMOEditorToolsPrivate::ResolveLayerIndex(MI, LayerNameOrIndex, LayerIndex, ResolvedName, Err))
	{
		return Err;
	}

	const FMaterialParameterInfo Info(FName(*ParamName), EMaterialParameterAssociation::LayerParameter, LayerIndex);
	MI->SetScalarParameterValueEditorOnly(Info, Value);
	UMaterialEditingLibrary::UpdateMaterialInstance(MI);
	MI->MarkPackageDirty();

	TArray<UPackage*> PackagesToSave;
	PackagesToSave.Add(MI->GetOutermost());
	FEditorFileUtils::PromptForCheckoutAndSave(PackagesToSave, false, false);

	float Verify = 0.f;
	MI->GetScalarParameterValue(FHashedMaterialParameterInfo(Info), Verify);
	return FString::Printf(
		TEXT("OK: %s layer[%d]='%s' %s -> %g (verify=%g)"),
		*MIPath, LayerIndex, *ResolvedName, *ParamName, Value, Verify);
#else
	return TEXT("ERR: editor-only");
#endif
}


FString URedMMOEditorTools::SetMFITextureParameter(
	const FString& MFIPath,
	const FString& ParamName,
	const FString& TexturePath)
{
#if WITH_EDITOR
	UMaterialFunctionInstance* MFI = LoadObject<UMaterialFunctionInstance>(nullptr, *MFIPath);
	if (!MFI)
	{
		return FString::Printf(TEXT("ERR: MaterialFunctionInstance not found: %s"), *MFIPath);
	}
	UTexture* Tex = LoadObject<UTexture>(nullptr, *TexturePath);
	if (!Tex)
	{
		return FString::Printf(TEXT("ERR: texture not found: %s"), *TexturePath);
	}

	MFI->Modify();
	bool bFound = false;
	for (FTextureParameterValue& TV : MFI->TextureParameterValues)
	{
		if (TV.ParameterInfo.Name == FName(*ParamName))
		{
			TV.ParameterValue = Tex;
			bFound = true;
		}
	}
	if (!bFound)
	{
		FTextureParameterValue NewTV;
		NewTV.ParameterInfo.Name = FName(*ParamName);
		NewTV.ParameterInfo.Association = EMaterialParameterAssociation::GlobalParameter;
		NewTV.ParameterInfo.Index = INDEX_NONE;
		NewTV.ParameterValue = Tex;
		MFI->TextureParameterValues.Add(NewTV);
	}
	MFI->UpdateParameterSet();
	MFI->MarkPackageDirty();

	// Never try to save Engine/Plugin packages from here — only /Game assets.
	const FString PkgName = MFI->GetOutermost()->GetName();
	if (PkgName.StartsWith(TEXT("/Game/")))
	{
		TArray<UPackage*> PackagesToSave;
		PackagesToSave.Add(MFI->GetOutermost());
		FEditorFileUtils::PromptForCheckoutAndSave(PackagesToSave, false, false);
	}

	return FString::Printf(TEXT("OK: %s %s -> %s (found=%s pkg=%s)"),
		*MFIPath, *ParamName, *GetNameSafe(Tex),
		bFound ? TEXT("yes") : TEXT("added"), *PkgName);
#else
	return TEXT("ERR: editor-only");
#endif
}


FString URedMMOEditorTools::ApplySoStylizedSandToPlanetBiome(
	const FString& MIPath,
	const FString& SandBCPath,
	const FString& SandNPath)
{
#if WITH_EDITOR
	// IMPORTANT:
	// - Do NOT create_asset with a factory (caused blocking ensure:
	//   AssetClass->IsChildOf(Factory->GetSupportedClass())).
	// - Do NOT set Global Texture/Normal on the MI (paints all 5 biomes).
	// - Do NOT point plugin MFI_Sand at /Game/SoStylized textures (AssetReferencingDomains
	//   blocks plugin→/Game refs → "Could not resolve referenced texture 'T_DesertSand_*'").
	// Correct path: LayerParameter overrides on the /Game MI (can reference /Game textures).

	UTexture* BC = LoadObject<UTexture>(nullptr, *SandBCPath);
	UTexture* Nrm = LoadObject<UTexture>(nullptr, *SandNPath);
	if (!BC || !Nrm)
	{
		return FString::Printf(TEXT("ERR: SoStylized textures missing BC=%s N=%s"),
			BC ? TEXT("ok") : *SandBCPath, Nrm ? TEXT("ok") : *SandNPath);
	}

	// Keep project MFI copy in sync (optional; used if Sand layer asset is swapped later).
	const FString ProjectMFIPath = TEXT("/Game/RedMMO/Materials/MFI_Sand_SoStylized.MFI_Sand_SoStylized");
	if (UMaterialFunctionInstance* ProjectMFI = LoadObject<UMaterialFunctionInstance>(nullptr, *ProjectMFIPath))
	{
		SetMFITextureParameter(ProjectMFIPath, TEXT("Texture"), SandBCPath);
		SetMFITextureParameter(ProjectMFIPath, TEXT("Normal"), SandNPath);
	}

	// Ensure plugin MFI_Sand stays on stock PlanetGen textures (safe domain).
	if (UMaterialFunctionInstance* PluginMFI = LoadObject<UMaterialFunctionInstance>(
			nullptr, TEXT("/PlanetGen/Materials/Landscape/MFI_Sand.MFI_Sand")))
	{
		if (UTexture* StockBC = LoadObject<UTexture>(nullptr, TEXT("/PlanetGen/Textures/T_Sand.T_Sand")))
		{
			for (FTextureParameterValue& TV : PluginMFI->TextureParameterValues)
			{
				if (TV.ParameterInfo.Name == FName(TEXT("Texture"))) { TV.ParameterValue = StockBC; }
			}
		}
		if (UTexture* StockN = LoadObject<UTexture>(nullptr, TEXT("/PlanetGen/Textures/T_Sand_N.T_Sand_N")))
		{
			for (FTextureParameterValue& TV : PluginMFI->TextureParameterValues)
			{
				if (TV.ParameterInfo.Name == FName(TEXT("Normal"))) { TV.ParameterValue = StockN; }
			}
		}
		PluginMFI->UpdateParameterSet();
	}

	UMaterialInstanceConstant* MI = LoadObject<UMaterialInstanceConstant>(nullptr, *MIPath);
	if (!MI)
	{
		return FString::Printf(TEXT("ERR: MI not found: %s"), *MIPath);
	}

	// Resolve Sand index by name if possible; else probe PlanetGen order Grass/Rock/Snow/Sand/Underwater.
	int32 SandIndex = INDEX_NONE;
	FString SandName;
	FString ResolveErr;
	if (!RedMMOEditorToolsPrivate::ResolveLayerIndex(MI, TEXT("Sand"), SandIndex, SandName, ResolveErr)
		&& !RedMMOEditorToolsPrivate::ResolveLayerIndex(MI, TEXT("MFI_Sand"), SandIndex, SandName, ResolveErr))
	{
		// PlanetGen M_Planet stack is typically 5 layers; Sand is commonly index 3.
		// Probe 0..4: prefer an index whose current Texture soft-name contains "Sand".
		for (int32 i = 0; i < 5; ++i)
		{
			UTexture* Cur = nullptr;
			MI->GetTextureParameterValue(
				FHashedMaterialParameterInfo(FName(TEXT("Texture")), EMaterialParameterAssociation::LayerParameter, i),
				Cur);
			const FString CurName = GetNameSafe(Cur);
			if (CurName.Contains(TEXT("Sand"), ESearchCase::IgnoreCase))
			{
				SandIndex = i;
				SandName = FString::Printf(TEXT("probed:%s"), *CurName);
				break;
			}
		}
		if (SandIndex == INDEX_NONE)
		{
			SandIndex = 3; // PlanetGen documented order: Grass, Rock, Snow, Sand, Underwater
			SandName = TEXT("fallback:index3");
		}
	}

	const FString TexR = SetMILayerTextureParameter(MIPath, FString::FromInt(SandIndex), TEXT("Texture"), SandBCPath);
	const FString NormR = SetMILayerTextureParameter(MIPath, FString::FromInt(SandIndex), TEXT("Normal"), SandNPath);
	// Soften sand: stock MF_LandscapeLayer CloseRangeTiling=500 turns T_DesertSand into gravel speckles.
	// The So Stylized desert demo uses a very broad world-space sand pattern.  Keep the
	// layer at 6 (not 64): 64 is the accidental coarse override that made the published
	// PlanetGen surface look lumpy rather than like the fine, flowing demo dunes.
	constexpr float SoStylizedDemoCloseRangeTiling = 6.f;
	constexpr float SoStylizedDemoFarRangeTiling = 6.f;
	const FString TileR = SetMILayerScalarParameter(
		MIPath, FString::FromInt(SandIndex), TEXT("CloseRangeTiling"), SoStylizedDemoCloseRangeTiling);
	// The PlanetGen material is a layered material.  A global scalar does not reliably reach the
	// Sand function and can accidentally affect another layer, so set only the two Sand-layer
	// parameters that the function actually exposes.
	const FString FarTileR = SetMILayerScalarParameter(
		MIPath, FString::FromInt(SandIndex), TEXT("FarRangeTiling"), SoStylizedDemoFarRangeTiling);

	UMaterialEditingLibrary::UpdateMaterialInstance(MI);
	MI->MarkPackageDirty();
	TArray<UPackage*> PackagesToSave;
	PackagesToSave.Add(MI->GetOutermost());
	FEditorFileUtils::PromptForCheckoutAndSave(PackagesToSave, false, false);

	if (!TexR.StartsWith(TEXT("OK:")) || !NormR.StartsWith(TEXT("OK:"))
		|| !TileR.StartsWith(TEXT("OK:")) || !FarTileR.StartsWith(TEXT("OK:")))
	{
		return FString::Printf(TEXT("ERR: sand-layer override failed SandIndex=%d name=%s Tex=%s Norm=%s Close=%s Far=%s"),
			SandIndex, *SandName, *TexR, *NormR, *TileR, *FarTileR);
	}

	return FString::Printf(
		TEXT("OK: MI Sand LayerParameter[%d] (%s) -> SoStylized BC+N + demo tiling; Tex=%s; Norm=%s; Close=%s; Far=%s; global parameters untouched"),
		SandIndex, *SandName, *TexR, *NormR, *TileR, *FarTileR);
#else
	return TEXT("ERR: editor-only");
#endif
}


FString URedMMOEditorTools::CreateSoStylizedDesertSparkleLayerTest()
{
#if WITH_EDITOR
	// This is deliberately a one-way, isolated test chain. The old texture-only override cannot
	// reproduce the demo because the gold flecks live in MF_DesertSand -> MF_Sparkle, not in the
	// base-color/normal textures. PlanetGen's M_Planet does not expose a swappable editor Material
	// Layers stack: it contains a direct MaterialFunctionCall to MFI_Sand. Therefore duplicate the
	// parent Material into /Game and replace only that duplicated call. Purchased and production
	// assets remain untouched, and runtime use still requires the explicit -RedSandSparkleT02 flag.
	const FString SourceFunctionPath = TEXT("/Game/SoStylized/Materials/MF_DesertSand.MF_DesertSand");
	const FString SourceParentPath = TEXT("/PlanetGen/Materials/Landscape/M_Planet.M_Planet");
	const FString SourceBiomePath = TEXT("/Game/RedMMO/Materials/MI_PlanetBiome_RED.MI_PlanetBiome_RED");
	const FString TestRoot = TEXT("/Game/RedMMO/Materials/DesertSparkleTest");
	const FString FunctionInstancePackageName = TestRoot + TEXT("/MFI_DesertSandSparkle_T02");
	const FString FunctionInstanceObjectPath = FunctionInstancePackageName + TEXT(".MFI_DesertSandSparkle_T02");
	const FString TestParentPackageName = TestRoot + TEXT("/M_Planet_DesertSparkle_T02");
	const FString TestParentObjectPath = TestParentPackageName + TEXT(".M_Planet_DesertSparkle_T02");
	const FString TestBiomePackageName = TestRoot + TEXT("/MI_PlanetBiome_DesertSparkle_T02");
	const FString TestBiomeObjectPath = TestBiomePackageName + TEXT(".MI_PlanetBiome_DesertSparkle_T02");

	auto DestinationIsUnused = [](const FString& PackageName, const FString& ObjectPath, FString& OutError)
	{
		if (FindObject<UObject>(nullptr, *ObjectPath) || FPackageName::DoesPackageExist(PackageName))
		{
			OutError = FString::Printf(
				TEXT("ERR: isolated sparkle-test destination already exists: %s (will not overwrite it)"),
				*ObjectPath);
			return false;
		}
		return true;
	};

	auto SaveOnlyThisProjectAsset = [](UPackage* Package, UObject* Asset, FString& OutError)
	{
		if (!Package || !Asset || !Package->GetName().StartsWith(TEXT("/Game/")))
		{
			OutError = TEXT("ERR: save helper received a non-project package");
			return false;
		}
		const FString OutputFilename = FPackageName::LongPackageNameToFilename(
			Package->GetName(), FPackageName::GetAssetPackageExtension());
		IFileManager::Get().MakeDirectory(*FPaths::GetPath(OutputFilename), true);
		FSavePackageArgs SaveArgs;
		SaveArgs.TopLevelFlags = RF_Public | RF_Standalone;
		SaveArgs.SaveFlags = SAVE_NoError;
		if (!UPackage::SavePackage(Package, Asset, *OutputFilename, SaveArgs))
		{
			OutError = FString::Printf(TEXT("ERR: failed to save %s"), *OutputFilename);
			return false;
		}
		return true;
	};

	FString DestinationError;
	if (!DestinationIsUnused(FunctionInstancePackageName, FunctionInstanceObjectPath, DestinationError)
		|| !DestinationIsUnused(TestParentPackageName, TestParentObjectPath, DestinationError)
		|| !DestinationIsUnused(TestBiomePackageName, TestBiomeObjectPath, DestinationError))
	{
		return DestinationError;
	}

	UMaterialFunction* SourceFunction = LoadObject<UMaterialFunction>(nullptr, *SourceFunctionPath);
	UMaterial* SourceParent = LoadObject<UMaterial>(nullptr, *SourceParentPath);
	UMaterialInstanceConstant* SourceBiome = LoadObject<UMaterialInstanceConstant>(nullptr, *SourceBiomePath);
	if (!SourceFunction || !SourceParent || !SourceBiome)
	{
		return FString::Printf(TEXT("ERR: missing source Function=%s Parent=%s BiomeMI=%s"),
			SourceFunction ? TEXT("ok") : *SourceFunctionPath,
			SourceParent ? TEXT("ok") : *SourceParentPath,
			SourceBiome ? TEXT("ok") : *SourceBiomePath);
	}

	UPackage* FunctionInstancePackage = CreatePackage(*FunctionInstancePackageName);
	UMaterialFunctionInstance* DesertMFI = FunctionInstancePackage
		? NewObject<UMaterialFunctionInstance>(
			FunctionInstancePackage, TEXT("MFI_DesertSandSparkle_T02"),
			RF_Public | RF_Standalone | RF_Transactional)
		: nullptr;
	if (!DesertMFI)
	{
		return TEXT("ERR: could not create the project-owned desert-sand function instance");
	}
	DesertMFI->SetParent(SourceFunction);
	DesertMFI->UpdateParameterSet();

	auto SetScalar = [DesertMFI](const FName Name, const float Value)
	{
		for (FScalarParameterValue& Parameter : DesertMFI->ScalarParameterValues)
		{
			if (Parameter.ParameterInfo.Name == Name)
			{
				Parameter.ParameterValue = Value;
				return;
			}
		}
		DesertMFI->ScalarParameterValues.Emplace(FMaterialParameterInfo(Name), Value);
	};
	auto SetSwitch = [DesertMFI](const FName Name, const bool bValue)
	{
		for (FStaticSwitchParameter& Parameter : DesertMFI->StaticSwitchParameterValues)
		{
			if (Parameter.ParameterInfo.Name == Name)
			{
				Parameter.Value = bValue;
				Parameter.bOverride = true;
				return;
			}
		}
		DesertMFI->StaticSwitchParameterValues.Emplace(
			FMaterialParameterInfo(Name), bValue, true, FGuid());
	};
	auto SetVector = [DesertMFI](const FName Name, const FLinearColor& Value)
	{
		for (FVectorParameterValue& Parameter : DesertMFI->VectorParameterValues)
		{
			if (Parameter.ParameterInfo.Name == Name)
			{
				Parameter.ParameterValue = Value;
				return;
			}
		}
		FVectorParameterValue NewParameter;
		NewParameter.ParameterInfo = FMaterialParameterInfo(Name);
		NewParameter.ParameterValue = Value;
		DesertMFI->VectorParameterValues.Add(NewParameter);
	};

	// Preserve the demo's fine grain/ripple scale but restrain the emissive sparkle for the
	// brighter RED Mars presentation.  The 3D projection switch is required on a sphere;
	// the flat demo leaves it off because a Landscape has one stable planar projection.
	SetScalar(TEXT("Desert Sand Scale"), 1024.f);
	SetScalar(TEXT("Desert Sand Normal Texture Scale"), 2400.f);
	SetScalar(TEXT("Desert Sand Roughness Min"), 0.5f);
	SetScalar(TEXT("Desert Sand Roughness Max"), 0.7f);
	SetScalar(TEXT("Desert Sand Specular"), 0.2f);
	SetScalar(TEXT("Desert Sparkle Scale"), 1600.f);
	SetScalar(TEXT("Desert Sparkle Brightness"), 2.5f);
	SetScalar(TEXT("Desert Sparkle Contrast"), 8.f);
	SetScalar(TEXT("Desert Sparkle Tolerance"), 0.82f);
	SetScalar(TEXT("Desert Sparkle Speed"), 0.35f);
	SetScalar(TEXT("Desert Sparkle Fade Start"), 750.f);
	SetScalar(TEXT("Desert Sparkle Fade End"), 3500.f);
	SetScalar(TEXT("Desert Sparkle Shrink Amount"), 0.3f);
	SetScalar(TEXT("Desert Sparkle Shrink Near Distance"), 500.f);
	SetScalar(TEXT("Desert Sparkle Shrink Far Distance"), 2500.f);
	// Vendor spelling intentionally contains two spaces between "Sparkle" and "Color".
	SetVector(TEXT("Desert Sparkle  Color"), FLinearColor(1.0f, 0.78f, 0.35f, 1.0f));
	SetSwitch(TEXT("DesertSandSparkle?"), true);
	SetSwitch(TEXT("SandRippleNormals?"), true);
	// Match the vendor demo's proven sparkle projection branch. The 3D projection path
	// compiles on the PlanetGen sphere but produces no readable sparkle in real-GPU captures.
	SetSwitch(TEXT("SparkleProject3D?"), false);
	SetSwitch(TEXT("SparklShrinkNear?"), true);
	SetSwitch(TEXT("SparkleIntensityVariance?"), true);
	SetSwitch(TEXT("SparkleDayAndWeather?"), false);
	SetSwitch(TEXT("SimpleSparkle?"), false);
	SetSwitch(TEXT("NeedWorldRotation?"), true);
	DesertMFI->UpdateParameterSet();
	DesertMFI->MarkPackageDirty();

	UPackage* TestParentPackage = CreatePackage(*TestParentPackageName);
	UMaterial* TestParent = TestParentPackage
		? Cast<UMaterial>(StaticDuplicateObject(
			SourceParent, TestParentPackage, TEXT("M_Planet_DesertSparkle_T02"),
			RF_Public | RF_Standalone | RF_Transactional))
		: nullptr;
	if (!TestParent)
	{
		return TEXT("ERR: could not duplicate PlanetGen M_Planet into the project test sandbox");
	}

	int32 ReplacedSandCalls = 0;
	for (UMaterialExpression* Expression : TestParent->GetExpressions())
	{
		UMaterialExpressionMaterialFunctionCall* FunctionCall =
			Cast<UMaterialExpressionMaterialFunctionCall>(Expression);
		if (FunctionCall && GetNameSafe(FunctionCall->MaterialFunction).Equals(TEXT("MFI_Sand")))
		{
			FunctionCall->Modify();
			FunctionCall->SetMaterialFunction(DesertMFI);
			++ReplacedSandCalls;
		}
	}
	if (ReplacedSandCalls != 1)
	{
		return FString::Printf(
			TEXT("ERR: duplicated PlanetGen parent contained %d exact MFI_Sand calls; expected one; no test asset was saved"),
			ReplacedSandCalls);
	}
	TestParent->MarkPackageDirty();
	UMaterialEditingLibrary::RecompileMaterial(TestParent);

	UPackage* TestBiomePackage = CreatePackage(*TestBiomePackageName);
	UMaterialInstanceConstant* TestBiome = TestBiomePackage
		? Cast<UMaterialInstanceConstant>(StaticDuplicateObject(
			SourceBiome, TestBiomePackage, TEXT("MI_PlanetBiome_DesertSparkle_T02"),
			RF_Public | RF_Standalone | RF_Transactional))
		: nullptr;
	if (!TestBiome)
	{
		return TEXT("ERR: could not duplicate the PlanetGen biome MI for sparkle testing");
	}

	UMaterialEditingLibrary::SetMaterialInstanceParent(TestBiome, TestParent);
	TestBiome->MarkPackageDirty();
	UMaterialEditingLibrary::UpdateMaterialInstance(TestBiome);

	// Validate the entire in-memory graph before persisting any part of the test chain. This
	// prevents the invalid T01/T02 partial-asset pattern from recurring after an early error.
	if (TestBiome->Parent != TestParent)
	{
		return TEXT("ERR: duplicated biome MI did not accept the duplicated PlanetGen parent; no test asset was saved");
	}

	FAssetRegistryModule::AssetCreated(DesertMFI);
	FAssetRegistryModule::AssetCreated(TestParent);
	FAssetRegistryModule::AssetCreated(TestBiome);
	FString SaveError;
	if (!SaveOnlyThisProjectAsset(FunctionInstancePackage, DesertMFI, SaveError)
		|| !SaveOnlyThisProjectAsset(TestParentPackage, TestParent, SaveError)
		|| !SaveOnlyThisProjectAsset(TestBiomePackage, TestBiome, SaveError))
	{
		return SaveError;
	}

	return FString::Printf(
		TEXT("OK: created isolated fine-sand sparkle chain. ReplacedCalls=%d; MFI=%s; Parent=%s; TestBiome=%s. No runtime map, production material, or plugin asset was changed."),
		ReplacedSandCalls, *FunctionInstanceObjectPath, *TestParentObjectPath, *TestBiomeObjectPath);
#else
	return TEXT("ERR: editor-only");
#endif
}


FString URedMMOEditorTools::TuneSoStylizedDesertSparkleLayerTest(
	const float SparkleBrightness,
	const float SparkleTolerance)
{
#if WITH_EDITOR
	const FString MFIPath = TEXT("/Game/RedMMO/Materials/DesertSparkleTest/MFI_DesertSandSparkle_T02.MFI_DesertSandSparkle_T02");
	const FString ParentPath = TEXT("/Game/RedMMO/Materials/DesertSparkleTest/M_Planet_DesertSparkle_T02.M_Planet_DesertSparkle_T02");
	const FString BiomePath = TEXT("/Game/RedMMO/Materials/DesertSparkleTest/MI_PlanetBiome_DesertSparkle_T02.MI_PlanetBiome_DesertSparkle_T02");
	const FString SourceFunctionPath = TEXT("/Game/SoStylized/Materials/MF_DesertSand.MF_DesertSand");
	UMaterialFunctionInstance* DesertMFI = LoadObject<UMaterialFunctionInstance>(nullptr, *MFIPath);
	UMaterial* TestParent = LoadObject<UMaterial>(nullptr, *ParentPath);
	UMaterialInstanceConstant* TestBiome = LoadObject<UMaterialInstanceConstant>(nullptr, *BiomePath);
	UMaterialFunction* SourceFunction = LoadObject<UMaterialFunction>(nullptr, *SourceFunctionPath);
	if (!DesertMFI || !TestParent || !TestBiome || !SourceFunction)
	{
		return FString::Printf(TEXT("ERR: incomplete T02 chain MFI=%s Parent=%s Biome=%s SourceFunction=%s"),
			DesertMFI ? TEXT("ok") : TEXT("missing"),
			TestParent ? TEXT("ok") : TEXT("missing"),
			TestBiome ? TEXT("ok") : TEXT("missing"),
			SourceFunction ? TEXT("ok") : TEXT("missing"));
	}
	if (TestBiome->Parent != TestParent)
	{
		return TEXT("ERR: T02 biome MI no longer references the isolated PlanetGen parent");
	}
	int32 MatchingCalls = 0;
	bool bRewiredToSourceFunction = false;
	UMaterialExpressionMaterialFunctionCall* DesertCall = nullptr;
	for (UMaterialExpression* Expression : TestParent->GetExpressions())
	{
		UMaterialExpressionMaterialFunctionCall* FunctionCall =
			Cast<UMaterialExpressionMaterialFunctionCall>(Expression);
		if (FunctionCall
			&& (FunctionCall->MaterialFunction == DesertMFI || FunctionCall->MaterialFunction == SourceFunction))
		{
			++MatchingCalls;
			DesertCall = FunctionCall;
			if (FunctionCall->MaterialFunction != SourceFunction)
			{
				FunctionCall->Modify();
				FunctionCall->SetMaterialFunction(SourceFunction);
				bRewiredToSourceFunction = true;
			}
		}
	}
	if (MatchingCalls != 1)
	{
		return FString::Printf(TEXT("ERR: isolated parent contains %d T02 desert function calls; expected one"), MatchingCalls);
	}

	// SetMaterialFunction remaps downstream links strictly by output name. PlanetGen's MFI_Sand
	// output is named "Material Attributes", while the vendor MF_DesertSand output is named
	// "Attributes"; UE therefore clears the original Top Material connection during the swap.
	// Repair that one project-owned graph edge explicitly and fail closed if the graph shape is
	// ambiguous. This is deliberately idempotent for subsequent tuning passes.
	UMaterialExpressionMaterialFunctionCall* ConnectedSandBlend = nullptr;
	UMaterialExpressionMaterialFunctionCall* DisconnectedSandBlend = nullptr;
	int32 ConnectedSandBlendCount = 0;
	int32 DisconnectedSandBlendCount = 0;
	for (UMaterialExpression* Expression : TestParent->GetExpressions())
	{
		UMaterialExpressionMaterialFunctionCall* FunctionCall =
			Cast<UMaterialExpressionMaterialFunctionCall>(Expression);
		if (!FunctionCall || !FunctionCall->MaterialFunction
			|| !GetNameSafe(FunctionCall->MaterialFunction).Equals(TEXT("MatLayerBlend_Standard")))
		{
			continue;
		}

		for (FFunctionExpressionInput& FunctionInput : FunctionCall->FunctionInputs)
		{
			if (FunctionInput.Input.InputName != FName(TEXT("Top Material")))
			{
				continue;
			}
			if (FunctionInput.Input.Expression == DesertCall)
			{
				ConnectedSandBlend = FunctionCall;
				++ConnectedSandBlendCount;
			}
			else if (!FunctionInput.Input.Expression)
			{
				DisconnectedSandBlend = FunctionCall;
				++DisconnectedSandBlendCount;
			}
		}
	}

	if (ConnectedSandBlendCount == 0)
	{
		TestParent->Modify();
		DesertCall->Modify();
		if (DisconnectedSandBlend)
		{
			DisconnectedSandBlend->Modify();
		}
		if (DisconnectedSandBlendCount != 1 || !DisconnectedSandBlend
			|| !UMaterialEditingLibrary::ConnectMaterialExpressions(
				DesertCall, TEXT("Attributes"), DisconnectedSandBlend, TEXT("Top Material")))
		{
			return FString::Printf(
				TEXT("ERR: could not uniquely reconnect vendor desert output; connected=%d disconnected=%d"),
				ConnectedSandBlendCount, DisconnectedSandBlendCount);
		}
		ConnectedSandBlend = DisconnectedSandBlend;
		ConnectedSandBlendCount = 1;
	}
	if (ConnectedSandBlendCount != 1 || !ConnectedSandBlend)
	{
		return FString::Printf(
			TEXT("ERR: isolated parent has %d vendor-desert Top Material consumers; expected one"),
			ConnectedSandBlendCount);
	}
	bool bConnectionVerified = false;
	for (const FFunctionExpressionInput& FunctionInput : ConnectedSandBlend->FunctionInputs)
	{
		if (FunctionInput.Input.InputName == FName(TEXT("Top Material"))
			&& FunctionInput.Input.Expression == DesertCall)
		{
			bConnectionVerified = true;
			break;
		}
	}
	if (!bConnectionVerified)
	{
		return TEXT("ERR: vendor desert Top Material connection did not survive immediate readback");
	}
	// Use the raw purchased function in the project-owned parent, matching the vendor demo. This
	// exposes real global parameter GUIDs to the final MI; an intermediate function instance made
	// values readable but prevented the final MI from creating valid overrides.
	TestParent->PostEditChange();
	TestParent->MarkPackageDirty();
	UMaterialEditingLibrary::RecompileMaterial(TestParent);
	UMaterialEditingLibrary::UpdateMaterialInstance(TestBiome);
	if (bRewiredToSourceFunction)
	{
		const FString ParentFilename = FPackageName::LongPackageNameToFilename(
			TestParent->GetOutermost()->GetName(), FPackageName::GetAssetPackageExtension());
		FSavePackageArgs ParentSaveArgs;
		ParentSaveArgs.TopLevelFlags = RF_Public | RF_Standalone;
		ParentSaveArgs.SaveFlags = SAVE_NoError;
		if (!UPackage::SavePackage(
			TestParent->GetOutermost(), TestParent, *ParentFilename, ParentSaveArgs))
		{
			return TEXT("ERR: failed to persist the isolated direct vendor-function rewire");
		}
		return TEXT("OK: rewired the isolated PlanetGen parent to the direct vendor desert function; rerun tune to apply final-MI demo overrides");
	}

	// The vendor demo's value of 15 is tuned for its brighter landscape/exposure stack. PlanetGen's
	// layered planet path attenuates the sparkle enough that 15 was visually absent in a real-GPU
	// capture. Keep a bounded diagnostic range so the isolated test can establish a readable level
	// without touching the purchased function or the production material.
	const float SafeBrightness = FMath::Clamp(SparkleBrightness, 0.0f, 200.0f);
	const float SafeTolerance = FMath::Clamp(SparkleTolerance, 0.0f, 1.0f);
	auto SetScalar = [DesertMFI](const FName Name, const float Value)
	{
		for (FScalarParameterValue& Parameter : DesertMFI->ScalarParameterValues)
		{
			if (Parameter.ParameterInfo.Name == Name)
			{
				Parameter.ParameterValue = Value;
				return;
			}
		}
		DesertMFI->ScalarParameterValues.Emplace(FMaterialParameterInfo(Name), Value);
	};
	auto SetSwitch = [DesertMFI](const FName Name, const bool bValue)
	{
		for (FStaticSwitchParameter& Parameter : DesertMFI->StaticSwitchParameterValues)
		{
			if (Parameter.ParameterInfo.Name == Name)
			{
				Parameter.Value = bValue;
				Parameter.bOverride = true;
				return;
			}
		}
		DesertMFI->StaticSwitchParameterValues.Emplace(
			FMaterialParameterInfo(Name), bValue, true, FGuid());
	};

	// Synchronize with the vendor function first, then re-apply every branch switch. Calling
	// UpdateParameterSet after setting switches can rebuild the array and silently discard an
	// override; the order here makes the compiled branch deterministic and preserves valid GUIDs.
	DesertMFI->UpdateParameterSet();
	SetScalar(TEXT("Desert Sparkle Brightness"), SafeBrightness);
	SetScalar(TEXT("Desert Sparkle Tolerance"), SafeTolerance);
	SetScalar(TEXT("Desert Sparkle Speed"), 1.0f);
	SetScalar(TEXT("Desert Sparkle Fade Start"), 1000.0f);
	SetScalar(TEXT("Desert Sparkle Fade End"), 5000.0f);
	SetSwitch(TEXT("DesertSandSparkle?"), true);
	SetSwitch(TEXT("SandRippleNormals?"), true);
	SetSwitch(TEXT("SparkleProject3D?"), false);
	SetSwitch(TEXT("SparklShrinkNear?"), true);
	SetSwitch(TEXT("SparkleIntensityVariance?"), true);
	SetSwitch(TEXT("SparkleDayAndWeather?"), true);
	SetSwitch(TEXT("SimpleSparkle?"), false);
	SetSwitch(TEXT("NeedWorldRotation?"), true);
	DesertMFI->PostEditChange();
	DesertMFI->MarkPackageDirty();

	// The vendor demo activates these global parameters on its final material instance. Mirror
	// that supported path on our isolated PlanetGen MI so Unreal resolves the real expression
	// GUIDs; function-instance switches alone can serialize with zero GUIDs and be ignored.
	TArray<FString> FailedFinalOverrides;
	auto SetFinalScalar = [TestBiome, &FailedFinalOverrides](const TCHAR* Name, const float Value)
	{
		const FName ParameterName(Name);
		// UE 5.8's MaterialEditingLibrary setter writes the value but currently returns false
		// unconditionally (MaterialEditingLibrary.cpp:1485-1493). Verify the resulting override
		// instead of treating that broken return value as a failed write.
		UMaterialEditingLibrary::SetMaterialInstanceScalarParameterValue(TestBiome, ParameterName, Value);
		if (!UMaterialEditingLibrary::IsMaterialInstanceParameterOverridden(TestBiome, ParameterName))
		{
			FailedFinalOverrides.Add(Name);
		}
	};
	auto SetFinalSwitch = [TestBiome, &FailedFinalOverrides](const TCHAR* Name, const bool bValue)
	{
		const FName ParameterName(Name);
		UMaterialEditingLibrary::SetMaterialInstanceStaticSwitchParameterValue(
			TestBiome, ParameterName, bValue, EMaterialParameterAssociation::GlobalParameter, false);
		if (!UMaterialEditingLibrary::IsMaterialInstanceParameterOverridden(TestBiome, ParameterName))
		{
			FailedFinalOverrides.Add(Name);
		}
	};
	SetFinalScalar(TEXT("Desert Sand Scale"), 1024.0f);
	SetFinalScalar(TEXT("Desert Sand Normal Texture Scale"), 2400.0f);
	SetFinalScalar(TEXT("Desert Sparkle Scale"), 1600.0f);
	SetFinalScalar(TEXT("Desert Sparkle Brightness"), SafeBrightness);
	SetFinalScalar(TEXT("Desert Sparkle Contrast"), 8.0f);
	SetFinalScalar(TEXT("Desert Sparkle Tolerance"), SafeTolerance);
	SetFinalScalar(TEXT("Desert Sparkle Speed"), 1.0f);
	SetFinalScalar(TEXT("Desert Sparkle Fade Start"), 1000.0f);
	SetFinalScalar(TEXT("Desert Sparkle Fade End"), 5000.0f);
	SetFinalScalar(TEXT("Desert Sparkle Shrink Amount"), 0.3f);
	SetFinalScalar(TEXT("Desert Sparkle Shrink Near Distance"), 500.0f);
	SetFinalScalar(TEXT("Desert Sparkle Shrink Far Distance"), 2500.0f);
	const FName SparkleColorName(TEXT("Desert Sparkle  Color"));
	UMaterialEditingLibrary::SetMaterialInstanceVectorParameterValue(
		TestBiome, SparkleColorName, FLinearColor(1.0f, 0.78f, 0.35f, 1.0f));
	if (!UMaterialEditingLibrary::IsMaterialInstanceParameterOverridden(TestBiome, SparkleColorName))
	{
		FailedFinalOverrides.Add(TEXT("Desert Sparkle Color"));
	}
	SetFinalSwitch(TEXT("DesertSandSparkle?"), true);
	SetFinalSwitch(TEXT("SandRippleNormals?"), true);
	SetFinalSwitch(TEXT("SparkleProject3D?"), false);
	SetFinalSwitch(TEXT("SparklShrinkNear?"), true);
	SetFinalSwitch(TEXT("SparkleIntensityVariance?"), true);
	SetFinalSwitch(TEXT("SparkleDayAndWeather?"), false);
	SetFinalSwitch(TEXT("SimpleSparkle?"), false);
	SetFinalSwitch(TEXT("NeedWorldRotation?"), true);
	if (FailedFinalOverrides.Num() > 0)
	{
		return FString::Printf(
			TEXT("ERR: vendor demo parameter(s) not exposed by isolated PlanetGen chain: %s"),
			*FString::Join(FailedFinalOverrides, TEXT(", ")));
	}

	// Material-function changes are not guaranteed to invalidate an already compiled duplicated
	// parent in a commandlet. Recompile and persist the whole isolated chain, never the plugin or
	// production material, so the next GPU run sees the new static permutation.
	TestParent->PostEditChange();
	TestParent->MarkPackageDirty();
	UMaterialEditingLibrary::RecompileMaterial(TestParent);
	UMaterialEditingLibrary::UpdateMaterialInstance(TestBiome);
	TestBiome->MarkPackageDirty();

	auto SaveProjectAsset = [](UObject* Asset)
	{
		if (!Asset || !Asset->GetOutermost()->GetName().StartsWith(TEXT("/Game/")))
		{
			return false;
		}
		const FString Filename = FPackageName::LongPackageNameToFilename(
			Asset->GetOutermost()->GetName(), FPackageName::GetAssetPackageExtension());
		FSavePackageArgs SaveArgs;
		SaveArgs.TopLevelFlags = RF_Public | RF_Standalone;
		SaveArgs.SaveFlags = SAVE_NoError;
		return UPackage::SavePackage(Asset->GetOutermost(), Asset, *Filename, SaveArgs);
	};
	if (!SaveProjectAsset(DesertMFI) || !SaveProjectAsset(TestParent) || !SaveProjectAsset(TestBiome))
	{
		return TEXT("ERR: failed to save the recompiled isolated T02 material chain");
	}

	float VerifyBrightness = -1.0f;
	float VerifyTolerance = -1.0f;
	for (const FScalarParameterValue& Parameter : DesertMFI->ScalarParameterValues)
	{
		if (Parameter.ParameterInfo.Name == FName(TEXT("Desert Sparkle Brightness")))
		{
			VerifyBrightness = Parameter.ParameterValue;
		}
		else if (Parameter.ParameterInfo.Name == FName(TEXT("Desert Sparkle Tolerance")))
		{
			VerifyTolerance = Parameter.ParameterValue;
		}
	}
	FString SwitchSummary;
	for (const FStaticSwitchParameter& Parameter : DesertMFI->StaticSwitchParameterValues)
	{
		SwitchSummary += FString::Printf(TEXT("%s=%d/override=%d/guid=%d;"),
			*Parameter.ParameterInfo.Name.ToString(), Parameter.Value ? 1 : 0,
			Parameter.bOverride ? 1 : 0, Parameter.ExpressionGUID.IsValid() ? 1 : 0);
	}
	return FString::Printf(
		TEXT("OK: tuned and recompiled isolated T02 sparkle brightness=%.3f tolerance=%.3f verifyBrightness=%.3f verifyTolerance=%.3f references=%d switches=[%s]"),
		SafeBrightness, SafeTolerance, VerifyBrightness, VerifyTolerance, MatchingCalls, *SwitchSummary);
#else
	return TEXT("ERR: editor-only");
#endif
}



FString URedMMOEditorTools::SnapSelectedStaticMeshActorsToPlanetSurface(float SurfaceOffsetCm)
{
#if WITH_EDITOR
	if (!GEditor || !FMath::IsFinite(SurfaceOffsetCm))
	{
		return TEXT("ERR: editor is unavailable or surface offset is not finite");
	}

	UEditorActorSubsystem* ActorSubsystem = GEditor->GetEditorSubsystem<UEditorActorSubsystem>();
	UWorld* World = GEditor->GetEditorWorldContext().World();
	if (!ActorSubsystem || !World || World->WorldType != EWorldType::Editor)
	{
		return TEXT("ERR: open a non-PIE editor world before snapping selected actors");
	}

	const FString WorldPackage = World->GetOutermost()->GetName();
	static const TSet<FString> ProtectedWorldPackages =
	{
		TEXT("/Game/RedMMO/Maps/RedPlanetGen"),
		TEXT("/Game/RedMMO/Maps/RedPlanetGen_50km_Test"),
		TEXT("/Game/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype")
	};
	if (ProtectedWorldPackages.Contains(WorldPackage))
	{
		return FString::Printf(
			TEXT("ERR: refusing protected world %s; duplicate it under /Game/RedMMO/Maps/Tests first"),
			*WorldPackage);
	}

	FVector PlanetCenter = FVector::ZeroVector;
	float DatumRadius = 0.0f;
	float PeakRadius = 0.0f;
	if (!RedGravity::FindMeshPlanet(World, PlanetCenter, DatumRadius, &PeakRadius)
		|| DatumRadius <= KINDA_SMALL_NUMBER || PeakRadius <= DatumRadius)
	{
		return TEXT("ERR: no valid PlanetGen terrain frame is active in this editor world");
	}

	struct FSnapPlan
	{
		TWeakObjectPtr<AStaticMeshActor> Actor;
		FVector Location = FVector::ZeroVector;
		FQuat Rotation = FQuat::Identity;
	};

	TArray<FSnapPlan> Plans;
	int32 SkippedNotStaticMesh = 0;
	int32 SkippedAttached = 0;
	int32 SkippedNoTerrainHit = 0;
	const TArray<AActor*> SelectedActors = ActorSubsystem->GetSelectedLevelActors();
	for (AActor* SelectedActor : SelectedActors)
	{
		AStaticMeshActor* StaticMeshActor = Cast<AStaticMeshActor>(SelectedActor);
		if (!IsValid(StaticMeshActor) || StaticMeshActor->GetWorld() != World
			|| !StaticMeshActor->GetStaticMeshComponent()
			|| !StaticMeshActor->GetStaticMeshComponent()->GetStaticMesh())
		{
			++SkippedNotStaticMesh;
			continue;
		}
		if (StaticMeshActor->GetAttachParentActor())
		{
			++SkippedAttached;
			continue;
		}

		const FVector RadialUp = (StaticMeshActor->GetActorLocation() - PlanetCenter).GetSafeNormal();
		if (RadialUp.IsNearlyZero())
		{
			++SkippedNoTerrainHit;
			continue;
		}

		FHitResult SurfaceHit;
		const ERedPlanetTerrainQueryResult QueryResult = RedPlanetTerrainQuery::LineTrace(
			World,
			PlanetCenter,
			PlanetCenter + RadialUp * (PeakRadius + 5000.0f),
			PlanetCenter + RadialUp * DatumRadius,
			SurfaceHit);
		if (QueryResult != ERedPlanetTerrainQueryResult::Hit
			|| !FMath::IsFinite(SurfaceHit.ImpactPoint.X)
			|| !FMath::IsFinite(SurfaceHit.ImpactPoint.Y)
			|| !FMath::IsFinite(SurfaceHit.ImpactPoint.Z))
		{
			++SkippedNoTerrainHit;
			continue;
		}

		FVector TangentHeading = FVector::VectorPlaneProject(
			StaticMeshActor->GetActorForwardVector(), RadialUp).GetSafeNormal();
		if (TangentHeading.IsNearlyZero())
		{
			const FVector TangentRight = FVector::VectorPlaneProject(
				StaticMeshActor->GetActorRightVector(), RadialUp).GetSafeNormal();
			TangentHeading = FVector::CrossProduct(TangentRight, RadialUp).GetSafeNormal();
		}
		if (TangentHeading.IsNearlyZero())
		{
			FVector FallbackAxis;
			FVector UnusedAxis;
			RadialUp.FindBestAxisVectors(FallbackAxis, UnusedAxis);
			TangentHeading = FallbackAxis;
		}

		FSnapPlan& Plan = Plans.AddDefaulted_GetRef();
		Plan.Actor = StaticMeshActor;
		Plan.Location = SurfaceHit.ImpactPoint + RadialUp * SurfaceOffsetCm;
		Plan.Rotation = FRotationMatrix::MakeFromZX(RadialUp, TangentHeading).ToQuat();
	}

	if (Plans.IsEmpty())
	{
		return FString::Printf(
			TEXT("ERR: no selected actor could be snapped (notStaticMesh=%d attached=%d noTerrainHit=%d)"),
			SkippedNotStaticMesh, SkippedAttached, SkippedNoTerrainHit);
	}

	const FScopedTransaction Transaction(
		NSLOCTEXT("RedMMOEditorTools", "SnapSelectedStaticMeshesToPlanet", "Snap selected meshes to planet"));
	int32 Snapped = 0;
	for (const FSnapPlan& Plan : Plans)
	{
		AStaticMeshActor* StaticMeshActor = Plan.Actor.Get();
		if (!IsValid(StaticMeshActor))
		{
			continue;
		}
		StaticMeshActor->Modify();
		StaticMeshActor->SetActorLocationAndRotation(
			Plan.Location, Plan.Rotation, false, nullptr, ETeleportType::TeleportPhysics);
		StaticMeshActor->PostEditMove(true);
		++Snapped;
	}
	GEditor->RedrawLevelEditingViewports(false);

	return FString::Printf(
		TEXT("OK: snapped=%d offset=%.2fcm skipped(notStaticMesh=%d attached=%d noTerrainHit=%d) world=%s"),
		Snapped, SurfaceOffsetCm, SkippedNotStaticMesh, SkippedAttached, SkippedNoTerrainHit,
		*WorldPackage);
#else
	return TEXT("ERR: editor-only");
#endif
}


FString URedMMOEditorTools::SetLayeredBlendBranchBone(const FString& AnimBlueprintPath, const FString& NewBoneName)
{
#if WITH_EDITOR
	UAnimBlueprint* ABP = LoadObject<UAnimBlueprint>(nullptr, *AnimBlueprintPath);
	if (!ABP)
	{
		return TEXT("ERR: AnimBlueprint not found");
	}
	int32 Changed = 0;
	TArray<UEdGraph*> Graphs;
	ABP->GetAllGraphs(Graphs);
	for (UEdGraph* Graph : Graphs)
	{
		for (UEdGraphNode* Node : Graph->Nodes)
		{
			if (UAnimGraphNode_LayeredBoneBlend* Layered = Cast<UAnimGraphNode_LayeredBoneBlend>(Node))
			{
				Layered->Modify();
				for (FInputBlendPose& Layer : Layered->Node.LayerSetup)
				{
					for (FBranchFilter& Filter : Layer.BranchFilters)
					{
						Filter.BoneName = FName(*NewBoneName);
						++Changed;
					}
				}
			}
		}
	}
	if (Changed > 0)
	{
		FBlueprintEditorUtils::MarkBlueprintAsModified(ABP);
		FKismetEditorUtilities::CompileBlueprint(ABP);
	}
	return FString::Printf(TEXT("OK: %d branch filter(s) -> %s"), Changed, *NewBoneName);
#else
	return TEXT("ERR: editor-only");
#endif
}


FString URedMMOEditorTools::SetAnimNodeAlphaBool(const FString& AnimBlueprintPath, const FString& NodeClassContains, bool bEnabled)
{
#if WITH_EDITOR
	UAnimBlueprint* ABP = LoadObject<UAnimBlueprint>(nullptr, *AnimBlueprintPath);
	if (!ABP)
	{
		return TEXT("ERR: AnimBlueprint not found");
	}
	int32 Changed = 0;
	TArray<UEdGraph*> Graphs;
	ABP->GetAllGraphs(Graphs);
	for (UEdGraph* Graph : Graphs)
	{
		for (UEdGraphNode* Node : Graph->Nodes)
		{
			if (!Node || !Node->GetClass()->GetName().Contains(NodeClassContains))
			{
				continue;
			}
			// Find the FAnimNode_* payload struct property named "Node", then its bAlphaBoolEnabled.
			for (TFieldIterator<FStructProperty> It(Node->GetClass()); It; ++It)
			{
				if (It->GetName() != TEXT("Node"))
				{
					continue;
				}
				void* NodePtr = It->ContainerPtrToValuePtr<void>(Node);
				for (TFieldIterator<FBoolProperty> BoolIt(It->Struct); BoolIt; ++BoolIt)
				{
					if (BoolIt->GetName() == TEXT("bAlphaBoolEnabled"))
					{
						Node->Modify();
						BoolIt->SetPropertyValue(BoolIt->ContainerPtrToValuePtr<void>(NodePtr), bEnabled);
						++Changed;
					}
				}
			}
		}
	}
	if (Changed > 0)
	{
		FBlueprintEditorUtils::MarkBlueprintAsModified(ABP);
		FKismetEditorUtilities::CompileBlueprint(ABP);
	}
	return FString::Printf(TEXT("OK: %d node(s) [%s] bAlphaBoolEnabled=%s"), Changed, *NodeClassContains, bEnabled ? TEXT("true") : TEXT("false"));
#else
	return TEXT("ERR: editor-only");
#endif
}

FString URedMMOEditorTools::ReparentBlueprint(const FString& BlueprintPath, const FString& NewParentClassPath)
{
#if WITH_EDITOR
	UBlueprint* BP = LoadObject<UBlueprint>(nullptr, *BlueprintPath);
	if (!BP)
	{
		return FString::Printf(TEXT("ERR: Blueprint not found: %s"), *BlueprintPath);
	}
	UClass* NewParent = LoadClass<UObject>(nullptr, *NewParentClassPath);
	if (!NewParent)
	{
		// Also try soft class path form without trailing _C
		NewParent = FindObject<UClass>(nullptr, *NewParentClassPath);
	}
	if (!NewParent)
	{
		return FString::Printf(TEXT("ERR: parent class not found: %s"), *NewParentClassPath);
	}
	if (!NewParent->IsChildOf(AActor::StaticClass()) && !NewParent->IsChildOf(UObject::StaticClass()))
	{
		return FString::Printf(TEXT("ERR: invalid parent class: %s"), *NewParentClassPath);
	}

	const FString OldParent = GetNameSafe(BP->ParentClass);
	BP->Modify();
	BP->ParentClass = NewParent;
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP);
	FKismetEditorUtilities::CompileBlueprint(BP);

	const FString PackageName = BP->GetOutermost()->GetName();
	TArray<UPackage*> PackagesToSave;
	PackagesToSave.Add(BP->GetOutermost());
	FEditorFileUtils::PromptForCheckoutAndSave(PackagesToSave, /*bCheckDirty=*/false, /*bPromptToSave=*/false);

	return FString::Printf(TEXT("OK: %s parent %s -> %s (compiled+saved)"),
		*BlueprintPath, *OldParent, *GetNameSafe(NewParent));
#else
	return TEXT("ERR: editor-only");
#endif
}

#if WITH_EDITOR
namespace RedMMOEditorToolsPrivate
{
	/**
	 * Epic's UE 5.8 MCP exposes Blueprint/asset/PIE operations but intentionally does not expose
	 * arbitrary Python or native UFunction execution. Keep one narrow editor command so the compiled,
	 * idempotent authoring pass can still be invoked from the editor console after a live-code build.
	 */
	static void InstallFocalRigAimFromConsole()
	{
		const FString FocalResult = URedMMOEditorTools::InstallFocalRigAim(
			TEXT("/Game/RedMMO/Characters/ABP_RedTrooperFemale.ABP_RedTrooperFemale"),
			TEXT("/Game/Action_Trooper/Meshes/Trooper_UE4_Tall_Female/SK_TF_Trooper_Standalone_Covered.SK_TF_Trooper_Standalone_Covered"),
			TEXT("/Game/RedMMO/Weapons/SK_RedTrooper_Rifle_A.SK_RedTrooper_Rifle_A"),
			TEXT("/Game/RedMMO/Characters/CR_RedTrooperFocalAim"));
		const FString MovementResult = URedMMOEditorTools::InstallRifleMovementPoses(
			TEXT("/Game/RedMMO/Characters/ABP_RedTrooperFemale.ABP_RedTrooperFemale"),
			TEXT("/Game/RedMMO/Anims/Rifle/A_Rifle_Jog_Aim_Fwd.A_Rifle_Jog_Aim_Fwd"),
			TEXT("/Game/RedMMO/Anims/Rifle/A_Rifle_Jetpack_Aim_Air.A_Rifle_Jetpack_Aim_Air"));

		UE_LOG(LogTemp, Display, TEXT("RedMMO.InstallFocalRigAim: %s | %s"), *FocalResult, *MovementResult);
	}

	static FAutoConsoleCommand GInstallFocalRigAimCommand(
		TEXT("RedMMO.InstallFocalRigAim"),
		TEXT("Build/update the Red trooper FocalRig asset and splice it into ABP_RedTrooperFemale."),
		FConsoleCommandDelegate::CreateStatic(&InstallFocalRigAimFromConsole));

	static void SnapSelectedStaticMeshesFromConsole(const TArray<FString>& Args)
	{
		const float SurfaceOffsetCm = Args.IsEmpty() ? 0.0f : FCString::Atof(*Args[0]);
		const FString Result = URedMMOEditorTools::SnapSelectedStaticMeshActorsToPlanetSurface(
			SurfaceOffsetCm);
		UE_LOG(LogTemp, Display, TEXT("RedMMO.SnapSelectedMeshesToPlanet: %s"), *Result);
	}

	static FAutoConsoleCommand GSnapSelectedStaticMeshesCommand(
		TEXT("RedMMO.SnapSelectedMeshesToPlanet"),
		TEXT("Snap selected static meshes to exact PlanetGen terrain. Optional arg: surface offset cm."),
		FConsoleCommandWithArgsDelegate::CreateStatic(&SnapSelectedStaticMeshesFromConsole));
}
#endif
