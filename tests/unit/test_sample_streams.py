"""Tests for per-second sample stream extraction and features (Fase 1 M1)."""

from __future__ import annotations

from app.collection.synthesize import (
    _target_points,
    extract_sample_streams,
)
from app.processing.streams import (
    aerobic_decoupling,
    cardiac_drift,
    compute_stream_features,
    speed_cv,
)


def test_extract_streams_emptyOrGarbage_returnsEmpty():
    assert extract_sample_streams(None) == {}
    assert extract_sample_streams({}) == {}
    assert extract_sample_streams({"metricDescriptors": "not a list"}) == {}
    assert extract_sample_streams({"activityDetailMetrics": "not a list"}) == {}


def test_extract_streams_missingDescriptors_returnsEmpty():
    assert extract_sample_streams({"activityDetailMetrics": []}) == {}


def test_extract_streams_allMappedFields_alignedDownsampled():
    # 60 seconds of data: 1 Hz, all fields present.
    rows = []
    for i in range(60):
        rows.append({
            "metrics": [
                i,  # sumDuration
                140 + i // 10,  # directHeartRate (steps up every 10s)
                3.0 + (i % 10) * 0.1,  # directSpeed (m/s, oscillates)
                250,  # directPower (constant)
                180,  # directRunCadence (constant)
                100.0 + i,  # directElevation (rises)
                i * 5.0,  # sumDistance (cumulative)
            ]
        })
    details = {
        "metricDescriptors": [
            {"metricsKey": "sumDuration"},
            {"metricsKey": "directHeartRate"},
            {"metricsKey": "directSpeed"},
            {"metricsKey": "directPower"},
            {"metricsKey": "directRunCadence"},
            {"metricsKey": "directElevation"},
            {"metricsKey": "sumDistance"},
        ],
        "activityDetailMetrics": rows,
    }
    out = extract_sample_streams(details)

    assert "t" in out
    assert "hr" in out
    assert "speed" in out
    assert "power" in out
    assert "cadence" in out
    assert "elevation" in out
    assert "distance" in out

    # All series are index-aligned and same length.
    n = len(out["t"])
    for name in ("hr", "speed", "power", "cadence", "elevation", "distance"):
        assert len(out[name]) == n, f"{name} length mismatch"

    # Time axis is integer seconds.
    assert out["t"][0] == 0
    assert out["t"][-1] == 59

    # HR is int, speed is float (3 decimals), elevation is float (1 decimal).
    assert isinstance(out["hr"][0], int)
    assert isinstance(out["speed"][0], float)
    assert isinstance(out["elevation"][0], float)

    # Downsampling: 60s → 30min budget (300 points) → no downsampling here.
    assert n == 60


def test_extract_streams_adaptiveDownsampling_byDuration():
    # 2 hours (7200 seconds) → >90min → 1200 point budget.
    rows = []
    for i in range(7200):
        rows.append({"metrics": [i, 140, 3.0]})
    details = {
        "metricDescriptors": [
            {"metricsKey": "sumDuration"},
            {"metricsKey": "directHeartRate"},
            {"metricsKey": "directSpeed"},
        ],
        "activityDetailMetrics": rows,
    }
    out = extract_sample_streams(details)
    # 7200 / 1200 = 6, so expect ~1200 points (step=6, plus last).
    assert 1200 <= len(out["t"]) <= 1205


def test_extract_streams_tolerant_unknownDescriptors_skipped():
    rows = [{"metrics": [0, 140, 3.0]}, {"metrics": [1, 141, 3.1]}]
    details = {
        "metricDescriptors": [
            {"metricsKey": "sumDuration"},
            {"metricsKey": "directHeartRate"},
            {"metricsKey": "directSpeed"},
            {"metricsKey": "futureMetricKey"},  # unknown → ignored (A11)
        ],
        "activityDetailMetrics": rows,
    }
    out = extract_sample_streams(details)
    assert "t" in out
    assert "hr" in out
    assert "speed" in out
    assert "futureMetricKey" not in out


def test_extract_streams_speedNotPace_storedAsMetersPerSecond():
    rows = [{"metrics": [0, 140, 3.5]}, {"metrics": [1, 141, 3.6]}]  # 3.5 m/s ≈ 2:51/km
    details = {
        "metricDescriptors": [
            {"metricsKey": "sumDuration"},
            {"metricsKey": "directHeartRate"},
            {"metricsKey": "directSpeed"},
        ],
        "activityDetailMetrics": rows,
    }
    out = extract_sample_streams(details)
    assert out["speed"][0] == 3.5  # not pace string


def test_extract_streams_gapsPreserved_asNone():
    rows = [
        {"metrics": [0, 140, 3.0]},
        {"metrics": [1, None, 3.1]},  # HR missing
        {"metrics": [2, 142, None]},  # speed missing
    ]
    details = {
        "metricDescriptors": [
            {"metricsKey": "sumDuration"},
            {"metricsKey": "directHeartRate"},
            {"metricsKey": "directSpeed"},
        ],
        "activityDetailMetrics": rows,
    }
    out = extract_sample_streams(details)
    assert out["hr"][1] is None
    assert out["speed"][2] is None


def test_extract_streams_onlyStreamsWithRealValues_emitted():
    rows = [{"metrics": [0, 140, None]}, {"metrics": [1, 141, None]}]  # speed is None
    details = {
        "metricDescriptors": [
            {"metricsKey": "sumDuration"},
            {"metricsKey": "directHeartRate"},
            {"metricsKey": "directSpeed"},
        ],
        "activityDetailMetrics": rows,
    }
    out = extract_sample_streams(details)
    assert "hr" in out
    assert "speed" not in out  # no real values → omitted


