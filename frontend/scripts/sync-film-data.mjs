// Copies the Film's non-API inputs VERBATIM into public/film-data/ (served statically, no network):
//   backend/replay/*.json      -> public/film-data/replays/   (the API has no replay-body endpoint)
//   data/test_results.json     -> public/film-data/test_results.json
//   data/validation/field_test.json (if it exists) -> public/film-data/field_test.json
//   docs/SPEAKER_NOTES.md      -> public/film-data/notes.json  ({ "<chapter number>": [points] })
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
writeFileSync(join(OUT, "manifest.json"), JSON.stringify({ files: log.map((x) => x.split(" ")[0]) }, null, 1));
console.log(`sync-film-data: ${log.join(", ")}`);
