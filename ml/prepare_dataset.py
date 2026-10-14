"""Validate an explicitly supplied approved CSV; never downloads data."""
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd
import numpy as np

FEATURES = ["age", "heart_rate", "spo2", "systolic_bp", "diastolic_bp", "temperature", "respiratory_rate"]
REQUIRED = ["patient_id", *FEATURES, "target"]
BOUNDS = {"age": (18,110), "heart_rate": (20,250), "spo2": (50,100), "systolic_bp": (50,280), "diastolic_bp": (20,180), "temperature": (30,45), "respiratory_rate": (3,70)}

class DatasetValidationError(ValueError): pass

def validate_frame(frame: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(set(REQUIRED) - set(frame.columns))
    if missing: raise DatasetValidationError(f"Missing required columns: {missing}")
    data = frame[REQUIRED].copy()
    if data.empty: raise DatasetValidationError("Dataset has no rows")
    if data["patient_id"].isna().any() or (data["patient_id"].astype(str).str.strip() == "").any():
        raise DatasetValidationError("patient_id must be present for patient-level splitting")
    for col in FEATURES + ["target"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    if data[FEATURES + ["target"]].isna().any().any():
        raise DatasetValidationError("Missing or non-numeric values found; resolve them using documented cohort rules")
    if not np.isfinite(data[FEATURES + ["target"]].to_numpy(dtype=float)).all():
        raise DatasetValidationError("Non-finite numeric values found")
    for col, (low, high) in BOUNDS.items():
        if not data[col].between(low, high).all(): raise DatasetValidationError(f"{col} outside expected API bounds; check units and data quality")
    if (data["diastolic_bp"] >= data["systolic_bp"]).any(): raise DatasetValidationError("diastolic_bp must be lower than systolic_bp")
    if set(data["target"].unique()) != {0,1}: raise DatasetValidationError("target must contain both binary classes 0 and 1")
    data["target"] = data["target"].astype(int)
    data["patient_id"] = data["patient_id"].astype(str)
    return data

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to approved CSV; no download is performed")
    parser.add_argument("--output", required=True, help="Output path for validated CSV")
    args=parser.parse_args()
    source=Path(args.input).expanduser().resolve()
    if not source.is_file(): raise SystemExit(f"Input CSV not found: {source}")
    clean=validate_frame(pd.read_csv(source))
    dest=Path(args.output).expanduser(); dest.parent.mkdir(parents=True, exist_ok=True)
    clean.to_csv(dest,index=False)
    print(f"Validated {len(clean)} rows; patient IDs retained only in this local intermediate. Keep output outside version control.")
if __name__ == "__main__": main()
