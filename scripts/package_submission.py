"""Package the project into weekend-<roll-no>.zip for assignment submission.

    python -m scripts.package_submission --roll-no 22CS045
"""
import argparse
import os
import zipfile
from pathlib import Path

EXCLUDE_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache"}
EXCLUDE_EXTS = {".pyc", ".db", ".sqlite", ".sqlite3"}
EXCLUDE_FILES = {".env"}

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--roll-no", default="22CS045", help="Your student roll number")
    a = p.parse_args()

    zip_name = f"weekend-{a.roll_no}.zip"
    zip_path = PROJECT_ROOT.parent / zip_name

    print(f"Creating submission zip: {zip_path.name} ...")
    count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(PROJECT_ROOT):
            # Prune excluded directories
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for file in files:
                ext = Path(file).suffix.lower()
                if ext in EXCLUDE_EXTS or file in EXCLUDE_FILES:
                    continue
                full_path = Path(root) / file
                rel_path = full_path.relative_to(PROJECT_ROOT)
                zf.write(full_path, arcname=str(rel_path))
                count += 1

    print(f"[✓] Successfully packaged {count} files into {zip_path.name}")
    print(f"[✓] Saved at: {zip_path}")
    print("Zero .venv, .db, or secret .env files included. Ready for submission!")


if __name__ == "__main__":
    main()
