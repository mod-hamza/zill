"use client";

import { usePathname } from "next/navigation";

// /film and /app render their own attribution inside the stage; this footer covers every other page.
const STAGE_PREFIXES = ["/film", "/app"];

export function Footer() {
  const pathname = usePathname();
  if (STAGE_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`))) return null;
  return (
    <footer className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex justify-between px-6 py-3 text-[11px] tracking-wide text-ivory/50">
      <span>&copy; OpenStreetMap contributors</span>
      <span>Model v1: buildings, mapped trees, covered links</span>
    </footer>
  );
}
