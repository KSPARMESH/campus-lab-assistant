"""Cancel a run from another terminal.

    python -m scripts.cancel <run_id_prefix>
"""
import sys

from app.config import open_stores


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.cancel <run_id>")
        sys.exit(1)
    store, _ = open_stores()
    prefix = sys.argv[1]
    row = store.conn.execute("SELECT id FROM run WHERE id LIKE ?", (prefix + "%",)).fetchone()
    if row is None:
        raise SystemExit(f"No run found matching prefix: {prefix}")
    status = store.request_cancel(row["id"])
    print(f"run {row['id'][:8]}: {status}" + (" (worker stops after current step)" if status == "running" else ""))


if __name__ == "__main__":
    main()
