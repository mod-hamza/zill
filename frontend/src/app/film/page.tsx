import { NAME, TAGLINE } from "@/brand";

export default function FilmPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-ink px-6 text-center">
      <h1 className="font-display text-champagne" style={{ fontWeight: 300, fontSize: "clamp(4rem, 12vw, 11rem)" }}>
        {NAME}
      </h1>
      <p className="smallcaps mt-6 text-ivory">{TAGLINE}</p>
    </main>
  );
}
