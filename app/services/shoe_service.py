"""Shoe tracking service (Roadmap #6).

CRUD operations for running shoes plus computed mileage from activities
that reference each shoe via ``shoe_id``.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Activity, Shoe
from app.schemas import ShoeIn, ShoeOut


def _compute_mileage(session: Session, shoe_id: int) -> float:
    total = session.scalar(
        select(func.coalesce(func.sum(Activity.distance_km), 0.0)).where(
            Activity.shoe_id == shoe_id, Activity.sport == "run"
        )
    )
    return float(total or 0.0)


def _to_out(session: Session, shoe: Shoe) -> ShoeOut:
    total_km = _compute_mileage(session, shoe.id)
    wear_pct = (total_km / shoe.max_km * 100.0) if shoe.max_km and shoe.max_km > 0 else 0.0
    return ShoeOut(
        id=shoe.id,
        name=shoe.name,
        brand=shoe.brand,
        model=shoe.model,
        purchase_date=shoe.purchase_date,
        max_km=shoe.max_km,
        retired=shoe.retired,
        notes=shoe.notes,
        total_km=round(total_km, 1),
        wear_pct=round(wear_pct, 1),
        replacement_due=wear_pct >= 100.0 and not shoe.retired,
    )


def list_shoes(session: Session, include_retired: bool = True) -> list[ShoeOut]:
    stmt = select(Shoe).order_by(Shoe.created_at.desc())
    if not include_retired:
        stmt = stmt.where(Shoe.retired.is_(False))
    rows = list(session.scalars(stmt).all())
    return [_to_out(session, s) for s in rows]


def get_shoe(session: Session, shoe_id: int) -> ShoeOut | None:
    shoe = session.get(Shoe, shoe_id)
    if shoe is None:
        return None
    return _to_out(session, shoe)


def create_shoe(session: Session, payload: ShoeIn) -> ShoeOut:
    shoe = Shoe(
        name=payload.name,
        brand=payload.brand,
        model=payload.model,
        purchase_date=payload.purchase_date,
        max_km=payload.max_km,
        retired=payload.retired,
        notes=payload.notes,
    )
    session.add(shoe)
    session.flush()
    return _to_out(session, shoe)


def update_shoe(session: Session, shoe_id: int, payload: ShoeIn) -> ShoeOut | None:
    shoe = session.get(Shoe, shoe_id)
    if shoe is None:
        return None
    shoe.name = payload.name
    shoe.brand = payload.brand
    shoe.model = payload.model
    shoe.purchase_date = payload.purchase_date
    shoe.max_km = payload.max_km
    shoe.retired = payload.retired
    shoe.notes = payload.notes
    session.flush()
    return _to_out(session, shoe)


def delete_shoe(session: Session, shoe_id: int) -> bool:
    shoe = session.get(Shoe, shoe_id)
    if shoe is None:
        return False
    session.delete(shoe)
    session.flush()
    return True


def assign_activity_shoe(session: Session, activity_id: int, shoe_id: int | None) -> bool:
    from app.db.models import Activity as ActivityModel

    activity = session.get(ActivityModel, activity_id)
    if activity is None:
        return False
    if shoe_id is not None and session.get(Shoe, shoe_id) is None:
        return False
    activity.shoe_id = shoe_id
    session.flush()
    return True
