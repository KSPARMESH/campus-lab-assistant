"""End-to-end tests: queue, leasing, multi-agent execution, crash recovery, cancellation, retry, and concurrency."""
import threading
import pytest

from app.providers import AgentError, demo_providers
from app.worker import Worker
from tests.conftest import SimulatedCrash

PRIYA_QUESTION = "Is Scanning Electron Microscope (SEM) available on 2026-09-21? If it is, book slot 1 for me and send a confirmation."


def ask(store, roll_no: str, text: str):
    thread = store.create_thread(roll_no)
    return thread, store.enqueue(thread, text, "mock")


def test_question_goes_all_the_way_through(store, db):
    thread, run_id = ask(store, "22CS045", PRIYA_QUESTION)
    worker = Worker(store, db, demo_providers(), worker_id="w1")
    done = worker.run_until_idle()
    assert done == [(run_id, "succeeded")]

    run = store.get_run(run_id)
    assert run["status"] == "succeeded"
    tool_steps = [s["tool_name"] for s in run["steps"] if s["kind"] == "tool"]
    assert "ask_inventory" in tool_steps
    assert "ask_booking_desk" in tool_steps

    history = store.load_history(thread)
    assert "Slot 1 (09:00 - 12:00) has been confirmed and booked" in history[-1]["text"]
    assert db.count("booking") == 2
    assert db.count("notification") == 1


def test_policy_refusal_is_a_normal_answer(store, db):
    thread, run_id = ask(store, "22IT017", "Can I book the Scanning Electron Microscope (SEM) slot 2?")
    Worker(store, db, demo_providers(), worker_id="w1").run_until_idle()

    run = store.get_run(run_id)
    assert run["status"] == "succeeded"
    history = store.load_history(thread)
    assert "Safety Level" in history[-1]["text"]
    assert db.count("booking") == 1      # Refused, no new booking


def test_crash_inside_specialist_replays_safely_without_duplicates(store, db, clock):
    """Crash drill: Worker A dies right after writing the booking. Worker B recovers the run."""
    _, run_id = ask(store, "22CS045", PRIYA_QUESTION)
    real_once = db.once

    def once_then_die(key, tool_name, effect):
        result = real_once(key, tool_name, effect)
        if tool_name == "book_slot":
            raise SimulatedCrash()
        return result

    db.once = once_then_die
    with pytest.raises(SimulatedCrash):
        Worker(store, db, demo_providers(), worker_id="worker-A", lease_seconds=30).run_once()

    db.once = real_once
    # Verify booking exists, but run is still incomplete
    assert db.count("booking") == 2
    assert store.get_run(run_id)["status"] == "running"

    # Simulate lease expiry
    clock.advance(31)

    # Worker B claims and finishes the run
    worker_b = Worker(store, db, demo_providers(), worker_id="worker-B", lease_seconds=30)
    done = worker_b.run_until_idle()
    assert done == [(run_id, "succeeded")]

    # Crucial assertion: no duplicate booking, no duplicate notification
    assert db.count("booking") == 2
    assert db.count("notification") == 1
    assert store.get_run(run_id)["attempts"] == 2


def test_asking_twice_still_one_booking(store, db):
    for _ in range(2):
        ask(store, "22CS045", PRIYA_QUESTION)
    Worker(store, db, demo_providers(), worker_id="w1").run_until_idle()
    assert db.count("booking") == 2
    assert db.count("notification") == 1


def test_external_cancellation(store, db):
    """A queued run is cancelled immediately when requested."""
    _, run_id = ask(store, "22CS045", PRIYA_QUESTION)
    status = store.request_cancel(run_id)
    assert status == "cancelled"

    # Worker picks up nothing
    assert Worker(store, db, demo_providers(), worker_id="w1").run_once() is None
    assert store.get_run(run_id)["status"] == "cancelled"


def test_retry_with_backoff_and_dead_letter(store, db, clock):
    """Higher grade requirement: retry with backoff and eventual dead-lettering."""
    thread = store.create_thread("22CS045")
    run_id = store.enqueue(thread, "question", "mock", max_attempts=2)

    # Attempt 1: Transient error
    claimed = store.claim_next("w1", lease_seconds=60)
    assert claimed.run_id == run_id
    new_status = store.fail_attempt(run_id, "w1", "network_timeout", retryable=True, backoff_seconds=10)
    assert new_status == "queued"

    # Not claimable before backoff expires
    assert store.claim_next("w2", lease_seconds=60) is None

    # Advance past backoff
    clock.advance(11)
    claimed2 = store.claim_next("w2", lease_seconds=60)
    assert claimed2.run_id == run_id
    assert claimed2.attempts == 2

    # Attempt 2 fails (max_attempts reached) -> dead-lettered
    final_status = store.fail_attempt(run_id, "w2", "network_timeout", retryable=True, backoff_seconds=10)
    assert final_status == "dead"
    assert store.get_run(run_id)["status"] == "dead"


def test_concurrent_booking_race_prevention(db):
    """Higher grade requirement: multi-threaded race test.
    Two threads attempt to book the same available slot simultaneously. Exactly one succeeds!
    """
    results = []

    def try_book(researcher_roll: str):
        from app.tools.lab_tools import BookingDeskTools
        desk = BookingDeskTools(db, researcher_roll)
        res = desk.book_slot(equipment_id=1, slot_id=2)
        results.append(res)

    # Update both to safety level 3 so both qualify
    db.conn.execute("UPDATE researcher SET safety_level = 3 WHERE roll_no IN ('22CS045', '22IT017')")

    t1 = threading.Thread(target=try_book, args=("22CS045",))
    t2 = threading.Thread(target=try_book, args=("22IT017",))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    statuses = [r.get("status") for r in results]
    errors = [r.get("error") for r in results]

    # Exactly one succeeded in booking
    assert statuses.count("booked") == 1
    # The other received booking_refused (slot clash detected by DB)
    assert errors.count("booking_refused") == 1
    assert db.get_slot(2)["is_booked"] == 1
