"""In-memory place index and ranked search (accent/case folded; prefix, token and fuzzy matching)."""

from __future__ import annotations

import json
import math
import re
import threading
from bisect import bisect_left
from collections import defaultdict
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process

from zill.places.build import KIND_WEIGHT
from zill.places.fold import fold

FUZZY_CUTOFF = 72.0
MAX_FUZZY_CANDIDATES = 60
CURATED_DEDUPE_M = 150.0
KINDS = tuple(KIND_WEIGHT)
_ARTICLE = re.compile(r"^(?:the|el|al) (?=\S)")
_PAREN = re.compile(r"\s*\(([^()]{2,40})\)\s*")
CURATED_BONUS = 1.05  # a curated place beats an equally exact-matching OSM stop/shop


def _dist_m(a: dict[str, Any], b: dict[str, Any]) -> float:
    dy = (a["lat"] - b["lat"]) * 110574.0
    dx = (a["lon"] - b["lon"]) * 111320.0 * math.cos(math.radians(a["lat"]))
    return math.hypot(dx, dy)


class PlaceIndex:
    def __init__(self, city_id: str, places: list[dict[str, Any]]) -> None:
        self.city_id = city_id
        self.places = places
        self.by_id: dict[str, dict[str, Any]] = {p["id"]: p for p in places}
        self._names: list[str] = []  # folded name variants (flat)
        self._owner: list[int] = []  # flat idx -> place idx
        self._raw: list[str] = []  # original-cased variant for display of the matched alias
        for i, p in enumerate(places):
            seen: set[str] = set()
            raws = [p["name"], *p.get("alt_names", [])]
            for m in _PAREN.finditer(p["name"]):  # "Oslo Central Station (Oslo S)": both parts are names
                raws += [m.group(1), _PAREN.sub(" ", p["name"]).strip()]
            for raw in raws:
                f = fold(raw)
                for v in (f, _ARTICLE.sub("", f)):  # "the dubai mall" is also findable as "dubai mall"
                    if len(v) >= 2 and v not in seen:
                        seen.add(v)
                        self._names.append(v)
                        self._owner.append(i)
                        self._raw.append(raw)
        self._exact: dict[str, list[int]] = defaultdict(list)
        for j, n in enumerate(self._names):
            self._exact[n].append(j)
        self._sorted = sorted(range(len(self._names)), key=self._names.__getitem__)
        self._sorted_names = [self._names[j] for j in self._sorted]
        self._tok: dict[str, set[int]] = defaultdict(set)
        for j, n in enumerate(self._names):
            for t in n.split():
                self._tok[t].add(j)
        self._tok_sorted = sorted(self._tok)

    def __len__(self) -> int:
        return len(self.places)

    # -- candidate generators -------------------------------------------------------------
    def _prefix_idx(self, q: str, limit: int = 400) -> list[int]:
        lo = bisect_left(self._sorted_names, q)
        out = []
        while lo < len(self._sorted_names) and self._sorted_names[lo].startswith(q) and len(out) < limit:
            out.append(self._sorted[lo])
            lo += 1
        return out

    def _token_prefix_idx(self, toks: list[str]) -> set[int]:
        """Variants where every query token is a prefix of some name token."""
        result: set[int] | None = None
        for t in toks:
            lo = bisect_left(self._tok_sorted, t)
            hit: set[int] = set()
            while lo < len(self._tok_sorted) and self._tok_sorted[lo].startswith(t):
                hit |= self._tok[self._tok_sorted[lo]]
                lo += 1
                if len(hit) > 3000:
                    break
            result = hit if result is None else result & hit
            if not result:
                return set()
        return result or set()

    # -- search ---------------------------------------------------------------------------
    def search(self, query: str, limit: int = 8, kinds: set[str] | None = None) -> list[dict[str, Any]]:
        q = fold(query)
        if not q or not self._names:
            return []
        qtoks = q.split()
        scores: dict[int, float] = {}  # flat idx -> base score

        def bump(j: int, s: float) -> None:
            if s > scores.get(j, 0.0):
                scores[j] = s

        for j in self._exact.get(q, ()):
            bump(j, 100.0)
        for j in self._prefix_idx(q):
            bump(j, 94.0 + 4.0 * len(q) / max(len(self._names[j]), 1))
        if len(q) >= 2:
            for j in self._token_prefix_idx(qtoks):
                n = self._names[j]
                bump(j, 84.0 + 8.0 * min(len(q) / max(len(n), 1), 1.0))
        if len(q) >= 3:
            for _n, sc, j in process.extract(
                q,
                self._names,
                scorer=fuzz.WRatio,
                limit=MAX_FUZZY_CANDIDATES,
                score_cutoff=FUZZY_CUTOFF,
            ):
                bump(j, min(float(sc), 88.0))  # fuzzy never outranks an exact/prefix hit
        best: dict[int, tuple[float, int]] = {}  # place idx -> (score, flat idx)
        for j, s in scores.items():
            i = self._owner[j]
            p = self.places[i]
            if kinds and p["kind"] not in kinds:
                continue
            adj = s * (0.8 + 0.2 * KIND_WEIGHT.get(p["kind"], 0.5))
            if p.get("curated"):
                adj *= CURATED_BONUS
            if i not in best or adj > best[i][0]:
                best[i] = (adj, j)
        ranked = sorted(best.items(), key=lambda kv: (-kv[1][0], len(self.places[kv[0]]["name"])))[:limit]
        out = []
        for i, (sc, j) in ranked:
            p = dict(self.places[i])
            p["score"] = round(sc, 1)
            p["source"] = "index"
            if self._raw[j] != p["name"]:
                p["matched"] = self._raw[j]
            out.append(p)
        return out


