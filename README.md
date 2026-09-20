# Campus Lab Equipment Booking Assistant: End-to-End Agentic AI

An autonomous, fault-tolerant multi-agent system with durable execution, data-driven policy enforcement, and Supabase / PostgreSQL database integration.

Built for the **SoDak EduTech Agentic AI Workshop** Weekend Project.

---

## 🏛 Architecture Overview

A researcher interacts with the system in natural language. A **Supervisor Agent** delegates tasks to specialized subagents under the principle of **least privilege**:
1. **Inventory Specialist**: **Read-only**. Has **zero** write tools. Searches scientific instruments, computing clusters, and inspects real-time slot availability.
2. **Booking Desk Specialist**: **Action-permitted**. Bound strictly to the authenticated researcher's roll number. Evaluates database-stored safety policies, atomically books equipment slots (preventing clashes), cancels bookings, and sends deduplicated notifications.

Every execution runs through a **durable job queue** with leases, heartbeats, and idempotency keys. If a worker process crashes mid-flight (even right after committing a database transaction), another worker safely resumes execution and replays completed side effects without duplicating them.

```
researcher ─▶ queue (agent.db / Supabase) ─▶ worker ─▶ supervisor
                                                          │
                                      ┌───────────────────┴────────────────────┐
                          ask_inventory                               ask_booking_desk
                                      │                                        │
                                      ▼                                        ▼
                              inventory agent                        booking desk agent
                            (search_equipment,                     (get_researcher_profile,
                            get_available_slots,                    check_eligibility,
                            get_equipment_details)                  book_slot*, cancel_booking*,
                                                                    notify_researcher*)
                         [Zero write permissions]
                                                              * side effects: idempotent via keys
```

---

## 🚀 Quickstart (No API Key Required)

Everything can be verified offline with deterministic scripted models:

```bash
# 1. Navigate to the project directory
cd "E:\KSP\HOPE programming\Agentic AI Workshop\lab-assistant"

# 2. Run the end-to-end interactive demo
python -m scripts.demo

# 3. Run the crash & replay recovery drill (Prints PASS)
python -m scripts.demo --crash

# 4. Run the full pytest test suite (26 tests, < 1 second)
pytest -v
```

---

## ⚡ Supabase Integration (PostgreSQL)

This agentic AI supports **Supabase (PostgreSQL)** for production persistence with automatic fallback to local SQLite (`agent.db` and `lab.db`):

