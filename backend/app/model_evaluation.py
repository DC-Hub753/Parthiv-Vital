"""Safe metadata view for model status; no fabricated evaluation numbers."""
from __future__ import annotations
import json, os
from pathlib import Path
from .model import active_model_metadata

def evaluation_report() -> dict:
    meta=active_model_metadata()
    manifest_path=os.getenv("VITALGUARD_MODEL_MANIFEST","").strip()
    manifest=None
    if manifest_path and Path(manifest_path).is_file():
        try: manifest=json.loads(Path(manifest_path).read_text())
        except (OSError, json.JSONDecodeError): manifest=None
    return {
      "model_version":meta["model_version"],"algorithm":meta["algorithm"],"mode":meta["mode"],
      "selected_candidate":(manifest or {}).get("selected_candidate"),
      "candidates":(manifest or {}).get("candidates",{}),
      "training_data_version":(manifest or {}).get("dataset_version"),
      "clinical_training_verified":bool((manifest or {}).get("clinical_training_verified",False)),
      "clinically_validated":False,"demo_only":True,
      "limitations":(manifest or {}).get("limitations",["No verified evaluation manifest is configured for this runtime.","Synthetic fallback is not clinically validated."]),
    }
