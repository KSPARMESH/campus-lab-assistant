"""The campus lab equipment tools, split between two specialist agents.
Descriptions are prompts that clearly state when to use, when not to use, and what data changes.
"""
from datetime import datetime, timezone

from app.idempotency import notification_dedupe_key
from app.lab_db import LabDb
from app.tools.dispatch import dispatch


class Toolset:
    SIDE_EFFECTS: tuple[str, ...] = ()     # run through LabDb.once with an idempotency key (Day 3)
    DELEGATES: tuple[str, ...] = ()        # hand work to another agent (Day 4)
    TOOL_NAMES: tuple[str, ...] = ()

    def functions(self) -> dict:
        return {n: getattr(self, n) for n in self.TOOL_NAMES}

    def call(self, name: str, args: dict) -> dict:
        return dispatch(self.functions(), name, args)


class InventoryTools(Toolset):
    """Read-only specialist toolset. The inventory agent can look and search, never book or modify."""

    TOOL_NAMES = ("search_equipment", "get_available_slots", "get_equipment_details")

    def __init__(self, db: LabDb):
        self.db = db

    def search_equipment(self, text: str) -> dict:
        """Find scientific instruments and computing clusters in the campus labs by name or lab room.

        Use for "do you have ...", "where is the SEM", "show available microscopes or clusters".
        Returns matching equipment and their minimum safety certification levels.
        Read-only: changes nothing. To book a slot, that is the booking desk's job, not this tool.

        Args:
            text: Keywords matching equipment name or lab room, e.g. "microscope", "GPU", "Central Lab".

        Returns:
            {"equipment": [{"equipment_id", "name", "lab_room", "min_safety_level", "total_slots", "status"}]}.
        """
        if not text.strip():
            return {"error": "empty_query", "hint": "Pass keywords matching equipment name or room."}
        items = self.db.search_equipment(text)
        return {
            "equipment": [{
                "equipment_id": eq["id"],
                "name": eq["name"],
                "lab_room": eq["lab_room"],
                "min_safety_level": eq["min_safety_level"],
                "total_slots": eq["total_slots"],
                "status": eq["status"]
            } for eq in items]
        }

    def get_available_slots(self, equipment_id: int, slot_date: str = "2026-09-21") -> dict:
        """Get all currently available (unbooked) time slots for a specific equipment on a date.

        Use when you already have an equipment_id and want to see what time slots are open.
        Read-only: changes nothing.

        Args:
            equipment_id: Integer id of the equipment.
            slot_date: ISO date string, e.g. "2026-09-21".

        Returns:
            {"equipment_id", "slot_date", "slots": [{"slot_id", "slot_name"}]}.
        """
        eq = self.db.get_equipment(equipment_id)
        if eq is None:
            return {"error": "unknown_equipment", "hint": "Use search_equipment to find valid equipment_id."}
        if eq["status"] != "operational":
            return {"error": "equipment_unavailable", "hint": f"{eq['name']} is currently under {eq['status']}."}
        slots = self.db.get_available_slots(equipment_id, slot_date)
        return {
            "equipment_id": equipment_id,
            "equipment_name": eq["name"],
            "slot_date": slot_date,
            "slots": [{"slot_id": s["slot_id"], "slot_name": s["slot_name"]} for s in slots]
        }

    def get_equipment_details(self, equipment_id: int) -> dict:
        """Get full specifications and status of one piece of equipment.

        Use to verify safety certification prerequisites and room location before proceeding.
        Read-only: changes nothing.

        Args:
            equipment_id: Integer id of the equipment.

        Returns:
            {"equipment_id", "name", "lab_room", "min_safety_level", "total_slots", "status"}.
        """
        eq = self.db.get_equipment(equipment_id)
        if eq is None:
            return {"error": "unknown_equipment", "hint": "Use search_equipment to find valid equipment_id."}
        return {
            "equipment_id": eq["id"],
            "name": eq["name"],
            "lab_room": eq["lab_room"],
            "min_safety_level": eq["min_safety_level"],
            "total_slots": eq["total_slots"],
            "status": eq["status"]
        }


