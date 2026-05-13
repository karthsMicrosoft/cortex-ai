# Log Analytics Alert — Leaked Token Detection (B12 Log-Scrubber)

> **Round 22 — 2026-05-14**

## What this alert does

The backend `_ScrubTokenFilter` (in `backend/app/main.py`) redacts `?token=<jwt>` from
all uvicorn log records before they reach any handler. If a log entry still contains an
un-scrubbed JWT (matching `token=ey` — JWTs always start with `eyJ`), the scrubber
either failed or was bypassed. This scheduled-query alert fires within 5 minutes of any
such leak appearing in Container App console logs.

---

## KQL query

```kusto
ContainerAppConsoleLogs_CL
| where Log_s has "token=ey"
| where Log_s !has "token=REDACTED"
| project TimeGenerated, Log_s, ContainerAppName_s
```

This searches the `ContainerAppConsoleLogs_CL` table (auto-ingested by Azure Container
Apps into the bound Log Analytics workspace) for lines that contain the raw JWT prefix
`token=ey` but do **not** contain `token=REDACTED` (which is the scrubbed form).

---

## az CLI command to create the alert

```bash
# 1. Resolve workspace and action-group resource IDs
WORKSPACE_ID=$(az monitor app-insights component show \
  --app cortexks-ai -g cortex-rg \
  --query "workspaceResourceId" -o tsv)

AG_ID=$(az monitor action-group show \
  -g cortex-rg -n cortex-alerts-ag \
  --query id -o tsv)

# 2. Create the scheduled-query alert rule
az monitor scheduled-query create \
  --name "cortexks-leaked-token-alert" \
  --resource-group cortex-rg \
  --scopes "$WORKSPACE_ID" \
  --condition "count 'leaked_tokens' > 0" \
  --condition-query leaked_tokens="ContainerAppConsoleLogs_CL | where Log_s has 'token=ey' | where Log_s !has 'token=REDACTED'" \
  --action-groups "$AG_ID" \
  --evaluation-frequency 5m \
  --window-size 5m \
  --severity 1 \
  --description "Fires when an un-scrubbed JWT token appears in Container App logs (B12 log-scrubber failure)"
```

### Parameter notes

| Parameter | Value | Why |
|---|---|---|
| `--scopes` | Log Analytics workspace bound to `cortexks-ai` | Query runs against workspace, not App Insights |
| `--severity 1` | Warning | Token leak is security-relevant but not a full outage |
| `--evaluation-frequency 5m` | Every 5 minutes | Fast detection without excessive cost |
| `--window-size 5m` | 5-minute lookback | Matches eval frequency; no overlap |
| `--condition` | `count > 0` | Any single leaked token is worth alerting on |
| `--action-groups` | `cortex-alerts-ag` | Routes email to `karths@microsoft.com` |

---

## How to test

1. **Unit tests** — `backend/tests/test_log_scrubber_alert.py` verifies the
   `_ScrubTokenFilter` correctly redacts tokens and leaves non-token content intact.

2. **Manual KQL test** — In the Azure Portal → Log Analytics workspace → Logs, run:
   ```kusto
   ContainerAppConsoleLogs_CL
   | where Log_s has "token=ey"
   | where Log_s !has "token=REDACTED"
   | take 10
   ```
   Should return 0 rows if the scrubber is working.

3. **Dry-run alert** — Temporarily modify the condition to `count > -1` (always fires)
   to verify the action group delivers the email, then revert.
