"""Collection layer: pulling raw activity data and synthesising it.

This layer is intentionally independent of processing and coaching. It knows
how to *get* activities (from Garmin, or from bundled demo data) and how to
*synthesise* a raw Garmin payload into a compact :class:`RunSummary`.
"""

from app.collection.sources import DemoSource, GarminSource, get_source
from app.collection.synthesize import synthesize

__all__ = ["DemoSource", "GarminSource", "get_source", "synthesize"]
