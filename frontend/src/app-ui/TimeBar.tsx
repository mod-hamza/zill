"use client";
// Bottom time bar (PRD 15): preset dates, sunrise->sunset scrubber with the sun-path arc, play
// (time-lapse), "Now". Scrubbing drives shade raster + light + sky continuously.
import { useMemo } from "react";
import { fmtDate } from "@/lib/format";
import { minutesToHHMM, nowMinutes, sunAt } from "@/lib/sun";
import { PRESET_ORDER, useSun } from "@/state/sun";
import { useRoute } from "@/state/route";

const LABEL: Record<string, string> = {
  winter: "Winter",
  spring: "Spring",
  summer: "Summer",
  hackathon: "Hackathon",
};
const ARC_W = 600;
const ARC_H = 34;

export function TimeBar() {
  const s = useSun();
  const flying = useRoute((r) => r.flyT !== null);
  const lo = Math.floor((s.sunrise - 20) / 10) * 10;
  const hi = Math.ceil((s.sunset + 20) / 10) * 10;

  // sun altitude curve for the arc (computed, not drawn freehand)
  const arc = useMemo(() => {
    const pts: string[] = [];
    let maxAlt = 1;
    const samples: [number, number][] = [];
    for (let m = lo; m <= hi; m += 5) {
      const a = sunAt(s.dateIso, m, s.origin.lat, s.origin.lon, s.tz).altDeg;
      samples.push([m, a]);
      maxAlt = Math.max(maxAlt, a);
    }
    for (const [m, a] of samples) {
      const x = ((m - lo) / (hi - lo)) * ARC_W;
      const y = ARC_H - 2 - (Math.max(-4, a) / maxAlt) * (ARC_H - 6);
      pts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
    }
    return { d: `M${pts.join(" L")}`, maxAlt };
  }, [s.dateIso, s.origin.lat, s.origin.lon, s.tz, lo, hi]);

  const frac = Math.min(1, Math.max(0, (s.minutes - lo) / (hi - lo)));
  const curAlt = s.sun.altDeg;
  const dotX = frac * ARC_W;
  const dotY = ARC_H - 2 - (Math.max(-4, curAlt) / arc.maxAlt) * (ARC_H - 6);
  const horizonY = ARC_H - 2;

  const now = () => {
    s.setPlaying(false);
    s.setMinutes(nowMinutes(s.tz));
  };

  return (
    <div
      className="zill-timebar pointer-events-auto fixed z-30 flex items-center gap-5 border border-[color:var(--zill-hairline)] bg-umber/[0.94] px-5 py-3"
      data-testid="time-bar"
    >
      <div className="zill-timebar-dates flex shrink-0 flex-col gap-1.5">
        <div className="flex gap-1.5">
          {PRESET_ORDER.filter((k) => s.presets[k]).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => s.setDate(k)}
              aria-pressed={s.dateKey === k}
              className={`border px-2.5 py-1 text-[11px] tracking-wide transition-colors ${
                s.dateKey === k
                  ? "border-brass/70 text-champagne"
                  : "border-[color:var(--zill-hairline)] text-ivory/55 hover:text-ivory/85"
              }`}
            >
              {LABEL[k]}
            </button>
          ))}
        </div>
        <span className="zill-timebar-sub tabular text-[11px] text-ivory/45">
          {fmtDate(s.presets[s.dateKey] ?? s.dateIso, s.tz)} &middot; {s.tz}
        </span>
      </div>

      <button
        type="button"
        onClick={() => s.setPlaying(!s.playing)}
        disabled={flying}
        aria-label={s.playing ? "Pause time-lapse" : "Play time-lapse"}
        className="zill-timebar-play flex h-9 w-9 shrink-0 items-center justify-center border border-[color:var(--zill-hairline)] text-champagne hover:bg-stone disabled:opacity-30"
      >
        {s.playing ? (
          <svg width="10" height="12" viewBox="0 0 10 12" aria-hidden>
            <rect x="0" y="0" width="3" height="12" fill="currentColor" />
            <rect x="7" y="0" width="3" height="12" fill="currentColor" />
          </svg>
        ) : (
          <svg width="10" height="12" viewBox="0 0 10 12" aria-hidden>
            <path d="M0 0 L10 6 L0 12 Z" fill="currentColor" />
          </svg>
        )}
      </button>

      <div className="zill-timebar-scrub relative min-w-0 flex-1">
        <svg
          viewBox={`0 0 ${ARC_W} ${ARC_H}`}
          preserveAspectRatio="none"
          className="block h-[34px] w-full"
          aria-hidden
        >
          <line
            x1="0"
            x2={ARC_W}
            y1={horizonY}
            y2={horizonY}
            stroke="rgb(244 238 225 / 0.12)"
            strokeWidth="1"
            vectorEffect="non-scaling-stroke"
          />
          <path
            d={arc.d}
            fill="none"
            stroke="var(--zill-brass)"
            strokeOpacity="0.75"
            strokeWidth="1"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
        <span
          className="pointer-events-none absolute h-[7px] w-[7px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-champagne"
          style={{
            left: `${((dotX / ARC_W) * 100).toFixed(2)}%`,
            top: `${((dotY / ARC_H) * 34).toFixed(1)}px`,
          }}
        />
        <input
          type="range"
          min={lo}
          max={hi}
          step={1}
          value={Math.round(Math.min(hi, Math.max(lo, s.minutes)))}
          onChange={(e) => {
            s.setPlaying(false);
            s.setMinutes(Number(e.target.value));
          }}
          disabled={flying}
          aria-label="Time of day"
          className="zill-range mt-1 w-full"
        />
        <div className="zill-timebar-sub tabular mt-0.5 flex justify-between text-[10px] text-ivory/40">
          <span>Sunrise {minutesToHHMM(s.sunrise, ":")}</span>
          <span>Sunset {minutesToHHMM(s.sunset, ":")}</span>
        </div>
      </div>

      <div className="zill-timebar-clock flex shrink-0 flex-col items-end">
        <span className="tabular font-display text-[34px] font-light leading-none text-champagne">
          {minutesToHHMM(s.minutes, ":")}
        </span>
        <span className="zill-timebar-sub tabular mt-1 text-[11px] text-ivory/45">
          {s.sun.altDeg < 0 ? (
            <>sun below horizon</>
          ) : (
            <>
              sun {s.sun.altDeg.toFixed(0)}&deg; alt &middot;{" "}
              {s.sun.azDeg.toFixed(0)}&deg; az
            </>
          )}
        </span>
      </div>
      <button
        type="button"
        onClick={now}
        disabled={flying}
        className="zill-timebar-now shrink-0 border border-[color:var(--zill-hairline)] px-3 py-1.5 text-[12px] text-ivory/70 hover:text-ivory disabled:opacity-30"
      >
        Now
      </button>
    </div>
  );
}
