"""Multi-agent system: Supervisor and Specialist agents for Campus Lab Assistant.

    researcher ──▶ supervisor ──ask_inventory────▶ inventory agent (search_equipment, get_available_slots,
                                                                    get_equipment_details)
                              └─ask_booking_desk─▶ booking desk agent (get_researcher_profile, check_eligibility,
                                                                      book_slot, cancel_booking, notify_researcher)

Supervisor coordinates delegations. Specialists maintain least privilege:
- Inventory Specialist has ZERO write tools (read-only).
- Booking Desk Specialist has domain write permissions bound strictly to researcher's roll number.
Idempotency keys are deterministically passed down from supervisor to specialists.
"""
import time
from collections.abc import Callable

from app.idempotency import idempotency_key
from app.lab_db import LabDb
from app.providers import AgentError
from app.tools.lab_tools import BookingDeskTools, InventoryTools, Toolset

SPECIALIST_MAX_STEPS = 6

SUPERVISOR_SYSTEM = """You are the Campus Lab Assistant, talking to the researcher with roll number {roll_no}.
You never search instruments or book slots directly yourself. Always delegate:
- ask_inventory for searching scientific equipment, checking lab rooms, and finding available time slots;
- ask_booking_desk for checking researcher eligibility, booking equipment slots, cancellations, and sending notifications.
Give each specialist a complete, specific request, including equipment_id and slot_id once you know them.
Then answer the researcher concisely, using only what the specialists reported."""

INVENTORY_SYSTEM = """You are the campus lab inventory specialist. Find scientific instruments and computing clusters,
report equipment_id, name, lab room, required min_safety_level, and available slots. You cannot book or modify any slots. Be brief."""

BOOKING_DESK_SYSTEM = """You are the lab booking desk specialist, acting strictly for researcher {roll_no}.
Always call check_eligibility before book_slot. Never invent or bypass policy yourself: report the reasons
the tools give from the database. Confirm a successful booking with notify_researcher. Report what you did, briefly."""


def run_tool(toolset: Toolset, db: LabDb, key: str, name: str, args: dict) -> tuple[dict, bool]:
    """Run one tool call for any agent. Returns (result, replayed). Never raises, except AgentError.

    Side effects run at most once per key; replayed is True when the stored result was returned
    and no new mutation occurred. Delegations hand the key down so child tools derive stable keys.
    """
    try:
        if name in toolset.DELEGATES:
            return toolset.delegate(name, args, key), False
        if name in toolset.SIDE_EFFECTS:
            result, fresh = db.once(key, name, lambda: toolset.call(name, args))
            return result, not fresh
        return toolset.call(name, args), False
    except AgentError:
        raise
    except NotImplementedError:
        return {"error": "not_implemented", "hint": f"{name} is not available yet."}, False
    except Exception as e:
        return {"error": "tool_failed", "hint": f"{name} failed ({type(e).__name__}). Try another way or tell the user."}, False


def run_specialist(agent: str, system: str, toolset: Toolset, *, db: LabDb, provider, task: str,
                   parent_key: str, on_step: Callable[[dict], None] | None = None) -> dict:
    """A specialist's whole agent loop, run inside one tool call of the supervisor."""
    contents = [{"role": "user", "text": task}]
    functions = list(toolset.functions().values())
    used = []
    seq = 0
    while seq < SPECIALIST_MAX_STEPS:
        turn = provider.generate(system, contents, functions)
        seq += 1
        if not turn.tool_calls:
            return {"agent": agent, "answer": turn.text or "", "tools_used": used}
        contents.append({"role": "model", "text": turn.text, "raw": turn.raw,
                         "tool_calls": [{"name": c.name, "args": c.args} for c in turn.tool_calls]})
        for call in turn.tool_calls:
            seq += 1
            key = idempotency_key(parent_key, seq, call.name, call.args)
            started = time.perf_counter()
            result, replayed = run_tool(toolset, db, key, call.name, call.args)
            used.append(call.name)
            if on_step:
                on_step({"agent": agent, "kind": "tool", "tool": call.name, "args": call.args, "result": result,
                         "ok": "error" not in result, "replayed": replayed,
                         "ms": round((time.perf_counter() - started) * 1000)})
            contents.append({"role": "tool", "name": call.name, "result": result})
    return {"agent": agent, "error": "specialist_step_limit", "tools_used": used,
            "hint": "The specialist could not finish within step limit. Tell the researcher to try a simpler request."}


class SupervisorTools(Toolset):
    """The supervisor's only tools are the two specialists."""

    TOOL_NAMES = ("ask_inventory", "ask_booking_desk")
    DELEGATES = ("ask_inventory", "ask_booking_desk")

    def __init__(self, db: LabDb, providers: dict, roll_no: str, on_step=None):
        self.db, self.providers, self.roll_no, self.on_step = db, providers, roll_no, on_step

    def ask_inventory(self, question: str) -> dict:
        """Ask the inventory specialist to search equipment, lab rooms, or available slots.

        Use for "do you have SEM", "is GPU cluster available", "what time slots exist for equipment X".
        Cannot book or alter data.

        Args:
            question: A complete request, e.g. "Find SEM microscope and list available slots for 2026-09-21."

        Returns:
            {"agent": "inventory", "answer": str, "tools_used": [str]}.
        """
        raise RuntimeError("delegations run through delegate()")

    def ask_booking_desk(self, request: str) -> dict:
        """Ask the booking desk specialist to inspect researcher status, check eligibility,
        book slots, cancel bookings, or send notifications. IT CAN CHANGE DATA.

        Use for booking slots, cancellations, and checking researcher limits. Include equipment_id
        and slot_id once known from inventory.

        Args:
            request: A complete instruction, e.g. "Check eligibility and book slot 1 for equipment 1, then notify researcher."

        Returns:
            {"agent": "booking_desk", "answer": str, "tools_used": [str]}.
        """
        raise RuntimeError("delegations run through delegate()")

    def delegate(self, name: str, args: dict, key: str) -> dict:
        bad = self.call_check(name, args)
        if bad:
            return bad
        if self.on_step:
            self.on_step({"agent": "supervisor", "kind": "delegate", "tool": name, "args": args})
        if name == "ask_inventory":
            return run_specialist("inventory", INVENTORY_SYSTEM, InventoryTools(self.db), db=self.db,
                                  provider=self.providers["inventory"], task=args["question"],
                                  parent_key=key, on_step=self.on_step)
        return run_specialist("booking_desk", BOOKING_DESK_SYSTEM.format(roll_no=self.roll_no),
                              BookingDeskTools(self.db, self.roll_no),
                              db=self.db, provider=self.providers["booking_desk"], task=args["request"],
                              parent_key=key, on_step=self.on_step)

    def call_check(self, name: str, args: dict) -> dict | None:
        """Validate delegation arguments."""
        field = "question" if name == "ask_inventory" else "request"
        if set(args) != {field} or not isinstance(args[field], str) or not args[field].strip():
            return {"error": "invalid_arguments", "hint": f"{name} takes one non-empty string: {field}."}
        return None
