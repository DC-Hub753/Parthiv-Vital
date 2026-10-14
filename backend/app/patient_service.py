"""Persistence helpers for patient records in the synthetic VitalGuard demo.

Follows the same engine-per-call pattern as alert_service.py and storage.py.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import insert, select, update, func
from sqlalchemy.exc import IntegrityError

from .storage import _engine, _ensure_schema
from .storage_schema import patients


def _serialize(row: Any) -> dict[str, Any]:
    item = dict(row)
    for key in ("created_at", "updated_at"):
        if item.get(key) is not None and hasattr(item[key], "isoformat"):
            item[key] = item[key].isoformat()
    return item


def create_patient(
    *,
    patient_id: str,
    display_name: str,
    sex: str = "U",
    date_of_birth: str | None = None,
    ward: str = "General Ward",
    bed: str = "",
    created_by: str = "demo-system",
) -> dict[str, Any]:
    """Create a new patient record. Raises IntegrityError on duplicate patient_id."""
    engine = _engine()
    try:
        with engine.begin() as connection:
            connection.execute(insert(patients).values(
                patient_id=patient_id,
                display_name=display_name,
                sex=sex,
                date_of_birth=date_of_birth,
                ward=ward,
                bed=bed,
                created_by=created_by,
            ))
            row = connection.execute(
                select(patients).where(patients.c.patient_id == patient_id)
            ).mappings().one()
        return _serialize(row)
    finally:
        engine.dispose()


def get_patient(patient_id: str, *, include_inactive: bool = False) -> dict[str, Any] | None:
    """Return a single patient by ID, or None if not found."""
    engine = _engine()
    try:
        query = select(patients).where(patients.c.patient_id == patient_id)
        if not include_inactive:
            query = query.where(patients.c.active == True)  # noqa: E712
        with engine.connect() as connection:
            row = connection.execute(query).mappings().first()
        return _serialize(row) if row else None
    finally:
        engine.dispose()


def list_patients(
    *,
    active_only: bool = True,
    ward: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Return a page of patients and the total matching count."""
    engine = _engine()
    try:
        query = select(patients)
        count_query = select(func.count()).select_from(patients)
        if active_only:
            query = query.where(patients.c.active == True)  # noqa: E712
            count_query = count_query.where(patients.c.active == True)  # noqa: E712
        if ward is not None:
            query = query.where(patients.c.ward == ward)
            count_query = count_query.where(patients.c.ward == ward)

        query = query.order_by(patients.c.patient_id).limit(limit).offset(offset)
        with engine.connect() as connection:
            rows = connection.execute(query).mappings().all()
            total = connection.execute(count_query).scalar()
        return [_serialize(row) for row in rows], total or 0
    finally:
        engine.dispose()


def update_patient(patient_id: str, *, updates: dict[str, Any]) -> dict[str, Any] | None:
    """Apply partial updates to a patient. Returns the updated patient or None."""
    if not updates:
        return get_patient(patient_id)
    engine = _engine()
    try:
        with engine.begin() as connection:
            # Only update an active patient.
            existing = connection.execute(
                select(patients).where(
                    patients.c.patient_id == patient_id,
                    patients.c.active == True,  # noqa: E712
                )
            ).mappings().first()
            if not existing:
                return None

            connection.execute(
                update(patients)
                .where(patients.c.patient_id == patient_id)
                .values(**updates)
            )
            row = connection.execute(
                select(patients).where(patients.c.patient_id == patient_id)
            ).mappings().one()
        return _serialize(row)
    finally:
        engine.dispose()


def deactivate_patient(patient_id: str) -> dict[str, Any] | None:
    """Soft-delete: set active=False. Returns the deactivated patient or None."""
    engine = _engine()
    try:
        with engine.begin() as connection:
            existing = connection.execute(
                select(patients).where(patients.c.patient_id == patient_id)
            ).mappings().first()
            if not existing:
                return None
            if not existing["active"]:
                return _serialize(existing)
            connection.execute(
                update(patients)
                .where(patients.c.patient_id == patient_id)
                .values(active=False)
            )
            row = connection.execute(
                select(patients).where(patients.c.patient_id == patient_id)
            ).mappings().one()
        return _serialize(row)
    finally:
        engine.dispose()


