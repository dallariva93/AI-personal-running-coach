"""Unit tests for shoe tracking service (Roadmap #6)."""

from app.services.shoe_service import (
    create_shoe,
    update_shoe,
    delete_shoe,
    get_shoe,
    list_shoes,
    assign_activity_shoe,
)
from app.schemas import ShoeIn
from app.db.models import Activity, Shoe


def test_create_shoe(session):
    """Create a new shoe and verify computed fields."""
    payload = ShoeIn(name="Nike Pegasus", brand="Nike", model="Pegasus 40", max_km=800.0)
    shoe = create_shoe(session, payload)

    assert shoe.id is not None
    assert shoe.name == "Nike Pegasus"
    assert shoe.brand == "Nike"
    assert shoe.model == "Pegasus 40"
    assert shoe.max_km == 800.0
    assert shoe.total_km == 0.0
    assert shoe.wear_pct == 0.0
    assert shoe.replacement_due is False


def test_update_shoe(session):
    """Update an existing shoe."""
    payload = ShoeIn(name="Test Shoe", max_km=500.0)
    shoe = create_shoe(session, payload)

    updated = update_shoe(
        session, shoe.id, ShoeIn(name="Updated Shoe", max_km=600.0, retired=True)
    )
    assert updated.name == "Updated Shoe"
    assert updated.max_km == 600.0
    assert updated.retired is True


def test_delete_shoe(session):
    """Delete a shoe."""
    payload = ShoeIn(name="To Delete")
    shoe = create_shoe(session, payload)

    assert delete_shoe(session, shoe.id) is True
    assert get_shoe(session, shoe.id) is None


def test_list_shoes(session):
    """List shoes, optionally filtering out retired ones."""
    create_shoe(session, ShoeIn(name="Active 1"))
    create_shoe(session, ShoeIn(name="Active 2"))
    create_shoe(session, ShoeIn(name="Retired", retired=True))

    all_shoes = list_shoes(session, include_retired=True)
    assert len(all_shoes) == 3

    active_only = list_shoes(session, include_retired=False)
    assert len(active_only) == 2
    assert all(not s.retired for s in active_only)


def test_shoe_mileage_computation(session):
    """Mileage is computed from activities referencing the shoe."""
    shoe = create_shoe(session, ShoeIn(name="Test Shoe", max_km=100.0))

    activity1 = Activity(
        date="2026-07-01",
        sport="run",
        activity_type="easy",
        duration_min=30.0,
        distance_km=10.0,
        shoe_id=shoe.id,
    )
    activity2 = Activity(
        date="2026-07-02",
        sport="run",
        activity_type="easy",
        duration_min=30.0,
        distance_km=15.0,
        shoe_id=shoe.id,
    )
    session.add(activity1)
    session.add(activity2)
    session.flush()

    shoe_with_mileage = get_shoe(session, shoe.id)
    assert shoe_with_mileage.total_km == 25.0
    assert shoe_with_mileage.wear_pct == 25.0
    assert shoe_with_mileage.replacement_due is False


def test_shoe_replacement_due(session):
    """Replacement flag is set when wear exceeds max_km."""
    shoe = create_shoe(session, ShoeIn(name="Worn Shoe", max_km=50.0))

    activity = Activity(
        date="2026-07-01",
        sport="run",
        activity_type="easy",
        duration_min=30.0,
        distance_km=60.0,
        shoe_id=shoe.id,
    )
    session.add(activity)
    session.flush()

    shoe_worn = get_shoe(session, shoe.id)
    assert shoe_worn.total_km == 60.0
    assert shoe_worn.wear_pct == 120.0
    assert shoe_worn.replacement_due is True


def test_shoe_replacement_ignored_when_retired(session):
    """Replacement flag is false for retired shoes even if worn."""
    shoe = create_shoe(session, ShoeIn(name="Retired Worn", max_km=50.0, retired=True))

    activity = Activity(
        date="2026-07-01",
        sport="run",
        activity_type="easy",
        duration_min=30.0,
        distance_km=60.0,
        shoe_id=shoe.id,
    )
    session.add(activity)
    session.flush()

    shoe_retired = get_shoe(session, shoe.id)
    assert shoe_retired.replacement_due is False


def test_assign_shoe_to_activity(session):
    """Assign a shoe to an activity."""
    shoe = create_shoe(session, ShoeIn(name="Test Shoe"))
    activity = Activity(
        date="2026-07-01",
        sport="run",
        activity_type="easy",
        duration_min=30.0,
        distance_km=10.0,
    )
    session.add(activity)
    session.flush()

    assert assign_activity_shoe(session, activity.id, shoe.id) is True
    session.refresh(activity)
    assert activity.shoe_id == shoe.id


def test_assign_shoe_null_removes_assignment(session):
    """Setting shoe_id to null removes the assignment."""
    shoe = create_shoe(session, ShoeIn(name="Test Shoe"))
    activity = Activity(
        date="2026-07-01",
        sport="run",
        activity_type="easy",
        duration_min=30.0,
        distance_km=10.0,
        shoe_id=shoe.id,
    )
    session.add(activity)
    session.flush()

    assert assign_activity_shoe(session, activity.id, None) is True
    session.refresh(activity)
    assert activity.shoe_id is None


def test_assign_shoe_to_nonexistent_activity(session):
    """Assigning to a non-existent activity returns False."""
    shoe = create_shoe(session, ShoeIn(name="Test Shoe"))
    assert assign_activity_shoe(session, 99999, shoe.id) is False


def test_assign_nonexistent_shoe_to_activity(session):
    """Assigning a non-existent shoe returns False."""
    activity = Activity(
        date="2026-07-01",
        sport="run",
        activity_type="easy",
        duration_min=30.0,
        distance_km=10.0,
    )
    session.add(activity)
    session.flush()

    assert assign_activity_shoe(session, activity.id, 99999) is False
