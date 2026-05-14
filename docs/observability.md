# Observability — Workbook & Cost-Rate Alert

This runbook covers the **Cortex Operations Overview** Azure Monitor Workbook and the
companion **RAG cost-rate metric alert**. Both target the `cortexks-ai` Application
Insights component in resource group `cortex-rg`. They complement the budget & health
alerts already documented in [`docs/DEPLOYMENT.md`](./DEPLOYMENT.md).

---

## Workbook: Cortex — Operations Overview

> **Status: LIVE** — deployed 2026-05-14 (Round 23) as `616a9790-ef54-58b1-a75e-36e5d589b96c` in `cortex-rg`.

Source-of-truth template: [`infra/observability/workbook-cortex-overview.json`](../infra/observability/workbook-cortex-overview.json).

### What it shows

| Section | Window | Data source |
|---|---|---|
| Today's RAG cost (USD) | last 24h | `customMetrics` (App Insights) — `cortex.rag.cost_usd_estimate` |
| Top 10 costliest `(route, model)` pairs | last 24h | `customMetrics` |
| Error rate per route (5xx %) | last 6h | `requests` |
| p95 / p50 latency per route | last 6h | `requests` |
| Replica restart count | last 24h | `InsightsMetrics` (Container App `RestartCount`) |

### View the workbook (post-deploy)

1. Azure Portal → **Application Insights** → `cortexks-ai` → **Workbooks**.
2. Open *Cortex — Operations Overview* (or paste the JSON via *New* → *Advanced Editor*
   → *Gallery Template* and paste `workbook-cortex-overview.json`).

### Deploy the workbook via `az` (post-merge)

`az portal workbook` is the supported CLI surface for ARM-managed workbooks. The
JSON in the repo is the *serialised content* (`Notebook/1.0`); the ARM resource wraps
it.

```bash
# Pre-reqs
RG=cortex-rg
AI_NAME=cortexks-ai
AI_ID=$(az monitor app-insights component show --app "$AI_NAME" -g "$RG" --query id -o tsv)
SUB=$(az account show --query id -o tsv)

# Deterministic GUID for the workbook resource (so re-runs are idempotent).
# Generate once, then pin it. Example:
WB_NAME=$(python -c "import uuid; print(uuid.uuid5(uuid.NAMESPACE_URL, 'cortex/observability/overview'))")

# Substitute the real subscription into the fallback resource ID before upload.
sed "s|00000000-0000-0000-0000-000000000000|$SUB|g" \
  infra/observability/workbook-cortex-overview.json \
  > infra/observability/workbook-cortex-overview.rendered.json

az portal workbook create \
  --resource-group "$RG" \
  --name "$WB_NAME" \
  --display-name "Cortex — Operations Overview" \
  --serialized-data @infra/observability/workbook-cortex-overview.rendered.json \
  --category workbook \
  --source-id "$AI_ID" \
  --kind shared

rm infra/observability/workbook-cortex-overview.rendered.json
```

To update an existing workbook, re-run the same command — `az portal workbook create`
upserts when `--name` matches an existing GUID. Alternatively use
`az portal workbook update --name "$WB_NAME" --resource-group "$RG" --serialized-data @...`.

> The fallback resource ID baked into the JSON uses an `00000000-…` placeholder
> subscription. The `sed` step above rewrites it to the live subscription before
> upload so portal links resolve correctly.

---

## RAG cost-rate metric alert

> **Status: LIVE** — deployed 2026-05-14 (Round 23). Created with `skipMetricValidation` since the custom metric has not yet been ingested; alert will activate once `cortex.rag.cost_usd_estimate` data flows.

Fires when the RAG pipeline burns through more than **$0.50 USD/hour** of model spend
(custom metric `cortex.rag.cost_usd_estimate`). At $0.50/hr sustained that's ~$12/day
≈ $360/mo — well above the expected single-user usage of <$5/mo, so it's a clean
"someone is hammering the API or a runaway loop is running" signal without false
positives during normal use. Routes through the existing `cortex-alerts-ag` action
group (Round 13).

### Live config (to be created post-merge)

| Field | Value |
|---|---|
| Name | `cortexks-rag-cost-rate` |
| Resource | App Insights `cortexks-ai` |
| Signal | Custom metric `cortex.rag.cost_usd_estimate` (namespace `azure.applicationinsights`) |
| Aggregation | `Total` (Sum) over **1 hour** |
| Threshold | `> 0.50` (USD) |
| Frequency | Every 15 minutes |
| Action group | `cortex-alerts-ag` |
| Severity | 2 (Warning) |

### Create the alert via `az` (post-merge)

```bash
RG=cortex-rg
AI_ID=$(az monitor app-insights component show --app cortexks-ai -g "$RG" --query id -o tsv)
AG_ID=$(az monitor action-group show -g "$RG" -n cortex-alerts-ag --query id -o tsv)

az monitor metrics alert create \
  --name cortexks-rag-cost-rate --resource-group "$RG" \
  --scopes "$AI_ID" \
  --condition "total customMetrics/cortex.rag.cost_usd_estimate > 0.50" \
  --window-size 1h --evaluation-frequency 15m \
  --severity 2 \
  --action "$AG_ID" \
  --description "RAG token spend exceeded \$0.50/hr — investigate /api/ai/answer traffic for runaway calls or abuse"
```

> The metric name appears as `customMetrics/cortex.rag.cost_usd_estimate` in the
> `azure.applicationinsights` namespace once App Insights has ingested at least one
> sample. If `az monitor metrics alert create` complains the metric is unknown,
> hit `/api/ai/answer` once in production first to seed the namespace, then re-run.

### Inspect / update / delete

```bash
az monitor metrics alert show -g cortex-rg -n cortexks-rag-cost-rate
az monitor metrics alert update -g cortex-rg -n cortexks-rag-cost-rate \
  --set criteria.allOf[0].threshold=1.00
az monitor metrics alert delete -g cortex-rg -n cortexks-rag-cost-rate
```

---

## Custom metrics emitted by the backend

Tracked via the OpenTelemetry → Azure Monitor exporter wired up in PR alpha (Round 20).
The workbook + alert above depend on these names being stable.

| Metric | Type | Dimensions | Emitted by |
|---|---|---|---|
| `cortex.rag.cost_usd_estimate` | counter (USD) | `route`, `model` | RAG pipeline (`/api/ai/answer`) — PR beta |
| `requests` (built-in) | distribution (ms) | `name`, `resultCode` | App Insights auto-instrumentation — PR alpha |

When adding a new custom metric, document it here so workbook owners know it exists.

---

## Related docs

- [`docs/DEPLOYMENT.md`](./DEPLOYMENT.md) — Budget alerts, health-check alerts, action group setup.
- [`infra/observability/workbook-cortex-overview.json`](../infra/observability/workbook-cortex-overview.json) — Workbook template.
- [`backend/tests/test_workbook_template.py`](../backend/tests/test_workbook_template.py) — Static introspection test that prevents regressions in the workbook JSON.
