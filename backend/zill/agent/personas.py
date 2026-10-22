"""Personas: tourist / rider / crew (PRD 11.7)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    id: str
    label: str
    default_mode: str
    tone: str  # narrator guidance
    policy_pack: str | None
    guidance: str  # planner guidance


PERSONAS: dict[str, Persona] = {
    "tourist": Persona(
        id="tourist",
        label="Tourist",
        default_mode="walk",
        tone="Warm, simple and reassuring. Short sentences. Plain words, no jargon.",
        policy_pack=None,
        guidance=(
            "The user is a visitor on foot who may tire in heat. Prefer shaded, covered and air-conditioned "
            "links in peak heat when the added time is within a quarter of the fastest walk. Mention where "
            "a cool stop is nearby when it helps."
        ),
    ),
    "rider": Persona(
        id="rider",
        label="Delivery rider",
        default_mode="cycle",
        tone="Terse and tactical. Lead with the call, then one line of evidence. No pleasantries.",
        policy_pack=None,
        guidance=(
            "The user rides a bike or scooter on deliveries. Time matters; only trade time for shade when "
            "the added time is small. Stairs are forbidden. Wind and unmapped awnings are not modelled."
        ),
    ),
    "crew": Persona(
        id="crew",
        label="Outdoor crew lead",
        default_mode="walk",
        tone="Operational and compliance-aware. State the schedule, the constraint, the conflict, the fix.",
        policy_pack="UAE_OUTDOOR_WORK",
        guidance=(
            "The user leads an outdoor crew. Always run check_policy with UAE_OUTDOOR_WORK on the plan. "
            "If a movement or work block falls in the midday window, propose a compliant time instead. "
            "Never present the policy pack as legal advice; it is marked unverified."
        ),
    ),
}


def get_persona(pid: str) -> Persona:
    return PERSONAS.get(pid, PERSONAS["tourist"])
