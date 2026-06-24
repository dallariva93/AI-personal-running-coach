"""Processing layer: derive training-load and form metrics from runs.

Pure functions, no I/O, no AI. Given a list of :class:`RunSummary` it computes
ACWR, weekly load, monotony, the 80/20 ratio, a form-state classification and
the load trend. This is the quantitative input the coaching layer reasons over.
"""

from app.processing.metrics import compute_metrics, weekly_buckets

__all__ = ["compute_metrics", "weekly_buckets"]
