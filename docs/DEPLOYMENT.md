# Deployment Guide

> **Currently deployed state (2026-04-30):** See `HANDOFF.md` § 2 for live URLs, resource names, and region splits. The "spec defaults" below describe a fresh deploy; current live deploy uses `appName=cortexks`, `location=centralus`, `openaiLocation=eastus`. See `DECISIONS.md` § 1 for why those differ from spec.

## Prerequisites

- **Azure CLI** (`az`) version 2.60+ — `az --version`
- **Docker** — for local image builds (not required if using `az acr build`)
- **Node.js 20+** — for frontend build
- **Python 3.11+** — for local Alembic runs

## Required GitHub Repository Secrets

| Secret | Description |
|---|---|
| `AZURE_CREDENTIALS` | JSON service-principal credentials for OIDC login (`az ad sp create-for-rbac --sdk-auth`) |
| `AZURE_STATIC_WEB_APPS_API_TOKEN` | Deployment token from the Static Web App resource (`az staticwebapp secrets list`) |
| `RESOURCE_GROUP` | Azure resource group name (default: `cortex-rg`) |
| `ACR_NAME` | Azure Container Registry name (default: `cortexacr`) |
| `CONTAINER_APP_NAME` | Container App resource name (default: `cortex-api`) |

## One-Time Bootstrap

### 1. Create Azure Key Vault and store secrets

```bash
KV_RG="cortex-kv-rg"
KV_NAME="cortex-kv"
LOCATION="westus2"

az group create --name "$KV_RG" --location "$LOCATION"
az keyvault create --name "$KV_NAME" --resource-group "$KV_RG" --location "$LOCATION"

# Store secrets (generate strong values before running)
az keyvault secret set --vault-name "$KV_NAME" --name cortex-db-admin-password --value "<strong-random-password>"
az keyvault secret set --vault-name "$KV_NAME" --name cortex-jwt-secret-key    --value "<64-char-random-string>"
```

### 2. Update `infra/parameters.json`

Replace the three `__PLACEHOLDER__` values with:
- `__SUBSCRIPTION_ID__` — your Azure subscription ID (`az account show --query id -o tsv`)
- `__KV_RESOURCE_GROUP__` — Key Vault resource group (e.g. `cortex-kv-rg`)
- `__KEY_VAULT_NAME__` — Key Vault name (e.g. `cortex-kv`)

### 3. Grant deployment principal access to Key Vault

```bash
SP_OBJECT_ID=$(az ad sp show --id <client-id-from-AZURE_CREDENTIALS> --query id -o tsv)
az keyvault set-policy --name "$KV_NAME" --object-id "$SP_OBJECT_ID" \
  --secret-permissions get list
```

## Running `infra/deploy.sh`

```bash
chmod +x infra/deploy.sh infra/teardown.sh

# Override defaults via env vars if needed:
export RESOURCE_GROUP="cortex-rg"
export LOCATION="westus2"
export APP_NAME="cortex"

bash infra/deploy.sh
```

The script performs six steps:
1. Create resource group
2. Deploy all Azure resources via Bicep (`infra/main.bicep`)
3. Build the backend Docker image and push to ACR
4. Update the Container App to use the new image
5. Run Alembic migrations via `az containerapp exec`
6. Build the React PWA and deploy to Azure Static Web Apps

At the end it prints:
```
Frontend: https://<swa-host>.azurestaticapps.net
Backend:  https://<container-app-fqdn>
```

## Verifying via `/api/health`

```bash
curl -s https://<container-app-fqdn>/api/health
# Expected: {"status":"ok"}
```

## Rollback Procedure

### Backend rollback

```bash
# Roll back to a previous image tag (use the git SHA from the failed deploy)
az containerapp update \
  --name cortex-api \
  --resource-group cortex-rg \
  --image cortexacr.azurecr.io/cortex-api:<previous-sha>
```

### Database rollback

```bash
az containerapp exec \
  --name cortex-api \
  --resource-group cortex-rg \
  --command "alembic downgrade -1"
```

### Frontend rollback

Azure Static Web Apps automatically retains previous deployments. Use the portal (Static Web Apps → Environments → Production → Deployment history) to reactivate the prior deployment.

## Budget Alerts

Azure Cost Management budget alerts are wired against the `cortex-rg` resource group to stay within the $150/mo NFR-4 budget ceiling.

**Live config** (created 2026-05-05 via `az consumption budget create-with-rg` + REST PUT for the Forecasted threshold):

| Budget | Scope | Amount | Thresholds | Recipients |
|---|---|---|---|---|
| `cortex-monthly` | RG `cortex-rg` | $150 / Monthly | 67% Actual (~$100, warning), 93% Actual (~$140, critical), 100% Forecasted (leading indicator) | `karths@microsoft.com` |

