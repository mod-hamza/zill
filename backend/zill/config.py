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
def _env_list(name: str, default: str) -> list[str]:
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


# Providers in priority order. Per provider: ZILL_<NAME>_API_KEY / _BASE_URL / _MODEL / _MODEL_FAST.
LLM_PROVIDERS = _env_list("ZILL_LLM_PROVIDERS", "opencode,voke")
# Voke (OpenAI-compatible). The legacy ZILL_LLM_* / ZILL_MODEL* names keep working as provider "voke".
VOKE_BASE_URL = os.environ.get("ZILL_VOKE_BASE_URL") or os.environ.get(
    "ZILL_LLM_BASE_URL", "https://www.vokeapi.com/v1"
)
VOKE_API_KEY = (
    os.environ.get("ZILL_VOKE_API_KEY")
    or os.environ.get("ZILL_LLM_API_KEY")
    or os.environ.get("OPENAI_API_KEY")
    or os.environ.get("ANTHROPIC_API_KEY")
    or ""
)
VOKE_MODEL = os.environ.get("ZILL_VOKE_MODEL") or os.environ.get("ZILL_MODEL", "claude-sonnet-5-5")
VOKE_MODEL_FAST = os.environ.get("ZILL_VOKE_MODEL_FAST") or os.environ.get(
    "ZILL_MODEL_FAST", "claude-haiku-5-5"
)
# OpenCode Go (OpenAI Chat Completions). Docs: https://opencode.ai/docs/go/
OPENCODE_BASE_URL = os.environ.get("ZILL_OPENCODE_BASE_URL", "https://opencode.ai/inference/go/openai/v1")
OPENCODE_MODELS_URL = os.environ.get("ZILL_OPENCODE_MODELS_URL", "https://opencode.ai/inference/go/v1/models")
OPENCODE_API_KEY = os.environ.get("ZILL_OPENCODE_API_KEY", "")
OPENCODE_MODEL = os.environ.get("ZILL_OPENCODE_MODEL", "kimi-k3")
OPENCODE_MODEL_FAST = os.environ.get("ZILL_OPENCODE_MODEL_FAST", "glm-5.3-flash")
OPENCODE_FALLBACK_MODELS = _env_list("ZILL_OPENCODE_FALLBACK_MODELS", "kimi-k3.1-pro,glm-5.3,glm-5.3-flash")
# Backward-compatible aliases: the legacy single-provider names (Voke) plus "any provider has a key".
LLM_BASE_URL = VOKE_BASE_URL
LLM_API_KEY = VOKE_API_KEY or OPENCODE_API_KEY
MODEL = VOKE_MODEL
MODEL_FAST = VOKE_MODEL_FAST
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

# --- appended by agent stream ---
RHL_BREAK_THRESHOLD = 1200.0  # rolling-30-min RHL (full-sun-seconds) above which plan_day inserts a cool-down
COOL_BREAK_MIN = 10.0
AUTO_APPLY_MAX_DELTA_ARRIVAL_MIN = 10.0  # PRD 11.5 L3
AUTO_APPLY_MAX_RHL_INCREASE_PCT = 10.0  # PRD 11.5 L3
MAX_FIX_ROUNDS = 2

# --- appended by routing/api stream ---
# Multi-stop planner (PRD 8.5): a cool-down break is inserted when the Relative Heat Load accumulated
# over any rolling RHL_BREAK_WINDOW_MIN minutes exceeds RHL_BREAK_THRESHOLD (1800 = 30 min fully in sun).
RHL_BREAK_THRESHOLD = 1200.0
RHL_BREAK_WINDOW_MIN = 30
COOLDOWN_BREAK_MIN = 10
PLAN_MAX_PERMUTE_STOPS = 6
GAZETTEER_ONLINE = os.environ.get("ZILL_NOMINATIM", "1").strip().lower() not in ("0", "false", "no", "off")

# --- appended by overnight Stream A (sun mode / well-being) ---
PREFERENCES = ("shade", "sun")  # shade = least direct sun (default); sun = most direct sun / daylight
DAYLIGHT_MIN_ALT_DEG = 45.0  # shadow-rule heuristic: your shadow is no longer than you are
DAYLIGHT_MIN_UV = 3.0  # WHO "moderate" band starts at 3
OVERCAST_CLOUD_PCT = 70.0  # cloud cover at/above which a sunny route has little direct sun
WELLBEING_BREAK_SUN_MIN = 10.0  # hydration / shade-break prompt every N minutes of direct sun (when hot)
WELLBEING_HOT_APPARENT_C = 32.2  # NWS heat-index "extreme caution" lower bound (90 F), indicative
CLEAR_SKY_INDEX_OVERCAST = 0.4  # measured / Haurwitz clear-sky radiation below this = overcast (Stream A)
CLEAR_SKY_MIN_GHI_WM2 = 50.0  # below this clear-sky irradiance (sun very low) the index is not judged
