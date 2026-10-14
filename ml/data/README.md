# Dataset policy and provenance

No clinical dataset is included, fetched, or presumed available by this repository. In particular, MIMIC-IV and eICU require their own access approvals, credentialing, licensing, and permitted-use compliance. Do not download restricted records without approval and never commit patient-level data.

## Current status

**Clinical training is blocked pending an approved dataset.** The existing API's synthetic generator uses seven features: age, heart rate, SpO2, systolic/diastolic blood pressure, temperature, and respiratory rate. Its labels are generated from a heuristic and do not represent independently observed clinical outcomes. Pipeline smoke tests may use synthetic data, but their metrics are not clinical performance claims.

## Approved-data contract

Once approval exists, place a permitted, de-identified CSV outside version control and pass its path explicitly to `ml/prepare_dataset.py`. It must contain a stable pseudonymous `patient_id`, the seven feature columns, and a documented binary `target` defined from an outcome measured after prediction time. Document cohort inclusion/exclusion, units, missingness handling, prediction timestamp, outcome window, and label provenance before training. Never use future measurements to construct input features. The current synthetic target does not satisfy this clinical target contract.

## Field mapping and validation

| Feature | Expected unit / domain | Validation |
| --- | --- | --- |
| age | years, 18–110 for current API | numeric, finite |
| heart_rate | beats/min, 20–250 | numeric, finite |
| spo2 | percent, 50–100 | numeric, finite |
| systolic_bp | mmHg, 50–280 | numeric, finite |
| diastolic_bp | mmHg, 20–180 and less than systolic | numeric, finite |
| temperature | Celsius, 30–45 | numeric, finite; convert source units before use |
| respiratory_rate | breaths/min, 3–70 | numeric, finite |

These are API plausibility bounds, not universal clinical reference ranges. Validate dataset-specific units and missingness rather than silently imputing or clipping invalid records.
