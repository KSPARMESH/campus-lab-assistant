"""Set up and verify Supabase PostgreSQL connection and tables.

    python -m scripts.setup_supabase
"""
import os
from pathlib import Path

from app.supabase_db import SupabaseRestClient, is_supabase_configured

SQL_FILE = Path(__file__).resolve().parent.parent / "schema" / "supabase_schema.sql"


def main() -> None:
    print("=====================================================================")
    print("           Campus Lab Assistant - Supabase Setup & Check             ")
    print("=====================================================================\n")

    if not is_supabase_configured():
        print("[!] Supabase environment variables NOT detected in this shell session.")
        print("\nTo connect to Supabase:")
        print("  1. Create a free project at https://supabase.com")
        print("  2. Go to the SQL Editor in your Supabase dashboard and run:")
        print(f"     {SQL_FILE}")
        print("  3. Set your environment variables (in .env or PowerShell):")
        print('     $env:SUPABASE_URL = "https://<your-project-id>.supabase.co"')
        print('     $env:SUPABASE_KEY = "<your-anon-or-service-role-key>"\n')
        print("[i] Current mode: Local SQLite (agent.db & lab.db) fully active and operational.")
        print("    All automated tests, demos, and crash replays run with zero configuration!\n")
        return

    client = SupabaseRestClient()
    print(f"Connecting to Supabase at: {client.url} ...")
    try:
        data = client.get("equipment")
        print(f"[+] Successfully connected to Supabase PostgREST!")
        print(f"[+] Found {len(data)} equipment entries in Supabase domain database.")
        for item in data[:3]:
            print(f"    - ID {item.get('id')}: {item.get('name')} (Room: {item.get('lab_room')})")
        print("\n[✓] Supabase is ready for live agent execution!\n")
    except Exception as e:
        print(f"[-] Could not query Supabase tables: {e}")
        print("\nEnsure you have executed the schema migration script in Supabase:")
        print(f"  {SQL_FILE}")


if __name__ == "__main__":
    main()
