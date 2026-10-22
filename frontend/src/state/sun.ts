// useSun: the scene clock. date_key + minutes-of-day -> sun alt/az via lib/sun.ts.
import { create } from "zustand";
import { sunAt, sunTimesMinutes, type SunPos } from "@/lib/sun";

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
  sun: SunPos;
  sunrise: number;
  sunset: number;
  /** "Sun follows traveller" etc. may pin the clock; UI time-lapse sets playing */
  playing: boolean;
  setDate: (dateKey: string, dateIso?: string) => void;
  setMinutes: (m: number) => void;
  setOrigin: (o: { lat: number; lon: number }) => void;
  setPlaying: (p: boolean) => void;
};

function derive(
  dateIso: string,
  minutes: number,
  o: { lat: number; lon: number },
) {
  const times = sunTimesMinutes(dateIso, o.lat, o.lon);
  return {
    sun: sunAt(dateIso, minutes, o.lat, o.lon),
    sunrise: times.sunrise,
    sunset: times.sunset,
  };
}

const initialIso = PRESET_DATES.hackathon!;

export const useSun = create<SunState>((set, get) => ({
  dateKey: "hackathon",
  dateIso: initialIso,
  minutes: 12 * 60,
  origin: ORIGIN_DEFAULT,
  ...derive(initialIso, 12 * 60, ORIGIN_DEFAULT),
  playing: false,
  setDate: (dateKey, dateIso) => {
    const iso = dateIso ?? PRESET_DATES[dateKey] ?? dateKey;
    set({ dateKey, dateIso: iso, ...derive(iso, get().minutes, get().origin) });
  },
  setMinutes: (m) => {
    const minutes = Math.max(0, Math.min(24 * 60 - 1, m));
    set({
      minutes,
      sun: sunAt(get().dateIso, minutes, get().origin.lat, get().origin.lon),
    });
  },
  setOrigin: (o) =>
    set({ origin: o, ...derive(get().dateIso, get().minutes, o) }),
  setPlaying: (playing) => set({ playing }),
}));
