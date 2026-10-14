# Model artifacts

Generated `*.joblib` model artifacts and manifests are intentionally not committed by default. They may contain fitted parameters and must be treated as versioned build outputs. Store approved artifacts in a controlled artifact registry or release, record SHA-256, dataset version, feature schema, training configuration, and evaluation report. Do not load an untrusted joblib file; deserialization can execute code. No clinically trained artifact is bundled with this repository.
