# Cortex — Second Brain — Research Findings

**Feature:** cortex-second-brain
**Author:** Researcher agent
**Date:** 2026-04-29
**Audience:** Architect (with key conflict callouts at top)

---

## 0. TL;DR — Conflicts the Architect Must Address First

These findings change the design direction or require updated decisions. Each is repeated with full context below.

| # | Conflict | Severity | Spec source | Action |
|---|---|---|---|---|
| C1 | **Azure OpenAI gpt-4o-mini and text-embedding-3-small are NOT available in `westus2`** for either Standard (regional) or Global Standard deployments per the Apr-2026 Microsoft Foundry availability tables. The spec hard-codes `westus2` (Section 9 of requirements; Bicep `Microsoft.CognitiveServices/accounts` in Section 5.2). | **BLOCKER** | requirements §9, spec Bicep §5.2 | Decouple the Azure OpenAI account region from the rest of the stack — deploy AOAI in `eastus2` or `swedencentral` (have full coverage of both models in Standard & Global Standard) or `westus` (regional Standard supports both); keep Container Apps, Postgres, Speech, Blob, AI Vision in `westus2`. |
| C2 | **`python-jose==3.3.*` carries CVE-2024-33663 (algorithm-confusion) and CVE-2024-33664 (DoS via large JWE).** The fixes shipped in 3.4.0 (Mar 2025) and 3.5.0 (May 2025), so the spec pin `python-jose[cryptography]==3.3.*` is below the patched line. FastAPI's own docs have moved to recommending PyJWT. | **HIGH** | spec §4.3 backend deps | Bump to `python-jose[cryptography]>=3.5,<4` **or** switch to `pyjwt>=2.10`. PyJWT is the recommended path for new code. |
| C3 | **`openai==1.40.*` is two major versions behind.** The Python SDK reached 2.x on 2025-09-30 and is at 2.33.x as of Apr 2026. The spec's Azure OpenAI API version `2024-10-21` is also old; current Azure preview is `2025-04-01-preview` and stable GA `2025-01-01`. Newer SDK shapes use `chat.completions.create` and `embeddings.create` the same way, but type stubs and async behavior differ. | **MEDIUM** | spec §4.3 + §4.4 env | Bump to `openai>=1.55,<3` (or pin `openai>=2.30,<3` for newest stable); align API version. |
| C4 | **`asyncpg==0.29.*` is two minors behind.** Latest is 0.31.0 (Nov 2025). 0.29 lacks Python 3.13/3.14 wheels and is missing SQL parser fixes. | **MEDIUM** | spec §4.3 | Bump to `asyncpg>=0.30,<0.32`. |
| C5 | **`alembic==1.13.*` is five minors behind** (latest 1.18.4, Feb 2026). 1.13 → 1.18 is non-breaking but contains migration-graph fixes and PG `IF NOT EXISTS` improvements. | **LOW** | spec §4.3 | Bump to `alembic>=1.16,<2`. |
| C6 | **`pgvector==0.3.*` (Python lib) is one minor behind** (latest 0.4.2, Dec 2025). The 0.4 line adds sparse-vector and binary-quantization helpers (not used by us) but is fully back-compat for our HNSW + cosine usage. | **LOW** | spec §4.3 | Bump to `pgvector>=0.4,<0.5`. |
| C7 | **`pydub==0.25.*` (last release Mar 2021) and `passlib==1.7.*` (last release Oct 2020) are effectively unmaintained.** `passlib[bcrypt]` further breaks on bcrypt ≥ 4.1 (`AttributeError: module 'bcrypt' has no attribute '__about__'`). | **MEDIUM** | spec §4.3 | Replace `passlib[bcrypt]` with direct `bcrypt>=4.2` calls (FastAPI security tutorials moved here in 2025). For pydub: pin `pydub==0.25.1` and pin `bcrypt<4.1` if you must keep passlib. Audio conversion is also doable with `ffmpeg-python` if you want a maintained alternative. |
| C8 | **Frontend pins are 1–3 majors stale.** React 18.3 → 19.2 (Oct 2025); Vite 5 → 8 (Mar 2026); Tailwind 3 → 4 (CSS-first config); Zustand 4 → 5 (drops <React 18, custom equality moved). vite-plugin-pwa 0.20 → 1.2 (stable 1.0 reached Apr 2025). | **MEDIUM** | spec §4.3 frontend | Either accept the spec's pins as a deliberate "frozen LTS-ish" snapshot OR bump to current majors. If bumping, factor the Tailwind v4 CSS-first migration into the design (no `tailwind.config.js`) and the Vite 8/Rolldown change. |

