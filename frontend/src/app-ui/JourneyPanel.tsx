"use client";
// Right Journey panel (PRD 15): Fastest / Balanced / Coolest with real stats from /api/route,
// travel mode, coolness lambda, view toggle, fly-through, hero journeys, source badges.
import { colors } from "@/design/tokens";
import type { Mode, Route } from "@/lib/api";
import { fmtKm, fmtMin, fmtPct, fmtSigned } from "@/lib/format";
import { useCity } from "@/state/city";
import { useRig } from "@/state/rig";
import { useRoute, type RouteKey } from "@/state/route";
import { frameRouteView } from "@/three/AppDrivers";

const MODES: { id: Mode; label: string }[] = [
  { id: "walk", label: "Walk" },
  { id: "cycle", label: "Cycle" },
  { id: "scooter", label: "Scooter" },
];

const CARDS: { k: RouteKey; label: string; color: string }[] = [
  { k: "fastest", label: "Fastest", color: colors.slate },
  { k: "balanced", label: "Balanced", color: colors.bronze },
  { k: "coolest", label: "Coolest", color: colors.brass },
];

const PERSONA: Record<string, string> = {
  tourist: "Tourist walk",
  rider: "Delivery rider",
  crew: "Crew shuttle",
};

function Segmented<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { id: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex border border-[color:var(--zill-hairline)]">
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          onClick={() => onChange(o.id)}
          aria-pressed={value === o.id}
          className={`flex-1 px-3 py-1.5 text-[12px] tracking-wide transition-colors ${
            value === o.id
              ? "bg-stone text-champagne"
              : "text-ivory/55 hover:text-ivory/85"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function Card({
  k,
  label,
  color,
  route,
  selected,
  onSelect,
}: {
  k: RouteKey;
  label: string;
  color: string;
  route: Route;
  selected: boolean;
  onSelect: () => void;
}) {
  const st = route.stats;
  const rel = k !== "fastest";
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`w-full border-t border-[color:var(--zill-hairline)] px-1 py-3 text-left transition-colors ${selected ? "" : "opacity-70 hover:opacity-100"}`}
    >
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2">
          <span
            className="inline-block h-px w-5"
            style={{ background: color, height: selected ? 2 : 1 }}
          />
          <span className="smallcaps text-[11px] text-sand/80">{label}</span>
        </span>
        <span className="tabular text-[12px] text-ivory/50">
          {fmtKm(st.distance_m)}
        </span>
      </div>
      <div className="mt-2 flex items-baseline gap-5">
        <span className="tabular font-display text-[30px] font-light leading-none text-champagne">
          {fmtMin(st.duration_s)}
          <span className="ml-1 font-sans text-[12px] text-ivory/50">min</span>
        </span>
        <span className="tabular text-[13px] text-ivory/75">
          <span style={{ color: colors.ember }}>
            {fmtMin(st.sun_exposure_s)}
          </span>{" "}
          min sun
        </span>
        <span className="tabular text-[13px] text-ivory/75">
          {fmtPct(st.shaded_pct)} shade
        </span>
      </div>
      {rel ? (
        <div className="tabular mt-1.5 text-[12px] text-ivory/50">
          {fmtSigned(st.added_time_s)} time &middot;{" "}
          {fmtSigned(-st.sun_saved_s)} sun &middot; RHL{" "}
          {st.rhl_saved_pct >= 0 ? "−" : "+"}
          {Math.abs(st.rhl_saved_pct).toFixed(0)}%
        </div>
      ) : (
        <div className="mt-1.5 text-[12px] text-ivory/40">Reference route</div>
      )}
      {st.covered_pct + st.indoor_pct > 0.5 ? (
        <div
          className="tabular mt-1 text-[12px]"
          style={{ color: colors.oasis }}
        >
          {fmtPct(st.covered_pct + st.indoor_pct)} covered or indoor
        </div>
      ) : null}
      {st.note ? (
        <div className="mt-1 text-[11px] text-ivory/45">{st.note}</div>
      ) : null}
    </button>
  );
}

export function JourneyPanel() {
  const r = useRoute();
  const fixture = useCity((s) => s.fixture);
  const scenarios = r.scenarios;
  const res = r.result;

  const startFly = () => {
    if (!res) return;
    r.setFlyT(0);
  };
  const stopFly = () => {
    r.setFlyT(null);
    const route = res?.[r.selected];
    if (route) useRig.getState().setView(frameRouteView(route));
  };

  return (
    <aside className="pointer-events-auto fixed right-6 top-[96px] z-30 flex max-h-[calc(100vh-260px)] w-[344px] flex-col overflow-y-auto border border-[color:var(--zill-hairline)] bg-umber/[0.92] px-5 pb-5 pt-4">
      <div className="flex items-baseline justify-between">
        <h2 className="smallcaps text-sand/70">Journey</h2>
        {r.a || r.b ? (
          <button
            type="button"
            onClick={r.clear}
            className="text-[11px] text-ivory/45 hover:text-ivory/80"
          >
            Clear
          </button>
        ) : null}
      </div>

      <div className="mt-3 space-y-1.5 font-display text-[17px] font-light text-champagne">
        <p className="truncate">
          <span className="mr-2 font-sans text-[11px] text-brass">A</span>
          {r.a ? (
            (r.a.name ?? `Node ${r.a.node}`)
          ) : (
            <span className="text-ivory/40">Click the map or search</span>
          )}
        </p>
        <p className="truncate">
          <span className="mr-2 font-sans text-[11px] text-brass">B</span>
          {r.b ? (
            (r.b.name ?? `Node ${r.b.node}`)
          ) : (
            <span className="text-ivory/40">
              {r.a ? "Now the destination" : "—"}
            </span>
          )}
        </p>
      </div>

      <div className="mt-4">
        <Segmented
          value={r.mode}
          options={MODES}
          onChange={(m) => r.setMode(m)}
        />
      </div>

      {r.loading ? (
        <p className="mt-4 text-[12px] text-ivory/55">
          Routing through the shade&hellip;
        </p>
      ) : null}
      {r.error ? (
        <p className="mt-4 text-[12px] text-clay">Routing failed: {r.error}</p>
      ) : null}

      {res ? (
        <div className="mt-4">
          {CARDS.map((c) => {
            const route = res[c.k];
            return route ? (
              <Card
                key={c.k}
                {...c}
                route={route}
                selected={r.selected === c.k}
                onSelect={() => r.setSelected(c.k)}
              />
            ) : null;
          })}
        </div>
      ) : null}

      <div className="mt-4 border-t border-[color:var(--zill-hairline)] pt-4">
        <div className="flex items-baseline justify-between">
          <label
            htmlFor="zill-lambda"
            className="smallcaps text-[11px] text-sand/70"
          >
            Coolness
          </label>
          <span className="tabular text-[12px] text-ivory/60">
            &lambda; {r.lambda.toFixed(1)}
          </span>
        </div>
        <input
          id="zill-lambda"
          type="range"
          min={0}
          max={3}
          step={0.1}
          value={r.lambda}
          onChange={(e) => r.setLambda(Number(e.target.value))}
          onPointerUp={() => void r.request()}
          onKeyUp={() => void r.request()}
          className="zill-range mt-2 w-full"
        />
        <p className="mt-1 text-[11px] text-ivory/40">
          Sets the balanced route&rsquo;s weight on sun exposure.
        </p>
      </div>

      <div className="mt-4">
        <Segmented
          value={r.view}
          options={[
            { id: "presentation", label: "Presentation" },
            { id: "analysis", label: "Analysis" },
          ]}
          onChange={(v) => r.setView(v)}
        />
      </div>

      {res ? (
        <button
          type="button"
          onClick={r.flyT === null ? startFly : stopFly}
          className="mt-4 border border-brass/60 px-4 py-2.5 text-[13px] tracking-wide text-champagne transition-colors hover:bg-stone"
        >
          {r.flyT === null ? "Fly me through it" : "Stop fly-through"}
        </button>
      ) : null}

      {scenarios.length > 0 ? (
        <div className="mt-5 border-t border-[color:var(--zill-hairline)] pt-4">
          <p className="smallcaps text-[11px] text-sand/70">
            Try a hero journey
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {scenarios.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => {
                  r.applyScenario(s.id);
                  useRig.getState().setView(frameRouteView(s.coolest));
                }}
                className={`border px-3 py-1 text-[12px] transition-colors ${
                  r.activeScenario === s.id
                    ? "border-brass/70 text-champagne"
                    : "border-[color:var(--zill-hairline)] text-ivory/70 hover:text-ivory"
                }`}
              >
                {PERSONA[s.persona] ?? s.id}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-5 flex flex-wrap gap-2 text-[10px] tracking-wide text-ivory/45">
        {fixture ? (
          <span className="border border-clay/60 px-2 py-0.5 text-clay">
            Synthetic fixture
          </span>
        ) : null}
        <span className="border border-[color:var(--zill-hairline)] px-2 py-0.5">
          Routes: computed
        </span>
        <span className="border border-[color:var(--zill-hairline)] px-2 py-0.5">
          Shade: baked raster
        </span>
        {r.activeScenario ? (
          <span className="border border-[color:var(--zill-hairline)] px-2 py-0.5">
            Hero: cached scenario
          </span>
        ) : null}
      </div>
    </aside>
  );
}