class BookingDeskTools(Toolset):
    """The booking desk specialist, bound to ONE researcher roll number.
    The model cannot act on behalf of a different roll number.
    """

    TOOL_NAMES = ("get_researcher_profile", "check_eligibility", "book_slot", "cancel_booking", "notify_researcher")
    SIDE_EFFECTS = ("book_slot", "cancel_booking", "notify_researcher")

    def __init__(self, db: LabDb, roll_no: str, clock=lambda: datetime.now(timezone.utc)):
        self.db, self.roll_no, self.clock = db, roll_no, clock

    def _researcher(self) -> dict:
        r = self.db.get_researcher(self.roll_no)
        if r is None:
            raise LookupError(f"researcher {self.roll_no} not found")
        return r

    def get_researcher_profile(self) -> dict:
        """Get the current researcher's lab record: safety certification level, department, active bookings.

        Use for "what is my safety level", "what equipment have I booked".
        Read-only: changes nothing.

        Returns:
            {"roll_no", "name", "dept", "safety_level", "is_suspended", "active_bookings": [...]}.
        """
        r = self._researcher()
        return {
            "roll_no": r["roll_no"],
            "name": r["name"],
            "dept": r["dept"],
            "safety_level": r["safety_level"],
            "is_suspended": bool(r["is_suspended"]),
            "active_bookings": self.db.active_bookings(r["id"])
        }

    def check_eligibility(self, equipment_id: int, slot_id: int) -> dict:
        """Evaluate whether the researcher satisfies all data-driven lab policies to book this slot.

        Use BEFORE calling book_slot, and when researcher asks if they can reserve a specific instrument.
        Checks:
        - Researcher suspension status.
        - Active bookings count vs policy limit ('max_active_bookings').
        - Researcher safety level vs equipment required min_safety_level.
        - Operational status of equipment.
        - Slot vacancy.
        Never decide policy in prompts; this tool checks the database policy table directly.
        Read-only: changes nothing.

        Returns:
            {"eligible": bool, "reason": str}.
        """
        r = self._researcher()
        ok, reason = self.db.check_eligibility(r["id"], equipment_id, slot_id)
        return {"eligible": ok, "reason": reason}

    def book_slot(self, equipment_id: int, slot_id: int) -> dict:
        """Atomically reserve a lab equipment slot for the current researcher.
        CHANGES DATA: reserves the slot and creates a confirmed booking record.

        Use only after confirming with check_eligibility that the researcher is eligible.
        Business rules in data are enforced in code even if the model skipped checking.
        Repeating the call for the same slot is safe (idempotent) and returns the existing booking.

        Args:
            equipment_id: Integer id of the equipment.
            slot_id: Integer id of the slot to book.

        Returns:
            {"status": "booked" | "already_booked", "booking_id": int, "slot_id": int} or
            {"error": "booking_refused", "reason": str}.
        """
        r = self._researcher()
        res = self.db.book_slot(r["id"], equipment_id, slot_id)
        if res.get("status") in ("booked", "already_booked"):
            return {
                "booking_id": res["booking_id"],
                "equipment_id": equipment_id,
                "slot_id": slot_id,
                "status": res["status"]
            }
        return {"error": "booking_refused", "reason": res.get("reason", "Ineligible to book.")}

    def cancel_booking(self, booking_id: int) -> dict:
        """Cancel an existing confirmed booking and release the slot back to the pool.
        CHANGES DATA: marks booking cancelled and makes the slot available again.

        Use when the researcher explicitly requests to cancel their booking.
        Safe to repeat: repeating returns already_cancelled.

        Args:
            booking_id: Integer id of the booking.

        Returns:
            {"booking_id": int, "status": "cancelled" | "already_cancelled"} or error.
        """
        r = self._researcher()
        res = self.db.cancel_booking(r["id"], booking_id)
        if res.get("status") in ("cancelled", "already_cancelled"):
            return res
        return {"error": "cancel_failed", "reason": res.get("reason", "Could not cancel booking.")}

    def notify_researcher(self, message: str) -> dict:
        """Send the current researcher a confirmation text/notification.
        CHANGES DATA: records an outgoing message in the notification log.

        Use to confirm a completed booking or cancellation. Identical messages to the same
        researcher on the same day are deduplicated automatically.
        Never use this to answer questions; reply in chat instead.

        Args:
            message: 1 to 160 characters.

        Returns:
            {"notification_id": int, "status": "queued", "duplicate": bool}.
        """
        if not message.strip() or len(message) > 160:
            return {"error": "invalid_message", "hint": "Message must be 1 to 160 characters."}
        key = notification_dedupe_key(self.roll_no, message, self.clock().date())
        nid, fresh = self.db.record_notification(self.roll_no, message, key)
        return {"notification_id": nid, "status": "queued", "duplicate": not fresh}