Everything else below is supporting evidence and non-blocking context (Azure availability, costs, deployment patterns).

---

## 1. Backend dependency audit (spec §4.3)

| Package | Spec pin | Latest stable (Apr 2026) | Status | Notes |
|---|---|---|---|---|
| fastapi | `0.115.*` | 0.136.1 (Apr 23 2026) | Stale (~21 minor versions) | No reported CVEs on PyPI page. 0.115 → 0.136 is back-compat for `APIRouter`, `Depends`, `WebSocket` we use. Would recommend `fastapi>=0.115,<0.140` to ride along. |
| uvicorn | `0.30.*` | 0.46.0 (Apr 23 2026) | Stale | `uvicorn[standard]` adds `httptools` and `websockets`. Bump to `>=0.32,<0.50`. |
| sqlalchemy[asyncio] | `2.0.*` | 2.0.49 (Apr 3 2026) on the 2.0 line; 2.1.0b2 in beta | Current | The 2.0 pin is fine; do **not** upgrade to 2.1 betas yet. |
| asyncpg | `0.29.*` | 0.31.0 (Nov 24 2025) | Stale | See C4 above. |
| pgvector (Python) | `0.3.*` | 0.4.2 (Dec 5 2025) | Stale | See C6. The Postgres extension itself is server-side and managed by Azure; only this Python helper bumps. |
| alembic | `1.13.*` | 1.18.4 (Feb 10 2026) | Stale | See C5. |
| python-jose[cryptography] | `3.3.*` | 3.5.0 (May 28 2025) | **Vulnerable at 3.3** | See C2 — CVE-2024-33663 + CVE-2024-33664. |
| passlib[bcrypt] | `1.7.*` | 1.7.4 (Oct 8 2020) | **Unmaintained, breaks bcrypt ≥ 4.1** | See C7. |
| python-multipart | `0.0.*` | 0.0.20 (Apr 2025) line; (note: had CVE-2024-53981 in versions <0.0.18 — DoS via malformed multipart). | Pinned too loose | Tighten to `python-multipart>=0.0.18`. |
| openai | `1.40.*` | 2.33.0 (Apr 28 2026) | Stale by one major | See C3. |
| azure-cognitiveservices-speech | `1.40.*` | 1.49.1 (Apr 15 2026) | Slightly stale | 9 minor versions; no breaking changes for `SpeechRecognizer` + `PhraseListGrammar`. |
| azure-storage-blob | `12.22.*` | 12.28.0 (Jan 6 2026) | Slightly stale | Bump to `>=12.24,<13`. |
| azure-ai-vision-imageanalysis | `1.0.*` | 1.0.0 (Oct 16 2024) | Current (still on 1.0) | Status flagged "Beta" on PyPI but is the only GA ImageAnalysis SDK. OK to keep. |
| pydub | `0.25.*` | 0.25.1 (Mar 10 2021) | Unmaintained but functional | See C7. |
| httpx | `0.27.*` | 0.28.1 (Dec 6 2024) | Slightly stale | 0.28 has the `URLTypes` reintroduction; 1.0 is in dev. Bump to `>=0.28,<0.29`. |
| pydantic-settings | `2.4.*` | 2.14.0 (Apr 20 2026) | Stale | Bump to `>=2.6,<3`. |
| tenacity | `8.5.*` | 9.1.4 (Feb 7 2026) | Stale by one major | 8 → 9 dropped Python <3.10 support; otherwise back-compat. Bump to `>=9.0,<10`. |

**Recommended consolidated backend pins (drop-in):**

