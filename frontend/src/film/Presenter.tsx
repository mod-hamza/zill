"use client";
// ?presenter=1: compact strip — chapter, elapsed vs target, speed, next chapter's first talking
// point (docs/SPEAKER_NOTES.md, embedded by scripts/sync-film-data.mjs; falls back to the next
// chapter's title while the notes are not written).
import { useFilmData } from "./data";
import { CHAPTER_STARTS, CHAPTERS, TOTAL_S } from "./master";
import { useFilm } from "./store";

const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

export function Presenter() {
  const on = useFilm((s) => s.presenter);
  const t = useFilm((s) => s.t);
  const speed = useFilm((s) => s.speed);
  const playing = useFilm((s) => s.playing);
  const ch = useFilm((s) => s.frame?.chapter ?? 0);
  const notes = useFilmData((s) => s.data?.notes);
  if (!on) return null;
  const c = CHAPTERS[ch]!;
  const next = CHAPTERS[ch + 1];
  // SPEAKER_NOTES.md predates the renumbering: each chapter names its notes section (or has none)
  const nextNote = next
    ? ((next.notes ? notes?.[String(next.notes)]?.[0] : undefined) ?? `Next: ${next.title}`)
    : "End: press A for the live app";
  const target = CHAPTER_STARTS[ch]! + c.dur_s;
  return (
    <div className="film-presenter tabular">
      <span>
        {String(ch + 1).padStart(2, "0")} {c.title}
      </span>
      <span>
        {clock(t)} / {clock(TOTAL_S)} &middot; chapter ends {clock(target)}
      </span>
      <span>
        {playing ? "playing" : "paused"} &middot; {speed.toFixed(2)}&times;
      </span>
      <span className="film-presenter-note">{nextNote}</span>
    </div>
  );
}
