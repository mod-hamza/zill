"use client";
// Top command bar (PRD 12.6): serif placeholder, hairline underline, brass caret.
// Two jobs (CONTRACTS "Overnight additions — Stream E"):
//  - search-as-you-type over the city's full name index (GET /api/places/search); picking a place
//    sets A, then B. Online (Nominatim) results are labelled "online".
//  - a one-line journey, e.g. "from Burj Park to Dubai Mall at 15:30 sunny", parsed by
//    POST /api/places/parse and applied in one go (A, B, time, mode, preference). Ambiguous names
//    open a picker of the parser's candidates.
// Keyboard: Up/Down move, Enter picks (or plans a journey), Esc clears.
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type PlaceHit, type PlaceParse, type Poi } from "@/lib/api";
import { isFixture } from "@/lib/assets";
import { looksLikeJourney } from "@/lib/journeyText";
import { hhmmToMinutes } from "@/lib/sun";
import { useCity } from "@/state/city";
import { useRoute, type Endpoint } from "@/state/route";
import { useRig } from "@/state/rig";
import { useSun } from "@/state/sun";
import { frameRouteView } from "@/three/AppDrivers";

const DEBOUNCE_MS = 110;
const MAX_HITS = 7;

function localHits(pois: Poi[] | null, q: string): PlaceHit[] {
  if (!pois || !q.trim()) return [];
  const s = q.toLowerCase().trim();
  const score = (p: Poi) => {
    const n = p.name.toLowerCase();
    if (n.startsWith(s)) return 3;
    if (n.split(/[\s/,-]+/).some((w) => w.startsWith(s))) return 2;
    return n.includes(s) ? 1 : 0;
  };
  return pois
    .map((p) => ({ p, s: score(p) }))
    .filter((x) => x.s > 0)
    .sort((x, y) => y.s - x.s || x.p.name.localeCompare(y.p.name))
    .slice(0, MAX_HITS)
    .map(({ p }) => ({ ...p, source: "index" }));
}

function toEndpoint(p: PlaceHit): Endpoint {
  const g = useCity.getState().graph;
  const node = p.node ?? (g ? g.nearest(p.x, p.z) : -1);
  return { node, x: p.x, z: p.z, lat: p.lat, lon: p.lon, name: p.name };
}

type Picker = {
  side: "origin" | "dest";
  candidates: PlaceHit[];
  parse: PlaceParse;
};

const KIND_LABEL: Record<string, string> = {
  station: "station",
  stop: "stop",
  landmark: "landmark",
  mall: "mall",
  square: "square",
  park: "park",
  hotel: "hotel",
  street: "street",
  food: "food",
  shop: "shop",
  building: "building",
  amenity: "place",
  other: "place",
};