def seed_initial_patients(engine: Engine) -> None:
    """Seed initial clinical cohort if the patients table is completely empty (skipped during pytest runs)."""
    import os
    if "PYTEST_CURRENT_TEST" in os.environ:
        return
    with engine.begin() as connection:
        count = connection.execute(select(func.count()).select_from(patients)).scalar()
        if count and count > 0:
            return

        demo_cohort = [
            ("P-SIM-001", "Arthur Pendelton", "M", "1960-04-12", "General Ward", "A-12", "demo-system"),
            ("P-SIM-002", "Beatrice Campbell", "F", "1966-09-23", "Cardiology", "C-07", "demo-system"),
            ("P-SIM-003", "Charles Montgomery", "M", "1953-11-05", "ICU", "B-14", "demo-system"),
            ("P-SIM-004", "Diana Ross", "F", "1979-02-18", "Emergency", "E-03", "demo-system"),
            ("P-SIM-005", "Edward Vance", "M", "1972-07-30", "General Ward", "A-21", "demo-system"),
            ("P-SIM-006", "Fiona Gallagher", "F", "1957-01-14", "ICU", "B-09", "demo-system"),
            ("P-SIM-007", "George Miller", "M", "1985-06-22", "Cardiology", "C-11", "demo-system"),
            ("P-SIM-008", "Helen Mirren", "F", "1949-10-03", "Emergency", "E-08", "demo-system"),
        ]
        for pid, name, sex, dob, ward, bed, cby in demo_cohort:
            connection.execute(insert(patients).values(
                patient_id=pid,
                display_name=name,
                sex=sex,
                date_of_birth=dob,
                ward=ward,
                bed=bed,
                active=True,
                created_by=cby,
            ))
    seed_initial_observations(engine)


