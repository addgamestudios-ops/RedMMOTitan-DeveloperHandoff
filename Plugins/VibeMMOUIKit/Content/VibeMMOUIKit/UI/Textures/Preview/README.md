# Preview Source Textures

These PNG files are original placeholder/source-preview art for approval and early import testing.

They are not intended to be final production art. Replace them with project-specific character portraits, ability icons, weapon icons, and map art.

Recommended workflow:

1. Import these PNG files into Unreal only if you want quick placeholder assets.
2. Assign imported textures to `UVibeMMOHUDLayoutDataAsset`.
3. Replace them later with final art without changing widget code.

For character portraits that match equipped armor, RED should render the actual character mesh to a UI texture/render target and pass it to `UVibeMMOHUDWidget::SetPortraitResource`.
