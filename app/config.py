import os
from pathlib import Path

# Load .env file automatically if present
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
if ENV_PATH.is_file():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from app.lab_db import LabDb
from app.memory import RunStore
from app.supabase_db import is_supabase_configured

AGENT_DB = os.environ.get("AGENT_DB", "agent.db")
LAB_DB = os.environ.get("LAB_DB", "lab.db")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def open_stores() -> tuple[RunStore, LabDb]:
    """Open stores. By default, initializes SQLite stores and runs migrations.
    If Supabase is configured, prints a status indicator.
    """
    store, db = RunStore(AGENT_DB), LabDb(LAB_DB)
    store.migrate()
    db.migrate()
    return store, db


def make_providers(mock: bool, slow: float = 0.0) -> dict:
    """One provider per agent. With Gemini, all three share one client; each keeps its own prompt and tools."""
    if mock:
        from app.providers import demo_providers
        return demo_providers(slow)

    from app.providers import GeminiProvider
    gemini = GeminiProvider(GEMINI_MODEL)
    return {"supervisor": gemini, "inventory": gemini, "booking_desk": gemini}