```
fastapi>=0.115,<0.140
uvicorn[standard]>=0.32,<0.50
sqlalchemy[asyncio]>=2.0.30,<2.1
asyncpg>=0.30,<0.32
pgvector>=0.4,<0.5
alembic>=1.16,<2
pyjwt>=2.10,<3                # replaces python-jose; OR python-jose[cryptography]>=3.5,<4
bcrypt>=4.2,<5                # replaces passlib[bcrypt]; or pin bcrypt<4.1 if keeping passlib
python-multipart>=0.0.18,<0.1
openai>=2.30,<3               # if 2.x SDK acceptable; otherwise openai>=1.55,<2
azure-cognitiveservices-speech>=1.45,<2
azure-storage-blob>=12.24,<13
azure-ai-vision-imageanalysis>=1.0,<2
pydub==0.25.1                 # last release; alternative: ffmpeg-python>=0.2.0
httpx>=0.28,<0.29
pydantic-settings>=2.6,<3
tenacity>=9.0,<10
```

---

## 2. Frontend dependency audit (spec §4.3)

| Package | Spec pin | Current (Apr 2026) | Notes |
|---|---|---|---|
| react / react-dom | `^18.3.0` | **19.2.5** (Apr 8 2026) | React 19 GA Dec 2024. Breaking: `useTransition` callback may return a promise; legacy refs API removed. Most app code carries forward. |
| react-router-dom | `^6.26.0` | 7.x line is current | v7 = framework mode + data router; v6 stays maintained. v6 → v7 migration is non-trivial; safe to keep on v6 for MVP. |
| zustand | `^4.5.0` | **5.x** (released late 2024) | See C8. v5 drops React <18, drops UMD/SystemJS, removes default export, requires `createWithEqualityFn` for custom equality. |
| dexie | `^4.0.0` | 4.4.2 (Mar 2026) | Same major; safe bump to `^4.4`. |
| dexie-react-hooks | `^1.1.0` | 1.1.x current | OK. |
| uuid | `^10.0.0` | 11.x is current | v11 is back-compat for `v4()`; safe. |
| recharts | `^2.12.0` | 2.x current line | OK. |
| react-force-graph-2d | `^1.25.0` | 1.x current | OK. |
| wavesurfer.js | `^7.8.0` | 7.x current | OK. |
| lucide-react | `^0.400.0` | 0.5xx current | OK; the version number is artisanal. |
| date-fns | `^3.6.0` | 4.x current | v4 is back-compat (timezones first-class); minor breaking around `formatDistance` rounding. Safe to bump. |
| typescript | `^5.5.0` | 5.7+ stable; 5.8 in pre-release | OK; bump to 5.7. |
| vite | `^5.4.0` | **8.0.10** (Apr 2026) | See C8. Major change in v8: Rolldown bundler default. Vite 5 is end-of-life. |
| vite-plugin-pwa | `^0.20.0` | 1.2.0 (Nov 2025) | API stable since 1.0; same Workbox-backed config. Bump. |
| vitest | `^2.0.0` | 2.x current; 3.x in dev | OK. |
| tailwindcss | `^3.4.0` | **4.2.x** (Apr 2026) | See C8. v4 is CSS-first (`@theme`), no `tailwind.config.js`, replaces PostCSS plugin chain. Migration tool exists. |
| @vitejs/plugin-react | `^4.3.0` | 4.x | OK. |

**Recommendation for the Architect:** Either explicitly call out the spec's pins as a "frozen 2024-Q3 snapshot for reproducibility" — which is a valid choice for a single-user MVP — **or** bump frontend to current. If bumping, the largest design impact is Tailwind v4's CSS-first config (move `tailwind.config.js` content into a `@theme` block in the root CSS file).

---

## 3. Azure OpenAI in `westus2` (spec §9, Bicep §5.2)

**Source:** `learn.microsoft.com/en-us/azure/ai-services/openai/concepts/models` (confirmed Apr 2026 page; `ms.date: 2026-04-17`).

### Findings

