"""Single source of truth for Zill constants (PRD Appendix B + CONTRACTS).

Mirrored to the frontend via GET /api/config (see `public_config`).
Other streams may append constants in clearly marked blocks at the bottom:
    # --- appended by <stream> ---
Never edit another stream's lines.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# --- paths (repo root = parents of backend/zill) ---------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
CITIES_DIR = DATA_DIR / "cities"
REPLAY_DIR = REPO_ROOT / "backend" / "replay"

load_dotenv(REPO_ROOT / ".env")

# --- geography ---------------------------------------------------------------------------------
ORIGIN_LAT = 25.1972
ORIGIN_LON = 55.2744
CORE_BBOX = {"s": 25.1850, "w": 55.2600, "n": 25.2100, "e": 55.2900}
CASTER_BUFFER_M = 900
SCENE_MARGIN_M = 100
DEFAULT_CITY = os.environ.get("ZILL_DEFAULT_CITY", "dubai_downtown")
TIMEZONE = os.environ.get("ZILL_TZ", "Asia/Dubai")

# --- dates ---------------------------------------------------------------------------------------
PRESET_DATES = {
    "winter": "2026-01-15",
    "spring": "2026-04-15",
    "summer": "2026-07-15",
    "hackathon": "2026-10-24",
}

# --- shade engine --------------------------------------------------------------------------------
GRID_RES_M = 2.0
TIME_STEP_MIN = 10
MAX_SHADOW_M = 1500
PED_H = 1.5
H0 = PED_H
SUN_MIN_ALT_DEG = 2.0
SUN_DISC_DEG = 0.53
EXPOSURE_SAMPLE_M = 3.0

# --- trees ---------------------------------------------------------------------------------------
TREE_RADIUS_M = 3.0
TREE_HEIGHT_M = 7.0
TREE_BLOCK = 0.65  # transmissivity 0.35
TREE_ROW_SPACING_M = 6.0

# --- routing -------------------------------------------------------------------------------------
SPEEDS = {"walk": 1.4, "cycle": 4.5, "scooter": 5.0}  # m/s
CROSSING_WAIT_S = {"walk": 8.0, "cycle": 10.0, "scooter": 10.0}
STAIRS_WALK_FACTOR = 0.5
SUN_WEIGHT = {"walk": 1.0, "scooter": 0.85, "cycle": 0.8}
COMFORT = {"indoor": 0.1, "ac_link": 0.1, "covered": 0.5, "open": 1.0}
CROWD = {"indoor": 1.15, "ac_link": 1.15}
RHL_SUN = 1.0
RHL_SHADE = 0.35
RHL_INDOOR = 0.1
LAMBDAS = {"fastest": 0, "balanced": 1.0, "coolest": 3.0}
DEPARTURE_STEP_MIN = 5
DEPARTURE_MU = 0.25

# --- agent ---------------------------------------------------------------------------------------
MAX_TOOL_CALLS = 12
TOOL_TIMEOUT_S = 8

# --- film ----------------------------------------------------------------------------------------
FILM_DURATION_S = 780

# --- env-driven LLM settings (key never leaves the backend) ------------------------------------
LLM_BASE_URL = os.environ.get("ZILL_LLM_BASE_URL", "https://www.vokeapi.com/v1")
LLM_API_KEY = (
    os.environ.get("ZILL_LLM_API_KEY")
    or os.environ.get("OPENAI_API_KEY")
    or os.environ.get("ANTHROPIC_API_KEY")
    or ""
)
MODEL = os.environ.get("ZILL_MODEL", "claude-sonnet-5-5")
MODEL_FAST = os.environ.get("ZILL_MODEL_FAST", "claude-haiku-5-5")
REPLAY = os.environ.get("ZILL_REPLAY", "0").strip().lower() in ("1", "true", "yes", "on")
OVERPASS_URLS = [
    u.strip()
    for u in os.environ.get(
        "OVERPASS_URLS",
        "https://overpass-api.de/api/interpreter,https://overpass.kumi.systems/api/interpreter",
    ).split(",")
    if u.strip()
]


def public_config() -> dict[str, Any]:
    """Frontend-safe subset of the configuration. Never includes the API key."""
    return {
        "origin": {"lat": ORIGIN_LAT, "lon": ORIGIN_LON},
        "core_bbox": CORE_BBOX,
        "caster_buffer_m": CASTER_BUFFER_M,
        "scene_margin_m": SCENE_MARGIN_M,
        "default_city": DEFAULT_CITY,
        "timezone": TIMEZONE,
        "preset_dates": PRESET_DATES,
        "grid_res_m": GRID_RES_M,
        "time_step_min": TIME_STEP_MIN,
        "max_shadow_m": MAX_SHADOW_M,
        "ped_h": PED_H,
        "sun_min_alt_deg": SUN_MIN_ALT_DEG,
        "exposure_sample_m": EXPOSURE_SAMPLE_M,
        "speeds": SPEEDS,
        "crossing_wait_s": CROSSING_WAIT_S,
        "stairs_walk_factor": STAIRS_WALK_FACTOR,
        "sun_weight": SUN_WEIGHT,
        "comfort": COMFORT,
        "crowd": CROWD,
        "rhl": {"sun": RHL_SUN, "shade": RHL_SHADE, "indoor": RHL_INDOOR},
        "lambdas": LAMBDAS,
        "departure_step_min": DEPARTURE_STEP_MIN,
        "departure_mu": DEPARTURE_MU,
        "tree": {"radius_m": TREE_RADIUS_M, "height_m": TREE_HEIGHT_M, "block": TREE_BLOCK},
        "max_tool_calls": MAX_TOOL_CALLS,
        "film_duration_s": FILM_DURATION_S,
        "replay": REPLAY,
    }


# --- appended by <stream> --- (append below; keep blocks small and named)
