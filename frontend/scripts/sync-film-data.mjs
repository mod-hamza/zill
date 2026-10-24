// Copies the Film's non-API inputs VERBATIM into public/film-data/ (served statically, no network):
//   backend/replay/*.json      -> public/film-data/replays/   (the API has no replay-body endpoint)
//   data/test_results.json     -> public/film-data/test_results.json
//   data/scenarios/case_studies.json -> public/film-data/case_studies.json
//   data/validation/field_test.json (if it exists) -> public/film-data/field_test.json
//   docs/SPEAKER_NOTES.md      -> public/film-data/notes.json  ({ "<chapter number>": [points] })
//   docs/COSTS.md · SECURITY.md · ACCURACY.md -> public/film-data/facts.json (values extracted, never edited)
// Run: node scripts/sync-film-data.mjs   (also wired as npm predev/prebuild)
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(here, "..", "..");
const OUT = resolve(here, "..", "public", "film-data");

mkdirSync(join(OUT, "replays"), { recursive: true });
const log = [];

const rdir = join(ROOT, "backend", "replay");
if (existsSync(rdir)) {
  for (const f of readdirSync(rdir).filter((x) => x.endsWith(".json"))) {
    copyFileSync(join(rdir, f), join(OUT, "replays", f));
    log.push(`replays/${f}`);
  }
}
const tr = join(ROOT, "data", "test_results.json");
if (existsSync(tr)) {
  copyFileSync(tr, join(OUT, "test_results.json"));
  log.push("test_results.json");
}
const cs = join(ROOT, "data", "scenarios", "case_studies.json");
if (existsSync(cs)) {
  copyFileSync(cs, join(OUT, "case_studies.json"));
  log.push("case_studies.json");
}
const pp = join(ROOT, "data", "curated", "policy_packs", "uae_outdoor_work.json");
if (existsSync(pp)) {
  copyFileSync(pp, join(OUT, "policy_uae_outdoor_work.json"));
  log.push("policy_uae_outdoor_work.json");
}
const ft = join(ROOT, "data", "validation", "field_test.json");
if (existsSync(ft)) {
  copyFileSync(ft, join(OUT, "field_test.json"));
  log.push("field_test.json");
} else if (existsSync(join(OUT, "field_test.json"))) {
  rmSync(join(OUT, "field_test.json"));
}

// Speaker notes: "## <n>." or "## Chapter <n>" headings; bullet lines below become talking points.
const sn = join(ROOT, "docs", "SPEAKER_NOTES.md");
const notes = {};
if (existsSync(sn)) {
  let cur = null;
  for (const line of readFileSync(sn, "utf8").split(/\r?\n/)) {
    const h = line.match(/^#{2,3}\s+(?:Chapter\s+|Ch\.?\s*)?(\d{1,2})\b/i);
    if (h) {
      cur = String(Number(h[1]));
      notes[cur] = [];
      continue;
    }
    if (/^#/.test(line)) {
      cur = null;
      continue;
    }
    const b = line.match(/^\s*(?:[-*]|\d+\.)\s+(.*)$/);
    if (cur && b && b[1].trim()) notes[cur].push(b[1].trim());
  }
}
writeFileSync(join(OUT, "notes.json"), JSON.stringify(notes, null, 1));
log.push(`notes.json (${Object.keys(notes).length} chapters)`);

// Business facts for the Film's cost / security / accuracy chapters, extracted VERBATIM from the
// committed docs (docs/COSTS.md, docs/SECURITY.md, docs/ACCURACY.md). Anything not found stays null
// and the Film shows a [TEAM TO FILL] placeholder instead of a number. Never edit values here.
const readDoc = (rel) => {
  const f = join(ROOT, ...rel.split("/"));
  return existsSync(f) ? readFileSync(f, "utf8") : "";
};
const num = (x) => {
  if (x === undefined || x === null) return null;
  const v = Number(String(x).replace(/,/g, "").trim());
  return Number.isFinite(v) ? v : null;
};
const m1 = (text, re) => {
  const m = text.match(re);
  return m ? m[1] : null;
};
/** body rows of the first markdown table after `anchor` (cells trimmed; header + rule skipped) */
function tableAfter(text, anchor) {
  const i = text.indexOf(anchor);
  if (i < 0) return [];
  const rows = [];
  let inTable = false;
  for (const l of text.slice(i).split(/\r?\n/)) {
    if (l.trim().startsWith("|")) {
      inTable = true;
      rows.push(l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim()));
    } else if (inTable) break;
  }
  return rows.slice(2);
}
const costsMd = readDoc("docs/COSTS.md");
const secMd = readDoc("docs/SECURITY.md");
const accMd = readDoc("docs/ACCURACY.md");
const loadRows = (anchor) =>
  tableAfter(costsMd, anchor).map((r) => ({
    users: num(r[0]),
    requests: num(r[1]),
    rps: num(r[2]),
    p50_ms: num(r[3]?.replace(/ms/, "")),
    p95_ms: num(r[4]?.replace(/ms/, "")),
    errors: num(r[6]),
  }));
const facts = {
  costs: {
    source: "docs/COSTS.md",
    vps_price: m1(costsMd, /Contabo VPS plan price:\s*`([^`]+)`/),
    go_usd_month: num(m1(costsMd, /Go is \*\*\$(\d+)\/month\*\*/)),
    goplus_usd_month: num(m1(costsMd, /Go Plus \*\*\$(\d+)\/month\*\*/)),
    llm: tableAfter(costsMd, "| Model | Go requests/mo").map((r) => ({
      model: r[0],
      go_requests_month: num(r[1]),
      go_conversations_month: num(r[2]?.replace(/about\s*/, "")),
    })),
    requests_per_conversation: num(m1(costsMd, /\| mean \| ([\d.]+) \|/)),
    local_load: loadRows("**Local machine**"),
    live_load: loadRows("**Live VM**"),
    shade_bake_s: num(m1(costsMd, /\*\*Shade bake:\*\* ([\d.]+) s/)),
    shade_bake_dates: m1(costsMd, /\*\*Shade bake:\*\* [\d.]+ s for (\w+) dates/),
    data_bake_s: num(m1(costsMd, /\*\*Data bake \(Dubai\):\*\* ([\d.]+) s/)),
  },
  security: {
    source: "docs/SECURITY.md",
    tests: num(m1(secMd, /test_security\.py` \((\d+) tests/)),
    body_cap_kb: num(m1(secMd, /Request body at most (\d+) KB/)),
  },
  accuracy: {
    source: "docs/ACCURACY.md",
    shadow_step_min: num(m1(accMd, /every \*\*(\d+) minutes\*\*/)),
    grid_m: num(m1(accMd, /on a \*\*(\d+) m\*\* grid/)),
    departure_step_min: num(m1(accMd, /DEPARTURE_STEP_MIN = (\d+)/)),
    weather_hourly: /Weather[^\n]*\*\*hourly\*\*/.test(accMd),
    sun_within_deg: num(m1(accMd, /within ([\d.]+)°/)),
    heights_fallback_pct: num(m1(accMd, /about (\d+)% of Dubai's footprints/)),
    weekly_rebake: /weekly scheduled re-bake is the production plan, not yet running/.test(accMd)
      ? "planned"
      : null,
    field_validation: /No field validation yet/.test(accMd) ? "pending" : null,
  },
};
writeFileSync(join(OUT, "facts.json"), JSON.stringify(facts, null, 1));
log.push("facts.json");
writeFileSync(join(OUT, "manifest.json"), JSON.stringify({ files: log.map((x) => x.split(" ")[0]) }, null, 1));
console.log(`sync-film-data: ${log.join(", ")}`);
