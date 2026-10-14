# Reproducible ML benchmark pipeline

Training is an offline command and never runs during API startup. No restricted dataset is fetched. Clinical training and algorithm selection remain blocked until an approved dataset, target definition, and permitted use are documented.

```bash
python ml/prepare_dataset.py --input /secure/approved.csv --output /secure/validated.csv
python ml/train.py --input /secure/validated.csv --dataset-version approved-v1 --output-dir /secure/artifacts
python ml/evaluate.py --artifact /secure/artifacts/vitalguard_logistic_regression.joblib --input /secure/independent-test.csv --threshold 0.5 --output /secure/evaluation.json
pytest ml/tests backend/tests -q
```

All candidates use the same patient-disjoint train/validation/test split and feature order. Logistic regression is mandatory baseline; random forest is available; XGBoost is benchmarked only when installed. Selection uses the predeclared validation metric. Test metrics are reported only after selection. Metrics include ROC-AUC, PR-AUC, sensitivity, specificity, precision, Brier score, artifact size, and approximate inference latency. Calibration curves and operating thresholds require clinical requirements and an adequately sized approved validation cohort.

Input CSV contract: `patient_id`, seven feature columns, binary `target`. Before clinical use, define prediction time, future outcome window, cohort inclusion/exclusion, label provenance, unit conversions, and missingness rules. The current synthetic target is heuristic-derived and cannot establish which algorithm is clinically best. Never use test data for tuning or threshold selection.
