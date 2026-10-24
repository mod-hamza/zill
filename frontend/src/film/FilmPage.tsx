"use client";
// /film: the 6-minute cut (business pitch); /film2: the full 13-minute film (?cut=short|full
// overrides either). Tall scroll container + keyboard controls + overlays. The canvas lives in the shared
// stage layout; the frame loop (FilmWorld) lives inside it.
//   Space autoplay · [ ] speed 0.85–1.15 · ←/→ chapter · 1–9,0,-,= chapters 1–12 (←/→ for 13–15) · Esc pause
//   F fullscreen · T elapsed · H hide chrome · L low quality · A -> /app (city/date/time kept)
//   ?qa=1&t=<s> (capture; sets window.__zillFrameReady) · &rate=<x> (QA autoplay speed)
//   ?presenter=1 strip · ?ch=<n> start at chapter n · ?autoplay=1
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { StillsFallback, webglAvailable } from "./StillsFallback";
import { NAME, TAGLINE } from "@/brand";
import { minutesToHHMM } from "@/lib/sun";
import { useCity } from "@/state/city";
import { useStage } from "@/state/stage";
import { useSun } from "@/state/sun";
import { useFilmData } from "./data";
import { CHAPTER_STARTS, CHAPTERS, cutFor, setCut, TOTAL_S } from "./master";
import { Overlay } from "./Overlay";
import { Presenter } from "./Presenter";
import { attachScroll, PX_PER_S } from "./scroll";
import { useFilm } from "./store";
import { FILM_HOME_CITY } from "./types";
import "./film.css";

/** the "scroll to begin" cue fades out over the first film seconds (driven by t, not a timer) */
const CUE_FADE_S = 2.5;

const KEY_CH: Record<string, number> = {
  "1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5, "7": 6, "8": 7, "9": 8, "0": 9, "-": 10, "=": 11,
};

export function FilmPage() {
  const router = useRouter();
  const qa = useFilm((s) => s.qa);
  const status = useFilmData((s) => s.status);
  const error = useFilmData((s) => s.error);
  const progress = useFilmData((s) => s.progress);
  const showElapsed = useFilm((s) => s.showElapsed);
  const hidden = useFilm((s) => s.chromeHidden);
  const t = useFilm((s) => s.t);
  const playing = useFilm((s) => s.playing);
  const chapter = useFilm((s) => s.frame?.chapter ?? 0);
  // the cut: re-render when it is chosen (TOTAL_S / CHAPTERS are the master's live bindings)
  useFilm((s) => s.cut);
  const contextLost = useStage((s) => s.contextLost);
  const [noGl, setNoGl] = useState(false);
  useEffect(() => setNoGl(!webglAvailable()), []);

  // URL flags
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const cut = cutFor(window.location.pathname, window.location.search);
    setCut(cut);
    const st = useFilm.getState();
    st.set({ cut });
    const isQa = p.has("qa");
    const rate = Number(p.get("rate"));
    st.set({
      qa: isQa,
      presenter: p.get("presenter") === "1",
      rate: isQa && Number.isFinite(rate) && rate > 0 ? rate : 1,
    });
    const tq = Number(p.get("t"));
    const ch = Number(p.get("ch"));
    if (p.has("t") && Number.isFinite(tq)) st.setT(tq, "init");
    else if (Number.isFinite(ch) && ch >= 1 && ch <= CHAPTERS.length)
      st.setT(CHAPTER_STARTS[ch - 1]! + 0.01, "init");
    else st.setT(0, "init");
    if (p.get("autoplay") === "1") st.setPlaying(true);
    if (isQa) (window as unknown as { __zillChapters?: unknown }).__zillChapters = CHAPTERS;
    if (isQa) {
      // capture tooling: jump without reloading the page
      (window as unknown as { __zillFilmSetT?: (t: number) => void }).__zillFilmSetT = (x: number) => {
        window.__zillFrameReady = false;
        useFilm.getState().setT(x, "init");
      };
    }
  }, []);

  // scroll (not in QA captures: the URL owns t there)
  useEffect(() => {
    if (qa) return;
    return attachScroll();
  }, [qa]);

  // keyboard
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const tgt = e.target as HTMLElement | null;
      if (tgt && (tgt.tagName === "INPUT" || tgt.tagName === "TEXTAREA")) return;
      const st = useFilm.getState();
      const cur = st.frame?.chapter ?? 0;
      const k = e.key;
      if (k === " ") {
        e.preventDefault();
        st.toggle();
      } else if (k === "[") st.nudgeSpeed(-0.05);
      else if (k === "]") st.nudgeSpeed(0.05);
      else if (k === "ArrowRight") {
        e.preventDefault();
        st.jumpChapter(cur + 1);
      } else if (k === "ArrowLeft") {
        e.preventDefault();
        // within the first 2 s of a chapter go to the previous one, else restart this one
        const into = st.t - CHAPTER_STARTS[cur]!;
        st.jumpChapter(into < 2 ? cur - 1 : cur);
      } else if (k in KEY_CH) st.jumpChapter(KEY_CH[k]!);
      else if (k === "Escape") st.setPlaying(false);
      else if (k === "f" || k === "F") {
        if (document.fullscreenElement) void document.exitFullscreen();
        else void document.documentElement.requestFullscreen?.();
      } else if (k === "t" || k === "T") st.set({ showElapsed: !st.showElapsed });
      else if (k === "h" || k === "H") st.set({ chromeHidden: !st.chromeHidden });
      else if (k === "l" || k === "L") {
        const s = useStage.getState();
        s.setQuality(s.quality === "low" ? "high" : "low", true);
      } else if (k === "a" || k === "A") {
        const sun = useSun.getState();
        st.setPlaying(false);
        const city = useCity.getState().cityId;
        const cq = city !== FILM_HOME_CITY ? `city=${encodeURIComponent(city)}&` : "";
        router.push(`/app?${cq}date=${sun.dateKey}&time=${minutesToHHMM(sun.minutes)}`);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router]);

  if (noGl || contextLost) return <StillsFallback />;
  const mm = Math.floor(t / 60);
  const ss = Math.floor(t % 60);
  return (
    <main className={`film-root ${hidden ? "is-chrome-hidden" : ""}`}>
      <h1 className="film-sr">{NAME}</h1>
      <p className="film-sr">{TAGLINE}</p>
      {qa ? null : <div aria-hidden style={{ height: `calc(${Math.round(TOTAL_S * PX_PER_S)}px + 100vh)` }} />}
      <Overlay />
      {!qa && status === "ready" && !hidden && !playing && t < CUE_FADE_S ? (
        <div className="film-scroll-cue" style={{ opacity: 1 - t / CUE_FADE_S }}>
          <span className="film-scroll-cue-label">Scroll to begin</span>
          <span className="film-scroll-cue-line" aria-hidden />
          <span className="film-scroll-cue-hint">or press Space to play</span>
        </div>
      ) : null}
      {showElapsed ? (
        <div className="film-elapsed tabular">
          {String(chapter + 1).padStart(2, "0")} &middot; {mm}:{String(ss).padStart(2, "0")}
        </div>
      ) : null}
      <Presenter />
      {status !== "ready" ? (
        <div className="film-veil" style={{ opacity: status === "error" ? 1 : 1 - progress * 0.2 }}>
          <p className="font-display">{status === "error" ? "The film data could not be loaded." : "Preparing the film…"}</p>
          {error ? <p className="film-veil-err">{error}</p> : null}
          <div className="film-veil-bar">
            <div style={{ width: `${Math.round(Math.max(0.03, progress) * 100)}%` }} />
          </div>
        </div>
      ) : null}
    </main>
  );
}
