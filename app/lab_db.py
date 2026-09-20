"""lab.db: Campus Lab Equipment, slots, researchers, bookings, and policies."""
import json
import time
from collections.abc import Callable
from pathlib import Path

from app.db import connect, transaction

SCHEMA = Path(__file__).resolve().parent.parent / "schema" / "lab.sql"


class LabDb:
    def __init__(self, path: str = ":memory:", clock: Callable[[], float] = time.time):
        self.conn = connect(path)
        self.clock = clock

    def transaction(self):
        return transaction(self.conn)

    def migrate(self) -> None:
        self.conn.executescript(SCHEMA.read_text())
        if self.conn.execute("SELECT count(*) FROM researcher").fetchone()[0]:
            return
        with self.transaction() as c:
            c.executemany("INSERT INTO policy (name, value) VALUES (?, ?)", [
                ("max_active_bookings", 2),
                ("min_safety_level_req", 1),
                ("advance_booking_days", 7)
            ])
            c.executemany("INSERT INTO researcher (id, roll_no, name, dept, safety_level, is_suspended) VALUES (?, ?, ?, ?, ?, ?)", [
                (1, "22CS045", "Priya Raman", "Computer Science", 3, 0),
                (2, "22IT017", "Arjun Kumar", "Information Tech", 1, 0),
                (3, "22EC031", "Divya Sekar", "Electronics", 2, 0),
                (4, "22ME009", "Rahul Roy", "Mechanical Engg", 1, 1)
            ])
            c.executemany("INSERT INTO equipment (id, name, lab_room, min_safety_level, total_slots, status) VALUES (?, ?, ?, ?, ?, ?)", [
                (1, "Scanning Electron Microscope (SEM)", "Central Lab 101", 3, 2, "operational"),
                (2, "Digital Phosphor Oscilloscope 4GHz", "Circuits Lab 204", 2, 2, "operational"),
                (3, "High-Performance GPU Cluster (Node A)", "AI Lab 302", 1, 3, "operational"),
                (4, "UV-Vis Spectrophotometer", "Materials Lab 105", 2, 2, "operational"),
                (5, "Cleanroom Photolithography Unit", "Cleanroom 110", 3, 1, "maintenance")
            ])
            c.executemany("INSERT INTO slot (id, equipment_id, slot_date, slot_name, is_booked, booked_by_researcher_id, version) VALUES (?, ?, ?, ?, ?, ?, ?)", [
                (1, 1, "2026-09-21", "09:00 - 12:00", 0, None, 0),
                (2, 1, "2026-09-21", "14:00 - 17:00", 0, None, 0),
                (3, 2, "2026-09-21", "10:00 - 12:00", 1, 3, 1),    # Divya already holds this
                (4, 2, "2026-09-21", "14:00 - 16:00", 0, None, 0),
                (5, 3, "2026-09-21", "09:00 - 13:00", 0, None, 0),
                (6, 3, "2026-09-21", "13:00 - 17:00", 0, None, 0),
                (7, 3, "2026-09-21", "17:00 - 21:00", 0, None, 0),
                (8, 4, "2026-09-21", "11:00 - 13:00", 0, None, 0),
                (9, 4, "2026-09-21", "15:00 - 17:00", 0, None, 0),
                (10, 5, "2026-09-21", "10:00 - 14:00", 0, None, 0)
            ])
            # Initial active booking for Divya on slot 3
            c.execute("INSERT INTO booking (id, researcher_id, equipment_id, slot_id, status, created_at) VALUES (1, 3, 2, 3, 'confirmed', ?)",
                      (self.clock(),))

    # ------------------------------------------------------------------ reads

    def get_researcher(self, roll_no: str) -> dict | None:
        r = self.conn.execute("SELECT * FROM researcher WHERE roll_no = ?", (roll_no,)).fetchone()
        return dict(r) if r else None

    def policy(self, name: str) -> int:
        row = self.conn.execute("SELECT value FROM policy WHERE name = ?", (name,)).fetchone()
        if not row:
            raise KeyError(f"Unknown policy: {name}")
        return row[0]

    def active_bookings(self, researcher_id: int) -> list[dict]:
        rows = self.conn.execute(
            """SELECT b.id AS booking_id, b.slot_id, e.id AS equipment_id, e.name AS equipment_name,
                      s.slot_date, s.slot_name, b.status
                 FROM booking b
                 JOIN equipment e ON e.id = b.equipment_id
                 JOIN slot s ON s.id = b.slot_id
                WHERE b.researcher_id = ? AND b.status = 'confirmed'
                ORDER BY b.id""", (researcher_id,)).fetchall()
        return [dict(r) for r in rows]

    def search_equipment(self, text: str, limit: int = 5) -> list[dict]:
        like = f"%{text.strip()}%"
        rows = self.conn.execute(
            """SELECT id, name, lab_room, min_safety_level, total_slots, status
                 FROM equipment
                WHERE name LIKE ? OR lab_room LIKE ?
                ORDER BY id LIMIT ?""", (like, like, limit)).fetchall()
        return [dict(r) for r in rows]

    def get_equipment(self, equipment_id: int) -> dict | None:
        r = self.conn.execute("SELECT * FROM equipment WHERE id = ?", (equipment_id,)).fetchone()
        return dict(r) if r else None

    def get_available_slots(self, equipment_id: int, slot_date: str = "2026-09-21") -> list[dict]:
        rows = self.conn.execute(
            """SELECT s.id AS slot_id, s.equipment_id, s.slot_date, s.slot_name, s.is_booked,
                      e.name AS equipment_name, e.status AS equipment_status
                 FROM slot s
                 JOIN equipment e ON e.id = s.equipment_id
                WHERE s.equipment_id = ? AND s.slot_date = ? AND s.is_booked = 0
                ORDER BY s.id""", (equipment_id, slot_date)).fetchall()
        return [dict(r) for r in rows]

    def get_slot(self, slot_id: int) -> dict | None:
        r = self.conn.execute(
            """SELECT s.id AS slot_id, s.equipment_id, s.slot_date, s.slot_name, s.is_booked,
                      s.booked_by_researcher_id, s.version, e.name AS equipment_name,
                      e.min_safety_level, e.status AS equipment_status
                 FROM slot s
                 JOIN equipment e ON e.id = s.equipment_id
                WHERE s.id = ?""", (slot_id,)).fetchone()
        return dict(r) if r else None

    def check_eligibility(self, researcher_id: int, equipment_id: int, slot_id: int) -> tuple[bool, str]:
        """Enforce business rules stored in data (Day 2/3 requirement).

        Checks:
        1. Researcher exists and is not suspended.
        2. Researcher active booking count < policy 'max_active_bookings'.
        3. Equipment is operational (not under maintenance).
        4. Researcher safety_level >= equipment min_safety_level.
        5. Slot belongs to the equipment and is not already booked by someone else.
        """
        researcher = self.conn.execute("SELECT * FROM researcher WHERE id = ?", (researcher_id,)).fetchone()
        if not researcher:
            return False, "Researcher not found."
        if researcher["is_suspended"]:
            return False, f"Researcher {researcher['roll_no']} is currently suspended from lab privileges."

        # Rule in data: Max active bookings
        max_allowed = self.policy("max_active_bookings")
        current_count = len(self.active_bookings(researcher_id))
        if current_count >= max_allowed:
            return False, f"Researcher has reached the limit of {max_allowed} active bookings."

        equipment = self.get_equipment(equipment_id)
        if not equipment:
            return False, f"Equipment ID {equipment_id} not found."
        if equipment["status"] != "operational":
            return False, f"{equipment['name']} is currently under {equipment['status']}."

        # Rule in data: Safety certification level
        if self.policy("min_safety_level_req"):
            if researcher["safety_level"] < equipment["min_safety_level"]:
                return False, (f"Safety Level {researcher['safety_level']} insufficient. "
                               f"{equipment['name']} requires Safety Level {equipment['min_safety_level']}.")

        slot = self.get_slot(slot_id)
        if not slot:
            return False, f"Slot ID {slot_id} not found."
        if slot["equipment_id"] != equipment_id:
            return False, f"Slot {slot_id} does not belong to equipment {equipment_id}."
        if slot["is_booked"]:
            if slot["booked_by_researcher_id"] == researcher_id:
                return True, "Slot already booked by this researcher."
            return False, f"Slot {slot['slot_name']} on {slot['slot_date']} is already booked by another researcher."

        return True, "Eligible"

    def count(self, table: str) -> int:
        assert table.isidentifier()
        return self.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    # ------------------------------------------------------------------ safe writes (Day 3)

    def book_slot(self, researcher_id: int, equipment_id: int, slot_id: int) -> dict:
        """Atomically books a slot with optimistic versioning. Safe to repeat."""
        eligible, reason = self.check_eligibility(researcher_id, equipment_id, slot_id)
        if not eligible:
            return {"status": "ineligible", "reason": reason}

        with self.transaction() as c:
            # Check if this researcher already booked it (idempotent repeat)
            existing = c.execute(
                "SELECT id FROM booking WHERE researcher_id = ? AND equipment_id = ? AND slot_id = ? AND status = 'confirmed'",
                (researcher_id, equipment_id, slot_id)).fetchone()
            if existing:
                return {"status": "already_booked", "booking_id": existing["id"], "slot_id": slot_id}

            slot = c.execute("SELECT version, is_booked FROM slot WHERE id = ?", (slot_id,)).fetchone()
            if not slot or slot["is_booked"]:
                return {"status": "slot_taken", "reason": "Slot is already taken by another researcher."}

            version = slot["version"]
            # Atomic update with version check
            took = c.execute(
                """UPDATE slot
                      SET is_booked = 1, booked_by_researcher_id = ?, version = version + 1
                    WHERE id = ? AND is_booked = 0 AND version = ?""",
                (researcher_id, slot_id, version)).rowcount

            if not took:
                return {"status": "slot_taken", "reason": "Lost race for this slot. Please choose another."}

            cur = c.execute(
                "INSERT INTO booking (researcher_id, equipment_id, slot_id, status, created_at) VALUES (?, ?, ?, 'confirmed', ?)",
                (researcher_id, equipment_id, slot_id, self.clock()))
            booking_id = cur.lastrowid
            return {"status": "booked", "booking_id": booking_id, "slot_id": slot_id}

    def cancel_booking(self, researcher_id: int, booking_id: int) -> dict:
        """Cancels a booking and releases the slot atomically. Safe to repeat."""
        with self.transaction() as c:
            b = c.execute("SELECT * FROM booking WHERE id = ? AND researcher_id = ?", (booking_id, researcher_id)).fetchone()
            if not b:
                return {"status": "not_found", "reason": "Booking not found or belongs to another researcher."}
            if b["status"] == "cancelled":
                return {"status": "already_cancelled", "booking_id": booking_id}

            c.execute("UPDATE booking SET status = 'cancelled' WHERE id = ?", (booking_id,))
            c.execute("UPDATE slot SET is_booked = 0, booked_by_researcher_id = NULL, version = version + 1 WHERE id = ?",
                      (b["slot_id"],))
            return {"status": "cancelled", "booking_id": booking_id, "slot_id": b["slot_id"]}

    def record_notification(self, roll_no: str, message: str, dedupe_key: str) -> tuple[int, bool]:
        """Records notification with deduplication. Returns (notification_id, is_fresh)."""
        cur = self.conn.execute(
            "INSERT INTO notification (roll_no, message, dedupe_key, created_at) VALUES (?, ?, ?, ?)"
            " ON CONFLICT (dedupe_key) DO NOTHING", (roll_no, message, dedupe_key, self.clock()))
        if cur.rowcount == 1:
            return cur.lastrowid, True
        return self.conn.execute("SELECT id FROM notification WHERE dedupe_key = ?", (dedupe_key,)).fetchone()[0], False

    def once(self, key: str, tool_name: str, effect: Callable[[], dict]) -> tuple[dict, bool]:
        """Run a side effect at most once per idempotency key; the effect and its key commit together."""
        with self.transaction() as c:
            row = c.execute("SELECT result FROM idempotency WHERE key = ?", (key,)).fetchone()
            if row is not None:
                return json.loads(row["result"]), False
            result = effect()
            c.execute("INSERT INTO idempotency (key, tool_name, result, created_at) VALUES (?, ?, ?, ?)",
                      (key, tool_name, json.dumps(result, default=str), self.clock()))
            return result, True
