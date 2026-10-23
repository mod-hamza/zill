// Client-side hint for the command bar: is the typed text a one-line journey (parsed by
// POST /api/places/parse) or a single place to search? The server does the real parsing.
/** Heuristic: does the text read as a journey ("from X to Y", "X to Y", "X → Y", Arabic)? */
export function looksLikeJourney(text: string): boolean {
  const t = text.trim();
  if (t.length < 4) return false;
  return (
    /(^|\s)from\s+\S/i.test(t) ||
    /\S\s+to\s+\S/i.test(t) ||
    /\S\s*(→|->)\s*\S/.test(t) ||
    /\S\s+[-–]\s+\S/.test(t) ||
    /(^|\s)من\s+\S/.test(t)
  );
}
