# VALIDATION

To be written in Phase 10.

## Data (Phase 1 bake, DATA stream)

Source: OpenStreetMap via Overpass (`overpass-api.de`), OSM base timestamp 2026-10-22T19:17Z. © OpenStreetMap contributors (ODbL).
Re-bake from cache: `python -m zill.data.bake --city dubai_downtown` (~8 s); `--refresh` refetches.

| Item | Value |
|---|---|
| Buildings in caster box (core + 900 m) | 8,602 (3,039 in scene = core + 100 m) |
| building:part polygons | 577; 97 shells replaced by parts, 132 shells kept minus partial parts |
| Height source | tag 1,098 · levels 167 · fallback 6,760 · part 576 · landmark 1 |
| Max height | 828 m (Burj Khalifa spire part; OSM tags 760 m → curated override) |
| Trees | 744 (547 mapped nodes + 197 sampled every 6 m along 11 tree rows); none carry crown/height tags → defaults r 3 m, h 7 m |
| Graph | 5,455 nodes, 7,657 edges (7,029 walk, 4,822 cycle/scooter), median edge 21 m, 302 km |
| Link classes | open 6,080 · indoor 1,446 · covered 116 · ac_link 15 |
| Dropped components | walk 40, cycle 23 (95 edges) |
| POIs | 50 (18 of 19 curated gazetteer entries resolved by name; Vida Downtown came in through the auto list) |
| buildings.glb | 152 tiles of 250 m, 112,115 vertices, 61,407 triangles, 4.5 MB; trimesh round-trip OK |

Honest caveats:
- **Heights are mostly guessed.** 79 % of footprints have no height/levels tag and use the PRD fallbacks (apartments 30 m, hotel 45 m, office 40 m, retail 22 m, default 18 m). Shadow lengths of those buildings are approximate.
- **Trees are under-estimated.** OSM tree mapping in Downtown Dubai is incomplete, so Zill under-estimates tree shade (a conservative bias).
- **Graph density.** The PRD gate expected > 10,000 edges; the real OSM network for the scene box gives 7,657 after splitting at every shared node. Many roads carry `foot=no` because their sidewalks are mapped as separate footways; those roads are cycle-only.
- **AC links come from OSM tags** (`bridge=yes` + `covered=yes`/`indoor=yes`), including the Metro Link (way/204267696), and are continuous from the metro station into the Dubai Mall indoor network. On-site check still open (OPEN_ITEMS).

POI resolution (resolved coordinate, snap distance to nearest walk node):
burj_khalifa (25.19704, 55.27421) 33 m · dubai_mall (25.19701, 55.27857) 6 m · dubai_fountain (25.19531, 55.27570) 78 m (in the lake; nearest promenade) · dubai_opera (25.19567, 55.27198) 38 m · metro_burj_khalifa (25.20144, 55.26955) 14 m · souk_al_bahar (25.19477, 55.27659) 49 m · burj_park (25.19418, 55.27342) 43 m · address_downtown (25.19402, 55.27889) 38 m · armani_hotel (25.19746, 55.27473) 16 m · palace_downtown (25.19366, 55.27571) 48 m · boulevard_plaza (25.20040, 55.27318) 0 m · emaar_square (25.20096, 55.27325) 8 m · address_boulevard (25.20088, 55.27620) 42 m · address_sky_view (25.20171, 55.27103) 14 m · burj_lake (25.19399, 55.27528) 88 m · dubai_opera_garden (25.19526, 55.27343) 12 m · business_bay_metro (25.19131, 55.26040) 44 m · dubai_mall_metro_link (25.20028, 55.27293) 18 m. Plus 32 auto POIs (hotels, malls, parks, attractions, cafés); full list with snaps in `data/cities/dubai_downtown/pois.json`.

QA images: `docs/qa/phase1/graph_overview.png`, `graph_core_zoom.png`, `buildings_caster.png`.
