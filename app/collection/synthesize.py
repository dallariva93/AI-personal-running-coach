"""Turn a raw Garmin activity dict into a compact :class:`RunSummary`.

Garmin returns a large, second-by-second-capable payload. For the LLM (and for
storage) we keep only what is informative and cheap in tokens. All field access
is defensive because the unofficial API changes shape over time.
"""

from __future__ import annotations

import json as _json
from typing import Any

from app.logging_config import get_logger
from app.schemas import RunSummary

logger = get_logger("app.collection.synthesize")

# Keyword search on the activity name only. Used as the first signal because
# when the athlete renames their session ("Tempo Padova", "Ripetute 1000"),
# their intent overrides anything Garmin computed.
_NAME_HINTS = {
    "race": "gara",
    "gara": "gara",
    "interval": "intervalli",
    "ripetut": "intervalli",  # ripetuta, ripetute
    "repeat": "intervalli",
    "sprint": "intervalli",
    "speed": "intervalli",
    "tempo": "tempo",
    "threshold": "tempo",
    "soglia": "tempo",
    "medio": "medio",  # Italian: steady-state Z3 effort
    "steady": "medio",
    "long": "lungo",
    "lungo": "lungo",
    "recovery": "recupero",
    "recupero": "recupero",
    "easy": "easy",
}

# Map Garmin's primary training-effect label to our taxonomy.
#
# Note the split between Garmin's TEMPO and LACTATE_THRESHOLD: Garmin calls
# ``TEMPO`` a Z3-dominant sustained effort, which in Italian coaching is
# ``medio``. The pure threshold work (Z4 sustained, what English speakers
# call a "tempo run") is ``LACTATE_THRESHOLD`` for Garmin and ``tempo`` for us.
#
# VO2MAX maps to ``tempo`` (not ``intervalli``) on purpose: when a session
# carries the VO2MAX label but ``anaerobicTrainingEffect`` is low (< 2.5,
# caught one step earlier), it's a sustained supra-threshold effort
# (think 9 km all-out time trial), not a structured HIIT block. Real HIIT
# pushes anaerobic and is intercepted before this map.
_TE_LABEL_MAP = {
    "recovery": "recupero",
    "aerobic_base": "easy",
    "base": "easy",
    "tempo": "medio",
    "lactate_threshold": "tempo",
    "threshold": "tempo",
    "muscular_endurance": "tempo",
    "vo2max": "tempo",
    "anaerobic_capacity": "intervalli",
    "anaerobic": "intervalli",
    "sprint": "intervalli",
}

# Numeric thresholds on Garmin's 0-5 training-effect scores. Tuned on the
# observed payloads: a true interval session pushes anaerobic >= 2.5 (e.g.
# 8x400 in Z5), while a sustained tempo stays below.
_ANAEROBIC_INTERVAL_TE = 2.5
# When no label is present, an aerobic effect >= 3.5 indicates a substantial
# steady-state effort. We classify conservatively as ``medio`` rather than
# ``tempo``: without the label we cannot confirm the effort sat at threshold.
_AEROBIC_MEDIO_TE = 3.5

# Long-run threshold (km). The athlete picked 14 km as the cutoff: above this
# the session is classified as ``lungo`` regardless of intensity, because the
# defining trait of a long run is volume, not HR (HR drift on a hot day would
# otherwise mislabel it as VO2max/intervals).
_LUNGO_MIN_DISTANCE_KM = 14.0

# Trail threshold (m of vertical gain). Above this the session is classified
# as ``trail`` regardless of distance/intensity, because the elevation cost
# dominates the physiological signature.
_TRAIL_MIN_ELEVATION_M = 150.0

# Walking-pause detection: a single short pause at a traffic light does not
# qualify; sustained walk segments (>= 60 s total) flag an interval-with-walks
# structure.
_WALK_MIN_SECONDS = 60.0


