"""Queue a lab equipment question and wait for the answer.

    python -m scripts.ask --researcher 22CS045 "Is Scanning Electron Microscope (SEM) available?"
"""
import argparse
import time

from app.config import GEMINI_MODEL, open_stores
from scripts._term import CYAN, DIM, GREEN, RED, RESET


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("text", help="Question or request for the Lab Assistant")
    p.add_argument("--researcher", default="22CS045", help="Researcher roll number")
    p.add_argument("--thread", help="Existing thread ID (optional)")
    a = p.parse_args()

    store, _ = open_stores()
    thread = a.thread or store.create_thread(a.researcher)
    run_id = store.enqueue(thread, a.text, GEMINI_MODEL)
    print(f"{DIM}thread {thread}{RESET}\n{CYAN}run {run_id}{RESET} queued; waiting for a worker...")
    while (run := store.get_run(run_id))["status"] not in ("succeeded", "failed", "cancelled", "dead"):
        time.sleep(0.5)
    if run["status"] == "succeeded":
        print(f"{GREEN}assistant>{RESET} {store.load_history(thread)[-1]['text']}")
    else:
        print(f"{RED}run ended: {run['status']} ({run['error_code']}){RESET}")


if __name__ == "__main__":
    main()
