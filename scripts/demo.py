"""The whole project in one command:
    python -m scripts.demo            # scripted models: no key, no quota, deterministic output
    python -m scripts.demo --real     # the same questions with live Gemini API
    python -m scripts.demo --crash    # kill worker right after booking, resume, verify no duplicates

Uses throwaway SQLite databases in a temporary folder.
"""
import argparse
import os
import tempfile

from scripts._term import CYAN, DIM, GREEN, RED, RESET, print_step

QUESTIONS = [
    ("22CS045", "Is Scanning Electron Microscope (SEM) available on 2026-09-21? If it is, book slot 1 for me and send a confirmation."),
    ("22IT017", "Can I book the Scanning Electron Microscope (SEM) slot 2?"),
]


class Crash(BaseException):
    """Simulates an abrupt process termination (e.g. SIGKILL / power failure)."""


def counts(db) -> str:
    return (f"bookings {db.count('booking')}   notifications {db.count('notification')}"
            f"   idempotency keys {db.count('idempotency')}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--real", action="store_true", help="Run against real Gemini LLM")
    p.add_argument("--crash", action="store_true", help="Simulate crash and replay recovery")
    a = p.parse_args()

    tmp = tempfile.mkdtemp(prefix="lab-demo-")
    os.environ["AGENT_DB"] = os.path.join(tmp, "agent.db")
    os.environ["LAB_DB"] = os.path.join(tmp, "lab.db")

    from app.config import make_providers, open_stores
    from app.worker import Worker

    store, db = open_stores()
    providers = make_providers(mock=not a.real)
    print(f"{DIM}databases in {tmp}   model: {providers['supervisor'].model}{RESET}")
    print(f"{DIM}before: {counts(db)}{RESET}\n")

    questions = QUESTIONS[:1] if a.crash else QUESTIONS
    for roll_no, text in questions:
        thread = store.create_thread(roll_no)
        run_id = store.enqueue(thread, text, providers["supervisor"].model)
        print(f"{CYAN}{roll_no}>{RESET} {text}")

        if a.crash:
            real_once = db.once

            def once_then_die(key, tool_name, effect):
                result = real_once(key, tool_name, effect)
                if tool_name == "book_slot":
                    raise Crash()        # booking and idempotency key committed; worker dies before completing
                return result

            db.once = once_then_die
            try:
                Worker(store, db, providers, worker_id="worker-A", lease_seconds=60, on_step=print_step).run_once()
            except Crash:
                db.once = real_once
                print(f"\n  {RED}worker-A died right after booking the slot{RESET}")
                print(f"  {DIM}{counts(db)}; run is '{store.get_run(run_id)['status']}'{RESET}")
                store.clock = lambda: __import__('time').time() + 61      # simulate lease expiry
                print(f"  {DIM}...lease expires, worker-B reclaims the run{RESET}\n")
            Worker(store, db, providers, worker_id="worker-B", lease_seconds=60, on_step=print_step).run_until_idle()
        else:
            Worker(store, db, providers, worker_id="demo-worker", on_step=print_step).run_until_idle()

        run = store.get_run(run_id)
        colour = GREEN if run["status"] == "succeeded" else RED
        reply = store.load_history(thread)[-1]["text"] if run["status"] == "succeeded" else run["error_code"]
        print(f"{colour}assistant>{RESET} {reply}")
        print(f"{DIM}run {run_id[:8]} {run['status']} after {run['attempts']} attempt(s), "
              f"{run['tokens_in']}+{run['tokens_out']} supervisor tokens{RESET}\n")

    print(f"after:  {counts(db)}")
    if a.crash:
        ok = db.count("booking") == 2 and db.count("notification") == 1      # seed data has 1 booking
        print(f"{GREEN}PASS: one new booking, one notification{RESET}" if ok else f"{RED}FAIL: duplicates detected{RESET}")


if __name__ == "__main__":
    main()