**Inspect:**
```bash
az consumption budget show-with-rg --resource-group cortex-rg --budget-name cortex-monthly
```

**Recreate from scratch:**
```bash
cat > /tmp/notif.json <<'JSON'
{
  "Actual_GreaterThan_67_Percent": {"enabled": true, "operator": "GreaterThan", "threshold": 67, "contact-emails": ["karths@microsoft.com"]},
  "Actual_GreaterThan_93_Percent": {"enabled": true, "operator": "GreaterThan", "threshold": 93, "contact-emails": ["karths@microsoft.com"]}
}
JSON
echo '{"startDate":"2026-05-01T00:00:00Z","endDate":"2027-05-01T00:00:00Z"}' > /tmp/tp.json
az consumption budget create-with-rg --resource-group cortex-rg --budget-name cortex-monthly \
  --amount 150 --category cost --time-grain Monthly \
  --time-period @/tmp/tp.json --notifications @/tmp/notif.json
# Then PUT https://management.azure.com/.../budgets/cortex-monthly?api-version=2024-08-01
# with the full body to add a Forecasted threshold (CLI cannot set thresholdType=Forecasted).
```

> **Note:** `Microsoft.Consumption/budgets` is not in `main.bicep` because budgets are subscription/RG-scope resources that require the latest eTag for re-deploys. Treating as one-time `az` command that's idempotent on re-run via `update-with-rg`.

## Health-Check Alerts

Three Azure Monitor alerts notify `karths@microsoft.com` when the live API is unhealthy. All three feed into a shared Action Group `cortex-alerts-ag`. Cost ~$1/month (the Application Insights availability test).

**Live config** (created 2026-05-07 via `az monitor` CLI, parallel to the Budget Alerts pattern):

| Alert | Severity | Scope | Fires when |
|---|---|---|---|
| `cortexks-api-restart-spike` | 2 (Warning) | Container App `cortexks-api` | `RestartCount` (max) >= 3 over 5 min — replica is crash-looping; liveness probe is restarting it faster than transient blips |
| `cortexks-api-5xx-rate` | 2 (Warning) | Container App `cortexks-api` | `Requests` (total, filtered `statusCodeCategory=5xx`) >= 10 over 5 min — container is up but the app is broken (DB exhausted, OpenAI key revoked, etc.) |
| `cortexks-api-availability` | 1 (Error) | App Insights `cortexks-ai` (web test `cortexks-api-health-ping`) | `availabilityResults/availabilityPercentage` (avg) < 100 over 5 min — synthetic ping to `/api/health` from the Chicago region failed (catches outages even when the platform thinks the container is healthy) |

**Inspect:**
```bash
az monitor metrics alert list -g cortex-rg -o table
az monitor app-insights web-test show -g cortex-rg --name cortexks-api-health-ping
az monitor action-group show -g cortex-rg -n cortex-alerts-ag
```

**Recreate from scratch:**
```bash
# 1. Action Group (single email recipient; reusable for future alerts)
az monitor action-group create -g cortex-rg -n cortex-alerts-ag \
  --short-name cortexag \
  --action email karths-email karths@microsoft.com

# 2. Container App restart-count alert
CA_ID=$(az containerapp show -n cortexks-api -g cortex-rg --query id -o tsv)
AG_ID=$(az monitor action-group show -g cortex-rg -n cortex-alerts-ag --query id -o tsv)
az monitor metrics alert create \
  --name cortexks-api-restart-spike --resource-group cortex-rg \
  --scopes "$CA_ID" \
  --condition "max RestartCount >= 3" \
  --evaluation-frequency 1m --window-size 5m --severity 2 \
  --action "$AG_ID" \
  --description "Container App replica restart count spiked - liveness probe likely failing"

# 3. Container App 5xx-rate alert (uses the statusCodeCategory dimension)
az monitor metrics alert create \
  --name cortexks-api-5xx-rate --resource-group cortex-rg \
  --scopes "$CA_ID" \
  --condition "total Requests >= 10 where statusCodeCategory includes 5xx" \
  --evaluation-frequency 1m --window-size 5m --severity 2 \
  --action "$AG_ID" \
  --description "Container App returning >=10 5xx responses in a 5-minute window - app-level failure"

# 4. Application Insights component (auto-binds to a default LA workspace)
az monitor app-insights component create \
  --app cortexks-ai --location centralus --resource-group cortex-rg \
  --kind web --application-type web

# 5. URL-ping availability test on /api/health (XML config required by the classic ping API).
#    The hidden-link tag binds the test to the AI component.
#    See backend/scripts/create_health_webtest.sh for the full XML template, OR re-run the
#    az monitor app-insights web-test create command from infra/.
#    Single region (us-il-ch1-azr / Chicago) keeps cost ~$1/mo; expand to 5 regions for ~$5/mo.

# 6. Availability alert on the AI component (NOT on the webtest resource —
#    microsoft.insights/webtests is not a supported metric namespace for metricAlerts)
AI_ID=$(az monitor app-insights component show --app cortexks-ai -g cortex-rg --query id -o tsv)
az monitor metrics alert create \
  --name cortexks-api-availability --resource-group cortex-rg \
  --scopes "$AI_ID" \
  --condition "avg availabilityResults/availabilityPercentage < 100" \
  --evaluation-frequency 1m --window-size 5m --severity 1 \
  --action "$AG_ID" \
  --description "Synthetic ping to /api/health below 100% availability in last 5 min"
```

