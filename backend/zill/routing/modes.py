"""Mode constants for routing (PRD 8.1). Values come from config; this is the routing-side view."""

from __future__ import annotations

from zill import config

MODES = ("walk", "cycle", "scooter", "run")  # run = the walk graph at running pace
SPEEDS = config.SPEEDS
CROSSING_WAIT_S = config.CROSSING_WAIT_S
STAIRS_WALK_FACTOR = config.STAIRS_WALK_FACTOR
SUN_WEIGHT = config.SUN_WEIGHT
COMFORT = config.COMFORT
CROWD = config.CROWD
LAMBDAS = config.LAMBDAS

# cls codes used in numpy arrays
CLS_OPEN, CLS_COVERED, CLS_INDOOR, CLS_AC = 0, 1, 2, 3
CLS_CODES = {"open": CLS_OPEN, "covered": CLS_COVERED, "indoor": CLS_INDOOR, "ac_link": CLS_AC}
CLS_NAMES = {v: k for k, v in CLS_CODES.items()}


def check_mode(mode: str) -> str:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; expected one of {MODES}")
    return mode