export function CommandBar() {
  const pois = useCity((s) => s.pois);
  const cityId = useCity((s) => s.cityId);
  const cityName = useCity((s) => s.meta?.name);
  const a = useRoute((s) => s.a);
  const b = useRoute((s) => s.b);
  const [q, setQ] = useState("");
  const [focus, setFocus] = useState(false);
  const [hits, setHits] = useState<PlaceHit[]>([]);
  const [active, setActive] = useState(0);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [picker, setPicker] = useState<Picker | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const journey = useMemo(() => looksLikeJourney(q), [q]);

  // search-as-you-type (debounced, aborted when superseded)
  useEffect(() => {
    const text = q.trim();
    if (!text || journey) {
      setHits([]);
      return;
    }
    if (isFixture()) {
      setHits(localHits(pois, text));
      return;
    }
    const ctl = new AbortController();
    const id = window.setTimeout(() => {
      api
        .searchPlaces(cityId, text.slice(0, 200), MAX_HITS, {
          signal: ctl.signal,
        })
        .then((r) => {
          setHits(r.results);
          setActive(0);
        })
        .catch((e: unknown) => {
          if ((e as { name?: string })?.name === "AbortError") return;
          setHits(localHits(pois, text));
        });
    }, DEBOUNCE_MS);
    return () => {
      ctl.abort();
      window.clearTimeout(id);
    };
  }, [q, journey, cityId, pois]);

  // reset when the city changes
  useEffect(() => {
    setQ("");
    setHits([]);
    setPicker(null);
    setNote(null);
  }, [cityId]);

  // ?ask=<one line> pre-fills and plans (shareable links, QA)
  useEffect(() => {
    const ask = new URLSearchParams(window.location.search).get("ask");
    if (!ask) return;
    const unsub = useCity.subscribe((s) => {
      if (s.loaded) {
        unsub();
        setQ(ask);
        void runParse(ask);
      }
    });
    if (useCity.getState().loaded) {
      unsub();
      setQ(ask);
      void runParse(ask);
    }
    return unsub;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once on mount
  }, []);

  const pick = (p: PlaceHit) => {
    useRoute.getState().clickPoint(toEndpoint(p));
    setQ("");
    setHits([]);
    setNote(null);
  };

  /** Apply a (possibly picker-resolved) parse: endpoints, time, mode, preference, then route. */
  const applyParse = (
    r: PlaceParse,
    origin: PlaceHit,
    dest: PlaceHit,
    text = q,
  ) => {
    const explicitDay = /(today|tomorrow|tonight|\d{4}-\d\d-\d\d)|غد|اليوم|i morgen|i dag/i.test(
      text,
    );
    const sun = useSun.getState();
    const notes: string[] = [];
    // the parser fills depart_date for any time; only honour it when the text names a day
    if (r.depart_date && explicitDay) {
      const key = Object.entries(sun.presets).find(
        ([, iso]) => iso === r.depart_date,
      )?.[0];
      if (key) sun.setDate(key);
      else
        notes.push(
          `Shade is baked for preset dates; showing ${sun.dateIso} for ${r.depart_date}.`,
        );
    }
    if (r.depart_time) {
      sun.setPlaying(false);
      sun.setMinutes(hhmmToMinutes(r.depart_time));
    }
    const rs = useRoute.getState();
    useRoute.setState({
      a: toEndpoint(origin),
      b: toEndpoint(dest),
      activeScenario: null,
      flyT: null,
      error: null,
      ...(r.mode ? { mode: r.mode } : {}),
      ...(r.preference ? { preference: r.preference } : {}),
    });
    void rs.request().then(() => {
      const res = useRoute.getState().result;
      if (res) useRig.getState().setView(frameRouteView(res.coolest));
    });
    setQ("");
    setPicker(null);
    setNote(notes.length ? notes.join(" ") : null);
  };

  const runParse = async (text: string) => {
    if (isFixture()) {
      setNote("Typed journeys need the live API (not the synthetic fixture).");
      return;
    }
    setBusy(true);
    setNote(null);
    try {
      const r = await api.parsePlaces(
        useCity.getState().cityId,
        text.slice(0, 300),
      );
      const o = r.origin;
      const d = r.dest;
      if (!o && !d) {
        setNote(`No places found in "${text}".`);
      } else if (!o || r.ambiguous.origin) {
        const c = r.origin_candidates.length
          ? r.origin_candidates
          : o
            ? [o]
            : [];
        if (c.length) setPicker({ side: "origin", candidates: c, parse: r });
        else setNote(`Could not find the start "${r.parsed.origin_text ?? ""}".`);
      } else if (!d || r.ambiguous.dest) {
        const c = r.dest_candidates.length ? r.dest_candidates : d ? [d] : [];
        if (c.length) setPicker({ side: "dest", candidates: c, parse: r });
        else {
          useRoute.getState().clickPoint(toEndpoint(o));
          setNote(`Start set. Could not find "${r.parsed.dest_text ?? ""}".`);
        }
      } else {
        applyParse(r, o, d, text);
      }
      setActive(0);
    } catch (e) {
      setNote(
        `Could not read that journey (${e instanceof Error ? e.message : String(e)}).`,
      );
    } finally {
      setBusy(false);
    }
  };

  const choosePicked = (p: PlaceHit) => {
    if (!picker) return;
    const r = picker.parse;
    if (picker.side === "origin") {
      const next: PlaceParse = {
        ...r,
        origin: p,
        ambiguous: { ...r.ambiguous, origin: false },
      };
      if (!r.dest || r.ambiguous.dest) {
        const c = r.dest_candidates.length
          ? r.dest_candidates
          : r.dest
            ? [r.dest]
            : [];
        if (c.length) {
          setPicker({ side: "dest", candidates: c, parse: next });
          setActive(0);
          return;
        }
        useRoute.getState().clickPoint(toEndpoint(p));
        setPicker(null);
        return;
      }
      applyParse(next, p, r.dest);
    } else {
      applyParse(r, r.origin!, p);
    }
  };

  // rows shown under the bar
  const rows: { key: string; hit?: PlaceHit; plan?: boolean }[] = picker
    ? picker.candidates.slice(0, MAX_HITS).map((h) => ({ key: h.id, hit: h }))
    : journey
      ? [{ key: "plan", plan: true }]
      : hits.map((h) => ({ key: h.id, hit: h }));

  const enter = () => {
    const row = rows[Math.min(active, rows.length - 1)];
    if (picker && row?.hit) return choosePicked(row.hit);
    if (journey || row?.plan) return void runParse(q);
    if (row?.hit) return pick(row.hit);
  };

  const city = cityName ?? "the city";
  const placeholder = !a
    ? "Where from? Or type: from A to B at 15:30"
    : !b
      ? "And where to?"
      : `Search ${city}`;

  return (
    <div
      className="zill-commandbar pointer-events-auto fixed left-1/2 top-6 z-40 w-[min(560px,calc(100vw-48px))] -translate-x-1/2"
      data-testid="command-bar"
    >
      <div className="relative">
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPicker(null);
            setActive(0);
          }}
          onFocus={() => setFocus(true)}
          onBlur={() => window.setTimeout(() => setFocus(false), 150)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((i) => Math.min(rows.length - 1, i + 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((i) => Math.max(0, i - 1));
            } else if (e.key === "Enter") {
              e.preventDefault();
              enter();
            } else if (e.key === "Escape") {
              setQ("");
              setPicker(null);
              setNote(null);
              inputRef.current?.blur();
            }
          }}
          placeholder={placeholder}
          aria-label="Search a place or type a journey"
          aria-expanded={focus && rows.length > 0}
          aria-controls="zill-command-list"
          aria-activedescendant={
            rows[active] ? `zill-cmd-${rows[active]!.key}` : undefined
          }
          role="combobox"
          aria-autocomplete="list"
          spellCheck={false}
          maxLength={300}
          className="zill-command w-full border-0 border-b border-[color:var(--zill-hairline)] bg-umber/[0.72] px-4 pb-2 pt-1.5 text-center font-display text-[22px] font-light text-champagne outline-none placeholder:text-champagne/45 focus:border-sand/40"
        />
        {(focus || picker) && rows.length > 0 ? (
          <ul
            id="zill-command-list"
            role="listbox"
            className="absolute left-0 right-0 top-full mt-2 border border-[color:var(--zill-hairline)] bg-umber/[0.95]"
          >
            {picker ? (
              <li className="smallcaps border-b border-[color:var(--zill-hairline)] px-4 py-1.5 text-[10px] text-sand/60">
                Which {picker.side === "origin" ? "start" : "destination"}
                {picker.side === "origin"
                  ? picker.parse.parsed.origin_text
                    ? ` for “${picker.parse.parsed.origin_text}”`
                    : ""
                  : picker.parse.parsed.dest_text
                    ? ` for “${picker.parse.parsed.dest_text}”`
                    : ""}
                ?
              </li>
            ) : null}
            {rows.map((r, i) => (
              <li
                key={r.key}
                id={`zill-cmd-${r.key}`}
                role="option"
                aria-selected={i === active}
              >
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => {
                    setActive(i);
                    if (r.plan) void runParse(q);
                    else if (r.hit)
                      if (picker) choosePicked(r.hit);
                      else pick(r.hit);
                  }}
                  className={`flex w-full items-baseline justify-between gap-3 px-4 py-2 text-left text-[14px] text-ivory/85 ${
                    i === active ? "bg-stone" : ""
                  }`}
                >
                  {r.plan ? (
                    <>
                      <span className="truncate">
                        {busy ? "Reading the journey…" : `Plan: ${q.trim()}`}
                      </span>
                      <span className="smallcaps shrink-0 text-[10px] text-sand/50">
                        Enter
                      </span>
                    </>
                  ) : r.hit ? (
                    <>
                      <span className="min-w-0 truncate">
                        {r.hit.name}
                        {r.hit.matched && r.hit.matched !== r.hit.name ? (
                          <span className="ml-2 text-[12px] text-ivory/45">
                            {r.hit.matched}
                          </span>
                        ) : null}
                      </span>
                      <span className="flex shrink-0 items-baseline gap-2">
                        {r.hit.source === "online" ? (
                          <span className="border border-clay/60 px-1.5 text-[10px] tracking-wide text-clay">
                            online
                          </span>
                        ) : null}
                        <span className="smallcaps text-[10px] text-sand/50">
                          {KIND_LABEL[r.hit.kind] ?? r.hit.kind}
                        </span>
                      </span>
                    </>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        {note && !(focus && rows.length > 0) ? (
          <p
            className="mt-2 text-center text-[12px] text-ivory/55"
            role="status"
          >
            {note}
          </p>
        ) : null}
      </div>
    </div>
  );
}