> **Note:** Alerts live in Azure (operational state), not in `infra/main.bicep`. Same pattern as Budget Alerts — they're idempotent CLI commands and don't change between deploys.

### Auto-restart behaviour (already wired)

`infra/modules/container-app.bicep` lines 133–148 (and the equivalent block in `infra/main.bicep`) configure both probes against `/api/health`:

| Probe | Purpose | Period | Failure threshold | Effect on failure |
|---|---|---|---|---|
| Liveness | "Is the container alive?" | 30 s | 3 | Container Apps **restarts the replica** automatically |
| Readiness | "Is it accepting traffic?" | 10 s | 3 | Replica is **removed from ingress** (LB stops routing) |

So "auto-restart on failure" is **already in production** by virtue of the Bicep probes — no additional infra needed. The health-check alerts above provide the missing piece: notification when those restarts happen.

## Known Security Limitations (MVP Threat Model)

### SEC-07 — Refresh Token Revocation Gap (30-day replay window)

**Status:** Accepted risk for single-user MVP. Explicitly documented per review finding 1.8.

The `/api/auth/refresh` endpoint rotates the refresh token on every call (issues a new
one and sets it as httpOnly cookie), but does **not** invalidate the previous token.
This means a stolen refresh token can be replayed for up to 30 days after the legitimate
user has rotated.

**Threat model note:** For the single-owner personal-brain MVP, the threat surface is
low — there are no multi-user sessions or shared credentials. However, operators should
be aware of this gap.

**Future remediation:** Before multi-user or team deployment, implement a
`refresh_token_revocations` table (or Redis deny-set) keyed by JWT `jti` claim.
On each `/refresh` call, check the incoming token's `jti` against the deny-set and
add it after issuing the new token. This bounds replay to the network window of the
rotation call.

---

### SEC-06 — WebSocket Token in URL (Azure platform log exposure)

**Status:** Partially mitigated. Residual risk documented.

The `/api/voice/stream` WebSocket endpoint authenticates via `?token=<jwt>` in the URL
query string (per spec § 2.9). The application-layer scrubber (B12) redacts the token
from uvicorn logs, but Azure Container App HTTP access logs capture the raw URL before
reaching uvicorn.

**Required operator action:** Configure Azure Log Analytics workspace for the Container
App with a **short log retention window** (≤ 7 days) and treat access logs as sensitive.
Apply the following KQL transformation in your workbook to read-side redact tokens:

```kusto
ContainerAppConsoleLogs_CL
| extend ScrubURL = replace_regex(Log_s, @"[?&]token=[^& ]+", "token=REDACTED")
| project TimeGenerated, ScrubURL
```

**Future hardening:** Migrate WebSocket auth to a short-lived opaque voice-ticket token
(REST endpoint exchanges the JWT for a single-use opaque ticket → WebSocket uses ticket)
so the long-lived JWT never appears in any URL.

---

## WebSocket Token Log-Scrubbing (B12)

The `?token=<jwt>` query parameter used by `/api/voice/stream` is redacted from logs at two levels:

1. **Backend (`app/main.py`):** a `_ScrubTokenFilter` logging filter is attached to the root logger and `uvicorn.access` logger, replacing `?token=<value>` with `?token=REDACTED` in every log record before it is written.
2. **Container App access logs:** Azure Container Apps does not expose a native URL-scrubbing filter for its built-in access log stream. To prevent the raw URL from appearing in Log Analytics, add a KQL query transformation in a Log Analytics workbook:

```kusto
ContainerAppConsoleLogs_CL
| extend ScrubURL = replace_regex(Log_s, @"[?&]token=[^& ]+", "token=REDACTED")
| project TimeGenerated, ScrubURL
```

This workbook step is a read-side redaction; the raw log may still contain the token in the underlying table. For production hardening, consider migrating WebSocket auth to the `Sec-WebSocket-Protocol` subprotocol pattern (tracked as a future ticket).

## Local Development

