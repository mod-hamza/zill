// Switch the App between baked cities by id (Dubai <-> Oslo, or any city /api/cities lists).
// Resets the journey, loads the city's GLB/graph/shade, re-frames the camera from its bbox and
// keeps `?city=` in the URL so the view is shareable.
import { cityView } from "@/three/sceneConfig";
import { DEFAULT_CITY, useCity } from "./city";
import { useRig } from "./rig";
import { useRoute } from "./route";
import { useSun } from "./sun";

export async function switchCity(id: string): Promise<void> {
  const city = useCity.getState();
  if (city.cityId === id && (city.loaded || city.meta)) return;
  useSun.getState().setPlaying(false);
  useRoute.getState().setFlyT(null);
  useRoute.getState().clear();
  useRoute.setState({ scenarios: [] });
  if (typeof window !== "undefined") {
    const u = new URL(window.location.href);
    if (id === DEFAULT_CITY) u.searchParams.delete("city");
    else u.searchParams.set("city", id);
    window.history.replaceState(null, "", u);
  }
  const p = useCity.getState().load(id);
  // frame the camera as soon as the meta (bbox) is known
  const unsub = useCity.subscribe((s) => {
    if (s.meta && s.cityId === id) {
      unsub();
      useRig.getState().setView(cityView(s.meta));
    }
  });
  await p;
  unsub();
  if (useCity.getState().cityId === id) await useRoute.getState().loadScenarios();
}