def _num(value: Any) -> float | None:
    """Best-effort float parse (Garmin fields are inconsistently typed)."""
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def extract_start_time(raw: Any) -> str | None:
    """Pull a local ``HH:MM`` start time from a timestamp string (Q6).

    Handles both Garmin ``"2026-06-24 07:05:00"`` and Strava/ISO
    ``"2026-06-24T07:05:00Z"``. Returns None when there is no usable time part.
    """
    if not raw:
        return None
    text = str(raw)
    sep = "T" if "T" in text else " "
    parts = text.split(sep, 1)
    if len(parts) < 2:
        return None
    time_part = parts[1].strip()
    if len(time_part) < 5 or time_part[2] != ":":
        return None
    hhmm = time_part[:5]
    hh, mm = hhmm[:2], hhmm[3:5]
    if not (hh.isdigit() and mm.isdigit() and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
        return None
    return hhmm


def _format_pace(distance_m: float, duration_s: float) -> str | None:
    """Return average pace as ``M:SS/km`` from distance (m) and duration (s)."""
    if not distance_m or not duration_s:
        return None
    pace_s_per_km = duration_s / (distance_m / 1000.0)
    minutes = int(pace_s_per_km // 60)
    seconds = int(round(pace_s_per_km % 60))
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d}/km"


def _match_name_hint(activity_name: str) -> str | None:
    """Return the activity type implied by the user-set name, if any."""
    name = (activity_name or "").lower()
    if not name:
        return None
    for hint, label in _NAME_HINTS.items():
        if hint in name:
            return label
    return None


def _has_walking_pauses(activity: dict[str, Any]) -> bool:
    """True if Garmin's split summary shows non-trivial walk segments.

    Indicates an interval-with-walk-recovery structure: think 8x400m with a
    walking break between reps, which Garmin labels as LACTATE_THRESHOLD on
    average but is structurally an interval session.
    """
    splits = activity.get("splitSummaries")
    if not isinstance(splits, list):
        return False
    walk_seconds = 0.0
    for entry in splits:
        if not isinstance(entry, dict):
            continue
        split_type = str(entry.get("splitType", "")).upper()
        if "WALK" not in split_type:
            continue
        try:
            walk_seconds += float(entry.get("duration") or 0.0)
        except (TypeError, ValueError):
            continue
    return walk_seconds >= _WALK_MIN_SECONDS


def _classify_by_training_effect(activity: dict[str, Any]) -> str | None:
    """Classification driven by Garmin's training-effect signals.

    Combines the numeric anaerobic effect (most reliable signal for
    intervals) with the textual ``trainingEffectLabel`` enum. Returns
    ``None`` when no signal is strong enough to commit.
    """
    anaerobic = _num(activity.get("anaerobicTrainingEffect"))
    aerobic = _num(activity.get("aerobicTrainingEffect"))
    if anaerobic is not None and anaerobic >= _ANAEROBIC_INTERVAL_TE:
        return "intervalli"
    label = str(activity.get("trainingEffectLabel") or "").strip().lower()
    if label and label in _TE_LABEL_MAP:
        return _TE_LABEL_MAP[label]
    if aerobic is not None and aerobic >= _AEROBIC_MEDIO_TE:
        return "medio"
    return None


def _is_trail(activity: dict[str, Any]) -> bool:
    """True if the session is on trails or has significant elevation gain.

    Two signals, either is sufficient:

    * Garmin's ``activityType.typeKey == 'trail_running'`` (explicit).
    * ``elevationGain`` (m) >= ``_TRAIL_MIN_ELEVATION_M`` (athlete preference).
    """
    type_field = activity.get("activityType")
    if isinstance(type_field, dict):
        if "trail" in str(type_field.get("typeKey", "")).lower():
            return True
    elevation = _num(activity.get("elevationGain"))
    return elevation is not None and elevation >= _TRAIL_MIN_ELEVATION_M


def _infer_type(
    activity: dict[str, Any],
    hr_zones: dict[str, float] | None = None,  # kept for backward-compat
    duration_min: float = 0.0,  # kept for backward-compat
) -> str:
    """Classify the workout from Garmin metadata.

    Cascade, in priority order:

    1. Explicit keyword in the user-set ``activityName`` (athlete intent wins,
       including ``gara``/``race``).
    2. Trail terrain (Garmin ``trail_running`` type or ``elevationGain`` >=
       150 m) → ``trail``: the climbing cost dominates the session.
    3. Distance >= 14 km → ``lungo`` (volume defines the long run, not HR).
    4. Walking pauses in ``splitSummaries`` → ``intervalli`` (reps with walks).
    5. ``anaerobicTrainingEffect`` >= 2.5 → ``intervalli`` (true HIIT signature).
    6. Garmin ``trainingEffectLabel`` mapped via :data:`_TE_LABEL_MAP`
       (``TEMPO`` → ``medio``, ``LACTATE_THRESHOLD`` → ``tempo``, ...).
    7. ``aerobicTrainingEffect`` >= 3.5 → ``medio`` (no label, but clearly
       above easy; conservative choice without label confirmation).
    8. Default ``easy``.

    ``hr_zones`` and ``duration_min`` are accepted for backward compatibility
    with the previous signature but are no longer consulted: aggregated HR
    zones cannot reliably distinguish structure (intervals vs sustained
    tempo) and are biased by ambient conditions (heat, hills).
    """
    del hr_zones, duration_min  # intentionally unused

    name_hint = _match_name_hint(str(activity.get("activityName", "")))
    if name_hint is not None:
        return name_hint

    if _is_trail(activity):
        return "trail"

    distance_km = float(activity.get("distance") or 0.0) / 1000.0
    if distance_km >= _LUNGO_MIN_DISTANCE_KM:
        return "lungo"

    if _has_walking_pauses(activity):
        return "intervalli"

    te_hint = _classify_by_training_effect(activity)
    if te_hint is not None:
        return te_hint

    return "easy"


def extract_rpe_from_details(details: dict[str, Any]) -> int | None:
    """Pull the user-entered RPE (1-10) from the activity details payload.

    Garmin stores the value as ``summaryDTO.directWorkoutRpe`` on a 10-100
    scale (corresponding to RPE 1-10 on the watch). Returns ``None`` when
    the field is missing or zero (the user did not set it).
    """
    summary = details.get("summaryDTO") if isinstance(details, dict) else None
    if not isinstance(summary, dict):
        return None
    raw = summary.get("directWorkoutRpe")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    rpe = round(value / 10.0)
    return max(1, min(10, rpe))


def extract_details_enrichment(details: dict[str, Any]) -> dict[str, Any]:
    """Extract every useful field from the ``get_activity(id)`` payload.

    Returns a plain dict keyed by ``RunSummary`` field name; absent or
    invalid fields are skipped (no ``None`` entries) so the caller can
    update an existing record without overwriting good data with nulls.

    Extracts the full set of optional metrics (VO2max, training load, HR
    zones, intensity minutes, temperature, grade-adjusted pace, fastest
    splits, body battery, training effect, RPE and stamina). The detail
    payload nests most of these under ``summaryDTO``; we flatten that on top
    of the top-level dict so a single :func:`_rich_fields` pass sees both.
    """
    out: dict[str, Any] = {}
    if not isinstance(details, dict):
        return out

    summary = details.get("summaryDTO")
    merged: dict[str, Any] = dict(details)
    if isinstance(summary, dict):
        merged.update(summary)
    if not merged:
        return out

    out.update(_rich_fields(merged))

    rpe = extract_rpe_from_details(details)
    if rpe is not None:
        out["rpe"] = rpe

    if isinstance(summary, dict):
        drop = _stamina_drop(summary)
        if drop is not None:
            out["stamina_drop"] = drop

    return out


def extract_hr_zones_from_timezones(payload: Any) -> dict[str, float] | None:
    """Parse ``get_activity_hr_in_timezones`` into ``{"z1": minutes, ...}``.

    Garmin returns a list of ``{"zoneNumber": n, "secsInZone": s}`` dicts.
    """
    if not isinstance(payload, list):
        return None
    out: dict[str, float] = {}
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        zone = entry.get("zoneNumber")
        secs = _num(entry.get("secsInZone"))
        if zone is None or secs is None:
            continue
        try:
            out[f"z{int(zone)}"] = round(secs / 60.0, 1)
        except (TypeError, ValueError):
            continue
    return out or None


def extract_splits(payload: Any) -> list[str] | None:
    """Parse ``get_activity_splits`` into a list of per-km pace strings.

    Uses the ``lapDTOs`` array; each lap's distance/duration becomes a pace.
    Only whole-kilometre-ish laps are kept so the list reads as clean splits.
    """
    laps = payload.get("lapDTOs") if isinstance(payload, dict) else None
    if not isinstance(laps, list):
        return None
    out: list[str] = []
    for lap in laps:
        if not isinstance(lap, dict):
            continue
        distance = _num(lap.get("distance"))
        duration = _num(lap.get("duration") or lap.get("movingDuration"))
        if distance is None or distance < 300:  # skip tiny trailing laps
            continue
        pace = _format_pace(distance, duration or 0.0)
        if pace:
            out.append(pace)
    return out or None


def extract_altitude_profile(payload: Any) -> list[float] | None:
    """Extract average altitude per km from ``lapDTOs`` in the splits payload.

    Used as a fallback when the full GPS detail stream is unavailable. Returns
    one altitude value per usable lap (typically one per km).
    """
    laps = payload.get("lapDTOs") if isinstance(payload, dict) else None
    if not isinstance(laps, list):
        return None
    out: list[float] = []
    for lap in laps:
        if not isinstance(lap, dict):
            continue
        distance = _num(lap.get("distance"))
        if distance is None or distance < 300:
            continue
        alt = _num(lap.get("averageElevation") or lap.get("avgElevation") or lap.get("elevation"))
        if alt is not None:
            out.append(round(alt, 0))
    return out if len(out) >= 2 else None


def extract_gps_from_details(details: Any) -> dict[str, Any]:
    """Extract GPS route and elevation profile from ``get_activity_details`` payload.

    Garmin's ``get_activity_details`` endpoint returns two GPS representations:

    1. ``geoPolylineDTO.polyline`` — a pre-simplified list of lat/lon/altitude
       points (up to ``maxPolylineSize``, default 4000) that Garmin Connect
       itself uses for the map view.  This is the primary source.

    2. ``activityDetailMetrics`` — the per-second metric stream, used as a
       fallback when the polyline DTO is absent.

    Returns a dict with zero or more of: ``route_polyline`` (JSON list of
    ``[lat, lon]`` pairs) and ``altitude_profile`` (list of altitude values in
    metres, resampled to ≤ 100 points for the chart).
    """
    out: dict[str, Any] = {}
    if not isinstance(details, dict):
        return out

    # ── primary: geoPolylineDTO ────────────────────────────────────────────
    polyline_dto = details.get("geoPolylineDTO")
    if isinstance(polyline_dto, dict):
        raw_poly = polyline_dto.get("polyline")
        if isinstance(raw_poly, list) and len(raw_poly) >= 2:
            pts: list[list[float]] = []
            alts: list[float] = []
            for pt in raw_poly:
                if not isinstance(pt, dict):
                    continue
                lat = _num(pt.get("lat"))
                lon = _num(pt.get("lon"))
                if lat is None or lon is None or (lat == 0.0 and lon == 0.0):
                    continue
                pts.append([round(lat, 6), round(lon, 6)])
                alt = _num(pt.get("altitude"))
                if alt is not None:
                    alts.append(round(alt, 1))
            if len(pts) >= 2:
                out["route_polyline"] = _json.dumps(pts)
            if len(alts) >= 2:
                step = max(1, len(alts) // 100)
                out["altitude_profile"] = alts[::step]

    # ── fallback: per-second metric stream ────────────────────────────────
    if "route_polyline" not in out:
        out.update(_extract_gps_from_metric_stream(details))

    return out


def _extract_gps_from_metric_stream(details: dict[str, Any]) -> dict[str, Any]:
    """GPS extraction from the ``activityDetailMetrics`` stream.

    Each row in ``activityDetailMetrics`` is one sample (typically one second).
    The descriptor list maps column indices to metric keys; we locate
    ``directLatitude``, ``directLongitude`` and optionally ``directElevation``
    then downsample to ≤ 300 track points so the JSON payload stays compact.
    """
    out: dict[str, Any] = {}
    descriptors = details.get("metricDescriptors")
    metric_rows = details.get("activityDetailMetrics")
    if not isinstance(descriptors, list) or not isinstance(metric_rows, list):
        return out

    lat_idx = lon_idx = alt_idx = None
    for i, desc in enumerate(descriptors):
        if not isinstance(desc, dict):
            continue
        key = str(desc.get("metricsKey", "")).lower()
        if key == "directlatitude":
            lat_idx = i
        elif key == "directlongitude":
            lon_idx = i
        elif key in ("directelevation", "directaltitude"):
            alt_idx = i

    if lat_idx is None or lon_idx is None:
        return out

    all_lats: list[float] = []
    all_lons: list[float] = []
    all_alts: list[float] = []

    for row in metric_rows:
        if not isinstance(row, dict):
            continue
        vals = row.get("metrics")
        if not isinstance(vals, list):
            continue
        try:
            lat_raw = vals[lat_idx] if lat_idx < len(vals) else None
            lon_raw = vals[lon_idx] if lon_idx < len(vals) else None
            lat = float(lat_raw) if lat_raw is not None else None
            lon = float(lon_raw) if lon_raw is not None else None
        except (TypeError, ValueError):
            continue
        if lat is None or lon is None or (lat == 0.0 and lon == 0.0):
            continue
        all_lats.append(lat)
        all_lons.append(lon)
        if alt_idx is not None and alt_idx < len(vals) and vals[alt_idx] is not None:
            try:
                all_alts.append(float(vals[alt_idx]))
            except (TypeError, ValueError):
                pass

    if len(all_lats) < 2:
        return out

    step = max(1, len(all_lats) // 300)
    pts = [[round(all_lats[i], 6), round(all_lons[i], 6)] for i in range(0, len(all_lats), step)]
    last = [round(all_lats[-1], 6), round(all_lons[-1], 6)]
    if pts[-1] != last:
        pts.append(last)
    out["route_polyline"] = _json.dumps(pts)

    if len(all_alts) >= 10:
        step_alt = max(1, len(all_alts) // 100)
        out["altitude_profile"] = [round(a, 1) for a in all_alts[::step_alt]]

    return out


# ── Per-second sample streams (Fase 1) ────────────────────────────────────

# Garmin ``metricsKey`` (lowercased) → output stream name. Speed stays in m/s
# (A4: pace is derived in UI/processing, never stored). Unknown descriptors are
# ignored (A11), so adding/renaming Garmin metrics never breaks extraction.
_STREAM_METRIC_KEYS: dict[str, str] = {
    "directheartrate": "hr",
    "directspeed": "speed",
    "directpower": "power",
    "directruncadence": "cadence",
    "directdoublecadence": "cadence",
    "directelevation": "elevation",
    "directaltitude": "elevation",
    "sumdistance": "distance",
}

# metricsKey candidates for the time axis. Duration keys are seconds from
# start; the timestamp key is epoch milliseconds (converted to seconds).
_DURATION_KEYS = ("sumduration", "sumelapsedduration", "summovingduration")
_TIMESTAMP_KEY = "directtimestamp"

# Streams rounded to int; every other stream is a float.
_INT_STREAMS = {"hr", "cadence"}


def _target_points(duration_min: float) -> int:
    """Adaptive point budget per stream by session duration (A8)."""
    if duration_min <= 30:
        return 300
    if duration_min <= 90:
        return 600
    return 1200


def _at(vals: list, idx: int) -> Any:
    return vals[idx] if 0 <= idx < len(vals) else None


def _round_stream(name: str, value: float | None) -> int | float | None:
    if value is None:
        return None
    if name in _INT_STREAMS:
        return int(round(value))
    if name == "speed":
        return round(value, 3)
    return round(value, 1)


def extract_sample_streams(details: Any) -> dict[str, list]:
    """Extract aligned per-second streams from ``get_activity_details``.

    Generalises :func:`_extract_gps_from_metric_stream`: instead of only GPS it
    reads every stream we care about (heart rate, speed in m/s [A4], power,
    cadence, elevation, cumulative distance) from the ``activityDetailMetrics``
    matrix, keyed by ``metricDescriptors``. Tolerant (A11): unknown descriptors
    are skipped and a missing/garbled matrix yields ``{}`` — never an exception.
    The aligned series are adaptively downsampled to a point budget that scales
    with duration (A8).

    Returns a JSON-serialisable dict ``{"t": [seconds], "<stream>": [...]}``
    holding ``t`` plus only the streams that carried at least one real value.
    Value gaps are preserved as ``None`` so every stream stays index-aligned
    with ``t``.
    """
    if not isinstance(details, dict):
        return {}
    descriptors = details.get("metricDescriptors")
    rows = details.get("activityDetailMetrics")
    if not isinstance(descriptors, list) or not isinstance(rows, list):
        return {}

    col_to_stream: dict[int, str] = {}
    assigned: set[str] = set()
    duration_idx: int | None = None
    timestamp_idx: int | None = None
    unknown: set[str] = set()
    for i, desc in enumerate(descriptors):
        if not isinstance(desc, dict):
            continue
        key = str(desc.get("metricsKey", "")).lower()
        name = _STREAM_METRIC_KEYS.get(key)
        if name is not None:
            if name not in assigned:  # first descriptor wins per stream
                col_to_stream[i] = name
                assigned.add(name)
        elif key in _DURATION_KEYS and duration_idx is None:
            duration_idx = i
        elif key == _TIMESTAMP_KEY and timestamp_idx is None:
            timestamp_idx = i
        elif key:
            unknown.add(key)
    if unknown:
        logger.debug(
            "sample_streams: ignoring %d unmapped descriptor(s): %s",
            len(unknown), sorted(unknown),
        )

    times: list[float] = []
    collected: dict[str, list[float | None]] = {name: [] for name in assigned}
    first_ts: float | None = None
    for idx, row in enumerate(rows):
        vals = row.get("metrics") if isinstance(row, dict) else None
        if not isinstance(vals, list):
            continue
        t: float | None = None
        if duration_idx is not None:
            t = _num(_at(vals, duration_idx))
        if t is None and timestamp_idx is not None:
            ts = _num(_at(vals, timestamp_idx))
            if ts is not None:
                if first_ts is None:
                    first_ts = ts
                t = (ts - first_ts) / 1000.0
        if t is None:
            t = float(idx)  # assume ~1 Hz when no time column is present
        times.append(t)
        for col, name in col_to_stream.items():
            collected[name].append(_num(_at(vals, col)))

    n = len(times)
    if n < 2:
        return {}

    streams = {
        name: vals for name, vals in collected.items()
        if any(v is not None for v in vals)
    }

    duration_min = max(0.0, times[-1] - times[0]) / 60.0
    step = max(1, n // _target_points(duration_min))
    keep = list(range(0, n, step))
    if keep[-1] != n - 1:
        keep.append(n - 1)

    out: dict[str, list] = {"t": [int(round(times[i])) for i in keep]}
    for name, vals in streams.items():
        out[name] = [_round_stream(name, vals[i]) for i in keep]
    return out


def extract_weather(payload: Any) -> dict[str, Any]:
    """Parse ``get_activity_weather`` for humidity (unit-safe fields only).

    Temperature from the weather endpoint is locale/unit-ambiguous, so we take
    it from the activity summary instead and only read relative humidity here.
    """
    out: dict[str, Any] = {}
    if not isinstance(payload, dict):
        return out
    humidity = _num(payload.get("relativeHumidity"))
    if humidity is not None:
        out["humidity_pct"] = humidity
    return out


def _stamina_drop(summary: dict[str, Any]) -> float | None:
    """Compute ``beginPotentialStamina - endPotentialStamina`` when sensible."""
    begin = _num(summary.get("beginPotentialStamina"))
    end = _num(summary.get("endPotentialStamina"))
    if begin is None or end is None:
        return None
    drop = begin - end
    # Guard against nonsensical values (Garmin occasionally reports negative
    # or near-zero deltas on very short activities).
    if drop < 0:
        return 0.0
    return round(drop, 1)


def _extract_hr_zones(activity: dict[str, Any]) -> dict[str, float] | None:
    """Pull per-zone time (minutes) if Garmin provided it.

    Supports both shapes seen in practice:

    * the flat field set returned by the public Connect API
      (``hrTimeInZone_1`` .. ``hrTimeInZone_5`` in seconds);
    * the nested ``hrTimeInZones`` / ``timeInZones`` dict used by older
      fixtures and tests.
    """
    flat: dict[str, float] = {}
    for n in range(1, 6):
        key = f"hrTimeInZone_{n}"
        if key in activity and activity[key] is not None:
            try:
                flat[f"z{n}"] = round(float(activity[key]) / 60.0, 1)
            except (TypeError, ValueError):
                continue
    if flat:
        return flat

    zones = activity.get("hrTimeInZones") or activity.get("timeInZones")
    if not isinstance(zones, dict):
        return None
    out: dict[str, float] = {}
    for key, value in zones.items():
        try:
            out[str(key).lower().replace("zone", "z")] = round(float(value) / 60.0, 1)
        except (TypeError, ValueError):
            continue
    return out or None


def _split_seconds_to_pace(total_s: float | None, distance_m: float) -> str | None:
    """Turn ``fastestSplit_*`` (seconds for the given distance) into a pace string."""
    if total_s is None or total_s <= 0 or distance_m <= 0:
        return None
    return _format_pace(distance_m, total_s)


def _speed_to_pace(speed_mps: float | None) -> str | None:
    """Format a m/s speed as ``mm:ss/km`` pace."""
    if speed_mps is None or speed_mps <= 0:
        return None
    return _format_pace(1000.0, 1000.0 / speed_mps)


# ── multi-sport (Feature 24): bike / swim / strength ─────────────────────────
#
# Garmin's ``activityType.typeKey`` is fine-grained (road_biking, lap_swimming,
# indoor_cardio, ...). We collapse it into the three cross-training disciplines
# the app tracks. Anything not matched here is not cross-training (it's running
# or an activity type we don't surface).
_GARMIN_SPORT_MAP = {
    # cycling family
    "cycling": "bike",
    "road_biking": "bike",
    "mountain_biking": "bike",
    "gravel_cycling": "bike",
    "indoor_cycling": "bike",
    "virtual_ride": "bike",
    "e_bike_fitness": "bike",
    "cyclocross": "bike",
    # swimming family
    "lap_swimming": "swim",
    "open_water_swimming": "swim",
    "swimming": "swim",
    # strength / gym family
    "strength_training": "strength",
    "indoor_cardio": "strength",
    "fitness_equipment": "strength",
    "elliptical": "strength",
    "pilates": "strength",
    "yoga": "strength",
}

# Cross-training disciplines the app supports. Used to validate inbound values.
CROSS_TRAINING_SPORTS = ("bike", "swim", "strength")


def garmin_sport(activity: dict[str, Any]) -> str | None:
    """Return the cross-training sport for a Garmin activity, or ``None``.

    ``None`` means the activity is not one of the tracked cross-training
    disciplines (it may be running, or a type we don't surface).
    """
    type_field = activity.get("activityType")
    type_key = ""
    if isinstance(type_field, dict):
        type_key = str(type_field.get("typeKey", "")).lower()
    else:
        type_key = str(type_field or "").lower()
    return _GARMIN_SPORT_MAP.get(type_key)


def synthesize_cross_training(activity: dict[str, Any], sport: str) -> RunSummary:
    """Map a raw Garmin cross-training activity onto the compact schema.

    Unlike :func:`synthesize`, this does not run the running-specific workout
    classifier (intervals/tempo/long): for cross-training the ``activity_type``
    simply mirrors the sport. Distance is meaningless for strength work, so it
    degrades to 0 gracefully. Heart-rate, duration and elevation are kept when
    present since they're sport-agnostic.
    """
    distance_m = float(activity.get("distance") or 0.0)
    duration_s = float(activity.get("duration") or activity.get("movingDuration") or 0.0)
    duration_min = round(duration_s / 60.0, 1)

    return RunSummary(
        garmin_activity_id=(
            str(activity["activityId"]) if activity.get("activityId") is not None else None
        ),
        date=str(activity.get("startTimeLocal", ""))[:10],
        start_time=extract_start_time(activity.get("startTimeLocal")),
        sport=sport,
        activity_type=sport,
        duration_min=duration_min,
        # Pace is only meaningful for distance sports; bike/swim keep distance,
        # strength has none.
        distance_km=round(distance_m / 1000.0, 2),
        avg_pace=_format_pace(distance_m, duration_s) if sport == "swim" else None,
        avg_hr=int(activity["averageHR"]) if activity.get("averageHR") else None,
        max_hr=int(activity["maxHR"]) if activity.get("maxHR") else None,
        elevation_gain_m=(
            round(float(activity["elevationGain"]), 0) if activity.get("elevationGain") else None
        ),
        avg_cadence=None,
        hr_zones=_extract_hr_zones(activity),
        rpe=None,
        notes=activity.get("activityName") or None,
    )


def synthesize(activity: dict[str, Any]) -> RunSummary:
    """Map a raw Garmin activity dict onto the compact schema."""
    distance_m = float(activity.get("distance") or 0.0)
    duration_s = float(activity.get("duration") or activity.get("movingDuration") or 0.0)
    duration_min = round(duration_s / 60.0, 1)
    hr_zones = _extract_hr_zones(activity)

    base = RunSummary(
        garmin_activity_id=(
            str(activity["activityId"]) if activity.get("activityId") is not None else None
        ),
        date=str(activity.get("startTimeLocal", ""))[:10],
        start_time=extract_start_time(activity.get("startTimeLocal")),
        activity_type=_infer_type(activity, hr_zones=hr_zones, duration_min=duration_min),
        duration_min=duration_min,
        distance_km=round(distance_m / 1000.0, 2),
        avg_pace=_format_pace(distance_m, duration_s),
        avg_hr=int(activity["averageHR"]) if activity.get("averageHR") else None,
        max_hr=int(activity["maxHR"]) if activity.get("maxHR") else None,
        elevation_gain_m=(
            round(float(activity["elevationGain"]), 0) if activity.get("elevationGain") else None
        ),
        avg_cadence=(
            int(activity["averageRunningCadenceInStepsPerMinute"])
            if activity.get("averageRunningCadenceInStepsPerMinute")
            else None
        ),
        hr_zones=hr_zones,
        splits_km=None,
        rpe=None,
        notes=None,
    )
    # Layer the optional Garmin-derived metrics on top. ``_rich_fields`` only
    # emits keys it could actually compute, so this never nulls out core data.
    return base.model_copy(update=_rich_fields(activity))


# Garmin field aliases seen across the list (``get_activities``) and detail
# (``get_activity`` / ``summaryDTO``) payloads. The same metric is named
# differently depending on the endpoint and account locale.
_TEMP_KEYS = ("temperature", "avgTemperature", "averageTemperature")
_GAP_KEYS = ("avgGradeAdjustedSpeed", "averageGradeAdjustedSpeed")
_VO2_KEYS = ("vO2MaxValue", "vo2MaxValue", "vO2MaxPreciseValue", "maxMetValue")


def _first_num(activity: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _num(activity.get(key))
        if value is not None:
            return value
    return None


def _rich_fields(activity: dict[str, Any]) -> dict[str, Any]:
    """Extract every optional Garmin metric present in ``activity``.

    Works on both the sparse list payload and the much richer detail payload
    (``summaryDTO`` flattened in). Only keys with a usable value are returned,
    so callers can ``model_copy(update=...)`` without clobbering good data.
    """
    out: dict[str, Any] = {}

    hr_zones = _extract_hr_zones(activity)
    if hr_zones:
        out["hr_zones"] = hr_zones

    temp = _first_num(activity, _TEMP_KEYS)
    if temp is None:
        lo, hi = _num(activity.get("minTemperature")), _num(activity.get("maxTemperature"))
        if lo is not None and hi is not None:
            temp = round((lo + hi) / 2.0, 1)
    if temp is not None:
        out["temperature_c"] = temp

    humidity = _num(activity.get("humidity") or activity.get("relativeHumidity"))
    if humidity is not None:
        out["humidity_pct"] = humidity

    eloss = _num(activity.get("elevationLoss"))
    if eloss is not None:
        out["elevation_loss_m"] = round(eloss, 0)

    egain = _num(activity.get("elevationGain"))
    if egain is not None:
        out["elevation_gain_m"] = round(egain, 0)

    cadence = _num(activity.get("averageRunningCadenceInStepsPerMinute"))
    if cadence is not None:
        out["avg_cadence"] = int(cadence)

    training_load = _num(activity.get("activityTrainingLoad"))
    if training_load is not None:
        out["garmin_training_load"] = round(training_load, 0)

    vigorous = _num(activity.get("vigorousIntensityMinutes"))
    if vigorous is not None:
        out["vigorous_minutes"] = vigorous
    moderate = _num(activity.get("moderateIntensityMinutes"))
    if moderate is not None:
        out["moderate_minutes"] = moderate

    bb_delta = _num(activity.get("differenceBodyBattery"))
    if bb_delta is not None:
        out["body_battery_delta"] = int(bb_delta)

    gap = _speed_to_pace(_first_num(activity, _GAP_KEYS))
    if gap:
        out["avg_grade_adjusted_pace"] = gap

    fastest_1k = _split_seconds_to_pace(_num(activity.get("fastestSplit_1000")), 1000.0)
    if fastest_1k:
        out["fastest_split_1k"] = fastest_1k
    fastest_5k = _split_seconds_to_pace(_num(activity.get("fastestSplit_5000")), 5000.0)
    if fastest_5k:
        out["fastest_split_5k"] = fastest_5k

    vo2max = _first_num(activity, _VO2_KEYS)
    if vo2max is not None:
        out["vo2max"] = round(vo2max, 1)

    aerobic_te = _num(activity.get("aerobicTrainingEffect"))
    if aerobic_te is not None:
        out["aerobic_training_effect"] = round(aerobic_te, 1)
    anaerobic_te = _num(activity.get("anaerobicTrainingEffect"))
    if anaerobic_te is not None:
        out["anaerobic_training_effect"] = round(anaerobic_te, 1)

    aerobic_msg = activity.get("aerobicTrainingEffectMessage")
    if aerobic_msg:
        out["aerobic_te_message"] = aerobic_msg
    anaerobic_msg = activity.get("anaerobicTrainingEffectMessage")
    if anaerobic_msg:
        out["anaerobic_te_message"] = anaerobic_msg

    return out
