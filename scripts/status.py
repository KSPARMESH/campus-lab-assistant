"""Inspect threads, runs, and tool execution history.

    python -m scripts.status [--runs] [--steps <run_id>]
"""
import argparse

from app.config import open_stores
from scripts._term import CYAN, DIM, GREEN, MAGENTA, RED, YELLOW, RESET, short


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--steps", help="Show all steps of a specific run")
    a = p.parse_args()

    store, db = open_stores()
    if a.steps:
        row = store.conn.execute("SELECT id, status, model, attempts FROM run WHERE id LIKE ?", (a.steps + "%",)).fetchone()
        if not row:
            print("Run not found.")
            return
        run_id = row["id"]
        print(f"{CYAN}Run {run_id}{RESET} [{row['status']}] attempts={row['attempts']}")
        steps = store.load_steps(run_id)
        for s in steps:
            if s["kind"] == "model":
                print(f"  {YELLOW}Step {s['seq']} [model]{RESET} {short(s['text'] or s['tool_calls'], 100)}")
            else:
                status = GREEN if s["ok"] else RED
                print(f"  {MAGENTA}Step {s['seq']} [tool: {s['tool_name']}]{RESET} args={short(s['args'], 60)}")
                print(f"    {status}\u2190 result: {short(s['result'], 90)}{RESET}")
        return

    print(f"\n{CYAN}=== RUNS SUMMARY ==={RESET}")
    runs = store.conn.execute(
        "SELECT id, thread_id, status, model, attempts, created_at FROM run ORDER BY created_at DESC LIMIT 10"
    ).fetchall()
    if not runs:
        print("  No runs yet.")
    for r in runs:
        color = GREEN if r["status"] == "succeeded" else (YELLOW if r["status"] in ("queued", "running") else RED)
        print(f"  {color}[{r['status'] polar: <9}]{RESET} run: {r['id'][:8]}  thread: {r['thread_id'][:8]}  attempts: {r['attempts']}")

    print(f"\n{CYAN}=== LAB DATABASE SUMMARY ==={RESET}")
    print(f"  Researchers:      {db.count('researcher')}")
    print(f"  Equipment:        {db.count('equipment')}")
    print(f"  Slots:            {db.count('slot')}")
    print(f"  Bookings:         {db.count('booking')}")
    print(f"  Notifications:    {db.count('notification')}")
    print(f"  Idempotency Keys: {db.count('idempotency')}\n")


if __name__ == "__main__":
    main()
