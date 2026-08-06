# Meshy/Tripo pipeline for RedMMOTitan alien assets

Use Meshy or Tripo for missing signature silhouettes, not for replacing every marketplace asset. The mood board calls for a small number of highly recognizable alien families supported by cheaper Fab foliage, terrain, and VFX.

## Generate first

Highest-value original families:

1. coral umbrella trees with buttressed trunks and thick horizontal canopy plates;
2. fungal cathedral trees with bracket shelves, root arches, and giant floor fungi;
3. crimson droop trees with hanging ribbon crowns;
4. fan rosettes, spear leaves, spiral shoots, bulb plants, and magenta moss colonies;
5. needle spires, caprock shelves, striated monoliths, and root-like stone arches;
6. floating balloon pods and drifting spore bodies.

Use Fab-first for ordinary grass, rubble, pebbles, secondary ferns/reeds, mist, dust, waterfall spray, wind systems, decals, and generic modular sci-fi pieces. Hand-model or kitbash portals, energy channels, bridges, collision-critical architecture, and repeatable modular structures.

## Input preparation

Do not send a whole scenic mood-board image directly to image-to-3D and expect a production asset. It contains overlapping objects, painted perspective, and baked lighting.

For each asset:

1. Make or generate an isolated single-object concept sheet.
2. Use a plain neutral background.
3. Include front, side, three-quarter, and back views when possible.
4. Show the root/base and complete silhouette without occlusion.
5. Add a human scale marker outside the asset silhouette.
6. Specify that color is material albedo, with no baked light, shadow, outline, or ambient occlusion.

## Prompt templates

### Coral umbrella tree

```text
Single isolated stylized alien tree asset, broad coral-like umbrella canopy made from 5 to 8 thick overlapping horizontal plates, pale buttressed trunk with large root flares, a few long hanging tendrils, readable Fortnite-like painterly silhouette, warm sandstone and dusty coral base colors with restrained magenta edge accents, game-ready shape language, no ground plane, no environment, no characters, no text, neutral studio light, no baked shadows, full object visible, orthographic reference views.
```

### Fungal cathedral tree

```text
Single isolated colossal alien forest tree, massive old buttressed trunk, root arches large enough for a person to walk under, layered bracket fungi and shelf growth, broad simple forms, stylized painterly science-fiction design, dark plum bark with muted cyan bioluminescent seams and sparse magenta fungi, no ordinary Earth leaves, no scene background, no ground plane, no baked lighting, full silhouette visible, orthographic asset sheet.
```

### Crimson droop tree

```text
Single isolated alien savanna tree, narrow twisting trunk supporting a wide crown of long drooping ribbon-like fronds, asymmetrical silhouette, hot coral and crimson foliage with indigo shadow colors, sparse violet bulbs, stylized game asset, no palm-tree shape, no environment, no terrain, no baked highlights or shadows, complete root-to-crown object visible.
```

### Striated stone arch

```text
Single isolated monumental alien rock arch, vertical sediment fins and broad caprock shelf, root-like opening suitable for player traversal, stylized painterly sandstone with terracotta, dusty rose, and muted plum strata, large low-frequency planes, no photogrammetry noise, no vegetation, no environment, no baked shadows, complete mesh silhouette visible.
```

Create at least three silhouettes, one juvenile/small version, and one damaged/dead version for every family that will repeat.

## Post-generation cleanup

Treat the generated mesh as a high-poly ingredient.

1. Download the highest-quality source allowed by the tool/account.
2. Archive the source prompt, reference sheet, tool, model version, seed, date, and license evidence.
3. Inspect for internal faces, floating shells, non-manifold edges, fused gaps, and accidental ground planes.
4. Retopologize or decimate by visual role; preserve the silhouette before surface detail.
5. Separate trunk, canopy, emissive, and optional hanging parts when they need different materials or wind behavior.
6. Set real-world centimetre scale, Z-up orientation, base pivot, and applied transforms.
7. Re-UV with consistent texel density. Bake normal/AO only from cleaned geometry.
8. Create base color, normal, and packed ORM textures without baked scene lighting.
9. Build simple collision from primitive/convex pieces. Do not use complex collision as simple on large traversal assets.
10. Create LODs or test Nanite according to the asset type.

## Unreal material rules

- Large rocks and trunks: opaque, high roughness, project-owned master instance, vertex-color hue/roughness variation.
- Foliage: masked rather than translucent, two-sided foliage shading, controlled subsurface tint, wind through WPO, correct expanded bounds.
- Energy/spores: separate restrained emissive material; never make the whole plant glow.
- Keep cyan and magenta as focal accents. Warm earth and indigo/plum shadow colors carry most of the surface.
- Test neutral noon and saturated dusk. If the asset only looks correct under one LUT, it is not approved.

## Performance and promotion gate

Before moving an asset from Quarantine to Approved:

- verify silhouette at gameplay, jetpack, and ship distances;
- review wireframe, UVs, shader complexity, masked overdraw, WPO bounds, shadow cost, and texture memory;
- test collision and radial surface alignment;
- check Nanite support for large rigid geometry and conventional LOD behavior for moving foliage;
- make a near/mid/far representation or a documented HLOD/impostor plan;
- spawn enough instances to expose repetition and runtime cost;
- confirm the asset can be recolored into its assigned biome without editing source textures destructively;
- tag it for hand placement first; PCG approval is a separate later decision.

## Record for each accepted asset

```text
Asset family:
Source tool/model/version:
Source prompt and seed:
License evidence:
Source and cleaned file paths:
Unreal asset path:
Real-world size:
Biome roles/tags:
Hand-placement status:
PCG status:
Collision policy:
Nanite/LOD/HLOD policy:
Material parameters:
Performance evidence:
Reviewer/date:
```

