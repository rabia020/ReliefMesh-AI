"""SQLite table definitions for ReliefMesh AI (SIMULATED data only)."""

DROP_SQL = """
DROP TABLE IF EXISTS audit_logs;
DROP TABLE IF EXISTS actions;
DROP TABLE IF EXISTS reports;
DROP TABLE IF EXISTS incidents;
DROP TABLE IF EXISTS resources;
DROP TABLE IF EXISTS shelters;
DROP TABLE IF EXISTS hospitals;
DROP TABLE IF EXISTS blocked_roads;
DROP TABLE IF EXISTS places;
DROP TABLE IF EXISTS meta;
"""

SCHEMA_SQL = """
CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE places (
    id      TEXT PRIMARY KEY,
    name    TEXT NOT NULL,
    name_ur TEXT,
    kind    TEXT NOT NULL,
    lat     REAL NOT NULL,
    lon     REAL NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE incidents (
    id                  TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    incident_type       TEXT NOT NULL,
    place_id            TEXT REFERENCES places(id),
    location_name       TEXT NOT NULL,
    lat                 REAL NOT NULL,
    lon                 REAL NOT NULL,
    estimated_affected  INTEGER NOT NULL DEFAULT 0 CHECK (estimated_affected >= 0),
    vulnerable_people   INTEGER NOT NULL DEFAULT 0 CHECK (vulnerable_people >= 0),
    medical_emergency   INTEGER NOT NULL DEFAULT 0 CHECK (medical_emergency IN (0, 1)),
    medical_severity    INTEGER NOT NULL DEFAULT 0 CHECK (medical_severity BETWEEN 0 AND 3),
    isolation           INTEGER NOT NULL DEFAULT 0 CHECK (isolation BETWEEN 0 AND 2),
    required_resources  TEXT NOT NULL DEFAULT '[]',
    priority            TEXT CHECK (priority IN ('Critical', 'High', 'Medium', 'Low')),
    priority_score      REAL,
    evidence_confidence INTEGER CHECK (evidence_confidence BETWEEN 0 AND 100),
    status              TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open', 'in_progress', 'resolved', 'unverified')),
    conflict_note       TEXT,
    summary             TEXT,
    first_report_time   TEXT,
    last_report_time    TEXT,
    origin              TEXT NOT NULL DEFAULT 'pipeline' CHECK (origin IN ('seed', 'pipeline'))
);

CREATE TABLE reports (
    id          TEXT PRIMARY KEY,
    timestamp   TEXT NOT NULL,
    language    TEXT NOT NULL CHECK (language IN ('en', 'roman_ur', 'ur')),
    source_type TEXT NOT NULL,
    text        TEXT NOT NULL,
    image_id    TEXT,
    image_file  TEXT,
    structured  TEXT,
    batch       TEXT NOT NULL CHECK (batch IN ('baseline', 'demo', 'live')),
    status      TEXT NOT NULL CHECK (status IN ('queued', 'received', 'processed')),
    incident_id TEXT REFERENCES incidents(id)
);
CREATE INDEX idx_reports_incident ON reports(incident_id);
CREATE INDEX idx_reports_status   ON reports(status);

CREATE TABLE resources (
    id                 TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    type               TEXT NOT NULL CHECK (type IN ('rescue_team', 'boat', 'ambulance', 'medical_team')),
    status             TEXT NOT NULL CHECK (status IN ('available', 'deployed', 'maintenance')),
    base               TEXT,
    lat                REAL NOT NULL,
    lon                REAL NOT NULL,
    crew_size          INTEGER NOT NULL DEFAULT 0,
    capacity_people    INTEGER NOT NULL DEFAULT 0,
    capabilities       TEXT NOT NULL DEFAULT '[]',
    current_assignment TEXT
);

CREATE TABLE shelters (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    lat               REAL NOT NULL,
    lon               REAL NOT NULL,
    capacity          INTEGER NOT NULL CHECK (capacity >= 0),
    current_occupancy INTEGER NOT NULL CHECK (current_occupancy >= 0),
    status            TEXT NOT NULL CHECK (status IN ('open', 'closed')),
    road_access       TEXT NOT NULL CHECK (road_access IN ('open', 'limited', 'blocked')),
    facilities        TEXT NOT NULL DEFAULT '[]',
    notes             TEXT,
    CHECK (current_occupancy <= capacity)
);

CREATE TABLE hospitals (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    lat             REAL NOT NULL,
    lon             REAL NOT NULL,
    total_beds      INTEGER NOT NULL CHECK (total_beds >= 0),
    available_beds  INTEGER NOT NULL CHECK (available_beds >= 0),
    icu_total       INTEGER NOT NULL CHECK (icu_total >= 0),
    icu_available   INTEGER NOT NULL CHECK (icu_available >= 0),
    emergency_open  INTEGER NOT NULL CHECK (emergency_open IN (0, 1)),
    status          TEXT NOT NULL CHECK (status IN ('operational', 'limited', 'closed')),
    specialties     TEXT NOT NULL DEFAULT '[]',
    notes           TEXT,
    CHECK (available_beds <= total_beds),
    CHECK (icu_available <= icu_total)
);

CREATE TABLE blocked_roads (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    lat         REAL NOT NULL,
    lon         REAL NOT NULL,
    radius_m    INTEGER NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('blocked', 'partial', 'disputed')),
    reason      TEXT,
    reported_at TEXT,
    source      TEXT
);

CREATE TABLE actions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id   TEXT NOT NULL REFERENCES incidents(id),
    action_type   TEXT NOT NULL,
    title         TEXT NOT NULL,
    reason        TEXT NOT NULL,
    resource_ids  TEXT NOT NULL DEFAULT '[]',
    status        TEXT NOT NULL DEFAULT 'proposed'
                  CHECK (status IN ('proposed', 'executed', 'rejected', 'info_requested')),
    proposed_by   TEXT NOT NULL,
    proposed_at   TEXT NOT NULL,
    decided_by    TEXT,
    decided_at    TEXT,
    decision_note TEXT,
    executed_at   TEXT,
    result        TEXT,
    CONSTRAINT decision_needs_human
        CHECK (status = 'proposed' OR (decided_by IS NOT NULL AND decided_at IS NOT NULL)),
    CONSTRAINT decider_must_be_human
        CHECK (decided_by IS NULL OR decided_by LIKE 'human:%'),
    CONSTRAINT executed_needs_time
        CHECK (status <> 'executed' OR executed_at IS NOT NULL)
);

CREATE TABLE audit_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    actor       TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    incident_id TEXT REFERENCES incidents(id),
    action_id   INTEGER REFERENCES actions(id),
    message     TEXT NOT NULL,
    details     TEXT NOT NULL DEFAULT '{}'
);

CREATE TRIGGER audit_logs_no_update BEFORE UPDATE ON audit_logs
BEGIN
    SELECT RAISE(ABORT, 'audit_logs is append-only');
END;

CREATE TRIGGER audit_logs_no_delete BEFORE DELETE ON audit_logs
BEGIN
    SELECT RAISE(ABORT, 'audit_logs is append-only');
END;
"""


def create_schema(conn) -> None:
    conn.executescript(DROP_SQL)
    conn.executescript(SCHEMA_SQL)