-- =====================================================================
-- Supabase / PostgreSQL Schema for Campus Lab Equipment Booking Assistant
-- Run this in your Supabase SQL Editor to set up the complete schema and seed data.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Agent Memory & Queue Schema (agent)
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS thread (
    id          TEXT PRIMARY KEY,
    student_id  TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS message (
    id          BIGSERIAL PRIMARY KEY,
    thread_id   TEXT NOT NULL REFERENCES thread (id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('user', 'model')),
    text        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (thread_id, seq)
);

-- Append-only protection for message table
CREATE OR REPLACE FUNCTION reject_message_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'message table is append-only: % rejected', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_message_no_update ON message;
CREATE TRIGGER trg_message_no_update
BEFORE UPDATE ON message
FOR EACH ROW EXECUTE FUNCTION reject_message_mutation();

DROP TRIGGER IF EXISTS trg_message_no_delete ON message;
CREATE TRIGGER trg_message_no_delete
BEFORE DELETE ON message
FOR EACH ROW EXECUTE FUNCTION reject_message_mutation();

CREATE TABLE IF NOT EXISTS run (
    id                TEXT PRIMARY KEY,
    thread_id         TEXT NOT NULL REFERENCES thread (id) ON DELETE CASCADE,
    status            TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'dead')),
    model             TEXT NOT NULL,
    tokens_in         INTEGER NOT NULL DEFAULT 0,
    tokens_out        INTEGER NOT NULL DEFAULT 0,
    attempts          INTEGER NOT NULL DEFAULT 0,
    max_attempts      INTEGER NOT NULL DEFAULT 3,
    available_at      DOUBLE PRECISION NOT NULL,
    lease_owner       TEXT,
    lease_until       DOUBLE PRECISION,
    cancel_requested  INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0, 1)),
    error_code        TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at        TIMESTAMPTZ,
    finished_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_run_claimable ON run (status, available_at);

CREATE TABLE IF NOT EXISTS run_step (
    id          BIGSERIAL PRIMARY KEY,
    run_id      TEXT NOT NULL REFERENCES run (id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('model', 'tool')),
    tokens_in   INTEGER NOT NULL DEFAULT 0,
    tokens_out  INTEGER NOT NULL DEFAULT 0,
    text        TEXT,
    tool_calls  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, seq)
);

