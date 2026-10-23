"use client";
// Film layer inside the ONE persistent canvas (mounted by World on /film only).
//   FilmLoop      the single frame loop: advances t (autoplay / eased chapter jumps), evaluates the
//                 master timeline and applies the FrameState to the shared stores and overrides.
//   SplitView     Ch.6 split: second camera -> HDR render target -> FilmFx right half (lens shift
//                 keeps both subjects centred in their halves).
//   + film-only 3D: hairline grid, brass road draw, sun-path arc, sun rays, travellers, labels,
//                 the globe.
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import {
  HalfFloatType,
  LinearFilter,
  PerspectiveCamera,
  Vector2,
  WebGLRenderTarget,
} from "three";
import { useCity } from "@/state/city";
import { useRig } from "@/state/rig";
import { useRoute } from "@/state/route";
import { useStage } from "@/state/stage";
import { useSun } from "@/state/sun";
import { linkUniforms } from "@/three/Links";
import { filmFx } from "@/three/post/FilmFxEffect";
import { routeFilm } from "@/three/Routes";
import { resetSceneOverrides, sceneOverrides } from "@/three/sceneOverrides";
import { setIndoorAmount } from "@/three/useLighting";
import { useFilmData } from "../data";
import { evaluate, TOTAL_S } from "../master";
import { JUMP_S, useFilm } from "../store";
import type { FrameState } from "../types";
import { power2InOut } from "@/three/rigs";
import { FilmExtras, travellerGroups } from "./FilmExtras";
import { tickScroll } from "../scroll";

declare global {
  interface Window {
    __zillFrameReady?: boolean;
    __zillFilm?: { t: number; chapter: number };
  }
}

/** last evaluated frame (module-level so the camera rig can read it without React) */
export const current: { frame: FrameState | null } = { frame: null };

function FilmLoop() {
  const camera = useThree((s) => s.camera) as PerspectiveCamera;
  const lastT = useRef(-1);
  const stable = useRef(0);
  const lastRouteKey = useRef<string | null>("__");

  useEffect(() => {
    useRig.getState().setRig({
      id: "film",
      evaluate: () =>
        current.frame?.camera ?? {
          position: [-2400, 300, 3000],
          target: [0, 200, 0],
          fov: 32,
          roll: 0,
        },
    });
    const r = useRoute.getState();
    r.setFlyT(null);
    r.clear();
    return () => {
      useRig.getState().setRig(null);
      resetSceneOverrides();
      setIndoorAmount(0);
      linkUniforms.uHighlight.value = 0;
      linkUniforms.uVis.value = 1;
      linkUniforms.uMinPx.value = 1.1;
      filmFx.set("uShimmer", 0);
      filmFx.set("uSplit", 0);
      routeFilm.gate = null;
      routeFilm.widthScale = 1;
      camera.clearViewOffset();
      useRoute.getState().setReveal({ fastest: 1, balanced: 1, coolest: 1 }, 1);
      useRoute.getState().clear();
      window.__zillFrameReady = false;
    };
  }, [camera]);

  useFrame((_, delta) => {
    const data = useFilmData.getState().data;
    const film = useFilm.getState();
    if (!data) return;
    const dt = Math.min(delta, 0.1);
    let t = film.t;
    if (film.jump) {
      const j = film.jump;
      const e = j.elapsed + dt;
      const u = Math.min(1, e / JUMP_S);
      t = j.from + (j.to - j.from) * power2InOut(u);
      useFilm.setState({ jump: u >= 1 ? null : { ...j, elapsed: e }, t, source: "loop" });
    } else if (film.playing) {
      t = Math.min(TOTAL_S, t + dt * film.speed * film.rate);
      useFilm.setState({ t, source: "loop", playing: t < TOTAL_S });
    }

    const f = evaluate(t, data);
    current.frame = f;
    useFilm.getState().setFrame(f);
    window.__zillFilm = { t, chapter: f.chapter + 1 };
    tickScroll(performance.now());

    // sun clock
    const sun = useSun.getState();
    if (sun.dateKey !== f.sun.dateKey) sun.setDate(f.sun.dateKey, data.meta.dates[f.sun.dateKey]);
    if (Math.abs(sun.minutes - f.sun.minutes) > 1e-4) sun.setMinutes(f.sun.minutes);
    useStage.getState().setFrameT(t);

    // scene overrides
    sceneOverrides.blackout = f.blackout;
    sceneOverrides.skyDim = f.skyDim;
    sceneOverrides.fogScale = f.fogScale;
    sceneOverrides.shadows = f.shadows;
    sceneOverrides.revealRadius = f.build.revealR;
    sceneOverrides.treeRadius = f.build.treeR;
    sceneOverrides.filmLook = f.look;
    sceneOverrides.plinth = 1;
    sceneOverrides.edgeSoft = 0.07;
    sceneOverrides.litFrac = f.litFrac;
    linkUniforms.uMinPx.value = f.build.linkPx;
    linkUniforms.uVis.value = f.build.links;
    linkUniforms.uHighlight.value = f.build.linkHighlight;
    setIndoorAmount(f.indoor);

    // routes (the shared Routes layer)
    const rkey = f.routes.result;
    const rs = useRoute.getState();
    if (rkey !== lastRouteKey.current) {
      lastRouteKey.current = rkey;
      if (!rkey) useRoute.setState({ result: null });
      else {
        const sc = rkey === "hero" ? data.hero : data.scenarios.find((x) => x.id === rkey);
        if (sc)
          useRoute.setState({
            result: {
              fastest: sc.fastest,
              balanced: sc.balanced,
              coolest: sc.coolest,
              origin: sc.origin,
              dest: sc.dest,
              date_key: sc.date_id,
            },
            a: null,
            b: null,
          });
      }
    }
    if (rs.view !== f.routes.view) rs.setView(f.routes.view);
    if (rs.selected !== f.routes.selected) rs.setSelected(f.routes.selected);
    rs.setReveal({ ...f.routes.reveal, balanced: 0 }, f.routes.opacity);
    routeFilm.widthScale = f.routeWidth;

    // post fx
    filmFx.set("uShimmer", f.shimmer);
    filmFx.set("uTime", t);
    const pitch = Math.atan2(
      f.camera.target[1] - f.camera.position[1],
      Math.hypot(f.camera.target[0] - f.camera.position[0], f.camera.target[2] - f.camera.position[2]),
    );
    const ndc = Math.tan(pitch) / Math.tan(((f.camera.fov / 2) * Math.PI) / 180);
    filmFx.set("uHorizonY", 0.5 - ndc / 2);

    // QA readiness: data + city + current shade pair + frames rendered since t settled
    if (Math.abs(t - lastT.current) > 1e-6) {
      lastT.current = t;
      stable.current = 0;
    } else stable.current++;
    const ready =
      useCity.getState().loaded && useStage.getState().shadeReady && stable.current > 12;
    window.__zillFrameReady = ready;
  }, -50);

  return null;
}

