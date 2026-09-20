"""Tests for Supervisor and Specialist multi-agent coordination."""
from app.agents import SupervisorTools, run_specialist, run_tool
from app.providers import ModelTurn, ScriptedProvider, ToolCall, demo_providers
from app.tools.lab_tools import InventoryTools


def test_supervisor_has_only_delegation_tools(db):
    tools = SupervisorTools(db, demo_providers(), "22CS045")
    assert set(tools.functions()) == {"ask_inventory", "ask_booking_desk"}
    assert set(tools.DELEGATES) == set(tools.TOOL_NAMES)


def test_inventory_specialist_answers_query(db):
    tools = SupervisorTools(db, demo_providers(), "22CS045")
    result, replayed = run_tool(tools, db, "k1", "ask_inventory",
                                {"question": "Find Scanning Electron Microscope (SEM) and list available slots for 2026-09-21."})
    assert result["agent"] == "inventory"
    assert "search_equipment" in result["tools_used"]
    assert "Central Lab 101" in result["answer"]
    assert not replayed


def test_booking_desk_books_and_notifies(db):
    tools = SupervisorTools(db, demo_providers(), "22CS045")
    result, _ = run_tool(tools, db, "k2", "ask_booking_desk",
                         {"request": "Check eligibility and book slot 1 for equipment 1 (SEM) on 2026-09-21, then notify the researcher."})
    assert "book_slot" in result["tools_used"]
    assert "notify_researcher" in result["tools_used"]
    assert db.count("booking") == 2
    assert db.count("notification") == 1


def test_repeated_delegation_with_same_key_is_idempotent(db):
    tools = SupervisorTools(db, demo_providers(), "22CS045")
    args = {"request": "Check eligibility and book slot 1 for equipment 1 (SEM) on 2026-09-21, then notify the researcher."}
    run_tool(tools, db, "same-key", "ask_booking_desk", args)
    run_tool(tools, db, "same-key", "ask_booking_desk", args)
    # Bookings remain 2, notifications remain 1, idempotency records 2
    assert db.count("booking") == 2
    assert db.count("notification") == 1
    assert db.count("idempotency") == 2


def test_bad_delegation_arguments_rejected(db):
    tools = SupervisorTools(db, demo_providers(), "22CS045")
    result, _ = run_tool(tools, db, "k3", "ask_booking_desk", {"request": "   "})
    assert result["error"] == "invalid_arguments"


def test_looping_specialist_terminates_at_limit(db):
    looping = ScriptedProvider(
        [ModelTurn(text=None, tool_calls=[ToolCall("search_equipment", {"text": "GPU"})])], loop=True
    )
    result = run_specialist("inventory", "sys", InventoryTools(db), db=db, provider=looping, task="loop", parent_key="k")
    assert result["error"] == "specialist_step_limit"


def test_specialists_see_only_their_assigned_task(db):
    providers = demo_providers()
    tools = SupervisorTools(db, providers, "22CS045")
    run_tool(tools, db, "k4", "ask_inventory", {"question": "Check SEM equipment details."})
    assert len(providers["inventory"].calls) > 0
    assert len(providers["booking_desk"].calls) == 0
