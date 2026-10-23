// Scroll <-> timeline. One tall scroll container; Lenis smooths the wheel. Lenis is ticked from the
// Film's single frame loop (no separate rAF). Scroll sets t; autoplay/jumps move the scroll to t.
import Lenis from "lenis";
import { TOTAL_S } from "./master";
import { useFilm } from "./store";

/** scroll pixels per film second (13:00 -> ~125k px; one wheel notch ≈ half a film second) */
export const PX_PER_S = 160;

let lenis: Lenis | null = null;
let programmatic: number | null = null;

function maxScroll() {
  return Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
}

export function attachScroll(): () => void {
  lenis = new Lenis({ autoRaf: false, smoothWheel: true, lerp: 0.085, wheelMultiplier: 0.8 });
  lenis.on("scroll", (l: Lenis) => {
    if (programmatic !== null && Math.abs(l.scroll - programmatic) < 3) return;
    programmatic = null;
    const p = Math.max(0, Math.min(1, l.scroll / maxScroll()));
    const st = useFilm.getState();
    if (st.playing) st.setPlaying(false);
    st.setT(p * TOTAL_S, "scroll");
  });
  return () => {
    lenis?.destroy();
    lenis = null;
  };
}

/** called once per frame by the film loop (after t was advanced) */
export function tickScroll(nowMs: number) {
  if (!lenis) return;
  lenis.raf(nowMs);
  const st = useFilm.getState();
  if (st.source === "scroll") return;
  const target = (st.t / TOTAL_S) * maxScroll();
  if (Math.abs(lenis.scroll - target) > 1.5) {
    programmatic = target;
    lenis.scrollTo(target, { immediate: true, force: true });
  }
}
