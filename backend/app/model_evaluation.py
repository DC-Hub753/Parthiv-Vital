"""Safe metadata view for model status; no fabricated evaluation numbers."""
from __future__ import annotations
import json, os
from pathlib import Path
from .model import active_model_metadata

def evaluation_report() -> dict:
    meta=active_model_metadata()
    explicit=os.getenv("VITALGUARD_MODEL_MANIFEST","").strip()
    model_path=os.getenv("VITALGUARD_MODEL_PATH","").strip()
    candidates=[Path(explicit).expanduser()] if explicit else ([Path(model_path).expanduser().parent/"manifest.json"] if model_path else [])
    manifest={}
    for candidate in candidates:
        if candidate.is_file():
            try:
                manifest=json.loads(candidate.read_text())
                break
            except (OSError,json.JSONDecodeError):
                continue
    return {
      "model_version":meta["model_version"],"algorithm":meta["algorithm"],"mode":meta["mode"],
      "selected_candidate":manifest.get("selected_candidate",meta.get("selected_candidate")),
      "candidates":manifest.get("candidates",{}),
      "training_data_version":manifest.get("dataset_version",meta.get("training_data_version")),
      "clinical_training_verified":bool(manifest.get("clinical_training_verified",False)),
      "clinically_validated":bool(manifest.get("clinically_validated",False)),"demo_only":True,
      "limitations":manifest.get("limitations",["No verified evaluation manifest is configured for this runtime.","Synthetic fallback is not clinically validated."]),
    }
