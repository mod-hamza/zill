import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

// Backend origin for the /api proxy. Local default; the Docker deploy sets ZILL_API_ORIGIN at build
// time (rewrites are compiled into the build) to reach the API container by name.
const API_ORIGIN = process.env.ZILL_API_ORIGIN ?? "http://127.0.0.1:8000";

export default function config(phase: string): NextConfig {
  return {
    reactStrictMode: true,
    devIndicators: false,
    // `next dev` writes to its own folder: a `next build` (demo, record, deck) used to overwrite the
    // chunks a running dev server was serving, which surfaced as "Application error" (ChunkLoadError)
    distDir: phase === PHASE_DEVELOPMENT_SERVER ? ".next-dev" : ".next",
    async rewrites() {
      return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
    },
  };
}
