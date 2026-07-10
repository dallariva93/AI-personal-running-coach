"""Periodization: turn a goal race into a phased macrocycle (GAP 2 + 17).

A real coach doesn't decide week by week — it works backwards from the race
date through a sequence of phases:

    Base → Build → Specific → Peak → Taper → Race

Each phase has a target weekly volume (relative to the athlete's current
baseline) and an intensity focus. The final **taper** sheds volume progressively
so the athlete arrives fresh. All functions here are pure and deterministic.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

from app.processing.plan_enforcement import parse_week_structure
from app.schemas import (
    AthleteProfile,
    Goal,
    PeriodizationPlan,
    PhasePlan,
    PlanGenerateRequest,
    TrainingMetrics,
)

# Taper length (weeks) by race distance — longer races need a longer taper.
_TAPER_WEEKS = {"marathon": 3, "half": 2, "10k": 1, "5k": 1, "trail": 2}

# Share of the *preparation* weeks (everything before the taper) per phase.
_PREP_SHARES = {"base": 0.35, "build": 0.30, "specific": 0.20, "peak": 0.15}

# Weekly volume relative to baseline, and the focus, per phase.
_PHASE_PROFILE = {
    "base": (1.0, "Costruzione aerobica: tanti km facili in Z2, 80/20.", [
        "Lungo progressivo in Z2",
        "Fondo medio facile",
        "Allunghi/strides a fine seduta",
    ]),
    "build": (1.15, "Aumento del volume e introduzione della soglia.", [
        "Tempo run in Z3-Z4",
        "Lungo con tratti a ritmo medio",
        "Ripetute medie (1000-2000m)",
    ]),
    "specific": (1.2, "Lavoro al ritmo gara e resistenza specifica.", [
        "Lungo con porzioni a ritmo gara",
        "Ripetute al ritmo gara",
        "Tempo run lungo alla soglia",
    ]),
    "peak": (1.1, "Affinamento: meno volume, qualità alta vicino al ritmo gara.", [
        "Ripetute brevi veloci (VO2max)",
        "Lungo medio con finale veloce",
        "Simulazione parziale di gara",
    ]),
    "taper": (0.6, "Scarico progressivo: riduci il volume, mantieni un po' di ritmo.", [
        "Sedute brevi con qualche allungo a ritmo gara",
        "Volume ridotto, recupero",
    ]),
    "race": (0.3, "Settimana gara: riposo, attivazione leggera, gara.", [
        "Attivazione 20-30 min con 3-4 allunghi",
        "Riposo pre-gara",
    ]),
}

_PHASE_ORDER = ["base", "build", "specific", "peak", "taper", "race"]


def _parse(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _allocate_prep_weeks(prep_weeks: int) -> dict[str, int]:
    """Split the preparation weeks across base/build/specific/peak.

    Rounds each share and gives any remainder to ``base`` (the foundation).
    """
    if prep_weeks <= 0:
        return {k: 0 for k in _PREP_SHARES}
    alloc = {name: int(round(prep_weeks * share)) for name, share in _PREP_SHARES.items()}
    drift = prep_weeks - sum(alloc.values())
    alloc["base"] += drift  # absorb rounding error
    if alloc["base"] < 0:  # pathological tiny runways
        alloc["base"] = 0
    return alloc


def build_periodization(
    goal: Goal | None,
    baseline_km: float,
    ref: date | None = None,
) -> PeriodizationPlan | None:
    """Build the macrocycle from ``ref`` to the goal race, or None if N/A."""
    ref = ref or date.today()
    if goal is None:
        return None
    target = _parse(goal.target_date)
    if target is None or target < ref:
        return None

    days = (target - ref).days
    weeks_to_race = max(1, math.ceil((days + 1) / 7))

    taper_weeks = _TAPER_WEEKS.get(goal.goal_type, 2)
    # Always leave at least the race week; never let taper exceed the runway.
    race_weeks = 1
    taper_weeks = min(taper_weeks, max(0, weeks_to_race - race_weeks))
    prep_weeks = max(0, weeks_to_race - taper_weeks - race_weeks)
    alloc = _allocate_prep_weeks(prep_weeks)
    alloc["taper"] = taper_weeks
    alloc["race"] = race_weeks if weeks_to_race >= 1 else 0

    baseline = max(baseline_km, 0.0)
    phases: list[PhasePlan] = []
    cursor = _monday(ref)
    for name in _PHASE_ORDER:
        weeks = alloc.get(name, 0)
        if weeks <= 0:
            continue
        factor, focus, workouts = _PHASE_PROFILE[name]
        start = cursor
        end = cursor + timedelta(days=weeks * 7 - 1)
        phases.append(
            PhasePlan(
                name=name,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                weeks=weeks,
                volume_factor=factor,
                intensity_focus=focus,
                key_workouts=workouts,
            )
        )
        cursor = end + timedelta(days=1)

    current = current_phase(phases, ref) or (phases[0].name if phases else "base")
    return PeriodizationPlan(
        goal_type=goal.goal_type,
        target_date=target.isoformat(),
        weeks_to_race=weeks_to_race,
        baseline_km=round(baseline, 1),
        current_phase=current,
        phases=phases,
    )


def current_phase(phases: list[PhasePlan], ref: date | None = None) -> str | None:
    """Return the name of the phase containing ``ref`` (default today)."""
    ref = ref or date.today()
    for p in phases:
        start, end = _parse(p.start_date), _parse(p.end_date)
        if start and end and start <= ref <= end:
            return p.name
    return None


def phase_for(plan: PeriodizationPlan | None, ref: date | None = None) -> PhasePlan | None:
    """Return the full :class:`PhasePlan` active at ``ref``."""
    if plan is None:
        return None
    name = current_phase(plan.phases, ref) or plan.current_phase
    for p in plan.phases:
        if p.name == name:
            return p
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Plan Spec engine (Fase A — plan architecture review)
#
# ``build_plan_spec`` turns the chat context (§CTX§), the athlete's metrics and
# the goal into a complete, week-by-week Plan Spec. It replaces the weak offline
# templates the fallback used to emit: deterministic, testable, with volumes that
# add up, a smooth week-over-week progression, deloads tied to how aggressively
# the load is ramping, and the chat-agreed weekly skeleton honoured verbatim.
#
# Everything below is pure: given the same inputs (and a fixed ``ref``) it always
# produces the same plan. No I/O, no network, no clock beyond the injected ``ref``.
# ══════════════════════════════════════════════════════════════════════════════

# Italian phase labels — kept identical to the previous offline output so the
# mobile timeline and existing tests stay compatible.
_SPEC_PREP_PHASES = ("Base", "Build", "Specifico", "Peak")
_SPEC_PREP_SHARES = {"Base": 0.35, "Build": 0.30, "Specifico": 0.20, "Peak": 0.15}
_SPEC_TAPER_WEEKS = {"marathon": 3, "half": 2, "10k": 1, "5k": 1, "trail": 2}

# Peak weekly volume as a multiple of the starting baseline — the ceiling the
# ramp is allowed to reach (a beginner shouldn't 3× their volume in 12 weeks).
_SPEC_PEAK_MULT = {"marathon": 1.6, "half": 1.45, "10k": 1.35, "5k": 1.30, "trail": 1.5}

# Absolute ceiling for the long run (km), whatever the weekly volume says.
_SPEC_LONG_CEIL = {"marathon": 32.0, "half": 22.0, "10k": 16.0, "5k": 12.0, "trail": 28.0}

# Quality (non-easy) session types offered per phase, in priority order.
_SPEC_QUALITY = {
    "Base": ["strides"],
    "Build": ["tempo"],
    "Specifico": ["intervals", "tempo"],
    "Peak": ["intervals", "tempo"],
    "Taper": ["strides"],
    "Gara": [],
}

# Default training-day patterns (0=Mon..6=Sun) by days-per-week.
_SPEC_DAY_PATTERNS = {
    3: (1, 3, 6),
    4: (1, 3, 5, 6),
    5: (0, 1, 3, 5, 6),
    6: (0, 1, 2, 4, 5, 6),
}

_SPEC_PACE_DEFAULTS = {
    "beginner": {
        "easy": "6:30/km", "long": "6:45/km", "tempo": "5:50/km", "intervals": "5:20/km",
    },
    "intermediate": {
        "easy": "5:30/km", "long": "5:45/km", "tempo": "4:45/km", "intervals": "4:15/km",
    },
    "advanced": {
        "easy": "5:00/km", "long": "5:10/km", "tempo": "4:15/km", "intervals": "3:50/km",
    },
}


def build_plan_spec(
    request: PlanGenerateRequest,
    profile: AthleteProfile | None = None,
    metrics: TrainingMetrics | None = None,
    ramp_pct: float | None = None,
    ref: date | None = None,
) -> dict:
    """Produce a complete multi-week Plan Spec from context + metrics + goal.

    Returns the same dict shape the offline templates used to (so the plan
    service and the enforcement pass are unchanged): ``{"weeks_total", "start_date",
    "weeks": [{"week_number", "phase", "target_km", "description", "sessions"}]}``.
    Each week always carries exactly 7 sessions (rest days included) with days
    0..6, and ``target_km`` equals the sum of the week's session distances — the
    header can never disagree with the sessions again.
    """
    today = ref or date.today()
    start_date = today - timedelta(days=today.weekday())  # Monday of current week

    weeks_total = _spec_weeks_total(request, today)
    phase_by_week, deload_by_week = _spec_timeline(
        request, weeks_total, metrics, ramp_pct
    )
    ctx = _spec_parse_ctx(request.runner_context)
    paces = _spec_paces(request, ctx)
    baseline = _spec_baseline(request, metrics, profile, ctx)
    volumes = _spec_volumes(
        phase_by_week, deload_by_week, baseline, request.goal_type, ramp_pct
    )
    agreed = {e["dow"]: e for e in parse_week_structure(request.runner_context)}

    weeks_out: list[dict] = []
    for i in range(weeks_total):
        phase = phase_by_week[i]
        is_deload = deload_by_week[i]
        assignments = _spec_assignments(phase, request, agreed, is_deload)
        long_frac = _spec_long_fraction(phase, i, weeks_total)
        sessions = _spec_sessions(
            assignments, volumes[i], long_frac, request.goal_type, paces, agreed
        )
        actual_km = round(
            sum(s["target_distance_km"] or 0.0 for s in sessions), 1
        )
        weeks_out.append(
            {
                "week_number": i + 1,
                "phase": phase,
                "target_km": actual_km,
                "description": _spec_phase_description(phase, i + 1, is_deload),
                "sessions": sessions,
            }
        )

    return {
        "weeks_total": len(weeks_out),
        "start_date": start_date.isoformat(),
        "weeks": weeks_out,
    }


# ── Timeline & phases ────────────────────────────────────────────────────────

def _spec_weeks_total(request: PlanGenerateRequest, today: date) -> int:
    try:
        race_date = datetime.strptime(request.goal_date[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        race_date = today + timedelta(weeks=16)
    days_to_race = (race_date - today).days
    return max(4, min(24, (days_to_race + 6) // 7))


def _spec_timeline(
    request: PlanGenerateRequest,
    weeks_total: int,
    metrics: TrainingMetrics | None,
    ramp_pct: float | None,
) -> tuple[list[str], list[bool]]:
    """Return (phase per week, is-deload per week) across the whole runway."""
    taper = min(
        _SPEC_TAPER_WEEKS.get(request.goal_type, 2), max(0, weeks_total - 1)
    )
    race = 1
    prep = max(0, weeks_total - taper - race)

    base_w = max(1, round(prep * _SPEC_PREP_SHARES["Base"])) if prep else 0
    build_w = max(1, round(prep * _SPEC_PREP_SHARES["Build"])) if prep else 0
    specific_w = max(1, round(prep * _SPEC_PREP_SHARES["Specifico"])) if prep else 0
    peak_w = max(0, prep - base_w - build_w - specific_w)

    phases: list[str] = (
        ["Base"] * base_w
        + ["Build"] * build_w
        + ["Specifico"] * specific_w
        + ["Peak"] * peak_w
        + ["Taper"] * taper
        + ["Gara"] * race
    )
    # Guard against rounding drift on very short runways.
    phases = phases[:weeks_total]
    while len(phases) < weeks_total:
        phases.insert(0, "Base")

    cadence = _spec_deload_cadence(metrics, ramp_pct)
    deloads: list[bool] = []
    prep_seen = 0
    for i, phase in enumerate(phases):
        is_deload = False
        if phase in _SPEC_PREP_PHASES:
            prep_seen += 1
            # No deload on the very first week, nor on the last prep week
            # (the taper already unloads right after).
            last_prep = i + 1 >= len(phases) or phases[i + 1] not in _SPEC_PREP_PHASES
            is_deload = prep_seen % cadence == 0 and prep_seen > 1 and not last_prep
        deloads.append(is_deload)
    return phases, deloads


def _spec_deload_cadence(
    metrics: TrainingMetrics | None, ramp_pct: float | None
) -> int:
    """Weeks between deloads: tighter when the athlete is ramping aggressively."""
    aggressive = (ramp_pct is not None and ramp_pct >= 9.0) or (
        metrics is not None and metrics.acwr is not None and metrics.acwr >= 1.2
    )
    return 3 if aggressive else 4


# ── Volume progression ───────────────────────────────────────────────────────

def _spec_baseline(
    request: PlanGenerateRequest,
    metrics: TrainingMetrics | None,
    profile: AthleteProfile | None,
    ctx: dict,
) -> float:
    """Starting weekly volume (km). Chat-stated volume wins, then metrics."""
    weekly = ctx.get("weekly_km")
    if isinstance(weekly, int | float) and weekly > 0:
        return float(weekly)
    if metrics is not None:
        return max(metrics.chronic_load_km, metrics.acute_load_km, 20.0)
    return 30.0


def _spec_volumes(
    phase_by_week: list[str],
    deload_by_week: list[bool],
    baseline: float,
    goal_type: str,
    ramp_pct: float | None,
) -> list[float]:
    """Smooth week-over-week volume: ramp up through prep, unload in the taper.

    Non-deload prep weeks grow the running ``trend`` by a bounded weekly ramp,
    capped at ``baseline × peak-multiplier``. Deload weeks dip to 80 % of the
    trend *without* resetting it, so the progression resumes from where it was.
    """
    ramp = 1.0 + _spec_clamp(
        (ramp_pct / 100.0) if ramp_pct else 0.08, 0.03, 0.10
    )
    cap = baseline * _SPEC_PEAK_MULT.get(goal_type, 1.5)

    volumes: list[float] = []
    trend = baseline
    peak_vol = baseline
    prep_seen = 0
    taper_seen = 0
    taper_total = sum(1 for p in phase_by_week if p == "Taper")
    for phase, is_deload in zip(phase_by_week, deload_by_week, strict=True):
        if phase in _SPEC_PREP_PHASES:
            prep_seen += 1
            if prep_seen == 1:
                v = baseline
                trend = baseline
            elif is_deload:
                v = trend * 0.80  # dip, but keep the trend intact
            elif phase == "Peak":
                v = trend * 0.90  # peak trims volume, intensity carries the load
            else:
                trend = min(trend * ramp, cap)
                v = trend
            peak_vol = max(peak_vol, v)
            volumes.append(v)
        elif phase == "Taper":
            taper_seen += 1
            mult = _spec_taper_mult(taper_seen, taper_total)
            volumes.append(peak_vol * mult)
        else:  # Gara
            volumes.append(peak_vol * 0.28)
    return volumes


def _spec_taper_mult(index: int, total: int) -> float:
    """Progressive taper: first week ~65 %, final taper week ~45 % of peak."""
    if total <= 1:
        return 0.55
    schedules = {
        2: [0.65, 0.50],
        3: [0.70, 0.55, 0.45],
    }
    sched = schedules.get(total)
    if sched and index <= len(sched):
        return sched[index - 1]
    return max(0.45, 0.70 - 0.10 * (index - 1))


def _spec_long_fraction(phase: str, week_idx: int, weeks_total: int) -> float:
    """Share of weekly volume in the long run — grows through the build."""
    if phase == "Gara":
        return 0.0
    if phase == "Taper":
        return 0.30
    span = max(1, weeks_total - 1)
    return min(0.36, 0.28 + 0.08 * (week_idx / span))


# ── Weekly structure & sessions ──────────────────────────────────────────────

def _spec_assignments(
    phase: str,
    request: PlanGenerateRequest,
    agreed: dict[int, dict],
    is_deload: bool,
) -> dict[int, str]:
    """Map each of the 7 days to a session type.

    Starts from a sensible default week for the phase, then overlays the
    chat-agreed skeleton (``week_structure``) verbatim — the agreement is a
    contract, so any day the athlete pinned wins.
    """
    week = _spec_default_week(phase, request, is_deload)
    for dow, entry in agreed.items():
        if 0 <= dow <= 6:
            week[dow] = entry["type"]
    return week


def _spec_default_week(
    phase: str, request: PlanGenerateRequest, is_deload: bool
) -> dict[int, str]:
    dpw = max(3, min(6, request.days_per_week))
    long_day = request.long_run_day if 0 <= request.long_run_day <= 6 else 6
    week = {d: "rest" for d in range(7)}

    if phase == "Gara":
        pattern = sorted(set(_SPEC_DAY_PATTERNS[dpw]) | {long_day})
        for i, d in enumerate(pattern):
            if d == max(pattern):
                week[d] = "race"
            elif i == len(pattern) - 2:
                week[d] = "strides"
            else:
                week[d] = "easy"
        return week

    training = set(_SPEC_DAY_PATTERNS[dpw])
    training.add(long_day)
    while len(training) > dpw:
        removable = sorted(training - {long_day})
        training.discard(removable[0])

    quality = [] if is_deload else list(_SPEC_QUALITY.get(phase, []))
    if phase != "Taper":
        week[long_day] = "long"
    q_idx = 0
    for d in sorted(training):
        if d == long_day and phase != "Taper":
            continue
        if q_idx < len(quality):
            week[d] = quality[q_idx]
            q_idx += 1
        else:
            week[d] = "easy"
    return week


def _spec_sessions(
    assignments: dict[int, str],
    target_km: float,
    long_frac: float,
    goal_type: str,
    paces: dict[str, str],
    agreed: dict[int, dict],
) -> list[dict]:
    """Distribute ``target_km`` across the week's sessions and render them.

    The distribution is built so the running sessions sum as close to the
    weekly target as the caps/floors allow; the residual is absorbed by the
    easy days (or the long run) so nothing is silently dropped.
    """
    by_type: dict[str, list[int]] = {}
    for dow, stype in assignments.items():
        by_type.setdefault(stype, []).append(dow)

    dist: dict[int, float] = {}
    remaining = target_km

    for dow in by_type.get("long", []):
        lk = min(target_km * long_frac, _SPEC_LONG_CEIL.get(goal_type, 30.0))
        lk = max(lk, 8.0)
        dist[dow] = lk
        remaining -= lk
    for dow in by_type.get("tempo", []):
        tk = _spec_clamp(0.22 * target_km, 6.0, 16.0)
        dist[dow] = tk
        remaining -= tk
    for dow in by_type.get("intervals", []):
        ik = _spec_clamp(0.18 * target_km, 6.0, 12.0)
        dist[dow] = ik
        remaining -= ik
    for dow in by_type.get("strides", []):
        sk = max(4.0, 0.12 * target_km)
        dist[dow] = sk
        remaining -= sk

    easy_days = by_type.get("easy", [])
    if easy_days:
        per = max(4.0, remaining / len(easy_days))
        for dow in easy_days:
            dist[dow] = per
    elif remaining > 0 and by_type.get("long"):
        # No easy days to soak up the remainder — give it to the long run.
        dist[by_type["long"][0]] += remaining

    # Chat-pinned distances override the computed ones.
    for dow, entry in agreed.items():
        km = entry.get("distance_km")
        if km and dow in dist:
            dist[dow] = float(km)

    sessions: list[dict] = []
    for dow in range(7):
        stype = assignments.get(dow, "rest")
        sessions.append(
            _spec_render(stype, dow, round(dist.get(dow, 0.0), 1), paces, goal_type)
        )
    return sessions


def _spec_render(
    stype: str, dow: int, km: float, paces: dict[str, str], goal_type: str
) -> dict:
    """Render one session dict (matches the offline template shape)."""
    ep, lp = paces["easy"], paces["long"]
    tp, ip = paces["tempo"], paces["intervals"]

    if stype == "easy":
        return _spec_dict(
            dow, "easy", "Corsa facile",
            f"Corsa facile in Z2 a {ep}. Ritmo di conversazione.",
            km, ep, round(km * _spec_pace_min(ep) + 0.5),
        )
    if stype == "long":
        return _spec_dict(
            dow, "long", "Lungo",
            f"Lungo in Z2 a {lp}. Parti piano, chiudi controllato.",
            km, lp, round(km * _spec_pace_min(lp) + 0.5),
        )
    if stype == "tempo":
        warm, cool = 2.0, 2.0
        quality = max(3.0, round(km - warm - cool, 1))
        return _spec_dict(
            dow, "tempo", "Corsa a soglia",
            f"Riscaldamento {warm:.0f} km + {quality:.0f} km @ {tp} (Z3-Z4) + "
            f"defaticamento {cool:.0f} km.",
            round(warm + quality + cool, 1), tp,
            round(warm * _spec_pace_min(ep) + quality * _spec_pace_min(tp)
                  + cool * _spec_pace_min(ep) + 0.5),
        )
    if stype == "intervals":
        reps = 5 if goal_type in ("marathon", "half") else 6
        rep_dist = 1.0 if goal_type in ("10k", "5k") else 1.5
        rec = 3 if goal_type in ("marathon", "half") else 2
        warm, cool = 2.5, 2.0
        quality = reps * rep_dist
        return _spec_dict(
            dow, "intervals", "Ripetute",
            f"Riscaldamento {warm:.1f} km + {reps}×{rep_dist:.0f} km @ {ip} "
            f"con {rec} min recupero + defaticamento {cool:.0f} km.",
            round(warm + quality + cool, 1), ip,
            round(warm * _spec_pace_min(ep) + quality * _spec_pace_min(ip)
                  + reps * rec + cool * _spec_pace_min(ep) + 0.5),
        )
    if stype == "strides":
        return _spec_dict(
            dow, "strides", "Corsa con allunghi",
            f"{km:.0f} km facili a {ep} + 4-6 allunghi da 100 m con recupero.",
            km, ep, round(km * _spec_pace_min(ep) + 12 + 0.5),
        )
    if stype == "race":
        return _spec_dict(
            dow, "race", "GARA",
            "Giorno di gara. Attivazione 15 min + 3 allunghi, poi gareggia!",
            None, None, None,
        )
    if stype == "cross":
        return _spec_dict(
            dow, "cross", "Cross training",
            "Bici, nuoto o palestra leggera. Recupero attivo, senza impatto.",
            None, None, 45.0,
        )
    return _spec_dict(
        dow, "rest", "Riposo",
        "Recupero completo. Stretching leggero se desiderato.",
        None, None, None,
    )


def _spec_dict(dow, stype, title, desc, km, pace, dur) -> dict:
    return {
        "day_of_week": dow,
        "session_type": stype,
        "title": title,
        "description": desc,
        "target_distance_km": km,
        "target_pace": pace,
        "target_duration_min": dur,
    }


def _spec_phase_description(phase: str, week_num: int, is_deload: bool) -> str:
    base = {
        "Base": "Costruzione aerobica: volume progressivo in Z2, 80/20.",
        "Build": "Sviluppo del volume e introduzione della soglia.",
        "Specifico": "Lavoro specifico: ripetute e lungo con tratti a ritmo gara.",
        "Peak": "Affinamento: meno volume, qualità vicino al ritmo gara.",
        "Taper": "Scarico progressivo: mantieni l'intensità, riduci il volume.",
        "Gara": "Settimana gara: riposo, attivazione leggera, gareggia!",
    }.get(phase, "")
    if is_deload:
        base = f"Settimana di scarico (-20%). {base}"
    return f"Settimana {week_num}: {base}"


# ── Context, paces, small helpers ────────────────────────────────────────────

def _spec_parse_ctx(runner_context: str | None) -> dict:
    if not runner_context:
        return {}
    import json

    try:
        ctx = json.loads(runner_context)
    except (ValueError, TypeError):
        return {}
    return ctx if isinstance(ctx, dict) else {}


def _spec_paces(request: PlanGenerateRequest, ctx: dict) -> dict[str, str]:
    """Resolve pace targets, preferring the values agreed in chat."""
    paces = dict(
        _SPEC_PACE_DEFAULTS.get(request.level, _SPEC_PACE_DEFAULTS["intermediate"])
    )
    easy = _spec_norm_pace(ctx.get("easy_pace"))
    if easy:
        paces["easy"] = easy
        paces["long"] = _spec_shift(easy, 15)  # long ~15 s/km slower than easy
    threshold = _spec_norm_pace(ctx.get("threshold_pace"))
    if threshold:
        paces["tempo"] = threshold
        paces["intervals"] = _spec_shift(threshold, -25)  # reps faster than LT
    return paces


def _spec_norm_pace(value) -> str | None:
    if not isinstance(value, str):
        return None
    v = value.strip()
    if not v:
        return None
    return v if "/km" in v else f"{v}/km"


def _spec_pace_min(pace: str) -> float:
    try:
        mmss = pace.replace("/km", "").strip()
        m, s = mmss.split(":")
        return int(m) + int(s) / 60.0
    except (ValueError, AttributeError):
        return 5.5


def _spec_shift(pace: str, seconds: int) -> str:
    total = int(round(_spec_pace_min(pace) * 60)) + seconds
    total = max(total, 150)  # never faster than 2:30/km (sanity floor)
    return f"{total // 60}:{total % 60:02d}/km"


def _spec_clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
