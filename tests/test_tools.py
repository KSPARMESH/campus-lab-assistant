"""Tests for Lab Tools: docstring prompt quality, database policies, clash prevention, and safe writes."""
import inspect

import pytest

from app.tools.lab_tools import BookingDeskTools, InventoryTools


@pytest.mark.parametrize("cls", [InventoryTools, BookingDeskTools])
def test_every_tool_is_described(cls):
    """Every tool description must be informative and at least 120 characters."""
    for name in cls.TOOL_NAMES:
        doc = inspect.getdoc(getattr(cls, name)) or ""
        assert len(doc) >= 120, f"Tool {name} description too short ({len(doc)} chars)"


def test_search_and_slots(db):
    inv = InventoryTools(db)
    items = inv.search_equipment("SEM")["equipment"]
    assert len(items) == 1
    assert items[0]["equipment_id"] == 1
    assert items[0]["min_safety_level"] == 3

    # Available slots for SEM
    slots = inv.get_available_slots(1)["slots"]
    assert len(slots) == 2

    # Empty search query handling
    assert inv.search_equipment("   ")["error"] == "empty_query"


def test_safety_policy_enforcement(db):
    """Researcher Arjun (Safety Level 1) cannot book SEM (requires Safety Level 3)."""
    arjun = BookingDeskTools(db, "22IT017")
    eligibility = arjun.check_eligibility(equipment_id=1, slot_id=1)
    assert eligibility["eligible"] is False
    assert "Safety Level 1 insufficient" in eligibility["reason"]


def test_suspended_researcher_refused(db):
    """Suspended researcher cannot book anything."""
    rahul = BookingDeskTools(db, "22ME009")
    eligibility = rahul.check_eligibility(equipment_id=3, slot_id=5)
    assert eligibility["eligible"] is False
    assert "suspended" in eligibility["reason"]


def test_booking_refuses_when_policy_forbids_even_if_model_skips_check(db):
    """Even if model calls book_slot directly without check_eligibility, database rule rejects it."""
    arjun = BookingDeskTools(db, "22IT017")
    res = arjun.book_slot(equipment_id=1, slot_id=1)
    assert res["error"] == "booking_refused"
    assert db.count("booking") == 1      # Only initial seed booking remains


def test_booking_quota_limit(db):
    """Divya already has 1 active booking. Max allowed is 2."""
    divya = BookingDeskTools(db, "22EC031")
    # Book her second allowed slot (GPU cluster slot 5)
    res = divya.book_slot(equipment_id=3, slot_id=5)
    assert res["status"] == "booked"

    # Try booking a 3rd slot -> rejected by policy
    res3 = divya.book_slot(equipment_id=3, slot_id=6)
    assert res3["error"] == "booking_refused"
    assert "limit of 2 active bookings" in res3["reason"]


def test_reserving_twice_is_safe_and_idempotent(db):
    priya = BookingDeskTools(db, "22CS045")
    first = priya.book_slot(equipment_id=1, slot_id=1)
    assert first["status"] == "booked"

    second = priya.book_slot(equipment_id=1, slot_id=1)
    assert second["status"] == "already_booked"
    assert first["booking_id"] == second["booking_id"]


def test_slot_clash_prevented(db):
    """Slot 1 cannot be booked by two different researchers."""
    priya = BookingDeskTools(db, "22CS045")
    assert priya.book_slot(equipment_id=1, slot_id=1)["status"] == "booked"

    # Another eligible researcher tries to book the same slot
    db.conn.execute("UPDATE researcher SET safety_level = 3 WHERE roll_no = '22EC031'")
    divya = BookingDeskTools(db, "22EC031")
    res = divya.book_slot(equipment_id=1, slot_id=1)
    assert res["error"] == "booking_refused"
    assert "already booked" in res["reason"]


def test_cancel_booking_releases_slot(db):
    priya = BookingDeskTools(db, "22CS045")
    book_res = priya.book_slot(equipment_id=1, slot_id=1)
    assert book_res["status"] == "booked"
    booking_id = book_res["booking_id"]

    cancel_res = priya.cancel_booking(booking_id)
    assert cancel_res["status"] == "cancelled"

    # Repeating cancel is safe
    cancel_repeat = priya.cancel_booking(booking_id)
    assert cancel_repeat["status"] == "already_cancelled"

    # Slot is unbooked again
    slot = db.get_slot(1)
    assert slot["is_booked"] == 0


def test_notification_deduplication(db):
    priya = BookingDeskTools(db, "22CS045")
    n1 = priya.notify_researcher("Slot 1 confirmed.")
    n2 = priya.notify_researcher("Slot 1 confirmed.")
    assert n1["notification_id"] == n2["notification_id"]
    assert n2["duplicate"] is True


def test_booking_desk_cannot_act_for_arbitrary_researcher(db):
    """Least privilege: the desk tool functions are bound to self.roll_no and do not accept a roll_no argument."""
    params = {n: list(inspect.signature(getattr(BookingDeskTools, n)).parameters) for n in BookingDeskTools.TOOL_NAMES}
    assert all("roll_no" not in p for p in params.values())
