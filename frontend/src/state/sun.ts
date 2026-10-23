// useSun: the scene clock. date_key + minutes-of-day -> sun alt/az via lib/sun.ts, in the active
// city's timezone (Dubai by default; the App switches city via `setCity`).
import { create } from "zustand";
import {
  DEFAULT_TZ,
  sunAt,
  sunTimesMinutes,
  type SunPos,
  type SunTimes,
} from "@/lib/sun";

/** Dubai preset dates (the Film and the default city). Other cities bring their own (meta.dates). */
export const PRESET_DATES: Record<string, string> = {
  winter: "2026-01-15",
  spring: "2026-04-15",
  summer: "2026-07-15",
  hackathon: "2026-10-24",
};
export const PRESET_ORDER = [
  "winter",
  "spring",
  "summer",
  "hackathon",
] as const;

export const ORIGIN_DEFAULT = { lat: 25.1972, lon: 55.2744 };

type SunState = {
  dateKey: string;
  dateIso: string;
  minutes: number;
  origin: { lat: number; lon: number };
  /** IANA timezone of the active city */
  tz: string;
  /** preset date ids -> ISO dates for the active city */
  presets: Record<string, string>;
  sun: SunPos;
  sunrise: number;
  sunset: number;
  dayKind: SunTimes["kind"];
  /** "Sun follows traveller" etc. may pin the clock; UI time-lapse sets playing */
  playing: boolean;
  setDate: (dateKey: string, dateIso?: string) => void;
  setMinutes: (m: number) => void;
  setOrigin: (o: { lat: number; lon: number }) => void;
  setPlaying: (p: boolean) => void;
  /** switch city: origin, timezone and preset dates (keeps the date key and time of day) */
  setCity: (c: {
    origin: { lat: number; lon: number };
    tz: string;
    presets?: Record<string, string>;
  }) => void;
};

function derive(
  dateIso: string,
  minutes: number,
  o: { lat: number; lon: number },
  tz: string,
) {
  const times = sunTimesMinutes(dateIso, o.lat, o.lon, tz);
  return {
    sun: sunAt(dateIso, minutes, o.lat, o.lon, tz),
    sunrise: times.sunrise,
    sunset: times.sunset,
    dayKind: times.kind,
  };
}

const initialIso = PRESET_DATES.hackathon!;

export const useSun = create<SunState>((set, get) => ({
  dateKey: "hackathon",
  dateIso: initialIso,
  minutes: 12 * 60,
  origin: ORIGIN_DEFAULT,
  tz: DEFAULT_TZ,
  presets: PRESET_DATES,
  ...derive(initialIso, 12 * 60, ORIGIN_DEFAULT, DEFAULT_TZ),
  playing: false,
  setDate: (dateKey, dateIso) => {
    const iso = dateIso ?? get().presets[dateKey] ?? dateKey;
    set({
      dateKey,
      dateIso: iso,
      ...derive(iso, get().minutes, get().origin, get().tz),
    });
  },
  setMinutes: (m) => {
    const minutes = Math.max(0, Math.min(24 * 60 - 1, m));
    const { dateIso, origin, tz } = get();
    set({ minutes, sun: sunAt(dateIso, minutes, origin.lat, origin.lon, tz) });
  },
  setOrigin: (o) =>
    set({ origin: o, ...derive(get().dateIso, get().minutes, o, get().tz) }),
  setPlaying: (playing) => set({ playing }),
  setCity: ({ origin, tz, presets }) => {
    const p = presets && Object.keys(presets).length ? presets : PRESET_DATES;
    const key = p[get().dateKey] ? get().dateKey : "hackathon";
    const iso = p[key] ?? get().dateIso;
    set({
      origin,
      tz,
      presets: p,
      dateKey: key,
      dateIso: iso,
      ...derive(iso, get().minutes, origin, tz),
    });
  },
}));
