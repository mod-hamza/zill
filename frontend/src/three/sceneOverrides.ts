// Optional, additive scene overrides written by the Film (FILM stream). Every default is the
// identity, so /app renders exactly as before. Module-level (one canvas), read every frame by the
// shared scene components. Values are set by the Film's single frame loop from evaluate(t).
export const sceneOverrides = {
  /** 0 = normal ground; 1 = ground (raster, roads) replaced by ink (Ch.4 "black ground plane") */
  blackout: 0,
  /** 0..1 darkens sky + fog towards ink (Ch.4 build, Ch.11 globe) */
  skyDim: 0,
  /** multiplier on fog density (Ch.11 globe shot needs clear air) */
  fogScale: 1,
  /** false: the sun casts no real-time shadow-map shadows (Ch.4 rising buildings) */
  shadows: true,
  /** building radial rise (Ch.4): metres of radius revealed from the origin; 1e9 = all risen */
  revealRadius: 1e9,
  /** width (m) of the rising band */
  revealBand: 260,
  /** trees grow-in radius (m) from the origin; 1e9 = all grown */
  treeRadius: 1e9,
  /** 0 = /app's dark plinth beyond the modelled area; 1 = plinth matches sunlit paving (Film) */
  plinth: 0,
  /** soft edge (uv fraction) where the modelled ground meets the plinth; /app default 0.012 */
  edgeSoft: 0.012,
  /** fraction of floors with lit windows at dusk/dawn (null = SCENE default) */
  litFrac: null as number | null,
  /** link ribbons: minimum width in px (Film highlight) */
  linkMinPx: 1.1,
  /** extra multiplier on the lighting model's sky blue / contrast (Film look) — 0 = off */
  filmLook: 0,
};

export type SceneOverrides = typeof sceneOverrides;

export const SCENE_OVERRIDE_DEFAULTS: SceneOverrides = { ...sceneOverrides };

export function resetSceneOverrides() {
  Object.assign(sceneOverrides, SCENE_OVERRIDE_DEFAULTS);
}
