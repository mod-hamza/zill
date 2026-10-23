#!/usr/bin/env python
"""Load test for the Zill API: ramps concurrent virtual users over a realistic read/route mix.

    python scripts/loadtest.py --base http://127.0.0.1:8010 --label "local machine" --levels 1,2,5,10,20,40 --secs 20
    python scripts/loadtest.py --base https://zill.itshamza.me --label "live VM" --levels 1,5,10,20 --secs 12

Only httpx + asyncio. The mix is read-only (no agent/LLM calls, no shade compute): city list, sun position,
hero-scenario routes with varied departures, the departure optimiser and health. Each virtual user loops
with a short think time. 429 responses are counted apart from real errors (the API rate-limits per IP; for a
local capacity run start the API with ZILL_RATE_LIMIT=0). Never point this at a host you do not own.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time
from collections import defaultdict
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
UA = "Zill-loadtest/0.1"
CITY = "dubai_downtown"
MIX = [("cities", 25), ("sun", 15), ("route", 35), ("departure", 15), ("health", 10)]  # weights


def load_scenarios() -> list[dict]:
    hero = json.loads((ROOT / "data" / "scenarios" / "hero.json").read_text(encoding="utf-8"))
    return hero["scenarios"]


def build_request(kind: str, scen: list[dict], rng: random.Random) -> tuple[str, str, dict | None]:
    s = rng.choice(scen)
    hh = rng.choice([10, 11, 12, 13, 14, 15, 16])
    mm = rng.choice([0, 15, 30, 45])
    body_base = {
        "city": CITY,
        "mode": s["mode"],
        "origin": {"lat": s["origin"]["lat"], "lon": s["origin"]["lon"]},
        "dest": {"lat": s["dest"]["lat"], "lon": s["dest"]["lon"]},
        "depart_at": f"{hh:02d}:{mm:02d}",
        "date_key": s["date_id"],
    }
    if kind == "cities":
        return "GET", "/api/cities", None
    if kind == "health":
        return "GET", "/api/health", None
    if kind == "sun":
        return "GET", f"/api/sun?city={CITY}&at=2026-07-15T{hh:02d}:{mm:02d}:00%2B04:00", None
    if kind == "route":
        return "POST", "/api/route", body_base
    if kind == "departure":
        return "POST", "/api/departure", body_base
    raise ValueError(kind)


def pct(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1)))))
    return xs[k]


async def vuser(client: httpx.AsyncClient, base: str, scen: list[dict], stop_at: float, seed: int, out: list) -> None:
    rng = random.Random(seed)
    kinds = [k for k, w in MIX for _ in range(w)]
    while time.perf_counter() < stop_at:
        kind = rng.choice(kinds)
        method, path, body = build_request(kind, scen, rng)
        t0 = time.perf_counter()
        status = 0
        try:
            r = await client.request(method, base + path, json=body, timeout=30.0)
            status = r.status_code
            await r.aread()
        except httpx.HTTPError:
            status = -1  # connect/read error or timeout
        out.append((kind, status, (time.perf_counter() - t0) * 1000.0))
        await asyncio.sleep(rng.uniform(0.2, 0.8))  # think time


async def run_level(base: str, n: int, secs: float, scen: list[dict]) -> dict:
    out: list[tuple[str, int, float]] = []
    limits = httpx.Limits(max_connections=n + 2, max_keepalive_connections=n + 2)
    async with httpx.AsyncClient(headers={"User-Agent": UA}, limits=limits, follow_redirects=False) as client:
        t0 = time.perf_counter()
        stop = t0 + secs
        await asyncio.gather(*(vuser(client, base, scen, stop, 1000 + i, out) for i in range(n)))
        wall = time.perf_counter() - t0
    ok = [o for o in out if 200 <= o[1] < 300]
    by_kind: dict[str, list[float]] = defaultdict(list)
    for k, st, ms in ok:
        by_kind[k].append(ms)
    return {
        "concurrency": n,
        "seconds": round(wall, 1),
        "requests": len(out),
        "ok": len(ok),
        "rate_limited_429": sum(1 for o in out if o[1] == 429),
        "errors": sum(1 for o in out if not (200 <= o[1] < 300) and o[1] != 429),
        "throughput_rps": round(len(out) / wall, 2),
        "p50_ms": round(pct([o[2] for o in ok], 50), 1),
        "p95_ms": round(pct([o[2] for o in ok], 95), 1),
        "max_ms": round(max((o[2] for o in ok), default=float("nan")), 1),
        "by_endpoint": {
            k: {"n": len(v), "p50_ms": round(statistics.median(v), 1), "p95_ms": round(pct(v, 95), 1)}
            for k, v in sorted(by_kind.items())
        },
    }


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:8010")
    ap.add_argument("--label", required=True, help='where this runs, e.g. "local machine" or "live VM"')
    ap.add_argument("--levels", default="1,2,5,10,20")
    ap.add_argument("--secs", type=float, default=20.0, help="seconds per concurrency level")
    ap.add_argument("--max-concurrency", type=int, default=200, help="safety cap")
    ap.add_argument("--out", default=None, help="write JSON results here")
    a = ap.parse_args()
    levels = [min(int(x), a.max_concurrency) for x in a.levels.split(",")]
    scen = load_scenarios()
    base = a.base.rstrip("/")
    print(f"# {a.label}: {base}  levels={levels}  {a.secs:.0f}s each  mix={dict(MIX)}")
    # warm-up so JIT / cold cache is not charged to level 1
    async with httpx.AsyncClient(headers={"User-Agent": UA}) as c:
        for _ in range(2):
            m, p, b = build_request("route", scen, random.Random(0))
            try:
                await c.request(m, base + p, json=b, timeout=60.0)
            except httpx.HTTPError as e:
                print("warm-up failed:", repr(e))
    results = []
    for n in levels:
        r = await run_level(base, n, a.secs, scen)
        results.append(r)
        print(
            f"c={n:<3} req={r['requests']:<5} rps={r['throughput_rps']:<7} p50={r['p50_ms']}ms "
            f"p95={r['p95_ms']}ms max={r['max_ms']}ms 429={r['rate_limited_429']} err={r['errors']}"
        )
        for k, v in r["by_endpoint"].items():
            print(f"    {k:<10} n={v['n']:<5} p50={v['p50_ms']}ms p95={v['p95_ms']}ms")
    payload = {"label": a.label, "base": base, "secs_per_level": a.secs, "mix": dict(MIX), "levels": results}
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print("wrote", a.out)


if __name__ == "__main__":
    asyncio.run(main())
