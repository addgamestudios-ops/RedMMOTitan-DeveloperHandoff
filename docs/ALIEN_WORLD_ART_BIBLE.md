# RedMMOTitan alien-world art bible

Source: the ten mood-board images supplied on 2026-07-14.

## Visual language

The target is stylized painterly science fiction with broad, readable forms and deliberate color blocking rather than photoreal surface noise.

- Geology is vertical, striated, and monumental: fins, pillars, shelf cliffs, arches, and caprock plateaus.
- Vegetation counters it with wide horizontal disks, fungal shelves, fan leaves, hanging ribbons, and drooping crowns.
- Technology uses perfect circles, clean arcs, radial segmentation, and cyan/magenta light channels embedded in rough natural forms.
- Use warm sandstone, terracotta, coral, burnt orange, and dusty rose as the base.
- Use crimson, magenta, violet, and occasional acid green for biome identity.
- Reserve cyan/turquoise for water, energy, wet stone, and major navigation landmarks.
- Shadows should tend toward indigo and muted plum instead of featureless black.
- Keep traversal corridors readable and preserve landmark silhouettes against the sky.

## Biome families

1. **Coral-canopy coast** — pale buttressed trunks, giant umbrella plates, hanging tendrils, turquoise shallows.
2. **Ember-magenta rift** — red/orange meadow, violet canopy clusters, sandstone needles and shelf rocks.
3. **Fungal cathedral forest** — colossal old trunks, bracket fungi, root arches, low floor colonies, light shafts.
4. **Monolithic pillar cavern** — enormous columns and ceiling shelves, waterfalls, sparse magenta ledge growth.
5. **Verdant sky plateau** — broad grass mesas, natural bridges, cloud voids, cyan channels and falls.
6. **Portal oasis** — monumental radial technology, clean water, pale rock, controlled magenta accents.
7. **Cliffside industrial spaceport** — modular infrastructure recessed into geology rather than sitting on top of it.

The ordinary green forest reference is a density and lighting baseline, not the dominant alien identity. The planetary reference calls for a few distinct continental masses separated by substantial oceans, not uniform foliage across the globe.

## Asset priorities

### Signature generation candidates — Meshy or Tripo

- coral umbrella trees: 3 trunks, 5–8 canopy plates, roots, tendrils, juvenile, dead variant;
- fungal cathedral trees: buttressed trunks, bracket shelves, root arches, giant and floor fungi;
- crimson droop trees: multiple trunk and hanging-crown silhouettes;
- alien understory: fan rosettes, spear leaves, spiral shoots, bulb plants, magenta moss colonies;
- hero meadow forms: emissive seed heads and unusual tufts, not every grass blade;
- signature rocks: needle spires, caprock shelves, striated monoliths, and root-like arches;
- floating life: balloon pods, tether strands, and drifting spore bodies.

Generate isolated asset sheets or clean single-object concepts first. The scenic mood-board images are too occluded for reliable direct image-to-3D conversion. Treat generated meshes as high-poly ingredients, never as automatic Unreal-ready finals.

### Fab-first support assets

- ordinary grass cards, rubble, pebbles, reeds, deadfall, and secondary fern clusters;
- terrain and rock materials;
- water, waterfalls, mist, dust, pollen, spores, spray, and light shafts;
- foliage wind systems, decals, and modular sci-fi components.

### Manual modeling or kitbashing

- 40–120 m portal rings and damaged radial sections;
- precise energy channels, natural-bridge inserts, and collision-critical structures;
- cliff-foundry walls, gates, buttresses, vents, and landing hardware;
- repeatable architecture that requires exact snapping and modular alignment.

## Scale tiers

- XL landmarks: 40–150 m
- biome anchors: 15–50 m
- trees and mid structures: 3–15 m
- human-scale plants and rocks: 0.5–3 m
- ground cover: 0.03–0.6 m

Every signature plant family needs at least three silhouettes, a juvenile, a damaged/dead variant, and near/mid/far representations.

## Placement grammar

1. Hand-place hero anchors first.
2. Add 3–7 related satellite plants or rocks around an anchor.
3. Add ground-cover colonies only after the composition reads at gameplay distance.
4. Bias clusters toward water, shade, roots, cliff bases, and material transitions.
5. Keep routes and skyline landmarks open; never use even grid spacing.
6. Use roughly 0.8–1.25 scale variation, randomized yaw, and restrained tilt.
7. Use hand placement for composition-critical clusters; PCG and foliage tools are filler systems that must follow the approved grammar.

## Unreal intake gate

An asset is not approved until it passes:

- centimeter scale, Z-up orientation, applied transforms, and a root/base pivot;
- clean silhouette and topology with no accidental internal faces, floating shells, or non-manifold sections;
- usable UVs, consistent texel density, packed ORM, and correct normal maps;
- editable color parameters without baked lighting, highlights, shadows, or outlines;
- masked two-sided foliage shading, subsurface tint, wind deformation, instance hue variation, and correct WPO bounds;
- simple collision for trunks/rocks and no collision on tiny cover;
- Nanite evaluation for rocks and large trunks; overdraw/LOD evaluation for foliage;
- at least three variants where repetition will be visible;
- neutral-noon and saturated-dusk review with a mannequin for scale;
- silhouette, shader complexity, overdraw, collision, wind, shadows, streaming, and post-process checks before promotion.

New assets enter a quarantine/review folder first. Only approved meshes are promoted into hand-placement and PCG palettes with explicit biome tags.