CREATE TABLE IF NOT EXISTS tool_call (
    id               BIGSERIAL PRIMARY KEY,
    run_step_id      BIGINT NOT NULL UNIQUE REFERENCES run_step (id) ON DELETE CASCADE,
    tool_name        TEXT NOT NULL,
    args             TEXT NOT NULL,
    result           TEXT NOT NULL,
    ok               INTEGER NOT NULL CHECK (ok IN (0, 1)),
    latency_ms       INTEGER NOT NULL,
    idempotency_key  TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------
-- 2. Domain Schema: Lab Equipment & Bookings
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS researcher (
    id            SERIAL PRIMARY KEY,
    roll_no       TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    dept          TEXT NOT NULL,
    safety_level  INTEGER NOT NULL DEFAULT 1 CHECK (safety_level BETWEEN 1 AND 3),
    is_suspended  INTEGER NOT NULL DEFAULT 0 CHECK (is_suspended IN (0, 1))
);

CREATE TABLE IF NOT EXISTS equipment (
    id                SERIAL PRIMARY KEY,
    name              TEXT NOT NULL,
    lab_room          TEXT NOT NULL,
    min_safety_level  INTEGER NOT NULL CHECK (min_safety_level BETWEEN 1 AND 3),
    total_slots       INTEGER NOT NULL,
    status            TEXT NOT NULL DEFAULT 'operational' CHECK (status IN ('operational', 'maintenance'))
);

CREATE TABLE IF NOT EXISTS slot (
    id                         SERIAL PRIMARY KEY,
    equipment_id               INTEGER NOT NULL REFERENCES equipment (id) ON DELETE CASCADE,
    slot_date                  TEXT NOT NULL,
    slot_name                  TEXT NOT NULL,
    is_booked                  INTEGER NOT NULL DEFAULT 0 CHECK (is_booked IN (0, 1)),
    booked_by_researcher_id    INTEGER REFERENCES researcher (id),
    version                    INTEGER NOT NULL DEFAULT 0,
    UNIQUE (equipment_id, slot_date, slot_name)
);

CREATE TABLE IF NOT EXISTS policy (
    name   TEXT PRIMARY KEY,
    value  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS booking (
    id             SERIAL PRIMARY KEY,
    researcher_id  INTEGER NOT NULL REFERENCES researcher (id),
    equipment_id   INTEGER NOT NULL REFERENCES equipment (id),
    slot_id        INTEGER NOT NULL REFERENCES slot (id),
    status         TEXT NOT NULL DEFAULT 'confirmed' CHECK (status IN ('confirmed', 'cancelled')),
    created_at     DOUBLE PRECISION NOT NULL,
    UNIQUE (equipment_id, slot_id)
);

CREATE TABLE IF NOT EXISTS notification (
    id          SERIAL PRIMARY KEY,
    roll_no     TEXT NOT NULL,
    message     TEXT NOT NULL,
    dedupe_key  TEXT NOT NULL UNIQUE,
    created_at  DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency (
    key         TEXT PRIMARY KEY,
    tool_name   TEXT NOT NULL,
    result      TEXT NOT NULL,
    created_at  DOUBLE PRECISION NOT NULL
);

-- ---------------------------------------------------------------------
-- 3. Seed Data
-- ---------------------------------------------------------------------

INSERT INTO policy (name, value) VALUES
    ('max_active_bookings', 2),
    ('min_safety_level_req', 1),
    ('advance_booking_days', 7)
ON CONFLICT (name) DO UPDATE SET value = EXCLUDED.value;

INSERT INTO researcher (id, roll_no, name, dept, safety_level, is_suspended) VALUES
    (1, '22CS045', 'Priya Raman', 'Computer Science', 3, 0),
    (2, '22IT017', 'Arjun Kumar', 'Information Tech', 1, 0),
    (3, '22EC031', 'Divya Sekar', 'Electronics', 2, 0),
    (4, '22ME009', 'Rahul Roy', 'Mechanical Engg', 1, 1)
ON CONFLICT (id) DO UPDATE SET
    roll_no = EXCLUDED.roll_no,
    name = EXCLUDED.name,
    dept = EXCLUDED.dept,
    safety_level = EXCLUDED.safety_level,
    is_suspended = EXCLUDED.is_suspended;

INSERT INTO equipment (id, name, lab_room, min_safety_level, total_slots, status) VALUES
    (1, 'Scanning Electron Microscope (SEM)', 'Central Lab 101', 3, 2, 'operational'),
    (2, 'Digital Phosphor Oscilloscope 4GHz', 'Circuits Lab 204', 2, 2, 'operational'),
    (3, 'High-Performance GPU Cluster (Node A)', 'AI Lab 302', 1, 3, 'operational'),
    (4, 'UV-Vis Spectrophotometer', 'Materials Lab 105', 2, 2, 'operational'),
    (5, 'Cleanroom Photolithography Unit', 'Cleanroom 110', 3, 1, 'maintenance')
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    lab_room = EXCLUDED.lab_room,
    min_safety_level = EXCLUDED.min_safety_level,
    total_slots = EXCLUDED.total_slots,
    status = EXCLUDED.status;

-- Slots for 2026-09-21
INSERT INTO slot (id, equipment_id, slot_date, slot_name, is_booked, booked_by_researcher_id, version) VALUES
    -- SEM (id 1)
    (1, 1, '2026-09-21', '09:00 - 12:00', 0, NULL, 0),
    (2, 1, '2026-09-21', '14:00 - 17:00', 0, NULL, 0),
    -- Oscilloscope (id 2)
    (3, 2, '2026-09-21', '10:00 - 12:00', 1, 3, 1),    -- Divya already booked this one
    (4, 2, '2026-09-21', '14:00 - 16:00', 0, NULL, 0),
    -- GPU Cluster (id 3)
    (5, 3, '2026-09-21', '09:00 - 13:00', 0, NULL, 0),
    (6, 3, '2026-09-21', '13:00 - 17:00', 0, NULL, 0),
    (7, 3, '2026-09-21', '17:00 - 21:00', 0, NULL, 0),
    -- UV-Vis (id 4)
    (8, 4, '2026-09-21', '11:00 - 13:00', 0, NULL, 0),
    (9, 4, '2026-09-21', '15:00 - 17:00', 0, NULL, 0),
    -- Cleanroom (id 5 - maintenance)
    (10, 5, '2026-09-21', '10:00 - 14:00', 0, NULL, 0)
ON CONFLICT (id) DO NOTHING;

-- Divya's initial booking for slot 3
INSERT INTO booking (id, researcher_id, equipment_id, slot_id, status, created_at)
VALUES (1, 3, 2, 3, 'confirmed', 1790000000.0)
ON CONFLICT (id) DO NOTHING;