### 1. Database Schema
The complete PostgreSQL schema and seed data are available in [schema/supabase_schema.sql](file:///E:/KSP/HOPE%20programming/Agentic%20AI%20Workshop/lab-assistant/schema/supabase_schema.sql):
- **Agent Memory**: `thread`, `message` (append-only via triggers), `run` (durable queue with leases & attempts), `run_step`, `tool_call`.
- **Domain Business Data**: `researcher`, `equipment`, `slot`, `policy`, `booking` (with unique clash constraints), `notification`, `idempotency`.

### 2. Setting up Supabase
1. Open your project on [supabase.com](https://supabase.com).
2. Go to the **SQL Editor** tab and execute the script in `schema/supabase_schema.sql`.
3. Set your credentials in `.env` (or environment):
   ```bash
   SUPABASE_URL=https://<your-project-id>.supabase.co
   SUPABASE_KEY=<your-anon-or-service-role-key>
   ```
4. Verify connectivity using the setup tool:
   ```bash
   python -m scripts.setup_supabase
   ```

---

## 🤖 Running with Live Gemini API

To run with live Gemini LLM models:

```bash
# Set your Gemini API key
$env:GEMINI_API_KEY="your_api_key_here"      # Windows PowerShell
export GEMINI_API_KEY="your_api_key_here"    # Linux / macOS

# Terminal 1: Start background worker
python -m scripts.worker

# Terminal 2: Enqueue researcher request
python -m scripts.ask --researcher 22CS045 "Is Scanning Electron Microscope (SEM) available on 2026-09-21?"
```

---

## 📋 Course Requirements Matrix

| Requirement | Implementation | Location |
|---|---|---|
| **1. Two Databases** | `agent.db` (queue & memory) + `lab.db` (domain data) / Supabase PostgreSQL | `schema/agent.sql`, `schema/lab.sql`, `schema/supabase_schema.sql` |
| **2. At Least 5 Tools** | 3 read-only (`search_equipment`, `get_available_slots`, `get_equipment_details`, `get_researcher_profile`, `check_eligibility`) + 3 side-effects (`book_slot`, `cancel_booking`, `notify_researcher`). Descriptions >= 120 chars with precise usage & mutation constraints. | `app/tools/lab_tools.py` |
| **3. Business Rule in Data** | `policy` table (`max_active_bookings=2`, `min_safety_level_req=1`). Enforced in code during `check_eligibility` and `book_slot` even if model skips check. | `app/lab_db.py`, `schema/lab.sql` |
| **4. Queue & Leased Worker** | Runs are queued; workers claim via atomic leases; expired leases reaped automatically; heartbeat extends lease. | `app/memory.py`, `app/worker.py` |
| **5. Idempotency & Safe Writes** | Deterministic SHA-256 keys derived from `(run_id, seq, tool, args)`. Side effects commit atomically with keys via `LabDb.once()`. Double-booking returns `already_booked`. | `app/idempotency.py`, `app/lab_db.py` |
| **6. Multi-Agent & Least Privilege** | Supervisor delegates only. Inventory Specialist has zero write tools. Booking Desk Specialist is restricted to researcher roll number. | `app/agents.py`, `app/tools/lab_tools.py` |
| **7. Proof Without API Key** | Deterministic scripted models (`RoutedMock`, `PositionalMock`). `demo.py` and `demo.py --crash` print PASS. 26 unit & integration tests pass in `<1s`. | `scripts/demo.py`, `tests/` |
| **8. Higher Grade Features** | Cancel from 2nd terminal (`scripts/cancel.py`), retry with backoff & dead-lettering (`test_retry_and_dead_letter`), multi-threaded race prevention (`test_concurrent_booking_race_prevention`). | `scripts/cancel.py`, `tests/test_end_to_end.py` |

---

## 🧪 Seed Data Overview

| Researcher | Roll No | Safety Level | Status | Active Bookings | Test Behavior |
|---|---|---|---|---|---|
| Priya Raman | `22CS045` | Level 3 (Advanced) | Active | 0 | Can book any instrument (SEM, GPU, Oscilloscope) |
| Arjun Kumar | `22IT017` | Level 1 (Basic) | Active | 0 | Refused for SEM (needs L3) and Oscilloscope (needs L2) |
| Divya Sekar | `22EC031` | Level 2 (Intermediate) | Active | 1 (Slot 3) | Can book 1 more slot; 3rd slot rejected (quota=2) |
| Rahul Roy | `22ME009` | Level 1 (Basic) | Suspended | 0 | Refused immediately (suspended privileges) |

---

## 📁 Directory Structure

```
lab-assistant/
├── app/
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── dispatch.py          # Introspection, argument coercion & function dispatch
│   │   └── lab_tools.py         # InventoryTools & BookingDeskTools with rich prompts
│   ├── __init__.py
│   ├── agents.py                # Multi-agent Supervisor & Specialist orchestration
│   ├── config.py                # Config loader & provider factory
│   ├── db.py                    # SQLite & transaction management
│   ├── idempotency.py           # SHA-256 key generation for exact-once side effects
│   ├── lab_db.py                # Domain database operations, policies & safe writes
│   ├── memory.py                # Agent memory, append-only messages, queue & leases
│   ├── providers.py             # ScriptedProvider, RoutedMock & GeminiProvider
│   ├── runner.py                # Crash-resilient run step execution loop
│   ├── supabase_db.py           # Supabase REST client (zero-dependency)
│   └── worker.py                # Background queue worker with lease recovery
├── docs/
│   └── architecture.md          # In-depth architectural documentation
├── schema/
│   ├── agent.sql                # Agent memory & queue schema (SQLite)
│   ├── lab.sql                  # Lab domain schema & policies (SQLite)
│   └── supabase_schema.sql      # Complete Supabase PostgreSQL schema & seed data
├── scripts/
│   ├── __init__.py
│   ├── _term.py                 # ANSI color formatting for terminal trace
│   ├── ask.py                   # Enqueue query to the agent queue
│   ├── cancel.py                # Cancel a run from external terminal
│   ├── demo.py                  # End-to-end interactive & crash replay demo
│   ├── setup_supabase.py        # Supabase setup, migration check & verification
│   ├── status.py                # Monitor runs, steps, and database entities
│   └── worker.py                # Run continuous background worker
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Test fixtures & FakeClock
│   ├── test_agents.py           # Supervisor delegation & least-privilege tests
│   ├── test_end_to_end.py       # E2E runs, crash recovery, cancel, retry, race tests
│   └── test_tools.py            # Tool docstrings, database policies, clash prevention
├── .env.example                 # Example environment variables
├── PROJECT_BRIEF.md             # Project requirements and specification
├── pytest.ini                   # Pytest configuration
├── README.md                    # Project documentation
└── requirements.txt             # Python dependencies
```
