// Where baked city assets come from (CONTRACTS section 8: always via the backend files endpoint).
// `?fixture=1` (or NEXT_PUBLIC_ZILL_FIXTURE=1) switches to the synthetic dev fixture in
// public/dev-fixture/ — used only while the real bake is not available. Labelled in the UI.

export function isFixture(): boolean {
  if (process.env.NEXT_PUBLIC_ZILL_FIXTURE === "1") return true;
  if (typeof window === "undefined") return false;
  return new URLSearchParams(window.location.search).get("fixture") === "1";
}

export function assetUrl(city: string, name: string): string {
  if (isFixture()) return `/dev-fixture/${name}`;
  return `/api/cities/${encodeURIComponent(city)}/files/${name}`;
}

export function shadeStepUrl(
  city: string,
  dateId: string,
  file: string,
): string {
  return assetUrl(city, `shade/${dateId}/${file}`);
}
