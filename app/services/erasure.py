"""Right to erasure — GDPR art. 17 (Roadmap A10).

One call wipes every piece of athlete data the app holds: all DB tables
(children before parents, one transaction — the caller commits) plus the
archived raw payloads on object storage, best-effort. Only ``alembic_version``
survives, because schema history is not personal data.

Deliberately NOT deleted: the Fernet key file and the Garmin token-store file
— they are credentials/secrets of the *installation*, not athlete data, and
deleting the Fernet key would be destructive beyond the erasure request.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Activity,
    AthleteModelRow,
    AthleteProfileRow,
    ChatMessage,
    ChatSession,
    CoachDecisionRow,
    CoachEvent,
    CoachingReport,
    CoachMemory,
    DailyCheckinRow,
    DailyWellnessRow,
    RawActivityAsset,
    Shoe,
    StravaAccount,
    StravaWebhookEvent,
    SyncState,
    TrainingPlan,
    TrainingPlanSession,
    TrainingPlanWeek,
    WorkoutSegment,
    WorkoutTemplate,
)
from app.logging_config import get_logger
from app.storage import get_object_store

logger = get_logger("app.services.erasure")

# Children before parents, so plain DELETEs never trip a FK regardless of
# whether SQLite has foreign_keys enforcement on.
_DELETE_ORDER = [
    WorkoutSegment,
    ChatMessage,
    TrainingPlanSession,
    CoachingReport,
    TrainingPlanWeek,
    ChatSession,
    TrainingPlan,
    WorkoutTemplate,
    RawActivityAsset,
    Activity,
    DailyCheckinRow,
    DailyWellnessRow,
    CoachDecisionRow,
    CoachEvent,
    Shoe,
    StravaAccount,
    StravaWebhookEvent,
    AthleteProfileRow,
    AthleteModelRow,
    CoachMemory,
    SyncState,
]


def _delete_raw_objects(db: Session) -> int:
    """Best-effort deletion of archived payloads on S3. Never raises."""
    store = get_object_store()
    if store is None:
        return 0
    deleted = 0
    keys = db.scalars(select(RawActivityAsset.s3_key)).all()
    for key in keys:
        try:
            store.delete(key)
            deleted += 1
        except Exception as exc:  # noqa: BLE001 - erasure must not fail on S3 hiccups
            logger.warning("Erasure: could not delete object %s: %s", key, exc)
    return deleted


def delete_all_user_data(db: Session) -> dict[str, int]:
    """Empty every user-data table; returns per-table deleted-row counts.

    Runs inside the caller's transaction: either everything is deleted or
    (on error) nothing is. S3 objects are removed first and best-effort —
    an S3 failure is logged, not fatal, because the DB rows (with the
    pointers) are going away regardless and orphan objects can be cleaned
    from the bucket console.
    """
    counts: dict[str, int] = {"s3_objects": _delete_raw_objects(db)}
    for model in _DELETE_ORDER:
        counts[model.__tablename__] = db.query(model).delete(
            synchronize_session=False
        )
    logger.info("Right-to-erasure executed: %s", counts)
    return counts
