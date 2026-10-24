import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

// Backend origin for the /api proxy. Local default; the Docker deploy sets ZILL_API_ORIGIN at build
// time (rewrites are compiled into the build) to reach the API container by name.
const API_ORIGIN = process.env.ZILL_API_ORIGIN ?? "http://127.0.0.1:8000";

// --- security headers (docs/SECURITY.md) -------------------------------------------------------------
// Next injects inline bootstrap scripts, so script-src needs 'unsafe-inline' unless a per-request nonce
// middleware is added (which would make every page dynamic). 'unsafe-eval' is only added for `next dev`
// (React refresh); the production build is checked in e2e without it. blob:/data: cover three.js textures.
const CSP_BASE = (dev: boolean): string[] => [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${dev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  `connect-src 'self' blob: data:${dev ? " ws: wss:" : ""}`,
  "media-src 'self' blob:",
  "worker-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
];

function securityHeaders(dev: boolean) {
  const common = [
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    // geolocation only for our own origin (the "use my location" button); everything else off
    {
      key: "Permissions-Policy",
      value: "geolocation=(self), camera=(), microphone=(), payment=(), usb=(), interest-cohort=()",
    },
    // HSTS: 1 year, no includeSubDomains (the apex hosts other apps), no preload
    ...(dev ? [] : [{ key: "Strict-Transport-Security", value: "max-age=31536000" }]),
  ];
  return [
    {
      // everything except /embed: not frameable
      source: "/((?!embed).*)",
      headers: [
        ...common,
        { key: "X-Frame-Options", value: "DENY" },
        { key: "Content-Security-Policy", value: [...CSP_BASE(dev), "frame-ancestors 'none'"].join("; ") },
      ],
    },
    {
      // the hotel widget is meant to be iframed on partner sites
      source: "/embed/:path*",
      headers: [
        ...common,
        { key: "Content-Security-Policy", value: [...CSP_BASE(dev), "frame-ancestors *"].join("; ") },
      ],
    },
  ];
}

export default function config(phase: string): NextConfig {
  return {
    reactStrictMode: true,
    devIndicators: false,
    // `next dev` writes to its own folder: a `next build` (demo, record, deck) used to overwrite the
    // chunks a running dev server was serving, which surfaced as "Application error" (ChunkLoadError)
    // ZILL_DIST_DIR: a second server/build (e.g. a parallel agent on another port) gets its own folder
    distDir: process.env.ZILL_DIST_DIR ?? (phase === PHASE_DEVELOPMENT_SERVER ? ".next-dev" : ".next"),
    async headers() {
      return securityHeaders(phase === PHASE_DEVELOPMENT_SERVER);
    },
    async rewrites() {
      return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
    },
  };
}