function SplitView() {
  const gl = useThree((s) => s.gl);
  const scene = useThree((s) => s.scene);
  const camera = useThree((s) => s.camera) as PerspectiveCamera;
  const cam2 = useMemo(() => new PerspectiveCamera(36, 1, 1, 40000), []);
  const rt = useMemo(
    () =>
      new WebGLRenderTarget(16, 16, {
        type: HalfFloatType,
        minFilter: LinearFilter,
        magFilter: LinearFilter,
        depthBuffer: true,
      }),
    [],
  );
  const size = useMemo(() => new Vector2(), []);
  const active = useRef(false);
  useEffect(() => () => rt.dispose(), [rt]);

  useFrame(() => {
    const f = current.frame;
    const split = f?.split;
    if (!split || split.amount <= 0) {
      if (active.current) {
        camera.clearViewOffset();
        filmFx.set("uSplit", 0);
        routeFilm.gate = null;
        active.current = false;
      }
      return;
    }
    active.current = true;
    gl.getDrawingBufferSize(size);
    const W = Math.max(2, Math.floor(size.x));
    const H = Math.max(2, Math.floor(size.y));
    if (rt.width !== W || rt.height !== H) rt.setSize(W, H);
    // lens shift: main camera's subject at 25% of the width, second camera's at 75%
    camera.setViewOffset(W, H, W / 4, 0, W, H);
    const c = split.camera;
    cam2.position.set(...c.position);
    cam2.up.set(0, 1, 0);
    cam2.lookAt(...c.target);
    cam2.fov = c.fov;
    cam2.aspect = W / H;
    cam2.near = camera.near;
    cam2.far = camera.far;
    cam2.setViewOffset(W, H, -W / 4, 0, W, H);
    cam2.updateMatrixWorld();
    // right half: only the coolest route + its traveller; left (main pass): only the fastest
    const [tf, tc] = travellerGroups;
    const vf = tf?.visible ?? false;
    const vc = tc?.visible ?? false;
    routeFilm.gate = (k) => (k === "coolest" ? 1 : 0);
    if (tf) tf.visible = false;
    const prev = gl.getRenderTarget();
    gl.setRenderTarget(rt);
    gl.clear();
    gl.render(scene, cam2);
    gl.setRenderTarget(prev);
    routeFilm.gate = (k) => (k === "fastest" ? 1 : 0);
    if (tf) tf.visible = vf;
    if (tc) tc.visible = false;
    void vc;
    filmFx.set("uSplitTex", rt.texture);
    filmFx.set("uSplit", split.amount);
  }, 0.5);
  return null;
}

export function FilmWorld() {
  const load = useFilmData((s) => s.load);
  useEffect(() => {
    void load();
  }, [load]);
  return (
    <>
      <FilmLoop />
      <SplitView />
      <FilmExtras />
    </>
  );
}
