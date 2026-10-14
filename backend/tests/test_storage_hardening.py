from __future__ import annotations

import json
import sqlite3

import pytest

from app.storage import (
    StorageError,
    _engine,
    initialize_storage,
    list_observations,
    save_observation,
    storage_status,
)


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("VITALGUARD_DB_PATH", str(tmp_path / "phase1.sqlite3"))
    initialize_storage()
    return tmp_path / "phase1.sqlite3"


def test_migration_is_idempotent_and_records_schema_version(isolated_db):
    initialize_storage()
    status = storage_status()
    assert status["backend"] == "sqlite"
    assert status["schema_ready"] is True
    assert status["schema_version"] == 2


def test_observation_survives_engine_disposal_and_reconnect(isolated_db):
    saved = save_observation(
        "DEMO-DURABLE",
        {"spo2": 97},
        {"model_version": "test-v1", "risk_score": 12},
    )
    _engine().dispose()

    rows = list_observations(patient_id="DEMO-DURABLE", limit=10)
    assert len(rows) == 1
    assert rows[0]["id"] == saved["id"]
    assert rows[0]["inputs"] == {"spo2": 97}


def test_incompatible_existing_schema_fails_without_repairing_it(tmp_path, monkeypatch):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE observations (id INTEGER PRIMARY KEY, patient_id TEXT)")
        connection.execute("INSERT INTO observations(id, patient_id) VALUES (1, 'keep-me')")

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("VITALGUARD_DB_PATH", str(path))
    with pytest.raises(StorageError, match="schema initialization failed"):
        initialize_storage()

    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(observations)")}
        row = connection.execute("SELECT patient_id FROM observations WHERE id=1").fetchone()
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert columns == {"id", "patient_id"}
    assert row == ("keep-me",)
    assert "vitalguard_storage_migrations" not in tables


def test_non_finite_json_is_rejected_without_writing(isolated_db):
    with pytest.raises(StorageError):
        save_observation(
            "DEMO-NAN",
            {"spo2": float("nan")},
            {"model_version": "test-v1", "risk_score": 20},
        )
    assert list_observations(patient_id="DEMO-NAN", limit=10) == []


def test_page_size_is_bounded_at_storage_boundary(isolated_db):
    with pytest.raises(ValueError, match="between 1 and 100"):
        list_observations(limit=101)


def test_health_inspection_does_not_create_missing_schema(tmp_path, monkeypatch):
    path = tmp_path / "empty.sqlite3"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("VITALGUARD_DB_PATH", str(path))

    status = storage_status()
    assert status["schema_ready"] is False
    with sqlite3.connect(path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == set()

def test_incompatible_event_log_fails_closed_without_advancing_migration(tmp_path,monkeypatch):
    path=tmp_path/"legacy-events.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE observations (id INTEGER PRIMARY KEY, patient_id TEXT NOT NULL, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, input_json TEXT NOT NULL, prediction_json TEXT NOT NULL, model_version TEXT NOT NULL)")
        connection.execute("CREATE TABLE vitalguard_storage_migrations (version INTEGER PRIMARY KEY, applied_at DATETIME NOT NULL, description VARCHAR(200) NOT NULL)")
        connection.execute("INSERT INTO vitalguard_storage_migrations(version, applied_at, description) VALUES (1, CURRENT_TIMESTAMP, 'phase one')")
        connection.execute("CREATE TABLE vitalguard_event_log (id INTEGER PRIMARY KEY, event_id TEXT)")
    monkeypatch.delenv("DATABASE_URL",raising=False)
    monkeypatch.setenv("VITALGUARD_DB_PATH",str(path))
    with pytest.raises(StorageError,match="schema initialization failed"):
        initialize_storage()
    with sqlite3.connect(path) as connection:
        columns={row[1] for row in connection.execute("PRAGMA table_info(vitalguard_event_log)")}
        version=connection.execute("SELECT MAX(version) FROM vitalguard_storage_migrations").fetchone()[0]
    assert columns=={"id","event_id"}
    assert version==1