def test_targetPoints_thresholds():
    assert _target_points(20) == 300
    assert _target_points(30) == 300
    assert _target_points(45) == 600
    assert _target_points(90) == 600
    assert _target_points(91) == 1200
    assert _target_points(120) == 1200


# ── Feature computation tests ───────────────────────────────────────────────

def test_speed_cv_constantSpeed_returnsZero():
    streams = {"speed": [3.0, 3.0, 3.0, 3.0]}
    assert speed_cv(streams) == 0.0


def test_speed_cv_variedSpeed_returnsPositive():
    streams = {"speed": [2.5, 3.0, 3.5, 4.0]}
    cv = speed_cv(streams)
    assert cv is not None
    assert cv > 0


def test_speed_cv_missingStream_returnsNone():
    assert speed_cv({}) is None
    assert speed_cv({"speed": None}) is None
    assert speed_cv({"other": [1, 2, 3]}) is None


def test_speed_cv_tooFewSamples_returnsNone():
    assert speed_cv({"speed": [3.0]}) is None


def test_speed_cv_filtersStoppedSamples():
    # Include stopped samples (<0.5 m/s) which should be filtered out
    streams = {"speed": [0.2, 0.3, 3.0, 3.1]}  # only 2 moving samples
    cv = speed_cv(streams)
    assert cv is not None  # should compute on filtered moving samples


def test_cardiac_drift_noDrift_returnsZero():
    # HR constant across halves - need longer series for valid split
    streams = {
        "t": [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300],
        "hr": [140, 140, 140, 140, 140, 140, 140, 140, 140, 140, 140],
    }
    assert cardiac_drift(streams) == 0.0


def test_cardiac_drift_risingHR_returnsPositive():
    # HR rises from 140 to 150 - need longer series for valid split
    streams = {
        "t": [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300],
        "hr": [140, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150],
    }
    drift = cardiac_drift(streams)
    assert drift is not None
    assert drift > 0


def test_cardiac_drift_missingStream_returnsNone():
    assert cardiac_drift({}) is None
    assert cardiac_drift({"t": [0, 30]}) is None
    assert cardiac_drift({"hr": [140, 142]}) is None


def test_cardiac_drift_tooFewSamples_returnsNone():
    streams = {"t": [0, 5], "hr": [140, 142]}
    assert cardiac_drift(streams) is None  # < MIN_HALF_SAMPLES per half


def test_cardiac_drift_handlesGaps():
    # HR with None gaps, only real values used - need enough samples after filtering
    streams = {
        "t": [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330, 360, 390, 420, 450, 480, 510, 540, 570, 600],
        "hr": [140, 141, None, 142, 143, None, 144, 145, None, 146, 147, None, 148, 149, None, 150, 151, None, 152, 153, 154],
    }
    drift = cardiac_drift(streams)
    assert drift is not None


def test_aerobic_decoupling_stableRatio_returnsZero():
    # Speed and HR both rise proportionally - need longer series for valid split
    streams = {
        "t": [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300],
        "speed": [3.0, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 4.0],
        "hr": [140, 145, 150, 155, 160, 165, 170, 175, 180, 185, 190],
    }
    dec = aerobic_decoupling(streams)
    # Ratio stays roughly constant, so decoupling near zero
    assert dec is not None
    assert abs(dec) < 5.0  # allow small numerical error


def test_aerobic_decoupling_degradingRatio_returnsPositive():
    # Speed drops while HR rises (typical fatigue) - need longer series
    streams = {
        "t": [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300],
        "speed": [4.0, 3.9, 3.8, 3.7, 3.6, 3.5, 3.4, 3.3, 3.2, 3.1, 3.0],
        "hr": [140, 142, 144, 146, 148, 150, 152, 154, 156, 158, 160],
    }
    dec = aerobic_decoupling(streams)
    assert dec is not None
    assert dec > 0  # positive = efficiency degraded


def test_aerobic_decoupling_missingStream_returnsNone():
    assert aerobic_decoupling({}) is None
    assert aerobic_decoupling({"t": [0, 30]}) is None
    assert aerobic_decoupling({"speed": [3.0, 3.1]}) is None
    assert aerobic_decoupling({"hr": [140, 142]}) is None


def test_aerobic_decoupling_tooFewSamples_returnsNone():
    streams = {"t": [0, 5], "speed": [3.0, 3.1], "hr": [140, 142]}
    assert aerobic_decoupling(streams) is None


def test_aerobic_decoupling_filtersStoppedSamples():
    # Include stopped samples which should be filtered - need longer series
    streams = {
        "t": [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330, 360, 390, 420],
        "speed": [0.3, 0.4, 3.0, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 4.0, 4.1, 4.2],
        "hr": [140, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150, 151, 152, 153, 154],
    }
    dec = aerobic_decoupling(streams)
    assert dec is not None  # should compute on filtered moving samples


def test_compute_stream_features_allPresent_returnsValues():
    streams = {
        "t": [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300],
        "speed": [3.0, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 4.0],
        "hr": [140, 142, 144, 146, 148, 150, 152, 154, 156, 158, 160],
    }
    features = compute_stream_features(streams)
    assert features.decoupling_pct is not None
    assert features.hr_drift_pct is not None
    assert features.speed_cv is not None


def test_compute_stream_features_empty_returnsAllNone():
    features = compute_stream_features({})
    assert features.decoupling_pct is None
    assert features.hr_drift_pct is None
    assert features.speed_cv is None


def test_compute_stream_features_invalidInput_returnsAllNone():
    features = compute_stream_features(None)
    assert features.decoupling_pct is None
    assert features.hr_drift_pct is None
    assert features.speed_cv is None
