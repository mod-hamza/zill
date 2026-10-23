"""Build ``data/cities/<city>/places.json`` from the (cached) Overpass named-feature dump.

One element list (every ``nwr["name"]`` in the scene bbox, the same query the POI bake uses, so it is a
cache hit after a bake) is classified, de-duplicated, projected and snapped to the walk graph with the
bake's own door-aware ``snap_pois``. Streets are merged by name into one place.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from zill import config
from zill.data.cities import CitySpec, get_city_spec
from zill.data.pois import _dist_m, _pos, slug
from zill.geo import to_local
from zill.places.fold import fold

MAX_SNAP_M = 150.0  # places further than this from any walk node are dropped (outside the graph)
DEDUPE_M = 60.0  # same folded name within this distance = one place
ALT_KEYS = (
    "name:en", "name:ar", "name:no", "name:nb", "name:nn", "alt_name", "official_name", "old_name",
    "short_name", "int_name", "brand", "alt_name:en", "alt_name:ar", "loc_name",
)  # fmt: skip
DROP_KEYS = ("boundary", "admin_level")
HIGHWAY_STREET = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "service",
    "living_street", "pedestrian", "footway", "path", "cycleway", "steps", "road", "secondary_link",
    "primary_link", "tertiary_link", "motorway_link", "trunk_link", "track",
}  # fmt: skip
AMENITY_FOOD = {"restaurant", "cafe", "fast_food", "bar", "pub", "food_court", "ice_cream", "biergarten"}

# ranking weight per kind (landmarks and stations above shops)
KIND_WEIGHT = {
    "station": 1.0, "landmark": 1.0, "mall": 0.95, "square": 0.9, "park": 0.9, "hotel": 0.85,
    "building": 0.8, "street": 0.8, "stop": 0.7, "amenity": 0.7, "food": 0.65, "shop": 0.6, "other": 0.5,
}  # fmt: skip


def classify(tags: dict[str, str], etype: str) -> str | None:
    """Map OSM tags to a place kind, or None when the feature should not be searchable."""
    t = tags
    if any(k in t for k in DROP_KEYS) or t.get("type") in ("route", "boundary"):
        return None
    if t.get("railway") in ("station", "halt", "tram_stop", "subway_entrance") or (
        t.get("public_transport") == "station"
    ):
        return "station"
    if t.get("tourism") in ("attraction", "museum", "gallery", "viewpoint", "theme_park", "zoo", "aquarium"):
        return "landmark"
    if t.get("historic") or t.get("man_made") in ("tower", "lighthouse", "obelisk", "bridge"):
        return "landmark"
    if t.get("amenity") in ("theatre", "arts_centre", "townhall", "library", "cinema", "place_of_worship"):
        return "landmark"
    if t.get("shop") == "mall" or (t.get("building") == "retail" and "mall" in fold(t.get("name", ""))):
        return "mall"
    if t.get("tourism") in ("hotel", "hostel", "guest_house", "apartment", "motel", "resort"):
        return "hotel"
    if t.get("place") in ("square", "neighbourhood", "suburb", "quarter", "locality", "city_block", "island"):
        return "square"
    if t.get("leisure") in ("park", "garden", "playground", "pitch", "stadium", "sports_centre", "marina"):
        return "park"
    if t.get("highway") in ("bus_stop", "platform") or t.get("public_transport") in (
        "platform",
        "stop_position",
    ):
        return "stop"
    if t.get("highway") in HIGHWAY_STREET and etype == "way":
        return "street"
    if t.get("highway") == "pedestrian" and etype == "relation":
        return "square"
    if t.get("amenity") in AMENITY_FOOD:
        return "food"
    if t.get("amenity"):
        return "amenity"
    if t.get("shop"):
        return "shop"
    if t.get("office") or t.get("tourism") or t.get("leisure") or t.get("landuse") == "retail":
        return "amenity"
    if t.get("building") and etype != "node":
        return "building"
    return None


def _alts(tags: dict[str, str], display: str) -> list[str]:
    seen = {fold(display)}
    out: list[str] = []
    for v in [tags.get("name", "")] + [tags.get(k, "") for k in ALT_KEYS]:
        for part in re.split(r"\s*;\s*", v):
            f = fold(part)
            if part and f and f not in seen:
                seen.add(f)
                out.append(part)
    return out


def _display(tags: dict[str, str]) -> str:
    """Primary name: English variant when mapped, else the local name."""
    return (tags.get("name:en") or tags.get("int_name") or tags.get("name", "")).strip()


def elements_to_places(
    elements: list[dict[str, Any]], origin: dict[str, float], bbox: dict[str, float]
) -> list[dict[str, Any]]:
    """Classify, merge streets, de-duplicate. Returns places with lat/lon/x/z but no graph node yet."""
    items: list[dict[str, Any]] = []
    streets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for el in elements:
        tags = el.get("tags") or {}
        if not tags.get("name"):
            continue
        kind = classify(tags, el["type"])
        pos = _pos(el)
        if kind is None or pos is None:
            continue
        lat, lon = pos
        if not (bbox["s"] <= lat <= bbox["n"] and bbox["w"] <= lon <= bbox["e"]):
            continue
        disp = _display(tags)
        if len(fold(disp)) < 2:
            continue
        rec = {
            "name": disp,
            "alt_names": _alts(tags, disp),
            "kind": kind,
            "lat": lat,
            "lon": lon,
            "osm": f"{el['type']}/{el['id']}",
        }
        if kind == "street":
            streets[fold(disp)].append(rec)
        else:
            items.append(rec)
    for recs in streets.values():  # one place per street: the segment centre nearest the mean centre
        mlat = sum(r["lat"] for r in recs) / len(recs)
        mlon = sum(r["lon"] for r in recs) / len(recs)
        merged = dict(min(recs, key=lambda r: _dist_m((mlat, mlon), (r["lat"], r["lon"]))))
        merged["alt_names"] = list({fold(a): a for r in recs for a in r["alt_names"]}.values())
        items.append(merged)
    # de-duplicate (same folded name, near each other): keep the heavier kind, then the first seen
    items.sort(key=lambda r: (-KIND_WEIGHT[r["kind"]], r["osm"]))
    kept: list[dict[str, Any]] = []
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in items:
        key = fold(r["name"])
        if any(_dist_m((r["lat"], r["lon"]), (k["lat"], k["lon"])) < DEDUPE_M for k in by_name[key]):
            continue
        by_name[key].append(r)
        kept.append(r)
    used: set[str] = set()
    for r in kept:
        typ, num = r["osm"].split("/")
        base = ("st_" if r["kind"] == "street" else "") + (slug(r["name"]) or "place")
        pid = base if r["kind"] == "street" and base not in used else f"{base}_{typ[0]}{num}"
        used.add(pid)
        r["id"] = pid
        x, z = to_local(r["lat"], r["lon"], origin)
        r["x"], r["z"] = round(float(x), 2), round(float(z), 2)
        r["lat"], r["lon"] = round(r["lat"], 7), round(r["lon"], 7)
    kept.sort(key=lambda r: (-KIND_WEIGHT[r["kind"]], r["name"].lower()))
    return kept


def _footprints(buildings: dict[str, Any]) -> dict[str, Any]:
    from shapely.geometry import Polygon

    out = {}
    for b in buildings.get("buildings", []):
        if b.get("osm") and len(b.get("footprint") or []) >= 3:
            try:
                poly = Polygon(b["footprint"])
                if poly.is_valid and not poly.is_empty:
                    out[b["osm"]] = poly
            except Exception:  # noqa: BLE001 - a bad ring only loses the door snap for that building
                continue
    return out


def build_places(city_id: str, spec: CitySpec | None = None, refresh: bool = False) -> dict[str, Any]:
    """Build and write ``places.json`` for a baked city. Needs graph.json + (cached) Overpass data."""
    from zill.data import overpass
    from zill.data.bake import snap_pois

    spec = spec or get_city_spec(city_id)
    cdir = config.DATA_DIR / "cities" / city_id
    graph = json.loads((cdir / "graph.json").read_text(encoding="utf-8"))
    bpath = cdir / "buildings.json"
    fps = _footprints(json.loads(bpath.read_text(encoding="utf-8"))) if bpath.exists() else {}
    els = overpass.fetch_pois(spec.bbox_scene, city_id, refresh=refresh)
    places = elements_to_places(els, spec.origin, spec.bbox_scene)
    n_before = len(places)
    snap_pois(places, graph, fps)
    places = [p for p in places if p["snap_m"] <= MAX_SNAP_M]
    from zill.places.index import apply_aliases, load_aliases

    apply_aliases(places, load_aliases(city_id))
    by_kind: dict[str, int] = defaultdict(int)
    for p in places:
        by_kind[p["kind"]] += 1
        p["alt_names"] = p["alt_names"][:8]
    keys = ("id", "name", "alt_names", "kind", "lat", "lon", "x", "z", "node", "snap_m", "osm")
    payload = {
        "city_id": city_id,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "OpenStreetMap via Overpass (cached raw dump)",
        "attribution": "© OpenStreetMap contributors",
        "count": len(places),
        "dropped_far_from_graph": n_before - len(places),
        "by_kind": dict(sorted(by_kind.items())),
        "places": [{k: p[k] for k in keys} for p in places],
    }
    out = cdir / "places.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return payload


def _main() -> None:  # python -m zill.places.build dubai_downtown [--refresh]
    import sys

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for cid in args or [config.DEFAULT_CITY]:
        out = build_places(cid, refresh="--refresh" in sys.argv)
        print(cid, out["count"], out["by_kind"], "dropped", out["dropped_far_from_graph"])


if __name__ == "__main__":
    _main()
