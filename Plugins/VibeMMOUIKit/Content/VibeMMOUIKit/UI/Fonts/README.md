# Vibe MMO UI Kit Fonts

This plugin does not bundle Saira Black 900 Italic or any other third-party commercial font file.

The runtime C++ defaults use Unreal Engine's built-in UI font as a safe placeholder through `FCoreStyle`. That placeholder is meant only to keep the widgets readable until the buyer assigns their own font asset.

## Recommended Visual Direction

For the intended chunky hero-shooter/MMO look, import and assign **Saira Black 900 Italic** to:

- `UVibeMMOUIStyleDataAsset -> Typography -> Primary Hero Font`

That single field drives these font roles:

- HUD numbers for shield, health, and resource values.
- Ability key labels: Q, E, R, F, X.
- Weapon slot labels: 1 and 2.
- Character level badge.
- Main menu titles.
- Character creator section headers.
- Talent tree titles.
- Inventory rarity labels.
- Important short labels and headings.

Use `Companion Font` for long descriptions, tooltips, quest text, and settings text.

## Marketplace Redistribution Rule

If you distribute this plugin on Fab Marketplace, do not include Saira Black 900 Italic unless your license explicitly allows redistribution inside a commercial Unreal Engine plugin.

Safe workflow:

1. Ship the plugin with the Unreal default placeholder font.
2. Keep these instructions in the plugin.
3. Let buyers import their licensed font file into their own project.
4. Let buyers assign the imported font to `Primary Hero Font` in their own `UVibeMMOUIStyleDataAsset`.

## Import Steps

1. In Unreal Editor, import your licensed font file into your project.
2. Create or open a `VibeMMOUIStyleDataAsset`.
3. Assign the imported Saira Black 900 Italic font to `Primary Hero Font`.
4. Assign a lighter readable font to `Companion Font`.
5. Set the style data asset in `Project Settings -> Vibe MMO UI Kit -> Default Style Data Asset`, or assign it directly on a Vibe MMO UI widget/player controller.

Widgets resolve font roles from the style data asset, so swapping the font should not require editing individual widget blueprints.