def seed_initial_observations(engine: Engine) -> None:
    """Seed baseline observations for the initial cohort if empty."""
    from datetime import datetime, timedelta, timezone
    from .storage import _OBSERVATIONS, save_observation
    with engine.begin() as connection:
        count = connection.execute(select(func.count()).select_from(_OBSERVATIONS)).scalar()
        if count and count > 0:
            return

    from .alert_generator import evaluate_and_generate_alerts
    now = datetime.now(timezone.utc)

    # Multi-point clinical history progressions (4 previous readings + 1 current reading)
    cohort_progressions = [
        # (patient_id, baseline_vitals, step_deltas, final_score, final_level)
        ("P-SIM-001", {"heart_rate": 70, "spo2": 98, "systolic_bp": 120, "diastolic_bp": 76, "temperature": 36.6, "respiratory_rate": 15, "consciousness": "A", "supplemental_oxygen": False},
         {"heart_rate": 1, "spo2": 0, "systolic_bp": 0, "diastolic_bp": 0, "temperature": 0.05, "respiratory_rate": 0}, 12, "low"),
        ("P-SIM-002", {"heart_rate": 76, "spo2": 98, "systolic_bp": 124, "diastolic_bp": 78, "temperature": 36.9, "respiratory_rate": 16, "consciousness": "A", "supplemental_oxygen": False},
         {"heart_rate": 1.5, "spo2": -0.5, "systolic_bp": 1.5, "diastolic_bp": 1.0, "temperature": 0.05, "respiratory_rate": 0.5}, 24, "low"),
        ("P-SIM-003", {"heart_rate": 88, "spo2": 96, "systolic_bp": 118, "diastolic_bp": 74, "temperature": 37.2, "respiratory_rate": 18, "consciousness": "A", "supplemental_oxygen": False},
         {"heart_rate": 8.5, "spo2": -1.5, "systolic_bp": -6.5, "diastolic_bp": -4.5, "temperature": 0.4, "respiratory_rate": 2.0}, 88, "critical"),
        ("P-SIM-004", {"heart_rate": 78, "spo2": 96, "systolic_bp": 124, "diastolic_bp": 78, "temperature": 36.8, "respiratory_rate": 16, "consciousness": "A", "supplemental_oxygen": False},
         {"heart_rate": -2.0, "spo2": 0.5, "systolic_bp": -1.5, "diastolic_bp": -1.0, "temperature": -0.05, "respiratory_rate": -0.5}, 15, "low"),
        ("P-SIM-005", {"heart_rate": 72, "spo2": 97, "systolic_bp": 122, "diastolic_bp": 78, "temperature": 36.7, "respiratory_rate": 15, "consciousness": "A", "supplemental_oxygen": False},
         {"heart_rate": 1.0, "spo2": -0.25, "systolic_bp": 1.0, "diastolic_bp": 0.5, "temperature": 0.05, "respiratory_rate": 0.25}, 18, "low"),
        ("P-SIM-006", {"heart_rate": 84, "spo2": 97, "systolic_bp": 122, "diastolic_bp": 78, "temperature": 37.0, "respiratory_rate": 16, "consciousness": "A", "supplemental_oxygen": False},
         {"heart_rate": 6.0, "spo2": -1.25, "systolic_bp": -4.5, "diastolic_bp": -3.5, "temperature": 0.25, "respiratory_rate": 1.5}, 72, "high"),
        ("P-SIM-007", {"heart_rate": 66, "spo2": 99, "systolic_bp": 114, "diastolic_bp": 70, "temperature": 36.6, "respiratory_rate": 13, "consciousness": "A", "supplemental_oxygen": False},
         {"heart_rate": 0.5, "spo2": 0.0, "systolic_bp": 0.25, "diastolic_bp": 0.5, "temperature": 0.02, "respiratory_rate": 0.25}, 10, "low"),
        ("P-SIM-008", {"heart_rate": 80, "spo2": 97, "systolic_bp": 126, "diastolic_bp": 80, "temperature": 37.0, "respiratory_rate": 15, "consciousness": "A", "supplemental_oxygen": False},
         {"heart_rate": 2.0, "spo2": -0.5, "systolic_bp": 2.0, "diastolic_bp": 1.0, "temperature": 0.05, "respiratory_rate": 0.5}, 32, "moderate"),
    ]

    for pid, base, deltas, final_score, final_level in cohort_progressions:
        # Generate 5 data points spaced 30 minutes apart leading to now
        for step in range(5):
            minutes_ago = (4 - step) * 30
            obs_time = now - timedelta(minutes=minutes_ago)
            vitals = {
                "heart_rate": round(base["heart_rate"] + deltas["heart_rate"] * step),
                "spo2": max(70, min(100, round(base["spo2"] + deltas["spo2"] * step))),
                "systolic_bp": round(base["systolic_bp"] + deltas["systolic_bp"] * step),
                "diastolic_bp": round(base["diastolic_bp"] + deltas["diastolic_bp"] * step),
                "temperature": round(base["temperature"] + deltas["temperature"] * step, 1),
                "respiratory_rate": round(base["respiratory_rate"] + deltas["respiratory_rate"] * step),
                "consciousness": "V" if step == 4 and final_score >= 80 else "A",
                "supplemental_oxygen": True if (step >= 2 and final_score >= 70) else False,
            }
            if step == 4:
                step_score = final_score
                step_level = final_level
            else:
                progress = step / 4.0
                step_score = max(5, round(15 + (final_score - 15) * progress))
                step_level = "critical" if step_score >= 80 else "high" if step_score >= 65 else "moderate" if step_score >= 35 else "low"

            pred = {
                "patient_id": pid,
                "risk_score": step_score,
                "risk_level": step_level,
                "model_probability": step_score / 100.0,
                "model_version": "xgboost-vitalguard-v1.0.0",
                "factors": [],
                "disclaimer": "Synthetic demo model prediction",
                "demo_only": True,
            }
            saved = save_observation(pid, vitals, pred, created_at=obs_time)
            if step == 4 and step_score >= 65:
                assessment = {
                    "news2": {
                        "total_score": 9 if step_score > 80 else 6,
                        "single_parameter_extreme": step_score > 80,
                        "escalation_response": "Emergency critical care assessment" if step_score > 80 else "Urgent clinical review",
                    },
                    "ml_prediction": {
                        "probability": step_score / 100.0,
                        "prediction_horizon": "6-hour acute clinical deterioration",
                        "model_version": "xgboost-vitalguard-v1.0.0",
                    },
                    "derived_features": {
                        "spo2_trend_30m": -4.0 if step_score > 80 else 0.0,
                        "hr_trend_30m": 25.0 if step_score > 80 else 0.0,
                    },
                    "data_quality": {"is_plausible": True, "warnings": []},
                }
                evaluate_and_generate_alerts(pid, assessment, source_event_id=f"init:{saved['id']}")


