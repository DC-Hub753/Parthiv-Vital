# Production wiring audit — 14 October 2026

## Scope and safety boundary

This audit covers only `DC-Hub753/Parthiv-Vital` and its associated Render services. It does not change the separate `DC-Hub753/VitalGuard-AI` repository or its Render services.

The application remains a **synthetic-data software prototype, not a clinically validated or production clinical system**. Do not send protected health information (PHI) or use it for diagnosis, triage, treatment, or live patient monitoring. A hospital/device feed requires an authorized integration, contractual permission, security review, and validation.

## Findings fixed in this change

- The frontend's production fallback API URL pointed at the separate VitalGuard deployment. It now points at this repository's `parthiv-vital-api-backend` service.
- Production previously defaulted to demo mode unless an environment variable explicitly disabled it. Production now defaults to API mode; local development remains demo-friendly. Set `VITE_DEMO_MODE=true` only for an explicitly labelled demo.
- API patient-list failures were silently replaced with synthetic patient records. API mode now propagates the error so backend outages cannot masquerade as live patient data.
- Demo role quick-fill and local-only authentication are now limited to explicit demo mode. Production login must be accepted by the backend; a network failure cannot create a fake local authenticated session.
- The repository's browser smoke and manual API smoke workflows now target the Parthiv-Vital Render services, not the separate VitalGuard deployment.
- The isolated local browser-test build explicitly enables demo mode; the live browser smoke still targets the deployed Parthiv frontend.

## Render configuration

Frontend service: `parthiv-vital-frontend`

- `VITE_API_BASE_URL=https://parthiv-vital-api-backend.onrender.com`
- `VITE_DEMO_MODE=false`

Backend service: `parthiv-vital-api-backend`

- `CORS_ORIGINS=https://parthiv-vital-frontend.onrender.com,http://localhost:5173,http://127.0.0.1:5173`
- Keep `VITALGUARD_AUTH_SECRET`, `VITALGUARD_AUTH_USERNAME`, and `VITALGUARD_AUTH_PASSWORD` configured in the private backend environment. Never put secrets in Vite variables.

The repository's Render services include a second backend service named `parthiv-vital-api` whose build/start commands do not match the nested `backend/` directory. Use `parthiv-vital-api-backend` as the canonical API service; avoid deploying the duplicate service.

## Remaining release blockers / limitations

- The free Render PostgreSQL allowance is already occupied by a different project. This change does not connect Parthiv-Vital to that database and does not create a paid database. The backend may therefore still use ephemeral SQLite until a dedicated database is provisioned and configured.
- Render logs showed repeated `WebSocket /api/v1/live` 403 responses. The live socket requires a valid signed-in session and the `vitalguard-live` subprotocol. Verify the browser login/session against this repository's backend after configuring the correct API URL; do not bypass WebSocket authentication.
- No authorized hospital/device feed is configured. Current ingestion paths are explicitly synthetic-demo or historical replay; a live feed remains an integration task.
- This branch must pass repository CI and the deployed health/API smoke checks before being described as verified end-to-end.

## Verification checklist

1. `npm ci && npm run lint && npm test && npm run build`
2. `PYTHONPATH=backend pytest backend/tests -q`
3. Verify `GET /health` reports a healthy database on the Parthiv backend.
4. Verify login, authenticated patient CRUD, observation persistence, alert workflow, and browser WebSocket reconnect against the Parthiv backend.
5. Confirm API errors are shown as errors and never silently replaced by demo patient data.
6. Confirm the separate VitalGuard-AI Render service IDs remain unchanged.

## Login regression coverage

The login tests now mount the same authentication provider used by the application and verify successful API login, rejected credentials, and unauthenticated route protection. They validate the current production login contract rather than the removed demo-session contract.
