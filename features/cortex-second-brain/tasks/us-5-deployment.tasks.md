# User Story: US-5 — Deployment (Bicep + deploy.sh + GitHub Workflows)

> Feature: cortex-second-brain
> Requirements: `/features/cortex-second-brain/requirements/requirements.md`
> Design: `/features/cortex-second-brain/designs/design.md`
> Spec: `SECOND_BRAIN_BUILD_SPEC.md` Phase 1 items 20–21 (section 4.2), deployment 5.2

## Acceptance Criteria

- `infra/main.bicep` matches the **canonical Bicep template in design.md** (NOT spec § 5.2 verbatim — design includes B1/B4/B14 deltas: `openaiLocation` param for OQ-1, Postgres firewall rule for OQ-5, full `Microsoft.App/containerApps` for OQ-7, `Microsoft.Web/staticSites` for OQ-6, `minReplicas: 1` for B14). Provisions Postgres B1ms with pgvector extension config, Storage Account StorageV2 LRS, Azure OpenAI S0 (in `westus`), Azure Speech S0, Azure AI Vision S1, Container App Environment + the Container App itself, ACR Basic, Static Web App Free, with all documented outputs.
- `infra/deploy.sh` runs end-to-end (resource group → Bicep deploy → ACR build → Container App update → Alembic migrate → Static Web App publish) per spec § 5.2.
- `infra/parameters.json` provides parameter values (with secrets pulled from Azure Key Vault references — no plaintext).
- `infra/modules/{container-app,postgres,storage,cognitive-services,static-web-app}.bicep` decompose `main.bicep` for clarity.
- `.github/workflows/deploy-backend.yml` builds and pushes Docker image to ACR and updates the Container App on push to `main`.
- `.github/workflows/deploy-frontend.yml` builds the PWA and deploys to Azure Static Web Apps on push to `main`.
- A successful deploy yields a working frontend URL and backend API URL with CORS configured for the frontend domain.

## Status
**Status**: Not Started
**Started**: TBD
**Completed**: TBD

## Relevant Documentation
- `/features/cortex-second-brain/designs/design.md` — Bicep Template, Project Structure, Environment Variables
- `SECOND_BRAIN_BUILD_SPEC.md` § 4.4 (env vars), § 5.2 (Bicep + deploy.sh)

## TDD Hook
Tester writes a smoke-test script at `backend/tests/test_deployed_smoke.py` (gated by env flag `RUN_DEPLOYED_SMOKE=1`) that hits `/api/health` against `BACKEND_URL` from env. Coder waits for failing-tests signal before authoring deploy artifacts.

---

## Tasks

