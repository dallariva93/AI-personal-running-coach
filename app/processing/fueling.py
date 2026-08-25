"""Fueling & hydration guidance for long runs and races (Fase F).

A coach tells the athlete *how to fuel* the sessions that need it — the long
run and the race — from duration and (when known) the heat. Short/easy sessions
need nothing. Pure and deterministic: session facts in, one guidance line out
(or ``None`` when fueling isn't warranted).

Sports-nutrition rules of thumb:
- under ~75 min: no in-run carbs needed;
- 75–150 min: 30–60 g carbs/hour;
- over 150 min: 60–90 g carbs/hour (train the gut for it);
- fluids ~400–800 ml/hour, raised in the heat.
"""

from __future__ import annotations

_FUELLED_TYPES = {"long", "race"}
_MIN_MINUTES = 75  # below this, no in-run fueling


def fueling_guidance(
    session_type: str | None,
    distance_km: float | None,
    duration_min: float | None,
    temp_c: float | None = None,
) -> str | None:
    """Return a fueling/hydration line for a long run or race, else ``None``."""
    stype = (session_type or "").lower()
    if stype not in _FUELLED_TYPES:
        return None

    minutes = _minutes(distance_km, duration_min)
    if minutes is None or minutes < _MIN_MINUTES:
        return None

    if minutes <= 150:
        carbs = "30-60 g di carboidrati/ora"
    else:
        carbs = "60-90 g di carboidrati/ora (allena l'intestino ad assorbirli)"

    fluid_low, fluid_high, heat = _fluids(temp_c)
    hours = minutes / 60.0
    guidance = (
        f"Rifornimento ({minutes:.0f}' ≈ {hours:.1f}h): {carbs}, "
        f"iniziando entro i primi 30-45 min. "
        f"Liquidi {fluid_low}-{fluid_high} ml/ora{heat}."
    )
    if stype == "race":
        guidance += " Prova la strategia nei lunghi, mai nulla di nuovo in gara."
    return guidance


def _minutes(distance_km: float | None, duration_min: float | None) -> float | None:
    if duration_min and duration_min > 0:
        return float(duration_min)
    if distance_km and distance_km > 0:
        return float(distance_km) * 6.0  # ~6 min/km fallback estimate
    return None


def _fluids(temp_c: float | None) -> tuple[int, int, str]:
    """Base fluid range (ml/h) with a heat bump and a note when it's hot."""
    if temp_c is None:
        return 400, 800, ""
    if temp_c >= 28:
        return 600, 1000, f" — caldo intenso ({temp_c:.0f}°C): bevi di più e usa elettroliti"
    if temp_c >= 22:
        return 500, 900, f" — clima caldo ({temp_c:.0f}°C): aumenta i liquidi"
    return 400, 800, ""
