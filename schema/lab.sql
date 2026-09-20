-- lab.db: Campus Lab Equipment domain database.
-- Agent memory is kept strictly separate in agent.db / Supabase agent schema.

CREATE TABLE IF NOT EXISTS researcher (
    id            INTEGER PRIMARY KEY,
    roll_no       TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    dept          TEXT NOT NULL,
    safety_level  INTEGER NOT NULL DEFAULT 1 CHECK (safety_level BETWEEN 1 AND 3),
    is_suspended  INTEGER NOT NULL DEFAULT 0 CHECK (is_suspended IN (0, 1))
);

CREATE TABLE IF NOT EXISTS equipment (
    id                INTEGER PRIMARY KEY,
    name              TEXT NOT NULL,
    lab_room          TEXT NOT NULL,
    min_safety_level  INTEGER NOT NULL CHECK (min_safety_level BETWEEN 1 AND 3),
    total_slots       INTEGER NOT NULL,
    status            TEXT NOT NULL DEFAULT 'operational' CHECK (status IN ('operational', 'maintenance'))
);

CREATE TABLE IF NOT EXISTS slot (
    id                         INTEGER PRIMARY KEY,
    equipment_id               INTEGER NOT NULL REFERENCES equipment (id),
    slot_date                  TEXT NOT NULL,       -- e.g. '2026-09-21'
    slot_name                  TEXT NOT NULL,       -- e.g. '09:00 - 12:00' or '14:00 - 17:00'
    is_booked                  INTEGER NOT NULL DEFAULT 0 CHECK (is_booked IN (0, 1)),
    booked_by_researcher_id    INTEGER REFERENCES researcher (id),
    version                    INTEGER NOT NULL DEFAULT 0,
    UNIQUE (equipment_id, slot_date, slot_name)
);

-- Business rules live in data, never just in prompt instructions.
CREATE TABLE IF NOT EXISTS policy (
    name   TEXT PRIMARY KEY,
    value  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS booking (
    id             INTEGER PRIMARY KEY,
    researcher_id  INTEGER NOT NULL REFERENCES researcher (id),
    equipment_id   INTEGER NOT NULL REFERENCES equipment (id),
    slot_id        INTEGER NOT NULL REFERENCES slot (id),
    status         TEXT NOT NULL DEFAULT 'confirmed' CHECK (status IN ('confirmed', 'cancelled')),
    created_at     REAL NOT NULL,
    UNIQUE (equipment_id, slot_id)                 -- Slot clash prevention: only one booking per slot
);

CREATE TABLE IF NOT EXISTS notification (
    id          INTEGER PRIMARY KEY,
    roll_no     TEXT NOT NULL,
    message     TEXT NOT NULL,
    dedupe_key  TEXT NOT NULL UNIQUE,
    created_at  REAL NOT NULL
);

-- Day 3: Idempotency keys live next to the side effects they protect.
CREATE TABLE IF NOT EXISTS idempotency (
    key         TEXT PRIMARY KEY,
    tool_name   TEXT NOT NULL,
    result      TEXT NOT NULL,
    created_at  REAL NOT NULL
);
