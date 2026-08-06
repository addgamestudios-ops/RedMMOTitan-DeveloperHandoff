#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "RedMMOEditorTools.generated.h"

/**
 * Compiled C++ editor-authoring tools for RedMMO — native operations the generic MCP/Python
 * channels can't do reliably on Mac (AnimGraph node edits crash UECP; raw Python can't reach
 * AnimBlueprint graph nodes). Each function uses the stable in-process editor C++ API and is
 * BlueprintCallable, so it's driveable from Python via the UECP bridge.
 */
UCLASS()
class REDMMO_API URedMMOEditorTools : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * Repoint Sequence Evaluator / Sequence Player nodes in an Animation Blueprint's graphs from
	 * one animation to another, in place, then recompile. This is the safe alternative to the
	 * crash-prone UECP "add node" surgery — it only sets the Sequence property on existing nodes.
	 * If FromAnimNameOrPath is empty, the FIRST sequence node found is swapped. Editor-only.
	 * @return "OK: swapped N node(s): ..."  or  "ERR: ..."
	 */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools")
	static FString SetAnimGraphSequence(const FString& AnimBlueprintPath, const FString& FromAnimNameOrPath, const FString& ToAnimPath);

	/**
	 * Insert a Transform (Modify) Bone into an AnimBlueprint's final component-space passthrough that
	 * additively rotates a spine bone, driven by a new FRotator member variable. This is the procedural
	 * "aim offset" — drive the variable each tick from the pawn (camera pitch/yaw) and the chest+arms+gun
	 * follow your aim. Idempotent (no-op if already inserted). Editor-only. Returns "OK: ..." / "ERR: ...".
	 */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools")
	static FString AddAimModifyBone(const FString& AnimBlueprintPath, const FString& BoneName, const FString& AimVarName);

	/**
	 * Build/update CR_RedTrooperFocalAim from the supplied trooper and rifle meshes, then splice it
	 * into the AnimBlueprint after locomotion/overlay evaluation.
	 * When marketplace FocalRig is present: virtual muzzle + Aim Chain + Aim Weapon.
	 * When marketplace FocalRig is absent (REDMMO_WITH_MARKETPLACE_FOCALRIG=0): stock ControlRig
	 * AimItem spine_03 substitute preserving FocalAimTarget/FocalAimWeight. Editor-only.
	 */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools")
	static FString InstallFocalRigAim(
		const FString& AnimBlueprintPath,
		const FString& CharacterMeshPath,
		const FString& WeaponMeshPath,
		const FString& ControlRigAssetPath = TEXT("/Game/RedMMO/Characters/CR_RedTrooperFocalAim"));

	/**
	 * Insert animated upper-body selectors immediately before DefaultSlot:
	 * existing relaxed/standing-aim stance -> moving rifle aim -> jetpack rifle aim -> fire montage.
	 * The two bool variables are driven by ARedPlayerCharacter, so the lower-body locomotion remains
	 * untouched and the final FocalRig pass still owns exact barrel alignment. Idempotent. Editor-only.
	 */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools")
	static FString InstallRifleMovementPoses(
		const FString& AnimBlueprintPath,
		const FString& MovingAimPosePath,
		const FString& JetpackAimPosePath,
		const FString& MovingBoolVarName = TEXT("bRifleAimMoving"),
		const FString& JetpackBoolVarName = TEXT("bRifleJetpackAim"));

	/**
	 * Insert a "Blend Poses by bool" feeding the upper-body overlay (the Layered Blend's BlendPoses_0):
	 * TRUE = AimPose (firing stance), FALSE = RelaxedPose (run carry), selected by a new bool member var.
	 * Drive the var from the pawn (true while aiming/firing) so the arms physically switch relaxed<->aim,
	 * with the aim ModifyBone offset riding on top. Expects the overlay SeqEvaluator to currently play
	 * AimPose (set it first via SetAnimGraphSequence). Editor-only. Returns "OK: ..." / "ERR: ...".
	 */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools")
	static FString InsertAimPoseBlend(const FString& AnimBlueprintPath, const FString& AimPosePath, const FString& RelaxedPosePath, const FString& BoolVarName);

	/**
	 * Splice a Layered Blend Per Bone overlay into an AnimGraph that has none (the pack's
	 * ABP_ThirdPerson_* is just StateMachine -> Root). Inserts:
	 *   locomotion -> LayeredBoneBlend(base) [overlay SeqEvaluator(OverlayPose) on BlendPoses_0,
	 *   branch = BranchBone] -> LocalToComponent -> ComponentToLocal -> Root.
	 * The C2L->Root tail lets AddAimModifyBone add the aim pitch afterward; the overlay SeqEvaluator
	 * (playing OverlayPose) is what InsertAimPoseBlend then converts into the carry<->aim toggle.
	 * This is the FOUNDATION the other overlay tools require. Idempotent. Editor-only.
	 */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools")
	static FString InsertRifleOverlay(const FString& AnimBlueprintPath, const FString& OverlayPosePath, const FString& BranchBone);

	/**
	 * Drive the Layered Blend Per Bone's overlay weight (BlendWeights_0) from a new float member var,
	 * so the upper-body rifle pose can be faded out (set the var to 0) to show empty hands when holstered,
	 * and back to 1 when drawn. Editor-only. Returns "OK: ..." / "ERR: ...".
	 */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools")
	static FString DriveOverlayWeightByVar(const FString& AnimBlueprintPath, const FString& VarName);

	/**
	 * BLUEPRINT X-RAY: dump EVERY graph of any Blueprint (EventGraph, functions, AnimGraph,
	 * state-machine sub-graphs, transitions) as JSON — per node: class, title, GUID, referenced
	 * assets (blendspaces/sequences/meshes — walked generically from the node's properties,
	 * including one level into FAnimNode_* struct payloads), and per pin: name, direction, type,
	 * literal default, and links (guid:pin). This is the full-visibility read the generic
	 * MCP/Python channels can't give (AnimGraph pose-graph internals are otherwise opaque).
	 * Editor-only. Returns the JSON string (write it to a file from the caller if large).
	 */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools")
	static FString DumpBlueprintGraphs(const FString& BlueprintPath, bool bIncludePinDetails = true);

	/**
	 * Import the generator's six headerless little-endian R16 cube faces into a cookable
	 * UPlanetGenMacroHeightfieldAsset. The RED_MacroWorld.json manifest supplies resolution and
	 * decode bounds. Every source file and a transient runtime capture are validated before the
	 * destination package is created or changed; an existing asset of the same class is updated.
	 * SourceDirectory may be absolute or relative to the project directory. Editor-only.
	 */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools|Planet")
	static FString ImportPlanetGenMacroHeightfield(
		const FString& SourceDirectory = TEXT("SourceArt/Planet50Km/MacroFaces"),
		const FString& AssetPackagePath = TEXT("/Game/RedMMO/Environment/DA_RED_Planet50Km_MacroHeightfield"));

	/** MATERIAL X-RAY: list every expression in a Material (class, constant values, parameter
	 *  names/defaults, textures, function calls) as JSON — Python can't read Material.Expressions
	 *  (protected). Pairs with SetMaterialScalarConstants for measure->adjust->verify loops. */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools")
	static FString DumpMaterialExpressions(const FString& MaterialPath);

	/** Replace every MaterialExpressionConstant whose value ~= FromValue with ToValue, then
	 *  recompile. Returns how many were changed. */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools")
	static FString SetMaterialScalarConstants(const FString& MaterialPath, float FromValue, float ToValue);

	/** Insert a Subtract (ConstB = the given value) right after expression #ExprIndex (index as
	 *  reported by DumpMaterialExpressions): every input that consumed that expression — other
	 *  expressions AND material property pins — is rewired to the Subtract's output. Built for
	 *  thresholding a mask channel (e.g. star density cuts) without hand graph surgery. Recompiles. */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools")
	static FString InsertSubtractAfterExpression(const FString& MaterialPath, int32 ExprIndex, float ConstB);

	/** Override a STATIC SWITCH on a MaterialInstanceConstant (python's MEL setter returns false).
	 *  Rebuilds the static permutation, so expect a shader recompile on save. */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools")
	static FString SetMIStaticSwitch(const FString& MIPath, const FString& ParamName, bool bValue);

	/** Override a STATIC SWITCH on one material layer of a MaterialInstanceConstant.
	 *  LayerNameOrIndex accepts "Sand" / "3" / "Layer 3".  This is deliberately separate
	 *  from SetMIStaticSwitch: a global parameter association cannot control a switch that
	 *  lives inside PlanetGen's Sand layer.  Rebuilds the static permutation and saves the MI. */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools")
	static FString SetMILayerStaticSwitch(
		const FString& MIPath,
		const FString& LayerNameOrIndex,
		const FString& ParamName,
		bool bValue);

	/**
	 * MATERIAL-LAYER X-RAY: dump layer stack names/indices plus every texture/scalar/vector
	 * parameter with Association+Index (Global vs Layer). Needed because Python's
	 * MaterialEditingLibrary hardcodes LayerParameter index 0 and can't discover Sand's index.
	 */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools")
	static FString DumpMILayerParameters(const FString& MIPath);

	/**
	 * Set a texture parameter on ONE material layer of a MaterialInstanceConstant.
	 * LayerNameOrIndex: "Sand" / "3" / "Layer 3". Association is always LayerParameter.
	 * Does NOT touch GlobalParameter Texture/Normal (that paints all biomes the same).
	 * Saves the package. Editor-only.
	 */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools")
	static FString SetMILayerTextureParameter(
		const FString& MIPath,
		const FString& LayerNameOrIndex,
		const FString& ParamName,
		const FString& TexturePath);

	/**
	 * Set a scalar on ONE material layer (LayerParameter). Critical for CloseRangeTiling:
	 * each PlanetGen landscape layer owns its own CloseRangeTiling (default 500) — a Global
	 * MI override does NOT soften sand. Pass LayerNameOrIndex "Sand" / "3".
	 */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools")
	static FString SetMILayerScalarParameter(
		const FString& MIPath,
		const FString& LayerNameOrIndex,
		const FString& ParamName,
		float Value);

	/**
	 * Set Texture/Normal on an EXISTING MaterialFunctionInstance (e.g. MFI_Sand_SoStylized).
	 * Does NOT create assets / factories (create_asset with wrong factory caused a blocking ensure).
	 * Only saves if the package is under /Game/.
	 */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools")
	static FString SetMFITextureParameter(
		const FString& MFIPath,
		const FString& ParamName,
		const FString& TexturePath);

	/**
	 * Wire SoStylized sand onto MI_PlanetBiome_RED Sand layer using the EXISTING
	 * /Game/RedMMO/Materials/MFI_Sand_SoStylized duplicate. Aborts if that asset is missing
	 * (never factory-creates). Also restores plugin MFI_Sand to stock T_Sand in-memory.
	 */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools")
	static FString ApplySoStylizedSandToPlanetBiome(
		const FString& MIPath = TEXT("/Game/RedMMO/Materials/MI_PlanetBiome_RED.MI_PlanetBiome_RED"),
		const FString& SandBCPath = TEXT("/Game/SoStylized/Environment/Landscape/Textures/T_DesertSand_BC.T_DesertSand_BC"),
		const FString& SandNPath = TEXT("/Game/SoStylized/Environment/Landscape/Textures/T_DesertSand_N.T_DesertSand_N"));

	/**
	 * Creates a completely project-owned, isolated test chain for the real So Stylized
	 * desert sparkle: a project-owned MF_DesertSand instance with restrained sparkle/ripple
	 * settings -> a duplicate of PlanetGen M_Planet whose one MFI_Sand call is replaced -> a
	 * duplicate PlanetGen biome MI. It never mutates the production MI, plugin assets, or the
	 * protected 50 km checkpoint.
	 * The output is intentionally a test asset and must receive real-GPU review before any
	 * runtime map is pointed at it.
	 */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools")
	static FString CreateSoStylizedDesertSparkleLayerTest();

	/** Retune only the already-created project-owned T02 sparkle MFI, then verify that the
	 *  duplicated PlanetGen parent and biome MI still reference the isolated chain. */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools")
	static FString TuneSoStylizedDesertSparkleLayerTest(
		float SparkleBrightness = 10.0f,
		float SparkleTolerance = 0.75f);

	/**
	 * Snap the origins of selected static-mesh actors to the exact streamed PlanetGen surface and
	 * align each actor's local +Z to radial up while preserving its tangent heading and scale.
	 * Runs only in an editor world, never saves packages, and refuses the protected production/
	 * checkpoint maps. Use a /Game/RedMMO/Maps/Tests duplicate while validating a placement set.
	 */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools|Planet")
	static FString SnapSelectedStaticMeshActorsToPlanetSurface(float SurfaceOffsetCm = 0.0f);

	/** Move a Layered-Blend-Per-Bone's branch filter to a different bone (e.g. spine_01 -> spine_03
	 *  so the rifle overlay keeps the run cycle's lower-spine bounce absorption). Recompiles. */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools")
	static FString SetLayeredBlendBranchBone(const FString& AnimBlueprintPath, const FString& NewBoneName);

	/** Force an anim-graph node's internal bAlphaBoolEnabled (pin defaults on anim nodes don't
	 *  reliably bake) — NodeClassContains matches the UAnimGraphNode class name substring
	 *  (e.g. "OrientationWarping"). Recompiles. */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools")
	static FString SetAnimNodeAlphaBool(const FString& AnimBlueprintPath, const FString& NodeClassContains, bool bEnabled);

	/**
	 * Reparent a Blueprint to a new UClass (e.g. BP_Shuttle → /Script/RedMMO.RedShuttleBase),
	 * compile, and save. Editor-only. Returns "OK: ..." / "ERR: ...".
	 */
	UFUNCTION(BlueprintCallable, Category = "RedMMO|EditorTools")
	static FString ReparentBlueprint(const FString& BlueprintPath, const FString& NewParentClassPath);
};
