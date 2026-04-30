# Extending Cortex

This document contains the operational runbooks from the design document (`features/cortex-second-brain/designs/design.md` § "Runbooks and Troubleshooting Guides") plus extension hooks for future development.

## Runbooks and Troubleshooting

### Pipeline stuck on a note (`processing_status='processed'` not advancing)

1. Identify the stuck note ID from the database or logs.
2. Re-trigger manually:
   ```bash
   curl -X POST https://<backend>/api/ai/process/<note-id> \
     -H "Authorization: Bearer <token>"
   ```
3. If the note stays stuck, check Azure OpenAI quota in the portal (OpenAI resource → Quotas).
4. Review logs for `pipeline_failed` events: in Log Analytics, filter `ContainerAppConsoleLogs_CL` by `Log_s contains "pipeline_failed"`.

### Sync queue not draining

1. Check `/api/health` from the PWA — if the backend is unreachable, all sync ops queue locally.
2. Check JWT expiry — the access token is 30-minute TTL; trigger a refresh via the auth flow.
3. Check the `deadLetter` IndexedDB table in browser DevTools (Application → IndexedDB → cortex-db → deadLetter). Entries there have failed 5+ times and need manual review.
4. Check `syncQueue` drain logs: `GET /api/sync/pull` and `POST /api/sync/push` response codes.

### Voice not transcribing

1. Verify the Speech key and region: `az cognitiveservices account keys list --name cortex-speech --resource-group cortex-rg`.
2. Check the WS auth token is fresh — the PWA passes `?token=<access_token>`; if expired, reconnect.
3. Look for the log line `Loaded {n} phrases for user {id}` in Container App logs. If `n=0` for a user with vocabulary terms, check Postgres connectivity from the Container App.
4. Try the file-upload path: `POST /api/voice/upload` with a short `.webm` blob to isolate the WS vs. SDK issue.

### Cost spike alert

1. Azure Portal → Cost Management → Costs by resource → filter last 7 days.
2. If Azure OpenAI tokens are spiking, reduce pipeline concurrency: in `backend/app/pipeline/processor.py`, lower the `asyncio.gather` concurrency or add a semaphore.
3. If the Container App is scaling beyond 3 replicas unexpectedly, check the CPU scaling rule in the Container App → Scale and replicas tab.
4. Budget alert thresholds: $100 (warning) and $140 (action). Both are configured as Azure Cost Management budgets (see `docs/DEPLOYMENT.md` § Budget Alerts).

## Extension Points

### Adding a new pipeline stage

1. Add a new coroutine in `backend/app/pipeline/processor.py` following the `_stage_*` pattern.
2. Wrap all Azure SDK calls with `tenacity` retry (see `backend/app/utils/retry.py`).
3. Update the `process_note(note_id)` orchestrator to call the new stage at the appropriate checkpoint.
4. Add a migration if the stage requires new columns.
5. Write a test in `backend/tests/test_pipeline.py` mocking the new external call.

### Adding a new API router

1. Create `backend/app/api/<name>.py` with an `APIRouter`.
2. Import and register in `backend/app/main.py` under `/api/<name>`.
3. Add Pydantic schemas to `backend/app/schemas/<name>.py`.

### Bumping the Azure OpenAI API version

The current pin is `2024-10-21` (env var `AZURE_OPENAI_API_VERSION`). To upgrade to a newer GA version (e.g. `2025-01-01`):
1. Update the default in `backend/app/config.py` and the value hardcoded in `infra/main.bicep`.
2. Test with `respx` mocks targeting the new version string.
3. Update this note with the new version.

### Migrating to Container Apps Jobs for Distill

The nightly distill schedule currently runs inside the FastAPI process via APScheduler (B14 — `minReplicas=1`). To migrate to Container Apps Jobs (reducing cost by allowing scale-to-zero for the API):
1. Create a new `infra/modules/distill-job.bicep` with `Microsoft.App/jobs` resource (cron trigger `59 23 * * *`).
2. Push the distill image as a separate Dockerfile or a shared image with a different `CMD`.
3. Set `minReplicas: 0` on the Container App after verifying the job fires.
4. Remove APScheduler from `app/main.py`.
This is tracked as a future ticket and is not blocking MVP.
