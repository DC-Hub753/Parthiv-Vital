# Model artifacts and rollback

Generated model files and manifests are ignored by Git. Preserve each approved release as an immutable version in a controlled artifact store with SHA-256, dataset version, feature schema, configuration, held-out predictions, and evaluation report. Rollback means restoring the previous immutable artifact path/version and restarting the service, then checking `/api/v1/model/info` and running a prediction smoke test. Never overwrite a known-good artifact in place.

Joblib deserialization can execute code: load only trusted artifacts. No approved clinical model artifact is bundled here. Synthetic benchmark output is not a clinical selection result.
