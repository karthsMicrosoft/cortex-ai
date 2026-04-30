# Deployment Guide

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

Azure Cost Management budget alerts are configured at **$100** and **$140** per month to stay within the $150 NFR-4 budget ceiling.

**Manual setup** (no native Bicep `Microsoft.Consumption/budgets` resource is wired in `main.bicep` due to subscription-scope constraint — portal step required):

1. Azure Portal → Cost Management + Billing → Budgets → + Add
2. Scope: subscription or resource group `cortex-rg`
3. Amount: $100 → alert at 100%; create a second budget at $140
4. Alert recipients: `karths@microsoft.com`

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
