"use client";
// Client shell of the (stage) route group: the ONE persistent canvas behind /film and /app,
// URL flags (?q=low|medium|high, ?debug, ?qa, ?date=, ?time=HHMM, ?cam=, ?route=, ?view=,
// ?fixture=1) and the loading / debug overlays.
import dynamic from "next/dynamic";
import { usePathname } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { DEFAULT_CITY, useCity } from "@/state/city";
import { switchCity } from "@/state/switchCity";
import { useBusy } from "@/lib/busy";
import { useRig } from "@/state/rig";
import { useRoute, type RouteKey, type RouteView } from "@/state/route";
import { useStage, type Quality } from "@/state/stage";
import { PRESET_DATES, useSun } from "@/state/sun";
import { hhmmToMinutes } from "@/lib/sun";
import {
  CAMERA_PRESETS,
  cityView,
  type CameraPreset,
} from "@/three/sceneConfig";
import { frameRouteView } from "@/three/AppDrivers";
import { DebugOverlay } from "./DebugOverlay";
import { LoadingScreen } from "./LoadingScreen";

const Scene = dynamic(() => import("@/three/Scene").then((m) => m.Scene), {
  ssr: false,
});

declare global {
  interface Window {
    __zill?: Record<string, unknown>;
  }
}

function parseCam(v: string): CameraPreset | null {
  const preset = CAMERA_PRESETS[v];
  if (preset) return preset;
  const n = v.split(",").map(Number);
  if (n.length >= 6 && n.every((x) => Number.isFinite(x))) {
    return {
      position: [n[0]!, n[1]!, n[2]!],
      target: [n[3]!, n[4]!, n[5]!],
      fov: n[6] ?? 35,
    };
  }
  return null;
}

export function StageShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const loaded = useCity((s) => s.loaded);
  const meta = useCity((s) => s.meta);

  useEffect(() => {
    const film = pathname?.startsWith("/film") ?? false;
    useStage.getState().setMode(film ? "film" : "app");
    // the Film is authored for Downtown Dubai: leaving /app?city=oslo for /film switches back
    const c = useCity.getState();
    if (film && c.cityId !== DEFAULT_CITY && (c.meta || c.loaded))
      void c.load(DEFAULT_CITY);
  }, [pathname]);

  // frame a non-default city from its bbox once its meta arrives (unless ?cam= pins the camera)
  useEffect(() => {
    if (!meta || meta.city_id === DEFAULT_CITY) return;
    if (useStage.getState().mode !== "app") return;
    if (new URLSearchParams(window.location.search).get("cam")) return;
    useRig.getState().setView(cityView(meta));
  }, [meta]);

  // flags that matter before the first frame
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const q = p.get("q");
    if (q === "low" || q === "medium" || q === "high")
      useStage.getState().setQuality(q as Quality, true);
    useStage.getState().setFlags({ debug: p.has("debug"), qa: p.has("qa") });
    const date = p.get("date");
    if (date)
      useSun
        .getState()
        .setDate(
          date,
          PRESET_DATES[date] ??
            (/^\d{4}-\d\d-\d\d$/.test(date) ? date : undefined),
        );
    const time = p.get("time");
    if (time) useSun.getState().setMinutes(hhmmToMinutes(time));
    const pref = p.get("pref");
    if (pref === "sun" || pref === "shade")
      useRoute.setState({ preference: pref });
    const view = p.get("view");
    if (view === "analysis" || view === "presentation")
      useRoute.getState().setView(view as RouteView);
    const cam = p.get("cam");
    const preset = cam ? parseCam(cam) : null;
    if (preset) useRig.getState().setView(preset);
    if (p.has("qa") || p.has("debug")) {
      window.__zill = {
        useCity,
        useSun,
        useRoute,
        useRig,
        useStage,
        frameRouteView,
        switchCity,
        useBusy,
      };
    }
  }, []);

  // flags that need the city (hero route)
  useEffect(() => {
    if (!loaded) return;
    const p = new URLSearchParams(window.location.search);
    const route = p.get("route");
    if (!route) return;
    void (async () => {
      const rs = useRoute.getState();
      if (route.startsWith("pois:")) {
        // QA/debug: an explicit origin,destination pair of gazetteer ids, routed live by /api/route
        const [o, d] = route.slice(5).split(",");
        const pois = useCity.getState().pois ?? [];
        const po = pois.find((x) => x.id === o);
        const pd = pois.find((x) => x.id === d);
        if (!po || !pd) return;
        const date = p.get("date");
        if (date) useSun.getState().setDate(date, PRESET_DATES[date]);
        const time = p.get("time");
        if (time) useSun.getState().setMinutes(hhmmToMinutes(time));
        const mode = p.get("mode");
        if (mode === "walk" || mode === "cycle" || mode === "scooter")
          rs.setMode(mode);
        rs.setEndpoint("a", {
          node: po.node,
          x: po.x,
          z: po.z,
          lat: po.lat,
          lon: po.lon,
          name: po.name,
        });
        rs.setEndpoint("b", {
          node: pd.node,
          x: pd.x,
          z: pd.z,
          lat: pd.lat,
          lon: pd.lon,
          name: pd.name,
        });
        await useRoute.getState().request();
      } else {
        await rs.loadScenarios();
        const sc = useRoute.getState().scenarios;
        const wantSun = p.get("pref") === "sun";
        const id =
          route === "hero"
            ? (sc.find((x) => (x.preference ?? "shade") === (wantSun ? "sun" : "shade")) ?? sc[0])?.id
            : route;
        if (!id) return;
        useRoute.getState().applyScenario(id);
        // explicit date/time win over the scenario's own
        const date = p.get("date");
        if (date) useSun.getState().setDate(date, PRESET_DATES[date]);
        const time = p.get("time");
        if (time) useSun.getState().setMinutes(hhmmToMinutes(time));
      }
      const sel = p.get("sel");
      if (sel === "fastest" || sel === "balanced" || sel === "coolest")
        useRoute.getState().setSelected(sel as RouteKey);
      if (sel === "sunniest" || sel === "best")
        useRoute.getState().setSelected("coolest");
      const cam = p.get("cam");
      const res = useRoute.getState().result;
      if (!cam && res) useRig.getState().setView(frameRouteView(res.coolest));
    })();
  }, [loaded]);

  return (
    <>
      <div className="fixed inset-0 bg-ink">
        <Scene />
      </div>
      {children}
      <LoadingScreen />
      <DebugOverlay />
    </>
  );
}