- **Standard (regional) deployment table:** `westus2` is **absent**. Only US regions in this table are `eastus`, `eastus2`, `northcentralus`, `southcentralus`, `westus`, and `westus3`. So a regional Azure OpenAI account in `westus2` cannot host gpt-4o-mini or text-embedding-3-small.
- **Global Standard deployment table:** `westus2` is **also absent**. (`westus` and `westus3` are present and have full coverage of both models.) Global Standard routes globally regardless of the AOAI account's home region — but you still must pick a home region from the supported list.
- **Speech, Storage, AI Vision, Container Apps, Static Web Apps, PostgreSQL Flexible Server** all support `westus2`, so the rest of the stack can stay there.

### Implication

The spec's "all Azure resources in `westus2`" constraint cannot be met as written. The Architect has three workable patterns:

1. **Recommended — split region for AOAI only:** Deploy `Microsoft.CognitiveServices/accounts` (kind=OpenAI) in `eastus2` (best US coverage of GA models including the gpt-5 line if we ever need it). Everything else stays in `westus2`. Cross-region latency from `westus2` → `eastus2` for Azure OpenAI HTTPS calls is ~70 ms, well within the 2 s voice SLO and the 500 ms search SLO (since search hits Postgres locally; embeddings are computed only on write, not on query — *re-check this against design*).
2. **Move AOAI to `westus`:** `westus` supports gpt-4o-mini and text-embedding-3-small in both Standard and Global Standard. Lowest latency from `westus2` (~5 ms). This is the simplest fix.
3. **Use `swedencentral`:** Best feature coverage including fine-tuning if we ever need it. ~150 ms from `westus2`.

In all three, the Bicep template needs the `openai` resource to take a separate `openaiLocation` parameter rather than `location: resourceGroup().location`.

### Sources
- https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/models (Foundry models, Apr 17 2026)
- https://azure.microsoft.com/en-us/pricing/details/azure-openai/

---

## 4. Azure Speech in `westus2`

**Source:** `learn.microsoft.com/en-us/azure/ai-services/speech-service/regions` (Apr 28 2026).

Confirmed for `westus2`:

- Real-time transcription — **yes**
- Fast transcription — **yes**
- Batch transcription — **yes**
- Custom speech training — **yes** (dedicated hardware region)
- Whisper via batch transcription — no
- Whisper via Azure OpenAI — no (no AOAI in westus2 anyway)
- Custom keyword advanced + keyword verification — yes
- TTS neural + HD voices — yes
- Real-time avatar — yes
- Real-time speech translation + Live interpreter — yes

`PhraseListGrammar` is supported by the SDK across all regional Speech endpoints; the **500-phrase per-session ceiling** is a documented SDK limit (`learn.microsoft.com/en-us/azure/ai-services/speech-service/improve-accuracy-phrase-list`). Phrase weight range is `[0.0, 2.0]`, default `1.0` — this matches the spec/addendum exactly. **No conflict** for FR-7.

### Source
- https://learn.microsoft.com/en-us/azure/ai-services/speech-service/regions
- https://learn.microsoft.com/en-us/azure/ai-services/speech-service/improve-accuracy-phrase-list

---

## 5. Azure PostgreSQL Flexible Server + pgvector

