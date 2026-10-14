# Reproducible ML pipeline

This pipeline is separate from API startup. No restricted dataset is downloaded. Clinical training is blocked until a dataset is approved and its outcome/label contract is documented. Current smoke-test metrics on heuristic/synthetic labels are engineering checks only, never clinical performance evidence.

## Commands

```bash
python -m pip install -r backend/requirements.txt
python ml/prepare_dataset.py --input /secure/path/approved.csv --output /secure/path/validated.csv
python ml/train.py --input /secure/path/validated.csv --dataset-version approved-dataset-v1 --output-dir ml/artifacts
python ml/evaluate.py --artifact ml/artifacts/vitalguard_logreg.joblib --input /secure/path/independent-test.csv
pytest ml/tests -q
```

Input CSV contract: `patient_id`, seven feature columns in `config.yaml`, and binary `target`. Before clinical use, establish the prediction timestamp, future outcome window, cohort inclusion/exclusion, outcome ascertainment, unit conversions, missingness policy, and patient/time split strategy. Never use future-derived data as features. Training makes patient-disjoint train/validation/test groups and fits preprocessing only on train. Keep the test set untouched for threshold selection and hyperparameter tuning.

Artifacts and datasets are excluded from Git. The manifest records dataset and artifact hashes, feature version, seed, split counts, target definition, metrics and a non-clinical status flag. Artifact creation is not evidence of clinical validity. Calibration requires a sufficiently sized independent cohort and should be assessed before any clinical claim.