def _merge_curated(places: list[dict[str, Any]], pois: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Curated POIs (stable ids used by the app and the agent) replace same-named indexed places."""
    curated = []
    for p in pois:
        if p.get("node") is None:
            continue
        curated.append(
            {
                "id": p["id"],
                "name": p["name"],
                "alt_names": [p["osm_name"]] if p.get("osm_name") and p["osm_name"] != p["name"] else [],
                "kind": p.get("kind") if p.get("kind") in KIND_WEIGHT else "landmark",
                "lat": p["lat"],
                "lon": p["lon"],
                "x": p.get("x"),
                "z": p.get("z"),
                "node": p["node"],
                "snap_m": p.get("snap_m"),
                "osm": p.get("osm"),
                "curated": True,
            }
        )
    cf = {fold(c["name"]) for c in curated} | {fold(a) for c in curated for a in c["alt_names"]}
    kept = []
    for p in places:
        if fold(p["name"]) in cf and any(
            _dist_m(p, c) < CURATED_DEDUPE_M for c in curated if fold(c["name"]) == fold(p["name"])
        ):
            continue
        if p.get("osm") and any(p["osm"] == c["osm"] for c in curated):
            continue
        kept.append(p)
    return curated + kept


def apply_aliases(places: list[dict[str, Any]], aliases: dict[str, list[str]]) -> None:
    """Add curated aliases (``data/curated/<city>/aliases.json``: ``{place_id: [alias, ...]}``) in place."""
    for p in places:
        extra = aliases.get(p["id"])
        if extra:
            have = {fold(p["name"]), *(fold(a) for a in p.get("alt_names", []))}
            p["alt_names"] = [*p.get("alt_names", []), *(a for a in extra if fold(a) not in have)]


def load_aliases(city_id: str) -> dict[str, list[str]]:
    from zill import config

    f = config.DATA_DIR / "curated" / city_id / "aliases.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def load_places(cdir: Path) -> list[dict[str, Any]]:
    pf = cdir / "places.json"
    places = json.loads(pf.read_text(encoding="utf-8"))["places"] if pf.exists() else []
    pp = cdir / "pois.json"
    pois = json.loads(pp.read_text(encoding="utf-8")).get("pois", []) if pp.exists() else []
    merged = _merge_curated(places, pois)
    apply_aliases(merged, load_aliases(cdir.name))
    return merged


_LOCK = threading.Lock()
_CACHE: dict[tuple[str, str, int], PlaceIndex] = {}


def get_index(city_id: str) -> PlaceIndex:
    """Index for a baked city (cached per file mtime). Raises ``zill.services.CityNotFound`` if unknown."""
    from zill.services import CityNotFound, city_dir

    cdir = city_dir(city_id)
    if not (cdir / "meta.json").exists():
        raise CityNotFound(city_id)
    mt = 0
    for f in ("places.json", "pois.json"):
        if (cdir / f).exists():
            mt = max(mt, (cdir / f).stat().st_mtime_ns)
    key = (city_id, str(cdir), mt)
    with _LOCK:
        idx = _CACHE.get(key)
        if idx is None:
            for k in [k for k in _CACHE if k[:2] == key[:2]]:
                del _CACHE[k]
            idx = _CACHE[key] = PlaceIndex(city_id, load_places(cdir))
        return idx


def get_place(city_id: str, place_id: str) -> dict[str, Any] | None:
    """Place by id (used by ``CityContext.poi`` so /api/route accepts index ids)."""
    try:
        if place_id.startswith("online_"):
            from zill.places import online

            return online.recall(city_id, place_id)
        return get_index(city_id).by_id.get(place_id)
    except Exception:  # noqa: BLE001 - routing must never fail because the optional index is broken
        return None


def clear_cache() -> None:
    with _LOCK:
        _CACHE.clear()
