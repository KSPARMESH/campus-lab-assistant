"""Supabase integration layer for Campus Lab Assistant.
Supports both Supabase REST API (zero third-party binary dependencies needed)
and psycopg/supabase-py if installed.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

# Load .env file automatically if present
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
if ENV_PATH.is_file():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")


def is_supabase_configured() -> bool:
    """Return True if Supabase environment variables are provided."""
    return bool(SUPABASE_URL and SUPABASE_KEY)


class SupabaseRestClient:
    """Lightweight PostgREST client that uses standard library urllib.
    Requires no native binaries or extra drivers.
    """

    def __init__(self, url: str | None = None, key: str | None = None):
        self.url = (url or SUPABASE_URL).rstrip("/")
        self.key = key or SUPABASE_KEY

    def _headers(self, prefer: str | None = None) -> dict[str, str]:
        h = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if prefer:
            h["Prefer"] = prefer
        return h

    def get(self, table: str, query_params: dict | None = None) -> list[dict]:
        """Perform a SELECT query against Supabase PostgREST."""
        params = f"?{urllib.parse.urlencode(query_params)}" if query_params else ""
        req_url = f"{self.url}/rest/v1/{table}{params}"
        req = urllib.request.Request(req_url, headers=self._headers())
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Supabase GET {table} failed ({e.code}): {body}") from e

    def post(self, table: str, payload: dict | list[dict], upsert: bool = False) -> list[dict]:
        """Perform an INSERT or UPSERT query against Supabase."""
        prefer = "return=representation"
        if upsert:
            prefer += ",resolution=merge-duplicates"
        req_url = f"{self.url}/rest/v1/{table}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(req_url, data=data, headers=self._headers(prefer=prefer), method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else []
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Supabase POST {table} failed ({e.code}): {body}") from e

    def patch(self, table: str, query_params: dict, payload: dict) -> list[dict]:
        """Perform an UPDATE query against Supabase."""
        params = f"?{urllib.parse.urlencode(query_params)}"
        req_url = f"{self.url}/rest/v1/{table}{params}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(req_url, data=data, headers=self._headers(prefer="return=representation"), method="PATCH")
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else []
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Supabase PATCH {table} failed ({e.code}): {body}") from e
