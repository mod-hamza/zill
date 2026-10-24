"""Pydantic v2 request/response models for the Zill API (PRD 10; CONTRACTS 5-6)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Mode = Literal["walk", "cycle", "scooter", "run"]
Preference = Literal["shade", "sun"]
PREFERENCE_DESC = "shade = least direct sun (default); sun = most direct sun / daylight (well-being)"


class Loose(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


# ---- places ------------------------------------------------------------------------------------
class PlaceIn(BaseModel):
    """A place by coordinates, by gazetteer id, or by graph node id."""

    model_config = ConfigDict(extra="ignore")
    lat: float | None = None
    lon: float | None = None
    name: str | None = None
    poi: str | None = Field(default=None, description="gazetteer id, e.g. 'burj_khalifa'")
    node: int | None = None


class Place(Loose):
    name: str
    lat: float
    lon: float
    x: float
    z: float
    node: int
    snap_m: float = 0.0


# ---- cities / sun ------------------------------------------------------------------------------
class CityListItem(Loose):
    id: str
    name: str
    origin: dict[str, float] | None = None
    bbox: dict[str, float] | None = None
    counts: dict[str, Any] = {}
    status: Literal["ready", "partial", "incomplete"]
    shade_dates: list[str] = []


class SunResponse(BaseModel):
    city: str
    at: str
    alt_deg: float
    az_deg: float
    vector: list[float] = Field(description="unit vector toward the sun, local frame (x east, y up, z south)")
    is_night: bool
    sunrise: str
    sunset: str
    solar_noon: str


class BuildEvent(BaseModel):
    step: str
    label: str = ""
    count: int | None = None
    mode: Literal["cached", "live"] = "cached"
    t_ms: int = 0
    city: str = ""
    note: str | None = None
    extra: dict[str, Any] = {}


class ShadeComputeRequest(BaseModel):
    city: str = "dubai_downtown"
    date: str = Field(description="ISO date YYYY-MM-DD or a preset id", examples=["2026-03-03"])
    first_hhmm: str | None = Field(default=None, description="compute this step first, e.g. '1330'")


# ---- routing -----------------------------------------------------------------------------------
class RouteRequest(BaseModel):
    city: str = "dubai_downtown"
    mode: Mode = "walk"
    origin: str | PlaceIn
    dest: str | PlaceIn
    depart_at: str = Field(
        description="ISO-8601 with offset, or 'HH:MM' together with date_key",
        examples=["2026-07-15T13:30:00+04:00"],
    )
    date_key: str | None = Field(
        default=None, description="preset id or ISO date; defaults to depart_at's date"
    )
    lambdas: list[float] | None = Field(
        default=None, description="[fastest, balanced, coolest|sunniest]; default [0,1,3]"
    )
    include_segments: bool = True
    preference: Preference = Field(default="shade", description=PREFERENCE_DESC)


class RouteStats(Loose):
    """Sun mode adds `sun_gained_s` / `sun_gained_pct` (vs fastest) as extra keys."""

    distance_m: float
    duration_s: float
    sun_exposure_s: float
    shaded_pct: float
    covered_pct: float
    indoor_pct: float
    rhl: float
    added_time_s: float
    sun_saved_s: float
    sun_saved_pct: float
    rhl_saved_pct: float
    note: str | None = None


class Segment(Loose):
    edge: int
    geometry: list[list[float]]
    latlon: list[list[float]]
    arrival_s: float
    t_s: float
    sun: float
    cls: str
    name: str | None = None


class Route(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    lam: float = Field(alias="lambda")
    label: str
    mode: str
    depart: str
    stats: RouteStats
    nodes: list[int]
    edges: list[int]
    segments: list[Segment] = []


class RouteResponse(BaseModel):
    """Shade mode (default): fastest / balanced / coolest; `best` = coolest."""

    fastest: Route
    balanced: Route
    coolest: Route
    best: Route
    preference: Literal["shade"] = "shade"
    origin: Place
    dest: Place
    date_key: str
    wellbeing: dict[str, Any] | None = None
    timing_ms: float | None = None


class SunRouteResponse(BaseModel):
    """Sun mode: fastest / balanced / sunniest (no `coolest` key); `best` = sunniest."""

    fastest: Route
    balanced: Route
    sunniest: Route
    best: Route
    preference: Literal["sun"]
    origin: Place
    dest: Place
    date_key: str
    wellbeing: dict[str, Any] | None = None
    timing_ms: float | None = None


class DepartureWindow(BaseModel):
    start: str | None = Field(default=None, description="ISO or HH:MM; default = depart_at")
    end: str | None = Field(default=None, description="default = start + 90 min")


class DepartureRequest(BaseModel):
    city: str = "dubai_downtown"
    mode: Mode = "walk"
    origin: str | PlaceIn
    dest: str | PlaceIn
    depart_at: str | None = Field(default=None, description="the requested departure (window start)")
    window: DepartureWindow | None = None
    date_key: str | None = None
    step_min: int = Field(default=5, ge=1, le=30)
    latest_arrival: str | None = None
    mu: float = Field(default=0.25, ge=0)
    preference: Preference = Field(default="shade", description=PREFERENCE_DESC)


class DepartureRow(Loose):
    depart: str
    duration_s: float
    sun_exposure_s: float
    shaded_pct: float
    rhl: float
    wait_s: float
    arrive: str
    feasible: bool = True


class DepartureResponse(Loose):
    table: list[DepartureRow]
    recommended: dict[str, Any]
    requested: dict[str, Any]
    why: dict[str, Any]
    origin: Place
    dest: Place
    date_key: str
    preference: Preference = "shade"
    timing_ms: float | None = None


class PlanStop(BaseModel):
    place: str | PlaceIn
    dwell_min: float = 0
    window: list[str] | None = Field(default=None, description="[earliest, latest] HH:MM or ISO")
    fixed: bool = False


class PlanRequest(BaseModel):
    city: str = "dubai_downtown"
    mode: Mode = "walk"
    persona: Literal["tourist", "rider", "crew"] = "tourist"
    start: str | PlaceIn | None = None
    stops: list[PlanStop]
    start_at: str
    date_key: str | None = None
    reorder: bool = True
    return_to_start: bool = False
    policy_pack: str | None = None
    shift_window: list[str] | None = Field(default=None, description="crew: [earliest start, latest end]")
    preference: Preference = Field(default="shade", description=PREFERENCE_DESC)


class PlanResponse(Loose):
    plan_id: str
    order: list[int]
    legs: list[dict[str, Any]]
    breaks: list[dict[str, Any]]
    totals: dict[str, Any]
    items: list[dict[str, Any]] = []
    stops: list[dict[str, Any]] = []
    notes: list[str] = []
    policy: dict[str, Any] | None = None


# ---- weather / gazetteer / scenarios -----------------------------------------------------------
class WeatherResponse(Loose):
    city: str
    at: str
    source: Literal["live", "cached", "representative"]
    temperature_c: float | None
    apparent_c: float | None
    humidity_pct: float | None
    uv_index: float | None
    uv_basis: str
    wind_ms: float | None
    heat_alert: bool
    label: str
    hourly: list[dict[str, Any]] = []


class GazetteerHit(Loose):
    id: str
    name: str
    lat: float
    lon: float
    kind: str | None = None
    node: int | None = None
    score: float = 1.0
    source: str = "gazetteer"


class GazetteerResponse(BaseModel):
    query: str
    results: list[GazetteerHit]
    online_fallback: bool = False


class HealthResponse(Loose):
    ok: bool
    service: str
    version: str
    replay: bool
    llm: dict[str, Any]
    city: dict[str, Any] = {}
    shade: dict[str, Any] = {}
    replay_available: bool = False