1. Copy `backend/.env.example` to `backend/.env` and fill in your secrets.
2. Start a local PostgreSQL instance with pgvector:
   ```bash
   docker run -d --name cortex-postgres \
     -e POSTGRES_USER=cortexadmin \
     -e POSTGRES_PASSWORD=localpass \
     -e POSTGRES_DB=cortex \
     -p 5432:5432 \
     pgvector/pgvector:pg16
   ```
3. Run Alembic migrations:
   ```bash
   cd backend
   alembic upgrade head
   ```
4. Start the FastAPI dev server:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

## Docker Build

```bash
docker build -t cortex-api ./backend
docker run --env-file backend/.env -p 8000:8000 cortex-api
```

Health check: `curl http://localhost:8000/api/health` should return `{"status":"ok"}`.

> **Security note:** Real `.env` files must never be committed to source control.
> Use Azure Key Vault references for production secrets (injected via Container App secret references).

## Key Vault — secret rotation

**Live KV:** `cortexks-kv` in `cortex-rg` / `centralus` (created 2026-05-06).

The Container App's two sensitive secrets — the asyncpg connection string and the JWT signing key — are stored in Azure Key Vault and resolved by the Container App at runtime via its system-assigned managed identity. Rotating a secret in KV automatically propagates to new replicas; no Bicep redeploy needed.

| Secret name | Container App secret | Source |
|---|---|---|
| `cortex-database-url` | `database-url` | Full asyncpg connection string (`postgresql+asyncpg://cortexadmin:.../cortex`) |
| `cortex-jwt-secret-key` | `jwt-secret-key` | 64-byte hex JWT HS256 signing key |

### Rotate the JWT secret

```bash
NEW_JWT=$(python -c "import secrets; print(secrets.token_hex(64))")
az keyvault secret set --vault-name cortexks-kv --name cortex-jwt-secret-key --value "$NEW_JWT"
# Force the Container App to pull a fresh secret value (otherwise it caches for ~30 min):
az containerapp update --name cortexks-api --resource-group cortex-rg --revision-suffix "rotjwt$(date +%s)"
```

### Rotate the DB password

1. Update Postgres admin password (Azure Portal or `az postgres flexible-server update --admin-password`).
2. Construct the new connection string and store in KV:
   ```bash
   NEW_PW=...
   NEW_URL="postgresql+asyncpg://cortexadmin:${NEW_PW}@cortexks-db.postgres.database.azure.com:5432/cortex"
   az keyvault secret set --vault-name cortexks-kv --name cortex-database-url --value "$NEW_URL"
   az containerapp update --name cortexks-api --resource-group cortex-rg --revision-suffix "rotdb$(date +%s)"
   ```

### How the bootstrap was done (one-time, 2026-05-06)

```bash
# 1. Create the vault
az keyvault create --name cortexks-kv --resource-group cortex-rg --location centralus \
  --enable-rbac-authorization true --sku standard --retention-days 90

# 2. RBAC: writer for you, reader for Container App's managed identity
KV_ID=$(az keyvault show --name cortexks-kv --resource-group cortex-rg --query id -o tsv)
ME=$(az ad signed-in-user show --query id -o tsv)
CA=$(az containerapp identity show --name cortexks-api --resource-group cortex-rg --query principalId -o tsv)
az role assignment create --assignee-object-id $ME --assignee-principal-type User \
  --role "Key Vault Secrets Officer" --scope $KV_ID
az role assignment create --assignee-object-id $CA --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" --scope $KV_ID

# 3. Copy current Container App secrets into KV
az keyvault secret set --vault-name cortexks-kv --name cortex-database-url \
  --value "$(az containerapp secret show --name cortexks-api --resource-group cortex-rg --secret-name database-url --query value -o tsv)"
az keyvault secret set --vault-name cortexks-kv --name cortex-jwt-secret-key \
  --value "$(az containerapp secret show --name cortexks-api --resource-group cortex-rg --secret-name jwt-secret-key --query value -o tsv)"

# 4. Switch Container App secrets to KV references
az containerapp secret set --name cortexks-api --resource-group cortex-rg \
  --secrets \
    "database-url=keyvaultref:https://cortexks-kv.vault.azure.net/secrets/cortex-database-url,identityref:system" \
    "jwt-secret-key=keyvaultref:https://cortexks-kv.vault.azure.net/secrets/cortex-jwt-secret-key,identityref:system"

# 5. Roll a new revision so the secrets take effect
az containerapp update --name cortexks-api --resource-group cortex-rg --revision-suffix "kv$(date +%s)"
```

For brand-new infra deploys, swap `infra/parameters.json` for `infra/parameters.keyvault-template.json` (already pre-populated with the live `cortexks-kv` ID + `cortex-jwt-secret-key` / `cortex-db-admin-password` references) and omit the `JWT_SECRET_KEY` / `DB_ADMIN_PASSWORD` env vars from `deploy.sh`.