- **pgvector is GA on Azure Database for PostgreSQL Flexible Server**, and the `westus2` region is supported for all current Postgres versions including the recent PG 18 GA on Azure (2026).
- The extension is allowlisted as `VECTOR` (the spec already uses `VECTOR,UUID-OSSP` — correct). Inside the database, `CREATE EXTENSION vector` (the spec uses `CREATE EXTENSION IF NOT EXISTS "pgvector"` — Azure's docs use `vector` as the extension name. **Minor doc-level fix** for the Architect: confirm the `CREATE EXTENSION` statement uses `vector` not `pgvector`.).
- `B1ms` Burstable (1 vCore, 2 GB) compute is ~$12.41/mo (compute only); add storage (32 GB ≈ $4) and 7-day backup ≈ free up to provisioned storage size. Realistic monthly = **$15–18 for compute+storage**, well below the spec's $25–35 estimate. Spec is conservative — good.
- **HNSW indexing scale check:** for 1k–10k notes at 1536 dims, the HNSW index fits comfortably in 2 GB RAM. The PG B1ms tier handles single-user loads up to ~10k notes per the public benchmark trends.
- **Auto-pause / auto-stop** is supported on Burstable tier; saves ~30% as the spec claims.

### Sources
- https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-use-pgvector
- https://learn.microsoft.com/en-us/azure/postgresql/release-notes/release-notes
- https://azure.microsoft.com/en-us/pricing/details/postgresql/flexible-server/
- https://techcommunity.microsoft.com/blog/adforpostgresql/postgresql-18-now-ga-on-azure-postgres-flexible-server/4469802

---

## 6. Azure Container Apps cost & scale-to-zero

- Consumption plan **does scale to zero** when minReplicas=0 — confirmed in 2026 docs; "When an application is configured to scale to zero replicas, no usage charges apply." Free tier per subscription per month: 180,000 vCPU-seconds + 360,000 GiB-seconds + 2,000,000 requests.
- For a single-user MVP with WebSocket sessions for STT (which keep one replica warm during recording), expected vCPU-seconds usage is ~100k/mo, fully within the free tier. **The spec's $15–25 estimate is high — actual cost should be $0–10 for this workload.**
- One non-obvious cost: the **Container Apps Environment** itself has no per-hour charge, but the Log Analytics workspace it auto-provisions does charge for ingestion. Configure log sampling or use the "Logs (Preview)" Azure-native logging mode introduced in 2025 to keep this near-zero.

### Sources
- https://azure.microsoft.com/en-us/pricing/details/container-apps/
- https://learn.microsoft.com/en-us/azure/container-apps/billing
- https://techcommunity.microsoft.com/blog/appsonazureblog/understanding-idle-usage-in-azure-container-apps/4419197

---

## 7. Azure Static Web Apps

- **Free tier** covers single-user PWA hosting (100 GB bandwidth/mo, 0.5 GB storage, 2 custom domains). No conflict with budget.
- Free tier does **not** include managed Functions back-end with auth integration beyond a low quota — but the spec uses Static Web Apps for the React PWA only, with the FastAPI backend on Container Apps, so this is fine.
- Bicep type: `Microsoft.Web/staticSites` is the right type for IaC — the spec doesn't include this resource yet; the Architect should add it.

---

## 8. Azure AI Vision (OCR)

- Pay-as-you-go: **~$1.50 per 1,000 transactions** for the Read API (Standard tier S1) in 2026.
- Free tier: 5,000 transactions/month, capped at 20 transactions/minute.
- For ~100 OCR images/month (spec assumption), this is **inside the free tier** → effective cost $0. Spec's $2–5 estimate is correct for safety margin if usage spikes.
- `westus2` is supported for AI Vision (Computer Vision resource, kind=ComputerVision).

### Source
- https://azure.microsoft.com/en-us/pricing/details/computer-vision/

---

## 9. Azure Container Registry

- Basic tier: ~$0.167/day = **~$5/month** (matches spec).
- Note: 10 GB included storage on Basic. Our FastAPI image with ffmpeg is ~400 MB. Headroom is fine.
- Alternative — Container Apps now supports pulling from any anonymous-access registry without needing ACR; but ACR is preferred for private images and gives managed-identity auth into Container Apps without a registry password.

### Source
- https://azure.microsoft.com/en-us/pricing/details/container-registry/

---

## 10. Azure Speech pricing reality-check

- Real-time STT Standard: **$1/hour** ($0.0167/min) as of 2026.
- The spec assumes ~5 hours of STT/month → $5. Spec range $10–15 is conservative; actuals likely closer to $5.
- Custom Speech model adapt/host = pricier; Personal Dictionary uses `PhraseListGrammar` which is free (no custom model).

### Source
- https://azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services/

---

## 11. Azure OpenAI pricing reality-check

- gpt-4o-mini (Apr 2026): **$0.15 per 1M input tokens, $0.60 per 1M output tokens** (Standard / Global Standard).
- text-embedding-3-small: $0.02 per 1M tokens.
- Spec's per-note token budget (~500 in / ~200 out for capture+organize, 200 tokens for embedding) → **~$0.0002 per note** → **~$0.20/mo at 1k notes**. This matches the spec's §2.11 calculation — **no conflict**.
- Shadow Reader (Phase 2) adds ~600 input + ~30 output tokens per substantive note → ~$0.0001/note × ~1k notes = $0.10/mo, matching the addendum's claim of ~$0.11/mo.

### Source
- https://azure.microsoft.com/en-us/pricing/details/azure-openai/
- https://pricepertoken.com/pricing-page/model/openai-gpt-4o-mini

---

## 12. Total cost realism (against $150 budget, NFR-4)

| Item | Spec estimate | Realistic Apr-2026 estimate | Notes |
|---|---|---|---|
| Static Web Apps | $0 | $0 | Free tier |
| Container Apps | $15–25 | $0–10 | Likely free-tier-bound |
| PostgreSQL B1ms | $25–35 | $15–25 | Includes storage + auto-pause savings |
| Blob Storage (10 GB hot) | $5–10 | $2–4 | Storage is cheap; egress at 1 GB/mo ≈ $0.09 |
| Speech (5 hr) | $10–15 | $5–8 | $1/hr standard |
| Azure OpenAI | $15–30 | $1–5 | Token volume tiny per note |
| AI Vision (100 OCR) | $2–5 | $0 | Inside free tier |
| Container Registry Basic | $5 | $5 | Fixed |
| Log Analytics (auto-provisioned) | (not in spec) | $1–3 | Watch out — only line that grows unexpectedly |
| **TOTAL** | **$77–145** | **~$30–60** | Well inside the $150 budget |

**The $150/mo budget is comfortably realistic.** The spec is conservative on Container Apps and AOAI — actual costs should land at ~$30–60/mo for the described single-user volume. Phase-2 additions (~$0.20/mo) confirmed.

---

## 13. Deployment pattern findings (FastAPI + Container Apps + Bicep)

For Architect's reference; spec's Bicep skeleton is solid but missing a few production hardening bits the 2026 patterns include:

1. **Use managed identity (`identity: { type: 'SystemAssigned' }`) on the Container App** and grant it `Storage Blob Data Contributor` on the storage account, `Cognitive Services User` on Speech/Vision/OpenAI, and `Azure Database for PostgreSQL Flexible Server Long Term Retention Backup User` (or use Entra auth). The spec uses connection strings — works but is less secure.
2. **Container App revision mode = "Single"** for an MVP keeps things simple; switch to "Multiple" only when you want blue/green.
3. **CPU target scaling rule**: `kind: 'cpu'`, target 70%, minReplicas 0, maxReplicas 3 — covers single-user bursts and idles to zero.
4. **Health probes** (`livenessProbe` + `readinessProbe` on `/health`) are mandatory in Container Apps to avoid the platform thrashing replicas.
5. **WebSocket support** is on by default in Container Apps but the ingress must have `transport: 'auto'` and `allowInsecure: false`. The spec's Bicep doesn't yet include the `containerApp` resource — that's where this goes.
6. **`registries` block on Container App** with `passwordSecretRef` or managed-identity auth into ACR — required for private images.
7. **Bicep `param` for `openaiLocation`** separate from `location` (per finding C1).
8. **Static Web App resource is missing** from the spec's Bicep — add `Microsoft.Web/staticSites` (Free SKU).
9. **Postgres `firewallRule` for Container Apps outbound IP** is needed; the simplest approach is to enable public access on the Postgres server with `Allow Azure Services` (a single firewall rule named `AllowAllAzureServicesAndResourcesWithinAzureIps` with `startIpAddress: 0.0.0.0` and `endIpAddress: 0.0.0.0`). The spec's Bicep doesn't include this and will fail at first connection.
10. **Bicep `secure()` parameters** — spec already uses these for `dbAdminPassword` and `jwtSecretKey`, good.

### Sources
- https://learn.microsoft.com/en-us/azure/templates/microsoft.app/containerapps
- https://learn.microsoft.com/en-us/azure/developer/python/tutorial-containerize-simple-web-app
- https://oneuptime.com/blog/post/2026-02-16-deploy-fastapi-azure-container-apps/view (Feb 2026 walkthrough)

---

## 14. Other small notes for the Architect

- **`AZURE_OPENAI_API_VERSION=2024-10-21`** in §4.4 is OK but a year stale. Current GA is `2025-01-01-preview` superseded by `2025-04-01-preview`. The bump unlocks structured outputs and the new tool-calling shape — relevant if Shadow Reader returns structured JSON.
- **Embedding dim** = 1536 for text-embedding-3-small is correct (confirmed on the model card). pgvector HNSW with `m=16, ef_construction=64` (per spec) is the right config for <100k vectors.
- **Python 3.11** Dockerfile base is fine, but Python 3.12 is the de-facto standard for FastAPI in 2026 and is supported by all our pinned deps. Optional bump.
- **Whisper-via-Azure-OpenAI is NOT in westus2** but the spec uses Azure Speech (not Whisper) for STT, so this doesn't matter.
- **PWA Lighthouse ≥ 90** (NFR-5) is achievable with vite-plugin-pwa 1.x defaults; the most common miss is the "installable" PWA criterion which requires a 512×512 maskable icon — the spec's `icon-512-mask.png` covers this.

---

## 15. Citations index

PyPI (dependency truth):
- https://pypi.org/project/fastapi/
- https://pypi.org/project/uvicorn/
- https://pypi.org/project/sqlalchemy/
- https://pypi.org/project/asyncpg/
- https://pypi.org/project/pgvector/
- https://pypi.org/project/alembic/
- https://pypi.org/project/python-jose/
- https://pypi.org/project/passlib/
- https://pypi.org/project/openai/
- https://pypi.org/project/azure-cognitiveservices-speech/
- https://pypi.org/project/azure-storage-blob/
- https://pypi.org/project/azure-ai-vision-imageanalysis/
- https://pypi.org/project/pydub/
- https://pypi.org/project/httpx/
- https://pypi.org/project/pydantic-settings/
- https://pypi.org/project/tenacity/

CVE references:
- python-jose CVE-2024-33663 (algorithm confusion): https://www.sentinelone.com/vulnerability-database/cve-2024-33663/
- python-jose CVE-2024-33664 (JWE DoS): tracked alongside 33663; fixed in 3.4.0/3.5.0
- FastAPI move to PyJWT discussion: https://github.com/fastapi/fastapi/discussions/9587

Azure documentation:
- AOAI model availability: https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/models
- Speech regions: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/regions
- Speech PhraseList: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/improve-accuracy-phrase-list
- pgvector on Azure: https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-use-pgvector
- Container Apps billing: https://learn.microsoft.com/en-us/azure/container-apps/billing
- Container Apps pricing: https://azure.microsoft.com/en-us/pricing/details/container-apps/
- Postgres pricing: https://azure.microsoft.com/en-us/pricing/details/postgresql/flexible-server/
- AOAI pricing: https://azure.microsoft.com/en-us/pricing/details/azure-openai/
- AI Vision pricing: https://azure.microsoft.com/en-us/pricing/details/computer-vision/
- ACR pricing: https://azure.microsoft.com/en-us/pricing/details/container-registry/
- Speech pricing: https://azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services/

Frontend ecosystem:
- React 19.2 release: https://react.dev/blog/2025/10/01/react-19-2
- Vite 8 release: https://vite.dev/blog/announcing-vite8
- Tailwind v4: https://tailwindcss.com/docs/upgrade-guide
- Zustand v5 migration: https://zustand.docs.pmnd.rs/reference/migrations/migrating-to-v5
- vite-plugin-pwa: https://vite-pwa-org.netlify.app/

Deployment patterns:
- ACA + Bicep walkthrough (Feb 2026): https://oneuptime.com/blog/post/2026-02-16-how-to-deploy-azure-container-apps-using-bicep-templates/view
- FastAPI on ACA (MS Learn): https://learn.microsoft.com/en-us/azure/developer/python/tutorial-containerize-simple-web-app

---

*End of research findings. Forwarding summary to the Architect.*