- [ ] 1 Bicep IaC
  - [ ] 1.1 Create `infra/main.bicep` per the canonical Bicep template in design.md § "Bicep Template (canonical, OQ-1/OQ-5/OQ-6/OQ-7 resolved)". Required parameters: `appName`, `location`, `openaiLocation` (default `'westus'`, B1/OQ-1), `containerImageTag`, `frontendOrigin`, `@secure() dbAdminPassword`, `@secure() jwtSecretKey`. Provision: (a) Postgres Flexible Server B1ms with pgvector configuration AND `AllowAllAzureServicesAndResourcesWithinAzureIps` firewall rule (B4/OQ-5), (b) Storage Account StorageV2 LRS + `cortex-media` blob container, (c) OpenAI account in `openaiLocation`, (d) Speech account in `location`, (e) Vision (ComputerVision S1) in `location`, (f) Container App Environment, (g) ACR Basic, (h) the Container App itself with system-assigned identity, ingress `transport: 'auto'` + `allowInsecure: false`, secrets and env-var bindings per the canonical template, CPU scaling rule with `minReplicas: 1` (B14) / `maxReplicas: 3`, liveness + readiness probes on `/api/health` (B4/OQ-7), (i) Static Web App Free SKU (B4/OQ-6). Emit all documented outputs (`postgresHost`, `storageAccountName`, `openaiEndpoint`, `openaiRegion`, `speechRegion`, `visionEndpoint`, `acrLoginServer`, `containerAppFqdn`, `staticWebAppName`, `staticWebAppHost`).
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 1.2 Create `infra/modules/postgres.bicep` extracting the Postgres + pgvector config block — same SKU/version/storage/backup. Per design Open Question OQ-5, also include a firewall rule `AllowAllAzureServicesAndResourcesWithinAzureIps` with `startIpAddress: 0.0.0.0` and `endIpAddress: 0.0.0.0` so Container Apps can reach the database.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 1.3 Create `infra/modules/storage.bicep` for the Storage Account StorageV2 LRS resource
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 1.4 Create `infra/modules/cognitive-services.bicep` containing the OpenAI account (parameterized location, default `westus` — B1/OQ-1), Speech account (S0), and Vision (`ComputerVision` S1) — all three Cognitive Services accounts the canonical template requires
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 1.5 Create `infra/modules/container-app.bicep` for the Container App Environment + the Container App itself per the canonical design template. Resource MUST include: `identity: { type: 'SystemAssigned' }`, `ingress.transport: 'auto'` (WebSocket support), `allowInsecure: false`, the full `secrets` array with ACR password, DATABASE_URL, JWT_SECRET_KEY, and all Cognitive Services keys, the full `env` array binding each setting from design § "Environment Variables" to either an output or a `secretRef`, CPU scaling rule (target 70%, **`minReplicas: 1`** (B14 — keeps APScheduler distill alive), `maxReplicas: 3`), liveness + readiness HTTP probes on `/api/health`. **Log-scrubbing for WebSocket token (B12):** configure the Container App so the `?token=` query parameter is redacted before reaching Application Insights / access logs (e.g. an Application Insights TelemetryProcessor injected via env var `APPLICATIONINSIGHTS_LOGGING_FILTERS`, or document a manual Log Analytics workbook redaction step in `docs/DEPLOYMENT.md` if no native Bicep affordance exists).
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 1.6 Create `infra/modules/static-web-app.bicep` for the Static Web App (Free SKU) pointing to the `frontend/` build output. Per design Open Question OQ-6 — use `Microsoft.Web/staticSites` resource so the entire stack is reproducible from Bicep (rather than relying on `az staticwebapp create` in `deploy.sh`).
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 1.7 Create `infra/parameters.json` with non-secret parameter values; secrets reference Key Vault by `keyVaultReferenceId`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 2 Deploy script
  - [ ] 2.1 Create `infra/deploy.sh` verbatim from design / spec § 5.2 — six-step flow: create resource group, deploy Bicep, ACR build, Container App update, run Alembic via `containerapp exec`, build+deploy frontend SWA. Use `set -e`. Print frontend and backend URLs at end.
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 2.2 Add a teardown helper `infra/teardown.sh` that runs `az group delete --name $RESOURCE_GROUP --yes` for clean dev iteration (read-only — never invoked from CI)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 3 GitHub Actions
  - [ ] 3.1 Replace placeholder `.github/workflows/deploy-backend.yml` with workflow: trigger on push to `main` paths `backend/**`, login to Azure via OIDC, `az acr build` to push `cortex-api:${{ github.sha }}`, `az containerapp update --image` to roll the new revision
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 3.2 Replace placeholder `.github/workflows/deploy-frontend.yml` with workflow: trigger on push to `main` paths `frontend/**`, run `npm ci && npm run build` in `frontend/`, deploy `dist/` to Static Web App via the official `Azure/static-web-apps-deploy` action
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 3.3 Document required GitHub repository secrets in `docs/DEPLOYMENT.md`: `AZURE_CREDENTIALS`, `AZURE_STATIC_WEB_APPS_API_TOKEN`, `RESOURCE_GROUP`, `ACR_NAME`, `CONTAINER_APP_NAME`
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 4 Operational docs
  - [ ] 4.1 Populate `docs/DEPLOYMENT.md` with: prerequisites (Azure CLI, Docker), one-time bootstrap (Key Vault + service principal), running `infra/deploy.sh`, verifying via `/api/health`, rollback procedure (`az containerapp update --image cortex-api:<previous-sha>` + `alembic downgrade -1`)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 4.2 Populate `docs/ARCHITECTURE.md` summary linking back to `design.md` (no duplication — pointer only)
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 4.3 Populate `docs/API_REFERENCE.md` with a pointer to FastAPI `/docs` Swagger UI; static endpoint table mirroring design "API / Interfaces"
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 4.4 Populate `docs/EXTENDING.md` with the runbook hooks from design "Runbooks and Troubleshooting Guides"
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD

- [ ] 5 Wire CORS, rate-limit, and Azure budget alerts
  - [ ] 5.1 In `backend/app/main.py`, install `slowapi` middleware enforcing 100 req/min/user (critique mitigation #8); attach to FastAPI app
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 5.2 In `infra/main.bicep`, add an Azure Cost Management budget alert resource (or document the manual portal step in DEPLOYMENT.md) at $100 and $140 thresholds per spec § 2.11
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
  - [ ] 5.3 Verify `CORS_ORIGINS` env var in deployed Container App points to the actual SWA URL emitted by deploy.sh; add a script step that updates the env var post-SWA-create
    - **Started**: TBD
    - **Completed**: TBD
    - **Duration**: TBD
